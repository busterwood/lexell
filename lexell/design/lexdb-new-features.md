# lexdb: the newest releases' SQL against the three doors

Status: audit, 2026-11-22, on main `30a02b82` (after recursion in the doors, lexdb-dialect-gaps.md section 10). No
lexdb code was changed; the branch adds this note and one test (`tds_distinct`, section 5). The order at the end
(section 6) is a proposal; the choices in it are the user's. Section 7 (later, commit 91781b58): the rows classed wrong
answer and wrong error fixed, marked *works* with the commit. Section 8 (later, commit ec3c5c17): the cheap missing statement
forms of 6.1 (items 1, 2's Oracle GROUP BY ALL, 4 and 5), marked *works* with the commit. Section 9 (later, commits f8c07339
and 271ca36e): 6.1's items 6 and 7, the missing scalar functions and aggregates, marked *works* with the commit.

**What was audited.** The SQL a user of each product's newest release would reach for: PostgreSQL 19 (and 18, and
older features met on the way), SQL Server 2025 (compatibility level 170) with 2022's additions, Oracle AI Database 26ai
(23.26) with 23ai's. Each feature was first run on the real product, then through lexdb's matching door.

**How it was checked.**
- PostgreSQL 19.0 (Debian 19.0-1.pgdg13+1): podman container `lxl-pg19` from `docker.io/library/postgres:19`, port
  127.0.0.1:54319, trust auth. psql against it and against lexdb's PostgreSQL door.
