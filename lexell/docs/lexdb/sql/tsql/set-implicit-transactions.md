# SET IMPLICIT_TRANSACTIONS (Transact-SQL)

With `ON`, a statement that reads or changes a table starts a transaction when none is open, and the transaction
lasts until `COMMIT` or `ROLLBACK`.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SET IMPLICIT_TRANSACTIONS { ON | OFF }
[ ; ]
```

## Arguments

`ON`
: The session's statements open transactions by themselves.

`OFF`
: The default: each statement outside `BEGIN TRANSACTION` commits by itself (autocommit).

## Remarks

- With `ON`, a `SELECT` with a `FROM` clause, an `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `TRUNCATE TABLE`, and DDL
  (`CREATE`, `ALTER`, `DROP` ...) start a transaction when there is none; `@@TRANCOUNT` becomes 1. A `SELECT`
  without `FROM`, `SET`, `DECLARE` and `PRINT` do not.
- The transaction lasts until `COMMIT` or `ROLLBACK`, which end it as they end one opened by `BEGIN TRANSACTION`.
- The setting lasts for the session, until it is set again.

## Differences from SQL Server

- None known.

## Examples

<!--setup: tsql
CREATE TABLE dbo.acct (id int PRIMARY KEY, bal int);
INSERT dbo.acct VALUES (1, 100), (2, 50);
-->

The examples use one table:

```sql
CREATE TABLE dbo.acct (id int PRIMARY KEY, bal int);
INSERT dbo.acct VALUES (1, 100), (2, 50);
```

### A. A statement opens a transaction

<!-- example: tsql -->
```sql
SET IMPLICIT_TRANSACTIONS ON;
SELECT @@TRANCOUNT AS before_update;
UPDATE dbo.acct SET bal = bal + 5 WHERE id = 2;
SELECT @@TRANCOUNT AS after_update;
ROLLBACK;
SET IMPLICIT_TRANSACTIONS OFF;
SELECT bal FROM dbo.acct WHERE id = 2;
```

```text
before_update
-------------
0

(1 row affected)

(1 row affected)

after_update
------------
1

(1 row affected)

bal
---
50

(1 row affected)
```

### B. A SELECT from a table opens one too

<!-- example: tsql -->
```sql
SET IMPLICIT_TRANSACTIONS ON;
SELECT 1 AS no_table;
SELECT @@TRANCOUNT AS after_no_table;
SELECT COUNT(*) AS n FROM dbo.acct;
SELECT @@TRANCOUNT AS after_table;
COMMIT;
SET IMPLICIT_TRANSACTIONS OFF;
```

```text
no_table
--------
1

(1 row affected)

after_no_table
--------------
0

(1 row affected)

n
-
2

(1 row affected)

after_table
-----------
1

(1 row affected)
```

## See also

[BEGIN TRANSACTION](begin-transaction.md) · [COMMIT TRANSACTION](commit-transaction.md) ·
[SET statements](set-statements.md)
