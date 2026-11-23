# DROP PROCEDURE

Removes a stored procedure.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP PROCEDURE [ schema. ] procedure
```

## Remarks

- A procedure that does not exist is ORA-04043 (`object NAME does not exist`).
- Calls to a dropped procedure from other units fail when they run.

## Differences from Oracle

- None known.

## Examples

### A. Drop a procedure

<!-- example: oracle -->
```sql
CREATE PROCEDURE p AS
BEGIN
  NULL;
END;
/
DROP PROCEDURE p;
DROP PROCEDURE p;
```

```text
Procedure created.

Procedure dropped.

ERROR:
ORA-04043: object P does not exist
```

## See also

[CREATE PROCEDURE](create-procedure.md), [DROP FUNCTION](drop-function.md), [DROP PACKAGE](drop-package.md)
