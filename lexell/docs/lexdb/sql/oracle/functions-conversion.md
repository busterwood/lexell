# Conversion functions

`TO_CHAR`, `TO_NCHAR`, `TO_DATE`, `TO_TIMESTAMP`, `TO_TIMESTAMP_TZ`, `TO_NUMBER`, `TO_BOOLEAN` and `CAST`, and the
conversions lexdb makes by itself.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
TO_CHAR ( number [, format [, 'nlsparam' ] ] )
TO_CHAR ( datetime [, format [, 'nlsparam' ] ] )
TO_CHAR ( character )
TO_NCHAR ( n | datetime | char [, format ] )
TO_DATE ( char [, format ] )
TO_TIMESTAMP ( char [, format ] )
TO_TIMESTAMP_TZ ( char [, format ] )
TO_NUMBER ( expr [, format [, 'nlsparam' ] ] )
TO_BOOLEAN ( expr )
CAST ( expr AS type )
```

## Functions

`TO_CHAR` (number)
: The number as text. Without a format the shortest exact text is returned (`.5`, not `0.5`). The format elements
  that work are `9` (a digit, blank when a leading zero), `0` (a digit, zero shown), `.` and `D` (decimal point),
  `,` and `G` (group separator), `$`, `L` (currency, `$` here), `MI` (trailing minus), `PR` (negative in angle
  brackets), `S` (leading sign) and `FM` (no padding blanks). A number that does not fit is `#` characters. The result
  of a signed format starts with a blank for the sign.

