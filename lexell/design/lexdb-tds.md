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

