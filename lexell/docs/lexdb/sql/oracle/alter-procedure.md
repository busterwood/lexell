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

- `COMPILE` compiles the unit again from its stored source. When it compiles, its status is `VALID`. When it does
  not (a procedure it calls has been dropped, say), the statement answers "Warning: Procedure altered with
  compilation errors.", the status is `INVALID` and [USER_ERRORS](data-dictionary-programs.md) holds the errors.
- A unit that is invalid (see [CREATE PROCEDURE](create-procedure.md)) is also compiled again, and becomes valid,
  when a block that names it runs.
- A name that is no unit is ORA-04043.

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

### B. A unit that no longer compiles

`caller` is made while `helper` does not exist, so it is stored invalid. Once `helper` exists, `COMPILE` makes it valid.
When `helper` is dropped, the next `COMPILE` leaves it invalid again, and `USER_ERRORS` says why.

<!-- example: oracle -->
```sql
CREATE PROCEDURE caller AS
BEGIN
  helper(1);
END;
/
SELECT object_name, status FROM user_objects WHERE object_name = 'CALLER';
CREATE PROCEDURE helper (n NUMBER) AS
BEGIN
  NULL;
END;
/
ALTER PROCEDURE caller COMPILE;
SELECT object_name, status FROM user_objects WHERE object_name = 'CALLER';
DROP PROCEDURE helper;
ALTER PROCEDURE caller COMPILE;
SELECT object_name, status FROM user_objects WHERE object_name = 'CALLER';
SELECT line, text FROM user_errors WHERE name = 'CALLER';
```

```text
Warning: Procedure created with compilation errors.

OBJECT_NAME STATUS
----------- -------
CALLER      INVALID

1 row selected.

Procedure created.

Procedure altered.

OBJECT_NAME STATUS
----------- ------
CALLER      VALID

1 row selected.

Procedure dropped.

Warning: Procedure altered with compilation errors.

OBJECT_NAME STATUS
----------- -------
CALLER      INVALID

1 row selected.

LINE TEXT
---- -----------------------------------------------
   3 PLS-00201: identifier 'HELPER' must be declared
   3 PL/SQL: Statement ignored

2 rows selected.
```

### C. A unit that does not exist

<!-- example: oracle -->
```sql
ALTER PROCEDURE nothere COMPILE;
```

```text
ERROR:
ORA-04043: object NOTHERE does not exist
```

## See also

[CREATE PROCEDURE](create-procedure.md), [CREATE FUNCTION](create-function.md), [CREATE PACKAGE](create-package.md)
