# lexdb against PostgreSQL: where it stands and what is missing

Status: a review taken on 2026-11-12, at commit 9133e91a (branch `lexdb`,
after design/lexdb.md 9.91), brought up to date for 9.92 to 9.96
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

## 1. Closed since the first review (9.75 to 9.96)

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
  - index options and `CONCURRENTLY` (9.85);
  - temporary tables, sequences and views, `ON COMMIT`, `DISCARD TEMP`
    and `ALL`, each session's `pg_temp_N` searched first; their DDL does
    not disturb other sessions (9.96);
  - ALTER TABLE: primary keys added, dropped and changed (USING INDEX
    too), ALTER COLUMN's identity forms, serial and identity columns added
    over rows, NOT VALID and VALIDATE, RENAME CONSTRAINT, and PostgreSQL's
    notices for the IF [NOT] EXISTS forms (9.117).
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
- **Event streams** (9.98, `lexdb-events.md`): `WAITFOR (SELECT ...),
  TIMEOUT ms`, a SELECT on an ordinary table that waits for a commit to add
  rows after a cursor.

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
   - multi-dimensional arrays, `array_fill` and `array_sort`;
   - `pg_sleep` (found while testing 9.98).

   Regular expressions are RE2's: no back-references inside a pattern and
   no lookahead, where PostgreSQL's have both (9.92).

### 2.2 Tier 2: common, each with a workaround

- **Sequences and identity columns** (probed against PostgreSQL 18,
  2026-11-13; the gaps found closed in 9.117).
  - **What matches:** nextval, currval, lastval and setval; the options,
    cycling, the types' bounds and RESTART; serial; identity ALWAYS and BY
    DEFAULT with options; OVERRIDING; `pg_get_serial_sequence`; nextval
    not rolled back; OWNED BY and its drop; `pg_sequences`,
    `pg_sequence` and `information_schema.sequences`; TRUNCATE RESTART
    IDENTITY. Since 9.117:
    - ALTER COLUMN's identity forms (`ADD GENERATED ... AS IDENTITY`,
      `SET GENERATED`, `SET` options, `RESTART`, `DROP IDENTITY [IF
      EXISTS]`);
    - serial, identity and volatile defaults added over rows;
    - a sequence read as a relation;
    - `ALTER SEQUENCE` RENAME and SET SCHEMA, and `DROP SEQUENCE a, b`;
    - nextval of a quoted, schema-qualified name;
    - `setval(pg_get_serial_sequence(...), ...)` (Django's reset);
    - the GENERATED ALWAYS error's text, DETAIL and HINT;
    - arithmetic at the integers' ends.
  - **Differences:**
    - `log_cnt` is PostgreSQL's only for a sequence's first 32 values;
    - a column filled over rows of a keyed table goes in key order, where
      PostgreSQL's is physical order;
    - RESTART takes effect at once, even in a block rolled back.
- **Tables:**
  - a primary key added, dropped or changed rewrites the table (9.117):
    1M rows take 5 s where PostgreSQL builds an index in 0.15 s;
  - PostgreSQL 18's NOT NULL constraints are not listed in `pg_constraint`
    (contype n);
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
- **Date input:** a day or month of one digit (`'2024-01-2'`) is refused
  (22007); PostgreSQL reads it. Found writing `exec_batchjoin` (9.102).
- **Differences from PostgreSQL 18,** found by 9.108's comparison
  (2026-11-13), all older than 9.108:
  - `upper`, `lower` and `initcap` change ASCII letters only (`été` gives
    `éTé`; PostgreSQL gives `ÉTÉ` in a UTF-8 database);
  - `round(NULL, 1)` gives 42883 ("function round with 2 arguments does
    not exist") where PostgreSQL gives NULL;
  - numeric division gives 16 decimal places where PostgreSQL gives up to
    20 (its `select_div_scale` rule);
  - `'abcdef'::varchar(3)` gives 22001; PostgreSQL truncates an explicit
    cast to the length (an assignment, an INSERT, is what errors);
  - a numeric overflow's message carries PostgreSQL's DETAIL line in the
    message itself.
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
    `lexdb`); deferred, and for tests see 2.7;
  - `pg_hba.conf`-style rules.
- **Large subsystems:**
  - partitioning (the user leans against it; see 2.5 for what is planned
    instead);
  - tablespaces: decided against (2.6);
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
    own fields, except for the errors 9.117 gave their own (key and unique
    violations, foreign keys, NOT NULL, identity, a drop refused);
  - no error position is sent, so psql shows no `LINE` and caret.
- **Memory:**
  - a query that sorts, groups or uses a window is made whole before it
    is sent, at about 890 bytes a row; plain queries, INSERT ... SELECT and
    integer series stream (9.99), as does COPY TO (9.84). T-SQL results
    over TDS are held whole;
  - the runtime's allocator never gives memory back to the system, so RSS
    stays at its highest (9.99);
  - a transaction's writes stay in memory until its commit, about 176
    bytes a row (9.84);
  - a large `CREATE TABLE AS` holds its result while it inserts (9.88).
- **Storage** (items 8 and 10 of 9.4):
  - no compression;
  - the file never shrinks;
  - temporary tables are written to the log like any (9.96): PostgreSQL
    writes no WAL for them.
- **Speed:** SIMD needs a Lexell language or runtime change: the user's
  decision (item 12 of 9.4).

### 2.5 Bulk deletes, in place of partitioning (noted 2026-11-14)

The user is leaning against declarative partitioning (2.3). Partitioning's
lasting value today is cheap removal of old data. lexdb already avoids
PostgreSQL's after-cost (no heap, no VACUUM: a DELETE removes rows and
index entries at commit), and min/max leaf skipping already gives much of
partition pruning. What is left is a large purge. Measured so far (9.109,
warm): DELETE of 10k rows with one index 164 ms (PostgreSQL 52), about
190k rows with no index 349 ms (PostgreSQL 99), so roughly 16 µs and 2 µs
a row. A drop instead frees a 105 MB table in 1.5 to 13 ms without reading
its leaves (9.32). Leaves are never merged, so a delete scattered across
the key order leaves sparse leaves for good.

