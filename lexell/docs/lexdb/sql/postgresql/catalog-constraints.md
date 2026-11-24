# Catalog: constraints and indexes

`pg_constraint`, `pg_index`, `pg_indexes`, and the constraint views of `information_schema`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SELECT ... FROM [ pg_catalog. ] pg_constraint
SELECT ... FROM [ pg_catalog. ] pg_index
SELECT ... FROM [ pg_catalog. ] pg_indexes
SELECT ... FROM information_schema.table_constraints
SELECT ... FROM information_schema.key_column_usage
SELECT ... FROM information_schema.referential_constraints
SELECT ... FROM information_schema.constraint_column_usage
SELECT ... FROM information_schema.check_constraints
```

## Views

Each relation has all of PostgreSQL 18's columns. The columns below are the ones lexdb fills in; the others are
NULL, zero, false or empty.

`pg_constraint`: one row per primary key, unique, foreign key, check and `NOT NULL` constraint
: `oid`, `conname`, `connamespace`, `contype` (`p`, `u`, `f`, `c`, `n`), `condeferrable`, `condeferred`,
  `conenforced`, `convalidated`, `conrelid`, `conindid` (the index of a key, or the referenced key's index for a foreign key),
  `confrelid`, `confupdtype` and `confdeltype` (`a` no action, `r` restrict, `c` cascade, `n` set null, `d` set
  default), `confmatchtype` (`s`), `conislocal`, `conkey`, `confkey`, `conbin` (a check's text; read it with
  `pg_get_constraintdef`). `conenforced` is false for a `CHECK` or foreign key made or altered `NOT ENFORCED`, and
  `convalidated` is then false too. `convalidated` is also false for a constraint added `NOT VALID`, which is still
  enforced for new rows. A `NOT NULL` constraint (`n`) has the name it was given, else `table_column_not_null`
  (`orders_no_not_null`), a number after it where the table has a constraint of that name already
  (`t_a_not_null1`), and `conkey` of its one column. `pg_get_constraintdef` gives `NOT NULL column`.

`pg_index`: one row per index
: `indexrelid`, `indrelid`, `indnatts`, `indnkeyatts`, `indisunique`, `indisprimary`, `indimmediate`,
  `indisvalid`, `indisready`, `indislive`, `indkey` (column numbers; 0 for an expression), `indexprs`, `indpred`.

`pg_indexes`: one row per index
: `schemaname`, `tablename`, `indexname`, `indexdef` (the `CREATE INDEX` statement).

`information_schema.table_constraints`
: `constraint_catalog`, `constraint_schema`, `constraint_name`, `table_catalog`, `table_schema`, `table_name`,
  `constraint_type` (`PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY`, `CHECK`; a `NOT NULL` constraint is a `CHECK` row), `is_deferrable`, `initially_deferred`,
  `enforced` (`NO` for a constraint that is not enforced), `nulls_distinct`.

`information_schema.key_column_usage`
: The columns of keys and foreign keys: the constraint and table names, `column_name`, `ordinal_position`,
  `position_in_unique_constraint` (for a foreign key).

`information_schema.referential_constraints`
: One row per foreign key: its name, the `unique_constraint_name` it references, `match_option` (`NONE`),
  `update_rule`, `delete_rule`.

`information_schema.constraint_column_usage`
: The columns each constraint uses (a `NOT NULL` constraint's column too); for a foreign key, the referenced
  columns. `key_column_usage` has no row for a `NOT NULL` constraint.

`information_schema.check_constraints`
: `constraint_catalog`, `constraint_schema`, `constraint_name`, `check_clause`. A `NOT NULL` constraint's clause is
  `column IS NOT NULL`.

## Remarks

- psql's `\d table` lists a table's indexes, checks and foreign keys from these relations.
- `DROP CONSTRAINT` and `RENAME CONSTRAINT` of a `NOT NULL` constraint work on its row (see [ALTER
  TABLE](alter-table.md), example J). A `NOT NULL` constraint's name is fixed when it is made: a rename of the
  column or the table leaves it.
- `pg_get_constraintdef` and `pg_get_indexdef` give a constraint's or an index's definition as SQL (see [catalog
  functions](functions-catalog.md)). The definition of a constraint that is not enforced ends in `NOT ENFORCED`, and
  that of one added `NOT VALID` in `NOT VALID` (example G).
- `information_schema.check_constraints` lists a `CHECK` that is not enforced like any other; its `check_clause` has
  no `NOT ENFORCED`. Read `pg_constraint` or `table_constraints` for the state.

## Differences from PostgreSQL

- psql's `\d+` shows no "Not-null constraints" section (PostgreSQL 18 lists them there); its query joins on
  `conkey[1]`, which finds nothing in lexdb. `\d` is as PostgreSQL's (example F). `pg_attribute.attnotnull` and
  `information_schema.columns.is_nullable` show the columns as before.
- On a table without a primary key, a column added later gets an `attnum`, and a `conkey` in `pg_constraint`, one
  higher than PostgreSQL's.
- `pg_indexes.indexdef` shows an expression index on `(n + 1)` as `(((n + 1)))`.
- `DROP INDEX` of a key's index (`t_pkey`) says it does not exist, though `pg_indexes` lists it.
- `indcollation`, `indclass` and `indoption` are 0, and `pg_opclass` is empty.
- `0::regclass` shows `0` (PostgreSQL: `-`), as in `confrelid::regclass` of a constraint that is not a foreign key.

## Examples

<!--setup: postgresql
CREATE TABLE customer (id int PRIMARY KEY, email text UNIQUE, score int CHECK (score >= 0));
CREATE TABLE orders (no int PRIMARY KEY, cust int REFERENCES customer (id) ON DELETE CASCADE, total numeric(10,2));
CREATE INDEX orders_cust ON orders (cust) WHERE total > 0;
CREATE INDEX orders_lower ON orders ((total * 2));
-->

The examples use these tables:

```sql
CREATE TABLE customer (id int PRIMARY KEY, email text UNIQUE, score int CHECK (score >= 0));
CREATE TABLE orders (no int PRIMARY KEY, cust int REFERENCES customer (id) ON DELETE CASCADE, total numeric(10,2));
CREATE INDEX orders_cust ON orders (cust) WHERE total > 0;
CREATE INDEX orders_lower ON orders ((total * 2));
```

### A. pg_constraint

<!-- example: postgresql -->
```sql
SELECT conrelid::regclass AS "table", conname, contype, conkey, confrelid::regclass AS refs, confdeltype,
       pg_get_constraintdef(oid) AS definition
