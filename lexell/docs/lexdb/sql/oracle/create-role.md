# CREATE ROLE, DROP ROLE

Creates and drops a role: a name that holds privileges and is granted to users.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE ROLE role
DROP ROLE role
```

## Remarks

- A role gets privileges with [GRANT](grant.md), and is granted to users and other roles.
- A role and a user cannot share a name: ORA-01920. `DROP ROLE` of a role that does not exist is ORA-01917.

## Differences from Oracle

- `IDENTIFIED BY password`, `NOT IDENTIFIED`, `CONTAINER` and the other options are ORA-00900.
- Roles are not listed in `DBA_ROLES`.

## Examples

### A. Create a role, use it, drop it

<!-- example: oracle -->
```sql
CREATE TABLE emp (id NUMBER PRIMARY KEY);
CREATE USER ann IDENTIFIED BY secret1;
CREATE ROLE clerk;
GRANT SELECT ON emp TO clerk;
GRANT clerk TO ann;
SELECT grantee, table_name, privilege FROM user_tab_privs WHERE grantee = 'CLERK';
DROP ROLE clerk;
SELECT COUNT(*) AS left_for_clerk FROM user_tab_privs WHERE grantee = 'CLERK';
```

```text
Table created.

User created.

Role created.

Grant succeeded.

Grant succeeded.

GRANTEE TABLE_NAME PRIVILEGE
------- ---------- ---------
CLERK   EMP        SELECT

1 row selected.

Role dropped.

LEFT_FOR_CLERK
--------------
             0

1 row selected.
```

### B. Errors

<!-- example: oracle -->
```sql
CREATE ROLE ann;
CREATE ROLE r2;
CREATE ROLE r2;
DROP ROLE nothere;
CREATE ROLE r3 IDENTIFIED BY pw;
```

```text
ERROR:
ORA-01920: user name conflicts with another user or role name

Role created.

ERROR:
ORA-01920: user name conflicts with another user or role name

ERROR:
ORA-01917: user or role 'NOTHERE' does not exist

ERROR:
ORA-00900: invalid SQL statement
```

## See also

[GRANT](grant.md), [REVOKE](revoke.md), [CREATE USER](create-user.md)
