# DECLARE @local_variable (Transact-SQL)

Declares variables and table variables in a batch or a procedure's body, with an optional first value.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DECLARE
{
    @local_variable [ AS ] data_type [ = value ]
  | @table_variable_name [ AS ] TABLE ( { column_definition | table_constraint } [ ,...n ] )
} [ ,...n ]
[ ; ]
```

## Arguments

*@local_variable*
: The variable's name, starting with `@`. Names do not depend on case: `@MyVar` and `@myvar` are one variable.

*data_type*
: Any type a column may have, such as `int`, `decimal(10, 2)`, `nvarchar(50)`, `nvarchar(max)`, `date`,
  `datetime2`, `uniqueidentifier`, `bit` or `xml`.

`=` *value*
: The first value: a constant, a variable, an expression or a scalar subquery. Without it, the variable is NULL.

*@table_variable_name* `TABLE (...)`
: A table variable: a table that lasts for the batch. Its columns and constraints are written as in
  [CREATE TABLE](create-table.md): `PRIMARY KEY`, `UNIQUE`, `DEFAULT`, `IDENTITY`, `CHECK`. It is read and changed
  with `SELECT`, `INSERT`, `UPDATE`, `DELETE` and `MERGE`, and may be the target of `OUTPUT ... INTO` and
  `INSERT ... EXEC`.

## Remarks

- A variable lasts until the end of its batch: after `GO` it is gone (error 137). It is seen in the whole batch
  after its `DECLARE`, also inside `IF`, `WHILE` and `TRY` blocks.
- A variable declared twice in a batch is error 134; a variable not declared is error 137.
- A value is converted to the variable's type as on assignment: a decimal is rounded to the scale, `bit` takes 1 for
  any number but 0, a string that is not a number for an `int` is error 245.
- Set a variable with [SET @local_variable](set-local-variable.md) or
  [SELECT @local_variable](select-local-variable.md).

## Differences from SQL Server

- **A string too long for the variable is error 2628**, and the variable stays NULL; SQL Server cuts the string to
  the variable's length without an error.
- `DECLARE @c CURSOR` is error 50000 ("DECLARE of a table or cursor variable is not supported yet"), and
  `DECLARE name CURSOR FOR ...` is error 102: lexdb has no cursors.
- **`ROLLBACK` undoes the changes to a table variable** (example D); in SQL Server a table variable keeps them.
- A table variable is a temporary table of the session named `#@name`. A table variable used after its batch is
  error 208, "Invalid object name '#@t'" (SQL Server: 1087, "Must declare the table variable "@t"").

## Examples

### A. Variables with and without a first value

<!-- example: tsql -->
```sql
DECLARE @a int, @b nvarchar(10) = N'ten', @c AS decimal(5, 2) = 1.239, @d date = '2026-11-23';
SELECT @a AS a, @b AS b, @c AS c, @d AS d;
```

```text
a    b   c    d
---- --- ---- ----------
NULL ten 1.24 2026-11-23

(1 row affected)
```

### B. A first value from a query

<!-- example: tsql -->
```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), salary decimal(10, 2));
INSERT dbo.emp VALUES (1, N'Ann', 5200), (2, N'Bob', 4100), (3, N'Cid', 6100);
DECLARE @top decimal(10, 2) = (SELECT MAX(salary) FROM dbo.emp),
        @staff int = (SELECT COUNT(*) FROM dbo.emp);
SELECT @top AS top_salary, @staff AS staff;
```

```text
(3 rows affected)

top_salary staff
---------- -----
6100.00    3

(1 row affected)
```

### C. A table variable

<!-- example: tsql -->
```sql
DECLARE @pay TABLE (id int PRIMARY KEY, amount decimal(10, 2) NOT NULL, note nvarchar(20) DEFAULT N'none',
                    seq int IDENTITY(1, 1));
INSERT @pay (id, amount) SELECT id, salary / 12 FROM dbo.emp WHERE salary > 5000;
UPDATE @pay SET note = N'high' WHERE amount > 500;
SELECT * FROM @pay ORDER BY id;
```

```text
(2 rows affected)

(1 row affected)

id amount note seq
-- ------ ---- ---
1  433.33 none 1
3  508.33 high 2

(2 rows affected)
```

### D. A table variable and ROLLBACK

<!-- example: tsql -->
```sql
DECLARE @log TABLE (step int);
BEGIN TRAN;
INSERT @log VALUES (1), (2);
ROLLBACK;
SELECT COUNT(*) AS rows_after_rollback FROM @log;
```

```text
(2 rows affected)

rows_after_rollback
-------------------
0

(1 row affected)
```

### E. Names do not depend on case

<!-- example: tsql -->
```sql
DECLARE @MyCount int = 3;
SELECT @mycount AS mycount;
```

```text
mycount
-------
3

(1 row affected)
```

### F. A variable lasts for its batch

<!-- example: tsql -->
```sql
DECLARE @x int = 1;
GO
SELECT @x;
GO
```

```text
Msg 137, Level 16, State 1, Line 1
Must declare the scalar variable "@x".
```

### G. Errors

<!-- example: tsql -->
```sql
DECLARE @i int = 'abc';
DECLARE @s varchar(3) = 'abcdef';
SELECT @s AS s;
GO
DECLARE @j int;
DECLARE @j int;
GO
DECLARE @cur CURSOR;
GO
```

```text
Msg 245, Level 16, State 1, Line 1
invalid input syntax for type integer: "abc"
Msg 2628, Level 16, State 1, Line 2
value too long for type character varying(3)
s
----
NULL

(1 row affected)

Msg 134, Level 16, State 1, Line 2
The variable name '@j' has already been declared. Variable names must be unique within a query batch or stored procedure.
Msg 50000, Level 16, State 1, Line 1
DECLARE of a table or cursor variable is not supported yet
```

## See also

[SET @local_variable](set-local-variable.md) · [SELECT @local_variable](select-local-variable.md) ·
[CREATE TABLE](create-table.md) · [IF...ELSE](if-else.md)
