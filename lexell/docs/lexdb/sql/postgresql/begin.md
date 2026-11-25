# BEGIN, START TRANSACTION

Starts a transaction block: the statements up to `COMMIT` or `ROLLBACK` are one transaction.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
BEGIN [ WORK | TRANSACTION ] [ transaction_mode [, ...] ]
START TRANSACTION [ transaction_mode [, ...] ]

transaction_mode:
    ISOLATION LEVEL { SERIALIZABLE | REPEATABLE READ | READ COMMITTED | READ UNCOMMITTED }
    | READ WRITE | READ ONLY
    | [ NOT ] DEFERRABLE
```

## Arguments

`WORK`, `TRANSACTION`
: Optional words.

`READ WRITE`
: The default: the block may read and write.

`READ ONLY`
: The block reads a snapshot taken at `BEGIN`, and may not write: `INSERT`, `UPDATE`, `DELETE`, `MERGE`, DDL and
  `SELECT ... FOR UPDATE` give 25006.

`ISOLATION LEVEL`
: `READ COMMITTED` and `READ UNCOMMITTED` give a block that takes a new snapshot for each statement (PostgreSQL's
  read committed); `SERIALIZABLE` and `REPEATABLE READ` give the serializable block described below. Without the
  clause the block is serializable, unless the session's `default_transaction_isolation` says otherwise.

`DEFERRABLE`
: Accepted and ignored.

## Remarks

- Outside a block, each statement is a transaction of its own (autocommit).
- **Serializable, checked at commit.** A read-write block reads the latest committed data and notes what it read. At
  `COMMIT`, if another transaction has committed a change to something it read since, the commit fails with 40001
  (`could not serialize access due to concurrent update`) and nothing of the block is kept. The application runs the block again. Row locks
  (`SELECT ... FOR UPDATE`, and the rows `UPDATE` and `DELETE` change) make a second writer wait instead, which
  removes the common case.
- DDL is transactional: `CREATE`, `ALTER` and `DROP` in a block are kept or undone with it. `nextval` and `ALTER
  SEQUENCE ... RESTART` are not undone.
- An error in a block aborts it: later statements give 25P02 (`current transaction is aborted, commands ignored
  until end of transaction block`) until `ROLLBACK`, `ROLLBACK TO SAVEPOINT`, or `COMMIT`, which then rolls back.
- A transaction's writes are held in memory until its commit (lexdb-gaps.md 2.4).

## Differences from PostgreSQL

- **The default level is `serializable`** (PostgreSQL: `read committed`), and `read committed` is opt-in: `BEGIN
  ISOLATION LEVEL READ COMMITTED`, `SET TRANSACTION ISOLATION LEVEL`, `SET default_transaction_isolation` and the
  connection's startup options take it. `READ UNCOMMITTED` is read committed, as in PostgreSQL, but `SHOW
  transaction_isolation` says `read committed` for it (PostgreSQL: `read uncommitted`), and `REPEATABLE READ` runs
  serializable and says `serializable` (PostgreSQL: `repeatable read`). An application written for read committed
  meets 40001 failures unless it asks for the level (lexdb-gaps.md 2.2).
- `BEGIN` ignores words it does not know: `BEGIN nonsense` starts a block where PostgreSQL gives 42601.
- In a `READ ONLY` block, `SHOW transaction_read_only` says `off`.
- `BEGIN` inside a block, and `COMMIT` or `ROLLBACK` outside one, give no `WARNING` (PostgreSQL warns `there is
  already a transaction in progress` and `there is no transaction in progress`).
- `SET TRANSACTION` and `SET SESSION CHARACTERISTICS AS TRANSACTION` take the isolation level (`SET TRANSACTION
  ISOLATION LEVEL` after the block's first statement is 25001 in lexdb; PostgreSQL allows it until a snapshot is
  taken, or when the level stays the same) and ignore `READ ONLY` and `READ WRITE`:
  write the mode in `BEGIN`.
- `PREPARE TRANSACTION` (two-phase commit) is not supported.

## Examples

<!--setup: postgresql
CREATE TABLE acct (id int PRIMARY KEY, bal int CHECK (bal >= 0));
INSERT INTO acct VALUES (1, 100), (2, 50);
-->

The examples use one table:

```sql
CREATE TABLE acct (id int PRIMARY KEY, bal int CHECK (bal >= 0));
INSERT INTO acct VALUES (1, 100), (2, 50);
```

### A. A transfer

<!-- example: postgresql -->
```sql
BEGIN;
UPDATE acct SET bal = bal - 30 WHERE id = 1;
UPDATE acct SET bal = bal + 30 WHERE id = 2;
COMMIT;
SELECT * FROM acct ORDER BY id;
```

```text
BEGIN
UPDATE 1
UPDATE 1
COMMIT
 id | bal
