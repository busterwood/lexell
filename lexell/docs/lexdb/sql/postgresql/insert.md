# INSERT

Adds rows to a table.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18 (and 19's `ON CONFLICT DO SELECT`).

## Syntax

```
[ WITH with_query [, ...] ]
INSERT INTO table_name [ AS alias ] [ ( column_name [, ...] ) ]
    [ OVERRIDING { SYSTEM | USER } VALUE ]
    { DEFAULT VALUES
    | VALUES ( { expression | DEFAULT } [, ...] ) [, ...]
    | query }
    [ ON CONFLICT [ conflict_target ] conflict_action ]
    [ RETURNING [ WITH ( { OLD | NEW } AS output_alias [, ...] ) ]
                { * | output_expression [ [ AS ] output_name ] } [, ...] ]

conflict_target:
    ( column_name [, ...] ) [ WHERE index_predicate ]
    | ON CONSTRAINT constraint_name

conflict_action:
    DO NOTHING
    | DO UPDATE SET { column_name = { expression | DEFAULT }
                    | ( column_name [, ...] ) = ( { expression | DEFAULT } [, ...] ) } [, ...]
                [ WHERE condition ]
    | DO SELECT [ FOR { UPDATE | NO KEY UPDATE | SHARE | KEY SHARE } ] [ WHERE condition ]
```

## Arguments

*with_query*
: A common table expression the query can read. See [WITH](with.md).

*table_name*
: The table, optionally schema-qualified (`app.orders`). A view cannot be inserted into.

*alias*
: A name for the table in `ON CONFLICT` and `RETURNING`. With an alias, the table's own name is not visible there.

*column_name*
: The columns the values go to, in order. Columns left out get their default, or NULL. Each column may be named
  once.

`OVERRIDING SYSTEM VALUE`
: Lets a value be given for a `GENERATED ALWAYS AS IDENTITY` column.

`OVERRIDING USER VALUE`
: Ignores the values given for an identity column; the column takes its next value.

`DEFAULT VALUES`
: One row, every column its default.

`VALUES`
: One or more rows. `DEFAULT` in a row gives that column its default.

*query*
: A `SELECT` (or `VALUES`, or a query in parentheses) whose rows are inserted. Its columns must match the column
  list in number, and each value is converted to its column's type as an assignment.

`ON CONFLICT`
: What to do with a row that would break a unique constraint or unique index.
  - *conflict_target* names the unique index by its columns, or the constraint by name. Without it, `DO NOTHING`
    covers every unique index.
  - `DO NOTHING` skips the row.
  - `DO UPDATE` updates the existing row instead. In `SET` and `WHERE`, the existing row is the table (or its
    alias) and the proposed row is `EXCLUDED`. A row the `WHERE` excludes is left as it is.
  - `DO SELECT` (PostgreSQL 19) leaves the existing row as it is and returns it through `RETURNING`.

`RETURNING`
: Returns rows from the inserted (or updated) rows, like a `SELECT` list. `WITH (OLD AS o, NEW AS n)` names the row
  before and after an `ON CONFLICT DO UPDATE`; `old` and `new` are the default names. Without `RETURNING` the
  command tag is `INSERT 0 n`.

## Remarks

- A column's value is converted to its type as an assignment: a `numeric(10,2)` rounds to two places, and a value
  too long for `varchar(n)` is error 22001.
- Defaults, sequences and identity columns, `NOT NULL`, `CHECK`, unique and foreign key constraints are checked for
  every row. Foreign keys are checked at the end of the statement.
- An `INSERT` is one statement: all its rows go in, or none do.
- `INSERT ... SELECT` streams the query's rows into the table; it does not hold the query's result first.
- In a serializable transaction (every read-write transaction in lexdb), two transactions that insert the same key
  conflict: the second gets 23505, or 40001 when the first has not committed yet.
- Inside a read-only transaction, and on a replica, `INSERT` gives 25006.
- Many rows load faster with [COPY](copy.md) than with `INSERT`.

## Differences from PostgreSQL

- A duplicate key's `DETAIL` (`Key (id)=(1) already exists.`) is a separate field, as in PostgreSQL; for some other
  errors lexdb puts the detail in the message (lexdb-gaps.md 2.4).
- The `WHERE index_predicate` of a conflict target is read and not used: the unique index is chosen by its columns.
- Data-modifying statements in `WITH` (`WITH d AS (DELETE ... RETURNING ...) INSERT ...`) are not supported
  (lexdb-gaps.md 2.2).
- Views are not updatable, so `INSERT` into a view is refused.
- There are no triggers and no rules.

## Examples

<!--setup: postgresql
CREATE TABLE product (id int PRIMARY KEY, name text NOT NULL, price numeric(10,2) DEFAULT 0 CHECK (price >= 0), stock int DEFAULT 0);
-->

### A. Insert one row, and several rows

<!-- example: postgresql -->
```sql
INSERT INTO product VALUES (1, 'pencil', 0.50, 100);
INSERT INTO product (id, name, price) VALUES (2, 'eraser', 0.75), (3, 'ruler', 1.20);
SELECT * FROM product ORDER BY id;
```

```text
INSERT 0 1
INSERT 0 2
 id |  name  | price | stock
----+--------+-------+-------
  1 | pencil |  0.50 |   100
  2 | eraser |  0.75 |     0
  3 | ruler  |  1.20 |     0
(3 rows)
```

### B. Defaults

`DEFAULT` gives one column its default; `DEFAULT VALUES` gives every column its default.

<!-- example: postgresql -->
```sql
CREATE TABLE note (id serial PRIMARY KEY, body text DEFAULT 'empty', made date DEFAULT DATE '2026-01-01');
INSERT INTO note (body, made) VALUES ('first', DEFAULT);
INSERT INTO note DEFAULT VALUES;
SELECT * FROM note ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 1
INSERT 0 1
 id | body  |    made
----+-------+------------
  1 | first | 2026-01-01
  2 | empty | 2026-01-01
(2 rows)
```

### C. Insert the rows of a query

<!-- example: postgresql -->
```sql
CREATE TABLE cheap (id int PRIMARY KEY, name text);
INSERT INTO cheap SELECT id, upper(name) FROM product WHERE price < 1;
SELECT * FROM cheap ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 2
 id |  name
----+--------
  1 | PENCIL
  2 | ERASER
(2 rows)
```

### D. RETURNING

<!-- example: postgresql -->
```sql
INSERT INTO product (id, name, price) VALUES (4, 'stapler', 6.40)
RETURNING id, name, price * 1.2 AS with_tax;
```

```text
 id |  name   | with_tax
----+---------+----------
  4 | stapler |    7.680
(1 row)

INSERT 0 1
```

### E. Upsert with ON CONFLICT

`DO NOTHING` skips a row whose key is taken; `DO UPDATE` changes the existing row, and `EXCLUDED` is the row that
was proposed.

<!-- example: postgresql -->
```sql
INSERT INTO product (id, name) VALUES (1, 'pen') ON CONFLICT DO NOTHING;
INSERT INTO product AS p (id, name, stock) VALUES (1, 'pencil', 50), (5, 'glue', 10)
ON CONFLICT (id) DO UPDATE SET stock = p.stock + EXCLUDED.stock
RETURNING id, name, stock;
```

```text
INSERT 0 0
 id |  name  | stock
----+--------+-------
  1 | pencil |   150
  5 | glue   |    10
(2 rows)

INSERT 0 2
```

### F. OLD and NEW in RETURNING

<!-- example: postgresql -->
```sql
INSERT INTO product (id, name, price) VALUES (2, 'eraser', 0.90)
ON CONFLICT (id) DO UPDATE SET price = EXCLUDED.price
RETURNING old.price AS old_price, new.price AS new_price;
```

```text
 old_price | new_price
-----------+-----------
      0.75 |      0.90
(1 row)

INSERT 0 1
```

### G. ON CONFLICT DO SELECT

`DO SELECT` returns the row that is already there, so one statement gives the row's key whether it was inserted or
not.

<!-- example: postgresql -->
```sql
INSERT INTO product (id, name) VALUES (3, 'ruler'), (9, 'compass')
ON CONFLICT (id) DO SELECT
RETURNING id, name, price;
```

```text
 id |  name   | price
----+---------+-------
  3 | ruler   |  1.20
  9 | compass |  0.00
(2 rows)

INSERT 0 2
```

### H. Identity columns and OVERRIDING

<!-- example: postgresql -->
```sql
CREATE TABLE ticket (id int GENERATED ALWAYS AS IDENTITY PRIMARY KEY, title text);
INSERT INTO ticket (title) VALUES ('first');
INSERT INTO ticket (id, title) VALUES (100, 'mine');
INSERT INTO ticket (id, title) OVERRIDING SYSTEM VALUE VALUES (100, 'mine');
SELECT * FROM ticket ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 1
ERROR:  cannot insert a non-DEFAULT value into column "id"
DETAIL:  Column "id" is an identity column defined as GENERATED ALWAYS.
HINT:  Use OVERRIDING SYSTEM VALUE to override.
INSERT 0 1
 id  | title
-----+-------
   1 | first
 100 | mine
(2 rows)
```

### I. Errors

A constraint error stops the statement, and none of its rows are inserted.

<!-- example: postgresql -->
```sql
INSERT INTO product (id, name, price) VALUES (6, 'tape', 1.00), (7, 'clip', -1);
INSERT INTO product (id, name) VALUES (8, NULL);
INSERT INTO product (id, name) VALUES (1, 'again');
SELECT count(*) FROM product WHERE id IN (6, 7, 8);
```

```text
ERROR:  new row for relation "product" violates check constraint "product_price_check"
ERROR:  null value in column "name" of relation "product" violates not-null constraint
DETAIL:  Failing row contains (8, null, 0.00, 0).
ERROR:  duplicate key value violates unique constraint "product_pkey"
DETAIL:  Key (id)=(1) already exists.
 count
-------
     0
(1 row)
```

## See also

[UPDATE](update.md) · [DELETE](delete.md) · [MERGE](merge.md) · [COPY](copy.md) · [CREATE TABLE](create-table.md) ·
[SELECT](select.md) · [WITH](with.md) · [Bulk loading](../../bulk-load.md)
