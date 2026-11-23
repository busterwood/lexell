# lexdb against PostgreSQL and SQL Server: the benchmark record

The headline comparisons of lexdb with PostgreSQL and SQL Server, in one
place. Section 1 is the current state; section 4 is the record, one row per
run, newest first. Each run's detail (plans, profiles, what changed) stays
in the design note it came from, linked from its row. When a suite is run
again, add its row to section 4 and update section 1.

## 1. Now (2026-11-23)

**Refresh at `4506a2e8` (main, after the compiler work of opt-experiments.md
17-19: integers written into string chains, drop loops, recursion inlined
once, records that never escape kept in a local, small allocations inline),
pinned (section 2), boost on except for TPC-H (run.sh's fixed clock);
PostgreSQL re-run on every suite; results in
`~/Work/lexdb-bench/saved/results/2026-11-23-refresh/` (`run_all.sh`).**

| | 2026-11-18 | 2026-11-23 | PostgreSQL today |
|---|---:|---:|---:|
| point selects, 1 / 8 / 32 clients (1 process) | 88,000 / 151,000 / 145,000/s | **92,300 / 164,800 / 160,100/s** | 82,100 / 448,500 / 408,400/s |
| point selects, 3 replicas, 1 / 8 / 32 clients | 87,000 / 334,000-340,000 / 401,000/s | 91,000 / 363,000-368,000 / **434,000-439,000/s** | (4 cores: above) |
| updates, 1 / 8 / 32 clients | 3,691 / 16,687 / 38,711/s | 3,654 / 16,400 / 42,300/s | 1,644 / 6,735 / 26,260/s |
| mixed: replica selects / master updates | 321,000-324,000 / 15,000-15,400/s | 347,600-349,600 / 15,100-15,300/s | |
| commit latency p50 / p99 / p99.9 / max (8 clients) | 0.42 / 1.38-1.40 / 4.2-4.3 / 9.2-9.6 ms | 0.44 / 1.35-1.40 / 3.84-3.86 / 8.4-9.9 ms | |
| replica lag under the mixed load, p50 / p99 | 0.26-0.29 / 0.39-0.46 ms | 0.24-0.26 / 0.49-0.55 ms | |
| 35 analytic queries, lexdb CPU / PG one core, lexdb wall / PG 4 processes | 0.69 / 1.19 | **0.54 / 1.04** (33 of 35 level or ahead of one core) | |
| TPC-H SF1, summed (boost off) | 8,910 ms (11-22, PG not re-run) | 8,943 ms | 14,610 one core / 8,818 four processes |
| COPY narrow / wide / wide + 2 indexes / no key / 10M narrow (not pinned) | - / 1.54 / 6.74 / 3.16 / 5.51 s | 0.46 / 1.44 / 6.31 / 2.98 / 4.85 s | 0.59 / 1.81 / 4.74 / 1.52 / 5.72 s |
| COPY peak RSS, wide / wide + 2 indexes / 10M narrow | 758 / 1,638 / - MB | 764 / 1,680 / 3,256 MB | |

- **The analytic ratios** are each run's median CPU (lexdb against PG one
  core) and median wall (lexdb against PG four processes), geometric mean
  over the 35 queries; 2026-11-18's files give 0.69 by this method (0.63
  was recorded then by another). lexdb's own CPU is 16% lower than on
  2026-11-18 (geometric mean): the text joins 28-33% (`join_text_rows` 93
  to 63 ms, `join_text_agg` 90 to 60, `join_text_group` 141 to 101), `minmax_text` 86 to 57, `window`
  195 to 122. PostgreSQL's figures moved within 2%.
- **Point selects** +5 to +10% on one process and +5 to +9% with replicas,
  where they are now above PostgreSQL on the same four cores at 32 clients
  (434,000-439,000 against 408,400). The compiler work of opt-experiments.md
  17-19 moved the in-process instructions per select by less than 0.5%; the
  rest of the change is the lexdb work since 2026-11-18.
- **Updates** at 32 clients 38,700 to 43,500 over the rounds (median 42,300):
  1.6 times PostgreSQL. Commit latency p99 was still the 1.35-1.40 ms of the
  owned-string migration; the checkpoint's steps of one leaf (not two) bring it
  to 0.97-0.98 ms (the row of the record after this one; lexdb.md 9.136).
- **TPC-H**: lexdb on one core level with PostgreSQL on four processes in
  total (8,943 against 8,818 ms), geometric mean 0.67 against one core
  (section 1.6).
- **Aggregates** (vspg; ms, median of the three rounds): lexdb 2.7 / 25.7 /
  28.6 / 67.0 / 60.6 against PG one core 19.8 / 58.3 / 47.3 / 86.6 / 60.6
  and PG four processes 15.5 / 26.5 / 22.5 / 36.5 / 30.0. q4 and q5 overlap
  the update rounds' checkpoints as before (q5 26.3 ms in round 1, 60.6 and
  65.5 after).
- **SQL Server** was not re-run (its container was down): no bcp column.

### 1.00 The 2026-11-18 refresh

**Refresh at `eababf57` (main), pinned (section 2), boost on as before;
results in `~/Work/lexdb-bench/saved/results/2026-11-18-refresh/`.** The
sections below (1.1 to 1.5) are the 2026-11-15 figures; what changed:

