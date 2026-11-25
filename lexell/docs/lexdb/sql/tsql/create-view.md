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
: Ties the view to the tables it reads: `ALTER TABLE ... DROP COLUMN` or `ALTER COLUMN` of a column the view uses
  is error 5074, `DROP TABLE` of a table it reads is 3729, `*` in the query is error 1054, a one-part name in the
  query (`FROM emp`) is 4512, and a view over a view that is not schema-bound (or over a function that is not) is
  4513. `sys.sql_modules.is_schema_bound` is 1. See example F.

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
  old column names, as SQL Server does when the view was not read in between. After a failed read SQL Server keeps
  giving 4502 until `sp_refreshview`; lexdb does not (a failed read changes nothing in the view), and
  `sp_refreshview` brings the table's columns as they are now (example H; see also [ALTER TABLE](alter-table.md),
  example K).
- **A `SELECT *` view keeps the columns it was made with**, by position, as in SQL Server: a column added to the table
  later is not in the view until `sp_refreshview` (example J). A view that names its own columns (`CREATE VIEW v (a, b)
  AS SELECT * FROM t`) is error 8158 when it is read after the table gained a column.
- Errors 4502 and 8158 name the view as the statement wrote it (`dbo.v_all` for `FROM dbo.v_all`), and, as 208 is, are
  compile errors of the statement that reads the view: a `TRY` block in the same batch does not catch them, as in SQL
  Server.
- `DROP TABLE` of a table a view reads is done, as in SQL Server, unless the view is schema-bound (3729): the view,
  and a view over it, fail with error 208 when they are read, and read again once a table of that name is made (see
  [DROP TABLE](drop-table.md), example D).
- `sp_refreshview 'v'` makes the view again from its stored text, so a `SELECT *` view takes its table's columns as
  they are now; a name that is no view is error 15165.
- The view's text, as written, is in `OBJECT_DEFINITION(OBJECT_ID('view'))` and `sys.sql_modules`; `sys.views`
  lists the view. `INFORMATION_SCHEMA.VIEWS.VIEW_DEFINITION` gives the query.
- The names in the query are checked when the view is made: an unknown table is error 208, an unknown column 207.
- `CREATE VIEW` is transactional.

## Differences from SQL Server

