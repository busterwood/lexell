# lexdb documentation

lexdb is a SQL database server on disk, written in Lexell, that serves the same data through three doors: the
PostgreSQL protocol with PostgreSQL's SQL, SQL Server's TDS with T-SQL, and Oracle's TNS with Oracle SQL and PL/SQL.

These pages are for people who run lexdb and write programs against it. For a high-level introduction and feature
showcase, start with [LEXDB.md](../../../LEXDB.md). The storage internals and historical benchmark log are in
[design/lexdb.md](../../design/lexdb.md) and [design/lexdb-benchmarks.md](../../design/lexdb-benchmarks.md).

## Guide

| Page | What it covers |
|---|---|
| [Overview](overview.md) | The idea: one engine, three doors; the store; transactions; replicas; what lexdb is not. |
| [Quick start](quickstart.md) | Build, start with all three doors, use one table from each. |
| [Driver & ORM compatibility](compatibility.md) | Verified compatibility matrix and reproducible test suite (`SQLAlchemy`, `Alembic`, `Django`, `EF Core`, `asyncpg`, `psycopg`, `pymssql`, `oracledb`, `ODP.NET`, `Knex`) across all three doors. |
| [Performance](performance.md) | Full TPC-H, ClickBench, analytic, OLTP (`pgbench`/`sysbench`), materialized view, skipping index, property graph, and bulk load benchmarks. |
| [Server options](server-options.md) | Every command-line option and environment variable, with defaults. |
| [Read replicas](replicas.md) | Replicas, routing per door, read-your-writes with `WAIT FOR LSN`. |
| [Architecture](architecture.md) | The files, commits, checkpoints and recovery, from a user's point of view. |
| [Transactions](transactions.md) | Isolation, how a transaction starts and ends in each door, retries. |
| [Security](security.md) | Logins, roles and privileges per door. |
| [Bulk loading](bulk-load.md) | `COPY`, SQL Server bulk copy (bcp, `SqlBulkCopy`), Oracle array DML. |
| [Restoring PostgreSQL backups](pg-restore.md) | Restore real PostgreSQL `pg_dump` / `pg_restore` backups (`-Fp`, `-Fc`, `-Ft`, `-Fd`) directly into LexDB. |
| [Materialized views](materialized-views.md) | Incremental (`FAST`) maintenance, real-time delta merging, cascading rollup DAGs, composable sketches, and automatic transparent query rewrite across all three doors. |
| [Data skipping indexes](skipping-indexes.md) | Automatic columnar zone maps and explicit `minmax`/`brin`, `set`, `bloom_filter`, `ngrambf`, and `tokenbf` skipping indexes across all three doors. |
| [Assertions](assertions.md) | SQL-standard `CREATE ASSERTION` (currently only in Oracle 26ai) enforced across all three doors, with join-key concurrency locking. |
| [Waiting for new data](sql/postgresql/select-wait.md) | `SELECT ... WAIT n SECONDS\|MILLISECONDS`: turn any indexed table into a zero-polling transactional event stream across all three doors, plus replica [`WAIT FOR LSN`](sql/postgresql/wait-for-lsn.md). |
| [Row pattern recognition](sql/postgresql/match-recognize.md) | SQL:2016 `MATCH_RECOGNIZE` over ordered rows across all three doors: [PostgreSQL](sql/postgresql/match-recognize.md), [SQL Server](sql/tsql/match-recognize.md), and [Oracle](sql/oracle/match-recognize.md). |
| [Property graphs](property-graphs.md) | SQL:2023 `CREATE PROPERTY GRAPH`, `GRAPH_TABLE`, and `ANY SHORTEST` over existing relational tables (CSR + bidirectional BFS), with 4-engine benchmarks against PostgreSQL 18, DuckPGQ, and Kùzu. |
| [Known issues](KNOWN-ISSUES.md) | Bugs and gaps found while writing these pages. |

Still to be written: monitoring (catalog views, statistics).

## Connecting

| Door | Page | Programs |
|---|---|---|
| PostgreSQL | [connect/postgresql.md](connect/postgresql.md) | [PgHello.java](connect/examples/java/PgHello.java), [PgCopy.java](connect/examples/java/PgCopy.java), [pg_hello.lxl](connect/examples/lexell/pg_hello.lxl) |
| SQL Server | [connect/sqlserver.md](connect/sqlserver.md) | [TdsHello.java](connect/examples/java/TdsHello.java), [TdsBulk.java](connect/examples/java/TdsBulk.java), [tds_hello.lxl](connect/examples/lexell/tds_hello.lxl) |
| Oracle | [connect/oracle.md](connect/oracle.md) | [OraHello.java](connect/examples/java/OraHello.java), [tns_hello.lxl](connect/examples/lexell/tns_hello.lxl) |

[connect/examples/README.md](connect/examples/README.md) says how to build and run the programs.

## SQL reference

One reference per door, each in its product's terms: syntax, types, functions, errors and catalog.

| Door | Reference | Follows |
|---|---|---|
| PostgreSQL | [sql/postgresql/](sql/postgresql/README.md) | PostgreSQL 18 and 19 |
| SQL Server | [sql/tsql/](sql/tsql/README.md) | SQL Server 2022 and 2025 |
| Oracle | [sql/oracle/](sql/oracle/README.md) | Oracle 23ai and 26ai |

Every reference page has the same parts: a short description, the syntax, the arguments, remarks, the differences
from the product, and examples with lexdb's output.

## The examples are checked

Every SQL example marked in these pages was run against a lexdb through its door, and the output shown is lexdb's.
[tools/check_examples.py](tools/check_examples.py) runs them again; [tools/README.md](tools/README.md) explains the
marking and how to run it.
