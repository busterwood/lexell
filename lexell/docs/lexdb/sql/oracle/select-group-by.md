# SELECT: GROUP BY and HAVING

Groups the rows of a [SELECT](select.md) and filters the groups. Includes `GROUP BY ALL`, `ROLLUP`, `CUBE` and
`GROUPING SETS`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
GROUP BY { ALL | group_by_item [, group_by_item ]... }
    [ HAVING condition ]

group_by_item:
    { expr
    | position
    | ROLLUP ( expr_list [, expr_list ]... )
    | CUBE ( expr_list [, expr_list ]... )
    | GROUPING SETS ( { expr_list | ( ) } [, ...] ) }

expr_list:
    expr | ( expr [, expr ]... )

GROUPING ( expr )
```

## Arguments

*expr*
: A column, an expression, or (23ai) the alias of a select-list column. Rows with equal values (NULLs are equal here) form one group. The select list may
  name the grouped expressions, aggregate functions, and constants.

`ALL` (26ai)
: Groups by every select-list expression that has no aggregate function. It takes no list of its own.

*position*
: The number of a select-list column, only when the session parameter `GROUP_BY_POSITION_ENABLED` is `TRUE`
  (`ALTER SESSION SET GROUP_BY_POSITION_ENABLED = TRUE`). Otherwise it is ORA-03162.

`ROLLUP`
: The groups for each prefix of the list, and a grand total: `ROLLUP (a, b)` gives `(a, b)`, `(a)` and `()`.

`CUBE`
: The groups for every subset of the list: `CUBE (a, b)` gives `(a, b)`, `(a)`, `(b)` and `()`.

`GROUPING SETS`
: The groups you list, and no others.

`GROUPING (` *expr* `)`
: 1 in a super-aggregate row where *expr* was left out of the grouping, else 0. It tells a NULL that a subtotal
  makes from a NULL in the data.

`HAVING`
: Keeps the groups for which the condition is true. It may use aggregates. Without `GROUP BY` the whole table is
  one group.

## Remarks

- Aggregates are `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `LISTAGG`, `STDDEV`, `VARIANCE` and the others in the Oracle
  index. `COUNT(*)` counts rows; `COUNT(expr)` counts rows where *expr* is not NULL; `DISTINCT` inside an aggregate
  counts each value once.
- With an aggregate and no `GROUP BY`, a query returns one row, even for an empty table (`COUNT` gives 0, the
  other aggregates NULL). With `GROUP BY`, an empty table gives no row.
- A select-list column that is neither grouped nor inside an aggregate is ORA-00979. An aggregate in `WHERE` is
  ORA-00979 as well.
- `ORDER BY` runs after grouping and may use aggregates and `GROUPING`.
- The order of the groups is not defined unless `ORDER BY` gives it.

## Differences from Oracle

