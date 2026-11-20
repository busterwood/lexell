# lexdb: SQL Server and Oracle features reported missing

Status: plan, 2026-11-20, on main `b4719fa9`. Source: feedback from use
through the TDS door (SQL Server clients) and the TNS door (Oracle
clients). Each item is a feature a client used and lexdb refused, ignored
or got wrong. The work is run as lexdb-batch-gaps.md's was: Sonnet agents,
two at a time, each in its own worktree; the coordinator reviews, gates and
merges (section 3).

## 1. The reported gaps

SQL Server (TDS):

| # | Feature | Notes from the report |
|---|---|---|
| S1 | `SYSTEM_USER` | as a function, in column defaults and in queries |
| S2 | `PERCENTILE_CONT` | aggregate and window forms |
| S3 | `CREATE OR ALTER VIEW` | plain CREATE VIEW works |
| S4 | `CREATE OR ALTER PROCEDURE`, procedures and functions in general | |
| S5 | `DROP PROCEDURE` | |
| S6 | `ALTER DATABASE ... SET` | snapshot isolation options |
| S7 | `QUOTENAME()` | |
| S8 | `OBJECT_DEFINITION()` | |
| S9 | computed columns | `ADD col AS (expr) PERSISTED` |
| S10 | `sp_rename` | tables and columns |
| S11 | `ALTER COLUMN` changing a column's declared type | only SET/DROP NOT NULL and SET/DROP DEFAULT work |
| S12 | `OUTPUT ... INTO @table_variable` | the INTO form for MERGE/UPDATE/DELETE |
| S13 | `sys.sequences.last_value` | |
| S14 | `CREATE OR ALTER` generally | it trips view and procedure DDL; the error claims only CREATE TABLE/INDEX/SCHEMA/SEQUENCE are supported, though views and table types work |

Oracle (TNS):

| # | Feature | Notes from the report |
|---|---|---|
| O1 | generated columns | `GENERATED ALWAYS AS (...) VIRTUAL` |
| O2 | `SYS_EXTRACT_UTC()` | |
| O3 | object grants issued by the table's owner | silently accepted, then dropped: cross-schema access via owner grants fails |
| O4 | `dba_tab_privs`, `all_tab_privs`, `user_tab_privs` | always empty |
| O5 | `PERCENTILE_CONT ... WITHIN GROUP ... OVER (PARTITION BY ...)` | window form; the plain aggregate works |
| O6 | `NUMTODSINTERVAL()` | |
| O7 | `EXTRACT(SECOND/MINUTE/HOUR/DAY FROM <timestamp difference>)` | extracting from an interval; from a DATE works |
| O8 | function-based (expression) indexes | `CREATE INDEX ... (CASE WHEN ...)` |

## 2. Packages

Each package starts by reproducing every reported gap through its door's
own test path (the `tds_*` / `tns_*` tests and their `*_queries.txt`
files, which parse as the door does), so the fix is tested as the client
sees it. A gap that turns out not to reproduce is reported with the
query that works.

