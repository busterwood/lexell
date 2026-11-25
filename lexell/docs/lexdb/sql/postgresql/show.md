# SHOW

Shows the value of a setting.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SHOW name
SHOW TIME ZONE
SHOW TRANSACTION ISOLATION LEVEL
SHOW ALL
```

## Arguments

*name*
: A setting of lexdb's (see [SET](set.md)), a custom setting (`myapp.user_id`), or one of the fixed values below.

`ALL`
: lexdb's settings, with their values, as rows of `name` and `setting`.

## Remarks

- The fixed values, for clients and tools that read them:

  | Name | Value |
  |---|---|
  | `server_version` | `16.0` |
  | `server_version_num` | `160000` |
  | `server_encoding`, `client_encoding` | `UTF8` |
  | `DateStyle` | `ISO, MDY` |
  | `IntervalStyle` | `postgres` |
  | `standard_conforming_strings` | `on` |
  | `integer_datetimes` | `on` |
  | `max_identifier_length` | `63` |
  | `transaction_isolation` | `serializable`; `read committed` in a block begun with that level, and after `SET default_transaction_isolation` |
  | `is_superuser` | `on` |
  | `transaction_read_only`, `default_transaction_read_only`, `in_hot_standby` | `on` on a replica, else `off` |

- `current_setting(name)` gives the same value as a function.

## Differences from PostgreSQL

- `server_version` is `16.0`, though lexdb follows PostgreSQL 18: clients choose their queries by it.
- `SHOW ALL` lists lexdb's settings only (and not `TimeZone`), not PostgreSQL's 300 and more.
- `transaction_read_only` is `off` even in a `READ ONLY` block, and `is_superuser` is `on` for every role.
- A name that `SET` accepted and ignored (`work_mem`) is 42704.

## Examples

### A. Settings and fixed values

<!-- example: postgresql -->
```sql
SHOW search_path;
SHOW TIME ZONE;
SHOW TRANSACTION ISOLATION LEVEL;
SHOW server_version;
SHOW standard_conforming_strings;
CREATE ROLE ann;
SET ROLE ann;
SHOW is_superuser;
RESET ROLE;
```

```text
 search_path
-------------
 public
(1 row)

 TimeZone
----------
 UTC
(1 row)

 transaction_isolation
-----------------------
 serializable
(1 row)

 server_version
----------------
 16.0
(1 row)

 standard_conforming_strings
-----------------------------
 on
(1 row)

CREATE ROLE
SET
 is_superuser
--------------
 on
(1 row)

RESET
```

### B. SHOW ALL

<!-- example: postgresql -->
```sql
SHOW ALL;
```

```text
        name        | setting
--------------------+----------
 max_recursion      | 1000
 statement_timeout  | 0
 max_statement_mem  | 262144kB
 search_path        | public
 lexdb_batch        | on
 lexdb_planner      | cost
 lexdb_autoanalyze  | on
 lexdb_range_delete | on
 max_match_steps    | 10000000
(9 rows)
```

### C. Errors

<!-- example: postgresql -->
```sql
SHOW nosuch;
```

```text
ERROR:  unrecognized configuration parameter "nosuch"
```

## See also

[SET](set.md) · [RESET](reset.md)
