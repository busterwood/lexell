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
    | ADD [ CONSTRAINT name ] table_constraint [ constraint_state ]
    | DROP CONSTRAINT name
    | { ENABLE | DISABLE } [ VALIDATE | NOVALIDATE ] CONSTRAINT name
    | MODIFY CONSTRAINT name constraint_state
    | RENAME COLUMN old TO new
    | RENAME TO new_table }

column_modification:
    column [ datatype ] [ DEFAULT expr ] [ NULL | NOT NULL ]

constraint_state:
    [ ENABLE | DISABLE ] [ VALIDATE | NOVALIDATE ] [ RELY | NORELY ]
```

*column_definition* and *table_constraint* are as in [CREATE TABLE](create-table.md), which also says what the
constraint states mean.

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

`ENABLE`, `DISABLE`, `MODIFY CONSTRAINT`
: Change the state of a `CHECK` or foreign key constraint (see Remarks). `ENABLE [VALIDATE]` checks every row first:
  a `CHECK` that a row fails is ORA-02293, a foreign key with no parent ORA-02298, and the constraint stays as it
  was. `ENABLE NOVALIDATE` enables it without looking at the rows that are there. `DISABLE` stops the checking, and
  the constraint is then also not validated. `DISABLE VALIDATE` checks the rows first, then disables. A bare
  `VALIDATE` or `NOVALIDATE` (only in `MODIFY CONSTRAINT`) changes the validity alone: `VALIDATE` checks the rows,
  `NOVALIDATE` forgets that they were checked. A name that is not a constraint of the table is ORA-02430
  (`ENABLE`, `VALIDATE`) or ORA-02431 (`DISABLE`).

`RENAME COLUMN`, `RENAME TO`
: Renames a column, or the table.

## Remarks

- Names in the statement are folded to upper case unless quoted.
- A constraint has two states: *enabled* or *disabled* (`USER_CONSTRAINTS.STATUS`), and *validated* or *not validated*
  (`VALIDATED`). A disabled constraint is never checked. An enabled one that is not validated is checked for rows
  inserted or changed from then on (ORA-02290 for a `CHECK`, ORA-02291 for a foreign key), and the rows that are there
  may break it. A disabled foreign key does not refuse the deletion of the parent (no ORA-02292) and does not
  cascade `ON DELETE`.
- Each statement does one kind of change; several `ADD` or `MODIFY` definitions go in one pair of brackets.

## Differences from Oracle

- **Not supported (ORA-03001):** `READ ONLY` and `READ WRITE`, and the other clauses of Oracle's `ALTER TABLE`
  (storage, partitions, `MOVE`, `SHRINK`, `ROW MOVEMENT`).
- **Constraint states** are kept for `CHECK` and foreign key constraints only. `PRIMARY KEY`, `UNIQUE` and `NOT NULL`
  cannot be disabled: `ENABLE CONSTRAINT` or `DISABLE CONSTRAINT` of one is ORA-02430 (`no such constraint`, its text
  saying `cannot enable` for both), and `DISABLE` or `NOVALIDATE` in the definition of one is ORA-00900. `RELY` and `NORELY` are read and not kept
  (`USER_CONSTRAINTS.RELY` is empty). Oracle has no `NOT ENFORCED`; neither has lexdb (ORA-00900).
- `ADD CONSTRAINT ... CHECK` over rows that break it is ORA-02290 (Oracle: ORA-02293).
- lexdb tests every `CHECK` of a row on an `UPDATE`; Oracle tests only those that read a column the `UPDATE` sets. A
  row that does not obey a constraint that is not validated therefore fails when any of its columns is updated.
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

### H. Constraint states: DISABLE and ENABLE

<!-- example: oracle -->
```sql
CREATE TABLE part (id NUMBER PRIMARY KEY, name VARCHAR2(20));
CREATE TABLE bin (id NUMBER PRIMARY KEY, part_id NUMBER, qty NUMBER,
  CONSTRAINT bin_qty_ck CHECK (qty >= 0) DISABLE,
  CONSTRAINT bin_part_fk FOREIGN KEY (part_id) REFERENCES part (id) DISABLE);
INSERT INTO part VALUES (1, 'bolt');
INSERT INTO bin VALUES (1, 1, 10);
INSERT INTO bin VALUES (2, 9, -5);
COMMIT;
SELECT constraint_name, constraint_type, status, validated FROM user_constraints
WHERE table_name = 'BIN' ORDER BY constraint_name;
```

```text
Table created.

Table created.

1 row created.

1 row created.

1 row created.

Commit complete.

CONSTRAINT_NAME CONSTRAINT_TYPE STATUS   VALIDATED
--------------- --------------- -------- -------------
BIN_PART_FK     R               DISABLED NOT VALIDATED
BIN_PKEY        P               ENABLED  VALIDATED
BIN_QTY_CK      C               DISABLED NOT VALIDATED

3 rows selected.
```

Both constraints are disabled, so row 2 was taken. `ENABLE` checks the rows, and refuses while one breaks the
constraint:

<!-- example: oracle -->
```sql
ALTER TABLE bin ENABLE CONSTRAINT bin_qty_ck;
ALTER TABLE bin ENABLE CONSTRAINT bin_part_fk;
UPDATE bin SET qty = 0, part_id = 1 WHERE id = 2;
ALTER TABLE bin ENABLE CONSTRAINT bin_qty_ck;
ALTER TABLE bin ENABLE CONSTRAINT bin_part_fk;
SELECT constraint_name, status, validated FROM user_constraints
WHERE table_name = 'BIN' AND constraint_type IN ('C', 'R') ORDER BY constraint_name;
```

```text
ERROR:
ORA-02293: cannot validate (BIN_QTY_CK) - check constraint violated

