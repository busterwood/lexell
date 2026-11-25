# CREATE TABLE

Creates a table, or a global temporary table, with its columns, defaults and constraints.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE [ GLOBAL TEMPORARY ] TABLE [ schema. ] table
    ( column_definition [, column_definition ]... [, table_constraint ]... )
    [ ON COMMIT { DELETE | PRESERVE } ROWS ] [ annotations_clause ]

CREATE TABLE [ schema. ] table [ ( column [, column ]... ) ] [ annotations_clause ] AS subquery

column_definition:
    column datatype [ DEFAULT [ ON NULL ] expr ]
        [ GENERATED { ALWAYS | BY DEFAULT } AS IDENTITY [ ( identity_option ... ) ] ]
        [ GENERATED ALWAYS AS ( expr ) [ VIRTUAL ] ]
        [ column_constraint ]... [ annotations_clause ]

column_constraint:
    [ CONSTRAINT name ]
    { NOT NULL | NULL | UNIQUE | PRIMARY KEY
    | CHECK ( condition ) [ constraint_state ]
    | REFERENCES [ schema. ] table [ ( column ) ] [ ON DELETE { CASCADE | SET NULL } ] [ constraint_state ] }

table_constraint:
    [ CONSTRAINT name ]
    { UNIQUE ( column [, ...] ) | PRIMARY KEY ( column [, ...] )
    | CHECK ( condition ) [ constraint_state ]
    | FOREIGN KEY ( column [, ...] ) REFERENCES [ schema. ] table [ ( column [, ...] ) ]
          [ ON DELETE { CASCADE | SET NULL } ] [ constraint_state ] }

constraint_state:
    [ ENABLE | DISABLE ] [ VALIDATE | NOVALIDATE ] [ RELY | NORELY ]

annotations_clause:
    ANNOTATIONS ( [ ADD [ IF NOT EXISTS ] ] name [ 'value' ] [, ...] )
