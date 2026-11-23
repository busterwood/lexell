# DROP ROLE, DROP USER

Removes roles.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
DROP ROLE [ IF EXISTS ] name [, ...]
DROP USER [ IF EXISTS ] name [, ...]
```

## Arguments

`IF EXISTS`
: A role that does not exist is skipped with a notice.

*name*
: A role. `DROP USER` is the same statement as `DROP ROLE`.

## Remarks

- A role that owns objects is refused (2BP01); give the objects to another role first (`ALTER TABLE ... OWNER TO`),
  or drop them.
- The role's privileges and memberships go with it.
- `DROP ROLE` is transactional.

## Differences from PostgreSQL

- A role that holds privileges on objects is dropped, with its privileges. PostgreSQL refuses it until they are
  revoked.
- `REASSIGN OWNED` and `DROP OWNED` are syntax errors.

## Examples

<!--setup: postgresql
CREATE ROLE ann;
CREATE ROLE bob;
CREATE ROLE cy;
CREATE TABLE doc (id int, body text);
GRANT SELECT ON doc TO bob;
-->

The examples use three roles and a table that `bob` may read:

```sql
CREATE ROLE ann;
CREATE ROLE bob;
CREATE ROLE cy;
CREATE TABLE doc (id int, body text);
GRANT SELECT ON doc TO bob;
```

### A. Drop roles

<!-- example: postgresql -->
```sql
DROP ROLE ann;
DROP USER IF EXISTS ann;
DROP ROLE bob;
SELECT grantee FROM information_schema.table_privileges WHERE table_name = 'doc' AND grantee = 'bob';
```

```text
DROP ROLE
NOTICE:  role "ann" does not exist, skipping
DROP ROLE
DROP ROLE
 grantee
---------
(0 rows)
```

### B. A role that owns a table

<!-- example: postgresql -->
```sql
CREATE TABLE note (body text);
ALTER TABLE note OWNER TO cy;
DROP ROLE cy;
DROP TABLE note;
DROP ROLE cy;
```

```text
CREATE TABLE
ALTER TABLE
ERROR:  role "cy" cannot be dropped because some objects depend on it (it owns note)
DROP TABLE
DROP ROLE
```

## See also

[CREATE ROLE](create-role.md) · [ALTER ROLE](alter-role.md) · [REVOKE](revoke.md)
