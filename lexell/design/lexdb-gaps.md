# lexdb against PostgreSQL: where it stands and what is missing

Status: a review taken on 2026-11-12, at commit 9133e91a (branch `lexdb`,
after design/lexdb.md 9.91), brought up to date for 9.92 to 9.95
(9.94 merged as 87d2a0b1). It replaces the review of 2026-11-10 (commit
238ff702, after 9.46). The order of work at the end is a proposal; the
choices in it are the user's.

**How it was taken.** About 200 statements were sent one at a time through
psql to a fresh lexdb server. They cover:
- every gap the first review listed;
- the functions applications use most;
- the statements tools send.

Each statement was recorded as accepted or failed, with its error.
Answers were not compared with PostgreSQL here: the suites that
`tests/lexdb/gen_pg.py` generates from PostgreSQL 18 do that, feature by
feature.

## 1. Closed since the first review (9.75 to 9.95)

- **Types:**
  - date, time, timestamp, timestamptz and interval, with their operators,
    `extract`, `date_trunc` and `age` (9.76);
  - session time zones: `SET TIME ZONE` and its forms, timestamptz shown
    and read in the session's zone (DST gaps and overlaps as PostgreSQL),
    `AT TIME ZONE`, `AT LOCAL` and `timezone()`, and ParameterStatus
    `TimeZone` (9.95);
  - `real` and `double precision` (9.79);
  - `bytea`, and `uuid` with `gen_random_uuid()` (9.78);
  - enum types (9.90).
- **The catalogs:** `pg_catalog` and `information_schema`, as far as
  SQLAlchemy, psycopg, Alembic, Django and psql use them (9.80). So these
  now work:
  - psql's `\d` commands;
  - `version()`, `current_user` and `SHOW server_version`;
  - the reg types.
- **Writes:**
  - `INSERT ... ON CONFLICT` (9.77);
  - `UPDATE ... FROM`, `DELETE ... USING`, an alias on their target, and
    `TRUNCATE` (9.91).
- **Transactions:**
  - savepoints (9.80);
  - `SELECT ... FOR UPDATE / SHARE`, with NOWAIT and SKIP LOCKED;
  - advisory locks (9.86);
  - deferrable foreign keys and `SET CONSTRAINTS` (9.85).
- **Logins:**
  - SCRAM-SHA-256 and TLS (9.81);
  - roles, owners, `GRANT` and `REVOKE`, and `SET ROLE` (9.83).
- **Tables and indexes:**
  - views, read-only (9.82);
  - tables without a primary key, `CREATE TABLE AS` and `SELECT INTO`
    (9.88);
  - indexes on expressions (9.89);
  - index options and `CONCURRENTLY` (9.85).
- **Queries:**
  - `VALUES` as a query;
  - `~` and its kin;
  - subscripts, `ARRAY(subquery)` and set-returning functions in a select
    list (9.80);
  - `array_agg` (9.78);
  - the bitwise operators (9.85).
- **Functions and operators** (9.79, 9.92). Almost all that the first
  review and the probe listed:
  - the regular expression functions and `substring(x from pattern)`;
  - the string functions, `format`, and the SQL forms of `position`,
    `overlay` and `substring`;
  - math with `^`, and numeric versions of `sqrt`, `exp`, `ln`, `log` and
    `power`;
  - the array functions, `@>`, `<@` and `&&`, and `||` on arrays (which
    gave text before);
  - `current_setting` and `set_config`, `pg_backend_pid` and
    `txid_current`;
  - `to_char`, `to_number`, `to_date` and `to_timestamp`.
- **COPY:**
  - COPY TO is sent as it runs (9.84);
  - COPY FROM is read as it comes, and `batch_rows` bounds a large load
    (9.87).
- **The small query forms** (9.93, 9.94):
  - `JOIN ... USING` and `NATURAL JOIN`;
  - `DISTINCT ON`, `FETCH FIRST` and `WITH TIES`;
  - row comparisons, `(a, b) < (c, d)`, and rows in IN;
  - `char(n)`;
  - `CREATE INDEX` without a name;
  - `SIMILAR TO`, `LIKE ANY / ALL` and `BETWEEN SYMMETRIC`;
  - `ROLLUP`, `CUBE`, `GROUPING SETS` and `GROUPING()`;
  - `percent_rank` and `cume_dist` as double precision;
  - `VACUUM`, `ANALYZE`, `CHECKPOINT`, `REINDEX` and `CLUSTER`, accepted
    as doing nothing.
- **Replication:** read-only replicas on the same machine (9.68 to 9.73).

**Speed** (9.67, PostgreSQL 18 on the same machine, all the data in
memory):

| Measure | lexdb against PostgreSQL |
|---|---|
| Point selects, 1 client | 1.18 times faster |
| Point selects, 8 clients | 0.36 times |
| Point selects, 32 clients | 0.24 times |
| Updates | the same, within 3% |
| Aggregates against one PostgreSQL core | 1.1 to 1.8 times faster |
| Aggregates against PostgreSQL's two workers | 1.2 to 1.9 times slower on four queries of five |
| Loads | PostgreSQL 1.7 times faster |

