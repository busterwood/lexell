# Known issues

Bugs and gaps found while writing and checking these pages (lexdb built from main at 4fba817b, 2026-11-23; the entries
that main ca687450, a15b9a64, 02646472, 436468d8, 81ee25d1, e689d814 and 7b6b1235, 2026-11-24, fixed are removed or
reworded to what is left; the new pages and examples were checked against main 60c08a84; the time zone entries were
reworded after the merge of timestamps that keep their offset, main 178ea2df, and checked against main 55040a20; the
Oracle annotation entry was reworded to what is left after the merge of annotations, main 6c2e83f1; the entries that
the third bug slice fixed, main 84ceec7e, 2026-11-25, are removed or reworded to what is left, checked against it; the
property graph entries are what is left after the merge of SQL/PGQ in the Oracle door, main e7691bd6, 2026-11-25, and
were checked against it and Oracle Free 23.26.3; the entries that the fourth bug slice fixed, main f87d8cf8, 2026-11-25
(a NUMBER foreign key to an identity key, views over dropped functions, units created with compilation errors, the
zone UTC, TO_CHAR of a TIMESTAMP WITH LOCAL TIME ZONE, property graph errors, SQL Server's reserved words as names), are
removed or reworded to what is left, checked against it, Oracle Free 23.26.3 and SQL Server 2022; the assertion
entry is what is left after the merges of CREATE ASSERTION in the Oracle door, main ad2ff242, and in the PostgreSQL and
SQL Server doors with every write path checked, main f23d0ebc, 2026-11-25, checked against main and Oracle Free
23.26.3; the entries that the fifth bug slice fixed, main 30b54d6f, 2026-11-25 (DROP COLUMN of a table views read, the
T-SQL inline INDEX and TOP in DELETE, UPDATE and INSERT, assertion checks run as their owner, stored functions' column
names, T-SQL INFORMATION_SCHEMA's dbo, syntax errors in stored units, ORA-32796, T-SQL parse errors, assertion
leftovers), are removed or reworded to what is left, checked against it, Oracle Free 23.26.3 and SQL Server 2022; the
entries that the sixth bug slice fixed, main f1e0ddf8, 2026-11-25 (Oracle's quoted names, nested subprograms, DROP TABLE
under a view in each door, T-SQL index names per table, INFORMATION_SCHEMA and `sp_refreshview`, schema-bound view
errors, `WITH CHECK OPTION` before `AS`, ORA-00907 before `INTO`), are removed or reworded to what is left, checked
against it, Oracle Free 23.26.3, SQL Server 2022 and PostgreSQL 18; the entries that the seventh bug slice fixed, main
1d5fb7d3, 2026-11-25 (Oracle's overloaded nested subprograms and PLS-00231, `SELECT *` views keeping their columns,
assertions under `NOVALIDATE`, the T-SQL texts as written, DROP INDEX's errors, DOMAINS and COLUMN_PRIVILEGES, schema
owners, PostgreSQL's DROP TABLE DETAIL and SET TRANSACTION READ ONLY), are removed or reworded to what is left, checked
against it, Oracle Free 23.26.3, SQL Server 2022 and PostgreSQL 18).
They are not fixed here: the pages describe what lexdb does. Each "Differences" section of the reference lists the smaller
differences of its statement.

## All doors

- **Replicas and temporary objects** (main f8e3d6d6, design/lexdb.md 9.137 "As built (phase 5)"):
  - SQL Server door: `#temp` tables, `SELECT ... INTO #x` and table variables work on a replica.
  - PostgreSQL door: temporary tables are refused with 25006, as on a hot standby.
  - Oracle door: `CREATE GLOBAL TEMPORARY TABLE` on a replica is ORA-16000, as on a standby, and DML on a global
    temporary table is not available there: Active Data Guard allows it for a table the primary defined, but in
    lexdb no such definition reaches a replica's session (see the Oracle door's entry below).

## PostgreSQL door

- **`inet_server_port()`** and the other `inet_*` functions do not exist (42883).
- **No PL/pgSQL and no `DO`.** Functions and procedures are `LANGUAGE sql` only; another language is 42704
  (`language "plpgsql" does not exist`), and `DO` is a syntax error.
- **Queries** (found writing the SELECT pages):
  - `FROM ONLY t` is `relation "only" does not exist`, and `MERGE INTO ONLY t` a syntax error (`UPDATE ONLY` and
    `DELETE FROM ONLY` work).
  - In a `FULL JOIN ... USING (k)`, a select-list `k` is named `coalesce` (PostgreSQL: `k`; `SELECT *` is right).
  - `ON` after a comma join is not scoped: `FROM a, b JOIN c ON c.x = a.k` is accepted (PostgreSQL: 42P01).
  - Syntax errors (42601) where PostgreSQL has a feature: `ORDER BY x USING >`, `TABLESAMPLE`, `TABLE t`,
    `SELECT;` and `SELECT FROM t`, `ROWS FROM (...)`, column definition lists (`AS g(a int)`),
    `mode() WITHIN GROUP (...)`, PostgreSQL 19's `GROUP BY ALL` without elements.
  - A subquery in `LIMIT` is 0A000.
  - `FOR UPDATE` with `FETCH ... WITH TIES` is 0A000.
  - `json_agg`, `corr`, `regr_slope`, `covar_pop` and the other statistics aggregates do not exist (42883).
- **WITH:**
  - A recursive CTE under `LIMIT`, `FETCH FIRST` or `TOP` stops when a `WHERE`, a join, a left join or a derived table
    filters it (`WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT * FROM r WHERE n % 7 = 0 LIMIT
    3`). It still runs to `max_recursion` (54001) for a join where lexdb's planner reads the other table first
    (`FROM rt JOIN n`), for a subquery in the `WHERE` or the select list, for a `WHERE` that calls `nextval` or
    `random`, and, in the T-SQL door, for a tree recursion (more than one row a round). The Oracle door gives ORA-32044,
    as Oracle does.
  - The recursive term's checks are missing: an aggregate, a window function, `ORDER BY`, or the CTE on the nullable
    side of an outer join is not refused (PostgreSQL: 42P19 or 0A000), and the query runs to 54001.
  - Under `RECURSIVE` a CTE cannot name a later one (`relation "a2" does not exist`).
  - Data-modifying CTEs (`WITH d AS (DELETE ... RETURNING *) ...`) are a syntax error (lexdb-gaps.md 2.2).
  - `WITH ... VALUES` is refused; the message (`WITH must be followed by SELECT, INSERT, UPDATE or DELETE`) also
    leaves out MERGE, which works.
- **UPDATE:** `SET (a, b) = (SELECT ...)` is a syntax error.
- **SELECT ... WAIT:** the refusals still say `lexdb: WAITFOR ...` (the clause is `WAIT n SECONDS`), and the clause
  is taken only by a statement that starts with `SELECT`, not after `WITH`.
- **TRUNCATE:** the foreign key refusal carries its DETAIL and HINT in the message text, and `TRUNCATE ... CASCADE`
  gives no NOTICE naming the tables it adds.
- **Tables** (found writing the DDL pages):
  - `ALTER TABLE | VIEW | SEQUENCE ... OWNER TO postgres` is `role "postgres" does not exist`, though `current_user`
    is `postgres` and `pg_roles` lists it. `OWNER TO` a role made with `CREATE ROLE` works.
  - `COMMENT ON` is a syntax error.
  - Syntax errors where PostgreSQL has a feature: `CREATE TABLE t ()`, `LIKE`, `INHERITS`, `PARTITION BY`,
    `WITH (fillfactor = ...)`, `TABLESPACE`, a column's `PRIMARY KEY INCLUDE (...)` / `DEFERRABLE`,
    `CREATE TABLE ... AS TABLE t` / `AS EXECUTE`, `ALTER COLUMN ... SET STATISTICS`, `ALTER COLUMN ... TYPE ...
    COLLATE`. At table level `INCLUDE`, `WITH`, `USING INDEX TABLESPACE` and `DEFERRABLE` on a key are 0A000.
  - `ALTER COLUMN ... TYPE` without `USING` folds its hint into the message (42804).
  - `DROP ... CASCADE` gives no NOTICE naming what it drops. `DROP TABLE` of a table that views or other tables'
    foreign keys depend on is refused as in PostgreSQL (2BP01, DETAIL and HINT; also when only foreign keys depend on
    it) and `CASCADE` drops them; the DETAIL lists the keys by referencing table first ("constraint fk on table c
    depends on table p"), then the views by name (PostgreSQL: the order they were made). The other 2BP01 refusals
    carry their hints in the message.
- **Constraint states** (`NOT ENFORCED`, `ALTER CONSTRAINT [NOT] ENFORCED`; see [ALTER TABLE](sql/postgresql/alter-table.md)):
  - `ALTER CONSTRAINT ... DEFERRABLE`, `INITIALLY` and `NOT DEFERRABLE` are 0A000 (PostgreSQL takes them for a foreign
    key); only `ENFORCED` and `NOT ENFORCED` are taken.
- **Views:**
  - `ALTER TABLE t DROP COLUMN` is refused only for a column a view uses (2BP01, `CASCADE` drops those views and the
    views over them), as in PostgreSQL. The DETAIL lists the views in lexdb's catalog order (by name; PostgreSQL:
    the order they were made), and `CASCADE` gives no NOTICE. While a view reads table t, `ALTER TABLE t SET SCHEMA` is still
    refused (2BP01, "lexdb keeps a view's text"). The other way round, `ALTER COLUMN ... TYPE` of a column a view
    uses is allowed, where PostgreSQL refuses it (0A000).
  - `pg_get_viewdef`, `pg_views.definition` and `information_schema.views` give the view's text as written (with
    its `;`), not PostgreSQL's rewritten form.
  - `CREATE OR REPLACE VIEW` with columns renamed or reordered says `cannot drop columns from view` (PostgreSQL:
    `cannot change name of view column ...`).
  - `CREATE RECURSIVE VIEW` and `ALTER VIEW v RENAME COLUMN` are syntax errors.
