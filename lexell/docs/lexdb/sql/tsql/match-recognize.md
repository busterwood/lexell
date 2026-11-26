# MATCH_RECOGNIZE (Transact-SQL)

Finds sequences of rows that match a pattern, in the `FROM` clause of a [SELECT](select.md).

**Door:** SQL Server (TDS). **Follows:** SQL:2016 row pattern recognition (feature R010), as Oracle has it. SQL Server
2022 and 2025 have no such clause; lexdb adds it to this door with T-SQL identifier rules, variables, and error
numbers.

## Syntax

```
table_source MATCH_RECOGNIZE (
    [ PARTITION BY column [ ,...n ] ]
    [ ORDER BY expression [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [ ,...n ] ]
    [ MEASURES expression [ AS ] alias [ ,...n ] ]
    [ ONE ROW PER MATCH
    | ALL ROWS PER MATCH [ SHOW EMPTY MATCHES | OMIT EMPTY MATCHES | WITH UNMATCHED ROWS ] ]
    [ AFTER MATCH SKIP { PAST LAST ROW | TO NEXT ROW | TO [ FIRST | LAST ] variable } ]
    PATTERN ( pattern )
    [ SUBSET name = ( variable [ ,...n ] ) [ ,...n ] ]
    DEFINE variable AS condition [ ,...n ]
) [ [ AS ] alias [ ( column_alias [ ,...n ] ) ] ]

pattern ::=
    term [ term ... ] [ | pattern ]

term ::=
    { variable | ^ | $ | ( pattern ) | {- pattern -} | PERMUTE ( pattern [ ,...n ] ) } [ quantifier ]

quantifier ::=
    { * | + | ? | {n} | {n,} | {,m} | {n,m} } [ ? ]
```

## Arguments

*table_source*
: A table, view, `#temp` table, `@table` variable, derived table, common table expression, `VALUES`, or table-valued
  function: the rows to search. Works with `CROSS APPLY` / `OUTER APPLY` and table hints (`WITH (NOLOCK)`).

`PARTITION BY` *column*
: Searches each partition on its own. Plain column names only (bracketed names such as `[day]` are allowed).

`ORDER BY`
: The order of the rows within a partition. Without it, the rows are taken as the input gives them. Follows T-SQL's
  default NULL order (NULLs sort first for `ASC` and last for `DESC`) unless `NULLS FIRST` or `NULLS LAST` is written.

`MEASURES` *expression* `AS` *alias*
: The columns a match gives. Each needs an alias. A measure may use:
  - columns, plain or qualified by a pattern variable (`down.price`: the row mapped to `down`);
  - `PREV(x [, n])` and `NEXT(x [, n])`: the value *n* rows (1 by default) before or after;
  - `FIRST(x [, n])` and `LAST(x [, n])`: the value at the first or last row mapped (to a variable, when `x` is
    qualified by one);
  - `COUNT`, `COUNT_BIG`, `SUM`, `AVG`, `MIN`, and `MAX` over the rows mapped (`COUNT(*)`, `COUNT_BIG(down.*)`,
    `SUM(up.price)`);
  - `CLASSIFIER()`: the variable the row is mapped to; `MATCH_NUMBER()`: the match's number in its partition, from 1;
  - `RUNNING` or `FINAL` before a navigation or aggregate: the value as of the current row, or at the end of the match.
    `RUNNING` is the default, and with `ONE ROW PER MATCH` both are the end;
  - local `@variables` and procedure parameters.

`ONE ROW PER MATCH`
: The default: one row for each match, with the `PARTITION BY` columns and the measures.

`ALL ROWS PER MATCH`
: One row for each row of each match: the `PARTITION BY` and plain `ORDER BY` columns, the measures, then the input's
  other columns. `SHOW EMPTY MATCHES` (the default) gives a row for an empty match, `OMIT EMPTY MATCHES` does not, and
  `WITH UNMATCHED ROWS` adds the rows in no match, with NULL measures.

`AFTER MATCH SKIP`
: Where the next search starts: `PAST LAST ROW` (the default) after the match; `TO NEXT ROW` at the row after the
  match's first; `TO FIRST v` or `TO LAST v` at the first or last row mapped to `v` (`TO v` is `TO LAST v`).

