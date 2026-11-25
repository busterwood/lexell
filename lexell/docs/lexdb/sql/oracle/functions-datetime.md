# Date and time functions

The clock, date arithmetic, `EXTRACT`, truncating and rounding dates, time zones, intervals and time buckets.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
SYSDATE
SYSTIMESTAMP
CURRENT_DATE
CURRENT_TIMESTAMP [ ( precision ) ]
LOCALTIMESTAMP [ ( precision ) ]
SESSIONTIMEZONE
DBTIMEZONE
ADD_MONTHS ( date, integer )
MONTHS_BETWEEN ( date1, date2 )
LAST_DAY ( date )
NEXT_DAY ( date, day_name )
EXTRACT ( field FROM datetime_or_interval )
TRUNC ( date [, format ] )
ROUND ( date [, format ] )
SYS_EXTRACT_UTC ( timestamp_with_time_zone )
FROM_TZ ( timestamp, time_zone )
datetime AT TIME ZONE { 'zone' | DBTIMEZONE | SESSIONTIMEZONE | expr }
datetime AT LOCAL
TZ_OFFSET ( 'zone' | DBTIMEZONE | SESSIONTIMEZONE )
NEW_TIME ( date, zone1, zone2 )
NUMTODSINTERVAL ( n, 'DAY' | 'HOUR' | 'MINUTE' | 'SECOND' )
NUMTOYMINTERVAL ( n, 'YEAR' | 'MONTH' )
TIME_BUCKET ( datetime, width, origin [, START | END ] )
DATEADD ( unit, n, datetime )
DATEDIFF ( unit, start, end )
TIMESTAMPDIFF ( unit, start, end )
```

`DATEADD`, `DATEDIFF`, `TIMESTAMPDIFF` and `TIME_BUCKET` are 26ai functions. Date formats for `TO_CHAR` and `TO_DATE`,
the time zone elements `TZH`, `TZM`, `TZR`, `TZD` and `TO_TIMESTAMP_TZ` are on the [conversion page](functions-conversion.md);
the types are on the [date and time types page](data-types-datetime.md).

A *zone* is an offset (`'+05:30'`, `'-03:00'`) or a region name (`'Europe/Paris'`, `'UTC'`). A region is used as the
offset it has at that instant (see the differences). An unknown region is ORA-01882.

## Functions

`SYSDATE`
: The current date and time of the server as a `DATE` (to the second).

`SYSTIMESTAMP`, `CURRENT_TIMESTAMP`, `LOCALTIMESTAMP`
: The current time. `SYSTIMESTAMP` is a `TIMESTAMP WITH TIME ZONE` at the server's offset, `+00:00`;
  `CURRENT_TIMESTAMP` is one at the session's time zone; `LOCALTIMESTAMP` is a `TIMESTAMP` of the session's local
  time. `CURRENT_DATE` is the session's date and time as a `DATE`. All of them are fixed for the length of a statement.

`SESSIONTIMEZONE`, `DBTIMEZONE`
: The session's time zone (set with `ALTER SESSION SET TIME_ZONE`) as it was set, an offset (`+02:00`) or a region
  name, and the database's, which is `+00:00`.

`ADD_MONTHS`
: *date* moved by *integer* months. When *date* is the last day of its month, so is the result:
  `ADD_MONTHS(DATE '2026-02-28', 1)` is 31 March. Otherwise a day that does not exist in the month is moved to the
  last day. The time of day is kept.

`MONTHS_BETWEEN`
: The months from *date2* to *date1*. When both dates are the same day of the month, or both the last day, the result
  is a whole number; otherwise the fraction counts days as 1/31 of a month.

`LAST_DAY`
: The last day of the month of *date*, with its time of day.

`NEXT_DAY`
: The first date after *date* that falls on *day_name* (`'MONDAY'`, `'MON'`, any case). An unknown name is ORA-01846.

`EXTRACT`
: One field of a date, timestamp or interval: `YEAR`, `MONTH`, `DAY`, `HOUR`, `MINUTE`, `SECOND` (with its fraction),
  and for a timestamp with a time zone `TIMEZONE_HOUR`, `TIMEZONE_MINUTE`, `TIMEZONE_REGION` and `TIMEZONE_ABBR`. The
  date and time fields of a `TIMESTAMP WITH TIME ZONE` are UTC's, as in Oracle: `EXTRACT(HOUR FROM TIMESTAMP
  '2026-11-23 14:30:00 +05:30')` is 9; use `TO_CHAR` for the local time. `TIMEZONE_HOUR` of a timestamp without a zone
  is ORA-30076.

`TRUNC`, `ROUND` of dates
: A date cut or rounded to a unit: `'YYYY'` or `'YEAR'`, `'Q'`, `'MM'` or `'MONTH'`, `'IW'` (Monday of the ISO week),
  `'DAY'` and `'D'` (the first day of the week, a Sunday here), `'DD'`, `'HH'`, `'HH24'`, `'MI'`. Without a format
  `TRUNC` gives midnight and `ROUND` the nearest midnight.

`SYS_EXTRACT_UTC`
: A timestamp with time zone as a timestamp in UTC.

`FROM_TZ`
: The timestamp, unchanged, with the zone attached: `FROM_TZ(TIMESTAMP '2026-11-23 14:30:00', '+05:30')` is 14:30 at
  `+05:30`. An offset beyond 15 hours is ORA-01874, and one without its minutes (`'+03'`) ORA-01861.

`AT TIME ZONE`, `AT LOCAL`
: The same instant at another zone: `TIMESTAMP '2026-11-23 14:05:09 +02:00' AT TIME ZONE '+00:00'` is 12:05:09 at
  `+00:00`. The zone may be `DBTIMEZONE`, `SESSIONTIMEZONE` or an expression. `AT LOCAL` moves the value to the
  session's time zone. A timestamp without a zone is read in the session's zone first.

`TZ_OFFSET`
: The offset of a zone as text, `+05:30`; for a region, its offset now.

`NEW_TIME`
: A `DATE` moved from one of Oracle's zone abbreviations to another: `AST`, `ADT`, `BST`, `BDT`, `CST`, `CDT`, `EST`,
  `EDT`, `GMT`, `HST`, `HDT`, `MST`, `MDT`, `NST`, `PST`, `PDT`, `YST`, `YDT`. Another is ORA-01857.

`NUMTODSINTERVAL`, `NUMTOYMINTERVAL`
: An interval of *n* units: `INTERVAL DAY TO SECOND` or `INTERVAL YEAR TO MONTH`. Add it to a date or timestamp.

`TIME_BUCKET`
: The start of the bucket of width *width* (an interval) that holds *datetime*, with buckets counted from *origin*.
  `START` (the default) gives the start of the bucket and `END` its end. The origin is not optional here.

`DATEADD`
: *datetime* moved by *n* units (`YEAR`, `MONTH`, `WEEK`, `DAY`, `HOUR`, `MINUTE`, `SECOND`).

`DATEDIFF`
: The number of unit boundaries crossed between two values, as an integer: `DATEDIFF(MONTH, DATE '2026-01-31', DATE
  '2026-03-01')` is 2.

`TIMESTAMPDIFF`
: The whole units between two values: 26 hours and a half is 26 `HOUR`.

## Remarks

- Subtracting two dates gives a number of days (with a fraction); subtracting two timestamps gives an `INTERVAL DAY TO
  SECOND`. A number added to a date is days: `DATE '2026-11-23' + 1.5` is noon on the 24th.
- A date or timestamp plus an `INTERVAL YEAR TO MONTH` (or a `NUMTOYMINTERVAL`) whose day is not in the month it
  reaches is ORA-01839: `DATE '2026-01-31' + INTERVAL '1' MONTH` (example H). `ADD_MONTHS` moves such a day to the end
  of the month.
- A `TIMESTAMP WITH TIME ZONE` keeps its offset through arithmetic: `+ INTERVAL` gives one at the same offset (months
  count in UTC: `TIMESTAMP '2026-01-31 23:00:00 -05:00' + INTERVAL '1' MONTH` is 28 February 23:00 at `-05:00`, 1 March
  in UTC), the difference of two is an `INTERVAL DAY TO SECOND` between the instants, and
  `+ n` gives a `DATE` of the local time. Two of them compare by instant (example L).
- The examples on this page never print the clock. They compare it with a fixed date or reduce it with `CASE`.
- The week starts on Sunday (NLS territory AMERICA): `TO_CHAR(DATE, 'D')` is 1 for Sunday, `TRUNC(date, 'D')` goes to
  Sunday.
- `TIMESTAMPADD`, `TO_DSINTERVAL`, `TO_YMINTERVAL` are not available (ORA-00904).

## Differences from Oracle

- **A region is kept as its offset at that instant.** `FROM_TZ(..., 'Europe/Paris')`, `AT TIME ZONE 'America/New_York'`
  and a session in a region give the offset alone: `EXTRACT(TIMEZONE_REGION ...)` is `UNKNOWN` and `TIMEZONE_ABBR`
  `UNK` (Oracle: `Europe/Paris`, `CET`), and `TO_CHAR(..., 'TZR')` shows `+01:00`. Adding an interval keeps the offset,
  not the region's summer time.
- `MIN` and `MAX` of equal instants at different offsets show the first in lexdb's scan order, which is primary key
  order; Oracle's is the order the rows were inserted.
- A session starts in the time zone the client sends at logon, as in Oracle (example B's first `SESSIONTIMEZONE`, a JDBC
  client in UTC, is `UTC`, as it is after `ALTER SESSION SET TIME_ZONE = 'UTC'`; `Etc/UTC` and `GMT` too). A zone lexdb
  does not know leaves the session at `+00:00`, where Oracle refuses the logon.
- `EXTRACT(HOUR FROM DATE ...)` returns 0; Oracle refuses a `DATE` with a time field (ORA-30076). `QUARTER` and `DOW`
  are accepted by `EXTRACT`; Oracle does not know them.
- `TIME_BUCKET` needs the *origin* argument and fails without it (ORA-00909, example I); Oracle makes it optional.
- A `DATE` result is shown with a time of day; use `TO_CHAR` for a date alone. A timestamp is shown with its
  fraction (`2026-11-23 14:30:00.0`), an interval as `days hours:minutes:seconds`.
- `CAST(TIMESTAMP '2026-11-23 14:05:09.9' AS DATE)` rounds the second (14:05:10); Oracle truncates the fraction.
- `MONTHS_BETWEEN` and a `DATE` difference with many digits can print in exponent form (`1.4166666666666666666666666666666666667E00`).

## Examples

### A. The clock, without printing it

<!-- example: oracle -->
```sql
SELECT CASE WHEN SYSDATE > DATE '2020-01-01' THEN 'after' ELSE 'before' END AS sysdate_check,
       CASE WHEN SYSTIMESTAMP > TIMESTAMP '2020-01-01 00:00:00' THEN 'after' ELSE 'before' END AS systimestamp_check,
       CASE WHEN CURRENT_DATE > DATE '2020-01-01' THEN 'after' END AS current_date_check,
       CASE WHEN CURRENT_TIMESTAMP > TIMESTAMP '2020-01-01 00:00:00 +00:00' THEN 'after' END AS current_timestamp_check,
       CASE WHEN LOCALTIMESTAMP > TIMESTAMP '2020-01-01 00:00:00' THEN 'after' END AS localtimestamp_check
