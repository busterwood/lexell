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
: A culture name, `'en-US'` by default. Dates have the month and day names, patterns, separators and AM or PM of
  46 cultures: `'en-US'`, `'en-GB'`, `'de-DE'`, `'fr-FR'`, `'es-ES'`, `'it-IT'`, `'nl-NL'`, `'pt-BR'`, `'ja-JP'`,
  `'sv-SE'` and 36 more (`'en-AU'`, `'de-AT'`, `'fr-CA'`, `'es-MX'`, `'zh-CN'`, `'ko-KR'`, `'pl-PL'`, `'ru-RU'`,
  `'tr-TR'`, `'th-TH'`, `'hi-IN'` and others; the language alone, such as `'de'`, takes the first of its cultures).
  Numbers follow 61 cultures (`'fr-FR'`, `'de-CH'`, `'en-IN'`, `'ru-RU'`,
  `'ja-JP'` and others: their separators, grouping and currency and percent patterns). A name of the form of a
  culture (a language of two or three letters, then parts of letters and digits joined by `-`, such as `'xx-YY'`)
  that lexdb does not know gets the invariant culture, as in SQL Server 2022. A name of any other form
  (`'english'`, `'en_US'`, `'x'`, an empty string) is error 9818.

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
written as it is, and other characters between the digit placeholders stay where they stand (`###-##-####`).
Up to three sections divided by `;` give the format of positive, negative and zero values: a value that rounds to zero
takes the zero section, the negative section shows no sign of its own, and an empty negative section is the first
section with a minus sign (example K).

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

- **Dates of 46 cultures only.** `'ar-SA'` (it uses the Hijri calendar, so every number differs) and the cultures
  outside the 46 get `en-US` dates (SQL Server gives their own). A name of the right form that no culture has gets
  the invariant culture, as in SQL Server (`Thursday, 05 March 2026` for `'D'` of `'xx-YY'`). A name of the wrong
  form is error 9818.
- **Numbers follow 61 cultures.** A real culture outside them is read as the invariant one (`,` and `.`, `¤` for the
  currency), where SQL Server has its own numbers for it.
- `FORMAT` of a `time` value is formatted as a .NET `TimeSpan`: the standard formats `c`, `t`, `T`, `g` and `G` and a
  custom format such as `hh\:mm` work, and any other standard letter is NULL (example F). The fraction has microsecond
  precision (`14:07:09.1234570`).
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
       FORMAT(5, '') AS empty_format, FORMAT(CAST('14:07:09' AS time), 'hh\:mm') AS from_time,
       FORMAT(CAST('14:07:09' AS time), 'c') AS time_c, FORMAT(CAST('14:07:09' AS time), 'd') AS time_d;
```

```text
from_date   from_datetime null_value null_format empty_format from_time time_c   time_d
----------- ------------- ---------- ----------- ------------ --------- -------- ------
05 Mar 2026 20260305      NULL       NULL        5            14:07     14:07:09 NULL

(1 row affected)
```

### G. Dates in other cultures

The names, patterns and separators of the culture are used: the standard formats `d`, `D`, `f`, `t`, `G` and the month
and day names.

<!-- example: tsql -->
```sql
DECLARE @d datetime2 = '2026-03-05 14:07:09.123';
SELECT FORMAT(@d, 'd', 'de-DE') AS standard_d, FORMAT(@d, 'D', 'de-DE') AS standard_long,
       FORMAT(@d, 'dd.MM.yyyy', 'de-DE') AS custom, FORMAT(@d, 'MMMM', 'de-DE') AS month_name;
SELECT FORMAT(@d, 'd', 'en-GB') AS en_gb, FORMAT(@d, 'd', 'fr-FR') AS fr_fr, FORMAT(@d, 'd', 'nl-NL') AS nl_nl,
       FORMAT(@d, 'd', 'ja-JP') AS ja_jp, FORMAT(@d, 'd', 'sv-SE') AS sv_se;
SELECT FORMAT(@d, 'D', 'fr-FR') AS fr_long, FORMAT(@d, 'D', 'es-ES') AS es_long, FORMAT(@d, 'D', 'ja-JP') AS ja_long,
       FORMAT(@d, 'MMMM', 'it-IT') AS it_month, FORMAT(@d, 'dddd', 'nl-NL') AS nl_day;
SELECT FORMAT(@d, 'f', 'en-GB') AS gb_f, FORMAT(@d, 'G', 'sv-SE') AS sv_g, FORMAT(@d, 'd', 'xx-XX') AS unknown_culture;
```

```text
standard_d standard_long            custom     month_name
---------- ------------------------ ---------- ----------
05.03.2026 Donnerstag, 5. März 2026 05.03.2026 März

(1 row affected)

en_gb      fr_fr      nl_nl    ja_jp      sv_se
---------- ---------- -------- ---------- ----------
05/03/2026 05/03/2026 5-3-2026 2026/03/05 2026-03-05

