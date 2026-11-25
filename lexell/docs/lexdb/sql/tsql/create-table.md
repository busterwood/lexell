# CREATE TABLE (Transact-SQL)

Makes a new table: its columns, their types, defaults and computed values, and its constraints.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE TABLE { database_name.schema_name.table_name | schema_name.table_name | table_name | #table_name }
(
    { column_definition | computed_column_definition | table_constraint } [ ,...n ]
)
[ ON filegroup ] [ TEXTIMAGE_ON filegroup ] [ WITH ( table_option [ ,...n ] ) ]
[ ; ]

column_definition ::=
column_name data_type
    [ COLLATE collation_name ]
    [ NULL | NOT NULL ]
    [ [ CONSTRAINT constraint_name ] DEFAULT constant_expression ]
    [ IDENTITY [ ( seed, increment ) ] ]
    [ column_constraint [ ...n ] ]

column_constraint ::=
[ CONSTRAINT constraint_name ]
{   { PRIMARY KEY | UNIQUE } [ CLUSTERED | NONCLUSTERED ]
  | [ FOREIGN KEY ] REFERENCES ref_table [ ( ref_column ) ]
        [ ON DELETE { NO ACTION | CASCADE | SET NULL | SET DEFAULT } ]
        [ ON UPDATE { NO ACTION | CASCADE | SET NULL | SET DEFAULT } ]
  | CHECK ( logical_expression )
}

computed_column_definition ::=
column_name AS computed_column_expression [ PERSISTED [ NOT NULL ] ]

table_constraint ::=
[ CONSTRAINT constraint_name ]
{   { PRIMARY KEY | UNIQUE } [ CLUSTERED | NONCLUSTERED ] ( column [ ASC | DESC ] [ ,...n ] )
        [ WITH ( index_option [ ,...n ] ) ] [ ON filegroup ]
  | FOREIGN KEY ( column [ ,...n ] ) REFERENCES ref_table [ ( ref_column [ ,...n ] ) ]
        [ ON DELETE ... ] [ ON UPDATE ... ]
  | CHECK ( logical_expression )
}
```

## Arguments

*table_name*
: The new table's name, with its schema (`dbo` by default) and the database (`lexdb`) if wanted. A name that
  starts with `#` makes a temporary table (see Remarks).

*data_type*
: A SQL Server type: `int`, `bigint`, `smallint`, `tinyint`, `bit`, `decimal(p, s)`, `numeric(p, s)`, `money`,
  `smallmoney`, `float(n)`, `real`, `char(n)`, `varchar(n | max)`, `nchar(n)`, `nvarchar(n | max)`, `text`,
  `ntext`, `sysname`, `binary(n)`, `varbinary(n | max)`, `image`, `rowversion`, `date`, `time(p)`, `datetime`,
  `smalldatetime`, `datetime2(p)`, `datetimeoffset(p)`, `uniqueidentifier`, `xml`, or a table type's name. An
  unknown type is error 2715.

`COLLATE` *collation_name*
: The column's collation, for its comparisons and sorts. The default is the database's, `SQL_Latin1_General_CP1_CI_AS`
  (case-insensitive).

`NULL`, `NOT NULL`
: Whether the column may hold NULL. The default is `NULL`, except for a primary key's columns.

`DEFAULT` *constant_expression*
: The value an `INSERT` gives the column when it gives none: a constant, or a function such as `GETDATE()`,
  `NEWID()`, `SYSTEM_USER` or `NEXT VALUE FOR` a sequence.

`IDENTITY [ (` *seed*`,` *increment* `) ]`
: The table numbers its rows in this column, from *seed* by *increment*; `IDENTITY` alone is `IDENTITY(1, 1)`.
  See [SET IDENTITY_INSERT](set-identity-insert.md).

`PRIMARY KEY`, `UNIQUE`
: A key: no two rows may have the same values (error 2627). A primary key's columns are `NOT NULL`. A unique
  key's columns may hold several NULLs. A table has one primary key: a second is error 8110.

`CLUSTERED`, `NONCLUSTERED`
: After `PRIMARY KEY` or `UNIQUE`: which key is the table's clustered index (see Remarks). `ASC` and `DESC` after a
  key column are read.

`REFERENCES`, `FOREIGN KEY`
: A foreign key: each value must be one of the referenced key's, or NULL (error 547). `ON DELETE` and `ON UPDATE`
  say what happens to the referring rows when the referenced row goes or its key changes.

`CHECK (` *logical_expression* `)`
: A condition each row must not make false (error 547).

*column_name* `AS` *computed_column_expression* [ `PERSISTED` ]
: A computed column, an expression of the row's other columns. It cannot be given a value (error 271). A
  `PERSISTED` column is stored; another is computed when read.

## Remarks

- A foreign key's action (`ON DELETE CASCADE`, `SET NULL`, `SET DEFAULT`, `ON UPDATE CASCADE`) writes the child table, and an
  [assertion](create-assertion.md) on the child is checked after it: error 547 undoes the whole statement.
- A temporary table (`#name`) belongs to the session that made it, and is dropped when the session ends or is
  reset. It may be made, filled and read on a replica.
- **`CLUSTERED` and `NONCLUSTERED` are labels.** lexdb keeps rows in the order of the primary key whatever is said.
  `sys.indexes` shows the clustered index as `CLUSTERED` (a primary key is, unless `NONCLUSTERED` is said for it or
  another key says `CLUSTERED`) and a table with none as a heap (`index_id` 0). Two `CLUSTERED` keys in one `CREATE
  TABLE` are error 8112; a second clustered index by `CREATE INDEX` is error 1902. See [CREATE INDEX](create-index.md).
- `ON filegroup`, `TEXTIMAGE_ON`, `WITH (...)` options on a key or the table (`FILLFACTOR`, `DATA_COMPRESSION` ...)
  are read and not kept.
- The names lexdb gives constraints that have none follow PostgreSQL: `emp_pkey`, `emp_name_key` (unique),
  `emp_dept_id_fkey`, `emp_name_check`. A `DEFAULT`'s constraint is named `DF_table_column`. SQL Server makes
  names such as `PK__emp__3213E83F...`: name the constraints that a script will refer to.
- `sys.tables`, `sys.columns`, `sys.objects`, `sys.indexes`, `sys.key_constraints` and the other catalog views,
  and `INFORMATION_SCHEMA`, show the new table.
- `CREATE TABLE` is transactional: inside a transaction, `ROLLBACK` removes the table.
- A name already used by a table, view or other object of the schema is error 2714.
- A `CHECK` or `FOREIGN KEY` is enforced from the moment the table is made. To add one without checking the rows
  that are there, or to switch one off and on, see [ALTER TABLE](alter-table.md) (`WITH NOCHECK`, `NOCHECK
  CONSTRAINT`).

## Differences from SQL Server

- A table named `HOLDLOCK` or `INDEX` (bare) is error 156; SQL Server reads it as a table hint and gives 1018. Every
  other reserved word as a bare table or column name is 156 in both. Bracket the name (`[plan]`) to use one.
- A column constraint written `CONSTRAINT name FOREIGN KEY REFERENCES t (c)` is error 102: write
  `CONSTRAINT name REFERENCES t (c)`, or a table constraint.
- `ROWGUIDCOL`, `SPARSE`, `FILESTREAM`, `NOT FOR REPLICATION`, `MASKED WITH`, `ENCRYPTED WITH` and
  `GENERATED ALWAYS AS ROW START` are syntax errors. SQL Server accepts an index in the table's definition (`INDEX ix
  (col)`); lexdb refuses it with error 156 (example I): use [CREATE INDEX](create-index.md).
- A `rowversion` (`timestamp`) column is not filled in: it stays NULL.
- A `DEFAULT` constraint's own name is not kept; it is shown as `DF_table_column`. `ALTER TABLE ... DROP CONSTRAINT`
  finds it by neither name (error 50000).
- Two `IDENTITY` columns in one table are taken (SQL Server: 2744).
- `##name` makes a temporary table of the session, as `#name` does: other sessions do not see it.
- `sql_variant`, `hierarchyid`, `geography`, `geometry` and CLR types are not available (2715). Alias types
  (`CREATE TYPE name FROM varchar(20)`) are error 156.

## Examples

### A. Keys, an identity, defaults and checks

<!-- example: tsql -->
```sql
CREATE TABLE dbo.dept (
    id   int NOT NULL CONSTRAINT pk_dept PRIMARY KEY,
    code char(3) NOT NULL CONSTRAINT uq_dept_code UNIQUE,
    name nvarchar(40) NOT NULL
);
CREATE TABLE dbo.emp (
    id      int IDENTITY(100, 1) PRIMARY KEY,
    name    nvarchar(40) NOT NULL CHECK (LEN(name) > 1),
    dept_id int NULL CONSTRAINT fk_emp_dept REFERENCES dbo.dept (id) ON DELETE SET NULL ON UPDATE CASCADE,
    salary  decimal(10, 2) NOT NULL DEFAULT 0 CONSTRAINT ck_emp_salary CHECK (salary >= 0),
    hired   date DEFAULT '2026-01-01',
    note    nvarchar(max) COLLATE Latin1_General_CS_AS NULL
);
INSERT dbo.dept VALUES (1, 'SAL', N'Sales'), (2, 'RES', N'Research');
INSERT dbo.emp (name, dept_id, salary) VALUES (N'Ann', 1, 6000), (N'Bob', 2, 4100);
SELECT * FROM dbo.emp;
```

```text
(2 rows affected)

(2 rows affected)

id  name dept_id salary  hired      note
--- ---- ------- ------- ---------- ----
100 Ann  1       6000.00 2026-01-01 NULL
101 Bob  2       4100.00 2026-01-01 NULL

(2 rows affected)
```

### B. What was made

<!-- example: tsql -->
```sql
SELECT name, type_desc FROM sys.objects WHERE parent_object_id = OBJECT_ID('dbo.emp') ORDER BY type_desc, name;
SELECT name, type_desc, is_unique, is_primary_key FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.dept') ORDER BY name;
```

```text
name           type_desc
-------------- ----------------------
ck_emp_salary  CHECK_CONSTRAINT
emp_name_check CHECK_CONSTRAINT
DF_emp_hired   DEFAULT_CONSTRAINT
DF_emp_salary  DEFAULT_CONSTRAINT
fk_emp_dept    FOREIGN_KEY_CONSTRAINT
emp_pkey       PRIMARY_KEY_CONSTRAINT

(6 rows affected)

name         type_desc    is_unique is_primary_key
------------ ------------ --------- --------------
pk_dept      CLUSTERED    1         1
uq_dept_code NONCLUSTERED 1         0

(2 rows affected)
```

### C. CLUSTERED, NONCLUSTERED and the storage clauses

These are read and shown in `sys.indexes`; the rows stay in primary-key order.

<!-- example: tsql -->
```sql
CREATE TABLE dbo.audit (
    id    bigint NOT NULL,
    at    datetime2 NOT NULL,
    what  nvarchar(100),
    CONSTRAINT pk_audit PRIMARY KEY NONCLUSTERED (id DESC) WITH (FILLFACTOR = 80),
    CONSTRAINT uq_audit_at UNIQUE CLUSTERED (at)
) ON [PRIMARY] TEXTIMAGE_ON [PRIMARY];
CREATE TABLE dbo.scratch (a int, b int);
SELECT OBJECT_NAME(object_id) AS tbl, index_id, name, type_desc, is_primary_key
FROM sys.indexes WHERE object_id IN (OBJECT_ID('dbo.audit'), OBJECT_ID('dbo.scratch')) ORDER BY object_id, index_id;
```

```text
tbl     index_id name        type_desc    is_primary_key
------- -------- ----------- ------------ --------------
audit   1        uq_audit_at CLUSTERED    0
audit   2        pk_audit    NONCLUSTERED 1
scratch 0        NULL        HEAP         0

(3 rows affected)
```

### D. ON UPDATE CASCADE and ON DELETE SET NULL

<!-- example: tsql -->
```sql
UPDATE dbo.dept SET id = 20 WHERE id = 2;
DELETE FROM dbo.dept WHERE id = 1;
SELECT name, dept_id FROM dbo.emp ORDER BY id;
```

```text
(1 row affected)

(1 row affected)

name dept_id
---- -------
Ann  NULL
Bob  20

(2 rows affected)
```

### E. Computed columns

<!-- example: tsql -->
```sql
CREATE TABLE dbo.line (
    qty   int NOT NULL,
    price decimal(10, 2) NOT NULL,
    total AS (qty * price) PERSISTED,
    band  AS (CASE WHEN qty >= 10 THEN 'bulk' ELSE 'single' END)
);
INSERT dbo.line (qty, price) VALUES (2, 1.50), (12, 0.90);
SELECT * FROM dbo.line;
```

```text
(2 rows affected)

qty price total band
--- ----- ----- ------
2   1.50  3.00  single
12  0.90  10.80 bulk

(2 rows affected)
```

### F. Table constraints over several columns

<!-- example: tsql -->
```sql
CREATE TABLE dbo.course (code char(4) NOT NULL, term smallint NOT NULL, title nvarchar(60),
    CONSTRAINT pk_course PRIMARY KEY (code, term));
CREATE TABLE dbo.enrolment (student int NOT NULL, code char(4) NOT NULL, term smallint NOT NULL,
    CONSTRAINT pk_enrolment PRIMARY KEY (student, code, term),
    CONSTRAINT fk_enrolment_course FOREIGN KEY (code, term) REFERENCES dbo.course (code, term),
    CONSTRAINT ck_term CHECK (term BETWEEN 1 AND 3));
SELECT name, type_desc FROM sys.objects WHERE parent_object_id = OBJECT_ID('dbo.enrolment') ORDER BY name;
```

```text
name                type_desc
------------------- ----------------------
ck_term             CHECK_CONSTRAINT
fk_enrolment_course FOREIGN_KEY_CONSTRAINT
pk_enrolment        PRIMARY_KEY_CONSTRAINT

(3 rows affected)
```

### G. A temporary table

<!-- example: tsql -->
```sql
CREATE TABLE #work (id int PRIMARY KEY, label nvarchar(20) DEFAULT N'none');
INSERT #work (id) VALUES (1);
SELECT * FROM #work;
SELECT CASE WHEN OBJECT_ID('tempdb..#work') IS NULL THEN 'no' ELSE 'yes' END AS found;
```

```text
(1 row affected)

id label
-- -----
1  none

(1 row affected)

found
-----
yes

(1 row affected)
```

### H. Errors

<!-- example: tsql -->
```sql
INSERT dbo.emp (name, salary) VALUES (N'X', 10);
INSERT dbo.emp (name, salary) VALUES (N'Cid', -5);
INSERT dbo.line (qty, price, total) VALUES (1, 1, 1);
GO
CREATE TABLE dbo.dept (x int);
GO
CREATE TABLE dbo.place (spot geography);
GO
CREATE TABLE dbo.twokeys (a int PRIMARY KEY, b int PRIMARY KEY);
GO
CREATE TABLE dbo.twoclustered (a int, b int, CONSTRAINT uq_a UNIQUE CLUSTERED (a), CONSTRAINT uq_b UNIQUE CLUSTERED (b));
GO
CREATE CLUSTERED INDEX cx_dept ON dbo.dept (name);
GO
```

```text
Msg 547, Level 16, State 1, Line 1
The INSERT statement conflicted with the CHECK constraint "emp_name_check". The conflict occurred in database "lexdb", table "dbo.emp", column 'name'.
Msg 547, Level 16, State 1, Line 2
The INSERT statement conflicted with the CHECK constraint "ck_emp_salary". The conflict occurred in database "lexdb", table "dbo.emp", column 'salary'.
Msg 271, Level 16, State 1, Line 3
The column "total" cannot be modified because it is either a computed column or is the result of a UNION operator.
Msg 2714, Level 16, State 1, Line 1
There is already an object named 'dept' in the database.
Msg 2715, Level 16, State 1, Line 1
Column, parameter, or variable #1: Cannot find data type geography.
Msg 8110, Level 16, State 1, Line 1
Cannot add multiple PRIMARY KEY constraints to table 'twokeys'.
Msg 8112, Level 16, State 1, Line 1
Cannot add more than one clustered index for constraints on table 'twoclustered'.
Msg 1902, Level 16, State 1, Line 1
Cannot create more than one clustered index on table 'dept'. Drop the existing clustered index 'pk_dept' before creating another.
```

### I. What lexdb does not take

<!-- example: tsql -->
```sql
CREATE TABLE dbo.t1 (id int, INDEX ix_t1 (id));
GO
CREATE TABLE dbo.t3 (id int, ref int CONSTRAINT fk_t3 FOREIGN KEY REFERENCES dbo.dept (id));
GO
```

```text
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'INDEX'.
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'FOREIGN'.
```

## See also

[ALTER TABLE](alter-table.md) · [DROP TABLE](drop-table.md) · [CREATE INDEX](create-index.md) ·
[SELECT INTO](select-into.md) · [SET IDENTITY_INSERT](set-identity-insert.md) · [CREATE SEQUENCE](create-sequence.md)
