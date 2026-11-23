# Operators

Comparison, logical, arithmetic, bitwise, text, array and pattern operators, and their precedence.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
-- comparison
a = b   a <> b   a != b   a < b   a <= b   a > b   a >= b
a [ NOT ] BETWEEN [ SYMMETRIC ] x AND y
a [ NOT ] IN ( value [, ...] )   a [ NOT ] IN ( subquery )
a operator { ANY | SOME | ALL } ( array | subquery )
[ NOT ] EXISTS ( subquery )
a IS [ NOT ] NULL   a IS [ NOT ] TRUE | FALSE | UNKNOWN
a IS [ NOT ] DISTINCT FROM b

-- logical
a AND b   a OR b   NOT a

-- arithmetic
a + b   a - b   a * b   a / b   a % b   a ^ b   - a   + a

-- bitwise (integers)
a & b   a | b   a # b   ~ a   a << n   a >> n

-- text and arrays
a || b
array @> array   array <@ array   array && array

-- pattern
a [ NOT ] LIKE p   a [ NOT ] ILIKE p   a [ NOT ] SIMILAR TO p   a ~ r   a ~* r   a !~ r   a !~* r

-- other
a :: type   array [ i ]   a AT TIME ZONE zone   a AT LOCAL   a COLLATE collation
```

## Arguments

Comparison
: `=`, `<>` (or `!=`), `<`, `<=`, `>`, `>=` compare values of the same kind; NULL on either side gives NULL.
  `BETWEEN x AND y` is `a >= x AND a <= y`; `SYMMETRIC` swaps *x* and *y* when *x* is the larger.

`IN`, `ANY`, `SOME`, `ALL`
: `IN` is true if *a* equals one of the values. `a op ANY (...)` (or `SOME`) is true if the comparison holds for
  one element of the array or row of the subquery, `ALL` if it holds for all. A NULL among the values makes a
  false answer NULL.

`EXISTS`
: True if the subquery returns a row.

`IS`
: `IS NULL`, `IS TRUE`, `IS FALSE` and `IS UNKNOWN` never give NULL. `IS DISTINCT FROM` is `<>` with NULL as an
  ordinary value: `NULL IS DISTINCT FROM NULL` is false.

`AND`, `OR`, `NOT`
: Three-valued logic: see [boolean type](data-types-boolean.md).

Arithmetic
: `/` of two integers truncates toward zero; `%` is the remainder with the sign of the left side; `^` is a power
  (a `numeric` or `double precision`). Integer overflow is 22003, division by zero 22012.

Bitwise
: AND, OR, exclusive OR (`#`), NOT (`~`), and shifts, on `smallint`, `integer` and `bigint`.

`||`
: Joins text, or text and another value as text; with an array, appends, prepends or joins arrays.

`@>`, `<@`, `&&`
: Array contains, is contained by, overlaps.

Pattern
: See [pattern matching](functions-pattern.md).

`::`, `[ ]`, `AT TIME ZONE`, `COLLATE`
: A cast (see [type conversion](type-conversion.md)); an array element (see [array types](data-types-arrays.md));
  a time zone conversion (see [date and time functions](functions-datetime.md)); a collation, read and ignored.

## Remarks

Precedence, from tightest to loosest:

| Operators | Associativity |
|---|---|
| `::` | left |
| `[ ]` | left |
| unary `+`, `-`, `~` | right |
| `COLLATE`, `AT TIME ZONE` | left |
| `^` | left |
| `*`, `/`, `%` | left |
| `+`, `-` | left |
| `||`, `&`, `|`, `#`, `<<`, `>>`, `@>`, `<@`, `&&`, `~` and the other operators | left |
| `BETWEEN`, `IN`, `LIKE`, `ILIKE`, `SIMILAR TO` | |
| `<`, `>`, `=`, `<=`, `>=`, `<>` | |
| `IS`, `IS NULL` | |
| `NOT` | right |
| `AND` | left |
| `OR` | left |

As in PostgreSQL, `-2 ^ 2` is 4 (the minus binds first) and `2 ^ 3 ^ 2` is 64 (left to right).

## Differences from PostgreSQL

- Arithmetic on `integer` and `smallint` constants does not overflow (`2147483647::int + 1` is 2147483648); on
  columns it does (see [numeric types](data-types-numeric.md)).
- `~~`, `~~*`, `!~~`, `!~~*` (LIKE spelled as operators), `^@` (starts with), `@` (absolute value), `|/` and `||/`
  (roots), `!` (factorial), `OVERLAPS` and the JSON, range, geometric and network operators do not exist.
- `OPERATOR(pg_catalog.+)` syntax and user-defined operators are not taken.
- `NOTNULL` and `ISNULL` are not operators: `SELECT 1 NOTNULL` gives 1 in a column named `notnull`.
- `a BETWEEN x AND y = b` is a syntax error (PostgreSQL reads `(a BETWEEN x AND y) = b`); use parentheses.
- The bitwise operators take a `numeric`: `1.5 & 1` gives 0 (PostgreSQL: 42883).
- A column alias after `AS` may not be a reserved word (`AS cast`, `AS select`, `AS set` are 42601); PostgreSQL
  takes any word there.
