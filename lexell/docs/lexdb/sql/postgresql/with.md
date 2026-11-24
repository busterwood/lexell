# WITH

Names queries, common table expressions, for one statement to read; `WITH RECURSIVE` lets a query read its own
rows.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
WITH [ RECURSIVE ] with_query [, ...]
{ SELECT ... | ( SELECT ... ) | INSERT ... | UPDATE ... | DELETE ... | MERGE ... }

with_query:
    name [ ( column_name [, ...] ) ] AS [ [ NOT ] MATERIALIZED ] ( query )
        [ SEARCH { BREADTH | DEPTH } FIRST BY column_name [, ...] SET search_seq_col_name ]
        [ CYCLE column_name [, ...] SET cycle_mark_col_name [ TO cycle_mark_value DEFAULT cycle_mark_default ]
              USING cycle_path_col_name ]

recursive query:
    non_recursive_term UNION [ ALL ] recursive_term
```

## Arguments

*name*
: The name the statement uses for the query's rows, as for a table. It hides a table of the same name.

*column_name*
: Names for the query's columns. Without them, the columns are named as the query names them.

`MATERIALIZED`, `NOT MATERIALIZED`
: Accepted. The planner decides how the query is run.

*query*
: A `SELECT` or `VALUES`. Each query may read the ones listed before it.

`RECURSIVE`
: Lets a query read its own name. Such a query is a *non-recursive term*, `UNION` or `UNION ALL`, and a *recursive
  term* that reads the name once. The first term's rows are the start; the second runs again on the rows the last
  round added, until a round adds none. With `UNION`, rows already found are not added again, which ends a walk
  around a cycle.

`SEARCH DEPTH FIRST BY` *columns* `SET` *col*
: Adds a column *col* whose order (`ORDER BY col`) is depth first: each row comes before the rows found from it.

`SEARCH BREADTH FIRST BY` *columns* `SET` *col*
: The same, breadth first: by the round that found the row, then by *columns*.

`CYCLE` *columns* `SET` *mark* `USING` *path*
: Detects cycles. *path* is an array of the *columns* of the rows that led to the row; a row whose *columns* are
  already in its path has *mark* true (or *cycle_mark_value*) and is not followed further. Other rows have *mark*
  false (or *cycle_mark_default*).

## Remarks

- A `WITH` query is part of its statement: it sees the same snapshot, and a statement after `WITH` may be `INSERT`,
  `UPDATE`, `DELETE` or `MERGE` as well as `SELECT`.
- A recursive query stops with 54001 after `max_recursion` rounds (1000 by default) that still add rows. `SET
  max_recursion = n` changes the limit; 0 is no limit. A constant `LIMIT` on a plain `SELECT` of the query ends it
  sooner, when it has the rows.
- A recursive term may not read its own name in a subquery (42P19), as in PostgreSQL.

## Differences from PostgreSQL

- Data-modifying statements in `WITH` (`WITH d AS (DELETE ... RETURNING *) SELECT ...`) are not supported (42601,
  lexdb-gaps.md 2.2).
- A recursive query stops at a `LIMIT` only when the statement is a plain `SELECT` of the query with a constant
  `LIMIT` (and `OFFSET`): `SELECT * FROM r LIMIT 3` gives three rows. With a `WHERE`, a join, grouping, `DISTINCT`,
  `ORDER BY` or an enclosing query block, PostgreSQL still stops when it has the rows, and lexdb runs the recursion
  until `max_recursion` and fails with 54001. Put the bound in the recursive term (`WHERE n < 3`).
- A recursive term with an aggregate, a window function, `ORDER BY`, or an outer join that has its own name on the
  nullable side is not refused, as PostgreSQL refuses it (42P19, 0A000). Such a query usually never stops adding
  rows, and ends with 54001 at `max_recursion`.
- With `RECURSIVE`, a query of the list may not read one listed after it (42P01); PostgreSQL allows it.
- PostgreSQL has no `max_recursion` setting; it recurses until the query ends or runs out of memory.
- `WITH ... VALUES ...` (a `VALUES` statement after `WITH`) is a syntax error. `VALUES` works as a `WITH` query, and
  after `WITH` in a `SELECT * FROM (VALUES ...)`.

## Examples

<!--setup: postgresql
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept_id int, salary numeric(8,2), manager_id int);
INSERT INTO emp VALUES (1, 'ada', 2, 5200, NULL), (2, 'ben', 1, 3100, 1), (3, 'cy', 1, 2900, 2), (4, 'dee', 2, 4800, 1), (5, 'eve', NULL, 2500, 1), (6, 'fay', 1, 2700, 3);
-->

The examples use one table:

```sql
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept_id int, salary numeric(8,2), manager_id int);
INSERT INTO emp VALUES (1, 'ada', 2, 5200, NULL), (2, 'ben', 1, 3100, 1), (3, 'cy', 1, 2900, 2),
  (4, 'dee', 2, 4800, 1), (5, 'eve', NULL, 2500, 1), (6, 'fay', 1, 2700, 3);
```

### A. Naming a query

<!-- example: postgresql -->
```sql
WITH dept_pay AS (
    SELECT dept_id, sum(salary) AS total FROM emp WHERE dept_id IS NOT NULL GROUP BY dept_id
)
SELECT e.name, e.salary, round(100 * e.salary / d.total) AS pct
FROM emp e JOIN dept_pay d USING (dept_id)
ORDER BY e.name;
```

```text
 name | salary  | pct
------+---------+-----
 ada  | 5200.00 |  52
 ben  | 3100.00 |  36
 cy   | 2900.00 |  33
 dee  | 4800.00 |  48
 fay  | 2700.00 |  31