----+-----
  1 |  70
  2 |  80
(2 rows)
```

### B. An error aborts the block

<!-- example: postgresql -->
```sql
BEGIN;
UPDATE acct SET bal = bal - 200 WHERE id = 1;
UPDATE acct SET bal = bal + 200 WHERE id = 2;
COMMIT;
SELECT * FROM acct ORDER BY id;
```

```text
BEGIN
ERROR:  new row for relation "acct" violates check constraint "acct_bal_check"
ERROR:  current transaction is aborted, commands ignored until end of transaction block
ROLLBACK
 id | bal
----+-----
  1 |  70
  2 |  80
(2 rows)
```

### C. A read-only block

<!-- example: postgresql -->
```sql
START TRANSACTION READ ONLY;
SELECT sum(bal) FROM acct;
INSERT INTO acct VALUES (3, 10);
ROLLBACK;
```

```text
BEGIN
 sum
-----
 150
(1 row)

ERROR:  cannot execute INSERT in a read-only transaction
ROLLBACK
```

### D. Isolation levels

The default is serializable. `READ COMMITTED` and `READ UNCOMMITTED` give a block that reads what is committed when each
statement starts; `REPEATABLE READ` is serializable.

<!-- example: postgresql -->
```sql
SHOW transaction_isolation;
BEGIN ISOLATION LEVEL READ COMMITTED;
SHOW transaction_isolation;
COMMIT;
BEGIN ISOLATION LEVEL REPEATABLE READ;
SHOW transaction_isolation;
COMMIT;
BEGIN;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
SHOW transaction_isolation;
COMMIT;
BEGIN;
SELECT 1;
SET TRANSACTION ISOLATION LEVEL READ COMMITTED;
ROLLBACK;
SET default_transaction_isolation = 'read committed';
BEGIN;
SHOW transaction_isolation;
COMMIT;
```

```text
 transaction_isolation
-----------------------
 serializable
(1 row)

BEGIN
 transaction_isolation
-----------------------
 read committed
(1 row)

COMMIT
BEGIN
 transaction_isolation
-----------------------
 serializable
(1 row)

COMMIT
BEGIN
SET
 transaction_isolation
-----------------------
 read committed
(1 row)

COMMIT
BEGIN
 ?column?
----------
        1
(1 row)

ERROR:  SET TRANSACTION ISOLATION LEVEL must be called before any query
ROLLBACK
SET
BEGIN
 transaction_isolation
-----------------------
 read committed
(1 row)

COMMIT
```

### E. DDL in a block

<!-- example: postgresql -->
```sql
BEGIN;
CREATE TABLE audit (id int, note text);
INSERT INTO audit VALUES (1, 'opened');
ROLLBACK;
SELECT * FROM audit;
```

```text
BEGIN
CREATE TABLE
INSERT 0 1
ROLLBACK
ERROR:  relation "audit" does not exist
```

## See also

[COMMIT](commit.md) · [ROLLBACK](rollback.md) · [SAVEPOINT](savepoint.md) · [SET CONSTRAINTS](set-constraints.md) ·
[SELECT](select.md) (`FOR UPDATE`)
