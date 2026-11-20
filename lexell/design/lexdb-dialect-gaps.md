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
| B | worktree-agent-a1e05408b04aabd79 | merged (MERGE_B); done 2026-11-20: `a3eacc68` (CREATE OR ALTER VIEW, ALTER VIEW, OR REPLACE in each dialect's rules, the misleading CREATE error), `16e65314` (ALTER DATABASE ... SET, new module lexdb_dbopt), `3faf9a1a` (renames: sp_rename, Oracle RENAME, PostgreSQL views following), and `13dafca3` (ALTER COLUMN type: T-SQL, PostgreSQL, Oracle MODIFY); suite 218 of 218. Tests: exec_ddl (PostgreSQL 18), tds_ddl (SQL Server 2022), tds_ddlgaps (hand: "not supported yet" messages), tns_ddl (Oracle: answers by hand from the documentation, no Oracle at hand). Left: views follow renames by a recorded overlay (Table.rn), so pg_get_viewdef and OBJECT_DEFINITION keep the text as written; a PostgreSQL view on a retyped column is found by the names in its text (it may refuse a column PostgreSQL would allow); a foreign key's column cannot be retyped (0A000, PostgreSQL allows compatible types); retyping a serial or identity column to text; PostgreSQL's re-binding of a CHECK after a type change (42883) is not done (the rows are rechecked); T-SQL nvarchar is not told from varchar (so varchar to nvarchar on an indexed column is not 5074), tinyint is smallint, ALTER COLUMN ... COLLATE, ALTER DATABASE READ_ONLY/SINGLE_USER/OFFLINE and its other forms, `SET TRANSACTION ISOLATION LEVEL SNAPSHOT` does not check ALLOW_SNAPSHOT_ISOLATION (3952), a table named as another table's index (SQL Server allows, lexdb's indexes share the schema's names), CREATE VIEW not first in a batch is not 111; Oracle: from memory ORA-14155 (RENAME without COLUMN), ORA-00905 (ALTER COLUMN), ORA-01439/01440/01441/02296, a `select *` view over a renamed column is not invalidated, CREATE OR REPLACE FORCE VIEW |
| C | | not started |
| D | worktree-agent-a28c35465652ef944 | merged (6dc5e38f; TPC-H 0.991 of ca529e9d alternated, checksums equal); done, 2026-11-20: `ee73ea26` (aggregate, PostgreSQL and Oracle), `2337277c` (window form, SQL Server and Oracle); suite 211 of 211. Left: PostgreSQL's array fraction `percentile_cont(array[...])`; PostgreSQL's `42803` for an ungrouped column in the fraction (the value of the group's first row is used); SQL Server's 402 for text/dates is raised at the first row, not at compile (an empty set gives NULL); Oracle's messages ORA-30487, ORA-00907 (frame) and ORA-00932 are from memory, no Oracle server was available (expectations in `tns_percentile` are by hand); Oracle DATE interpolation rounds to microseconds, intervals are not testable in Oracle until its interval columns exist (package A) |
| E | `worktree-agent-a5b25663707eeb5fb` | merged (f07b6e5d; TPC-H 0.973 of a1aa79e3 alternated, checksums equal; point selects unchanged); done, awaiting review; section 6 |
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