FROM pg_constraint WHERE connamespace = 'public'::regnamespace ORDER BY 1, 2;
```

```text
  table   |       conname        | contype | conkey |   refs   | confdeltype |                          definition
----------+----------------------+---------+--------+----------+-------------+--------------------------------------------------------------
 orders   | orders_cust_fkey     | f       | {2}    | customer | c           | FOREIGN KEY (cust) REFERENCES customer(id) ON DELETE CASCADE
 orders   | orders_no_not_null   | n       | {1}    | 0        |             | NOT NULL no
 orders   | orders_pkey          | p       | {1}    | 0        |             | PRIMARY KEY (no)
 customer | customer_email_key   | u       | {2}    | 0        |             | UNIQUE (email)
 customer | customer_id_not_null | n       | {1}    | 0        |             | NOT NULL id
 customer | customer_pkey        | p       | {1}    | 0        |             | PRIMARY KEY (id)
 customer | customer_score_check | c       | {3}    | 0        |             | CHECK ((score >= 0))
(7 rows)
```

### B. pg_index and pg_indexes

<!-- example: postgresql -->
```sql
SELECT indexrelid::regclass AS index, indisunique, indisprimary, indkey, pg_get_expr(indpred, indrelid) AS predicate
FROM pg_index WHERE indrelid = 'orders'::regclass ORDER BY 1;
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'orders' ORDER BY indexname;
```

```text
    index     | indisunique | indisprimary | indkey |  predicate