FROM dual;
SELECT CASE WHEN TRUNC(SYSDATE) = TRUNC(CURRENT_DATE) THEN 'same day' END AS same_day,
       CASE WHEN SYSDATE - TRUNC(SYSDATE) < 1 THEN 'under a day' END AS since_midnight,
       TO_CHAR(TRUNC(SYSDATE), 'HH24:MI:SS') AS midnight, SYSDATE - SYSDATE AS no_time_passes,
       CASE WHEN EXTRACT(YEAR FROM SYSTIMESTAMP) >= 2026 THEN 'valid' END AS year_ok
FROM dual;
```

```text
SYSDATE_CHECK SYSTIMESTAMP_CHECK CURRENT_DATE_CHECK CURRENT_TIMESTAMP_CHECK LOCALTIMESTAMP_CHECK
------------- ------------------ ------------------ ----------------------- --------------------
after         after              after              after                   after

1 row selected.

SAME_DAY SINCE_MIDNIGHT MIDNIGHT NO_TIME_PASSES YEAR_OK
-------- -------------- -------- -------------- -------
same day under a day    00:00:00              0 valid

1 row selected.
```

### B. Time zones

<!-- example: oracle -->
```sql
SELECT SESSIONTIMEZONE AS session_tz, DBTIMEZONE AS database_tz FROM dual;
ALTER SESSION SET TIME_ZONE = 'Europe/Paris';
SELECT SESSIONTIMEZONE AS session_tz FROM dual;
ALTER SESSION SET TIME_ZONE = '+02:00';
SELECT SESSIONTIMEZONE AS session_tz, TO_CHAR(CURRENT_TIMESTAMP, 'TZH:TZM') AS current_offset, TO_CHAR(SYSTIMESTAMP, 'TZH:TZM') AS system_offset,
       CASE WHEN LOCALTIMESTAMP - CAST(SYS_EXTRACT_UTC(SYSTIMESTAMP) AS TIMESTAMP) > INTERVAL '1' HOUR THEN 'ahead of UTC' END AS localtimestamp_check
