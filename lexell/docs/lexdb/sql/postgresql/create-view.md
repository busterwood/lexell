# CREATE VIEW

Names a query, which can then be read like a table.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CREATE [ OR REPLACE ] [ TEMP | TEMPORARY ] VIEW name [ ( column_name [, ...] ) ]
    AS query
```

## Arguments

`OR REPLACE`
: If a view of the name exists, gives it the new query. The new query must keep the old one's columns, by name and
  in order; it may add columns after them.

`TEMPORARY` or `TEMP`
: The view belongs to the session and is dropped when it ends.

*name*
: The view's name, optionally schema-qualified.

*column_name*
: Names for the view's columns, from the left. Without them, the columns take the query's names.

*query*
: A `SELECT`, `VALUES`, or `WITH ... SELECT`. It may not use parameters (`$1`).

## Remarks

- lexdb keeps the query's text, and reads it again each time the view is used. The query is planned with the
  statement that reads the view, so a condition on the view (`WHERE id = 1`) reaches the tables under it.
- **`SELECT *` keeps the columns the view was made with**, as in PostgreSQL: a column added to the table later is not in
  the view (example E). `SELECT t.*, u.*` keeps `t`'s and `u`'s columns.
- Renaming a table or a column that a view reads changes the view's text with it, so the view goes on working.
- Views are read-only: `INSERT`, `UPDATE`, `DELETE` and `MERGE` of a view are refused.
- `pg_get_viewdef`, `pg_views.definition` and `information_schema.views` give the query as written.
- `CREATE VIEW` is transactional.

## Differences from PostgreSQL

- Views are not updatable: PostgreSQL updates a simple view's table, and lexdb refuses (`cannot update view "v"
  (lexdb's views are read-only)`) (lexdb-gaps.md 2.2).
- The definition is shown as written; PostgreSQL shows its own rewritten form (`SELECT emp.id, emp.name FROM emp`).
- Not supported: `CREATE RECURSIVE VIEW` (42601), `WITH ( view_option )` and `WITH CHECK OPTION` (0A000), and
  materialized views (0A000).
- `CREATE OR REPLACE VIEW` that renames a column gives `cannot drop columns from view`; PostgreSQL says `cannot
  change name of view column`.

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

### A. A view, and a query of it

<!-- example: postgresql -->
```sql
CREATE VIEW well_paid AS SELECT id, name, salary FROM emp WHERE salary > 3000;
SELECT * FROM well_paid ORDER BY id;
EXPLAIN SELECT * FROM well_paid WHERE id = 1;
```

```text
CREATE VIEW
 id | name | salary
----+------+---------
  1 | ada  | 5200.00
  2 | ben  | 3100.00
(2 rows)

             QUERY PLAN
------------------------------------
 scan well_paid: rows of subquery 1
 subquery 1 (from): run once
   scan emp: primary key lookup
(3 rows)
```

### B. Column names, and grouping

<!-- example: postgresql -->
```sql
CREATE VIEW dept_pay (dept, staff, total) AS SELECT dept, count(*), sum(salary) FROM emp GROUP BY dept;
SELECT * FROM dept_pay ORDER BY dept;
```

```text
CREATE VIEW
   dept   | staff |  total
----------+-------+---------
 research |     1 | 5200.00
 sales    |     2 | 6000.00
(2 rows)
```

### C. OR REPLACE

<!-- example: postgresql -->
```sql
CREATE OR REPLACE VIEW well_paid AS SELECT id, name, salary, dept FROM emp WHERE salary > 3000;
SELECT * FROM well_paid ORDER BY id;
CREATE OR REPLACE VIEW well_paid AS SELECT id, name FROM emp;
```

```text
CREATE VIEW
 id | name | salary  |   dept
----+------+---------+----------
  1 | ada  | 5200.00 | research
  2 | ben  | 3100.00 | sales
(2 rows)

ERROR:  cannot drop columns from view
```

### D. The definition

<!-- example: postgresql -->
```sql
SELECT pg_get_viewdef('dept_pay');
SELECT viewname, definition FROM pg_views WHERE viewname = 'well_paid';
```

```text
                       pg_get_viewdef
------------------------------------------------------------
 SELECT dept, count(*), sum(salary) FROM emp GROUP BY dept;
(1 row)

 viewname  |                         definition
-----------+-------------------------------------------------------------
 well_paid | SELECT id, name, salary, dept FROM emp WHERE salary > 3000;
(1 row)
```

### E. SELECT * keeps the columns it was made with

A column added to the table after `CREATE VIEW` is not in the view; a view made after it has the column.

<!-- example: postgresql -->
```sql
CREATE VIEW all_emp AS SELECT * FROM emp;
ALTER TABLE emp ADD COLUMN phone text;
CREATE VIEW all_emp2 AS SELECT * FROM emp;
SELECT * FROM all_emp WHERE id = 1;
SELECT * FROM all_emp2 WHERE id = 1;
```

```text
CREATE VIEW
ALTER TABLE
CREATE VIEW
 id | name |   dept   | salary
----+------+----------+---------
  1 | ada  | research | 5200.00
(1 row)

 id | name |   dept   | salary  | phone
----+------+----------+---------+-------
  1 | ada  | research | 5200.00 |
(1 row)
```

### F. Read-only, and errors

<!-- example: postgresql -->
```sql
UPDATE well_paid SET salary = 1 WHERE id = 1;
CREATE VIEW well_paid AS SELECT 1;
CREATE VIEW checked AS SELECT * FROM emp WHERE salary > 0 WITH CHECK OPTION;
CREATE MATERIALIZED VIEW mv AS SELECT 1;
```

```text
ERROR:  cannot update view "well_paid" (lexdb's views are read-only)
ERROR:  relation "well_paid" already exists
ERROR:  lexdb: WITH CHECK OPTION is not supported
ERROR:  lexdb: CREATE MATERIALIZED is not supported yet (CREATE makes tables, views, indexes, schemas, sequences, types, roles and users)
```

## See also

[ALTER VIEW](alter-view.md) · [DROP VIEW](drop-view.md) · [SELECT](select.md) · [CREATE TABLE AS](create-table-as.md)
