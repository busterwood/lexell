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
server). Tests: `python3 lexell/tests/lexdb.py` (62 programs in
`tests/lexdb/run`, under `LXL_CHECK=1`).

    lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -o lexdb
    ./lexdb /path/to/data 127.0.0.1:5433 /path/to/sockets
    psql "host=127.0.0.1 port=5433 user=me dbname=lexdb"
    psql "host=/path/to/sockets port=5433 user=me dbname=lexdb"

Each address after the data directory is listened on: `HOST:PORT` over
TCP, a directory as a Unix socket named `.s.PGSQL.PORT` in it, or any other
path with a `/` as the socket file itself (9.54).

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
  default; a Unix socket gets the umask's mode (0755 under 022: only its
  owner can connect), not PostgreSQL's 0777.
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
  `LEXDB_CACHE_MB`, else a quarter of the memory since 9.54) replaces a count of nodes. Each loaded node counts an
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
  not COPY's syntax. (COPY TO is sent as it runs since 9.84.)
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
(`LEXDB_ROWFMT=fixed`; the default stayed tagged). 9.50 replaced it with
the real layout; its rows (byte 7) are no longer read.
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

### 9.49 Scans: the columns read, and pages loaded

The steps after 9.48 that need no decision of the user's (approved
2026-11-10), each measured on 9.48's tables (1M rows of 5 columns, 500K
of 20).

**Page loads on warm scans: none.** A profile over 30 runs put 9% of the
time in `Store.load`. Timing each run shows that it is the first run's:
- **The first run:** 1,873 ms.
- **Every later run:** 73 to 81 ms, with no loads.

A cold scan is thus 25 times a warm one: about 15,000 pages at about 120
µs each, read one at a time though the file was in the OS's cache.
Section 3 says the drive wants many reads in flight. The scan should read
ahead.

**Only the columns used.**
- **Which columns.** With no GROUP BY, an aggregate query can use a column
  only inside an aggregate (42803). So the batches read the columns of
  the conditions and aggregates alone, none for `count(*)`, where the
  planner's set said "all". With such a set, large rows are read in part.
- **Tagged rows.** Read up to their last place used, not to their end.

| Query, batches | tagged before | after | fixed before | after |
|---|---:|---:|---:|---:|
| `count(*)`, 5 columns | 52.8 | 38.7–39.9 | 40.6 | 41.2–41.5 |
| 4 aggregates `WHERE n > 10` | 86.2 | 72.7–73.0 | 75.5 | 73.8–74.0 |
| `GROUP BY g` | 126.8 | 113.2–114.2 | 129.0 | 123.7–125.2 |
| 20 columns: `sum(c18) WHERE c17 > 50` | 96.2 | 94.7–99.9 | 63.4 | 63.3–64.1 |

On the 5-column table the tagged rows now read as fast as the fixed ones,
since their columns used come first. The fixed layout's gain stays where
the columns come late.

**Leaves read in place.**
- **The store call.** `Store.scanLeaves` gives a callback each leaf's own
  key and value arrays, and the range of them in the scan's range, inside
  the store's lock (snapshot or live tree). The scan used to copy each
  entry into a list in the store, then again into the batch.
- **The batches.** `fillBatch` decodes rows from the leaves straight into
  the batch's arrays (`bRowInto`, no store call). It stops when the batch
  is full, then resumes at the first row not taken, with a new descent per
  batch.
- **Read tracking.** Each leaf's whole range is noted as read, for
  serializable transactions. A batch that stops inside a leaf notes a
  little more than it read, which is safe.
- **What goes the old way:**
  - a range the transaction has written itself, since only `scan` merges
    its writes;
  - a key lookup;
  - a value stored apart, read by the row path. Its key is where the
    batch resumes.

| Query, batches | tagged before | after | fixed before | after |
|---|---:|---:|---:|---:|
| `count(*)`, 5 columns | 38.7–39.9 | 25.1–27.1 | 41.2–41.5 | 28.4–28.8 |
| 4 aggregates `WHERE n > 10` | 72.7–73.0 | 61.9–64.3 | 73.8–74.0 | 62.1–64.2 |
| `sum(v)` with 3 conditions | 85.3–87.7 | 72.7–75.3 | 90.2–91.3 | 75.9–77.0 |
| `GROUP BY g` | 113.2–114.2 | 104.3–105.8 | 123.7–125.2 | 113.1–116.6 |
| 20 columns: `sum(c18) WHERE c17 > 50` | 94.7–99.9 | 83.4–87.1 | 63.3–64.1 | 44.8–45.8 |
| 20 columns: `WHERE c1 = 3 AND c13 < 5` | 83.3–86.1 | 74.1–75.7 | 62.0–62.6 | 45.5–46.8 |

**Checked.**
- **The suite.** All 58 programs pass in both layouts.
- **Planted bugs.** Nine were planted in the scan and its use; each was
  caught:
  - the end of the range ignored;
  - the transaction's own writes not looked for;
  - a snapshot reading the live tree;
  - resuming after the row not taken;
  - a row stored apart skipped;
  - the conditions' columns not read;
  - tagged rows read one place short;
  - reads not noted (twice: see below).
- **The bug that survived.** Reads not noted survived exec_batch until it
  gained a write-skew check. A transaction counts rows in batches, another
  inserts into that range and commits, then the first writes and commits:
  40001, with batches as without.

### 9.50 The row layout, for real

The user said yes (2026-11-10) to making 9.48's layout real. They then
said no table rewrite is needed and no old file need stay readable, since
lexdb is not released. So there is no `VACUUM FULL`, and the experiment's
rows (byte 7) are no longer read.

**The row.**
- Byte 8, then the row's layout number (2 bytes), then the NULL bitmap.
- Then the fixed part, per place: an integer at its column's width (8, 4
  or 2 bytes), a boolean in 1, a text or numeric as the end of its bytes in
  2, and a dropped place in none.
- Then the variable part: texts, and numerics in binary
  (`Decimal.toBin`, added to the library for this: 2 to 22 bytes, read
  back with `Decimal.fromBin`, no text parsed per read).
- Two-byte ends suffice: a row in the layout has at most 255 places, each
  text under 256 bytes (LONG), and numerics of at most 22.

**The layouts.**
- **Kept in the catalog.** Each table's catalog row ends with its layouts,
  each a kind per place, the last the current one.
- **A new one per schema change.** `encTable` adds one when the table's
  kinds have changed: a column added, dropped or retyped.
- **No rewrite.**
  - A row keeps its layout number.
  - ADD COLUMN, DROP COLUMN and a widening retype (int4 to int8, say)
    rewrite no row: old rows are read through their own layout.
  - A retype that does rewrite (`retype`) puts its rows in the new layout
    first (`syncLayouts`).
- **Read through the table.** `decTable` makes each layout's offsets once
  (`Table.lays`). A row's decoding is then an index into them, in
  `decRowNeed` and in the batches' `bRowInto`. `fetch`'s fast path for
  the experiment's rows is gone: every row goes through `rowOf`.

**The tagged form stays for** a row with a long text (encLong), a row of
over 255 places, a value that does not fit its place's kind, and
`LEXDB_ROWFMT=tagged`, kept to compare the two and to test the tagged
reader. The fixed layout is now the default.

**Row sizes,** computed from the two formats:

| Table | tagged | 9.48's experiment | the layout |
|---|---:|---:|---:|
| big: 4 int4, a 6-byte text | 47 | 50 | 28 |
| wide: 12 int4, 8 texts of 43 bytes in all | 191 | 196 | 113 |

**Speed,** 1M rows (big) and 500K (wide), warm, in ms, two runs each:

| Query, batches | tagged | the layout | PostgreSQL, one core | PostgreSQL, parallel |
|---|---:|---:|---:|---:|
| `count(*)` | 27.9–28.7 | 22.8–27.1 | 30.1–31.4 | 15.0–17.8 |
| 4 aggregates `WHERE n > 10` | 65.5–67.4 | 55.2–60.9 | 60.3–67.9 | 25.4–25.7 |
| `sum(v)` with 3 conditions | 77.7–78.1 | 68.5–71.0 | 46.1–50.1 | 19.9–21.5 |
| `GROUP BY g` | 105.1–109.3 | 96.3–105.5 | 103.7–112.0 | 38.9–45.7 |
| `GROUP BY n WHERE v % 2 = 0` | 82.0–84.4 | 71.6–77.6 | 77.8–83.2 | 58.4–68.7 |
| wide: `sum(c18) WHERE c17 > 50` | 85.8–86.1 | 41.2–42.2 | 38.3–42.4 | 19.8–25.0 |
| wide: `GROUP BY c19` | 99.4–102.3 | 57.5–59.6 | 65.8–67.6 | 28.7–30.5 |
| wide: `c1 = 3 AND c13 < 5` | 71.9–72.8 | 41.1–41.6 | 30.4–31.6 | 16.9–20.3 |

- **The layout against tagged:** 3 to 12% faster on the narrow table, and
  twice as fast on the wide one.
- **Loads:** 12 to 23% faster: 2.8 s against 3.6 s for 1M rows, 4.4 s
  against 5.1 s for 500K wide ones.
- **Unchanged:** updates and 1,000 point lookups (10.5 to 11.1 ms).
- **Against PostgreSQL 16 on one core** (`max_parallel_workers_per_gather
  = 0`; the same data and results, timed through psql, best of five):
  - lexdb is ahead or level on five queries;
  - it is behind on `sum(v)` with three conditions (1.4 times) and on the
    wide table's two-condition count (1.3 times).

  PostgreSQL's default runs two workers. lexdb has one thread, so against
  that it is 1.2 to 2.7 times slower.

**Checked.**
- **The suite.** All 58 programs pass in both forms.
- **exec_rowfmt** now also covers:
  - a widening retype, whose old rows keep 4-byte integers;
  - a smallint added;
  - the integer types' limits and numerics' edges;
  - a rewriting retype, int to numeric.

  It shows each table's rows by layout: five layouts and the tagged form,
  then one layout after the rewrite. Its 33 queries give the same results
  as an all-tagged copy, batches on and off.
- **Planted bugs.** Eleven were planted, and ten were caught: widths,
  offsets, layouts not stored or not placed, the layout number ignored,
  missing values, numerics as text, and retype not syncing.
- **The one that survived** is `encFixed`'s check that the table's last
  layout is its current one. No path now writes rows between a schema
  change and its layout's being made, so it is kept as a guard for
  future code.

### 9.51 Read-ahead

The user asked for read-ahead (2026-11-10) after 9.49 found cold scans
25 times slower than warm ones.

**Why cold scans were slow.** The data file is opened with O_DIRECT, so
every page read is a disk read: the operating system caches none of it. A
scan read one 4 KiB page at a time. A probe in C, on this machine's disk:

| O_DIRECT reads | per page |
|---|---:|
| random 4 KiB | 131 µs |
| sequential 4 KiB | 65 µs |
| 4 threads, 4 KiB each | 37 µs |
| sequential 64 KiB | 7.6 µs |
| sequential 256 KiB | 4.2 µs |

Larger reads cost far less per page than parallel small ones. The pages
a cold `count(*)` read were 98% each one after the last: checkpoints
write a tree's leaves in key order, with the internal nodes between runs
of about 60.

**The read-ahead.**
- **Which reads.** A forward scan (`scanIn`, and `scanLeaves` for the
  batches), on the live tree or a snapshot, that needs a leaf not in
  memory.
- **What it reads.** That leaf, and the leaves after it under the same
  parent that are not in memory and are on the pages right after it
  (`runAt`). They are read in one `pread` (`File.readPages`) and
  installed together (`loadAhead`).
- **How much.** A run starts at 8 pages and doubles with each read, up to
  64 (256 KiB). It is capped at a 32nd of the cache's budget, so a small
  cache does not evict a run before the scan reaches it.
- **Scans in parts.** The transaction keeps the run's size for its tree,
  so a scan its caller takes in parts (a batch at a time) keeps its long
  runs.
- **Not lookups.** A lookup reads its one page, as before.
- **Counted.** The store's stats count reads ahead and their pages.

**Cold runs,** the first query after opening the store, 1M and 500K rows
in the layout:

| Query | before | runs restarting per call | runs kept |
|---|---:|---:|---:|
| `count(*)`, batches | 886 ms | 213 ms | 127 ms |
| `count(*)`, row path | 1,171 ms | 455 ms | 351 ms |
| 20 columns: `sum(c18) WHERE c17 > 50`, batches | 1,354 ms | 236 ms | 177 ms |
| `sum(length(t)) WHERE id < 100000` | 172 ms | 97 ms | 88–97 ms |

Warm runs are unchanged. A cold batch scan is still 4 to 5 times its warm
time. Disk time is now about 4 µs a page, so most of what is left is
decoding pages and the scan itself, done one after the other. Reading
the next run while the last is decoded would overlap them. It needs a
task per scan, not done yet.

**Checked.**
- **store_ahead,** new: a tree of 8,000 keys, a few hundred rewritten
  after a checkpoint so their leaves move. Read from a cold cache, on the
  simulated disk and a real directory:
  - a scan, the leaves in place, a snapshot's scan, and a scan with the
    transaction's own writes give the model's entries in order, with most
    pages read ahead;
  - a scan in parts keeps runs over 16 pages on average;
  - lookups read none ahead.
- **Planted bugs.** Five were planted, and four were caught:
  - pages not checked to follow one another;
  - every page copied from the run's start (caught only on the real
    directory, which is why the test runs there too);
  - the run's size not kept between scans;
  - a snapshot's run taken from the wrong child.

  The survivor installs a run without its first page. The scan then
  reads that page again alone: one extra read, no wrong result.

### 9.52 Batches beyond aggregates: scans, top-N, texts

The user asked (2026-11-10) to extend the batches. Ten query shapes the
row path still ran, timed through psql against lexdb and PostgreSQL 16
(the same 1M-row table, warm, best of five), showed where it was
furthest behind:
- a filtered scan giving rows: 10 times behind;
- `ORDER BY ... LIMIT`: 35 times, the whole result sorted;
- `LIKE`: 13 times;
- an aggregate over a join: 8 times.

**The first table scanned in batches (`batchLevel`).**
- **What runs it.** A query's first level, when it is a forward scan of
  its table's key (not an index, nor key lookups only, nor correlated)
  and has a condition the batches evaluate. This covers queries giving
  rows, joins from their first table, and aggregates `batchGroups` does
  not take.
- **How.** Rows are decoded a batch at a time (`fillBatch`, in place);
  the level's conditions pick the rows over the batch. Only the rows kept
  become rows and go on through `tryRow`, as the row path's, which checks
  every condition again.
- **Any condition, in any order.** Every condition is pure and `tryRow`
  checks them all, so the batches may use any of them in any order.
- **Errors.** A batch on one of whose rows a condition gives an error is
  read by the row path from the batch's start. The row path tries the
  conditions in order and gives the error only if it reaches that row: a
  LIMIT may stop it first. A value a batch cannot hold falls back the
  same way.
- **Counting.** The rows a batch drops count as read, so EXPLAIN ANALYZE
  gives the row path's counts, with "batches N". A LIMIT stops the scan
  in the batch it ends in.

**Top-N.** `ORDER BY` with `LIMIT` keeps only the first `LIMIT + OFFSET`
rows.
- **Cutting.** The rows kept are sorted and cut when they reach twice
  that (`keepFirst`). The sort is stable and earlier rows stay first, so
  ties come out as the full sort gives them.
- **The bar.** A row that sorts at or after the last kept row is dropped
  on one comparison.
- **Memory.** `max_statement_mem` now counts only the rows kept, so
  `exec_limits`' LIMIT 5 sort is no longer stopped. One with LIMIT 15000
  is.

**Texts in batches.**
- **Comparisons.** A column of other values (texts, numerics) compared
  with a constant, on either side, is `ValCmp`. It runs eval's own
  `compare` per row, the constant made once.
- **LIKE.** `LIKE`, `NOT LIKE` and `ILIKE` with a constant pattern are
  `Like`.
- **A faster LIKE everywhere.** `likeMatch` turned the text and the
  pattern into code points on every call. A pattern of literal text and %
  only (no _, no escape character, not ILIKE) is now matched as bytes:
  its pieces at the start, at the end and in order between (`likePieces`).
  UTF-8 text matches a literal piece only at a character's start, so this
  gives what code points did. The row path uses it too.

**Results,** ms, through psql:

| Query | before | now | PostgreSQL, one core | parallel |
|---|---:|---:|---:|---:|
| `select id, v from big where n = 5` | 346 | 86–104 | 36 | 17 |
| `... where v > 90000` (100K rows out) | 399 | 173–200 | 51 | 49 |
| `where n < 50 order by v desc limit 10` | 2,017 | 261–274 | 57 | 25 |
| join, `where b.n = 7` | 361 | 94–102 | 34 | 17 |
| `count(*) where t like 'row1%'` | 580 | 79 | 43 | 20 |
| aggregate over a join, no condition | 1,209 | 1,200 | 149 | 56 |
| `count(distinct n), count(distinct g)` | 444 | 448 | 209 | 211 |
| `min(t), max(t)` | 382 | 384 | 71 | 29 |

The last three still take the row path:
- **The join's aggregate** joins by a key lookup per row: a million
  lookups into a 10-row table. PostgreSQL hashes the small side. That is
  the planner's choice, left for now (section 0).
- **DISTINCT aggregates, and min or max of a text,** are not batch
  aggregates yet.

**Checked.**
- **The suite.** 61 programs pass in both row forms.
- **exec_batch** gained:
  - 200 random queries giving rows, in six shapes: plain, LIMIT and
    OFFSET, inner and left joins, an aggregate over a join, DISTINCT.
    Some ran committed, some in a transaction with its own writes;
    batches on and off give the same.
  - Text conditions in its generator, on the aggregate path too.
  - A LIMIT reached before a row whose condition fails: rows, not the
    error.
  - EXPLAIN ANALYZE of a LIMIT, stopping in its first batch.
- **exec_topn,** new: 300 random `ORDER BY ... LIMIT ... OFFSET` queries,
  with ties, NULLs, `NULLS FIRST` and `LAST`, expressions, output columns
  by number, a join, and batches on and off. Each gives exactly the full
  sort's rows from OFFSET on, with and without a key to break ties.
- **exec_like,** new: 128 LIKE, NOT LIKE, ILIKE, ESCAPE and text-comparison
  queries over multi-byte, empty and NULL texts, both through the rows
  and through the aggregates. The expected lines are PostgreSQL 16's own
  output.
- **EXPLAIN ANALYZE.** `exec_join` and `exec_with` now show "batches 1"
  on scans that batch; their counts are unchanged.
- **Planted bugs.** 17 were planted, and 15 were caught.
  - **The scan:** rows dropped not counted; an error not left to the
    row path; the cursor not put back; emit's stop ignored (caught once
    the LIMIT check was added).
  - **Top-N:** the offset's rows; the comparison's direction; the bar
    from the wrong row; a cut one short.
  - **LIKE and comparisons:**
    - a middle piece found over the last;
    - the end not checked;
    - the escape character not looked for;
    - `_` taken as literal;
    - a constant on the left;
    - ILIKE as LIKE;
    - NULL texts.
  - **Not caught, and why:**
    - Another table's column taken as a batch column: the planner never
      puts one in the first level's conditions, so that check is a guard.
    - Trying the conditions after one that does not compile: harmless,
      as shown above, so the code now does it on purpose.
  - **Not planted:** keeping rows tied with the bar (`> 0` for `>= 0`)
    would only cost time, since the next cut drops them.

**Aggregates of values.**
- **What batches.** `batchGroups` takes `min` and `max` of a column of
  other values (texts, numerics) and `sum` and `avg` of a numeric one.
- **How.** Each group keeps a value, updated row by row in the scan's
  order with eval's own `arith` and `compare` (`bAccVal`), as `accumulate`
  does.
- **Ties.** Checking that showed the row path keeping the first of equal
  values. PostgreSQL keeps the last: for a plain numeric holding 1.0,
  1.00, 0.50, 0.5 and 0.500, its `min` and `max` are 0.500 and 1.00.
  Both paths now keep the last.
- **Time.** `min(t), max(t)` on 1M rows: 384 to 88 ms (PostgreSQL on one
  core: 71).
- **exec_batch** gained:
  - in its generator: `min` and `max` of texts, and the four aggregates of
    a numeric added after the rows, so its default is their missing value;
  - that tie case, with PostgreSQL's answers.
- **Planted bugs.** Of seven, five were caught:
  - max taken as min;
  - NULLs counted;
  - the count not given;
  - the first of equal values kept, in the batches;
  - the first of equal values kept, in the row path.

  The two not caught give the same results:
  - keeping the first of equal values in a column whose equal values are
    identical (a typed numeric, a text), before the tie case was added;
  - `sum` of a text in batches, which gives the row path's error through
    the same `arith`.

### 9.53 Decoding: the byte readers, and a column at a time

The user said (2026-11-10) that lexdb was still slower across the
benchmarks. A native profile of `sum(v)` with three conditions showed
decoding at about 70% of the time:
- `binary.readI32LEStr` alone: 28%;
- `bRowInto`: 28%;
- `layOf`: 8%.

**The byte readers.** `lib/binary` read an integer with a loop over its
bytes. The native code for that loop does all of this for each byte:
- takes and drops a reference to the string;
- copies the string's pointer and length;
- checks the index's addition for overflow, and the bounds;
- multiplies for the shift, and checks the shift's range.

That is about 35 instructions a byte. A micro-benchmark over the same
4 KiB, per value read:

| Read | ns |
|---|---:|
| `s[i]` in a plain loop (borrowed string) | 0.32 a byte |
| `readI32LEStr`, the loop | 7.5 |
| `readI32LEStr`, unrolled into statements | 2.8 |
| `readI32LEStr`, one expression | 2.7 |
| the expression written in place | 1.0 |

- **The change.** The library's 24 byte loops (readers and writers,
  strings and arrays) are unrolled, and its readers are single
  expressions. Same bytes, same results; the language suites pass.
- **What is left.** The rest of the 2.7 ns is the call, which the native
  compiler does not inline, and a reference to the string taken and
  dropped per call. Removing it is a compiler change (inlining small
  functions, no reference count on a borrowed string's index), the
  user's to decide.

**A column at a time (`bRunInto`).**
- **The run.** In a leaf, consecutive rows nearly always share a layout.
  `fillBatch` now takes the rows from one in the fixed layout up to the
  first in another layout (or not fixed, or the batch full).
- **The loops.** Per column used, the run has one offset, one kind and
  one NULL bit, so each column is a tight loop over the run's rows. An
  integer is read with the expression in place (8, 4 or 2 bytes), into
  the batch's array taken out of its record for the loop.
- **The rest.** Other rows (tagged, stored apart, another layout) go
  through `bRowInto` as before.

**Results,** in process, warm, ms (PostgreSQL 16 through psql, best of
five):

| Query | 9.52 | readers | + columns | PG one core | PG parallel |
|---|---:|---:|---:|---:|---:|
| `count(*)` | 23–27 | 22 | 14 | 30–31 | 15 |
| 4 aggregates `WHERE n > 10` | 55–61 | 49–51 | 33 | 60–68 | 25 |
| `sum(v)` with 3 conditions | 68–71 | 57–59 | 33 | 46–50 | 20 |
| `GROUP BY g` | 96–106 | 83–86 | 54 | 104–112 | 39–46 |
| `GROUP BY n WHERE v % 2 = 0` | 72–78 | 62–65 | 37–38 | 78–83 | 58–69 |
| wide: `sum(c18) WHERE c17 > 50` | 41–42 | 37–38 | 22–23 | 38–42 | 20–25 |
| wide: `GROUP BY c19` | 58–60 | 51 | 32 | 66–68 | 29–31 |
| wide: `c1 = 3 AND c13 < 5` | 41 | 33–34 | 21 | 30–32 | 17–20 |
| row path: `count(*)` of a subquery | 389 | 219 | 219 | | |

- **Against one core:** lexdb is ahead on all eight aggregate queries, by
  1.4 to 2 times.
- **Against PostgreSQL's two workers:** lexdb is ahead or level on four,
  and behind by 1.3 to 1.7 times on the other four.

**Checked.**
- **The suites.** 61 lexdb programs pass in both row forms; the 413
  native and 797 run tests of the language pass with the new library.
- **Planted bugs.** Seven were planted in the run decoder, and six were
  caught:
  - a run not ended at another layout;
  - int4 or int2 not sign-extended;
  - the NULL bit of the next place;
  - missing values not given;
  - a run longer than asked.

  The survivor reads a dropped place. That cannot happen: a used column's
  place is never a dropped one in any layout, since places are not
  reused.

**Point lookups,** after the batches. A profile of 500,000 lookups by key
in one process (10 to 11 us each) put:
- 30% in parsing;
- 25% in planning;
- 19% in the read.

Two changes:
- **A snapshot's get.** A statement's read was a one-key scan: a scan's
  setup for one entry. `snapGet` descends to the key's leaf in the
  snapshot once.
- **Reserved words.** `isReserved` looped over 56 words for each name the
  parser read. A `match` on the words is three times faster (89 to 28 ns
  a word). `isKw` reads the token in place, not a copy.

Together they take a lookup from 11.4 to 10.1 us in one process. Parsing
and planning are still about half: a statement cache keyed by its text,
or the extended protocol's prepared statements, skip both.

### 9.54 Unix sockets; the cache sized from memory

The user asked (2026-11-10) for Unix sockets.

**Addresses.** `lexdb DATADIR [ADDR ...]` listens on every ADDR:
- `HOST:PORT` over TCP; with none given, 127.0.0.1:5433 as before.
- A directory: a socket in it named as PostgreSQL names one,
  `.s.PGSQL.PORT`, with the first TCP address's port (its real one when
  given as 0; 5433 without one). `psql -h DIR -p PORT` and libpq's
  `host=DIR` find it.
- Any other path with a `/`: the socket file itself.

Each listener has its own accept loop (`lexdb_wire.acceptAll`), so
connections come in through any of them. A connection is the same over
either: the wire code's one TCP call, `setNoDelay`, fails harmlessly on a
socket.

**The socket file.**
- **Left by a server that is gone** (a SIGKILL): a connect to it is
  refused, and it is removed and made again.
