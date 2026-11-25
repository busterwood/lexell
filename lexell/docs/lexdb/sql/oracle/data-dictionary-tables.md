# Data dictionary: tables, columns, indexes and constraints

`USER_TABLES`, `USER_TAB_COLUMNS`, `USER_INDEXES`, `USER_IND_COLUMNS`, `USER_IND_EXPRESSIONS`, `USER_CONSTRAINTS`,
`USER_CONS_COLUMNS`, `USER_TAB_IDENTITY_COLS`, `USER_OBJECTS`, `USER_CATALOG`, `USER_ANNOTATIONS_USAGE`,
`USER_ANNOTATIONS`, `USER_ANNOTATION_VALUES`, the property graph views (`USER_PROPERTY_GRAPHS`, `USER_PG_ELEMENTS`,
`USER_PG_LABELS`, `USER_PG_ELEMENT_LABELS`, `USER_PG_LABEL_PROPERTIES`, `USER_PG_PROP_DEFINITIONS`, `USER_PG_KEYS`,
`USER_PG_EDGE_RELATIONSHIPS`, `USER_PG_COMMENTS`), the assertion views (`USER_ASSERTIONS`,
`USER_ASSERTION_DEPENDENCIES`, `USER_ASSERTION_LOCK_MATRIX`) and their `ALL_` and `DBA_` forms.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
SELECT ... FROM { USER_ | ALL_ | DBA_ }view
SELECT ... FROM TABS | COLS | DICT | DICTIONARY | DUAL
```

## Views

Each view has the columns of Oracle 23ai; the columns named below carry data, the others are NULL or a fixed value.
`SELECT * FROM DICTIONARY` lists the views the door has (235 names; many of them are present only so that tools can
read them, and return no rows).

`USER_`, `ALL_` and `DBA_` forms
: `USER_` views show the objects of the current user, `ALL_` the ones the user may see, and `DBA_` all of them.
  In lexdb a single user's session sees the same tables in all three; `ALL_` and `DBA_` carry an `OWNER` column. `USER_` views list the login's own schema. A table of the PostgreSQL door's `public` schema is in `ALL_` and `DBA_` with the owner `SYS`.

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
  `R_CONSTRAINT_NAME` (the key a foreign key points to), `DELETE_RULE`, `STATUS` (`ENABLED` or `DISABLED`),
  `VALIDATED` (`VALIDATED` or `NOT VALIDATED`; see [ALTER TABLE](alter-table.md)); and the columns of each
  constraint with `POSITION`. `RELY` is always empty.

`USER_TAB_IDENTITY_COLS`
: The identity columns: `TABLE_NAME`, `COLUMN_NAME`, `GENERATION_TYPE` (`ALWAYS` or `BY DEFAULT`),
  `IDENTITY_OPTIONS`.

`USER_OBJECTS`, `ALL_OBJECTS`, `DBA_OBJECTS`, `USER_CATALOG` (`CAT` is not present)
: Every table, view, index, sequence, procedure, function, package and property graph (`OBJECT_TYPE` `PROPERTY
  GRAPH`): `OBJECT_NAME`, `OBJECT_TYPE`, `STATUS`,
  `CREATED` and `LAST_DDL_TIME` (always 2000-01-01), `OBJECT_ID` (derived from the name). `USER_CATALOG` lists
  tables, views and sequences with `TABLE_TYPE`.

`USER_ANNOTATIONS_USAGE`, `ALL_ANNOTATIONS_USAGE`, `DBA_ANNOTATIONS_USAGE`
: One row for each [annotation](annotations.md) of a table, view or index or of one of their columns:
  `OBJECT_NAME`, `OBJECT_TYPE` (`TABLE`, `VIEW` or `INDEX`), `COLUMN_NAME` (NULL for the object's own),
  `ANNOTATION_NAME`, `ANNOTATION_VALUE` (NULL for a flag); `DOMAIN_NAME` and `DOMAIN_OWNER` are NULL. The `ALL_` and
  `DBA_` forms add `ANNOTATION_OWNER`.

`USER_ANNOTATIONS`, `USER_ANNOTATION_VALUES` and their `ALL_` and `DBA_` forms
: The annotation names in use (`ANNOTATION_NAME`), and the names and values in use (`ANNOTATION_NAME`,
  `ANNOTATION_VALUE`), each once for an owner (`ANNOTATION_OWNER` in `ALL_` and `DBA_`). A name goes from them when
  its last use goes.

`USER_PROPERTY_GRAPHS`, `ALL_PROPERTY_GRAPHS`, `DBA_PROPERTY_GRAPHS`
: One row for each [property graph](create-property-graph.md): `GRAPH_NAME`, `GRAPH_MODE` (`TRUSTED`),
  `ALLOWS_MIXED_TYPES` (`NO`), `INMEMORY` (`NO`); `OWNER` in `ALL_` and `DBA_`. A graph's `USER_OBJECTS.STATUS` is
  `INVALID` while a table or column it names is gone.

`USER_PG_ELEMENTS`, `USER_PG_KEYS`, `USER_PG_EDGE_RELATIONSHIPS`
: A graph's elements: `ELEMENT_NAME`, `ELEMENT_KIND` (`VERTEX` or `EDGE`), `OBJECT_OWNER` and `OBJECT_NAME` (the
  table or view); the key columns of each (`COLUMN_NAME`); and for each edge table its two ends: `EDGE_TAB_NAME`,
  `VERTEX_TAB_NAME`, `EDGE_END` (`SOURCE` or `DESTINATION`), `EDGE_COL_NAME`, `VERTEX_COL_NAME`, a row per column.

`USER_PG_LABELS`, `USER_PG_ELEMENT_LABELS`, `USER_PG_LABEL_PROPERTIES`, `USER_PG_PROP_DEFINITIONS`
: The labels (`LABEL_NAME`), the labels of each element, the properties of each label (`PROPERTY_NAME`,
  `DATA_TYPE`, `DATA_LENGTH`, `DATA_PRECISION`, `DATA_SCALE`, `DATA_CHAR_LENGTH`, `CHARACTER_SET_NAME`, `COLLATION`,
  `PROPERTY_ORDER`; the `DATA_LENGTH` of a property is the longest of the lengths of the properties of that name in
  the graph, as in Oracle: example J lists `DEPT`'s `NAME`, a `VARCHAR2(30)`, as 40, the length of `EMP`'s), and what
  each property of an element reads: `COLUMN_NAME` for a column, `COLUMN_EXPR` for an expression.

`USER_PG_COMMENTS`
: A row for each graph, `COMMENTS` empty (lexdb does not keep comments).

All of them have `ALL_` and `DBA_` forms with an `OWNER` column. Example J below.

`USER_ASSERTIONS`, `ALL_ASSERTIONS`, `DBA_ASSERTIONS`
: One row for each [assertion](create-assertion.md), whichever door made it: `ASSERTION_NAME`, `STATUS` (`ENABLED` or
  `DISABLED`), `DEFERRABLE` (`DEFERRABLE` or `NOT DEFERRABLE`), `DEFERRED` (`DEFERRED` or `IMMEDIATE`), `VALIDATED`
  (`VALIDATED` or `NOT VALIDATED`), `DEFINITION_SQL` (a CLOB: `CREATE ASSERTION "APP"."A1" CHECK`, a line with the
  condition as written, then the state words, each on a line of its own, joined by carriage return and line feed),
  and `INVALID` (`INVALID` once an `ALTER TABLE` added, dropped, retyped or renamed a column of a table the assertion
  reads, as in Oracle; NULL otherwise). `OWNER` in `ALL_` and `DBA_`; an assertion made in the PostgreSQL or SQL Server
  door is owned by the user, or by `SYS` for a user with a schema of its own, as public's tables are. A `DBA_` view is
  not readable by an ordinary user.

`USER_ASSERTION_DEPENDENCIES`, `ALL_ASSERTION_DEPENDENCIES`, `DBA_ASSERTION_DEPENDENCIES`
: A row for each table an assertion reads, each instance of it (a table read twice has two rows): `ASSERTION_NAME`,
  `REFERENCED_OWNER`, `REFERENCED_NAME`, `REFERENCED_TYPE` (`TABLE`), `REFERENCED_ID` (0, 1, ... in Oracle's order: the
  query's own tables first, by their age, then each `NOT EXISTS`'s), `VALIDATION_TYPE` (`FAST`, or `COMPLETE` for an
  `EXISTS`) and `VALIDATION_EVENT` (`ROWS INSERTED OR UPDATED`; `ROWS DELETED OR UPDATED` for a table under a `NOT EXISTS`
  and for an `EXISTS`).

`USER_ASSERTION_LOCK_MATRIX` (and `ALL_`, `DBA_`)
: Has the columns and no rows: lexdb's locks are the assertion's and its join key's values, not Oracle's per-instance
  modes.

An assertion is also a row of `USER_OBJECTS` with `OBJECT_TYPE` `UNDEFINED` and `STATUS` `VALID`. Example K.

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
- `USER_CONSTRAINTS` and `USER_CONS_COLUMNS` have no rows for `NOT NULL` constraints (Oracle: type `C`, `SEARCH_CONDITION`
  `"A" IS NOT NULL`); [CREATE TABLE](create-table.md), example K.
- `ALL_` and `DBA_ANNOTATIONS_USAGE` have no rows for the built-in domains of `SYS` (Oracle Free lists about a
  hundred, `OBJECT_TYPE` `DOMAIN`): lexdb has no domains. A global temporary table's annotations are not listed.
- `USER_INDEXES.COMPRESSION` is `DISABLED` and the storage columns are empty.
- A property graph's `USER_OBJECTS.STATUS` says whether the tables and columns it names are there; Oracle marks it
  `INVALID` when a column of one of its tables is changed, until its next use. `USER_PG_ELEMENTS.OBJECT_NAME`,
  `USER_PG_PROP_DEFINITIONS.COLUMN_NAME` and the types in `USER_PG_LABEL_PROPERTIES` are as they were at `CREATE
  PROPERTY GRAPH` (Oracle's follow a rename or `MODIFY`), and `USER_PG_COMMENTS` has no comments.
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
                271

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

### H. Constraint states

<!-- example: oracle -->
```sql
CREATE TABLE gate (id NUMBER PRIMARY KEY, dept_id NUMBER, level NUMBER,
  CONSTRAINT gate_level_ck CHECK (level > 0) DISABLE,
  CONSTRAINT gate_dept_fk FOREIGN KEY (dept_id) REFERENCES dept (id) ENABLE NOVALIDATE);
