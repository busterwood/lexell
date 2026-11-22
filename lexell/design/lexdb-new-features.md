# lexdb: the newest releases' SQL against the three doors

Status: audit, 2026-11-22, on main `30a02b82` (after recursion in the doors, lexdb-dialect-gaps.md section 10). No
lexdb code was changed; the branch adds this note and one test (`tds_distinct`, section 5). The order at the end
(section 6) is a proposal; the choices in it are the user's.

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
| P2 | `RETURNING old.x, new.x, old.*, new.*` and `RETURNING WITH (OLD AS o, NEW AS n)` for INSERT, UPDATE, DELETE, ON CONFLICT DO UPDATE, MERGE (P18) | INSERT's old NULL, DELETE's new NULL; MERGE RETURNING with `merge_action()` and old/new | 42P01 `missing FROM-clause entry for table "old"` | missing | S: the T-SQL door's `OUTPUT deleted.`/`inserted.` rewrite (`lexdb_parse.outputRefs` onto `#old`) is the same thing; add the qualifiers, stars and aliases | Oracle 23ai `RETURNING OLD c, NEW c INTO` (O19); T-SQL has OUTPUT (works) | lexdb_parse, RETURNING of upsert/MERGE |
| P3 | `PRIMARY KEY / UNIQUE (k, r WITHOUT OVERLAPS)`, `FOREIGN KEY (k, PERIOD r) REFERENCES t (k, PERIOD r)` (P18) | needs a range column (and btree_gist for scalar parts); 23P01 for an overlap, 23503 for a range the referenced rows do not cover | 42601 at `without`; range types do not exist (`daterange`: 42704) | missing | L: range types first, then the constraint (section 6.3) | none (Oracle's PERIOD FOR has no such key; SQL Server's temporal tables are system-versioned) | new lexdb_range, catalog, write path |
| P4 | `WAIT FOR LSN 'lsn' [WITH (MODE 'standby_replay\|standby_write\|standby_flush\|primary_flush', TIMEOUT '...', NO_THROW)]` (P19) | on a primary: `recovery is not in progress` (55000) for the standby modes | 42601 at `wait` | missing | M, with the replica work (the user's order): a replica's replayed position and a wait on it | none | lexdb_repl, lexdb_wire |
| P5 | `lag/lead/first_value/last_value/nth_value(...) IGNORE NULLS \| RESPECT NULLS OVER (...)` (P19) | NULLs skipped in the frame (lag/lead: in the offset) | 42601 at `nulls` | missing | M: the frame walk in both the row path and the pipeline window (lexdb_window) | SQL Server 2022 (FIRST_VALUE, LAST_VALUE, LAG, LEAD: S15), Oracle (`f(x IGNORE NULLS)` and `f(x) IGNORE NULLS`: O25) | lexdb_parse, lexdb_window |
| P6 | `CHECK (...) NOT ENFORCED`, `REFERENCES ... NOT ENFORCED` (P18); `ALTER TABLE ... ALTER CONSTRAINT c [NOT] ENFORCED` for CHECK (P19) | rows not checked while not enforced; ENFORCED rechecks (23514 "is violated by some row") | 42601 at `not`; ALTER CONSTRAINT: lexdb's ALTER COLUMN message | missing | M: a flag on the constraint, the write path skipping it, ALTER rechecking | Oracle `CHECK (...) DISABLE`, `ENABLE NOVALIDATE` (O26); SQL Server `WITH NOCHECK`, `NOCHECK CONSTRAINT` (S22) | lexdb_parse `checkTail`, lexdb_catalog, the write path |
| P7 | `CONSTRAINT n NOT NULL col` as a table constraint (P18) | a named NOT NULL | 42601 at `not` | missing | S | none | lexdb_parse |
| P8 | `uuidv7([shift interval])`, `uuidv4()` (P18); `uuid_extract_version`, `uuid_extract_timestamp` (P17) | | 42883 | missing | S | Oracle `UUID()`, `IS_UUID()` (O14); T-SQL NEWID (works) | lexdb_lib |
| P9 | `casefold`, `array_sort`, `array_reverse`, `crc32`, `crc32c`, `gamma`, `lgamma` (P18) | | 42883 (`array_sort`: lexdb-gaps.md 2.1) | missing | S (together) | none | lexdb_lib, lexdb_func |
| P10 | `reverse(bytea)` (P18) | `\x0102` gives `\x0201` | `2010x\`: the bytea's text reversed | wrong answer | S | none | lexdb_lib |
| P11 | int <-> bytea casts (P18), uuid <-> bytea (P19) | `258::bytea` = `\x00000102` | 42846 cannot cast | missing | S | none | lexdb_ops casts |
| P12 | `to_number(text, 'RN')` Roman numerals (P18) | 1994 | 22P02 `invalid input syntax for type numeric: " "` | wrong error | S | Oracle `TO_NUMBER` has no RN (TO_CHAR has) | lexdb_func |
| P13 | named arguments of `regexp_*` (`pattern =>`, P18) | | `function regexp_replace does not accept named arguments` | missing | S | none | lexdb_lib, lexdb_bind |
| P14 | `error_on_null(x)` (P19); `random(min, max)` for integers and numerics (P17), dates and timestamps (P19) | | 42883 | missing | S | none | lexdb_lib |
| P15 | `encode/decode(..., 'base64url' \| 'base32hex')` (P19) | `Af8` | 22023 unrecognized encoding | missing | S | T-SQL `BASE64_ENCODE(x, 1)` url-safe (S7) | lexdb_lib |
| P16 | `COPY ... TO (FORMAT json [, FORCE_ARRAY])` (P19); `ON_ERROR ignore \| set_null`, `REJECT_LIMIT` (P17-19) | one JSON object a line | `COPY format "json" not recognized`; `COPY's option "on_error" is not supported` | missing | M (JSON output is small; ON_ERROR needs the per-row error path of COPY FROM) | none | lexdb COPY (lexdb_exec, lexdb_wire) |
| P17 | json/jsonb, IS JSON, JSON_TABLE, JSON_VALUE/QUERY/EXISTS (P17), JSON_OBJECT/ARRAY/ARRAYAGG/OBJECTAGG (P16), `json_array()` of no rows `[]` (P19), jsonpath string methods (P19), `json_strip_nulls(.., true)` (P18) | | only `json_build_object` exists (lexdb-gaps.md 2.1) | missing | L (section 6.3) | SQL Server (S10), Oracle (O29) | new lexdb_json |
| P18 | virtual generated columns, the default kind (P18); `SET EXPRESSION` of a virtual column with a CHECK (P19) | | as PostgreSQL | works | | | |
| P19 | `MIN/MAX` of arrays (P18); `MERGE ... WHEN NOT MATCHED BY SOURCE ... RETURNING merge_action()` (P17); `GRANT ... GRANTED BY` (P19) | | as PostgreSQL (MERGE RETURNING's rows come in another order without ORDER BY) | works | | | |
| P20 | `EXTRACT(WEEK FROM ...)` (P18 lists it) | column named `extract` (since P14) | value right, column named `date_part` | wrong answer | S | | lexdb_bind `exprName` |
| P21 | `x IS DISTINCT FROM y` in a select list | column named `?column?` | column named `distinct` (the `IS NOT` form is right) | wrong answer | S: `"distinct from"` among `exprName`'s `?column?` calls | | lexdb_bind `exprName` |
| P22 | `0x1F`, `0o17`, `0b101`, `1_000` (P16) | 31, 15, 5, 1000 | `select 0x1F` gives 0 (read as `0 AS x1F`, PostgreSQL 15's reading); `'1_000'::int` 22P02 | wrong answer | S | T-SQL `0x..` is binary (works) | lexdb lexer |
| P23 | met on the way, older: `CREATE DOMAIN` (lexdb-gaps.md 2.2), `WITH v (x) AS (VALUES ...)`, `bit_and`/`bit_or` aggregates, `any_value` (P16), `date_bin` (P14), `unistr` (P14), `date_add`/`date_subtract` (P16), `trim_array` (P14), `array_shuffle`/`array_sample` (P16), `bit_count` (P14), `erf`/`erfc` (P16), `pg_input_is_valid`/`pg_input_error_info` (P16), `to_bin`/`to_oct` (P17) | | 42883, 42601 (`values`), 0A000 (CREATE DOMAIN) | missing | S each but CREATE DOMAIN (L, with O11) | `unistr`: S6/O27; `date_bin`: S13/O12; `any_value`: O18; `bit_and`: O17; domains: O11 | lexdb_lib, lexdb_agg, lexdb_parse |

## 2. SQL Server 2025 (compatibility level 170) and 2022

Checked on 2025 RTM-CU10 at level 170 unless marked 2022.

| # | Feature | SQL Server's behaviour | lexdb (TDS door) | Class | Size | Other doors natively | Modules |
|---|---|---|---|---|---|---|---|
| S1 | `REGEXP_LIKE(s, p [, flags])` | a predicate only: in a select list 156; bad pattern 19308 (`Missing ')' in the Pattern`); flags c, i, s, m only (19303 for others) | right in WHERE and CASE; a bit in a select list; bad pattern 50000; flag `q` accepted (PostgreSQL's) | wrong error | M, with S2-S6 as one T-SQL REGEXP slice (section 6.2) | PostgreSQL `regexp_like` (P15, works), Oracle `REGEXP_LIKE` (works) | lexdb_parse `tsqlCall`, lexdb_tsqlfn |
| S2 | `REGEXP_REPLACE(s, p, r [, start [, occurrence [, flags]]])` | occurrence 0 (all) by default: `a#b#c` | PostgreSQL's default (first only): `a#b22c`; with start and occurrence right; `\1` right | wrong answer | (S1) | PostgreSQL, Oracle (Oracle's default is all: its door already adds `g`) | (S1) |
| S3 | `REGEXP_SUBSTR`, `REGEXP_INSTR`, `REGEXP_COUNT` | occurrence, return option, flags, group | as SQL Server for every case tried | works | | PostgreSQL, Oracle | |
| S4 | `REGEXP_MATCHES(s, p [, flags])` (table) | columns `match_id, start_position, end_position, match_value, substring_matches` (JSON) | PostgreSQL's: one `text[]` column | wrong answer | (S1); substring_matches needs JSON text only | PostgreSQL `regexp_matches` (other shape) | lexdb_srf |
| S5 | `REGEXP_SPLIT_TO_TABLE(s, p [, flags])` | columns `value, ordinal` | one column named `regexp_split_to_table` | wrong answer | (S1) | PostgreSQL (one column, works there) | lexdb_srf |
| S6 | the flags' meaning | RE2's (SQL Server's engine): `.` does not match a newline unless `s`; `^`/`$` at lines only with `m` | the PostgreSQL door's mapping (`(?s)` by default) | wrong answer (not run on data with a newline: CHAR() is missing, S21) | (S1) | | lexdb_func `reFlags` |
| S7 | `BASE64_ENCODE(varbinary [, url_safe])`, `BASE64_DECODE(varchar)` | `AQL/`, `AQL_`; 9803 for bad input | 195 | missing | S | PostgreSQL `encode(.., 'base64')` and 19's base64url (P15) | lexdb_tsqlfn |
| S8 | `||` string concatenation | `'a' \|\| 1` = `'a1'`, NULL propagates; `1 \|\| 2` 402 | strings right; `1 \|\| 2` gives `'12'` | wrong error | S | PostgreSQL, Oracle (works) | lexdb_parse/lexdb_bind |
| S9 | `||=` compound assignment | `SET @s \|\|= 'b'` | 102 | missing | S | none | lexdb_tsqlparse |
| S10 | `json` type, `JSON_ARRAYAGG`, `JSON_OBJECTAGG(k : v)`, `JSON_CONTAINS`, `@j.modify(path, v)`; 2022's `JSON_OBJECT`, `JSON_ARRAY`, `JSON_PATH_EXISTS`, `ISJSON(x, type)`; 2016's `ISJSON`, `JSON_VALUE`, `JSON_QUERY`, `JSON_MODIFY`, `OPENJSON`, `FOR JSON` | `JSON_CONTAINS` takes the json type only (8116 for varchar); empty `JSON_ARRAYAGG` NULL | 195 / 2715 / 102 / 208 for every one | missing | L (section 6.3) | PostgreSQL (P17), Oracle (O29) | new lexdb_json, lexdb_tds (2025's json TDS type) |
| S11 | `vector(n [, float16])`, `VECTOR_DISTANCE('cosine'\|'euclidean'\|'dot', a, b)`, `VECTOR_NORM`, `VECTOR_NORMALIZE`, `VECTORPROPERTY`; `VECTOR_SEARCH` and vector indexes (PREVIEW_FEATURES) | shown as a JSON array `[1.0000000e+000,...]` | 102 | missing | L, note only (section 6.3) | Oracle `VECTOR` (O30); PostgreSQL only through pgvector (not native) | |
| S12 | `PRODUCT(x)` aggregate, also `DISTINCT` and `OVER (...)` | 24; 8115 for an int overflow; NULL for no rows | 195 (and no row at all for an empty input: S23) | missing | S: an accumulator in lexdb_agg (row path and pipeline share it), the window form | none | lexdb_agg, lexdb_bind |
| S13 | `DATE_BUCKET(part, n, d [, origin])` (2022) | `2020-01-06` for week 1 of `2020-01-08` | 207 (the part read as a column) | missing | S: one kernel, three spellings | PostgreSQL `date_bin` (P23), Oracle `TIME_BUCKET` (O12) | lexdb_time, lexdb_parse `tsqlCall` |
| S14 | `DATETRUNC(part, d)` (2022) | | 207 | missing | S | PostgreSQL `date_trunc`, Oracle `TRUNC(d, fmt)` (both work) | lexdb_parse `tsqlCall` |
| S15 | `FIRST_VALUE/LAST_VALUE/LAG/LEAD(x) IGNORE NULLS OVER (...)` (2022) | | 102 at `nulls` | missing | (P5) | PostgreSQL 19 (P5), Oracle (O25) | lexdb_window |
| S16 | `UNISTR(s [, escape])` | `\00e9`, `\+01F600`, another escape character; a varchar input needs a UTF-8 collation (9844) | 195 | missing | S: one function, three spellings | PostgreSQL `unistr` (P23), Oracle `UNISTR` (O27) | lexdb_func, lexdb_tsqlfn |
| S17 | `EDIT_DISTANCE(a, b [, max])`, `EDIT_DISTANCE_SIMILARITY`, `JARO_WINKLER_DISTANCE`, `JARO_WINKLER_SIMILARITY` | 3, 57, 0.0388..., 96 for kitten/sitting and martha/marhta; **9847 under a SQL_ collation**, which is the default (and lexdb's TDS collation, SQL_Latin1_General_CP1_CI_AS): a Windows collation must be named | 195 | missing | S (with the 9847 rule) | Oracle `UTL_MATCH.EDIT_DISTANCE[_SIMILARITY]`, `JARO_WINKLER[_SIMILARITY]` (a package: O28); PostgreSQL only in the fuzzystrmatch extension | lexdb_tsqlfn |
| S18 | `CURRENT_DATE`; `SUBSTRING(s, start)` without length; `DATEADD` with a bigint | | as SQL Server, but `SUBSTRING(NULL, 1)`: 8116 there, NULL here | works / wrong error | | | |
| S19 | `GREATEST`, `LEAST`, `TRIM/LTRIM/RTRIM(s, chars)`, `WINDOW` clause, `IS [NOT] DISTINCT FROM` (2022) | | as SQL Server (IS DISTINCT FROM: section 5) | works | | | |
| S20 | `GENERATE_SERIES` (2022), `STRING_SPLIT(s, sep, 1)` with the ordinal (2022) | columns `value` and `value, ordinal` | rows right, column `generate_series`; STRING_SPLIT 208 (missing in any form) | wrong answer / missing | S | | lexdb_srf, lexdb_parse |
| S21 | 2022's `APPROX_PERCENTILE_CONT/DISC`, `BIT_COUNT`, `LEFT_SHIFT`, `RIGHT_SHIFT`, `GET_BIT`, `SET_BIT`; and older ones met on the way: `CHAR()`, `NCHAR()`, `FORMAT(n, 'N2')` | `FORMAT(1234.5, 'N2')` = `1,234.50` | 195; FORMAT gives `1234.5` | missing / wrong answer (FORMAT) | S each | PostgreSQL `bit_count` (P23), `chr` | lexdb_tsqlfn |
| S22 | constraint checking off: `WITH NOCHECK`, `ALTER TABLE t NOCHECK CONSTRAINT c\|ALL` | | 50000 (ALTER TABLE takes ...) | missing | (P6) | PostgreSQL NOT ENFORCED (P6), Oracle DISABLE (O26) | |
| S23 | GROUP BY rules (old T-SQL): `GROUP BY ALL a` keeps the groups WHERE removed (count 0); a select alias or a position in GROUP BY is 207 / 164 | `1\|1;2\|0` | `GROUP BY ALL a` is a plain GROUP BY (`1\|1`); alias and position accepted | wrong answer / wrong error | S | Oracle 26ai `GROUP BY ALL` means another thing (O7): the two must not share a parse | lexdb_parse, lexdb_bind |
| S24 | an unknown function over no rows | 195 when the batch is compiled | no error, no row: functions are looked up when called, so `SELECT product(x) ... WHERE 1 = 0` answers an empty set (the PostgreSQL door too: `select nosuchfn(x) ... where false` gives 0 rows where PostgreSQL gives 42883) | wrong error | S, but on the binding path: measure point selects | all doors | lexdb_bind |
| S25 | DATEADD of a string literal | a `datetime` (`2020-01-03 00:00:00.000`) | a `datetime2` (7 digits) | wrong answer | S | | lexdb_tsqlfn |
| S26 | TDS 8.0 strict encryption (`Encrypt=Strict`: TLS before PRELOGIN, ALPN `tds/8.0`) | 2025 supports it for every component | lexdb speaks TDS 7.4 with TLS inside PRELOGIN (not tried with a strict client) | note only | M: the TLS-first path exists for TCPS (lexdb_tns), the handshake order is the work | | lexdb_tds |

## 3. Oracle AI Database 26ai (23.26.3) and 23ai

| # | Feature | Oracle's behaviour | lexdb (TNS door) | Class | Size | Other doors natively | Modules |
|---|---|---|---|---|---|---|---|
| O1 | `QUALIFY cond` (23.26.0) | filters on window results after them; select-list aliases visible (`qualify rn = 1`) | ORA-00900 | missing | M: a filter above the window step; aliases and ORDER BY make it more than a token rewrite | none | lexdb_parse, lexdb_plan |
| O2 | aggregate and window `FILTER (WHERE ...)` (23.26.1) | | as Oracle | works | | PostgreSQL (works) | |
| O3 | `SELECT` without `FROM` | | as Oracle | works | | PostgreSQL, T-SQL | |
| O4 | `BOOLEAN` columns, `TRUE`/`FALSE`, boolean expressions in the select list and WHERE | | as Oracle (types BOOLEAN on the wire); `TO_BOOLEAN`, `BOOLEAN_AND_AGG`, `BOOLEAN_OR_AGG`: ORA-00904 | works / missing (the three functions) | S | PostgreSQL `bool_and`/`bool_or` (work) | lexdb_orafn, lexdb_agg |
| O5 | table value constructor `VALUES (...), (...)` in FROM, INSERT, MERGE USING, WITH | | FROM, INSERT and MERGE right, but `SELECT *` names the columns `x, y` (Oracle `X, Y`) and a literal is VARCHAR2 (Oracle CHAR); in WITH ORA-00900 | wrong answer / missing | S (the names: lexdb-dialect-gaps.md 10 "Left"; WITH: as P23) | PostgreSQL (WITH form missing too), T-SQL (FROM only, works) | lexdb_parse `withList`, FROM binding |
| O6 | `CREATE ... IF NOT EXISTS`, `DROP ... IF EXISTS` | | as Oracle | works | | PostgreSQL, T-SQL DROP | |
| O7 | `GROUP BY ALL` (26ai) | groups by every select item that is not an aggregate | ORA-00900 | missing | S | none (T-SQL's `GROUP BY ALL` is another feature: S23) | lexdb_parse, lexdb_bind |
| O8 | `GROUP BY` alias and position; `HAVING` alias (23ai) | alias works; a position is ORA-03162 unless `ALTER SESSION SET group_by_position_enabled = TRUE` | alias works; a position always groups; the ALTER SESSION is ORA-02248; HAVING alias ORA-00904 | wrong error / missing | S | PostgreSQL (alias and position, works; no HAVING alias) | lexdb_bind, lexdb_tns (session parameter) |
| O9 | direct joins: `UPDATE t SET ... FROM t2 WHERE ...`, `DELETE t FROM t2 WHERE ...` | | UPDATE right; DELETE ORA-00900 | works / missing (DELETE) | S | T-SQL `DELETE t FROM ...` (works), PostgreSQL `DELETE ... USING` (works) | lexdb_parse |
| O10 | `INSERT INTO t SET c = v, ...`, `INSERT INTO t BY NAME SELECT ...` (26ai) | | ORA-00900 | missing | S: a rewrite to a column list | none | lexdb_parse |
| O11 | SQL domains: `CREATE DOMAIN d AS type CONSTRAINT .. CHECK (d > 0)`, domain columns, `DOMAIN_NAME()`, `DOMAIN_DISPLAY()` | ORA-11534 for a violation | ORA-03001 (0A000) | missing | L: a catalog object, its constraints on every write, its display/order expressions, the catalogs | PostgreSQL `CREATE DOMAIN` (P23; lexdb-gaps.md 2.2) | lexdb_catalog, lexdb_parse, the write path |
| O12 | `TIME_BUCKET(d, interval, origin)` (23ai) | `2024-03-05 10:15` for 15 minutes | ORA-00904 | missing | (S13) | T-SQL DATE_BUCKET (S13), PostgreSQL date_bin (P23) | lexdb_orafn |
| O13 | `DATEADD(part, n, d)`, `DATEDIFF(part, a, b)` / `TIMESTAMPDIFF` (26ai) | DATE result; 30 days | ORA-00904 `"DAY"` | missing | S: the T-SQL door's `#dateadd`/`#datediff` with Oracle's types | T-SQL (works) | lexdb_parse `oraCall` |
| O14 | `UUID()`, `IS_UUID()` (26ai) | | ORA-00904 | missing | (P8) | PostgreSQL uuidv7/uuidv4 (P8) | lexdb_orafn |
| O15 | `CEIL/FLOOR/ROUND/TRUNC` of DATE, TIMESTAMP and INTERVAL (23ai) | `CEIL(DATE '2024-03-05', 'MONTH')` = 2024-04-01; `TRUNC(timestamp, 'HH')` is a DATE | CEIL, ROUND(interval): ORA-00904; TRUNC of a timestamp gives a TIMESTAMP | missing / wrong answer (TRUNC's type) | S | | lexdb_orafn |
| O16 | `SUM`/`AVG` of INTERVAL (23ai) | INTERVAL DAY TO SECOND | SUM gives VARCHAR2 `'06:00:00'`; AVG ORA-00904 | wrong answer / missing | S | PostgreSQL (works) | lexdb_agg, lexdb_tns types |
| O17 | `BIT_AND_AGG`, `BIT_OR_AGG`, `BIT_XOR_AGG`, `CHECKSUM`, `KURTOSIS_POP/SAMP`, `SKEWNESS_POP/SAMP` (21c/23ai) | | ORA-00904 | missing | S | PostgreSQL `bit_and`/`bit_or`/`bit_xor` (P23) | lexdb_agg |
| O18 | `ANY_VALUE` (21c) | | ORA-00979 | missing | S | PostgreSQL 16 (P23) | lexdb_agg |
| O19 | `RETURNING OLD c, NEW c INTO :a, :b` for INSERT, UPDATE, DELETE, MERGE (23ai) | INSERT's OLD NULL, DELETE's NEW NULL | ORA-00904 `"OLD"`; plain RETURNING INTO works | missing | (P2) | PostgreSQL 18 (P2), T-SQL OUTPUT (works) | lexdb_parse |
| O20 | `DEFAULT ON NULL [FOR INSERT ONLY \| FOR INSERT AND UPDATE] v` (12c; UPDATE 23ai) | a NULL written becomes the default | ORA-00900 (12c's plain form too) | missing | S | none | lexdb_parse, the write path |
| O21 | annotations: `ANNOTATIONS (name 'value', ...)` on tables and columns, `USER_ANNOTATIONS_USAGE` | | ORA-00900 | missing | M: kept in the catalog, listed in the views | none | lexdb_parse, lexdb_oracat |
| O22 | SQL/PGQ: `CREATE PROPERTY GRAPH`, `GRAPH_TABLE (g MATCH ... WHERE ... COLUMNS (...))`, bounded quantifiers `->{1,2}` | rows as the joins of the pattern; ORA-42421 for an unknown graph | ORA-00900 | missing | L (section 6.3) | none (PostgreSQL 19 has not; SQL Server's MATCH over NODE/EDGE tables is another design) | new lexdb_graph |
| O23 | `CREATE ASSERTION a CHECK (NOT EXISTS (...) \| ALL (...) SATISFY (...))` (23.26.1) | ORA-08601 `Assertion (APP.A1) violated` at the DML; no aggregates (ORA-08689, ORA-00934); `USER_ASSERTIONS` | ORA-00900 | missing | L (section 6.3: a design note) | none | new lexdb_assert |
| O24 | `IS [NOT] DISTINCT FROM` | not Oracle's (ORA-00908, 23.26.3) | accepted (lexdb's extension in this door) | wrong error | S: refuse it when `p.ora` in `lexdb_parse.isTail`; but users may rely on the extension: the user's call | PostgreSQL, T-SQL 2022 | lexdb_parse |
| O25 | `IGNORE NULLS` in `FIRST_VALUE(x IGNORE NULLS)`, `LAST_VALUE`, `LAG(x) IGNORE NULLS`, `LEAD`, `NTH_VALUE` | | ORA-00900 | missing | (P5) | PostgreSQL 19, T-SQL 2022 | lexdb_window |
| O26 | `CONSTRAINT c CHECK (...) DISABLE`, `ENABLE [NO]VALIDATE` | | ORA-00900 | missing | (P6) | PostgreSQL NOT ENFORCED, T-SQL NOCHECK | |
| O27 | `UNISTR('\00e9')` | NVARCHAR2 | ORA-00904 | missing | (S16) | PostgreSQL, T-SQL 2025 | lexdb_orafn |
| O28 | `UTL_MATCH.EDIT_DISTANCE`, `.JARO_WINKLER`; `UTL_ENCODE.BASE64_ENCODE` | 3; `aGk=` | ORA-00904; UTL_ENCODE gives NULL | missing / wrong answer (UTL_ENCODE) | S | T-SQL 2025 (S17, S7) | lexdb_orafn |
| O29 | JSON: the `JSON` type, `JSON_OBJECT('a' : 1)`, `JSON_ARRAY`, `JSON_VALUE ... RETURNING`, `JSON_ARRAYAGG`, `JSON_OBJECTAGG(k VALUE v)`; JSON relational duality views (note only) | | ORA-00900 / ORA-00902 | missing | L (section 6.3) | PostgreSQL (P17), SQL Server (S10) | new lexdb_json, lexdb_tns (type 119) |
| O30 | `VECTOR(n, FLOAT32 \| INT8 \| ...)`, `VECTOR_DISTANCE(a, b, COSINE \| EUCLIDEAN ...)` | | ORA-00904 | missing | L, note only | SQL Server 2025 (S11) | |

Not counted: two 26ai features that 23.26.3 does not have yet, which lexdb already accepts as extensions: `SELECT *, 1 AS one` (ORA-00923 on 23.26.3) and `FETCH FIRST n ROWS ONLY FOR UPDATE` (ORA-02014). `JOIN TO ONE` was refused in the form tried (ORA-03048) and is left out until its syntax is confirmed.

## 4. Counts

A row with two parts (S18, S20, S21, S23; O4, O5, O8, O9, O15, O16, O28) is counted in each part's class, so the
parts add up to more than the rows.

| Product | works | wrong answer | wrong error | missing | parts / rows |
|---|---|---|---|---|---|
| PostgreSQL 19/18 (and older met on the way) | 2 (P18, P19) | 4 (P10, P20, P21, P22) | 1 (P12) | 16 (P1-P9, P11, P13-P17, P23) | 23 / 23 |
| SQL Server 2025/2022 | 3 (S3, S18, S19) | 8 (S2, S4, S5, S6, S20, S21, S23, S25) | 5 (S1, S8, S18, S23, S24) | 13 (S7, S9-S17, S20, S21, S22) | 29 / 25, and S26 (note) |
| Oracle 26ai/23ai | 5 (O2, O3, O4, O6, O9) | 4 (O5, O15, O16, O28) | 2 (O8, O24) | 26 (O1, O4, O5, O7-O23, O25-O30) | 37 / 30 |

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
- in a select list (`SELECT a IS DISTINCT FROM b AS k`): SQL Server 156, lexdb a bit (as REGEXP_LIKE, S1);
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
