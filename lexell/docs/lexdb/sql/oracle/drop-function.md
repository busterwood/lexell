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

- A view that calls the function is still read after it is dropped, with NULL in the function's column, and
  `USER_OBJECTS.STATUS` stays `VALID`; Oracle marks the view `INVALID` and reading it is ORA-04063 (see [CREATE
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