- **A. Functions and catalog values** (S1, S7, S8, S13, O2, O6, O7):
  `SYSTEM_USER` as a call and a default (T-SQL's bare keyword); QUOTENAME
  (brackets, quote character argument, 128-character limit giving NULL);
  OBJECT_DEFINITION (a view's text; a procedure's once F lands; NULL for a
  table); `sys.sequences.last_value`; SYS_EXTRACT_UTC; NUMTODSINTERVAL;
  EXTRACT of fields from an interval (Oracle: a timestamp difference is
  `INTERVAL DAY TO SECOND`). Where: lexdb_lib / lexdb_dialect, the
  catalogs (lexdb_syscat, lexdb_oracat), lexdb_time. Size S-M.
- **B. DDL forms** (S3, S6, S10, S11, S14): `CREATE OR ALTER` for views
  (and the general keyword, with an honest error for what stays
  unsupported); `ALTER DATABASE ... SET` options accepted (snapshot
  isolation ones recorded or accepted as no-ops matching lexdb's
  isolation, said in the note); `sp_rename` for tables and columns (onto
  lexdb's RENAME, adding it where missing); `ALTER COLUMN ... type` (a
  type change rewriting the rows with the cast's errors, its indexes,
  defaults and constraints kept; PostgreSQL's `ALTER COLUMN ... TYPE`
  through the same code). Where: lexdb_tsqlparse, lexdb_parse, the DDL
  statements, lexdb_catalog. Size M.
- **C. Computed and generated columns, expression indexes** (S9, O1,
  O8): a column whose value is an expression of the row's other columns,
  stored (T-SQL PERSISTED, PostgreSQL STORED) or computed on read (Oracle
  VIRTUAL, T-SQL non-persisted); refused as an INSERT/UPDATE target as the
  dialects refuse it; indexable. Oracle's function-based index on a CASE
  expression through the expression-index support the PostgreSQL door
  has. Where: lexdb_catalog, the write path, lexdb_tsqlparse/lexdb_orparse.
  Size M-L. After B (both change the catalog's column records).
- **D. PERCENTILE_CONT and PERCENTILE_DISC** (S2, O5): the ordered-set
  aggregate (`WITHIN GROUP (ORDER BY x)`) and its window form (`OVER
  (PARTITION BY ...)`, as T-SQL and Oracle write it), with each dialect's
  result type and interpolation; through lexdb_agg (the aggregate, in the
  pipeline too) and lexdb_window (the window form: a per-partition sort,
  one value per partition). Size M.
- **E. Oracle object privileges** (O3, O4): a GRANT on a table issued by
  its owner recorded and enforced (cross-schema SELECT/INSERT/UPDATE/
  DELETE), REVOKE, and the `*_tab_privs` views filled from what is
  recorded. Where: lexdb_privs (or wherever grants live), lexdb_oracat,
  the TNS session's checks. Size M.
- **F. T-SQL procedures and functions** (S4, S5, S12): `CREATE [OR ALTER]
  PROCEDURE` and `FUNCTION` (scalar and inline table-valued), `DROP
  PROCEDURE/FUNCTION [IF EXISTS]`, EXEC with parameters (OUTPUT
  parameters), their definitions stored for OBJECT_DEFINITION, and
  `OUTPUT ... INTO @table_variable` for INSERT/UPDATE/DELETE/MERGE. First
  find what lexdb_tsql already runs (batches, `INSERT ... EXEC`) and build
  on it. Size L: slice it, report per slice.

## 2a. Every dialect that has the feature

A feature is built once and exposed in each of the three dialects that
has it natively (PostgreSQL, the default; T-SQL; Oracle), with each
dialect's own syntax, names, result types and errors, and tested through
each door. A dialect that lacks the feature does not get another's
spelling of it. The counterparts to cover, per package (each agent checks
what already works before building):

| Package | PostgreSQL | SQL Server | Oracle |
|---|---|---|---|
| A | `SYSTEM_USER` (PG 16); `pg_sequences.last_value`; `pg_get_viewdef`; `quote_ident`; `EXTRACT(field FROM interval)`; `AT TIME ZONE 'UTC'`; `make_interval` | `SYSTEM_USER`, `QUOTENAME`, `OBJECT_DEFINITION`, `sys.sequences.last_value` | `SYS_EXTRACT_UTC`, `NUMTODSINTERVAL` (and `NUMTOYMINTERVAL`), `EXTRACT(... FROM interval)`, `DBMS_METADATA.GET_DDL` for views if cheap |
| B | `CREATE OR REPLACE VIEW`; `ALTER TABLE ... RENAME [COLUMN]`; `ALTER COLUMN ... TYPE ... [USING]` | `CREATE OR ALTER`; `ALTER DATABASE ... SET`; `sp_rename`; `ALTER COLUMN col type` | `CREATE OR REPLACE VIEW`; `RENAME t TO u`, `ALTER TABLE ... RENAME COLUMN`; `ALTER TABLE ... MODIFY (col type)` |
| C | `GENERATED ALWAYS AS (expr) STORED`; expression indexes | `col AS (expr) [PERSISTED]`; indexes on computed columns | `GENERATED ALWAYS AS (expr) VIRTUAL` (and the short form `col AS (expr)`); function-based indexes |
| D | `percentile_cont/percentile_disc(f) WITHIN GROUP (ORDER BY x)` (aggregate; PostgreSQL has no window form) | `PERCENTILE_CONT/DISC ... WITHIN GROUP ... OVER (...)` | aggregate and `... OVER (PARTITION BY ...)` |
| E | `GRANT/REVOKE ... ON TABLE` by the owner, `information_schema.table_privileges` / `role_table_grants`, `has_table_privilege` | `GRANT/REVOKE ... ON object`, `sys.database_permissions` | owner's object grants, `dba_/all_/user_tab_privs` |
| F | `CREATE [OR REPLACE] FUNCTION/PROCEDURE`, `DROP`, `CALL` (SQL-language bodies first; PL/pgSQL only as far as lexdb already runs it) | `CREATE [OR ALTER] PROCEDURE/FUNCTION`, `DROP`, `EXEC`, `OUTPUT ... INTO @tv` | PL/SQL procedures and functions exist (lexdb_plsql): `CREATE OR REPLACE PROCEDURE/FUNCTION`, `DROP` checked, not rebuilt |

## 3. How it is run

Two Sonnet agents at a time in their own worktrees, briefed from this note
and lexdb-batch-gaps.md section 2's rules (the same rules apply: results as
the dialect gives them, tested through the door; never move an expectation
to hide a regression; new code outside lexdb_exec where it can live
elsewhere; native builds and tests; timings under the exclusive lock).
The coordinator reviews each branch, runs the suite on the merged tree and
TPC-H once alternated with the previous main (checksums equal), merges and
pushes.

Queue (pairs that touch different files):

| Slot A | Slot B |
|---|---|
| A (functions, catalog values) | D (percentiles) |
| B (DDL forms) | E (Oracle privileges) |
| C (computed columns, expression indexes) | F (procedures, slice by slice) |

## 4. Status

| Package | Branch | State |
|---|---|---|
| A | `worktree-agent-a904a69d9594c5747` | done, awaiting review; section 5 |
| B | | not started |
| C | | not started |
| D | | not started |
| E | | not started |
| F | | not started |

## 5. Package A: what was done

Tests: `tds_funcs` (68 T-SQL batches, answers from SQL Server 2022 through
gen_mssql.py), `exec_dialect` (63 queries, answers from PostgreSQL 18
through gen_pg.py), `tns_funcs` (66 queries; no Oracle was at hand, so each
answer is as Oracle's documentation gives it, in the queries file's fourth
field; gen_oracle.py takes it when it has no connection). The three
generators' templates had fallen behind the language and were brought to
what the committed tests use.

- **S1, PostgreSQL's `SYSTEM_USER`**: a keyword, not called (`SYSTEM_USER()`
  is error 102 on SQL Server, 42601 on PostgreSQL). T-SQL: the login name as
  `SUSER_SNAME()`. PostgreSQL: NULL on a trusted connection,
  `scram-sha-256:name` after SCRAM. Both work in a column DEFAULT; before,
  CREATE TABLE and ALTER ADD COLUMN refused any session function there
  (`defaultValue` had no session).
