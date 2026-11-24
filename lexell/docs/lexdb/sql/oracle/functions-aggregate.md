# Aggregate functions

Functions that combine the rows of a group into one value.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
COUNT ( { * | [ DISTINCT | ALL ] expr } )
SUM ( [ DISTINCT | ALL ] expr )
AVG ( [ DISTINCT | ALL ] expr )
MIN ( expr )         MAX ( expr )
STDDEV ( expr )      VARIANCE ( expr )
LISTAGG ( [ DISTINCT ] expr [, separator ] ) WITHIN GROUP ( ORDER BY expr [ ASC | DESC ] )
ANY_VALUE ( expr )
PERCENTILE_CONT ( fraction ) WITHIN GROUP ( ORDER BY expr )
PERCENTILE_DISC ( fraction ) WITHIN GROUP ( ORDER BY expr )
BIT_AND_AGG ( expr )  BIT_OR_AGG ( expr )  BIT_XOR_AGG ( expr )
BOOLEAN_AND_AGG ( expr )  BOOLEAN_OR_AGG ( expr )
KURTOSIS_POP ( expr )  KURTOSIS_SAMP ( expr )  SKEWNESS_POP ( expr )  SKEWNESS_SAMP ( expr )
```

## Functions

`COUNT`
: The number of rows, or of rows where *expr* is not NULL. `COUNT(DISTINCT x)` counts different values. The result
  is never NULL: an empty group gives 0.

`SUM`, `AVG`
: The total and the mean of the non-NULL values; NULL when there are none.

`MIN`, `MAX`
: The least and greatest value of numbers, strings (case sensitive) and dates, NULLs left out.

`STDDEV`, `VARIANCE`
: The sample standard deviation and variance.

`LISTAGG`
: The values joined into one string, in the `WITHIN GROUP` order, with *separator* (none by default). NULLs are
  skipped.

`ANY_VALUE`
: One value of the group, whichever the engine meets; it avoids a `GROUP BY` on a column that is the same in the
  group (23ai).

`PERCENTILE_CONT`, `PERCENTILE_DISC`
: The value at *fraction* (0 to 1) of the ordered values: the first interpolates, the second takes a value of the
  group.

`BIT_AND_AGG`, `BIT_OR_AGG`, `BIT_XOR_AGG`
: The bitwise AND, OR and exclusive OR of the values (23ai).

`BOOLEAN_AND_AGG`, `BOOLEAN_OR_AGG`
: True when all, or when at least one, of the boolean values is true (23ai).

`KURTOSIS_*`, `SKEWNESS_*`
: The kurtosis and skewness of the values, of the whole population (`_POP`) or of a sample (`_SAMP`) (23ai).

## Remarks

- Without `GROUP BY` an aggregate gives one row over the whole table, even when it is empty.
- `WHERE` filters rows before grouping, `HAVING` filters groups after it. A select-list column that is neither
  grouped nor aggregated is ORA-00979.
- An aggregate followed by `OVER (...)` is an analytic function: see [analytic functions](functions-analytic.md).

## Differences from Oracle

- `MEDIAN`, `STATS_MODE`, `CORR`, `COVAR_POP`, `COVAR_SAMP`, `REGR_*` and `XMLAGG` are not available (ORA-00904).
- `MIN` and `MAX` of a `DATE` show as a timestamp (`2019-03-01 00:00:00.0`): use `TO_CHAR`.
- `SELECT COUNT(*) ... WHERE ROWNUM < n` counts the first n rows of one table, as Oracle does; over a join it limits
  the groups, not the rows (see [SELECT](select.md)).

## Examples

<!--setup: oracle
CREATE TABLE sale (id NUMBER PRIMARY KEY, region VARCHAR2(10), product VARCHAR2(10), qty NUMBER, price NUMBER(8,2));
INSERT INTO sale VALUES (1, 'north', 'pen', 10, 1.50);
INSERT INTO sale VALUES (2, 'north', 'ink', 2, 4.25);
INSERT INTO sale VALUES (3, 'south', 'pen', 5, 1.50);
INSERT INTO sale VALUES (4, 'south', 'pen', 7, 1.60);
INSERT INTO sale VALUES (5, 'south', NULL, NULL, 2.00);
INSERT INTO sale VALUES (6, 'east', 'ink', 1, 4.00);
COMMIT;
-->

The examples use a table `sale (id, region, product, qty, price)` with six rows; one has a NULL product and quantity.

```sql
CREATE TABLE sale (id NUMBER PRIMARY KEY, region VARCHAR2(10), product VARCHAR2(10), qty NUMBER, price NUMBER(8,2));
INSERT INTO sale VALUES (1, 'north', 'pen', 10, 1.50);
INSERT INTO sale VALUES (2, 'north', 'ink', 2, 4.25);
INSERT INTO sale VALUES (3, 'south', 'pen', 5, 1.50);
INSERT INTO sale VALUES (4, 'south', 'pen', 7, 1.60);
INSERT INTO sale VALUES (5, 'south', NULL, NULL, 2.00);
INSERT INTO sale VALUES (6, 'east', 'ink', 1, 4.00);
```

### A. COUNT, SUM, AVG, MIN and MAX

<!-- example: oracle -->
```sql
SELECT COUNT(*) AS rows_, COUNT(qty) AS with_qty, COUNT(DISTINCT product) AS products, SUM(qty) AS total_qty,
       AVG(qty) AS avg_qty, MIN(qty) AS min_qty, MAX(qty) AS max_qty, MIN(product) AS first_product,
       MAX(price) AS dearest
