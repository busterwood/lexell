# DROP SEQUENCE

Removes a sequence.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP SEQUENCE [ schema. ] sequence
```

## Remarks

- A sequence that does not exist is ORA-02289.

- A sequence that a column's default calls (`DEFAULT s.NEXTVAL`) cannot be dropped while the default exists: the
  statement is ORA-02449 (example B).

## Differences from Oracle

- The refusal for a sequence under a column default carries the message of ORA-02449 (`unique/primary keys in table
  referenced by foreign keys`), which does not describe it. The drop is refused until the table (or the default) is
  dropped; whether Oracle itself refuses it was not checked.

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
ORA-00942: table or view "SA"."S5" does not exist
```

### B. A sequence a column default uses

<!-- example: oracle -->
```sql
CREATE SEQUENCE s6;
CREATE TABLE ticket (id NUMBER DEFAULT s6.NEXTVAL, note VARCHAR2(20));
DROP SEQUENCE s6;
INSERT INTO ticket (note) VALUES ('first');
SELECT id, note FROM ticket;
DROP TABLE ticket;
DROP SEQUENCE s6;
```

```text
Sequence created.

Table created.

ERROR:
ORA-02449: unique/primary keys in table referenced by foreign keys

1 row created.

ID NOTE
-- -----
 1 first

1 row selected.

Table dropped.

Sequence dropped.
```

## See also

[CREATE SEQUENCE](create-sequence.md), [ALTER SEQUENCE](alter-sequence.md)
