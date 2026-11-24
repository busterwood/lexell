# Errors

The `ORA-` numbers lexdb gives in the Oracle door, with what causes them.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
ORA-nnnnn: message
ORA-06550: line l, column c:
PLS-nnnnn: message
```

## Arguments

lexdb has one internal code per failure (a PostgreSQL SQLSTATE) and the Oracle door gives it the `ORA-` number
Oracle gives the same failure. A refusal of a feature lexdb does not have is **ORA-03001** (`unimplemented feature`),
and a message that begins `lexdb:` says which. An error in PL/SQL source is **ORA-06550** with the `PLS-` line under
it.

### Names and syntax

| Error | Meaning |
|---|---|
| ORA-00900 | Invalid SQL statement: the statement is not one lexdb knows, or it has a clause lexdb does not take. |
| ORA-00903 | Invalid table name. |
| ORA-00904 | Invalid identifier: a column, a function or a pseudo-column that does not exist. |
| ORA-00918 | A column name that is ambiguous. |
| ORA-00960 | A name in `QUALIFY` that two select-list items are named. |
| ORA-00942 | A table or view that does not exist (the message names `"SCHEMA"."NAME"`). |
| ORA-00947 | Not enough values in an `INSERT`. |
| ORA-00955 | A name that is already used by an object. |
| ORA-00957 | A duplicate column name. |
| ORA-00979 | A select-list column that is not in `GROUP BY`. |
| ORA-01418 | An index that does not exist. |
| ORA-02289 | A sequence that does not exist (in `DROP SEQUENCE`, and `NEXTVAL` or `CURRVAL` of a missing or dropped one, and an `INSERT` whose default calls a dropped one). |
| ORA-03049 | `HAVING`, `WINDOW` or a second `QUALIFY` after a `QUALIFY` condition, and `QUALIFY` after `ORDER BY` or `FOR UPDATE`. |
| ORA-01786 | `FOR UPDATE` after `QUALIFY`. |

### Constraints and data

| Error | Meaning |
|---|---|
| ORA-00001 | A unique or primary key violated. The message names the constraint (`SA.P_PKEY`). |
| ORA-01400 | NULL in a `NOT NULL` column, and an empty string (which is NULL). |
| ORA-02290 | A `CHECK` constraint violated. |
| ORA-02291 | No parent key for a foreign key. |
| ORA-02292 | A child row exists for a parent key being deleted. |
| ORA-02293 | `ENABLE`, `VALIDATE` or `ADD CONSTRAINT` of a `CHECK` that a row breaks. |
| ORA-02298 | `ENABLE`, `VALIDATE` or `ADD CONSTRAINT` of a foreign key that a row has no parent for. |
| ORA-02299 | `ADD CONSTRAINT` of a `UNIQUE` key over duplicate values. |
| ORA-02275 | A second foreign key on the same columns and the same referenced columns (`ALTER TABLE`; ORA-02274 in `CREATE TABLE`). |
| ORA-12991 | `DROP COLUMN` of a column a multi-column `CHECK` reads. |
| ORA-02430 | `ENABLE` or `MODIFY CONSTRAINT` of a name that is no constraint of the table (and of a key or `NOT NULL`, which have no state). |
| ORA-02431 | `DISABLE CONSTRAINT` of a name that is no constraint of the table. |
| ORA-30926 | A `MERGE` target row that two source rows match. |
| ORA-08006 | A `MERGE` row that `DELETE WHERE` has deleted and that a later source row matches. |
| ORA-02260 | A second `PRIMARY KEY` in `CREATE TABLE`. |
| ORA-02449 | A table dropped while other tables' foreign keys point at it (use `CASCADE CONSTRAINTS`). |
| ORA-12899 | A string too long for the column. |
| ORA-01438 | A number with more digits than the column's precision. |
| ORA-01476 | Division by zero. |
| ORA-01722 | A string that is not a number. |
| ORA-01427 | A subquery that returns more than one row where one is expected. |
| ORA-01428, ORA-01760 | A function argument out of range (a `REGEXP_` position of 0, say); an illegal match parameter. |
| ORA-12725 to ORA-12732 | A regular expression that cannot be read: unmatched parentheses, bracket, back reference, range, class, repeat count. |
| ORA-01841, ORA-01843 | A date that cannot be read: a bad year or month. |
| ORA-01727 | A `NUMBER` precision out of range (1 to 38). |

### Users, privileges and the session

| Error | Meaning |
|---|---|
| ORA-01917 | A user or role that does not exist (in `GRANT`, `REVOKE`, `DROP ROLE`). |
| ORA-01918 | A user that does not exist (in `ALTER USER`, `DROP USER`). |
| ORA-01920 | A user or role name that is already taken. |
| ORA-01922 | `DROP USER` of a user who owns objects, without `CASCADE`. |
| ORA-01435 | `ALTER SESSION SET CURRENT_SCHEMA` to a user that does not exist. |
| ORA-01821, ORA-01882 | A date format that is not one (or a time zone element on a value without a zone); a time zone region that does not exist. |
| ORA-01857, ORA-01874, ORA-01875 | `NEW_TIME` of a zone that is not one of its abbreviations; a time zone hour beyond 15; a time zone minute beyond 59. |
| ORA-02248 | An `ALTER SESSION` parameter that does not exist. |
| ORA-16000 | A change on a read-only replica. |
| ORA-08177 | A serialization failure: the transaction lost and must be retried. |

### PL/SQL

| Error | Meaning |
|---|---|
| ORA-06550 | A PL/SQL compile error; the next lines give the position and the `PLS-` message. |
| PLS-00103 | A symbol that was not expected: a syntax error. |
| PLS-00201 | An identifier that is not declared: a procedure or variable that does not exist. |
| ORA-01403 | `SELECT ... INTO` found no row (`NO_DATA_FOUND`). |
| ORA-01422 | `SELECT ... INTO` found more than one row (`TOO_MANY_ROWS`). |
| PLS-00302, PLS-00363 | A component the package does not have (`pay.nothere`); a constant used as an assignment target. |
| ORA-06553 | A statement of its own that names a package variable (`SELECT pay.g_count FROM dual`: PLS-221). |
| ORA-04068 | A call into a package that another session compiled again since this session made its state. It is raised once; the next call runs on fresh variables. |
| ORA-06512 | Added after another error: the line of the block where it was raised. |
| ORA-20000 to ORA-20999 | `RAISE_APPLICATION_ERROR` with your own number; lexdb also uses ORA-20000 for some of its own refusals (a sequence at its limit, a savepoint outside a transaction). |
| ORA-04042 | `GRANT EXECUTE` on a procedure that does not exist. |
| ORA-04043 | `ALTER PROCEDURE`, `FUNCTION` or `PACKAGE ... COMPILE` of a unit that does not exist. |
| ORA-06575, PLS-00905 | `CALL` of a unit that is invalid (it was stored with compile errors); a block that names one. |

### Refusals

| Error | Meaning |
|---|---|
| ORA-03001 | A feature lexdb does not have: a trigger, a synonym, a view update, a column list in `GRANT`, `ALTER TABLE ... READ ONLY`. |

## Remarks

- Error texts are shorter than Oracle's: ORA-02290 names no constraint (Oracle: `check constraint (SA.SYS_C008)
  violated`), ORA-12899 names no column and no lengths.
- A statement that fails is undone alone; the transaction and the earlier statements stay.

## Differences from Oracle

- Several errors Oracle gives are different here: `COMMIT COMMENT` is ORA-00900, a missing procedure in `CALL` is
  ORA-06550, a savepoint that does not exist is ORA-20000
  (Oracle: ORA-01086), a sequence past its limit is ORA-20000 (Oracle: ORA-08004).
- `INSERT ALL`, `CREATE TRIGGER` and `CREATE SYNONYM` are refused as above (ORA-00900 and ORA-03001).
- Some statements lexdb does not take are ORA-00900 where Oracle's syntax is fine (a clause lexdb does not know).

## Examples

<!--setup: oracle
CREATE TABLE p (id NUMBER PRIMARY KEY, code VARCHAR2(5) NOT NULL UNIQUE, qty NUMBER(3) CHECK (qty >= 0));
CREATE TABLE c (id NUMBER, p_id NUMBER REFERENCES p (id));
INSERT INTO p VALUES (1, 'a', 1);
COMMIT;
-->

The examples use two tables:

```sql
CREATE TABLE p (id NUMBER PRIMARY KEY, code VARCHAR2(5) NOT NULL UNIQUE, qty NUMBER(3) CHECK (qty >= 0));
CREATE TABLE c (id NUMBER, p_id NUMBER REFERENCES p (id));
INSERT INTO p VALUES (1, 'a', 1);
COMMIT;
```

### A. Names that are not found

<!-- example: oracle -->
```sql
SELECT * FROM nothere;
SELECT nothere FROM p;
SELECT nofunc(1) FROM dual;
SELEC 1 FROM dual;
SELECT 1 FROM;
```

```text
ERROR:
ORA-00942: table or view "SA"."NOTHERE" does not exist

