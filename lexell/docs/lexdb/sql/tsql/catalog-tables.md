# Catalog views: schemas, tables, columns and indexes (Transact-SQL)

`sys.schemas`, `sys.objects`, `sys.tables`, `sys.columns`, `sys.types`, `sys.indexes`, `sys.index_columns`,
`sys.identity_columns`, `sys.computed_columns` and the `sys.all_*` forms.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SELECT ... FROM sys.schemas
SELECT ... FROM sys.objects | sys.all_objects | sys.system_objects
SELECT ... FROM sys.tables
SELECT ... FROM sys.columns | sys.all_columns
SELECT ... FROM sys.types
SELECT ... FROM sys.indexes
SELECT ... FROM sys.index_columns
SELECT ... FROM sys.identity_columns
SELECT ... FROM sys.computed_columns
```

A catalog view must be written with its `sys.` schema.

## Views

Each view has the columns of SQL Server 2022. The columns named below are the ones lexdb fills with data; the
others are 0, NULL or a fixed value (for example `is_replicated` is 0).

`sys.schemas`
: `name`, `schema_id`, `principal_id` (the owner's: that of `dbo` for `dbo` and for a schema made without
  `AUTHORIZATION`). The schemas of the database, the system ones (`sys`, `INFORMATION_SCHEMA`, `guest` and the fixed
  role names) included.

`sys.objects`, `sys.all_objects`
: One row per table, view, procedure, function, sequence, constraint, table type and index-owning object:
  `name`, `object_id`, `schema_id`, `parent_object_id` (the table, for a constraint), `type`, `type_desc`,
  `create_date`, `modify_date`, `is_ms_shipped`. `type` is `U` (table), `V` (view), `P` (procedure), `FN` and `IF`
  (scalar and inline table-valued function), `SO` (sequence), `TT` (table type), `PK`, `UQ`, `F`, `C` and `D`
  (constraints). `sys.all_objects` and `sys.system_objects` include lexdb's own catalog views.

`sys.tables`
: One row per user table: the columns of `sys.objects` and `max_column_id_used`, `uses_ansi_nulls`,
  `lock_escalation_desc`, `temporal_type_desc` and others, all with their usual values.

`sys.columns`, `sys.all_columns`
: One row per column of a table, view or table type: `object_id`, `name`, `column_id` (from 1), `system_type_id`,
  `user_type_id`, `max_length`, `precision`, `scale`, `collation_name`, `is_nullable`, `is_identity`,
  `is_computed`, `default_object_id`. `max_length` is -1 for `max` types.

`sys.types`
: The system types and the table types: `name`, `system_type_id`, `user_type_id`, `schema_id`, `max_length`,
  `precision`, `scale`, `is_nullable`, `is_user_defined`, `is_table_type`. See [Numeric types](data-types-numeric.md)
  for the id of each type.

`sys.indexes`
: One row per index, the key indexes included: `object_id`, `name`, `index_id`, `type` and `type_desc`
  (`CLUSTERED` for the table's clustered index, `NONCLUSTERED` for every other, `HEAP` for a table without one),
  `is_unique`, `is_primary_key`, `is_unique_constraint`, `has_filter`, `filter_definition`. The clustered index is
  `index_id` 1; a heap's row has `index_id` 0 and a NULL name.

`sys.index_columns`
: `object_id`, `index_id`, `index_column_id`, `column_id`, `key_ordinal`, `is_descending_key`,
  `is_included_column`.

`sys.identity_columns`, `sys.computed_columns`
: The columns of `sys.columns` for identity and computed columns, with `seed_value`, `increment_value` and
  `last_value` for the first, `definition` and `is_persisted` for the second.

## Remarks

- Join to `sys.schemas` on `schema_id` to get a schema's name; join `sys.columns` to `sys.tables` on `object_id`.
- `OBJECT_ID('schema.name')`, `OBJECT_NAME(id)` and `SCHEMA_NAME(id)` turn names into ids and back: see
  [system functions](functions-system.md).
- Object ids, schema ids and the creation date are not shown in the examples: ids are derived from the name and
  differ from SQL Server's, and every `create_date` and `modify_date` is 2000-01-01.
- `INFORMATION_SCHEMA` has the same facts in the standard's shape: see
  [INFORMATION_SCHEMA views](catalog-information-schema.md).

## Differences from SQL Server

- `sys.indexes` shows what `CLUSTERED` and `NONCLUSTERED` said (a primary key is the clustered index unless it is
  `NONCLUSTERED` or another index is `CLUSTERED`), but lexdb has one kind of index and stores a table in its primary
  key's order whatever the label (see [CREATE INDEX](create-index.md)).
- Names of constraints and keys that were not named follow PostgreSQL's pattern (`emp_pkey`, `emp_dept_id_fkey`),
  not SQL Server's `PK__emp__3213E83F...`. A default constraint is always called `DF_table_column`, whatever
  name was given.
- A computed column's type is reported as lexdb works it out: `salary / 10` on a `decimal(10,2)` is
  `decimal(21,13)`.
- `create_date` and `modify_date` are always 2000-01-01.
- `sys.index_columns` lists the key columns of an index only: the columns of `INCLUDE (...)` are missing (example E:
  `ix_emp_name` has `INCLUDE (salary)`). `sys.types` gives `decimal` and `numeric` a scale of 38.
- A table type's own row in `sys.objects` is named `TT_name_hash`, with a hash that lexdb picks.
- `sys.database_role_members`, `sys.partitions`, `sys.allocation_units`, `sys.sysobjects` and the other old
  `sys.sys*` views do not exist (error 208).

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

The examples use these objects (the other catalog pages use them too):

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

### A. The objects of a schema

<!-- example: tsql -->
```sql
SELECT o.name, o.type, o.type_desc, OBJECT_NAME(o.parent_object_id) AS parent
FROM sys.objects o
WHERE o.schema_id = SCHEMA_ID('hr') AND o.type <> 'TT'
ORDER BY o.name;
```

```text
name             type type_desc              parent
---------------- ---- ---------------------- ------
ck_sal           C    CHECK_CONSTRAINT       emp
dept             U    USER_TABLE             NULL
dept_name_key    UQ   UNIQUE_CONSTRAINT      dept
dept_pkey        PK   PRIMARY_KEY_CONSTRAINT dept
DF_emp_salary    D    DEFAULT_CONSTRAINT     emp
emp              U    USER_TABLE             NULL
emp_dept_id_fkey F    FOREIGN_KEY_CONSTRAINT emp
emp_pkey         PK   PRIMARY_KEY_CONSTRAINT emp
f_sq             FN   SQL_SCALAR_FUNCTION    NULL
p_raise          P    SQL_STORED_PROCEDURE   NULL
sq               SO   SEQUENCE_OBJECT        NULL
v_emp            V    VIEW                   NULL

