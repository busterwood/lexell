# CREATE ASSERTION

Creates an assertion: a condition over one or more tables that every write to them must leave true.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26.1 and later).

An assertion is the SQL standard's constraint across tables. A `CHECK` constraint sees one row; an assertion sees whole
tables, so it can say that no order is without its customer, that no two rows of a group are both `A` and `B`, or that
a department's salaries stay within its budget. lexdb checks it after each statement that writes a table the assertion
reads, from any door (see [Assertions in the three doors](../../assertions.md)).

## Syntax

```
CREATE ASSERTION [ IF NOT EXISTS ] [ schema. ] assertion
    CHECK ( condition )
    [ ENABLE | DISABLE ] [ VALIDATE | NOVALIDATE ]
    [ [ NOT ] DEFERRABLE ] [ INITIALLY { IMMEDIATE | DEFERRED } ]

condition:
    [ NOT ] EXISTS ( query )
  | ALL ( query ) SATISFY ( search_condition )
```

The condition may be written in any number of brackets: `CHECK ((NOT EXISTS (...)))`, `CHECK (NOT (EXISTS (...)))`.
The state words after `CHECK (...)` may come in any order, each once.

## Arguments

`NOT EXISTS ( query )`
: No row may satisfy the query. This is the usual form: the query finds the rows that break the rule.

`EXISTS ( query )`
: The query must find at least one row. Rows going away (a `DELETE`, an `UPDATE`) may break it.

`ALL ( query ) SATISFY ( search_condition )`
: Every row of a one-column query must satisfy the condition, written over the query's column names (not over the
  tables': `x.v` is ORA-00904). The query may not hold a subquery in `SATISFY`.

`ENABLE`, `DISABLE`
: With `DISABLE` the assertion is kept but not checked. `ENABLE` is the default. `DISABLE` alone means `NOVALIDATE`;
  `DISABLE VALIDATE` is ORA-08701.

`VALIDATE`, `NOVALIDATE`
: With `VALIDATE` (the default) the rows already in the tables must satisfy the assertion, or `CREATE` fails (ORA-08689
  over ORA-08601). With `NOVALIDATE` rows that already break it stay; a row written afterwards that breaks it is
  refused, and the others go in.

