# Date and time types (Transact-SQL)

Dates, times, and the two ways of holding both.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
date
time [ ( p ) ]
smalldatetime
datetime
datetime2 [ ( p ) ]
datetimeoffset [ ( p ) ]
```

## Arguments

`date`
: A calendar date, 0001-01-01 to 9999-12-31.

`time(p)`
: A time of day with *p* fractional digits (0 to 7, default 7).

`datetime`
: A date and time to three fractional digits, in 1753-01-01 to 9999-12-31. Fractions are rounded to .000, .003 or
  .007 (`.126` becomes `.127`). A date before 1753 is error 8115.

`smalldatetime`
: A date and time rounded to the minute (`13:45:30` becomes `13:46:00`).

`datetime2(p)`
: A date and time with *p* fractional digits (0 to 7, default 7).

`datetimeoffset(p)`
: A `datetime2(p)` and the time zone offset it was written with, from `-14:00` to `+14:00` (error 241 beyond):
  `'2026-03-15 10:00:00 +02:00'` is ten o'clock at `+02:00`, and stays so. A string without an offset is at
  `+00:00`.

## Remarks

- Literals are strings: `'2026-03-15'`, `'13:45:30.5'`, `'2026-03-15 13:45:30'` and `'2026-03-15T13:45:30'`
  convert to any of the types. Write a date in this ISO order; other layouts are error 241 (see below).
- A `date` has no time and a `time` no date. Casting a `datetime` to `date` drops the time; casting a `date` to
  `datetime2` gives midnight.
- Comparing a `date` with a `datetime` compares the date with the datetime's midnight (`'2026-03-15'` equals
  `'2026-03-15 00:00'`).
- `DATEADD`, `DATEDIFF`, `DATEPART`, `DATENAME`, `EOMONTH`, `DATEFROMPARTS` and `DATETRUNC` are on the
  [date and time functions](functions-datetime.md) page.
- An invalid date (`'2026-02-30'`) is error 517; text that is not a date at all is error 241. A value that is not
  a valid datetime in range is error 8115.
- Results print with the fractional digits of their type: `datetime2` and `time` with seven (`13:45:30.1234570`),
  `datetime` with one to three, `date` with none.
- **datetimeoffset.** Two values are compared by instant: `10:00 +02:00` equals `08:00 +00:00`. `ORDER BY`, `GROUP
  BY`, `DISTINCT`, joins, `IN` and indexes go by instant too (a unique index takes only one of the two); a group shows
  the offset of its first row. Each value keeps its own offset: `DATEPART(tzoffset, ...)` gives it in minutes, and
  `SWITCHOFFSET` moves a value to another (example D). `DATEADD` keeps the offset, and `DATEDIFF` counts between the
  UTC instants (example K). `CAST` to `datetime2`, `date` or `time` gives the local time; a `datetime2` or `date` cast
  to `datetimeoffset` is at `+00:00` (use `TODATETIMEOFFSET` to give it an offset). Clients get the offset too (TDS
  type 0x2B): `getObject(i, OffsetDateTime.class)` in JDBC, `DateTimeOffset` in .NET.

## Differences from SQL Server

- **Time resolution is a microsecond.** The seventh fractional digit is lost: `'13:45:30.1234567'` is stored as
  `13:45:30.1234570`.
- **A `datetimeoffset` as a string has seven fractional digits whatever its scale**: `CAST(x AS varchar(40))` of a
  `datetimeoffset(0)` is `2026-03-15 10:00:00.0000000 +02:00` (SQL Server: `2026-03-15 10:00:00 +02:00`). The value
  `SWITCHOFFSET`, `TODATETIMEOFFSET`, `AT TIME ZONE`, `MIN` and `MAX` give is a `datetimeoffset(7)` whatever the
  scale of their argument (SQL Server keeps it), so clients show it with seven digits.
- `MIN` and `MAX` of equal instants show the offset of the last row (SQL Server: of the first).
- A `VALUES` list keeps the instant, not the offset: `(VALUES (CAST('2026-03-15 10:00 +02:00' AS datetimeoffset)))`
  gives `2026-03-15 08:00:00 +00:00`.
- `datetimeoffset - datetimeoffset` is an interval (`01:00:00`; SQL Server: error 8117), and a variable plus a number
  (`@d + 1`) is error 195 (SQL Server: 206).
- A `datetimeoffset` loaded by bulk copy keeps its instant, not its offset (see [bulk loading](../../bulk-load.md)).
- **Only ISO layouts are read.** `'20260315'`, `'March 15, 2026'` and `'03/15/2026'` are error 241, and `SET
  DATEFORMAT` changes nothing. `'2026-03-15T13:45:30'` and `'2026-3-5'` are read.
- **Date arithmetic.** `datetime + 1`, `datetime - 1`, `1 + datetime` and `datetime - datetime` work as in SQL Server,
  also with `smalldatetime`: a number is days, and the difference of two datetimes is a datetime counted from
  1900-01-01 (example H). `date`, `datetime2`, `datetimeoffset` and `time` with a number are error 206, as in SQL
  Server; they take `DATEADD`. `date - date` is accepted and gives a number of days (SQL Server: 8117), and
  `GETDATE() - GETDATE()` is an interval (`00:00:00`), not a datetime.
- `time` from a string with a date (`CAST('2026-03-15 13:45:30' AS time)`) is error 241; SQL Server takes the time
  part.
- `datetime2(8)` is error 1002.
- `ISDATE` does not exist (error 195).
- A date out of range gives error 517 where SQL Server gives 242 or 241.

## Examples

### A. The types and their output

<!-- example: tsql -->
```sql
SELECT CAST('2026-03-15' AS date) AS d, CAST('13:45:30.1234567' AS time) AS t,
       CAST('2026-03-15 13:45:30.123' AS datetime) AS dt, CAST('2026-03-15 13:45:30' AS smalldatetime) AS sdt,
       CAST('2026-03-15 13:45:30.1234567' AS datetime2) AS dt2;
