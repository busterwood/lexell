# CREATE FUNCTION

Creates or replaces a stored function written in PL/SQL, which returns a value and can be used in SQL.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE [ OR REPLACE ] FUNCTION [ schema. ] function
    [ ( parameter [, parameter ]... ) ]
    RETURN datatype
    [ DETERMINISTIC ]
    { IS | AS }
    [ declaration [ declaration ]... ]
BEGIN
    statement [ statement ]...
[ EXCEPTION
    handler [ handler ]... ]
END [ function ] ;
```

*parameter* is as for [CREATE PROCEDURE](create-procedure.md).

## Arguments

`RETURN datatype`
: The type of the value, without a length. Every path through the body must end in `RETURN expr;`.

`DETERMINISTIC`
: Says that the same arguments always give the same result. It is accepted and has no effect.

## Remarks

- A function is called in an expression, in PL/SQL (`n := f(3);`) or in SQL (`SELECT f(salary) FROM emp`, and in
  `WHERE`, `ORDER BY` and other functions). A function with no parameters is called with empty brackets in SQL:
  `f()`.
- A function that reads tables can be called from SQL; one that changes data can be called from PL/SQL.
- The call works in a query sent by itself, in the SQL of a block (`SELECT f(x) INTO`, a cursor, a cursor `FOR` loop,
  `EXECUTE IMMEDIATE`, the DML of the block) and in `INSERT ... SELECT`, `UPDATE`, `DELETE` and `CREATE TABLE AS`
  (example G). The function runs once for each distinct set of arguments the statement gives it.
- A function that raises an unhandled exception ends the statement that called it with that error (example D, from
  PL/SQL). Called from a query, a function whose `SELECT ... INTO` finds no row (`NO_DATA_FOUND`) gives NULL, as in
  Oracle; any other error ends the query with the error and the `ORA-06512` lines of the function (example F).
- `CALL f(...) INTO :result` calls a function from a client with a bind variable; see [CALL](call.md).
- The function is listed in `USER_OBJECTS` and `USER_PROCEDURES`: see the
  [data dictionary](data-dictionary-programs.md).

## Differences from Oracle

- **A function with no parameters needs brackets in SQL.** `SELECT f FROM dual` is ORA-00904 (Oracle accepts it);
  write `f()`. Inside PL/SQL both forms work for a package function.
- A stored function is refused (ORA-03001, `unimplemented feature`) in a `MERGE`, in a subquery of an `INSERT`,
  `UPDATE` or `DELETE` that reads the statement's own table or refers to its columns, and with an argument that is an aggregate or another
  stored function's call (`f(SUM(x))`, `f(g(x))`). A view may call one, but an `INSERT`, `UPDATE`, `DELETE` or
  `CREATE TABLE ... AS` that reads such a view is ORA-03001 (Oracle allows it). Example H.
- Pipelined and table functions, `RESULT_CACHE`, `PARALLEL_ENABLE`, `AGGREGATE USING` and `AUTHID` are not supported.
- A `SYS_REFCURSOR` result works from PL/SQL; a JDBC client reads it as a cursor.
- **Compilation errors are found for names and syntax only.** An undeclared name, an expression that does not parse,
  a SQL statement that does not parse and DML on a missing table make the function `INVALID` when it is created
  (example I; a SQL statement's error is ORA-00936, or ORA-00907 with a parenthesis left open, at the token where
  lexdb's parser stopped: Oracle's number may differ for other syntax errors; a `SELECT ... INTO` with a
  parenthesis left open before `INTO` is ORA-00907, as in Oracle). Type errors, argument counts and
  unknown columns of a `SELECT INTO` appear when the code runs, and a package body or an anonymous block with any
  error is also found when it runs (Oracle: ORA-06550 first for a block).
- **Nested subprograms** (a `PROCEDURE` or `FUNCTION` in the declarations of the function, of a block or of another
  nested subprogram) work: forward declarations, recursion, calls between them, and the enclosing units' variables
  (example K). Not supported: overloading them (one subprogram to a name in a scope: with two `sq` of different
  argument types the later one is used for both calls, where Oracle picks by the arguments), and calling a nested
  function from SQL inside the unit (`SELECT sq(3) INTO r FROM dual`: the unit is stored `VALID`, and the statement is
  ORA-00904 when it runs; Oracle refuses the unit with PLS-00231).
- A call's column name is the call as written: `SELECT f(1) FROM dual` names the column `F(1)`, `5+f(3)` is `5+F(3)`
  and `f(id)` is `F(ID)`, as in Oracle (example A). A function whose name is quoted is exact, as every quoted
  name in the Oracle door is (see [CREATE TABLE](create-table.md)): `"MixF"` and `MIXF` are two functions, and
  `"MixF"(2)` is a call.

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), salary NUMBER(8,2));
INSERT INTO emp VALUES (1, 'ann', 100);
INSERT INTO emp VALUES (2, 'bob', 200);
COMMIT;
-->

The examples use a table `emp (id, name, salary)` with two rows: ann 100 and bob 200.

### A. A function in SQL

<!-- example: oracle -->
```sql
CREATE OR REPLACE FUNCTION double_it (x NUMBER) RETURN NUMBER AS
BEGIN
  RETURN x * 2;
