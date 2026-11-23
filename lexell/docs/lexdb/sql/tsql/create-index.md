# CREATE INDEX (Transact-SQL)

Makes an index on a table: unique or not, on columns or computed columns, with included columns and a filter.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CREATE [ UNIQUE ] INDEX index_name
    ON { schema_name.table_name | table_name | #table_name } ( column [ ASC | DESC ] [ ,...n ] )
    [ INCLUDE ( column_name [ ,...n ] ) ]
    [ WHERE filter_predicate ]
[ ; ]
```

## Arguments

`UNIQUE`
: No two rows may have the same key (error 2627 when a row would break it). The rows already in the table are
  checked when the index is made. NULLs do not clash with each other.

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

## Differences from SQL Server

- **`CLUSTERED` and `NONCLUSTERED`** are error 102. Every index lexdb makes is shown as `NONCLUSTERED`; a primary
  key is shown as `CLUSTERED`.
- `WITH (...)` index options (`ONLINE`, `FILLFACTOR`, `DATA_COMPRESSION`, `DROP_EXISTING` ...) are error 102, and
  `ON filegroup` is error 156.
- `ALTER INDEX ... REBUILD`, `REORGANIZE` and `DISABLE` are error 50000 ("lexdb: ALTER INDEX takes RENAME TO only").
  `CREATE STATISTICS` is error 50000; `UPDATE STATISTICS` is error 102.
- A unique index over rows that already clash is error 2627, "could not create unique index" (SQL Server: 1505).
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

Msg 2627, Level 14, State 1, Line 1
duplicate key value violates unique constraint "ux_emp_email"
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

Msg 2627, Level 14, State 1, Line 1
duplicate key value violates unique constraint "ux_emp_name_high"
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

### E. Errors

<!-- example: tsql -->
```sql
CREATE UNIQUE INDEX ux_emp_dept ON dbo.emp (dept_id);
CREATE INDEX ix_emp_dept ON dbo.emp (name);
GO
CREATE INDEX ix_emp_x ON dbo.emp (nothere);
GO
```

```text
Msg 2627, Level 14, State 1, Line 1
could not create unique index "ux_emp_dept"
Msg 2714, Level 16, State 1, Line 1
relation "ix_emp_dept" already exists
Msg 207, Level 16, State 1, Line 1
Invalid column name 'nothere'.
```

### F. What lexdb does not take

<!-- example: tsql -->
```sql
CREATE NONCLUSTERED INDEX ix_emp_name ON dbo.emp (name);
GO
CREATE INDEX ix_emp_name ON dbo.emp (name) WITH (FILLFACTOR = 90);
GO
ALTER INDEX ix_emp_dept ON dbo.emp REBUILD;
GO
```

```text
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near 'nonclustered'.
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near '('.
Msg 50000, Level 16, State 1, Line 1
lexdb: ALTER INDEX takes RENAME TO only
```

## See also

[DROP INDEX](drop-index.md) · [CREATE TABLE](create-table.md) · [sp_rename](sp-rename.md)
