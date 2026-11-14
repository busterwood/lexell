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
| S5 | procedures and functions (`CREATE PROCEDURE`, `EXEC`), `MERGE`, `sys.*` catalog views and SQL Server's `INFORMATION_SCHEMA`, collations (see L2) | EF Core's migrations and a Dapper program run against lexdb. The `sys.*` part is built (section 13: VS Code's SQL Server extension connects, browses and completes as against SQL Server); MERGE is built (design/lexdb.md 9.121; `tds_merge`); procedures and SQL Server's INFORMATION_SCHEMA are not |

S1 is one agent run. S3 to S5 split into independent slices that can run in
parallel, each in its own worktree.

## 5. Open decisions (the user's)

- **L1. Where T-SQL is parsed.** Recommendation: a dialect flag on
  lexdb_sql's lexer and parser (`[names]`, `N''`, `@vars`, `TOP`, `+`), so
  that a T-SQL statement and its PostgreSQL twin give the same `Stmt` and
  share the planner and executor; T-SQL's own statements (batches, control
  flow, procedures) in a new `lexdb_tsql.lxl` that interprets a batch and
  hands each statement to the shared parser. (As built: T-SQL's own
  statements are parsed in `lexdb_tsqlparse.lxl`, run in `lexdb_tsql.lxl`;
  section 8.) The alternative, a separate
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

## 7. Review before T-SQL (2026-11-11)

An independent review (Fable) of sections 3 to 6, read against the code.
The claims checked hold: unquoted names are lowercased by the lexer
(`lexdb_sql.lxl:631`); text keys are their raw bytes (`encKeyPart`,
`lexdb_exec.lxl:1972`); any error in a transaction block fails it until
ROLLBACK (`lexdb_exec.lxl:9507`); there is no CREATE DATABASE.

- **L1 holds, with more than a flag:** the lexer and parser take options
  (`LexOpts{tsql, quotedIdent}`): SET QUOTED_IDENTIFIER OFF makes `"x"` a
  string; `[x]`, `#t` and `@v` are T-SQL tokens; statements need no `;`, so
  the batch interpreter drives the parser statement by statement; `+` on
  strings is a distinct operator the typer resolves. Views, defaults and
  checks are stored as text and re-parsed with the PostgreSQL parser: one
  made over TDS must be stored in lexdb's dialect or tagged with its own.
- **L2 changes:** per column, not per database (there is no database to hang
  it on; a session cannot disagree with a unique index). A column carries a
  collation in the catalog: tables made over TDS default to
  SQL_Latin1_General_CP1_CI_AS (case-insensitive, trailing spaces ignored),
  over PostgreSQL to bytes; comparison, hashing, DISTINCT/GROUP BY keys,
  sorting and LIKE take it from the column. COLLATE is already parsed and
  dropped. And it moves before S3, not S5: every table and every recorded
  oracle answer with string =, ORDER BY or GROUP BY made before it would be
  wrong, and the key encoding is a format change.
- **L6 (new): identifier case.** SQL Server keeps a name's spelling and
  returns it in COLMETADATA (`SELECT Name FROM T` gives `Name`) while
  matching names case-insensitively. Fold for lookup, keep the spelling for
  display: a catalog change, decided before S3.
- **L3 holds:** `dbo` an alias of `public` on both protocols; T-SQL has no
  search path (the user's default schema, then dbo); three- and four-part
  names and `db..t`; sys.*, INFORMATION_SCHEMA and `tempdb..#t` are needed
  earlier than S5. "One database" is stated as a lasting decision.
- **L4 changes for S2:** sp_executesql's `@p1` does not lex in lexdb's
  dialect, and OUTPUT parameters need `SET @o = ...`. So S2 brings the lexer
  options, `@name` as a parameter, and a minimal variable frame (RPC
  parameters are the batch's pre-declared variables). lexdb's dialect stays
  reachable over TDS for debugging (`SET lexdb_dialect ...`).
- **Transactions in S2, not S4:** T-SQL rolls back only the failing
  statement (unless XACT_ABORT, or an error that dooms the transaction):
  each statement over TDS runs under an implicit savepoint (they exist:
  `SavePt`). Also `@@TRANCOUNT` and nested BEGIN TRAN, ENVCHANGE 8/9/10 for
  BEGIN TRAN in SQL text, and SET IMPLICIT_TRANSACTIONS ON (JDBC's and
  ODBC's manual commit). Errors carry a class (statement abort, batch
  abort, transaction doomed) beside SQL Server's number.
- **S1's code:** a statement sink instead of one buffer per request (DONE,
  DONEINPROC, DONEPROC, RETURNSTATUS, the reset's ENVCHANGE); a row count on
  `Res` instead of parsing command tags; column types from the plan
  (`describe`) rather than the values, which streaming, sp_prepare and
  sp_describe_first_result_set need; ATTENTION needs a reader task per
  connection and a cancel flag in the executor (PostgreSQL's CancelRequest
  is ignored today too). The SET pre-parser (`setBatch`) is replaced by the
  T-SQL front end, not extended.
- **S3's slices are not independent:** SELECT INTO #t, SCOPE_IDENTITY and
  TOP (@n) need S4's frames; there are no temporary tables at all yet; and
  parallel slices would collide in `primary()` and `typeName()`.

Revised order: S2 (RPC; lexer options and `@` parameters; transactions with
statement-level rollback; the statement sink), then L2 and L6 (the catalog's
collation and spelling, keys folded), then S3 and S4 largely in sequence,
then S5.

Decided (the user, 2026-11-11): L2 per column, case-insensitive by default
for tables made over TDS and exact over PostgreSQL, built before S3; L6
names matched case-insensitively, their spelling kept and returned (psql
sees it too); one database, for good.

## 8. Stage S2, as built (2026-11-11)

Widened by section 7: RPC, T-SQL's lexing and variables, and T-SQL's
transactions, with the S1 code restructured around them.

- **Parsing (`lexdb_sql`):** a `Dialect` (tsql, quotedIdent) for the lexer:
  `@name` and `@@name`, `[name]`, `N'...'`, and `"..."` as a string under
  QUOTED_IDENTIFIER OFF; E'' strings are lexdb's only. A quoted
  name is folded like a bare one (L6, section 9), so `[Orders]` and
  `Orders` are one table. In T-SQL mode the parser takes SQL Server's type names
  (nvarchar(n|max), bit, tinyint, datetime, datetime2(n), datetimeoffset,
  uniqueidentifier, money, varbinary(max), and timestamp as rowversion) and
  `SELECT @v = expr`. It exports a `Parser`: a cursor over T-SQL text
  (peek, next, keywords) with lexdb's statement, expression and type-name
  grammar behind it, and nothing T-SQL's own.
- **Parsing a batch (`lexdb_tsqlparse`):** a module of its own, so the
  T-SQL statements S4 adds (IF, WHILE, TRY ... CATCH, procedures) grow
  there and not in lexdb_sql. `parseBatch` parses a whole batch before any
  of it runs: DECLARE (with initialisers), SET @v = expr, SET options,
  BEGIN TRAN, COMMIT, ROLLBACK [name], SAVE TRAN, and any other statement
  through lexdb_sql's `Parser`, statement after statement with no `;`
  needed. `parseParamDecls` reads sp_executesql's @params.
- **Variables are parameters.** A batch's frame holds its variables in
  order: the @@ values (@@TRANCOUNT, @@ROWCOUNT, @@ERROR, @@SPID,
  @@VERSION, @@SERVERNAME, @@LANGUAGE), an RPC's parameters, then what
  DECLARE adds; `@name` parses to `$k`. The executor is unchanged. As SQL
  Server, @@TRANCOUNT inside an INSERT, UPDATE or DELETE is one more (the
  oracle shows 2 inside a transaction).
- **Running (`lexdb_tsql`):** nested BEGIN TRAN and @@TRANCOUNT; COMMIT
  without one is 3902, ROLLBACK 3903, SAVE TRAN 628. Each statement in a
  transaction runs under a savepoint and an error rolls back only it,
  unless XACT_ABORT ON or the error dooms the transaction (40001, 40P01,
  25P02): then the transaction is rolled back and the batch ends. The batch
  goes on after most errors and ends after those SQL Server finds compiling
  (208, 207, 102, 195, 137, 134, 2812); a syntax error anywhere runs none of
  it. IMPLICIT_TRANSACTIONS ON begins one at a statement that reads or
  writes a table. `SET LEXDB_DIALECT POSTGRES | TSQL` switches dialect.
  The batch's results are events (result set, statement end, error,
  transaction begun or ended) that lexdb_tds turns into tokens.
- **RPC and the rest (`lexdb_tds`):** as its header says; `tds.parseRpc`
  and `tds.allHeadersOf` read requests on the server side, and a received
  message now carries its first packet's status (RESETCONNECTION). Error
  severities are SQL Server's (14 for a key's violation, 15 for syntax).
