# ROLLBACK

Undoes the changes of the transaction, or of the part after a savepoint.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
ROLLBACK [ WORK ] [ TO [ SAVEPOINT ] savepoint ]
```

## Arguments

`TO SAVEPOINT`
: Undoes the changes made since the savepoint and keeps the transaction open, with the savepoint and the ones before
  it still defined.

## Remarks

- Without `TO`, the transaction ends and all its changes are undone.
- DDL (`CREATE TABLE` and the others) commits the open transaction, as in Oracle, so a `ROLLBACK` after it does not
  undo the DDL (example B).
- A statement that fails is undone by itself; the transaction and the earlier statements stay.
- The sequence values `NEXTVAL` gave are not given back.

## Differences from Oracle

- `ROLLBACK TO` a savepoint that does not exist is ORA-20000 (`ROLLBACK TO SAVEPOINT can only be used in transaction
  blocks`); Oracle gives ORA-01086.

## Examples

### A. Rollback to a savepoint, and the whole transaction

<!-- example: oracle -->
```sql
CREATE TABLE tx (a NUMBER);
COMMIT;
INSERT INTO tx VALUES (1);
SAVEPOINT s1;
INSERT INTO tx VALUES (2);
SAVEPOINT s2;
INSERT INTO tx VALUES (3);
ROLLBACK TO SAVEPOINT s2;
SELECT COUNT(*) AS after_s2 FROM tx;
ROLLBACK TO s1;
SELECT COUNT(*) AS after_s1 FROM tx;
ROLLBACK;
SELECT COUNT(*) AS after_rollback FROM tx;
```

```text
Table created.

Commit complete.

1 row created.

Savepoint created.

1 row created.

Savepoint created.

1 row created.

Rollback complete.

AFTER_S2
--------
       2

1 row selected.

Rollback complete.

AFTER_S1
--------
       1

1 row selected.

Rollback complete.

AFTER_ROLLBACK
--------------
             0

1 row selected.
```

### B. DDL commits

<!-- example: oracle -->
```sql
CREATE TABLE temp_t (a NUMBER);
INSERT INTO temp_t VALUES (1);
ROLLBACK;
SELECT COUNT(*) AS tables_left FROM user_tables WHERE table_name = 'TEMP_T';
```

```text
Table created.

1 row created.

Rollback complete.

TABLES_LEFT
-----------
          1

1 row selected.
```

### C. An unknown savepoint

<!-- example: oracle -->
```sql
ROLLBACK TO nothere;
```

```text
ERROR:
ORA-20000: ROLLBACK TO SAVEPOINT can only be used in transaction blocks
```

## See also

[COMMIT](commit.md), [SAVEPOINT](savepoint.md), [SET TRANSACTION](set-transaction.md)