INSERT INTO dept VALUES (1, 'Sales');
INSERT INTO gate VALUES (1, 1, -1);
SELECT constraint_name, constraint_type, status, validated FROM user_constraints
WHERE table_name = 'GATE' ORDER BY constraint_name;
ALTER TABLE gate MODIFY CONSTRAINT gate_dept_fk VALIDATE;
ALTER TABLE gate ENABLE NOVALIDATE CONSTRAINT gate_level_ck;
SELECT constraint_name, status, validated FROM user_constraints
WHERE table_name = 'GATE' AND constraint_type IN ('C', 'R') ORDER BY constraint_name;
```

```text
Table created.

1 row created.

1 row created.

CONSTRAINT_NAME CONSTRAINT_TYPE STATUS   VALIDATED
--------------- --------------- -------- -------------
GATE_DEPT_FK    R               ENABLED  NOT VALIDATED
GATE_LEVEL_CK   C               DISABLED NOT VALIDATED
GATE_PKEY       P               ENABLED  VALIDATED

3 rows selected.

Table altered.

Table altered.

CONSTRAINT_NAME STATUS  VALIDATED
--------------- ------- -------------
GATE_DEPT_FK    ENABLED VALIDATED
GATE_LEVEL_CK   ENABLED NOT VALIDATED

