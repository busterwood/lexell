# RENAME

Renames a table, view or sequence.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
RENAME old_name TO new_name
```

## Remarks

- The object keeps its rows, indexes and constraints; views that read a renamed table are not rewritten.
- A name already taken is ORA-00955; an object that does not exist is ORA-00942.
- To rename a table with `ALTER TABLE`, see [ALTER TABLE](alter-table.md); a column is renamed with `ALTER TABLE ...
  RENAME COLUMN`.
- The client prints `Statement processed.` after a rename: that is JDBC's message, not Oracle's `Table renamed.`.

## Differences from Oracle

- A missing object is ORA-00942, where Oracle gives ORA-04043.

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), dept NUMBER);
INSERT INTO emp VALUES (1, 'ann', 1);
CREATE VIEW v_dept AS SELECT dept, COUNT(*) AS n FROM emp GROUP BY dept;
-->

The examples use a table `emp` and a view `v_dept` over it.

### A. Rename a table and a view

<!-- example: oracle -->
```sql
RENAME emp TO staff;
SELECT COUNT(*) AS staff_rows FROM staff;
RENAME v_dept TO v_dept2;
SELECT view_name FROM user_views;
```

```text
Statement processed.

STAFF_ROWS
----------
         1

1 row selected.

Statement processed.

VIEW_NAME
---------
V_DEPT2

1 row selected.
```

### B. Errors

<!-- example: oracle -->
```sql
RENAME nothere TO x;
RENAME staff TO v_dept2;
```

```text
ERROR:
ORA-00942: table or view "SA"."NOTHERE" does not exist

ERROR:
ORA-00955: name is already used by an existing object
```

## See also

[ALTER TABLE](alter-table.md), [CREATE TABLE](create-table.md)
