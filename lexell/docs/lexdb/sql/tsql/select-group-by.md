# SELECT - GROUP BY (Transact-SQL)

Divides a query's rows into groups, one result row per group, for aggregate functions. `HAVING` filters the
groups.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
GROUP BY {
      column_expression [ ,...n ]
    | ROLLUP ( group_by_expression [ ,...n ] )
    | CUBE ( group_by_expression [ ,...n ] )
    | GROUPING SETS ( grouping_set [ ,...n ] )
    | ()
} [ ,...n ]

GROUP BY ALL column_expression [ ,...n ]

[ HAVING search_condition ]

grouping_set ::= { () | group_by_expression | ( group_by_expression [ ,...n ] ) }
```

## Arguments

*column_expression*
: A column, or an expression of columns (`YEAR(hired)`). Each select list item that is not in an aggregate must be
  one of the grouping expressions. A column alias of the select list cannot be used here.

`ROLLUP (a, b, ...)`
: The groups by `(a, b, ...)`, then subtotals by each shorter prefix `(a)`, and a grand total `()`.

`CUBE (a, b, ...)`
: The groups by every combination of the expressions, the grand total included.

`GROUPING SETS (...)`
: The groups by each listed set; `()` is the grand total. The other forms are short for grouping sets.

`ALL`
: Also returns the groups whose rows the `WHERE` clause removed, with NULL aggregates (deprecated in SQL Server).

`HAVING` *search_condition*
: Keeps the groups for which the condition is true. It may use aggregates.

## Remarks

- NULLs in a grouping column make one group.
- In a subtotal row a column that is not grouped is NULL. `GROUPING (column)` gives 1 there, and 0 where the NULL is
  a real value.
- Without `GROUP BY`, a query with an aggregate returns one row, even from no rows: `COUNT(*)` is 0 and `SUM` is
  NULL.
- Aggregates may take `DISTINCT` (`COUNT(DISTINCT yr)`). `STRING_AGG` takes `WITHIN GROUP (ORDER BY ...)`.
- The order of the groups is not defined without `ORDER BY`.

## Differences from SQL Server

- The old forms `GROUP BY ... WITH ROLLUP` and `WITH CUBE` are error 102: write `ROLLUP (...)` and `CUBE (...)`.
- `GROUPING_ID` is not available (error 195).
- `STDEV`, `STDEVP`, `VAR` and `VARP` are not available (error 195).
- A column that is neither grouped nor in an aggregate is error 50000 with lexdb's text (SQL Server: 8120).

## Examples

<!--setup: tsql
CREATE TABLE dbo.sale (region nvarchar(10), yr int, amount int);
INSERT dbo.sale VALUES (N'north', 2024, 10), (N'north', 2025, 20), (N'south', 2024, 5), (N'south', 2025, 7), (N'south', 2025, 3);
-->

The examples use one table:

```sql
CREATE TABLE dbo.sale (region nvarchar(10), yr int, amount int);
INSERT dbo.sale VALUES (N'north', 2024, 10), (N'north', 2025, 20), (N'south', 2024, 5), (N'south', 2025, 7),
  (N'south', 2025, 3);
```

### A. Groups and aggregates

<!-- example: tsql -->
```sql
SELECT region, COUNT(*) AS sales, SUM(amount) AS total, MIN(amount) AS least, MAX(amount) AS most
FROM dbo.sale
GROUP BY region
ORDER BY region;
```

```text
region sales total least most
------ ----- ----- ----- ----
north  2     30    10    20
south  3     15    3     7

(2 rows affected)
```

### B. HAVING

<!-- example: tsql -->
```sql
SELECT region, yr, SUM(amount) AS total
FROM dbo.sale
GROUP BY region, yr
HAVING SUM(amount) >= 10
ORDER BY region, yr;
```

```text
region yr   total
------ ---- -----
north  2024 10
north  2025 20
south  2025 10

(3 rows affected)
```

### C. DISTINCT in an aggregate, and STRING_AGG

<!-- example: tsql -->
```sql
SELECT region, COUNT(DISTINCT yr) AS years,
       STRING_AGG(CAST(amount AS nvarchar(10)), N'+') WITHIN GROUP (ORDER BY amount) AS parts
FROM dbo.sale
GROUP BY region
ORDER BY region;
```

```text
region years parts
------ ----- -----
north  2     10+20
south  2     3+5+7

(2 rows affected)
```

### D. ROLLUP, with GROUPING

<!-- example: tsql -->
```sql
SELECT CASE WHEN GROUPING(region) = 1 THEN N'all' ELSE region END AS region,
       SUM(amount) AS total
FROM dbo.sale
GROUP BY ROLLUP (region)
ORDER BY GROUPING(region), region;
```

```text
region total
------ -----
north  30
south  15
all    45

(3 rows affected)
```

### E. CUBE

<!-- example: tsql -->
```sql
SELECT region, yr, SUM(amount) AS total
FROM dbo.sale
GROUP BY CUBE (region, yr)
ORDER BY region, yr;
```

```text
region yr   total
------ ---- -----
NULL   NULL 45
NULL   2024 15
NULL   2025 30
north  NULL 30
north  2024 10
north  2025 20
south  NULL 15
south  2024 5
south  2025 10

(9 rows affected)
```

### F. GROUPING SETS

<!-- example: tsql -->
```sql
SELECT region, yr, SUM(amount) AS total
FROM dbo.sale
GROUP BY GROUPING SETS ((region), (yr), ())
ORDER BY GROUPING(region), GROUPING(yr), region, yr;
```

```text
region yr   total
------ ---- -----
north  NULL 30
south  NULL 15
NULL   2024 15
NULL   2025 30
NULL   NULL 45

(5 rows affected)
```

### G. GROUP BY ALL

The `WHERE` clause keeps only the north's rows; `ALL` still returns the south's group.

<!-- example: tsql -->
```sql
SELECT region, SUM(amount) AS total FROM dbo.sale WHERE region = N'north' GROUP BY ALL region ORDER BY region;
```

```text
region total
------ -----
north  30
south  NULL

(2 rows affected)
```

### H. An aggregate over no rows

<!-- example: tsql -->
```sql
SELECT COUNT(*) AS n, SUM(amount) AS total FROM dbo.sale WHERE yr = 1999;
```

```text
n total
- -----
0 NULL

(1 row affected)
```

### I. Errors

<!-- example: tsql -->
```sql
SELECT region, amount FROM dbo.sale GROUP BY region;
GO
SELECT region, SUM(amount) AS total FROM dbo.sale GROUP BY region WITH ROLLUP;
GO
SELECT region, GROUPING_ID(region) AS g FROM dbo.sale GROUP BY ROLLUP (region);
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
column "sale.amount" must appear in the GROUP BY clause or be used in an aggregate function
Msg 102, Level 15, State 1, Line 1
Incorrect syntax near ';'.
Msg 195, Level 15, State 1, Line 1
'grouping_id' is not a recognized built-in function name.
```

## See also

[SELECT](select.md) · [OVER](over.md) · [ORDER BY](order-by.md)
