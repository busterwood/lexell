# Transactions

How a transaction starts and ends in each door, what isolation lexdb gives, and what to do when a commit fails.

## Isolation

- Every transaction that writes runs at **serializable** isolation, phantoms included. At commit lexdb checks whether
  anything the transaction read has changed. If so the commit fails with a serialization error and the client
  retries the whole transaction.
- A transaction that only reads sees a **snapshot**: the database as it was when the transaction began. It never
  waits for writers, and writers never wait for it.
- The isolation levels each door accepts (`SET TRANSACTION ISOLATION LEVEL ...`, `BEGIN ISOLATION LEVEL ...`) are
  read and **do not change anything**: `READ COMMITTED` runs as serializable. In the PostgreSQL door `READ ONLY` is
  enforced (a write gives 25006); in the Oracle door `SET TRANSACTION READ ONLY` is accepted and does not stop
  writes.
- Row locks (`SELECT ... FOR UPDATE`) avoid the retries in the common read-then-update case.

| Door | The serialization failure |
|---|---|
| PostgreSQL | SQLSTATE `40001` |
| SQL Server | error 1205 |
| Oracle | `ORA-08177` |

A program that writes should be ready to run its transaction again after one of these.

## Starting and ending a transaction

| | PostgreSQL | SQL Server | Oracle |
|---|---|---|---|
| Begin | `BEGIN` or `START TRANSACTION`; otherwise each statement is its own transaction | `BEGIN TRANSACTION`; otherwise each statement is its own transaction (`SET IMPLICIT_TRANSACTIONS ON` begins one at the first statement) | the first `INSERT`, `UPDATE`, `DELETE`, `MERGE` or `SELECT ... FOR UPDATE` |
| End | `COMMIT`, `ROLLBACK` | `COMMIT`, `ROLLBACK` | `COMMIT`, `ROLLBACK` |
| Savepoints | `SAVEPOINT`, `ROLLBACK TO` | `SAVE TRANSACTION`, `ROLLBACK TRANSACTION name` | `SAVEPOINT`, `ROLLBACK TO` |
| Reference pages | [BEGIN](sql/postgresql/begin.md), [COMMIT](sql/postgresql/commit.md) | [BEGIN TRANSACTION](sql/tsql/begin-transaction.md), [COMMIT](sql/tsql/commit-transaction.md) | [COMMIT](sql/oracle/commit.md), [ROLLBACK](sql/oracle/rollback.md), [SAVEPOINT](sql/oracle/savepoint.md) |

- A client in **autocommit** mode (a JDBC connection by default) commits after every statement. Turn it off
  (`setAutoCommit(false)`) before using savepoints or an Oracle `ROLLBACK`.
- A **failed statement** is undone by itself; the transaction and the statements before it stay, in every door.
  The exceptions are noted on the pages: in PostgreSQL an error inside a transaction block puts the transaction in
  the aborted state until `ROLLBACK`, and T-SQL's `SET XACT_ABORT ON` rolls back the whole transaction on an error.
- **DDL.** In the PostgreSQL and SQL Server doors most DDL (`CREATE TABLE`, `ALTER TABLE`, ...) is part of the
  transaction and rolls back with it. In the Oracle door DDL commits the open transaction first, as in Oracle.
- **Sequences.** In the PostgreSQL door `nextval` is not rolled back: a value taken in a transaction that rolls back
  is not given again.

## Transactions and replicas

A read replica serves read-only snapshots; a write on a replica is refused (PostgreSQL `25006`, SQL Server 3906, Oracle
`ORA-16000`). Use `WAIT FOR LSN` to read your own writes: see [replicas](replicas.md).

## See also

[Overview](overview.md), [SET TRANSACTION (Oracle)](sql/oracle/set-transaction.md),
[SET TRANSACTION ISOLATION LEVEL (T-SQL)](sql/tsql/set-transaction-isolation-level.md),
[SET XACT_ABORT](sql/tsql/set-xact-abort.md), [Errors (T-SQL)](sql/tsql/errors.md), [Errors (Oracle)](sql/oracle/errors.md)
