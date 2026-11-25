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
SELECT ... FROM INFORMATION_SCHEMA.COLUMN_PRIVILEGES
SELECT ... FROM INFORMATION_SCHEMA.DOMAINS
SELECT ... FROM INFORMATION_SCHEMA.ROUTINES
SELECT ... FROM INFORMATION_SCHEMA.PARAMETERS
SELECT ... FROM INFORMATION_SCHEMA.VIEW_TABLE_USAGE
SELECT ... FROM INFORMATION_SCHEMA.VIEW_COLUMN_USAGE
```

## Views

The names resolve to PostgreSQL's `information_schema` views, so each has PostgreSQL's columns, in lower case, with
PostgreSQL's values, except `SCHEMATA`, `ROUTINES`, `PARAMETERS` and the two `VIEW_` views, which give SQL Server's rows
(below). They answer from the same catalog as [the `sys` views](catalog-tables.md).

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
: The columns of each key: `constraint_name`, `table_name`, `column_name`, and `ordinal_position` in the first. For a
  foreign key, `CONSTRAINT_COLUMN_USAGE` gives the key's own columns (`pid` of the child), as SQL Server does.

`REFERENTIAL_CONSTRAINTS`
: `constraint_name`, `unique_constraint_name` (the key it points to), `match_option`, `update_rule`, `delete_rule`.

`CHECK_CONSTRAINTS`
: `constraint_name` and `check_clause`.

`ASSERTIONS`
: One row per [assertion](create-assertion.md) (the standard's view; SQL Server has none): `constraint_catalog`,
  `constraint_schema`, `constraint_name`, `is_deferrable`, `initially_deferred`. An assertion also has a row in
  `CHECK_CONSTRAINTS` (its condition as written) and one in `CONSTRAINT_COLUMN_USAGE` for each column it reads. It has
  **no `sys.objects` row**: SQL Server has no object type for one, and a made-up type would be listed by SSMS's Object
  Explorer and `sp_help` under nothing. So SSMS, `sp_help` and mssql-jdbc's `DatabaseMetaData` do not see it,
  and `OBJECT_ID('a')` is NULL.

`SCHEMATA`
: SQL Server's schemas: `dbo`, `guest`, `INFORMATION_SCHEMA`, `sys`, the nine `db_*` role schemas and the schemas made
  with `CREATE SCHEMA`. Columns `catalog_name`, `schema_name`, `schema_owner` (the owner of a schema made `CREATE SCHEMA
  s AUTHORIZATION x`, `x`; `dbo` for `dbo` and for a schema made without `AUTHORIZATION`; each fixed schema is its own
  owner), `default_character_set_catalog`,
  `default_character_set_schema`, `default_character_set_name` (`iso_1`), `sql_path`.

`SEQUENCES`
: `sequence_schema`, `sequence_name`, `data_type`, `start_value`, `minimum_value`, `maximum_value`, `increment`,
  `cycle_option`.

`TABLE_PRIVILEGES`
: `grantor`, `grantee`, `table_schema`, `table_name`, `privilege_type`, `is_grantable`.

`COLUMN_PRIVILEGES`, `DOMAINS`
: No rows: lexdb grants on whole tables, never on columns, and `DOMAINS` does not list its table types, and it has
  no alias types (`CREATE TYPE ... FROM`). The views exist so that tools that read them work. Their columns are PostgreSQL's, in lower case (see below).

`ROUTINES`, `PARAMETERS`
: The T-SQL procedures and functions (those made in this door; the PostgreSQL door's functions are listed by its own
  `information_schema.routines`). `ROUTINES`: `specific_schema`, `specific_name`, `routine_schema`, `routine_name`,
  `routine_type` (`PROCEDURE` or `FUNCTION`), `data_type` (SQL Server's name for a function's result type, NULL for a
  procedure), `routine_body` (`SQL`), `routine_definition`, `is_deterministic`, `sql_data_access` (`READS` for a
  function, `MODIFIES` for a procedure). `PARAMETERS`: `specific_name`, `ordinal_position`, `parameter_mode` (`IN`,
  `INOUT` for `OUTPUT`, and `OUT` for a function's result, at position 0, with `is_result` `YES`), `parameter_name`
  (`@x`), `data_type`.

`VIEW_TABLE_USAGE`, `VIEW_COLUMN_USAGE`
: The tables and views each view reads (`view_catalog`, `view_schema`, `view_name`, `table_catalog`, `table_schema`,
  `table_name`) and, in the second, the columns of them it names (`column_name`: by name, qualified by the table or an
  alias; all of them for `*`).

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
- The schema columns (`table_schema`, `constraint_schema`, `routine_schema`, `schema_name` ...) show `dbo` where
  lexdb's schema is `public`, as `sys.schemas` does.
- `SCHEMATA`'s catalog name is `lexdb` (SQL Server: the database's name), and the column names are in lower case (SQL
  Server: upper case).
- Constraint names are lexdb's, `table_pkey`, `table_column_fkey`, and `view_definition` is the text of the query.
- `COLUMN_PRIVILEGES` and `DOMAINS` have no rows and PostgreSQL's columns in lower case. SQL Server's `DOMAINS` has 17
  columns (`DOMAIN_CATALOG` to `DOMAIN_DEFAULT`), lexdb's 27 (PostgreSQL's), and it lists table types
  (`CREATE TYPE ... AS TABLE`, `data_type` `table type`) and alias types, which lexdb's does not.
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

A schema made `AUTHORIZATION` a role or user is owned by it.

<!-- example: tsql -->
```sql
CREATE ROLE clerk;
GO
CREATE SCHEMA ops AUTHORIZATION clerk;
GO
SELECT schema_name, schema_owner FROM INFORMATION_SCHEMA.SCHEMATA WHERE schema_name IN ('dbo', 'hr', 'ops') ORDER BY schema_name;
```

```text
schema_name schema_owner
----------- ------------
dbo         dbo
hr          dbo
ops         clerk

