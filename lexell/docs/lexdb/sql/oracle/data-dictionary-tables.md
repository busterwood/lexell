# Data dictionary: tables, columns, indexes and constraints

`USER_TABLES`, `USER_TAB_COLUMNS`, `USER_INDEXES`, `USER_IND_COLUMNS`, `USER_IND_EXPRESSIONS`, `USER_CONSTRAINTS`,
`USER_CONS_COLUMNS`, `USER_TAB_IDENTITY_COLS`, `USER_OBJECTS`, `USER_CATALOG` and their `ALL_` and `DBA_` forms.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
SELECT ... FROM { USER_ | ALL_ | DBA_ }view
SELECT ... FROM TABS | COLS | DICT | DICTIONARY | DUAL
```

## Views

Each view has the columns of Oracle 23ai; the columns named below carry data, the others are NULL or a fixed value.
`SELECT * FROM DICTIONARY` lists the views the door has (226 names; many of them are present only so that tools can
read them, and return no rows).

`USER_`, `ALL_` and `DBA_` forms
: `USER_` views show the objects of the current user, `ALL_` the ones the user may see, and `DBA_` all of them.
  In lexdb a single user's session sees the same tables in all three; `ALL_` and `DBA_` carry an `OWNER` column.

`USER_TABLES` (`TABS`), `ALL_TABLES`, `DBA_TABLES`
: `TABLE_NAME`, `TABLESPACE_NAME` (`USERS`), `STATUS` (`VALID`), `PCT_FREE`, `TEMPORARY` (`Y` for a global
  temporary table). Statistics columns (`NUM_ROWS`, `BLOCKS`, ...) are empty.

`USER_TAB_COLUMNS` (`COLS`), `ALL_TAB_COLUMNS`, `USER_TAB_COLS`
: `TABLE_NAME`, `COLUMN_NAME`, `DATA_TYPE`, `DATA_LENGTH`, `DATA_PRECISION`, `DATA_SCALE`, `NULLABLE`, `COLUMN_ID`,
  `DATA_DEFAULT`, `CHAR_LENGTH`, `VIRTUAL_COLUMN`, `IDENTITY_COLUMN`. It lists the columns of views too.

`USER_INDEXES`, `USER_IND_COLUMNS`, `USER_IND_EXPRESSIONS`
: `INDEX_NAME`, `INDEX_TYPE` (`NORMAL`), `TABLE_NAME`, `UNIQUENESS`; the columns of each index with
  `COLUMN_POSITION` and `DESCEND`; the text of expressions of function-based indexes.

`USER_CONSTRAINTS`, `USER_CONS_COLUMNS`
: `CONSTRAINT_NAME`, `CONSTRAINT_TYPE` (`P`, `U`, `R`, `C`), `TABLE_NAME`, `SEARCH_CONDITION` (a check's text),
  `R_CONSTRAINT_NAME` (the key a foreign key points to), `DELETE_RULE`, `STATUS`; and the columns of each
  constraint with `POSITION`.

`USER_TAB_IDENTITY_COLS`
: The identity columns: `TABLE_NAME`, `COLUMN_NAME`, `GENERATION_TYPE` (`ALWAYS` or `BY DEFAULT`),
  `IDENTITY_OPTIONS`.

`USER_OBJECTS`, `ALL_OBJECTS`, `DBA_OBJECTS`, `USER_CATALOG` (`CAT` is not present)
: Every table, view, index, sequence, procedure, function and package: `OBJECT_NAME`, `OBJECT_TYPE`, `STATUS`,
  `CREATED` and `LAST_DDL_TIME` (always 2000-01-01), `OBJECT_ID` (derived from the name). `USER_CATALOG` lists
  tables, views and sequences with `TABLE_TYPE`.

`DICTIONARY` (`DICT`), `DICT_COLUMNS`
: The list of the dictionary's own views.

`DUAL`
: One row, one column `DUMMY` with `X`.

## Remarks

- Names are in upper case unless the object was made with a quoted name.
- Object ids and the dates are not shown in the examples (they are derived from names and fixed).

## Differences from Oracle

- Statistics columns (`NUM_ROWS`, `LAST_ANALYZED`, ...) are empty; `DBMS_STATS` calls are accepted and do nothing.
- Every key index is named after its table (`EMP_PKEY`) where Oracle uses `SYS_Cnnnnnn` for system-generated names.
- `USER_INDEXES.COMPRESSION` is `DISABLED` and the storage columns are empty.
- `USER_SOURCE` and the other program views are on [their own page](data-dictionary-programs.md).
- Views Oracle has and lexdb has not (`USER_TAB_PRIVS_MADE`, `USER_TAB_PRIVS_RECD`, `ROLE_TAB_PRIVS`) are
  ORA-00942.

## Examples

<!--setup: oracle
CREATE TABLE dept (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL UNIQUE);
CREATE TABLE emp (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY, dept_id NUMBER(4) NOT NULL REFERENCES dept (id), name VARCHAR2(40) NOT NULL, salary NUMBER(10,2) DEFAULT 1000 CONSTRAINT emp_sal_ck CHECK (salary >= 0), bonus NUMBER GENERATED ALWAYS AS (salary / 10) VIRTUAL);
CREATE INDEX ix_emp_name ON emp (name);
CREATE INDEX ix_emp_upper ON emp (UPPER(name));
CREATE VIEW v_emp AS SELECT id, name FROM emp;
CREATE SEQUENCE sq START WITH 5;
CREATE OR REPLACE PROCEDURE raise_pay (p_id IN NUMBER, p_pct IN NUMBER DEFAULT 10) AS
BEGIN
  UPDATE emp SET salary = salary * (1 + p_pct / 100) WHERE id = p_id;
END;
/
CREATE OR REPLACE FUNCTION double_it (x NUMBER) RETURN NUMBER AS
BEGIN
  RETURN x * 2;
END;
/
-->

The examples use these objects:

```sql
CREATE TABLE dept (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL UNIQUE);
CREATE TABLE emp (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY, dept_id NUMBER(4) NOT NULL REFERENCES dept (id),
                  name VARCHAR2(40) NOT NULL, salary NUMBER(10,2) DEFAULT 1000 CONSTRAINT emp_sal_ck CHECK (salary >= 0),
                  bonus NUMBER GENERATED ALWAYS AS (salary / 10) VIRTUAL);
