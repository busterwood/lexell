# DROP INDEX

Removes an index.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
DROP [ SKIPPING ] INDEX [ CONCURRENTLY ] [ IF EXISTS ] name
```

## Arguments

`CONCURRENTLY`
: The index is dropped as without it. As in PostgreSQL, it cannot run inside a transaction block (25001).

`IF EXISTS`
: If the index does not exist, does nothing and gives a notice.

*name*
: The index, optionally schema-qualified.

## Remarks

- The index's storage is freed without reading it.
- The index of a primary key or a unique constraint goes with its constraint: `ALTER TABLE ... DROP CONSTRAINT`.
- `DROP INDEX` is transactional: in a block, `ROLLBACK` brings the index back.
- Inside a read-only transaction, and on a replica, `DROP INDEX` gives 25006.

## Differences from PostgreSQL

- One index per statement: `DROP INDEX a, b` is a syntax error, and so are `CASCADE` and `RESTRICT`.
- The index of a primary key or unique constraint is not found by `DROP INDEX` (42704 `index "t_pkey" does not
  exist`); PostgreSQL finds it and refuses (2BP01, `cannot drop index t_pkey because constraint t_pkey on table t
  requires it`).

## Examples

<!--setup: postgresql
CREATE TABLE customer (id int PRIMARY KEY, city text, score int);
CREATE INDEX customer_city ON customer (city);
CREATE INDEX customer_score ON customer (score);
-->

The examples use one table with two indexes:

```sql
CREATE TABLE customer (id int PRIMARY KEY, city text, score int);
CREATE INDEX customer_city ON customer (city);
CREATE INDEX customer_score ON customer (score);
```

### A. Drop an index

<!-- example: postgresql -->
```sql
DROP INDEX customer_city;
DROP INDEX IF EXISTS customer_city;
SELECT indexname FROM pg_indexes WHERE tablename = 'customer' ORDER BY indexname;
```

```text
DROP INDEX
NOTICE:  index "customer_city" does not exist, skipping
DROP INDEX
   indexname
----------------
 customer_pkey
 customer_score
(2 rows)
```

### B. Rolled back

<!-- example: postgresql -->
```sql
BEGIN;
DROP INDEX customer_score;
ROLLBACK;
SELECT indexname FROM pg_indexes WHERE tablename = 'customer' ORDER BY indexname;
```

```text
BEGIN
DROP INDEX
ROLLBACK
   indexname
----------------
 customer_pkey
 customer_score
(2 rows)
```

### C. Errors

<!-- example: postgresql -->
```sql
DROP INDEX customer_city;
DROP INDEX customer_score, customer_pkey;
DROP INDEX customer_pkey;
```

```text
ERROR:  index "customer_city" does not exist
ERROR:  syntax error at or near ","
ERROR:  index "customer_pkey" does not exist
```

## See also

[CREATE INDEX](create-index.md) · [ALTER INDEX](alter-index.md) · [ALTER TABLE](alter-table.md)
