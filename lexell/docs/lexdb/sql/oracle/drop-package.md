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

- A view that calls one of the package's functions gives ORA-04067 after `DROP PACKAGE BODY` and ORA-04063 after
  `DROP PACKAGE`, as Oracle does (example B). ORA-04067 is its one line; Oracle adds ORA-06508 and ORA-06512 lines.
  `USER_OBJECTS.STATUS` of the view is `INVALID` after `DROP PACKAGE` and `VALID` after `DROP PACKAGE BODY`, as in
  Oracle. In a transaction that wrote something before the drop, a read of the view is ORA-00904 until the
  transaction ends (see [CREATE VIEW](create-view.md)).

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

### B. A view over a package's function

<!-- example: oracle -->
```sql
CREATE TABLE pay (id NUMBER PRIMARY KEY, amount NUMBER);
INSERT INTO pay VALUES (1, 100);
CREATE PACKAGE calc AS
  FUNCTION thrice (x NUMBER) RETURN NUMBER;
END calc;
/
CREATE PACKAGE BODY calc AS
  FUNCTION thrice (x NUMBER) RETURN NUMBER IS
  BEGIN
    RETURN x * 3;
  END;
END calc;
/
CREATE VIEW pay_thrice AS SELECT id, calc.thrice(amount) AS amount FROM pay;
SELECT * FROM pay_thrice;
DROP PACKAGE BODY calc;
SELECT * FROM pay_thrice;
SELECT object_name, object_type, status FROM user_objects WHERE object_name IN ('CALC', 'PAY_THRICE') ORDER BY object_name;
DROP PACKAGE calc;
SELECT * FROM pay_thrice;
SELECT object_name, object_type, status FROM user_objects WHERE object_name IN ('CALC', 'PAY_THRICE') ORDER BY object_name;
```

```text
Table created.

1 row created.

Package created.

Package body created.

View created.

ID AMOUNT
-- ------
 1    300

1 row selected.

Package body dropped.

ERROR:
ORA-04067: not executed, package body "SA.CALC" does not exist

OBJECT_NAME OBJECT_TYPE STATUS
----------- ----------- ------
CALC        PACKAGE     VALID
PAY_THRICE  VIEW        VALID

2 rows selected.

Package dropped.

ERROR:
ORA-04063: view "SA.PAY_THRICE" has errors

OBJECT_NAME OBJECT_TYPE STATUS
----------- ----------- -------
PAY_THRICE  VIEW        INVALID

1 row selected.
```

## See also

[CREATE PACKAGE](create-package.md), [DROP PROCEDURE](drop-procedure.md), [DROP FUNCTION](drop-function.md)
