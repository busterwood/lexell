# Aggregate functions (Transact-SQL)

Functions that combine the rows of a group into one value.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
COUNT ( { * | [ ALL | DISTINCT ] expression } )
COUNT_BIG ( { * | [ ALL | DISTINCT ] expression } )
SUM ( [ ALL | DISTINCT ] expression )
AVG ( [ ALL | DISTINCT ] expression )
MIN ( expression )
MAX ( expression )
STRING_AGG ( expression, separator ) [ WITHIN GROUP ( ORDER BY order_expression [ ASC | DESC ] [, ...] ) ]
PRODUCT ( expression )
APPROX_PERCENTILE_CONT ( numeric_literal ) WITHIN GROUP ( ORDER BY expression [ ASC | DESC ] )
APPROX_PERCENTILE_DISC ( numeric_literal ) WITHIN GROUP ( ORDER BY expression [ ASC | DESC ] )
APPROX_COUNT_DISTINCT ( expression )
APPROX_COUNT_DISTINCT_DETAIL ( expression )
APPROX_COUNT_DISTINCT_AGG ( detail )
TO_APPROX_COUNT_DISTINCT ( detail )
APPROX_PERCENTILE ( expression, fraction )
APPROX_PERCENTILE ( fraction ) WITHIN GROUP ( ORDER BY expression [ ASC | DESC ] )
APPROX_PERCENTILE_DETAIL ( expression )
APPROX_PERCENTILE_AGG ( detail )
TO_APPROX_PERCENTILE ( detail, fraction )
```

`PERCENTILE_CONT` and `PERCENTILE_DISC` are on the [window functions](functions-window.md) page, because SQL Server
takes them only with `OVER`.

## Functions

`COUNT`
: The number of rows, or with an expression the number of rows where it is not NULL. `COUNT(DISTINCT x)` counts
  the different non-NULL values. The result is an `int`.

`COUNT_BIG`
: The same, as a `bigint`.

`SUM`
: The total of the non-NULL values; NULL when there are none. An `int` total is returned as a `bigint`. `DISTINCT`
  adds each value once.

`AVG`
: The mean of the non-NULL values. An integer column gives an integer mean (`AVG` of 1, 2 and 4 is 2); a
  `decimal` column gives a decimal with at least six places; a `float` gives a `float`.

`MIN`, `MAX`
: The least and the greatest value, NULLs left out. They take numbers, strings (under the collation), dates and
  `bit`; strings compare without regard to case.

`STRING_AGG`
: The non-NULL values as text, joined by *separator*. `WITHIN GROUP (ORDER BY ...)` orders them. NULL when there
  are no values.

`PRODUCT`
: The product of the values (SQL Server 2025).

`APPROX_PERCENTILE_CONT`, `APPROX_PERCENTILE_DISC`
: The value at the given fraction (0 to 1) of the ordered values, interpolated or taken from the data
  (SQL Server 2022).

`APPROX_COUNT_DISTINCT`, `APPROX_COUNT_DISTINCT_DETAIL`, `APPROX_COUNT_DISTINCT_AGG`, `TO_APPROX_COUNT_DISTINCT`
: Approximate count of distinct non-NULL values (SQL Server 2019 `APPROX_COUNT_DISTINCT`, plus composable binary sketch
  variants `_DETAIL`, `_AGG`, and `TO_APPROX_COUNT_DISTINCT` backed by HyperLogLog++). Returns `bigint` (0 over no rows).

`APPROX_PERCENTILE`, `APPROX_PERCENTILE_DETAIL`, `APPROX_PERCENTILE_AGG`, `TO_APPROX_PERCENTILE`
: Composable approximate quantile backed by a Dunning merging t-digest, supporting both `APPROX_PERCENTILE(expr, p)` and
  `APPROX_PERCENTILE(p) WITHIN GROUP (ORDER BY expr [ASC | DESC])`, plus mergeable binary digests (`_DETAIL`, `_AGG`)
  and `TO_APPROX_PERCENTILE(detail, p)`.

## Remarks

- Without `GROUP BY` an aggregate gives one row over the whole table, even when the table is empty (`COUNT` is 0,
  the others NULL). With `GROUP BY` there is a row per group.
- A column in the select list that is neither grouped nor aggregated is an error (50000, `must appear in the GROUP BY
  clause`).
- `HAVING` filters groups after aggregation; `WHERE` filters rows before it.
- Aggregates with `OVER` are windows: see [OVER](over.md).

## Differences from SQL Server

- `STDEV`, `STDEVP`, `VAR`, `VARP` and `CHECKSUM_AGG` do not exist (error 195, example H); `GROUPING_ID` is error 195
  too.
- `SUM` of `int` values does not overflow at 2147483647: the total is a `bigint` (SQL Server: error 8115).
- `COUNT_BIG(*)` with `OVER` is error 195.

## Examples

<!--setup: tsql
CREATE TABLE dbo.sale (id int PRIMARY KEY, region varchar(10), product varchar(10), qty int, price decimal(8,2));
INSERT INTO dbo.sale VALUES (1, 'north', 'pen', 10, 1.50), (2, 'north', 'ink', 2, 4.25), (3, 'south', 'pen', 5, 1.50),
                            (4, 'south', 'pen', 7, 1.60), (5, 'south', NULL, NULL, 2.00), (6, 'east', 'ink', 1, 4.00);
-->

The examples use one table:

```sql
CREATE TABLE dbo.sale (id int PRIMARY KEY, region varchar(10), product varchar(10), qty int, price decimal(8,2));
INSERT INTO dbo.sale VALUES (1, 'north', 'pen', 10, 1.50), (2, 'north', 'ink', 2, 4.25), (3, 'south', 'pen', 5, 1.50),
                            (4, 'south', 'pen', 7, 1.60), (5, 'south', NULL, NULL, 2.00), (6, 'east', 'ink', 1, 4.00);
