# CREATE TABLE

Makes a new table.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18 and 19.

## Syntax

```
CREATE [ [ GLOBAL | LOCAL ] { TEMPORARY | TEMP } | UNLOGGED ] TABLE [ IF NOT EXISTS ] table_name (
    { column_name data_type [ COLLATE collation ] [ column_constraint [ ... ] ]
    | table_constraint } [, ... ]
)
[ ON COMMIT { PRESERVE ROWS | DELETE ROWS | DROP } ]

column_constraint:
    [ CONSTRAINT constraint_name ]
    { NOT NULL
    | NULL
    | CHECK ( expression ) [ NO INHERIT ] [ ENFORCED | NOT ENFORCED ]
    | DEFAULT default_expr
    | GENERATED ALWAYS AS ( generation_expr ) [ STORED | VIRTUAL ]
    | GENERATED { ALWAYS | BY DEFAULT } AS IDENTITY [ ( sequence_options ) ]
    | UNIQUE [ NULLS DISTINCT ]
    | PRIMARY KEY
    | REFERENCES reftable [ ( refcolumn ) ] [ MATCH SIMPLE ]
        [ ON DELETE referential_action ] [ ON UPDATE referential_action ]
        [ [ NOT ] DEFERRABLE ] [ INITIALLY { DEFERRED | IMMEDIATE } ] [ ENFORCED | NOT ENFORCED ] }

table_constraint:
    [ CONSTRAINT constraint_name ]
    { CHECK ( expression ) [ NO INHERIT ] [ NOT VALID ] [ ENFORCED | NOT ENFORCED ]
    | NOT NULL column_name
    | UNIQUE [ NULLS DISTINCT ] ( column_name [, ... ] )
    | PRIMARY KEY ( column_name [, ... ] )
    | FOREIGN KEY ( column_name [, ... ] ) REFERENCES reftable [ ( refcolumn [, ... ] ) ] [ MATCH SIMPLE ]
        [ ON DELETE referential_action ] [ ON UPDATE referential_action ]
        [ [ NOT ] DEFERRABLE ] [ INITIALLY { DEFERRED | IMMEDIATE } ] [ NOT VALID ]
        [ ENFORCED | NOT ENFORCED ] }

referential_action:
    NO ACTION | RESTRICT | CASCADE | SET NULL | SET DEFAULT
```

`serial`, `bigserial` and `smallserial` (`serial4`, `serial8`, `serial2`) may stand for *data_type*. For making a
table from a query, see [CREATE TABLE AS](create-table-as.md).

## Arguments

`TEMPORARY` or `TEMP`
: The table belongs to the session, in a schema of its own (`pg_temp_n`), and is dropped when the session ends.
  Other sessions cannot see it. `GLOBAL` and `LOCAL` are accepted and mean the same.

`UNLOGGED`
: Accepted; the table is an ordinary one, written to the log like any other.

`IF NOT EXISTS`
: If a relation of the name exists, does nothing and gives a notice.

*table_name*
: The table's name, optionally schema-qualified (`app.orders`). Without a schema, it goes in the first schema of
  `search_path` (`public`).

*column_name* *data_type*
: A column and its type. See the data types in the [index](README.md#data-types). A table has at least one column.

`COLLATE` *collation*
: Accepted and kept in the catalog; text always compares by its bytes.

`NOT NULL`, `NULL`
: Whether the column may be NULL. `NULL`, the default, says it may.

`CHECK (` *expression* `)`
: A condition every row must meet (not false: NULL passes). It may use the row's columns, but no subqueries. A
  column's `CHECK` is named `table_column_check`.

`DEFAULT` *default_expr*
: The column's value when an `INSERT` gives none. Any expression without columns or subqueries: a constant,
  `now()`, `nextval('s')`.

`GENERATED ALWAYS AS (` *generation_expr* `) STORED | VIRTUAL`
: A generated column, computed from the row's other columns. `STORED` keeps the value in the row; `VIRTUAL`, the
  default in PostgreSQL 18, computes it when it is read. A value cannot be given to it.

`GENERATED { ALWAYS | BY DEFAULT } AS IDENTITY`
: An identity column, an integer column filled from a sequence of its own. `ALWAYS` refuses a value given to it
  unless the `INSERT` says `OVERRIDING SYSTEM VALUE`; `BY DEFAULT` takes one. The options are those of [CREATE
  SEQUENCE](create-sequence.md) (`START WITH 10 INCREMENT BY 5`). The column is `NOT NULL`.

`serial`, `bigserial`, `smallserial`
: An `integer`, `bigint` or `smallint` column, `NOT NULL`, whose default is `nextval` of a sequence that the column
  owns, named `table_column_seq`.

`UNIQUE`
: No two rows have the same values in these columns. NULLs are distinct, so many rows may have NULL. It makes a
  unique index named `table_column_key`.

`PRIMARY KEY`
: `UNIQUE` and `NOT NULL`. A table has at most one. It makes a unique index named `table_pkey`, and the table's rows
  are kept in its order.

`REFERENCES`, `FOREIGN KEY`
: Each row's columns must match a row of *reftable* (its primary key, or the columns named, which must have a
  unique constraint), or be NULL. `ON DELETE` and `ON UPDATE` say what happens to these rows when the row they
  refer to goes or changes: `NO ACTION` (the default) and `RESTRICT` refuse; `CASCADE` deletes or updates them;
  `SET NULL` and `SET DEFAULT` set the columns. `DEFERRABLE INITIALLY DEFERRED` checks the key at the commit
  instead of at the end of the statement, in a transaction block.

