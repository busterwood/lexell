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