`PATTERN (` *pattern* `)`
: A regular expression over the variables. Terms in a row follow each other; `|` is either; `^` and `$` are the
  partition's start and end; `{- ... -}` matches but leaves its rows out of `ALL ROWS PER MATCH`; `PERMUTE (a, b)` is
  the variables in any order. A quantifier with a `?` after it is reluctant: it takes as few rows as it can.

`SUBSET` *name* `= (` *variables* `)`
: A name for a union of variables, usable in `MEASURES` and `DEFINE` (`FIRST(ab.[day])`).

`DEFINE` *variable* `AS` *condition*
: When a row may be mapped to the variable. A condition may use the same navigation, aggregates, and `@variables` as
  `MEASURES`. A variable in `PATTERN` without a definition matches any row.

*alias*
: The name of the result. The input's own alias is not visible outside the clause.

## Remarks

- The search tries the pattern at each row in turn, and takes the first match in the pattern's order of preference: a
  greedy quantifier tries more rows first, a reluctant one fewer, and `|` its left side first.
- Names follow T-SQL's rules: identifier resolution is case-insensitive, bracketed (`[Up Move]`) and double-quoted
  identifiers are supported for columns, aliases, and pattern variables, and `CLASSIFIER()` returns each pattern
  variable as spelled in `PATTERN`.
- A search whose conditions look back over the rows mapped (aggregates, `FIRST`, `LAST`) may take many steps. When a
  search from one row takes more than `MAX_MATCH_STEPS` steps (10,000,000 by default), the statement fails with error
  50000 (catchable in `TRY ... CATCH`). `SET MAX_MATCH_STEPS n` (or `SET MAX_MATCH_STEPS = n`) changes the limit for
  the session; `0` is no limit.
- Works in views, stored procedures, `SELECT TOP`, `SELECT ... INTO`, and with `CROSS APPLY` / `OUTER APPLY`.

## Differences from SQL Server

- SQL Server 2022 and 2025 do not have `MATCH_RECOGNIZE`; this is lexdb's, following SQL:2016 R010 and Oracle
  (`design/lexdb-match-recognize.md`).
- Where lexdb differs from the SQL:2016 standard / Oracle:
  - `ORDER BY` takes expressions; Oracle takes columns only;
  - subqueries in `MEASURES` and `DEFINE` are refused (error 50000);
  - aggregates other than `COUNT`, `COUNT_BIG`, `SUM`, `AVG`, `MIN`, and `MAX`, and aggregates with `DISTINCT`, are
    refused (error 50000);
  - an empty pattern `()`, an empty alternative, and a group that can match nothing repeated (`(a*)*`) are refused;
  - the window form of row pattern recognition (R020, `WINDOW w AS (... PATTERN ...)`) is not supported.

## Examples

<!--setup: tsql
CREATE TABLE dbo.ticker (symbol nvarchar(10), [day] int, price int);
INSERT INTO dbo.ticker VALUES
  (N'ACME', 1, 12), (N'ACME', 2, 17), (N'ACME', 3, 19), (N'ACME', 4, 21), (N'ACME', 5, 25),
  (N'ACME', 6, 12), (N'ACME', 7, 15), (N'ACME', 8, 20), (N'ACME', 9, 24), (N'ACME', 10, 25),
  (N'ACME', 11, 19), (N'ACME', 12, 15), (N'ACME', 13, 25),
  (N'ZED', 1, 8), (N'ZED', 2, 7), (N'ZED', 3, 5), (N'ZED', 4, 6), (N'ZED', 5, 9);
-->

The examples use one table of prices:

```sql
CREATE TABLE dbo.ticker (symbol nvarchar(10), [day] int, price int);
INSERT INTO dbo.ticker VALUES
  (N'ACME', 1, 12), (N'ACME', 2, 17), (N'ACME', 3, 19), (N'ACME', 4, 21), (N'ACME', 5, 25),
  (N'ACME', 6, 12), (N'ACME', 7, 15), (N'ACME', 8, 20), (N'ACME', 9, 24), (N'ACME', 10, 25),
  (N'ACME', 11, 19), (N'ACME', 12, 15), (N'ACME', 13, 25),
  (N'ZED', 1, 8), (N'ZED', 2, 7), (N'ZED', 3, 5), (N'ZED', 4, 6), (N'ZED', 5, 9);
```

