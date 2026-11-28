# LexDB performance

Measured on 28 November 2026 on `main` at `0907ea85` (TPC-H SF1 and ClickBench 1M refreshed after adding AVX2 widening loads `loadU8`/`loadU16`/`loadI16`/`loadU32`/`loadI32`, vectorized `unpack`/`intsInto`/`rangeFilter`/`neFilter`/`rangeCount`/`sumIntCols`/`bloomFilter`/`nullsInto`, and 256-row null-bitmap decoding; 35 Analytic Queries, `pgbench` OLTP + 3-replica scaling + commit latency, `sysbench` OLTP, bulk `\copy`, Social Graph 11q, and LDBC LSQB SF0.1/SF1 from `ab29758c`; selective star-schema joins from `4c1fb4cc`; materialized views and skipping-index deltas from `59797d55`). Every number compares LexDB directly against **PostgreSQL 18.6** on the same machine, data, disk, and transport.

For a high-level introduction to LexDB's architecture, features, and performance highlights, see [LEXDB.md](../../../LEXDB.md). For the full historical benchmark log, test rules, and reproduction scripts, see [design/lexdb-benchmarks.md](../../design/lexdb-benchmarks.md). For Lexell compiler, language, HTTP server, and CLI benchmarks, see [PERFORMANCE.md](../../../PERFORMANCE.md).

## Test environment and rules

- **Host:** AMD Ryzen 7 8745HS (8 cores, 16 threads), 46 GB RAM, Linux 7.2 (Arch).
- **Reference:** PostgreSQL 18.6, sysbench 1.0.20, `pgbench` from PostgreSQL 18.6.
- **Pinning & core budget:** Both servers are pinned to the same four physical cores (CPUs 0–3, SMT siblings idle), with clients on CPUs 4–7 and 12–15. PostgreSQL's parallel queries are capped at four processes — matching LexDB's four-core replica shape (one master process plus three read replicas) and `par.map` analytical worker pool.
- **Durability:** Both servers run durable by default (PostgreSQL with `fsync` and `synchronous_commit` on; LexDB with synchronous WAL flushes and group commit).
- **Clock stability:** TPC-H, ClickBench, sysbench, property graphs, and dedicated materialized view suites run at a fixed CPU clock (`cpu-boost off`). LexDB runs with `LXL_HASH_SEED=42`. One benchmark runs at a time.

## Headline summary

