# TRUNCATE

Empties one or more tables.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
TRUNCATE [ TABLE ] [ ONLY ] name [ * ] [, ... ]
    [ RESTART IDENTITY | CONTINUE IDENTITY ] [ CASCADE | RESTRICT ]
```

## Arguments

*name*
: A table, optionally schema-qualified. `ONLY` and `*` are accepted and change nothing: lexdb has no inheritance.

`RESTART IDENTITY`
: Restarts the sequences that the tables' columns own (`serial` and identity columns) at their start values.

`CONTINUE IDENTITY`
: Leaves the sequences as they are. This is the default.

`CASCADE`
: Also empties every table that references one of these by a foreign key, and the tables that reference those.

`RESTRICT`
: Refuses to empty a table that another table not listed references. This is the default.

## Remarks

- `TRUNCATE` gives each table and each of its indexes a new, empty tree and frees the old one, without reading the
  rows. It takes the same short time for any number of rows.
- It is transactional: in a transaction block, `ROLLBACK` brings the rows back.
- It needs the `TRUNCATE` privilege on each table, including those `CASCADE` adds.
- A table referenced by a foreign key from a table not being emptied is refused (0A000), whether or not any rows
  refer to it.
- The command tag is `TRUNCATE TABLE`.
- Inside a read-only transaction, and on a replica, `TRUNCATE` gives 25006.

## Differences from PostgreSQL

- The foreign key error carries PostgreSQL's `DETAIL` and `HINT` in its message (lexdb-gaps.md 2.4).
- `CASCADE` gives no `NOTICE` naming the tables it adds.
- There are no triggers, so no `ON TRUNCATE` triggers run.

## Examples

<!--setup: postgresql
CREATE TABLE customer (id serial PRIMARY KEY, name text);
CREATE TABLE orders (id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY, customer_id int REFERENCES customer, item text);
INSERT INTO customer (name) VALUES ('ann'), ('bob');
INSERT INTO orders (customer_id, item) VALUES (1, 'pen'), (2, 'ink');
-->

The examples use two tables:

```sql
CREATE TABLE customer (id serial PRIMARY KEY, name text);
CREATE TABLE orders (id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY, customer_id int REFERENCES customer,
                     item text);
INSERT INTO customer (name) VALUES ('ann'), ('bob');
INSERT INTO orders (customer_id, item) VALUES (1, 'pen'), (2, 'ink');
```

### A. Rolled back

<!-- example: postgresql -->
```sql
BEGIN;
TRUNCATE orders;
SELECT count(*) FROM orders;
ROLLBACK;
SELECT count(*) FROM orders;
```

```text
BEGIN
TRUNCATE TABLE
 count
-------
     0
(1 row)

ROLLBACK
 count
-------
     2
(1 row)
```

### B. A table that another references

<!-- example: postgresql -->
```sql
TRUNCATE customer;
TRUNCATE customer, orders;
SELECT (SELECT count(*) FROM customer) AS customers, (SELECT count(*) FROM orders) AS orders;
```

```text
ERROR:  cannot truncate a table referenced in a foreign key constraint: Table "orders" references "customer". Truncate table "orders" at the same time, or use TRUNCATE ... CASCADE.
TRUNCATE TABLE
 customers | orders
-----------+--------
         0 |      0
(1 row)
```

### C. RESTART IDENTITY

<!-- example: postgresql -->
```sql
INSERT INTO customer (name) VALUES ('cy') RETURNING id;
TRUNCATE customer CASCADE;
INSERT INTO customer (name) VALUES ('dee') RETURNING id;
TRUNCATE customer, orders RESTART IDENTITY;
INSERT INTO customer (name) VALUES ('eve') RETURNING id;
```

```text
 id
----
  3
(1 row)

INSERT 0 1
TRUNCATE TABLE
 id
----
  4
(1 row)

INSERT 0 1
TRUNCATE TABLE
 id
----
  1
(1 row)

INSERT 0 1
```

### D. Errors

<!-- example: postgresql -->
```sql
TRUNCATE nosuch;
CREATE VIEW names AS SELECT name FROM customer;
TRUNCATE names;
```

```text
ERROR:  relation "nosuch" does not exist
CREATE VIEW
ERROR:  "names" is not a table
```

## See also

[DELETE](delete.md) · CREATE TABLE · CREATE SEQUENCE
