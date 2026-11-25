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
SELECT name FROM emp WHERE double_it(salary) > 250;
```

```text
Function created.

ANSWER DOUBLED
------ -------
    42     200
    42     400

2 rows selected.

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

## See also

[CREATE PROCEDURE](create-procedure.md), [CREATE PACKAGE](create-package.md), [DROP FUNCTION](drop-function.md),
[CALL](call.md), [Functions](README.md#functions)
