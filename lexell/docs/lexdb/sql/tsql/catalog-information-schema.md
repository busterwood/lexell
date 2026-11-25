# INFORMATION_SCHEMA views (Transact-SQL)

The standard catalog views, as lexdb answers them in the SQL Server door.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SELECT ... FROM INFORMATION_SCHEMA.TABLES
SELECT ... FROM INFORMATION_SCHEMA.COLUMNS
SELECT ... FROM INFORMATION_SCHEMA.VIEWS
SELECT ... FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
SELECT ... FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
SELECT ... FROM INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE
SELECT ... FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
SELECT ... FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
SELECT ... FROM INFORMATION_SCHEMA.SCHEMATA
SELECT ... FROM INFORMATION_SCHEMA.SEQUENCES
SELECT ... FROM INFORMATION_SCHEMA.TABLE_PRIVILEGES
SELECT ... FROM INFORMATION_SCHEMA.ROUTINES
SELECT ... FROM INFORMATION_SCHEMA.PARAMETERS
```

## Views

The names resolve to PostgreSQL's `information_schema` views, so each has PostgreSQL's columns, in lower case, with
PostgreSQL's values. They answer from the same catalog as [the `sys` views](catalog-tables.md).

`TABLES`
: `table_catalog` (`lexdb`), `table_schema`, `table_name`, `table_type` (`BASE TABLE` or `VIEW`),
  `is_insertable_into`.

`COLUMNS`
: `table_catalog`, `table_schema`, `table_name`, `column_name`, `ordinal_position`, `column_default`,
  `is_nullable` (`YES`/`NO`), `data_type`, `character_maximum_length`, `numeric_precision`, `numeric_scale`,
  `datetime_precision`, `udt_name`, `is_identity`, `identity_start`, `identity_increment`, `is_generated`.

`VIEWS`
: `table_schema`, `table_name`, `view_definition`, `check_option`, `is_updatable`.

`TABLE_CONSTRAINTS`
: `constraint_schema`, `constraint_name`, `table_schema`, `table_name`, `constraint_type` (`PRIMARY KEY`,
  `UNIQUE`, `FOREIGN KEY`, `CHECK`).

`KEY_COLUMN_USAGE`, `CONSTRAINT_COLUMN_USAGE`
: The columns of each key: `constraint_name`, `table_name`, `column_name`, `ordinal_position`.

`REFERENTIAL_CONSTRAINTS`
: `constraint_name`, `unique_constraint_name` (the key it points to), `match_option`, `update_rule`, `delete_rule`.

`CHECK_CONSTRAINTS`
: `constraint_name` and `check_clause`.

`SCHEMATA`
: `schema_name`, `schema_owner`.

`SEQUENCES`
: `sequence_schema`, `sequence_name`, `data_type`, `start_value`, `minimum_value`, `maximum_value`, `increment`,
  `cycle_option`.

`TABLE_PRIVILEGES`
: `grantor`, `grantee`, `table_schema`, `table_name`, `privilege_type`, `is_grantable`.

`ROUTINES`, `PARAMETERS`
: Present, with PostgreSQL's columns. They list the functions and procedures of the PostgreSQL door only: see
  the differences below.

## Remarks

- The column names are in lower case, as PostgreSQL writes them; a name you write in capitals in the select list comes
  back as you wrote it.
- Table and schema names are those of the database: the tables of `dbo` are in `table_schema` `dbo`.

## Differences from SQL Server

- **The values are PostgreSQL's.** `data_type` is `integer`, `character varying`, `numeric`, `timestamp without
  time zone` and `bytea`, not `int`, `varchar`, `decimal`, `datetime2` and `varbinary`; `udt_name` is `int4`,
  `varchar`, `numeric`. Use `sys.columns` and `sys.types` when you need SQL Server's forms.
  `CHECK_CONSTRAINTS.check_clause` is SQL Server's text, `([salary]>=(0))`, as `sys.check_constraints.definition` is
  (see [constraints](catalog-constraints.md) for where it differs).
- `SCHEMATA` lists the schemas made with `CREATE SCHEMA`; `dbo` and the system schemas are not in it.
- Constraint names are lexdb's, `table_pkey`, `table_column_fkey`, and `view_definition` is the text of the query.
- `ROUTINES` and `PARAMETERS` have no rows for T-SQL procedures and functions: use `sys.procedures`,
  `sys.parameters` and `sys.sql_modules`.
- `COLUMN_PRIVILEGES`, `VIEW_COLUMN_USAGE`, `VIEW_TABLE_USAGE` and `DOMAINS` do not exist (error 208).
- The view `INFORMATION_SCHEMA.TABLES` has the extra PostgreSQL columns (`self_referencing_column_name`,
  `commit_action`, ...).

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

### A. Tables and views

<!-- example: tsql -->
```sql
SELECT table_schema, table_name, table_type FROM INFORMATION_SCHEMA.TABLES
WHERE table_schema = 'hr' ORDER BY table_name;
```

```text
table_schema table_name table_type
------------ ---------- ----------
hr           dept       BASE TABLE
hr           emp        BASE TABLE
hr           v_emp      VIEW

