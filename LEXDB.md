# LexDB

LexDB is a fast, full-featured SQL database server written in [Lexell](README.md). It ships as a single native executable built for modern NVMe/SSD storage, and handles both **OLTP transactions** and **columnar analytics** in one engine — with no locks, no page latches, and no separate analytics cluster to maintain.

One server speaks **three native wire protocols and SQL dialects simultaneously** over the same tables and catalog:

- **PostgreSQL** (`pgwire`, PostgreSQL SQL)
- **SQL Server** (`TDS`, T-SQL, batches, collations, `TOP`, `@variables`)
- **Oracle** (`TNS`, Oracle SQL & PL/SQL, `NUMBER`, `VARCHAR2`, `DUAL`, packages)

Existing drivers and tools — `psql`, `pgbench`, `libpq`, JDBC, ODBC, `sqlcmd`, `SqlClient`, `SQLcl`, and Lexell's own database clients — connect unchanged, see that database's own catalog views and error codes, and share one live database underneath.

---

## Why the design is different

LexDB follows the exact same **shared-nothing** architecture as the [Lexell language](README.md#concurrency-without-threads-or-locks):

- **One event loop, zero locks.** Every client connection runs as a lightweight cooperative task on a single thread using Linux `io_uring` for both network sockets and disk I/O. Only one task runs at a time, and a commit never yields partway through — so there are no mutexes, no spinlocks, no page latches, and no lock-ordering deadlocks anywhere in the storage engine.
- **Copy-on-write columnar B+trees.** Tables are stored as B+trees whose leaves pack rows column by column. Pages referenced by the last checkpoint are never overwritten in place, so power loss cannot corrupt a page and there is no doublewrite buffer, no full-page logging, and no undo pass on crash recovery. Commits arriving in the same event-loop turn automatically share one durable flush (`group commit`).
- **One store for OLTP and analytics.** Point lookups traverse the B+tree straight to a row, while scans, filters, joins, and aggregations read only the columns a query needs and process them in vectorized batches through a cost-based optimizer and adaptive two-level hash aggregation.
- **Strong consistency without blocking.** Read-write transactions run at `SERIALIZABLE` isolation by default (with opt-in `READ COMMITTED` in the PostgreSQL door). Read-only queries run against clean snapshots: readers never block writers, and writers never block readers.
- **Scale reads across cores with read replicas.** Just as Lexell services scale across cores with separate worker processes, LexDB scales reads with shared-nothing read-replica processes (`lexdb ./data --replicas 3`). Replicas follow the master's write-ahead log in real time — staying within **0.22 ms median / 0.44 ms p99** under heavy mixed load — and route read-only clients using each protocol's native mechanism (`target_session_attrs`, `ApplicationIntent=ReadOnly`, Oracle read-only service).

---

## Standout features you rarely find together

Beyond standard relational SQL (joins, CTEs, subqueries, window functions, secondary B+tree indexes, foreign keys, views, stored procedures and functions, roles, and fast native bulk loading via `COPY`, `bcp`/`SqlBulkCopy`, and Oracle array DML), LexDB ships several rare SQL capabilities — many of them unavailable in PostgreSQL or SQL Server today:

### 1. Database-wide `CREATE ASSERTION` across all three doors

The SQL standard's `CREATE ASSERTION` lets you enforce invariants that span multiple rows or multiple tables — "no order without an active customer", "total allocations never exceed capacity", "no two rows in a group can both be primary" — without fragile application-level checks or trigger spaghetti.

Today, **only Oracle AI Database 26ai ships `CREATE ASSERTION`** — neither PostgreSQL nor SQL Server supports it. LexDB implements `CREATE ASSERTION` (`NOT EXISTS`, `EXISTS`, `ALL (...) SATISFY (...)`, including `DEFERRABLE` / `INITIALLY DEFERRED`) across **all three doors**. Define an assertion once in any door and LexDB enforces it automatically on every write path from *every* door (`INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COPY`, `bcp`/`SqlBulkCopy`, Oracle array DML, and `TRUNCATE`), with join-key concurrency locking so two concurrent transactions can never race past an invariant together.

```sql
CREATE ASSERTION no_overbooked_accounts CHECK (
  NOT EXISTS (
    SELECT 1 FROM accounts a, holds h
    WHERE h.account_id = a.id AND h.amount > a.balance
  )
);
```

See [Assertions in the three doors](lexell/docs/lexdb/assertions.md).

### 2. Waiting for new data with `SELECT ... WAIT` (and `WAIT FOR LSN`)

Because every LexDB connection is a lightweight cooperative task on the `io_uring` event loop — not a heavy OS thread or forked backend process — **thousands of clients can park directly inside the database waiting for new rows to commit** with minimal memory and zero polling.

Append `WAIT n SECONDS` (or `MILLISECONDS`) to any indexed cursor query to turn an ordinary table into a transactional event stream across all three doors. If matching rows are already there, it returns immediately; if not, the task parks and wakes the instant a commit adds matching rows — and you can advance the consumer's offset in the **exact same ACID transaction** (no polling loop, no separate message broker, no dual-write problem):

```sql
BEGIN;
SELECT seq, body FROM event
WHERE topic = 'order' AND seq > $1
ORDER BY seq LIMIT 10
WAIT 30 SECONDS;

UPDATE consumer SET last_seen = $2 WHERE name = 'mailer' AND last_seen = $1;
COMMIT;
```

On read replicas, PostgreSQL 19's **`WAIT FOR LSN`** gives clients zero-polling read-your-writes consistency: wait for a replica to replay the master's commit position (`WAIT FOR LSN '0/00000005' WITH (TIMEOUT '1s')`) before running your read.

See [SELECT ... WAIT](lexell/docs/lexdb/sql/postgresql/select-wait.md) and [WAIT FOR LSN](lexell/docs/lexdb/sql/postgresql/wait-for-lsn.md).

### 3. Incremental materialized views & data skipping indexes

In most databases (including PostgreSQL), materialized views are static snapshots that require expensive full `REFRESH` scans and force you to rewrite every application query to name the view. LexDB removes both limits across all three doors:

- **Automatic incremental maintenance (`FAST`).** Inserts, updates, deletes, and bulk loads update only the affected summary rows in **under 1 ms** — supporting cascading multi-level rollup DAGs, composable **HyperLogLog++ / t-digest sketches** for approximate distinct counts and percentiles, and sharded append-only delta trees (`refresh = 'realtime'`) for high-contention hot keys (**22,100+ durable commits/s**).
- **Transparent query rewrite (`query_rewrite = true`).** Your application keeps querying the base tables unchanged; the planner automatically rewrites coarser rollups, filtered slices, `DATE_TRUNC` groupings, exact `COUNT(DISTINCT)` over MV keys, and dimension join-backs onto the materialized view.
- **Automatic zone maps & five data skipping index types.** Every columnar table automatically tracks hierarchical min/max bounds for range and Top-N pruning, and optional per-block skipping indexes (`minmax`/`brin`, `set`, `bloom_filter`, `ngrambf`, `tokenbf`) prune wide-table scans — including leading-wildcard `LIKE '%substring%'` and `ILIKE` — with **zero OLTP write slowdown**.

```sql
-- Maintained incrementally on every write; base-table queries rewrite onto it automatically
CREATE MATERIALIZED VIEW mv_orders_daily
WITH (refresh = 'fast_on_statement', query_rewrite = true) AS
SELECT order_date, region_id, status, COUNT(*) AS n, SUM(amount) AS total
FROM orders
GROUP BY order_date, region_id, status;

-- Prunes non-matching blocks for leading-wildcard substring searches (zero write amplification)
CREATE SKIPPING INDEX ix_hits_url ON hits (url) USING ngrambf(3, 2048, 3);
```

See [Materialized views](lexell/docs/lexdb/materialized-views.md), [Data skipping indexes](lexell/docs/lexdb/skipping-indexes.md), and the ClickBench / 1M-row benchmarks in [Unlocking even more performance](#unlocking-even-more-performance) below.

### 4. Row pattern recognition with `MATCH_RECOGNIZE`

SQL:2016 `MATCH_RECOGNIZE` lets you run regular-expression pattern matching directly over ordered sequences of rows — finding user sessions, V-shaped price reversals, gaps and islands, consecutive failure streaks, or fraud patterns in a single declarative query (`PARTITION BY`, `ORDER BY`, `PATTERN`, `DEFINE`, `MEASURES`, `SUBSET`, `PERMUTE`, `AFTER MATCH SKIP`).

PostgreSQL 18 and SQL Server 2022/2025 have no `MATCH_RECOGNIZE`; LexDB supports it across **all three doors** (PostgreSQL, SQL Server, and Oracle):

```sql
SELECT usr, sid, n, t0, t1
FROM events MATCH_RECOGNIZE (
  PARTITION BY usr ORDER BY ts
  MEASURES match_number() AS sid, count(*) AS n, first(ts) AS t0, last(ts) AS t1
  PATTERN (strt cont*)
  DEFINE cont AS ts - prev(ts) <= 10
) AS m;
```

See [MATCH_RECOGNIZE (PostgreSQL)](lexell/docs/lexdb/sql/postgresql/match-recognize.md), [MATCH_RECOGNIZE (SQL Server)](lexell/docs/lexdb/sql/tsql/match-recognize.md), and [MATCH_RECOGNIZE (Oracle)](lexell/docs/lexdb/sql/oracle/match-recognize.md).

### 5. SQL:2023 Property Graphs (`CREATE PROPERTY GRAPH`, `GRAPH_TABLE` & `ANY SHORTEST`)

Define property graphs directly over your existing relational tables using the single SQL:2023 standard across **all three doors** (PostgreSQL, SQL Server, and Oracle) — with zero data duplication, no separate graph database or ETL sync lag, and full ACID / MVCC transactional consistency. Query multi-hop traversals, cyclic patterns, label expressions, and bounded or unbounded **`ANY SHORTEST`** paths right alongside standard SQL joins, aggregations, and CTEs:

```sql
SELECT count(*), sum(hops)
FROM GRAPH_TABLE (social
  MATCH p = ANY SHORTEST (a IS person WHERE a.id = 42)
        -[k IS knows]->+(b IS person WHERE b.city = 'city_JP_3')
  COLUMNS (path_length(p) AS hops)
);
```

Under the hood, LexDB executes `GRAPH_TABLE` patterns natively with FK-verified vertex-table elimination, join flattening, direct-indexed and 64-bit composite integer hash joins, weighted count-only pipelines, cold bidirectional index-only BFS, and an MVCC-safe cached CSR engine. See **[Property graphs in LexDB](lexell/docs/lexdb/property-graphs.md)**.

---

## Performance out of the box

All comparisons below are measured apples-to-apples against **PostgreSQL 18.6** on the same machine (AMD Ryzen 7 8745HS, Linux 7.2, pinned to 4 physical cores, both servers durable with `fsync` and `synchronous_commit` on). Full query-by-query tables, methodology, and reproduction steps are in the [LexDB performance report](lexell/docs/lexdb/performance.md).

### 1. OLTP writes and read scaling

On durable transactional writes, LexDB's lock-free `io_uring` event loop with group commit sustains **2.4–3.1×** PostgreSQL's update throughput with sub-millisecond commit latency. Because a single LexDB process runs SQL on one thread, scaling read concurrency works by launching shared-nothing read replicas (`--replicas 3` on 4 cores — the same 4-core budget as PostgreSQL):

| OLTP workload (1M rows) | LexDB | PostgreSQL 18 | Takeaway |
|---|---:|---:|---|
| **Durable updates** (`pgbench`, 1–32 clients) | **3.9k / 17.8k / 63.3k/s** | 1.6k / 6.7k / 25.7k/s | **2.41–2.67× faster**; commit latency **0.42 ms** median / **0.86–0.89 ms** p99 |
| **Durable updates** (`sysbench`, non-indexed / indexed, 32t) | **58.9k/s** / **28.1k/s** | 23.0k/s / 21.0k/s | **2.56–3.14× faster** non-indexed; **1.34–2.90× faster** indexed |
| **Point selects** (1 client, `pgbench` / `sysbench`) | **90.4k/s** / **76.9k/s** | 74.5k/s / 65.1k/s | **1.21×** (`pgbench`) / **1.18×** (`sysbench`) faster (`0.01 ms` p95) |
| **Point selects — 3 read replicas** (32 clients, 4 cores) | **470–490k/s** (`pgbench`) / **430.9k/s** (`sysbench`) | 397k/s / 334.1k/s (4 cores) | **1.18–1.23×** (`pgbench`); **1.29×** (`sysbench`, 42% less CPU) |
| **Mixed load** (replica selects + master writes, 4 cores) | **368–403k/s** reads + **15.5–16.1k/s** writes | — | Replica lag stays at **0.22–0.23 ms** median, **0.41–0.44 ms** p99 |

### 2. OLAP analytics and bulk loads

With **no materialized views and no explicit skipping indexes**, LexDB's vectorized columnar engine — using pure `par.map` worker threads across the same 4-core budget as PostgreSQL for large scans, hash-join probes, and aggregations while keeping small tables and low-compute scans single-threaded — beats 4-process PostgreSQL across every analytical suite and bulk load:

| OLAP & load workload | LexDB | PostgreSQL 18 | Takeaway |
|---|---:|---:|---|
| **TPC-H SF1** (22 queries, 4 cores via `par.map`) | **3.25 s** *(4.78 s CPU)* | 8.84 s (4 proc) *(15.03 s 1c CPU)* | **2.72× faster** than 4-process PG overall (`0.51×` geomean, 17/22 faster; `q1` **261 ms** — **3.35×**, `q9` **323 ms** — **2.32×**, `q18` **103 ms** — **28.5×**); **3.14× less total CPU** |
| **ClickBench 1M** (43 queries, 105 cols, 4 cores via `par.map`) | **4.78 s** *(7.12 s CPU)* | 11.40 s (4 proc) *(23.12 s 1c CPU)* | **2.39× faster** than 4-process PG (**43/43** faster, `0.51×` geomean, no MVs); **3.25× less total CPU** (`0.29×` geomean) |
| **35 Analytic Queries** (1M rows, 1 core) | **0.39× CPU / 0.78× wall** | 1 core / 4 proc | **2.59× less CPU** than 1-core PG (**35/35** ahead on wall & CPU); **1.28× faster** wall time than 4-process PG |
| **Selective star-schema joins** (1M fact rows, 6 patterns, 1 core) | **0.54–22.5 ms** | 0.21–77.0 ms (1 core) / 0.24–50.7 ms (4 proc) | **1.24–71.7× faster** via hash-join runtime filters; **7.68×** vs PG1 / **4.46×** vs PG4 (geomean) |
| **Bulk `\copy` loads** (5 cases, 1M–10M rows) | **0.26–2.61 s** | 0.61–5.93 s | **1.25–2.6× faster** on every workload (`224–2,103 MB` peak RSS) |

### 3. Property graphs (SQL/PGQ)

Measured single-core / single-thread with 100% exact result parity across relational and dedicated graph engines:

| Graph benchmark (1 core / 1 thread) | LexDB | PostgreSQL 18 | DuckDB 2.0 + DuckPGQ | Kùzu 0.11 | Neo4j 5.26 CE |
|---|---:|---:|---:|---:|---:|
| **Social-graph suite** (11 queries, 100k vertices / 1.1M edges, incl. `ANY SHORTEST`) | **0.50 s** | 5.66 s | 0.96 s | 1.37 s | — |
| **LDBC LSQB SF0.1** (9 queries, 432k vertices / 2.1M edges) | **0.45 s** | 3.93 s *(8/9, Q9 timeout)* | **0.24 s** *(+PK/FK)* | 3.95 s | 7.60 s |
| **LDBC LSQB SF1** (9 queries, 4.0M vertices / 22.2M edges) | **7.30 s** | 98.1 s *(8/9, Q9 timeout)* | **4.56 s** *(+PK/FK)* | 105.0 s | 156.0 s |

On the **11-query social-graph suite** (local traversals, triangles, and shortest paths), LexDB is the **fastest of all four engines** (`0.50 s` total — **1.92× faster than DuckPGQ**, **2.73× faster than Kùzu**, **11.3× faster than PG1**; `0.45 ms` warm / `0.71 ms` cold 5-hop shortest path, `227 ms` 1M-edge triangles; geomean **7.82×** vs PG1, **3.06×** vs DuckPGQ, **5.86×** vs Kùzu). On **LDBC LSQB** (pure full-graph analytical pattern counting), in-memory DuckDB 2.0 + DuckPGQ (with matching `PRIMARY KEY` / `FOREIGN KEY` constraints) leads overall, while LexDB is **#2 overall and #1 among disk-backed transactional & graph databases** (`7.30 s` at SF1 — within **1.58×** geomean of in-memory DuckPGQ), beating PostgreSQL 18 (**9.03×** geomean on completed queries), Kùzu (**4.40×** geomean, **14.4×** total), and Neo4j Community (**17.4×** geomean, **21.4×** total), and ranking **#1 fastest of all five engines** on both billion-match queries at SF1 (`Q6` `97.8 ms` — **5.81× faster than DuckPGQ**; `Q9` `1,396.9 ms` vs DuckPGQ's `1,408.5 ms`) as well as SF0.1 `Q6` (`10.1 ms` — **1.95× faster than DuckPGQ**). See **[Property graphs in LexDB](lexell/docs/lexdb/property-graphs.md)** for full query-by-query tables and methodology.

**Where PostgreSQL is ahead today:** Multi-threaded reads against a single LexDB process (before adding replicas) and multi-statement read-write transaction blocks under high concurrency.

---

## Unlocking even more performance

Out-of-the-box speed is only half the story. Two built-in features let you turn multi-hundred-millisecond analytical scans into sub-millisecond lookups — without changing application code or slowing down OLTP writes.

### Incremental materialized views & transparent query rewrite

In most databases, materialized views are static snapshots that require expensive full refreshes and require rewriting every query to name the view. LexDB removes both limits:

1. **Sub-millisecond incremental maintenance (`FAST`).** Inserts, updates, deletes, and bulk loads update only the affected summary rows automatically — typically in **under 1 ms** instead of rescanning millions of rows. High-contention hot keys can use sharded append-only delta trees (`ON QUERY COMPUTATION`) to sustain **22,100+ durable commits/s** across 16 concurrent writers with zero serialization conflicts.
2. **Transparent query rewrite (`ENABLE QUERY REWRITE`).** Your application keeps querying the base tables as usual. When the planner sees that a fresh materialized view already holds the answer (or can be rolled up, filtered, date-truncated, or joined to a dimension table to produce it), it rewrites the query onto the view automatically.

It also supports **cascading multi-level rollup DAGs** and **composable HyperLogLog++ / t-digest sketches** for incremental approximate distinct counts and percentiles.

| Benchmark (1M rows, single core) | Without MVs | With MVs (unmodified queries) | Live write cost |
|---|---:|---:|---|
| **ClickBench 1M** (43 queries, +8 general MVs) | 4.78 s | 21 of 43 queries transparently rewritten to **0.47–54.9 ms** (geomean `0.10×` PG1 / `0.21×` PG4 at `59797d55`) | 1 / 100 new rows updating all 8 MVs live: **6.51 / 10.34 ms** |
| **35 Analytic Queries** (+4 general MVs) | geomean `0.48×` PG1 / `0.78×` PG4 | 9 aggregate & join queries drop from 8–74 ms to **3–4 ms** (geomean **`0.31×` PG1 / `0.49×` PG4**) | 1 / 100 / 1,000 new rows updating all 4 MVs live: **4.40 / 7.09 / 25.90 ms** vs PG `REFRESH` **758 / 264 ms** |
| **Grouped / Sketch / 3-level DAG** | 23.7 ms grouped / 234.4 ms sketch | **0.18 ms** (132×) / **0.56 ms** (419×) / **0.07 ms** | 1-row `FAST` update: **0.43–0.66 ms** vs PG `REFRESH` **60–369 ms** (**90–780× faster**) |

Read the user guide: **[Materialized views and transparent query rewrite](lexell/docs/lexdb/materialized-views.md)**.

### Automatic zone maps & data skipping indexes

A regular B+tree index is great for exact key lookups, but indexing five or ten text and analytics columns on a wide table bloats storage and slows down writes. LexDB solves this in two layers:

1. **Always-on automatic zone maps & hash-join runtime filters.** Every columnar table tracks min/max bounds hierarchically inside its B+tree automatically — pruning irrelevant blocks for range filters, dynamic `ORDER BY ... LIMIT` queries (`sort_lim` drops from 19 ms to **6 ms**), and selective hash joins (pushing build-side MinMax bounds, small `IN` sets, and register-blocked L1 Bloom filters into probe scans for **1.24×–71.7×** faster star-schema joins — **7.7×** faster than 1-core PostgreSQL 18 and **4.5×** faster than 4-process PostgreSQL 18).
2. **Optional data skipping indexes.** Add lightweight per-block summaries (`minmax`/`brin`, `set`, `bloom_filter`, `ngrambf`, or `tokenbf`) on columns you filter or join on — including arbitrary substring searches like `WHERE URL LIKE '%google%'` that a standard B+tree cannot help with.

| ClickBench 1M query | Filter | Skipping index | Baseline | With skipping index | Speedup |
|---|---|---|---:|---:|---:|
| `q19` | `WHERE UserID = 435090932899640449` | `bloom_filter(UserID)` | 173.2 ms | **42.6 ms** | **4.07×** |
| `q21` | `WHERE URL LIKE '%google%'` | `ngrambf(URL)` | 339.9 ms | **167.7 ms** | **2.03×** |
| `q23` | `WHERE Title LIKE '%Google%'` | `ngrambf(Title)` | 331.7 ms | **168.7 ms** | **1.97×** |
| `q22` | `WHERE Title LIKE '%Google%' AND URL NOT LIKE '%.google.%'` | `ngrambf(Title)` | 620.1 ms | **485.4 ms** | **1.28×** |

With all three skipping indexes active on the 105-column `hits` table, OLTP writes and point reads show **zero regression** (1,000 inserts: `303.9` vs `304.6 ms`; 1,000 PK lookups: `44.4` vs `45.1 ms`).

Read the user guide: **[Data skipping indexes](lexell/docs/lexdb/skipping-indexes.md)**.

---

## Try it in 30 seconds

On Linux x86-64-v3 (requires GCC for the initial compiler bootstrap):

```sh
# 1. Build the Lexell compiler and the single-binary lexdb executable
lexell/compiler/build.sh
lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -O -o lexdb

# 2. Start LexDB with PostgreSQL, SQL Server, and Oracle doors (add --replicas 3 to scale reads)
./lexdb ./data 127.0.0.1:5433 --tds 127.0.0.1:1433 --tns 127.0.0.1:1521

# 3. Connect with psql, sqlcmd, or SQLcl
psql -h 127.0.0.1 -p 5433 -U postgres lexdb
```

---

## Where to go next

| Page | What it covers |
|---|---|
| [Quick start](lexell/docs/lexdb/quickstart.md) | Step-by-step walkthrough using one table from PostgreSQL, SQL Server, and Oracle clients. |
| [Driver & ORM compatibility](lexell/docs/lexdb/compatibility.md) | Verified matrix and reproducible test suite across SQLAlchemy, Alembic, Django, Entity Framework Core, psycopg, asyncpg, pymssql, oracledb, ODP.NET, and Knex on all three doors. |
| [LexDB performance report](lexell/docs/lexdb/performance.md) | Full query-by-query TPC-H, ClickBench, 35 analytic, OLTP (`pgbench`/`sysbench`), materialized view, and bulk load numbers against PostgreSQL 18. |
| [Materialized views](lexell/docs/lexdb/materialized-views.md) | Incremental `FAST` updates, transparent query rewrite, real-time delta merging, sketches, and cascading DAGs. |
| [Data skipping indexes](lexell/docs/lexdb/skipping-indexes.md) | When to use `minmax`/`brin`, `set`, `bloom_filter`, `ngrambf`, and `tokenbf` — with plain-English examples. |
| [Read replicas](lexell/docs/lexdb/replicas.md) | Scaling reads across cores, per-door read-only routing, and `WAIT FOR LSN`. |
| [Assertions](lexell/docs/lexdb/assertions.md) | SQL-standard `CREATE ASSERTION` enforced across PostgreSQL, SQL Server, and Oracle doors. |
| [SELECT ... WAIT](lexell/docs/lexdb/sql/postgresql/select-wait.md) & [MATCH_RECOGNIZE](lexell/docs/lexdb/sql/postgresql/match-recognize.md) | Transactional event streams (`WAIT n SECONDS`) and SQL:2016 row pattern recognition. |
| [Bulk loading](lexell/docs/lexdb/bulk-load.md), [PostgreSQL `pg_dump`/`pg_restore`](lexell/docs/lexdb/pg-restore.md) & [SQL Server migration (`lexmigrate`)](lexell/docs/lexdb/migrate-mssql.md) | Fast `COPY`/bcp/array DML loading, restoring PostgreSQL backups (`-Fp`, `-Fc`, `-Ft`, `-Fd`), and native TDS live migration & zstd dump/restore from SQL Server. |
| [Full LexDB documentation](lexell/docs/lexdb/README.md) | Architecture, transactions, security, bulk loading, property graphs, and complete SQL references for all three doors. |
| [Internals & benchmark history](lexell/design/lexdb.md) | Storage engine internals ([lexdb.md](lexell/design/lexdb.md)) and the full historical benchmark log ([lexdb-benchmarks.md](lexell/design/lexdb-benchmarks.md)). |
