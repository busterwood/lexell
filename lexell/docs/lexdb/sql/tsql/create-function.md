# CREATE FUNCTION (Transact-SQL)

Makes a function of the user's: a scalar function, which returns one value, or a table-valued function, which
returns rows. `ALTER FUNCTION` and `CREATE OR ALTER FUNCTION` replace one.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
-- scalar function
{ CREATE [ OR ALTER ] | ALTER } FUNCTION [ schema_name. ] function_name
    ( [ @parameter [ AS ] data_type [ = default ] [ ,...n ] ] )
RETURNS return_data_type
    [ WITH SCHEMABINDING ]
[ AS ]
BEGIN
    function_body
    RETURN scalar_expression
END
[ ; ]

-- inline table-valued function
{ CREATE [ OR ALTER ] | ALTER } FUNCTION [ schema_name. ] function_name
    ( [ @parameter [ AS ] data_type [ = default ] [ ,...n ] ] )
RETURNS TABLE
[ AS ]
RETURN [ ( ] select_stmt [ ) ]
[ ; ]

-- multi-statement table-valued function
{ CREATE [ OR ALTER ] | ALTER } FUNCTION [ schema_name. ] function_name
    ( [ @parameter [ AS ] data_type [ = default ] [ ,...n ] ] )
RETURNS @return_variable TABLE ( column_definition [ ,...n ] )
[ AS ]
BEGIN
    function_body
    RETURN
END
[ ; ]
```

## Arguments

*function_name*
: The function's name. It is called with its schema: `dbo.tax(...)`.

*@parameter* *data_type* [ `=` *default* ]
: A parameter. A caller passes `DEFAULT` to use the default; every argument must be given, even when it has a
  default (error 313).

`RETURNS` *return_data_type*
: The type of a scalar function's value.

*function_body*
: `DECLARE`, `SET`, `IF`, `WHILE`, `SELECT` into variables, and calls of other functions. A function cannot change
  tables: `INSERT`, `UPDATE` or `DELETE` of a table is error 443.

`RETURNS TABLE` ... `RETURN (` *select_stmt* `)`
: An inline table-valued function: one query, with the parameters as values. It is read in `FROM` like a view with
  parameters, and works with `CROSS APPLY`.

`WITH SCHEMABINDING`
: Read and taken.

## Remarks

- `CREATE FUNCTION` must be the first statement of its batch.
- A scalar function may be used wherever an expression may, and may call itself.
- `EXEC @r = dbo.f 4, 1` runs a scalar function and puts its value in `@r`, as SQL Server does (arguments by place or
  by name; a parameter with a default may be left out). This is what Microsoft's JDBC driver sends for `{? = call dbo.f(?)}`.
- `sys.objects` shows scalar functions as `SQL_SCALAR_FUNCTION`, inline ones as `SQL_INLINE_TABLE_VALUED_FUNCTION`
  and multi-statement ones as `SQL_TABLE_VALUED_FUNCTION`; `OBJECT_DEFINITION` gives the text.
- A function name without its schema is looked up as a built-in function (error 195 when there is none).

## Differences from SQL Server

- **A multi-statement table-valued function is made but cannot be used**: reading it is error 50000 ("lexdb: the
  multi-statement table-valued function squares is not supported yet (an inline one is)").
- A function of the user's cannot be used in a column's `DEFAULT`, a `CHECK` constraint, a computed column, an index
  or a view: error 50000 (lexdb-dialect-gaps.md 7a).

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept int, salary decimal(10,2));
INSERT dbo.emp VALUES (1, N'Ann', 1, 5200), (2, N'Bob', 1, 4100), (3, N'Cid', 2, 6100);
-->

The examples use one table:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept int, salary decimal(10,2));
INSERT dbo.emp VALUES (1, N'Ann', 1, 5200), (2, N'Bob', 1, 4100), (3, N'Cid', 2, 6100);
```

### A. A scalar function with a default