`TO_CHAR` (date or timestamp)
: The date or timestamp as text, by the format elements `YYYY`, `YY`, `Y`, `RR`, `IYYY`, `MM`, `MON`, `MONTH`,
  `DD`, `DDD`, `D`, `DAY`, `DY`, `Q`, `WW`, `W`, `IW`, `J`, `HH`, `HH12`, `HH24`, `MI`, `SS`, `SSSSS`, `FF` and `FF1` to
  `FF9`, `AM`, `PM`, `A.M.`, `P.M.`, `AD`, `BC`, the suffixes `TH` and `SP`, the prefix `FM`, and text in double
  quotes. The case of `Day`, `Month` and `Mon` follows the format (`MONDAY`, `Monday`). Without a format the
  session's `NLS_DATE_FORMAT` (`DD-MON-RR`) is used, for timestamps `NLS_TIMESTAMP_FORMAT` (`DD-MON-RR HH.MI.SSXFF
  AM`), and for timestamps with a time zone `NLS_TIMESTAMP_TZ_FORMAT` (`DD-MON-RR HH.MI.SSXFF AM TZR`).
  The time zone elements take a `TIMESTAMP WITH TIME ZONE`: `TZH` is the offset's sign and hours (`+05`), `TZM` its
  minutes (`30`), `TZR` the zone (`+05:30`) and `TZD` its abbreviation (empty for an offset). On a value without a
  zone they are ORA-01821, as in Oracle.

`TO_NCHAR`
: As `TO_CHAR`, giving an `NVARCHAR2`.

`TO_DATE`
: A `DATE` from text by the same date elements. The format `RR` expands a two-digit year; a missing time is midnight
  and a missing day is the first. Text that does not fit the format gives ORA-01861 or a field error (ORA-01843,
  ORA-01830, ORA-01840, ORA-01850, ORA-01839, ORA-01858, ORA-01841).

`TO_TIMESTAMP`
: A `TIMESTAMP` from text; `FF` reads the fraction.

`TO_TIMESTAMP_TZ`
: A `TIMESTAMP WITH TIME ZONE` from text: `TZH` and `TZM` read the offset, `TZR` an offset or a region. Text without a
  zone is in the session's time zone. Without a format, the text is read by `NLS_TIMESTAMP_TZ_FORMAT`, then as ISO
  (`2026-11-23 14:05:09 +05:30`). An hour beyond 15 is ORA-01874, a minute beyond 59 ORA-01875, an unknown region
  ORA-01882.

`TO_NUMBER`
: A number from text, optionally by a format (`9`, `0`, `,`, `.`, `$`, `MI`, `PR`, `XX` for hexadecimal). Surrounding
  blanks are ignored and `1E3` is 1000. Anything else that is not a number is ORA-01722. An empty string is NULL.

`TO_BOOLEAN`
: A `BOOLEAN` (23ai) from text (`TRUE`, `T`, `YES`, `Y`, `ON`, `1`, and the opposites, in any case) or a number
  (0 is false, any other is true). Any other text is ORA-61800.

`CAST`
: Converts to `NUMBER(p,s)`, `INTEGER`, `FLOAT`, `BINARY_DOUBLE`, `VARCHAR2(n)`, `CHAR(n)`, `CLOB`, `RAW(n)`,
  `DATE`, `TIMESTAMP`, `TIMESTAMP WITH TIME ZONE` and `BOOLEAN`. Casting to a number type rounds half away from
  zero (`CAST(2.5 AS NUMBER(5,0))` is 3); to `VARCHAR2(n)` cuts the text to *n* characters.

## Remarks

- Implicit conversion: a character value used as a number is converted by `TO_NUMBER`, and a number or a date used as
  text by `TO_CHAR`: `1 + '2'` is 3, `10 || 5` is `105`. Text that is not a number is ORA-01722.
- A string put into a `DATE` column by `INSERT` is read in the form `YYYY-MM-DD` (see Differences).
- `TO_DSINTERVAL`, `TO_YMINTERVAL`, `TO_SINGLE_BYTE`, `TO_LOB`, `TO_BINARY_DOUBLE` and `TO_BINARY_FLOAT` do not
  exist (ORA-00904). `VALIDATE_CONVERSION`, and the `DEFAULT ... ON CONVERSION ERROR`
  clause of `TO_NUMBER`, `TO_DATE` and `CAST`, are ORA-00900.
- Where an interval is needed, write the literal: `INTERVAL '3 04:05:06' DAY TO SECOND`, `INTERVAL '2-5' YEAR TO MONTH`.

## Differences from Oracle

- Number format elements `EEEE`, `RN`, `rn`, `X` (`TO_CHAR(255, 'XXXX')`), `TM`, `B`, `V` and `C` are ORA-01481. Date
  elements `CC`, `E`, `RM`, `YEAR`, `SYYYY`, `DS`, `DL`, `TS` are ORA-01821.
- `TZR` of a value whose zone was a region shows its offset (`+01:00`; Oracle `EUROPE/BERLIN`), and `TZD` is empty
  (Oracle `CET`): lexdb keeps a region as the offset it had (see [date and time types](data-types-datetime.md)).
- `CAST(TRUE AS CHAR(5))` is `true ` and `LENGTH(TRUE)` is 1; Oracle gives `TRUE ` and 4.
- A `TIMESTAMP` literal converted to text has six fractional digits (`10.00.00.000000 AM +02:00`); Oracle gives it
  nine.
- `TO_CHAR(0, '999')` returns four blanks and `TO_CHAR(0, 'FM999')` an empty string; Oracle gives `0` in both.
- The third argument of `TO_CHAR` and `TO_NUMBER` (`NLS_DATE_LANGUAGE=GERMAN`, `NLS_NUMERIC_CHARACTERS`) is accepted and
  ignored: `TO_NUMBER('1,5', '9D9', 'NLS_NUMERIC_CHARACTERS='',.''')` is 15 (Oracle: 1.5).
- `DDSP` (spelled-out day) gives `03` instead of `THREE`.
- `TO_CHAR(INTERVAL '3 04:05:06' DAY TO SECOND)` is NULL.
- `TO_BOOLEAN(NULL)` is `false`; Oracle gives NULL.
- `INSERT INTO t (date_column) VALUES ('2026-11-23')` is accepted and `VALUES ('23-NOV-26')` is ORA-01861: the string is
  read as `YYYY-MM-DD`, not by the session's `NLS_DATE_FORMAT`. Oracle does the opposite. `TO_DATE('2026-11-23')`
  without a format uses `NLS_DATE_FORMAT` and is ORA-01861, as in Oracle.
- `INSERT ... VALUES ('2026-13-45')` into a `DATE` column is ORA-01881, not ORA-01843.
- `CAST(... AS INTERVAL DAY TO SECOND)` is ORA-00900. `TO_CHAR(.5)` and the literal `.5` are ORA-01426.
- The error texts are lexdb's own, shorter or different from Oracle's (ORA-01843 reads "An invalid month was
  specified"). The codes are Oracle's.
- A text inserted into a `TIMESTAMP WITH TIME ZONE` column is read as ISO (`'2026-03-15 10:00:00 +02:00'`), not by
  `NLS_TIMESTAMP_TZ_FORMAT`, as for a `DATE` column; `CAST` and `TO_TIMESTAMP_TZ` read the NLS format.

## Examples

### A. TO_CHAR of numbers

<!-- example: oracle -->
```sql
SELECT TO_CHAR(1234.567, '9999.99') AS nines, TO_CHAR(1234.567, '9,999.99') AS grouped, TO_CHAR(1234.567, '0000000.0000') AS zeros,
       TO_CHAR(-1234.567, '9,999.99') AS negative, TO_CHAR(0.5, '9.99') AS blank_zero, TO_CHAR(0.5, '0.99') AS zero_shown,
       TO_CHAR(0.5, 'FM9.99') AS fill_mode, TO_CHAR(12, '9999') AS padded
