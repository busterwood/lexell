# Array types

`type[]`: a list of values of one type, in one dimension.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
element_type [ ]
element_type [ n ]

ARRAY [ expression [, ...] ]
ARRAY ( subquery )
'{ value [, ...] }'
array_expression [ subscript ]
```

## Arguments

*element_type*
: Any built-in type on the [index](README.md#data-types): integers, `numeric`, floats, text types, `bytea`,
  `boolean`, date and time types, `uuid`. A length *n* is read and not kept, as in PostgreSQL.

`ARRAY [ ... ]`
: An array of the expressions' values; their common type is the element type. `ARRAY[]` needs a cast
  (`ARRAY[]::int[]`).

`ARRAY ( subquery )`
: An array of the one column the subquery returns, in its order.

`'{...}'`
: An array as text. Elements are parted by commas; one with spaces, commas or quotes is written in double quotes;
  `NULL` is a NULL element.

*subscript*
: An integer: the first element is 1. A subscript outside the array gives NULL.

## Remarks

- `||` appends an element, prepends one, or joins two arrays. `=` and `<` compare element by element.
- `x = ANY (array)`, `x <> ALL (array)`, `@>` (contains), `<@` (is contained by) and `&&` (overlaps) test
  membership. See [operators](operators.md).
- `unnest` turns an array into rows; `array_agg` turns rows into an array. See [array functions](functions-array.md).
- psql shows an array in its text form, `{1,2,3}`.

## Differences from PostgreSQL

- Arrays have one dimension: `ARRAY[[1, 2], [3, 4]]` is a syntax error and `'{{1,2},{3,4}}'::int[]` is 0A000
  (`lexdb: arrays of more than one dimension are not supported`). Lower bounds other than 1 (`'[0:2]={1,2,3}'`) are
  not read.
- Slices (`a[2:3]`) and assignment to an element (`UPDATE t SET a[2] = ...`) are syntax errors.
- `integer ARRAY` (the SQL standard's spelling) is a syntax error; write `integer[]`.
- Arrays of enum types are refused (0A000).
- A subscripted column's result column is named `#elem` (PostgreSQL: the column's name); give it an alias.
- `ARRAY[1, 'x']` is a text array `{1,x}` (PostgreSQL: 22P02, `'x'` is not an integer).

## Examples

### A. Making arrays

<!-- example: postgresql -->
```sql
SELECT ARRAY[1, 2, 3] AS a, '{"a b",c,NULL}'::text[] AS b, ARRAY[]::int[] AS empty,
       ARRAY(SELECT g * 10 FROM generate_series(1, 4) g) AS c, pg_typeof(ARRAY[1.5]) AS t;
```

```text
    a    |       b        | empty |       c       |     t
---------+----------------+-------+---------------+-----------
 {1,2,3} | {"a b",c,NULL} | {}    | {10,20,30,40} | numeric[]
(1 row)
```

### B. An array column

<!-- example: postgresql -->
```sql
CREATE TABLE post (id int, tags text[]);
INSERT INTO post VALUES (1, '{red,blue}'), (2, ARRAY['green']), (3, NULL);
SELECT id, tags, tags[1] AS first, tags[3] AS third FROM post ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 3
 id |    tags    | first | third
----+------------+-------+-------
  1 | {red,blue} | red   |
  2 | {green}    | green |
  3 |            |       |
(3 rows)
```

### C. Membership

<!-- example: postgresql -->
```sql
SELECT id FROM post WHERE 'red' = ANY (tags);
SELECT id FROM post WHERE tags && ARRAY['green', 'pink'];
SELECT ARRAY[1, 2, 3] @> ARRAY[2] AS contains, ARRAY[1] <@ ARRAY[1, 2] AS within, 5 > ALL (ARRAY[1, 2]) AS above;
```

```text
 id
----
  1
(1 row)

 id
----
  2
(1 row)

 contains | within | above
----------+--------+-------
 t        | t      | t
(1 row)
```

### D. Joining and comparing

<!-- example: postgresql -->
```sql
SELECT ARRAY[1, 2] || 3 AS append, 0 || ARRAY[1, 2] AS prepend, ARRAY[1] || ARRAY[2, 3] AS cat,
       ARRAY[1, 2] < ARRAY[1, 3] AS less;
```

```text
 append  | prepend |   cat   | less
---------+---------+---------+------
 {1,2,3} | {0,1,2} | {1,2,3} | t
(1 row)
```

### E. Arrays of other types

<!-- example: postgresql -->
```sql
SELECT ARRAY[DATE '2026-01-01', DATE '2026-01-02'] AS dates, ARRAY[true, false] AS flags, ARRAY[1, NULL, 3] AS ints;
```

```text
          dates          | flags |    ints
-------------------------+-------+------------
 {2026-01-01,2026-01-02} | {t,f} | {1,NULL,3}
(1 row)
```

### F. Errors

<!-- example: postgresql -->
```sql
SELECT '{1,2'::int[];
SELECT '{{1,2},{3,4}}'::int[];
SELECT (ARRAY[10, 20, 30])[2:3];
```

```text
ERROR:  malformed array literal: "{1,2"
ERROR:  lexdb: arrays of more than one dimension are not supported
ERROR:  syntax error at or near ":"
```

## See also

[Array functions](functions-array.md) · [Set-returning functions](functions-srf.md) ·
[Aggregate functions](functions-aggregate.md) · [Operators](operators.md)
