# Window functions

The functions that work only with `OVER`: ranking, offsets and values from the window's frame.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18 (and 19's `IGNORE NULLS`).

## Syntax

```
row_number ( ) → bigint
rank ( ) → bigint
dense_rank ( ) → bigint
percent_rank ( ) → double precision
cume_dist ( ) → double precision
ntile ( buckets ) → integer
lag ( value [, offset [, default ] ] ) [ { RESPECT | IGNORE } NULLS ] → type of value
lead ( value [, offset [, default ] ] ) [ { RESPECT | IGNORE } NULLS ] → type of value
first_value ( value ) [ { RESPECT | IGNORE } NULLS ] → type of value
last_value ( value ) [ { RESPECT | IGNORE } NULLS ] → type of value
nth_value ( value, n ) [ { RESPECT | IGNORE } NULLS ] → type of value

function ( ... ) OVER ( [ PARTITION BY ... ] [ ORDER BY ... ] [ frame_clause ] )
```

The `OVER` clause, frames and named windows are on the [OVER](over.md) page.

## Functions

`row_number`
: The row's number in its partition, from 1, in the window's order.

`rank`
: The row's rank, with gaps: rows that tie take the same rank, and the next rank skips.

`dense_rank`
: The rank without gaps.

`percent_rank`
: (`rank` - 1) / (rows in the partition - 1), from 0 to 1; 0 for a partition of one row.

`cume_dist`
: The fraction of the partition's rows that come before the row or tie with it.

`ntile`
: Which of *buckets* parts, as equal as can be, the row falls in, from 1.

`lag`, `lead`
: *value* from the row *offset* rows before or after (1 by default), or *default* (NULL by default) past the
  partition's edge. With `IGNORE NULLS`, rows where *value* is NULL are not counted.

`first_value`, `last_value`
: *value* at the first or last row of the frame. With the default frame, the frame ends at the current row (and
  its ties), so `last_value` needs a frame to the partition's end.

`nth_value`
: *value* at the *n*th row of the frame, or NULL if the frame is shorter.

## Remarks

- Every [aggregate function](functions-aggregate.md) is a window function with `OVER` too.
- Window functions are computed after `WHERE`, `GROUP BY` and `HAVING`; to filter on one, put the query in a
  subquery.

## Differences from PostgreSQL

- `IGNORE NULLS` is PostgreSQL 19's; PostgreSQL 18 refuses it.
- A window function in a query with `ROLLUP`, `CUBE` or `GROUPING SETS` is refused (0A000, lexdb-gaps.md 2.2).

## Examples

<!--setup: postgresql
CREATE TABLE score (player text, team text, points int);
INSERT INTO score VALUES ('ann', 'red', 30), ('bob', 'red', 20), ('cy', 'red', 20), ('dee', 'red', 10),
  ('eve', 'blue', 25), ('fay', 'blue', NULL), ('gus', 'blue', 15);
-->

The examples use this table:

```sql
CREATE TABLE score (player text, team text, points int);
INSERT INTO score VALUES ('ann', 'red', 30), ('bob', 'red', 20), ('cy', 'red', 20), ('dee', 'red', 10),
  ('eve', 'blue', 25), ('fay', 'blue', NULL), ('gus', 'blue', 15);
```

### A. row_number, rank and dense_rank

<!-- example: postgresql -->
```sql
SELECT player, points, row_number() OVER w AS row_number, rank() OVER w AS rank, dense_rank() OVER w AS dense_rank
FROM score WHERE team = 'red' WINDOW w AS (ORDER BY points DESC) ORDER BY points DESC, player;
```

```text
 player | points | row_number | rank | dense_rank
--------+--------+------------+------+------------
 ann    |     30 |          1 |    1 |          1
 bob    |     20 |          2 |    2 |          2
 cy     |     20 |          3 |    2 |          2
 dee    |     10 |          4 |    4 |          3
(4 rows)
```

### B. percent_rank, cume_dist and ntile

<!-- example: postgresql -->
```sql
SELECT player, points, round(percent_rank() OVER w::numeric, 3) AS pct_rank,
       round(cume_dist() OVER w::numeric, 3) AS cume_dist, ntile(3) OVER w AS ntile
FROM score WHERE team = 'red' WINDOW w AS (ORDER BY points DESC) ORDER BY points DESC, player;
```

```text
 player | points | pct_rank | cume_dist | ntile
--------+--------+----------+-----------+-------
 ann    |     30 |    0.000 |     0.250 |     1
 bob    |     20 |    0.333 |     0.750 |     1
 cy     |     20 |    0.333 |     0.750 |     2
 dee    |     10 |    1.000 |     1.000 |     3
(4 rows)
```

### C. lag and lead

<!-- example: postgresql -->
```sql
SELECT player, points, lag(points) OVER w AS prev, lead(points, 1, 0) OVER w AS next,
       points - lag(points) OVER w AS change
FROM score WHERE team = 'red' WINDOW w AS (ORDER BY player) ORDER BY player;
```

```text
 player | points | prev | next | change
--------+--------+------+------+--------
 ann    |     30 |      |   20 |
 bob    |     20 |   30 |   20 |    -10
 cy     |     20 |   20 |   10 |      0
 dee    |     10 |   20 |    0 |    -10
(4 rows)
```

### D. first_value, last_value and nth_value

<!-- example: postgresql -->
```sql
SELECT team, player, points,
       first_value(player) OVER w AS top,
       last_value(player) OVER w AS bottom,
       nth_value(player, 2) OVER w AS second
FROM score WHERE points IS NOT NULL
WINDOW w AS (PARTITION BY team ORDER BY points DESC, player ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING)
ORDER BY team, points DESC, player;
```

```text
 team | player | points | top | bottom | second
------+--------+--------+-----+--------+--------
 blue | eve    |     25 | eve | gus    | gus
 blue | gus    |     15 | eve | gus    | gus
 red  | ann    |     30 | ann | dee    | bob
 red  | bob    |     20 | ann | dee    | bob
 red  | cy     |     20 | ann | dee    | bob
 red  | dee    |     10 | ann | dee    | bob
(6 rows)
```

### E. IGNORE NULLS

<!-- example: postgresql -->
```sql
SELECT player, points, lag(points) OVER w AS prev, lag(points) IGNORE NULLS OVER w AS prev_known
FROM score WHERE team = 'blue' WINDOW w AS (ORDER BY player) ORDER BY player;
```

```text
 player | points | prev | prev_known
--------+--------+------+------------
 eve    |     25 |      |
 fay    |        |   25 |         25
 gus    |     15 |      |         25
(3 rows)
```

### F. Top two of each team

<!-- example: postgresql -->
```sql
SELECT team, player, points FROM (
  SELECT team, player, points, row_number() OVER (PARTITION BY team ORDER BY points DESC NULLS LAST, player) AS n
  FROM score) t
WHERE n <= 2 ORDER BY team, n;
```

```text
 team | player | points
------+--------+--------
 blue | eve    |     25
 blue | gus    |     15
 red  | ann    |     30
 red  | bob    |     20
(4 rows)
```

### G. Errors

<!-- example: postgresql -->
```sql
SELECT row_number() FROM score;
SELECT player FROM score WHERE rank() OVER (ORDER BY points) = 1;
```

```text
ERROR:  window function row_number requires an OVER clause
ERROR:  window functions are not allowed in WHERE
```

## See also

[OVER](over.md) · [Aggregate functions](functions-aggregate.md) · [SELECT](select.md)
