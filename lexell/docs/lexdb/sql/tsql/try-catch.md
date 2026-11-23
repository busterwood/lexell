# TRY...CATCH (Transact-SQL)

Runs a block of statements and, when one of them fails, a second block that handles the error.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
BEGIN TRY
    { sql_statement | statement_block }
END TRY
BEGIN CATCH
    [ { sql_statement | statement_block } ]
END CATCH
[ ; ]
```

## Arguments

*sql_statement*, *statement_block*
: Any statements, including other `TRY...CATCH` constructs.

## Remarks

- When a statement in the `TRY` block fails with an error of severity 11 or more, the rest of the block is skipped
  and the `CATCH` block runs. The client gets no error message: the `CATCH` block decides what to report. When no
  error happens, the `CATCH` block is skipped.
- In the `CATCH` block these functions describe the error: `ERROR_NUMBER()`, `ERROR_MESSAGE()`, `ERROR_SEVERITY()`,
  `ERROR_STATE()`, `ERROR_LINE()` and `ERROR_PROCEDURE()`. Outside a `CATCH` block they are NULL.
- `XACT_STATE()` tells what can be done with the transaction: 1, it is open and can be committed; -1, it is doomed and
  can only be rolled back (an error under `SET XACT_ABORT ON`); 0, there is none.
- [THROW](throw.md) without arguments, in a `CATCH` block, raises the caught error again, to the next `TRY` block
  out or to the client.
- An error in a nested `TRY` block goes to its own `CATCH` block; an error in a `CATCH` block goes to the next
  `CATCH` block out.
- An error in a procedure called from the `TRY` block is caught there too.
- An unknown table (208) or column (207) in the `TRY` block is not caught: as in SQL Server, the error ends the
  batch (example C). Put the statement in a procedure or in dynamic SQL (`EXEC`) to catch it.
- Messages of severity 10 or less (`PRINT`, `RAISERROR` with a low severity) are not errors and are not caught.

## Differences from SQL Server

- A failed statement in the `TRY` block sends `(0 rows affected)` before the `CATCH` block's output (example B);
  SQL Server sends no count for it.
- `ERROR_LINE()` gives 1, whatever line failed.
- After a batch in which an inner `CATCH` block printed a message and re-raised the error with `THROW` to an outer
  `CATCH` block, the session's next `TRY` block goes wrong: an unknown table (208) in it is reported, and then its
  `CATCH` block runs too, with the old error's `ERROR_NUMBER()` and `ERROR_MESSAGE()`.
- Many `ERROR_MESSAGE()` texts are lexdb's (PostgreSQL's wording), with SQL Server's numbers.

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

### A. The error functions

<!-- example: tsql -->
```sql
BEGIN TRY
    SELECT 1 / 0 AS never;
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS number, ERROR_SEVERITY() AS severity, ERROR_STATE() AS state,
           ERROR_MESSAGE() AS message, ERROR_PROCEDURE() AS in_procedure;
END CATCH;
```

```text
number severity state message                           in_procedure
------ -------- ----- --------------------------------- ------------
8134   16       1     Divide by zero error encountered. NULL

(1 row affected)
```

### B. The rest of the TRY block is skipped

<!-- example: tsql -->
```sql
BEGIN TRY
    UPDATE dbo.acct SET bal = -5 WHERE id = 1;
    PRINT 'not reached';
END TRY
BEGIN CATCH
    PRINT 'caught ' + CAST(ERROR_NUMBER() AS varchar(10)) + ': ' + ERROR_MESSAGE();
END CATCH;
SELECT ERROR_NUMBER() AS outside_catch;
```

```text
(0 rows affected)

caught 547: new row for relation "acct" violates check constraint "acct_bal_check"
outside_catch
-------------
NULL

(1 row affected)
```

### C. An unknown table is not caught

<!-- example: tsql -->
```sql
BEGIN TRY
    SELECT * FROM dbo.nothere;
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS number, ERROR_MESSAGE() AS message;
END CATCH;
GO
BEGIN TRY
    EXEC ('SELECT * FROM dbo.nothere');
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS number, ERROR_MESSAGE() AS message;
END CATCH;
```

```text
Msg 208, Level 16, State 1, Line 1
Invalid object name 'nothere'.
number message
------ ------------------------------
208    Invalid object name 'nothere'.

(1 row affected)
```

### D. Roll back a transaction in CATCH

<!-- example: tsql -->
```sql
BEGIN TRY
    BEGIN TRAN;
    UPDATE dbo.acct SET bal = bal - 10 WHERE id = 1;
    UPDATE dbo.acct SET bal = -1 WHERE id = 2;
    COMMIT;
END TRY
BEGIN CATCH
    SELECT XACT_STATE() AS state_in_catch, @@TRANCOUNT AS trancount;
    IF @@TRANCOUNT > 0 ROLLBACK;
END CATCH;
SELECT * FROM dbo.acct;
```

```text
(1 row affected)

(0 rows affected)

state_in_catch trancount
-------------- ---------
1              1

(1 row affected)

id bal
-- ---
1  100
2  50

(2 rows affected)
```

### E. Nested TRY blocks and THROW

<!-- example: tsql -->
```sql
BEGIN TRY
    BEGIN TRY
        RAISERROR('inner failure', 16, 1);
    END TRY
    BEGIN CATCH
        PRINT 'inner CATCH: ' + ERROR_MESSAGE();
        THROW;
    END CATCH;
END TRY
BEGIN CATCH
    PRINT 'outer CATCH: ' + ERROR_MESSAGE() + ' (' + CAST(ERROR_NUMBER() AS varchar(10)) + ')';
END CATCH;
```

```text
inner CATCH: inner failure
outer CATCH: inner failure (50000)
```

### F. Low severities are not caught

<!-- example: tsql -->
```sql
BEGIN TRY
    RAISERROR('just a note', 10, 1);
    PRINT 'the TRY block went on';
END TRY
BEGIN CATCH
    PRINT 'not reached';
END CATCH;
```

```text
just a note
the TRY block went on
```

### G. After a rethrow: the stale CATCH

This batch runs after example E (see Differences).

<!-- example: tsql -->
```sql
BEGIN TRY
    SELECT * FROM dbo.nothere;
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS number, ERROR_MESSAGE() AS message;
END CATCH;
```

```text
Msg 208, Level 16, State 1, Line 1
Invalid object name 'nothere'.
number message
------ -------------
50000  inner failure

(1 row affected)
```

## See also

[THROW](throw.md) · [RAISERROR](raiserror.md) · [SET XACT_ABORT](set-xact-abort.md) ·
[BEGIN TRANSACTION](begin-transaction.md)
