# Built-in packages: DBMS_OUTPUT and others

`DBMS_OUTPUT`, `DBMS_LOCK`, `DBMS_SESSION`, `DBMS_SQL`, `DBMS_UTILITY` and the packages that are accepted and ignored.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DBMS_OUTPUT.PUT_LINE ( text )
DBMS_OUTPUT.PUT ( text )
DBMS_OUTPUT.NEW_LINE
DBMS_OUTPUT.ENABLE [ ( buffer_size ) ]      DBMS_OUTPUT.DISABLE
DBMS_OUTPUT.GET_LINE ( line OUT, status OUT )
DBMS_OUTPUT.GET_LINES ( lines OUT, numlines IN OUT )

DBMS_LOCK.SLEEP ( seconds )
DBMS_SESSION.SLEEP ( seconds )
DBMS_SQL.RETURN_RESULT ( cursor )
DBMS_UTILITY.NAME_RESOLVE ( ... )
DBMS_MVIEW.REFRESH ( list [, method ] )

DBMS_APPLICATION_INFO.SET_MODULE ( module, action )     -- accepted, no effect
DBMS_STATS.GATHER_TABLE_STATS ( ... )                    -- accepted, no effect
DBMS_METADATA.SET_TRANSFORM_PARAM ( ... )                -- accepted, no effect
```

## Arguments

`DBMS_OUTPUT.PUT_LINE`, `PUT`, `NEW_LINE`
: Write text to the session's output buffer, which the client prints after the block. `PUT` leaves the line open
  until `NEW_LINE` or the next `PUT_LINE`. A number or date is converted to text; `PUT_LINE(NULL)` writes an empty
  line. (The checker prints the output as SQL\*Plus does with `SET SERVEROUTPUT ON`.)

`DBMS_OUTPUT.GET_LINE`, `GET_LINES`
: Read the buffer back into the program. `GET_LINE` sets *status* to 0 when it returned a line and 1 when the buffer
  is empty.

`DBMS_OUTPUT.ENABLE`, `DISABLE`
: Turn the output on and off.

`DBMS_LOCK.SLEEP`, `DBMS_SESSION.SLEEP`
: Wait for a number of seconds (fractions allowed).

`DBMS_SQL.RETURN_RESULT`
: Hands a cursor to the client as an implicit result set.

`DBMS_UTILITY.NAME_RESOLVE`
: Resolves a name to its schema and object.

`DBMS_MVIEW.REFRESH`
: Refreshes one or more [materialized views](create-materialized-view.md) named in a comma-separated *list*. The
  optional *method* string gives `'C'` (complete), `'F'` (fast), or `'?'` (force) per view.

*Others*
: `DBMS_APPLICATION_INFO.*`, `DBMS_SESSION.*` (other than `SLEEP`), `DBMS_STATS.*` and `DBMS_METADATA.SET_*` calls
  are accepted and do nothing. Any other package or procedure is PLS-00201 or PLS-00302.

## Remarks

- A client that does not turn output on (`SET SERVEROUTPUT ON` in SQL\*Plus, `DBMS_OUTPUT.ENABLE` in JDBC) sees none.

## Differences from Oracle

- Only the packages above exist in PL/SQL (and a few functions in SQL: see [functions](README.md#functions)).
  `UTL_FILE` and the others are PLS-00201 (example D).
- `DBMS_SQL.RETURN_RESULT` works with clients that read implicit results; the JDBC driver of the documentation's
  checker does not (ORA-17283).

## Examples

### A. DBMS_OUTPUT

<!-- example: oracle -->
```sql
BEGIN
  DBMS_OUTPUT.PUT('a');
  DBMS_OUTPUT.PUT('b');
  DBMS_OUTPUT.NEW_LINE;
  DBMS_OUTPUT.PUT_LINE('c');
  DBMS_OUTPUT.PUT_LINE(NULL);
  DBMS_OUTPUT.PUT_LINE(123);
END;
/
```

```text
ab
c

123

PL/SQL procedure successfully completed.
```

### B. GET_LINE

<!-- example: oracle -->
```sql
DECLARE
  l_line VARCHAR2(100);
  l_status NUMBER;
BEGIN
  DBMS_OUTPUT.PUT_LINE('x');
  DBMS_OUTPUT.GET_LINE(l_line, l_status);
  DBMS_OUTPUT.PUT_LINE('got: ' || l_line || ' status ' || l_status);
END;
/
```

```text
got: x status 0

PL/SQL procedure successfully completed.
```

### C. Sleeping, and packages that do nothing

<!-- example: oracle -->
```sql
BEGIN
  DBMS_LOCK.SLEEP(0.01);
  DBMS_SESSION.SLEEP(0.01);
  DBMS_APPLICATION_INFO.SET_MODULE('module', 'action');
  DBMS_OUTPUT.PUT_LINE('ok');
END;
/
```

```text
ok

PL/SQL procedure successfully completed.
```

### D. A package that does not exist

<!-- example: oracle -->
```sql
BEGIN
  UTL_FILE.PUT_LINE(NULL, 'x');
END;
/
```

```text
ERROR:
ORA-06550: line 2, column 3:
PLS-00201: identifier 'UTL_FILE.PUT_LINE' must be declared
ORA-06550: line 2, column 3:
PL/SQL: Statement ignored
```

## See also

[PL/SQL blocks](plsql-blocks.md), [Functions](README.md#functions)
