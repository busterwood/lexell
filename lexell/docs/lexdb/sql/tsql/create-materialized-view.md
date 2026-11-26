# CREATE MATERIALIZED VIEW (Transact-SQL)

Creates a materialized view storing query results on disk, supporting all lexdb refresh modes (`COMPLETE`, `FAST`,
`FORCE`) and timings (`ON DEMAND`, `ON COMMIT`, `ON STATEMENT`), alongside SQL Server's native indexed views
(`CREATE VIEW ... WITH SCHEMABINDING` + `CREATE UNIQUE CLUSTERED INDEX`).

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025 indexed views + lexdb cross-door materialized views.

## Syntax

```
CREATE MATERIALIZED VIEW [ IF NOT EXISTS ] [ schema_name . ] mview_name [ ( column [ ,...n ] ) ]
    [ BUILD { IMMEDIATE | DEFERRED } ]
    [ REFRESH [ FAST | COMPLETE | FORCE ] [ ON { DEMAND | COMMIT | STATEMENT } ] ]
    [ { ENABLE | DISABLE } QUERY REWRITE ]
    [ { ENABLE | DISABLE } ON QUERY COMPUTATION ]
    [ WITH ( refresh = 'demand' | 'fast_on_commit' | 'fast_on_statement' | 'realtime' | 'complete_on_commit' [, query_rewrite = true | false ] ) ]
    AS select_statement
    [ WITH [ NO ] DATA ]

REFRESH MATERIALIZED VIEW [ CONCURRENTLY ] [ schema_name . ] mview_name
    [ FAST | COMPLETE | FORCE ] [ WITH [ NO ] DATA ]

ALTER MATERIALIZED VIEW [ IF EXISTS ] [ schema_name . ] mview_name
    { RENAME TO new_name
    | REFRESH [ FAST | COMPLETE | FORCE ] [ ON { DEMAND | COMMIT | STATEMENT } ]
    | { ENABLE | DISABLE } QUERY REWRITE
    | { ENABLE | DISABLE } ON QUERY COMPUTATION
    | COMPILE }

DROP MATERIALIZED VIEW [ IF EXISTS ] [ schema_name . ] mview_name [ ,...n ] [ CASCADE | RESTRICT ]
```

## Remarks

- All three lexdb doors (PostgreSQL, Oracle, and SQL Server) share the same materialized view engine and accept the
  full set of build, refresh, and rewrite options.
- For SQL Server's native indexed view syntax (`CREATE VIEW ... WITH SCHEMABINDING` + `CREATE UNIQUE CLUSTERED INDEX`),
  see [CREATE VIEW](create-view.md).
- Incremental (`FAST`) maintenance supports single-table filter/projection views, `GROUP BY` and global aggregates
  (`COUNT(*)`, `COUNT(expr)`, `SUM`, `AVG`, `VAR_POP`, `VAR_SAMP`, `STDDEV_POP`, `STDDEV_SAMP`, `BOOL_AND`, `BOOL_OR`,
  `BIT_XOR`, `MIN`, `MAX`, `APPROX_COUNT_DISTINCT`, `APPROX_COUNT_DISTINCT_DETAIL`, `APPROX_PERCENTILE`,
  `APPROX_PERCENTILE_DETAIL`), and multi-table inner equi-joins across `INSERT`, `UPDATE`, `DELETE`, `MERGE`, and
  `TRUNCATE`.
- Composable HyperLogLog++ and t-digest sketch aggregates merge associatively in $O(\Delta)$ on appends and re-probe
  affected groups on deletes.
- Real-time materialized views (`WITH (refresh = 'realtime')` or `ENABLE ON QUERY COMPUTATION`) append signed deltas to
  a contention-free companion delta tree, merge deltas on read in the reader's MVCC snapshot, and fold into the base
  tree in the background or on `REFRESH MATERIALIZED VIEW ... FAST`.
- **Cascading materialized views:** A materialized view may query another materialized view (forming multi-level rollup
  DAGs, including cascading sketch rollups from `APPROX_COUNT_DISTINCT_DETAIL` / `APPROX_PERCENTILE_DETAIL` to
  `APPROX_COUNT_DISTINCT_AGG` / `APPROX_PERCENTILE_AGG`), with incremental deltas propagating topologically in
  $O(\Delta)$.
