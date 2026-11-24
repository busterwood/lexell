# Numeric types

Integers, exact decimal numbers, floating-point numbers and the serial types.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
smallint | int2
integer | int | int4
bigint | int8
numeric [ ( precision [, scale ] ) ]
decimal [ ( precision [, scale ] ) ]
real | float4
double precision | float8
float [ ( p ) ]
smallserial | serial2
serial | serial4
bigserial | serial8
```

## Arguments

`smallint`, `integer`, `bigint`
: Integers of 2, 4 and 8 bytes: -32768 to 32767, -2147483648 to 2147483647, and -9223372036854775808 to
  9223372036854775807. A value out of range is 22003 (`integer out of range`).

`numeric`, `decimal`
: An exact decimal number. *precision* is the number of significant digits, 1 to 38; *scale* the number of
  digits after the point, 0 to *precision*. A value is rounded to the scale, half away from zero; a value with
  more digits before the point than *precision* minus *scale* is 22003. Without a precision, a `numeric` keeps
  the digits it is given, up to 38 significant digits.

`real`, `double precision`
: Binary floating point of 4 and 8 bytes (IEEE 754). They take `'NaN'`, `'Infinity'` and `'-Infinity'`.

`float(p)`
: `real` for *p* from 1 to 24, `double precision` for 25 to 53. `float` alone is `double precision`.

`smallserial`, `serial`, `bigserial`
: Not types but shorthand in `CREATE TABLE`: a `smallint`, `integer` or `bigint` column, `NOT NULL`, whose default
  is `nextval` of a sequence made for it (`table_column_seq`).

## Remarks

- A literal without a point or exponent is an `integer`, or a `bigint` when it does not fit; `1.5` and `1e3` are
  `numeric`.
- Integer division truncates toward zero: `7 / 2` is 3, `-7 / 2` is -3. Division by zero is 22012.
- In mixed arithmetic the result is the wider type: an integer with a `numeric` gives `numeric`, anything with a
  `double precision` gives `double precision`.
- Casting a `numeric` or a float to an integer rounds: a `numeric` half away from zero (`2.5::int` is 3), a float
  half to even (`2.5::float8::int` is 2).
- `numeric` division gives at least 16 digits after the point (`1::numeric / 3` is
  `0.33333333333333333333`); `round` it for display.
- `0x1F`, `0b101`, `0o17` and `1_000_000` are integer literals, as in PostgreSQL 16.

## Differences from PostgreSQL

- Arithmetic on integer constants in a select list overflows as in PostgreSQL: `SELECT 2147483647 + 1`,
  `SELECT 46341 * 46341` and `SELECT -2147483648 - 1` are 22003 (`integer out of range`), `SELECT 9223372036854775807
  + 1` is 22003 (`bigint out of range`). A constant past `integer` is a `bigint`, so `2147483647 + 1::bigint` is
  2147483648. In `WHERE`, `ON`, `HAVING` and `ORDER BY` the constants' arithmetic is not checked (it is computed as
  `bigint`: `WHERE 2147483647 + 1 > 0` is true). With a cast to `smallint` or `integer` in the expression, and on a
  column, it is 22003 everywhere, as in PostgreSQL: `2147483647::int + 1`, `32767::smallint + 1::smallint` and
  `n + 1` of a column holding 2147483647. PostgreSQL folds a constant expression when it plans, so `SELECT
  2147483647::int + 1 FROM t WHERE false` is 22003 there and gives no rows here.
- `numeric` has at most 38 significant digits (PostgreSQL: 131072 digits before the point). An integer literal of
  39 digits is 22003 (`numeric literal out of range`).
- `numeric` has no `NaN` and no infinities: `'NaN'::numeric` is 22P02.
- A cast whose result column has no name is sometimes named `?column?` where PostgreSQL uses the type's name
  (`(-2.5)::int`).
- There is no `money` type (42704).

## Examples

### A. Integer types and their ranges

<!-- example: postgresql -->
```sql
SELECT 32767::smallint, 2147483647::int, 9223372036854775807::bigint;
SELECT pg_typeof(1), pg_typeof(2147483648), pg_typeof(1.5), pg_typeof(1e3);
SELECT 32768::smallint;
```

```text
 int2  |    int4    |        int8
-------+------------+---------------------
 32767 | 2147483647 | 9223372036854775807
(1 row)

 pg_typeof | pg_typeof | pg_typeof | pg_typeof
-----------+-----------+-----------+-----------
 integer   | bigint    | numeric   | numeric
(1 row)

ERROR:  smallint out of range
```

### B. Integer division and remainder

<!-- example: postgresql -->
```sql
SELECT 7 / 2 AS q, 7 % 2 AS r, -7 / 2 AS neg_q, 7.0 / 2 AS exact;
```

```text
 q | r | neg_q |       exact
---+---+-------+--------------------
 3 | 1 |    -3 | 3.5000000000000000
