# SET

Changes a setting of the session.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SET [ SESSION | LOCAL ] configuration_parameter { TO | = } { value | 'value' | DEFAULT }
SET [ SESSION | LOCAL ] TIME ZONE { value | 'value' | LOCAL | DEFAULT }
SET SCHEMA 'schema_name'
```

## Arguments

`SESSION`
: The default: the setting lasts until the session ends, or until a transaction block it was set in rolls back.

`LOCAL`
: For `TIME ZONE` and custom settings (`a.b`): the setting lasts until the end of the transaction block.

*configuration_parameter*
: One of lexdb's settings:

  | Setting | Default | What it does |
  |---|---|---|
  | `search_path` | `public` | The schemas a name without a schema is looked up in, in order. A list of names or one string (`'app, public'`). `SET SCHEMA 'x'` is `SET search_path = x`. |
  | `TimeZone` | `UTC` | The time zone of `timestamptz` input and output: a name (`'Europe/London'`), `LOCAL` (the server's), or an offset in hours. |
  | `statement_timeout` | `0` | Milliseconds (or `'2s'`, `'1min'`) a statement may run before 57014; 0 is no limit. |
  | `max_statement_mem` | `256MB` | The memory a statement may hold for sorts, groups and the like, before 53200. |
  | `max_recursion` | `1000` | Rounds a recursive `WITH` query may add rows in, before 54001; 0 is no limit. |
  | `max_match_steps` | `10000000` | Steps a `MATCH_RECOGNIZE` search from one row may take, before 54001; 0 is no limit. |
  | `lexdb_planner` | `cost` | `cost`, or `rules` for the older rule-based plans. |
  | `lexdb_batch` | `on` | Whether scans and operators work on batches of rows; `off` runs them a row at a time. |
  | `lexdb_autoanalyze` | `on` | Whether the session's changes count towards the statistics that are gathered on their own. |
  | `lexdb_range_delete` | `on` | Whether a `DELETE` of a primary key range drops the range whole (see [DELETE](delete.md)). |
  | `query_rewrite_enabled` | `on` | Whether the planner rewrites eligible `SELECT` queries onto materialized views created with `ENABLE QUERY REWRITE`. |

  A name with a dot (`myapp.user_id`) is a custom setting: any text, read with `SHOW` or `current_setting`.

  Other names of PostgreSQL's (`work_mem`, `client_min_messages`, `application_name` ...) are accepted and ignored,
  so that clients that set them work.

`DEFAULT`
: The setting's default. `RESET` does the same (see [RESET](reset.md)).

## Remarks

- A `SET` in a transaction block that rolls back is undone.
- `set_config(name, value, is_local)` is the function form.
- `pg_settings` is empty; `SHOW ALL` lists lexdb's settings.

## Differences from PostgreSQL

- Settings lexdb does not have are accepted and ignored by `SET`; `SHOW` of one is 42704 afterwards.
- `SET LOCAL` of lexdb's own settings (`SET LOCAL statement_timeout = 10`) is accepted and does nothing; for `TIME
  ZONE` and custom settings it works.
- `pg_settings` has no rows.
- `search_path` is `public` by default; PostgreSQL's is `"$user", public`.

## Examples

### A. statement_timeout

<!-- example: postgresql -->
```sql
SET statement_timeout = 20;
SELECT count(*) FROM generate_series(1, 100000000);
SET statement_timeout TO '2s';
SHOW statement_timeout;
SET statement_timeout = DEFAULT;
SHOW statement_timeout;
```

```text
SET
ERROR:  canceling statement due to statement timeout
SET
 statement_timeout
-------------------
 2000ms
(1 row)

SET
 statement_timeout
-------------------
 0
(1 row)
```

### B. Time zone

<!-- example: postgresql -->
```sql
SET TIME ZONE 'Europe/London';
SELECT TIMESTAMPTZ '2026-07-01 12:00:00+00' AS summer, TIMESTAMPTZ '2026-01-01 12:00:00+00' AS winter;
SET TIME ZONE 'Nowhere/Land';
SET TIME ZONE DEFAULT;
SHOW TimeZone;
```

```text
SET
         summer         |         winter
------------------------+------------------------
 2026-07-01 13:00:00+01 | 2026-01-01 12:00:00+00
(1 row)

ERROR:  invalid value for parameter "TimeZone": "Nowhere/Land"
SET
 TimeZone
----------
 UTC
(1 row)
```

### C. search_path

<!-- example: postgresql -->
```sql
CREATE SCHEMA app;
SET search_path = app, public;
SHOW search_path;
SET SCHEMA 'public';
SHOW search_path;
```

```text
CREATE SCHEMA
SET
 search_path
-------------
 app, public
(1 row)

SET
 search_path
-------------
 public
(1 row)
```

### D. Custom settings, and LOCAL

<!-- example: postgresql -->
```sql
SET myapp.user_id = '42';
SELECT current_setting('myapp.user_id');
BEGIN;
SET LOCAL myapp.user_id = '7';
SHOW myapp.user_id;
COMMIT;
SHOW myapp.user_id;
```

```text
SET
 current_setting
-----------------
 42
(1 row)

BEGIN
SET
 myapp.user_id
---------------
 7
(1 row)

COMMIT
 myapp.user_id
---------------
 42
(1 row)
```

### E. Rolled back with the block

<!-- example: postgresql -->
```sql
BEGIN;
SET max_recursion = 10;
SHOW max_recursion;
ROLLBACK;
SHOW max_recursion;
SHOW max_statement_mem;
```

```text
BEGIN
SET
 max_recursion
---------------
 10
(1 row)

ROLLBACK
 max_recursion
---------------
 1000
(1 row)

 max_statement_mem
-------------------
 262144kB
(1 row)
```

### F. Settings lexdb does not have

<!-- example: postgresql -->
```sql
SET work_mem = '64MB';
SHOW work_mem;
SET lexdb_planner = fast;
```

```text
SET
ERROR:  unrecognized configuration parameter "work_mem"
ERROR:  invalid value for parameter "lexdb_planner": use cost or rules
```

## See also

[RESET](reset.md) · [SHOW](show.md) · [SET ROLE](set-role.md)