ERROR:
ORA-00904: "NOTHERE": invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00903: invalid table name
```

### B. Constraints

<!-- example: oracle -->
```sql
INSERT INTO p VALUES (1, 'b', 1);
INSERT INTO p (id, code) VALUES (3, NULL);
INSERT INTO p VALUES (3, 'c', -1);
INSERT INTO c VALUES (1, 99);
INSERT INTO c VALUES (1, 1);
DELETE FROM p WHERE id = 1;
ROLLBACK;
```

```text
ERROR:
ORA-00001: unique constraint (SA.P_PKEY) violated

ERROR:
ORA-01400: cannot insert NULL into ("SA"."P"."CODE")

ERROR:
ORA-02290: check constraint violated

ERROR:
ORA-02291: integrity constraint violated - parent key not found

1 row created.

ERROR:
ORA-02292: integrity constraint violated - child record found

Rollback complete.
```

### C. Sizes and conversions

<!-- example: oracle -->
```sql
INSERT INTO p VALUES (4, 'toolong', 1);
INSERT INTO p VALUES (5, 'e', 1000);
INSERT INTO p VALUES (6, 'f');
SELECT 1 / 0 FROM dual;
SELECT TO_NUMBER('x') FROM dual;
SELECT TO_DATE('2026-13-45', 'YYYY-MM-DD') FROM dual;
UPDATE p SET qty = 'abc';
```

```text
ERROR:
ORA-12899: value too large for column

