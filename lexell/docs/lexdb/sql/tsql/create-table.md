# CREATE TABLE (Transact-SQL)

Makes a new table: its columns, their types, defaults and computed values, and its constraints.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE TABLE { database_name.schema_name.table_name | schema_name.table_name | table_name | #table_name }
(
    { column_definition | computed_column_definition | table_constraint } [ ,...n ]
)
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
{   PRIMARY KEY
  | UNIQUE
  | [ FOREIGN KEY ] REFERENCES ref_table [ ( ref_column ) ]
        [ ON DELETE { NO ACTION | CASCADE | SET NULL | SET DEFAULT } ]
        [ ON UPDATE { NO ACTION | CASCADE | SET NULL | SET DEFAULT } ]
  | CHECK ( logical_expression )
}

computed_column_definition ::=
column_name AS computed_column_expression [ PERSISTED [ NOT NULL ] ]

table_constraint ::=
[ CONSTRAINT constraint_name ]
{   { PRIMARY KEY | UNIQUE } ( column [ ASC ] [ ,...n ] )
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
  key's columns may hold several NULLs.

`REFERENCES`, `FOREIGN KEY`
: A foreign key: each value must be one of the referenced key's, or NULL (error 547). `ON DELETE` and `ON UPDATE`
  say what happens to the referring rows when the referenced row goes or its key changes.

`CHECK (` *logical_expression* `)`
: A condition each row must not make false (error 547).

*column_name* `AS` *computed_column_expression* [ `PERSISTED` ]
: A computed column, an expression of the row's other columns. It cannot be given a value (error 271). A
  `PERSISTED` column is stored; another is computed when read.

## Remarks

- A temporary table (`#name`) belongs to the session that made it, and is dropped when the session ends or is
  reset. It may be made, filled and read on a replica.
- The names lexdb gives constraints that have none follow PostgreSQL: `emp_pkey`, `emp_name_key` (unique),
  `emp_dept_id_fkey`, `emp_name_check`. A `DEFAULT`'s constraint is named `DF_table_column`.
- `sys.tables`, `sys.columns`, `sys.objects`, `sys.indexes`, `sys.key_constraints` and the other catalog views,
  and `INFORMATION_SCHEMA`, show the new table.
- `CREATE TABLE` is transactional: inside a transaction, `ROLLBACK` removes the table.
- A name already used by a table, view or other object of the schema is error 2714.

## Differences from SQL Server

- **`CLUSTERED` and `NONCLUSTERED`** after `PRIMARY KEY` or `UNIQUE` are error 102. Leave them out: a primary key is
  shown as clustered in `sys.indexes`.
- `ON filegroup` (`ON [PRIMARY]`), `TEXTIMAGE_ON`, `WITH (DATA_COMPRESSION = ...)` and the other table options are
  syntax errors (156, 102).
- A column constraint written `CONSTRAINT name FOREIGN KEY REFERENCES t (c)` is error 102: write
  `CONSTRAINT name REFERENCES t (c)`, or a table constraint.
- `ROWGUIDCOL`, `SPARSE`, `FILESTREAM`, `NOT FOR REPLICATION`, `MASKED WITH`, `ENCRYPTED WITH` and
  `GENERATED ALWAYS AS ROW START` are syntax errors. An index in the table's definition (`INDEX ix (col)`) is error
  102: use [CREATE INDEX](create-index.md). `DESC` in a key's column list is error 156.
- A `rowversion` (`timestamp`) column is not filled in: it stays NULL.
- A `DEFAULT` constraint's own name is not kept; it is shown as `DF_table_column`. `ALTER TABLE ... DROP CONSTRAINT`
  finds it by neither name (error 50000).
- Two `IDENTITY` columns in one table are taken (SQL Server: 2744).
- `##name` makes a temporary table of the session, as `#name` does: other sessions do not see it.
- `sql_variant`, `hierarchyid`, `geography`, `geometry` and CLR types are not available (2715). Alias types
  (`CREATE TYPE name FROM varchar(20)`) are error 156.
- Error 2714's text is lexdb's: `relation "dept" already exists`.

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

### C. ON UPDATE CASCADE and ON DELETE SET NULL

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

### D. Computed columns

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

### E. Table constraints over several columns

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

### F. A temporary table

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

### G. Errors

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
```

```text
Msg 547, Level 16, State 1, Line 1
new row for relation "emp" violates check constraint "emp_name_check"
Msg 547, Level 16, State 1, Line 1
new row for relation "emp" violates check constraint "ck_emp_salary"
Msg 271, Level 16, State 1, Line 1
The column "total" cannot be modified because it is either a computed column or is the result of a UNION operator.
Msg 2714, Level 16, State 1, Line 1
relation "dept" already exists
Msg 2715, Level 16, State 1, Line 1
Column, parameter, or variable #1: Cannot find data type geography.
```

### H. What lexdb does not take

<!-- example: tsql -->
```sql
CREATE TABLE dbo.t1 (id int NOT NULL, CONSTRAINT pk_t1 PRIMARY KEY CLUSTERED (id));
GO
CREATE TABLE dbo.t2 (id int) ON [PRIMARY];
GO
CREATE TABLE dbo.t3 (id int, ref int CONSTRAINT fk_t3 FOREIGN KEY REFERENCES dbo.dept (id));
GO
```

```text
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'clustered'.
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'primary'.
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'foreign'.
```

## See also

[ALTER TABLE](alter-table.md) · [DROP TABLE](drop-table.md) · [CREATE INDEX](create-index.md) ·
[SELECT INTO](select-into.md) · [SET IDENTITY_INSERT](set-identity-insert.md) · [CREATE SEQUENCE](create-sequence.md)
