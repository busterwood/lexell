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
  included. Not supported: overloading them (the later declaration of a name is the one called) and calling one from SQL
  inside the block (ORA-00904 when it runs; Oracle: PLS-00231).
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

## See also

[Declarations](plsql-declarations.md), [Control statements](plsql-control.md), [SQL in PL/SQL](plsql-sql.md),
[Exceptions](plsql-exceptions.md), [CREATE PROCEDURE](create-procedure.md)