2 rows selected.
```

### I. Annotations

<!-- example: oracle -->
```sql
ALTER TABLE emp ANNOTATIONS (ADD Owner 'hr', ADD Audited);
ALTER TABLE emp MODIFY (salary ANNOTATIONS (ADD Unit 'EUR'));
ALTER INDEX ix_emp_name ANNOTATIONS (ADD Purpose 'search');
SELECT object_name, object_type, column_name, annotation_name, annotation_value
FROM user_annotations_usage ORDER BY object_type, column_name NULLS FIRST, annotation_name;
SELECT * FROM user_annotations ORDER BY 1;
SELECT * FROM user_annotation_values ORDER BY 1, 2;
SELECT annotation_owner, annotation_name FROM all_annotations WHERE annotation_owner = USER ORDER BY 2;
```

```text
Table altered.

Table altered.

Index altered.

OBJECT_NAME OBJECT_TYPE COLUMN_NAME ANNOTATION_NAME ANNOTATION_VALUE
----------- ----------- ----------- --------------- ----------------
IX_EMP_NAME INDEX                   PURPOSE         search
EMP         TABLE                   AUDITED
EMP         TABLE                   OWNER           hr
EMP         TABLE       SALARY      UNIT            EUR

4 rows selected.

ANNOTATION_NAME
---------------
AUDITED
OWNER
PURPOSE
UNIT

