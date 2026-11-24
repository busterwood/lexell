# DELETE

Removes rows from a table.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
[ WITH [ RECURSIVE ] with_query [, ...] ]
DELETE FROM [ ONLY ] table_name [ * ] [ [ AS ] alias ]
    [ USING from_item [, ...] ]
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
  inheritance. A view cannot be deleted from.

*alias*
: A name for the table in the rest of the statement.

`USING` *from_item*
: Other tables (or subqueries, functions, joins) whose columns `WHERE` and `RETURNING` can use. A row is deleted if
  it joins to any of their rows.

`WHERE` *condition*
: The rows to delete. Without it, every row of the table is deleted.

`RETURNING`
: Returns the deleted rows, like a `SELECT` list. `old.column` is the deleted value; `new.column` is NULL. Without
  `RETURNING` the command tag is `DELETE n`.

`WITH ( batch_rows n )`
: lexdb's own: commits each *n* rows as a transaction of its own. See the remarks.

## Remarks

- Foreign keys that reference the table are checked, and their `ON DELETE` actions (`CASCADE`, `SET NULL`, `SET
  DEFAULT`) run, for every row deleted.
- A `DELETE` is one statement: all its rows go, or none do.
- **A range of the primary key is removed whole.** A `DELETE` whose `WHERE` is only a range of the primary key's
  leading columns (`id < 1000`, `day BETWEEN ... AND ...`, `region = 'x' AND id < 10`), or that has no `WHERE`,
  drops the parts of the table's tree the range covers without reading their rows, when:
  - no foreign key references the table, and its key is not of a floating-point type;
  - the statement has no `USING` and no `RETURNING`, and is not a lookup of one row by the whole key;
  - no other transaction holds a lock on a row in the range;
  - `lexdb_range_delete` is on (the default).

  It is one small write to the log whatever the number of rows. An index that leads with the same columns is cut by
  range too; the entries of other indexes are deleted one by one. `EXPLAIN` shows `range delete` when a `DELETE`
  takes this path. To remove a whole table's rows, see also [TRUNCATE](truncate.md).
- **Batches.** With `batch_rows n`, the statement deletes *n* rows, commits, and goes on, so a large delete by a
  column that is not the key holds *n* rows' writes and not all of them. It is not atomic: a failure keeps the
  batches committed before it, and its context says how many rows were committed. It cannot run inside a
  transaction block (25001), and cannot have `RETURNING` or `USING` (0A000). A delete that takes the range path
  ignores `batch_rows`.
- In a transaction block, a `DELETE` keeps a `FOR UPDATE` lock on each row it deletes until the block ends.
- A subquery in `WHERE` or `RETURNING` sees the table as it was when the statement began, not the rows the statement
  has already deleted.
- Inside a read-only transaction, and on a replica, `DELETE` gives 25006.

## Differences from PostgreSQL

- `WHERE CURRENT OF cursor_name` is not supported: lexdb has no cursors.
- Views are not updatable, so `DELETE` from a view is refused.
- The range path and `WITH ( batch_rows n )` are lexdb's own. A deleted row's space is reused at once: there is no
  `VACUUM` to run.
- There are no triggers and no rules.

## Examples

<!--setup: postgresql
CREATE TABLE product (id int PRIMARY KEY, name text NOT NULL, price numeric(10,2), stock int);
INSERT INTO product VALUES (1, 'pencil', 0.50, 100), (2, 'eraser', 0.75, 40), (3, 'ruler', 1.20, 0), (4, 'stapler', 6.40, 5), (5, 'glue', 2.10, 0);
CREATE TABLE discontinued (product_id int);
INSERT INTO discontinued VALUES (2), (9);
-->

The examples use two tables:

```sql
CREATE TABLE product (id int PRIMARY KEY, name text NOT NULL, price numeric(10,2), stock int);
INSERT INTO product VALUES (1, 'pencil', 0.50, 100), (2, 'eraser', 0.75, 40), (3, 'ruler', 1.20, 0),
  (4, 'stapler', 6.40, 5), (5, 'glue', 2.10, 0);
CREATE TABLE discontinued (product_id int);
INSERT INTO discontinued VALUES (2), (9);
```

### A. Delete some rows

<!-- example: postgresql -->
```sql
DELETE FROM product WHERE stock = 0 AND price > 2;
SELECT id, name FROM product ORDER BY id;
```

```text
DELETE 1
 id |  name
----+---------
  1 | pencil
  2 | eraser
  3 | ruler
  4 | stapler
(4 rows)
```

### B. RETURNING

<!-- example: postgresql -->
```sql
DELETE FROM product WHERE stock = 0 RETURNING id, name, old.price;
```

```text
 id | name  | price
----+-------+-------
  3 | ruler |  1.20
(1 row)

DELETE 1
```

### C. USING another table

<!-- example: postgresql -->
```sql
DELETE FROM product p USING discontinued d WHERE d.product_id = p.id RETURNING p.id, p.name;
```

```text
 id |  name
----+--------
  2 | eraser
(1 row)

DELETE 1
```

### D. A subquery in WHERE

<!-- example: postgresql -->
```sql
INSERT INTO product VALUES (6, 'tape', 0.90, 12), (7, 'clip', 0.10, 500);
DELETE FROM product WHERE price < (SELECT avg(price) FROM product) AND id > 5;
SELECT id, name FROM product ORDER BY id;
```

```text
INSERT 0 2
DELETE 2
 id |  name
----+---------
  1 | pencil
  4 | stapler
(2 rows)
```

### E. Foreign keys

<!-- example: postgresql -->
```sql
CREATE TABLE orders (id int PRIMARY KEY, product_id int REFERENCES product ON DELETE CASCADE);
CREATE TABLE review (id int PRIMARY KEY, product_id int REFERENCES product);
INSERT INTO orders VALUES (1, 1), (2, 4);
INSERT INTO review VALUES (1, 4);
DELETE FROM product WHERE id = 1;
SELECT * FROM orders;
DELETE FROM product WHERE id = 4;
```

```text
CREATE TABLE
CREATE TABLE
INSERT 0 2
INSERT 0 1
DELETE 1
 id | product_id
----+------------
  2 |          4
(1 row)

ERROR:  update or delete on table "product" violates foreign key constraint "review_product_id_fkey" on table "review"
DETAIL:  Key (id)=(4) is still referenced from table "review".
```

### F. A range of the primary key

<!-- example: postgresql -->
```sql
CREATE TABLE event (id bigint PRIMARY KEY, body text);
INSERT INTO event SELECT n, 'e' || n FROM generate_series(1, 10000) AS n;
EXPLAIN DELETE FROM event WHERE id <= 6000;
DELETE FROM event WHERE id <= 6000;
SELECT count(*), min(id) FROM event;
```

```text
CREATE TABLE
INSERT 0 10000
                    QUERY PLAN
---------------------------------------------------
 scan event: primary key range
 range delete: primary key range, subtrees dropped
(2 rows)

DELETE 6000
 count | min
-------+------
  4000 | 6001
(1 row)
```

### G. In batches

<!-- example: postgresql -->
```sql
DELETE FROM event WHERE body LIKE '%7' WITH (batch_rows 100);
SELECT count(*) FROM event;
DELETE FROM event WHERE id > 9000 RETURNING id WITH (batch_rows 100);
```

```text
DELETE 400
 count
-------
  3600
(1 row)

ERROR:  lexdb: DELETE with batch_rows cannot return rows (RETURNING, OUTPUT)
```

## See also

[TRUNCATE](truncate.md) · [INSERT](insert.md) · [UPDATE](update.md) · [MERGE](merge.md) · [SELECT](select.md)
