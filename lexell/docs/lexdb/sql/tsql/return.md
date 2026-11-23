# RETURN (Transact-SQL)

Leaves a batch, a block or a procedure at once. In a procedure it may give a return code; in a function it gives the
function's value.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
RETURN [ integer_expression ]
```

## Arguments

*integer_expression*
: In a procedure, the return code, an `int`, which `EXEC @rc = procedure` receives. Without it a procedure returns
  0. In a scalar function, the function's value.

## Remarks

- In a batch, `RETURN` ends the batch; the statements after it do not run. A batch's `RETURN` cannot give a value
  (error 178).
- In a procedure, `RETURN` ends the procedure, and the caller goes on.

## Differences from SQL Server

- None known.

## Examples

### A. Leave a batch

<!-- example: tsql -->
```sql
PRINT 'first';
RETURN;
PRINT 'not reached';
```

```text
first
```

### B. A procedure's return code

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.check_qty @qty int AS
BEGIN
    IF @qty < 0 RETURN 1;
    IF @qty = 0 RETURN 2;
    RETURN;
END
GO
DECLARE @a int, @b int, @c int;
EXEC @a = dbo.check_qty -5;
EXEC @b = dbo.check_qty 0;
EXEC @c = dbo.check_qty 9;
SELECT @a AS negative, @b AS zero, @c AS positive;
```

```text
negative zero positive
-------- ---- --------
1        2    0

(1 row affected)
```

### C. Errors

<!-- example: tsql -->
```sql
RETURN 5;
```

```text
Msg 178, Level 15, State 1, Line 1
A RETURN statement with a return value cannot be used in this context.
```

## See also

[EXECUTE](execute.md) · [CREATE PROCEDURE](create-procedure.md) · [CREATE FUNCTION](create-function.md)