- **Sequences:** `DROP SEQUENCE t` of a table is 42P01 `sequence "t" does not exist` (PostgreSQL: 42809 `"t" is not a
  sequence`).
- **Indexes:**
  - `DROP INDEX t_pkey` is 42704 `index "t_pkey" does not exist`, though `pg_indexes` lists it and `ALTER INDEX
    t_pkey RENAME` works (PostgreSQL: 2BP01, the index belongs to a constraint).
  - `DROP INDEX` takes one name, without `CASCADE` or `RESTRICT`: `DROP INDEX a, b` is a syntax error.
  - `pg_indexes.indexdef` shows an expression index on `(n + 1)` as `(((n + 1)))` (PostgreSQL: `((n + 1))`).
  - `INCLUDE (...)`, `WITH (...)`, `NULLS NOT DISTINCT` and `TABLESPACE` are syntax errors; methods other than
    btree are 0A000; `CONCURRENTLY` is accepted and changes nothing.
- **Transactions** (found writing the transaction pages):
  - `BEGIN` ignores words it does not know: `BEGIN nonsense words here` starts a block (PostgreSQL: 42601).
  - `SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY` / `READ WRITE` are accepted and do nothing (`SHOW
    default_transaction_read_only` stays `off`, and writes go on). `SET TRANSACTION` outside a block gives no WARNING
    (PostgreSQL: `can only be used in transaction blocks`).
  - The default isolation level is `serializable` (PostgreSQL: `read committed`); `READ COMMITTED` is opt-in
    (`BEGIN ISOLATION LEVEL`, `SET TRANSACTION`, `SET default_transaction_isolation`). `READ UNCOMMITTED` shows as
    `read committed` and `REPEATABLE READ` as `serializable` in `SHOW transaction_isolation` (PostgreSQL: their own
    names).
  - No WARNINGs for `BEGIN` inside a block, `COMMIT` or `ROLLBACK` outside one, or `SET CONSTRAINTS` outside one;
    outside a block `SET CONSTRAINTS nosuch DEFERRED` succeeds.
  - `COMMIT AND CHAIN`, `ROLLBACK AND CHAIN` and `PREPARE TRANSACTION` are syntax errors.
- **EXPLAIN:** no options (`EXPLAIN (ANALYZE)`, `(FORMAT JSON)`, `VERBOSE` are syntax errors); `EXPLAIN INSERT`
  and `EXPLAIN ANALYZE` of anything but a `SELECT` are 0A000; the plan is lexdb's own text, not PostgreSQL's node
  tree, so tools that parse PostgreSQL plans cannot read it.
- **Schemas:**
  - `information_schema.schemata.schema_owner` says `postgres` for a schema made `AUTHORIZATION alice`
    (`pg_namespace.nspowner` is right).
  - `CREATE SCHEMA s CREATE TABLE ...` (schema elements) and `DROP SCHEMA a, b` are syntax errors.
  - `DROP SCHEMA public` and `ALTER SCHEMA public RENAME` are 0A000; `DROP SCHEMA pg_catalog` says it does not
    exist.
  - A schema that holds a view, or that a view reads from, cannot be renamed (2BP01, "lexdb keeps a view's text").
  - `search_path` defaults to `public` (PostgreSQL: `"$user", public`).
  - `DROP SCHEMA`'s refusal has no DETAIL or HINT, and `CASCADE` gives no NOTICE.
- **Settings** (found writing the SET, SHOW and DISCARD pages):
  - `pg_settings` has no rows; `SHOW ALL` gives lexdb's own settings only, without `TimeZone`.
  - `SET LOCAL` of lexdb's settings (`statement_timeout` ...) and `SET LOCAL ROLE` do nothing (`SET LOCAL TIME
    ZONE` and custom `a.b` settings work).
  - `is_superuser` is always `on`, also after `SET ROLE` to a plain role.
  - After `RESET myapp.mode`, `SHOW myapp.mode` is 42704 (PostgreSQL shows an empty value).
  - `SET` of a name lexdb does not have (`work_mem`, `application_name`) is accepted and ignored; `SHOW work_mem` is
    then 42704.
  - `DISCARD SEQUENCES` and `DISCARD PLANS` do nothing (`currval` still answers); `DISCARD ALL` does not reset `SET
    ROLE` or `SET SESSION AUTHORIZATION`; `DEALLOCATE` does nothing and its command tag is `SET`.
- **Enum types:**
  - An enum value comes out typed as text: `pg_typeof('ok'::mood)` is `text`, and the column is named `text`.
  - `'mood'::regtype` is 42704 `type "mood" does not exist`; `enum_range` does not exist (42883).
  - `ALTER TYPE` takes only `ADD VALUE` (`RENAME VALUE`, `RENAME TO`, `OWNER TO` are 0A000); composite and range
    types are 0A000; `DROP TYPE ... CASCADE` and arrays of enums are 0A000.
- **Roles and privileges:**
  - `CREATE ROLE ... IN ROLE / ROLE / ADMIN` make no membership, and `CREATEDB`, `CREATEROLE` and the other
    non-login options are read and not kept.
  - `CREATE ROLE "public"` succeeds (PostgreSQL reserves the name).
  - The bootstrap role `postgres` cannot be named: `DROP ROLE postgres` and `OWNER TO postgres` say it does not
    exist, though `pg_roles` lists it.
  - `DROP ROLE` drops a role that holds privileges, and the grants go with it (PostgreSQL refuses until they are
    revoked); a role that owns objects is refused (2BP01).
  - `REASSIGN OWNED` and `DROP OWNED` are syntax errors; `ALTER DEFAULT PRIVILEGES` is 0A000 with a misleading
    message ("only ALTER TABLE, ALTER INDEX and ALTER SCHEMA are supported"); `pg_has_role` and `pg_authid` do not
    exist.
  - `GRANT MAINTAIN` is accepted and not kept. Column privileges, `WITH GRANT OPTION`, `WITH ADMIN OPTION` and
    privileges on types are 0A000.
- **SQL functions and procedures** (found writing the routine pages):
  - Overloads: with `add(int, int)` and `add(numeric, numeric)`, `SELECT add(2, 3)` calls the numeric one
    (PostgreSQL: the integer one).
  - 0A000 or 42883 in a query: a function whose body reads tables given a column or subquery as an argument; a
    function with several OUT parameters; a function whose body writes; a set-returning function in the select
    list; named arguments (`CALL` takes them); calling a VARIADIC function.
  - `ALTER FUNCTION` and `ALTER PROCEDURE` are 0A000 ("only ALTER TABLE, ALTER INDEX and ALTER SCHEMA are
    supported"); `SECURITY DEFINER` is accepted and ignored.
- **Maintenance and statistics:** `pg_stats` does not exist (42P01) and `pg_class.reltuples` stays -1 after `ANALYZE`
  (`pg_stat_user_tables.n_live_tup` is right). `REINDEX` and `CLUSTER` are checked and do nothing; `VACUUM` (and
  `VACUUM FULL`) rewrites row-form leaves as column leaves and gives no space back.
- **COPY:** `WITH (FORMAT binary)` is 0A000. `ON_ERROR set_null` (PostgreSQL 19) is 0A000; `FORMAT json` is for `COPY
  TO` only (`COPY FROM` with it is 22023, as in PostgreSQL). A view as `COPY FROM`'s target is refused before the
  CopyInResponse (PostgreSQL refuses it after, once the client is sending data). The other errors of a `COPY ... FROM
  STDIN` statement's table or options come before it, as in PostgreSQL; psql 18 then skips the script's lines up to a
  line `\.` with either server.
- **Data types** (found writing the type pages):
  - **Bare integer constants are checked only in a select list:** integer-literal arithmetic there is 22003 (int4 and
    bigint), as in PostgreSQL (`SELECT 2147483647 + 1`). In `WHERE`, `ON`, `HAVING` and `ORDER BY` it is not checked
    (computed as bigint: `WHERE 2147483647 + 1 > 0` is true). With a cast in the expression (`2147483647::int + 1`,
    `32767::smallint + 1::smallint`) and on a column it is 22003, as in PostgreSQL; PostgreSQL also folds a constant
    expression when it plans, so `2147483647::int + 1` from a table `WHERE false` raises there and gives no rows here.
    Oracle door: `9223372036854775807 + 1` is ORA-01426 where Oracle gives 9223372036854775808. T-SQL door:
    `9223372036854775807 + 1` is an error (8115) where SQL Server gives a numeric.
  - **Enums are still ordered as text in four places:** `min` and `max` as window functions, the `ORDER BY` inside
    an aggregate (`array_agg(m ORDER BY m)`), a set operation's `ORDER BY`, and arrays (`ARRAY['ok'::mood]` is an array
    of text). Elsewhere they follow the list and a string that is not a label is 22P02.
  - `'alice'::regrole` is looked up as a function (42883); `pg_proc` holds only the user's functions, so
    `'now'::regproc` is 42883; `regprocedure` leaves out the argument types.
  - `pg_typeof` says text for `oid`, `regclass`, `regtype`, `name` and `pg_class.relname`.
  - `'abc'::"char"` is not cut to one character, a `name` not to 63, and `varchar(0)` is accepted.
  - `varchar(n)` keeps excess trailing spaces: `'abc   '` into `varchar(3)` is 22001 (PostgreSQL cuts them).
  - bytea: `substring` and `position` work on the hex text, not the bytes; `get_byte`, `set_byte`, `convert_to`,
    `convert_from` and `sha256` do not exist; `SET bytea_output = 'escape'` is accepted and output stays hex.
  - numeric has no `NaN` or `Infinity`, and at most 38 significant digits (22003).
  - Dates are read in ISO order only (`'01/03/2026'`, `'20260301'`, `'March 1, 2026'` are 22007); `SET DateStyle`
    and `SET IntervalStyle` are accepted and change nothing; `'allballs'::time` and `'infinity'::interval` are not
    read.
  - Typed constants other than the date and time ones (`text '1'`, `int '42'`, `numeric '1.50'`, `bool 'yes'`), `B'101'`,
    `X'1F'` and `U&'\0041'` are not read.
  - Arrays: `integer ARRAY`, `SET a[2] = ...`, slices (`a[2:3]`), `ARRAY[[1,2],[3,4]]` are 42601; more than one
    dimension is 0A000; `'[0:2]={...}'` is 22P02; `a[1]` is named `#elem`; `ARRAY[1, 'x']` is accepted;
    `'1 2'::int2vector` prints `{1,2}`.
  - Some mixed types are still not refused: `true AND 1` gives an empty row, `ARRAY[1, true]` gives `{1,t}` and `1 IN
    (1, true)` is taken (`NOT 1` is refused with a shorter message). `CASE`, `coalesce`, `UNION`, `VALUES` and a text
    beside a number are checked.
  - Some casts' columns are named differently: `(-2.5)::int` is `?column?`, `42::oid` is `integer`.