(12 rows affected)
```

### B. Tables and their schemas

<!-- example: tsql -->
```sql
SELECT s.name AS schema_name, t.name AS table_name, t.type_desc, t.max_column_id_used
FROM sys.tables t JOIN sys.schemas s ON s.schema_id = t.schema_id
ORDER BY s.name, t.name;
GO
SELECT name FROM sys.schemas WHERE name IN ('hr', 'dbo', 'sys', 'INFORMATION_SCHEMA') ORDER BY name;
```

```text
schema_name table_name type_desc  max_column_id_used
----------- ---------- ---------- ------------------
hr          dept       USER_TABLE 2
hr          emp        USER_TABLE 5

(2 rows affected)

name
------------------
dbo
hr
INFORMATION_SCHEMA
sys

(4 rows affected)
```

### C. The columns of a table

<!-- example: tsql -->
```sql
SELECT c.column_id, c.name, t.name AS type_name, c.max_length, c.precision, c.scale, c.is_nullable, c.is_identity,
       c.is_computed
FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID('hr.emp')
ORDER BY c.column_id;
```

```text
column_id name    type_name max_length precision scale is_nullable is_identity is_computed
--------- ------- --------- ---------- --------- ----- ----------- ----------- -----------
1         id      int       4          10        0     0           1           0
2         dept_id int       4          10        0     0           0           0
3         name    varchar   40         0         0     0           0           0
4         salary  decimal   9          10        2     1           0           0
5         bonus   decimal   13         21        13    1           0           1

