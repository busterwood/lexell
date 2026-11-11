# lexdb speaks SQL Server: a TDS endpoint and T-SQL

Branch `lexdb-tds`, worktree `lexell-tds`, from `lexdb` at 9.87 (2026-11-11).

## 1. What and why

lexdb speaks the PostgreSQL protocol and dialect (design/lexdb.md). This
adds a second front door: a listener, by default on SQL Server's port 1433,
that speaks TDS 7.4, so a SQL Server client (sqlcmd, ODBC Driver 18,
Microsoft.Data.SqlClient, JDBC, go-mssqldb, Lexell's own `sqlserver`) can
connect to lexdb as if it were SQL Server. Then, on that connection, T-SQL:
SQL Server's syntax and, where it matters to programs, its semantics.

The same data is reachable through both doors: a table made over TDS is
there for psql, and the reverse.

AWS's Babelfish for Aurora PostgreSQL is this idea done at scale (a TDS
listener and a T-SQL dialect over PostgreSQL). It shows the idea works; it
also shows that "any SQL Server program" is years of work. The goal here is
a defined, growing subset, each piece checked against a real SQL Server.

## 2. The oracle

`tools/mssql_container.sh create` runs SQL Server 2022 Developer edition
(rootless podman, `lxl-mssql`, 127.0.0.1:14330, so 1433 stays free for
lexdb) and writes `~/.obo-mssql-dsn`, where the `sqlserver` live tests look.
`... sql` runs a batch through the container's sqlcmd. (2025-latest dies at
startup on this machine's kernel, 7.2, inside its lsass layer; 2022 runs.)
The `sqlserver` client's live suites pass against it (8 run, 1 skipped).

Tests are made the way gen_pg.py makes them against PostgreSQL: a file of
batches, run on the real server by a generator (`tests/lexdb/gen_mssql.py`)
that records the answers, and a test that runs them through lexdb's TDS
endpoint expecting those answers. Each answer is the result sets (column
names, TDS types, rows), row counts, and errors by number.

Clients to test with, beyond our own: the container's sqlcmd (mssql-tools18,
i.e. Microsoft's ODBC Driver 18), and later a .NET SqlClient and a JDBC
program in throwaway containers, since each driver sends its own startup
queries and uses RPC differently.

## 3. Architecture

```
  1433 ── lexdb_tds.lxl ── T-SQL front end ──┐
                                             ├── lexdb_exec Session ── store
  5433 ── lexdb_wire.lxl ── lexdb_sql ───────┘
```

- **`cmd/lexdb_tds.lxl`** (new): the server side of TDS. Packets and
  framing, PRELOGIN (with TLS carried inside PRELOGIN packets, then the
  socket), LOGIN7, SQLBatch, RPC, ATTENTION, and the token writers
  (LOGINACK, ENVCHANGE, INFO, ERROR, COLMETADATA, ROW/NBCROW, DONE,
  RETURNSTATUS, RETURNVALUE). It reuses `lib/tds.lxl`'s constants, packet
  header parser, UTF-16 conversion and value codecs; the server-only parts
  (writing tokens, reading LOGIN7 and RPC) are new.
- **Listening:** `lexdb DATADIR [ADDR ...] --tds ADDR` (repeatable; `ADDR`
  as for PostgreSQL's listeners, e.g. `127.0.0.1:1433`). The accept loop is
  shared; each listener knows its protocol.
- **Sessions:** a TDS connection owns an `lexdb_exec.Session`, as a
  PostgreSQL one does. Users, roles, privileges and TLS settings are the
  same ones (`--auth`, `--tls-cert`).
- **Authentication:** LOGIN7's password (scrambled, not encrypted: hence
  TLS) is checked against the role's SCRAM verifier: PBKDF2 with its salt
  and iterations, then StoredKey compared. Under `trust` any password is
  accepted, as for PostgreSQL. Integrated (SSPI/Kerberos) and Azure AD
  logins are refused.
- **Types out:** each result column's lexdb type becomes a TDS type:
  int2/4/8 to INTN, bool to BITN, float4/8 to FLTN, numeric to DECIMALN
  (precision 38, the scale of its values), text and varchar to NVARCHAR
  (n, or max), bytea to VARBINARY, uuid to GUID, date to DATEN, time to
  TIMEN(6), timestamp to DATETIME2N(6), timestamptz to DATETIMEOFFSETN(6),
  json and arrays to NVARCHAR(max) as text.
