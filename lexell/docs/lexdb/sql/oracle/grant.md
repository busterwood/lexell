# GRANT

Gives privileges on objects, and roles and system privileges, to users and roles.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
GRANT { object_privilege [, ...] | ALL [ PRIVILEGES ] } ON [ schema. ] object
    TO { user | role | PUBLIC } [, ...] [ WITH GRANT OPTION ]

GRANT { system_privilege | role } [, ...] TO { user | role | PUBLIC } [, ...] [ WITH ADMIN OPTION ]
```

## Arguments

*object_privilege*
: `SELECT`, `INSERT`, `UPDATE`, `DELETE` and `REFERENCES` on a table, view or sequence; `EXECUTE` on a procedure,
  function or package (accepted, no effect). `ALL` gives the five.

*system_privilege*, *role*
: `CREATE SESSION` and `CONNECT` let a user log in; `DBA` and `ALL PRIVILEGES` make the user a superuser;
  `RESOURCE`, `CREATE TABLE` and the other `CREATE ...` privileges are accepted. A role made with
  [CREATE ROLE](create-role.md) can be granted to users and other roles.

`WITH GRANT OPTION`, `WITH ADMIN OPTION`
: Accepted, but not kept: `USER_TAB_PRIVS.GRANTABLE` is always `NO`.

`PUBLIC`
: Every user.

## Remarks

- Object privileges show in `USER_TAB_PRIVS`; see the examples.
- Privileges on a table that does not exist are ORA-00942; to a user or role that does not exist, ORA-01917.
- A privilege on an object can be given to a role, and the role to users.

## Differences from Oracle

- **A column list is not supported**: `GRANT UPDATE (name) ON emp TO ann` is ORA-03001.
- `GRANT EXECUTE ON name` for a procedure is accepted; the name is checked (ORA-04042 when it does not exist).
- `GRANT` of a system privilege or role that lexdb does not know (`GRANT bogus_priv TO ann`) succeeds without
  doing anything.
- System privileges and roles granted are not listed: `DBA_SYS_PRIVS`, `DBA_ROLE_PRIVS` and `DBA_ROLES` have no
  rows, and `USER_ROLE_PRIVS`, `SESSION_PRIVS` and `SESSION_ROLES` show a recorded sample of Oracle's, not the
  session's real ones.
- `USER_TAB_PRIVS_MADE`, `USER_TAB_PRIVS_RECD` and `ROLE_TAB_PRIVS` do not exist (ORA-00942); `ALL_TAB_PRIVS` has no
  `OWNER` column (ORA-00904). Use `USER_TAB_PRIVS`.
- `GRANT ALL` gives five privileges; Oracle also gives `ALTER`, `INDEX` and others.

## Examples

<!--setup: oracle
CREATE USER ann IDENTIFIED BY secret1;
CREATE USER bob;
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20));
CREATE TABLE dept (id NUMBER);
-->

The examples use users `ann` and `bob` and two tables, `emp` and `dept`.

### A. Object privileges

<!-- example: oracle -->
```sql
GRANT SELECT ON emp TO ann;
GRANT SELECT, INSERT ON emp TO bob WITH GRANT OPTION;
GRANT ALL ON dept TO ann;
SELECT grantee, table_name, privilege, grantable FROM user_tab_privs ORDER BY grantee, table_name, privilege;
```

```text
Grant succeeded.

Grant succeeded.

Grant succeeded.

GRANTEE TABLE_NAME PRIVILEGE  GRANTABLE
------- ---------- ---------- ---------
ANN     DEPT       DELETE     NO
ANN     DEPT       INSERT     NO
ANN     DEPT       REFERENCES NO
ANN     DEPT       SELECT     NO
ANN     DEPT       UPDATE     NO
ANN     EMP        SELECT     NO
BOB     EMP        INSERT     NO
BOB     EMP        SELECT     NO

8 rows selected.
```

### B. A role holds the privileges

<!-- example: oracle -->
```sql
CREATE ROLE clerk;
GRANT SELECT ON dept TO clerk;
GRANT clerk TO ann;
SELECT grantee, table_name, privilege FROM user_tab_privs WHERE grantee = 'CLERK';
```

```text
Role created.

Grant succeeded.

Grant succeeded.

GRANTEE TABLE_NAME PRIVILEGE
------- ---------- ---------
CLERK   DEPT       SELECT

1 row selected.
```

### C. System privileges and roles

<!-- example: oracle -->
```sql
GRANT CREATE SESSION, CREATE TABLE TO ann;
GRANT CONNECT, RESOURCE TO bob;
GRANT UNLIMITED TABLESPACE TO ann;
SELECT COUNT(*) AS rows_in_dba_sys_privs FROM dba_sys_privs WHERE grantee = 'ANN';
```

```text
Grant succeeded.

Grant succeeded.

Grant succeeded.

ROWS_IN_DBA_SYS_PRIVS
---------------------
                    0

1 row selected.
```

### D. PUBLIC, and several grantees

<!-- example: oracle -->
```sql
GRANT SELECT ON emp TO PUBLIC;
GRANT DELETE ON emp TO ann, bob;
SELECT grantee, table_name, privilege FROM user_tab_privs WHERE table_name = 'EMP' ORDER BY grantee, privilege;
```

```text
Grant succeeded.

Grant succeeded.

GRANTEE TABLE_NAME PRIVILEGE
------- ---------- ---------
ANN     EMP        DELETE
ANN     EMP        SELECT
BOB     EMP        DELETE
BOB     EMP        INSERT
BOB     EMP        SELECT
PUBLIC  EMP        SELECT

6 rows selected.
```

### E. Errors

<!-- example: oracle -->
```sql
GRANT SELECT ON nothere TO ann;
GRANT SELECT ON emp TO nobody;
GRANT CREATE SESSION TO nobody;
GRANT UPDATE (name) ON emp TO ann;
GRANT EXECUTE ON nothere TO ann;
```

```text
ERROR:
ORA-00942: table or view does not exist

ERROR:
ORA-01917: user or role 'NOBODY' does not exist

ERROR:
ORA-01917: user or role 'NOBODY' does not exist

ERROR:
ORA-03001: unimplemented feature

ERROR:
ORA-04042: procedure, function, package, or package body does not exist
```

## See also

[REVOKE](revoke.md), [CREATE ROLE](create-role.md), [CREATE USER](create-user.md)
