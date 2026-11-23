# CREATE VIEW

Creates a view: a stored query that is read like a table.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE [ OR REPLACE ] [ NOFORCE ] VIEW [ schema. ] view [ ( alias [, alias ]... ) ] AS subquery
```

## Arguments

`OR REPLACE`
: Replaces a view of that name.

*alias*
: Names for the view's columns, in the order of the select list. Without them the columns have the names of the
  select list's expressions (give an alias to a computed column).

*subquery*
: Any query, with joins, grouping and subqueries.

## Remarks

- The query is checked when the view is created: a missing table is ORA-00942.
- A view is read like a table in `SELECT`, `JOIN` and other views. `USER_VIEWS` has its name and text, and
  `USER_TAB_COLUMNS` its columns.
- **Views are read-only in lexdb:** `INSERT`, `UPDATE` and `DELETE` through a view are ORA-03001.
- A view is dropped with [DROP VIEW](drop-view.md).

## Differences from Oracle

- **`INSERT`, `UPDATE` and `DELETE` through a view are not supported** (ORA-03001), including simple
  single-table views. Update the table.
- **`WITH READ ONLY` and `WITH CHECK OPTION` are refused** (ORA-03001, message `WITH CHECK OPTION is not supported`
  for both). Every view is read-only anyway.
- `FORCE` (a view over a table that does not exist yet) is ORA-00900; `NOFORCE` is the default and is accepted.
- `CREATE MATERIALIZED VIEW` is ORA-03001.

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

## See also

[DROP VIEW](drop-view.md), [SELECT](select.md), [CREATE TABLE](create-table.md)
