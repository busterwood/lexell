# DELETE (Transact-SQL)

Removes rows from a table or a table variable.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
[ WITH common_table_expression [ ,...n ] ]
DELETE
    [ TOP ( expression ) ]
    [ FROM ] { table_name | table_alias | @table_variable | #temp_table }
    [ WITH ( table_hint [ ,...n ] ) ]
    [ OUTPUT output_list [ INTO { @table_variable | table_name } [ ( column_list ) ] ] ]
    [ FROM table_source [ ,...n ] ]
    [ WHERE search_condition ]
    [ OPTION ( query_hint [ ,...n ] ) ]
[ ; ]
```

## Arguments

*common_table_expression*
: A named query the statement can read in `FROM` or `WHERE`. See [WITH](with.md).

`TOP (` *expression* `)`
: Removes at most this many rows, picked in no order. See [TOP](top.md).

`FROM` (the first)
: Optional, as in SQL Server: `DELETE dbo.t` is `DELETE FROM dbo.t`.

*table_name*, *table_alias*
: The table to remove rows from. With a second `FROM`, it may be the alias of a table there.

`WITH (` *table_hint* `)`
: Read and ignored.

`OUTPUT`
: Returns the removed rows through `DELETED`, or puts them into a table. See [OUTPUT](output.md).

`FROM` *table_source* (the second)
: Other tables, joined to the target, to choose the rows by. See [FROM, JOIN and APPLY](from.md).

`WHERE` *search_condition*
: The rows to remove. Without `WHERE`, every row goes.

## Remarks

- A foreign key that refers to a row stops its removal (error 547), unless the key has `ON DELETE CASCADE` or
  `SET NULL`, which removes or changes the rows that refer to it.
- A failed `DELETE` removes nothing; the batch goes on with the next statement unless `SET XACT_ABORT ON` or a
  `TRY ... CATCH` says otherwise.
- `@@ROWCOUNT` is the number of rows removed.
- To remove every row of a table at once, [TRUNCATE TABLE](truncate-table.md) is quicker.
- On a replica, `DELETE` from a table is error 3906; `#temp` tables and table variables can be used there.

## Differences from SQL Server

- `DELETE TOP (n) PERCENT` is not supported: `PERCENT` is read as a table name (error 208).
- A common table expression or a view cannot be the target: a CTE gives error 208, a view error 50000 ("cannot
  delete from view ... (lexdb's views are read-only)").
- `WHERE CURRENT OF` is error 102: lexdb has no cursors. There are no triggers.
- Most error messages are SQL Server's; those with number 50000 carry lexdb's text.

## Examples

<!--setup: tsql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30) NOT NULL);
CREATE TABLE dbo.emp (id int IDENTITY PRIMARY KEY, name nvarchar(30) NOT NULL, dept_id int REFERENCES dbo.dept (id), salary decimal(10,2));
INSERT dbo.dept VALUES (1, N'Sales'), (2, N'Research'), (3, N'Legal');
INSERT dbo.emp (name, dept_id, salary) VALUES (N'Ann', 1, 5200), (N'Bob', 1, 4100), (N'Cid', 2, 6100), (N'Dee', 2, 6100), (N'Eve', NULL, 3000), (N'Fay', 3, 7000);
-->

The examples use two tables:

```sql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30) NOT NULL);
CREATE TABLE dbo.emp (id int IDENTITY PRIMARY KEY, name nvarchar(30) NOT NULL,
                      dept_id int REFERENCES dbo.dept (id), salary decimal(10,2));
INSERT dbo.dept VALUES (1, N'Sales'), (2, N'Research'), (3, N'Legal');
INSERT dbo.emp (name, dept_id, salary) VALUES (N'Ann', 1, 5200), (N'Bob', 1, 4100), (N'Cid', 2, 6100),
  (N'Dee', 2, 6100), (N'Eve', NULL, 3000), (N'Fay', 3, 7000);
```

### A. Remove some rows

<!-- example: tsql -->
```sql
DELETE FROM dbo.emp WHERE dept_id IS NULL;
DELETE dbo.emp WHERE id = 99;
SELECT COUNT(*) AS staff FROM dbo.emp;
```

```text
(1 row affected)

(0 rows affected)

staff
-----
5

(1 row affected)
```

### B. Rows chosen by a join

<!-- example: tsql -->
```sql
DELETE e
FROM dbo.emp AS e
JOIN dbo.dept AS d ON d.id = e.dept_id
WHERE d.name = N'Legal';
SELECT name FROM dbo.emp ORDER BY id;
```

```text
(1 row affected)

name
----
Ann
Bob
Cid
Dee

(4 rows affected)
```

### C. Rows chosen by a subquery

<!-- example: tsql -->
```sql
DELETE FROM dbo.dept WHERE id NOT IN (SELECT dept_id FROM dbo.emp WHERE dept_id IS NOT NULL);
SELECT * FROM dbo.dept ORDER BY id;
```

```text
(1 row affected)

id name
-- --------
1  Sales
2  Research

(2 rows affected)
```

### D. TOP and OUTPUT

<!-- example: tsql -->
```sql
DELETE TOP (1) FROM dbo.emp OUTPUT DELETED.id, DELETED.name WHERE dept_id = 2;
SELECT @@ROWCOUNT AS removed;
```

```text
id name
-- ----
3  Cid

(1 row affected)

removed
-------
1

(1 row affected)
```

### E. OUTPUT INTO a table variable

<!-- example: tsql -->
```sql
DECLARE @gone TABLE (id int, name nvarchar(30));
DELETE FROM dbo.emp OUTPUT DELETED.id, DELETED.name INTO @gone WHERE salary < 5000;
SELECT * FROM @gone;
SELECT name FROM dbo.emp ORDER BY id;
```

```text
(1 row affected)

id name
-- ----
2  Bob

(1 row affected)

name
----
Ann
Dee

(2 rows affected)
```

### F. ON DELETE CASCADE

<!-- example: tsql -->
```sql
CREATE TABLE dbo.orders (id int PRIMARY KEY);
CREATE TABLE dbo.lines (order_id int REFERENCES dbo.orders (id) ON DELETE CASCADE, item nvarchar(10));
INSERT dbo.orders VALUES (1), (2);
INSERT dbo.lines VALUES (1, N'pen'), (1, N'ink'), (2, N'pad');
DELETE FROM dbo.orders WHERE id = 1;
SELECT * FROM dbo.lines;
```

```text
(2 rows affected)

(3 rows affected)

(1 row affected)

order_id item
-------- ----
2        pad

(1 row affected)
```

### G. Errors

<!-- example: tsql -->
```sql
DELETE FROM dbo.dept WHERE id = 1;
PRINT 'the batch went on';
GO
DELETE TOP (50) PERCENT FROM dbo.emp;
GO
```

```text
Msg 547, Level 16, State 1, Line 1
The DELETE statement conflicted with the REFERENCE constraint "emp_dept_id_fkey". The conflict occurred in database "lexdb", table "dbo.emp", column 'dept_id'.
the batch went on
Msg 208, Level 16, State 1, Line 1
Invalid object name 'percent'.
```

## See also

[INSERT](insert.md) · [UPDATE](update.md) · [MERGE](merge.md) · [TRUNCATE TABLE](truncate-table.md) ·
[OUTPUT clause](output.md)
