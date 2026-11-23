# Conversion functions: CAST, CONVERT, TRY_CAST, TRY_CONVERT (Transact-SQL)

Converts a value from one data type to another, with an optional style for dates, and with versions that give NULL
instead of an error.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
CAST ( expression AS data_type [ ( length ) ] )
CONVERT ( data_type [ ( length ) ], expression [, style ] )
TRY_CAST ( expression AS data_type [ ( length ) ] )
TRY_CONVERT ( data_type [ ( length ) ], expression [, style ] )
```

## Arguments

*expression*
: The value to convert.

*data_type*
: The target type, with its length, or precision and scale: `varchar(10)`, `decimal(5, 2)`, `datetime2(3)`.

*style*
: A number that says how a date or time is written when it is converted to a string (table below).

## Functions

`CAST`
: Converts the value to the target type. An impossible conversion is an error: 245 or 241 for a string that is not a
  number or a date, 8115 for a value that is too large for the type, 8134 for a division by zero.

`CONVERT`
: The same, with the type first and an optional style. `CONVERT(varchar(10), d, 103)` writes a date as `dd/mm/yyyy`.

`TRY_CAST`, `TRY_CONVERT`
: As `CAST` and `CONVERT`, but give NULL where those would fail on the value (a string that is not a number, a date
  out of range, a value too large). They do not hide an error in the arguments themselves.

`PARSE`, `TRY_PARSE`
: Do not exist: a call is a syntax error (156).

## Styles lexdb knows

A style takes effect when a date, time or datetime is converted to `char`, `varchar`, `nchar` or `nvarchar`. A style
with a century (100 and up) writes four year digits; the same style below 100 writes two. Both forms are given here.

| Style | Result | Style | Result |
|---|---|---|---|
| 0 or 100 | `Mar  5 2026  2:07PM` | 8, 24 or 108 | `14:07:09` |
| 1 / 101 | `03/05/26` / `03/05/2026` | 10 / 110 | `03-05-26` / `03-05-2026` |
| 2 / 102 | `26.03.05` / `2026.03.05` | 11 / 111 | `26/03/05` / `2026/03/05` |
| 3 / 103 | `05/03/26` / `05/03/2026` | 12 / 112 | `260305` / `20260305` |
| 4 / 104 | `05.03.26` / `05.03.2026` | 20 or 120 | `2026-03-05 14:07:09` |
| 5 / 105 | `05-03-26` / `05-03-2026` | 21 or 121 | `2026-03-05 14:07:09.123` |
| 6 / 106 | `05 Mar 26` / `05 Mar 2026` | 23 | `2026-03-05` |
| 7 / 107 | `Mar 05, 26` / `Mar 05, 2026` | 126 | `2026-03-05T14:07:09.123` |
| | | 127 | `2026-03-05T14:07:09.123Z` |

Any other style number is error 281. A style 126 or 127 string leaves out the fraction when it is zero. The result is
cut to the length of the target type.

## Remarks

- **Data type precedence.** When an operator or a function gets two types, the one lower in this list is converted to
  the one higher: `datetime2`, `datetime`, `date`, `time`, `float`, `real`, `decimal`, `money`, `bigint`, `int`,
  `smallint`, `tinyint`, `bit`, `nvarchar`, `varchar`. So `'1' + 1` is the integer 2, and `'a' + 1` is error 245,
  because the string is the one converted. To join text and a number, convert the number: `'Total: ' + CAST(5 AS
  varchar(10))`, or use `CONCAT`.
- Integer division gives an integer: `10 / 4` is 2, `10 / 4.0` is 2.500000. A `decimal` and an `int` give a `decimal`;
  a `float` with anything gives a `float`.
- A string longer than the target `varchar(n)` is cut to *n* characters by `CAST` and `CONVERT`; inserting it into a
  column is error 2628.
- A decimal is rounded to the target scale (`CAST(12.345 AS decimal(5, 2))` is 12.35), an integer from a decimal is
  cut towards zero (`CAST(-3.99 AS int)` is -3).
- A conversion of NULL gives NULL.
- A string given to a date type is read in ISO form: `2026-03-05`, `2026-03-05 14:07:09`, `2026-03-05T14:07:09.123`.
- `CAST` of a `bit` accepts the strings `'true'`, `'false'` and `'0'`, `'1'`; any non-zero number is 1.

## Differences from SQL Server

- **Only the date styles above work.** The style of a conversion to a number or from a string is read and ignored:
  `CONVERT(date, '05/03/2026', 103)` and `CONVERT(date, '20260305', 112)` are error 241, and `CONVERT(varchar(20),
  CAST(1234.5678 AS money), 1)` is `1234.5678`, as style 0 is (SQL Server: `1,234.57` and `1234.57`).
  `TRY_CONVERT(date, '05/03/2026', 103)` is NULL. The styles 9, 13, 14, 22, 109, 113, 114 and the others of SQL Server
  not in the table are error 281.
- **Binary styles do not work.** `CONVERT(varchar(10), CAST('hi' AS varbinary(10)), 1)` gives `\x6869` (SQL Server:
  `0x6869`), and style 2 gives the same; `CONVERT(varbinary(10), '6869', 2)` gives the bytes of the text `6869` and
  not 0x6869 (example F). `CAST(varbinary AS varchar)` gives the hex text too (SQL Server: the bytes as characters).
- **Hex literals are numbers.** `SELECT 0x00ff` is `255`, and `CAST(0x00ff AS varbinary(2))` is error 50000. SQL
  Server's `0x00ff` is a `binary(2)`. Make binary values from strings: `CAST('hi' AS varbinary(10))`.
- **`tinyint` has no range:** `CAST(300 AS tinyint)` is 300 (SQL Server: error 8115),
  and `TRY_CAST(300 AS tinyint)` is 300 (SQL Server: NULL). `smallint` and `int` are checked. `TRY_CAST('12' AS
  decimal(2, 0))` is 12 (SQL Server: NULL).
- `CAST(x AS varchar)` without a length is not cut at 30 characters, where SQL Server cuts it.
- `CAST(0 AS datetime)` is error 50000 (SQL Server: 1900-01-01). Numbers do not convert to dates.
- `datetime + 1` and `datetime + 0.5` are error 195 (SQL Server adds days); use `DATEADD`. `date + 1` works here
  (SQL Server: error 206).
- A value `CAST` to `char(n)` is not padded with spaces: `'[' + CONVERT(char(8), 12) + ']'` is `[12]`
  (SQL Server: `[12      ]`).
- An invalid string for a number is error 245 for every number type, with PostgreSQL's wording (`invalid input syntax
  for type integer: "abc"`), where SQL Server uses 8114 for `decimal`, `float` and `bigint`. In a comparison of a
  string column with a number (`WHERE s = 12`) lexdb gives error 195 (`operator does not exist`), where SQL Server
  converts the column and fails with 245.
- A `datetime` column takes PostgreSQL's special strings: `INSERT ... VALUES ('tomorrow')` is accepted.
- **A literal in E notation is a `decimal`:** `5 / 2.0E0` is `2.500000` (SQL Server: the float 2.5), and `1 + 1.5E0`
  has type `decimal` in the catalog. Use `CAST(x AS float)` to make a float.
- `DECLARE @d decimal(5, 2) = 10; SELECT 1 + @d / 100` gives the integer 1: see [KNOWN-ISSUES](../../KNOWN-ISSUES.md).
- A `decimal` result from arithmetic has precision 38 and scale 6 in the catalog and in the driver, where SQL Server
  works out smaller ones; the values print with 6 decimals (`10 / 4.0` is `2.500000`).
- `SQL_VARIANT_PROPERTY` does not exist, and `sql_variant` is only a name for a plain value. To see a result type, use a view and `sys.columns`
  (example I).

## Examples

### A. CAST and CONVERT

<!-- example: tsql -->
```sql
SELECT CAST(42 AS varchar(10)) AS to_text, CAST('42' AS int) AS to_int, CAST(3.99 AS int) AS cut, CAST(-3.99 AS int) AS cut_negative,
       CAST('3.99' AS decimal(5, 2)) AS to_decimal, CAST(12.345 AS decimal(5, 2)) AS rounded, CAST(1 AS bit) AS to_bit,
       CAST(5 AS bit) AS any_nonzero, CAST('abc' AS char(5)) AS to_char, CAST(12345678901 AS bigint) AS to_bigint,
       CONVERT(int, '42') AS convert_int, CONVERT(decimal(5, 2), '3.14159') AS convert_decimal, CONVERT(bigint, 3.99) AS convert_bigint;
