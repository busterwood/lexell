# Catalog functions

Functions that look up objects, show their definitions, check privileges and measure sizes. psql, drivers and
tools call them to describe a database.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
format_type ( type_oid, typemod ) → text
pg_get_userbyid ( role_oid ) → name
pg_encoding_to_char ( encoding ) → name
to_regclass ( text ) → regclass
to_regtype ( text ) → regtype
to_regnamespace ( text ) → regnamespace
pg_table_is_visible ( table_oid ) → boolean
pg_type_is_visible ( type_oid ) → boolean
pg_function_is_visible ( function_oid ) → boolean
pg_get_serial_sequence ( table, column ) → text
pg_get_expr ( expression, relation_oid [, pretty ] ) → text
pg_get_constraintdef ( constraint_oid [, pretty ] ) → text
pg_get_indexdef ( index_oid ) → text
pg_get_viewdef ( view [, pretty ] ) → text
pg_get_functiondef ( function_oid ) → text
pg_get_function_arguments ( function_oid ) → text
pg_get_function_result ( function_oid ) → text
obj_description ( oid [, catalog ] ) → text
col_description ( table_oid, column_number ) → text
has_table_privilege ( [ role, ] table, privilege ) → boolean
has_schema_privilege ( [ role, ] schema, privilege ) → boolean
has_database_privilege ( [ role, ] database, privilege ) → boolean
has_sequence_privilege ( [ role, ] sequence, privilege ) → boolean
has_function_privilege ( [ role, ] function, privilege ) → boolean
has_any_column_privilege ( [ role, ] table, privilege ) → boolean
pg_relation_size ( relation ) → bigint
pg_table_size ( relation ) → bigint
pg_indexes_size ( relation ) → bigint
pg_total_relation_size ( relation ) → bigint
pg_database_size ( name ) → bigint
pg_size_pretty ( bigint ) → text
```

## Functions

`format_type`
: A type's SQL name, with its modifier: `format_type(atttypid, atttypmod)` gives `character varying(20)`.

`pg_get_userbyid`
: A role's name from its oid.

`pg_encoding_to_char`
: An encoding's name from its number (`pg_database.encoding`): 6 is `UTF8`.

`to_regclass`, `to_regtype`, `to_regnamespace`
: Like the casts to `regclass`, `regtype` and `regnamespace`, but NULL for a name that does not exist.

`pg_table_is_visible`, `pg_type_is_visible`, `pg_function_is_visible`
: Whether the object is found by its bare name on the search path.

`pg_get_serial_sequence`
: The sequence of a `serial` or identity column, schema-qualified, or NULL.

`pg_get_expr`
: The text of an expression stored in the catalog: a default (`pg_attrdef.adbin`), a check, an index's predicate.

`pg_get_constraintdef`
: A constraint as it would be written in `CREATE TABLE` (`PRIMARY KEY (id)`, `CHECK (...)`, `FOREIGN KEY ...`).

`pg_get_indexdef`
: The `CREATE INDEX` statement of an index.

`pg_get_viewdef`
: A view's query, by name or oid.

`pg_get_functiondef`, `pg_get_function_arguments`, `pg_get_function_result`
: A function's `CREATE FUNCTION` statement, its argument list, and its result type.

`obj_description`, `col_description`
: The comment on an object or a column: always NULL, as lexdb has no `COMMENT ON`.

`has_table_privilege`, `has_schema_privilege`, `has_database_privilege`, `has_sequence_privilege`, `has_function_privilege`, `has_any_column_privilege`
: Whether the role (by default the current user) has the privilege (`SELECT`, `INSERT`, `UPDATE`, `DELETE`,
  `TRUNCATE`, `REFERENCES`, `USAGE`, `CREATE`, `CONNECT`, `TEMPORARY`, `EXECUTE`) on the object. Several may be
  given, parted by commas: true if any is held.

`pg_relation_size`, `pg_table_size`, `pg_indexes_size`, `pg_total_relation_size`, `pg_database_size`
: Sizes in bytes: a table's rows, the table, its indexes, the table with its indexes, the database.

`pg_size_pretty`
: A size in bytes as text in `bytes`, `kB`, `MB`, `GB` or `TB`, by powers of 1024.

## Remarks

- An oid argument may be given as a `regclass` cast: `pg_table_size('orders'::regclass)`, or as a name in text
  where the function takes one.
- See [system types](data-types-system.md) for `regclass` and the other `reg` types, and the catalog pages for the
  tables these functions read.

## Differences from PostgreSQL

- `pg_get_viewdef` gives the view's text as it was written, with its `;`, not PostgreSQL's rewritten query.
- `obj_description` and `col_description` are always NULL; `COMMENT ON` is a syntax error.
- `has_column_privilege`, `pg_has_role`, `pg_column_size`, `pg_relation_filepath`, `pg_get_keywords` and
  `to_regproc` do not exist (42883).
- Sizes count lexdb's own storage, not PostgreSQL's 8 kB pages.

## Examples

<!--setup: postgresql
CREATE TABLE orders (id serial PRIMARY KEY, customer varchar(20) NOT NULL, total numeric(10,2) DEFAULT 0 CHECK (total >= 0));
CREATE INDEX orders_customer ON orders (customer) WHERE total > 0;
CREATE VIEW big_orders AS SELECT id, total FROM orders WHERE total > 100;
CREATE FUNCTION tax(p numeric) RETURNS numeric LANGUAGE sql AS 'SELECT p * 0.2';
CREATE ROLE clerk;
GRANT SELECT ON orders TO clerk;
INSERT INTO orders (customer, total) SELECT 'c' || g, g FROM generate_series(1, 500) g;
-->

The examples use these objects:

```sql
CREATE TABLE orders (id serial PRIMARY KEY, customer varchar(20) NOT NULL, total numeric(10,2) DEFAULT 0
  CHECK (total >= 0));
