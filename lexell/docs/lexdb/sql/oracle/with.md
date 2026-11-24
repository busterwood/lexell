# WITH

Names subqueries (subquery factoring) that the statement's query can read, and writes recursive queries.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
WITH [ RECURSIVE ]
    query_name [ ( column [, column ]... ) ] AS ( subquery )
    [, query_name [ ( column [, column ]... ) ] AS ( subquery ) ]...
    [ search_clause ]
    [ cycle_clause ]
query

search_clause:
    SEARCH { DEPTH | BREADTH } FIRST BY column [ ASC | DESC ] [, ...] SET ordering_column

cycle_clause:
    CYCLE column [, column ]... SET cycle_mark_column TO cycle_value DEFAULT no_cycle_value
```

A recursive query name has the form

```
name ( column, ... ) AS ( anchor_query UNION ALL recursive_query )
```

where the recursive query reads *name* in its `FROM` clause.

## Arguments

*query_name*
: The name the main query and later `WITH` items use for the result of the subquery. Naming one twice is an error.

*column*
: Names for the result's columns. Without a list the subquery's own column names are used. A recursive query needs
  the list (ORA-32039).

*anchor_query*
: The rows the recursion starts from. It does not read *name*.

*recursive_query*
: Joins *name* (the rows of the last round) to other tables and gives the next round. The recursion ends when a
  round gives no row.

`SEARCH`
: Adds *ordering_column*, the position of each row in a depth-first or breadth-first walk of the tree, with sibling
  rows ordered by the `BY` columns. Sort by it in the main query.

`CYCLE`
: Stops following a row whose values of the `CYCLE` columns already appeared on its path, and marks that row in
  *cycle_mark_column* with *cycle_value* (other rows have *no_cycle_value*). Without it, a loop in the data gives
  ORA-32044.

`RECURSIVE`
: Accepted before the first name (PostgreSQL's form). Oracle does not have the word.

## Remarks

- A `WITH` query may be read several times by the main query. Each name sees the names before it.
- A recursive `WITH` must use `UNION ALL`: `UNION` gives ORA-32040.
- `WITH` may stand in front of a query inside a view, an inline view, and the subquery of `INSERT`, `UPDATE` or
  `DELETE`.
- Comments with hints (`/*+ MATERIALIZE */`) are ignored.
- A recursion that never ends is ORA-32044, also under `FETCH FIRST` (a row limit does not stop it, as in Oracle):
  bound the recursive term (`WHERE n < 10`), as example B does.

## Differences from Oracle

- `WITH FUNCTION ...` and `WITH PROCEDURE ...` (PL/SQL declared in the statement) are not supported (ORA-00900).
- A statement that begins with `WITH` must be a query. `WITH ... INSERT` is not Oracle syntax either; write
  `INSERT INTO t WITH ... SELECT ...`.
- The text of some errors differs: a column list longer than the query's gives ORA-20000 and lexdb's text (Oracle
  ORA-32038), and a name used twice also ORA-20000 (Oracle ORA-32039).

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

### A. Subquery factoring

<!-- example: oracle -->
```sql
WITH dept_pay AS (SELECT dept_id, SUM(salary) AS total FROM emp GROUP BY dept_id)
SELECT d.name, p.total FROM dept d JOIN dept_pay p ON p.dept_id = d.id ORDER BY d.id;
WITH a AS (SELECT dept_id, COUNT(*) AS n FROM emp GROUP BY dept_id),
     b AS (SELECT dept_id, n FROM a WHERE n > 1)
SELECT * FROM b ORDER BY dept_id;
WITH pay (d, t) AS (SELECT dept_id, SUM(salary) FROM emp GROUP BY dept_id) SELECT d, t FROM pay ORDER BY d;
WITH avg_pay AS (SELECT AVG(salary) AS a FROM emp) SELECT name FROM emp, avg_pay WHERE salary > a ORDER BY name;
```

```text
NAME     TOTAL
-------- -----
Sales     9300
Research 12200

2 rows selected.

DEPT_ID N
------- -
      1 2
      2 2

2 rows selected.

D     T
- -----
1  9300
2 12200
   3000

3 rows selected.

NAME
----
Ann
Cid
Dee

3 rows selected.
```

### B. A series of numbers

<!-- example: oracle -->
```sql
WITH nums (n) AS (SELECT 1 FROM dual UNION ALL SELECT n + 1 FROM nums WHERE n < 5) SELECT n FROM nums;
WITH nums (n) AS (SELECT 1 FROM dual UNION ALL SELECT n + 1 FROM nums WHERE n < 5) SELECT SUM(n) AS total FROM nums;
WITH RECURSIVE r (n) AS (SELECT 1 FROM dual UNION ALL SELECT n + 1 FROM r WHERE n < 3) SELECT n FROM r;
WITH f (n, fact) AS (SELECT 1, 1 FROM dual UNION ALL SELECT n + 1, fact * (n + 1) FROM f WHERE n < 6)
SELECT n, fact FROM f ORDER BY n;
WITH days (d) AS (SELECT DATE '2026-03-01' FROM dual UNION ALL SELECT d + 1 FROM days WHERE d < DATE '2026-03-04')
SELECT TO_CHAR(d, 'Dy DD') AS day FROM days;
```

```text
N
-
1
2
3
4
5

5 rows selected.

TOTAL
-----
   15

1 row selected.

N
-
1
2
3

3 rows selected.

N FACT
- ----
1    1
2    2
3    6
4   24
5  120
6  720

6 rows selected.

DAY
------
Sun 01
Mon 02
Tue 03
Wed 04

