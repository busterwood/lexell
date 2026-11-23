# Catalog: tables and columns

`pg_class`, `pg_attribute`, `pg_attrdef`, `pg_tables`, `information_schema.tables` and
`information_schema.columns`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SELECT ... FROM [ pg_catalog. ] pg_class
SELECT ... FROM [ pg_catalog. ] pg_attribute
SELECT ... FROM [ pg_catalog. ] pg_attrdef
SELECT ... FROM [ pg_catalog. ] pg_tables
SELECT ... FROM information_schema.tables
SELECT ... FROM information_schema.columns
```

## Views

Each relation has all of PostgreSQL 18's columns. The columns below are the ones lexdb fills in; the others are
NULL, zero, false or empty.

`pg_class`: one row per table, index, sequence and view, the catalog's own included
: `oid`, `relname`, `relnamespace`, `relowner`, `relam` (2 heap for a table, 403 btree for an index),
  `relfilenode`, `relkind` (`r` table, `i` index, `S` sequence, `v` view), `relpersistence` (`p`, or `t` for a
  temporary table), `relnatts`, `relchecks`, `relhasindex`, `relhasrules` (true for a view), `relhastriggers`
  (true for a table with foreign keys), `relreplident`, `relispopulated`, `relacl`. `reltuples` is -1 for a table.

`pg_attribute`: one row per column
: `attrelid`, `attname`, `atttypid`, `attlen`, `attnum` (from 1), `atttypmod` (the length or precision, as in
  PostgreSQL), `attndims`, `attbyval`, `attalign`, `attstorage`, `attnotnull`, `atthasdef`, `attidentity` (`a`
  always, `d` by default), `attgenerated` (`s` stored, `v` virtual), `attisdropped`, `attislocal`,
  `attcollation`.

`pg_attrdef`: one row per column default
: `oid`, `adrelid`, `adnum`, `adbin` (the default's text; read it with `pg_get_expr`).

`pg_tables`: one row per table
: `schemaname`, `tablename`, `tableowner`, `hasindexes`, `hasrules`, `hastriggers`, `rowsecurity`.

`information_schema.tables`: one row per table and view
: `table_catalog`, `table_schema`, `table_name`, `table_type` (`BASE TABLE`, `VIEW`, `LOCAL TEMPORARY`),
  `is_insertable_into`, `is_typed`.

`information_schema.columns`: one row per column of a table or view
: `table_catalog`, `table_schema`, `table_name`, `column_name`, `ordinal_position`, `column_default`,
  `is_nullable`, `data_type`, `character_maximum_length`, `character_octet_length`, `numeric_precision`,
  `numeric_precision_radix`, `numeric_scale`, `datetime_precision`, `udt_catalog`, `udt_schema`, `udt_name`,
  `dtd_identifier`, `is_self_referencing`, `is_identity`, `identity_generation`, `identity_start`,
  `identity_increment`, `identity_maximum`, `identity_minimum`, `identity_cycle`, `is_generated`,
  `generation_expression`, `is_updatable`.

## Remarks

- Join `pg_class` to `pg_attribute` on `attrelid = pg_class.oid`, or name the table with a `regclass` cast:
  `WHERE attrelid = 'orders'::regclass`.
- `format_type(atttypid, atttypmod)` gives a column's type as SQL writes it.
- The oids of the user's objects come from their names: they do not change from run to run, but they are not
  PostgreSQL's.
- psql's `\d`, `\dt` and `\d table` read these relations.

## Differences from PostgreSQL

- `pg_class.reltuples` stays -1 after `ANALYZE` (`pg_stat_user_tables.n_live_tup` has the count), and `relpages` is
  0.
- `pg_attrdef.adbin` is the default's text, not a node tree; `pg_get_expr` reads it either way.
- `reltype` is 0: tables have no row type.
- `pg_attribute` has no rows for the system columns (`ctid`, `xmin` ...), which lexdb does not have.

## Examples

<!--setup: postgresql
CREATE TABLE customer (id int PRIMARY KEY, email varchar(40) NOT NULL, born date, score numeric(6,2) DEFAULT 0);
CREATE TABLE orders (no bigserial PRIMARY KEY, cust int REFERENCES customer (id), made timestamptz(3),
  code int GENERATED ALWAYS AS IDENTITY);
CREATE VIEW recent AS SELECT no, made FROM orders;
-->

The examples use these tables:

```sql
CREATE TABLE customer (id int PRIMARY KEY, email varchar(40) NOT NULL, born date, score numeric(6,2) DEFAULT 0);
CREATE TABLE orders (no bigserial PRIMARY KEY, cust int REFERENCES customer (id), made timestamptz(3),
  code int GENERATED ALWAYS AS IDENTITY);
CREATE VIEW recent AS SELECT no, made FROM orders;
```

### A. The relations of a schema

<!-- example: postgresql -->
```sql
SELECT relname, relkind, relnatts, relhasindex, pg_get_userbyid(relowner) AS owner FROM pg_class
WHERE relnamespace = 'public'::regnamespace ORDER BY relkind, relname;
```

```text
     relname     | relkind | relnatts | relhasindex |  owner
-----------------+---------+----------+-------------+----------
 orders_code_seq | S       |        3 | f           | postgres
 orders_no_seq   | S       |        3 | f           | postgres
 customer_pkey   | i       |        1 | f           | postgres
 orders_pkey     | i       |        1 | f           | postgres
 customer        | r       |        4 | t           | postgres
 orders          | r       |        4 | t           | postgres
 recent          | v       |        2 | f           | postgres
