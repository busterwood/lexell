# Assertions in the three doors

An assertion is a condition over whole tables that every write must leave true: no order without its customer, no
negative stock, no two rows of a group that are both `A` and `B`. It is the SQL standard's `CREATE ASSERTION`
(ISO/IEC 9075-2, 11.47). Oracle AI Database 26ai (23.26.1) has it; **PostgreSQL and SQL Server do not**, and in their
doors `CREATE ASSERTION` is lexdb's own statement, in the standard's form.

One assertion is one object of the database. This page says how it works across the doors; the statements are on the
reference pages:

| Door | Create | Drop | Other |
|---|---|---|---|
| Oracle | [CREATE ASSERTION](sql/oracle/create-assertion.md) | [DROP ASSERTION](sql/oracle/drop-assertion.md) | [ALTER ASSERTION, SET CONSTRAINT](sql/oracle/alter-assertion.md), [views](sql/oracle/data-dictionary-tables.md#views) |
| PostgreSQL | [CREATE ASSERTION](sql/postgresql/create-assertion.md) | [DROP ASSERTION](sql/postgresql/drop-assertion.md) | [SET CONSTRAINTS](sql/postgresql/set-constraints.md) |
| SQL Server | [CREATE ASSERTION](sql/tsql/create-assertion.md) | [DROP ASSERTION](sql/tsql/drop-assertion.md) | [SET CONSTRAINTS](sql/tsql/set-constraints.md) |

## One assertion, three doors

- **Made in any door, enforced for writes from all.** An assertion made in the PostgreSQL door is checked when a
  program writes the same tables through the SQL Server or the Oracle door, and the other way round. Each write fails
  with the door's own error: ORA-08601 (and ORA-02091 at the commit of a deferred one) in the Oracle door, 23514 in
  the PostgreSQL door, 547 in the SQL Server door.
- **Listed in each door's catalog**: `USER_ASSERTIONS` (Oracle), `information_schema.assertions` (PostgreSQL and SQL
  Server). See [below](#the-catalogs).
- **The query is read with the dialect it was made in.** The text is kept as written, with the dialect of the door that
  made it, and the check parses it with that dialect's parser whatever door the write comes from. A query made in the
  Oracle door may call `NVL`; one made in the T-SQL door may use `[dbo].[t]`; each means the same to a writer in
  another door.
- **Dropped from any door.** `DROP ASSERTION` in one door drops it for all.
- **One namespace with tables.** An assertion's name cannot be a table's, view's or sequence's (ORA-00955, 42P07,
  2714), nor the other way round.
- **Replicas never check.** A replica applies what the master decided, so it does not check an assertion; the master
  refuses the write first. `CREATE ASSERTION` on a replica is refused as any DDL is (ORA-16000 in the Oracle door). An
  assertion made on the master is listed on the replica.

An assertion made in the PostgreSQL or SQL Server door is the standard's: `CREATE [IF NOT EXISTS] ASSERTION`, `DROP
ASSERTION`, `SET CONSTRAINTS`, deferral (`DEFERRABLE`, `INITIALLY DEFERRED`). Oracle's door has Oracle's own statement
with its state words (`ENABLE`, `DISABLE`, `VALIDATE`, `NOVALIDATE`) and `ALTER ASSERTION`. Oracle's views name the
owner of an assertion made elsewhere as they name the owner of public's tables (the user, or `SYS`).

## What an assertion's query may be

Oracle's rules, in every door: `NOT EXISTS (query)`, `EXISTS (query)` or `ALL (query) SATISFY (condition)`; no
aggregates, `GROUP BY`, `HAVING`, set operations, `OR` over a subquery, windows, `FETCH FIRST`, views, `WITH`, joins in
`FROM ... JOIN` syntax, values the rows do not decide (time, user, random, sequences), no query without a table, and
an equijoin only of columns that cannot be NULL. A temporary table cannot be read (it goes with its session; the
assertion would stay): 0A000, ORA-08689 or 50000, with the reason. Each door's page has the table of reasons and its
error.

## When it is checked

lexdb runs the assertion's query for the rows a statement wrote, after the statement and before the statement's own
commit. A statement that breaks it is undone and fails; the transaction is kept (PostgreSQL: aborted, as after any
error). Statements of a procedure or PL/SQL block are checked one by one. A deferrable assertion may wait for `COMMIT`:
`INITIALLY DEFERRED`, or `SET CONSTRAINT[S] ... DEFERRED`. A deferred one that fails at `COMMIT` rolls the transaction
back. `SET CONSTRAINT[S] ... IMMEDIATE` checks the waiting writes at once.

A table no assertion reads pays nothing. A table one reads pays for one extra query per writing statement: the query,
restricted to the rows the statement wrote (by key, 4,096 keys at a time for many rows), or the whole query when rows
leave a table under a `NOT EXISTS` or an `EXISTS` condition.

### Concurrency

Two sessions cannot break an assertion together. A writer of a table in an assertion's join takes a lock on the value
of the join key that the assertion joins on, held to the end of its transaction, before the check. The second writer
of the same value waits for the first's `COMMIT` or `ROLLBACK` and then fails, or passes, on what is committed. Writers
of other values do not wait; a `DELETE` does not wait for an `INSERT`; an assertion without an equijoin locks as a whole.
A deadlock between two such writers is the door's deadlock error (40P01 in the PostgreSQL door, ORA-00060 in the Oracle door).

## The write paths

Every way into a table is checked. The answers are the same in each door; what differs is the error.

| Path | What happens |
|---|---|
| `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `INSERT ... SELECT`, `ON CONFLICT` | Checked after the statement. |
| A procedure, function or PL/SQL block | Each statement is checked at its end. A PL/SQL handler that takes ORA-08601 keeps the block going; the statement is undone. A T-SQL procedure's 547 ends that statement only. |
| Foreign key actions (`ON DELETE CASCADE`, `SET NULL`, `SET DEFAULT`, `ON UPDATE CASCADE`) | The child table's assertions are checked, whatever columns the `UPDATE` set. |
| `COPY FROM` | Checked as one statement: a violation undoes the whole `COPY`. `ON_ERROR ignore` and `REJECT_LIMIT`: the rows skipped are not put and do not count. The fast path of an empty table is not taken for an asserted table. See [COPY](sql/postgresql/copy.md) and [Bulk loading](bulk-load.md). |
| `UPDATE`, `DELETE` and `COPY` with `batch_rows` | PostgreSQL and SQL Server doors: each batch is checked before it commits. A failure in batch *k* leaves batches 1 to *k*-1 committed (each left the assertion true) and batch *k* undone; the error's context says how many rows were committed. The Oracle door's statements always run in a transaction block, where `batch_rows` is not allowed, so there is no such path there. |
| TDS bulk load (`bcp`, `SqlBulkCopy`, `INSERT BULK`) | Checked, with or without `CHECK_CONSTRAINTS` (SQL Server skips `CHECK`s without it; an assertion has no untrusted state). In a transaction the load alone is undone. See [Bulk loading](bulk-load.md). |
| Oracle array DML (`executemany`, `executeBatch`) | All or nothing for an assertion, as Oracle: it is checked once after the last run, and a violation fails the call and undoes every run, with batch errors or not. A deferred one is checked at `COMMIT`. |
| `TRUNCATE` | Checked in every door (the whole query: an `EXISTS` or `NOT EXISTS` table may break it): 23514, 547, ORA-08601, and the table keeps its rows. In the Oracle door `TRUNCATE` ends the transaction, so what it did before is committed. |
| `ALTER TABLE ... TYPE`, `ALTER COLUMN` | The values are cast and the whole query then runs. In the Oracle door `ALTER TABLE ... MODIFY` of a column an assertion reads is ORA-08702. |
| `SELECT ... INTO`, `CREATE TABLE AS` | A new table: nothing to check. |
| `INSERT ... EXEC`, `OUTPUT ... INTO`, table variables and table-valued parameters (T-SQL) | Checked (the `OUTPUT` insert names `INSERT` in 547). |
| A replica applying the log, recovery after a crash | No check: the store applies what was decided. A write that broke a disabled assertion reaches the replica. |
| A session's temporary table | Cannot be read by an assertion. |

## DDL on its tables

`DROP TABLE` of a table an assertion reads is refused until the assertion is dropped (ORA-08702, 2BP01, 3729);
`CASCADE` (`CASCADE CONSTRAINTS` in Oracle, `CASCADE` in PostgreSQL) drops the assertion with the table. `DROP` of a
column it reads is refused too (ORA-08702, 2BP01, 5074). A rename of the table or a column it reads is refused
(ORA-08694 and ORA-08702, 0A000, 15336): PostgreSQL's renames follow what depends on them, and lexdb's stored text
cannot. An unrelated column may be added, dropped or renamed.

## The catalogs

| Door | Where |
|---|---|
| Oracle | `USER_ASSERTIONS`, `ALL_ASSERTIONS`, `DBA_ASSERTIONS`, `USER_ASSERTION_DEPENDENCIES` (and `ALL_`, `DBA_`), `USER_ASSERTION_LOCK_MATRIX` (always empty), and `USER_OBJECTS` with `OBJECT_TYPE` `UNDEFINED`. See [Data dictionary](sql/oracle/data-dictionary-tables.md). |
| PostgreSQL | `information_schema.assertions`, its row in `check_constraints` and one in `constraint_column_usage` per column read. **No `pg_constraint` row**: `psql`'s `\d` and pgjdbc's metadata list constraints by `conrelid` and `contype`, and a row of neither would be a constraint of nothing. `pg_class.relhastriggers` is true for an asserted table (its checks are its triggers, in effect). |
| SQL Server | `INFORMATION_SCHEMA.ASSERTIONS`, `CHECK_CONSTRAINTS`, `CONSTRAINT_COLUMN_USAGE`. **No `sys.objects` row**: SQL Server has no object type for an assertion, and a made-up one would be listed by SSMS's Object Explorer and `sp_help` under nothing. So SSMS, `sp_help` and mssql-jdbc's `DatabaseMetaData` do not see it, and `OBJECT_ID('a')` is NULL. |

## Errors of each door

| | Oracle | PostgreSQL | SQL Server |
|---|---|---|---|
| Violated by a statement | ORA-08601 | 23514 `assertion "a" is violated` | 547 `The INSERT statement conflicted with the assertion "a".` |
| Violated at COMMIT | ORA-02091 over ORA-08601 | 23514 | 547 naming `COMMIT TRANSACTION`; `@@TRANCOUNT` 0 |
| Rows there at CREATE | ORA-08689 over ORA-08601 | 23514 `... is violated by some row` | 547 naming `CREATE ASSERTION` |
| Query refused | ORA-08689 and a reason | 0A000 | 50000 |
| Name taken | ORA-00955 | 42710 (an assertion), 42P07 (a relation) | 2714 |
| Dropping none | ORA-13650 | 42704 | 3701 |
| `DROP TABLE` that it reads | ORA-08702 | 2BP01 | 3729 |
| Deferring one not deferrable | ORA-08687 | 42809 | 50000 |

## Known gaps

See [Known issues](KNOWN-ISSUES.md#oracle-door): the Oracle door's views leave `USER_ASSERTION_LOCK_MATRIX` empty and
`INVALID` NULL, and a few checks differ from Oracle's in the finer points.
