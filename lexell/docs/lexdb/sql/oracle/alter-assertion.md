# ALTER ASSERTION and SET CONSTRAINT

Enables or disables an assertion, and moves the check of a deferrable one to the statement or to the commit.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26.1 and later).

## Syntax

```
ALTER ASSERTION [ schema. ] assertion
    [ ENABLE | DISABLE ] [ VALIDATE | NOVALIDATE ]
```

```
SET { CONSTRAINT | CONSTRAINTS } { assertion [, ...] | ALL } { IMMEDIATE | DEFERRED }
```

## Arguments

`ENABLE VALIDATE`
: The assertion is checked again. The rows now in its tables are checked once: a row that breaks it is ORA-08601 and
  the assertion stays as it was.

`ENABLE NOVALIDATE`
: The assertion is checked for rows written from now on; the rows there are not checked.

`DISABLE`
: Writes are not checked. `USER_ASSERTIONS.STATUS` shows `DISABLED` and `VALIDATED` shows `NOT VALIDATED`.

`ENABLE` alone means `ENABLE VALIDATE`.

`IMMEDIATE`, `DEFERRED` (of `SET CONSTRAINT`)
: `DEFERRED` makes the check wait for `COMMIT` for the rest of the transaction; `IMMEDIATE` checks the writes made so
  far at once (ORA-08601 on a failure, the transaction kept), and then after each statement.

## Remarks

- `ALTER ASSERTION` with nothing after the name is accepted and changes nothing. Its deferrability cannot be changed
  (`ALTER ASSERTION a DEFERRABLE` is ORA-08725), and `RENAME TO` is ORA-00911.
- `SET CONSTRAINT[S] ... DEFERRED` of an assertion that is not `DEFERRABLE` is ORA-08687.
- `SET CONSTRAINT[S] ALL` applies to every deferrable assertion. It takes effect for the transaction
  and lasts to its end; the assertion's own `INITIALLY` setting applies again in the next one.
- A deferred check covers the writes made since the assertion's first statement in the transaction. At `COMMIT` a
  failure is ORA-02091 over ORA-08601 and the transaction is rolled back.
- `ALTER ASSERTION` of a name that does not exist is ORA-13650. `SET CONSTRAINT` of a name that does not exist is
  ORA-02448.

## Differences from Oracle

- `SET CONSTRAINT` of a name that is no constraint or assertion is ORA-02448, as in Oracle; `IMMEDIATE` of an
  assertion that is not deferrable is ORA-08687 too (create-assertion.md, example H). No other difference is known.

## Examples

### A. DISABLE and ENABLE

<!-- example: oracle -->
```sql
CREATE TABLE emp2 (id NUMBER PRIMARY KEY, sal NUMBER);
CREATE ASSERTION sal2_pos CHECK (NOT EXISTS (SELECT 1 FROM emp2 WHERE sal < 0));
ALTER ASSERTION sal2_pos DISABLE;
INSERT INTO emp2 VALUES (1, -9);
SELECT assertion_name, status, validated FROM user_assertions;
ALTER ASSERTION sal2_pos ENABLE;
DELETE FROM emp2;
ALTER ASSERTION sal2_pos ENABLE;
SELECT assertion_name, status, validated FROM user_assertions;
```

```text
Table created.

Assertion created.

Assertion altered.

1 row created.

ASSERTION_NAME STATUS   VALIDATED
-------------- -------- -------------
SAL2_POS       DISABLED NOT VALIDATED

1 row selected.

ERROR:
ORA-08601: Assertion (SA.SAL2_POS) violated.

1 row deleted.

Assertion altered.

ASSERTION_NAME STATUS  VALIDATED
-------------- ------- ---------
SAL2_POS       ENABLED VALIDATED

1 row selected.
```

### B. SET CONSTRAINT

<!-- example: oracle -->
```sql
CREATE TABLE d1 (id NUMBER PRIMARY KEY, v NUMBER);
CREATE ASSERTION d1_neg CHECK (NOT EXISTS (SELECT 1 FROM d1 WHERE v < 0)) DEFERRABLE;
CREATE ASSERTION d1_hundred CHECK (NOT EXISTS (SELECT 1 FROM d1 WHERE v > 100));
SET CONSTRAINT d1_neg DEFERRED;
INSERT INTO d1 VALUES (1, -1);
SET CONSTRAINT d1_neg IMMEDIATE;
UPDATE d1 SET v = 1;
SET CONSTRAINT d1_neg DEFERRED;
INSERT INTO d1 VALUES (2, -2);
COMMIT;
SELECT COUNT(*) AS n FROM d1;
SET CONSTRAINT d1_hundred DEFERRED;
```

```text
Table created.

Assertion created.

Assertion created.

Statement processed.

1 row created.

ERROR:
ORA-08601: Assertion (SA.D1_NEG) violated.

1 row updated.

Statement processed.

1 row created.

ERROR:
ORA-02091: transaction rolled back
ORA-08601: Assertion (SA.D1_NEG) violated.

N
-
0

1 row selected.

ERROR:
ORA-08687: Cannot defer an assertion that is not deferrable.
```

## See also

[CREATE ASSERTION](create-assertion.md), [DROP ASSERTION](drop-assertion.md), [COMMIT](commit.md)