(3 rows affected)
```

### G. Procedures and functions

<!-- example: tsql -->
```sql
SELECT routine_schema, routine_name, routine_type, data_type, routine_body, sql_data_access FROM INFORMATION_SCHEMA.ROUTINES WHERE routine_schema = 'hr' ORDER BY routine_name;
SELECT specific_name, ordinal_position, parameter_mode, is_result, parameter_name, data_type FROM INFORMATION_SCHEMA.PARAMETERS WHERE specific_schema = 'hr' ORDER BY specific_name, ordinal_position;
SELECT name, type_desc FROM sys.objects WHERE type IN ('P', 'FN') AND schema_id = SCHEMA_ID('hr') ORDER BY name;
```

```text
routine_schema routine_name routine_type data_type routine_body sql_data_access
-------------- ------------ ------------ --------- ------------ ---------------
hr             f_sq         FUNCTION     int       SQL          READS
hr             p_raise      PROCEDURE    NULL      SQL          MODIFIES

(2 rows affected)

specific_name ordinal_position parameter_mode is_result parameter_name data_type
------------- ---------------- -------------- --------- -------------- ---------
f_sq          0                OUT            YES                      int
f_sq          1                IN             NO        @x             int
p_raise       1                IN             NO        @pct           int
p_raise       2                INOUT          NO        @out           int

(4 rows affected)

name    type_desc
------- --------------------
f_sq    SQL_SCALAR_FUNCTION
p_raise SQL_STORED_PROCEDURE

(2 rows affected)
```

### H. What a view reads, and the columns of a foreign key

<!-- example: tsql -->
```sql
CREATE VIEW hr.v_dept_emp AS SELECT d.name AS dept, e.name FROM hr.dept AS d JOIN hr.v_emp AS e ON e.id = d.id;
GO
SELECT view_name, table_name FROM INFORMATION_SCHEMA.VIEW_TABLE_USAGE WHERE view_schema = 'hr' ORDER BY view_name, table_name;
SELECT view_name, table_name, column_name FROM INFORMATION_SCHEMA.VIEW_COLUMN_USAGE WHERE view_schema = 'hr' ORDER BY view_name, table_name, column_name;
SELECT table_name, column_name, constraint_name FROM INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE WHERE constraint_name LIKE '%fkey%' ORDER BY constraint_name, column_name;
```

```text
view_name  table_name
---------- ----------
v_dept_emp dept
v_dept_emp v_emp
v_emp      emp

(3 rows affected)

view_name  table_name column_name
---------- ---------- -----------
v_dept_emp dept       id
v_dept_emp dept       name
v_dept_emp v_emp      id
v_dept_emp v_emp      name
v_emp      emp        id
v_emp      emp        name

(6 rows affected)

table_name column_name constraint_name
---------- ----------- ----------------
emp        dept_id     emp_dept_id_fkey

(1 row affected)
```

### I. Views without rows

This database has a table type (`hr.idl`), which SQL Server's `DOMAINS` would list.

<!-- example: tsql -->
```sql
SELECT COUNT(*) AS n FROM INFORMATION_SCHEMA.DOMAINS;
GO
SELECT * FROM INFORMATION_SCHEMA.COLUMN_PRIVILEGES;
```

```text
n
-
0

(1 row affected)

grantor grantee table_catalog table_schema table_name column_name privilege_type is_grantable
------- ------- ------------- ------------ ---------- ----------- -------------- ------------

(0 rows affected)
```

## See also

[Schemas, tables, columns and indexes](catalog-tables.md), [Constraints](catalog-constraints.md),
[Views, procedures and sequences](catalog-programmability.md)
