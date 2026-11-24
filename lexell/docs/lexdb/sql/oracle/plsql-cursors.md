# PL/SQL cursors

Explicit cursors, cursor `FOR` loops, cursor variables (`REF CURSOR`) and the cursor attributes.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CURSOR name [ ( parameter datatype [, ...] ) ] IS select ;

OPEN name [ ( argument [, ...] ) ] ;
FETCH name INTO variable [, variable ]... ;
FETCH name INTO record ;
CLOSE name ;

FOR record IN name [ ( argument [, ...] ) ] LOOP ... END LOOP ;
FOR record IN ( select ) LOOP ... END LOOP ;

TYPE ref_type IS REF CURSOR ;
variable ref_type ;           variable SYS_REFCURSOR ;
OPEN variable FOR select ;
OPEN variable FOR 'dynamic select' [ USING value [, ...] ] ;

name%FOUND   name%NOTFOUND   name%ISOPEN   name%ROWCOUNT
SQL%FOUND    SQL%NOTFOUND    SQL%ISOPEN    SQL%ROWCOUNT
```

## Arguments

`CURSOR`
: Names a query, with optional parameters used in its `WHERE` clause.

`OPEN`, `FETCH`, `CLOSE`
: Start the query, read one row into variables or a record, and release it. `FETCH` past the last row leaves the
  variables as they were and sets `%NOTFOUND`.

`FOR record IN`
: Opens the cursor or query, fetches every row into *record* and closes it. The record's fields are the select
  list's column names.

`REF CURSOR`, `SYS_REFCURSOR`
: A variable that can hold any query: `OPEN rc FOR ...`. It may take a string for a dynamic query.

*cursor*`%FOUND`, `%NOTFOUND`, `%ISOPEN`, `%ROWCOUNT`
: Whether the last fetch returned a row, whether the cursor is open, and the number of rows fetched so far.

`SQL%`...
: The same for the last SQL statement run in the block; `SQL%ROWCOUNT` is the number of rows an `INSERT`, `UPDATE`
  or `DELETE` changed.

## Remarks

- A cursor must be closed before it is opened again (`CURSOR_ALREADY_OPEN`); using one that is not open is
  `INVALID_CURSOR`.
- `FETCH ... INTO` may name a package variable from outside the package (`FETCH c INTO pkg.v;`): see
  [CREATE PACKAGE](create-package.md), example G.
- A cursor `FOR` loop is the shortest way to read all rows: no `OPEN`, `FETCH`, `CLOSE` or `%NOTFOUND` test.
- A client reads the result of a `REF CURSOR` that an `OUT` parameter or a function returns: see
  [CREATE FUNCTION](create-function.md).

## Differences from Oracle

- `BULK COLLECT INTO`, `FETCH ... LIMIT` and cursor expressions are not supported (collections are not).
- `DBMS_SQL.RETURN_RESULT` accepts a cursor, but a JDBC client cannot read the implicit result set in the
  documentation's checker (ORA-17283); a client that supports implicit results (python-oracledb, SQLcl) can.

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), salary NUMBER(8,2));
INSERT INTO emp VALUES (1, 'ann', 100);
INSERT INTO emp VALUES (2, 'bob', 200);
INSERT INTO emp VALUES (3, 'cy', 300);
COMMIT;
-->

The examples use a table `emp (id, name, salary)` with three rows: ann 100, bob 200, cy 300.

### A. OPEN, FETCH, CLOSE

<!-- example: oracle -->
```sql
DECLARE
  CURSOR c IS SELECT id, name FROM emp ORDER BY id;
  v_id NUMBER;
  v_name VARCHAR2(20);
BEGIN
  OPEN c;
  LOOP
    FETCH c INTO v_id, v_name;
    EXIT WHEN c%NOTFOUND;
    DBMS_OUTPUT.PUT_LINE(c%ROWCOUNT || ' ' || v_id || ' ' || v_name);
  END LOOP;
  CLOSE c;
END;
/
```

```text
1 1 ann
2 2 bob
3 3 cy

PL/SQL procedure successfully completed.
```

### B. Cursor FOR loops, with parameters

<!-- example: oracle -->
```sql
DECLARE
  CURSOR c2 (p_min NUMBER) IS SELECT name FROM emp WHERE salary >= p_min ORDER BY id;
BEGIN
  FOR r IN c2(200) LOOP
    DBMS_OUTPUT.PUT_LINE('rich: ' || r.name);
  END LOOP;
  FOR r IN (SELECT name FROM emp WHERE id = 1) LOOP
    DBMS_OUTPUT.PUT_LINE('inline: ' || r.name);
  END LOOP;
END;
/
```

```text
rich: bob
rich: cy
inline: ann

PL/SQL procedure successfully completed.
```

### C. Cursor variables

<!-- example: oracle -->
```sql
DECLARE
  TYPE ref_t IS REF CURSOR;
  rc ref_t;
  sc SYS_REFCURSOR;
  v_name VARCHAR2(20);
BEGIN
  OPEN rc FOR SELECT name FROM emp WHERE id = 1;
  FETCH rc INTO v_name;
  DBMS_OUTPUT.PUT_LINE(v_name);
  CLOSE rc;
  OPEN sc FOR 'SELECT name FROM emp WHERE id = 2';
  FETCH sc INTO v_name;
  DBMS_OUTPUT.PUT_LINE(v_name);
  CLOSE sc;
END;
/
```

```text
ann
bob

PL/SQL procedure successfully completed.
```

### D. SQL% attributes

<!-- example: oracle -->
```sql
BEGIN
  UPDATE emp SET salary = salary + 1 WHERE id <= 2;
  DBMS_OUTPUT.PUT_LINE('updated ' || SQL%ROWCOUNT);
  DELETE FROM emp WHERE id = 99;
  DBMS_OUTPUT.PUT_LINE('found: ' || CASE WHEN SQL%FOUND THEN 'yes' ELSE 'no' END);
  ROLLBACK;
END;
/
```

```text
updated 2
found: no

PL/SQL procedure successfully completed.
```

## See also

[PL/SQL blocks](plsql-blocks.md), [SQL in PL/SQL](plsql-sql.md), [Control statements](plsql-control.md)