```

```text
to_text to_int cut cut_negative to_decimal rounded to_bit any_nonzero to_char to_bigint   convert_int convert_decimal convert_bigint
------- ------ --- ------------ ---------- ------- ------ ----------- ------- ----------- ----------- --------------- --------------
42      42     3   -3           3.99       12.35   1      1           abc     12345678901 42          3.14            3

(1 row affected)
```

### B. Dates to strings: styles 0 to 12

<!-- example: tsql -->
```sql
DECLARE @d datetime2(3) = '2026-03-05 14:07:09.123';
SELECT CONVERT(varchar(30), @d, 0) AS s0, CONVERT(varchar(30), @d, 1) AS s1, CONVERT(varchar(30), @d, 2) AS s2,
       CONVERT(varchar(30), @d, 3) AS s3, CONVERT(varchar(30), @d, 4) AS s4, CONVERT(varchar(30), @d, 5) AS s5,
       CONVERT(varchar(30), @d, 6) AS s6, CONVERT(varchar(30), @d, 7) AS s7, CONVERT(varchar(30), @d, 8) AS s8,
       CONVERT(varchar(30), @d, 10) AS s10, CONVERT(varchar(30), @d, 11) AS s11, CONVERT(varchar(30), @d, 12) AS s12;
```

```text
s0                  s1       s2       s3       s4       s5       s6        s7         s8       s10      s11      s12
------------------- -------- -------- -------- -------- -------- --------- ---------- -------- -------- -------- ------
Mar  5 2026  2:07PM 03/05/26 26.03.05 05/03/26 05.03.26 05-03-26 05 Mar 26 Mar 05, 26 14:07:09 03-05-26 26/03/05 260305