FROM sale;
SELECT COUNT(*) AS rows_, SUM(qty) AS total FROM sale WHERE id > 100;
```

```text
ROWS_ WITH_QTY PRODUCTS TOTAL_QTY AVG_QTY MIN_QTY MAX_QTY FIRST_PRODUCT DEAREST
----- -------- -------- --------- ------- ------- ------- ------------- -------
    6        5        2        25       5       1      10 ink              4.25

1 row selected.

ROWS_ TOTAL
----- -----
    0

1 row selected.
```

### B. GROUP BY and HAVING

<!-- example: oracle -->
```sql
SELECT region, COUNT(*) AS sales, SUM(qty) AS units FROM sale GROUP BY region HAVING COUNT(*) > 1 ORDER BY region;
SELECT region, qty FROM sale GROUP BY region;
```

```text
REGION SALES UNITS
------ ----- -----
north      2    12
south      3    12

2 rows selected.

ERROR:
ORA-00979: not a GROUP BY expression
```

### C. STDDEV and VARIANCE

<!-- example: oracle -->
```sql
SELECT ROUND(STDDEV(qty), 4) AS stddev_, ROUND(VARIANCE(qty), 4) AS variance_ FROM sale;
```

```text
STDDEV_ VARIANCE_
------- ---------
 3.6742      13.5

1 row selected.
```

### D. LISTAGG

<!-- example: oracle -->
```sql
SELECT region, LISTAGG(product, ', ') WITHIN GROUP (ORDER BY product) AS products
FROM sale GROUP BY region ORDER BY region;
SELECT LISTAGG(id, '-') WITHIN GROUP (ORDER BY id DESC) AS ids FROM sale;
SELECT LISTAGG(DISTINCT product, ',') WITHIN GROUP (ORDER BY product) AS distinct_products FROM sale;
```

```text
REGION PRODUCTS
------ --------
east   ink
north  ink, pen
south  pen, pen

3 rows selected.

IDS
-----------
6-5-4-3-2-1

1 row selected.

DISTINCT_PRODUCTS
-----------------
ink,pen

1 row selected.
```

### E. ANY_VALUE and percentiles

<!-- example: oracle -->
```sql
SELECT region, ANY_VALUE(region) AS any_region FROM sale GROUP BY region ORDER BY region;
SELECT PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY qty) AS median_cont,
       PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY qty) AS median_disc FROM sale;
```

```text
REGION ANY_REGION
------ ----------
east   east
north  north
south  south

3 rows selected.

MEDIAN_CONT MEDIAN_DISC
----------- -----------
          5           5

1 row selected.
```

### F. Bit and boolean aggregates

<!-- example: oracle -->
```sql
SELECT BIT_AND_AGG(qty) AS bit_and, BIT_OR_AGG(qty) AS bit_or, BIT_XOR_AGG(qty) AS bit_xor FROM sale;
SELECT BOOLEAN_AND_AGG(qty > 0) AS all_positive, BOOLEAN_OR_AGG(qty > 8) AS any_big FROM sale;
```

```text
BIT_AND BIT_OR BIT_XOR
------- ------ -------
      0     15      11

1 row selected.

ALL_POSITIVE ANY_BIG
------------ -------
true         true

1 row selected.
```

### G. Kurtosis and skewness

<!-- example: oracle -->
```sql
SELECT ROUND(SKEWNESS_POP(qty), 4) AS skew_pop, ROUND(SKEWNESS_SAMP(qty), 4) AS skew_samp,
       ROUND(KURTOSIS_POP(qty), 4) AS kurt_pop, ROUND(KURTOSIS_SAMP(qty), 4) AS kurt_samp FROM sale;
```

```text
SKEW_POP SKEW_SAMP KURT_POP KURT_SAMP
-------- --------- -------- ---------
  0.2367    0.3528   -1.323   -1.2922

1 row selected.
```

### H. Aggregates that are not available

<!-- example: oracle -->
```sql
SELECT MEDIAN(qty) FROM sale;
SELECT CORR(qty, price) FROM sale;
SELECT STATS_MODE(qty) FROM sale;
```

```text
ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier
```

## See also

[Analytic functions](functions-analytic.md), [SELECT](select-group-by.md), [Operators](operators.md)