(1 row affected)

fr_long           es_long                    ja_long   it_month nl_day
----------------- -------------------------- --------- -------- ---------
jeudi 5 mars 2026 jueves, 5 de marzo de 2026 2026年3月5日 marzo    donderdag

(1 row affected)

gb_f                sv_g                unknown_culture
------------------- ------------------- ---------------
05 March 2026 14:07 2026-03-05 14:07:09 03/05/2026

(1 row affected)
```

A month name takes its genitive form beside a day of the month in the pattern, as .NET does for Polish, Czech,
Russian, Ukrainian, Greek and Finnish; `fi-FI` and `id-ID` write the time with `.` instead of `:`; `th-TH` counts years
in the Buddhist era (+543):

<!-- example: tsql -->
```sql
DECLARE @d datetime2 = '2026-03-05 14:07:09';
SELECT FORMAT(@d, 'D', 'ru-RU') AS ru_long, FORMAT(@d, 'MMMM', 'ru-RU') AS ru_month, FORMAT(@d, 'D', 'pl-PL') AS pl_long;
SELECT FORMAT(@d, 'G', 'fi-FI') AS fi_g, FORMAT(@d, 'T', 'id-ID') AS id_t, FORMAT(@d, 'd', 'th-TH') AS th_d;
SELECT FORMAT(@d, 'D', 'ar-SA') AS ar_sa, FORMAT(@d, 'D', 'xx-XX') AS unknown_culture;
SELECT FORMAT(@d, 'D', 'english') AS wrong_form;
```

```text
ru_long         ru_month pl_long
--------------- -------- ----------------------
5 марта 2026 г. Март     czwartek, 5 marca 2026

(1 row affected)

fi_g              id_t     th_d
----------------- -------- --------
5.3.2026 14.07.09 14.07.09 5/3/2569

(1 row affected)

ar_sa                   unknown_culture
----------------------- -----------------------
Thursday, March 5, 2026 Thursday, 05 March 2026

(1 row affected)

Msg 9818, Level 16, State 1, Line 5
The culture parameter 'english' provided in the function call is not supported.
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

### K. Sections and literals in a custom numeric format

Up to three sections give the positive, negative and zero formats. Characters between the digit placeholders stay
where they are.

<!-- example: tsql -->
```sql
SELECT FORMAT(-5, '0;(0)') AS sections, FORMAT(5, '0;(0)') AS positive, FORMAT(0, '0;(0);zero') AS zero_section,
       FORMAT(-0.001, '0.0;(0.0);zero') AS rounds_to_zero, FORMAT(-5, '0;;zero') AS empty_negative,
       FORMAT(123456789, '###-##-####') AS ssn, FORMAT(5551234567, '(###) ###-####') AS phone;
```

```text
sections positive zero_section rounds_to_zero empty_negative ssn         phone
-------- -------- ------------ -------------- -------------- ----------- --------------
(5)      5        zero         zero           -5             123-45-6789 (555) 123-4567

(1 row affected)
```

### L. Numbers in other cultures

<!-- example: tsql -->
```sql
SELECT FORMAT(1234567.891, 'N2', 'fr-FR') AS fr, FORMAT(1234567.891, 'N2', 'de-CH') AS de_ch,
       FORMAT(1234567.891, 'N2', 'en-IN') AS en_in, FORMAT(1234.5, 'C', 'ja-JP') AS ja_yen, FORMAT(1234.5, 'C', 'pt-BR') AS pt_br,
       FORMAT(0.256, 'P1', 'sv-SE') AS sv_p;
```

```text
fr           de_ch        en_in        ja_yen    pt_br       sv_p
------------ ------------ ------------ --------- ----------- ------
1 234 567,89 1’234’567.89 12,34,567.89 ¥1,234.50 R$ 1.234,50 25,6 %

(1 row affected)
```

### M. Culture names

A name of the form of a culture that is not known gets the invariant culture: `,` and `.` for numbers, `¤` for
currency, and the invariant date patterns. A name of another form is error 9818.

<!-- example: tsql -->
```sql
SELECT FORMAT(1234567.891, 'C', 'xx-YY') AS invariant_c, FORMAT(CAST('2026-03-05' AS date), 'D', 'xx-YY') AS invariant_date;
GO
SELECT FORMAT(5, 'N2', 'english') AS a;
GO
SELECT FORMAT(5, 'N2', 'en_US') AS a;
GO
```

```text
invariant_c   invariant_date
------------- -----------------------
¤1,234,567.89 Thursday, 05 March 2026

(1 row affected)

Msg 9818, Level 16, State 1, Line 1
The culture parameter 'english' provided in the function call is not supported.
Msg 9818, Level 16, State 1, Line 1
The culture parameter 'en_US' provided in the function call is not supported.
```

## See also

[String functions](functions-string.md) · [Conversion functions](functions-conversion.md) ·
[SELECT](select.md)