Points to note:
- Point selects lose with many clients because lexdb runs one SQL thread
  by design, while PostgreSQL runs a process per connection.
- Updates are bound by the drive.
- Loads (9.84, 9.87): COPY of 1M rows takes about 1.1 s, against
  PostgreSQL's 0.6 to 0.9 s.

## 2. What is missing

In three tiers, by how soon a real application meets the gap.

### 2.1 Tier 1: almost every application or tool meets these

1. **json and jsonb.** There is no type: `->`, `->>`, `@>`, `json_agg`,
   `row_to_json` and the rest all fail. `json_build_object` alone exists,
   for the catalog's queries.
   - It is the last thing Alembic's probe stopped at (9.90), and Django's
     JSONField needs it.
   - Waiting is the user's decision (9.85).
2. **What 9.92 and 9.94 left of the functions:**
   - row values outside comparisons (`SELECT (1, 2)`, `row_to_json`);
   - multi-dimensional arrays, `array_fill` and `array_sort`.

   Regular expressions are RE2's: no back-references inside a pattern and
   no lookahead, where PostgreSQL's have both (9.92).

### 2.2 Tier 2: common, each with a workaround

- **Tables:**
  - `ADD PRIMARY KEY` on a table made without one (a table's key cannot
    change, 9.88);
  - temporary tables (`CREATE TEMP TABLE`);
  - generated columns;
  - materialized views;
  - views are read-only, and a rename of a table one reads is refused
    (9.82).
- **Queries:** window functions with grouping sets (0A000), and `USING
  (...) AS alias` (9.93, 9.94).
- **Data-modifying CTEs:** `WITH d AS (DELETE ... RETURNING ...)`.
- **User-defined types:**
  - domains;
  - arrays of an enum, enum renames, and `DROP TYPE ... CASCADE` (9.90).
- **Comments:** `COMMENT ON`. `obj_description` exists but gives nothing.
- **Statement-level SQL:**
  - `PREPARE` and `EXECUTE` (the protocol's prepared statements work);
  - cursors, `DECLARE` and `FETCH`;
  - `LISTEN` and `NOTIFY`;
  - `LOCK TABLE`.
- **Isolation levels.** `BEGIN ISOLATION LEVEL READ COMMITTED` is accepted
  and runs serializable (`SHOW transaction_isolation` says so).
  Applications written for read committed meet more serialization
  failures to retry. Row locks (9.86) remove the common case.
- **Locks:**
  - no `lock_timeout`;
  - `statement_timeout` does not end a wait for a lock;
  - no `pg_locks`.
- **Collations:** `COLLATE` is read and ignored; text compares by bytes.
- **Privileges** (9.83):
  - column privileges;
  - `WITH GRANT OPTION`;
  - `ALTER DEFAULT PRIVILEGES`;
  - row security.
- **Binary formats:** asyncpg, JDBC and psycopg's binary mode need them
  for results and COPY. They were planned last of 9.75's stages.

### 2.3 Tier 3: large subsystems, likely out of scope unless wanted

- **Procedural code:** user functions and procedures (SQL and PL/pgSQL),
  `DO` blocks, triggers, and `$$` quoting.
- **Databases and authentication:**
  - more than one database per server (`current_database()` is always
    `lexdb`);
  - `pg_hba.conf`-style rules.
- **Large subsystems:**
  - partitioning;
  - extensions;
  - full-text search;
  - `TABLESAMPLE`;
  - replication to another machine.
- **The planner and parallelism:**
  - a cost-based planner: left for now by the user (section 0);
  - parallel query: lexdb has one SQL thread by design.

### 2.4 Not SQL features

- **Wrong answers:** none left from the probe. `||` on arrays was fixed
  in 9.92, and `percent_rank`'s type in 9.94.
- **Errors:**
  - DETAIL and HINT are folded into the message rather than sent as their
    own fields;
  - no error position is sent, so psql shows no `LINE` and caret.
- **Memory:**
  - a query that sorts, groups or uses a window is made whole before it
    is sent (9.84; plain queries and COPY stream);
  - a transaction's writes stay in memory until its commit, about 176
    bytes a row (9.84);
  - a large `CREATE TABLE AS` holds its result while it inserts (9.88).
- **Storage** (items 8 and 10 of 9.4):
  - no compression;
  - the file never shrinks.
- **Speed:** SIMD needs a Lexell language or runtime change: the user's
  decision (item 12 of 9.4).

## 3. A proposed order

1. **json and jsonb,** when the user decides.
2. **Binary formats,** for asyncpg and JDBC.
3. **Data-modifying CTEs, temporary tables and generated columns.**

**Open questions for the user:**
- Is this order right?
- When should json come?
- Should `READ COMMITTED` stay serializable underneath? Or should it be
  refused, or built?
