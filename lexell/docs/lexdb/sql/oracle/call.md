# CALL and EXECUTE

Runs a stored procedure or function from a client.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CALL [ schema. ] { procedure | package.procedure } ( [ argument [, argument ]... ] ) [ INTO :bind ]
EXEC[UTE] { procedure | package.procedure } [ ( [ argument [, ...] ] ) ] ;
```

## Arguments

*argument*
: A value, by position, or `name => value` by name. An argument may be left out where the parameter has a default.

`EXEC`, `EXECUTE`
: A SQL\*Plus and SQLcl command: the client wraps the call in an anonymous block. lexdb takes it as a call too.

`INTO :bind`
: A client bind variable that receives a function's value.

## Remarks

- `CALL` and `EXEC` run a unit made with [CREATE PROCEDURE](create-procedure.md) or [CREATE PACKAGE](create-package.md).
  A procedure that prints with `DBMS_OUTPUT` shows its output before the client's confirmation.
- A unit that does not exist is ORA-06550 with PLS-00201 (`identifier ... must be declared`); a wrong number of
  arguments is PLS-00306.
- In a block, call a unit directly: `p(1);` or `pkg.p(1);`. An `OUT` argument may be a package variable
  (`p(pkg.v);`, see [CREATE PACKAGE](create-package.md), example G).

## Differences from Oracle

- `CALL` of a procedure that does not exist, or with the wrong arguments, is ORA-06550 with PLS-00201 or PLS-00306, as
  `EXEC` is in SQL\*Plus; Oracle's `CALL` statement itself says ORA-06576 (no such procedure) and ORA-06553 with PLS-306
  (wrong arguments), which a driver shows.
- `CALL` of a **function** without `INTO` is PLS-00201 (Oracle: ORA-06576); use `SELECT f() FROM dual` or a block.
- `OUT` binds work from a client that supplies them; the documentation's checker does not (`ORA-01008: not all
  variables bound`), so the examples call with variables inside a block instead.

## Examples

<!--setup: oracle
CREATE PROCEDURE hello (p_name VARCHAR2 DEFAULT 'world') AS
BEGIN
  DBMS_OUTPUT.PUT_LINE('hello ' || p_name);
END;
/
CREATE PACKAGE greeter AS
  PROCEDURE hi (p_name VARCHAR2);
END greeter;
/
CREATE PACKAGE BODY greeter AS
  PROCEDURE hi (p_name VARCHAR2) IS
  BEGIN
    DBMS_OUTPUT.PUT_LINE('hi ' || p_name);
  END;
END greeter;
/
-->

The examples use a procedure `hello (p_name DEFAULT 'world')` and a package `greeter` with a procedure `hi`.

### A. CALL and EXEC

<!-- example: oracle -->
```sql
CALL hello('ann');
CALL hello();
EXEC hello('bob');
EXECUTE hello;
CALL greeter.hi('cy');
EXEC greeter.hi('di');
```

```text
hello ann

PL/SQL procedure successfully completed.

hello world

PL/SQL procedure successfully completed.

hello bob

Statement processed.

hello world

Statement processed.

hi cy

PL/SQL procedure successfully completed.

hi di

Statement processed.
```

### B. Errors

<!-- example: oracle -->
```sql
CALL nothere();
CALL hello(1, 2);
EXEC nothere;
```

```text
ERROR:
ORA-06550: line 1, column 7:
PLS-00201: identifier 'NOTHERE' must be declared
ORA-06550: line 1, column 7:
PL/SQL: Statement ignored

ERROR:
ORA-06550: line 1, column 7:
PLS-00306: wrong number or types of arguments in call to 'HELLO'
ORA-06550: line 1, column 7:
PL/SQL: Statement ignored

ERROR:
ORA-06550: line 1, column 7:
PLS-00201: identifier 'NOTHERE' must be declared
ORA-06550: line 1, column 7:
PL/SQL: Statement ignored
```

## See also

[CREATE PROCEDURE](create-procedure.md), [CREATE FUNCTION](create-function.md), [CREATE PACKAGE](create-package.md),
[PL/SQL blocks](plsql-blocks.md)
