# Numeric functions

Rounding, powers, logarithms, bit operations, buckets and trigonometry.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
ABS ( n )
CEIL ( n )
FLOOR ( n )
ROUND ( n [, integer ] )
TRUNC ( n [, integer ] )
MOD ( n2, n1 )
SIGN ( n )
POWER ( n2, n1 )
SQRT ( n )
EXP ( n )
LN ( n )
LOG ( n2, n1 )
BITAND ( expr1, expr2 )
WIDTH_BUCKET ( expr, min_value, max_value, num_buckets )
SIN ( n )   COS ( n )   TAN ( n )
ASIN ( n )  ACOS ( n )  ATAN ( n )  ATAN2 ( n1, n2 )
SINH ( n )  COSH ( n )  TANH ( n )
```

`ROUND` and `TRUNC` of dates are on the [date and time page](functions-datetime.md).

## Functions

`ABS`
: The absolute value.

`CEIL`, `FLOOR`
: The smallest integer not below *n*, and the largest integer not above it.

`ROUND`
: *n* rounded to *integer* decimal places (0 by default). A negative *integer* rounds to tens, hundreds and so on.
  Halves round away from zero: `ROUND(2.5)` is 3 and `ROUND(-15.5)` is -16. The arithmetic is decimal, so
  `ROUND(1.005, 2)` is 1.01.

`TRUNC`
: *n* cut (not rounded) at *integer* decimal places. A negative *integer* cuts to tens, hundreds and so on.

`MOD`
: The remainder of *n2* divided by *n1*, with the sign of *n2*. Decimals are allowed.

`SIGN`
: -1, 0 or 1.

`POWER`
: *n2* raised to the power *n1*.

`SQRT`
: The square root. A negative argument is ORA-01428.

`EXP`, `LN`
: *e* to the power *n*, and the natural logarithm. `LN` of 0 or less is ORA-01428.

`LOG`
: The logarithm of *n1* to the base *n2*. A base of 1 is ORA-01476 and an argument of 0 or less is ORA-01428.

`BITAND`
: The bitwise AND of two integers. A negative number is taken in two's complement: `BITAND(-1, 255)` is 255.

`WIDTH_BUCKET`
: The number of the bucket (1 to *num_buckets*) that *expr* falls into when the range *min_value* up to *max_value*
  is cut into equal buckets. A value below the range is bucket 0 and a value at or above the end is bucket
  *num_buckets* + 1. When *min_value* is greater than *max_value* the buckets run downwards.

`SIN`, `COS`, `TAN`, `ASIN`, `ACOS`, `ATAN`, `ATAN2`
: The trigonometric functions, in radians. `ASIN` and `ACOS` of a value outside -1 to 1 are ORA-01426.

`SINH`, `COSH`, `TANH`
: The hyperbolic functions.

All of these return NULL for a NULL argument. A character argument that looks like a number is converted (`SQRT('16')`
is 4), except in `ABS` (see Differences).

## Remarks

- `POWER`, `SQRT`, `EXP`, `LN` and `LOG` compute with `NUMBER`, not floating point; their results have up to 38
  digits.
- Division of two integers gives a decimal: `7 / 2` is 3.5. Division by zero is ORA-01476.
- `REMAINDER`, `NANVL`, `BIN_TO_NUM` and `PI` do not exist (ORA-00904).

## Differences from Oracle

- `MOD(5, 0)` is ORA-01476; Oracle returns 5.
- `CEIL(5)` and `FLOOR(5)` of an integer literal come back as `5.0`; a column or `TO_NUMBER(5)` gives `5`.
- The trigonometric and hyperbolic functions return floating-point values: `SIN(0)` is shown as `0.0` and
  `COS(0)` as `1.0`. Oracle returns a `NUMBER` (`0` and `1`). Round them for output.
- `ABS('-3')` is ORA-00904; Oracle converts the string. `ROUND(5.5, 1.9)` (a non-integer *integer*) is ORA-00904 too.
- `ASIN(2)` and `ACOS(2)` are ORA-01426; Oracle gives ORA-01428.
- `LOG(10)` with one argument is accepted and gives the base-10 logarithm; Oracle needs two arguments. `COT` and
  `CBRT` exist under their PostgreSQL names; they are not Oracle functions.
- A number with 38 digits can come out in exponent form (`1.4166666666666666666666666666666666667E00`); `ROUND` it
  to avoid that.
- The literal `.5` (no digit before the point) is ORA-01426; write `0.5`.

## Examples

### A. ABS, CEIL, FLOOR and SIGN

<!-- example: oracle -->
```sql
SELECT ABS(-5) AS abs_int, ABS(5.5) AS abs_dec, ABS(NULL) AS abs_null, CEIL(4.2) AS ceil_pos, CEIL(-4.2) AS ceil_neg,
       FLOOR(4.8) AS floor_pos, FLOOR(-4.2) AS floor_neg, SIGN(-12) AS sign_neg, SIGN(0) AS sign_zero, SIGN(7.5) AS sign_pos