FROM dual;
ALTER SESSION SET TIME_ZONE = 'UTC';
```

```text
SESSION_TZ DATABASE_TZ
---------- -----------
UTC        +00:00

1 row selected.

Session altered.

SESSION_TZ
------------
Europe/Paris

1 row selected.

Session altered.

SESSION_TZ CURRENT_OFFSET SYSTEM_OFFSET LOCALTIMESTAMP_CHECK
---------- -------------- ------------- --------------------
+02:00     +02:00         +00:00        ahead of UTC

1 row selected.

Session altered.
```

### C. ADD_MONTHS, MONTHS_BETWEEN and LAST_DAY

<!-- example: oracle -->
```sql
SELECT TO_CHAR(ADD_MONTHS(DATE '2026-01-31', 1), 'YYYY-MM-DD') AS jan31_plus1, TO_CHAR(ADD_MONTHS(DATE '2026-01-15', 13), 'YYYY-MM-DD') AS plus13,
       TO_CHAR(ADD_MONTHS(DATE '2026-03-31', -1), 'YYYY-MM-DD') AS minus1, TO_CHAR(ADD_MONTHS(DATE '2026-02-28', 1), 'YYYY-MM-DD') AS last_to_last,
       TO_CHAR(ADD_MONTHS(DATE '2024-02-29', 12), 'YYYY-MM-DD') AS leap_day, TO_CHAR(ADD_MONTHS(TIMESTAMP '2026-01-31 10:11:12', 1), 'YYYY-MM-DD HH24:MI:SS') AS keeps_time
