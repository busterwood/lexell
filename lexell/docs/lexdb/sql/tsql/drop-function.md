# DROP FUNCTION (Transact-SQL)

Removes one or more functions of the user's.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP FUNCTION [ IF EXISTS ] { [ schema_name. ] function_name } [ ,...n ]
[ ; ]
```

## Arguments

`IF EXISTS`
: A function that does not exist is no error.

*function_name*
: The function to drop: scalar or table-valued.

## Remarks

- A function that does not exist is error 3701.

## Differences from SQL Server

- None known.

## Examples

### A. Drop functions

<!-- example: tsql -->
```sql
CREATE FUNCTION dbo.one () RETURNS int AS BEGIN RETURN 1; END
GO
CREATE FUNCTION dbo.nums () RETURNS TABLE AS RETURN (SELECT 1 AS n);
GO
DROP FUNCTION dbo.one, dbo.nums;
DROP FUNCTION IF EXISTS dbo.two;
SELECT COUNT(*) AS left_over FROM sys.objects WHERE type IN ('FN', 'IF', 'TF');
```

```text
left_over
---------
0

(1 row affected)
```

### B. Errors

<!-- example: tsql -->
```sql
DROP FUNCTION dbo.nothere;
```

```text
Msg 3701, Level 11, State 1, Line 1
Cannot drop the function 'dbo.nothere', because it does not exist or you do not have permission.
```

## See also

[CREATE FUNCTION](create-function.md)
