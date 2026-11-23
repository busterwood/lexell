# MATCH_RECOGNIZE

Finds sequences of rows that match a pattern, in the `FROM` clause of a [SELECT](select.md).

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai (row pattern matching, SQL:2016 R010).

## Syntax

```
table_or_subquery MATCH_RECOGNIZE (
    [ PARTITION BY column [, ...] ]
    [ ORDER BY expression [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [, ...] ]
    [ MEASURES expression AS alias [, ...] ]
    [ ONE ROW PER MATCH
    | ALL ROWS PER MATCH [ SHOW EMPTY MATCHES | OMIT EMPTY MATCHES | WITH UNMATCHED ROWS ] ]
    [ AFTER MATCH SKIP { PAST LAST ROW | TO NEXT ROW | TO [ FIRST | LAST ] variable } ]
    PATTERN ( pattern )
    [ SUBSET name = ( variable [, ...] ) [, ...] ]
    DEFINE variable AS condition [, ...]
) [ alias ]

pattern:
    term [ term ... ] [ | pattern ]

term:
    { variable | ^ | $ | ( pattern ) | {- pattern -} | PERMUTE ( pattern [, ...] ) } [ quantifier ]

quantifier:
    { * | + | {n} | {n,} | {,m} | {n,m} }
```

## Arguments

*table_or_subquery*
: A table, a view or an inline view: the rows to search.

`PARTITION BY` *column*
: Searches each partition on its own.

`ORDER BY`
: The order of the rows within a partition. Without it, the rows are taken as they come.

`MEASURES` *expression* `AS` *alias*
: The columns a match gives. Each needs an alias. A measure may use:
  - columns, plain or qualified by a pattern variable (`strt.day`: the row mapped to `strt`);
  - `PREV(x [, n])` and `NEXT(x [, n])`: the value *n* rows (1 by default) before or after;
  - `FIRST(x [, n])` and `LAST(x [, n])`: the value at the first or last row mapped (to a variable, when `x` is
    qualified by one);
  - `COUNT`, `SUM`, `AVG`, `MIN` and `MAX` over the rows mapped (`COUNT(*)`, `SUM(up.price)`);
  - `CLASSIFIER()`: the variable the row is mapped to; `MATCH_NUMBER()`: the match's number in its partition, from 1;
  - `RUNNING` or `FINAL` before a navigation or aggregate: the value as of the current row, or at the end of the
    match. `RUNNING` is the default, and with `ONE ROW PER MATCH` both are the end.

`ONE ROW PER MATCH`
: The default: one row for each match, with the `PARTITION BY` columns and the measures.

`ALL ROWS PER MATCH`
: One row for each row of each match: the `PARTITION BY` and `ORDER BY` columns, the measures, then the input's
  other columns. `SHOW EMPTY MATCHES` (the default) gives a row for an empty match, `OMIT EMPTY MATCHES` does not,
  and `WITH UNMATCHED ROWS` adds the rows in no match, with NULL measures.

`AFTER MATCH SKIP`
: Where the next search starts: `PAST LAST ROW` (the default) after the match; `TO NEXT ROW` at the row after the
  match's first; `TO FIRST v` or `TO LAST v` at the first or last row mapped to `v` (`TO v` is `TO LAST v`).

`PATTERN (` *pattern* `)`
: A regular expression over the variables. Terms in a row follow each other; `|` is either; `^` and `$` are the
  partition's start and end; `{- ... -}` matches but leaves its rows out of `ALL ROWS PER MATCH`; `PERMUTE (a, b)`
  is the variables in any order. Quantifiers are greedy.

`SUBSET` *name* `= (` *variables* `)`
: A name for a union of variables, usable in `MEASURES` and `DEFINE` (`FIRST(ab.day)`).

`DEFINE` *variable* `AS` *condition*
: When a row may be mapped to the variable. A condition may use the same navigation and aggregates as `MEASURES`.
  A variable in `PATTERN` without a definition matches any row.

*alias*
: The name of the result. The input's own alias is not visible outside the clause.

## Remarks

- The search tries the pattern at each row in turn, and takes the first match in the pattern's order of
  preference: a greedy quantifier tries more rows first, and `|` its left side first.
- Names are folded to upper case as elsewhere in this door: `CLASSIFIER()` gives `UP`, not `up`.
- A statement is refused when a `DEFINE` names a variable that is not in the pattern (ORA-62503), when a
  `MEASURES` expression has no alias (ORA-02000), and when an aggregate other than the five above is used
  (ORA-62512).
- The clause may be used in a view.

## Differences from Oracle

