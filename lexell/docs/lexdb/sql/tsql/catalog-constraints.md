# Catalog views: constraints (Transact-SQL)

`sys.key_constraints`, `sys.foreign_keys`, `sys.foreign_key_columns`, `sys.check_constraints` and
`sys.default_constraints`.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
SELECT ... FROM sys.key_constraints
SELECT ... FROM sys.foreign_keys
SELECT ... FROM sys.foreign_key_columns
SELECT ... FROM sys.check_constraints
SELECT ... FROM sys.default_constraints
```

## Views

Each view has the columns of SQL Server 2022. The columns named below are filled; the others are 0, NULL or a
fixed value. Every view except `sys.foreign_key_columns` also has the columns of `sys.objects` (`name`,
`object_id`, `schema_id`, `parent_object_id`, `type`, `type_desc`, `create_date`, `modify_date`):
`parent_object_id` is the table.

`sys.key_constraints`
: Primary keys (`type` `PK`) and unique constraints (`UQ`): `unique_index_id` (the `index_id` in
  [sys.indexes](catalog-tables.md)), `is_system_named`, `is_enforced`.

`sys.foreign_keys`
: `referenced_object_id`, `key_index_id`, `is_disabled` (1 after `NOCHECK CONSTRAINT`), `is_not_trusted` (1 for a key
  added `WITH NOCHECK`, disabled, or enabled again without `WITH CHECK`), `delete_referential_action` and
  `update_referential_action` (0 no action, 1 cascade, 2 set null, 3 set default) with their `_desc` names,
  `is_system_named`.

`sys.foreign_key_columns`
: One row per column of a foreign key: `constraint_object_id`, `constraint_column_id`, `parent_object_id`,
  `parent_column_id`, `referenced_object_id`, `referenced_column_id`.

`sys.check_constraints`
: `parent_column_id`, `definition` (the condition in SQL Server's bracketed form: `([salary]>=(0))`),
  `is_disabled`, `is_not_trusted` (as for a foreign key), `is_system_named`.

`sys.default_constraints`
: `parent_column_id`, `definition` (`((1000))`), `is_system_named`.

## Remarks

- Join a constraint to its table with `parent_object_id`, and to the column names with `sys.columns` on
  `parent_object_id = object_id` and `parent_column_id = column_id`.
- A constraint has the name it was given. An unnamed one gets lexdb's name: `table_pkey` for a primary key,
  `table_column_key` for a unique constraint, `table_column_fkey` for a foreign key.

- A disabled or untrusted `CHECK` or foreign key is not dropped from these views: read `is_disabled` and
  `is_not_trusted`. They are set by [ALTER TABLE](alter-table.md) (`WITH NOCHECK ADD`, `NOCHECK CONSTRAINT`,
  `CHECK CONSTRAINT`, `WITH CHECK CHECK CONSTRAINT`).

## Differences from SQL Server

- A `CHECK`'s `definition` is SQL Server's text (example G) except for a `CAST`, which shows as what lexdb made of it
  (`CAST(a AS varchar(3))` gives `left(bin2str([a],(0),(3)),(3))`, where SQL Server writes a `CONVERT` with the type in
  brackets), and an `N'...'` literal, which loses its `N`.
- Unnamed constraints have PostgreSQL's names (`dept_pkey`, `emp_dept_id_fkey`), not SQL Server's
  `PK__dept__3213E83F...`; `is_system_named` is 1 for them as in SQL Server.
- A default constraint is named `DF_table_column` whatever name `CONSTRAINT name DEFAULT` gave it (here `df_sal` is
  `DF_emp_salary`).

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

### A. Primary and unique keys

<!-- example: tsql -->
```sql
SELECT OBJECT_NAME(k.parent_object_id) AS table_name, k.name, k.type, k.type_desc, k.is_system_named
FROM sys.key_constraints k
ORDER BY table_name, k.name;
```

```text
table_name name          type type_desc              is_system_named
---------- ------------- ---- ---------------------- ---------------
dept       dept_name_key UQ   UNIQUE_CONSTRAINT      1
dept       dept_pkey     PK   PRIMARY_KEY_CONSTRAINT 1
emp        emp_pkey      PK   PRIMARY_KEY_CONSTRAINT 1

(3 rows affected)
```

### B. The columns of each key

<!-- example: tsql -->
```sql
SELECT k.name AS constraint_name, c.name AS column_name, ic.key_ordinal
FROM sys.key_constraints k
JOIN sys.index_columns ic ON ic.object_id = k.parent_object_id AND ic.index_id = k.unique_index_id
JOIN sys.columns c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
ORDER BY k.name, ic.key_ordinal;
```

```text
constraint_name column_name key_ordinal
--------------- ----------- -----------
dept_name_key   name        1
dept_pkey       id          1
emp_pkey        id          1

(3 rows affected)
```

### C. Foreign keys

<!-- example: tsql -->
```sql
SELECT f.name, OBJECT_NAME(f.parent_object_id) AS child, OBJECT_NAME(f.referenced_object_id) AS parent,
       f.delete_referential_action_desc AS on_delete, f.update_referential_action_desc AS on_update,
       f.is_disabled
FROM sys.foreign_keys f;
GO
SELECT OBJECT_NAME(fc.parent_object_id) AS child, pc.name AS child_column,
       OBJECT_NAME(fc.referenced_object_id) AS parent, rc.name AS parent_column
