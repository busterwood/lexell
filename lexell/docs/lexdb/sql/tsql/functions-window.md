# Window functions (Transact-SQL)

Ranking, offset, distribution and percentile functions that work over a window of rows.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
ROW_NUMBER ( ) OVER ( [ PARTITION BY ... ] ORDER BY ... )
RANK ( ) OVER ( [ PARTITION BY ... ] ORDER BY ... )
DENSE_RANK ( ) OVER ( [ PARTITION BY ... ] ORDER BY ... )
NTILE ( n ) OVER ( [ PARTITION BY ... ] ORDER BY ... )
PERCENT_RANK ( ) OVER ( [ PARTITION BY ... ] ORDER BY ... )
CUME_DIST ( ) OVER ( [ PARTITION BY ... ] ORDER BY ... )
LAG ( expression [, offset [, default ] ] ) [ IGNORE NULLS | RESPECT NULLS ] OVER ( [ PARTITION BY ... ] ORDER BY ... )
LEAD ( expression [, offset [, default ] ] ) [ IGNORE NULLS | RESPECT NULLS ] OVER ( [ PARTITION BY ... ] ORDER BY ... )
FIRST_VALUE ( expression ) [ IGNORE NULLS | RESPECT NULLS ] OVER ( ... [ frame ] )
NTH_VALUE ( expression, n ) [ IGNORE NULLS | RESPECT NULLS ] OVER ( ... [ frame ] )   -- lexdb's own
LAST_VALUE ( expression ) [ IGNORE NULLS | RESPECT NULLS ] OVER ( ... [ frame ] )
PERCENTILE_CONT ( fraction ) WITHIN GROUP ( ORDER BY expression ) OVER ( [ PARTITION BY ... ] )
PERCENTILE_DISC ( fraction ) WITHIN GROUP ( ORDER BY expression ) OVER ( [ PARTITION BY ... ] )
```

The clause after `OVER` is explained on the [OVER](over.md) page. The aggregates (`SUM`, `COUNT`, `MIN`, `MAX`,
`STRING_AGG`) also take `OVER`: see [aggregate functions](functions-aggregate.md).

## Functions

`ROW_NUMBER`
: The row's position in its partition, 1, 2, 3 ..., in the `ORDER BY` order. Tied rows get different numbers.

`RANK`, `DENSE_RANK`
: The position with ties: tied rows share a rank. `RANK` then skips (1, 1, 3); `DENSE_RANK` does not (1, 1, 2).

`NTILE(n)`
: Splits the partition into *n* groups of nearly equal size and gives the group's number. The first groups get
  the extra rows. *n* must be positive (error 4116).

`PERCENT_RANK`
: (rank - 1) / (rows - 1), from 0 to 1; 0 for a partition of one row.

`CUME_DIST`
: The share of rows up to and including the row's peers: the highest tie of the row's value divided by the number
  of rows.

`LAG`, `LEAD`
: The value of *expression* *offset* rows (default 1) before or after the current row in the order, or *default*
  (NULL if not given) when there is no such row. `IGNORE NULLS` skips rows where the value is NULL.

`FIRST_VALUE`, `LAST_VALUE`
: The value of *expression* in the first or last row of the frame. With an `ORDER BY` and no frame the frame ends at
  the current row, so `LAST_VALUE` gives the current row's own value (or its last peer's): add `ROWS BETWEEN
  UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING` to see the partition's last. `IGNORE NULLS` skips NULLs.

`NTH_VALUE`
: The value of *expression* in the *n*th row of the frame, NULL when the frame has fewer rows. SQL Server has no
  `NTH_VALUE`; lexdb takes it as Oracle and PostgreSQL do.

`PERCENTILE_CONT`, `PERCENTILE_DISC`
: The value at *fraction* (0 to 1) of the values in the partition, ordered by the `WITHIN GROUP` expression:
  `PERCENTILE_CONT` interpolates between values, `PERCENTILE_DISC` takes one of them. They need `OVER`; the
  `OVER` clause has `PARTITION BY` and no `ORDER BY`, and the result is repeated on every row.

## Remarks

- A window function may appear in the select list and in `ORDER BY`, not in `WHERE`, `GROUP BY` or `HAVING`. To
  filter on a rank, compute it in a derived table or a common table expression first.
- The ranking functions and `LAG` and `LEAD` need `ORDER BY` in `OVER`.
- NULLs sort first in ascending order.

## Differences from SQL Server

- `ROW_NUMBER() OVER ()` and the other ranking functions without `ORDER BY` are taken (SQL Server: error 4112).
- `NTH_VALUE` is lexdb's addition: SQL Server has none.
- `COUNT_BIG(*) OVER` is error 195; `AVG` with `OVER` fails (see [OVER](over.md)).
- `LAST_VALUE`, `FIRST_VALUE`, `LAG` and `LEAD` take `IGNORE NULLS` and `RESPECT NULLS` as SQL Server 2022 does.

## Examples

<!--setup: tsql
CREATE TABLE dbo.score (player varchar(10), team varchar(5), pts int);
INSERT INTO dbo.score VALUES ('ann', 'red', 10), ('bob', 'red', 20), ('cy', 'red', 20), ('di', 'blue', 5), ('ed', 'blue', 15), ('fay', 'blue', NULL);
-->

The examples use one table:

```sql
CREATE TABLE dbo.score (player varchar(10), team varchar(5), pts int);
INSERT INTO dbo.score VALUES ('ann', 'red', 10), ('bob', 'red', 20), ('cy', 'red', 20), ('di', 'blue', 5),
                             ('ed', 'blue', 15), ('fay', 'blue', NULL);
