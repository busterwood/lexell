# DROP SEQUENCE

Removes a sequence.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP SEQUENCE [ schema. ] sequence
```

## Remarks

- A sequence that does not exist is ORA-02289.

## Differences from Oracle

- None known.

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

## See also

[CREATE SEQUENCE](create-sequence.md), [ALTER SEQUENCE](alter-sequence.md)
