# ALTER SCHEMA

Renames a schema or gives it a new owner.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
ALTER SCHEMA name RENAME TO new_name
ALTER SCHEMA name OWNER TO { new_owner | CURRENT_USER | SESSION_USER }
```

## Arguments

*name*
: The schema.

*new_name*
: Its new name. Names beginning with `pg_` are refused (42939).

*new_owner*
: The role that is to own it.

## Remarks

- The schema's tables, indexes and other objects go with it to the new name.
- `ALTER SCHEMA` is transactional.

## Differences from PostgreSQL

- A schema that holds a view, or that a view reads from, cannot be renamed (2BP01, `... (lexdb keeps a view's
  text)`). PostgreSQL renames it.
- The `public` schema cannot be renamed (0A000).

## Examples

<!--setup: postgresql
CREATE SCHEMA app;
CREATE TABLE app.setting (name text PRIMARY KEY, value text);
CREATE ROLE alice;
-->

The examples use one schema with a table, and a role:

```sql
CREATE SCHEMA app;
CREATE TABLE app.setting (name text PRIMARY KEY, value text);
CREATE ROLE alice;
```

### A. Rename

<!-- example: postgresql -->
```sql
ALTER SCHEMA app RENAME TO config;
SELECT schemaname, tablename FROM pg_tables WHERE tablename = 'setting';
```

```text
ALTER SCHEMA
 schemaname | tablename
------------+-----------
 config     | setting
(1 row)
```

### B. A new owner

<!-- example: postgresql -->
```sql
ALTER SCHEMA config OWNER TO alice;
SELECT pg_get_userbyid(nspowner) FROM pg_namespace WHERE nspname = 'config';
```

```text
ALTER SCHEMA
 pg_get_userbyid
-----------------
 alice
(1 row)
```

### C. What is refused

<!-- example: postgresql -->
```sql
CREATE VIEW config.v AS SELECT name FROM config.setting;
ALTER SCHEMA config RENAME TO settings;
ALTER SCHEMA public RENAME TO main;
ALTER SCHEMA nosuch RENAME TO other;
```

```text
CREATE VIEW
ERROR:  cannot rename schema config because view config.v is in it or reads from it (lexdb keeps a view's text)
ERROR:  lexdb: schema public cannot be renamed
ERROR:  schema "nosuch" does not exist
```

## See also

[CREATE SCHEMA](create-schema.md) · [DROP SCHEMA](drop-schema.md)