CREATE INDEX orders_customer ON orders (customer) WHERE total > 0;
CREATE VIEW big_orders AS SELECT id, total FROM orders WHERE total > 100;
CREATE FUNCTION tax(p numeric) RETURNS numeric LANGUAGE sql AS 'SELECT p * 0.2';
CREATE ROLE clerk;
GRANT SELECT ON orders TO clerk;
INSERT INTO orders (customer, total) SELECT 'c' || g, g FROM generate_series(1, 500) g;
```

### A. format_type, pg_get_userbyid and pg_encoding_to_char

<!-- example: postgresql -->
```sql
SELECT attname, format_type(atttypid, atttypmod) AS type FROM pg_attribute
WHERE attrelid = 'orders'::regclass AND attnum > 0 ORDER BY attnum;
SELECT pg_get_userbyid(relowner) AS owner FROM pg_class WHERE relname = 'orders';
SELECT datname, pg_encoding_to_char(encoding) AS encoding FROM pg_database WHERE datname = current_database();
```

```text
 attname  |         type
----------+-----------------------
 id       | integer
 customer | character varying(20)
 total    | numeric(10,2)
(3 rows)

  owner
----------
 postgres
(1 row)

 datname | encoding
---------+----------
 lexdb   | UTF8
(1 row)
```

### B. to_regclass and its kin

<!-- example: postgresql -->
```sql
SELECT to_regclass('orders') AS a, to_regclass('nosuch') AS b, to_regtype('int4') AS c, to_regtype('nosuch') AS d,
       to_regnamespace('public') AS e, to_regnamespace('nosuch') AS f;
```

```text
   a    | b |    c    | d |   e    | f
--------+---+---------+---+--------+---
 orders |   | integer |   | public |
(1 row)
```

### C. Visible on the search path

<!-- example: postgresql -->
```sql
CREATE SCHEMA hidden;
CREATE TABLE hidden.t (a int);
SELECT relname, pg_table_is_visible(oid) AS visible FROM pg_class WHERE relname IN ('orders', 't') ORDER BY relname;
SELECT pg_type_is_visible('int4'::regtype) AS type_visible, pg_function_is_visible('tax'::regproc) AS func_visible;
```

```text
CREATE SCHEMA
CREATE TABLE
 relname | visible
---------+---------
 orders  | t
 t       | f
(2 rows)

 type_visible | func_visible
--------------+--------------
 t            | t
(1 row)
```

### D. Defaults, constraints and serial sequences

<!-- example: postgresql -->
```sql
SELECT a.attname, pg_get_expr(d.adbin, d.adrelid) AS default
FROM pg_attrdef d JOIN pg_attribute a ON a.attrelid = d.adrelid AND a.attnum = d.adnum
WHERE d.adrelid = 'orders'::regclass ORDER BY a.attnum;
SELECT conname, pg_get_constraintdef(oid) AS definition FROM pg_constraint
WHERE conrelid = 'orders'::regclass ORDER BY conname;
SELECT pg_get_serial_sequence('orders', 'id') AS seq;
```

```text
 attname |              default
