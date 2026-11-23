# ALTER PROCEDURE, ALTER FUNCTION, ALTER PACKAGE

Recompiles a stored unit.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
ALTER PROCEDURE [ schema. ] procedure COMPILE
ALTER FUNCTION [ schema. ] function COMPILE
ALTER PACKAGE [ schema. ] package COMPILE [ BODY | SPECIFICATION | PACKAGE ]
```

## Remarks

- The statement is accepted and does not change the unit: lexdb checks a unit when it is created.
- A unit that does not exist is not an error: `ALTER PROCEDURE nothere COMPILE` answers `Procedure altered.`
  (Oracle: ORA-04043).

## Differences from Oracle

- Only `COMPILE` is taken.

## Examples

### A. Recompile

<!-- example: oracle -->
```sql
CREATE PROCEDURE p AS
BEGIN
  NULL;
END;
/
CREATE FUNCTION f RETURN NUMBER AS
BEGIN
  RETURN 1;
END;
/
CREATE PACKAGE k AS
  PROCEDURE q;
END k;
/
CREATE PACKAGE BODY k AS
  PROCEDURE q IS
  BEGIN
    NULL;
  END;
END k;
/
ALTER PROCEDURE p COMPILE;
ALTER FUNCTION f COMPILE;
ALTER PACKAGE k COMPILE;
ALTER PACKAGE k COMPILE BODY;
SELECT object_name, object_type, status FROM user_objects WHERE object_type LIKE 'P%' OR object_type = 'FUNCTION'
ORDER BY object_type, object_name;
```

```text
Procedure created.

Function created.

Package created.

Package body created.

Procedure altered.

Function altered.

Package altered.

Package altered.

OBJECT_NAME OBJECT_TYPE  STATUS
----------- ------------ ------
F           FUNCTION     VALID
K           PACKAGE      VALID
K           PACKAGE BODY VALID
P           PROCEDURE    VALID

4 rows selected.
```

### B. A unit that does not exist is not refused

<!-- example: oracle -->
```sql
ALTER PROCEDURE nothere COMPILE;
```

```text
Procedure altered.
```

## See also

[CREATE PROCEDURE](create-procedure.md), [CREATE FUNCTION](create-function.md), [CREATE PACKAGE](create-package.md)
