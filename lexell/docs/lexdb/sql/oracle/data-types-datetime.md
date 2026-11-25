# Date and time types

`DATE`, `TIMESTAMP` with and without a time zone, and the `INTERVAL` types.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DATE
TIMESTAMP [ ( fractional_digits ) ]
TIMESTAMP [ ( fractional_digits ) ] WITH TIME ZONE
TIMESTAMP [ ( fractional_digits ) ] WITH LOCAL TIME ZONE
INTERVAL YEAR [ ( p ) ] TO MONTH
INTERVAL DAY [ ( p ) ] TO SECOND [ ( fractional_digits ) ]

DATE 'YYYY-MM-DD'
TIMESTAMP 'YYYY-MM-DD HH24:MI:SS[.FF]'
TIMESTAMP 'YYYY-MM-DD HH24:MI:SS[.FF] { +hh:mi | -hh:mi | region }'
INTERVAL 'text' { YEAR TO MONTH | DAY TO SECOND | unit }
```

## Arguments

`DATE`
: A date with a time of day to the second. It is a `TIMESTAMP(0)` underneath.

`TIMESTAMP(p)`
: A date and time with *p* fractional digits (0 to 9, default 6). lexdb keeps microseconds at most.

`WITH TIME ZONE`
: A timestamp and the time zone offset it was written with: `TIMESTAMP '2026-03-15 10:00:00 +02:00'` is ten o'clock
  at `+02:00`, and stays so. The offset's hours are -15 to 15 (ORA-01874 beyond) and its minutes 0 to 59
  (ORA-01875). A region name (`'Europe/Berlin'`) is read as the offset it has at that instant: see the differences.

`WITH LOCAL TIME ZONE`
: An instant without an offset of its own: it is shown in the session's time zone (`ALTER SESSION SET TIME_ZONE`), so
  the same value reads `10:00` in a session at `+02:00` and `03:00` in one at `-05:00`.

`INTERVAL YEAR TO MONTH`, `INTERVAL DAY TO SECOND`
: A span of time in years and months, or in days to seconds.

## Remarks

- A `DATE` has a time part: `DATE '2026-03-15'` is midnight. JDBC clients and `SELECT` show it as `2026-03-15
  00:00:00`; use `TO_CHAR(d, 'YYYY-MM-DD')` to choose the format.
- `DATE + n` adds *n* days (fractions are parts of a day); `DATE - DATE` is a number of days; `TIMESTAMP -
  TIMESTAMP` is an interval; `DATE + INTERVAL '1' HOUR` adds the interval.
- The default formats come from `NLS_DATE_FORMAT` and `NLS_TIMESTAMP_FORMAT`: see
  [ALTER SESSION](alter-session.md).
- `SYSDATE`, `SYSTIMESTAMP` and `CURRENT_DATE` give the clock; the other date functions are in
  [functions](README.md#functions).
- **Time zones.** Two `TIMESTAMP WITH TIME ZONE` values are compared by instant: `10:00 +02:00` equals `08:00 +00:00`.
  `ORDER BY`, `GROUP BY`, `DISTINCT`, joins, `IN` and indexes go by instant too (a unique index takes only one of the
  two); a group shows the offset of its first row. `TO_CHAR` with `TZH:TZM` shows each value's own offset, and
  `SYS_EXTRACT_UTC` the instant in UTC (example F).
- Arithmetic keeps the offset: `TIMESTAMP WITH TIME ZONE + INTERVAL` is at the same offset (months count in UTC, as in
  Oracle, and a day that is not in the month reached is ORA-01839); the difference of two is an `INTERVAL DAY TO SECOND` between the instants; `+ n` (days) gives a
  `DATE` of the local time (example G).
- A `TIMESTAMP` or `DATE` that becomes a `TIMESTAMP WITH TIME ZONE` (`CAST`, an `INSERT` into such a column) is read
  in the session's time zone; `CAST(x AS TIMESTAMP)` and `CAST(x AS DATE)` of one give its local time.
- Without a format, `TO_CHAR` and `CAST(... AS VARCHAR2(n))` of a `TIMESTAMP WITH TIME ZONE` use
  `NLS_TIMESTAMP_TZ_FORMAT` (`DD-MON-RR HH.MI.SSXFF AM TZR`). JDBC clients get the value with its offset (Oracle's type
  181): `getString` shows `2026-03-15 10:00:00.0 +2:00`, and `getObject(i, OffsetDateTime.class)` keeps the offset.
  A `TIMESTAMP WITH LOCAL TIME ZONE` value goes as Oracle's type 231, which the driver shows in its session's zone
  (`2026-03-15 08:00:00.0 UTC` for a client in UTC, example H).

## Differences from Oracle

- **`INTERVAL` columns are not supported.** `CREATE TABLE t (a INTERVAL DAY TO SECOND)` is ORA-00900. Intervals work
  as values in expressions (`INTERVAL '2 03:04:05' DAY TO SECOND`, `NUMTODSINTERVAL`, a difference of two
  timestamps).
- **A region is kept as its offset.** `FROM_TZ(TIMESTAMP '2026-03-15 10:00:00', 'Europe/Berlin')` is `10:00 +01:00`:
  `TO_CHAR(..., 'TZR')` shows `+01:00` (Oracle: `EUROPE/BERLIN`), `TZD` is empty (Oracle: `CET`), and
  `EXTRACT(TIMEZONE_REGION ...)` is `UNKNOWN`. Adding an interval keeps the offset, not the region's rules for
  summer time.
- **A text inserted into a `TIMESTAMP WITH TIME ZONE` column is read as ISO** (`'2026-03-15 10:00:00 +02:00'`), not by
  `NLS_TIMESTAMP_TZ_FORMAT` (`'15-MAR-26 10.00.00.000000 AM +02:00'` is ORA-01861; Oracle does the opposite and gives
  ORA-01843 for the ISO text). `CAST` and `TO_TIMESTAMP_TZ` read the NLS format, as in Oracle.
- A `TIMESTAMP` literal shown as text has six fractional digits (`10.00.00.000000 AM +02:00`; Oracle nine).
- After `ALTER SESSION SET TIME_ZONE`, a JDBC client still shows a `TIMESTAMP WITH LOCAL TIME ZONE` value in the zone
  it logged on with (`getString` gives `2026-03-15 13:30:00.0 Asia/Kolkata` in a session set to `-05:00`; Oracle
  `2026-03-15 03:00:00.0 -05:00`): Oracle tells the driver the new zone, lexdb does not. `TO_CHAR` shows it in the
  session's zone, as in Oracle (example H).
- `TO_CHAR` of a `TIMESTAMP WITH LOCAL TIME ZONE` takes `TZH` and `TZM` (the session's offset); Oracle gives ORA-01821.
- `MIN` and `MAX` of equal instants at different offsets show the first in lexdb's scan order, which is primary key
  order; Oracle's is the order the rows were inserted.
- A `VALUES` list (`FROM (VALUES (...)) v (a, b)`) keeps the instant, not the offset: `10:00 +02:00` comes out as
  `08:00 +00:00`.
- A `TIMESTAMP WITH TIME ZONE` column made by a lexdb older than main 178ea2df holds instants without offsets: it
  behaves as `WITH LOCAL TIME ZONE` until `ALTER TABLE t MODIFY (c TIMESTAMP WITH TIME ZONE)` rewrites it.
- `USER_TAB_COLUMNS` shows `TIMESTAMP WITH LOCAL TIME ZONE` and `TIMESTAMP WITH TIME ZONE` columns both as
  `TIMESTAMP(6) WITH TIME ZONE`.
- A value is rounded to the column's fractional digits (`.1236` into `TIMESTAMP(3)` is `.124`).
- Intervals print as `0 12:0:0.0` and `1-6` (without the padding Oracle gives).

## Examples

### A. Dates and timestamps

<!-- example: oracle -->
```sql
SELECT DATE '2026-03-15' AS d, TIMESTAMP '2026-03-15 13:45:30.123456' AS ts,
       TO_CHAR(DATE '2026-03-15' + 1, 'YYYY-MM-DD') AS plus_one_day,
       DATE '2026-03-20' - DATE '2026-03-15' AS days_between,
       TO_CHAR(TIMESTAMP '2026-03-15 13:45:30.5' + INTERVAL '1' HOUR, 'YYYY-MM-DD HH24:MI:SS.FF') AS plus_hour
