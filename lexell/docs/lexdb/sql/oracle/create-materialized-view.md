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
  (`COUNT(*)`, `COUNT(expr)`, `SUM`, `AVG`, `VAR_POP`, `VAR_SAMP`, `VARIANCE`, `STDDEV_POP`, `STDDEV_SAMP`, `STDDEV`,
  `BOOLEAN_AND_AGG`/`BOOL_AND`, `BOOLEAN_OR_AGG`/`BOOL_OR`, `BIT_XOR_AGG`/`BIT_XOR`, `MIN`, `MAX`,
  `APPROX_COUNT_DISTINCT`, `APPROX_COUNT_DISTINCT_DETAIL`, `APPROX_PERCENTILE`, `APPROX_PERCENTILE_DETAIL`), and
  multi-table inner equi-joins across `INSERT`, `UPDATE`, `DELETE`, `MERGE`, and `TRUNCATE`.
- Composable HyperLogLog++ and t-digest sketch aggregates merge associatively in $O(\Delta)$ on appends and re-probe
  affected groups on deletes.

## Differences from Oracle

- `CREATE MATERIALIZED VIEW LOG` records the log metadata in `USER_MVIEW_LOGS`; lexdb's `FAST` refresh tracks signed
  deltas directly without requiring a separate log table to be created first.
- `REFRESH FAST` on an ineligible query shape (such as `DISTINCT` or window functions) raises `ORA-12015`.

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, dept VARCHAR2(10), sal NUMBER);
INSERT INTO emp VALUES (1, 'a', 100);
INSERT INTO emp VALUES (2, 'a', 200);
INSERT INTO emp VALUES (3, 'b', 50);
COMMIT;
-->

The examples use one table:

```sql
CREATE TABLE emp (id NUMBER PRIMARY KEY, dept VARCHAR2(10), sal NUMBER);
INSERT INTO emp VALUES (1, 'a', 100);
INSERT INTO emp VALUES (2, 'a', 200);
INSERT INTO emp VALUES (3, 'b', 50);
COMMIT;
```

### A. Materialized view log, `ON DEMAND`, and `ON COMMIT`

<!-- example: oracle -->
```sql
CREATE MATERIALIZED VIEW LOG ON emp WITH PRIMARY KEY, ROWID, SEQUENCE (dept, sal) INCLUDING NEW VALUES;
CREATE MATERIALIZED VIEW mv_demand
    REFRESH COMPLETE ON DEMAND
AS SELECT dept, COUNT(*) AS n, SUM(sal) AS tot FROM emp GROUP BY dept;
CREATE MATERIALIZED VIEW mv_fast
    REFRESH FAST ON COMMIT ENABLE QUERY REWRITE
AS SELECT dept, COUNT(*) AS n, SUM(sal) AS tot FROM emp GROUP BY dept;
INSERT INTO emp VALUES (4, 'a', 150);
COMMIT;
SELECT dept, n, tot FROM mv_fast ORDER BY dept;
SELECT mview_name, refresh_mode, refresh_method, staleness, rewrite_enabled FROM user_mviews ORDER BY mview_name;
```

```text
Materialized view created.

Materialized view created.

Materialized view created.

1 row created.

Commit complete.

DEPT N TOT
---- - ---
a    3 450
b    1  50

2 rows selected.

MVIEW_NAME REFRESH_MODE REFRESH_METHOD STALENESS     REWRITE_ENABLED
---------- ------------ -------------- ------------- ---------------
MV_DEMAND  DEMAND       COMPLETE       NEEDS_COMPILE N
MV_FAST    COMMIT       FAST           FRESH         Y

2 rows selected.
```

### B. `DBMS_MVIEW.REFRESH` and incremental `ON STATEMENT` with sketches

<!-- example: oracle -->
```sql
BEGIN
  DBMS_MVIEW.REFRESH('mv_demand', 'C');
END;
/
SELECT dept, n, tot FROM mv_demand ORDER BY dept;
CREATE MATERIALIZED VIEW mv_stats
    REFRESH FAST ON STATEMENT
AS SELECT dept, MIN(sal) AS mn, MAX(sal) AS mx, BIT_XOR_AGG(sal) AS bx,
          APPROX_COUNT_DISTINCT(sal) AS du,
          APPROX_PERCENTILE(0.5) WITHIN GROUP (ORDER BY sal) AS p50
   FROM emp GROUP BY dept;
DELETE FROM emp WHERE id = 1;
INSERT INTO emp VALUES (5, 'a', 300);
COMMIT;
SELECT dept, mn, mx, bx, du, p50 FROM mv_stats ORDER BY dept;
```

```text
PL/SQL procedure successfully completed.

DEPT N TOT
---- - ---
a    3 450
b    1  50

2 rows selected.

Materialized view created.

1 row deleted.

1 row created.

Commit complete.

DEPT  MN  MX  BX DU P50
---- --- --- --- -- ---
a    150 300 370  3 200
b     50  50  50  1  50

2 rows selected.
```

### C. `ALTER` and `DROP`

<!-- example: oracle -->
```sql
ALTER MATERIALIZED VIEW mv_demand ENABLE QUERY REWRITE REFRESH COMPLETE ON COMMIT;
SELECT mview_name, refresh_mode, rewrite_enabled FROM user_mviews WHERE mview_name = 'MV_DEMAND';
DROP MATERIALIZED VIEW mv_demand;
DROP MATERIALIZED VIEW mv_fast;
DROP MATERIALIZED VIEW mv_stats;
DROP MATERIALIZED VIEW LOG ON emp;
```

```text
Materialized view altered.

MVIEW_NAME REFRESH_MODE REWRITE_ENABLED
---------- ------------ ---------------
MV_DEMAND  COMMIT       Y

1 row selected.

Materialized view dropped.

Materialized view dropped.

Materialized view dropped.

Materialized view dropped.
```

## See also

[CREATE VIEW](create-view.md), [Aggregate functions](functions-aggregate.md), [Built-in packages](plsql-builtin-packages.md),
[Data dictionary](data-dictionary-tables.md)