```

## Arguments

*schema*
: The owner. Without it, the session's current schema: the login user, or the one `ALTER SESSION SET
  CURRENT_SCHEMA` set. A user is a schema (see [CREATE USER](create-user.md)).

*datatype*
: One of lexdb's types: see the [type pages](README.md#data-types). `VARCHAR2(n [BYTE | CHAR])`, `CHAR(n)`,
  `NUMBER(p, s)`, `DATE`, `TIMESTAMP(p)` and its time zone forms, `CLOB`, `BLOB`, `RAW(n)`, `BINARY_FLOAT`,
  `BINARY_DOUBLE`, `BOOLEAN`, `ROWID`, and the ANSI names `INT`, `SMALLINT`, `DECIMAL`, `NUMERIC`, `REAL`,
  `DOUBLE PRECISION`, `VARCHAR`, `CHARACTER`. `NUMBER` precision is 1 to 38 (ORA-01727).

`DEFAULT expr`
: The value used when an `INSERT` leaves the column out or says `DEFAULT`. `DEFAULT ON NULL expr` also replaces an
  explicit NULL.

`GENERATED ... AS IDENTITY`
: A key made by lexdb. `ALWAYS` refuses a value in the `INSERT` (ORA-32795); `BY DEFAULT` takes one. Options:
  `START WITH`, `INCREMENT BY`.

`GENERATED ALWAYS AS (expr) [VIRTUAL]`
: A column computed from other columns when read.

*column_constraint*, *table_constraint*
: `NOT NULL`, `UNIQUE`, `PRIMARY KEY`, `CHECK`, and `REFERENCES` (a foreign key) with `ON DELETE CASCADE` or `SET
  NULL`. An unnamed key or check gets lexdb's name (`T_PKEY`, `EMP_DEPT_ID_FKEY`; see differences).

*constraint_state*
: For a `CHECK` or foreign key: whether it is checked. `ENABLE` (the default) checks new rows. `DISABLE` does not
  check any row: the constraint is kept and shown in the dictionary (`STATUS` `DISABLED`), and rows that break it
  are taken. `VALIDATE` and `NOVALIDATE` say whether the rows that are there are known to obey the constraint:
  in `CREATE TABLE` the table is empty, so a constraint is validated unless it is disabled or `NOVALIDATE`.
  [ALTER TABLE](alter-table.md) changes the state of a constraint later, and checks the rows when it does.
  `RELY` and `NORELY` are read and not kept.

`GLOBAL TEMPORARY`
: A table whose rows belong to the session. `ON COMMIT DELETE ROWS` (the default) empties it at each commit,
  `PRESERVE ROWS` keeps the rows until the session ends.

`AS subquery`
: A table with the subquery's columns and rows (and no rows when the query returns none).

`ANNOTATIONS`
: Names, with or without a value, kept for the table (after the column list) or a column (the last part of its
  definition) and shown in `USER_ANNOTATIONS_USAGE`; see [annotations](annotations.md) and example M below.

## Remarks

- Names are folded to upper case unless quoted: `CREATE TABLE "Mixed Case"` keeps its case.
- The data dictionary shows the table in `USER_TABLES`, its columns in `USER_TAB_COLUMNS`, and its constraints in
  `USER_CONSTRAINTS`.
- Foreign keys check the parent when a row is inserted (ORA-02291) and when a parent is deleted (ORA-02292, unless
  the key says `ON DELETE`).
- The table is made in the current schema, the login's own (a login's schema is made at its first connection). A table
  of the same name in the PostgreSQL door's `public` schema does not stop it, and the new table is the one a bare name
  finds. The PostgreSQL and SQL Server doors see it by its schema and its upper-case name (`sa."EMP"`), not in
  `public`; see [Schemas](../../connect/oracle.md#schemas).
- On a replica, `CREATE GLOBAL TEMPORARY TABLE` is ORA-16000; see [replicas](../../replicas.md).

## Differences from Oracle

- **Not supported (ORA-00900):** `INTERVAL YEAR TO MONTH` and `INTERVAL DAY TO SECOND` columns (the types work in
  expressions), `INVISIBLE` columns, `TABLESPACE`, storage clauses such as `PCTFREE`, `PARTITION BY`,
  `ORGANIZATION INDEX` and `DEFERRABLE`.
- A global temporary table's annotations are kept but not listed in `USER_ANNOTATIONS_USAGE`.
- **Constraint states** (`DISABLE`, `ENABLE`, `NOVALIDATE`) are taken on `CHECK` and foreign key constraints only: on a
  `PRIMARY KEY`, `UNIQUE` or `NOT NULL` they are ORA-00900. `NOT ENFORCED` is ORA-00900 (Oracle 23.26 has none either:
  it gives ORA-02000 or ORA-03075).
- **`GENERATED BY DEFAULT ON NULL AS IDENTITY` is accepted but does not fill the key:** inserting NULL is ORA-01400.
- `XMLTYPE`, `JSON` and `VECTOR` are ORA-00902 (invalid datatype); object and collection types are not supported.
- `USER_CONSTRAINTS` lists no `NOT NULL` constraint, where Oracle lists each as a row of type `C` with the search
  condition `"A" IS NOT NULL` (example K).
- Key names are lexdb's (`EMP_PKEY`, `EMP_DEPT_ID_FKEY`); Oracle uses `SYS_C00...` for a name you did not give.
- Error texts are shorter (ORA-02290 names no constraint; ORA-12899 no column; ORA-02291 and ORA-02292 name no
  constraint).
- **`ON UPDATE CASCADE` is accepted** (a parent's key change then changes the child rows). Oracle has no such clause:
  `ON` must be followed by `DELETE`, and it gives ORA-02000 (`missing DELETE keyword`).
- `USER_TAB_COLUMNS` shows a `RAW(4)` column as `BLOB` (length 4000) and a `CLOB` with length 4000.
- There are no tablespaces and no recycle bin.

## Examples

### A. Columns, defaults, a virtual column and constraints

<!-- example: oracle -->
```sql
CREATE TABLE dept (id NUMBER(4) PRIMARY KEY, name VARCHAR2(30) NOT NULL UNIQUE);
CREATE TABLE emp (
  id NUMBER GENERATED ALWAYS AS IDENTITY,
  dept_id NUMBER(4) NOT NULL,
  name VARCHAR2(40) NOT NULL,
  salary NUMBER(10,2) DEFAULT 1000 CONSTRAINT emp_sal_ck CHECK (salary >= 0),
  bonus NUMBER GENERATED ALWAYS AS (salary / 10) VIRTUAL,
  hired DATE DEFAULT DATE '2026-01-01',
  note VARCHAR2(20) DEFAULT ON NULL 'none',
  CONSTRAINT emp_pk PRIMARY KEY (id),
  CONSTRAINT emp_dept_fk FOREIGN KEY (dept_id) REFERENCES dept (id) ON DELETE CASCADE
);
INSERT INTO dept VALUES (1, 'sales');
INSERT INTO emp (dept_id, name) VALUES (1, 'ann');
SELECT id, dept_id, name, salary, bonus, TO_CHAR(hired, 'YYYY-MM-DD') AS hired, note FROM emp;
```

```text
Table created.

