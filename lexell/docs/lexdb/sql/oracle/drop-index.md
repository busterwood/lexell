# DROP INDEX

Removes an index.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP INDEX [ schema. ] index
```

## Remarks

- The table and its rows are not touched. Queries that used the index run without it.
- A missing index is ORA-01418.
- An index that a `PRIMARY KEY` or `UNIQUE` constraint made is dropped by dropping the constraint
  ([ALTER TABLE](alter-table.md)).

## Differences from Oracle

- `FORCE`, `ONLINE` and `DEFERRED INVALIDATION` are not supported.

## Examples

### A. Drop an index

<!-- example: oracle -->
```sql
CREATE TABLE ix (a NUMBER, b NUMBER);
CREATE INDEX ix_a ON ix (a);
DROP INDEX ix_a;
SELECT COUNT(*) AS indexes_left FROM user_indexes WHERE table_name = 'IX';
DROP INDEX ix_a;
```

```text
Table created.

Index created.

Index dropped.

INDEXES_LEFT
------------
           0

1 row selected.

ERROR:
ORA-01418: specified index does not exist
```

## See also

[CREATE INDEX](create-index.md), [ALTER TABLE](alter-table.md)
