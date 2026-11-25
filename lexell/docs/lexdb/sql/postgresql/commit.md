# COMMIT, END

Ends a transaction block and keeps its changes.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
COMMIT [ WORK | TRANSACTION ]
END [ WORK | TRANSACTION ]
```

## Arguments

`WORK`, `TRANSACTION`
: Optional words.

## Remarks

- A deferred [assertion](create-assertion.md) is checked here, with the deferred foreign keys: a violation fails the
  `COMMIT` with 23514 and the transaction is rolled back.
- The block's changes become visible to other sessions, and are on disk before `COMMIT` answers (unless the server
  runs with `--unsafe-no-sync`).
- A read-write block is checked at its commit: if a transaction that committed first changed what it read, the commit
  fails with 40001 (`could not serialize access due to concurrent update`), and nothing is kept. Run the block
  again.
- The deferred foreign key checks (`DEFERRABLE INITIALLY DEFERRED`, or `SET CONSTRAINTS ... DEFERRED`) run at
  `COMMIT`; one that fails rolls the block back (23503).
- `COMMIT` of a block that an error aborted rolls it back, and its tag is `ROLLBACK`.
- The block's row locks are released after the commit.
- `ON COMMIT DELETE ROWS` temporary tables are emptied, and `ON COMMIT DROP` ones dropped.

## Differences from PostgreSQL

- `COMMIT AND CHAIN` is a syntax error.
- `COMMIT` outside a block gives no `WARNING` (PostgreSQL: `there is no transaction in progress`).

## Examples

<!--setup: postgresql
CREATE TABLE acct (id int PRIMARY KEY, bal int);
INSERT INTO acct VALUES (1, 100);
CREATE TABLE owner (id int PRIMARY KEY);
CREATE TABLE pet (name text, owner_id int REFERENCES owner DEFERRABLE INITIALLY DEFERRED);
-->

The examples use these tables:

```sql
CREATE TABLE acct (id int PRIMARY KEY, bal int);
INSERT INTO acct VALUES (1, 100);
CREATE TABLE owner (id int PRIMARY KEY);
CREATE TABLE pet (name text, owner_id int REFERENCES owner DEFERRABLE INITIALLY DEFERRED);
```

### A. COMMIT and END

<!-- example: postgresql -->
```sql
BEGIN;
UPDATE acct SET bal = 90 WHERE id = 1;
COMMIT;
BEGIN WORK;
UPDATE acct SET bal = 80 WHERE id = 1;
END WORK;
SELECT bal FROM acct;
```

```text
BEGIN
UPDATE 1
COMMIT
BEGIN
UPDATE 1
COMMIT
 bal
-----
  80
(1 row)
```

### B. A commit after an error

<!-- example: postgresql -->
```sql
BEGIN;
UPDATE acct SET bal = 0 WHERE id = 1;
SELECT 1 / 0;
COMMIT;
SELECT bal FROM acct;
```

```text
BEGIN
UPDATE 1
ERROR:  division by zero
ROLLBACK
 bal
-----
  80
(1 row)
```

### C. A deferred foreign key, checked at COMMIT

<!-- example: postgresql -->
```sql
BEGIN;
INSERT INTO pet VALUES ('rex', 7);
COMMIT;
BEGIN;
INSERT INTO pet VALUES ('rex', 7);
INSERT INTO owner VALUES (7);
COMMIT;
SELECT * FROM pet;
```

```text
BEGIN
INSERT 0 1
ERROR:  insert or update on table "pet" violates foreign key constraint "pet_owner_id_fkey"
DETAIL:  Key (owner_id)=(7) is not present in table "owner".
BEGIN
INSERT 0 1
INSERT 0 1
COMMIT
 name | owner_id
------+----------
 rex  |        7
(1 row)
```

## See also

[BEGIN](begin.md) · [ROLLBACK](rollback.md) · [SAVEPOINT](savepoint.md) · [SET CONSTRAINTS](set-constraints.md)
