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
- A view that calls the function is ORA-04063 when it is read after the drop, and `USER_OBJECTS.STATUS` of the view is
  `INVALID` (example B).

## Differences from Oracle

- `USER_OBJECTS.STATUS` of the view is `VALID` again as soon as the function is created again; Oracle shows it
  `INVALID` until the view's next use (example B).
- A transaction that wrote something before the drop gets ORA-04063 at once, as Oracle does (see
  [CREATE VIEW](create-view.md)).

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

### B. A view over the dropped function

<!-- example: oracle -->
```sql
CREATE TABLE pay (id NUMBER PRIMARY KEY, amount NUMBER);
INSERT INTO pay VALUES (1, 100);
CREATE FUNCTION twice (x NUMBER) RETURN NUMBER AS
BEGIN
  RETURN x * 2;
END;
/
CREATE VIEW pay_twice AS SELECT id, twice(amount) AS amount FROM pay;
SELECT * FROM pay_twice;
DROP FUNCTION twice;
SELECT * FROM pay_twice;
SELECT object_name, object_type, status FROM user_objects WHERE object_name IN ('TWICE', 'PAY_TWICE') ORDER BY object_name;
CREATE FUNCTION twice (x NUMBER) RETURN NUMBER AS
BEGIN
  RETURN x * 2;
END;
/
SELECT object_name, object_type, status FROM user_objects WHERE object_name IN ('TWICE', 'PAY_TWICE') ORDER BY object_name;
SELECT * FROM pay_twice;
```

```text
Table created.

1 row created.

Function created.

View created.

ID AMOUNT
-- ------
 1    200

1 row selected.

Function dropped.

ERROR:
ORA-04063: view "SA.PAY_TWICE" has errors

OBJECT_NAME OBJECT_TYPE STATUS
----------- ----------- -------
PAY_TWICE   VIEW        INVALID

1 row selected.

Function created.

OBJECT_NAME OBJECT_TYPE STATUS
----------- ----------- ------
PAY_TWICE   VIEW        VALID
TWICE       FUNCTION    VALID

2 rows selected.

ID AMOUNT
-- ------
 1    200

1 row selected.
```

## See also

[CREATE FUNCTION](create-function.md), [DROP PROCEDURE](drop-procedure.md), [DROP PACKAGE](drop-package.md)
