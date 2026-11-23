# REVOKE (Transact-SQL)

Takes back permissions granted on an object.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
REVOKE { ALL [ PRIVILEGES ] | permission [ ,...n ] }
    ON [ OBJECT :: ] [ schema_name. ] object_name
    FROM principal [ ,...n ]
    [ CASCADE ]
[ ; ]
```

## Arguments

*permission*, *object_name*, *principal*
: As in [GRANT](grant.md).

`CASCADE`
: Taken.

## Remarks

- Revoking a permission that was not granted is no error.

## Differences from SQL Server

- `REVOKE GRANT OPTION FOR` is error 50000 ("lexdb: grant options are not supported"); the whole batch is refused.

## Examples

<!--setup: tsql
CREATE TABLE dbo.price (item nvarchar(20), amount decimal(10,2));
CREATE USER clerk;
GRANT SELECT, INSERT, UPDATE ON dbo.price TO clerk;
-->

The examples use a table and a user with three permissions on it:

```sql
CREATE TABLE dbo.price (item nvarchar(20), amount decimal(10,2));
CREATE USER clerk;
GRANT SELECT, INSERT, UPDATE ON dbo.price TO clerk;
```

### A. Revoke some permissions, then all

<!-- example: tsql -->
```sql
REVOKE DELETE ON dbo.price FROM clerk;
REVOKE INSERT, UPDATE ON dbo.price FROM clerk;
SELECT permission_name FROM sys.database_permissions WHERE major_id = OBJECT_ID('dbo.price');
REVOKE ALL ON OBJECT::dbo.price FROM clerk CASCADE;
SELECT COUNT(*) AS left_over FROM sys.database_permissions WHERE major_id = OBJECT_ID('dbo.price');
```

```text
permission_name
---------------
SELECT

(1 row affected)

left_over
---------
0

(1 row affected)
```

### B. Errors

<!-- example: tsql -->
```sql
REVOKE GRANT OPTION FOR SELECT ON dbo.price FROM clerk;
```

```text
Msg 50000, Level 16, State 1, Line 1
lexdb: grant options are not supported
```

## See also

[GRANT](grant.md)
