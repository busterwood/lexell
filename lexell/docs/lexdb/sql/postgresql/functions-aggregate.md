# Aggregate functions

Functions that compute one value from a group of rows.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
aggregate_name ( [ ALL | DISTINCT ] expression [, ...] [ ORDER BY sort_expression [, ...] ] )
    [ FILTER ( WHERE condition ) ]
aggregate_name ( * ) [ FILTER ( WHERE condition ) ]
ordered_set_aggregate ( fraction ) WITHIN GROUP ( ORDER BY sort_expression ) [ FILTER ( WHERE condition ) ]

count ( * ) → bigint
count ( value ) → bigint
sum ( number ) → bigint | numeric | double precision
avg ( number ) → numeric | double precision
min ( value ) → type of value
max ( value ) → type of value
string_agg ( text, delimiter ) → text
array_agg ( value ) → value[]
bool_and ( boolean ) → boolean
bool_or ( boolean ) → boolean
every ( boolean ) → boolean
bit_and ( integer ) → integer
bit_or ( integer ) → integer
bit_xor ( integer ) → integer
any_value ( value ) → type of value
stddev ( number ) → numeric | double precision
stddev_samp ( number ) → numeric | double precision
stddev_pop ( number ) → numeric | double precision
variance ( number ) → numeric | double precision
var_samp ( number ) → numeric | double precision
var_pop ( number ) → numeric | double precision
percentile_cont ( fraction ) WITHIN GROUP ( ORDER BY number ) → double precision
percentile_disc ( fraction ) WITHIN GROUP ( ORDER BY value ) → type of value
```

## Functions

`count`
: `count(*)` counts the rows; `count(value)` the rows where *value* is not NULL.

`sum`, `avg`
: The total and the mean. `sum` of `integer` or `smallint` is `bigint`, of `bigint` or `numeric` is `numeric`, of a
  float is `double precision`. `avg` of an integer or `numeric` is `numeric`.

`min`, `max`
: The smallest and largest value, of any type that sorts.

`string_agg`
: The values joined with *delimiter* between them, in the order of `ORDER BY` inside the call.

`array_agg`
: The values as an array, NULLs included.

`bool_and`, `every`, `bool_or`
: Whether all the values are true, or any is.

`bit_and`, `bit_or`, `bit_xor`
: The bitwise AND, OR and exclusive OR of the values.

`any_value`
: One of the values that are not NULL (PostgreSQL 16).

`stddev`, `stddev_samp`, `stddev_pop`
: The standard deviation, of a sample (`stddev` is `stddev_samp`) or of the population.

`variance`, `var_samp`, `var_pop`
: The variance, of a sample (`variance` is `var_samp`) or of the population.

`percentile_cont`
: The value at *fraction* (0 to 1) of the ordered values, interpolated between the two nearest: `0.5` is the
  median.

`percentile_disc`
: The first value whose place in the order is at or past *fraction*: always one of the values.

## Remarks

- Every aggregate but `count(*)` leaves out NULLs. Over no rows, `count` is 0 and the others are NULL.
- `DISTINCT` leaves out repeated values; `ORDER BY` inside the call sets the order for `string_agg` and
  `array_agg`; `FILTER (WHERE ...)` takes only the rows that pass.
- Every aggregate may also be a window function with `OVER`: see [window functions](functions-window.md).
- See [GROUP BY](select-group-by.md) for groups, `HAVING`, `ROLLUP`, `CUBE` and `GROUPING SETS`.

## Differences from PostgreSQL

- `json_agg`, `jsonb_agg`, `xmlagg`, `corr`, `covar_pop`, `covar_samp`, `regr_*` and the hypothetical-set
  aggregates (`rank(x) WITHIN GROUP`) do not exist (42883). `mode() WITHIN GROUP (...)` is a syntax error.
- `percentile_cont` and `percentile_disc` take one fraction, not an array of them.
- There is no `CREATE AGGREGATE`.
- `pg_typeof` of an aggregate is computed for each row instead of once: `SELECT pg_typeof(sum(x)) FROM t` over two
  rows gives two rows.

## Examples

<!--setup: postgresql
CREATE TABLE sale (region text, rep text, amount numeric(8,2), units int, paid boolean);
INSERT INTO sale VALUES ('north', 'ann', 120.00, 3, true), ('north', 'bob', 80.50, 2, false),
  ('north', 'ann', 200.00, 5, true), ('south', 'cy', 50.00, 1, true), ('south', 'dee', NULL, 4, NULL),
  ('east', 'eve', 300.00, 6, true);
-->

The examples use this table:

```sql
CREATE TABLE sale (region text, rep text, amount numeric(8,2), units int, paid boolean);
INSERT INTO sale VALUES ('north', 'ann', 120.00, 3, true), ('north', 'bob', 80.50, 2, false),
  ('north', 'ann', 200.00, 5, true), ('south', 'cy', 50.00, 1, true), ('south', 'dee', NULL, 4, NULL),
  ('east', 'eve', 300.00, 6, true);
