# ALTER TABLE (Transact-SQL)

Changes a table's definition: adds, changes and drops columns and constraints.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
ALTER TABLE { database_name.schema_name.table_name | schema_name.table_name | table_name }
{
    ADD column_definition
  | ADD computed_column_definition
  | ADD [ CONSTRAINT constraint_name ] table_constraint
  | ALTER COLUMN column_name new_data_type [ COLLATE collation_name ] [ NULL | NOT NULL ]
  | DROP COLUMN [ IF EXISTS ] column_name
  | DROP CONSTRAINT [ IF EXISTS ] constraint_name
}
[ ; ]
```

*column_definition*, *computed_column_definition* and *table_constraint* are as in
[CREATE TABLE](create-table.md).

## Arguments

`ADD` *column_definition*
: Adds a column at the end. Existing rows get its default, or NULL. A `NOT NULL` column without a default cannot be
  added to a table that has rows. An `IDENTITY` column numbers the existing rows.

`ADD` *computed_column_definition*
: Adds a computed column, `PERSISTED` or not.

`ADD CONSTRAINT` *table_constraint*
: Adds a `PRIMARY KEY`, `UNIQUE`, `FOREIGN KEY` or `CHECK` constraint. The existing rows are checked first. A
  `PRIMARY KEY` or `UNIQUE` may be `CLUSTERED` or `NONCLUSTERED` (labels: see [CREATE INDEX](create-index.md)); a
  table that has a primary key refuses a second one.

`ALTER COLUMN` *column_name* *new_data_type*
: Changes the column's type, and with `NULL` or `NOT NULL` whether it may hold NULL. The rows are converted; a value
  that does not convert is an error and nothing changes. A column that a foreign key, index or constraint depends
  on cannot change its type (error 5074).

`DROP COLUMN`
: Removes a column. `IF EXISTS` makes a missing column no error.

`DROP CONSTRAINT`
: Removes a constraint by its name (see `sys.objects` or `sys.key_constraints`). `IF EXISTS` makes a missing one no
  error.

## Remarks

- To rename a table, a column or an index, use [sp_rename](sp-rename.md).
- `ALTER TABLE` is transactional: inside a transaction, `ROLLBACK` undoes it.
- An unknown table is error 4902; an unknown column is 207.

## Differences from SQL Server

- One action per statement: several columns or constraints in one `ADD`, or `DROP COLUMN a, b`, give error 50000
  ("lexdb: ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA").
- **`ADD CONSTRAINT name DEFAULT value FOR column`** is error 102. Give the default when the column is made.
- `WITH CHECK` and `WITH NOCHECK` before `ADD`, `CHECK CONSTRAINT` and `NOCHECK CONSTRAINT` (enabling and disabling
  a constraint), `SET (LOCK_ESCALATION = ...)`, `SWITCH`, `REBUILD`, and `ENABLE` and `DISABLE TRIGGER` give the
  same error 50000.
- Adding a `NOT NULL` column without a default to a table with rows is error 515 with lexdb's text (SQL Server:
  4901). A column that already exists is 50000 (SQL Server: 2705); dropping an unknown column is 207 (SQL Server:
  4924).
- A second primary key by `ADD CONSTRAINT` is error 50000 (`multiple primary keys for table "emp" are not allowed`;
  SQL Server: 8110, which `CREATE TABLE` does give).
- PostgreSQL's `VALIDATE CONSTRAINT` and `SET SCHEMA` are taken in this door.

## Examples

<!--setup: tsql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30) NOT NULL);
CREATE TABLE dbo.emp (id int PRIMARY KEY, name varchar(10) NOT NULL, dept_id int);
INSERT dbo.dept VALUES (1, N'Sales');
INSERT dbo.emp VALUES (1, 'Ann', 1), (2, 'Bob', 9);
-->

The examples use two tables:

```sql
CREATE TABLE dbo.dept (id int PRIMARY KEY, name nvarchar(30) NOT NULL);
CREATE TABLE dbo.emp (id int PRIMARY KEY, name varchar(10) NOT NULL, dept_id int);
INSERT dbo.dept VALUES (1, N'Sales');
INSERT dbo.emp VALUES (1, 'Ann', 1), (2, 'Bob', 9);
```

### A. Add columns

<!-- example: tsql -->
```sql
ALTER TABLE dbo.emp ADD salary decimal(10, 2) NULL;
ALTER TABLE dbo.emp ADD active bit NOT NULL DEFAULT 1;
ALTER TABLE dbo.emp ADD yearly AS (salary * 12);
ALTER TABLE dbo.emp ADD badge int IDENTITY(500, 1);
SELECT * FROM dbo.emp ORDER BY id;
```

```text
id name dept_id salary active yearly badge
-- ---- ------- ------ ------ ------ -----
1  Ann  1       NULL   1      NULL   500
2  Bob  9       NULL   1      NULL   501