(1 row affected)
```

### C. Dates to strings: the styles with a century

<!-- example: tsql -->
```sql
DECLARE @d datetime2(3) = '2026-03-05 14:07:09.123';
SELECT CONVERT(varchar(30), @d, 100) AS s100, CONVERT(varchar(30), @d, 101) AS s101, CONVERT(varchar(30), @d, 103) AS s103,
       CONVERT(varchar(30), @d, 108) AS s108, CONVERT(varchar(30), @d, 112) AS s112, CONVERT(varchar(30), @d, 120) AS s120,
       CONVERT(varchar(30), @d, 121) AS s121, CONVERT(varchar(30), @d, 126) AS s126, CONVERT(varchar(30), @d, 127) AS s127;
```

```text
s100                s101       s103       s108     s112     s120                s121                    s126                    s127
------------------- ---------- ---------- -------- -------- ------------------- ----------------------- ----------------------- ------------------------
Mar  5 2026  2:07PM 03/05/2026 05/03/2026 14:07:09 20260305 2026-03-05 14:07:09 2026-03-05 14:07:09.123 2026-03-05T14:07:09.123 2026-03-05T14:07:09.123Z

(1 row affected)
```

### D. A style on a date, a cut, and a style that does not exist

The result is cut to the length of the target type, so `varchar(10)` with style 120 keeps the date.

<!-- example: tsql -->
```sql
SELECT CONVERT(varchar(30), CAST('2026-03-05' AS date), 103) AS date_103, CONVERT(varchar(30), CAST('14:07:09' AS time), 108) AS time_108,
       CONVERT(varchar(10), CAST('2026-03-05 14:07:09' AS datetime), 120) AS cut_to_date,
       CONVERT(varchar(30), CAST('2026-03-05 14:07:09.5' AS datetime2(1)), 126) AS iso_with_fraction,
       CONVERT(varchar(30), CAST('2026-03-05 14:07:09' AS datetime), 126) AS iso_without;
GO
SELECT CONVERT(varchar(30), CAST('2026-03-05' AS date), 109) AS not_a_style;
```

```text
date_103   time_108 cut_to_date iso_with_fraction       iso_without
---------- -------- ----------- ----------------------- -------------------
05/03/2026 14:07:09 2026-03-05  2026-03-05T14:07:09.500 2026-03-05T14:07:09

(1 row affected)

Msg 281, Level 16, State 1, Line 1
109 is not a valid style number when converting from datetime to a character string.
```

### E. Strings to dates

The ISO forms work, with and without a style 121 or 126.

<!-- example: tsql -->
```sql
SELECT CONVERT(date, '2026-03-05') AS iso_date, CONVERT(datetime, '2026-03-05T14:07:09', 126) AS style_126,
       CONVERT(datetime2, '2026-03-05 14:07:09.123', 121) AS style_121, CAST('14:07:09.5' AS time(1)) AS time_,
       CAST('2026-03-05 23:59:59' AS date) AS date_part_only;
GO
SELECT CONVERT(date, '05/03/2026', 103) AS day_first;
GO
SELECT CONVERT(date, '20260305') AS compact;
```

```text
iso_date   style_126             style_121                   time_      date_part_only
---------- --------------------- --------------------------- ---------- --------------
2026-03-05 2026-03-05 14:07:09.0 2026-03-05 14:07:09.1230000 14:07:09.5 2026-03-05

(1 row affected)