END;
/
SELECT double_it(21) AS answer, double_it(salary) AS doubled FROM emp ORDER BY id;
SELECT double_it(21), 5+double_it(3), double_it(salary) FROM emp WHERE id = 1;
SELECT name FROM emp WHERE double_it(salary) > 250;
```

```text
Function created.

ANSWER DOUBLED
------ -------
    42     200
    42     400

2 rows selected.

DOUBLE_IT(21) 5+DOUBLE_IT(3) DOUBLE_IT(SALARY)
------------- -------------- -----------------
           42             11               200

1 row selected.

NAME
----
bob

1 row selected.
```

### B. Defaults and a local variable

<!-- example: oracle -->
```sql
CREATE OR REPLACE FUNCTION greet (p_name VARCHAR2, p_greeting VARCHAR2 DEFAULT 'Hello') RETURN VARCHAR2 IS
  v VARCHAR2(100);
BEGIN
  v := p_greeting || ', ' || p_name || '!';
  RETURN v;
END greet;
/
SELECT greet('ann') AS a, greet('bob', 'Hi') AS b FROM dual;
```

```text
Function created.

A           B
----------- --------
Hello, ann! Hi, bob!

1 row selected.
```

### C. A function without parameters

<!-- example: oracle -->
```sql
CREATE OR REPLACE FUNCTION seven RETURN NUMBER IS
BEGIN
  RETURN 7;
END;
/
SELECT seven() AS with_brackets FROM dual;
SELECT seven AS without_brackets FROM dual;
```

```text
Function created.

WITH_BRACKETS
-------------
            7

1 row selected.

ERROR:
ORA-00904: "SEVEN": invalid identifier
```

### D. A function that reads a table, and an error inside it

<!-- example: oracle -->
```sql
CREATE OR REPLACE FUNCTION pay_of (p_id NUMBER) RETURN NUMBER IS
  v NUMBER;
BEGIN
  SELECT salary INTO v FROM emp WHERE id = p_id;
  RETURN v;
END;
/
SELECT pay_of(2) AS bob FROM dual;
BEGIN
  DBMS_OUTPUT.PUT_LINE(pay_of(99));
END;
/
```

```text
Function created.

BOB
---
200

1 row selected.

ERROR:
ORA-01403: no data found
ORA-06512: at "SA.PAY_OF", line 4
ORA-06512: at line 2
```

### E. A function called from PL/SQL

<!-- example: oracle -->
```sql
DECLARE
  n NUMBER;
BEGIN
  n := pay_of(1) + pay_of(2);
  DBMS_OUTPUT.PUT_LINE('total pay ' || n);
END;
/
```

```text
total pay 300

PL/SQL procedure successfully completed.
```

### F. A function that raises, called from a query

`NO_DATA_FOUND` in a function called from a query is NULL for that row. Another error ends the query.

<!-- example: oracle -->
```sql
SELECT id, pay_of(id) AS pay, pay_of(id + 1) AS next_pay FROM emp ORDER BY id;
CREATE OR REPLACE FUNCTION strict_pay (p_id NUMBER) RETURN NUMBER IS
BEGIN
  IF p_id > 1 THEN
    RAISE_APPLICATION_ERROR(-20001, 'id too large');
  END IF;
  RETURN p_id;
END;
/
SELECT id, strict_pay(id) AS ok FROM emp WHERE id = 1;
SELECT id, strict_pay(id) AS ok FROM emp;
```

```text
ID PAY NEXT_PAY
-- --- --------
 1 100      200
 2 200

2 rows selected.

Function created.

ID OK
-- --
 1  1

1 row selected.

ERROR:
ORA-20001: id too large
ORA-06512: at "SA.STRICT_PAY", line 4
```

### G. A function in the SQL of a block, and in DML

A stored function works in every SQL statement: a query of a block, a cursor, `EXECUTE IMMEDIATE`, `INSERT ... SELECT`,
`UPDATE`, `DELETE`, `CREATE TABLE AS` and a view (see [CREATE VIEW](create-view.md), example G).

<!-- example: oracle -->
```sql
CREATE TABLE bonus (id NUMBER PRIMARY KEY, amount NUMBER);
INSERT INTO bonus SELECT id, double_it(salary) FROM emp;
UPDATE bonus SET amount = double_it(amount) WHERE id = 2;
CREATE TABLE doubled AS SELECT id, double_it(amount) AS amount FROM bonus;
DECLARE
  v NUMBER;
