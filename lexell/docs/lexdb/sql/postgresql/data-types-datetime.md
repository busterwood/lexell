# Date and time types

Dates, times of day, timestamps with and without a time zone, and intervals.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
date
time [ ( p ) ] [ without time zone ]
timestamp [ ( p ) ] [ without time zone ]
timestamp [ ( p ) ] with time zone | timestamptz [ ( p ) ]
interval [ fields ] [ ( p ) ]

fields ::=
    YEAR | MONTH | DAY | HOUR | MINUTE | SECOND
  | YEAR TO MONTH | DAY TO HOUR | DAY TO MINUTE | DAY TO SECOND
  | HOUR TO MINUTE | HOUR TO SECOND | MINUTE TO SECOND
```

## Arguments

*p*
: The digits kept after the seconds' point, 0 to 6 (the default). A value is rounded to *p* digits.

`date`
: A calendar date, from 4713 BC to 5874897 AD, and `infinity`, `-infinity`.

`time`
: A time of day, 00:00:00 to 24:00:00, to the microsecond.

`timestamp`
: A date and time without a time zone.

`timestamptz`
: An instant. It is stored in UTC, read in the session's time zone when its text has none, and shown in the
  session's time zone (`SET TIME ZONE`; UTC by default).

`interval`
: A span of months, days and microseconds, kept apart: `1 month` is not `30 days` until it is compared. *fields*
  (SQL's interval qualifiers) name the units a value may hold and drop what is below the lowest one; *p* goes with
  `SECOND` (`interval second(3)`, `interval day to second(3)`).

## Remarks

- Constants: `DATE '2026-03-01'`, `TIME '10:30'`, `TIMESTAMP '2026-03-01 10:30'`, `TIMESTAMPTZ '2026-03-01
  10:30+02'`, `INTERVAL '1 day 2 hours'`, or a string cast with `::`. Dates are read in ISO order (year, month,
  day); `T` may part date and time. `today`, `tomorrow`, `yesterday`, `now`, `epoch`, `infinity` and `-infinity`
  are read too.
- A time zone in a `timestamptz` constant may be an offset (`+05:30`), a zone name (`Europe/Paris`) or an
  abbreviation (`PST`).
- Intervals are read in PostgreSQL's words (`1 year 2 mons 3 days 04:05:06`, `2 weeks`, `90 minutes`, `1 century`),
  `@ ... ago`, and ISO 8601 (`P1Y2M3DT4H`).
- The standard's qualifiers follow the string (`INTERVAL '1' DAY`, `INTERVAL '1-2' YEAR TO MONTH`) or the type of a
  column or cast. The text is read in the fields' terms: a bare number is in the lowest field's unit (`'1'` of `DAY`
  is a day; of `MINUTE` a minute), `'1-2'` is years and months, `'03:04'` of `MINUTE TO SECOND` is minutes and
  seconds. A value loses what is below its lowest field (`INTERVAL '1 day 2 hours' DAY` is `1 day`). A text the
  fields cannot hold is 22015 (`'1-14' YEAR TO MONTH`) or 22007.
- Arithmetic: `date + integer` and `date - integer` move by days; `date - date` is an integer of days; `date +
  interval` and `timestamp ± interval` are timestamps; `timestamp - timestamp` is an interval; `time ± interval`
  wraps round midnight; an interval multiplies and divides by a number.
- Adding months keeps the day where it can and else takes the month's last day: `2026-01-31 + 1 month` is
  `2026-02-28`.
- `AT TIME ZONE` turns a `timestamp` into a `timestamptz` and back. See [date and time
  functions](functions-datetime.md).
- `SHOW DateStyle` is `ISO, MDY` and `SHOW IntervalStyle` is `postgres`; output is always in those styles.

## Differences from PostgreSQL

- `time with time zone` (`timetz`) is refused (0A000, `lexdb: time with time zone is not supported (use
  timestamptz)`).
- Dates are read in ISO order only: `'01/03/2026'`, `'20260301'` and `'March 1, 2026'` are 22007 (PostgreSQL reads
  them by `DateStyle`). `SET DateStyle` and `SET IntervalStyle` are accepted and change nothing.
- `'infinity'::interval` and `'allballs'::time` are not read. `INTERVAL(3) '1' SECOND` (the precision before the
  string) is accepted and gives one second (PostgreSQL: a syntax error).
- A cast's result column is named after the source type in some cases (`TIMESTAMP '...'::timestamptz` is named
  `timestamp`).

## Examples

### A. Constants

<!-- example: postgresql -->
```sql
SELECT DATE '2026-03-01' AS d, TIME '10:30:15.5' AS t, TIMESTAMP '2026-03-01T10:30' AS ts,
       TIMESTAMPTZ '2026-03-01 10:30+02' AS tstz;
```

```text
     d      |     t      |         ts          |          tstz
------------+------------+---------------------+------------------------
 2026-03-01 | 10:30:15.5 | 2026-03-01 10:30:00 | 2026-03-01 08:30:00+00
(1 row)
```

### B. Precision

<!-- example: postgresql -->
```sql
SELECT '2026-03-01 10:30:15.555555'::timestamp(2) AS ts2, '10:30:59.6'::time(0) AS t0;
```

```text
          ts2           |    t0
------------------------+----------
 2026-03-01 10:30:15.56 | 10:31:00
(1 row)
```

