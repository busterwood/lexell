# COMMIT TRANSACTION (Transact-SQL)

Ends a transaction and makes its changes permanent, or lowers the nesting count of a nested one.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
COMMIT [ { TRAN | TRANSACTION } [ transaction_name | @tran_name_variable ] ]
[ ; ]

COMMIT [ WORK ]
[ ; ]
```

## Arguments

*transaction_name*, *@tran_name_variable*
: Read and not checked, as in SQL Server: `COMMIT` always applies to the innermost `BEGIN TRANSACTION`.

## Remarks

- When `@@TRANCOUNT` is 1, `COMMIT` commits the transaction and sets `@@TRANCOUNT` to 0. When it is more than 1,
  `COMMIT` only lowers it by one; nothing is committed until the outermost `COMMIT`.
- `COMMIT` with no transaction is error 3902.
- Every read-write transaction is serializable: a `COMMIT` may fail with error 1205 when another transaction
  changed what this one read. The transaction is then rolled back; run it again.
- After an error that dooms the transaction (`XACT_STATE()` is -1, in a `CATCH` block under
  [SET XACT_ABORT ON](set-xact-abort.md)), the transaction can only be rolled back (error 3930).

## Differences from SQL Server

- `WITH ( DELAYED_DURABILITY = ON )` is not supported.

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

### A. Commit a transaction

<!-- example: tsql -->
```sql
BEGIN TRANSACTION;
UPDATE dbo.acct SET bal = bal - 20 WHERE id = 1;
UPDATE dbo.acct SET bal = bal + 20 WHERE id = 2;
COMMIT TRANSACTION;
SELECT * FROM dbo.acct;
```

```text
(1 row affected)

(1 row affected)

id bal
-- ---
1  80
2  70

(2 rows affected)
```

### B. Nested commits

<!-- example: tsql -->
```sql
BEGIN TRAN outer_tran;
BEGIN TRAN inner_tran;
UPDATE dbo.acct SET bal = bal + 1 WHERE id = 1;
COMMIT TRAN inner_tran;
SELECT @@TRANCOUNT AS still_open;
COMMIT WORK;
SELECT @@TRANCOUNT AS trancount, bal FROM dbo.acct WHERE id = 1;
```

```text
(1 row affected)

still_open
----------
1

(1 row affected)

trancount bal
--------- ---
0         81

(1 row affected)
```

### C. Errors

<!-- example: tsql -->
```sql
COMMIT;
```

```text
Msg 3902, Level 16, State 1, Line 1
The COMMIT TRANSACTION request has no corresponding BEGIN TRANSACTION.
```

## See also

[BEGIN TRANSACTION](begin-transaction.md) · [ROLLBACK TRANSACTION](rollback-transaction.md) ·
[SAVE TRANSACTION](save-transaction.md)