FROM dual;
SELECT TO_CHAR(1234567.891, '9G999G999D99') AS g_and_d, TO_CHAR(1234.5, '$9,999.99') AS dollar, TO_CHAR(1234.5, 'L9,999.99') AS currency,
       TO_CHAR(1234.5, 'FM9,999.00') AS fm_group, TO_CHAR(-5, '9999PR') AS angle, TO_CHAR(-5, '9999MI') AS minus_after,
       TO_CHAR(5, 'S9999') AS plus_sign, TO_CHAR(-5, 'S9999') AS minus_sign
FROM dual;
SELECT TO_CHAR(12345, '999') AS too_small, TO_CHAR(12345.678, '99999') AS rounded, TO_CHAR(5, '009') AS leading_zeros,
       TO_CHAR(12345.6789, '99,999.999') AS three_places, TO_CHAR(0.5, '90.99') AS zero_before_point, TO_CHAR(NULL, '999') AS null_in
FROM dual;
SELECT TO_CHAR(123.456) AS plain, TO_CHAR(0.5) AS no_leading_zero, TO_CHAR(-0.5) AS negative, TO_CHAR(1E10) AS large, TO_CHAR(100) AS integer_value
FROM dual;
```

```text
NINES    GROUPED   ZEROS         NEGATIVE  BLANK_ZERO ZERO_SHOWN FILL_MODE PADDED
-------- --------- ------------- --------- ---------- ---------- --------- ------
 1234.57  1,234.57  0001234.5670 -1,234.57   .50       0.50      .5           12

1 row selected.

G_AND_D       DOLLAR     CURRENCY   FM_GROUP ANGLE  MINUS_AFTER PLUS_SIGN MINUS_SIGN
------------- ---------- ---------- -------- ------ ----------- --------- ----------
 1,234,567.89  $1,234.50  $1,234.50 1,234.50    <5>    5-          +5        -5

1 row selected.

TOO_SMALL ROUNDED LEADING_ZEROS THREE_PLACES ZERO_BEFORE_POINT NULL_IN
--------- ------- ------------- ------------ ----------------- -------
####       12346   005           12,345.679    0.50

1 row selected.

PLAIN   NO_LEADING_ZERO NEGATIVE LARGE       INTEGER_VALUE
------- --------------- -------- ----------- -------------
123.456 .5              -.5      10000000000 100

