# SELECT - OVER clause (Transact-SQL)

Defines the window of rows a window function, or an aggregate used as one, works over: how the rows are
partitioned, in what order, and which rows of the partition the frame holds.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
OVER (
    [ window_name ]
    [ PARTITION BY value_expression [ ,...n ] ]
    [ ORDER BY order_by_expression [ ASC | DESC ] [ ,...n ] ]
    [ ROWS_or_RANGE_clause ]
)
OVER window_name

ROWS_or_RANGE_clause ::=
{ ROWS | RANGE } { window_frame_preceding | BETWEEN window_frame_bound AND window_frame_bound }

window_frame_bound ::=
{ UNBOUNDED PRECEDING | n PRECEDING | CURRENT ROW | n FOLLOWING | UNBOUNDED FOLLOWING }

-- in the query, after HAVING (SQL Server 2022)
WINDOW window_name AS ( window_spec ) [ ,...n ]
```

## Arguments

`PARTITION BY`
: Divides the rows into partitions; the function starts again in each. Without it the whole result is one partition.

`ORDER BY`
: The order of the rows within the partition. Ranking functions, `LAG`, `LEAD` and the running forms of the
  aggregates need it.

`ROWS`, `RANGE`
: The frame: the rows of the partition that an aggregate, `FIRST_VALUE` or `LAST_VALUE` sees for the current row.
  `ROWS` counts rows; `RANGE` takes the rows whose `ORDER BY` value is in range, so rows that tie are in the frame
  together. With `ORDER BY` and no frame, the frame is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`; without
  `ORDER BY` it is the whole partition.

*window_name*, `WINDOW`
: A named window specification. `OVER (window_name ORDER BY ...)` adds to the named one.

## Remarks

- The functions that take `OVER`:
  - ranking: `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `NTILE`;
  - offset and value: `LAG`, `LEAD`, `FIRST_VALUE`, `LAST_VALUE`, with `IGNORE NULLS` or `RESPECT NULLS`
    (SQL Server 2022);
  - distribution: `PERCENT_RANK`, `CUME_DIST`, and `PERCENTILE_CONT` and `PERCENTILE_DISC` with
    `WITHIN GROUP (ORDER BY ...)` and an `OVER (PARTITION BY ...)`;
  - the aggregates `COUNT`, `SUM`, `MIN`, `MAX` and `STRING_AGG`.
- Window functions run after `WHERE`, `GROUP BY` and `HAVING`. They may be used in the select list and in
  `ORDER BY` only. To filter on one, compute it in a derived table or a common table expression first.
- `ORDER BY (SELECT NULL)` is taken when a function needs an order and any order will do.

## Differences from SQL Server

- **`AVG` with `OVER` fails**: the query gets error 50000, "column ... must appear in the GROUP BY clause or be
  used in an aggregate function" (example H). Use `SUM(x) OVER (...) / COUNT(x) OVER (...)`, with a cast where the
  type matters.
- `COUNT_BIG` with `OVER` is error 195 ("function count_big with 0 arguments does not exist"); use `COUNT`.
- `STDEV`, `STDEVP`, `VAR` and `VARP` are not available (error 195). `NTH_VALUE` works (SQL Server has none).
- `ROW_NUMBER`, `RANK` and the other ranking functions are taken without `ORDER BY` (`OVER ()`); SQL Server
  refuses that (4112).
- `RANGE` with an offset (`RANGE BETWEEN 2 PRECEDING AND CURRENT ROW`) is taken; SQL Server allows only
  `UNBOUNDED` and `CURRENT ROW` with `RANGE` (4194).
- A window function in `WHERE` is error 50000 with lexdb's text (SQL Server: 4108).

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

### A. Ranking

<!-- example: tsql -->
```sql
SELECT region, amount,
       ROW_NUMBER() OVER (ORDER BY amount DESC) AS rn,
       RANK() OVER (PARTITION BY region ORDER BY yr) AS rk,
       DENSE_RANK() OVER (PARTITION BY region ORDER BY yr) AS dr,
       NTILE(2) OVER (ORDER BY amount) AS half
FROM dbo.sale
ORDER BY region, amount;
```

```text
region amount rn rk dr half
------ ------ -- -- -- ----
north  10     2  1  1  2
north  20     1  2  2  2
south  3      5  2  2  1
south  5      4  1  1  1
south  7      3  2  2  1

