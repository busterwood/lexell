# Materialized views and transparent query rewrite

A materialized view stores the result of a query on disk in its own B+tree. Unlike a regular view — which re-executes
its defining query on every `SELECT` — a materialized view answers reads directly from precomputed rows, supports
indexes and `ANALYZE`, and participates in MVCC snapshots, WAL, and crash recovery just like a table.

In lexdb, materialized views go far beyond manual snapshot refresh:

- **Incremental $O(\Delta)$ maintenance (`FAST`)** using signed Z-set deltas on `INSERT`, `UPDATE`, `DELETE`, `COPY`,
  `MERGE`, and `TRUNCATE` — updating a materialized view in fractions of a millisecond instead of rescanning millions
  of rows.
- **Real-time contention-free writes (`realtime` / `ON QUERY COMPUTATION`)** that append deltas to a sharded companion
  delta tree, merge base + deltas on read inside the reader's MVCC snapshot, and fold deltas into the base tree in the
  background.
- **Cascading rollup DAGs** where materialized views query other materialized views and deltas propagate topologically
  in $O(\Delta)$.
- **Composable approximate sketches** (HyperLogLog++ distinct counts and t-digest percentiles) that merge associatively
  in $O(\Delta)$.
- **Automatic transparent query rewrite (`ENABLE QUERY REWRITE`)** so existing `SELECT` queries against base tables are
  rewritten by the planner onto the lowest-cost matching materialized view with zero application changes.

All three doors — PostgreSQL, Oracle (TNS), and SQL Server (TDS) — share the same engine, so a materialized view
created from one door is maintained for writes from every door and can accelerate queries from every door.

## Why materialized views matter

Analytical workloads frequently repeat the same joins and aggregations across dashboards, reports, and ad-hoc filters.
Without materialized views, every query scans the full fact table. With a handful of well-chosen rollup materialized
views and `ENABLE QUERY REWRITE`:

- **Zero-code query speedups:** Applications keep querying the base tables. The planner detects when an existing
  materialized view satisfies a query (exact match, filtered slice, coarser rollup, derived grouping, or dimension
  join-back) and transparently rewrites the plan onto the compact materialized view — turning 100–600 ms scans into
  1–5 ms lookups.
- **Orders-of-magnitude less refresh work:** Because `FAST` maintenance processes only the changed rows ($\Delta$)
  rather than rescanning the base table, incremental updates stay sub-millisecond even over million-row tables.
- **Single-core execution that beats multi-core full scans:** In the ClickBench 1M benchmark
  ([PERFORMANCE.md](../../../PERFORMANCE.md)), adding 8 compact rollup materialized views (built in ~6.0 s total)
  transparently rewrites 21 of the 43 queries with exact result parity, cutting total 43-query single-core wall time
  from **14.10 s** to **9.07 s** — 2.26 s faster than 4-core PostgreSQL 18 (11.33 s) on a single core, with a geometric
  mean ratio of **0.10×** against 1-core PostgreSQL and **0.21×** against 4-core PostgreSQL.
- **Measured impact on mixed analytic suites:** On the 35-query 1M-row analytic benchmark, 4 rollup materialized views
  transparently rewrite 9 aggregate and join queries down to ~3 ms each, cutting geometric-mean CPU and wall ratios
  nearly in half while live `INSERT` maintenance across all 4 views takes only a few milliseconds.
- **Incremental `FAST` vs full `REFRESH`:** On a 1M-row event table, incrementally maintaining a grouped, sketch, or
  3-level cascading materialized view takes **0.43–0.66 ms** in lexdb versus **60–369 ms** for PostgreSQL 18's full
  `REFRESH MATERIALIZED VIEW`.

## Refresh modes and maintenance timings

Choose a maintenance mode based on how fresh reads must be and how hot the write path is:

