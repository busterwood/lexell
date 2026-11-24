# Date and time functions (Transact-SQL)

Functions that read the clock, add to and subtract dates, take them apart and put them together.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
GETDATE ( )                      -> datetime
GETUTCDATE ( )                   -> datetime
CURRENT_TIMESTAMP                -> datetime
SYSDATETIME ( )                  -> datetime2
SYSUTCDATETIME ( )               -> datetime2
SYSDATETIMEOFFSET ( )            -> datetimeoffset
DATEADD ( datepart, number, date )
DATEDIFF ( datepart, startdate, enddate )
DATEDIFF_BIG ( datepart, startdate, enddate )
DATEPART ( datepart, date )
DATENAME ( datepart, date )
YEAR ( date )    MONTH ( date )    DAY ( date )
EOMONTH ( start_date [, month_to_add ] )
DATEFROMPARTS ( year, month, day )
DATETRUNC ( datepart, date )
DATE_BUCKET ( datepart, number, date [, origin ] )
SWITCHOFFSET ( datetimeoffset, offset )    -> datetimeoffset
TODATETIMEOFFSET ( datetime2, offset )     -> datetimeoffset
expression AT TIME ZONE timezone
```

## Arguments

*datepart*
: One of `year` (`yy`, `yyyy`), `quarter` (`qq`, `q`), `month` (`mm`, `m`), `dayofyear` (`dy`, `y`), `day` (`dd`,
  `d`), `week` (`wk`, `ww`), `weekday` (`dw`), `hour` (`hh`), `minute` (`mi`, `n`), `second` (`ss`, `s`),
  `millisecond` (`ms`), `microsecond` (`mcs`), `nanosecond` (`ns`) and `tzoffset` (`tz`). Which parts a function takes
  is listed under each function. An unknown name is error 155. A part the type cannot hold (`hour` of a `date`) is
  error 9810.

*offset*
: A time zone offset as a string `'+hh:mm'` or `'-hh:mm'`, or as a number of minutes (`-300`), within 14 hours.
  Another is error 9812.

## Functions

`GETDATE`, `CURRENT_TIMESTAMP`, `SYSDATETIME`, `GETUTCDATE`, `SYSUTCDATETIME`, `SYSDATETIMEOFFSET`
: The date and time now, as the server's clock gives it, in local time or UTC. `GETDATE` gives a `datetime`,
  `SYSDATETIME` a `datetime2`, `SYSDATETIMEOFFSET` a `datetimeoffset` at the server's offset. The server runs in UTC,
  so local time and UTC are the same and the offset is `+00:00`.

`DATEADD(datepart, number, date)`
: *date* with *number* of the part added; a negative number subtracts. A fraction in *number* is cut (`1.9` is 1).
  Adding months stops at the end of a shorter month: `DATEADD(month, 1, '2026-01-31')` is 28 February. A string
  is read as a `datetime`, and the result is a `datetime`; a `date`, `datetime2`, `datetimeoffset` or `time` keeps its
  type, and a `datetimeoffset` its offset (the part is added to its local time).

`DATEDIFF(datepart, startdate, enddate)`, `DATEDIFF_BIG`
: The number of part boundaries crossed between the two dates, as an `int` (`bigint` for `DATEDIFF_BIG`). It counts
  boundaries, not elapsed time: `DATEDIFF(year, '2025-12-31', '2026-01-01')` is 1. A negative result means *enddate*
  is earlier. Two `datetimeoffset` values are counted between their UTC instants.

`DATEPART(datepart, date)`
: One part as an `int`. `weekday` is 1 (Sunday) to 7; `week` counts weeks that start on Sunday, the week of 1 January
  being week 1. `millisecond`, `microsecond` and `nanosecond` give that many units of the fraction. `tzoffset` is the
  offset of a `datetimeoffset` in minutes (`-210` for `-03:30`), and 0 for the other types. The other parts of a
  `datetimeoffset` are of its local time.

`DATENAME(datepart, date)`
: The part as text: the name of the month or of the weekday in English, else the number; `tzoffset` as `-03:30`.

`YEAR`, `MONTH`, `DAY`
: `DATEPART` of `year`, `month` and `day`.

`EOMONTH(start_date [, month_to_add])`
: The last day of the month of *start_date*, moved by *month_to_add* months.

`DATEFROMPARTS(year, month, day)`
: A `date` made of the three numbers; one that is not a day is error 517.

`DATETRUNC(datepart, date)`
: *date* cut to the start of the part (SQL Server 2022): `year`, `quarter`, `month`, `week` (Sunday), `day`,
  `hour`, `minute` and `second`. The result is a `datetime2` for a string.

`DATE_BUCKET(datepart, number, date [, origin])`
: The start of the bucket of *number* parts that holds *date* (SQL Server 2022). The buckets count from *origin*,
  by default 1900-01-01.

`SWITCHOFFSET(datetimeoffset, offset)`
: The same instant at another offset: `SWITCHOFFSET('2026-03-15 10:00 +02:00', '+05:30')` is 13:30 at `+05:30`.

`TODATETIMEOFFSET(datetime2, offset)`
: The local time, unchanged, with the offset attached: `TODATETIMEOFFSET('2026-03-15 10:00', '+05:00')` is 10:00 at
  `+05:00`. A `datetimeoffset` loses its own offset first.

`expression AT TIME ZONE timezone`
: A `datetimeoffset` in the named Windows time zone (`'UTC'`, `'Pacific Standard Time'`, `'W. Europe Standard
  Time'`, `'India Standard Time'` and the others of `sys.time_zone_info`), with the zone's summer time: a
  `datetimeoffset` is moved to the zone's offset at that instant; a `datetime2` or `datetime` is read as the zone's local
  time (a time that happens twice is the first; one that never happens is moved forward an hour). An unknown zone is
  error 9820.

