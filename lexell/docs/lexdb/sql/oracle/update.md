# UPDATE

Changes the values of columns in the rows of a table.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
UPDATE [ schema. ] table [ t_alias ]
    SET { column = { expr | DEFAULT }
        | ( column [, column ]... ) = ( { expr | DEFAULT } [, ...] ) } [, ...]
    [ WHERE condition ]
    [ returning_clause ]

returning_clause:
    { RETURN | RETURNING } [ OLD | NEW ] expr [, [ OLD | NEW ] expr ]...
        INTO data_item [, data_item ]...
```

## Arguments

*schema*
: The owner of the table. Without it, the session's current schema is used.

*t_alias*
: A name for the table, usable in `SET`, `WHERE` and `RETURNING`. `SET e.salary = ...` may name the column through
  the alias.

`SET` *column* `=` *expr*
: Gives the column a new value. The expression may use the row's old values, other tables' columns through a
  subquery, and `DEFAULT`. All the new values are worked out from the old row, so `SET a = b, b = a` swaps.

`SET (` *columns* `) = (` *values* `)`
: Several columns at once, from a list of expressions of the same length.

*expr* as a subquery
: `SET col = ( SELECT ... )` takes the value from a query that returns one column and at most one row; no row gives
  NULL, more than one row is ORA-01427. The query may use the columns of the row being updated (a correlated
  update).

`WHERE`
: The rows to change. Without it every row changes. A subquery in it may read the table being updated.

*returning_clause*
: Returns values of the changed row into PL/SQL variables or bind variables. `OLD` and `NEW` (23ai) name the row
  before and after the change; a plain column is the new value. If a statement changes more than one row, a
  scalar variable is ORA-01422.

## Remarks

- The result is `N rows updated.`; in PL/SQL `SQL%ROWCOUNT` gives the count and `SQL%FOUND` tells whether any row
  changed.
- The first `UPDATE` begins a transaction, which `COMMIT` or `ROLLBACK` ends. A statement that fails is undone alone.
- A value is converted to its column's type, and constraints are checked: ORA-00001 (unique), ORA-01407 (a `NOT
  NULL` column set to NULL), ORA-02290 (check), ORA-02291 (no parent key), ORA-02292 (a parent key that has children),
  ORA-01438 (a number too large), ORA-12899 (a string too long).
- Setting a `NOT NULL` column to `''` is ORA-01407, because the empty string is NULL.
- On a replica, `UPDATE` of a table is ORA-16000; global temporary tables can be updated.

## Differences from Oracle

- A subquery in `SET` that reads the table being updated sees the rows the statement has already changed, where Oracle
  gives each row the table as it was when the statement began (example G).
- `SET (col1, col2) = (SELECT ...)`, a column list set from a subquery, is not supported (ORA-00900); use one
  `SET col = (SELECT ...)` for each column. A list set from values, `SET (a, b) = (1, 2)`, works.
- `UPDATE (subquery) SET ...` (updatable inline views) and `UPDATE ... PARTITION`, `LOG ERRORS`, `WHERE CURRENT OF`
  and `ORDER BY` are not supported (ORA-00900).
- `ROWNUM` in the `WHERE` clause of `UPDATE` is not supported (ORA-20000, "window functions are not allowed in
  UPDATE"). Select the keys in a subquery, `WHERE id IN (SELECT id FROM t FETCH FIRST 2 ROWS ONLY)`.
- `UPDATE ... FROM table` (PostgreSQL's and T-SQL's join form) is accepted; Oracle refuses it. Use a correlated
  subquery or `MERGE`.
- `RETURNING ... BULK COLLECT INTO` is not supported, as PL/SQL collections are not. `RETURNING` from a client's
  bind variables (`RETURNING salary INTO :s`) needs a client that binds them.
- Error texts are shorter than Oracle's: ORA-01407 names the column, but ORA-02290 names no constraint and
  ORA-02291 no constraint name.
- Hints are read as comments.

## Examples

<!--setup: oracle
CREATE TABLE dept (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL);
CREATE TABLE emp (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL, dept_id NUMBER(4) REFERENCES dept (id), mgr_id NUMBER(4), salary NUMBER(8,2), hired DATE);
INSERT INTO dept VALUES (1, 'Sales');
INSERT INTO dept VALUES (2, 'Research');
INSERT INTO dept VALUES (3, 'Legal');
INSERT INTO emp VALUES (1, 'Ann', 1, NULL, 5200, DATE '2019-03-01');
INSERT INTO emp VALUES (2, 'Bob', 1, 1, 4100, DATE '2021-07-15');
INSERT INTO emp VALUES (3, 'Cid', 2, 1, 6100, DATE '2018-01-10');
INSERT INTO emp VALUES (4, 'Dee', 2, 3, 6100, DATE '2022-05-02');
INSERT INTO emp VALUES (5, 'Eve', NULL, 3, 3000, DATE '2024-09-30');
COMMIT;
-->

The examples use the `emp` and `dept` tables of [SELECT](select.md). Each example ends with `ROLLBACK`, so the next
starts from the same rows.

### A. Change columns of some rows

<!-- example: oracle -->
```sql
UPDATE emp SET salary = salary * 1.1 WHERE dept_id = 1;
UPDATE emp SET salary = 5000, mgr_id = 1 WHERE name = 'Eve';
UPDATE emp SET (salary, mgr_id) = (7000, 2) WHERE name = 'Dee';
UPDATE emp SET salary = 1 WHERE 1 = 0;
SELECT name, mgr_id, salary FROM emp ORDER BY id;
ROLLBACK;
```

```text
2 rows updated.