FROM dual;
```

```text
D                   TS                         PLUS_ONE_DAY DAYS_BETWEEN PLUS_HOUR
------------------- -------------------------- ------------ ------------ -----------------------------
2026-03-15 00:00:00 2026-03-15 13:45:30.123456 2026-03-16              5 2026-03-15 14:45:30.500000000

1 row selected.
```

### B. Columns

<!-- example: oracle -->
```sql
CREATE TABLE d (a DATE, b TIMESTAMP(3), c TIMESTAMP WITH TIME ZONE, d TIMESTAMP WITH LOCAL TIME ZONE);
SELECT column_name, data_type FROM user_tab_columns WHERE table_name = 'D' ORDER BY column_id;
INSERT INTO d (a, b) VALUES (DATE '2026-03-15', TIMESTAMP '2026-03-15 10:00:00.1236');
SELECT TO_CHAR(a, 'YYYY-MM-DD HH24:MI:SS') AS a, TO_CHAR(b, 'YYYY-MM-DD HH24:MI:SS.FF3') AS b FROM d;
```

```text
Table created.

COLUMN_NAME DATA_TYPE
----------- ---------------------------
A           DATE
B           TIMESTAMP(3)
C           TIMESTAMP(6) WITH TIME ZONE
D           TIMESTAMP(6) WITH TIME ZONE