CREATE INDEX ix_emp_name ON emp (name);
CREATE INDEX ix_emp_upper ON emp (UPPER(name));
CREATE VIEW v_emp AS SELECT id, name FROM emp;
CREATE SEQUENCE sq START WITH 5;
CREATE OR REPLACE PROCEDURE raise_pay (p_id IN NUMBER, p_pct IN NUMBER DEFAULT 10) AS
BEGIN
  UPDATE emp SET salary = salary * (1 + p_pct / 100) WHERE id = p_id;
END;
/
CREATE OR REPLACE FUNCTION double_it (x NUMBER) RETURN NUMBER AS
BEGIN
  RETURN x * 2;
END;
/
```

### A. Tables and their columns

<!-- example: oracle -->
```sql
SELECT table_name, status, temporary FROM user_tables ORDER BY table_name;
SELECT column_name, data_type, data_length, data_precision, data_scale, nullable, column_id
FROM user_tab_columns WHERE table_name = 'EMP' ORDER BY column_id;
SELECT column_name, virtual_column, identity_column FROM user_tab_cols WHERE table_name = 'EMP' ORDER BY column_id;
```

```text
TABLE_NAME STATUS TEMPORARY
---------- ------ ---------
DEPT       VALID  N
EMP        VALID  N

2 rows selected.

COLUMN_NAME DATA_TYPE DATA_LENGTH DATA_PRECISION DATA_SCALE NULLABLE COLUMN_ID
----------- --------- ----------- -------------- ---------- -------- ---------
ID          NUMBER             22                           N                1
DEPT_ID     NUMBER             22              4          0 N                2
NAME        VARCHAR2           40                           N                3
SALARY      NUMBER             22             10          2 Y                4
BONUS       NUMBER             22                           Y                5

5 rows selected.

COLUMN_NAME VIRTUAL_COLUMN IDENTITY_COLUMN
----------- -------------- ---------------
ID          NO             YES
DEPT_ID     NO             NO
NAME        NO             NO
SALARY      NO             NO
BONUS       YES            NO

5 rows selected.
```

### B. Indexes

<!-- example: oracle -->
```sql
SELECT index_name, index_type, uniqueness, table_name FROM user_indexes ORDER BY index_name;
SELECT index_name, column_name, column_position, descend FROM user_ind_columns ORDER BY index_name, column_position;
SELECT index_name, column_expression FROM user_ind_expressions;
```

```text
INDEX_NAME    INDEX_TYPE            UNIQUENESS TABLE_NAME
------------- --------------------- ---------- ----------
DEPT_NAME_KEY NORMAL                UNIQUE     DEPT
DEPT_PKEY     NORMAL                UNIQUE     DEPT
EMP_PKEY      NORMAL                UNIQUE     EMP
IX_EMP_NAME   NORMAL                NONUNIQUE  EMP
IX_EMP_UPPER  FUNCTION-BASED NORMAL NONUNIQUE  EMP

5 rows selected.

