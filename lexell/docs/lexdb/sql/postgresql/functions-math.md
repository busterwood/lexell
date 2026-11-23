# Mathematical functions

Rounding, division, powers and logarithms, number theory, buckets, and other functions of numbers.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
abs ( number ) → same type
sign ( number ) → numeric | double precision
ceil ( number ) → numeric | double precision
ceiling ( number ) → numeric | double precision
floor ( number ) → numeric | double precision
round ( number ) → numeric | double precision
round ( numeric, places ) → numeric
trunc ( number ) → numeric | double precision
div ( y, x ) → numeric
mod ( y, x ) → same type
gcd ( a, b ) → same type
lcm ( a, b ) → same type
power ( a, b ) → numeric | double precision
sqrt ( number ) → numeric | double precision
cbrt ( double precision ) → double precision
exp ( number ) → numeric | double precision
ln ( number ) → numeric | double precision
log ( number ) → numeric | double precision
log10 ( number ) → numeric | double precision
log ( base, number ) → numeric
pi ( ) → double precision
degrees ( double precision ) → double precision
radians ( double precision ) → double precision
random ( ) → double precision
random ( min, max ) → integer | bigint | numeric
width_bucket ( operand, low, high, count ) → integer
scale ( numeric ) → integer
min_scale ( numeric ) → integer
trim_scale ( numeric ) → numeric
num_nulls ( value [, ...] ) → integer
num_nonnulls ( value [, ...] ) → integer
bit_count ( bytea ) → bigint
erf ( double precision ) → double precision
erfc ( double precision ) → double precision
gamma ( double precision ) → double precision
lgamma ( double precision ) → double precision
crc32 ( bytea ) → bigint
crc32c ( bytea ) → bigint
```

*number* is any numeric type. For the trigonometric functions see [their own page](functions-trig.md).

## Functions

`abs`
: The absolute value. `abs` of the smallest `bigint` is 22003.

`sign`
: -1, 0 or 1.

`ceil`, `ceiling`, `floor`
: The nearest whole number above or below. A `numeric` stays `numeric`; an integer or float gives `double
  precision`.

`round`
: The nearest whole number, or the nearest with *places* digits after the point (a negative *places* rounds to
  tens, hundreds ...). A `numeric` rounds half away from zero, a float half to even.

`trunc`
: The number cut toward zero, to a whole number.

`div`
: The integer quotient of *y* / *x*, cut toward zero.

`mod`
: The remainder of *y* / *x*, with the sign of *y*. The `%` operator is the same.

`gcd`, `lcm`
: The greatest common divisor and the least common multiple. `gcd(0, 0)` is 0.

`power`
: *a* raised to *b*. `pow` is another name. The `^` operator is the same.

`sqrt`, `cbrt`
: The square root and the cube root. The square root of a negative number is 2201F.

`exp`, `ln`
: *e* raised to the number; the natural logarithm. The logarithm of zero or a negative number is 2201E.

`log`, `log10`
: The base-10 logarithm, or the logarithm to *base*.

`pi`
: π.

`degrees`, `radians`
: Radians to degrees, and back.

`random`
: A random value from 0 up to but not including 1, or (PostgreSQL 17) a random value from *min* to *max*
  inclusive, of their type.

`width_bucket`
: The bucket *operand* falls in, of *count* equal buckets from *low* to *high*: 0 below *low*, *count* + 1 from
  *high* on.

`scale`, `min_scale`, `trim_scale`
: The number of digits after the point; the fewest needed to show the value exactly; the value with trailing
  zeros after the point removed.

`num_nulls`, `num_nonnulls`
: How many of the arguments are NULL, or not NULL.

`bit_count`
: How many bits of the bytes are 1.

`erf`, `erfc`
: The error function and the complementary error function (PostgreSQL 18).

`gamma`, `lgamma`
: The gamma function and the natural logarithm of its absolute value (PostgreSQL 18).

`crc32`, `crc32c`
: The CRC-32 and CRC-32C checksums of the bytes (PostgreSQL 18).

## Remarks

- A NULL argument gives NULL, except in `num_nulls` and `num_nonnulls`.
- `numeric` results of `sqrt`, `exp`, `ln`, `log` and `power` have at least 16 digits after the point; `round` them
  for display.
- Division by zero in `div`, `mod` and `%` is 22012.

## Differences from PostgreSQL

- `trunc (numeric, places)` does not exist (42883); use `round` or `floor`. `bit_count` takes `bytea` only, as
  in PostgreSQL (there is no `bit` type).
- `cbrt(27)` is `3.0000000000000004` (PostgreSQL: 3).
- `factorial`, `setseed`, `random_normal` and the `!` and `|/` operators do not exist.
- See [numeric types](data-types-numeric.md): `numeric` has 38 significant digits and no `NaN`.

## Examples

### A. Rounding

<!-- example: postgresql -->
```sql
SELECT round(2.5) AS r1, round(-2.5) AS r2, round(2.5::float8) AS r3, round(3.14159, 2) AS r4,
       round(1234.5, -2) AS r5, trunc(-3.7) AS t1, trunc(3.7::float8) AS t2;
SELECT ceil(4.2) AS c1, ceiling(-4.2) AS c2, floor(4.8) AS f1, floor(-4.2) AS f2, pg_typeof(floor(5)) AS t;
```

```text
 r1 | r2 | r3 |  r4  |  r5  | t1 | t2
----+----+----+------+------+----+----
  3 | -3 |  2 | 3.14 | 1200 | -3 |  3
(1 row)

 c1 | c2 | f1 | f2 |        t
----+----+----+----+------------------
  5 | -4 |  4 | -5 | double precision
