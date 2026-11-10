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
  prepared statement and shown by `EXPLAIN`. With joins, indexes and
  subqueries built, the user decided (2026-11-09): leave costs for now.

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
server). Tests: `python3 lexell/tests/lexdb.py` (59 programs in
`tests/lexdb/run`, under `LXL_CHECK=1`).

    lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -o lexdb
    ./lexdb /path/to/data 127.0.0.1:5433
    psql "host=127.0.0.1 port=5433 user=me dbname=lexdb"

### 9.1 What differs from the design

- **Nodes are decoded into records** (`lexdb_page.Node`: arrays of keys,
  values and children) rather than worked on as slotted pages. Simpler;
  the cost is a decode per load and an encode per checkpoint. Measure before
  changing it.
- **Large rows go to a companion tree, not to overflow pages** (9.29): a
  key is at most 512 bytes, a row at most 64 MiB (error 54000).
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
  underfull one stays. A dropped table's pages are freed by the
  checkpoints after the drop, a few hundred internal pages read by each
  (9.32).
- **Statements outside a block are retried** up to 10 times on 40001 (the
  client has seen nothing of the failed try). In a read-write block each
  statement waits, after it runs, until what it read is durable, since its
  result goes out before COMMIT (4.4).
- **Interpreted, not bytecode.** The executor walks the statement's tree.
- **No bytea, dates or times yet.** Schemas are built (9.20).
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
database: 26 MB idle, 63 MB after a full scan (now 2.7 MB and 45 MB: 9.13). Memory is the cache, which
grows as pages are read and is not given back; a query's own memory is
small (rows stream in batches; groups keep running totals).

One client is close to the drive's flush (about 1 ms, section 3); more
clients share flushes (group commit). No run had a failed transaction.
These are first numbers, not a comparison: PostgreSQL on the same machine
is the comparison to make.

### 9.4 Next

1. io_uring: measured (9.17), the decision is the user's (a runtime
   change). For file reads only it saves at most 17 us of system calls per
   cache miss on the SQL thread; for the whole event loop, sockets too.
2. Conflicts per row, not per leaf (built: 9.19).
3. Smaller items, in the order the user set (after schemas):
   - built: an uncorrelated `IN (subquery)` as lookups (9.21);
   - built: `WITH` before INSERT, UPDATE and DELETE, and `INSERT ...
     SELECT` (9.22); not done: data-modifying CTEs (`WITH d AS (DELETE
     ... RETURNING ...)`), which wait for `RETURNING`, and `UPDATE ...
     FROM`, the way to join a CTE into an UPDATE (now only through
     subqueries);
   - built: a correlated subquery's value as a lookup's key (9.23);
   - built: correlated subqueries in GROUP BY and in aggregates'
     arguments (9.24); not done: an aggregate inside a correlated
     subquery's reference to its parent (`HAVING (SELECT ... WHERE c.id =
     min(o.cust))`), which PostgreSQL evaluates in the parent;
   - built: ORDER BY inside an aggregate (`string_agg(x, ',' ORDER BY
     x)`, 9.25); not done: `array_agg` and `json_agg`, whose results
     depend on it too;
   - built: hashing a correlated scalar subquery with an aggregate (a
     count per customer) as a grouped run (9.26); not done: the same
     with GROUP BY, HAVING or DISTINCT in the subquery, and choosing
     between the hash and per-row lookups by row counts (now: lookups
     whenever an index path uses the reference).

   Waiting for row counts (costs, which the user has left for now: section
   0): choosing hash or index per row (9.9), and when an IN subquery's
   values are too many for lookups (now a fixed 1,000: 9.21).
   Functions in FROM and arrays (built: 9.27), `op ANY/ALL (array)`
   (built: 9.28). Not done:
   - `ANY`/`ALL` with a subquery other than `= ANY` and `<> ALL` (`x < ANY
     (SELECT ...)`: 0A000);
   - an index range from `col < ANY(array)` (only `= ANY` is a lookup);
   - subscripts (`a[1]`), `array_length`, `cardinality`, `array_agg`,
     `@>`, and array comparisons other than equality (now: by text);
   - functions in the select list (`SELECT generate_series(1, 3)`);
   - a function's rows are all made before they are read: a LIMIT does
     not stop generate_series early (max_statement_mem bounds it);
   - arrays of more than one dimension; binary numeric array parameters;
   - other set-returning functions (`regexp_split_to_table`, the JSON
     ones), and generate_series over dates (no date types yet).
4. Schemas (built: 9.20). Not done:
   - privileges (`GRANT`, `AUTHORIZATION`), which wait for logins (item 9);
   - `$user` in the search path as the login's name (now it is a schema
     name looked for like any other);
   - `current_schema()` and `current_schemas()`;
   - the `pg_catalog` and `information_schema` views, which clients and
     tools use to list schemas and tables (decided later: section 0);
   - `SHOW` of PostgreSQL's own settings (`server_version` and the rest).
5. Plans kept per prepared statement (built: 9.17).
6. Whole-server crash tests through the wire protocol (built: 9.18).
7. COPY; then the cost questions (section 0), with EXPLAIN ANALYZE's
   counts as the evidence.
8. Large rows (built: 9.29). Not done:
   - a large row whose columns before its long texts are more than its
     leaf holds (about 1.3 KB less the key) is read whole by any query; so
     is one whose large part is not a text (many medium texts, a large
     numeric);
   - compression;
   - space: a page holds three chunks; values loaded in random order fill
     84% of the pages with data, in key order 90% (9.30).
9. Authentication (SCRAM) and TLS, so the server can leave loopback.
10. The checkpoint pause under a large write load; io_uring if the helper
   pool is the limit (D5).
11. Batches, not rows (the user's backlog, 2026-11-09). The executor works
   a row at a time: a scan's callback gets one entry, `decRow` turns it
   into a `[]Val` (a tagged value per column), and each expression,
   condition and aggregate (`accumulate`) is evaluated for that row. The
   per-row cost is the dispatch and the tagged values, not the arithmetic.
   The question: process a leaf's rows as a batch, with each needed column
   decoded into a plain array (ints as `[]int`, a NULL bitmap), and run
   conditions and aggregates over the arrays. Measure first: the share of a
   scan's time now in decoding, dispatch and the B+tree walk.
    A prototype is built for aggregates over one table (9.47): 4 to 5 times
    faster.
12. Fast aggregation with SIMD (the user's backlog, 2026-11-09), on top of
   item 11: `sum`, `count`, `min`, `max` and filters over a column array
   with AVX2 (Lexell already requires x86-64-v3). Lexell has no vector
   types or intrinsics; SIMD is reached only through C runtime functions
   (as `hash.crc32c` is). Either needs a language or runtime change: the
   user's decision. Without SIMD, batches alone may give most of the gain
   (tight loops over arrays); measure that before deciding.
13. ALTER (the user's request, 2026-11-09), in steps: (1) the actions that
   rewrite no row: ADD COLUMN, RENAME COLUMN, RENAME TO, SET and DROP NOT
   NULL (built: 9.34); (2) DROP COLUMN (built: 9.35); (3) ALTER COLUMN
   TYPE (built: 9.36); (4) (built: 9.37) SET
   SCHEMA, ALTER INDEX ... RENAME, ALTER SCHEMA ... RENAME. Column
   defaults, ADD COLUMN ... DEFAULT among them, are built (9.38).
14. Constraints (the user's request, 2026-11-09), in steps: (1) UNIQUE
   (built: 9.39); (2) CHECK (built: 9.40); (3) FOREIGN KEY, with NO ACTION and RESTRICT
   (built: 9.41); (4) the CASCADE, SET NULL and SET DEFAULT actions
   (built: 9.42).
15. SERIAL and COPY (the user's request, 2026-11-09), in steps: (1)
   sequences, SERIAL and identity columns (built: 9.43); (2) RETURNING, for
   clients to read the ids back (built: 9.44); (3) COPY (built: 9.45).
16. Window functions (the user's request, 2026-11-09; built: 9.46).

A review against PostgreSQL 16 (2026-11-10), with the gaps in tiers and a
proposed order of work, is in [lexdb-gaps.md](lexdb-gaps.md).

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

### 9.8 Subqueries

- Scalar `(SELECT ...)`, `EXISTS (SELECT ...)` and `x IN (SELECT ...)`,
  with `NOT`, anywhere an expression goes: WHERE, ON, the select list,
  ORDER BY, HAVING, UPDATE's SET and WHERE, DELETE's WHERE, INSERT's
  VALUES. A scalar subquery with more than one row is error 21000; one
  with no rows is NULL. IN follows SQL's NULLs: no match and a NULL in the
  subquery's values is NULL, so `NOT IN` over a NULL keeps no row.
- The parser gives a statement its subqueries, numbered; an expression
  names one (`#sub`, `#exists`, `#in`). Each is planned inside the query
  it is in. A name not among a query's own tables is looked up in the
  queries around it, nearest first, and becomes a parameter numbered after
  the statement's own; the query it is in supplies its value, and a query
  in between passes it down (correlation two levels out works).
- A subquery with no outer names runs once per execution, before the
  query: its value is then a constant to the planner, so
  `id = (SELECT max(id) ...)` is a primary key lookup. IN's values become
  a hash set, probed per row. A correlated subquery runs for each row that
  needs it, with the outer values as parameters, so an index on its
  correlating column is used; its results are kept per outer value (up to
  10,000), and EXISTS stops at its first row. Its conjuncts are checked
  after the others; in the select list or ORDER BY it is evaluated after
  the scan, from the rows kept.
- Hash tables and subquery results moved from the plan to the run, so a
  plan does not change while it runs and a subquery's plan can run inside
  its parent's.
- Numeric keys drop trailing zeros, so a whole number has one key whether
  it came as an integer or a numeric (the IN set needs it).
- EXPLAIN shows each subquery, run once or per row and on which outer
  columns, with its plan; EXPLAIN ANALYZE adds its runs, how many came
  from the cache, and its tables' counts summed over the runs.
- Not yet: `ANY`/`ALL`, correlated subqueries in GROUP BY or in an
  aggregate's arguments (0A000).
- Tests: `exec_sub` (62 statements then, checked by hand); `exec_index_diff`
  compares IN with a correlated EXISTS and with the list of its values,
  NOT EXISTS with a LEFT JOIN's unmatched rows, a correlated count with a
  grouped LEFT JOIN and a scalar with its value, and UPDATE uses
  subqueries, with no differences over four seeds. Mutations: a cache
  that ignores the outer values (63 differ, 20 lines of `exec_sub`),
  NOT IN ignoring a NULL (5, 2), no trailing-zero rule (2 lines), a
  correlated subquery taken as a lookup's key (2 lines), an ambiguous name
  in a subquery taken from outside (2 lines, after adding that case).
- pgbench point selects before and after, alternating, four runs each:
  24,681 and 24,016 tps on average, within the runs' spread (22,800 to
  26,500). The binary is 1.08 MB.

### 9.9 Hashed subqueries (semi-joins and anti-joins)

- A correlated `EXISTS` or `IN` (and `NOT EXISTS`, `NOT IN`) is hashed
  when its outer values appear only in WHERE equalities `inner = outer`
  (outer: an expression of outer values only, `k.g + 1` too) and none of
  them is a lookup's key or a hash join's value: the equalities are taken
  out, the subquery outputs their inner sides (then IN's value), runs once
  per execution, and its rows go into a hash by key. Each outer row
  probes it once, with the same answers as running it: EXISTS is whether
  the key has rows; IN is true if the key has the value, NULL if x is
  NULL or the key has a NULL value, else false; a NULL key has no rows.
  It is a semi-join for EXISTS and IN, an anti-join for their NOTs, NULL-
  aware for NOT IN, and works wherever the subquery is (WHERE, the select
  list, ...).
- It stays per row when an equality is the subquery's lookup key (an
  index on the correlating column), when an outer value is used another
  way (`h.v > k.x`), or when the equality is in an outer join's ON.
- EXPLAIN: `subquery 1 (exists): hashed on o.cust = c.id`; ANALYZE adds
  `(runs 1, probes N)`.
- Measured (10,000 customers, 10,000 orders, NOT EXISTS on the customer,
  no index): 10,953 ms per row, 12 ms hashed, with the same count. With an
  index it stays per row, 21 to 23 ms; hashing would take 12 ms there,
  but for a few outer rows the lookups win: that choice needs row counts.
- Tests: `exec_sub` adds hashed EXISTS, NOT EXISTS, IN and NOT IN with
  NULLs on both sides, two keys, an expression key, the key on a
  hash-joined table, nesting, and the cases that stay per row (82
  statements now); `exec_index_diff` compares b (per row through its index
  on x) with b0 (hashed) for EXISTS, NOT EXISTS, IN, and IN and NOT IN as
  values, keyed on `x` and on `x + 1`, with no differences over four
  seeds. Mutations caught: NOT IN ignoring a NULL value (11 differ, 2
  lines of `exec_sub`), IN's set without the key (23, 3), ON conjuncts
  taken as keys (1 line), a key conjunct left in a hash join's filters
  (1 line, after adding that case). Skipping NULL keys on the build side
  and on the probe side are each enough alone: removing one changes
  nothing.

### 9.10 Subqueries in FROM and CTEs

- `FROM (SELECT ...) [AS] t [(a, b)]` (the alias may be left out, as in
  PostgreSQL 16: `unnamed_subquery`), and `WITH x [(a, b)] AS (SELECT ...),
  ... SELECT ...`, at the top or in any subquery, `[NOT] MATERIALIZED`
  accepted. A CTE sees the ones before it in its WITH and those around it;
  an inner one, or one of a name, hides the outer one or a table of that
  name.
- The parser keeps a CTE as its tokens and parses them again, as a
  subquery in FROM, wherever the CTE is used; scope comes from that. So a
  CTE used twice is planned and run twice: the same rows, more work
  (running it once is in 9.4).
- A subquery in FROM is planned before the query's tables, seeing the
  queries around the query but not its tables (`LATERAL`: 9.12). It runs once per execution,
  before the query, into rows held by the run; its level reads them, with
  no key: at the first level a scan of them, after it a hash join on its
  equalities (or a loop). Its hash keys are by value (`2 = 2.0`), as its
  values keep their own types. ORDER BY and MIN/MAX are not taken from its
  order, and grouping by its columns implies nothing of the others.
- EXPLAIN: `join s: hash on (cust) over rows of subquery 1`, then
  `subquery 1 (from): run once` and its plan.
- Not yet: `WITH RECURSIVE`, `LATERAL`, WITH before INSERT, UPDATE or
  DELETE (0A000; their subqueries may use subqueries in FROM and WITH),
  column aliases for a table (`FROM t x(a)`).
- Tests: `exec_with` (46 statements, checked by hand); `exec_index_diff`
  compares a subquery in FROM with its query, a grouped CTE joined with a
  correlated count, and subqueries in FROM on both sides of a LEFT JOIN
  with the tables themselves: no differences over four seeds. Mutations:
  its hash keys coerced like a table's (23 differ, 4 lines of
  `exec_with`), ORDER BY taken from its scan (21, 2), a CTE seeing itself
  and later ones (1 line), the outermost CTE of a name winning (1 line),
  column aliases ignored (2 lines).
- pgbench point selects, the last commit and this one, two rounds each:
  26,666 / 26,173 and 23,823 / 24,054 tps. The binary is 1.13 MB.

### 9.11 UNION, INTERSECT, EXCEPT and WITH RECURSIVE

- `UNION`, `INTERSECT` and `EXCEPT`, with `ALL` or `DISTINCT`, INTERSECT
  binding first, a query in parentheses with its own ORDER BY and LIMIT;
  ORDER BY (an output column's name or number), LIMIT and OFFSET of the
  whole. Each query is planned on its own (its outer values too); the
  first gives the names. Rows are equal with NULLs alike and numbers by
  value (`SELECT 2 UNION SELECT 2.0` is one row). A different number of
  columns is 42601.
- A CTE used more than once runs once per statement: its rows are kept,
  by its number, in rows the statement's runs share (a run hands them to
  the runs inside it and takes them back); its other uses copy them.
  EXPLAIN ANALYZE shows a use served so: `runs 0, from cache 1`.
- `WITH RECURSIVE x AS (first UNION [ALL] then)`: the first query's rows,
  then rounds of the second over the working table (the rows the last
  round added) until a round adds none. With UNION (not ALL) a row seen
  before is not added, so a cycle ends. The working table is in the
  shared rows; in its own body the CTE names it, only directly in the
  second query (in a subquery, in the first query, or a body not of that
  form: 42P19, as in PostgreSQL). A WITH RECURSIVE CTE that does not
  name itself is an ordinary one.
- **max_recursion.** PostgreSQL has no limit; lexdb has one, as SQL
  Server's MAXRECURSION: at most 1,000 rounds that add rows, then error
  54001. `SET max_recursion = n` (or `TO n`) per session, 0 for no limit,
  `RESET max_recursion` (or `= DEFAULT`) for 1,000. It bounds rounds, not
  rows: a query whose rows multiply each round can still use much memory
  within the limit (a limit on a statement's rows and a timeout are in
  9.4). Other SETs are still accepted and ignored.
- EXPLAIN: `recursive union all`, `first` and `then, per round, over the
  working table` with their plans; ANALYZE adds runs (rounds).
- Tests: `exec_with` (89 statements now, checked by hand): the set
  operations with NULLs and duplicates, precedence, ORDER BY rules; a
  CTE used twice; series, a hierarchy both ways, a cycle with UNION and
  with UNION ALL (the limit), max_recursion set, 0, reset, and at its
  edge; the 42P19 errors. `exec_index_diff` compares UNION with DISTINCT
  over UNION ALL and UNION ALL with the counts added, INTERSECT with AND,
  EXCEPT with AND NOT (a NULL condition: not in the second), and a
  recursive walk (x, x + 1, ...; the working table first or second in the
  join) with the walk done by the test: no differences over four seeds.
  Mutations caught: INTERSECT keeping duplicates, EXCEPT ALL taking all,
  UNION not removing duplicates across its sides, recursion without
  UNION's repeats removed, the limit one round early, the CTE store
  ignoring which CTE; the working table holding all rows so far makes
  `exec_with` run without end (rows multiply), so it fails by time.
- pgbench point selects, the last commit and this one: 25,523 / 25,516
  and 23,467 / 26,871 tps. The binary is 1.19 MB.

