# SAVEPOINT

Marks a point in the transaction that `ROLLBACK TO` can return to.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
SAVEPOINT name
ROLLBACK [ WORK ] TO [ SAVEPOINT ] name
```

## Remarks

- A savepoint belongs to the open transaction; `COMMIT` and `ROLLBACK` remove them all.
- `ROLLBACK TO name` undoes the changes made since `name` and removes the savepoints made after it. `name` stays.
- A savepoint outside a transaction is ORA-20000 (lexdb's text): a client in autocommit mode ends the transaction
  with each statement, so turn autocommit off (JDBC `setAutoCommit(false)`).
- A savepoint name used again moves the savepoint to the new place.
- In PL/SQL, `SAVEPOINT` and `ROLLBACK TO` are statements of the block.

## Differences from Oracle

- Outside a transaction, `SAVEPOINT` is ORA-20000 and not accepted; in Oracle a transaction begins at the
  savepoint.

## Examples

### A. Undo part of a transaction

<!-- example: oracle -->
```sql
CREATE TABLE tx (a NUMBER);
COMMIT;
INSERT INTO tx VALUES (1);
SAVEPOINT first_row;
INSERT INTO tx VALUES (2);
INSERT INTO tx VALUES (3);
ROLLBACK TO first_row;
SELECT a FROM tx ORDER BY a;
COMMIT;
```

```text
Table created.

Commit complete.

1 row created.

Savepoint created.

1 row created.

1 row created.

Rollback complete.

A
-
1

1 row selected.

Commit complete.
```

### B. A savepoint name used twice

<!-- example: oracle -->
```sql
INSERT INTO tx VALUES (10);
SAVEPOINT p;
INSERT INTO tx VALUES (11);
SAVEPOINT p;
INSERT INTO tx VALUES (12);
ROLLBACK TO p;
SELECT a FROM tx ORDER BY a;
ROLLBACK;
```

```text
1 row created.

Savepoint created.

1 row created.

Savepoint created.

1 row created.

Rollback complete.

 A
--
 1
10
11

3 rows selected.

Rollback complete.
```

### C. A savepoint in PL/SQL

<!-- example: oracle -->
```sql
BEGIN
  INSERT INTO tx VALUES (20);
  SAVEPOINT in_block;
  INSERT INTO tx VALUES (21);
  ROLLBACK TO in_block;
END;
/
SELECT a FROM tx ORDER BY a;
ROLLBACK;
```

```text
PL/SQL procedure successfully completed.

 A
--
 1
20

2 rows selected.

Rollback complete.
```

## See also

[ROLLBACK](rollback.md), [COMMIT](commit.md)
