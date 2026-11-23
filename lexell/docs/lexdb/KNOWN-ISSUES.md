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
- **Wrong arithmetic: an integer plus a decimal quotient of a variable gives an integer.** In the SQL Server door,
  `DECLARE @p decimal(5,2) = 10; SELECT 1 + @p / 100` gives 1 (`@p / 100` alone gives 0.1000...), so `UPDATE t SET
  salary = salary * (1 + @p / 100)` reports its rows and changes nothing. In the PostgreSQL door the same happens in
  a `LANGUAGE sql` procedure body with a numeric parameter (`1 + p / 100` gives 1), while a function body or a query
  gives 1.1. The two look like one bug in how a parameter's or variable's quotient is typed under `+`.


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
  - `BEGIN TRANSACTION ... WITH MARK` and `BEGIN DISTRIBUTED TRANSACTION` are 102; cursors (`DECLARE @c CURSOR`,
    `DECLARE c CURSOR FOR`) are 50000 and 102.
  - With `XACT_ABORT ON`, a failed `UPDATE` inside `BEGIN TRY` sends `(0 rows affected)` before the `CATCH` output.
- **Control of flow** (found writing those T-SQL pages):
  - **`RAISERROR('fatal', 20, 1)` hangs the session**: it never answers again. SQL Server ends the connection (and
    wants `WITH LOG` above severity 18). lexdb treats severities up to 19 as 16.
  - **A stale `CATCH` after a rethrow:** after a batch whose inner `CATCH` prints `ERROR_MESSAGE()` and rethrows with
    `THROW`, a later batch's `BEGIN TRY SELECT * FROM dbo.nothere; END TRY BEGIN CATCH ... END CATCH` gives Msg 208
    and then runs its `CATCH` with the old error (50000, 'inner failure'). Without the earlier batch, 208 ends the
    batch and the `CATCH` does not run (try-catch.md, example G).
  - A failed statement inside `BEGIN TRY` sends `(0 rows affected)` before the `CATCH` output.
  - `BREAK` or `CONTINUE` outside a loop is accepted (SQL Server: 135).
  - `RAISERROR` reads and ignores a placeholder's width, precision and flags (`%5d`, `%-6s`); `%o` prints decimal;
    `RAISERROR(50005, 16, 1)` gives Msg 50000 with the text "50005" (no `sys.messages`); `WITH LOG`, `NOWAIT` and
    `SETERROR` do nothing.
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
  - `EXEC @r = dbo.scalar_function` is 2812 (SQL Server allows it).
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
  - **Hangs:** `REGEXP_REPLACE('abc', 'b')` (two arguments) never answers; give `''` as the third argument.
  - **Binary:** hexadecimal literals are numbers (`SELECT 0x4142` is 16706; `CAST(0x4142 AS varbinary(10))` is
    50000); `CAST(varbinary AS varchar)` and `CONVERT(..., 1 | 2)` give `\x4142`; `LEN` of a binary value is 0,
    `SUBSTRING` and `LEFT` work on that hex text; `binary(n)` is not padded and a longer value into `varbinary(n)`
    is kept; `HASHBYTES` does not exist.
  - **Ranges and casts:** `tinyint` is not range-checked (`CAST(256 AS tinyint)`, a column storing 256 or -1);
    `smallmoney` takes up to 999999.9999; `TRY_CAST(300 AS tinyint)` and `TRY_CAST('12' AS decimal(2,0))` are not
    NULL; `CAST('yes' AS bit)` is 1; `SUM` of `int` does not overflow; `CAST(0 AS datetime)` is 50000.
  - **Character:** `char(n)` and `nchar(n)` are not padded; `DECLARE @n varchar = 'abcdef'` and `CAST(x AS varchar)`
    keep every character; assigning a long string to a `varchar(10)` variable is error 2628 (SQL Server cuts it);
    `ISNULL` is `COALESCE` (the type of the first argument is not kept); `DATALENGTH` counts two bytes per
    character of every string type and gives 0 for a `real`.
  - **Dates:** only ISO layouts are read (`'20260315'`, `'March 15, 2026'` and `'03/15/2026'` are 241, with any
    style); the seventh fractional digit is lost; a `datetimeoffset` is converted to UTC and shows `+00:00`;
    `DATEPART(tzoffset | tz | iso_week)` is 155; `datetime + 1` is 195; `datetime - datetime` is an interval
    (`1 day 10:00:00`); `date + 1` and `date - date` are accepted; `CAST('2026-03-15 13:45:30' AS time)` is 241;
    `ISDATE`, `SWITCHOFFSET`, `TODATETIMEOFFSET`, `DATETIMEFROMPARTS`, `TIMEFROMPARTS` and `DATETIME2FROMPARTS` are
    195; conversion styles 9, 13, 14, 22, 109, 113 and 114 are 281.
  - **Maths:** `LOG(100, 10)` is 0.5 (the arguments are swapped; SQL Server: 2); `ROUND(123.4567, -1)` on a decimal
    is 8115; `SQRT(-1)` and `LOG(0)` are 50000, `ASIN(2)` and `EXP(710)` 8115 with PostgreSQL's text; `5 / 2.0E0` is
    a decimal (6 places); `real / int` is computed as a float.
  - **Functions that are lenient:** `IIF(1, 'a', 'b')` gives `b` (SQL Server: 4145); `GREATEST(1)`, `CONCAT('a')`,
    `SUBSTRING('abcdef', 2)` and `LEFT('abc', -1)` are taken (SQL Server: 189, 174, 536); `TRANSLATE('abc', 'abc',
    'xy')` is accepted (9828); `ASCII('')` is 0; `CASE` and `COALESCE` over `1` and `2.5` give `1`, not `1.0`.
  - **`FORMAT`:** with `de-DE` a date format is still English (`d` gives `3/5/2026`); a custom format with sections
    stops at the first `;` (`FORMAT(-5, '0;(0)')` is -5); literals between digit placeholders are dropped
    (`FORMAT(123456789, '###-##-####')`); `FORMAT(CAST('14:07:09' AS time), 'hh\:mm')` is NULL.
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
    `sa`; `sys.dm_exec_sessions` is one recorded row; `INFORMATION_SCHEMA.SCHEMATA` has no `dbo`, and `ROUTINES` and
    `PARAMETERS` have no T-SQL procedures; `INFORMATION_SCHEMA.DOMAINS`, `COLUMN_PRIVILEGES` and
    `VIEW_COLUMN_USAGE` do not exist; `sys.database_role_members`, `sys.partitions` and `sys.dm_exec_requests` do
    not exist (208); `sys.types` gives `decimal` scale 38; every decimal expression is `decimal(38,6)` in
    `sys.columns`.
  - A `datetime` column takes PostgreSQL's special strings (`INSERT ... VALUES ('tomorrow')`).

## Oracle door

- **A global temporary table's definition is private to the session that made it**, on the master as on a
  replica. In Oracle the definition is a schema object that every session sees, and only the rows are private to a
  session.

- **A bare name finds a table of the PostgreSQL door's `public` schema, and blocks `CREATE TABLE` of that name.**
  With a table `city` made in the PostgreSQL door, `CREATE TABLE city (...)` in the Oracle door (user `SA`) fails with
  ORA-00955 "name is already used by an existing object", and `SELECT * FROM city` reads `public.city`. In Oracle a
  public synonym does not stop a user from making an object of the same name in its own schema.