(7 rows)
```

### B. The columns of a table

<!-- example: postgresql -->
```sql
SELECT attnum, attname, format_type(atttypid, atttypmod) AS type, attnotnull, atthasdef, attidentity
FROM pg_attribute WHERE attrelid = 'orders'::regclass AND attnum > 0 ORDER BY attnum;
```

```text
 attnum | attname |            type             | attnotnull | atthasdef | attidentity
--------+---------+-----------------------------+------------+-----------+-------------
      1 | no      | bigint                      | t          | t         |
      2 | cust    | integer                     | f          | f         |
      3 | made    | timestamp(3) with time zone | f          | f         |
      4 | code    | integer                     | t          | f         | a
(4 rows)
```

### C. Column defaults

<!-- example: postgresql -->
```sql
SELECT c.relname, a.attname, pg_get_expr(d.adbin, d.adrelid) AS default
FROM pg_attrdef d JOIN pg_class c ON c.oid = d.adrelid
JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
ORDER BY c.relname, a.attnum;
```

```text
 relname  | attname |              default
----------+---------+------------------------------------
 customer | score   | 0
 orders   | no      | nextval('orders_no_seq'::regclass)
(2 rows)
```

### D. pg_tables and information_schema.tables

<!-- example: postgresql -->
```sql
SELECT tablename, tableowner, hasindexes, hastriggers FROM pg_tables WHERE schemaname = 'public' ORDER BY tablename;
SELECT table_name, table_type, is_insertable_into FROM information_schema.tables
WHERE table_schema = 'public' ORDER BY table_name;
```

```text
 tablename | tableowner | hasindexes | hastriggers
-----------+------------+------------+-------------
 customer  | postgres   | t          | t
 orders    | postgres   | t          | t
(2 rows)

 table_name | table_type | is_insertable_into
------------+------------+--------------------
 customer   | BASE TABLE | YES
 orders     | BASE TABLE | YES
 recent     | VIEW       | NO
(3 rows)
```

### E. information_schema.columns

<!-- example: postgresql -->
```sql
SELECT column_name, data_type, character_maximum_length AS len, numeric_precision AS prec, numeric_scale AS scale,
       datetime_precision AS dt_prec, is_nullable, column_default, is_identity
FROM information_schema.columns WHERE table_name IN ('customer', 'orders')
ORDER BY table_name, ordinal_position;
```

```text
 column_name |        data_type         | len | prec | scale | dt_prec | is_nullable |           column_default           | is_identity
-------------+--------------------------+-----+------+-------+---------+-------------+------------------------------------+-------------
 id          | integer                  |     |   32 |     0 |         | NO          |                                    | NO
 email       | character varying        |  40 |      |       |         | NO          |                                    | NO
 born        | date                     |     |      |       |       0 | YES         |                                    | NO
 score       | numeric                  |     |    6 |     2 |         | YES         | 0                                  | NO
 no          | bigint                   |     |   64 |     0 |         | NO          | nextval('orders_no_seq'::regclass) | NO
 cust        | integer                  |     |   32 |     0 |         | YES         |                                    | NO
 made        | timestamp with time zone |     |      |       |       3 | YES         |                                    | NO
 code        | integer                  |     |   32 |     0 |         | NO          |                                    | YES
(8 rows)
```

### F. Temporary tables and generated columns

<!-- example: postgresql -->
```sql
CREATE TEMP TABLE scratch (x int);
SELECT relname, relpersistence, relnamespace::regnamespace::text LIKE 'pg_temp%' AS temp_schema FROM pg_class
WHERE relname = 'scratch';
SELECT table_type FROM information_schema.tables WHERE table_name = 'scratch';
CREATE TABLE calc (a int, b int GENERATED ALWAYS AS (a * 2) STORED, c int GENERATED ALWAYS AS (a * 3) VIRTUAL);
SELECT attname, attgenerated FROM pg_attribute WHERE attrelid = 'calc'::regclass AND attnum > 0 ORDER BY attnum;
SELECT column_name, is_generated, generation_expression FROM information_schema.columns
WHERE table_name = 'calc' ORDER BY ordinal_position;
```

```text
CREATE TABLE
 relname | relpersistence | temp_schema
---------+----------------+-------------
 scratch | t              | t
(1 row)

   table_type
-----------------
 LOCAL TEMPORARY
(1 row)

CREATE TABLE
 attname | attgenerated
---------+--------------
 a       |
 b       | s
 c       | v
(3 rows)

 column_name | is_generated | generation_expression
-------------+--------------+-----------------------
 a           | NEVER        |
 b           | ALWAYS       | (a * 2)
 c           | ALWAYS       | (a * 3)
(3 rows)
```

### G. psql's description of a table

<!-- example: postgresql -->
```sql
\d customer
```

```text
                     Table "public.customer"
 Column |         Type          | Collation | Nullable | Default
--------+-----------------------+-----------+----------+---------
 id     | integer               |           | not null |
 email  | character varying(40) |           | not null |
 born   | date                  |           |          |
 score  | numeric(6,2)          |           |          | 0
Indexes:
    "customer_pkey" PRIMARY KEY, btree (id)
Referenced by:
    TABLE "orders" CONSTRAINT "orders_cust_fkey" FOREIGN KEY (cust) REFERENCES customer(id)
```

## See also

[Catalog: constraints and indexes](catalog-constraints.md) · [Catalog functions](functions-catalog.md) ·
[System types](data-types-system.md) · [CREATE TABLE](create-table.md)
