# PL/SQL blocks

An anonymous block: `DECLARE ... BEGIN ... EXCEPTION ... END`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
[ <<label>> ]
[ DECLARE
    declaration [ declaration ]... ]
BEGIN
    statement [ statement ]...
[ EXCEPTION
    WHEN exception [ OR exception ]... THEN statement [ statement ]...
  [ WHEN OTHERS THEN statement [ statement ]... ] ]
END [ label ] ;
```

## Arguments

`DECLARE`
: Variables, constants, types, cursors and exceptions that the block uses: see
  [declarations](plsql-declarations.md). A block that declares nothing starts at `BEGIN`.

`BEGIN ... END`
: The statements, each ended by `;`. At least one statement is needed: `NULL;` does nothing.

`EXCEPTION`
: The handlers: see [exceptions](plsql-exceptions.md).

*label*
: A name in `<< >>` before the block (or a loop), used by `EXIT label` and to qualify variables.

## Remarks

- A client sends a block as one unit. In SQL\*Plus and in the examples a line holding only `/` ends it.
- Blocks nest: a `BEGIN ... END` may appear wherever a statement can, with its own `DECLARE` and `EXCEPTION`. A name
  declared in an inner block hides one of an outer block (example B).
- `CALL` and `EXEC` (or `EXECUTE`) run a stored procedure and are shorthand for a block: see [CALL](call.md).
- A block can contain SQL statements (`SELECT ... INTO`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `COMMIT`,
  `ROLLBACK`, `SAVEPOINT`) and, through `EXECUTE IMMEDIATE`, any other statement: see [SQL in PL/SQL](plsql-sql.md).
- Output is written with `DBMS_OUTPUT.PUT_LINE`; the client prints it after the block (`SET SERVEROUTPUT ON` in
  SQL\*Plus).
- A compile error (ORA-06550) stops the block before it runs.

## Differences from Oracle

- `GOTO`, `FORALL`, `BULK COLLECT` and collection types are not supported (PLS-00103).
- Subprograms declared in `DECLARE` work (example D): forward declarations, recursion and the enclosing variables
  included. They may be overloaded (example F): a call picks one by the number, names and type families of its
  arguments, and one that more than one fits is PLS-00307, one that none fits PLS-00306 (ORA-06550 in a block, as in
  Oracle). Calling one from SQL inside the block is PLS-00231, also as ORA-06550.
- DDL cannot be written directly in a block; use `EXECUTE IMMEDIATE` (as Oracle requires).
- `LOCK TABLE` inside a block is ORA-00900.

## Examples

### A. The smallest block, and a block with a declaration

<!-- example: oracle -->
```sql
BEGIN
  DBMS_OUTPUT.PUT_LINE('hello');
END;
/
DECLARE
  v_name VARCHAR2(20) := 'ann';
BEGIN
  DBMS_OUTPUT.PUT_LINE('hello ' || v_name);
END;
/
```

```text
hello

PL/SQL procedure successfully completed.

hello ann

PL/SQL procedure successfully completed.
```

### B. Nested blocks

<!-- example: oracle -->
```sql
DECLARE
  a NUMBER := 1;
BEGIN
  DECLARE
    a NUMBER := 2;
  BEGIN
    DBMS_OUTPUT.PUT_LINE('inner ' || a);
  END;
  DBMS_OUTPUT.PUT_LINE('outer ' || a);
END;
/
```

```text
inner 2
outer 1

PL/SQL procedure successfully completed.
```

### C. A block with an error handler

<!-- example: oracle -->
```sql
BEGIN
  DBMS_OUTPUT.PUT_LINE(1 / 0);
EXCEPTION
  WHEN ZERO_DIVIDE THEN
    DBMS_OUTPUT.PUT_LINE('cannot divide by zero');
END;
/
```

```text
cannot divide by zero

PL/SQL procedure successfully completed.
```

### D. Subprograms in DECLARE

<!-- example: oracle -->
```sql
DECLARE
  total NUMBER := 0;
  PROCEDURE bump (k NUMBER) IS
  BEGIN
    total := total + k;
  END;
  FUNCTION twice (k NUMBER) RETURN NUMBER IS
  BEGIN
    RETURN 2 * k;
  END;
