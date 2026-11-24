# SELECT - INTO clause (Transact-SQL)

Makes a new table and puts the rows of a query into it.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SELECT select_list
INTO { new_table | #new_temp_table }
[ FROM table_source ... ]
[ WHERE ... ] [ GROUP BY ... ] [ HAVING ... ] [ ORDER BY ... ]
```

## Arguments

*new_table*
: The name of the new table, with its schema if wanted (`dbo.yearly`). A table of that name must not exist
  (error 2714).

*#new_temp_table*
: A local temporary table of the session. It is dropped when the session ends.

## Remarks

- The new table's columns are named and typed after the select list. Every expression needs a name.
- The table gets no primary key, indexes, constraints or defaults.
- `SELECT TOP (0) * INTO new_table FROM t` copies the columns and no rows.
- `SELECT ... INTO #temp` works on a replica too.

## Differences from SQL Server

- The new columns do not keep the source's lengths and precisions, `NOT NULL` or `IDENTITY`: an `nvarchar(30)`
  column becomes `nvarchar(max)`, a `decimal(10,2)` one a wider `decimal`, every column allows NULL, and an identity
  column becomes a plain `int` (example D).
- The `IDENTITY (type, seed, increment)` function, which numbers the new rows, is not supported (error 207).
- No `(n rows affected)` message is given for the rows put in, as SQL Server gives; the counts in the examples are
  those of the queries after it.

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int IDENTITY PRIMARY KEY, name nvarchar(30) NOT NULL, dept_id int, salary decimal(10,2));
INSERT dbo.emp (name, dept_id, salary) VALUES (N'Ann', 1, 5200), (N'Bob', 1, 4100), (N'Cid', 2, 6100), (N'Dee', 2, 6100), (N'Eve', NULL, 3000);
-->

The examples use one table:

```sql
CREATE TABLE dbo.emp (id int IDENTITY PRIMARY KEY, name nvarchar(30) NOT NULL, dept_id int, salary decimal(10,2));
INSERT dbo.emp (name, dept_id, salary) VALUES (N'Ann', 1, 5200), (N'Bob', 1, 4100), (N'Cid', 2, 6100),
  (N'Dee', 2, 6100), (N'Eve', NULL, 3000);
```

### A. A new table from a query

<!-- example: tsql -->
```sql
SELECT name, salary * 12 AS yearly INTO dbo.yearly FROM dbo.emp WHERE dept_id = 1;
SELECT * FROM dbo.yearly ORDER BY name;
```

```text
name yearly
---- --------
Ann  62400.00
Bob  49200.00

(2 rows affected)
```

### B. A temporary table

<!-- example: tsql -->
```sql
SELECT dept_id, COUNT(*) AS staff, SUM(salary) AS total
INTO #by_dept
FROM dbo.emp
GROUP BY dept_id;
SELECT * FROM #by_dept ORDER BY dept_id;
```

```text
dept_id staff total
------- ----- --------
NULL    1     3000.00
1       2     9300.00
2       2     12200.00

(3 rows affected)
```

### C. The columns only

<!-- example: tsql -->
```sql
SELECT TOP (0) * INTO dbo.emp_empty FROM dbo.emp;
SELECT COUNT(*) AS rows_in FROM dbo.emp_empty;
```

```text
rows_in
-------
0

(1 row affected)
```

### D. What the new columns keep

<!-- example: tsql -->
```sql
SELECT c.name, t.name AS type, c.max_length, c.is_nullable, c.is_identity
FROM sys.columns AS c JOIN sys.types AS t ON t.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.emp_empty')
ORDER BY c.column_id;
```

```text
name    type     max_length is_nullable is_identity
------- -------- ---------- ----------- -----------
id      int      4          1           0
name    nvarchar -1         1           0
dept_id int      4          1           0
salary  decimal  17         1           0

(4 rows affected)
```

### E. Errors

<!-- example: tsql -->
```sql
SELECT name INTO dbo.yearly FROM dbo.emp;
GO
SELECT IDENTITY(int, 1, 1) AS n, name INTO #numbered FROM dbo.emp;
GO
```

```text
Msg 2714, Level 16, State 1, Line 1
There is already an object named 'yearly' in the database.
Msg 207, Level 16, State 1, Line 1
Invalid column name 'int'.
```

## See also

[SELECT](select.md) · CREATE TABLE · [INSERT](insert.md)
