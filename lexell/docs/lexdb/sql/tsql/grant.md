# GRANT (Transact-SQL)

Gives a user or a role permissions on a table, view, procedure or function, or makes a user a member of a role.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
GRANT { ALL [ PRIVILEGES ] | permission [ ,...n ] }
    ON [ OBJECT :: ] [ schema_name. ] object_name
    TO principal [ ,...n ]
[ ; ]

permission ::= SELECT | INSERT | UPDATE | DELETE | REFERENCES | EXECUTE | EXEC

-- membership (PostgreSQL's form)
GRANT role_name TO principal
[ ; ]
```

## Arguments

*permission*
: `SELECT`, `INSERT`, `UPDATE`, `DELETE` and `REFERENCES` on tables and views; `EXECUTE` on procedures and functions.
  `ALL` is every permission the object has.

`OBJECT ::` *object_name*
: The object. `OBJECT::` may be left out.

*principal*
: A user, a role, or `public` (everyone).

## Remarks

- The owner of an object (and `sa`) has every permission on it. Other users need a grant: without it, a statement
  fails with error 229 ("permission was denied").
- A procedure runs with its owner's rights: a user with `EXECUTE` on it need not have permissions on the tables it
  uses.
- `sys.database_permissions` lists the grants, with `HAS_PERMS_BY_NAME` and `sp_table_privileges` reporting them.
- An unknown object or principal is error 15151.

## Differences from SQL Server

- Column permissions (`GRANT UPDATE (name) ON t`) are error 50000 ("lexdb: column privileges are not supported").
- `WITH GRANT OPTION` is error 50000 ("lexdb: grant and admin options are not supported").
- Permissions on a schema (`ON SCHEMA::dbo`) are error 50000. Database permissions (`GRANT CREATE TABLE TO ...`)
  are error 156. `DENY` is error 102.
- Because the error comes from the parser, the whole batch is refused, its other statements included.

## Examples

<!--setup: tsql
CREATE TABLE dbo.price (item nvarchar(20), amount decimal(10,2));
CREATE USER clerk;
CREATE ROLE readers;
-->

The examples use a table, a user and a role:

```sql
CREATE TABLE dbo.price (item nvarchar(20), amount decimal(10,2));
CREATE USER clerk;
CREATE ROLE readers;
```

### A. Grant on a table

<!-- example: tsql -->
```sql
GRANT SELECT ON dbo.price TO readers;
GRANT SELECT, INSERT ON OBJECT::dbo.price TO clerk;
SELECT pr.name AS grantee, pe.permission_name, pe.state_desc, OBJECT_NAME(pe.major_id) AS object
FROM sys.database_permissions AS pe
JOIN sys.database_principals AS pr ON pr.principal_id = pe.grantee_principal_id
WHERE pe.major_id = OBJECT_ID('dbo.price')
ORDER BY grantee, pe.permission_name;
```

```text
grantee permission_name state_desc object
------- --------------- ---------- ------
clerk   INSERT          GRANT      price
clerk   SELECT          GRANT      price
readers SELECT          GRANT      price

(3 rows affected)
```

### B. EXECUTE on a procedure, and role membership

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.price_list AS SELECT item, amount FROM dbo.price;
GO
GRANT EXECUTE ON dbo.price_list TO readers;
GRANT readers TO clerk;
SELECT pr.name AS grantee, pe.permission_name, OBJECT_NAME(pe.major_id) AS object
FROM sys.database_permissions AS pe
JOIN sys.database_principals AS pr ON pr.principal_id = pe.grantee_principal_id
WHERE pe.major_id = OBJECT_ID('dbo.price_list');
```

```text
grantee permission_name object
------- --------------- ----------
readers EXECUTE         price_list

(1 row affected)
```

### C. ALL

<!-- example: tsql -->
```sql
CREATE TABLE dbo.note (id int, body nvarchar(100));
GRANT ALL ON dbo.note TO clerk;
SELECT pe.permission_name FROM sys.database_permissions AS pe
WHERE pe.major_id = OBJECT_ID('dbo.note') ORDER BY pe.permission_name;
```

```text
permission_name
---------------
DELETE
INSERT
REFERENCES
SELECT
UPDATE

(5 rows affected)
```

### D. Errors

<!-- example: tsql -->
```sql
GRANT SELECT ON dbo.nothere TO clerk;
GRANT SELECT ON dbo.price TO nobody;
GO
GRANT UPDATE (amount) ON dbo.price TO clerk;
GO
GRANT SELECT ON dbo.price TO clerk WITH GRANT OPTION;
GO
DENY SELECT ON dbo.price TO clerk;
GO
```

```text
Msg 15151, Level 16, State 1, Line 1
Cannot find the object 'nothere', because it does not exist or you do not have permission.
Msg 15151, Level 16, State 1, Line 2
Cannot find the user 'nobody', because it does not exist or you do not have permission.
Msg 50000, Level 16, State 1, Line 1
lexdb: column privileges are not supported
Msg 50000, Level 16, State 1, Line 1
lexdb: grant and admin options are not supported
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'deny'.
```

## See also

[REVOKE](revoke.md) · [CREATE USER](create-user.md) · [CREATE ROLE](create-role.md)