`NOT VALID`
: For a table's `CHECK` or `FOREIGN KEY`: the constraint applies to new rows; on a new table there are no others. It
  is written in a table constraint only: after a column constraint, with or without `NOT ENFORCED`, it is a syntax
  error (42601). A table constraint takes `NOT VALID` and `NOT ENFORCED` together, in either order.

`ENFORCED`, `NOT ENFORCED`
: For a `CHECK` or a foreign key. `ENFORCED` is the default. A constraint that is `NOT ENFORCED` is kept and shown in
  the catalog, but rows are not checked against it: a row that breaks a `CHECK` is taken, and a foreign key does
  not look at the table it refers to and does not act when a row there is deleted or changed. It is also not valid
  (`pg_constraint.convalidated` is false). [ALTER TABLE](alter-table.md) `ALTER CONSTRAINT` changes the state. A
  primary key, a unique constraint, `NOT NULL` and a default have no such state: on a column they are 42601
  (`misplaced NOT ENFORCED clause`), on a table's primary key or unique constraint 0A000.

`ON COMMIT`
: For a temporary table: `PRESERVE ROWS` (the default) keeps its rows at each commit; `DELETE ROWS` empties it;
  `DROP` drops it at the end of the transaction.

## Remarks

- The table's rows are kept in a B+tree in the order of the primary key. A table with no primary key is kept in the
  order of a hidden row number.
- Constraint names that are not given are made as PostgreSQL makes them: `t_pkey`, `t_a_key`, `t_b_check`,
  `t_c_fkey`.
- `CREATE TABLE` is transactional: in a block, `ROLLBACK` takes it back.
- Temporary tables are written to the log like other tables (lexdb-gaps.md 2.4).
- Inside a read-only transaction, and on a replica, `CREATE TABLE` gives 25006.

## Differences from PostgreSQL

- Not supported (42601 or 0A000):
  - `LIKE source_table`, `INHERITS`, `PARTITION BY` and `PARTITION OF`, `WITH ( storage_parameter )`,
    `TABLESPACE`, `OF type_name`;
  - a table with no columns, `CREATE TABLE t ()`;
  - `EXCLUDE` constraints;
  - `UNIQUE NULLS NOT DISTINCT`;
  - `MATCH FULL` and `MATCH PARTIAL`;
  - `INCLUDE`, `WITH` and `USING INDEX TABLESPACE` on a key, and `DEFERRABLE` on a primary key or a unique
    constraint;
  - `SET NULL (column, ...)` and `SET DEFAULT (column, ...)`.
- PostgreSQL 18 lists a `NOT NULL` constraint in `pg_constraint` (`contype` n); lexdb does not (lexdb-gaps.md 2.2).
- `COLLATE` changes nothing: text compares by bytes.
- `UNLOGGED` tables are logged, and temporary tables too.
- Types not in lexdb (`json`, `jsonb`, `xml`, `money`, network and geometric types, ranges, domains) are 42704.

## Examples

### A. Columns and constraints

<!-- example: postgresql -->
```sql
CREATE TABLE customer (
    id    int PRIMARY KEY,
    email text NOT NULL UNIQUE,
    name  text,
    level int DEFAULT 1 CHECK (level BETWEEN 1 AND 5)
);
INSERT INTO customer (id, email, name) VALUES (1, 'ann@example.com', 'Ann');
SELECT * FROM customer;
\d customer
```

