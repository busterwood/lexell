# BEGIN TRANSACTION (Transact-SQL)

Starts a transaction, or raises the nesting count of the one in progress.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
BEGIN { TRAN | TRANSACTION } [ transaction_name | @tran_name_variable ]
[ ; ]
```

## Arguments

*transaction_name*, *@tran_name_variable*
: A name for the transaction, for the reader: `COMMIT` and `ROLLBACK` may repeat it.

## Remarks

- Outside a transaction, each statement is a transaction of its own (autocommit), unless
  [SET IMPLICIT_TRANSACTIONS ON](set-implicit-transactions.md).
- `BEGIN TRANSACTION` raises `@@TRANCOUNT` by one. Inside a transaction it starts nothing new: only the outermost
  `COMMIT` commits, and any `ROLLBACK` without a savepoint name rolls back the whole transaction and sets
  `@@TRANCOUNT` to 0.
- A statement that fails inside a transaction is undone, and the transaction goes on (`XACT_STATE()` is 1), unless
  [SET XACT_ABORT ON](set-xact-abort.md): then the error rolls the transaction back and ends the batch.
- Every read-write transaction is serializable. When it read rows that another transaction changed and committed
  meanwhile, its statement or its `COMMIT` fails with error 1205; run the transaction again. The isolation level set
  by [SET TRANSACTION ISOLATION LEVEL](set-transaction-isolation-level.md) does not change this.
- Table changes and DDL (`CREATE TABLE`, `ALTER TABLE`, `DROP TABLE` ...) are both undone by `ROLLBACK`. A
  sequence's `NEXT VALUE FOR` is not.

## Differences from SQL Server

- `WITH MARK` is error 102. `BEGIN DISTRIBUTED TRANSACTION` is error 156 (`near the keyword 'DISTRIBUTED'`).
- `ROLLBACK` with a name that is neither the transaction's nor a savepoint's rolls the transaction back; SQL Server
  refuses it (6401) and leaves the transaction open. See [ROLLBACK TRANSACTION](rollback-transaction.md).

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

### A. A named transaction

<!-- example: tsql -->
```sql
BEGIN TRANSACTION transfer;
UPDATE dbo.acct SET bal = bal - 30 WHERE id = 1;
UPDATE dbo.acct SET bal = bal + 30 WHERE id = 2;
COMMIT TRANSACTION transfer;
SELECT * FROM dbo.acct;
```

```text
(1 row affected)

(1 row affected)

id bal
-- ---
1  70
2  80

(2 rows affected)
```

### B. Nesting and @@TRANCOUNT

<!-- example: tsql -->
```sql
SELECT @@TRANCOUNT AS outside;
BEGIN TRAN;
BEGIN TRAN;
SELECT @@TRANCOUNT AS nested;
COMMIT;
SELECT @@TRANCOUNT AS after_inner_commit;
COMMIT;
SELECT @@TRANCOUNT AS after_outer_commit;
```

```text
outside
-------
0

(1 row affected)

nested
------
2

(1 row affected)

after_inner_commit
------------------
1

(1 row affected)

after_outer_commit
------------------
0

(1 row affected)
```

### C. An inner ROLLBACK rolls back everything

<!-- example: tsql -->
```sql
BEGIN TRAN;
UPDATE dbo.acct SET bal = 0 WHERE id = 1;
BEGIN TRAN;
ROLLBACK;
SELECT @@TRANCOUNT AS trancount, bal FROM dbo.acct WHERE id = 1;
```

```text
(1 row affected)

trancount bal
--------- ---
0         70

(1 row affected)
```

### D. A failed statement inside a transaction

The `UPDATE` that breaks the check is undone; the transaction goes on and commits the rest.

<!-- example: tsql -->
```sql
BEGIN TRAN;
UPDATE dbo.acct SET bal = bal + 1 WHERE id = 2;
UPDATE dbo.acct SET bal = -1 WHERE id = 1;
SELECT @@TRANCOUNT AS trancount, XACT_STATE() AS state;
COMMIT;
SELECT * FROM dbo.acct;
```

```text
(1 row affected)

Msg 547, Level 16, State 1, Line 3
The UPDATE statement conflicted with the CHECK constraint "acct_bal_check". The conflict occurred in database "lexdb", table "dbo.acct", column 'bal'.
trancount state
--------- -----
1         1

(1 row affected)

id bal
-- ---
1  70
2  81

(2 rows affected)
```

### E. DDL is transactional

<!-- example: tsql -->
```sql
BEGIN TRAN;
CREATE TABLE dbo.temp_work (a int);
ROLLBACK;
SELECT CASE WHEN OBJECT_ID('dbo.temp_work') IS NULL THEN 'gone' ELSE 'there' END AS temp_work;
```

```text
temp_work
---------
gone

(1 row affected)
```

### F. What lexdb does not take

<!-- example: tsql -->
```sql
BEGIN TRANSACTION t1 WITH MARK 'before the load';
GO
BEGIN DISTRIBUTED TRANSACTION;
GO
```

```text
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'before the load'.
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'DISTRIBUTED'.
```

## See also

[COMMIT TRANSACTION](commit-transaction.md) · [ROLLBACK TRANSACTION](rollback-transaction.md) ·
[SAVE TRANSACTION](save-transaction.md) · [SET XACT_ABORT](set-xact-abort.md) ·
[SET IMPLICIT_TRANSACTIONS](set-implicit-transactions.md) · [TRY...CATCH](try-catch.md)
