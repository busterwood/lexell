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
: 0 to 10: an informational message, not an error; the batch goes on and `TRY` does not catch it. 11 to 16: an
  error that the batch goes on after, or that `CATCH` handles.

*state*
: A number from 0 to 255, for the reader.

*argument*
: The values for the placeholders, in order.

`WITH` *option*
: `NOWAIT`, `LOG` and `SETERROR` are read.

## Remarks

- The error number is 50000.
- Unlike [THROW](throw.md), an error raised by `RAISERROR` does not end the batch: the next statement runs. In a `TRY`
  block, the `CATCH` block runs.
- `@@ERROR` is 50000 after an error raised this way, and 0 after the next statement that succeeds.

## Differences from SQL Server

- A message number instead of a string (`RAISERROR(50005, 16, 1)`) is taken as the text of the number; lexdb has no
  `sys.messages` and no `sp_addmessage`.
- `WITH LOG`, `WITH NOWAIT` and `WITH SETERROR` change nothing: messages are sent at the end of each statement.
- A width, precision or flags in a placeholder (`%5d`, `%-6s`) are read and not used. `%o` gives the value in
  decimal, not octal.
- **Severity 20 or more makes the session stop answering**: after `RAISERROR('fatal', 20, 1)` the client waits for
  an answer that does not come. SQL Server ends the connection. Severities 19 and less are taken as 16 is (SQL Server
  needs `WITH LOG` from 19).

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
Msg 50000, Level 16, State 2, Line 1
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

## See also

[THROW](throw.md) · [TRY...CATCH](try-catch.md) · [PRINT](print.md)
