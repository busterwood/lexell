# MATCH_RECOGNIZE

Finds sequences of rows that match a pattern, in the `FROM` clause of a [SELECT](select.md).

**Door:** PostgreSQL. **Follows:** SQL:2016 row pattern recognition (feature R010), as Oracle has it. PostgreSQL 18
has no such clause; lexdb adds it to this door.

## Syntax

```
from_item MATCH_RECOGNIZE (
    [ PARTITION BY column [, ...] ]
    [ ORDER BY expression [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [, ...] ]
    [ MEASURES expression [ AS ] alias [, ...] ]
    [ ONE ROW PER MATCH
    | ALL ROWS PER MATCH [ SHOW EMPTY MATCHES | OMIT EMPTY MATCHES | WITH UNMATCHED ROWS ] ]
    [ AFTER MATCH SKIP { PAST LAST ROW | TO NEXT ROW | TO [ FIRST | LAST ] variable } ]
    PATTERN ( pattern )
    [ SUBSET name = ( variable [, ...] ) [, ...] ]
    DEFINE variable AS condition [, ...]
) [ [ AS ] alias [ ( column_alias [, ...] ) ] ]

pattern:
    term [ term ... ] [ | pattern ]

term:
    { variable | ^ | $ | ( pattern ) | {- pattern -} | PERMUTE ( pattern [, ...] ) } [ quantifier ]

quantifier:
    { * | + | ? | {n} | {n,} | {,m} | {n,m} } [ ? ]
```

## Arguments

*from_item*
: A table, view, subquery, common table expression, `VALUES` or set-returning function: the rows to search. A
  `LATERAL` subquery may be the input.

`PARTITION BY` *column*
: Searches each partition on its own. Plain column names only.

`ORDER BY`
: The order of the rows within a partition. Without it, the rows are taken as the input gives them.

`MEASURES` *expression* `AS` *alias*
: The columns a match gives. Each needs an alias. A measure may use:
  - columns, plain or qualified by a pattern variable (`down.price`: the row mapped to `down`);
  - `prev(x [, n])` and `next(x [, n])`: the value *n* rows (1 by default) before or after;
  - `first(x [, n])` and `last(x [, n])`: the value at the first or last row mapped (to a variable, when `x` is
    qualified by one);
  - `count`, `sum`, `avg`, `min` and `max` over the rows mapped (`count(*)`, `count(down.*)`, `sum(up.price)`);
  - `classifier()`: the variable the row is mapped to; `match_number()`: the match's number in its partition,
    from 1;
  - `running` or `final` before a navigation or aggregate: the value as of the current row, or at the end of the
    match. `running` is the default, and with `ONE ROW PER MATCH` both are the end.

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
  is the variables in any order. A quantifier with a `?` after it is reluctant: it takes as few rows as it can.

`SUBSET` *name* `= (` *variables* `)`
: A name for a union of variables, usable in `MEASURES` and `DEFINE` (`first(ab.day)`).

`DEFINE` *variable* `AS` *condition*
: When a row may be mapped to the variable. A condition may use the same navigation and aggregates as `MEASURES`.
  A variable in `PATTERN` without a definition matches any row.

*alias*
: The name of the result. The input's own alias is not visible outside the clause.

## Remarks

- The search tries the pattern at each row in turn, and takes the first match in the pattern's order of
  preference: a greedy quantifier tries more rows first, a reluctant one fewer, and `|` its left side first.
- Names follow this door's rules: `classifier()` gives the variable's name in lower case, unless it was quoted.
- A search whose conditions look back over the rows mapped (aggregates, `first`, `last`) may take many steps. When a
  search from one row takes more than `max_match_steps` steps (10,000,000 by default), the statement fails with
  54001. `SET max_match_steps = n` changes the limit; 0 is no limit. `statement_timeout` also applies.
- `EXPLAIN` shows the clause as one step of the plan.

## Differences from PostgreSQL

- PostgreSQL 18 has no `MATCH_RECOGNIZE`; this is lexdb's, following the standard and Oracle (design/lexdb-match-recognize.md).
- Where lexdb differs from Oracle's clause:
  - `ORDER BY` takes expressions; Oracle takes columns only;
  - subqueries in `MEASURES` and `DEFINE` are refused (0A000);
  - aggregates other than `count`, `sum`, `avg`, `min` and `max`, and aggregates with `DISTINCT`, are refused
    (0A000);
  - an empty pattern `()`, an empty alternative, and a group that can match nothing repeated (`(a*)*`) are refused,
    as in Oracle; the standard allows them;
  - the window form of row pattern recognition (R020, `WINDOW w AS (... PATTERN ...)`) is not supported.

## Examples

<!--setup: postgresql
CREATE TABLE ticker (symbol text, day int, price int);
INSERT INTO ticker VALUES ('ACME', 1, 12), ('ACME', 2, 17), ('ACME', 3, 19), ('ACME', 4, 21), ('ACME', 5, 25),
  ('ACME', 6, 12), ('ACME', 7, 15), ('ACME', 8, 20), ('ACME', 9, 24), ('ACME', 10, 25), ('ACME', 11, 19),
  ('ACME', 12, 15), ('ACME', 13, 25),
  ('ZED', 1, 8), ('ZED', 2, 7), ('ZED', 3, 5), ('ZED', 4, 6), ('ZED', 5, 9);
