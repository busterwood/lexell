# Table value constructor (Transact-SQL)

Writes a set of rows in the statement, with `VALUES`: in an `INSERT`, as a derived table in `FROM`, or as the
source of a `MERGE`.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
VALUES ( { DEFAULT | NULL | expression } [ ,...n ] ) [ ,...n ]

-- as a derived table
( VALUES ( expression [ ,...n ] ) [ ,...n ] ) [ AS ] table_alias [ ( column_alias [ ,...n ] ) ]
```

## Arguments

*expression*
: A constant, a variable, an expression, or a scalar subquery. In `CROSS APPLY (VALUES ...)` it may use the columns
  of the sources before it.

`DEFAULT`
: The column's default. Only in an `INSERT`.

*table_alias*, *column_alias*
: The derived table's name and its columns' names.

## Remarks

- Every row has the same number of values.
- The type of each column is that of its values together: a row's value is converted to it, and a value that cannot
  be converted is an error (245).
- In an `INSERT`, SQL Server takes at most 1000 rows; lexdb takes any number.

## Differences from SQL Server

- `VALUES` in `FROM` without column aliases names its columns `column1`, `column2` ...; SQL Server needs them
  (error 8155).
- `VALUES (...)` on its own, as a statement, returns its rows (PostgreSQL's form); SQL Server refuses it.

## Examples

### A. Rows in FROM

<!-- example: tsql -->
```sql
SELECT n, word FROM (VALUES (1, N'one'), (2, N'two'), (3, N'three')) AS v (n, word) WHERE n > 1;
```

```text
n word
- -----
2 two
3 three

(2 rows affected)
```

### B. Rows in INSERT, with DEFAULT

<!-- example: tsql -->
```sql
CREATE TABLE dbo.colour (id int PRIMARY KEY, name nvarchar(20), hex char(7) DEFAULT '#000000');
INSERT INTO dbo.colour VALUES (1, N'red', '#ff0000'), (2, N'black', DEFAULT), (3, N'white', '#ffffff');
SELECT * FROM dbo.colour ORDER BY id;
```

```text
(3 rows affected)

id name  hex
-- ----- -------
1  red   #ff0000
2  black #000000
3  white #ffffff

(3 rows affected)
```

### C. A join to a list of values

A string of `VALUES` has the session's collation, so it compares with a table's column as it would in SQL Server.

<!-- example: tsql -->
```sql
SELECT c.name, v.rank_no
FROM dbo.colour AS c
JOIN (VALUES (N'white', 1), (N'red', 2)) AS v (name, rank_no) ON v.name = c.name
ORDER BY v.rank_no;
```

```text
name  rank_no
----- -------
white 1
red   2

(2 rows affected)
```

### D. Columns into rows with CROSS APPLY

<!-- example: tsql -->
```sql
SELECT c.id, x.part, x.val
FROM dbo.colour AS c
CROSS APPLY (VALUES (N'red', SUBSTRING(c.hex, 2, 2)), (N'green', SUBSTRING(c.hex, 4, 2))) AS x (part, val)
WHERE c.id = 1;
```

```text
id part  val
-- ----- ---
1  red   ff
1  green 00

(2 rows affected)
```

### E. A subquery as a value

<!-- example: tsql -->
```sql
SELECT * FROM (VALUES ((SELECT COUNT(*) FROM dbo.colour), N'colours')) AS v (n, what);
```

```text
n what
- -------
3 colours

(1 row affected)
```

### F. Errors

<!-- example: tsql -->
```sql
SELECT * FROM (VALUES (1), (N'x')) AS v (n);
GO
```

```text
Msg 245, Level 16, State 1, Line 1
Conversion failed when converting the varchar value 'x' to data type int.
```

## See also

[INSERT](insert.md) · [FROM, JOIN and APPLY](from.md) · [MERGE](merge.md)
