# Numeric types (Transact-SQL)

Integers, exact decimal numbers, money and floating-point numbers.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
tinyint
smallint
int | integer
bigint
decimal [ ( precision [ , scale ] ) ]
numeric [ ( precision [ , scale ] ) ]
money
smallmoney
float [ ( n ) ]
real
```

## Arguments

`tinyint`, `smallint`, `int`, `bigint`
: Integers of 1, 2, 4 and 8 bytes. `tinyint` is 0 to 255, `smallint` -32768 to 32767, `int` -2147483648 to
  2147483647, `bigint` -9223372036854775808 to 9223372036854775807. A value out of range for `smallint`, `int` or
  `bigint` is error 8115.

`decimal`, `numeric`
: The same type. An exact decimal number with *precision* significant digits (1 to 38, default 18) and *scale*
  digits after the point (0 to *precision*, default 0). A value is rounded to the scale, half away from zero; one
  with too many digits before the point is error 8115.

`money`, `smallmoney`
: Exact decimals with four places: lexdb keeps `money` as `numeric(19,4)` and `smallmoney` as `numeric(10,4)`.

`float`, `real`
: Binary floating point (IEEE 754) of 8 and 4 bytes. `float(n)` is `real` for *n* up to 24 and `float` above;
  `float` alone is `float(53)`.

## Remarks

- A literal without a point or exponent is an `int` (or a `bigint` when it does not fit); `1.5` is a `decimal`;
  `1e0` is a `float`.
- Integer division truncates toward zero (`7 / 2` is 3, `-7 / 2` is -3) and `%` takes the sign of the left operand
  (`-7 % 3` is -1). Division or `%` by zero is error 8134. `int` arithmetic that does not fit is error 8115.
- An integer with a `decimal` gives a `decimal`; anything with a `float` gives a `float`; an integer with `money`
  gives `money`. The quotient of two decimals has at least six places: see the differences below.
- Casting a `decimal` or a `float` to an integer cuts toward zero (`CAST(2.9 AS int)` is 2, `CAST(-2.5 AS int)` is
  -2). `ROUND` rounds half away from zero.
- A character value is converted to a number when it meets one in arithmetic or in a comparison: `'12' + 1` is 13.
  A string that is not a number is error 245.
- Booleans, floats and large numbers print as the client driver prints them: a `float` as `1.0E10` or `0.1`, in
  JDBC (sqlcmd uses its own format).
- `bit` is on [its own page](data-types-other.md).

## Differences from SQL Server

- **`tinyint` is not range-checked.** `CAST(256 AS tinyint)` is 256 and `CAST(-1 AS tinyint)` is -1; a column of
  type `tinyint` stores 256 and -1 as well. (`smallint` is checked: 8115.)
- **`smallmoney` is `numeric(10,4)`**: it takes up to 999999.9999 where SQL Server stops at 214748.3647, and it
  refuses a larger value with 8115 (`numeric field overflow`). `money` is `numeric(19,4)`, as SQL Server's range
  suggests, but is named `decimal` in `sys.columns` after `SELECT INTO`.
- **Scales of divisions differ.** `decimal(10,4) / 3` has scale 6, where SQL Server gives the larger scale (at
  least 6, up to 38 - precision). `@p / 100` for a `decimal(5,2)` variable has scale 20. `AVG` of a `decimal`
  has scale 6.
- **`1 + @p / 100` gives an integer.** With `DECLARE @p decimal(5,2) = 10`, `1 + @p / 100` is 1, where SQL Server
  gives 1.100000 (see [KNOWN-ISSUES](../../KNOWN-ISSUES.md)). The same sum with a constant (`1 + CAST(10 AS
  decimal(5,2)) / 100`) is right.
- `SUM` of `int` values does not raise 8115 when the total passes 2147483647; it returns the `bigint` total.
- `SELECT ... INTO` and `sp_describe_first_result_set` report every computed decimal as `decimal(38,6)` and a
  `tinyint` or `money` column as `smallint` or `decimal`.
- `real` arithmetic is done as `float`: `CAST(1 AS real) / 3` is 0.3333333333333333, where SQL Server gives
  0.33333334. A `real` column keeps the 4-byte value.
- `DATALENGTH` of a number gives sizes that are not SQL Server's (4 for a `tinyint`, 0 for a `real`).
- `CAST('yes' AS bit)` is 1, not error 245.
- `SQRT(-1)` is error 50000 (`cannot take square root of a negative number`; SQL Server: 3623 or NULL by session
  setting), and a `float` overflow such as `1e308 * 10` is 8115 with a long message.

## Examples

### A. Integer types and their ranges

<!-- example: tsql -->
```sql
SELECT CAST(255 AS tinyint) AS t, CAST(32767 AS smallint) AS s, CAST(2147483647 AS int) AS i,
       CAST(9223372036854775807 AS bigint) AS b;