4 rows selected.
```

### C. A tree, with its path

<!-- example: oracle -->
```sql
WITH tree (id, name, lvl, path) AS (
  SELECT id, name, 1, name FROM emp WHERE mgr_id IS NULL
  UNION ALL
  SELECT e.id, e.name, t.lvl + 1, t.path || '/' || e.name FROM emp e JOIN tree t ON e.mgr_id = t.id)
SELECT lvl, path FROM tree ORDER BY path;
```

```text
LVL PATH
--- -----------
  1 Ann
  2 Ann/Bob
  2 Ann/Cid
  3 Ann/Cid/Dee
  3 Ann/Cid/Eve

5 rows selected.
```

### D. SEARCH

Ordering by name, depth first and breadth first walk the tree in different orders.

<!-- example: oracle -->
```sql
WITH tree (id, name, lvl) AS (
  SELECT id, name, 1 FROM emp WHERE mgr_id IS NULL
  UNION ALL
  SELECT e.id, e.name, t.lvl + 1 FROM emp e JOIN tree t ON e.mgr_id = t.id)
SEARCH DEPTH FIRST BY name DESC SET ord
SELECT lvl, name, ord FROM tree ORDER BY ord;
WITH tree (id, name, lvl) AS (
  SELECT id, name, 1 FROM emp WHERE mgr_id IS NULL
  UNION ALL
  SELECT e.id, e.name, t.lvl + 1 FROM emp e JOIN tree t ON e.mgr_id = t.id)
SEARCH BREADTH FIRST BY name DESC SET ord
SELECT lvl, name, ord FROM tree ORDER BY ord;
```

```text
LVL NAME ORD
--- ---- ---
  1 Ann    1
  2 Cid    2
  3 Eve    3
  3 Dee    4
  2 Bob    5

5 rows selected.

LVL NAME ORD
--- ---- ---
  1 Ann    1
  2 Cid    2
  2 Bob    3
  3 Eve    4
  3 Dee    5

5 rows selected.
```

### E. CYCLE

<!-- example: oracle -->
```sql
CREATE TABLE edge (a NUMBER, b NUMBER);
INSERT INTO edge VALUES (1, 2);
INSERT INTO edge VALUES (2, 3);
INSERT INTO edge VALUES (3, 1);
INSERT INTO edge VALUES (3, 4);
COMMIT;
WITH g (a, b) AS (SELECT a, b FROM edge WHERE a = 1 UNION ALL SELECT e.a, e.b FROM edge e JOIN g ON e.a = g.b)
SELECT a, b FROM g;
WITH g (a, b) AS (SELECT a, b FROM edge WHERE a = 1 UNION ALL SELECT e.a, e.b FROM edge e JOIN g ON e.a = g.b)
CYCLE a SET is_cycle TO 'Y' DEFAULT 'N'
SELECT a, b, is_cycle FROM g;
```

```text
Table created.

1 row created.

1 row created.

1 row created.

1 row created.

Commit complete.

ERROR:
ORA-32044: cycle detected while executing recursive WITH query

A B IS_CYCLE
- - --------
1 2 N
2 3 N
3 1 N
3 4 N
1 2 Y

5 rows selected.
```

### F. WITH inside other statements

<!-- example: oracle -->
```sql
INSERT INTO dept WITH t AS (SELECT 99 AS id, 'Zed' AS name FROM dual) SELECT id, name FROM t;
UPDATE emp SET salary = salary + 1 WHERE id IN (WITH s AS (SELECT 1 AS id FROM dual) SELECT id FROM s);
SELECT * FROM (WITH t AS (SELECT 1 AS a FROM dual) SELECT a FROM t);
CREATE VIEW one AS WITH t AS (SELECT 1 AS a FROM dual) SELECT a FROM t;
SELECT * FROM one;
ROLLBACK;
```

```text
1 row created.

1 row updated.

A
-
1

1 row selected.

View created.

A
-
1

1 row selected.

Rollback complete.
```

### G. Errors and what lexdb does not take

<!-- example: oracle -->
```sql
WITH nums AS (SELECT 1 AS n FROM dual UNION ALL SELECT n + 1 FROM nums WHERE n < 3) SELECT n FROM nums;
WITH nums (n) AS (SELECT 1 FROM dual UNION SELECT n + 1 FROM nums WHERE n < 3) SELECT n FROM nums;
WITH t (a, b) AS (SELECT 1 FROM dual) SELECT * FROM t;
WITH t AS (SELECT 1 AS a FROM dual), t AS (SELECT 2 AS a FROM dual) SELECT * FROM t;
WITH FUNCTION twice(x NUMBER) RETURN NUMBER IS BEGIN RETURN x * 2; END; SELECT twice(4) FROM dual;
WITH nums (n) AS (SELECT 1 FROM dual UNION ALL SELECT n + 1 FROM nums) SELECT n FROM nums FETCH FIRST 3 ROWS ONLY;
WITH nums (n) AS (SELECT 1 FROM dual UNION ALL SELECT n + 1 FROM nums) SELECT n FROM nums WHERE n > 2 FETCH FIRST 3 ROWS ONLY;
```

```text
ERROR:
ORA-32039: missing column alias list in recursive WITH clause element NUMS

ERROR:
ORA-32040: missing UNION ALL in recursive WITH clause element NUMS

ERROR:
ORA-20000: table "t" has 1 columns available but 2 columns specified

ERROR:
ORA-20000: WITH query name "t" specified more than once

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-32044: cycle detected while executing recursive WITH query

ERROR:
ORA-32044: cycle detected while executing recursive WITH query
```

## See also

[SELECT](select.md) · [Hierarchical queries](hierarchical-queries.md) · [Joins](select-join.md)
