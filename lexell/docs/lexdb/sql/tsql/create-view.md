# CREATE VIEW (Transact-SQL)

Makes a view: a named query that can be read as a table. `CREATE OR ALTER VIEW` makes it, or replaces it when it
exists.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE [ OR ALTER ] VIEW [ schema_name . ] view_name [ ( column [ ,...n ] ) ]
[ WITH { SCHEMABINDING | VIEW_METADATA | ENCRYPTION } [ ,...n ] ]
AS select_statement
[ ; ]
```

## Arguments

`OR ALTER`
: When a view of that name exists, replaces its definition; otherwise makes it. A table of that name is an error.

*view_name*
: The view's name, with its schema (`dbo` by default). It must not be used by another table, view or index of the
  schema (error 2714).

*column*
: Names for the view's columns, as many as the query has. Without them the columns take the query's names, and
  each expression needs a name.

`WITH SCHEMABINDING`
: Ties the view to the tables it reads: `ALTER TABLE ... DROP COLUMN` of a column the view uses is error 5074, and `*`
  in the query is error 1054. `sys.sql_modules.is_schema_bound` is 1. See example F.

`WITH VIEW_METADATA`, `WITH ENCRYPTION`
: Read and ignored (the text is not encrypted).

*select_statement*
: The query. It may join tables and views, group, use common table expressions and `UNION`. An `ORDER BY` needs
  `TOP` to mean anything.

## Remarks

- A view stores its query, not its rows: each read runs the query.
- `ALTER TABLE ... DROP COLUMN` of a column a view reads is allowed unless the view is schema-bound. The view then
  fails when it is read: error 207 for a column it names, 4502 for a `SELECT *` view that has fewer columns than it
  had. A `SELECT *` view whose table lost a column and gained another reads the table's columns by position under its
  old column names, as SQL Server does when the view was not read in between (after a failed read SQL Server keeps
  giving 4502 until `sp_refreshview`, which lexdb does not have; see [ALTER TABLE](alter-table.md), example K).
- The view's text, as written, is in `OBJECT_DEFINITION(OBJECT_ID('view'))` and `sys.sql_modules`; `sys.views`
  lists the view. `INFORMATION_SCHEMA.VIEWS.VIEW_DEFINITION` gives the query.
- The names in the query are checked when the view is made: an unknown table is error 208, an unknown column 207.
- `CREATE VIEW` is transactional.

## Differences from SQL Server

- **Views are read-only.** `INSERT`, `UPDATE`, `DELETE` and `MERGE` through a view are error 50000 ("cannot update
  view "v" (lexdb's views are read-only)").
- `WITH CHECK OPTION` is error 50000 (written before `AS` it is 195, SQL Server 102). There are no indexed views.
- `WITH SCHEMABINDING` is read and kept, but not all of SQL Server's checks are made: a one-part name in the query
  (`FROM emp`) and a schema-bound view over a view that is not are taken (SQL Server: 4512 and 4513), and `ALTER TABLE
  ... ALTER COLUMN` of a column the view reads is made (SQL Server: 5074). The 4502 text names the view without its
  schema, and the state of 1054 is 1 (SQL Server: 6).
- `CREATE VIEW` need not be the first statement of its batch (SQL Server: 111).
- An `ORDER BY` without `TOP` is taken (SQL Server: 1033). The rows of the view are not sorted by it.
- A table that a view reads cannot be dropped while the view exists, schema-bound or not: error 50000 (SQL Server
  drops it unless the view is schema-bound, 3729; see [DROP TABLE](drop-table.md)).
- `sp_helptext` and `sp_refreshview` are not available (2812).

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept_id int, salary decimal(10,2));
INSERT dbo.emp VALUES (1, N'Ann', 1, 5200), (2, N'Bob', 1, 4100), (3, N'Cid', 2, 6100);
-->

The examples use one table:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept_id int, salary decimal(10,2));
INSERT dbo.emp VALUES (1, N'Ann', 1, 5200), (2, N'Bob', 1, 4100), (3, N'Cid', 2, 6100);
```

### A. A simple view

<!-- example: tsql -->
```sql
CREATE VIEW dbo.v_well_paid AS
SELECT id, name, salary FROM dbo.emp WHERE salary > 5000;
GO
SELECT * FROM dbo.v_well_paid ORDER BY id;
```

```text
id name salary
-- ---- -------
1  Ann  5200.00
3  Cid  6100.00

(2 rows affected)
```

### B. Column names, and grouping

<!-- example: tsql -->
```sql
CREATE VIEW dbo.v_dept (dept_id, staff, total) AS
SELECT dept_id, COUNT(*), SUM(salary) FROM dbo.emp GROUP BY dept_id;
GO
SELECT * FROM dbo.v_dept ORDER BY dept_id;
```

