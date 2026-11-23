# SELECT

Reads rows from tables, views, subqueries and functions.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
[ WITH [ RECURSIVE ] with_query [, ...] ]
SELECT [ ALL | DISTINCT [ ON ( expression [, ...] ) ] ]
    { * | table_name.* | expression [ [ AS ] output_name ] } [, ...]
    [ INTO [ TEMPORARY | TEMP | UNLOGGED ] [ TABLE ] new_table ]
    [ FROM from_item [, ...] ]
    [ WHERE condition ]
    [ GROUP BY [ ALL | DISTINCT ] grouping_element [, ...] ]
    [ HAVING condition ]
    [ WINDOW window_name AS ( window_definition ) [, ...] ]
    [ { UNION | INTERSECT | EXCEPT } [ ALL | DISTINCT ] select ]
    [ ORDER BY expression [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [, ...] ]
    [ LIMIT { count | ALL } ]
    [ OFFSET start [ ROW | ROWS ] ]
    [ FETCH { FIRST | NEXT } [ count ] { ROW | ROWS } { ONLY | WITH TIES } ]
    [ FOR { UPDATE | NO KEY UPDATE | SHARE | KEY SHARE } [ OF table_name [, ...] ] [ NOWAIT | SKIP LOCKED ] [...] ]
    [ WAIT count { SECOND | SECONDS | MILLISECOND | MILLISECONDS | MS } ]

from_item:
    table_name [ [ AS ] alias [ ( column_alias [, ...] ) ] ]
    with_query_name [ [ AS ] alias [ ( column_alias [, ...] ) ] ]
    [ LATERAL ] ( select ) [ [ AS ] alias [ ( column_alias [, ...] ) ] ]
    ( VALUES ( expression [, ...] ) [, ...] ) [ AS ] alias [ ( column_alias [, ...] ) ]
    [ LATERAL ] function_name ( [ argument [, ...] ] ) [ WITH ORDINALITY ] [ [ AS ] alias [ ( column_alias [, ...] ) ] ]
    from_item join_type from_item { ON join_condition | USING ( join_column [, ...] ) }
    from_item NATURAL join_type from_item
    from_item CROSS JOIN from_item
    ( from_item join_type from_item ... ) [ [ AS ] alias [ ( column_alias [, ...] ) ] ]
    from_item MATCH_RECOGNIZE ( ... ) [ [ AS ] alias [ ( column_alias [, ...] ) ] ]
```

A query in parentheses, `( select )`, may stand where a `select` does, and takes its own `ORDER BY` and `LIMIT`.

## Arguments

*with_query*
: A common table expression. See [WITH](with.md).

`ALL`
: Keeps duplicate rows. This is the default.

`DISTINCT`
: Keeps one row of each set of equal rows. NULLs are equal here.

`DISTINCT ON (` *expression* `, ... )`
: Keeps the first row of each set of rows whose expressions are equal. "First" is by `ORDER BY`, whose leading
  expressions must be the `DISTINCT ON` expressions.

*expression* [ `AS` *output_name* ]
: A column of the result. Without `AS`, a column is named after the column or function it shows, or `?column?`.
  `*` is every column of the `FROM` items; `t.*` is every column of `t`.

`INTO` *new_table*
: Makes a new table from the result, as `CREATE TABLE new_table AS` does. The command tag is `SELECT n`.

*from_item*
: Where the rows come from:
  - a table or view, optionally schema-qualified, or a catalog relation (`pg_class`, `information_schema.tables`);
  - a common table expression by name;
  - a subquery in parentheses. It may have no alias (PostgreSQL 16 and later);
  - `VALUES` in parentheses (see [VALUES](values.md));
  - a set-returning function: `generate_series`, `unnest`, `regexp_matches`, `regexp_split_to_table`,
    `string_to_table`, or a `LANGUAGE sql` function of the user's that returns rows. `WITH ORDINALITY` adds a
    column numbering the rows from 1;
  - joins of these. See [Joins](select-join.md);
  - a `MATCH_RECOGNIZE` clause after any of these. See [MATCH_RECOGNIZE](match-recognize.md).

  An alias renames the item; a column alias list renames its columns from the left.

`LATERAL`
: Lets a subquery see the columns of the `FROM` items before it. A function in `FROM` always may.

`WHERE` *condition*
: Keeps the rows for which the condition is true.

`GROUP BY`, `HAVING`
: Groups rows and filters the groups. See [GROUP BY](select-group-by.md).

`WINDOW`
: Names window definitions that `OVER` clauses use. See [Window functions](over.md).

`UNION`, `INTERSECT`, `EXCEPT`
: Combine the rows of two queries with the same number of columns. `UNION` gives the rows of either, `INTERSECT`
  the rows of both, `EXCEPT` the rows of the first that are not in the second. Without `ALL` the result has no
  duplicates. `INTERSECT` binds tighter than `UNION` and `EXCEPT`. The column names are the first query's.

`ORDER BY`
: Sorts the result. An expression may be an output column's name or position (`ORDER BY 2`). `ASC` is the
  default. NULLs sort after every other value going up and before them going down, unless `NULLS FIRST` or
  `NULLS LAST` says otherwise. Without `ORDER BY`, the order of the rows is not defined.

`LIMIT` *count*, `FETCH FIRST` *count* `ROWS ONLY`
: Returns at most *count* rows. `LIMIT ALL` is no limit. `FETCH` without a count is one row. `WITH TIES` also
  returns the rows that tie with the last row by `ORDER BY`, and needs an `ORDER BY`.

`OFFSET` *start*
: Skips *start* rows first.

`FOR UPDATE`, `FOR NO KEY UPDATE`, `FOR SHARE`, `FOR KEY SHARE`
: Locks the rows returned, until the end of the transaction. `OF` names the tables whose rows are locked (by
  their aliases); without it, every table's. `NOWAIT` fails at once with 55P03 when another transaction holds a
  lock that conflicts; `SKIP LOCKED` leaves those rows out.

`WAIT` *count* `SECONDS`
: lexdb's own: when the query finds no rows, it waits up to that time for a commit that gives it some. See
  [SELECT ... WAIT](select-wait.md).

## Remarks

- A statement's clauses are worked in this order: `FROM`, `WHERE`, `GROUP BY`, `HAVING`, window functions, the
  select list, `DISTINCT`, set operations, `ORDER BY`, `OFFSET` and `LIMIT`. So `WHERE` cannot use an output
  column's name, and `ORDER BY` can.
- A subquery may be used as a value (one row, one column; no row gives NULL, more than one is 21000), with `IN`,
  `NOT IN`, `EXISTS`, and with `ANY`, `SOME` and `ALL` after a comparison. A subquery may refer to the columns of the
  query around it.
- Row values compare column by column: `(a, b) = (1, 2)`, `(a, b) > (1, 2)`, `(a, b) IN (SELECT x, y ...)`.
- Text sorts and compares by its bytes, as in PostgreSQL's `C` collation.
- A locking clause is not allowed with `GROUP BY`, `HAVING`, `DISTINCT`, aggregates, window functions or set
  operations, nor on the nullable side of an outer join (0A000), as in PostgreSQL. Inside a read-only transaction it is 25006.
- Every read-write transaction is serializable. A transaction whose reads another commit has changed fails at its
  commit with 40001; `FOR UPDATE` makes the second writer wait instead.

## Differences from PostgreSQL

- `FROM ONLY t` is read as a table named `only` (42P01 `relation "only" does not exist`). `UPDATE ONLY` and
  `DELETE FROM ONLY` work; lexdb has no inheritance, so `ONLY` would change nothing.
- `TABLESAMPLE`, `ROWS FROM (...)`, column definition lists for functions returning `record`, and the `TABLE name`
  statement are not supported (42601).
- A `SELECT` with no select list (`SELECT;`, `SELECT FROM t`) is a syntax error.
- `ORDER BY ... USING operator` is a syntax error.
- `LIMIT` and `OFFSET` take a constant, a parameter or an expression without a subquery; a subquery is 0A000
  (`a subquery is not supported here`).
- `COLLATE` is read and ignored: text always compares by bytes (lexdb-gaps.md 2.2).
- In `FROM a, b JOIN c ON ...`, the `ON` may use `a`'s columns; PostgreSQL refuses that (42P01, `invalid reference to
  FROM-clause entry`).
- A locking clause with `FETCH ... WITH TIES` is refused (0A000).
- `FOR UPDATE` with `NOWAIT` is the only bound on a lock wait: there is no `lock_timeout`, and `statement_timeout`
  does not end a wait for a lock (lexdb-gaps.md 2.2).

## Examples

<!--setup: postgresql
CREATE TABLE dept (id int PRIMARY KEY, name text NOT NULL);
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept_id int REFERENCES dept, salary numeric(8,2), hired date, manager_id int);
INSERT INTO dept VALUES (1, 'sales'), (2, 'research'), (3, 'admin');
INSERT INTO emp VALUES (1, 'ada', 2, 5200, '2020-03-01', NULL), (2, 'ben', 1, 3100, '2021-07-15', 1),
  (3, 'cy', 1, 2900, '2022-01-10', 2), (4, 'dee', 2, 4800, '2019-11-30', 1), (5, 'eve', NULL, 2500, '2023-05-02', 1);
-->

The examples use two tables:

```sql
CREATE TABLE dept (id int PRIMARY KEY, name text NOT NULL);
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept_id int REFERENCES dept, salary numeric(8,2),
                  hired date, manager_id int);
