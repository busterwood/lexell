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

- Each session has its own copy of a package's variables. The first use makes them from their initial values, and the
  body's initialisation section (`BEGIN` ... at its end) runs then. Another session's assignments are not seen.
- When a package is compiled again (`CREATE OR REPLACE`), a session that held its state gets **ORA-04068** ("existing
  state of packages has been discarded") at its next call into the package, once; the call after it runs on fresh
  variables. Reading or assigning a variable from outside does not raise it.
- A package's members are called as `package.member`: `pay.give_bonus(1)`, `pay.total()`. Variables and constants
  declared in the specification are shared by the code that uses the package, and keep their values for the session.
- A package whose specification declares no procedure or function needs no body: its variables and constants are used
  as they are (example F).
- `USER_OBJECTS` lists both as `PACKAGE` and `PACKAGE BODY`; `USER_SOURCE` has their text.

## Differences from Oracle

- **Package variables are used from PL/SQL, not from a statement of its own.** A block, procedure or function outside
  the package reads and assigns the package's variables and reads its constants (example C), also inside a SQL
  statement it runs. A statement sent by itself (`SELECT pay.g_count FROM dual`) is ORA-06553, as in Oracle
  (example D). Not supported: a package variable as an `INTO` target or an `OUT` argument from outside the package,
  and a variable of a record or collection type.
- A specification that declares procedures or functions needs its body: without it a call is PLS-00201 (Oracle:
  ORA-04067).
- Records, subtypes and exceptions declared in a package are not supported, with a body or without. Collection types and
  nested subprograms are not supported, as elsewhere in PL/SQL.

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

A block outside the package reads and assigns the variables of its specification. They belong to the session: they
keep their values from one block to the next.

<!-- example: oracle -->
```sql
BEGIN
  DBMS_OUTPUT.PUT_LINE('count ' || pay.g_count || ', bonus ' || pay.c_bonus);
  pay.g_count := 100;
  DBMS_OUTPUT.PUT_LINE('count_given() says ' || pay.count_given());
  pay.give_bonus(1);
  pay.g_count := pay.g_count + 5;
END;
/
DECLARE
  v VARCHAR2(20);
BEGIN
  DBMS_OUTPUT.PUT_LINE('count is now ' || pay.g_count);
  IF pay.g_count > 100 THEN
    DBMS_OUTPUT.PUT_LINE('over 100');
  END IF;
  SELECT name INTO v FROM emp WHERE id = pay.g_count - 104;
  DBMS_OUTPUT.PUT_LINE('row ' || (pay.g_count - 104) || ' is ' || v);
  pay.g_count := 0;
END;
/
```

```text
count 3, bonus 10
count_given() says 100

PL/SQL procedure successfully completed.

count is now 106
over 100
row 2 is bob

PL/SQL procedure successfully completed.
```

### D. What a variable cannot do

A statement of its own cannot name a package variable (ORA-06553, as in Oracle). A constant cannot be assigned
(PLS-00363), and a name the package does not have is PLS-00302.

<!-- example: oracle -->
```sql
SELECT pay.g_count FROM dual;
BEGIN
  pay.c_bonus := 5;
END;
/
BEGIN
  DBMS_OUTPUT.PUT_LINE(pay.nothere);
END;
/
```

```text
ERROR:
ORA-06553: PLS-221: 'G_COUNT' is not a procedure or is undefined

ERROR:
ORA-06550: line 2, column 3:
PLS-00363: expression 'PAY.C_BONUS' cannot be used as an assignment target
ORA-06550: line 2, column 3:
PL/SQL: Statement ignored

ERROR:
ORA-06550: line 2, column 28:
PLS-00302: component 'NOTHERE' must be declared
ORA-06550: line 2, column 3:
PL/SQL: Statement ignored
```

### E. The dictionary

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

### F. A package with only a specification

A package of variables and constants needs no body. A package that declares a procedure does:

<!-- example: oracle -->
```sql
CREATE OR REPLACE PACKAGE cfg AS
  c_rate CONSTANT NUMBER := 0.2;
  g_hits NUMBER := 0;
  g_name VARCHAR2(20) := 'none';
END cfg;
/
BEGIN
  cfg.g_hits := cfg.g_hits + 1;
  cfg.g_name := 'main';
  DBMS_OUTPUT.PUT_LINE(cfg.g_name || ' ' || cfg.g_hits || ' ' || cfg.c_rate);
END;
/
CREATE OR REPLACE PACKAGE nobody_home AS
  PROCEDURE p;
END nobody_home;
/
BEGIN nobody_home.p; END;
/
```

```text
Package created.

main 1 .2

PL/SQL procedure successfully completed.

Package created.

ERROR:
ORA-06550: line 1, column 7:
PLS-00201: identifier 'NOBODY_HOME.P' must be declared
ORA-06550: line 1, column 7:
PL/SQL: Statement ignored
```

## See also

[CREATE PROCEDURE](create-procedure.md), [CREATE FUNCTION](create-function.md), [DROP PACKAGE](drop-package.md),
[ALTER PROCEDURE, FUNCTION, PACKAGE](alter-procedure.md)
