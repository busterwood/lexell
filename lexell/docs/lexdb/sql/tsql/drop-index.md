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
: The index's table, as SQL Server's usual form names it. lexdb's index names are unique in a schema, so the name
  alone finds the index.

## Remarks

- An index that backs a `PRIMARY KEY` or `UNIQUE` constraint is dropped with the constraint: `ALTER TABLE ... DROP
  CONSTRAINT`.
- `DROP INDEX` is transactional.

## Differences from SQL Server

- **One index per statement:** a list (`DROP INDEX ix1 ON t1, ix2 ON t2`) is error 102.
- The old form `DROP INDEX table_name.index_name` is error 50000 (`index "emp.ix_emp_name" does not exist`).
- An index that does not exist is error 50000 with lexdb's text (SQL Server: 3701). An index that backs a primary key
  or a unique constraint is not found either (SQL Server: 3723, "An explicit DROP INDEX is not allowed on index ...");
  drop the constraint.
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
DROP INDEX ix_emp_name;
DROP INDEX IF EXISTS dbo.ix_emp_dept;
DROP INDEX IF EXISTS ix_nothere;
SELECT name FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.emp');
```

```text
name
--------
emp_pkey

(1 row affected)
```

### B. SQL Server's usual form

<!-- example: tsql -->
```sql
CREATE INDEX ix_emp_name ON dbo.emp (name);
GO
DROP INDEX ix_emp_name ON dbo.emp;
GO
DROP INDEX IF EXISTS ix_emp_name ON dbo.emp;
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

### C. Errors

<!-- example: tsql -->
```sql
DROP INDEX ix_nothere;
GO
DROP INDEX ix_nothere ON dbo.emp;
GO
CREATE INDEX ix_emp_name ON dbo.emp (name);
GO
DROP INDEX dbo.emp.ix_emp_name;
GO
DROP INDEX ix_emp_name ON dbo.emp, ix_emp_dept ON dbo.emp;
GO
DROP INDEX emp_pkey ON dbo.emp;
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
index "ix_nothere" does not exist
Msg 50000, Level 16, State 1, Line 1
index "ix_nothere" does not exist
Msg 50000, Level 16, State 1, Line 1
index "emp.ix_emp_name" does not exist
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near ','.
Msg 50000, Level 16, State 1, Line 1
index "emp_pkey" does not exist
```

## See also

[CREATE INDEX](create-index.md) · [ALTER TABLE](alter-table.md)
