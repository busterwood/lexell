# GROUP BY

Groups the rows of a [SELECT](select.md) and computes aggregates over each group; `HAVING` filters the groups.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SELECT ...
    FROM ...
    [ WHERE condition ]
    GROUP BY [ ALL | DISTINCT ] grouping_element [, ...]
    [ HAVING condition ]

grouping_element:
    ()
    | expression
    | ( expression [, ...] )
    | ROLLUP ( { expression | ( expression [, ...] ) } [, ...] )
    | CUBE ( { expression | ( expression [, ...] ) } [, ...] )
    | GROUPING SETS ( grouping_element [, ...] )

aggregate_name ( [ ALL | DISTINCT ] expression [, ...] [ ORDER BY sort_item [, ...] ] ) [ FILTER ( WHERE condition ) ]
aggregate_name ( * ) [ FILTER ( WHERE condition ) ]
aggregate_name ( fraction ) WITHIN GROUP ( ORDER BY sort_item ) [ FILTER ( WHERE condition ) ]
```

## Arguments

*expression*
: A value to group by: a column, an expression, an output column's name or its position in the select list
  (`GROUP BY 1`). Rows with equal values (NULLs are equal here) form one group.

`()`
: The empty grouping set: one group of every row.

`ROLLUP (a, b, c)`
: The grouping sets `(a, b, c)`, `(a, b)`, `(a)` and `()`: subtotals and a total.

`CUBE (a, b)`
: Every subset: `(a, b)`, `(a)`, `(b)`, `()`. At most 12 elements (54001).

`GROUPING SETS (...)`
: The sets listed, one after another. A list of several elements in `GROUP BY` is the cross product of their sets.

`DISTINCT`
: Removes a grouping set listed twice. `ALL`, the default, keeps them.

`HAVING` *condition*
: Keeps the groups for which the condition is true. It may use aggregates and the grouping columns. Without
  `GROUP BY`, `HAVING` makes the whole result one group.

`DISTINCT` in an aggregate
: Aggregates each distinct value once: `count(DISTINCT dept_id)`.

`ORDER BY` in an aggregate
: The order in which the aggregate takes its values, for `string_agg` and `array_agg`.

`FILTER ( WHERE` *condition* `)`
: Gives the aggregate only the rows for which the condition is true.

`WITHIN GROUP ( ORDER BY ... )`
: The order an ordered-set aggregate (`percentile_cont`, `percentile_disc`) reads.

## Remarks

- Every column the select list, `HAVING` or `ORDER BY` uses outside an aggregate must be grouped, or be a column
  of a table whose primary key is grouped (42803 otherwise).
- In a grouping set that leaves a column out, the column is NULL. `grouping(a, b, ...)` tells a row of a set that
  left the column out from a NULL in the data: it gives a bit for each argument, 1 when that column is not grouped
  in the row's set, the first argument the highest bit.
- An aggregate over no rows gives NULL, except `count`, which gives 0. A query with aggregates and no `GROUP BY` gives
  one row.
- The aggregate functions are `count`, `sum`, `avg`, `min`, `max`, `string_agg`, `array_agg`, `bool_and`,
  `bool_or`, `every`, `bit_and`, `bit_or`, `bit_xor`, `any_value`, `stddev`, `stddev_samp`, `stddev_pop`, `variance`,
  `var_samp`, `var_pop`, `percentile_cont` and `percentile_disc`.

## Differences from PostgreSQL

- A window function in a query with `ROLLUP`, `CUBE` or `GROUPING SETS` is refused (0A000, lexdb-gaps.md 2.2). With a
  plain `GROUP BY` it works.
- `GROUP BY ALL` with no elements after it (PostgreSQL 19's "group by every column that is not an aggregate") is a
  syntax error; `ALL` is read as PostgreSQL 18 reads it, the opposite of `DISTINCT`.
- `json_agg` and the statistical aggregates `corr`, `regr_*` and `covar_*` do not exist (42883). `mode() WITHIN
  GROUP (...)` is a syntax error.

## Examples

<!--setup: postgresql
CREATE TABLE dept (id int PRIMARY KEY, name text NOT NULL);
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept_id int REFERENCES dept, salary numeric(8,2), hired date, manager_id int);
INSERT INTO dept VALUES (1, 'sales'), (2, 'research'), (3, 'admin');
INSERT INTO emp VALUES (1, 'ada', 2, 5200, '2020-03-01', NULL), (2, 'ben', 1, 3100, '2021-07-15', 1),
  (3, 'cy', 1, 2900, '2022-01-10', 2), (4, 'dee', 2, 4800, '2019-11-30', 1), (5, 'eve', NULL, 2500, '2023-05-02', 1);
CREATE TABLE sale (region text, product text, qty int);
INSERT INTO sale VALUES ('north', 'pen', 10), ('north', 'ink', 4), ('south', 'pen', 7), ('south', 'pen', 3), ('south', 'ink', 1);
-->

The examples use these tables:

```sql
CREATE TABLE dept (id int PRIMARY KEY, name text NOT NULL);
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept_id int REFERENCES dept, salary numeric(8,2),
                  hired date, manager_id int);
INSERT INTO dept VALUES (1, 'sales'), (2, 'research'), (3, 'admin');
INSERT INTO emp VALUES (1, 'ada', 2, 5200, '2020-03-01', NULL), (2, 'ben', 1, 3100, '2021-07-15', 1),
  (3, 'cy', 1, 2900, '2022-01-10', 2), (4, 'dee', 2, 4800, '2019-11-30', 1), (5, 'eve', NULL, 2500, '2023-05-02', 1);
