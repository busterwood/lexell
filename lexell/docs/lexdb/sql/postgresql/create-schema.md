# CREATE SCHEMA

Makes a schema: a namespace for tables, views, indexes, sequences, types and functions.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CREATE SCHEMA [ IF NOT EXISTS ] schema_name [ AUTHORIZATION role_specification ]
CREATE SCHEMA [ IF NOT EXISTS ] AUTHORIZATION role_specification

role_specification:
    role_name | CURRENT_USER | SESSION_USER
```

## Arguments

`IF NOT EXISTS`
: If the schema exists, does nothing and gives a notice.

*schema_name*
: The new schema's name. Names beginning with `pg_` are refused (42939).

`AUTHORIZATION` *role*
: The role that owns the schema. Without a name, the schema is named after the role.

## Remarks

- An object's name without a schema is looked up in the schemas of `search_path` (`public` by default),
  and a new one goes in the first schema of `search_path` that exists. `SET search_path = app, public` puts `app`
  first.
- `pg_namespace` and `information_schema.schemata` list the schemas.
- `CREATE SCHEMA` is transactional.

## Differences from PostgreSQL

- `search_path` is `public` by default; PostgreSQL's default is `"$user", public`.
- The schema elements (`CREATE SCHEMA app CREATE TABLE t (...) ...`) are a syntax error: make the objects with their
  own statements.

## Examples

### A. A schema and a table in it

<!-- example: postgresql -->
```sql
CREATE SCHEMA app;
CREATE TABLE app.setting (name text PRIMARY KEY, value text);
INSERT INTO app.setting VALUES ('mode', 'test');
SELECT * FROM app.setting;
```

```text
CREATE SCHEMA
CREATE TABLE
INSERT 0 1
 name | value
------+-------
 mode | test
(1 row)
```

### B. search_path

<!-- example: postgresql -->
```sql
SHOW search_path;
SET search_path = app, public;
SELECT current_schema();
CREATE TABLE note (body text);
SELECT schemaname, tablename FROM pg_tables WHERE tablename = 'note';
RESET search_path;
```

```text
 search_path
-------------
 public
(1 row)

SET
 current_schema
----------------
 app
(1 row)

CREATE TABLE
 schemaname | tablename
------------+-----------
 app        | note
(1 row)

RESET
```

### C. AUTHORIZATION

<!-- example: postgresql -->
```sql
CREATE ROLE alice;
CREATE SCHEMA AUTHORIZATION alice;
CREATE SCHEMA reports AUTHORIZATION alice;
SELECT nspname, pg_get_userbyid(nspowner) AS owner FROM pg_namespace WHERE nspname IN ('alice', 'reports') ORDER BY 1;
```

```text
CREATE ROLE
CREATE SCHEMA
CREATE SCHEMA
 nspname | owner
---------+-------
 alice   | alice
 reports | alice
(2 rows)
```

### D. Errors

<!-- example: postgresql -->
```sql
CREATE SCHEMA app;
CREATE SCHEMA IF NOT EXISTS app;
CREATE SCHEMA pg_mine;
CREATE SCHEMA tools CREATE TABLE t (x int);
```

```text
ERROR:  schema "app" already exists
NOTICE:  schema "app" already exists, skipping
CREATE SCHEMA
ERROR:  unacceptable schema name "pg_mine"
ERROR:  syntax error at or near "create"
```

## See also

[ALTER SCHEMA](alter-schema.md) · [DROP SCHEMA](drop-schema.md) · [CREATE TABLE](create-table.md) · SET
