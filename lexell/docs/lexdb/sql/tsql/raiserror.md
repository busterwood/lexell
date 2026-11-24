# RAISERROR (Transact-SQL)

Raises an error with a formatted message, or with a low severity sends a message without an error.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
RAISERROR ( { msg_str | @local_variable } , severity , state [ , argument [ ,...n ] ] )
    [ WITH option [ ,...n ] ]
[ ; ]
```

## Arguments

*msg_str*
: The message, with placeholders that the arguments fill: `%d`, `%i` and `%u` (an integer), `%s` (a string),
  `%x` and `%X` (an integer in hexadecimal). `%%` is a percent sign. A placeholder with no argument left gives
  `(null)`.

*severity*
: 0 to 10: an informational message, not an error; the batch goes on and `TRY` does not catch it. 11 to 18: an
  error that the batch goes on after, or that `CATCH` handles. 19 to 25: needs `WITH LOG` (SQL Server also wants the
  `sysadmin` role); without it the error is 2754. From 20 the error is fatal: see Remarks. A severity above 25 is
  read as 25.

*state*
: A number from 0 to 255, for the reader.

*argument*
: The values for the placeholders, in order.

`WITH` *option*
: `LOG`, `SETERROR` and `NOWAIT`. `LOG` allows a severity of 19 or more. `SETERROR` makes `@@ERROR` 50000 whatever
  the severity (even 5). `NOWAIT` is read.

## Remarks

- The error number is 50000.
- Unlike [THROW](throw.md), an error raised by `RAISERROR` does not end the batch: the next statement runs. In a `TRY`
  block, the `CATCH` block runs.
- `@@ERROR` is 50000 after an error raised this way, and 0 after the next statement that succeeds.
- **Severity 19 to 25.** Without `WITH LOG` the statement is error 2754 (severity 16): a `TRY` block catches that
  error, with `ERROR_NUMBER()` 2754. With `WITH LOG`, severity 19 is an ordinary error 50000 of severity 19 and the
  session stays open. At severity 20 and above it is fatal, as in SQL Server: the client gets the message (50000,
  severity 20 or more), then 2745 and 596 (the session is in the kill state), and the connection is closed. A `TRY`
  block does not catch it. A client has to connect again.

## Differences from SQL Server

- A message number instead of a string (`RAISERROR(50005, 16, 1)`) is taken as the text of the number; lexdb has no
  `sys.messages` and no `sp_addmessage`.
- `WITH LOG` writes nothing to a log, and `WITH NOWAIT` changes nothing: messages are sent at the end of each
  statement.
- A width, precision or flags in a placeholder (`%5d`, `%-6s`) are read and not used. `%o` gives the value in
  decimal, not octal.

## Examples

### A. An error, and the batch goes on

<!-- example: tsql -->
```sql
RAISERROR('Simple message', 16, 1);
SELECT 'the batch went on' AS result;
```

```text
Msg 50000, Level 16, State 1, Line 1
Simple message
result
-----------------
the batch went on

(1 row affected)
```

### B. Placeholders

<!-- example: tsql -->
```sql
RAISERROR('Value %d of %s is wrong', 16, 1, 42, N'balance');
RAISERROR('[%5d] [%-6s] [%x] 100%%', 16, 2, 42, N'ab', 255);
```

```text
Msg 50000, Level 16, State 1, Line 1
Value 42 of balance is wrong
Msg 50000, Level 16, State 2, Line 2
[42] [ab] [ff] 100%
```

### C. Informational messages

<!-- example: tsql -->
```sql
RAISERROR('step 1 done', 0, 1) WITH NOWAIT;
RAISERROR('severity 10 is a message too', 10, 1);
```

```text
step 1 done
severity 10 is a message too
```

### D. @@ERROR

<!-- example: tsql -->
```sql
RAISERROR('failed', 16, 1);
SELECT @@ERROR AS error_now;
SELECT @@ERROR AS error_after;
```

```text
Msg 50000, Level 16, State 1, Line 1
failed
error_now
---------
50000

(1 row affected)

error_after
-----------
0

(1 row affected)
```

### E. A message number

<!-- example: tsql -->
```sql
RAISERROR(50005, 16, 1);
```

```text
Msg 50000, Level 16, State 1, Line 1
50005
```

### F. Severity 19 and above

<!-- example: tsql -->
```sql
RAISERROR('too severe', 19, 1);
GO
RAISERROR('severe, logged', 19, 1) WITH LOG;
SELECT 'the session is still open' AS state;
GO
BEGIN TRY
    RAISERROR('severe, caught', 20, 1);
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS number, ERROR_SEVERITY() AS severity;
END CATCH
GO
RAISERROR('minor', 5, 1) WITH SETERROR;
SELECT @@ERROR AS error_now;
GO
```

```text
Msg 2754, Level 16, State 1, Line 1
Error severity levels greater than 18 can only be specified by members of the sysadmin role, using the WITH LOG option.
Msg 50000, Level 19, State 1, Line 1
severe, logged
state
-------------------------
the session is still open

(1 row affected)

number severity
------ --------
2754   16

(1 row affected)

minor
error_now
---------
50000

(1 row affected)
```

### G. A fatal error closes the connection

At severity 20 and above, with `WITH LOG`, the client gets the message and the connection is closed. The Microsoft
JDBC driver of the checker reports the message, then (as `Msg 0`) that the connection is closed; a client that
reads on gets 2745 and 596 after the message. This example is last on the page because the checker's connection does
not survive it.

<!-- example: tsql -->
```sql
RAISERROR('fatal', 20, 1) WITH LOG;
GO
```

```text
Msg 50000, Level 20, State 1, Line 1
fatal
Msg 0, Level 16, State 1, Line 1
The connection is closed.
Msg 0, Level 16, State 1, Line 1
The connection is closed.
```

## See also

[THROW](throw.md) · [TRY...CATCH](try-catch.md) · [PRINT](print.md)
