# Restoring PostgreSQL backups (`pg_dump` & `pg_restore`)

LexDB restores standard **PostgreSQL `pg_dump` backups** directly over its PostgreSQL wire protocol (`pgwire`) using stock `psql` and `pg_restore` — supporting all four `pg_dump` output formats:

- **Plain SQL (`-Fp`)** via `psql -f dump.sql`
- **Custom archive (`-Fc`)** via `pg_restore`
- **Tar archive (`-Ft`)** via `pg_restore`
- **Directory archive (`-Fd`)** via `pg_restore`

Because `pg_restore` unpacks custom, tar, and directory archives client-side and streams standard SQL + `COPY ... FROM stdin` over `pgwire`, you can take an existing PostgreSQL backup and load it straight into LexDB with no conversion step.

---

## Quick start

### 1. Custom archive (`-Fc`, recommended)

```sh
# Dump from PostgreSQL
pg_dump -h pg-host -U postgres -Fc mydb > mydb.dump

# Restore into LexDB
pg_restore -h 127.0.0.1 -p 5433 -U postgres -d lexdb --exit-on-error mydb.dump
```

### 2. Plain SQL dump (`-Fp`)

```sh
# Dump from PostgreSQL
pg_dump -h pg-host -U postgres -Fp mydb > mydb.sql

# Restore into LexDB
psql -h 127.0.0.1 -p 5433 -U postgres -d lexdb -v ON_ERROR_STOP=1 -f mydb.sql
```

### 3. Tar (`-Ft`) and directory (`-Fd`) archives

```sh
pg_dump -h pg-host -U postgres -Ft mydb > mydb.tar
pg_restore -h 127.0.0.1 -p 5433 -U postgres -d lexdb --exit-on-error mydb.tar

pg_dump -h pg-host -U postgres -Fd mydb -f mydb_dir
pg_restore -h 127.0.0.1 -p 5433 -U postgres -d lexdb --exit-on-error mydb_dir
```

### 4. Useful `pg_dump` / `pg_restore` flags

| Flag | Works in LexDB | Notes |
|---|:-:|---|
| `--clean --if-exists` | Yes | Drops existing objects cleanly on both empty and populated LexDB databases. |
| `--single-transaction` (`-1`) | Yes | Restores schema and data atomically in one transaction. |
| `--no-owner` (`-O`) | Yes | Recommended when the source PostgreSQL database has roles that have not been created in LexDB. |
| `--inserts` / `--column-inserts` | Yes | Including `INSERT ... OVERRIDING SYSTEM VALUE` for `GENERATED ALWAYS AS IDENTITY` columns. |
| `--schema-only` / `--data-only` | Yes | Useful for staged restores or inspecting schema compatibility first. |
| `-t table` / `-n schema` | Yes | Selective table or schema restore via `pg_restore`. |
| `-j N` (`--jobs`) | Use `-j 1` | Keep the default single job; LexDB runs SQL on one thread and parallel DDL jobs (`-j > 1`) can hit `SERIALIZABLE` DDL conflicts. |

---

## What is restored

Verified end-to-end against PostgreSQL 18.6 `pg_dump` and `pg_restore` with exact row-for-row parity:

- **Dump header settings:** All standard `pg_dump` `SET` GUCs (`statement_timeout`, `lock_timeout`, `idle_in_transaction_session_timeout`, `transaction_timeout`, `client_encoding`, `standard_conforming_strings`, `check_function_bodies`, `xmloption`, `client_min_messages`, `row_security`, `default_tablespace`, `default_table_access_method`) and `SELECT pg_catalog.set_config('search_path', '', false)`.
- **Schemas & custom types:** `CREATE SCHEMA`, `CREATE TYPE ... AS ENUM (...)`, `ALTER TYPE ... OWNER TO`.
- **Tables & columns:** All standard PostgreSQL types (`smallint`, `integer`, `bigint`, `numeric(p,s)`, `real`, `double precision`, `boolean`, `text`, `varchar(n)`, `char(n)`, `date`, `time`, `timestamp`, `timestamptz`, `interval`, `uuid`, `bytea`, `json`, `jsonb`, arrays, enums), `GENERATED ALWAYS AS (...) STORED` columns, and quoted mixed-case identifiers.
- **Sequences, `SERIAL`, and `IDENTITY`:** `CREATE SEQUENCE`, `ALTER SEQUENCE ... OWNED BY`, `ALTER TABLE ONLY ... SET DEFAULT nextval('public.t_id_seq'::regclass)`, `ALTER TABLE ... ALTER COLUMN ... ADD GENERATED {ALWAYS | BY DEFAULT} AS IDENTITY (SEQUENCE NAME ...)`, and `SELECT pg_catalog.setval(...)` so post-restore inserts continue cleanly from the next sequence value.
- **Table data:** Standard `COPY ... FROM stdin` text format (including `\N` nulls, `\t`/`\n`/`\r`/`\\` escapes, empty strings, Unicode, `bytea`, `jsonb`, arrays, and empty tables) as well as `--inserts`.
- **Constraints & indexes:** `PRIMARY KEY`, `UNIQUE`, `CHECK`, `FOREIGN KEY` (including composite keys, self-references, `ON DELETE`/`ON UPDATE` actions, and `DEFERRABLE INITIALLY DEFERRED`), B+tree indexes (`USING btree`), descending indexes, partial indexes (`WHERE ...`), and expression indexes (`lower(email)`, etc.).
- **Views, materialized views & SQL routines:** `CREATE VIEW`, `CREATE MATERIALIZED VIEW ... WITH NO DATA` + `REFRESH MATERIALIZED VIEW`, `CREATE FUNCTION ... LANGUAGE sql`, `CREATE PROCEDURE ... LANGUAGE sql`.
- **Ownership, privileges & comments:** `ALTER SCHEMA | TABLE [ONLY] | VIEW | MATERIALIZED VIEW | SEQUENCE | TYPE | FUNCTION | PROCEDURE ... OWNER TO`, `GRANT` / `REVOKE`, and `COMMENT ON ... IS '...' | NULL` (accepted cleanly; comments are not stored).

---

## Roles and ownership

When connecting to a fresh LexDB instance without `--auth`, connecting as `-U postgres` makes `postgres` the active session user, so standard `ALTER ... OWNER TO postgres;` statements in a default `pg_dump` succeed automatically.

If your source dump contains objects owned by additional PostgreSQL roles (for example `app_user`):

- Either pre-create those roles in LexDB (`CREATE ROLE app_user;`) before restoring, **or**
- Pass `--no-owner` (`-O`) to `pg_dump` or `pg_restore`.

---

## Current limitations

If your PostgreSQL dump includes features LexDB's PostgreSQL door does not implement yet, omit or migrate them separately:

- **`LANGUAGE plpgsql` functions & triggers:** LexDB's PostgreSQL door supports `LANGUAGE sql` functions and procedures (PL/SQL is supported in the Oracle door and T-SQL routines in the SQL Server door). `CREATE TRIGGER` and `LANGUAGE plpgsql` routines will return an error unless omitted or restored without `--exit-on-error`.
- **PostgreSQL extensions, domains, RLS policies, and partitioning:** `CREATE EXTENSION`, `CREATE DOMAIN`, `CREATE POLICY`, and declarative `PARTITION BY` clauses are not yet supported.
- **Dumping out of LexDB:** Running PostgreSQL's `pg_dump` client *against* LexDB as a source is not supported yet; use `COPY ... TO STDOUT` (see [Bulk loading](bulk-load.md)) to export table data.