<!-- example: tsql -->
```sql
CREATE FUNCTION dbo.tax (@amount decimal(10,2), @rate decimal(4,2) = 0.20)
RETURNS decimal(10,2)
AS
BEGIN
    RETURN @amount * @rate;
END
GO
SELECT name, dbo.tax(salary, 0.25) AS quarter, dbo.tax(salary, DEFAULT) AS standard FROM dbo.emp ORDER BY id;
```

```text
name quarter standard
---- ------- --------
Ann  1300.00 1040.00
Bob  1025.00 820.00
Cid  1525.00 1220.00

(3 rows affected)
```

### B. Variables and a loop in the body; recursion

<!-- example: tsql -->
```sql
CREATE FUNCTION dbo.digits (@n bigint) RETURNS int AS
BEGIN
    DECLARE @count int = 1;
    WHILE @n >= 10
    BEGIN
        SET @n = @n / 10;
        SET @count += 1;
    END
    RETURN @count;
END
GO
CREATE FUNCTION dbo.fact (@n int) RETURNS bigint AS
BEGIN
    IF @n <= 1 RETURN 1;
    RETURN @n * dbo.fact(@n - 1);
END
GO
SELECT dbo.digits(123456) AS digits, dbo.fact(10) AS fact10;
```

```text
digits fact10
------ -------
6      3628800

(1 row affected)
```

### C. An inline table-valued function, and CROSS APPLY

<!-- example: tsql -->
```sql
CREATE FUNCTION dbo.staff_of (@dept int) RETURNS TABLE
AS RETURN (SELECT id, name FROM dbo.emp WHERE dept = @dept);
GO
SELECT * FROM dbo.staff_of(1) ORDER BY id;
SELECT d.n AS dept, s.name
FROM (VALUES (1), (2)) AS d (n) CROSS APPLY dbo.staff_of(d.n) AS s
ORDER BY d.n, s.name;
```

```text
id name
-- ----
1  Ann
2  Bob

(2 rows affected)

dept name
---- ----
1    Ann
1    Bob
2    Cid

(3 rows affected)
```

### D. CREATE OR ALTER, and the catalog

<!-- example: tsql -->
```sql
CREATE OR ALTER FUNCTION dbo.tax (@amount decimal(10,2), @rate decimal(4,2) = 0.20)
RETURNS decimal(10,2)
AS
BEGIN
    RETURN ROUND(@amount * @rate, 0);
END
GO
SELECT dbo.tax(1234, 0.2) AS rounded;
SELECT name, type_desc FROM sys.objects WHERE type IN ('FN', 'IF', 'TF') ORDER BY name;
```

```text
rounded
-------
247.00

(1 row affected)

name     type_desc
-------- --------------------------------
digits   SQL_SCALAR_FUNCTION
fact     SQL_SCALAR_FUNCTION
staff_of SQL_INLINE_TABLE_VALUED_FUNCTION
tax      SQL_SCALAR_FUNCTION

(4 rows affected)
```

### E. Errors

<!-- example: tsql -->
```sql
SELECT dbo.tax(100);
GO
SELECT tax(100, 0.1);
GO
CREATE FUNCTION dbo.wipe () RETURNS int AS BEGIN UPDATE dbo.emp SET salary = 0; RETURN 1; END
GO
CREATE FUNCTION dbo.squares (@n int) RETURNS @t TABLE (i int, sq int) AS
BEGIN
    DECLARE @i int = 1;
    WHILE @i <= @n BEGIN INSERT @t VALUES (@i, @i * @i); SET @i += 1; END
    RETURN;
END
GO
SELECT * FROM dbo.squares(3);
GO
```

```text
Msg 313, Level 16, State 1, Line 1
An insufficient number of arguments were supplied for the procedure or function dbo.tax.
Msg 195, Level 15, State 1, Line 1
'tax' is not a recognized built-in function name.
Msg 443, Level 16, State 1, Line 1
Invalid use of a side-effecting operator 'UPDATE' within a function.
Msg 50000, Level 16, State 1, Line 1
lexdb: the multi-statement table-valued function squares is not supported yet (an inline one is)
```

## See also

[DROP FUNCTION](drop-function.md) · [CREATE PROCEDURE](create-procedure.md) · [FROM, JOIN and APPLY](from.md)