```

### A. COUNT

<!-- example: tsql -->
```sql
SELECT COUNT(*) AS rows_, COUNT(qty) AS with_qty, COUNT(DISTINCT product) AS products, COUNT_BIG(*) AS big
FROM dbo.sale;
SELECT COUNT(*) AS rows_, SUM(qty) AS total FROM dbo.sale WHERE id > 100;
```

```text
rows_ with_qty products big
----- -------- -------- ---
6     5        2        6

(1 row affected)

rows_ total
----- -----
0     NULL

(1 row affected)
```

### B. SUM and AVG

<!-- example: tsql -->
```sql
SELECT SUM(qty) AS total_qty, AVG(qty) AS avg_qty, SUM(DISTINCT qty) AS sum_distinct,
       SUM(qty * price) AS revenue, AVG(price) AS avg_price, AVG(CAST(qty AS float)) AS avg_float
FROM dbo.sale;
```

```text
total_qty avg_qty sum_distinct revenue avg_price avg_float
--------- ------- ------------ ------- --------- ---------
25        5       25           46.20   2.475000  5.0

(1 row affected)
```

### C. MIN and MAX

<!-- example: tsql -->
```sql
SELECT MIN(qty) AS min_qty, MAX(qty) AS max_qty, MIN(product) AS first_product, MAX(product) AS last_product,
       MIN(price) AS cheapest, MAX(price) AS dearest
FROM dbo.sale;
```

```text
min_qty max_qty first_product last_product cheapest dearest
------- ------- ------------- ------------ -------- -------
1       10      ink           pen          1.50     4.25

(1 row affected)
```

### D. GROUP BY and HAVING

<!-- example: tsql -->
```sql
SELECT region, COUNT(*) AS sales, SUM(qty) AS units, MAX(price) AS top_price
FROM dbo.sale GROUP BY region HAVING COUNT(*) > 1 ORDER BY region;
GO
SELECT region, qty FROM dbo.sale GROUP BY region;
```

```text
region sales units top_price
------ ----- ----- ---------
north  2     12    4.25
south  3     12    2.00

(2 rows affected)

Msg 50000, Level 16, State 1, Line 1
column "sale.qty" must appear in the GROUP BY clause or be used in an aggregate function
```

### E. STRING_AGG

<!-- example: tsql -->
```sql
SELECT region, STRING_AGG(product, ', ') WITHIN GROUP (ORDER BY product) AS products
FROM dbo.sale GROUP BY region ORDER BY region;
SELECT STRING_AGG(CAST(id AS varchar(5)), '-') WITHIN GROUP (ORDER BY id DESC) AS ids FROM dbo.sale;
SELECT STRING_AGG(product, ',') AS none FROM dbo.sale WHERE id > 100;
```

```text
region products
------ --------
east   ink
north  ink, pen
south  pen, pen

(3 rows affected)

ids
-----------
6-5-4-3-2-1

(1 row affected)

none
----
NULL

(1 row affected)
```

### F. PRODUCT

<!-- example: tsql -->
```sql
SELECT PRODUCT(qty) AS product_of_qty FROM dbo.sale WHERE qty IS NOT NULL;
```

```text
product_of_qty
--------------
700

(1 row affected)
```

### G. Percentiles

<!-- example: tsql -->
```sql
SELECT APPROX_PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY qty) AS median_cont,
       APPROX_PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY qty) AS median_disc
FROM dbo.sale;
```

```text
median_cont median_disc
----------- -----------
5.0         5

(1 row affected)
```

### H. Approximate distinct counts and percentiles (sketches)

<!-- example: tsql -->
```sql
SELECT APPROX_COUNT_DISTINCT(product) AS approx_products,
       APPROX_PERCENTILE(qty, 0.5) AS approx_median
FROM dbo.sale;
SELECT TO_APPROX_COUNT_DISTINCT(APPROX_COUNT_DISTINCT_AGG(h)) AS merged_products,
       TO_APPROX_PERCENTILE(APPROX_PERCENTILE_AGG(td), 0.5) AS merged_median
FROM (SELECT region,
             APPROX_COUNT_DISTINCT_DETAIL(product) AS h,
             APPROX_PERCENTILE_DETAIL(qty) AS td
      FROM dbo.sale GROUP BY region) parts;
```

```text
approx_products approx_median
--------------- -------------
2               5.0

(1 row affected)

merged_products merged_median
--------------- -------------
2               5.0

(1 row affected)
```

### I. Aggregates that are not available

<!-- example: tsql -->
```sql
SELECT STDEV(qty) FROM dbo.sale;
GO
SELECT VAR(qty) FROM dbo.sale;
GO
SELECT CHECKSUM_AGG(qty) FROM dbo.sale;
```

```text
Msg 195, Level 15, State 1, Line 1
'stdev' is not a recognized built-in function name.
Msg 195, Level 15, State 1, Line 1
'var' is not a recognized built-in function name.
Msg 195, Level 15, State 1, Line 1
'checksum_agg' is not a recognized built-in function name.
```

## See also

[SELECT ... GROUP BY](select-group-by.md), [OVER](over.md), [Window functions](functions-window.md),
[String functions](functions-string.md)
