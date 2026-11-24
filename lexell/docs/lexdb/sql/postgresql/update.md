# UPDATE

Changes the values of rows of a table.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
[ WITH [ RECURSIVE ] with_query [, ...] ]
UPDATE [ ONLY ] table_name [ * ] [ [ AS ] alias ]
    SET { column_name = { expression | DEFAULT }
        | ( column_name [, ...] ) = ( { expression | DEFAULT } [, ...] ) } [, ...]
    [ FROM from_item [, ...] ]
    [ WHERE condition ]
    [ RETURNING [ WITH ( { OLD | NEW } AS output_alias [, ...] ) ]
                { * | output_expression [ [ AS ] output_name ] } [, ...] ]
    [ WITH ( batch_rows n ) ]
```

## Arguments

*with_query*
: A common table expression the statement can read. See [WITH](with.md).

*table_name*
: The table, optionally schema-qualified. `ONLY` and `*` are accepted and change nothing: lexdb has no
  inheritance. A view cannot be updated.

*alias*
: A name for the table in the rest of the statement. With an alias, the table's own name is not visible.

*column_name*
: A column of the table, named without the table's name or alias. A column may be set once.

*expression*
: The new value. It is computed from the row as it was before the statement, so `SET a = b, b = a` swaps two
  columns. `DEFAULT` gives the column's default (NULL if it has none).

`( column_name, ... ) = ( expression, ... )`
: Sets several columns at once.

`FROM` *from_item*
: Other tables (or subqueries, functions, joins) whose columns `SET`, `WHERE` and `RETURNING` can use. Join them to
  the target in `WHERE`. A target row that several `FROM` rows match is updated once, with one of them.

`WHERE` *condition*
: The rows to change. Without it, every row of the table is changed.

`RETURNING`
: Returns the updated rows, like a `SELECT` list. `*` and plain column names give the new values. `old.column` and
  `new.column` (PostgreSQL 18) give the value before and after; `WITH (OLD AS o, NEW AS n)` renames them. Without
  `RETURNING` the command tag is `UPDATE n`.

`WITH ( batch_rows n )`
: lexdb's own: commits each *n* rows as a transaction of its own, so a large update holds the writes of *n* rows,
  not all of them. See the remarks.

## Remarks

- Each new value is converted to the column's type as an assignment (a `numeric(10,2)` rounds, a value too long for
  a `varchar(n)` is 22001), and `NOT NULL`, `CHECK`, unique and foreign key constraints are checked for every row.
  Generated columns are computed again.
- An `UPDATE` is one statement: all its rows change, or none do.
- A subquery in `SET` or `RETURNING` sees the table as it was when the statement began, not the rows the statement
  has already changed (example F). The same holds in the SQL Server and Oracle doors.
- A primary key may be updated. A foreign key's `ON UPDATE` action runs for the rows that reference it.
- An `UPDATE` waits for the row locks other transactions hold on its rows, then finds its rows again, reading what
  they committed. In a transaction block it keeps a lock on each row it changes until the block ends (`FOR NO KEY
  UPDATE`, or `FOR UPDATE` when a key changes), so another transaction's `UPDATE` or `SELECT ... FOR UPDATE` of the
  row waits for the block.
- Inside a read-only transaction, and on a replica, `UPDATE` gives 25006.
- With `batch_rows`:
  - the rows go in order of the primary key, and a batch that fails keeps the batches committed before it; the
    error's context says how many rows were committed;
  - it cannot run inside a transaction block (25001), and cannot have `RETURNING` or `FROM`, or assign a
    primary key column (0A000).

## Differences from PostgreSQL

- `SET ( column_name, ... ) = ( SELECT ... )`, a sub-select that sets several columns, is a syntax error. Set each
  column from its own scalar subquery instead.
- `WHERE CURRENT OF cursor_name` is not supported: lexdb has no cursors.
- Views are not updatable, so `UPDATE` of a view is refused.
- `WITH ( batch_rows n )` is lexdb's, not PostgreSQL's.
- There are no triggers and no rules.

## Examples

<!--setup: postgresql
CREATE TABLE product (id int PRIMARY KEY, name text NOT NULL, price numeric(10,2) DEFAULT 0 CHECK (price >= 0), stock int DEFAULT 0);
INSERT INTO product VALUES (1, 'pencil', 0.50, 100), (2, 'eraser', 0.75, 40), (3, 'ruler', 1.20, 0), (4, 'stapler', 6.40, 5);
CREATE TABLE delivery (product_id int, qty int);
INSERT INTO delivery VALUES (1, 50), (3, 20), (9, 10);
-->

The examples use two tables:

```sql
CREATE TABLE product (id int PRIMARY KEY, name text NOT NULL,
                      price numeric(10,2) DEFAULT 0 CHECK (price >= 0), stock int DEFAULT 0);
