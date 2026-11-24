# CREATE SEQUENCE

Creates a sequence of numbers, read with `NEXTVAL` and `CURRVAL`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE SEQUENCE [ schema. ] sequence
    [ START WITH n ] [ INCREMENT BY n ]
    [ MAXVALUE n | NOMAXVALUE ] [ MINVALUE n | NOMINVALUE ]
    [ CYCLE | NOCYCLE ] [ CACHE n | NOCACHE ] [ ORDER | NOORDER ]
    [ KEEP | NOKEEP ]
```

```
sequence.NEXTVAL
sequence.CURRVAL
```

## Arguments

`START WITH`
: The first value; 1 by default.

`INCREMENT BY`
: The step, positive or negative; 1 by default.

`MAXVALUE`, `MINVALUE`
: The limits. Without them, an ascending sequence runs from 1 to 9999999999999999999999999999.

`CYCLE`, `NOCYCLE`
: With `CYCLE` the sequence goes back to `MINVALUE` (ascending) after `MAXVALUE`. With `NOCYCLE` (the default) it
  stops with an error.

`CACHE`, `NOCACHE`, `ORDER`, `NOORDER`, `KEEP`, `NOKEEP`
: Accepted and ignored: lexdb hands out values in order from one counter.

## Remarks

- `seq.NEXTVAL` is the next value, `seq.CURRVAL` the value `NEXTVAL` last gave in this session. `CURRVAL` before the
  first `NEXTVAL` in the session is an error.
- Two `NEXTVAL`s in one statement give two values.
- `USER_SEQUENCES` lists sequences with their limits.
- Sequences give keys: `INSERT INTO t (id) VALUES (seq.NEXTVAL)`, or use an identity column
  ([CREATE TABLE](create-table.md)).

## Differences from Oracle

- A sequence past its `MAXVALUE` is ORA-20000 (`nextval: reached maximum value of sequence`); Oracle gives ORA-08004.
- `CURRVAL` before the first `NEXTVAL` is ORA-20000 (`currval of sequence ... is not yet defined in this session`);
  Oracle gives ORA-08002.
- `USER_SEQUENCES.CACHE_SIZE` is 0 and `LAST_NUMBER` is the start value, whatever the options said.
- `SESSION` and `SCALE` sequences are ORA-00900.
- `CURRVAL` and `NEXTVAL` are allowed in a subquery (Oracle: ORA-02287).

## Examples

### A. The next value, and the current one

<!-- example: oracle -->
```sql
CREATE SEQUENCE s1;
SELECT s1.NEXTVAL, s1.NEXTVAL FROM dual;
SELECT s1.CURRVAL FROM dual;
```

```text
Sequence created.

NEXTVAL NEXTVAL
------- -------
      1       2

1 row selected.

CURRVAL
-------
      2

1 row selected.
```

### B. Options: a cycle

<!-- example: oracle -->
```sql
CREATE SEQUENCE s2 START WITH 100 INCREMENT BY 10 MINVALUE 0 MAXVALUE 130 NOCACHE CYCLE;
SELECT s2.NEXTVAL FROM dual;
SELECT s2.NEXTVAL FROM dual;
SELECT s2.NEXTVAL FROM dual;
SELECT s2.NEXTVAL FROM dual;
SELECT s2.NEXTVAL FROM dual;
```

```text
Sequence created.

NEXTVAL
-------
    100

1 row selected.

NEXTVAL
-------
    110

1 row selected.

NEXTVAL
-------
    120

1 row selected.

NEXTVAL
-------
    130

1 row selected.

NEXTVAL
-------
      0

1 row selected.
```

### C. A sequence that stops

<!-- example: oracle -->
```sql
CREATE SEQUENCE s3 MAXVALUE 2 NOCYCLE;
SELECT s3.NEXTVAL FROM dual;
SELECT s3.NEXTVAL FROM dual;
SELECT s3.NEXTVAL FROM dual;
```

```text
Sequence created.

NEXTVAL
-------
      1

1 row selected.

NEXTVAL
-------
      2

1 row selected.

ERROR:
ORA-20000: nextval: reached maximum value of sequence "s3" (2)
```

### D. A descending sequence

<!-- example: oracle -->
```sql
CREATE SEQUENCE s4 INCREMENT BY -1 START WITH 5 MINVALUE 1 MAXVALUE 5;
SELECT s4.NEXTVAL FROM dual;
SELECT s4.NEXTVAL FROM dual;
```

```text
Sequence created.

NEXTVAL
-------
      5

1 row selected.

NEXTVAL
-------
      4

1 row selected.
```

### E. The dictionary

<!-- example: oracle -->
```sql
SELECT sequence_name, min_value, max_value, increment_by, cycle_flag, order_flag, cache_size, last_number
FROM user_sequences ORDER BY sequence_name;
```

```text
SEQUENCE_NAME MIN_VALUE                    MAX_VALUE INCREMENT_BY CYCLE_FLAG ORDER_FLAG CACHE_SIZE LAST_NUMBER
------------- --------- ---------------------------- ------------ ---------- ---------- ---------- -----------
S1                    1 9999999999999999999999999999            1 N          N                   0           1
S2                    0                          130           10 Y          N                   0         100
S3                    1                            2            1 N          N                   0           1
S4                    1                            5           -1 N          N                   0           5

4 rows selected.
```

### F. Keys from a sequence

<!-- example: oracle -->
```sql
CREATE SEQUENCE item_seq START WITH 10;
CREATE TABLE item (id NUMBER PRIMARY KEY, label VARCHAR2(10));
INSERT INTO item VALUES (item_seq.NEXTVAL, 'a');
INSERT INTO item VALUES (item_seq.NEXTVAL, 'b');
SELECT * FROM item ORDER BY id;
```

```text
Sequence created.

Table created.

1 row created.

1 row created.

ID LABEL
-- -----
10 a
11 b

2 rows selected.
```

### G. Errors

<!-- example: oracle -->
```sql
SELECT s_nothere.NEXTVAL FROM dual;
CREATE SEQUENCE s5;
SELECT s5.CURRVAL FROM dual;
```

```text
ERROR:
ORA-02289: sequence does not exist

Sequence created.

ERROR:
ORA-20000: currval of sequence "s5" is not yet defined in this session
```

### H. Options that are accepted, and two that are not

<!-- example: oracle -->
```sql
CREATE SEQUENCE s6 SESSION;
CREATE SEQUENCE s7 SCALE EXTEND;
CREATE SEQUENCE s8 ORDER KEEP CACHE 20;
```

```text
ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

Sequence created.
```

## See also

[ALTER SEQUENCE](alter-sequence.md), [DROP SEQUENCE](drop-sequence.md), [INSERT](insert.md)
