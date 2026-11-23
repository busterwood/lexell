# Known issues

Bugs and gaps found while writing and checking these pages (lexdb built from main at 4fba817b, 2026-11-23). They
are not fixed here: the pages describe what lexdb does. Each "Differences" section of the reference lists the
smaller differences of its statement.

## All doors

- **Replicas: temporary objects not built yet.** The pages describe a replica's T-SQL `#temp` tables and table
  variables, and Oracle DML on global temporary tables, as working, per design/lexdb.md 9.137 phase 5. Until that
  phase lands, a replica refuses them as it refuses any write (3906, ORA-16000). The replica examples for them in
  [replicas](replicas.md) show no output for that reason.

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
- **Missing functions:** `UNICODE`, `STDEV`, `STDEVP`, `VAR`, `VARP` and `ATN2` give error 195 ("function ... does
  not exist"). An error 195 ends the batch, as SQL Server's compile errors do.
- **`INSERT TOP (n)`** is error 102, and a table hint on an `INSERT`'s target (`INSERT INTO t WITH (TABLOCK)`) is
  error 156. Table hints in `FROM` are read and ignored.
- **No `CREATE LOGIN`.** `CREATE USER name WITH PASSWORD = '...'` is error 102; `CREATE ROLE name LOGIN PASSWORD
  '...'` (PostgreSQL's form) works in this door.

## Oracle door

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
