# Mathematical functions (Transact-SQL)

Rounding, powers and logarithms, trigonometry, and bit manipulation.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
ABS ( numeric_expression ) → same type
CEILING ( numeric_expression ) → same type
FLOOR ( numeric_expression ) → same type
ROUND ( numeric_expression, length [, function ] ) → same type
SIGN ( numeric_expression ) → same type
POWER ( float_expression, y ) → type of float_expression
SQUARE ( float_expression ) → float
SQRT ( float_expression ) → float
EXP ( float_expression ) → float
LOG ( float_expression [, base ] ) → float
LOG10 ( float_expression ) → float
PI ( ) → float
SIN ( float_expression ) → float
COS ( float_expression ) → float
TAN ( float_expression ) → float
COT ( float_expression ) → float
ASIN ( float_expression ) → float
ACOS ( float_expression ) → float
ATAN ( float_expression ) → float
DEGREES ( numeric_expression ) → same type
RADIANS ( numeric_expression ) → same type

BIT_COUNT ( expression ) → bigint
LEFT_SHIFT ( expression_value, shift_amount ) → type of expression_value
RIGHT_SHIFT ( expression_value, shift_amount ) → type of expression_value
GET_BIT ( expression_value, bit_offset ) → bit
SET_BIT ( expression_value, bit_offset [, bit_value ] ) → type of expression_value
```

## Functions

`ABS`
: The absolute value.

`CEILING`, `FLOOR`
: The smallest integer not below, and the largest not above, the value. A float stays a float.

`ROUND`
: The value rounded to *length* decimal places; a negative *length* rounds the digits left of the point. Halves go
  away from zero. With a *function* other than 0, the value is cut instead of rounded.

`SIGN`
: -1, 0 or 1.

`POWER`
: The first argument raised to the second. The result has the type of the first: `POWER(2, 3)` is the integer 8, and
  `POWER(2, 0.5)` the integer 1.

`SQUARE`
: The value times itself, as a float.

`SQRT`
: The square root, as a float.

`EXP`
: *e* raised to the value.

`LOG`
: The natural logarithm. With *base*, the logarithm to that base (but see Differences).

`LOG10`
: The logarithm to base 10.

`PI`
: 3.141592653589793.

`SIN`, `COS`, `TAN`, `COT`
: The trigonometric functions of an angle in radians.

`ASIN`, `ACOS`, `ATAN`
: The angle in radians for a sine, cosine or tangent.

`DEGREES`, `RADIANS`
: An angle in radians converted to degrees, and the other way.

`BIT_COUNT`
: The number of bits that are set in the value (its two's complement, to the width of its type).

`LEFT_SHIFT`, `RIGHT_SHIFT`
: The value shifted left or right by *shift_amount* bits. Both give the type of the value.

`GET_BIT`
: The bit at *bit_offset*, counted from the least significant bit, which is 0.

`SET_BIT`
: The value with that bit set to *bit_value* (1 by default).

## Remarks

- A NULL argument gives NULL.
- `+ - * / %` and the bitwise operators `& | ^ ~ << >>` are operators, not functions. Dividing two integers gives an
  integer: `10 / 4` is 2.
- `SQRT`, `LOG`, `EXP`, the trigonometric functions and `PI` give a `float`. `ABS` and `POWER` keep the type of their
  argument, so an integer overflow is error 8115 (`POWER(2, 31)`).
- A result that is not a number (the square root of a negative number) is an error. Example I shows each one.
- The bit functions work on the width of the type: a `tinyint` has 8 bits, an `int` 32, a `bigint` 64.

## Differences from SQL Server

- **`LOG(x, base)` has its arguments the wrong way round:** `LOG(100, 10)` gives 0.5 (SQL Server: 2), as it is the
  logarithm of 10 to base 100, and the result is a `decimal`. Use `LOG10`, or `LOG(x) / LOG(base)` (which can differ
  in the last digit).
- `ROUND` of a `decimal` with a negative length is error 8115: `ROUND(123.4567, -1)` (SQL Server: 120.0000). An `int`
  or a `float` can be rounded that way (example B).
- `SQRT(-1)`, `LOG(0)`, `LOG(-1)` and `ASIN(2)` are errors (50000 or 8115, with PostgreSQL's wording); SQL Server's
  error for each is 3623.
- `LEFT_SHIFT` does not drop the bits that leave the width of the type: `LEFT_SHIFT(CAST(1 AS tinyint), 8)` is 256
  (SQL Server: 0).
- `ATN2` is not available (error 195); write `ATAN` of a quotient.
- The catalog gives every `decimal` expression result the precision 38 and scale 6, whatever its real size.

## Examples

### A. ABS, SIGN, CEILING and FLOOR

<!-- example: tsql -->
```sql
SELECT ABS(-5) AS abs_int, ABS(-5.5) AS abs_decimal, ABS(CAST(-3 AS float)) AS abs_float, SIGN(-3) AS sign_neg, SIGN(0) AS sign_zero,
       SIGN(2.5) AS sign_pos, CEILING(1.2) AS ceil_pos, CEILING(-1.2) AS ceil_neg, FLOOR(1.8) AS floor_pos, FLOOR(-1.2) AS floor_neg;