---------+------------------------------------
 id      | nextval('orders_id_seq'::regclass)
 total   | 0
(2 rows)

      conname       |      definition
--------------------+----------------------
 orders_pkey        | PRIMARY KEY (id)
 orders_total_check | CHECK ((total >= 0))
(2 rows)

         seq
----------------------
 public.orders_id_seq
(1 row)
```

### E. Index, view and function definitions

<!-- example: postgresql -->
```sql
SELECT pg_get_indexdef('orders_customer'::regclass) AS index;
SELECT pg_get_viewdef('big_orders') AS view;
SELECT pg_get_function_arguments('tax'::regproc) AS args, pg_get_function_result('tax'::regproc) AS result;
SELECT pg_get_functiondef('tax'::regproc) AS def;
```

```text
                                         index
----------------------------------------------------------------------------------------
 CREATE INDEX orders_customer ON public.orders USING btree (customer) WHERE (total > 0)
(1 row)

                      view
-------------------------------------------------
 SELECT id, total FROM orders WHERE total > 100;
(1 row)

   args    | result
-----------+---------
 p numeric | numeric
(1 row)

                       def
--------------------------------------------------
 CREATE OR REPLACE FUNCTION public.tax(p numeric)+
  RETURNS numeric                                +
  LANGUAGE sql                                   +
 AS $function$SELECT p * 0.2$function$           +

(1 row)
```

### F. Comments

<!-- example: postgresql -->
```sql
SELECT obj_description('orders'::regclass, 'pg_class') AS table_comment, col_description('orders'::regclass, 1) AS col;
```

```text
 table_comment | col
---------------+-----
               |
(1 row)
```

### G. Privileges

<!-- example: postgresql -->
```sql
SELECT has_table_privilege('clerk', 'orders', 'SELECT') AS sel, has_table_privilege('clerk', 'orders', 'INSERT') AS ins,
       has_table_privilege('clerk', 'orders', 'INSERT, SELECT') AS either, has_table_privilege('orders', 'DELETE') AS me;
SELECT has_schema_privilege('clerk', 'public', 'USAGE') AS schema_usage,
       has_database_privilege('clerk', current_database(), 'CONNECT') AS db_connect,
       has_sequence_privilege('clerk', 'orders_id_seq', 'USAGE') AS seq_usage,
       has_function_privilege('clerk', 'tax(numeric)', 'EXECUTE') AS func_exec,
       has_any_column_privilege('clerk', 'orders', 'SELECT') AS any_col;
```

```text
 sel | ins | either | me
-----+-----+--------+----
 t   | f   | t      | t
(1 row)

 schema_usage | db_connect | seq_usage | func_exec | any_col
--------------+------------+-----------+-----------+---------
 t            | t          | f         | t         | t
(1 row)
```

### H. Sizes

Sizes depend on the storage, so the example compares them.

<!-- example: postgresql -->
```sql
SELECT pg_relation_size('orders') > 0 AS rel, pg_table_size('orders') >= pg_relation_size('orders') AS tbl,
       pg_indexes_size('orders') > 0 AS idx,
       pg_total_relation_size('orders') = pg_table_size('orders') + pg_indexes_size('orders') AS total,
       pg_database_size(current_database()) >= pg_total_relation_size('orders') AS db;
SELECT pg_size_pretty(512::bigint) AS a, pg_size_pretty(20480::bigint) AS b, pg_size_pretty(5368709120) AS c;
```

```text
 rel | tbl | idx | total | db
-----+-----+-----+-------+----
 t   | t   | t   | t     | t
(1 row)

     a     |   b   |    c
-----------+-------+---------
 512 bytes | 20 kB | 5120 MB
(1 row)
```

### I. Errors

<!-- example: postgresql -->
```sql
SELECT pg_table_size('nosuch');
SELECT has_table_privilege('nobody', 'orders', 'SELECT');
SELECT has_column_privilege('orders', 'id', 'SELECT');
```

```text
ERROR:  relation "nosuch" does not exist
ERROR:  role "nobody" does not exist
ERROR:  function has_column_privilege with 3 arguments does not exist
```

## See also

[System types](data-types-system.md) · [Catalog: tables and columns](catalog-tables.md) · [GRANT](grant.md) ·
[Session information functions](functions-session.md)
