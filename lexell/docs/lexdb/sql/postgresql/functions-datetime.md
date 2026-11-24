# Date and time functions

The current date and time, fields of a date, truncation and binning, ages, building values from parts, and time
zones.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
now ( ) → timestamptz
current_timestamp [ ( p ) ] → timestamptz
transaction_timestamp ( ) → timestamptz
statement_timestamp ( ) → timestamptz
clock_timestamp ( ) → timestamptz
current_date → date
current_time [ ( p ) ] → time
localtime [ ( p ) ] → time
localtimestamp [ ( p ) ] → timestamp
EXTRACT ( field FROM source ) → numeric
date_part ( 'field', source ) → double precision
date_trunc ( 'unit', source [, time_zone ] ) → same type
date_bin ( stride, source, origin ) → same type
age ( timestamp, timestamp ) → interval
age ( timestamp ) → interval
make_date ( year, month, day ) → date
make_timestamp ( year, month, day, hour, min, sec ) → timestamp
make_timestamptz ( year, month, day, hour, min, sec [, time_zone ] ) → timestamptz
make_interval ( [ years [, months [, weeks [, days [, hours [, mins [, secs ] ] ] ] ] ] ] ) → interval
to_timestamp ( seconds ) → timestamptz
isfinite ( date | timestamp | interval ) → boolean
date_add ( timestamptz, interval [, time_zone ] ) → timestamptz
date_subtract ( timestamptz, interval [, time_zone ] ) → timestamptz
source AT TIME ZONE zone → timestamp | timestamptz
source AT LOCAL → timestamp | timestamptz
timezone ( zone, source ) → timestamp | timestamptz
```

## Functions

`now`, `current_timestamp`, `transaction_timestamp`
: The time the transaction started. Every call in one transaction gives the same value.

`statement_timestamp`
: The time the statement started.

`clock_timestamp`
: The time now; it changes within a statement.

`current_date`, `current_time`, `localtime`, `localtimestamp`
: The transaction's start as a date, a time, or a timestamp without time zone, in the session's time zone. *p*
  rounds to that many digits after the seconds' point.

`EXTRACT`, `date_part`
: A field of a date, time, timestamp or interval: `century`, `decade`, `year`, `quarter`, `month`, `week` (ISO
  week), `day`, `dow` (0 = Sunday), `isodow` (7 = Sunday), `doy`, `isoyear`, `hour`, `minute`, `second` (with its
  fraction), `milliseconds`, `microseconds`, `epoch` (seconds since 1970-01-01 00:00 UTC), `julian`, `timezone`.
  `EXTRACT` gives `numeric`, `date_part` `double precision`.

`date_trunc`
: The value cut down to the start of its `microseconds`, `milliseconds`, `second`, `minute`, `hour`, `day`,
  `week` (Monday), `month`, `quarter`, `year`, `decade`, `century` or `millennium`. A `timestamptz` is cut in the
  session's time zone, or in *time_zone*.

`date_bin`
: The start of the *stride*-long bin, counted from *origin*, that *source* falls in (PostgreSQL 14).

`age`
: The difference between two timestamps in years, months and days; with one argument, from midnight of today.

`make_date`, `make_timestamp`, `make_timestamptz`
: A value from its parts; *sec* may have a fraction. `make_timestamptz` reads the parts in *time_zone*, or in the
  session's.

`make_interval`
: An interval from its parts, by place or by name (`make_interval(days => 10)`).

`to_timestamp`
: The `timestamptz` that many seconds after 1970-01-01 00:00 UTC. With two arguments it reads text by a format:
  see [formatting functions](functions-formatting.md).

`isfinite`
: Whether the value is not `infinity` or `-infinity`.

`date_add`, `date_subtract`
: The `timestamptz` plus or minus the interval, its days and months counted in *time_zone* or the session's time
  zone (PostgreSQL 16).

`AT TIME ZONE`, `timezone`
: A `timestamp` read as a time in *zone* gives the `timestamptz`; a `timestamptz` gives the wall-clock
  `timestamp` in *zone*. `AT LOCAL` uses the session's time zone (PostgreSQL 17).

## Remarks

- `now()` and its kin are the same through the transaction, so a transaction's rows carry one time.
- The session's time zone is UTC unless set with `SET TIME ZONE`.
- A zone may be a name (`Europe/Paris`), an abbreviation (`CET`) or an offset (`+02`, as in ISO 8601, east of
  UTC).

## Differences from PostgreSQL

- `justify_days`, `justify_hours`, `justify_interval`, `make_time`, `pg_sleep` and the `OVERLAPS` operator do not
  exist.

## Examples

<!--setup: postgresql
CREATE TABLE visit (id int, at timestamp);
INSERT INTO visit VALUES (1, '2026-03-01 09:15:30'), (2, '2026-03-01 10:40:00'), (3, '2026-03-02 23:59:59.5'),
  (4, '2026-04-15 12:00:00');
-->

The examples use this table:

```sql
CREATE TABLE visit (id int, at timestamp);
INSERT INTO visit VALUES (1, '2026-03-01 09:15:30'), (2, '2026-03-01 10:40:00'), (3, '2026-03-02 23:59:59.5'),
  (4, '2026-04-15 12:00:00');
