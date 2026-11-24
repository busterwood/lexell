# CREATE USER

Creates a user, who is also a schema that owns objects.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE USER user [ IDENTIFIED BY password ]
    [ DEFAULT TABLESPACE name ] [ TEMPORARY TABLESPACE name ] [ QUOTA ... ON name ] [ PASSWORD EXPIRE ]
```

## Arguments

*user*
: The user's name, folded to upper case unless quoted. It is also the name of the user's schema: objects made by
  the user, or in `user.table` form, live there.

`IDENTIFIED BY password`
: The password for logins. Without it the user cannot log in. See the remarks.

`DEFAULT TABLESPACE`, `TEMPORARY TABLESPACE`, `QUOTA`, `PASSWORD EXPIRE`
: Accepted and ignored: lexdb has no tablespaces or quotas.

## Remarks

- A new user has no rights. `GRANT CREATE SESSION TO user` lets the user log in (it makes the login usable);
  see [GRANT](grant.md).
- A user is a lexdb role with its own schema, made by `CREATE USER`. (A login that was made in another door has its
  schema made at its first Oracle connection.) A user and a role cannot share a name (ORA-01920).
- The other doors see the user's tables as `schema."NAME"` in the PostgreSQL door and `schema.NAME` in the SQL Server
  door: see [Schemas](../../connect/oracle.md#schemas).
- `ALL_USERS` and `DBA_USERS` list only the users that can log in: those granted `CREATE SESSION` or `CONNECT`. A
  user without that grant owns a schema but is not listed (see example A).

## Differences from Oracle

- `ALL_USERS` also lists fixed names Oracle databases have (`SYS`, `SYSTEM`, `AUDSYS`, `XDB` and others) that are
  not real users here.
- `DBA_USERS` has `USERNAME` and `ACCOUNT_STATUS` (always `OPEN`); `ALL_USERS` has `USERNAME` and little else
  (`ACCOUNT_STATUS` there is ORA-00904).
- Profiles, `CONTAINER`, external and global authentication are not supported.

## Examples

### A. Create a user

<!-- example: oracle -->
```sql
CREATE USER ann IDENTIFIED BY secret1;
SELECT username FROM all_users WHERE username = 'ANN';
SELECT username FROM dba_users WHERE username = 'ANN';
GRANT CREATE SESSION TO ann;
SELECT username, account_status FROM dba_users WHERE username = 'ANN';
```

```text
User created.

no rows selected

no rows selected

Grant succeeded.

USERNAME ACCOUNT_STATUS
-------- --------------
ANN      OPEN

1 row selected.
```

### B. A user that exists

<!-- example: oracle -->
```sql
CREATE USER ann IDENTIFIED BY x;
```

```text
ERROR:
ORA-01920: user name 'ANN' conflicts with another user or role name
```

### C. A user owns a schema

<!-- example: oracle -->
```sql
CREATE USER hr IDENTIFIED BY pw;
CREATE TABLE hr.t (a NUMBER);
INSERT INTO hr.t VALUES (1);
COMMIT;
SELECT owner, table_name FROM all_tables WHERE table_name = 'T';
SELECT * FROM hr.t;
```

```text
User created.

Table created.

1 row created.

Commit complete.

OWNER TABLE_NAME
----- ----------
HR    T

1 row selected.

A
-
1

1 row selected.
```

### D. The other doors see the schema

<!-- example: postgresql -->
```sql
SELECT schemaname, tablename FROM pg_tables WHERE schemaname = 'hr';
SELECT hr."T".a FROM hr."T";
```

```text
 schemaname | tablename
------------+-----------
 hr         | T
(1 row)

 a
---
 1
(1 row)
```

### E. Options that are accepted

<!-- example: oracle -->
```sql
CREATE USER cy IDENTIFIED BY pw DEFAULT TABLESPACE users QUOTA UNLIMITED ON users;
CREATE USER di IDENTIFIED BY pw PASSWORD EXPIRE;
SELECT owner, table_name FROM all_tables WHERE owner IN ('CY', 'DI');
```

```text
User created.

User created.

no rows selected
```

## See also

[ALTER USER](alter-user.md), [DROP USER](drop-user.md), [GRANT](grant.md), [CREATE ROLE](create-role.md),
[ALTER SESSION](alter-session.md)
