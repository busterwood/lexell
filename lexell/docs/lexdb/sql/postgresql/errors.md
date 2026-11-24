# Error codes

The SQLSTATE codes lexdb gives in the PostgreSQL door, what causes each, and how to see them.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

An error reaches the client as PostgreSQL's `ErrorResponse`: a severity (`ERROR`, or `FATAL` when the session
ends), a five-character SQLSTATE code, a message, and for some errors a `DETAIL` and a `HINT`. In psql,
`\set VERBOSITY verbose` shows the code:

```
ERROR:  23505: duplicate key value violates unique constraint "item_pkey"
DETAIL:  Key (id)=(1) already exists.
```

Drivers give the code as the exception's SQL state (`SQLException.getSQLState()` in JDBC, `e.sqlstate` in
psycopg, `err.code` in node-postgres).

## Codes

The codes are PostgreSQL's, with PostgreSQL's meaning. The first two characters are the class.

### Class 08: connection

| Code | Name | Cause in lexdb |
|---|---|---|
| 08P01 | protocol_violation | A message the wire protocol does not allow; unencrypted data after an SSL request. |
| 08006 | connection_failure | The connection was lost while rows were sent or during `COPY`. |

### Class 0A: feature not supported

| Code | Name | Cause in lexdb |
|---|---|---|
| 0A000 | feature_not_supported | Something lexdb does not do. The message starts with `lexdb:` (`lexdb: time with time zone is not supported`). |

### Class 0L: invalid grantor

| Code | Name | Cause in lexdb |
|---|---|---|
| 0LP01 | invalid_grant_operation | A role granted to itself, or a membership that would make a loop. |

### Class 21: cardinality violation

| Code | Name | Cause in lexdb |
|---|---|---|
| 21000 | cardinality_violation | A scalar subquery returned more than one row; `ON CONFLICT DO UPDATE` met the same row twice. |

### Class 22: data exception

| Code | Name | Cause in lexdb |
|---|---|---|
| 22001 | string_data_right_truncation | A value too long for a `varchar(n)` or `char(n)` column. |
| 22003 | numeric_value_out_of_range | An integer or `numeric` too large for its type or column, or an integer sum or product cast to `smallint` or `integer` that overflows. |
| 22004 | null_value_not_allowed | A NULL where one is not allowed (`error_on_null`, `format('%I', NULL)`, a JSON key). |
| 22007 | invalid_datetime_format | Text that does not read as a date or time. |
| 22008 | datetime_field_overflow | A date or time field out of range (`'2026-02-30'`). |
| 22011 | substring_error | A negative length in `substr`. |
| 22012 | division_by_zero | Division or `mod` by zero. |
| 22013, 22014, 22016 | invalid window argument | A bad frame offset, `ntile(0)`, `nth_value(x, 0)`. |
| 22019, 22025 | invalid escape | A bad `ESCAPE` character or a `LIKE` pattern ending in it; a bad `unistr` escape. |
| 2200H | sequence_generator_limit_exceeded | `nextval` past a sequence's limit without `CYCLE`. |
| 2201B | invalid_regular_expression | A regular expression that does not compile. |
| 2201E | invalid_argument_for_logarithm | The logarithm of zero or of a negative number. |
| 2201F | invalid_argument_for_power_function | The square root of a negative number; a bad power. |
| 2201G | invalid_argument_for_width_bucket_function | A bucket count below 1. |
| 22023 | invalid_parameter_value | A bad argument or setting value (a precision out of range, an unknown `encode` format). |
| 22P02 | invalid_text_representation | Text that does not read as the type (`'abc'::int`, `1 = 'a'`, a bad uuid, a malformed array, a string that is not a label of an enum). |
| 22P03 | invalid_binary_representation | A binary parameter of the wrong length. |
| 22P04 | bad_copy_file_format | Missing or extra columns in a `COPY FROM` line. |

### Class 23: integrity constraint violation

