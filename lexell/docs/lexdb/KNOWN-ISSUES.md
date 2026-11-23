# Known issues

Bugs and gaps found while writing and checking these pages (lexdb built from main at 4fba817b, 2026-11-23). They
are not fixed here: the pages describe what lexdb does. Each "Differences" section of the reference lists the
smaller differences of its statement.

## All doors

- **Replicas and temporary objects** (main f8e3d6d6, design/lexdb.md 9.137 "As built (phase 5)"):
  - SQL Server door: `#temp` tables, `SELECT ... INTO #x` and table variables work on a replica.
  - PostgreSQL door: temporary tables are refused with 25006, as on a hot standby.
  - Oracle door: `CREATE GLOBAL TEMPORARY TABLE` on a replica is ORA-16000, as on a standby, and DML on a global
    temporary table is not available there: Active Data Guard allows it for a table the primary defined, but in
    lexdb no such definition reaches a replica's session (see the Oracle door's entry below).

## PostgreSQL door

- **pgjdbc fails with its default settings.** lexdb takes binary parameters only for `int2`, `int4`, `int8`,
  `bool`, `float4`, `float8` and text types, and sends no binary results. pgjdbc 42.7 sends `BigDecimal`, `UUID` and
  `byte[]` parameters in binary ("a binary parameter of type 1700 is not supported"), and after a prepared statement
  has run five times (`prepareThreshold`) it asks for binary results, so the sixth run fails ("results in binary are
  not supported"). `binaryTransfer=false` in the URL avoids both, except for `setBytes`, which is always binary.
  ([connect/postgresql.md](connect/postgresql.md#java-pgjdbc))
- **Cancel requests are ignored.** psql's Ctrl-C, JDBC's `Statement.cancel()` and libpq's `PQcancel` do not stop a
  running statement. `statement_timeout` does.
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
  - `VALUES (1), (true)` gives 42804 with a vaguer message than PostgreSQL's (`VALUES types integer and boolean
    cannot be matched`).
- **WITH:**
  - `LIMIT` does not stop a recursive query: `WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r)
    SELECT * FROM r LIMIT 3` runs to 54001 after `max_recursion` rounds (PostgreSQL returns 3 rows).
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
  - Two column-level primary keys are not refused: `CREATE TABLE t (a int PRIMARY KEY, b int PRIMARY KEY)` makes
    one key on (a, b) (PostgreSQL: 42P16).
  - `ALTER TABLE | VIEW | SEQUENCE ... OWNER TO postgres` is `role "postgres" does not exist`, though `current_user`
    is `postgres` and `pg_roles` lists it. `OWNER TO` a role made with `CREATE ROLE` works.
  - `COMMENT ON` is a syntax error.
  - Syntax errors where PostgreSQL has a feature: `CREATE TABLE t ()`, `LIKE`, `INHERITS`, `PARTITION BY`,
    `WITH (fillfactor = ...)`, `TABLESPACE`, a column's `PRIMARY KEY INCLUDE (...)` / `DEFERRABLE`,
    `CREATE TABLE ... AS TABLE t` / `AS EXECUTE`, `ALTER COLUMN ... SET STATISTICS`, `ALTER COLUMN ... TYPE ...
    COLLATE`. At table level `INCLUDE`, `WITH`, `USING INDEX TABLESPACE` and `DEFERRABLE` on a key are 0A000.
  - `ALTER COLUMN ... TYPE` without `USING` folds its hint into the message (42804).
  - `DROP ... CASCADE` gives no NOTICE naming what it drops; the 2BP01 refusals carry their hints in the message.
- **Views:**
  - While a view reads table t, `ALTER TABLE t DROP COLUMN` (any column, even one the view does not use) and
    `ALTER TABLE t SET SCHEMA` are refused (2BP01, "lexdb keeps a view's text"). PostgreSQL refuses only the drop of
    a column the view uses. The other way round, `ALTER COLUMN ... TYPE` of a column a view uses is allowed, where
    PostgreSQL refuses it (0A000).
  - `SELECT *` in a view is expanded when the view is read, not when it is made: a column added to the table later
    shows in the view.
  - `pg_get_viewdef`, `pg_views.definition` and `information_schema.views` give the view's text as written (with
    its `;`), not PostgreSQL's rewritten form.
  - `CREATE OR REPLACE VIEW` with columns renamed or reordered says `cannot drop columns from view` (PostgreSQL:
    `cannot change name of view column ...`).
  - `CREATE RECURSIVE VIEW` and `ALTER VIEW v RENAME COLUMN` are syntax errors.
- **Sequences:** `DROP SEQUENCE s` succeeds while a column default calls `nextval('s')`, and the next insert fails
  with `relation "s" does not exist` (PostgreSQL: 2BP01). `DROP SEQUENCE t` of a table is 42P01 `sequence "t" does
  not exist` (PostgreSQL: 42809 `"t" is not a sequence`).
- **Indexes:**
  - `DROP INDEX t_pkey` is 42704 `index "t_pkey" does not exist`, though `pg_indexes` lists it and `ALTER INDEX
    t_pkey RENAME` works (PostgreSQL: 2BP01, the index belongs to a constraint).
  - `DROP INDEX` takes one name, without `CASCADE` or `RESTRICT`: `DROP INDEX a, b` is a syntax error.
  - `pg_indexes.indexdef` shows an expression index on `(n + 1)` as `(((n + 1)))` (PostgreSQL: `((n + 1))`).
  - `INCLUDE (...)`, `WITH (...)`, `NULLS NOT DISTINCT` and `TABLESPACE` are syntax errors; methods other than
    btree are 0A000; `CONCURRENTLY` is accepted and changes nothing.
- **Transactions** (found writing the transaction pages):
  - `SHOW transaction_read_only` says `off` inside `BEGIN READ ONLY`, which refuses writes (25006).
  - `BEGIN` ignores words it does not know: `BEGIN nonsense words here` starts a block (PostgreSQL: 42601).
  - `SET TRANSACTION READ ONLY` and `SET SESSION CHARACTERISTICS AS TRANSACTION ...` are accepted and do nothing.
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
  - **Wrong arithmetic in a procedure body:** in a `LANGUAGE sql` procedure, `1 + p / 100` with a numeric parameter
    `p = 10` gives 1, as if the division were of integers, so `SET salary = salary * (1 + p / 100)` changes nothing.
    The same expression in a function body or a query gives 1.1; `p / 100` alone is right.
  - Overloads: with `add(int, int)` and `add(numeric, numeric)`, `SELECT add(2, 3)` calls the numeric one
    (PostgreSQL: the integer one).
  - A call's result column is named after its type or expression (`numeric`, `int4`, `?column?`), not after the
    function.
  - 0A000 or 42883 in a query: a function whose body reads tables given a column or subquery as an argument; a
    function with several OUT parameters; a function whose body writes; a set-returning function in the select
    list; named arguments (`CALL` takes them); calling a VARIADIC function.
  - `ALTER FUNCTION` and `ALTER PROCEDURE` are 0A000 ("only ALTER TABLE, ALTER INDEX and ALTER SCHEMA are
    supported"); `SECURITY DEFINER` is accepted and ignored.
- **Maintenance and statistics:** `pg_stats` does not exist (42P01) and `pg_class.reltuples` stays -1 after `ANALYZE`
  (`pg_stat_user_tables.n_live_tup` is right). `REINDEX` and `CLUSTER` are checked and do nothing; `VACUUM` (and
  `VACUUM FULL`) rewrites row-form leaves as column leaves and gives no space back.
- **COPY:** `WITH (FORMAT binary)` is 0A000; once, after a COPY error at the end of a psql script, the session gave
  no answer for 120 s (not narrowed down).
- **Data types** (found writing the type pages):
  - **Integer constant arithmetic does not overflow:** `2147483647::int + 1` gives 2147483648 (and
    `32767::smallint + 1::smallint` 32768), while `pg_typeof` says integer. On a column it is 22003, as in PostgreSQL.
  - **Enums compare as text outside `WHERE` and `ORDER BY`:** with `mood ('sad','ok','happy')`, `SELECT 'ok'::mood <
    'happy'::mood` gives f; `min`, `max` and `greatest` of enums go by the labels' text. `'angry'::mood` is accepted
    for a label that does not exist (an `INSERT` of it is 22P02).
  - `INTERVAL '1' DAY` reads `day` as an alias (one second); `INTERVAL '1-2' YEAR TO MONTH` is 42601.
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
  - Mixed types are not checked in `CASE`, `UNION` and `coalesce` (`coalesce(1, true)` gives 1; PostgreSQL: 42804).
  - `1 = 'a'` is 42883 `operator does not exist` (PostgreSQL: 22P02).
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
  - NOT NULL constraints have no rows in `pg_constraint` or `information_schema.table_constraints` (PostgreSQL 18:
    contype `n`).
  - `pg_rewrite` is empty, though a view's `pg_class.relhasrules` is t; `pg_depend` holds only column-to-sequence
    rows; `pg_opclass` is empty; `pg_am` lists `hash`, which `CREATE INDEX` refuses.
  - Identity sequences are in `pg_sequences` but not in `information_schema.sequences`.
  - `ALTER TYPE ... ADD VALUE ... BEFORE` renumbers `pg_enum.enumsortorder` (1, 2, 3; PostgreSQL: 1, 1.5, 2).
  - `0::regclass` shows `0` (PostgreSQL: `-`); `pg_type.oid` and other `oid` and `regtype` columns are sent as text,
    so psql aligns them left.
  - Missing (42P01): `pg_stat_activity` (monitoring tools need it), `pg_stats`, `pg_locks`, `pg_operator`,
    `pg_cast`, `pg_authid`, `pg_timezone_names`, `pg_stat_all_tables`, `pg_statio_user_tables`, and
    `information_schema` `triggers`, `domains`, `column_privileges`, `enabled_roles`, `applicable_roles`,
    `element_types`.
- **Errors:** `SELECT $1` in a simple query is 08P01 `there is no parameter $1` (PostgreSQL: 42P02). A
  `max_statement_mem` of 1 kB did not stop a top-N sort over 100,000 rows (not narrowed down).


## SQL Server door

- **Error text.** Many errors carry SQL Server's number and severity with lexdb's (PostgreSQL's) text, for example
  2714 `relation "t1" already exists` where SQL Server says `There is already an object named 't1' in the database.`,
  and 2627 `duplicate key value violates unique constraint "t1_pkey"`.
- **`SET FMTONLY ON` stays on after mssql-jdbc's `SQLServerBulkCopy`.** After `writeToServer`, every later query on
  that connection returns its columns and no rows, until the program runs `SET FMTONLY OFF` (checked with mssql-jdbc
  13.6.2; the rows are loaded). The same happens after an `executeBatch` sent as bulk copy
  (`useBulkCopyForBatchInsert=true`). The driver's metadata batch (`SET FMTONLY ON ... SET FMTONLY OFF`) leaves the
  option on in lexdb. bcp and SqlBulkCopy were not affected when checked during development (design/lexdb-tds.md
  section 14). ([bulk loading](bulk-load.md#from-java-sqlserverbulkcopy))
- **Error line numbers** are always 1 (`Msg 2627, Level 14, State 1, Line 1`), whatever line of the batch failed.
- **`UPDATE STATISTICS`** is a syntax error (102), on the master and on a replica.
- **Missing functions:** `UNICODE`, `STDEV`, `STDEVP`, `VAR`, `VARP` and `ATN2` give error 195 ("function ... does
  not exist"). An error 195 ends the batch, as SQL Server's compile errors do.
- **`INSERT TOP (n)`** is error 102, and a table hint on an `INSERT`'s target (`INSERT INTO t WITH (TABLOCK)`) is
  error 156. Table hints in `FROM` are read and ignored.
- **No `CREATE LOGIN`.** `CREATE USER name WITH PASSWORD = '...'` is error 102; `CREATE ROLE name LOGIN PASSWORD
  '...'` (PostgreSQL's form) works in this door.
- **Queries and DML** (found writing the T-SQL query pages):
  - `AVG(x) OVER (...)` is error 50000 (`column ... must appear in the GROUP BY clause`); `SUM`, `MIN`, `MAX` and
    `COUNT` with `OVER` work. `COUNT_BIG(*) OVER (...)` is 195.
  - A `VALUES` derived table's strings conflict on collation when joined to a column: 468 "Cannot resolve the
    collation conflict between "SQL_Latin1_General_CP1_CI_AS" and "default"" (`COLLATE DATABASE_DEFAULT` avoids it).
  - `TRUNCATE TABLE` does not reset the `IDENTITY` (the next id goes on; SQL Server starts again at the seed).
  - Views are read-only (50000), and a CTE cannot be the target of `UPDATE`, `DELETE` or `MERGE` (208).
  - `SELECT INTO` loses column attributes: `nvarchar(30)` becomes `nvarchar(max)`, a decimal gets wider, `NOT NULL`
    and `IDENTITY` are lost. `SELECT IDENTITY(int, 1, 1) AS n ... INTO` is 207.
  - Error 102 for `PIVOT`, `UNPIVOT`, `FOR XML`, `FOR JSON`, `TABLESAMPLE`, `$IDENTITY`, join hints (`INNER LOOP
    JOIN`), `FOR SYSTEM_TIME`, `GROUP BY ... WITH ROLLUP` / `WITH CUBE`; `GROUPING_ID` is 195.
  - `TOP (subquery)` is 156; `UPDATE TOP (n) PERCENT` 102; `DELETE TOP (n) PERCENT` 208; `MERGE TOP ... PERCENT`
    50000.
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
  - **`CLUSTERED` and `NONCLUSTERED` are refused everywhere** (102): `PRIMARY KEY CLUSTERED (id)`, `CREATE
    NONCLUSTERED INDEX`. Most scripts SSMS generates use them.
  - `DROP INDEX ix ON dbo.t`, SQL Server's usual form, is 156; `DROP INDEX t.ix` is 50000; only `DROP INDEX ix` and
    `DROP INDEX dbo.ix` work, one at a time.
  - `ALTER TABLE t ADD CONSTRAINT df DEFAULT 0 FOR col` is 102; a DEFAULT constraint's own name is not kept (it shows
    as `DF_table_col`), and `DROP CONSTRAINT` finds it by neither name.
  - `ALTER TABLE` takes one action per statement (`ADD b int, c int` is 50000), and refuses `WITH CHECK ADD`, `WITH
    NOCHECK ADD`, `NOCHECK CONSTRAINT`, `CHECK CONSTRAINT`, `SET (LOCK_ESCALATION = ...)`, `SWITCH`, `REBUILD` and
    `DISABLE TRIGGER` (50000).
  - A column-level `CONSTRAINT fk FOREIGN KEY REFERENCES t (c)` is 102 (without `FOREIGN KEY` it works).
  - Storage and index options are syntax errors: `ON [PRIMARY]`, `TEXTIMAGE_ON`, `WITH (DATA_COMPRESSION = ...)`,
    `WITH (FILLFACTOR = ...)`, `WITH (ONLINE = ON)`; so are `ROWGUIDCOL`, `SPARSE`, `FILESTREAM`, `MASKED WITH`, `NOT
    FOR REPLICATION`, `GENERATED ALWAYS AS ROW START`, `PRIMARY KEY (a DESC)` and an inline `INDEX ix (c)`.
  - A `rowversion` (`timestamp`) column is never filled in (NULL).
  - A table with two `IDENTITY` columns is accepted (SQL Server: 2744).
  - `##g` is a session-private temporary table, as `#g` is.
  - Alias types (`CREATE TYPE dbo.phone FROM varchar(20)`) are 156.
  - `ALTER INDEX ... REBUILD`, `REORGANIZE` and `DISABLE` and `CREATE STATISTICS` are 50000; `CREATE COLUMNSTORE
    INDEX` is 102; `sp_helpindex`, `sp_helptext` and `sp_refreshview` are 2812.
  - A unique index over rows that clash is 2627 (SQL Server: 1505).
  - Views: `WITH SCHEMABINDING`, `WITH ENCRYPTION` and `WITH CHECK OPTION` are 50000; `CREATE VIEW` need not be first
    in its batch (SQL Server: 111); `DROP TABLE` of a table a view reads and `DROP VIEW` of a view another view reads
    are refused (50000; SQL Server allows both).
  - `DROP TABLE` of a table a foreign key refers to is 50000 (SQL Server: 3726). A sequence a column `DEFAULT` uses
    can be dropped, and the next `INSERT` fails with 208 (SQL Server refuses the drop: 3729).
  - Sequences: `NO CACHE` is 102; `AS decimal(10,0)` is 50000; without `AS` and `START WITH` a sequence starts at 1
    (SQL Server: a bigint from its minimum); `NEXT VALUE FOR s` twice in one row gives two values (SQL Server: the
    same); `NEXT VALUE FOR s OVER (...)` is 102; `sp_sequence_get_range` is 2812; past `MAXVALUE` the error is 50000
    (SQL Server: 11728); `ALTER SEQUENCE s MAXVALUE 100` of a sequence started at 1000 is refused even with
    `RESTART WITH 50`.
  - Other error numbers: `DROP TABLE`, `VIEW` or `SEQUENCE` of a missing object is 208 (SQL Server: 3701), `DROP
    INDEX` of a missing index 50000 (3701), adding a column that exists 50000 (2705), dropping an unknown column 207
    (4924), adding a `NOT NULL` column without a default to a table with rows 515 (4901).


## Oracle door

- **A global temporary table's definition is private to the session that made it**, on the master as on a
  replica. In Oracle the definition is a schema object that every session sees, and only the rows are private to a
  session.

- **A bare name finds a table of the PostgreSQL door's `public` schema, and blocks `CREATE TABLE` of that name.**
  With a table `city` made in the PostgreSQL door, `CREATE TABLE city (...)` in the Oracle door (user `SA`) fails with
  ORA-00955 "name is already used by an existing object", and `SELECT * FROM city` reads `public.city`. In Oracle a
  public synonym does not stop a user from making an object of the same name in its own schema.
- **ojdbc does not follow the read-only redirect.** A JDBC thin connection to the master with the read-only service
  (`lexdb_ro`) fails in the driver with `ORA-18951: NL exception was generated: TNS-04605: Invalid syntax error:
  Unexpected char or LITERAL " " before or at ( DESCRIPTION ...`: ojdbc 23.26 cannot parse the REDIRECT packet's data.
  python-oracledb and Lexell's `oracle` module follow it (design/lexdb.md 9.137). Connecting to a replica's own
  listener works with ojdbc.
- **`SYS_CONTEXT('USERENV', 'NETWORK_PROTOCOL')` says `tcp` on a TCPS connection**, where Oracle says `tcps`.
