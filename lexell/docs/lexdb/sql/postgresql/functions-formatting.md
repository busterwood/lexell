# Formatting functions

`to_char`, `to_number`, `to_date` and `to_timestamp`: numbers and dates to text by a template, and back.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
to_char ( timestamp | timestamptz | date | interval, template ) → text
to_char ( number, template ) → text
to_number ( text, template ) → numeric
to_date ( text, template ) → date
to_timestamp ( text, template ) → timestamptz
```

## Functions

`to_char` of a date or time
: The value as text by *template*. The common patterns: `YYYY`, `YY`, `MM`, `Month`, `Mon`, `DD`, `DDD` (day of
  year), `D` (day of week, Sunday 1), `Day`, `Dy`, `HH24`, `HH12` (or `HH`), `MI`, `SS`, `MS`, `US`, `AM` / `PM`,
  `Q`, `WW`, `IW`, `TZ`. `FM` before a pattern drops its padding; text in double quotes is copied. `MONTH`,
  `Month` and `month` give the name in that case.

`to_char` of a number
: The number as text by *template*: `9` a digit (blank if a leading zero), `0` a digit (always shown), `.` or `D`
  the point, `,` or `G` a group separator, `S` or `MI` the sign, `PR` angle brackets for a negative, `FM` no
  padding, `EEEE` scientific notation. A number too long for the template shows as `#`.

`to_number`
: The number in text read by the same patterns.

`to_date`, `to_timestamp`
: A date or a `timestamptz` read from text by the date patterns. Separators in the text need not match the
  template's.

## Remarks

- The result of `to_char` of a number has a place for the sign at the start, as in PostgreSQL: use `FM` to drop it.
- `to_timestamp` reads the text in the session's time zone unless it holds a `TZH`/`TZM` offset.

## Differences from PostgreSQL

None known. Besides the patterns above, `J`, `CC`, `RM`, `Y,YYY`, `SSSS`, `TZH`, `TZM`, `OF`, `FF1` ... `FF6`, the
`TH` suffix and the number patterns `RN`, `MI` and `SG` were checked. Other characters are copied as text.

## Examples

### A. Dates and times to text

<!-- example: postgresql -->
```sql
SELECT to_char(TIMESTAMP '2026-03-01 14:05:09.123', 'YYYY-MM-DD HH24:MI:SS.MS') AS iso,
       to_char(TIMESTAMP '2026-03-01 14:05:09', 'Dy DD Mon YYYY HH12:MI AM') AS short,
       to_char(DATE '2026-03-01', 'FMDay, FMDD FMMonth YYYY') AS long;
```

```text
           iso           |          short           |         long
-------------------------+--------------------------+----------------------
 2026-03-01 14:05:09.123 | Sun 01 Mar 2026 02:05 PM | Sunday, 1 March 2026
(1 row)
```

### B. More date patterns

<!-- example: postgresql -->
```sql
SELECT to_char(DATE '2026-03-01', 'Q') AS quarter, to_char(DATE '2026-03-01', 'DDD') AS day_of_year,
       to_char(DATE '2026-03-01', 'IW') AS iso_week, to_char(DATE '2026-03-01', 'D') AS dow,
       to_char(DATE '2026-03-01', '"Week" WW "of" YYYY') AS quoted, to_char(DATE '2026-03-01', 'MONTH') AS upper;
```

```text
 quarter | day_of_year | iso_week | dow |     quoted      |   upper
---------+-------------+----------+-----+-----------------+-----------
 1       | 060         | 09       | 1   | Week 09 of 2026 | MARCH
(1 row)
```

### C. Time zones and intervals

<!-- example: postgresql -->
```sql
SELECT to_char(TIMESTAMPTZ '2026-03-01 12:00+00', 'HH24:MI TZ') AS utc,
       to_char(INTERVAL '26 hours 5 minutes', 'HH24:MI') AS hours;
```

```text
    utc    | hours
-----------+-------
 12:00 UTC | 26:05
(1 row)
```

### D. Numbers to text

<!-- example: postgresql -->
```sql
SELECT to_char(1234.5, '9999.99') AS a, to_char(1234.5, 'FM9,999.00') AS b, to_char(7, '000') AS c,
       to_char(-12.3, 'S999.9') AS d, to_char(-12.3, '999.9PR') AS e, to_char(123456, '9.99EEEE') AS f,
       to_char(12345, '999') AS too_long;
```

```text
    a     |    b     |  c   |   d    |    e    |     f     | too_long
----------+----------+------+--------+---------+-----------+----------
  1234.50 | 1,234.50 |  007 |  -12.3 |  <12.3> |  1.23e+05 |  ###
(1 row)
```

### E. Text to numbers

<!-- example: postgresql -->
```sql
SELECT to_number('1,234.50', '9,999.99') AS a, to_number('-42', 'S99') AS b, to_number('$ 99.5', 'L99.9') AS c;
```

```text
    a    |  b  |  c
---------+-----+------
 1234.50 | -42 | 99.5
(1 row)
```

### F. Text to dates and timestamps

<!-- example: postgresql -->
```sql
SELECT to_date('01/03/2026', 'DD/MM/YYYY') AS d, to_date('1 March 2026', 'DD Month YYYY') AS d2,
       to_timestamp('2026-03-01 14:05', 'YYYY-MM-DD HH24:MI') AS ts, to_timestamp('20260301', 'YYYYMMDD') AS ts2;
```

```text
     d      |     d2     |           ts           |          ts2
------------+------------+------------------------+------------------------
 2026-03-01 | 2026-03-01 | 2026-03-01 14:05:00+00 | 2026-03-01 00:00:00+00
(1 row)
```

### G. Errors

<!-- example: postgresql -->
```sql
SELECT to_date('2026-13-01', 'YYYY-MM-DD');
SELECT to_number('abc', '999');
```

```text
ERROR:  date/time field value out of range: "2026-13-1"
ERROR:  invalid input syntax for type numeric: " "
```

## See also

[Date and time functions](functions-datetime.md) · [String conversion functions](functions-string-convert.md) ·
[Date and time types](data-types-datetime.md)