1 row selected.
```

### B. TO_CHAR of dates and timestamps

<!-- example: oracle -->
```sql
SELECT TO_CHAR(DATE '2026-11-23', 'YYYY-MM-DD') AS iso, TO_CHAR(DATE '2026-11-23', 'DD/MM/YY') AS short_year,
       TO_CHAR(TIMESTAMP '2026-11-23 14:05:09', 'HH24:MI:SS') AS h24, TO_CHAR(TIMESTAMP '2026-11-23 14:05:09', 'HH:MI:SS AM') AS h12,
       TO_CHAR(TIMESTAMP '2026-11-23 14:05:09.123456', 'HH24:MI:SS.FF3') AS ff3, TO_CHAR(TIMESTAMP '2026-11-23 14:05:09.123456', 'FF') AS ff_default,
       TO_CHAR(TIMESTAMP '2026-11-23 14:05:09', 'SSSSS') AS seconds_of_day
FROM dual;
SELECT TO_CHAR(DATE '2026-11-23', 'DAY') AS day_upper, TO_CHAR(DATE '2026-11-23', 'Day') AS day_mixed, TO_CHAR(DATE '2026-11-23', 'DY') AS dy,
       TO_CHAR(DATE '2026-11-23', 'MON') AS mon, TO_CHAR(DATE '2026-11-23', 'MONTH') AS month_upper, TO_CHAR(DATE '2026-11-23', 'Month') AS month_mixed,
       TO_CHAR(DATE '2026-11-23', 'fmDay, DD Month YYYY') AS long_form, TO_CHAR(DATE '2026-11-23', 'Dy, DD Mon YYYY') AS rfc_form
FROM dual;
SELECT TO_CHAR(DATE '2026-11-23', 'Q') AS quarter, TO_CHAR(DATE '2026-11-23', 'WW') AS week_of_year, TO_CHAR(DATE '2026-11-23', 'W') AS week_of_month,
       TO_CHAR(DATE '2026-11-23', 'IW') AS iso_week, TO_CHAR(DATE '2026-11-23', 'DDD') AS day_of_year, TO_CHAR(DATE '2026-11-23', 'D') AS day_of_week,
       TO_CHAR(DATE '2026-11-23', 'IYYY') AS iso_year, TO_CHAR(DATE '2026-11-23', 'J') AS julian
FROM dual;
SELECT TO_CHAR(DATE '2026-11-03', 'DD') AS dd, TO_CHAR(DATE '2026-11-03', 'FMDD') AS fm_dd, TO_CHAR(DATE '2026-11-03', 'DDth') AS ordinal,
       TO_CHAR(DATE '2026-11-03', 'YYYY "year" Q') AS quoted_text, TO_CHAR(DATE '2026-11-23', 'YYYY-MM-DD"T"HH24:MI:SS') AS iso_8601,
       TO_CHAR(TIMESTAMP '2026-11-23 00:05:09', 'HH12:MI AM') AS midnight, TO_CHAR(DATE '2026-11-23') AS default_format
FROM dual;
```

```text
ISO        SHORT_YEAR H24      H12         FF3          FF_DEFAULT SECONDS_OF_DAY
---------- ---------- -------- ----------- ------------ ---------- --------------
2026-11-23 23/11/26   14:05:09 02:05:09 PM 14:05:09.123 123456000  50709

1 row selected.

DAY_UPPER DAY_MIXED DY  MON MONTH_UPPER MONTH_MIXED LONG_FORM                RFC_FORM
--------- --------- --- --- ----------- ----------- ------------------------ ----------------
MONDAY    Monday    MON NOV NOVEMBER    November    Monday, 23 November 2026 Mon, 23 Nov 2026

1 row selected.

QUARTER WEEK_OF_YEAR WEEK_OF_MONTH ISO_WEEK DAY_OF_YEAR DAY_OF_WEEK ISO_YEAR JULIAN
------- ------------ ------------- -------- ----------- ----------- -------- -------
4       47           4             48       327         2           2026     2461368

1 row selected.

DD FM_DD ORDINAL QUOTED_TEXT ISO_8601            MIDNIGHT DEFAULT_FORMAT
-- ----- ------- ----------- ------------------- -------- --------------
03 3     03rd    2026 year 4 2026-11-23T00:00:00 12:05 AM 23-NOV-26