### A. V shapes

A fall followed by a rise, in each symbol. `SKIP TO LAST up` lets the top of one V start the next.

<!-- example: tsql -->
```sql
SELECT *
FROM dbo.ticker MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY [day]
    MEASURES strt.[day] AS start_day, LAST(down.[day]) AS bottom_day, LAST(up.[day]) AS end_day
    ONE ROW PER MATCH
    AFTER MATCH SKIP TO LAST up
    PATTERN (strt down+ up+)
    DEFINE down AS price < PREV(price), up AS price > PREV(price)
) AS v
ORDER BY symbol, start_day;
```

```text
symbol start_day bottom_day end_day
------ --------- ---------- -------
ACME   5         6          10
ACME   10        12         13
ZED    1         3          5

(3 rows affected)
```

### B. `ALL ROWS PER MATCH` with `CLASSIFIER()`

Each row of each rising run of three or more days, with its variable name (preserving T-SQL spelling) and running
count.

<!-- example: tsql -->
```sql
SELECT symbol, [day], price, m, cls, n
FROM dbo.ticker MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY [day]
    MEASURES MATCH_NUMBER() AS m, CLASSIFIER() AS cls, RUNNING COUNT(*) AS n
    ALL ROWS PER MATCH
    PATTERN (Strt Up{2,})
    DEFINE Up AS price > PREV(price)
) AS r
ORDER BY symbol, [day];
```

```text
symbol day price m cls  n
------ --- ----- - ---- -
ACME   1   12    1 Strt 1
ACME   2   17    1 Up   2
ACME   3   19    1 Up   3
ACME   4   21    1 Up   4
ACME   5   25    1 Up   5
ACME   6   12    2 Strt 1
ACME   7   15    2 Up   2
ACME   8   20    2 Up   3
ACME   9   24    2 Up   4
ACME   10  25    2 Up   5
ZED    3   5     1 Strt 1
ZED    4   6     1 Up   2
ZED    5   9     1 Up   3

(13 rows affected)
```

### C. Local `@variables` and `COUNT_BIG`

Filter V shapes using a T-SQL `@min_drop` variable inside `DEFINE` and count rows with `COUNT_BIG`.

<!-- example: tsql -->
```sql
DECLARE @min_drop int = 10;

SELECT symbol, start_day, bottom_day, drop_amt, down_rows
FROM dbo.ticker MATCH_RECOGNIZE (
    PARTITION BY symbol
    ORDER BY [day]
    MEASURES
        strt.[day] AS start_day,
        LAST(down.[day]) AS bottom_day,
        strt.price - LAST(down.price) AS drop_amt,
        COUNT_BIG(down.*) AS down_rows
    AFTER MATCH SKIP TO LAST up
    PATTERN (strt down+ up+)
    DEFINE
        down AS price < PREV(price),
        up AS price > PREV(price) AND FIRST(strt.price) - LAST(down.price) >= @min_drop
) AS v
ORDER BY symbol, start_day;
```

```text
symbol start_day bottom_day drop_amt down_rows
------ --------- ---------- -------- ---------
ACME   5         6          13       1
ACME   10        12         10       2

(2 rows affected)
```

### D. Islands over a `@table` variable

<!-- example: tsql -->
```sql
DECLARE @nums TABLE (n int);
INSERT INTO @nums VALUES (1), (2), (3), (5), (6), (9);

SELECT low, high
FROM @nums MATCH_RECOGNIZE (
    ORDER BY n
    MEASURES FIRST(n) AS low, LAST(n) AS high
    PATTERN (a b*)
    DEFINE b AS n = PREV(n) + 1
) AS r
ORDER BY low;
```

```text
low high
--- ----
1   3
5   6
9   9

(3 rows affected)
```

## See also

[SELECT](select.md) · [FROM, JOIN and APPLY](from.md) · [OVER](over.md) · [SET statements](set-statements.md)
