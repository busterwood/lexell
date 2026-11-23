# ALTER SESSION

Changes a setting of the current session: the schema, the time zone, date formats and other parameters.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
ALTER SESSION SET parameter = value [ parameter = value ]...
```

## Arguments

`CURRENT_SCHEMA`
: The schema that unqualified names resolve in: `ALTER SESSION SET CURRENT_SCHEMA = hr` makes `SELECT * FROM t` read
  `hr.t`. A schema that is not a user is ORA-01435.

`TIME_ZONE`
: A fixed offset (`'+05:30'`) or a region name (`'Europe/Paris'`); `SESSIONTIMEZONE` returns it. An unknown region is
  ORA-01882.

`NLS_DATE_FORMAT`, `NLS_TIMESTAMP_FORMAT`, `NLS_TIMESTAMP_TZ_FORMAT`
: The default format of `TO_CHAR`, `TO_DATE` and the other conversions of dates. A format that is not one is
  ORA-01821.

`GROUP_BY_POSITION_ENABLED`
: `TRUE` lets `GROUP BY 1` name the first column of the select list (23ai).

Other `NLS_*` parameters, `OPTIMIZER_*`, `SQL_TRACE`, `ISOLATION_LEVEL`, `CURSOR_SHARING` and many more
: Accepted and ignored.

## Remarks

- The setting lasts until the session ends or it is set again.
- An unknown parameter name is ORA-02248.
- `ALTER SESSION ENABLE PARALLEL DML` and `CLOSE DATABASE LINK` are accepted and do nothing.

## Differences from Oracle

- `SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA')` still says the login user after `SET CURRENT_SCHEMA`
  (`SYS_CONTEXT('USERENV', 'NLS_DATE_FORMAT')` likewise keeps the default `DD-MON-RR`), although the setting works.
- `NLS_NUMERIC_CHARACTERS` and `NLS_LANGUAGE` are accepted but do not change the output of `TO_CHAR`: the group and
  decimal characters, the day and month names stay those of `AMERICAN`.

## Examples

### A. The current schema

<!-- example: oracle -->
```sql
CREATE USER hr IDENTIFIED BY pw;
CREATE TABLE hr.t (a NUMBER);
INSERT INTO hr.t VALUES (1);
ALTER SESSION SET CURRENT_SCHEMA = hr;
SELECT * FROM t;
SELECT SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema FROM dual;
ALTER SESSION SET CURRENT_SCHEMA = SA;
ALTER SESSION SET CURRENT_SCHEMA = nobody;
```

```text
User created.

Table created.

1 row created.

Session altered.

A
-
1

1 row selected.

CURRENT_SCHEMA
--------------
SA

1 row selected.

Session altered.

ERROR:
ORA-01435: user does not exist
```

### B. A date format

<!-- example: oracle -->
```sql
ALTER SESSION SET NLS_DATE_FORMAT = 'DD/MM/YYYY';
SELECT TO_CHAR(DATE '2026-03-15') AS d FROM dual;
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
SELECT TO_CHAR(DATE '2026-03-15') AS d FROM dual;
ALTER SESSION SET NLS_DATE_FORMAT = 'NOT A FORMAT';
```

```text
Session altered.

D
----------
15/03/2026

1 row selected.

Session altered.

D
----------
2026-03-15

1 row selected.

ERROR:
ORA-01821: date format not recognized
```

### C. The time zone

<!-- example: oracle -->
```sql
ALTER SESSION SET TIME_ZONE = '+05:30';
SELECT SESSIONTIMEZONE FROM dual;
ALTER SESSION SET TIME_ZONE = 'Europe/Paris';
SELECT SESSIONTIMEZONE FROM dual;
ALTER SESSION SET TIME_ZONE = 'Nowhere/Land';
```

```text
Session altered.

SESSIONTIMEZONE
---------------
+05:30

1 row selected.

Session altered.

SESSIONTIMEZONE
---------------
Europe/Paris

1 row selected.

ERROR:
ORA-01882: time zone region not found
```

### D. GROUP BY a position

<!-- example: oracle -->
```sql
CREATE TABLE g (a NUMBER, b NUMBER);
INSERT INTO g VALUES (1, 2);
INSERT INTO g VALUES (1, 3);
ALTER SESSION SET GROUP_BY_POSITION_ENABLED = TRUE;
SELECT a, COUNT(*) AS n FROM g GROUP BY 1;
```

```text
Table created.

1 row created.

1 row created.

Session altered.

A N
- -
1 2

1 row selected.
```

### E. Parameters that are accepted, ignored or unknown

<!-- example: oracle -->
```sql
ALTER SESSION SET OPTIMIZER_MODE = ALL_ROWS;
ALTER SESSION SET SQL_TRACE = TRUE;
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = ',.';
SELECT TO_CHAR(1234.5, '9G999D99') AS n FROM dual;
ALTER SESSION SET NLS_NUMERIC_CHARACTERS = '.,';
ALTER SESSION SET BOGUS_PARAM = 1;
```

```text
Session altered.

Session altered.

Session altered.

N
---------
 1,234.50

1 row selected.

Session altered.

ERROR:
ORA-02248: invalid option for ALTER SESSION
```

## See also

[CREATE USER](create-user.md), [Conversion functions](README.md#functions)
