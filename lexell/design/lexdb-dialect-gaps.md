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
| D | `percentile_cont/percentile_disc(f) WITHIN GROUP (ORDER BY x)` (aggregate; PostgreSQL has no window form) | merged (6dc5e38f; TPC-H 0.991 of ca529e9d alternated, checksums equal); `PERCENTILE_CONT/DISC ... WITHIN GROUP ... OVER (...)` | aggregate and `... OVER (PARTITION BY ...)` |
| E | `GRANT/REVOKE ... ON TABLE` by the owner, `information_schema.table_privileges` / `role_table_grants`, `has_table_privilege` | `GRANT/REVOKE ... ON object`, `sys.database_permissions` | owner's object grants, `dba_/all_/user_tab_privs` |
| F | `CREATE [OR REPLACE] FUNCTION/PROCEDURE`, `DROP`, `CALL` (SQL-language bodies first; PL/pgSQL only as far as lexdb already runs it) | `CREATE [OR ALTER] PROCEDURE/FUNCTION`, `DROP`, `EXEC`, `OUTPUT ... INTO @tv` | PL/SQL procedures and functions exist (lexdb_plsql): `CREATE OR REPLACE PROCEDURE/FUNCTION`, `DROP` checked, not rebuilt |

## 3. How it is run

Two Sonnet agents at a time in their own worktrees, briefed from this note
and lexdb-batch-gaps.md section 2's rules (the same rules apply: results as
the dialect gives them, tested through the door; never move an expectation
to hide a regression; new code outside lexdb_exec where it can live
elsewhere; native builds and tests; timings under the exclusive lock).
Each agent edits, builds and tests only under its own worktree's path
(the main checkout's compiler binary is the one file it uses from
outside); an agent's stray edit to the main checkout broke main's build
once (package E, caught and moved before any commit). The coordinator reviews each branch, runs the suite on the merged tree and
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
| A | `worktree-agent-a904a69d9594c5747` | merged (a1aa79e3; TPC-H 0.998 of 6dc5e38f alternated, checksums equal; with the session's SYSTEM_USER memo entry dropped at close); section 5 |
| B | worktree-agent-a1e05408b04aabd79 | merged (fdee644f; TPC-H 0.993 of f07b6e5d alternated, checksums equal); done 2026-11-20: `a3eacc68` (CREATE OR ALTER VIEW, ALTER VIEW, OR REPLACE in each dialect's rules, the misleading CREATE error), `16e65314` (ALTER DATABASE ... SET, new module lexdb_dbopt), `3faf9a1a` (renames: sp_rename, Oracle RENAME, PostgreSQL views following), and `13dafca3` (ALTER COLUMN type: T-SQL, PostgreSQL, Oracle MODIFY); suite 218 of 218. Tests: exec_ddl (PostgreSQL 18), tds_ddl (SQL Server 2022), tds_ddlgaps (hand: "not supported yet" messages), tns_ddl (Oracle: answers by hand from the documentation, no Oracle at hand). Left: views follow renames by a recorded overlay (Table.rn), so pg_get_viewdef and OBJECT_DEFINITION keep the text as written; a PostgreSQL view on a retyped column is found by the names in its text (it may refuse a column PostgreSQL would allow); a foreign key's column cannot be retyped (0A000, PostgreSQL allows compatible types); retyping a serial or identity column to text; PostgreSQL's re-binding of a CHECK after a type change (42883) is not done (the rows are rechecked); T-SQL nvarchar is not told from varchar (so varchar to nvarchar on an indexed column is not 5074), tinyint is smallint, ALTER COLUMN ... COLLATE, ALTER DATABASE READ_ONLY/SINGLE_USER/OFFLINE and its other forms, `SET TRANSACTION ISOLATION LEVEL SNAPSHOT` does not check ALLOW_SNAPSHOT_ISOLATION (3952), a table named as another table's index (SQL Server allows, lexdb's indexes share the schema's names), CREATE VIEW not first in a batch is not 111; Oracle: from memory ORA-14155 (RENAME without COLUMN), ORA-00905 (ALTER COLUMN), ORA-01439/01440/01441/02296, a `select *` view over a renamed column is not invalidated, CREATE OR REPLACE FORCE VIEW |
| C | `worktree-agent-aca063a259081a2aa` | merged (0c7dbe94; TPC-H 0.994 of e2c93002 alternated, checksums equal; point selects -0.2% instructions; virtual columns were computed at write and stored then, read at read time since Q2: section 8, "Q2: virtual columns computed when read"); done, 2026-11-20 (not merged; merged with main 650b5753, suite 232 of 232): `da2d720a` (the model, `lexdb_gen`, the write path, PostgreSQL door), `8fc87e14` (SQL Server computed columns, catalogs), `8645e600` (Oracle virtual columns, function-based indexes, catalogs), `5aec6a69` (DROP / SET EXPRESSION, COPY, `exec_generated`), `cb6ed31c` (parser: INSERT 218 instructions cheaper than the base, 148,350 against 148,568); section 8. Left: Oracle's ORA-54027 / 54031 / 54033, the SYS_NC numbering and DEFAULT for a virtual column are from memory (no Oracle was at hand, `tns_computed` is by hand) |
| D | worktree-agent-a28c35465652ef944 | merged (6dc5e38f; TPC-H 0.991 of ca529e9d alternated, checksums equal); done, 2026-11-20: `ee73ea26` (aggregate, PostgreSQL and Oracle), `2337277c` (window form, SQL Server and Oracle); suite 211 of 211. Left: PostgreSQL's array fraction `percentile_cont(array[...])`; PostgreSQL's `42803` for an ungrouped column in the fraction (the value of the group's first row is used); SQL Server's 402 for text/dates is raised at the first row, not at compile (an empty set gives NULL); Oracle's messages ORA-30487, ORA-00907 (frame) and ORA-00932 are from memory, no Oracle server was available (expectations in `tns_percentile` are by hand); Oracle DATE interpolation rounds to microseconds, intervals are not testable in Oracle until its interval columns exist (package A) |
| E | `worktree-agent-a5b25663707eeb5fb` | merged (f07b6e5d; TPC-H 0.973 of a1aa79e3 alternated, checksums equal; point selects unchanged); done, awaiting review; section 6 |
| F | `worktree-agent-a5c6d6b7ae9c4bd2c` | merged F3 (bc0c6a21, re-homed onto Q3's modules; suite 243; TPC-H 1.024 / 1.016 / 1.038 of 95b9968d alternated, but server instructions per query equal within 0.02% on q3, q6, q9, q10, q21: code placement, not work; point selects -0.3%); merged F2 (fa2eaaa0; TPC-H 1.003 of 0c7dbe94 alternated, checksums equal; point selects equal: 3.3937/3.3969 bn against 3.3953/3.3969); merged F1 (e2c93002; TPC-H 1.003 of fdee644f alternated, checksums equal; point selects +0.6% instructions, fixed: see open points); slice F1 done 2026-11-20 (not merged): `8d2ee116` (the routine record, T-SQL procedures, PostgreSQL functions and procedures), `b082a983` (DROP SCHEMA, Describe, Oracle's kind clash, tests), `7908d6e3` (a procedure called by name over TDS), `d4f23aea` (OBJECTPROPERTY, refusals), merge of main `a0607c4a`; suite green on the merged tree; section 7. Later slices: T-SQL functions (scalar, inline table-valued) and `OUTPUT ... INTO @table_variable` (S12), PostgreSQL's set-returning SQL functions and table-reading bodies over columns, GRANT EXECUTE |
| F3 | `worktree-agent-aef37fd3888ca784e` | slice F3 done 2026-11-20 (branched from main 9cfcbe8e, suite 243 of 243), merged onto Q3's modules 2026-11-20 (main dbda1ef3; suite 243 of 243, point selects 0.3% fewer instructions than main, two alternated rounds: 3,743.6M against 3,729.9M and 3,732.0M): `15ae0aa4` (sp_stored_procedures and sp_sproc_columns), `5ad8ef30` (EXECUTE privileges in each dialect), `88acfc13` (set-returning functions, pg_get_functiondef, information_schema.routines and parameters), `6b84551c` (Oracle functions of a column), `e014ae45` (point selects: the FROM name test), then this note; point selects 0.5% fewer instructions than the base (139,141 against 139,834 per statement, three interleaved runs each); `lexdb_exec` 25,163 lines against 24,744 before the merge; on Q3's tree it is 19,608 against 19,290 (+318: the grant targets, the catalog functions and their binding, the evaluator's `#plf`, the session's calls of the checks); where F3's code went: the routine checks (`lackOn`, `useLetter`, `markDenied`, `unitsDeniedIn`, `actAs`/`backTo`), `Target.owner`, `needGrantor`'s routine cases and the `X` and `tvf` letters to `lexdb_priv`; the stored-function value memo (`plfGet`, `plfPut`, `plfNote`, `plfMisses`, `plfDrop`) and the GRANT name lookup (`grantPick`) to `lexdb_routine`; the rest in `lexdb_pg`, `lexdb_catalog` and the new `lexdb_plcall`; no new import edge; `grantRoutineTargets` and `grantOtherTarget` stay in exec (they resolve names through `schemaExists`, `catKey` and `lexdb_pgcat`, which `lexdb_priv` and `lexdb_routine` may not import); EXECUTE privileges in each dialect, PostgreSQL's set-returning functions and `pg_get_functiondef`, `sp_stored_procedures` / `sp_sproc_columns`, Oracle's PL/SQL functions of a column in a query; section 7b. Tests `exec_routinepriv` (PostgreSQL 18), `exec_routinesrf` (PostgreSQL 18), `tds_perm` (SQL Server 2022), `tds_procmeta` (SQL Server 2022), `tns_routinepriv` and `tns_plcolumn` (by hand: no Oracle at hand), `exec_routinepriv_reopen`, `wire_routine` (extended). Left for F3 (7b): see there |
| F2 | `worktree-agent-a41e5e133714c96b3` | slice F2 done 2026-11-20 (not merged; merged with main 0c7dbe94, suite 236 of 236): `81640550` (functions and OUTPUT INTO), `efc9794c` (merge of main), `7f85e2a6` (last row of a SELECT @v, tests, notes), then this note; T-SQL scalar and inline table-valued functions, `OUTPUT ... INTO` (S12); section 7a. Tests `tds_func` (SQL Server 2022), `tds_output` (SQL Server 2022), `tds_funcbatch`, `tds_funcgaps`. Left for F2 (7a): multi-statement table-valued functions, a function in a column DEFAULT, CHECK, index or view, a table-reading function with a loop, cursors, EXEC of a function. Left for F3: `GRANT EXECUTE` and routine permissions (any role that reaches the schema runs one), PostgreSQL's set-returning functions and `RETURNS TABLE`, `pg_get_functiondef` and `pg_get_function_arguments`, `information_schema.routines`, `sp_stored_procedures` and `sp_sproc_columns` (JDBC's getProcedures), Oracle PL/SQL functions of a column in a query |

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

## 6. Package E: what was done

**What reproduced (O3, O4).** The grants were not dropped: lexdb stored them
(catalog rows `ACL_PRE + "r:" + table`, owner and grants, durable like any
catalog row, removed with the table). They did nothing across schemas because
every read went through `needRel`, which asks PostgreSQL's USAGE on the
table's schema first, and a user's schema (Oracle `CREATE USER`, T-SQL
`CREATE SCHEMA ... AUTHORIZATION`) gives other users none: ORA-01031 / 229
whatever was granted. `*_tab_privs` were the empty templates; TDS had
`sys.database_permissions` of class 0 only and `HAS_PERMS_BY_NAME` answered 1.

**The model (one, in `lexdb_exec`).** Owner, grants, `GRANT`/`REVOKE` and
`has_table_privilege` are as 9.83 made them for PostgreSQL. New: a session
knows its door (`Session.setDoor`, set by `lexdb_tds` and `lexdb_tns`; kept in
the store's memo). SQL Server and Oracle have no schema privilege, so for
those doors `needRel` does not ask for USAGE (only after the USAGE test has
failed: no extra work for a session that passes it, nor for a superuser, whose
check returns first). The PostgreSQL door is unchanged: USAGE still needed.
Errors per door, raised where the check fails: TDS 229 with SQL Server's text
(`The SELECT permission was denied on the object 't', database 'lexdb', schema
's1'.`), 4613 (grantor without the right), 15151 (object or user not found);
TNS ORA-00942 for a table the user cannot read, ORA-01031 for one it can read
and not write, ORA-01720 for a user that holds the privilege and cannot grant
it (no grant option), ORA-03001 for a column list (it was widened to the whole
table). `GRANT ALL` on a table is the five privileges SQL Server and Oracle
have (not TRUNCATE and TRIGGER). T-SQL parsing: `ON [OBJECT::]name`,
`REVOKE ... TO`, an honest 0A000 (number 50000) for ALTER/CONTROL/other
classes (`SCHEMA::`), `WITH GRANT OPTION`; `TRUNCATE`/`TRIGGER` are syntax
errors (102).

**Catalog views.** `lexdb_catalog.privRows` is the one list of grants the
views read. PostgreSQL: `information_schema.role_table_grants` (new), and
`table_privileges` now shows only what its roles are grantor or grantee of
(PUBLIC too, in table_privileges), as PostgreSQL's view does (checked against
18.6 with gen_pg.py). Oracle: `DBA_/ALL_/USER_TAB_PRIVS` (columns as Oracle's;
one row a privilege, GRANTOR the owner, GRANTABLE NO, TYPE TABLE/VIEW/SEQUENCE;
USER_ the grants the user holds, owns or made, ALL_ those and PUBLIC's and its
roles'). SQL Server: `sys.database_permissions` class 1 rows (`type` `SL  `,
`IN  `, `UP  `, `DL  `, `RF  `, state `G`), grantee and grantor by the
principal ids of `sys.database_principals` (which now also lists roles that
cannot log in, as `DATABASE_ROLE`); `sp_table_privileges` adds them to the
dbo rows; `HAS_PERMS_BY_NAME(name, 'OBJECT', perm)` answers from the same
privileges (NULL for a name not found).

**Tests.** `tns_privs` (55 lines), `tds_privs` (57), `exec_privsdoor` (the
three doors on one table, the disk crashed and the store opened again, REVOKE,
DROP TABLE, a table of the same name made again), `exec_privs` regenerated
against PostgreSQL 18.6 with the new `role_table_grants`/`table_privileges`
cases. Suite 217 of 217. Point select (PK, in process, `perf stat
instructions:u`, pinned, base and branch interleaved three times): 119.6k
instructions per statement as a superuser either side, 129.2k for a role with
SELECT either side (differences under 0.1%, noise).

**Left, and unsure.** `WITH GRANT OPTION` / grant options are not modelled in
any dialect (PostgreSQL and SQL Server refuse, Oracle accepts and ignores it,
GRANTABLE is always NO); column privileges (refused: 0A000, ORA-03001); DENY;
the other Oracle object privileges (ALTER, INDEX, ...) are accepted and
ignored as before; `GRANT ... ON SCHEMA::` and schema permissions of SQL
Server; Oracle's ORA-01927 for a REVOKE of nothing. No Oracle or SQL Server
was at hand: ORA-00942/01031/01720/03001 and 229/4613/15151 with their texts
are from the documentation and memory (ORA-01720 versus 01031 for a grantor
without privilege on the table is the least sure; 23ai's ORA-41900 for DML
without privilege on a readable table is still 01031 here). A view's text is
kept unqualified and resolved along the reader's path, so a view made in
another schema must name its tables with their schema to be read by others.

Open points from review (package E): grant options are not modelled (PostgreSQL and SQL Server
refuse WITH GRANT OPTION, Oracle accepts and ignores it); column privileges, DENY and schema
permissions are not done; Oracle object privileges other than SELECT/INSERT/UPDATE/DELETE
(ALTER, INDEX, ...) are still accepted and ignored; the TNS and TDS expectations (error numbers,
view columns) are from documentation, not run against real servers.

## 7. Package F, slice F1: what was done

**One record for every dialect.** A stored routine is a `lexdb_sql.Routine`
(name key as tables are keyed, kind procedure or function, dialect, parameters
with mode, type, as-written spelling and DEFAULT text, return type, language,
body, the statement's text as the dialect keeps it, owner), kept in the catalog
tree under `lexdb_catalog.routineKey(dialect, key, signature)` (signature:
PostgreSQL's identity argument types, so functions overload; none for T-SQL),
read into `CatSnap.routines`, made, replaced, dropped and found by the new
core module `lexdb_routine`. The statements are `S_CREATE_ROUTINE`,
`S_DROP_ROUTINE` and `S_CALL` (numbers 70 to 72: B took 60 and 61); `lexdb_exec`
holds their hooks and the CALL runner (`createRoutine`, `dropRoutine`,
`callRoutine`, `Session.routines`), about 250 lines at the end of the file. A
routine runs only for the dialect that made it: its body is that dialect's
text, so the PostgreSQL door does not CALL a T-SQL procedure and TDS does not
EXEC a PostgreSQL one (each says not found, 42883 / 2812); the catalog views
list each dialect's own. Oracle's PL/SQL units stay `lexdb_plsql`'s (their own
`ProcSrc` rows).

**SQL Server (TDS), answers from SQL Server 2022 (`tds_proc`, 198 batches;
`tds_procrpc`, 16 RPC calls through `callProc`).**
`CREATE [OR ALTER] PROC[EDURE]` and `ALTER PROCEDURE` are read whole by
`lexdb_tsqlparse.procBatch` before the batch's table variables are rewritten:
the header (`@p type [= default] [OUT[PUT]] [READONLY]`, optionally in
parentheses, WITH options, `AS`), then the rest of the batch is the body, read
as a batch to check it (a syntax error creates nothing: 156/102) and kept as
text. `OBJECT_DEFINITION` and `sys.sql_modules` give the text as SQL Server
keeps it: `CREATE OR ALTER` loses its two words and keeps the blanks around
them (`CREATE   PROCEDURE`), `ALTER` is kept as `CREATE` (checked on the
container). `EXEC` takes positional and named arguments (119 for a positional
one after a named), DEFAULT, OUTPUT, `EXEC @rc = p`, `WITH RECOMPILE`, and as
the first statement of a batch the name alone (`p 1, 2`; a first statement
that does not parse and is a name, as `selec 1`, is this: 2812). The body runs
as a batch (`lexdb_tsql.callProc`) with the parameters as its first variables;
`RETURN expr` gives the return code (and a count of 1, as SQL Server's does;
the value outside a procedure is 178); `@@NESTLEVEL`, 217 at depth 32 (EXEC
(string) and sp_executesql count a level too); `ERROR_PROCEDURE()`, `@@PROCID`
and `OBJECT_NAME(@@PROCID)`; SET NOCOUNT, XACT_ABORT and ROWCOUNT are the
procedure's own and go back at its end; its #temporary tables and table
variables are dropped there. Errors as SQL Server gives them: 2714 (an object
of the name is there, table or procedure), 2812, 201 (a parameter with no
default not given, checked before an unknown name), 8143, 8144, 8145, 8162,
8114 (a value that will not convert, not 245), 179 (OUTPUT of a constant), 111
(CREATE PROCEDURE not first in its batch), 2010 (ALTER of a table), 208
(ALTER of nothing), 3701 and 3705 (DROP PROCEDURE of nothing, of a table or
view). An error that ends the *scope* (208, 207: `endsBatch`) ends the
procedure and the caller goes on (flow `F_SCOPE`); THROW and XACT_ABORT end the
batch; 208 and 207 for a statement in a TRY block of the same procedure or
batch are not caught (SQL Server finds them compiling) and no `(0)` count goes
out for a caught 208, 207 or 2812; 2812 no longer ends the batch. `DROP
PROCEDURE [IF EXISTS] a, b` (also `PROC`). `sys.procedures`, `sys.objects`
(type `P`), `sys.parameters`, `sys.sql_modules`, `OBJECT_ID(name, 'P')` (the
type argument is read now: it was dropped) and `OBJECTPROPERTY(id,
'IsProcedure')`. An RPC that names a procedure (`callProc`, a driver's
CallableStatement) is the same EXEC (`lexdb_tds.userProc`): parameters bound by
name or place to the procedure's own, DEFAULT and left-out ones taking their
defaults, OUTPUT and input-output parameters returned as the client sent them,
the return code as RETURNSTATUS.

**PostgreSQL, answers from PostgreSQL 18 (`exec_routine`, 144 queries;
`wire_routine`; `exec_routine_reopen`).** `CREATE [OR REPLACE] FUNCTION |
PROCEDURE name(args) ... LANGUAGE sql` with `$$ ... $$` bodies (the lexer
reads dollar quotes now), quoted bodies, `BEGIN ATOMIC ... END`, `RETURN
expr`; modes IN, OUT, INOUT (VARIADIC parsed, not run), DEFAULT, overloads by
argument types, schemas, STRICT and the volatility words kept; typmods of
arguments and results ignored as PostgreSQL ignores them. A language other than
sql is `42704 language "plpgsql" does not exist` (lexdb has no PL/pgSQL;
pg_language lists internal, c and sql); the body's syntax is checked at
CREATE (not its names: PostgreSQL resolves them there). `CALL name(args)`
(positional and `name => value`): the arguments run as a SELECT and are
converted to the parameters' types, the OUT/INOUT values are the result row,
the body's statements run in the call's transaction or one of their own (all
or none), `$n` or the parameters' names in the body (a column of a table the
body reads wins over a parameter of its name, as in PostgreSQL's SQL
functions); a CALL with OUT is described as columns (NoData for none) for the
extended protocol. A SQL function in a query is written as its body before the
query is planned (`lexdb_routine.inlineCalls`, also for Describe): a body that
is one SELECT of an expression is substituted with the arguments cast to the
parameter types and the result cast to the return type; a body that reads
tables becomes a scalar subquery of the statement, for arguments that are
values (no column, no subquery); STRICT becomes a CASE. `schema.f(args)`
parses now. `DROP FUNCTION | PROCEDURE | ROUTINE [IF EXISTS]
name[(types)], ...` (42883; 42725 for an ambiguous name; 42809 for the wrong
kind, with a list only). `pg_proc` rows (proname, prokind, pronargs,
pronargdefaults, prorettype with void and record now in `pg_type`,
proargtypes, proallargtypes, proargmodes, proargnames, prosrc, ...). DROP
SCHEMA refuses a schema holding routines without CASCADE and drops them with
it.

**Oracle (`tns_routine`, answers by hand: no Oracle at hand).** CREATE, CREATE
OR REPLACE and DROP of procedures and functions, CALL, `user_objects` were
right through the TNS door. One fault, fixed in `lexdb_plsql.createUnit`:
`CREATE OR REPLACE FUNCTION p` over a procedure `p` replaced it; Oracle's is
ORA-00955.

**Changed expectations.** `tds_client`'s `selec 1` gave 102; SQL Server gives
2812 (the name of a procedure; checked on the container), so the test sends
`select 1 2`. `tds_ddlgaps`'s first two batches pinned CREATE [OR ALTER]
PROCEDURE as refused (package B's honest error until F); procedures are made
now. T-SQL functions keep B's messages.

**Left for later slices.** T-SQL user-defined functions (scalar and inline
table-valued: `CREATE FUNCTION` is B's 0A000 still) and `OUTPUT ... INTO
@table_variable` (S12); `GRANT EXECUTE` and permission checks for routines
(any role that can reach the schema runs one; DROP needs the owner or a
superuser); PostgreSQL: a function whose body writes (`insert ...; select
...`) or reads tables with a column as its argument, inside a query (0A000
"cannot be used in a query yet": that wants a per-row call or LATERAL),
set-returning functions and RETURNS TABLE, `pg_get_functiondef` and
`pg_get_function_arguments` (`\sf`, `\df+`), `information_schema.routines`, the
3F000 of a function of a schema that is not there (42883 now), the 22003 of an
int4 product past its width in a body (lexdb's integers are 64-bit), named
notation in a function call in a query (`f(a => 1)`; CALL has it), VARIADIC;
T-SQL: `sp_stored_procedures` and `sp_sproc_columns` (JDBC's getProcedures)
still answer empty, `WITH EXECUTE AS` and `ENCRYPTION` are accepted and
ignored, error 266 (transaction count mismatch at a procedure's end) is not
given, table-valued parameters of a procedure (`READONLY` is read and kept, not
bound), and an old difference met on the way, not fixed: a conversion error
(245) ends the batch in SQL Server, lexdb goes on.

**Hand-over.** The inliner is the seam for PostgreSQL's richer functions;
T-SQL's scalar functions are a different thing: found by
`Session.routines(RD_TSQL, key)` and run by `lexdb_tsql`, so a call inside a
query needs a per-row hook in the evaluator that PostgreSQL's substitution does
not (inline table-valued ones are a substitution as a derived table:
`lexdb_routine.mapStmt` walks every expression of a statement, `FromItem` is
where it would go). OUTPUT INTO: `lexdb_tsqlparse` has `TS_INSERTEXEC`,
`tableVariables` and the `#@name` tables, and `tsqlDml` turns OUTPUT into the
statement's RETURNING items; `OUTPUT INTO @t` is `INSERT INTO @t` of those rows
in the same statement. New work goes in `lexdb_routine` (core) and
`lexdb_tsql`/`lexdb_tsqlparse` (T-SQL), not `lexdb_exec`. Generators:
`gen_mssql.py proc` (mssql_proc_queries.txt) and `gen_pg.py routine`
(routine_queries.txt); `tds_procrpc` (run with `LEXDB_MSSQL` it prints the
oracle's answers), `tns_routine`, `wire_routine` and `exec_routine_reopen`
are written by hand.

Open point from review (package F1): every statement now checks for PostgreSQL SQL functions to inline
(`Session.inlineFunctions` reads the shared memo's name list, a lock and a string copy, even when no
function exists): +0.6% instructions per primary-key point select (20,000 statements, 3.3955 to 3.4157
billion, repeated). A cheaper gate (a flag or count that needs no copy, kept with the catalog version)
would remove it. Fixed after review: each session caches the names with lexdb_routine's generation
(`namesGen`, moved by every `setNames`); a statement compares one integer. Point selects back to
before F1 (3.3990 / 3.3982 billion against 3.3999 / 3.3983; F1 3.4125 / 3.4134). Test:
`exec_routine_sessions` (a function made, replaced and dropped in one session seen by another that
had cached none; it fails with the invalidation removed).
A second hole, found from a user question about transactions (and in F1 from the start): the shared list
was built from the building session's transaction, so a function another session made in a transaction still
open at that moment was left out after it committed (every session then got 42883 until a restart). The list
must only ever hold more names than some transaction can see, never fewer: a function made before the list
exists is now kept aside and merged when the list is built (`noteFunction`, `loadNames`). Definitions
themselves were always transactional (catalog rows; calls resolve through the caller's transaction).

## 7a. Package F, slice F2: what was done

**T-SQL functions (S4).** `CREATE [OR ALTER] FUNCTION` and `ALTER FUNCTION` are read whole, like procedures, by
`lexdb_tsqlparse.funcBatch` (the header: `lexdb_parse.funcHeader`: parameters with defaults, `RETURNS type | TABLE |
@t TABLE (...)`, `WITH` options, an optional `AS`); the routine is the F1 record (kind function; `attrs` says `scalar`,
`inline` or `multi`, then `schemabinding`, `reads` and one `calls:key` for each function its body calls). A body is read at
CREATE to check it and refused as SQL Server refuses it: 443 (PRINT, RAISERROR, THROW, TRY, BEGIN TRAN, DML on anything but a
table variable, EXECUTE string, SET ...), 444 (a SELECT that gives rows), 2772 (#temporary tables), 154 (USE), 455 (the last
statement not a RETURN), 1075 and 178 (a RETURN with or without value), 135/136, 134/137, 111 (not first in the batch), 2714,
2010 (ALTER of the other kind), 208 (ALTER of nothing); `OBJECT_DEFINITION`/`sys.sql_modules` give the text as SQL Server
does. `DROP FUNCTION [IF EXISTS] a, b` (3701, 3705 for a procedure, and DROP PROCEDURE of a function). Catalogs: `sys.objects`
`FN`/`IF`/`TF`, `sys.sql_modules`, `sys.parameters` (a scalar function's result is its parameter 0), `OBJECT_ID(name, 'FN')`,
`OBJECTPROPERTY(IsScalarFunction | IsTableFunction | IsInlineFunction)`.

*Calls.* The parser names `schema.f(args)` a call "schema.f" and marks the statement (`Stmt.udf`; DEFAULT is `#default`; the old
`dbo.f` that dropped the schema is gone: SQL Server says 4121 for `dbo.len(x)` too). Only a marked statement costs anything: its
`Session.inlineFunctions` branch is a flag test ahead of PostgreSQL's cache check, so a statement that calls none is as before.
`lexdb_routine.tsqlCalls` writes a marked statement out (4121, 313, 8144, 208 and 317 for what SQL Server gives them):

- a scalar function that only computes: `Cast(#udf("key", arguments), result type)`. The evaluator (`lexdb_exec.udfEval`) finds
  the function in the session's memo (`udfKey`, published by `tsqlFunctions` from the caller's transaction, so what an open
  transaction made or dropped is its own) and runs its program with `lexdb_udf.run`. The program is the body compiled at CREATE
  (`lexdb_tsqlparse.genFunc`: SET, JF, JMP, RET, ERR ops with each expression as `exprText`, kept in `Routine.code`), run over
  variables by the caller's `eval`: DECLARE, SET, SELECT @v = ..., IF, WHILE, BREAK, CONTINUE, RETURN, recursion to SQL Server's
  nesting limit of 32 (217; the depth rides as a last, unnumbered parameter, as a statement's evaluation may run on several
  tasks), calls of other functions, any builtin. The program is read back (parseExpr) at each call; 3,000 calls of a body with a
  loop cost 0.3 s.
- a function that reads tables (`SELECT @r = b FROM t WHERE a = @a`, `RETURN (SELECT ...)`), or calls one, has no program: it is
  written as a scalar subquery of the statement (`lexdb_tsqlfunc.query`, given to lexdb_exec once by `lexdb_tds` through
  `setUdfQuery`: core does not import a dialect). The body is run symbolically: a variable is the expression it was last given, an
  IF a CASE over the rest of the body in each branch, a SELECT @v = ... FROM a scalar subquery (of several rows SQL Server keeps the last: the
  query's order reversed and its first row taken), RETURN the result. A call's column argument comes through a derived table of one row
  (`FROM (SELECT arg AS __a0) __uN`), so no name in the body can capture it (the outer `t` of `dbo.f(t.a)` against the body's own
  `t`). A WHILE in such a body is refused (0A000).
- an inline table-valued function in FROM (`FROM dbo.f(args) [AS x]`, also `f(args)` without the schema, as SQL Server allows,
  CROSS and OUTER APPLY, JOIN, IN/EXISTS subqueries, defaults through DEFAULT): `lexdb_routine.inlineTvf` replaces the item by the
  function's query with the arguments put in (constants as they are, others through the one-row derived table placed before it as
  a lateral item).

**OUTPUT ... INTO (S12).** `OUTPUT list INTO target [(columns)]` for INSERT, UPDATE, DELETE and MERGE (`lexdb_parse.outputList`:
the target in `Stmt.outInto`, its columns in `outCols`; the list is RETURNING's, `$action`, `inserted.`, `deleted.` as before):
`lexdb_tsql.outputInto` inserts the rows the statement returned into the target (a table variable, a #temporary table or a
table) in the statement's own transaction (begun when there is none), so a failing insert undoes the statement; the statement
returns no result set, its count is the rows it changed. 208 (before the statement), 1087 (an undeclared table variable), 120,
121, 213 for the lists, and the insert's own errors (245, 2627, 2628, 515).

**Tests.** `tds_func` (184 batches, answers from SQL Server 2022: gen_mssql.py `func`), `tds_output` (42, `output`),
`tds_funcbatch` (3,000 rows, batches on and off, same answers, and the lines equal SQL Server's run of the same file),
`tds_funcgaps` (by hand: two connections, a function made, dropped and replaced in an open transaction seen or not by the other; what
is refused). `tds_ddlgaps`'s CREATE [OR ALTER] FUNCTION lines changed: the functions are made now.

**Left (F2).** Multi-statement table-valued functions (`RETURNS @t TABLE`: read, checked, kept as `TF`, called: 0A000 "not supported
yet"); a function of the user's in a column DEFAULT, CHECK, computed column, index or view (0A000: those are kept as text and read
again by the PostgreSQL parser: they need the `#udf` form in the catalog); a function that reads tables called per row from another
function's loop, a reads function with a WHILE, `GROUP BY dbo.f(col)` of one that reads tables (the subquery's column is not the
grouped one); cursors (`DECLARE @c CURSOR`), `@@NESTLEVEL` and the other system variables in a body, EXEC of a function (2812: SQL
Server runs it), SCHEMABINDING checks (4513), 195 for an unknown builtin in a body at CREATE (SQL Server finds it compiling; lexdb
at the first call), the 3705/3701 partial effect of `DROP FUNCTION a, b` (SQL Server drops a before it fails on b), `OUTPUT x INTO @t
OUTPUT y` (both clauses: 0A000), sys.columns rows for a table-valued function, a program parsed again at each call (a cache would
make a loop-heavy function a few times faster). PostgreSQL and Oracle: PostgreSQL has no OUTPUT INTO (`RETURNING` into a variable
is PL/pgSQL; its writable CTEs are refused in lexdb as before); Oracle has `RETURNING ... INTO` in PL/SQL and through OCI binds
(`tns_binds`), unchanged; an Oracle PL/SQL function of a column in a query was still refused (`lexdb_plsql.expandCalls` takes
constants only): done in F3 (7b).

## 7b. Package F, slice F3: what was done

**Privileges on routines (one model, three doors).** A routine's privileges are an ACL row of its own (`lexdb_catalog.routineObj`:
dialect, name's key, signature; `PrivRow` and `privRows` list the grants of T-SQL's routines and Oracle's units with the tables'),
written by the first GRANT or REVOKE; before that a PostgreSQL routine is EXECUTE for PUBLIC (as PostgreSQL's) and a T-SQL routine or
Oracle unit its owner's alone. The owner is the role that made it (`Routine.owner`; for a unit the schema it is in). Letter `X` is
EXECUTE; `r` is SELECT on a T-SQL table-valued function. DROP takes the row (PostgreSQL, SQL Server and, in `putSource`, Oracle's
units; DROP SCHEMA CASCADE); CREATE OR REPLACE and ALTER keep it. Checks are made where a routine is used, never on a statement that
calls none (`Session.needExecute`, `markDeniedFns`, which only run for a statement `callNames` found a call in, or the TDS EXEC):
- PostgreSQL: `GRANT/REVOKE EXECUTE | ALL ON FUNCTION | PROCEDURE | ROUTINE name[(types)] [, ...]` and `ALL FUNCTIONS | PROCEDURES |
  ROUTINES IN SCHEMA` (42883, 42725 for a name with overloads and no list, 42809 for the wrong kind, 3F000, 0LP01 for another
  privilege), 42501 for a function inlined into a query or a CALL without EXECUTE and for one of a schema without USAGE;
  `information_schema.routine_privileges` and `role_routine_grants`, `has_function_privilege`, `pg_proc.proacl`.
- SQL Server: `GRANT/REVOKE EXECUTE (EXEC, ALL) ON [OBJECT::]proc | function` and SELECT on a table-valued function; 229 for EXEC,
  a scalar function or a TVF without it, 4606 for a permission the object's kind has not, 15151 for a grantor that may not grant (and
  for a REVOKE by one it is a silent no-op). Checked against SQL Server 2022: that 15151, not 4613, is what a user that holds SELECT on
  a table without the right to pass it on is told too (tds_privs's 4613 was from the documentation, changed with this reason). The
  body of a procedure or function runs with its owner's rights (SQL Server's ownership chaining, as lexdb has no schema owners: the
  session acts as `Routine.owner` for the run, `Session.actAs`; the query of a table-valued or table-reading function is planned as
  its owner, `Stmt.runAs`, the way a view is), so a user with EXECUTE on `p` reads what `p` reads and nothing else (a nested EXEC
  needs no EXECUTE either). `sys.database_permissions` class 1, type `EX  `, `HAS_PERMS_BY_NAME(.., 'OBJECT', 'EXECUTE')`.
- Oracle: `GRANT/REVOKE EXECUTE | ALL ON [owner.]unit TO user | PUBLIC` (lexdb_tns builds the same GRANT; `grantOtherTarget` finds the
  unit among lexdb_plsql's sources); a call without it is ORA-06550 (PLS-00201) from a block and ORA-00904 `"U1"."F"` from SQL
  (`Prog.denied`: the units of other owners the user may not run, found when the units are compiled and left out of the signatures and
  of the lookup; GRANT and REVOKE move `plsql.ver` so each connection looks again). A unit runs, and is compiled, as its owner
  (definer's rights: `Session.actAsSchema` sets the role and the search path), so it reads the tables of its schema its caller cannot.
  ORA-00942 for a privilege other than EXECUTE on a unit, ORA-00990 for EXECUTE on a table, ORA-01720 and ORA-01031, USER_, ALL_ and
  DBA_TAB_PRIVS with privilege EXECUTE and type PROCEDURE or FUNCTION. Packages are not given EXECUTE (any user may call a package).

**Set-returning SQL functions (PostgreSQL).** `RETURNS SETOF type`, `RETURNS TABLE (...)` (OUT parameters with `table` in the routine's
attrs), `RETURNS SETOF record` with OUT parameters. A function of the user's in FROM (`[schema.]f(args) [AS alias [(columns)]]`, named
and default arguments; the parser's `pgFunctionFrom` marks the statement `udf`) is written as its query before the statement is planned
(`lexdb_routine.inlineSrf`): constants put into the body, a column as an argument through a derived table of one row placed before it (an
implicit LATERAL), the columns named as the function declares them. It composes with joins, WHERE, aggregates, IN / EXISTS, CTEs and
UNION. CREATE checks the number of columns the last statement gives against the declared (42P13) and a changed SETOF. `pg_get_functiondef`,
`pg_get_function_arguments`, `_identity_arguments`, `_result` (they were NULL), `regproc`, `pg_proc` modes (`t` for TABLE columns) and
`information_schema.routines` and `parameters` (all 82 and 32 columns, values as PostgreSQL 18's; the renderers are `lexdb_pg.fnDef`
and its parts, handed to a statement through the bound catalog's `f` and `g` lines).

**SQL Server's metadata.** `sp_stored_procedures` and `sp_sproc_columns` / `_100` answer from sys.objects and sys.parameters: `;1` and
`;0` names, `@RETURN_VALUE` and `@TABLE_RETURN_VALUE`, each type's ODBC code, size, scale, radix, octet length and TDS code (ODBC 2's
or, with `@ODBCVer = 3`, ODBC 3's), patterns for name, owner and column. `tds_procmeta` (34 batches, SQL Server 2022).

**Oracle: a PL/SQL function of a column in a query** (`lexdb_plcall`, a new Oracle behavior module; `expandCalls` took constants only).
After the query is parsed, each call of a stored function is `Cast(Call("#plf", [function, arguments]))`; the evaluator reads the value
for its arguments from the store's memo (`plfEval`; a combination with none is noted and gives NULL). Before the query runs, for each
call a query made of the block's FROM, its conditions that call no function and the arguments as its select list (DISTINCT) gives the
combinations, and the function is run for each (`runBlock`); a run that missed one gives it back, it is computed and the query run again
(a query with a row limit and no ORDER BY has no such first query: it runs until it has all). So a function runs once for each distinct
combination of arguments in a query, as Oracle may do for a deterministic one, not once for each row; a function that raises raises
its error. Owner.function and package.function work (the parser now reads `a.f(` in Oracle's SQL). `tns_plcolumn`: 3,000 rows, each
shape answered with `lexdb_batch` on, off and by the same query written without the function.

**Not done / left (F3).** PostgreSQL: SECURITY DEFINER (parsed, ignored: a function runs as the caller), a set-returning function in the
select list, WITH ORDINALITY and RETURNS SETOF of a table's row type, `ALTER FUNCTION ... OWNER TO`, `DROP OWNED BY`, GRANT OPTION,
the regprocedure form with argument types and `pg_get_functiondef` of a `BEGIN ATOMIC` body (PostgreSQL deparses it; lexdb shows the
text as written), the dependency PostgreSQL finds for DROP ROLE (2BP01) on a role with routine privileges. SQL Server: DENY, the
`SCHEMA::` class, the ownership chain breaking at an object another owner has (lexdb runs the body as its owner: a procedure made by
a superuser reads everything), sp_sproc_columns's SQL Server 2000 types of the non-`_100` form for date, max and xml parameters (given
as the `_100`'s), money and numeric (lexdb's types keep them as decimal), the `sp_stored_procedures` list of SQL Server's own
procedures (the user's only), `@sp_qualifier` (15250), HAS_PERMS_BY_NAME for a name that is none (NULL; SQL Server gives 0 to a user
without rights). Oracle: EXECUTE on a package, ORA-06576 for a CALL of a denied unit (06550 here), a stored function of a column in
DML (INSERT ... SELECT f(col): ORA-00904), an aggregate or another stored function as the argument (ORA-03001), a function in a
cursor (`OPEN c FOR SELECT f(col)` inside PL/SQL), `owner.f(column)` for a name that is none (904 now), a non-deterministic function
(each distinct argument once per query) and all Oracle expectations are by hand. Errors from memory: ORA-00942 / 00990 for the wrong
privilege and ORA-01031 for a user with no privilege on a unit.

## 8. Package C: what was done

**What reproduced (S9, O1, O8, and the PostgreSQL counterparts).** Every form: PostgreSQL `GENERATED ALWAYS AS (...)` was 0A000
("generated columns are not supported"), SQL Server `col AS (expr)` a syntax error (156), Oracle `GENERATED ALWAYS AS (...) VIRTUAL`
ORA-03001 and the short form ORA-00900. Oracle's function-based index worked only for a call (`CREATE INDEX ... (UPPER(s))`); a CASE or
an arithmetic expression was ORA-00900, and USER_IND_COLUMNS showed lexdb's internal text as the column name with USER_IND_EXPRESSIONS
empty. PostgreSQL's expression indexes (9.89) were there, as was `exprindex_queries.txt`; SQL Server has no function-based index.

**The model (one, in `lexdb_gen` and `lexdb_exec`).** A column's `ColDef` has `gen` (an expression of the same row's other columns) and
`genKind` (stored: PostgreSQL STORED, T-SQL PERSISTED; virtual: PostgreSQL 18's VIRTUAL and default, Oracle VIRTUAL, T-SQL's computed
column that is not persisted); the catalog row has a flag for them (16, after the collation). The value is computed as the row is written
(`genFill`, from `Defs.gens`, before the NOT NULL and CHECK tests) by INSERT, INSERT ... SELECT, ON CONFLICT DO UPDATE, COPY (its fast
path refuses such a table), MERGE, INSERT BULK, UPDATE (also joined and with batch_rows), a foreign key action's update and the rewrite
of ALTER TABLE; and kept in the row, **for the virtual kind too** (as package C was merged; Q2 below changed that: the virtual kind is computed when
it is read). The kind says what the catalogs call it and which rules apply; scans, indexes, constraints, statistics and the batch pipeline
see an ordinary column of the stored kind (the 3,000-row test in `exec_generated` reads one with `lexdb_batch` off and on). `Stmt.mdialect` is now set for CREATE TABLE, INSERT, UPDATE
and CREATE INDEX (it was for ALTER, MERGE and views): the write errors and the rules below are each dialect's.

**Per dialect.**
- PostgreSQL: `GENERATED ALWAYS AS (expr) [STORED | VIRTUAL]` (VIRTUAL when neither: 18's), 428C9 for a value given (DEFAULT is taken),
  42P17 for another generated column or an expression that is not immutable, 42803, 0A000 for a subquery, 42601 with a DEFAULT or BY
  DEFAULT; virtual columns take no index, primary key, unique nor foreign key (0A000, as 18); stored ones take all of them; `COPY` leaves
  them out of its default columns and names one 42P10; RENAME COLUMN rewrites the expressions, ALTER COLUMN TYPE of a column one reads is
  0A000, of a generated one is allowed (USING 42611), DROP COLUMN of a column one reads is 2BP01 (CASCADE drops the generated one),
  `DROP EXPRESSION` (stored only), `SET EXPRESSION AS` (rows recomputed, indexes made again); `pg_attribute.attgenerated`, `pg_attrdef`,
  `information_schema.columns.is_generated` / `generation_expression`, psql's `\d` (checked against 18.6, `exec_computed`).
- SQL Server: `col AS expr [PERSISTED [NOT NULL]]` at CREATE TABLE and ADD, the type from the expression by SQL Server's rules
  (`lexdb_gen.tsqlType`: casts, columns, varchar + varchar, integer and decimal arithmetic), 271 for a value given (and for DEFAULT), a
  list-less INSERT leaves computed columns out (213 for the wrong count, 109 / 110 with a list), 1759, 4936, 1046, 207, 8183 (NOT NULL,
  DEFAULT, CHECK and FOREIGN KEY on one that is not persisted), 10609 (a filtered index over one), 5074 / 4922 for ALTER COLUMN and DROP
  COLUMN of a column one reads, 4928 for ALTER COLUMN of one, 15336 for sp_rename of a column one reads; indexes and unique constraints
  on them; `sys.columns.is_computed`, `sys.computed_columns`, `COLUMNPROPERTY(.., 'IsComputed')` (checked against SQL Server 2022,
  `tds_computed`).
- Oracle: `[type] GENERATED ALWAYS AS (expr) [VIRTUAL]` and `[type] AS (expr)` (the type optional), ORA-54013 / ORA-54017 for a value
  given, ORA-00947 for fewer values than columns (so an INSERT needs its column list), ORA-54012, 54002, 54016, 904, and 54031 / 54033 /
  54027 for RENAME, MODIFY and DROP of a column one reads; indexes, NOT NULL, CHECK, PRIMARY KEY and UNIQUE on virtual columns;
  function-based indexes take any expression (O8: `CASE`, arithmetic, calls; ORA-01743 for one that is not pure), USER_IND_COLUMNS names
  them SYS_NCnnnnn$ and USER_IND_EXPRESSIONS gives the expression as Oracle writes it, USER_TAB_COLS / TAB_COLUMNS give VIRTUAL_COLUMN
  and DATA_DEFAULT (`tns_computed`).

**A side fix.** T-SQL's `+` in a CHECK, DEFAULT or index expression broke the catalog round trip (the stored text "t+" was not read
back): `CREATE TABLE t (a int, b int, CHECK (a + b > 0))` over TDS failed. parseExpr reads it now, and `sys.check_constraints` shows `+`.

**Tests.** `exec_computed` (PostgreSQL 18, gen_pg.py), `tds_computed` (SQL Server 2022, gen_mssql.py), `tns_computed` (by hand: no
Oracle was at hand), `exec_generated` (hand written: the disk crashed twice and the store opened again, EXPLAIN showing the index of a
stored generated column and an expression index, 3,000 rows batched against `lexdb_batch = off`, an error in a later batch, writes
checked against a recomputation, a rolled back INSERT). Single-row INSERT (in process, five columns and an index, a transaction of
2,000, `perf stat instructions:u`, pinned, base and branch interleaved): 148.5k instructions per statement at the base, 148.4k on the
branch (the additive-operator test in the parser, `isAddOp`, is cheaper than the two `isKw` calls it replaces, and pays for the two
fields every column record gained).

**Left, and unsure.**
- PostgreSQL: `CREATE TABLE ... (LIKE t INCLUDING GENERATED)` (lexdb has no LIKE); a virtual column's NOT NULL is checked at the write.
- SQL Server: `COLUMNPROPERTY(.., 'IsDeterministic' / 'IsPrecise')`; a unique index's NULLs are distinct (SQL Server's are equal) and its
  violation is 2627, not 2601 (both existing); a computed column in a table variable or a table type is parsed, not tested.
- Oracle (documentation and memory, no server): ORA-54027 for DROP COLUMN of a column a virtual one reads, 54031 and 54033, the
  numbering of the SYS_NC columns (after the table's columns, in the order the indexes were made), DEFAULT taken for a virtual column
  in INSERT, MODIFY of a virtual column's own type (allowed here), the hidden SYS_NC rows of USER_TAB_COLS (not listed).

### Q2: virtual columns computed when read (design/lexdb-layers.md 6.3, decided by the coordinator: the owner did not choose)

**Decision.** The virtual kind (Oracle VIRTUAL and the short form, T-SQL's `col AS expr` without PERSISTED, PostgreSQL 18's VIRTUAL
default) is computed where it is read and is not stored; STORED and PERSISTED stay as package C built them. What changes, as the
real systems have it: ADD COLUMN of a virtual column writes nothing (no rewrite, however many rows); an expression's error (a division
by zero) comes at the read, not the INSERT; a T-SQL column that is not persisted may be non-deterministic (`age AS DATEDIFF(day, born,
GETDATE())`, `NEWID()`: a new value at each read; 4936 stays for PERSISTED, and an index, UNIQUE or key on one is 2729). Writes to
one stay refused (428C9, 271, ORA-54013 / 54017), the catalogs are as package C left them.

**How it is built.**
- *Storage.* A virtual column's place in a row has kind `PK_NONE` (`lexdb_rows.placeKind`), as a dropped column's: nothing is written
  for it (`encodeRowOf` puts NULL there, whatever the row holds), `kindsFit` counts it, and the layout the table's next catalog write
  appends says so. A column added is a new place; rows written before read it as missing (NULL), so ADD COLUMN touches no row
  (`rowLayouts` and `treeDump` of the table before and after are equal: `exec_virtual`).
- *Read.* The binder puts the expression where a reference is. `buildQuery` sets, for each virtual column of a table in FROM,
  `ColDef.gen` of the query's column to the column's expression in the query's terms (`lexdb_gen.setQueryGen`: names `alias.column`,
  the query's slots, resolved by `lexdb_bind.resolve` as if the user had written it, cast to the column's type where that differs); `lexdb_bind.colAt` returns it in
  `resolve`, in `*`, ORDER BY, GROUP BY, JOIN ... USING and for outer references (`outerRef`: a correlated reference is the expression of
  the outer row). So the row path and the batch pipeline evaluate it as any expression of the row's other columns, in a projection
  as in WHERE, ORDER BY, a join key or an aggregate; a later batch's error is the row path's error (`exec_virtual`: 26 queries equal
  with `lexdb_batch` off and on, and a division by zero in a row of the fourth batch the same state either way). A scan that reads
  the column reads what it computes from: `lexdb_gen.needDeps` adds the expression's columns to `Level.need` (SELECT's `narrow` and
  `narrowSub`, DELETE's `delNarrow`, the range delete's `slowNeed`); an UPDATE, MERGE or upsert reads whole rows. ON CONFLICT DO
  UPDATE's alias and `excluded` rows get their own (`setQueryGen` over `up.cols`). A select list item that is the column keeps its name.
  A column alias list (`t AS x(p, q, r)`, PostgreSQL: it renames the first columns, the virtual column too) renames the table's columns
  before the FROM item is bound; `lexdb_gen.renamedGens` then gives each virtual column's expression the new names and keeps the
  place each column read has in the table, and `termsOf` / `needDeps` follow that place (a name only where the expression carries
  none), so the expression reads the table's own columns whatever the query calls them, as PostgreSQL 18 does (`exec_computed`: the
  select list, WHERE, ORDER BY, joins, `x.*`, a partial list, a swapped or repeated name, a correlated subquery, a CTE's list; T-SQL
  has the alias list on derived tables only, `tds_computed`).
- *Write.* `genFill` computes only what a write checks: `Defs.fill` (`lexdb_gen.fillCols`) is the stored and kept columns and a virtual
  one with NOT NULL or read by a CHECK; `Defs.gens` (every generated column) still refuses a value given. An index on a virtual column
  (Oracle, T-SQL; PostgreSQL refuses, 0A000) keeps the computed value: `lexdb_access.ixPart` asks `lexdb_exec.idxVal`, which computes it from the row's
  other columns (old rows too: an UPDATE or DELETE has the row it read, whose virtual place is NULL), and index expressions and predicates
  that read a virtual column get it computed (`virtualsOf`). The planner reads such an index for the column's expression: `choosePath`
  matches the conjuncts against `colAt` of the query's column, as it does for an expression index.
- *Kept.* A virtual column a primary key or foreign key holds is `GEN_KEPT` (made by `lexdb_gen.keepKeyed` in CREATE TABLE): the row
  keeps its value, as for a stored column, because the key's bytes come from the row; the catalogs call it virtual. ALTER TABLE ADD
  PRIMARY KEY / FOREIGN KEY over a virtual column is 0A000 (the table would need rewriting).
- *Rows package C stored.* A table made before Q2 has rows whose layout holds the value at the virtual column's place. It is ignored: the
  column is computed from the others wherever it is read, and a row written again has NULL there (nothing is migrated). Until a DDL
  statement stores the table's new layout, such a table's rows are written in the tagged form, not the fixed one (the catalog row has no
  layout for the place's new kind yet); the first DDL on it (or a rebuild) repairs that. There is no migration test: no table of
  the old format is made by this tree.
- *Code.* New code is in `lexdb_gen` (`setQueryGen`, `termsOf`, `renamedGens`, `typed`, `fillCols`, `needDeps`, `keepKeyed`, `keyOnVirtual`,
  `indexable`; it now imports `lexdb_catalog`, and `lexdb_plan` imports it) and one line each in `lexdb_bind`, `lexdb_rows`,
  `lexdb_access`, `lexdb_plan`; `lexdb_exec` has the glue: 19,608 lines before, 19,676 after (the Defs, `idxVal`, `virtualsOf`, `buildQuery`'s call, ADD COLUMN,
  CREATE INDEX checks). `Level.gen` and `Names.virt` keep the checks off the path of a table with no virtual column.
- *Cost.* In process, `-O`, pinned, `perf stat instructions:u`, base (main 4a39ed20) and branch alternated, ten rounds each, setup
  subtracted: a primary-key point select (20,000 of them) 168,253 instructions (median; 167,069 least) at the base, 168,373 (167,254)
  on the branch (+0.07%, inside the 0.15% spread of the runs); a single-row INSERT of a table with no generated column (2,000 in a
  transaction, a primary key and an index) 219.4k median (209.4k least) at the base, 218.8k (209.5k) on the branch (the runs are
  bimodal, 210k / 219k / 229k, by the process: the two variants fall in the same modes). The first cut was 0.5% slower on the point
  select and the INSERT 0.4%: `for c in cols` over `[]ColDef` in `encodeRowOf` (an index loop costs less), and `setQueryGen` and
  `needDeps` called for every column of every table: now an index loop there and the calls guarded by `Level.gen`.

**Left.** ALTER COLUMN TYPE of a virtual column still rewrites the table where it could not (PostgreSQL 18 does not); `ORDER BY v` on an
indexed virtual column is a sort (the index serves `WHERE v = x`, not the order: `servesOrder` sees the expression); statistics are
not gathered for a virtual column (its estimates are the defaults); a table with a virtual column is not copied by COPY's fast path
(unchanged); the Oracle answers added (the `r1`
lines of `oracle_computed_queries.txt`) are by hand, from the documentation: no Oracle was at hand. The T-SQL ones (the `nd`
tables of `mssql_computed_queries.txt`) were first written by hand and were regenerated against SQL Server 2022
(`gen_mssql.py computed`, 2026-11-20): all 121 answers equal the hand-written ones, no difference.


## 9. Oracle answers checked against Oracle Free (ora, 2026-11-21; paused, hand-over)

Several `tns_*` tests had answers written by hand from the documentation or from lexdb's own output ("no Oracle was at
hand"). They are now run against the real server: Oracle Database Free 23.26.3 (`gvenzl/oracle-free:slim`).

**The server.** Podman container `lxl-oracle` (127.0.0.1:1521, service FREEPDB1), left running. After a reboot:
`lexell/tools/oracle_container.sh start` (it waits for "DATABASE IS READY TO USE"); `create` makes it from scratch (its
`tls` step needs the `full` image and was not run). The accounts are in `~/.obo-oracle-dsn` (APP) and
`~/.obo-oracle-dsn.system` (SYSTEM), mode 600; `oracle_container.sh grants` gives APP the V$ and DBA_TABLES reads the
catalog test uses. python-oracledb (thin mode) is in the venv `~/.venvs/oracle`.

**Running it.** `~/.venvs/oracle/bin/python lexell/tests/lexdb/gen_oracle.py --check [TEST ...]` runs the statements of
each test on the server (an emptied schema for each) and prints every answer that differs from the test's `// expect:`
line. It writes nothing. Covered: `tns_catalog, computed, ddl, funcs, merge, oracle, percentile` (the helper calls
`x/q/qb/t/u`), `tns_unnest, unnest_agg, subrows` (their SETUP and query constants), `tns_privs, routinepriv` (accounts
u1-u3, created and dropped by the script), `tns_routine`. Differences listed in `oracle_known_diffs.txt` print as `known`
with their reason; only new ones count (the exit status). Numbers compare by value (lib/oracle shows NUMBER(10,2) with
its scale, the wire has none; 37 against 40 digits). The queries-file generators (`gen_oracle.py SUITE`, `gen_mr.py`)
still write the tests; the headers of `computed`, `ddl` and `funcs` now say their answers are checked.
Also re-run and equal: `gen_mr.py` (all 163 MATCH_RECOGNIZE answers, `tns_mr`; only the generated program text had
drifted, not reverted into the tests) and `oracledb_o6.py --oracle` against `oracle_o6_expect.json` (55 PL/SQL
scenarios, `tns_plsql`): no difference.

**Not checked (lexdb-specific or driver-level):** `tns_client, binds, java` (wire and lib/oracle layouts; the
python-oracledb scripts `oracledb_o2..o6.py` are their check), `tns_nls` (recorded 2026-11-13; its two ORA-41900 lines
are updated below, the rest not re-run), `tns_review, rangedel, plcolumn` (lexdb's own behaviour; plcolumn compares lexdb
with itself), `tns_wait` (only partly Oracle: see FOR UPDATE WAIT below).

**Found and fixed (lexdb now equal to Oracle; expectations updated; all 23 `tns_*` tests pass):**
- A missing DML privilege on a table the user holds another privilege on: ORA-41900 `missing INSERT privilege on
  "U1"."T"` (READ for a query), not 01031 (`tns_privs`, `tns_nls`); a table it holds none on: 942, also for a GRANT by
  such a user. A GRANT without the right to pass the privilege on is 01031, never 01720.
- GRANT SELECT on a function or procedure: 02225; GRANT EXECUTE on a table: 02224; GRANT EXECUTE on a name that is no unit: 04042.
- Virtual columns: DROP COLUMN, and MODIFY within the datatype, of a column a virtual column reads are 54031 (another
  datatype 54033); RENAME COLUMN is allowed and the expressions follow it; DEFAULT on a virtual column 02254. Test inputs
  that Oracle refuses were changed: an index on `a * 2` duplicated a virtual column's expression (Oracle then refuses
  ADD of virtual columns, 54015), now `a * 3`; `varchar2(5)` for a TO_CHAR column is ORA-12899 at CREATE, now `varchar2(40)`.
- Argument counts: functions of a fixed number of arguments are ORA-00909, those with optional arguments 938/939;
  SYS_EXTRACT_UTC of a number 30175; percentile_cont of text 30495, with a frame 30485; `create or alter` 02000;
  `alter table ... alter column` 01735.
- CREATE TABLE AS SELECT: the row count is the rows made (175, not 0).

**Open** (with the reason, in `oracle_known_diffs.txt`): an index on an expression a virtual column's index covers is
accepted (01408); USER_IND_COLUMNS and USER_IND_EXPRESSIONS details of function indexes; system-generated names
(`SYS_Cnnnnnn`, lexdb `T_PKEY`); RENAME of a missing object 04043 (lexdb 942); MODIFY to an unknown type 22858 (lexdb
902); CURRVAL in a subquery (02287) is accepted; GRANT with a column list refused (03001, Oracle grants it); USER_TAB_PRIVS
lacks the PUBLIC INHERIT PRIVILEGES row, ALL_TAB_PRIVS the SYS objects, GRANT ALL the extra privileges, DROP TABLE the
recycle bin; LATERAL over MATCH_RECOGNIZE is a lexdb extension. Not in the known file, to do: **`SELECT ... FOR UPDATE
WAIT n`** (valid Oracle, lexdb ORA-00900; it needs a lock timeout, not a simple change), and the error numbers of
lexdb's own `WAIT n SECONDS` clause on the Oracle door (Oracle says 03049 for the unknown keyword).

**Next:** run `--check` after any Oracle-door change; check `tns_nls` and `tns_wait` the same way (add the `println(`
form to the scenario parser); ORA-41900 holds for this image (23.26), the 2026-11-13 recording had 01031.

## 10. Recursion in the doors (rec, 2026-11-22)

Before: lexdb's recursive CTE was PostgreSQL's `WITH RECURSIVE` only (rounds over a working table, `SET max_recursion`,
lexdb-layers.md 6.3.Q8 R2). The T-SQL door refused a CTE that names itself (208), the Oracle door Oracle's recursive
WITH (ORA-00942), and the Oracle door's CONNECT BY was the `dual connect by level <= n` generator alone. Each product's
behaviour below was checked on the real server (SQL Server 2022 in `lxl-mssql`, Oracle Free 23.26 in `lxl-oracle`,
the scratch PostgreSQL 18.6), and the tests' answers are theirs.

**What the products do.**

- *SQL Server.* A CTE that names itself is recursive (no RECURSIVE). Anchor members (several, combined by UNION ALL,
  UNION, EXCEPT, INTERSECT), then UNION ALL and the recursive members (several, UNION ALL only); errors 246 (no anchor),
  247 (an anchor after a recursive member), 252 (no top-level UNION ALL: UNION, EXCEPT, a lone member), 253 (two
  references in a member), 460 DISTINCT, 461 TOP/OFFSET, 462 any outer join, 465 a reference in a subquery of an
  expression (one in a derived table is taken), 467 GROUP BY, HAVING or an aggregate (in a scalar subquery of the member
  too), 240 a column's type (and length) not the same in both parts (a NULL anchor takes the recursive part's), 8158 /
  8159 the column list's length, 239 a CTE named twice. MAXRECURSION: 100 by default, `OPTION (MAXRECURSION n)` 0 (no
  limit) to 32767 (310 past it, 1042 given twice, 102 for a negative or a variable); a row at level n + 1 is 530 ("The
  statement terminated. The maximum recursion %d has been exhausted before statement completion."), the statement
  rolled back. The rows come from a stack spool: the anchors as made, then the last row made is expanded next, its
  children after it, so without ORDER BY the order is depth first from the last sibling; a client streaming a plain
  SELECT of the CTE gets the rows made before the 530 and then the error (with ORDER BY or an aggregate: the columns and
  the error; `TOP n` stops the spool, no error when n rows come first). WITH ... INSERT / UPDATE / DELETE / MERGE.
- *Oracle.* Recursive subquery factoring needs the column alias list (ORA-32039); exactly two branches joined by UNION
  ALL (32040 for UNION or one branch, 32041 for three), the recursive one may come first; 32486 (aggregate, DISTINCT,
  GROUP BY in the recursive branch), 32487 (the CTE on an outer join's NULL side; `r LEFT JOIN t` is taken), 32490
  (referenced twice), 32042 (in any subquery, derived tables too), 01790 (different datatypes; lengths do not matter,
  `s || 'a'` grows), 32038 (the list's length). Rows come iteration by iteration (each round's rows in their parents'
  order). A row equal in every column to an ancestor is ORA-32044 (a cycle), and so is a recursive branch without any
  predicate (`WHERE 1 = 1` included), at once, before a row. `SEARCH DEPTH|BREADTH FIRST BY c [ASC|DESC] [NULLS
  FIRST|LAST], ... SET o` numbers the rows 1.. in that order and gives them in it; `CYCLE c, ... SET m TO 'Y' DEFAULT
  'N'` marks a row whose columns are an ancestor's, gives it and does not expand it (the values one-character strings or
  digits: 32047; 32048, 32046, 32482, 32489 for the names). Hierarchical queries: `START WITH` (none: every row a root),
  `CONNECT BY [NOCYCLE]` with `PRIOR` on either side and LEVEL, the WHERE applied after the hierarchy, depth first with
  siblings by `ORDER SIBLINGS BY` (the roots too, when START WITH gives them); a loop is a row whose PRIOR operands'
  values are an ancestor's (`prior sys_guid() is not null` is the known trick): ORA-01436, or with NOCYCLE the row left
  out and its parent's CONNECT_BY_ISCYCLE 1; CONNECT_BY_ISLEAF, CONNECT_BY_ROOT, SYS_CONNECT_BY_PATH, PRIOR in the select
  list; PRIOR without CONNECT BY ORA-01788, ORDER SIBLINGS BY without it ORA-30929; without PRIOR (`connect by level <=
  n`) no loop check.
- *PostgreSQL 14+.* `SEARCH DEPTH|BREADTH FIRST BY c, ... SET o` (no ASC/DESC/NULLS) adds o, a `record[]` path (depth
  first) or a `record` (depth, columns) (breadth first); the rows are not reordered (ORDER BY o does it). `CYCLE c, ...
  SET m [TO v DEFAULT d] USING p` adds the mark (boolean by default; integers, texts) and the path p (`record[]`); a row
  whose columns are in its path is marked and not expanded; a NULL is never equal. Errors 42702, 42601 (column not in the
  list, mark or path name taken or the same, not recursive, no USING), 42701 (a search column twice), 22P02 (1 and 'N').
  A recursive reference in a derived table is taken; in a subquery of an expression 42P19.

**What was built.** Parsing in lexdb_parse (the T-SQL door's parser is the same with `tsql`), the rules and the shape in
a new module, `lexdb_recur` (statements only), the run's dialect parts in another, `lexdb_recrun`; lexdb_exec's
`runRecursive` runs the rounds as before and hands them over (`runRecursiveAs`); the pipeline's held working table is
unchanged.

- `withList`: in T-SQL and Oracle every CTE is in scope in its own body; one that reads itself is recursive.
  `lexdb_recur.check` gives each dialect's errors when the WITH is read; `lexdb_recur.shape`, where the CTE is used,
  makes the body the executor runs: the anchors as written, UNION ALL, the recursive members as one UNION ALL query
  (Oracle's branches swapped when the recursive one is first), and the *lineage*: a hidden last column
  (`\x00rowid:rid`, hidden as a keyless table's rowid is, so `*` never shows it) that is 0 in the anchors and the working
  table's row number in the recursive members, so the run knows each row's parent. Its `Spec` (dialect, SEARCH, CYCLE,
  CONNECT BY's flags, the CTE's name and columns) rides in the set operation's `Stmt.index` and the Sel's one expression
  (set operations have no other use for them; no new field on Stmt or Sel).
- `lexdb_recrun`: the CTE's columns (lineage hidden; SEARCH's, CYCLE's added; T-SQL's 240 by type and hinted length,
  Oracle's 01790 by datatype family), and the run: each round's rows numbered with their parent and level, UNION's dedup
  kept, the loop check (CYCLE's columns, CONNECT BY's PRIOR values, Oracle's whole row; by a hash of the keys seen, the
  ancestors walked only on a hit), the limit (T-SQL 530, Oracle's lexdb limit as 32044, PostgreSQL's 54001), and at the
  end the rows in the dialect's order: SQL Server's stack, Oracle's iterations or its SEARCH order, PostgreSQL's rounds;
  SEARCH's ordering column (Oracle: the place; PostgreSQL: `Reg(place, text)` typed `record[]` / `record`, so it sorts as
  PostgreSQL's path does and prints as record_out and array_out write it; `_record`, 2287, added to pg_type), CYCLE's mark
  and path.
- T-SQL door: `OPTION (...)` read after a statement (lexdb_tsqlparse: MAXRECURSION kept in the TS_SQL statement's flags,
  the other hints read and ignored, an unknown one 102); the session's limit 100 (lexdb_tds sets it at login and reset;
  `OPTION` sets it for the statement); a SELECT that fails with 530 is run again stopped at the limit
  (`lexdb_recrun.TRUNCATE`, read only) and its rows (or, when it does not stream from the CTE, its columns alone) are sent
  before the error, as SQL Server sends them; with TOP n and n rows the answer is those rows.
- Oracle door: `START WITH` / `CONNECT BY` after WHERE (`hierTail`, reached from selectCore's existing Oracle branch, so the
  other doors pay nothing), `PRIOR` and `CONNECT_BY_ROOT` as operators (oraPrimary), `ORDER SIBLINGS BY`; the query is
  rewritten (`lexdb_recur.hierQuery`) into a recursive CTE over its FROM item: the item's columns and hidden columns for
  LEVEL, CONNECT_BY_ISLEAF, CONNECT_BY_ISCYCLE and per PRIOR / CONNECT_BY_ROOT / SYS_CONNECT_BY_PATH use, per PRIOR
  operand of CONNECT BY (the loop check) and per sibling key; the anchor the item's rows under START WITH, the recursive
  member the item joined to the working table ON the CONNECT BY condition (PRIOR's operands the parent's, an unqualified
  column the child's, LEVEL the parent's + 1); the run depth first by the sibling keys, a loop row left out (NOCYCLE) or
  ORA-01436; the query reads the CTE under the item's alias, its WHERE after the hierarchy. The `dual connect by level`
  generator is kept as it was (a token rewrite to generate_series, before any of this).
- PostgreSQL door: SEARCH and CYCLE as above; a recursive reference in a derived table now taken (lexdb said 42P19).

**Tests.** `tds_recursion` (72 batches; SQL Server 2022's answers, generated with LEXDB_MSSQL against an empty
database), `tns_recursion` (81 statements; registered in gen_oracle.py; `--check` against Oracle Free: 81 answers, no
difference), `exec_recursion` (37 statements; PostgreSQL 18.6's answers; `tests/lexdb/check_pg.py` checks the test's
lines against a PostgreSQL server: no difference), each statement with batches off and on. Suite 308 of 308.

**Gates** (branch a2e15762 against main ed51b718, both built `-O` alike). Point statements in process (`LXL_HASH_SEED=1`,
the 1-statement run subtracted from the 20,000-statement one, two rounds, identical within 0.2 instructions): select by
key 124,628.6 against 124,631.6 instructions, INSERT -48, UPDATE by key -6. Over the wire (`icount6.sh BIN 3`, three
alternated pairs): 173,364 / 173,357 / 173,372 against main's 173,600 / 173,349 / 173,364 instructions a statement (main's
own spread 250; cycles and L1 i-cache misses lower or level). TPC-H SF1 (`~/tpch-w/rec`, alternated twice): totals
9,091 and 8,920 ms against main's 9,776 and 9,244 (best of each: 8,913 against 9,098, 0.98), checksums equal on all 22
and the reference's; no query slower beyond its runs' spread.

**Left.**
- CONNECT BY over more than one FROM item (a join, or comma-joined tables with the join in WHERE) is 0A000: Oracle joins
  first, then builds the hierarchy, then applies the rest of the WHERE. Plan: build the CTE's base as a derived table of
  the join (the parenthesised-tree subquery, TREE_STAR, keeps the columns' qualifiers), split the WHERE's conjuncts into
  the join's (those naming two FROM items, as Oracle does) and the rest, and qualify the CONNECT BY condition's columns
  against that tree; the rest is as built.
- Without START WITH, Oracle's roots come in an order of its own (not ORDER SIBLINGS BY's); lexdb gives them in the
  FROM item's order, then siblings as asked.
- SQL Server's row order without ORDER BY follows its plan; lexdb's is the stack order over the rows as its join makes
  them (each parent's children in the join's order), which is SQL Server's for the plans checked. Where a recursive member
  reads the working table only inside a derived table there is no lineage and the rows come round by round.
- T-SQL types: lexdb does not know an expression's length or a numeric's precision, so 240 is given for a different type
  or a hinted length (CAST(... AS varchar(10)) against varchar(11)), not for `'a'` against `s + 'a'` or numeric(5,0)
  against numeric(6,0) (SQL Server: 240).
- Oracle: lexdb's own round limit (max_recursion, 1000 by default) is ORA-32044 with lexdb's note; Oracle has no limit
  and runs on. The ORA-32044 of a branch without a predicate is lexdb's reading of what Oracle does (WHERE 1 = 1 and a
  join ON 1 = 1 are it, `WHERE n > 0` is not).
- Rows before an error other than 530 (8134 in a later row, ...) are not sent: the T-SQL door sends an error alone, as
  before. `TOP n` over a CTE that never ends, with `MAXRECURSION 0`, runs until lexdb's statement memory
  (max_statement_mem) ends it: SQL Server stops the spool after n rows; lexdb runs a CTE's rounds before its reader.
- Found, not fixed (not recursion's): a non-recursive CTE's column list names its columns in lower case in the T-SQL and
  Oracle doors (`WITH r (X) AS (SELECT 1) SELECT * FROM r` shows `x`; SQL Server `X`, Oracle `X`): the FROM item's
  column list carries folded names (lexdb_exec's FROM binding). The recursive ones name theirs as written
  (`lexdb_recur.Spec.spells`).
