# lexdb: the idea and the design

lexdb is a SQL database server written in Lexell. It keeps its data on disk and serves it through three wire
protocols: PostgreSQL's, SQL Server's (TDS) and Oracle's (TNS). A client connects with its usual driver or tool and
gets that product's SQL dialect, data types, error numbers and catalog views. All three work on one store and one catalog.

This page explains what is different about lexdb and what it is not. [Quick start](quickstart.md) shows how to run
it.

## One engine, three doors

```
  psql, pgjdbc, libpq ... ──── PostgreSQL door (pgwire) ───┐
  sqlcmd, mssql-jdbc, SqlClient ─ SQL Server door (TDS) ───┼── one parser, planner and executor ── one store
  SQLcl, ojdbc, python-oracledb ─ Oracle door (TNS/TCPS) ──┘
```

Each protocol listener is called a **door** in these pages. A door is more than a protocol:

- **Syntax.** The PostgreSQL door takes PostgreSQL's SQL and PL/pgSQL. The SQL Server door takes T-SQL: batches,
  `@variables`, `TOP`, `[quoted names]`, procedures. The Oracle door takes Oracle SQL and PL/SQL: `NUMBER`,
  `VARCHAR2`, `DUAL`, `ROWNUM`, packages.
- **Semantics where programs depend on them.** In the Oracle door the empty string is NULL and `DATE` has a time of
  day. In the SQL Server door string comparison follows the column's collation (case-insensitive by default).
- **Errors.** Each door reports the product's error codes: SQLSTATE `23505` in the PostgreSQL door, error 2627 in
  the SQL Server door, `ORA-00001` in the Oracle door, for the same duplicate key.
- **Catalog.** Each door has the product's own views: `pg_catalog` and `information_schema`; `sys.*` and
  `INFORMATION_SCHEMA`; the Oracle data dictionary (`ALL_TABLES`, `USER_TAB_COLUMNS`, `V$DATABASE`, ...). Tools such
  as psql's `\d`, the VS Code SQL Server extension and SQLcl browse lexdb as they browse the product.

Below the doors there is one implementation. A statement from any door becomes the same internal statement, and the
same planner and executor run it. There is one store and one catalog, so a table made in one door can be reached
from the other two. What a door finds by a bare table name differs:

| Door | A bare name is looked for in | Tables it makes go to |
|---|---|---|
| PostgreSQL | `public` (the `search_path`) | `public` |
| SQL Server | `dbo`, which is `public` | `dbo`, which is `public` |
| Oracle | the login's own schema, then `public` | the login's own schema |

An Oracle login's schema is made at its first connection and has the login's name: the login `sa` works in schema
`sa`. The tables it makes are named in upper case unless quoted, so the PostgreSQL and SQL Server doors see
`sa."CITY"` for `CREATE TABLE city` made as `sa`. Tables the PostgreSQL or SQL Server doors make are in `public`, and
an Oracle login finds them by their bare name, or as `public.city`. A table of the same name in the login's own
schema hides the one in `public`, and does not stop the login from making it. See the
[Oracle door](connect/oracle.md#schemas) for the details.

Each door follows a current product release: PostgreSQL 18 and 19, SQL Server 2022 and 2025, Oracle 23ai and 26ai.
The reference pages under [sql/](sql/) say per statement and function where lexdb differs.

## The store

lexdb keeps a database in one data file (`data.lxdb`) and a write-ahead log (`log.N` segments) in a data directory.
Memory holds a cache only. The design assumes SSD or NVMe storage.

- **Copy-on-write pages.** A page that the last checkpoint refers to is never overwritten. A checkpoint writes the
  changed pages to new places and then switches one of two meta pages. A torn write cannot damage a page in use, so
  there are no full-page images and no doublewrite buffer.
- **No undo.** A transaction keeps its writes in its own memory until it commits. Pages only ever hold committed
  data, so recovery is a replay of the log from the last checkpoint, with no undo pass.
- **Group commit.** Commits that arrive together share one log write and one flush.
- **B+trees with column leaves.** A table is a B+tree on its primary key (or a hidden key). Its leaves store rows
  column by column, so a scan reads only the columns a query uses and decodes them a batch at a time.

See [architecture](architecture.md) for the files, checkpoints and recovery from a user's point of view.

## Transactions

- **Read-write transactions are serializable.** Every transaction that writes runs at SERIALIZABLE, phantoms
  included. lexdb checks at commit whether anything a transaction read has changed; if so, the commit fails with
  a serialization error (SQLSTATE `40001`, SQL Server 1205, `ORA-08177`) and the client retries. In the
  PostgreSQL door `READ COMMITTED` can be asked for and then has no commit check; in the SQL Server and Oracle doors
  the levels are accepted and run as serializable. Row locks (`SELECT ... FOR UPDATE`) avoid the retries
  in the common read-then-update case.
- **Read-only transactions are snapshots.** A read-only transaction sees the database as it was when it began.
- **Readers never wait for writers, and writers never wait for readers.**
- **Assertions** (`CREATE ASSERTION`, the SQL standard's constraint across tables) are checked at the end of each
  statement or, if deferred, at the commit, whichever door the write comes through: see [assertions](assertions.md).

See [transactions](transactions.md).

## How it runs

- **One SQL thread per process.** Sessions are coroutines on one event loop. A session that waits for the disk or
  the network lets the others run. The commit step cannot be interrupted, which is what makes the serializable
  check simple.
- **io_uring** for files and sockets.
- **Batches, not rows.** Scans, filters, joins, grouping, sorting and most expressions work on batches of rows
  decoded column by column.
- **A cost-based planner.** `ANALYZE` (and automatic statistics, on by default) gives row counts, distinct counts,
  common values and samples. The planner chooses access paths and the join order by cost. `SET lexdb_planner =
  rules` gives the older rule-based plans.
- **Scaling reads.** Read replicas are separate processes on the same machine that follow the master's log. Each is
  a core of its own. See [replicas](replicas.md).

## Read replicas

`lexdb DATADIR --replicas N` runs a master and N read-only replicas under one supervisor. The replicas read the
master's data directory and receive its log as it is written, so a commit is visible on a replica well under a
millisecond after the master acknowledges it. Each door's replica answers as that product's read-only secondary, and
each door routes read-only clients its own way: SQL Server's `ApplicationIntent=ReadOnly`, Oracle's read-only
service, libpq's and pgjdbc's `target_session_attrs` / `targetServerType`. See [replicas](replicas.md).

## What lexdb is not

- **Not a drop-in for every program.** Each door covers a defined and growing part of its product, checked against
  the real product. [Known issues](KNOWN-ISSUES.md) and the "Differences" section of each reference page list what
  is missing or different.
- **One database per server.** `current_database()` is always `lexdb`; a database name given at connection time is
  accepted and ignored. Schemas (PostgreSQL), `dbo` and other schemas (SQL Server) and users (Oracle) divide it.
- **One machine.** Replicas run on the same machine as the master and share its data directory. There is no
  replication to another machine yet.
- **No parallel query.** One statement runs on one core. Replicas add cores for reads.
- **Not in memory.** The data lives on disk; the cache (`--cache-mb`) holds what is in use.
- **Missing subsystems.** No extensions, no full-text search, no partitioning, no triggers, no
  tablespaces. Collations exist in the SQL Server door only (lexdb's other doors compare text by bytes).
