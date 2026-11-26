# DROP INDEX (Transact-SQL)

Removes an index.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP [ SKIPPING ] INDEX [ IF EXISTS ] index_name [ ON { schema_name.table_name | table_name } ]
DROP INDEX [ IF EXISTS ] [ schema_name. ] table_name.index_name
[ ; ]
```

## Arguments

`IF EXISTS`
: An index that does not exist is no error.

*index_name*
: The index to drop. A bare name is error 159 (SQL Server's text, "Must specify the table name and index name"): name
  the table with `ON`, or in the older form `table_name.index_name`.

`ON` *table_name*
: The index's table, as SQL Server's usual form names it. Index names are per table, as in SQL Server: two tables may
  each have an `ix_name`.

## Remarks

- An index that backs a `PRIMARY KEY` or `UNIQUE` constraint is dropped with the constraint: `ALTER TABLE ... DROP
  CONSTRAINT`.
- `DROP INDEX` is transactional.
- The older forms `DROP INDEX table_name.index_name` and `DROP INDEX schema_name.table_name.index_name` work (example B),
  and name the table whose index is dropped.
- **Errors,** as in SQL Server: a bare name is 159 (severity 15). `table.index`, `schema.table.index` and `index ON table` give 3701
  (`Cannot drop the index 'dbo.emp.ix_nothere', because it does not exist or you do not have permission.`, state 6 when
  the table is not there and 7 when the index is not) and 3723 (an index that backs a constraint: `An explicit DROP
  INDEX is not allowed on index 'dbo.part.uq_part_code'. It is being used for UNIQUE KEY constraint enforcement.`,
  state 5 for a `UNIQUE` constraint's index and 4 for a `PRIMARY KEY`'s), with the index named as the statement wrote
  it. `DROP INDEX dbo.ix` is 3701, as in SQL Server: `dbo` is read as the table (example D).

## Differences from SQL Server

- **One index per statement:** a list (`DROP INDEX ix1 ON t1, ix2 ON t2`, `DROP INDEX a.x, b.y`) is error 102 (SQL
  Server takes it).
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

A bare index name is 159. A table or index that is not there is 3701, and the index of a constraint 3723.

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
DROP INDEX ix_emp_name;
GO
DROP INDEX dbo.ix_emp_name;
GO
DROP INDEX IF EXISTS ix_emp_name;
GO
```

```text
Msg 3701, Level 11, State 7, Line 1
Cannot drop the index 'dbo.emp.ix_nothere', because it does not exist or you do not have permission.
Msg 3701, Level 11, State 7, Line 1
Cannot drop the index 'dbo.emp.ix_nothere', because it does not exist or you do not have permission.
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near ','.
Msg 3723, Level 16, State 5, Line 1
An explicit DROP INDEX is not allowed on index 'dbo.part.uq_part_code'. It is being used for UNIQUE KEY constraint enforcement.
Msg 3723, Level 16, State 4, Line 1
An explicit DROP INDEX is not allowed on index 'dbo.emp.emp_pkey'. It is being used for PRIMARY KEY constraint enforcement.
Msg 159, Level 15, State 1, Line 1
Must specify the table name and index name for the DROP INDEX statement.
Msg 3701, Level 11, State 6, Line 1
Cannot drop the index 'dbo.ix_emp_name', because it does not exist or you do not have permission.
Msg 159, Level 15, State 1, Line 1
Must specify the table name and index name for the DROP INDEX statement.
```

## See also

[CREATE INDEX](create-index.md) · [ALTER TABLE](alter-table.md)
