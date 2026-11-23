# DROP ROLE (Transact-SQL)

Removes a database role.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP ROLE [ IF EXISTS ] role_name
[ ; ]
```

## Arguments

`IF EXISTS`
: A role that does not exist is no error.

*role_name*
: The role to drop.

## Remarks

- lexdb's users and roles are one kind of principal, so `DROP ROLE` and [DROP USER](drop-user.md) do the same.

## Differences from SQL Server

- A role that does not exist gives error 50000, `role "nobody" does not exist` (SQL Server: 15151).
- A role that has members can be dropped (SQL Server: 15144).

## Examples

### A. Drop a role

<!-- example: tsql -->
```sql
CREATE ROLE auditors;
CREATE USER clerk;
GRANT auditors TO clerk;
DROP ROLE auditors;
DROP ROLE IF EXISTS auditors;
SELECT COUNT(*) AS left_over FROM sys.database_principals WHERE name = 'auditors';
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
DROP ROLE nobody;
```

```text
Msg 50000, Level 16, State 1, Line 1
role "nobody" does not exist
```

## See also

[CREATE ROLE](create-role.md) · [DROP USER](drop-user.md)
