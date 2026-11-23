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
INTERVAL 'text' { YEAR TO MONTH | DAY TO SECOND | unit }
```

## Arguments

`DATE`
: A date with a time of day to the second. It is a `TIMESTAMP(0)` underneath.

`TIMESTAMP(p)`
: A date and time with *p* fractional digits (0 to 9, default 6). lexdb keeps microseconds at most.

`WITH TIME ZONE`, `WITH LOCAL TIME ZONE`
: A timestamp with a zone. lexdb stores the instant in UTC: see the differences.

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

## Differences from Oracle

- **`INTERVAL` columns are not supported.** `CREATE TABLE t (a INTERVAL DAY TO SECOND)` is ORA-00900. Intervals work
  as values in expressions (`INTERVAL '2 03:04:05' DAY TO SECOND`, `NUMTODSINTERVAL`, a difference of two
  timestamps).
- **A time zone offset is not kept.** `TIMESTAMP '2026-03-15 13:45:30 +05:30'` is shown as `2026-03-15 08:15:30.0
  +0:00`: the instant is right, the offset is UTC.
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
2026-03-15 08:15:30.0 +0:00 0 12:0:0.0 1-6 2 3:4:5.0

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

## See also

[Numeric types](data-types-number.md), [Character types](data-types-character.md),
[ALTER SESSION](alter-session.md), [CREATE TABLE](create-table.md)
