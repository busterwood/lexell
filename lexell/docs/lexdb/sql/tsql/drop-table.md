# DROP TABLE (Transact-SQL)

Removes one or more tables, with their rows, indexes and constraints.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP TABLE [ IF EXISTS ] { database_name.schema_name.table_name | schema_name.table_name | table_name | #table_name }
    [ ,...n ]
[ ; ]
```

## Arguments

`IF EXISTS`
: A table that does not exist is no error.

*table_name*
: The table to drop, or a temporary table of the session.

## Remarks

- A table that a foreign key of another table refers to cannot be dropped. Drop the foreign key, or the referring
  table first; in one `DROP TABLE` list, put the referring table first.
- `DROP TABLE` is transactional: inside a transaction, `ROLLBACK` brings the table back.
- A temporary table is dropped by itself when its session ends.

## Differences from SQL Server

- **A table that a view reads is dropped, as in SQL Server**, unless the view is `WITH SCHEMABINDING` (error 3729,
  naming the table without its schema; SQL Server: `dbo.emp`). The view, and a view over it, fail with error 208 when
  read (the text names the table without its schema), and read again as soon as a table of that name is made (example
  E). `DROP VIEW` of a view another view reads is still refused (error 50000; SQL Server allows it).
- A table that a foreign key refers to gives error 50000 with lexdb's text (SQL Server: 3726).

## Examples

### A. Drop a table

<!-- example: tsql -->
```sql
CREATE TABLE dbo.scratch (id int);
DROP TABLE dbo.scratch;
SELECT COUNT(*) AS left_over FROM sys.tables WHERE name = 'scratch';
```

```text
left_over
---------
0

(1 row affected)
```

### B. IF EXISTS, and several tables

<!-- example: tsql -->
```sql
CREATE TABLE dbo.a (id int);
CREATE TABLE dbo.b (id int);
DROP TABLE IF EXISTS dbo.a, dbo.b, dbo.nothere;
DROP TABLE IF EXISTS dbo.nothere;
SELECT COUNT(*) AS left_over FROM sys.tables WHERE name IN ('a', 'b');
```

```text
left_over
---------
0

(1 row affected)
```

### C. A table with a foreign key to it

<!-- example: tsql -->
```sql
CREATE TABLE dbo.parent (id int PRIMARY KEY);
CREATE TABLE dbo.child (id int, parent_id int REFERENCES dbo.parent (id));
DROP TABLE dbo.parent;
DROP TABLE dbo.child, dbo.parent;
SELECT COUNT(*) AS left_over FROM sys.tables WHERE name IN ('parent', 'child');
```

```text
Msg 50000, Level 16, State 1, Line 3
cannot drop table parent because other objects depend on it (with CASCADE the foreign keys on it are dropped)
left_over
---------
0

(1 row affected)
```

### D. Inside a transaction

<!-- example: tsql -->
```sql
CREATE TABLE dbo.keep (id int);
INSERT dbo.keep VALUES (1), (2);
BEGIN TRANSACTION;
DROP TABLE dbo.keep;
ROLLBACK;
SELECT COUNT(*) AS rows_back FROM dbo.keep;
```

```text
(2 rows affected)

rows_back
---------
2

(1 row affected)
```

### E. A table under a view

A view over a dropped table is not dropped with it. Reading it is error 208 until a table of that name is made again.
A schema-bound view stops the drop.

<!-- example: tsql -->
```sql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(20));
INSERT dbo.dept VALUES (1, N'sales');
GO
CREATE VIEW dbo.v_dept AS SELECT name FROM dbo.dept;
GO
CREATE VIEW dbo.v_dept_up AS SELECT UPPER(name) AS name FROM dbo.v_dept;
GO
DROP TABLE dbo.dept;
GO
SELECT * FROM dbo.v_dept_up;
GO
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(20));
INSERT dbo.dept VALUES (2, N'ops');
GO
SELECT * FROM dbo.v_dept_up;
GO
CREATE VIEW dbo.v_dept_bound WITH SCHEMABINDING AS SELECT id FROM dbo.dept;
GO
DROP TABLE dbo.dept;
GO
```

```text
(1 row affected)

Msg 208, Level 16, State 1, Line 1
Invalid object name 'dept'.
(1 row affected)

name
----
OPS

(1 row affected)

Msg 3729, Level 16, State 1, Line 1
Cannot DROP TABLE 'dept' because it is being referenced by object 'v_dept_bound'.
```

### F. Errors

<!-- example: tsql -->
```sql
DROP TABLE dbo.nothere;
```

```text
Msg 3701, Level 11, State 1, Line 1
Cannot drop the table 'nothere', because it does not exist or you do not have permission.
```

## See also

[CREATE TABLE](create-table.md) · [ALTER TABLE](alter-table.md) · [TRUNCATE TABLE](truncate-table.md) ·
[DROP VIEW](drop-view.md)
