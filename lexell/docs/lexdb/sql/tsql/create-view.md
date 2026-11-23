# CREATE VIEW (Transact-SQL)

Makes a view: a named query that can be read as a table. `CREATE OR ALTER VIEW` makes it, or replaces it when it
exists.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE [ OR ALTER ] VIEW [ schema_name . ] view_name [ ( column [ ,...n ] ) ]
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

*select_statement*
: The query. It may join tables and views, group, use common table expressions and `UNION`. An `ORDER BY` needs
  `TOP` to mean anything.

## Remarks

- A view stores its query, not its rows: each read runs the query.
- The view's text, as written, is in `OBJECT_DEFINITION(OBJECT_ID('view'))` and `sys.sql_modules`; `sys.views`
  lists the view. `INFORMATION_SCHEMA.VIEWS.VIEW_DEFINITION` gives the query.
- The names in the query are checked when the view is made: an unknown table is error 208, an unknown column 207.
- `CREATE VIEW` is transactional.

## Differences from SQL Server

- **Views are read-only.** `INSERT`, `UPDATE`, `DELETE` and `MERGE` through a view are error 50000 ("cannot update
  view "v" (lexdb's views are read-only)").
- `WITH SCHEMABINDING`, `WITH ENCRYPTION`, `WITH VIEW_METADATA` and `WITH CHECK OPTION` are error 50000. There are
  no indexed views.
- `CREATE VIEW` need not be the first statement of its batch (SQL Server: 111).
- An `ORDER BY` without `TOP` is taken (SQL Server: 1033). The rows of the view are not sorted by it.
- A table that a view reads cannot be dropped while the view exists (see [DROP TABLE](drop-table.md)).
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

### F. Errors

<!-- example: tsql -->
```sql
UPDATE dbo.v_well_paid SET salary = 0 WHERE id = 1;
CREATE VIEW dbo.v_dept AS SELECT 1 AS one;
GO
CREATE VIEW dbo.v_bad AS SELECT nothere FROM dbo.emp;
GO
CREATE VIEW dbo.v_bound WITH SCHEMABINDING AS SELECT id FROM dbo.emp;
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
cannot update view "v_well_paid" (lexdb's views are read-only)
Msg 2714, Level 16, State 1, Line 1
relation "v_dept" already exists
Msg 207, Level 16, State 1, Line 1
Invalid column name 'nothere'.
Msg 50000, Level 16, State 1, Line 1
lexdb: view options (WITH (...)) are not supported
```

## See also

[ALTER VIEW](alter-view.md) · [DROP VIEW](drop-view.md) · [SELECT](select.md)
