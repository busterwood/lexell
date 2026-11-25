# Catalog: schemas, the database and tablespaces

`pg_namespace`, `pg_database`, `pg_tablespace` and `information_schema.schemata`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SELECT ... FROM [ pg_catalog. ] pg_namespace
SELECT ... FROM [ pg_catalog. ] pg_database
SELECT ... FROM [ pg_catalog. ] pg_tablespace
SELECT ... FROM information_schema.schemata
```

## Views

Each relation has all of PostgreSQL 18's columns. The columns below are the ones lexdb fills in; the others are
NULL, zero, false or empty.

`pg_namespace`: one row per schema
: `oid`, `nspname`, `nspowner` (the owner's oid), `nspacl` (the privileges, as `aclitem` text). The rows are
  `pg_catalog`, `information_schema`, `public`, the user's schemas and the sessions' temporary schemas
  (`pg_temp_n`).

`pg_database`: one row, the database
: `oid`, `datname` (`lexdb`), `datdba` (10, the bootstrap role `postgres`), `encoding` (6, UTF8),
  `datlocprovider` (`c`), `datistemplate` (false), `datallowconn` (true), `datconnlimit` (-1), `dattablespace`,
  `datcollate` and `datctype` (`C`).

`pg_tablespace`: two rows
: `pg_default` (1663) and `pg_global` (1664), with `oid`, `spcname` and `spcowner`. lexdb has no tablespaces of its
  own.

`information_schema.schemata`: one row per schema
: `catalog_name` (`lexdb`), `schema_name`, `schema_owner` (the schema's owner: its `AUTHORIZATION` role, as `pg_namespace.nspowner`).

## Remarks

- `pg_catalog` relations may be named with or without `pg_catalog.`; `information_schema` relations must be
  qualified.
- psql's `\dn` and `\l` read these relations.

## Differences from PostgreSQL

- There is one database; `CREATE DATABASE` is refused.

## Examples

### A. Schemas and their owners

<!-- example: postgresql -->
```sql
CREATE ROLE alice;
CREATE SCHEMA app AUTHORIZATION alice;
SELECT nspname, pg_get_userbyid(nspowner) AS owner FROM pg_namespace
WHERE nspname NOT LIKE 'pg_temp%' ORDER BY nspname;
SELECT schema_name, schema_owner FROM information_schema.schemata ORDER BY schema_name;
```

```text
CREATE ROLE
CREATE SCHEMA
      nspname       |  owner
--------------------+----------
 app                | alice
 information_schema | postgres
 pg_catalog         | postgres
 public             | postgres
(4 rows)

    schema_name     | schema_owner
--------------------+--------------
 app                | alice
 information_schema | postgres
 pg_catalog         | postgres
 public             | postgres
(4 rows)
```

### B. Schema privileges

<!-- example: postgresql -->
```sql
CREATE ROLE bob;
GRANT USAGE ON SCHEMA app TO bob;
SELECT nspname, nspacl FROM pg_namespace WHERE nspname IN ('public', 'app') ORDER BY nspname;
```

```text
CREATE ROLE
GRANT
 nspname |               nspacl
---------+------------------------------------
 app     | {alice=UC/alice,bob=U/alice}
 public  | {postgres=UC/postgres,=U/postgres}
(2 rows)
```

### C. The database

<!-- example: postgresql -->
```sql
SELECT datname, pg_get_userbyid(datdba) AS owner, pg_encoding_to_char(encoding) AS encoding, datcollate,
       datallowconn, datconnlimit FROM pg_database;
SELECT spcname FROM pg_tablespace ORDER BY oid;
```

```text
 datname |  owner   | encoding | datcollate | datallowconn | datconnlimit
---------+----------+----------+------------+--------------+--------------
 lexdb   | postgres | UTF8     | C          | t            |           -1
(1 row)

  spcname
------------
 pg_default
 pg_global
(2 rows)
```

### D. psql's list of schemas

<!-- example: postgresql -->
```sql
\dn
```

```text
  List of schemas
  Name  |  Owner
--------+----------
 app    | alice
 public | postgres
(2 rows)
```

## See also

[CREATE SCHEMA](create-schema.md) · [Catalog: tables and columns](catalog-tables.md) ·
[Catalog: roles and privileges](catalog-roles.md)
