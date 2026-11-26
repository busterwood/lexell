# LexDB performance

Measured on 24–26 November 2026 on `main` (analytics, joins, and graph suites refreshed at `4c1fb4cc` after vectorized `DISTINCT` / `i128` `SUM`/`AVG`, packed hash tables with L3 Bloom pre-filters and `neqCountOnly` joins, single-pass columnar wide-table decoding, and simple-query auto-parameterized PK selects; OLTP, bulk loads, and materialized views from `59797d55`). Every number compares LexDB directly against **PostgreSQL 18.6** on the same machine, data, disk, and transport.

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
| **TPC-H SF1** (22 queries, 1 core) | **6,286 ms** | 14,670 ms (1 core) / 8,839 ms (4 proc) | **2.33× faster** than 1 core (22/22 faster, geomean `0.45` wall / `0.42` CPU); **1.41× faster** than 4 proc (`0.72` geomean) |
| **ClickBench 1M** (43 queries, 105 cols, 1 core) | **12,161 ms** | 22,363 ms (1 core) / 11,326 ms (4 proc) | **1.84× faster** than 1 core (42/43 level or ahead; geomean `0.58` wall / `0.55` CPU; within **7%** of 4-core PG on 1 core) |
| **ClickBench 1M + 8 MVs** (unmodified queries, 1 core) | **9,068 ms** | 11,326 ms (4 proc) | **1.25× faster than 4-core PG on one core** (21 rewritten; geomean `0.10` vs PG1 / `0.21` vs PG4) |
| **ClickBench 1M + 3 skipping indexes** | 42.6–485.4 ms | — | **1.28–4.07× faster** on selective point & `LIKE '%substring%'` filters; zero OLTP write/read regression |
| **Selective star-schema joins** (1M fact rows, 6 patterns, 1 core) | **0.54–22.5 ms** | 0.21–77.0 ms (1 core) / 0.24–50.7 ms (4 proc) | **1.24–71.7× faster** (`4.87×` geomean) via hash-join runtime filters; **7.68× faster** than 1-core PG / **4.46×** vs 4-proc PG (geomean) |
| **35 Analytic Queries** (1M rows, 1 core) | **`0.39×` CPU / `0.78×` wall** | 1 core / 4 proc | **2.59× less CPU** than 1 core (**35/35** ahead on CPU and wall); **1.28× faster** than 4 proc on wall (`0.31 / 0.49` geomean with 4 MVs) |
| **Materialized view maintenance** (1M rows, 1 row) | **0.43–0.66 ms** (`FAST`) | 60–369 ms (`REFRESH`) | **90–780× faster** incremental updates; sketch MV build **220 vs 379 ms**; hot-key `realtime` **22,102 commits/s** |
| **Durable OLTP updates** (1–32 clients) | up to **63.3k/s** (`pgbench`) / **54.2k/s** (`sysbench`) | 25.7k/s / 23.0k/s | **2.41–2.67×** (`pgbench`); **2.36–3.13×** (`sysbench` non-index); **1.32–2.54×** (`sysbench` indexed) |
| **Point selects (3 read replicas, 32 clients)** | **470–490k/s** (`pgbench`) / **350.5k/s** (`sysbench`) | 397k/s / 334k/s (4 cores) | **1.18–1.23×** (`pgbench`); **1.05×** (`sysbench`, 29% less CPU); replica lag **0.22 ms** p50 / **0.44 ms** p99 |
| **Bulk `\copy` loads** (5 cases, 1M–10M rows) | 0.24–2.44 s | 0.61–5.93 s | **1.1–2.7× faster** (`0.37–0.94×`) on all 5 workloads |
| **Property graphs — LDBC LSQB SF1** (9 queries, 22.2M edges, 1 core) | **8.14 s** (`0.10 s` Q6 / `0.82 s` Q1 / `2.24 s` Q9) | 98.1 s (PG1, 8/9) / 4.56 s (DuckPGQ+FK) / 105.0 s (Kùzu) / 156.0 s (Neo4j CE) | **#2 overall behind in-memory DuckPGQ+FK; #1 disk-backed DB** — geomean **9.02×** vs PG1, **4.17×** vs Kùzu (**12.9×** total), **16.5×** vs Neo4j CE (**19.2×** total); `Q6` **5.51× faster than DuckPGQ** ([full report](property-graphs.md#benchmark-2-ldbc-lsqb-sf01-and-sf1-5-engines)) |
| **Property graphs — social suite** (11 queries, 1.1M edges, 1 core) | **505.5 ms** (`0.41 ms` G10 / `5.78 ms` G11 / `226.5 ms` G9) | 5,661 ms (PG1) / 962 ms (DuckPGQ) / 1,367 ms (Kùzu) | **Fastest total time of all 4** (**1.90×** DuckPGQ, **2.71×** Kùzu, **11.2×** PG1); geomean **7.74×** vs PG1, **3.03×** vs DuckPGQ, **5.81×** vs Kùzu ([full report](property-graphs.md#benchmark-1-social-network-graph-suite-11-queries-11m-edges)) |

PostgreSQL is ahead on single-process multi-thread reads (before adding replicas) and multi-statement read-write blocks.

## TPC-H derived (SF1)

22 queries, SF1, warm, median of 3, at a fixed clock with boost off; every result checked against PostgreSQL's (22/22 exact match):

| | LexDB (one core) | PostgreSQL, one core | PostgreSQL, four processes |
|---|---:|---:|---:|
| all 22 queries, summed (wall) | **6,286 ms** | 14,670 ms | 8,839 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | **0.45** | **0.72** |
| geometric mean of LexDB / PostgreSQL (CPU) | | **0.42** | |
| queries faster than one core | | **22 of 22** | |

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| q1 | 1,061.9 ms | 3,365.9 ms | 0.32 | 1,058.2 ms | 3,375.3 ms | 0.31 | 873.5 ms | 1.22 |
| q2 | 32.5 ms | 160.9 ms | 0.20 | 32.4 ms | 166.9 ms | 0.19 | 137.6 ms | 0.24 |
| q3 | 262.8 ms | 551.7 ms | 0.48 | 261.7 ms | 579.3 ms | 0.45 | 353.6 ms | 0.74 |
| q4 | 115.3 ms | 184.9 ms | 0.62 | 114.8 ms | 211.6 ms | 0.54 | 102.9 ms | 1.12 |
| q5 | 124.0 ms | 312.6 ms | 0.40 | 123.5 ms | 341.2 ms | 0.36 | 173.2 ms | 0.72 |
| q6 | 172.2 ms | 274.8 ms | 0.63 | 171.5 ms | 294.1 ms | 0.58 | 203.4 ms | 0.85 |
| q7 | 335.1 ms | 585.8 ms | 0.57 | 333.7 ms | 615.2 ms | 0.54 | 287.6 ms | 1.17 |
| q8 | 147.6 ms | 226.2 ms | 0.65 | 146.9 ms | 253.5 ms | 0.58 | 141.9 ms | 1.04 |
| q9 | 1,117.2 ms | 1,743.2 ms | 0.64 | 1,112.3 ms | 1,770.1 ms | 0.63 | 750.9 ms | 1.49 |
| q10 | 255.1 ms | 389.0 ms | 0.66 | 253.8 ms | 417.2 ms | 0.61 | 167.3 ms | 1.52 |
| q11 | 51.2 ms | 61.4 ms | 0.83 | 51.0 ms | 67.7 ms | 0.75 | 61.5 ms | 0.83 |
| q12 | 397.9 ms | 854.9 ms | 0.47 | 396.4 ms | 880.7 ms | 0.45 | 253.6 ms | 1.57 |
| q13 | 520.3 ms | 839.8 ms | 0.62 | 517.8 ms | 843.9 ms | 0.61 | 825.6 ms | 0.63 |
| q14 | 120.2 ms | 141.6 ms | 0.85 | 119.6 ms | 159.8 ms | 0.75 | 95.1 ms | 1.26 |
| q15 | 152.6 ms | 331.9 ms | 0.46 | 152.4 ms | 348.1 ms | 0.44 | 333.9 ms | 0.46 |
| q16 | 198.9 ms | 267.9 ms | 0.74 | 196.5 ms | 273.4 ms | 0.72 | 105.3 ms | 1.89 |
| q17 | 21.1 ms | 551.2 ms | 0.04 | 21.1 ms | 569.9 ms | 0.04 | 554.7 ms | 0.04 |
| q18 | 528.5 ms | 2,753.9 ms | 0.19 | 526.5 ms | 2,722.6 ms | 0.19 | 2,933.0 ms | 0.18 |
| q19 | 27.7 ms | 40.2 ms | 0.69 | 27.8 ms | 53.6 ms | 0.52 | 37.5 ms | 0.74 |
| q20 | 27.4 ms | 125.8 ms | 0.22 | 27.5 ms | 149.3 ms | 0.18 | 127.8 ms | 0.21 |
| q21 | 569.2 ms | 818.4 ms | 0.70 | 566.9 ms | 846.4 ms | 0.67 | 269.6 ms | 2.11 |
| q22 | 46.9 ms | 88.4 ms | 0.53 | 46.8 ms | 94.1 ms | 0.50 | 49.5 ms | 0.95 |
| **sum** | **6,285.6 ms** | **14,670.4 ms** | **0.43** | **6,259.2 ms** | **15,033.9 ms** | **0.42** | **8,839.0 ms** | **0.71** |
| **geomean** | | | **0.45** | | | **0.42** | | **0.72** |

## ClickBench (1M rows)

`bench/clickbench/run.sh`: official ClickBench `hits` schema (105 columns, wide web-analytics table) and all 43 queries
(`q0`–`q42`) on the first 1,000,000 rows, warm, median of 3, at a fixed clock (`cpu-boost off`), both servers on CPUs 0–3.
All 43 queries pass (31 exact MD5 matches; 12 top-N/unordered queries with matching row counts).

The baseline columns (`LexDB wall`, `PG 1-core`, `PG 4-proc`) run strictly apples-to-apples with no materialized views
and no explicit skipping indexes (automatic zero-config `T_CLEAF` zone maps, adaptive two-level hash aggregation with
bump-arena string keys, direct Top-N group pruning, dictionary-code deduplication, and vectorized string/regex kernels
are always on by default).

The final column (`LexDB + MV`) shows a separate run of the **exact same unmodified queries** after adding eight
general-purpose incremental `ENABLE QUERY REWRITE` rollup views (`mv_hits_adv` 6 rows / 871 ms build,
`mv_hits_counter` 7 rows / 564 ms, `mv_hits_region_user` 80,309 rows / 646 ms, `mv_hits_mobile` 2,522 rows / 292 ms,
`mv_hits_search` 28,357 rows / 441 ms, `mv_hits_url` 275,494 rows / 1,812 ms, `mv_hits_ip` 68,330 rows / 445 ms,
`mv_hits_minute` 4,346 rows / 943 ms; total build 6.01 s), exercising exact `COUNT(DISTINCT)` rollups (`q4`, `q8`–`q11`,
`q13`), wide (`>512`-byte) hashed group keys (`q12`–`q14`, `q20`, `q33`, `q34`), and functionally dependent exact-grain
`GROUP BY` matching (`q34`, `q35`). All 21 rewritten queries were verified against `query_rewrite_enabled = off` (19
bit-for-bit identical; `q10` and `q11` match exact counts with tie-breaking at count 12). After data load, inserting
1 / 100 new `hits` rows while maintaining all 8 views live (`REFRESH FAST ON STATEMENT`) takes **6.51 / 10.34 ms**.

| | LexDB (one core) | PostgreSQL, one core | PostgreSQL, four processes | LexDB + 8 MVs (transparent rewrite) |
|---|---:|---:|---:|---:|
| all 43 queries, summed (wall) | **12,161 ms** | 22,363 ms | 11,326 ms | 9,068 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | **0.58** | **1.29** | 0.10 vs PG1 / 0.21 vs PG4 |
| geometric mean of LexDB / PostgreSQL (CPU) | | **0.55** | | |
| queries level or ahead of one core (within 10%) | | **42 of 43** | | 42 of 43 (21 rewritten; 29 of 43 vs PG4) |

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 | LexDB + MV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q0 | 50.3 ms | 87.5 ms | 0.57 | 50.2 ms | 109.9 ms | 0.46 | 34.7 ms | 1.45 | **0.58 ms** |
| q1 | 182.3 ms | 342.0 ms | 0.53 | 181.5 ms | 361.5 ms | 0.50 | 106.3 ms | 1.71 | **0.63 ms** |
| q2 | 177.4 ms | 392.2 ms | 0.45 | 176.7 ms | 411.9 ms | 0.43 | 107.7 ms | 1.65 | **0.69 ms** |
| q3 | 141.1 ms | 256.2 ms | 0.55 | 140.6 ms | 276.6 ms | 0.51 | 80.0 ms | 1.76 | **0.64 ms** |
| q4 | 154.8 ms | 304.0 ms | 0.51 | 154.1 ms | 323.7 ms | 0.48 | 302.4 ms | 0.51 | **5.99 ms** |
| q5 | 243.8 ms | 429.8 ms | 0.57 | 242.8 ms | 450.0 ms | 0.54 | 419.5 ms | 0.58 | — |
| q6 | 184.4 ms | 252.1 ms | 0.73 | 183.6 ms | 273.4 ms | 0.67 | 79.3 ms | 2.33 | **0.54 ms** |
| q7 | 182.7 ms | 337.2 ms | 0.54 | 181.8 ms | 357.9 ms | 0.51 | 107.1 ms | 1.71 | **0.47 ms** |
| q8 | 171.7 ms | 489.4 ms | 0.35 | 171.0 ms | 509.3 ms | 0.34 | 479.0 ms | 0.36 | **5.06 ms** |
| q9 | 236.6 ms | 624.1 ms | 0.38 | 235.6 ms | 643.1 ms | 0.37 | 604.6 ms | 0.39 | **12.69 ms** |
| q10 | 183.6 ms | 347.7 ms | 0.53 | 182.7 ms | 368.2 ms | 0.50 | 101.3 ms | 1.81 | **0.83 ms** |
| q11 | 185.6 ms | 352.4 ms | 0.53 | 184.8 ms | 371.1 ms | 0.50 | 103.8 ms | 1.79 | **0.90 ms** |
| q12 | 200.4 ms | 365.6 ms | 0.55 | 199.4 ms | 385.4 ms | 0.52 | 113.6 ms | 1.76 | **41.38 ms** |
| q13 | 232.0 ms | 381.5 ms | 0.61 | 231.0 ms | 402.8 ms | 0.57 | 143.7 ms | 1.61 | **32.80 ms** |
| q14 | 216.9 ms | 363.1 ms | 0.60 | 215.9 ms | 383.8 ms | 0.56 | 346.7 ms | 0.63 | **48.82 ms** |
| q15 | 171.3 ms | 336.5 ms | 0.51 | 170.6 ms | 359.0 ms | 0.48 | 132.2 ms | 1.30 | **144.53 ms** |
| q16 | 332.4 ms | 468.6 ms | 0.71 | 330.8 ms | 488.9 ms | 0.68 | 442.8 ms | 0.75 | — |
| q17 | 249.8 ms | 444.5 ms | 0.56 | 248.7 ms | 464.2 ms | 0.54 | 162.0 ms | 1.54 | — |
| q18 | 409.9 ms | 674.1 ms | 0.61 | 407.8 ms | 692.9 ms | 0.59 | 635.6 ms | 0.64 | — |
| q19 | 155.1 ms | 238.6 ms | 0.65 | 154.5 ms | 259.3 ms | 0.60 | 73.6 ms | 2.11 | — |
| q20 | 272.8 ms | 375.3 ms | 0.73 | 271.6 ms | 397.4 ms | 0.68 | 106.5 ms | 2.56 | **54.86 ms** |
| q21 | 266.7 ms | 456.5 ms | 0.58 | 265.4 ms | 476.3 ms | 0.56 | 134.2 ms | 1.99 | — |
| q22 | 467.0 ms | 512.7 ms | 0.91 | 465.0 ms | 533.1 ms | 0.87 | 137.7 ms | 3.39 | — |
| q23 | 306.8 ms | 370.6 ms | 0.83 | 305.4 ms | 390.8 ms | 0.78 | 104.2 ms | 2.94 | — |
| q24 | 204.2 ms | 349.7 ms | 0.58 | 203.4 ms | 370.1 ms | 0.55 | 100.6 ms | 2.03 | — |
| q25 | 198.7 ms | 347.4 ms | 0.57 | 197.8 ms | 367.8 ms | 0.54 | 100.5 ms | 1.98 | — |
| q26 | 208.2 ms | 351.7 ms | 0.59 | 207.2 ms | 371.6 ms | 0.56 | 100.9 ms | 2.06 | — |
| q27 | 350.6 ms | 501.9 ms | 0.70 | 349.0 ms | 523.8 ms | 0.67 | 169.1 ms | 2.07 | **0.50 ms** |
| q28 | 952.4 ms | 4,030.8 ms | 0.24 | 948.5 ms | 4,039.0 ms | 0.23 | 1,057.0 ms | 0.90 | — |
| q29 | 159.4 ms | 852.2 ms | 0.19 | 158.6 ms | 871.6 ms | 0.18 | 336.3 ms | 0.47 | — |
| q30 | 218.0 ms | 362.4 ms | 0.60 | 216.9 ms | 382.1 ms | 0.57 | 353.7 ms | 0.62 | — |
| q31 | 224.5 ms | 385.5 ms | 0.58 | 223.4 ms | 406.5 ms | 0.55 | 375.7 ms | 0.60 | — |
| q32 | 389.6 ms | 917.0 ms | 0.42 | 387.7 ms | 935.4 ms | 0.41 | 905.7 ms | 0.43 | — |
| q33 | 401.7 ms | 479.2 ms | 0.84 | 399.6 ms | 498.1 ms | 0.80 | 461.8 ms | 0.87 | **38.26 ms** |
| q34 | 402.4 ms | 487.0 ms | 0.83 | 400.3 ms | 506.5 ms | 0.79 | 466.9 ms | 0.86 | **38.16 ms** |
| q35 | 252.8 ms | 396.7 ms | 0.64 | 251.7 ms | 416.7 ms | 0.60 | 156.4 ms | 1.62 | **4.00 ms** |
| q36 | 419.3 ms | 548.0 ms | 0.77 | 417.3 ms | 566.9 ms | 0.74 | 246.7 ms | 1.70 | — |
| q37 | 509.1 ms | 494.2 ms | 1.03 | 506.7 ms | 514.5 ms | 0.98 | 169.9 ms | 3.00 | — |
| q38 | 252.7 ms | 404.5 ms | 0.62 | 251.6 ms | 425.5 ms | 0.59 | 145.8 ms | 1.73 | — |
| q39 | 599.2 ms | 536.6 ms | 1.12 | 596.0 ms | 556.1 ms | 1.07 | 532.5 ms | 1.13 | — |
| q40 | 330.4 ms | 621.5 ms | 0.53 | 328.9 ms | 641.0 ms | 0.51 | 220.6 ms | 1.50 | — |
| q41 | 327.9 ms | 599.1 ms | 0.55 | 326.4 ms | 618.9 ms | 0.53 | 198.9 ms | 1.65 | — |
| q42 | 384.3 ms | 495.3 ms | 0.78 | 382.5 ms | 515.4 ms | 0.74 | 168.0 ms | 2.29 | **2.32 ms** |
| **sum** | **12,160.8 ms** | **22,362.9 ms** | **0.54** | **12,104.9 ms** | **23,218.0 ms** | **0.52** | **11,325.5 ms** | **1.07** | **9,067.5 ms** |
| **geomean** | | | **0.58** | | | **0.55** | | **1.29** | **0.10 / 0.21** |

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
Prepare (1M rows + 4 secondary indexes + `ANALYZE`): LexDB 5.60 s vs PostgreSQL 2.55 s.

LexDB (1 process) vs PostgreSQL 18 (4 cores):

| workload | threads | LexDB TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio | LexDB err | PG err |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 71,014 | 65,124 | 1.09 | 0.02 | 0.02 | 14.0 | 10.1 | 1.39 | 0 | 0 |
| `oltp_point_select` | 8 | 125,465 | 369,540 | 0.34 | 0.07 | 0.03 | 7.9 | 10.7 | 0.74 | 0 | 0 |
| `oltp_point_select` | 32 | 123,451 | 334,053 | 0.37 | 0.27 | 0.15 | 8.1 | 11.9 | 0.68 | 0 | 0 |
| `oltp_read_only` | 1 | 2,754 | 2,418 | 1.14 | 0.38 | 0.43 | 360.9 | 326.2 | 1.11 | 0 | 0 |
| `oltp_read_only` | 8 | 3,813 | 11,547 | 0.33 | 2.43 | 0.80 | 261.1 | 341.0 | 0.77 | 0 | 0 |
| `oltp_read_only` | 32 | 3,659 | 10,241 | 0.36 | 9.22 | 4.18 | 272.3 | 389.9 | 0.70 | 0 | 0 |
| `oltp_read_write` (`SERIALIZABLE`) | 1 | 1,147 | 829 | 1.38 | 0.94 | 1.32 | 676.1 | 565.8 | 1.19 | 0 | 0 |
| `oltp_read_write` (`SERIALIZABLE`) | 8 | 1,332 | 4,082 | 0.33 | 12.08 | 2.22 | 749.9 | 607.1 | 1.24 | 6,253 | 14 |
| `oltp_read_write` (`SERIALIZABLE`) | 32 | 816 | 5,553 | 0.15 | 102.97 | 8.28 | 1,221.1 | 690.3 | 1.77 | 12,744 | 66 |
| `oltp_read_write` (`READ COMMITTED`) | 1 | 1,127 | 829 | 1.36 | 1.14 | 1.32 | 675.9 | 565.8 | 1.19 | 0 | 0 |
| `oltp_read_write` (`READ COMMITTED`) | 8 | 1,682 | 4,082 | 0.41 | 5.47 | 2.22 | 593.8 | 607.1 | 0.98 | 0 | 14 |
| `oltp_read_write` (`READ COMMITTED`) | 32 | 1,806 | 5,553 | 0.33 | 20.37 | 8.28 | 552.4 | 690.3 | 0.80 | 0 | 66 |
| `oltp_write_only` | 1 | 2,594 | 1,326 | 1.96 | 0.44 | 0.80 | 201.5 | 200.4 | 1.01 | 0 | 0 |
| `oltp_write_only` | 8 | 8,016 | 5,964 | 1.34 | 1.23 | 1.39 | 125.6 | 152.4 | 0.82 | 0 | 28 |
| `oltp_write_only` | 32 | 5,499 | 18,505 | 0.30 | 7.98 | 2.35 | 181.2 | 137.4 | 1.32 | 0 | 318 |
| `oltp_update_index` | 1 | 3,540 | 1,501 | 2.36 | 0.37 | 0.70 | 99.2 | 138.5 | 0.72 | 0 | 0 |
| `oltp_update_index` | 8 | 14,932 | 5,882 | 2.54 | 0.63 | 1.96 | 52.6 | 82.8 | 0.64 | 0 | 0 |
| `oltp_update_index` | 32 | 27,657 | 20,992 | 1.32 | 1.44 | 2.22 | 36.0 | 55.0 | 0.66 | 0 | 0 |
| `oltp_update_non_index` | 1 | 3,874 | 1,381 | 2.81 | 0.29 | 0.80 | 72.7 | 139.2 | 0.52 | 0 | 0 |
| `oltp_update_non_index` | 8 | 18,482 | 5,898 | 3.13 | 0.46 | 1.96 | 28.6 | 70.5 | 0.41 | 0 | 0 |
| `oltp_update_non_index` | 32 | 54,241 | 23,015 | 2.36 | 0.75 | 1.55 | 18.4 | 48.6 | 0.38 | 0 | 0 |

LexDB (3 read replicas, 4 processes) vs PostgreSQL 18 (4 cores) — read workloads:

| workload | threads | LexDB 3-rep TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 70,829 | 65,124 | 1.09 | 0.02 | 0.02 | 14.1 | 10.1 | 1.39 |
| `oltp_point_select` | 8 | 295,252 | 369,540 | 0.80 | 0.06 | 0.03 | 10.1 | 10.7 | 0.94 |
| `oltp_point_select` | 32 | 350,462 | 334,053 | 1.05 | 0.14 | 0.15 | 8.5 | 11.9 | 0.71 |
| `oltp_read_only` | 1 | 2,608 | 2,418 | 1.08 | 0.43 | 0.43 | 374.8 | 326.2 | 1.15 |
| `oltp_read_only` | 8 | 9,898 | 11,547 | 0.86 | 1.16 | 0.80 | 296.6 | 341.0 | 0.87 |
| `oltp_read_only` | 32 | 9,998 | 10,241 | 0.98 | 3.96 | 4.18 | 298.7 | 389.9 | 0.77 |

## Bulk loads

`\copy`, median of 3, not pinned:

| workload | LexDB | PostgreSQL 18 | LexDB / PG | LexDB peak RSS |
|---|---:|---:|---:|---:|
| narrow, 1M rows | 0.24 s | 0.61 s | 0.39 | 301 MB |
| wide, 1M rows | 1.07 s | 2.00 s | 0.54 | 621 MB |
| wide + 2 secondary indexes, 1M rows | 1.79 s | 4.90 s | 0.37 | 1,331 MB |
| wide, no primary key, 1M rows | 1.32 s | 1.41 s | 0.94 | 653 MB |
| narrow, 10M rows | 2.44 s | 5.93 s | 0.41 | 2,873 MB |

## Property graphs (SQL/PGQ)

11 social-graph queries (`G1`–`G11`: 1–4 hop traversals, full-graph aggregations, filtered multi-hop joins, triangle counting, point-to-point and single-source shortest paths) over 100k vertices and 1.1M edges, warm median of 5, single core / single thread (`cpu-boost off`), exact result parity across all four engines (11/11). See [property-graphs.md](property-graphs.md) for the full query-by-query table, cold vs warm shortest-path latencies, and execution engine architecture.

| Metric (11 queries, 1 core / 1 thread) | LexDB | PostgreSQL 18 | DuckDB 2.0 + DuckPGQ | Kùzu 0.11.3 |
|---|---:|---:|---:|---:|
| Sum of all 11 queries | **505.5 ms** | 5,660.5 ms | 962.2 ms | 1,367.4 ms |
| Geometric mean (LexDB / peer) | — | **0.13× (7.74× faster)** | **0.33× (3.03× faster)** | **0.17× (5.81× faster)** |
| 5-hop shortest path (`G10`) | **0.41 ms** (`0.71 ms` cold) | 1,080.53 ms | 61.89 ms | 40.59 ms |
| Single-source shortest paths (`G11`, 2k targets) | **5.78 ms** (`23.92 ms` cold) | 1,263.90 ms | 64.31 ms | 48.26 ms |
| Full-graph 1M-edge triangles (`G9`) | **226.52 ms** | 1,813.83 ms | 518.85 ms | 521.31 ms |

## Not measured in this run

- **SQL Server** against LexDB: its container was not running for this run.
- **Oracle** comparison: dropped for now, to be added back later.