INSERT INTO dept VALUES (1, 'sales'), (2, 'research'), (3, 'admin');
INSERT INTO emp VALUES (1, 'ada', 2, 5200, '2020-03-01', NULL), (2, 'ben', 1, 3100, '2021-07-15', 1),
  (3, 'cy', 1, 2900, '2022-01-10', 2), (4, 'dee', 2, 4800, '2019-11-30', 1), (5, 'eve', NULL, 2500, '2023-05-02', 1);
```

### A. Columns, a condition and an order

<!-- example: postgresql -->
```sql
SELECT name, salary, salary * 12 AS yearly
FROM emp
WHERE salary > 3000
ORDER BY yearly DESC;
```

```text
 name | salary  |  yearly
------+---------+----------
 ada  | 5200.00 | 62400.00
 dee  | 4800.00 | 57600.00
 ben  | 3100.00 | 37200.00
(3 rows)
```

### B. DISTINCT and DISTINCT ON

`DISTINCT ON` keeps the best-paid employee of each department; the employee with no department is a group of its
own.

<!-- example: postgresql -->
```sql
SELECT DISTINCT dept_id FROM emp ORDER BY dept_id;
SELECT DISTINCT ON (dept_id) dept_id, name, salary
FROM emp
ORDER BY dept_id, salary DESC;
```

```text
 dept_id