```text
CREATE TABLE
INSERT 0 1
 id |      email      | name | level
----+-----------------+------+-------
  1 | ann@example.com | Ann  |     1
(1 row)

              Table "public.customer"
 Column |  Type   | Collation | Nullable | Default
--------+---------+-----------+----------+---------
 id     | integer |           | not null |
 email  | text    |           | not null |
 name   | text    |           |          |
 level  | integer |           |          | 1
Indexes:
    "customer_pkey" PRIMARY KEY, btree (id)
    "customer_email_key" UNIQUE CONSTRAINT, btree (email)
Check constraints:
    "customer_level_check" CHECK ((level >= 1) AND (level <= 5))
```

### B. Table constraints and foreign keys

<!-- example: postgresql -->
```sql
CREATE TABLE orders (
    customer_id int REFERENCES customer ON DELETE CASCADE,
    line        int,
    item        text NOT NULL,
    qty         int NOT NULL,
    PRIMARY KEY (customer_id, line),
    CONSTRAINT qty_positive CHECK (qty > 0)
);
INSERT INTO orders VALUES (1, 1, 'pen', 2);
INSERT INTO orders VALUES (2, 1, 'ink', 1);
INSERT INTO orders VALUES (1, 2, 'pad', 0);
SELECT conname, contype FROM pg_constraint WHERE conrelid = 'orders'::regclass ORDER BY conname;
```

```text
CREATE TABLE
INSERT 0 1
ERROR:  insert or update on table "orders" violates foreign key constraint "orders_customer_id_fkey"
DETAIL:  Key (customer_id)=(2) is not present in table "customer".
ERROR:  new row for relation "orders" violates check constraint "qty_positive"
         conname         | contype
-------------------------+---------
 orders_customer_id_fkey | f
 orders_pkey             | p
 qty_positive            | c
(3 rows)
```

### C. Identity and serial columns

<!-- example: postgresql -->
```sql
CREATE TABLE ticket (id bigint GENERATED BY DEFAULT AS IDENTITY (START WITH 100 INCREMENT BY 10), title text);
INSERT INTO ticket (title) VALUES ('first'), ('second');
INSERT INTO ticket VALUES (1, 'mine');
SELECT * FROM ticket ORDER BY id;
CREATE TABLE note (id serial PRIMARY KEY, body text);
INSERT INTO note (body) VALUES ('a') RETURNING id;
SELECT pg_get_serial_sequence('note', 'id');
```

```text
CREATE TABLE
INSERT 0 2
INSERT 0 1
 id  | title
-----+--------
   1 | mine
 100 | first
 110 | second
(3 rows)

CREATE TABLE
 id
----
  1
(1 row)

INSERT 0 1
 pg_get_serial_sequence
------------------------
 public.note_id_seq
(1 row)
```

### D. Generated columns

<!-- example: postgresql -->
```sql
CREATE TABLE box (
    w int, h int,
    area int GENERATED ALWAYS AS (w * h) STORED,
    perimeter int GENERATED ALWAYS AS (2 * (w + h))
);
INSERT INTO box (w, h) VALUES (2, 3);
SELECT * FROM box;
INSERT INTO box (w, h, area) VALUES (1, 1, 5);
```

```text
CREATE TABLE
INSERT 0 1
 w | h | area | perimeter
---+---+------+-----------
 2 | 3 |    6 |        10
(1 row)

ERROR:  cannot insert a non-DEFAULT value into column "area"
DETAIL:  Column "area" is a generated column.
```

### E. Temporary tables

<!-- example: postgresql -->
```sql
CREATE TEMP TABLE scratch (x int) ON COMMIT DELETE ROWS;
BEGIN;
INSERT INTO scratch VALUES (1), (2);
SELECT count(*) FROM scratch;
COMMIT;
SELECT count(*) FROM scratch;
SELECT relpersistence FROM pg_class WHERE relname = 'scratch';
```

```text
CREATE TABLE
BEGIN
INSERT 0 2
 count
-------
     2
(1 row)

COMMIT
 count
-------
     0
(1 row)

 relpersistence
----------------
 t
(1 row)
```

### F. IF NOT EXISTS, and a schema

<!-- example: postgresql -->
```sql
CREATE TABLE IF NOT EXISTS customer (x int);
CREATE SCHEMA app;
CREATE TABLE app.setting (name text PRIMARY KEY, value text);
SELECT table_schema, table_name FROM information_schema.tables WHERE table_name = 'setting';
```

```text
NOTICE:  relation "customer" already exists, skipping
CREATE TABLE
CREATE SCHEMA
CREATE TABLE
 table_schema | table_name
--------------+------------
 app          | setting
(1 row)
```

### G. Constraints that are not enforced