```

### A. The current time

The values change, so the example compares them.

<!-- example: postgresql -->
```sql
BEGIN;
SELECT now() = current_timestamp AS same, now() = transaction_timestamp() AS same2,
       current_date = now()::date AS today, clock_timestamp() >= now() AS later,
       statement_timestamp() >= now() AS stmt, pg_typeof(localtimestamp) AS lts, pg_typeof(localtime) AS lt;
COMMIT;
```

```text
BEGIN
 same | same2 | today | later | stmt |             lts             |           lt
------+-------+-------+-------+------+-----------------------------+------------------------
 t    | t     | t     | t     | t    | timestamp without time zone | time without time zone
(1 row)

COMMIT
```

### B. EXTRACT and date_part

<!-- example: postgresql -->
```sql
SELECT EXTRACT(year FROM at) AS year, EXTRACT(month FROM at) AS month, EXTRACT(dow FROM at) AS dow,
       EXTRACT(doy FROM at) AS doy, EXTRACT(week FROM at) AS week, EXTRACT(second FROM at) AS second,
       date_part('hour', at) AS hour
FROM visit ORDER BY id;
```

```text
 year | month | dow | doy | week |  second   | hour
------+-------+-----+-----+------+-----------+------
 2026 |     3 |   0 |  60 |    9 | 30.000000 |    9
 2026 |     3 |   0 |  60 |    9 |  0.000000 |   10
 2026 |     3 |   1 |  61 |   10 | 59.500000 |   23
 2026 |     4 |   3 | 105 |   16 |  0.000000 |   12
(4 rows)
```

### C. Epoch and interval fields

<!-- example: postgresql -->
```sql
SELECT EXTRACT(epoch FROM TIMESTAMPTZ '2026-03-01 00:00+00') AS epoch, EXTRACT(quarter FROM DATE '2026-08-01') AS q,
       EXTRACT(isodow FROM DATE '2026-03-01') AS isodow, EXTRACT(epoch FROM INTERVAL '1 day 1 hour') AS secs,
       EXTRACT(day FROM INTERVAL '40 days') AS days;
```

```text
       epoch       | q | isodow |     secs     | days
-------------------+---+--------+--------------+------
 1772323200.000000 | 3 |      7 | 90000.000000 |   40
(1 row)
```

### D. date_trunc

<!-- example: postgresql -->
```sql
SELECT date_trunc('hour', at) AS hour, date_trunc('day', at) AS day, date_trunc('week', at) AS week,
       date_trunc('month', at) AS month FROM visit WHERE id = 3;
SELECT date_trunc('month', at) AS month, count(*) FROM visit GROUP BY 1 ORDER BY 1;
```

```text
        hour         |         day         |        week         |        month
---------------------+---------------------+---------------------+---------------------
 2026-03-02 23:00:00 | 2026-03-02 00:00:00 | 2026-03-02 00:00:00 | 2026-03-01 00:00:00
(1 row)

        month        | count
---------------------+-------
 2026-03-01 00:00:00 |     3
 2026-04-01 00:00:00 |     1
(2 rows)
```

### E. date_trunc of a timestamptz in a time zone

<!-- example: postgresql -->
```sql
SELECT date_trunc('day', TIMESTAMPTZ '2026-03-01 23:30+00') AS utc,
       date_trunc('day', TIMESTAMPTZ '2026-03-01 23:30+00', 'Asia/Tokyo') AS tokyo;
```

```text
          utc           |         tokyo
------------------------+------------------------
 2026-03-01 00:00:00+00 | 2026-03-01 15:00:00+00