### 9.12 LATERAL

- `FROM t, LATERAL (SELECT ... t.x ...) l`, `JOIN LATERAL (...) l ON ...`,
  `LEFT JOIN LATERAL (...) l ON true`: the subquery sees the FROM items
  before it. A query's scope is made before its FROM items and gets each
  table's columns as it is read; a subquery in FROM that is not LATERAL
  plans with them hidden, so it sees the queries around (its use of them
  now works) but not its neighbours (42P01 for those, as in PostgreSQL).
- A subquery in FROM with outer values is a level run per row: its
  values from the row, the subquery run with them (cached per values, as
  correlated subqueries are), its rows joined. On the right of a RIGHT or
  FULL JOIN it is 42P10.
- EXPLAIN: `cross join t: rows of subquery 1, run per row`, then
  `subquery 1 (from): per row, on c.id` with runs and cache hits.
- Tests: `exec_with` (102 statements): top-N per row, LEFT JOIN LATERAL ON
  true, aggregates, UNION inside, nested subqueries, outer columns in a
  FROM subquery of a correlated subquery, the errors. `exec_index_diff`
  compares a LATERAL count with a scalar count and LEFT JOIN LATERAL's
  first row with min(): no differences over four seeds. Mutations caught:
  its cache ignoring the values (31 differ), cached rows not put back
  (38), neighbours visible without LATERAL (2 lines), the level hashed
  instead of per row (41).
- pgbench point selects over six pairs, last commit and this one: 24,339
  and 23,980 tps on average, each pair varying by up to 3,000: noise.

### 9.13 The cache in bytes

- **The budget.** `Options.cacheBytes` (128 MB by default; the server takes
  `LEXDB_CACHE_MB`) replaces a count of nodes. Each loaded node counts an
  estimate of its memory, `lexdb_page.nodeCost`, kept per slot and summed;
  clean nodes are evicted while the sum is over the budget. The estimate
  was fitted to measurements: a node read from disk, its entries' bytes and
  64 bytes a key; a node changed since, its entries' bytes and 144 bytes a
  key; 200 bytes for each child's slot. A test checked the running sum
  against a full recount at every eviction pass over the whole suite.
- **A smaller node.** A node read from disk keeps its keys and values as
  slices of one string, the page's entries, not two allocations an entry.
  A checkpoint does the same for each node it writes (repack), and its
  write list holds those same strings, making each 4 KiB page only as it is
  written. A slice keeps its whole string alive, so a key that moves up
  into a parent on a split is copied. What get and scans hand out is not
  copied (9.14 measured the copies at 14% of a scan). The executor keeps
  nothing beyond a statement, so a page stays alive at most until the
  statement that read it ends.
- **Writes.** A changed node leaves memory only once a checkpoint has
  written it. When the cache is over budget, the writer starts a checkpoint
  after an eighth of `ckptBytes` of log, not all of it. While a checkpoint
  runs and the cache is over twice its budget, a commit that writes waits
  for it to end (the stop line counts these: "commits held").
- **Shutdown** waits for a running checkpoint and then takes its own. It
  used to return at once when the checkpointer was busy, so the next start
  replayed up to `ckptBytes` of log: that was the 26 MB idle after restart.
- **Two bugs found on the way, both older than this change.**
  - Evicting an internal node freed its children's pages, though the
    parent's page still named them. A later checkpoint reused them:
    "page 2398: type 5" after a bulk load with a small cache. The tests
    missed it because their trees had two levels, whose root is never
    evicted.
  - Evicting a parent drops its children's slots, and a transaction's reads
    were validated by slot generation. So a scan bigger than the cache always
    conflicted. A read of a clean leaf now also notes its page and the
    commit it saw. If the slot is gone, the read still holds unless the page
    has been freed since (`freedAt`, 8 bytes per page). Pages are written
    once and never in place.
- **Measured** (300,000 rows of about 80 bytes, 34 MB of pages):

| budget | bulk load, peak RSS | full scan after restart, peak RSS |
|---|---|---|
| before (100,000 nodes) | 112 MB | 63 MB (26 MB idle) |
| 16 MB | 49 MB (3 commits held) | 19 MB |
| 64 MB | 105 MB | 45 MB (all of it cached) |
| 128 MB | 111 MB | 45 MB |

  A restart idles at 2.7 MB. Reads stay within a few MB of the budget.
  Writes reach about three times it at 16 MB: the counted cache goes up to
  twice the budget before commits wait, and the allocator keeps freed
  memory. With a large budget the peak is a bulk load's changed nodes and
  their repacking at the shutdown checkpoint. pgbench point selects, HEAD
  and this over four pairs: 23,866 and 23,318 tps on average, each pair
  varying by over 2,000 tps: noise.
- **Tests.** `store_evict` is new. It uses a tree of three levels (100-byte
  keys) and a 64 KB cache. Over 30 rounds of changes and checkpoints, the
  tree must equal a model, and again after a reopen. Whole scans commit,
  20 of 20. A read whose leaf's slot was dropped conflicts when another
  commit changed that leaf (20 of 20) and commits when it changed another
  (20 of 20). Bugs put back to check the test catches them:
  - children's pages freed on eviction: the test hangs, as the tree breaks;
  - dropped slots always conflicting: a scan's commit fails;
  - the page not checked: conflicted 0;
  - freeing on change not recorded: conflicted 0.

  The store tests that sized their caches in nodes use 2 KB a node now.

### 9.14 A statement's limits

Per session, as PostgreSQL's SET, kept until changed:

- `statement_timeout`: in ms, or with a unit (`'5s'`, `'2 min'`); 0, the
  default, for none. Error 57014 when exceeded. It counts from the
  statement's start, across its retries after a conflict. Every 256th
  row a query looks at (any level of a join, in any query inside it)
  checks the clock, and so does every round of a recursive CTE. lexdb is
  one thread, so a long statement holds up every other session; this
  bounds how long.
- `max_statement_mem`: in kB, or with a unit (`'64MB'`); 0 for none, 256 MB
  by default. Error 53200 when exceeded. It counts an estimate of the rows
  a statement keeps until it ends:
  - its result and sort;
  - its groups;
  - a hash join's built side;
  - subqueries' results and their per-row cache;
  - a CTE's shared rows;
  - a set operation's sides;
  - a recursion's rows;
  - the rows an UPDATE or DELETE changes.

  A query inside another checks against its parent's count plus its own,
  and the parent counts only what it keeps. So a subquery run per row does
  not add up, while one kept does. Rows that stream (a count, a filter, a
  few groups) count nothing.
- `max_recursion` (9.11) is the third. `RESET name`, `RESET ALL` and
  `SET name = DEFAULT` restore the defaults. A SET in a transaction block
  that rolls back is undone, as in PostgreSQL. Bad values are 22023. Other
  SETs are accepted and ignored.
- **Not counted:** a transaction's writes across statements (an explicit
  block of many INSERTs), and the pages kept alive by rows that slice them
  (9.13). The latter is about 1.3 times the count for whole rows; it can
  be more for a small piece of each of many rows, until the statement
  ends. A sort cannot be interrupted by the clock: a statement over its
  time ends after its sort.
- **Tests.** `exec_limits` (78 statements) covers:
  - timeouts of a cross join, an endless recursion, a per-row UPDATE, and
    one in a transaction block (which then fails, 25P02);
  - each kind of row the memory limit counts, with cases sized so the part
    alone fits and what is kept from it does not;
  - streaming queries and per-row subqueries not stopped;
  - SET forms, units, bad values, RESET, RESET ALL, rollback and commit
    of SETs.

  Each count removed, the clock check removed, the limits not handed to
  inner queries, inner queries' temporary rows added to the parent, or
  rollback keeping SETs: each changes the output. One mutant changes no
  output: the check inside the row callbacks removed. The count after the
  scan still stops the statement, only after the rows are gathered.
- **Measured:** pgbench point selects, HEAD and this over four pairs:
  23,826 and 23,501 tps (noise). Three scans and a join of 300,000 rows,
  warm: 0.56 s, the same as before 9.13. 9.13 had made it 0.64 s by
  copying what scans hand out, and this change stops copying it.

### 9.15 Taking turns, and SELECT on a snapshot

- **Turns.** lexdb runs SQL on one thread; sessions interleave when one
  waits (sockets through epoll, the disk through the helper pool). A
  statement whose pages are all in the cache never waits, so it used to
  run to its end while every other session waited. Now the per-row clock
  check (9.14) yields after 0.1 ms of a statement (`TURN_NS`).
- **The runtime.** `task.yield` looked at sockets only every 64th switch,
  so a lone long query let a waiting client in only every 64 turns. It now
  looks every time (commit 608223a8, the user's decision: both runtimes,
  regenerated, reseeded; run.py, run_native.py and httpsrvgen.py pass).
- **SELECT outside a block runs on a snapshot.** A query that yields lets
  other sessions commit meanwhile. Run optimistically, a long scan beside
  writers to its table conflicted on every retry and failed. On a
  snapshot it sees one state and never conflicts. It is serializable:
  read-write transactions are validated in commit order, and a snapshot
  sees a prefix of that order. A snapshot whose old versions passed their
  budget (72000) is retried on a new one. Inside a transaction block
  nothing changed: reads are validated at COMMIT, and a long read there
  can fail with 40001, as in serializable PostgreSQL (`BEGIN READ ONLY`
  for long reads).
- **Measured** (point selects, 4 clients, a 300,000-row cached aggregate
  running all the time on another connection):

| | point-select p50 | p99 | max | point tps | aggregates in 6 s |
|---|---|---|---|---|---|
| before | 109 ms | 122 ms | 224 ms | 44 | 54 |
| turns of 1 ms | 1.34 ms | 3.5 ms | 6.8 ms | 2,668 | 49 |
| turns of 0.25 ms | 0.72 ms | 2.9 ms | 4.3 ms | 4,300 | 47 |
| turns of 0.1 ms | 0.54 ms | 2.7 ms | 4.1 ms | 5,234 | 46 |

  Alone, the aggregate takes 98 ms with turns (no cost seen). Beside 4
  writers updating random rows of its table, it failed every time before
  the snapshot change. After it, it takes 151 ms, while the writers do
  1,572 tps (316 before, held off by the scan). Retrying on a snapshot
  only after a conflict took 299 ms. 16 writers and 8 point readers
  together are the same either way (readers 3,460 tps, writers 3,390).
  Further tuning was stopped at the user's request.
- **Tests.** `exec_turns` runs sessions as tasks on one store:
  - a short session started after a long query ends first;
  - a long sum outside a block, while another session commits transfers
    that keep the sum, gives the sum; every transfer commits;
  - the same query inside a block fails at COMMIT with 40001.

  Never yielding, no turn started, and optimistic SELECTs each change the
  output.

### 9.16 Readers never wait for writers, writers never wait for readers

The user's rule. There are no locks, so the only waits were for
durability. A read showed only what the log held, and when it saw a
commit not yet flushed it waited for the flush: a snapshot as it began,
a read-only commit, and every statement in a transaction block
(`syncReads`). Under write load that is a wait on the writers' flushes.
Beside 16 writers, point selects took 2.2 ms instead of 0.27 ms, and
6 to 14 ms when the drive was slow.

- **Snapshots read as of the last durable commit** (`durableSeq`, moved by
  the writer after each flush). What they show is durable, so they wait
  for nothing; a commit shows once its flush is done, as in PostgreSQL. A
  session's own autocommit write returns only after its flush, so the
  session sees it next.
- **What that needs.** Each change to a node's contents keeps its previous
  version until the change is durable and no snapshot needs it.
  `willChange` is called where contents change, no longer for every node
  marked dirty: a parent on the path is not copied. Freed slots are kept
  likewise (`deferred`), and root changes go into `rootHist`: a snapshot
  starts from the roots as of its commit, through root splits, new and
  dropped trees. `prune` runs after each flush. Replay does not advance
  `seq`, so recovery copies nothing.
- **Transaction blocks read a snapshot too** (`beginBlock`), taken at
  BEGIN, with their own writes over it (forward, backward and point
  reads). Reads are noted. A read of a leaf changed after the snapshot is
  stale at once, as in serializable PostgreSQL. A block that only read
  commits without a check and never fails. A block that wrote checks at
  COMMIT that everything it read is still current, or fails with 40001.
  Its UPDATE, DELETE and INSERT read the live tree (`Txn.live`), since
  what they read is checked at COMMIT the same way and the latest is less
  often stale. With every read checked against the state at COMMIT, the
  block is serializable at its commit.
- **Writers never wait for readers.** Snapshots cost writers only the copy
  of a changed node's old version. A snapshot whose old versions pass
  `snapNodes` is cancelled (72000) and, outside a block, retried.
- **Measured** (16 writers, 8 point readers on a 10,000-row table, 6 s):

| | readers | reader latency | writers | writers failed |
|---|---|---|---|---|
| autocommit writers, before | 3,600 tps | 2.2 ms | 3,480 tps | 0 |
| autocommit writers, after | 12,400 tps | 0.65 ms | 4,430 tps | 0 |
| writers in blocks, before | 3,950 tps | 2.0 ms | 2,300 tps | 3.8% |
| blocks reading the snapshot for DML too | 10,800 tps | 0.74 ms | 2,880 tps | 6.3% |
| blocks, DML reading the live tree (kept) | 11,000 tps | 0.72 ms | 3,000 tps | 1.6% |

  The failures are per-leaf conflicts (9.4). Point selects alone are
  unchanged over five pairs (23,602 and 23,340 tps).
- **Tests.** `store_durable` holds the log's flushes open:
  - a commit is then applied but not durable: it updates a value, splits
    the root, empties and drops a tree and creates one;
  - a snapshot begun meanwhile does not wait and sees the state before,
    exactly, and still does after the flush;
  - 40 rounds take two snapshots in each window (the second after the
    first ended and pruned), each seeing the round before, whole;
  - 20 blocks read their snapshot with their own writes, forward, backward
    and point; a commit fails when a key it read changed after its
    snapshot, and not when one far from its reads did.

  `exec_turns` checks that a block that only reads commits with the right
  sum, and that one that then writes fails. Caught, each put back:
  - snapshots at the applied commit;
  - copies only for live snapshots;
  - root changes not noted;
  - freed slots not kept;
  - prune dropping pending versions;
  - the durable point never moving;
  - a parent not copied on a split;
  - a stale read noted as current;
  - block reads not noted;
  - a commit with writes not checked;
  - the backward fence wrong (by `store_back`).

  Checking own writes before the snapshot in `get` turned out to be only
  a shortcut: the scan merges them anyway.

### 9.17 The read path beyond the cache, and io_uring

The user asked to consider io_uring for reads and writes. It was measured
first against the helper pool, then in lexdb itself. Then they asked
whether uncached plans were the cost.

**The drive, with and without io_uring** (`uring_probe.c`, no liburing;
4 KiB `O_DIRECT` random reads of a 4 GiB file; two runs agreed; the first
run, while the host still wrote the file back, was 2 to 5 times slower and
is left out):

| | IOPS | p50 | p99 | CPU per read |
|---|---:|---:|---:|---:|
| threads, 1 / 8 / 32 | 6,000 / 40,000 / 88,000 | 140 / 173 / 310 us | 330 / 450 / 1,050 us | 16 / 18 / 24 us |
| io_uring, one thread, depth 1 / 8 / 32 / 64 | 5,400 / 40,000 / 85,000 / 98,000 | 160 / 179 / 330 / 554 us | 333 / 472 / 1,060 / 2,040 us | 17 / 9 / 6 / 6 us |
| 4 KiB write + `fdatasync`: pwrite / io_uring linked | 1,080 / 980 a second | 880 / 955 us | 1,450 / 1,700 us | 33 / 78 us |

The drive gives the same reads in flight either way. io_uring costs a
quarter of the CPU per read, and a flush the same time (the device sets
it). The kernel allows io_uring (`io_uring_disabled` 0).

**lexdb, random point selects on 10 million rows (2.9 GB) with a 64 MB
cache**, so nearly every select reads its leaf (pgbench, prepared, 32
clients; CPU per select from `/proc`):

| | selects/s | SQL thread per select | user | system | helpers |
|---|---:|---:|---:|---:|---:|
| before | 8,900 | 110 us | 78 us | 32 us | 87 us |
| after (below) | 14,000 | 68 us | 41 us | 27 us | 80 us |
| the same, all in cache (ids 0 to 99,999) | 41,000 | 23 us | 14 us | 10 us | none |

The SQL thread was saturated, and 98% of its sampled time was user code
(perf, with the symbol map that `LXL_NATIVE_MAP` writes). Planning and
parsing were 1.5%: a prepared point select plans in a few microseconds.
What it was:

- `Wire.fill`, 23%: a new 64 KiB array, zeroed, for every socket read,
  copied byte by byte. Now one buffer per connection, read into directly.
- CRC32C, 17%: a byte at a time. Now `hash.crc32c` in the standard
  library, with the CPU's crc32 instruction (the user's choice), 2%.
- Eviction: the clock scanned every child of each inner node it passed,
  though an inner node on a path in use is nearly always referenced. The
  reference bit is now checked first. Freeing an evicted inner node's
  child slots made and dropped an empty node for each, though they were
  empty already.

**What io_uring would give.** Per cache miss, the SQL thread spends 28 us
of user time and 17 us of system time (the pool: a futex wake, the
eventfd, more turns of the epoll loop). io_uring for file reads would
save at most those 17 us, about a quarter of a miss, and the helpers'
spinning on other cores. Even all in cache, the sockets cost 10 us of
system calls per select, a third of it. An event loop built on io_uring
for sockets too could batch those across sessions. Either is a runtime
change, so it is the user's decision.

