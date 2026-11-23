# Window functions (OVER)

Compute a value for each row from a set of rows related to it, its window, without merging the rows into groups.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
function_name ( [ expression [, ...] ] ) [ { RESPECT | IGNORE } NULLS ] [ FILTER ( WHERE condition ) ]
    OVER { window_name | ( window_definition ) }
aggregate_name ( * ) [ FILTER ( WHERE condition ) ] OVER { window_name | ( window_definition ) }

window_definition:
    [ existing_window_name ]
    [ PARTITION BY expression [, ...] ]
    [ ORDER BY expression [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [, ...] ]
    [ frame_clause ]

frame_clause:
    { RANGE | ROWS | GROUPS } frame_start [ frame_exclusion ]
    | { RANGE | ROWS | GROUPS } BETWEEN frame_start AND frame_end [ frame_exclusion ]

frame_start, frame_end:
    UNBOUNDED PRECEDING
    | offset PRECEDING
    | CURRENT ROW
    | offset FOLLOWING
    | UNBOUNDED FOLLOWING

frame_exclusion:
    EXCLUDE CURRENT ROW | EXCLUDE GROUP | EXCLUDE TIES | EXCLUDE NO OTHERS

SELECT ... WINDOW window_name AS ( window_definition ) [, ...]
```

## Arguments

*function_name*
: A window function (`row_number`, `rank`, `dense_rank`, `percent_rank`, `cume_dist`, `ntile`, `lag`, `lead`,
  `first_value`, `last_value`, `nth_value`) or any aggregate (`sum`, `count`, `avg`, `array_agg` ...).

`IGNORE NULLS`
: For `lag`, `lead`, `first_value`, `last_value` and `nth_value` (PostgreSQL 19): skips the rows whose value is
  NULL. `RESPECT NULLS` is the default.

`FILTER ( WHERE` *condition* `)`
: For an aggregate: only the rows of the window for which the condition is true.

`PARTITION BY`
: Splits the rows into partitions; a row's window is within its partition. Without it, all rows are one
  partition.

`ORDER BY`
: The order of the rows in a partition, which the ranking functions, `lag`, `lead` and the frame follow. Rows
  equal by it are peers.

*frame_clause*
: The rows of the partition an aggregate, `first_value`, `last_value` and `nth_value` see:
  - `ROWS` counts rows; `GROUPS` counts groups of peers; `RANGE` takes the rows whose `ORDER BY` value is within
    *offset* of the current row's (one `ORDER BY` column: a number, or an interval for a date or timestamp).
  - The default, with `ORDER BY`, is `RANGE BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`: the rows up to the current
    row and its peers. Without `ORDER BY` it is the whole partition.
  - A frame with only *frame_start* ends at `CURRENT ROW`.
  - `EXCLUDE CURRENT ROW` leaves the current row out, `EXCLUDE GROUP` the row and its peers, `EXCLUDE TIES` its
    peers but not the row.

*existing_window_name*
: A window of the `WINDOW` clause to build on: the new definition may add `ORDER BY` (if the named one has none)
  and a frame.

`WINDOW` *window_name* `AS (` *window_definition* `)`
: Names a window that several `OVER` clauses share.

## Remarks

- Window functions are computed after `WHERE`, `GROUP BY` and `HAVING`, and before `DISTINCT`, `ORDER BY` and
  `LIMIT`. They may be used in the select list and `ORDER BY` only; to filter by one, use a subquery.
- In a query with `GROUP BY`, a window function's arguments and its `PARTITION BY` and `ORDER BY` may use
  aggregates: `rank() OVER (ORDER BY sum(qty) DESC)`.
- `lag(x, n, default)` and `lead(x, n, default)` look *n* rows back or ahead (1 by default) and give *default*
  (NULL by default) past the partition's ends.
- `ntile(n)` splits the partition into *n* numbered parts as equal as can be.
- An aggregate with `DISTINCT` cannot be a window function (0A000), as in PostgreSQL.

## Differences from PostgreSQL

- A window function in a query with `ROLLUP`, `CUBE` or `GROUPING SETS` is refused (0A000, lexdb-gaps.md 2.2).
- `IGNORE NULLS` is PostgreSQL 19's; PostgreSQL 18 has no such option.

## Examples

<!--setup: postgresql
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept_id int, salary numeric(8,2), hired date);
INSERT INTO emp VALUES (1, 'ada', 2, 5200, '2020-03-01'), (2, 'ben', 1, 3100, '2021-07-15'),
  (3, 'cy', 1, 2900, '2022-01-10'), (4, 'dee', 2, 4800, '2019-11-30'), (5, 'eve', NULL, 2500, '2023-05-02');
-->

The examples use one table:

```sql
CREATE TABLE emp (id int PRIMARY KEY, name text NOT NULL, dept_id int, salary numeric(8,2), hired date);
INSERT INTO emp VALUES (1, 'ada', 2, 5200, '2020-03-01'), (2, 'ben', 1, 3100, '2021-07-15'),
  (3, 'cy', 1, 2900, '2022-01-10'), (4, 'dee', 2, 4800, '2019-11-30'), (5, 'eve', NULL, 2500, '2023-05-02');
```

### A. Ranking

<!-- example: postgresql -->
```sql
SELECT name, dept_id, salary,
       rank() OVER (ORDER BY salary DESC) AS overall,
       row_number() OVER (PARTITION BY dept_id ORDER BY salary DESC) AS in_dept
FROM emp
ORDER BY id;
```

```text
 name | dept_id | salary  | overall | in_dept
------+---------+---------+---------+---------
 ada  |       2 | 5200.00 |       1 |       1
 ben  |       1 | 3100.00 |       3 |       1
 cy   |       1 | 2900.00 |       4 |       2
 dee  |       2 | 4800.00 |       2 |       2
 eve  |         | 2500.00 |       5 |       1
(5 rows)
```

### B. An aggregate over a partition

<!-- example: postgresql -->
```sql
SELECT name, dept_id, salary, sum(salary) OVER (PARTITION BY dept_id) AS dept_total
FROM emp
ORDER BY id;
```

```text
 name | dept_id | salary  | dept_total
------+---------+---------+------------
 ada  |       2 | 5200.00 |   10000.00
 ben  |       1 | 3100.00 |    6000.00
 cy   |       1 | 2900.00 |    6000.00
 dee  |       2 | 4800.00 |   10000.00
 eve  |         | 2500.00 |    2500.00
(5 rows)
```

### C. A running total and a moving average

<!-- example: postgresql -->
```sql
SELECT name, hired, salary,
       sum(salary) OVER (ORDER BY hired) AS running,
       avg(salary) OVER (ORDER BY hired ROWS BETWEEN 1 PRECEDING AND 1 FOLLOWING)::numeric(8,2) AS moving
FROM emp
ORDER BY hired;
```

```text
 name |   hired    | salary  | running  | moving
------+------------+---------+----------+---------
 dee  | 2019-11-30 | 4800.00 |  4800.00 | 5000.00
 ada  | 2020-03-01 | 5200.00 | 10000.00 | 4366.67
 ben  | 2021-07-15 | 3100.00 | 13100.00 | 3733.33
 cy   | 2022-01-10 | 2900.00 | 16000.00 | 2833.33
 eve  | 2023-05-02 | 2500.00 | 18500.00 | 2700.00
(5 rows)
```

### D. lag, lead and a named window

<!-- example: postgresql -->
```sql
SELECT name, hired, lag(name) OVER w AS before, lead(name, 1, '-') OVER w AS after
FROM emp
WINDOW w AS (ORDER BY hired)
ORDER BY hired;
```

```text
 name |   hired    | before | after
------+------------+--------+-------
 dee  | 2019-11-30 |        | ada
 ada  | 2020-03-01 | dee    | ben
 ben  | 2021-07-15 | ada    | cy
 cy   | 2022-01-10 | ben    | eve
 eve  | 2023-05-02 | cy     | -
(5 rows)
```

### E. first_value, last_value and nth_value

The default frame ends at the current row, so `last_value` needs a frame to the partition's end.

<!-- example: postgresql -->
```sql
SELECT name, salary,
       first_value(name) OVER w AS lowest,
       last_value(name) OVER w AS highest,
       nth_value(name, 2) OVER w AS second
FROM emp
WINDOW w AS (ORDER BY salary ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
ORDER BY salary;
```

```text
 name | salary  | lowest | highest | second
------+---------+--------+---------+--------
 eve  | 2500.00 | eve    | ada     | cy
 cy   | 2900.00 | eve    | ada     | cy
 ben  | 3100.00 | eve    | ada     | cy
 dee  | 4800.00 | eve    | ada     | cy
 ada  | 5200.00 | eve    | ada     | cy
(5 rows)
```

### F. ROWS, GROUPS and RANGE

With the values 1, 2, 2 and 4, the three kinds of frame of "one before to the current row" differ.

<!-- example: postgresql -->
```sql
SELECT x,
       sum(x) OVER (ORDER BY x ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) AS rows_,
       sum(x) OVER (ORDER BY x GROUPS BETWEEN 1 PRECEDING AND CURRENT ROW) AS groups_,
       sum(x) OVER (ORDER BY x RANGE BETWEEN 1 PRECEDING AND CURRENT ROW) AS range_
FROM (VALUES (1), (2), (2), (4)) AS v(x)
ORDER BY x;
```

```text
 x | rows_ | groups_ | range_
---+-------+---------+--------
 1 |     1 |       1 |      1
 2 |     3 |       5 |      5
 2 |     4 |       5 |      5
 4 |     6 |       8 |      4
(4 rows)
```

### G. RANGE with an interval

The total of the salaries of the people hired in the two years up to each one.

<!-- example: postgresql -->
```sql
SELECT name, hired,
       sum(salary) OVER (ORDER BY hired RANGE BETWEEN INTERVAL '2 years' PRECEDING AND CURRENT ROW) AS two_years
FROM emp
ORDER BY hired;
```

```text
 name |   hired    | two_years
------+------------+-----------
 dee  | 2019-11-30 |   4800.00
 ada  | 2020-03-01 |  10000.00
 ben  | 2021-07-15 |  13100.00
 cy   | 2022-01-10 |  11200.00
 eve  | 2023-05-02 |   8500.00
(5 rows)
```

### H. EXCLUDE

<!-- example: postgresql -->
```sql
SELECT x,
       sum(x) OVER (ORDER BY x ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING EXCLUDE CURRENT ROW) AS others,
       sum(x) OVER (ORDER BY x ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING EXCLUDE GROUP) AS not_peers,
       sum(x) OVER (ORDER BY x ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING EXCLUDE TIES) AS not_ties
FROM (VALUES (1), (2), (2), (4)) AS v(x)
ORDER BY x;
```

```text
 x | others | not_peers | not_ties
---+--------+-----------+----------
 1 |      8 |         8 |        9
 2 |      7 |         5 |        7
 2 |      7 |         5 |        7
 4 |      5 |         5 |        9
(4 rows)
```

### I. ntile, percent_rank and cume_dist

<!-- example: postgresql -->
```sql
SELECT x, ntile(2) OVER w, dense_rank() OVER w, percent_rank() OVER w, cume_dist() OVER w
FROM (VALUES (1), (2), (2), (4)) AS v(x)
WINDOW w AS (ORDER BY x)
ORDER BY x;
```

```text
 x | ntile | dense_rank |    percent_rank    | cume_dist
---+-------+------------+--------------------+-----------
 1 |     1 |          1 |                  0 |      0.25
 2 |     1 |          2 | 0.3333333333333333 |      0.75
 2 |     2 |          2 | 0.3333333333333333 |      0.75
 4 |     2 |          3 |                  1 |         1
(4 rows)
```

### J. IGNORE NULLS and FILTER

<!-- example: postgresql -->
```sql
SELECT i, x,
       lag(x) OVER (ORDER BY i) AS lag,
       lag(x) IGNORE NULLS OVER (ORDER BY i) AS lag_known,
       count(*) FILTER (WHERE x > 15) OVER (ORDER BY i) AS big_so_far
FROM (VALUES (1, 10), (2, NULL), (3, 30), (4, 20)) AS v(i, x)
ORDER BY i;
```

```text
 i | x  | lag | lag_known | big_so_far
---+----+-----+-----------+------------
 1 | 10 |     |           |          0
 2 |    |  10 |        10 |          0
 3 | 30 |     |        10 |          1
 4 | 20 |  30 |        30 |          2
(4 rows)
```

### K. The top row of each partition

A window function cannot be used in `WHERE`; a subquery filters by it.

<!-- example: postgresql -->
```sql
SELECT name FROM emp WHERE rank() OVER (ORDER BY salary) = 1;
SELECT name, dept_id, salary
FROM (SELECT *, rank() OVER (PARTITION BY dept_id ORDER BY salary DESC) AS r FROM emp) t
WHERE r = 1
ORDER BY name;
```

```text
ERROR:  window functions are not allowed in WHERE
 name | dept_id | salary
------+---------+---------
 ada  |       2 | 5200.00
 ben  |       1 | 3100.00
 eve  |         | 2500.00
(3 rows)
```

### L. Errors

<!-- example: postgresql -->
```sql
SELECT name, rank() OVER w FROM emp;
SELECT count(DISTINCT dept_id) OVER () FROM emp;
SELECT x, sum(x) OVER (ROWS BETWEEN CURRENT ROW AND 1 PRECEDING) FROM (VALUES (1)) v(x);
```

```text
ERROR:  window "w" does not exist
ERROR:  DISTINCT is not implemented for window functions
ERROR:  frame starting from current row cannot have preceding rows
```

## See also

[SELECT](select.md) · [GROUP BY](select-group-by.md) · [WITH](with.md)
