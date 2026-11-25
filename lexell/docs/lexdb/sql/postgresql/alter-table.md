# ALTER TABLE

Changes a table's columns, constraints, name or schema.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18, and 19 for `ALTER CONSTRAINT ... ENFORCED`.

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
    | ALTER CONSTRAINT constraint_name { ENFORCED | NOT ENFORCED }
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
: `SET NOT NULL` checks the rows first (23502 if one is NULL), and makes a `NOT NULL` constraint named
  `table_column_not_null` (a column that has one already is left as it is). `DROP NOT NULL` removes the constraint;
  on a column of a primary key it is 42P16, and on an identity column 42601.

`ADD` [ `CONSTRAINT` *name* ] `NOT NULL` *column_name*
: Makes the column `NOT NULL` under the name given (checking the rows first, as `SET NOT NULL` does). A column that
  has a `NOT NULL` constraint already takes no second one: the statement is 55000 when it gives a name, and does
  nothing when it does not.

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
: Checks a `NOT VALID` constraint against the rows, and marks it valid. A constraint that is `NOT ENFORCED` cannot
  be validated (55000): make it `ENFORCED` first.

`ALTER CONSTRAINT` ... `ENFORCED`, `NOT ENFORCED`
: Changes whether a `CHECK` or `FOREIGN KEY` constraint is enforced. `ENFORCED` checks every row first, as `ADD`
  does (a `CHECK` that a row fails is 23514, a foreign key 23503); if all pass, the constraint is enforced and valid.
  `NOT ENFORCED` stops the checking of new and changed rows; the constraint is then also not valid. A constraint
  that is in the state asked for is left as it is. A primary key, a unique constraint and a `NOT NULL` cannot
  change: that is 42809.

`DROP CONSTRAINT`
: Removes a constraint, and the index of a unique or primary key. The name of a `NOT NULL` constraint makes the
  column nullable again, as `DROP NOT NULL` does (42P16 on a column of a primary key, 42704 for a name that is
  none; `IF EXISTS` gives a notice instead).

`RENAME`
: Renames a column, a constraint (a `NOT NULL` constraint too: 42710 for a name the table uses already), or the
  table. Views that use the old name go on working: their text follows the
  new name.

`SET SCHEMA`
: Moves the table to another schema.

`OWNER TO`
: Gives the table to another role.

## Remarks

- `ALTER COLUMN ... TYPE` of a column an [assertion](create-assertion.md) reads casts the values, and then runs the
  assertion's whole query: 23514 if it fails. `DROP COLUMN` of one is 2BP01 and a rename 0A000.
- Several actions may be given at once, separated by commas.
- `ALTER TABLE` is transactional: in a block, `ROLLBACK` takes it back.
- Adding, dropping or changing the primary key, and changing a column's type, rewrite the table: 1 million rows take
  some seconds (lexdb-gaps.md 2.2).
- Inside a read-only transaction, and on a replica, `ALTER TABLE` gives 25006.
- A constraint that is not enforced is kept in the catalog and can be renamed and dropped like any other. The state
  shows in `pg_constraint.conenforced` and `convalidated`, in the text `pg_get_constraintdef` gives, and in
  `information_schema.table_constraints.enforced` (see [Catalog: constraints](catalog-constraints.md)).
- A foreign key that is not enforced does not check the table it refers to, and does not act on it: deleting the
  parent row neither refuses (23503) nor cascades.
- `ALTER CONSTRAINT` takes the name of a constraint of the table (42704 for another name).
- A `NOT NULL` constraint is a row of `pg_constraint` (`contype` `n`) with its name, and of `information_schema`
  (see [Catalog: constraints](catalog-constraints.md)). Its name is fixed when it is made: renaming the column or
  the table leaves it.

## Differences from PostgreSQL

- Not supported: `ALTER COLUMN ... SET STATISTICS` and `COLLATE` in `ALTER COLUMN ... TYPE` (42601); `SET ( storage_parameter )`, `ENABLE` and `DISABLE TRIGGER`, `CLUSTER ON`, `SET LOGGED`,
  `SET TABLESPACE`, `ATTACH` and `DETACH PARTITION`, `INHERIT`, row security, `REPLICA IDENTITY` (0A000, `lexdb:
  ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA`).
- `ALTER CONSTRAINT ... DEFERRABLE`, `INITIALLY DEFERRED` and `NOT DEFERRABLE` are 0A000 (`lexdb: ALTER
  CONSTRAINT ... DEFERRABLE is not supported`); only `ENFORCED` and `NOT ENFORCED` are taken.
