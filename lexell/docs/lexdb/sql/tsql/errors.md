# Errors (Transact-SQL)

The error numbers, severities and messages the SQL Server door returns.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
Msg number, Level severity, State state, Line line
message
```

## Arguments

A client sees the error as SQL Server sends it: a number (`Msg`), a severity (`Level`), a state and a line, and a
message. In T-SQL code `ERROR_NUMBER()`, `ERROR_SEVERITY()`, `ERROR_STATE()`, `ERROR_LINE()` and `ERROR_MESSAGE()`
return the same values inside a `CATCH` block (see [system functions](functions-system.md)).

lexdb has one internal error code per failure (a PostgreSQL SQLSTATE), and the SQL Server door turns it into the
number SQL Server gives the same failure. Where SQL Server has no such failure, or lexdb does not support the
feature, the number is **50000**.

### Names and syntax

| Number | Meaning |
|---|---|
| 102 | Incorrect syntax near a token. |
| 111 | `CREATE PROCEDURE` or `CREATE FUNCTION` is not the first statement of its batch. |
| 134 | A variable is declared twice in the batch. |
| 137 | A variable is used before it is declared (`Must declare the scalar variable`). |
| 141 | A `SELECT` that assigns to a variable also returns data. |
| 155 | An unknown part name in `DATEPART`, `DATEADD` and the other date functions. |
| 156 | Incorrect syntax near a keyword. |
| 178 | `RETURN` with a value outside a procedure. |
| 179 | `OUTPUT` with a constant argument in `EXEC`. |
| 195 | An unknown function or system variable (`function x with n arguments does not exist`). |
| 207 | An invalid column name. |
| 208 | An invalid object name (a table, view or other relation that is not there). |
| 213 | The number of values in an `INSERT` does not match the table. |
| 468 | A collation conflict between two strings. |
| 1002 | An invalid scale in a type such as `datetime2(8)`. |
| 1087 | A table variable used but not declared. |
| 2812 | A procedure that does not exist (also what a misspelt statement such as `SELEC 1` gives). |

### Constraints and data

| Number | Meaning |
|---|---|
| 515 | NULL in a `NOT NULL` column. |
| 544 | An explicit value for an identity column while `IDENTITY_INSERT` is `OFF`. |
| 547 | A `CHECK` or `FOREIGN KEY` constraint violated. |
| 2627 | A `PRIMARY KEY` or `UNIQUE` constraint violated (a unique index gives the same). |
| 8110 | A second `PRIMARY KEY` in `CREATE TABLE`. |
| 1902 | A second `CLUSTERED` index on a table. |
| 2628 | A string too long for its column. |
| 241 | A date or time that cannot be read. |
| 245 | A string that cannot be converted to an integer. |
| 517 | A date or time out of range (`2026-02-30`, `25:00`). |
| 8114 | A string that cannot be converted to a `decimal`, `float` or `bigint`. |
| 8115 | An arithmetic overflow, an integer out of range or a number too large for its decimal. |
| 8134 | Division by zero. |
| 512 | A subquery that returns more than one value where one is expected. |
| 271 | An attempt to modify a computed column. |
| 8116 | A function argument of an invalid type. |
| 8117 | An operand of an invalid type for the operator. |

### Objects and statements

| Number | Meaning |
|---|---|
| 218, 219 | A type that does not exist (on `DROP TYPE`), or one that exists already (`CREATE TYPE`). |
| 2714 | An object, role or user that exists already. |
| 2715 | A data type that does not exist. |
| 3701 | `DROP` of a table, view, procedure or function that does not exist (severity 11). |
| 4121 | A column, function or method that cannot be found by that name. |
| 4902 | A table named by `TRUNCATE` or similar that cannot be found. |
| 5074 | An object depends on the column you are dropping or changing. |
| 2754 | `RAISERROR` of severity 19 to 25 without `WITH LOG`. |
| 5324, 8672, 10713 | `MERGE` rules: a `WHEN` clause after one with no condition; a target row matched twice; a missing `;`. |
| 310, 1042 | `OPTION (MAXRECURSION n)` out of range, or given twice. |
| 313 | Too few arguments for a procedure or function. |
| 911 | `USE` of a database that does not exist. |
| 15151 | A user, role or object named in `GRANT`, `REVOKE` and the like that cannot be found. |
| 229 | Permission denied. |
| 3906 | A change on a read-only replica. |

### Transactions

| Number | Meaning |
|---|---|
| 1205 | A serialization failure: the transaction lost and must be retried. |
| 3902, 3903 | `COMMIT` or `ROLLBACK` with no transaction open. |
| 3930 | The transaction cannot commit because an earlier error doomed it. |
| 628 | `SAVE TRANSACTION` with no transaction open. |

### Errors you raise, and what lexdb does not support

| Number | Meaning |
|---|---|
| 50000 | `RAISERROR` with a message text; also every error SQL Server has no number for here (a column named twice, a column that must be in `GROUP BY`, an ambiguous column) and every feature lexdb does not support: the message begins `lexdb:`. |
| 51000 and up | `THROW` with your own number. |
| 2745, 596 | Sent after a `RAISERROR ... WITH LOG` of severity 20 or more; the connection is closed. |
| 18456 | A failed login. |

## Remarks

- Severity (`Level`) is 16 for most errors, 15 for syntax errors (102, 156, 178 and a few more), and 14 for a key
  violation (2627), a denied permission (229) and a failed login (18456).
- The `Line` is the line of the failing statement in the batch.
- A batch is parsed whole before it runs. A syntax error (102, 156) or a refusal at parse time (error 50000
  `lexdb:` messages, 111, 179) stops the batch before anything in it runs, so put such a statement in a batch of its
  own. Errors 207, 208, 195, 137, 134, 468 and 2812 end the batch at their statement: the statements before it
  have run. Any other error ends only its statement, unless `SET XACT_ABORT ON` is in force.
- `lexdb:` messages (error 50000) give the feature that is missing: see the *Differences* section of the page for
  the statement.
- Most messages are SQL Server's text. Errors numbered 50000, and a few others (8115 for a decimal that does not fit,
  2628 for a string too long), carry lexdb's own.

## Differences from SQL Server

- A few messages differ in wording from SQL Server's (see the examples); the numbers and levels are the ones listed.
- Error 8115 for an integer that does not fit says SQL Server's `Arithmetic overflow error converting expression to
  data type int.` (or `smallint`); for a decimal that does not fit it says `numeric field overflow: ...`, where SQL
  Server says `Arithmetic overflow error converting numeric to data type numeric`.
- A unique index violation is 2627 (SQL Server: 2601).

## Examples

<!--setup: tsql
CREATE TABLE dbo.p (id int PRIMARY KEY, code varchar(5) NOT NULL UNIQUE, qty int CHECK (qty >= 0));
CREATE TABLE dbo.c (id int PRIMARY KEY, p_id int REFERENCES dbo.p (id));
INSERT INTO dbo.p VALUES (1, 'a', 1);
-->

The examples use two tables:

```sql
CREATE TABLE dbo.p (id int PRIMARY KEY, code varchar(5) NOT NULL UNIQUE, qty int CHECK (qty >= 0));
CREATE TABLE dbo.c (id int PRIMARY KEY, p_id int REFERENCES dbo.p (id));
INSERT INTO dbo.p VALUES (1, 'a', 1);
```

### A. Names that are not found

<!-- example: tsql -->
```sql
SELECT * FROM dbo.nothere;
GO
SELECT nothere FROM dbo.p;
GO
SELECT nofunc(1);
GO
EXEC dbo.nothere;
GO
USE nosuchdb;
```

```text
Msg 208, Level 16, State 1, Line 1
Invalid object name 'nothere'.
Msg 207, Level 16, State 1, Line 1
Invalid column name 'nothere'.
Msg 195, Level 15, State 1, Line 1
'nofunc' is not a recognized built-in function name.
Msg 2812, Level 16, State 62, Line 1
Could not find stored procedure 'nothere'.
Msg 911, Level 16, State 1, Line 1
Database 'nosuchdb' does not exist. Make sure that the name is entered correctly.
```

### B. Syntax errors

<!-- example: tsql -->
```sql
SELECT 1 FROM;
GO
SELEC 1;
GO
DECLARE @x int; DECLARE @x int;
GO
SELECT @undeclared;
GO
SELECT DATEPART(foo, CAST('2026-03-15' AS date));
```

```text
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near ';'.
Msg 2812, Level 16, State 62, Line 1
Could not find stored procedure 'selec'.
Msg 134, Level 16, State 1, Line 1
The variable name '@x' has already been declared. Variable names must be unique within a query batch or stored procedure.
Msg 137, Level 16, State 1, Line 1
Must declare the scalar variable "@undeclared".
Msg 155, Level 16, State 1, Line 1
'"foo"' is not a recognized datepart option.
```

### C. Constraints

<!-- example: tsql -->
```sql
INSERT INTO dbo.p VALUES (1, 'b', 1);
INSERT INTO dbo.p VALUES (2, 'a', 1);
INSERT INTO dbo.p (id, code) VALUES (3, NULL);
INSERT INTO dbo.p VALUES (3, 'c', -1);
INSERT INTO dbo.c VALUES (1, 99);
INSERT INTO dbo.p VALUES (4, 'toolong', 1);
INSERT INTO dbo.p VALUES (5, 'e');
```

```text
Msg 2627, Level 14, State 1, Line 1
Violation of PRIMARY KEY constraint 'p_pkey'. Cannot insert duplicate key in object 'dbo.p'. The duplicate key value is (1).
Msg 2627, Level 14, State 1, Line 2
Violation of UNIQUE KEY constraint 'p_code_key'. Cannot insert duplicate key in object 'dbo.p'. The duplicate key value is (a).
Msg 515, Level 16, State 1, Line 3
Cannot insert the value NULL into column 'code', table 'lexdb.dbo.p'; column does not allow nulls. INSERT fails.
Msg 547, Level 16, State 1, Line 4
The INSERT statement conflicted with the CHECK constraint "p_qty_check". The conflict occurred in database "lexdb", table "dbo.p", column 'qty'.
Msg 547, Level 16, State 1, Line 5
The INSERT statement conflicted with the FOREIGN KEY constraint "c_p_id_fkey". The conflict occurred in database "lexdb", table "dbo.p", column 'id'.
Msg 2628, Level 16, State 1, Line 6
value too long for type character varying(5)
Msg 213, Level 16, State 1, Line 7
Column name or number of supplied values does not match table definition.
```

### D. Conversion and arithmetic

<!-- example: tsql -->
```sql
SELECT 1 / 0;
SELECT CAST('x' AS int);
SELECT CAST('x' AS date);
SELECT CAST(99999999999 AS int);
SELECT CAST('2026-02-30' AS date);
SELECT 'abc' + 1;
```

```text
Msg 8134, Level 16, State 1, Line 1
Divide by zero error encountered.
Msg 245, Level 16, State 1, Line 2
Conversion failed when converting the varchar value 'x' to data type int.
Msg 241, Level 16, State 1, Line 3
Conversion failed when converting date and/or time from character string.
Msg 8115, Level 16, State 1, Line 4
Arithmetic overflow error converting expression to data type int.
Msg 517, Level 16, State 1, Line 5
date/time field value out of range: "2026-02-30"
Msg 8114, Level 16, State 1, Line 6
Error converting data type varchar to bigint.
```

### E. Objects that exist, or do not

<!-- example: tsql -->
```sql
CREATE TABLE dbo.p (a int);
GO
CREATE TABLE dbo.q (a nosuchtype);
GO
DROP TABLE dbo.nothere;
GO
CREATE USER dup1;
CREATE USER dup1;
```

```text
Msg 2714, Level 16, State 1, Line 1
There is already an object named 'p' in the database.
Msg 2715, Level 16, State 1, Line 1
Column, parameter, or variable #1: Cannot find data type nosuchtype.
Msg 3701, Level 11, State 1, Line 1
Cannot drop the table 'nothere', because it does not exist or you do not have permission.
Msg 2714, Level 16, State 1, Line 2
There is already an object named 'dup1' in the database.
```

### F. Transactions

<!-- example: tsql -->
```sql
COMMIT;
ROLLBACK;
SAVE TRANSACTION s1;
```

```text
Msg 3902, Level 16, State 1, Line 1
The COMMIT TRANSACTION request has no corresponding BEGIN TRANSACTION.
Msg 3903, Level 16, State 1, Line 2
The ROLLBACK TRANSACTION request has no corresponding BEGIN TRANSACTION.
Msg 628, Level 16, State 1, Line 1
Cannot issue SAVE TRANSACTION when there is no active transaction.
```

### G. RAISERROR and THROW

<!-- example: tsql -->
```sql
RAISERROR('custom %d', 16, 1, 5);
GO
THROW 51000, 'thrown', 1;
GO
BEGIN TRY
    THROW 51001, 'caught', 1;
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS number, ERROR_SEVERITY() AS severity, ERROR_MESSAGE() AS message;
END CATCH;
```

```text
Msg 50000, Level 16, State 1, Line 1
custom 5
Msg 51000, Level 16, State 1, Line 1
thrown
number severity message
------ -------- -------
51001  16       caught

(1 row affected)
```

### H. Errors without a SQL Server number

<!-- example: tsql -->
```sql
SELECT id, COUNT(*) FROM dbo.p;
GO
SELECT id FROM dbo.p, dbo.c;
GO
CREATE TRIGGER t ON dbo.p AFTER INSERT AS SELECT 1;
```

```text
Msg 50000, Level 16, State 1, Line 1
column "p.id" must appear in the GROUP BY clause or be used in an aggregate function
Msg 50000, Level 16, State 1, Line 1
column reference "id" is ambiguous
Msg 50000, Level 16, State 1, Line 1
lexdb: CREATE TRIGGER is not supported yet (CREATE makes tables, views, indexes, schemas, sequences, types, roles and users)
```

## See also

[TRY ... CATCH](try-catch.md), [THROW](throw.md), [RAISERROR](raiserror.md),
[System functions](functions-system.md), [PostgreSQL SQLSTATEs](../postgresql/errors.md)
