# GRANT

Gives privileges on objects to roles, or makes roles members of other roles.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
GRANT { { SELECT | INSERT | UPDATE | DELETE | TRUNCATE | REFERENCES | TRIGGER | MAINTAIN } [, ...] | ALL [ PRIVILEGES ] }
    ON { [ TABLE ] table_name [, ...] | ALL TABLES IN SCHEMA schema_name }
    TO role_specification [, ...]

GRANT { { USAGE | SELECT | UPDATE } [, ...] | ALL [ PRIVILEGES ] }
    ON { SEQUENCE sequence_name [, ...] | ALL SEQUENCES IN SCHEMA schema_name }
    TO role_specification [, ...]

GRANT { { CREATE | USAGE } [, ...] | ALL [ PRIVILEGES ] }
    ON SCHEMA schema_name [, ...]
    TO role_specification [, ...]

GRANT { { CREATE | CONNECT | TEMPORARY | TEMP } [, ...] | ALL [ PRIVILEGES ] }
    ON DATABASE database_name [, ...]
    TO role_specification [, ...]

GRANT { EXECUTE | ALL [ PRIVILEGES ] }
    ON { { FUNCTION | PROCEDURE | ROUTINE } routine_name [ ( [ argument_type [, ...] ] ) ] [, ...]
         | ALL { FUNCTIONS | PROCEDURES | ROUTINES } IN SCHEMA schema_name }
    TO role_specification [, ...]

GRANT role_name [, ...] TO role_specification [, ...] [ GRANTED BY role_specification ]

role_specification:
    [ GROUP ] role_name | PUBLIC | CURRENT_USER | SESSION_USER
```

## Arguments

*privileges*
: What the role may do. On a table or view: `SELECT` (read), `INSERT`, `UPDATE`, `DELETE`, `TRUNCATE`,
  `REFERENCES` (make a foreign key to it) and `TRIGGER` (kept, though there are no triggers); `MAINTAIN` is
  accepted and not kept. On a sequence: `USAGE`, `SELECT`, `UPDATE`. On a schema: `USAGE`, `CREATE`. On a
  function or procedure: `EXECUTE`. `ALL` is every privilege of the kind of object.

`ALL TABLES IN SCHEMA`, `ALL SEQUENCES`, `ALL FUNCTIONS` ...
: Every object of the kind in the schema now; objects made later are not included.

*role_specification*
: The roles that receive the privileges. `PUBLIC` is every role, now and later.

`GRANT` *role* `TO` *member*
: Makes *member* a member of *role*: it has *role*'s privileges and may `SET ROLE` to it.

## Remarks

- The owner of an object (the role that made it) and superusers have every privilege on it. Others need a grant,
  to them, to a role they are a member of, or to `PUBLIC`; otherwise 42501 (`permission denied for table doc`).
- `information_schema.table_privileges`, `relacl` in `pg_class`, and `has_table_privilege` and the other
  `has_*_privilege` functions show them.
- Granting a privilege that is held already does nothing.
- `GRANT` is transactional.

## Differences from PostgreSQL

- Not supported (0A000): column privileges (`GRANT UPDATE (body) ON doc`), `WITH GRANT OPTION`, `WITH ADMIN
  OPTION`, `WITH INHERIT` and `WITH SET`, privileges on types, domains, languages, tablespaces, foreign objects and
  large objects.
- `ALTER DEFAULT PRIVILEGES` is not supported (0A000) (lexdb-gaps.md 2.2).
- There is no row security.

## Examples

<!--setup: postgresql
CREATE TABLE doc (id int PRIMARY KEY, body text);
INSERT INTO doc VALUES (1, 'hello');
CREATE ROLE readers;
CREATE ROLE ann LOGIN;
CREATE ROLE bob LOGIN;
-->

The examples use a table and three roles:

```sql
CREATE TABLE doc (id int PRIMARY KEY, body text);
INSERT INTO doc VALUES (1, 'hello');
CREATE ROLE readers;
CREATE ROLE ann LOGIN;
CREATE ROLE bob LOGIN;
```

### A. Privileges on a table

<!-- example: postgresql -->
```sql
GRANT SELECT, INSERT ON doc TO ann;
SET ROLE ann;
SELECT * FROM doc;
INSERT INTO doc VALUES (2, 'from ann');
UPDATE doc SET body = 'x';
RESET ROLE;
```

```text
GRANT
SET
 id | body
----+-------
  1 | hello
(1 row)

INSERT 0 1
ERROR:  permission denied for table doc
RESET
```

### B. Through a group

<!-- example: postgresql -->
```sql
GRANT SELECT ON doc TO readers;
GRANT readers TO bob;
SET ROLE bob;
SELECT count(*) FROM doc;
RESET ROLE;
```

```text
GRANT
GRANT ROLE
SET
 count
-------
     2
(1 row)

RESET
```

### C. Seeing the privileges

<!-- example: postgresql -->
```sql
SELECT grantee, privilege_type FROM information_schema.table_privileges
WHERE table_name = 'doc' AND grantee <> 'postgres' ORDER BY 1, 2;
SELECT has_table_privilege('ann', 'doc', 'INSERT'), has_table_privilege('ann', 'doc', 'DELETE');
```

```text
 grantee | privilege_type
---------+----------------
 ann     | INSERT
 ann     | SELECT
 readers | SELECT
(3 rows)

 has_table_privilege | has_table_privilege
---------------------+---------------------
 t                   | f
(1 row)
```

### D. Schemas, sequences and PUBLIC

<!-- example: postgresql -->
```sql
CREATE SCHEMA app;
GRANT USAGE ON SCHEMA app TO readers;
CREATE SEQUENCE doc_no;
GRANT USAGE ON SEQUENCE doc_no TO PUBLIC;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO readers;
```

```text
CREATE SCHEMA
GRANT
CREATE SEQUENCE
GRANT
GRANT
```

### E. Errors

<!-- example: postgresql -->
```sql
GRANT UPDATE (body) ON doc TO ann;
GRANT SELECT ON doc TO ann WITH GRANT OPTION;
GRANT SELECT ON doc TO nosuch;
GRANT SELECT ON nosuch TO ann;
```

```text
ERROR:  lexdb: column privileges are not supported
ERROR:  lexdb: grant and admin options are not supported
ERROR:  role "nosuch" does not exist
ERROR:  relation "nosuch" does not exist
```

## See also

[REVOKE](revoke.md) · [CREATE ROLE](create-role.md) · [SET ROLE](set-role.md)