## Remarks

- All functions return NULL for a NULL argument.
- The clock functions give a different value each time, so the examples compare them with a fixed date.
- `DATEPART(weekday, ...)` does not depend on `SET DATEFIRST`: the first day is always Sunday (`@@DATEFIRST` is 7).

## Differences from SQL Server

- **Missing parts:** `iso_week` and `isowk` are error 155. `nanosecond` is taken, but the time has only microseconds,
  so it ends in three zeros (`123456000`).
- **Missing functions:** `ISDATE`, `DATETIMEFROMPARTS`, `TIMEFROMPARTS` and `DATETIME2FROMPARTS` are error 195.
- `AT TIME ZONE` knows about 45 Windows zones, the common ones of each continent; another
  (`'Mountain Standard Time (Mexico)'`) is error 9820, where SQL Server knows every zone of `sys.time_zone_info`.
- `SWITCHOFFSET`, `TODATETIMEOFFSET` and `AT TIME ZONE` give a `datetimeoffset(7)` whatever the scale of their
  argument; SQL Server keeps the scale, so a client shows `10:00:00 +02:00` where lexdb's shows `10:00:00.0000000
  +02:00`.
- `DATEFROMPARTS` with an impossible date is error 517 (SQL Server: 289).
- `datetime + number` and `datetime - datetime` work as in SQL Server, but `date`, `datetime2` and `time` with a
  number are error 206: use `DATEADD` and `DATEDIFF` (see [date and time types](data-types-datetime.md)).
- A `datetime` result prints with one fractional digit (`.0`); see the types page.

## Examples

### A. The clock

<!-- example: tsql -->
```sql
SELECT CASE WHEN GETDATE() > CAST('2020-01-01' AS datetime) THEN 'after 2020' END AS getdate,
       CASE WHEN SYSDATETIME() > CAST('2020-01-01' AS datetime2) THEN 'after 2020' END AS sysdatetime,
       CASE WHEN GETUTCDATE() > CAST('2020-01-01' AS datetime) THEN 'after 2020' END AS getutcdate,
       CASE WHEN SYSUTCDATETIME() > CAST('2020-01-01' AS datetime2) THEN 'after 2020' END AS sysutcdatetime,
       CASE WHEN CURRENT_TIMESTAMP > CAST('2020-01-01' AS datetime) THEN 'after 2020' END AS current_timestamp_,
       CASE WHEN SYSDATETIMEOFFSET() > CAST('2020-01-01' AS datetimeoffset) THEN 'after 2020' END AS sysdatetimeoffset;