- **Automatic query rewrite:** Materialized views created with `ENABLE QUERY REWRITE` (or `WITH (query_rewrite = true)`)
  automatically accelerate eligible `SELECT` queries against their base table(s) — supporting exact matches, `HAVING`,
  subsumed `WHERE` predicates (including range, `BETWEEN`, `IN`, `<>`, and `IS NOT NULL`), coarser and derived
  `GROUP BY` expressions, join-back to extra dimension tables (including `LEFT JOIN`), exact
  `COUNT(DISTINCT)`/`SUM(DISTINCT)`/`AVG(DISTINCT)` rollups over MV keys, and
  `COUNT`/`SUM`/`AVG`/`MIN`/`MAX`/`VAR_*`/`STDDEV_*`/sketch rollups, while skipping stale `ON DEMAND` views and
  uncommitted `ON COMMIT` changes. Oversized `GROUP BY` keys exceeding 512 bytes are fingerprinted automatically.
  Control per session with `SET query_rewrite_enabled = on | off` (default `on`).

## Examples

<!--setup: tsql
CREATE TABLE dbo.sales (id int PRIMARY KEY, dept_id int, amount int);
INSERT dbo.sales VALUES (1, 1, 100), (2, 1, 200), (3, 2, 50);
-->

The examples use one table:

```sql
CREATE TABLE dbo.sales (id int PRIMARY KEY, dept_id int, amount int);
INSERT dbo.sales VALUES (1, 1, 100), (2, 1, 200), (3, 2, 50);
```

### A. Native SQL Server indexed view (`WITH SCHEMABINDING` + `UNIQUE CLUSTERED INDEX`)

<!-- example: tsql -->
```sql
CREATE VIEW dbo.v_sales WITH SCHEMABINDING AS
SELECT dept_id, COUNT(*) AS cnt, SUM(amount) AS tot FROM dbo.sales GROUP BY dept_id;
GO
CREATE UNIQUE CLUSTERED INDEX ix_v_sales ON dbo.v_sales (dept_id);
GO
INSERT dbo.sales VALUES (4, 1, 150);
GO
SELECT dept_id, cnt, tot FROM dbo.v_sales ORDER BY dept_id;
```

```text
(1 row affected)

dept_id cnt tot
------- --- ---
1       3   450
2       1   50

(2 rows affected)
```

### B. Incremental materialized view with `MIN`, `MAX`, `APPROX_COUNT_DISTINCT`, and `VAR_POP`

<!-- example: tsql -->
```sql
CREATE MATERIALIZED VIEW dbo.mv_stats
    REFRESH FAST ON STATEMENT
AS SELECT dept_id, MIN(amount) AS mn, MAX(amount) AS mx,
          APPROX_COUNT_DISTINCT(amount) AS du, VAR_POP(amount) AS vp
   FROM dbo.sales GROUP BY dept_id;
GO
INSERT dbo.sales VALUES (5, 1, 300), (6, 2, 150);
GO
SELECT dept_id, mn, mx, du, vp FROM dbo.mv_stats ORDER BY dept_id;
```

```text
(2 rows affected)

dept_id mn  mx  du vp
------- --- --- -- ---------------------
1       100 300 4  5468.7500000000000000
2       50  150 2  2500.0000000000000000

(2 rows affected)
```

### C. Real-time materialized view (`refresh = 'realtime'`) and `REFRESH ... FAST`

<!-- example: tsql -->
```sql
CREATE MATERIALIZED VIEW dbo.mv_rt
    WITH (refresh = 'realtime')
AS SELECT dept_id, COUNT(*) AS cnt, SUM(amount) AS tot FROM dbo.sales GROUP BY dept_id;
GO
INSERT dbo.sales VALUES (7, 2, 25);
GO
SELECT dept_id, cnt, tot FROM dbo.mv_rt ORDER BY dept_id;
GO
REFRESH MATERIALIZED VIEW dbo.mv_rt FAST;
GO
SELECT dept_id, cnt, tot FROM dbo.mv_rt ORDER BY dept_id;
```