FROM dual;
SELECT MONTHS_BETWEEN(DATE '2026-03-15', DATE '2026-01-15') AS two_months, MONTHS_BETWEEN(DATE '2026-03-31', DATE '2026-02-28') AS last_days,
       ROUND(MONTHS_BETWEEN(DATE '2026-03-16', DATE '2026-03-01'), 4) AS fraction, ROUND(MONTHS_BETWEEN(DATE '2026-01-31', DATE '2026-03-01'), 4) AS negative
FROM dual;
SELECT TO_CHAR(LAST_DAY(DATE '2026-02-10'), 'YYYY-MM-DD') AS feb_2026, TO_CHAR(LAST_DAY(DATE '2024-02-10'), 'YYYY-MM-DD') AS feb_2024,
       TO_CHAR(LAST_DAY(TIMESTAMP '2026-02-10 13:14:15'), 'YYYY-MM-DD HH24:MI:SS') AS keeps_time
FROM dual;
```

```text
JAN31_PLUS1 PLUS13     MINUS1     LAST_TO_LAST LEAP_DAY   KEEPS_TIME
----------- ---------- ---------- ------------ ---------- -------------------
2026-02-28  2027-02-15 2026-02-28 2026-03-31   2025-02-28 2026-02-28 10:11:12

1 row selected.

TWO_MONTHS LAST_DAYS FRACTION NEGATIVE
---------- --------- -------- --------
         2         1   0.4839  -1.0323

1 row selected.

FEB_2026   FEB_2024   KEEPS_TIME
---------- ---------- -------------------
2026-02-28 2024-02-29 2026-02-28 13:14:15

1 row selected.
```

### D. NEXT_DAY

<!-- example: oracle -->
```sql
SELECT TO_CHAR(DATE '2026-11-23', 'DAY') AS start_day, TO_CHAR(NEXT_DAY(DATE '2026-11-23', 'FRIDAY'), 'YYYY-MM-DD') AS friday,
       TO_CHAR(NEXT_DAY(DATE '2026-11-23', 'MONDAY'), 'YYYY-MM-DD') AS next_monday, TO_CHAR(NEXT_DAY(DATE '2026-11-23', 'MON'), 'YYYY-MM-DD') AS abbreviated,
       TO_CHAR(NEXT_DAY(DATE '2026-11-23', 'sun'), 'YYYY-MM-DD') AS lower_case
FROM dual;
SELECT NEXT_DAY(DATE '2026-11-23', 'XYZ') FROM dual;
```

```text
START_DAY FRIDAY     NEXT_MONDAY ABBREVIATED LOWER_CASE
--------- ---------- ----------- ----------- ----------
MONDAY    2026-11-27 2026-11-30  2026-11-30  2026-11-29