4 rows selected.

1 row created.

A                   B
------------------- -----------------------
2026-03-15 00:00:00 2026-03-15 10:00:00.124

1 row selected.
```

### C. Time zones and intervals

<!-- example: oracle -->
```sql
SELECT TIMESTAMP '2026-03-15 13:45:30 +05:30' AS tstz,
       TIMESTAMP '2026-03-16 00:00:00' - TIMESTAMP '2026-03-15 12:00:00' AS ds,
       INTERVAL '1-6' YEAR TO MONTH AS ym, INTERVAL '2 03:04:05' DAY TO SECOND AS dts FROM dual;
SELECT NUMTODSINTERVAL(90, 'MINUTE') AS a, NUMTOYMINTERVAL(14, 'MONTH') AS b FROM dual;
```

```text
TSTZ                        DS         YM  DTS
--------------------------- ---------- --- ---------
2026-03-15 13:45:30.0 +5:30 0 12:0:0.0 1-6 2 3:4:5.0

1 row selected.

A          B
---------- ---
0 1:30:0.0 1-2

1 row selected.
```

### D. Converting

<!-- example: oracle -->
```sql
SELECT TO_CHAR(DATE '2026-03-15', 'DD-MON-YYYY') AS a, TO_DATE('15-03-2026', 'DD-MM-YYYY') AS b,
       TO_TIMESTAMP('2026-03-15 10:00:00', 'YYYY-MM-DD HH24:MI:SS') AS c FROM dual;
```

```text
A           B                   C
----------- ------------------- ---------------------
15-MAR-2026 2026-03-15 00:00:00 2026-03-15 10:00:00.0

1 row selected.
```

### E. Interval columns

<!-- example: oracle -->
```sql
CREATE TABLE iv (a INTERVAL DAY TO SECOND);
CREATE TABLE iv2 (a INTERVAL YEAR TO MONTH);
```

```text
ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement
```

### F. A column of mixed offsets

Four departures at four offsets; three of them are the same instant, 08:00 UTC. They sort, compare and count by
instant, and each keeps its own offset.

<!-- example: oracle -->
```sql
CREATE TABLE departures (id NUMBER PRIMARY KEY, city VARCHAR2(10), dep TIMESTAMP WITH TIME ZONE);
INSERT INTO departures VALUES (1, 'Athens', TIMESTAMP '2026-03-15 10:00:00 +02:00');
INSERT INTO departures VALUES (2, 'London', TIMESTAMP '2026-03-15 08:00:00 +00:00');
INSERT INTO departures VALUES (3, 'New York', TIMESTAMP '2026-03-15 03:00:00 -05:00');
INSERT INTO departures VALUES (4, 'Mumbai', TIMESTAMP '2026-03-15 12:00:00 +05:30');
SELECT id, city, TO_CHAR(dep, 'YYYY-MM-DD HH24:MI TZH:TZM') AS local_time, TO_CHAR(SYS_EXTRACT_UTC(dep), 'HH24:MI') AS utc
FROM departures ORDER BY dep, id;
SELECT city FROM departures WHERE dep = TIMESTAMP '2026-03-15 11:00:00 +03:00' ORDER BY id;
SELECT COUNT(DISTINCT dep) AS instants, COUNT(*) AS n_rows FROM departures;
SELECT id, dep FROM departures WHERE id IN (1, 4) ORDER BY id;
COMMIT;
```

```text
Table created.