BEGIN
  SELECT double_it(salary) INTO v FROM emp WHERE id = 2;
  DBMS_OUTPUT.PUT_LINE('select into: ' || v);
  FOR r IN (SELECT name, double_it(salary) AS d FROM emp ORDER BY id) LOOP
    DBMS_OUTPUT.PUT_LINE('cursor: ' || r.name || ' ' || r.d);
  END LOOP;
  EXECUTE IMMEDIATE 'SELECT double_it(salary) FROM emp WHERE id = :1' INTO v USING 1;
  DBMS_OUTPUT.PUT_LINE('dynamic: ' || v);
  DELETE FROM bonus WHERE amount > double_it(300);
  DBMS_OUTPUT.PUT_LINE('deleted: ' || SQL%ROWCOUNT);
END;
/
SELECT * FROM bonus ORDER BY id;
SELECT * FROM doubled ORDER BY id;
ROLLBACK;
```

```text
Table created.

2 rows created.

1 row updated.

Table created.

select into: 400
cursor: ann 200
cursor: bob 400
dynamic: 200
deleted: 1

PL/SQL procedure successfully completed.

ID AMOUNT
-- ------
 1    200

1 row selected.

ID AMOUNT
-- ------
 1    400
 2   1600

2 rows selected.

Rollback complete.
```

### H. What is still refused

<!-- example: oracle -->
```sql
MERGE INTO bonus b USING emp e ON (b.id = e.id) WHEN MATCHED THEN UPDATE SET b.amount = double_it(e.salary);
UPDATE bonus SET amount = 0 WHERE EXISTS (SELECT 1 FROM emp e WHERE e.salary > double_it(bonus.amount));
CREATE VIEW doubled_pay AS SELECT id, double_it(salary) AS pay FROM emp;
INSERT INTO bonus SELECT id, pay FROM doubled_pay;
SELECT double_it(SUM(salary)) AS total FROM emp;
SELECT double_it(double_it(salary)) AS quad FROM emp ORDER BY id;
```

```text
ERROR:
ORA-03001: unimplemented feature: lexdb: a stored function called in a MERGE statement is not supported

ERROR:
ORA-03001: unimplemented feature: lexdb: a stored function called in a subquery that reads the statement's table is not supported in INSERT, UPDATE and DELETE

View created.

ERROR:
ORA-03001: unimplemented feature: lexdb: a view that calls a stored function is not supported in INSERT, UPDATE, DELETE and CREATE TABLE AS

ERROR:
ORA-03001: unimplemented feature: lexdb: an argument of a stored function that is an aggregate or calls a stored function is not supported

ERROR:
ORA-03001: unimplemented feature: lexdb: an argument of a stored function that is an aggregate or calls a stored function is not supported
```

### I. A function that does not compile

A function whose body has an undeclared name, an expression that does not parse, a SQL statement that does not parse or
DML on a table that does not exist is stored **invalid**, and SQL\*Plus says "Warning: Function created with compilation errors." `USER_OBJECTS.STATUS` is
`INVALID` and `USER_ERRORS` holds the `PLS-` errors with their line and position (the text of PLS-00103 has no list of
the symbols expected). A call from SQL is ORA-06575, and so is a `CREATE VIEW` over it.

<!-- example: oracle -->
```sql
CREATE FUNCTION bonus_of (p_id NUMBER) RETURN NUMBER IS
BEGIN
  RETURN p_id * rate;
END;
/
CREATE FUNCTION broken_sum (p_id NUMBER) RETURN NUMBER IS
BEGIN
  RETURN p_id + ;
END;
/
CREATE FUNCTION bad_count (p_id NUMBER) RETURN NUMBER IS
  n NUMBER;
BEGIN
  SELECT COUNT(*) INTO n FROM emp WHERE id = ;
  RETURN n;
END;
/
SELECT object_name, status FROM user_objects WHERE object_name IN ('BONUS_OF', 'BROKEN_SUM', 'BAD_COUNT') ORDER BY object_name;
SELECT name, line, position, text FROM user_errors ORDER BY name, sequence;
SELECT bonus_of(id) AS bonus FROM emp;
CREATE VIEW bonus_view AS SELECT id, bonus_of(id) AS bonus FROM emp;
```

```text
Warning: Function created with compilation errors.

Warning: Function created with compilation errors.

Warning: Function created with compilation errors.

