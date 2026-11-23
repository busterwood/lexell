# Hierarchical queries

Walks a tree or a graph stored as rows that point at their parents, with `START WITH` and `CONNECT BY`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
SELECT select_list
FROM table_or_view [ alias ]
[ WHERE condition ]
[ START WITH condition ]
CONNECT BY [ NOCYCLE ] condition_with_PRIOR
[ ORDER SIBLINGS BY expr [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [, ...] ]

-- in the select list, WHERE, ORDER BY
LEVEL
PRIOR expr
CONNECT_BY_ROOT expr
CONNECT_BY_ISLEAF
CONNECT_BY_ISCYCLE
SYS_CONNECT_BY_PATH ( column, 'separator' )

-- a row generator
SELECT expr FROM DUAL CONNECT BY LEVEL <= n
```

`START WITH` may come before or after `CONNECT BY`.

## Arguments

`START WITH`
: The condition the root rows meet. Without it, every row is a root.

`CONNECT BY`
: How a child row relates to its parent row, with `PRIOR` marking the parent's column: `PRIOR id = mgr_id` takes as
  children the rows whose `mgr_id` is the parent's `id`. The condition may have further tests; a test on `LEVEL`
  stops the descent.

`NOCYCLE`
: Allows data with loops: a row that is its own ancestor is not followed further. Without it a loop is ORA-01436.

`PRIOR` *expr*
: The value of *expr* in the parent row. In the select list it gives the parent's value (NULL for a root).

`LEVEL`
: 1 for a root row, 2 for its children, and so on.

`CONNECT_BY_ROOT` *expr*
: The value of *expr* in the root row of the branch.

`CONNECT_BY_ISLEAF`
: 1 for a row that has no children, else 0.

`CONNECT_BY_ISCYCLE`
: 1 for a row that has a child that is also its ancestor, else 0. It is used with `NOCYCLE`.

`SYS_CONNECT_BY_PATH`
: The values of a column from the root to the row, each after the separator: `/Ann/Cid/Dee`.

`ORDER SIBLINGS BY`
: Sorts the children of each parent, and keeps each child with its subtree. A plain `ORDER BY` sorts the whole
  result and breaks the tree order.

## Remarks

- The `WHERE` condition filters rows after the tree is built: a row that fails it is left out, but its children
  are still visited. A test in `CONNECT BY` cuts the tree.
- Without `ORDER SIBLINGS BY` or `ORDER BY`, rows come depth first, each parent before its children.
- `CONNECT BY LEVEL <= n` with no `PRIOR` makes n rows from one: the usual way to produce a series of numbers or
  dates. It is used with `FROM DUAL`.
- `CONNECT BY` without `START WITH` takes every row as a root.
- The query reads one table or view. A subquery in the select list is allowed; a join in `FROM` is not (see below).

## Differences from Oracle

- A query with a join in its `FROM` list is not supported (ORA-03001): make the join an inline view and put
  `CONNECT BY` over it.
- `CONNECT BY ROWNUM <= n` is not read as a row generator (ORA-32044); write `LEVEL <= n`.
- `GROUP BY CONNECT_BY_ROOT col` is ORA-00979; group over an inline view.
- `LEVEL` and the other pseudo-columns are ORA-00904 outside a hierarchical query, as in Oracle. `START WITH`
  without `CONNECT BY` is ORA-01788.

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL, mgr_id NUMBER(4), salary NUMBER(8,2));
INSERT INTO emp VALUES (1, 'Ann', NULL, 5200);
INSERT INTO emp VALUES (2, 'Bob', 1, 4100);
INSERT INTO emp VALUES (3, 'Cid', 1, 6100);
INSERT INTO emp VALUES (4, 'Dee', 3, 6100);
INSERT INTO emp VALUES (5, 'Eve', 3, 3000);
COMMIT;
-->

The examples use a table of employees and their managers:

```sql
CREATE TABLE emp (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL, mgr_id NUMBER(4), salary NUMBER(8,2));
INSERT INTO emp VALUES (1, 'Ann', NULL, 5200);
INSERT INTO emp VALUES (2, 'Bob', 1, 4100);
INSERT INTO emp VALUES (3, 'Cid', 1, 6100);
INSERT INTO emp VALUES (4, 'Dee', 3, 6100);
INSERT INTO emp VALUES (5, 'Eve', 3, 3000);
```

### A. The whole tree

<!-- example: oracle -->
```sql
SELECT LEVEL, name, mgr_id FROM emp START WITH mgr_id IS NULL CONNECT BY PRIOR id = mgr_id;
SELECT LEVEL, LPAD(' ', 2 * (LEVEL - 1)) || name AS tree FROM emp
START WITH mgr_id IS NULL CONNECT BY PRIOR id = mgr_id ORDER SIBLINGS BY name;
```

```text
LEVEL NAME MGR_ID
----- ---- ------
    1 Ann
    2 Bob       1
    2 Cid       1
    3 Dee       3
    3 Eve       3

5 rows selected.

LEVEL TREE
----- -------
    1 Ann
    2   Bob
    2   Cid
    3     Dee
    3     Eve

5 rows selected.
```

### B. ORDER SIBLINGS BY

<!-- example: oracle -->
```sql
SELECT LEVEL, name FROM emp START WITH mgr_id IS NULL CONNECT BY PRIOR id = mgr_id ORDER SIBLINGS BY name DESC;
SELECT LEVEL, name FROM emp START WITH mgr_id IS NULL CONNECT BY PRIOR id = mgr_id ORDER SIBLINGS BY salary DESC, name;
```

```text
LEVEL NAME
----- ----
    1 Ann
    2 Cid
    3 Eve
    3 Dee
    2 Bob

5 rows selected.

LEVEL NAME
----- ----
    1 Ann
    2 Cid
    3 Dee
    3 Eve
    2 Bob

5 rows selected.
```

### C. PRIOR, CONNECT_BY_ROOT, CONNECT_BY_ISLEAF and SYS_CONNECT_BY_PATH

<!-- example: oracle -->
```sql
SELECT name, PRIOR name AS boss, CONNECT_BY_ROOT name AS top, CONNECT_BY_ISLEAF AS leaf, SYS_CONNECT_BY_PATH(name, '/') AS path
FROM emp START WITH mgr_id IS NULL CONNECT BY PRIOR id = mgr_id ORDER SIBLINGS BY name;
```

```text
NAME BOSS TOP LEAF PATH
---- ---- --- ---- ------------
Ann       Ann    0 /Ann
Bob  Ann  Ann    1 /Ann/Bob
Cid  Ann  Ann    0 /Ann/Cid
Dee  Cid  Ann    1 /Ann/Cid/Dee
Eve  Cid  Ann    1 /Ann/Cid/Eve

5 rows selected.
```

### D. A subtree, and the way up

<!-- example: oracle -->
```sql
SELECT name, LEVEL FROM emp START WITH name = 'Cid' CONNECT BY PRIOR id = mgr_id;
SELECT name, LEVEL FROM emp START WITH name = 'Eve' CONNECT BY id = PRIOR mgr_id;
```

```text
NAME LEVEL
---- -----
Cid      1
Dee      2
Eve      2

3 rows selected.

NAME LEVEL
---- -----
Eve      1
Cid      2
Ann      3

3 rows selected.
```

### E. Filters: WHERE, and a test in CONNECT BY

<!-- example: oracle -->
```sql
SELECT name, LEVEL FROM emp WHERE LEVEL = 2 START WITH mgr_id IS NULL CONNECT BY PRIOR id = mgr_id ORDER BY name;
SELECT name, LEVEL FROM emp START WITH mgr_id IS NULL CONNECT BY PRIOR id = mgr_id AND LEVEL <= 2 ORDER BY LEVEL, name;
SELECT name, LEVEL FROM emp WHERE salary > 4000 START WITH mgr_id IS NULL CONNECT BY PRIOR id = mgr_id ORDER BY LEVEL, name;
SELECT name, LEVEL FROM emp START WITH id = 1 CONNECT BY PRIOR id = mgr_id AND PRIOR salary > salary ORDER BY LEVEL, name;
```

```text
NAME LEVEL
---- -----
Bob      2
Cid      2

2 rows selected.

NAME LEVEL
---- -----
Ann      1
Bob      2
Cid      2

3 rows selected.

NAME LEVEL
---- -----
Ann      1
Bob      2
Cid      2
Dee      3

4 rows selected.

NAME LEVEL
---- -----
Ann      1
Bob      2

2 rows selected.
```

### F. Aggregates over a tree

<!-- example: oracle -->
```sql
SELECT COUNT(*) AS n, MAX(LEVEL) AS depth FROM emp START WITH mgr_id IS NULL CONNECT BY PRIOR id = mgr_id;
SELECT name, CONNECT_BY_ROOT name AS top, CONNECT_BY_ROOT salary AS top_salary FROM emp START WITH id = 3 CONNECT BY PRIOR id = mgr_id;
SELECT name FROM emp CONNECT BY PRIOR id = mgr_id;
```

```text
N DEPTH
- -----
5     3

1 row selected.

NAME TOP TOP_SALARY
---- --- ----------
Cid  Cid       6100
Dee  Cid       6100
Eve  Cid       6100

3 rows selected.

NAME
----
Ann
Bob
Cid
Dee
Eve
Bob
Cid
Dee
Eve
Dee
Eve

11 rows selected.
```

### G. Loops: NOCYCLE and CONNECT_BY_ISCYCLE

<!-- example: oracle -->
```sql
CREATE TABLE edge (a NUMBER, b NUMBER);
INSERT INTO edge VALUES (1, 2);
INSERT INTO edge VALUES (2, 3);
INSERT INTO edge VALUES (3, 1);
INSERT INTO edge VALUES (3, 4);
COMMIT;
SELECT a, b, LEVEL FROM edge START WITH a = 1 CONNECT BY PRIOR b = a;
SELECT a, b, LEVEL, CONNECT_BY_ISCYCLE AS cyc, SYS_CONNECT_BY_PATH(b, '>') AS path
FROM edge START WITH a = 1 CONNECT BY NOCYCLE PRIOR b = a;
```

```text
Table created.

1 row created.

1 row created.

1 row created.

1 row created.

Commit complete.

ERROR:
ORA-01436: CONNECT BY loop in user data

A B LEVEL CYC PATH
- - ----- --- ------
1 2     1   0 >2
2 3     2   0 >2>3
3 1     3   1 >2>3>1
3 4     3   0 >2>3>4

4 rows selected.
```

### H. A row generator

<!-- example: oracle -->
```sql
SELECT LEVEL AS n, LEVEL * LEVEL AS square FROM DUAL CONNECT BY LEVEL <= 5;
SELECT DATE '2026-01-30' + LEVEL - 1 AS d FROM DUAL CONNECT BY LEVEL <= 3;
SELECT TO_CHAR(ADD_MONTHS(DATE '2026-01-15', LEVEL - 1), 'YYYY-MM') AS month FROM DUAL CONNECT BY LEVEL <= 4;
SELECT CHR(64 + LEVEL) AS letter FROM DUAL CONNECT BY LEVEL <= 3;
SELECT COUNT(*) AS n FROM DUAL CONNECT BY LEVEL <= 1000;
```

```text
N SQUARE
- ------
1      1
2      4
3      9
4     16
5     25

5 rows selected.

D
-------------------
2026-01-30 00:00:00
2026-01-31 00:00:00
2026-02-01 00:00:00

3 rows selected.

MONTH
-------
2026-01
2026-02
2026-03
2026-04

4 rows selected.

LETTER
------
A
B
C

3 rows selected.

   N
----
1000

1 row selected.
```

### I. What lexdb does not take, and errors

<!-- example: oracle -->
```sql
SELECT e.name, m.name AS boss FROM emp e JOIN emp m ON m.id = e.mgr_id START WITH e.mgr_id IS NULL CONNECT BY PRIOR e.id = e.mgr_id;
SELECT LEVEL FROM DUAL CONNECT BY ROWNUM <= 3;
SELECT CONNECT_BY_ROOT name AS top, COUNT(*) AS n FROM emp START WITH mgr_id IS NULL CONNECT BY PRIOR id = mgr_id GROUP BY CONNECT_BY_ROOT name;
SELECT name, LEVEL FROM emp;
SELECT name FROM emp START WITH id = 1;
```

```text
ERROR:
ORA-03001: unimplemented feature: lexdb: CONNECT BY over more than one FROM item is not supported yet: write the join as a derived table

ERROR:
ORA-32044: cycle detected while executing recursive WITH query

ERROR:
ORA-00979: not a GROUP BY expression

ERROR:
ORA-00904: "LEVEL": invalid identifier

ERROR:
ORA-01788: CONNECT BY clause required in this query block
```

## See also

[SELECT](select.md) · [WITH](with.md) · [Joins](select-join.md)
