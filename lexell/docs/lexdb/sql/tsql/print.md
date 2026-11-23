# PRINT (Transact-SQL)

Sends a message to the client.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
PRINT msg_str | @local_variable | string_expr
[ ; ]
```

## Arguments

*msg_str*, *@local_variable*, *string_expr*
: A string, a variable, or an expression whose value is converted to a string.

## Remarks

- The message goes to the client as an informational message, not a result set: sqlcmd and SSMS show it in the
  messages, JDBC as a warning on the statement.
- A NULL prints an empty line.
- [RAISERROR](raiserror.md) with severity 0 to 10 sends a message too, and can format it.

## Differences from SQL Server

- None known.

## Examples

### A. Strings, numbers and expressions

<!-- example: tsql -->
```sql
PRINT 'Total: ' + CAST(42 AS varchar(10));
PRINT 42;
PRINT N'Unicode: é ü ß';
PRINT CONCAT('a', 1, NULL, 'b');
```

```text
Total: 42
42
Unicode: é ü ß
a1b
```

### B. A variable, and NULL

<!-- example: tsql -->
```sql
CREATE TABLE dbo.t (id int);
DECLARE @who nvarchar(20) = N'Ann', @none nvarchar(20);
SELECT COUNT(*) AS n FROM dbo.t;
PRINT N'Hello, ' + @who;
PRINT @none;
PRINT 'after the empty line';
```

```text
n
-
0

(1 row affected)

Hello, Ann

after the empty line
```

### C. A message right after SET and DECLARE

<!-- example: tsql -->
```sql
SET NOCOUNT ON;
PRINT 'after SET';
DECLARE @x int = 1;
PRINT 'after DECLARE';
SELECT @x AS x;
```

```text
after SET
after DECLARE
x
-
1

(1 row affected)
```

## See also

[RAISERROR](raiserror.md) · [THROW](throw.md)