| Code | Name | Cause in lexdb |
|---|---|---|
| 23502 | not_null_violation | NULL in a `NOT NULL` column. |
| 23503 | foreign_key_violation | A row with no parent, or a parent row still referenced. |
| 23505 | unique_violation | A duplicate key in a primary key or unique constraint or index. |
| 23514 | check_violation | A row a `CHECK` constraint refuses. |

### Class 25: invalid transaction state

| Code | Name | Cause in lexdb |
|---|---|---|
| 25001 | active_sql_transaction | `CREATE INDEX CONCURRENTLY` or `DROP INDEX CONCURRENTLY` inside a transaction block. |
| 25006 | read_only_sql_transaction | A write in a `READ ONLY` transaction, or on a replica. |
| 25P01 | no_active_sql_transaction | `SAVEPOINT` and the like outside a transaction block. |
| 25P02 | in_failed_sql_transaction | A statement after an error in a transaction block, before `ROLLBACK`. |

### Class 28: invalid authorization

| Code | Name | Cause in lexdb |
|---|---|---|
| 28000 | invalid_authorization_specification | No user name in the startup message; a role that may not log in. |
| 28P01 | invalid_password | A wrong password. |

### Class 2B, 34, 26, 3B, 3D, 3F: objects that do or do not exist

| Code | Name | Cause in lexdb |
|---|---|---|
| 2BP01 | dependent_objects_still_exist | `DROP` or `ALTER` of an object that others depend on, without `CASCADE` (a sequence a column default calls, for one). |
| 26000 | invalid_sql_statement_name | A prepared statement name the session does not have (extended protocol). |
| 34000 | invalid_cursor_name | A portal name the session does not have (extended protocol). |
| 3B001 | invalid_savepoint_specification | `ROLLBACK TO` or `RELEASE` of a savepoint that does not exist. |
| 3D000 | invalid_catalog_name | A database other than `lexdb` in the startup message. |
| 3F000 | invalid_schema_name | A schema that does not exist; no schema on the search path to create in. |

### Class 40: transaction rollback

| Code | Name | Cause in lexdb |
|---|---|---|
| 40001 | serialization_failure | Two serializable transactions that conflict: the later one fails and should be run again. |
| 40P01 | deadlock_detected | Two transactions that wait for each other's locks. |

### Class 42: syntax error or access rule violation

| Code | Name | Cause in lexdb |
|---|---|---|
| 42501 | insufficient_privilege | A privilege the role does not have; not the object's owner. |
| 42601 | syntax_error | Text lexdb cannot parse, including PostgreSQL features it does not have. |
| 42701 | duplicate_column | A column named twice. |
| 42702 | ambiguous_column | A column name that more than one table in `FROM` has. |
| 42703 | undefined_column | A column that does not exist. |
| 42704 | undefined_object | A type, role, index, setting or other object that does not exist. |
| 42710 | duplicate_object | A role, type, enum label or constraint that already exists. |
| 42712 | duplicate_alias | A table name or alias used twice in `FROM`. |
| 42725 | ambiguous_function | A call that more than one function matches. |
| 42803 | grouping_error | A column that must be in `GROUP BY`; an aggregate where none is allowed. |
| 42804 | datatype_mismatch | Values whose types cannot meet: `CASE`, `COALESCE`, `GREATEST`, `UNION` or `VALUES` over a number and a boolean. |
| 42809 | wrong_object_type | An object of the wrong kind (a view where a table is needed; `ANY` without an array). |
| 42830 | invalid_foreign_key | A foreign key without a matching unique key, or with the wrong number of columns. |
| 42846 | cannot_coerce | A cast lexdb does not have. |
| 42883 | undefined_function | A function or operator that does not exist for those argument types. |
| 42939 | reserved_name | A schema name starting with `pg_`. |
| 428C9 | generated_always | A value for a `GENERATED ALWAYS` column. |
| 42P01 | undefined_table | A table, view or sequence that does not exist. |
| 42P06 | duplicate_schema | A schema that already exists. |
| 42P07 | duplicate_table | A table, view, index or sequence that already exists. |
| 42P10 | invalid_column_reference | An `ORDER BY` or `GROUP BY` position past the select list; a bad `ON CONFLICT` target. |
| 42P13 | invalid_function_definition | `CREATE OR REPLACE FUNCTION` that changes the result type or a parameter's name. |
| 42P16 | invalid_table_definition | Bad table options: `ON COMMIT` on a permanent table, a temporary table in a permanent schema, a second `PRIMARY KEY`. |
| 42P17 | invalid_object_definition | A bad generated column. |
| 42P19 | invalid_recursion | A misplaced recursive reference in `WITH RECURSIVE`. |
| 42P20 | windowing_error | A bad window frame. |