BEGIN
  bump(5);
  bump(twice(3));
  DBMS_OUTPUT.PUT_LINE('total ' || total);
END;
/
```

```text
total 11

PL/SQL procedure successfully completed.
```

### E. Compile errors

<!-- example: oracle -->
```sql
BEGIN
  NULL
END;
/
BEGIN
  GOTO done;
  <<done>> NULL;
END;
/
BEGIN
  LOCK TABLE nothere IN EXCLUSIVE MODE;
END;
/
```

```text
ERROR:
ORA-06550: line 3, column 1:
PLS-00103: Encountered the symbol "END" when expecting one of the following: ;

ERROR:
ORA-06550: line 2, column 3:
PLS-00103: GOTO is not supported

ERROR:
ORA-00900: invalid SQL statement
ORA-06512: at line 2
```

### F. Overloaded subprograms, and calling one from SQL

Subprograms of one name in `DECLARE` are told apart by their arguments. A call that two of them fit is PLS-00307, a call
that none fits PLS-00306, and a nested function named in a SQL statement of the block is PLS-00231; each stops the block
before it runs.

<!-- example: oracle -->
```sql
DECLARE
  PROCEDURE show (v NUMBER) IS BEGIN DBMS_OUTPUT.PUT_LINE('number ' || v); END;
  PROCEDURE show (v VARCHAR2) IS BEGIN DBMS_OUTPUT.PUT_LINE('text ' || v); END;
  PROCEDURE show (v NUMBER, w NUMBER) IS BEGIN DBMS_OUTPUT.PUT_LINE('sum ' || (v + w)); END;
BEGIN
  show(42);
  show('forty-two');
  show(40, 2);
END;
/
DECLARE
  PROCEDURE show (v NUMBER) IS BEGIN DBMS_OUTPUT.PUT_LINE('a ' || v); END;
  PROCEDURE show (w NUMBER) IS BEGIN DBMS_OUTPUT.PUT_LINE('b ' || w); END;
BEGIN
  show(1);
END;
/
DECLARE
  PROCEDURE show (v NUMBER) IS BEGIN DBMS_OUTPUT.PUT_LINE('a ' || v); END;
BEGIN
  show(1, 2);
END;
/
DECLARE
  r NUMBER;
  FUNCTION sq (x NUMBER) RETURN NUMBER IS BEGIN RETURN x * x; END;
BEGIN
  SELECT sq(3) INTO r FROM dual;
END;
/
```

```text
number 42
text forty-two
sum 42

PL/SQL procedure successfully completed.

ERROR:
ORA-06550: line 5, column 3:
PLS-00307: too many declarations of 'SHOW' match this call
ORA-06550: line 5, column 3:
PL/SQL: Statement ignored

ERROR:
ORA-06550: line 4, column 3:
PLS-00306: wrong number or types of arguments in call to 'SHOW'
ORA-06550: line 4, column 3:
PL/SQL: Statement ignored

ERROR:
ORA-06550: line 5, column 10:
PLS-00231: function 'SQ' may not be used in SQL
ORA-06550: line 5, column 10:
PL/SQL: ORA-03066: invalid PL/SQL expression
ORA-06550: line 5, column 3:
PL/SQL: SQL Statement ignored
```

### G. A named argument given twice

<!-- example: oracle -->
```sql
DECLARE
  FUNCTION add2 (a NUMBER, b NUMBER) RETURN NUMBER IS BEGIN RETURN a + b; END;
BEGIN
  DBMS_OUTPUT.PUT_LINE(add2(b => 2, a => 1));
  DBMS_OUTPUT.PUT_LINE(add2(a => 1, a => 2));
END;
/
```

```text
ERROR:
ORA-06550: line 5, column 24:
PLS-00703: multiple instances of named argument in list
ORA-06550: line 5, column 3:
PL/SQL: Statement ignored
```

## See also

[Declarations](plsql-declarations.md), [Control statements](plsql-control.md), [SQL in PL/SQL](plsql-sql.md),
[Exceptions](plsql-exceptions.md), [CREATE PROCEDURE](create-procedure.md)
