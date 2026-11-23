# ROLLBACK, ABORT

Ends a transaction block and undoes its changes.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
ROLLBACK [ WORK | TRANSACTION ]
ABORT [ WORK | TRANSACTION ]
```

## Arguments

`WORK`, `TRANSACTION`
: Optional words.

## Remarks

- Every change of the block is undone: rows, and DDL such as `CREATE TABLE`. Values taken by `nextval`, and
  `ALTER SEQUENCE ... RESTART`, are not.
- The block's row locks are released.
- `ROLLBACK` ends a block that an error aborted.
- To undo part of a block, see [ROLLBACK TO SAVEPOINT](rollback-to-savepoint.md).

## Differences from PostgreSQL

- `ROLLBACK` outside a block gives no `WARNING` (PostgreSQL: `there is no transaction in progress`).
- `ROLLBACK AND CHAIN` is a syntax error.

## Examples

<!--setup: postgresql
CREATE TABLE acct (id int PRIMARY KEY, bal int);
INSERT INTO acct VALUES (1, 100);
CREATE SEQUENCE ticket_no;
-->

The examples use a table and a sequence:

```sql
CREATE TABLE acct (id int PRIMARY KEY, bal int);
INSERT INTO acct VALUES (1, 100);
CREATE SEQUENCE ticket_no;
```

### A. Undo a block

<!-- example: postgresql -->
```sql
BEGIN;
DELETE FROM acct;
CREATE TABLE note (body text);
ROLLBACK;
SELECT * FROM acct;
SELECT count(*) FROM pg_tables WHERE tablename = 'note';
```

```text
BEGIN
DELETE 1
CREATE TABLE
ROLLBACK
 id | bal
----+-----
  1 | 100
(1 row)

 count
-------
     0
(1 row)
```

### B. Sequences are not rolled back

<!-- example: postgresql -->
```sql
BEGIN;
SELECT nextval('ticket_no');
ABORT;
SELECT nextval('ticket_no');
```

```text
BEGIN
 nextval
---------
       1
(1 row)

ROLLBACK
 nextval
---------
       2
(1 row)
```

### C. After an error

<!-- example: postgresql -->
```sql
BEGIN;
INSERT INTO acct VALUES (1, 5);
SELECT * FROM acct;
ROLLBACK;
SELECT * FROM acct;
BEGIN;
ROLLBACK AND CHAIN;
ROLLBACK;
```

```text
BEGIN
ERROR:  duplicate key value violates unique constraint "acct_pkey"
DETAIL:  Key (id)=(1) already exists.
ERROR:  current transaction is aborted, commands ignored until end of transaction block
ROLLBACK
 id | bal
----+-----
  1 | 100
(1 row)

BEGIN
ERROR:  syntax error at or near "and"
ROLLBACK
```

## See also

[BEGIN](begin.md) · [COMMIT](commit.md) · [ROLLBACK TO SAVEPOINT](rollback-to-savepoint.md)