```

### A. ROW_NUMBER, RANK and DENSE_RANK

<!-- example: tsql -->
```sql
SELECT player, team, pts,
       ROW_NUMBER() OVER (PARTITION BY team ORDER BY pts DESC) AS row_number_,
       RANK() OVER (PARTITION BY team ORDER BY pts DESC) AS rank_,
       DENSE_RANK() OVER (PARTITION BY team ORDER BY pts DESC) AS dense_rank_
FROM dbo.score ORDER BY team, row_number_;
```

```text
player team pts  row_number_ rank_ dense_rank_
------ ---- ---- ----------- ----- -----------
ed     blue 15   1           1     1
di     blue 5    2           2     2
fay    blue NULL 3           3     3
bob    red  20   1           1     1
cy     red  20   2           1     1
ann    red  10   3           3     2

(6 rows affected)
```

### B. NTILE

<!-- example: tsql -->
```sql
SELECT player, pts, NTILE(2) OVER (ORDER BY pts DESC) AS half, NTILE(4) OVER (ORDER BY pts DESC) AS quarter
FROM dbo.score WHERE pts IS NOT NULL ORDER BY pts DESC, player;
GO
SELECT NTILE(0) OVER (ORDER BY pts) FROM dbo.score;
```

```text
player pts half quarter
------ --- ---- -------
bob    20  1    1
cy     20  1    1
ed     15  1    2
ann    10  2    3
di     5   2    4

(5 rows affected)

Msg 4116, Level 16, State 1, Line 1
argument of ntile must be greater than zero
```

### C. PERCENT_RANK and CUME_DIST

<!-- example: tsql -->
```sql
SELECT player, pts, PERCENT_RANK() OVER (ORDER BY pts) AS percent_rank_, CUME_DIST() OVER (ORDER BY pts) AS cume_dist_
FROM dbo.score WHERE pts IS NOT NULL ORDER BY pts, player;
```

```text
player pts percent_rank_ cume_dist_
------ --- ------------- ----------
di     5   0.0           0.2
ann    10  0.25          0.4
ed     15  0.5           0.6
bob    20  0.75          1.0
cy     20  0.75          1.0

(5 rows affected)
```

### D. LAG and LEAD

<!-- example: tsql -->
```sql
SELECT player, team, pts,
       LAG(pts) OVER (PARTITION BY team ORDER BY player) AS previous,
       LEAD(pts, 1, -1) OVER (PARTITION BY team ORDER BY player) AS next_or_minus_one,
       LAG(pts, 2, 0) OVER (PARTITION BY team ORDER BY player) AS two_back
