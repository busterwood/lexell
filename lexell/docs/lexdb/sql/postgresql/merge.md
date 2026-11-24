# MERGE

Inserts, updates or deletes the rows of a table by joining it to a source.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
[ WITH [ RECURSIVE ] with_query [, ...] ]
MERGE INTO target_table [ [ AS ] target_alias ]
    USING data_source ON join_condition
    when_clause [...]
    [ RETURNING [ WITH ( { OLD | NEW } AS output_alias [, ...] ) ]
                { * | output_expression [ [ AS ] output_name ] } [, ...] ]

data_source:
    { source_table | ( source_query ) | ( VALUES ... ) } [ [ AS ] source_alias [ ( column_alias [, ...] ) ] ]

when_clause:
    WHEN MATCHED [ AND condition ] THEN { merge_update | DELETE | DO NOTHING }
    | WHEN NOT MATCHED BY SOURCE [ AND condition ] THEN { merge_update | DELETE | DO NOTHING }
    | WHEN NOT MATCHED [ BY TARGET ] [ AND condition ] THEN { merge_insert | DO NOTHING }

merge_update:
    UPDATE SET { column_name = { expression | DEFAULT }
               | ( column_name [, ...] ) = ( { expression | DEFAULT } [, ...] ) } [, ...]

merge_insert:
    INSERT [ ( column_name [, ...] ) ] [ OVERRIDING { SYSTEM | USER } VALUE ]
        { VALUES ( { expression | DEFAULT } [, ...] ) | DEFAULT VALUES }
```

## Arguments

*target_table*
: The table to change, optionally schema-qualified. It cannot be a view.

*data_source*
: A table, a subquery, `VALUES` or a common table expression: the rows to merge.

*join_condition*
: Pairs source rows with target rows. A source row that pairs with a target row is *matched*.

`WHEN MATCHED`
: For a source row with a target row. `UPDATE SET` changes the target row (with no table name before the
  columns); `DELETE` removes it.

`WHEN NOT MATCHED BY SOURCE`
: For a target row that no source row pairs with. Its `AND` condition and `UPDATE` may use the target's columns
  only.

`WHEN NOT MATCHED [ BY TARGET ]`
: For a source row with no target row. `INSERT` adds a row; its values may use the source's columns only.

`AND` *condition*
: The clause applies only when the condition is true. For each row, the first clause of its kind whose condition is
  true runs; if none is, the row is left alone.

`DO NOTHING`
: Leaves the row alone.

`RETURNING`
: Returns a row for each row inserted, updated or deleted. `merge_action()` gives `INSERT`, `UPDATE` or `DELETE`.
  The target's columns are the new row's (the old one's for a delete); `old.` and `new.` name each, and the
  source's columns can be returned too. Without `RETURNING` the command tag is `MERGE n`, the rows changed.

## Remarks

- A target row may be changed by one source row only: a second gives 21000 (`MERGE command cannot affect row a
  second time`), and nothing is changed.
- Constraints, defaults, identity columns and foreign keys apply to the rows as in `INSERT`, `UPDATE` and `DELETE`.
- A `MERGE` is one statement: all its changes are made, or none are.
- A subquery in a `WHEN` condition, in `SET` or in `VALUES` reads the tables as the statement found them: it does not
  see the rows the same `MERGE` has already changed (example F).
- `EXPLAIN MERGE` shows the join that pairs the rows.
- Inside a read-only transaction, and on a replica, `MERGE` gives 25006.

## Differences from PostgreSQL

- `MERGE INTO ONLY t` is a syntax error. lexdb has no inheritance; write `MERGE INTO t`.
- The target cannot be a view (views are not updatable).
- `WITH ( batch_rows n )` is not taken by `MERGE`.
- There are no triggers and no rules.

## Examples

<!--setup: postgresql
CREATE TABLE product (id int PRIMARY KEY, name text NOT NULL, price numeric(10,2) DEFAULT 0, stock int DEFAULT 0);
INSERT INTO product VALUES (1, 'pencil', 0.50, 100), (2, 'eraser', 0.75, 40), (3, 'ruler', 1.20, 0), (4, 'stapler', 6.40, 5);
CREATE TABLE delivery (product_id int, name text, qty int, price numeric(10,2));
INSERT INTO delivery VALUES (1, 'pencil', 50, 0.55), (3, 'ruler', 0, NULL), (9, 'glue', 10, 2.00);
-->

The examples use two tables:

```sql
CREATE TABLE product (id int PRIMARY KEY, name text NOT NULL, price numeric(10,2) DEFAULT 0, stock int DEFAULT 0);
INSERT INTO product VALUES (1, 'pencil', 0.50, 100), (2, 'eraser', 0.75, 40), (3, 'ruler', 1.20, 0),
  (4, 'stapler', 6.40, 5);