1 row selected.
```

### C. TO_DATE and TO_TIMESTAMP

<!-- example: oracle -->
```sql
SELECT TO_CHAR(TO_DATE('2026-11-23', 'YYYY-MM-DD'), 'YYYY-MM-DD') AS iso, TO_CHAR(TO_DATE('23/11/26', 'DD/MM/RR'), 'YYYY-MM-DD') AS two_digit_year,
       TO_CHAR(TO_DATE('23 November 2026', 'DD Month YYYY'), 'YYYY-MM-DD') AS month_name, TO_CHAR(TO_DATE('Nov 5 2026', 'Mon DD YYYY'), 'YYYY-MM-DD') AS short_month,
       TO_CHAR(TO_DATE('20261123', 'YYYYMMDD'), 'YYYY-MM-DD') AS compact, TO_CHAR(TO_DATE('2026-333', 'YYYY-DDD'), 'YYYY-MM-DD') AS day_of_year,
       TO_CHAR(TO_DATE('2026-11', 'YYYY-MM'), 'YYYY-MM-DD') AS missing_day
FROM dual;
SELECT TO_CHAR(TO_DATE('2026-11-23 02:05:09 PM', 'YYYY-MM-DD HH:MI:SS PM'), 'HH24:MI') AS pm_time,
       TO_CHAR(TO_DATE('2026-11-23 14:05:09', 'YYYY-MM-DD HH24:MI:SS'), 'YYYY-MM-DD HH24:MI:SS') AS date_and_time
FROM dual;
SELECT TO_CHAR(TO_TIMESTAMP('2026-11-23 14:05:09.123456', 'YYYY-MM-DD HH24:MI:SS.FF'), 'YYYY-MM-DD HH24:MI:SS.FF6') AS microseconds,
       TO_CHAR(TO_TIMESTAMP('23-NOV-26 02.05.09.5 PM', 'DD-MON-RR HH.MI.SS.FF AM'), 'HH24:MI:SS.FF1') AS twelve_hour
FROM dual;
```

```text
ISO        TWO_DIGIT_YEAR MONTH_NAME SHORT_MONTH COMPACT    DAY_OF_YEAR MISSING_DAY
---------- -------------- ---------- ----------- ---------- ----------- -----------
2026-11-23 2026-11-23     2026-11-23 2026-11-05  2026-11-23 2026-11-29  2026-11-01

1 row selected.

PM_TIME DATE_AND_TIME
------- -------------------
14:05   2026-11-23 14:05:09

1 row selected.

MICROSECONDS               TWELVE_HOUR
-------------------------- -----------
2026-11-23 14:05:09.123456 14:05:09.5

1 row selected.
```

### D. TO_NUMBER and TO_NCHAR

<!-- example: oracle -->
```sql
SELECT TO_NUMBER('123') AS a, TO_NUMBER('123.45') AS b, TO_NUMBER('-0.5') AS c, TO_NUMBER('1,234.5', '9,999.9') AS grouped,
       TO_NUMBER('$1,234.50', '$9,999.99') AS dollars, TO_NUMBER('  42  ') AS blanks, TO_NUMBER('1E3') AS exponent,
       TO_NUMBER('FF', 'XX') AS hex, TO_NUMBER('12-', '99MI') AS trailing_minus, TO_NUMBER('<5>', '9PR') AS angle,
       TO_NUMBER('') AS empty, TO_NUMBER('1,5', '9D9', 'NLS_NUMERIC_CHARACTERS='',.''') AS comma_decimal_ignored
FROM dual;
SELECT TO_NCHAR(123) AS from_number, TO_NCHAR('héllo') AS from_text, TO_NCHAR(DATE '2026-11-23') AS from_date,
       TO_NCHAR(12.5, '999.99') AS from_number_format
FROM dual;
```

```text
  A      B    C GROUPED DOLLARS BLANKS EXPONENT HEX TRAILING_MINUS ANGLE EMPTY COMMA_DECIMAL_IGNORED
--- ------ ---- ------- ------- ------ -------- --- -------------- ----- ----- ---------------------
123 123.45 -0.5  1234.5  1234.5     42     1000 255            -12    -5                          15

1 row selected.