--------------+-------------+--------------+--------+-------------
 orders_lower | f           | f            | 0      |
 orders_pkey  | t           | t            | 1      |
 orders_cust  | f           | f            | 2      | (total > 0)
(3 rows)

  indexname   |                                    indexdef
--------------+--------------------------------------------------------------------------------
 orders_cust  | CREATE INDEX orders_cust ON public.orders USING btree (cust) WHERE (total > 0)
 orders_lower | CREATE INDEX orders_lower ON public.orders USING btree (((total * 2)))
 orders_pkey  | CREATE UNIQUE INDEX orders_pkey ON public.orders USING btree (no)
(3 rows)
```

### C. table_constraints and key_column_usage

<!-- example: postgresql -->
```sql
SELECT tc.table_name, tc.constraint_name, tc.constraint_type, kcu.column_name
FROM information_schema.table_constraints tc
LEFT JOIN information_schema.key_column_usage kcu
  ON kcu.constraint_name = tc.constraint_name AND kcu.table_name = tc.table_name
WHERE tc.table_schema = 'public' ORDER BY 1, 2;
```

```text
 table_name |   constraint_name    | constraint_type | column_name
------------+----------------------+-----------------+-------------
 customer   | customer_email_key   | UNIQUE          | email
 customer   | customer_id_not_null | CHECK           |
 customer   | customer_pkey        | PRIMARY KEY     | id
 customer   | customer_score_check | CHECK           |
 orders     | orders_cust_fkey     | FOREIGN KEY     | cust
 orders     | orders_no_not_null   | CHECK           |
 orders     | orders_pkey          | PRIMARY KEY     | no
(7 rows)
```

### D. Foreign keys

<!-- example: postgresql -->
```sql
SELECT constraint_name, unique_constraint_name, match_option, update_rule, delete_rule
FROM information_schema.referential_constraints;
SELECT table_name, column_name, constraint_name FROM information_schema.constraint_column_usage
WHERE constraint_name = 'orders_cust_fkey';
```

```text
 constraint_name  | unique_constraint_name | match_option | update_rule | delete_rule
------------------+------------------------+--------------+-------------+-------------
 orders_cust_fkey | customer_pkey          | NONE         | NO ACTION   | CASCADE
(1 row)

 table_name | column_name | constraint_name
------------+-------------+------------------
 customer   | id          | orders_cust_fkey
(1 row)
```

### E. Check constraints

<!-- example: postgresql -->
```sql
SELECT constraint_name, check_clause FROM information_schema.check_constraints ORDER BY constraint_name;
```

```text
   constraint_name    |  check_clause
----------------------+----------------
 customer_id_not_null | id IS NOT NULL
 customer_score_check | (score >= 0)
 orders_no_not_null   | no IS NOT NULL
(3 rows)
```

### F. psql's description of a table

<!-- example: postgresql -->
```sql
\d orders
```

```text
                  Table "public.orders"
 Column |     Type      | Collation | Nullable | Default
--------+---------------+-----------+----------+---------
 no     | integer       |           | not null |
 cust   | integer       |           |          |
 total  | numeric(10,2) |           |          |
Indexes:
    "orders_pkey" PRIMARY KEY, btree (no)
    "orders_cust" btree (cust) WHERE total > 0
    "orders_lower" btree (((total * 2)))
Foreign-key constraints:
    "orders_cust_fkey" FOREIGN KEY (cust) REFERENCES customer(id) ON DELETE CASCADE
```

### G. Constraints that are not enforced

<!-- example: postgresql -->
```sql
CREATE TABLE shipment (id int PRIMARY KEY, cust int REFERENCES customer (id) NOT ENFORCED,
                       qty int CONSTRAINT qty_pos CHECK (qty > 0) NOT ENFORCED);
