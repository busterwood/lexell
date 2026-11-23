# Joins

Combine the rows of two or more `FROM` items in a [SELECT](select.md).

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
from_item [ NATURAL ] join_type from_item [ ON join_condition | USING ( join_column [, ...] ) ]
from_item CROSS JOIN from_item
from_item, from_item
( joined_table ) [ [ AS ] alias [ ( column_alias [, ...] ) ] ]

join_type:
    [ INNER ] JOIN
    | LEFT [ OUTER ] JOIN
    | RIGHT [ OUTER ] JOIN
    | FULL [ OUTER ] JOIN
```

## Arguments

`[ INNER ] JOIN`
: The pairs of rows for which *join_condition* is true.

`LEFT [ OUTER ] JOIN`
: The inner join's rows, and each row of the left item that has no partner, with NULLs for the right item's
  columns.

`RIGHT [ OUTER ] JOIN`
: The same, keeping every row of the right item.

`FULL [ OUTER ] JOIN`
: The inner join's rows, and the rows of either side that have no partner.

`CROSS JOIN`, and a comma
: Every pair of rows. A comma binds more loosely than `JOIN`: `a, b JOIN c ON ...` joins `b` and `c` first.

`ON` *join_condition*
: Any condition. It may use the columns of both items and of the items before them.

`USING (` *join_column* `, ... )`
: Pairs rows whose columns of these names are equal. Each name is one column in the result, placed first; for a
  `FULL JOIN` it is the value of whichever side has one. The table's own columns can still be named (`a.k`).

`NATURAL`
: `USING` with every column name the two items share.

`LATERAL`
: Before a subquery, lets it use the columns of the items to its left (see [SELECT](select.md)). With
  `LEFT JOIN LATERAL (...) ON true`, a row on the left with no row from the subquery is kept.

`(` *joined_table* `)`
: A join in parentheses, which is joined as one item. With an alias, its columns are known only by the alias.

## Remarks

- A table may be joined to itself under two aliases.
- A column name used by two items must be qualified: `column reference "k" is ambiguous` (42702) otherwise.
- The planner chooses the join order, and for each join an index lookup per row or a hash join, by cost. `SET
  lexdb_planner = rules` gives the older rule-based plans.
- A condition in `WHERE` on the right item of a `LEFT JOIN` removes the rows the join added with NULLs; put it in
  `ON` to keep them.

## Differences from PostgreSQL

- An alias for a `USING` join (`JOIN b USING (k) AS j`, PostgreSQL 14) is not supported (0A000, lexdb-gaps.md 2.2).
- In a `FULL JOIN ... USING (k)`, a select list that names `k` gets a column named `coalesce`; PostgreSQL names it
  `k` (example D). `SELECT *` names it `k`. Write `k AS k` to keep the name.
- In `FROM a, b JOIN c ON ...`, the `ON` condition may use `a`'s columns. PostgreSQL refuses it (42P01, `invalid
  reference to FROM-clause entry for table "a"`).

## Examples

<!--setup: postgresql
CREATE TABLE dept (id int PRIMARY KEY, name text NOT NULL);
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept_id int REFERENCES dept, salary numeric(8,2), manager_id int);
INSERT INTO dept VALUES (1, 'sales'), (2, 'research'), (3, 'admin');
INSERT INTO emp VALUES (1, 'ada', 2, 5200, NULL), (2, 'ben', 1, 3100, 1), (3, 'cy', 1, 2900, 2), (4, 'dee', 2, 4800, 1), (5, 'eve', NULL, 2500, 1);
-->

The examples use two tables:

```sql
CREATE TABLE dept (id int PRIMARY KEY, name text NOT NULL);
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept_id int REFERENCES dept, salary numeric(8,2),
                  manager_id int);
INSERT INTO dept VALUES (1, 'sales'), (2, 'research'), (3, 'admin');
INSERT INTO emp VALUES (1, 'ada', 2, 5200, NULL), (2, 'ben', 1, 3100, 1), (3, 'cy', 1, 2900, 2),
  (4, 'dee', 2, 4800, 1), (5, 'eve', NULL, 2500, 1);
```

### A. Inner join

<!-- example: postgresql -->
```sql
SELECT e.name, d.name AS dept
FROM emp e JOIN dept d ON d.id = e.dept_id
ORDER BY e.name;
```

```text
 name |   dept
------+----------
 ada  | research
 ben  | sales
 cy   | sales
 dee  | research
