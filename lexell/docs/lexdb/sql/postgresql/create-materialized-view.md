# CREATE MATERIALIZED VIEW

Creates a materialized view: a query whose result is stored on disk in its own B+tree, with optional indexes and
either on-demand atomic refresh or incremental maintenance.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18 (with optional lexdb incremental-refresh parameters).

## Syntax

```
CREATE MATERIALIZED VIEW [ IF NOT EXISTS ] name [ ( column_name [, ...] ) ]
    [ USING method ]
    [ WITH ( storage_parameter = value [, ...] ) ]
    [ REFRESH [ FAST | COMPLETE | FORCE ] [ ON { DEMAND | COMMIT | STATEMENT } ] ]
    [ { ENABLE | DISABLE } QUERY REWRITE ]
    [ { ENABLE | DISABLE } ON QUERY COMPUTATION ]
    [ TABLESPACE tablespace_name ]
    AS query
    [ WITH [ NO ] DATA ]

REFRESH MATERIALIZED VIEW [ CONCURRENTLY ] name
    [ FAST | COMPLETE | FORCE ]
    [ WITH [ NO ] DATA ]

ALTER MATERIALIZED VIEW [ IF EXISTS ] name RENAME TO new_name
ALTER MATERIALIZED VIEW [ IF EXISTS ] name RENAME [ COLUMN ] column_name TO new_column_name
ALTER MATERIALIZED VIEW [ IF EXISTS ] name OWNER TO new_owner
ALTER MATERIALIZED VIEW [ IF EXISTS ] name
    [ REFRESH [ FAST | COMPLETE | FORCE ] [ ON { DEMAND | COMMIT | STATEMENT } ] ]
    [ { ENABLE | DISABLE } QUERY REWRITE ]
    [ { ENABLE | DISABLE } ON QUERY COMPUTATION ]

DROP MATERIALIZED VIEW [ IF EXISTS ] name [, ...] [ CASCADE | RESTRICT ]
```

## Arguments

`IF NOT EXISTS`
: Emits a notice instead of an error if a relation with the same name already exists.

*column_name*
: Names for the materialized view's columns, from the left. Without them, the columns take the query's output names.

`WITH ( refresh = '...' [, query_rewrite = true | false ] )`
: Optional lexdb extension controlling maintenance mode (Oracle-style `REFRESH ...` clauses are also accepted):
  - `'demand'` (default): manual refresh via `REFRESH MATERIALIZED VIEW`.
  - `'fast_on_statement'`: synchronously maintained on each DML statement over the base table(s) using $O(\Delta)$
    signed Z-set deltas.
  - `'fast_on_commit'` (or `'incremental'`): incrementally maintained at transaction `COMMIT` (not visible to queries
    inside the uncommitted transaction; savepoint-safe).
  - `'complete_on_commit'`: atomically rebuilt at `COMMIT` whenever a base table changes.
  - `'force_on_commit'` / `'force_on_statement'`: uses incremental `FAST` maintenance when the query shape is eligible
    and falls back to atomic `COMPLETE` refresh otherwise.
  - `'realtime'` (or `ENABLE ON QUERY COMPUTATION`): appends signed deltas to a contention-free sharded companion
    delta tree (avoiding hot-leaf `40001` write-write conflicts across concurrent writers), merges base + deltas on
    read in the reader's MVCC snapshot, and folds deltas into the base tree automatically in the background (or on
    `REFRESH MATERIALIZED VIEW name FAST`). Set `LEXDB_MV_FOLD=off` to disable background folding.

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
  (`COUNT(*)`, `COUNT(expr)`, `SUM`, `AVG`, `VAR_POP`, `VAR_SAMP`, `VARIANCE`, `STDDEV_POP`, `STDDEV_SAMP`, `STDDEV`,
  `BOOL_AND`/`EVERY`, `BOOL_OR`, `BIT_XOR`, `MIN`, `MAX`, `APPROX_COUNT_DISTINCT`, `APPROX_COUNT_DISTINCT_DETAIL`,
  `APPROX_PERCENTILE`, `APPROX_PERCENTILE_DETAIL`, including `FILTER (WHERE ...)`), and multi-table inner
  equi-joins (projection or grouped aggregate) across `INSERT`, `UPDATE`, `DELETE`, `COPY FROM`, `MERGE`, and
  `TRUNCATE`.
- Sketch aggregates (`APPROX_COUNT_DISTINCT` via HyperLogLog++, `APPROX_PERCENTILE` via Dunning merging t-digest)
  merge associatively in $O(\Delta)$ on appends and automatically re-probe affected groups on deletes.
- Dropping a base table or column referenced by a materialized view is refused (`2BP01`) unless `CASCADE` is given.

## Differences from PostgreSQL

- PostgreSQL has only on-demand `REFRESH MATERIALIZED VIEW`; lexdb adds incremental `FAST` maintenance (`WITH
  (refresh = 'fast_on_commit' | 'fast_on_statement')` and Oracle-style `REFRESH` clauses).
- `REFRESH MATERIALIZED VIEW CONCURRENTLY` atomically swaps a freshly built copy-on-write B+tree root instead of
  diffing and updating rows in place.

## Examples

