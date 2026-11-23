# ROLLBACK TRANSACTION (Transact-SQL)

Undoes the transaction in progress, or its work since a savepoint.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
ROLLBACK { TRAN | TRANSACTION }
    [ transaction_name | @tran_name_variable | savepoint_name | @savepoint_variable ]
[ ; ]

ROLLBACK [ WORK ]
[ ; ]
```

## Arguments

*transaction_name*
: The transaction's name. The whole transaction is rolled back.

*savepoint_name*
: A savepoint made by [SAVE TRANSACTION](save-transaction.md). The work since the savepoint is undone; the
  transaction stays open and `@@TRANCOUNT` does not change.

## Remarks

- Without a savepoint name, `ROLLBACK` undoes the whole transaction, however deeply nested, and sets `@@TRANCOUNT`
  to 0.
- `ROLLBACK` with no transaction is error 3903.
- DDL is undone too: a table made in the transaction is gone, a table dropped in it is back.

## Differences from SQL Server

- A name that is neither the outermost transaction's nor a savepoint's (an inner transaction's name, or a name not
  used) rolls back the whole transaction. SQL Server refuses it with error 6401, "Cannot roll back ... No
  transaction or savepoint of that name was found", and the transaction stays open.

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

### A. Roll back a transaction

<!-- example: tsql -->
```sql
BEGIN TRANSACTION;
DELETE FROM dbo.acct;
SELECT COUNT(*) AS inside FROM dbo.acct;
ROLLBACK TRANSACTION;
SELECT COUNT(*) AS after_rollback FROM dbo.acct;
```

```text
(2 rows affected)

inside
------
0

(1 row affected)

after_rollback
--------------
2

(1 row affected)
```

### B. Roll back to a savepoint

<!-- example: tsql -->
```sql
BEGIN TRAN;
UPDATE dbo.acct SET bal = bal - 10 WHERE id = 1;
SAVE TRAN before_second;
UPDATE dbo.acct SET bal = bal - 10 WHERE id = 1;
ROLLBACK TRAN before_second;
SELECT @@TRANCOUNT AS trancount, bal FROM dbo.acct WHERE id = 1;
COMMIT;
```

```text
(1 row affected)

(1 row affected)

trancount bal
--------- ---
1         90

(1 row affected)
```

### C. DDL is undone

<!-- example: tsql -->
```sql
BEGIN TRAN;
DROP TABLE dbo.acct;
ROLLBACK;
SELECT COUNT(*) AS rows_back FROM dbo.acct;
```

```text
rows_back
---------
2

(1 row affected)
```

### D. An unknown name rolls back everything

<!-- example: tsql -->
```sql
BEGIN TRAN;
UPDATE dbo.acct SET bal = 0 WHERE id = 2;
ROLLBACK TRAN no_such_name;
SELECT @@TRANCOUNT AS trancount, bal FROM dbo.acct WHERE id = 2;
```

```text
(1 row affected)

trancount bal
--------- ---
0         50

(1 row affected)
```

### E. Errors

<!-- example: tsql -->
```sql
ROLLBACK;
```

```text
Msg 3903, Level 16, State 1, Line 1
The ROLLBACK TRANSACTION request has no corresponding BEGIN TRANSACTION.
```

## See also

[BEGIN TRANSACTION](begin-transaction.md) · [COMMIT TRANSACTION](commit-transaction.md) ·
[SAVE TRANSACTION](save-transaction.md)
