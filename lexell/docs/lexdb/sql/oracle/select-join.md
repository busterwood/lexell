# SELECT: joins

Combines rows of several tables, views or inline views in the `FROM` clause of a [SELECT](select.md), in the ANSI
form (`JOIN ... ON`, `USING`) and in Oracle's old form (a comma list with the `(+)` outer join marker).

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
table_reference [, table_reference ]...

table_reference:
    { table | view | ( subquery ) | LATERAL ( subquery ) } [ alias ]
  | table_reference [ INNER ] JOIN table_reference { ON condition | USING ( column [, ...] ) }
  | table_reference { LEFT | RIGHT | FULL } [ OUTER ] JOIN table_reference { ON condition | USING ( column [, ...] ) }
  | table_reference CROSS JOIN table_reference
  | table_reference NATURAL [ INNER | LEFT [ OUTER ] | RIGHT [ OUTER ] | FULL [ OUTER ] ] JOIN table_reference
  | table_reference { CROSS | OUTER } APPLY ( subquery ) [ alias ]
  | ( table_reference )

-- the old outer join, in WHERE
WHERE a.column = b.column (+) [ AND ... ]
```

## Arguments

`[ INNER ] JOIN`
: Rows of both sides for which the `ON` condition is true.

`LEFT`, `RIGHT`, `FULL [ OUTER ] JOIN`
: Also the rows of the left, right or both sides that have no partner; the other side's columns are NULL.

`CROSS JOIN`
: Every row of the left side with every row of the right. A comma between two `FROM` items does the same.

`USING (` *column* `)`
: Joins on equal values of the named columns, which both sides have. In the result the column appears once, and it
  is normally named without a qualifier (`SELECT id`); lexdb also accepts `e.id`, which Oracle refuses (ORA-25154).

`NATURAL JOIN`
: A `USING` over every column name that both sides have. With no such name it is a cross join.

`LATERAL`, `CROSS APPLY`, `OUTER APPLY`
: A subquery that may use columns of the `FROM` items to its left. `OUTER APPLY` keeps a left row for which the
  subquery returns no row.

`(+)`
: Marks the optional side of an outer join in `WHERE`: `e.dept_id = d.id (+)` keeps every `e` row, with NULLs when
  there is no `d`. It is the same as `e LEFT JOIN d ON e.dept_id = d.id`.

## Remarks

- A column name that two items share must be qualified, or the query is ORA-00918. In `USING` and `NATURAL JOIN`
  the joined columns are the exception.
- A condition in the `ON` clause of an outer join decides which rows match; a condition in `WHERE` filters the
  joined rows afterwards. `LEFT JOIN d ON ... AND d.name = 'Sales'` keeps every left row, while the same test in
  `WHERE` drops the rows without a partner.
- With `(+)`, the conditions that mark one table, joined to tables before it in the list, move to that table's `ON`
  clause and the table becomes the optional side. Conditions without `(+)` stay in `WHERE`. A marker on the table
  that comes first in the list is ORA-03001. Several conditions that mark the same table all go into its `ON`
  clause, as in Oracle.
- `(+)` is read only in the `WHERE` clause of a `SELECT`.
- Joined rows come in no defined order without `ORDER BY`.

## Differences from Oracle

- `(+)` is taken only when the marked table is listed after the table it is joined to. `FROM emp e, dept d WHERE
  e.dept_id (+) = d.id` (marking `e`, the first table) is ORA-03001; write `FROM dept d, emp e` or a `RIGHT JOIN`.
  The same holds for a marked comparison with a constant (`e.mgr_id (+) = 1`).
- A `(+)` inside an `OR` is not refused (Oracle: ORA-01719): `WHERE e.dept_id = d.id (+) OR e.id = 1` is read as
  one `ON` condition.
- In `SELECT *` over a `NATURAL JOIN` or a `JOIN ... USING`, the column names appear in lower case (`dept_id`, not
  `DEPT_ID`), and a `DATE` column shows with a fraction of a second. A select list that names the columns is not
  affected.
- Partitioned outer joins (`LEFT JOIN d PARTITION BY (...) ON ...`) are not supported (ORA-00900).
- `CROSS APPLY` and `OUTER APPLY` are also taken, as in Oracle 12c and later.

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

The examples use the `emp` and `dept` tables of [SELECT](select.md): five employees, three departments (Legal has
no employee, Eve has no department).

### A. Inner and outer joins

<!-- example: oracle -->
```sql
SELECT e.name, d.name AS dept FROM emp e JOIN dept d ON d.id = e.dept_id ORDER BY e.id;
SELECT e.name, d.name AS dept FROM emp e LEFT JOIN dept d ON d.id = e.dept_id ORDER BY e.id;
SELECT e.name, d.name AS dept FROM emp e RIGHT OUTER JOIN dept d ON d.id = e.dept_id ORDER BY e.id, d.id;
SELECT e.name, d.name AS dept FROM emp e FULL OUTER JOIN dept d ON d.id = e.dept_id ORDER BY e.id, d.id;
```

```text
NAME DEPT
---- --------
Ann  Sales
Bob  Sales
Cid  Research
Dee  Research

