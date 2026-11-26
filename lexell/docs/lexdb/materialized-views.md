# Materialized views and transparent query rewrite

A materialized view is a precomputed query result stored on disk like a table. Instead of rescanning millions of rows
every time a dashboard, report, or API endpoint asks for a sum, count, or join, lexdb reads the small precomputed
summary in a millisecond or two.

In traditional databases (like PostgreSQL), materialized views are static snapshots: after data changes, you have to
manually run `REFRESH MATERIALIZED VIEW` and recompute the whole view from scratch, and every application query has to
be rewritten to name the materialized view explicitly.

lexdb removes both of those limitations:

1. **Automatic incremental updates (`FAST`):** When rows are inserted, updated, deleted, or bulk-loaded into the base
   table, lexdb updates only the affected summary rows — typically in **under 1 ms** instead of rescanning millions of
   rows.
2. **Transparent query rewrite (`ENABLE QUERY REWRITE`):** Your application keeps running ordinary `SELECT` queries
   against the base tables. When the planner sees that a fresh materialized view already has the answer (or can be
   rolled up into the answer), it rewrites the query onto the materialized view automatically — **zero application code
   changes required**.

All three doors — PostgreSQL, Oracle (TNS), and SQL Server (TDS) — share the same engine. A materialized view created
from one door is automatically kept up to date for writes from every door and accelerates queries from every door.

## See it in action: one view, five faster queries

Suppose you have a 10-million-row `orders` table and a small `regions` dimension table. You create **one** moderately
detailed rollup materialized view:

```sql
CREATE MATERIALIZED VIEW mv_orders_daily
WITH (refresh = 'fast_on_statement', query_rewrite = true) AS
SELECT order_date,
       region_id,
       status,
       COUNT(*) AS order_count,
       SUM(amount) AS total_amount,
       MIN(amount) AS min_amount,
       MAX(amount) AS max_amount
FROM orders
GROUP BY order_date, region_id, status;
```

Even though your application never mentions `mv_orders_daily`, **all five** of these ordinary queries against `orders`
are transparently rewritten onto `mv_orders_daily` and return exact results in milliseconds:

```sql
-- 1. Coarser rollup (drops order_date and status):
SELECT region_id, SUM(amount), AVG(amount)
FROM orders
GROUP BY region_id;

-- 2. Filtered slice (WHERE predicates pushed onto the MV):
SELECT order_date, SUM(amount)
FROM orders
WHERE order_date BETWEEN DATE '2026-11-01' AND DATE '2026-11-30'
  AND status = 'paid'
GROUP BY order_date;

-- 3. Derived date grouping (DATE_TRUNC / EXTRACT over an MV key):
SELECT DATE_TRUNC('month', order_date) AS month, COUNT(*), SUM(amount)
FROM orders
GROUP BY DATE_TRUNC('month', order_date);

-- 4. Exact COUNT(DISTINCT) over an MV grouping key:
SELECT region_id, COUNT(DISTINCT order_date) AS active_days
FROM orders
GROUP BY region_id;

-- 5. Dimension join-back (joins orders to a table not in the MV):
SELECT r.region_name, SUM(o.amount)
FROM orders o
JOIN regions r ON r.id = o.region_id
WHERE o.status = 'paid'
GROUP BY r.region_name;
```

To verify that a query is using your materialized view, run `EXPLAIN` on the base-table query — you will see
`mv_orders_daily` in the scan plan instead of `orders`. You can also test with `SET query_rewrite_enabled = off` vs
`on` to compare timings and confirm identical output.

## When to use a materialized view vs an index vs a skipping index

lexdb gives you three ways to speed up reads. Each solves a different problem:

| What your workload is doing | Best tool | Why |
|---|---|---|
| Looking up a few specific rows by key (`WHERE order_id = 42` or `WHERE email = '...'`) | **Regular B+tree `CREATE INDEX`** | Jumps straight to exact rows in sub-millisecond time |
| Ad-hoc filtering over arbitrary columns or `LIKE '%google%'` on a wide table | **[Data skipping index](skipping-indexes.md)** | Tiny footprint, zero write overhead, skips non-matching blocks |
| Repeated aggregations, dashboards, KPIs, and rollups (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `GROUP BY`, joins) | **Materialized view with `ENABLE QUERY REWRITE`** | Turns 100–600 ms full-table aggregations into 0.5–5 ms lookups |

