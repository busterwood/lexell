# ALTER SEQUENCE

Changes a sequence's step, limits or position.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
ALTER SEQUENCE [ schema. ] sequence
    [ INCREMENT BY n ] [ MAXVALUE n | NOMAXVALUE ] [ MINVALUE n | NOMINVALUE ]
    [ CYCLE | NOCYCLE ] [ CACHE n | NOCACHE ] [ ORDER | NOORDER ]
    [ RESTART [ START WITH n ] ]
```

## Arguments

`INCREMENT BY`, `MAXVALUE`, `MINVALUE`, `CYCLE`, `CACHE`, `ORDER`
: As in [CREATE SEQUENCE](create-sequence.md). The next value follows the new step.

`RESTART`
: Sets the sequence back to its start value, or to `START WITH n` (Oracle 18c and later). The next `NEXTVAL` gives
  that value.

## Remarks

- A change does not affect values already given.

## Differences from Oracle

- `ALTER SEQUENCE ... START WITH n` is accepted and does nothing; Oracle refuses it (ORA-02283).
- A sequence that does not exist is ORA-00942.

## Examples

### A. A new step, and RESTART

<!-- example: oracle -->
```sql
CREATE SEQUENCE s1;
SELECT s1.NEXTVAL FROM dual;
SELECT s1.NEXTVAL FROM dual;
ALTER SEQUENCE s1 INCREMENT BY 5 MAXVALUE 1000;
SELECT s1.NEXTVAL FROM dual;
ALTER SEQUENCE s1 RESTART;
SELECT s1.NEXTVAL FROM dual;
ALTER SEQUENCE s1 RESTART START WITH 50;
SELECT s1.NEXTVAL FROM dual;
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

Sequence altered.

NEXTVAL
-------
      7

1 row selected.

Sequence altered.

NEXTVAL
-------
      1

1 row selected.

Sequence altered.

NEXTVAL
-------
     50

1 row selected.
```

### B. START WITH

<!-- example: oracle -->
```sql
ALTER SEQUENCE s1 START WITH 5;
SELECT s1.NEXTVAL FROM dual;
```

```text
Sequence altered.

NEXTVAL
-------
     55

1 row selected.
```

### C. A missing sequence

<!-- example: oracle -->
```sql
ALTER SEQUENCE nothere INCREMENT BY 2;
```

```text
ERROR:
ORA-00942: table or view "SA"."NOTHERE" does not exist
```

## See also

[CREATE SEQUENCE](create-sequence.md), [DROP SEQUENCE](drop-sequence.md)
