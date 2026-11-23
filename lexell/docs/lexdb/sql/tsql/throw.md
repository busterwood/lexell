# THROW (Transact-SQL)

Raises an error, or in a `CATCH` block raises the caught error again.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
THROW [ { error_number | @local_variable } ,
        { message | @local_variable } ,
        { state | @local_variable } ]
[ ; ]
```

## Arguments

*error_number*
: The error's number, an `int` from 50000 up.

*message*
: The error's text, an `nvarchar`. It is not formatted: build it first (with `CONCAT` or `FORMATMESSAGE`) if it
  needs values.

*state*
: A number from 0 to 255, for the reader.

## Remarks

- The error's severity is always 16.
- `THROW` ends the batch, unless it is in a `TRY` block: then the `CATCH` block runs. Under `SET XACT_ABORT ON` the
  transaction is rolled back.
- `THROW` without arguments is allowed only in a `CATCH` block (error 10704 elsewhere): it raises the error being
  handled, with its own number, message, severity and state.
- The statement before `THROW` should end with a semicolon, as SQL Server wants.
- For a message with `%d`-style placeholders, or a severity other than 16, use [RAISERROR](raiserror.md).

## Differences from SQL Server

- An error number below 50000 is taken; SQL Server refuses it (error 35100).

## Examples

### A. Raise an error

<!-- example: tsql -->
```sql
THROW 51000, 'The record does not exist.', 1;
PRINT 'not reached';
```

```text
Msg 51000, Level 16, State 1, Line 1
The record does not exist.
```

### B. A message built from values

<!-- example: tsql -->
```sql
CREATE TABLE dbo.acct (id int PRIMARY KEY);
DECLARE @id int = 7, @msg nvarchar(100);
SELECT COUNT(*) AS accounts FROM dbo.acct;
SET @msg = CONCAT(N'Account ', @id, N' is closed.');
THROW 51001, @msg, 2;
```

```text
accounts
--------
0

(1 row affected)

Msg 51001, Level 16, State 2, Line 5
Account 7 is closed.
```

### C. Raise the caught error again

<!-- example: tsql -->
```sql
BEGIN TRY
    SELECT 1 / 0 AS never;
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS logged_number;
    THROW;
END CATCH;
```

```text
logged_number
-------------
8134

(1 row affected)

Msg 8134, Level 16, State 1, Line 6
Divide by zero error encountered.
```

### D. Errors

<!-- example: tsql -->
```sql
THROW;
GO
THROW 49999, 'a number below 50000', 1;
GO
```

```text
Msg 10704, Level 15, State 1, Line 1
To rethrow an error, a THROW statement must be used inside a CATCH block. Insert the THROW statement inside a CATCH block, or add error parameters to the THROW statement.
Msg 49999, Level 16, State 1, Line 1
a number below 50000
```

## See also

[TRY...CATCH](try-catch.md) · [RAISERROR](raiserror.md) · [PRINT](print.md)
