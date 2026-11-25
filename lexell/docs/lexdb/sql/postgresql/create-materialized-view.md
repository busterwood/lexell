# CREATE MATERIALIZED VIEW

Creates a materialized view: a query whose result is stored on disk in its own B+tree, with optional indexes and
either on-demand atomic refresh or incremental maintenance.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18 (with optional lexdb incremental-refresh storage parameters).

## Syntax

```
CREATE MATERIALIZED VIEW [ IF NOT EXISTS ] name [ ( column_name [, ...] ) ]
    [ USING method ]
    [ WITH ( storage_parameter = value [, ...] ) ]
    [ TABLESPACE tablespace_name ]
    AS query
    [ WITH [ NO ] DATA ]

REFRESH MATERIALIZED VIEW [ CONCURRENTLY ] name
    [ WITH [ NO ] DATA ]

ALTER MATERIALIZED VIEW [ IF EXISTS ] name RENAME TO new_name
ALTER MATERIALIZED VIEW [ IF EXISTS ] name RENAME [ COLUMN ] column_name TO new_column_name
ALTER MATERIALIZED VIEW [ IF EXISTS ] name OWNER TO new_owner

DROP MATERIALIZED VIEW [ IF EXISTS ] name [, ...] [ CASCADE | RESTRICT ]
```

## Arguments

`IF NOT EXISTS`
: Emits a notice instead of an error if a relation with the same name already exists.

*column_name*
: Names for the materialized view's columns, from the left. Without them, the columns take the query's output names.

`WITH ( refresh = '...' [, query_rewrite = true | false ] )`
: Optional lexdb extension controlling maintenance mode:
  - `'demand'` (default): manual refresh via `REFRESH MATERIALIZED VIEW`.
  - `'fast_on_statement'`: synchronously maintained on each DML statement over the base table(s) using $O(\Delta)$
    signed Z-set deltas.
  - `'fast_on_commit'` (or `'incremental'`): incrementally maintained at transaction `COMMIT` (not visible to queries
    inside the uncommitted transaction; savepoint-safe).
  - `'complete_on_commit'`: atomically rebuilt at `COMMIT` whenever a base table changes.
  - `'force_on_commit'` / `'force_on_statement'`: uses incremental `FAST` maintenance when the query shape is eligible
    and falls back to atomic `COMPLETE` refresh otherwise.

`WITH [ NO ] DATA`
: `WITH DATA` (the default) populates the view immediately. `WITH NO DATA` creates it empty; reading it before the
  first `REFRESH MATERIALIZED VIEW` raises SQLSTATE `55000`.

`CONCURRENTLY`
: On `REFRESH MATERIALIZED VIEW`, requires the view to be populated and to have a unique index with no `WHERE` clause
  (SQLSTATE `55000` otherwise). lexdb builds the refreshed data into a brand-new B+tree and swaps the root atomically
  without blocking concurrent readers.

## Remarks

- Materialized views are backed by ordinary lexdb B+trees, so `CREATE [UNIQUE] INDEX`, `ANALYZE`, snapshots, WAL, and
  crash recovery work identically to tables.
- Direct DML (`INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`) and `DROP TABLE` / `DROP VIEW` on a materialized view are
  refused (`42809`).
- `pg_matviews` lists every materialized view (`schemaname`, `matviewname`, `matviewowner`, `hasindexes`,
  `ispopulated`, `definition`), and `pg_class` lists it with `relkind = 'm'` (excluded from `pg_tables` and
  `information_schema.tables`).
- Incremental (`FAST`) maintenance supports single-table filter/projection views, `GROUP BY` and global aggregates
  (`COUNT(*)`, `COUNT(expr)`, `SUM(expr)`, `AVG(expr)`, including `FILTER (WHERE ...)`), and multi-table inner
  equi-joins (projection or grouped aggregate) across `INSERT`, `UPDATE`, `DELETE`, `COPY FROM`, `MERGE`, and
  `TRUNCATE`.
- Dropping a base table or column referenced by a materialized view is refused (`2BP01`) unless `CASCADE` is given.

## Examples

### A. Snapshot materialized view, `WITH NO DATA`, and `CONCURRENTLY`

```sql
CREATE TABLE sales (id int PRIMARY KEY, dept text, amt int);
INSERT INTO sales VALUES (1, 'a', 100), (2, 'a', 200), (3, 'b', 50);

CREATE MATERIALIZED VIEW mv_sales AS
SELECT dept, count(*) AS n, sum(amt) AS total FROM sales GROUP BY dept;

SELECT * FROM mv_sales ORDER BY dept;

CREATE UNIQUE INDEX mv_sales_dept_idx ON mv_sales (dept);
INSERT INTO sales VALUES (4, 'c', 300);
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sales;
SELECT * FROM mv_sales ORDER BY dept;
```

### B. Incremental materialized view (`fast_on_commit`)

```sql
CREATE MATERIALIZED VIEW mv_live WITH (refresh = 'fast_on_commit') AS
SELECT dept, count(*) AS n, sum(amt) AS total, avg(amt) AS avg_amt
FROM sales
GROUP BY dept;

INSERT INTO sales VALUES (5, 'a', 150);
UPDATE sales SET amt = 75 WHERE id = 3;
SELECT * FROM mv_live ORDER BY dept;
```