CREATE TABLE sale (region text, product text, qty int);
INSERT INTO sale VALUES ('north', 'pen', 10), ('north', 'ink', 4), ('south', 'pen', 7), ('south', 'pen', 3),
  ('south', 'ink', 1);
```

### A. Groups and aggregates

<!-- example: postgresql -->
```sql
SELECT dept_id, count(*), sum(salary), min(salary), max(salary)
FROM emp
GROUP BY dept_id
ORDER BY dept_id;
```

```text
 dept_id | count |   sum    |   min   |   max
---------+-------+----------+---------+---------
       1 |     2 |  6000.00 | 2900.00 | 3100.00
       2 |     2 | 10000.00 | 4800.00 | 5200.00
         |     1 |  2500.00 | 2500.00 | 2500.00
(3 rows)
```

### B. HAVING

<!-- example: postgresql -->
```sql
SELECT dept_id, count(*) FROM emp GROUP BY dept_id HAVING count(*) > 1 ORDER BY dept_id;
```

```text
 dept_id | count
---------+-------
       1 |     2
       2 |     2
(2 rows)
```

### C. Grouping by a primary key

`d.name` need not be grouped: it is a column of `dept`, whose primary key is.

<!-- example: postgresql -->
```sql
SELECT d.id, d.name, count(e.id) AS staff
FROM dept d LEFT JOIN emp e ON e.dept_id = d.id
GROUP BY d.id
ORDER BY d.id;
```

```text
 id |   name   | staff
----+----------+-------
  1 | sales    |     2
  2 | research |     2
  3 | admin    |     0
(3 rows)
```

### D. DISTINCT, ORDER BY and FILTER in an aggregate

<!-- example: postgresql -->
```sql
SELECT count(DISTINCT dept_id) AS depts,
       string_agg(name, ', ' ORDER BY name) AS names,
       count(*) FILTER (WHERE salary > 3000) AS well_paid
FROM emp;
```

```text
 depts |         names          | well_paid
-------+------------------------+-----------
     2 | ada, ben, cy, dee, eve |         3
(1 row)
```

### E. An ordered-set aggregate

<!-- example: postgresql -->
```sql
SELECT percentile_disc(0.5) WITHIN GROUP (ORDER BY salary) AS median FROM emp;
```

```text
 median
---------
 3100.00
(1 row)
```

### F. ROLLUP

Subtotals for each region and a total. `grouping` marks the rows a set made.

<!-- example: postgresql -->
```sql
SELECT region, product, sum(qty), grouping(region, product) AS g
FROM sale
GROUP BY ROLLUP (region, product)
ORDER BY region, product;
```

```text
 region | product | sum | g
--------+---------+-----+---
 north  | ink     |   4 | 0
 north  | pen     |  10 | 0
 north  |         |  14 | 1
 south  | ink     |   1 | 0
 south  | pen     |  10 | 0
 south  |         |  11 | 1
        |         |  25 | 3
(7 rows)
```

### G. CUBE and GROUPING SETS

<!-- example: postgresql -->
```sql
SELECT region, product, sum(qty) FROM sale GROUP BY CUBE (region, product) ORDER BY region, product;
SELECT region, product, sum(qty) FROM sale GROUP BY GROUPING SETS ((region), (product)) ORDER BY region, product;
```

```text
 region | product | sum
--------+---------+-----
 north  | ink     |   4
 north  | pen     |  10
 north  |         |  14
 south  | ink     |   1
 south  | pen     |  10
 south  |         |  11
        | ink     |   5
        | pen     |  20
        |         |  25
(9 rows)

 region | product | sum
--------+---------+-----
 north  |         |  14
 south  |         |  11
        | ink     |   5
        | pen     |  20
(4 rows)
```

### H. Aggregates over no rows

<!-- example: postgresql -->
```sql
SELECT count(*), sum(qty), max(qty) FROM sale WHERE qty > 100;
SELECT region, sum(qty) FROM sale WHERE qty > 100 GROUP BY region;
```

```text
 count | sum | max
-------+-----+-----
     0 |     |
(1 row)

 region | sum
--------+-----
(0 rows)
```

### I. A window function over the groups

<!-- example: postgresql -->
```sql
SELECT region, sum(qty) AS qty, rank() OVER (ORDER BY sum(qty) DESC) FROM sale GROUP BY region ORDER BY region;
SELECT region, sum(qty), rank() OVER (ORDER BY sum(qty)) FROM sale GROUP BY ROLLUP (region);
```

```text
 region | qty | rank
--------+-----+------
 north  |  14 |    1
 south  |  11 |    2
(2 rows)

ERROR:  lexdb: window functions with ROLLUP, CUBE or GROUPING SETS are not supported
```

### J. Errors

<!-- example: postgresql -->
```sql
SELECT name, count(*) FROM emp;
SELECT dept_id, count(*) FROM emp GROUP BY dept_id HAVING salary > 3000;
```

```text
ERROR:  column "emp.name" must appear in the GROUP BY clause or be used in an aggregate function
ERROR:  column "emp.salary" must appear in the GROUP BY clause or be used in an aggregate function
```

## See also

[SELECT](select.md) · [Window functions](over.md) · [Joins](select-join.md)