- SQL Server 2025 RTM-CU10-GDR (17.0.5045.3, Enterprise Developer), database at compatibility level 170: podman
  container `lxl-mssql25` from `mcr.microsoft.com/mssql/server:2025-latest`, port 127.0.0.1:14331, the sa password of
  `lxl-mssql`. As the image's default user `mssql` it dies at startup on this kernel (`[AppLoader] Failed to load LSA:
  0xc0070102`, the failure `tools/mssql_container.sh` records); **run as root (`-u 0 --hostname mssql25`) it starts**.
  SQL Server 2022 (16.0.4315.2, `lxl-mssql`) for the 2022 features and the test's answers.
- Oracle AI Database 26ai Free 23.26.3.0.0: `lxl-oracle` (python-oracledb thin, account APP).
- lexdb: main `30a02b82` built `-O` (`~/tpch-w/bind/os/lexdb-audit-O`), one server with the three doors, a fresh data
  directory for each comparison. The T-SQL batches went through a small client over `lib/sqlserver` (the one the
  `tds_*` tests use), the Oracle statements through python-oracledb, as `gen_oracle.py --check` does.

**Classes.** *works*: the product's rows, types and error (by number); *wrong answer*: rows, column names or types
differ; *wrong error*: lexdb accepts what the product refuses, or refuses with another error; *missing*: lexdb has no
such syntax or function. **Sizes**: S under half a day, M about a day, L more (why, in the row). *Other doors*: the
dialects that have the feature natively, each in its own spelling (lexdb-dialect-gaps.md 2a: a feature goes into every
dialect that has it; a dialect without it does not get another's spelling).

**Known gaps, cited not counted.** lexdb-gaps.md 2.1/2.2 already list json/jsonb (waiting on the user, 9.85), domains,
`array_sort`, and that lexdb's regular expressions are RE2's (no back-references or lookahead). lexdb-dialect-gaps.md
section 10 "Left" lists the lower-case names of a CTE's or derived table's column list in the T-SQL and Oracle doors;
the Oracle `VALUES` row below is that fault.

**Not in the releases (dropped from the brief's list).** PostgreSQL 19.0 has no `GROUP BY ALL`, no `UPDATE/DELETE ...
FOR PORTION OF`, no SQL/PGQ (`CREATE PROPERTY GRAPH`, `GRAPH_TABLE`): each is a syntax error on 19.0 and none is in
the release notes (they were committed during the cycle and taken out). `GROUP BY ALL` and `GRAPH_TABLE` are in Oracle
26ai (section 3). Oracle 26ai has no `IS [NOT] DISTINCT FROM` (ORA-00908 on 23.26.3).

## 1. PostgreSQL 19 and 18

Checked on 19.0 unless marked. "P18" etc.: the release that added it.

| # | Feature | PostgreSQL's behaviour | lexdb (PostgreSQL door) | Class | Size | Other doors natively | Modules |
|---|---|---|---|---|---|---|---|
| P1 | `INSERT ... ON CONFLICT (target) DO SELECT [FOR UPDATE\|NO KEY UPDATE\|SHARE\|KEY SHARE] [WHERE cond] RETURNING ...` (P19) | the conflicting row is returned as it is (optionally locked), a new row as inserted; WHERE filters the conflicting ones out of RETURNING (`INSERT 0 0`); RETURNING required (42601 "requires a RETURNING clause"), so is a conflict target (42601 "requires inference specification"); `old.*`/`new.*` both the existing row | 42601 syntax error at `select` | missing | M: a third conflict action beside NOTHING/UPDATE; the row lock and WHERE reuse ON CONFLICT DO UPDATE's (`upsertOf`, `conflictOf`, in lexdb_exec: new code in its own module) | none (T-SQL and Oracle have MERGE only) | lexdb_parse `onConflict`, the upsert path |
| P2 | `RETURNING old.x, new.x, old.*, new.*` and `RETURNING WITH (OLD AS o, NEW AS n)` for INSERT, UPDATE, DELETE, ON CONFLICT DO UPDATE, MERGE (P18) | INSERT's old NULL, DELETE's new NULL; MERGE RETURNING with `merge_action()` and old/new | as PostgreSQL 18: `old.c`, `new.c`, `old.*`, `new.*`, `WITH (OLD AS o, NEW AS n)` in INSERT, ON CONFLICT DO UPDATE (old the row there), UPDATE (... FROM), DELETE (... USING), MERGE per action; a default name a table has is the table's, one given in WITH 42712; OLD/NEW twice 42601 (was 42P01). Not: the whole row (`RETURNING old`, a composite), old/new in a subquery of RETURNING (8.3) | works (ec3c5c17) | S | Oracle 23ai `RETURNING OLD c, NEW c INTO` (O19, works); T-SQL has OUTPUT (works) | new lexdb_oldnew, lexdb_parse `returning`, lexdb_exec `retOf` |
| P3 | `PRIMARY KEY / UNIQUE (k, r WITHOUT OVERLAPS)`, `FOREIGN KEY (k, PERIOD r) REFERENCES t (k, PERIOD r)` (P18) | needs a range column (and btree_gist for scalar parts); 23P01 for an overlap, 23503 for a range the referenced rows do not cover | 42601 at `without`; range types do not exist (`daterange`: 42704) | missing | L: range types first, then the constraint (section 6.3) | none (Oracle's PERIOD FOR has no such key; SQL Server's temporal tables are system-versioned) | new lexdb_range, catalog, write path |
| P4 | `WAIT FOR LSN 'lsn' [WITH (MODE 'standby_replay\|standby_write\|standby_flush\|primary_flush', TIMEOUT '...', NO_THROW)]` (P19) | on a primary: `recovery is not in progress` (55000) for the standby modes | as PostgreSQL 19 (lexdb.md 9.137): the options, statuses and errors, checked against a 19.0 primary and standby; lexdb's LSN is the batch number; `pg_current_wal_lsn`, `pg_last_wal_replay_lsn`, `pg_last_wal_receive_lsn`, `pg_is_in_recovery` added (was 42601 at `wait`) | works (replica branch) | M, with the replica work (the user's order) | none (SQL Server and Oracle have no statement for it) | lexdb_standby, lexdb_parse, lexdb_store (Follower.waitApplied) |
| P5 | `lag/lead/first_value/last_value/nth_value(...) IGNORE NULLS \| RESPECT NULLS OVER (...)` (P19) | NULLs skipped in the frame (lag/lead: in the offset) | 42601 at `nulls` | missing | M: the frame walk in both the row path and the pipeline window (lexdb_window) | SQL Server 2022 (FIRST_VALUE, LAST_VALUE, LAG, LEAD: S15), Oracle (`f(x IGNORE NULLS)` and `f(x) IGNORE NULLS`: O25) | lexdb_parse, lexdb_window |
| P6 | `CHECK (...) NOT ENFORCED`, `REFERENCES ... NOT ENFORCED` (P18); `ALTER TABLE ... ALTER CONSTRAINT c [NOT] ENFORCED` for CHECK (P19) | rows not checked while not enforced; ENFORCED rechecks (23514 "is violated by some row") | 42601 at `not`; ALTER CONSTRAINT: lexdb's ALTER COLUMN message | missing | M: a flag on the constraint, the write path skipping it, ALTER rechecking | Oracle `CHECK (...) DISABLE`, `ENABLE NOVALIDATE` (O26); SQL Server `WITH NOCHECK`, `NOCHECK CONSTRAINT` (S22) | lexdb_parse `checkTail`, lexdb_catalog, the write path |
| P7 | `CONSTRAINT n NOT NULL col` as a table constraint (P18) | a named NOT NULL, kept in pg_constraint (contype `n`, every NOT NULL there, `t_c_not_null` by default), information_schema's CHECK rows, DROP / RENAME CONSTRAINT | the syntax as PostgreSQL 18 (`[CONSTRAINT n] NOT NULL c` in CREATE TABLE and ALTER TABLE ... ADD, 42703, 42601 for two names of a column); the name is not kept, the catalogs list no NOT NULL constraints, DROP CONSTRAINT n 42704 | works (syntax, ec3c5c17) / missing (the catalogs: plan in 8.4) | S (syntax) / M (catalogs) | none | lexdb_parse `nnCons`; lexdb_catalog, lexdb_pgcat |
| P8 | `uuidv7([shift interval])`, `uuidv4()` (P18); `uuid_extract_version`, `uuid_extract_timestamp` (P17) | | as PostgreSQL: version 7 with 12 bits of the sub-millisecond, rising within the process; the version and time of versions 1, 4, 7 (NULL for another variant) (was 42883) | works (f8c07339) | S | Oracle `UUID()`, `IS_UUID()` (O14, works); T-SQL NEWID (works) | lexdb_newfn |
| P9 | `casefold`, `array_sort`, `array_reverse`, `crc32`, `crc32c`, `gamma`, `lgamma` (P18) | | as PostgreSQL but array_sort (lexdb-gaps.md 2.1: 42883 still); gamma and lgamma the C library's (its last digit may differ from another libm's) | works (271ca36e) / missing (array_sort) | S (together) | none | lexdb_newfn |
| P10 | `reverse(bytea)` (P18) | `\x0102` gives `\x0201` | as PostgreSQL (was `2010x\`, the bytea's text reversed) | works (91781b58) | S | none | lexdb_lib |
| P11 | int <-> bytea casts (P18), uuid <-> bytea (P19) | `258::bytea` = `\x00000102` | as PostgreSQL: an integer's bytes as wide as its type, a bytea as an integer (22003 past its width), uuid to and from 16 bytes (22P03) (was 42846) | works (271ca36e) | S | none | lexdb_ops `castMore`, lexdb_bind `byteaCast`, `intCast` |
| P12 | `to_number(text, 'RN')` Roman numerals (P18) | 1994 | as PostgreSQL: either case, blanks before it, the rest not read, 22P02 for one not written as one (IIII, IC) (was 22P02 always) | works (91781b58) | S | Oracle `TO_NUMBER` has no RN (TO_CHAR has) | lexdb_func |
| P13 | named arguments of `regexp_*` (`pattern =>`, P18) | | `function regexp_replace does not accept named arguments` (plan in 9.3) | missing | S | none | lexdb_parse `paramsOf`, lexdb_bind |
| P14 | `error_on_null(x)` (P19); `random(min, max)` for integers and numerics (P17), dates and timestamps (P19) | | as PostgreSQL: error_on_null (22004), random of integers and numerics (22023; the larger scale); of dates and timestamps 42883 still | works (271ca36e) / missing (random of dates) | S | none | lexdb_newfn |
| P15 | `encode/decode(..., 'base64url' \| 'base32hex')` (P19) | `Af8` | as PostgreSQL 19 (was 22023 unrecognized encoding) | works (f8c07339) | S | T-SQL `BASE64_ENCODE(x, 1)` url-safe (S7, works) | lexdb_lib, lexdb_newfn |
| P16 | `COPY ... TO (FORMAT json [, FORCE_ARRAY])` (P19); `ON_ERROR ignore \| set_null`, `REJECT_LIMIT` (P17-19) | one JSON object a line | `COPY format "json" not recognized`; `COPY's option "on_error" is not supported` | missing | M (JSON output is small; ON_ERROR needs the per-row error path of COPY FROM) | none | lexdb COPY (lexdb_exec, lexdb_wire) |
| P17 | json/jsonb, IS JSON, JSON_TABLE, JSON_VALUE/QUERY/EXISTS (P17), JSON_OBJECT/ARRAY/ARRAYAGG/OBJECTAGG (P16), `json_array()` of no rows `[]` (P19), jsonpath string methods (P19), `json_strip_nulls(.., true)` (P18) | | only `json_build_object` exists (lexdb-gaps.md 2.1) | missing | L (section 6.3) | SQL Server (S10), Oracle (O29) | new lexdb_json |
| P18 | virtual generated columns, the default kind (P18); `SET EXPRESSION` of a virtual column with a CHECK (P19) | | as PostgreSQL | works | | | |
| P19 | `MIN/MAX` of arrays (P18); `MERGE ... WHEN NOT MATCHED BY SOURCE ... RETURNING merge_action()` (P17); `GRANT ... GRANTED BY` (P19) | | as PostgreSQL (MERGE RETURNING's rows come in another order without ORDER BY) | works | | | |
| P20 | `EXTRACT(WEEK FROM ...)` (P18 lists it) | column named `extract` (since P14) | as PostgreSQL (was `date_part`); also a cast's column is the type's own name (`int4`, not `integer`) and `pg_typeof`'s is `pg_typeof` (was `?column?`) | works (91781b58) | S | | lexdb_parse, lexdb_bind `exprName` |
| P21 | `x IS DISTINCT FROM y` in a select list | column named `?column?` | as PostgreSQL (was `distinct`) | works (91781b58) | S | | lexdb_bind `exprName` |
| P22 | `0x1F`, `0o17`, `0b101`, `1_000` (P16) | 31, 15, 5, 1000 | as PostgreSQL 16: the literals (of any length: past int8 a numeric), `_` between digits, a number running into a name 42601 ("trailing junk"), a text constant cast to an integer or numeric (`'0x1F'::int`, `'1_000'::bigint`; not a text column's value: below) | works (91781b58) | S | T-SQL `0x..` stays T-SQL's; Oracle has neither: `1_000` is ORA-00911 there now (was `1` aliased `_000`), `0x1F` is 0 aliased X1F as Oracle's | lexdb_parse lexer |
| P23 | met on the way, older: `CREATE DOMAIN` (lexdb-gaps.md 2.2), `WITH v (x) AS (VALUES ...)`, `bit_and`/`bit_or` aggregates, `any_value` (P16), `date_bin` (P14), `unistr` (P14), `date_add`/`date_subtract` (P16), `trim_array` (P14), `array_shuffle`/`array_sample` (P16), `bit_count` (P14), `erf`/`erfc` (P16), `pg_input_is_valid`/`pg_input_error_info` (P16), `to_bin`/`to_oct` (P17) | | `WITH v (x) AS (VALUES ...)` as PostgreSQL (ec3c5c17); bit_and, bit_or, bit_xor, any_value, date_bin, unistr (f8c07339) and date_add, date_subtract, trim_array, array_shuffle, array_sample, bit_count(bytea), erf, erfc, to_bin, to_oct (271ca36e) as PostgreSQL; CREATE DOMAIN 0A000, pg_input_is_valid / _error_info 42883 still | works / missing (CREATE DOMAIN, pg_input_*) | S each but CREATE DOMAIN (L, with O11) | `unistr`: S16/O27 (works); `date_bin`: S13/O12 (works); `any_value`: O18 (works); `bit_and`: O17 (works); domains: O11 | lexdb_newfn, lexdb_agg, lexdb_parse |

## 2. SQL Server 2025 (compatibility level 170) and 2022

Checked on 2025 RTM-CU10 at level 170 unless marked 2022.

| # | Feature | SQL Server's behaviour | lexdb (TDS door) | Class | Size | Other doors natively | Modules |
|---|---|---|---|---|---|---|---|
| S1 | `REGEXP_LIKE(s, p [, flags])` | a predicate only: in a select list 156; bad pattern 19308 (`Missing ')' in the Pattern`); flags c, i, s, m only (19303 for others) | as SQL Server: 156 as a value, 19300/19307/19308/19309 for a pattern RE2 refuses, 19303 for a flag (a variable's too, at the run) | works (91781b58) | M | PostgreSQL `regexp_like` (P15, works), Oracle `REGEXP_LIKE` (works) | lexdb_parse `tsqlCall`, lexdb_func `tsReFlags` |
| S2 | `REGEXP_REPLACE(s, p, r [, start [, occurrence [, flags]]])` | occurrence 0 (all) by default: `a#b#c` | as SQL Server (the door fills SQL Server's defaults); 19301 for a start below 1, an occurrence below 0 | works (91781b58) | (S1) | PostgreSQL, Oracle (Oracle's default is all: its door already adds `g`) | (S1) |
| S3 | `REGEXP_SUBSTR`, `REGEXP_INSTR`, `REGEXP_COUNT` | occurrence, return option, flags, group | as SQL Server for every case tried; now also Perl's leftmost-first match (`a\|ab` finds `a`; PostgreSQL's longest found `ab`) and 19301 for its arguments | works (91781b58) | | PostgreSQL, Oracle | |
| S4 | `REGEXP_MATCHES(s, p [, flags])` (table) | columns `match_id, start_position, end_position, match_value, substring_matches` (JSON) | as SQL Server: every match, empty ones' places as SQL Server gives them, the groups' JSON text (`null` for a group not taking part), in FROM and APPLY (substring_matches is nvarchar text, SQL Server's json type) | works (91781b58) | (S1) | PostgreSQL `regexp_matches` (other shape) | lexdb_srf, lexdb_lib `tsqlMatchRows` |
| S5 | `REGEXP_SPLIT_TO_TABLE(s, p [, flags])` | columns `value, ordinal` | as SQL Server | works (91781b58) | (S1) | PostgreSQL (one column, works there) | lexdb_srf |
| S6 | the flags' meaning | RE2's (SQL Server's engine): `.` does not match a newline unless `s`; `^`/`$` at lines only with `m` | as SQL Server; the pattern as RE2 reads it (no PostgreSQL ARE escapes: `\m` is 19300) | works (91781b58) | (S1) | | lexdb_func `tsReFlags`, `reCompileFor` |
| S7 | `BASE64_ENCODE(varbinary [, url_safe])`, `BASE64_DECODE(varchar)` | `AQL/`, `AQL_`; 9803 for bad input | as SQL Server 2025: url-safe without padding, either alphabet and optional padding in, 9803, 8116 (a literal's varchar / nvarchar: 9.3) (was 195) | works (f8c07339) | S | PostgreSQL `encode(.., 'base64')` and 19's base64url (P15, works) | lexdb_newfn, lexdb_parse `tsqlNewCall` |
| S8 | `||` string concatenation | `'a' \|\| 1` = `'a1'`, NULL propagates; `1 \|\| 2` 402 | as SQL Server (402 when neither side is a string; the PostgreSQL door's `1 \|\| 2` is 42883 now, as PostgreSQL's; Oracle's `\|\|` takes numbers, unchanged) | works (91781b58) | S | PostgreSQL, Oracle (works) | lexdb_bind `catTypes` |
| S9 | `||=` compound assignment (2025) | `SET @s \|\|= 'b'`, `UPDATE t SET c \|\|= 'b'`; NULL stays NULL; int \|\|= int 402 | as SQL Server 2025 (ec3c5c17: was 102); with it the compound assignments UPDATE ... SET lacked (`+=`, `-=`, `*=`, `/=`, `%=`, `&=`, `\|=`, `^=`: 102 before) and `^=` of SET @v; and `^` is XOR in the door (it was PostgreSQL's power: `6 ^ 3` 216, SQL Server's 5) | works (ec3c5c17) | S | none | lexdb_tsqlparse, lexdb_parse `tsqlCompound`, `setList` |
| S10 | `json` type, `JSON_ARRAYAGG`, `JSON_OBJECTAGG(k : v)`, `JSON_CONTAINS`, `@j.modify(path, v)`; 2022's `JSON_OBJECT`, `JSON_ARRAY`, `JSON_PATH_EXISTS`, `ISJSON(x, type)`; 2016's `ISJSON`, `JSON_VALUE`, `JSON_QUERY`, `JSON_MODIFY`, `OPENJSON`, `FOR JSON` | `JSON_CONTAINS` takes the json type only (8116 for varchar); empty `JSON_ARRAYAGG` NULL | 195 / 2715 / 102 / 208 for every one | missing | L (section 6.3) | PostgreSQL (P17), Oracle (O29) | new lexdb_json, lexdb_tds (2025's json TDS type) |
| S11 | `vector(n [, float16])`, `VECTOR_DISTANCE('cosine'\|'euclidean'\|'dot', a, b)`, `VECTOR_NORM`, `VECTOR_NORMALIZE`, `VECTORPROPERTY`; `VECTOR_SEARCH` and vector indexes (PREVIEW_FEATURES) | shown as a JSON array `[1.0000000e+000,...]` | 102 | missing | L, note only (section 6.3) | Oracle `VECTOR` (O30); PostgreSQL only through pgvector (not native) | |
| S12 | `PRODUCT(x)` aggregate, also `DISTINCT` and `OVER (...)` | 24; 8115 for an int overflow; NULL for no rows | as SQL Server: an int's an int (8115), bigint, float, decimal(38, 6), DISTINCT, OVER, NULL for no rows, 8117 for a varchar (was 195) | works (f8c07339) | S | none | lexdb_agg, lexdb_bind `productName` |
| S13 | `DATE_BUCKET(part, n, d [, origin])` (2022) | `2020-01-06` for week 1 of `2020-01-08` | as SQL Server: each part and type, an origin, months from its day, 8116, 9810, 9834, 155 (a datetimeoffset's offset: 9.3) (was 207) | works (f8c07339) | S: one kernel, three spellings | PostgreSQL `date_bin` (P23, works), Oracle `TIME_BUCKET` (O12, works) | lexdb_newfn `bucketOf`, lexdb_parse `tsqlNewCall` |
| S14 | `DATETRUNC(part, d)` (2022) | | as SQL Server: each part, week (DATEFIRST 7) and iso_week, the type and its precision (9810), a string as datetime2(7) (was 207) | works (f8c07339) | S | PostgreSQL `date_trunc`, Oracle `TRUNC(d, fmt)` (both work) | lexdb_newfn, lexdb_exec `newScale` |
| S15 | `FIRST_VALUE/LAST_VALUE/LAG/LEAD(x) IGNORE NULLS OVER (...)` (2022) | | 102 at `nulls` | missing | (P5) | PostgreSQL 19 (P5), Oracle (O25) | lexdb_window |
| S16 | `UNISTR(s [, escape])` | `\00e9`, `\+01F600`, another escape character; a varchar input needs a UTF-8 collation (9844) | as SQL Server: the escapes, another escape character, 9841-9843; 9844 not for a literal (9.3) (was 195) | works (f8c07339) | S: one function, three spellings | PostgreSQL `unistr` (P23, works), Oracle `UNISTR` (O27, works) | lexdb_newfn `unistr` |
| S17 | `EDIT_DISTANCE(a, b [, max])`, `EDIT_DISTANCE_SIMILARITY`, `JARO_WINKLER_DISTANCE`, `JARO_WINKLER_SIMILARITY` | 3, 57, 0.0388..., 96 for kitten/sitting and martha/marhta; **9847 under a SQL_ collation**, which is the default (and lexdb's TDS collation, SQL_Latin1_General_CP1_CI_AS): a Windows collation must be named | as SQL Server 2025: the optimal string alignment distance (martha/marhta 1), its maximum, 9847 under an SQL_ collation, a CI one's case folded, 8116, 174, 189 (was 195) | works (f8c07339) | S (with the 9847 rule) | Oracle `UTL_MATCH` (O28, works); PostgreSQL only in the fuzzystrmatch extension | lexdb_newfn, lexdb_bind `newCall` |
| S18 | `CURRENT_DATE`; `SUBSTRING(s, start)` without length; `DATEADD` with a bigint | | as SQL Server (`SUBSTRING(NULL, 1)` 8116 now) | works (91781b58) | | | |
| S19 | `GREATEST`, `LEAST`, `TRIM/LTRIM/RTRIM(s, chars)`, `WINDOW` clause, `IS [NOT] DISTINCT FROM` (2022) | | as SQL Server (IS DISTINCT FROM: section 5) | works | | | |
| S20 | `GENERATE_SERIES` (2022), `STRING_SPLIT(s, sep, 1)` with the ordinal (2022) | columns `value` and `value, ordinal` | GENERATE_SERIES as SQL Server (`value`; without a step -1 when start > stop, as SQL Server: was no rows) (91781b58); STRING_SPLIT 208 (missing in any form) | works / missing | S | | lexdb_srf, lexdb_parse |
| S21 | 2022's `APPROX_PERCENTILE_CONT/DISC`, `BIT_COUNT`, `LEFT_SHIFT`, `RIGHT_SHIFT`, `GET_BIT`, `SET_BIT`; and older ones met on the way: `CHAR()`, `NCHAR()`, `FORMAT(n, 'N2')` | `FORMAT(1234.5, 'N2')` = `1,234.50` | FORMAT as SQL Server: .NET's standard and custom number and date formats, en-US and de-DE (new module lexdb_tsqlfmt); CHAR and NCHAR (the REGEXP tests' newlines needed them) (91781b58); the 2022 functions as SQL Server (ec3c5c17): BIT_COUNT, LEFT_SHIFT / RIGHT_SHIFT and `<<` / `>>` (as wide as the type: `1 << 33` is 0, logical, a negative count the other way), GET_BIT, SET_BIT, their errors (8116, 9838, 9839, 174), APPROX_PERCENTILE_CONT / _DISC (exact: lexdb_pct's T-SQL percentiles, no OVER: 4113); a varbinary's bits only where lexdb has a varbinary value (a `0x..` literal is an int in the door, lexdb-tds.md 13) | works | S each | PostgreSQL `bit_count` (P23), `chr` | lexdb_tsqlfmt, lexdb_parse `tsqlCall` |
| S22 | constraint checking off: `WITH NOCHECK`, `ALTER TABLE t NOCHECK CONSTRAINT c\|ALL` | | 50000 (ALTER TABLE takes ...) | missing | (P6) | PostgreSQL NOT ENFORCED (P6), Oracle DISABLE (O26) | |
| S23 | GROUP BY rules (old T-SQL): `GROUP BY ALL a` keeps the groups WHERE removed (count 0); a select alias or a position in GROUP BY is 207 / 164 | `1\|1;2\|0` | as SQL Server: GROUP BY ALL's groups of every row, each aggregate over WHERE's rows (in the select list, HAVING and ORDER BY), 1028 with ROLLUP; 207 for an alias; 164 for a constant, a position or a variable (91781b58) | works | S | Oracle 26ai `GROUP BY ALL` means another thing (O7): not parsed in that door | lexdb_parse `groupAll`, lexdb_bind `resolveGroupIn` |
| S24 | an unknown function over no rows | 195 when the batch is compiled | 42883 / 195 / ORA-00904 when the statement is bound, over no rows too (91781b58) | works | S | all doors | lexdb_bind `knownCall`, lexdb_lib `entryOf`'s misses |
| S25 | DATEADD of a string literal | a `datetime` (`2020-01-03 00:00:00.000`) | as SQL Server; DATEADD's type is its date's (datetime, smalldatetime, datetime2) (91781b58) | works | S | | lexdb_parse `tsqlCall`, lexdb_exec `exprScale` |
| S26 | TDS 8.0 strict encryption (`Encrypt=Strict`: TLS before PRELOGIN, ALPN `tds/8.0`) | 2025 supports it for every component | lexdb speaks TDS 7.4 with TLS inside PRELOGIN (not tried with a strict client) | note only | M: the TLS-first path exists for TCPS (lexdb_tns), the handshake order is the work | | lexdb_tds |

## 3. Oracle AI Database 26ai (23.26.3) and 23ai

| # | Feature | Oracle's behaviour | lexdb (TNS door) | Class | Size | Other doors natively | Modules |
|---|---|---|---|---|---|---|---|
| O1 | `QUALIFY cond` (23.26.0) | filters on window results after them; select-list aliases visible (`qualify rn = 1`) | ORA-00900 | missing | M: a filter above the window step; aliases and ORDER BY make it more than a token rewrite | none | lexdb_parse, lexdb_plan |
| O2 | aggregate and window `FILTER (WHERE ...)` (23.26.1) | | as Oracle | works | | PostgreSQL (works) | |
| O3 | `SELECT` without `FROM` | | as Oracle | works | | PostgreSQL, T-SQL | |
| O4 | `BOOLEAN` columns, `TRUE`/`FALSE`, boolean expressions in the select list and WHERE | | as Oracle (types BOOLEAN on the wire); `TO_BOOLEAN` (ORA-61800), `BOOLEAN_AND_AGG`, `BOOLEAN_OR_AGG` as Oracle (f8c07339) | works | S | PostgreSQL `bool_and`/`bool_or` (work) | lexdb_newfn, lexdb_agg |
| O5 | table value constructor `VALUES (...), (...)` in FROM, INSERT, MERGE USING, WITH | | the column names as written (`X, Y`, a quoted one as quoted; a CTE's column list's too, and a derived table's in T-SQL: lexdb-dialect-gaps.md 10 "Left"), ORA-00931 / ORA-63814 without an alias or its column list (91781b58); a string literal is a VARCHAR2 where Oracle's is a CHAR (every literal of the door, not VALUES': not changed, see 7.3); in WITH as Oracle (ec3c5c17) | works (names; WITH: as Oracle, ec3c5c17, with ORA-63803 without a column list, 63815, 63801) / wrong answer (literal type) | S | PostgreSQL (WITH: works, ec3c5c17), T-SQL (FROM only, works) | lexdb_parse `aliasOf`, lexdb_exec FROM binding |
| O6 | `CREATE ... IF NOT EXISTS`, `DROP ... IF EXISTS` | | as Oracle | works | | PostgreSQL, T-SQL DROP | |
| O7 | `GROUP BY ALL` (26ai) | groups by every select item that is not an aggregate | as Oracle (ec3c5c17): every select item without an aggregate (GROUPING too) or a window call, `*` and `t.*` expanded; ORA-03048 for a comma or ALL after it, ORA-03049 for ROLLUP; not T-SQL's (S23) | works (ec3c5c17) | S | none (T-SQL's `GROUP BY ALL` is another feature: S23) | lexdb_parse, lexdb_bind |
| O8 | `GROUP BY` alias and position; `HAVING` alias (23ai) | alias works; a position is ORA-03162 unless `ALTER SESSION SET group_by_position_enabled = TRUE` | as Oracle: a number a constant (ORA-03162 when the list needs a grouping), a position after the ALTER SESSION (TRUE/FALSE, ORA-00922 else), HAVING's alias where no column has the name (91781b58) | works | S | PostgreSQL (alias and position, works; no HAVING alias) | lexdb_parse `groupBy`, lexdb_bind `groupedIn`, `resolveHaving`, lexdb_tns `parseOpts` |
| O9 | direct joins: `UPDATE t SET ... FROM t2 WHERE ...`, `DELETE t FROM t2 WHERE ...` | | UPDATE right; DELETE `[FROM] t [alias] FROM list` as Oracle (ec3c5c17: was ORA-00900) | works | S | T-SQL `DELETE t FROM ...` (works), PostgreSQL `DELETE ... USING` (works) | lexdb_parse |
| O10 | `INSERT INTO t SET c = v, ...`, `INSERT INTO t BY NAME SELECT ...` (26ai) | both in 23.26.3: SET's `(c, d) = (v, w)` too, BY POSITION; ORA-00957, 00947, 00913, 63875-63878 | as Oracle (ec3c5c17): rewritten to a column list; not `SET (c, d) = (subquery)` (0A000) nor BY NAME of `*` (0A000) | works (ec3c5c17) | S | none | lexdb_parse `oraInsertSet`, `oraByName` |
| O11 | SQL domains: `CREATE DOMAIN d AS type CONSTRAINT .. CHECK (d > 0)`, domain columns, `DOMAIN_NAME()`, `DOMAIN_DISPLAY()` | ORA-11534 for a violation | ORA-03001 (0A000) | missing | L: a catalog object, its constraints on every write, its display/order expressions, the catalogs | PostgreSQL `CREATE DOMAIN` (P23; lexdb-gaps.md 2.2) | lexdb_catalog, lexdb_parse, the write path |
| O12 | `TIME_BUCKET(d, interval, origin)` (23ai) | `2024-03-05 10:15` for 15 minutes | as Oracle: an INTERVAL or ISO 8601 stride, START / END, ORA-03403, 01867, 03404 (was ORA-00904) | works (f8c07339) | (S13) | T-SQL DATE_BUCKET (S13, works), PostgreSQL date_bin (P23, works) | lexdb_newfn `bucketOf` |
| O13 | `DATEADD(part, n, d)`, `DATEDIFF(part, a, b)` / `TIMESTAMPDIFF` (26ai) | DATE result; 30 days | as Oracle: the T-SQL door's `#dateadd`/`#datediff`, the part by its whole name (ORA-00904), n rounded (was ORA-00904 `"DAY"`) | works (271ca36e) | S | T-SQL (works) | lexdb_parse `oraDateAdd` |
| O14 | `UUID()`, `IS_UUID()` (26ai) | | as Oracle, with RAW_TO_UUID and UUID_TO_RAW (ORA-62432) (was ORA-00904) | works (f8c07339) | (P8) | PostgreSQL uuidv7/uuidv4 (P8, works) | lexdb_newfn |
| O15 | `CEIL/FLOOR/ROUND/TRUNC` of DATE, TIMESTAMP and INTERVAL (23ai) | `CEIL(DATE '2024-03-05', 'MONTH')` = 2024-04-01; `TRUNC(timestamp, 'HH')` is a DATE | TRUNC of a timestamp is a DATE (on the wire, and in arithmetic: TRUNC(ts) - DATE is a number of days) (91781b58); CEIL, FLOOR, ROUND of a DATE, a TIMESTAMP (a DATE) and an INTERVAL as Oracle, ORA-01821, 01899 (271ca36e) | works | S | | lexdb_bind `oraStamp`, `newCall`, lexdb_newfn `oRoundFn` |
| O16 | `SUM`/`AVG` of INTERVAL (23ai) | INTERVAL DAY TO SECOND | SUM an interval (DAY TO SECOND, YEAR TO MONTH), AVG of DAY TO SECOND (91781b58; the PostgreSQL door's `avg(interval)` was 42883 too: works now, PostgreSQL's interval_avg); AVG of YEAR TO MONTH whole months cut toward zero, as Oracle (271ca36e: was PostgreSQL's `1 year 15 days`, a VARCHAR2) | works | S | PostgreSQL (works) | lexdb_agg, lexdb_bind |
| O17 | `BIT_AND_AGG`, `BIT_OR_AGG`, `BIT_XOR_AGG`, `CHECKSUM`, `KURTOSIS_POP/SAMP`, `SKEWNESS_POP/SAMP` (21c/23ai) | | as Oracle (0 over no rows; the moments in doubles: ROUND them to compare, 9.3) but CHECKSUM (Oracle's own hash: 9.3), ORA-00904 still | works (f8c07339) / missing (CHECKSUM) | S | PostgreSQL `bit_and`/`bit_or`/`bit_xor` (P23, works) | lexdb_agg |
| O18 | `ANY_VALUE` (21c) | | as Oracle (was ORA-00979) | works (f8c07339) | S | PostgreSQL 16 (P23, works) | lexdb_agg |
| O19 | `RETURNING OLD c, NEW c INTO :a, :b` for INSERT, UPDATE, DELETE, MERGE (23ai) | INSERT's OLD NULL, DELETE's NEW NULL; OLD/NEW before any column of an expression; ORA-00904 for `old.c` and `OLD f(x)`, ORA-01747 for `OLD *`, ORA-03050 without a column; MERGE with DELETE WHERE ORA-03001; INSERT ... SELECT has no RETURNING (ORA-03049) | as Oracle (ec3c5c17), through the door's RETURNING INTO and in PL/SQL; the two errors of other RETURNINGs (03001, 03049) too (they were accepted) | works (ec3c5c17) | (P2) | PostgreSQL 18 (P2), T-SQL OUTPUT (works) | lexdb_parse |
| O20 | `DEFAULT ON NULL [FOR INSERT ONLY \| FOR INSERT AND UPDATE] v` (12c; UPDATE 23ai) | a NULL written becomes the default, the column NOT NULL; an UPDATE to NULL ORA-01407 unless FOR INSERT AND UPDATE; USER_TAB_COLUMNS' DEFAULT_ON_NULL, DEFAULT_ON_NULL_UPD | as Oracle (ec3c5c17): INSERT, INSERT ... SELECT, UPDATE, MERGE, ALTER TABLE ADD / MODIFY, the views, ORA-02000, 00936, 30665 | works (ec3c5c17) | S | none | lexdb_parse `oraDefault`, lexdb_exec `onNullFill`, lexdb_oracat |
| O21 | annotations: `ANNOTATIONS (name 'value', ...)` on tables and columns, `USER_ANNOTATIONS_USAGE` | | ORA-00900 | missing | M: kept in the catalog, listed in the views | none | lexdb_parse, lexdb_oracat |
| O22 | SQL/PGQ: `CREATE PROPERTY GRAPH`, `GRAPH_TABLE (g MATCH ... WHERE ... COLUMNS (...))`, bounded quantifiers `->{1,2}` | rows as the joins of the pattern; ORA-42421 for an unknown graph | ORA-00900 | missing | L (section 6.3) | none (PostgreSQL 19 has not; SQL Server's MATCH over NODE/EDGE tables is another design) | new lexdb_graph |
| O23 | `CREATE ASSERTION a CHECK (NOT EXISTS (...) \| ALL (...) SATISFY (...))` (23.26.1) | ORA-08601 `Assertion (APP.A1) violated` at the DML; no aggregates (ORA-08689, ORA-00934); `USER_ASSERTIONS` | ORA-00900 | missing | L (section 6.3: a design note) | none | new lexdb_assert |
| O24 | `IS [NOT] DISTINCT FROM` | not Oracle's (ORA-00908, 23.26.3) | accepted (lexdb's extension in this door) | wrong error | S: refuse it when `p.ora` in `lexdb_parse.isTail`; but users may rely on the extension: the user's call | PostgreSQL, T-SQL 2022 | lexdb_parse |
| O25 | `IGNORE NULLS` in `FIRST_VALUE(x IGNORE NULLS)`, `LAST_VALUE`, `LAG(x) IGNORE NULLS`, `LEAD`, `NTH_VALUE` | | ORA-00900 | missing | (P5) | PostgreSQL 19, T-SQL 2022 | lexdb_window |
| O26 | `CONSTRAINT c CHECK (...) DISABLE`, `ENABLE [NO]VALIDATE` | | ORA-00900 | missing | (P6) | PostgreSQL NOT ENFORCED, T-SQL NOCHECK | |
| O27 | `UNISTR('\00e9')` | NVARCHAR2 | as Oracle (ORA-30186) (was ORA-00904) | works (f8c07339) | (S16) | PostgreSQL, T-SQL 2025 (works) | lexdb_newfn |
| O28 | `UTL_MATCH.EDIT_DISTANCE`, `.JARO_WINKLER`; `UTL_ENCODE.BASE64_ENCODE` | 3; `aGk=` | UTL_ENCODE.BASE64_ENCODE and BASE64_DECODE as Oracle (RAW in, RAW out; ORA-29261 for NULL), with UTL_RAW.CAST_TO_RAW and CAST_TO_VARCHAR2 (they were NULL) (91781b58); UTL_MATCH's EDIT_DISTANCE, EDIT_DISTANCE_SIMILARITY, JARO_WINKLER, JARO_WINKLER_SIMILARITY as Oracle (f8c07339) | works | S | T-SQL 2025 (S17, S7, works) | lexdb_orafn, lexdb_newfn, lexdb_parse |
| O29 | JSON: the `JSON` type, `JSON_OBJECT('a' : 1)`, `JSON_ARRAY`, `JSON_VALUE ... RETURNING`, `JSON_ARRAYAGG`, `JSON_OBJECTAGG(k VALUE v)`; JSON relational duality views (note only) | | ORA-00900 / ORA-00902 | missing | L (section 6.3) | PostgreSQL (P17), SQL Server (S10) | new lexdb_json, lexdb_tns (type 119) |
| O30 | `VECTOR(n, FLOAT32 \| INT8 \| ...)`, `VECTOR_DISTANCE(a, b, COSINE \| EUCLIDEAN ...)` | | ORA-00904 | missing | L, note only | SQL Server 2025 (S11) | |

Not counted: two 26ai features that 23.26.3 does not have yet, which lexdb already accepts as extensions: `SELECT *, 1 AS one` (ORA-00923 on 23.26.3) and `FETCH FIRST n ROWS ONLY FOR UPDATE` (ORA-02014). `JOIN TO ONE` was refused in the form tried (ORA-03048) and is left out until its syntax is confirmed.

## 4. Counts

A row with two parts (P7, P9, P14, P23; S20; O5, O17) is counted in each part's class, so the parts add up to more than
the rows.

| Product | works | wrong answer | wrong error | missing | parts / rows |
|---|---|---|---|---|---|
| PostgreSQL 19/18 (and older met on the way) | 16 (P2, P4, P7's syntax, P8, P9 but array_sort, P10-P12, P14 but random of dates, P15, P18-P22, P23's VALUES in WITH and functions) | 0 | 0 | 11 (P1, P3, P5, P6, P7's catalogs, P9's array_sort, P13, P14's random of dates, P16, P17, P23's CREATE DOMAIN and pg_input_*) | 27 / 23 |
| SQL Server 2025/2022 | 21 (S1-S9, S12-S14, S16-S21, S23-S25) | 0 | 0 | 5 (S10, S11, S15, S20's STRING_SPLIT, S22) | 26 / 25, and S26 (note) |
| Oracle 26ai/23ai | 20 (O2-O10, O12-O20 but O17's CHECKSUM, O27, O28) | 1 (O5's literal type) | 1 (O24) | 10 (O1, O11, O17's CHECKSUM, O21-O23, O25, O26, O29, O30) | 32 / 30 |

Before the fixes of section 7 (the audit as run): PostgreSQL 2 / 4 / 1 / 16; SQL Server 3 / 8 / 5 / 13; Oracle 5 / 4 / 2 / 26. After
section 7, before section 8: PostgreSQL 7 / 0 / 0 / 16; SQL Server 14 / 0 / 0 / 13; Oracle 10 / 2 / 1 / 26. After section 8,
before section 9: PostgreSQL 11 / 0 / 0 / 14; SQL Server 15 / 0 / 0 / 11; Oracle 14 / 2 / 1 / 18.

## 5. IS [NOT] DISTINCT FROM in the T-SQL door: the test

`tests/lexdb/run/tds_distinct.lxl`, generated by `gen_mssql.py distinct` from `mssql_distinct_queries.txt` against SQL
Server 2022 (70 batches). The generator has a new mode for it (`BOTH`): against lexdb each batch runs with `SET
lexdb_batch = off` and then `on`, and the line is `same: ` and the answer (or `DIFFERENT: rows // batches: ...`); against
SQL Server it prints `same: ` and SQL Server's answer; `@once ` lines (setup) run once. Covered: WHERE, NOT, AND/OR,
CASE, IIF, IF, variables, inner and left joins, HAVING, EXISTS, NOT EXISTS, scalar subqueries, UPDATE and DELETE (in a
transaction rolled back so both runs see the same rows); NULL on either side and both; int against decimal, bigint,
float and a text that converts; text under the default collation (case and trailing blanks) and a CS one, nvarchar;
dates against a text and a datetime; empty tables and empty results; 3,000 rows with NULLs and duplicates, grouped and
joined on text keys; errors in a later row (8134, 245) and syntax errors (102, 156). Every answer equals SQL Server's.

Left out of the test because lexdb answers otherwise (recorded here, not fixed: none is specific to IS DISTINCT FROM):
- in a select list (`SELECT a IS DISTINCT FROM b AS k`): SQL Server 156, lexdb a bit (as REGEXP_LIKE, S1): 156 now (section 7, tds_newfix);
- a row value (`(a, b) IS DISTINCT FROM (1, 1)`): SQL Server 4145, lexdb compares the rows (PostgreSQL's form);
- int against a text that does not convert: 245, lexdb 195; int against date: 206, lexdb 195. `=` behaves the same
  (`WHERE a = 'x'` is 195 in lexdb; `WHERE a = dt`, int against date, gives no rows and no error): the door's
  comparison of mixed types, not this predicate.

The Oracle door has no test: Oracle 26ai has no IS DISTINCT FROM (O24).

## 6. A proposed order

The user's priority stands: cheap binder items first, WAIT FOR LSN with the replica work, REGEXP_*, GRAPH_TABLE, CREATE
ASSERTION. Each slice puts a feature into every door that has it natively, tested per door against the product (the
containers above), batches on and off.

### 6.1 Cheap: parser and binder items, each under half a day

1. **RETURNING old/new** (P2, O19): `old.`/`new.` and `WITH (OLD AS o, NEW AS n)` onto the `#old` machinery OUTPUT
   already uses; Oracle's `RETURNING OLD c, NEW c INTO`.
2. **GROUP BY's dialect rules** (O7, O8, S23): Oracle's GROUP BY ALL, HAVING alias, `group_by_position_enabled`
   (ORA-03162 by default); T-SQL's alias/position refusals (207, 164) and its own GROUP BY ALL (the WHERE-removed
   groups with empty aggregates).
3. **Column names** (P20, P21, S20's `value`): `extract`, `?column?` for IS DISTINCT FROM, GENERATE_SERIES's `value`.
4. **Statement forms** (O9, O10, O5's WITH and P23's `WITH v AS (VALUES ...)`, P7, O20): Oracle's `DELETE t FROM`,
   `INSERT ... SET` / `BY NAME`, VALUES as a CTE body (PostgreSQL and Oracle), the named NOT NULL constraint, DEFAULT
   ON NULL.
5. **T-SQL odds** (S8, S9, S25, S21's CHAR/NCHAR/FORMAT): `||` of two numbers (402), `||=`, DATEADD of a literal, the
   missing old functions.
6. **Scalar functions, three spellings where they exist** (lexdb_lib/lexdb_func with thin per-door names):
   UNISTR (S16, O27, P23); UUIDs (P8, O14); BASE64 (S7, P15, O28's UTL_ENCODE); the date buckets (S13, O12, P23's
   date_bin) and DATETRUNC (S14); Oracle's DATEADD/DATEDIFF (O13) and date/interval CEIL/FLOOR/ROUND/TRUNC (O15);
   EDIT_DISTANCE / JARO_WINKLER (S17, O28's UTL_MATCH); TO_BOOLEAN (O4); PostgreSQL 18/19's small functions (P9, P10,
   P11, P12, P13, P14) and the older ones of P23.
7. **Aggregates** (lexdb_agg, row path and pipeline together): PRODUCT (S12), BIT_AND/OR/XOR (O17, P23),
   BOOLEAN_AND/OR_AGG (O4), ANY_VALUE (O18, P23), CHECKSUM, KURTOSIS, SKEWNESS (O17), APPROX_PERCENTILE (S21), SUM/AVG
   of intervals in the Oracle door (O16).
8. **Lexer** (P22): `0x`/`0o`/`0b` and `_` in numbers (PostgreSQL 16).
9. **Unknown functions at binding** (S24): 42883 / 195 / ORA-00904 when the statement is bound, not when a row first
   calls it. On the binding path: the point-select gate decides.

### 6.2 Medium, about a day each

1. **T-SQL REGEXP_*** (S1-S6; the user's list). SQL Server 2025's engine is RE2, as lexdb's is (lexdb-gaps.md 2.1), so
   the T-SQL door can be exact where the PostgreSQL door is not: its own flag mapping (c, i, s, m; 19303 for others;
   `.` not matching a newline by default), REGEXP_REPLACE's occurrence 0, REGEXP_LIKE only as a predicate (156), the
   195xx/193xx errors, and the table shapes of REGEXP_MATCHES (with the substring_matches JSON text) and
   REGEXP_SPLIT_TO_TABLE (value, ordinal). Where: `lexdb_parse.tsqlCall`, lexdb_tsqlfn, lexdb_srf. Test: `tds_regexp`
   against the 2025 container (gen_mssql.py with a DSN option for it).
2. **WAIT FOR LSN** (P4): with the replica work (memory: replicas get dialect listeners next), not alone.
3. **IGNORE NULLS / RESPECT NULLS** (P5, S15, O25): one frame walk in lexdb_window for the five functions, each door's
   spelling (Oracle's inside the parentheses too).
4. **QUALIFY** (O1): a filter after the window step, select aliases visible.
5. **ON CONFLICT DO SELECT** (P1): a third conflict action with its lock strengths and WHERE.
6. **Unenforced constraints** (P6, S22, O26): NOT ENFORCED / NOCHECK / DISABLE, ENABLE NOVALIDATE; one flag, three
   spellings, ALTER rechecking when enforced again.
7. **Annotations** (O21) and **COPY's JSON format, ON_ERROR, REJECT_LIMIT** (P16).
8. **TDS 8 strict** (S26), when a client needs it.

### 6.3 Large, with a short plan each

1. **GRAPH_TABLE** (O22; PostgreSQL when it ships SQL/PGQ, the same rewrite). A property graph is a catalog object:
   vertex tables (KEY, LABEL, PROPERTIES) and edge tables (KEY, SOURCE KEY ... REFERENCES, DESTINATION KEY ...
   REFERENCES, LABEL, PROPERTIES). `GRAPH_TABLE (g MATCH pattern [WHERE c] COLUMNS (...))` in FROM is rewritten into
   SQL before planning: a vertex pattern `(a IS person)` becomes the label's table (a UNION ALL when several tables
   carry the label), an edge `-[k IS knows]->` the edge table joined to its two ends on the declared keys (`<-` swaps
   them, `-` is both directions), the pattern's WHERE and the label predicates join conditions, COLUMNS the select list.
   A bounded quantifier `{m,n}` (Oracle allows bounded ones only) is the UNION ALL of the fixed lengths m..n, or for
   long bounds a recursive CTE through lexdb_recur (section 10's machinery: its depth limit is the bound). Errors
   ORA-42421 and the 424xx family; `USER_PROPERTY_GRAPHS`, `USER_PG_ELEMENTS`, `USER_PG_LABELS`. New module
   `lexdb_graph` (catalog record, rewrite), a hook in the Oracle FROM parse, views in lexdb_oracat. Three to five days.
2. **CREATE ASSERTION** (O23; design note). Oracle 23.26.1: `CREATE ASSERTION n CHECK (NOT EXISTS (q) | ALL (q)
   SATISFY (c))`, optionally DEFERRABLE / INITIALLY DEFERRED, no aggregates (ORA-08689 at CREATE), ORA-08601 at the
   statement that breaks it, `USER_ASSERTIONS`, and the guarantee that two transactions cannot break it together.
   What it takes in lexdb: (a) a catalog object with its query and the tables it reads; (b) after each statement that
   wrote one of those tables (or at COMMIT when deferred), run the violation query: first the whole query, later only
   its delta (each occurrence of a written table replaced by the statement's new rows: the assertion's query is a
   conjunctive NOT EXISTS, so a violation needs a new row); (c) concurrency: lexdb's snapshots allow write skew (two
   transactions each adding half of a violation), so a writer of an asserted table takes an assertion lock held to
   commit (exclusive per assertion at first; per key of the delta query later, as Oracle does with its internal
   locks) and the check reads the latest committed rows under it. The gate is a per-table flag tested once per writing
   statement: reads and point selects pay nothing. New module `lexdb_assert`; one hook in the write path. Three to
   five days for (a)-(c) with the whole-query check.
3. **JSON in the three doors** (P17, S10, O29; waiting on the user, lexdb-gaps.md 9.85). Phase 1: one json value kind
   (text, validated, with lib/json's parser) and the functions the three share: JSON_VALUE, JSON_QUERY, JSON_EXISTS,
   JSON_OBJECT, JSON_ARRAY, JSON_ARRAYAGG, JSON_OBJECTAGG, IS JSON, each with its dialect's result types and errors.
   Phase 2 per dialect: PostgreSQL's json/jsonb with `->`, `->>`, `@>`, `?`, jsonpath, JSON_TABLE and the json_*
   functions; T-SQL's OPENJSON, FOR JSON, JSON_MODIFY, ISJSON, 2025's json type, JSON_CONTAINS and `.modify()`; Oracle's
   JSON type, JSON_TABLE, JSON_TRANSFORM, dot notation. Phase 3: the wire types (PostgreSQL oids 114/3802, the TDS
   json type of 2025, Oracle's OSON type 119) and a binary form for jsonb. Weeks, not days; JSON relational duality
   views after.
4. **Temporal keys** (P3; FOR PORTION OF when PostgreSQL ships it). Range types first (int4range, int8range, numrange,
   daterange, tsrange, tstzrange: literals, bounds, `&&`, `@>`, `-|-`, functions; multiranges later). Then WITHOUT
   OVERLAPS without GiST: for a fixed scalar key the ranges of the rows that obey the constraint are ordered by their
   lower bound, so a btree on (key, lower) and a look at the neighbours decide an overlap (23P01). PERIOD foreign keys
   check that the referenced rows' ranges cover the referencing range (their union, read in key order). FOR PORTION
   OF later splits a row into the updated part and the untouched rests. A week or more; range types alone are days.
5. **Domains** (O11 and PostgreSQL's CREATE DOMAIN): a named type over a base type with NOT NULL, CHECK (VALUE ...),
   DEFAULT (PostgreSQL) or a column's constraints, display and order expressions (Oracle), applied on every write and
   cast, listed in each door's catalogs. Two to three days.
6. **Vector** (S11, O30): note only. A typed float array with each product's text form, VECTOR_DISTANCE's metrics,
   norms, the wire types (TDS vector, Oracle's type 127); approximate indexes much later.

### 6.4 Not to do without the user

O24 (refusing IS DISTINCT FROM in the Oracle door, which lexdb accepts today) changes what existing users of the door
may run; the rule says refuse, the user decides.

## 7. The wrong answers and wrong errors fixed (as built)

Branch from main `a319f1f5`, commits `91781b58` and `577bf9fe` (knownCall without an Option in the library's lookup). Every row of sections 1-3 classed *wrong answer* or *wrong error* was
checked again against the product (the containers of the header; PostgreSQL's answers from the scratch PostgreSQL 18)
and fixed in each door that has the feature, but O24 (the user's call) and the parts of 7.3. Rows above say
*works (91781b58)*.

### 7.1 What changed, where

- **T-SQL REGEXP_*** (S1-S6). The T-SQL door's calls keep lexdb's functions; the parser (`lexdb_parse.tsqlCall`) fills
  SQL Server's defaults (REGEXP_REPLACE's occurrence 0, every match) and puts `lexdb_sql.RE_TSQL` before the flags (a
  constant's text, or `RE_TSQL || flags` for an expression), and `lexdb_func.reFlags` then reads them as SQL Server's
  (`tsReFlags`: c, i, s, m; 19303 for others, a variable's at the run). Such a pattern is compiled as RE2 reads it, with
  Perl's leftmost-first match (`a|ab` finds `a`) and none of the PostgreSQL ARE escapes (`\m` is 19300), and RE2's
  errors become SQL Server's (`tsReErr`: 19308 for a missing `)` or `]`, 19307, 19309, 19300 with RE2's words). The
  argument errors are 19301 naming START, OCCURRENCE, RETURN_OPTION, GROUP (`lexdb_lib.posArgIn`). REGEXP_LIKE (and IS
  [NOT] DISTINCT FROM) as a select item is 156. REGEXP_MATCHES and REGEXP_SPLIT_TO_TABLE in FROM or APPLY are
  set-returning functions of their own (`tsql_regexp_matches`, `tsql_regexp_split_to_table`: lexdb_srf, their columns
  in lexdb_exec's srfCols, their rows in `lexdb_lib.tsqlMatchRows` / `tsqlSplitRows`). The PostgreSQL and Oracle doors
  never carry the mark: their regexps are as before.
- **GROUP BY's rules** (S23, O8). T-SQL's `GROUP BY ALL` is rewritten when parsed, as SQL Server's plan does it: WHERE
  moves into each aggregate's argument (`CASE WHEN w THEN x END`; `COUNT(*)` counts `CASE WHEN w THEN 1 END`) in the
  select list, HAVING and ORDER BY, and is dropped (`groupAll`; WHERE goes from selectCore to select in the SELECT's
  `sets`); 1028 with ROLLUP. A T-SQL GROUP BY item without a column is 164 when parsed; a name is a column only
  (`lexdb_bind.resolveGroupIn`: 207). Oracle: a GROUP BY number is a constant (`lexdb_sql.gbConst`) unless the session
  has `ALTER SESSION SET group_by_position_enabled = TRUE` (lexdb_tns keeps it with the NLS values and hands it to the
  parser after the formats, `lexdb_parse.GB_POS`); an ungrouped column then is ORA-03162 (`lexdb_bind.groupedIn`);
  HAVING may name a select alias where no column has the name (`resolveHaving`). Oracle's own GROUP BY ALL (O7) is not
  parsed in that door (ORA-00900 as before).
- **Column names** (P20, P21, S20, O5). EXTRACT is its own call (`extract`, date_part's kernel, read back as EXTRACT by
  exprText); IS DISTINCT FROM is `?column?`; a cast's column the type's own name (`int4`) and pg_typeof's `pg_typeof`
  (both met while testing: PostgreSQL's names); T-SQL GENERATE_SERIES's column `value` (and without a step -1 when the
  start is above the stop, as SQL Server). A FROM subquery's, a VALUES' and a non-recursive CTE's column list keep their
  spelling in the T-SQL and Oracle doors (`aliasOf` hands the spellings back; lexdb_exec's FROM binding puts them in
  ColDef.spell): lexdb-dialect-gaps.md section 10's "Left" item. Oracle's VALUES needs an alias (ORA-00931) with columns
  (ORA-63814).
- **T-SQL odds** (S8, S18, S21, S25). `||` of two values neither of which is a string is 402 (42883 in the PostgreSQL
  door, PostgreSQL's: `lexdb_bind.catTypes`); SUBSTRING and FORMAT of a NULL constant 8116; FORMAT has .NET's format
  strings (new module `lexdb_tsqlfmt`: N, F, D, X, P, C, E, G and custom number formats, the standard and custom date
  formats, en-US and de-DE, NULL for a format .NET refuses, 8116 and 9818); DATEADD of a string constant is a datetime,
  and DATEADD's type is its date's (`lexdb_exec.exprScale`); CHAR and NCHAR (missing; the REGEXP tests' newlines need
  them).
- **Lexer** (P22). PostgreSQL 16's literals (`lexdb_parse.pgNumber`, entered only when a number runs into a letter or
  `_`, or an exponent has no digits): 0x, 0o, 0b of any length, `_` between digits, and "trailing junk" (42601) for
  `0x`, `1__0`, `12abc`, `1.5e`; a text constant cast to an integer or numeric reads the same forms (`pgCast`). T-SQL's
  `0x..` is as before; Oracle has neither, and `1_000` is ORA-00911 there now.
- **Unknown functions** (S24). `lexdb_bind.resolve` refuses a call no evaluator has (`knownCall`: the parser's own `#`
  names and modified names, aggregates, window, sequence, lock, catalog and session functions, the library's through
  `lexdb_lib.entryOf`, which counts its misses, and the executor's own) with 42883 (195, ORA-00904 in the other doors) when the statement is
  bound, over no rows too.
- **Small ones** (P10, P12, O15, O16, O28). reverse(bytea) reverses the bytes; to_number's RN reads a Roman numeral
  (`lexdb_func.romanIn`); Oracle's TRUNC of a TIMESTAMP is a DATE (`oraStamp`, exprScale); SUM of an interval is typed an
  interval and AVG of intervals exists (it was missing in every door: 42883); UTL_ENCODE.BASE64_ENCODE / BASE64_DECODE
  and UTL_RAW.CAST_TO_RAW / CAST_TO_VARCHAR2 (they were NULL) in lexdb_orafn.

Tests, each statement with batches off and on: `tds_regexp` (94 batches) and `tds_newfix` (69), SQL Server 2025
(`gen_mssql.py --port 14331 --container lxl-mssql25`; `tools/mssql_container.sh` takes LXL_MSSQL_NAME); `tns_newfix`
(42 statements, Oracle Free 23.26.3, `gen_oracle.py --check tns_newfix`: 0 differences); `exec_newfix` (55 queries,
PostgreSQL 18, `gen_pg.py`'s new NAMED mode: columns' names, batches off and on). Suite 313 of 313.

### 7.2 Cost

The parser reset its per-statement state before each statement, the first too: five empty arrays made again for every
parse. It is now reset only after a `;`, which makes a point select's parse 284 instructions cheaper and pays for the
new code; what the new forms hand between parser functions travels in the statement or in the column list, not in new
fields of the parser (two empty arrays there cost 122 instructions a parse).

- In process (`LXL_HASH_SEED=1`, 20,000 statements less the setup, base main a319f1f5, both `-O`, two rounds
  alternated, equal in both): point select 120,549 -> 120,265 instructions, INSERT 4,295,195 -> 4,294,929, UPDATE by
  key 4,280,417 -> 4,280,140.
- Over the wire (`icount6.sh`, 3 x points.sql, base and branch alternated twice), per statement: instructions
  173,337 / 173,419 -> 173,194 / 173,252; cycles 96,861 / 97,436 -> 96,939 / 97,184; L1 i-cache misses 294 / 295 ->
  348 / 349, iTLB misses 54 / 52 -> 36 / 36. (Before 577bf9fe, with knownCall over an Option of entryOf's, the cycles
  were 1.6 to 1.9% up at equal instructions: placement.)
- TPC-H SF1 (`run.sh`, lexdb only, base and branch alternated twice, the best of each side): checksums equal on all 22;
  total 8,891 -> 8,879 ms. No query slower beyond noise: q17 (22.0 -> 22.6 ms) and q11 (88.9 -> 89.9) by server
  instructions equal (130.31M / 130.31M against 130.30M / 130.31M; 530.4M / 530.4M against 530.5M / 530.1M); q20
  253.9 -> 246.1. (The first round, before 577bf9fe: 8,932 -> 8,874, q16 and q19 up by placement, their instructions
  equal run order alternated.)
- lexdb_exec: 20,430 -> 20,446 lines (FROM binding's spellings, DATEADD's and TRUNC's types, the srf columns, the GROUP BY
  and HAVING calls).

### 7.3 Left

- Oracle's string literal is a CHAR (fixed length, blank-padded comparison: `where q = 'a '` finds `'a'`); every literal
  of lexdb's Oracle door is a VARCHAR2. Not VALUES' alone: a change of the door's typing, to plan with the CHAR
  semantics it brings.
- Oracle's AVG of INTERVAL YEAR TO MONTH truncates to months (`+000000001-00`); lexdb gives PostgreSQL's (`1 year 15
  days`, a VARCHAR2): the aggregate does not know the dialect (lexdb_agg's `dia` is the percentiles'). Oracle's DAY TO
  SECOND average has nine fractional digits where lexdb has six (equal through python-oracledb when the microseconds are
  exact, as in the test).
- A text column's value cast to an integer (`t::int` of `'0x1F'`) still takes decimal digits only: the cast does not
  know the door (only text constants are read as PostgreSQL 16's).
- Met while testing, not changed: PostgreSQL's select-list `generate_series(...)` is 42883 in lexdb (now when bound);
  T-SQL `0x1F` in a select list is an int (31) where SQL Server's is a varbinary (lexdb's reading for arithmetic,
  lexdb-tds.md 13); T-SQL CHAR(0) gives NULL (SQL Server a NUL character).
- O24 (refusing IS DISTINCT FROM in the Oracle door) stays the user's call.

## 8. The cheap missing statement forms (as built)

Branch from main `a89a203e`, commit `ec3c5c17` (and d39d41c8, c14f9b06, b12fa897: the cost, 8.2): section 6.1's items 1 (RETURNING old/new), 2's Oracle GROUP BY ALL, 4
(statement forms) and 5 (T-SQL odds), each checked again against the product first (the containers of the header,
PostgreSQL's answers from the scratch PostgreSQL 18) and built in every door that has it. Rows above say *works
(ec3c5c17)*.

### 8.1 What changed, where

- **RETURNING old and new** (P2, O19). New module `lexdb_oldnew`, on the machinery T-SQL's OUTPUT DELETED.c has: a
  reference to the row as it was is `#old(t.c)`, to the row after the statement `#new(t.c)`. PostgreSQL's `old.c`,
  `new.c`, `old.*`, `new.*` and `RETURNING WITH (OLD AS o, NEW AS n)` are read in `lexdb_parse.returning` (a default name
  a table of the statement has is the table's; a name given in WITH that one has is 42712; OLD or NEW twice 42601);
  Oracle's `OLD c` / `NEW c` (before a column, anywhere in RETURNING's expressions, `OLD t.c` too) are written as the
  column of a qualifier no name has (`oraOldNew`, a pass over RETURNING's tokens), with Oracle's errors (ORA-00904 for
  `old.c` and `OLD f(x)`, ORA-01747 for `OLD *`, ORA-03050 without a column). The executor settles what the statement
  decides once (`lexdb_oldnew.settle` in `retOf`: an INSERT's old row NULLs, a DELETE's new row NULLs, an UPDATE's new row
  the row) and the rest per row: an UPDATE's old row as T-SQL's (`oldRefs`), ON CONFLICT DO UPDATE's the row there (an
  updated row is kept followed by the row it was, `upsertOld`; `keptRet` reads it), MERGE's by the action (`actionRefs`: DELETE's new NULL).
  `old.*` and `new.*` are expanded over the target's columns, as T-SQL MERGE's DELETED.* (`lexdb_oldnew.items`, shared
  now). Oracle's other RETURNING errors met on the way: MERGE with DELETE WHERE and RETURNING is ORA-03001, INSERT ...
  SELECT has no RETURNING (ORA-03049); both were accepted.
- **Oracle 26ai's GROUP BY ALL** (O7). Its own parse (`lexdb_parse.oraGroupAll`, the Oracle door only; T-SQL's GROUP BY
  ALL stays `groupAll`'s rewrite): GROUP BY's one item `lexdb_sql.GB_ALL`, which the planner makes the resolved select
  items without an aggregate (GROUPING too) or a window call, `*` and `t.*` expanded (`lexdb_bind.gbAllKeys`, called from
  `lexdb_exec.groupKeys`: GROUP BY's resolution moved out of `planSelect` into it). ORA-03048 for a comma or ALL after
  it, ORA-03049 for ROLLUP and the like; a window over an ungrouped column ORA-00979 as Oracle.
- **Statement forms** (O9, O10, O5's WITH, P23, P7, O20). Oracle's `DELETE [FROM] t [alias] FROM list` (23ai's direct
  join) is PostgreSQL's USING. 26ai's `INSERT INTO t SET c = v, (c, d) = (v, w)` (`oraInsertSet`) and `INSERT INTO t
  [(cols)] BY NAME | BY POSITION query` (`oraByName`: the query's names its columns) are rewritten to a column list, with
  ORA-00957, 00947, 00913, 00904, 63875-63878. VALUES is a CTE's body in PostgreSQL and Oracle (`lexdb_parse.subquery`;
  Oracle's ORA-63803 without a column list, 63815 for a list of another width, 63801 for rows of different widths, also
  in FROM). PostgreSQL 18's NOT NULL table constraint `[CONSTRAINT n] NOT NULL c` in CREATE TABLE and ALTER TABLE ... ADD
  (`nnCons`; 42703, 42601 for two names): the column is NOT NULL, the name is not kept (8.4). Oracle's `DEFAULT ON NULL
  [FOR INSERT ONLY | FOR INSERT AND UPDATE] v` (`oraDefault`): the default kept as `lexdb_sql.ON_NULL(v)` /
  `ON_NULL_UPD(v)` (lexdb_orafn gives v's value; the catalog text round-trips), the column NOT NULL; a row refused for a
  NULL there (the cold path of `checkRow`, in `insertOne` and `updRow`: `onNullFill`) gets the default, on an UPDATE only
  FOR INSERT AND UPDATE (else ORA-01407, as before); USER_TAB_COLUMNS' DEFAULT_ON_NULL and DEFAULT_ON_NULL_UPD (YES / NO,
  as Oracle; they were NULL), DATA_DEFAULT without the mark; ORA-02000, 00936, 30665.
- **T-SQL odds** (S9, S21). `||=` (2025) and the compound assignments UPDATE ... SET lacked (`lexdb_parse.tsqlCompound`,
  `tsqlAssign`, in `setList` and lexdb_tsqlparse's SET @v); `^` is XOR in the door (it was PostgreSQL's power). 2022's
  BIT_COUNT, LEFT_SHIFT, RIGHT_SHIFT, `<<`, `>>`, GET_BIT, SET_BIT in lexdb_tsqlfn (`tbit`: as wide as the value's type,
  from the binder's hint of the arguments' types, `isTypedFn`), with 8116, 9838, 9839, 174. APPROX_PERCENTILE_CONT /
  _DISC are lexdb_pct's T-SQL percentiles as aggregates (exact; SQL Server's estimate is exact on the sizes tried), 4113
  with OVER, 10754 without WITHIN GROUP.
- **Met on the way** (a regression of 91781b58): a select item of integer arithmetic was named after the overflow cast
  resolve puts on it (`a + a` was `int4` in the PostgreSQL door, `?column?` in PostgreSQL): `lexdb_bind.exprName` skips
  that cast.

Tests, each statement with batches off and on: `tns_retold` (37 calls with out binds, a new `@n` kind of
`gen_oracle.py`'s consts tests: 0 differences against Oracle Free 23.26.3) and `tns_stmtforms` (78 statements,
`gen_oracle.py --check`: 0 differences); `exec_retold` (50 statements) and `exec_stmtforms` (21), PostgreSQL 18
(`gen_pg.py`'s NAMED suites, with a new `@tx` line: in a transaction rolled back each time); `tds_stmtforms` (41
batches, SQL Server 2025, `gen_mssql.py --port 14331 --container lxl-mssql25 stmtforms`). Suite 319 of 319.

### 8.2 Cost

Measured on the branch's last commit (b12fa897) against main `a89a203e`, both `-O`.

- In process (`LXL_HASH_SEED=1`, 20,000 statements less the setup, two rounds alternated, equal in both): point select
  123,983.3 -> 123,966.3 instructions, INSERT 55,118,190.6 -> 55,118,174.7, UPDATE by key 55,138,484.2 -> 55,138,480.2.
  The first build was above main (select +15, INSERT +72, UPDATE +44): T-SQL's `^` tested in PostgreSQL's operator
  loops (now lexed as `#` in the T-SQL door), INSERT's parse split in two functions (a Stmt handed by value), RETURNING's
  list in `returning` itself, an Upsert field; d39d41c8 took them out.
- Over the wire (`icount6.sh`, 3 x points.sql, base and branch alternated twice), per statement: instructions 173,092 /
  173,085 -> 173,056 / 173,075; cycles 95,662 / 95,643 -> 94,893 / 94,707; L1 i-cache misses 309 / 310 -> 360 / 358;
  branch misses 379 / 386 -> 366 / 364. Before b12fa897 the instructions were as equal and the cycles 4-5% up (branch
  misses +15%, spread over unrelated functions): placement, found by building subsets of the change (lexdb_orafn's two
  additions at the head of `call` and `resultOid`); 160 KB of padding put into main's parser moved nothing.
- TPC-H SF1 (`run.sh`, lexdb only, base and branch alternated twice, the best of each side): checksums equal on all 22;
  total 8,834 -> 8,836 ms. Above 1.5%: q15 357.2 -> 371.1 (base's runs 357.2 / 378.7), q20 243.0 -> 250.6, q21 690.7 ->
  704.2; their server instructions equal (q15 2,638.6M -> 2,638.3M, q20 1,640.20M -> 1,640.22M, q21 6,961.2M ->
  6,953.9M): noise and placement.
- lexdb_exec: 20,464 -> 20,529 lines (RETURNING's settling and stars, `keptRet`, `groupKeys`, `onNullFill`); the rest in
  the new lexdb_oldnew (179 lines), lexdb_parse, lexdb_bind and lexdb_tsqlfn.

### 8.3 Left

- PostgreSQL's whole-row `RETURNING old` / `new` (a composite: lexdb has no row values as columns) and old/new inside a
  subquery of RETURNING (`(SELECT old.a)`: the rewrite does not enter subqueries; 42P01).
- The new value of a DEFAULT ON NULL FOR INSERT AND UPDATE column set to NULL by an UPDATE is the default in the row
  written but NULL in that UPDATE's RETURNING (the default is given where the row is checked, after RETURNING's row is
  made).
- Oracle's `INSERT ... SET (c, d) = (subquery)` and BY NAME of a query with `*` (0A000); a later UNION branch of BY NAME
  is checked only for names the first has; `NOT NULL DEFAULT ON NULL` (ORA-03076) and `WHERE x IN (VALUES ...)`
  (ORA-63813) are accepted or refused otherwise.
- SQL Server's varchar(n) variable truncated on assignment (`SET @s ||= 'efgh'` of a varchar(5) is `abcde`): lexdb
  refuses the value (2628) for `=` too; the bit functions of a `0x..` literal (an int in lexdb's door, lexdb-tds.md 13);
  tinyint's width (lexdb's smallint: `LEFT_SHIFT(CAST(1 AS tinyint), 9)` is 512, SQL Server's 0).
- Met while testing: lexdb's Oracle door finds a quoted lower-case name's upper-case column (`"a"` finds A; Oracle
  ORA-00904), and has no aggregate RETURNING (`RETURNING SUM(OLD a) INTO`, ORA-00979; Oracle's single-set aggregate).

### 8.4 Plan: PostgreSQL 18's NOT NULL constraints in the catalogs (P7, about a day)

PostgreSQL 18 keeps every NOT NULL as a constraint: pg_constraint has a row of contype `n` for each NOT NULL column (its
name the one given, else `table_column_not_null`, conkey the column), information_schema.table_constraints and
check_constraints list them (as CHECK, `c IS NOT NULL`), psql's `\d+` shows them, and ALTER TABLE ... DROP CONSTRAINT n /
RENAME CONSTRAINT act on them (DROP is DROP NOT NULL). What it takes: (a) the names given kept per table (a new
`Table.nnNames` of "column\x00name" for the names that are not the default, encoded in the catalog after the checks;
CREATE TABLE, ADD, column-level `CONSTRAINT n NOT NULL`, RENAME COLUMN and RENAME TABLE keeping them, DROP NOT NULL and
DROP COLUMN dropping them); (b) the `n` rows in lexdb_pgcat's pg_constraint with their oids (after the others', so
existing oids do not move), pg_get_constraintdef's `NOT NULL c`, the information_schema rows; (c) DROP / RENAME
CONSTRAINT finding them; (d) the tests that read pg_constraint without a contype filter (exec_catalog, exec_keyless and
tds_vscode's) checked again against PostgreSQL 18. No row path is touched: NOT NULL is checked as now.

## 9. The missing functions and aggregates (as built)

Branch from main `c50e071d`, commits `f8c07339`, `271ca36e` and `ed4b68b2` (the cost, 9.2): section 6.1's items 6 (scalar
functions) and 7 (aggregates), each checked again against the product first (the containers of the header; PostgreSQL's
answers from the `lxl-pg19` container, PostgreSQL 19.0, since base64url is 19's) and built in every door that has it, under
its own name, types and errors. Rows above say *works (f8c07339)* or *works (271ca36e)*.

### 9.1 What changed, where

- **One module for the functions**, `lexdb_newfn` (core; 1,514 lines): `lexdb_lib.entryOf` finds its entries after its own
  (the hook is the last thing before a miss is counted), `lexdb_bind.exprOid` its types (`resultOid`, before the dialects'
  typing), so the calls lexdb had pay nothing. The PostgreSQL door calls them by PostgreSQL's names; the T-SQL door's
  `tsqlCall` and the Oracle door's `oraCall` name them `#n_t...` and `#n_o...` at the end of their chains (lexdb_parse
  `tsqlNewCall`, `oraNewCall`), so knownCall knows them and no dispatch of the dialect modules grew. A T-SQL call gets its
  arguments' types after them (`lexdb_bind.newCall`: oid, prec, scale), for SQL Server's errors by type (8116, 9810) and
  DATETRUNC's precision.
- **Date buckets** (S13, O12, P23's date_bin): one kernel (`bucketOf`: whole months counted from the origin's day and time,
  else a fixed width, floor division either side of the origin). T-SQL's DATE_BUCKET(part, n, d [, origin]) of every date
  and time type (1900-01-01 the origin; months from the origin's day: 03-30 from 01-31 is 02-29), 8116 for a string, an int,
  NULL or an origin of another type, 9810 for a part the type has not (and dayofyear, microsecond), 9834 for n <= 0;
  Oracle's TIME_BUCKET(datetime, stride, origin [, START | END]) with an INTERVAL or an ISO 8601 stride ('PT15M'), ORA-03403
  for an origin of the other type (DATE / TIMESTAMP, the binder's oraStamp), 01867 for a negative or mixed stride, 03404 below
  a second; PostgreSQL's date_bin (0A000 with months, 22008 for a stride <= 0, infinity kept, an untyped source a
  timestamptz).
- **DATETRUNC** (S14): each part, week from Sunday (DATEFIRST 7), iso_week from Monday, the type kept (a string a
  datetime2(7)), 9810 for a part below the type's precision (microsecond of a datetime2(3), millisecond of a smalldatetime)
  or above it (an hour of a date, a day of a time); the output type by `lexdb_exec.newScale` (DATEADD's rule, in its own
  function: in exprScale it cost the point select 8 instructions).
- **UUIDs** (P8, O14): uuidv4(), uuidv7([shift]) (the clock's milliseconds and 12 bits of the sub-millisecond, rising within
  the process as PostgreSQL's within a backend), uuid_extract_version (NULL for another variant), uuid_extract_timestamp (of
  versions 1 and 7); Oracle 26ai's UUID() (a version 4 RAW(16)), IS_UUID (32 digits, or 36 with the hyphens), RAW_TO_UUID,
  UUID_TO_RAW (as loose as Oracle's: the hyphens dropped, fewer digits the low ones; ORA-62432). Volatile for the planner
  (`lexdb_bind.newVolatile`).
- **BASE64** (S7, P15): BASE64_ENCODE(varbinary [, url_safe]) (url-safe: `-_`, no padding) and BASE64_DECODE (either
  alphabet, blanks skipped, padding optional but whole; 9803; 8116 for a varchar to encode or a varbinary to decode);
  PostgreSQL 19's encode/decode 'base64url' (no padding, `=` 22023, either alphabet in) and 'base32hex' (padded; decode
  either case, padding optional), in `lexdb_lib.encodeBytes`'s and `decodeBytes`'s ends.
- **UNISTR** (S16, O27, P23): one escape reader (`unistr`) with each door's escapes and errors: `\XXXX` and `\\` everywhere,
  `\+XXXXXX` in T-SQL and PostgreSQL, `\uXXXX`, `\UXXXXXXXX` in PostgreSQL, a surrogate pair one character; T-SQL's other
  escape character (9842, 9843) and 9841, Oracle's ORA-30186 (no `\+`), PostgreSQL's 42601 and 22023 past U+10FFFF.
- **Fuzzy matching** (S17, O28): T-SQL 2025's EDIT_DISTANCE (the optimal string alignment distance: SQL Server's martha /
  marhta is 1; its maximum, max + 1 past it), EDIT_DISTANCE_SIMILARITY (rounded), JARO_WINKLER_DISTANCE (a float),
  JARO_WINKLER_SIMILARITY, under their arguments' collation (the binder: 9847 under an SQL_ one, which is the door's default; a
  case-insensitive one's arguments folded); Oracle's UTL_MATCH.EDIT_DISTANCE (Levenshtein's; -1 with a NULL, which '' is),
  EDIT_DISTANCE_SIMILARITY (100 less the share, cut: 58 where SQL Server says 57), JARO_WINKLER (the sum times a third, as
  Oracle's last digit: 0.8333333333333333 where SQL Server's is ...334), JARO_WINKLER_SIMILARITY (cut).
- **Oracle's TO_BOOLEAN** (O4): the texts true/false, yes/no, on/off, t/f, y/n, 1/0 (blanks and case aside), a number's
  non-zero; ORA-61800.
- **Oracle 26ai's DATEADD, DATEDIFF, TIMESTAMPDIFF** (O13): T-SQL's kernels under Oracle's rules (the part by its whole name,
  ORA-00904 for `dd` or another; n rounded: 1.5 days is 2; a DATE stays a DATE).
- **Oracle 23ai's CEIL, FLOOR, ROUND of a DATE, a TIMESTAMP and an INTERVAL** (O15): `oraCall` names them `#n_oceil`,
  `#n_ofloor`, `#n_oround` and the binder gives a number's back to lexdb's (ceil, floor, #ora_round); a date-time is made a
  DATE first (the second's fraction dropped), each format's unit as TRUNC's, ROUND's rounding points Oracle's (July 1, the
  16th, noon, 30 minutes, 30 seconds, a quarter's 16th of its second month, half a week); an interval to whole years (a YEAR
  TO MONTH's), days, hours or minutes, halves away from zero; ORA-01821 (CEIL, FLOOR), 01899 (ROUND, intervals).
- **PostgreSQL's smaller ones**: error_on_null (19; 22004), random(min, max) of integers and numerics (17; 22023, the scale
  the larger), casefold (18; lower() as under a libc collation), crc32 and crc32c (18), gamma and lgamma (18) and erf, erfc
  (16) from the C library (22003 for an overflow), to_bin and to_oct (17; a negative one as wide as its type, TYPED_FNS'
  hint), bit_count(bytea) (14), date_add and date_subtract (16, in a zone), trim_array (14; 2202E), array_reverse (18),
  array_shuffle and array_sample (16; 22023); int to bytea (as wide as its type) and bytea to an integer (22003 past its
  width; the binder's `byteaCast` and `intCast` to `#n_intbytes`, `#n_bytes2/4/8`: in coerce it cost the point select 25
  instructions), uuid to and from bytea (19; 22P03; `lexdb_ops.castMore`, on coerce's failing arms only) (P11).
- **Aggregates** (lexdb_agg, the row engine and the pipeline's generic step alike; windows through lexdb_window): T-SQL's
  PRODUCT (`#product`: SQL Server's types, an int's an int, 8115 past 2^31 at the row it happens, `#product4`; a decimal's
  decimal(38, 6), each product rounded to six places, `#product6`; float, bigint; a varchar 8117; DISTINCT, OVER);
  PostgreSQL's bit_and, bit_or, bit_xor (integers; 42883 for another type) and Oracle's BIT_AND_AGG, BIT_OR_AGG, BIT_XOR_AGG
  (the same accumulators marked " dia:o": a NUMBER cut toward zero, 0 over no rows, ORA-00932 for a date); any_value
  (PostgreSQL 16, Oracle 21c: the first value not NULL); Oracle's BOOLEAN_AND_AGG / BOOLEAN_OR_AGG (bool_and, bool_or);
  KURTOSIS_POP / _SAMP and SKEWNESS_POP / _SAMP (`#kurtosis_...`: the moments about the mean, the sample's adjustments, 0 below
  four values (three for the skewness) or for equal values, as Oracle; computed in doubles). Oracle's AVG of a YEAR TO MONTH
  interval is whole months cut toward zero (7.3's leftover: the parser marks Oracle's AVG " dia:o", lexdb_pct's dialect mark).
- **Met on the way**: Oracle's `INTERVAL '1 12' DAY TO HOUR` was a day and 12 seconds (the hours read as PostgreSQL reads a
  bare number), and `INTERVAL '30:15' MINUTE TO SECOND` 30 hours 15 minutes; both as Oracle's now (lexdb_parse, the typed
  literal's DAY TO HOUR and MINUTE TO SECOND).

Tests, each statement with batches off and on: `tds_newfn` (90 batches, SQL Server 2025, `gen_mssql.py --port 14331
--container lxl-mssql25 newfn`), `exec_newfn` (78 statements, PostgreSQL 19, `gen_pg.py`'s NAMED mode against `lxl-pg19`),
`tns_newfn` (67 statements, Oracle Free 23.26.3, `gen_oracle.py --check tns_newfn`: 0 differences). Suite 322 of 322.

### 9.2 Cost

Measured on the branch's last code commit (ed4b68b2) against main `c50e071d`, both `-O`.

- In process (`LXL_HASH_SEED=1`, 20,000 statements less the setup, two rounds alternated, equal in both): point select
  123,966.3 -> 123,966.3 instructions, INSERT 55,118,174.5 / 174.6 -> 55,118,174.6, UPDATE by key 55,138,480.2 ->
  55,138,480.2. Two builds on the way were above main, each found by building the branch with one file of the base and then
  with parts of the change: DATE_BUCKET's and DATETRUNC's lines in `lexdb_exec.exprScale` (+8 for the point select, though
  no call reaches them: now `newScale`, its own function) and the bytea-to-integer cast in `lexdb_ops.coerce` (+25, in the
  integer arm or at the end alike: now the binder's `intCast`, only for an explicit cast to an integer).
- Over the wire (`icount6.sh`, 3 x points.sql, base and branch alternated three times), per statement: instructions
  173,348 / 173,005 / 172,958 -> 173,078 / 172,997 / 173,172; cycles 94,996 / 95,277 / 96,800 -> 95,945 / 95,600 / 96,535;
  L1 i-cache misses 306 / 308 / 334 -> 287 / 287 / 372; branch misses 366 / 369 / 367 -> 363 / 362 / 355: within the runs'
  spread, either way.
- TPC-H SF1 (`run.sh`, lexdb only, base and branch alternated twice, the best of each side): checksums equal on all 22;
  total 8,834 -> 8,845 ms. Above 1.5%: q12 440.5 -> 447.7 (base's runs 440.5 / 455.5); its server instructions are equal
  (4,097.68M / 4,097.68M against 4,097.69M / 4,097.68M), as q16's (2,044.2M / 2,040.6M against 2,040.7M / 2,040.0M) and
  q19's (180.22M against 180.25M): noise and placement.
- lexdb_exec: 20,529 -> 20,540 lines (`newScale`, the volatile check); the rest in the new lexdb_newfn (1,514 lines), and
  in lexdb_agg, lexdb_bind and lexdb_parse (each new part at the end of its chain or file).

### 9.3 Left

- Not built: Oracle's CHECKSUM (O17: the hash of each value is Oracle's own, undocumented; 6 and 6 give 0, 6 alone 290064);
  PostgreSQL's array_sort (P9: lexdb-gaps.md 2.1, its order the collation's), named arguments of regexp_* (P13: their
  defaults differ by overload; namedArgs would need a table per function), random(min, max) of dates and timestamps (19),
  pg_input_is_valid and pg_input_error_info (16: a type named by a string, which the library cannot parse; the error_info's
  composite). Plan: CHECKSUM needs Oracle's value hash (ORA_HASH's is not it: `checksum(x)` of 6 and 3 is not the xor or sum of
  their ORA_HASHes); P13 a parameter table in `lexdb_parse.paramsOf` with each function's defaults, the overload chosen by the
  names given; pg_input_is_valid a parse-time rewrite in the PostgreSQL door when the type is a literal (`#n_valid(x,
  CAST(NULL AS t))`, a cast tried), error_info after composites.
- Literals in the T-SQL door are nvarchar (N'..' and '..' are one token kind), so SQL Server's errors that tell varchar from
  nvarchar are not given for a literal: UNISTR('\00e9') (9844: a varchar needs a UTF-8 collation), BASE64_DECODE(N'..')
  (8116), EDIT_DISTANCE of a varchar and an nvarchar (8116); a column's or a cast's type is told. Columns of two Windows
  collations of the same kind (CI and CI) do not conflict in lexdb's collation rules (SQL Server's 468 for EDIT_DISTANCE(a, c)).
- lexdb keeps microseconds, so a datetime2(7)'s seventh digit is rounded away before DATE_BUCKET or DATETRUNC sees it
  (DATETRUNC(microsecond, ...1234567) is ...1234570 where SQL Server's is ...1234560); a datetimeoffset's offset is the
  session's (lexdb's Tstz), so DATE_BUCKET and DATETRUNC of one give its instant in the session's zone, not its own offset.
- Met while testing, not changed: Oracle's LENGTH of a RAW is its hex digits' (32 for a UUID), lexdb's its bytes' (16);
  lexdb's Oracle AVG of a NUMBER has a double's digits where Oracle's has 38; in the Oracle door `insert into t (id, d) select n, date
  '2024-03-05' + n / 97 from ...` (a DATE column) ends the process ("decimal result is not exactly representable": a panic,
  not an error; the same expression in a SELECT works); PostgreSQL's `pg_typeof(agg(x))` is
  evaluated as a constant per row (no aggregation); T-SQL's CAST(varbinary AS varchar) gives the hex text, not the bytes;
  T-SQL LEN of an emoji is 2 in SQL Server (UTF-16 units), 1 in lexdb.
