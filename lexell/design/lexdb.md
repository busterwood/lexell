# lexdb: a small SQL database server

Status: the decisions in section 0 are the user's (2026-11-09). Stages D0 to
D3, the read-only snapshots of 4.5, and D4's secondary indexes and joins
are built (2026-11-09, branch `lexdb`); section 9 records how, with what differs from this design and
the measurements. Section 3's measurements were taken on the development
machine, through WSL2's virtual disk.

## 0. Decisions

2026-11-09:

- **On disk, not in memory.** The database lives on disk, and memory holds
  only a cache. RAM has become too expensive to assume that the working data
  fits in it.
- **SSDs and NVMe only.** No optimization for spinning disks: no layout for
  sequential locality, no seek scheduling, no read-ahead heuristics.
- **Consumer NVMe first; enterprise drives later.** A consumer drive has no
  power-loss protection, so a flush costs about a millisecond (section 3).
  Defaults and benchmarks are chosen for that. Enterprise drives, which flush
  in tens of microseconds, should only change defaults, never the design.
- **The Postgres wire protocol, and only that for now.** Existing clients,
  including Lexell's own `pgwire`, connect unchanged. Whether to emulate
  enough of `pg_catalog` for `psql`'s `\d` commands is decided later.
- **The name is lexdb.** The server is `cmd/lexdb.lxl`, and its modules are
  `cmd/lexdb_*.lxl`, the same layout as the jq port. If it outgrows `cmd/`,
  it moves to a directory of its own.
- **File I/O starts on the existing helper pool.** io_uring is added behind
  the same park/wake interface when a measurement shows the pool is the
  limit. The concurrency note already says io_uring comes "later if file
  I/O needs it", and a database is that case.
- **Two isolation levels, both in the plan.** Read-write transactions are
  serializable (4.4), the default and the only level for writes; there is no
  read-write snapshot isolation, which allows write skew. Read-only
  transactions are snapshots (4.5): every statement sees the database as of
  the start, for a page built from several queries on one connection. Both
  are built (section 9).
- **No cost-based optimizer for now.** The planner's rules (4.8) give
  predictable plans. Costs are reconsidered with joins and secondary indexes
  (D4), and then only a small model: a row count per table, distinct-value
  estimates per index, join order over a few tables, plans fixed per
  prepared statement and shown by `EXPLAIN`.

## 1. Recommendation

Classic engines carry three subsystems that make up much of their size:
ARIES-style recovery, a lock manager, and a buffer pool with latches and
pins. They need them because of three assumptions:

1. many threads share pages;
2. pages are updated in place, on drives that can leave a page half written
   (torn) when power fails;