```

```text
d          t                dt                      sdt                   dt2
---------- ---------------- ----------------------- --------------------- ---------------------------
2026-03-15 13:45:30.1234570 2026-03-15 13:45:30.123 2026-03-15 13:46:00.0 2026-03-15 13:45:30.1234570

(1 row affected)
```

### B. Precision and rounding

<!-- example: tsql -->
```sql
SELECT CAST('2026-03-15 13:45:30.1234567' AS datetime2(3)) AS p3,
       CAST('2026-03-15 13:45:30.1234567' AS datetime2(0)) AS p0,
       CAST('13:45:30.1234567' AS time(2)) AS t2,
       CAST('2026-03-15 13:45:30.126' AS datetime) AS dt,
       CAST('2026-03-15 13:45:31' AS smalldatetime) AS sdt;
```

```text
p3                      p0                  t2          dt                      sdt
----------------------- ------------------- ----------- ----------------------- ---------------------
2026-03-15 13:45:30.123 2026-03-15 13:45:30 13:45:30.12 2026-03-15 13:45:30.127 2026-03-15 13:46:00.0

(1 row affected)
```

### C. Columns

<!-- example: tsql -->
```sql
CREATE TABLE ev (id int, d date, t time(3), dt datetime, dt2 datetime2(2));
INSERT INTO ev VALUES (1, '2026-03-15', '09:30:00.5', '2026-03-15 09:30:00', '2026-03-15 09:30:00.126');
SELECT * FROM ev;
GO
INSERT INTO ev (d) VALUES ('2026-02-30');
GO
INSERT INTO ev (d) VALUES ('hello');
```

```text
(1 row affected)

id d          t            dt                    dt2
-- ---------- ------------ --------------------- ----------------------
1  2026-03-15 09:30:00.500 2026-03-15 09:30:00.0 2026-03-15 09:30:00.13

(1 row affected)

