# sp_rename (Transact-SQL)

Renames a table, a view, a column or an index.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
EXEC sp_rename
    [ @objname = ] 'object_name' ,
    [ @newname = ] 'new_name'
    [ , [ @objtype = ] { 'OBJECT' | 'COLUMN' | 'INDEX' } ]
[ ; ]
```

## Arguments

`@objname`
: What to rename: `'schema.table'` for a table or view, `'schema.table.column'` for a column, `'schema.table.index'`
  for an index. The schema may be left out.

`@newname`
: The new name, alone (no schema or table part).

`@objtype`
: `'COLUMN'` for a column, `'INDEX'` for an index; `'OBJECT'` or nothing for a table or view. `'DATABASE'`,
  `'STATISTICS'` and `'USERDATATYPE'` are also taken as words; any other is error 15249.

## Remarks

- On success, `sp_rename` prints SQL Server's caution: "Caution: Changing any part of an object name could break
  scripts and stored procedures."
- Indexes, constraints and foreign keys follow a renamed table or column. A view's text keeps the old name, so a
  view that reads a renamed column fails when read (207), as in SQL Server.
- Errors: no such object is 15225, a wrong `@objtype` for the name is 15248, a missing argument 201, a NULL name
  15223, an empty new name 15004.
- `ALTER TABLE ... RENAME` is error 102 in this door: `sp_rename` is the way to rename.

## Differences from SQL Server

- None known for tables, columns and indexes.

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept int);
INSERT dbo.emp VALUES (1, N'Ann', 1);
CREATE INDEX ix_emp_dept ON dbo.emp (dept);
-->

The examples use one table:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30), dept int);
INSERT dbo.emp VALUES (1, N'Ann', 1);
CREATE INDEX ix_emp_dept ON dbo.emp (dept);
```

### A. Rename a column, an index and a table

<!-- example: tsql -->
```sql
EXEC sp_rename 'dbo.emp.dept', 'dept_id', 'COLUMN';
EXEC sp_rename 'dbo.emp.ix_emp_dept', 'ix_staff_dept', 'INDEX';
EXEC sp_rename 'dbo.emp', 'staff';
SELECT * FROM dbo.staff;
SELECT name FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.staff') ORDER BY name;
```

```text
Caution: Changing any part of an object name could break scripts and stored procedures.
Caution: Changing any part of an object name could break scripts and stored procedures.
Caution: Changing any part of an object name could break scripts and stored procedures.
id name dept_id
-- ---- -------
1  Ann  1

(1 row affected)

name
-------------
emp_pkey
ix_staff_dept

(2 rows affected)
```

### B. Named arguments

<!-- example: tsql -->
```sql
EXEC sp_rename @objname = N'dbo.staff.name', @newname = N'full_name', @objtype = N'COLUMN';
SELECT id, full_name FROM dbo.staff;
```

```text
Caution: Changing any part of an object name could break scripts and stored procedures.
id full_name
-- ---------
1  Ann

(1 row affected)
```

### C. Errors

<!-- example: tsql -->
```sql
EXEC sp_rename 'dbo.nothere', 'x';
EXEC sp_rename 'dbo.staff.id', 'x', 'INDEX';
EXEC sp_rename 'dbo.staff', 'x', 'TABLE';
EXEC sp_rename 'dbo.staff';
```

```text
Msg 15225, Level 16, State 1, Line 1
No item by the name 'dbo.nothere' could be found in the current database 'lexdb', given that @itemtype was input as '(null)'.
Msg 15248, Level 16, State 1, Line 2
Either the parameter @objname is ambiguous or the claimed @objtype (INDEX) is wrong.
Msg 15249, Level 16, State 1, Line 3
Error: The type of the object 'TABLE' is not valid. It must be COLUMN, DATABASE, INDEX, OBJECT, STATISTICS or USERDATATYPE.
Msg 201, Level 16, State 4, Line 4
Procedure or function 'sp_rename' expects parameter '@newname', which was not supplied.
```

## See also

[ALTER TABLE](alter-table.md) · [CREATE INDEX](create-index.md) · [CREATE VIEW](create-view.md)