- **Scalar functions** (found writing the function pages):
  - Regular expressions are RE2's: no back references (`'aa' ~ '(a)\1'` is 2201B) and no lookaround; the error
    texts are RE2's (`missing closing )`, where PostgreSQL says `parentheses () not balanced`).
  - `ILIKE` folds ASCII letters only, while `~*` folds every letter: `'É' ILIKE 'é'` is f, `'É' ~* 'é'` is t.
  - `trunc(numeric, places)` does not exist (42883); `cbrt(27)` gives 3.0000000000000004.
  - Missing (42883): `character_length`, `bit_length`, `normalize`, `to_ascii`, `sha224` to `sha512`, `factorial`,
    `setseed`, `random_normal`, `justify_days`, `justify_hours`, `justify_interval`, `make_time`. The `^@` and `~~`
    operators are not taken.
  - `concat_ws(',')` alone is 42883 (PostgreSQL: an empty string); `format('%*s', 5, 'a')` has no `*` width.
  - Messages: `date_trunc('fortnight', ...)` says `for type timestamp` (PostgreSQL: `timestamp without time zone`);
    `to_date('2026-13-01', ...)` quotes the value re-formatted (`"2026-13-1"`).
- **Aggregate, set-returning and other functions:**
  - `pg_typeof(sum(x))` (and `pg_typeof(count(*))`) is computed for each row: two rows for a two-row input
    (PostgreSQL: one).
  - `generate_series` works only in `FROM` (`SELECT generate_series(1, 3)` is 42883), and has no time-zone form;
    `generate_subscripts` works only in the select list.
  - `array_append(ARRAY[1, 2], 'x')` gives `{1,2,x}` (PostgreSQL: 22P02); `array_fill`, `array_to_json` and
    `array_sort` do not exist.
  - `current_catalog`, `current_schemas`, `pg_client_encoding`, `pg_postmaster_start_time`, `current_query` and
    `pg_my_temp_schema` do not exist (42883).
  - `current_schema` names a schema of `search_path` that does not exist (PostgreSQL skips it).
  - `pg_typeof` says text for `current_user` (PostgreSQL: name), `'x'` and `NULL` (unknown), and
    `pg_advisory_lock(...)` (void). `SELECT current_role` and `SELECT user` name their column `current_user`.
  - `pg_locks` does not exist, so advisory locks cannot be listed.
  - `pg_wal_lsn_diff`, `pg_last_xact_replay_timestamp` and `pg_stat_replication` do not exist; there is no `pg_lsn`
    type, and LSNs are text with eight hex digits after the slash (`0/00000004`; PostgreSQL: `0/4`).
  - `has_column_privilege`, `pg_has_role`, `pg_column_size` and `to_regproc` do not exist.
  - Only `json_build_object` and `jsonb_build_object` exist; the second returns the same text as the first, with
    its keys neither sorted nor de-duplicated.
- **Operators and expressions:**
  - Reserved words are not taken as column aliases after `AS` (`SELECT 1 AS cast` is 42601).
  - `NOTNULL` and `ISNULL` are read as aliases, not operators.
  - `2 BETWEEN 1 AND 3 = true` is a syntax error (PostgreSQL reads `(2 BETWEEN 1 AND 3) = true`).
  - Bitwise operators take numeric (`1.5 & 1` gives 0; PostgreSQL: 42883).
  - `OPERATOR(pg_catalog.+)` is not taken; `@`, `|/`, `||/` and `!` do not exist.
  - `SELECT 'a' || 'b' LIKE 'a%'` names its column `like` (PostgreSQL: `?column?`).
- **Catalog** (found writing the catalog pages):
  - NOT NULL constraints (named, in `pg_constraint` as contype `n`, and in `information_schema`) are there, and
    `DROP CONSTRAINT` and `RENAME CONSTRAINT` act on them. What is left: psql's `\d+` shows no "Not-null constraints"
    section (its query joins on `conkey[1]` and finds nothing; primary keys too, on main before); `CREATE TABLE ...
    LIKE` is 42601; on a table without a primary key a column added later gets an `attnum` and a `conkey` one too
    high.
  - `pg_rewrite` is empty, though a view's `pg_class.relhasrules` is t; `pg_depend` holds only column-to-sequence
    rows; `pg_opclass` is empty; `pg_am` lists `hash`, which `CREATE INDEX` refuses.
  - Identity sequences are in `pg_sequences` but not in `information_schema.sequences`.
  - `ALTER TYPE ... ADD VALUE ... BEFORE` renumbers `pg_enum.enumsortorder` (1, 2, 3; PostgreSQL: 1, 1.5, 2).
  - `0::regclass` shows `0` (PostgreSQL: `-`); `pg_type.oid` and other `oid` and `regtype` columns are sent as text,
    so psql aligns them left.
  - Missing (42P01): `pg_stat_activity` (monitoring tools need it), `pg_stats`, `pg_locks`, `pg_operator`,
    `pg_cast`, `pg_authid`, `pg_timezone_names`, `pg_stat_all_tables`, `pg_statio_user_tables`, and
    `information_schema` `triggers`, `enabled_roles`, `applicable_roles`,
    `element_types`.
- **Errors:** `SELECT $1` in a simple query is 08P01 `there is no parameter $1` (PostgreSQL: 42P02). A
  `max_statement_mem` of 1 kB did not stop a top-N sort over 100,000 rows (not narrowed down).


## SQL Server door

