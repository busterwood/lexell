# PL/SQL exceptions

Handlers, predefined exceptions, user-defined exceptions, `RAISE`, `RAISE_APPLICATION_ERROR`, `SQLCODE` and `SQLERRM`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
EXCEPTION
    WHEN exception_name [ OR exception_name ]... THEN statements
    [ WHEN OTHERS THEN statements ]

name EXCEPTION ;
PRAGMA EXCEPTION_INIT ( name, error_number ) ;

RAISE name ;
RAISE ;                                 -- inside a handler: raise the same error again
RAISE_APPLICATION_ERROR ( error_number, message [, keep_errors ] ) ;
SQLCODE        SQLERRM
```

## Arguments

`WHEN ... THEN`
: Handles the named exceptions raised by the block's statements. The first handler that matches runs, and the block
  ends normally; an exception raised in a handler goes to the enclosing block. `OTHERS` matches every error.

*Predefined exceptions*
: `NO_DATA_FOUND` (ORA-01403), `TOO_MANY_ROWS` (ORA-01422), `ZERO_DIVIDE` (ORA-01476), `DUP_VAL_ON_INDEX`
  (ORA-00001), `INVALID_NUMBER` (ORA-01722), `VALUE_ERROR` (ORA-06502), `CURSOR_ALREADY_OPEN` (ORA-06511),
  `INVALID_CURSOR` (ORA-01001), `CASE_NOT_FOUND` (ORA-06592) and others.

*name* `EXCEPTION`
: Declares an exception of your own, raised with `RAISE`.

`PRAGMA EXCEPTION_INIT`
: Gives a declared exception an error number, so that a `WHEN` clause catches that error (an Oracle error or one from
  `RAISE_APPLICATION_ERROR`).

`RAISE_APPLICATION_ERROR`
: Raises an error with a number from -20000 to -20999 and a message, which a client receives as `ORA-20001: ...`.

`SQLCODE`, `SQLERRM`
: In a handler, the number of the error and its message (`ORA-01476: divisor is equal to zero`).

## Remarks

- An error that nothing handles ends the block, and the client sees it, followed by `ORA-06512: at line n` naming the
  line where it was raised.
- Statements that ran before the error stay: a block does not roll back by itself.
- A `SELECT ... INTO` that finds no row raises `NO_DATA_FOUND`; an `UPDATE` that changes no row does not.

## Differences from Oracle

- `TO_NUMBER('abc')` raises `VALUE_ERROR` (Oracle: `INVALID_NUMBER`).

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20));
INSERT INTO emp VALUES (1, 'ann');
COMMIT;
-->

The examples use a table `emp (id, name)` with one row.

### A. A predefined exception

<!-- example: oracle -->
```sql
DECLARE
  v NUMBER;
BEGIN
  SELECT id INTO v FROM emp WHERE id = 99;
EXCEPTION
  WHEN NO_DATA_FOUND THEN DBMS_OUTPUT.PUT_LINE('no data');
END;
/
BEGIN
  INSERT INTO emp VALUES (1, 'dup');
EXCEPTION
  WHEN DUP_VAL_ON_INDEX THEN DBMS_OUTPUT.PUT_LINE('dup val');
  WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('other ' || SQLCODE);
END;
/
```

```text
no data

PL/SQL procedure successfully completed.

dup val

PL/SQL procedure successfully completed.
```

### B. SQLCODE and SQLERRM, and your own error number

<!-- example: oracle -->
```sql
DECLARE
  e_custom EXCEPTION;
  PRAGMA EXCEPTION_INIT(e_custom, -20100);
  v NUMBER;
BEGIN
  BEGIN
    v := 1 / 0;
  EXCEPTION
    WHEN ZERO_DIVIDE THEN DBMS_OUTPUT.PUT_LINE('zero divide: ' || SQLERRM);
  END;
  RAISE_APPLICATION_ERROR(-20100, 'boom');
EXCEPTION
  WHEN e_custom THEN DBMS_OUTPUT.PUT_LINE('custom caught: ' || SQLCODE || ' ' || SQLERRM);
  WHEN OTHERS THEN DBMS_OUTPUT.PUT_LINE('others');
END;
/
```

```text
zero divide: ORA-01476: divisor is equal to zero
custom caught: -20100 ORA-20100: boom

PL/SQL procedure successfully completed.
```

### C. A user-defined exception

<!-- example: oracle -->
```sql
DECLARE
  my_err EXCEPTION;
BEGIN
  RAISE my_err;
EXCEPTION
  WHEN my_err THEN DBMS_OUTPUT.PUT_LINE('my_err');
END;
/
```

```text
my_err

PL/SQL procedure successfully completed.
```

### D. Errors that are not handled

<!-- example: oracle -->
```sql
BEGIN
  RAISE_APPLICATION_ERROR(-20001, 'custom');
END;
/
DECLARE
  v NUMBER;
BEGIN
  SELECT id INTO v FROM emp WHERE id = 99;
END;
/
```

```text
ERROR:
ORA-20001: custom
ORA-06512: at line 2

ERROR:
ORA-01403: no data found
ORA-06512: at line 4
```

### E. Raising again

<!-- example: oracle -->
```sql
BEGIN
  BEGIN
    INSERT INTO emp VALUES (1, 'dup');
  EXCEPTION
    WHEN OTHERS THEN
      DBMS_OUTPUT.PUT_LINE('inner: ' || SQLCODE);
      RAISE;
  END;
EXCEPTION
  WHEN DUP_VAL_ON_INDEX THEN DBMS_OUTPUT.PUT_LINE('outer: dup val');
END;
/
```

```text
inner: -1
outer: dup val

PL/SQL procedure successfully completed.
```

### F. A number that is not a number

<!-- example: oracle -->
```sql
DECLARE
  v NUMBER;
BEGIN
  v := TO_NUMBER('abc');
EXCEPTION
  WHEN INVALID_NUMBER THEN DBMS_OUTPUT.PUT_LINE('invalid number');
  WHEN VALUE_ERROR THEN DBMS_OUTPUT.PUT_LINE('value error');
END;
/
```

```text
value error

PL/SQL procedure successfully completed.
```

## See also

[PL/SQL blocks](plsql-blocks.md), [SQL in PL/SQL](plsql-sql.md), [Errors](errors.md)