4 rows selected.

NAME DEPT
---- --------
Ann  Sales
Bob  Sales
Cid  Research
Dee  Research
Eve

5 rows selected.

NAME DEPT
---- --------
Ann  Sales
Bob  Sales
Cid  Research
Dee  Research
     Legal

5 rows selected.

NAME DEPT
---- --------
Ann  Sales
Bob  Sales
Cid  Research
Dee  Research
Eve
     Legal

6 rows selected.
```

### B. ON or WHERE

A test in `ON` takes part in the match; the same test in `WHERE` filters afterwards.

<!-- example: oracle -->
```sql
SELECT e.name, d.name AS dept FROM emp e LEFT JOIN dept d ON d.id = e.dept_id AND d.name = 'Sales' ORDER BY e.id;
SELECT e.name, d.name AS dept FROM emp e LEFT JOIN dept d ON d.id = e.dept_id WHERE d.name = 'Sales' ORDER BY e.id;
SELECT e.name FROM emp e LEFT JOIN dept d ON d.id = e.dept_id WHERE d.id IS NULL;
```

```text
NAME DEPT
---- -----
Ann  Sales
Bob  Sales
Cid
Dee
Eve

5 rows selected.

NAME DEPT
---- -----
Ann  Sales
Bob  Sales

2 rows selected.

NAME
----
Eve

1 row selected.
```

### C. Self join, several tables, cross join

<!-- example: oracle -->
```sql
SELECT e.name, d.name AS dept, m.name AS boss
FROM emp e INNER JOIN dept d ON d.id = e.dept_id LEFT OUTER JOIN emp m ON m.id = e.mgr_id
ORDER BY e.id;
SELECT a.name, b.name AS better_paid FROM emp a JOIN emp b ON a.salary < b.salary AND a.dept_id = b.dept_id ORDER BY 1, 2;
SELECT COUNT(*) AS pairs FROM emp CROSS JOIN dept;
```

```text
NAME DEPT     BOSS
---- -------- ----
Ann  Sales
Bob  Sales    Ann
Cid  Research Ann
Dee  Research Cid

4 rows selected.

NAME BETTER_PAID
---- -----------
Bob  Ann

1 row selected.

PAIRS
-----
   15

1 row selected.
```

### D. USING and NATURAL JOIN

<!-- example: oracle -->
```sql
SELECT dept_id, d.dept_name, c.n
FROM (SELECT id AS dept_id, name AS dept_name FROM dept) d
FULL OUTER JOIN (SELECT dept_id, COUNT(*) AS n FROM emp GROUP BY dept_id) c USING (dept_id)
ORDER BY dept_id;
SELECT id, e.name FROM emp e JOIN dept d USING (id) ORDER BY id;
SELECT id, name FROM emp NATURAL JOIN dept;
SELECT * FROM emp NATURAL JOIN (SELECT id AS dept_id, name AS dept_name FROM dept) ORDER BY id;
```

```text
DEPT_ID DEPT_NAME N
------- --------- -
      1 Sales     2
      2 Research  2
      3 Legal
                  1

