# INSERT (Transact-SQL)

Adds one or more rows to a table or a table variable.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
[ WITH common_table_expression [ ,...n ] ]
INSERT [ INTO ] { table_name | @table_variable | #temp_table }
    [ ( column_list ) ]
    [ OUTPUT { INSERTED.column_name | INSERTED.* | expression } [ [ AS ] column_alias ] [ ,...n ]
        [ INTO { @table_variable | table_name } [ ( column_list ) ] ] ]
    { VALUES ( { DEFAULT | NULL | expression } [ ,...n ] ) [ ,...n ]
    | select_statement
    | EXECUTE procedure_name [ argument [ ,...n ] ]
    | DEFAULT VALUES }
[ ; ]

table_name ::= [ database_name . [ schema_name ] . | schema_name . ] table_name
```

## Arguments

*common_table_expression*
: A named query the `SELECT` can read. See [WITH](with.md).

`INTO`
: Optional, as in SQL Server.

*table_name*
: The target table: `t`, `dbo.t`, `lexdb.dbo.t`, or `[my table]`. The database part, when given, must be `lexdb`
  (or `master`). The default schema is `dbo`.

*@table_variable*
: A table variable declared in the batch (`DECLARE @t TABLE (...)`).

*#temp_table*
: A local temporary table of the session.

*column_list*
: The columns the values go to, in order. A column left out gets its `DEFAULT`, the next identity value, or NULL.

`OUTPUT`
: Returns the inserted rows, through `INSERTED`, as a result set; or with `INTO`, puts them into a table or table
  variable. `DELETED` is not available in an `INSERT`.

`VALUES`
: One or more rows (up to 1000 in SQL Server; lexdb has no limit). `DEFAULT` gives a column its default.

*select_statement*
: A query whose rows are inserted.

`EXECUTE` *procedure_name*
: Inserts the rows of the procedure's result set (INSERT ... EXEC).

`DEFAULT VALUES`
: One row, every column its default.

## Remarks

- Values are converted to the column's type as SQL Server converts them on assignment: a string too long for
  `varchar(n)` is error 2628 ("String or binary data would be truncated"), a decimal is rounded to the column's
  scale.
- An `IDENTITY` column cannot be given a value unless `SET IDENTITY_INSERT table ON` is in effect (error 544).
  `SCOPE_IDENTITY()` and `@@IDENTITY` give the last identity value made.
- `@@ROWCOUNT` is the number of rows inserted. With `SET NOCOUNT ON` the client gets no `(n rows affected)`
  message.
- Constraint errors are SQL Server's numbers: 2627 (primary key or unique constraint), 515 (NULL into a column that
  does not allow it), 547 (CHECK or FOREIGN KEY). The statement is undone and the batch goes on with the next
  statement, as in SQL Server, unless `SET XACT_ABORT ON` or a `TRY ... CATCH` says otherwise.
- String comparisons, and so unique keys on string columns, follow the column's collation: under the default
  (case-insensitive) collation `'Bob'` and `'bob'` are the same key.
- On a replica, `INSERT` into a table gives error 3906 ("Failed to update database "lexdb" because the database is
  read-only."); `#temp` tables and table variables can be used there.
- Many rows load faster by bulk copy (bcp, `SqlBulkCopy`, `INSERT BULK`): see [bulk loading](../../bulk-load.md).

## Differences from SQL Server

- `INSERT TOP (n)` and table hints (`WITH (TABLOCK)`) are not taken: see the examples.
- The text of many error messages is lexdb's (PostgreSQL's wording), with SQL Server's number and severity.
- The line number in an error message is that of the batch's first line.
- There are no triggers, so `INSERT` fires none.
- `VALUES` takes any number of rows (SQL Server stops at 1000, error 10738).

## Examples

<!--setup: tsql
CREATE TABLE dbo.product (id int IDENTITY(1,1) PRIMARY KEY, name nvarchar(40) NOT NULL, price decimal(10,2) DEFAULT 0 CHECK (price >= 0), stock int DEFAULT 0);
-->

### A. Insert one row, and several rows

<!-- example: tsql -->
```sql
INSERT INTO dbo.product (name, price, stock) VALUES (N'pencil', 0.50, 100);
INSERT dbo.product (name, price) VALUES (N'eraser', 0.75), (N'ruler', 1.20);
SELECT id, name, price, stock FROM dbo.product ORDER BY id;
```

```text
(1 row affected)

(2 rows affected)

id name   price stock
-- ------ ----- -----
1  pencil 0.50  100
2  eraser 0.75  0
3  ruler  1.20  0

(3 rows affected)
```

### B. Defaults and DEFAULT VALUES