(1 row)
```

### B. Sign and absolute value

<!-- example: postgresql -->
```sql
SELECT abs(-7) AS a1, abs(-7.5) AS a2, sign(-3) AS s1, sign(0.0) AS s2, sign(2.5::float8) AS s3;
```

```text
 a1 | a2  | s1 | s2 | s3
----+-----+----+----+----
  7 | 7.5 | -1 |  0 |  1
(1 row)
```

### C. Division and remainder

<!-- example: postgresql -->
```sql
SELECT div(17, 5) AS d1, div(-17, 5) AS d2, mod(17, 5) AS m1, mod(-17, 5) AS m2, 17 % 5 AS pct,
       mod(5.5, 2) AS m3;
```

```text
 d1 | d2 | m1 | m2 | pct | m3
----+----+----+----+-----+-----
  3 | -3 |  2 | -2 |   2 | 1.5
(1 row)
```

### D. gcd and lcm

<!-- example: postgresql -->
```sql
SELECT gcd(12, 18) AS gcd, lcm(4, 6) AS lcm, gcd(0, 0) AS gcd0;
```

```text
 gcd | lcm | gcd0
-----+-----+------
   6 |  12 |    0
(1 row)
```

### E. Powers and roots

<!-- example: postgresql -->
```sql
SELECT power(2, 10) AS p1, pow(2.0, 0.5) AS p2, 2 ^ 3 AS caret, sqrt(16) AS s1, round(sqrt(2::numeric), 6) AS s2,
       cbrt(27) AS cbrt;
```

```text
  p1  |         p2         | caret | s1 |    s2    |        cbrt
------+--------------------+-------+----+----------+--------------------
 1024 | 1.4142135623730950 |     8 |  4 | 1.414214 | 3.0000000000000004
(1 row)
```

### F. Exponentials and logarithms

<!-- example: postgresql -->
```sql
SELECT round(exp(1::numeric), 6) AS e, ln(1) AS ln1, round(ln(10::numeric), 6) AS ln10,
       log(1000) AS log, log10(0.01) AS log10, log(2, 1024) AS log2;
```

```text
    e     | ln1 |   ln10   | log |        log10        |        log2
----------+-----+----------+-----+---------------------+---------------------
 2.718282 |   0 | 2.302585 |   3 | -2.0000000000000000 | 10.0000000000000000
(1 row)
```

### G. pi, degrees and radians

<!-- example: postgresql -->
```sql
SELECT pi() AS pi, degrees(pi()) AS deg, radians(180) AS rad;
```

```text
        pi         | deg |        rad
-------------------+-----+-------------------
 3.141592653589793 | 180 | 3.141592653589793
(1 row)
```

### H. Random numbers

The values change from call to call, so the example only checks their range.

<!-- example: postgresql -->
```sql
SELECT bool_and(r >= 0 AND r < 1) AS in_range FROM (SELECT random() AS r FROM generate_series(1, 100)) s;
SELECT bool_and(r BETWEEN 1 AND 6) AS dice, pg_typeof(min(r)) AS type
FROM (SELECT random(1, 6) AS r FROM generate_series(1, 100)) s;
```

```text
 in_range
----------
 t
(1 row)

 dice |  type
------+---------
 t    | integer
(1 row)
```

### I. width_bucket

<!-- example: postgresql -->
```sql
SELECT v, width_bucket(v, 0, 100, 4) AS bucket FROM (VALUES (-5), (0), (24.9), (25), (99), (100)) t(v);
```

```text
  v   | bucket
------+--------
   -5 |      0
    0 |      1
 24.9 |      1
   25 |      2
   99 |      4
  100 |      5
(6 rows)
```

### J. Scale

<!-- example: postgresql -->
```sql
SELECT scale(1.2300) AS scale, min_scale(1.2300) AS min_scale, trim_scale(1.2300) AS trimmed;
```

```text
 scale | min_scale | trimmed
-------+-----------+---------
     4 |         2 |    1.23
(1 row)
```

### K. Counting NULLs

<!-- example: postgresql -->
```sql
SELECT num_nulls(1, NULL, 'a', NULL) AS nulls, num_nonnulls(1, NULL, 'a', NULL) AS nonnulls;
```

```text
 nulls | nonnulls
-------+----------
     2 |        2
(1 row)
```

### L. bit_count, erf, gamma and checksums

<!-- example: postgresql -->
```sql
SELECT bit_count('\xff01'::bytea) AS bits, round(erf(1)::numeric, 6) AS erf, round(erfc(1)::numeric, 6) AS erfc,
       gamma(5) AS gamma, round(lgamma(10)::numeric, 6) AS lgamma;
SELECT crc32('The quick brown fox jumps over the lazy dog'::bytea) AS crc32,
       crc32c('The quick brown fox jumps over the lazy dog'::bytea) AS crc32c;
```

```text
 bits |   erf    |   erfc   | gamma |  lgamma
------+----------+----------+-------+-----------
    9 | 0.842701 | 0.157299 |    24 | 12.801827
(1 row)

   crc32    |  crc32c
------------+-----------
 1095738169 | 576848900
(1 row)
```

### M. Errors

<!-- example: postgresql -->
```sql
SELECT sqrt(-1);
SELECT ln(0);
SELECT mod(5, 0);
SELECT trunc(3.14159, 2);
SELECT factorial(5);
```

```text
ERROR:  cannot take square root of a negative number
ERROR:  cannot take logarithm of zero
ERROR:  division by zero
ERROR:  function trunc with 2 arguments does not exist
ERROR:  function factorial with 1 arguments does not exist
```

## See also

[Trigonometric functions](functions-trig.md) · [Numeric types](data-types-numeric.md) · [Operators](operators.md) ·
[Aggregate functions](functions-aggregate.md)