Msg 241, Level 16, State 1, Line 1
invalid input syntax for type date: "05/03/2026"
Msg 241, Level 16, State 1, Line 1
invalid input syntax for type date: "20260305"
```

### F. Styles that lexdb ignores: money and binary

<!-- example: tsql -->
```sql
SELECT CONVERT(varchar(20), CAST(1234.5678 AS money), 0) AS money_0, CONVERT(varchar(20), CAST(1234.5678 AS money), 1) AS money_1,
       CONVERT(varchar(10), CAST('hi' AS varbinary(10)), 1) AS binary_1, CONVERT(varchar(10), CAST('hi' AS varbinary(10)), 2) AS binary_2,
       CONVERT(varbinary(10), '6869', 2) AS from_hex_text, CAST('hi' AS varbinary(10)) AS bytes;
```

```text
money_0   money_1   binary_1 binary_2 from_hex_text bytes
--------- --------- -------- -------- ------------- -----
1234.5678 1234.5678 \x6869   \x6869   36383639      6869

(1 row affected)
```

### G. TRY_CAST and TRY_CONVERT

<!-- example: tsql -->
```sql
SELECT TRY_CAST('abc' AS int) AS not_a_number, TRY_CAST('42' AS int) AS number, TRY_CONVERT(int, '4x') AS partly,
       TRY_CONVERT(date, '2026-02-30') AS no_such_day, TRY_CONVERT(date, '2026-02-28') AS good_date,
       TRY_CAST(NULL AS int) AS null_value, TRY_CAST('1.5' AS decimal(5, 2)) AS decimal_, TRY_CAST(40000 AS smallint) AS too_big,
       TRY_CAST('abc' AS uniqueidentifier) AS not_a_guid, TRY_CONVERT(datetime, 'garbage') AS not_a_date;
```

```text
not_a_number number partly no_such_day good_date  null_value decimal_ too_big not_a_guid not_a_date
------------ ------ ------ ----------- ---------- ---------- -------- ------- ---------- ----------
NULL         42     NULL   NULL        2026-02-28 NULL       1.50     NULL    NULL       NULL

(1 row affected)
```

### H. Implicit conversion and data type precedence

The lower type is converted to the higher: the string to an `int`, the `int` to a `decimal` or a `float`.

<!-- example: tsql -->
```sql
SELECT '1' + 1 AS string_plus_int, 1 + '1' AS int_plus_string, '1' + '1' AS two_strings, 10 / 4 AS int_division,
       10 / 4.0 AS decimal_division, 10 % 4 AS modulo, 1 + 1.5 AS int_plus_decimal, 1 + CAST(1.5 AS float) AS int_plus_float,
       5 / CAST(2 AS float) AS float_division, 5 / 2.0E0 AS e_literal, 5.5 + '3' AS decimal_plus_string, 'Total: ' + CAST(5 AS varchar(10)) AS joined,
       CONCAT('Total: ', 5) AS concat_;
```

```text
string_plus_int int_plus_string two_strings int_division decimal_division modulo int_plus_decimal int_plus_float float_division e_literal decimal_plus_string joined   concat_
--------------- --------------- ----------- ------------ ---------------- ------ ---------------- -------------- -------------- --------- ------------------- -------- --------
2               2               11          2            2.500000         2      2.5              2.5            2.5            2.500000  8.5                 Total: 5 Total: 5

(1 row affected)
```

### I. The type of a result

A view over the expressions, and the catalog's view of its columns.

<!-- example: tsql -->
```sql
CREATE VIEW dbo.conversion_types AS
SELECT 1 + 1 AS int_int, CAST(1 AS bigint) + CAST(2 AS int) AS bigint_int, 1 + CAST(1.5 AS float) AS int_float, '5' * 2 AS string_int,
       CAST(1 AS int) + CAST(2.5 AS float) AS int_float_cast, CAST('2026-03-05' AS date) AS a_date, CAST(1 AS bit) AS a_bit;
GO
SELECT c.name, t.name AS type_name FROM sys.columns c JOIN sys.types t ON t.user_type_id = c.user_type_id
WHERE c.object_id = OBJECT_ID('dbo.conversion_types') ORDER BY c.column_id;
```

```text
name           type_name
-------------- ---------
int_int        int
bigint_int     bigint
int_float      float
string_int     int
int_float_cast float
a_date         date
a_bit          bit