FROM dual;
```

```text
ABS_INT ABS_DEC ABS_NULL CEIL_POS CEIL_NEG FLOOR_POS FLOOR_NEG SIGN_NEG SIGN_ZERO SIGN_POS
------- ------- -------- -------- -------- --------- --------- -------- --------- --------
      5     5.5                 5       -4         4        -5       -1         0        1

1 row selected.
```

### B. ROUND and TRUNC

<!-- example: oracle -->
```sql
SELECT ROUND(15.193) AS r0, ROUND(15.193, 1) AS r1, ROUND(15.193, -1) AS r_tens, ROUND(15.5) AS half_up,
       ROUND(-15.5) AS half_down, ROUND(2.5) AS two_half, ROUND(1234.5678, 2) AS r2, ROUND(1234.5678, -2) AS r_hundreds,
       ROUND(1.005, 2) AS decimal_exact
FROM dual;
SELECT TRUNC(15.79) AS t0, TRUNC(15.79, 1) AS t1, TRUNC(15.79, -1) AS t_tens, TRUNC(-15.79) AS neg, TRUNC(-15.79, 1) AS neg1,
       TRUNC(1234.5678, -2) AS t_hundreds
FROM dual;
```

```text
R0   R1 R_TENS HALF_UP HALF_DOWN TWO_HALF      R2 R_HUNDREDS DECIMAL_EXACT
-- ---- ------ ------- --------- -------- ------- ---------- -------------
15 15.2     20      16       -16        3 1234.57       1200          1.01

1 row selected.

T0   T1 T_TENS NEG  NEG1 T_HUNDREDS
-- ---- ------ --- ----- ----------
15 15.7     10 -15 -15.7       1200

1 row selected.
```

### C. MOD

<!-- example: oracle -->
```sql
SELECT MOD(11, 4) AS a, MOD(-11, 4) AS neg_dividend, MOD(11, -4) AS neg_divisor, MOD(11.5, 4) AS decimal_dividend,
       MOD(0, 5) AS zero, MOD(-5.5, 2) AS neg_decimal
FROM dual;
```

```text
A NEG_DIVIDEND NEG_DIVISOR DECIMAL_DIVIDEND ZERO NEG_DECIMAL
- ------------ ----------- ---------------- ---- -----------
3           -3           3              3.5    0        -1.5

1 row selected.
```

### D. POWER, SQRT, EXP, LN and LOG

<!-- example: oracle -->
```sql
SELECT POWER(2, 10) AS p1, POWER(2, -1) AS p2, POWER(2.5, 2) AS p3, POWER(9, 0.5) AS p4, POWER(-2, 3) AS p5,
       POWER(10, 20) AS p6, SQRT(16) AS s1, SQRT(2) AS s2, SQRT('16') AS s3
FROM dual;
SELECT EXP(0) AS e0, EXP(1) AS e1, EXP(-1) AS e_neg, LN(1) AS ln1, LN(EXP(2)) AS ln_exp, LN(10) AS ln10 FROM dual;
SELECT LOG(10, 100) AS log10, LOG(2, 8) AS log2_8, LOG(2, 1024) AS log2_1024, LOG(10, 2) AS log10_2 FROM dual;
```

```text
  P1  P2   P3 P4 P5                    P6 S1                S2 S3
---- --- ---- -- -- --------------------- -- ----------------- --
1024 0.5 6.25  3 -8 100000000000000000000  4 1.414213562373095  4

1 row selected.

E0                 E1              E_NEG LN1 LN_EXP               LN10
-- ------------------ ------------------ --- ------ ------------------
 1 2.7182818284590452 0.3678794411714423   0      2 2.3025850929940457

1 row selected.

LOG10 LOG2_8 LOG2_1024            LOG10_2
----- ------ --------- ------------------
    2      3        10 0.3010299956639812

