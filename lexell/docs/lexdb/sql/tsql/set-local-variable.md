# SET @local_variable (Transact-SQL)

Gives a variable a value.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SET @local_variable { = | += | -= | *= | /= | %= | &= | ^= | |= } expression
[ ; ]
```

## Arguments

*@local_variable*
: A variable declared earlier in the batch (error 137 if not).

`=` *expression*
: The new value: a constant, a variable, an expression, a function's value, or a scalar subquery in parentheses.

`+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `^=`, `|=`
: Compound assignment: `SET @n += 1` is `SET @n = @n + 1`. `+=` joins strings too.

## Remarks

- `SET` sets one variable. To set several from one query, use [SELECT @local_variable](select-local-variable.md).
- A subquery that returns no row sets the variable to NULL; one that returns more than one row is error 512, and
  the variable keeps its value.
- The value is converted to the variable's type; a value out of range is an error (8115 for an `int` overflow) and
  the variable keeps its value.

## Differences from SQL Server

- A string too long for the variable is error 2628; SQL Server cuts it without an error. See
  [DECLARE](declare-local-variable.md).
- `SET @cursor_variable = CURSOR ...` is not supported: lexdb has no cursors.

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), salary decimal(10, 2));
INSERT dbo.emp VALUES (1, N'Ann', 5200), (2, N'Bob', 4100), (3, N'Cid', 6100);
-->

The examples use one table:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), salary decimal(10, 2));
INSERT dbo.emp VALUES (1, N'Ann', 5200), (2, N'Bob', 4100), (3, N'Cid', 6100);
```

### A. Set and compound assignment

<!-- example: tsql -->
```sql
DECLARE @n int = 5, @s nvarchar(20) = N'a';
SET @n = @n * 2;
SET @n += 3;
SET @n %= 5;
SET @s += N'bc';
SELECT @n AS n, @s AS s;
```

```text
n s
- ---
3 abc

(1 row affected)
```

### B. A value from a query

<!-- example: tsql -->
```sql
DECLARE @top decimal(10, 2), @who nvarchar(30);
SET @top = (SELECT MAX(salary) FROM dbo.emp);
SET @who = (SELECT name FROM dbo.emp WHERE salary = @top);
SELECT @top AS top_salary, @who AS who;
SET @who = (SELECT name FROM dbo.emp WHERE id = 99);
SELECT @who AS no_row;
```

```text
top_salary who
---------- ---
6100.00    Cid

(1 row affected)

no_row
------
NULL

(1 row affected)
```

### C. Functions and expressions

<!-- example: tsql -->
```sql
DECLARE @d date = '2026-01-31', @msg nvarchar(100);
SET @d = DATEADD(month, 1, @d);
SET @msg = CONCAT(N'Due on ', CONVERT(nvarchar(10), @d, 23), N'.');
SELECT @msg AS msg;
```

```text
msg
------------------
Due on 2026-02-28.

(1 row affected)
```

### D. Errors

<!-- example: tsql -->
```sql
DECLARE @m decimal(10, 2) = 1, @i int = 2147483647;
SET @m = (SELECT salary FROM dbo.emp);
SET @i = @i + 1;
SELECT @m AS m, @i AS i;
GO
SET @nothere = 1;
GO
```

```text
Msg 512, Level 16, State 1, Line 1
more than one row returned by a subquery used as an expression
Msg 8115, Level 16, State 1, Line 1
integer out of range
m    i
---- ----------
1.00 2147483647

(1 row affected)

Msg 137, Level 16, State 1, Line 1
Must declare the scalar variable "@nothere".
```

## See also

[DECLARE @local_variable](declare-local-variable.md) · [SELECT @local_variable](select-local-variable.md)
