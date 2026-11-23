# SELECT - ORDER BY clause (Transact-SQL)

Sorts a query's result, and with `OFFSET` and `FETCH` returns one page of it.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
ORDER BY order_by_expression
    [ COLLATE collation_name ]
    [ ASC | DESC ]
    [ ,...n ]
[ OFFSET offset_row_count { ROW | ROWS }
    [ FETCH { FIRST | NEXT } fetch_row_count { ROW | ROWS } ONLY ] ]
```

## Arguments

*order_by_expression*
: A column, a column alias of the select list, an expression, or the position of a column in the select list
  (`ORDER BY 2`; deprecated in SQL Server, but taken).

`COLLATE` *collation_name*
: Sorts the strings by this collation, for example `Latin1_General_BIN` or `Latin1_General_CS_AS`.

`ASC`, `DESC`
: Up (the default) or down. NULLs sort before every other value going up, and after them going down.

`OFFSET` *offset_row_count* `ROWS`
: Skips this many rows first. A constant, a variable or a parameter.

`FETCH { FIRST | NEXT }` *fetch_row_count* `ROWS ONLY`
: Returns at most this many rows after the offset. `FIRST` and `NEXT`, `ROW` and `ROWS` mean the same.

## Remarks

- Without `ORDER BY`, the order of the rows is not defined, even when it looks stable.
- `ORDER BY` may name columns that are not in the select list, unless the query has `DISTINCT` or is a `UNION`,
  `EXCEPT` or `INTERSECT`, where it may name only the result's columns.
- Strings sort by the column's collation: by default without regard to case.
- With `UNION`, `EXCEPT` or `INTERSECT`, `ORDER BY` comes at the end and sorts the combined result; it names the
  first query's columns.
- For stable pages, sort by a unique key, or the rows that tie may move between pages.

## Differences from SQL Server

- `OFFSET` without `ORDER BY`, and `FETCH` without `OFFSET`, are taken; SQL Server refuses both (error 102 and
  153).
- `TOP` and `OFFSET` in one query are both applied; SQL Server refuses them together (10741).
- `FETCH NEXT 0 ROWS` returns no rows; SQL Server refuses a count of 0 (10744). A negative `OFFSET` is 50000
  with lexdb's text (SQL Server: 10742).
- An `ORDER BY` with `DISTINCT` on a column not in the select list is 50000 with lexdb's text (SQL Server: 145).

## Examples

<!--setup: tsql
CREATE TABLE dbo.sale (id int PRIMARY KEY, region nvarchar(10), yr int, amount int);
INSERT dbo.sale VALUES (1, N'north', 2024, 10), (2, N'north', 2025, 20), (3, N'south', 2024, 5), (4, N'South', 2025, 7), (5, NULL, 2025, 3);
-->

The examples use one table:

```sql
CREATE TABLE dbo.sale (id int PRIMARY KEY, region nvarchar(10), yr int, amount int);
INSERT dbo.sale VALUES (1, N'north', 2024, 10), (2, N'north', 2025, 20), (3, N'south', 2024, 5),
  (4, N'South', 2025, 7), (5, NULL, 2025, 3);
```

### A. Several columns, up and down

<!-- example: tsql -->
```sql
SELECT region, yr, amount FROM dbo.sale ORDER BY region, amount DESC;
```

```text
region yr   amount
------ ---- ------
NULL   2025 3
north  2025 20
north  2024 10
South  2025 7
south  2024 5

(5 rows affected)
```

### B. An alias, a position and an expression

<!-- example: tsql -->
```sql
SELECT region, amount * 2 AS doubled FROM dbo.sale ORDER BY doubled DESC;
SELECT region, amount FROM dbo.sale ORDER BY 2;
SELECT region, amount FROM dbo.sale ORDER BY CASE WHEN region IS NULL THEN 1 ELSE 0 END, amount;
```

```text
region doubled
------ -------
north  40
north  20
South  14
south  10
NULL   6

(5 rows affected)

region amount
------ ------
NULL   3
south  5
South  7
north  10
north  20

(5 rows affected)

region amount
------ ------
south  5
South  7
north  10
north  20
NULL   3

(5 rows affected)
```

### C. COLLATE

The default collation ignores case; a binary collation puts upper case first.

<!-- example: tsql -->
```sql
SELECT id, region FROM dbo.sale WHERE region IS NOT NULL ORDER BY region, id;
SELECT id, region FROM dbo.sale WHERE region IS NOT NULL ORDER BY region COLLATE Latin1_General_BIN, id;
```

```text
id region
-- ------
1  north
2  north
3  south
4  South

(4 rows affected)

id region
-- ------
4  South
1  north
2  north
3  south

(4 rows affected)
```

### D. A page of rows

<!-- example: tsql -->
```sql
SELECT id, amount FROM dbo.sale ORDER BY id OFFSET 1 ROWS FETCH NEXT 2 ROWS ONLY;
SELECT id, amount FROM dbo.sale ORDER BY id OFFSET 3 ROWS;
```

```text
id amount
-- ------
2  20
3  5

(2 rows affected)

id amount
-- ------
4  7
5  3

(2 rows affected)
```

### E. Paging with variables

<!-- example: tsql -->
```sql
DECLARE @page int = 2, @size int = 2;
SELECT id, amount FROM dbo.sale ORDER BY id
OFFSET (@page - 1) * @size ROWS FETCH NEXT @size ROWS ONLY;
```

```text
id amount
-- ------
3  5
4  7

(2 rows affected)
```

### F. Errors

<!-- example: tsql -->
```sql
SELECT DISTINCT region FROM dbo.sale ORDER BY amount;
SELECT id FROM dbo.sale ORDER BY id OFFSET -1 ROWS;
```

```text
Msg 50000, Level 16, State 1, Line 1
for SELECT DISTINCT, ORDER BY expressions must appear in select list
Msg 50000, Level 16, State 1, Line 2
OFFSET must not be negative
```

## See also

[SELECT](select.md) · [TOP](top.md) · [Set operators](set-operators.md) · [OVER](over.md)
