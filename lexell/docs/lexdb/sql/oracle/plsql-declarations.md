# PL/SQL declarations

Variables, constants, `%TYPE`, `%ROWTYPE`, records and the PL/SQL types.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
variable [ CONSTANT ] datatype [ NOT NULL ] [ { := | DEFAULT } expr ] ;
variable table.column%TYPE ;
variable other_variable%TYPE ;
variable table%ROWTYPE ;
TYPE record_type IS RECORD ( field datatype [, field datatype ]... ) ;
TYPE ref_cursor_type IS REF CURSOR ;
CURSOR name [ ( parameter datatype [, ...] ) ] IS select ;
exception EXCEPTION ;
PRAGMA EXCEPTION_INIT ( exception, error_number ) ;
```

## Arguments

*datatype*
: A SQL type (`NUMBER`, `VARCHAR2(n)`, `DATE`, `TIMESTAMP`, `CLOB`, `RAW`, ...) or a PL/SQL type: `BOOLEAN`,
  `PLS_INTEGER`, `BINARY_INTEGER`, `NATURAL`, `NATURALN`, `POSITIVE`, `POSITIVEN`, `SIGNTYPE`, `SIMPLE_INTEGER`,
  `STRING`, `SYS_REFCURSOR`. See the [type pages](README.md#data-types).

`CONSTANT`
: A variable that cannot be assigned to; it needs a value.

`NOT NULL`
: The variable must always have a value, and needs one at declaration.

`%TYPE`
: The type of a column or of another variable.

`%ROWTYPE`
: A record with a field for each column of a table: `v.name` reads one.

`TYPE ... IS RECORD`
: A record type with named fields. A record variable's fields are read and assigned as `r.field`; a whole record may
  be assigned from another of the same type or filled by `SELECT ... INTO`.

`TYPE ... IS REF CURSOR`, `SYS_REFCURSOR`
: A cursor variable: see [cursors](plsql-cursors.md).

`EXCEPTION`, `PRAGMA EXCEPTION_INIT`
: A named exception, and the binding of a name to an error number: see [exceptions](plsql-exceptions.md).

## Remarks

- Declarations come after `DECLARE` (or after `IS` / `AS` in a stored unit) and before `BEGIN`.
- A variable has the value NULL until assigned, unless it has an initial value.
- `:=` assigns. Names are case-insensitive.

## Differences from Oracle

- **Collection types** (`TABLE OF`, `VARRAY`, associative arrays) are not supported: PLS-00103.
- `TO_NUMBER('abc')` raises `VALUE_ERROR` here, where Oracle raises `INVALID_NUMBER` (ORA-01722).

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), salary NUMBER(8,2));
INSERT INTO emp VALUES (1, 'ann', 100);
INSERT INTO emp VALUES (2, 'bob', 200);
INSERT INTO emp VALUES (3, 'cy', 300);
COMMIT;
-->

The examples use a table `emp (id, name, salary)` with three rows: ann 100, bob 200, cy 300.

### A. Variables and constants

<!-- example: oracle -->
```sql
DECLARE
  v_name VARCHAR2(20) := 'ann';
  v_n NUMBER DEFAULT 5;
  c_pi CONSTANT NUMBER := 3.14;
  v_nn NUMBER NOT NULL := 1;
  v_d DATE := DATE '2026-03-15';
  v_b BOOLEAN := TRUE;
  v_p PLS_INTEGER := 7;
BEGIN
  DBMS_OUTPUT.PUT_LINE(v_name || ' ' || v_n || ' ' || c_pi || ' ' || v_nn || ' ' || TO_CHAR(v_d, 'YYYY-MM-DD'));
  v_n := v_n * 2;
  DBMS_OUTPUT.PUT_LINE('n=' || v_n || ' p=' || v_p);
  IF v_b THEN DBMS_OUTPUT.PUT_LINE('boolean true'); END IF;
END;
/
```

```text
ann 5 3.14 1 2026-03-15
n=10 p=7
boolean true

PL/SQL procedure successfully completed.
```

### B. %TYPE, %ROWTYPE and records

<!-- example: oracle -->
```sql
DECLARE
  v_name emp.name%TYPE;
  v_other v_name%TYPE := 'copy';
  v_row emp%ROWTYPE;
  TYPE rec_t IS RECORD (id NUMBER, label VARCHAR2(10));
  r rec_t;
BEGIN
  SELECT name INTO v_name FROM emp WHERE id = 1;
  SELECT * INTO v_row FROM emp WHERE id = 2;
  r.id := 7;
  r.label := 'seven';
  DBMS_OUTPUT.PUT_LINE(v_name || ' ' || v_other || ' ' || v_row.name || ' ' || v_row.salary || ' ' || r.id || ' ' || r.label);
END;
/
```

```text
ann copy bob 200 7 seven

PL/SQL procedure successfully completed.
```

### C. A constant cannot be assigned

<!-- example: oracle -->
```sql
DECLARE
  c CONSTANT NUMBER := 1;
BEGIN
  c := 2;
END;
/
```

```text
ERROR:
ORA-06550: line 4, column 3:
PLS-00363: expression 'C' cannot be used as an assignment target
```

### D. Collections are not supported

<!-- example: oracle -->
```sql
DECLARE
  TYPE nums IS TABLE OF NUMBER;
BEGIN
  NULL;
END;
/
```

```text
ERROR:
ORA-06550: line 2, column 3:
PLS-00103: collection types are not supported
```

## See also

[PL/SQL blocks](plsql-blocks.md), [Cursors](plsql-cursors.md), [Exceptions](plsql-exceptions.md),
[Numeric types](data-types-number.md)
