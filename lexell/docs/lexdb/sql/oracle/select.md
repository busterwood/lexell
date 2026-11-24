# SELECT

Reads rows from tables, views, inline views and `DUAL`, and returns them as a result set.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
[ WITH [ RECURSIVE ] query_name [ ( column [, column ]... ) ] AS ( subquery ) [, ...] ]
query_block
    [ { UNION [ ALL ] | INTERSECT [ ALL ] | MINUS [ ALL ] | EXCEPT [ ALL ] } query_block ]...
    [ ORDER BY { expr | position | alias } [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [, ...] ]
    [ OFFSET n { ROW | ROWS } ]
    [ FETCH { FIRST | NEXT } [ n ] { ROW | ROWS } { ONLY | WITH TIES } ]
    [ FOR UPDATE [ OF table_or_alias [, ...] ] [ NOWAIT | SKIP LOCKED ] ]

query_block:
SELECT [ ALL | DISTINCT ] select_list
    [ FROM table_reference [, table_reference ]... ]
    [ WHERE condition ]
    [ hierarchical_query_clause ]
    [ GROUP BY group_by_item [, ...] [ HAVING condition ] ]

select_list:
    { * | { table | alias }.* | expr [ [ AS ] alias ] } [, ...]
```

## Arguments

`WITH`
: Names queries the statement can read. See [WITH](with.md).

`ALL`, `DISTINCT`
: `ALL` keeps duplicate rows and is the default. `DISTINCT` keeps one row of each set of equal rows; two NULLs are
  equal here.

*select_list*
: The columns of the result. `*` is every column of the `FROM` items; `t.*` every column of `t`. A column takes its
  name from `AS` *alias* (or the alias alone), else from the column it shows, else from its expression's text. An
  alias without double quotes is folded to upper case; `"Mixed Case"` keeps its case.

`FROM`
: Tables, views, inline views (`( subquery )`), `LATERAL` and `CROSS APPLY` / `OUTER APPLY` subqueries, and joins of
  them. See [Joins](select-join.md). `FROM DUAL` gives one row; the `FROM` clause may also be left out.

`WHERE`
: Keeps the rows for which the condition is true. `ROWNUM` tests in it are read as a row limit (see Remarks).

`GROUP BY`, `HAVING`
: Groups the rows and filters the groups. See [GROUP BY](select-group-by.md).

*hierarchical_query_clause*
: `START WITH` and `CONNECT BY`. See [Hierarchical queries](hierarchical-queries.md).

`UNION`, `INTERSECT`, `MINUS`, `EXCEPT`
: Combine the rows of two queries, which must have the same number of columns. Without `ALL` duplicates are
  removed. `MINUS` and `EXCEPT` are the same operator. `INTERSECT` binds tighter than the others, which go left to
  right; brackets change that. `ORDER BY` after the last query sorts the whole result; it names a column of the
  first query by its alias or position.

`ORDER BY`
: Sorts the rows. A number is the position of a select-list column. NULLs sort last in ascending order and first in
  descending order; `NULLS FIRST` and `NULLS LAST` change that. Without `ORDER BY` the order is not defined.

`OFFSET`, `FETCH`
: Skip rows and return the next n (1 if n is left out). `WITH TIES` also returns the rows that equal the last row on
  the `ORDER BY` keys.

`FOR UPDATE`
: Locks the rows the query returns until the transaction ends. `NOWAIT` and `SKIP LOCKED` are accepted. `OF`
  names a table or alias.

## Remarks

- The clauses are worked in this order: `FROM`, `WHERE`, `GROUP BY`, `HAVING`, the select list, `DISTINCT`, set
  operators, `ORDER BY`, `OFFSET` and `FETCH`. `WHERE` cannot use a select-list alias; `ORDER BY` can.
- `ROWNUM` numbers the rows as the query produces them, before `ORDER BY`. `WHERE ROWNUM <= n` (also `< n`, `= 1`)
  is a limit: with `ORDER BY` it takes the first n rows and sorts them. To take the top n of a sorted result, sort in
  an inline view and test `ROWNUM` outside, or use `FETCH FIRST`. `ROWNUM = 2` and `ROWNUM > 1` return no rows.
  The limit comes before the aggregates, `GROUP BY`, `HAVING`, `DISTINCT` and `ORDER BY` of the query block, as in
  Oracle (`SELECT COUNT(*) FROM emp WHERE ROWNUM < 4` is 3). `ROWNUM` also works in `UPDATE` and `DELETE`.
- A subquery may stand for a value (one column; no row gives NULL; more than one row is ORA-01427), and be used with
  `IN`, `NOT IN`, `EXISTS`, and with `ANY`, `SOME` and `ALL` after a comparison. `(a, b) IN (subquery)` takes a
  list of columns. A subquery may use the columns of the query around it.
- The empty string is NULL, and `||` ignores NULLs, as in Oracle.
- A table name may carry its owner. Every login has a schema of its own, made at its first connection, and the tables it
  makes are there (`sa.emp`). Without an owner the current schema is searched, then `public`, the PostgreSQL door's
  schema (`public.emp` names one of its tables).
- A syntax error is ORA-00900. An unknown column is ORA-00904, an unknown table ORA-00942, a column that is neither
  grouped nor in an aggregate ORA-00979, and a column name that two `FROM` items have is ORA-00918.

## Differences from Oracle

- `SELECT UNIQUE` is not accepted (ORA-00904); write `DISTINCT`.
- `FETCH FIRST n PERCENT ROWS ONLY` is not supported (ORA-00900), and neither is `FOR UPDATE WAIT n`. `LIMIT n` is
  accepted, which Oracle refuses.
- `FOR UPDATE OF` takes a table or an alias (`OF emp`, `OF e`); Oracle takes columns (`OF e.name`), which lexdb
  answers with ORA-00942. `FOR UPDATE` is refused with `GROUP BY`, aggregates, `DISTINCT` and set operators
  (ORA-03001; Oracle gives ORA-01786 and others). It is accepted on an inline view, which Oracle refuses (ORA-02014).
- `WHERE ROWNUM <= n` is read from the `WHERE` clause of a query block. With one table in `FROM` it limits the rows
  read, before the grouping, as Oracle does. With a join it limits the rows the block returns, so over a join with an
  aggregate or `GROUP BY` it limits the groups, not the rows that are grouped: `SELECT COUNT(*) FROM emp e, dept d
  WHERE e.dept_id = d.id AND ROWNUM < 3` is 4 (Oracle: 2).
- A set operator over columns of different types is not refused: `SELECT id FROM emp UNION SELECT name FROM dept`
  returns numbers and names together as text (Oracle: ORA-01790), though `SELECT 1 ... UNION SELECT 'a' ...` is
  ORA-01722.
- `MIN` and `MAX` of a `DATE` column show as a timestamp with a fraction (`2019-03-01 00:00:00.0`); use `TO_CHAR`.
- `SELECT *` over a `NATURAL JOIN` or `JOIN ... USING` names its columns in lower case; see [Joins](select-join.md).
- Some errors have other numbers: `SELECT DISTINCT name ... ORDER BY salary` is ORA-20000 (Oracle ORA-01791), and
  `ORDER BY` on a column that a set operator's first query does not name is ORA-20000 (Oracle ORA-00904).
- Hints (`/*+ ... */`) are read as comments. `SAMPLE`, `AS OF` (flashback), `PIVOT`, `UNPIVOT`, `MODEL`,
  partitioned outer joins, `XMLTABLE` and `JSON_TABLE` are not supported (ORA-00900).

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

The examples use two tables:

```sql
CREATE TABLE dept (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL);
CREATE TABLE emp (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL, dept_id NUMBER(4) REFERENCES dept (id),
                  mgr_id NUMBER(4), salary NUMBER(8,2), hired DATE);
INSERT INTO dept VALUES (1, 'Sales');
INSERT INTO dept VALUES (2, 'Research');
INSERT INTO dept VALUES (3, 'Legal');
INSERT INTO emp VALUES (1, 'Ann', 1, NULL, 5200, DATE '2019-03-01');
INSERT INTO emp VALUES (2, 'Bob', 1, 1, 4100, DATE '2021-07-15');
INSERT INTO emp VALUES (3, 'Cid', 2, 1, 6100, DATE '2018-01-10');
INSERT INTO emp VALUES (4, 'Dee', 2, 3, 6100, DATE '2022-05-02');
INSERT INTO emp VALUES (5, 'Eve', NULL, 3, 3000, DATE '2024-09-30');
```

### A. The select list, aliases and DUAL

<!-- example: oracle -->
```sql
SELECT 1 + 1 AS two, 'x' || 'y' AS joined FROM DUAL;
SELECT 2 * 3 AS six;
SELECT name AS "Employee Name", salary * 12 yearly FROM emp WHERE id = 2;
SELECT e.*, 1 AS one FROM emp e WHERE e.id = 1;
```

```text
TWO JOINED
--- ------
  2 xy

1 row selected.

SIX
---
  6

1 row selected.

Employee Name YEARLY
------------- ------
Bob            49200

1 row selected.

ID NAME DEPT_ID MGR_ID SALARY HIRED               ONE
-- ---- ------- ------ ------ ------------------- ---
 1 Ann        1          5200 2019-03-01 00:00:00   1

1 row selected.
```

### B. WHERE and DISTINCT

<!-- example: oracle -->
```sql
SELECT name FROM emp WHERE salary BETWEEN 4000 AND 5500 AND name LIKE '_o%' OR dept_id IS NULL ORDER BY name;
SELECT name FROM emp WHERE dept_id IN (1, 3) ORDER BY name;
SELECT DISTINCT dept_id, mgr_id FROM emp ORDER BY 1, 2;
SELECT COUNT(*) AS rows_, COUNT(dept_id) AS with_dept, COUNT(DISTINCT dept_id) AS depts FROM emp;
```

```text
NAME
----
Bob
Eve

2 rows selected.

NAME
----
Ann
Bob

2 rows selected.

DEPT_ID MGR_ID
------- ------
      1      1
      1
      2      1
      2      3
             3

5 rows selected.

ROWS_ WITH_DEPT DEPTS
----- --------- -----
    5         4     2

1 row selected.
```

### C. ORDER BY and NULLS

NULLs sort last in ascending order by default.

<!-- example: oracle -->
```sql
SELECT dept_id, name FROM emp ORDER BY dept_id, name DESC;
SELECT dept_id, name FROM emp ORDER BY dept_id NULLS FIRST, name;
SELECT dept_id, name FROM emp ORDER BY dept_id DESC NULLS LAST, name;
SELECT name, salary AS pay FROM emp ORDER BY pay DESC, 1;
```

```text
DEPT_ID NAME
------- ----
      1 Bob
      1 Ann
      2 Dee
      2 Cid
        Eve

5 rows selected.

DEPT_ID NAME
------- ----
        Eve
      1 Ann
      1 Bob
      2 Cid
      2 Dee

5 rows selected.

DEPT_ID NAME
------- ----
      2 Cid
      2 Dee
      1 Ann
      1 Bob
        Eve

5 rows selected.

NAME  PAY
---- ----
Cid  6100
Dee  6100
Ann  5200
Bob  4100
Eve  3000

5 rows selected.
```

### D. FETCH FIRST, OFFSET and WITH TIES

<!-- example: oracle -->
```sql
SELECT name FROM emp ORDER BY id FETCH FIRST 2 ROWS ONLY;
SELECT name FROM emp ORDER BY id OFFSET 1 ROW FETCH NEXT 2 ROWS ONLY;
SELECT name FROM emp ORDER BY id OFFSET 3 ROWS;
SELECT name, salary FROM emp ORDER BY salary DESC FETCH FIRST 1 ROW WITH TIES;
```

```text
NAME
----
Ann
Bob

2 rows selected.

NAME
----
Bob
Cid

2 rows selected.

NAME
----
Dee
Eve

2 rows selected.

NAME SALARY
---- ------
Cid    6100
Dee    6100

2 rows selected.
```

### E. ROWNUM

`ROWNUM` counts rows before `ORDER BY`. To take the highest paid, sort first in an inline view. With one table in
`FROM`, the limit comes before an aggregate, `GROUP BY`, `HAVING` or `DISTINCT`, so the last four queries read
the first three, three, two and four rows of `emp`.

<!-- example: oracle -->
```sql
SELECT ROWNUM, name FROM emp WHERE ROWNUM <= 3;
SELECT name FROM emp WHERE ROWNUM <= 2 ORDER BY salary;
SELECT name, salary FROM (SELECT name, salary FROM emp ORDER BY salary DESC, name) x WHERE ROWNUM <= 2;
SELECT * FROM (SELECT ROWNUM AS rn, name FROM emp) WHERE rn BETWEEN 2 AND 3;
SELECT name FROM emp WHERE ROWNUM = 2;
SELECT COUNT(*) AS n FROM emp WHERE ROWNUM < 4;
SELECT dept_id, COUNT(*) AS n FROM emp WHERE ROWNUM <= 3 GROUP BY dept_id ORDER BY dept_id;
SELECT DISTINCT dept_id FROM emp WHERE ROWNUM <= 2;
SELECT dept_id, SUM(salary) AS total FROM emp WHERE ROWNUM <= 4 GROUP BY dept_id HAVING SUM(salary) > 6000;
```

```text
ROWNUM NAME
------ ----
     1 Ann
     2 Bob
     3 Cid

3 rows selected.

NAME
----
Bob
Ann

2 rows selected.

NAME SALARY
---- ------
Cid    6100
Dee    6100

2 rows selected.

RN NAME
-- ----
 2 Bob
 3 Cid

2 rows selected.

no rows selected

N
-
3

1 row selected.

DEPT_ID N
------- -
      1 2
      2 1

2 rows selected.

DEPT_ID
-------
      1

1 row selected.

DEPT_ID TOTAL
------- -----
      1  9300
      2 12200

2 rows selected.
```

### F. UNION, INTERSECT and MINUS

<!-- example: oracle -->
```sql
SELECT dept_id FROM emp WHERE dept_id IS NOT NULL UNION SELECT id FROM dept ORDER BY 1;
SELECT dept_id FROM emp WHERE dept_id IS NOT NULL UNION ALL SELECT id FROM dept ORDER BY 1;
SELECT id FROM dept INTERSECT SELECT dept_id FROM emp ORDER BY 1;
SELECT id FROM dept MINUS SELECT dept_id FROM emp;
SELECT id AS n FROM dept UNION ALL (SELECT id FROM dept WHERE id < 3) ORDER BY n DESC FETCH FIRST 3 ROWS ONLY;
```

```text
DEPT_ID
-------
      1
      2
      3

3 rows selected.

DEPT_ID
-------
      1
      1
      1
      2
      2
      2
      3

7 rows selected.

ID
--
 1
 2

2 rows selected.

ID
--
 3

1 row selected.

N
-
3
2
2

3 rows selected.
```

### G. Subqueries

<!-- example: oracle -->
```sql
SELECT name, (SELECT name FROM dept d WHERE d.id = e.dept_id) AS dept FROM emp e ORDER BY id;
SELECT name FROM emp WHERE salary > (SELECT AVG(salary) FROM emp) ORDER BY name;
SELECT name FROM emp e WHERE salary = (SELECT MAX(salary) FROM emp x WHERE x.dept_id = e.dept_id) ORDER BY name;
SELECT name FROM emp WHERE NOT EXISTS (SELECT 1 FROM dept d WHERE d.id = emp.dept_id);
SELECT name FROM emp WHERE dept_id = ANY (SELECT id FROM dept WHERE name = 'Research') ORDER BY name;
SELECT d.name, x.n FROM dept d, LATERAL (SELECT COUNT(*) AS n FROM emp e WHERE e.dept_id = d.id) x ORDER BY d.id;
SELECT (SELECT id FROM dept) AS id FROM dual;
```

```text
NAME DEPT
---- --------
Ann  Sales
Bob  Sales
Cid  Research
Dee  Research
Eve

5 rows selected.

NAME
----
Ann
Cid
Dee

3 rows selected.

NAME
----
Ann
Cid
Dee

3 rows selected.

NAME
----
Eve

1 row selected.

NAME
----
Cid
Dee

2 rows selected.

NAME     N
-------- -
Sales    2
Research 2
Legal    0

3 rows selected.

ERROR:
ORA-01427: single-row subquery returns more than one row
```

### H. FOR UPDATE

A query with `FOR UPDATE` locks its rows until `COMMIT` or `ROLLBACK`.

<!-- example: oracle -->
```sql
SELECT name, salary FROM emp WHERE id = 2 FOR UPDATE;
UPDATE emp SET salary = salary + 100 WHERE id = 2;
COMMIT;
SELECT e.name FROM emp e WHERE e.id = 3 FOR UPDATE OF e NOWAIT;
SELECT name FROM emp WHERE id = 4 FOR UPDATE SKIP LOCKED;
ROLLBACK;
```

```text
NAME SALARY
---- ------
Bob    4100

1 row selected.

1 row updated.

Commit complete.

NAME
----
Cid

1 row selected.

NAME
----
Dee

1 row selected.

Rollback complete.
```

### I. What lexdb does not take, and errors

<!-- example: oracle -->
```sql
SELECT UNIQUE dept_id FROM emp;
SELECT name FROM emp ORDER BY id FETCH FIRST 40 PERCENT ROWS ONLY;
SELECT name FROM emp WHERE id = 2 FOR UPDATE WAIT 5;
SELECT name FROM emp e WHERE id = 2 FOR UPDATE OF e.name;
SELECT name FROM emp GROUP BY name FOR UPDATE;
SELECT name FROM emp ORDER BY 2;
SELECT * FROM emp SAMPLE (50);
SELECT * FROM emp PIVOT (COUNT(*) FOR dept_id IN (1, 2));
SELECT dept_id, name FROM emp GROUP BY dept_id;
SELECT id FROM dept UNION SELECT id, name FROM dept;
SELECT name, nosuch FROM emp;
SELECT * FROM nosuch;
SELECT name FROM dept d, emp e WHERE d.id = e.dept_id;
```

```text
ERROR:
ORA-00904: "UNIQUE": invalid identifier

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00942: table or view does not exist

ERROR:
ORA-03001: unimplemented feature: FOR UPDATE is not allowed with GROUP BY clause

ERROR:
ORA-01785: ORDER BY item must be the number of a SELECT-list expression

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00979: not a GROUP BY expression

ERROR:
ORA-01789: query block has incorrect number of result columns

ERROR:
ORA-00904: "NOSUCH": invalid identifier

ERROR:
ORA-00942: table or view "SA"."NOSUCH" does not exist

ERROR:
ORA-00918: column ambiguously defined
```

## See also

[Joins](select-join.md) · [GROUP BY](select-group-by.md) · [Hierarchical queries](hierarchical-queries.md) · [WITH](with.md) ·
[MATCH_RECOGNIZE](match-recognize.md) · [INSERT](insert.md) · [UPDATE](update.md) · [DELETE](delete.md) · [MERGE](merge.md)
