# QUALIFY

Filters the rows of a query on the result of a window function, after the window step.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26).

## Syntax

```
SELECT [ ALL | DISTINCT ] select_list
    FROM table_reference [, ...]
    [ WHERE condition ]
    [ GROUP BY group_by_item [, ...] [ HAVING condition ] ]
    [ WINDOW window_name AS ( window_spec ) [, ...] ]
    [ QUALIFY condition ]
    [ ORDER BY ... ] [ OFFSET ... ] [ FETCH ... ]
```

`QUALIFY` comes after `WHERE`, `GROUP BY`, `HAVING` and `WINDOW`, and before `DISTINCT`, `ORDER BY`, `OFFSET` and
`FETCH`. See [SELECT](select.md) for the rest of the statement and [Analytic functions](functions-analytic.md) for
the window functions.

## Arguments

*condition*
: An expression that is true for the rows to keep. It may call window functions (`ROW_NUMBER() OVER (...)`) and
  aggregates, and name the select list's aliases. A row for which it is not true is dropped.

## Remarks

- A window function cannot be used in `WHERE`, because `WHERE` is worked before the windows. `QUALIFY` is worked
  after them, so it keeps the first row of each group, the top n, or the rows above a running total without an
  inline view around the query.
- The order of work is `FROM`, `WHERE`, `GROUP BY`, `HAVING`, the window functions, `QUALIFY`, `DISTINCT`, `ORDER BY`,
  `OFFSET` and `FETCH`. A row `QUALIFY` drops is not seen by `DISTINCT`, and does not count for `FETCH FIRST`.
- A name in the condition is first a select-list alias, then a column. `SELECT id AS x, v AS id ... QUALIFY id = 1`
  tests the column `v`, the one the alias `id` stands for. Two select items with the same alias make the name
  ambiguous: ORA-00960. A select item with no alias is not an alias: a join's `id` that both tables have is
  ORA-00918.
- The window functions in the condition may be over aggregates of a `GROUP BY` query
  (`QUALIFY RANK() OVER (ORDER BY SUM(salary) DESC) = 1`).
- A query with no window function at all treats `QUALIFY` as `WHERE`, or as `HAVING` when it has a `GROUP BY`.
- `HAVING`, `WINDOW` or a second `QUALIFY` after the condition is ORA-03049. `ORDER BY` before `QUALIFY` is
  ORA-00900.
- `QUALIFY` is not a reserved word. Where no condition follows it, it is a table alias: `FROM emp qualify`.
- In a set operation each query has its own `QUALIFY`, and an alias of one is not visible in another.

## Differences from Oracle

- Oracle added `QUALIFY` in 23.26.0; the 23ai releases before it have none.
- `QUALIFY` is not read after `CONNECT BY`: a hierarchical query with it is ORA-00900 (example J).
- A condition that is a number or a text is read as `WHERE` reads it, which is as no row: `QUALIFY 1` and
  `QUALIFY id - 1` return no rows (Oracle: not zero is true, so `QUALIFY 1` returns every row; a text is ORA-61800).
  Write the comparison (`QUALIFY id <> 1`).
- `FOR UPDATE` after `QUALIFY` is accepted when the query has no window function, and is ORA-03001 when it has one
  (Oracle: ORA-01786 in both cases).
- The text of ORA-03049 is shorter than Oracle's: it names the first word of the condition, not the whole of it.
- PostgreSQL and SQL Server have no `QUALIFY`; the same query there is an inline view with a `WHERE`.

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
COMMIT;
```

### A. The best-paid employee of each department

<!-- example: oracle -->
```sql
SELECT name, dept_id, salary FROM emp
QUALIFY RANK() OVER (PARTITION BY dept_id ORDER BY salary DESC) = 1
ORDER BY dept_id, name;
```

```text
NAME DEPT_ID SALARY
---- ------- ------
Ann        1   5200
Cid        2   6100
Dee        2   6100
Eve            3000

4 rows selected.
```

### B. A select-list alias in the condition

<!-- example: oracle -->
```sql
SELECT name, dept_id, ROW_NUMBER() OVER (PARTITION BY dept_id ORDER BY hired) AS rn FROM emp
QUALIFY rn = 1
ORDER BY dept_id;
```

```text
NAME DEPT_ID RN
---- ------- --
Ann        1  1
Cid        2  1
Eve           1

