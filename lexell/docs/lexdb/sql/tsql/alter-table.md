# ALTER TABLE (Transact-SQL)

Changes a table's definition: adds, changes and drops columns and constraints.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
ALTER TABLE { database_name.schema_name.table_name | schema_name.table_name | table_name }
{
    ADD column_definition
  | ADD computed_column_definition
  | [ WITH { CHECK | NOCHECK } ] ADD [ CONSTRAINT constraint_name ] table_constraint
  | ALTER COLUMN column_name new_data_type [ COLLATE collation_name ] [ NULL | NOT NULL ]
  | DROP COLUMN [ IF EXISTS ] column_name
  | DROP CONSTRAINT [ IF EXISTS ] constraint_name
  | [ WITH { CHECK | NOCHECK } ] { CHECK | NOCHECK } CONSTRAINT { ALL | constraint_name [ ,...n ] }
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
  table that has a primary key refuses a second one (error 1779; `CREATE TABLE` gives 8110).

`ALTER COLUMN` *column_name* *new_data_type*
: Changes the column's type, and with `NULL` or `NOT NULL` whether it may hold NULL. The rows are converted; a value
  that does not convert is an error and nothing changes. A column that a foreign key, index or constraint depends
  on cannot change its type (error 5074).

`WITH CHECK`, `WITH NOCHECK` before `ADD`
: For a `CHECK` or `FOREIGN KEY`: whether the rows that are there are checked against it. `WITH CHECK` is the default
  and is as `ADD` alone. `WITH NOCHECK` adds the constraint without looking at the rows: it is enforced for rows
  inserted or changed from then on, and is marked not trusted (`is_not_trusted` is 1 in `sys.check_constraints` or
  `sys.foreign_keys`).

`NOCHECK CONSTRAINT`
: Disables a `CHECK` or `FOREIGN KEY` constraint: rows are no longer checked against it, and a disabled foreign key
  does not cascade `ON DELETE` or `ON UPDATE`. It names one constraint, several separated by commas, or `ALL`, which
  takes every `CHECK` and `FOREIGN KEY` constraint of the table and leaves the keys alone. The constraint shows
  `is_disabled` 1 and `is_not_trusted` 1.

`CHECK CONSTRAINT`
: Enables a constraint (or `ALL`). `ALTER TABLE t CHECK CONSTRAINT c` does not look at the rows: the constraint
  checks new rows again and stays not trusted. `ALTER TABLE t WITH CHECK CHECK CONSTRAINT c` checks every row first,
  and fails with error 547 if one breaks the constraint, leaving it disabled; when all rows pass, the constraint is
  enabled and trusted (`is_not_trusted` 0). `WITH NOCHECK CHECK CONSTRAINT` is the same as `CHECK CONSTRAINT`.
  A name that is not a constraint of the table is error 4917; the name of a key or default is error 11415.

`DROP COLUMN`
: Removes a column. `IF EXISTS` makes a missing column no error. A column that a `CHECK` constraint reads
  (alone or with other columns) cannot be dropped: error 5074 names the constraint, and the constraint and the column
  stay (example J). Drop the constraint first.

`DROP CONSTRAINT`
: Removes a constraint by its name (see `sys.objects` or `sys.key_constraints`). `IF EXISTS` makes a missing one no
  error.

## Remarks

- To rename a table, a column or an index, use [sp_rename](sp-rename.md).
- `ALTER TABLE` is transactional: inside a transaction, `ROLLBACK` undoes it.
- An unknown table is error 4902; an unknown column is 207.

## Differences from SQL Server

- **`DROP COLUMN` is refused while a view reads the table** (error 50000: `lexdb keeps a view's text`), whatever the
  column. SQL Server drops it. Drop the view, change the table, and make the view again.
- One action per statement: several columns or constraints in one `ADD`, or `DROP COLUMN a, b`, give error 50000
  ("lexdb: ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA").
- **`ADD CONSTRAINT name DEFAULT value FOR column`** is error 102. Give the default when the column is made.
- `SET (LOCK_ESCALATION = ...)`, `SWITCH`, `REBUILD`, and `ENABLE` and `DISABLE TRIGGER` give the same error 50000.
- Disabling and enabling takes `CHECK` and `FOREIGN KEY` constraints only, as in SQL Server (error 11415 for a key).
- The error 547 of `ADD` and of `WITH CHECK CHECK CONSTRAINT` says `The INSERT statement conflicted with ...` (a
  foreign key under `ADD`: PostgreSQL's `insert or update on table ... violates foreign key constraint`); SQL Server
  says `The ALTER TABLE statement conflicted with ...`.
- Adding a `NOT NULL` column without a default to a table with rows is error 515 with lexdb's text (SQL Server:
  4901). A column that already exists is 50000 (SQL Server: 2705); dropping an unknown column is 207 (SQL Server:
  4924).
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
Msg 1779, Level 16, State 1, Line 1
Table 'emp' already has a primary key defined on it.
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

### H. Constraint states: NOCHECK and CHECK

<!-- example: tsql -->
```sql
CREATE TABLE dbo.part (id int PRIMARY KEY, name varchar(20));
CREATE TABLE dbo.bin (id int PRIMARY KEY, part_id int, qty int);
INSERT dbo.part VALUES (1, 'bolt');
INSERT dbo.bin VALUES (1, 1, 10), (2, 9, -5);
GO
ALTER TABLE dbo.bin ADD CONSTRAINT ck_qty CHECK (qty >= 0);
GO
ALTER TABLE dbo.bin WITH NOCHECK ADD CONSTRAINT ck_qty CHECK (qty >= 0);
ALTER TABLE dbo.bin WITH NOCHECK ADD CONSTRAINT fk_part FOREIGN KEY (part_id) REFERENCES dbo.part (id);
GO
SELECT name, is_disabled, is_not_trusted FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('dbo.bin');
SELECT name, is_disabled, is_not_trusted FROM sys.foreign_keys WHERE parent_object_id = OBJECT_ID('dbo.bin');
GO
```

```text
(1 row affected)

(2 rows affected)

Msg 547, Level 16, State 1, Line 1
The INSERT statement conflicted with the CHECK constraint "ck_qty". The conflict occurred in database "lexdb", table "dbo.bin".
name   is_disabled is_not_trusted
------ ----------- --------------
ck_qty 0           1

(1 row affected)

name    is_disabled is_not_trusted
------- ----------- --------------
fk_part 0           1

(1 row affected)
```

The first `ADD` failed because row 2 breaks the check; `WITH NOCHECK` added both constraints without looking. They
are enforced for new rows. Row 2 still breaks the check, but an `UPDATE` tests only the constraints that read a column
it sets, as SQL Server does: setting `part_id` does not test `ck_qty`, and setting `qty` does. It is so in an explicit
transaction, in `MERGE` and with `OUTPUT ... INTO` too:

<!-- example: tsql -->
```sql
INSERT dbo.bin VALUES (3, 1, -1);
GO
INSERT dbo.bin VALUES (3, 7, 1);
GO
INSERT dbo.bin VALUES (3, 1, 1);
GO
UPDATE dbo.bin SET part_id = 1 WHERE id = 2;
GO
UPDATE dbo.bin SET qty = -5 WHERE id = 2;
GO
BEGIN TRANSACTION;
UPDATE dbo.bin SET part_id = 1 WHERE id = 2;
ROLLBACK;
GO
MERGE dbo.bin AS t USING (SELECT 2 AS id) AS s ON t.id = s.id WHEN MATCHED THEN UPDATE SET part_id = 1;
GO
DECLARE @moved TABLE (id int);
UPDATE dbo.bin SET part_id = 1 OUTPUT inserted.id INTO @moved WHERE id = 2;
SELECT id FROM @moved;
GO
```

```text
Msg 547, Level 16, State 1, Line 1
The INSERT statement conflicted with the CHECK constraint "ck_qty". The conflict occurred in database "lexdb", table "dbo.bin", column 'qty'.
Msg 547, Level 16, State 1, Line 1
The INSERT statement conflicted with the FOREIGN KEY constraint "fk_part". The conflict occurred in database "lexdb", table "dbo.part", column 'id'.
(1 row affected)

(1 row affected)

Msg 547, Level 16, State 1, Line 1
The UPDATE statement conflicted with the CHECK constraint "ck_qty". The conflict occurred in database "lexdb", table "dbo.bin", column 'qty'.
(1 row affected)

(1 row affected)

(1 row affected)

id
--
2

(1 row affected)
```

`WITH CHECK CHECK CONSTRAINT` checks the rows and makes a constraint trusted, once they pass:

<!-- example: tsql -->
```sql
ALTER TABLE dbo.bin WITH CHECK CHECK CONSTRAINT ck_qty;
GO
UPDATE dbo.bin SET qty = 0 WHERE id = 2;
ALTER TABLE dbo.bin WITH CHECK CHECK CONSTRAINT ck_qty;
GO
SELECT name, is_disabled, is_not_trusted FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('dbo.bin');
GO
```

```text
Msg 547, Level 16, State 1, Line 1
The INSERT statement conflicted with the CHECK constraint "ck_qty". The conflict occurred in database "lexdb", table "dbo.bin", column 'qty'.
(1 row affected)

name   is_disabled is_not_trusted
------ ----------- --------------
ck_qty 0           0

(1 row affected)
```

`NOCHECK CONSTRAINT` turns a constraint off, one by name or all of them. `CHECK CONSTRAINT` turns it on again, but does
not trust it until the rows have been checked:

<!-- example: tsql -->
```sql
ALTER TABLE dbo.bin NOCHECK CONSTRAINT ALL;
INSERT dbo.bin VALUES (4, 55, -9);
GO
SELECT name, is_disabled, is_not_trusted FROM sys.foreign_keys WHERE parent_object_id = OBJECT_ID('dbo.bin');
GO
ALTER TABLE dbo.bin CHECK CONSTRAINT ALL;
GO
SELECT name, is_disabled, is_not_trusted FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('dbo.bin');
SELECT name, is_disabled, is_not_trusted FROM sys.foreign_keys WHERE parent_object_id = OBJECT_ID('dbo.bin');
GO
ALTER TABLE dbo.bin WITH CHECK CHECK CONSTRAINT fk_part;
GO
```

```text
(1 row affected)

name    is_disabled is_not_trusted
------- ----------- --------------
fk_part 1           1

(1 row affected)

name   is_disabled is_not_trusted
------ ----------- --------------
ck_qty 0           1

(1 row affected)

name    is_disabled is_not_trusted
------- ----------- --------------
fk_part 0           1

(1 row affected)

Msg 547, Level 16, State 1, Line 1
The INSERT statement conflicted with the FOREIGN KEY constraint "fk_part". The conflict occurred in database "lexdb", table "dbo.part", column 'id'.
```

A disabled foreign key does not refuse the parent's deletion:

<!-- example: tsql -->
```sql
DELETE dbo.part WHERE id = 1;
GO
ALTER TABLE dbo.bin NOCHECK CONSTRAINT fk_part;
DELETE dbo.part WHERE id = 1;
SELECT id, part_id FROM dbo.bin ORDER BY id;
GO
```

```text
Msg 547, Level 16, State 1, Line 1
The DELETE statement conflicted with the REFERENCE constraint "fk_part". The conflict occurred in database "lexdb", table "dbo.bin", column 'part_id'.
(1 row affected)

id part_id
-- -------
1  1
2  1
3  1
4  55

(4 rows affected)
```

Errors:

<!-- example: tsql -->
```sql
ALTER TABLE dbo.bin CHECK CONSTRAINT nosuch;
GO
ALTER TABLE dbo.bin NOCHECK CONSTRAINT bin_pkey;
GO
ALTER TABLE dbo.nothere NOCHECK CONSTRAINT ALL;
GO
```

```text
Msg 4917, Level 16, State 1, Line 1
Constraint 'nosuch' does not exist.
Msg 11415, Level 16, State 1, Line 1
Object 'bin_pkey' cannot be disabled or enabled. This action applies only to foreign key and check constraints.
Msg 4902, Level 16, State 1, Line 1
Cannot find the object "nothere" because it does not exist or you do not have permissions.
```

### I. What lexdb does not take

<!-- example: tsql -->
```sql
ALTER TABLE dbo.emp ADD CONSTRAINT df_emp_salary DEFAULT 0 FOR salary;
GO
ALTER TABLE dbo.emp ADD a int NULL, b int NULL;
GO
ALTER TABLE dbo.emp REBUILD;
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

### J. A column that a CHECK reads cannot be dropped

<!-- example: tsql -->
```sql
CREATE TABLE dbo.stock (id int PRIMARY KEY, lo int, hi int, CONSTRAINT ck_range CHECK (lo <= hi));
GO
ALTER TABLE dbo.stock DROP COLUMN hi;
GO
SELECT name FROM sys.check_constraints WHERE parent_object_id = OBJECT_ID('dbo.stock');
GO
ALTER TABLE dbo.stock DROP CONSTRAINT ck_range;
ALTER TABLE dbo.stock DROP COLUMN hi;
GO
```

```text
Msg 5074, Level 16, State 1, Line 1
The object 'ck_range' is dependent on column 'hi'.
name
--------
ck_range

(1 row affected)
```

## See also

[CREATE TABLE](create-table.md) · [DROP TABLE](drop-table.md) · [sp_rename](sp-rename.md) ·
[CREATE INDEX](create-index.md)
