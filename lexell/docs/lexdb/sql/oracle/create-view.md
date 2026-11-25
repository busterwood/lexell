# CREATE VIEW

Creates a view: a stored query that is read like a table.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE [ OR REPLACE ] [ NOFORCE ] VIEW [ schema. ] view [ ( alias [ annotations_clause ] [, ...] ) ]
    [ annotations_clause ] AS subquery

ALTER VIEW [ schema. ] view annotations_clause
ALTER VIEW [ schema. ] view MODIFY ( column annotations_clause [, ...] )
ALTER VIEW [ schema. ] view { COMPILE | EDITIONABLE | NONEDITIONABLE }

annotations_clause:
    ANNOTATIONS ( [ ADD [ IF NOT EXISTS ] | DROP [ IF EXISTS ] | REPLACE ] name [ 'value' ] [, ...] )
```

## Arguments

`OR REPLACE`
: Replaces a view of that name.

*alias*
: Names for the view's columns, in the order of the select list. Without them the columns have the names of the
  select list's expressions (give an alias to a computed column).

*subquery*
: Any query, with joins, grouping and subqueries. It may call a stored function, a standalone one or a package's
  (example G).

`ANNOTATIONS`
: Names, with or without a value, kept for the view or one of its columns and shown in `USER_ANNOTATIONS_USAGE`
  (`OBJECT_TYPE` `VIEW`). `CREATE VIEW` adds them; `ALTER VIEW` adds, drops and replaces them. `CREATE OR REPLACE
  VIEW` keeps only the new statement's. Example F below; see also [annotations](annotations.md).

## Remarks

- The query is checked when the view is created: a missing table is ORA-00942.
- A view is read like a table in `SELECT`, `JOIN` and other views. `USER_VIEWS` has its name and text, and
  `USER_TAB_COLUMNS` its columns.
- **Views are read-only in lexdb:** `INSERT`, `UPDATE` and `DELETE` through a view are ORA-03001.
- A view that calls a stored function runs the function's current body each time it is read: `CREATE OR REPLACE
  FUNCTION` changes what the view gives. `USER_VIEWS.TEXT` shows the query as it was written.
- `ALTER VIEW ... COMPILE`, `EDITIONABLE` and `NONEDITIONABLE` are accepted and do nothing (example H). A view is
  renamed by [RENAME](rename.md): `ALTER VIEW ... RENAME TO` is ORA-00922, as in Oracle.
- A view is dropped with [DROP VIEW](drop-view.md).

## Differences from Oracle

- **`INSERT`, `UPDATE` and `DELETE` through a view are not supported** (ORA-03001), including simple
  single-table views. Update the table.
- **`WITH READ ONLY` and `WITH CHECK OPTION` are refused** (ORA-03001, message `WITH CHECK OPTION is not supported`
  for both). Every view is read-only anyway.
- `FORCE` (a view over a table that does not exist yet) is ORA-00900; `NOFORCE` is the default and is accepted.
- `CREATE MATERIALIZED VIEW` is ORA-03001.
- **A view that calls a stored function cannot be read by DML:** an `INSERT`, `UPDATE`, `DELETE` or `CREATE TABLE ...
  AS` that reads one is ORA-03001 (example G). A query reads it.
- After `DROP FUNCTION` (or `DROP PACKAGE`) of a function a view calls, reading the view is ORA-04063 (`view ... has
  errors`; ORA-04067 after `DROP PACKAGE BODY`), as in Oracle, but `USER_OBJECTS.STATUS` stays `VALID` (Oracle:
  `INVALID`), and a session that read the view before the drop gets ORA-00904 or ORA-00900 on its first read.
- `ALTER VIEW ... READ ONLY` is ORA-03001; Oracle gives ORA-42310 for a view that is not an editioning view.

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), salary NUMBER(8,2), dept NUMBER);
INSERT INTO emp VALUES (1, 'ann', 100, 1);
INSERT INTO emp VALUES (2, 'bob', 200, 1);
INSERT INTO emp VALUES (3, 'cy', 300, 2);
-->

The examples use a table `emp (id, name, salary, dept)` with three rows (ann 100 and bob 200 in department 1, cy
300 in department 2).

### A. A grouping view

<!-- example: oracle -->
```sql
CREATE VIEW v_dept AS SELECT dept, COUNT(*) AS n, SUM(salary) AS total FROM emp GROUP BY dept;
SELECT * FROM v_dept ORDER BY dept;
```

```text
View created.

