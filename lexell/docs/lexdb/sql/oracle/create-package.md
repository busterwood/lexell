# CREATE PACKAGE, CREATE PACKAGE BODY

Creates or replaces a package: procedures, functions, variables and constants kept together under one name.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE [ OR REPLACE ] PACKAGE [ schema. ] package { IS | AS }
    variable_or_constant_declaration
    procedure_or_function_declaration
END [ package ] ;

CREATE [ OR REPLACE ] PACKAGE BODY [ schema. ] package { IS | AS }
    [ private declarations ]
    procedure_or_function_definition
    [ BEGIN initialization statements ]
END [ package ] ;
```

## Arguments

*specification* (`PACKAGE`)
: The public part: constants, variables, cursors, types, and the headings of the procedures and functions callers may
  use (`PROCEDURE p (x NUMBER);`, `FUNCTION f RETURN NUMBER;`).

*body* (`PACKAGE BODY`)
: The code of each procedure and function of the specification, and private ones that only the body uses. The
  body's headings must match the specification.

## Remarks

- A package's members are called as `package.member`: `pay.give_bonus(1)`, `pay.total()`. Variables and constants
  declared in the specification are shared by the code that uses the package, and keep their values for the session.
- `USER_OBJECTS` lists both as `PACKAGE` and `PACKAGE BODY`; `USER_SOURCE` has their text.

## Differences from Oracle

- **Package variables and constants cannot be read from outside the package:** `DBMS_OUTPUT.PUT_LINE(pay.g_count)`
  and `pay.c_bonus` are ORA-00904 (example C). The package's own code uses them freely. A function in the package
  can return the value instead.
- Collection types and nested subprograms are not supported, as elsewhere in PL/SQL.

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), salary NUMBER(8,2));
INSERT INTO emp VALUES (1, 'ann', 100);
INSERT INTO emp VALUES (2, 'bob', 200);
COMMIT;
-->

The examples use a table `emp (id, name, salary)` with two rows: ann 100 and bob 200.

### A. A package and its body

<!-- example: oracle -->
```sql
CREATE OR REPLACE PACKAGE pay AS
  c_bonus CONSTANT NUMBER := 10;
  g_count NUMBER := 0;
  PROCEDURE give_bonus (p_id NUMBER);
  FUNCTION total RETURN NUMBER;
  FUNCTION count_given RETURN NUMBER;
END pay;
/
CREATE OR REPLACE PACKAGE BODY pay AS
  PROCEDURE give_bonus (p_id NUMBER) IS
  BEGIN
    UPDATE emp SET salary = salary + c_bonus WHERE id = p_id;
    g_count := g_count + 1;
  END;
  FUNCTION total RETURN NUMBER IS
    v NUMBER;
  BEGIN
    SELECT SUM(salary) INTO v FROM emp;
    RETURN v;
  END;
  FUNCTION count_given RETURN NUMBER IS
  BEGIN
    RETURN g_count;
  END;
END pay;
/
```

```text
Package created.

Package body created.
```

### B. Calling its members

<!-- example: oracle -->
```sql
BEGIN
  pay.give_bonus(1);
  pay.give_bonus(2);
  DBMS_OUTPUT.PUT_LINE('given ' || pay.count_given() || ', total ' || pay.total());
END;
/
SELECT pay.total() AS total FROM dual;
EXEC pay.give_bonus(1);
SELECT pay.total() AS total_after FROM dual;
```

```text
given 2, total 320

PL/SQL procedure successfully completed.

TOTAL
-----
  320

1 row selected.

Statement processed.

TOTAL_AFTER
-----------
        330

1 row selected.
```

### C. Package variables from outside

<!-- example: oracle -->
```sql
BEGIN
  DBMS_OUTPUT.PUT_LINE('count ' || pay.g_count);
END;
/
BEGIN
  DBMS_OUTPUT.PUT_LINE('bonus ' || pay.c_bonus);
END;
/
```

```text
ERROR:
ORA-00904: invalid identifier
ORA-06512: at line 2

ERROR:
ORA-00904: invalid identifier
ORA-06512: at line 2
```

### D. The dictionary

<!-- example: oracle -->
```sql
SELECT object_name, object_type, status FROM user_objects WHERE object_name = 'PAY' ORDER BY object_type;
```

```text
OBJECT_NAME OBJECT_TYPE  STATUS
----------- ------------ ------
PAY         PACKAGE      VALID
PAY         PACKAGE BODY VALID

2 rows selected.
```

## See also

[CREATE PROCEDURE](create-procedure.md), [CREATE FUNCTION](create-function.md), [DROP PACKAGE](drop-package.md),
[ALTER PROCEDURE, FUNCTION, PACKAGE](alter-procedure.md)