Table created.

1 row created.

1 row created.

ID DEPT_ID NAME SALARY BONUS HIRED      NOTE
-- ------- ---- ------ ----- ---------- ----
 1       1 ann    1000   100 2026-01-01 none

1 row selected.
```

### B. Constraint errors

<!-- example: oracle -->
```sql
INSERT INTO emp (dept_id, name, salary) VALUES (1, 'bob', -5);
INSERT INTO emp (dept_id, name) VALUES (9, 'cy');
INSERT INTO emp (id, dept_id, name) VALUES (50, 1, 'di');
INSERT INTO emp (dept_id, name, note) VALUES (1, 'ed', NULL);
SELECT name, note FROM emp ORDER BY id;
DELETE FROM dept WHERE id = 1;
SELECT COUNT(*) AS employees FROM emp;
```

```text
ERROR:
ORA-02290: check constraint violated

ERROR:
ORA-02291: integrity constraint violated - parent key not found

ERROR:
ORA-32795: cannot insert into a generated always identity column

1 row created.

NAME NOTE
---- ----
ann  none
ed   none

2 rows selected.

1 row deleted.

EMPLOYEES
---------
        0

1 row selected.
```

### C. Types and what the dictionary says

<!-- example: oracle -->
```sql
CREATE TABLE ty (a NUMBER(5,2), b NUMBER(3) NOT NULL, c VARCHAR2(10 CHAR), d CHAR(3), e DATE, f TIMESTAMP(3),
                 g CLOB, h RAW(4), i BINARY_DOUBLE, j FLOAT(10), k INTEGER, l BOOLEAN);
SELECT column_name, data_type, data_length, data_precision, data_scale, nullable
FROM user_tab_columns WHERE table_name = 'TY' ORDER BY column_id;
```

```text
Table created.

COLUMN_NAME DATA_TYPE     DATA_LENGTH DATA_PRECISION DATA_SCALE NULLABLE
----------- ------------- ----------- -------------- ---------- --------
A           NUMBER                 22              5          2 Y
B           NUMBER                 22              3          0 N
C           VARCHAR2               10                           Y
D           CHAR                    3                           Y
E           DATE                    7                           Y
F           TIMESTAMP(3)           11                         3 Y
G           CLOB                 4000                           Y
H           BLOB                 4000                           Y
I           BINARY_DOUBLE           8                           Y
J           NUMBER                 22                           Y
K           NUMBER                 22                         0 Y
L           BOOLEAN                 1                           Y

12 rows selected.
```

### D. Identity columns

<!-- example: oracle -->
```sql
CREATE TABLE t11 (id NUMBER GENERATED BY DEFAULT AS IDENTITY (START WITH 100 INCREMENT BY 10), v NUMBER);
INSERT INTO t11 (v) VALUES (1);
INSERT INTO t11 (v) VALUES (2);
INSERT INTO t11 (id, v) VALUES (5, 3);
SELECT * FROM t11 ORDER BY v;
```

```text
Table created.