(4 rows)
```

### B. Outer joins

`eve` has no department and `admin` has no employees.

<!-- example: postgresql -->
```sql
SELECT e.name, d.name AS dept FROM emp e LEFT JOIN dept d ON d.id = e.dept_id ORDER BY e.name;
SELECT e.name, d.name AS dept FROM emp e RIGHT JOIN dept d ON d.id = e.dept_id ORDER BY d.name, e.name;
SELECT e.name, d.name AS dept FROM emp e FULL JOIN dept d ON d.id = e.dept_id ORDER BY d.name, e.name;
```

```text
 name |   dept
------+----------
 ada  | research
 ben  | sales
 cy   | sales
 dee  | research
 eve  |
(5 rows)

 name |   dept
------+----------
      | admin
 ada  | research
 dee  | research
 ben  | sales
 cy   | sales
(5 rows)

 name |   dept
------+----------
      | admin
 ada  | research
 dee  | research
 ben  | sales
 cy   | sales
 eve  |
(6 rows)
```

### C. A condition in ON, or in WHERE

<!-- example: postgresql -->
```sql
SELECT d.name, e.name FROM dept d LEFT JOIN emp e ON e.dept_id = d.id AND e.salary > 3000 ORDER BY d.name, e.name;
SELECT d.name, e.name FROM dept d LEFT JOIN emp e ON e.dept_id = d.id WHERE e.salary > 3000 ORDER BY d.name, e.name;
```

```text
   name   | name
----------+------
 admin    |
 research | ada
 research | dee
 sales    | ben
(4 rows)

   name   | name
----------+------
 research | ada
 research | dee
 sales    | ben
(3 rows)
```

### D. USING and NATURAL

<!-- example: postgresql -->
```sql
CREATE TABLE a (k int, x text);
CREATE TABLE b (k int, y text);
INSERT INTO a VALUES (1, 'a1'), (2, 'a2');
INSERT INTO b VALUES (2, 'b2'), (3, 'b3');
SELECT * FROM a JOIN b USING (k);
SELECT * FROM a NATURAL FULL JOIN b ORDER BY k;
SELECT a.k AS a_k, b.k AS b_k, k FROM a FULL JOIN b USING (k) ORDER BY k;
```

```text
CREATE TABLE
CREATE TABLE
INSERT 0 2
INSERT 0 2
 k | x  | y
---+----+----
 2 | a2 | b2
(1 row)

 k | x  | y
---+----+----
 1 | a1 |
 2 | a2 | b2
 3 |    | b3
(3 rows)

 a_k | b_k | coalesce
-----+-----+----------
   1 |     |        1
   2 |   2 |        2
     |   3 |        3
(3 rows)
```

### E. A self-join

<!-- example: postgresql -->
```sql
SELECT m.name AS manager, e.name
FROM emp e JOIN emp m ON m.id = e.manager_id
ORDER BY manager, e.name;
```

```text
 manager | name
---------+------
 ada     | ben
 ada     | dee
 ada     | eve
 ben     | cy
(4 rows)
```

### F. CROSS JOIN and a join that is not on equality

<!-- example: postgresql -->
```sql
SELECT count(*) FROM emp CROSS JOIN dept;
SELECT a.k AS a_k, b.k AS b_k FROM a JOIN b ON a.k < b.k ORDER BY a_k, b_k;
```

```text
 count
-------
    15
(1 row)

 a_k | b_k
-----+-----
   1 |   2
   1 |   3
   2 |   3
(3 rows)
```

### G. LEFT JOIN LATERAL

<!-- example: postgresql -->
```sql
SELECT d.name, x.n, x.top
FROM dept d
LEFT JOIN LATERAL (SELECT count(*) AS n, max(salary) AS top FROM emp WHERE dept_id = d.id) x ON true
ORDER BY d.name;
```

```text
   name   | n |   top
----------+---+---------
 admin    | 0 |
 research | 2 | 5200.00
 sales    | 2 | 3100.00
(3 rows)
```

### H. A join in parentheses, with an alias

<!-- example: postgresql -->
```sql
SELECT * FROM (a JOIN b ON a.k = b.k) AS j(k1, x, k2, y);
```

```text
 k1 | x  | k2 | y
----+----+----+----
  2 | a2 |  2 | b2
(1 row)
```

### I. Errors

<!-- example: postgresql -->
```sql
SELECT k FROM a JOIN b ON a.k = b.k;
SELECT * FROM a JOIN b USING (k) AS j;
```

```text
ERROR:  column reference "k" is ambiguous
ERROR:  lexdb: an alias for JOIN ... USING is not supported
```

## See also

[SELECT](select.md) · [GROUP BY](select-group-by.md) · [WITH](with.md) · [UPDATE](update.md) ·
[DELETE](delete.md) · [MERGE](merge.md)