1 row created.

1 row created.

1 row created.

1 row created.

ID CITY     LOCAL_TIME              UTC
-- -------- ----------------------- -----
 4 Mumbai   2026-03-15 12:00 +05:30 06:30
 1 Athens   2026-03-15 10:00 +02:00 08:00
 2 London   2026-03-15 08:00 +00:00 08:00
 3 New York 2026-03-15 03:00 -05:00 08:00

4 rows selected.

CITY
--------
Athens
London
New York

3 rows selected.

INSTANTS N_ROWS
-------- ------
       2      4

1 row selected.

ID DEP
-- ---------------------------
 1 2026-03-15 10:00:00.0 +2:00
 4 2026-03-15 12:00:00.0 +5:30

2 rows selected.

Commit complete.
```

### G. Arithmetic keeps the offset

<!-- example: oracle -->
```sql
SELECT TO_CHAR(dep + INTERVAL '90' MINUTE, 'YYYY-MM-DD HH24:MI TZH:TZM') AS plus_90_minutes,
       TO_CHAR(dep + INTERVAL '1' MONTH, 'YYYY-MM-DD HH24:MI TZH:TZM') AS plus_month,
       TO_CHAR(dep + 1, 'YYYY-MM-DD HH24:MI') AS plus_day_as_date,
       dep - TIMESTAMP '2026-03-15 00:00:00 +00:00' AS since_utc_midnight
FROM departures WHERE id = 4;
```

```text
PLUS_90_MINUTES         PLUS_MONTH              PLUS_DAY_AS_DATE SINCE_UTC_MIDNIGHT
----------------------- ----------------------- ---------------- ------------------
2026-03-15 13:30 +05:30 2026-04-15 12:00 +05:30 2026-03-16 12:00 0 6:30:0.0

1 row selected.
```

### H. WITH LOCAL TIME ZONE

The value is an instant. The JDBC client shows it in its own zone (UTC here); `TO_CHAR` shows it in the session's time
zone.

<!-- example: oracle -->
```sql
CREATE TABLE seen (id NUMBER PRIMARY KEY, at_local TIMESTAMP WITH LOCAL TIME ZONE);
INSERT INTO seen VALUES (1, TIMESTAMP '2026-03-15 10:00:00 +02:00');
SELECT at_local FROM seen;
ALTER SESSION SET TIME_ZONE = '-05:00';
SELECT TO_CHAR(at_local, 'YYYY-MM-DD HH24:MI') AS at_local, TO_CHAR(CAST(at_local AS TIMESTAMP WITH TIME ZONE), 'TZH:TZM') AS zone FROM seen;
ALTER SESSION SET TIME_ZONE = '+00:00';
SELECT TO_CHAR(at_local, 'YYYY-MM-DD HH24:MI') AS at_local FROM seen;
```

```text
Table created.

1 row created.

AT_LOCAL
-------------------------
2026-03-15 08:00:00.0 UTC

1 row selected.

Session altered.

AT_LOCAL         ZONE
---------------- ------
2026-03-15 03:00 -05:00

1 row selected.

Session altered.

AT_LOCAL
----------------
2026-03-15 08:00

1 row selected.
```

## See also

[Numeric types](data-types-number.md), [Character types](data-types-character.md),
[ALTER SESSION](alter-session.md), [CREATE TABLE](create-table.md), [Date and time functions](functions-datetime.md)