You can combine them freely — for example, you can put a B+tree index or skipping index on a large materialized view
just as you would on a regular table.

## How big is the impact?

All figures below are single-core measurements from [PERFORMANCE.md](../../../PERFORMANCE.md):

| Benchmark | Without MVs | With MVs (unmodified queries) | Incremental write cost |
|---|---:|---:|---|
| **ClickBench 1M** (43 queries, 105-column `hits` table) | 14.10 s total (0.68× PG 1-core) | **9.07 s total** — 2.26 s faster than **4-core** PostgreSQL (11.33 s) on one core; 21 queries rewritten; geomean **0.10×** PG1 / **0.21×** PG4 | 1 / 100 new rows maintaining all 8 MVs live: **6.51 / 10.34 ms** (total initial build: 6.01 s) |
| **35 Analytic Queries** (1M rows) | geomean 0.56× PG1 / 0.91× PG4 | 9 aggregate & join queries drop from 8–91 ms to **3–4 ms** (geomean **0.31×** PG1 / **0.49×** PG4) | 1 / 100 / 1,000 new rows maintaining all 4 MVs live: **4.40 / 7.09 / 25.90 ms** vs PG `REFRESH` **758 / 264 ms** |
| **Dedicated 1M-row event table** (grouped / sketch / 3-level DAG) | 23.7 ms grouped scan, 234.4 ms sketch scan | **0.18 ms** (132×) / **0.56 ms** (419×) / **0.07 ms** | 1-row `FAST` update: **0.66 / 0.47 / 0.43 ms** vs PG `REFRESH` **60–369 ms** (100×–750× less work) |

## Which refresh mode should I choose?

Pick the refresh mode based on how fresh your reads need to be and how many writers update the same summary rows at
once:

### 1. `fast_on_statement` — the everyday default for live dashboards
Every `INSERT`, `UPDATE`, `DELETE`, `COPY`, or `MERGE` immediately updates the materialized view in the same statement.
Reads always see the latest data — including uncommitted changes inside your own transaction.

- **Use when:** You want always-fresh dashboards and reports with moderate write concurrency, or read-your-writes
  consistency inside transactions.

### 2. `fast_on_commit` (alias `incremental`) — batching multi-statement transactions
Changes are accumulated during a transaction and applied to the materialized view once at `COMMIT` (and cleanly
discarded on `ROLLBACK` or `ROLLBACK TO SAVEPOINT`).

- **Use when:** Your application runs multi-statement OLTP transactions that touch several rows before committing, and
  you don't need to query the MV for uncommitted rows mid-transaction.

### 3. `realtime` (`ENABLE ON QUERY COMPUTATION`) — high-concurrency hot keys
Suppose 16 concurrent threads all insert rows into `orders` at the same time, and your materialized view maintains a
single global total or a handful of active status buckets. With `fast_on_statement` or `fast_on_commit`, those 16
writers all compete to update the *same* summary row in the MV.

With `realtime`, writers never touch the shared summary row. Instead, each writer appends its change to a
contention-free companion delta tree. When a query reads the MV, lexdb merges the base summary with the pending deltas
on the fly inside the reader's MVCC snapshot — so reads are still 100% up to date — and a background worker folds the
deltas back into the base MV automatically (or on demand via `REFRESH MATERIALIZED VIEW name FAST`).

- **Use when:** Many concurrent OLTP writers frequently hit the same small set of MV groups (e.g., global totals,
  per-status counts, or hot tenant buckets).

### 4. `demand` — periodic snapshots and batch ETL
The materialized view is only refreshed when you explicitly run `REFRESH MATERIALIZED VIEW` (or `DBMS_MVIEW.REFRESH`
in Oracle). While the base table has newer changes, lexdb marks the view stale and automatically **skips** it during
transparent query rewrite so queries never return out-of-date answers.

- **Use when:** You load data in scheduled batches and want zero write-path cost during ingest, refreshing once at the
  end of the batch. Add `CONCURRENTLY` (`REFRESH MATERIALIZED VIEW CONCURRENTLY name`) to rebuild into a brand-new
  B+tree and swap it atomically without blocking readers (requires a unique index with no `WHERE` clause).

### 5. `complete_on_commit` and `force_on_commit` / `force_on_statement`
- **`complete_on_commit`:** Rebuilds the whole MV atomically at `COMMIT` whenever the base table changes. Handy for
  small tables with complex queries (like window functions) that cannot be incrementally maintained.