```

```text
getdate    sysdatetime getutcdate sysutcdatetime current_timestamp_ sysdatetimeoffset
---------- ----------- ---------- -------------- ------------------ -----------------
after 2020 after 2020  after 2020 after 2020     after 2020         after 2020

(1 row affected)
```

### B. DATEADD

<!-- example: tsql -->
```sql
SELECT DATEADD(year, 1, '2026-02-28') AS year_, DATEADD(quarter, 1, '2026-01-31') AS quarter_,
       DATEADD(month, 1, '2026-01-31') AS month_, DATEADD(week, 1, '2026-03-15') AS week_,
       DATEADD(day, -15, '2026-03-15') AS day_, DATEADD(dayofyear, 1, '2026-03-15') AS dayofyear_,
       DATEADD(hour, 5, '2026-03-15 10:00') AS hour_, DATEADD(minute, 90, '2026-03-15 10:00') AS minute_,
       DATEADD(second, 30, '2026-03-15 10:00') AS second_, DATEADD(millisecond, 500, '2026-03-15 10:00') AS ms_;
GO
SELECT DATEADD(day, 1, CAST('2026-03-15' AS date)) AS date_stays_a_date,
       DATEADD(day, 1, CAST('2026-03-15 10:00' AS datetime)) AS datetime_stays,
       DATEADD(day, 1.9, '2026-03-15') AS fraction_is_cut, DATEADD(day, 1, NULL) AS null_in;
GO
SELECT DATEADD(hour, 1, CAST('2026-03-15' AS date)) AS hour_to_a_date;
```

```text
year_                 quarter_              month_                week_                 day_                  dayofyear_            hour_                 minute_               second_               ms_
--------------------- --------------------- --------------------- --------------------- --------------------- --------------------- --------------------- --------------------- --------------------- ---------------------
2027-02-28 00:00:00.0 2026-04-30 00:00:00.0 2026-02-28 00:00:00.0 2026-03-22 00:00:00.0 2026-02-28 00:00:00.0 2026-03-16 00:00:00.0 2026-03-15 15:00:00.0 2026-03-15 11:30:00.0 2026-03-15 10:00:30.0 2026-03-15 10:00:00.5

(1 row affected)

date_stays_a_date datetime_stays        fraction_is_cut       null_in
----------------- --------------------- --------------------- -------
2026-03-16        2026-03-16 10:00:00.0 2026-03-16 00:00:00.0 NULL

(1 row affected)

Msg 9810, Level 16, State 1, Line 1
The datepart hour is not supported by date function dateadd for data type date.
```

### C. DATEDIFF counts boundaries

<!-- example: tsql -->
```sql
SELECT DATEDIFF(year, '2025-12-31', '2026-01-01') AS years, DATEDIFF(month, '2026-01-31', '2026-02-01') AS months,
       DATEDIFF(day, '2026-03-15', '2026-03-10') AS days_backwards,
       DATEDIFF(hour, '2026-03-15 10:30', '2026-03-15 11:29') AS hours,
       DATEDIFF(minute, '2026-03-15 10:00:59', '2026-03-15 10:01:00') AS minutes,
       DATEDIFF(week, '2026-03-14', '2026-03-15') AS weeks, DATEDIFF(quarter, '2026-03-31', '2026-04-01') AS quarters,
       DATEDIFF_BIG(second, '2020-01-01', '2026-01-01') AS seconds_big;
SELECT DATEDIFF(millisecond, '2026-03-15 10:00:00', '2026-03-15 10:00:01.5') AS ms,
       DATEDIFF(day, '2026-03-15 23:59', '2026-03-16 00:01') AS midnight_crossed,
       DATEDIFF(dayofyear, '2026-01-01', '2026-03-15') AS dayofyears, DATEDIFF(weekday, '2026-03-13', '2026-03-16') AS weekdays;
```

```text
years months days_backwards hours minutes weeks quarters seconds_big
----- ------ -------------- ----- ------- ----- -------- -----------
1     1      -5             1     1       1     1        189388800

