# DROP FUNCTION

Removes a stored function.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP FUNCTION [ schema. ] function
```

## Remarks

- A function that does not exist is ORA-04043.
- A query or unit that calls a dropped function fails when it runs.

## Differences from Oracle

- A view that calls the function is ORA-04063 after it is dropped, as in Oracle, but `USER_OBJECTS.STATUS` stays
  `VALID` (Oracle: `INVALID`), and a session that read the view before the drop gets ORA-00904 once (see [CREATE
  VIEW](create-view.md)).

## Examples

### A. Drop a function

<!-- example: oracle -->
```sql
CREATE FUNCTION one RETURN NUMBER AS
BEGIN
  RETURN 1;
END;
/
SELECT one() AS one FROM dual;
DROP FUNCTION one;
SELECT one() AS one FROM dual;
DROP FUNCTION one;
```

```text
Function created.

ONE
---
  1

1 row selected.

Function dropped.

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-04043: object ONE does not exist
```

## See also

[CREATE FUNCTION](create-function.md), [DROP PROCEDURE](drop-procedure.md), [DROP PACKAGE](drop-package.md)
