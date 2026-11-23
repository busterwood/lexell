# SET TRANSACTION

Sets properties of the next transaction.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
SET TRANSACTION { READ ONLY | READ WRITE
                | ISOLATION LEVEL { SERIALIZABLE | READ COMMITTED }
                | NAME 'text' }
```

## Remarks

- The statement is accepted and **changes nothing**: every read-write transaction is serializable, and a
  transaction declared `READ ONLY` can still change data.
- Oracle requires `SET TRANSACTION` to be the first statement of a transaction; lexdb does not check.

## Differences from Oracle

- `READ ONLY` is not enforced (example B). `ISOLATION LEVEL READ COMMITTED` gives a serializable transaction.
- `USE ROLLBACK SEGMENT` is not supported.

## Examples

### A. The forms that are accepted

<!-- example: oracle -->
```sql
SET TRANSACTION ISOLATION LEVEL SERIALIZABLE;
SET TRANSACTION READ ONLY;
SET TRANSACTION READ WRITE;
SET TRANSACTION NAME 'x';
```

```text
Statement processed.

Statement processed.

Statement processed.

Statement processed.
```

### B. READ ONLY does not stop changes

<!-- example: oracle -->
```sql
CREATE TABLE tx (a NUMBER);
COMMIT;
SET TRANSACTION READ ONLY;
INSERT INTO tx VALUES (99);
COMMIT;
SELECT COUNT(*) AS rows_inserted FROM tx;
```

```text
Table created.

Commit complete.

Statement processed.

1 row created.

Commit complete.

ROWS_INSERTED
-------------
            1

1 row selected.
```

## See also

[COMMIT](commit.md), [ROLLBACK](rollback.md)