(5 rows)
```

### B. Several queries, one reading another

<!-- example: postgresql -->
```sql
WITH a AS (SELECT avg(salary) AS pay FROM emp),
     b (name, over_by) AS (SELECT name, salary - a.pay FROM emp, a WHERE salary > a.pay)
SELECT name, round(over_by, 2) FROM b ORDER BY name;
```

```text
 name |  round
------+---------
 ada  | 1666.67
 dee  | 1266.67
(2 rows)
```

### C. Counting with RECURSIVE

<!-- example: postgresql -->
```sql
WITH RECURSIVE r(n) AS (
    SELECT 1
    UNION ALL
    SELECT n + 1 FROM r WHERE n < 5
)
SELECT * FROM r;
```

```text
 n
---
 1
 2
 3
 4
 5
(5 rows)
```

### D. Walking a hierarchy

Everyone under `ben`, with their depth below him.

<!-- example: postgresql -->
```sql
WITH RECURSIVE under (id, name, depth) AS (
    SELECT id, name, 0 FROM emp WHERE name = 'ben'
    UNION ALL
    SELECT e.id, e.name, u.depth + 1 FROM emp e JOIN under u ON e.manager_id = u.id
)
SELECT * FROM under ORDER BY depth, name;
```

```text
 id | name | depth
----+------+-------
  2 | ben  |     0
  3 | cy   |     1
  6 | fay  |     2
(3 rows)
```

### E. SEARCH DEPTH FIRST and BREADTH FIRST

<!-- example: postgresql -->
```sql
WITH RECURSIVE t (id, name) AS (
    SELECT id, name FROM emp WHERE manager_id IS NULL
    UNION ALL
    SELECT e.id, e.name FROM emp e JOIN t ON e.manager_id = t.id
) SEARCH DEPTH FIRST BY id SET ord
SELECT id, name, ord FROM t ORDER BY ord;

WITH RECURSIVE t (id, name) AS (
    SELECT id, name FROM emp WHERE manager_id IS NULL
    UNION ALL
    SELECT e.id, e.name FROM emp e JOIN t ON e.manager_id = t.id
) SEARCH BREADTH FIRST BY id SET ord
SELECT id, name FROM t ORDER BY ord;
```

```text
 id | name |        ord
----+------+-------------------
  1 | ada  | {(1)}
  2 | ben  | {(1),(2)}
  3 | cy   | {(1),(2),(3)}
  6 | fay  | {(1),(2),(3),(6)}
  4 | dee  | {(1),(4)}
  5 | eve  | {(1),(5)}
(6 rows)

 id | name
----+------
  1 | ada
  2 | ben
  4 | dee
  5 | eve
  3 | cy
  6 | fay
(6 rows)
```

### F. CYCLE

The road from `a` comes back to `a`; `CYCLE` marks the row that closes the loop and stops there.

<!-- example: postgresql -->
```sql
CREATE TABLE road (src text, dst text);
INSERT INTO road VALUES ('a', 'b'), ('b', 'c'), ('c', 'a');
WITH RECURSIVE trip (src, dst) AS (
    SELECT src, dst FROM road WHERE src = 'a'
    UNION ALL
    SELECT r.src, r.dst FROM road r JOIN trip t ON r.src = t.dst
) CYCLE src SET looped USING path
SELECT * FROM trip;
```

```text
CREATE TABLE
INSERT 0 3
 src | dst | looped |       path
-----+-----+--------+-------------------
 a   | b   | f      | {(a)}
 b   | c   | f      | {(a),(b)}
 c   | a   | f      | {(a),(b),(c)}
 a   | b   | t      | {(a),(b),(c),(a)}
(4 rows)
```

### G. WITH before UPDATE and INSERT

<!-- example: postgresql -->
```sql
WITH low AS (SELECT id FROM emp WHERE salary < 2800)
UPDATE emp SET salary = salary + 100 WHERE id IN (SELECT id FROM low);
CREATE TABLE pay_log (name text, salary numeric(8,2));
WITH v (name, salary) AS (VALUES ('eve', 2600.00), ('fay', 2800.00))
INSERT INTO pay_log SELECT * FROM v;
SELECT * FROM pay_log ORDER BY name;
```

```text
UPDATE 2
CREATE TABLE
INSERT 0 2
 name | salary
------+---------
 eve  | 2600.00
 fay  | 2800.00
(2 rows)
```

### H. The recursion limit

A `LIMIT` ends an endless query when the statement only selects from it; a `WHERE` in the statement does not allow
that.

<!-- example: postgresql -->
```sql
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT * FROM r LIMIT 3;
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT * FROM r WHERE n > 0 LIMIT 3;
SET max_recursion = 5000;
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n < 2000) SELECT count(*) FROM r;
RESET max_recursion;
```

```text
 n
---
 1
 2
 3
(3 rows)

ERROR:  recursive query still adding rows after 1000 rounds (max_recursion); SET max_recursion = n to allow more, 0 for no limit
SET
 count
-------
  2000
(1 row)

RESET
```

### I. Errors

<!-- example: postgresql -->
```sql
WITH d AS (DELETE FROM emp WHERE id = 6 RETURNING *) SELECT * FROM d;
WITH t AS (SELECT 1), t AS (SELECT 2) SELECT 1;
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r WHERE n IN (SELECT n FROM r)) SELECT * FROM r;
```

```text
ERROR:  syntax error at or near "delete"
ERROR:  WITH query name "t" specified more than once
ERROR:  recursive reference to query "r" must not appear within a subquery
```

## See also

[SELECT](select.md) · [INSERT](insert.md) · [UPDATE](update.md) · [DELETE](delete.md) · [MERGE](merge.md)
