# lexdb against PostgreSQL: where it stands and what is missing

Status: a review taken on 2026-11-10, at commit 238ff702 (branch `lexdb`,
after window functions, design/lexdb.md 9.46). The order of work at the end
is a proposal; the choices in it are the user's.

**How it was taken.** About 130 statements were sent through psql to a fresh
lexdb server. They cover the features ordinary applications, ORMs and tools
use: types, data changes, query forms, functions, DDL, transactions and the
catalogs. Each was recorded as accepted or failed, with its error. Where
PostgreSQL's behaviour was in question, a scratch PostgreSQL 16 on the same
machine was the reference. The measurements are design/lexdb.md's (9.45 and
9.46).

## 1. What lexdb has

- **Storage:**
  - an on-disk B+tree with a write-ahead log, checkpoints and snapshots;
  - crash tests on a simulated disk and through the wire protocol (9.18);
  - readers never wait for writers, nor writers for readers (9.16).
- **The wire protocol:**
  - the simple and extended query protocols;
  - plans kept per prepared statement;
  - query cancel;
  - COPY IN and OUT.

  psql and the usual client libraries connect unchanged.
- **Queries:**
  - inner, left, right and full joins, and LATERAL;
  - subqueries, correlated ones included;
  - CTEs, recursive ones included;
  - UNION, INTERSECT and EXCEPT;
  - GROUP BY and HAVING;
  - aggregates with FILTER and ORDER BY;
  - window functions;
  - CASE, generate_series, unnest, and `op ANY/ALL (array)`;
  - ORDER BY with NULLS FIRST / LAST;
  - EXPLAIN, and EXPLAIN ANALYZE with row counts.
- **Data changes:**
  - INSERT, UPDATE and DELETE, with WITH before them;
  - INSERT ... SELECT;
  - RETURNING;
  - COPY, text and CSV.
- **Tables and indexes:**
  - indexes: unique, partial and multi-column;
  - schemas;
  - ALTER TABLE: add, drop, rename and retype columns; SET SCHEMA;
  - defaults;
  - UNIQUE, CHECK and FOREIGN KEY constraints, with CASCADE, SET NULL and
    SET DEFAULT;
  - sequences, SERIAL and identity columns.
- **Transactions:**
  - read-write transactions are serializable;
  - read-only transactions run on a snapshot;
  - `statement_timeout` and `max_statement_mem`.
- **Types:** int2, int4 and int8, numeric, text and varchar, bool, and
  one-dimensional arrays.

**Speed.** On 1M rows lexdb is about 2 to 5 times slower than PostgreSQL 16:

| Operation | Slower by |
|---|---|
| COPY load | about 2 times |
| COPY dump | about 3.5 times |
| Window queries | 3.5 to 5 times |

The cost is the executor's work per row, not COPY's or the windows' own: item
11 of design/lexdb.md 9.4 (batches, not rows).

## 2. What is missing

In three tiers, by how soon a real application meets the gap.

### 2.1 Tier 1: almost every application or tool meets these

1. **Types.**
   - There is no date or time type at all. `timestamp`, `timestamptz`,
     `date`, `interval`, `now()` and `current_timestamp` all fail. This is
     the largest gap: nearly every real schema has a timestamp column.
   - Also missing: `float8`/`real`, `bytea`, `uuid` (and
     `gen_random_uuid()`), `json`/`jsonb`, and `char(n)`.
2. **The system catalogs**, `pg_catalog` and `information_schema`. Without
   them:
   - psql's `\d` commands fail;
   - ORMs cannot inspect a schema, nor migration tools check one;
   - GUI tools (DBeaver, pgAdmin) cannot list tables;
   - `pg_dump` cannot back the database up.

   `current_user`, `current_setting()` and `SHOW server_version` are missing
   too. Whether to emulate the catalogs is an open decision (design/lexdb.md
   section 0).
3. **Upsert and joined writes.** These are syntax errors:
   - `INSERT ... ON CONFLICT` (DO UPDATE and DO NOTHING);
   - `UPDATE ... FROM`;
   - `DELETE ... USING`;
   - `TRUNCATE`.
4. **Savepoints and row locks.**
   - `SAVEPOINT` and `ROLLBACK TO`: ORMs use them for nested transactions,
     psql for its `ON_ERROR_ROLLBACK`.
   - `SELECT ... FOR UPDATE`, common in ORM code.
