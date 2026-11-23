# DROP VIEW (Transact-SQL)

Removes one or more views.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP VIEW [ IF EXISTS ] [ schema_name . ] view_name [ ,...n ]
[ ; ]
```

## Arguments

`IF EXISTS`
: A view that does not exist is no error.

*view_name*
: The view to drop.

## Remarks

- Dropping a view does not touch the tables it reads.
- `DROP VIEW` is transactional.

## Differences from SQL Server

- A view that does not exist is error 208, `view "v_nothere" does not exist` (SQL Server: 3701).
- A view that another view reads cannot be dropped while the other exists (as for tables, see
  [DROP TABLE](drop-table.md)).

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30));
CREATE VIEW dbo.v_a AS SELECT id FROM dbo.emp;
CREATE VIEW dbo.v_b AS SELECT name FROM dbo.emp;
CREATE VIEW dbo.v_c AS SELECT id FROM dbo.emp;
CREATE VIEW dbo.v_on_c AS SELECT id FROM dbo.v_c;
-->

The examples use a table and four views:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30));
CREATE VIEW dbo.v_a AS SELECT id FROM dbo.emp;
CREATE VIEW dbo.v_b AS SELECT name FROM dbo.emp;
CREATE VIEW dbo.v_c AS SELECT id FROM dbo.emp;
CREATE VIEW dbo.v_on_c AS SELECT id FROM dbo.v_c;
```

### A. Drop views

<!-- example: tsql -->
```sql
DROP VIEW dbo.v_a, dbo.v_b;
DROP VIEW IF EXISTS dbo.v_nothere;
SELECT name FROM sys.views ORDER BY name;
```

```text
name
------
v_c
v_on_c

(2 rows affected)
```

### B. Errors

<!-- example: tsql -->
```sql
DROP VIEW dbo.v_c;
GO
DROP VIEW dbo.v_nothere;
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
cannot drop view v_c because other objects depend on it
Msg 208, Level 16, State 1, Line 1
view "v_nothere" does not exist
```

## See also

[CREATE VIEW](create-view.md) · [ALTER VIEW](alter-view.md) · [DROP TABLE](drop-table.md)