- **`force_on_commit` / `force_on_statement`:** Uses incremental `FAST` maintenance if the query shape is eligible, and
  automatically falls back to `COMPLETE` otherwise.

### Quick comparison

| Mode (PostgreSQL `WITH` / Oracle & T-SQL clause) | When updated | Always fresh? | Best for |
|---|---|---|---|
| `'fast_on_statement'` / `REFRESH FAST ON STATEMENT` | End of every DML statement | Yes (even mid-tx) | Most live dashboards & interactive apps |
| `'fast_on_commit'` / `REFRESH FAST ON COMMIT` | At transaction `COMMIT` | Yes (committed) | Multi-statement OLTP transactions |
| `'realtime'` / `ENABLE ON QUERY COMPUTATION` | Merged on read; folded in background | Yes (in snapshot) | Concurrent writers hitting hot MV keys |
| `'demand'` / `REFRESH ... ON DEMAND` | Manual `REFRESH` | After refresh | Scheduled batch ETL & periodic snapshots |
| `'complete_on_commit'` / `REFRESH COMPLETE ON COMMIT` | Full rebuild at `COMMIT` | Yes (committed) | Small tables with non-`FAST` queries |
| `'force_on_commit'` / `'force_on_statement'` | `FAST` if eligible, else `COMPLETE` | Yes | General definitions with automatic fallback |

## Three high-leverage patterns

### Pattern 1: One rich rollup instead of ten narrow views
Every extra materialized view adds a little work to writes. Instead of creating separate views for "sales by day",
"sales by region", "sales by status", and "grand total sales", create **one** MV grouped by `(sale_date, region_id,
status)` with `COUNT(*)`, `SUM(...)`, `MIN(...)`, and `MAX(...)`. Transparent query rewrite automatically rolls that
single view up to answer all four queries while writes only maintain one view.

### Pattern 2: Fast distinct counts and percentiles over millions of rows (sketches)
Exact `COUNT(DISTINCT user_id)` and exact medians over millions of rows are expensive to recompute on every write.
lexdb supports composable approximate sketches that update incrementally on every write in fractions of a millisecond:

- **Distinct counts (HyperLogLog++):** `APPROX_COUNT_DISTINCT(user_id)` — or store the reusable sketch state with
  `APPROX_COUNT_DISTINCT_DETAIL(user_id)` and combine across groups/days with `APPROX_COUNT_DISTINCT_AGG(sketch)`.
- **Percentiles (t-digest):** `APPROX_PERCENTILE(latency_ms, 0.95)` — or store reusable state with
  `APPROX_PERCENTILE_DETAIL(latency_ms)` and merge with `APPROX_PERCENTILE_AGG(sketch, 0.95)`.

### Pattern 3: Cascading rollup hierarchies (MV on top of MV)
A materialized view can query another materialized view, forming a multi-level rollup chain:

```text
events (100M rows)
  └── mv_hourly  (GROUP BY hour, region; includes APPROX_COUNT_DISTINCT_DETAIL(user_id))
        └── mv_daily   (GROUP BY day, region; merges via APPROX_COUNT_DISTINCT_AGG)
              └── mv_total   (grand totals: 1 row)
```

When new rows arrive in `events`, lexdb propagates the small incremental delta down the chain (`events → mv_hourly →
mv_daily → mv_total`) automatically in topological order — keeping hourly, daily, and all-time dashboards current in
sub-millisecond time.

## Syntax across the three doors

### PostgreSQL door

Full reference: [CREATE MATERIALIZED VIEW (PostgreSQL)](sql/postgresql/create-materialized-view.md).

```sql
-- Incremental MV with transparent query rewrite:
CREATE MATERIALIZED VIEW mv_sales_daily
WITH (refresh = 'fast_on_statement', query_rewrite = true) AS
SELECT sale_date, region_id,
       COUNT(*) AS cnt,
       SUM(amount) AS total_amount,
       APPROX_COUNT_DISTINCT(customer_id) AS approx_customers
FROM sales
GROUP BY sale_date, region_id;

-- Contention-free real-time MV for hot keys:
CREATE MATERIALIZED VIEW mv_hot_counters
WITH (refresh = 'realtime', query_rewrite = true) AS
SELECT bucket_id, COUNT(*) AS cnt, SUM(val) AS tot
FROM hot_events
GROUP BY bucket_id;

-- Toggle transparent rewrite per session (default: on):
SET query_rewrite_enabled = on;   -- or off
```