OBJECT_NAME STATUS
----------- -------
BAD_COUNT   INVALID
BONUS_OF    INVALID
BROKEN_SUM  INVALID

3 rows selected.

NAME       LINE POSITION TEXT
---------- ---- -------- ---------------------------------------------
BAD_COUNT     4       46 PL/SQL: ORA-00936: missing expression
BAD_COUNT     4        3 PL/SQL: SQL Statement ignored
BONUS_OF      3       17 PLS-00201: identifier 'RATE' must be declared
BONUS_OF      3        3 PL/SQL: Statement ignored
BROKEN_SUM    3       17 PLS-00103: Encountered the symbol ";"

5 rows selected.

ERROR:
ORA-06575: Package or function BONUS_OF is in an invalid state

ERROR:
ORA-06575: Package or function BONUS_OF is in an invalid state
```

### J. Errors found when the code runs

Other errors in a function's body (a type mismatch, a wrong argument count, an unknown column of a `SELECT INTO`) do not
make the function invalid: they come when it runs (Oracle finds them when it compiles: PLS-00382 here, and ORA-06575 for
the call). The same holds for a package body and for an anonymous block, where Oracle's compile errors are ORA-06550
before anything runs (and ORA-04063 for the call of a package body with errors).

<!-- example: oracle -->
```sql
CREATE FUNCTION to_day (n NUMBER) RETURN NUMBER IS
  d DATE;
BEGIN
  d := n;
  RETURN 1;
END;
/
SELECT to_day(1) AS x FROM dual;
BEGIN
  INSERT INTO no_such_table VALUES (1);
END;
/
```

```text
Function created.

ERROR:
ORA-06502: PL/SQL: value or conversion error
ORA-06512: at "SA.TO_DAY", line 4

ERROR:
ORA-00942: table or view does not exist
ORA-06512: at line 2
```

### K. Nested subprograms

A function or procedure declared in the declarations of a unit is local to it, sees the unit's variables, may be
declared ahead and defined later, and may call itself. The last function calls a nested one from SQL inside the unit,
which is stored valid and fails when it runs.

<!-- example: oracle -->
```sql
CREATE FUNCTION fact (n NUMBER) RETURN NUMBER IS
  FUNCTION f (k NUMBER) RETURN NUMBER IS
  BEGIN
    IF k <= 1 THEN RETURN 1; END IF;
    RETURN k * f(k - 1);
  END;
BEGIN
  RETURN f(n);
END;
/
CREATE FUNCTION is_even (n NUMBER) RETURN NUMBER IS
  FUNCTION is_odd (k NUMBER) RETURN NUMBER;
  FUNCTION is_even2 (k NUMBER) RETURN NUMBER IS
  BEGIN
    IF k = 0 THEN RETURN 1; END IF;
    RETURN is_odd(k - 1);
  END;
  FUNCTION is_odd (k NUMBER) RETURN NUMBER IS
  BEGIN
    IF k = 0 THEN RETURN 0; END IF;
    RETURN is_even2(k - 1);
  END;
BEGIN
  RETURN is_even2(n);
END;
/
CREATE FUNCTION sum_to (n NUMBER) RETURN NUMBER IS
  total NUMBER := 0;
  PROCEDURE add_to (k NUMBER) IS
  BEGIN
    total := total + k;
  END;
BEGIN
  FOR i IN 1 .. n LOOP add_to(i); END LOOP;
  RETURN total;
END;
/
CREATE FUNCTION sql_calls_nested RETURN NUMBER IS
  r NUMBER;
  FUNCTION sq (x NUMBER) RETURN NUMBER IS BEGIN RETURN x * x; END;
BEGIN
  SELECT sq(3) INTO r FROM dual;
  RETURN r;
END;
/
SELECT fact(5) AS fact5, is_even(10) AS e10, is_even(7) AS e7, sum_to(4) AS s4 FROM dual;
SELECT status FROM user_objects WHERE object_name IN ('FACT', 'IS_EVEN', 'SUM_TO', 'SQL_CALLS_NESTED') ORDER BY object_name;
SELECT sql_calls_nested() FROM dual;
```

```text
Function created.

Function created.

Function created.

Function created.

FACT5 E10 E7 S4
----- --- -- --
  120   1  0 10

1 row selected.

STATUS
------
VALID
VALID
VALID
VALID

4 rows selected.

ERROR:
ORA-00904: invalid identifier
ORA-06512: at "SA.SQL_CALLS_NESTED", line 5
```

## See also

[CREATE PROCEDURE](create-procedure.md), [CREATE PACKAGE](create-package.md), [DROP FUNCTION](drop-function.md),
[CALL](call.md), [Functions](README.md#functions)