4 rows selected.

ID NAME
-- ----
 1 Ann
 2 Bob
 3 Cid

3 rows selected.

no rows selected

dept_id id name mgr_id salary hired                 dept_name
------- -- ---- ------ ------ --------------------- ---------
      1  1 Ann           5200 2019-03-01 00:00:00.0 Sales
      1  2 Bob       1   4100 2021-07-15 00:00:00.0 Sales
      2  3 Cid       1   6100 2018-01-10 00:00:00.0 Research
      2  4 Dee       3   6100 2022-05-02 00:00:00.0 Research

4 rows selected.
```

### E. The old outer join, (+)

<!-- example: oracle -->
```sql
SELECT e.name, d.name AS dept FROM emp e, dept d WHERE e.dept_id = d.id (+) ORDER BY e.id;
SELECT d.name, e.name AS employee FROM dept d, emp e WHERE e.dept_id (+) = d.id ORDER BY d.id, e.id;
SELECT e.name, d.name AS dept FROM emp e, dept d WHERE e.dept_id = d.id (+) AND d.name (+) = 'Sales' ORDER BY e.id;
SELECT e.name, d.name AS dept, m.name AS boss
FROM emp e, dept d, emp m
WHERE e.dept_id = d.id (+) AND e.mgr_id = m.id (+)
ORDER BY e.id;
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

NAME     EMPLOYEE
-------- --------
Sales    Ann
Sales    Bob
Research Cid
Research Dee
Legal

5 rows selected.

NAME DEPT
---- -----
Ann  Sales
Bob  Sales
Cid
Dee
Eve

5 rows selected.

NAME DEPT     BOSS
---- -------- ----
Ann  Sales
Bob  Sales    Ann
Cid  Research Ann
Dee  Research Cid
Eve           Cid

5 rows selected.
```

### F. LATERAL and APPLY

<!-- example: oracle -->
```sql
SELECT d.name, x.n FROM dept d, LATERAL (SELECT COUNT(*) AS n FROM emp e WHERE e.dept_id = d.id) x ORDER BY d.id;
SELECT d.name, x.top FROM dept d OUTER APPLY (SELECT MAX(salary) AS top FROM emp e WHERE e.dept_id = d.id) x ORDER BY d.id;
```

```text
NAME     N
-------- -
Sales    2
Research 2
Legal    0

3 rows selected.

NAME      TOP
-------- ----
Sales    5200
Research 6100
Legal

3 rows selected.
```

### G. What lexdb does not take

<!-- example: oracle -->
```sql
SELECT e.name, d.name FROM emp e, dept d WHERE e.dept_id (+) = d.id;
SELECT e.name, d.name FROM dept d, emp e WHERE e.dept_id = d.id (+) AND e.mgr_id (+) = 1;
SELECT e.name FROM emp e LEFT JOIN dept d PARTITION BY (e.mgr_id) ON d.id = e.dept_id;
SELECT name, d.name FROM emp JOIN dept d USING (id);
SELECT e.id FROM emp e JOIN dept d USING (id);
```

```text
ERROR:
ORA-03001: unimplemented feature: this use of the old outer join operator (+) is not supported: use LEFT or RIGHT JOIN

ERROR:
ORA-03001: unimplemented feature: this use of the old outer join operator (+) is not supported: use LEFT or RIGHT JOIN

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00918: column ambiguously defined

ID
--
 1
 2
 3

3 rows selected.
```

## See also

[SELECT](select.md) · [GROUP BY](select-group-by.md) · [Hierarchical queries](hierarchical-queries.md) · [WITH](with.md)