(1 row affected)

ms   midnight_crossed dayofyears weekdays
---- ---------------- ---------- --------
1500 1                73         3

(1 row affected)
```

### D. DATEPART and DATENAME

<!-- example: tsql -->
```sql
SELECT DATEPART(year, '2026-03-15 13:45:30.123') AS y, DATEPART(quarter, '2026-03-15') AS q,
       DATEPART(month, '2026-03-15') AS m, DATEPART(dayofyear, '2026-03-15') AS doy, DATEPART(day, '2026-03-15') AS d,
       DATEPART(week, '2026-03-15') AS wk, DATEPART(weekday, '2026-03-15') AS wd,
       DATEPART(hour, '2026-03-15 13:45:30') AS h, DATEPART(minute, '2026-03-15 13:45:30') AS mi,
       DATEPART(second, '2026-03-15 13:45:30') AS s, DATEPART(millisecond, '2026-03-15 13:45:30.123') AS ms;
SELECT DATEPART(microsecond, '2026-03-15 13:45:30.123456') AS us,
       DATEPART(nanosecond, CAST('2026-03-15 13:45:30.123456' AS datetime2)) AS ns,
       DATEPART(yy, '2026-03-15') AS yy, DATEPART(dw, '2026-03-15') AS dw, DATEPART(hh, '2026-03-15 13:00') AS hh;
SELECT DATENAME(month, '2026-03-15') AS month_name, DATENAME(weekday, '2026-03-15') AS weekday_name,
       DATENAME(year, '2026-03-15') AS y, DATENAME(dayofyear, '2026-03-15') AS doy, DATENAME(quarter, '2026-03-15') AS q;
```

```text
y    q m doy d  wk wd h  mi s  ms
---- - - --- -- -- -- -- -- -- ---
2026 1 3 74  15 12 1  13 45 30 123

(1 row affected)

us     ns        yy   dw hh
------ --------- ---- -- --
123456 123456000 2026 1  13

(1 row affected)

month_name weekday_name y    doy q
---------- ------------ ---- --- -
March      Sunday       2026 74  1

(1 row affected)
```

### E. YEAR, MONTH, DAY and EOMONTH

<!-- example: tsql -->
```sql
SELECT YEAR('2026-03-15') AS y, MONTH('2026-03-15') AS m, DAY('2026-03-15') AS d, DAY(NULL) AS null_in;
SELECT EOMONTH('2026-02-10') AS feb, EOMONTH('2026-02-10', 1) AS next_month, EOMONTH('2024-02-10') AS leap_year,
       EOMONTH('2026-03-15', -1) AS previous_month;
```

```text
y    m d  null_in
---- - -- -------
2026 3 15 NULL

(1 row affected)

feb        next_month leap_year  previous_month
---------- ---------- ---------- --------------
2026-02-28 2026-03-31 2024-02-29 2026-02-28

(1 row affected)
```

### F. DATEFROMPARTS

<!-- example: tsql -->
```sql
SELECT DATEFROMPARTS(2026, 3, 15) AS d;
GO
SELECT DATEFROMPARTS(2026, 2, 30) AS not_a_day;
```

```text
d
----------
2026-03-15

(1 row affected)

Msg 517, Level 16, State 1, Line 1
date field value out of range: 2026-02-30
```

### G. DATETRUNC and DATE_BUCKET

<!-- example: tsql -->
```sql
SELECT DATETRUNC(year, '2026-03-15 13:45:30') AS y, DATETRUNC(quarter, '2026-05-15') AS q,
       DATETRUNC(month, '2026-03-15 13:45:30') AS m, DATETRUNC(week, '2026-03-15') AS wk,
       DATETRUNC(day, '2026-03-15 13:45:30') AS d, DATETRUNC(hour, '2026-03-15 13:45:30') AS h,
       DATETRUNC(minute, '2026-03-15 13:45:30') AS mi, DATETRUNC(second, '2026-03-15 13:45:30.5') AS s;