### Oracle (TNS) door

Full reference: [CREATE MATERIALIZED VIEW (Oracle)](sql/oracle/create-materialized-view.md).

```sql
CREATE MATERIALIZED VIEW mv_sales_daily
    BUILD IMMEDIATE
    REFRESH FAST ON COMMIT
    ENABLE QUERY REWRITE
AS
SELECT sale_date, region_id, COUNT(*) AS cnt, SUM(amount) AS total_amount
FROM sales
GROUP BY sale_date, region_id;

-- Real-time on-query delta merging (even on ON DEMAND views):
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

Control per session with `ALTER SESSION SET QUERY_REWRITE_ENABLED = TRUE | FALSE | FORCE;`.

### SQL Server (TDS) door

Full reference: [CREATE MATERIALIZED VIEW (Transact-SQL)](sql/tsql/create-materialized-view.md) and
[CREATE VIEW (Transact-SQL)](sql/tsql/create-view.md). SQL Server supports both cross-door `CREATE MATERIALIZED VIEW`
and native indexed views (`WITH SCHEMABINDING` + `CREATE UNIQUE CLUSTERED INDEX`):

```sql
-- Cross-door incremental MV with transparent rewrite:
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

## Reference & operational notes

### What query shapes support `FAST` incremental maintenance?
- Single-table filter and projection views (`SELECT ... FROM t WHERE ...`)
- Grouped and global aggregates: `COUNT(*)`, `COUNT(expr)`, `SUM`, `AVG`, `MIN`, `MAX`, `VAR_POP`, `VAR_SAMP`,
  `VARIANCE`, `STDDEV_POP`, `STDDEV_SAMP`, `STDDEV`, `BOOL_AND`/`EVERY`, `BOOL_OR`, `BIT_XOR`, and HyperLogLog++ /
  t-digest sketches — including `FILTER (WHERE ...)` clauses
- Multi-table inner equi-joins (both projection views and grouped aggregate views)
- Works across `INSERT`, `UPDATE`, `DELETE`, `COPY`, `MERGE`, and `TRUNCATE`. (Note: deleting the current `MIN` or
  `MAX` row in a group automatically re-probes that group from the base table so results stay exact.)

### What transparent query rewrite handles (and when it safely skips an MV)
- **Supported rewrites:** exact/subset projections, `HAVING`, `ORDER BY`/`LIMIT`, pushed `WHERE` predicates (`=`,
  `<`/`<=`/`>`/`>=`, `BETWEEN`, `IN`, `<>`, `IS NOT NULL`), coarser and derived `GROUP BY` (`DATE_TRUNC`, `EXTRACT`),
  dimension join-back (including `LEFT JOIN`), exact `COUNT`/`SUM`/`AVG(DISTINCT)` over MV keys, algebraic and sketch
  rollups (including from hidden internal MV state), and oversized `GROUP BY` text keys (`>512` bytes, fingerprinted
  automatically).
- **Cost-based selection:** When several MVs match a query, lexdb automatically picks the cheapest fresh candidate.
- **Zero stale reads:** `ON DEMAND` views that have become stale (without `ON QUERY COMPUTATION`), `WITH NO DATA` /
  `BUILD DEFERRED` views that haven't been populated yet, and `ON COMMIT` views during a transaction that modified the
  base table are automatically bypassed for correctness.

### Day-to-day operations
- **Bulk loading:** During large `COPY` or multi-row `INSERT` loads, `fast_on_statement` and `fast_on_commit` aggregate
  the batch's changes before applying them to the MV. For huge one-time backfills, you can also load the table first
  and create the MV afterward.
- **Background folding:** Real-time (`ON QUERY COMPUTATION`) views fold deltas into their base B+tree automatically in
  the background. Set `LEXDB_MV_FOLD=off` if you prefer to fold explicitly with `REFRESH MATERIALIZED VIEW name FAST`.
- **Inspecting and dropping:** List MVs via `pg_matviews` / `pg_class` (`relkind = 'm'`) in PostgreSQL, or
  `USER_MVIEWS` / `ALL_MVIEWS` / `DBA_MVIEWS` and `USER_MVIEW_LOGS` in Oracle. Dropping a base table, referenced
  column, or upstream MV is refused (`2BP01`) unless `CASCADE` is given.