- **Checked against the oracle:** the batch semantics above (nested counts,
  statement rollback, XACT_ABORT, SAVE TRAN, 3902, syntax and 208 ending the
  batch, QUOTED_IDENTIFIER OFF, IMPLICIT_TRANSACTIONS, an OUTPUT parameter)
  give the same answers from SQL Server 2022 as from lexdb, through
  lib/sqlserver. `tests/lexdb/tds_dotnet/run.sh` (Microsoft.Data.SqlClient
  6: parameters, Prepare, an OUTPUT parameter, BeginTransaction with
  rollback and commit, error number and class, a pooled connection reset)
  prints the same lines against both, but for the database's name. sqlcmd
  (ODBC Driver 18) runs T-SQL batches with variables and transactions.
- **Tests:** `tds_client.lxl` grew the S2 cases (parameters of every kind,
  OUTPUT, transaction[T] committed and rolled back, variables, SELECT
  assignment, 137, nesting, statement rollback, XACT_ABORT, savepoints,
  3902, syntax and 208 ending the batch, QUOTED_IDENTIFIER OFF, brackets
  and N strings, the dialect switch, RESETCONNECTION).
- **Left:** ATTENTION during a statement and streamed results (a reader
  task and a cancel flag in the executor; column types from the plan);
  sp_prepare's metadata; TDS errors' classes beyond the common ones; the
  rest of T-SQL (S3, S4) after L2 and L6.

## 9. L6, identifier case, as built (2026-11-12)

Names are matched without regard to case on both protocols and shown as
written, as SQL Server does (checked against the oracle: a column's label
is the query's spelling, `NAME`, `name` and `Name` side by side; `*`,
INFORMATION_SCHEMA and the catalog give the spelling the table was made
with; a second table whose name differs only in case is refused, 2714).

- **Tokens:** a name's text is folded (ASCII lower case), quoted or not, in
  both dialects; `Tok.spell` keeps its spelling where that differs: a
  quoted name's always, a bare name's in T-SQL only (PostgreSQL folds bare
  names, so over psql `CREATE TABLE Foo` makes `foo` and a label of
  `SELECT Foo` is `foo`, as there). Everything lexdb matches on (catalog
  keys, column names, aliases) stays folded; the spelling rides beside it.
- **Where the spelling is kept:** a table's and a view's (`Table.spell`,
  after the layouts in the catalog row), a column's (`ColDef.spell`: the
  catalog row stores the spelling and its decoder folds it for the name, so
  rows written before need nothing), CREATE TABLE, ADD COLUMN, RENAME TO,
  RENAME COLUMN (a change of case alone too), CREATE VIEW and CREATE TABLE
  ... AS with their column lists, SELECT ... INTO.
- **Where it is shown:** a result column's label (`OutCol.spell`, from the
  item's alias or bare column, or `*`'s column), through subqueries, views,
  CTEs and set operations; RowDescription and COLMETADATA send `label()`.
  pg_class, pg_attribute, pg_tables, information_schema (tables, columns,
  views, privileges), `\d`, index and constraint definitions and regclass
  show it; regclass input is folded, quoted parts too.
- **Differences from PostgreSQL:** `"Foo"` and `foo` are one name (lexdb's
  decision, so that a name made over TDS can be written either way from
  psql). A table made before L6 with a quoted name not in lower case cannot
  be reached (its key keeps the case; nothing migrates it); a column of one
  can, folded.
- **Not yet spelled** (shown folded): index, constraint, schema, sequence,
  role and type names; `AS x(a, b)` column lists in FROM; CTE column lists.
  Error messages give the folded name. String comparison (`WHERE
  TABLE_NAME = 'orders'`) is still exact: that is L2.
- **Tests:** `tds_client.lxl` (spelling of `*`, of a query's columns and
  aliases, through a subquery, 2714 for a name in another case).

## 10. L2, collation per column: the design (2026-11-12)

Decided (the user, 2026-11-12): in two parts, equality first and SQL
Server's order second; the column's collation holds on both protocols;
over TDS literals and variables compare case-insensitively too; a column's
collation is fixed when it is made.

