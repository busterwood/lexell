# LexDB performance

Measured on 24–26 November 2026 on `main` (`59797d55`). Every number compares LexDB directly against **PostgreSQL 18.6** on the same machine, data, disk, and transport.

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
| **TPC-H SF1** (22 queries, 1 core) | 7,197 ms | 14,670 ms (1 core) / 8,839 ms (4 proc) | **2.0× faster** than 1 core (22/22 faster, geomean `0.49` wall / `0.45` CPU); **1.23× faster** than 4 proc (`0.79` geomean) |
| **ClickBench 1M** (43 queries, 105 cols, 1 core) | 14,104 ms | 22,363 ms (1 core) / 11,326 ms (4 proc) | **1.59× faster** than 1 core (40/43 level or ahead; geomean `0.68` wall / `0.64` CPU) |
| **ClickBench 1M + 8 MVs** (unmodified queries, 1 core) | **9,068 ms** | 11,326 ms (4 proc) | **1.25× faster than 4-core PG on one core** (21 rewritten; geomean `0.10` vs PG1 / `0.21` vs PG4) |
| **ClickBench 1M + 3 skipping indexes** | 42.6–485.4 ms | — | **1.28–4.07× faster** on selective point & `LIKE '%substring%'` filters; zero OLTP write/read regression |
| **35 Analytic Queries** (1M rows, 1 core) | `0.46×` CPU / `0.91×` wall | 1 core / 4 proc | **2.2× less CPU** than 1 core; ahead of 4 proc on wall (`0.31 / 0.49` geomean with 4 MVs) |
| **Materialized view maintenance** (1M rows, 1 row) | **0.43–0.66 ms** (`FAST`) | 60–369 ms (`REFRESH`) | **90–780× faster** incremental updates; sketch MV build **220 vs 379 ms**; hot-key `realtime` **22,102 commits/s** |
| **Durable OLTP updates** (1–32 clients) | up to **63.3k/s** (`pgbench`) / **54.2k/s** (`sysbench`) | 25.7k/s / 23.0k/s | **2.41–2.67×** (`pgbench`); **2.36–3.13×** (`sysbench` non-index); **1.32–2.54×** (`sysbench` indexed) |
| **Point selects (3 read replicas, 32 clients)** | **470–490k/s** (`pgbench`) / **350.5k/s** (`sysbench`) | 397k/s / 334k/s (4 cores) | **1.18–1.23×** (`pgbench`); **1.05×** (`sysbench`, 29% less CPU); replica lag **0.22 ms** p50 / **0.44 ms** p99 |
| **Bulk `\copy` loads** (5 cases, 1M–10M rows) | 0.24–2.44 s | 0.61–5.93 s | **1.1–2.7× faster** (`0.37–0.94×`) on all 5 workloads |
| **Property graphs (SQL/PGQ)** (11 queries, 1.1M edges, 1 core) | **860 ms** (`0.38 ms` G10 / `6.41 ms` G11 / `396 ms` G9) | 5,661 ms (PG1) / 962 ms (DuckPGQ) / 1,367 ms (Kùzu) | **Fastest total time of all 4**; geomean **6.04× faster** than PG1, **2.37× faster** than DuckPGQ, **4.54× faster** than Kùzu ([full report](property-graphs.md)) |

PostgreSQL is ahead on single-process multi-thread reads (before adding replicas) and multi-statement read-write blocks.

## TPC-H derived (SF1)

22 queries, SF1, warm, median of 3, at a fixed clock with boost off; every result checked against PostgreSQL's (22/22 exact match):