ERROR:
ORA-01438: value larger than specified precision allowed for this column

ERROR:
ORA-00947: not enough values

ERROR:
ORA-01476: divisor is equal to zero

ERROR:
ORA-01722: invalid number

ERROR:
ORA-01843: An invalid month was specified.

ERROR:
ORA-01722: invalid number
```

### D. Queries

<!-- example: oracle -->
```sql
SELECT id, COUNT(*) FROM p;
SELECT id FROM p, c;
SELECT * FROM p WHERE id = (SELECT 1 FROM dual UNION ALL SELECT 2 FROM dual);
```

```text
ERROR:
ORA-00979: not a GROUP BY expression

ERROR:
ORA-00918: column ambiguously defined

ERROR:
ORA-01427: single-row subquery returns more than one row
```

### E. Objects

<!-- example: oracle -->
```sql
CREATE TABLE p (a NUMBER);
CREATE TABLE q (a NOSUCHTYPE);
DROP TABLE nothere;
DROP INDEX nothere;
DROP TABLE p;
```

```text
ERROR:
ORA-00955: name is already used by an existing object

ERROR:
ORA-00902: invalid datatype

ERROR:
ORA-00942: table or view "SA"."NOTHERE" does not exist

ERROR:
ORA-01418: specified index does not exist

ERROR:
ORA-02449: unique/primary keys in table referenced by foreign keys
```

### F. Users and the session

<!-- example: oracle -->
```sql
GRANT SELECT ON p TO nobody;
CREATE USER ann IDENTIFIED BY x;
CREATE USER ann IDENTIFIED BY x;
ALTER SESSION SET BOGUS = 1;
ALTER SESSION SET CURRENT_SCHEMA = nobody;
```

```text
ERROR:
ORA-01917: user or role 'NOBODY' does not exist