1 row updated.

1 row updated.

0 rows updated.

NAME MGR_ID SALARY
---- ------ ------
Ann           5720
Bob       1   4510
Cid       1   6100
Dee       2   7000
Eve       1   5000

5 rows selected.

Rollback complete.
```

### B. UPDATE with a subquery

<!-- example: oracle -->
```sql
UPDATE emp SET salary = salary + 100 WHERE id IN (SELECT id FROM emp WHERE dept_id = (SELECT id FROM dept WHERE name = 'Sales'));
UPDATE emp SET dept_id = (SELECT id FROM dept WHERE name = 'Legal') WHERE name = 'Eve';
UPDATE emp SET salary = salary - 50 WHERE salary > (SELECT AVG(salary) FROM emp);
SELECT name, dept_id, salary FROM emp ORDER BY id;
ROLLBACK;
```

```text
2 rows updated.

1 row updated.

3 rows updated.

NAME DEPT_ID SALARY
---- ------- ------
Ann        1   5250
Bob        1   4200
Cid        2   6050
Dee        2   6050
Eve        3   3000

5 rows selected.

Rollback complete.
```

### C. A correlated SET

Each row takes a value computed from its own row, through the alias.

<!-- example: oracle -->
```sql
UPDATE emp e SET e.salary = (SELECT MAX(x.salary) FROM emp x WHERE x.dept_id = e.dept_id) WHERE e.dept_id = 2;
UPDATE emp e SET e.name = (SELECT d.name FROM dept d WHERE d.id = e.dept_id) WHERE e.id = 1;
SELECT id, name, salary FROM emp ORDER BY id;
ROLLBACK;
```

```text
2 rows updated.

1 row updated.

ID NAME  SALARY
-- ----- ------
 1 Sales   5200
 2 Bob     4100
 3 Cid     6100
 4 Dee     6100
 5 Eve     3000

5 rows selected.

Rollback complete.
```

### D. NULL, DEFAULT and expressions

<!-- example: oracle -->
```sql
UPDATE emp SET salary = NULL WHERE id = 5;
UPDATE emp SET salary = DEFAULT WHERE id = 5;
UPDATE emp SET salary = NVL(salary, 0) + 1, name = UPPER(name) WHERE dept_id IS NULL;
SELECT name, salary FROM emp WHERE id = 5;
ROLLBACK;
```

```text
1 row updated.

1 row updated.

1 row updated.

NAME SALARY
---- ------
EVE       1

1 row selected.

Rollback complete.
```

### E. RETURNING INTO in PL/SQL

<!-- example: oracle -->
```sql
DECLARE
  new_sal emp.salary%TYPE;
  old_sal emp.salary%TYPE;
  nm      emp.name%TYPE;