FROM_NUMBER FROM_TEXT FROM_DATE FROM_NUMBER_FORMAT
----------- --------- --------- ------------------
123         héllo     23-NOV-26   12.50

1 row selected.
```

### E. TO_BOOLEAN

<!-- example: oracle -->
```sql
SELECT TO_BOOLEAN('true') AS a, TO_BOOLEAN('FALSE') AS b, TO_BOOLEAN('yes') AS c, TO_BOOLEAN('no') AS d, TO_BOOLEAN('on') AS e,
       TO_BOOLEAN('1') AS f, TO_BOOLEAN('t') AS g, TO_BOOLEAN('y') AS h, TO_BOOLEAN(0) AS i, TO_BOOLEAN(5) AS j
FROM dual;
SELECT TO_BOOLEAN('maybe') FROM dual;
```

```text
A    B     C    D     E    F    G    H    I     J
---- ----- ---- ----- ---- ---- ---- ---- ----- ----
true false true false true true true true false true

1 row selected.

ERROR:
ORA-61800: invalid boolean literal: maybe
```

### F. CAST

<!-- example: oracle -->
```sql
SELECT CAST('123' AS NUMBER) AS to_number, CAST(123 AS VARCHAR2(10)) AS to_text, TO_CHAR(CAST('2026-11-23' AS DATE), 'YYYY-MM-DD') AS to_date,
       CAST(1.5 AS INTEGER) AS to_integer, CAST(1 AS BINARY_DOUBLE) AS to_double, CAST(1.5 AS NUMBER(5,2)) AS to_number_5_2,
       CAST('abc' AS VARCHAR2(2)) AS cut, CAST(NULL AS NUMBER) AS null_number
FROM dual;
SELECT CAST(1.5 AS NUMBER(5,0)) AS up, CAST(2.5 AS NUMBER(5,0)) AS half_up, CAST(-1.5 AS INTEGER) AS negative, CAST(1.4 AS INT) AS down,
       CAST('1e3' AS NUMBER) AS exponent, CAST(' 12 ' AS NUMBER) AS blanks
FROM dual;
SELECT TO_CHAR(CAST(DATE '2026-11-23' AS TIMESTAMP), 'YYYY-MM-DD HH24:MI:SS') AS date_to_timestamp,
       TO_CHAR(CAST(TIMESTAMP '2026-11-23 14:05:09.9' AS DATE), 'HH24:MI:SS') AS timestamp_to_date,
       CAST('x' AS CLOB) AS to_clob, CAST(HEXTORAW('41') AS RAW(1)) AS to_raw, CAST(1 AS BOOLEAN) AS number_to_boolean,
       CAST('true' AS BOOLEAN) AS text_to_boolean, CAST(TRUE AS VARCHAR2(5)) AS boolean_to_text
FROM dual;
```

```text
TO_NUMBER TO_TEXT TO_DATE    TO_INTEGER TO_DOUBLE TO_NUMBER_5_2 CUT NULL_NUMBER
--------- ------- ---------- ---------- --------- ------------- --- -----------
      123 123     2026-11-23          2       1.0           1.5 ab

1 row selected.

UP HALF_UP NEGATIVE DOWN EXPONENT BLANKS
-- ------- -------- ---- -------- ------
 2       3       -2    1     1000     12

1 row selected.

DATE_TO_TIMESTAMP   TIMESTAMP_TO_DATE TO_CLOB TO_RAW NUMBER_TO_BOOLEAN TEXT_TO_BOOLEAN BOOLEAN_TO_TEXT
------------------- ----------------- ------- ------ ----------------- --------------- ---------------
2026-11-23 00:00:00 14:05:10          x       41     true              true            TRUE

1 row selected.
```

### G. Implicit conversions

<!-- example: oracle -->
```sql
SELECT 1 + '2' AS num_plus_text, '3' * '4' AS text_times_text, 10 || 5 AS number_concat, '5' + 1 AS text_plus_num FROM dual;
SELECT TO_CHAR(DATE '2026-11-23' + '1', 'YYYY-MM-DD') AS date_plus_text FROM dual;
CREATE TABLE cv (d DATE, n NUMBER, s VARCHAR2(10));
INSERT INTO cv VALUES ('2026-11-23', '42', 7);
SELECT TO_CHAR(d, 'YYYY-MM-DD') AS d, n, s FROM cv;
```

```text
NUM_PLUS_TEXT TEXT_TIMES_TEXT NUMBER_CONCAT TEXT_PLUS_NUM
------------- --------------- ------------- -------------
            3              12 105                       6