- **A server still answers on it:** an error, not replaced.
- **Not a socket:** an error; it is never removed.
- **On stop** (SIGTERM, SIGINT): the files made are removed.

**The cache.** Measuring pgbench through the sockets showed lexdb's
latency unchanged (233 us) where PostgreSQL's halved. The cause was not
the socket: a Lexell echo server over a Unix socket answers in 55 us, as
a C one does. It was the cache. The server's 128 MB default holds about
two thirds of pgbench's 1M-row table. lexdb reads its data file past the
kernel's cache (O_DIRECT), so every miss went to the disk: 189,086 pages
read and 169,455 evicted in that run. PostgreSQL's 128 MB of shared
buffers is backed by the kernel's cache, which on this machine is most of
its 23 GB. The server now takes a quarter of `/proc/meminfo`'s MemTotal
(128 MB at least; `LEXDB_CACHE_MB` still decides when set).

**Results,** pgbench's select (`SELECT abalance FROM acct WHERE aid = :aid`,
1M rows), both through Unix sockets, cache warm, transactions/s:

| Mode, clients | lexdb, 128 MB | lexdb, cache warm | PostgreSQL 16 |
|---|---:|---:|---:|
| simple, 1 | 4,283 | 11,371 | 9,867 |
| prepared, 1 | 7,052 | 13,250 | 12,401 |
| simple, 8 | 19,881 | 22,398 | 64,038 |
| prepared, 8 | 24,824 | 29,614 | 79,836 |
| simple, 32 | 20,283 | 22,558 | 203,881 |
| prepared, 32 | 26,615 | 34,230 | 287,495 |

- **One client:** lexdb is ahead, by 15% simple and 7% prepared.
- **Eight and more clients:** PostgreSQL runs a process per connection on
  the 16 cores. lexdb runs its statements on one thread, which tops out
  at 22,000 to 34,000 statements/s. Running statements on several cores is
  a runtime change, the user's to decide.

**Checked.**
- **`wire_unix`.** Server and client (lib/postgres) in one process:
  - a TCP address and a directory;
  - rows written through the socket, read through TCP;
  - a second server on a served socket refused;
  - a stale socket replaced;
  - a plain file left alone;
  - a socket at a path of its own.
- **Planted bugs.** Six were planted, and all six were caught:
  - a live socket replaced;
  - a plain file replaced;
  - the directory's socket on 5433 whatever the port;
  - a stale socket kept;
  - one listener served;
  - a socket file not recorded for removal.
- **By hand.** The real server was tried with psql through the socket,
  SIGKILL then a restart over the stale file, a second server, a plain
  file, and SIGTERM (which removes the file).
- **The suites.** 62 programs pass in both row forms; the crash test
  passes 4 rounds.

### 9.55 io_uring again: not for sockets, not yet for files

*Corrected by 9.56: the socket result below measured a test client's
spurious wakeups under WSL2, not io_uring.*

The user asked (2026-11-10) whether now is the time to switch to
io_uring, since 9.17 measured it using less CPU.

**Where the SQL thread's time goes now.** pgbench's select with the cache
warm (no disk reads), CPU per select from `/proc`:

| Through, mode, clients | selects/s | user | system |
|---|---:|---:|---:|
| Unix socket, prepared, 32 | 35,135 | 13.0 us | 15.1 us |
| Unix socket, simple, 32 | 23,195 | 27.3 us | 16.1 us |
| TCP, prepared, 32 | 44,360 | 11.7 us | 10.7 us |
| TCP, simple, 32 | 33,491 | 18.5 us | 11.0 us |

System time is now about half of a prepared select (a third in 9.17),
because user time fell. The runtime registers a socket with epoll once,
edge-triggered, so a select costs three system calls (the read, the read
that finds nothing more, the write) and a share of an `epoll_wait`.

**Sockets measured** (`sockbench.c` in the scratchpad: a C server on one
thread answering 60-byte requests with 80 bytes, clients on other cores,
over a Unix socket; kernel time per message):

| Server | 1 client | 8 clients | 32 clients | messages/s at 32 |
|---|---:|---:|---:|---:|
| epoll, edge-triggered (as the runtime) | 25.4 us | 18.3 us | 18.1 us | 53,900 |
| io_uring, a receive then a send per message | 27.2 us | 30.6 us | 30.4 us | 32,500 |
| the same, with SINGLE_ISSUER, DEFER_TASKRUN or COOP_TASKRUN | | 30.3 us | 30.2 us | 32,700 |
| io_uring, a receive per message, send by `write` | | 30.2 us | 29.9 us | 32,600 |
| io_uring, multishot receive into provided buffers | 26.0 us | 29.9 us | 29.4 us | 33,600 |
| the same, send by `write` | 25.2 us | 26.3 us | 27.0 us | 36,200 |

- **On this kernel** (6.18, WSL2), io_uring's socket receive costs about
  10 us more per message than epoll, in every form tried: re-armed or
  multishot, with or without the setup flags.
- **The floor.** Even epoll in C spends 18 us of kernel time per message;
  lexdb's 10.7 to 16 us is at that floor already. Most of it is the
  socket's own work (copying, waking the client), which no interface
  removes.

**Files.** 9.17 still holds: io_uring would save at most 17 us of the SQL
thread's time per cache miss. Since 9.54 the server's cache is a quarter
of memory, so the measured workloads miss only when cold. A cold scan
reads a run of up to 64 pages in one `pread` (9.51), so its per-read cost
is shared.

**So: not now.**
- **Sockets:** io_uring would cost more here, not less.
- **Files:** it would matter only for data well beyond the cache, which
  none of the benchmarks are.

