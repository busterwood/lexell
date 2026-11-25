# DROP TABLE

Removes a table, its rows, its indexes and its constraints.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
DROP TABLE [ IF EXISTS ] [ schema. ] table [ CASCADE CONSTRAINTS ] [ PURGE ]
```

## Arguments

`IF EXISTS`
: No error when the table does not exist (23ai).

`CASCADE CONSTRAINTS`
: Drops the foreign keys of other tables that point at this one. Without it, a table that others reference is
  ORA-02449.

`PURGE`
: Accepted. lexdb has no recycle bin, so every drop is final.

## Remarks

- The table's indexes, constraints and rows go with it.
- A table that does not exist is ORA-00942.
- A table that views read is dropped, as in Oracle: each view is `INVALID`, reading it is ORA-04063, and `USER_ERRORS`
  holds ORA-00942 for it (example E).
- To empty a table and keep it, use [TRUNCATE TABLE](truncate-table.md).

## Differences from Oracle

- `DROP TABLE` without `PURGE` does not keep the table in a recycle bin (no `FLASHBACK TABLE ... TO BEFORE DROP`).
- A view over a dropped table is `VALID` again as soon as a table of that name is made again; Oracle shows it
  `INVALID` until the view's next use (example E).

## Examples

### A. Drop a table

<!-- example: oracle -->
```sql
CREATE TABLE staff (id NUMBER);
DROP TABLE staff;
DROP TABLE staff;
```

```text
Table created.

Table dropped.

ERROR:
ORA-00942: table or view "SA"."STAFF" does not exist
```

### B. A table that other tables reference

<!-- example: oracle -->
```sql
CREATE TABLE p (id NUMBER PRIMARY KEY);
CREATE TABLE c (id NUMBER, p_id NUMBER REFERENCES p (id));
DROP TABLE p;
DROP TABLE p CASCADE CONSTRAINTS;
SELECT COUNT(*) AS foreign_keys_left FROM user_constraints WHERE table_name = 'C' AND constraint_type = 'R';
```

```text
Table created.

Table created.

ERROR:
ORA-02449: unique/primary keys in table referenced by foreign keys

Table dropped.

FOREIGN_KEYS_LEFT
-----------------
                0

1 row selected.
```

### C. PURGE

<!-- example: oracle -->
```sql
CREATE TABLE q (id NUMBER);
DROP TABLE q PURGE;
SELECT COUNT(*) AS q_left FROM user_tables WHERE table_name = 'Q';
```

```text
Table created.

Table dropped.

Q_LEFT
------
     0

1 row selected.
```

### D. IF EXISTS

<!-- example: oracle -->
```sql
DROP TABLE IF EXISTS nothere;
```

```text
Table dropped.
```

### E. A table under a view

<!-- example: oracle -->
```sql
CREATE TABLE dept (id NUMBER PRIMARY KEY, name VARCHAR2(20));
INSERT INTO dept VALUES (1, 'sales');
CREATE VIEW dept_names AS SELECT name FROM dept;
CREATE VIEW dept_upper AS SELECT UPPER(name) AS name FROM dept_names;
DROP TABLE dept;
SELECT object_name, status FROM user_objects WHERE object_type = 'VIEW' ORDER BY object_name;
SELECT * FROM dept_names;
SELECT name, type, TRIM(text) AS text FROM user_errors WHERE name = 'DEPT_NAMES';
CREATE TABLE dept (id NUMBER PRIMARY KEY, name VARCHAR2(20));
SELECT object_name, status FROM user_objects WHERE object_type = 'VIEW' ORDER BY object_name;
```

```text
Table created.

1 row created.

View created.

View created.

Table dropped.

OBJECT_NAME STATUS
----------- -------
DEPT_NAMES  INVALID
DEPT_UPPER  INVALID

2 rows selected.

ERROR:
ORA-04063: view "SA.DEPT_NAMES" has errors

NAME       TYPE TEXT
---------- ---- ---------------------------------------------------
DEPT_NAMES VIEW ORA-00942: table or view "SA"."DEPT" does not exist

1 row selected.

Table created.

OBJECT_NAME STATUS
----------- ------
DEPT_NAMES  VALID
DEPT_UPPER  VALID

2 rows selected.
```

## See also

[CREATE TABLE](create-table.md), [TRUNCATE TABLE](truncate-table.md), [ALTER TABLE](alter-table.md)