- `COLLATE` is read and ignored.

## Examples

### A. Comparison and BETWEEN

<!-- example: postgresql -->
```sql
SELECT 1 < 2 AS lt, 'a' <> 'b' AS ne, 2 != 2 AS ne2, 5 BETWEEN 1 AND 10 AS btw, 5 BETWEEN 10 AND 1 AS btw_rev,
       5 BETWEEN SYMMETRIC 10 AND 1 AS sym, 1 = NULL AS eq_null;
```

```text
 lt | ne | ne2 | btw | btw_rev | sym | eq_null
----+----+-----+-----+---------+-----+---------
 t  | t  | f   | t   | f       | t   |
(1 row)
```

### B. IN, ANY and ALL

<!-- example: postgresql -->
```sql
SELECT 3 IN (1, 2, 3) AS in_list, 4 NOT IN (1, 2) AS not_in, 4 NOT IN (1, NULL) AS not_in_null,
       2 = ANY (ARRAY[1, 2]) AS any_arr, 2 < ALL (ARRAY[3, 4]) AS all_arr,
       1 = ANY (SELECT g FROM generate_series(1, 3) g) AS any_sub, EXISTS (SELECT 1 WHERE false) AS ex;
```

```text
 in_list | not_in | not_in_null | any_arr | all_arr | any_sub | ex
---------+--------+-------------+---------+---------+---------+----
 t       | t      |             | t       | t       | t       | f
(1 row)
```

### C. IS and IS DISTINCT FROM

<!-- example: postgresql -->
```sql
SELECT NULL IS NULL AS a, 1 IS NOT NULL AS b, NULL::bool IS UNKNOWN AS c, (1 = 1) IS TRUE AS d,
       NULL IS DISTINCT FROM NULL AS e, 1 IS DISTINCT FROM NULL AS f, 1 IS NOT DISTINCT FROM 1 AS g;
```

```text
 a | b | c | d | e | f | g
---+---+---+---+---+---+---
 t | t | t | t | f | t | t
(1 row)
```

### D. Arithmetic and precedence

<!-- example: postgresql -->
```sql
SELECT 7 / 2 AS idiv, -7 % 3 AS imod, 2 ^ 10 AS pow, -2 ^ 2 AS neg_pow, 2 ^ 3 ^ 2 AS left_assoc,
       2 + 3 * 4 AS prec, 7.0 / 2 AS ndiv, 1.5 * 2 AS nmul;
```

```text
 idiv | imod | pow  | neg_pow | left_assoc | prec |        ndiv        | nmul
------+------+------+---------+------------+------+--------------------+------
    3 |   -1 | 1024 |       4 |         64 |   14 | 3.5000000000000000 |  3.0
(1 row)
```

### E. Bitwise operators

<!-- example: postgresql -->
```sql
SELECT 12 & 10 AS "and", 12 | 10 AS "or", 12 # 10 AS "xor", ~ 5 AS "not", 1 << 4 AS shl, 256 >> 2 AS shr;
```

```text
 and | or | xor | not | shl | shr
-----+----+-----+-----+-----+-----
   8 | 14 |   6 |  -6 |  16 |  64
(1 row)
```

### F. Text and arrays

<!-- example: postgresql -->
```sql
SELECT 'lex' || 'db' AS t, 'n=' || 42 AS t2, ARRAY[1, 2] || 3 AS a, ARRAY[1, 2] @> ARRAY[1] AS contains,
       ARRAY[1, 2] && ARRAY[3] AS overlaps;
```

```text
   t   |  t2  |    a    | contains | overlaps
-------+------+---------+----------+----------
 lexdb | n=42 | {1,2,3} | t        | f
(1 row)
```

### G. Casts, subscripts and time zones

<!-- example: postgresql -->
```sql
SELECT '42'::int + 1 AS casted, (ARRAY[10, 20, 30])[2] AS elem,
       TIMESTAMPTZ '2026-03-01 12:00+00' AT TIME ZONE 'Asia/Tokyo' AS tokyo, 'b' < 'a' COLLATE "C" AS coll;
```

```text
 casted | elem |        tokyo        | coll
--------+------+---------------------+------
     43 |   20 | 2026-03-01 21:00:00 | f
(1 row)
```

### H. Errors

<!-- example: postgresql -->
```sql
SELECT 1 / 0;
SELECT 'a' + 1;
SELECT @ -5;
SELECT 2 BETWEEN 1 AND 3 = true;
```

```text
ERROR:  division by zero
ERROR:  operator does not exist: a + 1
ERROR:  syntax error at or near "@"
ERROR:  syntax error at or near "="
```

## See also

[Pattern matching](functions-pattern.md) · [Mathematical functions](functions-math.md) ·
[Type conversion](type-conversion.md) · [Array types](data-types-arrays.md) · [SELECT](select.md)
