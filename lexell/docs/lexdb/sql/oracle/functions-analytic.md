# Analytic functions

Ranking, offset, distribution and running functions that work over a window of rows.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
function ( [ arguments ] ) [ { RESPECT | IGNORE } NULLS ]
    OVER ( [ PARTITION BY expr [, ...] ] [ ORDER BY expr [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [, ...] ]
           [ { ROWS | RANGE } { frame_start | BETWEEN frame_start AND frame_end } ] )

ROW_NUMBER ( )   RANK ( )   DENSE_RANK ( )   PERCENT_RANK ( )   CUME_DIST ( )
NTILE ( n )
LAG ( expr [, offset [, default ] ] )     LEAD ( expr [, offset [, default ] ] )
FIRST_VALUE ( expr )   LAST_VALUE ( expr )   NTH_VALUE ( expr, n )

aggregate ( ... ) OVER ( ... )            -- COUNT, SUM, AVG, MIN, MAX, STDDEV, VARIANCE, LISTAGG
PERCENTILE_CONT ( fraction ) WITHIN GROUP ( ORDER BY expr ) OVER ( [ PARTITION BY ... ] )
PERCENTILE_DISC ( fraction ) WITHIN GROUP ( ORDER BY expr ) OVER ( [ PARTITION BY ... ] )

frame_start, frame_end: UNBOUNDED PRECEDING | n PRECEDING | CURRENT ROW | n FOLLOWING | UNBOUNDED FOLLOWING
```

## Functions

`ROW_NUMBER`
: The row's position in its partition, 1, 2, 3 ..., in the `ORDER BY` order. Tied rows get different numbers.

`RANK`, `DENSE_RANK`
: The position with ties: tied rows share a rank. `RANK` then skips (1, 1, 3); `DENSE_RANK` does not (1, 1, 2).

`PERCENT_RANK`, `CUME_DIST`
: (rank - 1) / (rows - 1), from 0 to 1; and the share of rows up to and including the row's peers.

`NTILE(n)`
: Splits the partition into *n* groups of nearly equal size and gives the group's number; the first groups get the
  extra rows.

`LAG`, `LEAD`
: The value of *expr* *offset* rows (default 1) before or after the current row, or *default* (NULL if not given)
  when there is no such row. `IGNORE NULLS` skips rows where the value is NULL.

`FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE`
: The value of *expr* in the first, last or *n*th row of the frame. With an `ORDER BY` and no frame the frame ends
  at the current row, so `LAST_VALUE` gives the current row's value: add `ROWS BETWEEN UNBOUNDED PRECEDING AND
  UNBOUNDED FOLLOWING` to see the partition's last. `IGNORE NULLS` skips NULLs.

*aggregates* `OVER`
: With `ORDER BY` and no frame an aggregate is a running total (the frame is `RANGE BETWEEN UNBOUNDED PRECEDING
  AND CURRENT ROW`); without `ORDER BY` it covers the whole partition.

`PERCENTILE_CONT`, `PERCENTILE_DISC`
: The value at *fraction* of the partition's ordered values, repeated on every row.

## Remarks

- An analytic function may appear in the select list and in `ORDER BY`, not in `WHERE`, `GROUP BY` or `HAVING`. To
  filter on a rank, compute it in a subquery first.
- `RANGE` takes the rows whose `ORDER BY` value is in range, so tied rows are in the frame together; `ROWS` counts
  rows.
- `IGNORE NULLS` goes inside the parentheses or after them (`LAG(x IGNORE NULLS)` and `LAG(x) IGNORE NULLS`); both
  work.

## Differences from Oracle

- `RATIO_TO_REPORT` is ORA-00904 and `LISTAGG ... OVER` is ORA-03001.
- `NULLS FIRST` is the default for `DESC` and `NULLS LAST` for `ASC`, as in Oracle (example A: `fay` ranks first).

## Examples

<!--setup: oracle
CREATE TABLE score (player VARCHAR2(10), team VARCHAR2(5), pts NUMBER);
INSERT INTO score VALUES ('ann', 'red', 10);
INSERT INTO score VALUES ('bob', 'red', 20);
INSERT INTO score VALUES ('cy', 'red', 20);
INSERT INTO score VALUES ('di', 'blue', 5);
INSERT INTO score VALUES ('ed', 'blue', 15);
INSERT INTO score VALUES ('fay', 'blue', NULL);
COMMIT;
-->

The examples use a table `score (player, team, pts)`: ann 10, bob 20 and cy 20 in team red; di 5, ed 15 and fay
(NULL) in team blue.

### A. ROW_NUMBER, RANK and DENSE_RANK

<!-- example: oracle -->
```sql
SELECT player, team, pts,
       ROW_NUMBER() OVER (PARTITION BY team ORDER BY pts DESC) AS row_number_,
       RANK() OVER (PARTITION BY team ORDER BY pts DESC) AS rank_,
       DENSE_RANK() OVER (PARTITION BY team ORDER BY pts DESC) AS dense_rank_
FROM score ORDER BY team, row_number_;
```

```text
PLAYER TEAM PTS ROW_NUMBER_ RANK_ DENSE_RANK_
------ ---- --- ----------- ----- -----------
fay    blue               1     1           1
ed     blue  15           2     2           2
di     blue   5           3     3           3
bob    red   20           1     1           1
cy     red   20           2     1           1
ann    red   10           3     3           2

6 rows selected.
```

### B. NTILE, PERCENT_RANK and CUME_DIST

<!-- example: oracle -->
```sql
SELECT player, pts, NTILE(2) OVER (ORDER BY pts DESC) AS half, PERCENT_RANK() OVER (ORDER BY pts) AS percent_rank_,
       CUME_DIST() OVER (ORDER BY pts) AS cume_dist_
FROM score WHERE pts IS NOT NULL ORDER BY pts, player;
```

```text
PLAYER PTS HALF PERCENT_RANK_ CUME_DIST_
------ --- ---- ------------- ----------
di       5    2           0.0        0.2
ann     10    2          0.25        0.4
ed      15    1           0.5        0.6
bob     20    1          0.75        1.0
cy      20    1          0.75        1.0

5 rows selected.
```

### C. LAG and LEAD

<!-- example: oracle -->
```sql
SELECT player, team, pts,
       LAG(pts) OVER (PARTITION BY team ORDER BY player) AS previous,
       LEAD(pts, 1, -1) OVER (PARTITION BY team ORDER BY player) AS next_or_minus_one,
       LAG(pts, 2, 0) OVER (PARTITION BY team ORDER BY player) AS two_back
FROM score ORDER BY team, player;
```

```text
PLAYER TEAM PTS PREVIOUS NEXT_OR_MINUS_ONE TWO_BACK
------ ---- --- -------- ----------------- --------
di     blue   5                         15        0
ed     blue  15        5                          0
fay    blue           15                -1        5
ann    red   10                         20        0
bob    red   20       10                20        0
cy     red   20       20                -1       10

6 rows selected.
```

### D. IGNORE NULLS

<!-- example: oracle -->
```sql
SELECT player, pts, LAG(pts) OVER (ORDER BY player) AS previous,
       LAG(pts) IGNORE NULLS OVER (ORDER BY player) AS previous_not_null,
       LAG(pts IGNORE NULLS) OVER (ORDER BY player) AS inside_brackets
FROM score ORDER BY player;
```

```text
PLAYER PTS PREVIOUS PREVIOUS_NOT_NULL INSIDE_BRACKETS
------ --- -------- ----------------- ---------------
ann     10
bob     20       10                10              10
cy      20       20                20              20
di       5       20                20              20
ed      15        5                 5               5
fay              15                15              15

6 rows selected.
```

### E. FIRST_VALUE, LAST_VALUE and NTH_VALUE

<!-- example: oracle -->
```sql
SELECT player, team, pts,
       FIRST_VALUE(player) OVER (PARTITION BY team ORDER BY pts DESC, player) AS best,
       LAST_VALUE(player) OVER (PARTITION BY team ORDER BY pts DESC, player) AS last_to_here,
       LAST_VALUE(player) OVER (PARTITION BY team ORDER BY pts DESC, player
                                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last_of_team,
       NTH_VALUE(player, 2) OVER (PARTITION BY team ORDER BY pts DESC, player
                                  ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS second
FROM score WHERE pts IS NOT NULL ORDER BY team, pts DESC, player;
```

```text
PLAYER TEAM PTS BEST LAST_TO_HERE LAST_OF_TEAM SECOND
------ ---- --- ---- ------------ ------------ ------
ed     blue  15 ed   ed           di           di
di     blue   5 ed   di           di           di
bob    red   20 bob  bob          ann          cy
cy     red   20 bob  cy           ann          cy
ann    red   10 bob  ann          ann          cy

5 rows selected.
```

### F. Aggregates as analytic functions

<!-- example: oracle -->
```sql
SELECT player, pts, SUM(pts) OVER (ORDER BY player ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running,
       COUNT(pts) OVER (PARTITION BY team) AS team_count,
       ROUND(AVG(pts) OVER (PARTITION BY team), 2) AS team_avg,
       MAX(pts) OVER (PARTITION BY team ORDER BY player ROWS BETWEEN 1 PRECEDING AND CURRENT ROW) AS max_of_two
FROM score ORDER BY player;
```

```text
PLAYER PTS RUNNING TEAM_COUNT TEAM_AVG MAX_OF_TWO
------ --- ------- ---------- -------- ----------
ann     10      10          3    16.67         10
bob     20      30          3    16.67         20
cy      20      50          3    16.67         20
di       5      55          2       10          5
ed      15      70          2       10         15
fay             70          2       10         15

6 rows selected.
```

### G. Percentiles

<!-- example: oracle -->
```sql
SELECT DISTINCT team,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pts) OVER (PARTITION BY team) AS median_cont,
       PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY pts) OVER (PARTITION BY team) AS median_disc
FROM score ORDER BY team;
```

```text
TEAM MEDIAN_CONT MEDIAN_DISC
---- ----------- -----------
blue          10           5
red           20          20

2 rows selected.
```

### H. Filtering on a rank

<!-- example: oracle -->
```sql
SELECT player, team, pts
FROM (SELECT player, team, pts, ROW_NUMBER() OVER (PARTITION BY team ORDER BY pts DESC, player) AS n
      FROM score WHERE pts IS NOT NULL)
WHERE n = 1 ORDER BY team;
SELECT player FROM score WHERE ROW_NUMBER() OVER (ORDER BY pts) = 1;
```

```text
PLAYER TEAM PTS
------ ---- ---
ed     blue  15
bob    red   20

2 rows selected.

ERROR:
ORA-20000: window functions are not allowed in WHERE
```

### I. Functions that are not available

<!-- example: oracle -->
```sql
SELECT RATIO_TO_REPORT(pts) OVER () FROM score;
SELECT LISTAGG(player, ',') WITHIN GROUP (ORDER BY player) OVER (PARTITION BY team) FROM score;
```

```text
ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-03001: unimplemented feature: aggregate ORDER BY is not implemented for window functions
```

## See also

[Aggregate functions](functions-aggregate.md), [SELECT](select.md), [QUALIFY](qualify.md) (a filter on window results)
