# Catalog views: views, procedures, functions, sequences and types (Transact-SQL)

`sys.views`, `sys.procedures`, `sys.parameters`, `sys.sql_modules`, `sys.sequences` and `sys.table_types`.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SELECT ... FROM sys.views | sys.all_views
SELECT ... FROM sys.procedures
SELECT ... FROM sys.parameters | sys.all_parameters
SELECT ... FROM sys.sql_modules
SELECT ... FROM sys.sequences
SELECT ... FROM sys.table_types
```

## Views

Each view has the columns of SQL Server 2022. The columns named below are filled; the others are 0, NULL or a
fixed value.

`sys.views`
: One row per user view: the columns of [sys.objects](catalog-tables.md) (`type` `V`), and flags such as
  `with_check_option` (0).

`sys.all_views`
: The user views and lexdb's own catalog views.

`sys.procedures`
: One row per stored procedure (`type` `P`, `type_desc` `SQL_STORED_PROCEDURE`). Functions are in `sys.objects`,
  not here.

`sys.parameters`
: One row per parameter of a procedure or function: `object_id`, `name` (with the `@`), `parameter_id`,
  `system_type_id`, `user_type_id`, `max_length`, `precision`, `scale`, `is_output`, `has_default_value`,
  `is_readonly` (table-valued parameters), `is_nullable`. `sys.all_parameters` has no rows.

`sys.sql_modules`
: The text of each view, procedure and function: `object_id`, `definition` (the `CREATE` statement as it was
  written), `uses_ansi_nulls`, `uses_quoted_identifier`, `is_schema_bound`.

`sys.sequences`
: `name`, `start_value`, `increment`, `minimum_value`, `maximum_value`, `is_cycling`, `is_cached`, `cache_size`,
  `system_type_id` (127 for `bigint`), `precision`, `current_value`, `is_exhausted`.

`sys.table_types`
: One row per table type made with [CREATE TYPE](create-type.md): `name`, `system_type_id` (243),
  `user_type_id`, `schema_id`, `is_table_type`, `type_table_object_id`.

## Remarks

- `OBJECT_DEFINITION(object_id)` gives one module's text: see [system functions](functions-system.md).
- `sys.sequences.current_value` is the last value handed out, or the start value before the first.
- A table type's columns are in `sys.columns` under its `type_table_object_id`.

## Differences from SQL Server

- `sys.sequences.cache_size` is 1 and `is_cached` 1, whatever `CACHE` says.
- `create_date` and `modify_date` are always 2000-01-01.
- `sys.sql_modules` lists views, procedures and functions only.

## Examples

<!--setup: tsql
CREATE SCHEMA hr;
GO
CREATE TABLE hr.dept (id int PRIMARY KEY, name varchar(30) NOT NULL UNIQUE);
CREATE TABLE hr.emp (id int IDENTITY(1,1) PRIMARY KEY, dept_id int NOT NULL REFERENCES hr.dept (id), name varchar(40) NOT NULL, salary decimal(10,2) CONSTRAINT df_sal DEFAULT 1000, bonus AS (salary / 10), CONSTRAINT ck_sal CHECK (salary >= 0));
CREATE INDEX ix_emp_name ON hr.emp (name) INCLUDE (salary);
GO
CREATE VIEW hr.v_emp AS SELECT id, name FROM hr.emp;
GO
CREATE PROCEDURE hr.p_raise @pct int, @out int OUTPUT AS SET @out = @pct * 2;
GO
CREATE FUNCTION hr.f_sq (@x int) RETURNS int AS BEGIN RETURN @x * @x; END;
GO
CREATE SEQUENCE hr.sq START WITH 5;
GO
CREATE TYPE hr.idl AS TABLE (id int);
GO
-->

The examples use the objects of [the first catalog page](catalog-tables.md):

```sql
CREATE SCHEMA hr;
GO
CREATE TABLE hr.dept (id int PRIMARY KEY, name varchar(30) NOT NULL UNIQUE);
CREATE TABLE hr.emp (id int IDENTITY(1,1) PRIMARY KEY, dept_id int NOT NULL REFERENCES hr.dept (id),
    name varchar(40) NOT NULL, salary decimal(10,2) CONSTRAINT df_sal DEFAULT 1000, bonus AS (salary / 10),
    CONSTRAINT ck_sal CHECK (salary >= 0));