| | LexDB (one core) | PostgreSQL, one core | PostgreSQL, four processes |
|---|---:|---:|---:|
| all 22 queries, summed (wall) | 7,197 ms | 14,670 ms | 8,839 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | 0.49 | 0.79 |
| geometric mean of LexDB / PostgreSQL (CPU) | | 0.45 | |
| queries faster than one core | | 22 of 22 | |

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| q1 | 1,150.9 ms | 3,365.9 ms | 0.34 | 1,146.1 ms | 3,375.3 ms | 0.34 | 873.5 ms | 1.32 |
| q2 | 35.8 ms | 160.9 ms | 0.22 | 35.7 ms | 166.9 ms | 0.21 | 137.6 ms | 0.26 |
| q3 | 472.9 ms | 551.7 ms | 0.86 | 470.5 ms | 579.3 ms | 0.81 | 353.6 ms | 1.34 |
| q4 | 117.6 ms | 184.9 ms | 0.64 | 117.0 ms | 211.6 ms | 0.55 | 102.9 ms | 1.14 |
| q5 | 156.6 ms | 312.6 ms | 0.50 | 155.9 ms | 341.2 ms | 0.46 | 173.2 ms | 0.90 |
| q6 | 186.7 ms | 274.8 ms | 0.68 | 186.0 ms | 294.1 ms | 0.63 | 203.4 ms | 0.92 |
| q7 | 385.9 ms | 585.8 ms | 0.66 | 383.7 ms | 615.2 ms | 0.62 | 287.6 ms | 1.34 |
| q8 | 152.9 ms | 226.2 ms | 0.68 | 152.1 ms | 253.5 ms | 0.60 | 141.9 ms | 1.08 |
| q9 | 1,430.0 ms | 1,743.2 ms | 0.82 | 1,422.9 ms | 1,770.1 ms | 0.80 | 750.9 ms | 1.90 |
| q10 | 266.4 ms | 389.0 ms | 0.68 | 265.0 ms | 417.2 ms | 0.64 | 167.3 ms | 1.59 |
| q11 | 50.0 ms | 61.4 ms | 0.81 | 49.7 ms | 67.7 ms | 0.73 | 61.5 ms | 0.81 |
| q12 | 424.5 ms | 854.9 ms | 0.50 | 422.7 ms | 880.7 ms | 0.48 | 253.6 ms | 1.67 |
| q13 | 615.9 ms | 839.8 ms | 0.73 | 613.0 ms | 843.9 ms | 0.73 | 825.6 ms | 0.75 |
| q14 | 131.4 ms | 141.6 ms | 0.93 | 130.8 ms | 159.8 ms | 0.82 | 95.1 ms | 1.38 |
| q15 | 154.3 ms | 331.9 ms | 0.46 | 154.1 ms | 348.1 ms | 0.44 | 333.9 ms | 0.46 |
| q16 | 201.4 ms | 267.9 ms | 0.75 | 198.8 ms | 273.4 ms | 0.73 | 105.3 ms | 1.91 |
| q17 | 20.4 ms | 551.2 ms | 0.04 | 20.4 ms | 569.9 ms | 0.04 | 554.7 ms | 0.04 |
| q18 | 529.8 ms | 2,753.9 ms | 0.19 | 527.6 ms | 2,722.6 ms | 0.19 | 2,933.0 ms | 0.18 |
| q19 | 28.9 ms | 40.2 ms | 0.72 | 28.9 ms | 53.6 ms | 0.54 | 37.5 ms | 0.77 |
| q20 | 26.9 ms | 125.8 ms | 0.21 | 26.8 ms | 149.3 ms | 0.18 | 127.8 ms | 0.21 |
| q21 | 610.6 ms | 818.4 ms | 0.75 | 608.1 ms | 846.4 ms | 0.72 | 269.6 ms | 2.26 |
| q22 | 47.2 ms | 88.4 ms | 0.53 | 47.0 ms | 94.1 ms | 0.50 | 49.5 ms | 0.95 |
| **sum** | **7,197.0 ms** | **14,670.4 ms** | **0.49** | **7,162.9 ms** | **15,033.8 ms** | **0.48** | **8,839.0 ms** | **0.81** |
| **geomean** | | | **0.49** | | | **0.45** | | **0.79** |

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
| all 43 queries, summed (wall) | 14,104 ms | 22,363 ms | 11,326 ms | 9,068 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | 0.68 | 1.50 | 0.10 vs PG1 / 0.21 vs PG4 |
| geometric mean of LexDB / PostgreSQL (CPU) | | 0.64 | | |
| queries level or ahead of one core (within 10%) | | 40 of 43 | | 40 of 43 (21 rewritten; 29 of 43 vs PG4) |

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 | LexDB + MV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q0 | 50.5 ms | 87.5 ms | 0.58 | 50.5 ms | 109.9 ms | 0.46 | 34.7 ms | 1.46 | **0.58 ms** |
| q1 | 216.2 ms | 342.0 ms | 0.63 | 215.0 ms | 361.5 ms | 0.59 | 106.3 ms | 2.03 | **0.63 ms** |
| q2 | 206.5 ms | 392.2 ms | 0.53 | 205.4 ms | 411.9 ms | 0.50 | 107.7 ms | 1.92 | **0.69 ms** |
| q3 | 274.7 ms | 256.2 ms | 1.07 | 273.5 ms | 276.6 ms | 0.99 | 80.0 ms | 3.43 | **0.64 ms** |
| q4 | 169.4 ms | 304.0 ms | 0.56 | 168.4 ms | 323.7 ms | 0.52 | 302.4 ms | 0.56 | **5.99 ms** |
| q5 | 278.7 ms | 429.8 ms | 0.65 | 276.0 ms | 450.0 ms | 0.61 | 419.5 ms | 0.66 | — |
| q6 | 196.9 ms | 252.1 ms | 0.78 | 196.0 ms | 273.4 ms | 0.72 | 79.3 ms | 2.48 | **0.54 ms** |
| q7 | 216.2 ms | 337.2 ms | 0.64 | 215.1 ms | 357.9 ms | 0.60 | 107.1 ms | 2.02 | **0.47 ms** |
| q8 | 185.1 ms | 489.4 ms | 0.38 | 184.1 ms | 509.3 ms | 0.36 | 479.0 ms | 0.39 | **5.06 ms** |
| q9 | 266.1 ms | 624.1 ms | 0.43 | 264.6 ms | 643.1 ms | 0.41 | 604.6 ms | 0.44 | **12.69 ms** |
| q10 | 222.4 ms | 347.7 ms | 0.64 | 221.3 ms | 368.2 ms | 0.60 | 101.3 ms | 2.20 | **0.83 ms** |
| q11 | 226.3 ms | 352.4 ms | 0.64 | 224.9 ms | 371.1 ms | 0.61 | 103.8 ms | 2.18 | **0.90 ms** |
| q12 | 242.9 ms | 365.6 ms | 0.66 | 241.6 ms | 385.4 ms | 0.63 | 113.6 ms | 2.14 | **41.38 ms** |
| q13 | 282.8 ms | 381.5 ms | 0.74 | 281.2 ms | 402.8 ms | 0.70 | 143.7 ms | 1.97 | **32.80 ms** |
| q14 | 261.6 ms | 363.1 ms | 0.72 | 260.0 ms | 383.8 ms | 0.68 | 346.7 ms | 0.75 | **48.82 ms** |
| q15 | 187.1 ms | 336.5 ms | 0.56 | 186.0 ms | 359.0 ms | 0.52 | 132.2 ms | 1.42 | **144.53 ms** |
| q16 | 328.9 ms | 468.6 ms | 0.70 | 327.2 ms | 488.9 ms | 0.67 | 442.8 ms | 0.74 | — |
| q17 | 425.7 ms | 444.5 ms | 0.96 | 423.7 ms | 464.2 ms | 0.91 | 162.0 ms | 2.63 | — |
| q18 | 450.3 ms | 674.1 ms | 0.67 | 448.1 ms | 692.9 ms | 0.65 | 635.6 ms | 0.71 | — |
| q19 | 171.8 ms | 238.6 ms | 0.72 | 170.9 ms | 259.3 ms | 0.66 | 73.6 ms | 2.33 | — |
| q20 | 309.7 ms | 375.3 ms | 0.83 | 308.4 ms | 397.4 ms | 0.78 | 106.5 ms | 2.91 | **54.86 ms** |
| q21 | 314.3 ms | 456.5 ms | 0.69 | 312.9 ms | 476.3 ms | 0.66 | 134.2 ms | 2.34 | — |
| q22 | 623.0 ms | 512.7 ms | 1.22 | 619.8 ms | 533.1 ms | 1.16 | 137.7 ms | 4.52 | — |
| q23 | 344.4 ms | 370.6 ms | 0.93 | 342.7 ms | 390.8 ms | 0.88 | 104.2 ms | 3.31 | — |
| q24 | 243.3 ms | 349.7 ms | 0.70 | 242.2 ms | 370.1 ms | 0.65 | 100.6 ms | 2.42 | — |
| q25 | 235.8 ms | 347.4 ms | 0.68 | 234.7 ms | 367.8 ms | 0.64 | 100.5 ms | 2.35 | — |
| q26 | 248.0 ms | 351.7 ms | 0.71 | 246.9 ms | 371.6 ms | 0.66 | 100.9 ms | 2.46 | — |
| q27 | 395.6 ms | 501.9 ms | 0.79 | 393.8 ms | 523.8 ms | 0.75 | 169.1 ms | 2.34 | **0.50 ms** |
| q28 | 1,015.2 ms | 4,030.8 ms | 0.25 | 1,010.9 ms | 4,039.0 ms | 0.25 | 1,057.0 ms | 0.96 | — |
| q29 | 180.2 ms | 852.2 ms | 0.21 | 179.2 ms | 871.6 ms | 0.21 | 336.3 ms | 0.54 | — |
| q30 | 262.0 ms | 362.4 ms | 0.72 | 260.7 ms | 382.1 ms | 0.68 | 353.7 ms | 0.74 | — |
| q31 | 262.9 ms | 385.5 ms | 0.68 | 261.4 ms | 406.5 ms | 0.64 | 375.7 ms | 0.70 | — |
| q32 | 399.6 ms | 917.0 ms | 0.44 | 397.4 ms | 935.4 ms | 0.42 | 905.7 ms | 0.44 | — |
| q33 | 425.7 ms | 479.2 ms | 0.89 | 423.4 ms | 498.1 ms | 0.85 | 461.8 ms | 0.92 | **38.26 ms** |
| q34 | 443.4 ms | 487.0 ms | 0.91 | 440.5 ms | 506.5 ms | 0.87 | 466.9 ms | 0.95 | **38.16 ms** |
| q35 | 264.3 ms | 396.7 ms | 0.67 | 262.9 ms | 416.7 ms | 0.63 | 156.4 ms | 1.69 | **4.00 ms** |
| q36 | 478.9 ms | 548.0 ms | 0.87 | 476.6 ms | 566.9 ms | 0.84 | 246.7 ms | 1.94 | — |
| q37 | 625.8 ms | 494.2 ms | 1.27 | 622.9 ms | 514.5 ms | 1.21 | 169.9 ms | 3.68 | — |
| q38 | 291.3 ms | 404.5 ms | 0.72 | 289.6 ms | 425.5 ms | 0.68 | 145.8 ms | 2.00 | — |
| q39 | 658.9 ms | 536.6 ms | 1.23 | 655.3 ms | 556.1 ms | 1.18 | 532.5 ms | 1.24 | — |
| q40 | 397.0 ms | 621.5 ms | 0.64 | 395.2 ms | 641.0 ms | 0.62 | 220.6 ms | 1.80 | — |
| q41 | 396.9 ms | 599.1 ms | 0.66 | 395.1 ms | 618.9 ms | 0.64 | 198.9 ms | 2.00 | — |
| q42 | 427.7 ms | 495.3 ms | 0.86 | 425.6 ms | 515.4 ms | 0.83 | 168.0 ms | 2.55 | **2.32 ms** |
| **sum** | **14,104.0 ms** | **22,362.9 ms** | **0.63** | **14,031.6 ms** | **23,217.8 ms** | **0.60** | **11,325.5 ms** | **1.25** | **9,067.5 ms** |
| **geomean** | | | **0.68** | | | **0.64** | | **1.50** | **0.10 / 0.21** |