GO
SELECT CAST(32768 AS smallint);
GO
SELECT CAST(2147483648 AS int);
```

```text
t   s     i          b
--- ----- ---------- -------------------
255 32767 2147483647 9223372036854775807

(1 row affected)

Msg 8115, Level 16, State 1, Line 1
smallint out of range
Msg 8115, Level 16, State 1, Line 1
integer out of range
```

### B. Integer division and remainder

<!-- example: tsql -->
```sql
SELECT 7 / 2 AS q, 7 % 2 AS r, -7 / 2 AS neg_q, -7 % 3 AS neg_r, 7.0 / 2 AS d1, 7 / 2.0 AS d2;
GO
SELECT 2147483647 + 1;
GO
SELECT 1 % 0;
```

```text
q r neg_q neg_r d1       d2
- - ----- ----- -------- --------
3 1 -3    -1    3.500000 3.500000

(1 row affected)

Msg 8115, Level 16, State 1, Line 1
Arithmetic overflow error converting expression to data type int.
Msg 8134, Level 16, State 1, Line 1
Divide by zero error encountered.
```

### C. decimal: rounding to the scale

A value is rounded to the column's scale; one with too many digits before the point is refused.

<!-- example: tsql -->
```sql
CREATE TABLE price (item varchar(5), amount decimal(7,2));
INSERT INTO price VALUES ('a', 12345.678), ('b', 0.005), ('c', -0.005);
SELECT * FROM price;
GO
INSERT INTO price VALUES ('d', 123456.7);
GO
SELECT CAST(123.456 AS decimal(5,1)) AS rounds, CAST(-123.456 AS decimal(5,1)) AS neg, CAST(1.9999 AS decimal(5,2)) AS two;
```

```text
(3 rows affected)

item amount
---- --------
a    12345.68
b    0.01
c    -0.01

(3 rows affected)

Msg 8115, Level 16, State 1, Line 1
numeric field overflow: a field with precision 7, scale 2 must round to an absolute value less than 10^5
rounds neg    two
------ ------ ----
123.5  -123.5 2.00

(1 row affected)
```

### D. The size of a decimal

<!-- example: tsql -->
```sql
SELECT CAST(12345678901234567890123456789012345678 AS decimal(38,0)) AS d38;
GO
SELECT CAST(1 AS decimal(39,0));
GO
SELECT CAST(12.5 AS decimal(3,2));
```

```text
d38
--------------------------------------
12345678901234567890123456789012345678

(1 row affected)

Msg 50000, Level 16, State 1, Line 1
NUMERIC precision 39 must be between 1 and 38
Msg 8115, Level 16, State 1, Line 1
numeric field overflow: a field with precision 3, scale 2 must round to an absolute value less than 10^1
```

### E. Division of decimals, and the type of an expression

<!-- example: tsql -->
```sql
SELECT CAST(1 AS decimal(10,4)) / 3 AS third, CAST(1 AS decimal(38,10)) / 3 AS third38, 10 / 4.0 AS ratio;
GO
SELECT CAST(1.25 AS decimal(5,2)) * CAST(1.5 AS decimal(5,2)) AS product,
       CAST(1.25 AS decimal(5,2)) + CAST(1.5 AS decimal(10,4)) AS total;