(1 row)
```

### F. date_bin

<!-- example: postgresql -->
```sql
SELECT id, date_bin(INTERVAL '15 minutes', at, TIMESTAMP '2026-01-01') AS quarter_hour FROM visit ORDER BY id;
```

```text
 id |    quarter_hour
----+---------------------
  1 | 2026-03-01 09:15:00
  2 | 2026-03-01 10:30:00
  3 | 2026-03-02 23:45:00
  4 | 2026-04-15 12:00:00
(4 rows)
```

### G. age

<!-- example: postgresql -->
```sql
SELECT age(TIMESTAMP '2026-03-01', TIMESTAMP '1990-07-15') AS age, age(TIMESTAMP '2026-03-31', TIMESTAMP '2026-02-28')
       AS short, age(current_date::timestamp) AS since_midnight;
```

```text
           age           |    short     | since_midnight
-------------------------+--------------+----------------
 35 years 7 mons 17 days | 1 mon 3 days | 00:00:00
(1 row)
```

### H. Building values from parts

<!-- example: postgresql -->
```sql
SELECT make_date(2026, 3, 1) AS d, make_timestamp(2026, 3, 1, 10, 30, 15.5) AS ts,
       make_timestamptz(2026, 3, 1, 10, 30, 0, 'Europe/Paris') AS tstz;
SELECT make_interval(1, 2) AS a, make_interval(days => 10, hours => 3) AS b, to_timestamp(1772323200) AS c;
```

```text
     d      |          ts           |          tstz
------------+-----------------------+------------------------
 2026-03-01 | 2026-03-01 10:30:15.5 | 2026-03-01 09:30:00+00
(1 row)

       a       |        b         |           c
---------------+------------------+------------------------
 1 year 2 mons | 10 days 03:00:00 | 2026-03-01 00:00:00+00
(1 row)
```

### I. isfinite

<!-- example: postgresql -->
```sql
SELECT isfinite(DATE '2026-03-01') AS d, isfinite('infinity'::timestamp) AS ts, isfinite(INTERVAL '1 day') AS i;
```

```text
 d | ts | i
---+----+---
 t | f  | t
(1 row)
```

### J. date_add and date_subtract

Across a change of clocks, a day in a time zone is not 24 hours.

<!-- example: postgresql -->
```sql
SELECT date_add(TIMESTAMPTZ '2026-03-28 12:00+00', INTERVAL '1 day', 'Europe/Paris') AS paris,
       date_add(TIMESTAMPTZ '2026-03-28 12:00+00', INTERVAL '1 day') AS utc,
       date_subtract(TIMESTAMPTZ '2026-03-01 00:00+00', INTERVAL '1 month') AS month_back;
```

```text
         paris          |          utc           |       month_back
------------------------+------------------------+------------------------
 2026-03-29 11:00:00+00 | 2026-03-29 12:00:00+00 | 2026-02-01 00:00:00+00
(1 row)
```

### K. AT TIME ZONE

<!-- example: postgresql -->
```sql
SELECT TIMESTAMP '2026-03-01 12:00' AT TIME ZONE 'America/New_York' AS ny_noon_as_utc,
       TIMESTAMPTZ '2026-03-01 12:00+00' AT TIME ZONE 'Asia/Tokyo' AS tokyo_wall_clock,
       timezone('Europe/Paris', TIMESTAMPTZ '2026-03-01 12:00+00') AS paris_wall_clock,
       TIMESTAMPTZ '2026-03-01 12:00+00' AT LOCAL AS local;
```

```text
     ny_noon_as_utc     |  tokyo_wall_clock   |  paris_wall_clock   |        local
------------------------+---------------------+---------------------+---------------------
 2026-03-01 17:00:00+00 | 2026-03-01 21:00:00 | 2026-03-01 13:00:00 | 2026-03-01 12:00:00
(1 row)
```

### L. Errors

<!-- example: postgresql -->
```sql
SELECT date_trunc('fortnight', TIMESTAMP '2026-03-01');
SELECT make_date(2026, 2, 30);
SELECT justify_hours(INTERVAL '30 hours');
```

```text
ERROR:  unit "fortnight" not recognized for type timestamp
ERROR:  date field value out of range: 2026-02-30
ERROR:  function justify_hours with 1 arguments does not exist
```

## See also

[Date and time types](data-types-datetime.md) · [Formatting functions](functions-formatting.md) ·
[SET](set.md) (`TIME ZONE`) · [Set-returning functions](functions-srf.md) (`generate_series` of timestamps)