SELECT DATE_BUCKET(day, 7, CAST('2026-03-15' AS date), CAST('2026-01-01' AS date)) AS week_from_origin,
       DATE_BUCKET(month, 2, CAST('2026-03-15' AS date), CAST('2026-01-01' AS date)) AS two_months,
       DATE_BUCKET(hour, 6, CAST('2026-03-15 13:45' AS datetime2), CAST('2026-01-01' AS datetime2)) AS six_hours,
       DATE_BUCKET(day, 7, CAST('2026-03-15' AS date)) AS default_origin;
```

```text
y                           q                           m                           wk                          d                           h                           mi                          s
--------------------------- --------------------------- --------------------------- --------------------------- --------------------------- --------------------------- --------------------------- ---------------------------
2026-01-01 00:00:00.0000000 2026-04-01 00:00:00.0000000 2026-03-01 00:00:00.0000000 2026-03-15 00:00:00.0000000 2026-03-15 00:00:00.0000000 2026-03-15 13:00:00.0000000 2026-03-15 13:45:00.0000000 2026-03-15 13:45:30.0000000

(1 row affected)

week_from_origin two_months six_hours                   default_origin
---------------- ---------- --------------------------- --------------
2026-03-12       2026-03-01 2026-03-15 12:00:00.0000000 2026-03-09

(1 row affected)
```

### H. Grouping by a date part

<!-- example: tsql -->
```sql
CREATE TABLE sale (id int IDENTITY(1,1), sold date, amount decimal(10,2));
INSERT INTO sale (sold, amount) VALUES ('2026-01-05', 10), ('2026-01-20', 5.5), ('2026-02-03', 7.25), ('2026-02-28', 3);
SELECT DATETRUNC(month, sold) AS month_start, COUNT(*) AS sales, SUM(amount) AS total
FROM sale GROUP BY DATETRUNC(month, sold) ORDER BY month_start;
SELECT YEAR(sold) AS y, MONTH(sold) AS m, EOMONTH(sold) AS month_end, SUM(amount) AS total
FROM sale GROUP BY YEAR(sold), MONTH(sold), EOMONTH(sold) ORDER BY y, m;
```

```text
(4 rows affected)

month_start sales total
----------- ----- -----
2026-01-01  2     15.50
2026-02-01  2     10.25

(2 rows affected)

y    m month_end  total
---- - ---------- -----
2026 1 2026-01-31 15.50
2026 2 2026-02-28 10.25

(2 rows affected)
```

### I. AT TIME ZONE

<!-- example: tsql -->
```sql
SELECT CAST('2026-03-15 10:00:00 +02:00' AS datetimeoffset(0)) AT TIME ZONE 'UTC' AS utc,
       CAST('2026-03-15 10:00:00 +02:00' AS datetimeoffset(0)) AT TIME ZONE 'Pacific Standard Time' AS pacific,
       CAST('2026-03-15 10:00:00 +02:00' AS datetimeoffset(0)) AT TIME ZONE 'India Standard Time' AS india;
SELECT CAST('2026-03-15 10:00:00' AS datetime2(0)) AT TIME ZONE 'W. Europe Standard Time' AS winter,
       CAST('2026-07-15 10:00:00' AS datetime2(0)) AT TIME ZONE 'W. Europe Standard Time' AS summer,
       CAST('2026-03-08 02:30:00' AS datetime2(0)) AT TIME ZONE 'Eastern Standard Time' AS in_the_gap,
       CAST('2026-11-01 01:30:00' AS datetime2(0)) AT TIME ZONE 'Eastern Standard Time' AS twice;
GO
SELECT CAST('2026-03-15 10:00:00 +02:00' AS datetimeoffset) AT TIME ZONE 'Nowhere Time';
```

```text
utc                                pacific                            india
---------------------------------- ---------------------------------- ----------------------------------
2026-03-15 08:00:00.0000000 +00:00 2026-03-15 01:00:00.0000000 -07:00 2026-03-15 13:30:00.0000000 +05:30

(1 row affected)

winter                             summer                             in_the_gap                         twice
---------------------------------- ---------------------------------- ---------------------------------- ----------------------------------
2026-03-15 10:00:00.0000000 +01:00 2026-07-15 10:00:00.0000000 +02:00 2026-03-08 03:30:00.0000000 -04:00 2026-11-01 01:30:00.0000000 -04:00

