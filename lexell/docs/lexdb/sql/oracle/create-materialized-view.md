# CREATE MATERIALIZED VIEW

Creates a materialized view storing the result of a query on disk, with Oracle-style build modes, incremental (`FAST`)
or atomic (`COMPLETE` / `FORCE`) refresh, `DBMS_MVIEW.REFRESH`, and dictionary views.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE MATERIALIZED VIEW [ IF NOT EXISTS ] [ schema. ] mview [ ( alias [, ...] ) ]
    [ BUILD { IMMEDIATE | DEFERRED } ]
    [ REFRESH [ FAST | COMPLETE | FORCE ] [ ON { DEMAND | COMMIT | STATEMENT } ] ]
    [ { ENABLE | DISABLE } QUERY REWRITE ]
    [ { ENABLE | DISABLE } ON QUERY COMPUTATION ]
    AS subquery

ALTER MATERIALIZED VIEW [ schema. ] mview
    [ REFRESH [ FAST | COMPLETE | FORCE ] [ ON { DEMAND | COMMIT | STATEMENT } ] ]
    [ { ENABLE | DISABLE } QUERY REWRITE ]
    [ { ENABLE | DISABLE } ON QUERY COMPUTATION ]
    [ COMPILE ]

DROP MATERIALIZED VIEW [ IF EXISTS ] [ schema. ] mview

CREATE MATERIALIZED VIEW LOG ON [ schema. ] table
    [ WITH [ PRIMARY KEY | ROWID | SEQUENCE | ( column [, ...] ) ] [, ...] ]
    [ { INCLUDING | EXCLUDING } NEW VALUES ]

DROP MATERIALIZED VIEW LOG ON [ schema. ] table
```

## Arguments

`BUILD IMMEDIATE` | `BUILD DEFERRED`
: `BUILD IMMEDIATE` (default) populates the materialized view on creation. `BUILD DEFERRED` creates it empty
  (`STALENESS = 'UNUSABLE'`) until refreshed with `DBMS_MVIEW.REFRESH`.

`REFRESH [ FAST | COMPLETE | FORCE ] [ ON DEMAND | ON COMMIT | ON STATEMENT ]`
: - `COMPLETE`: atomically rebuilds the materialized view into a fresh B+tree and swaps it into place.
  - `FAST`: maintains the materialized view incrementally in $O(\Delta)$ using signed Z-set deltas. Raises `ORA-12015`
    if the query shape is not eligible for fast refresh.
  - `FORCE` (default): uses `FAST` when the query is eligible and falls back to `COMPLETE` otherwise.
  - `ON DEMAND` (default): refreshed explicitly via `DBMS_MVIEW.REFRESH(list [, method])`. Base-table DML marks the
    view `NEEDS_COMPILE` in `USER_MVIEWS.STALENESS`.
  - `ON COMMIT`: automatically refreshed at transaction `COMMIT`.
  - `ON STATEMENT`: synchronously updated at the end of every DML statement on a base table.

`ENABLE QUERY REWRITE` / `ENABLE ON QUERY COMPUTATION`
: Recorded in `USER_MVIEWS` (`REWRITE_ENABLED`, `ON_QUERY_COMPUTATION`) and changeable via `ALTER MATERIALIZED VIEW`.

## Remarks

- `USER_MVIEWS`, `ALL_MVIEWS`, and `DBA_MVIEWS` report `MVIEW_NAME`, `CONTAINER_NAME`, `QUERY`, `REFRESH_MODE`,
  `REFRESH_METHOD`, `BUILD_MODE`, `FAST_REFRESHABLE`, `LAST_REFRESH_TYPE`, `STALENESS`, `REWRITE_ENABLED`, and
  `ON_QUERY_COMPUTATION`.
- `USER_MVIEW_LOGS`, `ALL_MVIEW_LOGS`, and `DBA_MVIEW_LOGS` report materialized view logs created with
  `CREATE MATERIALIZED VIEW LOG ON table`.
- `USER_OBJECTS` lists each materialized view with `OBJECT_TYPE = 'MATERIALIZED VIEW'`.
- `DBMS_MVIEW.REFRESH('mv1, mv2', 'C' | 'F' | '?')` refreshes one or more materialized views inside a PL/SQL block.
- Incremental (`FAST`) maintenance supports single-table filter/projection views, `GROUP BY` and global aggregates
  (`COUNT(*)`, `COUNT(expr)`, `SUM(expr)`, `AVG(expr)`), and multi-table inner equi-joins across `INSERT`, `UPDATE`,
  `DELETE`, `MERGE`, and `TRUNCATE`.

## Examples

```sql
CREATE TABLE emp (id NUMBER PRIMARY KEY, dept VARCHAR2(10), sal NUMBER);
INSERT INTO emp VALUES (1, 'a', 100);
INSERT INTO emp VALUES (2, 'a', 200);
INSERT INTO emp VALUES (3, 'b', 50);

CREATE MATERIALIZED VIEW LOG ON emp WITH PRIMARY KEY, ROWID, SEQUENCE (dept, sal) INCLUDING NEW VALUES;

CREATE MATERIALIZED VIEW mv_dept
    REFRESH FAST ON COMMIT ENABLE QUERY REWRITE
AS SELECT dept, COUNT(*) AS n, SUM(sal) AS tot FROM emp GROUP BY dept;

INSERT INTO emp VALUES (4, 'a', 150);
COMMIT;
SELECT dept, n, tot FROM mv_dept ORDER BY dept;

CREATE MATERIALIZED VIEW mv_snap
    REFRESH COMPLETE ON DEMAND
AS SELECT dept, COUNT(*) AS n, SUM(sal) AS tot FROM emp GROUP BY dept;

BEGIN
    DBMS_MVIEW.REFRESH('mv_snap', 'C');
END;
/

SELECT mview_name, refresh_mode, refresh_method, staleness FROM user_mviews ORDER BY mview_name;
```
