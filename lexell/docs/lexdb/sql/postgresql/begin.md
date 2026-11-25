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
- With `default_transaction_read_only` on (see `SET SESSION CHARACTERISTICS`, example G), a block starts read-only, and so
  is a statement outside a block: 25006, except for writes to a temporary table that already exists. `BEGIN READ WRITE`
  and a `SET TRANSACTION READ WRITE` before the first query override it.
- `SET TRANSACTION READ ONLY` makes the block read-only at any time, also after its first query (a write is 25006);
  `SET TRANSACTION READ WRITE` makes a block that was made `READ ONLY` read-write only before its first query (25001
  `transaction read-write mode must be set before any query` after it); in a read-write block it changes nothing. The modes may come in any order, with or without commas. `SHOW transaction_read_only` says `on` in a
  read-only block (example E).
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
- `BEGIN` inside a block, and `COMMIT` or `ROLLBACK` outside one, give no `WARNING` (PostgreSQL warns `there is
  already a transaction in progress` and `there is no transaction in progress`).
- `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` and `READ WRITE` set `default_transaction_read_only`, as `SET
  default_transaction_read_only` and `RESET` do (example G); an isolation level in it is taken, and one alone leaves the
  read-only default as it was. The setting is **not undone** when the block that set it rolls back (PostgreSQL undoes
  it: after `BEGIN; SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY; ROLLBACK;` it is `off` there, `on` in lexdb).
- `SET TRANSACTION` outside a block gives no `WARNING` (PostgreSQL: `SET TRANSACTION can only be used in transaction
  blocks`), and does nothing.
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

### E. READ ONLY, in BEGIN and in SET TRANSACTION

`SET TRANSACTION READ ONLY` makes a block that has been reading read-only from then on. A block made `READ ONLY` can
be made read-write again before its first query.

<!-- example: postgresql -->
```sql
BEGIN;
SELECT sum(bal) FROM acct;
SET TRANSACTION READ ONLY;
SHOW transaction_read_only;
UPDATE acct SET bal = 0;
ROLLBACK;
BEGIN READ ONLY;
SET TRANSACTION READ WRITE;
SHOW transaction_read_only;
ROLLBACK;
BEGIN READ ONLY;
SELECT 1;
SET TRANSACTION READ WRITE;
ROLLBACK;
```

```text
BEGIN
 sum
-----
 150
(1 row)

SET
 transaction_read_only
-----------------------
 on
(1 row)

ERROR:  cannot execute UPDATE in a read-only transaction
ROLLBACK
BEGIN
SET
 transaction_read_only
-----------------------
 off
(1 row)

ROLLBACK
BEGIN
 ?column?
----------
        1
(1 row)

ERROR:  transaction read-write mode must be set before any query
ROLLBACK
```

### F. DDL in a block

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

### G. The session's default

`SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` makes later blocks, and statements outside a block, read-only
until a block asks for `READ WRITE` or the default is set back.

<!-- example: postgresql -->
```sql
SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY;
SHOW default_transaction_read_only;
UPDATE acct SET bal = bal + 1 WHERE id = 1;
BEGIN;
SHOW transaction_read_only;
UPDATE acct SET bal = bal + 1 WHERE id = 1;
ROLLBACK;
BEGIN READ WRITE;
UPDATE acct SET bal = bal + 1 WHERE id = 1;
ROLLBACK;
SET SESSION CHARACTERISTICS AS TRANSACTION READ WRITE;
SHOW default_transaction_read_only;
```

```text
SET
 default_transaction_read_only
-------------------------------
 on
(1 row)

ERROR:  cannot execute UPDATE in a read-only transaction
BEGIN
 transaction_read_only
-----------------------
 on
(1 row)

ERROR:  cannot execute UPDATE in a read-only transaction
ROLLBACK
BEGIN
UPDATE 1
ROLLBACK
SET
 default_transaction_read_only
-------------------------------
 off
(1 row)
```

## See also

[COMMIT](commit.md) · [ROLLBACK](rollback.md) · [SAVEPOINT](savepoint.md) · [SET CONSTRAINTS](set-constraints.md) ·
[SELECT](select.md) (`FOR UPDATE`)
