# PostgreSQL door: SQL reference

The PostgreSQL door takes PostgreSQL's SQL. lexdb follows PostgreSQL 18, with some of PostgreSQL 19 (`WAIT FOR
LSN`, `ON CONFLICT DO SELECT`), and reports itself as server version 16.0. Each page names what lexdb lacks or does
differently.

This index lists everything the door takes today. Pages not written yet are listed without a link.

## Statements

### Queries

| Statement | What it does |
|---|---|
| SELECT | Queries: joins, `LATERAL`, grouping, `GROUPING SETS`, windows, `DISTINCT ON`, `LIMIT`/`OFFSET`/`FETCH`, `FOR UPDATE`, set operations, `MATCH_RECOGNIZE`. `SELECT ... INTO` makes a table. lexdb's `WAIT n SECONDS` suffix waits for rows. |
| VALUES | A table of literal rows. |
| WITH | Common table expressions, `WITH RECURSIVE`, before `SELECT`, `INSERT`, `UPDATE`, `DELETE` or `MERGE`. |
| EXPLAIN | The plan of a `SELECT`, `UPDATE`, `DELETE` or `MERGE`; `EXPLAIN ANALYZE` of a `SELECT`. |

### Changing data

| Statement | What it does |
|---|---|
| [INSERT](insert.md) | Adds rows; `ON CONFLICT`, `RETURNING`. |
| UPDATE | Changes rows; `FROM`, `RETURNING`, lexdb's `WITH (batch_rows n)`. |
| DELETE | Removes rows; `USING`, `RETURNING`, `WITH (batch_rows n)`. |
| MERGE | Inserts, updates or deletes by a join. |
| TRUNCATE | Empties tables; `RESTART IDENTITY`, `CASCADE`. |
| COPY | Bulk load and unload, text and CSV: see also [bulk loading](../../bulk-load.md#postgresql-copy). |

### Tables, indexes and other objects

| Statement | What it does |
|---|---|
| CREATE TABLE | Tables: temporary and unlogged, constraints, identity, serial and generated columns. |
| CREATE TABLE AS | A table from a query. |
| ALTER TABLE | Columns, constraints, types, defaults, identity, renames, `SET SCHEMA`, `OWNER TO`. |
| DROP TABLE | |
| CREATE INDEX | B-tree indexes, unique, on expressions, partial, `CONCURRENTLY`. |
| ALTER INDEX, DROP INDEX | Rename; drop. |
| CREATE VIEW, ALTER VIEW, DROP VIEW | Views (read-only). |
| CREATE SEQUENCE, ALTER SEQUENCE, DROP SEQUENCE | Sequences. |
| CREATE SCHEMA, ALTER SCHEMA, DROP SCHEMA | Schemas. |
| CREATE TYPE, ALTER TYPE, DROP TYPE | Enum types. |
| CREATE FUNCTION, CREATE PROCEDURE, DROP FUNCTION, DROP PROCEDURE | Routines in `LANGUAGE sql` (`AS '...'`, `BEGIN ATOMIC`, `RETURN`). |
| CALL | Calls a procedure. |
| COMMENT ON | Accepted; comments are not kept. |

### Roles and privileges

| Statement | What it does |
|---|---|
| CREATE ROLE, CREATE USER | Roles, with `LOGIN`, `SUPERUSER`, `PASSWORD`. |
| ALTER ROLE, ALTER USER, DROP ROLE, DROP USER | |
| GRANT, REVOKE | Table, view, sequence, schema, function and database privileges; role membership. |
| SET ROLE, SET SESSION AUTHORIZATION | |

### Transactions

| Statement | What it does |
|---|---|
| BEGIN, START TRANSACTION | `READ ONLY`, `READ WRITE`, `ISOLATION LEVEL` (every read-write transaction is serializable). |
| COMMIT, END | |
| ROLLBACK, ABORT | |
| SAVEPOINT, RELEASE SAVEPOINT, ROLLBACK TO SAVEPOINT | |
| SET CONSTRAINTS | |

### Session and server

| Statement | What it does |
|---|---|
| SET, RESET, SHOW | Settings; `SET TIME ZONE`, `SET search_path`. |
| DISCARD, DEALLOCATE | |
| WAIT FOR LSN | Waits on a replica for a commit (PostgreSQL 19). See [replicas](../../replicas.md). |
| ANALYZE | Gathers the planner's statistics. |
| VACUUM, CHECKPOINT, REINDEX, CLUSTER | `CHECKPOINT` writes one; the others are accepted. |

### Not in this door

`DO`, PL/pgSQL (functions in any language but `sql`: 42704), triggers, `LOCK TABLE`, SQL-level `PREPARE` and
`EXECUTE` (the protocol's prepared statements work), cursors (`DECLARE`, `FETCH`), `LISTEN`/`NOTIFY`, materialized
views, domains, extensions, `CREATE DATABASE`.

## Data types

| Type | Names |
|---|---|
| Integers | `smallint` (`int2`), `integer` (`int`, `int4`), `bigint` (`int8`), `smallserial`, `serial`, `bigserial` |
| Exact numbers | `numeric(p, s)`, `decimal(p, s)`: precision up to 38 |
| Floating point | `real` (`float4`), `double precision` (`float8`), `float(p)` |
| Text | `text`, `varchar(n)` (`character varying`), `char(n)` (`character`, `bpchar`), `"char"`, `name` |
| Binary | `bytea` |
| Boolean | `boolean` (`bool`) |
| Date and time | `date`, `time(p)`, `timestamp(p)`, `timestamptz`, `interval`. No `time with time zone`. |
| UUID | `uuid` |
| Arrays | `type[]` of the types above (one dimension) |
| Enums | `CREATE TYPE ... AS ENUM` |
| System | `oid`, `regclass`, `regtype`, `regnamespace`, `regproc`, `regprocedure`, `regrole`, `int2vector`, `oidvector` |

Not available: `json`, `jsonb`, `xml`, `money`, network and geometric types, ranges, domains, composite types.

## Functions

| Family | Functions |
|---|---|
| String | `lower`, `upper`, `initcap`, `length`, `char_length`, `octet_length`, `substr`, `substring`, `position`, `strpos`, `overlay`, `trim`, `btrim`, `ltrim`, `rtrim`, `lpad`, `rpad`, `left`, `right`, `repeat`, `replace`, `translate`, `reverse`, `split_part`, `concat`, `concat_ws`, `format`, `chr`, `ascii`, `quote_literal`, `quote_nullable`, `quote_ident`, `starts_with`, `md5`, `encode`, `decode`, `to_hex`, `to_bin`, `to_oct`, `unistr`, `casefold`, `string_to_array`, `string_to_table` |
| Pattern matching | `LIKE`, `ILIKE`, `SIMILAR TO`, `~` and its forms, `regexp_replace`, `regexp_match`, `regexp_matches`, `regexp_like`, `regexp_count`, `regexp_instr`, `regexp_substr`, `regexp_split_to_table`, `regexp_split_to_array` |
| Mathematical | `abs`, `sign`, `ceil`, `ceiling`, `floor`, `round`, `trunc`, `div`, `mod`, `gcd`, `lcm`, `power`, `sqrt`, `cbrt`, `exp`, `ln`, `log`, `log10`, `pi`, `degrees`, `radians`, `random`, `width_bucket`, `scale`, `min_scale`, `trim_scale`, `num_nulls`, `num_nonnulls`, `bit_count`, `erf`, `erfc`, `gamma`, `lgamma`, `crc32`, `crc32c` |
| Trigonometric | `sin`, `cos`, `tan`, `cot`, `asin`, `acos`, `atan`, `atan2`, `sinh`, `cosh`, `tanh`, `asinh`, `acosh`, `atanh`, and the degree forms `sind` ... `atan2d` |
| Date and time | `now`, `current_date`, `current_time`, `current_timestamp`, `localtime`, `localtimestamp`, `transaction_timestamp`, `statement_timestamp`, `clock_timestamp`, `date_part`, `EXTRACT`, `date_trunc`, `date_bin`, `age`, `make_date`, `make_interval`, `make_timestamp`, `make_timestamptz`, `to_timestamp`, `isfinite`, `date_add`, `date_subtract`, `AT TIME ZONE` |
| Formatting | `to_char`, `to_number`, `to_date`, `to_timestamp` |
| Conditional | `CASE`, `coalesce`, `nullif`, `greatest`, `least`, `error_on_null` |
| Arrays | `array_append`, `array_prepend`, `array_cat`, `array_remove`, `array_replace`, `array_position`, `array_positions`, `array_to_string`, `array_length`, `array_lower`, `array_upper`, `array_ndims`, `array_dims`, `cardinality`, `trim_array`, `array_reverse`, `array_shuffle`, `array_sample`, `unnest`, `generate_subscripts` |
| UUID | `gen_random_uuid`, `uuidv4`, `uuidv7`, `uuid_extract_version`, `uuid_extract_timestamp` |
| JSON | `json_build_object`, `jsonb_build_object` (text results; there is no JSON type) |
| Aggregate | `count`, `sum`, `avg`, `min`, `max`, `string_agg`, `array_agg`, `bool_and`, `bool_or`, `every`, `bit_and`, `bit_or`, `bit_xor`, `any_value`, `stddev`, `stddev_samp`, `stddev_pop`, `variance`, `var_samp`, `var_pop`, `percentile_cont`, `percentile_disc` |
| Window | `row_number`, `rank`, `dense_rank`, `percent_rank`, `cume_dist`, `ntile`, `lag`, `lead`, `first_value`, `last_value`, `nth_value` (with `IGNORE NULLS`), and every aggregate with `OVER` |
| Set-returning | `generate_series`, `unnest [WITH ORDINALITY]`, `regexp_matches`, `regexp_split_to_table`, `string_to_table` |
| Sequences | `nextval`, `currval`, `setval`, `lastval` |
| Session | `current_user`, `session_user`, `current_role`, `current_schema`, `current_catalog`, `current_database`, `version`, `current_setting`, `set_config`, `pg_backend_pid`, `txid_current`, `pg_current_xact_id`, `pg_typeof` |
| Replication | `pg_is_in_recovery`, `pg_current_wal_lsn`, `pg_current_wal_insert_lsn`, `pg_current_wal_flush_lsn`, `pg_last_wal_replay_lsn`, `pg_last_wal_receive_lsn` |
| Advisory locks | `pg_advisory_lock`, `pg_try_advisory_lock`, `pg_advisory_xact_lock`, `pg_try_advisory_xact_lock`, `pg_advisory_unlock`, `pg_advisory_unlock_all`, and their `_shared` forms |
| Catalog | `pg_get_userbyid`, `pg_table_is_visible`, `pg_type_is_visible`, `pg_function_is_visible`, `pg_get_expr`, `pg_get_constraintdef`, `pg_get_indexdef`, `pg_get_viewdef`, `pg_get_functiondef`, `pg_get_function_arguments`, `pg_get_function_result`, `pg_get_serial_sequence`, `to_regclass`, `to_regtype`, `to_regnamespace`, `obj_description`, `col_description`, `has_table_privilege`, `has_schema_privilege`, `has_database_privilege`, `has_sequence_privilege`, `has_function_privilege`, `has_any_column_privilege`, `pg_relation_size`, `pg_total_relation_size`, `pg_table_size`, `pg_indexes_size`, `pg_database_size`, `pg_size_pretty`, `format_type`, `pg_encoding_to_char` |

## Operators

Comparison (`=`, `<>`, `!=`, `<`, `<=`, `>`, `>=`), `BETWEEN [SYMMETRIC]`, `IN`, `ANY`/`SOME`/`ALL`, `EXISTS`,
`IS [NOT] NULL / TRUE / FALSE / UNKNOWN / DISTINCT FROM`; arithmetic (`+ - * / % ^`, unary `-` `+`); bitwise
(`& | # ~ << >>`); `||` for text and arrays; array `@>`, `<@`, `&&`; pattern `LIKE`, `ILIKE`, `SIMILAR TO`,
`~ ~* !~ !~*`; `::` casts, `AT TIME ZONE`, `COLLATE` (read and ignored); `AND`, `OR`, `NOT`.

