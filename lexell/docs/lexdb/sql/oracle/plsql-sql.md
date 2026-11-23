# SQL in PL/SQL

`SELECT ... INTO`, DML with `RETURNING INTO`, `EXECUTE IMMEDIATE` and the transaction statements.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
SELECT expr [, ...] INTO variable [, ...] FROM ... ;

INSERT | UPDATE | DELETE ... RETURNING expr [, ...] INTO variable [, ...] ;

EXECUTE IMMEDIATE 'statement'
    [ INTO variable [, ...] ]
    [ USING [ IN | OUT | IN OUT ] value [, ...] ] ;

COMMIT ;   ROLLBACK [ TO savepoint ] ;   SAVEPOINT name ;
```

## Arguments

`SELECT ... INTO`
: Reads one row into variables. No row is `NO_DATA_FOUND` (ORA-01403) and more than one is `TOO_MANY_ROWS`
  (ORA-01422). Without `INTO` a `SELECT` in a block is PLS-00428.

`RETURNING ... INTO`
: Puts the values of the row an `INSERT`, `UPDATE` or `DELETE` changed into variables.

`EXECUTE IMMEDIATE`
: Runs a statement built as a string, including DDL, with bind values by position (`:1`, `:name`) in `USING`. `INTO`
  reads a one-row query's result. An `OUT` bind returns a value.

`COMMIT`, `ROLLBACK`, `SAVEPOINT`
: As in SQL: see [COMMIT](commit.md), [ROLLBACK](rollback.md), [SAVEPOINT](savepoint.md).

## Remarks

- A variable in a SQL statement is a bind: `WHERE id = v_id` uses the value of `v_id`.
- DDL (`CREATE TABLE`, ...) is not allowed directly in a block (PLS-00103): write it in `EXECUTE IMMEDIATE`.
- `SQL%ROWCOUNT` and the other implicit cursor attributes describe the last statement: see [cursors](plsql-cursors.md).
- `EXECUTE IMMEDIATE` with a bad statement raises the SQL error (for example ORA-00942).

## Differences from Oracle

- `RETURNING ... BULK COLLECT INTO`, `FORALL` and `SELECT ... BULK COLLECT INTO` are not supported.
- `LOCK TABLE` in a block is ORA-00900.

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), salary NUMBER(8,2));
INSERT INTO emp VALUES (1, 'ann', 100);
INSERT INTO emp VALUES (2, 'bob', 200);
INSERT INTO emp VALUES (3, 'cy', 300);
COMMIT;
-->

The examples use a table `emp (id, name, salary)` with three rows: ann 100, bob 200, cy 300.

### A. SELECT INTO

<!-- example: oracle -->
```sql
DECLARE
  v_name VARCHAR2(20);
  v_total NUMBER;
BEGIN
  SELECT name INTO v_name FROM emp WHERE id = 2;
  SELECT SUM(salary) INTO v_total FROM emp;
  DBMS_OUTPUT.PUT_LINE(v_name || ' ' || v_total);
END;
/
```

```text
bob 600

PL/SQL procedure successfully completed.
```

### B. RETURNING INTO

<!-- example: oracle -->
```sql
DECLARE
  v_id NUMBER;
  v_salary NUMBER;
BEGIN
  INSERT INTO emp VALUES (4, 'di', 400) RETURNING id INTO v_id;
  UPDATE emp SET salary = salary * 2 WHERE id = 4 RETURNING salary INTO v_salary;
  DBMS_OUTPUT.PUT_LINE('inserted ' || v_id || ', salary now ' || v_salary);
  ROLLBACK;
END;
/
```

```text
inserted 4, salary now 800

PL/SQL procedure successfully completed.
```

### C. Dynamic SQL

<!-- example: oracle -->
```sql
BEGIN
  EXECUTE IMMEDIATE 'CREATE TABLE dyn (a NUMBER)';
  EXECUTE IMMEDIATE 'INSERT INTO dyn VALUES (:1)' USING 42;
  DECLARE
    n NUMBER;
  BEGIN
    EXECUTE IMMEDIATE 'SELECT a FROM dyn' INTO n;
    DBMS_OUTPUT.PUT_LINE('dyn ' || n);
  END;
END;
/
```

```text
dyn 42

PL/SQL procedure successfully completed.
```

### D. Errors

<!-- example: oracle -->
```sql
DECLARE
  v NUMBER;
BEGIN
  SELECT id INTO v FROM emp WHERE id = 99;
END;
/
DECLARE
  v NUMBER;
BEGIN
  SELECT id INTO v FROM emp;
END;
/
BEGIN
  EXECUTE IMMEDIATE 'SELECT * FROM nothere';
END;
/
BEGIN
  SELECT 1 FROM dual;
END;
/
```

```text
ERROR:
ORA-01403: no data found
ORA-06512: at line 4

ERROR:
ORA-01422: exact fetch returned more than the requested number of rows
ORA-06512: at line 4

ERROR:
ORA-00942: table or view does not exist
ORA-06512: at line 2

ERROR:
ORA-06550: line 2, column 3:
PLS-00428: an INTO clause is expected in this SELECT statement
```

## See also

[PL/SQL blocks](plsql-blocks.md), [Cursors](plsql-cursors.md), [Exceptions](plsql-exceptions.md),
[INSERT](insert.md)