```

### A. count, sum, avg, min and max

<!-- example: postgresql -->
```sql
SELECT count(*) AS rows, count(amount) AS amounts, count(DISTINCT region) AS regions, sum(amount) AS total,
       round(avg(amount), 2) AS mean, min(amount) AS least, max(rep) AS last_rep FROM sale;
```

```text
 rows | amounts | regions | total  |  mean  | least | last_rep
------+---------+---------+--------+--------+-------+----------
    6 |       5 |       3 | 750.50 | 150.10 | 50.00 | eve
(1 row)
```

### B. Result types

`pg_typeof` is applied in an outer query: see Differences.

<!-- example: postgresql -->
```sql
SELECT pg_typeof(s_int) AS sum_int, pg_typeof(a_int) AS avg_int, pg_typeof(s_num) AS sum_num,
       pg_typeof(s_float) AS sum_float
FROM (SELECT sum(units) AS s_int, avg(units) AS a_int, sum(amount) AS s_num, sum(units::float8) AS s_float
      FROM sale) t;
```

```text
 sum_int | avg_int | sum_num |    sum_float
---------+---------+---------+------------------
 bigint  | numeric | numeric | double precision
(1 row)
```

### C. Per group, with FILTER

<!-- example: postgresql -->
```sql
SELECT region, count(*) AS n, sum(amount) FILTER (WHERE paid) AS paid_total, sum(units) AS units
FROM sale GROUP BY region ORDER BY region;
```

```text
 region | n | paid_total | units
--------+---+------------+-------
 east   | 1 |     300.00 |     6
 north  | 3 |     320.00 |    10
 south  | 2 |      50.00 |     5
(3 rows)
```

### D. string_agg and array_agg

<!-- example: postgresql -->
```sql
SELECT region, string_agg(rep, ', ' ORDER BY rep) AS reps, string_agg(DISTINCT rep, '/') AS distinct_reps,
       array_agg(amount ORDER BY amount DESC) AS amounts FROM sale GROUP BY region ORDER BY region;
```

```text
 region |     reps      | distinct_reps |        amounts
--------+---------------+---------------+-----------------------
 east   | eve           | eve           | {300.00}
 north  | ann, ann, bob | ann/bob       | {200.00,120.00,80.50}
 south  | cy, dee       | cy/dee        | {NULL,50.00}
(3 rows)
```

### E. bool_and, bool_or and every

<!-- example: postgresql -->
```sql
SELECT region, bool_and(paid) AS all_paid, bool_or(paid) AS any_paid, every(units > 1) AS every_multi
FROM sale GROUP BY region ORDER BY region;
```

```text
 region | all_paid | any_paid | every_multi
--------+----------+----------+-------------
 east   | t        | t        | t
 north  | f        | t        | t
 south  | t        | t        | f
(3 rows)
```

### F. Bitwise aggregates and any_value

<!-- example: postgresql -->
```sql
SELECT bit_and(f) AS "and", bit_or(f) AS "or", bit_xor(f) AS "xor" FROM (VALUES (12), (10), (6)) t(f);
SELECT region, any_value(region) IS NOT NULL AS has_value FROM sale GROUP BY region ORDER BY region;
```

```text
 and | or | xor
-----+----+-----
   0 | 14 |   0
(1 row)

 region | has_value
--------+-----------
 east   | t
 north  | t
 south  | t
(3 rows)
```

### G. Standard deviation and variance

<!-- example: postgresql -->
```sql
SELECT round(stddev(units), 4) AS stddev, round(stddev_samp(units), 4) AS samp, round(stddev_pop(units), 4) AS pop,
       round(variance(units), 4) AS var, round(var_samp(units), 4) AS var_samp, round(var_pop(units), 4) AS var_pop
FROM sale;
```

```text
 stddev |  samp  |  pop   |  var   | var_samp | var_pop
--------+--------+--------+--------+----------+---------
 1.8708 | 1.8708 | 1.7078 | 3.5000 |   3.5000 |  2.9167
(1 row)
```

### H. Percentiles

<!-- example: postgresql -->
```sql
SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY units) AS median,
       percentile_cont(0.25) WITHIN GROUP (ORDER BY units) AS q1,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY units) AS median_disc,
       percentile_disc(0.5) WITHIN GROUP (ORDER BY rep) AS middle_rep FROM sale;
```

```text
 median |  q1  | median_disc | middle_rep
--------+------+-------------+------------
    3.5 | 2.25 |           3 | bob
(1 row)
```

### I. Over no rows

<!-- example: postgresql -->
```sql
SELECT count(*) AS n, sum(amount) AS total, max(rep) AS rep, bool_and(paid) AS all_paid FROM sale WHERE false;
```

```text
 n | total | rep | all_paid
---+-------+-----+----------
 0 |       |     |
(1 row)
```

### J. Errors

<!-- example: postgresql -->
```sql
SELECT region, rep, sum(amount) FROM sale GROUP BY region;
SELECT corr(units, amount) FROM sale;
```

```text
ERROR:  column "sale.rep" must appear in the GROUP BY clause or be used in an aggregate function
ERROR:  function corr with 2 arguments does not exist
```

## See also

[GROUP BY](select-group-by.md) · [Window functions](functions-window.md) · [OVER](over.md) ·
[SELECT](select.md)