## System catalog

- **pg_catalog**: `pg_namespace`, `pg_class`, `pg_attribute`, `pg_attrdef`, `pg_type`, `pg_index`,
  `pg_constraint`, `pg_description`, `pg_sequence`, `pg_sequences`, `pg_enum`, `pg_collation`, `pg_am`,
  `pg_opclass`, `pg_database`, `pg_proc`, `pg_roles`, `pg_user`, `pg_auth_members`, `pg_inherits`, `pg_depend`,
  `pg_tables`, `pg_views`, `pg_indexes`, `pg_matviews`, `pg_settings`, `pg_stat_user_tables`, `pg_language`,
  `pg_extension`, `pg_tablespace`, `pg_trigger`, `pg_rewrite`, `pg_policy`, `pg_publication` and others psql reads
  (empty where lexdb has no such object).
- **information_schema**: `schemata`, `tables`, `columns`, `views`, `table_constraints`, `key_column_usage`,
  `referential_constraints`, `constraint_column_usage`, `check_constraints`, `sequences`, `table_privileges`,
  `role_table_grants`, `routines`, `parameters`, `routine_privileges`, `role_routine_grants`.

## Settings

`SET` and `SHOW`: `search_path`, `TimeZone`, `statement_timeout`, `max_recursion`, `max_statement_mem`,
`max_match_steps`, and lexdb's `lexdb_planner` (`cost` or `rules`), `lexdb_batch`, `lexdb_autoanalyze`,
`lexdb_range_delete`. `SHOW` also gives `transaction_isolation`, `transaction_read_only`, `server_version`,
`server_encoding`, `client_encoding`, `DateStyle`, `IntervalStyle`, `standard_conforming_strings`, `is_superuser`,
`in_hot_standby` and other fixed values. Other names are accepted and ignored by `SET`.

## Errors

Errors carry PostgreSQL's SQLSTATE codes: 23505 (unique violation), 23503 (foreign key), 23502 (not null), 23514
(check), 42P01 (undefined table), 42703 (undefined column), 42883 (undefined function), 42601 (syntax error), 22P02
(invalid text representation), 22001 (string too long), 22003 (numeric out of range), 22012 (division by zero),
25006 (read-only transaction), 40001 (serialization failure), 57014 (canceled by timeout), 0A000 (not supported by
lexdb; the message begins `lexdb:`).
