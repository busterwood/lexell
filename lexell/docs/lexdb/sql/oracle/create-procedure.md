# CREATE PROCEDURE

Creates or replaces a stored procedure written in PL/SQL.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE [ OR REPLACE ] PROCEDURE [ schema. ] procedure
    [ ( parameter [, parameter ]... ) ]
    { IS | AS }
    [ declaration [ declaration ]... ]
BEGIN
    statement [ statement ]...
[ EXCEPTION
    handler [ handler ]... ]
END [ procedure ] ;

parameter:
    name [ IN | OUT | IN OUT ] datatype [ { := | DEFAULT } expr ]
```

## Arguments

`OR REPLACE`
: Replaces a procedure of that name. Without it, a name that is used is ORA-00955.

*parameter*
: A name, a mode and a type, without a length (`NUMBER`, `VARCHAR2`). `IN` (the default) passes a value in; `OUT`
  returns one; `IN OUT` does both. An `IN` parameter may have a default, so a call can leave it out.

*declaration*
: Variables, cursors and exceptions local to the procedure: see [PL/SQL declarations](plsql-declarations.md).

## Remarks

- The body is PL/SQL: see [blocks](plsql-blocks.md). Like an anonymous block, the statement is sent as one unit and
  a line holding `/` ends it in SQL\*Plus and in the examples.
- A procedure is called from a block (`my_proc(1, 2);`), with `CALL`, or with `EXEC`: see [CALL](call.md). Arguments
  go by position, or by name (`p_id => 2`) after the positional ones.
- A procedure may call itself and other procedures.
- A body that does not compile (a call of a procedure that does not exist, an unknown identifier) does not stop the
  statement: the procedure is stored **invalid**, and SQL\*Plus says "Warning: Procedure created with compilation
  errors." `USER_OBJECTS.STATUS` is `INVALID`, and `USER_ERRORS` and `ALL_ERRORS` hold the `PLS-` errors with their
  line and position. `CALL` of an invalid procedure is ORA-06575, and a block that names it is ORA-06550 with
  PLS-00905. [ALTER PROCEDURE ... COMPILE](alter-procedure.md) compiles it again (example F).
- `USER_OBJECTS` lists the procedure, and `USER_SOURCE` its text: see the
  [data dictionary](data-dictionary-programs.md).

## Differences from Oracle

- Subprograms declared inside another unit or block, collection-typed parameters, and `AUTHID`, `ACCESSIBLE BY` and
  `PRAGMA AUTONOMOUS_TRANSACTION` clauses are not supported.
- A call with a wrong argument count is PLS-00306, as in Oracle; an argument that cannot be converted is ORA-06502.

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), salary NUMBER(8,2));
INSERT INTO emp VALUES (1, 'ann', 100);
INSERT INTO emp VALUES (2, 'bob', 200);
COMMIT;
-->

The examples use a table `emp (id, name, salary)` with two rows: ann 100 and bob 200.

### A. A procedure with IN and OUT parameters, and a default

<!-- example: oracle -->
```sql
CREATE OR REPLACE PROCEDURE raise_pay (p_id IN NUMBER, p_pct IN NUMBER DEFAULT 10, p_new OUT NUMBER) AS
BEGIN
  UPDATE emp SET salary = salary * (1 + p_pct / 100) WHERE id = p_id RETURNING salary INTO p_new;
  DBMS_OUTPUT.PUT_LINE('raised ' || p_id);
END;
/
DECLARE
  v NUMBER;
BEGIN
  raise_pay(1, 50, v);
  DBMS_OUTPUT.PUT_LINE('new salary ' || v);
  raise_pay(p_id => 2, p_new => v);
  DBMS_OUTPUT.PUT_LINE('new salary ' || v);
END;
/
```

```text
Procedure created.

raised 1
new salary 150
raised 2
new salary 220

PL/SQL procedure successfully completed.
```

### B. IN OUT

<!-- example: oracle -->
```sql
CREATE OR REPLACE PROCEDURE swap (a IN OUT NUMBER, b IN OUT NUMBER) IS
  t NUMBER;
BEGIN
  t := a;
  a := b;
  b := t;
END;
/
DECLARE
  x NUMBER := 1;
  y NUMBER := 2;
BEGIN
  swap(x, y);
  DBMS_OUTPUT.PUT_LINE(x || ' ' || y);
END;
/
```

```text
Procedure created.

2 1

PL/SQL procedure successfully completed.
```

### C. A recursive procedure

<!-- example: oracle -->
```sql
CREATE OR REPLACE PROCEDURE countdown (n NUMBER) IS
BEGIN
  IF n > 0 THEN
    DBMS_OUTPUT.PUT_LINE(n);
    countdown(n - 1);
  END IF;
END;
/
BEGIN
  countdown(3);
END;
/
```

```text
Procedure created.

3
2
1

PL/SQL procedure successfully completed.
```

### D. Calling with the wrong arguments

<!-- example: oracle -->
```sql
CREATE PROCEDURE p_text (n NUMBER) AS
BEGIN
  DBMS_OUTPUT.PUT_LINE('n=' || n);
END;
/
CALL p_text('abc');
CALL p_text(1, 2);
CREATE PROCEDURE p_text AS
BEGIN
  NULL;
END;
/
```

```text
Procedure created.

ERROR:
ORA-06502: PL/SQL: value or conversion error: character to number conversion error
ORA-06512: at line 1

ERROR:
ORA-06550: line 1, column 17:
PLS-00306: wrong number or types of arguments in call to 'P_TEXT'
ORA-06550: line 1, column 7:
PL/SQL: Statement ignored

ERROR:
ORA-00955: name is already used by an existing object
```

### E. The dictionary

<!-- example: oracle -->
```sql
SELECT object_name, object_type, status FROM user_objects WHERE object_type = 'PROCEDURE' ORDER BY object_name;
```

```text
OBJECT_NAME OBJECT_TYPE STATUS
----------- ----------- ------
COUNTDOWN   PROCEDURE   VALID
P_TEXT      PROCEDURE   VALID
RAISE_PAY   PROCEDURE   VALID
SWAP        PROCEDURE   VALID

4 rows selected.
```

### F. A procedure that does not compile

<!-- example: oracle -->
```sql
CREATE PROCEDURE report AS
BEGIN
  nothere(1);
END;
/
SELECT object_name, status FROM user_objects WHERE object_name = 'REPORT';
SELECT line, position, text FROM user_errors WHERE name = 'REPORT';
CALL report();
BEGIN
  report;
END;
/
```

```text
Warning: Procedure created with compilation errors.

OBJECT_NAME STATUS
----------- -------
REPORT      INVALID

1 row selected.

LINE POSITION TEXT
---- -------- ------------------------------------------------
   3        3 PLS-00201: identifier 'NOTHERE' must be declared
   3        3 PL/SQL: Statement ignored

2 rows selected.

ERROR:
ORA-06575: Package or function REPORT is in an invalid state

ERROR:
ORA-06550: line 2, column 1:
PLS-00905: object SA.REPORT is invalid
ORA-06550: line 2, column 1:
PL/SQL: Statement ignored
```

## See also

[CALL and EXECUTE](call.md), [CREATE FUNCTION](create-function.md), [CREATE PACKAGE](create-package.md),
[DROP PROCEDURE](drop-procedure.md), [PL/SQL blocks](plsql-blocks.md)