```

```text
abs_int abs_decimal abs_float sign_neg sign_zero sign_pos ceil_pos ceil_neg floor_pos floor_neg
------- ----------- --------- -------- --------- -------- -------- -------- --------- ---------
5       5.5         3.0       -1       0         1        2        -1       1         -2

(1 row affected)
```

### B. ROUND, with and without truncation

A third argument other than 0 cuts the value instead of rounding it.

<!-- example: tsql -->
```sql
SELECT ROUND(123.4567, 2) AS two_places, ROUND(123.4567, 0) AS whole, ROUND(123.4567, 2, 1) AS truncated,
       ROUND(5.5, 0) AS half_up, ROUND(-5.5, 0) AS half_down, ROUND(5.55, 1, 1) AS cut, ROUND(NULL, 1) AS null_value,
       ROUND(1234, -2) AS int_hundreds, ROUND(1250, -2) AS int_half, ROUND(CAST(1234.5678 AS float), -2) AS float_hundreds,
       ROUND(CAST(2.567 AS float), 2) AS float_places;
```

```text
two_places whole    truncated half_up half_down cut  null_value int_hundreds int_half float_hundreds float_places
---------- -------- --------- ------- --------- ---- ---------- ------------ -------- -------------- ------------
123.4600   123.0000 123.4500  6.0     -6.0      5.50 NULL       1200         1300     1200.0         2.57

(1 row affected)
```

### C. POWER, SQUARE, SQRT and EXP

<!-- example: tsql -->
```sql
SELECT POWER(2, 10) AS int_power, POWER(2, 0.5) AS int_base, POWER(CAST(2 AS float), 0.5) AS float_base,
       POWER(CAST(2 AS bigint), 40) AS big_power, POWER(10, -2) AS int_negative, POWER(CAST(10 AS float), -2) AS float_negative,
       SQUARE(4) AS square_, SQRT(16) AS sqrt_, SQRT(2) AS sqrt_two, EXP(1) AS e, EXP(0) AS exp_zero;
```

```text
int_power int_base float_base         big_power     int_negative float_negative square_ sqrt_ sqrt_two           e                 exp_zero
--------- -------- ------------------ ------------- ------------ -------------- ------- ----- ------------------ ----------------- --------
1024      1        1.4142135623730951 1099511627776 0            0.01           16.0    4.0   1.4142135623730951 2.718281828459045 1.0

(1 row affected)
```

### D. Logarithms

`LOG(100, 10)` is shown as lexdb gives it: the arguments are the wrong way round (see Differences).

<!-- example: tsql -->
```sql
SELECT LOG(100) AS ln_100, LOG(EXP(1)) AS ln_of_e, LOG10(1000) AS base_10, LOG(1000) / LOG(10) AS base_10_by_hand,
       LOG(100, 10) AS two_arguments;
```

```text
ln_100            ln_of_e base_10 base_10_by_hand    two_arguments
----------------- ------- ------- ------------------ ------------------
4.605170185988092 1.0     3.0     2.9999999999999996 0.5000000000000000

(1 row affected)
```

### E. Trigonometry

<!-- example: tsql -->
```sql
SELECT SIN(PI() / 2) AS sin_, COS(PI()) AS cos_, TAN(PI() / 4) AS tan_, COT(1) AS cot_, ASIN(1) AS asin_, ACOS(-1) AS acos_,
       ATAN(1) AS atan_, DEGREES(PI()) AS degrees_, RADIANS(180) AS radians_, ATAN(1) * 4 AS pi_from_atan;
