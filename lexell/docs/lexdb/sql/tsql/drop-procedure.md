# DROP PROCEDURE (Transact-SQL)

Removes one or more stored procedures.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP { PROC | PROCEDURE } [ IF EXISTS ] { [ schema_name. ] procedure } [ ,...n ]
[ ; ]
```

## Arguments

`IF EXISTS`
: A procedure that does not exist is no error.

*procedure*
: The procedure to drop.

## Remarks

- A procedure that does not exist is error 3701.
- Permissions granted on the procedure go with it.

## Differences from SQL Server

- None known.

## Examples

### A. Drop procedures

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.p1 AS SELECT 1 AS one;
GO
CREATE PROCEDURE dbo.p2 AS SELECT 2 AS two;
GO
DROP PROCEDURE dbo.p1, dbo.p2;
DROP PROC IF EXISTS dbo.p3;
SELECT COUNT(*) AS left_over FROM sys.procedures;
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
DROP PROCEDURE dbo.nothere;
```

```text
Msg 3701, Level 11, State 1, Line 1
Cannot drop the procedure 'dbo.nothere', because it does not exist or you do not have permission.
```

## See also

[CREATE PROCEDURE](create-procedure.md) · [EXECUTE](execute.md)
