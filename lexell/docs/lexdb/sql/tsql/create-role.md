# CREATE ROLE (Transact-SQL)

Makes a database role: a group of users that permissions can be granted to together.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE ROLE role_name
[ ; ]

-- PostgreSQL's form, taken in this door: a principal that can log in
CREATE ROLE role_name LOGIN PASSWORD 'password'
[ ; ]

-- membership, PostgreSQL's form
GRANT role_name TO user_name
[ ; ]
```

## Arguments

*role_name*
: The role's name.

`LOGIN PASSWORD '...'`
: Makes a principal that can log in with this password: a user, shown as `SQL_USER`.

## Remarks

- `sys.database_principals` lists a role as `DATABASE_ROLE`. The role `public` exists already.
- Permissions granted to a role apply to its members.

## Differences from SQL Server

- **Members are added with `GRANT role TO user`.** `ALTER ROLE ... ADD MEMBER` and `DROP MEMBER` are error 102, and
  `sp_addrolemember` is error 2812. `sys.database_role_members` does not exist (208).
- `AUTHORIZATION owner` is error 102. `ALTER ROLE ... WITH NAME` is error 102.
- The fixed database roles (`db_owner`, `db_datareader`, `db_datawriter` ...) do not exist: `IS_MEMBER('db_owner')`
  is 0, also for `sa`.

## Examples

### A. A role, and a member

<!-- example: tsql -->
```sql
CREATE ROLE readers;
CREATE USER clerk;
GRANT readers TO clerk;
SELECT name, type_desc FROM sys.database_principals WHERE name IN ('readers', 'clerk', 'public') ORDER BY name;
```

```text
name    type_desc
------- -------------
clerk   SQL_USER
public  DATABASE_ROLE
readers DATABASE_ROLE

(3 rows affected)
```

### B. Grant to the role

<!-- example: tsql -->
```sql
CREATE TABLE dbo.price (item nvarchar(20), amount decimal(10,2));
GRANT SELECT ON dbo.price TO readers;
SELECT pr.name AS grantee, pe.permission_name, OBJECT_NAME(pe.major_id) AS object
FROM sys.database_permissions AS pe
JOIN sys.database_principals AS pr ON pr.principal_id = pe.grantee_principal_id
WHERE pr.name = 'readers';
```

```text
grantee permission_name object
------- --------------- ------
readers SELECT          price

(1 row affected)
```

### C. What lexdb does not take

<!-- example: tsql -->
```sql
ALTER ROLE readers ADD MEMBER clerk;
GO
EXEC sp_addrolemember 'readers', 'clerk';
GO
```

```text
Msg 102, Level 15, State 1, Line 1
unrecognized role option "add"
Msg 2812, Level 16, State 62, Line 1
Could not find stored procedure 'sp_addrolemember'.
```

## See also

[CREATE USER](create-user.md) · [DROP ROLE](drop-role.md) · [GRANT](grant.md)