1 row selected.

ERROR:
ORA-01846: not a valid day of the week
```

### E. EXTRACT

<!-- example: oracle -->
```sql
SELECT EXTRACT(YEAR FROM DATE '2026-11-23') AS yr, EXTRACT(MONTH FROM DATE '2026-11-23') AS mon, EXTRACT(DAY FROM DATE '2026-11-23') AS dy,
       EXTRACT(HOUR FROM TIMESTAMP '2026-11-23 14:30:45.5') AS hr, EXTRACT(MINUTE FROM TIMESTAMP '2026-11-23 14:30:45.5') AS mi,
       EXTRACT(SECOND FROM TIMESTAMP '2026-11-23 14:30:45.5') AS ss
FROM dual;
SELECT EXTRACT(DAY FROM INTERVAL '3 04:05:06' DAY TO SECOND) AS interval_days, EXTRACT(HOUR FROM INTERVAL '3 04:05:06' DAY TO SECOND) AS interval_hours,
       EXTRACT(YEAR FROM INTERVAL '2-5' YEAR TO MONTH) AS interval_years, EXTRACT(MONTH FROM INTERVAL '2-5' YEAR TO MONTH) AS interval_months
FROM dual;
SELECT EXTRACT(HOUR FROM TIMESTAMP '2026-11-23 14:30:45 +05:30') AS utc_hour, EXTRACT(TIMEZONE_HOUR FROM TIMESTAMP '2026-11-23 14:30:45 +05:30') AS tz_hour,
       EXTRACT(TIMEZONE_MINUTE FROM TIMESTAMP '2026-11-23 14:30:45 +05:30') AS tz_minute, TO_CHAR(TIMESTAMP '2026-11-23 14:30:45 +05:30', 'HH24:MI') AS local_time
FROM dual;
```

```text
  YR MON DY HR MI   SS
---- --- -- -- -- ----
2026  11 23 14 30 45.5

1 row selected.

INTERVAL_DAYS INTERVAL_HOURS INTERVAL_YEARS INTERVAL_MONTHS
------------- -------------- -------------- ---------------
            3              4              2               5

1 row selected.

UTC_HOUR TZ_HOUR TZ_MINUTE LOCAL_TIME
-------- ------- --------- ----------
       9       5        30 14:30

1 row selected.
```

### F. TRUNC and ROUND of dates

<!-- example: oracle -->
```sql
SELECT TO_CHAR(TRUNC(TIMESTAMP '2026-11-23 14:30:45'), 'YYYY-MM-DD HH24:MI:SS') AS day_start, TO_CHAR(TRUNC(TIMESTAMP '2026-11-23 14:30:45', 'HH'), 'YYYY-MM-DD HH24:MI:SS') AS hour_start,
       TO_CHAR(TRUNC(DATE '2026-11-23', 'MM'), 'YYYY-MM-DD') AS month_start, TO_CHAR(TRUNC(DATE '2026-11-23', 'YYYY'), 'YYYY-MM-DD') AS year_start,
       TO_CHAR(TRUNC(DATE '2026-11-23', 'Q'), 'YYYY-MM-DD') AS quarter_start, TO_CHAR(TRUNC(DATE '2026-11-25', 'IW'), 'YYYY-MM-DD') AS iso_week_start,
       TO_CHAR(TRUNC(DATE '2026-11-25', 'DAY'), 'YYYY-MM-DD') AS sunday
FROM dual;
SELECT TO_CHAR(ROUND(DATE '2026-11-23', 'MM'), 'YYYY-MM-DD') AS round_month_up, TO_CHAR(ROUND(DATE '2026-11-10', 'MM'), 'YYYY-MM-DD') AS round_month_down,
       TO_CHAR(ROUND(DATE '2026-07-01', 'YYYY'), 'YYYY-MM-DD') AS round_year, TO_CHAR(ROUND(TIMESTAMP '2026-11-23 14:30:45', 'HH24'), 'YYYY-MM-DD HH24:MI:SS') AS round_hour,
       TO_CHAR(ROUND(TIMESTAMP '2026-11-23 14:30:45'), 'YYYY-MM-DD HH24:MI:SS') AS round_day
FROM dual;
```

```text
DAY_START           HOUR_START          MONTH_START YEAR_START QUARTER_START ISO_WEEK_START SUNDAY
------------------- ------------------- ----------- ---------- ------------- -------------- ----------
2026-11-23 00:00:00 2026-11-23 14:00:00 2026-11-01  2026-01-01 2026-10-01    2026-11-23     2026-11-22

