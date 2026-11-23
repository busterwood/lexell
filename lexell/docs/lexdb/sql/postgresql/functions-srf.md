# Set-returning functions

Functions that return rows: series, the elements of an array, the matches and parts of text.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
generate_series ( start, stop [, step ] ) → setof integer | bigint | numeric
generate_series ( start, stop, step_interval ) → setof timestamp | timestamptz
unnest ( array [, ...] ) → setof element [, ...]
generate_subscripts ( array, dimension [, reverse ] ) → setof integer
regexp_matches ( text, regex [, flags ] ) → setof text[]
regexp_split_to_table ( text, regex [, flags ] ) → setof text
string_to_table ( text, delimiter [, null_string ] ) → setof text

FROM function ( ... ) [ WITH ORDINALITY ] [ [ AS ] alias [ ( column_alias [, ...] ) ] ]
```

## Functions

`generate_series`
: The values from *start* to *stop*, *step* apart (1 by default; a negative step counts down). Of timestamps, the
  step is an interval; of dates, the values are `timestamptz`. A step of zero is an error. No rows when *start* is
  past *stop*.

`unnest`
: The elements of the array as rows. Given several arrays, it gives one column for each, as long as the longest,
  with NULLs for the shorter ones.

`generate_subscripts`
: The subscripts of the array (1 to its length), or from the last with *reverse* true.

`regexp_matches`, `regexp_split_to_table`, `string_to_table`
: The matches of a regular expression, and the parts of text split by one or by a delimiter: see [pattern
  matching](functions-pattern.md) and [string functions](functions-string.md).

`WITH ORDINALITY`
: Adds a `bigint` column, `ordinality` unless named, numbering the rows from 1.

## Remarks

- In `FROM`, a function is a table: give it an alias, and column aliases if you like (`AS g(n)`).
- With `LATERAL` (or after a comma), a function in `FROM` can take columns of the tables before it:
  `FROM post, unnest(post.tags) AS t(tag)`.
- `unnest`, `regexp_matches`, `regexp_split_to_table`, `string_to_table` and `generate_subscripts` may also be in
  the select list, where they give one output row for each row they return. Several in one select list run side by
  side, as long as the longest.

## Differences from PostgreSQL

- `generate_series` works in `FROM` only: in the select list it is 42883 (`function generate_series with 2
  arguments does not exist`). `generate_subscripts` works in the select list only: in `FROM` it is 42883.
- `generate_series` with a time zone (PostgreSQL 16's fourth argument) does not exist.
- `ROWS FROM (...)` and column definition lists (`AS t(a int)`) are syntax errors.
- A `LANGUAGE sql` function that returns a set cannot be called in the select list (see [CREATE
  FUNCTION](create-function.md)).

## Examples

### A. A series of integers

<!-- example: postgresql -->
```sql
SELECT * FROM generate_series(1, 4);
SELECT n FROM generate_series(10, 1, -3) AS g(n);
```

```text
 generate_series
-----------------
               1
               2
               3
               4
(4 rows)

 n
----
 10
  7
  4
  1
(4 rows)
```

### B. Numbers and timestamps

<!-- example: postgresql -->
```sql
SELECT * FROM generate_series(0.5, 2, 0.5) AS x;
SELECT d FROM generate_series(TIMESTAMP '2026-03-01', TIMESTAMP '2026-03-03', INTERVAL '1 day') AS d;
```

```text
  x
-----
 0.5
 1.0
 1.5
 2.0
(4 rows)

          d
---------------------
 2026-03-01 00:00:00
 2026-03-02 00:00:00
 2026-03-03 00:00:00
(3 rows)
```

### C. Filling gaps in a report

<!-- example: postgresql -->
```sql
CREATE TABLE sale (day date, amount int);
INSERT INTO sale VALUES ('2026-03-01', 10), ('2026-03-03', 5), ('2026-03-03', 7);
SELECT d::date AS day, coalesce(sum(s.amount), 0) AS total
FROM generate_series(DATE '2026-03-01', DATE '2026-03-04', INTERVAL '1 day') AS d
LEFT JOIN sale s ON s.day = d::date GROUP BY d ORDER BY d;
```

```text
CREATE TABLE
INSERT 0 3
    day     | total
------------+-------
 2026-03-01 |    10
 2026-03-02 |     0
 2026-03-03 |    12
 2026-03-04 |     0
(4 rows)
```

### D. unnest and WITH ORDINALITY

<!-- example: postgresql -->
```sql
SELECT * FROM unnest(ARRAY['a', 'b', 'c']) WITH ORDINALITY AS u(letter, n);
SELECT * FROM unnest(ARRAY[1, 2, 3], ARRAY['x', 'y']) AS u(num, letter);
```

```text
 letter | n
--------+---
 a      | 1
 b      | 2
 c      | 3
(3 rows)

 num | letter
-----+--------
   1 | x
   2 | y
   3 |
(3 rows)
```

### E. unnest of a column

<!-- example: postgresql -->
```sql
CREATE TABLE post (id int, tags text[]);
INSERT INTO post VALUES (1, '{sql,lexdb}'), (2, '{docs}');
SELECT p.id, t.tag, t.n FROM post p, unnest(p.tags) WITH ORDINALITY AS t(tag, n) ORDER BY p.id, t.n;
SELECT id, unnest(tags) AS tag FROM post ORDER BY id, tag;
```

```text
CREATE TABLE
INSERT 0 2
 id |  tag  | n
----+-------+---
  1 | sql   | 1
  1 | lexdb | 2
  2 | docs  | 1
(3 rows)

 id |  tag
----+-------
  1 | lexdb
  1 | sql
  2 | docs
(3 rows)
```

### F. Matches and parts of text

<!-- example: postgresql -->
```sql
SELECT * FROM regexp_matches('a1 b22 c333', '(\w)(\d+)', 'g') AS m;
SELECT * FROM regexp_split_to_table('one  two three', '\s+') WITH ORDINALITY AS t(word, n);
SELECT * FROM string_to_table('x|y|z', '|') AS t(part);
```

```text
    m
---------
 {a,1}
 {b,22}
 {c,333}
(3 rows)

 word  | n
-------+---
 one   | 1
 two   | 2
 three | 3
(3 rows)

 part
------
 x
 y
 z
(3 rows)
```

### G. Errors

<!-- example: postgresql -->
```sql
SELECT * FROM generate_series(1, 5, 0);
SELECT generate_series(1, 3);
```

```text
ERROR:  step size cannot equal zero
ERROR:  function generate_series with 2 arguments does not exist
```

## See also

[Array functions](functions-array.md) · [Pattern matching](functions-pattern.md) · [SELECT](select.md) ·
[Joins and LATERAL](select-join.md)