5. **Functions and operators.** Each is small; together they are much of
   everyday SQL.
   - Regular expressions: the `~` operator and the `regexp_*` functions.
   - Strings: `lpad`, `split_part`, `repeat`, `position(... in ...)`,
     `concat_ws`, `md5`, `format`, `chr`, `ascii`, `initcap`, `reverse`,
     `starts_with`, `to_hex`.
   - Math: `sqrt`, `power`, `floor`, `ceil`, `mod`, `div`, `trunc`, `sign`,
     `exp`, `ln`, `random`.
   - Operators: `^`, and the bitwise `&`, `|`, `<<` and `>>`.
   - Arrays: subscripts (`a[1]`), `array_agg`, `array_length`.
   - Formatting: `to_char`.
6. **Logins and encryption.** There is no authentication (SCRAM) and no TLS,
   so lexdb is safe only on the loopback address (item 9 of 9.4).

### 2.2 Tier 2: common, each with a workaround

- **Tables:**
  - every table needs a primary key, and one cannot be added later;
  - no `CREATE TABLE ... AS`;
  - no temporary tables;
  - no generated columns;
  - no indexes on expressions, such as `lower(a)`;
  - no views, plain or materialized.
- **Queries:**
  - no `VALUES` as a query;
  - no `JOIN ... USING` or `NATURAL JOIN`;
  - no `DISTINCT ON`;
  - no `FETCH FIRST`;
  - no row comparisons, `(a, b) < (c, d)`;
  - no `BETWEEN SYMMETRIC` or `SIMILAR TO`;
  - no `ROLLUP`, `CUBE` or `GROUPING SETS`. ROLLUP gives a misleading
    error ("must appear in the GROUP BY clause") rather than "not
    supported".
- **Data-modifying CTEs:** `WITH d AS (DELETE ... RETURNING ...)`.
- **User-defined types:** enum types and domains.
- **Comments:** `COMMENT ON`.
- **Statement-level SQL:**
  - `PREPARE` and `EXECUTE` (the protocol's prepared statements work);
  - cursors, `DECLARE` and `FETCH`;
  - `LISTEN` and `NOTIFY`;
  - `LOCK TABLE`.
- **Collations:** `COLLATE` is not supported; text compares by bytes.
- **Settings accepted silently:**
  - `BEGIN ISOLATION LEVEL READ COMMITTED` runs serializable. That is
    stricter, so applications written for read committed meet more
    serialization failures to retry.
  - `SET timezone` is accepted, with no time types for it to affect.

### 2.3 Tier 3: large subsystems, likely out of scope unless wanted

- User functions and procedures (SQL and PL/pgSQL), `DO` blocks, triggers,
  and `$$` quoting.
- Roles, `GRANT`, and more than one database per server.
- Partitioning, replication, extensions, and full-text search with its own
  index types.
- A cost-based planner: left for now by the user (section 0).
- Parallel query: lexdb has one SQL thread by design.

### 2.4 Not SQL features

- **Memory.** Results and COPY output are held whole in memory: dumping 1M
  rows peaked at about 1 GB. Streaming results would fix both.
- **Errors:**
  - DETAIL is folded into the message rather than sent as its own field;
  - no error position is sent, so psql shows no `LINE` and caret;
  - `percent_rank` and `cume_dist` return numeric, as there is no float
    type.
- **Storage** (items 8 and 10 of 9.4):
  - no compression;
  - the file never shrinks;
  - the checkpoint pause under a heavy write load.
- **Speed:** batches rather than rows, and SIMD on top. SIMD needs a Lexell
  language or runtime change: the user's decision (items 11 and 12 of 9.4).

## 3. A proposed order

1. **Date and time types, and float8.** They unblock the most real schemas.
   The largest item, mostly for the time-zone rules.
2. **Upsert and its kin:** ON CONFLICT, UPDATE ... FROM, DELETE ... USING,
   TRUNCATE and SAVEPOINT. Moderate in size; ORMs need them. The easy Tier
   2 items can come with them:
   - `VALUES` as a query;
   - `JOIN ... USING`;
   - `DISTINCT ON`;
   - `FETCH FIRST`;
   - `CREATE TABLE ... AS`;
   - tables without a primary key.
3. **A sweep of functions:** regular expressions, strings, math and arrays.
   Each is cheap, and each can be checked against PostgreSQL 16 itself.
4. **A minimal `pg_catalog` and `information_schema`**, enough for psql's
   `\d` and the common drivers. This waits for the user's decision.
5. **Streaming results.**
6. **SCRAM and TLS**, before lexdb listens beyond loopback.

**Open questions for the user:**
- Is this order right?
- Should lexdb emulate the catalogs at all? That decides whether psql's
  `\d`, GUI tools and `pg_dump` will ever work against it.
