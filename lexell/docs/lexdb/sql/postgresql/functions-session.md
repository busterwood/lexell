# Session information functions

Who is connected, to what, with which settings, in which transaction; and `pg_typeof`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
current_user → name
current_role → name
user → name
session_user → name
current_schema [ ( ) ] → name
current_database ( ) → name
version ( ) → text
current_setting ( setting [, missing_ok ] ) → text
set_config ( setting, value, is_local ) → text
pg_backend_pid ( ) → integer
txid_current ( ) → bigint
pg_current_xact_id ( ) → bigint
pg_typeof ( value ) → regtype
```

## Functions

`current_user`, `current_role`, `user`
: The role whose privileges apply now: the login role, or the role of `SET ROLE`.

`session_user`
: The role that logged in, or the role of `SET SESSION AUTHORIZATION`.

`current_schema`
: The first schema of `search_path`, where a table made without a schema goes.

`current_database`
: The database's name, `lexdb`.

`version`
: lexdb's version string, `PostgreSQL 16.0 (lexdb 0.1)`.

`current_setting`
: A setting's value as text, as `SHOW` gives it. An unknown name is 42704, or NULL with *missing_ok* true.

`set_config`
: Sets a setting, as `SET` does, and returns the value. With *is_local* true, as `SET LOCAL`: until the end of the
  transaction.

`pg_backend_pid`
: The session's number.

`txid_current`, `pg_current_xact_id`
: The current transaction's number; the same for every call in one transaction.

`pg_typeof`
: The name of the type of the value.

## Remarks

- `current_user`, `current_role`, `user`, `session_user` and `current_schema` are written without parentheses
  (`current_schema()` also works).
- See [SET](set.md) and [SHOW](show.md) for the settings lexdb has.

## Differences from PostgreSQL

- `current_catalog`, `current_schemas`, `pg_client_encoding`, `inet_server_port` (and the other `inet_*`),
  `pg_postmaster_start_time`, `current_query` and `pg_my_temp_schema` do not exist (42883).
- `current_schema` is the first schema of `search_path` even when it does not exist (PostgreSQL skips it).
- `pg_typeof` returns text, and says `text` for `name`, `oid`, the `reg` types and enum values, and for a string
  constant or NULL of no type (PostgreSQL: `unknown`).
- The result column of `current_role` and `user` is named `current_user`.
- `set` is not taken as a column alias (`AS set` is 42601).
- `version()` says 16.0, though lexdb follows PostgreSQL 18.

## Examples

### A. Users and roles

<!-- example: postgresql -->
```sql
SELECT current_user, session_user, current_role AS role, user AS u;
CREATE ROLE alice;
SET ROLE alice;
SELECT current_user, session_user;
RESET ROLE;
```

```text
 current_user | session_user |   role   |    u
--------------+--------------+----------+----------
 postgres     | postgres     | postgres | postgres
(1 row)

CREATE ROLE
SET
 current_user | session_user
--------------+--------------
 alice        | postgres
(1 row)

RESET
```

### B. Schema, database and version

<!-- example: postgresql -->
```sql
SELECT current_schema, current_database(), version();
CREATE SCHEMA app;
SET search_path = app, public;
SELECT current_schema();
RESET search_path;
```

```text
 current_schema | current_database |           version
----------------+------------------+-----------------------------
 public         | lexdb            | PostgreSQL 16.0 (lexdb 0.1)
(1 row)

CREATE SCHEMA
SET
 current_schema
----------------
 app
(1 row)

RESET
```

### C. current_setting and set_config

<!-- example: postgresql -->
```sql
SELECT current_setting('search_path') AS path, current_setting('TimeZone') AS tz,
       current_setting('no.such', true) AS missing;
SELECT set_config('myapp.user_id', '42', false) AS set_to, current_setting('myapp.user_id') AS now_set;
BEGIN;
SELECT set_config('myapp.mode', 'batch', true);
SELECT current_setting('myapp.mode');
COMMIT;
SELECT current_setting('myapp.mode', true) AS after_commit;
```

```text
  path  | tz  | missing
--------+-----+---------
 public | UTC |
(1 row)

 set_to | now_set
--------+---------
 42     | 42
(1 row)

BEGIN
 set_config
------------
 batch
(1 row)

 current_setting
-----------------
 batch
(1 row)

COMMIT
 after_commit
--------------

(1 row)
```

### D. The session and the transaction

The numbers change from run to run, so the example compares them.

<!-- example: postgresql -->
```sql
SELECT pg_backend_pid() > 0 AS pid, pg_typeof(pg_backend_pid()) AS pid_type, pg_typeof(txid_current()) AS xid_type;
BEGIN;
SELECT txid_current() = txid_current() AS same, txid_current() = pg_current_xact_id() AS same2;
COMMIT;
```

```text
 pid | pid_type | xid_type
-----+----------+----------
 t   | integer  | bigint
(1 row)

BEGIN
 same | same2
------+-------
 t    | t
(1 row)

COMMIT
```

### E. pg_typeof

<!-- example: postgresql -->
```sql
SELECT pg_typeof(1) AS a, pg_typeof(1.5) AS b, pg_typeof(now()) AS c, pg_typeof(ARRAY['x']) AS d,
       pg_typeof(DATE '2026-03-01' - 1) AS e, pg_typeof('x') AS f;
```

```text
    a    |    b    |            c             |   d    |  e   |  f
---------+---------+--------------------------+--------+------+------
 integer | numeric | timestamp with time zone | text[] | date | text
(1 row)
```

### F. Errors

<!-- example: postgresql -->
```sql
SELECT current_setting('no.such');
SELECT current_catalog;
```

```text
ERROR:  unrecognized configuration parameter "no.such"
ERROR:  function current_catalog with 0 arguments does not exist
```

## See also

[SET](set.md) · [SHOW](show.md) · [SET ROLE](set-role.md) · [Catalog functions](functions-catalog.md) ·
[Replication functions](functions-replication.md)
