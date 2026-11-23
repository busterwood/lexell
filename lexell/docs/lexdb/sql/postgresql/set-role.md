# SET ROLE, SET SESSION AUTHORIZATION

Changes the role the session acts as.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SET [ SESSION ] ROLE role_name
SET [ SESSION ] ROLE NONE
RESET ROLE

SET SESSION AUTHORIZATION user_name
SET SESSION AUTHORIZATION DEFAULT
RESET SESSION AUTHORIZATION
```

## Arguments

`SET ROLE` *role_name*
: The session's privileges become *role_name*'s: `current_user` is the role, `session_user` stays. The session's
  role must be a member of it, or a superuser (42501 otherwise).

`SET ROLE NONE`, `RESET ROLE`
: Back to the session user.

`SET SESSION AUTHORIZATION` *user_name*
: For a superuser: the session acts as *user_name*, and both `session_user` and `current_user` become it.

`DEFAULT`, `RESET SESSION AUTHORIZATION`
: Back to the user that logged in.

## Remarks

- Objects made after `SET ROLE` are owned by the role.
- `SET ROLE` in a transaction block that rolls back is undone with it.

## Differences from PostgreSQL

- `SET LOCAL ROLE` is accepted and does nothing (example D).

## Examples

<!--setup: postgresql
CREATE TABLE doc (id int PRIMARY KEY, body text);
INSERT INTO doc VALUES (1, 'hello');
CREATE ROLE readers;
CREATE ROLE ann LOGIN;
CREATE ROLE bob LOGIN;
GRANT SELECT ON doc TO readers;
GRANT readers TO ann;
-->

The examples use a table that the group `readers` may read; `ann` is in the group and `bob` is not:

```sql
CREATE TABLE doc (id int PRIMARY KEY, body text);
INSERT INTO doc VALUES (1, 'hello');
CREATE ROLE readers;
CREATE ROLE ann LOGIN;
CREATE ROLE bob LOGIN;
GRANT SELECT ON doc TO readers;
GRANT readers TO ann;
```

### A. SET ROLE

<!-- example: postgresql -->
```sql
SET ROLE ann;
SELECT current_user, session_user;
SELECT body FROM doc;
DELETE FROM doc;
RESET ROLE;
SELECT current_user;
```

```text
SET
 current_user | session_user
--------------+--------------
 ann          | postgres
(1 row)

 body
-------
 hello
(1 row)

ERROR:  permission denied for table doc
RESET
 current_user
--------------
 postgres
(1 row)
```

### B. SET SESSION AUTHORIZATION

<!-- example: postgresql -->
```sql
SET SESSION AUTHORIZATION bob;
SELECT current_user, session_user;
SELECT body FROM doc;
SET ROLE readers;
RESET SESSION AUTHORIZATION;
SELECT current_user, session_user;
```

```text
SET
 current_user | session_user
--------------+--------------
 bob          | bob
(1 row)

ERROR:  permission denied for table doc
ERROR:  permission denied to set role "readers"
RESET
 current_user | session_user
--------------+--------------
 postgres     | postgres
(1 row)
```

### C. The owner of new objects

<!-- example: postgresql -->
```sql
CREATE SCHEMA scratch;
GRANT CREATE, USAGE ON SCHEMA scratch TO ann;
SET ROLE ann;
CREATE TABLE scratch.mine (x int);
RESET ROLE;
SELECT tableowner FROM pg_tables WHERE tablename = 'mine';
```

```text
CREATE SCHEMA
GRANT
SET
CREATE TABLE
RESET
 tableowner
------------
 ann
(1 row)
```

### D. In a transaction block

<!-- example: postgresql -->
```sql
BEGIN;
SET ROLE ann;
SELECT current_user;
ROLLBACK;
SELECT current_user;
BEGIN;
SET LOCAL ROLE ann;
SELECT current_user;
COMMIT;
```

```text
BEGIN
SET
 current_user
--------------
 ann
(1 row)

ROLLBACK
 current_user
--------------
 postgres
(1 row)

BEGIN
SET
 current_user
--------------
 postgres
(1 row)

COMMIT
```

## See also

[GRANT](grant.md) · [CREATE ROLE](create-role.md) · [SET](set.md)