(1 row affected)

Msg 9820, Level 16, State 1, Line 1
The time zone parameter 'Nowhere Time' provided to AT TIME ZONE clause is invalid.
```

### J. Parts and functions that are missing

<!-- example: tsql -->
```sql
SELECT DATEPART(iso_week, '2026-01-01');
GO
SELECT DATENAME(foo, '2026-03-15');
GO
SELECT ISDATE('2026-03-15');
GO
SELECT DATETIMEFROMPARTS(2026, 3, 15, 10, 30, 0, 0);
```

```text
Msg 155, Level 16, State 1, Line 1
'"iso_week"' is not a recognized datepart option.
Msg 155, Level 16, State 1, Line 1
'"foo"' is not a recognized datename option.
Msg 195, Level 15, State 1, Line 1
'isdate' is not a recognized built-in function name.
Msg 195, Level 15, State 1, Line 1
'datetimefromparts' is not a recognized built-in function name.
```

### K. Offsets: SWITCHOFFSET, TODATETIMEOFFSET, DATEPART and DATENAME

<!-- example: tsql -->
```sql
SELECT SWITCHOFFSET(CAST('2026-03-15 10:00:00 +02:00' AS datetimeoffset(0)), '+05:30') AS to_offset,
       SWITCHOFFSET(CAST('2026-03-15 10:00:00 +02:00' AS datetimeoffset(0)), -300) AS to_minutes,
       TODATETIMEOFFSET(CAST('2026-03-15 10:00:00' AS datetime2(0)), '+05:00') AS attach,
       TODATETIMEOFFSET(CAST('2026-03-15 10:00:00' AS datetime2(0)), -90) AS attach_minutes;
SELECT DATEPART(tzoffset, CAST('2026-03-15 10:00:00 -03:30' AS datetimeoffset)) AS tzoffset,
       DATEPART(tz, CAST('2026-03-15 10:00:00 -03:30' AS datetimeoffset)) AS tz,
       DATENAME(tzoffset, CAST('2026-03-15 10:00:00 -03:30' AS datetimeoffset)) AS name,
       DATEPART(tzoffset, CAST('2026-03-15 10:00:00' AS datetime2)) AS of_datetime2,
       DATEDIFF(hour, CAST('2026-03-15 10:00:00 +02:00' AS datetimeoffset), CAST('2026-03-15 10:00:00 +00:00' AS datetimeoffset)) AS hours_between;
SELECT CASE WHEN SYSDATETIMEOFFSET() > CAST('2020-01-01 00:00 +00:00' AS datetimeoffset) THEN 'after 2020' END AS now_,
       DATEPART(tzoffset, SYSDATETIMEOFFSET()) AS now_offset;
GO
SELECT SWITCHOFFSET(CAST('2026-03-15 10:00:00 +02:00' AS datetimeoffset), '+15:00');
GO
SELECT TODATETIMEOFFSET(CAST('2026-03-15 10:00:00' AS datetime2), 'zz');
```

```text
to_offset                          to_minutes                         attach                             attach_minutes
---------------------------------- ---------------------------------- ---------------------------------- ----------------------------------
2026-03-15 13:30:00.0000000 +05:30 2026-03-15 03:00:00.0000000 -05:00 2026-03-15 10:00:00.0000000 +05:00 2026-03-15 10:00:00.0000000 -01:30

(1 row affected)

tzoffset tz   name   of_datetime2 hours_between
-------- ---- ------ ------------ -------------
-210     -210 -03:30 0            2

(1 row affected)

now_       now_offset
---------- ----------
after 2020 0

(1 row affected)

Msg 9812, Level 16, State 1, Line 1
The timezone provided to builtin function switchoffset is invalid.
Msg 9812, Level 16, State 1, Line 1
The timezone provided to builtin function todatetimeoffset is invalid.
```

## See also

[Date and time types](data-types-datetime.md), [CAST and CONVERT](functions-conversion.md),
[FORMAT](functions-format.md), [Operators](operators.md)