Two things would change this:
- **Bare metal** (section 8's open question). WSL2's virtual machine may
  make io_uring's receive dearer than a host kernel does; it should be
  measured there before being ruled out.
- **Working sets past the cache.** Then the file half of 9.17 applies
  again.

**What would pay instead.** One SQL thread tops out at 35,000 to 44,000
selects/s even if the kernel cost nothing: 13 us of user time a select
alone gives 77,000. Statements on several cores (a runtime change, the
user's decision) would also spread the sockets' kernel time over the
cores. That is what PostgreSQL does, with a process per connection, to
reach 287,000.

### 9.56 io_uring for sockets, measured properly: it wins

The user had read Jasny et al., "io_uring for High-Performance DBMSs: When
and How to Use It" (VLDB 2026, arXiv 2512.04859), doubted 9.55, and asked
whether the disk or the drive count was to blame. Neither: the socket test
touches no disk. `bench/sock/sockbench.c` (rewritten from 9.55's, now in the
tree) has one C server thread answering 60-byte requests with 80 bytes,
the server's CPU per message (its thread plus any SQPOLL thread) and IPIs
per message from `/proc/interrupts`.

**Batching was not the problem.** Every `io_uring_enter` carried a turn's
sends and re-armed receives for all connections (64 SQEs at 32 clients)
and waited in the same call. Neither POLL_FIRST, nor waiting for 4 or 8
completions, nor dropping the wait's timeout, changed the 31 us a message.
SQPOLL moved the work to its kernel thread and cost more in total (40 us).

**Wakeups are.** With clients that poll instead of sleeping, so no task is
ever woken on another CPU (8 clients, no work):

| | epoll | io_uring |
|---|---:|---:|
| clients sleep in `read()` | 18.7 us, 1.0 IPI | 30.6 us, 2.0 IPIs |
| clients spin | 2.8 us | 1.9 us (358,700 / 489,500 msgs/s) |

Every IPI costs the sender about 15 us under WSL2 (Hyper-V); on bare
metal about a microsecond. Pinning tasks to CPUs changed nothing, and a
server that polls 50 us before sleeping did not remove the second IPI.

**Where the second IPI comes from** (tracefs `ipi_send_cpu` with stack
traces; root was needed once). Both IPIs are sent by the server and both
wake the client:

- `sock_def_readable < unix_stream_sendmsg`: the reply. Expected.
- `unix_write_space < sock_wfree < unix_wfree`: the server's *read* of the
  request frees its skb, which returns send-buffer space to the client's
  socket, and Unix sockets then wake every sleeper on that socket,
  including a client blocked in `read()` (`autoremove_wake_function` does
  not look at the event mask). The client wakes for nothing and sleeps
  again. epoll without work replied before it slept again, so it showed one
  IPI; io_uring holds the reply until the turn's batch is submitted, and
  any real work does the same for epoll, so both then pay two.

A client waiting in `poll(POLLIN)`, as libpq and pgbench do, filters the
write-space wakeup out (`pollwake` checks the mask); TCP wakes for write
space only when a writer was blocked for it. 9.55's client was the worst
case and not a realistic one.

**Realistic clients** (32 clients, 13 us of work a message, about lexdb's
SQL time for a prepared point select):

| Through, client waits in | epoll | io_uring | io_uring saves |
|---|---|---|---:|
| Unix, `read()` (9.55's test) | 21,600/s, 44.6 us | 22,700/s, 43.6 us | 2% |
| Unix, `poll()` (as libpq) | 30,700/s, 31.7 us | 33,700/s, 29.4 us | 7% |
| TCP | 41,200/s, 23.6 us | 45,100/s, 19.9 us | 16% |

Over TCP the overhead beyond the 13 us of work falls from 10.6 to 6.9 us,
a third, with 23 SQEs per call. TCP costs the server less than Unix sockets
here, as lexdb's own numbers in 9.55 showed (10.7 against 15.1 us of
system time).

**Polling before sleeping.** One client at a time (`poll()` client, 13 us
of work): a server that polls up to 50 us before blocking goes from 13,500
to 20,800 round trips a second (74 to 48 us each), one IPI fewer, for 5 us
more CPU a message (the polling). Under load it changes nothing, since the
server never gets as far as sleeping.

**What applies from the paper here:** batched submission and the
completion model, DEFER_TASKRUN with a single issuer, and (for later, with
larger messages) registered buffers. Not here: IOPOLL and NVMe passthrough
(WSL2's disks are virtual, `io_poll` 0); SQPOLL (costs more in total);
`fsync` through io_uring (a worker thread, as 9.17 found: 78 us against 33).
More drives would matter only past one drive's IOPS, which lexdb's one SQL
thread is far from.

**So 9.55's "not for sockets" is withdrawn.** io_uring with a turn's
operations batched into the waiting call saves 7 to 16% of the server's
CPU a select here, and should save more where wakeups are cheap. The user
said to go ahead (2026-11-10) with: an io_uring event loop in the Lexell
runtime, beside epoll behind a switch, measured with pgbench against lexdb
over TCP and Unix sockets; then polling before sleeping.

### 9.57 io_uring in the runtime, behind a switch; polling before sleeping

Built as 9.56 proposed (the user: "go ahead", 2026-11-10), in the native
runtime (`compiler/native/rt.c`); the C backend's runtime keeps epoll.

**`LXL_URING=1`.** `net`'s `Conn.read` and `ReadHalf.read` now call one
runtime function, `lxllib_net_recv`, that parks until data (before, the
library looped over a non-blocking read and a readiness wait). Through the
ring it queues an `IORING_OP_RECV` into the caller's buffer and parks; the
loop's wait is one `io_uring_enter` that submits every queued receive and
waits for the first completion (SINGLE_ISSUER | DEFER_TASKRUN, so
completions are made only inside that call, on this thread). A turn of the
scheduler costs one system call for all its reads, where epoll costs a read
that finds nothing per socket plus an `epoll_wait`. Writes stay `send`.

- **Everything else stays with epoll.** The epoll set is watched from the
  ring by a multishot poll on its descriptor. A ring socket is in the set
  for hangups only (EPOLLRDHUP): with EPOLLIN or EPOLLOUT in it, every
  message, and every write-space wakeup (9.56), would also fire the set.
  A readiness wait (a write that found the buffer full, a timed wait) adds
  the bit for its duration with EPOLL_CTL_MOD, which reports readiness
  already there.
- **Stopping a read.** A read whose task is cancelled, or whose deadline
  passes, queues an `IORING_OP_ASYNC_CANCEL` and submits and reaps it at
  once: a receive waiting for data is cancelled inline, so the task goes
  on in the same turn as with epoll (`net_accept_cancel` checks the order).
  Data that arrived meanwhile is returned rather than lost; the buffer is
  never written after the call returns.
- **One ring per process**, made at the first socket; a `task.workers`
  child closes the parent's and makes its own.
- **Tests:** the library's 306, lexdb's 62 and the 797 of the conformance
  suite pass with epoll; the library's and lexdb's pass with `LXL_URING=1`
  too, and the library's with `LXL_URING=1 LXL_SPIN_US=50`.

**pgbench point selects** (`bench/sock/pgsel.sh`: 1M rows, prepared,
cache warm, 10 s runs, the server's CPU per select from `/proc`; averages
of two rounds, the server restarted per mode):

| Through, clients | epoll | io_uring | |
|---|---|---|---:|
| Unix, 32 | 34,160/s, 28.3 us | 38,950/s, 24.9 us | +14% |
| Unix, 8 | 28,880/s, 33.3 us | 30,620/s, 31.4 us | +6% |
| Unix, 1 | 13,350/s, 45.3 us | 12,780/s, 43.2 us | -4% |
| TCP, 32 | 42,560/s, 22.8 us | 45,720/s, 21.2 us | +7% |
| TCP, 8 | 29,910/s, 21.5 us | 29,430/s, 21.6 us | 0 |
| TCP, 1 | 5,050/s, 33.1 us | 4,660/s, 34.8 us | -8% |

Under load io_uring saves 7 to 12% of the server's CPU a select and gains
up to 14% throughput, as `sockbench` predicted (9.56). With one client
there is nothing to batch, and it is a little slower. Runs vary: a second
series gave io_uring at Unix/32 34,560 once against about 38,700 three
times.

One client over TCP manages only 5,000 round trips a second in both modes:
200 us each, against 75 us over a Unix socket. A C ping-pong over loopback
TCP shows the same (4,300 to 4,500/s), so it is WSL2's loopback TCP, not
lexdb.

**`LXL_SPIN_US=N`: polling before sleeping.** When the loop would sleep
with tasks waiting for sockets, it looks without waiting for up to N us
first (never past the nearest timer). 50 us, averages of two rounds:

| Through, clients | without | with 50 us |
|---|---|---|
| Unix, 1 | 13,340/s, 45 us | 19,370/s (+45%), 49 us |
| TCP, 1 | 4,500/s, 34 us | 3,400/s (-25%), 82 us |
| TCP, 8 | 29,300/s, 22 us | 31,100/s (+6%), 27 us |
| 32 clients | | no change |

It pays only when the next request comes within the window. Over a Unix
socket pgbench's next request is back in about 50 us, so the loop is still
awake for it; over WSL2's loopback TCP a round trip is 200 us, so the loop
spins 50 us for nothing and sleeps anyway, which costs CPU and, here,
throughput. A fixed spin is therefore not a default. The shape that would
be: adaptive, as KVM's halt polling (spin only while recent waits were
shorter than the window; grow the window when spinning succeeds, drop it
when the wait after spinning was long).

**Not done:**
- Writes through the ring. They usually complete at once, so the saving
  is one system call per batch at most; it needs buffers kept alive until
  completion, and ordering for partial sends.
- The C backend's runtime (`rt.h`): epoll only.
- io_uring as the default: it needs measurements where wakeups are cheap
  (bare metal), and the one-client case is 4 to 8% slower here.
- Adaptive spinning (above).
- Files through the ring (9.17).

### 9.58 Files through the ring; one server per data directory

Step 1 of the plan the user agreed (2026-11-10): io_uring in the runtime
for sockets and files where the kernel has it; files first.

**`fs.pread`, `pwrite`, `fdatasync`, `fsync`, `fallocate`** (new in
`lib/fs`): positioned I/O on a descriptor with C buffers (O_DIRECT's
aligned ones), a count or 0, or -errno. Each asks the runtime first
(`lxllib_file_op`): with a ring (`LXL_URING=1`, native backend) it queues
IORING_OP_READ, WRITE, FSYNC (DATASYNC for fdatasync) or FALLOCATE and
parks, not cancellably, until the completion; without one, or when no
other task could run (as `rt_blocking` decides), the call is the blocking
C call it was. `fallocate` falls back to `posix_fallocate` on EOPNOTSUPP.
lexdb's disk layer uses these instead of its own blocking externs. The
ring's completions now go to an `rt_uop` on the waiting task's stack (many
tasks read one file at once), receives included. Test: `fs_pread` (eight
tasks writing and reading back their regions of one file at once; short
reads at the end; EBADF), passing natively with and without the ring and
through C.

With the ring the helper pool never starts: the server ran 2 threads (the
second io_uring's own worker, for `fdatasync`, which the kernel always
hands to one) against 33.

**Measured** (`bench/sock/pgsel.sh`, `LEXDB_CACHE_MB=64` so most selects
miss, Unix socket, 8 s runs, averages of two rounds; the server's CPU per
operation from `/proc`, every thread):

| Selects, clients | epoll and the pool | io_uring |
|---|---|---|
| 1 | 6,980/s, 88.6 us | 8,340/s (+20%), 49.2 us (-44%) |
| 8 | 24,480/s, 55.6 us | 28,050/s (+15%), 34.3 us (-38%) |
| 32 | 26,660/s, 52.4 us | 30,730/s (+15%), 31.5 us (-40%) |

| Updates (a commit each), clients | epoll and the pool | io_uring |
|---|---|---|
| 1 | 760/s, 514 us | 800/s, 192 us (-63%) |
| 8 | 3,500/s, 172 us | 3,440/s, 84 us (-51%) |
| 32 | 7,150/s, 128 us | 6,990/s, 60 us (-53%) |

Commits are bound by the drive's flush (about 1.3 ms here), so their rate
does not change; the CPU does, most of it the pool's helpers (spinning
for jobs, futex wakes) and the eventfd's trips through the loop. A read
that misses costs the SQL thread one queued SQE instead of a job handed
to another thread.

The crash test (`tests/lexdb/crash.py`, 20 rounds of SIGKILL and SIGTERM
under load, killed again during recovery) passes with `LXL_URING=1` and
without.

**One server per data directory.** The first run of these benchmarks
started the next server while the last still wrote its shutdown
checkpoint (the script waited 0.3 s after SIGTERM); the new one met a
page in the middle of being written (`page 76: type 5`) and refused to
open. Nothing was damaged: copies of the directory opened in both modes,
and the balance column's sum equalled the commits the three servers had
logged (12,003 + 11,782 + 128,420 = 152,205). But two servers writing one
directory would corrupt it, and nothing stopped one. Now lexdb takes an
exclusive `flock` on `DATADIR/lock` before opening the store and exits 1
("in use by another lexdb") when it cannot; the kernel drops the lock
when the process ends, however it ends. `crash.py` checks that a second
server is refused. The script now waits for the old server to exit.

**Not done (steps 2 to 4):** why one client over a socket is 4 to 8%
slower through the ring (9.57); the ring as the default where the kernel
allows it, with both modes in the gate; socket writes through the ring.

### 9.59 Step 2 so far: the one-client gap; what to measure on bare metal

Step 2 of 9.58's plan: why one client over a socket is slower through the
ring (9.57: 4 to 8%). Unfinished; the user is moving development to a
machine running Linux directly on a dedicated NVMe (PCIe 3) drive, so the
rest is better measured there.

**Not the kernel's io_uring.** `sockbench`, one client waiting in `poll`,
13 us of work a message, three runs each (round trip in us):

| | epoll | io_uring | io_uring, POLL_FIRST |
|---|---|---|---|
| Unix | 74.1, 71.7, 70.7 | 76.9, 70.5, 73.4 | 79.1, 70.9, 73.1 |
| TCP | 256, 259, 237 | 280, 212, 215 | 232, 225, 220 |

No gap beyond the noise (about 5% over Unix sockets, 10% over TCP).

**In lexdb it is small and real over a Unix socket only** (pgsel.sh, one
client, warm cache, 6 s runs, three rounds, the server restarted for each):

| | epoll | io_uring |
|---|---|---|
| Unix, selects/s | 12,203, 12,247, 11,760 | 11,828, 11,637, 11,751 |
| Unix, server CPU a select | 50.0 us | 46.9 us |
| TCP, selects/s | 4,506, 4,010, 3,759 | 3,858, 4,093, 4,204 |

About 2.5 us more per round trip (of about 83), with 6% less CPU; over TCP
nothing beyond noise. Another series: epoll 12,922, 13,192, 13,031;
io_uring 12,828, 12,441, 12,809. `IORING_RECVSEND_POLL_FIRST` on the
receive (a throwaway build) did not help: 12,442, 12,579, 12,089. So the
2.5 us is in how the runtime meets the kernel on the wake-up path, not in
the receive's first attempt.

**Tracing it** (`bench/sock/trace1.sh`: tracefs, 0.3 s of one warm client,
system calls, wakeups and switches of both processes, io_uring events).
One io_uring capture so far, on a cold cache, so indicative only: per
request the server waits; about 14 us later pgbench's send queues the
receive's completion (`io_uring_task_add`); the server is running and has
completed it 25 to 28 us after that (the wake-up, about 15 us of it the
IPI under WSL2, 9.56); it then works about 34 us before queueing the next
receive. Two traps met: under WSL2 the distro's pids are not the kernel's,
so filter by process name; and warm the cache first (an epoll capture had
0.24 `pread`s a request). Tracing itself slows both modes (7,900 and
8,900 selects/s under it), so compare its intervals, not its rates.

**Next, on the new machine (bare metal, NVMe PCIe 3):**
1. `sockbench` with sleeping and with spinning clients, and IPIs a message:
   wakeups should cost about a microsecond, not 15 (9.56).
2. `pgsel.sh`, both modes, TCP and Unix, 1, 8 and 32 clients; again with
   `LEXDB_CACHE_MB=64`, and `QUERY=upd`. A consumer drive without
   power-loss protection still flushes in milliseconds (the paper's Figure
   9: 1.6 ms), so commits stay flush-bound.
3. The one-client gap, with `trace1.sh` in both modes; it may be gone with
   cheap wakeups.
4. `tests/lexdb/crash.py` with and without `LXL_URING=1`.
5. Then step 3 (the ring by default where the kernel allows it, both modes
   in `tools/gate.sh`) and step 4 (socket writes through the ring).
6. Possible there and not here: IOPOLL for the data file (O_DIRECT on
   ext4 with NVMe poll queues, `nvme.poll_queues=N` at boot; a second ring,
   since an IOPOLL ring cannot wait on sockets); the paper measured +21%.


### 9.60 On bare metal: wakeups are cheap; commits waited for the scheduler

9.59's list, run on the new machine: Linux 7.2 directly on the hardware,
16 CPUs, `/home` on btrfs over dm-crypt on an NVMe drive. gcc 16 there
builds `libgcc.a` with `-fno-plt`: its `__fixdfti` calls `__fixunsdfti`
through the GOT, which `gen_rtx.py` now relaxes to a direct call or jump,
as a linker does (`rtx.lxl` changes with the gcc anyway).

**`sockbench`, one client, 13 us of work a message** (round trip in us,
three runs each):

| | epoll | io_uring |
|---|---|---|
| Unix, client sleeping | 21.0 to 21.5 | 20.6 to 20.9 |
| TCP, client sleeping | 24.2 to 24.5 | 24.3 to 24.5 |
| Unix, client spinning | 18.4 | 18.4 to 18.6 |
| TCP, client spinning | 22.4 | 22.4 to 22.6 |

A wakeup costs a few microseconds where WSL2 took about 60 (71 to 74 us
over Unix, 237 to 280 over TCP, 9.59); 0.03 to 0.3 function-call IPIs a
message. Loopback TCP is no longer ten times slower than a Unix socket.

**`pgsel.sh`** (6 s runs; warm cache 3 rounds, the others 2; averages):

| | epoll | io_uring |
|---|---|---|
| Warm, Unix, 1 client | 86,100/s, 8.3 us | 79,400/s, 8.6 us |
| Warm, Unix, 8 and 32 | ~150,000/s, 6.6 us | ~170,000/s, 5.9 us |
| Warm, TCP, 1 | 62,000/s, 9.4 us | 63,100/s, 9.3 us |
| Warm, TCP, 8 and 32 | ~114,000/s, 7.4 us | ~120,000/s, 7.0 us |
| `LEXDB_CACHE_MB=64`, Unix, 32 | 118,000/s, 16.9 us | 99,000/s, 9.2 us |
| Updates, Unix, 1 | 1,310/s, 358 us | 1,260/s, 182 us |
| Updates, Unix, 32 | 21,700/s, 33 us | 17,600/s, 26 us |

Five to seven times WSL2's rates. The warm io_uring rows at 8 and 32
clients are rounds 1 and 2: the third came in 15% low in every row
through the ring (144,000 and 137,000 over Unix); the one-client rerun
below did not repeat it.

**The one-client gap (step 2) is the wakeup.** `trace1.sh`, both modes,
warm: a request's round trip is 14 us with epoll, 16 through the ring.
The server's own part is 1 us shorter through the ring (no `read`), but
with epoll it is woken inside pgbench's `send`, and through the ring 2 us
later: the receive's completion is queued as task work
(`io_uring_task_add`), and the waiting thread woken from that. Polling
before sleeping closes it (one client, 5 s, three rounds each):

| | epoll | io_uring | epoll, 20 us | io_uring, 20 us |
|---|---|---|---|---|
| Unix | 85,600/s, 8.4 us | 79,400/s, 8.6 us | 95,700/s, 10.4 us | 96,400/s, 10.3 us |
| TCP | 61,200/s, 9.7 us | 63,100/s, 9.2 us | 72,000/s, 12.5 us | 72,700/s, 12.4 us |

Here, unlike WSL2, spinning pays: the next request comes back within
20 us. It costs about 25% more CPU a select, so it is still not a
default; the adaptive shape of 9.57 is.

**Commits through the ring were slower: the scheduler, not the kernel.**
With 32 clients, updates ran at 17,600/s through the ring against 21,700
with epoll. Traced (fdatasync and pwrite, or the ring's FSYNC and WRITE,
2 s at 32 clients):

| A flush | epoll and the pool | io_uring |
|---|---|---|
| fdatasync | 638 us | 632 us |
| the log write | 37 us | 147 us |
| a flush's end to the next's start | 64 us | 231 us |

Two causes. First btrfs: an O_DIRECT write to a copy-on-write file must
allocate, so it cannot be issued without blocking and the ring hands
every log write to an io-wq worker (`io_uring_queue_async_work ... WRITE,
hashed queue`); zeroing a segment ahead (`openSeg`) does not help on a
copy-on-write file system. A data directory with copy-on-write off
(`chattr +C` on the empty directory) removes that: the write is issued
inline, and both modes commit faster (epoll 26,400/s at 32 clients).
But the ring still lagged (19,900/s), its write still taking 160 us.

Second, and the main one: the loop looks at the ring only when it would
sleep or every 64 task switches (`rt_next`). With 32 sessions runnable it
never sleeps, so the log write's SQE waited up to 64 switches to be
submitted, and its completion up to 64 more to be reaped; then the
woken writer queued behind every runnable session. The helper pool starts
a job at once on another thread. Now a file operation is submitted when
it is queued if other tasks are runnable (one `io_uring_enter`, as the
pool's futex wake was one system call), and a file operation's
completion wakes its task to run next (`rt_wake_front`). Measured
(no-COW directory, Unix, 6 s, two rounds):

| Updates, 32 clients | /s | CPU an update |
|---|---|---|
| epoll and the pool | 26,200 | 25.7 us |
| io_uring before | 19,900 | 17.6 us |
| submitted at once | 21,300 | 17.7 us |
| polled every 8 switches with a file operation out | 22,400 | 17.6 us |
| both | 23,600 | 17.7 us |
| at once, completions first | 25,600 | 17.7 us |
| all three | 25,800 | 18.0 us |

The third and fourth together are the change: the same commit rate as
epoll for 30% less CPU, the write back to 49 us. Polling more often adds
nothing beyond noise and is not kept. At 8 clients every variant is
within noise of the others (6,100 to 6,800/s). Cache-missing selects
are unchanged by it (`LEXDB_CACHE_MB=64`, Unix, 32 clients: 100,000/s at
9 us before and after).

**Cache-missing selects with many clients: one thread's limit.** At 32
clients the ring serves 100,000 selects/s at 9 us of server CPU each,
epoll and the pool 118,000 at 17 us. The ring's 9 us are all on the one
loop thread, which is then busy (0.9 of a CPU); the pool spreads its
`pread`s over helper threads. More throughput through the ring needs more
than one loop (task.workers), not a cheaper read.

The crash test passes, 20 rounds each, with and without `LXL_URING=1`.

**A cancelled read and the end of the stream.** `net_read_cancel` failed
natively with `LXL_URING=1` on Linux 7.2, with the runtime as committed
too: its reader, parked in a receive, is cancelled as its scope ends, and
the scope's end also closes the peer. Here the receive's completion with
the end of the stream (res 0) comes before the cancel's, and the runtime
returned any res >= 0 as data that arrived meanwhile, so the reader saw
`read 0`, not the cancellation. Bytes must be returned (they were taken
from the socket); the end of the stream need not be (it consumes
nothing, a later read sees it again). Now only res > 0 is. The kernel
itself completes a cancelled receive with -ECANCELED (a liburing probe).

**The tests on this machine.** Two library tests differ for reasons of
the machine, not the runtime: `tls_memory` (OpenSSL 3.6 appends "; record
layer failure" to the bad-MAC error) and `tz_zones` (the system's tzdata).
lexdb's tests hit the conformance runner's 20 s compile limit: gcc 16
takes 24.5 s for one test's 4.5 MB of C; with a longer limit all 62 pass,
with and without the ring.

**Next:**
1. Step 3: the ring by default where the kernel allows it, both modes in
   `tools/gate.sh`. The commit regression is gone; the one-client gap (2
   us over a Unix socket) remains, and adaptive polling is its answer.
2. Adaptive polling before sleeping (9.57's shape).
3. Step 4: socket writes through the ring.
4. IOPOLL for the data file needs ext4 or a raw partition (this
   `/home` is btrfs over dm-crypt) and `nvme.poll_queues` at boot.
5. Should lexdb set copy-on-write off (`FS_NOCOW_FL`) on its data
   directory when it makes it on btrfs? It gives up btrfs's checksums for
   those files; lexdb's pages carry their own CRC32C.

### 9.61 Copy-on-write off for the data directory; the gate on gcc 16

Decided (the user, 2026-11-11: what lexdb checks itself the file system
need not check too). At start, after making DATADIR, lexdb sets
FS_NOCOW_FL on it (`FS_IOC_GETFLAGS`, `FS_IOC_SETFLAGS`), so files
created in it are written in place: on btrfs an O_DIRECT write then need
not allocate, io_uring issues it inline, and the flush is cheaper (9.60:
commits at 32 clients 21,700/s to 26,400 with epoll). btrfs keeps no
checksums for such files; lexdb's pages carry CRC32C, and its log
records theirs. A file that already has data keeps copy-on-write (the
kernel converts only empty files), so an existing directory gains it for
new log segments only. Other file systems refuse the flag (ext4,
EOPNOTSUPP; tmpfs, ENOTTY) and every failure is ignored. Checked on
btrfs with both backends: the directory, `lock`, `data.lxdb` and
`log.1` all have it.

The gate's failures on this machine are fixed in the tests: `tls_memory`
compares the first of OpenSSL's reasons (3.6 adds "; record layer
failure"); `tz_zones` no longer has EST5EDT, which distributions build
differently (a link to America/New_York, with EWT in 1942-45, or the old
rule-based zone; `gen_tz.py` still draws its instants, so the other
zones' stay as they were); and the conformance runner allows 90 s to
compile (gcc 16 takes about 25 s for a lexdb test).

### 9.62 Cache-missing selects: where the loop's time goes; reads to io-wq when busy

9.60 left the ring behind epoll and the pool on cache-missing selects with
many clients (`LEXDB_CACHE_MB=64`, Unix, 32 clients: 101,000/s against
120,000), though it costs half the CPU a select: all of it is on the one
loop thread, which is then the bottleneck.

**Profile** (`perf record -g` of the server, 4 s at 32 clients through
the ring; lexdb's own functions named from `LXL_NATIVE_MAP`):

| The loop thread | |
|---|---:|
| lexdb (SQL, decoding, the wire), spread thin: the top function 2.8% | 55% |
| reads from the drive: submitting (iomap, btrfs, the block layer, plug flush) | 16% |
| the drive's completions: interrupts and softirqs on this CPU | 8% |
| `sendto` (replies) | 10% |
| receives (requests) | 7% |
| system call entry and exit, the ring's wait | 2% |

Within the reads, pinning the buffer's pages costs 0.5% and the file's
lookup (fget, fput) 0.6%: registered buffers and files, the obvious
io_uring step, would save about 1%, and are not done. The I/O scheduler
(kyber, this distribution's default for NVMe) costs 2.4%, dm-crypt 2.7%.

**Reads to io-wq when the loop is busy.** A read queued while other tasks
are runnable now carries IOSQE_ASYNC: an io-wq worker issues it, so the
block layer's work, and the drive's interrupt, which comes on the CPU that
issued the read, leave the loop thread; the completion reaches it as task
work as before. With nothing else runnable the read is issued inline, the
quicker way for the one waiting. Unix, `LEXDB_CACHE_MB=64`, 6 s, two
rounds (server CPU from `/proc`, every thread, io-wq's included):

| Selects, clients | epoll and the pool | ring | ring, async when busy | ring, async always |
|---|---|---|---|---|
| 1 | 28,700/s, 38 us | 29,900/s, 13 us | 29,900/s, 13 us | 28,800/s, 14 us |
| 8 | 102,000/s, 18.5 us | 103,400/s, 9.0 us | 120,300/s, 9.5 us | 63,000 and 132,000 |
| 32 | 119,900/s, 17.3 us | 101,400/s, 9.2 us | 126,100/s, 9.6 us | 121,000 and 133,000 |

The ring now leads at every client count, at half the CPU. Always async
was erratic and is not kept. Writes async too (the log's) did not help
updates (21,000 to 24,600/s at 32 clients against 23,500 to 26,000 with
reads alone) and are not kept.

Tests: the quick gate passes; the library's natively with `LXL_URING=1`;
lexdb's; the crash test in both modes.

### 9.63 Checkpoints write runs of pages, several at once; the log's flush not linked

A commit writes no pages: its records join the log writer's batch, and
the writer writes each batch as one frame with one write, then one
fdatasync (at 32 clients about 15 commits a flush). Pages go to the data
file at checkpoints, and `finishCheckpoint` wrote them one at a time,
each write waited for before the next was queued: one write in flight,
a round trip (40 to 50 us on NVMe) per page.

**Now** (`writeCheckpointPages`): the pages sorted by number, in runs of
consecutive pages (at most 64, 256 KiB), each run one write
(`File.writePages`, one aligned buffer), 16 runs at once (tasks in a
scope). A checkpoint may hold every page in the cache (a quarter of the
memory by default), so it is never encoded whole: only the runs being
written are, at most 16 * 64 pages (4 MiB, and as much again in the
writes' aligned buffers), where encoding them all first would have held
a second copy of the checkpoint. A page listed twice is written once, as
its later entry (as the writes in order left it).

Measured (the shutdown's checkpoint, time from SIGTERM to exit, two
rounds; the no-COW directory):

| | after a 1M-row insert (contiguous pages) | after 30 s of random updates, through the ring |
|---|---|---|
| a page at a time (before) | 1.17, 1.18 s (epoll 1.02, 1.03) | 0.26, 0.26 s |
| runs, one at a time | 0.33, 0.42 s | 0.18, 0.32 s |
| runs, 16 at once | 0.31, 0.32 s | 0.16, 0.13 s |
| 32 at once | 0.31, 0.32 s | 0.14, 0.19 s |
| 64 at once | 0.32, 0.31 s | 0.14, 0.14 s |

Contiguous pages gain from the runs; scattered ones from the writes in
flight too. 32 and 64 are no faster than 16. Update rates do not change
(the table here is about 3,000 leaf pages, so its checkpoints are small).

**Not done: the log's flush linked to its write.** A `pwriteSync` (the
write and an fdatasync linked with IOSQE_IO_LINK, one submission, the
writer woken once) was built and measured: a log write to the next took
591 us against 597 (traced, 32 clients), and update rates were within
noise. Since 9.60 the writer runs 13 us after its flush completes, so
the round trip linking saves was a few microseconds. Not kept.

**Not done: I/O straight from lexdb's arrays.** A vectored write (or
read) of lexdb's own page arrays would save the copy into an aligned C
buffer, but O_DIRECT here needs 4 KiB-aligned memory (dm-crypt's
`dma_alignment` is 4095; btrfs reports no STATX_DIOALIGN), and arrays
are not page-aligned. With aligned page arrays from the runtime it could
be done, but it is not worth it: by the profile's call stacks (9.62) the
read path's own buffer and copies cost under 1% of the loop thread
(`File.read`'s aligned buffer 0.40%, `Store.load`'s copies 0.23%, the
body string's allocation 0.20%); the rest of `malloc`, `memcpy` and
`free` (4.6% together) is the SQL engine's. And a cached node cannot
keep its page without a copy: a string's bytes follow its reference
count in one block, so a page's bytes cannot start 4 KiB-aligned with
the count before them unless each page wastes most of another 4 KiB, or
strings change representation.

### 9.64 Adaptive polling before sleeping, by default

9.60 left one client over a Unix socket 7% slower through the ring than
with epoll (the wakeup's 2 us), and a fixed 20 us of polling before
sleeping closing it, and more, for about 25% more CPU a select. A fixed
window is wrong when requests come further apart: the loop looks for
nothing, then sleeps anyway.

**First try: grow and shrink** (KVM's halt polling): after a sleep, the
window doubles (from 10 us, to at most 50) when the next event came
within the maximum, and halves (to 0 below 10 us) when it did not. Busy
clients kept the gain, but paced ones (`pgbench -R`, one client, Unix,
6 s) still paid for it, since pgbench's gaps are exponential and a share
of them is always short:

| One paced client, server CPU a select | no polling | fixed 20 us | grow and shrink |
|---|---|---|---|
| 20,000/s (gaps of 50 us on average) | 8.8 us | 17.8 us | 12.6 us |
| 5,000/s (200 us) | 11.6 us | 26.5 us | 14.3 us |
| 1,000/s (1 ms) | 28.5 us | 43.7 us | 33.4 us |

Latency did not improve with any of them (0.054 to 0.056 ms at
20,000/s): a paced client sends on its schedule, not on the reply.

**Kept: the window that catches most gaps.** The loop remembers its last
32 idle gaps (from finding nothing to run to the event that ended it,
whether found by polling or after sleeping), and polls for the least
multiple of 10 us, up to 50, that would have caught 80% of them; when
none would, it does not poll. A client waiting on its reply (gaps of
about 15 us, every time) gets a window of 20 us; scattered or long gaps
get none.

| | no polling | fixed 20 us | adaptive |
|---|---|---|---|
| paced 20,000/s, CPU a select | 9.20 us | | 9.18 us |
| paced 5,000/s | 11.31 us | | 11.71 us |
| paced 1,000/s | 32.21 us | | 29.30 us |
| warm, one client, Unix (ring) | 79,300/s, 8.7 us | 95,500/s, 10.4 us | 94,300/s, 10.6 us |
| warm, one client, TCP (ring) | 62,600/s, 9.4 us | 72,200/s, 12.4 us | 71,800/s, 12.5 us |
| warm, one client, Unix (epoll) | 85,200/s, 8.5 us | | 94,000/s, 10.6 us |
| warm, 8 and 32 clients | | | unchanged (the loop never idles) |
| `LEXDB_CACHE_MB=64`, one client (ring) | 29,900/s, 13.1 us | | 30,700/s, 14.6 us |
| updates, 1 to 32 clients (ring) | | | unchanged (gaps are flushes, ~600 us) |

With it, one client is faster through the ring than with epoll without
it, in both transports. It is now the runtime's default (native backend,
both modes): `LXL_SPIN_US=N` polls a fixed N us, `0` never, `aN` adapts
up to N us.

### 9.65 io_uring by default; both modes in the gate

Step 3 of 9.58's plan. With 9.60 to 9.64 the ring is ahead of epoll and
the helper pool everywhere measured on this machine, at less CPU:

| | epoll and the pool | the ring |
|---|---|---|
| warm selects, 8 and 32 clients, Unix | ~148,000/s, 6.8 us | ~170,000/s, 5.9 us |
| warm selects, one client, Unix (with 9.64's polling) | 94,000/s, 10.6 us | 94,300/s, 10.6 us |
| `LEXDB_CACHE_MB=64`, 32 clients | 119,900/s, 17.3 us | 126,100/s, 9.6 us |
| updates, 32 clients | ~25,500/s, 26 us | ~25,800/s, 18 us |

So the native runtime now uses the ring unless `LXL_URING=0`. Where the
kernel will not set one up (before 6.1, `kernel.io_uring_disabled`, a
seccomp filter as containers have), it falls back to epoll and the pool
as before: checked by running lexdb under a systemd unit with
`SystemCallFilter=~io_uring_setup` (no ring, the 32 helpers, queries
answered). The C backend's runtime stays with epoll.

`tools/gate.sh quick` runs the native library tests a third time with
`LXL_URING=0`, so both modes are gated; the other native steps now run
through the ring. The benchmark scripts' `epoll` mode sets `LXL_URING=0`.

Left of the plan: step 4, socket writes through the ring.

### 9.66 Socket writes through the ring: measured, not kept

Step 4 of 9.58's plan. A send through the ring saves a system call only
if the task does not wait for it: the reply's bytes copied, a SEND queued
(MSG_WAITALL), the write returned at once, and the SEND submitted with
the next receive in the loop's next `io_uring_enter`. A prototype did
that for writes up to 64 KiB, one SEND in flight a socket (a second
write waited for the first), errors kept for the socket's next write.
Warm selects (`pgsel.sh`, 5 s, two rounds, the ring and 9.64's polling):

| | sendto | queued SEND |
|---|---|---|
| one client, Unix / TCP | 94,500 / 71,200/s | 93,800 / 70,400/s |
| 8 clients, Unix | 170,300/s, 5.87 us | 172,800/s, 5.77 us |
| 32 clients, Unix | 167,100/s, 5.96 us | 171,200/s, 5.83 us |
| 32 clients, TCP | 120,000/s, 6.93 us | 123,900/s, 6.79 us |

2 to 3% with many clients, a little worse with one. Most of `sendto`'s
cost (10% of the loop thread, 9.62) is the socket's work, copying into
the peer's buffer and waking it, which the ring does on the same thread
when it submits; only the system call's entry and exit go. A real
version needs per-socket ordering of queued sends, a cap on queued bytes
(backpressure when the peer does not read), errors reported later, the
queue drained at exit and across `task.workers`' fork, write deadlines
(`writeFor`, `writeStalled`), and a completion that cannot be confused
with a later socket on the same descriptor. That is not worth 2 to 3%.
Not kept; writes stay `sendto`.

That ends 9.58's plan: the ring is the default (9.65), with file I/O
through it (9.58), commits keeping up (9.60), reads off the loop when it
is busy (9.62), checkpoints in runs (9.63) and adaptive polling (9.64).

### 9.67 Against PostgreSQL 18, on bare metal

`bench/sock/vspg.sh`: lexdb and PostgreSQL 18.6 on the same machine (16
CPUs, NVMe, btrfs over dm-crypt), the same data and Unix sockets, both
data directories with copy-on-write off. PostgreSQL: shared_buffers 4GB,
otherwise its defaults (fsync and synchronous_commit on); lexdb: its
defaults (io_uring, adaptive polling). Both hold all the data in memory.
Each server is a transient systemd user service and its CPU is its
cgroup's, PostgreSQL's backends included. Three rounds of 10 s; the five
aggregate queries' results are the same on both (checksummed).

| pgbench, 1M rows | lexdb | PostgreSQL | lexdb / PG |
|---|---|---|---|
| point selects, 1 client | 94,700/s, 10.5 us | 80,100/s, 8.5 us | 1.18x |
| point selects, 8 clients | 173,900/s, 5.7 us | 489,800/s, 11.4 us | 0.36x |
| point selects, 32 clients | 172,300/s, 5.8 us | 710,900/s, 14.6 us | 0.24x |
| updates, 1 client | 1,663/s, 92 us | 1,669/s, 87 us | 1.00x |
| updates, 8 clients | 6,690/s, 35 us | 6,900/s, 60 us | 0.97x |
| updates, 32 clients | 26,140/s, 17.5 us | 26,810/s, 50.7 us | 0.98x |

| Query on t (1M rows), ms, best of 5 | lexdb | PG, one core | PG, parallel |
|---|---:|---:|---:|
| `count(*)` | 13.9 | 19.4 | 11.4 |
| 4 aggregates `WHERE n > 10` | 36.8 | 58.9 | 25.9 |
| `sum(v)` with three conditions | 42.2 | 46.1 | 21.8 |
| `GROUP BY g`, 3 aggregates | 47.4 | 86.4 | 36.4 |
| `GROUP BY n WHERE v % 2 = 0` | 35.1 | 59.3 | 33.9 |

| Load, 1M rows (INSERT ... generate_series) | lexdb | PostgreSQL |
|---|---:|---:|
| acct (2 ints) | 1.49 s | 0.87 s |
| t (4 ints and a text) | 2.52 s | 1.45 s |

- **A select's CPU:** lexdb's is half PostgreSQL's under load (5.7 us
  against 11.4 to 14.6); with one client PostgreSQL's is lower (8.5
  against 10.5, of which about 2 us is lexdb's polling).
- **Throughput with many clients** is PostgreSQL's: a process per
  connection on 16 CPUs (at 32 clients about 10 CPUs busy), against
  lexdb's one loop thread. One client: lexdb 18% ahead.
- **Commits** are the drive's: the same rate within 3%, lexdb at a third
  of PostgreSQL's CPU an update with many clients.
- **Aggregates:** ahead of PostgreSQL on one core on all five (1.1 to 1.8
  times); against its default two workers behind on four (1.2 to 1.9
  times), level on one.
- **Loads:** PostgreSQL 1.7 times faster.

### 9.68 A read-only replica on the same machine: design, and the page cache

The user asked whether read-only transactions could run beside the SQL
thread. Lexell has no threads (reference counts are not atomic and the
allocator is per process), so the step is a second process: one master
(read-write) and one read-only replica, on the same machine and data
directory, with clients choosing at connection time (as PostgreSQL's
`target_session_attrs=read-write` / `read-only`). The user's worry is
that the page cache would be held twice. This note measures that cost
and designs around it. Nothing is built yet.

**What the cache costs now** (the 9.67 data: acct and t, 1M rows each;
a cache of 4 GB, so everything read stays; RSS of the process):

| | RSS |
|---|---:|
| started | 3 MB |
| acct read whole | 62 MB |
| acct and t read whole | 146 MB |
| their pages on disk (live; estimated: 2.0M of the 3.0M keys on valid leaf pages, the rest in free pages) | about 62 MB |

Decoded nodes take about 2.4 times their pages: per key, a `str` for
the key and the value, and the arrays (`nodeCost`: 64 bytes a key plus
the entries, 9.13). A second process caching the same data would double
the larger number.

**Misses served by the kernel's page cache.** Variant: the page file
opened without `O_DIRECT` (log segments unchanged), so a page not in
lexdb's cache is copied from the kernel's page cache, which every
process on the machine shares. pgbench point selects on acct, 8 s
(CPU from `/proc`, every thread of the process):

| page file, lexdb cache | 1 client | 8 clients | RSS |
|---|---|---|---:|
| O_DIRECT, 4 GB (now) | 95,600/s, 10.4 us | 173,800/s, 5.7 us | 62 MB |
| buffered, 4 GB | 95,300/s, 10.5 us | 173,600/s, 5.7 us | 62 MB |
| buffered, 32 MB | 72,300/s, 13.8 us | 110,000/s, 10.4 us | 26 MB |
| buffered, 8 MB | 68,500/s, 14.5 us | 99,400/s, 11.7 us | 11 MB |
| O_DIRECT, 8 MB (from the drive) | 53,500/s, 21.8 us | 97,800/s, 13.2 us | 11 MB |

- Buffered costs nothing when the cache holds everything.
- With 8 MB nearly every select misses its leaf. A miss from the kernel
  costs about 4 to 6 us of CPU: the read, CRC, decode and install. The
  kernel's part (`filemap_read`, the copy) is under 5% of the profile.
- These reads still went through io_uring's worker threads (the profile
  shows `io_worker_handle_work`). `IOSQE_ASYNC` is set when other tasks
  are runnable (9.62), which suits the drive. A page already in the
  kernel's cache would complete inline without it, so a buffered page
  file should not force it. Not yet measured.

So the kernel can be the one shared copy, in page form (1x), with a
small decoded cache in each process in front of it. Today one process
holds everything decoded (2.4x). One master and one replica with small
private caches would take less memory than one server does now, at
about 5 us a miss.

**How the replica gets its state: base and delta.** The page file is
written only by checkpoints, and a page is never written in place
(4.1). The log holds rows' after-images (4.6). So the replica:

- **reads the master's pages,** as of a checkpoint (its base: the roots
  from that checkpoint's meta page). Its cache is keyed by page number
  and holds only clean pages. A page stays valid across checkpoints
  until it is freed and reused, so most of the cache survives each one;
- **keeps the rows changed since its base** in a delta per tree: key to
  versions, (batch, value or deletion), sorted by key. A read-only
  transaction is a snapshot at a batch: the newest delta version at or
  below it, else the base tree. Scans merge the two, as transaction
  blocks already merge their own writes over a snapshot (`ownRange`);
- **never writes a page, never checkpoints, and has no dirty nodes.**
  The delta takes about the log since the last checkpoint (at most
  `ckptBytes`, 32 MB, plus the map's overhead).

Rejected: replaying into a B+tree of its own, as recovery does. The
replica could not checkpoint that tree into the master's file, and its
dirty nodes would grow without end. Adopting the master's checkpoints
would need the two trees to split identically, which nothing promises.
Also rejected: a shared buffer pool in shared memory (PostgreSQL's
shared_buffers). That needs atomics and an allocator in shared memory,
and Lexell has neither.

**The stream** (a Unix socket in the data directory, master to replica):

- **Frames,** as written to the log, sent after their flush, so the
  replica only ever sees durable batches. A replica that is behind, or
  just started, reads the segments on disk with recovery's `readFrame`,
  then switches to the socket.
- **Checkpoint n done:** its meta page (roots, the batch it covers B_n),
  and the pages it frees.
- **Back from the replica:** the batch it has applied, and the oldest
  base a live snapshot uses.

**Checkpoints.** A new snapshot uses base n with the delta above B_n.
One begun earlier keeps base n-1. When none is left on n-1, the replica
drops the delta at or below B_n, evicts the pages checkpoint n freed,
and acknowledges. The master reuses those pages, and the log segments
before B_n, only after the acknowledgement. This is the rule it already
keeps for its own snapshots (pages free once no live snapshot reads
them), and LMDB's reader table, across a process boundary. When a
checkpoint rewrites many leaves, the replica rereads them. If checkpoint
pages are written through the kernel's cache, those rereads are copies,
not drive reads. Whether buffered checkpoint writes cost anything has to
be measured.

**Isolation.** A snapshot on the replica sees a prefix of the master's
commit order at a batch boundary, the same thing `durableSeq` gives on
the master (9.16), so read-only transactions there are serializable.
They can lag: a client that commits on the master and then reads on the
replica may miss its own commit by one batch on the socket. For clients
that need it, a session setting could make the replica ask the master
for its durable batch and wait until it has applied it: one round trip
on a local socket. A write on the replica fails with SQLSTATE 25006, as
on a PostgreSQL standby.

**Applying a batch** costs parsing its records and one sorted insert
per row. That is far below the master's work for the same commit:
updates cost the master 17.5 us each, mostly SQL.

**Processes.** `task.workers(2, ...)`: worker 0 the master, worker 1 the
replica, each with its own listener (one replica needs no
`SO_REUSEPORT`). The supervisor restarts either one:

- **The replica crashes:** the master releases whatever it held for it
  when the socket closes.
- **The master crashes:** it recovers on restart. The replica holds only
  flushed batches, so it reconnects from its applied batch. It keeps
  serving meanwhile, falling further behind.

**Elsewhere:**

- LMDB: one writer and readers in other processes share a read-only
  mmap of a copy-on-write B+tree. A reader table pins old pages.
- SQLite WAL: readers find newer page versions through a shared index
  over the log (here, the delta).
- Aurora replicas: they apply the log to the pages they have cached and
  read the rest from shared storage at the right position.
- PostgreSQL standbys: they replay pages into their own copy, normally
  on another machine.

**Next, in order:**

1. A buffered page file without `IOSQE_ASYNC` for its reads, and
   buffered checkpoint writes: measure a miss and a checkpoint.
2. The delta and base read path in one process, tested against the
   store (the same rows at every snapshot).
3. The stream, the acknowledgements, and the replica process.
4. Measure: point selects on the replica beside updates on the master,
   with memory, against one server.

Later, perhaps: search pages in their disk form instead of decoding
them, so the cache is 1x. The pages would be read into memory lexdb owns,
not mapped. A read-only mmap of the page file avoids the worst objection
to mmap in a database (the kernel writing pages back behind the log's
back: Crotty, Leis and Pavlo, "Are You Sure You Want to Use MMAP in Your
Database Management System?", CIDR 2022). The others remain:
- a fault stalls the thread, and here that is every session's;
- an I/O error arrives as SIGBUS;
- eviction is the kernel's, with TLB shootdowns.

Reads through the page cache give the same one shared copy without any
of these.

### 9.69 The page file through the page cache (step 1 of 9.68)

- **`LEXDB_PAGES=buffered`** (`Options.bufferedPages`) opens the page
  file without `O_DIRECT` (`Fs.openBuffered`; `File.Real` carries the
  flag). Log segments stay `O_DIRECT`. Pages, CRCs, writes and flushes
  are unchanged: a checkpoint's pages are written, then `fdatasync`ed,
  then the meta page. The default stays `direct` until the replica uses
  this.
- **Reads tried inline.** The runtime set `IOSQE_ASYNC` on every read
  issued while other tasks were runnable (9.62), so a page the kernel
  held was copied by an io-wq worker and woke the loop from there. Now
  `fs.pread` lets the kernel try inline: from the page cache it is a
  copy, and a miss goes to io-wq by itself. The new `fs.preadDirect`
  (op 5) keeps the flag for `O_DIRECT` descriptors, and lexdb uses it
  for them.

**Point selects on acct** (1M rows; the page file in the kernel's cache;
CPU per select from `/proc`; 8 s each):

| page file, lexdb cache | 1 client | 8 clients | 32 clients | RSS |
|---|---|---|---|---:|
| direct, 4 GB | 96,000/s, 10.4 us | 171,900/s, 5.8 us | 168,900/s, 5.9 us | 62 MB |
| buffered, 4 GB | 95,900/s, 10.4 us | 172,900/s, 5.8 us | 171,200/s, 5.8 us | 62 MB |
| buffered, 8 MB, through io-wq (9.68) | 68,500/s, 14.5 us | 99,400/s, 11.7 us | | 11 MB |
| buffered, 8 MB, inline | 68,200/s, 14.6 us | 100,700/s, 9.9 us | 85,600/s, 11.6 us | 11 MB |
| direct, 8 MB (the drive) | 53,700/s, 21.8 us | 97,900/s, 13.2 us | 94,000/s, 13.5 us | 11 MB |

Inline saves about 1.8 us of CPU a miss at 8 clients. At 32 clients the
SQL thread now does the copies itself, and with the drive the reads
overlap more, so it is behind.

**Where a miss goes** (perf, buffered, 8 MB, 8 clients; inclusive):

| | share |
|---|---:|
| `Store.load` | 30% |
| `Db.install` | 28% |
| `decodeNode` (`unpack` 8%, itself 7%, slicing 4%) | 19% |
| eviction | 4% |
| the kernel's read (`io_read`) | 5% |
| CRC | 3% |

Decoding is most of a miss: a leaf of acct holds about 200 rows, each
made into a key slice and a value slice to read one. The same decoded
form is why the cache takes 2.4 times its pages (9.68).

**Checkpoints:** updates, 32 clients, a checkpoint every 4 MB of log
(17 in 15 s), two rounds:

| mode | round 1 | round 2 |
|---|---|---|
| direct | 19,800/s, 29.9 us | 20,800/s, 29.7 us |
| buffered | 19,700/s, 30.3 us | 19,200/s, 28.5 us |

The difference is noise.

**Next: decode lazily.** A node read from disk would keep its body and
an array of entry offsets, not a slice per key and value. A key or
value would be sliced only when used, and a node is unpacked into
arrays only when a commit changes it. Search would compare a key
against the body in place. A slice of a str allocates nothing: it is the
same buffer with an offset and a reference (`rt_str_sub`, or
`rt_str_view` without the reference). That would remove most of the decode from a miss and
bring the cache to near 1x. Both the master and the replica need it.
The work is confined to lexdb_page and lexdb_store, about 150 uses of
`keys`, `vals` and `kids`, plus `scanLeaves`' callback, which hands the
executor whole arrays.

### 9.70 Lazy leaves

A leaf read from disk, or written by a checkpoint, is now *lazy*. It
keeps its page's entries as one string (`body`) and, per entry, one int
packing where its key and value are (start and length, 16 bits each:
`ents`). It makes no slice per key or value. The accessors are `count`,
`key`, `val`, `lower` and `valView` (a view: nothing counted). A change
first calls `loosen`, which makes the `keys` and `vals` arrays as before.
Each checkpoint's `repack` makes the leaf lazy again. Internal nodes
are unchanged. A lazy leaf costs `160 + entries + 8 a key`, against 64
bytes a key decoded.

**Scans.** `scanLeaves` hands the executor the leaf, not its arrays.
`bRunInto` takes each row's view once per run (`valView`, kept in an
array of views) and reads it once per column. Two things lost on the way:
- reading the value's lengths from the page for every row and column
  (aggregates 15 to 50% slower);
- a value start per row with `if lazy { body } else { ... }`: the native
  backend made that `str` counted, and so incremented and decremented its
  count at every byte read (aggregates up to 2 times slower).

`lower` compares the first key before searching, since a scan going on
into the next leaf always starts there. That shortcut is why scans are
now faster than before.

**Measured** (the 9.67 data; before: 9.69's build):

| | before | lazy |
|---|---:|---:|
| RSS, acct cached | 61 MB | 38 MB |
| RSS, acct and t cached (about 62 MB of pages) | 145 MB | 96 MB |

| point selects on acct | before | lazy |
|---|---|---|
| all cached, 1 / 8 / 32 clients | 94,900 / 169,900 / 168,000 | 96,100 / 172,100 / 170,400 |
| buffered, 8 MB cache, 1 / 8 / 32 | 67,400 / 98,500 / 86,700 | 76,700 / 117,400 / 105,000 |
| buffered, 32 MB cache, 1 / 8 / 32 | 71,300 / 106,800 / 101,000 | 96,200 / 169,800 / 168,000 (acct fits) |
| O_DIRECT, 8 MB, 1 / 8 (same hour, two runs) | 27,100 / 85,700 | 33,000 / 105,600 |

| aggregates, ms, best of 7, two rounds the same within 0.2 | before | lazy |
|---|---:|---:|
| `count(*)` on t | 15.0 | 12.6 |
| 4 aggregates `WHERE n > 10` | 37.5 | 35.5 |
| `sum(v)`, three conditions | 43.3 | 41.0 |
| `GROUP BY g` | 48.3 | 45.9 |
| `GROUP BY n WHERE v % 2 = 0` | 36.1 | 34.1 |
| `sum(abalance)` on acct | 22.0 | 21.0 |

Updates (32 clients, a checkpoint every 4 MB of log): 20,800 and
20,400/s before, 20,800 and 19,300/s after, at 29.9 to 30.3 us each.

- **Memory:** the cache is now 1.5 times the pages, not 2.3.
- **A miss from the page cache** costs about 2.7 us of CPU, not 4.3.
- **Hits and updates** are unchanged; scans are 5 to 16% faster.

**For the replica (9.68):**
- a 32 MB private cache now holds all of acct;
- one master and one replica, each with a small cache over the shared
  page cache, take less memory than one server did before this note.

**Tests.** `page_codec` checks a decoded leaf is lazy, its `lower` at
five keys, and `loosen`. `store_ahead` reads its leaves through the node.
All 62 lexdb tests, the crash test (20 rounds, direct and buffered) and
the native library tests pass.

**`withCapacity`** (a built-in added for this, at the user's suggestion:
SPEC 11). `bRunInto` used to grow its array of row views by appending.
Lexell had no way to size an array of views ahead, since `array(n, v)`
makes owned values. `var rows: []&str = withCapacity(to - from)` makes an
empty array with that room, rounded up to a power of two. Its element
type comes from where it is used. It is in both runtimes as
`rt_arr_cap`.

| aggregates, ms (as in the table above), two rounds | appending | withCapacity |
|---|---|---|
| round 1 | 12.5 / 35.6 / 41.0 / 46.0 / 34.0 / 21.1 | 12.0 / 34.8 / 40.5 / 45.5 / 33.5 / 20.7 |
| round 2 | 12.5 / 35.6 / 41.5 / 46.1 / 34.1 / 21.2 | 12.2 / 35.0 / 40.8 / 45.5 / 33.4 / 20.7 |

### 9.71 The follower: base and delta, in one process (step 2 of 9.68)

`cmd/lexdb_follow.lxl` is the read side of a replica. It reads the store
from the master's files and changes nothing:

- **Base:** a checkpoint's trees, read from the page file. It keeps its
  own page cache, keyed by page number: lazy leaves (9.70), and internal
  nodes with their children as page numbers. A page is never written in
  place, so a cached page stays right for every checkpoint that names it.
- **Delta:** every batch's rows since the base, read from the log
  segments with recovery's `readFrame`. Per tree, each key has its
  versions by batch (whole values: the log holds rows), and the keys are
  in sorted runs of key numbers. A run merges into the one before it while
  that one is no longer (a binary counter), so a scan merges about log n
  runs. Tree creates and drops are kept by batch.
- **A snapshot** is a batch and a base. A point read takes the newest
  version at or before the batch, else the base. A scan merges the base's
  leaves with the delta's keys in the range. A base value is unescaped,
  and a large value's chunks are read from the base's companion tree, as
  `unstore` does.

**When a checkpoint can serve a snapshot.** A checkpoint takes the trees
as they are, which can include commits in the batch still open, and
replays from `durableBatch + 1`. So its trees can hold a commit that its
replay point does not cover. The meta page now records `covers` (the
batch of the last commit applied when the trees were taken), and a base
serves only snapshots at batches >= it. Files from before this have
`covers` 0, and a follower does not use their checkpoint. The next one
the master writes, at the latest at shutdown, has it.

**What the master keeps for a follower** (`Store.hold(ckpt, seg)`):
- the pages that checkpoints after `ckpt` free stay unused (`heldFree`).
  They are still written into the meta page's free list, so a restart,
  which drops the hold, does not leak them;
- log segments from `seg` on are not recycled.

`holdNow` starts a hold at the durable checkpoint, and every segment, in
one step. The follower then reads the meta page, which may be that
checkpoint or a later one. When no snapshot uses a base but the newest,
the follower lets the older ones go:
1. it evicts the pages the oldest kept base lists as free (the master
   may reuse them from then on);
2. it drops the versions before that base's replay batch;
3. it moves the hold up.

A durable batch missing from the log is now an error, where the follower
used to stop short of it without saying so.

**Tests:**
- `follow_basic`, twice: a follower cache of 48 KB (pages come and go)
  and 16 MB (every page stays, so a page the master reuses must be
  evicted). Each pass runs 80 rounds of concurrent random commits: puts,
  deletes, escaped values, large values, trees created and dropped,
  checkpoints, 64 KB log segments. Each round records every tree and 20
  keys a tree as a master snapshot sees them. The follower runs a round
  behind (twelve, for twenty rounds) and must match the record whole and
  by point reads. Snapshots kept across about a dozen checkpoints must
  still read their state. The page file audits clean at the end.
- `follow_covers` holds the log's flushes so that a checkpoint takes a
  commit beyond its replay point. A follower one batch short must not see
  that commit.

Ten bugs were put back, and each was caught:
- versions read regardless of the batch;
- freed pages kept in the cache;
- an escaped value not unescaped;
- the master ignoring the hold;
- a base used before its covers batch;
- the delta pruned to the newest base;
- creates and drops ignored;
- a deleted key not hiding the base's;
- segments not held;
- `covers` not written.

The last needed `follow_covers`. Segments not held needed smaller
segments and the lag. All 64 lexdb tests and the crash test pass.

**Measured** (one process, the simulated files, everything cached;
100,000 rows, then 20,000 updates in the delta, 18,116 keys):

| | master | follower |
|---|---:|---:|
| point read | 390 to 400 ns | 382 to 393 ns |
| full scan, empty delta | 2 ms | 4 ms |
| full scan, 18,116 delta keys | 2 ms | 9 ms (15 before the runs held key numbers and merged instead of sorting) |

**Next:**
- **Scans:** stream the delta's merge rather than collecting it, and read
  the base's entries without copying them out of the cache.
- **Step 3:** the replica process. Batches come over a socket after their
  flush (with this as catch-up), and hold and the durable batch become
  messages. The executor reads through the follower for read-only
  sessions, and refuses writes with 25006.

### 9.72 The replica process (step 3 of 9.68)

`lexdb --replica DATADIR ADDR...` runs a read-only replica of the master
that serves `DATADIR`. It is a process of its own, with its own TCP port
and Unix socket. Clients choose at connection time: the master's address
for read-write sessions, the replica's for read-only ones. Nothing is
forwarded between them, and no client socket moves.

**Between the two** (`cmd/lexdb_repl.lxl`): a Unix socket in the data
directory, `repl.sock`, carries short lines:

| line | direction | meaning |
|---|---|---|
| `N` | replica to master | the handshake: hold what I will read |
| `C ckpt` | master to replica | held from that checkpoint |
| `D batch ckpt` | master to replica | the log holds batches up to `batch`; the last checkpoint is `ckpt` |
| `H ckpt seg` | replica to master | `Store.hold` |

- The master sends `D` after each flush and each checkpoint, coalesced,
  so a replica that is behind gets the newest only. The replica reads the
  log and the pages itself, and nothing else crosses.
- The replica reads the meta page only when the checkpoint number has
  changed. It used to read it on every poll: two page reads per batch.
- The follower cannot write to the socket from inside its lock, so it
  leaves its newest hold in an outbox (`Link.Remote`), and a task sends
  it.
- At the handshake, a master whose last checkpoint does not record
  `covers` (a new store, or a file from before 9.71) takes one first.
  `covers` is now kept as `covers + 1`, so 0 means not known, and a real
  `covers` of 0 (a new store) is usable.
- **When the replica goes**, the master releases the hold. **When the
  master goes**, the replica stops with exit 1. A master that restarts may
  reuse pages the replica reads, so the replica starts again from scratch.
- One replica at a time, since the hold is one. A replica started again
  retries its handshake until the master has seen the old one go.

**The replica's store** (`openReplica`) has the follower in it
(`Store.fo`). The follower now lives in `lexdb_store`, since Lexell
modules cannot import each other in a cycle.
- **Reads:** `get`, `scan` and `scanBack` (a backward scan, new in the
  follower) are served from a follower snapshot. The transaction takes it
  at its first read (a snapshot or block, at its start) and keeps it to
  its end, so a block on the replica reads one state.
- **Batch scans:** `scanLeaves` answers "not in place", and the executor
  uses its row path.
- **Writes:** the executor refuses writing statements before running
  them, as a PostgreSQL standby does: SQLSTATE 25006, "cannot execute
  INSERT in a read-only transaction". COPY TO and EXPLAIN without ANALYZE
  are allowed. A write that gets past that, such as `nextval`'s, fails at
  commit.
- **Catalog changes** the replica applies are counted for the plan cache
  (`watch`).
- **A snapshot ends when its transaction is dropped.** The SQL layer drops
  some transactions without ending them: a prepared statement's Describe
  reads the catalog in one. That is harmless on the master, whose plain
  transactions pin nothing. On a replica, pgbench's prepared selects left
  two snapshots per connection, pinning the first checkpoint for good. In
  15 s of updates that held 3 checkpoints and 268,777 delta keys, and kept
  the master's pages and log segments; the replica's memory went from
  95 MB to 270 MB. The transaction now holds its snapshot as a `RepPin`
  whose `drop` ends it.

**Measured** (the 9.67 data; master and replica on one machine, each
with its own port; pgbench prepared, 8 s; CPU from `/proc`):

| load | master | replica |
|---|---|---|
| point selects, 8 clients, on the master only | 169,900/s | |
| the same, on the replica only | | 167,400/s |
| both at once, 8 clients each | 163,800/s | 162,900/s |
| updates, 32 clients, on the master | 22,400/s, 4.32 s CPU | applies them: 0.58 s CPU |
| updates on the master, selects on the replica | 21,900/s | 142,900/s |
| updates and selects both on the master | 20,800/s, selects 101,000/s | |

- **Selects:** two processes serve 1.92 times what one does.
- **Selects beside writes:** on the replica they do not slow the master's
  commits, and the replica serves 41% more of them than the master did
  beside its own commits.
- **Applying the master's writes** costs the replica about 2.6 us of CPU
  each, 7% of a core at 22,000 a second.
- **Memory** (RSS, LEXDB_PAGES direct, all data cached): 40 MB and 39 MB
  warm. Under updates the master reaches 96 MB and the replica 61 to
  67 MB: one checkpoint's delta, and a 31 MB page cache with 11,892 pages
  evicted as freed in 15 s.

**Tests:**
- `exec_replica` runs SQL on a master and a replica store in one process:
  - twelve queries give the same rows on both;
  - later commits show after a poll, and a block keeps its snapshot;
  - a column added and an index created on the master show on the
    replica, its plans made again;
  - six kinds of write are refused with 25006, and the session goes on;
  - the page file audits clean.
- `follow_basic` checks backward scans of random ranges against the
  master's, and three more bugs put back are caught (a backward scan's
  deletes, its descent, its stop).
- `tests/lexdb/replica.py` runs the two processes through psql:
  - rounds of writes on the master, after each of which the replica must
    give the master's answers;
  - the replica refuses a write every round;
  - every third round it is killed with SIGKILL during the writes and
    started again;
  - the master is killed with SIGKILL halfway: the replica must stop
    (exit 1), and both start again;
  - the master stops with SIGTERM at the end, and the replica with it.

  Four runs passed (12 and 3 × 20 rounds). It needs psql, and skips (77)
  without it.

**Next:**
- a replica that outlives a master restart, if wanted: it would start
  again from the new checkpoint itself, not exit;
- more than one replica: a hold per replica;
- the scans' delta merge (9.71).

### 9.73 Several replicas, under one command

```
lexdb DATADIR ADDR... --replicas N [--replica-addr ADDR...]
```

This runs a supervisor (`task.workers`): worker 0 is the master, workers 1
to N are replicas.

- **Addresses:** the replicas serve `--replica-addr`, by default each
  master address with the port one higher.
  - They share the TCP port: each listens with `SO_REUSEPORT`, and the
    kernel spreads connections by a hash.
  - They share the Unix socket: the supervisor makes it before forking,
    and each worker takes its own copy of the listener, so all accept from
    one queue (`EPOLLEXCLUSIVE`).
- **Restarts:** each worker marks itself ready (`workerReady`) once
  serving, so its later ends never count toward the supervisor giving up.
  - A crashed master is started again. The replicas see the link end,
    exit 1, and are started again with it. A replica waits up to 60 s for
    the master's socket.
  - A crashed replica is started again on its own.
- **Stopping:** SIGTERM or SIGINT to the supervisor stops them all, and it
  removes the replicas' Unix socket.

`lexdb --replica` (9.72) is still there, to run one by hand.

**A hold per replica.** `Store.holds` maps each follower's id to its
checkpoint and segment. The effective hold, which decides what the master
does not reuse, is the oldest, recomputed on each change (`rehold`). A
replica's connection is its id, and its hold goes when the connection
does. `hold` and `holdNow` are follower 0, the one in this process. The
link no longer refuses a second replica.

**Measured** (the 9.67 data; pgbench point selects, prepared, 8 clients
per replica, on the replicas' shared Unix socket; 16 CPUs, which pgbench
shares):

| replicas | clients | selects/s | against one | CPU per replica |
|---:|---:|---:|---:|---|
| 1 | 8 | 167,200 | 1.0 | 1.00 |
| 2 | 16 | 324,700 | 1.94 | 1.00 each |
| 4 | 32 | 538,000 | 3.2 | 1.00 each |
| 8 | 64 | 686,700 | 4.1 | 0.85 to 0.96 |

- **Up to four** the replicas are each a busy core, and the shared socket
  spreads the connections evenly.
- **At eight** the machine runs out: pgbench's 16 threads and the
  kernel share its 16 CPUs. PostgreSQL's best on this machine was 711,000
  (9.67).
- **Over TCP** (`SO_REUSEPORT`), four replicas give 396,000/s, each 0.84 of
  a core. The spread is even; the TCP stack costs more on both sides.
- **Memory:** each replica held 38 to 40 MB with acct cached.

**Tests:**
- `follow_basic` has a second follower with its own hold (`Link.LocalId`).
  It stops at round 10 for 50 rounds with a snapshot open, while the first
  goes on through many checkpoints. Its snapshot must still read round
  10's state, and then it must catch up. Two more bugs put back were
  caught (the newest hold kept, not the oldest; one hold for all), fifteen
  in all.
- `replica.py` adds the supervised form:
  - a master and two replicas, both replicas answering on the replicas'
    port;
  - the master (the worker holding the data directory's lock) killed with
    SIGKILL: the supervisor starts it again, the replicas with it, the
    data intact;
  - a replica killed and started again on its own;
  - a write refused;
  - SIGTERM stopping all of them with exit 0.
- All 65 lexdb tests, the crash test, and `replica.py` with 20 rounds pass.

### 9.74 A connection per user: what a connection costs (a note, nothing built)

The user's thought: databases have needed connection pools between web
servers and themselves because a connection is expensive (PostgreSQL's is
a process). lexdb's is a task in one event loop. Could each real user of a
website have a connection of their own, 10,000 or 50,000 at once?

**Measured** (the master; Unix-socket connections, each through startup
and then idle; RSS of the process; the 9.67 data cached):

| idle connections | RSS | per connection | after one query on each | a query on one, the others open |
|---:|---:|---:|---:|---:|
| 1,000 | 39 to 115 MB | 78 KB | 86 KB | 14 us |
| 10,000 | 112 to 807 MB | 71 KB | 79 KB | 13 us |

Opening 10,000 took 0.5 s.

- **Where it goes:** a connection's read buffer is a 64 KiB array, zeroed
  when the connection opens (`Wire.inBuf`), so it is resident at once:
  most of the cost. The rest is the task's stack (256 KiB reserved with
  `MAP_NORESERVE`, only the pages touched resident), the session, the
  output buffer, and after a query the plan cache. The kernel's socket
  memory is not in RSS.
- **At 50,000:** about 4 GB as it is.
- **What would shrink it:** the read buffer made only while a message is
  being read, or started at 4 KiB, would bring an idle connection to about
  15 to 20 KB (1 GB for 50,000).

**Limits besides memory:**
- Each task's stack is two mappings (the stack and its guard).
  `vm.max_map_count` is 65,530 on many distributions, which caps a process
  at about 32,000 connections (this machine allows 1,048,576). Stacks in
  slabs would lift that.
- File descriptors: the soft limit must be raised to the hard one.
- **A transaction left open by a user** holds a snapshot. On the master
  its old versions are bounded (`snapNodes`); on a replica it holds a
  checkpoint and the master's pages. A pool keeps transactions short by
  itself; a connection per user would want something like PostgreSQL's
  `idle_in_transaction_session_timeout`.
- Throughput is unchanged: one process runs its sessions' SQL on one core,
  so many active users queue on it (replicas spread them).

**For comparison:** PostgreSQL's backend is a process with a few MB of its
own memory, and taking a snapshot costs more as connections grow;
pgbouncer exists for this. SQL Server, and CockroachDB and TiDB (one
goroutine each), also take many connections. So this is not new in
databases, but it is new for a server speaking PostgreSQL's protocol
without a pooler.

Not planned: recorded for later.

### 9.75 Usable by real applications: what four clients need

The user's next aim: lexdb usable by real applications. Four common
clients were pointed at a new lexdb, each doing what a web application
does: create tables, insert with parameters, select, update, transactions,
upsert, introspection. The clients were psycopg 3.3, asyncpg 0.32,
SQLAlchemy 2.1 on psycopg, and node-postgres 8.23, plus psql's `\dt` and
`\d`. The probes are in the session's scratch folder: to become a test.

**What failed, and why:**

| what | client | cause |
|---|---|---|
| almost every CREATE TABLE | all | no `timestamptz` (or `timestamp`, `date`, `time`, `interval`), `bytea`, `real`/`double precision`, `uuid`, `json`/`jsonb`. lexdb has int2/4/8, bool, numeric, text/varchar, and arrays of them. 4.8 planned `timestamptz` and `bytea`; they were never built |
| upsert | psycopg | no `INSERT ... ON CONFLICT` |
| connecting | SQLAlchemy | its first query, `select pg_catalog.version()`: no schema-qualified function names, no `version()` |
| create_all, reflection | SQLAlchemy | `pg_catalog.pg_class`, `pg_namespace` and the rest: no catalog views |
| `information_schema.tables`, `pg_tables` | psycopg | the same |
| `\dt`, `\d` | psql | its catalog queries; `~` (regular expression match) |
| binary results | psycopg (binary=True), asyncpg | "results in binary are not supported" |
| typed parameters | asyncpg | it reads the parameter types lexdb describes and sends values to match: an untyped parameter is text |

node-postgres and psycopg (text format) worked wherever the SQL did.

**A plan, in stages, each tested by these clients:**

1. **Types:**
   - `timestamptz`, `timestamp`, `date`, `time`, `interval`, with
     `now()`, `current_timestamp`, `current_date`, `extract`,
     `date_trunc`, and date and interval arithmetic;
   - `double precision`/`real`, `bytea` (hex output), `uuid`
     (`gen_random_uuid()`), `json`/`jsonb` (validated; `->`, `->>`,
     `@>` perhaps);
   - `char(n)`.

   Each needs: parsing, text input and output, comparison, an
   order-keeping key encoding, a place in the fixed row layout,
   coercion of parameters, and its OID in RowDescription.
2. **SQL that applications use:**
   - `INSERT ... ON CONFLICT (cols) DO NOTHING / DO UPDATE SET ... =
     EXCLUDED.col [WHERE]`;
   - schema-qualified function names;
   - `version()`, `current_schema()`, `current_user`, `string_agg`,
     `array_agg`, `ilike`, `~`;
   - the error codes clients test for (23505 and the rest).
3. **The catalog,** as read-only views made from lexdb's own:
   - `information_schema` (tables, columns, key_column_usage,
     table_constraints);
   - `pg_catalog`: `pg_namespace`, `pg_class`, `pg_attribute`, `pg_type`,
     `pg_index`, `pg_constraint`, `pg_attrdef`, `pg_tables`, `pg_database`,
     `pg_settings` perhaps;
   - the functions their queries call: `pg_table_is_visible`,
     `format_type`, `pg_get_indexdef`, `pg_get_constraintdef`, `obj_description`.

   Enough for SQLAlchemy's create_all and reflection, the usual
   migration tools, and psql's `\dt` and `\d`. 0 left this to be
   decided; the probes decide it.
4. **Authentication and TLS:** SCRAM-SHA-256 (and password), TLS through
   `lib/tls`, as 4.7 planned. Until then lexdb is for loopback only.
5. **Views** (added after 9.81): `CREATE [OR REPLACE] VIEW`, `DROP VIEW`,
   a view's query inlined where it is named, dependencies (a table a view
   reads is not dropped without CASCADE), and their catalog rows
   (`pg_views`, `information_schema.views`, relkind `v`,
   `pg_get_viewdef`, psql's `\dv` and `\d`). Before privileges, because
   views are part of PostgreSQL's privilege model: a view is how a role
   is given some columns or rows of a table, and it reads with its owner's
   privileges.
6. **Privileges** (added after 9.81): owners for tables, views, schemas
   and sequences; GRANT and REVOKE of their privileges (SELECT, INSERT,
   UPDATE, DELETE, TRUNCATE; a schema's USAGE and CREATE; a sequence's
   USAGE); role membership (GRANT role TO role); `relacl`,
   `has_table_privilege` and psql's `\dp` true to them.
7. **Binary formats** for the common types: asyncpg needs them, and JDBC
   and psycopg's binary mode use them. Last, as the user decided after
   9.81.

Added after 9.83, at the user's choice, before binary formats: COPY's speed
and memory (9.84), then what migration tools need (9.85) and row locks
(9.86).

**The values for the new types.** The executor's values (`Val`) are null,
int, bool, numeric and text. Arrays were added as text in PostgreSQL's
text form (9.27), which keeps every value printable without its type. Two
ways for the new types:
- **New kinds of value** (a timestamp as microseconds, a date as days, a
  double, bytes). Exact and fast, but every match on `Val` in the executor
  learns them, and output must know types.
- **Text in a canonical form,** typed by the column, as arrays are (a
  timestamptz as `2026-01-02 03:04:05.123456+00` in UTC, which sorts as
  it compares). Fewer changes; arithmetic and functions parse and format.

The recommendation is new kinds for the time types and doubles (they are
compared, sorted and computed with all the time) and text for json, uuid
and bytea, which are mostly stored and returned.

### 9.76 Dates, times, timestamps and intervals

Stage 1 of 9.75, built on the standard library's new types
(design/time-types.md). `cmd/lexdb_time.lxl` holds PostgreSQL's side: its
input forms, its output (DateStyle ISO, IntervalStyle postgres), interval
text, `extract`, `date_trunc`, `age`, and the arithmetic.

**Types:**
- `date`;
- `time` and `time(p)`;
- `timestamp` and `timestamp(p)` (also `timestamp without time zone`);
- `timestamptz` (`timestamp with time zone`);
- `interval`;
- arrays of each.

`time with time zone` is refused (0A000), as PostgreSQL advises against
it.

**Values** are new kinds of `Val`: `Date` (days), `Time` (microseconds
since midnight), `Ts` and `Tstz` (microseconds) and `Ival` (months, days,
microseconds).
- **The numbers count from 2000-01-01, PostgreSQL's zero point.** That is
  not a limit: a date before it is negative, as a Unix time before 1970 is.
  The range is PostgreSQL's: dates from 4714-11-24 BC to 5874897 AD,
  timestamps to 294276 AD, BC years written " BC". Counting from 2000 is
  what lets the whole range fit 64 bits of microseconds; from 1970 it would
  end about 30 years short. PostgreSQL's binary format is the same numbers.
- `infinity` and `-infinity` are the largest and smallest ints.
- A timestamptz is an instant, shown in the session's zone, which is
  always UTC so far (`SET TimeZone` is to come). Input with an offset or a
  zone name (`Europe/London`) is converted, using `tz.instantOf`'s rules.

**Stored:**
- **In rows:** tags 7 to 10 (8 bytes) and 11 (an interval, 24 bytes). One
  function now gives each tag's size (`valSize`), where four copies of
  that rule were. The fixed layout (9.50) does not take them yet: a row
  with one is in the tagged form.
- **In keys:** as integers. An interval's key is PostgreSQL's comparison,
  a month as 30 days, then the time left of a day, so
  `interval '1 month' = interval '30 days'` in an index as in a `WHERE`.

**What PostgreSQL does, done the same:**
- **Coercion and comparison:** input rounded to the column's precision,
  halves away from zero. A date, timestamp and timestamptz compare with
  each other (a date at midnight, a timestamp in the session's zone), and
  a text with any of them is read as the other's type.
- **The operators:**
  - a date and days;
  - a date's difference in days;
  - a date plus a time or an interval;
  - a timestamp or timestamptz plus or minus an interval (months clamped
    to the month's end, then days, then time; a timestamptz's months and
    days in the session's zone);
  - the difference of two date-times, as days and a time of one sign;
  - intervals added, negated, and multiplied or divided by a number, with
    PostgreSQL's spill of fractions and its rounding;
  - `timestamp + '1 day'` reads the text as an interval, and `timestamp -
    '1 day'` as a timestamp, which fails as there.
- **`now()`, `current_timestamp`, `transaction_timestamp()`, `localtimestamp`,
  `current_date`, `current_time`:** the transaction's start (`Txn.now`),
  so they agree within a statement and within a block. `clock_timestamp()`
  is the clock.
- **`extract`/`date_part`:** every field PostgreSQL has, including `epoch`
  (an interval's year as 365.25 days), `julian`, the ISO week, and BC
  years. A date's fields are whole numbers, and it has no time fields
  (0A000). A field nobody has is 22023.
- **The rest:** `date_trunc` (a week starts on Monday), `age` (borrowing
  the earlier date's month's days), `make_date`, `to_timestamp`,
  `isfinite`.
- **Errors:** a well-formed value with no such day or hour is 22008
  (`2026-02-30`, `25:00`); a malformed one is 22007.

**Tests.** `tests/lexdb/time_queries.txt` holds 93 queries: literals and
output at the range's ends and in BC, infinity, precision, the interval
forms (PostgreSQL's words, `hh:mm:ss`, ISO 8601, fractions, `ago`),
casts, every operator, comparisons across the types, `extract` and
`date_trunc` fields, `age`, errors, and the types stored, keyed, indexed,
sorted, aggregated and updated. `tests/lexdb/gen_pg.py` runs them on
PostgreSQL (18.6 here) and writes `exec_time`, which expects PostgreSQL's
answers from lexdb's executor; all 93 agree.

Found on the way:
- the batch decoder (count, filtered scans) had its own copy of the row
  tags and failed on the new ones with XX001;
- the time functions' NULL rule ran for every function, so `coalesce` and
  `ANY` with a NULL gave NULL (7 tests caught it).

**The clients** (9.75):
- node-postgres: everything passes now;
- psycopg: everything with dates does, its timestamptz read as Python
  datetimes;
- still to do: `ON CONFLICT`, bytea, uuid, double precision, `array_agg`,
  the catalog, and binary formats (asyncpg).

All 66 lexdb tests pass. The crash test was not run: storage changed
only in the new tags.

### 9.77 INSERT ... ON CONFLICT

```
INSERT INTO t [AS alias] ... ON CONFLICT [(col, ...) [WHERE pred] | ON CONSTRAINT name]
    DO NOTHING | DO UPDATE SET col = expr, ... | (a, b) = (x, y) [WHERE cond]
```

It works after VALUES, `DEFAULT VALUES` and `INSERT ... SELECT`.

- **The keys that count:**
  - a target's columns choose the primary key or a unique index with the
    same columns, in any order;
  - `ON CONSTRAINT` names one (the primary key is `t_pkey`);
  - DO NOTHING without a target counts every unique key, and DO UPDATE
    needs a target (42601);
  - no key matches the target: 42P10; an unknown constraint: 42704;
  - a target's WHERE (a partial index's predicate) is read and not used.
- **Each proposed row** is made as an INSERT would make it (defaults,
  coercion, NOT NULL and CHECK). Then the rows there are looked up by
  each key, the primary key by its key and an index by its prefix.
  - **DO NOTHING** skips the row.
  - **DO UPDATE** updates the row there through UPDATE's path, so other
    unique keys, CHECKs and foreign keys still hold, and its tree is
    written as an UPDATE's.
- **In DO UPDATE's expressions:**
  - `excluded.col` is the proposed row, `t.col` or `alias.col` the row
    there;
  - a bare name is in both, so ambiguous (42702), as in PostgreSQL; only
    the column SET names stands alone;
  - `DEFAULT` is the column's default;
  - the WHERE decides whether the row is updated (not, if it is not true).
- **A row the statement already inserted or updated,** met again by DO
  UPDATE, is 21000 ("cannot affect row a second time"). DO NOTHING skips
  it.
- **RETURNING** gives the rows inserted and updated, and the tag `INSERT
  0 n` counts both.

`insertOne` is now in three parts: building the row, the conflict and its
update (`conflictOf`, `upsertOld`), and storing it (`storeRow`). COPY uses
it with no conflict clause.

**Tests:** `exec_upsert`, 37 statements generated from PostgreSQL 18.
- **The cases:**
  - DO NOTHING on the primary key, a unique column, and any key;
  - DO UPDATE with EXCLUDED and the row there, and its WHERE true and
    false;
  - RETURNING;
  - a row touched twice, under both actions;
  - ON CONSTRAINT, a two-column key named in the other order, a target no
    key matches, DO UPDATE without a target, an unknown constraint;
  - another unique key's 23505;
  - an alias, DEFAULT, a column list, `(a, b) = (x, y)`, `INSERT ...
    SELECT`;
  - ROLLBACK.
- **The bare-name ambiguity** was found by them: lexdb first made a bare
  name mean the row there, and PostgreSQL refuses it.

`tests/lexdb/gen_pg.py` replaces `gen_time.py`. It makes every test
checked against PostgreSQL (`gen_pg.py CONN [time] [upsert]`), each
suite's queries in one session, so a `BEGIN ... ROLLBACK` across several
queries runs as in the test; `exec_time`'s 93 answers came out the same.

Run: `exec_upsert`, `exec_time`, and the INSERT tests one by one
(`exec_sql`, `exec_returning`, `exec_unique`, `exec_fkey`,
`exec_fkaction`, `exec_insertsel`, `exec_copy`, `exec_default`,
`exec_seq`, `exec_seqcrash`, `exec_check`); not the whole suite, at the
user's asking, while another session benchmarks.

### 9.78 array_agg, uuid and bytea

- **`array_agg(x [ORDER BY ...]) [FILTER (WHERE ...)]`,** with DISTINCT.
  - It keeps NULLs as elements (the other aggregates skip them), and gives
    NULL for no rows.
  - Its type is the array of x's type: an array of dates is `date[]`.
  - Its ORDER BY shares `string_agg`'s sort (`orderIdx`).
- **`uuid`** (`Val.Uuid`, OID 2950).
  - It is read in all of PostgreSQL's forms: upper case, braces, no
    hyphens, or a hyphen after any group of four digits.
  - It is shown, compared and keyed as its 36-character lowercase form,
    which sorts as its bytes do, and stored in a row as 16 bytes (tag 12).
  - `gen_random_uuid()` is version 4, from the kernel's random bytes
    (`getrandom`), not `lib/uuid`'s OpenSSL: lexdb links no OpenSSL yet.
- **`bytea`** (`Val.Bytes`, OID 17).
  - It is read in hex (`\x0001ff`, pairs perhaps spaced) or the escape form
    (`\\`, `\nnn`), and shown in hex.
  - `encode` and `decode` take hex, base64 (76 characters a line) and
    escape; with `||`, `length`, and `octet_length` (a text's in bytes).
  - It is compared and keyed as its bytes, and stored with its length (tag
    13).
- **The kinds** join the dates' row tags (`valSize` and `timeVal` read tags 7 to
  13), the row decoder and the batch decoder.

**Tests.** `exec_types`, 40 queries generated from PostgreSQL 18 by
`gen_pg.py types`:
- `array_agg`'s cases;
- uuid's forms and four malformed ones, a uuid key's order and lookups,
  its duplicate, its text;
- gen_random_uuid's version and variant digits, and two calls differing;
- bytea's forms and three malformed ones, encode and decode both ways and
  an unknown format, `||` and the lengths, a bytea key's order and
  lookups.

`gen_pg.py` dropped empty lines from psql's output, so a row of one empty
text vanished. It now drops only the last newline; `exec_time` and
`exec_upsert` came out the same. Run one by one, besides `exec_types`:
`exec_time`, `exec_upsert`, `exec_aggorder`, `exec_agg`, `exec_srf`,
`exec_hashagg`, `exec_any`.

### 9.79 real and double precision

- **The types.**
  - `real` and `float4` are `Val.Real` (OID 700): a double that holds a
    single-precision value.
  - `double precision`, `float8` and `float` are `Val.Float` (OID 701).
  - `float(p)` is a real for p up to 24 and a double precision to 53.
  - Both are kind `K_FLOAT`; arrays are `real[]` and `double precision[]`.
- **Their text** is in `cmd/lexdb_float.lxl`, as PostgreSQL 12 on
  writes it.
  - The value is the shortest decimal that reads back as the value. A real's
    is the fewest digits that read back after rounding to single precision.
  - It is plain for exponents -4 to 14 (5 for a real), else `1.5e-07`; with
    `NaN`, `Infinity`, `-Infinity` and `-0`.
  - Reading accepts spaces, `NaN`, and `[+-]Infinity` or `inf` in any case.
    Out of range is 22003, as are nonzero digits that read as zero.
- **Arithmetic** (`arithFloat`):
  - two reals give a real, rounded to single precision; any other mix with a
    float gives a double precision, as PostgreSQL resolves it;
  - overflow and underflow from finite operands are 22003, a zero divisor is
    22012, and `%` on floats is 42883.
- **Conversions:**
  - to an integer type, rounded half to even (`rint`);
  - to numeric, at 15 significant digits (6 for a real), as
    `float8_numeric`; NaN and the infinities are 0A000 for now, as lexdb's
    numeric has neither;
  - from numeric, by its text.
- **Comparison** treats NaN as equal to itself and after every other value,
  and `-0 = 0`.
  - The key is the bits, turned to sort as the values do, with -0 as 0 and
    every NaN as one.
  - In rows, tag 14 is a double's 8 bytes and tag 15 a real's 4.
- **Functions:**
  - `abs`;
  - `round`, `floor`, `ceil`, `ceiling` and `trunc` (a numeric stays numeric
    and its own; an integer or float gives a double precision);
  - `sqrt`, `cbrt`, `exp`, `ln`, `log10`, `power`/`pow`, `sign` and
    `random()` (from `getrandom`), with PostgreSQL's 2201E and 2201F errors.
- **Aggregates:**
  - `sum` of reals is a real;
  - `avg` and the variances of floats are double precision;
  - `avg` squares its values as `float8_accum` does, so 1e300 overflows as
    in PostgreSQL.
- **`pg_typeof(x)`** is now known: the resolver replaces it with x's type
  (`exprOid`) as text.
- **Binary parameters** of both types are read, and `typLen` gives their
  sizes.

**Tests.** `exec_float`, 48 queries generated from PostgreSQL 18 by
`gen_pg.py float`:
- text both ways and the malformed or out-of-range cases;
- arithmetic and its types (`pg_typeof`), overflow, underflow and division
  by zero;
- casts with integers and numeric;
- comparisons with NaN, -0 and a real against a double;
- the functions and their errors;
- a table of float columns: their order, filters, aggregates and an
  overflowing `avg`;
- a float primary key with NaN, -0 (a duplicate of 0), -Infinity, and
  lookups;
- UPDATE ... RETURNING.

**Two differences, left as they are:**
- **cbrt.** PostgreSQL's `cbrt(27)` is glibc's 3.0000000000000004, and
  Lexell's own `cbrt` gives exactly 3. The test leaves it out.
- **Subnormals.** Lexell's float `toStr` is not shortest for subnormals
  (`1e-310` prints as `9.99999999999997e-311`, though its bits are right),
  so lexdb shows such values with more digits than PostgreSQL. That is for
  the runtime to fix.

Run one by one, besides `exec_float`: `exec_types`, `exec_time`,
`exec_upsert`, `exec_agg`, `exec_aggorder`, `exec_sql`, `exec_retype`,
`exec_window`, `wire_client`, `wire_describe`, `wire_prepared`.

### 9.80 pg_catalog, information_schema, savepoints and VALUES

Stage 3 of 9.75. **What clients send** was captured from PostgreSQL 18 with
`log_statement = all` and from `psql -E`:
- SQLAlchemy's connect, `create_all`, every inspector call Alembic makes
  (columns, keys, foreign keys, indexes, unique and check constraints,
  `has_table`, schemas, views, sequences, comments), and `drop_all`;
- psycopg's;
- psql's `\dt \d \di \dn \ds \dv \l`, and `\d` on a table, an index and a
  sequence.

Those queries are the specification, and they now run against lexdb.

- **The relations** are in `cmd/lexdb_pgcat.lxl`: their columns, and
  PostgreSQL's built-in types (pg_type's rows) with `format_type`.
  - pg_catalog's:
    - `pg_namespace`, `pg_class`, `pg_attribute`, `pg_attrdef`, `pg_type`,
      `pg_index`, `pg_constraint`, `pg_sequence`, `pg_depend`,
      `pg_collation`, `pg_am`, `pg_database`, `pg_roles`, `pg_user`,
      `pg_tablespace`;
    - the views `pg_tables`, `pg_indexes` and `pg_sequences`;
    - with no rows (lexdb has none of the things they describe):
      `pg_description`, `pg_shdescription`, `pg_proc`, `pg_opclass`,
      `pg_inherits`, `pg_policy`, `pg_statistic_ext`, the
      `pg_publication` three, `pg_trigger`, `pg_rewrite`, `pg_enum`,
      `pg_extension`, `pg_foreign_table`, `pg_views`, `pg_matviews` and
      `pg_settings`.
  - information_schema's: `schemata`, `tables`, `columns`,
    `table_constraints`, `key_column_usage`, `referential_constraints`,
    `constraint_column_usage`, `check_constraints`, `sequences`, and
    `views` (no rows).
- **How a relation is read.**
  - The parser makes `pg_class` (bare, or `pg_catalog.pg_class`) and
    `information_schema.tables` a function in FROM, `#pg_class`, as
    `generate_series` is one. A CTE of the same name comes first.
  - `execSrf` makes its rows from lexdb's catalog as the statement's
    transaction sees it (`catSnap`, `catRows`), so DDL earlier in the same
    block shows.
  - Joins, WHERE, subqueries and ORDER BY are the executor's own.
- **OIDs.**
  - lexdb has no OIDs, so they are made from names: a 32-bit FNV hash of
    the kind and the catalog key, from 16384 up (`catOid`). A relation keeps
    its OID while it keeps its name.
  - public is 2200, pg_catalog 11, information_schema 13000; the catalog
    relations clients name as a `classoid` have PostgreSQL's (pg_class
    1259, ...).
  - A primary key is an index of its own here (`t_pkey`), as in PostgreSQL;
    in lexdb it is the table's tree.
- **What the rows say,** as PostgreSQL would:
  - `atttypmod` (varchar's length + 4, numeric's precision and scale);
  - `attidentity`;
  - DEFAULTs as `pg_attrdef` shows them (`nextval('t_id_seq'::regclass)`,
    `'x'::text`, `'-1'::integer`, `now()`), but none for an identity
    column;
  - constraints and their definitions (`PRIMARY KEY (id)`, `FOREIGN KEY
    (a) REFERENCES t(id) ON DELETE CASCADE`, `CHECK ((qty > 0))`);
  - `indkey` as an `int2vector` (`2 3`);
  - `pg_get_indexdef`'s `CREATE UNIQUE INDEX ... USING btree (...) WHERE
    (...)`;
  - `information_schema`'s data types, precisions, identity columns, and
    its sequences, which leave out the identity columns' as PostgreSQL's
    do.
- **New types.**
  - `oid` (an integer, OID 26), `name` (text, 19), `"char"` (text, 18),
    and `int2vector` and `oidvector` (arrays of int2 and oid).
  - The reg types `regclass`, `regtype`, `regnamespace` and `regproc` are
    `Val.Reg`, an OID with the name it shows:
    - compared and keyed as the OID, shown as the name;
    - `'book'::regclass` looks the name up along the path (42P01 if none);
    - `c.oid::regclass` shows a name, qualified if its schema is not on the
      path;
    - `'int4'::regtype` and `to_regtype` use the built-in types.
- **The catalog functions:**
  - `pg_table_is_visible`, `pg_get_constraintdef` (pretty: `CHECK (x)`),
    `pg_get_indexdef` (whole, or a column), `pg_get_expr` (pretty: no outer
    parentheses), `pg_get_serial_sequence`, `pg_get_userbyid`,
    `format_type`;
  - `to_regclass`, `to_regtype`, `to_regnamespace`, `current_schema`,
    `current_user`;
  - `quote_ident`, `array_to_string`, `array_length`, `cardinality`,
    `json_build_object`, `pg_encoding_to_char`;
  - with fixed answers: `obj_description`, `pg_get_triggerdef`, the
    `has_*_privilege`s, `pg_relation_size` and the rest.
  - They read the catalog through a summary the statement binds before it
    runs: one line a fact, in the store's memo under the session. A
    statement whose parse met a catalog relation, a reg type or one of
    these functions carries `CAT_MARK` among its sequence names, and
    `bindSeqs` binds it as it binds nextval's sequences.
  - The session's user, from the startup message, is `current_user` and
    every object's owner.
- **The SQL these queries use:**
  - `pg_catalog.f(...)` and `pg_catalog.type`;
  - `~ !~ ~* !~*` (`lib/regex`), and `OPERATOR(pg_catalog.~)`;
  - `COLLATE name` (read; lexdb compares bytes);
  - subscripts `x[i]`;
  - `ARRAY(subquery)`;
  - set-returning functions in a select list (`unnest`,
    `generate_subscripts`): marked values, made into rows when the query's
    rows are (`expandSrfs`, PostgreSQL 10's zip), and
    `pg_partition_ancestors` in FROM;
  - `current_user`, `session_user`, `user` and `current_schema` without
    parentheses;
  - the settings clients SHOW (`standard_conforming_strings`,
    `server_version_num`, ...).
- **VALUES** (SQLAlchemy's bulk insert reads `FROM (VALUES ...) AS t(a,
  b)`; psql uses `UNION ALL VALUES`).
  - It works in FROM, as a branch of UNION and the rest, and as a
    statement.
  - It is a function in FROM (`#values:k`) whose arguments are the rows'
    values; a column's type is its first typed value's, and the others are
    coerced to it.
- **Savepoints** (psycopg wraps its type lookups in one; Django and
  SQLAlchemy's nested transactions use them). `SAVEPOINT name`, `RELEASE
  [SAVEPOINT] name` and `ROLLBACK [WORK] TO [SAVEPOINT] name`.
  - A savepoint is the block's count of writes (`Txn.mark`). ROLLBACK TO
    drops the writes after it and rebuilds the key index (`Txn.undoTo`),
    keeps the savepoint, and clears the error state.
  - Its reads stay noted: a commit checks them all, the safe side.
  - A tree made after it (a CREATE TABLE) stays, empty.
  - Errors: 25P01 outside a block, 3B001 for an unknown name.

**What the clients do now:**
- **SQLAlchemy 2.1:** every step passes. That covers its connect,
  `create_all`, ORM inserts (`INSERT ... SELECT ... FROM (VALUES ...)`) and
  queries, every inspector call, and `drop_all`.
- **node-postgres:** every step passes.
- **psql:** `\dt`, `\d`, `\di`, `\dn`, `\ds`, `\dv` and `\l`, and `\d` on a
  table, an index or a sequence, show what PostgreSQL's psql shows: columns
  with types, collations, nullability and defaults; indexes with
  predicates; check and foreign-key constraints; "Referenced by"; and a
  sequence's owner.
- **psycopg:** every step that does not use the binary format passes. Its
  binary parameters (bytea, date) and binary results, and asyncpg's
  binary results and COPY, are stage 5; `jsonb` is not done yet.

**Tests.** `exec_catalog`, 66 statements generated from PostgreSQL 18 by
`gen_pg.py catalog`, all the same:
- a schema of two schemas: serial and identity keys, varchar(n),
  numeric(p, s), a text array, defaults (a negative one among them),
  CHECKs, a foreign key with actions, a partial unique index;
- everything above that holds no OIDs: the information_schema relations;
  pg_class, pg_attribute, pg_attrdef, pg_constraint (with
  `pg_get_constraintdef`), pg_index (`indkey`, `pg_get_indexdef`,
  `pg_get_expr`), pg_indexes, pg_tables, pg_namespace, pg_sequence and
  pg_type;
- the reg types and their errors, `to_regclass` and `to_regtype`,
  `pg_get_serial_sequence` and `format_type`;
- visibility under `SET search_path`, `current_schema`;
- `~` and its kin, subscripts, `pg_catalog.`-qualified names;
- VALUES three ways, select-list unnest zipped and crossed;
- the array functions, `json_build_object`, `ARRAY(subquery)`;
- savepoints: an error rolled back to, one released, and their errors.

`gen_pg.py` writes a statement's tag after its RETURNING rows, but not
SHOW's: psql shows none.

**Differences from PostgreSQL, left as they are:**
- the defaults and CHECKs of a numeric column keep the constant as written
  (`0`, where PostgreSQL writes `0::numeric` in a CHECK);
- `generate_subscripts` of an `int2vector` counts from 1 (PostgreSQL's
  vectors count from 0);
- not-null constraints are not rows of `pg_constraint` (PostgreSQL 18
  makes them some);
- `current_database()` is `lexdb` whatever database the client named.

### 9.81 Authentication and TLS

Stage 4 of 9.75. Until now lexdb let any connection in as any user, in
plaintext: fit for loopback only.

- **Roles** are rows of the catalog (`\x05name`): whether one may log in,
  whether it is a superuser, and its password's SCRAM verifier. The
  verifier is PostgreSQL's form, `SCRAM-SHA-256$4096:salt$StoredKey:ServerKey`;
  the password itself is never kept.
  - The statements:
    - `CREATE ROLE | USER name [WITH] options`, where USER implies LOGIN;
    - `ALTER ROLE | USER name [WITH] options`, `ALTER ROLE name RENAME TO
      new`;
    - `DROP ROLE | USER [IF EXISTS] name, ...`.
  - Their options are LOGIN, SUPERUSER and their NOs, and `[ENCRYPTED]
    PASSWORD 'text' | NULL`. The other options PostgreSQL has are read and
    not kept.
  - A PASSWORD that is already a SCRAM verifier is kept as given (pg_dump
    writes them). An MD5 one is refused (0A000), and an empty one is none.
  - **Who may:** a superuser role, or a session that is no role (one that
    came in by trust). A role may change its own password (42501
    otherwise).
  - **Errors** as PostgreSQL's: 42710 exists, 42704 does not exist, 55006
    dropping yourself, 42939 for a `pg_` name.
  - `pg_roles` and `pg_user` list the roles (and the trusted session's user
    when it is none). Roles replicate with the catalog, and a replica
    refuses role DDL as it refuses any write.
- **Methods**, by the connection's kind: `--auth` for TCP, `--auth-local`
  for the Unix socket. Each is `trust` (the default, as initdb's) or
  `scram-sha-256`.
  - **trust** lets any user name in, as before.
  - **SCRAM-SHA-256** (`cmd/lexdb_auth.lxl`, RFC 5802 and 7677) checks the
    role's verifier.
    - The server offers `SCRAM-SHA-256-PLUS` too over TLS, binding the
      exchange to the connection (tls-server-end-point: a hash of the
      server's certificate, `tls.Engine.ownEndPoint`, new in lib/tls). A
      client that can bind but says it cannot ("y") is refused, as a
      downgrade.
    - An unknown role, or one with no password, goes through the same
      exchange with a made-up verifier and fails at its end (28P01, the
      same message), so a client cannot tell which roles exist.
    - A role that may not log in is refused after the exchange (28000).
    - With no roles yet, nobody gets in by SCRAM. The first roles are made
      over the trusted Unix socket, as PostgreSQL's are made by peer
      authentication.
- **TLS:** `--tls-cert FILE [--tls-key FILE]`.
  - An SSLRequest is answered `S`, and the handshake is lib/tls's memory
    engine. `Wire.fill` and `Wire.flush` read and write through it, so
    every message, COPY included, goes over TLS.
  - Bytes the client sent after the SSLRequest, before TLS, are refused
    (CVE-2021-23214).
  - Each accept loop loads the certificate once, and every connection
    shares that context.
  - `--require-tls` refuses a TCP connection without TLS (28000).
  - GSSAPI encryption is answered `N`. Direct TLS (PostgreSQL 17's
    `sslnegotiation=direct`) is not done.
- **The settings** are checked when the server starts: a method it does not
  know, or a certificate it cannot load, stops it with a message. They are
  then kept in the store's memo (`lexdb_wire.configure`), where the accept
  loops read them, so the tests' accept loops did not change. The master,
  the replicas and the supervisor all take the same flags.
- `current_user` is the authenticated role.
- `repeat(text, n)`, which the test wanted, was missing; it is added.

**Clients, against a server with `--auth scram-sha-256` and TLS:**
- **psql (libpq 18):** connects with `sslmode=verify-full`,
  `channel_binding=require` and TLS 1.3. Wrong passwords, unknown roles and
  NOLOGIN roles get PostgreSQL's messages. 5 MB of SELECT and COPY go
  through TLS both ways.
- **psycopg** (channel binding required) and **node-postgres** (TLS
  verified against the CA) connect and query.
- **asyncpg** connects and authenticates over TLS. It then stops at binary
  results (stage 5).

**Tests.** `wire_auth`, against Lexell's own client (lib/postgres over
pgwire). The certificates are made at test time by lib's test PKI
(`tlstest.pki()`, the openssl command; skipped without it). It covers:
- roles made over trust, and `pg_roles` and `pg_user`;
- SCRAM without TLS: the right password, a wrong one, an unknown role, a
  NOLOGIN role;
- SCRAM-SHA-256-PLUS with `verify-full` against the test CA, and a 1 MB
  result over TLS;
- a role changing its own password and refused CREATE ROLE, a superuser's
  ALTER and DROP, and the errors;
- `--require-tls` both ways.

**Not done:**
- per-database or per-address rules (pg_hba.conf);
- `password` (cleartext), `md5`, client certificates (`cert`), GSSAPI;
- SASLprep of passwords: they are used as their UTF-8 bytes, which is
  SASLprep's answer for ASCII;
- the role's own settings (`ALTER ROLE ... SET`) and memberships (`GRANT
  role`);
- privileges on tables. Any role that logs in may read and write
  everything, as a superuser may in PostgreSQL.

### 9.82 Views

Stage 5 of 9.75 as reordered: views before privileges, because a view is
how PostgreSQL gives a role some columns or rows of a table.

- **`CREATE [OR REPLACE] VIEW name [(column, ...)] AS query`.**
  - The query may be a SELECT, `WITH ... SELECT`, or VALUES. It is checked
    by planning it, which gives the view's columns.
  - A view shares a table's names (a catalog row under its name), so the
    two cannot have the same one (42P07).
  - More column names than columns is 42601, and the same name twice is
    42701.
  - A view that reads itself is refused (42P17), and so is a chain of views
    more than 64 deep.
  - **OR REPLACE** keeps PostgreSQL's rules. The old columns stay, in order,
    with their names and types (42P16 otherwise); new ones may follow. On a
    table it is 42809.
  - `WITH CHECK OPTION` and view options are refused (0A000). A parameter is
    42P02.
- **What is kept:** the query's text, cut from the statement by its tokens'
  positions; the columns' names, types and typmods; and the catalog keys of
  the relations the query reads (`readsOf`: FROM items, subqueries, CTEs,
  set operations). The row starts with `VIEW_MARK`, four `0xFF` bytes, where
  a table's starts with its tree's number.
- **Where a view is named in FROM,** `buildQuery` finds it where it finds a
  table, parses its text, and plans it as a subquery in FROM (`planSub`,
  not seeing the query around it).
  - The plan goes after the statement's own subqueries in `Query.subs`, and
    its level reads its rows as a FROM subquery's.
  - So a view costs a statement nothing until it is used. Kept plans hold
    the view's plan, and DDL bumps the catalog's version.
  - Views of views plan the same way. Column aliases (`v AS x(a, b)`)
    rename the view's columns.
  - Column aliases on a table are now allowed too: lexdb refused them
    before, and PostgreSQL does not.
- **Dependencies,** found through the views' kept keys:
  - `DROP TABLE` of a table a view reads is refused (2BP01) unless CASCADE,
    which drops the views too, and the views on them;
  - `DROP VIEW [IF EXISTS] name, ... [CASCADE]` works the same way;
  - `DROP SCHEMA ... CASCADE` drops its views, and the views elsewhere that
    read its tables;
  - DROP VIEW on a table, DROP TABLE on a view, and ALTER TABLE on a view
    are 42809.
- **Where lexdb differs from PostgreSQL** (deliberately, for now;
  `exec_viewsx` holds its own answers):
  - **Views are read-only.** INSERT, UPDATE and DELETE on a view are
    refused (0A000). PostgreSQL updates a simple view's table.
  - **A view keeps its text, not a tree of OIDs.** So renaming a table it
    reads, or renaming, dropping or retyping a column of one, or moving it
    to another schema, is refused (2BP01, saying to drop the view and make
    it again). PostgreSQL follows a rename. Adding a column is allowed.
  - `ALTER VIEW name RENAME TO new` works while no other view reads it.
  - `pg_get_viewdef`, `pg_views.definition` and
    `information_schema.views.view_definition` give the text as written,
    with a `;`. PostgreSQL gives its own formatting.
  - A view's columns keep their types but not a table column's typmod
    (`numeric`, not `numeric(10,2)`).
- **The catalog:**
  - `pg_class` (relkind `v`), `pg_attribute`, `pg_views`, and
    information_schema's `tables` (`VIEW`), `columns` and `views`;
  - `'v'::regclass`, and `pg_get_viewdef` by OID or name.
  - psql's `\dv`, `\d v` and `\d+ v` show views as PostgreSQL's psql does,
    the definition included. SQLAlchemy's `get_view_names` and
    `get_view_definition` work.
- **For psql's `\d+` on a view,** two things were added: SQL's `trim([LEADING
  | TRAILING | BOTH] [chars] FROM x)`, with `btrim`, `ltrim` and `rtrim`
  taking the characters to remove; and `pg_get_ruledef` (NULL: lexdb has no
  rules).

**Tests.**
- `exec_views`: 56 statements generated from PostgreSQL 18, all the same.
  They cover:
  - views over a filter, a join, a grouped join, a CTE and VALUES; a column
    list; a view of a view; one in another schema;
  - reads with WHERE, joins to tables, IN, scalar subqueries and column
    aliases, on views and tables;
  - OR REPLACE's three errors and its added column;
  - the name clashes, the catalog's rows;
  - DROP's dependencies and CASCADE, IF EXISTS, a schema's CASCADE;
  - the `trim` forms.
- `exec_viewsx`, by hand: lexdb's own answers above (writes refused, renames
  and column changes refused, ALTER VIEW, the text kept, a view reading
  itself).

### 9.83 Privileges

Stage 6 of 9.75: owners, GRANT and REVOKE, roles' memberships, and SET
ROLE, as PostgreSQL has them. Until now any role that logged in could read
and write everything.

- **Who is checked:** the session's current role. That is SET ROLE's role,
  else SET SESSION AUTHORIZATION's, else the login's.
  - A superuser role is not checked.
  - Neither is a session whose user is no role: one that came in by trust,
    as every session did before 9.81. So existing deployments and the
    tests run as before.
- **What is kept:** catalog rows of their own, so tables' rows did not
  change.
  - `ACL_PRE` and an object hold its owner and its grants. The object is
    `r:` and a relation's catalog key (a table, view or sequence), or `n:`
    and a schema.
  - Privileges are PostgreSQL's aclitem letters: `r` SELECT, `a` INSERT,
    `w` UPDATE, `d` DELETE, `D` TRUNCATE, `x` REFERENCES, `t` TRIGGER, `U`
    USAGE, `C` CREATE.
  - `MEM_PRE`, a role and a member, holds a membership. A role acts as
    itself, every role it is a member of (followed up the chain), and
    PUBLIC.
- **Owners.** CREATE TABLE, VIEW and SEQUENCE make the current role the
  owner, and a table's serial and identity sequences go to the table's
  owner. CREATE SCHEMA gives the schema to AUTHORIZATION's role, or to its
  maker.
  - Objects made before this have no owner: only superusers (and trusted
    sessions) may do an owner's things with them.
  - The schema public has PostgreSQL 15's grants: USAGE for PUBLIC, no
    CREATE.
- **The checks,** with PostgreSQL's 42501 messages:
  - **Reading:** SELECT on each table and view a query reads (`scCheck` in
    `buildQuery`), and USAGE on its schema.
    - A view's own relations are read as the view's owner, so a view gives
      a role exactly what it shows.
    - The checks happen when a query is planned. A prepared statement's
      kept plan is keyed by the catalog's version, which every GRANT,
      REVOKE, role DDL and OWNER TO bumps, and by SET ROLE's role.
  - **Writing** (`dmlCheck`):
    - INSERT, UPDATE and DELETE need their privilege on the target;
    - SELECT too where the statement reads rows: a WHERE, RETURNING, a SET
      that reads a column, ON CONFLICT DO UPDATE (which needs UPDATE as
      well);
    - COPY FROM needs INSERT, and COPY TO is a query.
  - **Sequences:** nextval and setval need USAGE or UPDATE, currval USAGE
    or SELECT, checked when the statement binds the sequences it names.
  - **DDL:** CREATE TABLE, VIEW and SEQUENCE need CREATE on the schema.
    ALTER, DROP, CREATE INDEX, RENAME and OR REPLACE need the owner. CREATE
    SCHEMA needs a superuser (PostgreSQL: the database's CREATE). DROP
    SCHEMA needs the schema's owner.
- **The statements:**
  - `GRANT privileges | ALL ON [TABLE] t, ... | SEQUENCE s, ... | SCHEMA s,
    ... | ALL TABLES IN SCHEMA s | ALL SEQUENCES IN SCHEMA s TO role |
    PUBLIC | CURRENT_USER, ...`, and REVOKE ... FROM. The grant is the
    owner's to give. A privilege that does not fit the object is 0LP01, an
    unknown role 42704. ALL TABLES IN SCHEMA means the tables and views
    there now.
  - `GRANT role TO role` and REVOKE: a superuser's to give, with cycles
    refused (0LP01).
  - `ALTER TABLE | VIEW | SEQUENCE | SCHEMA name OWNER TO role`: a
    superuser's, or the owner's when it is a member of the new owner.
  - `CREATE SCHEMA [name] AUTHORIZATION role`.
  - `GRANT ... ON DATABASE` is accepted with no effect: lexdb has no
    database privileges, so everyone may connect.
  - `SET [SESSION] ROLE name | NONE`, `RESET ROLE`: the session's user
    must be a member of the role, or a superuser.
  - `SET SESSION AUTHORIZATION name | DEFAULT`, `RESET SESSION
    AUTHORIZATION`: for a superuser's login only. Both are restored by a
    block's ROLLBACK, as `search_path` is.
  - `current_user` is the current role, and `session_user` the session's
    user.
- **Keeping grants with their objects.**
  - A dropped object's grants go with it, so a new table of the same name
    gets none of them.
  - A rename, SET SCHEMA, a schema's rename and a role's rename carry the
    owner and grants along.
  - DROP ROLE is refused while the role owns something (2BP01). Its grants
    and memberships go with it, where PostgreSQL asks for them to be
    revoked first.
  - Renaming a schema that holds a view, or that holds a table a view
    reads, is refused, as a view keeps names as text (9.82). This also
    stops 9.82's schema rename from treating a view's row as a table's.
- **The catalog:**
  - `pg_class.relowner` and `relacl` (PostgreSQL 16's aclitem text:
    `boot=arwdDxt/boot,team=ar/boot`), and `pg_namespace.nspowner` and
    `nspacl`;
  - `pg_roles` with each role's OID, and `pg_auth_members`;
  - `pg_tables.tableowner` and `pg_views.viewowner`,
    `information_schema.table_privileges`, and `pg_get_userbyid`;
  - `has_table_privilege`, `has_schema_privilege`,
    `has_sequence_privilege` and `has_any_column_privilege`, with or
    without a role, by name or OID, true if any privilege named is held.
    They read the bound catalog, roles and grants included.
  - psql's `\dp`, `\du` and `\dn+` show what PostgreSQL's psql shows.

**Tests.**
- `exec_privs`: 106 statements generated from PostgreSQL 18, all the same.
  A superuser acts as roles through SET ROLE, and the test covers:
  - each DML statement, and when each needs SELECT as well;
  - schema USAGE and CREATE, ALL TABLES IN SCHEMA;
  - a view read as its owner; membership given and taken;
  - owners: a role's own table, view and index; OWNER TO; who may not ALTER
    or DROP;
  - a sequence's USAGE; the catalog functions and views;
  - the errors, and DROP ROLE's dependency.
- `exec_privsx`, by hand: lexdb's own answers. These are SET ROLE undone
  by ROLLBACK, SET SESSION AUTHORIZATION, grants following renames, a new
  table of an old name with none, a view of a view read as each owner, and
  DROP ROLE.
- `wire_auth`: a role that logs in by SCRAM is refused, then granted
  SELECT but not UPDATE. A prepared statement made as a superuser is
  refused after SET ROLE, and works again after RESET ROLE.

**Not done:**
- column privileges (`GRANT SELECT (a) ON t`), grant options (`WITH GRANT
  OPTION`), and `WITH ADMIN OPTION` and membership options;
- `ALTER DEFAULT PRIVILEGES`, `REASSIGN OWNED`, `DROP OWNED`;
- `CREATEROLE` and `CREATEDB` as their own attributes: a superuser does
  their work;
- row security (policies);
- the USAGE a serial column's sequence needs for an INSERT (PostgreSQL asks
  for it);
- REFERENCES, checked when a foreign key is made;
- privileges on functions and types.

### 9.84 COPY: lines sent as they are made; what a bulk load keeps

The user's request: COPY's speed and memory, before migrations and row
locking. Measured with psql's `\copy` of 1M rows of three columns (26 MB:
`id int primary key, n int, s text`), on a fresh data directory, the
server's peak RSS from `/proc`:

| | before | after | PostgreSQL 18 |
|---|---|---|---|
| `\copy from` | 1.55 s, 512 MB | 1.07 s, 339 MB | 0.57-0.87 s |
| `\copy to` | 0.76 s, 813 MB | 0.41 s, 57 MB | 0.11 s |

**COPY TO is sent as it runs.** Before, the query's rows were made whole,
then a second copy of them as lines, then sent.
- `Session.runOut` runs a COPY TO with `out`, a closure the wire gives:
  `out(n, b)` gets `b`, CopyData messages for a query of n columns, about
  64 kB at a time. The executor frames the messages, a line each, as
  PostgreSQL sends them (psycopg reads a row per message). The wire sends
  CopyOutResponse before the first part and CopyDone after the last.
- A closure cannot be stored (SPEC 4.6), so `out` is a parameter from
  `runIn` down to `copyStmt`. The wire's closure uses its connection while
  the session runs: the session is moved out of the Wire for the run
  (`parkedSession` holds its place).
- `eachRow` gives a planned SELECT's rows to a callback. A plain query
  (no sort, grouping, DISTINCT, window, set operation, OFFSET or
  set-returning function in its list) gives each row as the scan reads it,
  so nothing is kept. Any other query is made whole first, as before; only
  the copy as lines is saved.
- An error after lines went out is an ErrorResponse with no CopyDone, as
  in PostgreSQL. A snapshot too old (72000) is not retried once lines have
  been sent.
- A value with nothing to escape is added whole. Before, every byte was
  looked at and added one at a time.
- `Wire.flush` writes its buffer's bytes (`StrBuf.view`, new). Before, it
  copied them twice (`toStr`, then `writeStr`). This holds for every
  result, not only COPY's.

The 57 MB left is the table's pages read into the cache. The time left is
the scan's per-row cost (decoding, `eval`, `text` per value), which every
query pays.

**COPY FROM: where the memory went**, measured at each step:

| step | RSS before | RSS after |
|---|---|---|
| input held | 34 MB (61 MB peak while it came) | the same |
| rows written, before the commit | 290 MB | 211 MB |
| peak during the commit | 473 MB | 347 MB |
| left after it | 202 MB | 171 MB |

Four changes:
- **A transaction's writes are indexed per tree, by their own key**
  (`Txn.idxTrees`, `Txn.idx`). Before, there was one map keyed by a new
  string `"tree:key"` per write.
- **Reads of keys in order, with no key of the tree between them, are one
  range.**
  - An insert reads its key first (the unique check), and each read was a
    mark with a string of its own: 1M marks for 1M rows.
  - Now a read just after the last one widens it, when the leaf shows no
    key between them, or the tree is empty. The leaf's key before the new
    one is checked; at a leaf's start nothing is looked for.
  - A load in key order is then a few marks.
  - The range is wider than what was read: a commit into the gap between
    two loaded keys now conflicts. That is the safe side, and a load's own
    keys fill the gap anyway.
- **A commit of more than 1024 writes to a tree logs their range**
  (`WEntry.hi`), not each key, for the checks of transactions still
  running. Before, a 1M-row commit added 1M entries to `Db.wlog`, and half
  of them stayed there afterwards.
- **A commit's log records go into room made for them once**
  (`reserveBatch`), and the batch starts with room for its frame's header.
  `frame` fills in the header and padding in place. Before, the batch grew
  by doubling, holding the old and new arrays at once, and `frame` copied
  it whole.

What is left grows with the rows: about 176 bytes a row for the
transaction's writes until it commits, and about 130 a row for the tree's
nodes in the cache after. A transaction's writes stay in memory until its
commit (4.4), and a COPY is one statement, so it is all or nothing. Loading
10M rows would hold about 1.8 GB until the commit. Bounding that would need
one of:
- a COPY committed in parts, an option rather than the default, since
  PostgreSQL's COPY is all or nothing;
- a transaction's writes spilled to disk past a size, as PostgreSQL's
  sorts spill.

Neither is built.

**COPY FROM: where the time went.** 1M rows, timed in the server: the
input took 25 ms, the rows 930 ms, the commit 410 ms. Fixed:
- **A field with no escape is a slice of the input,** not a copy made a
  byte at a time.
- **The error's CONTEXT** (`COPY t, line n`) is made only on an error, not
  for every row.
- **Each value is turned to its column's type once,** by `insertOne`.
  Before, COPY's loop did it first so that an error could name the column;
  now, on an error, the values are checked again to find which.
- **A put no longer looks for an old large value to drop** (`dropChunks`)
  when the table has no companion tree, so none can exist. It was a
  descent of the tree per row in the commit: 31% of the commit's time.
- **The commit checks that a tree still exists** once per run of writes to
  it, not once per write.

After: the rows take 740 ms and the commit 310 ms. What is left:
- the executor's per-row cost (`insertOne`, encoding the row, two map
  lookups);
- two descents of the tree per row: the unique check, and the commit's
  put;
- a third in the commit's `writeNeeds`, which makes sure every leaf a
  write needs is in the cache before it starts.

A load in key order could reuse the last leaf rather than descending again
each time; that is not done.

**Tests:**
- `wire_copy`, nine new lines, from a raw client:
  - 5000 rows in parts, each CopyData one line;
  - a sorted query (made whole first);
  - CSV with a header, and LIMIT;
  - an error after some parts went out: ErrorResponse, no CopyDone;
  - the extended protocol's COPY TO.
- `store_bulk` (new):
  - reads widened across a gap, and the gap's conflicts;
  - reads with a key between them kept apart;
  - an empty tree;
  - a 2000-write commit logged as a range (a key inside it, written or
    not, conflicts; one outside does not), and a 100-write one logged key
    by key;
  - one transaction's own writes to two trees, with the same key in each.

The suite passes (76). The benchmark scripts are in the session's scratch
folder.

### 9.85 What migration tools need

The user's next items, after COPY (9.84): first what migration tools need,
then row locking (9.86). Probed the way 9.75 did: two tools pointed at a
new lexdb.
- **Alembic 1.20** ran four revisions. They:
  - made tables with foreign keys, identity and defaults;
  - added constraints after the fact;
  - changed a column's type, NOT NULL and default, and renamed a column and
    a table;
  - made an expression index, a partial index, an enum and a JSON column.

  It then went down to base and up again.
- **Django 6.1** ran `migrate`: its own apps (auth, contenttypes, sessions,
  admin) and a shop app with foreign keys, a many-to-many through a model,
  unique_together and an index. Then its ORM ran select_for_update,
  get_or_create, update_or_create, bulk upserts, aggregates over joins,
  PROTECT and CASCADE deletes, and its introspection.

**What already worked:** ADD CONSTRAINT (FOREIGN KEY, UNIQUE, CHECK), ALTER
COLUMN TYPE, SET and DROP NOT NULL, SET DEFAULT, renames of columns and
tables, partial indexes. Alembic's first three revisions ran, and went down
and up again.

**What failed, and is now built:**
- **DEFERRABLE foreign keys.** Django makes every foreign key DEFERRABLE
  INITIALLY DEFERRED, and adds a column's with SET CONSTRAINTS ...
  IMMEDIATE after it.
  - A foreign key keeps DEFERRABLE and INITIALLY DEFERRED. In its catalog
    row they are in high bits of the byte that holds ON UPDATE, so a row
    written before reads as neither.
  - In a transaction block, a deferred key's checks are not done at the
    statement's end (9.41). They wait in `Txn.pending` until COMMIT, or
    until SET CONSTRAINTS ... IMMEDIATE names the key.
  - A check is done again from the key alone: it fails if the key is still
    missing from the parent and some row still references it. So a row
    deleted since, or written and then undone by ROLLBACK TO, leaves
    nothing to fail.
  - A failing COMMIT rolls back, as in PostgreSQL. Outside a block, a
    statement is its own transaction: its end is its commit.
  - RESTRICT is never deferred.
- **SET CONSTRAINTS ALL | names DEFERRED | IMMEDIATE.** It used to be
  accepted and ignored.
  - It now sets the mode for the transaction (`Txn.consAll`,
    `consNames`).
  - A name that is not a deferrable foreign key is 42809, and an unknown
    one 42704.
  - Outside a block it does nothing, as PostgreSQL does after its warning.
  - `pg_constraint.condeferrable`, `condeferred`, `pg_get_constraintdef`
    and `information_schema.table_constraints` show the flags.
- **An index column's options** (`varchar_pattern_ops`, DESC, NULLS
  FIRST/LAST, COLLATE). Django makes a `_like` index with the pattern
  operator class for every indexed varchar.
  - They change nothing. lexdb's text compares bytewise, which is what the
    pattern classes give PostgreSQL, and a B+tree is read either way.
  - They are kept (`Index.opts`, flag 8 in the catalog row) for
    `pg_get_indexdef` and `pg_index.indoption`, which Django's
    introspection reads.
  - An operator class not among PostgreSQL's B-tree ones is 42704.
- **CREATE INDEX CONCURRENTLY and DROP INDEX CONCURRENTLY.** They are
  accepted, and inside a block they are 25001, as in PostgreSQL. lexdb's
  build is one transaction either way.
- **ADD COLUMN with constraints.** `ADD COLUMN x int REFERENCES t`,
  `UNIQUE` and `CHECK` become the column's ADD then an ADD CONSTRAINT each.
  IF NOT EXISTS on a column already there adds neither.
- **The bitwise operators** `& | # << >>` and prefix `~`, at PostgreSQL's
  "other operator" precedence. Django's introspection uses `(option & 1)`.
- **`key` is no longer reserved.** It isn't in PostgreSQL, and Django's
  introspection names a column `key`. `for` is reserved now, as it is
  there: `FROM t FOR UPDATE` took it as t's alias.
- **A CHECK constraint's conkey** lists the columns it uses. Django finds a
  field's checks by their columns when it alters the field.

**Not built, found by the probe:**
- **Indexes on expressions** (`CREATE UNIQUE INDEX ON t (lower(email))`),
  which Alembic and Django's functional indexes write. They are refused
  with a clear 0A000. They need an index entry made from an expression, and
  the planner matching the expression where it is used.
- **CREATE TYPE ... AS ENUM**, which SQLAlchemy's Enum writes on
  PostgreSQL.
- JSON (the user's decision: not yet).

After these, Django's `migrate` runs whole and all of its ORM probe passes.
Alembic's revisions run apart from the expression index and the enum.

**Tests:**
- `exec_migrate`: 105 statements generated from PostgreSQL 18 by
  `gen_pg.py migrate`, all the same. They cover:
  - deferred keys at COMMIT, a failing COMMIT, SET CONSTRAINTS each way and
    its errors;
  - the catalog's flags;
  - ADD COLUMN with constraints;
  - index options as `pg_indexes` shows them, and `indoption`;
  - CONCURRENTLY in and out of a block;
  - the operators, `key` as a column;
  - in one session, the locking clauses, their errors and the advisory
    functions (9.86).
- `exec_fkey`'s refused DEFERRABLE became NOT DEFERRABLE INITIALLY
  DEFERRED's 42601.

### 9.86 Row locks and advisory locks

**Why lexdb needs them.** lexdb's read-write transactions are optimistic
and serializable (4.4): one that read a row another then changed fails at
its COMMIT (40001). That keeps data right, but applications written for
PostgreSQL do not retry:
- Django's `select_for_update()` (in `update_or_create`, too), Rails'
  `lock`, and SQLAlchemy's `with_for_update()` expect the second
  transaction to wait for the first, then go on with what it committed.
- Job queues (good_job, Oban, river, pg-boss) take work with `FOR UPDATE
  SKIP LOCKED`, and expect two workers never to get the same row, or to
  fail.
- Migration runners (Rails, Prisma, Flyway) take `pg_advisory_lock` so
  that two deploys do not migrate at once.

**The lock table** (`lexdb_store`: `Db.locks`, `lockAs`, `lockRow`,
`unlockAll`).
- Locks are kept in the store, not in the rows. A lock key is "tree:key"
  for a row, or "adv:" and the numbers for an advisory lock. Its holders
  are owner ids with their modes.
- The modes are PostgreSQL's four, with its table of which conflict: FOR
  KEY SHARE, FOR SHARE, FOR NO KEY UPDATE, FOR UPDATE. An owner holds a key
  once, in its strongest mode.
- An owner is a transaction (`Txn.lockId`, given at its first lock; its
  keys in `Txn.held`), or a session for advisory locks (minus its id).
- Commit and abort release a transaction's locks. Commit releases them
  after the commit is applied, so those it wakes read what it wrote. The
  session's close aborts its block, so a dropped connection's locks go
  too.
- A transaction a lock keeps out waits on a promise, woken when a holder
  releases the key, and tries again.
- Before it waits, `Db.waitFor` (owner to the key it waits for) is followed
  from the holders. A wait that would close a cycle is 40P01.

**SELECT ... FOR UPDATE | NO KEY UPDATE | SHARE | KEY SHARE [OF t] [NOWAIT
| SKIP LOCKED]:**
- **Rows are locked in the output's order, as PostgreSQL's LockRows below
  its Limit.**
  - Locking the rows as the scan chose them was tried first. It locked
    every row the WHERE passed, before ORDER BY and LIMIT, so a job
    queue's first worker locked every waiting job and the second found
    none.
  - Now each locked table's key columns are read as extra outputs after
    the query's own (`Sel.locks`, `nOut`). The query runs without its LIMIT
    and OFFSET (`Run.noLimit`), and `runLocking` locks the rows in order.
  - A row SKIP LOCKED leaves out does not count towards the LIMIT. A row
    that OFFSET passes over is locked too, as in PostgreSQL.
  - The cost is that the query makes all its rows before the first lock: a
    LIMIT does not stop the scan early.
- **A lock waited for means the rows may have changed**, so the query runs
  again holding the locks it has. It then reads what the other committed,
  where PostgreSQL re-checks the row. It reads the latest commit, not the
  block's snapshot, as UPDATE does (9.16). Outside a block it runs on a
  live transaction, not a snapshot.
- **Its reads are not noted for COMMIT's check** (`Txn.quiet`): the locks
  keep the rows it gives. Noted, they made the waiter of a lock fail at
  its COMMIT, and a SKIP LOCKED worker fail when another committed the job
  it skipped. That is PostgreSQL's READ COMMITTED for this statement; the
  block's other statements stay serializable.
- **Errors, as PostgreSQL's:**
  - with aggregates, GROUP BY, HAVING, DISTINCT, windows or a set
    operation: 0A000;
  - the nullable side of an outer join: 0A000;
  - OF a table not in FROM: 42P01;
  - NOWAIT on a held row: 55P03;
  - in a READ ONLY block, or on a replica: 25006.

**UPDATE and DELETE** take the row's lock before they write it: FOR UPDATE
for a DELETE or a key change, FOR NO KEY UPDATE otherwise.
- In a block they keep it to the end, so a FOR UPDATE in another session
  waits for the block.
- Outside one they only wait for others' locks and take none: their commit
  follows at once. A table-wide UPDATE does not fill the lock table, and
  with no locks anywhere it costs one check.
- A lock waited for runs the statement's search again, with the first
  try's reads forgotten (`Txn.forgetReads`).
- INSERT ... ON CONFLICT DO UPDATE does not lock the row it updates yet.

**Advisory locks** (`pg_advisory_lock`, `_shared`, `pg_try_*`, `*_xact_*`,
`pg_advisory_unlock`, `_shared`, `_all`; one bigint, or two ints, which
are keys apart from one bigint's):
- They use the same table, owned by the session.
- The session counts its holds in the store memo, so they are re-entrant;
  the table's lock goes with the last hold.
- A transaction's are released when no block is open after a statement,
  and all of them when the session closes.
- Unlocking one not held gives false. A NULL key gives NULL.

**Tests:**
- `exec_locks` (new): sessions in tasks of their own.
  - A waiter reads the holder's commit: 105, then 115, with no 40001.
  - Six sessions × ten increments by FOR UPDATE: 60, none failing.
  - Four SKIP LOCKED workers do twenty jobs, each once, none failing.
  - NOWAIT; a block's UPDATE holding its row; an UPDATE outside a block
    waiting.
  - A deadlock: 40P01, and the other then gets its row.
  - Locks gone with ROLLBACK and with the session's close.
  - Advisory locks between sessions; none left at the end.
- `exec_migrate` (9.85): the clauses and functions in one session.
- `exec_snapshot`: its two blocks writing one row would now wait for each
  other, in one task. It is now write skew: both read a row, one writes it
  and the other another, and the second COMMIT is still 40001.

Checked by hand with Python's psycopg against a server: the same
scenarios, and Django's select_for_update, skip_locked, nowait and of. The
suite passes (78).

**Not done:**
- statement_timeout does not end a wait for a lock, and there is no
  lock_timeout;
- `pg_locks` is not shown;
- ROLLBACK TO keeps the locks taken after the savepoint (PostgreSQL drops
  them);
- a view in FROM is not locked through.

### 9.87 COPY FROM read as it comes; batch_rows

COPY TO was sent as it ran (9.84), but COPY FROM still was not. The wire
collected the client's CopyData until CopyDone (26 MB of input held as
34 MB, 61 MB while it came), then the statement read it. A 10 GB file
needed more than 10 GB of memory.

**Read as it comes.**
- `Session.copyInFrom` takes `pull`, a closure the wire gives (threaded
  like 9.84's `out`). Each call returns a `CopyPart`: the CopyData already
  received, up to about 64 kB. The last part comes with CopyDone, or
  carries CopyFail's message, or a protocol error.
- `copyStmt` keeps what is not yet read in `buf`. A record that runs off
  its end waits for the next part, and parsing starts again at the
  record's start with the part added. That covers a text record with no
  newline yet, and a CSV quote not yet closed (CSV's only parse error).
  An end marker split across parts waits the same way.
- `Session.copyIn(data)` gives its data as one part, so `exec_copy` runs
  the same code.
- An error part way is sent at once, as in PostgreSQL. The CopyData,
  CopyDone and CopyFail that follow are dropped by the wire's `step`, as
  PostgreSQL drops them. A CopyFail after rows that were read rolls them
  back.
- **The cost:** a COPY whose data was read as it came is not run again on
  a conflict at its commit (40001), because the data is gone. Its reads
  are few since 9.84 (its keys are one range), so conflicts are rare.
- **The behaviour change:** a bad line is reported when it arrives, before
  a CopyFail that comes after it, as PostgreSQL reports it. `wire_copy`'s
  CopyFail case now sends a valid line first.

**WITH (batch_rows n), lexdb's own.** The user's choice of how to bound a
large load (instead of spilling a transaction's writes to disk):
- COPY FROM commits each n rows: the batch's foreign keys checked, then its
  commit, then a new transaction (the same path, session and now()) for
  the rest.
- It is not all or nothing: a failure keeps the batches before it. Its
  error's context says how many rows were committed.
- Inside a transaction block it is 25001, since the block commits once.
  For COPY TO it is 0A000. n must be positive (22023). It is never run
  again on a conflict.

**Measured** with 1M rows (26 MB) through psql's `\copy`:

| | before | read as it comes | with batch_rows 100000 |
|---|---|---|---|
| load | 1.07 s, 339 MB | 1.16 s, 314 MB | 1.48 s, 170 MB |

With batches, what is left is the table's tree in the cache, which its
budget bounds. The transaction's writes are flat: at most 100k rows'.
Without batches, the transaction's writes still grow with the rows, about
176 bytes a row (9.84).

**Tests:**
- `exec_copystream` (new): the same input given whole and in parts of
  every size from 1 to 7 bytes, loading the same rows. In text it has
  escapes, `\r\n`, an empty field and the end marker followed by more;
  in CSV, a header, quoted commas, quoted newlines, doubled quotes and no
  final newline.
  - An error names the same line for every split.
  - A CopyFail part way loads nothing.
  - batch_rows commits ten rows in batches of three. A duplicate key in
    the third batch keeps four rows.
  - The refusals.
- `wire_copy`: its CopyFail case changed as above.

### 9.88 Tables without a primary key; CREATE TABLE AS and SELECT INTO

The user asked whether CREATE TABLE AS worked. It did not, and it could
not: lexdb required every table to have a primary key (42P16), and a table
CREATE TABLE AS makes has none. Plain `CREATE TABLE t (a int)`, common in
schemas, scripts and pg_dump's output, was refused too. Among the two ways
offered, the user chose keyless tables first, with CREATE TABLE AS on top.

**A hidden key.**
- A table made with no primary key gets a last column ROWID: a bigint,
  GENERATED ALWAYS AS IDENTITY, which is its key.
- Its identity sequence numbers the rows, as SERIAL's does, owned by the
  table and dropped with it.
- So UPDATE, DELETE, indexes, foreign keys from it, COPY, row locks and
  replication find a row by its key, as for any table: nothing below the
  catalog changed.

**Hidden everywhere it would show.** The name starts with a NUL byte, which
no statement text can hold, so no SQL names it. `hiddenName` and
`rowidKeyed` find it, and these leave it out:
- `SELECT *` and `t.*` (and so RETURNING *, views, `INSERT ... SELECT *`);
- INSERT's and COPY's columns when none are named;
- `pg_attribute`, `pg_attrdef`, `pg_depend`, `information_schema.columns`;
- `relnatts`, the `_pkey` index and constraint, and its sequence (in
  `pg_class` and the catalog's sequences).

Attribute numbers are the columns' own places, so a column added later
leaves a gap where the hidden one is, as a dropped column leaves one in
PostgreSQL. A foreign key that references a keyless table without naming
columns is 42704 "there is no primary key for referenced table".

**CREATE TABLE [IF NOT EXISTS] t [(names)] AS query [WITH [NO] DATA]**, the
query a SELECT, VALUES or WITH ... SELECT, in parentheses or not. **SELECT
... INTO [TEMPORARY | UNLOGGED] [TABLE] t** is parsed into the same.
- The query is planned. Its output names (or the names given; more names
  than columns is 42601, a name twice 42701) and types become t's
  columns. t has no primary key.
- The query's rows are then inserted. They are made whole first, because
  the query reads in the transaction the inserts write, which may hold a
  table made earlier in the block.
- The tag is PostgreSQL's: `SELECT n`, or `CREATE TABLE AS` for WITH NO
  DATA and for IF NOT EXISTS of a table already there.
- A column keeps its type's OID, not its typmod: `varchar(20)` becomes
  `varchar`.

**DROP TABLE a, b, ...** takes several names (the generated test drops
several at its end).

**Tests:** `exec_keyless`, 55 statements generated from PostgreSQL 18 by
`gen_pg.py keyless`, all the same. They cover:
- duplicate rows, UPDATE, DELETE, RETURNING *, `t.*`, a self-join;
- a unique index and ON CONFLICT on it; a view;
- the catalog not showing the hidden column, its index, its constraint or
  its sequence;
- the foreign key refused; ADD COLUMN;
- each form of CREATE TABLE AS and SELECT INTO: names, types, WITH NO
  DATA, IF NOT EXISTS, grouping, LIMIT in parentheses, WITH, VALUES;
- in a block rolled back; a duplicate column name.

**Not done:**
- ALTER TABLE ADD PRIMARY KEY on a keyless table: still 0A000, since a
  table's key cannot change;
- CREATE TABLE AS's typmods;
- a very large CREATE TABLE AS holds its result in memory while it
  inserts;
- TEMPORARY tables (the word is accepted by SELECT INTO and ignored).

### 9.89 Indexes on expressions

Asked for after 9.88. Alembic's probe (9.85) wrote `CREATE UNIQUE INDEX ...
ON account (lower(mail))`, the usual way to make a column unique without
regard to case, and Django's functional indexes write the same. lexdb
refused them (0A000).

**What an index holds.**
- An index column is now a table column or an expression: `(expr)`, or a
  function's call, with the column options of 9.85 after it.
- `Index.cols` holds -1 for an expression, and `Index.exprs` holds the
  expressions, their column names bare as a filtered index's predicate's
  are. The catalog row keeps them as text under flag 16; an older row
  has none.
- An entry's values come from `idxVal`: the column's, or the expression
  evaluated over the row and coerced to the expression's type
  (`exprType`, from `exprOid` over the table's columns).
- Making a key can now fail, as an expression can (a division by zero on
  a new row), so `idxPrefix`, `idxEntry` and `hasNull` return a Result and
  take the table.
- An UPDATE makes an entry only for a row the index holds: outside a
  filtered index's rows, the expression need not have a value.
- A unique index's error names the expression, as PostgreSQL's does:
  `Key (lower(mail))=(ann@x.org) already exists.`
- Foreign keys, ON CONFLICT's targets and the primary key never match an
  index with an expression, because no column number is -1.

**What is refused when the index is made, as PostgreSQL refuses it:** a
column not there (42703), an aggregate (42803), a subquery or a parameter,
and a function whose value changes over time: now() and the other clocks,
random(), gen_random_uuid(), the sequence functions, current_user. That is
PostgreSQL's IMMUTABLE rule, 42P17.

**The planner.** For an expression's place in an index, `choosePath` takes
the conjuncts comparing the same expression with a value known before the
table (`exprBounds`: `=`, `<`, `<=`, `>`, `>=`, on either side).
- "The same" means the expression qualified with the table's alias
  (`qualified`) gives the same text (`sameExpr`) as the conjunct's side.
- The bound values are coerced to the expression's type (`keyType`,
  which `pathScan` and `pathScans` now use for every place). An equality
  on all of a unique index's expressions is a lookup.
- The conditions stay and are checked on each row read, so the index only
  narrows the scan.
- Not matched yet: IN lists, LIKE prefixes, and ORDER BY by an expression.

**Kept up by ALTER TABLE.**
- DROP COLUMN drops an index whose expression names the column.
- ALTER COLUMN TYPE rebuilds the indexes whose expressions name a changed
  column.
- RENAME COLUMN renames the column inside the expressions (`renameCol`, as
  for predicates).

**The catalog.**
- `pg_index.indkey` holds 0 for an expression, and `indexprs` is not NULL
  (Django's introspection tests it, then reads `pg_get_indexdef`).
- `pg_get_indexdef` and `pg_indexes` show a call as it is and any other
  expression in parentheses, as PostgreSQL does: `(lower(mail))`,
  `(((n + id)))`.

**Two fixes on the way, found by the test generated from PostgreSQL:**
- **`exprText` wrote a whole numeric constant without its point.** 2.0
  was written as 2, which reads back as an integer, so a stored expression
  (an index's, a CHECK, a predicate, a DEFAULT) changed type: `n / 2.0`
  read back as integer division. It now keeps the point.
- **`pgExprText` wrote a call's arguments with `exprText`,** which quotes
  column names: `lower("mail")`, `length("title")` in a CHECK. A call's
  arguments are now written as PostgreSQL's deparser writes them: columns
  bare, text constants typed (`''::text`), COALESCE, NULLIF, GREATEST and
  LEAST in capitals, `date_part` with a constant field as `EXTRACT(year
  FROM born)`.
- Still not matched: the casts PostgreSQL shows where an operator's types
  differ (`price * (2)::numeric`), which need the columns' types.

**Tests:** `exec_exprindex`, 49 statements generated from PostgreSQL 18 by
`gen_pg.py exprindex`, all the same. They cover:
- unique, mixed with columns, filtered and DESC expression indexes;
- a duplicate refused;
- queries using them: `=` on either side, ranges, BETWEEN, two places, IS
  NULL;
- UPDATE, DELETE and a key changed under them;
- the catalog's rows and `pg_get_indexdef`;
- a column renamed, retyped and dropped under one;
- the refusals; two unique expression indexes over the same columns.

Alembic's probe now runs past the expression index, to CREATE TYPE ... AS
ENUM (not yet).

### 9.90 Enum types

The last thing Alembic's probe (9.85) stopped at, apart from JSON: SQLAlchemy
writes `CREATE TYPE event_kind AS ENUM ('a', 'b')` for an `Enum` column.

**The type.**
- `CREATE TYPE name AS ENUM ('label', ...)` writes a catalog row keyed by
  the type's OID (`"\x02enum\x00" + oid`), holding its name and labels
  in order.
- The OID comes from the name (`lexdb_sql.nameOid("T", key)`, moved from
  lexdb_exec's `catOid` so that the parser can use it).
- The errors:
  - a type already there: 42710;
  - a label used twice: 23505 (PostgreSQL's comes from pg_enum's unique
    index);
  - an empty label, or one longer than 63 bytes: 22P02.
- An unqualified name is the type's key as given (public's). The search
  path does not choose a schema for it, because the parser makes the OID.
- Other forms of CREATE TYPE (composite, range, base) are 0A000.

**A column of the type.**
- The parser does not know the user's types, so a type name it does not
  know is now `K_ENUM` with the OID of that name (it was 42704 at once).
  The name is noted in the statement's `seqNames` after
  `lexdb_sql.TYPE_MARK`, as catalog functions mark themselves.
- `bindSeqs` then finds the type when the statement runs, or gives 42704
  "type ... does not exist".
- A value is a text, a label: `coerce` and the row layout treat the kind
  as text.
- As a row is written (`storeRow`, `updRow`: INSERT, UPDATE, COPY, upsert,
  CREATE TABLE AS), `checkEnums` reads the type's labels and refuses a
  value not among them: 22P02 `invalid input value for enum mood:
  "angry"`. That is one catalog read per enum column per row.

**Order.** An enum orders as its labels are listed, not as texts.
- When a query is planned, a comparison (`<`, `<=`, `>`, `>=`, and so
  BETWEEN) with an enum value on either side becomes a comparison of the
  labels' places: `#enumpos(x, "mood\x1fsad\x1fok\x1fhappy")`. This is
  done to WHERE and ON in `buildQuery`, before the paths are chosen.
- An ORDER BY item of an enum type becomes its place too, in
  `planSelect`.
- `#enumpos` of a text not a label is 22P02, as PostgreSQL's cast of the
  literal is.
- So an index on an enum column, which is in the labels' text order,
  serves equality and IN only. A range uses the places, read from the
  rows.
- GROUP BY needs only equality. MIN and MAX of an enum still compare
  texts (not done).

**ALTER TYPE name ADD VALUE [IF NOT EXISTS] 'v' [BEFORE | AFTER 'w'].**
- The label is put in its place. The rows hold labels, so nothing is
  rewritten and the order of those there follows at once.
- The errors: a label there is 42710, or nothing with IF NOT EXISTS; a
  neighbour not there is 22023; a type not there is 42704.
- RENAME VALUE, RENAME TO and the rest are 0A000. A rename would have to
  rewrite the rows, and RENAME TO would change the OID, which the
  columns hold.

**DROP TYPE [IF EXISTS] name, ...:**
- refused (2BP01) while a table has a column of the type;
- CASCADE, which would drop the columns, is 0A000.

**The catalog.**
- `pg_type` has a row per enum: typtype `e`, category `E`, `enum_in` and
  `enum_out`.
- `pg_enum` is new. Its sort orders are the places 1 to n, where
  PostgreSQL gives a value added BEFORE a fraction; the order is the
  same.
- `format_type` is a catalog function now, so the statement's catalog
  lines carry the enums' names (kind `e`) and psql's `\d` shows the
  column's type by name.
- `information_schema.columns` gives `USER-DEFINED` and the type's
  schema and name as its udt.
- psql's `\dT` lists them.

**Checked:**
- Alembic's four revisions, with the enum (and the expression index of
  9.89), run up, down and up again once the JSON column is taken out.
  JSON is not built (the user's decision).
- `exec_enum`: 42 statements generated from PostgreSQL 18 by `gen_pg.py
  enum`, all the same. They cover:
  - a column with a default; a label refused;
  - `=`, `<>`, `>`, IN, BETWEEN, ORDER BY and GROUP BY in the labels'
    order, and with an index;
  - ADD VALUE BEFORE, after, twice and IF NOT EXISTS; a neighbour not
    there;
  - pg_enum, pg_type, format_type, information_schema;
  - a cast, CREATE TABLE AS, the refusals, DROP TYPE of two.

**Not done:** arrays of an enum (0A000); RENAME VALUE and RENAME TO; DROP
TYPE ... CASCADE; MIN and MAX in the labels' order; privileges on types
(USAGE); a cast of a text that is not a label is checked only when it is
written or compared.

### 9.91 UPDATE ... FROM, DELETE ... USING, and TRUNCATE

Tier 1 of design/lexdb-gaps.md's joined writes: all three were syntax
errors. ORMs write them (Django's and SQLAlchemy's bulk updates, Rails'
`update_all` with joins), and so do test suites and scripts, which clear
tables with TRUNCATE.

**The statements:**
- `UPDATE [ONLY] t [*] [[AS] alias] SET ... [FROM list] [WHERE ...]
  [RETURNING ...]`;
- `DELETE FROM [ONLY] t [*] [[AS] alias] [USING list] [WHERE ...]
  [RETURNING ...]`;
- `TRUNCATE [TABLE] [ONLY] t [*], ... [RESTART IDENTITY | CONTINUE
  IDENTITY] [CASCADE | RESTRICT]`.

lexdb has no inheritance, so ONLY and `*` change nothing. The target's
alias is new as well: UPDATE and DELETE took none before.

**The parser.**
- SELECT's FROM list is now `fromList`, shared with UPDATE's FROM and
  DELETE's USING. The list holds tables, subqueries, VALUES, functions and
  joins.
- The target and its alias are read by `dmlTarget`.
- UPDATE's SET list is now `setList`, shared with ON CONFLICT DO UPDATE. So
  a plain UPDATE takes `(a, b) = (x, y)` too.

**UPDATE ... FROM and DELETE ... USING** are planned as a query over the
target and then the list (`dmlFrom`). The list is joined to the target as
a cross join, which WHERE narrows.
- **Column order.** Tables are joined in the order written, and UPDATE and
  DELETE read rows whole. So the target's columns come first in each
  joined row.
  - The row written is that prefix (`rowPrefix`).
  - SET, WHERE and RETURNING read the whole joined row, so `RETURNING *`
    gives the FROM tables' columns too, as in PostgreSQL.
- **Each target row is changed once,** even when several FROM rows join
  it, as in PostgreSQL. `onceEach` keeps the first match by primary key,
  before the rows are locked (9.86). PostgreSQL uses whichever match its
  join gives first, so the value chosen may differ when the matches
  disagree.
- **Names, as PostgreSQL resolves them:**
  - with an alias, the table's own name no longer names it (42P01);
  - a bare column in both tables is ambiguous (42702);
  - the target named again in the list is 42712.
- **Privileges.** The FROM tables need SELECT, through `buildQuery`'s check
  (9.83). The target's checks are as before.
- **RIGHT and FULL JOINs in the list are refused (0A000).** In lexdb's
  left-to-right order they would make the target's columns NULL, where
  PostgreSQL joins the list first.
- **One difference, left as it is:** an ON in the list may name the
  target. PostgreSQL refuses this (42P01).
- EXPLAIN, Describe and the guessing of parameter types (`guessParams`)
  plan the same FROM list.

**TRUNCATE** (`truncate`) gives each table, and each of its indexes, a new
empty tree, and drops the old ones (`dropTree`, which takes the large
values' companion tree too). It is the same swap as ALTER COLUMN TYPE's
rewrite (`retype`), and like PostgreSQL's new file for the table.
- No row is deleted one by one, so the transaction holds no write per row;
  the old trees are freed when it commits. A ROLLBACK undoes it.
  Concurrent transactions meet it as they meet the rewrite's DDL.
- **Foreign keys.** No foreign key action runs.
  - A table referenced from a table outside the list is refused, as in
    PostgreSQL (0A000), with its DETAIL and HINT folded into the message.
  - CASCADE adds the referencing tables, and the tables that reference
    those.
- **RESTART IDENTITY** restarts the sequences the tables own, serial and
  identity columns alike, at their start.
  - The restart is done at once, as setval is, so a ROLLBACK does not undo
    it. PostgreSQL's restart is undone.
  - Other sequences are not touched.
- **Privileges and errors.** Each table, the cascaded ones included, needs
  TRUNCATE (`D`). A view is 42809, and a table not there 42P01.
- Its tag is `TRUNCATE TABLE`. It is a write, so a replica refuses it.

**Tests:** `exec_joinwrite`, 90 statements generated from PostgreSQL 18 by
`gen_pg.py joinwrite`, all the same. They cover:
- **UPDATE ... FROM:**
  - a table, an alias on each side, a JOIN in the list, a grouped
    subquery and VALUES;
  - a row joined twice, changed once;
  - `(a, b) = (...)`, RETURNING of both sides, no row matched;
  - a block rolled back;
  - the errors: an ambiguous column, the target twice, the hidden name,
    unknown columns.
- **DELETE ... USING:** a table, an alias with RETURNING, a subquery, rows
  joined twice, and the alias hiding the name.
- **TRUNCATE:**
  - a referenced table refused, then named with its child, and CASCADE
    through two levels;
  - CONTINUE and RESTART IDENTITY on serial and identity columns, with
    another sequence left alone;
  - a block rolled back;
  - indexes, unique ones included, working after it;
  - ONLY and RESTRICT;
  - a view, and tables not there.

**Not done:**
- `WHERE CURRENT OF` (lexdb has no cursors);
- data-modifying CTEs (`WITH d AS (DELETE ... RETURNING ...)`);
- `TRUNCATE` firing ON TRUNCATE triggers (lexdb has no triggers).

### 9.92 Built-in functions and operators

PostgreSQL's functions that applications and tools call, and lexdb did not
have ("function ... does not exist", or a syntax error). The ones that need
no table or session are in a new module, `cmd/lexdb_func.lxl`; lexdb_exec
turns values to and from it (`callFn`, called from `callAt` after
`callMisc`).

**Regular expressions** (`lib/regex`, RE2 syntax):
- `regexp_replace` (flags, or PostgreSQL 16's start and N), `regexp_match`,
  `regexp_matches` (set-returning, in a select list or FROM), `regexp_like`,
  `regexp_count`, `regexp_instr`, `regexp_substr`, `regexp_split_to_table`
  (both places) and `regexp_split_to_array`.
- `substring(x FROM pattern)`: the first group's match, or the whole match.
- **PostgreSQL's rules, kept:**
  - the flags g i c n m s p w q x (x: white space and comments dropped
    outside brackets); another is 22023;
  - without n, `.` matches a newline. That now holds for `~` and its kin too;
  - matches are found as `setup_regexp_matches` finds them: after an empty
    match the search moves one character on, and a split skips empty
    matches at the ends and just after a match;
  - the replacement's `\1` to `\9`, `\&` and `\\`;
  - the longest match is taken (RE2's leftmost-longest mode), as an ARE
    with no non-greedy quantifier prefers; with one, the shortest;
  - `\y \m \M \Y \Z` are spelled as RE2 spells them;
  - start and N below their least are 22023; 'g' where it is refused is
    22023; a bad pattern is 2201B.

**Strings:** `lpad`, `rpad`, `split_part` (a negative field counts from the
end; 0 is 22023), `concat_ws`, `md5` (lib crypto), `format` (%s %I %L %%,
`%2$s`, widths `%10s` `%-10s` `%*s` `%*2$s`, and its errors), `chr` (0 is
54000, negative 22023), `ascii`, `initcap`, `reverse`, `starts_with`,
`to_hex`, `translate`, `quote_literal`, `quote_nullable`. The SQL forms
`substring(x FROM n FOR m)` (and FROM or FOR alone), `position(a IN b)` and
`overlay(x PLACING y FROM n [FOR m])`; the parser reads a call's FROM, FOR
or PLACING (`sqlForm`) before its commas.

**Math:**
- `mod`, `div`, `gcd` and `lcm` over integers and numeric, each of the
  type PostgreSQL gives; `width_bucket` over numeric (exactly) and double
  precision; `pi`, `degrees`, `radians`, the trigonometric functions and
  the degree ones (`sind` and the rest computed as PostgreSQL does, so
  `sind(30)` is 0.5 exactly), the hyperbolic ones; `log(x)`, `log(b, x)`.
- `x ^ y`: above `*` and `/`, below a sign, left to right, so `-2 ^ 2` is 4
  and `2 ^ 3 ^ 2` 64. Double precision, or numeric when an operand is and
  neither is a float; `power` the same.
- **numeric's own `sqrt`, `exp`, `ln`, `log10`, `log` and `^`** (they were
  0A000): each to PostgreSQL's result scale (`numeric_sqrt`'s, `ln`'s from
  `estimate_ln_dweight`, `power_var_int`'s), rounded half away from zero.
  A whole exponent is multiplied out exactly while it fits 38 digits. The
  rest is computed in `Hp`, a decimal floating point of 19 digits in a
  u128 (ln by atanh's series after halving into [1, 2), exp by Taylor's
  after taking out powers of ten, sqrt by Newton's), then rounded.

**Arrays:**
- `array_append`, `array_prepend`, `array_cat`, `array_remove`,
  `array_replace`, `array_position` (with a start), `array_positions`,
  `string_to_array` (a NULL delimiter splits into characters, a third
  argument names NULL), `string_to_table`, `array_ndims`, `array_dims`;
- `@>`, `<@` and `&&`, as calls, at `||`'s level.
- **Fixed: `||` with an array** gave a text (`{1,2}{3}`). The resolver now
  makes it array_cat, array_append or array_prepend by the sides' types
  (`arrayConcat`); a literal text or NULL beside an array is read as an
  array, as PostgreSQL reads an unknown literal (so `array['a'] || 'b'` is
  22P02 there and here). Its type is the array of the elements' common type
  (`int[] || numeric` is `numeric[]`). An expression the resolver does not
  see (INSERT's VALUES) decides the same way when a side's value starts
  with `{`.
- `ARRAY[1.0, 2]` is now `numeric[]` (its type was its last element's).
- **Elements are compared as their type.** An array is its text, so the
  resolver adds to the calls that compare elements (`TYPED_FNS`) a last
  argument, a text no SQL can hold, with the arguments' type OIDs (`HINT`).
  `array_remove(array[1.0, 2], 1)` then removes 1.0.

**Settings and the session:**
- `current_setting(name [, missing_ok])` and `set_config(name, value,
  is_local)`. A statement that calls one carries `SET_MARK` among its
  `seqNames`; the session then puts its settings in the store's memo before
  it runs (`publishSettings`), the calls read them there, and `set_config`'s
  changes are made after it succeeds (`takeSetConfigs`), through the same
  code as SET (`applySetting`). `set_config('search_path', ...)`, which
  pg_dump sends, sets the path.
- **Custom settings** (a dot in the name, `myapp.user_id`): `SET`, `SET
  LOCAL`, `RESET`, `SHOW`, `current_setting` and `set_config`. They are
  rolled back with the block; a local one (`SET LOCAL`, `is_local` true)
  goes back when the block ends.
- `pg_backend_pid()` is the session's number; `txid_current()` and
  `pg_current_xact_id()` a number from a count in the memo, the same within
  a transaction and growing.

**Formatting** (PostgreSQL's formatting.c, followed closely):
- `to_char` of a date, timestamp, timestamptz and interval: every pattern
  PostgreSQL has (with FM, TH, quoted text), in the C locale;
- `to_char` of an integer, numeric, real and double precision: 9 0 . , D G
  S MI PL SG PR FM TH V RN EEEE, PostgreSQL's NUM_processor's placing of
  the sign, blanks and `#` for overflow. A float is rounded as C's printf
  rounds its exact value (`floatFixed`: `to_char(12.345::float8, '99.99')`
  is 12.35, `0.125` gives .12), to 15 digits (6 for a real);
- `to_number`, `to_date`, `to_timestamp(text, format)` (with TZH and TZM;
  no year is 1 BC, as there).

**Tests.** `exec_funcs`, 174 statements generated from PostgreSQL 18 by
`gen_pg.py funcs`, all the same: each function's cases, NULLs, `pg_typeof`
and errors; `^`'s precedence; `||` on array literals, columns, in UPDATE and
INSERT; `@>` and `&&` in WHERE; regexp_matches and regexp_split_to_table in
FROM with aliases and ORDINALITY; settings across BEGIN, COMMIT, ROLLBACK and
SET LOCAL; txid_current within a block; to_char's number and date patterns;
the new operators in a CHECK, which keeps its text and reads it again
(`exprText` writes `~`, `@>`, `<@`, `&&` and `position` as SQL). The numeric
math was also compared over about two hundred values outside the test. The
reference server was a scratch PostgreSQL 18.6 (en_US.UTF-8). The whole
lexdb suite passes.

**Differences from PostgreSQL, left as they are:**
- **The regular expressions are RE2's:** no back references (`\1` in a
  pattern), no lookahead, and `\b` is a word boundary (an ARE's is a
  backspace); RE2 takes `(?P<name>...)`, which PostgreSQL refuses. Which
  match a pattern with both greedy and non-greedy parts takes may differ.
  A pattern is compiled on each call.
- **numeric's math** is right where the result shows up to about 17
  significant digits. Past that (many decimals in an argument, `exp(45.3)`)
  the last digits may differ, and a result over 38 digits is 22003
  (lexdb's numeric limit), where PostgreSQL gives it. Near a tie the 17th
  digit may round the other way (`sqrt(0.99)`).
- `to_char`'s L is a blank and D, G are `.` and `,`: the C locale, as
  lexdb's `lc_monetary` says (the reference cluster's en_US gives `$`).
  TM, SP and FX are read and ignored.
- to_date and to_timestamp read in PostgreSQL's lenient mode only (FX is
  ignored), and fewer of their errors are checked.
- `set_config` returns the value as given (PostgreSQL shows it normalized,
  `5s`); an unknown setting without a dot is 42704 for `set_config` and
  `current_setting`, but `SET` of one is still accepted and ignored. A
  custom setting reset after use is gone (PostgreSQL keeps it, empty).
- `pg_current_xact_id()` is a bigint (PostgreSQL's xid8).
- `gcd` and `lcm` of integers check bigint's range, not integer's.
- `to_hex` of a negative number takes integer's width from the resolver's
  type; where nothing is resolved, by the value.

**Not done:** `SIMILAR TO` and `substring(x FROM pattern FOR escape)`
(0A000; done in 9.94); multi-dimensional arrays; `array_fill`,
`array_reverse`, `array_sort`; json (a decision).

### 9.94 DISTINCT ON, FETCH FIRST, row comparisons, char(n) and other small forms

Item 2 of design/lexdb-gaps.md's proposed order: the small query forms
applications meet, each refused or a syntax error before. `JOIN ... USING`
and `NATURAL JOIN`, of the same item, are 9.93.

**DISTINCT ON (exprs).**
- Planned as PostgreSQL's `transformDistinctOnClause`. The ORDER BY items
  that are DISTINCT ON's come first, else 42P10. The DISTINCT ON
  expressions ORDER BY lacks are sorted by after it.
- Items are matched by text; a position or an output name means that
  output column's expression (`outText`), as both clauses read them.
- After the sort, the first row of each run of equal keys is kept: the
  first `donKey` sort values, NULLs equal. This is before OFFSET and LIMIT.
- Such a query always sorts: no index order, no top-N cut, not streamed.
- With FOR UPDATE it is 0A000, as in PostgreSQL.

**FETCH FIRST | NEXT [n] ROW | ROWS ONLY | WITH TIES**, after `OFFSET n
[ROW | ROWS]` or before it.
- FETCH is LIMIT. Its n is a constant, a parameter or in parentheses; 1
  when not given.
- LIMIT with FETCH, or OFFSET twice, is 42601.
- WITH TIES keeps the rows whose ORDER BY values equal the last row kept.
  Without ORDER BY it is 42601, and with SKIP LOCKED 42601, as in
  PostgreSQL. With FOR UPDATE it is 0A000 here, where PostgreSQL allows it.

**Row comparisons.** `(a, b)` and `ROW(a, b)` are the call `row`, and are
only compared. The parser expands each comparison into its fields'
(`rowCmp`), with PostgreSQL's NULL rules:
- `=` is the pairs ANDed, `<>` ORed.
- `(a, b) < (c, d)` is `a <= c AND (a < c OR (a = c AND b < d))`.
  - The first conjunct is true whenever the whole is, and lets an index on
    a serve the comparison as a range.
  - So keyset pagination, `WHERE (a, b) > ($1, $2) ORDER BY a, b LIMIT n`
    on a two-column key, reads from a's bound. b's bound is checked on
    each row read, where PostgreSQL's index starts exactly there.
- Also expanded: IN lists of rows (the equalities ORed), NOT IN, BETWEEN
  [SYMMETRIC] (`cmpOf`), IS [NOT] NULL (each field), IS [NOT] DISTINCT
  FROM.
- Rows of unequal length are 42601.

**A row against a subquery:** `(a, b) op (SELECT x, y ...)`, `IN
(SELECT ...)`, `= ANY` and `<> ALL`.
- `rowSub` makes a scalar subquery over a derived table, `(SELECT ... FROM
  (subquery) AS "#row"("#1", "#2"))`, which the row's columns reach as
  outer values.
- For op, it gives the row comparison of the one row: NULL for no rows,
  21000 for two.
- For IN, it gives the best of the rows' answers: true, else NULL, else
  false (as max over 2, 1, 0).
- It is correlated, so it runs once per outer row: no hash, no index.
- Too many or too few columns is 42601. A subquery or window call inside
  such a row is 0A000.
- A row anywhere else (`SELECT (1, 2)`) is 0A000: lexdb has no composite
  values.

**char(n), character(n), bpchar** (OID 1042; its array 1014). `char` and
`character` alone are char(1); `bpchar` has no length.
- **Values.** A value is kept and shown padded with blanks to n. An
  assignment longer than n is 22001 unless only blanks are cut; an explicit
  cast cuts anything (`bpcharOf`).
- **Casts put in by the resolver.** A value carries no type, so `resolve`
  puts in the casts PostgreSQL's types imply:
  - `#bptrim(x)` (the blanks taken off) wherever PostgreSQL casts bpchar to
    text: `||`, a cast to text or varchar, and a comparison with a text;
  - the same for the text functions (`length`, `upper`, `substr`,
    `string_agg` ...). These keep the blanks, as PostgreSQL's do:
    `concat`, `concat_ws`, `format`, `octet_length`, LIKE, SIMILAR TO, `~`,
    COALESCE, CASE, GREATEST, LEAST, the other aggregates and the window
    functions (`bpKeeps`);
  - a comparison of a char with a char, a literal, a parameter or a varchar
    compares both without their blanks (`bpCmp`). `=` between a char(n)
    column and a value pads the value to n instead (`#bppad`), so an index
    serves it; IN lists the same. NULLIF and IS DISTINCT FROM the same.
  - IN (subquery) compares without blanks on both sides (`inVal`).
- **Stored expressions:** a CHECK, an index's predicate and a DEFAULT get
  the same casts when they are evaluated (`bpEval`, `bpFix`).
- **Assignment:** a char given to a text or varchar column (UPDATE's SET,
  DO UPDATE's SET, INSERT ... SELECT) loses its blanks.
- **The catalog:** pg_type's rows; `format_type` gives `character(n)` or
  `bpchar`; atttypmod is n + 4; information_schema gives `character` and the
  lengths; psql's `\d` shows `character(3)`.

**CREATE INDEX [CONCURRENTLY] ON t (...)** without a name takes
PostgreSQL's (`chooseIndexName`, after `ChooseIndexName`).
- The name is t, the columns' names joined by _, and `idx`: `t_a_b_idx`.
- An expression's name (`indexColName`) is its call's name (`t_lower_idx`),
  a cast's operand's (else its type's), `case`, or `expr`.
- A name given twice is numbered: `t_a_a1_idx`.
- It is cut to 63 bytes as `makeObjectName` cuts, the longer part first.
- While a relation of t's schema has the name, `idx1`, `idx2` and on are
  tried.
- A unique index is `_idx` too, as PostgreSQL's CREATE UNIQUE INDEX.
- IF NOT EXISTS without a name is 42601.

**SIMILAR TO, NOT SIMILAR TO [ESCAPE e], `substring(x SIMILAR p ESCAPE
e)`, `substring(x FROM p FOR e)`** (`lexdb_func.similarRe`). The pattern
is turned into a regular expression as PostgreSQL's `similar_to_escape`
turns it:
- `%` is `.*`, `_` is `.`, `(` is `(?:`; `.`, `^`, `$` and `\` are literal;
  a bracket is passed as it is;
- the escape character makes the next character literal (a letter: its
  class, `\d`). The default is `\`; `''` means none; a longer one is 22025;
- the whole is anchored, `^(?:...)$`, and `.` matches a newline;
- two escape-double-quotes divide it, `^(?:a){1,1}?(b){1,1}(?:c)$`, and
  substring gives b; a third is 2200C.

**x [NOT] LIKE | ILIKE ANY | SOME | ALL (array or subquery)** is the call
`any like`, `all not like` and the like.
- The NOT is each element's, as in PostgreSQL.
- `quantified` gives ANY's and ALL's NULL rules.
- A subquery is read as `ARRAY(subquery)` (`arrayOfSub`).
- `x op ANY | ALL (subquery)` for the other comparison operators is done
  the same way. It was 0A000 (only `= ANY` and `<> ALL` are IN), so
  exec_any's expectation changed.

**BETWEEN SYMMETRIC** is `(x >= a AND x <= b) OR (x >= b AND x <= a)`, as
PostgreSQL's parser writes it. ASYMMETRIC is accepted.

**percent_rank() and cume_dist()** are double precision, computed as
floats (they were numeric). exec_window's described type changed.

**VACUUM, ANALYZE (ANALYSE), CHECKPOINT, REINDEX and CLUSTER** are
`S_MAINT`. lexdb has nothing for them to do, so they are checked as
PostgreSQL checks them, do nothing, and give its tags (`maint`).
- **The forms:**
  - `VACUUM [(options)] [FULL] [FREEZE] [VERBOSE] [ANALYZE] [[ONLY] t
    [(cols)], ...]`, and ANALYZE the same;
  - `REINDEX [(options)] {INDEX | TABLE | SCHEMA | DATABASE | SYSTEM}
    [CONCURRENTLY] [name]`;
  - `CLUSTER [(options)] [VERBOSE] [t [USING index]]`.
- **The checks:**
  - an unknown option is 42601;
  - columns without ANALYZE, FULL with PARALLEL, and REINDEX SYSTEM
    CONCURRENTLY are 0A000;
  - a table not there is 42P01;
  - a column not there is 42703, and one named twice 42701;
  - an index not there is 42P01, or 42704 for CLUSTER; an index not the
    table's is 42809;
  - a schema not there is 3F000; a database other than lexdb 0A000;
  - REINDEX and CLUSTER of a view are 42809 (VACUUM and ANALYZE accept a
    view, where PostgreSQL warns).
- `t_pkey` is found, though lexdb keeps no index apart from the table for
  it.
- **In a block, 25001:** VACUUM; REINDEX CONCURRENTLY, DATABASE and SYSTEM;
  CLUSTER without a table.

**GROUP BY ROLLUP, CUBE, GROUPING SETS and (), GROUP BY DISTINCT, and
GROUPING()** are built.
- **The parser** (`groupBy`, `groupItem`) crosses the items' sets: ROLLUP's
  prefixes; CUBE's subsets, the larger first as PostgreSQL lists them, at
  most 12 elements; GROUPING SETS' items one after another, nested ones
  too.
  - An element may be `(a, b)`; `GROUP BY (a, b)` is `a, b`.
  - Each expression goes in `group` once, and `gsets` holds the sets as
    places in it.
  - DISTINCT drops a set listed again.
- **The planner** makes, per set, its select list, ORDER BY and HAVING
  (`setSubst`):
  - an expression grouped by but not in the set is NULL;
  - GROUPING(a, ...) is its bits, the first argument's highest, 1 for an
    argument not in the set. It is cast, so ORDER BY does not read it as a
    column's place;
  - a plain GROUP BY is one set of all, its GROUPING() 0;
  - a GROUPING argument that is not grouped by, or GROUPING without GROUP
    BY, is 42803.
- **Execution:** each row joins a group of each set, keyed by the set and
  its values (`addToGroup`). The batched grouping (9.47) does not run.
  With no rows, each empty set gives its group, so `ROLLUP(a)` over nothing
  gives one row, as in PostgreSQL.

**Tests.** `exec_forms`, 300 statements generated from PostgreSQL 18 by
`gen_pg.py forms` (a new suite, seed 94), all the same. The reference
server was a scratch PostgreSQL 18.6 (en_US.UTF-8). They cover:
- percent_rank's and cume_dist's values and types;
- each maintenance statement, its options, errors, views, and its
  behaviour in a block;
- BETWEEN SYMMETRIC with NULLs and in WHERE;
- LIKE, ILIKE and NOT LIKE ANY and ALL over arrays, NULLs and subqueries;
  `> ALL` and `< ANY` over subqueries, correlated too;
- SIMILAR TO's operators, escapes, brackets, classes and errors;
  substring's three forms and their separators;
- DISTINCT ON:
  - with ORDER BY's directions, positions and aliases, expressions,
    grouping, windows and joins;
  - LIMIT, OFFSET and FETCH, in a subquery, a CTE, a view and IN;
  - its 42P10, and FOR UPDATE;
- FETCH FIRST's forms and errors; WITH TIES with NULLs, OFFSET, grouping,
  UNION, VALUES and IN;
- unnamed indexes: columns, expressions, repeats, numbering past a table of
  the name, a schema, long names, `pg_indexes`;
- row comparisons:
  - each operator with NULLs; IN lists; IS NULL and IS DISTINCT FROM;
  - in WHERE, correlated and not;
  - against subqueries with =, <, IN, NOT IN and = ANY, and their errors;
  - keyset pagination on a two-column key, BETWEEN of rows;
- char(n):
  - casts, padding, lengths and the text functions;
  - comparisons with texts, varchars, literals and chars of other lengths;
  - a char(3) key looked up, IN lists, ranges, LIKE;
  - joins, GROUP BY, DISTINCT, aggregates, UPDATE, RETURNING, ON CONFLICT;
  - CHECK, DEFAULT and a filtered index over one; INSERT ... SELECT into
    text and varchar;
  - information_schema, `pg_attribute`, `format_type`, `pg_type`, CREATE
    TABLE AS, ALTER COLUMN TYPE;
  - IN (subquery), correlated too;
- ROLLUP, CUBE, GROUPING SETS (nested, mixed with plain columns, DISTINCT),
  `()`, GROUPING with its errors, HAVING, FILTER, ORDER BY GROUPING, no
  rows, char columns.

The whole lexdb suite passes.

**Differences from PostgreSQL, left as they are:**
- **char:**
  - ORDER BY, GROUP BY, DISTINCT, MIN, MAX, GREATEST and LEAST compare the
    padded values. For a char(n) column's values, all n long, that is the
    same order, except where a character below the blank (a tab) follows a
    common start. For bpchar without a length, `'a'` and `'a '` are two
    groups where PostgreSQL has one.
  - A range (`<`, `>`, BETWEEN) on a char column, and an index on an
    expression over one, do not use the index: the resolver's casts change
    the expression. The results are right.
  - The elements of an array of char(n) are not padded.
  - `pg_get_constraintdef` shows `'x'::text` where PostgreSQL shows
    `'x'::bpchar`.
  - INSERT ... VALUES of a char expression into a text column keeps its
    blanks.
- **SIMILAR TO's substring:** PostgreSQL's ARE makes its first part as a
  whole as short as can be. Here each of that part's quantifiers is made
  non-greedy, under Perl's rules. Patterns whose first part has
  alternatives may divide otherwise. The regular expressions are RE2's
  (9.92).
- **Rows against subqueries** run once per outer row.
- **CLUSTER t without USING** is accepted. PostgreSQL gives 42704 unless t
  was clustered before; lexdb keeps no clustered index.
- **The maintenance statements:**
  - those not in a block are accepted in a read-only transaction and on a
    replica;
  - a catalog table (`VACUUM pg_class`) is 42P01.
- **FOR UPDATE with WITH TIES** is 0A000.
- **Index names** come from lexdb's own call names, which differ for a few:
  `trim` is `btrim`, `extract` is `date_part`.

**Not done:**
- window functions in a query with grouping sets (0A000);
- the primary key's functional dependency with grouping sets (a column must
  be grouped by);
- row values outside comparisons (composite types);
- `(SELECT x, y) = (a, b)` with the subquery on the left.
