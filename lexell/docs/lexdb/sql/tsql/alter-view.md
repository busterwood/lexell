# ALTER VIEW (Transact-SQL)

Replaces the query of a view that exists.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
ALTER VIEW [ schema_name . ] view_name [ ( column [ ,...n ] ) ]
AS select_statement
[ ; ]
```

## Arguments

*view_name*
: The view to change. A view that does not exist is error 208.

*column*, *select_statement*
: As in [CREATE VIEW](create-view.md). The new query may have other columns than the old one.

## Remarks

- The view keeps its name and its permissions; only its query changes.
- `CREATE OR ALTER VIEW` does the same, and makes the view when there is none.
- `OBJECT_DEFINITION` gives the new text.

## Differences from SQL Server

- The options `WITH SCHEMABINDING`, `WITH ENCRYPTION` and `WITH CHECK OPTION` are error 50000, as in
  [CREATE VIEW](create-view.md).
- The text kept for the view is the `ALTER VIEW` statement turned into `CREATE VIEW`.

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept_id int, salary decimal(10,2));
INSERT dbo.emp VALUES (1, N'Ann', 1, 5200), (2, N'Bob', 1, 4100), (3, N'Cid', 2, 6100);
CREATE VIEW dbo.v_emp AS SELECT id, name FROM dbo.emp;
-->

The examples use a table and a view:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept_id int, salary decimal(10,2));
INSERT dbo.emp VALUES (1, N'Ann', 1, 5200), (2, N'Bob', 1, 4100), (3, N'Cid', 2, 6100);
CREATE VIEW dbo.v_emp AS SELECT id, name FROM dbo.emp;
```

### A. Change a view's query

<!-- example: tsql -->
```sql
ALTER VIEW dbo.v_emp AS
SELECT id, name, salary FROM dbo.emp WHERE dept_id = 1;
GO
SELECT * FROM dbo.v_emp ORDER BY id;
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.v_emp')) AS definition;
```

```text
id name salary
-- ---- -------
1  Ann  5200.00
2  Bob  4100.00

(2 rows affected)

definition
---------------------------------------------------------------------------------
CREATE VIEW dbo.v_emp AS
SELECT id, name, salary FROM dbo.emp WHERE dept_id = 1;

(1 row affected)
```

### B. Errors

<!-- example: tsql -->
```sql
ALTER VIEW dbo.v_nothere AS SELECT 1 AS one;
GO
ALTER VIEW dbo.emp AS SELECT 1 AS one;
GO
```

```text
Msg 208, Level 16, State 1, Line 1
Invalid object name 'v_nothere'.
Msg 2010, Level 16, State 1, Line 1
Cannot perform alter on 'emp' because it is an incompatible object type.
```

## See also

[CREATE VIEW](create-view.md) · [DROP VIEW](drop-view.md)