- **Errors:** a lexdb error (SQLSTATE) becomes an ERROR token with SQL
  Server's number for the same failure where there is one (42P01 to 208,
  23505 to 2627, 22012 to 8134, 42601 to 102, ...), else 50000; severity
  16; state 1. The table is checked against the oracle.
- **T-SQL front end:** see section 5 and decision L1.

## 4. Stages

| stage | contents | done when |
|---|---|---|
| S1 | the listener; PRELOGIN, TLS, LOGIN7, LOGINACK, ENVCHANGE; SQLBatch running lexdb's own dialect; COLMETADATA/ROW/DONE for every lexdb type; ERROR mapping; ATTENTION; the connect-time queries drivers send (`SET` options, `@@VERSION`, `SERVERPROPERTY`, `@@SPID`, `DB_NAME()`) | `sqlserver` and sqlcmd (ODBC 18) log in, with and without TLS, run batches, read every type, see errors by number and cancel |
| S2 | RPC: `sp_executesql` with parameters, `sp_prepare`/`sp_execute`/`sp_unprepare`, `sp_prepexec`; parameters of every type; OUTPUT parameters and RETURNVALUE; transactions by Transaction Manager request and ENVCHANGE 8/9/10; RESETCONNECTION | the `sqlserver` client's parameter, transaction and pool tests pass against lexdb; a .NET SqlClient program with parameters works |
| S3 | T-SQL surface: `[quoted]` names, `TOP n` / `TOP (n)`, `N'...'`, `+` on strings, `@@IDENTITY`/`SCOPE_IDENTITY()`, `IDENTITY(s,i)`, SQL Server's type names (nvarchar, datetime2, bit, uniqueidentifier, money, ...), common functions (GETDATE, ISNULL, LEN, CHARINDEX, CONVERT with styles, DATEADD, DATEDIFF, ...), `SELECT ... INTO`, `OFFSET ... FETCH` | gen_mssql suites for each pass |
| S4 | T-SQL batches: `DECLARE`/`SET`/`SELECT @v =`, `IF`/`ELSE`, `WHILE`, `BEGIN ... END`, `PRINT`, `RAISERROR`/`THROW`, `TRY ... CATCH`, `#temp` tables, several result sets per batch, `OUTPUT`, `GO` handled by clients | gen_mssql suites pass |
| S5 | procedures and functions (`CREATE PROCEDURE`, `EXEC`), `MERGE`, `sys.*` catalog views and SQL Server's `INFORMATION_SCHEMA`, collations (see L2) | EF Core's migrations and a Dapper program run against lexdb |

S1 is one agent run. S3 to S5 split into independent slices that can run in
parallel, each in its own worktree.

## 5. Open decisions (the user's)

- **L1. Where T-SQL is parsed.** Recommendation: a dialect flag on
  lexdb_sql's lexer and parser (`[names]`, `N''`, `@vars`, `TOP`, `+`), so
  that a T-SQL statement and its PostgreSQL twin give the same `Stmt` and
  share the planner and executor; T-SQL's own statements (batches, control
  flow, procedures) in a new `lexdb_tsql.lxl` that interprets a batch and
  hands each statement to the shared parser. The alternative, a separate
  T-SQL parser making the same `Stmt`, duplicates the expression grammar
  and drifts.
- **L2. Case-insensitive comparison.** SQL Server's default collation
  (SQL_Latin1_General_CP1_CI_AS) compares strings ignoring case and
  trailing spaces, so `WHERE name = 'bob'` finds 'Bob', and a unique key on
  it refuses both. Many programs rely on this. Recommendation: a database
  property set when it is made (`CREATE DATABASE ... COLLATE`, or the TDS
  default) that changes comparison, sorting, hashing and keys for its
  string columns; until then, comparisons are exact, and the differences
  are documented.
- **L3. One namespace or two.** SQL Server's `dbo` schema and three-part
  names (`db.schema.table`) against lexdb's `public` and search_path.
  Recommendation: over TDS, `dbo` is an alias of `public` and the default
  schema; `db.` is accepted when it names the current database.