- While a view reads the table, `DROP COLUMN` of any of its columns and `SET SCHEMA` are refused (2BP01, `cannot
  alter table t because view v depends on it (lexdb keeps a view's text: drop the view, then make it again)`).
  PostgreSQL refuses only the drop of a column the view uses, and moves the table with the view following it. A
  type change of a column a view uses is allowed; PostgreSQL refuses it (0A000).
- `OWNER TO postgres` gives 42704 `role "postgres" does not exist`, although `pg_roles` lists `postgres` and the
  session runs as it. `OWNER TO` a role made with `CREATE ROLE` works.
- A view that selects `*` from the table shows the columns added and dropped later (see [CREATE
  VIEW](create-view.md)).
- A type change that needs `USING` says so in its message (`USING name::integer would`) rather than in a `HINT`.
- On a table without a primary key, a column added later gets an `attnum` (and a `conkey` in `pg_constraint`) one
  higher than in PostgreSQL.

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
 item_id_not_null  | n       | t
 item_pkey         | p       | t
 item_price_id_key | u       | t
 item_qty_not_null | n       | t
(4 rows)
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

### H. Constraints that are not enforced

<!-- example: postgresql -->
```sql
CREATE TABLE team (id int PRIMARY KEY, name text);
CREATE TABLE member (id int PRIMARY KEY, team_id int, age int,
  CONSTRAINT member_age_ck CHECK (age >= 0) NOT ENFORCED,
  CONSTRAINT member_team_fk FOREIGN KEY (team_id) REFERENCES team (id) NOT ENFORCED);
INSERT INTO team VALUES (1, 'red');
INSERT INTO member VALUES (1, 1, 30), (2, 7, -2);
SELECT conname, conenforced, convalidated FROM pg_constraint
WHERE conrelid = 'member'::regclass AND contype <> 'p' ORDER BY conname;
```

```text
CREATE TABLE
CREATE TABLE
INSERT 0 1
INSERT 0 2
      conname       | conenforced | convalidated
--------------------+-------------+--------------
 member_age_ck      | f           | f
 member_id_not_null | t           | t
 member_team_fk     | f           | f
(3 rows)
```

Both rows were taken, though row 2 breaks both constraints. `ENFORCED` checks the rows first, and refuses while one
breaks the constraint:

<!-- example: postgresql -->
```sql
ALTER TABLE member ALTER CONSTRAINT member_age_ck ENFORCED;
ALTER TABLE member ALTER CONSTRAINT member_team_fk ENFORCED;
UPDATE member SET age = 0, team_id = 1 WHERE id = 2;
ALTER TABLE member ALTER CONSTRAINT member_age_ck ENFORCED;
ALTER TABLE member ALTER CONSTRAINT member_team_fk ENFORCED;
INSERT INTO member VALUES (3, 9, 5);
INSERT INTO member VALUES (3, 1, -1);
```

```text
ERROR:  check constraint "member_age_ck" of relation "member" is violated by some row
ERROR:  insert or update on table "member" violates foreign key constraint "member_team_fk"
DETAIL:  Key (team_id)=(7) is not present in table "team".
UPDATE 1
ALTER TABLE
ALTER TABLE
ERROR:  insert or update on table "member" violates foreign key constraint "member_team_fk"
DETAIL:  Key (team_id)=(9) is not present in table "team".
ERROR:  new row for relation "member" violates check constraint "member_age_ck"
```

`NOT ENFORCED` lets the rows in again, and the constraint is not valid until it is enforced:

<!-- example: postgresql -->
```sql
ALTER TABLE member ALTER CONSTRAINT member_age_ck NOT ENFORCED;
INSERT INTO member VALUES (3, 1, -1);
SELECT conname, pg_get_constraintdef(oid) AS definition, conenforced, convalidated FROM pg_constraint
WHERE conrelid = 'member'::regclass AND contype <> 'p' ORDER BY conname;
ALTER TABLE member ALTER CONSTRAINT member_age_ck ENFORCED;
UPDATE member SET age = 1 WHERE id = 3;
ALTER TABLE member ALTER CONSTRAINT member_age_ck ENFORCED;
```

```text
ALTER TABLE
INSERT 0 1
      conname       |                definition                 | conenforced | convalidated
--------------------+-------------------------------------------+-------------+--------------
 member_age_ck      | CHECK ((age >= 0)) NOT ENFORCED           | f           | f
 member_id_not_null | NOT NULL id                               | t           | t
 member_team_fk     | FOREIGN KEY (team_id) REFERENCES team(id) | t           | t
(3 rows)

ERROR:  check constraint "member_age_ck" of relation "member" is violated by some row
UPDATE 1
ALTER TABLE
```

While a foreign key is enforced, the parent row it refers to cannot be deleted. When it is not enforced, it can:

