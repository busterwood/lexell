# LexDB

LexDB is a fast, full-featured SQL database server written in [Lexell](README.md). It ships as a single native executable built for modern NVMe/SSD storage, and handles both **OLTP transactions** and **columnar analytics** in one engine — with no locks, no page latches, and no separate analytics cluster to maintain.

One server speaks **three native wire protocols and SQL dialects simultaneously** over the same tables and catalog:

- **PostgreSQL** (`pgwire`, PostgreSQL SQL & PL/pgSQL)
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

### 3. Row pattern recognition with `MATCH_RECOGNIZE`

SQL:2016 `MATCH_RECOGNIZE` lets you run regular-expression pattern matching directly over ordered sequences of rows — finding user sessions, V-shaped price reversals, gaps and islands, consecutive failure streaks, or fraud patterns in a single declarative query (`PARTITION BY`, `ORDER BY`, `PATTERN`, `DEFINE`, `MEASURES`, `SUBSET`, `PERMUTE`, `AFTER MATCH SKIP`).

PostgreSQL 18 has no `MATCH_RECOGNIZE`; LexDB supports it in both the **PostgreSQL** and **Oracle** doors:

```sql
SELECT usr, sid, n, t0, t1
FROM events MATCH_RECOGNIZE (
  PARTITION BY usr ORDER BY ts
  MEASURES match_number() AS sid, count(*) AS n, first(ts) AS t0, last(ts) AS t1
  PATTERN (strt cont*)
  DEFINE cont AS ts - prev(ts) <= 10
) AS m;
```

See [MATCH_RECOGNIZE (PostgreSQL door)](lexell/docs/lexdb/sql/postgresql/match-recognize.md) and [MATCH_RECOGNIZE (Oracle door)](lexell/docs/lexdb/sql/oracle/match-recognize.md).

### 4. SQL:2023 Property Graphs (`CREATE PROPERTY GRAPH` & `GRAPH_TABLE`)

Define property graphs directly over your existing relational tables with zero data duplication and query multi-hop patterns, label expressions, and bounded paths using standard SQL/PGQ `GRAPH_TABLE` across all three doors. See [GRAPH_TABLE](lexell/docs/lexdb/sql/postgresql/graph-table.md).

### 5. Incremental materialized views & data skipping indexes