| Mode (PostgreSQL `WITH` / Oracle & T-SQL clause) | When updated | Read freshness | Best for |
|---|---|---|---|
| `'demand'` / `REFRESH [COMPLETE\|FAST\|FORCE] ON DEMAND` | Manual `REFRESH MATERIALIZED VIEW` / `DBMS_MVIEW.REFRESH` | As of last refresh (skipped by query rewrite when stale) | Batch ETL, periodic reporting snapshots |
| `'fast_on_statement'` / `REFRESH FAST ON STATEMENT` | Synchronously at the end of every DML statement | Always current, including inside the writing transaction | Interactive apps needing read-your-writes on MVs |
| `'fast_on_commit'` (`'incremental'`) / `REFRESH FAST ON COMMIT` | Incrementally at transaction `COMMIT` (savepoint-safe) | Always current for committed transactions | Multi-statement OLTP transactions batching several writes |
| `'complete_on_commit'` / `REFRESH COMPLETE ON COMMIT` | Atomically rebuilt at `COMMIT` if a base table changed | Always current for committed transactions | Small tables with query shapes not eligible for `FAST` |
| `'force_on_commit'` / `'force_on_statement'` | Uses `FAST` if eligible, otherwise falls back to `COMPLETE` | Always current | General-purpose definitions where fallback is desired |
| `'realtime'` / `ENABLE ON QUERY COMPUTATION` | Appends signed deltas to a sharded delta tree; merged on read and folded in the background (or on `REFRESH ... FAST`) | Always current in the reader's MVCC snapshot (even for `ON DEMAND` views) | High-concurrency OLTP writers updating hot aggregate keys |

Notes on refresh execution:

- **Atomic non-blocking complete refresh (`CONCURRENTLY`):** `REFRESH MATERIALIZED VIEW CONCURRENTLY` builds the fresh
  result into a brand-new B+tree and swaps the root atomically, so concurrent readers never block or observe partial
  state. (Requires the view to be populated and to have a unique index with no `WHERE` clause.)
- **Background delta folding:** Real-time materialized views automatically fold accumulated deltas into the base B+tree
  in the background. Set `LEXDB_MV_FOLD=off` to disable background folding and fold explicitly with
  `REFRESH MATERIALIZED VIEW name FAST`.

## Transparent query rewrite

Transparent query rewrite is what makes materialized views practical at scale: you can add or tune rollup views to
accelerate a workload without modifying a single application query.

### Enabling and controlling rewrite

1. Enable rewrite on the materialized view when creating or altering it:
   - PostgreSQL / SQL Server: `WITH (refresh = 'fast_on_statement', query_rewrite = true)` or `ENABLE QUERY REWRITE`
   - Oracle: `ENABLE QUERY REWRITE`
2. Query rewrite is enabled by default per session and can be toggled at any time:
   - PostgreSQL / SQL Server: `SET query_rewrite_enabled = on | off;`
   - Oracle: `ALTER SESSION SET QUERY_REWRITE_ENABLED = TRUE | FALSE | FORCE;`

### What queries rewrite automatically

When multiple materialized views match a query, lexdb chooses the lowest-cost fresh candidate. Supported rewrite
patterns include:

- **Exact and subset projections** of the view's columns and aggregates, plus `ORDER BY`, `LIMIT`, and `HAVING`
  evaluated over the compact view.
- **Subsumed `WHERE` predicates:** Exact equality, range comparisons (`<`, `<=`, `>`, `>=`, `BETWEEN`), `IN (...)`,
  `<>`, and `IS NOT NULL` pushed onto view grouping keys (or already satisfied by the view's own `WHERE` predicate).
- **Coarser and derived `GROUP BY` rollups:** A single finer-grained MV — for example grouped by `(event_date,
  region_id, category_id)` — transparently answers queries grouped by `(event_date)`, `(region_id)`, global totals
  with no `GROUP BY`, or derived expressions such as `DATE_TRUNC('month', event_date)` and `EXTRACT(YEAR FROM
  event_date)`.
- **Algebraic and sketch aggregate rollups:** `COUNT(*)`, `COUNT(expr)`, `SUM`, `AVG` (via internal `SUM`/`COUNT`
  state), `MIN`, `MAX`, `VAR_POP`, `VAR_SAMP`, `VARIANCE`, `STDDEV_POP`, `STDDEV_SAMP`, `STDDEV`, `BOOL_AND`/`EVERY`,
  `BOOL_OR`, `BIT_XOR`, and HyperLogLog++ / t-digest sketches — including rolling up from hidden internal state
  columns stored automatically by the MV.
- **Exact `DISTINCT` aggregate rollups over MV keys:** `COUNT(DISTINCT k)`, `SUM(DISTINCT k)`, and `AVG(DISTINCT k)`
  when `k` is one of the MV's grouping keys (automatically simplifying to non-distinct `COUNT`/`SUM`/`AVG` when the
  query's `GROUP BY` matches the MV's keys).
- **Dimension join-back:** Queries that join the base fact table to additional dimension tables (including `LEFT JOIN`)
  not present in the MV, provided the join key is preserved as a grouping key in the MV.
- **Long text grouping keys:** Oversized `GROUP BY` keys (such as `URL` or `Referer` strings exceeding 512 bytes) are
  fingerprinted automatically into a fixed-width internal key so MVs over wide text columns still build, maintain, and
  rewrite cleanly.