(3 rows affected)
```

### B. Columns

<!-- example: tsql -->
```sql
SELECT column_name, ordinal_position, is_nullable, data_type, character_maximum_length, numeric_precision,
       numeric_scale, is_identity
FROM INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = 'hr' AND table_name = 'emp'
ORDER BY ordinal_position;
```

```text
column_name ordinal_position is_nullable data_type         character_maximum_length numeric_precision numeric_scale is_identity
----------- ---------------- ----------- ----------------- ------------------------ ----------------- ------------- -----------
id          1                NO          integer           NULL                     32                0             YES
dept_id     2                NO          integer           NULL                     32                0             NO
name        3                NO          character varying 40                       NULL              NULL          NO
salary      4                YES         numeric           NULL                     10                2             NO
bonus       5                YES         numeric           NULL                     21                13            NO

(5 rows affected)
```

### C. Defaults

<!-- example: tsql -->
```sql
SELECT column_name, column_default FROM INFORMATION_SCHEMA.COLUMNS
WHERE table_schema = 'hr' AND table_name = 'emp' AND column_default IS NOT NULL;
```

```text
column_name column_default
----------- --------------
salary      1000

(1 row affected)
```

### D. Constraints

<!-- example: tsql -->
```sql
SELECT constraint_name, table_name, constraint_type FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
WHERE table_schema = 'hr' ORDER BY constraint_name;
GO
SELECT constraint_name, table_name, column_name, ordinal_position FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE table_schema = 'hr' ORDER BY constraint_name, ordinal_position;
GO
SELECT constraint_name, unique_constraint_name, update_rule, delete_rule FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS;
SELECT constraint_name, check_clause FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS;
```

```text
constraint_name  table_name constraint_type
---------------- ---------- ---------------
ck_sal           emp        CHECK
dept_name_key    dept       UNIQUE
dept_pkey        dept       PRIMARY KEY
emp_dept_id_fkey emp        FOREIGN KEY
emp_pkey         emp        PRIMARY KEY

(5 rows affected)

constraint_name  table_name column_name ordinal_position
---------------- ---------- ----------- ----------------
dept_name_key    dept       name        1
dept_pkey        dept       id          1
emp_dept_id_fkey emp        dept_id     1
emp_pkey         emp        id          1

(4 rows affected)

constraint_name  unique_constraint_name update_rule delete_rule
---------------- ---------------------- ----------- -----------
emp_dept_id_fkey dept_pkey              NO ACTION   NO ACTION

(1 row affected)

constraint_name check_clause
--------------- ---------------
ck_sal          ([salary]>=(0))

(1 row affected)
```

### E. Views and sequences

<!-- example: tsql -->
```sql
SELECT table_name, view_definition, is_updatable FROM INFORMATION_SCHEMA.VIEWS WHERE table_schema = 'hr';
SELECT sequence_name, data_type, start_value, increment, cycle_option FROM INFORMATION_SCHEMA.SEQUENCES;
```

```text
table_name view_definition              is_updatable
---------- ---------------------------- ------------
v_emp      SELECT id, name FROM hr.emp; NO

(1 row affected)

sequence_name data_type start_value increment cycle_option
------------- --------- ----------- --------- ------------
sq            bigint    5           1         NO

(1 row affected)
```

### F. Schemas

<!-- example: tsql -->
```sql
SELECT schema_name FROM INFORMATION_SCHEMA.SCHEMATA WHERE schema_name IN ('dbo', 'hr') ORDER BY schema_name;
```

```text
schema_name
-----------
hr

(1 row affected)
```

### G. Procedures and functions

<!-- example: tsql -->
```sql
SELECT routine_name, routine_type FROM INFORMATION_SCHEMA.ROUTINES WHERE routine_schema = 'hr';
SELECT name, type_desc FROM sys.objects WHERE type IN ('P', 'FN') AND schema_id = SCHEMA_ID('hr') ORDER BY name;
```

```text
routine_name routine_type
------------ ------------

(0 rows affected)

name    type_desc
------- --------------------
f_sq    SQL_SCALAR_FUNCTION
p_raise SQL_STORED_PROCEDURE

(2 rows affected)
```

### H. Views that do not exist

<!-- example: tsql -->
```sql
SELECT * FROM INFORMATION_SCHEMA.DOMAINS;
GO
SELECT * FROM INFORMATION_SCHEMA.COLUMN_PRIVILEGES;
```

```text
Msg 208, Level 16, State 1, Line 1
Invalid object name 'information_schema.domains'.
Msg 208, Level 16, State 1, Line 1
Invalid object name 'information_schema.column_privileges'.
```

## See also

[Schemas, tables, columns and indexes](catalog-tables.md), [Constraints](catalog-constraints.md),
[Views, procedures and sequences](catalog-programmability.md)