<!--setup: postgresql
CREATE TABLE sales (id int PRIMARY KEY, dept text, amt int, paid boolean);
INSERT INTO sales VALUES (1, 'a', 100, true), (2, 'a', 200, true), (3, 'b', 50, false);
-->

The examples use one table:

```sql
CREATE TABLE sales (id int PRIMARY KEY, dept text, amt int, paid boolean);
INSERT INTO sales VALUES (1, 'a', 100, true), (2, 'a', 200, true), (3, 'b', 50, false);
```

### A. Snapshot materialized view, `WITH NO DATA`, and `CONCURRENTLY`

<!-- example: postgresql -->
```sql
CREATE MATERIALIZED VIEW mv_sales AS
SELECT dept, count(*) AS n, sum(amt) AS total FROM sales GROUP BY dept
WITH NO DATA;
SELECT * FROM mv_sales;
REFRESH MATERIALIZED VIEW mv_sales;
SELECT * FROM mv_sales ORDER BY dept;
CREATE UNIQUE INDEX mv_sales_dept_idx ON mv_sales (dept);
INSERT INTO sales VALUES (4, 'c', 300, true);
REFRESH MATERIALIZED VIEW CONCURRENTLY mv_sales;
SELECT * FROM mv_sales ORDER BY dept;
```

```text
CREATE MATERIALIZED VIEW
ERROR:  materialized view "mv_sales" has not been populated
HINT:  Use the REFRESH MATERIALIZED VIEW command.
REFRESH MATERIALIZED VIEW
 dept | n | total
------+---+-------
 a    | 2 |   300
 b    | 1 |    50
(2 rows)

CREATE INDEX
INSERT 0 1
REFRESH MATERIALIZED VIEW
 dept | n | total
------+---+-------
 a    | 2 |   300
 b    | 1 |    50
 c    | 1 |   300
(3 rows)
```

### B. Incremental materialized view with algebraic and sketch aggregates

<!-- example: postgresql -->
```sql
CREATE MATERIALIZED VIEW mv_live WITH (refresh = 'fast_on_statement') AS
SELECT dept,
       count(*) AS n,
       sum(amt) AS total,
       min(amt) AS lo,
       max(amt) AS hi,
       bool_and(paid) AS all_paid,
       approx_count_distinct(amt) AS distinct_amts,
       approx_percentile(amt, 0.5) AS p50
FROM sales
GROUP BY dept;
SELECT * FROM mv_live ORDER BY dept;
INSERT INTO sales VALUES (5, 'a', 150, true), (6, 'b', 250, true);
DELETE FROM sales WHERE id = 1;
SELECT * FROM mv_live ORDER BY dept;
```

```text
SELECT 3
 dept | n | total | lo  | hi  | all_paid | distinct_amts | p50
------+---+-------+-----+-----+----------+---------------+-----
 a    | 2 |   300 | 100 | 200 | t        |             2 | 150
 b    | 1 |    50 |  50 |  50 | f        |             1 |  50
 c    | 1 |   300 | 300 | 300 | t        |             1 | 300
(3 rows)

INSERT 0 2
DELETE 1
 dept | n | total | lo  | hi  | all_paid | distinct_amts | p50
------+---+-------+-----+-----+----------+---------------+-----
 a    | 2 |   350 | 150 | 200 | t        |             2 | 175
 b    | 2 |   300 |  50 | 250 | f        |             2 | 150
 c    | 1 |   300 | 300 | 300 | t        |             1 | 300
(3 rows)
```

### C. Real-time materialized view (`refresh = 'realtime'` / `ON QUERY COMPUTATION`)

<!-- example: postgresql -->
```sql
CREATE MATERIALIZED VIEW mv_rt WITH (refresh = 'realtime') AS
SELECT dept, count(*) AS n, sum(amt) AS total FROM sales GROUP BY dept;
INSERT INTO sales VALUES (7, 'a', 50, true);
SELECT * FROM mv_rt ORDER BY dept;
REFRESH MATERIALIZED VIEW mv_rt FAST;
SELECT * FROM mv_rt ORDER BY dept;
```

```text
SELECT 3
INSERT 0 1
 dept | n | total
------+---+-------
 a    | 3 |   400
 b    | 2 |   300
 c    | 1 |   300
(3 rows)

REFRESH MATERIALIZED VIEW
 dept | n | total
------+---+-------
 a    | 3 |   400
 b    | 2 |   300
 c    | 1 |   300
(3 rows)
```

### D. Catalog views and `ALTER` / `DROP`

<!-- example: postgresql -->
```sql
SELECT matviewname, hasindexes, ispopulated FROM pg_matviews ORDER BY matviewname;
ALTER MATERIALIZED VIEW mv_sales RENAME TO mv_sales_snap;
DROP MATERIALIZED VIEW mv_sales_snap, mv_live, mv_rt;
```

```text
 matviewname | hasindexes | ispopulated
-------------+------------+-------------
 mv_live     | f          | t
 mv_rt       | f          | t
 mv_sales    | t          | t
(3 rows)

ALTER MATERIALIZED VIEW
DROP MATERIALIZED VIEW
```

## See also

[CREATE VIEW](create-view.md), [Aggregate functions](functions-aggregate.md), [Catalog views](catalog-views-sequences.md)