FROM sys.foreign_key_columns fc
JOIN sys.columns pc ON pc.object_id = fc.parent_object_id AND pc.column_id = fc.parent_column_id
JOIN sys.columns rc ON rc.object_id = fc.referenced_object_id AND rc.column_id = fc.referenced_column_id;
```

```text
name             child parent on_delete on_update is_disabled
---------------- ----- ------ --------- --------- -----------
emp_dept_id_fkey emp   dept   NO_ACTION NO_ACTION 0

(1 row affected)

child child_column parent parent_column
----- ------------ ------ -------------
emp   dept_id      dept   id

(1 row affected)
```

### D. Check and default constraints

<!-- example: tsql -->
```sql
SELECT name, OBJECT_NAME(parent_object_id) AS table_name, definition FROM sys.check_constraints;
SELECT d.name, c.name AS column_name, d.definition
FROM sys.default_constraints d
JOIN sys.columns c ON c.object_id = d.parent_object_id AND c.column_id = d.parent_column_id;
```

```text
name   table_name definition
------ ---------- ---------------
ck_sal emp        ([salary]>=(0))

(1 row affected)

name          column_name definition
------------- ----------- ----------
DF_emp_salary salary      ((1000))

(1 row affected)
```

### E. Cascading actions

<!-- example: tsql -->
```sql
CREATE TABLE hr.child (id int PRIMARY KEY, dept_id int REFERENCES hr.dept (id) ON DELETE CASCADE ON UPDATE SET NULL);
SELECT name, delete_referential_action_desc, update_referential_action_desc
FROM sys.foreign_keys WHERE parent_object_id = OBJECT_ID('hr.child');
```

```text
name               delete_referential_action_desc update_referential_action_desc
------------------ ------------------------------ ------------------------------
child_dept_id_fkey CASCADE                        SET_NULL

(1 row affected)
```

### F. Disabled and not trusted constraints

<!-- example: tsql -->
```sql
CREATE TABLE hr.badge (id int PRIMARY KEY, dept_id int, level int);
GO
ALTER TABLE hr.badge WITH NOCHECK ADD CONSTRAINT ck_level CHECK (level > 0);
ALTER TABLE hr.badge ADD CONSTRAINT fk_badge_dept FOREIGN KEY (dept_id) REFERENCES hr.dept (id);
GO
SELECT name, is_disabled, is_not_trusted FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('hr.badge');
SELECT name, is_disabled, is_not_trusted FROM sys.foreign_keys WHERE parent_object_id = OBJECT_ID('hr.badge');
GO
ALTER TABLE hr.badge NOCHECK CONSTRAINT ALL;
GO
SELECT name, is_disabled, is_not_trusted FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('hr.badge');
SELECT name, is_disabled, is_not_trusted FROM sys.foreign_keys WHERE parent_object_id = OBJECT_ID('hr.badge');
GO
ALTER TABLE hr.badge WITH CHECK CHECK CONSTRAINT ALL;
GO
SELECT name, is_disabled, is_not_trusted FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('hr.badge');
SELECT name, is_disabled, is_not_trusted FROM sys.foreign_keys WHERE parent_object_id = OBJECT_ID('hr.badge');
```

```text
name     is_disabled is_not_trusted
-------- ----------- --------------
ck_level 0           1

(1 row affected)

name          is_disabled is_not_trusted
------------- ----------- --------------
fk_badge_dept 0           0

(1 row affected)

name     is_disabled is_not_trusted
-------- ----------- --------------
ck_level 1           1

(1 row affected)

name          is_disabled is_not_trusted
------------- ----------- --------------
fk_badge_dept 1           1

(1 row affected)

name     is_disabled is_not_trusted
-------- ----------- --------------
ck_level 0           0

(1 row affected)

name          is_disabled is_not_trusted
------------- ----------- --------------
fk_badge_dept 0           0

(1 row affected)
```

### G. The text of a CHECK

`definition` is the condition as SQL Server writes it: names in brackets, numbers in parentheses, `BETWEEN` as two
comparisons, `IN` as `OR`s.

<!-- example: tsql -->
```sql
CREATE TABLE hr.grading (
    id int PRIMARY KEY,
    code varchar(10) CONSTRAINT ck_code CHECK (code LIKE 'R%'),
    grade int CONSTRAINT ck_grade CHECK (grade BETWEEN 1 AND 5),
    kind int CONSTRAINT ck_kind CHECK (kind IN (1, 2, 3) OR kind IS NULL),
    price decimal(8,2), qty int,
    CONSTRAINT ck_total CHECK (price * qty < 1000 AND NOT price < 0));
SELECT name, definition FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('hr.grading') ORDER BY name;
```

```text
name     definition
-------- ----------------------------------------------------------
ck_code  ([code] like 'R%')
ck_grade ([grade]>=(1) AND [grade]<=(5))
ck_kind  ([kind]=(3) OR [kind]=(2) OR [kind]=(1) OR [kind] IS NULL)
ck_total ([price]*[qty]<(1000) AND NOT [price]<(0))

(4 rows affected)
```

## See also

[Schemas, tables, columns and indexes](catalog-tables.md), [CREATE TABLE](create-table.md),
[ALTER TABLE](alter-table.md), [INFORMATION_SCHEMA views](catalog-information-schema.md)
