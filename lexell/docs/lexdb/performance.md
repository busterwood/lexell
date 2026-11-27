# LexDB performance

Measured on 24–27 November 2026 on `main` (TPC-H SF1 and ClickBench 1M refreshed at `a751fe1d` after OLAP v3: whole-leaf `memmem` `LIKE` pre-scan & zero-alloc batch `reuse`, derived-table flattening under aggregation, PK-lookup hash build groups with parallel `JK_INT2` Bloom runtime filter, `TopAgg` for `SUM`, parallel `COUNT(DISTINCT text)`, `CondText` `elideComp`, `COLL_PAD` / `#bptrim` vectorization, batched same-leaf range scans, and pre-kernel dense pushdown; `sysbench` OLTP and bulk `\copy` loads from `513bc194`; Social Graph 11q and LDBC LSQB SF0.1/SF1 from `48b393c0`; 35 Analytic and star-schema joins from `4c1fb4cc`; `pgbench` and materialized views from `59797d55`). Every number compares LexDB directly against **PostgreSQL 18.6** on the same machine, data, disk, and transport.

For a high-level introduction to LexDB's architecture, features, and performance highlights, see [LEXDB.md](../../../LEXDB.md). For the full historical benchmark log, test rules, and reproduction scripts, see [design/lexdb-benchmarks.md](../../design/lexdb-benchmarks.md). For Lexell compiler, language, HTTP server, and CLI benchmarks, see [PERFORMANCE.md](../../../PERFORMANCE.md).

## Test environment and rules

- **Host:** AMD Ryzen 7 8745HS (8 cores, 16 threads), 46 GB RAM, Linux 7.2 (Arch).
- **Reference:** PostgreSQL 18.6, sysbench 1.0.20, `pgbench` from PostgreSQL 18.6.
- **Pinning & core budget:** Both servers are pinned to the same four physical cores (CPUs 0–3, SMT siblings idle), with clients on CPUs 4–7 and 12–15. PostgreSQL's parallel queries are capped at four processes — matching LexDB's four-core replica shape (one master process plus three read replicas).
- **Durability:** Both servers run durable by default (PostgreSQL with `fsync` and `synchronous_commit` on; LexDB with synchronous WAL flushes and group commit).
- **Clock stability:** TPC-H, ClickBench, sysbench, and dedicated materialized view suites run at a fixed CPU clock (`cpu-boost off`). LexDB runs with `LXL_HASH_SEED=42`. One benchmark runs at a time.

## Headline summary

