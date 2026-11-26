# WITH common_table_expression (Transact-SQL)

Names a temporary result set, a common table expression (CTE), that the statement after it can read. A CTE may
refer to itself: a recursive CTE.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
WITH expression_name [ ( column_name [ ,...n ] ) ]
AS
( CTE_query_definition )
[ ,...n ]
{ SELECT ... | INSERT ... | UPDATE ... | DELETE ... | MERGE ... }
[ OPTION ( MAXRECURSION number ) ]
```

## Arguments

*expression_name*
: The CTE's name. The statement after the `WITH`, and the CTEs after this one, can read it as a table.

*column_name*
: Names for the CTE's columns, as many as its query has. Without them the columns take the query's names.

*CTE_query_definition*
: A `SELECT`. In a recursive CTE it is an anchor query, `UNION ALL`, and a recursive query that reads the CTE.

`MAXRECURSION` *number*
: How many times the recursive part may run, from 0 to 32767; 0 is no limit. The default is 100.

## Remarks

- A CTE lasts for one statement.
- A recursive CTE runs the anchor once, then the recursive part on the rows the last step made, until a step makes
  no rows. Past the `MAXRECURSION` limit the statement fails with error 530.
- `MAXRECURSION` above 32767 is error 310; given twice it is 1042.
- In a batch, the statement before `WITH` should end with a semicolon, as SQL Server wants.

## Differences from SQL Server

- A CTE cannot be the target of `UPDATE` or `DELETE` (error 208, "Invalid object name"); SQL Server changes the
  table under it. Name the table and read the CTE in the `WHERE` clause (example E).
- A recursive CTE's rows are made before the query reads them, with one exception: a `TOP` query without `ORDER BY`,
  grouping or `DISTINCT` that reads the CTE as its first table stops an endless recursion when it has its rows, also
  with a `WHERE`, a join, a left join or a derived table that filters them (example C). `MAXRECURSION` then counts the
  levels the rows `TOP` needs take: error 530 when they are further than the limit. This holds only for a chain (one
  row a round); a tree recursion (more than one row a round), a join where lexdb's planner reads the other table
  first (`FROM t JOIN n`), a subquery in the `WHERE` or the select list, and a `WHERE` that calls `NEWID` or `RAND`
  run the recursion to `MAXRECURSION` (error 530) or, with `MAXRECURSION 0` and no end, to error 50000 when the
  statement holds more than `max_statement_mem` of rows.
- `WITH RECURSIVE` (PostgreSQL's form) is taken; SQL Server refuses it.
- Data-modifying CTEs (`WITH d AS (DELETE FROM t OUTPUT DELETED.* WHERE ...) SELECT * FROM d`, and `INSERT`, `UPDATE`,
  or `MERGE` with `OUTPUT`) are supported as a LexDB extension, running against the pre-statement snapshot and passing
  `OUTPUT` rows to later CTEs and the main statement. `OUTPUT ... INTO` is not allowed inside a CTE.
- `WITH XMLNAMESPACES` is not supported.

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30) NOT NULL, boss_id int, salary decimal(10,2));
INSERT dbo.emp VALUES (1, N'Ann', NULL, 9000), (2, N'Bob', 1, 6000), (3, N'Cid', 1, 6500), (4, N'Dee', 2, 4000), (5, N'Eve', 4, 3000);
-->

The examples use one table:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30) NOT NULL, boss_id int, salary decimal(10,2));
INSERT dbo.emp VALUES (1, N'Ann', NULL, 9000), (2, N'Bob', 1, 6000), (3, N'Cid', 1, 6500), (4, N'Dee', 2, 4000),
  (5, N'Eve', 4, 3000);
```

### A. Two CTEs, one with column names

<!-- example: tsql -->
```sql
WITH paid AS (SELECT * FROM dbo.emp WHERE salary >= 6000),
     boss (boss_id, boss_name) AS (SELECT id, name FROM dbo.emp)
SELECT p.name, b.boss_name
FROM paid AS p LEFT JOIN boss AS b ON b.boss_id = p.boss_id
ORDER BY p.id;
```

```text
name boss_name
---- ---------
Ann  NULL
Bob  Ann
Cid  Ann

(3 rows affected)
```