<!-- example: tsql -->
```sql
CREATE TABLE dbo.note (id int IDENTITY PRIMARY KEY, body nvarchar(100) DEFAULT N'empty', made date DEFAULT '2026-01-01');
INSERT INTO dbo.note (body, made) VALUES (N'first', DEFAULT);
INSERT INTO dbo.note DEFAULT VALUES;
SELECT * FROM dbo.note;
```

```text
(1 row affected)

(1 row affected)

id body  made
-- ----- ----------
1  first 2026-01-01
2  empty 2026-01-01

(2 rows affected)
```

### C. Insert the rows of a query

<!-- example: tsql -->
```sql
CREATE TABLE dbo.cheap (id int PRIMARY KEY, name nvarchar(40));
INSERT INTO dbo.cheap (id, name)
SELECT id, UPPER(name) FROM dbo.product WHERE price < 1;
SELECT * FROM dbo.cheap ORDER BY id;
```

```text
(2 rows affected)

id name
-- ------
1  PENCIL
2  ERASER

(2 rows affected)
```

### D. OUTPUT and SCOPE_IDENTITY

<!-- example: tsql -->
```sql
INSERT INTO dbo.product (name, price)
OUTPUT INSERTED.id, INSERTED.name, INSERTED.price * 1.2 AS with_tax
VALUES (N'stapler', 6.40);
SELECT SCOPE_IDENTITY() AS last_id, @@ROWCOUNT AS rows_before;
```

```text
id name    with_tax
-- ------- --------
4  stapler 7.680

(1 row affected)

last_id rows_before
------- -----------
4       1

(1 row affected)
```

### E. OUTPUT INTO a table variable

<!-- example: tsql -->
```sql
DECLARE @made TABLE (id int, name nvarchar(40));
INSERT INTO dbo.product (name, price)
OUTPUT INSERTED.id, INSERTED.name INTO @made
VALUES (N'glue', 2.10), (N'tape', 1.10);
SELECT * FROM @made ORDER BY id;
```

```text
(2 rows affected)

id name
-- ----
5  glue
6  tape

(2 rows affected)
```

### F. Into a temporary table, and INSERT ... EXEC

<!-- example: tsql -->
```sql
CREATE PROCEDURE dbo.low_stock AS SELECT id, name FROM dbo.product WHERE stock < 10;
GO
CREATE TABLE #low (id int, name nvarchar(40));
INSERT INTO #low EXEC dbo.low_stock;
SELECT * FROM #low ORDER BY id;
```

```text
(5 rows affected)

id name
-- -------
2  eraser
3  ruler
4  stapler
5  glue
6  tape

(5 rows affected)
```

### G. IDENTITY_INSERT

<!-- example: tsql -->
```sql
INSERT INTO dbo.product (id, name) VALUES (100, N'special');
SET IDENTITY_INSERT dbo.product ON;
INSERT INTO dbo.product (id, name) VALUES (100, N'special');
SET IDENTITY_INSERT dbo.product OFF;
INSERT INTO dbo.product (name) VALUES (N'next');
SELECT id, name FROM dbo.product WHERE id >= 100 ORDER BY id;
```

```text
Msg 544, Level 16, State 1, Line 1
cannot insert a non-DEFAULT value into column "id"
(1 row affected)

(1 row affected)

id  name
--- -------
100 special
101 next

(2 rows affected)
```

### H. Errors

Each failed statement is undone and the batch goes on.

<!-- example: tsql -->
```sql
INSERT INTO dbo.product (name, price) VALUES (N'clip', -1);
INSERT INTO dbo.product (name) VALUES (NULL);
INSERT INTO dbo.cheap (id, name) VALUES (1, N'again');
INSERT INTO dbo.cheap (id, name) VALUES (9, N'a name that is far too long for forty characters, surely');
PRINT 'the batch went on';
```

```text
Msg 547, Level 16, State 1, Line 1
new row for relation "product" violates check constraint "product_price_check"
Msg 515, Level 16, State 1, Line 1
null value in column "name" of relation "product" violates not-null constraint
Msg 2627, Level 14, State 1, Line 1
duplicate key value violates unique constraint "cheap_pkey"
Msg 2628, Level 16, State 1, Line 1
value too long for type character varying(40)
the batch went on
```

### I. What lexdb does not take

<!-- example: tsql -->
```sql
INSERT TOP (1) INTO dbo.cheap (id, name) SELECT id, name FROM dbo.product;
GO
INSERT INTO dbo.cheap WITH (TABLOCK) (id, name) VALUES (20, N'x');
GO
```

```text
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near '1'.
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'with'.
```

## See also

[UPDATE](update.md) · [DELETE](delete.md) · [MERGE](merge.md) · [SELECT](select.md) · [OUTPUT clause](output.md) ·
[SET IDENTITY_INSERT](set-identity-insert.md) · [Bulk copy](../../bulk-load.md#sql-server-bulk-copy)