1 row created.

1 row created.

1 row created.

 ID V
--- -
100 1
110 2
  5 3

3 rows selected.
```

### E. A table from a query

<!-- example: oracle -->
```sql
CREATE TABLE t3 AS SELECT id, name FROM emp WHERE dept_id = 1;
SELECT COUNT(*) AS rows_copied FROM t3;
CREATE TABLE t4 AS SELECT id FROM emp WHERE 1 = 0;
SELECT COUNT(*) AS rows_copied FROM t4;
```

```text
Table created.

ROWS_COPIED
-----------
          0

1 row selected.

Table created.

ROWS_COPIED
-----------
          0

1 row selected.
```

### F. Foreign keys with several columns, and ON DELETE SET NULL

<!-- example: oracle -->
```sql
CREATE TABLE t16 (a NUMBER, b NUMBER, CONSTRAINT pk16 PRIMARY KEY (a, b));
CREATE TABLE t17 (a NUMBER, b NUMBER, CONSTRAINT fk17 FOREIGN KEY (a, b) REFERENCES t16 (a, b));
SELECT constraint_name, constraint_type, table_name, r_constraint_name, delete_rule
FROM user_constraints WHERE table_name IN ('T16', 'T17') ORDER BY constraint_name;
CREATE TABLE a6 (id NUMBER PRIMARY KEY, ref NUMBER, CONSTRAINT a6_fk FOREIGN KEY (ref) REFERENCES a6 (id) ON DELETE SET NULL);
INSERT INTO a6 VALUES (1, NULL);
INSERT INTO a6 VALUES (2, 1);
DELETE FROM a6 WHERE id = 1;
SELECT id, ref FROM a6;
```

```text
Table created.

Table created.

CONSTRAINT_NAME CONSTRAINT_TYPE TABLE_NAME R_CONSTRAINT_NAME DELETE_RULE
--------------- --------------- ---------- ----------------- -----------
FK17            R               T17        PK16              NO ACTION
PK16            P               T16

2 rows selected.

Table created.

1 row created.

1 row created.

1 row deleted.

ID REF
-- ---
 2

1 row selected.
```

### G. Global temporary tables

<!-- example: oracle -->
```sql
CREATE GLOBAL TEMPORARY TABLE gtt (id NUMBER, v VARCHAR2(10)) ON COMMIT DELETE ROWS;
INSERT INTO gtt VALUES (1, 'a');
SELECT COUNT(*) AS before_commit FROM gtt;
COMMIT;
SELECT COUNT(*) AS after_commit FROM gtt;
CREATE GLOBAL TEMPORARY TABLE gtt2 (id NUMBER) ON COMMIT PRESERVE ROWS;
INSERT INTO gtt2 VALUES (1);
COMMIT;
SELECT COUNT(*) AS kept FROM gtt2;
```

```text
Table created.

1 row created.

BEFORE_COMMIT
-------------
            1

1 row selected.

Commit complete.

AFTER_COMMIT
------------
           0

1 row selected.

Table created.

1 row created.

Commit complete.

KEPT
----
   1

1 row selected.
```

### H. Names in quotes

<!-- example: oracle -->
```sql
CREATE TABLE "Mixed Case" (a NUMBER);
SELECT table_name FROM user_tables WHERE table_name LIKE 'Mixed%';
```

```text
Table created.

TABLE_NAME
----------
Mixed Case

