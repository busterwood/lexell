# DROP SCHEMA

Removes a schema.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
DROP SCHEMA [ IF EXISTS ] name [ CASCADE | RESTRICT ]
```

## Arguments

`IF EXISTS`
: If the schema does not exist, does nothing and gives a notice.

*name*
: The schema.

`CASCADE`
: Also drops every object in it: tables, views, indexes, sequences, types and functions.

`RESTRICT`
: Refuses to drop a schema that holds objects (2BP01). This is the default.

## Remarks

- `DROP SCHEMA` is transactional.

## Differences from PostgreSQL

- One schema per statement: `DROP SCHEMA a, b` is a syntax error.
- The `public` schema cannot be dropped (0A000). PostgreSQL drops it.
- `DROP SCHEMA pg_catalog` says the schema does not exist (3F000).
- The refusal has no `DETAIL` naming the objects, and `CASCADE` gives no `NOTICE`.

## Examples

<!--setup: postgresql
CREATE SCHEMA app;
CREATE TABLE app.setting (name text PRIMARY KEY, value text);
CREATE VIEW app.modes AS SELECT value FROM app.setting;
CREATE SCHEMA empty;
-->

The examples use two schemas:

```sql
CREATE SCHEMA app;
CREATE TABLE app.setting (name text PRIMARY KEY, value text);
CREATE VIEW app.modes AS SELECT value FROM app.setting;
CREATE SCHEMA empty;
```

### A. An empty schema

<!-- example: postgresql -->
```sql
DROP SCHEMA empty;
DROP SCHEMA IF EXISTS empty;
```

```text
DROP SCHEMA
NOTICE:  schema "empty" does not exist, skipping
DROP SCHEMA
```

### B. A schema with objects

<!-- example: postgresql -->
```sql
DROP SCHEMA app;
BEGIN;
DROP SCHEMA app CASCADE;
SELECT count(*) FROM pg_tables WHERE schemaname = 'app';
ROLLBACK;
SELECT count(*) FROM pg_tables WHERE schemaname = 'app';
```

```text
ERROR:  cannot drop schema app because other objects depend on it
BEGIN
DROP SCHEMA
 count
-------
     0
(1 row)

ROLLBACK
 count
-------
     1
(1 row)
```

### C. Errors

<!-- example: postgresql -->
```sql
DROP SCHEMA nosuch;
DROP SCHEMA public;
DROP SCHEMA app, empty;
```

```text
ERROR:  schema "nosuch" does not exist
ERROR:  lexdb: schema public cannot be dropped
ERROR:  syntax error at or near ","
```

## See also

[CREATE SCHEMA](create-schema.md) · [ALTER SCHEMA](alter-schema.md) · [DROP TABLE](drop-table.md)