(5 rows affected)
```

### D. Identity and computed columns

<!-- example: tsql -->
```sql
SELECT OBJECT_NAME(object_id) AS table_name, name, seed_value, increment_value FROM sys.identity_columns;
SELECT OBJECT_NAME(object_id) AS table_name, name, definition, is_persisted FROM sys.computed_columns;
```

```text
table_name name seed_value increment_value
---------- ---- ---------- ---------------
emp        id   1          1

(1 row affected)

table_name name  definition      is_persisted
---------- ----- --------------- ------------
emp        bonus ([salary]/(10)) 0

(1 row affected)
```

### E. Indexes and their columns

<!-- example: tsql -->
```sql
SELECT i.name AS index_name, i.type_desc, i.is_unique, i.is_primary_key, i.is_unique_constraint
FROM sys.indexes i
WHERE i.object_id = OBJECT_ID('hr.emp')
ORDER BY i.index_id;
GO
SELECT i.name AS index_name, c.name AS column_name, ic.key_ordinal, ic.is_included_column
FROM sys.indexes i
JOIN sys.index_columns ic ON ic.object_id = i.object_id AND ic.index_id = i.index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE i.object_id = OBJECT_ID('hr.emp')
ORDER BY i.index_id, ic.index_column_id;
GO
CREATE TABLE hr.note (txt varchar(40));
CREATE CLUSTERED INDEX cx_note ON hr.note (txt);
GO
SELECT OBJECT_NAME(object_id) AS tbl, index_id, name, type_desc FROM sys.indexes
WHERE object_id IN (OBJECT_ID('hr.note'), OBJECT_ID('hr.emp')) ORDER BY object_id, index_id;
GO
DROP INDEX cx_note ON hr.note;
GO
SELECT index_id, name, type_desc FROM sys.indexes WHERE object_id = OBJECT_ID('hr.note');
```

```text
index_name  type_desc    is_unique is_primary_key is_unique_constraint
----------- ------------ --------- -------------- --------------------
emp_pkey    CLUSTERED    1         1              0
ix_emp_name NONCLUSTERED 0         0              0

(2 rows affected)

index_name  column_name key_ordinal is_included_column
----------- ----------- ----------- ------------------
emp_pkey    id          1           0
ix_emp_name name        1           0

(2 rows affected)

tbl  index_id name        type_desc
---- -------- ----------- ------------
note 1        cx_note     CLUSTERED
emp  1        emp_pkey    CLUSTERED
emp  2        ix_emp_name NONCLUSTERED

(3 rows affected)

index_id name type_desc
-------- ---- ---------
0        NULL HEAP

(1 row affected)
```

### F. Types

<!-- example: tsql -->
```sql
SELECT name, system_type_id, user_type_id, max_length, precision, scale, is_user_defined, is_table_type
FROM sys.types
WHERE name IN ('int', 'bigint', 'varchar', 'nvarchar', 'bit', 'uniqueidentifier', 'idl')
ORDER BY name;
```

```text
name             system_type_id user_type_id max_length precision scale is_user_defined is_table_type
---------------- -------------- ------------ ---------- --------- ----- --------------- -------------
bigint           127            127          8          19        0     0               0
bit              104            104          1          1         0     0               0
idl              243            1637520911   -1         0         0     1               1
int              56             56           4          10        0     0               0
nvarchar         231            231          8000       0         0     0               0
uniqueidentifier 36             36           16         0         0     0               0
varchar          167            167          8000       0         0     0               0

(7 rows affected)
```

### G. A view that is missing

<!-- example: tsql -->
```sql
SELECT * FROM sys.database_role_members;
GO
SELECT COUNT(*) AS rows_without_prefix FROM tables;
```

```text
Msg 208, Level 16, State 1, Line 1
Invalid object name 'sys.database_role_members'.
Msg 208, Level 16, State 1, Line 1
Invalid object name 'tables'.
```

## See also

[Constraints](catalog-constraints.md), [Views, procedures and sequences](catalog-programmability.md),
[Security and server views](catalog-security.md), [INFORMATION_SCHEMA views](catalog-information-schema.md),
[System functions](functions-system.md)
