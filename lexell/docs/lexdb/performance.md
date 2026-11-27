# LexDB performance

Measured on 24–27 November 2026 on `main` (TPC-H SF1, ClickBench 1M, `sysbench` OLTP, Social Graph 11q, and LDBC LSQB SF0.1/SF1 refreshed at `48b393c0` after Wave 2 LexDB optimizations: batched sibling-leaf `scanLeaves`, composite-key `AggSt` `fv` elision + L2 `probeBufBatch` + `twoText` dict cache + `q1` expression/agg fusion + fast URL host extractor, single-shot autocommit & in-txn `FastSelPlan` + `Store.pointRead` / `Follower.pointRead`, zero-copy wire reader + pre-framed `RowDescription`, typed `LockEntry` lock table, in-place MVCC delta pruning, compact 16B/slot `FastInt2Set`, bottom-up `foldCountJoin` with zero-rehash `intoWeightedCount` and `neqOut` weight pushdown, and weighted `count+sum`; 35 Analytic and star-schema joins from `4c1fb4cc`; `pgbench`, bulk loads, and materialized views from `59797d55`). Every number compares LexDB directly against **PostgreSQL 18.6** on the same machine, data, disk, and transport.

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
| **TPC-H SF1** (22 queries, 1 core) | **5,590 ms** | 14,670 ms (1 core) / 8,839 ms (4 proc) | **2.62× faster** than 1 core (22/22 faster, geomean `0.42` wall / `0.39` CPU; `q1` **809 ms** beats 4-proc PG); **1.58× faster** than 4 proc (`0.68` geomean) |
| **ClickBench 1M** (43 queries, 105 cols, 1 core) | **6,993 ms** | 22,081 ms (1 core) / 11,401 ms (4 proc) | **3.16× faster** than 1 core (43/43 level or ahead; geomean `0.33` wall & CPU); **1.63× faster than 4-core PG on 1 core** (`0.72` geomean, no MVs) |
| **ClickBench 1M + 8 MVs** (unmodified queries, 1 core) | **0.47–54.9 ms** *(21 rewritten)* | 22,081 ms (1 core) / 11,401 ms (4 proc) | 21 of 43 queries transparently rewritten to sub-ms–55 ms (measured at `59797d55`: geomean `0.10` vs PG1 / `0.21` vs PG4) |
| **ClickBench 1M + 3 skipping indexes** | 42.6–485.4 ms | — | **1.28–4.07× faster** on selective point & `LIKE '%substring%'` filters; zero OLTP write/read regression |
| **Selective star-schema joins** (1M fact rows, 6 patterns, 1 core) | **0.54–22.5 ms** | 0.21–77.0 ms (1 core) / 0.24–50.7 ms (4 proc) | **1.24–71.7× faster** (`4.87×` geomean) via hash-join runtime filters; **7.68× faster** than 1-core PG / **4.46×** vs 4-proc PG (geomean) |
| **35 Analytic Queries** (1M rows, 1 core) | **`0.39×` CPU / `0.78×` wall** | 1 core / 4 proc | **2.59× less CPU** than 1 core (**35/35** ahead on CPU and wall); **1.28× faster** than 4 proc on wall (`0.31 / 0.49` geomean with 4 MVs) |
| **Materialized view maintenance** (1M rows, 1 row) | **0.43–0.66 ms** (`FAST`) | 60–369 ms (`REFRESH`) | **90–780× faster** incremental updates; sketch MV build **220 vs 379 ms**; hot-key `realtime` **22,102 commits/s** |
| **Durable OLTP updates** (1–32 clients) | up to **63.3k/s** (`pgbench`) / **58.4k/s** (`sysbench`) | 25.7k/s / 23.0k/s | **2.41–2.67×** (`pgbench`); **2.54–3.12×** (`sysbench` non-index); **1.63–2.85×** (`sysbench` indexed) |
| **Point selects (3 read replicas, 32 clients)** | **470–490k/s** (`pgbench`) / **427.1k/s** (`sysbench`) | 397k/s / 334k/s (4 cores) | **1.18–1.23×** (`pgbench`); **1.28×** (`sysbench`, 42% less CPU; `oltp_read_only` **1.12×** PG); replica lag **0.22 ms** p50 / **0.44 ms** p99 |
| **Bulk `\copy` loads** (5 cases, 1M–10M rows) | 0.24–2.44 s | 0.61–5.93 s | **1.1–2.7× faster** (`0.37–0.94×`) on all 5 workloads |
| **Property graphs — LDBC LSQB SF1** (9 queries, 22.2M edges, 1 core) | **7.30 s** (`0.10 s` Q6 / `0.87 s` Q1 / `1.40 s` Q9) | 98.1 s (PG1, 8/9) / 4.56 s (DuckPGQ+FK) / 105.0 s (Kùzu) / 156.0 s (Neo4j CE) | **#2 overall behind in-memory DuckPGQ+FK; #1 disk-backed DB** — geomean **9.03×** vs PG1, **4.40×** vs Kùzu (**14.4×** total), **17.4×** vs Neo4j CE (**21.4×** total); **#1 of all 5** on both `Q6` (**5.81×** DuckPGQ) and `Q9` (`1.40 s` vs `1.41 s`) ([full report](property-graphs.md#benchmark-2-ldbc-lsqb-sf01-and-sf1-5-engines)) |
| **Property graphs — social suite** (11 queries, 1.1M edges, 1 core) | **500.9 ms** (`0.45 ms` G10 / `5.83 ms` G11 / `226.6 ms` G9) | 5,661 ms (PG1) / 962 ms (DuckPGQ) / 1,367 ms (Kùzu) | **Fastest total time of all 4** (**1.92×** DuckPGQ, **2.73×** Kùzu, **11.3×** PG1); geomean **7.82×** vs PG1, **3.06×** vs DuckPGQ, **5.86×** vs Kùzu ([full report](property-graphs.md#benchmark-1-social-network-graph-suite-11-queries-11m-edges)) |

PostgreSQL is ahead on single-process multi-thread reads (before adding replicas) and multi-statement read-write blocks.

## TPC-H derived (SF1)

22 queries, SF1, warm, median of 3, at a fixed clock with boost off; every result checked against PostgreSQL's (22/22 exact match):

| | LexDB (one core) | PostgreSQL, one core | PostgreSQL, four processes |
|---|---:|---:|---:|
| all 22 queries, summed (wall) | **5,590 ms** | 14,670 ms | 8,839 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | **0.42** | **0.68** |
| geometric mean of LexDB / PostgreSQL (CPU) | | **0.39** | |
| queries faster than one core | | **22 of 22** | |

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| q1 | 808.6 ms | 3,365.9 ms | 0.24 | 806.2 ms | 3,375.3 ms | 0.24 | 873.5 ms | 0.93 |
| q2 | 33.2 ms | 160.9 ms | 0.21 | 33.1 ms | 166.9 ms | 0.20 | 137.6 ms | 0.24 |
| q3 | 264.2 ms | 551.7 ms | 0.48 | 263.2 ms | 579.3 ms | 0.45 | 353.6 ms | 0.75 |
| q4 | 114.6 ms | 184.9 ms | 0.62 | 114.3 ms | 211.6 ms | 0.54 | 102.9 ms | 1.11 |
| q5 | 124.0 ms | 312.6 ms | 0.40 | 123.5 ms | 341.2 ms | 0.36 | 173.2 ms | 0.72 |
| q6 | 164.4 ms | 274.8 ms | 0.60 | 163.8 ms | 294.1 ms | 0.56 | 203.4 ms | 0.81 |
| q7 | 335.3 ms | 585.8 ms | 0.57 | 334.1 ms | 615.2 ms | 0.54 | 287.6 ms | 1.17 |
| q8 | 146.7 ms | 226.2 ms | 0.65 | 146.3 ms | 253.5 ms | 0.58 | 141.9 ms | 1.03 |
| q9 | 1,110.4 ms | 1,743.2 ms | 0.64 | 1,106.0 ms | 1,770.1 ms | 0.62 | 750.9 ms | 1.48 |
| q10 | 256.4 ms | 389.0 ms | 0.66 | 255.2 ms | 417.2 ms | 0.61 | 167.3 ms | 1.53 |
| q11 | 54.9 ms | 61.4 ms | 0.89 | 54.8 ms | 67.7 ms | 0.81 | 61.5 ms | 0.89 |
| q12 | 401.7 ms | 854.9 ms | 0.47 | 400.2 ms | 880.7 ms | 0.45 | 253.6 ms | 1.58 |
| q13 | 461.7 ms | 839.8 ms | 0.55 | 459.8 ms | 843.9 ms | 0.54 | 825.6 ms | 0.56 |
| q14 | 117.4 ms | 141.6 ms | 0.83 | 116.9 ms | 159.8 ms | 0.73 | 95.1 ms | 1.23 |
| q15 | 151.7 ms | 331.9 ms | 0.46 | 151.6 ms | 348.1 ms | 0.44 | 333.9 ms | 0.45 |
| q16 | 192.3 ms | 267.9 ms | 0.72 | 189.9 ms | 273.4 ms | 0.69 | 105.3 ms | 1.83 |
| q17 | 20.6 ms | 551.2 ms | 0.04 | 20.7 ms | 569.9 ms | 0.04 | 554.7 ms | 0.04 |
| q18 | 211.8 ms | 2,753.9 ms | 0.08 | 211.1 ms | 2,722.6 ms | 0.08 | 2,933.0 ms | 0.07 |
| q19 | 28.8 ms | 40.2 ms | 0.72 | 28.9 ms | 53.6 ms | 0.54 | 37.5 ms | 0.77 |
| q20 | 27.6 ms | 125.8 ms | 0.22 | 27.6 ms | 149.3 ms | 0.18 | 127.8 ms | 0.22 |
| q21 | 518.7 ms | 818.4 ms | 0.63 | 517.0 ms | 846.4 ms | 0.61 | 269.6 ms | 1.92 |
| q22 | 44.5 ms | 88.4 ms | 0.50 | 44.4 ms | 94.1 ms | 0.47 | 49.5 ms | 0.90 |
| **sum** | **5,589.5 ms** | **14,670.4 ms** | **0.38** | **5,568.4 ms** | **15,033.9 ms** | **0.37** | **8,839.0 ms** | **0.63** |
| **geomean** | | | **0.42** | | | **0.39** | | **0.68** |

## ClickBench (1M rows)

`bench/clickbench/run.sh`: official ClickBench `hits` schema (105 columns, wide web-analytics table) and all 43 queries
(`q0`–`q42`) on the first 1,000,000 rows, warm, median of 3, at a fixed clock (`cpu-boost off`), both servers on CPUs 0–3.
All 43 queries pass (31 exact MD5 matches; 12 top-N/unordered queries with matching row counts).

The baseline columns (`LexDB wall`, `PG 1-core`, `PG 4-proc`) run strictly apples-to-apples with no materialized views
and no explicit skipping indexes (automatic zero-config `T_CLEAF` zone maps, adaptive two-level hash aggregation with
bump-arena string keys, direct Top-N group pruning, dictionary-code deduplication, and vectorized string/regex kernels
are always on by default). Fresh load of the 1,000,000-row 105-column `hits` table takes **4.76 s** (`\copy`) vs
PostgreSQL's **6.35 s** (`0.75×`), and `ANALYZE hits` takes **0.36 s** vs PostgreSQL's **1.17 s**.

The final column (`LexDB + MV`, measured at `59797d55` before Waves 1–2 cut MV-free total time to **6,993 ms**) shows the 21 unmodified queries transparently rewritten onto eight
general-purpose incremental `ENABLE QUERY REWRITE` rollup views (`mv_hits_adv` 6 rows / 871 ms build,
`mv_hits_counter` 7 rows / 564 ms, `mv_hits_region_user` 80,309 rows / 646 ms, `mv_hits_mobile` 2,522 rows / 292 ms,
`mv_hits_search` 28,357 rows / 441 ms, `mv_hits_url` 275,494 rows / 1,812 ms, `mv_hits_ip` 68,330 rows / 445 ms,
`mv_hits_minute` 4,346 rows / 943 ms; total build 6.01 s), exercising exact `COUNT(DISTINCT)` rollups (`q4`, `q8`–`q11`,
`q13`), wide (`>512`-byte) hashed group keys (`q12`–`q14`, `q20`, `q33`, `q34`), and functionally dependent exact-grain
`GROUP BY` matching (`q34`, `q35`). All 21 rewritten queries were verified against `query_rewrite_enabled = off` (19
bit-for-bit identical; `q10` and `q11` match exact counts with tie-breaking at count 12). After data load, inserting
1 / 100 new `hits` rows while maintaining all 8 views live (`REFRESH FAST ON STATEMENT`) takes **6.51 / 10.34 ms**.

| | LexDB (one core) | PostgreSQL, one core | PostgreSQL, four processes | LexDB + 8 MVs (`59797d55`, 21 rewritten) |
|---|---:|---:|---:|---:|
| all 43 queries, summed (wall) | **6,993 ms** | 22,081 ms | 11,401 ms | *(see per-query rewritten latencies below)* |
| geometric mean of LexDB / PostgreSQL (wall) | | **0.33** | **0.72** | 0.10 vs PG1 / 0.21 vs PG4 |
| geometric mean of LexDB / PostgreSQL (CPU) | | **0.33** | | |
| queries level or ahead of one core (within 10%) | | **43 of 43** | | 42 of 43 (21 rewritten) |

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 | LexDB + MV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q0 | 17.0 ms | 90.0 ms | 0.19 | 27.4 ms | 116.2 ms | 0.24 | 36.4 ms | 0.47 | **0.58 ms** |
| q1 | 155.0 ms | 338.9 ms | 0.46 | 164.2 ms | 359.5 ms | 0.46 | 100.7 ms | 1.54 | **0.63 ms** |
| q2 | 99.1 ms | 380.5 ms | 0.26 | 109.4 ms | 404.3 ms | 0.27 | 104.4 ms | 0.95 | **0.69 ms** |
| q3 | 83.7 ms | 258.3 ms | 0.32 | 93.5 ms | 282.8 ms | 0.33 | 76.4 ms | 1.10 | **0.64 ms** |
| q4 | 97.5 ms | 307.7 ms | 0.32 | 108.4 ms | 331.3 ms | 0.33 | 296.6 ms | 0.33 | **5.99 ms** |
| q5 | 181.5 ms | 428.0 ms | 0.42 | 191.6 ms | 452.2 ms | 0.42 | 410.2 ms | 0.44 | — |
| q6 | 152.8 ms | 257.9 ms | 0.59 | 161.5 ms | 283.0 ms | 0.57 | 78.3 ms | 1.95 | **0.54 ms** |
| q7 | 130.7 ms | 329.4 ms | 0.40 | 140.3 ms | 353.5 ms | 0.40 | 101.7 ms | 1.29 | **0.47 ms** |
| q8 | 109.9 ms | 488.3 ms | 0.23 | 119.3 ms | 513.2 ms | 0.23 | 465.5 ms | 0.24 | **5.06 ms** |
| q9 | 149.6 ms | 617.2 ms | 0.24 | 159.1 ms | 640.4 ms | 0.25 | 590.8 ms | 0.25 | **12.69 ms** |
| q10 | 108.9 ms | 343.0 ms | 0.32 | 119.4 ms | 367.5 ms | 0.32 | 103.5 ms | 1.05 | **0.83 ms** |
| q11 | 110.9 ms | 347.4 ms | 0.32 | 121.3 ms | 372.2 ms | 0.33 | 108.6 ms | 1.02 | **0.90 ms** |
| q12 | 117.8 ms | 368.6 ms | 0.32 | 127.3 ms | 393.8 ms | 0.32 | 114.6 ms | 1.03 | **41.38 ms** |
| q13 | 154.6 ms | 386.1 ms | 0.40 | 165.2 ms | 410.5 ms | 0.40 | 146.7 ms | 1.05 | **32.80 ms** |
| q14 | 121.8 ms | 368.4 ms | 0.33 | 131.3 ms | 393.3 ms | 0.33 | 351.2 ms | 0.35 | **48.82 ms** |
| q15 | 102.8 ms | 333.1 ms | 0.31 | 112.3 ms | 356.5 ms | 0.31 | 134.8 ms | 0.76 | **144.53 ms** |
| q16 | 277.6 ms | 471.3 ms | 0.59 | 286.4 ms | 495.9 ms | 0.58 | 453.9 ms | 0.61 | — |
| q17 | 150.3 ms | 452.5 ms | 0.33 | 160.2 ms | 475.9 ms | 0.34 | 165.9 ms | 0.91 | — |
| q18 | 320.7 ms | 670.4 ms | 0.48 | 328.8 ms | 694.3 ms | 0.47 | 639.2 ms | 0.50 | — |
| q19 | 86.0 ms | 243.3 ms | 0.35 | 97.4 ms | 269.3 ms | 0.36 | 74.8 ms | 1.15 | — |
| q20 | 148.2 ms | 374.4 ms | 0.40 | 147.6 ms | 398.1 ms | 0.37 | 110.6 ms | 1.34 | **54.86 ms** |
| q21 | 126.8 ms | 437.8 ms | 0.29 | 126.4 ms | 461.9 ms | 0.27 | 131.0 ms | 0.97 | — |
| q22 | 131.3 ms | 491.1 ms | 0.27 | 130.8 ms | 515.0 ms | 0.25 | 147.3 ms | 0.89 | — |
| q23 | 178.4 ms | 360.6 ms | 0.49 | 177.2 ms | 384.8 ms | 0.46 | 107.3 ms | 1.66 | — |
| q24 | 94.5 ms | 333.5 ms | 0.28 | 94.3 ms | 357.6 ms | 0.26 | 105.6 ms | 0.89 | — |
| q25 | 89.1 ms | 332.8 ms | 0.27 | 88.9 ms | 357.7 ms | 0.25 | 102.6 ms | 0.87 | — |
| q26 | 98.4 ms | 333.8 ms | 0.29 | 98.0 ms | 358.9 ms | 0.27 | 103.5 ms | 0.95 | — |
| q27 | 232.3 ms | 481.9 ms | 0.48 | 231.4 ms | 506.1 ms | 0.46 | 166.3 ms | 1.40 | **0.50 ms** |
| q28 | 257.9 ms | 3,999.7 ms | 0.06 | 256.9 ms | 4,017.1 ms | 0.06 | 1,078.7 ms | 0.24 | — |
| q29 | 67.5 ms | 852.3 ms | 0.08 | 67.2 ms | 876.0 ms | 0.08 | 342.1 ms | 0.20 | — |
| q30 | 103.3 ms | 355.4 ms | 0.29 | 102.6 ms | 380.4 ms | 0.27 | 356.6 ms | 0.29 | — |
| q31 | 109.1 ms | 378.4 ms | 0.29 | 108.5 ms | 402.2 ms | 0.27 | 382.0 ms | 0.29 | — |
| q32 | 303.7 ms | 906.3 ms | 0.34 | 302.2 ms | 928.8 ms | 0.33 | 924.6 ms | 0.33 | — |
| q33 | 299.6 ms | 467.2 ms | 0.64 | 298.1 ms | 496.4 ms | 0.60 | 467.7 ms | 0.64 | **38.26 ms** |
| q34 | 301.5 ms | 475.3 ms | 0.63 | 299.5 ms | 499.2 ms | 0.60 | 470.1 ms | 0.64 | **38.16 ms** |
| q35 | 182.2 ms | 395.2 ms | 0.46 | 181.5 ms | 420.1 ms | 0.43 | 158.6 ms | 1.15 | **4.00 ms** |
| q36 | 268.1 ms | 538.9 ms | 0.50 | 266.6 ms | 562.6 ms | 0.47 | 255.0 ms | 1.05 | — |
| q37 | 175.1 ms | 483.1 ms | 0.36 | 174.4 ms | 507.1 ms | 0.34 | 173.0 ms | 1.01 | — |
| q38 | 133.4 ms | 399.4 ms | 0.33 | 132.8 ms | 423.9 ms | 0.31 | 156.8 ms | 0.85 | — |
| q39 | 496.2 ms | 522.7 ms | 0.95 | 492.9 ms | 546.8 ms | 0.90 | 529.9 ms | 0.94 | — |
| q40 | 162.3 ms | 619.9 ms | 0.26 | 161.6 ms | 642.9 ms | 0.25 | 208.1 ms | 0.78 | — |
| q41 | 159.6 ms | 583.6 ms | 0.27 | 158.6 ms | 608.1 ms | 0.26 | 200.3 ms | 0.80 | — |
| q42 | 146.3 ms | 477.0 ms | 0.31 | 145.3 ms | 501.1 ms | 0.29 | 168.8 ms | 0.87 | **2.32 ms** |
| **sum** | **6,993.0 ms** | **22,080.6 ms** | **0.32** | **7,167.3 ms** | **23,118.4 ms** | **0.31** | **11,400.7 ms** | **0.61** | — |
| **geomean** | | | **0.33** | | | **0.33** | | **0.72** | **0.10 / 0.21** |

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
| `oltp_point_select` | 1 | 76,201 | 65,124 | 1.17 | 0.01 | 0.02 | 13.1 | 10.1 | 1.30 | 0 | 0 |
| `oltp_point_select` | 8 | 146,010 | 369,540 | 0.40 | 0.06 | 0.03 | 6.8 | 10.7 | 0.64 | 0 | 0 |
| `oltp_point_select` | 32 | 145,376 | 334,053 | 0.44 | 0.23 | 0.15 | 6.9 | 11.9 | 0.57 | 0 | 0 |
| `oltp_read_only` | 1 | 2,868 | 2,418 | 1.19 | 0.39 | 0.43 | 345.9 | 326.2 | 1.06 | 0 | 0 |
| `oltp_read_only` | 8 | 4,001 | 11,547 | 0.35 | 2.35 | 0.80 | 248.8 | 341.0 | 0.73 | 0 | 0 |
| `oltp_read_only` | 32 | 3,901 | 10,241 | 0.38 | 8.74 | 4.18 | 255.3 | 389.9 | 0.65 | 0 | 0 |
| `oltp_read_write` (`SERIALIZABLE`) | 1 | 1,166 | 829 | 1.41 | 0.94 | 1.32 | 653.4 | 565.8 | 1.15 | 0 | 0 |
| `oltp_read_write` (`SERIALIZABLE`) | 8 | 1,409 | 4,082 | 0.35 | 11.24 | 2.22 | 709.0 | 607.1 | 1.17 | 6,588 | 14 |
| `oltp_read_write` (`SERIALIZABLE`) | 32 | 867 | 5,553 | 0.16 | 95.81 | 8.28 | 1,150.5 | 690.3 | 1.67 | 13,545 | 66 |
| `oltp_read_write` (`READ COMMITTED`) | 1 | 1,127 | 829 | 1.36 | 1.14 | 1.32 | 675.9 | 565.8 | 1.19 | 0 | 0 |
| `oltp_read_write` (`READ COMMITTED`) | 8 | 1,682 | 4,082 | 0.41 | 5.47 | 2.22 | 593.8 | 607.1 | 0.98 | 0 | 14 |
| `oltp_read_write` (`READ COMMITTED`) | 32 | 1,806 | 5,553 | 0.33 | 20.37 | 8.28 | 552.4 | 690.3 | 0.80 | 0 | 66 |
| `oltp_write_only` | 1 | 2,648 | 1,326 | 2.00 | 0.44 | 0.80 | 199.1 | 200.4 | 0.99 | 0 | 0 |
| `oltp_write_only` | 8 | 9,105 | 5,964 | 1.53 | 1.34 | 1.39 | 110.5 | 152.4 | 0.73 | 0 | 28 |
| `oltp_write_only` | 32 | 9,868 | 18,505 | 0.53 | 5.99 | 2.35 | 102.3 | 137.4 | 0.74 | 0 | 318 |
| `oltp_update_index` | 1 | 3,509 | 1,501 | 2.34 | 0.38 | 0.70 | 102.7 | 138.5 | 0.74 | 0 | 0 |
| `oltp_update_index` | 8 | 16,741 | 5,882 | 2.85 | 0.62 | 1.96 | 44.7 | 82.8 | 0.54 | 0 | 0 |
| `oltp_update_index` | 32 | 34,205 | 20,992 | 1.63 | 1.23 | 2.22 | 29.4 | 55.0 | 0.53 | 0 | 0 |
| `oltp_update_non_index` | 1 | 3,923 | 1,381 | 2.84 | 0.29 | 0.80 | 67.8 | 139.2 | 0.49 | 0 | 0 |
| `oltp_update_non_index` | 8 | 18,391 | 5,898 | 3.12 | 0.46 | 1.96 | 27.7 | 70.5 | 0.39 | 0 | 0 |
| `oltp_update_non_index` | 32 | 58,352 | 23,015 | 2.54 | 0.67 | 1.55 | 17.2 | 48.6 | 0.35 | 0 | 0 |

LexDB (3 read replicas, 4 processes) vs PostgreSQL 18 (4 cores) — read workloads:

| workload | threads | LexDB 3-rep TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 71,953 | 65,124 | 1.10 | 0.02 | 0.02 | 13.7 | 10.1 | 1.35 |
| `oltp_point_select` | 8 | 389,338 | 369,540 | 1.05 | 0.03 | 0.03 | 7.7 | 10.7 | 0.71 |
| `oltp_point_select` | 32 | 427,129 | 334,053 | 1.28 | 0.09 | 0.15 | 7.0 | 11.9 | 0.58 |
| `oltp_read_only` | 1 | 2,910 | 2,418 | 1.20 | 0.36 | 0.43 | 341.2 | 326.2 | 1.05 |
| `oltp_read_only` | 8 | 10,505 | 11,547 | 0.91 | 1.27 | 0.80 | 283.4 | 341.0 | 0.83 |
| `oltp_read_only` | 32 | 11,515 | 10,241 | 1.12 | 3.82 | 4.18 | 259.4 | 389.9 | 0.67 |

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
| Sum of all 11 queries | **500.9 ms** | 5,660.5 ms | 962.2 ms | 1,367.4 ms |
| Geometric mean (LexDB / peer) | — | **0.13× (7.82× faster)** | **0.33× (3.06× faster)** | **0.17× (5.86× faster)** |
| 5-hop shortest path (`G10`) | **0.45 ms** (`0.71 ms` cold) | 1,080.53 ms | 61.89 ms | 40.59 ms |
| Single-source shortest paths (`G11`, 2k targets) | **5.83 ms** (`24.86 ms` cold) | 1,263.90 ms | 64.31 ms | 48.26 ms |
| Full-graph 1M-edge triangles (`G9`) | **226.55 ms** | 1,813.83 ms | 518.85 ms | 521.31 ms |

## Not measured in this run

- **SQL Server** against LexDB: its container was not running for this run.
- **Oracle** comparison: dropped for now, to be added back later.