- **L4. What runs on 1433 before T-SQL.** Recommendation: in S1 and S2,
  lexdb's own (PostgreSQL) dialect, so the protocol is tested apart from the
  dialect; from S3 the T-SQL front end, with lexdb's dialect no longer
  reachable over TDS.
- **L5. Which version lexdb says it is.** As built: LOGINACK and PRELOGIN
  say "Microsoft SQL Server" 16.0.4315 (SQL Server 2022, the oracle's
  build), because drivers decide features by it; Babelfish does the same.
  `@@VERSION` (S3) will say lexdb.

## 6. Stage S1, as built (2026-11-11)

`cmd/lexdb_tds.lxl`; `lexdb DATADIR ... --tds 127.0.0.1:1433`.

- **What clients send**, seen through `tests/lexdb/tds_proxy.py` (a capture
  proxy that decodes packets and tokens) between sqlcmd (ODBC Driver 18)
  and the oracle: PRELOGIN with TRACEID; the server answers in a REPLY
  packet; the TLS handshake (TLS 1.2) in PRELOGIN packets both ways; LOGIN7
  asking for session recovery, data classification, UTF-8 and DNS caching
  (none acknowledged by lexdb: the client then uses none); then `SET
  QUOTED_IDENTIFIER OFF` and `SET TEXTSIZE 4096` before the user's batch.
- **PRELOGIN and TLS:** without `--tls-cert` the answer is NOT_SUP, and a
  client that wants encryption gives up (as with a SQL Server that has no
  certificate). With one: ON for a client that asks, OFF (TLS for LOGIN7
  only, then plain) for one that does not, REQ under `--require-tls`. The
  server's TLS context is capped at 1.2: under 1.3 the server's handshake
  ends on the client's last flight and its session tickets would be sent
  inside a PRELOGIN packet that the client no longer expects. `tds.lxl`'s
  `Transport` carries the server side too (`startTls` and `stopTls` are now
  public).
- **LOGIN7:** the password unscrambled and checked against the role's SCRAM
  verifier (`lexdb_auth.checkPassword`: PBKDF2 with its salt and count, then
  StoredKey compared in constant time). Refusals are SQL Server's: 18456
  "Login failed for user 'x'." (a wrong password, no such role, NOLOGIN,
  integrated security, plain under `--require-tls`); 4060 for a database
  other than lexdb (or master, or none). The packet size asked for is
  granted up to 16384.
- **The login's answer** mirrors SQL Server's: ENVCHANGE database, INFO
  5701, ENVCHANGE collation (SQL_Latin1_General_CP1_CI_AS), ENVCHANGE
  language, INFO 5703, LOGINACK, ENVCHANGE packet size, DONE.
- **Batches:** a batch of T-SQL SET options alone (the options drivers send)
  is accepted; NOCOUNT is kept and drops DONE's count; `SET
  IMPLICIT_TRANSACTIONS ON` is refused. Anything else is parsed as lexdb's
  dialect and run as over PostgreSQL's protocol, the first error ending the
  batch (T-SQL's rules for which errors end a batch are S4's: the oracle
  goes on after 8134, divide by zero, and stops after 208). COPY is refused.
  RPC and Transaction Manager requests are refused with an error, and
  ATTENTION is acknowledged (DONE_ATTN) once the request before it has
  answered.
- **Results** are made whole and sent as one message; the column types as
  section 3 says, decimal's scale the largest among the column's values
  (its exponent or its display scale), text nvarchar(4000) unless a value
  is longer, then nvarchar(max) (PLP). A value SQL Server cannot hold (a
  date before year 1, NaN) is error 8115 for the statement.
- **Tests:** `tests/lexdb/run/tds_client.lxl` (lib/sqlserver against lexdb
  in the same process: TLS both ways, every type and NULL, row counts, two
  result sets, errors by number, the SET options, NOCOUNT, SCRAM logins and
  refusals, the database). By hand: sqlcmd from the mssql image (`podman
  run --network host ... sqlcmd -S 127.0.0.1,1433 -C`) logs in under
  Encrypt mandatory and optional, runs batches, reads every type, and is
  refused an untrusted certificate as by SQL Server.
- **Left for S2:** RPC (sp_executesql, prepare/execute), Transaction
  Manager requests and ENVCHANGE for transactions, RESETCONNECTION, ATTENTION
  that interrupts a running statement, streaming large results.