Msg 517, Level 16, State 1, Line 1
date/time field value out of range: "2026-02-30"
Msg 241, Level 16, State 1, Line 1
Conversion failed when converting date and/or time from character string.
```

### D. datetimeoffset keeps its offset

Four departures at four offsets; three of them are the same instant, 08:00 UTC. They sort, compare and count by
instant, and each keeps its own offset.

<!-- example: tsql -->
```sql
CREATE TABLE departures (id int PRIMARY KEY, city varchar(10), dep datetimeoffset(0));
INSERT INTO departures VALUES (1, 'Athens', '2026-03-15 10:00:00 +02:00'), (2, 'London', '2026-03-15 08:00:00 +00:00'),
  (3, 'New York', '2026-03-15 03:00:00 -05:00'), (4, 'Mumbai', '2026-03-15 12:00:00 +05:30');
SELECT id, city, dep, DATEPART(tzoffset, dep) AS offset_minutes, CAST(SWITCHOFFSET(dep, '+00:00') AS datetime2(0)) AS utc
FROM departures ORDER BY dep, id;
SELECT city FROM departures WHERE dep = '2026-03-15 11:00:00 +03:00' ORDER BY id;
SELECT COUNT(DISTINCT dep) AS instants, COUNT(*) AS n_rows FROM departures;
GO
SELECT CAST('2026-03-15 10:00:00 +14:01' AS datetimeoffset);
```

```text
(4 rows affected)

id city     dep                        offset_minutes utc
-- -------- -------------------------- -------------- -------------------
4  Mumbai   2026-03-15 12:00:00 +05:30 330            2026-03-15 06:30:00
1  Athens   2026-03-15 10:00:00 +02:00 120            2026-03-15 08:00:00
2  London   2026-03-15 08:00:00 +00:00 0              2026-03-15 08:00:00
3  New York 2026-03-15 03:00:00 -05:00 -300           2026-03-15 08:00:00

(4 rows affected)

city
--------
Athens
London
New York

(3 rows affected)

instants n_rows
-------- ------
2        4

(1 row affected)

Msg 241, Level 16, State 1, Line 1
Conversion failed when converting date and/or time from character string.
```

### E. Conversions between the types

<!-- example: tsql -->
```sql
DECLARE @d date = '2026-03-15', @t time = '10:30:00', @dt datetime2 = '2026-03-15 10:30:45';
SELECT CAST(@d AS datetime2) AS date_to_datetime2, CAST(@dt AS date) AS datetime2_to_date,
       CAST(@dt AS time(0)) AS datetime2_to_time, CAST(@t AS time(0)) AS t;
```

```text
date_to_datetime2           datetime2_to_date datetime2_to_time t
--------------------------- ----------------- ----------------- --------
2026-03-15 00:00:00.0000000 2026-03-15        10:30:45          10:30:00

(1 row affected)
```

### F. Range

<!-- example: tsql -->
```sql
SELECT CAST('0001-01-01' AS date) AS min_date, CAST('9999-12-31' AS date) AS max_date,
       CAST('1753-01-01' AS datetime) AS min_datetime;
GO
SELECT CAST('1700-01-01' AS datetime);
GO
SELECT CAST('2026-03-15 25:00' AS datetime);
```

```text
min_date   max_date   min_datetime
---------- ---------- ---------------------
0001-01-01 9999-12-31 1753-01-01 00:00:00.0

(1 row affected)

Msg 8115, Level 16, State 1, Line 1
The conversion of a datetime2 data type to a datetime data type resulted in an out-of-range value.
Msg 517, Level 16, State 1, Line 1
date/time field value out of range: "2026-03-15 25:00"
```

### G. Comparing

<!-- example: tsql -->
```sql
SELECT CASE WHEN CAST('2026-03-15' AS date) < CAST('2026-03-16' AS date) THEN 'earlier' ELSE 'later' END AS cmp,
       CASE WHEN CAST('2026-03-15' AS date) = CAST('2026-03-15 00:00' AS datetime) THEN 'equal' ELSE 'different' END AS date_datetime;