- **S7 `QUOTENAME`** (`lexdb_tsqlfn`), also bound in batches.
- **S8 `OBJECT_DEFINITION`**: a view made over TDS keeps its text from CREATE
  to the end of the batch after its query (`lexdb_sql.DEF_MARK`);
  `lexdb_syscat.bind` writes a `D` line (object id, escaped text) for every
  object that has a definition and `sysCall` reads them; sys.sql_modules
  uses it. Package F adds its procedures' texts to the same `bind` loop.
  Not done: a view made in another dialect has none (NULL).
- **S13**: SQL Server has no `sys.sequences.last_value`; its column is
  `last_used_value` (NULL until used) and `sys.identity_columns.last_value`.
  Both are filled, `current_value` too (the last given, else the start or
  restart value). `NEXT VALUE FOR seq` did not parse over TDS: added; two
  references to one sequence in a row give different values here (SQL
  Server's give one): not done. `sys.sequences.minimum_value` of an `AS int`
  sequence is 1, SQL Server's -2147483648: not done.
  PostgreSQL's `pg_sequences.last_value` filled.
- **O2, O6, O7 (and `NUMTOYMINTERVAL`, `FROM_TZ`)** in `lexdb_orafn`. An
  Oracle `TIMESTAMP 'x +02:00'` literal was a timestamp without the zone: now
  with one. Timestamp minus timestamp is an INTERVAL DAY TO SECOND when
  either side is a TIMESTAMP (`lexdb_bind.oraSubStamp`: a DATE is a timestamp
  of scale 0 in the Oracle door; derived tables now keep that scale); DATE
  minus DATE stays a number. EXTRACT is `#ora_extract`: the fields of an
  interval by its kind (ORA-30076 for the wrong ones), days past 24 hours
  normalised, a time with a zone in UTC. Interval literals carry their sign
  to every part (`'-3 04:05:06' DAY TO SECOND`).
- **PostgreSQL**: `make_interval` with `name => value`, `quote_ident`
  quoting PostgreSQL's keyword list (it was the parser's reserved words:
  `user` was not quoted).
- Not done: `pg_get_viewdef` gives the view's text, not PostgreSQL's
  deparsed form (a deparser); `date_part(...)` returns numeric, PostgreSQL's
  double precision (the cast round-trips badly through stored expressions);
  interval times a number, `'infinity'` intervals; Oracle's `EXTRACT(HOUR
  FROM <DATE>)` (ORA-30076) and `TIMEZONE_HOUR` of a literal's own offset
  (a time with a zone keeps no offset); `DBMS_METADATA.GET_DDL`;
  `quote_ident(123)` (PostgreSQL has no such function: 42883).
