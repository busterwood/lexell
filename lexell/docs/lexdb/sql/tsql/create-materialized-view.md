# CREATE MATERIALIZED VIEW (Transact-SQL)

Creates a materialized view storing query results on disk, supporting all lexdb refresh modes (`COMPLETE`, `FAST`,
`FORCE`) and timings (`ON DEMAND`, `ON COMMIT`, `ON STATEMENT`), alongside SQL Server's native indexed views
(`CREATE VIEW ... WITH SCHEMABINDING` + `CREATE UNIQUE CLUSTERED INDEX`).

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022/2025 indexed views + lexdb cross-door materialized views.

## Syntax

```
CREATE MATERIALIZED VIEW [ IF NOT EXISTS ] [ schema_name . ] mview_name [ ( column [ ,...n ] ) ]
    [ BUILD { IMMEDIATE | DEFERRED } ]
    [ REFRESH [ FAST | COMPLETE | FORCE ] [ ON { DEMAND | COMMIT | STATEMENT } ] ]
    [ { ENABLE | DISABLE } QUERY REWRITE ]
    [ { ENABLE | DISABLE } ON QUERY COMPUTATION ]
    [ WITH ( refresh = 'demand' | 'fast_on_commit' | 'fast_on_statement' | 'complete_on_commit' [, query_rewrite = true | false ] ) ]
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
  (`COUNT(*)`, `COUNT(expr)`, `SUM(expr)`, `AVG(expr)`), and multi-table inner equi-joins across `INSERT`, `UPDATE`,
  `DELETE`, `MERGE`, and `TRUNCATE`.

## Examples

```sql
CREATE TABLE dbo.sales (id int PRIMARY KEY, dept_id int, amount int);
INSERT dbo.sales VALUES (1, 1, 100), (2, 1, 200), (3, 2, 50);

CREATE MATERIALIZED VIEW dbo.mv_sales
    REFRESH FAST ON COMMIT ENABLE QUERY REWRITE
AS SELECT dept_id, count(*) AS cnt, sum(amount) AS tot FROM dbo.sales GROUP BY dept_id;

INSERT dbo.sales VALUES (4, 1, 150);
SELECT dept_id, cnt, tot FROM dbo.mv_sales ORDER BY dept_id;

CREATE MATERIALIZED VIEW dbo.mv_snap
    REFRESH COMPLETE ON DEMAND
AS SELECT dept_id, sum(amount) AS tot FROM dbo.sales GROUP BY dept_id;

INSERT dbo.sales VALUES (5, 2, 25);
REFRESH MATERIALIZED VIEW dbo.mv_snap;
SELECT dept_id, tot FROM dbo.mv_snap ORDER BY dept_id;
```