CREATE INDEX ix_emp_name ON hr.emp (name) INCLUDE (salary);
GO
CREATE VIEW hr.v_emp AS SELECT id, name FROM hr.emp;
GO
CREATE PROCEDURE hr.p_raise @pct int, @out int OUTPUT AS SET @out = @pct * 2;
GO
CREATE FUNCTION hr.f_sq (@x int) RETURNS int AS BEGIN RETURN @x * @x; END;
GO
CREATE SEQUENCE hr.sq START WITH 5;
GO
CREATE TYPE hr.idl AS TABLE (id int);
```

### A. Views and their definitions

<!-- example: tsql -->
```sql
SELECT v.name, v.type_desc, m.definition
FROM sys.views v JOIN sys.sql_modules m ON m.object_id = v.object_id;
```

```text
name  type_desc definition
----- --------- -----------------------------------------------------
v_emp VIEW      CREATE VIEW hr.v_emp AS SELECT id, name FROM hr.emp;

(1 row affected)
```

### B. Procedures, functions and other objects with code

<!-- example: tsql -->
```sql
SELECT name, type, type_desc FROM sys.procedures;
SELECT name, type, type_desc FROM sys.objects WHERE type IN ('FN', 'IF', 'TF') ORDER BY name;
SELECT OBJECT_NAME(object_id) AS module, LEN(definition) AS definition_length
FROM sys.sql_modules ORDER BY 1;
```

```text
name    type type_desc
------- ---- --------------------
p_raise P    SQL_STORED_PROCEDURE

(1 row affected)

name type type_desc
---- ---- -------------------
f_sq FN   SQL_SCALAR_FUNCTION

(1 row affected)

module  definition_length
------- -----------------
f_sq    75
p_raise 78
v_emp   53

(3 rows affected)
```

### C. Parameters

<!-- example: tsql -->
```sql
SELECT OBJECT_NAME(p.object_id) AS routine, p.parameter_id, p.name, t.name AS type_name, p.is_output
FROM sys.parameters p JOIN sys.types t ON t.user_type_id = p.user_type_id
ORDER BY routine, p.parameter_id;
```

```text
routine parameter_id name type_name is_output
------- ------------ ---- --------- ---------
f_sq    0                 int       1
f_sq    1            @x   int       0
p_raise 1            @pct int       0
p_raise 2            @out int       1

(4 rows affected)
```

### D. Sequences

<!-- example: tsql -->
```sql
SELECT name, start_value, increment, minimum_value, maximum_value, is_cycling, current_value FROM sys.sequences;
SELECT NEXT VALUE FOR hr.sq AS first_value, NEXT VALUE FOR hr.sq AS second_value;
SELECT name, current_value FROM sys.sequences;
```

```text
name start_value increment minimum_value maximum_value       is_cycling current_value
---- ----------- --------- ------------- ------------------- ---------- -------------
sq   5           1         1             9223372036854775807 0          5

(1 row affected)

first_value second_value
----------- ------------
5           6

(1 row affected)

name current_value
---- -------------
sq   6

(1 row affected)
```

### E. Table types

<!-- example: tsql -->
```sql
SELECT name, is_table_type, is_user_defined FROM sys.table_types;
SELECT t.name AS type_name, c.name AS column_name
FROM sys.table_types t JOIN sys.columns c ON c.object_id = t.type_table_object_id;
```

```text
name is_table_type is_user_defined
---- ------------- ---------------
idl  1             1

(1 row affected)

type_name column_name
--------- -----------
idl       id

(1 row affected)
```

## See also

[CREATE VIEW](create-view.md), [CREATE PROCEDURE](create-procedure.md), [CREATE FUNCTION](create-function.md),
[CREATE SEQUENCE](create-sequence.md), [CREATE TYPE](create-type.md),
[Schemas, tables, columns and indexes](catalog-tables.md)
