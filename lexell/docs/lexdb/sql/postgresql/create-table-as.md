# CREATE TABLE AS

Makes a new table from the result of a query. `SELECT ... INTO` does the same.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CREATE [ [ GLOBAL | LOCAL ] { TEMPORARY | TEMP } | UNLOGGED ] TABLE [ IF NOT EXISTS ] table_name
    [ ( column_name [, ...] ) ]
    [ ON COMMIT { PRESERVE ROWS | DELETE ROWS | DROP } ]
    AS query
    [ WITH [ NO ] DATA ]

SELECT select_list INTO [ TEMPORARY | TEMP | UNLOGGED ] [ TABLE ] new_table [ FROM ... ] ...
```

## Arguments

`TEMPORARY`, `UNLOGGED`, `IF NOT EXISTS`, `ON COMMIT`
: As in [CREATE TABLE](create-table.md).

*column_name*
: Names for the new table's columns, from the left. Without them the columns take the query's names.

*query*
: A `SELECT`, a `VALUES`, or a `WITH ... SELECT`, in parentheses or not.

`WITH DATA`, `WITH NO DATA`
: Whether the rows are copied. `WITH DATA` is the default; `WITH NO DATA` makes an empty table with the query's
  columns.

## Remarks

- The columns take the query's types: `numeric` for `1.5`, `text` for a string or a NULL, `timestamp with time zone`
  for `now()`.
- The new table has no constraints, defaults or indexes: not even `NOT NULL` where the query's table had one. Add
  them with [ALTER TABLE](alter-table.md) and [CREATE INDEX](create-index.md).
- Two columns with the same name are refused (42701); name them with `AS` or a column list.
- The command tag is `SELECT n`, the rows copied, or `CREATE TABLE AS` for `WITH NO DATA` and `IF NOT EXISTS` that
  found the table.
- The query's result is made whole before it is inserted (lexdb-gaps.md 2.4).

## Differences from PostgreSQL

- `CREATE TABLE ... AS TABLE t` and `AS EXECUTE name` are syntax errors; write `AS SELECT * FROM t`.
- `WITH ( storage_parameter )` and `TABLESPACE` are not supported.

## Examples

<!--setup: postgresql
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept text, salary numeric(8,2));
INSERT INTO emp VALUES (1, 'ada', 'research', 5200), (2, 'ben', 'sales', 3100), (3, 'cy', 'sales', 2900);
-->

The examples use one table:

```sql
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept text, salary numeric(8,2));
INSERT INTO emp VALUES (1, 'ada', 'research', 5200), (2, 'ben', 'sales', 3100), (3, 'cy', 'sales', 2900);
```

### A. A table from a query

<!-- example: postgresql -->
```sql
CREATE TABLE dept_pay AS
    SELECT dept, count(*) AS staff, sum(salary) AS total FROM emp GROUP BY dept;
SELECT * FROM dept_pay ORDER BY dept;
\d dept_pay
```

```text
SELECT 2
   dept   | staff |  total
----------+-------+---------
 research |     1 | 5200.00
 sales    |     2 | 6000.00
(2 rows)

              Table "public.dept_pay"
 Column |  Type   | Collation | Nullable | Default
--------+---------+-----------+----------+---------
 dept   | text    |           |          |
 staff  | bigint  |           |          |
 total  | numeric |           |          |
```

### B. Column names, and WITH NO DATA

<!-- example: postgresql -->
```sql
CREATE TABLE emp_shape (who, pay) AS SELECT name, salary FROM emp WITH NO DATA;
SELECT count(*) FROM emp_shape;
SELECT attname, format_type(atttypid, atttypmod), attnotnull
FROM pg_attribute WHERE attrelid = 'emp_shape'::regclass AND attnum > 0 ORDER BY attnum;
```

```text
CREATE TABLE AS
 count
-------
     0
(1 row)

 attname | format_type | attnotnull
---------+-------------+------------
 who     | text        | f
 pay     | numeric     | f
(2 rows)
```

### C. Types of the columns

<!-- example: postgresql -->
```sql
CREATE TABLE kinds AS SELECT 'x' AS a, 1.5 AS b, NULL AS c, 7 AS d, DATE '2026-01-01' AS e;
SELECT attname, format_type(atttypid, atttypmod)
FROM pg_attribute WHERE attrelid = 'kinds'::regclass AND attnum > 0 ORDER BY attnum;
```

```text
SELECT 1
 attname | format_type
---------+-------------
 a       | text
 b       | numeric
 c       | text
 d       | integer
 e       | date
(5 rows)
```

### D. SELECT INTO, a temporary table, and VALUES

<!-- example: postgresql -->
```sql
SELECT id, name INTO TEMP sales_team FROM emp WHERE dept = 'sales';
SELECT * FROM sales_team ORDER BY id;
CREATE TABLE code AS VALUES (1, 'one'), (2, 'two');
SELECT * FROM code ORDER BY column1;
```

```text
SELECT 2
 id | name
----+------
  2 | ben
  3 | cy
(2 rows)

SELECT 2
 column1 | column2
---------+---------
       1 | one
       2 | two
(2 rows)
```

### E. Errors

<!-- example: postgresql -->
```sql
CREATE TABLE twice AS SELECT 1 AS a, 2 AS a;
CREATE TABLE IF NOT EXISTS dept_pay AS SELECT 1;
CREATE TABLE copy AS TABLE emp;
```

```text
ERROR:  column "a" specified more than once
NOTICE:  relation "dept_pay" already exists, skipping
CREATE TABLE AS
ERROR:  syntax error at or near "table"
```

## See also

[CREATE TABLE](create-table.md) · [SELECT](select.md) · [INSERT](insert.md) · [DROP TABLE](drop-table.md)