DEPT N TOTAL
---- - -----
   1 2   300
   2 1   300

2 rows selected.
```

### B. Replace a view, and name its columns

<!-- example: oracle -->
```sql
CREATE OR REPLACE VIEW v_dept (d, cnt) AS SELECT dept, COUNT(*) FROM emp GROUP BY dept;
SELECT * FROM v_dept ORDER BY d;
SELECT view_name, text FROM user_views;
```

```text
View created.

D CNT
- ---
1   2
2   1

2 rows selected.

VIEW_NAME TEXT
--------- --------------------------------------------
V_DEPT    SELECT dept, COUNT(*) FROM emp GROUP BY dept

1 row selected.
```

### C. The columns of a view

<!-- example: oracle -->
```sql
CREATE VIEW v_cols AS SELECT id AS a, salary * 2 AS double_salary FROM emp;
SELECT column_name, data_type FROM user_tab_columns WHERE table_name = 'V_COLS' ORDER BY column_id;
```

```text
View created.

COLUMN_NAME   DATA_TYPE
------------- ---------
A             NUMBER
DOUBLE_SALARY NUMBER

2 rows selected.
```

### D. A view is read-only

<!-- example: oracle -->
```sql
CREATE VIEW v_up AS SELECT id, name FROM emp WHERE dept = 1;
INSERT INTO v_up VALUES (9, 'x');
UPDATE v_up SET name = 'ANN' WHERE id = 1;
DELETE FROM v_up WHERE id = 1;
SELECT name FROM emp WHERE id = 1;
```

```text
View created.