INSERT INTO product VALUES (1, 'pencil', 0.50, 100), (2, 'eraser', 0.75, 40), (3, 'ruler', 1.20, 0),
  (4, 'stapler', 6.40, 5);
CREATE TABLE delivery (product_id int, qty int);
INSERT INTO delivery VALUES (1, 50), (3, 20), (9, 10);
```

### A. Change some rows

<!-- example: postgresql -->
```sql
UPDATE product SET price = price * 1.10 WHERE id = 1;
UPDATE product SET stock = stock + 1, name = upper(name) WHERE price > 1;
SELECT * FROM product ORDER BY id;
```

```text
UPDATE 1
UPDATE 2
 id |  name   | price | stock
----+---------+-------+-------
  1 | pencil  |  0.55 |   100
  2 | eraser  |  0.75 |    40
  3 | RULER   |  1.20 |     1
  4 | STAPLER |  6.40 |     6
(4 rows)
```

### B. Several columns, and DEFAULT

<!-- example: postgresql -->
```sql
UPDATE product SET (price, stock) = (1.00, DEFAULT) WHERE id = 2;
SELECT * FROM product WHERE id = 2;
```

```text
UPDATE 1
 id |  name  | price | stock
----+--------+-------+-------
  2 | eraser |  1.00 |     0
(1 row)
```

### C. RETURNING, with OLD and NEW

<!-- example: postgresql -->
```sql
UPDATE product SET price = price + 0.25 WHERE id IN (1, 2)
RETURNING id, old.price AS was, new.price AS now;
```

```text
 id | was  | now
----+------+------
  1 | 0.55 | 0.80
  2 | 1.00 | 1.25
(2 rows)

UPDATE 2
```

### D. Values from another table

<!-- example: postgresql -->
```sql
UPDATE product p SET stock = p.stock + d.qty
FROM delivery d
WHERE d.product_id = p.id
RETURNING p.id, p.name, p.stock;
```

```text
 id |  name  | stock
----+--------+-------
  1 | pencil |   150
  3 | RULER  |    21
(2 rows)

UPDATE 2
```

### E. A value from a subquery

<!-- example: postgresql -->
```sql
UPDATE product SET price = (SELECT max(price) FROM product) WHERE id = 3 RETURNING id, price;
```

```text
 id | price
----+-------
  3 |  6.40
(1 row)

UPDATE 1
```

### F. A subquery sees the starting rows

Each employee takes twice the pay of the manager. The managers are updated in the same statement, but the subquery
reads their old pay, and so does the one in `RETURNING` (`rows_paid_400` is the one row that had 400 when the
statement began).

<!-- example: postgresql -->
```sql
CREATE TABLE staff (id int PRIMARY KEY, boss int, pay int);
INSERT INTO staff VALUES (1, NULL, 100), (2, 1, 200), (3, 2, 300), (4, 3, 400);
UPDATE staff s SET pay = (SELECT b.pay * 2 FROM staff b WHERE b.id = s.boss) WHERE boss IS NOT NULL
RETURNING s.id, s.pay, (SELECT count(*) FROM staff x WHERE x.pay = 400) AS rows_paid_400;
SELECT id, pay FROM staff ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 4
 id | pay | rows_paid_400
----+-----+---------------
  2 | 200 |             1
  3 | 400 |             1
  4 | 600 |             1
(3 rows)

UPDATE 3
 id | pay
----+-----
  1 | 100
  2 | 200
  3 | 400
  4 | 600
(4 rows)
```

### G. In batches

<!-- example: postgresql -->
```sql
UPDATE product SET stock = 0 WITH (batch_rows 2);
BEGIN;
UPDATE product SET stock = 1 WITH (batch_rows 2);
ROLLBACK;
UPDATE product SET id = id + 10 WITH (batch_rows 2);
```

```text
UPDATE 4
BEGIN
ERROR:  lexdb: UPDATE with batch_rows cannot run inside a transaction block
ROLLBACK
ERROR:  lexdb: UPDATE with batch_rows cannot assign a primary key column
CONTEXT:  UPDATE with batch_rows 2: 0 rows committed before the error
```

### H. Errors

A constraint error stops the statement, and no row is changed.

<!-- example: postgresql -->
```sql
UPDATE product SET price = price - 1;
UPDATE product SET nosuch = 1;
UPDATE product SET (price, stock) = (SELECT 1.00, 5);
SELECT id, price FROM product ORDER BY id;
```

```text
ERROR:  new row for relation "product" violates check constraint "product_price_check"
ERROR:  column "nosuch" of relation "product" does not exist
ERROR:  syntax error at or near "select"
 id | price
----+-------
  1 |  0.80
  2 |  1.25
  3 |  6.40
  4 |  6.40
(4 rows)
```

## See also

[INSERT](insert.md) · [DELETE](delete.md) · [MERGE](merge.md) · [SELECT](select.md) · [WITH](with.md)
