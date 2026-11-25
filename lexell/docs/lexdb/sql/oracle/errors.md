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
| ORA-11543 to ORA-11562, ORA-11602 | An `ANNOTATIONS` clause that is not right: a name that is reserved or missing, a value that is empty or not text, a name and value given twice, `DROP` or `REPLACE` in a `CREATE`, an annotation to drop that is not there or to add that is; see [Annotations](annotations.md). ORA-03099, ORA-03076, ORA-03062: something after a column's `ANNOTATIONS`. |

### Property graphs

The errors of [CREATE PROPERTY GRAPH](create-property-graph.md), [DROP PROPERTY GRAPH](drop-property-graph.md) and
[GRAPH_TABLE](graph-table.md), with Oracle's numbers and texts.

| Error | Meaning |
|---|---|
| ORA-42421 | A property graph that does not exist (`GRAPH_TABLE`, `DROP PROPERTY GRAPH`). |
| ORA-04045 | `GRAPH_TABLE` over a graph whose table, or a column it names, has been dropped or renamed (a second line gives the cause: ORA-00942 or ORA-00904). |
| ORA-42402, ORA-42442 | An element table without a primary key and without `KEY`; a view without `KEY`. |
| ORA-42404, ORA-42416 | Two elements of one name; a column twice in a `KEY`. |
| ORA-42405 | `REFERENCES` of a name that is no vertex element (a table's name where the element has an alias). |
| ORA-42413, ORA-42431 | `SOURCE` or `DESTINATION` without `KEY`, when the edge table has no foreign key to that vertex table; when it has more than one. |
| ORA-42415 | `KEY (...) REFERENCES v (...)` with lists of different lengths. |
| ORA-42407 | A property twice in one label. |
| ORA-42409, ORA-42414 | A label on two elements with other property names; with a property of another kind of type. |
| ORA-42424, ORA-42439 | A property expression without `AS`; one that calls a function that is not deterministic (`SYSDATE`). |
| ORA-40954, ORA-40951 | A label the graph does not have; `!` in a label expression. |
| ORA-40983, ORA-49044, ORA-49013 | A property no label of the graph has; one the variable's labels do not have; a property of a variable whose label expression no element satisfies. |
| ORA-40984, ORA-40985, ORA-49003 | A quantifier bound out of range (`{0}`, `{3,1}`) or unbounded (`{m,}`); `+` and `*`; `?`. |
| ORA-49028 | A PL/SQL variable inside `GRAPH_TABLE` (a bind is taken). |
| ORA-40997 | A quantifier after a vertex pattern; a `GRAPH_TABLE` without `COLUMNS`. |
| ORA-40990, ORA-40998, ORA-49011, ORA-40956 | A quantified variable outside an aggregate in `COLUMNS`; in the pattern's `WHERE`; an aggregate without a quantified variable (and `COUNT(*)`); `COUNT(e)` without a property. |
| ORA-49000, ORA-40996 | A vertex and an edge variable of one name; a variable that is not in the pattern, or a column of the query outside. |
| ORA-40988 | A subquery inside `GRAPH_TABLE`. |
| ORA-49033 | `ELEMENT_NUMBER` without `ONE ROW PER VERTEX` or `STEP`. |
| ORA-02000 | A `COLUMNS` expression without `AS`; `SOURCE`, `DESTINATION` or `VERTEX` missing in `CREATE PROPERTY GRAPH`. |

### Constraints and data

| Error | Meaning |
|---|---|
| ORA-00001 | A unique or primary key violated. The message names the constraint (`SA.P_PKEY`). |
| ORA-01400 | NULL in a `NOT NULL` column, and an empty string (which is NULL). |
| ORA-02290 | A `CHECK` constraint violated. |
| ORA-02291 | No parent key for a foreign key. |
| ORA-02292 | A child row exists for a parent key being deleted. |
| ORA-02267 | A foreign key column whose type cannot refer to the key's (`VARCHAR2` or `BINARY_DOUBLE` to a `NUMBER`; a `NUMBER` to an identity or `INTEGER` key is taken: [CREATE TABLE](create-table.md), example N). |
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

### Assertions

See [CREATE ASSERTION](create-assertion.md). The same errors come in the other doors as 23514, 547 and the numbers
in [Assertions in the three doors](../../assertions.md#errors-of-each-door).

| Error | Meaning |
|---|---|
| ORA-08601 | A statement broke an assertion (`Assertion (APP.A1) violated.`); the statement is undone. Also `SET CONSTRAINT ... IMMEDIATE`, `ALTER ASSERTION ... ENABLE VALIDATE`, and the first line under ORA-08689 or ORA-02091. |
| ORA-02091 | The `COMMIT` of a deferred assertion that failed: the transaction was rolled back; ORA-08601 is on the next line. |
| ORA-08689 | `CREATE ASSERTION failed`: the next line is the reason (below), or ORA-08601 when the rows there break it. |
| ORA-08661 | The reason: an aggregate, `GROUP BY` or `HAVING`. |
| ORA-08695 | The reason: a subquery under `OR`. |
| ORA-08680 | The reason: a subquery in `SATISFY`. |
| ORA-08697 | The reason: `FETCH FIRST`. |
| ORA-08677 | The reason: `SYSDATE`, `ROWNUM` and the like. |
| ORA-08664 | The reason: a window function. |
| ORA-08678 | The reason: `DUAL`. |
| ORA-08651 | The reason: a view. |
| ORA-08735 | The reason: an ANSI join. |
| ORA-08659 | The reason: `IN` with an aggregate subquery. |
| ORA-08660 | The reason: `WITH`. |
| ORA-08673 | The reason: an equijoin of columns that may be NULL (`Equijoin "A"."G"="B"."G" found does not meet the criteria to do a FAST validation.`). |
| ORA-08702 | `DROP TABLE` (without `CASCADE CONSTRAINTS`), `DROP COLUMN`, `RENAME COLUMN` or `MODIFY` of what an assertion reads (`Columns are referenced by assertion APP.A1.`). |
| ORA-08694 | `RENAME` or `ALTER TABLE ... RENAME TO` of a table an assertion reads. |
| ORA-08687 | `SET CONSTRAINT ... DEFERRED` of an assertion that is not deferrable. |
| ORA-08724 | `NOT DEFERRABLE INITIALLY DEFERRED`. |
| ORA-08725 | `ALTER ASSERTION ... DEFERRABLE`: a deferrability cannot be changed. |
| ORA-08701 | `DISABLE VALIDATE`. |
| ORA-13650 | `DROP` or `ALTER ASSERTION` of an assertion that does not exist. |
| ORA-02443 | `SET CONSTRAINT` of a name that is no constraint or assertion (Oracle: ORA-02448). |

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
| ORA-06575, PLS-00905 | A call of a unit that is invalid (it was stored with compile errors): `CALL` or a function in SQL (and so a `CREATE VIEW` over it); a block that names one. |
| ORA-04063, ORA-04067 | A view over a function, package or property graph that was dropped (`view ... has errors`); a package body that was dropped. |

### Refusals

| Error | Meaning |
|---|---|
| ORA-03001 | A feature lexdb does not have: a trigger, a synonym, a view update, a column list in `GRANT`, `ALTER TABLE ... READ ONLY`, `ONE ROW PER VERTEX` in `GRAPH_TABLE`. |

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

### J. Property graphs

<!-- example: oracle -->
```sql
CREATE PROPERTY GRAPH pg VERTEX TABLES (p);
CREATE PROPERTY GRAPH pg2 VERTEX TABLES (c);
CREATE PROPERTY GRAPH p VERTEX TABLES (p);
SELECT * FROM GRAPH_TABLE (nosuch MATCH (x) COLUMNS (x.id AS id));
SELECT * FROM GRAPH_TABLE (pg MATCH (x IS nolabel) COLUMNS (x.id AS id));
SELECT * FROM GRAPH_TABLE (pg MATCH (x) COLUMNS (x.nosuch AS v));
SELECT * FROM GRAPH_TABLE (pg MATCH (x) COLUMNS (x.id + 1));
SELECT * FROM GRAPH_TABLE (pg MATCH (x){2} COLUMNS (x.id AS id));
DROP PROPERTY GRAPH pg;
DROP PROPERTY GRAPH pg;
```

```text
Property graph created.

ERROR:
ORA-42402: cannot infer key for graph element table C

ERROR:
ORA-00955: name is already used by an existing object

ERROR:
ORA-42421: property graph does not exist

ERROR:
ORA-40954: unknown label

ERROR:
ORA-40983: property "NOSUCH" is never defined

ERROR:
ORA-02000: missing AS keyword

ERROR:
ORA-40997: invalid path pattern expression is specified in a GRAPH_TABLE operator

Property graph dropped.

ERROR:
ORA-42421: property graph does not exist
```

### K. Assertions

<!-- example: oracle -->
```sql
CREATE TABLE ak (id NUMBER PRIMARY KEY, v NUMBER);
CREATE ASSERTION ak_pos CHECK (NOT EXISTS (SELECT 1 FROM ak WHERE v < 0)) DEFERRABLE;
INSERT INTO ak VALUES (1, -1);
SET CONSTRAINT ak_pos DEFERRED;
INSERT INTO ak VALUES (1, -1);
COMMIT;
DROP TABLE ak;
ALTER TABLE ak RENAME TO ak2;
ALTER ASSERTION ak_pos DEFERRABLE;
CREATE ASSERTION ak_bad CHECK (NOT EXISTS (SELECT 1 FROM ak WHERE v < 0)) NOT DEFERRABLE INITIALLY DEFERRED;
DROP ASSERTION nosuch;
```

```text
Table created.

Assertion created.

ERROR:
ORA-08601: Assertion (SA.AK_POS) violated.

Statement processed.

1 row created.

ERROR:
ORA-02091: transaction rolled back
ORA-08601: Assertion (SA.AK_POS) violated.

ERROR:
ORA-08702: Columns are referenced by assertion SA.AK_POS.

ERROR:
ORA-08694: Cannot rename a table referenced in assertion.

ERROR:
ORA-08725: Attempting to modify deferrability of assertion.

ERROR:
ORA-08724: Attempting to set assertion to INITIALLY DEFERRED NOT DEFERRABLE.

ERROR:
ORA-13650: The specified object does not exist for this execution.
```

## See also

[INSERT](insert.md), [PL/SQL exceptions](README.md#plsql), [Data dictionary](data-dictionary-tables.md),
[GRAPH_TABLE](graph-table.md)