Two next steps cover most of what partitioning would give:

1. **A range delete as a subtree drop.** A DELETE whose WHERE is only a
   range on the leading primary-key columns detaches the subtrees the range
   covers whole, freed as a dropped table's are (9.32), and deletes rows
   one by one only in the two edge leaves. The design question is the
   secondary indexes: their order differs, so either the fast path applies
   only to a table with none (or with indexes that lead with the same
   key), or their entries are still deleted one by one. The log records
   the range, not each row; recovery and the replicas' follower must apply
   it the same way.
2. **Bounded memory for a large transaction.** A transaction's writes stay
   in memory until its commit, about 176 bytes a row (2.4), and DELETE has
   no way to bound them: deleting 100M rows would hold something like 15
   to 20 GB [estimate]. Either spill a transaction's writes to disk past a
   size, as sorts spill, keeping the statement all or nothing; or give
   DELETE (and UPDATE) a batched form like COPY's `WITH (batch_rows n)`,
   which commits in parts and is not.

`design/lexdb-events.md` (expiry of old events) would use either.

### 2.6 Tablespaces: decided against; a log directory instead (2026-11-14)

**Decision (the user's): lexdb will not support tablespaces.** They were
made for small disks that nothing joined, raw devices, spreading I/O over
spindles, and backup or offline by container. Today a filesystem or
volume grows online and takes new disks (LVM, ZFS, btrfs, XFS, cloud
volumes) without the database knowing. `CREATE TABLESPACE` and the
`TABLESPACE` clauses stay unsupported. `pg_tablespace` keeps its one
row, `pg_default` (oid 1663), for clients that only read it.

Notes that go with the decision:
- One data file means the filesystem's largest file is lexdb's largest
  database: 16 TiB on ext4 with 4 KiB blocks, far more on XFS. Say so in
  the docs.
- A full filesystem (ENOSPC) on a data or log write must fail cleanly and
  recover once space is added. Check that a test covers it.

**Built (2026-11-14, lexdb.md 9.124): the log in a directory of its own, `--log-dir DIR`.** The text that was the
plan is kept below, with what was done to each point.

Not supported before: `lexdb_disk.Fs.Real(dir)` was the one directory for every file, so the log
segments (`log.N`, `log.spare`, `lexdb_store.segName`) sat beside the data
file, and there was no flag (`cmd/lexdb.lxl` `usage`). Wanted: a
`--log-dir DIR`, so the log's fsyncs go to another
device from the checkpoint's writes, and a full data disk does not stop
the log. What it touched:
- a second `Fs` for the log, used for opening, creating, renaming and
  removing the segments and the spare: `Db.logFs` (`lexdb_store.openSplit`, `runSplit`);
- `syncDir` on the log's directory after those, not the data's: it is a method of the `Fs`, so the log's does it;
- the replicas' follower, which reads segments (`Fol.fs` is the log's `Fs`; `openReplicaSplit`);
- startup: refuse a data directory whose log is missing or is somewhere
  else, so the wrong log is never replayed: a `logdir` file in the data directory and a `logid` file in the log
  directory carry one random id, compared at start (`checkLog`, 9.124);