(1 row)
```

### C. numeric precision and scale

A value is rounded to the column's scale; one with too many digits before the point is refused.

<!-- example: postgresql -->
```sql
CREATE TABLE price (item text, amount numeric(7,2));
INSERT INTO price VALUES ('a', 12345.678), ('b', 0.005), ('c', -0.005);
SELECT * FROM price;
INSERT INTO price VALUES ('d', 123456.7);
```

```text
CREATE TABLE
INSERT 0 3
 item |  amount
------+----------
 a    | 12345.68
 b    |     0.01
 c    |    -0.01
(3 rows)

ERROR:  numeric field overflow: a field with precision 7, scale 2 must round to an absolute value less than 10^5
```

### D. numeric without a precision

<!-- example: postgresql -->
```sql
SELECT 1::numeric / 3 AS third, round(1::numeric / 3, 4) AS rounded,
       12345678901234567890123456789012345678::numeric AS digits_38;
```

```text
         third          | rounded |               digits_38
------------------------+---------+----------------------------------------
 0.33333333333333333333 |  0.3333 | 12345678901234567890123456789012345678
(1 row)
```

### E. Floating point

<!-- example: postgresql -->
```sql
SELECT 1.5::real AS r, 0.1::float8 + 0.2::float8 AS sum, 1 / 3::float8 AS third;
SELECT 'NaN'::float8, 'Infinity'::float8, '-Infinity'::real;
SELECT pg_typeof(1::float(10)), pg_typeof(1::float(30)), pg_typeof(1::float);
```

```text
  r  |         sum         |       third
-----+---------------------+--------------------
 1.5 | 0.30000000000000004 | 0.3333333333333333
(1 row)

 float8 |  float8  |  float4
--------+----------+-----------
    NaN | Infinity | -Infinity
(1 row)

 pg_typeof |    pg_typeof     |    pg_typeof
-----------+------------------+------------------
 real      | double precision | double precision
(1 row)
```

### F. Casts to integer round

<!-- example: postgresql -->
```sql
SELECT 2.5::int AS a, 3.5::int AS b, 2.5::float8::int AS c, '42'::int AS d;
```

```text
 a | b | c | d
---+---+---+----
 3 | 4 | 2 | 42
(1 row)
```

### G. Mixed arithmetic

<!-- example: postgresql -->
```sql
SELECT pg_typeof(1 + 1.5) AS int_num, pg_typeof(1 + 1.5::float8) AS int_float,
       pg_typeof(1::int + 1::bigint) AS int_big, pg_typeof(1::smallint + 1::smallint) AS small;
```

```text
 int_num |    int_float     | int_big |  small
---------+------------------+---------+----------
 numeric | double precision | bigint  | smallint
(1 row)
```

### H. Serial columns

<!-- example: postgresql -->
```sql
CREATE TABLE item (id serial PRIMARY KEY, big bigserial, name text);
INSERT INTO item (name) VALUES ('first'), ('second');
SELECT * FROM item;
SELECT column_name, data_type, column_default FROM information_schema.columns
WHERE table_name = 'item' ORDER BY ordinal_position;
```

```text
CREATE TABLE
INSERT 0 2
 id | big |  name
----+-----+--------
  1 |   1 | first
  2 |   2 | second
(2 rows)

 column_name | data_type |          column_default
-------------+-----------+-----------------------------------
 id          | integer   | nextval('item_id_seq'::regclass)
 big         | bigint    | nextval('item_big_seq'::regclass)
 name        | text      |
(3 rows)
```

### I. Integer literals in other bases

<!-- example: postgresql -->
```sql
SELECT 0x1F AS hex, 0b101 AS bin, 0o17 AS oct, 1_000_000 AS million;
```

```text
 hex | bin | oct | million
-----+-----+-----+---------
  31 |   5 |  15 | 1000000
(1 row)
```

### J. Errors

<!-- example: postgresql -->
```sql
CREATE TABLE counter (n int);
INSERT INTO counter VALUES (2147483647);
SELECT n + 1 FROM counter;
SELECT 2147483647 + 1;
SELECT 46341 * 46341;
SELECT 9223372036854775807 + 1;
SELECT 2147483647 + 1::bigint;
SELECT 2147483647::int + 1;
SELECT 32767::smallint + 1::smallint;
SELECT 2147483647::int * 2;
SELECT 5 / 0;
SELECT 'abc'::int;
SELECT 'NaN'::numeric;
SELECT 1::float(60);
```

```text
CREATE TABLE
INSERT 0 1
ERROR:  integer out of range
ERROR:  integer out of range
ERROR:  integer out of range
ERROR:  bigint out of range
  ?column?
------------
 2147483648
(1 row)

ERROR:  integer out of range
ERROR:  smallint out of range
ERROR:  integer out of range
ERROR:  division by zero
ERROR:  invalid input syntax for type integer: "abc"
ERROR:  invalid input syntax for type numeric: "NaN"
ERROR:  precision for type float must be less than 54 bits
```

## See also

[Mathematical functions](functions-math.md) · [Type conversion](type-conversion.md) ·
[CREATE TABLE](create-table.md) · [CREATE SEQUENCE](create-sequence.md) · [Operators](operators.md)