```text
dept_id staff total
------- ----- -------
1       2     9300.00
2       1     6100.00

(2 rows affected)
```

### C. CREATE OR ALTER

<!-- example: tsql -->
```sql
CREATE OR ALTER VIEW dbo.v_well_paid AS
SELECT id, name, salary, dept_id FROM dbo.emp WHERE salary > 4000;
GO
SELECT * FROM dbo.v_well_paid ORDER BY id;
```

```text
id name salary  dept_id
-- ---- ------- -------
1  Ann  5200.00 1
2  Bob  4100.00 1
3  Cid  6100.00 2

(3 rows affected)
```

### D. The view's text and catalog rows

<!-- example: tsql -->
```sql
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.v_dept')) AS definition;
SELECT name, type_desc FROM sys.views ORDER BY name;
```

```text
definition
-----------------------------------------------------------------------------------------------------------------------
CREATE VIEW dbo.v_dept (dept_id, staff, total) AS
SELECT dept_id, COUNT(*), SUM(salary) FROM dbo.emp GROUP BY dept_id;

(1 row affected)

name        type_desc
----------- ---------
v_dept      VIEW
v_well_paid VIEW

(2 rows affected)
```

### E. TOP and ORDER BY in a view

<!-- example: tsql -->
```sql
CREATE VIEW dbo.v_top2 AS SELECT TOP (2) name, salary FROM dbo.emp ORDER BY salary DESC;
GO
SELECT * FROM dbo.v_top2 ORDER BY salary DESC;
```

```text
name salary
---- -------
Cid  6100.00
Ann  5200.00

(2 rows affected)
```

### F. WITH SCHEMABINDING and DROP COLUMN

<!-- example: tsql -->
```sql
CREATE TABLE dbo.pay (id int PRIMARY KEY, name nvarchar(30), bonus int, note nvarchar(20));
INSERT dbo.pay VALUES (1, N'Ann', 10, N'a'), (2, N'Bob', 20, N'b');
GO
CREATE VIEW dbo.v_pay AS SELECT id, name FROM dbo.pay;
GO
CREATE VIEW dbo.v_pay_bound WITH SCHEMABINDING AS SELECT id, bonus FROM dbo.pay;
GO
CREATE VIEW dbo.v_pay_all AS SELECT * FROM dbo.pay;
GO
SELECT v.name AS view_name, m.is_schema_bound FROM sys.sql_modules m JOIN sys.views v ON v.object_id = m.object_id WHERE v.name LIKE 'v_pay%' ORDER BY v.name;
GO
ALTER TABLE dbo.pay DROP COLUMN bonus;
GO
ALTER TABLE dbo.pay DROP COLUMN note;
GO
SELECT * FROM dbo.v_pay_all;
GO
ALTER TABLE dbo.pay DROP COLUMN name;
GO
SELECT * FROM dbo.v_pay;
GO
SELECT * FROM dbo.v_pay_bound;
GO
CREATE VIEW dbo.v_star_bound WITH SCHEMABINDING AS SELECT * FROM dbo.pay;
GO
DROP TABLE dbo.pay;
GO
```

```text
(2 rows affected)

view_name   is_schema_bound
----------- ---------------
v_pay       0
v_pay_all   0
v_pay_bound 1

(3 rows affected)

Msg 5074, Level 16, State 1, Line 1
The object 'v_pay_bound' is dependent on column 'bonus'.
Msg 4502, Level 16, State 1, Line 1
View or function 'v_pay_all' has more column names specified than columns defined.
Msg 207, Level 16, State 1, Line 1
Invalid column name 'name'.
id bonus
-- -----
1  10
2  20

(2 rows affected)

Msg 1054, Level 15, State 1, Line 1
Syntax '*' is not allowed in schema-bound objects.
Msg 50000, Level 16, State 1, Line 1
cannot drop table pay because other objects depend on it
```

### G. Errors

<!-- example: tsql -->
```sql
UPDATE dbo.v_well_paid SET salary = 0 WHERE id = 1;
CREATE VIEW dbo.v_dept AS SELECT 1 AS one;
GO
CREATE VIEW dbo.v_bad AS SELECT nothere FROM dbo.emp;
GO
CREATE VIEW dbo.v_chk AS SELECT id FROM dbo.emp WITH CHECK OPTION;
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
cannot update view "v_well_paid" (lexdb's views are read-only)
Msg 2714, Level 16, State 1, Line 2
There is already an object named 'v_dept' in the database.
Msg 207, Level 16, State 1, Line 1
Invalid column name 'nothere'.
Msg 50000, Level 16, State 1, Line 1
lexdb: WITH CHECK OPTION is not supported
```

## See also

[ALTER VIEW](alter-view.md) · [DROP VIEW](drop-view.md) · [SELECT](select.md)
