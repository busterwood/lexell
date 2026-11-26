# Connecting through the PostgreSQL door

The PostgreSQL door is lexdb's first and default listener. It speaks the PostgreSQL frontend/backend protocol 3.0
and PostgreSQL's SQL. lexdb reports itself as PostgreSQL 16.0 (`server_version`), and follows PostgreSQL 18 and 19
for SQL.

## Listening

Positional addresses after the data directory are this door's listeners (see
[server options](../server-options.md#addresses)):

```sh
lexdb ./data                                # 127.0.0.1:5433
lexdb ./data 127.0.0.1:5432 /run/lexdb      # TCP, and a Unix socket /run/lexdb/.s.PGSQL.5432
```

## The protocol

- **Simple and extended query protocols.** Several statements in one Query message; Parse, Bind, Describe,
  Execute, Close, Sync and Flush. After an error in the extended protocol the messages up to Sync are skipped, as
  PostgreSQL does. Named and unnamed prepared statements and portals work.
- **Text and binary results & parameters.** Binary parameters and binary results are supported across standard scalar types (`int2`, `int4`, `int8`, `oid`, `bool`, `float4`, `float8`, `numeric`, `text`, `varchar`, `bpchar`, `bytea`, `uuid`, `date`, `time`, `timestamp`, `timestamptz`, `json`, `jsonb`) and arrays of those — working out of the box with `asyncpg`, `psycopg` (`binary=True`), `Npgsql` / EF Core, and `pgjdbc` without special connection flags.
- **COPY** `FROM STDIN` and `TO STDOUT` in text and CSV format: see [bulk loading](../bulk-load.md#postgresql-copy).
- **ParameterStatus** at startup: `server_version` (16.0), `server_encoding` and `client_encoding` (UTF8),
  `DateStyle` (ISO, MDY), `integer_datetimes`, `standard_conforming_strings`, `TimeZone`, `application_name`,
  `default_transaction_read_only` and `in_hot_standby` (off on the master, on on a replica).
- **Cancel requests** (psql's Ctrl-C, JDBC's `Statement.cancel()`, libpq's `PQcancel`) stop a running statement with
  SQLSTATE 57014; `statement_timeout` does the same.
- **Not supported:** GSSAPI encryption (answered "no", as PostgreSQL does without it); the
  replication protocol; `LISTEN`/`NOTIFY`.

## Logins

- **Database name.** Any name is accepted, and the database is always `lexdb` (`current_database()`).
- **User name.** Under `--auth trust` (the default) any user name logs in. A name that is not a role has a
  superuser's rights. Under `--auth scram-sha-256` the user must be a role with `LOGIN` and a password, and the
  password is checked by SCRAM-SHA-256. `md5` and `password` authentication are not offered.
- `--auth-local` sets the method for Unix socket logins separately.
- **Schemas.** `search_path` is `public`. A login of the Oracle door has a schema of its name, made at its first Oracle
  connection, and the tables it makes are there with upper-case names: `SELECT * FROM sa."CITY"` (see the
  [Oracle door's schemas](oracle.md#schemas)). Tables made in this door are in `public`.

```sql
CREATE ROLE app LOGIN PASSWORD 'secret';
GRANT USAGE ON SCHEMA public TO app;
GRANT SELECT, INSERT, UPDATE, DELETE ON fruit TO app;
```

See [security](../security.md) for roles and privileges.

## TLS

With `--tls-cert FILE` (and `--tls-key FILE` when the key is in another file) the door answers an SSLRequest with
TLS. `--require-tls` refuses TCP logins without it.

```sh
lexdb ./data 127.0.0.1:5433 --tls-cert server.pem --tls-key server.key --require-tls
psql "host=127.0.0.1 port=5433 user=app dbname=lexdb sslmode=require"
```

Without `--tls-cert` an SSLRequest is answered "no", and clients with `sslmode=prefer` (libpq's default) go on
without TLS.

## Connection strings

| Client | Example |
|---|---|
| libpq, psql, psycopg | `host=127.0.0.1 port=5433 user=app dbname=lexdb` or `postgresql://app@127.0.0.1:5433/lexdb` |
| pgjdbc | `jdbc:postgresql://127.0.0.1:5433/lexdb` |
| Lexell `postgres` | `host=127.0.0.1 port=5433 user=app dbname=lexdb` (libpq's syntax) |
| a Unix socket | `host=/run/lexdb port=5432` |

For a master and its replicas, list both and let the client choose by role: see [replicas](../replicas.md#postgresql).

## Clients known to work

Checked for this documentation (2026-11-23), against a lexdb built from the same tree:

- **psql 18.6**, including `\d`, `\dt`, `\d+`, `\l`, `\copy`.
- **pgjdbc 42.7.14**, with its default settings (below).
- **Lexell's `postgres` module** (lib/postgres).

Checked against LexDB (2026-11-26): **psql 18.6**, **pgjdbc 42.7.14**, **psycopg 3** (text & binary), **asyncpg 0.32** (including arrays and binary parameters), **SQLAlchemy 2.1 + Alembic autogenerate**, **Django 6.1** (migrations, ORM, introspection), **Npgsql / Entity Framework Core 9**, **node-postgres 8 + Knex**, **pgbench**, and Lexell's `postgres` module. Server-side SQL cursors (`DECLARE` / `FETCH`) are not yet supported.

## psql

```sh
psql -h 127.0.0.1 -p 5433 -U postgres lexdb
```

<!-- example: postgresql -->
```sql
SELECT version();
SELECT current_user, current_database(), current_schema();
SHOW transaction_isolation;
```

```text
           version
-----------------------------
 PostgreSQL 16.0 (lexdb 0.1)
(1 row)

 current_user | current_database | current_schema
--------------+------------------+----------------
 postgres     | lexdb            | public
(1 row)

 transaction_isolation
-----------------------
 serializable
(1 row)
```

## Java: pgjdbc

[PgHello.java](examples/java/PgHello.java) makes a table, inserts rows with a batch of prepared statements, reads them
back, and shows a transaction rolled back by a CHECK constraint.

```sh
javac -d out docs/lexdb/connect/examples/java/PgHello.java
java -cp out:postgresql-42.7.14.jar PgHello 'jdbc:postgresql://127.0.0.1:5433/lexdb' postgres x
```

```
server: PostgreSQL 16.0
batch: 3 rows
transaction: rolled back, SQLSTATE 23514
1 apple 1.20
2 pear 0.85
3 plum 2.40
```

The driver is on Maven Central as `org.postgresql:postgresql`
(`https://repo1.maven.org/maven2/org/postgresql/postgresql/42.7.14/postgresql-42.7.14.jar`).

lexdb takes pgjdbc's binary parameters (`BigDecimal`, `UUID`, `byte[]`) and its binary results (after a statement has run five times, `prepareThreshold`), so no connection setting is needed.

## Lexell: lib/postgres

[pg_hello.lxl](examples/lexell/pg_hello.lxl) does the same with Lexell's own client, which speaks the protocol
itself (no libpq):

```sh
lexell/compiler/out/lxlc lexell/docs/lexdb/connect/examples/lexell/pg_hello.lxl -o pg_hello
./pg_hello "host=127.0.0.1 port=5433 user=postgres dbname=lexdb"
```

```
server: PostgreSQL 16.0 (lexdb 0.1)
transaction: rolled back, SQLSTATE 23514
1 apple 1.20
2 pear 0.85
3 plum 2.40
```

lib/postgres has no COPY: use psql's `\copy` or another driver for bulk loads.

## See also

- [The PostgreSQL SQL reference](../sql/postgresql/README.md)
- [Bulk loading with COPY](../bulk-load.md#postgresql-copy)
- [Read replicas](../replicas.md#postgresql)
