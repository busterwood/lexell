# DELETE

Removes rows from a table.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DELETE [ FROM ] [ schema. ] table [ t_alias ]
    [ WHERE condition ]
    [ returning_clause ]

returning_clause:
    { RETURN | RETURNING } [ OLD ] expr [, [ OLD ] expr ]...
        INTO data_item [, data_item ]...
```

## Arguments

*schema*
: The owner of the table. Without it, the session's current schema is used.

*t_alias*
: A name for the table in `WHERE` and `RETURNING`.

`WHERE`
: The rows to remove. Without it every row goes. A subquery in it may read the table itself, and other tables.

*returning_clause*
: Returns values of the removed row into PL/SQL variables or bind variables. In a `DELETE` a column is its old
  value, so `OLD` is not needed. A statement that removes more than one row cannot return into scalar variables
  (ORA-01422).

## Remarks

- The result is `N rows deleted.`; in PL/SQL `SQL%ROWCOUNT` gives the count.
- `FROM` may be left out: `DELETE emp WHERE id = 4`.
- A row that another table's foreign key points at cannot be removed: ORA-02292. Remove the child rows first, or
  declare the key `ON DELETE CASCADE`.
- The first `DELETE` begins a transaction, which `COMMIT` or `ROLLBACK` ends. A statement that fails is undone alone.
- `DELETE` of every row of a large table is slower than `TRUNCATE TABLE`, which cannot be rolled back; see
  [TRUNCATE TABLE](truncate-table.md).
- On a replica, `DELETE` from a table is ORA-16000; global temporary tables can be used.

## Differences from Oracle

- `DELETE FROM (subquery)`, `PARTITION`, `LOG ERRORS` and `WHERE CURRENT OF` are not supported (ORA-00900).
- `ROWNUM` in the `WHERE` clause of `DELETE` is not supported (ORA-20000, "window functions are not allowed in
  DELETE"). Select the keys in a subquery: `WHERE id IN (SELECT id FROM t FETCH FIRST 2 ROWS ONLY)`.
- `DELETE FROM t USING u WHERE ...` (PostgreSQL's join form) is accepted; Oracle refuses it. Use `EXISTS` or `IN`.
- `RETURNING ... BULK COLLECT INTO` is not supported, as PL/SQL collections are not.
- A view cannot be deleted from (ORA-03001): lexdb's views are read-only.
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

The examples use the `emp` and `dept` tables of [SELECT](select.md). Each ends with `ROLLBACK`, so the next starts
from the same rows.

### A. Delete some rows

<!-- example: oracle -->
```sql
DELETE FROM emp WHERE id = 5;
DELETE emp WHERE id = 4;
DELETE FROM emp e WHERE e.salary < 4000;
DELETE FROM emp WHERE 1 = 0;
SELECT id, name FROM emp ORDER BY id;
ROLLBACK;
SELECT COUNT(*) AS n FROM emp;
```

```text
1 row deleted.

1 row deleted.

0 rows deleted.

0 rows deleted.

ID NAME
-- ----
 1 Ann
 2 Bob
 3 Cid

3 rows selected.

Rollback complete.

N
-
5

1 row selected.
```

### B. Delete with a subquery

<!-- example: oracle -->
```sql
DELETE FROM emp WHERE dept_id IN (SELECT id FROM dept WHERE name = 'Research');
DELETE FROM emp WHERE salary > (SELECT AVG(salary) FROM emp);
SELECT id, name FROM emp ORDER BY id;
ROLLBACK;
DELETE FROM emp WHERE EXISTS (SELECT 1 FROM dept d WHERE d.id = emp.dept_id AND d.name = 'Sales');
SELECT COUNT(*) AS n FROM emp;
ROLLBACK;
```

```text
2 rows deleted.

1 row deleted.

ID NAME
-- ----
 2 Bob
 5 Eve

2 rows selected.

Rollback complete.

2 rows deleted.

N
-
3

1 row selected.

Rollback complete.
```

### C. RETURNING INTO in PL/SQL

<!-- example: oracle -->
```sql
DECLARE
  nm  emp.name%TYPE;
  sal emp.salary%TYPE;
BEGIN
  DELETE FROM emp WHERE id = 2 RETURNING name, salary INTO nm, sal;
  DBMS_OUTPUT.PUT_LINE('deleted ' || nm || ' ' || sal);
  DBMS_OUTPUT.PUT_LINE('rows: ' || SQL%ROWCOUNT);
  DELETE FROM emp WHERE id = 99 RETURNING name INTO nm;
  DBMS_OUTPUT.PUT_LINE('rows: ' || SQL%ROWCOUNT);
  ROLLBACK;
END;
/
```

```text
deleted Bob 4100
rows: 1
rows: 0

PL/SQL procedure successfully completed.
```

### D. Foreign keys

<!-- example: oracle -->
```sql
DELETE FROM dept WHERE id = 1;
DELETE FROM dept WHERE id = 3;
DELETE FROM emp WHERE dept_id = 1;
DELETE FROM dept WHERE id = 1;
SELECT id FROM dept ORDER BY id;
ROLLBACK;
```

```text
ERROR:
ORA-02292: integrity constraint violated - child record found

1 row deleted.

2 rows deleted.

1 row deleted.

ID
--
 2

1 row selected.

Rollback complete.
```

### E. Errors and what lexdb does not take

<!-- example: oracle -->
```sql
DELETE FROM nosuch;
DELETE FROM emp WHERE nosuch = 1;
DELETE FROM emp WHERE ROWNUM <= 2;
DELETE FROM (SELECT * FROM emp) WHERE id = 1;
DELETE FROM emp WHERE id = 1 LOG ERRORS INTO errlog;
CREATE VIEW ev AS SELECT * FROM emp;
DELETE FROM ev WHERE id = 1;
ROLLBACK;
```

```text
ERROR:
ORA-00942: table or view "SA"."NOSUCH" does not exist

ERROR:
ORA-00904: "NOSUCH": invalid identifier

ERROR:
ORA-20000: window functions are not allowed in DELETE

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

View created.

ERROR:
ORA-03001: unimplemented feature: cannot delete from view "ev" (lexdb's views are read-only)

Rollback complete.
```

## See also

[TRUNCATE TABLE](truncate-table.md) · [INSERT](insert.md) · [UPDATE](update.md) · [MERGE](merge.md) · [SELECT](select.md)