- Reluctant quantifiers (`+?`, `*?`) are not available: the `?` is read as a bind placeholder and the statement is
  ORA-00931. The `?` quantifier by itself (`b?`) is not read either; write `b{0,1}`.
- `ORDER BY` takes expressions; Oracle takes columns only. Subqueries in `MEASURES` and `DEFINE` are refused
  (ORA-03001, "intended feature is not enabled"), and so are aggregates with `DISTINCT` and the aggregates other
  than `COUNT`, `SUM`, `AVG`, `MIN`, `MAX` (ORA-62512; Oracle has the same limit for many of them).
- An empty pattern `()`, an empty alternative, and a group that can match nothing repeated (`(a*)*`) are refused.
- The window form of row pattern recognition (R020) is not supported.

## Examples

<!--setup: oracle
CREATE TABLE ticker (symbol VARCHAR2(10), day NUMBER(3), price NUMBER(6));
INSERT INTO ticker VALUES ('ACME', 1, 12);
INSERT INTO ticker VALUES ('ACME', 2, 17);
INSERT INTO ticker VALUES ('ACME', 3, 19);
INSERT INTO ticker VALUES ('ACME', 4, 21);
INSERT INTO ticker VALUES ('ACME', 5, 25);
INSERT INTO ticker VALUES ('ACME', 6, 12);
INSERT INTO ticker VALUES ('ACME', 7, 15);
INSERT INTO ticker VALUES ('ACME', 8, 20);
INSERT INTO ticker VALUES ('ACME', 9, 24);
INSERT INTO ticker VALUES ('ACME', 10, 25);
INSERT INTO ticker VALUES ('ACME', 11, 19);
INSERT INTO ticker VALUES ('ACME', 12, 15);
INSERT INTO ticker VALUES ('ACME', 13, 25);
INSERT INTO ticker VALUES ('ZED', 1, 8);
INSERT INTO ticker VALUES ('ZED', 2, 7);
INSERT INTO ticker VALUES ('ZED', 3, 5);
INSERT INTO ticker VALUES ('ZED', 4, 6);
INSERT INTO ticker VALUES ('ZED', 5, 9);
COMMIT;
-->

The examples use one table of prices: ACME for 13 days, ZED for 5.

```sql
CREATE TABLE ticker (symbol VARCHAR2(10), day NUMBER(3), price NUMBER(6));
INSERT INTO ticker VALUES ('ACME', 1, 12);
INSERT INTO ticker VALUES ('ACME', 2, 17);
INSERT INTO ticker VALUES ('ACME', 3, 19);
INSERT INTO ticker VALUES ('ACME', 4, 21);
INSERT INTO ticker VALUES ('ACME', 5, 25);
INSERT INTO ticker VALUES ('ACME', 6, 12);
INSERT INTO ticker VALUES ('ACME', 7, 15);
INSERT INTO ticker VALUES ('ACME', 8, 20);
INSERT INTO ticker VALUES ('ACME', 9, 24);
INSERT INTO ticker VALUES ('ACME', 10, 25);
INSERT INTO ticker VALUES ('ACME', 11, 19);
INSERT INTO ticker VALUES ('ACME', 12, 15);
INSERT INTO ticker VALUES ('ACME', 13, 25);
INSERT INTO ticker VALUES ('ZED', 1, 8);
INSERT INTO ticker VALUES ('ZED', 2, 7);
INSERT INTO ticker VALUES ('ZED', 3, 5);
INSERT INTO ticker VALUES ('ZED', 4, 6);
INSERT INTO ticker VALUES ('ZED', 5, 9);
```

### A. V shapes

A fall followed by a rise, in each symbol. `SKIP TO LAST up` lets the top of one V start the next.

<!-- example: oracle -->
```sql
SELECT *
FROM ticker MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY day
    MEASURES strt.day AS start_day, LAST(down.day) AS bottom_day, LAST(up.day) AS end_day
    ONE ROW PER MATCH
    AFTER MATCH SKIP TO LAST up
    PATTERN (strt down+ up+)
    DEFINE down AS price < PREV(price), up AS price > PREV(price)
) v
ORDER BY symbol, start_day;
```

```text
SYMBOL START_DAY BOTTOM_DAY END_DAY
------ --------- ---------- -------
ACME           5          6      10
ACME          10         12      13
ZED            1          3       5

3 rows selected.
```

### B. ALL ROWS PER MATCH

Each row of each rising run of three or more days, with its variable and its place in the run.

<!-- example: oracle -->
```sql
SELECT symbol, day, price, m, cls, n
FROM ticker MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY day
    MEASURES MATCH_NUMBER() AS m, CLASSIFIER() AS cls, RUNNING COUNT(*) AS n
    ALL ROWS PER MATCH
    PATTERN (strt up{2,})
    DEFINE up AS price > PREV(price)
) r
ORDER BY symbol, day;
```