BEGIN
  UPDATE emp SET salary = salary + 500 WHERE id = 2 RETURNING salary INTO new_sal;
  DBMS_OUTPUT.PUT_LINE('new salary: ' || new_sal);
  UPDATE emp SET salary = salary + 500 WHERE id = 2 RETURNING OLD salary, NEW salary, name INTO old_sal, new_sal, nm;
  DBMS_OUTPUT.PUT_LINE(nm || ': ' || old_sal || ' -> ' || new_sal);
  DBMS_OUTPUT.PUT_LINE('rows: ' || SQL%ROWCOUNT);
  UPDATE emp SET salary = salary WHERE id = 99;
  IF SQL%NOTFOUND THEN DBMS_OUTPUT.PUT_LINE('no row 99'); END IF;
  ROLLBACK;
END;
/
```

```text
new salary: 4600
Bob: 4600 -> 5100
rows: 1
no row 99

PL/SQL procedure successfully completed.
```

### F. Errors

<!-- example: oracle -->
```sql
UPDATE emp SET name = '' WHERE id = 5;
UPDATE emp SET id = 1 WHERE id = 2;
UPDATE emp SET dept_id = 99 WHERE id = 2;
UPDATE emp SET salary = 123456789 WHERE id = 2;
UPDATE emp SET nosuch = 1;
UPDATE nosuch SET a = 1;
UPDATE emp SET salary = (SELECT d.id FROM dept d WHERE d.id > 0) WHERE id = 1;
DECLARE
  sal emp.salary%TYPE;
BEGIN
  UPDATE emp SET salary = salary + 1 WHERE dept_id = 1 RETURNING salary INTO sal;
END;
/
ROLLBACK;
```

```text
ERROR:
ORA-01407: cannot update ("SA"."EMP"."NAME") to NULL

ERROR:
ORA-00001: unique constraint (SA.EMP_PKEY) violated

ERROR:
ORA-02291: integrity constraint violated - parent key not found

ERROR:
ORA-01438: value larger than specified precision allowed for this column

ERROR:
ORA-00904: "NOSUCH": invalid identifier

ERROR:
ORA-00942: table or view "SA"."NOSUCH" does not exist

ERROR:
ORA-01427: single-row subquery returns more than one row

ERROR:
ORA-01422: exact fetch returned more than the requested number of rows
ORA-06512: at line 4

Rollback complete.
```

### G. A subquery that reads the table being updated

Each row takes twice its manager's salary. Oracle reads the table as it was when the statement began, so Dee and Eve
get 12200 (twice Cid's old 6100). lexdb reads the rows the statement has already changed, so they get 20800 (twice
Cid's new 10400).

<!-- example: oracle -->
```sql
UPDATE emp e SET salary = (SELECT salary * 2 FROM emp x WHERE x.id = e.mgr_id) WHERE mgr_id IS NOT NULL;
SELECT id, name, salary FROM emp ORDER BY id;
ROLLBACK;
```

```text
4 rows updated.

ID NAME SALARY
-- ---- ------
 1 Ann    5200
 2 Bob   10400
 3 Cid   10400
 4 Dee   20800
 5 Eve   20800

5 rows selected.

Rollback complete.
```

### H. What lexdb does not take

<!-- example: oracle -->
```sql
UPDATE emp SET (salary, mgr_id) = (SELECT 7000, 2 FROM dual) WHERE name = 'Dee';
UPDATE (SELECT salary FROM emp WHERE id = 1) SET salary = 1;
UPDATE emp SET salary = salary + 1 WHERE ROWNUM <= 2;
UPDATE emp SET salary = salary + 1 WHERE id = 1 LOG ERRORS INTO errlog;
UPDATE emp SET salary = 1 WHERE CURRENT OF c1;
```

```text
ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-20000: window functions are not allowed in UPDATE

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement
```

## See also

[INSERT](insert.md) · [DELETE](delete.md) · [MERGE](merge.md) · [SELECT](select.md) · [PL/SQL blocks](plsql-blocks.md)