**Ascending loads fill their pages.** After those fixes, at 128 MB (the
default cache) a select still read 1.4 pages: the inner nodes did not fit.
Counted: 3,900 of them held 121 of the 128 MB (32.5 KB each, about two
thirds of it the 200 bytes kept per child: 9.4), and still 28% of loads
were inner nodes. And the 10 million rows (1.35 GB of entries) took a
2.9 GB file: every split cut a node in half, so a load in key order left
every page half full for good. A clock count for inner nodes (as
PostgreSQL's usage count) was tried first and changed nothing: the inner
nodes did not fit at all.

Now an insert past every key in the tree (the rightmost leaf, at its end)
splits leaving the left node full: one entry goes right. Up the tree the
same holds while the new child is its parent's last, where the last two
children go right. These are PostgreSQL's rightmost split and SQLite's
quick balance. Other inserts split in half as before.

| 10 million rows loaded in key order | before | after |
|---|---:|---:|
| data file | 2,815 MB | 1,401 MB |
| load (psql, 2,000-row INSERTs) | 135 s | 94 s |
| random point selects, 64 MB cache | 14,000/s, 1.72 reads each | 15,200/s, 1.41 reads each |
| the same, 128 MB cache | 14,600/s, 1.40 reads each | 19,200/s, 1.00 reads each |

`store_fill` loads 40,000 entries of about 100 bytes in three orders and
checks that each reads back whole, forward, backward and by key. Fill:
ascending 98%, descending 51%, random 68% (the textbook 69% for random
inserts). Caught: no end detection, and a leaf split that ignores it
(both 49%). Not caught: the rule applied at the end of any leaf, not only
the rightmost, which changes nothing measurable (random 67%). Nor the
inner-level rule, whose pages are 1% of the total; checked by hand
instead: 961 pages in use against 964 without it.

**A slot not in memory holds no node.** An unloaded child kept a slot of
about 230 bytes (measured: an empty `Node` record 118, `SlotMeta` 85, the
history list 24), and was charged 200, so the cache ran over its budget.
Now the nodes in memory sit in a dense pool (`Db.pool`, `SlotMeta.frame`,
`owner`): a node loaded takes a frame, and one evicted or freed gives it
back, with the pool's last node moved into the hole. A slot not in memory
costs about 117 bytes, charged 120. A stray read of one now stops with an
index error, where it used to read an empty node.

| 10 million rows in key order, random point selects | before | after |
|---|---:|---:|
| 64 MB cache | 15,200/s, 1.41 reads each, RSS 75 MB | 16,700/s, 1.19 reads each, RSS 66 MB |
| 128 MB cache | 19,200/s, 1.00 reads each | 19,800/s, 0.96 reads each |

Caught: `freeNode` not telling the moved node its new frame (5 programs).
A further 40 bytes a slot could come from moving the history lists into a
map (most slots have none) and narrowing `SlotMeta`'s fields.

**Describe once per schema.** libpq, and so pgbench's prepared mode,
sends Bind, Describe portal, Execute, Sync for every execution, and
Describe planned the whole query (catalog lookup included) to report its
columns: 15% of the SQL thread, then Execute planned it again. A prepared
statement now keeps the columns Describe found, with the catalog's write
count then. The store counts the writes to one watched tree
(`Store.watch`, `changes`), which the executor sets to its catalog at
bootstrap; any DDL by any session changes the count. Describe fell to
2.7%; 10 million rows at 128 MB: 19,800 to 21,000 selects/s.
`wire_describe` drives the protocol by hand: one prepared statement run
three times while another connection inserts a row (same columns), then
drops and recreates the table with others (new columns, matching rows).
Caught: a cache never invalidated, and a catalog never watched. Next:
planning at Execute, 17% (9.4).

**A prepared statement keeps its plan.** Execute planned the SELECT every
time: 17% of the SQL thread, catalog lookup included. A prepared
statement now keeps its plan (`PlanCache` in the wire layer's
`Prepared`, passed down through `runCached`, `execIn` and `execStmt`).

- **Keyed by the schema the transaction sees.** A snapshot may predate
  the latest DDL, and a plan made from a newer catalog could name an
  index or a table's tree the snapshot cannot see. So the key is a
  version row in the catalog (`\x02version`), which every DDL statement
  bumps and which is read through the transaction. Concurrent DDL
  statements conflict on it, which serializes them.
- **Never kept when planning looked at a parameter's value:** a LIMIT or
  OFFSET that is not a literal, and the question whether `x > $1`
  implies a partial index's predicate. Both count in `PARAM_LOOKS`.
- **A statement run once** (simple query protocol, `Session.run`) keeps
  nothing.

| 10 million rows, random point selects | before | after |
|---|---:|---:|
| 128 MB cache | 21,000/s, user 25.2 us a select | 22,500/s, user 21.3 us |
| all in cache (ids 0 to 99,999) | 43,400/s, user 11.4 us | 47,200/s, user 9.1 us |

All in cache, system calls (11.3 us a select) now cost more than the
user code: the socket side of the io_uring question.

`exec_plancache` uses two sessions. Covered: one plan for three runs; a
new plan after CREATE INDEX, and after a table is dropped and remade
with other columns; LIMIT $1 and a partial index (5 and 12 rows) never
kept; a block begun before a drop and remake keeps the plan its snapshot
matches and sees the old rows, then plans again after COMMIT; `run`
keeps nothing. Caught:

- DDL not bumping the version (a wrong, empty result);
- the version read outside the transaction;
- LIMIT looks not counted (1 row where 3 were asked);
- partial-index looks not counted (7 rows where 12 were right);
- a one-shot run keeping its plan.

Lexell's PostgreSQL client parsed every query as the unnamed statement,
so a Lexell program never reused a plan. It now has prepared statements
the program asks for (`prepare`, `queryPrepared`, `closePrepared`;
design/pgwire.md 7.2). `wire_prepared` runs them against lexdb in one
process:

- a select run for three ids takes one round trip each;
- a prepared insert;
- the select after another connection remakes the table with other
  columns: lexdb plans it again, where PostgreSQL refuses with 0A000;
- LIMIT $1;
- a statement that does not parse;
- a statement used on another connection.

### 9.18 The whole-server crash test

`tests/lexdb/crash.py` runs a real lexdb process on the real disk.
`crash/client.lxl`, on `lib/postgres`, loads it from 12 connections:

- transfers in blocks: two balance updates and a log row;
- prepared inserts of about 180 bytes, which split the tree;
- deletes of each worker's own acknowledged rows.

After 0.3 to 3 s the server is killed with SIGKILL, or every fifth round
stopped with SIGTERM, when it must exit 0. Every fourth round the
restarted server is killed again during recovery. The server runs with a
4 MB cache, 1 MB log segments and a checkpoint every 512 KB of log
(`LEXDB_CACHE_MB`, `LEXDB_SEG_KB`, `LEXDB_CKPT_KB`), so kills land in
evictions, segment switches and checkpoints.

After each round, a check on the restarted server, against every round's
records:

- the 1,000 accounts still sum to 1,000,000;
- every acknowledged insert is there and every acknowledged delete gone
  (an operation in flight at the kill may go either way);
- no row is there that was never attempted;
- every row's worker and note are what its id says;
- per worker, the index and the scan count the same rows.

A kill leaves the kernel's page cache, so this tests the server's own
path: sockets, group commit, checkpoints, recovery. A power cut is the
simulated disk's (`store_crash`).

40 rounds (seed 2) passed: 240,451 acknowledged writes and 387 in flight
over 32 kills, 10 of them in recovery, and 8 clean stops. Recovery took
0.02 to 0.1 s. Two planted bugs were caught in the first round, and put
back:

- a commit acknowledged before its flush: 9 acknowledged inserts missing;
- replay stopping at the end of a log segment: acknowledged deletes back
  and inserts missing.

The test is not in the quick suite (`tests/lexdb.py`): 40 rounds take
about three minutes.

It also shows the cost of page-level conflicts. About 15% of all
operations failed with 40001 (43,339 of about 284,000): transfers among
1,000 accounts in a few leaves collide even when they touch different
accounts. That is the baseline for per-row conflicts (9.4), next.

### 9.19 Conflicts per row

A commit failed when any leaf it read had changed since, even for another
row in that leaf. Transfers between 1,000 accounts in a few leaves failed
15% of the time in the crash test (43,339 of about 284,000 operations),
and 3% in the mixed benchmark.

- **A read is a key range** (`Mark{tree, lo, hi, seq}`), as of the commit
  it saw:
  - a point read, found or not, is `[key, key+"\x00")`;
  - a scan's chunk runs from its cursor to the leaf's fence, or to the
    key where its callback stopped (a backward scan the other way);
  - adjacent chunks merge, so a long scan is one range.
- **Committed writes are kept** in commit order (`Db.wlog`: seq, tree,
  key; a dropped tree is a write to all of it). There are at most
  `WLOG_MAX` (131,072). Past that the older half goes, and a read older
  than what is kept fails its check (a conflict).
- **A commit fails only when a write committed after a read falls in the
  read's range.** That is the check of backward-validating OCC, in key
  ranges, so an insert into a range a transaction scanned conflicts with
  it: no phantoms. A block's reads are its snapshot's, as of `snapSeq`,
  so a write applied but not yet durable when it began counts as after.
- **Leaf identity no longer matters.** A split, an eviction or a freed
  page used to need care (`Mark.page`, `freedAt`), and both are gone.

| | before | after |
|---|---:|---:|
| crash test, conflicts by round 10 (seed 2) | 11,739 | 122 |
| crash test, acknowledged writes by round 10 | 63,839 | 68,177 |
| mixed: 16 writers in blocks, failed | 2.96% (814) | 0.04% (11) |
| mixed: 8 point readers | 20,800/s | 20,300/s |

The 11 failures left are real: two writers updating the same one of
10,000 rows. The write log costs about 70 bytes a write kept, at most a
few MB, outside the cache's budget.

`store_rowconflict` covers, all in one leaf:

- two transactions updating different rows (both commit), and the same
  row (the second fails);
- an insert into a scanned range (a phantom: fails), and at its exclusive
  end (commits);
- scans stopped by their callback, forward and backward: an insert inside
  the read part conflicts, one past it does not;
- a missing key read and then inserted (fails), and its neighbour
  (commits);
- a tree dropped after a read of it;
- a block, where a neighbouring row passes and its own row fails;
- a read older than the kept log (`setWriteLogMax`).

Caught, each put back:

- exact keys only, no ranges;
- an inclusive range end;
- writes of the read's own commit counted;
- a drop not logged;
- the floor ignored;
- blocks' reads not noted;
- a scan's stop ignored;
- a missing key not noted.

### 9.20 Schemas

- **Names.** `schema.table` anywhere a table is named; `s.t.c` as a
  column (the schema is not checked: the column is `t.c`). The parser
  joins a qualified name with `QSEP` (`\x1f`, which no identifier holds);
  `public.t` is `t`.
- **The catalog.** A table's key is its qualified name, so public's tables
  keep the keys they had and old databases need no change. A schema is a
  row of its own (`\x03name`). An index lives in its table's schema: the
  same index name may be used in two schemas.
- **The search path.** `SET search_path TO a, b` (also `= 'a, b'`, `SET
  SCHEMA 'a'`, `RESET`). It is the session's, and its open transaction
  carries a copy (`Txn.path`). `findTable` looks an unqualified name up
  along it: the first schema holding it. A new unqualified table or index
  goes in the first schema on the path that exists. With none:
  3F000, as in PostgreSQL.
  - A ROLLBACK restores the path from before its block, as it does the
    other settings.
  - The default path is `[]` (public alone), so a statement pays nothing
    for it: point selects in cache ran at 46,500 to 48,500/s before and
    after, user time 9.0 to 9.3 us each.
- **Kept plans and descriptions** depend on the path: a prepared SELECT's
  plan is keyed by the catalog version and the path, and the wire's kept
  description (9.17) by the catalog's changes and `Session.pathVersion`.
- **`CREATE SCHEMA [IF NOT EXISTS]`**, **`DROP SCHEMA [IF EXISTS] ...
  [CASCADE | RESTRICT]`**. DROP refuses (2BP01) while the schema holds a
  table; CASCADE drops them and their indexes. public cannot be dropped.
- **`SHOW name`**, **`SHOW ALL`**: lexdb's settings, and
  `transaction_isolation` (serializable).

Not done: `ALTER ... SET SCHEMA`, privileges, `$user` in the path (a
schema named `$user` is looked for and usually not there, which is what
PostgreSQL does for a user without one), `current_schema()`, and the
`pg_catalog` and `information_schema` views.

`exec_schema` covers:

- public's t and s's t side by side, and a join of the two;
- the path finding s's t first and a table only in public;
- an unqualified CREATE going in s;
- the same index name in two schemas, EXPLAIN naming it, DROP INDEX found
  by the path or qualified;
- UPDATE and DELETE of s.t;
- a block using the path from before BEGIN and one SET in it, and the
  ROLLBACK restoring it;
- a prepared SELECT planning again when the path changes;
- DROP SCHEMA refused, then CASCADE;
- the errors.

`wire_prepared` adds a prepared `SELECT *` described again when only the
path changed.

Planted and caught, each put back: public not normalised, the path
ignored, the plan's key without the path, an index outside its table's
schema, DROP SCHEMA ignoring its tables, ROLLBACK keeping the path, a
block not given the path at BEGIN or at a SET in it, the wire's
description kept across a path change, CREATE ignoring the path.

### 9.21 IN (subquery) as lookups

`col IN (SELECT ...)`, the subquery uncorrelated, was a filter over a full
scan even with an index on col. Such a subquery already runs once before
the tables are read, so its values are known when each level builds its
scans.

- **The path.** `choosePath` takes it as it takes an IN list: as the
  column after the equalities, on the primary key or an index
  (`Path.inSub`). `pathScans` makes a lookup per distinct value, in key
  order. The condition stays a filter, so what IN means (NULLs, numbers
  against text) is decided as before. A value not of the column's type is
  left out of the lookups rather than being an error.
- **Too many values.** There are no row counts yet to choose by. Past
  `IN_LOOKUP_MAX` (1,000) distinct values the level reads the whole table
  instead (`Scan.whole`), not the whole index. Such a path never serves an
  ORDER BY, since that read is in primary key order.
- **Measured.** In 10,000 rows, `region IN (3 values)` reads 300 rows
  instead of 10,000.

`exec_insub` compares each result with the same query written so no path
can use it (`region + 0 IN ...`):

- on an index, on the primary key, in a join's second table;
- the subquery giving nothing, 3 values 10,000 times (still lookups),
  NULLs, a value twice, text, numeric and unconvertible values for an
  int column;
- more than 1,000 values on the key and on the index, with ORDER BY still
  sorted;
- DELETE with it, and EXPLAIN.

Caught, each put back:

- no fallback;
- the path serving ORDER BY;
- an unconvertible value as an error;
- values kept with duplicates;
- the path never chosen.

Not caught, as expected: the fallback reading the whole index (the same
rows, only slower), and NULLs looked up (the subquery's values never hold
them).

### 9.22 INSERT ... SELECT, and WITH before INSERT, UPDATE and DELETE

- **`INSERT INTO t [(cols)] SELECT ...`**, or the query in parentheses.
  The query is kept as the statement's `inner[0]`, with its own
  subqueries. It runs to its end before the first row goes in, so `INSERT
  INTO t SELECT ... FROM t` never reads its own rows. Its rows go through
  the same checks as VALUES' (`insertOne`): types, NOT NULL, the key,
  the indexes. A parameter in the query takes its type from what it is
  compared with there.
- **`WITH ... INSERT | UPDATE | DELETE`.** A CTE is parsed again where it
  is named (9.10), so it needs no executor change: it is used in an
  INSERT's query, or in an UPDATE's or a DELETE's subqueries. Recursive
  CTEs work too.

Not done:

- `RETURNING`, and with it data-modifying CTEs;
- `UPDATE ... FROM` and `DELETE ... USING`;
- `INSERT ... ON CONFLICT`;
- `DEFAULT VALUES` and `DEFAULT` in a VALUES row (there are no column
  defaults yet).

`exec_insertsel` covers:

- all columns, a column list with expressions, a query in parentheses;
- a table into itself;
- a duplicate key from the query (an error, nothing inserted);
- too many columns, and NULL into NOT NULL;
- WITH before INSERT (plain and recursive), UPDATE and DELETE;
- a parameter's guessed type;
- a block rolled back;
- WITH before CREATE (an error).

`exec_with`'s case of a refused `WITH ... INSERT` now uses CREATE TABLE.

Caught, each put back:

- the query's rows cut short;
- the query's subqueries not its own;
- no parameter type from the query;
- the column count unchecked.

### 9.23 A correlated subquery's value as a lookup's key

`b.id = (SELECT min(id) FROM c x WHERE x.grp = a.grp AND x.id > a.id)`
was a filter over every row of b, for every row of a: path values had to
be free of correlated subqueries (`valBefore`), since those run per row
(`fillCur`) and a path's values were evaluated without them.

- **Choosing.** A path's key value (`keyBefore`) needs only to use the
  tables before its level; a correlated subquery whose references are
  among them, or the parent query's, qualifies. Equalities, ranges and IN
  lists all take such values. A value using the level's own columns stays
  a filter.
- **Running.** Before the level is read for a row of the tables before it,
  `pathCur` runs the path's correlated subqueries (memoized by their
  references' values, as a filter's are) and the scans are built with
  their values. The condition stays as a filter, so a subquery giving no
  row (NULL: no key) or two rows (an error) means what it meant.
- **Per row.** A level whose path holds such a value is read per row
  (`pathOuter`), never hashed once: in a subquery, a value using only the
  parent query's columns still changes from one run to the next.
- **Measured.** "Each row's next row in its group" over 1,000 rows reads
  990 rows of b instead of 1,000,000.

`exec_corrkey` compares each result with the same query written so no
path can use it (`col + 0`):

- the primary key and an index;
- a range;
- an IN list;
- NULL and two-row subqueries;
- a subquery keyed by its parent's correlated subquery, and a join's
  second table inside a subquery keyed so;
- a value using the table's own columns.

Caught, each put back:

- never a key;
- such a level hashed once;
- the values not computed before the scan;
- the level's own columns allowed in the key.

### 9.24 Correlated subqueries in GROUP BY and in aggregates

`sum((SELECT count(*) FROM o WHERE o.cust = c.id))` and `GROUP BY (SELECT
grp FROM c WHERE c.id = o.cust)` were refused: grouping happens in
`runQuery`'s row callback, and a correlated subquery cannot run there
(the run and the transaction are held by the read).

- **Rows kept, then grouped.** When a GROUP BY key, an aggregate's
  argument or its FILTER holds a correlated subquery (`groupCorr`), the
  callback only keeps the rows, counted against `max_statement_mem`.
  Then each row's subqueries run (`fillCur`, memoized by their
  references' values) and it is grouped (`addToGroup`, the grouping
  shared with the usual path). Without such a subquery nothing changes.