<!-- example: postgresql -->
```sql
CREATE TABLE lot (id int PRIMARY KEY);
CREATE TABLE crate (
  id int PRIMARY KEY,
  weight int CHECK (weight > 0) NOT ENFORCED,
  lot_id int REFERENCES lot (id) NOT ENFORCED,
  CONSTRAINT crate_id_ck CHECK (id > 0)
);
INSERT INTO crate VALUES (1, -5, 99);
SELECT * FROM crate;
INSERT INTO crate VALUES (-2, 10, NULL);
SELECT conname, contype, conenforced, convalidated, pg_get_constraintdef(oid) AS definition
FROM pg_constraint WHERE conrelid = 'crate'::regclass ORDER BY conname;
SELECT constraint_name, constraint_type, enforced FROM information_schema.table_constraints
WHERE table_name = 'crate' ORDER BY constraint_name;
```

```text
CREATE TABLE
CREATE TABLE
INSERT 0 1
 id | weight | lot_id
----+--------+--------
  1 |     -5 |     99
(1 row)

ERROR:  new row for relation "crate" violates check constraint "crate_id_ck"
      conname       | contype | conenforced | convalidated |                      definition
--------------------+---------+-------------+--------------+------------------------------------------------------
 crate_id_ck        | c       | t           | t            | CHECK ((id > 0))
 crate_lot_id_fkey  | f       | f           | f            | FOREIGN KEY (lot_id) REFERENCES lot(id) NOT ENFORCED
 crate_pkey         | p       | t           | t            | PRIMARY KEY (id)
 crate_weight_check | c       | f           | f            | CHECK ((weight > 0)) NOT ENFORCED
(4 rows)

  constraint_name   | constraint_type | enforced
--------------------+-----------------+----------
 crate_id_ck        | CHECK           | YES
 crate_lot_id_fkey  | FOREIGN KEY     | NO
 crate_pkey         | PRIMARY KEY     | YES
 crate_weight_check | CHECK           | NO
(4 rows)
```

### H. Errors

<!-- example: postgresql -->
```sql
CREATE TABLE customer (x int);
CREATE TABLE dup (a int, a int);
CREATE TABLE twokeys (a int PRIMARY KEY, b int PRIMARY KEY);
CREATE TABLE copy (LIKE customer);
CREATE TABLE doc (body json);
CREATE TABLE bad (p text REFERENCES customer);
CREATE TABLE ex (a int, EXCLUDE USING gist (a WITH =));
CREATE TABLE ne1 (a int PRIMARY KEY NOT ENFORCED);
CREATE TABLE ne2 (a int, UNIQUE (a) NOT ENFORCED);
CREATE TABLE ne3 (a int CHECK (a > 0) NOT ENFORCED ENFORCED);
CREATE TABLE ne4 (a int CHECK (a > 0) NOT VALID NOT ENFORCED);
CREATE TABLE ne5 (a int CHECK (a > 0) NOT ENFORCED NOT VALID);
BEGIN READ ONLY;
CREATE TABLE ro (a int);
ROLLBACK;
```

```text
ERROR:  relation "customer" already exists
ERROR:  column "a" specified more than once
ERROR:  multiple primary keys for table "twokeys" are not allowed
ERROR:  syntax error at or near "like"
ERROR:  type "json" does not exist
ERROR:  foreign key constraint "bad_p_fkey" cannot be implemented: Key columns "p" and "id" are of incompatible types: text and integer.
ERROR:  lexdb: EXCLUDE constraints are not supported
ERROR:  misplaced NOT ENFORCED clause
ERROR:  UNIQUE constraints cannot be marked NOT ENFORCED
ERROR:  multiple ENFORCED/NOT ENFORCED clauses not allowed
ERROR:  syntax error at or near "valid"
ERROR:  syntax error at or near "valid"
BEGIN
ERROR:  cannot execute CREATE TABLE in a read-only transaction
ROLLBACK
```

### I. NOT VALID and NOT ENFORCED in a table constraint

<!-- example: postgresql -->
```sql
CREATE TABLE nv3 (a int, CHECK (a > 0) NOT VALID NOT ENFORCED);
SELECT conname, convalidated, conenforced FROM pg_constraint WHERE conrelid = 'nv3'::regclass;
```

```text
CREATE TABLE
   conname   | convalidated | conenforced
-------------+--------------+-------------
 nv3_a_check | f            | f
(1 row)
```

## See also

[CREATE TABLE AS](create-table-as.md) · [ALTER TABLE](alter-table.md) · [DROP TABLE](drop-table.md) ·
[CREATE INDEX](create-index.md) · [CREATE SEQUENCE](create-sequence.md) · [INSERT](insert.md)