| Area | LexDB | PostgreSQL 18 | Result |
|---|---:|---:|---|
| **TPC-H SF1** (22 queries, 4 cores via `par.map`) | **3,203 ms** *(4,672 ms CPU)* | 8,839 ms (4 proc) *(15,034 ms 1c CPU)* | **2.76× faster** than 4-proc PG (`0.50` geomean, 17/22 faster; `q1` **258 ms** — **3.39×**, `q6` **100 ms** — **2.04×**, `q9` **316 ms** — **2.38×**, `q13` **230 ms** — **3.59×**, `q18` **102 ms** — **28.8×**); **3.22× less total CPU** (`0.36` geomean) |
| **ClickBench 1M** (43 queries, 105 cols, 4 cores via `par.map`) | **4,692 ms** *(6,871 ms CPU)* | 11,401 ms (4 proc) *(23,119 ms 1c CPU)* | **2.43× faster** than 4-proc PG (**43/43** faster, `0.51` geomean, no MVs); **3.36× less total CPU** (`0.29` geomean) |
| **ClickBench 1M + 8 MVs** (unmodified queries, 1 core) | **0.47–54.9 ms** *(21 rewritten)* | 22,081 ms (1 core) / 11,401 ms (4 proc) | 21 of 43 queries transparently rewritten to sub-ms–55 ms (measured at `59797d55`: geomean `0.10` vs PG1 / `0.21` vs PG4) |
| **ClickBench 1M + 3 skipping indexes** | 42.6–485.4 ms | — | **1.28–4.07× faster** on selective point & `LIKE '%substring%'` filters; zero OLTP write/read regression |
| **Selective star-schema joins** (1M fact rows, 6 patterns, 1 core) | **0.54–22.5 ms** | 0.21–77.0 ms (1 core) / 0.24–50.7 ms (4 proc) | **1.24–71.7× faster** (`4.87×` geomean) via hash-join runtime filters; **7.68× faster** than 1-core PG / **4.46×** vs 4-proc PG (geomean) |
| **35 Analytic Queries** (1M rows, 4 cores via `par.map`) | **`0.36×` CPU / `0.61×` wall** | 1 core / 4 proc | **2.80× less total CPU** than 1-core PG (**35/35** ahead of PG1 on wall, `0.38` geomean); **1.64× faster** geomean wall than 4-proc PG (**31/35** level or ahead; summed 2,663 vs 3,832 ms) |
| **Materialized view maintenance** (1M rows, 1 row) | **0.43–0.66 ms** (`FAST`) | 60–369 ms (`REFRESH`) | **90–780× faster** incremental updates; sketch MV build **220 vs 379 ms**; hot-key `realtime` **22,102 commits/s** |
| **Durable OLTP updates** (1–32 clients) | up to **68.3k/s** (`pgbench`) / **57.7k/s** (`sysbench`) | 25.9k/s / 23.0k/s | **2.53–2.77×** (`pgbench`); **2.51–3.16×** (`sysbench` non-index); **1.36–2.84×** (`sysbench` indexed) |
| **Point selects (3 read replicas, 32 clients)** | **567–588k/s** (`pgbench`) / **431.6k/s** (`sysbench`) | 404k/s / 334k/s (4 cores) | **1.40–1.46×** (`pgbench`, half the CPU/op); **1.29×** (`sysbench`, 42% less CPU); replica lag **0.14–0.15 ms** p50 / **0.27–0.33 ms** p99 |
| **Bulk `\copy` loads** (5 cases, 1M–10M rows) | 0.24–2.64 s | 0.61–5.93 s | **1.29–2.63× faster** (`0.38–0.77×`) on all 5 workloads (`224–2,103 MB` peak RSS) |
| **Property graphs — LDBC LSQB SF1** (9 queries, 22.2M edges, 1 core) | **8.63 s** (`0.12 s` Q6 / `0.85 s` Q1 / `1.47 s` Q9) | 98.1 s (PG1, 8/9) / 4.56 s (DuckPGQ+FK) / 105.0 s (Kùzu) / 156.0 s (Neo4j CE) | **#2 overall behind in-memory DuckPGQ+FK; #1 disk-backed DB** — geomean **7.41×** vs PG1, **3.66×** vs Kùzu (**12.2×** total), **14.5×** vs Neo4j CE (**18.1×** total); **#1 of all 5** on `Q6` (**4.62×** DuckPGQ+FK) ([full report](property-graphs.md#benchmark-2-ldbc-lsqb-sf01-and-sf1-5-engines)) |
| **Property graphs — social suite** (11 queries, 1.1M edges, 1 core) | **515.1 ms** (`0.46 ms` G10 / `5.95 ms` G11 / `221.8 ms` G9) | 5,661 ms (PG1) / 962 ms (DuckPGQ) / 1,367 ms (Kùzu) | **Fastest total time of all 4** (**1.87×** DuckPGQ, **2.65×** Kùzu, **11.0×** PG1); geomean **7.08×** vs PG1, **2.78×** vs DuckPGQ, **5.32×** vs Kùzu ([full report](property-graphs.md#benchmark-1-social-network-graph-suite-11-queries-11m-edges)) |

PostgreSQL is ahead on single-process multi-thread reads (before adding replicas) and multi-statement read-write blocks.

## TPC-H derived (SF1)

22 queries, SF1, warm, median of 3, at a fixed clock with boost off, both servers pinned to the same four physical cores (CPUs 0–3; LexDB parallelizes large columnar scans, probes, and aggregations across the 4-core `par.map` pool, while PostgreSQL runs with up to 4 parallel processes). Wall time is compared strictly **4 cores vs 4 cores**; total server CPU time (summed across all LexDB threads) is compared against single-core PostgreSQL's CPU time. Every result is checked against PostgreSQL's (22/22 exact match):

| | LexDB (4 cores) | PostgreSQL (4 processes) | Ratio (LexDB / PG) |
|---|---:|---:|---:|
| all 22 queries, summed (wall) | **3,203 ms** | 8,839 ms | **0.36** (**2.76× faster**) |
| geometric mean (wall, 4c vs 4p) | | | **0.50** |
| queries faster than 4-proc PG | **17 of 22** | | |
| total server CPU vs PG 1-core CPU | **4,672 ms** | 15,034 ms *(1c)* | **0.31** (geomean **0.36**) |

| query | LexDB wall (4c) | PG 4-proc wall | LexDB / PG4 | LexDB total CPU | PG 1-core CPU | CPU ratio |
|---|---:|---:|---:|---:|---:|---:|
| q1 | 257.8 ms | 873.5 ms | 0.30 | 770.2 ms | 3,375.3 ms | 0.23 |
| q2 | 41.2 ms | 137.6 ms | 0.30 | 41.1 ms | 166.9 ms | 0.25 |
| q3 | 225.1 ms | 353.6 ms | 0.64 | 258.9 ms | 579.3 ms | 0.45 |
| q4 | 116.8 ms | 102.9 ms | 1.14 | 116.3 ms | 211.6 ms | 0.55 |
| q5 | 128.4 ms | 173.2 ms | 0.74 | 127.9 ms | 341.2 ms | 0.37 |
| q6 | 99.8 ms | 203.4 ms | 0.49 | 157.6 ms | 294.1 ms | 0.54 |
| q7 | 204.8 ms | 287.6 ms | 0.71 | 303.6 ms | 615.2 ms | 0.49 |
| q8 | 144.9 ms | 141.9 ms | 1.02 | 144.2 ms | 253.5 ms | 0.57 |
| q9 | 315.8 ms | 750.9 ms | 0.42 | 453.5 ms | 1,770.1 ms | 0.26 |
| q10 | 219.5 ms | 167.3 ms | 1.31 | 218.5 ms | 417.2 ms | 0.52 |
| q11 | 47.4 ms | 61.5 ms | 0.77 | 47.3 ms | 67.7 ms | 0.70 |
| q12 | 196.5 ms | 253.6 ms | 0.77 | 385.8 ms | 880.7 ms | 0.44 |
| q13 | 230.1 ms | 825.6 ms | 0.28 | 461.3 ms | 843.9 ms | 0.55 |
| q14 | 81.7 ms | 95.1 ms | 0.86 | 90.3 ms | 159.8 ms | 0.57 |
| q15 | 152.1 ms | 333.9 ms | 0.46 | 152.0 ms | 348.1 ms | 0.44 |
| q16 | 186.6 ms | 105.3 ms | 1.77 | 184.3 ms | 273.4 ms | 0.67 |
| q17 | 21.1 ms | 554.7 ms | 0.04 | 21.1 ms | 569.9 ms | 0.04 |
| q18 | 101.8 ms | 2,933.0 ms | 0.03 | 221.3 ms | 2,722.6 ms | 0.08 |
| q19 | 27.7 ms | 37.5 ms | 0.74 | 27.7 ms | 53.6 ms | 0.52 |
| q20 | 28.3 ms | 127.8 ms | 0.22 | 28.3 ms | 149.3 ms | 0.19 |
| q21 | 332.6 ms | 269.6 ms | 1.23 | 418.7 ms | 846.4 ms | 0.49 |
| q22 | 42.5 ms | 49.5 ms | 0.86 | 42.4 ms | 94.1 ms | 0.45 |
| **sum** | **3,202.5 ms** | **8,839.0 ms** | **0.36** | **4,672.3 ms** | **15,033.8 ms** | **0.31** |
| **geomean** | | | **0.50** | | | **0.36** |

## ClickBench (1M rows)

`bench/clickbench/run.sh`: official ClickBench `hits` schema (105 columns, wide web-analytics table) and all 43 queries
(`q0`–`q42`) on the first 1,000,000 rows, warm, median of 3, at a fixed clock (`cpu-boost off`), both servers on CPUs 0–3.
All 43 queries pass (31 exact MD5 matches; 12 top-N/unordered queries with matching row counts).

The baseline columns (`LexDB wall (4c)`, `PG 4-proc wall`) compare strictly **4 cores vs 4 cores** with no materialized views
and no explicit skipping indexes (automatic zero-config `T_CLEAF` zone maps, adaptive two-level hash aggregation with
bump-arena string keys, 32-byte SwissTable / 8-wide SIMD hash tables, direct Top-N group pruning, dictionary-code deduplication,
and AVX2 vectorized columnar/string/regex kernels are always on by default). Total server CPU (summed across all LexDB threads)
is compared against single-core PostgreSQL's CPU time. Fresh load of the 1,000,000-row 105-column `hits` table takes **4.76 s**
(`\copy`) vs PostgreSQL's **6.35 s** (`0.75×`), and `ANALYZE hits` takes **0.36 s** vs PostgreSQL's **1.17 s**.

The final column (`LexDB + MV`, measured at `59797d55` before later engine work cut MV-free total time to **4,713 ms**) shows the 21 unmodified queries transparently rewritten onto eight
general-purpose incremental `ENABLE QUERY REWRITE` rollup views (`mv_hits_adv` 6 rows / 871 ms build,
`mv_hits_counter` 7 rows / 564 ms, `mv_hits_region_user` 80,309 rows / 646 ms, `mv_hits_mobile` 2,522 rows / 292 ms,
`mv_hits_search` 28,357 rows / 441 ms, `mv_hits_url` 275,494 rows / 1,812 ms, `mv_hits_ip` 68,330 rows / 445 ms,
`mv_hits_minute` 4,346 rows / 943 ms; total build 6.01 s), exercising exact `COUNT(DISTINCT)` rollups (`q4`, `q8`–`q11`,
`q13`), wide (`>512`-byte) hashed group keys (`q12`–`q14`, `q20`, `q33`, `q34`), and functionally dependent exact-grain
`GROUP BY` matching (`q34`, `q35`). All 21 rewritten queries were verified against `query_rewrite_enabled = off` (19
bit-for-bit identical; `q10` and `q11` match exact counts with tie-breaking at count 12). After data load, inserting
1 / 100 new `hits` rows while maintaining all 8 views live (`REFRESH FAST ON STATEMENT`) takes **6.51 / 10.34 ms**.

| | LexDB (4 cores) | PostgreSQL (4 processes) | Ratio (LexDB / PG) | LexDB + 8 MVs (`59797d55`, 1c, 21 rewritten) |
|---|---:|---:|---:|---:|
| all 43 queries, summed (wall) | **4,692 ms** | 11,401 ms | **0.41** (**2.43× faster**) | *(see per-query rewritten latencies below)* |
| geometric mean (wall, 4c vs 4p) | | | **0.51** | 0.21 vs PG4 |
| queries faster than 4-proc PG | **43 of 43** | | | 42 of 43 (21 rewritten) |
| total server CPU vs PG 1-core CPU | **6,871 ms** | 23,119 ms *(1c)* | **0.30** (**3.36× less CPU**, geomean **0.29**) | |

| query | LexDB wall (4c) | PG 4-proc wall | LexDB / PG4 | LexDB total CPU | PG 1-core CPU | CPU ratio | LexDB + MV |
|---|---:|---:|---:|---:|---:|---:|---:|
| q0 | 16.3 ms | 36.4 ms | 0.45 | 16.4 ms | 116.2 ms | 0.14 | **0.58 ms** |
| q1 | 73.2 ms | 100.7 ms | 0.73 | 72.9 ms | 359.5 ms | 0.20 | **0.63 ms** |
| q2 | 72.2 ms | 104.4 ms | 0.69 | 72.0 ms | 404.3 ms | 0.18 | **0.69 ms** |
| q3 | 58.7 ms | 76.4 ms | 0.77 | 58.5 ms | 282.8 ms | 0.21 | **0.64 ms** |
| q4 | 69.0 ms | 296.6 ms | 0.23 | 98.0 ms | 331.3 ms | 0.30 | **5.99 ms** |
| q5 | 80.7 ms | 410.2 ms | 0.20 | 125.1 ms | 452.2 ms | 0.28 | — |
| q6 | 66.1 ms | 78.3 ms | 0.84 | 117.2 ms | 283.0 ms | 0.41 | **0.54 ms** |
| q7 | 73.3 ms | 101.7 ms | 0.72 | 73.0 ms | 353.5 ms | 0.21 | **0.47 ms** |
| q8 | 78.6 ms | 465.5 ms | 0.17 | 116.2 ms | 513.2 ms | 0.23 | **5.06 ms** |
| q9 | 117.8 ms | 590.8 ms | 0.20 | 176.8 ms | 640.4 ms | 0.28 | **12.69 ms** |
| q10 | 78.7 ms | 103.5 ms | 0.76 | 98.9 ms | 367.5 ms | 0.27 | **0.83 ms** |
| q11 | 82.1 ms | 108.6 ms | 0.76 | 103.8 ms | 372.2 ms | 0.28 | **0.90 ms** |
| q12 | 76.5 ms | 114.6 ms | 0.67 | 103.2 ms | 393.8 ms | 0.26 | **41.38 ms** |
| q13 | 115.8 ms | 146.7 ms | 0.79 | 151.7 ms | 410.5 ms | 0.37 | **32.80 ms** |
| q14 | 83.5 ms | 351.2 ms | 0.24 | 113.5 ms | 393.3 ms | 0.29 | **48.82 ms** |
| q15 | 85.8 ms | 134.8 ms | 0.64 | 85.6 ms | 356.5 ms | 0.24 | **144.53 ms** |
| q16 | 117.0 ms | 453.9 ms | 0.26 | 217.8 ms | 495.9 ms | 0.44 | — |
| q17 | 142.4 ms | 165.9 ms | 0.86 | 141.8 ms | 475.9 ms | 0.30 | — |
| q18 | 190.0 ms | 639.2 ms | 0.30 | 467.5 ms | 694.3 ms | 0.67 | — |
| q19 | 66.3 ms | 74.8 ms | 0.89 | 66.0 ms | 269.3 ms | 0.25 | — |
| q20 | 96.1 ms | 110.6 ms | 0.87 | 95.8 ms | 398.1 ms | 0.24 | **54.86 ms** |
| q21 | 96.8 ms | 131.0 ms | 0.74 | 96.5 ms | 461.9 ms | 0.21 | — |
| q22 | 92.5 ms | 147.3 ms | 0.63 | 92.2 ms | 515.0 ms | 0.18 | — |
| q23 | 102.2 ms | 107.3 ms | 0.95 | 101.5 ms | 384.8 ms | 0.26 | — |
| q24 | 89.2 ms | 105.6 ms | 0.84 | 88.9 ms | 357.6 ms | 0.25 | — |
| q25 | 84.7 ms | 102.6 ms | 0.83 | 84.4 ms | 357.7 ms | 0.24 | — |
| q26 | 93.3 ms | 103.5 ms | 0.90 | 92.9 ms | 358.9 ms | 0.26 | — |
| q27 | 138.2 ms | 166.3 ms | 0.83 | 208.0 ms | 506.1 ms | 0.41 | **0.50 ms** |
| q28 | 144.9 ms | 1,078.7 ms | 0.13 | 247.8 ms | 4,017.1 ms | 0.06 | — |
| q29 | 61.6 ms | 342.1 ms | 0.18 | 61.4 ms | 876.0 ms | 0.07 | — |
| q30 | 113.0 ms | 356.6 ms | 0.32 | 143.8 ms | 380.4 ms | 0.38 | — |
| q31 | 116.9 ms | 382.0 ms | 0.31 | 160.3 ms | 402.2 ms | 0.40 | — |
| q32 | 193.4 ms | 924.6 ms | 0.21 | 499.6 ms | 928.8 ms | 0.54 | — |
| q33 | 193.1 ms | 467.7 ms | 0.41 | 354.9 ms | 496.4 ms | 0.71 | **38.26 ms** |
| q34 | 185.4 ms | 470.1 ms | 0.39 | 348.5 ms | 499.2 ms | 0.70 | **38.16 ms** |
| q35 | 94.8 ms | 158.6 ms | 0.60 | 202.3 ms | 420.1 ms | 0.48 | **4.00 ms** |
| q36 | 180.1 ms | 255.0 ms | 0.71 | 285.7 ms | 562.6 ms | 0.51 | — |
| q37 | 123.2 ms | 173.0 ms | 0.71 | 177.5 ms | 507.1 ms | 0.35 | — |
| q38 | 110.6 ms | 156.8 ms | 0.71 | 123.1 ms | 423.9 ms | 0.29 | — |
| q39 | 276.9 ms | 529.9 ms | 0.52 | 515.7 ms | 546.8 ms | 0.94 | — |
| q40 | 123.5 ms | 208.1 ms | 0.59 | 166.1 ms | 642.9 ms | 0.26 | — |
| q41 | 132.0 ms | 200.3 ms | 0.66 | 162.7 ms | 608.1 ms | 0.27 | — |
| q42 | 126.9 ms | 168.8 ms | 0.75 | 126.3 ms | 501.1 ms | 0.25 | **2.32 ms** |
| **sum** | **4,713.3 ms** | **11,400.7 ms** | **0.41** | **6,912.0 ms** | **23,118.7 ms** | **0.30** | — |
| **geomean** | | | **0.51** | | | **0.29** | **0.21 vs PG4** |

### Optional data skipping indexes on ClickBench 1M

Adding three optional hierarchical [data skipping indexes](skipping-indexes.md) on `hits` (`USING bloom_filter` on `UserID`, `USING ngrambf(3, 2048, 3)` on `URL` and `Title`) further accelerates selective point and substring-`LIKE` filters with exact output parity and zero OLTP write/read regression (1,000 inserts `303.9` vs `304.6 ms`; 1,000 PK selects `44.4` vs `45.1 ms`):

| Query | Filter pattern | Skipping index used | Baseline | With skipping index | Speedup |
|---|---|---|---:|---:|---:|
| `q19` | `WHERE UserID = 435090932899640449` | `bloom_filter(UserID)` | 173.2 ms | **42.6 ms** | **4.07×** |
| `q21` | `WHERE URL LIKE '%google%'` | `ngrambf(URL)` | 339.9 ms | **167.7 ms** | **2.03×** |
| `q23` | `WHERE Title LIKE '%Google%'` | `ngrambf(Title)` | 331.7 ms | **168.7 ms** | **1.97×** |
| `q22` | `WHERE Title LIKE '%Google%' AND URL NOT LIKE '%.google.%'` | `ngrambf(Title)` | 620.1 ms | **485.4 ms** | **1.28×** |

### Selective star-schema joins (hash-join runtime filters, 1M fact rows)

Hash joins automatically push build-side MinMax bounds, small `IN` sets (`<= 64` keys), and register-blocked L1-hot Bloom filters into the probe table's automatic zone maps, explicit [data skipping indexes](skipping-indexes.md#hash-join-runtime-filters), and columnar leaf kernels (with an adaptive bypass so unfiltered full-table scans pay zero overhead).

Measured on a 1,000,000-row `fact_sales` star schema (`6` selective join patterns, warm median of 5, `cpu-boost off`, pinned CPU 0, exact result parity 6/6 against PostgreSQL 18.6 with matching `BRIN` indexes on clustered columns):

| Query | Join pattern & runtime filter path | LexDB (before) | LexDB (with RT filters) | Speedup | PG 18 (1 core) | PG 18 (4 proc) | LexDB / PG1 | LexDB / PG4 |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| `J1_auto_zonemap` | 1% clustered `order_id` (zero-config zone maps) | 9.76 ms | **3.14 ms** | **3.11×** | 73.43 ms | 36.09 ms | **0.043×** | **0.087×** |
| `J2_empty_build` | Empty build side short-circuit (0 matching rows) | 8.67 ms | **0.63 ms** | **13.74×** | 0.21 ms | 0.24 ms | 3.03× | 2.65× |
| `J3_multiway_bloom` | Multi-way star join (2nd join L1-hot `IntBloom`) | 27.94 ms | **22.54 ms** | **1.24×** | 77.02 ms | 50.66 ms | **0.293×** | **0.445×** |
| `J4_bloom_skip_idx` | 50 scattered `user_id`s via `bloom_filter` index | 12.32 ms | **9.59 ms** | **1.28×** | 49.38 ms | 23.46 ms | **0.194×** | **0.409×** |
| `J5_set_skip_intbloom` | 200 `cat_id`s (`> 64`) `IntBloom` via `set` index | 9.73 ms | **3.57 ms** | **2.73×** | 55.72 ms | 25.78 ms | **0.064×** | **0.138×** |
| `J6_text_minmax_skip` | 0.5% `text` join (`JK_TEXT`) via `minmax` index | 39.02 ms | **0.54 ms** | **71.73×** | 52.53 ms | 24.93 ms | **0.010×** | **0.022×** |
| **geomean** | | | | **4.87×** | | | **0.130× (7.68×)** | **0.224× (4.46×)** |

## Analytic queries (35 queries, 1M rows)

35 queries over 1M-row tables (scans, joins, groups, windows; median of 5, both servers pinned to CPUs 0–3).
The baseline columns (`LexDB`, `PG 1-core`, `PG 4-proc`) run strictly apples-to-apples with no materialized views:
LexDB's total CPU is **0.36** of PostgreSQL's on one core (geometric mean, **2.80× less CPU**; wall **0.38**), and its wall time
is **0.61** of PostgreSQL's on four processes (**1.64× faster** geomean, summed **2,663 ms** vs **3,832 ms**); **35 of 35** are ahead of PostgreSQL on one core
and **31 of 35** are level or ahead of PostgreSQL on four processes, including `filt_like` at **13 ms** (`0.41×` PG4),
`grp_int` at **13 ms** (`0.37×` PG4), `grp_text` at **18 ms** (`0.42×` PG4), `minmax_text` at **24 ms** (`0.56×` PG4),
`join_hash_agg` at **15 ms** (`0.43×` PG4), `join_text_agg` at **21 ms** (`0.66×` PG4), `join_text_rows` at **35 ms** (`0.40×` PG4),
and `join_text_group` at **24 ms** (`0.44×` PG4).

The rightmost column (`LexDB + MV`, measured at `59797d55` before the SIMD and parallel updates) runs the **exact same 35 unmodified queries** after creating four
general-purpose incremental `ENABLE QUERY REWRITE` rollup views (`mv_w_cube` 1,940 rows / 189 ms build,
`mv_w_join_d` 10 rows / 170 ms, `mv_w_join_cr` 17 rows / 141 ms, `mv_w_join_t` 1 row / 218 ms). Nine aggregate
and join-aggregate queries transparently rewrite onto those views with exact result parity, dropping to 3–4 ms
(0–1 ms server CPU; the remaining ~3 ms is `psql` process startup). After data load, inserting
1 / 100 / 1,000 new rows into `w` while keeping all four views live (`REFRESH FAST ON STATEMENT`) takes
**4.40 / 7.09 / 25.90 ms** (including `psql` startup and durable commit), whereas PostgreSQL 18 requires
**758.4 ms** (1-core) or **263.7 ms** (4-proc) to `REFRESH MATERIALIZED VIEW` all four views after any write.

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 | LexDB + MV (`59797d55`) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `scan2` | 109 ms | 141 ms | 0.77 | 51 ms | 80 ms | 0.64 | 141 ms | 0.77 | 115 ms |
| `scan3` | 161 ms | 213 ms | 0.76 | 75 ms | 120 ms | 0.62 | 215 ms | 0.75 | 167 ms |
| `scan9` | 511 ms | 532 ms | 0.96 | 252 ms | 250 ms | 1.01 | 532 ms | 0.96 | 532 ms |
| `filt1pct` | 17 ms | 41 ms | 0.41 | 12 ms | 40 ms | 0.30 | 22 ms | 0.77 | 21 ms |
| `filt10pct` | 32 ms | 59 ms | 0.54 | 20 ms | 50 ms | 0.40 | 59 ms | 0.54 | 37 ms |
| `filt_like` | 13 ms | 81 ms | 0.16 | 8 ms | 80 ms | 0.10 | 32 ms | 0.41 | 57 ms |
| `filt_agg` | 13 ms | 45 ms | 0.29 | 13 ms | 40 ms | 0.33 | 22 ms | 0.59 | 23 ms |
| `expr_int` | 153 ms | 217 ms | 0.71 | 67 ms | 140 ms | 0.48 | 215 ms | 0.71 | 160 ms |
| `expr_mix` | 368 ms | 422 ms | 0.87 | 250 ms | 300 ms | 0.83 | 418 ms | 0.88 | 381 ms |
| `expr_agg` | 15 ms | 58 ms | 0.26 | 26 ms | 60 ms | 0.43 | 25 ms | 0.60 | **3 ms** |
| `sort_all` | 119 ms | 447 ms | 0.27 | 62 ms | 390 ms | 0.16 | 443 ms | 0.27 | 120 ms |
| `sort_lim` | 7 ms | 91 ms | 0.08 | 3 ms | 90 ms | 0.03 | 33 ms | 0.21 | 6 ms |
| `count` | 4 ms | 36 ms | 0.11 | 1 ms | 30 ms | 0.03 | 18 ms | 0.22 | **3 ms** |
| `grp_int` | 13 ms | 95 ms | 0.14 | 22 ms | 100 ms | 0.22 | 35 ms | 0.37 | **3 ms** |
| `grp_text` | 18 ms | 127 ms | 0.14 | 35 ms | 130 ms | 0.27 | 43 ms | 0.42 | **4 ms** |
| `minmax_text` | 24 ms | 132 ms | 0.18 | 52 ms | 130 ms | 0.40 | 43 ms | 0.56 | **3 ms** |
| `distinct` | 40 ms | 95 ms | 0.42 | 36 ms | 100 ms | 0.36 | 34 ms | 1.18 | 77 ms |
| `distinct2` | 79 ms | 110 ms | 0.72 | 75 ms | 110 ms | 0.68 | 40 ms | 1.98 | 173 ms |
| `idx_range1k` | 5 ms | 10 ms | 0.50 | 1 ms | 10 ms | 0.10 | 10 ms | 0.50 | 5 ms |
| `idx_range100k` | 40 ms | 46 ms | 0.87 | 26 ms | 30 ms | 0.87 | 46 ms | 0.87 | 50 ms |
| `idx_range_agg` | 21 ms | 30 ms | 0.70 | 17 ms | 30 ms | 0.57 | 24 ms | 0.88 | 32 ms |
| `pk_range100k` | 21 ms | 32 ms | 0.66 | 9 ms | 20 ms | 0.45 | 32 ms | 0.66 | 22 ms |
| `pk_point20k` | 391 ms | 629 ms | 0.62 | 356 ms | 430 ms | 0.83 | 642 ms | 0.61 | 680 ms |
| `join_hash_agg` | 15 ms | 95 ms | 0.16 | 22 ms | 100 ms | 0.22 | 35 ms | 0.43 | **3 ms** |
| `join_hash_rows` | 25 ms | 63 ms | 0.40 | 25 ms | 60 ms | 0.42 | 63 ms | 0.40 | 36 ms |
| `join_lookup_agg` | 74 ms | 80 ms | 0.93 | 70 ms | 80 ms | 0.88 | 33 ms | 2.24 | **3 ms** |
| `sub_in` | 13 ms | 50 ms | 0.26 | 15 ms | 50 ms | 0.30 | 24 ms | 0.54 | 26 ms |
| `sub_exists` | 13 ms | 50 ms | 0.26 | 15 ms | 50 ms | 0.30 | 25 ms | 0.52 | 26 ms |
| `sub_corr_sel` | 88 ms | 150 ms | 0.59 | 75 ms | 150 ms | 0.50 | 150 ms | 0.59 | 122 ms |
| `window` | 101 ms | 144 ms | 0.70 | 85 ms | 130 ms | 0.65 | 91 ms | 1.11 | 120 ms |
| `join_hash_sort` | 49 ms | 111 ms | 0.44 | 46 ms | 100 ms | 0.46 | 55 ms | 0.89 | 61 ms |
| `join_text_agg` | 21 ms | 85 ms | 0.25 | 47 ms | 80 ms | 0.59 | 32 ms | 0.66 | **3 ms** |
| `join_text_rows` | 35 ms | 86 ms | 0.41 | 37 ms | 80 ms | 0.46 | 87 ms | 0.40 | 73 ms |
| `join_text_group` | 24 ms | 169 ms | 0.14 | 59 ms | 170 ms | 0.35 | 54 ms | 0.44 | **3 ms** |
| `join_left_rows` | 31 ms | 56 ms | 0.55 | 17 ms | 40 ms | 0.42 | 59 ms | 0.53 | 33 ms |
| **geomean** | | | **0.38** | | | **0.36** | | **0.61** | **0.31 / 0.49** |

## Materialized views (1M rows)

Direct comparison against PostgreSQL 18 on a 1,000,000-row table (`ev`: 100 groups, 1,000 subgroups,
50,000 distinct user IDs), pinned to CPUs 0–3, `cpu-boost off`, server-side `psql \timing` (median of 5 for LexDB,
median of 3 for PG). PostgreSQL has only full `REFRESH MATERIALIZED VIEW [CONCURRENTLY]`, whereas LexDB maintains
[materialized views](materialized-views.md) incrementally in O(Δ) (including composable HyperLogLog++ / t-digest sketches,
cascading multi-level DAGs, and sharded append-only `ON QUERY COMPUTATION` delta trees):

| workload (1M base rows) | Initial build (LexDB / PG) | LexDB `FAST` (1 / 100 / 1,000 rows) | PG 18 `REFRESH` (1-core) | PG 18 `REFRESH` (4-proc) | LexDB query rewrite (base → MV) |
|---|---:|---:|---:|---:|---:|
| Grouped rollup (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`) | **65.4** / 66.8 ms | **0.66 / 1.43 / 3.46 ms** | 144.4 ms | 59.7 ms (`CONCURRENTLY`: 62.0 ms) | 23.68 → **0.18 ms** (132×) |
| Sketch rollup (`APPROX_COUNT_DISTINCT` + `APPROX_PERCENTILE` vs PG `COUNT(DISTINCT)` + `PERCENTILE_CONT`) | **220.0** / 378.8 ms | **0.47 / 3.94 / 6.29 ms** | 368.6 ms | 363.2 ms | 234.4 → **0.56 ms** (419×) |
| 3-level cascading DAG (`ev → mv_l1 → mv_l2 → mv_l3`) | **39.9 ms** | **0.43 / 1.78 / 8.87 ms** | 136.2 ms | 136.1 ms | `mv_l3` read: **0.07 ms** |

Hot-key concurrent writes (16 clients × 100 durable autocommit `INSERT`s across 10 shared groups, `LEXDB_MV_FOLD=off`):

| mode | commits/s | errors | live read / fold |
|---|---:|---:|---|
| Plain table (no MV) | 25,850/s | 0 | — |
| `FAST ON STATEMENT` (synchronous in-place) | 20,063/s | 0 | base tree always folded |
| `ON QUERY COMPUTATION` (`refresh = 'realtime'` sharded delta tree) | 22,102/s | 0 | 1.40 ms merge-on-read; 7.25 ms `REFRESH FAST` fold (1,600 deltas) |

## OLTP

### `pgbench` (1M rows)

Prepared statements over Unix sockets, 1M rows, median of three 10 s rounds (two runs for replicas and commit latency):

| | LexDB | PostgreSQL | LexDB / PostgreSQL |
|---|---:|---:|---:|
| point selects, 1 client | 105,578/s | 80,880/s | 1.31 |
| point selects, 8 / 32 clients, one process | 214,006 / 208,393/s | 443,445 / 403,874/s | 0.48 / 0.52 |
| point selects, 32 clients, three read replicas | 567,116–587,781/s | 403,874/s | 1.40–1.46 |
| updates, 1 / 8 / 32 clients (a durable commit each) | 4,124 / 18,528 / 68,261/s | 1,629 / 6,697 / 25,869/s | 2.53 / 2.77 / 2.64 |

On single-process point selects, LexDB uses half PostgreSQL's server CPU per operation (4.66–4.79 µs vs 8.97–9.88 µs at 8–32 clients) and scales reads across cores with [read replica](replicas.md) processes, which follow the
master with a lag of **0.14–0.15 ms** at the median and **0.27–0.33 ms** at p99 under a mixed load
(**443,400–478,600/s** replica selects alongside **15,060–16,460/s** master updates). Commit latency
with 8 clients is **0.41 ms** at the median and **0.84–0.87 ms** at p99 (p99.9 **3.70–3.81 ms**, max **8.03–9.09 ms**).
On the five 1M-row aggregates in `vspg.sh` (median of 3 rounds), LexDB runs in **0.3 / 7.6 / 10.4 / 8.5 / 10.1 ms** against PostgreSQL 4-proc **15.6 / 27.2 / 23.2 / 37.1 / 30.4 ms** (**2.2–52× faster** on all five).

### `sysbench` OLTP (1M rows)

`bench/sysbench/run.sh`: sysbench 1.0.20, 4 tables × 250,000 rows (`sbtest1..4` with secondary index `k_i`),
prepared statements (`--db-ps-mode=auto`), Unix sockets, 10 s per run at a fixed clock (`cpu-boost off`),
servers on CPUs 0–3 and client on CPUs 4–7 and 12–15. Both servers run durable (`fsync` and `synchronous_commit` on).
LexDB defaults to `SERIALIZABLE` isolation and also supports opt-in `READ COMMITTED`; PostgreSQL runs at its default `READ COMMITTED`.
Both isolation levels are shown for `oltp_read_write`.

LexDB (1 process) vs PostgreSQL 18 (4 cores):

| workload | threads | LexDB TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio | LexDB err | PG err |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 75,058 | 65,124 | 1.15 | 0.01 | 0.02 | 13.2 | 10.1 | 1.31 | 0 | 0 |
| `oltp_point_select` | 8 | 143,304 | 369,540 | 0.39 | 0.06 | 0.03 | 7.0 | 10.7 | 0.65 | 0 | 0 |
| `oltp_point_select` | 32 | 141,711 | 334,053 | 0.42 | 0.24 | 0.15 | 7.0 | 11.9 | 0.59 | 0 | 0 |
| `oltp_read_only` | 1 | 2,808 | 2,418 | 1.16 | 0.37 | 0.43 | 353.9 | 326.2 | 1.08 | 0 | 0 |
| `oltp_read_only` | 8 | 3,867 | 11,547 | 0.33 | 2.39 | 0.80 | 257.4 | 341.0 | 0.75 | 0 | 0 |
| `oltp_read_only` | 32 | 3,611 | 10,241 | 0.35 | 9.73 | 4.18 | 275.9 | 389.9 | 0.71 | 0 | 0 |
| `oltp_read_write` (`SERIALIZABLE`) | 1 | 1,104 | 829 | 1.33 | 1.10 | 1.32 | 699.5 | 565.8 | 1.24 | 0 | 0 |
| `oltp_read_write` (`SERIALIZABLE`) | 8 | 1,563 | 4,082 | 0.38 | 8.90 | 2.22 | 636.3 | 607.1 | 1.05 | 3,550 | 14 |
| `oltp_read_write` (`SERIALIZABLE`) | 32 | 992 | 5,553 | 0.18 | 77.19 | 8.28 | 1,005.7 | 690.3 | 1.46 | 10,974 | 66 |
| `oltp_read_write` (`READ COMMITTED`) | 1 | 1,197 | 829 | 1.44 | 0.92 | 1.32 | 639.3 | 565.8 | 1.13 | 0 | 0 |
| `oltp_read_write` (`READ COMMITTED`) | 8 | 1,885 | 4,082 | 0.46 | 4.74 | 2.22 | 528.7 | 607.1 | 0.87 | 0 | 14 |
| `oltp_read_write` (`READ COMMITTED`) | 32 | 1,982 | 5,553 | 0.36 | 18.28 | 8.28 | 505.7 | 690.3 | 0.73 | 0 | 66 |
| `oltp_write_only` | 1 | 2,642 | 1,326 | 1.99 | 0.46 | 0.80 | 196.7 | 200.4 | 0.98 | 0 | 0 |
| `oltp_write_only` | 8 | 8,962 | 5,964 | 1.50 | 1.37 | 1.39 | 112.7 | 152.4 | 0.74 | 0 | 28 |
| `oltp_write_only` | 32 | 6,412 | 18,505 | 0.35 | 10.65 | 2.35 | 156.6 | 137.4 | 1.14 | 0 | 318 |
| `oltp_update_index` | 1 | 3,456 | 1,501 | 2.30 | 0.42 | 0.70 | 111.8 | 138.5 | 0.81 | 0 | 0 |
| `oltp_update_index` | 8 | 16,716 | 5,882 | 2.84 | 0.63 | 1.96 | 45.8 | 82.8 | 0.55 | 0 | 0 |
| `oltp_update_index` | 32 | 28,561 | 20,992 | 1.36 | 2.11 | 2.22 | 35.2 | 55.0 | 0.64 | 0 | 0 |
| `oltp_update_non_index` | 1 | 3,994 | 1,381 | 2.89 | 0.29 | 0.80 | 62.3 | 139.2 | 0.45 | 0 | 0 |
| `oltp_update_non_index` | 8 | 18,629 | 5,898 | 3.16 | 0.45 | 1.96 | 27.1 | 70.5 | 0.38 | 0 | 0 |
| `oltp_update_non_index` | 32 | 57,721 | 23,015 | 2.51 | 0.70 | 1.55 | 17.4 | 48.6 | 0.36 | 0 | 0 |

LexDB (3 read replicas, 4 processes) vs PostgreSQL 18 (4 cores) — read workloads:

| workload | threads | LexDB 3-rep TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 77,779 | 65,124 | 1.19 | 0.01 | 0.02 | 12.8 | 10.1 | 1.27 |
| `oltp_point_select` | 8 | 346,445 | 369,540 | 0.94 | 0.04 | 0.03 | 8.6 | 10.7 | 0.80 |
| `oltp_point_select` | 32 | 431,625 | 334,053 | 1.29 | 0.10 | 0.15 | 6.9 | 11.9 | 0.58 |
| `oltp_read_only` | 1 | 2,768 | 2,418 | 1.14 | 0.41 | 0.43 | 358.3 | 326.2 | 1.10 |
| `oltp_read_only` | 8 | 10,915 | 11,547 | 0.95 | 1.32 | 0.80 | 273.7 | 341.0 | 0.80 |
| `oltp_read_only` | 32 | 11,105 | 10,241 | 1.08 | 4.57 | 4.18 | 269.1 | 389.9 | 0.69 |

## Bulk loads

`\copy`, median of 3, not pinned:

| workload | LexDB | PostgreSQL 18 | LexDB / PG | LexDB peak RSS |
|---|---:|---:|---:|---:|
| narrow, 1M rows | 0.24 s | 0.61 s | 0.39 | 224 MB |
| wide, 1M rows | 1.03 s | 2.00 s | 0.52 | 618 MB |
| wide + 2 secondary indexes, 1M rows | 1.86 s | 4.90 s | 0.38 | 1,029 MB |
| wide, no primary key, 1M rows | 1.09 s | 1.41 s | 0.77 | 658 MB |
| narrow, 10M rows | 2.64 s | 5.93 s | 0.45 | 2,103 MB |

## Property graphs (SQL/PGQ)

11 social-graph queries (`G1`–`G11`: 1–4 hop traversals, full-graph aggregations, filtered multi-hop joins, triangle counting, point-to-point and single-source shortest paths) over 100k vertices and 1.1M edges, warm median of 5, single core / single thread (`cpu-boost off`), exact result parity across all four engines (11/11). See [property-graphs.md](property-graphs.md) for the full query-by-query table, cold vs warm shortest-path latencies, and execution engine architecture.

| Metric (11 queries, 1 core / 1 thread) | LexDB | PostgreSQL 18 | DuckDB 2.0 + DuckPGQ | Kùzu 0.11.3 |
|---|---:|---:|---:|---:|
| Sum of all 11 queries | **515.1 ms** | 5,660.5 ms | 962.2 ms | 1,367.4 ms |
| Geometric mean (LexDB / peer) | — | **0.14× (7.08× faster)** | **0.36× (2.78× faster)** | **0.19× (5.32× faster)** |
| 5-hop shortest path (`G10`) | **0.46 ms** (`0.71 ms` cold) | 1,080.53 ms | 61.89 ms | 40.59 ms |
| Single-source shortest paths (`G11`, 2k targets) | **5.95 ms** (`24.86 ms` cold) | 1,263.90 ms | 64.31 ms | 48.26 ms |
| Full-graph 1M-edge triangles (`G9`) | **221.77 ms** | 1,813.83 ms | 518.85 ms | 521.31 ms |

## Not measured in this run

- **SQL Server** against LexDB: its container was not running for this run.
- **Oracle** comparison: dropped for now, to be added back later.