### C. Date arithmetic

<!-- example: postgresql -->
```sql
SELECT DATE '2026-03-01' + 30 AS plus_days, DATE '2026-03-01' - DATE '2026-01-01' AS days_between,
       DATE '2026-03-01' + INTERVAL '1 month' AS plus_month, DATE '2026-03-01' + TIME '10:30' AS at_time;
```

```text
 plus_days  | days_between |     plus_month      |       at_time
------------+--------------+---------------------+---------------------
 2026-03-31 |           59 | 2026-04-01 00:00:00 | 2026-03-01 10:30:00
(1 row)
```

### D. Timestamp arithmetic and month ends

<!-- example: postgresql -->
```sql
SELECT TIMESTAMP '2026-03-01' - TIMESTAMP '2026-01-01 12:00' AS span,
       TIMESTAMP '2026-01-31' + INTERVAL '1 month' AS jan_31_plus_month,
       TIME '23:00' + INTERVAL '2 hours' AS wraps;
```

```text
       span       |  jan_31_plus_month  |  wraps
------------------+---------------------+----------
 58 days 12:00:00 | 2026-02-28 00:00:00 | 01:00:00
(1 row)
```

### E. timestamptz and the session's time zone

The same instant shows differently in another time zone; a timestamp without a zone is read in the session's.

<!-- example: postgresql -->
```sql
CREATE TABLE event (name text, at timestamptz);
INSERT INTO event VALUES ('launch', '2026-03-01 10:30:00+00'), ('call', '2026-03-01 10:30:00 Europe/Paris');
SELECT * FROM event ORDER BY at;
SET TIME ZONE 'Europe/Paris';
SELECT * FROM event ORDER BY at;
SELECT TIMESTAMP '2026-07-01 12:00'::timestamptz AS summer;
RESET TIME ZONE;
```

```text
CREATE TABLE
INSERT 0 2
  name  |           at
--------+------------------------
 call   | 2026-03-01 09:30:00+00
 launch | 2026-03-01 10:30:00+00
(2 rows)

SET
  name  |           at
--------+------------------------
 call   | 2026-03-01 10:30:00+01
 launch | 2026-03-01 11:30:00+01
(2 rows)

         summer
------------------------
 2026-07-01 12:00:00+02
(1 row)

RESET
```

### F. Intervals

<!-- example: postgresql -->
```sql
SELECT INTERVAL '1 year 2 months 3 days 04:05:06.7' AS a, '90 minutes'::interval AS b, INTERVAL '2 weeks' AS c,
       'P1Y2M3DT4H'::interval AS iso, '@ 1 day ago'::interval AS ago;
SELECT INTERVAL '1 day' * 3 AS times3, INTERVAL '1 hour' / 4 AS quarter, INTERVAL '1 month' = INTERVAL '30 days' AS eq;
```

```text
                a                |    b     |    c    |              iso              |   ago
---------------------------------+----------+---------+-------------------------------+---------
 1 year 2 mons 3 days 04:05:06.7 | 01:30:00 | 14 days | 1 year 2 mons 3 days 04:00:00 | -1 days
(1 row)

 times3 | quarter  | eq
--------+----------+----
 3 days | 00:15:00 | t
(1 row)
```

The standard's qualifiers, after the string and in a column's type:

<!-- example: postgresql -->
```sql
SELECT INTERVAL '1' DAY AS d, INTERVAL '1-2' YEAR TO MONTH AS ym, INTERVAL '03:04' MINUTE TO SECOND AS ms,
       INTERVAL '1 day 2 hours' DAY AS cut;
CREATE TABLE shift (len interval hour to minute);
INSERT INTO shift VALUES ('2:30:45'), ('90 minutes');
SELECT len FROM shift;
SELECT INTERVAL '1-14' YEAR TO MONTH;
```

```text
   d   |      ym       |    ms    |  cut
-------+---------------+----------+-------
 1 day | 1 year 2 mons | 00:03:04 | 1 day
(1 row)

CREATE TABLE
INSERT 0 2
   len
----------
 02:30:00
 01:30:00
(2 rows)

ERROR:  interval field value out of range: "1-14"
```

### G. Special values

<!-- example: postgresql -->
```sql
SELECT 'infinity'::date AS inf, 'epoch'::timestamptz AS epoch, '4713-01-01 BC'::date AS first_day,
       'tomorrow'::date - 'yesterday'::date AS two;
```

```text
   inf    |         epoch          |   first_day   | two
----------+------------------------+---------------+-----
 infinity | 1970-01-01 00:00:00+00 | 4713-01-01 BC |   2
(1 row)
```

### H. Errors

<!-- example: postgresql -->
```sql
SELECT '2026-02-30'::date;
SELECT '01/03/2026'::date;
SELECT '10:30'::timetz;
SELECT INTERVAL '1 2' YEAR TO MONTH;
```

```text
ERROR:  date/time field value out of range: "2026-02-30"
ERROR:  invalid input syntax for type date: "01/03/2026"
ERROR:  lexdb: time with time zone is not supported (use timestamptz)
ERROR:  invalid input syntax for type interval: "1 2"
```

## See also

[Date and time functions](functions-datetime.md) · [Formatting functions](functions-formatting.md) ·
[SET](set.md) · [Type conversion](type-conversion.md)