What the oracle (SQL Server 2022, SQL_Latin1_General_CP1_CI_AS, nvarchar)
says the first part must do: `N'a' = N'A'`, and so for every script (`Σ`
`σ`, `Я` `я`, `Ǆ` `ǆ`); `N'e' <> N'é'` (accent-sensitive); `N'a  ' =
N'a'` (trailing spaces ignored) but `N' a' <> N'a'`; LIKE ignores case but
not trailing spaces (`N'a ' LIKE N'a'` is false); GROUP BY and DISTINCT
show the first value of each group (`bob`, `alice` for bob, Bob, BOB );
`min` and `max` likewise; a primary key holding `'x'` refuses `'X '`
(2627); two columns of different collations compared is 468 ("Cannot
resolve the collation conflict between ... in the equal to operation").
`N'straße' = N'strasse'` (an expansion) is the second part's.

- **Collations.** Two behaviours: exact (bytes, lexdb's until now, and
  PostgreSQL's "C", "POSIX", "default" and the like) and case-insensitive,
  "ci" (SQL Server's `*_CI_*`: case folded by Unicode's lower case of the
  upper case, trailing spaces dropped). A collation keeps its name, for
  INFORMATION_SCHEMA and errors; names are mapped to a behaviour by `_CI_`
  in them. Two collations conflict only when their behaviours differ.
- **Columns.** `ColDef.coll`, stored in the catalog row after the existing
  fields (a row without it: exact). Text columns made over TDS default to
  SQL_Latin1_General_CP1_CI_AS; over PostgreSQL to exact. `COLLATE` on a
  column definition is kept (it is read and dropped today). It travels
  with the column through subqueries, views, CTEs and CREATE TABLE AS, as
  the spelling does (section 9).
- **The session's default.** A TDS session's default collation is the CI
  one; a PostgreSQL session's exact. It is what a literal, a variable or a
  parameter has (SQL Server's "coercible default").
- **Expressions.** When a query is planned (`resolve`), each comparison
  (`=`, `<>`, `<`, `<=`, `>`, `>=`, and so BETWEEN; IN; simple CASE;
  NULLIF; LIKE) whose operands are text is given a collation by SQL
  Server's precedence: `COLLATE` in the expression (explicit) over a
  column's (implicit) over the session default (coercible); two implicit
  ones that conflict are 468. Under "ci" its operands are wrapped in
  `#ci(x)`, the sort key (folded, trailing spaces dropped); LIKE becomes a
  case-insensitive LIKE (spaces kept). Values themselves are never
  changed: a row keeps what was written.
- **Keys.** A primary key, unique index or index on a "ci" column holds the
  key of the value (`encKeyPart` of `#ci`); the row holds the value. So
  `Bob` and `bob` collide, `WHERE name = 'BOB'` finds `Bob` through the
  index, and a foreign key to a "ci" key looks it up so. An index is used
  for a comparison only under its column's collation. Only new "ci"
  columns are keyed so: every table made before is exact and unchanged.
- **Grouping.** GROUP BY, DISTINCT, UNION, INTERSECT, EXCEPT, PARTITION BY,
  `count(DISTINCT x)`, hash joins and `min`/`max` key "ci" columns by
  `#ci` and show the group's first value; ORDER BY sorts by the key.
- **Not in the first part:** SQL Server's order (accents between letters,
  hyphens and apostrophes nearly ignored, `ß` as `ss`): ORDER BY and `<`
  on "ci" text follow the folded bytes until then, and the differences
  are recorded against the oracle. ALTER COLUMN ... COLLATE is refused.
  String functions that compare (REPLACE, CHARINDEX) are S3's.

### L2's first part, as built (2026-11-12)

- **Three behaviours, not two:** SQL Server ignores trailing spaces under
  every collation, its case-sensitive and binary ones too (`'BOB ' = 'BOB'
  COLLATE Latin1_General_CS_AS` is true in the oracle). So
  `lexdb_sql.collKind`: COLL_CI (`*_CI_*`: `#ci`, folded, spaces
  dropped), COLL_PAD (`*_CS_*`, `*_BIN*`: `#pad`, spaces dropped),
  COLL_EXACT (anything else, and none). 468 names the right operand's
  collation first, as the oracle does.
- **Where it is decided:** `resolve` gives each comparison (`=` `<>` `<`
  `<=` `>` `>=`, and so BETWEEN and simple CASE), IN lists, LIKE and IS
  DISTINCT FROM their collation (`exprColl`, `cmpColl`) and wraps their
  operands. The session's default is `Scope.coll`, from a per-session memo
  that lexdb_tds sets (`Session.setCollation`). A column's collation is
  `ColDef.coll` (catalog: flag 8 of the column's defaults byte), carried
  through FROM's subqueries, views and CTEs and into `OutCol.coll`, and
  given to the columns CREATE TABLE ... AS and SELECT INTO make.
- **Keys:** `keyOf` and `idxVal` key a collated column by `keyVal`; the
  planner treats such a column as an index on `#ci(col)` (or `#pad`), so
  the conditions the expression-index code (9.89) matches use the index:
  `WHERE nm = 'BOB'` on a key or index is a lookup, `>` a range. Locks and
  the foreign-key lookups of referencing rows use the same keys.
- **Grouping:** `Sel.groupKinds`, `ordKinds` and `outKinds`: GROUP BY,
  ORDER BY, DISTINCT, UNION, INTERSECT, EXCEPT and recursive UNION key and
  sort by `collVal`; a group shows its first row's value. `min`, `max`
  and `count(DISTINCT)` compare keys (`AggSpec.kind`; of equal keys the
  first). The batch executor (9.47) leaves collated groups and aggregates
  to the row path; it skips the `#ci` conditions it cannot compile.
- **Checked against the oracle:** equality across scripts, accents kept,
  trailing spaces, LIKE, literals, 468, a key refusing `'X '` after `'x'`,
  GROUP BY, DISTINCT, min, max, count(DISTINCT), UNION, INTERSECT, ORDER BY
  ties: the same answers. Over psql a TDS table is case-insensitive and a
  psql one exact; `'a' = 'A'` is false there.
- **Closed since:** window PARTITION BY and a window's ORDER BY go by keys;
  a join on collated columns is a hash join on the key (`Level.hashKinds`;
  or a key lookup when the other side is the key's column); `IN
  (subquery)` keys its set under the comparison's collation (resolve
  decides it, `Frame.subKinds`, endScope gives it to the `SubPlan`; the
  hashed form too); a correlated subquery's outer column keeps its
  collation (`#coll(param, name)`, implicit); NULLIF compares keys; a key
  violation's message gives the value as written. Still exact: `= ANY
  (array)` (T-SQL has no arrays) and the string functions (S3's).

### L2's second part, SQL Server's order (2026-11-12)

`ciKey` is SQL Server's order for SQL_Latin1_General_CP1_CI_AS on nvarchar
(its Windows sort), from a table generated from the oracle:
`tools/gen_sqlserver_collation.py` writes `cmd/lexdb_sqlcoll.lxl` and the
test `tests/lexdb/run/exec_sqlcoll.lxl` (1500 random strings over Latin,
Greek, Cyrillic, punctuation, dashes, quotes, ligatures and combining marks,
in the oracle's order with its ties).

- **What the oracle showed:** four kinds of character. Letters (and space,
  punctuation, symbols, digits, which sort before the letters: space <
  NBSP < `.` < `_` < digits) with a primary weight and, within it, a
  secondary one (accents, but also `ª`, `ɐ`, circled letters: SQL Server's
  own order of the variants of a letter, read from it as each one's rank).
  Hyphen-like marks (`-`, `'`, soft hyphen, the dashes, Arabic vowel
  marks): ignored by the letters, they break ties after the accents, by how
  many letters come before them and then by their own order (`coop` <
  `-coop` < `co'op` < `co-op` < `cOOp-` < `coöp`). Combining marks: an
  accent on the letter before. And characters SQL Server's table does not
  know (most of Latin Extended-B, much else): ignored, equal to nothing.
  Expansions: `æ` = `ae`, `ß` = `ss`, `þ` = `th`, `œ`, `ĳ`, `ǆ` and the like.
  Each character is ranked as c + 'a': a lone space is a trailing one.
- **The key:** the primary weights (3 bytes each; a code point beyond the
  BMP after all of them), 0 0 0, the secondary ones (2 bytes each), then
  the hyphen-like marks (position, weight). A combining mark after a letter
  composes with it where Unicode has the letter (`e` + U+0301 is `é`);
  trailing spaces are dropped after ignored characters (`'Éå ẞ'` =
  `'Éå'`). Checked: no difference from the oracle in 1500 + 4000 + 6000
  random strings (equality and order). Left: a combining mark with no letter
  before it to compose with (at the start, after punctuation) is placed
  after its letter's variants, near but not where SQL Server puts it.
- **Format:** the key of a case-insensitive column's index changed with it.
  An index on such a column made with the first part's build (the commit
  before) holds the old keys: drop and make it again (there is no release
  with the first part).
- LIKE under the collation folds case only (`#cifold`); SQL Server's
  character matching under its weights (`'æ' LIKE 'ae'`) is not done.

## 11. Stage S3, as built so far (2026-11-12)

Checked by `tests/lexdb/gen_mssql.py`: a file of T-SQL batches
(`mssql_tsql_queries.txt`, one a line) run on the oracle through
lib/sqlserver by the test program itself (LEXDB_MSSQL set: the expect
lines), then through lexdb's TDS endpoint in the same process with the
same client (`run/tds_tsql.lxl`). A result: each statement's column names
and rows, or row count, or the batch's error number. 57 batches, the
oracle's answers all.

- **IDENTITY(seed, increment)** columns (an ALWAYS identity: a value given
  is 544), `SCOPE_IDENTITY()` and `@@IDENTITY` (the session's last identity
  value, NULL before one), `SET IDENTITY_INSERT t ON` (a session memo the
  INSERT reads: lexdb_sql.OVR_TSQL; a value past the identity moves it, as
  SQL Server).
- **TOP** n, (expr), PERCENT, WITH TIES (`Stmt.topMode`; PERCENT and TIES
  applied to the sorted rows); UPDATE TOP (n), DELETE TOP (n), DELETE
  without FROM; `OFFSET n ROWS FETCH {FIRST | NEXT} m {ROW | ROWS} ONLY`
  (SQL's, so PostgreSQL's too).
- **Expressions:** `+` joins strings (`t+`: NULL with a NULL, a string with a
  number read as the number); `alias = expr`, `AS 'alias'`; a column neither
  a table's nor named has no name (`lexdb_sql.ANON`); NULLs are the least
  in ORDER BY (first going up); LIKE's `[sets]` (`#tlike`); bit takes and
  compares with numbers (`TypeName.len` 1); CAST and CONVERT cut a string
  to its length and an integer's fraction (3.9 is 3), CONVERT's date
  styles (0-12, 20-24, 100-112, 120, 121, 126, 127), TRY_CAST and
  TRY_CONVERT (`#try`: NULL where the conversion fails).
- **Functions:** LEN, DATALENGTH, CHARINDEX, PATINDEX, REPLACE (case-
  insensitive under the collation), REPLICATE, REVERSE, STUFF, SPACE,
  CONCAT, CONCAT_WS, ISNULL, IIF, CHOOSE, ROUND (its argument's type and
  scale), POWER, CEILING, SQRT and the float ones, GETDATE, SYSDATETIME,
  GETUTCDATE, CURRENT_TIMESTAMP, DATEADD, DATEDIFF (boundaries crossed),
  DATEPART, DATENAME, YEAR, MONTH, DAY, EOMONTH, DATEFROMPARTS, NEWID,
  DB_NAME, SCHEMA_NAME, USER_NAME, STRING_AGG ... WITHIN GROUP. Those of
  lexdb's own are mapped onto them in the parser (`tsqlCall`); the rest are
  `cmd/lexdb_tsqlfn.lxl`.
- **Types as clients see them:** datetime2, time and datetimeoffset sent
  at their scale (7 unless the type says: datetime's 3), `OutCol.scale`;
  decimal division and AVG at SQL Server's scales (`#tdiv`: max(6, s1 + p2
  + 1), an integer literal's precision its digits; `#tavg`: of integers an
  integer, of decimal(p, s) scale max(s, 6)). A value that does not fit its
  column's TDS type is sent as its own type where the column's values
  share one (ISNULL(NULL, 5) an int), else as text: before, an int could
  be written into an nvarchar column, breaking the stream.
- **What applications send** (`mssql_app_queries.txt`, `run/tds_app.lxl`,
  35 batches, all the oracle's answers): EF Core's tables (`IDENTITY`,
  `CONSTRAINT [PK_x] PRIMARY KEY`, `nvarchar(max)`, cascading foreign
  keys), `OUTPUT INSERTED.c` on INSERT, UPDATE and DELETE (RETURNING; an
  UPDATE's `DELETED.c` the row before: `#old`, filled per row), `OUTPUT 1`,
  CROSS APPLY and OUTER APPLY (LATERAL joins), paging by variables, EXISTS
  as bit, ROW_NUMBER, LIKE ... ESCAPE, `UPDATE p SET p.c = ... FROM Posts
  AS p JOIN ...` and `DELETE p FROM ...` (the target found in FROM, taken
  out, its join's condition the WHERE's: `tsqlDml`), table hints (`WITH
  (NOLOCK)`, read and not used), `dbo.` and `db.dbo.` (public),
  COUNT_BIG, SCOPE_IDENTITY() in a WHERE (the frame's @@IDENTITY). A
  DECLARE of several variables counts one row. COALESCE's untyped
  arguments take its type ('1900-01-01' after a datetime2 column), over
  PostgreSQL too.
- **Not yet:** DATALENGTH of a varchar literal (lexdb has one string type:
  every string counts as nvarchar); FORMAT; CONVERT's number styles and a
  string's date styles (`CONVERT(date, '05/03/2024', 103)`); decimal
  precision past division and AVG (multiplication's and addition's scales
  are the values'); OUTPUT ... INTO. (MERGE is built: design/lexdb.md 9.121; checked against SQL Server 2022 by
  `tds_merge`, with OUTPUT, $action, TOP, 8672, 10710 to 10714 and 5324.)

## 12. Stage S4, as built (2026-11-12)

`mssql_batch_queries.txt`, `run/tds_batch.lxl`: 35 batches, the oracle's
answers all (generated by gen_mssql.py as S3's).

- **Parsing** (`lexdb_tsqlparse`): IF ... [ELSE], WHILE, BEGIN ... END,
  BEGIN TRY ... END TRY BEGIN CATCH ... END CATCH, BREAK, CONTINUE, RETURN,
  PRINT, RAISERROR (message, severity, state, arguments) [WITH ...], THROW
  [number, message, state], SET @v op= x, DECLARE @t TABLE (...). `TStmt`
  nests (`body`, `els`); a condition is a statement of lexdb's parser,
  `SELECT CASE WHEN c THEN 1 ELSE 0 END`, so EXISTS and the rest are its.
- **Running** (`lexdb_tsql`): a block's statements and how it ended (next,
  BREAK, CONTINUE, RETURN, the batch's end, an error leaving a TRY block).
  An error goes through `fail`: to the client, or in a TRY block to its
  CATCH block (the statement ends with a count of 0, as SQL Server's;
  RAISERROR and THROW with none); a CATCH block's error is ERROR_NUMBER(),
  ERROR_MESSAGE(), ERROR_SEVERITY(), ERROR_STATE() (the frame's @@error_*,
  NULL outside one), and THROW alone throws it again. XACT_ABORT's error in
  a TRY block leaves the transaction open but doomed (XACT_STATE() -1)
  until ROLLBACK. RAISERROR under severity 11 and PRINT are INFO tokens;
  RAISERROR's %d %i %u %s %x take its arguments. THROW ends the batch.
  SQL Server counts SET @v = x and DECLARE @v = x as a row each (S2 had SET
  without one).
- **SELECT @v = f(@v, ...)** (`Sel.feedback`): when an assignment reads a
  variable the SELECT assigns, its rows are evaluated in their order, each
  seeing the last's values (`SELECT @s = @s + v + ',' FROM t ORDER BY id`
  joins them, as SQL Server).
- **Temporary tables:** `#name` is a session's own: a temporary table
  (lexdb 9.96) of that name in the session's temporary schema `pg_temp_N`
  (`tempKey`; `createKey` makes a `#name` temporary), so other sessions'
  catalog reads skip it and a crash's are dropped at start; dropped when
  the connection ends or is reset. A table variable, `DECLARE @t TABLE (...)`,
  is the table `#@t`, dropped after the batch. OBJECT_ID(name) a relation's
  id or NULL (brackets, dbo. and #names read).
- **Not yet:** a SELECT whose error comes after SQL Server has sent its
  columns (`BEGIN TRY SELECT 1/0 ...`: the oracle sends the empty result
  first); GOTO, WAITFOR, cursors; @@ERROR after a caught error; procedures (S5).

## 13. SQL Server's catalog, for VS Code's SQL Server extension (2026-11-13)

VS Code's SQL Server extension (mssql) does its work in Microsoft SQL Tools
Service (STS), which reads the server through SMO's queries on `sys.*`.
Against lexdb it failed at connect: `relation "sys.all_columns" does not
exist`. What STS sends was recorded from the oracle by an Extended Events
trace (`~/Work/lexdb-bench/saved/mssql-vscode`): 183 statements, 94
distinct, over 64 `sys` views, two dozen catalog and property functions,
`sp_executesql`, dynamic SQL and extended procedures.

- **The views** (`cmd/lexdb_syscat.lxl`, data in `cmd/lexdb_sysdata.lxl`,
  generated by `tools/gen_sqlserver_syscat.py` from the oracle): 67 views
  (those in the trace and `views`, `procedures`, `sequences`, `parameters`,
  `system_objects`, `system_views`, `system_columns`,
  `sql_expression_dependencies`), each with exactly SQL Server's columns
  (name, type, length, precision, scale, nullability, collation) and
  object_id. As pg_catalog's (9.80): in T-SQL mode the parser makes `sys.x`,
  `[sys].[x]`, `master.sys.x` and `db.sys.x` the function `#sys.x` in FROM,
  whose rows lexdb_exec makes when the statement runs (`sysRows`). Never in
  a PostgreSQL session.
- **How each is filled.** From lexdb's catalog (`catSnap`), each row from a
  template row SQL Server gave for such an object (one of the generator's
  demo schema) with the columns that describe lexdb's object set: `objects`
  and `all_objects` (tables U, views V, primary keys PK, unique constraints
  UQ, foreign keys F, checks C, defaults D, sequences SO; `all_objects` and
  `system_objects` add the sys views, shipped, schema 4), `tables`, `views`,
  `all_views`, `columns`, `all_columns` (with the sys views' own columns),
  `indexes` (the primary key clustered, index_id 1; a table without one a
  heap, 0; the rest nonclustered from 2), `index_columns`, `stats` (one per
  index), `key_constraints`, `foreign_keys`, `foreign_key_columns`,
  `check_constraints`, `default_constraints` (a column's DEFAULT is the
  object `DF_table_column`), `identity_columns`, `sql_modules` (views),
  `sequences`, `schemas` (SQL Server's fixed ones, then lexdb's; public is
  dbo, schema_id 1), `databases` (below), `server_principals` (the fixed
  server roles, then lexdb's roles that log in), `database_principals` (the
  fixed ones; superusers are dbo, other roles users of their names),
  `dm_exec_sessions` (the session's own row). SQL Server's own rows as they
  are: `types` (its 34), `configurations`, `syslanguages`,
  `fulltext_languages`, `database_scoped_configurations`, `data_spaces`,
  `database_files`, `dm_os_host_info`, `database_permissions` (class 0),
  `database_recovery_status` and `database_filestream_options` (the system
  databases', and lexdb's from the template). The rest exist with no rows:
  triggers, extended properties, xml, spatial, fulltext, hash and resumable
  indexes, synonyms, assemblies, keys, certificates, credentials,
  sensitivity classifications, and so on. One msdb table SMO reads,
  `msdb.dbo.syspolicy_system_health_state`, is there too, empty.
- **Ids.** A table's or a view's object_id is its OID (`catOid`), a
  constraint's its pg_constraint OID, a default's its pg_attrdef OID, a sys
  view's SQL Server's own (negative); a schema's id is its OID (dbo 1). Type
  ids and names are SQL Server's: a column's type is the T-SQL type it was
  made with (below), else the nearest (text nvarchar(max), varchar(n)
  nvarchar(n), timestamp datetime2, numeric decimal, bytea varbinary(max)).
  A column made over PostgreSQL shows collation Latin1_General_BIN2 (lexdb's
  exact comparison). An interval, an array (and an enum) are nvarchar(max),
  as lexdb_tds sends them, as text; a timestamp, timestamptz or time without
  a precision is datetime2(7), datetimeoffset(7), time(7), as sent; serial
  and bigserial are int and bigint identity columns. Object Explorer labels
  a schema made over PostgreSQL (`tests/lexdb/vscode_pg_schema.sql`) as SQL
  Server labels a table of those types (checked against the oracle). Creation and change dates are 2000-01-01: lexdb keeps
  no times. A constraint's name is lexdb's (`customers_pkey`,
  `orders_customer_id_fkey`), not SQL Server's made-up `PK__customer__3213E83F...`.
- **Databases (the decision).** `sys.databases` lists SQL Server's four
  system databases with the oracle's rows (master 1, tempdb 2, model 3,
  msdb 4) and lexdb's own as database 5, so Object Explorer shows its
  "System Databases" folder as SQL Server's. They are listed, not opened:
  HAS_DBACCESS is 0 for them (Object Explorer greys them), `USE tempdb`,
  `model` and `msdb` are SQL Server's error 916, an unknown name 911. `USE
  master` is accepted and stays in lexdb's database, as a login naming
  master already is (S1); `USE lexdb` too (ENVCHANGE and INFO 5701, as SQL
  Server).
- **Types on the wire.** A column made with a T-SQL type name keeps SQL
  Server's type where lexdb's own does not say it: its system_type_id in
  `TypeName.prec` (unused for text, integer and binary types; for a time
  type, datetime and smalldatetime beside the scale's 1), `numeric` apart
  from decimal in `len` (`lexdb_sql.tsqlCode`); the catalog row stores them
  in the fields it has, so no format changes. They ride to the client in
  `OutCol.scale` (`lexdb_syscat.hint`: the code and the length, above a
  time type's scale), through subqueries, views' and catalog relations'
  columns (`outType`) and casts; lexdb_tds then sends tinyint, char(n),
  varchar(n|max) (in code page 1252), nchar(n), datetime, smalldatetime and
  numeric as SQL Server does, and sql_variant (SSVARIANT: int, bigint, bit,
  datetime or nvarchar inside) for SERVERPROPERTY, DATABASEPROPERTYEX,
  SESSIONPROPERTY, CONNECTIONPROPERTY and the sys columns of that type. A
  bare NULL is an int, as SQL Server's; an integer 0 or 1 in a bit column
  (`ISNULL(bit, 0)`) is a bit.
- **Functions** (constants folded by the parser, `tsqlCatCall`; the rest
  lexdb_exec's `sysCall`, over the bound catalog's new O, K and I lines):
  SERVERPROPERTY (the oracle's values, recorded by the generator, but for
  MachineName, ServerName and ComputerNamePhysicalNetBIOS: this host's),
  DATABASEPROPERTYEX (likewise, NULL for a database there is not),
  SESSIONPROPERTY (the drivers' SET options: on), CONNECTIONPROPERTY
  (net_transport TCP, ...), FULLTEXTSERVICEPROPERTY, CONTEXT_INFO (NULL),
  OBJECT_ID (now also a sys view's, a constraint's, a default's),
  OBJECT_NAME, OBJECT_SCHEMA_NAME, OBJECTPROPERTY and OBJECTPROPERTYEX
  (IsMSShipped, BaseType, IsTable, IsView, Is...Cnst, TableHasPrimaryKey,
  ...), COLUMNPROPERTY (ColumnId, AllowsNull, IsIdentity, IsComputed 0,
  IsDeterministic and IsPrecise NULL as for a column not computed, ...),
  INDEXPROPERTY, SCHEMA_NAME(id), SCHEMA_ID, DB_ID, DB_NAME(id),
  HAS_DBACCESS, TYPE_NAME, TYPE_ID, SUSER_SNAME(sid) (a login's sid is
  0x4C58 and its role's OID; 0x01, dbo's, the first superuser),
  SUSER_SID, IS_SRVROLEMEMBER, IS_MEMBER, HAS_PERMS_BY_NAME, and
  @@MICROSOFTVERSION, @@MAX_PRECISION, @@SERVICENAME, @@LANGID,
  @@DATEFIRST, @@TEXTSIZE, @@LOCK_TIMEOUT, @@MAX_CONNECTIONS.
- **T-SQL the trace needed:** `USE`; `EXEC (string)` (a batch of its own,
  without the caller's variables), `EXEC sp_executesql` in a batch (its
  @params, OUTPUT ones back), `EXEC master.dbo.xp_msver` (SQL Server's
  rows), `xp_instance_regread` (its OUTPUT NULL: lexdb has no registry),
  any other procedure 2812; `INSERT t EXEC ...`; 0x literals (up to 8
  digits an int, as arithmetic takes them; longer, bytes); a bit in
  arithmetic and `~` (`#bitint`, `#bitnot`); `''` as a number is 0 (CAST,
  ISNULL's second argument, a VALUES column); `INSERT` without `INTO`;
  `CREATE INDEX ... INCLUDE (...)` (read, not kept: lexdb's index holds its
  key); a T-SQL keyword after a table or an item is not its alias (`FROM t
  IF ...`); `db.dbo.f(...)` calls. Two lexdb bugs on the way: a DEFAULT
  using a T-SQL function (`SYSUTCDATETIME()`, stored as `#utcnow()`) could
  not be read back from the catalog (`parseExpr` takes the executor's #
  names now), and a view made over TDS was re-read as PostgreSQL (its text
  is now tagged and parsed as T-SQL, `lexdb_sql.parseView`). lib/tds read an
  ntext RPC parameter (SqlClient's for a string over 4000 characters) as a
  column's, with a table name it does not have.
- **The replay** (`tests/lexdb/gen_vscode.py`, `vscode_queries.txt`,
  `vscode_schema.sql`, `run/tds_vscode.lxl`): every distinct statement of
  the trace, an RPC as an RPC, run against the oracle (database demo) and
  through lexdb's TDS endpoint after the same schema. An answer: per result
  set its columns' names and TDS types and its rows, or a count, or the
  error; ids, sids, guids, dates and times masked, as are the database's,
  the login's and the machine's names and constraint names either server
  made up; `{pk:t}` in a statement is the server's own primary key's name.
  The oracle's answers are recorded in the test, which runs in the suite
  without the container and prints, for each statement, ok or how lexdb's
  answer differs: 78 of 94 the same. The 16 that differ: SQL Server's
  system objects lexdb does not have (the system views, functions and
  procedures IntelliSense lists: 68, 70, 71, 73; logins: 56); the system
  databases inaccessible (14, 55, the decision above); the order of two
  constraints whose names each server makes up (27, 35, 37); a varchar
  literal (lexdb has one string type: 20, 65); a sql_variant from a scalar
  subquery or a CASE (18, 21); a row count inside the server-information
  batches (12, 15).
- **@@SPID** is the session's own number (`Session.number`), which
  `sys.dm_exec_sessions` gives: the connect-time check of contained
  authentication (`... FROM sys.dm_exec_sessions WHERE session_id =
  @@SPID`) found no row once a PostgreSQL session had taken a number (they
  are shared), and Object Explorer could not open Databases.
  `run/tds_pgcatalog.lxl` (in the suite) makes a schema over a PostgreSQL
  session, then reads it over TDS: that row, and the labels Object Explorer
  makes of its columns, keys, indexes, defaults, its cascading foreign key,
  its identity columns.
- **The live check** (`tests/lexdb/vscode.py`, not in the suite): `STS=...
  python3 lexell/tests/lexdb/vscode.py` starts lexdb, makes
  `vscode_pg_schema.sql` through psql (a schema app: serial and bigserial
  keys, text, varchar(n), numeric(p,s), boolean defaults, date, timestamp,
  timestamptz, float8, real, smallint, interval, bytea, uuid with a default,
  time, text[], a cascading foreign key, an index, a view), loads
  `vscode_schema.sql` through STS and drives it as the extension does (`vscode_sts.py`, from the
  trace's driver): connect with server info, Object Explorer down to each
  table's columns (`id (PK, int, not null)`, `email (varchar(200), null)`,
  a view's columns as their tables'), keys, constraints, indexes and
  statistics, table and column completions, a query: the same as against
  SQL Server but for the constraints' names and the system objects
  completions list.
- **Not done:** Object Explorer's other folders (Security, Programmability,
  Storage, Service Broker: they list nothing, from empty views); scripting
  and the table designer (sys.sql_modules has views only; check and
  default definitions are rendered in SQL Server's style from lexdb's
  expressions, close but not always its text); SQL Server's
  INFORMATION_SCHEMA (T-SQL sessions see lexdb's, PostgreSQL's); a
  constraint named in T-SQL (`CONSTRAINT PK_x PRIMARY KEY`) still has
  lexdb's name; INCLUDE columns are not kept; procedures (the other
  session's S5 work: EXEC here knows sp_executesql and two extended
  procedures only); the SQL Server system views, functions and procedures
  beyond these.

## 14. Bulk load: INSERT BULK and BULK_LOAD (2026-11-13)

`bcp ... in` against lexdb failed: the endpoint knew neither INSERT BULK nor
packet type 7. Bulk-copy clients (bcp, .NET's SqlBulkCopy, lib/tds's
bulkWriter) now load into lexdb as into SQL Server, on lexdb's per-row
insert path (COPY's, 9.45, 9.87, 9.119).

- **What clients send**, recorded from the oracle by the Extended Events
  trace of section 13 and by `tds_proxy.py` with every message dumped.
  bcp (ODBC Driver 18): `set quoted_identifier off`; RPC
  `sp_describe_first_result_set N'select * from db.dbo.t'`; RPC
  `sp_prepare @p1 output, NULL, N'select * from db.dbo.t', 1` (options 1:
  the statement's COLMETADATA comes back before RETURNSTATUS); `insert bulk
  db.dbo.t([id] bigint,[amt] numeric(12,2),[cust] varchar(100) collate
  SQL_Latin1_General_CP1_CI_AS, ...)with(TABLOCK, ORDER(id ASC),
  ROWS_PER_BATCH=10, ..., KEEP_NULLS)`; the rows; `sp_unprepare`. bcp leaves
  an identity column out of INSERT BULK unless `-E` (KEEPIDENTITY is no
  option: naming the column is what keeps its values), sends (max) columns
  last, and with `-b n` an INSERT BULK and a message per batch.
  SqlBulkCopy (Microsoft.Data.SqlClient 6): one batch `select @@trancount;
  SET FMTONLY ON select * from [dbo].[t] SET FMTONLY OFF exec
  ..sp_tablecollations_100 N'[dbo].[t]'`, then `insert bulk [dbo].[t] ([i]
  Int, [d] Decimal(12,2), [s] NVarChar(50) COLLATE ..., ...) with
  (KEEP_NULLS, TABLOCK, CHECK_CONSTRAINTS)`, then the rows. Both send each
  value in the type the metadata gave (bcp converts its text itself), so
  that metadata must be the table's declared types.
- **The message** (packet type 7, any number of packets): COLMETADATA (the
  INSERT BULK's columns in its order; bcp says 19 for a numeric's length,
  which lib/tds's reader now takes), a ROW per row, DONE (SqlClient's with a
  4-byte count). SQL Server takes no NBCROW and no PLP of a known length in
  it (4804, 4815: clients send (max) values as PLP of unknown length);
  lexdb takes both.
- **Metadata** (`lexdb_exec.DeclCol`, `Session.tableDecl` and
  `describeDecl`): a column as SQL Server describes it, from lexdb's
  `sqlTypeOf` (section 13): type, length, precision, scale, collation,
  nullability (a primary key's columns NOT NULL), identity, default. A
  query of one table gives a column of that table, by name and type, the
  table's declaration; anything else its lexdb type's nearest. Used by:
  `SET FMTONLY ON` (now kept: a SELECT gives a COLMETADATA of these and no
  rows, nothing else runs; a batch that an error ends still leaves FMTONLY
  as its last SET FMTONLY said, as SQL Server, which applies it as it
  compiles: SqlBulkCopy's batch for a missing table depends on it);
  sp_prepare with options 1; `sp_describe_first_result_set` (RPC and EXEC:
  its 39 columns, those lexdb has nothing for NULL as SQL Server leaves them
  for a plain table column; tds_type_id and tds_length as the oracle's:
  INT4 for a NOT NULL int, INTN for a nullable one, ...); `EXEC
  sp_tablecollations_100` (a row per column, the collation's 5 bytes and
  name for text columns; none for a table that is not there). The
  COLMETADATA writer (`declMetadata`) sends SQL Server's own types: fixed
  INT4 and BIT for NOT NULL, decimal(p, s), varchar(n) and char(n) with the
  collation, time(s), datetime2(s), and so on.
- **INSERT BULK** (`lexdb_tsqlparse`: TS_INSERTBULK; `lexdb_tsql`): the table
  (208, sent twice as SQL Server sends it), the columns with their types,
  COLLATE and NULL / NOT NULL read and not used, WITH's CHECK_CONSTRAINTS,
  FIRE_TRIGGERS, KEEP_NULLS, TABLOCK, ROWS_PER_BATCH, KILOBYTES_PER_BATCH,
  ORDER (...) (another option: 102); a column named twice 264; with another
  statement in the batch 428. Answered as SQL Server: DONE, CurCmd 0xFD, no
  count. Kept on the connection (`State.bulk`) for the next request; any
  other request drops it. A column the table does not have: SQL Server's
  DONE has the error flag and no message, and so does the load's answer
  (lexdb does the same; the oracle then closes the connection at the next
  request, lexdb does not).
- **The load** (`lexdb_tds.bulkLoad`, `lexdb_tsql.bulk`, `lexdb_exec.bulkStmt`):
  one statement, a COPY of `copy.bulk` run by `Session.copyInFrom` (so in
  the session's transaction when one is open, under the statement's
  savepoint, else its own transaction; IMPLICIT_TRANSACTIONS begins one; not
  run again on a conflict, its rows being read). Its pull reads the
  message's next packet when the bytes it has hold no whole row
  (`tds.scanRow`, now public, finds a row's values), decodes each value
  straight to lexdb's (`bulkVal`: integers, bit, real and float, decimal and
  numeric from the sign and magnitude, money, char, varchar and text in
  their collation's code page (ASCII as it is), nchar, nvarchar, ntext and
  xml from UTF-16, binary, varbinary, image, PLP values joined, date, time,
  datetime2 and datetimeoffset from their units, datetime and
  smalldatetime through lib/tds's decoder, uniqueidentifier; sql_variant
  and UDTs 4816), and gives a packet's rows at a time. `bulkStmt` inserts
  each with `insertOne`, as COPY: the value made the column's type as an
  INSERT's (a bit into a number column 0 or 1), the other columns their
  defaults, the hidden key's runs (9.119), keys, checks and foreign keys.
  Without KEEP_NULLS a NULL for a column with a DEFAULT (or an identity)
  takes it. An identity column named keeps its values and goes on past the
  largest (as IDENTITY_INSERT). The message is read to its end whatever
  happens, so the connection goes on.
- **The answer**: DONE with DONE_COUNT, CurCmd 0xF0 and the row count (NOCOUNT
  does not drop it); an error: ERROR, INFO 3621 "The statement has been
  terminated.", DONE with the error flag, nothing loaded (in a transaction,
  the transaction goes on, as the oracle's for 2627); a message ended by
  the client (a last packet with IGNORE): DONE with the error flag alone,
  as SQL Server.
- **Differences from SQL Server.** CHECK constraints and foreign keys are
  always checked (SQL Server skips both without CHECK_CONSTRAINTS and marks
  them not trusted); FIRE_TRIGGERS, TABLOCK, ROWS_PER_BATCH,
  KILOBYTES_PER_BATCH and ORDER are read and ignored (lexdb has no triggers;
  its locking and commits are its own). The COLMETADATA's nullability is
  not compared with the table's (SQL Server refuses another, 4816: lexdb's
  own result metadata says nullable for every column, so lib/tds's writer,
  which copies it, would be refused). Constraint and conversion errors
  have SQL Server's numbers (2627, 515, 547, 2628 for a value too long for
  varchar(n), as SQL Server 2022's); a malformed message (SQL Server's 4804,
  4815) is an error of lexdb's own text, number 50000, and a type lexdb
  does not take 4816, as a statement's error (SQL Server's 48xx end the
  transaction too). Times keep microseconds (datetime2(7)'s last digit
  rounded), a datetimeoffset its UTC instant (not its offset), money is
  decimal(19,4): lexdb's types (section 13).
- **Clients checked.** bcp (mssql-tools18, ODBC Driver 18) `-c` loads into
  lexdb with and without `-E`, `-k`, `-h "..."` and `-b n`; the rows read
  back are the oracle's. SqlBulkCopy (Microsoft.Data.SqlClient 6, a
  throwaway program in the .NET SDK image: every common type from a
  DataTable, default options and KEEP_NULLS | TABLOCK | CHECK_CONSTRAINTS,
  a load in a transaction rolled back, a missing table) prints against
  lexdb what it prints against SQL Server. lib/tds's bulkWriter (through
  lib/sqlserver's bulkStream) loads as into SQL Server.
- **Tests:** `tests/lexdb/run/tds_bulk.lxl` (in the suite; with
  LEXDB_MSSQL it runs against a server, how its expect lines were
  checked): a message made by hand with every type above and a row of
  NULLs, KEEP_NULLS and defaults (515 for NULL into a NOT NULL column),
  identity values kept and the identity going on past them, a duplicate
  key part way (2627, 3621, none loaded, the connection usable), loads in
  a transaction (rolled back; an error in one leaves it open), 5,000 rows
  of lib/tds's writer in many packets, IGNORE, 208, 428, 264, 2628, a CHECK,
  FMTONLY and sp_tablecollations_100 as SqlBulkCopy sends them,
  sp_describe_first_result_set as bcp sends it, a column the table has
  not. The oracle's answers but three, listed in its header (times' 100 ns,
  the CHECK, the connection SQL Server closes).
- **Measured** (2026-11-13; 1M rows of `w1m_bcp.tsv`, 12 columns, into
  `t (id bigint primary key, a int, b bigint, amt numeric(12,2), f float,
  cust varchar(100), note varchar(200), d date, ts datetimeoffset, flag bit,
  u uniqueidentifier, sku varchar(20))`; medians of 3, one at a time; other
  sessions' tests ran on the machine meanwhile):

  | load | lexdb | SQL Server 2022 |
  |---|---|---|
  | `bcp -c`, bcp's own clock | 3.07 s | 3.08 s |
  | `bcp -c`, the whole bcp run | 3.64 s | 3.16 s |
  | lib/tds bulkWriter (lib/sqlserver bulkStream, parsing the file itself) | 3.43 s | 3.83 s |
  | lexdb's COPY of the same rows over psql (`\copy`, PostgreSQL's types) | 3.08 s | |

  bcp for SQL Server ran inside its container, for lexdb in a container
  of the same image on the host's network. The half second between bcp's
  clock and its end on lexdb is lexdb's checkpoint after a commit of 140 MB
  of log, which holds up bcp's sp_unprepare; COPY's psql shows the same
  0.48 s on a `select 1` after the load, and its timing above stops before
  it. A profile of the load: the TDS decoding (`bulkVal`, `bulkRows`,
  `scanRow`) about 15%, the rest insertOne, coercion, row encoding and the
  store, as COPY's. Two things the profile found: a varchar(n) value's
  characters were counted for every value (now only when its bytes are more
  than n, which helps COPY too), and the ASCII test of a varchar value is
  made on the packet's bytes before any copy.
- **Not done:** NOT NULL in result metadata generally (lexdb's COLMETADATA
  says nullable for every column but in the metadata above); `numeric`
  table columns described as `decimal` (bcp then declares decimal(p,s), which
  loads the same); SET FMTONLY ON for statements other than SELECT (they
  are skipped, not described); CHECK_CONSTRAINTS off; triggers; tedious
  and JDBC's bulk copy were not tried.

## 15. Java client pass (2026-11-14)

Microsoft's own JDBC driver (mssql-jdbc 13.6.2, `jre11`) was run against the door for the first time, and the same program
(`tests/lexdb/java/MssqlJdbc.java`, about 190 checks; README there) against a real SQL Server 2022 (RTM-CU27, in a container of
its own): connect with `encrypt=false`, `true;trustServerCertificate=true` and `true` with a trust store, every column type,
DatabaseMetaData (all of it), parameters (sp_executesql, and a statement run more than the driver's threshold, sp_prepexec,
sp_execute), generated keys, batches with and without `useBulkCopyForBatchInsert`, transactions and savepoints, MERGE with
OUTPUT, errors by number, CallableStatement. SQL Server passes every check; lexdb, after the fixes, all but what is listed below.

**Broke, and fixed.**
- A decimal parameter: mssql-jdbc sends as many bytes as the value needs (a sign byte and 1 to 16 of magnitude), not the 5, 9,
  13 or 17 of the precision (`lib/tds.lxl` `decimalCell`, `lexdb_tds.lxl`): "a decimal of 3 bytes" for any BigDecimal.
- DatabaseMetaData is `sp_tables`, `sp_columns_170` (and `_100`), `sp_pkeys`, `sp_fkeys`, `sp_statistics_100`, `sp_special_columns_100`,
  `sp_stored_procedures`, `sp_sproc_columns_100`, `sp_datatype_info_100`, `sp_table_privileges` and `sp_column_privileges`, whose rows
  the driver collects in a table variable (`DECLARE @t TABLE (...); INSERT INTO @t EXEC sp_columns_170 ...; SELECT ... FROM @t`).
  lexdb had none of the procedures and no table variable. A procedure is the SELECT of lexdb's sys views that has SQL Server's columns
  (`catalogProcSql`; `sp_datatype_info_100` is SQL Server 2022's 37 rows as they are); a table variable is a temporary table `#tv_name`
  (`DROP TABLE IF EXISTS` then `CREATE TABLE` where it is declared, every `@name` of the batch outside strings and comments renamed;
  `tableVariables`). A batch may begin with a system procedure's name (`sp_executesql N'SET FMTONLY ON SELECT ...'`, which the bulk
  copy for batches sends) without EXEC. BEGIN TRAN's name is not the keyword of the statement after it (`BEGIN TRAN IF @@TRANCOUNT =
  2 COMMIT TRAN`, which `Connection.setSavepoint` sends).
- `CONVERT(smallint, <bit column>)` and `CAST(bit AS int)` were an error (a boolean to an integer type: 1 or 0, in the shared explicit
  cast, so `true::int` works in PostgreSQL mode too).
- MERGE's DONE had command 0xC6; SQL Server's is 0x117, and the driver drops the count of a command it does not know: `executeUpdate`
  of a MERGE said 0.
- SET ROWCOUNT n was accepted and ignored (`Statement.setMaxRows`): a SELECT returns at most n rows now (not DML).
- SQL Server's words for the errors programs read: 208 `Invalid object name 'x'.`, 207 `Invalid column name 'x'.`, 156 `Incorrect syntax near
  the keyword 'x'.` (a reserved word; 102 otherwise: `Incorrect syntax near 'x'.`). The ERROR of a parse failure had lexdb's own text.
- `encrypt=strict` (TDS 8.0, TLS before PRELOGIN): lexdb waited for a packet whose length the ClientHello read as; the driver timed out
  after its login timeout. A TLS record where a packet header is now closes the connection at once (not supported).
  Tests: `tests/lexdb/run/tds_java.lxl` (the catalog procedures in the driver's own form, the table variables, the implicit EXEC, the
  savepoint batch, bit to int, SET ROWCOUNT, MERGE, the three error texts).

**Left (KNOWN and SKIP lines of the program).**
- `CREATE PROCEDURE` and `CREATE FUNCTION` (T-SQL): not supported, so a CallableStatement with an OUT parameter, a procedure's
  result sets and `getProcedures`/`getProcedureColumns` of a real procedure are not run (`sp_stored_procedures` and `sp_sproc_columns_100` answer empty).
- Server cursors: a scrollable or updatable result set is `sp_cursoropen` and `sp_cursorfetch` ("Could not find stored procedure 'procedure 2'").
- `sp_describe_undeclared_parameters`: `ParameterMetaData` (`PreparedStatement.getMetaData()` works).
- A result column of `decimal(12,3)` is described as `decimal(38,3)`, `money` as `decimal`, every column as nullable; a `datetimeoffset`
  keeps no offset (the instant, UTC); a time parameter comes back as `datetime2` where SQL Server's driver sends `datetime`;
  `@@VERSION` is lexdb's own text ("lexdb (SQL Server protocol, ...") not "Microsoft SQL Server ...".
- SET ROWCOUNT does not limit INSERT, UPDATE or DELETE.
- TDS 8.0 (`encrypt=strict`, TLS before PRELOGIN) is not supported: the connection closes at once.

## 16. As built: table-valued parameters (2026-11-14)

A client's table-valued parameter (TVP: RPC parameter type TVPTYPE 0xF3, MS-TDS 2.2.5.5.5) failed at lexdb's door: the RPC
decoder knew no 0xF3, and T-SQL had no table types. mssql-jdbc's `SQLServerDataTable` (`setStructured`), SqlClient's
`SqlDbType.Structured` and go-mssqldb's `mssql.TVP` all send one; lib/tds's `tableParam` (design/tds.md section 11, the
client side of the same bytes) is the reference the server side was built and tested against. Every answer below was
checked against SQL Server 2022 (RTM-CU27, a throwaway container of its own, removed after).

- **Table types.** `CREATE TYPE [schema.]name AS TABLE (...)` (T-SQL only) is read with CREATE TABLE's grammar (columns,
  NULL / NOT NULL, DEFAULT, IDENTITY, PRIMARY KEY, UNIQUE, CHECK) and kept as a catalog row `"\x02ttype\x00" + key` (the key
  as a table's: dbo, or no schema, is public): the key, the name as written, and the definition's text, `( ... )`, read
  again where it is used. A name an enum type or a table type has: 219 (`The type 'dbo.T' already exists, or you do not
  have permission to create it.`). `DROP TYPE` drops either kind; in T-SQL a missing one is 218 (`Could not find the type
  'dbo.Nope'. Either it does not exist or you do not have the necessary permission.`), with IF EXISTS nothing. Ids:
  user_type_id is the type's OID (`nameOid("T", key)`, the enum types' space), its table's object_id `catOid("tt", key)`.
  The catalog (lexdb_exec `sysRows`, from `CatSnap.ttypes`): a row in `sys.types` and `sys.table_types` as SQL Server's
  (system_type_id 243, max_length -1, is_nullable 0, is_user_defined 1, is_table_type 1, type_table_object_id,
  is_memory_optimized 0); its table in `sys.objects` and `sys.all_objects` (`TT_name_XXXXXXXX`, type TT, TYPE_TABLE,
  is_ms_shipped 1); its columns in `sys.columns` and `sys.all_columns` under that object_id (a primary key's NOT NULL);
  `TYPE_ID('dbo.T')` and `TYPE_NAME(id)` find it (the bound catalog's `Y` lines). `DECLARE @x [AS] type` makes a table
  variable of the type (lexdb_tsql `withTableTypes`: `DECLARE @x TABLE (definition)`, then section 15's table variables),
  its DEFAULTs and keys as the type's.
- **The bytes** (lib/tds `parseRpc`, `tableValue`; `RpcParam.table: Option[TableValue]`): TVP_TYPENAME (DbName, schema,
  name, B_VARCHAR each); the column count, or TVP_NULL_TOKEN (0xFFFF: the type's default, an empty table, `isDefault`;
  SqlClient's and lib/tds's for no rows); per column UserType, Flags (fDefault 0x200: the server fills it, no values are
  sent), a TYPE_INFO as a parameter's (text, ntext and image without a table name) and ColName (kept, not used); then
  TVP_ORDER_UNIQUE (0x10) and TVP_COLUMN_ORDERING (0x11), read and dropped (hints), and TVP_END_TOKEN; then TVP_ROW_TOKEN
  and a TYPE_VARBYTE per column sent, per row, to TVP_END_TOKEN. Every length is checked against what is left (the
  cursor's `need`), so a malformed TVP is E_PROTOCOL, never a crash: no columns or more than 1,024, a column of a table
  type, an unknown token, rows after TVP_NULL_TOKEN, a value longer than its column or past the request's end, more than
  `MAX_TABLE_CELLS` (8,388,608) rows plus values. lexdb answers ERROR 50000 (its own text) and the RPC's DONE, and the
  connection goes on, as SQL Server's does after its 8050 (column count), 4002 (stream cut short) and 8037 (length). A
  decimal column of precision 0 (mssql-jdbc's for a `SQLServerDataTable` without rows, which SQL Server takes) is read as
  decimal(38, its scale).
- **Binding** (lexdb_tds `execute`, lexdb_tsql `bindTable`), in SQL Server's order: a database name in the TVP's type
  name, 8047; a TVP's type that is not there, 351 (`Column, parameter, or variable @items. : Cannot find data type
  dbo.Nope.`, before @params is read); in @params (`lexdb_tsqlparse.parseParamDecls`: `ParamDecl.tableType`, `typeText`,
  `readonly`), a READONLY declaration of a type that is not there 2715 (`#n`, its place), a table type without READONLY 352,
  READONLY on a scalar 346, a TVP for another type or a scalar for a TVP 206; a TVP not given is its type's default (no
  8178). A declaration of a type of lexdb's own that is not a table type stays a scalar, as before. Each TVP becomes the
  session's temporary table `#tvp_<name>` (`tvpTable`): `DROP TABLE IF EXISTS`, then `CREATE TABLE #tvp_name <the type's
  definition>`; a column count other than the type's is 500 (`Trying to pass a table-valued parameter with 2 column(s)
  where the corresponding user-defined table type requires 5 column(s).`); a value sent for an identity column 1077; a
  text column sent for a binary one 257 (even all NULL, as SQL Server). Each value is decoded (`cellVal`, as a scalar
  parameter's) and made its column's type (`coerce`; a bit into a number column 1 or 0), a failure SQL Server's error and
  words (`convErr`): 245 into int, smallint, tinyint and bit (`Conversion failed when converting the nvarchar value 'x' to
  data type int.`), 8114 into bigint, decimal, numeric, float and real (`Error converting data type nvarchar to bigint.`),
  8115 for an overflow, 241 into a date or time, 8169 into uniqueidentifier, 206 for a type clash (`Operand type clash:
  bigint is incompatible with date`), 2628 for text too long. The rows go in through the bulk load's path (`bulkStmt`,
  section 14, KEEP_NULLS: a NULL sent stays NULL; a column not sent, fDefault, takes its DEFAULT or identity), so the
  type's own constraints hold, with SQL Server's words: 2627 (`Violation of PRIMARY KEY constraint '#tvp_items_pkey'.
  Cannot insert duplicate key in object 'dbo.@items'. The duplicate key value is (1).`), 515 (`... table '@items'; column
  does not allow nulls. INSERT fails.`). In an open transaction all of it runs under a savepoint, and an error leaves the transaction as it was.
- **The SQL.** Every `@name` of a TVP in the statement, outside strings, [quoted] names and comments, is made its table's
  name (`lexdb_tsqlparse.renameVars`), so a TVP reads as any table: FROM, JOIN, `IN (SELECT ...)`, EXISTS, `INSERT ...
  SELECT`, MERGE's USING, a subquery. Writing to one is 10700 (`The table-valued parameter "@items" is READONLY and cannot
  be modified.`) for an INSERT, UPDATE, DELETE or MERGE whose target is its table (UPDATE and DELETE through an alias of
  it in FROM too), found before anything of the batch runs (`State.writesReadOnly`), as SQL Server finds it compiling;
  TRUNCATE TABLE of one is SQL Server's 102. When the call is done its tables are dropped (`dropTables`).
- **Paths.** sp_executesql; sp_prepexec and sp_execute (the declarations kept with the handle, the TVP bound at each
  execute). Drivers send these by ProcID; SQL Server refuses a TVP to them called by name (8144, 349), lexdb takes both.
  T-SQL procedures are not built (section 15), so there is no procedure's TVP parameter.
- **Clients checked.** mssql-jdbc 13.6.2 (`tests/lexdb/java/MssqlJdbcTvp.java`, 21 checks: every column kind with NULLs,
  an empty table, a scalar beside one, JOIN, IN, INSERT ... SELECT, 3,000 rows, the same statement run until the driver
  prepares it, `setStructured` with a `ResultSet`, a transaction rolled back, 351, 8114, 515, 2627, 10700) passes against
  lexdb and SQL Server. lib/tds's live test `sqlserver_live_tvp`, pointed at lexdb, gives SQL Server's answers but for
  its procedure and its computed column (both missing in lexdb). SqlClient and go-mssqldb were not tried.
- **Tests.** `tests/lexdb/run/tds_tvp.lxl` (in the suite; with LEXDB_MSSQL against a SQL Server, which made its expect
  lines: the rows, the default, fDefault, 5,000 rows, two TVPs, by ProcID, a TVP made by hand with TVP_ORDER_UNIQUE and PLP
  values, a transaction, the catalog, DECLARE of a table type, and every error above); `tests/lexdb/run/tds_tvp_wire.lxl`
  (the decoder byte for byte: lib/tds's TVPs, the default, one made by hand with both order tokens, column names, PLP in
  chunks and of unknown length and a fDefault column; thirteen malformed ones; five sent to the door, each answered and
  the connection usable).
- **Differences from SQL Server, and not done.** A computed column in a table type (`x AS a * 2`: lexdb has no computed
  columns; the CREATE TYPE fails). `EXEC sp_executesql ..., @p = @x` inside a batch, passing a table variable, is not
  built (only the RPC paths bind TVPs). sp_describe_first_result_set and sp_prepare's metadata (options 1) for a statement
  that reads a TVP give no columns. varbinary into an integer column is 206 (SQL Server converts the bytes). The
  protocol errors are 50000, not 8050, 4002, 8037. 2627's text names lexdb's constraint of the temporary table
  (`#tvp_items_pkey`, SQL Server's `PK__#A0A7B7B__3213E83F...`), 2628's the parameter (`'@items'`, SQL Server's
  `'tempdb.dbo.#A0A7B7BC'`). A table type is not checked against the objects
  that use it: DROP SCHEMA leaves its types, and a FOREIGN KEY in one is taken (SQL Server refuses both). Under
  IMPLICIT_TRANSACTIONS the drop of a TVP's table is rolled back with the transaction, so the table stays until the next
  call that names the parameter (which drops it first) or the session's end. TVP_ORDER_UNIQUE is not checked: uniqueness
  is the type's own constraints'.