### Class 53, 54, 55, 57, 58, 72: resources, limits, state, operator, system

| Code | Name | Cause in lexdb |
|---|---|---|
| 53200 | out_of_memory | A statement holds more than `max_statement_mem`. |
| 54000 | program_limit_exceeded | A value too large to build. |
| 54001 | statement_too_complex | A recursive query past `max_recursion` rounds; a function calling itself too deep. |
| 54011 | too_many_columns | `GROUPING` with 32 or more arguments. |
| 55000 | object_not_in_prerequisite_state | `currval` or `lastval` before `nextval`; a primary-only function on a replica. |
| 55006 | object_in_use | `DROP ROLE` of the current user. |
| 55P03 | lock_not_available | `FOR UPDATE NOWAIT` on a locked row. |
| 57014 | query_canceled | `statement_timeout` passed; `WAIT FOR LSN` timed out. |
| 57P01 | admin_shutdown | The server is shutting down. |
| 58000 | system_error | No random values to be had. |
| 72000 | snapshot_too_old | A long transaction's snapshot needed old row versions past lexdb's budget for them. |

## Remarks

- After an error inside `BEGIN ... COMMIT`, the transaction is aborted: every statement until `ROLLBACK` (or
  `ROLLBACK TO SAVEPOINT`) gives 25P02, and `COMMIT` rolls back.
- 40001 and 40P01 mean "run the transaction again": the work is undone and nothing is wrong with the statements.
- Key, foreign key and `NOT NULL` errors carry a `DETAIL` naming the values, as in PostgreSQL.

## Differences from PostgreSQL

- Some errors carry PostgreSQL's `DETAIL` and `HINT` in the message instead of in their own fields
  (lexdb-gaps.md 2.4).
- Several messages differ in wording: see the "Differences" sections of the statement and function pages.
- 0A000 marks features PostgreSQL has and lexdb does not; PostgreSQL gives it only for features it lacks too.
- 72000 (snapshot too old) comes from lexdb's limit on old row versions, not from `old_snapshot_threshold`.
- `LOCATION` (the source file and line) is not sent.
- A `$1` in a simple query, with no parameters, is 08P01 `there is no parameter $1` (PostgreSQL: 42P02).

## Examples

### A. Seeing the code

<!-- example: postgresql -->
```sql
\set VERBOSITY verbose
CREATE TABLE item (id int PRIMARY KEY, name text NOT NULL, qty int CHECK (qty >= 0));
INSERT INTO item VALUES (1, 'pen', 5);
INSERT INTO item VALUES (1, 'ink', 2);
INSERT INTO item VALUES (2, NULL, 2);
INSERT INTO item VALUES (3, 'pad', -1);
```

```text
CREATE TABLE
INSERT 0 1
ERROR:  23505: duplicate key value violates unique constraint "item_pkey"
DETAIL:  Key (id)=(1) already exists.
ERROR:  23502: null value in column "name" of relation "item" violates not-null constraint
DETAIL:  Failing row contains (2, null, 2).
ERROR:  23514: new row for relation "item" violates check constraint "item_qty_check"
```

### B. Names and syntax

