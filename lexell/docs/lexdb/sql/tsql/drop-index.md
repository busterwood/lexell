# DROP INDEX (Transact-SQL)

Removes an index.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP INDEX [ IF EXISTS ] index_name ON { schema_name.table_name | table_name }
DROP INDEX [ IF EXISTS ] [ schema_name. ] index_name
[ ; ]
```

## Arguments

`IF EXISTS`
: An index that does not exist is no error.

*index_name*
: The index to drop, by its name alone or with its schema (`dbo.ix_emp_name`).

`ON` *table_name*
: The index's table, as SQL Server's usual form names it. Index names are per table, as in SQL Server: two tables may
  each have an `ix_name`.

## Remarks

- An index that backs a `PRIMARY KEY` or `UNIQUE` constraint is dropped with the constraint: `ALTER TABLE ... DROP
  CONSTRAINT`.
- `DROP INDEX` is transactional.
- The older forms `DROP INDEX table_name.index_name` and `DROP INDEX schema_name.table_name.index_name` work (example B),
  and name the table whose index is dropped.

## Differences from SQL Server

- **One index per statement:** a list (`DROP INDEX ix1 ON t1, ix2 ON t2`) is error 102.
- `DROP INDEX ix` without a table is taken (SQL Server: 159, "Must specify the table name and index name"); when
  several tables have an `ix`, use `ON` or the older form to say which. `DROP INDEX schema_name.ix` is read as a table
  and an index (error 208, `Invalid object name 'dbo'`; SQL Server: 159).
- An index that does not exist is error 50000 with lexdb's text (SQL Server: 3701).
- An index that backs a unique constraint is refused with error 50000 (`cannot drop index ... because constraint ...
  requires it`; SQL Server: 3723, "An explicit DROP INDEX is not allowed on index ..."), and the index of a primary key
  is not found (error 50000; SQL Server: 3723); drop the constraint.
- Dropping the clustered index leaves a heap: see [CREATE INDEX](create-index.md).

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept_id int);
CREATE INDEX ix_emp_name ON dbo.emp (name);
CREATE INDEX ix_emp_dept ON dbo.emp (dept_id);
-->

The examples use a table with two indexes:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept_id int);
CREATE INDEX ix_emp_name ON dbo.emp (name);
CREATE INDEX ix_emp_dept ON dbo.emp (dept_id);
```

### A. Drop indexes

<!-- example: tsql -->
```sql
DROP INDEX ix_emp_name ON dbo.emp;
DROP INDEX IF EXISTS ix_nothere ON dbo.emp;
SELECT name FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.emp') ORDER BY index_id;
```

```text
name
-----------
emp_pkey
ix_emp_dept

(2 rows affected)
```

### B. SQL Server's older forms

<!-- example: tsql -->
```sql
CREATE INDEX ix_emp_name ON dbo.emp (name);
GO
DROP INDEX emp.ix_emp_name;
GO
DROP INDEX IF EXISTS dbo.emp.ix_emp_dept;
GO
DROP INDEX IF EXISTS dbo.emp.ix_emp_dept;
GO
SELECT index_id, name, type_desc FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.emp') ORDER BY index_id;
GO
```

```text
index_id name     type_desc
-------- -------- ---------
1        emp_pkey CLUSTERED

(1 row affected)
```

### C. The same name on two tables

<!-- example: tsql -->
```sql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30));
CREATE INDEX ix_name ON dbo.emp (name);
CREATE INDEX ix_name ON dbo.dept (name);
GO
SELECT OBJECT_NAME(object_id) AS tbl, name FROM sys.indexes WHERE name = 'ix_name' ORDER BY 1;
GO
DROP INDEX ix_name ON dbo.dept;
GO
SELECT OBJECT_NAME(object_id) AS tbl, name FROM sys.indexes WHERE name = 'ix_name' ORDER BY 1;
GO
DROP INDEX dbo.emp.ix_name;
GO
SELECT OBJECT_NAME(object_id) AS tbl, name FROM sys.indexes WHERE name = 'ix_name' ORDER BY 1;
GO
```

```text
tbl  name
---- -------
dept ix_name
emp  ix_name

(2 rows affected)

tbl name
--- -------
emp ix_name

(1 row affected)

tbl name
--- ----

(0 rows affected)
```

### D. Errors

<!-- example: tsql -->
```sql
CREATE TABLE dbo.part (id int PRIMARY KEY, code nvarchar(10), CONSTRAINT uq_part_code UNIQUE (code));
GO
DROP INDEX ix_nothere ON dbo.emp;
GO
DROP INDEX dbo.emp.ix_nothere;
GO
DROP INDEX ix_emp_name ON dbo.emp, ix_emp_dept ON dbo.emp;
GO
DROP INDEX uq_part_code ON dbo.part;
GO
DROP INDEX emp_pkey ON dbo.emp;
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
index "ix_nothere" does not exist
Msg 50000, Level 16, State 1, Line 1
index "ix_nothere" does not exist
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near ','.
Msg 50000, Level 16, State 1, Line 1
cannot drop index uq_part_code because constraint uq_part_code on table part requires it (drop the constraint instead)
Msg 50000, Level 16, State 1, Line 1
index "emp_pkey" does not exist
```

## See also

[CREATE INDEX](create-index.md) · [ALTER TABLE](alter-table.md)
