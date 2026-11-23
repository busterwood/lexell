# REVOKE

Takes privileges and roles back.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
REVOKE { object_privilege [, ...] | ALL [ PRIVILEGES ] } ON [ schema. ] object FROM { user | role | PUBLIC } [, ...]

REVOKE { system_privilege | role } [, ...] FROM { user | role | PUBLIC } [, ...]
```

## Remarks

- The privileges are those of [GRANT](grant.md). Revoking a privilege that was not granted succeeds without a
  change.
- A user or role that does not exist is ORA-01917; an object that does not exist, ORA-00942.

## Differences from Oracle

- Revoking something not granted is not an error (Oracle: ORA-01927 or ORA-01952).
- `CASCADE CONSTRAINTS` and `FORCE` are not supported.

## Examples

<!--setup: oracle
CREATE USER ann IDENTIFIED BY secret1;
CREATE USER bob;
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20));
GRANT SELECT, INSERT, UPDATE ON emp TO ann;
GRANT SELECT ON emp TO bob;
-->

The examples use users `ann` and `bob`, and a table `emp` on which `ann` has `SELECT`, `INSERT` and `UPDATE`, and
`bob` has `SELECT`.

### A. Revoke object privileges

<!-- example: oracle -->
```sql
SELECT grantee, privilege FROM user_tab_privs ORDER BY grantee, privilege;
REVOKE INSERT ON emp FROM ann;
REVOKE SELECT ON emp FROM bob;
SELECT grantee, privilege FROM user_tab_privs ORDER BY grantee, privilege;
```

```text
GRANTEE PRIVILEGE
------- ---------
ANN     INSERT
ANN     SELECT
ANN     UPDATE
BOB     SELECT

4 rows selected.

Revoke succeeded.

Revoke succeeded.

GRANTEE PRIVILEGE
------- ---------
ANN     SELECT
ANN     UPDATE

2 rows selected.
```

### B. Revoke what was never granted

<!-- example: oracle -->
```sql
REVOKE DELETE ON emp FROM ann;
REVOKE ALL ON emp FROM ann;
SELECT COUNT(*) AS left_for_ann FROM user_tab_privs WHERE grantee = 'ANN';
```

```text
Revoke succeeded.

Revoke succeeded.

LEFT_FOR_ANN
------------
           0

1 row selected.
```

### C. Roles and system privileges

<!-- example: oracle -->
```sql
CREATE ROLE clerk;
GRANT clerk TO bob;
GRANT CREATE SESSION TO bob;
REVOKE clerk FROM bob;
REVOKE CREATE SESSION FROM bob;
```

```text
Role created.

Grant succeeded.

Grant succeeded.

Revoke succeeded.

Revoke succeeded.
```

### D. Errors

<!-- example: oracle -->
```sql
REVOKE SELECT ON emp FROM nobody;
REVOKE SELECT ON nothere FROM ann;
```

```text
ERROR:
ORA-01917: user or role 'NOBODY' does not exist

ERROR:
ORA-00942: table or view does not exist
```

## See also

[GRANT](grant.md), [CREATE ROLE](create-role.md)
