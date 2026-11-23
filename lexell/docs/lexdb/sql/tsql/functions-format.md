# FORMAT (Transact-SQL)

Formats a number or a date as text, with a .NET format string and a culture.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
FORMAT ( value, format [, culture ] ) → nvarchar
```

## Arguments

*value*
: A number (`int`, `bigint`, `decimal`, `float`, `real`, `money`) or a date and time (`date`, `datetime`, `datetime2`,
  `datetimeoffset`). A string is error 8116.

*format*
: A .NET format string: a standard one (one letter, with a precision for numbers) or a custom one (see below).
  An empty string gives the number's plain text, or for a date the `G` format.

*culture*
: `'en-US'` (the default) or `'de-DE'` (also `'de'`). Any other name is read as `en-US`.

## Remarks

The result is NULL when *value* or *format* is NULL, and when .NET would refuse the format (a letter the type does not
take, such as `'D'` for a decimal, or `'Q'` for a date).

**Standard numeric formats.** A letter and an optional precision:

| Format | Result for `1234567.891` (en-US) |
|---|---|
| `N2` | `1,234,567.89`: a group separator, 2 decimals (`N` alone is `N2`) |
| `F1` | `1234567.9`: no group separator |
| `D5` | whole numbers only: at least 5 digits, `00042` |
| `X`, `x4` | whole numbers only: hexadecimal, upper or lower case (`FF`, `00ff`) |
| `P1` | a percentage: the value times 100, `25.6%` for `0.256` |
| `C` | currency: `$1,234.50`, and `($1,234.50)` for a negative value |
| `E3` | scientific: `1.235E+004` |
| `G3` | general: the shorter of fixed and scientific, 3 significant digits |

**Custom numeric formats.** `0` is a digit that always shows, `#` one that shows where it is significant, `,` between
placeholders groups the integer part, `.` is the decimal point, `%` multiplies by 100, text in quotes or after `\` is
written as it is. Only the first section (before a `;`) is used.

**Standard date formats** (en-US):

| Format | Pattern | Format | Pattern |
|---|---|---|---|
| `d` | `M/d/yyyy` | `D` | `dddd, MMMM d, yyyy` |
| `t` | `h:mm tt` | `T` | `h:mm:ss tt` |
| `f` | `dddd, MMMM d, yyyy h:mm tt` | `F` | `dddd, MMMM d, yyyy h:mm:ss tt` |
| `g` | `M/d/yyyy h:mm tt` | `G` | `M/d/yyyy h:mm:ss tt` |
| `M` or `m` | `MMMM d` | `Y` or `y` | `MMMM yyyy` |
| `s` | `yyyy-MM-ddTHH:mm:ss` | `u` | `yyyy-MM-dd HH:mm:ssZ` |

**Custom date formats:** `yy`, `yyyy`; `M`, `MM`, `MMM`, `MMMM`; `d`, `dd`, `ddd`, `dddd`; `H`, `HH`; `h`, `hh`;
`m`, `mm`; `s`, `ss`; `f` to `fffffff` (fraction digits) and `F` (without trailing zeros); `t`, `tt` (AM or PM);
text in quotes or after `\`; any other character as it is.

## Differences from SQL Server

- The culture `de-DE` changes the separators of numbers (`1.234.567,89`, currency `1.234,50 €`, percentage `25,6 %`),
  but not dates: month and day names stay English and the standard date formats keep the `en-US` patterns (`FORMAT(@d,
  'd', 'de-DE')` is `3/5/2026`; SQL Server gives `05.03.2026`). A custom pattern such as `dd.MM.yyyy` works. Other
  cultures are read as `en-US`.
- A custom numeric format with several sections is cut at the first `;`: `FORMAT(-5, '0;(0)')` is `-5` (SQL Server:
  `(5)`).
- Literal characters between digit placeholders are dropped: `FORMAT(123456789, '###-##-####')` is `123456789`
  (SQL Server: `123-45-6789`).
- `FORMAT` of a `time` value is NULL, whatever the format (example F).
- Digits are rounded half away from zero, as .NET does.

## Examples

### A. Standard numeric formats

<!-- example: tsql -->
```sql
SELECT FORMAT(1234567.891, 'N2') AS n2, FORMAT(1234567.891, 'N0') AS n0, FORMAT(1234567.891, 'F1') AS f1,
       FORMAT(0.256, 'P1') AS p1, FORMAT(1234.5, 'C') AS c, FORMAT(-1234.5, 'C') AS c_negative,
       FORMAT(42, 'D5') AS d5, FORMAT(255, 'X') AS x, FORMAT(255, 'x4') AS x4, FORMAT(12345.6789, 'E3') AS e3,
       FORMAT(0.000123, 'G3') AS g3;