Keep precomputed rollups, cascading rollup DAGs, and HyperLogLog++ / t-digest sketches fresh in under a millisecond with automatic transparent query rewrite, and prune wide-table scans (including `LIKE '%substring%'`) with automatic zone maps and five skipping index types — see [Unlocking even more performance](#unlocking-even-more-performance) below.

---

## Performance out of the box

All comparisons below are measured apples-to-apples against **PostgreSQL 18.6** on the same machine (AMD Ryzen 7 8745HS, Linux 7.2, pinned to 4 physical cores, both servers durable with `fsync` and `synchronous_commit` on). Full query-by-query tables, methodology, and reproduction steps are in the [LexDB performance report](lexell/docs/lexdb/performance.md).

### 1. Standard analytics, OLTP writes, and bulk loads

With **no materialized views and no explicit skipping indexes**, LexDB's single-core engine beats single-core PostgreSQL across analytical suites, durable OLTP writes, and bulk loads — and often beats 4-process PostgreSQL on total time:

| Workload | LexDB | PostgreSQL 18 | Takeaway |
|---|---:|---:|---|
| **TPC-H SF1** (22 queries, 1 core) | **7.20 s** | 14.67 s (1 core) / 8.84 s (4 proc) | **2.0× faster** than 1-core PG (faster on all 22/22); **1.23× faster** than 4-process PG overall |
| **ClickBench 1M** (43 queries, 105 cols, 1 core) | **14.10 s** | 22.36 s (1 core) / 11.33 s (4 proc) | **1.59× faster** than 1-core PG (40/43 level or ahead; 0.64× CPU) |
| **35 Analytic Queries** (1M rows, 1 core) | **0.46× CPU / 0.91× wall** | 1 core / 4 proc | **2.2× less CPU** than 1-core PG; faster wall time than 4-process PG |
| **Durable OLTP updates** (1–32 clients) | up to **63.3k/s** (`pgbench`) / **54.2k/s** (`sysbench`) | 25.7k/s / 23.0k/s | **2.4–3.1× faster** non-indexed updates; **1.3–2.5× faster** indexed updates (`27.7k/s`); commit latency **0.42 ms** median / **0.86–0.89 ms** p99 |
| **Bulk `\copy` loads** (5 cases, 1M–10M rows) | **0.24–2.44 s** | 0.61–5.93 s | **1.1–2.7× faster** on every workload (including wide tables + secondary indexes) |

### 2. Scaling reads across cores with read replicas

Because a single LexDB process runs SQL on one thread, scaling read concurrency works by launching shared-nothing read replicas (`--replicas 3` on 4 cores — the same 4-core budget as PostgreSQL):

| Read workload (32 clients, 4 cores) | LexDB (master + 3 replicas) | PostgreSQL 18 (4 cores) | Takeaway |
|---|---:|---:|---|
| **`pgbench` point selects** (1M rows) | **470–490k/s** | 397k/s | **1.18–1.23× faster** |
| **`sysbench` point selects** (1M rows) | **350.5k/s** (p95 `0.14 ms`) | 334.1k/s (p95 `0.15 ms`) | **1.05× faster**, using **29% less CPU** |
| **Mixed load** (replica selects + master writes) | **368–403k/s** reads + **15.5–16.1k/s** writes | — | Replica lag stays at **0.22–0.23 ms** median, **0.41–0.44 ms** p99 |

**Where PostgreSQL is ahead today:** Multi-threaded reads against a single LexDB process (before adding replicas), multi-statement read-write transaction blocks under high concurrency, and individual heavy queries that benefit from PostgreSQL's 4-worker parallel query execution (LexDB runs each single statement on one core).

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
| **ClickBench 1M** (43 queries, +8 general MVs) | 14.10 s | **9.07 s total** — **1.25× faster than 4-core PG (`11.33 s`) on one core** (21 queries rewritten; geomean `0.10×` PG1 / `0.21×` PG4) | 1 / 100 new rows updating all 8 MVs live: **6.51 / 10.34 ms** |
| **35 Analytic Queries** (+4 general MVs) | geomean `0.56×` PG1 / `0.91×` PG4 | 9 aggregate & join queries drop from 8–91 ms to **3–4 ms** (geomean **`0.31×` PG1 / `0.49×` PG4**) | 1 / 100 / 1,000 new rows updating all 4 MVs live: **4.40 / 7.09 / 25.90 ms** vs PG `REFRESH` **758 / 264 ms** |
| **Grouped / Sketch / 3-level DAG** | 23.7 ms grouped / 234.4 ms sketch | **0.18 ms** (132×) / **0.56 ms** (419×) / **0.07 ms** | 1-row `FAST` update: **0.43–0.66 ms** vs PG `REFRESH` **60–369 ms** (**90–780× faster**) |

Read the user guide: **[Materialized views and transparent query rewrite](lexell/docs/lexdb/materialized-views.md)**.

### Automatic zone maps & data skipping indexes

A regular B+tree index is great for exact key lookups, but indexing five or ten text and analytics columns on a wide table bloats storage and slows down writes. LexDB solves this in two layers:

1. **Always-on automatic zone maps.** Every columnar table tracks min/max bounds hierarchically inside its B+tree automatically — pruning irrelevant blocks for range filters and dynamic `ORDER BY ... LIMIT` queries (`sort_lim` drops from 19 ms to **6 ms** with zero configuration).
2. **Optional data skipping indexes.** Add lightweight per-block summaries (`minmax`/`brin`, `set`, `bloom_filter`, `ngrambf`, or `tokenbf`) on columns you filter on — including arbitrary substring searches like `WHERE URL LIKE '%google%'` that a standard B+tree cannot help with.

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
| [LexDB performance report](lexell/docs/lexdb/performance.md) | Full query-by-query TPC-H, ClickBench, 35 analytic, OLTP (`pgbench`/`sysbench`), materialized view, and bulk load numbers against PostgreSQL 18. |
| [Materialized views](lexell/docs/lexdb/materialized-views.md) | Incremental `FAST` updates, transparent query rewrite, real-time delta merging, sketches, and cascading DAGs. |
| [Data skipping indexes](lexell/docs/lexdb/skipping-indexes.md) | When to use `minmax`/`brin`, `set`, `bloom_filter`, `ngrambf`, and `tokenbf` — with plain-English examples. |
| [Read replicas](lexell/docs/lexdb/replicas.md) | Scaling reads across cores, per-door read-only routing, and `WAIT FOR LSN`. |
| [Assertions](lexell/docs/lexdb/assertions.md) | SQL-standard `CREATE ASSERTION` enforced across PostgreSQL, SQL Server, and Oracle doors. |
| [SELECT ... WAIT](lexell/docs/lexdb/sql/postgresql/select-wait.md) & [MATCH_RECOGNIZE](lexell/docs/lexdb/sql/postgresql/match-recognize.md) | Transactional event streams (`WAIT n SECONDS`) and SQL:2016 row pattern recognition. |
| [Full LexDB documentation](lexell/docs/lexdb/README.md) | Architecture, transactions, security, bulk loading, property graphs, and complete SQL references for all three doors. |
| [Internals & benchmark history](lexell/design/lexdb.md) | Storage engine internals ([lexdb.md](lexell/design/lexdb.md)) and the full historical benchmark log ([lexdb-benchmarks.md](lexell/design/lexdb-benchmarks.md)). |