- **`UPDATE STATISTICS`** is a syntax error (102), on the master and on a replica.
- **Missing functions:** `UNICODE`, `STDEV`, `STDEVP`, `VAR`, `VARP` and `ATN2` give error 195 ("function ... does
  not exist"). An error 195 ends the batch, as SQL Server's compile errors do.
- **A table hint on an `INSERT`'s target** (`INSERT INTO t WITH (TABLOCK)`) is error 156 (SQL Server accepts it).
  Table hints in `FROM` are read and ignored.
- **Reserved words as names:** SQL Server's reserved words are refused as bare table, column and alias names (156), as
  SQL Server does (`SELECT 1 rule` is 156, and `CREATE TABLE HOLDLOCK` and `CREATE TABLE INDEX` are 1018, as in SQL
  Server).
- **No `CREATE LOGIN`.** `CREATE USER name WITH PASSWORD = '...'` is error 102; `CREATE ROLE name LOGIN PASSWORD
  '...'` (PostgreSQL's form) works in this door.
- **Queries and DML** (found writing the T-SQL query pages):
  - `AVG(x) OVER (...)` is error 50000 (`column ... must appear in the GROUP BY clause`); `SUM`, `MIN`, `MAX` and
    `COUNT` with `OVER` work. `COUNT_BIG(*) OVER (...)` is 195.
  - `TRUNCATE TABLE` does not reset the `IDENTITY` (the next id goes on; SQL Server starts again at the seed).
  - Views are read-only (50000), and a CTE cannot be the target of `UPDATE`, `DELETE` or `MERGE` (208).
  - `SELECT INTO` loses column attributes: `nvarchar(30)` becomes `nvarchar(max)`, a decimal gets wider, `NOT NULL`
    and `IDENTITY` are lost. `SELECT IDENTITY(int, 1, 1) AS n ... INTO` is 207.
  - Error 156 for `PIVOT`, `UNPIVOT` and `TABLESAMPLE`, and 102 for `FOR XML`, `FOR JSON`, `$IDENTITY`, join hints
    (`INNER LOOP JOIN`), `FOR SYSTEM_TIME`, `GROUP BY ... WITH ROLLUP` / `WITH CUBE` (SQL Server accepts them all);
    `GROUPING_ID` is 195.
  - `TOP (subquery)` is 156 (SQL Server accepts it); `MERGE TOP ... PERCENT` is 50000.
  - `INSERT TOP (n) ... SELECT ... ORDER BY` follows the `ORDER BY`; SQL Server ignores it (the rows `INSERT TOP` takes
    are in no defined order, and in a test it took the first rows of its scan).
  - A `SELECT *` view whose table lost a column and gained another reads the columns by position: the view's column
    `y` shows the values of the column that took its place, and keeps its old name. SQL Server does the same
    (checked) when the view was not read in between; once a read has failed with 4502, SQL Server goes on with 4502
    until `sp_refreshview`, while lexdb reads by position again (a failed read changes nothing in the view);
    `sp_refreshview` exists and brings the table's columns as they are now. With a column dropped and none added,
    both give 4502 (naming the view as written). Oracle reads by name.
  - `UPDATE t SET @v = @v + col` and `SET @v = col = expr` are 102.
  - `OUTPUT ... INTO t` followed by an `OUTPUT` that returns rows is 50000.
  - `SET IDENTITY_INSERT` checks nothing: a missing table (208), a table without an identity (8106), a second table
    ON (8107) are taken; with it ON, an `INSERT` that leaves out the identity column gets the next value (545), and one
    without a column list is taken (8101).
  - Taken where SQL Server refuses: `TOP ... WITH TIES` without `ORDER BY` (1062), `TOP 2.5` (1060), `TOP` with
    `OFFSET` (10741), `OFFSET` without `ORDER BY`, `FETCH` without `OFFSET`, `FETCH` 0 rows (10744), `ORDER BY` in a
    derived table without `TOP` (1033), `ROW_NUMBER() OVER ()` (4112), `RANGE` with a numeric offset (4194), a column
    set twice in one `UPDATE` (264), `DELETED` in an `INSERT`'s `OUTPUT` (4104), `NATURAL JOIN`, `USING`, `LATERAL`,
    a standalone `VALUES`, `WITH RECURSIVE`, `TRUNCATE TABLE a, b`, a `VALUES` derived table without column names
    (8155).
  - A `UNION` of an int column and an nvarchar column gives mixed text rows (SQL Server: 245).
  - Error 50000 with lexdb's text where SQL Server has a number: ambiguous column (209), ungrouped column (8120),
    window function in `WHERE` (4108), `DISTINCT` with `ORDER BY` of a column not selected (145), negative `OFFSET`
    (10742), `TOP (-1)` (1014), `TRUNCATE` of a table a foreign key refers to (4712). A `UNION` column-count
    mismatch is 102 (SQL Server: 205); updating an identity column is 544 (SQL Server: 8102).
  - `DATALENGTH` of a `char(7)` value is 14 (SQL Server: 7).
- **Tables, indexes, views and sequences** (found writing the T-SQL DDL pages):
  - **`CLUSTERED` and `NONCLUSTERED` are labels:** the rows stay in primary-key order.
  - Constraint names that were not given still differ: `emp_pkey`, `emp_name_key`, `emp_dept_id_fkey` where SQL Server
    generates `PK__emp__3213E83F...`.
  - `DROP INDEX ix ON dbo.t`, `DROP INDEX t.ix` and `DROP INDEX dbo.t.ix` work; a bare name is 159, `DROP INDEX
    dbo.ix` is 3701 (it reads `dbo` as the table), and 3701 and 3723 come with SQL Server's texts and states, as in SQL
    Server, except that 159 has severity 16 (SQL Server: 15; found on main 1d5fb7d3, not fixed). A list of indexes
    (`DROP INDEX a.x, b.y`) is still 102 (SQL Server takes it).
  - `ALTER TABLE t ADD CONSTRAINT df DEFAULT 0 FOR col` is 102; a DEFAULT constraint's own name is not kept (it shows
    as `DF_table_col`), and `DROP CONSTRAINT` finds it by neither name.
  - `ALTER TABLE` takes one action per statement (`ADD b int, c int` is 50000), and refuses `SET (LOCK_ESCALATION =
    ...)`, `SWITCH`, `REBUILD` and `DISABLE TRIGGER` (50000).
  - **Constraint states** (`WITH NOCHECK`, `NOCHECK CONSTRAINT`, `CHECK CONSTRAINT`):
    - The 547 of `ADD` and of `WITH CHECK CHECK CONSTRAINT` says `The INSERT statement conflicted with ...` (a foreign
      key under `ADD`: `insert or update on table ... violates foreign key constraint`); SQL Server says `The ALTER TABLE
      statement conflicted with ...`.
  - A column-level `CONSTRAINT fk FOREIGN KEY REFERENCES t (c)` is 102 (without `FOREIGN KEY` it works).
  - `ON [PRIMARY]`, `TEXTIMAGE_ON`, `WITH (...)` index and table options and `ASC` / `DESC` in a key are read and not
    kept. Still syntax errors: `ROWGUIDCOL`, `SPARSE`, `FILESTREAM`, `MASKED WITH`, `NOT FOR REPLICATION` and `GENERATED
    ALWAYS AS ROW START`.
  - A `rowversion` (`timestamp`) column is never filled in (NULL).
  - A table with two `IDENTITY` columns is accepted (SQL Server: 2744).
  - `##g` is a session-private temporary table, as `#g` is.
  - Alias types (`CREATE TYPE dbo.phone FROM varchar(20)`) are 156.
  - `ALTER INDEX ... REBUILD`, `REORGANIZE` and `DISABLE` and `CREATE STATISTICS` are 50000; `CREATE COLUMNSTORE
    INDEX` is 102; `sp_helpindex` and `sp_helptext` are 2812.
  - A unique index over rows that clash is 2627 (SQL Server: 1505).
  - Views: `WITH CHECK OPTION` after the query is 50000 (before `AS` it is 102, as in SQL Server); `CREATE VIEW` need
    not be first in its batch (SQL Server: 111); `DROP VIEW` of a view another view reads is refused (50000; SQL
    Server allows it, and the other view then fails with 208 when read). `DROP TABLE` under a view is done as in SQL
    Server (208 when the view is read, 3729 for a schema-bound view). A `SELECT *` view keeps its CREATE-time columns
    by position until `sp_refreshview`, and a view that names its own columns is 8158 once the table has gained one,
    as in SQL Server; 4502 and 8158 are compile errors that a `TRY` block in the same scope does not catch, as in SQL
    Server. Found on main 1d5fb7d3, not fixed: the 4512 of `CREATE VIEW dbo.v WITH SCHEMABINDING AS SELECT ... FROM t`
    names `'v'` (SQL Server: `'dbo.v'`; 4513's is right), `ALTER VIEW` of a missing view is 208 with state 1 (SQL
    Server: 6), and 2010 names `'emp'` (SQL Server: `'dbo.emp'`).
  - `WITH SCHEMABINDING` is read and kept (`sys.sql_modules.is_schema_bound`): `ALTER TABLE ... DROP COLUMN` or
    `ALTER COLUMN` of a column such a view uses is 5074, `SELECT *` in one is 1054, a one-part name in the view 4512,
    a view over a view or function that is not schema-bound 4513, as in SQL Server.
  - `DROP TABLE` of a table a foreign key refers to is 50000 (SQL Server: 3726).
  - Sequences: `NO CACHE` is 102; `AS decimal(10,0)` is 50000; without `AS` and `START WITH` a sequence starts at 1
    (SQL Server: a bigint from its minimum); `NEXT VALUE FOR s` twice in one row gives two values (SQL Server: the
    same); `NEXT VALUE FOR s OVER (...)` is 102; `sp_sequence_get_range` is 2812; past `MAXVALUE` the error is 50000
    (SQL Server: 11728); `ALTER SEQUENCE s MAXVALUE 100` of a sequence started at 1000 is refused even with
    `RESTART WITH 50`.
  - Other error numbers: `DROP TABLE`, `VIEW` or `SEQUENCE` of a missing object is 208 (SQL Server: 3701), adding a
    column that exists 50000 (2705), dropping an unknown column 207 (4924), adding a `NOT NULL` column without a
    default to a table with rows 515 (4901).
  - Index names are per table, as in SQL Server (1913 for the same name on the same table, 8168 for a repeated inline
    name, 8112 for two `CLUSTERED`). The PostgreSQL and Oracle doors keep index names per schema, and show the second
    `ix` under a longer name (`ix`, a control character and the table's name).
- **Transactions and variables** (found writing those T-SQL pages):
  - A string too long for a variable is error 2628 and leaves it NULL: `DECLARE @s varchar(3) = 'abcdef'` (SQL
    Server cuts it to 'abc').
  - `ROLLBACK` undoes changes to a table variable (SQL Server keeps them).
  - A table variable used after its batch is 208 `Invalid object name '#@t'` (SQL Server: 1087).
  - `SELECT @n += id FROM t` is 102 (it works in `SET`); in `SELECT @a = 1, @b = @a + 1`, `@b` does not see the new
    `@a` (SQL Server: 2).
  - `ROLLBACK TRAN` with a name that is neither the outermost transaction's nor a savepoint's rolls back everything
    (SQL Server: 6401, the transaction stays open).
  - `SET TRANSACTION ISOLATION LEVEL` takes any word (`CHAOS`) and keeps nothing:
    `sys.dm_exec_sessions.transaction_isolation_level` stays 2.
  - `BEGIN TRANSACTION ... WITH MARK` is 102 and `BEGIN DISTRIBUTED TRANSACTION` 156; cursors (`DECLARE @c CURSOR`,
    `DECLARE c CURSOR FOR`) are 50000 and 102.
  - With `XACT_ABORT ON`, a failed `UPDATE` inside `BEGIN TRY` sends `(0 rows affected)` before the `CATCH` output.
- **Control of flow** (found writing those T-SQL pages):
  - A failed `INSERT`, `UPDATE` or `DELETE` inside `BEGIN TRY` sends `(0 rows affected)` before the `CATCH` output (a
    failed `SELECT` or DDL statement sends none, as in SQL Server).
  - `BREAK` or `CONTINUE` outside a loop is accepted (SQL Server: 135).
  - `RAISERROR` reads and ignores a placeholder's width, precision and flags (`%5d`, `%-6s`); `%o` prints decimal;
    `RAISERROR(50005, 16, 1)` gives Msg 50000 with the text "50005" (no `sys.messages`); `WITH LOG` writes no log and
    `NOWAIT` changes nothing.
  - `THROW 49999, 'too low', 1` is accepted (SQL Server: 35100).
  - `EXECUTE AS USER = 'dbo'` is 2812 (`Could not find stored procedure 'as'`); `EXEC ('...') AT linked` is 102;
    `GOTO` and `WAITFOR` are 102.
  - `GETDATE() - GETDATE()` is an interval (`00:00:00`); SQL Server gives a datetime (1900-01-01).
- **Procedures, functions, types and schemas** (found writing those T-SQL pages):
  - Multi-statement table-valued functions are made but cannot be read: `SELECT * FROM dbo.squares(4)` is 50000
    ("not supported yet (an inline one is)").
  - A table-valued parameter passed from a T-SQL batch fails: `DECLARE @l dbo.id_list; ... EXEC dbo.take_ids @ids =
    @l` is 207 `Invalid column name '#tv_l'` (over RPC it works).
  - A table type a procedure uses can be dropped (SQL Server: 3732); an index in a table type is 102.
  - `CREATE PROCEDURE` takes a parameter of a type that does not exist; `WITH EXECUTE AS OWNER` is 102; `WITH
    ENCRYPTION` is accepted.
  - `CREATE SCHEMA hr CREATE TABLE staff ...` makes `dbo.staff`, not `hr.staff`; `AUTHORIZATION dbo` is 50000;
    `CREATE SCHEMA dbo` is accepted (SQL Server: 2714); an existing schema is 50000 (2714); `CREATE SCHEMA` need not
    be first in its batch (111).
  - `ALTER SCHEMA hr TRANSFER dbo.t` is 50000: an object cannot move to another schema.
  - `DROP SCHEMA` of a schema with objects is 50000 (SQL Server: 3729), of a missing one 50000 (3701).
- **Security, ALTER DATABASE, SET and system procedures** (found writing those T-SQL pages):
  - Role membership: `ALTER ROLE r ADD MEMBER u` is 102, `sp_addrolemember` 2812, `sys.database_role_members` 208
    (PostgreSQL's `GRANT r TO u` works). The fixed database roles do not exist: `IS_MEMBER('db_owner')` is 0 for sa.
  - `CREATE USER u WITHOUT LOGIN` / `FOR LOGIN l`, `CREATE ROLE r AUTHORIZATION dbo`, `ALTER USER u WITH
    DEFAULT_SCHEMA = ...` and `ALTER ROLE r WITH NAME = ...` are 102. A user made by `CREATE USER` is listed as a
    `SQL_USER` and as a `SQL_LOGIN`.
  - `DROP USER` / `DROP ROLE` of a missing name is 50000 (SQL Server: 15151); a role with members can be dropped
    (15144).
  - Refused, with the whole batch: column privileges, `WITH GRANT OPTION`, `REVOKE GRANT OPTION FOR`, `ON SCHEMA::`
    (50000), `GRANT CREATE TABLE` (156), `DENY` (102). `EXECUTE AS USER` is 2812 and `SETUSER` 102.
  - `ALTER DATABASE` inside a transaction is 226, which ends the batch and leaves the transaction open. After `SET
    RECOVERY SIMPLE`, `DATABASEPROPERTYEX(..., 'Recovery')` still says FULL (`sys.databases` says SIMPLE). `MODIFY
    NAME`, `COLLATE` and `CREATE DATABASE` are 50000; `DROP DATABASE` is 102.
  - SET options: `SET STATISTICS IO ON` (and `TIME`, `XML`) is 156; `SET BOGUS ON` is accepted; `NOEXEC`,
    `PARSEONLY` and the `SHOWPLAN` options still run the statements; `SET DATEFIRST` and `SET LOCK_TIMEOUT` change
    neither `@@DATEFIRST` nor `@@LOCK_TIMEOUT`; `ANSI_NULLS OFF` and `CONCAT_NULL_YIELDS_NULL OFF` have no effect;
    `SET ROWCOUNT` limits `SELECT` only; `SET QUOTED_IDENTIFIER OFF` applies from the next batch; `@@OPTIONS` is 195;
    `CONTEXT_INFO()` stays NULL after `SET CONTEXT_INFO`; `SET DATEFORMAT dmy` does not make `'01/02/2026'` readable
    (241).
  - `sp_help`, `sp_helpdb`, `sp_who`, `sp_spaceused`, `sp_configure` and `sp_server_info` are 2812; in a batch,
    `EXEC sp_prepare` and its family are 2812 (they work over RPC); `sp_datatype_info 4` returns every row;
    `xp_msver` shows the real machine's processor count and memory.


- **Data types, functions and catalog** (found writing the T-SQL phase 3 pages):
  - **Binary:** `0x00 = 0x0000` is false (SQL Server pads the shorter value); `CAST(0x41 AS bit)` is 50000; a
    `varbinary` variable in an expression (`@v + 0x43`) is 195; `HASHBYTES` does not exist.
  - **Ranges and casts:** `smallmoney` takes up to 999999.9999; `TRY_CAST('12' AS decimal(2,0))` is not NULL;
    `CAST('yes' AS bit)` is 1; `SUM` of `int` does not overflow; `CAST(0 AS datetime)` is 50000.
  - **Character:** `DECLARE @n varchar = 'abcdef'` and `CAST(x AS varchar)` keep every character; assigning a long
    string to a `varchar(10)` variable is error 2628 (SQL Server cuts it); `ISNULL` is `COALESCE` (the type of the
    first argument is not kept); `DATALENGTH` counts two bytes per character of every string type (a padded
    `char(5)` is 10) and gives 0 for a `real`.
  - **Dates:** only ISO layouts are read (`'20260315'`, `'March 15, 2026'` and `'03/15/2026'` are 241, with any
    style; with an offset too, `'March 15, 2026 10:00:00 AM +02:00'`); the seventh fractional digit is lost;
    `DATEPART(iso_week)` is 155; `date - date` is accepted (SQL Server: 8117) and `GETDATE() - GETDATE()` is an
    interval (`00:00:00`; SQL Server: a datetime); `CAST('2026-03-15 13:45:30' AS time)` is 241; `ISDATE`,
    `DATETIMEFROMPARTS`, `TIMEFROMPARTS` and `DATETIME2FROMPARTS` are 195; conversion styles 14, 22 and 114 are 281,
    and 9, 13, 109 and 113 are 281 for every type but `datetimeoffset` (SQL Server: `Mar  5 2026  2:07:09:123PM`
    and the like).
  - **datetimeoffset** (it keeps its offset since main 178ea2df; see [date and time
    types](sql/tsql/data-types-datetime.md)): its string form (`CAST` to `varchar`, and the styles that show a
    fraction) has seven fractional digits whatever its scale (`datetimeoffset(0)` gives `10:00:00.0000000 +02:00`; SQL
    Server `10:00:00 +02:00`), and styles 126 and 127 print none, three or seven by the value (`.500` for `.5`; SQL
    Server the scale's digits); `FORMAT` does not know `zzz` (it is printed as it is; SQL Server `+02:00`); a `VALUES`
    list or a derived column typed only by its type id keeps the instant, not the offset (`(VALUES (CAST('2026-03-15
    10:00 +02:00' AS datetimeoffset)))` gives `08:00:00 +00:00`); `MAX` alone over an index on the column: SQL Server
    reads the index backwards and shows the last of equal instants in key order, lexdb the first (`MIN`, and `MAX`
    without an index, show the first in both); `datetimeoffset - datetimeoffset` is an interval (`01:00:00`; SQL
    Server: 8117), and a variable plus a number (`@d + 1`) is 195 (SQL Server: 206); `AT TIME ZONE` knows about 45
    Windows zone names, and another (`'Mountain Standard Time (Mexico)'`) is 9820.
  - **Maths:** `ROUND(123.4567, -1)` on a decimal is 8115; `SQRT(-1)` and `LOG(0)` are 50000, `ASIN(2)` and `EXP(710)` 8115 with PostgreSQL's text; `5 / 2.0E0` is
    a decimal (6 places); `real / int` is computed as a float.
  - **Functions that are lenient:** `IIF(1, 'a', 'b')` gives `b` (SQL Server: 4145); `GREATEST(1)`, `CONCAT('a')`,
    `SUBSTRING('abcdef', 2)` and `LEFT('abc', -1)` are taken (SQL Server: 189, 174, 536); `TRANSLATE('abc', 'abc',
    'xy')` is accepted (9828); `ASCII('')` is 0; `CASE` and `COALESCE` over `1` and `2.5` give `1`, not `1.0`.
  - **`FORMAT`:** dates cover 46 cultures (the ten en-US, en-GB, de-DE, fr-FR, es-ES, it-IT, nl-NL, pt-BR, ja-JP,
    sv-SE and 36 more, with genitive month names, the time separator and Thai Buddhist years). ar-SA (the Hijri
    calendar) and cultures outside the 46 get en-US dates. A valid-form unknown name gets the invariant culture, as SQL
    Server 2022 does; a name of the wrong form is error 9818. 61 cultures are known for numbers; a real culture outside
    them is read as the invariant one.
  - **Conversion errors:** a comparison of a string with a number is 195 (`'abc' = 1`; SQL Server: 245).
  - **Operators:** `!<` and `!>` are 102; `SELECT 1 = 1` and `SELECT NOT 1 = 2` are accepted (SQL Server: 102); `||`
    joins strings.
  - **System functions:** `IDENT_CURRENT`, `NEWSEQUENTIALID`, `ROWCOUNT_BIG`, `TRIGGER_NESTLEVEL`,
    `SESSION_CONTEXT`, `COL_NAME`, `COL_LENGTH`, `HOST_NAME`, `APP_NAME`, `SUSER_ID`, `USER_ID`, `PARSENAME`,
    `@@FETCH_STATUS`, `@@CURSOR_ROWS`, `@@DBTS`, `@@OPTIONS` and `SQL_VARIANT_PROPERTY` are 195; `USER_NAME(id)` is
    195; `@@IDENTITY` takes the value of `NEXT VALUE FOR`; `IS_MEMBER('db_owner')` and
    `IS_SRVROLEMEMBER('sysadmin')` are 0 for `sa`; `xml` has no methods (`doc.value(...)` is 4121); `NTH_VALUE`
    works (SQL Server has none).
  - **Catalog:** `sys.index_columns` omits the `INCLUDE` columns of an index; `sys.server_principals` does not list
    `sa`; `sys.dm_exec_sessions` is one recorded row; `INFORMATION_SCHEMA` is SQL Server's for
    `SCHEMATA` (its schemas, `dbo`, `guest`, `INFORMATION_SCHEMA`, `sys` and the `db_*` ones, and the schemas made with
    `CREATE SCHEMA`, owned by `dbo` or their `AUTHORIZATION` owner), `ROUTINES`, `PARAMETERS`,
    `CONSTRAINT_COLUMN_USAGE` (a foreign key's own columns), `VIEW_TABLE_USAGE` and `VIEW_COLUMN_USAGE`; `DOMAINS`
    and `COLUMN_PRIVILEGES` exist with no rows (their columns are PostgreSQL's, in lower case; SQL Server's `DOMAINS`
    has 17 and lists table types and alias types, which lexdb's does not), the column names are in lower case and the
    catalog name is `lexdb` (SQL Server: upper case, the database's name); `sys.database_role_members`,
    `sys.partitions` and `sys.dm_exec_requests` do not exist (208); `sys.types` gives `decimal` scale 38; every decimal expression is `decimal(38,6)` in
    `sys.columns`. A CHECK's text (`INFORMATION_SCHEMA.CHECK_CONSTRAINTS.CHECK_CLAUSE`,
    `sys.check_constraints.definition`) is SQL Server's form (`([salary]>=(0))`) except a `CAST`, which shows as what
    lexdb made of it (`CAST(a AS varchar(3))` is `left(bin2str([a],(0),(3)),(3))`; SQL Server writes a `CONVERT` with
    the type in brackets), an `N'...'` literal (the `N` is dropped) and a system-named constraint's name (`ck_c_check`;
    SQL Server `CK__ck__c__3C69FB99`).
  - A `datetime` column takes PostgreSQL's special strings (`INSERT ... VALUES ('tomorrow')`).

## Oracle door

- **A global temporary table's definition is private to the session that made it**, on the master as on a
  replica. In Oracle the definition is a schema object that every session sees, and only the rows are private to a
  session.

- **Queries and DML** (found writing the Oracle query pages):
  - `ROWNUM` in a join with an aggregate or `GROUP BY` limits the groups, not the rows grouped (`SELECT COUNT(*) FROM
    emp e, dept d WHERE e.dept_id = d.id AND ROWNUM < 3` is 4; Oracle: 2). With one table in `FROM` it works.
  - `SELECT *` over `NATURAL JOIN` and `JOIN ... USING` shows a `DATE` as a timestamp (`2019-03-01 00:00:00.0`) and
    prints column names in lower case.
  - `UNION` of a number column and a text column returns both as text (Oracle: ORA-01790).
  - `(+)` works only when the marked table comes after the one it joins; the other order is ORA-03001, and a `(+)`
    inside `OR` is not refused.
  - `CONNECT BY` with a join in the FROM list is ORA-03001, `CONNECT BY ROWNUM <= n` is ORA-32044, and
    `GROUP BY CONNECT_BY_ROOT col` is ORA-00979.
  - `MATCH_RECOGNIZE`: `?` is read as a bind placeholder, reluctant quantifiers (`b+?`) are ORA-00931 and `b?` gives
    ORA-62503; `b{0,1}` works.
  - `FOR UPDATE OF e.name` (columns) is ORA-00942 (a table or alias works); `FOR UPDATE WAIT n` is ORA-00900;
    `FOR UPDATE` on an inline view is accepted.
  - `FETCH FIRST n PERCENT ROWS ONLY`, `SELECT UNIQUE`, `GROUPING_ID` and `GROUP_ID` are not supported.
  - Not supported (ORA-00900): `SAMPLE`, `AS OF`, `PIVOT`, `UNPIVOT`, `MODEL`, `XMLTABLE`, `JSON_TABLE`, a partitioned
    outer join, `UPDATE SET (a, b) = (SELECT ...)`, `UPDATE (subquery)`, `DELETE FROM (subquery)`, `LOG ERRORS`,
    `WHERE CURRENT OF`, `WITH FUNCTION`, `TRUNCATE ... DROP STORAGE`. Accepted although Oracle refuses them: `LIMIT n`,
    `UPDATE ... FROM`, `DELETE ... USING`, `WITH RECURSIVE`.
  - `TRUNCATE` of a table a foreign key refers to is ORA-03001 (Oracle: ORA-02266); `TRUNCATE ... CASCADE`
    truncates the referencing tables whether or not the key is `ON DELETE CASCADE`; an identity column continues.
- **Property graphs** (SQL/PGQ, supported since main e7691bd6; see [GRAPH_TABLE](sql/oracle/graph-table.md) and
  [CREATE PROPERTY GRAPH](sql/oracle/create-property-graph.md)):
  - Not supported (ORA-03001): `ONE ROW PER VERTEX` and `ONE ROW PER STEP`, and so `ELEMENT_NUMBER`; `LISTAGG ...
    WITHIN GROUP` and `DISTINCT` in an aggregate of a quantified variable; a pattern that needs more than 4,096 joins
    (Oracle runs out of memory on one, ORA-04036 at `{1,5000}`). `ALTER PROPERTY GRAPH ... COMPILE` is ORA-03001 and
    privileges on a graph (`GRANT READ ON PROPERTY GRAPH g`) ORA-00942; `COMMENT ON PROPERTY GRAPH` is accepted and not
    kept (`USER_PG_COMMENTS.COMMENTS` stays empty).
  - `VERTEX_ID` and `EDGE_ID` give the JSON's text as `VARCHAR2` (Oracle: `JSON`; lexdb has no JSON type), and
    `MATCHNUM()`'s numbers are lexdb's own (one a match, as in Oracle, but not Oracle's numbers).
  - Quoted graph names and quoted labels are exact, as in Oracle: `GRAPH_TABLE (mixg ...)` and `DROP PROPERTY GRAPH
    mixg` are ORA-42421 for `"MixG"` (checked on Oracle Free 23.26.3), in a database made by this lexdb or later (see
    the names entry below).
  - `USER_OBJECTS.STATUS` of a graph says whether the tables and columns it names are there. Oracle marks a graph
    `INVALID` when a column of one of its tables is changed (`ALTER TABLE ... MODIFY`, a column renamed) even with its
    names all there, and `VALID` at its next use (`ADD` of a column and `CREATE INDEX` leave it `VALID`).
    `USER_PG_ELEMENTS.OBJECT_NAME`, `USER_PG_PROP_DEFINITIONS.COLUMN_NAME` and the types in `USER_PG_LABEL_PROPERTIES`
    stay as they were at `CREATE` (Oracle's follow a rename and a `MODIFY`).
  - `ALTER TABLE ... DROP COLUMN` of a column a view reads through `GRAPH_TABLE` drops it: the view is `INVALID`,
    reading it is ORA-04063, and `USER_ERRORS` shows ORA-04045 and its cause, as in Oracle. Once the column is
    back, the graph and the view are `VALID` and the view readable at once; Oracle keeps both `INVALID`, with
    ORA-04063 on every read, until `ALTER VIEW ... COMPILE` (checked on Oracle Free 23.26.3; kept as a deliberate
    choice: lexdb's view says what its query does now). The same holds for a
    view over a graph that was dropped and made again: `VALID` at once (Oracle: `INVALID` until its next use).
- **Assertions** (`CREATE ASSERTION`, supported since main f23d0ebc; see [CREATE ASSERTION](sql/oracle/create-assertion.md)
  and [Assertions in the three doors](assertions.md)). What is left, checked against main and Oracle Free 23.26.3:
  - `USER_ASSERTION_LOCK_MATRIX` has no rows.
  - `USER_ASSERTIONS.INVALID` is set to `INVALID` by an `ALTER TABLE` that adds, drops, retypes or renames a column of
    a table the assertion reads, and is never cleared; the assertion is still checked. Oracle Free 23.26.3 does the
    same and kept `INVALID` through a write, `ALTER ASSERTION ... ENABLE VALIDATE` and `DBMS_UTILITY.COMPILE_SCHEMA`:
    only `DROP ASSERTION` and a new `CREATE ASSERTION` cleared it, as in lexdb; no case where Oracle clears it
    and lexdb does not was found.
  - Writers of rows that meet in an assertion's join key wait for each other, and without a join key every writer of
    rows that meet their own conditions; Oracle's locks can be finer, for chains of joins.
  - Under `NOVALIDATE`, an `UPDATE` or `DELETE` of a table under the assertion's inner `NOT EXISTS` checks only the outer
    rows of the join-key values taken out, as Oracle's row-only check does ([CREATE ASSERTION](sql/oracle/create-assertion.md),
    example G); the whole query still runs for an `EXISTS` assertion, one without a join key, more than 64 rows taken out
    and a range delete, and is refused there when rows already break the assertion.
  - In the PostgreSQL door an asserted table shows `pg_class.relhastriggers` true (the checks are its triggers, in
    effect; `pg_trigger` has no rows).
- **QUALIFY** (Oracle 23.26's clause; see [QUALIFY](sql/oracle/qualify.md)):
  - The ORA-03049 text keeps at most 28 characters of the statement before the word (Oracle cuts differently after a
    long `CONNECT BY`).
  - `QUALIFY DATE '...'` is ORA-00932 (Oracle: ORA-03048).
- **Constraint states** (`DISABLE`, `ENABLE [NO]VALIDATE`, `MODIFY CONSTRAINT`; see
  [ALTER TABLE](sql/oracle/alter-table.md)):
  - `DISABLE` and `NOVALIDATE` of a `PRIMARY KEY` or `UNIQUE` constraint are refused (ORA-03001; Oracle disables it);
    `ENABLE` and `VALIDATE` of one are accepted and do nothing. In a definition, `DISABLE` or `NOVALIDATE` of a key
    or `NOT NULL` is ORA-00900.
  - `RELY` and `NORELY` are read and not kept (`USER_CONSTRAINTS.RELY` is empty). `NOT ENFORCED` is ORA-00900 (Oracle
    23.26 has none: ORA-02000 or ORA-03075).
- **Tables, users and PL/SQL** (found writing the Oracle DDL and PL/SQL pages):
  - `CREATE TABLE`: `INTERVAL` columns, `INVISIBLE`, `TABLESPACE`, storage clauses, `PARTITION BY`,
    `ORGANIZATION INDEX` and `DEFERRABLE` are ORA-00900;
    `GENERATED BY DEFAULT ON NULL AS IDENTITY` does not fill a NULL key (ORA-01400); `USER_TAB_COLUMNS` shows a
    `RAW` as `BLOB` and a `TIMESTAMP WITH LOCAL TIME ZONE` as `TIMESTAMP(6) WITH TIME ZONE`.
  - Views are read-only (`INSERT`, `UPDATE`, `DELETE` through a view are ORA-03001); `WITH READ ONLY` and `WITH CHECK
    OPTION` are refused; a view another view reads cannot be dropped (ORA-02449). `ALTER VIEW ... READ ONLY` is
    ORA-03001 (Oracle ORA-42310: only an editioning view).
  - `USER_OBJECTS.STATUS` and `USER_ERRORS` of a view say what the view's query does now: after `ALTER TABLE ... DROP
    COLUMN` of a column it reads the view is `INVALID` with its error in `USER_ERRORS` at once (Oracle fills
    `USER_ERRORS` at the view's next use), and it is `VALID` again as soon as the column is back (Oracle keeps it
    `INVALID` until its next use, a view over another view too). `DROP TABLE` under a view is done as in Oracle (the
    view is `INVALID`, ORA-04063 when read, ORA-00942 in `USER_ERRORS`), and the view is `VALID` again as soon as the
    table is made again (Oracle: at its next use). A `SELECT *` view keeps its CREATE-time
    columns, as in Oracle (a column added to the table later is not in it), but over a table that lost a column and
    gained another it reads the columns by position (each view column shows the values of the table column that now
    stands in its place); Oracle reads them by name. `USER_VIEWS.TEXT` shows the text as written (Oracle shows the `*`
    expanded: `SELECT "A","B" FROM vt`).
  - `ALTER TABLE ... READ ONLY` and `ALTER INDEX ... UNUSABLE` are ORA-03001 (Oracle marks the index unusable);
    `ALTER INDEX ... REBUILD`, `COALESCE`, `[NO]PARALLEL`, `[NO]LOGGING` and `ALTER VIEW ... COMPILE` are accepted and do
    nothing; `COMMIT COMMENT` and `COMMIT WRITE` are ORA-00900; `COMMENT ON` does not keep the comment and accepts a
    missing table.
  - A foreign key accepts `ON UPDATE CASCADE` (the child rows follow a parent's key change); Oracle has no such
    clause and gives ORA-02000 (`missing DELETE keyword`).
  - **Quoted names are exact, as in Oracle** (`"qt"` and `QT` are two tables, `mixt` does not find `"MixT"`, and
    `"MixF"(2)` is a call), in a database made by this lexdb or a later one. A database made before keeps the old
    rule for good: its quoted mixed-case names are folded, so its objects answer to the spellings they were made with
    (`mixt` finds `"MixT"`, and `"qt"` and `QT` are one table); to get exact names, load it into a new database.
    Limits: an exact name cannot be reached from the PostgreSQL or SQL Server doors (their quoted names are folded:
    `sa."qt"` is 42P01 / 208 there, though both list the table); a SQL Server spelling such as `Orders` is `ORDERS` to
    the Oracle door (`public.orders` finds it) but is listed as `Orders`; and names lexdb makes from an exact table's
    name (`Emp_PKEY` for `"Emp"`) show their raw bytes in the other doors (`e\x1Cmp\x1D_pkey` in `pg_indexes`).
  - `USER_TAB_COLUMNS.DATA_DEFAULT` of a column whose default is a sequence shows `nextval('s')` (Oracle:
    `"APP"."S"."NEXTVAL"`).
  - Sequences: past `MAXVALUE` the error is ORA-20000 (Oracle ORA-08004); `CURRVAL` before `NEXTVAL` is ORA-20000
    (ORA-08002); `ALTER SEQUENCE ... START WITH` is accepted and does nothing; `SESSION` and `SCALE` sequences are ORA-00900.
  - Users: `ALL_USERS` and `DBA_USERS` list only users that can log in (granted `CREATE SESSION`); `ACCOUNT LOCK` removes a
    user from the lists; `WITH GRANT OPTION` is not kept (`GRANTABLE` is `NO`); `DBA_SYS_PRIVS`, `DBA_ROLE_PRIVS` and
    `DBA_ROLES` are empty; `SESSION_PRIVS`, `SESSION_ROLES` and `USER_ROLE_PRIVS` are recorded samples;
    `USER_TAB_PRIVS_MADE`, `USER_TAB_PRIVS_RECD` and `ROLE_TAB_PRIVS` do not exist; `GRANT bogus_priv TO user` succeeds.
  - `SET TRANSACTION READ ONLY` does not stop changes; `ROLLBACK TO` an unknown savepoint is ORA-20000.
  - `NLS_NUMERIC_CHARACTERS` and `NLS_LANGUAGE` do not change `TO_CHAR` of numbers or messages;
    `SYS_CONTEXT('USERENV', 'NLS_CURRENCY')` is `$` until a territory is set.
  - PL/SQL: records, subtypes, exceptions and collections in a package are not supported (scalar variables and
    constants are read and assigned from outside, and a variable is an `INTO` or `OUT` target); a package specification that declares procedures or functions needs its body
    (a call is PLS-00201 without it); a function without parameters needs brackets in SQL (`SELECT f FROM dual` is ORA-00904); `CALL f()` of
    a function is PLS-00201; `TO_NUMBER('abc')` raises `VALUE_ERROR`, not `INVALID_NUMBER`; `LOCK TABLE` in a block,
    `GOTO`, `FORALL` and collections are refused.
  - A stored function (a standalone one or a package's) works in the SQL of a block, a cursor, `EXECUTE IMMEDIATE`,
    `INSERT ... SELECT`, `UPDATE`, `DELETE` and `CREATE TABLE AS` (fixed on main 7b6b1235). Still refused (the Oracle
    door says ORA-03001, `unimplemented feature`; 0A000 inside): a `MERGE` that calls one; a function in a subquery
    of a DML statement when the subquery reads the statement's own table or refers to its columns; a function whose
    argument is an aggregate or another stored function's call (`f(SUM(x))`, `f(g(x))`). A view may call one (since
    main 84ceec7e), but an `INSERT`, `UPDATE`, `DELETE` or `CREATE TABLE AS` that reads such a view is ORA-03001.
    After `DROP FUNCTION`, `DROP PACKAGE` or `DROP PACKAGE BODY` of the function, reading the view is ORA-04063
    (ORA-04067 after `DROP PACKAGE BODY`, as one line: Oracle adds ORA-06508 and ORA-06512), as in Oracle, also in a
    transaction that wrote something before the drop. `USER_OBJECTS.STATUS` of such a view is `INVALID` while the
    function is gone, and `VALID` as soon as it is back (Oracle: at the view's next use).
  - A stored procedure or function with an undeclared name, an expression that does not parse or DML on a missing
    table is created with compilation errors (`INVALID`, `USER_ERRORS`), as in Oracle; SQL's call of it is ORA-06575
    and `CREATE VIEW` over it is refused with ORA-06575. A syntax error in a SQL statement of a stored procedure or
    function is found at `CREATE` too (ORA-00936, ORA-00907 with a parenthesis left open, at the token where lexdb's
    parser stopped; Oracle's number may differ for other syntax errors); a `SELECT ... INTO` with a parenthesis left
    open before `INTO` (`select count(* into n from t`) is ORA-00907, as in Oracle. Other compile
    errors (types, argument counts, unknown columns of `SELECT INTO`), and any in a package body or an anonymous
    block, appear when the code runs (Oracle: ORA-06550 first for a block, ORA-04063 for a package body).
    PLS-00103's text has no list of expected symbols.
  - **Nested subprograms** (in a stored unit's, a package member's or a block's declarations) work: forward
    declarations, recursion, the enclosing variables and overloads (a call is matched by the number, names and type
    families of its arguments; PLS-00307 when more than one fits, PLS-00306 when none does; a call from SQL inside
    the unit is PLS-00231 at compile time, ORA-06550 in a block). **Found on main 1d5fb7d3, not fixed:** the
    overloaded members of a **package** are not told apart: they are found by name, and the first one declared answers
    every call, from SQL and from PL/SQL (with `sq(number)` before `sq(varchar2)`, `pko.sq('abc')` is ORA-06502; with
    the other order `pko.sq(4)` answers with the `VARCHAR2` member, 1; Oracle picks by the arguments). Also found: the
    ORA-06550 of a PLS-00306 in an anonymous block (a nested call with the wrong arguments) points at column 11, the
    argument list (Oracle: column 3, the call).
  - Annotations (supported since main 6c2e83f1; see [annotations](sql/oracle/annotations.md)): `ALL_` and
    `DBA_ANNOTATIONS_USAGE` have no rows for the built-in domains of `SYS` and `DOMAIN_NAME` / `DOMAIN_OWNER` are
    always NULL (lexdb has no domains); a global temporary table's annotations are kept but not listed.
  - `USER_CONSTRAINTS` does not list `NOT NULL` constraints (Oracle lists them as type `C` rows with the search
    condition `"A" IS NOT NULL`).
- **Functions** (found writing the Oracle function pages):
  - **Character:** `LENGTHB` and `SUBSTRB` count characters (`LENGTHB('€')` is 1); `LENGTH(DATE ...)` is 19;
    `TRIM('xy' FROM 'xyabc')` returns `abc` (Oracle ORA-30001); `SYS_GUID()` is text of 64 hex digits, not `RAW(16)`;
    `HEXTORAW('abc')` is ORA-01722; `REVERSE`, `REPEAT`, `COT` and `CBRT` are accepted under their PostgreSQL names.
  - **Package functions:** `UTL_MATCH.EDIT_DISTANCE` of NULL or `''` is -1; `UTL_RAW.CAST_TO_VARCHAR2('414243')` is
    `414243`; `DBMS_LOB.SUBSTR` of a `RAW` works on its hex text; `UTL_ENCODE.BASE64_ENCODE` takes a string;
    `UTL_RAW.LENGTH`, `UTL_RAW.CONCAT`, `DBMS_LOB.INSTR`, `DBMS_RANDOM` and `UTL_I18N` do not exist.
  - **Numeric:** `MOD(5, 0)` is ORA-01476 (Oracle 5); `CEIL(5)` and `FLOOR(5)` of a literal are `5.0`; `SIN(0)` prints
    `0.0`; `ABS('-3')` and `ROUND(5.5, 1.9)` are ORA-00904; `LOG(10)` is accepted; the literal `.5` is ORA-01426; a
    38-digit result prints in exponent form (`1.41666...E00`); `REMAINDER`, `NANVL`, `PI` and `BIN_TO_NUM` are
    ORA-00904.
  - **Date and time:** `EXTRACT(HOUR FROM DATE ...)` is 0 (Oracle ORA-30076) and `QUARTER` and `DOW` are accepted;
    `TIME_BUCKET` needs its origin argument; `CAST(timestamp AS DATE)` rounds; `TIMESTAMPADD` does not exist.
  - **Time zones** (a `TIMESTAMP WITH TIME ZONE` keeps its offset since main 178ea2df; see [date and time
    types](sql/oracle/data-types-datetime.md)): a region name is kept only as the offset it had at that instant
    (`FROM_TZ(..., 'Europe/Berlin')`, `AT TIME ZONE 'Europe/Berlin'`, a session in a region): `TZR` shows `+01:00` where
    Oracle shows `EUROPE/BERLIN`, `TZD` is empty (Oracle `CET`), `EXTRACT(TIMEZONE_REGION ...)` is `UNKNOWN` and
    `TIMEZONE_ABBR` `UNK` (Oracle `Europe/Berlin` and `CET`). A text inserted into a `TIMESTAMP WITH TIME ZONE` column
    is read as ISO, not by `NLS_TIMESTAMP_TZ_FORMAT`, as for `DATE` (`'2026-03-15 10:00:00 +02:00'` is taken, Oracle
    ORA-01843; `'15-MAR-26 10.00.00.000000 AM +02:00'` is ORA-01861; `CAST` and `TO_TIMESTAMP_TZ` read the NLS
    format). A `TIMESTAMP` literal as text has six fractional digits (Oracle nine: `CAST(TIMESTAMP '2026-03-15
    10:00:00 +02:00' AS VARCHAR2(60))`). A column made before main 178ea2df behaves as `TIMESTAMP WITH LOCAL TIME ZONE`
    (an instant, shown at the session zone's offset) until `ALTER TABLE ... MODIFY (c TIMESTAMP WITH TIME ZONE)`. A
    `VALUES` list (`FROM (VALUES (...)) v (a, b)`) or a derived column typed only by its type id keeps the instant, not
    the offset (`10:00 +02:00` comes out as `08:00 +00:00`). After `ALTER SESSION SET TIME_ZONE`, a JDBC client still
    converts a `TIMESTAMP WITH LOCAL TIME ZONE` value by its logon zone (`getString` gives `2026-03-15 13:30:00.0
    Asia/Kolkata` in a session set to `-05:00`; Oracle `2026-03-15 03:00:00.0 -05:00`: it tells the driver the new zone
    in a session-state message lexdb does not send; `TO_CHAR` is right). A logon time zone lexdb does not know (a
    client's `ORA_SDTZ` of `Foo/Bar`) leaves the session at `+00:00` (Oracle refuses the logon, ORA-00604). `MIN` and `MAX`
    of equal instants with different offsets show the first in lexdb's scan order, which is primary key order (Oracle's
    is the order the rows were inserted). `TO_CHAR` of a `TIMESTAMP WITH LOCAL TIME ZONE` refuses `TZH` and `TZM` (ORA-01821)
    and takes `TZR` and `TZD`, as Oracle; `TZR` is the offset (`+00:00`; Oracle `UTC`) as above.
  - **Conversion:** `TO_CHAR` number elements `EEEE`, `RN`, `XXXX`, `TM`, `B`, `V`, `C` are ORA-01481 and date elements
    `CC`, `E`, `RM`, `YEAR`, `SYYYY`, `DS`, `DL`, `TS` are ORA-01821 (the zone elements `TZH`, `TZM`, `TZR` and `TZD`
    work on a value with a time zone, and are ORA-01821 on one without, as in Oracle); `CAST(TRUE AS CHAR(5))` is
    `true ` (Oracle `TRUE `) and `LENGTH(TRUE)` is 1 (Oracle 4);
    `TO_CHAR(0, '999')` is blanks and `TO_CHAR(0, 'FM999')` is empty (Oracle `0`); the third argument of `TO_CHAR` and `TO_NUMBER`
    (NLS parameters) is ignored; `DDSP` gives `03`; `TO_CHAR` of an interval is NULL; `TO_BOOLEAN(NULL)` is false;
    a string inserted into a `DATE` column is read as `YYYY-MM-DD`, not by `NLS_DATE_FORMAT`; `CAST(... AS INTERVAL ...)`,
    `VALIDATE_CONVERSION` and `DEFAULT ... ON CONVERSION ERROR` are ORA-00900.
  - `ORA_DATABASE_NAME`, `RATIO_TO_REPORT`, `MEDIAN`, `STATS_MODE`, `CORR`, `COVAR_*`, `REGR_*`, `LNNVL`, `NANVL`,
    `GROUPING_ID` and `GROUP_ID` do not exist (ORA-00904); `LISTAGG ... OVER` is ORA-03001.
