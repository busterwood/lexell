# Set operators - UNION, EXCEPT and INTERSECT (Transact-SQL)

Combine the results of two or more queries into one result.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
{ query_specification | ( query_expression ) }
{ UNION [ ALL ] | EXCEPT | INTERSECT }
{ query_specification | ( query_expression ) }
[ ...n ]
[ ORDER BY ... ]
```

## Arguments

`UNION`
: The rows of either query, without duplicates.

`UNION ALL`
: The rows of both queries, duplicates kept.

`EXCEPT`
: The distinct rows of the left query that the right query does not return.

`INTERSECT`
: The distinct rows that both queries return.

## Remarks

- The queries must have the same number of columns. The result's column names are the first query's.
- NULLs are equal here: two rows that are both NULL in a column match.
- `INTERSECT` binds tighter than `UNION` and `EXCEPT`; otherwise the operators go from left to right. Parentheses
  change that.
- `ORDER BY` comes once, after the last query, and sorts the whole result. A query in parentheses may have its own
  `TOP ... ORDER BY`.

## Differences from SQL Server

- An `int` column and an `nvarchar` column are combined as text (example F), where SQL Server converts the strings
  to `int` by type precedence and fails on the first that is not a number (error 245). Constants are converted as
  SQL Server converts them: `SELECT 1 UNION SELECT N'a'` is error 245.
- Queries with different numbers of columns give error 102; SQL Server gives 205.
- PostgreSQL's `EXCEPT ALL` and `INTERSECT ALL` are taken; SQL Server refuses them.

## Examples

<!--setup: tsql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30));
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept_id int);
INSERT dbo.dept VALUES (1, N'Sales'), (2, N'Research'), (3, N'Legal');
INSERT dbo.emp VALUES (1, N'Ann', 1), (2, N'Bob', 1), (3, N'Cid', 2), (4, N'Eve', NULL);
-->

The examples use two tables:

```sql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30));
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept_id int);
INSERT dbo.dept VALUES (1, N'Sales'), (2, N'Research'), (3, N'Legal');
INSERT dbo.emp VALUES (1, N'Ann', 1), (2, N'Bob', 1), (3, N'Cid', 2), (4, N'Eve', NULL);
```

### A. UNION and UNION ALL

<!-- example: tsql -->
```sql
SELECT id FROM dbo.dept UNION SELECT dept_id FROM dbo.emp ORDER BY id;
SELECT id FROM dbo.dept UNION ALL SELECT dept_id FROM dbo.emp ORDER BY id;
```

```text
id
----
NULL
1
2
3

(4 rows affected)

id
----
NULL
1
1
1
2
2
3

(7 rows affected)
```

### B. EXCEPT and INTERSECT

<!-- example: tsql -->
```sql
SELECT id FROM dbo.dept EXCEPT SELECT dept_id FROM dbo.emp;
SELECT id FROM dbo.dept INTERSECT SELECT dept_id FROM dbo.emp ORDER BY id;
```

```text
id
--
3

(1 row affected)

id
--
1
2

(2 rows affected)
```

### C. Names from the first query, and one ORDER BY

<!-- example: tsql -->
```sql
SELECT name AS label, 'dept' AS kind FROM dbo.dept
UNION ALL
SELECT name, 'emp' FROM dbo.emp
ORDER BY kind, label;
```

```text
label    kind
-------- ----
Legal    dept
Research dept
Sales    dept
Ann      emp
Bob      emp
Cid      emp
Eve      emp

(7 rows affected)
```

### D. Queries in parentheses with their own TOP

<!-- example: tsql -->
```sql
(SELECT TOP (1) name FROM dbo.emp ORDER BY id)
UNION ALL
(SELECT TOP (1) name FROM dbo.emp ORDER BY id DESC);
```

```text
name
----
Ann
Eve

(2 rows affected)
```

### E. INTERSECT first

<!-- example: tsql -->
```sql
SELECT id FROM dbo.dept EXCEPT SELECT 1 INTERSECT SELECT 1;
```

```text
id
--
2
3

(2 rows affected)
```

### F. Columns of different types

<!-- example: tsql -->
```sql
SELECT id FROM dbo.dept UNION ALL SELECT name FROM dbo.emp;
```

```text
id
---
1
2
3
Ann
Bob
Cid
Eve

(7 rows affected)
```

### G. Errors

<!-- example: tsql -->
```sql
SELECT id, name FROM dbo.dept UNION SELECT id FROM dbo.emp;
GO
SELECT 1 UNION SELECT N'a';
GO
```

```text
Msg 102, Level 15, State 1, Line 1
each UNION query must have the same number of columns
Msg 245, Level 16, State 1, Line 1
invalid input syntax for type integer: "a"
```

## See also

[SELECT](select.md) · [ORDER BY](order-by.md)
