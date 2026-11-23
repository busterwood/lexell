# DROP INDEX (Transact-SQL)

Removes an index.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
DROP INDEX [ IF EXISTS ] [ schema_name. ] index_name
[ ; ]
```

## Arguments

`IF EXISTS`
: An index that does not exist is no error.

*index_name*
: The index to drop, by its name alone or with its schema (`dbo.ix_emp_name`). lexdb's index names are unique in
  a schema, so the table need not be named.

## Remarks

- An index that backs a `PRIMARY KEY` or `UNIQUE` constraint is dropped with the constraint: `ALTER TABLE ... DROP
  CONSTRAINT`.
- `DROP INDEX` is transactional.

## Differences from SQL Server

- **`DROP INDEX index_name ON table_name`, SQL Server's usual form, is error 156** ("Incorrect syntax near the
  keyword 'on'"). Name the index alone. The old form `DROP INDEX table_name.index_name` gives error 50000 ("index
  "emp.ix_emp_name" does not exist").
- One index per statement: a list is error 102.
- The form above is PostgreSQL's. An index that does not exist is error 50000 with lexdb's text (SQL Server: 3701).

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

### B. Errors

<!-- example: tsql -->
```sql
DROP INDEX ix_nothere;
GO
CREATE INDEX ix_emp_name ON dbo.emp (name);
GO
DROP INDEX ix_emp_name ON dbo.emp;
GO
DROP INDEX dbo.emp.ix_emp_name;
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
index "ix_nothere" does not exist
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'on'.
Msg 50000, Level 16, State 1, Line 1
index "emp.ix_emp_name" does not exist
```

## See also

[CREATE INDEX](create-index.md) · [ALTER TABLE](alter-table.md)