1 row selected.

ROUND_MONTH_UP ROUND_MONTH_DOWN ROUND_YEAR ROUND_HOUR          ROUND_DAY
-------------- ---------------- ---------- ------------------- -------------------
2026-12-01     2026-11-01       2027-01-01 2026-11-23 15:00:00 2026-11-24 00:00:00

1 row selected.
```

### G. Time zone functions

<!-- example: oracle -->
```sql
SELECT TO_CHAR(SYS_EXTRACT_UTC(TIMESTAMP '2026-11-23 14:30:00 +05:30'), 'YYYY-MM-DD HH24:MI:SS') AS utc FROM dual;
SELECT TO_CHAR(FROM_TZ(TIMESTAMP '2026-11-23 14:30:00', '+05:30'), 'YYYY-MM-DD HH24:MI TZH:TZM') AS from_offset,
       TO_CHAR(FROM_TZ(TIMESTAMP '2026-11-23 14:30:00', 'Europe/Paris'), 'YYYY-MM-DD HH24:MI TZH:TZM') AS from_region
FROM dual;
SELECT TO_CHAR(FROM_TZ(TIMESTAMP '2026-11-23 14:05:09', '+02:00') AT TIME ZONE '+00:00', 'HH24:MI TZH:TZM') AS at_utc,
       TO_CHAR(FROM_TZ(TIMESTAMP '2026-11-23 14:05:09', 'UTC') AT TIME ZONE 'America/New_York', 'HH24:MI TZH:TZM') AS at_new_york,
       TO_CHAR(TIMESTAMP '2026-11-23 14:05:09 +02:00' AT LOCAL, 'HH24:MI TZH:TZM') AS at_local,
       TO_CHAR(TIMESTAMP '2026-11-23 14:05:09' AT TIME ZONE '+05:30', 'HH24:MI TZH:TZM') AS without_zone
FROM dual;
SELECT TZ_OFFSET('+05:30') AS fixed, TZ_OFFSET('Asia/Tokyo') AS tokyo, TZ_OFFSET(DBTIMEZONE) AS db, TZ_OFFSET(SESSIONTIMEZONE) AS session_ FROM dual;
SELECT TO_CHAR(NEW_TIME(TO_DATE('2026-11-23 12:00', 'YYYY-MM-DD HH24:MI'), 'GMT', 'EST'), 'YYYY-MM-DD HH24:MI') AS gmt_noon_in_est,
       TO_CHAR(NEW_TIME(TO_DATE('2026-11-23 09:00', 'YYYY-MM-DD HH24:MI'), 'PST', 'EST'), 'YYYY-MM-DD HH24:MI') AS pst_9_in_est
FROM dual;
SELECT FROM_TZ(TIMESTAMP '2026-11-23 14:05:09', 'Mars/Olympus') FROM dual;
SELECT NEW_TIME(DATE '2026-11-23', 'GMT', 'XXX') FROM dual;
SELECT TIMESTAMP '2026-11-23 14:05:09 +16:00' FROM dual;
```

```text
UTC
-------------------
2026-11-23 09:00:00

1 row selected.

FROM_OFFSET             FROM_REGION
----------------------- -----------------------
2026-11-23 14:30 +05:30 2026-11-23 14:30 +01:00

1 row selected.

AT_UTC       AT_NEW_YORK  AT_LOCAL     WITHOUT_ZONE
------------ ------------ ------------ ------------
12:05 +00:00 09:05 -05:00 12:05 +00:00 19:35 +05:30

1 row selected.

FIXED  TOKYO  DB     SESSION_
------ ------ ------ --------
+05:30 +09:00 +00:00 +00:00

1 row selected.

GMT_NOON_IN_EST  PST_9_IN_EST
---------------- ----------------
2026-11-23 07:00 2026-11-23 12:00

1 row selected.

ERROR:
ORA-01882: time zone region not found

ERROR:
ORA-01857: not a valid time zone

ERROR:
ORA-01874: time zone hour must be between -15 and 15
```

### H. Intervals

<!-- example: oracle -->
```sql
SELECT EXTRACT(HOUR FROM NUMTODSINTERVAL(90, 'MINUTE')) AS hours, EXTRACT(MINUTE FROM NUMTODSINTERVAL(90, 'MINUTE')) AS minutes,
       EXTRACT(DAY FROM NUMTODSINTERVAL(1.5, 'DAY')) AS days, EXTRACT(HOUR FROM NUMTODSINTERVAL(1.5, 'DAY')) AS day_hours,
       EXTRACT(YEAR FROM NUMTOYMINTERVAL(14, 'MONTH')) AS years, EXTRACT(MONTH FROM NUMTOYMINTERVAL(14, 'MONTH')) AS months
