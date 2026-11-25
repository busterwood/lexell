# SET CONSTRAINTS (Transact-SQL)

Sets when a transaction checks its deferrable assertions: after each statement, or at the commit.

**Door:** SQL Server (TDS). **Follows:** the SQL standard (ISO/IEC 9075-2, 17.4), not SQL Server: **SQL Server has no
`SET CONSTRAINTS`** and no deferral. The statement is lexdb's own, taken from the standard, and works only on
[assertions](create-assertion.md).

## Syntax

```
SET CONSTRAINTS { ALL | assertion_name [ ,...n ] } { DEFERRED | IMMEDIATE }
[ ; ]
```

## Arguments

`ALL`
: Every deferrable assertion.

*assertion_name*
: An assertion, optionally schema-qualified. It must be `DEFERRABLE` to be set `DEFERRED` (error 50000 otherwise;
  PostgreSQL's door gives 42809). A name that is no assertion is error 50000 (`constraint "name" does not exist`) inside a transaction.

`DEFERRED`
: The check waits for the outermost `COMMIT TRAN`.

`IMMEDIATE`
: The check runs after each statement. The writes made since the assertion was deferred are checked at once; a failure
  is 547 naming `SET CONSTRAINTS`, and the transaction is kept.

## Remarks

- The setting lasts until the end of the transaction. An assertion's own `INITIALLY` setting applies again in the
  next one.
- Outside a transaction the statement does nothing, and gives no error for a name that is no assertion (the last example).
- Foreign keys cannot be deferred in SQL Server and are not affected.
- A deferred assertion's check at `COMMIT TRAN` failing is 547 naming `COMMIT TRANSACTION`; the transaction is rolled
  back and `@@TRANCOUNT` is 0.

## Differences from SQL Server

- The statement does not exist in SQL Server.

## Examples

### A. Deferring a check

<!-- example: tsql -->
```sql
CREATE TABLE dbo.owner (id int PRIMARY KEY);
CREATE TABLE dbo.pet (name varchar(20), owner_id int NOT NULL);
GO
CREATE ASSERTION pet_has_owner CHECK (NOT EXISTS (
    SELECT 1 FROM dbo.pet p WHERE NOT EXISTS (SELECT 1 FROM dbo.owner o WHERE o.id = p.owner_id))) DEFERRABLE
GO
INSERT dbo.pet VALUES ('rex', 1);
GO
BEGIN TRAN;
SET CONSTRAINTS pet_has_owner DEFERRED;
INSERT dbo.pet VALUES ('rex', 1);
INSERT dbo.owner VALUES (1);
COMMIT TRAN;
SELECT * FROM dbo.pet;
```

```text
Msg 547, Level 16, State 1, Line 1
The INSERT statement conflicted with the assertion "pet_has_owner". The conflict occurred in database "lexdb", table "dbo.pet".
(1 row affected)

(1 row affected)

name owner_id
---- --------
rex  1

(1 row affected)
```

### B. IMMEDIATE runs the waiting check

<!-- example: tsql -->
```sql
BEGIN TRAN;
SET CONSTRAINTS pet_has_owner DEFERRED;
INSERT dbo.pet VALUES ('tom', 2);
SET CONSTRAINTS pet_has_owner IMMEDIATE;
SELECT @@TRANCOUNT AS trancount;
ROLLBACK TRAN;
GO
SET CONSTRAINTS nosuch DEFERRED;
GO
BEGIN TRAN;
SET CONSTRAINTS nosuch DEFERRED;
ROLLBACK TRAN;
```

```text
(1 row affected)

Msg 547, Level 16, State 1, Line 4
The SET CONSTRAINTS statement conflicted with the assertion "pet_has_owner". The conflict occurred in database "lexdb", table "dbo.pet".
trancount
---------
1

(1 row affected)

Msg 50000, Level 16, State 1, Line 2
constraint "nosuch" does not exist
```

## See also

[CREATE ASSERTION](create-assertion.md), [COMMIT TRANSACTION](commit-transaction.md),
[BEGIN TRANSACTION](begin-transaction.md)