1 row selected.
```

### E. BITAND and WIDTH_BUCKET

<!-- example: oracle -->
```sql
SELECT BITAND(6, 3) AS b1, BITAND(12, 10) AS b2, BITAND(5, 0) AS b3, BITAND(-1, 255) AS b4 FROM dual;
SELECT WIDTH_BUCKET(5, 0, 10, 5) AS middle, WIDTH_BUCKET(0, 0, 10, 5) AS at_start, WIDTH_BUCKET(10, 0, 10, 5) AS at_end,
       WIDTH_BUCKET(-1, 0, 10, 5) AS below, WIDTH_BUCKET(11, 0, 10, 5) AS above, WIDTH_BUCKET(5, 10, 0, 5) AS descending,
       WIDTH_BUCKET(3.99, 0, 10, 4) AS fraction
FROM dual;
```

```text
B1 B2 B3  B4
-- -- -- ---
 2  8  0 255

1 row selected.

MIDDLE AT_START AT_END BELOW ABOVE DESCENDING FRACTION
------ -------- ------ ----- ----- ---------- --------
     3        1      6     0     6          3        2

1 row selected.
```

### F. Trigonometric and hyperbolic functions

<!-- example: oracle -->
```sql
SELECT ROUND(SIN(1), 10) AS sin1, ROUND(COS(1), 10) AS cos1, ROUND(TAN(1), 10) AS tan1, ROUND(ASIN(0.5), 10) AS asin,
       ROUND(ACOS(0.5), 10) AS acos, ROUND(ATAN(2), 10) AS atan, ROUND(ATAN2(1, 2), 10) AS atan2
FROM dual;
SELECT ROUND(SINH(1), 10) AS sinh1, ROUND(COSH(1), 10) AS cosh1, ROUND(TANH(1), 10) AS tanh1,
       ROUND(ATAN(1) * 4, 10) AS pi_estimate
FROM dual;
SELECT SIN(0) AS sin0, COS(0) AS cos0 FROM dual;
```

```text
        SIN1         COS1         TAN1         ASIN         ACOS         ATAN       ATAN2
------------ ------------ ------------ ------------ ------------ ------------ -----------
0.8414709848 0.5403023059 1.5574077247 0.5235987756 1.0471975512 1.1071487178 0.463647609

1 row selected.

       SINH1        COSH1       TANH1  PI_ESTIMATE
------------ ------------ ----------- ------------
1.1752011936 1.5430806348 0.761594156 3.1415926536

1 row selected.

SIN0 COS0
---- ----
 0.0  1.0

1 row selected.
```

### G. Functions on columns

<!-- example: oracle -->
```sql
CREATE TABLE n (id NUMBER(5), x NUMBER(8,2));
INSERT INTO n VALUES (5, 5.25);
SELECT CEIL(id) AS ceil_id, FLOOR(id) AS floor_id, CEIL(x) AS ceil_x, FLOOR(x) AS floor_x, ROUND(x, 1) AS round_x,
       TRUNC(x) AS trunc_x, ABS(x) AS abs_x, SIGN(x) AS sign_x, MOD(id, 3) AS mod_id, POWER(id, 2) AS power_id
FROM n;
SELECT CEIL(5) AS ceil_literal, FLOOR(5) AS floor_literal, CEIL(TO_NUMBER(5)) AS ceil_to_number FROM dual;
```

```text
Table created.

1 row created.

CEIL_ID FLOOR_ID CEIL_X FLOOR_X ROUND_X TRUNC_X ABS_X SIGN_X MOD_ID POWER_ID
------- -------- ------ ------- ------- ------- ----- ------ ------ --------
      5        5      6       5     5.3       5  5.25      1      2       25

1 row selected.

CEIL_LITERAL FLOOR_LITERAL CEIL_TO_NUMBER
------------ ------------- --------------
         5.0           5.0              5

1 row selected.
```

### H. Errors, and functions that are not available

<!-- example: oracle -->
```sql
SELECT SQRT(-1) FROM dual;
SELECT LN(0) FROM dual;
SELECT LOG(1, 5) FROM dual;
SELECT ASIN(2) FROM dual;
SELECT 10 / 0 FROM dual;
SELECT MOD(5, 0) FROM dual;
SELECT ABS('-3') FROM dual;
SELECT REMAINDER(11, 4) FROM dual;
SELECT NANVL(1, 0) FROM dual;
SELECT PI FROM dual;
```

```text
ERROR:
ORA-01428: Argument is out of range.

ERROR:
ORA-01428: Argument 0 is out of range.

ERROR:
ORA-01476: divisor is equal to zero

ERROR:
ORA-01426: numeric overflow

ERROR:
ORA-01476: divisor is equal to zero

ERROR:
ORA-01476: divisor is equal to zero

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: "PI": invalid identifier
```

## See also

[Operators](operators.md), [Date and time functions](functions-datetime.md),
[Conversion functions](functions-conversion.md), [Number data types](data-types-number.md),
[NULL-handling functions](functions-null.md)