- `GROUPING_ID` and `GROUP_ID` are not available (ORA-00904); use one `GROUPING` call for each column.
- `GROUP BY ... WITH ROLLUP` (MySQL's form) is refused, as in Oracle.
- An aggregate in `WHERE` is ORA-00979 here (Oracle: ORA-00934).

## Examples

<!--setup: oracle
CREATE TABLE dept (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL);
CREATE TABLE emp (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL, dept_id NUMBER(4) REFERENCES dept (id), mgr_id NUMBER(4), salary NUMBER(8,2), hired DATE);
INSERT INTO dept VALUES (1, 'Sales');
INSERT INTO dept VALUES (2, 'Research');
INSERT INTO dept VALUES (3, 'Legal');
INSERT INTO emp VALUES (1, 'Ann', 1, NULL, 5200, DATE '2019-03-01');
INSERT INTO emp VALUES (2, 'Bob', 1, 1, 4100, DATE '2021-07-15');
INSERT INTO emp VALUES (3, 'Cid', 2, 1, 6100, DATE '2018-01-10');
INSERT INTO emp VALUES (4, 'Dee', 2, 3, 6100, DATE '2022-05-02');
INSERT INTO emp VALUES (5, 'Eve', NULL, 3, 3000, DATE '2024-09-30');
COMMIT;
-->

The examples use the `emp` and `dept` tables of [SELECT](select.md).

### A. Groups and aggregates

<!-- example: oracle -->
```sql
SELECT dept_id, COUNT(*) AS n, SUM(salary) AS total, AVG(salary) AS average, TO_CHAR(MIN(hired), 'YYYY-MM-DD') AS first_hired
FROM emp GROUP BY dept_id ORDER BY dept_id;
SELECT COUNT(*) AS n, SUM(salary) AS total FROM emp;
SELECT COUNT(*) AS n, SUM(salary) AS total FROM emp WHERE 1 = 0;
SELECT dept_id, COUNT(*) AS n FROM emp WHERE 1 = 0 GROUP BY dept_id;
```

```text
DEPT_ID N TOTAL AVERAGE FIRST_HIRED
------- - ----- ------- -----------
      1 2  9300    4650 2019-03-01
      2 2 12200    6100 2018-01-10
        1  3000    3000 2024-09-30

3 rows selected.

N TOTAL
- -----
5 24500

1 row selected.

N TOTAL
- -----
0

1 row selected.

no rows selected
```

### B. HAVING

<!-- example: oracle -->
```sql
SELECT dept_id, COUNT(*) AS n FROM emp GROUP BY dept_id HAVING COUNT(*) > 1 ORDER BY dept_id;
SELECT dept_id, SUM(salary) AS total FROM emp GROUP BY dept_id HAVING SUM(salary) > 5000 ORDER BY total DESC;
SELECT COUNT(*) AS n FROM emp HAVING COUNT(*) > 10;
SELECT dept_id, LISTAGG(name, ', ') WITHIN GROUP (ORDER BY name) AS names FROM emp GROUP BY dept_id ORDER BY dept_id;
```

```text
DEPT_ID N
------- -
      1 2
      2 2

2 rows selected.

DEPT_ID TOTAL
------- -----
      2 12200
      1  9300

2 rows selected.

no rows selected

DEPT_ID NAMES
------- --------
      1 Ann, Bob
      2 Cid, Dee
        Eve

3 rows selected.
```

### C. Grouping by an expression

<!-- example: oracle -->
```sql
SELECT EXTRACT(YEAR FROM hired) AS yr, COUNT(*) AS n FROM emp GROUP BY EXTRACT(YEAR FROM hired) ORDER BY yr;
SELECT CASE WHEN salary >= 6000 THEN 'high' WHEN salary >= 4000 THEN 'mid' ELSE 'low' END AS band, COUNT(*) AS n
FROM emp GROUP BY CASE WHEN salary >= 6000 THEN 'high' WHEN salary >= 4000 THEN 'mid' ELSE 'low' END ORDER BY 1;
SELECT dept_id AS d, COUNT(*) AS n FROM emp GROUP BY d ORDER BY d;
```

```text
  YR N
---- -
2018 1
2019 1
2021 1
2022 1
2024 1

5 rows selected.

BAND N
---- -
high 2
low  1
mid  2

3 rows selected.

D N
- -
1 2
2 2
  1

3 rows selected.
```

### D. GROUP BY ALL

<!-- example: oracle -->
```sql
SELECT dept_id, COUNT(*) AS n FROM emp GROUP BY ALL ORDER BY dept_id;
SELECT dept_id, mgr_id, COUNT(*) AS n FROM emp GROUP BY ALL ORDER BY dept_id, mgr_id;
```

```text
DEPT_ID N
------- -
      1 2
      2 2
        1

3 rows selected.

DEPT_ID MGR_ID N
------- ------ -
      1      1 1
      1        1
      2      1 1
      2      3 1
             3 1

5 rows selected.
```

### E. Positions

<!-- example: oracle -->
```sql
SELECT dept_id, COUNT(*) AS n FROM emp GROUP BY 1 ORDER BY 1;
ALTER SESSION SET GROUP_BY_POSITION_ENABLED = TRUE;
SELECT dept_id, COUNT(*) AS n FROM emp GROUP BY 1 ORDER BY 1;
ALTER SESSION SET GROUP_BY_POSITION_ENABLED = FALSE;
```

```text
ERROR:
ORA-03162: "DEPT_ID": must appear in the GROUP BY clause or be used in an aggregate function as 'group_by_position_enabled' is FALSE

Session altered.

DEPT_ID N
------- -
      1 2
      2 2
        1

3 rows selected.

Session altered.
```

### F. ROLLUP

`GROUPING` tells a subtotal row from a row whose value is NULL in the data.

<!-- example: oracle -->
```sql
SELECT dept_id, mgr_id, COUNT(*) AS n, GROUPING(dept_id) AS g_dept, GROUPING(mgr_id) AS g_mgr
FROM emp GROUP BY ROLLUP (dept_id, mgr_id) ORDER BY g_dept, g_mgr, dept_id, mgr_id;
```

```text
DEPT_ID MGR_ID N G_DEPT G_MGR
------- ------ - ------ -----
      1      1 1      0     0
      1        1      0     0
      2      1 1      0     0
      2      3 1      0     0
             3 1      0     0
      1        2      0     1
      2        2      0     1
               1      0     1
               5      1     1

9 rows selected.
```

### G. CUBE and GROUPING SETS

<!-- example: oracle -->
```sql
SELECT dept_id, mgr_id, COUNT(*) AS n, GROUPING(dept_id) AS g_dept, GROUPING(mgr_id) AS g_mgr
FROM emp GROUP BY CUBE (dept_id, mgr_id) ORDER BY g_dept, g_mgr, dept_id, mgr_id;
SELECT dept_id, mgr_id, COUNT(*) AS n, GROUPING(dept_id) AS g_dept, GROUPING(mgr_id) AS g_mgr
FROM emp GROUP BY GROUPING SETS ((dept_id), (mgr_id), ()) ORDER BY g_dept, g_mgr, dept_id, mgr_id;
SELECT dept_id, mgr_id, COUNT(*) AS n FROM emp GROUP BY dept_id, ROLLUP (mgr_id) ORDER BY dept_id, mgr_id;
SELECT dept_id, mgr_id, COUNT(*) AS n, GROUPING(dept_id) AS g_dept FROM emp
GROUP BY ROLLUP ((dept_id, mgr_id)) ORDER BY g_dept, dept_id, mgr_id;
```

```text
DEPT_ID MGR_ID N G_DEPT G_MGR
------- ------ - ------ -----
      1      1 1      0     0
      1        1      0     0
      2      1 1      0     0
      2      3 1      0     0
             3 1      0     0
      1        2      0     1
      2        2      0     1
               1      0     1
             1 2      1     0
             3 2      1     0
               1      1     0
               5      1     1

12 rows selected.

DEPT_ID MGR_ID N G_DEPT G_MGR
------- ------ - ------ -----
      1        2      0     1
      2        2      0     1
               1      0     1
             1 2      1     0
             3 2      1     0
               1      1     0
               5      1     1

7 rows selected.

DEPT_ID MGR_ID N
------- ------ -
      1      1 1
      1        1
      1        2
      2      1 1
      2      3 1
      2        2
             3 1
               1

8 rows selected.

DEPT_ID MGR_ID N G_DEPT
------- ------ - ------
      1      1 1      0
      1        1      0
      2      1 1      0
      2      3 1      0
             3 1      0
               5      1

6 rows selected.
```

### H. Errors

<!-- example: oracle -->
```sql
SELECT dept_id, name FROM emp GROUP BY dept_id;
SELECT dept_id, COUNT(*) FROM emp WHERE COUNT(*) > 1 GROUP BY dept_id;
SELECT dept_id, COUNT(*) AS n FROM emp GROUP BY dept_id WITH ROLLUP;
SELECT dept_id, GROUPING_ID(dept_id) AS g FROM emp GROUP BY ROLLUP (dept_id);
SELECT dept_id, COUNT(*) AS n FROM emp GROUP BY ALL dept_id;
```

```text
ERROR:
ORA-00979: not a GROUP BY expression

ERROR:
ORA-00979: not a GROUP BY expression

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-03049: SQL keyword 'DEPT_ID' is not syntactically valid following '...group by all '
```

## See also

[SELECT](select.md) · [Joins](select-join.md) · [Hierarchical queries](hierarchical-queries.md)