```text
(1 row affected)

dept_id cnt tot
------- --- ---
1       4   750
2       3   225

(2 rows affected)

dept_id cnt tot
------- --- ---
1       4   750
2       3   225

(2 rows affected)
```

### D. Cascading rollup DAG and automatic query rewrite

<!-- example: tsql -->
```sql
CREATE MATERIALIZED VIEW dbo.mv_dept
    REFRESH FAST ON STATEMENT ENABLE QUERY REWRITE
AS SELECT dept_id, COUNT(*) AS cnt, SUM(amount) AS tot FROM dbo.sales GROUP BY dept_id;
GO
CREATE MATERIALIZED VIEW dbo.mv_grand
    REFRESH FAST ON STATEMENT
AS SELECT SUM(cnt) AS total_rows, SUM(tot) AS grand_tot FROM dbo.mv_dept;
GO
INSERT dbo.sales VALUES (8, 3, 200);
GO
SELECT total_rows, grand_tot FROM dbo.mv_grand;
GO
SELECT SUM(amount) AS grand_tot FROM dbo.sales;
```

```text
(1 row affected)

total_rows grand_tot
---------- ---------
8          1175

(1 row affected)

grand_tot
---------
1175

(1 row affected)
```

### E. On-demand snapshot materialized view and cleanup

<!-- example: tsql -->
```sql
CREATE MATERIALIZED VIEW dbo.mv_snap
    REFRESH COMPLETE ON DEMAND
AS SELECT dept_id, SUM(amount) AS tot FROM dbo.sales GROUP BY dept_id;
GO
INSERT dbo.sales VALUES (9, 2, 75);
GO
REFRESH MATERIALIZED VIEW dbo.mv_snap;
GO
SELECT dept_id, tot FROM dbo.mv_snap ORDER BY dept_id;
GO
DROP MATERIALIZED VIEW dbo.mv_dept CASCADE;
DROP MATERIALIZED VIEW dbo.mv_stats, dbo.mv_rt, dbo.mv_snap;
DROP INDEX ix_v_sales ON dbo.v_sales;
DROP VIEW dbo.v_sales;
```

```text
(1 row affected)

dept_id tot
------- ---
1       750
2       300
3       200

(3 rows affected)
```

### F. Finer-grain rollup rewrite (derived `GROUP BY`, range subsumption, join-back, and `VAR_POP`)

<!-- example: tsql -->
```sql
CREATE TABLE dbo.dept_info (dept_id INT PRIMARY KEY, region NVARCHAR(10));
INSERT dbo.dept_info VALUES (1, 'EMEA'), (2, 'EMEA'), (3, 'AMER');
GO
CREATE MATERIALIZED VIEW dbo.mv_detail
    REFRESH FAST ON STATEMENT ENABLE QUERY REWRITE
AS SELECT dept_id, amount, SUM(amount) AS tot, STDDEV_SAMP(amount) AS sd
   FROM dbo.sales
   WHERE amount >= 50
   GROUP BY dept_id, amount;
GO
SELECT d.region, SUM(s.amount) AS region_tot, COUNT(*) AS n
FROM dbo.sales s JOIN dbo.dept_info d ON s.dept_id = d.dept_id
WHERE s.amount >= 100
GROUP BY d.region
ORDER BY d.region;
GO
SELECT dept_id / 2 AS bucket, ROUND(VAR_POP(amount), 2) AS vp
FROM dbo.sales
WHERE amount >= 50
GROUP BY dept_id / 2
ORDER BY dept_id / 2;
GO
DROP MATERIALIZED VIEW dbo.mv_detail;
DROP TABLE dbo.dept_info;
```

```text
(3 rows affected)

region region_tot n
------ ---------- -
AMER   200        1
EMEA   900        5

(2 rows affected)

bucket vp
------ ---------------------
0      5468.7500000000000000
1      3554.6900000000000000

(2 rows affected)
```

## See also

[CREATE VIEW](create-view.md), [Aggregate functions](functions-aggregate.md)