```text
SYMBOL DAY PRICE M CLS  N
------ --- ----- - ---- -
ACME     1    12 1 STRT 1
ACME     2    17 1 UP   2
ACME     3    19 1 UP   3
ACME     4    21 1 UP   4
ACME     5    25 1 UP   5
ACME     6    12 2 STRT 1
ACME     7    15 2 UP   2
ACME     8    20 2 UP   3
ACME     9    24 2 UP   4
ACME    10    25 2 UP   5
ZED      3     5 1 STRT 1
ZED      4     6 1 UP   2
ZED      5     9 1 UP   3

13 rows selected.
```

### C. Runs, with aggregates

<!-- example: oracle -->
```sql
SELECT *
FROM ticker MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY day
    MEASURES FIRST(day) AS first_day, LAST(day) AS last_day, COUNT(*) AS days, MAX(price) AS top
    PATTERN (a b+)
    DEFINE b AS price > PREV(price)
) r
ORDER BY symbol, first_day;
```

```text
SYMBOL FIRST_DAY LAST_DAY DAYS TOP
------ --------- -------- ---- ---
ACME           1        5    5  25
ACME           6       10    5  25
ACME          12       13    2  25
ZED            3        5    3   9

4 rows selected.
```

### D. Islands of consecutive numbers

<!-- example: oracle -->
```sql
SELECT *
FROM (SELECT 1 AS n FROM dual UNION ALL SELECT 2 FROM dual UNION ALL SELECT 3 FROM dual
      UNION ALL SELECT 5 FROM dual UNION ALL SELECT 6 FROM dual UNION ALL SELECT 9 FROM dual)
MATCH_RECOGNIZE (
    ORDER BY n
    MEASURES FIRST(n) AS low, LAST(n) AS high
    PATTERN (a b*)
    DEFINE b AS n = PREV(n) + 1
) r
ORDER BY low;
```

```text
LOW HIGH
--- ----
  1    3
  5    6
  9    9

3 rows selected.
```

### E. Alternatives, anchors, exclusions and PERMUTE

<!-- example: oracle -->
```sql
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES COUNT(*) AS n, FIRST(day) AS d1
  PATTERN (a b+ | c)
  DEFINE b AS price > PREV(price), c AS price < 8) m
ORDER BY symbol, d1;
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES FIRST(day) AS d1, LAST(day) AS d2
  PATTERN (^ a+ $)
  DEFINE a AS price > 0) m
ORDER BY symbol;
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES FIRST(day) AS d1, LAST(day) AS d2
  PATTERN (a {- b -} c)
  DEFINE b AS price > PREV(price), c AS price < PREV(price)) m
ORDER BY symbol, d1;
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES FIRST(day) AS d1, LAST(day) AS d2
  PATTERN (PERMUTE(a, b))
  DEFINE a AS price > PREV(price), b AS price < PREV(price)) m
ORDER BY symbol, d1;
```

```text
SYMBOL N D1
------ - --
ACME   5  1
ACME   5  6
ACME   2 12
ZED    1  2
ZED    3  3

5 rows selected.

SYMBOL D1 D2
------ -- --
ACME    1 13
ZED     1  5

2 rows selected.

SYMBOL D1 D2
------ -- --
ACME    4  6
ACME    9 11

2 rows selected.

SYMBOL D1 D2
------ -- --
ACME    5  6
ACME   10 11
ACME   12 13
ZED     3  4

4 rows selected.
```

### F. SKIP, SUBSET, and empty and unmatched rows

<!-- example: oracle -->
```sql
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES FIRST(up.day) AS first_up, LAST(up.day) AS last_up
  AFTER MATCH SKIP TO NEXT ROW
  PATTERN (strt up+)
  DEFINE up AS price > PREV(price)) m
WHERE symbol = 'ZED'
ORDER BY first_up;
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES FIRST(ab.day) AS d1, LAST(ab.day) AS d2
  PATTERN (a b)
  SUBSET ab = (a, b)
  DEFINE b AS price > PREV(price)) m
WHERE symbol = 'ZED'
ORDER BY d1;
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES MATCH_NUMBER() AS mn, CLASSIFIER() AS cls
  ALL ROWS PER MATCH WITH UNMATCHED ROWS
  PATTERN (up+)
  DEFINE up AS price > PREV(price)) m
WHERE symbol = 'ZED'
ORDER BY day;
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES COUNT(*) AS n
  PATTERN (a*)
  DEFINE a AS price > 100) m
WHERE symbol = 'ZED'
ORDER BY symbol;
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES COUNT(*) AS n
  ALL ROWS PER MATCH OMIT EMPTY MATCHES
  PATTERN (a*)
  DEFINE a AS price > 100) m;
```

