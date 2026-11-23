# REVOKE

Takes privileges away from roles, or ends roles' memberships.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
REVOKE { privilege [, ...] | ALL [ PRIVILEGES ] }
    ON object
    FROM role_specification [, ...]
    [ GRANTED BY role_specification ] [ CASCADE | RESTRICT ]

REVOKE role_name [, ...] FROM role_specification [, ...]
    [ GRANTED BY role_specification ] [ CASCADE | RESTRICT ]
```

*privilege*, *object* and *role_specification* are as in [GRANT](grant.md).

## Arguments

*privilege*
: The privileges to take away. `ALL` takes every privilege the role was granted on the object.

`FROM` *role*
: The roles that lose them. `PUBLIC` takes back what was granted to `PUBLIC`; a role keeps what it was granted
  itself, or through a group.

`REVOKE` *role* `FROM` *member*
: Ends a membership.

`GRANTED BY`, `CASCADE`, `RESTRICT`
: Accepted.

## Remarks

- Revoking a privilege that is not held does nothing.
- An owner's and a superuser's privileges are not taken away by `REVOKE`.
- `REVOKE` is transactional.

## Differences from PostgreSQL

- `REVOKE GRANT OPTION FOR` and `REVOKE ADMIN OPTION FOR` are refused (0A000): there are no grant options.
- Column privileges are not supported (0A000).

## Examples

<!--setup: postgresql
CREATE TABLE doc (id int PRIMARY KEY, body text);
INSERT INTO doc VALUES (1, 'hello');
CREATE ROLE readers;
CREATE ROLE ann LOGIN;
GRANT SELECT, INSERT, UPDATE ON doc TO ann;
GRANT SELECT ON doc TO readers;
GRANT readers TO ann;
-->

The examples use a table that `ann` may read and change, and a group she is in:

```sql
CREATE TABLE doc (id int PRIMARY KEY, body text);
INSERT INTO doc VALUES (1, 'hello');
CREATE ROLE readers;
CREATE ROLE ann LOGIN;
GRANT SELECT, INSERT, UPDATE ON doc TO ann;
GRANT SELECT ON doc TO readers;
GRANT readers TO ann;
```

### A. Take away some privileges

<!-- example: postgresql -->
```sql
REVOKE INSERT, UPDATE ON doc FROM ann;
SELECT privilege_type FROM information_schema.table_privileges WHERE table_name = 'doc' AND grantee = 'ann';
```

```text
REVOKE
 privilege_type
----------------
 SELECT
(1 row)
```

### B. A privilege still held through a group

<!-- example: postgresql -->
```sql
REVOKE SELECT ON doc FROM ann;
SET ROLE ann;
SELECT body FROM doc;
RESET ROLE;
REVOKE readers FROM ann;
SET ROLE ann;
SELECT body FROM doc;
RESET ROLE;
```

```text
REVOKE
SET
 body
-------
 hello
(1 row)

RESET
REVOKE ROLE
SET
ERROR:  permission denied for table doc
RESET
```

### C. Errors

<!-- example: postgresql -->
```sql
REVOKE GRANT OPTION FOR SELECT ON doc FROM ann;
REVOKE SELECT ON nosuch FROM ann;
```

```text
ERROR:  lexdb: grant options are not supported
ERROR:  relation "nosuch" does not exist
```

## See also

[GRANT](grant.md) · [DROP ROLE](drop-role.md)
