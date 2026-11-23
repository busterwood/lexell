# SAVE TRANSACTION (Transact-SQL)

Marks a savepoint in the transaction in progress, so that a later `ROLLBACK` can undo only the work after it.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SAVE { TRAN | TRANSACTION } { savepoint_name | @savepoint_variable }
[ ; ]
```

## Arguments

*savepoint_name*, *@savepoint_variable*
: The savepoint's name.

## Remarks

- `ROLLBACK TRANSACTION savepoint_name` undoes the work since the savepoint and leaves the transaction open;
  `@@TRANCOUNT` does not change. The savepoint can be rolled back to again.
- A name used twice marks a new savepoint; `ROLLBACK` goes back to the latest of that name.
- `SAVE TRANSACTION` with no transaction is error 628.
- `COMMIT` commits all the work, savepoints or not.

## Differences from SQL Server

- None known.

## Examples

<!--setup: tsql
CREATE TABLE dbo.log (step int);
-->

The examples use one table:

```sql
CREATE TABLE dbo.log (step int);
```

### A. Undo part of a transaction

<!-- example: tsql -->
```sql
BEGIN TRANSACTION;
INSERT dbo.log VALUES (1);
SAVE TRANSACTION after_one;
INSERT dbo.log VALUES (2);
INSERT dbo.log VALUES (3);
ROLLBACK TRANSACTION after_one;
INSERT dbo.log VALUES (4);
COMMIT;
SELECT step FROM dbo.log ORDER BY step;
```

```text
(1 row affected)

(1 row affected)

(1 row affected)

(1 row affected)

step
----
1
4

(2 rows affected)
```

### B. A savepoint in a variable, rolled back to twice

<!-- example: tsql -->
```sql
DECLARE @sp nvarchar(32) = N'mark';
BEGIN TRAN;
SAVE TRAN @sp;
INSERT dbo.log VALUES (5);
ROLLBACK TRAN @sp;
INSERT dbo.log VALUES (6);
ROLLBACK TRAN @sp;
SELECT @@TRANCOUNT AS trancount, COUNT(*) AS rows_now FROM dbo.log;
COMMIT;
```

```text
(1 row affected)

(1 row affected)

trancount rows_now
--------- --------
1         2

(1 row affected)
```

### C. Errors

<!-- example: tsql -->
```sql
SAVE TRANSACTION nowhere;
```

```text
Msg 628, Level 16, State 1, Line 1
Cannot issue SAVE TRANSACTION when there is no active transaction.
```

## See also

[BEGIN TRANSACTION](begin-transaction.md) · [ROLLBACK TRANSACTION](rollback-transaction.md)
