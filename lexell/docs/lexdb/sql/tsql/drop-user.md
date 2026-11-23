# DROP USER (Transact-SQL)

Removes a database user.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP USER [ IF EXISTS ] user_name
[ ; ]
```

## Arguments

`IF EXISTS`
: A user that does not exist is no error.

*user_name*
: The user to drop.

## Remarks

- lexdb's users and roles are one kind of principal, so `DROP USER` and [DROP ROLE](drop-role.md) do the same.

## Differences from SQL Server

- A user that does not exist gives error 50000, `role "nobody" does not exist` (SQL Server: 15151).

## Examples

### A. Drop a user

<!-- example: tsql -->
```sql
CREATE USER temp_clerk;
DROP USER temp_clerk;
DROP USER IF EXISTS temp_clerk;
SELECT COUNT(*) AS left_over FROM sys.database_principals WHERE name = 'temp_clerk';
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
DROP USER nobody;
```

```text
Msg 50000, Level 16, State 1, Line 1
role "nobody" does not exist
```

## See also

[CREATE USER](create-user.md) · [DROP ROLE](drop-role.md)