INDEX_NAME    COLUMN_NAME  COLUMN_POSITION DESCEND
------------- ------------ --------------- -------
DEPT_NAME_KEY NAME                       1 ASC
DEPT_PKEY     ID                         1 ASC
EMP_PKEY      ID                         1 ASC
IX_EMP_NAME   NAME                       1 ASC
IX_EMP_UPPER  SYS_NC00006$               1 ASC

5 rows selected.

INDEX_NAME   COLUMN_EXPRESSION
------------ -----------------
IX_EMP_UPPER UPPER("NAME")

1 row selected.
```

### C. Constraints

<!-- example: oracle -->
```sql
SELECT constraint_name, constraint_type, table_name, r_constraint_name, delete_rule, status
FROM user_constraints ORDER BY constraint_name;
SELECT constraint_name, column_name, position FROM user_cons_columns ORDER BY constraint_name, position;
SELECT constraint_name, search_condition FROM user_constraints WHERE constraint_type = 'C';
```

```text
CONSTRAINT_NAME  CONSTRAINT_TYPE TABLE_NAME R_CONSTRAINT_NAME DELETE_RULE STATUS
---------------- --------------- ---------- ----------------- ----------- -------
DEPT_NAME_KEY    U               DEPT                                     ENABLED
DEPT_PKEY        P               DEPT                                     ENABLED
EMP_DEPT_ID_FKEY R               EMP        DEPT_PKEY         NO ACTION   ENABLED
EMP_PKEY         P               EMP                                      ENABLED
EMP_SAL_CK       C               EMP                                      ENABLED

5 rows selected.

CONSTRAINT_NAME  COLUMN_NAME POSITION
---------------- ----------- --------
DEPT_NAME_KEY    NAME               1
DEPT_PKEY        ID                 1
EMP_DEPT_ID_FKEY DEPT_ID            1
EMP_PKEY         ID                 1

4 rows selected.

CONSTRAINT_NAME SEARCH_CONDITION
--------------- ----------------
EMP_SAL_CK      salary >= 0

1 row selected.
```

### D. Identity columns

<!-- example: oracle -->
```sql
SELECT table_name, column_name, generation_type FROM user_tab_identity_cols;
```

```text
TABLE_NAME COLUMN_NAME GENERATION_TYPE
---------- ----------- ---------------
EMP        ID          ALWAYS

1 row selected.
```

### E. Objects

<!-- example: oracle -->
```sql
SELECT object_name, object_type, status FROM user_objects ORDER BY object_type, object_name;
SELECT table_name, table_type FROM user_catalog ORDER BY table_name;
```

```text
OBJECT_NAME   OBJECT_TYPE STATUS
------------- ----------- ------
DOUBLE_IT     FUNCTION    VALID
DEPT_NAME_KEY INDEX       VALID
DEPT_PKEY     INDEX       VALID
EMP_PKEY      INDEX       VALID
IX_EMP_NAME   INDEX       VALID
IX_EMP_UPPER  INDEX       VALID
RAISE_PAY     PROCEDURE   VALID
SQ            SEQUENCE    VALID
DEPT          TABLE       VALID
EMP           TABLE       VALID
V_EMP         VIEW        VALID

11 rows selected.

TABLE_NAME TABLE_TYPE
---------- ----------
DEPT       TABLE
EMP        TABLE
SQ         SEQUENCE
V_EMP      VIEW

4 rows selected.
```

### F. The three forms and the shortcuts

<!-- example: oracle -->
```sql
SELECT COUNT(*) AS user_tables FROM user_tables;
SELECT COUNT(*) AS all_tables FROM all_tables;
SELECT COUNT(*) AS dba_tables FROM dba_tables;
SELECT COUNT(*) AS tabs FROM tabs;
SELECT COUNT(*) AS cols FROM cols WHERE table_name = 'EMP';
SELECT COUNT(*) AS views_in_dictionary FROM dict;
```

```text
USER_TABLES
-----------
          2

1 row selected.

ALL_TABLES
----------
         2

1 row selected.

DBA_TABLES
----------
         2

1 row selected.

TABS
----
   2

1 row selected.

COLS
----
   5

1 row selected.

VIEWS_IN_DICTIONARY
-------------------
                226

1 row selected.
```

### G. Views that do not exist

<!-- example: oracle -->
```sql
SELECT * FROM user_tab_privs_made;
SELECT * FROM role_tab_privs;
```

```text
ERROR:
ORA-00942: table or view "SA"."USER_TAB_PRIVS_MADE" does not exist

ERROR:
ORA-00942: table or view "SA"."ROLE_TAB_PRIVS" does not exist
```

## See also

[Programs, sequences and views](data-dictionary-programs.md), [System and session views](data-dictionary-system.md),
[CREATE TABLE](create-table.md), [CREATE INDEX](create-index.md)