3. uncommitted data may be written to disk (ARIES's "steal").

This design drops all three:

1. **One thread runs everything.** Transactions are coroutines that park on
   I/O, as in [concurrency.md](concurrency.md). The commit step cannot park,
   so no other task can run inside it. That gives the same guarantee as a
   `Shared.with` block.
2. **Copy-on-write pages.** A page that a durable checkpoint refers to is
   never overwritten. A torn write can therefore never damage a page that is
   in use.
3. **No steal.** A transaction keeps its writes in a private buffer until it
   commits, so pages only ever hold committed data.

What remains is small:

- a log of committed row changes, with group commit at the end of each
  event-loop turn;
- a checkpoint that writes changed pages to new locations and then switches
  one of two meta pages;
- a version check on B+tree leaf pages at commit, which gives serializable
  isolation, phantoms included.

There is no undo pass, no compensation log records, no full-page images, no
doublewrite buffer, no lock manager and no latches. One mechanism (section
4.5) serves both read-only snapshots and checkpoints.

A rough target is a few tens of thousands of lines of Lexell. For scale,
SQLite is about 150,000 lines of C and LMDB's core is about 10,000.

## 2. Survey

| System | What started small | What it grew, and why | What we take or leave |
|---|---|---|---|
| PostgreSQL | Berkeley POSTGRES. Its storage manager never overwrote a row, so old data could be queried ("time travel"). | Time travel was removed in the 1990s; the no-overwrite heap stayed. That is why it needs VACUUM, freezing and transaction-ID wraparound handling. A forked process per connection led to external poolers (PgBouncer). It added extensible types and index methods, a genetic join search, TOAST, and a buffer cache that duplicates the OS page cache. Well over a million lines of C. | Take the wire protocol. Leave the heap, the per-connection processes and the extensibility. |
| MySQL / InnoDB | Fast, non-transactional MyISAM for read-heavy websites. | Transactions came with a plug-in engine (InnoDB), giving two logs (binlog and redo) with an internal two-phase commit between them. InnoDB's doublewrite buffer guards against torn pages. The query cache was added for speed and removed in 8.0, because its global lock was a bottleneck. | Take the clustered primary key, and secondary indexes that store the primary key. Leave everything else. |
| SQLite | Still small, as a library: one writer, file locks, a bytecode VM (VDBE). | It isn't a server. | Take the register-based bytecode VM as the first executor. |
| LMDB | A copy-on-write B+tree with one writer and two meta pages. Readers keep an old root and never block. About 10,000 lines. | It uses `mmap` (see the next row), and each commit writes the path from changed leaves to the root plus a meta page. | Take copy-on-write pages, the two meta pages and readers on old roots. Leave `mmap`, and amortize the root-path writes over a checkpoint rather than every commit. |
| *Are You Sure You Want to Use MMAP in Your DBMS?* (Crotty, Leis and Pavlo, CIDR 2022) | — | — | For Lexell there's a stronger reason than theirs: a page fault blocks the only thread, and a coroutine cannot park on a fault. One cold page would stall every connection. We keep our own cache with `O_DIRECT`. |
| H-Store / VoltDB; *OLTP Through the Looking Glass* (2008) | Serial execution in memory, by one thread per partition. | That paper found that buffer management, locking, latching and logging each took a large share of instructions in a conventional engine. | Take serial commit on one thread. Leave the requirement that data fit in memory. Anti-caching (DeBrabant et al., 2013) also handled cold data on disk under serial execution, by aborting and restarting the transaction. Our coroutines park instead. |
| Silo (Tu et al., SOSP 2013) | Optimistic concurrency with validation at commit. | Multi-core, with per-record latches. | Take the idea of checking B+tree node versions at commit to catch phantoms (its "node set"). With one thread, no latches are needed. |
| LeanStore, vmcache (Leis et al.) | Buffer managers that run close to in-memory speed. | Both are built for many threads. | One thread needs neither pointer swizzling nor optimistic latches. A hash table from page number to frame, plus clock eviction, is enough. |
| RocksDB and LSM trees | Fast writes. | Compaction, bloom filters and dozens of tuning options. Reads may check several levels. | Leave. A B+tree with copy-on-write checkpoints is simpler and reads in one path. |
| TigerBeetle | Single-threaded, fixed-size records, a ledger for finance. | — | Take deterministic simulation testing: the disk sits behind an interface with a simulated implementation that loses or tears writes that were never flushed (stage D0). |

## 3. The development drive, measured

Program: [bench/disk/probe.c](../bench/disk/probe.c). Run three times on
2026-11-09 (load about 0.4 to 2, AMD Ryzen 7 8745HS, WSL2, ext4 on a VHDX
virtual disk, 4 GiB test file). The first and third runs agreed. During the
second run's read tests, the host was still writing back the 4 GiB file,
and they were 5 to 10 times slower. The table shows runs 1 and 3. Latencies
are in microseconds.

| operation | p50 | p99 |
|---|---:|---:|
| 4 KiB append to a growing file, then `fdatasync` | 2,060–2,400 (run 2: 10,400) | 3,400–4,200 |
| 4 KiB `pwrite` into a preallocated file, then `fdatasync` | 900–1,000 | 1,400–2,100 |
| 64 KiB `pwrite` into a preallocated file, then `fdatasync` | 990–1,050 | 1,600–1,800 |
| 4 KiB `O_DIRECT \| O_DSYNC` `pwrite` | 910–935 | 1,700–1,750 |
| 4 KiB `O_DIRECT` random read, one at a time | 123–136 | 210–1,000 |

| 4 KiB `O_DIRECT` random reads in parallel | IOPS |
|---|---:|
| 4 threads | 25,000–27,000 |
| 16 threads | 83,000 |
| 32 threads | 103,000–128,000 |

What follows for the design:

- **A flush costs about 1 ms, whether it carries 4 KiB or 64 KiB.** So
  roughly 1,000 flushes a second is the ceiling, and group commit is
  essential: throughput is about the commits per batch times 1,000. With at
  most one flush in flight, the event loop keeps running transactions while
  the flush runs on a helper thread, and those commits join the next batch.
  The latency floor for a durable commit is one flush, about 1 ms.
- **Never grow a file at commit.** Appending to a growing file costs 2 to
  10 times as much, because ext4 must also journal the file's new size. Log
  segments are preallocated and reused.
- **The drive needs many reads in flight.** One read at a time gives about
  7,000 reads a second, while 32 in flight give more than 100,000. The
  helper pool starts 4 threads by default (`LXL_HELPERS`, at most 64;
  `native/rt.c` `rt_pool_start`), so the server must start about 32. That
  is the measurement that will eventually justify io_uring.
- **These are WSL2 numbers.** They include Hyper-V's storage stack and the
  VHDX file on NTFS. The ~1 ms flush suggests the flush does reach the
  device, but this doesn't prove it. The virtual disk also reports itself as
  rotational with 512-byte sectors, so the server must not trust what the
  device reports. Correctness work doesn't need the real drive, because the
  simulated disk covers crashes. Performance numbers that we publish should
  be repeated on bare-metal Linux (section 8).

## 4. Design

### 4.1 Files and pages

- **The page file.** It is made of 4 KiB pages, opened with `O_DIRECT`, and
  read and written only in aligned 4 KiB units. Pages 0 and 1 are the two
  meta pages. Every page ends with a CRC32C (x86-64-v3 has the `crc32`
  instruction) and its own page number, so a page read from the wrong
  location is detected as well as a corrupt one.
- **Meta pages.** Each holds:
  - a checkpoint number;
  - the root page of each B+tree (the catalog is itself a tree);
  - the free-list root;
  - the batch number the checkpoint covers;
  - the log position to replay from;
  - a CRC.

  Checkpoint *n* writes meta page *n* mod 2. Recovery uses the valid meta
  page with the higher checkpoint number.
- **Page reuse.** Checkpoint *n* frees the pages that checkpoint *n−1*
  referred to and that it replaced. Those pages become reusable once meta
  page *n* has been flushed and no live snapshot reads them. Until then,
  recovery could still fall back to checkpoint *n−1*. The free list is
  itself copy-on-write and saved with each checkpoint, so recovery never
  has to walk the whole tree.
- **Flush errors are fatal.** If `fdatasync` fails, the server stops and
  recovers on restart. It never retries the flush. This is PostgreSQL's
  lesson from 2018 ("fsyncgate"): after a failed flush, Linux may already
  have discarded the dirty pages.

### 4.2 B+trees and keys

- Each table is a B+tree clustered on its primary key, and every table must
  declare one. Each secondary index is a B+tree keyed on the index key
  followed by the primary key. Page locations move at every checkpoint;
  primary keys don't.
- Keys are encoded so that comparing their bytes gives SQL order. That
  covers integers, `DECIMAL(38)`, text with the binary UTF-8 collation,
  booleans, timestamps and composite keys. The tree then only ever compares
  bytes.
- A value larger than about a quarter of a page goes to overflow pages.
  This is a small version of TOAST: no compression, at least at first.

### 4.3 The page cache

- A hash table maps page numbers to frames, with clock eviction. It is
  owned by one thread, so it has no latches.
- A frame is pinned only while a coroutine is parked holding a reference to
  it.
- The size is set at startup, and the cache never grows past it.
- Range scans read the next leaves ahead of time, with several reads in
  flight (section 3).

### 4.4 Transactions

1. **Execute** (may park). The transaction reads through the cache and
   records each leaf page it reads together with that page's version. Its
   writes stay in a private buffer.
2. **Prepare** (may park). The transaction loads the leaf pages its writes
   will touch.
3. **Commit** (cannot park; the server traps if it does).
   - Check that every recorded leaf version is unchanged. If one has
     changed, abort with SQLSTATE `40001`, which Postgres clients already
     treat as "retry".
   - Apply the writes and bump the versions of the leaves they change.
   - Append the log record to the current batch.
4. **Reply after the flush.** At the end of the loop turn, the batch is
   written and flushed. A reply goes out only after the flush that covers
   everything its transaction observed. That holds for read-only
   transactions too, so no client sees data that a crash could still lose.

Checking leaf versions also catches phantoms. An insert into a range that
another transaction scanned changes a leaf it read. A leaf split changes
versions too, which can cause a false conflict. A busy leaf page can also
cause false conflicts, so measure how often that happens before checking
anything finer, such as individual rows.

A single SQL statement outside `BEGIN` is a transaction of its own and
rarely conflicts. With `BEGIN` … `COMMIT`, a transaction can span network
round trips without holding anything. It only records versions.

### 4.5 Snapshots and checkpoints: one mechanism

A page is copied when it is written only if some live snapshot can still
see the current version. If nothing holds a snapshot, a page is changed in
place in memory.

- **Read-only transactions** (`START TRANSACTION READ ONLY`, and long
  reports) take a snapshot. They never abort and never block a writer.
- **A checkpoint is itself a snapshot.** It writes the snapshot's changed
  pages to new locations, in parallel. Then it flushes, writes the meta
  page and flushes again. Commits continue while it runs.

A snapshot's old page versions stay in memory until the snapshot ends.
That memory has a budget. A snapshot that exceeds it is cancelled, like
PostgreSQL's "snapshot too old" error.

### 4.6 The log

- **Segments.** The log is made of preallocated 64 MiB segments that are
  reused once a checkpoint no longer needs them.
- **Records.** Each holds a batch number, the after-image of each changed
  row (table, key, value, or a delete), and a CRC32C. There are no page
  images.
- **Written once.** Each batch is padded to a 4 KiB boundary, so a block
  that has been flushed is never written again. A torn write can then only
  damage the batch still in flight, never one that has been acknowledged.
  Padding costs at most 4 KiB per flush, about 4 MiB a second at 1,000
  flushes a second.
- **Generations.** Each segment header carries a generation number, so
  records left over from a segment's previous use are never replayed.
- **Recovery.** Load the newest valid meta page, then replay the log from
  its position until the first record whose CRC, generation or batch
  number doesn't follow on.
- **Replication** later uses the same log: a replica replays the log it is
  sent.

### 4.7 The wire protocol

The server is the mirror image of `lib/pgwire.lxl`:

- the startup message, SCRAM-SHA-256 and TLS through `lib/tls`;
- the simple query protocol;
- the extended query protocol: Parse, Bind, Execute and Sync, with prepared
  statements whose plans are cached;
- `COPY FROM STDIN` for bulk loads;
- cancel requests.

Binary formats are supported for the column types we have. `pg_catalog` is
decided later (section 0).

### 4.8 SQL and execution

- **Types.** `bigint`, `int`, `boolean`, `numeric(p,s)` with p ≤ 38 (the
  Lexell `Decimal`), `text`, `bytea` and `timestamptz`.
- **Statements.** `CREATE TABLE` (a primary key is required), `CREATE
  INDEX`, `DROP`, `INSERT`, `UPDATE`, `DELETE`, `BEGIN`, `COMMIT`,
  `ROLLBACK`, and `SELECT`. `SELECT` supports `WHERE`, `ORDER BY`, `LIMIT`,
  inner and left joins, `GROUP BY` with the common aggregates, and
  parameters.
- **Left out.** Triggers, rules, inheritance, user-defined types,
  extensions, PL/pgSQL, and collations other than binary UTF-8. Views come
  later, if at all.
- **Planner.** Rules, not costs:
  - an equality on the primary key gives a point lookup;
  - a prefix of the key gives a range scan;
  - otherwise the longest matching index prefix is used, then a full scan;
  - joins are index nested loops, falling back to a hash join when the
    inner side has no usable index;
  - `ORDER BY` uses an index when one fits, and sorts otherwise.
- **Executor.** A register-based bytecode VM, as in SQLite. Later, prepared
  statements and stored procedures could be compiled to native code with
  Lexell's own backend (section 7).

## 5. Staged plan

Each stage ends with a gate that can be measured, and its results are
written into this note.

**D0: the disk interface and the simulated disk.**
- A `Disk` interface (read, write, flush, allocate) with two
  implementations:
  - the real one: `O_DIRECT` on the helper pool;
  - a simulated one that keeps writes that haven't been flushed separately.
    A "crash" keeps a random subset of them and tears some at 512-byte
    boundaries.
- Page CRC32C and the two meta pages.
- A Lexell version of the probe, to compare with section 3's C numbers.
- Gate: the meta-page switch survives every crash point the simulation
  produces.

**D1: one copy-on-write B+tree with checkpoints.**
- Byte keys and byte values, the page cache, checkpoint and recovery from
  the meta pages, the free list.
- Gate: random operations, with a crash at random points, checked against a
  simple in-memory map. Recovery must give exactly the last checkpoint's
  contents.

**D2: the log, group commit and transactions.**
- Commit as in 4.4 and 4.6, page-version validation, `40001` aborts.
- Gate:
  - after any simulated crash, every acknowledged commit is present and
    nothing else is;
  - a bank-transfer test with many concurrent coroutines keeps the total
    constant, which shows serializability;
  - measure commits per second against batch size on the real drive.

**D3: the pgwire server with the first SQL.**
- `CREATE TABLE`, `INSERT`, `SELECT` by key and range, `UPDATE`, `DELETE`,
  `BEGIN`/`COMMIT`, and the types in 4.8.
- Gate: Lexell's `postgres` client and `psql` connect and run the
  statements, and a pgbench-like load is measured.

**D4: the rest of version 1's SQL.**
- Secondary indexes, joins, `COPY`. (Read-only snapshots, `ORDER BY`,
  `LIMIT` and aggregates came earlier. Indexes, joins and `EXPLAIN` are
  built: 9.5. `COPY` is not yet.)

**D5: io_uring**, behind park/wake, when D2 to D4's numbers show the
helper pool is the limit.

**Later:**
- replicas fed by the log;
- `pg_catalog`;
- enterprise-drive defaults;
- native-compiled procedures;
- running the measurements on bare metal.

## 6. Costs and what is given up

- **One core does all writes.** At around 1,000 flushes a second on this
  drive, the flush is the limit long before the CPU is. Read scaling comes
  later from replicas.
- **Commits abort under contention**, and clients have to retry `40001`.
  Hot pages, such as a counter row or an append-only key at the right edge
  of the tree, conflict more than row locks would.
- **A large transaction's writes are buffered in memory**, so bulk changes
  go through `COPY` or a size limit.
- **Every checkpoint rewrites the path from each changed leaf to the
  root.** That amplifies writes, which wears flash. Measure it in D1 and D2.
- **Long snapshots hold memory** until they finish or hit the budget.
- **The rule-based planner is weak at analytical joins** over many tables.
  That is deliberate.
- **The helper pool means threads** and rules out `task.workers` after the
  pool starts (exit 15). The server is one process.

## 7. Ideas under consideration

- **Procedures compiled by Lexell.** A stored procedure written in Lexell
  could be compiled to native code at `CREATE PROCEDURE` and run inside the
  commit step. That only works if procedures cannot reach FFI or unsafe code.
- **Deterministic simulation of the whole server.** The simulated disk from
  D0 could be extended to the network and the clock, as TigerBeetle does.

## 8. Open questions

- **Bare-metal measurements.** Where should the published numbers come
  from: a Linux boot on this machine, or a second NVMe attached to WSL2 with
  `wsl --mount --bare`? WSL2 is fine for development and for crash
  correctness.
- **`pg_catalog`** (section 0).

## 9. As built (D0 to D3, snapshots, D4's indexes and joins)

Built on 2026-11-09 on branch `lexdb`, about 6,300 lines in
`cmd/lexdb*.lxl`: `lexdb_base` (errors, CRC32C, a generator), `lexdb_disk`
(real and simulated files), `lexdb_page` (page formats), `lexdb_store`
(cache, trees, transactions, log, checkpoints, recovery, snapshots),
`lexdb_sql` (lexer, parser), `lexdb_exec` (catalog, rows, keys, planner,
statements, sessions), `lexdb_wire` (protocol 3.0) and `lexdb` (the
server). Tests: `python3 lexell/tests/lexdb.py` (18 programs in
`tests/lexdb/run`, under `LXL_CHECK=1`).

    lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -o lexdb
    ./lexdb /path/to/data 127.0.0.1:5433
    psql "host=127.0.0.1 port=5433 user=me dbname=lexdb"

### 9.1 What differs from the design

- **Nodes are decoded into records** (`lexdb_page.Node`: arrays of keys,
  values and children) rather than worked on as slotted pages. Simpler;
  the cost is a decode per load and an encode per checkpoint. Measure before
  changing it.
- **No overflow pages yet**: a key is at most 512 bytes and a key and its row
  at most 1,350 (an entry over a third of a page cannot always split), so a
  row is limited to about 1.3 KB. Error 54000.
- **Old versions are kept per node, not per page**, as copies made when a
  commit changes a node a snapshot can see (4.5). Slots a snapshot may
  still reach are kept until it ends, and not evicted. A checkpoint is not
  a snapshot as 4.5 suggests: it encodes every dirty node inside one `with`
  (no park), then writes the pages outside it. That pause grows with the
  dirty set; it is the first thing to measure under a large write load.
- **The checkpoint waits for the log.** The meta page is written only after
  the log holds every commit the checkpoint includes. Without that, replay
  from the checkpoint's log position could re-apply an older batch over a
  newer, unlogged one and leave a transaction half applied.
- **Deleting does not merge nodes**: an empty node leaves its parent, an
  underfull one stays. **A dropped table's pages are not reclaimed** unless
  its nodes are in memory (the free list never sees the others).
- **Statements outside a block are retried** up to 10 times on 40001 (the
  client has seen nothing of the failed try). In a read-write block each
  statement waits, after it runs, until what it read is durable, since its
  result goes out before COMMIT (4.4).
- **Interpreted, not bytecode.** The executor walks the statement's tree.
- **No subqueries, CTEs, schemas, bytea, dates or times yet.**
- **Trust login**: no password, no TLS. The server listens on loopback by
  default.
- **A simple query with several statements** runs each in its own
  transaction, not one implicit transaction as PostgreSQL does.
- **Log segments are zero-filled** when made, not only allocated: a flush
  after writing into an allocated, unwritten extent cost twice as much
  (1.6 ms against 2.9 ms per pgbench transaction with one client).

### 9.2 Tests and what they catch

- `store_crash`: 40 seeds, three crashes each, at a random acknowledged
  commit, with a 3-node cache (evictions), 64 KiB log segments and a
  checkpoint every 24 KiB of log; the recovered tree must equal a model.
  Removing the flush before the meta page fails it (3 of 120).
- `store_bank`: 30 runs of 6 tasks making transfers with think time
  (conflicts and retries), a crash at a random moment: the money adds up
  and every acknowledged transfer survives. Skipping validation fails it
  at once. It does not catch removing the checkpoint's wait for the log
  (above): the window is narrow and a random crash rarely lands in it.
- `store_ckptwait` builds that window: a log flush held open (the simulated
  disk's `holdFlushes`), a later commit, a checkpoint, a crash. Recovery
  must give a prefix of the commits; without the wait 17 of 30 crashes leave
  a transaction half applied.
- `store_snapshot`: 60 snapshots totalling 1,200 accounts while 300
  transfers commit, with a 20-node cache; keeping no old versions fails it.
  A snapshot over the budget gets 72000.
- `exec_index_diff`: two tables with indexes and copies of them without,
  under the same random inserts, updates and deletes; 1,200 random queries
  and joins (index lookups and ranges against full scans, per-row lookups
  against hash joins) must agree, with a 12-node cache. Leaving the old
  index entry behind on UPDATE (974 differ) or DELETE (1,021), or making a
  range's lower bound exclusive (109), fails it.
- `exec_join`: each index, join and EXPLAIN feature once, checked by hand.
- `exec_index_diff` also compares ORDER BY/LIMIT and MIN/MAX through
  indexes with sorts, RIGHT JOIN with the LEFT JOIN the other way, FULL
  JOIN with the LEFT JOIN plus the unmatched rows, scans longer than a
  batch, and filtered indexes with plain scans. Caught: a backward cursor
  repeating a row, WHERE below a RIGHT JOIN, ON filtering the kept table,
  rows not added to a filtered index, a stale entry, `x >= 0` taken to
  imply `x > 0`, an implication across columns.
- `store_back`: backward scans equal forward scans reversed, with the
  transaction's own writes and in snapshots.
- `wire_client`: `lib/postgres` against the server in the same process.
- `store_real`: the real file system: write, reopen, read.

### 9.3 Measurements

pgbench 16.15 on the development machine (section 3: WSL2, consumer NVMe),
2026-11-09, `-M prepared`, a table of 10,000 rows, the server with its
defaults (`LXL_HELPERS=32`), 5 s runs, one run each:

| workload | clients | tps | latency |
|---|---:|---:|---:|
| UPDATE by key, then SELECT it (autocommit) | 1 | 611 | 1.6 ms |
| same | 8 | 1,146 | 7.0 ms |
| same | 32 | 3,376 | 9.5 ms |
| same | 64 | 5,376 | 11.9 ms |
| SELECT by key | 8 | 26,668 | 0.30 ms |
| BEGIN READ ONLY, two 100-row aggregates, COMMIT, beside 16 writers | 8 | 2,266 | 3.5 ms |
| (the 16 writers meanwhile) | 16 | 3,481 | 4.6 ms |

Size and memory (2026-11-09, the native backend): the binary is 993 KB
(773 KB through C), linking only libc. Resident memory: 4.0 MB at a fresh
start (33 threads: the main one and 32 I/O helpers); 6 MB with the
10,000-row table; 8.7 MB under 32 writing and 8 reading clients; 111 MB
after inserting 300,000 rows of about 80 bytes (a 34 MB data file), 112 MB
after a full scan and a 1,000-group GROUP BY over them. Restarted on that
database: 26 MB idle, 63 MB after a full scan. Memory is the cache, which
grows as pages are read and is not given back; a query's own memory is
small (rows stream in batches; groups keep running totals).

One client is close to the drive's flush (about 1 ms, section 3); more
clients share flushes (group commit). No run had a failed transaction.
These are first numbers, not a comparison: PostgreSQL on the same machine
is the comparison to make.

### 9.4 Next

1. Subqueries and CTEs (the user needs them soon): uncorrelated
   `IN (SELECT ...)` and scalar subqueries; correlated `EXISTS` and
   `NOT EXISTS` as semi-joins and anti-joins in the join levels; `WITH`
   as named subqueries, then `WITH RECURSIVE`.
2. The cache budget in bytes, not nodes (measured in 9.3: decoded nodes
   take 1.8 to 3.3 times their page, so the default of 100,000 nodes could
   reach 0.7 to 1.5 GB), a smaller decoded node, and why a restarted server
   idles at 26 MB.
3. Schemas (the user uses them extensively): `schema.table` names, the
   catalog keyed by schema, `CREATE SCHEMA`/`DROP SCHEMA`, `search_path`,
   and three-part column names (`s.t.c`) in the resolver.
4. Plans kept per prepared statement: since D4 every execution resolves
   names and chooses paths, and point selects fell from 26,700 to about
   24,000 tps.
5. Whole-server crash tests through the wire protocol.
6. COPY; then the cost questions (section 0), with EXPLAIN ANALYZE's
   counts as the evidence.
7. Overflow pages for large rows; reclaiming a dropped table's pages.
8. Authentication (SCRAM) and TLS, so the server can leave loopback.
9. The checkpoint pause under a large write load; io_uring if the helper
   pool is the limit (D5).

### 9.5 Indexes and joins (D4)

- **An index is a tree of its own.** Per row, its key is the indexed
  columns then the primary key, and its value is the primary key. Each
  column is a marker (1 a value, 2 NULL, so NULLs sort last as in
  PostgreSQL) and then the column in key order. The index's definition is
  part of its table's catalog entry, and the catalog maps its name (prefixed
  by byte 1) to the table, so CREATE INDEX and DROP INDEX are transactional.
  INSERT, UPDATE and DELETE keep every index in step in the same
  transaction. A unique index is checked by scanning its value's prefix:
  the scan reads the leaf, so two transactions adding the same value fail
  one with 40001. NULLs never clash.
- **Numeric keys** encode the canonical decimal: 0x80 for zero; 0x81, the
  exponent of the leading digit and the digits for a positive value; 0x7F
  and all of that complemented for a negative one. 1.5 and 1.50 give the
  same key, so numeric primary keys and GROUP BY on numerics work.
- **The rules choose a path per table**: the primary key or an index, by
  the whole primary key equal, then a unique index fully equal, then the
  most leading equalities and a range on the next column; the primary key
  wins a tie. Range ends are inclusive, because a bound coerced to the
  column's type may be rounded. Every row is checked against the
  conditions.
- **Joins run in the order written.** A table whose path takes its values
  from the tables before it is looked up per row (a nested loop through a
  key or an index). Otherwise it is read once into memory and matched by a
  hash of the equalities that link it (none: a cross product). Each WHERE
  conjunct is checked at the first table where its columns are known. For
  a LEFT JOIN, the WHERE conjunct is checked after the NULL row is made, and
  only ON decides the match. Rows are read in batches of 256, because a
  scan holds the transaction and the lookups need it in between.
- **EXPLAIN** prints a line per table: its path and how it joins. **EXPLAIN
  ANALYZE** runs a SELECT and adds, per table, the lookups or probes made,
  the rows tried and joined, a hash table's rows and LEFT JOIN null rows,
  then the result's rows and time. On 1,000 customers and 10,000 orders,
  one customer's orders: the hash join reads all 10,000 orders to find 4
  (3.4 ms); with an index on `orders(cust)`, 1 lookup and 4 rows (0.04 ms).
  Writing the FROM list in a good order is the user's job until costs come
  (section 0).
- **Composite indexes** are used by their leading equalities and a range on
  the next column, and for ORDER BY and MIN/MAX on the columns after the
  equalities.
- **Filtered indexes** (`CREATE [UNIQUE] INDEX ... WHERE predicate`) hold
  only the rows whose predicate is true; a filtered unique index makes its
  columns unique among those rows ("one open task per owner"). The
  predicate is kept in the catalog as SQL text (`lexdb_sql.exprText`, parsed
  again when the table is read). The planner uses one only when the
  query's conditions on that table imply the predicate: the same
  conjunct, a comparison of a column for its `IS NOT NULL`, or comparisons
  with constants or parameters (`x >= 3` implies `x > 0`; plans are made
  per execution, so a parameter's value counts). A usable filtered index
  scores one more than an unfiltered one, so `WHERE status = 'open'` alone
  scans just the open rows. EXPLAIN marks it `(filtered)`.
- **RIGHT and FULL joins.** The kept table is read once and its rows marked
  as they join; after the scan its unmatched rows go on, with NULLs for the
  tables before it, through the tables after it. No WHERE conjunct is
  checked below the last RIGHT or FULL JOIN, and the table's own ON
  conditions decide matches without filtering it.
- **Indexes give order.** The store scans backward too. When the first
  table's path yields the ORDER BY order (its key after its equalities,
  an index's key ending with the primary key), in one direction, there is
  no sort and a LIMIT stops the scan; DESC reads backward, NULLs first as in
  PostgreSQL. A full scan switches to an index for its order only with a
  LIMIT or for MIN/MAX (else a sort costs less than a lookup per row).
  MIN or MAX of one column is the first non-NULL value in that order.
  EXPLAIN says `order: sort` or `order: the scan's`.
- **Not yet:** a hash join's table must fit in memory; CREATE INDEX on a
  large table buffers every entry in its transaction; no expression
  indexes; mixed ASC/DESC orders and MIN with MAX in one query are sorted
  or aggregated the plain way.

### 9.6 Grouping and aggregates

- **Running totals.** Each aggregate call of a query (shared when two are
  the same text) is an accumulator per group, and the expressions use its
  slot (`#agg`). A grouped query holds, per group, its first row and its
  accumulators, not its rows.
- **Functions:** count, sum, avg, min, max, string_agg, bool_and, bool_or,
  every, variance, var_samp, var_pop, stddev, stddev_samp, stddev_pop;
  `agg(DISTINCT x)` and `agg(...) FILTER (WHERE ...)` on any of them (kept
  in the call's name, "count distinct filter", the filter as the last
  argument). avg and the variances divide at 16 places as PostgreSQL does
  for integers; for numeric columns PostgreSQL keeps more places in the
  variances. stddev is a square root by Newton's method.
- **GROUP BY** takes expressions, output positions and output names (an
  input column first), and **HAVING**. A grouped query may use a column only
  inside an aggregate, inside a GROUP BY expression, or from a table whose
  whole primary key is grouped (42803 otherwise, as in PostgreSQL); nested
  aggregates and aggregates in WHERE or GROUP BY are 42803 too.
- **SELECT DISTINCT** drops repeated output rows as they come, so a LIMIT
  still stops the scan; its ORDER BY may use only its outputs (42P10).
- **Not yet:** ORDER BY inside an aggregate (string_agg's order is the
  scan's), GROUPING SETS and ROLLUP, DISTINCT ON, grouping in an index's
  order without a hash table.
- **Tests:** `exec_agg`, checked by hand. `exec_index_diff` compares grouped
  aggregates on the indexed and plain tables, DISTINCT with GROUP BY,
  FILTER with WHERE, and HAVING with the groups filtered in the test;
  ignoring DISTINCT (36 differ), FILTER (64) or HAVING (29) fails it.

### 9.7 Operators and functions

- `[NOT] LIKE` and `ILIKE` (ASCII case folding) with `ESCAPE`, matching by
  character; `[NOT] IN (list)` with SQL's NULLs (no match and a NULL in
  the list is NULL); `[NOT] BETWEEN`, parsed as two comparisons;
  `IS [NOT] DISTINCT FROM`; `CASE`, both forms, evaluating only the branch
  taken; nullif, greatest, least, concat, substr/substring, strpos, trim,
  ltrim, rtrim, replace, left, right.
- The planner reads an IN list on a key column as a lookup (or range) per
  value, in key order, so ORDER BY and MIN/MAX still come from the scan;
  `LIKE 'abc%'` on a text column as the range from 'abc' to 'abd'. A
  bound too long for a varchar column matches nothing rather than failing.
- `IN (SELECT ...)` says it is not supported yet (0A000).
- Tests: `exec_ops`, checked by hand; `exec_index_diff` uses the new
  operators in its random conditions and compares IN with a chain of ORs,
  NOT IN with NOT of it, LIKE with substr and CASE buckets with FILTER
  counts. Unsorted IN keys (6 differ), a LIKE bound past its prefix (5) and
  an IN path taken for a full scan (11, a bug the test found) fail it.

