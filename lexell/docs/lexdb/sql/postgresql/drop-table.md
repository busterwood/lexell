# DROP TABLE

Removes tables, with their rows, indexes, constraints and owned sequences.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
DROP TABLE [ IF EXISTS ] name [, ...] [ CASCADE | RESTRICT ]
```

## Arguments

`IF EXISTS`
: A table that does not exist is skipped with a notice.

*name*
: A table, optionally schema-qualified.

`CASCADE`
: Also drops the views that use the table, and the foreign keys of other tables that refer to it (those tables
  stay).

`RESTRICT`
: Refuses to drop a table that a view or another table's foreign key depends on. This is the default.

## Remarks

- The table's storage is freed without reading its rows: a large table drops in milliseconds.
- The sequences of its `serial` and identity columns, and others it owns (`OWNED BY`), are dropped with it.
- `DROP TABLE` is transactional: in a block, `ROLLBACK` brings the table back.
- A view is dropped with [DROP VIEW](drop-view.md); `DROP TABLE` of a view is 42809.
- Inside a read-only transaction, and on a replica, `DROP TABLE` gives 25006.

## Differences from PostgreSQL

- The refusal of a table with dependents (2BP01) has no `DETAIL` listing them and no `HINT`. When only foreign keys
  depend on it, the message says what `CASCADE` would do (`with CASCADE the foreign keys on it are dropped`).
- `CASCADE` gives no `NOTICE` naming what it drops.

## Examples

<!--setup: postgresql
CREATE TABLE customer (id serial PRIMARY KEY, name text);
CREATE TABLE orders (id int PRIMARY KEY, customer_id int REFERENCES customer);
CREATE VIEW customer_names AS SELECT name FROM customer;
CREATE TABLE scratch_a (x int);
CREATE TABLE scratch_b (x int);
-->

The examples use these objects:

```sql
CREATE TABLE customer (id serial PRIMARY KEY, name text);
CREATE TABLE orders (id int PRIMARY KEY, customer_id int REFERENCES customer);
CREATE VIEW customer_names AS SELECT name FROM customer;
CREATE TABLE scratch_a (x int);
CREATE TABLE scratch_b (x int);
```

### A. Drop tables

<!-- example: postgresql -->
```sql
DROP TABLE scratch_a, scratch_b;
DROP TABLE IF EXISTS scratch_a, nosuch;
```

```text
DROP TABLE
NOTICE:  table "scratch_a" does not exist, skipping
NOTICE:  table "nosuch" does not exist, skipping
DROP TABLE
```

### B. Rolled back

<!-- example: postgresql -->
```sql
BEGIN;
DROP TABLE orders;
ROLLBACK;
SELECT count(*) FROM orders;
```

```text
BEGIN
DROP TABLE
ROLLBACK
 count
-------
     0
(1 row)
```

### C. Dependents and CASCADE

<!-- example: postgresql -->
```sql
DROP TABLE customer;
DROP TABLE customer CASCADE;
SELECT conname FROM pg_constraint WHERE conrelid = 'orders'::regclass ORDER BY conname;
SELECT count(*) FROM pg_views WHERE viewname = 'customer_names';
SELECT count(*) FROM pg_class WHERE relname = 'customer_id_seq';
```

```text
ERROR:  cannot drop table customer because other objects depend on it
DROP TABLE
      conname
--------------------
 orders_pkey
 orders_id_not_null
(2 rows)

 count
-------
     0
(1 row)

 count
-------
     0
(1 row)
```

### D. Errors

<!-- example: postgresql -->
```sql
DROP TABLE nosuch;
CREATE VIEW v AS SELECT 1 AS one;
DROP TABLE v;
```

```text
ERROR:  table "nosuch" does not exist
CREATE VIEW
ERROR:  "v" is not a table (use DROP VIEW)
```

## See also

[CREATE TABLE](create-table.md) · [TRUNCATE](truncate.md) · [DROP VIEW](drop-view.md) · [DROP INDEX](drop-index.md)