-->

The examples use one table of prices:

```sql
CREATE TABLE ticker (symbol text, day int, price int);
INSERT INTO ticker VALUES ('ACME', 1, 12), ('ACME', 2, 17), ('ACME', 3, 19), ('ACME', 4, 21), ('ACME', 5, 25),
  ('ACME', 6, 12), ('ACME', 7, 15), ('ACME', 8, 20), ('ACME', 9, 24), ('ACME', 10, 25), ('ACME', 11, 19),
  ('ACME', 12, 15), ('ACME', 13, 25),
  ('ZED', 1, 8), ('ZED', 2, 7), ('ZED', 3, 5), ('ZED', 4, 6), ('ZED', 5, 9);
```

### A. V shapes

A fall followed by a rise, in each symbol. `SKIP TO LAST up` lets the top of one V start the next.

<!-- example: postgresql -->
```sql
SELECT *
FROM ticker MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY day
    MEASURES strt.day AS start_day, last(down.day) AS bottom_day, last(up.day) AS end_day
    ONE ROW PER MATCH
    AFTER MATCH SKIP TO LAST up
    PATTERN (strt down+ up+)
    DEFINE down AS price < prev(price), up AS price > prev(price)
) AS v
ORDER BY symbol, start_day;
```

```text
 symbol | start_day | bottom_day | end_day
--------+-----------+------------+---------
 ACME   |         5 |          6 |      10
 ACME   |        10 |         12 |      13
 ZED    |         1 |          3 |       5
(3 rows)
```

### B. ALL ROWS PER MATCH

Each row of each rising run of three or more days, with its variable and its place in the run.

<!-- example: postgresql -->
```sql
SELECT symbol, day, price, m, cls, n
FROM ticker MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY day
    MEASURES match_number() AS m, classifier() AS cls, running count(*) AS n
    ALL ROWS PER MATCH
    PATTERN (strt up{2,})
    DEFINE up AS price > prev(price)
) AS r
ORDER BY symbol, day;
```

```text
 symbol | day | price | m | cls  | n
--------+-----+-------+---+------+---
 ACME   |   1 |    12 | 1 | strt | 1
 ACME   |   2 |    17 | 1 | up   | 2
 ACME   |   3 |    19 | 1 | up   | 3
 ACME   |   4 |    21 | 1 | up   | 4
 ACME   |   5 |    25 | 1 | up   | 5
 ACME   |   6 |    12 | 2 | strt | 1
 ACME   |   7 |    15 | 2 | up   | 2
 ACME   |   8 |    20 | 2 | up   | 3
 ACME   |   9 |    24 | 2 | up   | 4
 ACME   |  10 |    25 | 2 | up   | 5
 ZED    |   3 |     5 | 1 | strt | 1
 ZED    |   4 |     6 | 1 | up   | 2
 ZED    |   5 |     9 | 1 | up   | 3
(13 rows)
```

### C. Runs, with aggregates

<!-- example: postgresql -->
```sql
SELECT *
FROM ticker MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY day
    MEASURES first(day) AS first_day, last(day) AS last_day, count(*) AS days, max(price) AS top
    PATTERN (a b+)
    DEFINE b AS price > prev(price)
) AS r
ORDER BY symbol, first_day;
```

```text
 symbol | first_day | last_day | days | top
--------+-----------+----------+------+-----
 ACME   |         1 |        5 |    5 |  25
 ACME   |         6 |       10 |    5 |  25
 ACME   |        12 |       13 |    2 |  25
 ZED    |         3 |        5 |    3 |   9
(4 rows)
```

### D. Islands of consecutive numbers

<!-- example: postgresql -->
```sql
SELECT *
FROM (VALUES (1), (2), (3), (5), (6), (9)) AS v(n) MATCH_RECOGNIZE (
    ORDER BY n
    MEASURES first(n) AS low, last(n) AS high
    PATTERN (a b*)
    DEFINE b AS n = prev(n) + 1
) AS r
ORDER BY low;
```

```text
 low | high
-----+------
   1 |    3
   5 |    6
   9 |    9
(3 rows)
```

### E. Errors

<!-- example: postgresql -->
```sql
SELECT * FROM ticker MATCH_RECOGNIZE (ORDER BY day MEASURES first(day) AS f PATTERN (a) DEFINE b AS true) m;
SELECT * FROM ticker MATCH_RECOGNIZE (ORDER BY day MEASURES count(DISTINCT price) AS f PATTERN (a) DEFINE a AS true) m;
SELECT * FROM ticker MATCH_RECOGNIZE (ORDER BY day MEASURES first(day) PATTERN (a) DEFINE a AS true) m;
```

```text
ERROR:  DEFINE names "b", which is not a pattern variable
ERROR:  lexdb: this aggregate is not supported in MATCH_RECOGNIZE
ERROR:  MEASURES expression needs to be aliased
```

## See also

[SELECT](select.md) · [Window functions](over.md)