### Verifying a rewrite with `EXPLAIN`

Run `EXPLAIN` on your base-table query to confirm that the planner reads the materialized view instead of scanning the
base table:

```sql
EXPLAIN SELECT region_id, SUM(amount) FROM orders GROUP BY region_id;
```

If rewritten, the plan scans the materialized view (for example `mv_orders_daily`) instead of `orders`. You can verify
exact result parity at any time by comparing results with `SET query_rewrite_enabled = off` vs `on`.

### Freshness and correctness guarantees

Query rewrite never sacrifices correctness for speed:

- **Stale `ON DEMAND` views** (whose base table has been modified since the last refresh and that do not have
  `ON QUERY COMPUTATION` enabled) are automatically skipped by the rewriter.
- **Uncommitted `ON COMMIT` changes** inside the current transaction cause the rewriter to bypass affected `ON COMMIT`
  views for that transaction so uncommitted writes remain visible.
- **`WITH NO DATA` / `BUILD DEFERRED`** views are ignored until first populated.

## Incremental maintenance (`FAST`), sketches, and cascading DAGs

### Eligible query shapes for `FAST` maintenance

Incremental maintenance handles all standard analytical building blocks across `INSERT`, `UPDATE`, `DELETE`, `COPY`,
`MERGE`, and `TRUNCATE`:

- Single-table filter and projection views (`SELECT ... FROM t WHERE ...`)
- Grouped and global aggregates: `COUNT(*)`, `COUNT(expr)`, `SUM`, `AVG`, `MIN`, `MAX`, `VAR_POP`, `VAR_SAMP`,
  `VARIANCE`, `STDDEV_POP`, `STDDEV_SAMP`, `STDDEV`, `BOOL_AND`/`EVERY`, `BOOL_OR`, `BIT_XOR`, and sketch aggregates,
  including `FILTER (WHERE ...)` clauses
- Multi-table inner equi-joins (both projection views and grouped aggregate views)

Algebraic aggregates (`COUNT`, `SUM`, `AVG`, variance/stddev, `BIT_XOR`) update purely from the signed Z-set delta
without touching the base table. Non-algebraic extrema (`MIN`, `MAX`) update in $O(\Delta)$ on inserts and only
re-probe the affected group if a delete removes the current minimum or maximum.

### Composable approximate sketches

For high-cardinality distinct counts and percentiles over millions of rows, lexdb provides composable sketch aggregates
that maintain incrementally in $O(\Delta)$:

- **HyperLogLog++ distinct counts:** `APPROX_COUNT_DISTINCT(expr)`, `APPROX_COUNT_DISTINCT_DETAIL(expr)` (returns
  serializable sketch state), and `APPROX_COUNT_DISTINCT_AGG(detail)` (merges sketches across coarser rollups).
- **Dunning merging t-digest percentiles:** `APPROX_PERCENTILE(expr, p)`, `APPROX_PERCENTILE_DETAIL(expr)`, and
  `APPROX_PERCENTILE_AGG(detail, p)`.

Appends merge associatively in $O(\Delta)$; deletes automatically re-probe affected groups when needed.

### Cascading materialized views (rollup DAGs)

A materialized view can query another materialized view, forming a multi-level rollup hierarchy — for example:

```text
events (base table)
  └── mv_hourly (GROUP BY hour, region; includes APPROX_COUNT_DISTINCT_DETAIL(user_id))
        └── mv_daily (GROUP BY day, region; merges via APPROX_COUNT_DISTINCT_AGG)
              └── mv_total (global totals)
```

Incremental deltas propagate topologically down the DAG in $O(\Delta)$ across `ON STATEMENT`, `ON COMMIT`, and
background or explicit `FAST` delta folding.

## Syntax across the three doors

The engine is shared across all three doors; each door exposes its native syntax alongside lexdb's incremental and
rewrite clauses.

### PostgreSQL door

See [CREATE MATERIALIZED VIEW (PostgreSQL)](sql/postgresql/create-materialized-view.md) for the full reference.

