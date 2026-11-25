# DROP PACKAGE

Removes a package, or only its body.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP PACKAGE [ BODY ] [ schema. ] package
```

## Arguments

`BODY`
: Drops the body and keeps the specification; calls fail until a body is created again.

## Remarks

- Without `BODY`, the specification and the body both go.
- A package that does not exist is ORA-04043.

## Differences from Oracle

- A view that calls one of the package's functions gives ORA-04063 after `DROP PACKAGE` and ORA-04067 after `DROP
  PACKAGE BODY`, as Oracle does, but a session that read the view before the drop gets ORA-00900 once (see [CREATE
  VIEW](create-view.md)).

## Examples

### A. Drop the body, then the package

<!-- example: oracle -->
```sql
CREATE PACKAGE util AS
  FUNCTION answer RETURN NUMBER;
END util;
/
CREATE PACKAGE BODY util AS
  FUNCTION answer RETURN NUMBER IS
  BEGIN
    RETURN 42;
  END;
END util;
/
SELECT util.answer() AS answer FROM dual;
SELECT object_type FROM user_objects WHERE object_name = 'UTIL' ORDER BY object_type;
DROP PACKAGE BODY util;
SELECT object_type FROM user_objects WHERE object_name = 'UTIL' ORDER BY object_type;
DROP PACKAGE util;
DROP PACKAGE util;
```

```text
Package created.

Package body created.

ANSWER
------
    42

1 row selected.

OBJECT_TYPE
------------
PACKAGE
PACKAGE BODY

2 rows selected.

Package body dropped.

OBJECT_TYPE
-----------
PACKAGE

1 row selected.

Package dropped.

ERROR:
ORA-04043: object UTIL does not exist
```

## See also

[CREATE PACKAGE](create-package.md), [DROP PROCEDURE](drop-procedure.md), [DROP FUNCTION](drop-function.md)
