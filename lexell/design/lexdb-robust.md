# lexdb: robustness and wrong answers from the documentation pass

The last pages of the user documentation (lexell/docs/lexdb/KNOWN-ISSUES.md: the Oracle sections and "T-SQL phase 3") found hangs,
dropped connections and wrong answers. This slice (branch `worktree-agent-a450f2a0c5292c967`, from main ca687450, tag `rb-base`) fixes
what is below under "As built" and plans what was too large under "Plans". Each fix was checked against the real product (SQL Server
2022 / 2025, Oracle Free 23.26, PostgreSQL 19 in the podman containers), each has a test per door that has the behaviour.

## As built

### Oracle door (lexdb_tns, lexdb_plsql, lexdb_plcall, lexdb_parse, lexdb_oracat)

- **A statement of 83 bytes starting with S, 82 starting with R ... (the "84-byte statement", and a one-line `CREATE FUNCTION`, which
  was the same bug: 67 bytes and a C).** `lenStr` told a length byte from JDBC's bare text by "the first byte equals the length": a
  statement whose first letter's code is its length (SELECT of 83 bytes: `S`, 83; INSERT of 73; CREATE of 67; BEGIN of 66; DECLARE
  68; WITH 87; UPDATE 85) was read as python-oracledb's length-prefixed form, so the text came out one byte short and shifted (ORA-00900, or the
  connection closed by the next message). The client's table of types says whose it is (`Out.sb1u`: universal SB1 is JDBC's): with
  JDBC the text is bare (`parseRequest`'s `jdbc`), else the old rule. ojdbc swept over statement lengths 10 to 600 and around the
  SDU (8192, 16384, 32768, 65536), thirteen shapes (SELECT, select, WITH, INSERT, UPDATE, DELETE, BEGIN, DECLARE, CREATE FUNCTION and
  PROCEDURE, a comment first, two with binds): 0 failures (`tests/lexdb/java/OracleJdbc.java`, "lengths").
- **CREATE PROCEDURE with an undefined call closed the connection (ORA-17008).** The warning ORA-24344 was sent as a WARNING message
  whose text JDBC reads bare (python-oracledb's is length-prefixed): the extra length byte was a protocol violation (ORA-17401) and
  ojdbc closed. Oracle sends no WARNING message at all: the call's ERROR message carries the warning flags (the sixth of the six
  flag bytes after the cursor: 0x21), and ojdbc turns them into `SQLWarning` "ORA-17110: Execution completed with warning". lexdb does
  that for JDBC (lib/oracle, python-like, still reads the WARNING message). The unit is **stored invalid**: the compile error is kept
  after the source in the unit's catalog value (a NUL between), `USER_OBJECTS.STATUS` is INVALID and `USER_ERRORS` / `ALL_ERRORS`
  have the PLS error and its "PL/SQL: Statement ignored" at its line and column. A unit that does not compile when it is next compiled
  (a dependency dropped) becomes invalid, one that compiles again is valid when a block that names it runs (`revalidate`) or
  `ALTER PROCEDURE | FUNCTION name COMPILE` (now real: ORA-04043 for a name that is none, the warning when it still fails). `CALL` of
  an invalid unit is ORA-06575, a block's PLS-00905 inside ORA-06550.
- **A SELECT calling a stored function that raises: ojdbc's NullPointerException.** The error ORA-01403 (NO_DATA_FOUND) of a function
  is NULL in Oracle's SQL (checked: `select f(1) from dual` gives a NULL row); lexdb answered ORA-01403, which ojdbc takes for the end
  of an empty cursor (no describe: `accessors is null`). Now NULL (`lexdb_plcall.compute`, `expandCalls`). The other errors
  of such a function end the query with the unit's own text: `ORA-06510` for an unhandled user exception, the ORA-06512 lines of the
  unit (`lexdb_plsql.sqlError`: not the anonymous block lexdb calls it through).
- **ROWNUM.** `WHERE ROWNUM <= n` is lexdb's LIMIT, applied after the groups and the DISTINCT: `SELECT COUNT(*) FROM emp WHERE ROWNUM < 4`
  was 5. Oracle numbers the rows before them. For one table in FROM (no join, no subquery of the select) a select with an aggregate,
  GROUP BY, HAVING, DISTINCT or ORDER BY takes its rows from `(SELECT * FROM t WHERE ... LIMIT n)` (`oraLimit`). A join keeps the
  limit on its output (not done). `UPDATE` and `DELETE` take the ROWNUM tests of their WHERE as the statement's limit (`dmlWhere`:
  TOP's `firstN`, ORA-20000 before).
- **REGEXP_SUBSTR, _INSTR, _COUNT, _REPLACE, _LIKE.** Oracle's arguments (position, occurrence, return option, match parameter,
  subexpression, `REGEXP_REPLACE`'s default occurrence 0 = all, a NULL replacement = removed, two arguments) go to lexdb's own functions
  of the same argument order; the match parameter is marked `RE_ORA` and read as Oracle does (`oraReFlags`: i, c, n = dot matches a
  newline, m = ^ $ at lines, x; default: the dot does not match a newline; ORA-01760 for another letter), position, occurrence and
  return option errors are ORA-01428, a pattern's errors ORA-12725 to ORA-12732 (a backreference `\1` is ORA-12727: the engine has none).
- **DROP SEQUENCE while a column's DEFAULT uses it** is allowed (Oracle's; ORA-02449 was the foreign key's text); a later
  `s.NEXTVAL` of it is ORA-02289 (also for a missing sequence named in a statement). An INSERT whose DEFAULT calls the dropped
  sequence still says ORA-00942 (the default's evaluation does not know it is a sequence).

### SQL Server door

- `REGEXP_REPLACE('abc', 'b')`: two arguments read past its argument list (an index out of range in lexdb_parse: the *server* failed,
  the batch never answered); the replacement is optional, the matches removed (SQL Server 2025's).
- `LOG(x, base)`: the arguments were swapped.
- `tinyint` is 0 to 255: 220 for a cast, an INSERT, an UPDATE or an assignment out of range; 244 for a string; TRY_CAST NULL.
- `char(n)` and `nchar(n)` are padded with blanks to n by every conversion to them.
- `datetime + days`, `datetime - days`, `days + datetime` and `datetime - datetime` (a datetime from 1900-01-01 on, as SQL Server's),
  `smalldatetime` the same; `date`, `datetime2`, `datetimeoffset` and `time` with a number are 206 (`lexdb_bind.tsDateArith`: where the
  operands are columns or casts, whose types the binder knows).
- `FORMAT` with a culture: the names, patterns, separators and AM/PM of en-US, en-GB, de-DE, fr-FR, es-ES, it-IT, nl-NL, pt-BR, ja-JP and
  sv-SE (read from SQL Server 2022 for four dates each; `lexdb_tsqlfmt.CULTURES`); `time` values are formatted as a .NET TimeSpan
  (`c`, `t`, `T`, `g`, `G`, custom `hh\:mm`; NULL for the others).
- **0x literals are `varbinary`** (they were an int up to 8 digits). Beside a number a binary is read as the number (int, bigint beside
  one: its last bytes, big-endian), beside another binary `+` joins them and `- * / % & | ^` are 402, beside a string a comparison
  reads the string as bytes and the others are 402, a decimal beside one is 8114. CAST and CONVERT to varbinary(n) / binary(n)
  (a string by its bytes, style 1 and 2 hex text, a number big-endian, binary padded with zeros, cut to n) and to varchar / int /
  bigint / smallint (bytes as characters, styles 1 and 2 hex, the last bytes), `LEN` and `DATALENGTH` of bytes, `SUBSTRING` (bytes),
  `LEFT` and `RIGHT` (characters), assignment to int, varchar, binary(n) (padded) and varbinary(n) (2628) columns.
  lexdb-tds.md section 13's old reading (an int up to 8 hex digits) is replaced.
- `DROP SEQUENCE` under a column's default: 3729 (the default constraint named `DF__table__column__nnnnnnnn`); a second PRIMARY KEY by
  ALTER TABLE: 1779 (CREATE TABLE's is 8110); two CLUSTERED keys in one CREATE TABLE: 8112 (CREATE INDEX's and ALTER TABLE's second
  clustered key stay 1902); `OBJECTPROPERTY(id, 'TableHasPrimaryKey')` was "has a clustered index" (the index lines now say primary key and
  unique constraint: `TableHasUniqueCnst` too).

### All doors

- **UPDATE and DELETE read their subqueries as the statement found the rows.** A correlated subquery in `SET` or in `RETURNING` read
  rows the statement had already changed (found rows were written one by one, each row's SET evaluated just before its write). With
  subqueries in the statement, `updateB` evaluates every row's new values (and RETURNING) first and writes after (`updNew`: an error of
  a row's values ends them and the rows before it are written first); `deleteB` evaluates RETURNING first. A statement without a
  subquery runs the old loop unchanged (the point path). PostgreSQL 19, SQL Server 2022 and Oracle Free give the same answers.
  MERGE: see "The leftovers" below.
- PostgreSQL: a LANGUAGE sql function's column is named as the function (`twice`, not `int4`: the select item takes the name of
  the call that was inlined); `INTERVAL(p) '...' FIELD` and `INTERVAL FIELD '...'` are syntax errors (42601), `INTERVAL(p)` keeps its
  precision (it was reset to none).

## Plans (too large for this slice)

### Oracle TIMESTAMP WITH TIME ZONE and FROM_TZ keep their offset (item 9)
`Val.Tstz(int)` is microseconds since 2000-01-01 UTC: the offset a value was written with is lost. Oracle keeps a region or offset
per value, shows it (`2026-03-15 10:00:00.000000 +02:00`, TO_CHAR TZH/TZM/TZR/TZD), EXTRACT(TIMEZONE_HOUR | TIMEZONE_MINUTE |
TIMEZONE_REGION | TIMEZONE_ABBR) reads it, compares by instant, `AT TIME ZONE` converts, a column holds values of mixed offsets.
Plan: a new `Val.Tsz(int, int)` (instant, offset in minutes; a region as a negative id into a table of names) in `lexdb_sql.Val`
(a closed enum: every `match` without `else` is a compile error that lists the sites; the ones with `else` are the risk: comparison
(`lexdb_ops.cmp`), hash and group keys (`keyOfVals`), sorting, row encoding (`lexdb_rows` kinds, `encTable` of defaults),
batch columns (`lexdb_pipe` falls back for a kind it does not hold), TNS describe and cell bytes (type 181), `lexdb_time` parse and
text out, casts, `lexdb_orafn` (FROM_TZ, SYS_EXTRACT_UTC, EXTRACT, AT TIME ZONE, TO_TIMESTAMP_TZ, NEW_TIME, TZ_OFFSET). About 300
sites in 25 files (`grep -c Val.Tstz`: 160). Start with the TNS door alone: Oracle columns of TIMESTAMP WITH TIME ZONE store the
instant and the offset in a second column?? No: store `Val.Tsz` natively, PostgreSQL's and SQL Server's `datetimeoffset` (the same
loss: KNOWN-ISSUES "a datetimeoffset is converted to UTC") take it too, in their own slice.

### PostgreSQL's bare-literal overflow and recursive CTEs (item 13)
Built in the second robustness slice (below, "The second slice").

## The leftovers (2026-11-24)

The planned items of the two sections above, built on `worktree-agent-a7390c6519a32d455` (from main a15b9a64, tag `lo-base`); each fix was checked against the products
(PostgreSQL 19, SQL Server 2022, Oracle Free 23.26) and has a test per door.

### MERGE's subqueries
`merge` now works a row in two steps, `mergePlan` and `mergeApply`: the plan decides the row's clause (its WHEN condition), evaluates the values (UPDATE's SET, INSERT's
values, Oracle's UPDATE WHERE and DELETE WHERE) and the RETURNING / OUTPUT row, and counts the target rows touched twice (ORA-30926 / 21000 / 8672; Oracle's ORA-08006 for a
row its DELETE WHERE deleted and a later source row matches); the apply writes. With subqueries in the statement (`len(q.subs) > 0`) every row is planned before any is
applied (an error ends the planning; the rows before it are written first, as `updateB` does); without, each row is planned and applied in turn, as before. An INSERT
clause's row is built by `insertOne` in a dry mode (`CONFLICT_DRY`: `conflictOf` says the row is its own conflict and `upsertOld` gives it back; a check inside `insertOne`
itself cost a plain INSERT one instruction) and stored by `storeRow` in the apply. PostgreSQL 19, SQL Server 2022 and Oracle Free read their subqueries as of the statement's start in every clause, RETURNING included (SQL
Server's OUTPUT takes no subquery: 10705, now also here for INSERT, UPDATE and DELETE). Found by the tests: a text column of `VALUES` in a T-SQL session has the
session's collation (it was an exact one: a column beside it was error 468, and `'A' = 'a'` was false). Tests: `exec_mergesub`, `tds_mergesub`, `tns_mergesub`.

### The Oracle door's schemas (lexdb-oracle.md section 22)
Built as planned, except that the roles are not given the schema when made but at their first Oracle login. Tests: `tns_ownschema`, `tns_nls` (reads `sa.pub`),
`replica_doors` (the schema's commit moves the LSNs by one).

### Package variables
See lexdb-oracle.md, "As built: package variables". Tests: `tns_pkgvar` (`gen_oracle.py --check`: 0 differences), `tns_pkgstate`.

### Small ones the coordinator asked for
`CAST` and `CONVERT` of a uniqueidentifier to `binary(n)` / `varbinary(n)` (error 529 since the hex-literal slice; SQL Server's mixed-endian layout: the first three groups
little-endian), of a binary to uniqueidentifier (padded or cut to 16 bytes), a uniqueidentifier as a string in upper case (8170 for `varchar(n)` under 36);
`OBJECTPROPERTY(id, 'TableHasNonclustIndex')`. Test: `tds_guidbin`.

## The second slice (2026-11-24)

The planned items of "Plans" and the gaps the last slice left, on `worktree-agent-a9cdc75e89e3586c6` (from main 6275b6eb, tags `rp-base` and `rp`). Each was checked against the
products (PostgreSQL 19, SQL Server 2022, Oracle Free 23.26) and has a test per door that has the behaviour: `exec_robust2` (`gen_pg.py robust2`), `tds_robust2`
(`gen_mssql.py robust2`), `tns_robust2` (`gen_oracle.py --check tns_robust2`: 0 differences).

### A recursive CTE under LIMIT with a filter, a join or a derived table
PostgreSQL and SQL Server make the CTE's rows as the query above it asks for them: `WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n) SELECT i FROM n WHERE i % 7 = 0 LIMIT 3`
is 7, 14, 21 (`TOP 3` with `OPTION (MAXRECURSION 0)` too; MAXRECURSION counts the levels the rows TOP needs take: 530 when they are further than it). Oracle never stops: ORA-32044
for every endless recursion under `FETCH FIRST`, a join or a filter (so the Oracle door is left as it is: `lexdb_recprobe.mark` is not asked for a statement of that door).
lexdb made a CTE's rows whole (rounds, `runRecursive`) before the query read them, so the stop flag the plan called for was not possible. What is built: a query with a LIMIT (and
OFFSET) and no ORDER BY, grouping, DISTINCT, window, lock or set-returning function in its list, that reads one recursive CTE it alone uses (`Stmt.cteOnce`, `SubPlan.need` -2) as its first
table, or a plain select of such a query (a derived table), marks that subquery with the rows it needs (`limitQuery`, `lexdb_recprobe.mark`; its joins are inner or left, its conditions
call no volatile function and no subquery). `runSubs` then runs `probeRecursion` before the subquery: an attempt makes the CTE to a cap of rows (a whole round past it: `runRecursive`
reads the cap from the run's cache, key `k` and the CTE's number, and notes how it ended under `x`), reads it with the query's levels by the row engine and counts the rows they keep.
Too few: the cap is doubled (64 first). The attempt that has enough, or in which the recursion ended by itself, leaves its rows in the cache where `runFrom` finds them, and the query
then runs as always, with batches on or off, to a sink or held. If the CTE's rounds ran out (max_recursion, MAXRECURSION) before the query had its rows, the CTE is run as it was: its
error. An error of a cap's attempt may come from rows the query would not have read (`1 / (i - 40)` in the recursive part when the query is satisfied at 21): the caps below it are
tried (a bisection: `lexdb_recprobe.Search`), the smallest that errors gives the error. `limitRecursion` (the plain case, 9.139) took a CTE read twice as read by this query alone:
`(SELECT * FROM r LIMIT 3) UNION ALL (SELECT * FROM r)` gave the second part three rows; it asks `cteOnce` now. A door's recursion (`runRecursiveAs`: SQL Server's stack spool order, made
at the end from the rounds' lineage) stops at a cap only while every round has made one row (a chain: its order is the rounds'); a tree runs to MAXRECURSION as before.
Not done: a join where lexdb's planner reads the other table first (`FROM rt JOIN n`: PostgreSQL stops, lexdb gives 54001), a CTE read by a subquery of the WHERE (`IN (SELECT ...)`),
an ORDER BY or aggregate over the CTE (PostgreSQL and SQL Server do not stop either), a constant false WHERE (PostgreSQL does not run the CTE at all). The probe runs the query's levels
once more (EXPLAIN ANALYZE counts them twice).

### PostgreSQL's bare-literal overflow
`SELECT 2147483647 + 1`, `-2147483648 - 1`, `2147483647 * 2`, `46341 * 46341` and a chain of such (`1 + 2147483647 + 1`) are 22003 `integer out of range`, `9223372036854775807 + 1` and
`-9223372036854775808 - 1` `bigint out of range` (a literal past int4 is a bigint, a negated literal is a literal: `-2147483648` an integer; `2147483647 + 1::bigint` and `+ 1.0` are
not errors). Built in `lexdb_litint` (`walk`, `check`), asked by the parser for each expression of a select list in the PostgreSQL door that is not a column (`itemListAssign`), where the
statement is read (so `WHERE false` does not hide it, as PostgreSQL's planner does not). Where it could not go: a check in `addExpr` / `mulExpr` of the parser costs every statement
a few instructions whether it has arithmetic or not (the frame of the two functions: +12 instructions of an INSERT by a single added `try`), a call from their loops costs an UPDATE's `v + 1`
19 instructions, the binder's `intChecked` costs nothing but cannot tell the Oracle door's NUMBER literals from the PostgreSQL door's (no dialect in `Names`), and the Oracle door's
`2147483647 + 1` is 2147483648. The select list's `else` of the existing `isColExpr` test costs a statement of columns nothing. Not covered: literal arithmetic in WHERE, ON, HAVING,
ORDER BY, INSERT's values and UPDATE's SET (the column's own range still gives 22003 for the last two). The Oracle door's `9223372036854775807 + 1` is ORA-01426 (Oracle: 9223372036854775808),
and T-SQL's is 8115 (SQL Server: a numeric, no error): both as before, the literals past int4 being numbers there.

### UPDATE's CHECKs, SQL Server and Oracle
The retry of the whole statement (`retryLax`, `failedInBlock`, a memo key) is gone, with its gaps (BEGIN TRANSACTION of the T-SQL door, `UPDATE ... OUTPUT ... INTO`, `MERGE`, a single
autocommit UPDATE of the Oracle door). `updRow`'s check failure tags its error (`LAX` in its `context`; the error path only) and the places that know the columns a statement sets try the
row again (`laxRow`): `updateB` (the plain UPDATE, UPDATE ... FROM, the two-phase form), `mergeApply` (the clause's targets: `MAct.set`) and `upsertOld`; the checks that read one of the columns are
tested, and the row is written by `updRow` with a copy of the table that has no other check. PostgreSQL's door gets the error untagged (every check), a cascade's child too.
SQL Server 2022 and Oracle Free: `SET a = a` fails when a CHECK that is not validated reads `a`, `SET b = ...` does not, in a transaction, with OUTPUT INTO a table or a table variable, in MERGE
(Oracle's WHERE and DELETE WHERE forms too), in `UPDATE ... FROM` and `UPDATE TOP`; an INSERT tests every check.

### Oracle package variables as targets
`SELECT ... INTO pkg.v`, `FETCH c INTO pkg.v`, `... RETURNING ... INTO pkg.v`, `EXECUTE IMMEDIATE ... INTO pkg.v` and `USING OUT | IN OUT pkg.v`, and a procedure's OUT and IN OUT arguments
`proc(pkg.v)` work from outside the package (lexdb-oracle.md, "As built: package variables"). `Cx.target` gives a slot of the statement's own, `Cx.stmt` wraps the statement and the
`K_PVSET`s that copy the slots to the variables into a block, so an error leaves a variable as it was (Oracle's by-copy OUT). Found on the way, not fixed: `SELECT pkg.f() FROM dual` of a
function reading a package variable is the plan's constant: a second `SELECT pv.f() FROM dual` after an assignment gives the first answer (the same on main).

### FORMAT in the other 36 cultures
`lexdb_tsqlfmt.CULTURES` has the dates of every specific culture the table of numbers knows (47 with the ten) except ar-SA (the Hijri calendar): names, abbreviations, AM and PM, the date
separator and `d D t T M Y` (so `f F g G`) read from SQL Server 2022 with two dates and read off into patterns by a script that reproduces the ten that were there exactly. New: the genitive
month names (`MMMM` beside a `d` or `dd` of the pattern, outside the quotes: .NET's rule `genitive`; pl, cs, ru, uk, el and fi-FI), the time separator a custom `:` takes (fi-FI and id-ID: `.`),
and Thai Buddhist years (+543). Test: a batch per culture in `tds_robust2`. A name of two letters takes the first specific culture (`zh` is zh-CN).

### Measured
In process (`pts.lxl`, 5,000 statements minus none, `LXL_HASH_SEED=1`, two rounds, base = main 6275b6eb): point select 109,187 against 109,168, UPDATE by key 55,289,924 against 55,289,920
(without and with a CHECK: 55,288,138 / 55,288,134), INSERT 55,290,085 / 55,290,083 and 55,287,197 / 55,287,195.
Over the wire (`icount6.sh`, 20,000 point selects x 3, base and branch alternated twice): instructions 170,621 and 170,629 against 170,559 and 170,613, cycles 97,814 and 98,147 against 98,544
and 97,187, L1 i-cache misses 377 and 375 against 404 and 397 (code placement: the instructions are lower, the cycles level), iTLB misses 55 against 33. TPC-H SF1, 22 queries, base and
branch alternated twice, checksums equal on all 22, best of two: total 8,810 ms against 8,769 ms, no query more than 1.4% slower (q13, within its runs' spread).
`replica.py` passes.


## Timestamps that keep their offset (item 9, as built)

`Val.Tsz(instant, offset)`: the instant as `Val.Tstz` (microseconds since 2000 UTC) and the offset east in minutes, added last in `Val` (the other variants keep their tags). The type of a
column that keeps it is `TypeName` kind `K_TSTZ`, OID `OID_TSTZ` and `len` 1 (Oracle's `TIMESTAMP WITH TIME ZONE`) or 2 (T-SQL's `datetimeoffset`: offsets within 14:00, 241 beyond):
`lexdb_sql.isTszType`. The PostgreSQL door's `timestamptz` and Oracle's `TIMESTAMP WITH LOCAL TIME ZONE` stay `len` 0 and `Val.Tstz`; a Tsz seen by the PostgreSQL door is an instant
(`lexdb_sql.text`, `textOut`, the binary send, `pg_typeof` and the OID are `timestamptz`'s). A `kind` of its own was tried first: it cost the point path instructions in `coerce`'s chain, and a
fifth term in `isVarKind` stopped the compiler folding the four into a bit test (+8 instructions a point select, +38 an UPDATE), so:
- **Row form:** a variable place of the uuid's kind (`PK_TSZ` = `PK_UUID`), 10 bytes (the instant, the offset as an int16) where a uuid has 16, told by `varVal` by the length (`tszVal`, off
  the uuid's path); the tagged form has tag 16 (10 bytes). `placeKind` chooses it from `len`. Column leaves (`lexdb_cols`) hold it as bytes; a tagged tag 16 row is "not convertible", as
  an unknown tag was. A fast COPY (`fastCopyPlan`) refuses it. Index keys (`encKeyPart`) are the instant alone: equal instants are one key, a unique index refuses the second.
- **Compare, sort, hash, group, DISTINCT, IN, join:** by instant (`compareTime`, `timeCmpLocal`, `asTstz`, `skIntOf`, `inValKeys` through `encIdxPart`); GROUP BY and DISTINCT show the
  first row's offset, as Oracle and SQL Server do. Batches: a Tsz column's place is not a kind the batch columns hold, so a scan reads rows (`timeKindOf` refuses it for ranges).
- **Coercion (`lexdb_tz.coerceTsz`):** a text is read with the offset it carries (the session's zone where it has none; a named zone or abbreviation as the offset it has at that
  instant); a date or timestamp as local time in the session's zone; a Tstz as its instant seen at the session zone's offset; a Tsz to `timestamp`, `date`, `time` as its own local time.
  `CREATE TABLE AS` and `SELECT INTO` in these doors make the column a Tsz (`lexdb_sql.madeType`); a VALUES list and a derived column typed by OID alone are an instant (the offset lost).
- **Storage compatibility:** a column made before has `len` 0 and stays an instant (its cells decode as the instant, shown at the session zone's offset: `+00:00`); a database made by main's
  binary, closed and killed (WAL replay), opens and reads in the branch's (checked). `ALTER TABLE ... MODIFY (t TIMESTAMP WITH TIME ZONE)` rewrites a column into the new type.
- **Regions:** offsets only. `lexdb_time` has a zone registry by name (`zoneNamed`) but no table of ids, and a region is not kept in a row: `FROM_TZ(..., 'Europe/Berlin')`, `AT TIME ZONE
  'Europe/Berlin'`, a literal `... Europe/Berlin` and a session in a region keep the offset the region had at that instant (`TZR` shows `+01:00`, `TZD` is empty, `EXTRACT(TIMEZONE_REGION)` is
  `UNKNOWN`); Oracle shows `EUROPE/BERLIN`, `CET`, `Europe/Berlin`. (The plan: a negative offset field as an id into a table of region names, the name kept in the row.)


## The third bug slice (2026-11-25)

The bugs the documentation passes listed in KNOWN-ISSUES.md (found on main 55040a20 and 6c2e83f1), on `worktree-agent-a36938384ff7b1bdf` (from main 6c2e83f1, tags `b3-base` and
`b3`). Each was checked on the product before and after (Oracle Free 23.26.3, SQL Server 2022, PostgreSQL 18.6). Tests: `tns_bugs3` (`gen_oracle.py --check tns_bugs3`: 91 answers, 0
differences), `tns_logonzone`, `tds_bugs3` (`gen_mssql.py bugs3`), `tds_selectinto` (the same output against SQL Server with LEXDB_MSSQL), `wire_copyerr`.

### Oracle
- **The client's time zone at logon.** python-oracledb sends `ALTER SESSION SET TIME_ZONE='+05:30'` (its local offset, or ORA_SDTZ) and JDBC the JVM's zone (`Asia/Kolkata`) in AUTH_ALTER_SESSION;
  the session started at +00:00. `lexdb_tns.logonZone` takes TIME_ZONE from it (`lexdb_oraadm.zoneSet`) as ALTER SESSION SET TIME_ZONE would, and makes it LOCAL's zone too (Oracle's `ALTER SESSION SET
  TIME_ZONE = LOCAL` goes back to it). `+00:00` (lib/oracle) sets nothing; a zone lexdb's settings do not know leaves the session at +00:00 (Oracle refuses the logon). The other settings of the
  statement (JDBC's NLS_LANGUAGE, NLS_TERRITORY) are not applied. lib/oracle sends +00:00 only, so the in-process test reads the statement's forms; the logon was checked with python-oracledb (TZ,
  ORA_SDTZ) and ojdbc11 (`-Duser.timezone`).
- **MIN and MAX of equal instants** (with the T-SQL door's): they kept the last equal value (PostgreSQL's numeric_smaller, right for numerics); a Val.Tsz keeps the first one read
  (`lexdb_agg.takes`, row engine and batches, window functions through the row engine). "First" is the scan's order: Oracle's heap is the order rows were inserted, SQL Server's a clustered key's
  or a heap's, lexdb's the primary key's or a keyless table's insertion order; they agree where those agree (a table filled in key order, a keyless one). An index's end is not used for MIN/MAX of
  such a column (`lexdb_plan.minMax`): SQL Server reads an index on the column backwards for MAX alone (the last of equal keys), Oracle does not use it (its index is on SYS_EXTRACT_UTC). Found on the
  way: an index-only scan of such a column gave the instant without its offset (the key holds the instant alone): `lexdb_access.idCode` refuses it.
- **TIMESTAMP WITH LOCAL TIME ZONE on the wire** is type 231 in DBTIMEZONE (UTC), 11 bytes, its column's fractional digits (`lexdb_tns.localTz`: a column of Val.Tstz values, none with an offset);
  it went as type 181 at +00:00. JDBC shows it in its session's zone (`2026-03-15 13:30:00.0 Asia/Kolkata`). Not done: after an ALTER SESSION SET TIME_ZONE in the session, Oracle tells JDBC the new zone
  (a SYNC piggyback, message 23 opcode 5, after the call's reply) and lexdb does not, so JDBC still converts by the logon zone. A `timestamptz` cast in the Oracle door is one of these now (tns_client).
- **A datetime plus an INTERVAL YEAR TO MONTH** whose day is not in the month is ORA-01839 (`lexdb_orafn.monthFits`): DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE, NUMTOYMINTERVAL; ADD_MONTHS
  clamps as before. A TIMESTAMP WITH TIME ZONE moves in UTC, as Oracle's (`TIMESTAMP '2026-01-31 23:00:00 -05:00' + INTERVAL '1' MONTH` is 28 February 23:00 -05:00).
- **OFFSET and LIMIT are names** where no clause follows (`lexdb_parse.oraWordNames`, after the Oracle door's lexing: the token is made a quoted name of its spelling unless a number, a bind, a
  bracket or, for OFFSET, a word and ROW / ROWS follows): column aliases, column names (CREATE TABLE, INSERT, UPDATE), a table's alias, a CTE's name. `LIMIT n` stays lexdb's own.
- **A view that calls a stored function** (a standalone one or a package's): CREATE VIEW was ORA-00904. `lexdb_plcall.viewMarked` keeps the calls after the view's text (`lexdb_sql.PLF_MARK`: the name as
  written, the function's id, its type's OID; resolved as the maker sees them), `lexdb_exec.viewQuery` makes them lexdb_plcall's lookups when the view is read (`lexdb_routine.viewPlf`), and a statement
  that read one and missed values computes them and runs again (`lexdb_tns.runPlan`, `lexdb_plcall.again`). A query that calls functions itself and reads such a view: its own sites and the view's
  misses in the one loop. INSERT, UPDATE, DELETE and CREATE TABLE AS reading such a view are 0A000 (they would have to run twice). Found on the way: a cursor executed again (python-oracledb's
  statement cache) after CREATE OR REPLACE FUNCTION ran the old body (the program is loaded at parse): it is loaded again before a run that calls a function.
- **Annotations and ALTER:** a column annotation in CREATE TABLE AS is ORA-11559 (`colAnnotThenAs`); a column twice in ALTER TABLE ... MODIFY (...) ORA-00957; ALTER INDEX of no index ORA-01418;
  ALTER TABLE of a view (ADD, ANNOTATIONS, RENAME TO: a view is renamed by `RENAME v TO w`, `Stmt.alter` marks that statement) and ALTER VIEW of a table ORA-00942; ALTER VIEW ... RENAME TO
  ORA-00922. ALTER INDEX ... REBUILD [ONLINE], COALESCE, [NO]PARALLEL, [NO]LOGGING and ALTER VIEW ... COMPILE, [NON]EDITIONABLE are accepted and do nothing (as on a valid object). Still
  ORA-03001 (their texts list what is taken): ALTER INDEX ... UNUSABLE (Oracle marks the index), ALTER VIEW ... READ ONLY (Oracle ORA-42310 for a view that is not an editioning view).

### SQL Server
- **The scale of a datetimeoffset result:** SWITCHOFFSET, TODATETIMEOFFSET and AT TIME ZONE give a datetimeoffset of their argument's digits (a datetime's 3), MIN and MAX keep a time type's (and
  as window functions): `lexdb_syscat.timeScale` from `exprScale`. The Oracle door's MIN and MAX of a DATE are a DATE now (type 12; they were a TIMESTAMP), of a TIMESTAMP(3) a TIMESTAMP(3).
  Still seven digits: the text of `CAST(x AS varchar)` (KNOWN-ISSUES' separate entry).
- **SELECT ... INTO's DONE** has CurCmd 0xC2 (SELECT INTO), as SQL Server's: lexdb sent the count with CurCmd 0, which mssql-jdbc does not take as an update count (-1) and sqlcmd does not print.
- **FORMAT's C** without a precision has no decimals for ja-JP, ko-KR, id-ID, es-CO, ja and ko (`NUMCULS`' eleventh field). The 61 cultures' C, C0, C3, N, P, F, D and E of 1234.5, -1234.5 and
  0.125 were compared with SQL Server 2022: these were the only differences.
- **A CHECK's text** in INFORMATION_SCHEMA.CHECK_CONSTRAINTS.CHECK_CLAUSE (it was PostgreSQL's) and sys.check_constraints.definition (half SQL Server's) is `lexdb_tsqldef.checkText`: [names],
  (literals), comparisons and arithmetic without spaces (a + or - operand of a comparison in brackets, the rest by precedence), AND / OR / NOT / IS [NOT] NULL / LIKE in SQL Server's words and brackets,
  IN as ORs in reverse order, BETWEEN as >= AND <=, CASE and functions in lower case. Different still: a CAST (SQL Server writes CONVERT([varchar](5),[a]); lexdb's cast is kept as what it became),
  N'...' (the N is not kept), a system-named constraint's name (`b9_b_check`, SQL Server `CK__b9__b__412EB0B6`).

### PostgreSQL
- **COPY FROM STDIN's errors before CopyInResponse:** an unknown table, column or option and REJECT_LIMIT without ON_ERROR were already answered first (since the entry was written); an option given
  twice (42601), FORCE_NOT_NULL / FORCE_NULL of no column (42703, `lexdb_copyjson.unknownCol`) or of one not copied (42P10, was 42703) and HEADER 2 were not: they asked for the data first, so psql took
  a script's next lines as COPY data. Checked with a raw client against PostgreSQL 18.6 (`wire_copyerr`); a view as COPY's target is refused first by lexdb, after CopyInResponse by PostgreSQL.

### Measured
In process (`pts.lxl`, 20,000 statements, `LXL_HASH_SEED=1`, two rounds, base = main 6c2e83f1 built the same way, trees at paths of equal length): point select 101,816 against 101,816,
UPDATE by key 55,312,600 / 55,312,600 (without a CHECK 55,310,902 / 55,310,902), INSERT 55,312,480 / 55,312,480 (without 55,309,781 / 55,309,781), both rounds. Over the wire (`icount6.sh`, 20,000 point
selects x 3, base and branch alternated twice, a quiet machine): instructions 160,953 and 160,848 against 160,982 and 160,794, cycles 84,604 and 84,367 against 89,629 and 89,136, L1 i-cache misses
376 and 381 against 276 and 275, iTLB misses 84 against 125, branch misses 320 against 383 (code placement: the instructions are level). TPC-H SF1, 22 queries, base and branch alternated
twice, checksums equal on all 22, best of two: total 8,036 ms against 8,076 ms; q6 (+4.4%), q8, q9, q17 (+1.9%) and q12 (+1.5%) slower in time with the server's instructions per query equal
(q6 1,528.2 M against 1,529.5 M, q9 13,492 M against 13,493 M, q12 3,887.5 M against 3,889.1 M; q8 and q17 fewer): placement and the runs' spread (q6's base runs 190.0 and 174.5 ms).
lexdb_exec.lxl 21,492 lines before, 21,499 after.

## The fourth bug slice (2026-11-25)

The bugs the documentation passes listed in KNOWN-ISSUES.md (found on main e7691bd6 and 84ceec7e), on `worktree-agent-a6e32fbef48a2c168` (from main f23d0ebc, tags `b4-base` and `b4`). Each
was checked on the product before and after (Oracle Free 23.26.3, SQL Server 2022, PostgreSQL 18). Tests: `tns_bugs4` (`gen_oracle.py --check tns_bugs4`: 72 answers, 0 differences),
`tns_viewplf`, `tns_graphtext` (texts as Oracle gives them), `tds_bugs4` (`gen_mssql.py bugs4`), `exec_bugs4` (`gen_pg.py bugs4`).

### Oracle
- **A NUMBER foreign key to an identity key.** lexdb keeps NUMBER GENERATED AS IDENTITY and INTEGER as bigints and other NUMBERs as numerics; makeFk refused a key between them (ORA-00932). The
  Oracle door takes an integer and a number either way (`lexdb_fkconv.compatible`; the PostgreSQL door refuses numeric to bigint as PostgreSQL does, `exec_bugs4`), and the lookups compare values:
  a parent found by its primary key's key made from the values (`lexdb_fkconv.pkKey`, no row built: 5 and 5.0 find 5, 5.5 and numbers past bigint's range find nothing), another unique key and the
  parent's side (`refRows`: DELETE, UPDATE, ON DELETE CASCADE / SET NULL, NO ACTION) through `needs` and `fit`; a statement's probes leave such a key to the row's lookup (`fkProbes`, via -2);
  ON UPDATE CASCADE (which lexdb's Oracle door reads and Oracle does not) coerces into the child's type. A pair Oracle refuses (VARCHAR2 or BINARY_DOUBLE to NUMBER) is ORA-02267.
  NUMBER to NUMBER(10) and NUMBER(10) to INTEGER behave as Oracle's (a NUMBER(10) child rounds 1.4 to 1 before the check). pkKey also made an INSERT into a table with a foreign key about 500
  instructions cheaper (no row is built for the lookup).
- **A view over a dropped function, read again.** A PL/SQL unit's CREATE and DROP did not move the catalog's version, so a cursor's kept plan of a view calling the function ran its old call
  (ORA-00904, ORA-00900 for a package's). `lexdb_plsql.putUnit` (CREATE, DROP; not a compile's status flips) bumps it in the unit's own transaction (`lexdb_catalog.CAT_VERSION_KEY`); the
  plan is made again and gives ORA-04063 (ORA-04067 for a package's body). As with every DDL in lexdb, a write transaction open in another session that read the version fails at COMMIT
  (08177). USER_OBJECTS.STATUS of the view is INVALID while a function or package it calls is gone (`lexdb_routine.viewPlfBad`), VALID once it is back (Oracle keeps it INVALID until its next
  use). Not done: in a transaction opened before the DROP, the first read is still ORA-00904 (its snapshot sees the function's source).
- **Units created with compilation errors.** A stored procedure's or function's compile (`Cx.strict`) checks each expression's SQL: one that does not parse is PLS-00103 at the token after it, a
  name that is no variable, column or function PLS-00201 (`checkExpr`), and DML on a missing table `PL/SQL: ORA-00942` at the table's name (`checkTarget`). The unit is stored INVALID with
  USER_ERRORS' rows (the second, "Statement ignored" or "SQL Statement ignored", at the statement's start). SQL's call of an invalid function is ORA-06575 (`sqlError`, `invalidFunction`) and
  CREATE VIEW over one is refused with it (Oracle's; the entry said ORA-04063); the program's invalid units keep their parameters (a call was PLS-00306). Found only when the code runs, as
  before: type errors, a wrong argument count to a built-in, unknown columns of a SELECT INTO; package bodies and anonymous blocks are compiled as before (Oracle compiles a block first:
  ORA-06550 where lexdb gives the run's ORA-00904 or ORA-00942). PLS-00103's text has no "expecting" list. Subprograms declared in a block remain unsupported.
- **The zone UTC by its name.** `ALTER SESSION SET TIME_ZONE = 'UTC'` and a logon in UTC load the region from the zone database (`lexdb_time.REGION_UTC`, the setting `lexdb_tns.zoneSetting`
  gives), so SESSIONTIMEZONE shows UTC (and Etc/UTC, GMT by their names); only a session's default, lexdb's own UTC, shows +00:00. TZR of CURRENT_TIMESTAMP is +00:00 still (regions are kept
  as offsets in values: KNOWN-ISSUES' entry).
- **TO_CHAR of a TIMESTAMP WITH LOCAL TIME ZONE** refuses TZH and TZM (ORA-01821, `TzOut.ltz`); TZR and TZD are taken (+00:00 and NULL, as Oracle). Without a format it is the timestamp's
  (NLS_TIMESTAMP_FORMAT), as Oracle shows one (it was DD-MON-RR, or the TSTZ format with TZR).
- **Property graphs' errors** (lexdb_graph): "is never defined" (the text said "noRows"); a property no label of the variable's kind has is ORA-40983 (ORA-49044 when another label of that kind
  has it); `{m,}` ORA-40984; SOURCE v without KEY and two foreign keys to v's table ORA-42431; ORA-42442 "KEY is not specified for view graph element table V."; ORA-04045 with its cause on a
  second line (a table gone, ORA-00942, before a column, ORA-00904); DROP PROPERTY GRAPH ... CASCADE | PURGE ORA-03049; `GRAPH_TABLE (...) AS` ORA-03048 with the statement's text cut at tokens
  (`oraKwErrToks`); a view over a dropped graph ORA-04063 and INVALID (`viewGraphGone`); USER_PG_LABEL_PROPERTIES.DATA_LENGTH the longest of the graph's properties of the name; a PL/SQL
  variable inside GRAPH_TABLE ORA-49028 when the block compiles. tns_graph's expect lines did not change (they hold numbers only); `--check tns_graph` 159 answers, 0 differences.
  Found on the way: ALTER TABLE ... DROP COLUMN of a column a view reads through GRAPH_TABLE is ORA-02449 in lexdb (Oracle drops it and invalidates the graph and the view).

### SQL Server
- **Reserved words as names.** `lexdb_sql.tsqlReserved` is SQL Server's list, checked against SQL Server 2022 (DISK, DUMP, LOAD, PRECISION and SECURITYAUDIT, on the list, are names there);
  a bare one is 156 as a table's name (`qname`), a column's in CREATE TABLE and an alias after AS (`notTsqlReserved`, error TS156: whether SQL Server says 156 or 102 for a word depends on where it
  is, so lexdb_tsql's mapping of a syntax error does not decide it), and a bare alias is not taken. CREATE TABLE IF (no NOT) is the name IF. Checked in the T-SQL paths only, so the PostgreSQL
  door's parse is unchanged. Different still: a bare reserved alias (`SELECT 1 rule`) is 102 (SQL Server 156); CREATE TABLE HOLDLOCK and INDEX are 156 (SQL Server 1018, a table hint).

### Measured
In process (`pt.lxl`, 20,000 statements, `LXL_HASH_SEED=1`, two rounds, base = main f23d0ebc built the same way, trees at paths of equal length), equal in both rounds: point select 30,626.2,
INSERT 216,528.7, UPDATE by key 199,616.9, as text 105,091.3 / 238,008.8 / 224,547.0; in a transaction block INSERT 49,647.0, UPDATE 83,776.3. An INSERT into a table with a foreign key
(the same with `v int not null references t (id)`): 245,023.3 against 244,524.2 (text 266,342.0 / 265,833.0, block 75,338.5 / 74,829.5): pkKey builds no row. Over the wire (`icount6.sh`,
20,000 point selects x 3, base and branch alternated twice): instructions 160,774 and 160,971 against 155,517 and 155,590, cycles 88,216 and 88,208 against 86,258 and 84,509, L1 i-cache misses 567
and 559 against 314 and 315 (the server's hash seed is not fixed there). TPC-H SF1, 22 queries, base and branch alternated twice (base's first run cold, so best of two): checksums equal on all 22,
total 8,082 ms against 7,958 ms; q1 (+2.9%), q6 (+2.2%) slower in time with fewer server instructions (q1 16,637 M against 16,244 M, q6 1,524.6 M against 1,484.9 M; `iq.sh`). Suite 392 passed;
replica.py passed. lexdb_exec.lxl 21,558 lines before, 21,564 after.

## The fifth bug slice (2026-11-25)

The bugs the documentation passes listed in KNOWN-ISSUES.md, on `worktree-agent-aada84ce95b9c4421` (from main 0400f272, tags `b5-base` and `b5`). Each was checked on the product
before and after (Oracle Free 23.26.3, SQL Server 2022, PostgreSQL 18.6). Tests: `tns_bugs5` (`gen_oracle.py --check tns_bugs5`: 44 answers, 0 differences), `tns_assertpriv`
(`--check`, scenario: 11 answers, 0 differences), `tns_plfdrop` (two sessions; Oracle's answers by python-oracledb), `tds_bugs5` (`gen_mssql.py bugs5`), `tds_assertpriv` (lexdb's own: the
T-SQL and PostgreSQL doors' assertions), `exec_bugs5` (`gen_pg.py bugs5`).

### Every door: DROP COLUMN of a table views read (item 1)
- lexdb refused the drop of any column of a table a view reads (2BP01, ORA-02449, 50000). The drop is done now and checked afterwards in the statement (`lexdb_viewdep.afterAlter`, from
  the end of `alterTable`): each view that reads the table is planned on its own (`lexdb_exec.viewCols`, as reading it plans it: its rename map, its owner's rights); one whose query fails
  with a name gone (42703, 42P01, a graph's ORA-04045 / ORA-42421, a view under it with errors) or gives fewer columns than the view has (a `SELECT *` over the table: a view's columns are
  those of its CREATE) uses the column. PostgreSQL's door refuses then (2BP01, PostgreSQL's DETAIL lines and HINT), and its CASCADE drops those views (and the views over them) and no
  others; SQL Server's door refuses only for a view made WITH SCHEMABINDING (5074); Oracle's door never refuses. A refusal undoes the statement (its door's savepoint).
- Reading such a view: Oracle's ORA-04063 (now also through GRAPH_TABLE, which gave the graph's ORA-04045), SQL Server's 207 for a name, 4502 for a `SELECT *` short of columns
  (`fewerErr`). USER_OBJECTS.STATUS of an Oracle view whose query does not plan now is INVALID, and USER_ERRORS has its error (TYPE VIEW, LINE 0, POSITION 0, the text with Oracle's line
  feed: ORA-00904 for the column or the function gone, ORA-04063 for a view under it, ORA-04045 and its cause for a graph; `viewErrs`, `CatView.verrs`, computed only for the *_OBJECTS and
  *_ERRORS views). Oracle keeps a view INVALID from the DDL until its next use; lexdb's says what the view's query does now (VALID as soon as the column is back).
- T-SQL's CREATE VIEW reads WITH SCHEMABINDING (kept: `lexdb_sql.SB_MARK` after the query, `viewBound`; `sys.sql_modules.is_schema_bound`), VIEW_METADATA and ENCRYPTION (195 for another
  option, 1054 for `SELECT *` in a schema-bound view). Not done: SQL Server's 4512 (one-part names) and 4513 (a schema-bound view over one that is not), ALTER COLUMN of a column a
  schema-bound view reads (5074), DROP TABLE of its table (3729: lexdb refuses DROP TABLE under any view, in every door). A `SELECT *` view after a column of it was dropped and another
  added reads the table's columns by position (SQL Server: 4502 until sp_refreshview; Oracle: by name).

### SQL Server (items 2, 6, 9)
- **An inline INDEX in CREATE TABLE** (`INDEX ix [UNIQUE] [CLUSTERED | NONCLUSTERED] (cols) [INCLUDE] [WHERE]` among the elements, `INDEX ix ...` after a column) is a CREATE INDEX kept in
  the statement's `inner` and made with the table in its statement (`Parser.inlineIndex`; a CLUSTERED one makes an unsaid primary key NONCLUSTERED); CREATE INDEX of a missing column is 1911.
- **DELETE, UPDATE and INSERT TOP (n) [PERCENT]**: PERCENT takes n percent of the rows found, rounded up (`lexdb_plan.topOf`; 1031 past 100); INSERT TOP (n) [PERCENT] [INTO] limits its
  query (read as a derived table when it has its own TOP, ORDER BY, OFFSET or a set operation, `insertTop`) or cuts its VALUES. INSERT ... SELECT TOP n PERCENT inserted every row: the rows
  are now made whole first (the existing PERCENT code then cuts them).
- **INFORMATION_SCHEMA in the T-SQL door** shows dbo where the schema is lexdb's public (`lexdb_syscat.dboRows`: every *_SCHEMA column and SCHEMA_NAME, SCHEMATA's owner), as sys.schemas and
  SCHEMA_NAME() did; the PostgreSQL door keeps public. Still: ROUTINES and PARAMETERS have no T-SQL procedures and functions, CONSTRAINT_COLUMN_USAGE has no foreign key's columns,
  VIEW_TABLE_USAGE does not exist.
- **Parse errors**: a parenthesized operand of UNION / INTERSECT / EXCEPT with its own ORDER BY is 156 (`armOrder`); a reserved word where a statement would start (`SELECT 1 rule`) is 156,
  decided on the error path only (`Parser.statement`'s `startErr`); CREATE TABLE HOLDLOCK / INDEX and a table followed by HOLDLOCK are 1018 (`tableHintErr`). 1018, 1031 and 1054 have
  SQL Server's severity 15.

### Oracle (items 3, 4, 7, 8, 10, 11)
- **An assertion's check runs with its owner's rights** (also in the T-SQL and PostgreSQL doors): `lexdb_assert.asOwner` reads the check's query as a derived table under `Stmt.runAs`
  (the assertion's schema, or the user that made it), as a view's query is read: a writer with INSERT, UPDATE or DELETE and no SELECT is checked (ORA-08601, 547, 23514), not refused (ORA-41900,
  229, 42501); its own WHERE and SELECT still need the privilege. Oracle refuses an assertion over another schema's table even with SELECT and REFERENCES on it (ORA-01031), so the owner
  reads its own tables.
- **A stored function's column name**: a call with constant arguments, made before the query and written as its value, keeps the call as written in a comment, `(/*#plf okf(1)*/2)`
  (`lexdb_sql.PLF_LABEL`), which `oraLabel` reads back: OKF(1), 5+OKF(3), APP.OKF(2). A call of a quoted mixed-case function (`"MixF"(2)`) is still ORA-00900.
- **A SQL statement of a stored unit that does not parse** is a compile error: ORA-00936 (ORA-00907 with a parenthesis left open) at the token the parser stopped at
  (`lexdb_parse.oraSyntaxAt`: its text and how many of it come before), then "SQL Statement ignored" at its start; the unit is INVALID with USER_ERRORS' rows (`Cx.checkSyntax`, stored units
  only). Oracle's exact number can differ from 936 for other syntax errors; a `SELECT count(* INTO ...` is still PLS-00428 (lexdb's INTO test) where Oracle gives ORA-00907.
- **UPDATE of a GENERATED ALWAYS identity column** is ORA-32796, `SET id = DEFAULT` and MERGE's UPDATE too; INSERT stays ORA-32795.
- **Assertions**: a quoted lower-case name is kept ("xq"); SET CONSTRAINT[S] of a name that is not there is ORA-02448, of a non-deferrable assertion ORA-08687 for IMMEDIATE too;
  USER_ASSERTIONS.INVALID is INVALID once ALTER TABLE added, dropped, retyped or renamed a column of a table the assertion reads (Oracle's, checked: CREATE INDEX, COMMENT, ADD CONSTRAINT,
  TRUNCATE leave it; DISABLE / ENABLE do not clear it), kept in its catalog row (`Assertion.invalid`, `columnsChanged`, from `afterAlter`), and it is still checked. Not done: under
  NOVALIDATE, a DELETE or UPDATE of a table under the inner NOT EXISTS still runs the whole query (Oracle checks only the rows related to those written): it needs the old rows' join-key values
  (the deleted rows are gone when the check runs) to restrict the outer instance (`plan.keys`), captured by the write paths or read at the statement's start.
- **A view over a function dropped by another session while a transaction that wrote is open** gives ORA-04063 at once: whether a unit is there is read from the transaction's snapshot and
  the latest catalog (`lexdb_routine.srcValid`; Oracle's DDL is not transactional). It gave ORA-00904, then rows with NULLs, until the transaction ended.
- Quoted lower-case table names are still folded (`create table "qt"` is listed as QT and is the same table as qt): the Oracle lexer drops a quoted name's spelling when it is lower case.

### Not done: nested subprograms (item 5)
A procedure or function declared in a block (a stored unit's declare section, a package member's) is still PLS-00103 "not supported". What it needs, from how packages work: the nested
units compiled as members of the unit that declares them (`pkgMember`'s path: their own slot ranges in the enclosing unit's slot space, signatures in `cx.sigs` under a name only the
enclosing unit resolves, overloads by argument count as members'), returned with the unit (as `compilePackage` returns its members) and kept in the program; a call copies the slots outside
the callee's own range from the caller's frame into the callee's and back after it (as `pkgLoad` / `pkgSave` copy a package's variables), which gives the outer unit's variables, recursion
and calls among nested units; USER_ERRORS positions for errors inside them. About a day with its tests against Oracle.

### Measured
In process (`pt.lxl`, 20,000 statements, `LXL_HASH_SEED=1`, two rounds, base = main 0400f272 built the same way, trees at paths of equal length), equal in both rounds: point select
31,336.5, INSERT 217,229.9, UPDATE by key 200,302.6, as text 105,736.3 / 238,692.2 / 225,189.3; in a transaction block INSERT 50,325.9, UPDATE 84,459.0 against 84,459.1 (the 0.1 flips
between runs). A first build was 4.0 instructions a text INSERT more (INSERT TOP's test ahead of INTO's): moved into the T-SQL branch. Over the wire (`icount6.sh`, 20,000 point selects x 3,
base and branch alternated twice): instructions 156,075 and 156,077 against 156,250 and 156,173, cycles 84,973 and 85,429 against 85,511 and 84,794, L1 i-cache misses 293 and 290 against 414
and 410 (the server's hash seed is not fixed there). TPC-H SF1, 22 queries, base and branch alternated twice: checksums equal on all 22, total 7,586 ms against 7,532 ms; q21 (+2.0%) and q22
(+1.9%) slower in time with the same server instructions (q21 6,390.5 M against 6,394.6 M, q22 464.86 M against 464.87 M; `iq.sh`). Suite 398 passed; replica.py passed. lexdb_exec.lxl
22,175 lines before, 22,186 after (viewCols and viewErr; viewPlanned's body moved to lexdb_viewdep).

## The sixth bug slice (2026-11-25)

The bugs the documentation passes listed in KNOWN-ISSUES.md, on `worktree-agent-a8da2f176e663b6fe` (from main b7c7b37f, tags `b6-base` and `b6`). Each was checked on the product before
and after (Oracle Free 23.26.3, SQL Server 2022, PostgreSQL 18). Tests: `tns_bugs6` (`gen_oracle.py --check tns_bugs6`), `tds_bugs6` (`gen_mssql.py bugs6`), `exec_bugs6`
(`gen_pg.py bugs6`).

### Oracle: quoted names are exact (item 1)
- lexdb's keys are folded (L6): every door's lexer lowered a name, quoted or not, and kept its spelling beside it, so `"qt"` and `QT` were one table and `mixt` found `"MixT"`.
  The Oracle door's lexer now gives a quoted name that has a lower-case letter a key of its own (`lexdb_sql.oraQuoted`): the name in lower case, ORA_UPC (0x1c) after each
  letter that was upper case, ORA_EXACT (0x1d) at the end (`"MixT"` is `m^ixt^$`, `"qt"` is `qt$`). No fold reaches such a key and every fold leaves it as it is, so all
  the code that lowers names (column decoders, stored expressions read again in lexdb's dialect, catalog lookups) keeps it, and nothing else changed: a bare name and a quoted
  one without a lower-case letter keep their fold (`T`, `"T"` and `t` are the key `t`, which the PostgreSQL door calls `t` and the T-SQL door `t` in any case, as before).
  `lexdb_sql.oraShown` gives the name back (an exact key as written, a folded one in upper case, a name generated from an exact one, `"Emp"`'s `Emp_PKEY`, its exact part as
  written): the Oracle door's dictionary (`lexdb_oracat.oraUp`, `lexdb_graph` and `lexdb_assert`'s `shownOf`), its error texts (`lexdb_oratext.quotedName`), the views' ORA-04063
  and PL/SQL's lookup of a function SQL calls (`findFunction`). A column's catalog row stores an exact key itself (`colStored`; `spelledCol` reads it back with its spelling).
  Tables, views, columns, indexes, constraints, sequences, PL/SQL units, assertions, graphs, the dictionary views' columns (`"table_name"` is ORA-00904) and GRANT ... ON's
  object (`lexdb_tns.quotedObject`) all follow. `"MixF"(2)`, a call of a quoted name, is read as a call (`primary`; a stored function's
  call from SQL and PL/SQL's %TYPE and %ROWTYPE quote the names they write, `callFunction`, `qn`); the SQL GRAPH_TABLE writes names as the Oracle door reads them
  (`lexdb_graph.q`); an expression's label upper-cases quoted names too (`"ID"+1`, as Oracle 23.26). 
- **Databases made before keep folding.** Exact names are a database's from its making: `lexdb_exec.bootstrap` writes the sequences' tree's
  number with a leading 0 in a store it makes (a mark that adds no key and no page: a key of its own, in the catalog or the sequences' tree,
  moved UPDATE by key's instructions by 2 to 18 through the trees' pages), and sets `lexdb_sql.setOraExact` from it at every open (a process
  serves one store). A store made before has no mark, and its Oracle door folds quoted names as before: `"MixT"`, `mixt` and `MIXT` are the
  table made as `"MixT"`, `"lowt"` and `LOWT` the one made as `"lowt"` (listed `LOWT`), `"Col"` and `col` its column, `create table "mixt"`
  ORA-00955; an application that quotes its names goes on working (checked: a store made by main b7c7b37f's binary answers the same through
  this one, `"MixF"(2)` better). The alternatives were not sound: a migration at open cannot tell a name made quoted in the Oracle door from a
  T-SQL spelling (`"MixT"` and T-SQL's `MixT` are both the key `mixt` with the spelling `MixT`, and `"lowt"` has none, as `LOWT`); a lookup
  that tries the folded key when an exact one finds nothing would have to be in every name lookup (relations, columns in the binder and the
  planner, sequences, indexes, constraints, graphs, assertions, grants), would let `"table_name"` and `"qt"` find `TABLE_NAME` and `QT` where
  Oracle gives ORA-00904 / ORA-00942, and with an old `mixt` and a new `"mixt"` in one database would make what a spelling finds depend on what
  is there. So a database has one rule for good: an old one never has an exact key beside a folded one, and a new one never has an old
  one. An old database moves to exact names only by being loaded into a new one (Data Pump-style export and import); nothing switches it in
  place. Test `tns_oldnames` (a store made, its mark taken out, opened again).
- The other doors cannot name an exact key (their lexers fold quoted names): an Oracle table `"qt"` is reached from the Oracle door only; a T-SQL table `Orders` is `ORDERS`
  to the Oracle door (found by `orders` or `"ORDERS"`) and is still shown as `Orders` there (its spelling). An index or constraint name generated from an exact table name
  shows the key's bytes in the PostgreSQL and T-SQL doors.
- Synonyms: lexdb has no CREATE SYNONYM (ORA-03001), so there is nothing to make exact.

### SQL Server: index names per table (item 2)
- `lexdb_ixname`: a T-SQL CREATE INDEX whose name another table's index (or a relation) has in the schema keeps the index under the name, IX_OF (0x0e) and its table's name;
  the T-SQL door shows the name as written (`lexdb_sql.ixShown`: sys.indexes, and so INDEXPROPERTY) and finds it through its table (`DROP INDEX ix ON t`, and now `DROP INDEX
  t.ix` and `schema.t.ix`, which were 50000). The same name on the same table is 1913; in CREATE TABLE a repeated inline name is 8168 and two CLUSTERED indexes (or a
  CLUSTERED primary key and a CLUSTERED index) 8112, as SQL Server's. PostgreSQL's and Oracle's doors keep names per schema and see the kept name. `sp_helpindex` is still 2812.

### Oracle: nested subprograms (item 3)
- A procedure or function declared in a unit's declarations (a stored unit's, a package member's, an anonymous block's, a nested block's) is compiled as a package's member is
  (`Cx.nestedUnit`): its parameters and variables get slots of its own (`PUnit.nfrom`..`nto`) in the slot space of the unit that declares it; it is a unit of the program
  (`subs`, moved beside its unit in `ensureProg`; an anonymous block's live in `Ip.subs` for the block's run) with a scope id (`PUnit.nest`, the fourth name of `Sig.canon`), so
  that no name from outside reaches it. A bare name resolves to the innermost nested subprogram in scope first (`Cx.nested`, trimmed at the end of the declaring block);
  forward declarations take the definition's body; recursion and calls between nested subprograms work. On a call (`callUnit`) the slots outside the callee's own are
  copied from the caller's frame into the callee's and back after it (`nestCopy`), which gives it the enclosing units' variables (and the package's). Errors inside one are
  compile errors of the unit (USER_ERRORS at their own lines). Not done: overloading by arguments (one subprogram a name in a scope), and the call of a nested function from
  SQL inside the unit (Oracle: PLS-00231; lexdb: ORA-00904 when it runs).

### Every door: DROP TABLE under a view (item 4)
- `lexdb_viewdep.dropTable`: PostgreSQL's door refuses it as before (2BP01), now with PostgreSQL's DETAIL (each view and what it depends on) and HINT, and CASCADE drops the
  views; SQL Server's door drops the table unless a view made WITH SCHEMABINDING reads it (3729), a view over it fails with 208 when read; Oracle's door drops it, a view over
  it is INVALID, reading it ORA-04063 and USER_ERRORS has ORA-00942. Such a view reads the table again once one of the name is made (lexdb keeps a view's text): in Oracle it
  is VALID at once (Oracle: at its next use).

### SQL Server: INFORMATION_SCHEMA and sp_refreshview (item 5)
- `lexdb_syscat.infoRows`: the T-SQL door's SCHEMATA lists SQL Server's schemas (dbo, guest, INFORMATION_SCHEMA, sys, the db_* roles' and those made, owned by dbo, character set
  iso_1) and not pg_catalog or information_schema; ROUTINES and PARAMETERS list the T-SQL procedures and functions (types as SQL Server's, a scalar function's result as
  parameter 0, OUTPUT as INOUT, the definition, READS or MODIFIES); CONSTRAINT_COLUMN_USAGE gives a foreign key's own columns; VIEW_TABLE_USAGE and VIEW_COLUMN_USAGE exist (in
  the PostgreSQL door too, as PostgreSQL's; `lexdb_viewdep.usageRows`): a view's relations are its kept dependencies, the columns those its text names (by name, qualified by the table or an alias, or
  all of them for `*`).
- `sp_refreshview 'v'` makes the view again from its kept text (a CREATE OR ALTER VIEW: `lexdb_viewdep.refreshStmt`), so a `SELECT *` view takes its table's columns as they
  are now; 15165 for a name that is no view. SQL Server keeps giving 4502 for a `SELECT *` view once a read failed until sp_refreshview; lexdb does not follow that (a read's
  failure does not change the view): it reads by position as before, and sp_refreshview brings the new columns.

### SQL Server: smaller ones (item 6)
- `INSERT TOP (n) ... SELECT ... ORDER BY`: SQL Server ignores the ORDER BY (its documentation: the rows TOP takes for INSERT are in no order; checked with three ORDER BYs
  and a WHERE, it took the first rows of its scan each time). Its choice is undefined, so lexdb keeps honouring the ORDER BY.
- `WITH CHECK OPTION` before AS is 102 (`Incorrect syntax near 'with'.`); 1054's state is 6 (`lexdb_tsql.sqlState`, in the TDS error and ERROR_STATE()).
- A schema-bound view: a FROM item not in two parts is 4512 (`Parser.boundNames`), a view over a view that is not schema-bound 4513 (`lexdb_viewdep.boundOver`), over a
  function 4513 (`lexdb_tsqlparse`: the function is not schema-bound); ALTER COLUMN of a column such a view names is 5074 (`afterAlter`).
- Not done: 4502's text names the view without its schema when the query wrote `dbo.v` (lexdb's statement does not keep the name as written).

### Oracle: smaller ones (item 7)
- A view over a graph after DROP COLUMN and the column back: kept VALID at once (lexdb's view says what its query does now; Oracle's stays INVALID with ORA-04063 on every
  read until ALTER VIEW ... COMPILE, which only adds a step that changes nothing in the data).
- A SELECT with a parenthesis left open before INTO in a block or a stored unit: ORA-00907 at the INTO, then "SQL Statement ignored" at the statement (USER_ERRORS of a
  stored unit), as Oracle's, not PLS-00428.
- Not done: under NOVALIDATE, a DELETE or UPDATE of the inner table of a NOT EXISTS still runs the whole query. Restricting it needs the old rows' join-key values; the
  transaction's writes keep only a deleted row's key (OP_DEL), and the old row is not readable through the transaction (its reads overlay its own writes), so either the
  write paths note the join-key values of the rows they delete or change (a per-row cost on UPDATE and DELETE of asserted tables only: their refBy marks them) or the store
  offers a read of the snapshot below the transaction's own writes.

### Measured
In process (`pt.lxl`, 20,000 statements, `LXL_HASH_SEED=1`, two rounds, base = main b7c7b37f built the same way, trees at paths of equal length), equal in both rounds: point select
30,934.2, INSERT 177,941.6, UPDATE by key 199,908.2 (199,908.3 in round 2, both), as text 105,360.3 / 197,960.2 / 224,376.3 (the text select and update flip by 0.1 between
base and branch); in a transaction block INSERT 50,155.0, UPDATE 84,068.2. Over the wire (`icount6.sh`, 20,000 point selects x 3, base and branch alternated twice):
instructions 155,389 and 155,349 against 155,264 and 155,200, cycles 88,938 and 89,622 against 82,015 and 81,765, L1 i-cache misses 566 and 562 against 307 and 314 (the server's
hash seed is not fixed there). TPC-H SF1, 22 queries, base and branch alternated twice: checksums equal on all 22, total 7,526 ms against 7,593 ms; q9 (+2.3%), q13 (+2.2%), q14
(+1.9%), q16 (+2.3%), q17 (+2.6 ms) and q19 (+4.5%) slower in time with the same server instructions (`iq.sh`: q9 13,093.4 M against 13,097.0 M, q13 4,477.7 M / 4,478.5 M,
q14 983.6 M / 983.7 M, q16 1,902.3 M / 1,908.8 M, q17 119.89 M / 119.88 M, q19 154.14 M / 154.15 M). An earlier pair of runs (a branch build without the last three edits,
none of them on the PostgreSQL door's path) gave 7,744 ms against 7,634 ms, its slower queries (q2, q7, q15, q21) with the same instructions too. Suite 401 passed; replica.py
passed. lexdb_exec.lxl 22,186 lines before, 22,191 after (the calls of lexdb_viewdep, lexdb_ixname and lexdb_syscat.infoRows).