4 rows selected.

ANNOTATION_NAME ANNOTATION_VALUE
--------------- ----------------
AUDITED
OWNER           hr
PURPOSE         search
UNIT            EUR

4 rows selected.

ANNOTATION_OWNER ANNOTATION_NAME
---------------- ---------------
SA               AUDITED
SA               OWNER
SA               PURPOSE
SA               UNIT

4 rows selected.
```

### J. Property graphs

<!-- example: oracle -->
```sql
CREATE TABLE works_in (emp_id INTEGER PRIMARY KEY REFERENCES emp (id), dept_id NUMBER(4) NOT NULL REFERENCES dept (id));
CREATE PROPERTY GRAPH org
  VERTEX TABLES (emp LABEL employee PROPERTIES (name, salary, salary * 12 AS yearly), dept)
  EDGE TABLES (works_in SOURCE emp DESTINATION dept NO PROPERTIES);
SELECT * FROM user_property_graphs;
SELECT element_name, element_kind, object_name FROM user_pg_elements ORDER BY 1;
SELECT element_name, label_name FROM user_pg_element_labels ORDER BY 1;
SELECT label_name, property_name, data_type, data_length, property_order FROM user_pg_label_properties ORDER BY 1, 5;
SELECT element_name, property_name, column_name, column_expr FROM user_pg_prop_definitions ORDER BY 1, 2;
SELECT element_name, column_name FROM user_pg_keys ORDER BY 1;
SELECT edge_tab_name, vertex_tab_name, edge_end, edge_col_name, vertex_col_name
FROM user_pg_edge_relationships ORDER BY 3 DESC;
SELECT object_name, object_type, status FROM user_objects WHERE object_type = 'PROPERTY GRAPH';
```

```text
Table created.

Property graph created.

GRAPH_NAME GRAPH_MODE ALLOWS_MIXED_TYPES INMEMORY
---------- ---------- ------------------ --------
ORG        TRUSTED    NO                 NO

1 row selected.

ELEMENT_NAME ELEMENT_KIND OBJECT_NAME
------------ ------------ -----------
DEPT         VERTEX       DEPT
EMP          VERTEX       EMP
WORKS_IN     EDGE         WORKS_IN

3 rows selected.

ELEMENT_NAME LABEL_NAME
------------ ----------
DEPT         DEPT
EMP          EMPLOYEE
WORKS_IN     WORKS_IN

3 rows selected.

LABEL_NAME PROPERTY_NAME DATA_TYPE DATA_LENGTH PROPERTY_ORDER
---------- ------------- --------- ----------- --------------
DEPT       ID            NUMBER             22              1
DEPT       NAME          VARCHAR2           40              2
EMPLOYEE   NAME          VARCHAR2           40              1
EMPLOYEE   SALARY        NUMBER             22              2
EMPLOYEE   YEARLY        NUMBER             22              3

5 rows selected.