1 row selected.

DATE_PLUS_TEXT
--------------
2026-11-24

1 row selected.

Table created.

1 row created.

D           N S
---------- -- -
2026-11-23 42 7

1 row selected.
```

### H. Conversion errors

<!-- example: oracle -->
```sql
SELECT 'a' + 1 FROM dual;
SELECT TO_NUMBER('12abc') FROM dual;
SELECT CAST('x' AS NUMBER) FROM dual;
SELECT CAST(123456 AS NUMBER(3)) FROM dual;
SELECT * FROM dual WHERE dummy = 1;
SELECT TO_DATE('2026-11-23') FROM dual;
SELECT TO_DATE('26-11-23') FROM dual;
SELECT TO_DATE('2026-13-45', 'YYYY-MM-DD') FROM dual;
SELECT TO_DATE('2026-02-30', 'YYYY-MM-DD') FROM dual;
SELECT TO_DATE('2026-11-23 extra', 'YYYY-MM-DD') FROM dual;
SELECT TO_DATE('2026-11-23', 'YYYY-MM-DD HH24:MI') FROM dual;
SELECT TO_DATE('2026-11-23 25:00', 'YYYY-MM-DD HH24:MI') FROM dual;
SELECT TO_DATE('garbage', 'YYYY-MM-DD') FROM dual;
SELECT TO_TIMESTAMP('garbage', 'YYYY') FROM dual;
```

```text
ERROR:
ORA-01722: invalid number

ERROR:
ORA-01722: invalid number

ERROR:
ORA-01722: invalid number

ERROR:
ORA-01438: value larger than specified precision allowed for this column

ERROR:
ORA-01722: invalid number

ERROR:
ORA-01861: literal does not match format string

ERROR:
ORA-01843: An invalid month was specified.

ERROR:
ORA-01843: An invalid month was specified.

ERROR:
ORA-01839: date not valid for month specified

ERROR:
ORA-01830: Date format picture ends before converting entire input string.

ERROR:
ORA-01840: input value not long enough for date format

ERROR:
ORA-01850: hour must be between 0 and 23

ERROR:
ORA-01841: (full) year must be between -4713 and +9999, and not be 0

ERROR:
ORA-01841: (full) year must be between -4713 and +9999, and not be 0
```

### I. Strings into DATE columns

<!-- example: oracle -->
```sql
CREATE TABLE cv2 (d DATE);
INSERT INTO cv2 VALUES ('23-NOV-26');
INSERT INTO cv2 VALUES ('garbage');
INSERT INTO cv2 VALUES ('2026-13-45');
CREATE TABLE cv3 (n NUMBER);
INSERT INTO cv3 VALUES ('abc');
```

```text
Table created.

ERROR:
ORA-01861: literal does not match format string

ERROR:
ORA-01858: A non-numeric character was found instead of a numeric character.

ERROR:
ORA-01881: invalid time zone displacement value

Table created.

ERROR:
ORA-01722: invalid number
```

### J. Format elements and functions that are not available

<!-- example: oracle -->
```sql
SELECT TO_CHAR(1234.5678, '9.9999EEEE') FROM dual;
SELECT TO_CHAR(1994, 'RN') FROM dual;
SELECT TO_CHAR(255, 'XXXX') FROM dual;
SELECT TO_CHAR(DATE '2026-11-23', 'RM') FROM dual;
SELECT TO_DSINTERVAL('3 04:05:06') FROM dual;
SELECT TO_YMINTERVAL('2-5') FROM dual;
SELECT TO_NUMBER('x' DEFAULT -1 ON CONVERSION ERROR) FROM dual;
SELECT VALIDATE_CONVERSION('12' AS NUMBER) FROM dual;
SELECT CAST('3 04:05:06' AS INTERVAL DAY TO SECOND) FROM dual;
```

```text
ERROR:
ORA-01481: invalid number format model

