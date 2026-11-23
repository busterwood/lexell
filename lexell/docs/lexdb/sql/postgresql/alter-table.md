# ALTER TABLE

Changes a table's columns, constraints, name or schema.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
ALTER TABLE [ IF EXISTS ] [ ONLY ] name action [, ... ]
ALTER TABLE [ IF EXISTS ] [ ONLY ] name RENAME [ COLUMN ] column_name TO new_column_name
ALTER TABLE [ IF EXISTS ] [ ONLY ] name RENAME CONSTRAINT constraint_name TO new_constraint_name
ALTER TABLE [ IF EXISTS ] name RENAME TO new_name
ALTER TABLE [ IF EXISTS ] name SET SCHEMA new_schema
ALTER TABLE [ IF EXISTS ] name OWNER TO { new_owner | CURRENT_USER | SESSION_USER }

action:
    ADD [ COLUMN ] [ IF NOT EXISTS ] column_name data_type [ COLLATE collation ] [ column_constraint [ ... ] ]
    | DROP [ COLUMN ] [ IF EXISTS ] column_name [ RESTRICT | CASCADE ]
    | ALTER [ COLUMN ] column_name [ SET DATA ] TYPE data_type [ USING expression ]
    | ALTER [ COLUMN ] column_name SET DEFAULT expression
    | ALTER [ COLUMN ] column_name DROP DEFAULT
    | ALTER [ COLUMN ] column_name { SET | DROP } NOT NULL
    | ALTER [ COLUMN ] column_name SET EXPRESSION AS ( expression )
    | ALTER [ COLUMN ] column_name DROP EXPRESSION [ IF EXISTS ]
    | ALTER [ COLUMN ] column_name ADD GENERATED { ALWAYS | BY DEFAULT } AS IDENTITY [ ( sequence_options ) ]
    | ALTER [ COLUMN ] column_name { SET GENERATED { ALWAYS | BY DEFAULT } | SET sequence_option | RESTART [ [ WITH ] restart ] } [...]
    | ALTER [ COLUMN ] column_name DROP IDENTITY [ IF EXISTS ]
    | ADD table_constraint
    | ADD [ CONSTRAINT constraint_name ] NOT NULL column_name
    | VALIDATE CONSTRAINT constraint_name
    | DROP CONSTRAINT [ IF EXISTS ] constraint_name [ RESTRICT | CASCADE ]
