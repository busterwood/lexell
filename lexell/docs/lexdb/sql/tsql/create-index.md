# CREATE INDEX (Transact-SQL)

Makes an index on a table: unique or not, on columns or computed columns, with included columns and a filter.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE [ UNIQUE ] [ CLUSTERED | NONCLUSTERED ] INDEX index_name
    ON { schema_name.table_name | table_name | #table_name } ( column [ ASC | DESC ] [ ,...n ] )
    [ INCLUDE ( column_name [ ,...n ] ) ]
    [ WHERE filter_predicate ]
    [ WITH ( index_option [ ,...n ] ) ]
    [ ON filegroup_name ]
[ ; ]
```

## Arguments

`UNIQUE`
: No two rows may have the same key (error 2627 when a row would break it). The rows already in the table are
  checked when the index is made. NULLs do not clash with each other.

`CLUSTERED`, `NONCLUSTERED`
: Which index is the table's clustered one. A table has at most one clustered index: a second is error 1902. See
  Remarks.

*index_name*
: The index's name. It must not be used by another index, table or view of the schema (error 2714).

*column* [ `ASC` | `DESC` ]
: The key's columns, in order, each sorted up or down. A computed column may be one.

`INCLUDE (` *column_name* `)`
: Columns kept in the index besides its key. They are not part of the key, and are not checked for `UNIQUE`.

`WHERE` *filter_predicate*
: A filtered index: only the rows for which the condition is true are in it. A unique filtered index checks only
  those rows.

## Remarks

- `sys.indexes` and `sys.index_columns` show the index; a filtered index's condition is in
  `sys.indexes.filter_definition`.
- `CREATE INDEX` is transactional.
- To rename an index, use [sp_rename](sp-rename.md) with `'INDEX'`.
- **`CLUSTERED` and `NONCLUSTERED` are labels.** lexdb keeps a table's rows in the order of its primary key whatever
  is said, so the words change what the catalog shows and nothing else. `sys.indexes` shows the clustered index as
  `CLUSTERED` with `index_id` 1, every other as `NONCLUSTERED`, and a table with no clustered index as a heap (a row
  with `index_id` 0, `type_desc` `HEAP` and no name; `OBJECTPROPERTY(..., 'TableHasClustIndex')` is 0).
- A primary key is the clustered index unless `NONCLUSTERED` is said for it or another index is clustered. A
  `CREATE CLUSTERED INDEX` on a table that has a primary key is error 1902 until the primary key is made
  `NONCLUSTERED`; dropping the clustered index (or its constraint) leaves a heap.
- `WITH (...)` index options (`FILLFACTOR`, `ONLINE`, `DATA_COMPRESSION` ...) and `ON filegroup` are read and not
  kept.

## Differences from SQL Server

- `ALTER INDEX ... REBUILD`, `REORGANIZE` and `DISABLE` are error 50000 ("lexdb: ALTER INDEX takes RENAME TO only").
  `CREATE STATISTICS` is error 50000; `UPDATE STATISTICS` is error 102.
- A unique index over rows that already clash is error 2627, "could not create unique index" (SQL Server: 1505).
- **Index names are per table**, as in SQL Server: `ix_emp_dept` may be the name of an index of each of two tables
  (example E), and the same name twice on one table is error 1913. The PostgreSQL and Oracle doors keep index names
  per schema: they list the second `ix` under a longer name (`ix`, a control character and the table's name), and a
  `CREATE INDEX ix` there is refused while the schema has one. A name that a table or another object has in the schema is still
  error 2714.
- Columnstore indexes (`CREATE COLUMNSTORE INDEX`, error 102), and spatial, XML and full-text indexes, are not
  supported.
- PostgreSQL's `CREATE INDEX IF NOT EXISTS` is taken.

## Examples

<!--setup: tsql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30) NOT NULL, email varchar(60), dept_id int, salary decimal(10,2), band AS (CASE WHEN salary > 5000 THEN 'high' ELSE 'low' END));
INSERT dbo.emp (id, name, email, dept_id, salary) VALUES (1, N'Ann', 'ann@example.com', 1, 5200), (2, N'Bob', NULL, 1, 4100), (3, N'Cid', NULL, 2, 6100);
-->

The examples use one table:

```sql
CREATE TABLE dbo.emp (id int PRIMARY KEY, name nvarchar(30) NOT NULL, email varchar(60), dept_id int,
                      salary decimal(10,2), band AS (CASE WHEN salary > 5000 THEN 'high' ELSE 'low' END));
INSERT dbo.emp (id, name, email, dept_id, salary) VALUES (1, N'Ann', 'ann@example.com', 1, 5200),
  (2, N'Bob', NULL, 1, 4100), (3, N'Cid', NULL, 2, 6100);
```

### A. An index on two columns

<!-- example: tsql -->
```sql
CREATE INDEX ix_emp_dept ON dbo.emp (dept_id, salary DESC);
SELECT name, type_desc, is_unique FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.emp') ORDER BY name;
```

```text
name        type_desc    is_unique
----------- ------------ ---------
emp_pkey    CLUSTERED    1
ix_emp_dept NONCLUSTERED 0

(2 rows affected)
```

### B. A unique index, with included columns

NULLs do not clash.

<!-- example: tsql -->
```sql
CREATE UNIQUE INDEX ux_emp_email ON dbo.emp (email) INCLUDE (name);
INSERT dbo.emp (id, name, email) VALUES (4, N'Dee', NULL);
INSERT dbo.emp (id, name, email) VALUES (5, N'Eve', 'ann@example.com');
```

```text
(1 row affected)

Msg 2601, Level 14, State 1, Line 3
Cannot insert duplicate key row in object 'dbo.emp' with unique index 'ux_emp_email'. The duplicate key value is (ann@example.com).
```

### C. A filtered unique index

Only the rows the filter keeps must be unique.

<!-- example: tsql -->
```sql
CREATE UNIQUE INDEX ux_emp_name_high ON dbo.emp (name) WHERE salary > 5000;
INSERT dbo.emp (id, name, salary) VALUES (6, N'Bob', 3000);
INSERT dbo.emp (id, name, salary) VALUES (7, N'Ann', 9000);
SELECT name, has_filter, filter_definition FROM sys.indexes WHERE name = 'ux_emp_name_high';
```

```text
(1 row affected)

Msg 2601, Level 14, State 1, Line 3
Cannot insert duplicate key row in object 'dbo.emp' with unique index 'ux_emp_name_high'. The duplicate key value is (Ann).
name             has_filter filter_definition
---------------- ---------- -------------------
ux_emp_name_high 1          (([salary]>(5000)))

(1 row affected)
```

### D. An index on a computed column, and its columns

<!-- example: tsql -->
```sql
CREATE INDEX ix_emp_band ON dbo.emp (band);
SELECT i.name, c.name AS col, ic.key_ordinal, ic.is_descending_key, ic.is_included_column
FROM sys.index_columns AS ic
JOIN sys.indexes AS i ON i.object_id = ic.object_id AND i.index_id = ic.index_id
JOIN sys.columns AS c ON c.object_id = ic.object_id AND c.column_id = ic.column_id
WHERE ic.object_id = OBJECT_ID('dbo.emp') AND i.name IN ('ix_emp_dept', 'ux_emp_email', 'ix_emp_band')
ORDER BY i.name, ic.is_included_column, ic.key_ordinal;
```

```text
name         col     key_ordinal is_descending_key is_included_column
------------ ------- ----------- ----------------- ------------------
ix_emp_band  band    1           0                 0
ix_emp_dept  dept_id 1           0                 0
ix_emp_dept  salary  2           1                 0
ux_emp_email email   1           0                 0

(4 rows affected)
```

### E. Errors, and one name on two tables

The same name on the same table is error 1913. On another table it is a second index: `sys.indexes` lists both.

<!-- example: tsql -->
```sql
CREATE UNIQUE INDEX ux_emp_dept ON dbo.emp (dept_id);
CREATE INDEX ix_emp_dept ON dbo.emp (name);
GO
CREATE INDEX ix_emp_x ON dbo.emp (nothere);
GO
CREATE TABLE dbo.dept_copy (id int);
CREATE INDEX ix_emp_dept ON dbo.dept_copy (id);
GO
SELECT OBJECT_NAME(object_id) AS tbl, name FROM sys.indexes WHERE name = 'ix_emp_dept' ORDER BY 1;
GO
```

```text
Msg 2627, Level 14, State 1, Line 1
could not create unique index "ux_emp_dept"
Msg 1913, Level 16, State 1, Line 2
The operation failed because an index or statistics with name 'ix_emp_dept' already exists on table 'emp'.
Msg 1911, Level 16, State 1, Line 1
Column name 'nothere' does not exist in the target table or view.
tbl       name
--------- -----------
dept_copy ix_emp_dept
emp       ix_emp_dept

(2 rows affected)
```

### F. CLUSTERED and NONCLUSTERED

The primary key `emp_pkey` is the table's clustered index, so a second clustered index is refused. A table made with its
key `NONCLUSTERED` can have a clustered index of another column, and a heap shows as index 0.

<!-- example: tsql -->
```sql
CREATE NONCLUSTERED INDEX ix_emp_name ON dbo.emp (name) WITH (FILLFACTOR = 90) ON [PRIMARY];
GO
CREATE CLUSTERED INDEX cx_emp_dept ON dbo.emp (dept_id);
GO
CREATE TABLE dbo.log_entry (id int NOT NULL, at datetime2 NOT NULL, msg nvarchar(200),
    CONSTRAINT pk_log PRIMARY KEY NONCLUSTERED (id));
CREATE UNIQUE CLUSTERED INDEX cx_log_at ON dbo.log_entry (at DESC, id);
GO
SELECT OBJECT_NAME(object_id) AS tbl, index_id, name, type_desc FROM sys.indexes
WHERE object_id IN (OBJECT_ID('dbo.emp'), OBJECT_ID('dbo.log_entry')) ORDER BY object_id, index_id;
GO
DROP INDEX cx_log_at ON dbo.log_entry;
GO
SELECT index_id, name, type_desc FROM sys.indexes WHERE object_id = OBJECT_ID('dbo.log_entry') ORDER BY index_id;
GO
```

```text
Msg 1902, Level 16, State 1, Line 1
Cannot create more than one clustered index on table 'emp'. Drop the existing clustered index 'emp_pkey' before creating another.
tbl       index_id name             type_desc
--------- -------- ---------------- ------------
emp       1        emp_pkey         CLUSTERED
emp       2        ix_emp_dept      NONCLUSTERED
emp       3        ux_emp_email     NONCLUSTERED
emp       4        ux_emp_name_high NONCLUSTERED
emp       5        ix_emp_band      NONCLUSTERED
emp       6        ix_emp_name      NONCLUSTERED
log_entry 1        cx_log_at        CLUSTERED
log_entry 2        pk_log           NONCLUSTERED

(8 rows affected)

index_id name   type_desc
-------- ------ ------------
0        NULL   HEAP
2        pk_log NONCLUSTERED

(2 rows affected)
```

### G. What lexdb does not take

<!-- example: tsql -->
```sql
CREATE COLUMNSTORE INDEX cs_emp ON dbo.emp (salary);
GO
ALTER INDEX ix_emp_dept ON dbo.emp REBUILD;
GO
```

```text
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'COLUMNSTORE'.
Msg 50000, Level 16, State 1, Line 1
lexdb: ALTER INDEX takes RENAME TO only
```

## See also

[DROP INDEX](drop-index.md) · [CREATE TABLE](create-table.md) · [sp_rename](sp-rename.md)