3 rows selected.
```

### C. Before ORDER BY, DISTINCT and FETCH

<!-- example: oracle -->
```sql
SELECT name, salary FROM emp
QUALIFY ROW_NUMBER() OVER (ORDER BY salary DESC, id) <= 3
ORDER BY name;
SELECT DISTINCT salary FROM emp
QUALIFY salary > 4000
ORDER BY salary DESC
FETCH FIRST 2 ROWS ONLY;
```

```text
NAME SALARY
---- ------
Ann    5200
Cid    6100
Dee    6100

3 rows selected.

SALARY
------
  6100
  5200

2 rows selected.
```

### D. Aggregates in the condition

<!-- example: oracle -->
```sql
SELECT dept_id, SUM(salary) AS total FROM emp
GROUP BY dept_id
QUALIFY RANK() OVER (ORDER BY SUM(salary) DESC) <= 2
ORDER BY total DESC;
```

```text
DEPT_ID TOTAL
------- -----
      2 12200
      1  9300

2 rows selected.
```

### E. A named window

<!-- example: oracle -->
```sql
SELECT name, dept_id, salary FROM emp
WINDOW w AS (PARTITION BY dept_id ORDER BY salary DESC, id)
QUALIFY ROW_NUMBER() OVER w = 1
ORDER BY dept_id;
```

```text
NAME DEPT_ID SALARY
---- ------- ------
Ann        1   5200
Cid        2   6100
Eve            3000

3 rows selected.
```

### F. A query with no window function

<!-- example: oracle -->
```sql
SELECT name, salary FROM emp
QUALIFY salary > 5000
ORDER BY name;
SELECT dept_id, COUNT(*) AS staff FROM emp
GROUP BY dept_id
QUALIFY COUNT(*) > 1
ORDER BY dept_id;
```

```text
NAME SALARY
---- ------
Ann    5200
Cid    6100
Dee    6100

3 rows selected.

DEPT_ID STAFF
------- -----
      1     2
      2     2

2 rows selected.
```

### G. QUALIFY as a table alias

<!-- example: oracle -->
```sql
SELECT qualify.name FROM emp qualify WHERE qualify.id = 1;
```

```text
NAME
----
Ann

1 row selected.
```

### H. In a derived table, and with UNION

<!-- example: oracle -->
```sql
SELECT name FROM (
  SELECT name, ROW_NUMBER() OVER (ORDER BY hired) AS n FROM emp QUALIFY n <= 2
) ORDER BY name;
SELECT name FROM emp QUALIFY ROW_NUMBER() OVER (ORDER BY id) = 1
UNION ALL
SELECT name FROM emp QUALIFY ROW_NUMBER() OVER (ORDER BY id DESC) = 1;
```

```text
NAME
----
Ann
Cid

2 rows selected.

NAME
----
Ann
Eve

2 rows selected.
```

### I. Errors

<!-- example: oracle -->
```sql
SELECT salary AS x, id AS x FROM emp QUALIFY x > 4000;
SELECT name FROM emp QUALIFY salary > 4000 HAVING COUNT(*) > 0;
SELECT name FROM emp QUALIFY salary > 4000 QUALIFY id > 1;
SELECT name, id FROM emp ORDER BY id QUALIFY id > 1;
SELECT e.name FROM emp e, dept d QUALIFY id > 1;
```

```text
ERROR:
ORA-00960: ambiguous column naming in select list

ERROR:
ORA-03049: SQL keyword 'SALARY' is not syntactically valid following 'qualify '

ERROR:
ORA-03049: SQL keyword 'SALARY' is not syntactically valid following 'qualify '

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00918: column ambiguously defined
```

### J. Where lexdb differs

<!-- example: oracle -->
```sql
SELECT name FROM emp QUALIFY 1;
SELECT name FROM emp QUALIFY id <> 1 ORDER BY name FOR UPDATE;
SELECT name FROM emp QUALIFY ROW_NUMBER() OVER (ORDER BY id) = 1 FOR UPDATE;
SELECT name, LEVEL FROM emp START WITH id = 1 CONNECT BY PRIOR id = mgr_id QUALIFY id > 2;
```

```text
no rows selected

NAME
----
Bob
Cid
Dee
Eve

4 rows selected.

ERROR:
ORA-03001: unimplemented feature: FOR UPDATE is not allowed with window functions

ERROR:
ORA-00900: invalid SQL statement
```

## See also

[SELECT](select.md) · [Analytic functions](functions-analytic.md) · [GROUP BY](select-group-by.md) ·
[Hierarchical queries](hierarchical-queries.md)