FROM dual;
SELECT TO_CHAR(DATE '2026-11-23' + NUMTODSINTERVAL(36, 'HOUR'), 'YYYY-MM-DD HH24:MI') AS plus_36_hours,
       TO_CHAR(DATE '2026-11-23' + NUMTOYMINTERVAL(3, 'MONTH'), 'YYYY-MM-DD') AS plus_3_months,
       TO_CHAR(DATE '2026-11-23' + 1.5, 'YYYY-MM-DD HH24:MI') AS plus_1_5_days, DATE '2026-11-25' - DATE '2026-11-23' AS days_between
FROM dual;
SELECT TO_CHAR(DATE '2026-01-31' + INTERVAL '1' MONTH, 'YYYY-MM-DD') AS no_feb_31 FROM dual;
SELECT TO_CHAR(TIMESTAMP '2026-01-31 23:00:00 -05:00' + INTERVAL '1' MONTH, 'YYYY-MM-DD HH24:MI TZH:TZM') AS utc_month FROM dual;
SELECT TIMESTAMP '2026-11-25 12:00:00' - TIMESTAMP '2026-11-23 06:30:00' AS timestamp_difference FROM dual;
```

```text
HOURS MINUTES DAYS DAY_HOURS YEARS MONTHS
----- ------- ---- --------- ----- ------
    1      30    1        12     1      2

1 row selected.

PLUS_36_HOURS    PLUS_3_MONTHS PLUS_1_5_DAYS    DAYS_BETWEEN
---------------- ------------- ---------------- ------------
2026-11-24 12:00 2027-02-23    2026-11-24 12:00            2

1 row selected.

ERROR:
ORA-01839: date not valid for month specified

UTC_MONTH
-----------------------
2026-02-28 23:00 -05:00

1 row selected.

TIMESTAMP_DIFFERENCE
--------------------
2 5:30:0.0

1 row selected.
```

### I. TIME_BUCKET

<!-- example: oracle -->
```sql
SELECT TO_CHAR(TIME_BUCKET(TIMESTAMP '2026-11-23 14:37:00', INTERVAL '15' MINUTE, TIMESTAMP '2026-01-01 00:00:00'), 'HH24:MI') AS quarter_hour,
       TO_CHAR(TIME_BUCKET(TIMESTAMP '2026-11-23 14:37:00', INTERVAL '1' HOUR, TIMESTAMP '2026-01-01 00:00:00', END), 'HH24:MI') AS bucket_end,
       TO_CHAR(TIME_BUCKET(DATE '2026-11-23', INTERVAL '7' DAY, DATE '2026-01-01'), 'YYYY-MM-DD') AS week_bucket
FROM dual;
SELECT TIME_BUCKET(TIMESTAMP '2026-11-23 14:37:00', INTERVAL '15' MINUTE) FROM dual;
```

```text
QUARTER_HOUR BUCKET_END WEEK_BUCKET
------------ ---------- -----------
14:30        15:00      2026-11-19

1 row selected.

ERROR:
ORA-00909: invalid number of arguments
```

### J. DATEADD, DATEDIFF and TIMESTAMPDIFF

<!-- example: oracle -->
```sql
SELECT TO_CHAR(DATEADD(DAY, 5, DATE '2026-11-23'), 'YYYY-MM-DD') AS plus_days, TO_CHAR(DATEADD(MONTH, 2, DATE '2026-11-23'), 'YYYY-MM-DD') AS plus_months,
       TO_CHAR(DATEADD(HOUR, -3, TIMESTAMP '2026-11-23 01:00:00'), 'YYYY-MM-DD HH24:MI') AS minus_hours,
       TO_CHAR(DATEADD(YEAR, 1, DATE '2026-02-28'), 'YYYY-MM-DD') AS plus_year
FROM dual;
SELECT DATEDIFF(DAY, DATE '2026-11-01', DATE '2026-11-23') AS days, DATEDIFF(MONTH, DATE '2026-01-31', DATE '2026-03-01') AS months,
       DATEDIFF(YEAR, DATE '2025-12-31', DATE '2026-01-01') AS years, DATEDIFF(WEEK, DATE '2026-11-01', DATE '2026-11-23') AS weeks,
       DATEDIFF(HOUR, TIMESTAMP '2026-11-23 01:00:00', TIMESTAMP '2026-11-24 03:30:00') AS hours