```

```text
n2           n0        f1        p1    c         c_negative  d5    x  x4   e3         g3
------------ --------- --------- ----- --------- ----------- ----- -- ---- ---------- --------
1,234,567.89 1,234,568 1234567.9 25.6% $1,234.50 ($1,234.50) 00042 FF 00ff 1.235E+004 0.000123

(1 row affected)
```

### B. Numbers in the de-DE culture

<!-- example: tsql -->
```sql
SELECT FORMAT(1234567.891, 'N2', 'de-DE') AS n2, FORMAT(1234.5, 'C', 'de-DE') AS c, FORMAT(0.256, 'P1', 'de-DE') AS p1,
       FORMAT(1234.5, 'F2', 'en-US') AS en_us;
```

```text
n2           c          p1     en_us
------------ ---------- ------ -------
1.234.567,89 1.234,50 € 25,6 % 1234.50

(1 row affected)
```

### C. Custom numeric formats

<!-- example: tsql -->
```sql
SELECT FORMAT(1234.5, '#,##0.00') AS grouped, FORMAT(5, '000') AS padded, FORMAT(0.5, '0.#') AS optional_digit,
       FORMAT(1234.5, '#,###') AS rounded, FORMAT(0.256, '0.0%') AS percent_, FORMAT(1234.5, '$#,##0.00') AS dollars,
       FORMAT(12, '"No. "00') AS quoted_text;
```

```text
grouped  padded optional_digit rounded percent_ dollars   quoted_text
-------- ------ -------------- ------- -------- --------- -----------
1,234.50 005    0.5            1,235   25.6%    $1,234.50 No. 12

(1 row affected)
```

### D. Standard date formats

<!-- example: tsql -->
```sql
DECLARE @d datetime2 = '2026-03-05 14:07:09.123';
SELECT FORMAT(@d, 'd') AS d, FORMAT(@d, 'D') AS d_long, FORMAT(@d, 't') AS t, FORMAT(@d, 'T') AS t_long,
       FORMAT(@d, 'f') AS f, FORMAT(@d, 'g') AS g, FORMAT(@d, 'M') AS m, FORMAT(@d, 'Y') AS y,
       FORMAT(@d, 's') AS s, FORMAT(@d, 'u') AS u;
```

```text
d        d_long                  t       t_long     f                               g                m       y          s                   u
-------- ----------------------- ------- ---------- ------------------------------- ---------------- ------- ---------- ------------------- --------------------
3/5/2026 Thursday, March 5, 2026 2:07 PM 2:07:09 PM Thursday, March 5, 2026 2:07 PM 3/5/2026 2:07 PM March 5 March 2026 2026-03-05T14:07:09 2026-03-05 14:07:09Z

(1 row affected)
```

### E. Custom date formats

<!-- example: tsql -->
```sql
DECLARE @d datetime2 = '2026-03-05 14:07:09.123';
SELECT FORMAT(@d, 'yyyy-MM-dd') AS iso, FORMAT(@d, 'dd/MM/yy HH:mm:ss') AS day_first,
       FORMAT(@d, 'dddd, d MMMM yyyy') AS long_form, FORMAT(@d, 'ddd MMM') AS short_names,
       FORMAT(@d, 'h:mm tt') AS twelve_hour, FORMAT(@d, 'HH:mm:ss.fff') AS millis, FORMAT(@d, 'yyyy''Q''') AS quoted;
