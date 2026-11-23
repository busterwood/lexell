# CREATE USER (Transact-SQL)

Makes a database user, which can be granted permissions on objects.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE USER user_name
[ ; ]
```

## Arguments

*user_name*
: The user's name.

## Remarks

- lexdb has one kind of principal for users, logins and roles: a user made by `CREATE USER` is listed both in
  `sys.database_principals` (as `SQL_USER`) and in `sys.server_principals` (as `SQL_LOGIN`).
- A user gets permissions with [GRANT](grant.md), directly or through a role (`GRANT role TO user`).
- A user that can log in, with a password, is made with PostgreSQL's form, which this door takes:
  `CREATE ROLE name LOGIN PASSWORD 'secret'` (see [CREATE ROLE](create-role.md)).
- A name already used is an error.

## Differences from SQL Server

- There is no `CREATE LOGIN` (error 50000). `CREATE USER name WITH PASSWORD = '...'` is error 102, and
  `FOR LOGIN`, `FROM LOGIN`, `WITHOUT LOGIN` and `WITH DEFAULT_SCHEMA` give error 102 ("unrecognized role option").
- `ALTER USER` is not supported (error 102).
- The session cannot change its user: `EXECUTE AS USER` and `SETUSER` are not supported.

## Examples

### A. A user, and the catalog

<!-- example: tsql -->
```sql
CREATE USER clerk;
SELECT name, type_desc FROM sys.database_principals WHERE name = 'clerk';
SELECT name, type_desc FROM sys.server_principals WHERE name = 'clerk';
```

```text
name  type_desc
----- ---------
clerk SQL_USER

(1 row affected)

name  type_desc
----- ---------
clerk SQL_LOGIN

(1 row affected)
```

### B. A user that can log in

<!-- example: tsql -->
```sql
CREATE ROLE app_login LOGIN PASSWORD 'secret';
SELECT name, type_desc FROM sys.database_principals WHERE name = 'app_login';
```

```text
name      type_desc
--------- ---------
app_login SQL_USER

(1 row affected)
```

### C. What lexdb does not take

<!-- example: tsql -->
```sql
CREATE USER clerk2 WITHOUT LOGIN;
GO
CREATE USER clerk3 WITH PASSWORD = 'secret';
GO
CREATE LOGIN clerk4 WITH PASSWORD = 'secret';
GO
```

```text
Msg 102, Level 15, State 1, Line 1
unrecognized role option "without"
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near '='.
Msg 50000, Level 16, State 1, Line 1
lexdb: CREATE LOGIN is not supported yet (CREATE makes tables, views, indexes, schemas, sequences, types, roles and users)
```

## See also

[CREATE ROLE](create-role.md) · [DROP USER](drop-user.md) · [GRANT](grant.md)