| | 2026-11-15 | 2026-11-18 | PostgreSQL today |
|---|---:|---:|---:|
| point selects, 1 / 8 / 32 clients (1 process) | 80,100 / 133,900 / 128,400/s | **88,000 / 151,000 / 145,000/s** | 81,000 / 445,000 / 405,000/s |
| point selects, 3 replicas, 1 / 8 / 32 clients | 79,600 / 244,000-346,000 / 377,000/s | 87,000 / 334,000-340,000 / **401,000/s** | (4 cores) |
| updates, 1 / 8 / 32 clients | 3,726 / 17,846 / 40,124/s | 3,691 / 16,687 / 38,711/s | 1,660 / 6,859 / 26,700/s |
| mixed: replica selects / master updates | 317,000-319,000 / 16,500/s | 321,000-324,000 / 15,000-15,400/s | |
| commit latency p50 / p99 / p99.9 / max (8 clients) | 0.42 / 0.88-0.91 / 3.9-4.4 / 8.0-11.1 ms | 0.42 / **1.38-1.40** / 4.2-4.3 / 9.2-9.6 ms | |
| replica lag under the mixed load, p50 / p99 | 0.23-0.26 / 0.80-1.27 ms | 0.26-0.29 / **0.39-0.46** ms | |
| 35 analytic queries, lexdb / PG one core (CPU) / PG 4 processes (wall) | 0.78 / 1.30 (not pinned) | **0.63 / 1.19** (pinned; 25 of 35 level or ahead) | |
| COPY wide / wide + 2 indexes / no key / 10M narrow (not pinned) | 1.48 / 7.11 / 3.29 / 5.32 s | 1.54 / 6.74 / 3.16 / 5.51 s | 1.79 / 4.54 / 1.32 / 5.53 s |
| COPY peak RSS, wide / wide + 2 indexes | 583 / 1,181 MB | **758 / 1,638 MB** | |

- **Updates** fell 52% at 32 clients with the owned-string migration
  (`9aeeeadb`: a leaf copied for snapshots per update, each key and value
  a malloc); restored by `eababf57` (keys one counted array, values each
  counted). Before it: 19,300/s at 32 clients.
- **Commit latency p99** rose 0.81 to 1.39 ms with the migration (the
  pre-migration binary measured today: 0.80-0.82); `eababf57` brought the
  max back (15-18 to 9.2-9.6 ms), not p99. Not resolved.
- **COPY's peak memory** rose about 30% with the migration (580 to 740 MB
  wide, 1,178 to 1,582 MB with indexes, measured today on the old and new
  binaries; `eababf57` adds 2-4%); the time is level. A leaf's keys and
  values were slices of one string (one allocation a page, 9.13) and are
  now each their own. Not resolved.
- **Aggregates** (1.3): vspg runs them after the update rounds, and they
  overlap that load's checkpoints (q4 36 to 59 ms, q5 49 to 59 ms over the
  rounds). On a settled server lexdb is faster than before the migration
  (q4 30.5 against 37.5 ms, q5 22.0 against 26.5): measure them settled.
- **Text columns** (`d0f00b92`, review finding 2): a batch keeps a text
  column as one buffer plus offsets, and the wire writes each value's
  bytes at once (`bytesGrow`). lexdb's own CPU on the 35 analytic queries
  fell 6.7% (geometric mean; PostgreSQL not re-run): `select *` of 1M rows
  -23%, text hash joins -19 to -24%. TPC-H level (+0.7% instructions).