```

```text
sin_ cos_ tan_               cot_               asin_              acos_             atan_              degrees_ radians_          pi_from_atan
---- ---- ------------------ ------------------ ------------------ ----------------- ------------------ -------- ----------------- -----------------
1.0  -1.0 0.9999999999999999 0.6420926159343306 1.5707963267948966 3.141592653589793 0.7853981633974483 180.0    3.141592653589793 3.141592653589793

(1 row affected)
```

### F. Result types

A view over the expressions, and the catalog's view of its columns: `SQRT`, `LOG`, `EXP`, `SQUARE` and `PI` give
`float`,
`ABS` and `POWER` of integers give `int`.

<!-- example: tsql -->
```sql
CREATE VIEW dbo.math_types AS
SELECT ABS(-5) AS abs_int, SQRT(4) AS sqrt_int, POWER(2, 3) AS power_int, LOG(2) AS log_int, SQUARE(3) AS square_int,
       EXP(1) AS exp_int, PI() AS pi_;
GO
SELECT c.name, t.name AS type_name FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.math_types') ORDER BY c.column_id;
```

```text
name       type_name
---------- ---------
abs_int    int
sqrt_int   float
power_int  int
log_int    float
square_int float
exp_int    float
pi_        float

(7 rows affected)
```

### G. Bit functions

<!-- example: tsql -->
```sql
SELECT BIT_COUNT(7) AS bits_7, BIT_COUNT(255) AS bits_255, BIT_COUNT(CAST(-1 AS bigint)) AS bits_minus_1_bigint,
       BIT_COUNT(CAST(-1 AS smallint)) AS bits_minus_1_smallint, LEFT_SHIFT(1, 4) AS shl, RIGHT_SHIFT(256, 4) AS shr,
       GET_BIT(5, 0) AS bit_0, GET_BIT(5, 1) AS bit_1, SET_BIT(0, 3) AS set_3, SET_BIT(15, 0, 0) AS clear_0,
       LEFT_SHIFT(CAST(1 AS bigint), 40) AS shl_bigint, LEFT_SHIFT(CAST(1 AS tinyint), 8) AS shl_tinyint, BIT_COUNT(NULL) AS null_value;
```

```text
bits_7 bits_255 bits_minus_1_bigint bits_minus_1_smallint shl shr bit_0 bit_1 set_3 clear_0 shl_bigint    shl_tinyint null_value
------ -------- ------------------- --------------------- --- --- ----- ----- ----- ------- ------------- ----------- ----------
3      8        64                  16                    16  16  1     0     8     14      1099511627776 256         NULL

(1 row affected)
```

### H. The bitwise operators

<!-- example: tsql -->
```sql
SELECT 5 & 3 AS bit_and, 5 | 3 AS bit_or, 5 ^ 3 AS bit_xor, ~5 AS bit_not, 1 << 3 AS shift_left, 16 >> 2 AS shift_right;
```

```text
bit_and bit_or bit_xor bit_not shift_left shift_right
------- ------ ------- ------- ---------- -----------
1       7      6       -6      8          4

(1 row affected)
```

### I. Errors

Each in its own batch.

<!-- example: tsql -->
```sql
SELECT SQRT(-1) AS a;
GO
SELECT LOG(0) AS a;
GO
SELECT ASIN(2) AS a;
GO
SELECT EXP(710) AS a;
GO
SELECT POWER(2, 31) AS a;
GO
SELECT ROUND(123.4567, -1) AS a;
GO
SELECT GET_BIT(5, 40) AS a;
GO
SELECT SET_BIT(5, 1, 2) AS a;
GO
SELECT ATN2(1, 1) AS a;
```

```text
Msg 50000, Level 16, State 1, Line 1
cannot take square root of a negative number
Msg 50000, Level 16, State 1, Line 1
cannot take logarithm of zero
Msg 8115, Level 16, State 1, Line 1
input is out of range
Msg 8115, Level 16, State 1, Line 1
value out of range: overflow
Msg 8115, Level 16, State 1, Line 1
Arithmetic overflow error converting expression to data type int.
Msg 8115, Level 16, State 1, Line 1
Arithmetic overflow error converting expression to data type numeric.
Msg 9838, Level 16, State 1, Line 1
Parameter 2 in function 'get_bit' is out of range 0 to 31.
Msg 9839, Level 16, State 1, Line 1
Parameter 3 in function 'set_bit' must be 0 or 1.
Msg 195, Level 16, State 1, Line 1
function atn2 with 2 arguments does not exist
```

## See also

[Logical functions](functions-logical.md) · [Conversion functions](functions-conversion.md) ·
[String functions](functions-string.md) · [SELECT](select.md)
