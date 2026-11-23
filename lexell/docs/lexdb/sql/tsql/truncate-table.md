# TRUNCATE TABLE (Transact-SQL)

Removes every row of a table, faster than `DELETE` without `WHERE`.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
TRUNCATE TABLE { database_name.schema_name.table_name | schema_name.table_name | table_name | #temp_table }
[ ; ]
```

## Arguments

*table_name*
: The table to empty, with its schema and database if wanted, or a `#temp` table of the session.

## Remarks

- `TRUNCATE TABLE` gives no `(n rows affected)` message, and checks no row.
- It is transactional: inside a transaction, `ROLLBACK` brings the rows back.
- A table that a foreign key of another table refers to cannot be truncated, even when no row refers to it. Use
  `DELETE`.

## Differences from SQL Server

- **The `IDENTITY` column is not reset to its seed.** The next row gets the next value after the last one made
  before the truncation (example B); SQL Server starts again at the seed.
- A table a foreign key refers to gives error 50000 with lexdb's text; SQL Server gives 4712.
- `WITH (PARTITIONS (...))` is error 102: lexdb has no partitions.
- Several tables separated by commas are taken (PostgreSQL's form); SQL Server takes one.

## Examples

<!--setup: tsql
CREATE TABLE dbo.log (id int IDENTITY PRIMARY KEY, msg nvarchar(40));
INSERT dbo.log (msg) VALUES (N'one'), (N'two'), (N'three');
-->

The examples use one table:

```sql
CREATE TABLE dbo.log (id int IDENTITY PRIMARY KEY, msg nvarchar(40));
INSERT dbo.log (msg) VALUES (N'one'), (N'two'), (N'three');
```

### A. Empty a table, and roll it back

<!-- example: tsql -->
```sql
BEGIN TRANSACTION;
TRUNCATE TABLE dbo.log;
SELECT COUNT(*) AS inside FROM dbo.log;
ROLLBACK;
SELECT COUNT(*) AS after_rollback FROM dbo.log;
```

```text
inside
------
0

(1 row affected)

after_rollback
--------------
3

(1 row affected)
```

### B. Empty a table: the identity goes on

<!-- example: tsql -->
```sql
TRUNCATE TABLE dbo.log;
INSERT dbo.log (msg) VALUES (N'four');
SELECT * FROM dbo.log;
```

```text
(1 row affected)

id msg
-- ----
4  four

(1 row affected)
```

### C. A temporary table

<!-- example: tsql -->
```sql
CREATE TABLE #work (n int);
INSERT #work VALUES (1), (2);
TRUNCATE TABLE #work;
SELECT COUNT(*) AS n FROM #work;
```

```text
(2 rows affected)

n
-
0

(1 row affected)
```

### D. Errors

<!-- example: tsql -->
```sql
CREATE TABLE dbo.parent (id int PRIMARY KEY);
CREATE TABLE dbo.child (parent_id int REFERENCES dbo.parent (id));
TRUNCATE TABLE dbo.parent;
GO
TRUNCATE TABLE dbo.log WITH (PARTITIONS (1));
GO
```

```text
Msg 50000, Level 16, State 1, Line 3
cannot truncate a table referenced in a foreign key constraint: Table "child" references "parent". Truncate table "child" at the same time, or use TRUNCATE ... CASCADE.
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near '('.
```

## See also

[DELETE](delete.md) · DROP TABLE · BEGIN TRANSACTION