```sql
CREATE MATERIALIZED VIEW mv_sales_daily
WITH (refresh = 'fast_on_statement', query_rewrite = true) AS
SELECT sale_date, region_id,
       COUNT(*) AS cnt,
       SUM(amount) AS total_amount,
       APPROX_COUNT_DISTINCT(customer_id) AS approx_customers
FROM sales
GROUP BY sale_date, region_id;

-- Existing base-table queries rewrite automatically onto mv_sales_daily:
SELECT region_id, SUM(amount) FROM sales GROUP BY region_id;

-- Contention-free real-time MV for hot keys:
CREATE MATERIALIZED VIEW mv_hot_counters
WITH (refresh = 'realtime', query_rewrite = true) AS
SELECT bucket_id, COUNT(*) AS cnt, SUM(val) AS tot
FROM hot_events
GROUP BY bucket_id;
```

### Oracle (TNS) door

See [CREATE MATERIALIZED VIEW (Oracle)](sql/oracle/create-materialized-view.md) for the full reference.

```sql
CREATE MATERIALIZED VIEW mv_sales_daily
    BUILD IMMEDIATE
    REFRESH FAST ON COMMIT
    ENABLE QUERY REWRITE
AS
SELECT sale_date, region_id, COUNT(*) AS cnt, SUM(amount) AS total_amount
FROM sales
GROUP BY sale_date, region_id;

-- Real-time on-query delta merging:
CREATE MATERIALIZED VIEW mv_hot_counters
    REFRESH FAST ON DEMAND
    ENABLE QUERY REWRITE
    ENABLE ON QUERY COMPUTATION
AS
SELECT bucket_id, COUNT(*) AS cnt, SUM(val) AS tot
FROM hot_events
GROUP BY bucket_id;

-- Manual refresh via PL/SQL:
BEGIN
    DBMS_MVIEW.REFRESH('mv_sales_daily', 'F');
END;
```

### SQL Server (TDS) door

See [CREATE MATERIALIZED VIEW (Transact-SQL)](sql/tsql/create-materialized-view.md) and
[CREATE VIEW (Transact-SQL)](sql/tsql/create-view.md) for the full reference. SQL Server supports both cross-door
`CREATE MATERIALIZED VIEW` and native indexed views (`WITH SCHEMABINDING` + `CREATE UNIQUE CLUSTERED INDEX`):

```sql
-- Cross-door materialized view with incremental maintenance and rewrite:
CREATE MATERIALIZED VIEW dbo.mv_sales_daily
    REFRESH FAST ON STATEMENT
    ENABLE QUERY REWRITE
AS
SELECT sale_date, region_id, COUNT(*) AS cnt, SUM(amount) AS total_amount
FROM dbo.sales
GROUP BY sale_date, region_id;
GO

-- Native SQL Server indexed view:
CREATE VIEW dbo.v_sales_by_region WITH SCHEMABINDING AS
SELECT region_id, COUNT(*) AS cnt, SUM(amount) AS total_amount
FROM dbo.sales
GROUP BY region_id;
GO
CREATE UNIQUE CLUSTERED INDEX ix_v_sales_by_region ON dbo.v_sales_by_region (region_id);
GO
```

## Practical guidelines

- **Design one rich rollup instead of many narrow MVs:** A single MV grouped by 2–4 commonly filtered dimensions and
  containing `COUNT(*)`, `SUM(...)`, `MIN(...)`, `MAX(...)`, and sketch details can transparently answer dozens of
  coarser dashboard queries while incurring only one incremental maintenance step per write.
- **Use `realtime` (`ON QUERY COMPUTATION`) for hot aggregate keys:** If many concurrent OLTP writers update rows that
  map to the same small set of MV groups (such as a global counter or a few hot buckets), `fast_on_statement` /
  `fast_on_commit` serialize on the same MV leaf key (`40001` retry). Switching to `realtime` appends deltas to a
  sharded delta tree and eliminates write-write conflicts on the MV.
- **Batch bulk loads:** During large `COPY` or multi-row `INSERT` loads, `fast_on_statement` and `fast_on_commit`
  aggregate the batch's deltas before applying them to the MV, keeping ingest overhead low. For massive one-time loads,
  you can also create the MV afterward (or load into a `demand` MV and run `REFRESH MATERIALIZED VIEW`).
- **Index your MVs when they are large:** Because an MV is a B+tree, you can add secondary B+tree indexes or
  [data skipping indexes](skipping-indexes.md) on a high-cardinality materialized view just like on a base table.
- **Catalog and lifecycle:** Inspect materialized views via `pg_matviews` / `pg_class` (`relkind = 'm'`) in PostgreSQL,
  or `USER_MVIEWS` / `ALL_MVIEWS` / `DBA_MVIEWS` and `USER_MVIEW_LOGS` in Oracle. Dropping a base table, referenced
  column, or upstream MV is refused (`2BP01`) unless `CASCADE` is specified.