---------
       1
       2

(3 rows)

 dept_id | name | salary
---------+------+---------
       1 | ben  | 3100.00
       2 | ada  | 5200.00
         | eve  | 2500.00
(3 rows)
```

### C. NULLs in the order

<!-- example: postgresql -->
```sql
SELECT name, dept_id FROM emp ORDER BY dept_id NULLS FIRST, name;
```

```text
 name | dept_id
------+---------
 eve  |
 ben  |       1
 cy   |       1
 ada  |       2
 dee  |       2
(5 rows)
```

### D. LIMIT, OFFSET and FETCH

<!-- example: postgresql -->
```sql
SELECT name, salary FROM emp ORDER BY salary DESC LIMIT 2 OFFSET 1;
SELECT name, salary FROM emp ORDER BY salary OFFSET 1 ROWS FETCH NEXT 2 ROWS ONLY;
```

```text
 name | salary
------+---------
 dee  | 4800.00
 ben  | 3100.00
(2 rows)

 name | salary
------+---------
 cy   | 2900.00
 ben  | 3100.00
(2 rows)
```

`WITH TIES` returns the rows that tie with the last one:

<!-- example: postgresql -->
```sql
SELECT name, dept_id FROM emp ORDER BY dept_id FETCH FIRST 1 ROW WITH TIES;
```

```text
 name | dept_id
------+---------
 ben  |       1
 cy   |       1
(2 rows)
```

### E. Subqueries in FROM, and LATERAL

<!-- example: postgresql -->
```sql
SELECT t.name, t.yearly
FROM (SELECT name, salary * 12 AS yearly FROM emp) AS t
WHERE t.yearly > 40000
ORDER BY t.name;

SELECT count(*) FROM (SELECT DISTINCT dept_id FROM emp);

SELECT d.name AS dept, top.name AS best_paid
FROM dept d,
     LATERAL (SELECT name FROM emp WHERE dept_id = d.id ORDER BY salary DESC LIMIT 1) AS top
ORDER BY d.name;
```

```text
 name |  yearly
------+----------
 ada  | 62400.00
 dee  | 57600.00
(2 rows)

 count
-------
     3
(1 row)

   dept   | best_paid
----------+-----------
 research | ada
 sales    | ben
(2 rows)
```

### F. VALUES and functions in FROM

<!-- example: postgresql -->
```sql
SELECT * FROM (VALUES (1, 'one'), (2, 'two')) AS v(n, word);
SELECT * FROM unnest(ARRAY['x', 'y']) WITH ORDINALITY AS u(letter, n);
SELECT d.name, s FROM dept d, generate_series(1, d.id) AS s ORDER BY d.name, s;
```

```text
 n | word
