# Numeric types

`NUMBER` and its ANSI names, `FLOAT`, `BINARY_FLOAT` and `BINARY_DOUBLE`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
NUMBER [ ( precision [, scale ] ) ]
FLOAT [ ( binary_precision ) ]
INTEGER | INT | SMALLINT
DECIMAL ( p [, s ] ) | NUMERIC ( p [, s ] ) | DEC
REAL | DOUBLE PRECISION
BINARY_FLOAT
BINARY_DOUBLE
```

## Arguments

`NUMBER(p, s)`
: A decimal number with up to *p* significant digits (1 to 38) and *s* digits after the point. A value is rounded to
  *s* places; one with more than *p* - *s* digits before the point is ORA-01438. `NUMBER(p)` is an integer of *p*
  digits; `NUMBER(*, s)` has any precision; `NUMBER` alone keeps what it is given (up to 38 digits).

`FLOAT(b)`, `REAL`, `DOUBLE PRECISION`
: `NUMBER` columns without a scale (`USER_TAB_COLUMNS.DATA_TYPE` says `NUMBER`).

`INTEGER`, `INT`, `SMALLINT`
: `NUMBER(38)` with scale 0: a value is rounded to a whole number (2.7 is stored as 3).

`DECIMAL(p, s)`, `NUMERIC(p, s)`
: Synonyms of `NUMBER(p, s)`.

`BINARY_FLOAT`, `BINARY_DOUBLE`
: 4- and 8-byte binary floating point (IEEE 754).

## Remarks

- Arithmetic on `NUMBER` is exact decimal arithmetic: `1/3` gives `.3333333333333333333333333333333333333` (38
  digits).
- A string is converted to a number in arithmetic when it looks like one: `'12' + 1` is 13. A string that does
  not is ORA-01722.
- `TO_NUMBER(string [, format])` converts explicitly: see [conversion functions](README.md#functions).
- Division by zero is ORA-01476.
- A `NUMBER` prints without trailing zeros; a client shows the precision it asked for.

## Differences from Oracle

- A `NUMBER` with a negative scale (`NUMBER(5,-2)`) is ORA-03001.
- A precision above 38 is ORA-01727.
- `FLOAT(b)`, `REAL` and `DOUBLE PRECISION` are plain `NUMBER` columns: there is no binary precision, and
  `USER_TAB_COLUMNS.DATA_PRECISION` is empty for them.
- `TO_BINARY_DOUBLE` and `TO_BINARY_FLOAT` are ORA-00904; use `CAST(x AS BINARY_DOUBLE)`.

## Examples

### A. The dictionary view of the types

<!-- example: oracle -->
```sql
CREATE TABLE n (a NUMBER, b NUMBER(5,2), c NUMBER(3), d NUMBER(*,2), e FLOAT, g INTEGER, h SMALLINT,
                i DECIMAL(6,1), j BINARY_FLOAT, k BINARY_DOUBLE);
SELECT column_name, data_type, data_precision, data_scale FROM user_tab_columns
WHERE table_name = 'N' ORDER BY column_id;
```

```text
Table created.

COLUMN_NAME DATA_TYPE     DATA_PRECISION DATA_SCALE
----------- ------------- -------------- ----------
A           NUMBER
B           NUMBER                     5          2
C           NUMBER                     3          0
D           NUMBER                    38          2
E           NUMBER
G           NUMBER                                0
H           NUMBER                                0
I           NUMBER                     6          1
J           BINARY_FLOAT
K           BINARY_DOUBLE

10 rows selected.
```

### B. Rounding and precision

<!-- example: oracle -->
```sql
INSERT INTO n (a, b, c, g) VALUES (1/3, 123.456, 999, 2.7);
SELECT a, b, c, g FROM n;
INSERT INTO n (b) VALUES (1000);
INSERT INTO n (c) VALUES (1000);
```

```text
1 row created.

                                      A      B   C G
--------------------------------------- ------ --- -
0.3333333333333333333333333333333333333 123.46 999 3

1 row selected.

ERROR:
ORA-01438: value larger than specified precision allowed for this column

ERROR:
ORA-01438: value larger than specified precision allowed for this column
```

### C. Arithmetic

<!-- example: oracle -->
```sql
SELECT 1/3 AS third, 10/4 AS ratio, 7 - 10 AS negative, POWER(2, 40) AS p40, 1e10 AS sci,
       123456789012345678901234567890 AS big, MOD(-7, 3) AS remainder FROM dual;
SELECT 1/0 FROM dual;
```

```text
                                  THIRD RATIO NEGATIVE           P40         SCI                            BIG REMAINDER
--------------------------------------- ----- -------- ------------- ----------- ------------------------------ ---------
0.3333333333333333333333333333333333333   2.5       -3 1099511627776 10000000000 123456789012345678901234567890        -1

1 row selected.

ERROR:
ORA-01476: divisor is equal to zero
```

### D. Strings and numbers

<!-- example: oracle -->
```sql
SELECT TO_NUMBER('12.5') + 1 AS a, '12' + 1 AS b, TO_NUMBER('1e3') AS c, CAST('7' AS NUMBER) AS d FROM dual;
SELECT '12abc' + 1 FROM dual;
INSERT INTO n (a) VALUES ('abc');
```

```text
   A  B    C D
---- -- ---- -
13.5 13 1000 7

1 row selected.

ERROR:
ORA-01722: invalid number

ERROR:
ORA-01722: invalid number
```

### E. Binary floating point

<!-- example: oracle -->
```sql
SELECT CAST(1.5 AS BINARY_FLOAT) AS bf, CAST(0.1 AS BINARY_DOUBLE) AS bd FROM dual;
SELECT TO_BINARY_DOUBLE('1.5') FROM dual;
```

```text
 BF  BD
--- ---
1.5 0.1

1 row selected.

ERROR:
ORA-00904: invalid identifier
```

### F. What lexdb does not take

<!-- example: oracle -->
```sql
CREATE TABLE x4 (a NUMBER(5,-2));
CREATE TABLE x5 (a NUMBER(39));
```

```text
ERROR:
ORA-03001: unimplemented feature: a NUMBER with a negative scale is not supported

ERROR:
ORA-01727: numeric precision specifier is out of range (1 to 38)
```

## See also

[Character types](data-types-character.md), [Date and time types](data-types-datetime.md),
[CREATE TABLE](create-table.md)
