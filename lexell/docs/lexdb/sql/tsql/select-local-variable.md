# SELECT @local_variable (Transact-SQL)

Sets one or more variables from a query, or from expressions.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SELECT { @local_variable = expression } [ ,...n ]
    [ FROM ... ] [ WHERE ... ] [ GROUP BY ... ] [ HAVING ... ] [ ORDER BY ... ]
[ ; ]
```

## Arguments

*@local_variable* `=` *expression*
: The variable and its new value, an expression of the query's columns, constants and other variables.

## Remarks

- The statement returns no result set to the client.
- When the query returns several rows, the variables end with the values of the last row, in the `ORDER BY`'s
  order. Each row's expression sees the variables as the row before left them, so
  `SELECT @list = @list + name + ',' FROM t ORDER BY id` joins the names.
- When the query returns no rows, the variables keep their values.
- `@@ROWCOUNT` is the number of rows the query returned.
- A `SELECT` that sets variables cannot also return columns (error 141).

## Differences from SQL Server

- Compound assignment (`SELECT @list += name ...`) is error 102 in a `SELECT`; write `@list = @list + name`. It
  works in `SET`.
- In one `SELECT` without `FROM`, a variable set earlier in the list is not seen by a later item:
  `SELECT @a = 1, @b = @a + 1` leaves `@b` NULL when `@a` was NULL before.
- For a joined string, `STRING_AGG ... WITHIN GROUP (ORDER BY ...)` gives a defined order and is the better
  form, in lexdb as in SQL Server.

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

### A. Several variables from one row

<!-- example: tsql -->
```sql
DECLARE @name nvarchar(30), @salary decimal(10, 2);
SELECT @name = name, @salary = salary FROM dbo.emp WHERE id = 2;
SELECT @name AS name, @salary AS salary;
```

```text
name salary
---- -------
Bob  4100.00

(1 row affected)
```

### B. An aggregate, and @@ROWCOUNT

<!-- example: tsql -->
```sql
DECLARE @staff int, @total decimal(12, 2);
SELECT @staff = COUNT(*), @total = SUM(salary) FROM dbo.emp;
SELECT @staff AS staff, @total AS total, @@ROWCOUNT AS rows_read;
```

```text
staff total    rows_read
----- -------- ---------
3     15400.00 1

(1 row affected)
```

### C. Several rows: the last one wins; no row: nothing changes

<!-- example: tsql -->
```sql
DECLARE @name nvarchar(30) = N'none';
SELECT @name = name FROM dbo.emp WHERE id = 99;
SELECT @name AS after_no_row;
SELECT @name = name FROM dbo.emp ORDER BY id;
SELECT @name AS after_three_rows;
```

```text
after_no_row
------------
none

(1 row affected)

after_three_rows
----------------
Cid

(1 row affected)
```

### D. Join strings row by row

<!-- example: tsql -->
```sql
DECLARE @list nvarchar(200) = N'';
SELECT @list = @list + name + N';' FROM dbo.emp ORDER BY salary DESC;
SELECT @list AS list;
```

```text
list
------------
Cid;Ann;Bob;

(1 row affected)
```

### E. Errors

<!-- example: tsql -->
```sql
DECLARE @a int;
SELECT @a = id, name FROM dbo.emp;
GO
DECLARE @n int = 0;
SELECT @n += id FROM dbo.emp;
GO
```

```text
Msg 141, Level 16, State 1, Line 1
A SELECT statement that assigns a value to a variable must not be combined with data-retrieval operations.
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near '='.
```

## See also

[DECLARE @local_variable](declare-local-variable.md) · [SET @local_variable](set-local-variable.md) ·
[SELECT](select.md)