(2 rows affected)
```

### B. Add and drop constraints

<!-- example: tsql -->
```sql
ALTER TABLE dbo.emp ADD CONSTRAINT ck_emp_salary CHECK (salary > 0);
ALTER TABLE dbo.emp ADD CONSTRAINT uq_emp_name UNIQUE (name);
SELECT name, type_desc FROM sys.objects WHERE parent_object_id = OBJECT_ID('dbo.emp') ORDER BY name;
ALTER TABLE dbo.emp DROP CONSTRAINT uq_emp_name;
ALTER TABLE dbo.emp DROP CONSTRAINT IF EXISTS uq_nothere;
```

```text
name          type_desc
------------- ----------------------
ck_emp_salary CHECK_CONSTRAINT
DF_emp_active DEFAULT_CONSTRAINT
emp_pkey      PRIMARY_KEY_CONSTRAINT
uq_emp_name   UNIQUE_CONSTRAINT

(4 rows affected)
```

### C. A foreign key is checked against the rows

<!-- example: tsql -->
```sql
ALTER TABLE dbo.emp ADD CONSTRAINT fk_emp_dept FOREIGN KEY (dept_id) REFERENCES dbo.dept (id);
UPDATE dbo.emp SET dept_id = 1 WHERE id = 2;
ALTER TABLE dbo.emp ADD CONSTRAINT fk_emp_dept FOREIGN KEY (dept_id) REFERENCES dbo.dept (id);
```

```text
Msg 547, Level 16, State 1, Line 1
insert or update on table "emp" violates foreign key constraint "fk_emp_dept"
(1 row affected)
```

### D. Change a column's type

`salary` cannot change while the computed column `yearly` uses it (error 5074); `name` can.

<!-- example: tsql -->
```sql
ALTER TABLE dbo.emp ALTER COLUMN name nvarchar(40) NOT NULL;
ALTER TABLE dbo.emp ALTER COLUMN salary decimal(12, 2) NULL;
SELECT c.name, t.name AS type, c.max_length, c.precision, c.is_nullable
FROM sys.columns AS c JOIN sys.types AS t ON t.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.emp') AND c.name IN ('name', 'salary');
```

```text
Msg 5074, Level 16, State 1, Line 2
The column 'yearly' is dependent on column 'salary'.
name   type     max_length precision is_nullable
------ -------- ---------- --------- -----------
name   nvarchar 80         0         0
salary decimal  9          10        1

(2 rows affected)
```

### E. Drop columns

<!-- example: tsql -->
```sql
ALTER TABLE dbo.emp DROP COLUMN yearly;
ALTER TABLE dbo.emp DROP COLUMN IF EXISTS nothere;
ALTER TABLE dbo.emp DROP COLUMN active;
SELECT * FROM dbo.emp ORDER BY id;
```

```text
id name dept_id salary badge
-- ---- ------- ------ -----
1  Ann  1       NULL   500
2  Bob  1       NULL   501

(2 rows affected)
```

### F. Errors

<!-- example: tsql -->
```sql
ALTER TABLE dbo.emp ALTER COLUMN dept_id varchar(3);
ALTER TABLE dbo.emp ADD extra int NOT NULL;
ALTER TABLE dbo.nothere ADD x int;
GO
ALTER TABLE dbo.emp DROP COLUMN nothere;
GO
ALTER TABLE dbo.emp ADD CONSTRAINT pk_emp_name PRIMARY KEY (name);
GO
```

```text
Msg 5074, Level 16, State 1, Line 1
The object 'fk_emp_dept' is dependent on column 'dept_id'.
Msg 515, Level 16, State 1, Line 2
column "extra" of relation "emp" contains null values
Msg 4902, Level 16, State 1, Line 3
Cannot find the object "nothere" because it does not exist or you do not have permissions.
Msg 207, Level 16, State 1, Line 1
Invalid column name 'nothere'.
Msg 50000, Level 16, State 1, Line 1
multiple primary keys for table "emp" are not allowed
```

### G. CLUSTERED and NONCLUSTERED in a constraint

<!-- example: tsql -->
```sql
ALTER TABLE dbo.dept ADD CONSTRAINT uq_dept_name UNIQUE NONCLUSTERED (name);
SELECT name, type_desc, is_unique, is_primary_key FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.dept') ORDER BY index_id;
```

```text
name         type_desc    is_unique is_primary_key
------------ ------------ --------- --------------
dept_pkey    CLUSTERED    1         1
uq_dept_name NONCLUSTERED 1         0

(2 rows affected)
```

### H. What lexdb does not take

<!-- example: tsql -->
```sql
ALTER TABLE dbo.emp ADD CONSTRAINT df_emp_salary DEFAULT 0 FOR salary;
GO
ALTER TABLE dbo.emp ADD a int NULL, b int NULL;
GO
ALTER TABLE dbo.emp NOCHECK CONSTRAINT fk_emp_dept;
GO
```

```text
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'DEFAULT'.
Msg 50000, Level 16, State 1, Line 1
lexdb: ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA
Msg 50000, Level 16, State 1, Line 1
lexdb: ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA
```

## See also

[CREATE TABLE](create-table.md) · [DROP TABLE](drop-table.md) · [sp_rename](sp-rename.md) ·
[CREATE INDEX](create-index.md)