```text
SYMBOL FIRST_UP LAST_UP
------ -------- -------
ZED           4       5
ZED           5       5

2 rows selected.

SYMBOL D1 D2
------ -- --
ZED     3  4

1 row selected.

SYMBOL DAY MN CLS PRICE
------ --- -- --- -----
ZED      1            8
ZED      2            7
ZED      3            5
ZED      4  1 UP      6
ZED      5  1 UP      9

5 rows selected.

SYMBOL N
------ -
ZED    0
ZED    0
ZED    0
ZED    0
ZED    0

5 rows selected.

no rows selected
```

### G. FINAL and RUNNING

<!-- example: oracle -->
```sql
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES FINAL COUNT(*) AS cnt, FINAL LAST(price) AS last_price, FIRST(price) AS first_price, RUNNING COUNT(*) AS so_far
  ALL ROWS PER MATCH
  PATTERN (a b)
  DEFINE b AS price < PREV(price)) m
ORDER BY symbol, day;
```

```text
SYMBOL DAY CNT LAST_PRICE FIRST_PRICE SO_FAR PRICE
------ --- --- ---------- ----------- ------ -----
ACME     5   2         12          25      1    25
ACME     6   2         12          25      2    12
ACME    10   2         19          25      1    25
ACME    11   2         19          25      2    19
ZED      1   2          7           8      1     8
ZED      2   2          7           8      2     7

6 rows selected.
```

### H. A view over MATCH_RECOGNIZE

<!-- example: oracle -->
```sql
CREATE VIEW up_runs AS
SELECT * FROM ticker MATCH_RECOGNIZE (
  PARTITION BY symbol ORDER BY day
  MEASURES FIRST(day) AS d1, LAST(day) AS d2
  PATTERN (a b+)
  DEFINE b AS price > PREV(price));
SELECT * FROM up_runs ORDER BY symbol, d1;
```

```text
View created.

SYMBOL D1 D2
------ -- --
ACME    1  5
ACME    6 10
ACME   12 13
ZED     3  5

4 rows selected.
```

### I. Errors and what lexdb does not take

<!-- example: oracle -->
```sql
SELECT * FROM ticker MATCH_RECOGNIZE (ORDER BY day MEASURES FIRST(day) AS f PATTERN (a) DEFINE b AS 1 = 1) m;
SELECT * FROM ticker MATCH_RECOGNIZE (ORDER BY day MEASURES FIRST(day) PATTERN (a) DEFINE a AS 1 = 1) m;
SELECT * FROM ticker MATCH_RECOGNIZE (ORDER BY day MEASURES COUNT(DISTINCT price) AS f PATTERN (a) DEFINE a AS 1 = 1) m;
SELECT * FROM ticker MATCH_RECOGNIZE (ORDER BY day MEASURES (SELECT 1 FROM dual) AS f PATTERN (a) DEFINE a AS 1 = 1) m;
SELECT * FROM ticker MATCH_RECOGNIZE (ORDER BY day MEASURES 1 AS f PATTERN (a*)* DEFINE a AS 1 = 1) m;
SELECT * FROM ticker MATCH_RECOGNIZE (ORDER BY day MEASURES FIRST(day) AS d PATTERN (a b+?) DEFINE b AS price > PREV(price)) m;
SELECT * FROM ticker MATCH_RECOGNIZE (ORDER BY day MEASURES FIRST(day) AS d PATTERN (a b?) DEFINE b AS price > PREV(price)) m;
SELECT * FROM ticker MATCH_RECOGNIZE (PARTITION BY symbol ORDER BY day MEASURES COUNT(*) AS n PATTERN (a b{0,1})
  DEFINE b AS price > PREV(price)) m
WHERE symbol = 'ZED' ORDER BY n;
```

```text
ERROR:
ORA-62503: illegal variable definition

ERROR:
ORA-02000: missing PATTERN keyword

ERROR:
ORA-62512: This aggregate is not yet supported in MATCH_RECOGNIZE clause.

ERROR:
ORA-03001: intended feature is not enabled

ERROR:
ORA-02000: missing DEFINE keyword

ERROR:
ORA-00931: missing identifier

ERROR:
ORA-62503: illegal variable definition

SYMBOL N
------ -
ZED    1
ZED    1
ZED    1
ZED    2

4 rows selected.
```

## See also

[SELECT](select.md) · [WITH](with.md) · [Hierarchical queries](hierarchical-queries.md)