<!-- example: postgresql -->
```sql
\set VERBOSITY verbose
SELECT * FROM nosuch;
SELECT nosuch FROM item;
SELECT nosuch(1);
SELEC 1;
CREATE TABLE item (x int);
```

```text
ERROR:  42P01: relation "nosuch" does not exist
ERROR:  42703: column "nosuch" does not exist
ERROR:  42883: function nosuch with 1 arguments does not exist
ERROR:  42601: syntax error at or near "selec"
ERROR:  42P07: relation "item" already exists
```

### C. Data errors

<!-- example: postgresql -->
```sql
\set VERBOSITY verbose
SELECT 'abc'::int;
SELECT 2147483647 * 2::bigint * 9223372036854775807;
SELECT 1 / 0;
SELECT '2026-02-30'::date;
CREATE TABLE code (c varchar(3));
INSERT INTO code VALUES ('abcd');
INSERT INTO item VALUES (4, repeat('x', 3), 1000000000000);
```

```text
ERROR:  22P02: invalid input syntax for type integer: "abc"
ERROR:  22003: bigint out of range
ERROR:  22012: division by zero
ERROR:  22008: date/time field value out of range: "2026-02-30"
CREATE TABLE
ERROR:  22001: value too long for type character varying(3)
ERROR:  22003: integer out of range
```

### D. Foreign keys

<!-- example: postgresql -->
```sql
\set VERBOSITY verbose
CREATE TABLE line (no int PRIMARY KEY, item_id int REFERENCES item (id));
INSERT INTO line VALUES (1, 99);
INSERT INTO line VALUES (1, 1);
DELETE FROM item WHERE id = 1;
```

```text
CREATE TABLE
ERROR:  23503: insert or update on table "line" violates foreign key constraint "line_item_id_fkey"
DETAIL:  Key (item_id)=(99) is not present in table "item".
INSERT 0 1
ERROR:  23503: update or delete on table "item" violates foreign key constraint "line_item_id_fkey" on table "line"
DETAIL:  Key (id)=(1) is still referenced from table "line".
```

### E. An aborted transaction

<!-- example: postgresql -->
```sql
\set VERBOSITY verbose
BEGIN;
INSERT INTO item VALUES (1, 'again', 1);
SELECT count(*) FROM item;
ROLLBACK;
SELECT count(*) FROM item;
```

```text
BEGIN
ERROR:  23505: duplicate key value violates unique constraint "item_pkey"
DETAIL:  Key (id)=(1) already exists.
ERROR:  25P02: current transaction is aborted, commands ignored until end of transaction block
ROLLBACK
 count
-------
     1
(1 row)
```

### F. Limits and lexdb's refusals

<!-- example: postgresql -->
```sql
\set VERBOSITY verbose
SET max_recursion = 10;
WITH RECURSIVE r(n) AS (SELECT 1 UNION ALL SELECT n + 1 FROM r) SELECT count(*) FROM r;
RESET max_recursion;
BEGIN READ ONLY;
DELETE FROM item;
ROLLBACK;
SELECT '10:30'::timetz;
CREATE SEQUENCE s;
SELECT currval('s');
```

```text
SET
ERROR:  54001: recursive query still adding rows after 10 rounds (max_recursion); SET max_recursion = n to allow more, 0 for no limit
RESET
BEGIN
ERROR:  25006: cannot execute DELETE in a read-only transaction
ROLLBACK
ERROR:  0A000: lexdb: time with time zone is not supported (use timestamptz)
CREATE SEQUENCE
ERROR:  55000: currval of sequence "s" is not yet defined in this session
```

### G. statement_timeout

<!-- example: postgresql -->
```sql
\set VERBOSITY verbose
SET statement_timeout = 50;
SELECT count(*) FROM generate_series(1, 1000000000) a;
RESET statement_timeout;
```

```text
SET
ERROR:  57014: canceling statement due to statement timeout
RESET
```

## See also

[BEGIN](begin.md) · [SAVEPOINT](savepoint.md) · [SET](set.md) · [Connecting](../../connect/postgresql.md)