FROM dbo.score ORDER BY team, player;
```

```text
player team pts  previous next_or_minus_one two_back
------ ---- ---- -------- ----------------- --------
di     blue 5    NULL     15                0
ed     blue 15   5        NULL              0
fay    blue NULL 15       -1                5
ann    red  10   NULL     20                0
bob    red  20   10       20                0
cy     red  20   20       -1                10

(6 rows affected)
```

### E. IGNORE NULLS

<!-- example: tsql -->
```sql
SELECT player, pts,
       LAG(pts) OVER (ORDER BY player) AS previous,
       LAG(pts) IGNORE NULLS OVER (ORDER BY player) AS previous_not_null
FROM dbo.score ORDER BY player;
```

```text
player pts  previous previous_not_null
------ ---- -------- -----------------
ann    10   NULL     NULL
bob    20   10       10
cy     20   20       20
di     5    20       20
ed     15   5        5
fay    NULL 15       15

(6 rows affected)
```

### F. FIRST_VALUE and LAST_VALUE

<!-- example: tsql -->
```sql
SELECT player, team, pts,
       FIRST_VALUE(player) OVER (PARTITION BY team ORDER BY pts DESC, player) AS best,
       LAST_VALUE(player) OVER (PARTITION BY team ORDER BY pts DESC, player) AS last_to_here,
       LAST_VALUE(player) OVER (PARTITION BY team ORDER BY pts DESC, player
                                ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS last_of_team
FROM dbo.score WHERE pts IS NOT NULL ORDER BY team, pts DESC, player;
```

```text
player team pts best last_to_here last_of_team
------ ---- --- ---- ------------ ------------
ed     blue 15  ed   ed           di
di     blue 5   ed   di           di
bob    red  20  bob  bob          ann
cy     red  20  bob  cy           ann
ann    red  10  bob  ann          ann

(5 rows affected)
```

### G. PERCENTILE_CONT and PERCENTILE_DISC

<!-- example: tsql -->
```sql
SELECT DISTINCT team,
       PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY pts) OVER (PARTITION BY team) AS median_cont,
       PERCENTILE_DISC(0.5) WITHIN GROUP (ORDER BY pts) OVER (PARTITION BY team) AS median_disc
FROM dbo.score ORDER BY team;
```

```text
team median_cont median_disc
---- ----------- -----------
blue 10.0        5
red  20.0        20

(2 rows affected)
```

### H. An aggregate as a window: running total

<!-- example: tsql -->
```sql
SELECT player, pts, SUM(pts) OVER (ORDER BY player ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW) AS running,
       COUNT(pts) OVER (PARTITION BY team) AS team_count
FROM dbo.score ORDER BY player;
```

```text
player pts  running team_count
------ ---- ------- ----------
ann    10   10      3
bob    20   30      3
cy     20   50      3
di     5    55      2
ed     15   70      2
fay    NULL 70      2

(6 rows affected)
```

### I. Filtering on a rank

<!-- example: tsql -->
```sql
SELECT player, team, pts
FROM (SELECT player, team, pts, ROW_NUMBER() OVER (PARTITION BY team ORDER BY pts DESC, player) AS n
      FROM dbo.score WHERE pts IS NOT NULL) ranked
WHERE n = 1 ORDER BY team;
GO
SELECT player FROM dbo.score WHERE ROW_NUMBER() OVER (ORDER BY pts) = 1;
```

```text
player team pts
------ ---- ---
ed     blue 15
bob    red  20

(2 rows affected)

Msg 50000, Level 16, State 1, Line 1
window functions are not allowed in WHERE
```

### J. NTH_VALUE

<!-- example: tsql -->
```sql
SELECT player, pts, NTH_VALUE(pts, 2) OVER (ORDER BY player) AS second_so_far,
       NTH_VALUE(pts, 2) OVER (ORDER BY player ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING) AS second
FROM dbo.score ORDER BY player;
```

```text
player pts  second_so_far second
------ ---- ------------- ------
ann    10   NULL          20
bob    20   20            20
cy     20   20            20
di     5    20            20
ed     15   20            20
fay    NULL 20            20

(6 rows affected)
```

## See also

[OVER](over.md), [Aggregate functions](functions-aggregate.md), [SELECT](select.md), [ORDER BY](order-by.md)