ALTER TABLE shipment ADD CONSTRAINT qty_max CHECK (qty < 100) NOT VALID;
SELECT conname, contype, conenforced, convalidated FROM pg_constraint
WHERE conrelid = 'shipment'::regclass ORDER BY conname;
SELECT constraint_name, constraint_type, enforced FROM information_schema.table_constraints
WHERE table_name = 'shipment' ORDER BY constraint_name;
SELECT pg_get_constraintdef(oid) AS definition FROM pg_constraint
WHERE conrelid = 'shipment'::regclass AND contype IN ('c', 'f') ORDER BY conname;
```

```text
CREATE TABLE
ALTER TABLE
       conname        | contype | conenforced | convalidated
----------------------+---------+-------------+--------------
 qty_max              | c       | t           | f
 qty_pos              | c       | f           | f
 shipment_cust_fkey   | f       | f           | f
 shipment_id_not_null | n       | t           | t
 shipment_pkey        | p       | t           | t
(5 rows)

   constraint_name    | constraint_type | enforced
----------------------+-----------------+----------
 qty_max              | CHECK           | YES
 qty_pos              | CHECK           | NO
 shipment_cust_fkey   | FOREIGN KEY     | NO
 shipment_id_not_null | CHECK           | YES
 shipment_pkey        | PRIMARY KEY     | YES
(5 rows)

                       definition
---------------------------------------------------------
 CHECK ((qty < 100)) NOT VALID
 CHECK ((qty > 0)) NOT ENFORCED
 FOREIGN KEY (cust) REFERENCES customer(id) NOT ENFORCED
(3 rows)
```

### H. NOT NULL constraints

<!-- example: postgresql -->
```sql
CREATE TABLE seat (row_no int CONSTRAINT seat_row_no_not_null CHECK (row_no > 0), label text NOT NULL,
                   guest text CONSTRAINT guest_named NOT NULL);
ALTER TABLE seat ALTER COLUMN row_no SET NOT NULL;
ALTER TABLE seat RENAME COLUMN label TO tag;
SELECT conname, contype, conkey, pg_get_constraintdef(oid) AS definition FROM pg_constraint
WHERE conrelid = 'seat'::regclass ORDER BY conname;
SELECT constraint_name, constraint_type FROM information_schema.table_constraints
WHERE table_name = 'seat' ORDER BY constraint_name;
SELECT constraint_name, column_name FROM information_schema.constraint_column_usage
WHERE table_name = 'seat' ORDER BY constraint_name;
SELECT constraint_name, check_clause FROM information_schema.check_constraints
WHERE constraint_name LIKE 'seat%' OR constraint_name = 'guest_named' ORDER BY constraint_name;
```

```text
CREATE TABLE
ALTER TABLE
ALTER TABLE
        conname        | contype | conkey |      definition
-----------------------+---------+--------+----------------------
 guest_named           | n       | {3}    | NOT NULL guest
 seat_label_not_null   | n       | {2}    | NOT NULL tag
 seat_row_no_not_null  | c       | {1}    | CHECK ((row_no > 0))
 seat_row_no_not_null1 | n       | {1}    | NOT NULL row_no
(4 rows)

    constraint_name    | constraint_type
-----------------------+-----------------
 guest_named           | CHECK
 seat_label_not_null   | CHECK
 seat_row_no_not_null  | CHECK
 seat_row_no_not_null1 | CHECK
(4 rows)

    constraint_name    | column_name
-----------------------+-------------
 guest_named           | guest
 seat_label_not_null   | tag
 seat_row_no_not_null  | row_no
 seat_row_no_not_null1 | row_no
(4 rows)

    constraint_name    |    check_clause
-----------------------+--------------------
 guest_named           | guest IS NOT NULL
 seat_label_not_null   | tag IS NOT NULL
 seat_row_no_not_null  | (row_no > 0)
 seat_row_no_not_null1 | row_no IS NOT NULL
(4 rows)
```

## See also

[Catalog: tables and columns](catalog-tables.md) · [CREATE TABLE](create-table.md) ·
[CREATE INDEX](create-index.md) · [Catalog functions](functions-catalog.md)