- `--replica` and the supervisor passing the option to each worker (a module variable set before the forks);
- the crash tests: `store_logdir.lxl` runs two simulated file systems, each crashed its own way. Not done: an ENOSPC
  test (below).

Not done: a test of ENOSPC on a data or log write. There is none: no test in `tests/lexdb` mentions ENOSPC or
errno 28; the simulated `Fs` can fail one call with EIO (`failIn`, used by `disk_sim.lxl`), which exercises the same
error path, but not a full disk and its recovery once space is added.

A temporary or spill directory is not needed yet: lexdb spills nothing
(2.4). Add one with the first spill.

### 2.7 Fast empty databases for tests (2026-11-14)

What the user wants from "multiple databases" (2.3, deferred) is cheap,
isolated, known starting states for test fixtures, so tests can run in
parallel. The plan, in place of `CREATE DATABASE ... TEMPLATE`:
- **A template data directory, cloned per test worker** with `mkdir wN;
  chattr +C wN; cp --reflink=always template/data.lxdb template/log.1 wN/`,
  then one lexdb per worker. Nothing to build. Measured (btrfs, a build of
  2026-11-13; 31 tables, 62 indexes, 56,000 seed rows; times include
  psql's own start): a copy 2 to 5 ms, start to first answer 7 to 21 ms,
  TRUNCATE of all 31 tables 8 to 16 ms, 14 MB RSS a server, 432 KB of
  its own disk a clone. 8 and 16 at once were as fast as one. Ports must
  be below the ephemeral range (32768 to 60999 here), or a client's
  socket can take one.
- **Reset within a fixture:** a rollback per test (free: the writes are in
  memory until commit), or TRUNCATE.
- **Built (2026-11-14, lexdb.md 9.123): `--unsafe-no-sync` and `--cache-mb N`.** No-sync makes 2,000 autocommit
  INSERTs 9.4 times faster (1,280 to 137 ms) and warns at start; it reaches `--replicas` workers and `--replica`.
  `--cache-mb` takes 1 to 1,048,576. The original plan follows.
- **To build: a test-only no-sync mode** (`--no-sync` or similar): a
  commit does not wait for fdatasync, about 1 ms a commit on this machine.
  The user wants this. Name it so no one runs production with it, and say
  in the log at start that it is on.
- **To consider with it:** a cache budget option. Every server takes the
  same default budget (11,987 MB here), so many servers at once could
  together promise more memory than the machine has.
- Later, only if restarts prove too slow: reset in place to a pinned
  checkpoint.

**Future task, after all the planned work (the user's, 2026-11-14):
TRUNCATE CASCADE in the T-SQL and Oracle doors.** The PostgreSQL door has
it (9.91): checked on a clone of the template above, `truncate ref
cascade` emptied ref, the 30 tables referencing it and a table
referencing one of those, in 3.3 ms. The aim is the same reset for tests
through the other two doors. Each server differs:
- **SQL Server** has no CASCADE on TRUNCATE, and refuses to truncate any
  table a foreign key references (4712). `TRUNCATE TABLE t CASCADE` would
  be lexdb's own extension. Keep 4712 for the plain form.
- **Oracle** (12c on) has `TRUNCATE TABLE t CASCADE`, but follows only
  foreign keys declared ON DELETE CASCADE, and refuses otherwise. To
  decide: Oracle's rule, or PostgreSQL's (every referencing table), which
  is what tests want.
- Not yet checked: what the two doors do with CASCADE today.

## 3. A proposed order

1. **json and jsonb,** when the user decides.
2. **Binary formats,** for asyncpg and JDBC.
3. **Data-modifying CTEs and generated columns.**

**Open questions for the user:**
- Is this order right?
- When should json come?
- Should `READ COMMITTED` stay serializable underneath? Or should it be
  refused, or built?
