# ALTER USER

Changes a user's password or locks and unlocks the account.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
ALTER USER user { IDENTIFIED BY password | ACCOUNT { LOCK | UNLOCK } }
```

## Arguments

`IDENTIFIED BY password`
: Sets a new password.

`ACCOUNT LOCK`, `ACCOUNT UNLOCK`
: A locked account cannot log in, and is no longer listed in `ALL_USERS` and `DBA_USERS` (there is no `LOCKED` status).

## Remarks

- A user that does not exist is ORA-01918.

## Differences from Oracle

- Only these two forms are taken; `DEFAULT TABLESPACE`, `QUOTA`, `PROFILE` and
  the other options are not supported.

## Examples

<!--setup: oracle
CREATE USER bob IDENTIFIED BY pw;
GRANT CREATE SESSION TO bob;
-->

### A. Change the password and lock the account

<!-- example: oracle -->
```sql
ALTER USER bob IDENTIFIED BY newpw;
ALTER USER bob ACCOUNT LOCK;
SELECT username, account_status FROM dba_users WHERE username = 'BOB';
ALTER USER bob ACCOUNT UNLOCK;
SELECT username, account_status FROM dba_users WHERE username = 'BOB';
```

```text
User altered.

User altered.

no rows selected

User altered.

USERNAME ACCOUNT_STATUS
-------- --------------
BOB      OPEN

1 row selected.
```

### B. A user that does not exist

<!-- example: oracle -->
```sql
ALTER USER nobody ACCOUNT LOCK;
```

```text
ERROR:
ORA-01918: user 'NOBODY' does not exist
```

## See also

[CREATE USER](create-user.md), [DROP USER](drop-user.md)