`DEFERRABLE`, `NOT DEFERRABLE`
: A deferrable assertion may be checked at `COMMIT` instead of after each statement, by `INITIALLY DEFERRED` or by
  [`SET CONSTRAINT`](alter-assertion.md#set-constraint). `NOT DEFERRABLE` is the default. `NOT DEFERRABLE INITIALLY
  DEFERRED` is ORA-08724.

`INITIALLY IMMEDIATE`, `INITIALLY DEFERRED`
: When the check runs. `INITIALLY DEFERRED` alone makes the assertion `DEFERRABLE`.

`IF NOT EXISTS`
: No error if an assertion of the name is there. (`OR REPLACE` is ORA-00922: drop and create.)

## What a query may hold

Oracle refuses queries it cannot check from the rows a statement wrote; lexdb refuses the same ones with the same
numbers: ORA-08689 `CREATE ASSERTION failed`, with the reason on the next line.

| Reason | In the query |
|---|---|
| ORA-08661 | An aggregate, `GROUP BY` or `HAVING`. |
| ORA-08695 | A subquery under `OR`. |
| ORA-08680 | Two conditions joined by `AND`, a set operation (`UNION`, ...), or a subquery in `SATISFY` (`Consider splitting the assertion definition.`). |
| ORA-08697 | `FETCH FIRST`. |
| ORA-08677 | `SYSDATE`, `ROWNUM` and the like: a value the rows do not decide. |
| ORA-08664 | A window (analytic) function. |
| ORA-08678 | `DUAL`. |
| ORA-08651 | A view. |
| ORA-08735 | An ANSI join (`JOIN ... ON`): write the join in `WHERE`. |
| ORA-08659 | A scalar subquery (`WHERE sal = (SELECT ...)`), and `IN` with an aggregate subquery (`Subquery is not supported.`). |
| ORA-08660 | `WITH`. |
| ORA-08673 | An equijoin of two instances of tables where either column may be NULL. |

Also refused: `ORDER BY` (ORA-00907), a bind variable (ORA-01027), a condition that is no `EXISTS` (`CHECK (1 = 1)`,
ORA-00936).

The equijoin rule (ORA-08673): when two tables meet in `a.g = b.g`, both columns must be `NOT NULL` or a key's, or be
kept from NULL by a condition of their own block (`g > 0`, `g IS NOT NULL`, `g IN (...)`, `g = 5`). Accepted: `NOT
EXISTS`, `EXISTS` and [`NOT`] `IN` (subquery) at any depth, correlated subqueries, inline views in `FROM`, self-joins,
and functions of a row (`UPPER`, `NVL`).

Names are read first: an unknown column is ORA-00904, a table ORA-00942 (a dictionary view too).

## When it is checked

- After each `INSERT`, `UPDATE`, `DELETE` and `MERGE`, and after each statement of a PL/SQL block. A violation is
  ORA-08601 (`Assertion (APP.A1) violated.`) and undoes that statement, not the transaction.
- An `UPDATE` that sets no column the assertion reads is not checked.
- A deferred assertion is checked when the transaction commits: the commit fails with ORA-02091 (`transaction rolled
  back`) over ORA-08601, and the transaction is rolled back. [`SET CONSTRAINT[S]`](alter-assertion.md#set-constraint)
  moves the check: `IMMEDIATE` checks at once and, on a failure, gives ORA-08601 and keeps the transaction.
- Each write path is checked: see [Assertions in the three doors](../../assertions.md#the-write-paths).

## Whose rights the check has

The check runs with the rights of the assertion's owner, in every door, as Oracle's does: a user who has `INSERT`,
`UPDATE` or `DELETE` on an asserted table but no `SELECT` on it is not refused; the write is checked (ORA-08601 when
it breaks the assertion). The user's own `WHERE` and `SELECT` in the statement still need the privilege.

## What DDL does to its tables

| Statement | Result |
|---|---|
| `DROP TABLE` of a table the assertion reads | ORA-08702 (`Columns are referenced by assertion APP.A1.`). `DROP TABLE ... CASCADE CONSTRAINTS` drops the assertion with it. |
| `ALTER TABLE ... DROP COLUMN` or `RENAME COLUMN` of a column it reads | ORA-08702. |
| `ALTER TABLE ... MODIFY` of a column it reads | ORA-08702. |
| `RENAME` or `ALTER TABLE ... RENAME TO` of its table | ORA-08694. |
| `TRUNCATE TABLE` of a table it reads | Checked, as in Oracle: ORA-08601 when the table is the `EXISTS` one, or the one a `NOT EXISTS` looks for (`TRUNCATE` ends the transaction, so it cannot be rolled back; nothing was removed). |
| `ADD COLUMN`, or `DROP` or `RENAME` of another column | Allowed. `ALTER TABLE` that adds, drops, retypes or renames a column of a table the assertion reads sets `USER_ASSERTIONS.INVALID` to `INVALID`, as in Oracle; the assertion is still checked, and `INVALID` stays until the assertion is dropped and made again (example H). `CREATE INDEX`, `COMMENT`, `ADD CONSTRAINT` and `TRUNCATE` leave it. |

## Concurrency

Two sessions that add rows which together break an assertion cannot both succeed. A writer of a table with a join in
the assertion locks the values of the join key before the check; the second writer of the same value waits for the
first's `COMMIT`, then fails with ORA-08601 if the rows together break it, or passes. Writers of other values do not
wait. An assertion without an equijoin locks its tables: the second writer waits, and passes if the first rolls back. A
`DELETE` does not wait for an `INSERT`. A deadlock is ORA-00060.

## Cost

A statement that writes a table an assertion reads pays for one check: the assertion's query run for the rows the
statement wrote (for a `NOT EXISTS` over several tables, restricted to those rows' keys), or, for rows going away and
for an `UPDATE` or `DELETE` that may break a `NOT EXISTS`'s inner tables, the whole query. A table no assertion reads
pays nothing. Many rows put at once (a `COPY`, an array insert) are checked by key, 4,096 at a time.

## Differences from Oracle

- `USER_ASSERTION_LOCK_MATRIX` is empty.
- Writers of rows that meet in an assertion's join key wait for each other. Oracle's locks can be finer, for chains of
  joins.
- Under `NOVALIDATE`, an `UPDATE` or `DELETE` of a table under the assertion's inner `NOT EXISTS` runs the whole query,
  so it fails when rows already break the assertion, where Oracle's row-only check passes (example G).

## Examples

### A. One table: no negative salaries

<!-- example: oracle -->
```sql
CREATE TABLE emp (id NUMBER PRIMARY KEY, name VARCHAR2(20), sal NUMBER);
INSERT INTO emp VALUES (1, 'Ann', 50);
INSERT INTO emp VALUES (2, 'Bob', 30);
COMMIT;
CREATE ASSERTION sal_pos CHECK (NOT EXISTS (SELECT 1 FROM emp WHERE sal < 0));
INSERT INTO emp VALUES (3, 'Cy', -1);
INSERT INTO emp VALUES (3, 'Cy', 10);
SELECT COUNT(*) AS n FROM emp;
```

```text
Table created.

1 row created.

1 row created.

Commit complete.

Assertion created.

ERROR:
ORA-08601: Assertion (SA.SAL_POS) violated.

1 row created.

N
-
3

1 row selected.
```

### B. Two tables: an order needs its customer

<!-- example: oracle -->
```sql
CREATE TABLE customers (id NUMBER PRIMARY KEY, name VARCHAR2(20) NOT NULL);
CREATE TABLE orders (id NUMBER PRIMARY KEY, customer_id NUMBER NOT NULL, total NUMBER);
INSERT INTO customers VALUES (1, 'Ann');
INSERT INTO customers VALUES (2, 'Bob');
INSERT INTO orders VALUES (10, 1, 5);
COMMIT;
CREATE ASSERTION order_has_customer CHECK (NOT EXISTS (
    SELECT 1 FROM orders o
    WHERE NOT EXISTS (SELECT 1 FROM customers c WHERE c.id = o.customer_id)));
INSERT INTO orders VALUES (11, 3, 7);
INSERT INTO orders VALUES (11, 2, 7);
DELETE FROM customers WHERE id = 1;
UPDATE orders SET total = total + 1 WHERE id = 10;
DELETE FROM customers WHERE id = 2;
```

```text
Table created.

Table created.

1 row created.

1 row created.

1 row created.

Commit complete.

Assertion created.

ERROR:
ORA-08601: Assertion (SA.ORDER_HAS_CUSTOMER) violated.

1 row created.

ERROR:
ORA-08601: Assertion (SA.ORDER_HAS_CUSTOMER) violated.

1 row updated.

ERROR:
ORA-08601: Assertion (SA.ORDER_HAS_CUSTOMER) violated.
```

### C. Deferred: checked at COMMIT

<!-- example: oracle -->
```sql
CREATE TABLE budget (dept NUMBER PRIMARY KEY, amount NUMBER);
CREATE ASSERTION budget_pos CHECK (NOT EXISTS (SELECT 1 FROM budget WHERE amount < 0))
    DEFERRABLE INITIALLY DEFERRED;
INSERT INTO budget VALUES (1, -5);
SELECT COUNT(*) AS n FROM budget;
COMMIT;
SELECT COUNT(*) AS n FROM budget;
INSERT INTO budget VALUES (1, -5);
UPDATE budget SET amount = 5 WHERE dept = 1;
COMMIT;
SELECT dept, amount FROM budget;
```

```text
Table created.

Assertion created.

1 row created.

N
-
1

1 row selected.

ERROR:
ORA-02091: transaction rolled back
ORA-08601: Assertion (SA.BUDGET_POS) violated.

N
-
0

1 row selected.

1 row created.

1 row updated.

Commit complete.

DEPT AMOUNT
---- ------
   1      5

1 row selected.
```

### D. ALL ... SATISFY

<!-- example: oracle -->
```sql
CREATE TABLE reading (id NUMBER PRIMARY KEY, v NUMBER);
INSERT INTO reading VALUES (1, 5);
INSERT INTO reading VALUES (2, NULL);
CREATE ASSERTION v_positive CHECK (ALL (SELECT v FROM reading) SATISFY (v > 0));
INSERT INTO reading VALUES (3, -1);
INSERT INTO reading VALUES (3, 7);
SELECT id, v FROM reading ORDER BY id;
```

```text
Table created.

1 row created.

1 row created.

Assertion created.

ERROR:
ORA-08601: Assertion (SA.V_POSITIVE) violated.

1 row created.

ID V
-- -
 1 5
 2
 3 7

3 rows selected.
```

### E. Three refusals at CREATE

<!-- example: oracle -->
```sql
CREATE ASSERTION a1 CHECK (NOT EXISTS (SELECT dept FROM emp_dept GROUP BY dept HAVING COUNT(*) > 9));
CREATE TABLE emp_dept (id NUMBER PRIMARY KEY, dept NUMBER NOT NULL, mgr NUMBER);
CREATE ASSERTION a1 CHECK (NOT EXISTS (SELECT dept FROM emp_dept GROUP BY dept HAVING COUNT(*) > 9));
CREATE ASSERTION a2 CHECK (NOT EXISTS (SELECT 1 FROM emp_dept WHERE id > 5 FETCH FIRST 1 ROWS ONLY));
CREATE ASSERTION a3 CHECK (NOT EXISTS (SELECT 1 FROM emp_dept a, emp_dept b WHERE a.id <> b.id AND a.mgr = b.mgr));
```

```text
ERROR:
ORA-00942: table or view "SA"."EMP_DEPT" does not exist

Table created.

ERROR:
ORA-08689: CREATE ASSERTION failed
ORA-08661: Aggregates are not supported.

ERROR:
ORA-08689: CREATE ASSERTION failed
ORA-08697: SYS owned tables are not supported.

ERROR:
ORA-08689: CREATE ASSERTION failed
ORA-08673: Equijoin "A"."MGR"="B"."MGR" found does not meet the criteria to do a FAST validation.
```

### F. The dictionary

<!-- example: oracle -->
```sql
SELECT assertion_name, status, deferrable, deferred, validated
FROM user_assertions ORDER BY assertion_name;
SELECT assertion_name, referenced_name, validation_type, validation_event
FROM user_assertion_dependencies ORDER BY assertion_name, referenced_id;
```

```text
ASSERTION_NAME     STATUS  DEFERRABLE     DEFERRED  VALIDATED
------------------ ------- -------------- --------- ---------
BUDGET_POS         ENABLED DEFERRABLE     DEFERRED  VALIDATED
ORDER_HAS_CUSTOMER ENABLED NOT DEFERRABLE IMMEDIATE VALIDATED
SAL_POS            ENABLED NOT DEFERRABLE IMMEDIATE VALIDATED
V_POSITIVE         ENABLED NOT DEFERRABLE IMMEDIATE VALIDATED

4 rows selected.

ASSERTION_NAME     REFERENCED_NAME VALIDATION_TYPE VALIDATION_EVENT
------------------ --------------- --------------- ------------------------
BUDGET_POS         BUDGET          FAST            ROWS INSERTED OR UPDATED
ORDER_HAS_CUSTOMER ORDERS          FAST            ROWS INSERTED OR UPDATED
ORDER_HAS_CUSTOMER CUSTOMERS       FAST            ROWS DELETED OR UPDATED
SAL_POS            EMP             FAST            ROWS INSERTED OR UPDATED
V_POSITIVE         READING         FAST            ROWS INSERTED OR UPDATED

5 rows selected.
```

### G. NOVALIDATE, and DDL on the tables

<!-- example: oracle -->
```sql
CREATE TABLE person (id NUMBER PRIMARY KEY, dept NUMBER NOT NULL, role VARCHAR2(5));
CREATE TABLE proj (id NUMBER PRIMARY KEY, dept NUMBER NOT NULL);
INSERT INTO person VALUES (1, 1, 'boss');
INSERT INTO person VALUES (3, 1, 'dev');
INSERT INTO proj VALUES (1, 1);
INSERT INTO proj VALUES (2, 2);
COMMIT;
CREATE ASSERTION proj_has_person CHECK (NOT EXISTS (
    SELECT 1 FROM proj p WHERE NOT EXISTS (SELECT 1 FROM person e WHERE e.dept = p.dept))) NOVALIDATE;
SELECT assertion_name, validated FROM user_assertions WHERE assertion_name = 'PROJ_HAS_PERSON';
INSERT INTO proj VALUES (4, 3);
INSERT INTO person VALUES (5, 1, 'dev');
DELETE FROM person WHERE id = 1;
ALTER TABLE person RENAME COLUMN dept TO d;
ALTER TABLE person MODIFY (dept NUMBER(5));
ALTER TABLE person ADD (note VARCHAR2(10));
ALTER TABLE person RENAME TO staff;
DROP TABLE person;
TRUNCATE TABLE person;
DROP TABLE person CASCADE CONSTRAINTS PURGE;
SELECT COUNT(*) AS n FROM user_assertions WHERE assertion_name = 'PROJ_HAS_PERSON';
```

```text
Table created.

Table created.

1 row created.

1 row created.

1 row created.

1 row created.

Commit complete.

Assertion created.

ASSERTION_NAME  VALIDATED
--------------- -------------
PROJ_HAS_PERSON NOT VALIDATED

1 row selected.

ERROR:
ORA-08601: Assertion (SA.PROJ_HAS_PERSON) violated.

1 row created.

ERROR:
ORA-08601: Assertion (SA.PROJ_HAS_PERSON) violated.

ERROR:
ORA-08702: Columns are referenced by assertion SA.PROJ_HAS_PERSON.

ERROR:
ORA-08702: Columns are referenced by assertion SA.PROJ_HAS_PERSON.

Table altered.

ERROR:
ORA-08694: Cannot rename a table referenced in assertion.

ERROR:
ORA-08702: Columns are referenced by assertion SA.PROJ_HAS_PERSON.

ERROR:
ORA-08601: Assertion (SA.PROJ_HAS_PERSON) violated.

Table dropped.

N
-
0

1 row selected.
```

### H. INVALID, a quoted name and SET CONSTRAINT

<!-- example: oracle -->
```sql
CREATE TABLE stock (id NUMBER PRIMARY KEY, qty NUMBER);
CREATE ASSERTION qty_ok CHECK (NOT EXISTS (SELECT 1 FROM stock WHERE qty < 0));
CREATE ASSERTION "low_ok" CHECK (NOT EXISTS (SELECT 1 FROM stock WHERE qty < -100));
SELECT assertion_name, status, invalid FROM user_assertions WHERE assertion_name IN ('QTY_OK', 'low_ok') ORDER BY assertion_name;
ALTER TABLE stock ADD (note VARCHAR2(10));
SELECT assertion_name, status, invalid FROM user_assertions WHERE assertion_name IN ('QTY_OK', 'low_ok') ORDER BY assertion_name;
INSERT INTO stock VALUES (1, -5, 'x');
SET CONSTRAINT nosuch DEFERRED;
SET CONSTRAINT qty_ok IMMEDIATE;
DROP ASSERTION "low_ok";
```

```text
Table created.

Assertion created.

Assertion created.

ASSERTION_NAME STATUS  INVALID
-------------- ------- -------
QTY_OK         ENABLED
low_ok         ENABLED

2 rows selected.

Table altered.

ASSERTION_NAME STATUS  INVALID
-------------- ------- -------
QTY_OK         ENABLED INVALID
low_ok         ENABLED INVALID

2 rows selected.

ERROR:
ORA-08601: Assertion (SA.QTY_OK) violated.

ERROR:
ORA-02448: constraint does not exist

ERROR:
ORA-08687: Cannot defer an assertion that is not deferrable.

Assertion dropped.
```

## See also

[DROP ASSERTION](drop-assertion.md) · [ALTER ASSERTION and SET CONSTRAINT](alter-assertion.md) ·
[Assertions in the three doors](../../assertions.md) · [Data dictionary](data-dictionary-tables.md) ·
[Errors](errors.md)