- **The analytic data:** `la/base2` (2026-11-15) holds a page in the
  T_LEAF format, which lexdb no longer reads since 5808f012 (it gives
  "page 23349: type 2"); `la/base3` is the same data loaded by the
  current binary (results checked against PostgreSQL's).

## 1.0 As of 2026-11-15

lexdb at `exp/ckpt-incremental` (checkpoints from a cut, lexdb.md 9.136)
for sections 1.1 to 1.3, pinned (section 2: both servers on the same four
physical cores, clients on the other four); at `478d49f6` (main, not
pinned) for 1.4 and 1.5. PostgreSQL 18.6; SQL Server 2022 CU27. The host
and the rules are in section 2.

### 1.1 OLTP: pgbench, 1M rows (`bench/sock/vspg.sh`, `bench/repl/vsrep.sh`)

PostgreSQL on 4 cores; lexdb as one process, and as its master with 3 read
replicas (4 processes, lexdb's shape), on the same 4 cores. The median of
3 rounds of 10 s (replicas: two runs); server CPU an operation in µs.

| | lexdb, 1 process | lexdb, 3 replicas | PostgreSQL (4 cores) | lexdb / PG |
|---|---:|---:|---:|---:|
| point selects, 1 client | 80,100/s, 12.4 µs | 79,400-79,900/s, 12.4 µs | 75,900/s, 9.0 µs | 1.05 × |
| point selects, 8 clients | 133,900/s, 7.5 µs | 244,200-345,800/s, 8.2-8.7 µs | **426,000/s**, 9.3 µs | 0.57-0.81 × (replicas) |
| point selects, 32 clients | 128,400/s, 7.8 µs | 376,000-377,700/s, 7.9 µs | 386,600/s, 10.3 µs | 0.97 × (replicas) |
| updates, 1 client | **3,726/s**, 74 µs | | 1,650/s, 98 µs | **2.26 ×** |
| updates, 8 clients | **17,846/s**, 34 µs | | 6,793/s, 61 µs | **2.63 ×** |
| updates, 32 clients | **40,124/s**, 25 µs | | 26,040/s, 42 µs | **1.54 ×** |

Updates are on the master: replicas serve only reads. With replicas,
mixed: 8 clients updating on the master and 24 reading on the replicas give
16,500-16,600 updates/s and 316,900-319,500 selects/s together.

Pinned, PostgreSQL's point selects are much faster than under the earlier
`CPUQuota=400%` over every CPU (426,000 against 342,700/s at 8 clients,
386,600 against 270,800 at 32): with four whole cores it no longer shares
them with its clients or SMT siblings. lexdb's replicas run 8 clients'
selects at 244,000 to 346,000/s from run to run (not yet looked at).

### 1.2 Commit latency and read replicas

The master's commit latency (`bench/sock/commitlat.sh`: the
master alone, pgbench updates, 8 clients, 20 s, every commit logged; two
runs, and one of the script). The checkpoint's 70 ms stall (lexdb.md 9.135) is gone (9.136):

| commit latency | p50 | p99 | p99.9 | max |
|---|---:|---:|---:|---:|
| before 9.136 (518f8d9d) | 0.42 ms | 0.72-0.76 | 4.2-4.5 | 70 |
| now | 0.42 ms | 0.88-0.91 | 3.9-4.4 | **8.0-11.1** |

A commit visible on a replica (`bench/repl/probe2.py`): from the master's
commit acknowledgement to the first read on a replica that shows it, to
within one read (about 0.1 ms); replicas show only commits the master has
made durable. The acceptance test is p99 under 1 ms at the mixed load
above. Two runs, pinned:

| | p50 | p90 | p99 | p99.9 | max |
|---|---:|---:|---:|---:|---:|
| idle | 0.08-0.12 ms | 0.14-0.21 | 0.55-1.46 | 2.2-2.3 | 2.2-2.4 |
| mixed load | 0.23-0.26 ms | 0.31-0.36 | **0.80-1.27** | 3.8-4.3 | 4.4-5.2 |

Unpinned (before), p99 was 0.24 idle and 0.54-1.12 under load. Pinned to 4
cores, four busy processes and the kernel's I/O workers share them, and
p99 sits about 1 ms with or without 9.136, idle too. The probe times from
the acknowledgement, so a master stall delays the acknowledgement and
hides from it: the commit latency above is where the checkpoint showed.

### 1.3 Aggregates on t, 1M rows (`vspg.sh`; ms, best of 5, median of 3 rounds)

| query | lexdb | PG one core | PG 4 processes |
|---|---:|---:|---:|
| `count(*)` | **3.9** | 19.4 | 12.1 |
| 4 aggregates `WHERE n > 10` | **24.2** | 59.7 | 26.7 |
| `sum(v)` with three conditions | 26.2 | 48.6 | **23.0** |
| `GROUP BY g`, 3 aggregates | 67.5 (63 to 69) | 88.1 | **37.6** |
| `GROUP BY n WHERE v % 2 = 0` | **23.8** | 62.3 | 35.8 |

lexdb runs a query on one thread. `GROUP BY g` took 30 to 66 ms unpinned
over the day and 63 to 69 pinned (not yet looked at). The results are
checksummed and the same on both.

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

### 1.6 TPC-H derived, SF1 (`bench/tpch/run.sh`; ms, warm, median of 3)

**2026-11-23, main `4506a2e8`, lexdb and PostgreSQL both run (boost off, the
fixed clock; one core each, PostgreSQL also at four processes; all 22 results
checked against PostgreSQL's):** lexdb summed **8,943 ms** against
PostgreSQL's **14,610** on one core and **8,818** with four processes: level
in total with four processes. Geometric mean 0.67 of one core's wall (0.63 of
its server CPU), 1.08 of four processes'; 17 of 22 level or ahead of one
core. lexdb's sum is within 0.4% of `647ce4d5`'s run (8,910), each query within
5% (q18 600 to 626, q1 1,573 to 1,607); PostgreSQL ran 2.3% faster on one core and 5.2% faster on four than in
the `01b0250c` run. Worst against one core: q20 245 / 124 (1.97), q11 91 /
61 (1.50), q10 448 / 390 (1.15), q22 101 / 87 (1.17), q15 379 / 332 (1.14).
Raw: `~/Work/lexdb-bench/saved/results/2026-11-23-refresh/tpch-out`.

| ms | lexdb `4506a2e8` | PG one core | PG four processes |
|---|---:|---:|---:|
| q1 | 1,607 | 3,452 | 874 |
| q2 | 38 | 158 | 134 |
| q3 | 524 | 545 | 350 |
| q4 | 141 | 183 | 101 |
| q5 | 160 | 311 | 172 |
| q6 | 182 | 273 | 201 |
| q7 | 408 | 571 | 282 |
| q8 | 156 | 221 | 139 |
| q9 | 1,576 | 1,732 | 746 |
| q10 | 448 | 390 | 167 |
| q11 | 91 | 61 | 61 |
| q12 | 443 | 855 | 257 |
| q13 | 683 | 776 | 777 |
| q14 | 139 | 141 | 93 |
| q15 | 379 | 332 | 332 |
| q16 | 225 | 261 | 109 |
| q17 | 22 | 538 | 533 |
| q18 | 626 | 2,743 | 2,997 |
| q19 | 37 | 40 | 37 |
| q20 | 245 | 124 | 124 |
| q21 | 711 | 817 | 285 |
| q22 | 101 | 87 | 49 |
| all 22, summed | 8,943 | 14,610 | 8,818 |


**Since, lexdb alone (2026-11-22, main `647ce4d5`, after Q8 R8 and the
descents slice), against the PostgreSQL figures of the `01b0250c` run
below (PostgreSQL not re-run):** lexdb summed **8,910 ms** (mean of two runs
alternated with main `7ff69abe`'s 9,325, its second q15 outlier left out),
against PostgreSQL's 14,960 on one core and **9,300 with four processes:
lexdb on one core is now below PostgreSQL on four**. Level or ahead of one
core on 17 of 22; geometric mean 0.64. The key searches compare 8-byte
words of the keys before the strings, and a range read's batch is sized per
range (lexdb-tpch-perf.md 4.7): q3 644 to 528, q8 198 to 157, q10 483 to
449, q20 272 to 246, q4 164 to 140, q17 28 to 22. Worst against one core:
q20 246 / 133 (1.85), q11 91 / 63 (1.44), q22 103 / 88 (1.18), q10 449 /
402 (1.12), q15 373 / 349 (1.07). Logs: `~/tpch-w/ds/logs`.

| ms | lexdb `647ce4d5` | PG one core | PG four processes |
|---|---:|---:|---:|
| q1 | 1,573 | 3,277 | 881 |
| q2 | 39 | 167 | 144 |
| q3 | 528 | 564 | 386 |
| q4 | 140 | 194 | 111 |
| q5 | 162 | 334 | 188 |
| q6 | 182 | 282 | 220 |
| q7 | 405 | 597 | 309 |
| q8 | 157 | 236 | 162 |
| q9 | 1,594 | 1,805 | 785 |
| q10 | 449 | 402 | 183 |
| q11 | 91 | 63 | 69 |
| q12 | 438 | 873 | 264 |
| q13 | 697 | 892 | 918 |
| q14 | 140 | 153 | 101 |
| q15 | 373 | 349 | 351 |
| q16 | 227 | 261 | 103 |
| q17 | 22 | 564 | 566 |
| q18 | 600 | 2,844 | 3,053 |
| q19 | 37 | 45 | 43 |
| q20 | 246 | 133 | 137 |
| q21 | 707 | 837 | 273 |
| q22 | 103 | 88 | 50 |
| all 22, summed | 8,910 | 14,960 | 9,300 |

**Since, lexdb alone (2026-11-22, main `f1623851`), against the
PostgreSQL figures of the `01b0250c` run below (PostgreSQL not re-run):**
lexdb summed **9,481 ms** (mean of two runs alternated with main
`1a561b87`'s 11,113), against PostgreSQL's 14,960 on one core and 9,300
with four processes. Since `01b0250c`: Q8 R1-R7 (the pipeline runs nearly
every query), the OR of index paths (q19 86.9 to 41.8 ms, PostgreSQL 45;
lexdb-optimizer.md 52) and conditions on a column leaf's bytes
(lexdb-tpch-perf.md 4.6: q6 176, q12 442, q7 405, q21 722, q22 115 ms).
Worst against one core now: q20 262 / 133 (1.97), q11 95 / 63 (1.52),
q22 115 / 88 (1.30), q10 503 / 402 (1.25), q3 649 / 564 (1.15). Logs:
`~/tpch-w/perf2`, `~/tpch-w/q19b`.

**Now, main `01b0250c` (2026-11-20, after optimizer Q4-Q6), the same
setup, lexdb and PostgreSQL in the same run (one run each, lexdb `-O`):**
summed 12,239 ms against PostgreSQL's 14,960 on one core; **geometric mean
0.94 on wall** (was 1.03), 0.85 on server CPU; level or ahead on 11 of 22
(was 9); against PostgreSQL's four processes 1.47 (sum 9,300; was 1.58).
Since `0f96fee9`: Q4's key-ordered index read (q4 0.9, q14 1.1, q15 2.5 to
1.8), Q6's bushy build groups (q7 1.2 from about 1.6, q21 1.3); Q5 changed
no TPC-H plan. Worst ratios against one core: q19 2.1, q20 2.1, q11 1.9,
q22 1.9, q15 1.8, q6 1.6. Results: `~/tpch-w/int/out-pgcmp-01b0250c`.

| | lexdb `01b0250c` | PG one core | ratio | PG four processes |
|---|---:|---:|---:|---:|
| q1 | 1,719 | 3,277 | 0.52 | 881 |
| q4 | 183 | 194 | 0.94 | 111 |
| q6 | 459 | 282 | 1.63 | 221 |
| q7 | 702 | 597 | 1.18 | 309 |
| q11 | 117 | 63 | 1.87 | 69 |
| q15 | 633 | 349 | 1.82 | 351 |
| q18 | 694 | 2,844 | 0.24 | 3,053 |
| q19 | 95 | 45 | 2.12 | 43 |
| q20 | 286 | 133 | 2.15 | 137 |
| q21 | 1,106 | 837 | 1.32 | 273 |
| q22 | 166 | 88 | 1.89 | 50 |
| all 22, summed | 12.24 s | 14.96 s | | 9.30 s |

**Before, main `0f96fee9` (2026-11-20), the same setup, lexdb and PostgreSQL
both run today (one run each, lexdb built with `-O`):** summed 13,435 ms
against PostgreSQL's 15,231 on one core (PostgreSQL ran 9% slower than its
18 Nov figure: the machine's state, not lexdb); geometric mean 1.03 on wall,
0.94 on server CPU; level or ahead on 9 of 22; against PostgreSQL's four
processes 1.58 (sum 9,713). q1, q8 and q17 differ from PostgreSQL only in
decimal formatting, as before. Since 18 Nov: the batch-gaps work (q16
-16%) and the dialect packages; the 20 Nov gate binaries, built without
`-O`, were about 14% slower on q1 (lexdb-layers.md 6.3, Q1). Worst ratios
against one core: q15 2.5, q20 2.2, q11 2.1, q19 2.1, q22 1.8.
Results: `~/tpch-w/int/out-pgcmp-0f96fee9`.

**Before, main `aaadeb1e` (2026-11-18), the same setup:** summed 12,984 ms
against PostgreSQL's 13,955 (one core); geometric mean 0.98, below 1 for
the first time; level or ahead on 9 of 22. The runtime's string compare
compares short strings 8 bytes at a time (no memcmp call): lexdb's B-tree
searches. Results: `~/tpch-w/int/out-main-aaadeb1e`.

**Before, main `89cf0a59` (2026-11-18), the same setup:** summed 13,524 ms
against PostgreSQL's 13,955 (one core): lexdb's sum is below PG's for the
first time; geometric mean 1.03. q7 942 ms (1.61×), q21 1,226 (1.49×) after
the hash cut (lexdb-layers.md 6.2.13); the rest within run spread of
`48c22c45`. Results: `~/tpch-w/int/out-main-89cf0a59`.

**Before, main `48c22c45` (2026-11-18):** lexdb alone, one run, boost off
(3.8 GHz), the setup below; PostgreSQL's times are its one-core run at
`94536d12` (same machine, clock and data). After the layered redesign's
pipeline (P1-P3), the owned-string migration and its review. **Geometric
mean of lexdb / PG one core: 1.05**; summed 14,083 ms against 13,955; level
or ahead on 9 of 22. Results: `~/tpch-w/int/out-main-48c22c45`.

| | lexdb `48c22c45` | PG one core | ratio |
|---|---:|---:|---:|
| q1 | 1,714 | 3,300 | 0.52 |
| q3 | 809 | 516 | 1.57 |
| q7 | 1,192 | 585 | 2.04 |
| q9 | 1,935 | 1,732 | 1.12 |
| q11 | 129 | 61 | 2.12 |
| q17 | 36 | 579 | 0.06 |
| q19 | 101 | 40 | 2.53 |
| q20 | 279 | 123 | 2.27 |
| q21 | 1,448 | 820 | 1.77 |
| q22 | 171 | 88 | 1.94 |
| all 22, summed | 14.08 s | 13.96 s | |


lexdb at `1744ef99` (main, 2026-11-16) against PostgreSQL 18.6 with
parallel query off, both pinned to CPUs 0-3, conventional secondary
indexes (`bench/tpch/indexes.sql`). **Geometric mean of lexdb / PG one
core: 3.77** (wall; 3.52 server CPU); level or ahead on 2 of 22 (q2, q17).
19 queries give PostgreSQL's checksum; q1, q8 and q17 differ in decimal
scale only. Results: `~/tpch/out-baseline-1744ef99`. The plan comparison
is `lexdb-tpch-plans.md`; the work to close the gap is `lexdb-tpch-perf.md`.

| | lexdb | PG one core | ratio |
|---|---:|---:|---:|
| q1 | 15,925 | 2,833 | 5.6 |
| q4 | 4,004 | 180 | 22.2 |
| q7 | 5,113 | 565 | 9.1 |
| q13 | 5,938 | 818 | 7.3 |
| q21 | 13,525 | 687 | 19.7 |
| q22 | 1,200 | 76 | 15.9 |
| q17 | **37** | 515 | 0.1 |
| all 22, summed | 66.0 s | 12.5 s | |

**At a fixed clock, main `94536d12` (2026-11-16):** the same setup with the
CPU boost off for both engines (3.8 GHz; `run.sh` turns it off and records
it in `config.txt`), after the first merges of the perf work (exec steps 1
and 2a, semi, joinorder, outer). **Geometric mean of lexdb / PG one core:
2.48** (wall; 2.31 server CPU; 4.51 against four processes); level or
ahead on 4 of 22 (q1, q2, q17, q18). Checksums as at the baseline.
Results: `~/tpch-w/int/out-main-94536d12-full`. The baseline column ran
with boost on, so it is up to ~20% faster than it would be at this clock:
PostgreSQL's own sum moved from 12.5 s to 14.0 s between the two.

| | lexdb `1744ef99` (boost on) | lexdb `94536d12` | PG one core | ratio |
|---|---:|---:|---:|---:|
| q1 | 15,924 | 2,527 | 3,300 | 0.8 |
| q2 | 61 | 70 | 160 | 0.4 |
| q3 | 2,642 | 2,499 | 516 | 4.8 |
| q4 | 4,004 | 666 | 201 | 3.3 |
| q5 | 1,703 | 1,166 | 280 | 4.2 |
| q6 | 1,061 | 666 | 512 | 1.3 |
| q7 | 5,113 | 1,939 | 585 | 3.3 |
| q8 | 425 | 474 | 240 | 2.0 |
| q9 | 4,296 | 5,370 | 1,732 | 3.1 |
| q10 | 1,612 | 1,826 | 681 | 2.7 |
| q11 | 197 | 231 | 61 | 3.8 |
| q12 | 1,231 | 1,508 | 944 | 1.6 |
| q13 | 5,938 | 1,226 | 789 | 1.6 |
| q14 | 696 | 807 | 161 | 5.0 |
| q15 | 1,413 | 1,239 | 620 | 2.0 |
| q16 | 580 | 703 | 260 | 2.7 |
| q17 | 37 | 45 | 579 | 0.1 |
| q18 | 2,731 | 1,268 | 1,261 | 1.0 |
| q19 | 463 | 572 | 40 | 14.3 |
| q20 | 1,140 | 1,431 | 123 | 11.6 |
| q21 | 13,525 | 8,634 | 820 | 10.5 |
| q22 | 1,200 | 745 | 88 | 8.5 |
| all 22, summed | 66.0 s | 35.6 s | 14.0 s | |

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
    `max_parallel_workers = 3`. Figures with all its CPUs are not
    comparable (before 2026-11-15).
  - **Pinned, no shared cores** (since 2026-11-15, the ckpt-incremental
    rows): the server under test (lexdb and its replicas, or PostgreSQL) on
    CPUs 0-3, their SMT siblings 8-11 idle; pgbench, psql and the probes on
    4-7 and 12-15. On this CPU a core's siblings are N and N+8
    (`/sys/devices/system/cpu/cpu*/topology/thread_siblings_list`). The
    scripts take `SERVER_CPUS` and `CLIENT_CPUS`. Before, nothing was
    pinned and PostgreSQL had `CPUQuota=400%` over all 16: those rows are
    not comparable with pinned ones.
  - One benchmark at a time, on a quiet machine (load under 1).
  - Results are checked: row counts, checksums, or column sums.
- **Warm vs cold:** every figure here is warm (data in memory) unless it
  says cold.

## 3. The suites, and how to run them

| suite | command | what |
|---|---|---|
| OLTP and aggregates | `lexell/bench/sock/vspg.sh LEXDB WORKDIR 3 10 1 8 32` | pgbench point selects and updates (prepared, Unix sockets), five aggregates, two loads; each server a systemd unit, its CPU from the cgroup |
| read replicas | `lexell/bench/repl/vsrep.sh LEXDB WORKDIR OUT` (WORKDIR: vspg.sh's) | 3 replicas: point selects, the mixed load, the lag probe |
| commit latency | `lexell/bench/sock/commitlat.sh LEXDB WORKDIR OUT` (WORKDIR: vspg.sh's) | the master alone, pgbench updates, every commit's latency (p50 to max) |
| analytic queries | `~/Work/lexdb-bench/saved/vec/bench.py` over `~/Work/lexdb-bench/hp/q.txt` (`.../2026-11-15-refresh/query_run.sh`, `cmp.py`) | 35 queries over w (1M), d, t (1M), cr; the scratch PostgreSQL `saved/pg18` |
| bulk loads | `.../2026-11-15-refresh/copy_run.sh` (`bench.py`, `bcp.sh`, `gen.py`) | `\copy` and `bcp` of generated files |
| commits | pgbench `-M simple -f ins.sql -c N -T 10` | single-row autocommit inserts |
| TPC-H derived | `lexell/bench/tpch/run.sh LEXDB WORKDIR [SF] [RUNS]` | 22 TPC-H queries over dbgen at SF1/10, conventional indexes, lexdb against PG one core and four processes; plan findings in `lexdb-tpch-plans.md` |

The raw results of each run: `~/Work/lexdb-bench/saved/results/<date>-*/`.
The TPC-H-like workload (`design/experiments/workload.lxl`) compares
lexdb's own planners, not engines (lexdb-optimizer.md 34, 46).

## 4. The record

Newest first. lexdb / PostgreSQL ratios above 1 favour lexdb for rates,
below 1 for times.

| date | lexdb | suite | headline | detail |
|---|---|---|---|---|
| 2026-11-23 | after daa96ce9 (COPY's fast path for keyless tables) | bulk loads (lexdb; PG from the day's refresh) | no primary key 2.98 to 1.50 s (PG 1.52: level); two secondary indexes 6.31 to 5.82 s (PG 4.74); narrow 0.49, wide 1.45, 10M 4.90 s (PG 0.59, 1.81, 5.72) | lexdb-copy-fast.md |
| 2026-11-23 | after 73cea2c1 (one-leaf checkpoint steps) | commit latency (master alone, 8 clients, pinned, two runs each) | p99 1.33-1.37 ms to 0.97-0.98 (steps of 1 leaf, not 2), updates +1.5%; with checkpoints held off p99 0.50 ms; leaf copies for kept versions 9.7% of server CPU | lexdb.md 9.136 |
| 2026-11-23 | 4506a2e8 | TPC-H derived, SF1, boost off, lexdb (`-O`), PG one core and PG four processes, median of 3 | summed 8,943 ms against PG one core 14,610 and PG four processes 8,818 (level in total); geometric mean 0.67 of one core (wall), 0.63 (CPU), 1.08 of four processes; 17 of 22 level or ahead of one core; worst q20 1.97, q11 1.50 | this page, 1.6 |
| 2026-11-23 | 4506a2e8 | OLTP, replicas, commit latency, aggregates (pinned) | point selects 92,300 / 164,800 / 160,100/s (+5-10%); 3 replicas 434,000-439,000/s at 32 clients, above PG on four cores (408,400); updates 3,654 / 16,400 / 42,300/s (1.6-2.4 × PG); commit p99 1.35-1.40 ms (unchanged) | this page, 1 |
| 2026-11-23 | 4506a2e8 | analytic queries (pinned), bulk loads (lexdb and PG; no SQL Server) | 35 queries: lexdb CPU / PG one core 0.54 (0.69 on 11-18 by the same method), wall / PG four processes 1.04; 33 of 35 level or ahead; lexdb CPU -16% since 11-18 (text joins -30%); COPY 0.46 / 1.44 / 6.31 / 2.98 / 4.85 s against PG 0.59 / 1.81 / 4.74 / 1.52 / 5.72 | this page, 1 |
| 2026-11-22 | 647ce4d5 | TPC-H derived, SF1, lexdb alone against the recorded PG figures of `01b0250c` | summed 8,910 ms (was 9,325 at `7ff69abe`) against PG one core 14,960 and PG four processes 9,300: below four processes for the first time; 17 of 22 level or ahead of one core; q3 528 (PG 564); worst q20 1.85, q11 1.44, q22 1.18 | this page, 1.6; lexdb-tpch-perf.md 4.7 |
| 2026-11-22 | f1623851 | TPC-H derived, SF1, lexdb alone against the recorded PG figures of `01b0250c` | summed 9,481 ms (was 12,239 at `01b0250c`) against PG one core 14,960 and PG four processes 9,300; q19 41.8 ms (PG 45); worst q20 1.97, q11 1.52, q22 1.30 | this page, 1.6 |
| 2026-11-21 | 7fec138f (branch, Q8 R7) | windows, 1M rows (row_number per partition, running sum, 10-row moving average, rank; under an aggregate and to the client), lexdb `-O` main 3aabcade vs branch, PG 18 (leader + 3 workers, `work_mem` 256MB), server on CPUs 0-3 | the pipeline's Window operator 0.77-0.91 of main's row engine, 1.03 for the partitioned row_number to the client; lexdb / PG 0.82-1.20 (time; under an aggregate: row_number per partition 0.85, running sum 1.07, moving average 1.20, rank 1.12; to the client 1.02, 1.02, 1.00, 0.82); raw: ~/Work/lexdb-bench/saved/results/2026-11-21-window-r7 | lexdb-layers.md 6.3.Q8 R7 |
| 2026-11-20 | 01b0250c | TPC-H derived, SF1, boost off, lexdb (`-O`), PG one core and PG four processes, one run each | after optimizer Q4-Q6: lexdb / PG one core 0.94 (geometric mean, wall; 0.85 server CPU), 11 of 22 level or ahead; summed 12.24 s against PG's 14.96 s; against PG four processes 1.47; worst q19 2.1, q20 2.1, q11 1.9, q22 1.9, q15 1.8 | this page, 1.6 |
| 2026-11-20 | 0f96fee9 | TPC-H derived, SF1, boost off, lexdb (`-O`), PG one core and PG four processes, one run each | lexdb / PG one core 1.03 (geometric mean, wall; 0.94 server CPU), 9 of 22 level or ahead; summed 13.44 s against PG's 15.23 s; against PG four processes 1.58; worst q15 2.5, q20 2.2, q11 2.1, q19 2.1 | this page, 1.6 |
| 2026-11-18 | d0f00b92 | analytic queries (lexdb only, pinned, `la/base3`, CPU against the build before), TPC-H and point-select instruction counts | text columns as one buffer plus offsets, and the wire writer on `bytesGrow`: 35 queries geometric mean -6.7% CPU (scans -5 to -23%, `select *` -23%, text joins -19 to -24%, text min/max -31%, text group -12%; `distinct2` +3%); TPC-H +0.66% instructions, +0.75% cycles (results unchanged); point selects +0.1% instructions, -1.4% cycles | this page, 1 |
| 2026-11-18 | eababf57 | OLTP, replicas, commit latency, aggregates (pinned) | point selects 88k / 151k / 145k/s (+10-14%); replicas 401k/s at 32 clients (PG 405k); updates 3,691 / 16,687 / 38,711/s after restoring the 32-client rate (19,300/s at aaadeb1e: owned-string regression); commit p99 1.38-1.40 ms (0.81 before the migration, unresolved) | this page, 1 |
| 2026-11-18 | eababf57 | analytic queries (pinned), bulk loads | 35 queries: lexdb / PG one core 0.63 (CPU), / PG 4 processes 1.19 (wall); COPY level in time, peak RSS +30% since the migration | this page, 1 |
| 2026-11-18 | aaadeb1e | TPC-H derived, SF1, boost off (lexdb only; PG one core from 94536d12's run) | lexdb / PG one core 0.98 (geometric mean, wall; first below 1); summed 12.98 s against PG's 13.96 s; the runtime's short-string compare (rt_str_cmp): -4.0% wall, q19 -11%, q3 -10%, q21 -9%; worst q19 2.3×, q20 2.2×, q11 1.9×, q22 1.8× | this page, 1.6 |
| 2026-11-18 | 89cf0a59 | TPC-H derived, SF1, boost off (lexdb only; PG one core from 94536d12's run) | lexdb / PG one core 1.03 (geometric mean, wall); summed 13.52 s against PG's 13.96 s (lexdb's first sum below PG's); q7 -21%, q21 -15% (hash cut by the next hash), q22 -46% instructions (IN over an expression); worst q19 2.6×, q20 2.3×, q11 2.1×, q22 1.9× | this page, 1.6; lexdb-layers.md 6.2.13 |
| 2026-11-18 | 48c22c45 | TPC-H derived, SF1, boost off (lexdb only; PG one core from 94536d12's run) | lexdb / PG one core 1.05 (geometric mean, wall; was 2.48), 9 of 22 level or ahead; summed 14.08 s against PG's 13.96 s; worst q19 2.5×, q20 2.3×, q11 2.1×, q7 2.0× | this page, 1.6 |
| 2026-11-16 | 94536d12 | TPC-H derived, SF1, boost off | lexdb / PG one core 2.48 (geometric mean, wall; was 3.77), 4 of 22 level or ahead; worst q19 14×, q20 12×, q21 10.5×, q22 8.5×; pinned 0-3, 3.8 GHz | this page, 1.6; lexdb-tpch-perf.md |
| 2026-11-16 | 1744ef99 | TPC-H derived, SF1 | lexdb / PG one core 3.77 (geometric mean, wall), 2 of 22 level or ahead; q4 22×, q21 20×, q1 5.6×; pinned 0-3 | this page, 1.6; lexdb-tpch-perf.md |
| 2026-11-15 | exp/ckpt-incremental | commit latency | the checkpoint's stall gone: commit max 70 → 8-11 ms, p99.9 4.2-4.5 → 3.9-4.4, p99 0.72-0.76 → 0.88-0.91 (master alone, 8 clients, pinned) | this page, 1.2; lexdb.md 9.136 |
| 2026-11-15 | exp/ckpt-incremental | OLTP, replicas, aggregates (**pinned**, first) | 3 replicas: point selects 376,000-377,700/s at 32 clients (PG on 4 cores 386,600; 426,000 at 8); updates 2.26 / 2.63 / 1.54 × PG; lag p99 0.80-1.27 ms under load | this page, 1.1-1.3; lexdb.md 9.136 |
| 2026-11-15 | 518f8d9d | OLTP, replicas (not pinned) | 3 replicas: point selects 333,900 / 367,800/s at 8 / 32 clients (PG at 4 CPUs 342,700 / 270,800); updates 2.3 to 2.6 × PG; replica lag p50 0.28 ms, p99 1.12 | this page, 1.1, 1.2; lexdb.md 9.135 |
| 2026-11-15 | 518f8d9d | replica lag | under the mixed load p50 0.26-0.32 ms, p99 0.54-1.10 (before: p50 4.6, p99 355, max 1.08 s) | lexdb.md 9.135 |
| 2026-11-15 | 478d49f6 | OLTP, aggregates | one process: point selects 83,000 / 138,500 / 127,000/s (12 to 26% below 11-11); updates 3,713 / 17,630 / 41,100/s (2.3 / 2.6 / 1.6 × PG at 4 CPUs); aggregates ahead of PG one core on all five | lexdb.md 9.134 |
| 2026-11-15 | 478d49f6 | analytic queries | lexdb / PG one core 0.78 (CPU), / PG 4 processes 1.30 (wall); on settled data, column leaves throughout | lexdb-engines.md 7 |
| 2026-11-15 | 478d49f6 | bulk loads, commits | 1M narrow 0.55 s (PG 0.58, bcp 1.17); wide 1.48 s (1.79, 3.34); 10M 5.32 s (5.81, 10.86); commits 3,843/s against 1,577 | lexdb.md 9.133 |
| 2026-11-13 | (section 6 of lexdb-engines.md) | analytic queries | lexdb / PG one core 0.72 (CPU), / PG 4 processes 1.28 | lexdb-engines.md 6 |
| 2026-11-13 | (9.118) | bulk loads | 1M narrow 1.23 s (PG 0.55, bcp 1.11); wide 5.15 s (1.96, 3.19); 10M 14.3 s (5.93, 10.3) | lexdb.md 9.118 |
| 2026-11-12 | 25a7b4e2 | analytic queries | 15 queries, lexdb 1.4 to 12 × slower than PG on one core, before the batch work | lexdb-engines.md 1 |
| 2026-11-11 | (9.67) | OLTP, aggregates | point selects 94,700 / 173,900 / 172,300/s (PG with every CPU 80,100 / 489,800 / 710,900); updates level with PG (1,663 / 6,690 / 26,140); aggregates 1.1 to 1.8 × PG one core; not capped | lexdb.md 9.67 |
