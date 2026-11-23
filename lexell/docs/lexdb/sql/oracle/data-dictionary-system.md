# Data dictionary: users, privileges, parameters and the V$ views

`USER_USERS`, `ALL_USERS`, `DBA_USERS`, `USER_TAB_PRIVS`, `SESSION_PRIVS`, `SESSION_ROLES`,
`NLS_SESSION_PARAMETERS`, `NLS_DATABASE_PARAMETERS`, `DATABASE_PROPERTIES`, `PRODUCT_COMPONENT_VERSION`, `V$VERSION`,
`V$INSTANCE`, `V$DATABASE`, `V$SESSION`, `V$PARAMETER`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
SELECT ... FROM view_name
```

## Views

`USER_USERS`
: One row for the login: `USERNAME`, `USER_ID`, `ACCOUNT_STATUS` (`OPEN`), `DEFAULT_TABLESPACE` (`USERS`),
  `TEMPORARY_TABLESPACE`.

`ALL_USERS`, `DBA_USERS`
: The users that can log in (those granted `CREATE SESSION` or `CONNECT`), and fixed names Oracle databases have
  (`SYS`, `SYSTEM`, ...). See [CREATE USER](create-user.md).

`USER_TAB_PRIVS`, `ALL_TAB_PRIVS`
: The object privileges given with [GRANT](grant.md): `GRANTEE`, `OWNER`, `TABLE_NAME`, `GRANTOR`, `PRIVILEGE`,
  `GRANTABLE` (always `NO`).

`SESSION_PRIVS`, `SESSION_ROLES`, `USER_ROLE_PRIVS`
: A recorded list of Oracle's own privileges and roles; they do not change with `GRANT`.

`NLS_SESSION_PARAMETERS`, `NLS_DATABASE_PARAMETERS`, `NLS_INSTANCE_PARAMETERS`
: The NLS parameters: `PARAMETER`, `VALUE`. They are fixed: `ALTER SESSION SET NLS_DATE_FORMAT` changes how
  dates print (see [ALTER SESSION](alter-session.md)) but not `NLS_SESSION_PARAMETERS`.

`DATABASE_PROPERTIES`, `PRODUCT_COMPONENT_VERSION`, `V$VERSION`
: Properties of the database (`NLS_CHARACTERSET` `AL32UTF8`) and its version: Oracle Database 23ai Free 23.4.

`V$INSTANCE`, `V$DATABASE`, `V$SESSION`, `V$PARAMETER`, `V$MYSTAT`, `V$SESSTAT`, `V$STATNAME`, `V$TRANSACTION`, `V$LOCK`, `V$SQL`
: Dynamic views. `V$DATABASE` has the name (`LEXDB`) and `OPEN_MODE`; `V$INSTANCE` the host and version;
  `V$SESSION` one row per session; `V$PARAMETER` a few recorded parameters (`db_name`).

## Remarks

- `V$` views need no special grant here.
- The session's own row in `V$SESSION` has `STATUS` `ACTIVE` and `TYPE` `USER`.
- `PRODUCT_COMPONENT_VERSION` and `V$VERSION` report Oracle Database 23ai Free, the version the door reports to
  clients.

## Differences from Oracle

- `SESSION_PRIVS`, `SESSION_ROLES` and `USER_ROLE_PRIVS` do not show what the session was really granted.
- `DBA_SYS_PRIVS`, `DBA_ROLE_PRIVS` and `DBA_ROLES` have no rows.
- `NLS_SESSION_PARAMETERS` does not follow `ALTER SESSION` (example C).
- `V$` views show a few rows of recorded values, not live statistics.

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

### A. The current user

<!-- example: oracle -->
```sql
SELECT username, account_status, default_tablespace FROM user_users;
SELECT user FROM dual;
```

```text
USERNAME ACCOUNT_STATUS DEFAULT_TABLESPACE
-------- -------------- ------------------
SA       OPEN           USERS

1 row selected.

USER
----
SA

1 row selected.
```

### B. Privileges

<!-- example: oracle -->
```sql
CREATE USER ann IDENTIFIED BY pw;
GRANT SELECT ON emp TO ann;
GRANT CREATE SESSION TO ann;
SELECT grantee, table_name, privilege, grantable FROM user_tab_privs;
SELECT username FROM all_users WHERE username = 'ANN';
```

```text
User created.

Grant succeeded.

Grant succeeded.

GRANTEE TABLE_NAME PRIVILEGE GRANTABLE
------- ---------- --------- ---------
ANN     EMP        SELECT    NO

1 row selected.

USERNAME
--------
ANN

1 row selected.
```

### C. NLS parameters

<!-- example: oracle -->
```sql
SELECT parameter, value FROM nls_session_parameters WHERE parameter IN ('NLS_DATE_FORMAT', 'NLS_LANGUAGE', 'NLS_SORT') ORDER BY parameter;
ALTER SESSION SET NLS_DATE_FORMAT = 'YYYY-MM-DD';
SELECT parameter, value FROM nls_session_parameters WHERE parameter = 'NLS_DATE_FORMAT';
SELECT parameter, value FROM nls_database_parameters WHERE parameter IN ('NLS_CHARACTERSET', 'NLS_LANGUAGE') ORDER BY parameter;
```

```text
PARAMETER       VALUE
--------------- ---------
NLS_DATE_FORMAT DD-MON-RR
NLS_LANGUAGE    AMERICAN
NLS_SORT        BINARY

3 rows selected.

Session altered.

PARAMETER       VALUE
--------------- ---------
NLS_DATE_FORMAT DD-MON-RR

1 row selected.

PARAMETER        VALUE
---------------- --------
NLS_CHARACTERSET AL32UTF8
NLS_LANGUAGE     AMERICAN

2 rows selected.
```

### D. Version and properties

<!-- example: oracle -->
```sql
SELECT banner FROM v$version;
SELECT product, version FROM product_component_version;
SELECT property_name, property_value FROM database_properties WHERE property_name = 'NLS_CHARACTERSET';
```

```text
BANNER
-------------------------------------------------------------------------------
Oracle Database 23ai Free Release 23.0.0.0.0 - Develop, Learn, and Run for Free

1 row selected.

PRODUCT                   VERSION
------------------------- ----------
Oracle Database 23ai Free 23.0.0.0.0

1 row selected.

PROPERTY_NAME    PROPERTY_VALUE
---------------- --------------
NLS_CHARACTERSET AL32UTF8

1 row selected.
```

### E. The instance, database and session

<!-- example: oracle -->
```sql
SELECT instance_name, status, version FROM v$instance;
SELECT name, open_mode FROM v$database;
SELECT username, status, type FROM v$session;
SELECT name, value FROM v$parameter WHERE name = 'db_name';
```

```text
INSTANCE_NAME STATUS VERSION
------------- ------ ----------
lexdb         OPEN   23.0.0.0.0

1 row selected.

NAME  OPEN_MODE
----- ----------
LEXDB READ WRITE

1 row selected.

USERNAME STATUS TYPE
-------- ------ ----
SA       ACTIVE USER

1 row selected.

NAME    VALUE
------- -----
db_name FREE

1 row selected.
```

## See also

[Tables, columns and constraints](data-dictionary-tables.md), [Programs, sequences and views](data-dictionary-programs.md),
[GRANT](grant.md), [ALTER SESSION](alter-session.md)