- **A scalar subquery written twice is one.** `SELECT (subquery), count(*)
  ... GROUP BY (subquery)` needs the two to match, as PostgreSQL matches
  them by their text. The parser now gives a scalar subquery the same
  number as an earlier one with the same tokens at the same level
  (`Stmt.src`). It also runs once per row instead of twice. Only scalar
  subqueries: a FROM subquery's rows are moved into its level, so two
  levels cannot share one.

`exec_groupcorr` compares each result with the same answer written with a
join:

- sum of a correlated count, max per group, count(DISTINCT ...);
- GROUP BY a correlated subquery, and HAVING on it;
- FILTER (WHERE EXISTS correlated);
- MIN with a correlated argument;
- two subqueries differing in one token kept apart; the same text twice
  in FROM still two levels;
- the kept rows over `max_statement_mem` (256 kB: an error; no limit:
  the answer);
- EXPLAIN ANALYZE's runs: 1,000, one per distinct reference.

`exec_sub`'s refused sum of a correlated count now gives its answer.

Caught, each put back:

- the rows not kept (the old refusal's case);
- the kept rows not charged;
- FILTER's values not computed;
- no merging;
- merging regardless of the text.

### 9.25 ORDER BY inside an aggregate

`string_agg(name, ',' ORDER BY k DESC NULLS LAST, name)`.

- **Parsing.** The keys follow the call's arguments. The call's name
  carries their directions (`string_agg order:Da`: `a` ascending, NULLs
  last; `A` ascending, NULLs first; `d` descending, NULLs first; `D`
  descending, NULLs last), as it already carries DISTINCT and FILTER.
  `collectAggs` takes them off into `AggSpec.order` and `dirs`.
- **string_agg** keeps each value with its own separator and its keys,
  and sorts when it finishes (stable: ties keep the order the rows came
  in). Each value but the first is preceded by its own row's separator,
  as in PostgreSQL. The other aggregates accept ORDER BY and ignore it:
  their results do not depend on order.
- **Correlated keys** group later, as correlated arguments do (9.24).
- **`exprText` shows the ORDER BY** (`string_agg(name, ',' order by k
  desc)`). It is the key equal calls share an accumulator by: without the
  directions, two calls differing only in them shared one.

`exec_aggorder` covers:

- ascending and descending;
- per group;
- NULLs' default places and NULLS FIRST/LAST;
- two keys;
- each row's separator, forward and backward;
- sum with ORDER BY;
- DISTINCT;
- two orders in one query;
- a correlated key;
- no rows;
- ORDER BY in a function that is not an aggregate (42883).

Caught, each put back:

- DESC ignored;
- NULLs always last;
- NULLS FIRST not parsed;
- separators by arrival;
- ties unstable;
- accumulators shared across directions, and `exprText` without them;
- the second key ignored.

### 9.26 A correlated scalar aggregate as one grouped run

`SELECT c.id, (SELECT count(*) FROM o WHERE o.cust = c.id) FROM c` ran the
subquery once per distinct `c.id` (memoized). Without an index on
`o.cust`, each run read all of o.

- **When.** `hashSub` now also takes a scalar subquery that:
  - is one aggregate row (no GROUP BY, HAVING, DISTINCT, LIMIT or
    OFFSET, and no subquery in its output);
  - refers to its outer row only in equality keys;
  - has no path that already uses those references.

  That last rule is the one EXISTS and IN follow (9.10): with an index on
  the key, a lookup per row reads only the rows it needs.
- **How.** The key's inner sides become the subquery's GROUP BY, and it
  outputs the key, then the aggregate. `runHashed` keeps a value per key.
  For a key with no rows, or a NULL outer key, the value is the aggregate
  over no rows: count 0, sum NULL, `coalesce(sum(x), 0)` 0,
  `count(*) + 1` 1. It is computed once, from fresh accumulators.
- **Measured.** For 50 customers over 9,990 orders, o is read once
  (9,990 rows) instead of 50 times (499,500).

`exec_hashagg` compares each result with the same subquery written with
`LIMIT 1`, which is not hashed and returns the same single row:

- counts, and a key with no rows;
- sum, coalesce and count + 1 over no rows;
- max;
- an extra filter;
- two keys;
- a NULL outer key;
- in WHERE;
- a non-equality reference (not hashed);
- a key with an index (not hashed);
- EXPLAIN and the rows read.

Caught, each put back:

- the no-rows value left NULL;
- never hashed;
- LIMIT allowed (wrong answers: the limit applies to the grouped run);
- not grouped by the key.

Not caught, as expected: dropping the NULL-key check, since NULL keys are
never stored and the lookup misses anyway.

### 9.27 generate_series, unnest and arrays

The user uses `generate_series`, and `unnest(a, b, ...)` to pass arrays of
data as parameters and turn them into rows (`INSERT INTO t SELECT * FROM
unnest($1::int[], $2::text[])`).

- **Functions in FROM** are subqueries. `generate_series(start, stop [,
  step])` or `unnest(array, ...)`, with `[WITH ORDINALITY] [AS alias
  [(columns)]]`, parses as a FROM subquery whose select items are the
  arguments and whose `srf` names the function. Planning is a subquery's:
  - an argument using an earlier FROM item makes it LATERAL (implicitly,
    as in PostgreSQL), run per row and memoized;
  - its columns come from its arguments' types (`srfCols`);
  - a single-column function with an alias and no column names takes
    the alias as its column (`generate_series(1, 3) g`).

  At run time `execSrf` evaluates the one row of arguments and makes the
  rows.
- **generate_series** over int4, int8 or numeric, by the arguments'
  widest type. A step of 0 is an error. A NULL argument gives no rows.
  Past the type's range it stops.
- **unnest** sets the arrays side by side, the shorter padded with NULLs.
  A NULL array gives no rows.
- **Arrays** are one-dimensional. Their value is PostgreSQL's text form
  (`{1,"a b",NULL}`), so `Val` is unchanged and results go out with the
  array's OID as PostgreSQL sends them.
  - A cast (`'{1,2}'::int[]`, `$1::text[]`) checks each element against
    the element type and writes the canonical form. `ARRAY[a, b]` builds
    one.
  - A parameter cast where it is used (`$1::int[]`) is described to the
    client as the array type. Binary array parameters (int2, int4, int8,
    bool, text, varchar elements) become the text form at Bind.
- **Fixed on the way:** a column name repeated in one FROM item (`(SELECT
  1 AS a, 2 AS a) x`, and unnest's columns, all named `unnest`) resolved
  to the first column, so `SELECT *` showed it twice. Now each is its own
  column (marked internally, `DUPSEP`, the mark off in output names), and
  a reference to the name is ambiguous (42702), as in PostgreSQL.

`exec_srf` covers:

- generate_series up, down, numeric, int8, empty, NULL and its errors;
- the alias as the column; WITH ORDINALITY;
- LATERAL per row of a table;
- a series joined to a table's key (a lookup per value);
- unnest of several arrays with padding, NULLs and quoting, empty and
  NULL arrays;
- casts and their errors (a bad element, no braces, two dimensions);
- `ARRAY[]`;
- the column types and parameter types a client is told;
- `INSERT ... SELECT * FROM unnest($1::int[], $2::text[])`;
- the rows over max_statement_mem.

A raw-protocol client (Parse with unknown types, Describe, Bind with
binary arrays, as pgx does) was checked by hand: the parameters are
described as int4[] and text[], and three rows come back, a NULL and a
quoted element among them.

Caught, each put back:

- repeated names shared;
- no ordinality;
- no padding;
- descending series ending wrong;
- casts not typing parameters;
- functions not LATERAL;
- the alias not the column;
- elements unchecked.

### 9.28 op ANY (array) and op ALL (array)

`WHERE id = ANY($1)` passes a list of keys as one parameter, one plan for
any number of them (an IN list's plan is per length).

- **Parsing.** After a comparison operator, `ANY`, `SOME` or `ALL` and a
  parenthesis: with an array, the call `"any op"` or `"all op"` (x,
  array); `exprText` writes it back, so filtered-index predicates and
  aggregate keys keep it. With a subquery, `= ANY` is `IN` and `<> ALL`
  is `NOT IN`; other operators with a subquery are refused (0A000).
- **Values**, as PostgreSQL: ANY is true if one comparison is, else NULL
  if an element or x is NULL, else false; an empty array gives false
  (ALL: true) whatever x is. Elements are read as x's type.
- **Lookups.** `col = ANY(array)`, the array from constants, parameters
  or earlier tables, is a lookup per element on the column's key or
  index (`Path.inArr`, beside the IN list and the IN subquery), shown
  as "lookup for each element of the array". Elements not of the
  column's type are skipped there and the condition, which stays,
  decides. From an earlier table (`JOIN t ON t.id = ANY(p.ids)`) it is
  recomputed per row.
- **Parameters.** `col op ANY($1)` describes `$1` as the array of the
  column's type, so drivers send an array (binary, as pgx does, or text).

`exec_any` covers:

- ANY, SOME and ALL with each kind of answer, NULLs and empty arrays;
- text elements, quoting and case;
- lookups by key and by index (2 rows read of 10,000), with a repeated
  and a missing key;
- a parameter: its type, and one plan kept;
- `<> ALL`; `= ANY` and `<> ALL` with subqueries, and the refusal;
- an array column joined per row;
- a filtered index whose predicate uses ANY, and a row inserted later;
- errors.

`WHERE id = ANY($1)` through the server with a binary int4 array from a
raw-protocol client: `$1` described as int4[], and the rows found.

Caught, each put back:

- NULL elements ignored;
- an empty array NULL;
- ALL as ANY;
- never a lookup;
- no array parameter type;
- the array not recomputed per row;
- `<> ALL (subquery)` as IN;
- exprText losing the operator.

### 9.29 Large rows

A row whose leaf entry would be over `MAX_ENTRY` (1,350 bytes) used to be
refused (54000). Now it is cut into chunks, kept in a **companion tree** of
its table (id `tree + OVF`, 2^40), as PostgreSQL's TOAST keeps them in a
table of their own. The leaf keeps a 14-byte stub: a mark (0xFF), 1, the
value's length and its CRC32C. A value that itself begins with 0xFF is
stored with one more 0xFF before it, so a stub is never mistaken for a value.

- **Only where commits apply.** The log, a transaction's writes, conflict
  checks and what `get` and scans return all carry the value as written.
  `putValue` cuts it when the commit applies (and so again when recovery
  replays the log). Snapshots, checkpoints, eviction and recovery needed no
  change: the companion is an ordinary tree.
- **Chunks** are keyed by the row key's length, the key and the chunk's
  number (the length keeps one key's chunks from mixing with a longer
  key's). A chunk fills one leaf entry. They change only with their row,
  so they need no conflict marks of their own.
- **Before a commit applies**, `writeNeeds` also loads the companion's
  leaves for the key's chunks when the write makes or removes a large value.
  An overwrite or delete removes the old chunks, the ones found under the
  key, not as many as the stub's length says, so a damaged stub cannot make
  a commit run on (9.30). Dropping the table drops the companion tree.
- **Reading back** (`unstore`): the chunks are read and checked against the
  stub's length and CRC. A live read that finds them changed since it read
  the stub (a commit between, while it loaded a page) fails with 40001, as
  its commit would have. A snapshot reads them as of its snapshot.
- **Limit:** 64 MiB a row, the wire's largest message.
- **Fixed on the way (not only large values):** a commit that emptied a
  leaf unlinked it, and its keys' range went to a neighbour. A later write
  of the same commit into that range, with the neighbour not in memory,
  panicked the server, because a commit cannot load a page. This happens
  when rows are deleted and put back in one transaction. Checked against
  the old store: 300 such commits with a small cache panicked within the
  run. Now an empty node is unlinked only when the nodes that take its
  range are in memory; otherwise it stays, empty.

`store_big` covers:

- 60 crashes against a model, with values of every size (either side of a
  leaf's largest, values beginning with 0xFF or shaped like a stub, up to
  40 KB) over a cache of a few nodes; then every row deleted and no chunk
  left;
- a snapshot reading an overwritten large value;
- a live scan finding a row's chunks replaced by a value of the same length
  (40001: the CRC tells);
- the next table's id (a companion's must not raise it);
- limits: a 513-byte key, a value over 64 MiB, a megabyte, a 512-byte key
  with a large value;
- a dropped table's chunks;
- the delete-and-refill commits above.

`exec_big` does the same through SQL:

- 40 rows to 120 KB; reads through an index, ORDER BY and backwards;
- updates to larger, to small and to large; deletes;
- reopening from the checkpoint and the log;
- a megabyte parameter;
- a primary key too large.

Planted bugs, each put back (the run was stopped for low memory before
the last one):

- caught:
  - chunks kept on delete;
  - chunks kept on overwrite;
  - the companion not loaded;
  - empty leaves always unlinked;
  - the CRC unchecked;
  - the companion not dropped;
  - a companion's id raising the next table's;
  - `get` giving the stub;
  - a backward scan giving the stub;
- not confirmed:
  - no escape: reported not caught, probably because the diff held raw
    bytes and the script's grep treated it as binary;
  - the last chunk cut short: not run.

### 9.30 Large rows: measured, and full pages in random order

Measured on real files (`fdatasync` per commit), 1,000 rows of 20 KB in a
table `d (id, title, body)`, beside a table `e (id, title)` without bodies:

| | key order | random order |
|---|---:|---:|
| insert, a row of each table (two commits) | 2.2 ms | 2.2 ms |
| pages that are data, before | 90% | 57% |
| pages that are data, after | 90% | 84% |
| scan of d for its titles | 9.1 ms | 11.4 ms |
| scan of e for its titles | 0.2 ms | 0.2 ms |

- **Space.** Chunks put into the middle of the companion tree split
  leaves in half, so values loaded in random order left them half full.
  Now a companion leaf splits just after the new entry, or else just before
  it, when both halves fit. A run of chunks then fills its leaves, as a
  load in key order does. Tables' splits are unchanged. In `store_big`,
  300 values of 8 KB in random order: 96% data, 61% without the change.
- **Chunks are removed by walking their range** in the companion, not by
  the count the stub's length gives. A stub that claimed 8×10^18 bytes (a
  planted bug made one) kept the commit removing chunks indefinitely.
- **Reading.** A scan that needs only `title` costs 45 to 55 times as
  much with the bodies: every row's chunks are read and put together.
  This is the next step (9.4, item 8).
- **Measuring with the simulated disk misleads.** The first run took
  147 ms a row. A profile (`perf`, with the `LXL_NATIVE_MAP` symbol map)
  put 93% of the time in the simulated disk's flush, which copies the
  whole log segment to model a crash. With 64 MB segments that is 64 MB
  per commit. The tests use 1 MB segments. Measure on real files.

### 9.31 Reading only the columns used

A large row was read whole however little of it a query used (9.30).
This was done in three steps, all built:

1. **A SELECT decodes only the columns it names** (`narrow`, after
   `buildQuery` in `planSelect`). For each table it reads, the columns
   named anywhere in the statement (its parts and its subqueries, which is
   where correlated references are) are decoded. The others are skipped in
   the row and read as NULL (`decRowNeed`). A `*` anywhere in the statement
   means all. A SELECT's results depend on nothing else. UPDATE and DELETE,
   which write rows back whole, are not planned there, and `narrow`
   checks the statement is a SELECT.

   This applies to every row, not only large ones. The 40 test programs
   are its check: a column missed would read as NULL. Planted bugs, each
   caught by `exec_sub`:
   - names in subqueries not collected;
   - names in join conditions not collected;
   - names in ORDER BY not collected.
2. **Long texts are stored after a row's other columns.** A row with a
   text of `LONG` (256) bytes or more begins with tag 6 and its column
   count; each such text is tag 5 and its length in its place, its bytes
   after the last column, in column order. The other columns stay at the
   row's start. The count keeps a column added later reading as NULL
   rather than as the long texts' bytes. Rows with no long text are
   written as before. `exec_big` reads such rows column by column and
   whole, and checks each long text's first and last bytes. Planted:
   the long texts' offsets not advancing, caught by those bytes (lengths
   alone did not catch it).
3. **A large row's start stays in its leaf.** A stub is now version 2: the
   length and CRC, then the value's first bytes, the chunks holding the
   rest (version 1 stubs are still read). How many is the writer's
   choice: `Txn.putRow`'s head, as many as the leaf holds. The executor
   gives a row's columns before its long texts (`rowHead`), so the table's
   leaves stay small. A store-chosen amount (all the leaf holds) left three
   rows a leaf and a random-order load 80% data. The head is in the write
   and in the log: a put with a head is log op 5, its length after the
   value, and `frameLen` counts it.

   `getPart`, `scanPart` and `scanBackPart` give a large value's stub as
   it is; `partOf` gives its first bytes and `whole` the value. A SELECT
   with columns narrowed reads this way. A row whose used columns are all
   in its first bytes (`fitsIn`: the columns before the long texts are
   there, and no long text is used) is decoded from them; any other is
   read whole.

   Measured as in 9.30, scanning `d` for its titles:

   | | before | after | e (no bodies) |
   |---|---:|---:|---:|
   | key order | 9.1 ms | 0.48 ms | 0.20 ms |
   | random order | 11.4 ms | 0.30 ms | 0.21 ms |

   Space is as before: 90% and 84%.

   `exec_big` counts the large values read whole (`Stats.wholes`):
   - none for a scan of titles, an index scan, or a backward scan;
   - every row for a sum of the bodies, one for a body by key, and one for
     a long text column.

   `store_big` writes values with a head and reads them in part, again
   after a crash: recovered from the log. One value's length puts its log
   frame 2 bytes into a page.

   Planted, each caught:
   - no head passed;
   - a used long text taken as being in the first bytes;
   - a Part scan, forward or backward, reading whole;
   - the log losing the head;
   - a frame's length counted without the head's 4 bytes. Not caught
     until the frame was placed on a page boundary: frames are padded to
     pages, so 4 bytes matter only there.

### 9.32 Freeing a dropped table's pages

A drop freed only the nodes in memory. A node not in memory has no slots
for its children, so the pages under it were never freed: dropping a
table that was mostly on disk leaked nearly all of it.

**The dropped subtrees.** When a slot not in memory is released, its page
and the height of the subtree under it go on `Db.dropped`, instead of the
page alone going to the free list. Its subtree is on disk as it was
written: a node is evicted only clean, and only after its children.

**The walk.** Each checkpoint, before it writes, takes the list and reads
up to `DROP_READS` (256) of its pages (`walkDropped`). An internal page's
children go on the list one level lower; a page of height 0 is a leaf and
is freed without being read. Every page reached is freed as the
checkpoint's other pages are: free once the checkpoint is durable. What
is left of the list is written with the checkpoint, a list like the free
list (`Meta.dropped`, `(page, height + 1)` pairs), and an open reads it
back. A crash at any point leaves each page in one of: a tree, the dropped
list, the free list.

**Heights.** The walk first read every subtree whose height it did not
know, leaves included. A drop's nodes in memory are mostly internal ones
whose children are not loaded, so this read about as many leaves as the
cache's internal nodes have children. Now a drop loads the first leaf of
the tree and of its companion (`writeNeeds`: a few pages), the depth of
that leaf gives the tree's height, and each node released gets its height
from its depth. Heights also go through the slots kept for snapshots
(`Deferred.height`). A height not known (-1) is learned by reading down
the first children (`heightAt`).

**Checked** by `store_drop`, with `audit`. Audit reads a closed data file's
last checkpoint and counts each page's uses. Every page must be in exactly
one of: a tree, a dropped subtree, the free list, a list page.
- A table of 3,000 rows, three levels deep, with a companion tree: 775
  pages. One checkpoint at two reads leaves 671 pages to free. A reopened
  store goes on from there, and the 15 internal pages left take 8
  checkpoints, so the leaves are not read (41 before the heights).
- Afterwards every page but tree a's is free. Writing the rows again does
  not grow the file.
- 12 crashes at random points of a drop and its walk, with commits to
  another tree going on. Some come with the walk partway done in the
  durable checkpoint. Each recovers with nothing lost or freed twice and
  every committed row there.

Planted, each caught: an internal page's children not walked; leaves of
known height read; the list not read at open; the rest of the list not
kept; unloaded subtrees leaked (as before); children one level too low;
the height stored off by one; the depth off by one at the drop; the drop
loading nothing; the deferred release losing the height; freed pages not
given back; freed pages listed again (a page twice).

**Measured** on real files, a table of 400,000 rows of 250 bytes (26,800
pages, 105 MB):

| | the drop's commit | checkpoints walking | the next checkpoint |
|---|---:|---:|---:|
| reopened, nothing in memory | 1.5 ms | one, 26 ms (117 reads) | 7 ms |
| everything in memory | 13 ms | none | 21 ms |

Times vary between runs: another run of the second row gave 8.7 ms and
8 ms.

The walk's time is its reads: 117 took 27 ms, 0.7 ms of it decoding. The
data file is opened with O_DIRECT, and each read waits for the device
(here WSL2's virtual disk). The reads park the checkpoint's task on the
helper pool: commits and queries go on, and only the checkpoint's end is
later.

Not done:
- **The free list is written whole by every checkpoint.** After this drop
  it is 26,800 pages, 53 list pages. A 10 GB table would add 2.5 million,
  20 MB a checkpoint until they are used again. (Built: 9.33, the free
  pages as runs.)
- **A large drop is freed over many checkpoints.** A 10 GB table has
  about 10,000 internal pages: about 40 checkpoints, and checkpoints come
  with the log's growth (`ckptBytes`). With few writes after the drop,
  the space comes back slowly. The reads are one at a time; several at
  once would shorten each checkpoint's share.

### 9.33 Free pages as runs

Every checkpoint wrote the free list whole, and an open read it whole: a
page number for each free page (9.32). Measured on real files, a table of
4 million rows (1 GB, 268,000 pages) dropped and freed:

| | free pages 6 | 268,000, a list | 268,000, runs |
|---|---:|---:|---:|
| a checkpoint of one row | 2.1 ms | 44 ms | 2.1 ms |
| an open | | 43 ms | 1 ms |

A 10 GB table would have added about 0.4 s to every checkpoint.

**Runs.** The free pages are now kept, in memory and on disk, as runs of
consecutive pages: `(first, count)` pairs, highest first, no two touching
(`runsOf`, `mergeRuns`). The pages of a dropped table are mostly
consecutive: those 268,000 pages are 2 runs. A checkpoint turns the pages
it frees into runs (sorting them) and merges them with the free runs. The
list is written as before, on list pages named by a new meta field,
`Meta.runs`. A file written before keeps its flat list in `Meta.free`;
an open reads either and takes both as runs, and the file's next
checkpoint writes runs. The free page count is summed from the runs
(`Stats.free`; a separate counter was one more thing to keep right).

**The lowest page first.** `allocPage` takes the lowest free page, from
the last run. Before, it took the last page freed. Lowest first keeps the
free pages at the file's end together, where they could later be cut off.
Checkpoints before the drop are not slower: 1.9 to 2.4 ms both ways, on
100 MB and 1 GB.

**The worst case** is a free page between every two used ones: then a
run is a page, and the list is twice what a flat one was.

**Checked** by `store_drop`. The audit gives runs, and the earlier steps'
counts are unchanged but for one list page fewer. Added: a file whose
free list was rewritten flat, as before runs, opens with its pages as
runs, and after a write its checkpoint has runs, nothing lost.

Planted, each caught:
- a page given out, its run not shortened;
- touching runs not joined;
- a run one page short;
- freed pages not added when the checkpoint is durable;
- a flat list ignored at open;
- runs ignored at open;
- this checkpoint's freed pages not written;
- the highest page given out.

Not done: cutting the file's free tail; a file does not shrink.

### 9.34 ALTER TABLE, without rewriting rows

`ALTER TABLE [IF EXISTS] [ONLY] name` and then:
- `ADD [COLUMN] [IF NOT EXISTS] name type [NOT NULL | NULL]`;
- `RENAME [COLUMN] a TO b`;
- `RENAME TO name`;
- `ALTER [COLUMN] name SET NOT NULL` or `DROP NOT NULL`.

The RENAME forms stand alone; the others can be several, separated by
commas. They are applied in order to the table's catalog row
(`alterTable`), and the statement does all or none, as any statement in its
transaction. DDL was already transactional, so an ALTER in a block rolls
back with it, and the catalog's version tells cached plans.

**No row is rewritten.** Rows are positional, and a row written before a
column was added has fewer values: the decoder reads the missing ones as
NULL (`decRowNeed` already did, rows with long texts included). So ADD
COLUMN costs one catalog write whatever the table's size. A column added
NOT NULL needs an empty table (23502 otherwise, as PostgreSQL without a
default), and SET NOT NULL scans for a NULL (23502). Both scans are reads
of the transaction: a NULL committed meanwhile by another session makes
the ALTER fail at commit (40001), as the test shows.

**Names.** A table renamed stays in its schema; its indexes' catalog rows,
which name their table, are rewritten. A renamed column is renamed in its
table's filtered indexes' predicates, which name columns. Index columns
are positions and need nothing. DROP NOT NULL on a key column is 42P16.

**Prepared statements.** A statement's result columns are described once,
and libpq describes again before each run, so the client sees new
columns. A client that runs it without describing would read rows by the
old description. Execute now refuses rows whose columns differ from those
last described, with PostgreSQL's 0A000 "cached plan must not change
result type". This covers a table dropped and made again with other
columns too, which went unchecked.

**Not supported yet**, each 0A000: constraints (ADD PRIMARY KEY, UNIQUE,
CHECK, FOREIGN KEY: a unique index can be created), DEFAULT (no column
defaults yet), ALTER INDEX. DROP COLUMN (built: 9.35), ALTER COLUMN TYPE
and SET SCHEMA are the next steps (9.4, item 13).

**Checked** by `exec_alter` and `wire_describe`. Planted, each caught:
- a column added twice;
- NOT NULL added over rows;
- index rows keeping the old table name;
- the old name kept;
- a table renamed to an index's name;
- a table renamed out of its schema;
- predicates keeping the old column name;
- SET NOT NULL over NULLs;
- any row taken as a NULL;
- DROP NOT NULL on the key;
- a column renamed to a name the table has;
- rows unlike the description sent.

The renames to a taken name were not caught at first; the test now tries
both.

### 9.35 DROP COLUMN

`DROP [COLUMN] [IF EXISTS] name [RESTRICT | CASCADE]`, one of ALTER
TABLE's actions (with the others, separated by commas).

**No row is rewritten.** As in PostgreSQL, a dropped column keeps its
place in the stored rows. A table that has dropped a column has
`Table.slots`, each column's place in a row, and `Table.width`, the
places a row has; both are in its catalog row, after its indexes (a
catalog row without them: column i at place i). Reads decode the places
and give the columns (`rowOf`). The columns a query uses are mapped to
places first (`placesNeeded`), so narrowed reads and large rows read in
part work as before. Writes put each column at its place and NULL at a
dropped one's (`encRowOf`), so a dropped value's space comes back as rows
are written again. A column added after a drop takes a new place: a
column added again under the dropped one's name is NULL in the old rows,
not their old values. A table that never dropped a column has no slots
and pays nothing.

**What goes with it.** Indexes on the column, and filtered ones whose
predicate names it, are dropped with it, as PostgreSQL's are; the others'
column numbers, and the key's, move down. The key's own columns cannot be
dropped (0A000): lexdb's tables need their key.

**Cost**, on real files, 200,000 rows of five columns, one dropped: a
scan's `sum` 53 to 57 ms, a filtered count 60 to 65 ms, a filter with
no rows 67 to 69 ms. That is the mapping, an array a row.

**Checked** by `exec_dropcol`: rows with long texts and short ones; each
column read alone; reads through an index on a column after the dropped
one, and backwards; the indexes dropped with it (their trees too) and
those kept, a unique one still enforced; a column added again under the
name; updates and inserts after the drop; a drop rolled back; two drops
in one statement; a key after the dropped column; the key's column, a
column that does not exist, IF EXISTS; after a reopen.

Planted, each caught:
- places not mapped to columns;
- rows written by column, not place;
- needed columns not mapped to places;
- a column added after a drop at the dropped place;
- the key's column not moved;
- indexes' columns not moved;
- an index on the column kept;
- a predicate naming it kept;
- places not saved;
- the width not read back;
- the key column dropped;
- a dropped index's tree kept.

The last was caught only after the test counted the store's trees.

Not done: the places are never compacted (a table that drops and adds
many columns keeps a NULL a place in each row written).

### 9.36 ALTER COLUMN TYPE

`ALTER [COLUMN] name [SET DATA] TYPE type [USING expr]`, one of ALTER
TABLE's actions. Several in one statement are done together, after the
statement's other actions, and USING sees the row as it was. USING may
use any of the row's columns; a subquery or an aggregate in it is refused
(0A000, 42803), as PostgreSQL does.

**Without USING**, only PostgreSQL's assignment casts among lexdb's types:
within a kind (int widths, numeric precision, varchar length), int to
numeric and back, and anything to text. Others (text to int, bool to
int) are 42804, naming the USING that would do it.

**A widening rewrites nothing**: int2 to int4 to int8, a varchar made
longer or text, numeric with more precision and the same scale (or
none). Its values are stored as they are, so only the catalog changes
(`widens`).

**Any other change rewrites the table** (`retype`), as PostgreSQL does.
The rows are read as the table stands, and each gets its new values
(USING, or the column) converted to the new type (`coerce`: 22P02,
22003, 22001 as an assignment). It is checked for NOT NULL and written
to a new tree; two rows whose keys become equal are 23505. Indexes on a
changed column, or whose predicate names one, are made again into new
trees (all of them when the key changes, since their entries hold it). A
unique one made equal is 23505. The old trees are dropped, and their pages
freed by checkpoints (9.32). It is one transaction: an error leaves the
table as it was, and a block's rollback undoes it. The rows are held in
memory, as an UPDATE's are, bounded by `max_statement_mem`.

**Cost**, on real files, 200,000 rows of five columns:

| | |
|---|---:|
| widen an int column to bigint | 5.6 ms |
| UPDATE of every row (for comparison) | 455 ms |
| a column to text, no index on it | 524 ms |
| an indexed column to text | 869 ms |
| the key, with USING | 914 ms |

**Checked** by `exec_retype`. Widenings leave the store's trees as they
were; a rewrite changes them, and their number stays the same (the old
ones dropped). Cases covered:
- int to text and back with USING, an index used after each;
- no automatic cast, bool to text;
- bad values (the statement undone);
- varchar shorter (22001) and longer;
- numeric rounding, to int, and overflow;
- the key to text and back, with another index used after;
- keys made equal;
- a unique index made equal;
- a filtered index whose predicate holds other rows under the new type;
- NOT NULL kept;
- USING with other columns;
- two changes at once;
- large values moved with their rows;
- a rollback, and a reopen.

Planted, each caught:
- every change taken as a widening, or none;
- a shorter varchar taken as one;
- every cast automatic;
- the old table tree kept;
- an old index tree kept;
- indexes not filled again;
- the key's change not felt by the other indexes;
- keys made equal not seen;
- unique indexes not checked;
- NOT NULL not checked;
- USING ignored;
- a filtered index naming the column not made again;
- values not converted.

Three were not caught at first. The test read the other index only after
the key was changed back, which made its stale entries right again. It
never used a filtered index whose rows change. And the unique-check
mutant did not compile.

### 9.37 SET SCHEMA, ALTER INDEX and ALTER SCHEMA

- `ALTER TABLE [IF EXISTS] name SET SCHEMA s`: the table moves with its
  indexes, their names kept. A table or index of any of those names
  already in `s` is 42P07 ("relation ... already exists in schema ..."),
  and a missing `s` is 3F000.
- `ALTER INDEX [IF EXISTS] name RENAME TO new`: in its schema; a name
  taken by a table or an index is 42P07.
- `ALTER SCHEMA name RENAME TO new`: its tables and indexes go with it.
  `public` cannot be renamed, since its names are kept unqualified (0A000);
  a name taken is 42P06, `pg_` names 42939.

Each moves catalog rows only (`moveTable`): the table's under its new key,
each index's, and the index rows' pointer to the table. No data moves; a
table's trees are named by number. All in the transaction, and the
catalog's version is bumped, as for other DDL.

**Checked** by `exec_rename`:
- a table moved, its index used under the new schema;
- names taken, by a table and by an index;
- a schema missing; a move to `public`;
- an index renamed, then renamed again through the search path;
- a schema renamed, its index used, and an insert;
- `public`, a taken name, a missing schema, a `pg_` name;
- a rollback, and a reopen.

After the moves, the old names can be made again: no catalog row is left
under them. Planted, each caught:
- the old table row kept;
- the old index rows kept;
- index rows naming the old table;
- indexes left in the old schema;
- a name taken not seen;
- no such schema not seen;
- an index renamed in its table's row only;
- an index's old row kept;
- an index renamed onto a taken name;
- a schema's tables not moved;
- the old schema row kept;
- a schema renamed onto one that exists.

The old index rows were not caught at first. The old index name being
free again is now checked.

### 9.38 Column defaults

**Where.**
- `DEFAULT expr` in CREATE TABLE and in ALTER TABLE ADD COLUMN;
- `ALTER [COLUMN] c SET DEFAULT expr` and `DROP DEFAULT`;
- `DEFAULT` as a value in INSERT's VALUES and in UPDATE's SET;
- `INSERT ... DEFAULT VALUES`.

A column an INSERT leaves out, or one written DEFAULT, takes its default;
with none, NULL. A NULL written stays NULL. INSERT ... SELECT fills the
columns it leaves out the same way.

**The expression** is parsed as PostgreSQL's `b_expr` is, so that
`DEFAULT 1 NOT NULL` parses: arithmetic, `||`, casts, calls, and
anything in parentheses (`catExpr`). It may not use a column (0A000), a
subquery (0A000), an aggregate (42803) or a parameter (42P02). It is
kept as its text in the table's catalog row, with the column.

**Checked when made.** lexdb has no volatile function (no `random()` or
`now()` yet), so a default's value is the same whenever it is made. Its
value is made, of the column's type, when the default is set. A bad one
(`'abc'` for an int, an overflow) fails then, not at each INSERT. A
statement makes each default once, for all its rows (`defaultsOf`).

**ADD COLUMN ... DEFAULT rewrites no row**, as in PostgreSQL 11 and later.
The value is kept with the column as its *missing value*: what rows
written before the column was added read for it. The row decoder gives
it for a place a row does not have (`placesMissing`, by place, so after
a DROP COLUMN too), and so do narrowed reads. An index made later gets
it, and so does a row updated (written whole). SET DEFAULT and DROP
DEFAULT change new rows only: the rows there keep the value they had. A
NOT NULL column may be added over rows when its default is not NULL.

**Type changes.** A default must be of the column's new type, or the
ALTER fails. A rewrite writes every row whole, the missing values with
them, and then no column has one.

**In the catalog row**, after the places (9.35), which are written, empty,
when there are defaults: a byte per column (1: a default, 2: a missing
value), the default's text, the missing value encoded as a row of one.

**Checked** by `exec_default`:
- each kind of type, with expressions;
- columns left out, DEFAULT in VALUES, DEFAULT VALUES, INSERT ... SELECT;
- SET c = DEFAULT, with and without a default;
- the six errors at CREATE;
- parsing next to NOT NULL, NULL and PRIMARY KEY;
- ADD COLUMN ... DEFAULT over short rows and a row with a long text, read
  whole, alone, in a WHERE, and by an index made after;
- NOT NULL with a default;
- SET and DROP DEFAULT (the old rows unchanged);
- after a dropped column;
- a type change refused by the default, and one that rewrites;
- a rollback, and a reopen.

Planted, each caught:
- old rows reading NULL;
- ADD's default not kept as the missing value;
- SET DEFAULT changing the rows there;
- columns left out NULL;
- DEFAULT in VALUES taken as NULL;
- SET c = DEFAULT ignored;
- defaults not saved;
- a column referenced in a default;
- missing values by column, not by place;
- NOT NULL refused over rows despite a default;
- a default not checked for a new type;
- a default not converted to the column's type.

Not done: volatile defaults (`now()`, `nextval()`, `gen_random_uuid()`)
wait for those functions. When they come, ADD COLUMN with one must
rewrite the rows, and the default must be made per row.

### 9.39 UNIQUE constraints

**Where.**
- In CREATE TABLE: `UNIQUE` on a column, `UNIQUE (a, b)` among the
  columns, either after `CONSTRAINT name`.
- `ALTER TABLE ADD [CONSTRAINT name] UNIQUE (cols)`.
- `ALTER TABLE DROP CONSTRAINT [IF EXISTS] name`.

`NULLS DISTINCT` (the default) is accepted, `NULLS NOT DISTINCT` is 0A000.
`CONSTRAINT name` before NOT NULL, DEFAULT or PRIMARY KEY is accepted, and
the name is not kept.

**As in PostgreSQL, a unique constraint is a unique index the constraint
owns**, of the same name, in the table's schema. `Index.con` marks it,
saved as bit 4 of the index's flags byte; the flags are now read as bits.
The index enforces it and the planner uses it, as any unique index. NULLs
are not equal, and the violation message names the constraint (23505).
DROP CONSTRAINT drops the index. DROP INDEX of it is 2BP01 ("constraint
... requires it"). What happens to indexes happens to it: DROP COLUMN of
one of its columns drops it, a type change rebuilds it, and renames and
SET SCHEMA move it.

**Names** are made as PostgreSQL makes them: the table, the columns and
`key`, joined by `_` and cut to 63 bytes, with 1, 2, ... added while the
name is taken by a relation in the schema or a constraint of the table
(`makeName`). A name given and taken is 42P07 (a relation's) or 42710
(the table's constraint's).

**ADD UNIQUE checks the rows there** as CREATE UNIQUE INDEX does (23505,
"could not create unique index"), through the same code (`addIndex`, now
shared).

**Checked** by `exec_unique`:
- violations naming each kind of constraint;
- several NULLs;
- updates;
- names made around a taken one, and a name given twice;
- ADD over duplicated rows and then without;
- the planner using it;
- DROP INDEX refused, DROP CONSTRAINT (its tree dropped);
- a constraint missing, IF EXISTS, the key's name (0A000);
- DROP COLUMN, a rename, SET SCHEMA;
- a rollback;
- bad columns, and a reopen.

Planted, each caught:
- the flag not saved, or not read;
- the index not unique;
- names made without a number;
- a taken name not skipped;
- DROP INDEX allowed;
- DROP CONSTRAINT leaving the index's tree (caught once the test counted
  the store's trees);
- columns twice;
- CREATE's constraints dropped;
- rows not checked when added;
- a constraint name given twice.

### 9.40 CHECK constraints

**Where.**
- In CREATE TABLE: `CHECK (expr)` on a column or among the columns, either
  after `CONSTRAINT name`.
- `ALTER TABLE ADD [CONSTRAINT name] CHECK (expr)`; DROP CONSTRAINT (9.39).

`NO INHERIT` is accepted (there is no inheritance). `NOT VALID` is 0A000:
the rows there are always checked.

**The rule is SQL's: a row passes unless the expression is false.** NULL
passes. Every row written is checked (`checkChecks`): INSERT (VALUES,
SELECT, DEFAULT VALUES), UPDATE, and a type change's rewrite. A violation
is 23514 "new row for relation ... violates check constraint ...".
ADD CHECK reads the rows there first (23514 "... is violated by some
row").

**When made**, refused:
- a column not the table's (42703);
- a subquery (0A000) or a parameter (42P02), by the parser;
- an aggregate (42803);
- an expression not boolean (42804). There is no type of an expression
  without a row, so it is evaluated on a row of zeros ('' for text,
  false, 0); errors other than 42804 there are let be.

**Names** are made as PostgreSQL makes them (`makeName`): a column's check
is `t_col_check`; a table's is named for its column when it names one, and
is `t_check` otherwise. A number is added while the name is another
constraint's of the table. A check is not a relation, so relations' names
do not count.

**Kept** in the table's catalog row, after the defaults section: a count,
then each check's name and expression text (`exprText`, parsed again on
reading). RENAME COLUMN renames in it. DROP COLUMN drops the checks naming
the column, as PostgreSQL does.

**Cost.** Each check is evaluated by walking its expression for each row.
100K rows in 1000-row INSERTs into a real file: 439 ms without checks,
550 ms with three (about 0.4 µs per check per row; parsing the VALUES is
the larger cost). One-row statements: 3%, the commit's fdatasync being
most of it.

Measuring this first ran on the simulated disk, which took 45 ms per
commit whatever the rows. Its flush copies the whole file, one byte at a
time, to model what a crash keeps. Benchmarks must use a real file.

**Checked** by `exec_check`:
- each kind of check violated (a column's, a named one, a table's, a
  function, IN, OR);
- NULL passing;
- names made and their numbers;
- INSERT ... SELECT, DEFAULT VALUES, UPDATE (the row unchanged);
- ADD over violating rows and then without;
- DROP CONSTRAINT;
- errors when made;
- RENAME COLUMN, DROP COLUMN, a type change;
- a rollback, and a reopen.

Planted, each caught:
- INSERT, UPDATE or the rewrite not checked;
- NULL failing;
- the rows there not checked;
- checks not saved;
- RENAME COLUMN or DROP COLUMN leaving checks;
- check names not compared;
- a table's one-column check named `t_check`;
- an unknown column, an aggregate or a non-boolean allowed;
- DROP CONSTRAINT doing nothing.

### 9.41 Foreign keys

**Where.**
- In CREATE TABLE: `REFERENCES t [(cols)]` on a column, `FOREIGN KEY
  (cols) REFERENCES t [(cols)]` among the columns, either after
  `CONSTRAINT name`. Without columns, t's primary key.
- `ALTER TABLE ADD [CONSTRAINT name] FOREIGN KEY ...`, which checks the
  rows there; DROP CONSTRAINT.
- `ON DELETE` and `ON UPDATE` with NO ACTION (the default) or RESTRICT.
  CASCADE, SET NULL and SET DEFAULT are parsed and refused (0A000) until
  the next step.
- MATCH SIMPLE, NOT DEFERRABLE and INITIALLY IMMEDIATE are accepted.
  MATCH FULL and PARTIAL, DEFERRABLE and INITIALLY DEFERRED are 0A000.

**When made**, as PostgreSQL:
- the referenced columns must be the primary key or a unique index that is
  not filtered (unique constraint or index), in any order (42830);
- as many columns on each side (42830);
- each pair of the same kind of type: the key is looked up by its encoded
  value, equal for int and bigint or for numerics of other scales (42804);
- columns missing (42703) or twice (42701);
- a name taken (42710).

Names are made as PostgreSQL makes them: `t_col_fkey`.

**Kept** in both catalog rows, after the checks: the referencing table's
`fks`, each with its name, columns, referenced table's catalog key and
columns (by name) and actions; and the referenced table's `refBy`, the
tables referencing it (itself among them if so). A statement on either
table finds the other through them, and `fkTables` loads the tables a
statement needs once. A table with neither does no foreign-key work.

**Checked, as PostgreSQL checks them:**
- *A row written to the referencing table* (INSERT, UPDATE of the key's
  columns): a NULL in the key's columns references nothing (MATCH SIMPLE).
  Otherwise the key is looked up in the referenced table, through its
  primary key or the unique index (`parentHas`). A key not there may be
  inserted later in the same statement (a table referencing itself, a
  child row before its parent), so it is looked up again at the
  statement's end (`fkFinish`), then refused (23503 "... is not present
  in table ...").
- *A referenced key deleted or changed:* the rows referencing it are
  looked for (`referenced`) through the referencing table's primary key or
  an index starting with the key's columns; failing both, the whole table
  is read. With rows found, both look again at the statement's end (23503
  "... is still referenced from table ..."). By then the rows referencing
  it may be gone: a table referencing itself can be emptied with one
  DELETE. NO ACTION also lets the key be if it is back by then; RESTRICT
  does not. (First built with RESTRICT refusing at once; PostgreSQL checks
  both at the statement's end, so 9.42 made it so.)
- *Two transactions racing* (a parent deleted while a child referencing it
  is inserted) are caught by serializable validation: the insert read the
  parent's row.

**What depends on a foreign key:**
- *DROP TABLE of a referenced table* is 2BP01 unless CASCADE (new to DROP
  TABLE), which drops the foreign keys referencing it. Dropping the
  referencing table removes it from the referenced table's list.
- *DROP SCHEMA ... CASCADE* does the same for each table.
- *DROP COLUMN:* the table's own foreign keys on the column are dropped
  (as PostgreSQL's are). A column other tables reference is 2BP01 unless
  CASCADE.
- *DROP CONSTRAINT or DROP INDEX of a unique key* a foreign key needs, with
  no other unique key of those columns, is 2BP01. DROP CONSTRAINT ...
  CASCADE drops the foreign key too.
- *RENAME COLUMN, RENAME TO, SET SCHEMA and ALTER SCHEMA RENAME* rewrite
  the names in the other tables' rows (`renameFkCol`, `relink`).
- *A type change* of a column in a foreign key, on either side, is 0A000:
  drop the constraint first.

**Cost**, on a real file:

| Operation | Time |
|---|---:|
| 100K rows in 1000-row INSERTs, no key | 317 ms |
| Same, with a foreign key | 386 ms (0.7 µs a row, one lookup) |
| Delete of a parent row, no referencing table | 1.06 ms (the commit's fdatasync) |
| Same, 100K referencing rows, an index on the key's column | 1.05 ms |
| Same, 100K referencing rows, no index | 19.9 ms (every row read) |

As in PostgreSQL, an index on the referencing columns is the user's to
make.

**Checked** by `exec_fkey`:
- missing keys, present keys, NULLs, a unique key referenced, updates;
- deletes and key changes, referenced and not;
- a table referencing itself (a parent later in the statement, the whole
  table deleted); RESTRICT against NO ACTION;
- ADD over violating rows and then without;
- errors when made;
- the unique key, an index, a table and columns that keys need, with and
  without CASCADE;
- renames, moves, a schema renamed, with the keys checked under the new
  names;
- type changes refused;
- two sessions racing;
- a rollback;
- a dropped key's table no longer named;
- a reopen.

Planted, each caught:
- INSERT, UPDATE (either side) or DELETE not checked;
- the statement's end not checked, or a missing key let through there;
- NO ACTION as RESTRICT and the reverse;
- NULLs looked up;
- foreign keys or `refBy` not saved;
- the rows there not checked;
- a unique key always found;
- DROP CONSTRAINT, DROP INDEX or DROP TABLE of what a key needs allowed;
- a dropped table or key still named;
- renames not carried to the other table (table, column), caught once the
  test checked the keys while the columns were renamed;
- a type change allowed;
- a dropped column's own key kept, or a referenced column dropped;
- names, types or the referenced key not compared.

### 9.42 Foreign key actions

`ON DELETE` and `ON UPDATE` take CASCADE, SET NULL and SET DEFAULT too.
`SET NULL (cols)` and `SET DEFAULT (cols)` remain 0A000.

**At the statement's end, in order, as PostgreSQL's triggers run.** A row
deleted or changed in a referenced table queues what its key's going
does, in the statement's queue (`FkLater`):
- FK_DELETE: ON DELETE CASCADE;
- FK_SET: SET NULL, SET DEFAULT, ON UPDATE CASCADE, with the new key;
- FK_GONE: NO ACTION and RESTRICT, queued only when rows reference the key
  now;
- FK_MISSING, from 9.41: a key a row was written with that was not there.

`fkFinish` runs the queue from its front. For DELETE and SET it reads the
rows referencing the key *then* and deletes them (`delRow`) or sets the
key's columns (`updRow`). Those writes queue their own work behind, so
chains of tables and tables referencing themselves are followed to their
end without recursion.

Running last is what PostgreSQL does, and it decides what a statement
sees of its own rows:
- `DELETE FROM tree WHERE id IN (1, 2)` with 2 under 1 deletes both
  (DELETE 2) before the cascade looks;
- an UPDATE's rows are all written before a cascade sets the rows
  referencing them.

**A row an action writes is a row written.** The same code as UPDATE and
DELETE writes it (`updRow` and `delRow`, now shared):
- NOT NULL (SET NULL on a NOT NULL column: 23502);
- CHECK constraints;
- the primary key and unique indexes;
- the table's indexes kept;
- its own foreign keys: a SET DEFAULT whose default is not in the
  referenced table is 23503;
- the tables referencing it in turn.

Any error undoes the whole statement, cascades included.

**Tables loaded.** `fkTables` loads the tables a statement needs once:
those referencing a table an action writes, and their referenced tables,
followed until no new table is written.

**Cost**, on a real file: deleting 100 parents, which cascades to 10K
child rows through an index on the child's key column, took 57 ms. The
same rows deleted by hand in one transaction, without the foreign key,
took 51 ms.

**Checked** by `exec_fkaction`:
- ON DELETE CASCADE three tables deep, the child's index after;
- SET NULL, and on a NOT NULL column (all undone);
- SET DEFAULT, and a default not in the referenced table;
- ON UPDATE CASCADE from a primary key and a unique key, with the index
  read after;
- ON UPDATE SET NULL;
- a CHECK and a unique key violated by an action;
- a table referencing itself: a subtree deleted, two rows of one branch,
  a key renumbered;
- a cascade with NO ACTION on the same key (all undone);
- a rollback, and a reopen.

`exec_fkey` now checks RESTRICT against NO ACTION where they differ: a key
changed and back in one UPDATE.

Planted, each caught:
- the cascade not done, or not followed from the deleted rows;
- the rows an action writes not checked, or their foreign keys not;
- their indexes not kept;
- SET NULL setting nothing;
- ON UPDATE CASCADE keeping the old key;
- ON UPDATE taking ON DELETE's action;
- NO ACTION never letting a key back, RESTRICT letting it;
- the queue not run to its end;
- the tables actions write not followed;
- RESTRICT refusing at once.

### 9.43 Sequences, SERIAL and identity columns

**What is built.**
- `CREATE SEQUENCE [IF NOT EXISTS] name` with AS, INCREMENT [BY],
  MINVALUE / NO MINVALUE, MAXVALUE / NO MAXVALUE, START [WITH], CACHE,
  [NO] CYCLE and OWNED BY table.column / NONE. PostgreSQL's defaults and
  checks apply (22023).
- `ALTER SEQUENCE` with the same options and RESTART [[WITH] n].
  RENAME, SET SCHEMA and OWNER are 0A000.
- `DROP SEQUENCE [IF EXISTS] ... [CASCADE]`.
- `nextval`, `currval`, `setval(name, v [, is_called])` and `lastval`, with
  PostgreSQL's errors: 55000 for a value not yet defined in the session,
  2200H for a sequence at its end, 22003 for setval out of bounds. A name
  is written as PostgreSQL takes it: 'name', 'Schema.name', '"Quoted"', or
  'name'::regclass (regclass is text here).
- `serial`, `bigserial` and `smallserial` (and serial2/4/8).
- `GENERATED ALWAYS | BY DEFAULT AS IDENTITY [(options)]`, in CREATE TABLE
  and ADD COLUMN.
- INSERT's `OVERRIDING SYSTEM VALUE` and `OVERRIDING USER VALUE`.
- `DEFAULT nextval('s')` and other defaults calling sequence functions,
  evaluated for each row.

**A sequence** is a catalog row of its own, `"\x04" + key`, in the
relations' namespace: a table, an index or a sequence may not share a name
(42P07; `relExists` checks all three). The row holds its definition
(`Seq`), changed only by DDL in the DDL's transaction, and an id made when
it is created (the catalog version and the time). The id names its values,
so a sequence dropped and made again starts afresh.

**Its values are outside transactions, as PostgreSQL's.** A value taken in
a transaction that rolls back is not given again, and two sessions taking
values never conflict. Kept as an ordinary row, every two concurrent
inserts would conflict under serializable validation.

They are handed out from the store's memo (`Store.memoGet` and
`memoPut`: a map kept while the store is open, outside any transaction) a
block at a time. Before a block's first value is given, its last is
written (`seqWrite`) to the sequences' tree, in a transaction of its own.
The tree is made by `bootstrap`, its id under the catalog key "\x02seqs".
It is not the catalog, whose writes make the wire describe statements
again.

A block is max(CACHE, 32) values. Opened again, or after a crash, a
sequence goes on after the last block written, skipping what was left of
it, as PostgreSQL skips the values it logged ahead.

**The block's write does not wait for the disk** (`Store.commitAhead`,
new). It is applied and in the log ahead of every commit after it, and the
log is made durable in order. So no transaction using its values can be
durable before it is.

Measured: with a separate durable commit per block, inserting 100K serial
rows took 3.4 s against 0.31 s with ids given, one fdatasync per 32
values. Without waiting it takes 0.35 s, and 100K nextval calls take
159 ms (1.6 µs each).

A crash may let a value seen by a transaction that never committed be
given again. That is PostgreSQL's behaviour too: nothing durable used it.
`exec_seqcrash` crashes the simulated disk 120 times at random commits and
checks that every committed row is there and that no id is given again.

**Evaluation.** An expression is evaluated without the store, and a
sequence made earlier in the open transaction is seen only through that
transaction. So:
- the parser notes the names nextval, currval and setval calls give as
  literals (`Stmt.seqNames`);
- the statement's start (`execIn`, `bindSeqs`) looks them up in its
  transaction and keeps them in the memo under the session and a
  statement number;
- evaluation (`seqCall`) finds them there through `Env.seq`: the store's
  handle and the session's id. Transactions carry the id (`Txn.sess`, as
  they carry the search path).

A name not bound by its statement (a non-literal argument) is 0A000.
Where `Env.seq` is none (CHECK, index predicates, constant folding), the
functions are 0A000, so a call is never folded into a constant. currval
and lastval are per session, in the memo.

**Defaults.** `defaultsOf` now returns, per column:
- a value;
- its own sequence (`ColDef.seq`, the sequence's key: serial and identity
  columns);
- or a default calling sequence functions, evaluated per row (its names
  bound like a statement's).

`defAt` gives a row's default. A sequence's value is taken only for the
columns a row leaves out, as in PostgreSQL. INSERT's VALUES with DEFAULT,
UPDATE SET c = DEFAULT and the SET DEFAULT action go through it.
`ColDef.identity` and `ColDef.seq` are kept in the catalog's defaults
section (flag 4).

**Identity:**
- GENERATED ALWAYS refuses a value given (428C9) unless OVERRIDING SYSTEM
  VALUE;
- UPDATE may set it only to DEFAULT (428C9);
- OVERRIDING USER VALUE gives identity columns their defaults;
- SET DEFAULT and DROP DEFAULT of an identity column are 42601.

For a serial column they replace the sequence's default; the sequence
stays, owned by the column.

**A column's sequence** is made named `table_column_seq` (a number added
while the name is taken), in the table's schema, of the column's type,
owned by the column. It goes with its column:
- DROP TABLE and DROP COLUMN drop it (any sequence OWNED BY them);
- DROP SEQUENCE of it is 2BP01 unless CASCADE, which drops the column's
  default;
- renames of the table or the column change its owner;
- SET SCHEMA moves it with the table;
- ALTER SCHEMA RENAME moves every sequence in the schema;
- a type change of the column to a non-integer is 0A000.

**Not done:**
- ADD COLUMN with a sequence's default on a table with rows is 0A000
  (PostgreSQL rewrites the table).
- A non-owned sequence renamed or moved breaks the defaults naming it as
  text (PostgreSQL binds them by OID).
- RESTART takes effect at once, even if its transaction rolls back.
- nextval runs in READ ONLY transactions (PostgreSQL refuses).
- After ALTER SEQUENCE, the next value follows the last given in this
  store's life, else the last block written.

**Checked** by `exec_seq` (20 lines) and `exec_seqcrash`. Planted, each
caught:
- the block not written first, values not reloaded after it, blocks of
  one, a block written short (by the crash test);
- bounds not checked;
- cycling to the start, not the minimum (caught once the test's sequence
  started above its minimum);
- setval's is_called ignored;
- currval not kept, or kept per store not per session;
- a name's binding used by a later statement (caught once the test used a
  non-literal name);
- explicit values taking a sequence's value too;
- ALWAYS not enforced on INSERT or UPDATE;
- OVERRIDING USER VALUE ignored;
- column sequences not saved;
- owned sequences not dropped, their owner not renamed, not moved;
- DROP SEQUENCE of a column's allowed;
- sequences' names free for tables;
- ALTER INCREMENT going on from the block's end;
- ADD COLUMN serial on rows.

**Tests now run natively.** The test runner built every program through
gcc (its cached C build), which took several minutes for the suite and
timed out under load. With `LXL_NOCACHE=1` it calls `lxlc src -o out`,
the native backend: 10 s for the suite. The C build is for profiling only.

### 9.44 RETURNING

**What is built.** `INSERT ... RETURNING`, `UPDATE ... RETURNING` and
`DELETE ... RETURNING`, with a SELECT's item list: `*`, `t.*`,
expressions, aliases and subqueries. INSERT's every form takes it: VALUES,
DEFAULT VALUES and SELECT. An INSERT or UPDATE returns its rows as
written, so defaults, sequences' values and coerced types show; a DELETE
returns the rows as they were. The command tag stays the statement's
(`INSERT 0 n`), and clients read the count from it as before.

**How.** The parser's item list is now one function (`itemList`) for
SELECT and RETURNING. A DML statement keeps its RETURNING items in
`Stmt.items`, which it did not use. `returning` is now a reserved word, so
`INSERT ... SELECT x FROM u RETURNING id` does not take it as an alias.

In the executor, `itemCols` (SELECT's `selectCols`, generalized) resolves
the items over the table's columns. A `Ret` collects a row of values per
row written (`retAdd`, through `evalX`, so correlated subqueries work),
and `retRes` makes the result.
- UPDATE and DELETE already have a query over their table.
- INSERT builds one over its table only when it has RETURNING. Its VALUES
  are then resolved with no columns visible, as before, so `VALUES (t.v)`
  is still 42P01 and a plain INSERT keeps its old path. `insertOne` now
  returns the row it wrote.
- An aggregate in RETURNING is 42803 even on no rows.

A subquery in RETURNING runs before the statement's writes, unless it is
correlated. So it sees the table as the statement began, as PostgreSQL's
snapshot does.

**The wire.** Describe asked whether a statement was a SELECT or SHOW, and
sent NoData for anything else. libpq and Lexell's client then refused the
DataRows of an `INSERT ... RETURNING` ("a DataRow before a
RowDescription"). `lexdb_exec.returnsRows` now decides, for EXPLAIN too,
which had the same gap. `describe` gives RETURNING's columns.
`wire_client` reads serial ids back through the extended protocol.

**Measured** with 100K serial rows in 100 INSERTs: 0.34-0.37 s, and
0.37-0.39 s with `RETURNING id`. A 100K-row UPDATE: 189 ms, and 223 ms
returning two columns.

**Not done:**
- Data-modifying statements in WITH: `WITH x AS (INSERT ... RETURNING)
  SELECT ...` is a syntax error.
- `INSERT ... ON CONFLICT`.
- RETURNING's values are evaluated after all of an INSERT's rows are
  written, not as each is. Only a volatile function in RETURNING could
  tell.

**Checked** by `exec_returning` (13 lines) and `wire_client`. Planted,
each caught:
- UPDATE returning nothing, or the old rows;
- DELETE returning nothing;
- INSERT ... SELECT or VALUES keeping no rows;
- INSERT returning the values given rather than the row written;
- aggregates allowed (caught once the test had one on no rows);
- the rows flag lost;
- the tag replaced;
- `*` refused;
- RETURNING not described, at the wire or by `describe`;
- VALUES left unresolved with RETURNING (caught once the test had
  `VALUES (t.v)`).

### 9.45 COPY

**What is built.**
- `COPY table [(cols)] FROM STDIN`, `COPY table [(cols)] TO STDOUT` and
  `COPY (SELECT ...) TO STDOUT`.
- Options in both forms PostgreSQL takes:
  - `WITH (FORMAT text|csv, DELIMITER, NULL, HEADER, QUOTE, ESCAPE,
    ENCODING 'utf8', FREEZE, FORCE_QUOTE, FORCE_NOT_NULL, FORCE_NULL)`;
  - the old `[BINARY] [DELIMITER [AS] 'c'] [NULL [AS] 's'] [CSV [HEADER]
    [QUOTE ...] [ESCAPE ...] [FORCE QUOTE ...] [FORCE NOT NULL ...]]`.
- The lexer now takes `E'...'` strings, with their backslash escapes
  (`lexdb_sql.unescape`, shared with COPY's text format), for `DELIMITER
  E'\t'`.

**Checked against PostgreSQL 16 itself.** A scratch cluster
(`initdb` and `postgres` from /usr/lib/postgresql/16) ran the same psql
scripts as lexdb, and the outputs were diffed. They covered:
- every escape both ways;
- `\N` and NULL strings;
- CSV quoting, doubled quotes, other escapes and newlines in fields;
- headers, end markers and the FORCE options;
- the errors and their CONTEXT lines.

They agree byte for byte, except that a duplicate key's DETAIL stays in
lexdb's message, as it does for INSERT. A 1M-row dump through psql's
`\copy` is identical to PostgreSQL's.

**The text format.**
- Fields are split by the delimiter (tab by default).
- `\b \f \n \r \t \v`, `\ooo` octal and `\xhh` hex escapes; any other
  `\c` is c.
- NULL is the NULL string (`\N`), compared before the escapes are undone.
- A line `\.` ends the data.
- Written out: backslash, newline, carriage return, tab and the other
  control characters escaped, and the delimiter after a backslash.

**CSV.**
- Fields are quoted with QUOTE; inside quotes, ESCAPE (QUOTE by default)
  writes a quote or itself, and newlines are data.
- An unquoted field equal to the NULL string ('' by default) is NULL; a
  quoted empty field is an empty string.
- Written out, a field is quoted if it holds the delimiter, the quote or a
  newline, equals the NULL string, or is `\.` alone on its line.
- FORCE_QUOTE quotes a column's non-NULL values; FORCE_NOT_NULL never
  reads a column as NULL; FORCE_NULL reads a quoted NULL string as NULL.

**One statement.** The wire collects the client's CopyData until CopyDone,
then runs the COPY with it (`Session.copyIn`, `CopyInput`). It is then a
statement like any other: retried whole on a commit conflict, all or
nothing, inside a transaction block or not.
- `Session.run` of a COPY FROM checks the table and its columns and
  returns `Res.copy = COPY_IN`. The wire then sends CopyInResponse. A
  wrong table is an error before any data is asked for, as in PostgreSQL;
  psql then reads the rest of its script as the data it would have sent,
  as it does with PostgreSQL.
- Rows go through `insertOne`, as INSERT's do: defaults, sequences,
  NOT NULL, CHECK, unique keys, foreign keys (at the end) and indexes.
  Identity columns take the values given, as PostgreSQL's COPY does.
- Each value is turned to its column's type before the insert, so an
  error names the column: CONTEXT `COPY t, line 2, column n: "x"`.
- `DbErr` has a new `context` field, sent as the ErrorResponse's W
  field.
- A CopyFail is 57014. A message other than CopyData, CopyDone, CopyFail,
  Flush or Sync is 08P01. Flush and Sync in the middle are ignored, so the
  extended protocol's Sync, sent before the data, does no harm.
- COPY TO runs its query on a snapshot, as SELECT does. It returns
  `COPY_OUT` with the lines as rows, which the wire sends as a CopyData
  each between CopyOutResponse and CopyDone.
- A read-only block refuses COPY FROM (25006) and allows COPY TO.

**Measured** with 100K rows of three columns, in the executor:

| Operation | Time |
|---|---|
| 100 INSERTs of 1000 rows | 341-361 ms |
| COPY FROM | 167-202 ms |
| COPY TO | 61-92 ms |
| The same SELECT alone | 58-61 ms |

COPY TO's cost is its query's. Through psql with 1M rows (22 MB):

| | PostgreSQL 16 | lexdb |
|---|---|---|
| `\copy from` | 0.89 s | 1.84 s |
| `\copy to`, warm | 0.19 s | 0.66-0.72 s |

The difference is the executor's per-row cost: insertOne, about 1.7 µs a
row, and the scan, about 0.6 µs. That is item 11's work (batches), not
COPY's.

A profile of the server's dump (the C build) showed:
- a third of the samples were the runtime's idle threads spinning;
- the rest spread thin, libc's copying the largest share.

Each line was copied four times on its way out. The wire now writes
CopyData and DataRow messages straight into its output buffer. In an A/B
of three runs each, alternating, the dump went from 0.70-0.75 s to
0.66-0.72 s and a 1M-row SELECT from 1.02-1.04 s to 0.98-1.05 s: small,
but it is less code.

**Memory, measured.** Loading 1M rows peaked at 546 MB, and 251 MB were
left (the 128 MB cache and the allocator's). The transaction holds every
row's writes until it commits, as a 1M-row INSERT's would; the input
held whole adds 22 MB (its buffer a little more). Dumping 1M rows peaked
at 1006 MB, as `SELECT *` does (1055 MB): results are made whole before
they are sent.

**Not done:**
- Streaming: results sent as they are made, and a large COPY FROM
  committed in parts. Both are matters of the executor and the store,
  not COPY's syntax.
- The binary format (0A000).
- Files and programs on the server (0A000: psql's `\copy` reads and
  writes the client's).
- `WHERE`, `ON_ERROR`, `DEFAULT` and `HEADER MATCH`.
- Mixed newlines: lexdb takes `\r\n` and `\n` in one input, where
  PostgreSQL fixes the newline from the first line and refuses the other.
  A lone `\r` as the newline is not taken.
- A duplicate key's DETAIL is part of the message, for INSERT too.

**Checked** by:
- `exec_copy` (25 lines), through the session;
- `wire_copy` (10 lines), raw protocol messages both ways, in both query
  protocols;
- the psql scripts above, against PostgreSQL (not in the suite: they need
  the PostgreSQL server).

Planted (39), each caught but one:
- in the text format: escapes not undone; NULL compared after undoing
  them; `\r\n` kept; no end marker; header not skipped; the default
  delimiter a comma;
- in CSV: a doubled quote not one; a quoted newline (and `\r\n`) ending
  the record; an unterminated field accepted; FORCE_NOT_NULL or
  FORCE_NULL ignored; CSV's NULL not ''; the escape not the quote;
- in checks and errors: missing or extra data accepted; no column in the
  context; duplicate columns allowed; the binary format, files, or a long
  delimiter accepted;
- in writing rows: foreign keys not checked at the end; the client's
  CopyFail ignored; a read-only block allowing COPY FROM;
- in writing out: no escaping; the delimiter not escaped; quotes not
  doubled; commas not quoted; FORCE_QUOTE ignored; no header; the tag
  counting the header;
- in escapes: octal and hex read wrongly;
- at the wire: CopyData dropped; Sync ending the copy; no CopyDone; the
  column count wrong; the extended protocol's COPY not run; no CONTEXT
  field.

Seven survived the first run. The tests then gained a quoted empty field,
`\r\n` CSV, values holding the delimiter, quote and comma, a header's
tag, the delimiter `||`, and CONTEXT at the wire. The one left, a quoted
empty field read as NULL by its unquoted branch, is equivalent: an
unquoted field's raw and decoded text are the same.

### 9.46 Window functions

**What is built.** `f(args) OVER (...)`, `OVER name`, and `WINDOW name AS
(...)`.
- **Specs:** `[name] [PARTITION BY ...] [ORDER BY ... [ASC | DESC] [NULLS
  FIRST | LAST]] [frame]`.
- **Frames:** `{ROWS | RANGE | GROUPS} [BETWEEN] bound [AND bound]
  [EXCLUDE CURRENT ROW | GROUP | TIES | NO OTHERS]`, the bounds UNBOUNDED,
  n PRECEDING, CURRENT ROW and n FOLLOWING. RANGE offsets are over a
  number.
- **Ranking functions:** row_number, rank, dense_rank, percent_rank,
  cume_dist, ntile.
- **Value functions:** lag and lead (an offset and a default),
  first_value, last_value, nth_value.
- **Aggregates:** every aggregate (count, sum, avg, min, max, string_agg,
  bool_and, bool_or, the variances), FILTER included.
- **Where they may be:** in the select list and ORDER BY, over a grouped
  query's groups (`rank() OVER (ORDER BY sum(x))`, `sum(sum(x)) OVER ()`),
  in subqueries and CTEs.
- **ORDER BY ... NULLS FIRST / LAST**, which SELECT lacked: it is now in
  ORDER BY too. An index serves an order only when its NULLs go where the
  index keeps them.

**Checked against PostgreSQL 16 itself.** Two psql scripts (about 70
queries with the errors) ran on a scratch PostgreSQL and on lexdb, and
the outputs were diffed. They agree but for:
- the order of peers, which is unspecified;
- percent_rank and cume_dist, float8 in PostgreSQL. lexdb has no float
  type, so they are numeric, shown without trailing zeros (as float8 is
  shown); 8/9 is 0.8888888888888889 where float8 gives ...888;
- a duplicate key's DETAIL (as for INSERT, 9.45);
- PostgreSQL's LINE and position lines in errors.

`exec_window`'s expected lines for its queries are PostgreSQL's own
output (psql -At).

**How.**
- **The parser.** A call followed by OVER becomes `Call("#win", [Lit(i),
  the call])`, and its definition goes to `Stmt.wins[i]` (`WinDef`). The
  call is kept inside the `#win` so that the column has its function's
  name and type before planning (exprName, exprOid). Window calls are
  scoped to their SELECT, as subqueries are: wherever the parser moves
  `p.subs` it moves `p.wins`. WINDOW's definitions go to `Stmt.windows`.
  `window` is now reserved.
- **Planning (planSelect).**
  - `mergeWin` applies a named window by PostgreSQL's rules: `OVER w` is
    w as it is; `OVER (w ...)` takes its partitions and order, and may add
    an order and a frame.
  - Window calls are 42P20 in WHERE, GROUP BY, HAVING, JOIN conditions,
    window definitions, other window calls, and INSERT, UPDATE, DELETE and
    RETURNING; 42803 in aggregates.
  - The select list's and ORDER BY's `#win` become marks, so that a
    window's own aggregate is not taken for the query's. In a grouped
    query, a window's arguments, partitions and order then go through
    `collectAggs` (their aggregates become the query's) and
    `checkGrouped`.
  - At last the marks become slots after the aggregates: `#agg nAggs +
    i`. The evaluator reads a window value as it reads an aggregate, and
    `Env` is unchanged.
  - `winPlan` checks the function and its arguments, and makes the frame
    whole. The default is RANGE UNBOUNDED PRECEDING to CURRENT ROW, which
    without ORDER BY is the whole partition (every row a peer). It also
    refuses: DISTINCT and ORDER BY in a window aggregate (0A000, as
    PostgreSQL); RANGE offsets without exactly one ORDER BY column;
    GROUPS without ORDER BY; offsets with columns.
- **Running (execSel).**
  - The rows are kept first: a plain query takes the path that keeps its
    rows (`late`, with no early stop at LIMIT); a grouped one keeps the
    groups HAVING chose, with their aggregates (`WinRow`).
  - `winValues` then gives each row each call's value.
  - Then the select list, DISTINCT, ORDER BY and LIMIT run as before.
- **Per window (winValues and winPartition).**
  - Each row's partition key and ORDER BY values; the rows sorted by them,
    peers keeping their order. The sort is skipped when the rows already
    come in that order, and windows with the same partitioning and order
    share it.
  - Per partition: peer groups.
  - Ranking functions from the positions and groups.
  - lag and lead by position.
  - Frames by position (ROWS), by peer group (GROUPS) or by value (RANGE:
    a binary search for v - n and v + n, the direction and the NULLs'
    end taken into account; a NULL row's offset frame is its peers).
  - Aggregates through the query's own accumulators (`accumulate`,
    `finish`). A frame starting UNBOUNDED PRECEDING with no EXCLUDE only
    grows: one accumulator, its value made again only when its end moves.
    Other frames are summed afresh per row.

**Measured** on 1M rows (id, n = i % 97), through psql:

| Query | PostgreSQL 16 | lexdb |
|---|---|---|
| `row_number()` and `sum(id)` over `(PARTITION BY n ORDER BY id)` | 0.58 s | 2.4-2.7 s |
| `rank() OVER (ORDER BY n)` | 0.35 s | 1.82 s |
| `sum(n) OVER (ORDER BY id ROWS 10 PRECEDING)` | 0.34 s | 1.70 s |
| `lag(n) OVER (ORDER BY id)` | 0.30 s | 1.03 s |

The first lexdb version took 4.06, 1.99, 2.20 and 1.49 s.

In the executor with 300K rows, lag was 440 ms, against 176 ms for the
same subquery without it. A profile (the C build) spread the cost thin:
the sort's comparisons about 7%, the rest in allocation and copying.
Three changes brought it to 280-300 ms:
- skipping the sort when the rows are in order already;
- moving the kept rows instead of copying them;
- no partition key, and no slot copy, when there is none.

Sharing one sort between windows of one partitioning and order took the
first query from 3.77 s to about 2.5 s. What is left is the sort of 1M
rows by a closure, and the scan (9.45: about 0.6 µs a row): item 11's
work.

**Not done:**
- Inverse transitions: a sliding frame's aggregate is summed afresh per
  row, O(rows x frame).
- RANGE offsets over dates or intervals (lexdb has neither).
- Window calls in the ORDER BY of a UNION (0A000).
- Correlated subqueries in a window's arguments (an aggregate's
  `accumulate` evaluates without them).
- The window functions' float8 results (numeric here).

**Checked** by `exec_window` (33 lines: 28 queries' results as
PostgreSQL gives them, then errors and described types). Planted (39),
each caught:
- in ranking: rank as row_number; dense_rank as rank; cume_dist to the
  group's start; ntile's buckets even;
- in values: lag as lead; no default; last_value from the frame's start;
- in sorting: partitions not split; the partition left out of the sort;
  DESC ignored; NULLs' place ignored, in a window and in a SELECT's
  ORDER BY, and the window's default (DESC: first); no peers; the sorted
  check ignoring partitions; always taken as sorted; windows with other
  specs, or only another direction, sharing a sort;
- in frames: the default frame ROWS; a ROWS offset ignored; FOLLOWING one
  short; GROUPS by rows; RANGE's direction; RANGE's end not inclusive;
  EXCLUDE ignored; TIES excluding the row; the incremental value not made
  again; the `ROWS n PRECEDING` shorthand ending elsewhere;
- in planning: slots over the aggregates; a window's group aggregates not
  collected; an early stop at LIMIT; DISTINCT before the windows; WHERE
  allowed; bare `OVER w` refused; an ORDER BY override allowed; partition
  columns not read (9.31's narrowing); FILTER lost; percent_rank's type;
  window calls not scoped to their subquery.

Five survived the first run; the test then gained:
- a LIMIT with a whole-table window;
- WHERE's own message (the evaluator's has the same state);
- a bare `OVER w` with a frame;
- a window's DESC with its default NULLs;
- the `ROWS n PRECEDING` shorthand.

### 9.47 Batches, not rows: a prototype for aggregates

The user's idea (item 11 of 9.4), prototyped so that the two can be
compared: rows processed in batches of up to 1,024, not one at a time.

**Where it applies.** An aggregate query (with or without GROUP BY) over
one table read in primary key order: no join, no subquery, no index path,
no window calls, no DISTINCT or ORDER BY inside an aggregate. The parts
the batches evaluate:
- **Columns:** integers and booleans; columns of other types only for
  IS NULL, count and GROUP BY.
- **Expressions:** constants and parameters (each evaluated once), + - * /
  %, unary minus, the six comparisons, AND, OR, NOT, IS [NOT] NULL.
- **Aggregates:** count(*), count, sum, avg, min and max over integers,
  with FILTER.
- **Group keys:** one integer or boolean key, hashed as an integer; other
  keys as encoded strings.

Anything else, and any stored value of an unexpected kind (an integer
column holding another tag), returns before anything is done, and the row
path runs the query as before. `SET lexdb_batch = off` turns the batches
off; they are on by default. EXPLAIN ANALYZE shows them ("batches N").

**How** (`batchGroups` and the functions before it, at the end of
lexdb_exec.lxl).
- **Compiling.** The WHERE's conditions, the group keys and the
  aggregates' arguments and FILTERs are compiled into `BNode` trees.
- **Reading.** `fetchRaw` scans up to 1,024 stored rows. `bDecode` reads
  each row's tags once and writes the columns used into arrays (`BVec`:
  ints and NULL flags; values for other types). Large rows go through
  `rowOf`, as in the row path.
- **WHERE.** It is a list of the rows chosen, narrowed one condition at a
  time: one loop per node over the batch, not a tree walk per row. A
  comparison with a constant keeps the constant in a register. AND and OR
  evaluate their right side only on the rows the left leaves open, as
  `eval` does, so a division by zero in a row the left side excludes is
  not an error.
- **Groups.** Each chosen row's group is found or made, in the rows' order.
- **Aggregates.** `bAccum` adds each aggregate's values into plain
  integers per group, in one loop per aggregate. With no GROUP BY the
  running sum and count stay in registers.
- **The end.** The accumulators become the row path's `Groups` and `Acc`
  records, so `finish`, HAVING, the output and ORDER BY are unchanged.
  Sums overflow with 22003, as `arith` does.
- **Limits.** `tickN` counts a batch's rows for statement_timeout and
  turn-taking. Groups count toward max_statement_mem as in `addToGroup`.

**One difference.** A query whose rows hit two errors may report the other
one first, because each aggregate runs over a whole batch before the next.
In the row path every aggregate takes a row before the next row. Both
report an error. PostgreSQL does not promise which of several errors comes
first either.

**Checked.**
- **`exec_batch`:** 400 random aggregate queries, each run with batches
  off and on, must give the same results and errors.
  - **The table:** 1,800 rows (two batches and part of a third) with NULLs
    in every column; int, smallint and bigint, a boolean, texts; large
    rows of both kinds; a dropped column and an added one with a default.
  - **The queries:** arithmetic with division by zero and overflow, nested
    AND, OR and NOT, NULL constants, FILTER, and six kinds of GROUP BY.
  - **In a transaction:** 100 of them run inside a block whose own inserts,
    updates and deletes are not committed.
  - **Also:** overflowing sums, and the shapes left to the row path.
  - **The result:** all 400 the same. 338 ran in batches. 51 others were
    errors, which EXPLAIN ANALYZE cannot show. The rest read no rows or
    were max(id) read from the key's end.
- **The other tests.** Batches are on by default, so the suite exercises
  them too: about 1,400 queries in 27 test programs ran in batches, all
  with their expected results. exec_with's EXPLAIN ANALYZE line now shows
  "batches 5", for a LATERAL subquery's count, its outer value a
  parameter.

**Measured** in the executor, 1M rows of (id, g = i % 10, n = i % 97, v,
t), all in the cache. Best of five, in ms; the two rounds agreed within 4%:

| Query | Rows | Batches | Faster |
|---|---:|---:|---:|
| `count(*)` | 227 | 52 | 4.4× |
| 4 aggregates `WHERE n > 10` | 466 | 82–85 | 5.6× |
| `sum(v)` with three conditions | 450 | 93 | 4.8× |
| `GROUP BY g`, 3 aggregates | 479–491 | 124–129 | 3.8× |
| `GROUP BY n WHERE v % 2 = 0` | 465 | 99–102 | 4.6× |

**The hardware counters** per row (perf stat; 11 runs less 1, divided by
10):

| Per row | 4 aggregates, rows | batches | GROUP BY g, rows | batches |
|---|---:|---:|---:|---:|
| Instructions | 6,689 | 1,633 | 7,370 | 2,735 |
| Cycles | 2,191 | 404 | 2,221 | 593 |
| Instructions per cycle | 3.05 | 4.04 | 3.32 | 4.61 |
| Branch misses | 0.91 | 0.18 | 0.65 | 0.16 |
| Cache misses | 0.90 | 0.57 | 0.89 | 0.53 |

The user's reasons for batches were better branch prediction, prefetching
and use of the caches and registers.
- **Instructions.** Most of the gain is executing 3 to 4 times fewer:
  no tree walk, no tagged values and no allocation per row.
- **Instructions per cycle.** The rest: the CPU runs the tight loops
  better (3.0–3.3 rises to 4.0–4.6).
- **Branch misses.** Rare before (0.05–0.08% of branches; under one per
  row, about 15 of 2,200 cycles), so the predictor was not the limit.
- **Cache misses.** Below one per row either way, with the data in
  lexdb's cache. Prefetching would matter on rows read from the disk,
  which this did not measure.

**Against PostgreSQL 16**, the same table and queries through psql (the
results identical), best of five, in ms:

| Query | PostgreSQL, parallel | PostgreSQL, one core | lexdb rows | lexdb batches |
|---|---:|---:|---:|---:|
| `count(*)` | 15 | 26–27 | 233 | 54–56 |
| 4 aggregates `WHERE n > 10` | 26–27 | 59–60 | 468–470 | 88 |
| `sum(v)` with three conditions | 22 | 44–45 | 449–455 | 96–99 |
| `GROUP BY g`, 3 aggregates | 41–43 | 103 | 467–479 | 127–129 |
| `GROUP BY n WHERE v % 2 = 0` | 60–61 | 72–73 | 477–486 | 103–105 |

PostgreSQL runs these on two workers and its own process by default; on
one core (`max_parallel_workers_per_gather = 0`) it compares per core. The
row path was 7 to 18 times slower than PostgreSQL on one core; batches are
1.2 to 2.2 times slower.

**Where the batches' time goes now** (a native profile of the 4-aggregate
query):
- **Decoding: about 39%.** bDecode walks every row's tags.
- **The store's scan: about 37%.** It copies each entry out of its leaf
  (`scanIn`), then into the batch (`fetchRaw`), and loads the pages on the
  first run.
- **The evaluation itself: about 20%** (bEval, bAccum, and `checkedAdd`,
  which is a call, not inlined).

**What would come next:**
- **A scan that gives a leaf's entries in place,** not copied twice. Most
  of the store's 37%.
- **Decoding:** stop at the last column used; skip `partOf` for rows that
  cannot be large; decode nothing for `count(*)`.
- **More shapes:** filters and projections without aggregates (most of
  `SELECT ... WHERE`), joins' probe side, numeric columns (stored as text
  now, parsed per value), index paths.
- **The row format itself:** a page that keeps each column's values
  together would make decoding a copy. A storage format change, so the
  user's decision.
- **Parallel scans,** which PostgreSQL uses on these queries: the
  multi-core question.

### 9.48 The row format: options, and the fixed layout tried

The user asked (2026-11-10) for a better storage format, weighing inserts,
updates, ALTER and dropped columns, tried on the batches of 9.47.

**What the format costs now.** A row is its values in their places, each
a tag byte and its bytes:
- an integer takes 9 bytes;
- a numeric is stored as text and parsed on every read;
- a text is 5 bytes and its own.

Reading column k means walking columns 0 to k - 1. In the batches that
walk was the largest cost, at 39% (9.47).

**Three ways to go.**

- **A. A fixed layout per row,** as PostgreSQL's heap tuples but with
  every column's offset fixed:
  - a NULL bitmap;
  - each fixed-width column at a constant offset;
  - then the variable-length values' ends, and their bytes.

  A table keeps a list of layouts, and each row names its own. Reading a
  column is one load and a bit test, with no walk.
- **B. Column-grouped leaves (PAX).** A leaf page keeps its keys, then each
  column's NULL bitmap and values together. Decoding becomes nearly a
  copy, a scan reads only the bytes of the columns it uses, and a column
  of a page can be compressed.
- **C. A columnar cache.** The format stays. Decoded column arrays are kept
  per leaf version in memory, dropped when the leaf changes.

| | Tagged (now) | A: fixed layout | B: PAX leaves | C: column cache |
|---|---|---|---|---|
| Scan of a few columns | walks the columns before each | one load per column | a column's array, its bytes only | as B on a cached leaf, else as now |
| Point read | walks | direct | gathers from each column | as now |
| INSERT | encode, put | the same | shifts every column array of its leaf | as now, the leaf's cache dropped |
| UPDATE of a column | the row again | the row again (a fixed-width value could be patched in place) | one element; the leaf's version copied whole | as now, cache dropped |
| ADD COLUMN | no rewrite: older rows lack it (its default) | no rewrite: a new layout | no rewrite: a leaf without it gives the default | cache dropped |
| DROP COLUMN | no rewrite; every later row keeps a NULL in its place | no rewrite; a new layout without it, later rows smaller | no rewrite; a leaf converted when next written | cache dropped |
| Widening a type (int4 to int8) | no rewrite | a new layout: old rows keep the old width | per leaf | cache dropped |
| Other type changes | rewrite | rewrite | rewrite | rewrite |
| Space | a tag per value | a bit per value; a NULL fixed column keeps its bytes; int4 can take 4 | per-column compression possible | the cached copies in memory |
| The store | — | unchanged: values are still bytes | must know the schema; splits, merges, versions and conflicts by column | needs a leaf version to cache by |
| Risk | — | small: the encoder and decoders | large | moderate |

A changes only how a row's bytes are laid out. Everything else stays: the
B+tree, copy-on-write versions, per-row conflicts, large rows. B is the
better scan format, but it would rebuild the store. Section 0 keeps the
store free of the schema, and its write paths all work on whole entries.

**What was tried.** A, as an experiment beside the tagged form
(`LEXDB_ROWFMT=fixed`; the default stays tagged).
- **The row.** Byte 7 (no tag uses it), the place count, a kind byte per
  place, the NULL bitmap, the fixed part (8 bytes an integer, 1 a boolean,
  4 the end of a text's or numeric's bytes, 0 a dropped place), then the
  variable bytes.
- **What it stands in for.** The kind bytes stand for a layout number, so
  rows describe themselves without catalog changes. They cost as much
  space as today's tags; a layout number would take 2 bytes.
- **What stays tagged.** A row with a long text, or a value of another kind
  than its column's.
- **Readers.** Both layouts are read everywhere, so a table may hold both,
  as a migration would leave it.
- **Layouts.** Readers take a row's offsets from the table's current
  layout (made once per fetch of 256 rows, or per batch) when its kinds
  match; a catalog's layout number would do the same. A row of an older
  layout, from before an ALTER, makes its own.

**Checked.**
- **The suite in both layouts.** All 58 programs pass with every row
  written fixed (`LEXDB_ROWFMT=fixed`) and with the tagged default. That
  covers ALTER of every kind, COPY, the crash tests, the wire protocol
  and exec_batch's 400 random queries.
- **`exec_rowfmt`.** One table holds both layouts and three sets of places:
  rows written tagged, then fixed, old rows updated, a column added and
  one dropped between inserts. Another table gets the same statements,
  always tagged. 26 queries (aggregates, groups, filters, whole rows, long
  texts, numerics, DISTINCT) give the same results on both tables, with
  batches on and off.
- **Bugs found while building it.** Two showed up only in the batches:
  - the batch decoder took byte 7 for a tag;
  - an empty layout cache matched every row, which read the bitmap from
    byte 0.

**Writes, measured** (1M rows, in the executor; one run each):

| | Tagged | Fixed |
|---|---:|---:|
| INSERT ... SELECT 1M rows (5 columns) | 3,335 ms | 2,838 ms |
| INSERT ... SELECT 500K rows (20 columns) | 4,929 ms | 4,558 ms |
| UPDATE all 1M rows (an integer) | 2,449 ms | 2,343 ms |
| UPDATE 100K rows (a text longer) | 799 ms | 772 ms |
| Data file after the load | 59.6 MB | 63.2 MB |

Writes cost the same or a little less. The file is 6% larger only because
this experiment stores a kind byte per place. A 5-column row is 47 bytes
tagged and 50 here. With a 2-byte layout number it would be 46, and 30
with int4 kept in 4 bytes.

**Reads, measured.** Best of two rounds of five, in ms; "+b" is with
batches on:

| Query | tagged+b | fixed+b | tagged | fixed |
|---|---:|---:|---:|---:|
| `count(*)`, 5 columns | 52.8 | 40.6 | 226 | 206 |
| 4 aggregates `WHERE n > 10` | 86.2 | 75.5 | 475 | 449 |
| `sum(v)` with 3 conditions | 95.3 | 89.8 | 455 | 434 |
| `GROUP BY g`, 3 aggregates | 126.8 | 129.0 | 470 | 471 |
| `GROUP BY n WHERE v % 2 = 0` | 101.0 | 92.7 | 474 | 460 |
| 20 columns: `sum(c18) WHERE c17 > 50` | 96.2 | 63.4 | 347 | 347 |
| 20 columns: `GROUP BY c19`, 3 aggregates | 108.2 | 81.2 | 442 | 450 |
| 20 columns: `WHERE c1 = 3 AND c13 < 5` | 91.2 | 60.5 | 287 | 280 |
| 1,000 point lookups | 10.5 | 10.4 | 10.2 | 10.7 |

- **The 20-column table, with batches:** 1.3 to 1.5 times faster. Its
  columns used come late in the row, so the tagged walk was long.
- **The 5-column table:** 0 to 23% faster; its columns came early.
- **The row path and point lookups:** about the same. Their cost is
  elsewhere (making values, parsing and planning).

A check of a 2-byte layout number, taking only the place count in a
throwaway build, gave 2 to 10% more.

**Where the time goes now** (fixed layout, batches, native profile):

| Part | 4 aggregates | 20 columns, `sum(c18)` |
|---|---:|---:|
| The store's scan (`scanIn`, `fetchRaw`): copying each entry out of its leaf, then into the batch; `Store.load` 9 to 11% even when warm | 42% | 48% |
| Decoding (`bDecode`): now array writes with their bounds checks, and a batch's arrays made, more than reading the row | 33% | 39% |
| Evaluating and aggregating | about 20% | about 10% |

**What this says.**
- **A is worth having.** It is faster where the columns used come late,
  costs nothing on writes, and handles ADD and DROP COLUMN better than
  now: dropped columns stop costing space in new rows.
- **Making it real:**
  - a layout number per row, with each table's layouts in the catalog;
  - int2 and int4 at their width;
  - numerics in binary, not text parsed per read;
  - rewriting a table to the current layout when the user asks.
- **B's further gain is bounded by decoding's share,** a third of the batch
  time now, and costs the store's rewrite. Not now.
- **The next cost is the store's scan.** A scan that gives a leaf's entries
  in place, not copied twice, and a look at why `Store.load` runs on warm
  scans. Both help any format, and come before B or C would.
- **The batches decode every column for `count(*)`** (the planner's "all
  columns" for no column named). With no GROUP BY, only the columns of
  the conditions and aggregates are needed.