(7 rows affected)
```

### J. Cutting and rounding

<!-- example: tsql -->
```sql
SELECT CAST('abcdef' AS varchar(3)) AS cut_text, CAST(123456 AS varchar(3)) AS cut_number, CAST(1.5 AS varchar(10)) AS decimal_text,
       CAST(CAST(1.5 AS float) AS varchar(10)) AS float_text, CAST(12.0 AS varchar(10)) AS decimal_scale_kept,
       CAST(CAST('2026-03-05 14:07:09.126' AS datetime2(3)) AS datetime) AS datetime_rounding,
       CAST(CAST('2026-03-05 14:07:09.123456' AS datetime2(6)) AS datetime2(2)) AS fewer_digits;
```

```text
cut_text cut_number decimal_text float_text decimal_scale_kept datetime_rounding       fewer_digits
-------- ---------- ------------ ---------- ------------------ ----------------------- ----------------------
abc      123        1.5          1.5        12.0               2026-03-05 14:07:09.127 2026-03-05 14:07:09.12

(1 row affected)
```

### K. A CASE takes the higher type

<!-- example: tsql -->
```sql
SELECT CASE WHEN 1 = 2 THEN 'x' ELSE 5 END AS int_wins;
GO
SELECT CASE WHEN 1 = 1 THEN 'x' ELSE 5 END AS text_cannot_be_int;
```

```text
int_wins
--------
5

(1 row affected)

Msg 245, Level 16, State 1, Line 1
invalid input syntax for type integer: "x"
```

### L. Conversion errors

Each in its own batch; an error in the batch ends it.

<!-- example: tsql -->
```sql
SELECT CAST('abc' AS int) AS a;
GO
SELECT CAST('abc' AS decimal(5, 2)) AS a;
GO
SELECT 'a' + 1 AS a;
GO
SELECT CAST('2026-13-45' AS date) AS a;
GO
SELECT CAST('abc' AS datetime) AS a;
GO
SELECT CAST(2147483648 AS int) AS a;
GO
SELECT CAST(99999 AS decimal(4, 0)) AS a;
GO
SELECT 2147483647 + 1 AS a;
GO
SELECT CAST(1 AS int) / 0 AS a;
GO
SELECT CAST('abc' AS bit) AS a;
```

```text
Msg 245, Level 16, State 1, Line 1
invalid input syntax for type integer: "abc"
Msg 245, Level 16, State 1, Line 1
invalid input syntax for type numeric: "abc"
Msg 245, Level 16, State 1, Line 1
invalid input syntax for type bigint: "a"
Msg 517, Level 16, State 1, Line 1
date/time field value out of range: "2026-13-45"
Msg 241, Level 16, State 1, Line 1
invalid input syntax for type timestamp: "abc"
Msg 8115, Level 16, State 1, Line 1
integer out of range
Msg 8115, Level 16, State 1, Line 1
numeric field overflow: a field with precision 4, scale 0 must round to an absolute value less than 10^4
Msg 8115, Level 16, State 1, Line 1
Arithmetic overflow error converting expression to data type int.
Msg 8134, Level 16, State 1, Line 1
Divide by zero error encountered.
Msg 245, Level 16, State 1, Line 1
invalid input syntax for type boolean: "abc"
```

### M. Conversions in a table

<!-- example: tsql -->
```sql
CREATE TABLE dbo.item (id int PRIMARY KEY, code varchar(5), price decimal(4, 2));
INSERT dbo.item VALUES (1, '12', 1.5);
GO
INSERT dbo.item VALUES (2, 'abcdef', 1.5);
GO
INSERT dbo.item VALUES (3, 'x', 123.45);
GO
INSERT dbo.item VALUES ('x', 'x', 1.5);
GO
SELECT id, code + 1 AS code_plus_one FROM dbo.item;
GO
SELECT id FROM dbo.item WHERE code = 12;
```

```text
(1 row affected)

Msg 2628, Level 16, State 1, Line 1
value too long for type character varying(5)
Msg 8115, Level 16, State 1, Line 1
numeric field overflow: a field with precision 4, scale 2 must round to an absolute value less than 10^2
Msg 245, Level 16, State 1, Line 1
invalid input syntax for type integer: "x"
id code_plus_one
-- -------------
1  13

(1 row affected)

id
--
1

(1 row affected)
```

### N. PARSE and TRY_PARSE

<!-- example: tsql -->
```sql
SELECT PARSE('5' AS int) AS a;
GO
SELECT TRY_PARSE('5' AS int) AS a;
```

```text
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'as'.
Msg 156, Level 15, State 1, Line 1
Incorrect syntax near the keyword 'as'.
```

## See also

[String functions](functions-string.md) · [FORMAT](functions-format.md) · [Logical functions](functions-logical.md) ·
[Mathematical functions](functions-math.md) · [SELECT](select.md)
