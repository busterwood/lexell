# Data dictionary: views, sequences, procedures and source

`USER_VIEWS`, `USER_SEQUENCES`, `USER_SOURCE`, `USER_PROCEDURES`, `USER_ARGUMENTS`, `USER_ERRORS`, `USER_TRIGGERS`,
`USER_SYNONYMS` and their `ALL_` and `DBA_` forms.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
SELECT ... FROM { USER_ | ALL_ | DBA_ }{ VIEWS | SEQUENCES | SOURCE | PROCEDURES | ARGUMENTS | ERRORS }
```

## Views

`USER_VIEWS`
: `VIEW_NAME`, `TEXT_LENGTH`, `TEXT` (the query as written after `AS`), `READ_ONLY` (`N`).

`USER_SEQUENCES`
: `SEQUENCE_NAME`, `MIN_VALUE`, `MAX_VALUE`, `INCREMENT_BY`, `CYCLE_FLAG`, `ORDER_FLAG`, `CACHE_SIZE` (0),
  `LAST_NUMBER`.

`USER_SOURCE`
: The source of procedures, functions and packages: `NAME`, `TYPE`, `LINE`, `TEXT`, one row per line, starting at
  the unit's keyword (`PROCEDURE name ...`, without `CREATE OR REPLACE`).

`USER_PROCEDURES`
: One row per procedure, function and package: `OBJECT_NAME`, `OBJECT_TYPE`, `AUTHID` (`DEFINER`).

`USER_ARGUMENTS`
: The parameters of procedures and functions.

`USER_ERRORS`
: The compile errors of units that were stored invalid (example F): `NAME`, `TYPE`, `SEQUENCE`, `LINE`, `POSITION`,
  `TEXT` (`PLS-00201: identifier 'NOTHERE' must be declared`, then `PL/SQL: Statement ignored`), `ATTRIBUTE` (`ERROR`),
  `MESSAGE_NUMBER`. `ALL_ERRORS` and `DBA_ERRORS` hold the same rows. A unit with errors is `INVALID` in `USER_OBJECTS`;
  the rows go when the unit compiles again.

`USER_TRIGGERS`, `USER_SYNONYMS`
: No rows: lexdb has no triggers and no synonyms.

## Remarks

- A view's `TEXT` is the query without `CREATE VIEW ... AS`.
- `USER_SOURCE` starts each unit at `PROCEDURE`, `FUNCTION` or `PACKAGE`: the `CREATE OR REPLACE` is not kept.

## Differences from Oracle

- `USER_SOURCE` does not hold the `CREATE OR REPLACE` words that Oracle keeps in line 1.
- `USER_TRIGGERS` and `USER_SYNONYMS` are always empty.
- `USER_SEQUENCES.CACHE_SIZE` is 0 and `LAST_NUMBER` is the start value or the last value handed out.

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

### A. Views

<!-- example: oracle -->
```sql
SELECT view_name, text_length, text, read_only FROM user_views;
```

```text
VIEW_NAME TEXT_LENGTH TEXT                     READ_ONLY
--------- ----------- ------------------------ ---------
V_EMP              24 SELECT id, name FROM emp N

1 row selected.
```

### B. Sequences

<!-- example: oracle -->
```sql
SELECT sequence_name, min_value, max_value, increment_by, cycle_flag, cache_size, last_number FROM user_sequences;
SELECT sq.NEXTVAL AS first_value FROM dual;
SELECT sequence_name, last_number FROM user_sequences;
```

```text
SEQUENCE_NAME MIN_VALUE                    MAX_VALUE INCREMENT_BY CYCLE_FLAG CACHE_SIZE LAST_NUMBER
------------- --------- ---------------------------- ------------ ---------- ---------- -----------
SQ                    1 9999999999999999999999999999            1 N                   0           5

1 row selected.

FIRST_VALUE
-----------
          5

1 row selected.

SEQUENCE_NAME LAST_NUMBER
------------- -----------
SQ                      5

1 row selected.
```

### C. Source

<!-- example: oracle -->
```sql
SELECT name, type, line, text FROM user_source ORDER BY name, line;
```

```text
NAME      TYPE      LINE TEXT
--------- --------- ---- ----------------------------------------------------------------------
DOUBLE_IT FUNCTION     1 FUNCTION double_it (x NUMBER) RETURN NUMBER AS
DOUBLE_IT FUNCTION     2 BEGIN
DOUBLE_IT FUNCTION     3   RETURN x * 2;
DOUBLE_IT FUNCTION     4 END;
RAISE_PAY PROCEDURE    1 PROCEDURE raise_pay (p_id IN NUMBER, p_pct IN NUMBER DEFAULT 10) AS
RAISE_PAY PROCEDURE    2 BEGIN
RAISE_PAY PROCEDURE    3   UPDATE emp SET salary = salary * (1 + p_pct / 100) WHERE id = p_id;
RAISE_PAY PROCEDURE    4 END;

8 rows selected.
```

### D. Procedures and functions

<!-- example: oracle -->
```sql
SELECT object_name, object_type, authid FROM user_procedures ORDER BY object_name;
```

```text
OBJECT_NAME OBJECT_TYPE AUTHID
----------- ----------- -------
DOUBLE_IT   FUNCTION    DEFINER
RAISE_PAY   PROCEDURE   DEFINER

2 rows selected.
```

### E. Triggers and synonyms

<!-- example: oracle -->
```sql
SELECT COUNT(*) AS triggers FROM user_triggers;
SELECT COUNT(*) AS synonyms FROM user_synonyms;
```

```text
TRIGGERS
--------
       0

1 row selected.

SYNONYMS
--------
       0

1 row selected.
```

### F. Errors of a unit that does not compile

<!-- example: oracle -->
```sql
CREATE PROCEDURE broken AS
BEGIN
  nothere(1);
END;
/
SELECT name, type, sequence, line, position, text, attribute, message_number FROM user_errors ORDER BY sequence;
SELECT object_name, status FROM user_objects WHERE status = 'INVALID';
```

```text
Warning: Procedure created with compilation errors.

NAME   TYPE      SEQUENCE LINE POSITION TEXT                                             ATTRIBUTE MESSAGE_NUMBER
------ --------- -------- ---- -------- ------------------------------------------------ --------- --------------
BROKEN PROCEDURE        1    3        3 PLS-00201: identifier 'NOTHERE' must be declared ERROR                201
BROKEN PROCEDURE        2    3        3 PL/SQL: Statement ignored                        ERROR                  0

2 rows selected.

OBJECT_NAME STATUS
----------- -------
BROKEN      INVALID

1 row selected.
```

## See also

[Tables, columns and constraints](data-dictionary-tables.md), [CREATE PROCEDURE](create-procedure.md),
[CREATE VIEW](create-view.md), [CREATE SEQUENCE](create-sequence.md)
