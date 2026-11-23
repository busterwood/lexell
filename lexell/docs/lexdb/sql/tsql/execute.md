# EXECUTE (Transact-SQL)

Runs a stored procedure, a system procedure, or a string of T-SQL (dynamic SQL).

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
-- a procedure
{ EXEC | EXECUTE }
    [ @return_status = ] procedure_name
    [ [ @parameter = ] { value | @variable [ OUTPUT | OUT ] | DEFAULT } ] [ ,...n ]
    [ WITH RECOMPILE ]
[ ; ]

-- a string
{ EXEC | EXECUTE } ( { @string_variable | [ N ]'tsql_string' } [ + ...n ] )
[ ; ]
```

## Arguments

`@return_status`
: A variable that gets the procedure's return code (see [RETURN](return.md)).

*procedure_name*
: A procedure of the user's (`dbo.by_dept`), or a system procedure (`sp_executesql`, `sp_rename`, `sp_tables` ...).
  A batch that starts with a procedure's name runs it without `EXEC`.

`@parameter =` *value*
: An argument by name. Without names, the arguments go to the parameters in order. Named and positional arguments
  may be mixed, the positional ones first.

`OUTPUT`, `OUT`
: The parameter is an output parameter: the variable gets its value when the procedure ends.

`DEFAULT`
: The parameter's default value. For a parameter without a default it is error 201, as a missing argument is.

`WITH RECOMPILE`
: Read and ignored.

`(` *string* `)`
: A string of T-SQL, run as a batch of its own. Strings and variables may be joined with `+`.

## Remarks

- Dynamic SQL runs in its own scope: it cannot see the caller's variables (error 137). To pass values in and out,
  use `sp_executesql` with parameters (example D).
- `INSERT ... EXEC` puts the rows of a procedure's or a string's result set into a table or table variable. See
  [INSERT](insert.md).
- Errors: an unknown procedure is 2812, a missing argument 201, an unknown parameter name 8145, `OUTPUT` with a
  constant 179 (which stops the whole batch, as a syntax error does), a value that does not convert 8114.
- See [CREATE PROCEDURE](create-procedure.md) for procedures.

## Differences from SQL Server

- `EXECUTE AS` (and `EXEC AS`) is not supported: it is read as a procedure named `as` (error 2812). `REVERT` is not
  available.
- `EXEC (...) AT linked_server` is error 102: lexdb has no linked servers.

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept int);
INSERT dbo.emp VALUES (1, N'Ann', 1), (2, N'Bob', 1), (3, N'Cid', 2);
-->

The examples use one table:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept int);
INSERT dbo.emp VALUES (1, N'Ann', 1), (2, N'Bob', 1), (3, N'Cid', 2);
```

### A. A procedure with an output parameter and a return code

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.by_dept @dept int, @n int OUTPUT AS
BEGIN
    SELECT id, name FROM dbo.emp WHERE dept = @dept ORDER BY id;
    SET @n = @@ROWCOUNT;
    RETURN 7;
END
GO
DECLARE @count int, @rc int;
EXEC @rc = dbo.by_dept @dept = 1, @n = @count OUTPUT;
SELECT @count AS n, @rc AS return_code;
```

```text
id name
-- ----
1  Ann
2  Bob

(2 rows affected)

n return_code
- -----------
2 7

(1 row affected)
```

### B. Arguments by position, and without EXEC

<!-- example: tsql -->
```sql
DECLARE @count int;
EXECUTE dbo.by_dept 2, @count OUT;
SELECT @count AS n;
GO
dbo.by_dept 1, NULL
```

```text
id name
-- ----
3  Cid

(1 row affected)

n
-
1

(1 row affected)

id name
-- ----
1  Ann
2  Bob

(2 rows affected)
```

### C. A string

<!-- example: tsql -->
```sql
EXEC ('SELECT COUNT(*) AS n FROM dbo.emp');
DECLARE @table sysname = N'dbo.emp', @sql nvarchar(200);
SET @sql = N'SELECT MAX(id) AS top_id FROM ' + @table;
EXEC (@sql);
```

```text
n
-
3

(1 row affected)

top_id
------
3

(1 row affected)
```

### D. sp_executesql with parameters

<!-- example: tsql -->
```sql
EXEC sp_executesql N'SELECT name FROM dbo.emp WHERE dept = @d ORDER BY id', N'@d int', @d = 1;
DECLARE @out int;
EXEC sp_executesql N'SELECT @c = COUNT(*) FROM dbo.emp', N'@c int OUTPUT', @c = @out OUTPUT;
SELECT @out AS counted;
```

```text
name
----
Ann
Bob

(2 rows affected)

counted
-------
3

(1 row affected)
```

### E. INSERT ... EXEC

<!-- example: tsql -->
```sql
DECLARE @t TABLE (id int, name nvarchar(30));
INSERT @t EXEC ('SELECT id, name FROM dbo.emp WHERE dept = 2');
SELECT * FROM @t;
```

```text
(1 row affected)

id name
-- ----
3  Cid

(1 row affected)
```

### F. Errors

<!-- example: tsql -->
```sql
EXEC dbo.by_dept;
EXEC dbo.by_dept @dept = 1, @n = NULL, @extra = 3;
EXEC dbo.by_dept @dept = 'abc', @n = NULL;
EXEC dbo.nothere;
GO
EXEC dbo.by_dept @dept = 1, @n = 5 OUTPUT;
GO
DECLARE @x int = 5;
EXEC ('SELECT @x AS x');
GO
EXECUTE AS USER = 'dbo';
GO
```

```text
Msg 201, Level 16, State 4, Line 1
Procedure or function 'by_dept' expects parameter '@dept', which was not supplied.
Msg 8145, Level 16, State 2, Line 1
@extra is not a parameter for procedure by_dept.
Msg 8114, Level 16, State 1, Line 1
Error converting data type varchar to int.
Msg 2812, Level 16, State 62, Line 1
Could not find stored procedure 'nothere'.
Msg 179, Level 16, State 1, Line 1
Cannot use the OUTPUT option when passing a constant to a stored procedure.
Msg 137, Level 16, State 1, Line 1
Must declare the scalar variable "@x".
Msg 2812, Level 16, State 62, Line 1
Could not find stored procedure 'as'.
```

## See also

[CREATE PROCEDURE](create-procedure.md) · [RETURN](return.md) · [INSERT](insert.md) · [System procedures](system-procedures.md)