ERROR:
ORA-02298: cannot validate (BIN_PART_FK) - parent keys not found

1 row updated.

Table altered.

Table altered.

CONSTRAINT_NAME STATUS  VALIDATED
--------------- ------- ---------
BIN_PART_FK     ENABLED VALIDATED
BIN_QTY_CK      ENABLED VALIDATED

2 rows selected.
```

`ENABLE NOVALIDATE` enables a constraint for the new rows and leaves the old ones unchecked:

<!-- example: oracle -->
```sql
ALTER TABLE bin DISABLE CONSTRAINT bin_qty_ck;
ALTER TABLE bin DISABLE CONSTRAINT bin_part_fk;
UPDATE bin SET qty = -5, part_id = 9 WHERE id = 2;
ALTER TABLE bin ENABLE NOVALIDATE CONSTRAINT bin_qty_ck;
ALTER TABLE bin MODIFY CONSTRAINT bin_part_fk ENABLE NOVALIDATE;
INSERT INTO bin VALUES (3, 1, -1);
INSERT INTO bin VALUES (3, 8, 1);
INSERT INTO bin VALUES (3, 1, 1);
SELECT constraint_name, status, validated FROM user_constraints
WHERE table_name = 'BIN' AND constraint_type IN ('C', 'R') ORDER BY constraint_name;
```

```text
Table altered.

Table altered.

1 row updated.

Table altered.

Table altered.

ERROR:
ORA-02290: check constraint violated

ERROR:
ORA-02291: integrity constraint violated - parent key not found

1 row created.

CONSTRAINT_NAME STATUS  VALIDATED
--------------- ------- -------------
BIN_PART_FK     ENABLED NOT VALIDATED
BIN_QTY_CK      ENABLED NOT VALIDATED

2 rows selected.
```

`MODIFY CONSTRAINT ... VALIDATE` checks the rows of a constraint that is enabled and not validated, and a disabled
foreign key does not stop the deletion of its parent:

<!-- example: oracle -->
```sql
ALTER TABLE bin MODIFY CONSTRAINT bin_qty_ck VALIDATE;
UPDATE bin SET qty = 0, part_id = 1 WHERE id = 2;
ALTER TABLE bin MODIFY CONSTRAINT bin_qty_ck VALIDATE;
DELETE FROM part WHERE id = 1;
ALTER TABLE bin DISABLE CONSTRAINT bin_part_fk;
DELETE FROM part WHERE id = 1;
SELECT id, part_id FROM bin ORDER BY id;
```

```text
ERROR:
ORA-02293: cannot validate (BIN_QTY_CK) - check constraint violated

1 row updated.

Table altered.

ERROR:
ORA-02292: integrity constraint violated - child record found

Table altered.

1 row deleted.

ID PART_ID
-- -------
 1       1
 2       1
 3       1

3 rows selected.
```

A state can be given when a constraint is added:

<!-- example: oracle -->
```sql
ALTER TABLE bin ADD CONSTRAINT bin_cap_ck CHECK (qty < 1000) DISABLE;
ALTER TABLE bin ADD CONSTRAINT bin_min_ck CHECK (qty > -10) ENABLE NOVALIDATE;
ALTER TABLE bin DROP CONSTRAINT bin_cap_ck;
SELECT constraint_name, status, validated FROM user_constraints
WHERE table_name = 'BIN' AND constraint_type = 'C' ORDER BY constraint_name;
ALTER TABLE bin ENABLE CONSTRAINT nosuch;
ALTER TABLE bin MODIFY CONSTRAINT nosuch DISABLE;
ALTER TABLE bin DISABLE CONSTRAINT nosuch;
```

```text
Table altered.

Table altered.

Table altered.

CONSTRAINT_NAME STATUS  VALIDATED
--------------- ------- -------------
BIN_MIN_CK      ENABLED NOT VALIDATED
BIN_QTY_CK      ENABLED VALIDATED

2 rows selected.

ERROR:
ORA-02430: cannot enable constraint (NOSUCH) - no such constraint

ERROR:
ORA-02431: cannot disable constraint (NOSUCH) - no such constraint

ERROR:
ORA-02431: cannot disable constraint (NOSUCH) - no such constraint
```

### I. What lexdb does not take

<!-- example: oracle -->
```sql
ALTER TABLE staff READ ONLY;
ALTER TABLE staff DISABLE CONSTRAINT emp_pkey;
ALTER TABLE staff ALTER COLUMN salary SET DEFAULT 5;
```

```text
ERROR:
ORA-03001: unimplemented feature: lexdb: ALTER TABLE takes ADD, DROP, ALTER COLUMN, VALIDATE CONSTRAINT, RENAME and SET SCHEMA

ERROR:
ORA-02430: cannot enable constraint (EMP_PKEY) - no such constraint

ERROR:
ORA-01735: invalid ALTER TABLE option
```

## See also

[CREATE TABLE](create-table.md), [DROP TABLE](drop-table.md), [RENAME](rename.md)
