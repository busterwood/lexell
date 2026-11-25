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

- **A table that a view reads cannot be dropped** (error 50000, "cannot drop table emp because other objects depend
  on it"), schema-bound or not. SQL Server drops it, and the view fails when it is next used, unless the view is
  `WITH SCHEMABINDING` (error 3729). Drop the view first.
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

### E. Errors

<!-- example: tsql -->
```sql
CREATE VIEW dbo.v_keep AS SELECT id FROM dbo.keep;
GO
DROP TABLE dbo.keep;
DROP TABLE dbo.nothere;
```

```text
Msg 50000, Level 16, State 1, Line 1
cannot drop table keep because other objects depend on it
Msg 3701, Level 11, State 1, Line 2
Cannot drop the table 'nothere', because it does not exist or you do not have permission.
```

## See also

[CREATE TABLE](create-table.md) · [ALTER TABLE](alter-table.md) · [TRUNCATE TABLE](truncate-table.md) ·
[DROP VIEW](drop-view.md)
