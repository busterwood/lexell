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
| ORA-00942 | A table, view or sequence that does not exist (the message names `"SCHEMA"."NAME"`). |
| ORA-00947 | Not enough values in an `INSERT`. |
| ORA-00955 | A name that is already used by an object. |
| ORA-00957 | A duplicate column name. |
| ORA-00979 | A select-list column that is not in `GROUP BY`. |
| ORA-01418 | An index that does not exist. |
| ORA-02289 | A sequence that does not exist (in `DROP SEQUENCE`). |

### Constraints and data

| Error | Meaning |
|---|---|
| ORA-00001 | A unique or primary key violated. The message names the constraint (`SA.P_PKEY`). |
| ORA-01400 | NULL in a `NOT NULL` column, and an empty string (which is NULL). |
| ORA-02290 | A `CHECK` constraint violated. |
| ORA-02291 | No parent key for a foreign key. |
| ORA-02292 | A child row exists for a parent key being deleted. |
| ORA-02449 | A table dropped while other tables' foreign keys point at it (use `CASCADE CONSTRAINTS`). |
| ORA-12899 | A string too long for the column. |
| ORA-01438 | A number with more digits than the column's precision. |
| ORA-01476 | Division by zero. |
| ORA-01722 | A string that is not a number. |
| ORA-01427 | A subquery that returns more than one row where one is expected. |
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
| ORA-01821, ORA-01882 | A date format that is not one; a time zone region that does not exist. |
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
| ORA-06512 | Added after another error: the line of the block where it was raised. |
| ORA-20000 to ORA-20999 | `RAISE_APPLICATION_ERROR` with your own number; lexdb also uses ORA-20000 for some of its own refusals (a sequence at its limit, a savepoint outside a transaction). |
| ORA-04042 | `GRANT EXECUTE` on a procedure that does not exist. |

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
  ORA-06550, a missing sequence in `NEXTVAL` is ORA-00942, a savepoint that does not exist is ORA-20000
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

## See also

[INSERT](insert.md), [PL/SQL exceptions](README.md#plsql), [Data dictionary](data-dictionary-tables.md)