User created.

ERROR:
ORA-01920: user name 'ANN' conflicts with another user or role name

ERROR:
ORA-02248: invalid option for ALTER SESSION

ERROR:
ORA-01435: user does not exist
```

### G. PL/SQL errors

<!-- example: oracle -->
```sql
DECLARE
  n NUMBER;
BEGIN
  SELECT id INTO n FROM p WHERE id = 99;
END;
/
DECLARE
  n NUMBER;
BEGIN
  SELECT id INTO n FROM p UNION ALL SELECT 2 FROM dual;
END;
/
BEGIN
  RAISE_APPLICATION_ERROR(-20001, 'custom');
END;
/
BEGIN
  NULL
END;
/
CALL nothere();
CREATE OR REPLACE PACKAGE cnt AS
  n NUMBER := 0;
  PROCEDURE bump;
END cnt;
/
CREATE OR REPLACE PACKAGE BODY cnt AS
  PROCEDURE bump IS
  BEGIN
    n := n + 1;
  END;
END cnt;
/
SELECT cnt.n FROM dual;
BEGIN
  cnt.bump;
  cnt.n := cnt.n + 10;
  DBMS_OUTPUT.PUT_LINE('n is ' || cnt.n);
END;
/
```

```text
ERROR:
ORA-01403: no data found
ORA-06512: at line 4

ERROR:
ORA-01422: exact fetch returned more than the requested number of rows
ORA-06512: at line 4

ERROR:
ORA-20001: custom
ORA-06512: at line 2

ERROR:
ORA-06550: line 3, column 1:
PLS-00103: Encountered the symbol "END" when expecting one of the following: ;

ERROR:
ORA-06550: line 1, column 7:
PLS-00201: identifier 'NOTHERE' must be declared
ORA-06550: line 1, column 7:
PL/SQL: Statement ignored

Package created.

Package body created.

ERROR:
ORA-06553: PLS-221: 'N' is not a procedure or is undefined

n is 11

PL/SQL procedure successfully completed.
```

### H. Features that are refused

<!-- example: oracle -->
```sql
CREATE TRIGGER t BEFORE INSERT ON p FOR EACH ROW BEGIN NULL; END;
/
CREATE SYNONYM s FOR p;
INSERT ALL INTO p VALUES (7, 'g', 1) SELECT 1 FROM dual;
```

```text
ERROR:
ORA-03001: unimplemented feature: lexdb: CREATE TRIGGER is not supported yet (CREATE makes tables, views, indexes, schemas, sequences, types, roles and users)

ERROR:
ORA-03001: unimplemented feature: lexdb: CREATE SYNONYM is not supported yet (CREATE makes tables, views, indexes, schemas, sequences, types, roles and users)

ERROR:
ORA-00900: invalid SQL statement
```

### I. QUALIFY and constraint states

<!-- example: oracle -->
```sql
CREATE TABLE qa (id NUMBER PRIMARY KEY, v NUMBER, CONSTRAINT qa_v_ck CHECK (v > 0) DISABLE);
INSERT INTO qa VALUES (1, -1);
SELECT id AS x, v AS x FROM qa QUALIFY x > 0;
SELECT id FROM qa QUALIFY v > 0 HAVING COUNT(*) > 0;
ALTER TABLE qa ENABLE CONSTRAINT qa_v_ck;
ALTER TABLE qa ENABLE CONSTRAINT nosuch;
ALTER TABLE qa DISABLE CONSTRAINT nosuch;
```

```text
Table created.

1 row created.

ERROR:
ORA-00960: ambiguous column naming in select list

ERROR:
ORA-03049: SQL keyword 'V' is not syntactically valid following 'SELECT id FROM qa QUALIFY '

ERROR:
ORA-02293: cannot validate (QA_V_CK) - check constraint violated

ERROR:
ORA-02430: cannot enable constraint (NOSUCH) - no such constraint

ERROR:
ORA-02431: cannot disable constraint (NOSUCH) - no such constraint
```

## See also

[INSERT](insert.md), [PL/SQL exceptions](README.md#plsql), [Data dictionary](data-dictionary-tables.md)
