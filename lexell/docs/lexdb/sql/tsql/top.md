# TOP (Transact-SQL)

Limits the rows a query returns, or the rows an `INSERT`, `UPDATE`, `DELETE` or `MERGE` changes.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
-- in SELECT
SELECT [ ALL | DISTINCT ] TOP ( expression ) [ PERCENT ] [ WITH TIES ] select_list ...
SELECT [ ALL | DISTINCT ] TOP constant [ PERCENT ] [ WITH TIES ] select_list ...

-- in INSERT, UPDATE, DELETE and MERGE
INSERT TOP ( expression ) [ PERCENT ] [ INTO ] ...
UPDATE TOP ( expression ) [ PERCENT ] ...
DELETE TOP ( expression ) [ PERCENT ] ...
MERGE TOP ( expression ) ...
```

## Arguments

*expression*
: The number of rows: a constant, a variable or a parameter. Without parentheses only a constant is allowed.

`PERCENT`
: *expression* is a percentage of the rows, from 0 to 100, rounded up to a whole row.

`WITH TIES`
: Also returns the rows that tie with the last row by the `ORDER BY` columns. The result may have more rows than
  *expression* says.

## Remarks

- Without `ORDER BY`, which rows `TOP` returns is not defined. Use `ORDER BY` to say which.
- In `UPDATE`, `DELETE` and `MERGE`, the rows `TOP` picks are in no order. In `INSERT`, they are the first rows of
  the query (its `ORDER BY` decides which) or of the `VALUES` list. With `PERCENT`, `UPDATE` and `DELETE` take *n*
  percent of the rows they found, rounded up (examples in [DELETE](delete.md), [UPDATE](update.md) and
  [INSERT](insert.md)).
- `TOP (0)` returns no rows, and gives the result's columns.
- `TOP` without `ORDER BY` ends a recursive CTE that has no end of its own once it has its rows (see [WITH](with.md),
  example C).
- A percentage outside 0 to 100 is error 1031.
- For paging, [`OFFSET ... FETCH`](order-by.md) is the standard form. `SET ROWCOUNT n` limits every `SELECT` of
  the session.

## Differences from SQL Server

- `MERGE TOP (n) PERCENT` is error 50000 ("lexdb: MERGE TOP ... PERCENT is not supported"); SQL Server accepts it.
  `PERCENT` is taken in `SELECT`, `INSERT`, `UPDATE` and `DELETE`.
- `TOP (`*subquery*`)` is a syntax error (156), and SQL Server accepts it: put the count in a variable first.
- `TOP ... WITH TIES` without `ORDER BY` returns every row; SQL Server refuses it (error 1062).
- `TOP` with a decimal constant and no `PERCENT` (`TOP 2.5`) returns a whole number of rows (3 here); SQL Server
  refuses it (1060).
- `TOP (-1)` is error 50000 ("LIMIT must not be negative"); SQL Server gives 1014.
- `TOP` and `OFFSET` in the same query are both applied; SQL Server refuses them together (10741).

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

### A. The first rows by an order

<!-- example: tsql -->
```sql
SELECT TOP (3) name, salary FROM dbo.emp ORDER BY salary DESC, name;
```

```text
name salary
---- -------
Cid  6100.00
Dee  6100.00
Ann  5200.00

(3 rows affected)
```

### B. WITH TIES

<!-- example: tsql -->
```sql
SELECT TOP (1) name, salary FROM dbo.emp ORDER BY salary DESC;
SELECT TOP (1) WITH TIES name, salary FROM dbo.emp ORDER BY salary DESC;
```

```text
name salary
---- -------
Cid  6100.00

(1 row affected)

name salary
---- -------
Cid  6100.00
Dee  6100.00

(2 rows affected)
```

### C. PERCENT, and a variable

<!-- example: tsql -->
```sql
SELECT TOP (40) PERCENT name FROM dbo.emp ORDER BY id;
DECLARE @n int = 2;
SELECT TOP (@n) name FROM dbo.emp ORDER BY id DESC;
```

```text
name
----
Ann
Bob

(2 rows affected)

name
----
Eve
Dee

(2 rows affected)
```

### D. TOP in UPDATE and DELETE

<!-- example: tsql -->
```sql
UPDATE TOP (1) dbo.emp SET salary = salary + 100 WHERE dept_id = 2;
DELETE TOP (1) FROM dbo.emp WHERE dept_id IS NULL;
SELECT COUNT(*) AS staff, SUM(salary) AS total FROM dbo.emp;
```

```text
(1 row affected)

(1 row affected)

staff total
----- --------
4     21600.00

(1 row affected)
```

### E. To choose the rows, use a subquery

`UPDATE TOP` takes rows in no order. To change the rows first by some order, pick them in a subquery.

<!-- example: tsql -->
```sql
UPDATE dbo.emp SET salary = salary + 50
WHERE id IN (SELECT TOP (2) id FROM dbo.emp ORDER BY salary);
SELECT name, salary FROM dbo.emp ORDER BY id;
```

```text
(2 rows affected)

name salary
---- -------
Ann  5250.00
Bob  4150.00
Cid  6200.00
Dee  6100.00

(4 rows affected)
```

### F. Errors

<!-- example: tsql -->
```sql
SELECT TOP (150) PERCENT name FROM dbo.emp;
GO
SELECT TOP (SELECT COUNT(*) FROM dbo.emp) name FROM dbo.emp;
GO
```

```text
Msg 1031, Level 15, State 1, Line 1
Percent values must be between 0 and 100.
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'select'.
```

## See also

[SELECT](select.md) · [ORDER BY](order-by.md) · [UPDATE](update.md) · [DELETE](delete.md) · [MERGE](merge.md)