---+------
 1 | one
 2 | two
(2 rows)

 letter | n
--------+---
 x      | 1
 y      | 2
(2 rows)

   name   | s
----------+---
 admin    | 1
 admin    | 2
 admin    | 3
 research | 1
 research | 2
 sales    | 1
(6 rows)
```

### G. Subqueries as values

<!-- example: postgresql -->
```sql
SELECT name, (SELECT name FROM dept WHERE id = emp.dept_id) AS dept FROM emp ORDER BY id;
SELECT name FROM emp WHERE id IN (SELECT manager_id FROM emp) ORDER BY name;
SELECT name FROM dept d WHERE NOT EXISTS (SELECT 1 FROM emp WHERE dept_id = d.id);
SELECT name FROM emp WHERE salary > ALL (SELECT salary FROM emp WHERE dept_id = 1) ORDER BY name;
SELECT name FROM emp WHERE (dept_id, salary) IN (SELECT dept_id, max(salary) FROM emp GROUP BY dept_id) ORDER BY name;
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

 name
------
 ada
 ben
(2 rows)

 name
-------
 admin
(1 row)

 name
------
 ada
 dee
(2 rows)

 name
------
 ada
 ben
(2 rows)
```

### H. Set operations

<!-- example: postgresql -->
```sql
SELECT name FROM emp WHERE dept_id = 1 UNION SELECT name FROM dept ORDER BY name;
SELECT id FROM dept EXCEPT SELECT dept_id FROM emp;
SELECT id FROM dept INTERSECT SELECT dept_id FROM emp ORDER BY id;
(SELECT name FROM emp ORDER BY salary LIMIT 1)
UNION ALL
(SELECT name FROM emp ORDER BY salary DESC LIMIT 1);
```

```text
   name
----------
 admin
 ben
 cy
 research
 sales
(5 rows)

 id
----
  3
(1 row)

 id
----
  1
  2
(2 rows)

 name
------
 eve
 ada
(2 rows)
```

### I. SELECT INTO

<!-- example: postgresql -->
```sql
SELECT id, name INTO senior FROM emp WHERE hired < DATE '2021-01-01';
SELECT * FROM senior ORDER BY id;
```

```text
SELECT 2
 id | name
----+------
  1 | ada
  4 | dee
(2 rows)
```

### J. Locking rows

`OF e` locks the employees' rows and not the departments'.

<!-- example: postgresql -->
```sql
BEGIN;
SELECT e.id, e.salary FROM emp e JOIN dept d ON d.id = e.dept_id WHERE d.name = 'sales' ORDER BY e.id FOR UPDATE OF e;
UPDATE emp SET salary = salary + 100 WHERE dept_id = 1;
COMMIT;
SELECT count(*) FROM emp GROUP BY dept_id FOR UPDATE;
BEGIN READ ONLY;
SELECT id FROM emp WHERE id = 1 FOR UPDATE;
ROLLBACK;
```

```text
BEGIN
 id | salary
----+---------
  2 | 3100.00
  3 | 2900.00
(2 rows)

UPDATE 2
COMMIT
ERROR:  FOR UPDATE is not allowed with GROUP BY clause
BEGIN
ERROR:  cannot execute SELECT FOR UPDATE in a read-only transaction
ROLLBACK
```

### K. Text order

Text sorts by its bytes: capitals before small letters.

<!-- example: postgresql -->
```sql
SELECT w FROM (VALUES ('b'), ('B'), ('a'), ('_')) AS v(w) ORDER BY w;
```

```text
 w
---
 B
 _
 a
 b
(4 rows)
```

### L. Errors

<!-- example: postgresql -->
```sql
SELECT name, salary * 12 AS yearly FROM emp WHERE yearly > 40000;
SELECT DISTINCT dept_id FROM emp ORDER BY salary;
SELECT (SELECT name FROM emp);
SELECT * FROM ONLY emp;
```

```text
ERROR:  column "yearly" does not exist
ERROR:  for SELECT DISTINCT, ORDER BY expressions must appear in select list
ERROR:  more than one row returned by a subquery used as an expression
ERROR:  relation "only" does not exist
```

## See also

[Joins](select-join.md) · [GROUP BY](select-group-by.md) · [Window functions](over.md) · [WITH](with.md) ·
[VALUES](values.md) · [SELECT ... WAIT](select-wait.md) · [MATCH_RECOGNIZE](match-recognize.md) ·
[INSERT](insert.md) · [UPDATE](update.md) · [DELETE](delete.md)