FROM dual;
SELECT TIMESTAMPDIFF(HOUR, TIMESTAMP '2026-11-23 01:00:00', TIMESTAMP '2026-11-24 03:30:00') AS hours,
       TIMESTAMPDIFF(MINUTE, TIMESTAMP '2026-11-23 01:00:00', TIMESTAMP '2026-11-23 03:30:00') AS minutes,
       TIMESTAMPDIFF(DAY, DATE '2026-11-01', DATE '2026-11-23') AS days
FROM dual;
```

```text
PLUS_DAYS  PLUS_MONTHS MINUS_HOURS      PLUS_YEAR
---------- ----------- ---------------- ----------
2026-11-28 2027-01-23  2026-11-22 22:00 2027-02-28

1 row selected.

DAYS MONTHS YEARS WEEKS HOURS
---- ------ ----- ----- -----
  22      2     1     3    26

1 row selected.

HOURS MINUTES DAYS
----- ------- ----
   26     150   22

1 row selected.
```

### K. Functions that are not available

<!-- example: oracle -->
```sql
SELECT TIMESTAMPADD(DAY, 1, DATE '2026-11-01') FROM dual;
SELECT TO_DSINTERVAL('3 04:05:06') FROM dual;
```

```text
ERROR:
ORA-00904: "DAY": invalid identifier

ERROR:
ORA-00904: invalid identifier
```

### L. Arithmetic and comparison with a time zone

The offset stays through arithmetic; a comparison is by instant.

<!-- example: oracle -->
```sql
SELECT TO_CHAR(TIMESTAMP '2026-03-15 10:00:00 +02:00' + INTERVAL '1' DAY, 'YYYY-MM-DD HH24:MI TZH:TZM') AS plus_day,
       TO_CHAR(TIMESTAMP '2026-03-15 10:00:00 +02:00' - INTERVAL '5' HOUR, 'YYYY-MM-DD HH24:MI TZH:TZM') AS minus_5_hours,
       TO_CHAR(TIMESTAMP '2026-01-15 10:00:00 -03:00' + INTERVAL '1' MONTH, 'YYYY-MM-DD HH24:MI TZH:TZM') AS plus_month,
       TIMESTAMP '2026-03-15 10:00:00 +02:00' - TIMESTAMP '2026-03-15 07:00:00 +00:00' AS difference
FROM dual;
SELECT CASE WHEN TIMESTAMP '2026-03-15 10:00:00 +02:00' = TIMESTAMP '2026-03-15 08:00:00 +00:00' THEN 'same instant' END AS equal,
       CASE WHEN TIMESTAMP '2026-03-15 10:00:00 +02:00' < TIMESTAMP '2026-03-15 09:00:00 +00:00' THEN 'earlier' END AS less,
       TO_CHAR(GREATEST(TIMESTAMP '2026-03-15 10:00:00 +02:00', TIMESTAMP '2026-03-15 09:00:00 +00:00'), 'HH24:MI TZH:TZM') AS later,
       TO_CHAR(TRUNC(TIMESTAMP '2026-03-15 01:30:00 +05:30'), 'YYYY-MM-DD HH24:MI') AS trunc_local_day,
       TO_CHAR(TIMESTAMP '2026-03-15 10:00:00 +02:00' + 1, 'YYYY-MM-DD HH24:MI') AS plus_one_is_date
FROM dual;
```

```text
PLUS_DAY                MINUS_5_HOURS           PLUS_MONTH              DIFFERENCE
----------------------- ----------------------- ----------------------- ----------
2026-03-16 10:00 +02:00 2026-03-15 05:00 +02:00 2026-02-15 10:00 -03:00 0 1:0:0.0

1 row selected.

EQUAL        LESS    LATER        TRUNC_LOCAL_DAY  PLUS_ONE_IS_DATE
------------ ------- ------------ ---------------- ----------------
same instant earlier 09:00 +00:00 2026-03-15 00:00 2026-03-16 10:00

1 row selected.
```

## See also

[Conversion functions](functions-conversion.md), [Date and time data types](data-types-datetime.md),
[Operators](operators.md), [ALTER SESSION](alter-session.md), [Numeric functions](functions-numeric.md)