### Optional data skipping indexes on ClickBench 1M

Adding three optional hierarchical [data skipping indexes](skipping-indexes.md) on `hits` (`USING bloom_filter` on `UserID`, `USING ngrambf(3, 2048, 3)` on `URL` and `Title`) further accelerates selective point and substring-`LIKE` filters with exact output parity and zero OLTP write/read regression (1,000 inserts `303.9` vs `304.6 ms`; 1,000 PK selects `44.4` vs `45.1 ms`):

| Query | Filter pattern | Skipping index used | Baseline | With skipping index | Speedup |
|---|---|---|---:|---:|---:|
| `q19` | `WHERE UserID = 435090932899640449` | `bloom_filter(UserID)` | 173.2 ms | **42.6 ms** | **4.07×** |
| `q21` | `WHERE URL LIKE '%google%'` | `ngrambf(URL)` | 339.9 ms | **167.7 ms** | **2.03×** |
| `q23` | `WHERE Title LIKE '%Google%'` | `ngrambf(Title)` | 331.7 ms | **168.7 ms** | **1.97×** |
| `q22` | `WHERE Title LIKE '%Google%' AND URL NOT LIKE '%.google.%'` | `ngrambf(Title)` | 620.1 ms | **485.4 ms** | **1.28×** |

## Analytic queries (35 queries, 1M rows)