- **Views are read-only.** `INSERT`, `UPDATE`, `DELETE` and `MERGE` through a view are error 50000 ("cannot update
  view "v" (lexdb's views are read-only)").
- `WITH CHECK OPTION` after the query is error 50000 (written before `AS` it is 102, as in SQL Server).
- **Indexed views:** Creating a `UNIQUE CLUSTERED INDEX` on a view defined `WITH SCHEMABINDING` materializes the view
  into a synchronously maintained (`ON STATEMENT`) indexed view. Additional `NONCLUSTERED` indexes may be added on it.
  Dropping the unique clustered index demotes it back to a regular schema-bound view. `sys.views` and `sys.objects`
  continue to list it as type `'V'`, `sys.indexes` lists its indexes, and `sys.tables` excludes it. Creating an index
  on a view without `WITH SCHEMABINDING` raises error 1939.
- The 4512 of a `WITH SCHEMABINDING` view names the view being made without the schema the statement wrote
  (`'v_bad1'` for `CREATE VIEW dbo.v_bad1`; SQL Server: `'dbo.v_bad1'`); its 4513 is right.
- `CREATE VIEW` need not be the first statement of its batch (SQL Server: 111).
- An `ORDER BY` without `TOP` is taken (SQL Server: 1033). The rows of the view are not sorted by it.
- `DROP VIEW` of a view that another view reads is refused (error 50000); SQL Server drops it, and the other view
  then fails with 208 when it is read.
- `sp_helptext` is not available (2812).

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
View or function 'dbo.v_pay_all' has more column names specified than columns defined.
Msg 207, Level 16, State 1, Line 1
Invalid column name 'name'.
id bonus
-- -----
1  10
2  20

(2 rows affected)

Msg 1054, Level 15, State 6, Line 1
Syntax '*' is not allowed in schema-bound objects.
Msg 3729, Level 16, State 1, Line 1
Cannot DROP TABLE 'dbo.pay' because it is being referenced by object 'v_pay_bound'.
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
CREATE VIEW dbo.v_chk2 WITH CHECK OPTION AS SELECT id FROM dbo.emp;
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
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'WITH'.
```

### H. sp_refreshview

A `SELECT *` view whose table lost a column is error 4502 when it is read. `sp_refreshview` makes the view again from
its stored text, with the table's columns as they are now.

<!-- example: tsql -->
```sql
CREATE TABLE dbo.gadget (id int PRIMARY KEY, name nvarchar(20), price int);
INSERT dbo.gadget VALUES (1, N'bolt', 5);
GO
CREATE VIEW dbo.v_gadget AS SELECT * FROM dbo.gadget;
GO
ALTER TABLE dbo.gadget DROP COLUMN price;
GO
SELECT * FROM dbo.v_gadget;
GO
EXEC sp_refreshview 'dbo.v_gadget';
GO
SELECT * FROM dbo.v_gadget;
GO
EXEC sp_refreshview 'dbo.gadget';
GO
```

```text
(1 row affected)

Msg 4502, Level 16, State 1, Line 1
View or function 'dbo.v_gadget' has more column names specified than columns defined.
id name
-- ----
1  bolt

(1 row affected)

Msg 15165, Level 16, State 1, Line 1
Could not find object 'dbo.gadget' or you do not have permission.
```

### I. What a schema-bound view refuses

<!-- example: tsql -->
```sql
CREATE TABLE dbo.part (id int PRIMARY KEY, label nvarchar(20), qty int);
GO
CREATE VIEW dbo.v_part_plain AS SELECT id, label FROM dbo.part;
GO
CREATE VIEW dbo.v_part_bound WITH SCHEMABINDING AS SELECT id, qty FROM dbo.part;
GO
CREATE VIEW dbo.v_bad1 WITH SCHEMABINDING AS SELECT id FROM part;
GO
CREATE VIEW dbo.v_bad2 WITH SCHEMABINDING AS SELECT id FROM dbo.v_part_plain;
GO
ALTER TABLE dbo.part ALTER COLUMN qty bigint;
GO
ALTER TABLE dbo.part ALTER COLUMN label nvarchar(40);
GO
DROP TABLE dbo.part;
GO
```

```text
Msg 4512, Level 16, State 3, Line 1
Cannot schema bind view 'v_bad1' because name 'part' is invalid for schema binding. Names must be in two-part format and an object cannot reference itself.
Msg 4513, Level 16, State 2, Line 1
Cannot schema bind view 'dbo.v_bad2'. 'dbo.v_part_plain' is not schema bound.
Msg 5074, Level 16, State 1, Line 1
The object 'v_part_bound' is dependent on column 'qty'.
Msg 3729, Level 16, State 1, Line 1
Cannot DROP TABLE 'dbo.part' because it is being referenced by object 'v_part_bound'.
```

### J. SELECT * keeps the columns, until sp_refreshview

A column added to the table does not show in a `SELECT *` view made before it. A view with a column list (`tool_id`,
`tool_name`) cannot take the third column: error 8158. `sp_refreshview` makes the first view again, and it then has the
new column.

<!-- example: tsql -->
```sql
CREATE TABLE dbo.tool (id int PRIMARY KEY, name nvarchar(20));
INSERT dbo.tool VALUES (1, N'saw');
GO
CREATE VIEW dbo.v_tool AS SELECT * FROM dbo.tool;
GO
CREATE VIEW dbo.v_tool_named (tool_id, tool_name) AS SELECT * FROM dbo.tool;
GO
ALTER TABLE dbo.tool ADD price int;
GO
UPDATE dbo.tool SET price = 12;
GO
SELECT * FROM dbo.v_tool;
GO
SELECT * FROM dbo.v_tool_named;
GO
EXEC sp_refreshview 'dbo.v_tool';
GO
SELECT * FROM dbo.v_tool;
GO
```

```text
(1 row affected)

(1 row affected)

id name
-- ----
1  saw

(1 row affected)

Msg 8158, Level 16, State 1, Line 1
'v_tool_named' has more columns than were specified in the column list.
id name price
-- ---- -----
1  saw  12

(1 row affected)
```

## See also

[ALTER VIEW](alter-view.md) · [DROP VIEW](drop-view.md) · [SELECT](select.md)
