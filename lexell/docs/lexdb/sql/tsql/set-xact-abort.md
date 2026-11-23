# SET XACT_ABORT (Transact-SQL)

With `ON`, an error in a statement rolls back the whole transaction and ends the batch.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SET XACT_ABORT { ON | OFF }
[ ; ]
```

## Arguments

`ON`
: A run-time error rolls back the transaction in progress and ends the batch. Outside a transaction, the batch
  ends after the failed statement.

`OFF`
: The default: only the failed statement is undone, and the batch goes on with the next statement. Compile errors
  (such as 207, 208 and 102) end the batch either way.

## Remarks

- In a `TRY` block, an error under `XACT_ABORT ON` goes to the `CATCH` block with the transaction doomed:
  `XACT_STATE()` is -1, and the transaction can only be rolled back. See [TRY...CATCH](try-catch.md).
- `XACT_ABORT ON` is the usual setting for code that must not leave half a transaction behind.
- The setting lasts for the session, until it is set again.

## Differences from SQL Server

- None known.

## Examples

<!--setup: tsql
CREATE TABLE dbo.acct (id int PRIMARY KEY, bal int CHECK (bal >= 0));
INSERT dbo.acct VALUES (1, 100), (2, 50);
-->

The examples use one table:

```sql
CREATE TABLE dbo.acct (id int PRIMARY KEY, bal int CHECK (bal >= 0));
INSERT dbo.acct VALUES (1, 100), (2, 50);
```

### A. OFF: the transaction goes on

<!-- example: tsql -->
```sql
SET XACT_ABORT OFF;
BEGIN TRAN;
UPDATE dbo.acct SET bal = bal + 1 WHERE id = 2;
UPDATE dbo.acct SET bal = -1 WHERE id = 1;
PRINT 'the batch went on';
COMMIT;
SELECT * FROM dbo.acct;
```

```text
(1 row affected)

Msg 547, Level 16, State 1, Line 1
new row for relation "acct" violates check constraint "acct_bal_check"
the batch went on
id bal
-- ---
1  100
2  51

(2 rows affected)
```

### B. ON: the transaction is rolled back and the batch ends

<!-- example: tsql -->
```sql
SET XACT_ABORT ON;
BEGIN TRAN;
UPDATE dbo.acct SET bal = bal + 1 WHERE id = 2;
UPDATE dbo.acct SET bal = -1 WHERE id = 1;
PRINT 'not reached';
GO
SELECT @@TRANCOUNT AS trancount, bal FROM dbo.acct WHERE id = 2;
```

```text
(1 row affected)

Msg 547, Level 16, State 1, Line 1
new row for relation "acct" violates check constraint "acct_bal_check"
trancount bal
--------- ---
0         51

(1 row affected)
```

### C. ON, in TRY...CATCH

<!-- example: tsql -->
```sql
SET XACT_ABORT ON;
BEGIN TRY
    BEGIN TRAN;
    UPDATE dbo.acct SET bal = -1 WHERE id = 1;
    COMMIT;
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS number, XACT_STATE() AS state, @@TRANCOUNT AS trancount;
    ROLLBACK;
END CATCH;
SELECT @@TRANCOUNT AS after_catch;
SET XACT_ABORT OFF;
```

```text
(0 rows affected)

number state trancount
------ ----- ---------
547    -1    1

(1 row affected)

after_catch
-----------
0

(1 row affected)
```

## See also

[BEGIN TRANSACTION](begin-transaction.md) · [TRY...CATCH](try-catch.md) · [SET statements](set-statements.md)