35 queries over 1M-row tables (scans, joins, groups, windows; median of 5).
The baseline columns (`LexDB`, `PG 1-core`, `PG 4-proc`) run strictly apples-to-apples with no materialized views:
LexDB's CPU is 0.46 of PostgreSQL's on one core (geometric mean; wall 0.56), and its wall time
0.91 of PostgreSQL's on four processes; 32 of 35 are level with or ahead of PostgreSQL on one core
on CPU (34 of 35 on wall time), including `sort_lim` dropping 19 → 6 ms (3.2× faster via dynamic Top-N pruning)
and `grp_text` dropping 53 → 40 ms (0.93× of 4-core PostgreSQL on one core).

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
| `scan2` | 112 ms | 141 ms | 0.79 | 55 ms | 80 ms | 0.69 | 141 ms | 0.79 | 115 ms |
| `scan3` | 160 ms | 213 ms | 0.75 | 74 ms | 120 ms | 0.62 | 215 ms | 0.74 | 167 ms |
| `scan9` | 520 ms | 532 ms | 0.98 | 255 ms | 250 ms | 1.02 | 532 ms | 0.98 | 532 ms |
| `filt1pct` | 20 ms | 41 ms | 0.49 | 15 ms | 40 ms | 0.38 | 22 ms | 0.91 | 21 ms |
| `filt10pct` | 38 ms | 59 ms | 0.64 | 25 ms | 50 ms | 0.50 | 59 ms | 0.64 | 37 ms |
| `filt_like` | 58 ms | 81 ms | 0.72 | 53 ms | 80 ms | 0.66 | 32 ms | 1.81 | 57 ms |
| `filt_agg` | 22 ms | 45 ms | 0.49 | 18 ms | 40 ms | 0.45 | 22 ms | 1.00 | 23 ms |
| `expr_int` | 150 ms | 217 ms | 0.69 | 70 ms | 140 ms | 0.50 | 215 ms | 0.70 | 160 ms |
| `expr_mix` | 357 ms | 422 ms | 0.85 | 243 ms | 300 ms | 0.81 | 418 ms | 0.85 | 381 ms |
| `expr_agg` | 32 ms | 58 ms | 0.55 | 27 ms | 60 ms | 0.45 | 25 ms | 1.28 | **3 ms** |
| `sort_all` | 116 ms | 447 ms | 0.26 | 61 ms | 390 ms | 0.16 | 443 ms | 0.26 | 120 ms |
| `sort_lim` | 6 ms | 91 ms | 0.07 | 3 ms | 90 ms | 0.03 | 33 ms | 0.18 | 6 ms |
| `count` | 8 ms | 36 ms | 0.22 | 4 ms | 30 ms | 0.13 | 18 ms | 0.44 | **3 ms** |
| `grp_int` | 24 ms | 95 ms | 0.25 | 20 ms | 100 ms | 0.20 | 35 ms | 0.69 | **3 ms** |
| `grp_text` | 40 ms | 127 ms | 0.31 | 36 ms | 130 ms | 0.28 | 43 ms | 0.93 | **4 ms** |
| `minmax_text` | 54 ms | 132 ms | 0.41 | 50 ms | 130 ms | 0.38 | 43 ms | 1.26 | **3 ms** |
| `distinct` | 63 ms | 95 ms | 0.66 | 58 ms | 100 ms | 0.58 | 34 ms | 1.85 | 77 ms |
| `distinct2` | 140 ms | 110 ms | 1.27 | 135 ms | 110 ms | 1.23 | 40 ms | 3.50 | 173 ms |
| `idx_range1k` | 5 ms | 10 ms | 0.50 | 1 ms | 10 ms | 0.10 | 10 ms | 0.50 | 5 ms |
| `idx_range100k` | 47 ms | 46 ms | 1.02 | 35 ms | 30 ms | 1.17 | 46 ms | 1.02 | 50 ms |
| `idx_range_agg` | 30 ms | 30 ms | 1.00 | 26 ms | 30 ms | 0.87 | 24 ms | 1.25 | 32 ms |
| `pk_range100k` | 21 ms | 32 ms | 0.66 | 9 ms | 20 ms | 0.45 | 32 ms | 0.66 | 22 ms |
| `pk_point20k` | 615 ms | 629 ms | 0.98 | 570 ms | 430 ms | 1.33 | 642 ms | 0.96 | 680 ms |
| `join_hash_agg` | 38 ms | 95 ms | 0.40 | 34 ms | 100 ms | 0.34 | 35 ms | 1.09 | **3 ms** |
| `join_hash_rows` | 35 ms | 63 ms | 0.56 | 26 ms | 60 ms | 0.43 | 63 ms | 0.56 | 36 ms |
| `join_lookup_agg` | 74 ms | 80 ms | 0.93 | 70 ms | 80 ms | 0.88 | 33 ms | 2.24 | **3 ms** |
| `sub_in` | 26 ms | 50 ms | 0.52 | 22 ms | 50 ms | 0.44 | 24 ms | 1.08 | 26 ms |
| `sub_exists` | 25 ms | 50 ms | 0.50 | 21 ms | 50 ms | 0.42 | 25 ms | 1.00 | 26 ms |
| `sub_corr_sel` | 113 ms | 150 ms | 0.75 | 100 ms | 150 ms | 0.67 | 150 ms | 0.75 | 122 ms |
| `window` | 109 ms | 144 ms | 0.76 | 93 ms | 130 ms | 0.72 | 91 ms | 1.20 | 120 ms |
| `join_hash_sort` | 58 ms | 111 ms | 0.52 | 45 ms | 100 ms | 0.45 | 55 ms | 1.05 | 61 ms |
| `join_text_agg` | 57 ms | 85 ms | 0.67 | 53 ms | 80 ms | 0.66 | 32 ms | 1.78 | **3 ms** |
| `join_text_rows` | 72 ms | 86 ms | 0.84 | 60 ms | 80 ms | 0.75 | 87 ms | 0.83 | 73 ms |
| `join_text_group` | 91 ms | 169 ms | 0.54 | 87 ms | 170 ms | 0.51 | 54 ms | 1.69 | **3 ms** |
| `join_left_rows` | 32 ms | 56 ms | 0.57 | 17 ms | 40 ms | 0.42 | 59 ms | 0.54 | 33 ms |
| **geomean** | | | **0.56** | | | **0.46** | | **0.91** | **0.31 / 0.49** |

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
| Sum of all 11 queries | **859.6 ms** | 5,660.5 ms | 962.2 ms | 1,367.4 ms |
| Geometric mean (LexDB / peer) | — | **0.17× (6.04× faster)** | **0.42× (2.37× faster)** | **0.22× (4.54× faster)** |
| 5-hop shortest path (`G10`) | **0.38 ms** (`0.70 ms` cold) | 1,080.53 ms | 61.89 ms | 40.59 ms |
| Single-source shortest paths (`G11`, 2k targets) | **6.41 ms** (`24.76 ms` cold) | 1,263.90 ms | 64.31 ms | 48.26 ms |
| Full-graph 1M-edge triangles (`G9`) | **396.28 ms** | 1,813.83 ms | 518.85 ms | 521.31 ms |

## Not measured in this run

- **SQL Server** against LexDB: its container was not running for this run.
- **Oracle** comparison: dropped for now, to be added back later.