<!-- example: postgresql -->
```sql
DELETE FROM team WHERE id = 1;
ALTER TABLE member ALTER CONSTRAINT member_team_fk NOT ENFORCED;
DELETE FROM team WHERE id = 1;
SELECT id, team_id FROM member ORDER BY id;
```

```text
ERROR:  update or delete on table "team" violates foreign key constraint "member_team_fk" on table "member"
DETAIL:  Key (id)=(1) is still referenced from table "member".
ALTER TABLE
DELETE 1
 id | team_id
----+---------
  1 |       1
  2 |       1
  3 |       1
(3 rows)
```

### I. Errors

<!-- example: postgresql -->
```sql
ALTER TABLE store.stock DROP COLUMN nosuch;
ALTER TABLE IF EXISTS nosuch ADD COLUMN x int;
ALTER TABLE store.stock ADD PRIMARY KEY (name);
ALTER TABLE store.stock SET (fillfactor = 50);
ALTER TABLE store.stock OWNER TO postgres;
ALTER TABLE member ALTER CONSTRAINT member_pkey NOT ENFORCED;
ALTER TABLE member ALTER CONSTRAINT member_age_ck NOT DEFERRABLE;
ALTER TABLE member ALTER CONSTRAINT nosuch ENFORCED;
ALTER TABLE member ADD CONSTRAINT member_age_max CHECK (age < 150) NOT ENFORCED;
ALTER TABLE member VALIDATE CONSTRAINT member_age_max;
```

```text
ERROR:  column "nosuch" of relation "stock" does not exist
NOTICE:  relation "nosuch" does not exist, skipping
ALTER TABLE
ERROR:  multiple primary keys for table "stock" are not allowed
ERROR:  lexdb: ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA
ERROR:  role "postgres" does not exist
ERROR:  cannot alter enforceability of constraint "member_pkey" of relation "member"
HINT:  Only foreign key and check constraints can change enforceability.
ERROR:  lexdb: ALTER CONSTRAINT ... DEFERRABLE is not supported
ERROR:  constraint "nosuch" of relation "member" does not exist
ALTER TABLE
ERROR:  cannot validate NOT ENFORCED constraint
```

### J. Named NOT NULL constraints

<!-- example: postgresql -->
```sql
CREATE TABLE badge (id int PRIMARY KEY, holder text CONSTRAINT holder_required NOT NULL, issued date, expires date);
ALTER TABLE badge ALTER COLUMN issued SET NOT NULL;
ALTER TABLE badge ADD CONSTRAINT expires_required NOT NULL expires;
ALTER TABLE badge ADD CONSTRAINT issued_again NOT NULL issued;
ALTER TABLE badge RENAME CONSTRAINT holder_required TO holder_needed;
ALTER TABLE badge RENAME COLUMN issued TO issued_on;
SELECT conname, conkey, pg_get_constraintdef(oid) AS definition FROM pg_constraint
WHERE conrelid = 'badge'::regclass AND contype = 'n' ORDER BY conname;
ALTER TABLE badge DROP CONSTRAINT expires_required;
ALTER TABLE badge DROP CONSTRAINT badge_id_not_null;
ALTER TABLE badge DROP CONSTRAINT nosuch;
ALTER TABLE badge DROP CONSTRAINT IF EXISTS nosuch;
INSERT INTO badge VALUES (1, 'ann', DATE '2026-01-01', NULL);
INSERT INTO badge VALUES (2, NULL, DATE '2026-01-01', NULL);
```

```text
CREATE TABLE
ALTER TABLE
ALTER TABLE
ERROR:  cannot create not-null constraint "issued_again" on column "issued" of table "badge"
DETAIL:  A not-null constraint named "badge_issued_not_null" already exists for this column.
ALTER TABLE
ALTER TABLE
        conname        | conkey |     definition
-----------------------+--------+--------------------
 badge_id_not_null     | {1}    | NOT NULL id
 badge_issued_not_null | {3}    | NOT NULL issued_on
 expires_required      | {4}    | NOT NULL expires
 holder_needed         | {2}    | NOT NULL holder
(4 rows)

ALTER TABLE
ERROR:  column "id" is in a primary key
ERROR:  constraint "nosuch" of relation "badge" does not exist
NOTICE:  constraint "nosuch" of relation "badge" does not exist, skipping
ALTER TABLE
INSERT 0 1
ERROR:  null value in column "holder" of relation "badge" violates not-null constraint
DETAIL:  Failing row contains (2, null, 2026-01-01, null).
```

## See also

[CREATE TABLE](create-table.md) · [DROP TABLE](drop-table.md) · [CREATE INDEX](create-index.md) ·
[CREATE VIEW](create-view.md)
