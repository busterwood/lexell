# CREATE PROCEDURE (Transact-SQL)

Makes a stored procedure: a named batch of T-SQL with parameters, run by `EXECUTE`. `ALTER PROCEDURE` and
`CREATE OR ALTER PROCEDURE` replace one.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
{ CREATE [ OR ALTER ] | ALTER } { PROC | PROCEDURE } [ schema_name. ] procedure_name
    [ { @parameter [ AS ] data_type } [ = default ] [ OUT | OUTPUT ] [ READONLY ] ] [ ,...n ]
AS
    { sql_statement [ ; ] [ ...n ] | BEGIN sql_statement [ ; ] [ ...n ] END }
[ ; ]
```

## Arguments

`OR ALTER`
: Replaces the procedure if it exists; otherwise makes it.

`ALTER`
: Replaces a procedure that exists (error 208 if it does not). Its permissions stay.

*procedure_name*
: The procedure's name, with its schema (`dbo` by default).

*@parameter* *data_type*
: A parameter. Any type a column may have, or a table type with `READONLY` (a table-valued parameter).

`=` *default*
: The value when the caller gives none, or gives `DEFAULT`. A parameter without a default must be given (error 201).

`OUTPUT`, `OUT`
: An output parameter: its value at the end goes back to the caller's variable.

*sql_statement*
: The body: any statements a batch may hold, including `DECLARE`, `IF`, `WHILE`, `TRY...CATCH`, transactions, and
  calls of other procedures. Everything after `AS` up to the end of the batch is the body.

## Remarks

- `CREATE PROCEDURE` must be the first statement of its batch (error 111): put `GO` before and after it.
- A name already used is error 2714.
- Inside the procedure, `@@NESTLEVEL` is its call depth and `@@PROCID` its object id; `ERROR_PROCEDURE()` names it in
  a `CATCH` block. Procedures may call themselves.
- `RETURN n` gives the return code; without it the code is 0.
- `sys.procedures`, `sys.parameters`, `sys.sql_modules` and `OBJECT_DEFINITION` show the procedure; `sp_stored_procedures`
  and `sp_sproc_columns` list them for drivers.
- Running a procedure needs `EXECUTE` permission on it (see GRANT); its body runs with its owner's rights.

## Differences from SQL Server

- `WITH EXECUTE AS ...` is error 102. `WITH ENCRYPTION` is taken.
- A parameter's type is not checked when the procedure is made: an unknown table type is found only at the call.
- A table-valued parameter cannot be passed from a T-SQL batch: `EXEC dbo.p @ids = @list` gives error 207
  ("Invalid column name '#tv_list'"). Clients that send it as an RPC parameter (ADO.NET, mssql-jdbc's
  `SQLServerDataTable`) work (lexdb-tds.md 16).

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

### A. Parameters, a default and an output parameter

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.add_bonus @dept int, @bonus decimal(10,2) = 100, @changed int = NULL OUTPUT
AS
BEGIN
    SET NOCOUNT ON;
    UPDATE dbo.emp SET salary = salary + @bonus WHERE dept = @dept;
    SET @changed = @@ROWCOUNT;
    RETURN 0;
END
GO
DECLARE @n int;
EXEC dbo.add_bonus 1, @changed = @n OUTPUT;
SELECT @n AS changed;
SELECT name, salary FROM dbo.emp ORDER BY id;
```

```text
changed
-------
2

(1 row affected)

name salary
---- -------
Ann  5300.00
Bob  4200.00
Cid  6100.00

(3 rows affected)
```

### B. Result sets, and nesting

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.inner_proc AS SELECT @@NESTLEVEL AS inner_level;
GO
CREATE PROCEDURE dbo.outer_proc AS
BEGIN
    SELECT @@NESTLEVEL AS outer_level, OBJECT_NAME(@@PROCID) AS me;
    EXEC dbo.inner_proc;
END
GO
EXEC dbo.outer_proc;
```

```text
outer_level me
----------- ----------
1           outer_proc

(1 row affected)

inner_level
-----------
2

(1 row affected)
```

### C. CREATE OR ALTER and ALTER

<!-- example: tsql -->
```sql
CREATE OR ALTER PROCEDURE dbo.staff AS SELECT COUNT(*) AS n FROM dbo.emp;
GO
EXEC dbo.staff;
GO
ALTER PROCEDURE dbo.staff @dept int AS SELECT COUNT(*) AS n FROM dbo.emp WHERE dept = @dept;
GO
EXEC dbo.staff 2;
SELECT OBJECT_DEFINITION(OBJECT_ID('dbo.staff')) AS definition;
```

```text
n
-
3

(1 row affected)

n
-
1

(1 row affected)

definition
----------------------------------------------------------------------------------------------
CREATE PROCEDURE dbo.staff @dept int AS SELECT COUNT(*) AS n FROM dbo.emp WHERE dept = @dept;

(1 row affected)
```

### D. An error inside a procedure

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.divide @a int, @b int AS SELECT @a / @b AS q;
GO
BEGIN TRY
    EXEC dbo.divide 1, 0;
END TRY
BEGIN CATCH
    SELECT ERROR_NUMBER() AS number, ERROR_PROCEDURE() AS in_procedure;
END CATCH;
```

```text
number in_procedure
------ ------------
8134   divide

(1 row affected)
```

### E. A procedure that calls itself

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.countdown @n int AS
BEGIN
    IF @n > 0
    BEGIN
        SELECT @n AS n;
        DECLARE @m int = @n - 1;
        EXEC dbo.countdown @m;
    END
END
GO
EXEC dbo.countdown 2;
```

```text
n
-
2

(1 row affected)

n
-
1

(1 row affected)
```

### F. The catalog

<!-- example: tsql -->
```sql
SELECT name, type_desc FROM sys.procedures ORDER BY name;
SELECT p.name, t.name AS type, p.is_output
FROM sys.parameters AS p JOIN sys.types AS t ON t.user_type_id = p.user_type_id
WHERE p.object_id = OBJECT_ID('dbo.add_bonus') ORDER BY p.parameter_id;
```

```text
name       type_desc
---------- --------------------
add_bonus  SQL_STORED_PROCEDURE
countdown  SQL_STORED_PROCEDURE
divide     SQL_STORED_PROCEDURE
inner_proc SQL_STORED_PROCEDURE
outer_proc SQL_STORED_PROCEDURE
staff      SQL_STORED_PROCEDURE

(6 rows affected)

name     type    is_output
-------- ------- ---------
@dept    int     0
@bonus   decimal 0
@changed int     1

(3 rows affected)
```

### G. Errors

<!-- example: tsql -->
```sql
SELECT 1 AS one;
CREATE PROCEDURE dbo.late AS SELECT 1;
GO
CREATE PROCEDURE dbo.staff AS SELECT 1;
GO
ALTER PROCEDURE dbo.nothere AS SELECT 1;
GO
CREATE PROCEDURE dbo.as_owner WITH EXECUTE AS OWNER AS SELECT 1;
GO
```

```text
Msg 111, Level 16, State 1, Line 2
'CREATE/ALTER PROCEDURE' must be the first statement in a query batch.
Msg 2714, Level 16, State 1, Line 1
There is already an object named 'staff' in the database.
Msg 208, Level 16, State 1, Line 1
Invalid object name 'dbo.nothere'.
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'owner'.
```

## See also

[EXECUTE](execute.md) · [DROP PROCEDURE](drop-procedure.md) · [RETURN](return.md) · [CREATE FUNCTION](create-function.md) ·
[CREATE TYPE](create-type.md) · [System procedures](system-procedures.md)