1 row selected.
```

### I. Constraints that are disabled or not validated

<!-- example: oracle -->
```sql
CREATE TABLE lot (id NUMBER PRIMARY KEY);
INSERT INTO lot VALUES (1);
CREATE TABLE crate (
  id NUMBER PRIMARY KEY,
  weight NUMBER CONSTRAINT crate_weight_ck CHECK (weight > 0) DISABLE,
  lot_id NUMBER CONSTRAINT crate_lot_fk REFERENCES lot (id) ENABLE NOVALIDATE,
  CONSTRAINT crate_id_ck CHECK (id > 0)
);
INSERT INTO crate VALUES (1, -5, 1);
INSERT INTO crate VALUES (2, 5, 99);
INSERT INTO crate VALUES (-3, 5, 1);
SELECT constraint_name, constraint_type, status, validated FROM user_constraints
WHERE table_name = 'CRATE' ORDER BY constraint_name;
```

```text
Table created.

1 row created.

Table created.

1 row created.

ERROR:
ORA-02291: integrity constraint violated - parent key not found

ERROR:
ORA-02290: check constraint violated

CONSTRAINT_NAME CONSTRAINT_TYPE STATUS   VALIDATED
--------------- --------------- -------- -------------
CRATE_ID_CK     C               ENABLED  VALIDATED
CRATE_LOT_FK    R               ENABLED  NOT VALIDATED
CRATE_PKEY      P               ENABLED  VALIDATED
CRATE_WEIGHT_CK C               DISABLED NOT VALIDATED

4 rows selected.
```

### J. Errors

<!-- example: oracle -->
```sql
CREATE TABLE emp (a NUMBER);
CREATE TABLE t5 (a NUMBER(39));
CREATE TABLE t6 (a NUMBER, a NUMBER);
CREATE TABLE t7 (a NUMBER PRIMARY KEY, b NUMBER PRIMARY KEY);
CREATE TABLE x1 (a XMLTYPE);
```

```text
ERROR:
ORA-00955: name is already used by an existing object

ERROR:
ORA-01727: numeric precision specifier is out of range (1 to 38)

ERROR:
ORA-00957: duplicate column name

ERROR:
ORA-02260: table can have only one primary key

ERROR:
ORA-00902: invalid datatype
```

### K. What lexdb does not take

<!-- example: oracle -->
```sql
CREATE TABLE u1 (a INTERVAL DAY TO SECOND);
CREATE TABLE u2 (a NUMBER) TABLESPACE users;
CREATE TABLE u3 (a NUMBER INVISIBLE);
CREATE TABLE u4 (a NUMBER) PARTITION BY HASH (a) PARTITIONS 2;
CREATE TABLE u5 (id NUMBER, CONSTRAINT u5_pk PRIMARY KEY (id) DEFERRABLE INITIALLY DEFERRED);
CREATE TABLE u6 (id NUMBER GENERATED BY DEFAULT ON NULL AS IDENTITY, v NUMBER);
INSERT INTO u6 (id, v) VALUES (NULL, 1);
CREATE TABLE u7 (a NUMBER PRIMARY KEY DISABLE);
CREATE TABLE u8 (a NUMBER NOT NULL DISABLE);
CREATE TABLE u9 (a NUMBER CHECK (a > 0) NOT ENFORCED);
CREATE TABLE u10 (a NUMBER ANNOTATIONS (Owner 'sales'));
CREATE TABLE u11 (a NUMBER NOT NULL, b NUMBER CHECK (b > 0));
SELECT constraint_type, search_condition FROM user_constraints WHERE table_name = 'U11';
```

```text
ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

Table created.

ERROR:
ORA-01400: cannot insert NULL into ("SA"."U6"."ID")

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

Table created.

Table created.

CONSTRAINT_TYPE SEARCH_CONDITION
--------------- ----------------
C               b > 0

1 row selected.
```

### L. The same name in the PostgreSQL door and the login's schema

A table that the PostgreSQL door made is in `public`. The Oracle login can make a table of the same name in its own
schema. A bare name then finds the login's table, and `public.place` the other. The PostgreSQL door sees the Oracle
table as `sa."PLACE"`.

<!-- example: postgresql -->
```sql
CREATE TABLE place (id int, note text);
INSERT INTO place VALUES (1, 'made in the PostgreSQL door');
```

```text
CREATE TABLE
INSERT 0 1
```

<!-- example: oracle -->
```sql
SELECT note FROM place;
CREATE TABLE place (id NUMBER, note VARCHAR2(40));
INSERT INTO place VALUES (2, 'made in the Oracle door');
COMMIT;
SELECT note FROM place;
SELECT note FROM public.place;
SELECT note FROM sa.place;
```

```text
NOTE
---------------------------
made in the PostgreSQL door