```

*column_constraint* and *table_constraint* are those of [CREATE TABLE](create-table.md).

## Arguments

`IF EXISTS`
: If the table does not exist, does nothing and gives a notice.

`ONLY`
: Accepted and changes nothing: lexdb has no inheritance.

`ADD COLUMN`
: Adds a column at the end. Existing rows get its default, computed for each row (so `DEFAULT now()` and a
  `serial` column fill every row), or NULL. A `NOT NULL` column needs a default when the table has rows (23502
  otherwise). `IF NOT EXISTS` skips a column that is there, with a notice.

`DROP COLUMN`
: Removes a column, with the indexes and constraints on it. `IF EXISTS` skips one that is not there.

`ALTER COLUMN ... TYPE`
: Changes a column's type, converting each value. `USING` gives the new value as an expression of the old row;
  without it, a type that the old one does not convert to by assignment (text to integer) is 42804.

`SET DEFAULT`, `DROP DEFAULT`
: The default for rows inserted from now on.

`SET NOT NULL`, `DROP NOT NULL`
: `SET NOT NULL` checks the rows first (23502 if one is NULL).

`SET EXPRESSION AS`, `DROP EXPRESSION`
: Gives a generated column a new expression, computed again for every row; or makes it an ordinary column that
  keeps its values.

`ADD GENERATED ... AS IDENTITY`, `SET GENERATED`, `RESTART`, `DROP IDENTITY`
: Makes a `NOT NULL` integer column an identity column, changes how it takes values, restarts its sequence, or
  makes it an ordinary column again.

`ADD` *table_constraint*
: Adds a constraint. The rows are checked first: a `CHECK` that a row fails is 23514, a `UNIQUE` or `PRIMARY KEY`
  over duplicates 23505, a `FOREIGN KEY` that a row breaks 23503. With `NOT VALID`, a `CHECK` or `FOREIGN KEY`
  applies to new rows only, until `VALIDATE CONSTRAINT`.

`VALIDATE CONSTRAINT`
: Checks a `NOT VALID` constraint against the rows, and marks it valid.

`DROP CONSTRAINT`
: Removes a constraint, and the index of a unique or primary key.

`RENAME`
: Renames a column, a constraint, or the table. Views that use the old name go on working: their text follows the
  new name.

`SET SCHEMA`
: Moves the table to another schema.

`OWNER TO`
: Gives the table to another role.

## Remarks

- Several actions may be given at once, separated by commas.
- `ALTER TABLE` is transactional: in a block, `ROLLBACK` takes it back.
- Adding, dropping or changing the primary key, and changing a column's type, rewrite the table: 1 million rows take
  some seconds (lexdb-gaps.md 2.2).
- Inside a read-only transaction, and on a replica, `ALTER TABLE` gives 25006.

## Differences from PostgreSQL

- Not supported: `ALTER COLUMN ... SET STATISTICS` and `COLLATE` in `ALTER COLUMN ... TYPE` (42601); `SET ( storage_parameter )`, `ENABLE` and `DISABLE TRIGGER`, `CLUSTER ON`, `SET LOGGED`,
  `SET TABLESPACE`, `ATTACH` and `DETACH PARTITION`, `INHERIT`, row security, `REPLICA IDENTITY` (0A000, `lexdb:
  ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA`).
- While a view reads the table, `DROP COLUMN` of any of its columns and `SET SCHEMA` are refused (2BP01, `cannot
  alter table t because view v depends on it (lexdb keeps a view's text: drop the view, then make it again)`).
  PostgreSQL refuses only the drop of a column the view uses, and moves the table with the view following it. A
  type change of a column a view uses is allowed; PostgreSQL refuses it (0A000).
- `OWNER TO postgres` gives 42704 `role "postgres" does not exist`, although `pg_roles` lists `postgres` and the
  session runs as it. `OWNER TO` a role made with `CREATE ROLE` works.
- A view that selects `*` from the table shows the columns added and dropped later (see [CREATE
  VIEW](create-view.md)).
- A type change that needs `USING` says so in its message (`USING name::integer would`) rather than in a `HINT`.

## Examples

<!--setup: postgresql
CREATE TABLE item (id int PRIMARY KEY, name text, qty int);
INSERT INTO item VALUES (1, 'pen', 10), (2, 'ink', NULL);
-->

The examples start from one table:

```sql
CREATE TABLE item (id int PRIMARY KEY, name text, qty int);
INSERT INTO item VALUES (1, 'pen', 10), (2, 'ink', NULL);
```

### A. Add and drop columns

<!-- example: postgresql -->
```sql
ALTER TABLE item ADD COLUMN price numeric(6,2) DEFAULT 1.50, ADD COLUMN code serial;
ALTER TABLE item ADD COLUMN IF NOT EXISTS price int;
SELECT * FROM item ORDER BY id;
ALTER TABLE item DROP COLUMN code;
ALTER TABLE item ADD COLUMN needed int NOT NULL;
```

```text
ALTER TABLE
NOTICE:  column "price" of relation "item" already exists, skipping
ALTER TABLE
 id | name | qty | price | code
----+------+-----+-------+------
  1 | pen  |  10 |  1.50 |    1
  2 | ink  |     |  1.50 |    2
(2 rows)

ALTER TABLE
ERROR:  column "needed" of relation "item" contains null values
```

### B. Defaults and NOT NULL

<!-- example: postgresql -->
```sql
ALTER TABLE item ALTER COLUMN qty SET NOT NULL;
UPDATE item SET qty = 0 WHERE qty IS NULL;
ALTER TABLE item ALTER COLUMN qty SET NOT NULL, ALTER COLUMN qty SET DEFAULT 0;
INSERT INTO item (id, name) VALUES (3, 'pad');
SELECT id, qty FROM item ORDER BY id;
```

```text
ERROR:  column "qty" of relation "item" contains null values
UPDATE 1
ALTER TABLE
INSERT 0 1
 id | qty
----+-----
  1 |  10
  2 |   0
  3 |   0
(3 rows)
```

### C. Change a type

<!-- example: postgresql -->
```sql
ALTER TABLE item ALTER COLUMN qty TYPE bigint;
ALTER TABLE item ALTER COLUMN name TYPE int;
ALTER TABLE item ALTER COLUMN name TYPE int USING length(name);
SELECT id, name, pg_typeof(name) FROM item ORDER BY id;
ALTER TABLE item ALTER COLUMN name TYPE text;
```

```text
ALTER TABLE
ERROR:  column "name" cannot be cast automatically to type integer (USING name::integer would)
ALTER TABLE
 id | name | pg_typeof
----+------+-----------
  1 |    3 | integer
  2 |    3 | integer
  3 |    3 | integer
(3 rows)

ALTER TABLE
```

### D. Add, validate and drop constraints

<!-- example: postgresql -->
```sql
ALTER TABLE item ADD CONSTRAINT qty_small CHECK (qty < 5);
ALTER TABLE item ADD CONSTRAINT qty_small CHECK (qty < 5) NOT VALID;
INSERT INTO item (id, qty) VALUES (4, 9);
ALTER TABLE item VALIDATE CONSTRAINT qty_small;
ALTER TABLE item DROP CONSTRAINT qty_small;
ALTER TABLE item ADD UNIQUE (price, id);
SELECT conname, contype, convalidated FROM pg_constraint WHERE conrelid = 'item'::regclass ORDER BY conname;
```

```text
ERROR:  check constraint "qty_small" of relation "item" is violated by some row
ALTER TABLE
ERROR:  new row for relation "item" violates check constraint "qty_small"
ERROR:  check constraint "qty_small" of relation "item" is violated by some row
ALTER TABLE
ALTER TABLE
      conname      | contype | convalidated
-------------------+---------+--------------
 item_pkey         | p       | t
 item_price_id_key | u       | t
(2 rows)
```

### E. Identity and generated columns

<!-- example: postgresql -->
```sql
ALTER TABLE item ADD COLUMN seq int GENERATED ALWAYS AS IDENTITY;
ALTER TABLE item ALTER COLUMN seq RESTART WITH 100;
INSERT INTO item (id) VALUES (5);
ALTER TABLE item ADD COLUMN twice bigint GENERATED ALWAYS AS (qty * 2) STORED;
ALTER TABLE item ALTER COLUMN twice SET EXPRESSION AS (qty * 3);
SELECT id, qty, seq, twice FROM item ORDER BY id;
```

```text
ALTER TABLE
ALTER TABLE
INSERT 0 1
ALTER TABLE
ALTER TABLE
 id | qty | seq | twice
----+-----+-----+-------
  1 |  10 |   1 |    30
  2 |   0 |   2 |     0
  3 |   0 |   3 |     0
  5 |   0 | 100 |     0
(4 rows)
```

### F. Rename, and move to a schema

<!-- example: postgresql -->
```sql
CREATE VIEW item_names AS SELECT id, name FROM item;
ALTER TABLE item RENAME COLUMN qty TO quantity;
ALTER TABLE item RENAME TO stock;
SELECT * FROM item_names ORDER BY id;
CREATE SCHEMA store;
ALTER TABLE stock SET SCHEMA store;
DROP VIEW item_names;
ALTER TABLE stock SET SCHEMA store;
SELECT schemaname, tablename FROM pg_tables WHERE tablename = 'stock';
```

```text
CREATE VIEW
ALTER TABLE
ALTER TABLE
 id | name
----+------
  1 | 3
  2 | 3
  3 | 3
  5 |
(4 rows)

CREATE SCHEMA
ERROR:  cannot alter table stock because view item_names depends on it (lexdb keeps a view's text: drop the view, then make it again)
DROP VIEW
ALTER TABLE
 schemaname | tablename
------------+-----------
 store      | stock
(1 row)
```

### G. Rolled back

<!-- example: postgresql -->
```sql
BEGIN;
ALTER TABLE store.stock ADD COLUMN note text;
ROLLBACK;
SELECT count(*) FROM information_schema.columns WHERE table_name = 'stock' AND column_name = 'note';
```

```text
BEGIN
ALTER TABLE
ROLLBACK
 count
-------
     0
(1 row)
```

### H. Errors

<!-- example: postgresql -->
```sql
ALTER TABLE store.stock DROP COLUMN nosuch;
ALTER TABLE IF EXISTS nosuch ADD COLUMN x int;
ALTER TABLE store.stock ADD PRIMARY KEY (name);
ALTER TABLE store.stock SET (fillfactor = 50);
ALTER TABLE store.stock OWNER TO postgres;
```

```text
ERROR:  column "nosuch" of relation "stock" does not exist
NOTICE:  relation "nosuch" does not exist, skipping
ALTER TABLE
ERROR:  multiple primary keys for table "stock" are not allowed
ERROR:  lexdb: ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA
ERROR:  role "postgres" does not exist
```

## See also

[CREATE TABLE](create-table.md) · [DROP TABLE](drop-table.md) · [CREATE INDEX](create-index.md) ·
[CREATE VIEW](create-view.md)
