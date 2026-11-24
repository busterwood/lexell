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
  **MERGE** has the same fault (an UPDATE clause's correlated subquery) and is not done (see Plans).
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

### Package variables and constants outside the package (item 10)
State is `ip.pkgs[i].vals[slot]` (lexdb_plsql `PkgInst`); the specification's variables are slots of the package unit, not named for
callers. Plan: (1) the U_PKG unit keeps a list of its public variables (name, slot, constant, type) from the specification's declarations
(`compilePackage`: `specDecls`); `SigEntry`-like entries make them visible to later compiles; (2) in PL/SQL an expression's text is rendered
to SQL with its variables replaced (`render`): a `pkg.var` reads like a hoisted call (`hoistCall`) of a synthetic zero-argument
function that loads the package state (`pkgState`) and returns the slot, an assignment `pkg.var := e` to a K_ASSIGN of the slot of the
package's state (write back in `ip.pkgs`; ORA-06550/PLS-00363 for a constant); (3) in SQL `lexdb_plcall.block` takes an
`Expr.Col("pkg.var")` whose first part is no FROM item as a call of that function (the same change makes `SELECT f FROM dual`, a function without brackets,
work: KNOWN-ISSUES); (4) `pkgSave`/`pkgLoad` already move slots between member frames and the instance: a read from outside while a member runs reads
the instance (stale until the member's next save: Oracle's package state is one memory). Tests: tns_plsql's package cases plus a new set
(`pay.g_count` in SQL and PL/SQL, constants, a boolean, a date, the state per session, a second session not seeing the first's, ORA-06550 for
a name that is none, assignment from a block, `RESET` by recompiling the package).

### PostgreSQL's bare-literal overflow and recursive CTEs (item 13)
`SELECT 2147483647 + 1` is 22003 in PostgreSQL (two int4 literals) and 2147483648 in lexdb: constant arithmetic of integer literals is bigint.
The Oracle door's NUMBER literals must stay unlimited, the point path (`id = 5`, `values (1, 2)`) must not slow: the fix belongs in the PostgreSQL
and T-SQL doors' parse of a binary operator whose both operands are integer literals (fold with int4 range checks, int8 only when a literal
is itself past int4), not in `binOp`. A recursive CTE under LIMIT with WHERE, a join or an outer block (lexdb.md 9.139 records the plain
case): the LIMIT is pushed into the recursion only when nothing filters the CTE's rows after it; the plan is to push it through a stop
flag the consumer sets when its own LIMIT is met (`lexdb_recrun` produces row by row), so that a filter, join or outer aggregate on top
of the CTE sees rows until the consumer is satisfied.

### MERGE's subqueries (item 6, the rest)
`merge` evaluates a WHEN clause's expressions per source row between writes, as UPDATE did. The fix is UPDATE's: for a MERGE with
subqueries in its clauses, decide each row's clause and evaluate its values and conditions first (the writes of earlier rows do not change which
clause fires: that is decided by the joined row and conditions), then apply the writes in order, stopping at the first error as
`updateB` does. `touched` (ORA-30926 / 21000) is computed in the first pass.