1 row selected.

Table created.

1 row created.

Commit complete.

NOTE
-----------------------
made in the Oracle door

1 row selected.

NOTE
---------------------------
made in the PostgreSQL door

1 row selected.

NOTE
-----------------------
made in the Oracle door

1 row selected.
```

<!-- example: postgresql -->
```sql
SELECT note FROM place;
SELECT note FROM sa."PLACE";
```

```text
            note
-----------------------------
 made in the PostgreSQL door
(1 row)

          note
-------------------------
 made in the Oracle door
(1 row)
```

### M. Annotations

`Searchable` and `Audited` are flags, without a value.

<!-- example: oracle -->
```sql
CREATE TABLE item (
  id NUMBER PRIMARY KEY ANNOTATIONS (Display 'Item id'),
  name VARCHAR2(40) NOT NULL ANNOTATIONS (Display 'Name', Searchable)
) ANNOTATIONS (Owner 'sales', Audited);
SELECT column_name, annotation_name, annotation_value FROM user_annotations_usage
WHERE object_name = 'ITEM' ORDER BY column_name NULLS FIRST, annotation_name;
CREATE TABLE item2 (id NUMBER ANNOTATIONS (Display 'x') NOT NULL);
```

```text
Table created.

COLUMN_NAME ANNOTATION_NAME ANNOTATION_VALUE
----------- --------------- ----------------
            AUDITED
            OWNER           sales
ID          DISPLAY         Item id
NAME        DISPLAY         Name
NAME        SEARCHABLE

5 rows selected.

ERROR:
ORA-03099: unexpected item NOT in a column definition
```

### N. A NUMBER foreign key to an identity key

A foreign key compares values, so a `NUMBER` column can refer to a `NUMBER GENERATED ... AS IDENTITY` key (lexdb keeps
the identity key as an integer) and an `INTEGER` column to a plain `NUMBER` key. 5 and 5.0 find the parent 5; 5.5
finds nothing. A column of a type Oracle does not allow in a foreign key to a number (`VARCHAR2`, `BINARY_DOUBLE`) is
ORA-02267.

<!-- example: oracle -->
```sql
CREATE TABLE site (id NUMBER GENERATED ALWAYS AS IDENTITY PRIMARY KEY, name VARCHAR2(20));
INSERT INTO site (name) VALUES ('north');
INSERT INTO site (name) VALUES ('south');
CREATE TABLE booth (id NUMBER PRIMARY KEY, site_id NUMBER REFERENCES site (id));
INSERT INTO booth VALUES (1, 1);
INSERT INTO booth VALUES (2, 2.0);
INSERT INTO booth VALUES (3, 2.5);
INSERT INTO booth VALUES (4, 99);
SELECT id, site_id FROM booth ORDER BY id;
CREATE TABLE booth2 (id NUMBER, site_id VARCHAR2(5) REFERENCES site (id));
CREATE TABLE booth3 (id NUMBER, site_id BINARY_DOUBLE REFERENCES site (id));
```

```text
Table created.

1 row created.

1 row created.

Table created.

1 row created.

1 row created.

ERROR:
ORA-02291: integrity constraint violated - parent key not found

ERROR:
ORA-02291: integrity constraint violated - parent key not found

ID SITE_ID
-- -------
 1       1
 2       2

2 rows selected.

ERROR:
ORA-02267: column type incompatible with referenced column type

ERROR:
ORA-02267: column type incompatible with referenced column type
```

## See also

[ALTER TABLE](alter-table.md), [DROP TABLE](drop-table.md), [INSERT](insert.md), [CREATE INDEX](create-index.md),
[CREATE SEQUENCE](create-sequence.md), [Annotations](annotations.md)