### B. A recursive CTE: everyone under Bob

<!-- example: tsql -->
```sql
WITH chain AS (
    SELECT id, name, 0 AS depth FROM dbo.emp WHERE name = N'Bob'
    UNION ALL
    SELECT e.id, e.name, c.depth + 1 FROM dbo.emp AS e JOIN chain AS c ON e.boss_id = c.id
)
SELECT name, depth FROM chain ORDER BY depth;
```

```text
name depth
---- -----
Bob  0
Dee  1
Eve  2

(3 rows affected)
```

### C. MAXRECURSION

The default limit of 100 stops the first query. `TOP` stops an endless recursion (`MAXRECURSION 0`) when it has its
rows, with a `WHERE` on them; if the rows it needs are further than `MAXRECURSION`, the error is 530.

<!-- example: tsql -->
```sql
WITH n AS (SELECT 1 AS i UNION ALL SELECT i + 1 FROM n WHERE i < 200)
SELECT MAX(i) AS top_i FROM n;
GO
WITH n AS (SELECT 1 AS i UNION ALL SELECT i + 1 FROM n WHERE i < 200)
SELECT MAX(i) AS top_i FROM n
OPTION (MAXRECURSION 300);
GO
WITH n AS (SELECT 1 AS i UNION ALL SELECT i + 1 FROM n)
SELECT TOP (3) i FROM n WHERE i % 7 = 0 OPTION (MAXRECURSION 0);
GO
WITH n AS (SELECT 1 AS i UNION ALL SELECT i + 1 FROM n)
SELECT TOP (3) i FROM n WHERE i % 700 = 0 OPTION (MAXRECURSION 500);
```

```text
Msg 530, Level 16, State 1, Line 1
An error occurred during the current command (Done status 0). The statement terminated. The maximum recursion 100 has been exhausted before statement completion.
top_i
-----
200

(1 row affected)

i
--
7
14
21

(3 rows affected)

Msg 530, Level 16, State 1, Line 1
An error occurred during the current command (Done status 0). The statement terminated. The maximum recursion 500 has been exhausted before statement completion.
```

### D. A CTE in INSERT and MERGE

<!-- example: tsql -->
```sql
CREATE TABLE dbo.top_paid (id int PRIMARY KEY, name nvarchar(30));
WITH t AS (SELECT TOP (2) id, name FROM dbo.emp ORDER BY salary DESC)
INSERT INTO dbo.top_paid (id, name) SELECT id, name FROM t;
WITH s AS (SELECT id, name FROM dbo.emp WHERE id <= 3)
MERGE dbo.top_paid AS t USING s ON t.id = s.id
WHEN NOT MATCHED THEN INSERT (id, name) VALUES (s.id, s.name);
SELECT * FROM dbo.top_paid ORDER BY id;
```

```text
(2 rows affected)

(1 row affected)

id name
-- ----
1  Ann
2  Bob
3  Cid

(3 rows affected)
```

### E. A CTE in UPDATE

<!-- example: tsql -->
```sql
WITH low AS (SELECT id FROM dbo.emp WHERE salary < 5000)
UPDATE dbo.emp SET salary = salary + 100 WHERE id IN (SELECT id FROM low);
SELECT name, salary FROM dbo.emp WHERE salary < 5000 ORDER BY id;
```

```text
(2 rows affected)

name salary
---- -------
Dee  4100.00
Eve  3100.00

(2 rows affected)
```

### F. Errors

<!-- example: tsql -->
```sql
WITH low AS (SELECT * FROM dbo.emp WHERE salary < 5000)
UPDATE low SET salary = salary + 100;
GO
WITH n AS (SELECT 1 AS i UNION ALL SELECT i + 1 FROM n WHERE i < 10)
SELECT i FROM n OPTION (MAXRECURSION 40000);
GO
```

```text
Msg 208, Level 16, State 1, Line 1
Invalid object name 'low'.
Msg 310, Level 16, State 1, Line 2
The value 40000 specified for the MAXRECURSION option exceeds the allowed maximum of 32767.
```

## See also

[SELECT](select.md) · [INSERT](insert.md) · [UPDATE](update.md) · [DELETE](delete.md) · [MERGE](merge.md)