ERROR:
ORA-03001: unimplemented feature: cannot insert into view "v_up" (lexdb's views are read-only)

ERROR:
ORA-03001: unimplemented feature: cannot update view "v_up" (lexdb's views are read-only)

ERROR:
ORA-03001: unimplemented feature: cannot delete from view "v_up" (lexdb's views are read-only)

NAME
----
ann

1 row selected.
```

### E. Errors and refusals

<!-- example: oracle -->
```sql
CREATE VIEW v_bad AS SELECT * FROM nothere;
CREATE VIEW v_ro AS SELECT id, name FROM emp WITH READ ONLY;
CREATE VIEW v_ck AS SELECT id, dept FROM emp WHERE dept = 1 WITH CHECK OPTION;
CREATE FORCE VIEW v_force AS SELECT * FROM nothere;
CREATE MATERIALIZED VIEW mv AS SELECT * FROM emp;
```

```text
ERROR:
ORA-00942: table or view "SA"."NOTHERE" does not exist

ERROR:
ORA-03001: unimplemented feature: lexdb: WITH CHECK OPTION is not supported

ERROR:
ORA-03001: unimplemented feature: lexdb: WITH CHECK OPTION is not supported

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-03001: unimplemented feature: lexdb: CREATE MATERIALIZED is not supported yet (CREATE makes tables, views, indexes, schemas, sequences, types, roles and users)
```

### F. Annotations

<!-- example: oracle -->
```sql
CREATE VIEW v_pay (id, salary ANNOTATIONS (Unit 'EUR')) ANNOTATIONS (Purpose 'payroll', Restricted)
AS SELECT id, salary FROM emp;
ALTER VIEW v_pay ANNOTATIONS (REPLACE Purpose 'pay review', DROP Restricted);
ALTER VIEW v_pay MODIFY (id ANNOTATIONS (ADD Display 'Employee'));
SELECT column_name, annotation_name, annotation_value FROM user_annotations_usage
WHERE object_name = 'V_PAY' ORDER BY column_name NULLS FIRST, annotation_name;
ALTER VIEW v_pay ANNOTATIONS (DROP Restricted);
```

```text
View created.

View altered.

View altered.

COLUMN_NAME ANNOTATION_NAME ANNOTATION_VALUE
----------- --------------- ----------------
            PURPOSE         pay review
ID          DISPLAY         Employee
SALARY      UNIT            EUR

3 rows selected.

ERROR:
ORA-11553: Provided annotation 'RESTRICTED' does not exist for the object 'V_PAY'.
```

### G. A view that calls a stored function

<!-- example: oracle -->
```sql
CREATE FUNCTION bonus (sal NUMBER) RETURN NUMBER IS
BEGIN
  RETURN ROUND(sal * 0.1);
END;
/
CREATE VIEW v_bonus AS SELECT id, name, bonus(salary) AS bonus FROM emp WHERE bonus(salary) > 10;
SELECT * FROM v_bonus ORDER BY id;
SELECT text FROM user_views WHERE view_name = 'V_BONUS';
CREATE OR REPLACE FUNCTION bonus (sal NUMBER) RETURN NUMBER IS
BEGIN
  RETURN ROUND(sal * 0.2);
END;
/
SELECT id, bonus FROM v_bonus ORDER BY id;
CREATE TABLE bonus_copy AS SELECT * FROM v_bonus;
INSERT INTO emp (id, name, salary, dept) SELECT id + 10, name, bonus, 3 FROM v_bonus;
```

```text
Function created.

View created.

ID NAME BONUS
-- ---- -----
 2 bob     20
 3 cy      30

2 rows selected.

TEXT
-------------------------------------------------------------------------
SELECT id, name, bonus(salary) AS bonus FROM emp WHERE bonus(salary) > 10

1 row selected.

Function created.

ID BONUS
-- -----
 1    20
 2    40
 3    60

3 rows selected.

ERROR:
ORA-03001: unimplemented feature: lexdb: a view that calls a stored function is not supported in INSERT, UPDATE, DELETE and CREATE TABLE AS

ERROR:
ORA-03001: unimplemented feature: lexdb: a view that calls a stored function is not supported in INSERT, UPDATE, DELETE and CREATE TABLE AS
```

A function of a package works the same way:

<!-- example: oracle -->
```sql
CREATE PACKAGE pay IS
  FUNCTION grade (sal NUMBER) RETURN VARCHAR2;
END;
/
CREATE PACKAGE BODY pay IS
  FUNCTION grade (sal NUMBER) RETURN VARCHAR2 IS
  BEGIN
    RETURN CASE WHEN sal >= 200 THEN 'senior' ELSE 'junior' END;
  END;
END;
/
CREATE VIEW v_grade AS SELECT dept, pay.grade(salary) AS grade, COUNT(*) AS n FROM emp GROUP BY dept, pay.grade(salary);
SELECT * FROM v_grade ORDER BY dept, grade;
SELECT e.name, g.n FROM emp e JOIN v_grade g ON g.dept = e.dept AND g.grade = pay.grade(e.salary) ORDER BY e.id;
```

```text
Package created.

Package body created.

View created.

DEPT GRADE  N
---- ------ -
   1 junior 1
   1 senior 1
   2 senior 1

3 rows selected.

NAME N
---- -
ann  1
bob  1
cy   1

3 rows selected.
```

### H. ALTER VIEW

<!-- example: oracle -->
```sql
ALTER VIEW v_dept COMPILE;
ALTER VIEW v_dept EDITIONABLE;
ALTER VIEW v_dept RENAME TO v_depts;
ALTER VIEW v_dept READ ONLY;
ALTER VIEW emp COMPILE;
ALTER VIEW nothere COMPILE;
```

```text
View altered.

View altered.

ERROR:
ORA-00922: missing or invalid option

ERROR:
ORA-03001: unimplemented feature: lexdb: ALTER VIEW takes COMPILE, ANNOTATIONS, MODIFY and [NON]EDITIONABLE only

ERROR:
ORA-00942: table or view "SA"."EMP" does not exist

ERROR:
ORA-00942: table or view "SA"."NOTHERE" does not exist
```

## See also

[DROP VIEW](drop-view.md), [SELECT](select.md), [CREATE TABLE](create-table.md), [Annotations](annotations.md)