```

```text
third    third38      ratio
-------- ------------ --------
0.333333 0.3333333333 2.500000

(1 row affected)

product total
------- ------
1.8750  2.7500

(1 row affected)
```

### F. Converting to an integer

<!-- example: tsql -->
```sql
SELECT CAST(2.5 AS int) AS a, CAST(-2.5 AS int) AS b, CAST(2.9 AS int) AS c, ROUND(2.5, 0) AS rounded,
       ROUND(-2.5, 0) AS neg_rounded;
```

```text
a b  c rounded neg_rounded
- -- - ------- -----------
2 -2 2 3.0     -3.0

(1 row affected)
```

### G. float and real

<!-- example: tsql -->
```sql
CREATE TABLE sc (id int IDENTITY(1,1), v real, f float);
INSERT INTO sc (v, f) VALUES (0.1, 0.1), (16777217, 16777217), (1.5e38, 1e-5);
SELECT id, v, f FROM sc;
GO
SELECT CAST(1 AS float) / 3 AS f, 1e0 + 0.1 AS sum_f, CAST(1.5 AS float(24)) AS f24;
```

```text
(3 rows affected)

id v           f
-- ----------- -----------
1  0.1         0.1
2  1.6777216E7 1.6777217E7
3  1.5E38      1.0E-5

(3 rows affected)

f                  sum_f f24
------------------ ----- ---
0.3333333333333333 1.1   1.5

(1 row affected)
```

### H. money

<!-- example: tsql -->
```sql
CREATE TABLE m (a money, b smallmoney);
INSERT INTO m VALUES (1234.5678, 214748.3647);
SELECT a, b, a * 2 AS dbl, CAST(a AS varchar(20)) AS txt FROM m;
GO
INSERT INTO m VALUES (1, 1000000);
```

```text
(1 row affected)

a         b           dbl       txt
--------- ----------- --------- ---------
1234.5678 214748.3647 2469.1356 1234.5678

(1 row affected)

Msg 8115, Level 16, State 1, Line 1
numeric field overflow: a field with precision 10, scale 4 must round to an absolute value less than 10^6
```

### I. Numbers and strings

<!-- example: tsql -->
```sql
SELECT CAST('12' AS int) + 1 AS x, '12' + 1 AS y, CAST('1e3' AS float) AS z, CAST(' 7 ' AS int) AS w;
GO
SELECT CAST('abc' AS int);
```

```text
x  y  z      w
-- -- ------ -
13 13 1000.0 7

(1 row affected)

Msg 245, Level 16, State 1, Line 1
Conversion failed when converting the varchar value 'abc' to data type int.
```

### J. The decimal quotient under +

<!-- example: tsql -->
```sql
DECLARE @p decimal(5,2) = 10;
SELECT 1 + @p / 100 AS variable, 1 + CAST(10 AS decimal(5,2)) / 100 AS constant;
```

```text
variable constant
-------- --------
1        1.100000

(1 row affected)
```

### K. tinyint is not range-checked

<!-- example: tsql -->
```sql
CREATE TABLE tt (a tinyint, b smallint);
INSERT INTO tt VALUES (255, 32767), (256, 1), (-1, 1);
SELECT * FROM tt;
GO
INSERT INTO tt VALUES (1, 32768);
```

```text
(3 rows affected)

a   b
--- -----
255 32767
256 1
-1  1

(3 rows affected)

Msg 8115, Level 16, State 1, Line 1
smallint out of range
```

## See also

[Other types](data-types-other.md), [Character types](data-types-character.md),
[Mathematical functions](functions-math.md), [CAST and CONVERT](functions-conversion.md),
[Operators](operators.md)