ELEMENT_NAME PROPERTY_NAME COLUMN_NAME COLUMN_EXPR
------------ ------------- ----------- -----------
DEPT         ID            ID
DEPT         NAME          NAME
EMP          NAME          NAME
EMP          SALARY        SALARY
EMP          YEARLY                    "SALARY"*12

5 rows selected.

ELEMENT_NAME COLUMN_NAME
------------ -----------
DEPT         ID
EMP          ID
WORKS_IN     EMP_ID

3 rows selected.

EDGE_TAB_NAME VERTEX_TAB_NAME EDGE_END    EDGE_COL_NAME VERTEX_COL_NAME
------------- --------------- ----------- ------------- ---------------
WORKS_IN      EMP             SOURCE      EMP_ID        ID
WORKS_IN      DEPT            DESTINATION DEPT_ID       ID

2 rows selected.

OBJECT_NAME OBJECT_TYPE    STATUS
----------- -------------- ------
ORG         PROPERTY GRAPH VALID

1 row selected.
```

### K. Assertions

<!-- example: oracle -->
```sql
CREATE TABLE ka (id NUMBER PRIMARY KEY, v NUMBER);
CREATE TABLE kb (id NUMBER PRIMARY KEY, ka_id NUMBER NOT NULL);
CREATE ASSERTION kb_has_ka CHECK (NOT EXISTS (SELECT 1 FROM kb WHERE NOT EXISTS (SELECT 1 FROM ka WHERE ka.id = kb.ka_id)));
CREATE ASSERTION ka_pos CHECK (NOT EXISTS (SELECT 1 FROM ka WHERE v < 0)) DEFERRABLE INITIALLY DEFERRED;
SELECT assertion_name, status, deferrable, deferred, validated, invalid FROM user_assertions ORDER BY 1;
SELECT assertion_name, referenced_name, referenced_id, validation_type, validation_event
FROM user_assertion_dependencies ORDER BY assertion_name, referenced_id;
SELECT object_name, object_type, status FROM user_objects WHERE object_type = 'UNDEFINED' ORDER BY 1;
SELECT REPLACE(REPLACE(definition_sql, CHR(13), '<cr>'), CHR(10), '<lf>') AS d FROM user_assertions WHERE assertion_name = 'KA_POS';
SELECT COUNT(*) AS n FROM user_assertion_lock_matrix;
```

```text
Table created.

Table created.

Assertion created.

Assertion created.

ASSERTION_NAME STATUS  DEFERRABLE     DEFERRED  VALIDATED INVALID
-------------- ------- -------------- --------- --------- -------
KA_POS         ENABLED DEFERRABLE     DEFERRED  VALIDATED
KB_HAS_KA      ENABLED NOT DEFERRABLE IMMEDIATE VALIDATED

2 rows selected.

ASSERTION_NAME REFERENCED_NAME REFERENCED_ID VALIDATION_TYPE VALIDATION_EVENT
-------------- --------------- ------------- --------------- ------------------------
KA_POS         KA                          0 FAST            ROWS INSERTED OR UPDATED
KB_HAS_KA      KB                          0 FAST            ROWS INSERTED OR UPDATED
KB_HAS_KA      KA                          1 FAST            ROWS DELETED OR UPDATED

3 rows selected.

OBJECT_NAME OBJECT_TYPE STATUS
----------- ----------- ------
KA_POS      UNDEFINED   VALID
KB_HAS_KA   UNDEFINED   VALID

2 rows selected.

D
----------------------------------------------------------------------------------------------------------------------------------------------------------------------
CREATE ASSERTION "SA"."KA_POS" CHECK <cr><lf>(NOT EXISTS (SELECT 1 FROM ka WHERE v < 0))<cr><lf> ENABLE<cr><lf> DEFERRABLE<cr><lf> INITIALLY DEFERRED<cr><lf> VALIDATE

1 row selected.

N
-
0

1 row selected.
```

## See also

[Programs, sequences and views](data-dictionary-programs.md), [System and session views](data-dictionary-system.md),
[CREATE TABLE](create-table.md), [CREATE INDEX](create-index.md), [Annotations](annotations.md),
[CREATE PROPERTY GRAPH](create-property-graph.md), [CREATE ASSERTION](create-assertion.md)
