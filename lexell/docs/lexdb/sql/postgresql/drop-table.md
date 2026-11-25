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

- The refusal of a table that other objects depend on (2BP01) is PostgreSQL's: a `DETAIL` with a line for each foreign
  key of another table (`constraint orders_customer_id_fkey on table orders depends on table customer`) and for each
  view (and the views that read those views), and the `HINT`. A table that only foreign keys depend on is refused the
  same way; a table's foreign key on itself is no dependent. The order of the lines differs: lexdb lists the keys by
  their tables, then the views by their names, where PostgreSQL lists the objects in the order they were made.
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

The refusal names the foreign key of `orders` and the view `customer_names`. `CASCADE` drops the view and the key (the
table `orders` stays).

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
DETAIL:  constraint orders_customer_id_fkey on table orders depends on table customer
view customer_names depends on table customer
HINT:  Use DROP ... CASCADE to drop the dependent objects too.
DROP TABLE
      conname
--------------------
 orders_id_not_null
 orders_pkey
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

### D. A table under a view, and a view under a view

The refusal names each view and what it reads. `CASCADE` drops the views, and the views over them.

<!-- example: postgresql -->
```sql
CREATE TABLE dept (id int PRIMARY KEY, name text);
CREATE VIEW dept_names AS SELECT name FROM dept;
CREATE VIEW dept_upper AS SELECT upper(name) AS name FROM dept_names;
DROP TABLE dept;
DROP TABLE dept CASCADE;
SELECT count(*) FROM pg_views WHERE viewname IN ('dept_names', 'dept_upper');
```

```text
CREATE TABLE
CREATE VIEW
CREATE VIEW
ERROR:  cannot drop table dept because other objects depend on it
DETAIL:  view dept_names depends on table dept
view dept_upper depends on view dept_names
HINT:  Use DROP ... CASCADE to drop the dependent objects too.
DROP TABLE
 count
-------
     0
(1 row)
```

### E. Errors

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

### F. Only a foreign key depends on it

<!-- example: postgresql -->
```sql
CREATE TABLE team (id int PRIMARY KEY);
CREATE TABLE player (id int PRIMARY KEY, team_id int REFERENCES team);
DROP TABLE team;
DROP TABLE team CASCADE;
SELECT count(*) FROM pg_constraint WHERE conrelid = 'player'::regclass AND contype = 'f';
```

```text
CREATE TABLE
CREATE TABLE
ERROR:  cannot drop table team because other objects depend on it
DETAIL:  constraint player_team_id_fkey on table player depends on table team
HINT:  Use DROP ... CASCADE to drop the dependent objects too.
DROP TABLE
 count
-------
     0
(1 row)
```

## See also

[CREATE TABLE](create-table.md) · [TRUNCATE](truncate.md) · [DROP VIEW](drop-view.md) · [DROP INDEX](drop-index.md)