CREATE TABLE delivery (product_id int, name text, qty int, price numeric(10,2));
INSERT INTO delivery VALUES (1, 'pencil', 50, 0.55), (3, 'ruler', 0, NULL), (9, 'glue', 10, 2.00);
```

### A. Update, delete or insert

A delivery of 0 removes the product; others add stock, and a new product is inserted.

<!-- example: postgresql -->
```sql
BEGIN;
MERGE INTO product p
USING delivery d ON p.id = d.product_id
WHEN MATCHED AND d.qty = 0 THEN DELETE
WHEN MATCHED THEN UPDATE SET stock = p.stock + d.qty, price = coalesce(d.price, p.price)
WHEN NOT MATCHED THEN INSERT (id, name, price, stock) VALUES (d.product_id, d.name, d.price, d.qty);
SELECT * FROM product ORDER BY id;
ROLLBACK;
```

```text
BEGIN
MERGE 3
 id |  name   | price | stock
----+---------+-------+-------
  1 | pencil  |  0.55 |   150
  2 | eraser  |  0.75 |    40
  4 | stapler |  6.40 |     5
  9 | glue    |  2.00 |    10
(4 rows)

ROLLBACK
```

### B. RETURNING and merge_action()

<!-- example: postgresql -->
```sql
BEGIN;
MERGE INTO product p
USING delivery d ON p.id = d.product_id
WHEN MATCHED AND d.qty = 0 THEN DELETE
WHEN MATCHED THEN UPDATE SET stock = p.stock + d.qty
WHEN NOT MATCHED THEN INSERT (id, name, stock) VALUES (d.product_id, d.name, d.qty)
RETURNING merge_action(), p.id, d.name, old.stock AS was, new.stock AS now;
ROLLBACK;
```

```text
BEGIN
 merge_action | id |  name  | was | now
--------------+----+--------+-----+-----
 UPDATE       |  1 | pencil | 100 | 150
 DELETE       |  3 | ruler  |   0 |
 INSERT       |  9 | glue   |     |  10
(3 rows)

MERGE 3
ROLLBACK
```

### C. NOT MATCHED BY SOURCE

The products that the delivery does not name are set to no stock.

<!-- example: postgresql -->
```sql
BEGIN;
MERGE INTO product p
USING delivery d ON p.id = d.product_id
WHEN NOT MATCHED BY SOURCE THEN UPDATE SET stock = 0
WHEN NOT MATCHED BY TARGET THEN DO NOTHING;
SELECT id, stock FROM product ORDER BY id;
ROLLBACK;
```

```text
BEGIN
MERGE 2
 id | stock
----+-------
  1 |   100
  2 |     0
  3 |     0
  4 |     0
(4 rows)

ROLLBACK
```

### D. A source of VALUES

<!-- example: postgresql -->
```sql
MERGE INTO product p
USING (VALUES (4, 'stapler', 7.00), (10, 'tape', 0.90)) AS s(id, name, price) ON p.id = s.id
WHEN MATCHED THEN UPDATE SET price = s.price
WHEN NOT MATCHED THEN INSERT (id, name, price) VALUES (s.id, s.name, s.price);
SELECT * FROM product WHERE id IN (4, 10) ORDER BY id;
```

```text
MERGE 2
 id |  name   | price | stock
----+---------+-------+-------
  4 | stapler |  7.00 |     5
 10 | tape    |  0.90 |     0
(2 rows)
```

### E. WITH before MERGE

<!-- example: postgresql -->
```sql
WITH s AS (SELECT 4 AS id, 99 AS n)
MERGE INTO product p USING s ON p.id = s.id
WHEN MATCHED THEN UPDATE SET stock = s.n
RETURNING p.id, p.stock;
```

```text
 id | stock
----+-------
  4 |    99
(1 row)

MERGE 1
```

### F. A subquery reads the rows as the statement found them

The subquery sums the stock of the whole table. Both matched rows get the same total, the one before the statement
changed anything.

<!-- example: postgresql -->
```sql
SELECT sum(stock) AS total_before FROM product;
BEGIN;
MERGE INTO product p
USING delivery d ON p.id = d.product_id
WHEN MATCHED THEN UPDATE SET stock = (SELECT sum(stock) FROM product);
SELECT id, stock FROM product ORDER BY id;
ROLLBACK;
```

```text
 total_before
--------------
          239
(1 row)

BEGIN
MERGE 2
 id | stock
----+-------
  1 |   239
  2 |    40
  3 |   239
  4 |    99
 10 |     0
(5 rows)

ROLLBACK
```

### G. Errors

<!-- example: postgresql -->
```sql
MERGE INTO product p USING (VALUES (1), (1)) AS s(id) ON p.id = s.id
WHEN MATCHED THEN UPDATE SET stock = stock + 1;
SELECT stock FROM product WHERE id = 1;
CREATE VIEW cheap AS SELECT * FROM product WHERE price < 1;
MERGE INTO cheap c USING delivery d ON c.id = d.product_id WHEN MATCHED THEN DELETE;
```

```text
ERROR:  MERGE command cannot affect row a second time
HINT:  Ensure that not more than one source row matches any one target row.
 stock
-------
   100
(1 row)

CREATE VIEW
ERROR:  cannot merge into view "cheap" (lexdb's views are read-only)
```

## See also

[INSERT](insert.md) · [UPDATE](update.md) · [DELETE](delete.md) · [WITH](with.md)
