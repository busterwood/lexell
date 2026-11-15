# lexdb against PostgreSQL and SQL Server: the benchmark record

The headline comparisons of lexdb with PostgreSQL and SQL Server, in one
place. Section 1 is the current state; section 4 is the record, one row per
run, newest first. Each run's detail (plans, profiles, what changed) stays
in the design note it came from, linked from its row. When a suite is run
again, add its row to section 4 and update section 1.

## 1. Now (2026-11-15)

lexdb at `518f8d9d` (`exp/replica-lag`: the log pushed to replicas, 9.135)
for sections 1.1 and 1.2; at `478d49f6` (main) for 1.3 to 1.5. PostgreSQL
18.6; SQL Server 2022 CU27. The host and the rules are in section 2.

### 1.1 OLTP: pgbench, 1M rows (`bench/sock/vspg.sh`, `bench/repl/vsrep.sh`)

PostgreSQL limited to 4 CPUs; lexdb as one process, and as its master with
3 read replicas (4 processes, lexdb's shape). The median of 3 rounds of
10 s; server CPU an operation in µs.

| | lexdb, 1 process | lexdb, 3 replicas | PostgreSQL (4 CPUs) | lexdb / PG |
|---|---:|---:|---:|---:|
| point selects, 1 client | 84,800/s, 11.7 µs | 79,700/s, 12.4 µs | 76,900/s, 8.9 µs | 1.10 × |
| point selects, 8 clients | 143,400/s, 7.0 µs | **333,900/s**, 9.0 µs | 342,700/s, 11.7 µs | 0.97 × (replicas) |
| point selects, 32 clients | 139,600/s, 7.1 µs | **367,800/s**, 8.1 µs | 270,800/s, 14.9 µs | **1.36 ×** (replicas) |
| updates, 1 client | **3,802/s**, 66 µs | | 1,651/s, 90 µs | **2.30 ×** |
| updates, 8 clients | **18,037/s**, 32 µs | | 6,831/s, 63 µs | **2.64 ×** |
| updates, 32 clients | **45,765/s**, 22 µs | | 26,552/s, 52 µs | **1.72 ×** |

Updates are on the master: replicas serve only reads. With replicas,
mixed: 8 clients updating on the master and 24 reading on the replicas give
16,500 updates/s and 307,800 selects/s together.

### 1.2 Read replicas: how soon a commit is visible (`bench/repl/probe2.py`)

From the master's commit acknowledgement to the first read on a replica
that shows it, to within one read (about 0.1 ms); replicas show only commits
the master has made durable. The acceptance test is p99 under 1 ms at the
mixed load above.

| | p50 | p90 | p99 | p99.9 | max |
|---|---:|---:|---:|---:|---:|
| idle | 0.12 ms | 0.18 | 0.25 | 0.74 | 1.05 |
| mixed load, 5 runs | 0.26-0.32 ms | 0.37-0.44 | **0.54-1.12** | 3.5-72 | 4.3-72 |

The tail is the master's checkpoint: its encode holds the master's event
loop 65 to 70 ms every 2 s (lexdb.md 9.135), which also stalls its commits.

### 1.3 Aggregates on t, 1M rows (`vspg.sh`; ms, best of 5, median of 3 rounds)

| query | lexdb | PG one core | PG 4 processes |
|---|---:|---:|---:|
| `count(*)` | **3.8** | 19.2 | 11.7 |
| 4 aggregates `WHERE n > 10` | **22.9** | 57.4 | 26.0 |
| `sum(v)` with three conditions | 26.0 | 46.3 | **22.5** |
| `GROUP BY g`, 3 aggregates | **31.1** | 84.1 | 36.4 |
| `GROUP BY n WHERE v % 2 = 0` | 46.7 (32 to 47) | 60.0 | **35.5** |

lexdb runs a query on one thread. The last two vary between rounds (q4 30
to 66 ms over the day, q5 22 to 47), most likely the master's checkpoint
landing in them. The results are checksummed and the same on both.

### 1.4 Analytic queries: 35 queries over w, d, t, cr (`saved/vec/bench.py`; lexdb-engines.md 7)

| geometric mean, 34 queries | lexdb / PostgreSQL |
|---|---:|
| server CPU, PostgreSQL on one core | **0.78** |
| wall time, PostgreSQL on one core | 0.82 |
| wall time, PostgreSQL at 4 processes | 1.30 |

23 of 34 level or ahead on one core. Behind: returning every column of 1M
rows (1.7 ×), hashing text keys (1.2 to 1.7 ×), windows (1.4 ×), 20k
single-statement point lookups (1.4 ×). Against 4 processes PostgreSQL's
parallel aggregates and hash joins are 2.3 to 4.6 × faster.

### 1.5 Bulk loads and commits (lexdb.md 9.133)

| `\copy` / `bcp -c`, 1M rows unless said | lexdb | PostgreSQL 18 | SQL Server bcp |
|---|---:|---:|---:|
| narrow: int key, int, text | **0.55 s** | 0.58 s | 1.17 s |
| wide: 12 columns, 174 MB | **1.48 s** | 1.79 s | 3.34 s (2.84 TABLOCK) |
| wide, 2 secondary indexes | 7.11 s | **4.81 s** | 7.40 s |
| wide, no key | 3.29 s | **1.39 s** | 2.28 s |
| narrow, 10M rows | **5.32 s** | 5.81 s | 10.86 s |

| single-row autocommit inserts (pgbench `ins.sql`) | lexdb | PostgreSQL |
|---|---:|---:|
| 1 client | **3,843/s** | 1,577/s |
| 4 clients | **9,359/s** | 3,354/s |
| 16 clients | **33,976/s** | 13,073/s |

`INSERT ... SELECT generate_series` loads (`vspg.sh`): acct (2 ints) lexdb
1.26 s, PostgreSQL 0.90; t (4 ints, a text) 2.54 s and 1.07.

## 2. Host and rules

- **Host:** AMD Ryzen 7 8745HS (8 cores, 16 threads), 46 GB, bare-metal
  Linux 7.2.15 (Arch/Omarchy). NVMe WD Blue SN570 1 TB (a consumer drive: no
  power-loss protection, volatile write cache, FUA), under LUKS (dm-crypt),
  btrfs; I/O scheduler kyber. Every data directory is NOCOW (`chattr +C`).
- **PostgreSQL 18.6:** `shared_buffers` 1 to 4 GB (all data in memory),
  otherwise its defaults: `fsync`, `synchronous_commit` on,
  `wal_sync_method = fdatasync`.
- **SQL Server 2022 CU27** (Developer, the `lxl-mssql` podman container,
  `lexell/tools/mssql_container.sh`), database in SIMPLE recovery: a
  reference, not tuned.
- **lexdb:** its defaults (io_uring, the O_DSYNC log, the page file through
  the kernel's cache).
- **The user's rules:**
  - PostgreSQL in parallel is capped at 4 processes, lexdb's shape (a main
    process and 3 replicas): `max_parallel_workers_per_gather = 3`,
    `max_parallel_workers = 3`, and 4 CPUs (`CPUQuota=400%`) for many
    clients. Figures with all its CPUs are not comparable (before
    2026-11-15).
  - One benchmark at a time, on a quiet machine (load under 1).
  - Results are checked: row counts, checksums, or column sums.
- **Warm vs cold:** every figure here is warm (data in memory) unless it
  says cold.

## 3. The suites, and how to run them

| suite | command | what |
|---|---|---|
| OLTP and aggregates | `lexell/bench/sock/vspg.sh LEXDB WORKDIR 3 10 1 8 32` | pgbench point selects and updates (prepared, Unix sockets), five aggregates, two loads; each server a systemd unit, its CPU from the cgroup |
| read replicas | `lexell/bench/repl/vsrep.sh LEXDB WORKDIR OUT` (WORKDIR: vspg.sh's) | 3 replicas: point selects, the mixed load, the lag probe |
| analytic queries | `~/Work/lexdb-bench/saved/vec/bench.py` over `~/Work/lexdb-bench/hp/q.txt` (`.../2026-11-15-refresh/query_run.sh`, `cmp.py`) | 35 queries over w (1M), d, t (1M), cr; the scratch PostgreSQL `saved/pg18` |
| bulk loads | `.../2026-11-15-refresh/copy_run.sh` (`bench.py`, `bcp.sh`, `gen.py`) | `\copy` and `bcp` of generated files |
| commits | pgbench `-M simple -f ins.sql -c N -T 10` | single-row autocommit inserts |

The raw results of each run: `~/Work/lexdb-bench/saved/results/<date>-*/`.
The TPC-H-like workload (`design/experiments/workload.lxl`) compares
lexdb's own planners, not engines (lexdb-optimizer.md 34, 46).

## 4. The record

Newest first. lexdb / PostgreSQL ratios above 1 favour lexdb for rates,
below 1 for times.

| date | lexdb | suite | headline | detail |
|---|---|---|---|---|
| 2026-11-15 | 518f8d9d | OLTP, replicas | 3 replicas: point selects 333,900 / 367,800/s at 8 / 32 clients (PG at 4 CPUs 342,700 / 270,800); updates 2.3 to 2.6 × PG; replica lag p50 0.28 ms, p99 1.12 | this page, 1.1, 1.2; lexdb.md 9.135 |
| 2026-11-15 | 518f8d9d | replica lag | under the mixed load p50 0.26-0.32 ms, p99 0.54-1.10 (before: p50 4.6, p99 355, max 1.08 s) | lexdb.md 9.135 |
| 2026-11-15 | 478d49f6 | OLTP, aggregates | one process: point selects 83,000 / 138,500 / 127,000/s (12 to 26% below 11-11); updates 3,713 / 17,630 / 41,100/s (2.3 / 2.6 / 1.6 × PG at 4 CPUs); aggregates ahead of PG one core on all five | lexdb.md 9.134 |
| 2026-11-15 | 478d49f6 | analytic queries | lexdb / PG one core 0.78 (CPU), / PG 4 processes 1.30 (wall); on settled data, column leaves throughout | lexdb-engines.md 7 |
| 2026-11-15 | 478d49f6 | bulk loads, commits | 1M narrow 0.55 s (PG 0.58, bcp 1.17); wide 1.48 s (1.79, 3.34); 10M 5.32 s (5.81, 10.86); commits 3,843/s against 1,577 | lexdb.md 9.133 |
| 2026-11-13 | (section 6 of lexdb-engines.md) | analytic queries | lexdb / PG one core 0.72 (CPU), / PG 4 processes 1.28 | lexdb-engines.md 6 |
| 2026-11-13 | (9.118) | bulk loads | 1M narrow 1.23 s (PG 0.55, bcp 1.11); wide 5.15 s (1.96, 3.19); 10M 14.3 s (5.93, 10.3) | lexdb.md 9.118 |
| 2026-11-12 | 25a7b4e2 | analytic queries | 15 queries, lexdb 1.4 to 12 × slower than PG on one core, before the batch work | lexdb-engines.md 1 |
| 2026-11-11 | (9.67) | OLTP, aggregates | point selects 94,700 / 173,900 / 172,300/s (PG with every CPU 80,100 / 489,800 / 710,900); updates level with PG (1,663 / 6,690 / 26,140); aggregates 1.1 to 1.8 × PG one core; not capped | lexdb.md 9.67 |
