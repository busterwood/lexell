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
  When `QUERY REWRITE` is enabled and `ALTER SESSION SET QUERY_REWRITE_ENABLED = TRUE` (default), the planner
  transparently rewrites eligible `SELECT` queries against the base table(s) onto the materialized view (supporting
  exact matches, `HAVING`, subsumed `WHERE` predicates including range/`IN`/`IS NOT NULL`, coarser and derived
  `GROUP BY` expressions, join-back to extra dimension tables, exact `COUNT(DISTINCT)`/`SUM(DISTINCT)`/`AVG(DISTINCT)`
  rollups over MV keys, and `COUNT`/`SUM`/`AVG`/`MIN`/`MAX`/`VAR_*`/`STDDEV_*`/sketch rollups, while skipping stale
  `ON DEMAND` views and uncommitted `ON COMMIT` changes). Oversized `GROUP BY` keys exceeding 512 bytes are
  fingerprinted automatically.
  When `ON QUERY COMPUTATION` is enabled on a fast-refreshable materialized view, DML appends signed deltas to a
  contention-free companion delta tree, `SELECT` queries merge base + delta rows on the fly in the reader's MVCC
  snapshot (even on `ON DEMAND` views before refresh), and `DBMS_MVIEW.REFRESH(..., 'F')` or the background folder
  folds deltas into the base tree in $O(\Delta)$.

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
- **Cascading materialized views:** A materialized view may query another materialized view (including cascading sketch
  rollups from `APPROX_COUNT_DISTINCT_DETAIL` / `APPROX_PERCENTILE_DETAIL` to `APPROX_COUNT_DISTINCT_AGG` /
  `APPROX_PERCENTILE_AGG`). Incremental deltas propagate topologically in $O(\Delta)$ down the DAG across `ON STATEMENT`,
  `ON COMMIT`, and `FAST` delta folding.
- **Automatic query rewrite:** Controlled per session with `ALTER SESSION SET QUERY_REWRITE_ENABLED = TRUE | FALSE | FORCE`
  (see [ALTER SESSION](alter-session.md)). Eligible queries transparently read fresh `ENABLE QUERY REWRITE` views
  (including `ON QUERY COMPUTATION` views).

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

### C. Real-time materialized view (`ON DEMAND ENABLE ON QUERY COMPUTATION`)

<!-- example: oracle -->
```sql
CREATE MATERIALIZED VIEW mv_oqc
    REFRESH FAST ON DEMAND ENABLE ON QUERY COMPUTATION
AS SELECT dept, COUNT(*) AS n, SUM(sal) AS tot FROM emp GROUP BY dept;
INSERT INTO emp VALUES (6, 'c', 400);
COMMIT;
SELECT dept, n, tot FROM mv_oqc ORDER BY dept;
BEGIN
  DBMS_MVIEW.REFRESH('mv_oqc', 'F');
END;
/
SELECT mview_name, on_query_computation, staleness FROM user_mviews WHERE mview_name = 'MV_OQC';
```

```text
Materialized view created.

1 row created.

Commit complete.

DEPT N TOT
---- - ---
a    3 650
b    1  50
c    1 400

3 rows selected.

PL/SQL procedure successfully completed.

MVIEW_NAME ON_QUERY_COMPUTATION STALENESS
---------- -------------------- ---------
MV_OQC     Y                    FRESH

1 row selected.
```

### D. Cascading rollup DAG and automatic query rewrite

<!-- example: oracle -->
```sql
CREATE MATERIALIZED VIEW mv_total
    REFRESH FAST ON STATEMENT
AS SELECT SUM(n) AS total_emp, SUM(tot) AS grand_tot FROM mv_fast;
INSERT INTO emp VALUES (7, 'c', 250);
COMMIT;
SELECT total_emp, grand_tot FROM mv_total;
SELECT SUM(sal) AS grand_tot FROM emp;
ALTER SESSION SET QUERY_REWRITE_ENABLED = FALSE;
SELECT SUM(sal) AS grand_tot FROM emp;
ALTER SESSION SET QUERY_REWRITE_ENABLED = TRUE;
```

```text
Materialized view created.

1 row created.

Commit complete.

TOTAL_EMP GRAND_TOT
--------- ---------
        6      1350

1 row selected.

GRAND_TOT
---------
     1350

1 row selected.

Session altered.

GRAND_TOT
---------
     1350

1 row selected.

Session altered.
```

### E. `ALTER` and `DROP`

<!-- example: oracle -->
```sql
ALTER MATERIALIZED VIEW mv_demand ENABLE QUERY REWRITE REFRESH COMPLETE ON COMMIT;
SELECT mview_name, refresh_mode, rewrite_enabled FROM user_mviews WHERE mview_name = 'MV_DEMAND';
DROP MATERIALIZED VIEW mv_total;
DROP MATERIALIZED VIEW mv_demand;
DROP MATERIALIZED VIEW mv_fast;
DROP MATERIALIZED VIEW mv_stats;
DROP MATERIALIZED VIEW mv_oqc;
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

Materialized view dropped.

Materialized view dropped.
```

### F. Finer-grain rollup rewrite (derived `GROUP BY`, range subsumption, join-back, and `VAR_POP`)

<!-- example: oracle -->
```sql
CREATE TABLE dept_info (dept VARCHAR2(10) PRIMARY KEY, region VARCHAR2(10));
INSERT INTO dept_info VALUES ('a', 'EMEA');
INSERT INTO dept_info VALUES ('b', 'EMEA');
INSERT INTO dept_info VALUES ('c', 'AMER');
COMMIT;
CREATE MATERIALIZED VIEW mv_detail
    REFRESH FAST ON STATEMENT ENABLE QUERY REWRITE
AS SELECT dept, sal, SUM(sal) AS tot, STDDEV(sal) AS sd
   FROM emp
   WHERE sal >= 50
   GROUP BY dept, sal;
SELECT d.region, SUM(e.sal) AS region_tot, COUNT(*) AS n
FROM emp e JOIN dept_info d ON e.dept = d.dept
WHERE e.sal >= 100
GROUP BY d.region
ORDER BY d.region;
SELECT UPPER(dept) AS dept_up, ROUND(VAR_POP(sal), 2) AS vp
FROM emp
WHERE sal >= 50
GROUP BY UPPER(dept)
ORDER BY UPPER(dept);
DROP MATERIALIZED VIEW mv_detail;
DROP TABLE dept_info;
```

```text
Table created.

1 row created.

1 row created.

1 row created.

Commit complete.

Materialized view created.

REGION REGION_TOT N
------ ---------- -
AMER          650 2
EMEA          650 3

2 rows selected.

DEPT_UP      VP
------- -------
A       3888.89
B             0
C          5625

3 rows selected.

Materialized view dropped.

Table dropped.
```

## See also

[CREATE VIEW](create-view.md), [Aggregate functions](functions-aggregate.md), [Built-in packages](plsql-builtin-packages.md),
[Data dictionary](data-dictionary-tables.md)