```

```text
cmp     date_datetime
------- -------------
earlier equal

(1 row affected)
```

### H. Date arithmetic

<!-- example: tsql -->
```sql
SELECT DATEADD(day, 1, CAST('2026-02-28' AS date)) AS next_day,
       DATEADD(month, 1, CAST('2026-01-31' AS date)) AS next_month,
       DATEDIFF(day, '2026-03-15', '2026-03-20') AS days_between;
GO
SELECT CAST('2026-03-15' AS datetime) + 1 AS plus_one, CAST('2026-03-15 12:00' AS datetime) - 1 AS minus_one,
       CAST('2026-03-15' AS datetime) + 0.5 AS plus_half;
GO
SELECT CAST('2026-03-16 10:00' AS datetime) - CAST('2026-03-15' AS datetime) AS difference;
GO
SELECT CAST('2026-03-15' AS date) + 1 AS date_plus_one;
GO
SELECT CAST('2026-03-15 10:00' AS datetime2) + 1 AS datetime2_plus_one;
```

```text
next_day   next_month days_between
---------- ---------- ------------
2026-03-01 2026-02-28 5

(1 row affected)

plus_one              minus_one             plus_half
--------------------- --------------------- ---------------------
2026-03-16 00:00:00.0 2026-03-14 12:00:00.0 2026-03-15 12:00:00.0

(1 row affected)

difference
---------------------
1900-01-02 10:00:00.0

(1 row affected)

Msg 206, Level 16, State 1, Line 1
Operand type clash: date is incompatible with int
Msg 206, Level 16, State 1, Line 1
Operand type clash: datetime2 is incompatible with int
```

### I. Layouts that are not read

<!-- example: tsql -->
```sql
SELECT CAST('2026-03-15T13:45:30' AS datetime) AS iso_t, CAST('2026-3-5' AS date) AS short_form;
GO
SELECT CAST('20260315' AS date) AS compact;
GO
SELECT CAST('March 15, 2026' AS date) AS words;
GO
SELECT CAST('03/15/2026' AS date) AS slashes;
```

```text
iso_t                 short_form
--------------------- ----------
2026-03-15 13:45:30.0 2026-03-05

(1 row affected)

Msg 241, Level 16, State 1, Line 1
Conversion failed when converting date and/or time from character string.
Msg 241, Level 16, State 1, Line 1
Conversion failed when converting date and/or time from character string.
Msg 241, Level 16, State 1, Line 1
Conversion failed when converting date and/or time from character string.
```

### J. Other refusals

<!-- example: tsql -->
```sql
SELECT CAST('2026-03-15 13:45:30' AS time);
GO
SELECT CAST('2026-03-15' AS datetime2(8));
GO
SELECT ISDATE('2026-03-15');
```

```text
Msg 241, Level 16, State 1, Line 1
Conversion failed when converting date and/or time from character string.
Msg 1002, Level 16, State 1, Line 1
Line 1: Specified scale 8 is invalid.
Msg 195, Level 15, State 1, Line 1
'isdate' is not a recognized built-in function name.
```

### K. Arithmetic keeps the offset

<!-- example: tsql -->
```sql
SELECT DATEADD(minute, 90, dep) AS plus_90_minutes, DATEADD(month, 1, dep) AS plus_month,
       DATEDIFF(minute, '2026-03-15 00:00 +00:00', dep) AS minutes_since_utc_midnight,
       CAST(dep AS datetime2(0)) AS local_time, CAST(dep AS date) AS local_date
FROM departures WHERE id = 4;
```

```text
plus_90_minutes            plus_month                 minutes_since_utc_midnight local_time          local_date
-------------------------- -------------------------- -------------------------- ------------------- ----------
2026-03-15 13:30:00 +05:30 2026-04-15 12:00:00 +05:30 390                        2026-03-15 12:00:00 2026-03-15

(1 row affected)
```

## See also

[Date and time functions](functions-datetime.md), [CAST and CONVERT](functions-conversion.md),
[Operators](operators.md)