| Area | LexDB | PostgreSQL 18 | Result |
|---|---:|---:|---|
| **TPC-H SF1** (22 queries, 4 cores via `par.map`) | **3,254 ms** *(4,781 ms CPU)* | 8,839 ms (4 proc) *(15,034 ms 1c CPU)* | **2.72× faster** than 4-proc PG (`0.51` geomean, 17/22 faster; `q1` **261 ms** — **3.35×**, `q9` **323 ms** — **2.32×**, `q18` **103 ms** — **28.5×**); **3.14× less total CPU** (`0.37` geomean) |
| **ClickBench 1M** (43 queries, 105 cols, 4 cores via `par.map`) | **4,776 ms** *(7,118 ms CPU)* | 11,401 ms (4 proc) *(23,119 ms 1c CPU)* | **2.39× faster** than 4-proc PG (**43/43** faster, `0.51` geomean, no MVs); **3.25× less total CPU** (`0.29` geomean) |
| **ClickBench 1M + 8 MVs** (unmodified queries, 1 core) | **0.47–54.9 ms** *(21 rewritten)* | 22,081 ms (1 core) / 11,401 ms (4 proc) | 21 of 43 queries transparently rewritten to sub-ms–55 ms (measured at `59797d55`: geomean `0.10` vs PG1 / `0.21` vs PG4) |
| **ClickBench 1M + 3 skipping indexes** | 42.6–485.4 ms | — | **1.28–4.07× faster** on selective point & `LIKE '%substring%'` filters; zero OLTP write/read regression |
| **Selective star-schema joins** (1M fact rows, 6 patterns, 1 core) | **0.54–22.5 ms** | 0.21–77.0 ms (1 core) / 0.24–50.7 ms (4 proc) | **1.24–71.7× faster** (`4.87×` geomean) via hash-join runtime filters; **7.68× faster** than 1-core PG / **4.46×** vs 4-proc PG (geomean) |
| **35 Analytic Queries** (1M rows, 1 core) | **`0.39×` CPU / `0.78×` wall** | 1 core / 4 proc | **2.59× less CPU** than 1 core (**35/35** ahead on CPU and wall); **1.28× faster** than 4 proc on wall (`0.31 / 0.49` geomean with 4 MVs) |
| **Materialized view maintenance** (1M rows, 1 row) | **0.43–0.66 ms** (`FAST`) | 60–369 ms (`REFRESH`) | **90–780× faster** incremental updates; sketch MV build **220 vs 379 ms**; hot-key `realtime` **22,102 commits/s** |
| **Durable OLTP updates** (1–32 clients) | up to **63.3k/s** (`pgbench`) / **58.9k/s** (`sysbench`) | 25.7k/s / 23.0k/s | **2.41–2.67×** (`pgbench`); **2.56–3.14×** (`sysbench` non-index); **1.34–2.90×** (`sysbench` indexed) |
| **Point selects (3 read replicas, 32 clients)** | **470–490k/s** (`pgbench`) / **430.9k/s** (`sysbench`) | 397k/s / 334k/s (4 cores) | **1.18–1.23×** (`pgbench`); **1.29×** (`sysbench`, 42% less CPU); replica lag **0.22 ms** p50 / **0.44 ms** p99 |
| **Bulk `\copy` loads** (5 cases, 1M–10M rows) | 0.26–2.61 s | 0.61–5.93 s | **1.25–2.6× faster** (`0.39–0.80×`) on all 5 workloads (`224–2,103 MB` peak RSS) |
| **Property graphs — LDBC LSQB SF1** (9 queries, 22.2M edges, 1 core) | **7.30 s** (`0.10 s` Q6 / `0.87 s` Q1 / `1.40 s` Q9) | 98.1 s (PG1, 8/9) / 4.56 s (DuckPGQ+FK) / 105.0 s (Kùzu) / 156.0 s (Neo4j CE) | **#2 overall behind in-memory DuckPGQ+FK; #1 disk-backed DB** — geomean **9.03×** vs PG1, **4.40×** vs Kùzu (**14.4×** total), **17.4×** vs Neo4j CE (**21.4×** total); **#1 of all 5** on both `Q6` (**5.81×** DuckPGQ) and `Q9` (`1.40 s` vs `1.41 s`) ([full report](property-graphs.md#benchmark-2-ldbc-lsqb-sf01-and-sf1-5-engines)) |
| **Property graphs — social suite** (11 queries, 1.1M edges, 1 core) | **500.9 ms** (`0.45 ms` G10 / `5.83 ms` G11 / `226.6 ms` G9) | 5,661 ms (PG1) / 962 ms (DuckPGQ) / 1,367 ms (Kùzu) | **Fastest total time of all 4** (**1.92×** DuckPGQ, **2.73×** Kùzu, **11.3×** PG1); geomean **7.82×** vs PG1, **3.06×** vs DuckPGQ, **5.86×** vs Kùzu ([full report](property-graphs.md#benchmark-1-social-network-graph-suite-11-queries-11m-edges)) |

PostgreSQL is ahead on single-process multi-thread reads (before adding replicas) and multi-statement read-write blocks.

## TPC-H derived (SF1)

22 queries, SF1, warm, median of 3, at a fixed clock with boost off, both servers pinned to the same four physical cores (CPUs 0–3; LexDB parallelizes large columnar scans, probes, and aggregations across the 4-core `par.map` pool, while PostgreSQL runs with up to 4 parallel processes). Wall time is compared strictly **4 cores vs 4 cores**; total server CPU time (summed across all LexDB threads) is compared against single-core PostgreSQL's CPU time. Every result is checked against PostgreSQL's (22/22 exact match):

| | LexDB (4 cores) | PostgreSQL (4 processes) | Ratio (LexDB / PG) |
|---|---:|---:|---:|
| all 22 queries, summed (wall) | **3,254 ms** | 8,839 ms | **0.37** (**2.72× faster**) |
| geometric mean (wall, 4c vs 4p) | | | **0.51** |
| queries faster than 4-proc PG | **17 of 22** | | |
| total server CPU vs PG 1-core CPU | **4,781 ms** | 15,034 ms *(1c)* | **0.32** (geomean **0.37**) |

| query | LexDB wall (4c) | PG 4-proc wall | LexDB / PG4 | LexDB total CPU | PG 1-core CPU | CPU ratio |
|---|---:|---:|---:|---:|---:|---:|
| q1 | 260.7 ms | 873.5 ms | 0.30 | 774.4 ms | 3,375.3 ms | 0.23 |
| q2 | 42.2 ms | 137.6 ms | 0.31 | 42.0 ms | 166.9 ms | 0.25 |
| q3 | 222.6 ms | 353.6 ms | 0.63 | 255.6 ms | 579.3 ms | 0.44 |
| q4 | 116.6 ms | 102.9 ms | 1.13 | 116.1 ms | 211.6 ms | 0.55 |
| q5 | 130.2 ms | 173.2 ms | 0.75 | 129.6 ms | 341.2 ms | 0.38 |
| q6 | 102.5 ms | 203.4 ms | 0.50 | 162.7 ms | 294.1 ms | 0.55 |
| q7 | 208.0 ms | 287.6 ms | 0.72 | 306.1 ms | 615.2 ms | 0.50 |
| q8 | 144.8 ms | 141.9 ms | 1.02 | 144.1 ms | 253.5 ms | 0.57 |
| q9 | 323.3 ms | 750.9 ms | 0.43 | 457.6 ms | 1,770.1 ms | 0.26 |
| q10 | 222.7 ms | 167.3 ms | 1.33 | 220.9 ms | 417.2 ms | 0.53 |
| q11 | 48.8 ms | 61.5 ms | 0.79 | 48.5 ms | 67.7 ms | 0.72 |
| q12 | 194.3 ms | 253.6 ms | 0.77 | 390.1 ms | 880.7 ms | 0.44 |
| q13 | 255.7 ms | 825.6 ms | 0.31 | 538.1 ms | 843.9 ms | 0.64 |
| q14 | 84.0 ms | 95.1 ms | 0.88 | 92.3 ms | 159.8 ms | 0.58 |
| q15 | 153.8 ms | 333.9 ms | 0.46 | 153.4 ms | 348.1 ms | 0.44 |
| q16 | 184.3 ms | 105.3 ms | 1.75 | 181.8 ms | 273.4 ms | 0.66 |
| q17 | 20.9 ms | 554.7 ms | 0.04 | 21.0 ms | 569.9 ms | 0.04 |
| q18 | 103.0 ms | 2,933.0 ms | 0.04 | 226.6 ms | 2,722.6 ms | 0.08 |
| q19 | 27.9 ms | 37.5 ms | 0.74 | 28.1 ms | 53.6 ms | 0.52 |
| q20 | 27.4 ms | 127.8 ms | 0.21 | 27.4 ms | 149.3 ms | 0.18 |
| q21 | 337.1 ms | 269.6 ms | 1.25 | 422.2 ms | 846.4 ms | 0.50 |
| q22 | 42.8 ms | 49.5 ms | 0.86 | 42.8 ms | 94.1 ms | 0.45 |
| **sum** | **3,253.6 ms** | **8,839.0 ms** | **0.37** | **4,781.4 ms** | **15,033.9 ms** | **0.32** |
| **geomean** | | | **0.51** | | | **0.37** |

## ClickBench (1M rows)

`bench/clickbench/run.sh`: official ClickBench `hits` schema (105 columns, wide web-analytics table) and all 43 queries
(`q0`–`q42`) on the first 1,000,000 rows, warm, median of 3, at a fixed clock (`cpu-boost off`), both servers on CPUs 0–3.
All 43 queries pass (31 exact MD5 matches; 12 top-N/unordered queries with matching row counts).

The baseline columns (`LexDB wall (4c)`, `PG 4-proc wall`) compare strictly **4 cores vs 4 cores** with no materialized views
and no explicit skipping indexes (automatic zero-config `T_CLEAF` zone maps, adaptive two-level hash aggregation with
bump-arena string keys, direct Top-N group pruning, dictionary-code deduplication, and vectorized string/regex kernels
are always on by default). Total server CPU (summed across all LexDB threads) is compared against single-core PostgreSQL's CPU time. Fresh load of the 1,000,000-row 105-column `hits` table takes **4.76 s** (`\copy`) vs
PostgreSQL's **6.35 s** (`0.75×`), and `ANALYZE hits` takes **0.36 s** vs PostgreSQL's **1.17 s**.

The final column (`LexDB + MV`, measured at `59797d55` before later engine work cut MV-free total time to **4,776 ms**) shows the 21 unmodified queries transparently rewritten onto eight
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
| all 43 queries, summed (wall) | **4,776 ms** | 11,401 ms | **0.42** (**2.39× faster**) | *(see per-query rewritten latencies below)* |
| geometric mean (wall, 4c vs 4p) | | | **0.51** | 0.21 vs PG4 |
| queries faster than 4-proc PG | **43 of 43** | | | 42 of 43 (21 rewritten) |
| total server CPU vs PG 1-core CPU | **7,118 ms** | 23,119 ms *(1c)* | **0.31** (geomean **0.29**) | |

| query | LexDB wall (4c) | PG 4-proc wall | LexDB / PG4 | LexDB total CPU | PG 1-core CPU | CPU ratio | LexDB + MV |
|---|---:|---:|---:|---:|---:|---:|---:|
| q0 | 16.2 ms | 36.4 ms | 0.45 | 16.3 ms | 116.2 ms | 0.14 | **0.58 ms** |
| q1 | 72.1 ms | 100.7 ms | 0.72 | 71.8 ms | 359.5 ms | 0.20 | **0.63 ms** |
| q2 | 72.5 ms | 104.4 ms | 0.69 | 72.2 ms | 404.3 ms | 0.18 | **0.69 ms** |
| q3 | 58.6 ms | 76.4 ms | 0.77 | 58.4 ms | 282.8 ms | 0.21 | **0.64 ms** |
| q4 | 69.8 ms | 296.6 ms | 0.24 | 99.7 ms | 331.3 ms | 0.30 | **5.99 ms** |
| q5 | 80.7 ms | 410.2 ms | 0.20 | 125.3 ms | 452.2 ms | 0.28 | — |
| q6 | 66.7 ms | 78.3 ms | 0.85 | 121.9 ms | 283.0 ms | 0.43 | **0.54 ms** |
| q7 | 73.2 ms | 101.7 ms | 0.72 | 72.9 ms | 353.5 ms | 0.21 | **0.47 ms** |
| q8 | 79.0 ms | 465.5 ms | 0.17 | 115.4 ms | 513.2 ms | 0.22 | **5.06 ms** |
| q9 | 118.4 ms | 590.8 ms | 0.20 | 177.4 ms | 640.4 ms | 0.28 | **12.69 ms** |
| q10 | 80.0 ms | 103.5 ms | 0.77 | 103.7 ms | 367.5 ms | 0.28 | **0.83 ms** |
| q11 | 83.1 ms | 108.6 ms | 0.77 | 108.3 ms | 372.2 ms | 0.29 | **0.90 ms** |
| q12 | 77.7 ms | 114.6 ms | 0.68 | 107.7 ms | 393.8 ms | 0.27 | **41.38 ms** |
| q13 | 114.4 ms | 146.7 ms | 0.78 | 153.9 ms | 410.5 ms | 0.37 | **32.80 ms** |
| q14 | 83.4 ms | 351.2 ms | 0.24 | 117.8 ms | 393.3 ms | 0.30 | **48.82 ms** |
| q15 | 87.1 ms | 134.8 ms | 0.65 | 86.8 ms | 356.5 ms | 0.24 | **144.53 ms** |
| q16 | 115.6 ms | 453.9 ms | 0.25 | 214.4 ms | 495.9 ms | 0.43 | — |
| q17 | 141.9 ms | 165.9 ms | 0.86 | 141.3 ms | 475.9 ms | 0.30 | — |
| q18 | 189.6 ms | 639.2 ms | 0.30 | 466.6 ms | 694.3 ms | 0.67 | — |
| q19 | 65.7 ms | 74.8 ms | 0.88 | 65.5 ms | 269.3 ms | 0.24 | — |
| q20 | 95.4 ms | 110.6 ms | 0.86 | 95.2 ms | 398.1 ms | 0.24 | **54.86 ms** |
| q21 | 97.3 ms | 131.0 ms | 0.74 | 96.9 ms | 461.9 ms | 0.21 | — |
| q22 | 93.7 ms | 147.3 ms | 0.64 | 93.2 ms | 515.0 ms | 0.18 | — |
| q23 | 102.9 ms | 107.3 ms | 0.96 | 102.2 ms | 384.8 ms | 0.27 | — |
| q24 | 88.8 ms | 105.6 ms | 0.84 | 88.6 ms | 357.6 ms | 0.25 | — |
| q25 | 84.2 ms | 102.6 ms | 0.82 | 84.0 ms | 357.7 ms | 0.23 | — |
| q26 | 92.7 ms | 103.5 ms | 0.90 | 92.5 ms | 358.9 ms | 0.26 | — |
| q27 | 145.3 ms | 166.3 ms | 0.87 | 225.9 ms | 506.1 ms | 0.45 | **0.50 ms** |
| q28 | 152.5 ms | 1,078.7 ms | 0.14 | 266.7 ms | 4,017.1 ms | 0.07 | — |
| q29 | 61.2 ms | 342.1 ms | 0.18 | 61.0 ms | 876.0 ms | 0.07 | — |
| q30 | 118.8 ms | 356.6 ms | 0.33 | 153.7 ms | 380.4 ms | 0.40 | — |
| q31 | 118.6 ms | 382.0 ms | 0.31 | 166.6 ms | 402.2 ms | 0.41 | — |
| q32 | 228.6 ms | 924.6 ms | 0.25 | 620.5 ms | 928.8 ms | 0.67 | — |
| q33 | 186.6 ms | 467.7 ms | 0.40 | 349.1 ms | 496.4 ms | 0.70 | **38.26 ms** |
| q34 | 203.5 ms | 470.1 ms | 0.43 | 372.6 ms | 499.2 ms | 0.75 | **38.16 ms** |
| q35 | 98.9 ms | 158.6 ms | 0.62 | 210.2 ms | 420.1 ms | 0.50 | **4.00 ms** |
| q36 | 180.3 ms | 255.0 ms | 0.71 | 285.6 ms | 562.6 ms | 0.51 | — |
| q37 | 122.6 ms | 173.0 ms | 0.71 | 178.1 ms | 507.1 ms | 0.35 | — |
| q38 | 112.2 ms | 156.8 ms | 0.72 | 123.4 ms | 423.9 ms | 0.29 | — |
| q39 | 265.5 ms | 529.9 ms | 0.50 | 496.5 ms | 546.8 ms | 0.91 | — |
| q40 | 123.9 ms | 208.1 ms | 0.60 | 169.4 ms | 642.9 ms | 0.26 | — |
| q41 | 131.0 ms | 200.3 ms | 0.65 | 164.4 ms | 608.1 ms | 0.27 | — |
| q42 | 125.3 ms | 168.8 ms | 0.74 | 124.8 ms | 501.1 ms | 0.25 | **2.32 ms** |
| **sum** | **4,775.5 ms** | **11,400.7 ms** | **0.42** | **7,118.1 ms** | **23,118.7 ms** | **0.31** | — |
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

On non-selective full-table and graph joins, runtime filters show zero regression (TPC-H SF1 `0.935×` total / `0.977×` geomean vs prior `HEAD`, 35 Analytic Queries `0.995×` wall / `0.998×` CPU, Social Graph 11 queries `1.003×`, single-row PK select `-0.05%` `instructions:u`).

## Analytic queries (35 queries, 1M rows)

35 queries over 1M-row tables (scans, joins, groups, windows; median of 5).
The baseline columns (`LexDB`, `PG 1-core`, `PG 4-proc`) run strictly apples-to-apples with no materialized views:
LexDB's CPU is **0.39** of PostgreSQL's on one core (geometric mean; wall **0.48**), and its wall time
**0.78** of PostgreSQL's on four processes; **35 of 35** are ahead of PostgreSQL on one core
on both CPU and wall time, including `distinct` dropping 62 → 42 ms (`0.44×` PG1), `distinct2` dropping 134 → 79 ms (`0.72×` PG1),
`pk_point20k` dropping 635 → 390 ms (`0.62×` wall / `0.83×` CPU vs PG1), `join_hash_agg` at 24 ms (`0.69×` of 4-core PG),
`sub_in`/`sub_exists` at 17 ms (`0.68–0.71×` of 4-core PG), `join_text_rows` at 42 ms (`0.48×` of 4-core PG),
`sort_lim` at 6 ms, and `grp_text` at 39 ms (`0.91×` of 4-core PG).

The rightmost column (`LexDB + MV`) runs the **exact same 35 unmodified queries** after creating four
general-purpose incremental `ENABLE QUERY REWRITE` rollup views (`mv_w_cube` 1,940 rows / 189 ms build,
`mv_w_join_d` 10 rows / 170 ms, `mv_w_join_cr` 17 rows / 141 ms, `mv_w_join_t` 1 row / 218 ms). Nine aggregate
and join-aggregate queries transparently rewrite onto those views with exact result parity, dropping from
8–91 ms to 3–4 ms (0–1 ms server CPU; the remaining ~3 ms is `psql` process startup), bringing the 35-query
geometric mean to **0.31** against PG 1-core and **0.49** against PG 4-proc. After data load, inserting
1 / 100 / 1,000 new rows into `w` while keeping all four views live (`REFRESH FAST ON STATEMENT`) takes
**4.40 / 7.09 / 25.90 ms** (including `psql` startup and durable commit), whereas PostgreSQL 18 requires
**758.4 ms** (1-core) or **263.7 ms** (4-proc) to `REFRESH MATERIALIZED VIEW` all four views after any write.

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 | LexDB + MV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `scan2` | 109 ms | 141 ms | 0.77 | 53 ms | 80 ms | 0.66 | 141 ms | 0.77 | 115 ms |
| `scan3` | 159 ms | 213 ms | 0.75 | 74 ms | 120 ms | 0.62 | 215 ms | 0.74 | 167 ms |
| `scan9` | 503 ms | 532 ms | 0.95 | 248 ms | 250 ms | 0.99 | 532 ms | 0.95 | 532 ms |
| `filt1pct` | 17 ms | 41 ms | 0.41 | 12 ms | 40 ms | 0.30 | 22 ms | 0.77 | 21 ms |
| `filt10pct` | 32 ms | 59 ms | 0.54 | 19 ms | 50 ms | 0.38 | 59 ms | 0.54 | 37 ms |
| `filt_like` | 54 ms | 81 ms | 0.67 | 49 ms | 80 ms | 0.61 | 32 ms | 1.69 | 57 ms |
| `filt_agg` | 18 ms | 45 ms | 0.40 | 14 ms | 40 ms | 0.35 | 22 ms | 0.82 | 23 ms |
| `expr_int` | 149 ms | 217 ms | 0.69 | 70 ms | 140 ms | 0.50 | 215 ms | 0.69 | 160 ms |
| `expr_mix` | 362 ms | 422 ms | 0.86 | 244 ms | 300 ms | 0.81 | 418 ms | 0.87 | 381 ms |
| `expr_agg` | 31 ms | 58 ms | 0.53 | 27 ms | 60 ms | 0.45 | 25 ms | 1.24 | **3 ms** |
| `sort_all` | 116 ms | 447 ms | 0.26 | 61 ms | 390 ms | 0.16 | 443 ms | 0.26 | 120 ms |
| `sort_lim` | 6 ms | 91 ms | 0.07 | 3 ms | 90 ms | 0.03 | 33 ms | 0.18 | 6 ms |
| `count` | 8 ms | 36 ms | 0.22 | 4 ms | 30 ms | 0.13 | 18 ms | 0.44 | **3 ms** |
| `grp_int` | 24 ms | 95 ms | 0.25 | 20 ms | 100 ms | 0.20 | 35 ms | 0.69 | **3 ms** |
| `grp_text` | 39 ms | 127 ms | 0.31 | 35 ms | 130 ms | 0.27 | 43 ms | 0.91 | **4 ms** |
| `minmax_text` | 54 ms | 132 ms | 0.41 | 50 ms | 130 ms | 0.38 | 43 ms | 1.26 | **3 ms** |
| `distinct` | 42 ms | 95 ms | 0.44 | 37 ms | 100 ms | 0.37 | 34 ms | 1.24 | 77 ms |
| `distinct2` | 79 ms | 110 ms | 0.72 | 74 ms | 110 ms | 0.67 | 40 ms | 1.98 | 173 ms |
| `idx_range1k` | 4 ms | 10 ms | 0.40 | 1 ms | 10 ms | 0.10 | 10 ms | 0.40 | 5 ms |
| `idx_range100k` | 42 ms | 46 ms | 0.91 | 30 ms | 30 ms | 1.00 | 46 ms | 0.91 | 50 ms |
| `idx_range_agg` | 26 ms | 30 ms | 0.87 | 22 ms | 30 ms | 0.73 | 24 ms | 1.08 | 32 ms |
| `pk_range100k` | 20 ms | 32 ms | 0.62 | 8 ms | 20 ms | 0.40 | 32 ms | 0.62 | 22 ms |
| `pk_point20k` | 390 ms | 629 ms | 0.62 | 356 ms | 430 ms | 0.83 | 642 ms | 0.61 | 680 ms |
| `join_hash_agg` | 24 ms | 95 ms | 0.25 | 20 ms | 100 ms | 0.20 | 35 ms | 0.69 | **3 ms** |
| `join_hash_rows` | 30 ms | 63 ms | 0.48 | 20 ms | 60 ms | 0.33 | 63 ms | 0.48 | 36 ms |
| `join_lookup_agg` | 74 ms | 80 ms | 0.93 | 70 ms | 80 ms | 0.88 | 33 ms | 2.24 | **3 ms** |
| `sub_in` | 17 ms | 50 ms | 0.34 | 13 ms | 50 ms | 0.26 | 24 ms | 0.71 | 26 ms |
| `sub_exists` | 17 ms | 50 ms | 0.34 | 13 ms | 50 ms | 0.26 | 25 ms | 0.68 | 26 ms |
| `sub_corr_sel` | 106 ms | 150 ms | 0.71 | 92 ms | 150 ms | 0.61 | 150 ms | 0.71 | 122 ms |
| `window` | 101 ms | 144 ms | 0.70 | 86 ms | 130 ms | 0.66 | 91 ms | 1.11 | 120 ms |
| `join_hash_sort` | 52 ms | 111 ms | 0.47 | 40 ms | 100 ms | 0.40 | 55 ms | 0.95 | 61 ms |
| `join_text_agg` | 49 ms | 85 ms | 0.58 | 45 ms | 80 ms | 0.56 | 32 ms | 1.53 | **3 ms** |
| `join_text_rows` | 42 ms | 86 ms | 0.49 | 31 ms | 80 ms | 0.39 | 87 ms | 0.48 | 73 ms |
| `join_text_group` | 74 ms | 169 ms | 0.44 | 69 ms | 170 ms | 0.41 | 54 ms | 1.37 | **3 ms** |
| `join_left_rows` | 29 ms | 56 ms | 0.52 | 15 ms | 40 ms | 0.38 | 59 ms | 0.49 | 33 ms |
| **geomean** | | | **0.48** | | | **0.39** | | **0.78** | **0.31 / 0.49** |

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

Prepared statements over Unix sockets, 1M rows, median of three 10 s rounds:

| | LexDB | PostgreSQL | LexDB / PostgreSQL |
|---|---:|---:|---:|
| point selects, 1 client | 90,358/s | 74,476/s | 1.21 |
| point selects, 8 / 32 clients, one process | 168,897 / 162,732/s | 427,460 / 397,465/s | 0.40 / 0.41 |
| point selects, 32 clients, three read replicas | 470,054–490,451/s | 397,465/s | 1.18–1.23 |
| updates, 1 / 8 / 32 clients (a durable commit each) | 3,943 / 17,811 / 63,304/s | 1,637 / 6,668 / 25,673/s | 2.41 / 2.67 / 2.47 |

LexDB runs every session on one thread; it scales reads with [read replica](replicas.md) processes, which follow the
master with a lag of 0.22–0.23 ms at the median and 0.41–0.44 ms at p99 under a mixed load
(368,100–402,800/s replica selects alongside 15,480–16,090/s master updates). Its commit latency
with 8 clients is 0.42 ms at the median and 0.86–0.89 ms at p99.

### `sysbench` OLTP (1M rows)

`bench/sysbench/run.sh`: sysbench 1.0.20, 4 tables × 250,000 rows (`sbtest1..4` with secondary index `k_i`),
prepared statements (`--db-ps-mode=auto`), Unix sockets, 10 s per run at a fixed clock (`cpu-boost off`),
servers on CPUs 0–3 and client on CPUs 4–7 and 12–15. Both servers run durable (`fsync` and `synchronous_commit` on).
LexDB defaults to `SERIALIZABLE` isolation and also supports opt-in `READ COMMITTED`; PostgreSQL runs at its default `READ COMMITTED`.
Both isolation levels are shown for `oltp_read_write`.
Prepare (1M rows + 4 secondary indexes + `ANALYZE`): LexDB 5.04 s vs PostgreSQL 2.55 s.

LexDB (1 process) vs PostgreSQL 18 (4 cores):

| workload | threads | LexDB TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio | LexDB err | PG err |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 76,910 | 65,124 | 1.18 | 0.01 | 0.02 | 13.0 | 10.1 | 1.28 | 0 | 0 |
| `oltp_point_select` | 8 | 149,549 | 369,540 | 0.40 | 0.06 | 0.03 | 6.7 | 10.7 | 0.62 | 0 | 0 |
| `oltp_point_select` | 32 | 146,718 | 334,053 | 0.44 | 0.23 | 0.15 | 6.8 | 11.9 | 0.57 | 0 | 0 |
| `oltp_read_only` | 1 | 2,839 | 2,418 | 1.17 | 0.37 | 0.43 | 350.1 | 326.2 | 1.07 | 0 | 0 |
| `oltp_read_only` | 8 | 3,907 | 11,547 | 0.34 | 2.39 | 0.80 | 254.8 | 341.0 | 0.75 | 0 | 0 |
| `oltp_read_only` | 32 | 3,749 | 10,241 | 0.37 | 9.06 | 4.18 | 265.8 | 389.9 | 0.68 | 0 | 0 |
| `oltp_read_write` (`SERIALIZABLE`) | 1 | 1,192 | 829 | 1.44 | 0.92 | 1.32 | 641.7 | 565.8 | 1.13 | 0 | 0 |
| `oltp_read_write` (`SERIALIZABLE`) | 8 | 1,654 | 4,082 | 0.41 | 8.13 | 2.22 | 604.1 | 607.1 | 1.00 | 3,902 | 14 |
| `oltp_read_write` (`SERIALIZABLE`) | 32 | 1,055 | 5,553 | 0.19 | 71.83 | 8.28 | 948.1 | 690.3 | 1.37 | 11,187 | 66 |
| `oltp_read_write` (`READ COMMITTED`) | 1 | 1,127 | 829 | 1.36 | 1.14 | 1.32 | 675.9 | 565.8 | 1.19 | 0 | 0 |
| `oltp_read_write` (`READ COMMITTED`) | 8 | 1,682 | 4,082 | 0.41 | 5.47 | 2.22 | 593.8 | 607.1 | 0.98 | 0 | 14 |
| `oltp_read_write` (`READ COMMITTED`) | 32 | 1,806 | 5,553 | 0.33 | 20.37 | 8.28 | 552.4 | 690.3 | 0.80 | 0 | 66 |
| `oltp_write_only` | 1 | 2,678 | 1,326 | 2.02 | 0.45 | 0.80 | 194.8 | 200.4 | 0.97 | 0 | 0 |
| `oltp_write_only` | 8 | 8,389 | 5,964 | 1.41 | 1.82 | 1.39 | 119.4 | 152.4 | 0.78 | 0 | 28 |
| `oltp_write_only` | 32 | 7,389 | 18,505 | 0.40 | 9.73 | 2.35 | 135.9 | 137.4 | 0.99 | 0 | 318 |
| `oltp_update_index` | 1 | 3,489 | 1,501 | 2.32 | 0.41 | 0.70 | 110.3 | 138.5 | 0.80 | 0 | 0 |
| `oltp_update_index` | 8 | 17,075 | 5,882 | 2.90 | 0.62 | 1.96 | 44.3 | 82.8 | 0.54 | 0 | 0 |
| `oltp_update_index` | 32 | 28,130 | 20,992 | 1.34 | 2.26 | 2.22 | 35.7 | 55.0 | 0.65 | 0 | 0 |
| `oltp_update_non_index` | 1 | 3,969 | 1,381 | 2.88 | 0.29 | 0.80 | 65.6 | 139.2 | 0.47 | 0 | 0 |
| `oltp_update_non_index` | 8 | 18,537 | 5,898 | 3.14 | 0.46 | 1.96 | 27.9 | 70.5 | 0.40 | 0 | 0 |
| `oltp_update_non_index` | 32 | 58,895 | 23,015 | 2.56 | 0.67 | 1.55 | 17.0 | 48.6 | 0.35 | 0 | 0 |

LexDB (3 read replicas, 4 processes) vs PostgreSQL 18 (4 cores) — read workloads:

| workload | threads | LexDB 3-rep TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 77,233 | 65,124 | 1.19 | 0.01 | 0.02 | 12.9 | 10.1 | 1.28 |
| `oltp_point_select` | 8 | 391,829 | 369,540 | 1.06 | 0.03 | 0.03 | 7.6 | 10.7 | 0.71 |
| `oltp_point_select` | 32 | 430,868 | 334,053 | 1.29 | 0.11 | 0.15 | 6.9 | 11.9 | 0.58 |
| `oltp_read_only` | 1 | 2,839 | 2,418 | 1.17 | 0.37 | 0.43 | 350.3 | 326.2 | 1.07 |
| `oltp_read_only` | 8 | 10,941 | 11,547 | 0.95 | 0.99 | 0.80 | 273.0 | 341.0 | 0.80 |
| `oltp_read_only` | 32 | 10,011 | 10,241 | 0.98 | 5.67 | 4.18 | 296.0 | 389.9 | 0.76 |

## Bulk loads

`\copy`, median of 3, not pinned:

| workload | LexDB | PostgreSQL 18 | LexDB / PG | LexDB peak RSS |
|---|---:|---:|---:|---:|
| narrow, 1M rows | 0.26 s | 0.61 s | 0.43 | 224 MB |
| wide, 1M rows | 1.07 s | 2.00 s | 0.54 | 619 MB |
| wide + 2 secondary indexes, 1M rows | 1.89 s | 4.90 s | 0.39 | 1,029 MB |
| wide, no primary key, 1M rows | 1.13 s | 1.41 s | 0.80 | 658 MB |
| narrow, 10M rows | 2.61 s | 5.93 s | 0.44 | 2,103 MB |

## Property graphs (SQL/PGQ)

11 social-graph queries (`G1`–`G11`: 1–4 hop traversals, full-graph aggregations, filtered multi-hop joins, triangle counting, point-to-point and single-source shortest paths) over 100k vertices and 1.1M edges, warm median of 5, single core / single thread (`cpu-boost off`), exact result parity across all four engines (11/11). See [property-graphs.md](property-graphs.md) for the full query-by-query table, cold vs warm shortest-path latencies, and execution engine architecture.

| Metric (11 queries, 1 core / 1 thread) | LexDB | PostgreSQL 18 | DuckDB 2.0 + DuckPGQ | Kùzu 0.11.3 |
|---|---:|---:|---:|---:|
| Sum of all 11 queries | **500.9 ms** | 5,660.5 ms | 962.2 ms | 1,367.4 ms |
| Geometric mean (LexDB / peer) | — | **0.13× (7.82× faster)** | **0.33× (3.06× faster)** | **0.17× (5.86× faster)** |
| 5-hop shortest path (`G10`) | **0.45 ms** (`0.71 ms` cold) | 1,080.53 ms | 61.89 ms | 40.59 ms |
| Single-source shortest paths (`G11`, 2k targets) | **5.83 ms** (`24.86 ms` cold) | 1,263.90 ms | 64.31 ms | 48.26 ms |
| Full-graph 1M-edge triangles (`G9`) | **226.55 ms** | 1,813.83 ms | 518.85 ms | 521.31 ms |

## Not measured in this run

- **SQL Server** against LexDB: its container was not running for this run.
- **Oracle** comparison: dropped for now, to be added back later.