ERROR:
ORA-01481: invalid number format model

ERROR:
ORA-01481: invalid number format model

ERROR:
ORA-01821: date format not recognized

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement
```

### K. Where lexdb differs

<!-- example: oracle -->
```sql
SELECT '[' || TO_CHAR(0, '999') || ']' AS nines, '[' || TO_CHAR(0, 'FM999') || ']' AS fm_nines, TO_CHAR(0, '0') AS zero_format FROM dual;
SELECT TO_CHAR(DATE '2026-11-23', 'Day Month', 'NLS_DATE_LANGUAGE=GERMAN') AS ignores_language FROM dual;
SELECT TO_CHAR(DATE '2026-11-03', 'DDSP') AS spelled FROM dual;
SELECT TO_CHAR(INTERVAL '3 04:05:06' DAY TO SECOND) IS NULL AS interval_text_is_null FROM dual;
SELECT TO_BOOLEAN(NULL) AS null_boolean FROM dual;
SELECT .5 FROM dual;
```

```text
NINES  FM_NINES ZERO_FORMAT
------ -------- -----------
[    ] []        0

1 row selected.

IGNORES_LANGUAGE
-------------------
Monday    November

1 row selected.

SPELLED
-------
03

1 row selected.

INTERVAL_TEXT_IS_NULL
---------------------
true

1 row selected.

NULL_BOOLEAN
------------
false

1 row selected.

ERROR:
ORA-01426: numeric overflow
```

### L. Time zones: TZH, TZM, TZR and TO_TIMESTAMP_TZ

<!-- example: oracle -->
```sql
SELECT TO_CHAR(TIMESTAMP '2026-11-23 14:05:09.5 -03:30', 'HH24:MI:SS.FF3 TZH TZM TZR') AS elements,
       TO_CHAR(TIMESTAMP '2026-11-23 14:05:09 -03:30') AS nls_default
FROM dual;
SELECT TO_CHAR(TO_TIMESTAMP_TZ('2026-11-23 14:05:09 +05:30', 'YYYY-MM-DD HH24:MI:SS TZH:TZM'), 'YYYY-MM-DD HH24:MI:SS TZH:TZM') AS with_offset,
       TO_CHAR(TO_TIMESTAMP_TZ('2026-11-23 14:05:09', 'YYYY-MM-DD HH24:MI:SS'), 'YYYY-MM-DD HH24:MI:SS TZH:TZM') AS session_zone,
       TO_CHAR(TO_TIMESTAMP_TZ('23-NOV-26 02.05.09.000000 PM -03:30'), 'HH24:MI TZH:TZM') AS nls_format
FROM dual;
SELECT TO_TIMESTAMP_TZ('2026-11-23 14:05:09 +02:60', 'YYYY-MM-DD HH24:MI:SS TZH:TZM') FROM dual;
SELECT TO_CHAR(TIMESTAMP '2026-11-23 14:05:09', 'TZH:TZM') FROM dual;
SELECT TO_CHAR(DATE '2026-11-23', 'TZR') FROM dual;
```

```text
ELEMENTS                   NLS_DEFAULT
-------------------------- -----------------------------------
14:05:09.500 -03 30 -03:30 23-NOV-26 02.05.09.000000 PM -03:30

1 row selected.

WITH_OFFSET                SESSION_ZONE               NLS_FORMAT
-------------------------- -------------------------- ------------
2026-11-23 14:05:09 +05:30 2026-11-23 14:05:09 +00:00 14:05 -03:30

1 row selected.

ERROR:
ORA-01875: time zone minute must be between -59 and 59

ERROR:
ORA-01821: date format not recognized

ERROR:
ORA-01821: date format not recognized
```

## See also

[Date and time functions](functions-datetime.md), [Numeric functions](functions-numeric.md),
[Character functions](functions-character.md), [Date and time data types](data-types-datetime.md),
[Number data types](data-types-number.md), [Operators](operators.md)
