# DROP SEQUENCE

Removes a sequence.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP SEQUENCE [ schema. ] sequence
```

## Remarks

- A sequence that does not exist is ORA-02289, and so is `s.NEXTVAL` of a sequence that was dropped.
- A sequence that a column's default calls (`DEFAULT s.NEXTVAL`) can be dropped, as in Oracle. The column keeps its
  default, and the next `INSERT` that takes the default fails with ORA-02289 (example B). An `INSERT` that gives the
  column a value, and an `UPDATE`, are not affected.

## Differences from Oracle

- `USER_TAB_COLUMNS.DATA_DEFAULT` of a column whose default is a sequence shows `nextval('s6')`, where Oracle shows
  `"SA"."S6"."NEXTVAL"`.

## Examples

### A. Drop a sequence

<!-- example: oracle -->
```sql
CREATE SEQUENCE s5;
DROP SEQUENCE s5;
DROP SEQUENCE s5;
SELECT s5.NEXTVAL FROM dual;
```

```text
Sequence created.

Sequence dropped.

ERROR:
ORA-02289: sequence does not exist

ERROR:
ORA-02289: sequence does not exist
```

### B. A sequence a column default uses

<!-- example: oracle -->
```sql
CREATE SEQUENCE s6;
CREATE TABLE ticket (id NUMBER DEFAULT s6.NEXTVAL, note VARCHAR2(20));
INSERT INTO ticket (note) VALUES ('first');
DROP SEQUENCE s6;
INSERT INTO ticket (note) VALUES ('second');
INSERT INTO ticket (id, note) VALUES (10, 'second');
SELECT id, note FROM ticket;
SELECT data_default FROM user_tab_columns WHERE table_name = 'TICKET' AND column_name = 'ID';
DROP TABLE ticket;
```

```text
Sequence created.

Table created.

1 row created.

Sequence dropped.

ERROR:
ORA-02289: sequence does not exist

1 row created.

ID NOTE
-- ------
 1 first
10 second

2 rows selected.

DATA_DEFAULT
-------------
nextval('s6')

1 row selected.

Table dropped.
```

## See also

[CREATE SEQUENCE](create-sequence.md), [ALTER SEQUENCE](alter-sequence.md)
