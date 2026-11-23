# ALTER TABLE

Adds, changes and drops the columns and constraints of a table, and renames it or a column.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
ALTER TABLE [ schema. ] table
    { ADD ( column_definition [, column_definition ]... )
    | ADD column_definition
    | MODIFY ( column_modification [, ...] )
    | DROP COLUMN column
    | DROP ( column [, column ]... )
    | ADD [ CONSTRAINT name ] table_constraint
    | DROP CONSTRAINT name
    | RENAME COLUMN old TO new
    | RENAME TO new_table }

column_modification:
    column [ datatype ] [ DEFAULT expr ] [ NULL | NOT NULL ]
```

*column_definition* and *table_constraint* are as in [CREATE TABLE](create-table.md).

## Arguments

`ADD`
: Adds columns, with their defaults and constraints, or a constraint. A column with `DEFAULT` gives existing rows
  the default. A virtual column (`GENERATED ALWAYS AS (expr) VIRTUAL`) can be added.

`MODIFY`
: Changes a column's type or size, its default, or its `NULL` or `NOT NULL`. Several columns may be changed in one
  statement.

`DROP COLUMN`, `DROP (...)`
: Removes columns and their data.

`DROP CONSTRAINT`
: Removes a constraint by name.

`RENAME COLUMN`, `RENAME TO`
: Renames a column, or the table.

## Remarks

- Names in the statement are folded to upper case unless quoted.
- Each statement does one kind of change; several `ADD` or `MODIFY` definitions go in one pair of brackets.

## Differences from Oracle

- **Not supported (ORA-03001):** `ENABLE` and `DISABLE` of a constraint, `READ ONLY` and `READ WRITE`, and the other
  clauses of Oracle's `ALTER TABLE` (storage, partitions, `MOVE`, `SHRINK`, `ROW MOVEMENT`).
- `ALTER TABLE ... ALTER COLUMN` (T-SQL and PostgreSQL's form) is ORA-01735.

## Examples

<!--setup: oracle
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), salary NUMBER(8,2));
INSERT INTO emp VALUES (1, 'ann', 100);
-->

The examples use a table `emp`:

```sql
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), salary NUMBER(8,2));
INSERT INTO emp VALUES (1, 'ann', 100);
```

### A. Add columns

<!-- example: oracle -->
```sql
ALTER TABLE emp ADD (dept_id NUMBER(4), hired DATE DEFAULT DATE '2026-01-01');
SELECT column_name, data_type FROM user_tab_columns WHERE table_name = 'EMP' ORDER BY column_id;
SELECT TO_CHAR(hired, 'YYYY-MM-DD') AS hired FROM emp;
```

```text
Table altered.

COLUMN_NAME DATA_TYPE
----------- ---------
ID          NUMBER
NAME        VARCHAR2
SALARY      NUMBER
DEPT_ID     NUMBER
HIRED       DATE

5 rows selected.

HIRED
----------
2026-01-01

1 row selected.
```

### B. Modify columns

<!-- example: oracle -->
```sql
ALTER TABLE emp MODIFY (name VARCHAR2(50) NOT NULL, salary NUMBER(10,2));
SELECT column_name, data_type, data_length, nullable FROM user_tab_columns
WHERE table_name = 'EMP' AND column_name IN ('NAME', 'SALARY') ORDER BY column_name;
ALTER TABLE emp MODIFY (name NULL);
ALTER TABLE emp MODIFY (salary DEFAULT 0);
SELECT column_name, nullable FROM user_tab_columns WHERE table_name = 'EMP' AND column_name = 'NAME';
```

```text
Table altered.

COLUMN_NAME DATA_TYPE DATA_LENGTH NULLABLE
----------- --------- ----------- --------
NAME        VARCHAR2           50 N
SALARY      NUMBER             22 Y

2 rows selected.

Table altered.

Table altered.

COLUMN_NAME NULLABLE
----------- --------
NAME        Y

1 row selected.
```

### C. Constraints

<!-- example: oracle -->
```sql
ALTER TABLE emp ADD CONSTRAINT emp_sal_ck CHECK (salary >= 0);
ALTER TABLE emp ADD CONSTRAINT emp_name_uq UNIQUE (name);
INSERT INTO emp (id, name, salary) VALUES (2, 'bob', -1);
ALTER TABLE emp DROP CONSTRAINT emp_name_uq;
SELECT constraint_name, constraint_type FROM user_constraints WHERE table_name = 'EMP' ORDER BY constraint_name;
```

```text
Table altered.

Table altered.

ERROR:
ORA-02290: check constraint violated

Table altered.

CONSTRAINT_NAME CONSTRAINT_TYPE
--------------- ---------------
EMP_PKEY        P
EMP_SAL_CK      C

2 rows selected.
```

### D. Rename a column and the table

<!-- example: oracle -->
```sql
ALTER TABLE emp RENAME COLUMN name TO full_name;
ALTER TABLE emp RENAME TO staff;
SELECT table_name FROM user_tables;
SELECT column_name FROM user_tab_columns WHERE table_name = 'STAFF' ORDER BY column_id;
```

```text
Table altered.

Table altered.

TABLE_NAME
----------
STAFF

1 row selected.

COLUMN_NAME
-----------
ID
FULL_NAME
SALARY
DEPT_ID
HIRED

5 rows selected.
```

### E. Drop columns

<!-- example: oracle -->
```sql
ALTER TABLE staff DROP COLUMN hired;
ALTER TABLE staff DROP (dept_id);
SELECT column_name FROM user_tab_columns WHERE table_name = 'STAFF' ORDER BY column_id;
```

```text
Table altered.

Table altered.

COLUMN_NAME
-----------
ID
FULL_NAME
SALARY

3 rows selected.
```

### F. A virtual column added later

<!-- example: oracle -->
```sql
ALTER TABLE staff ADD (double_salary NUMBER GENERATED ALWAYS AS (salary * 2) VIRTUAL);
SELECT id, salary, double_salary FROM staff;
```

```text
Table altered.

ID SALARY DOUBLE_SALARY
-- ------ -------------
 1    100           200

1 row selected.
```

### G. Errors

<!-- example: oracle -->
```sql
ALTER TABLE nothere ADD (a NUMBER);
ALTER TABLE staff DROP COLUMN nothere;
ALTER TABLE staff ADD (full_name NUMBER);
ALTER TABLE staff ADD CONSTRAINT staff_fk FOREIGN KEY (id) REFERENCES nothere (id);
```

```text
ERROR:
ORA-00942: table or view "SA"."NOTHERE" does not exist

ERROR:
ORA-00904: "NOTHERE": invalid identifier

ERROR:
ORA-01430: column being added already exists in table

ERROR:
ORA-00942: table or view "SA"."NOTHERE" does not exist
```

### H. What lexdb does not take

<!-- example: oracle -->
```sql
ALTER TABLE staff DISABLE CONSTRAINT emp_sal_ck;
ALTER TABLE staff READ ONLY;
ALTER TABLE staff ALTER COLUMN salary SET DEFAULT 5;
```

```text
ERROR:
ORA-03001: unimplemented feature: lexdb: ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA

ERROR:
ORA-03001: unimplemented feature: lexdb: ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA

ERROR:
ORA-01735: invalid ALTER TABLE option
```

## See also

[CREATE TABLE](create-table.md), [DROP TABLE](drop-table.md), [RENAME](rename.md)
