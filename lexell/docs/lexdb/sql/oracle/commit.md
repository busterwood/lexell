# COMMIT

Ends the transaction and makes its changes permanent.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
COMMIT [ WORK ]
```

## Remarks

- A transaction begins with the first `INSERT`, `UPDATE`, `DELETE`, `MERGE` or `SELECT ... FOR UPDATE`. `COMMIT`
  makes its changes visible to other sessions and releases its locks.
- Other sessions see a change only after its `COMMIT`. A client that is in autocommit mode (a JDBC connection by
  default) commits after every statement.
- `COMMIT` with no transaction open is not an error.
- A global temporary table made `ON COMMIT DELETE ROWS` is emptied at a commit.
- In PL/SQL, `COMMIT` is a statement of the block.
- A serialization failure ends the transaction: ORA-08177, which a program retries.

## Differences from Oracle

- Every read-write transaction is serializable; a transaction that conflicts with another gets ORA-08177 and is
  retried by the program.
- `COMMIT COMMENT '...'`, `COMMIT WRITE ...` and `COMMIT FORCE` are ORA-00900 (example C).

## Examples

### A. Commit

<!-- example: oracle -->
```sql
CREATE TABLE tx (a NUMBER);
INSERT INTO tx VALUES (1);
COMMIT;
ROLLBACK;
SELECT COUNT(*) AS rows_kept FROM tx;
COMMIT WORK;
COMMIT;
```

```text
Table created.

1 row created.

Commit complete.

Rollback complete.

ROWS_KEPT
---------
        1

1 row selected.

Commit complete.

Commit complete.
```

### B. A global temporary table at commit

<!-- example: oracle -->
```sql
CREATE GLOBAL TEMPORARY TABLE gtt (a NUMBER) ON COMMIT DELETE ROWS;
INSERT INTO gtt VALUES (1);
SELECT COUNT(*) AS before_commit FROM gtt;
COMMIT;
SELECT COUNT(*) AS after_commit FROM gtt;
```

```text
Table created.

1 row created.

BEFORE_COMMIT
-------------
            1

1 row selected.

Commit complete.

AFTER_COMMIT
------------
           0

1 row selected.
```

### C. Clauses that are not taken

<!-- example: oracle -->
```sql
COMMIT COMMENT 'second row';
COMMIT WRITE BATCH NOWAIT;
```

```text
ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement
```

## See also

[ROLLBACK](rollback.md), [SAVEPOINT](savepoint.md), [SET TRANSACTION](set-transaction.md)
