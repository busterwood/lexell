# ALTER INDEX

Renames an index.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
ALTER INDEX [ IF EXISTS ] name RENAME TO new_name
```

## Arguments

`IF EXISTS`
: If the index does not exist, does nothing and gives a notice.

*name*
: The index, optionally schema-qualified.

*new_name*
: Its new name, in the same schema.

## Remarks

- The index of a primary key or unique constraint may be renamed too.
- `ALTER INDEX` is transactional.

## Differences from PostgreSQL

- `ALTER INDEX` takes `RENAME TO` only: `SET ( storage_parameter )`, `RESET`, `SET TABLESPACE`, `ATTACH PARTITION`,
  `DEPENDS ON EXTENSION` and `ALTER COLUMN ... SET STATISTICS` are refused (0A000, `lexdb: ALTER INDEX takes RENAME
  TO only`).

## Examples

<!--setup: postgresql
CREATE TABLE customer (id int PRIMARY KEY, city text);
CREATE INDEX customer_city ON customer (city);
-->

The examples use one table with an index:

```sql
CREATE TABLE customer (id int PRIMARY KEY, city text);
CREATE INDEX customer_city ON customer (city);
```

### A. Rename an index

<!-- example: postgresql -->
```sql
ALTER INDEX customer_city RENAME TO customer_town;
SELECT indexname FROM pg_indexes WHERE tablename = 'customer' ORDER BY indexname;
```

```text
ALTER INDEX
   indexname
---------------
 customer_pkey
 customer_town
(2 rows)
```

### B. IF EXISTS, a constraint's index, and a rollback

<!-- example: postgresql -->
```sql
ALTER INDEX IF EXISTS nosuch RENAME TO other;
ALTER INDEX customer_town SET (fillfactor = 70);
ALTER INDEX customer_pkey RENAME TO customer_key;
BEGIN;
ALTER INDEX customer_town RENAME TO customer_place;
ROLLBACK;
SELECT indexname FROM pg_indexes WHERE tablename = 'customer' ORDER BY indexname;
```

```text
NOTICE:  relation "nosuch" does not exist, skipping
ALTER INDEX
ERROR:  lexdb: ALTER INDEX takes RENAME TO only
ALTER INDEX
BEGIN
ALTER INDEX
ROLLBACK
   indexname
---------------
 customer_key
 customer_town
(2 rows)
```

## See also

[CREATE INDEX](create-index.md) · [DROP INDEX](drop-index.md) · [ALTER TABLE](alter-table.md)