```

```text
iso        day_first         long_form              short_names twelve_hour millis       quoted
---------- ----------------- ---------------------- ----------- ----------- ------------ ------
2026-03-05 05/03/26 14:07:09 Thursday, 5 March 2026 Thu Mar     2:07 PM     14:07:09.123 2026Q

(1 row affected)
```

### F. Other date types, NULL and a time

<!-- example: tsql -->
```sql
SELECT FORMAT(CAST('2026-03-05' AS date), 'dd MMM yyyy') AS from_date, FORMAT(CAST('2026-03-05' AS datetime), 'yyyyMMdd') AS from_datetime,
       FORMAT(CAST(NULL AS int), 'N2') AS null_value, FORMAT(5, CAST(NULL AS varchar(5))) AS null_format,
       FORMAT(5, '') AS empty_format, FORMAT(CAST('14:07:09' AS time), 'hh\:mm') AS from_time;
```

```text
from_date   from_datetime null_value null_format empty_format from_time
----------- ------------- ---------- ----------- ------------ ---------
05 Mar 2026 20260305      NULL       NULL        5            NULL

(1 row affected)
```

### G. Dates in the de-DE culture

Only a custom pattern is followed; month and day names and the standard patterns stay English.

<!-- example: tsql -->
```sql
DECLARE @d datetime2 = '2026-03-05 14:07:09.123';
SELECT FORMAT(@d, 'd', 'de-DE') AS standard_d, FORMAT(@d, 'D', 'de-DE') AS standard_long,
       FORMAT(@d, 'dd.MM.yyyy', 'de-DE') AS custom, FORMAT(@d, 'MMMM', 'de-DE') AS month_name;
```

```text
standard_d standard_long           custom     month_name
---------- ----------------------- ---------- ----------
3/5/2026   Thursday, March 5, 2026 05.03.2026 March

(1 row affected)
```

### H. Rounding and the numeric types

<!-- example: tsql -->
```sql
SELECT FORMAT(1.5, 'N2') AS a, FORMAT(2.5, 'N0') AS b, FORMAT(0.125, 'N2') AS c, FORMAT(-0.001, 'N2') AS d,
       FORMAT(12345, 'N') AS int_, FORMAT(CAST(12345.678 AS float), 'N1') AS float_, FORMAT(CAST(12.5 AS money), 'C') AS money_,
       FORMAT(1234567890123, 'N0') AS bigint_;
```

```text
a    b c    d    int_      float_   money_ bigint_
---- - ---- ---- --------- -------- ------ -----------------
1.50 3 0.13 0.00 12,345.00 12,345.7 $12.50 1,234,567,890,123

(1 row affected)
```

### I. A format .NET refuses gives NULL

<!-- example: tsql -->
```sql
SELECT FORMAT(12.5, 'Z') AS unknown_letter, FORMAT(12.5, 'D') AS d_for_decimal, FORMAT(CAST('2026-03-05' AS date), 'Q') AS q_for_date;
```

```text
unknown_letter d_for_decimal q_for_date
-------------- ------------- ----------
NULL           NULL          NULL

(1 row affected)
```

### J. A string is not a value

<!-- example: tsql -->
```sql
SELECT FORMAT('abc', 'N2') AS a;
```

```text
Msg 8116, Level 16, State 1, Line 1
Argument data type varchar is invalid for argument 1 of format function.
```

### K. Custom numeric formats that lexdb does not follow

Both lines show lexdb's answer; SQL Server gives `(5)` and `123-45-6789`.

<!-- example: tsql -->
```sql
SELECT FORMAT(-5, '0;(0)') AS sections, FORMAT(123456789, '###-##-####') AS literals_between_digits;
```

```text
sections literals_between_digits
-------- -----------------------
-5       123456789

(1 row affected)
```

## See also

[String functions](functions-string.md) · [Conversion functions](functions-conversion.md) ·
[SELECT](select.md)
