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
  default, and the next `INSERT` that needs the default fails (example B).

## Differences from Oracle

- An `INSERT` into a table whose default calls the dropped sequence is ORA-00942 (`table or view "SA"."S6" does not
  exist`), also when the statement gives the column a value. The error of a missing sequence is ORA-02289 (as
  `s6.NEXTVAL` gives it).

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
DROP TABLE ticket;
```

```text
Sequence created.

Table created.

1 row created.

Sequence dropped.

ERROR:
ORA-00942: table or view "SA"."S6" does not exist

ERROR:
ORA-00942: table or view "SA"."S6" does not exist

ID NOTE
-- -----
 1 first

1 row selected.

Table dropped.
```

## See also

[CREATE SEQUENCE](create-sequence.md), [ALTER SEQUENCE](alter-sequence.md)