(5 rows affected)
```

### B. Aggregates over a partition

<!-- example: tsql -->
```sql
SELECT region, amount,
       SUM(amount) OVER (PARTITION BY region) AS region_total,
       COUNT(*) OVER () AS all_rows,
       MAX(amount) OVER (PARTITION BY region) AS region_max
FROM dbo.sale
ORDER BY region, amount;
```

```text
region amount region_total all_rows region_max
------ ------ ------------ -------- ----------
north  10     30           5        20
north  20     30           5        20
south  3      15           5        7
south  5      15           5        7
south  7      15           5        7

(5 rows affected)
```

### C. A running total and a moving sum

<!-- example: tsql -->
```sql
SELECT region, amount,
       SUM(amount) OVER (PARTITION BY region ORDER BY amount ROWS UNBOUNDED PRECEDING) AS running,
       SUM(amount) OVER (PARTITION BY region ORDER BY amount ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING) AS moving
FROM dbo.sale
ORDER BY region, amount;
```

```text
region amount running moving
------ ------ ------- ------
north  10     10      30
north  20     30      30
south  3      3       8
south  5      8       15
south  7      15      12

(5 rows affected)
```

### D. LAG, LEAD, FIRST_VALUE and LAST_VALUE

<!-- example: tsql -->
```sql
SELECT region, yr, amount,
       LAG(amount) OVER (PARTITION BY region ORDER BY yr, amount) AS prev,
       LEAD(amount, 1, 0) OVER (PARTITION BY region ORDER BY yr, amount) AS next,
       FIRST_VALUE(amount) OVER (PARTITION BY region ORDER BY yr, amount) AS first,
       LAST_VALUE(amount) OVER (PARTITION BY region ORDER BY yr, amount
                                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last
FROM dbo.sale
ORDER BY region, yr, amount;
```

```text
region yr   amount prev next first last
------ ---- ------ ---- ---- ----- ----
north  2024 10     NULL 20   10    20
north  2025 20     10   0    10    20
south  2024 5      NULL 3    5     7
south  2025 3      5    7    5     7
south  2025 7      3    0    5     7

(5 rows affected)
```

### E. IGNORE NULLS

<!-- example: tsql -->
```sql
SELECT n, v, LAST_VALUE(v) IGNORE NULLS OVER (ORDER BY n ROWS UNBOUNDED PRECEDING) AS filled
FROM (VALUES (1, 10), (2, NULL), (3, NULL), (4, 40)) AS t (n, v)
ORDER BY n;
```

```text
n v    filled
- ---- ------
1 10   10
2 NULL 10
3 NULL 10
4 40   40

(4 rows affected)
```

### F. A named window

<!-- example: tsql -->
```sql
SELECT region, amount,
       SUM(amount) OVER w AS region_total,
       ROW_NUMBER() OVER (w ORDER BY amount) AS n
FROM dbo.sale
WINDOW w AS (PARTITION BY region)
ORDER BY region, amount;
```

```text
region amount region_total n
------ ------ ------------ -
north  10     30           1
north  20     30           2
south  3      15           1
south  5      15           2
south  7      15           3

(5 rows affected)
```

### G. PERCENTILE_CONT over a partition, and filtering on a window function

<!-- example: tsql -->
```sql
SELECT DISTINCT region,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY amount) OVER (PARTITION BY region) AS median
FROM dbo.sale;
SELECT region, amount
FROM (SELECT region, amount, ROW_NUMBER() OVER (PARTITION BY region ORDER BY amount DESC) AS rn FROM dbo.sale) AS r
WHERE rn = 1
ORDER BY region;
```

```text
region median
------ ------
north  15.0
south  5.0

(2 rows affected)

region amount
------ ------
north  20
south  7

(2 rows affected)
```

### H. Errors

<!-- example: tsql -->
```sql
SELECT region, AVG(amount) OVER (PARTITION BY region) AS region_avg FROM dbo.sale;
SELECT region FROM dbo.sale WHERE ROW_NUMBER() OVER (ORDER BY amount) = 1;
GO
SELECT region, STDEV(amount) OVER () FROM dbo.sale;
GO
```

```text
Msg 50000, Level 16, State 1, Line 1
column "sale.region" must appear in the GROUP BY clause or be used in an aggregate function
Msg 50000, Level 16, State 1, Line 2
window functions are not allowed in WHERE
Msg 195, Level 15, State 1, Line 1
'stdev' is not a recognized built-in function name.
```

## See also

[SELECT](select.md) · [GROUP BY](select-group-by.md) · [ORDER BY](order-by.md)
