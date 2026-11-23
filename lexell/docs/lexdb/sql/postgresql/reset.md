# RESET

Gives a setting of the session its default again.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
RESET configuration_parameter
RESET TIME ZONE
RESET ALL
```

## Arguments

*configuration_parameter*
: A setting (see [SET](set.md)). `RESET x` is `SET x TO DEFAULT`.

`ALL`
: Every setting of lexdb's.

## Remarks

- `RESET ROLE` and `RESET SESSION AUTHORIZATION` are described in [SET ROLE](set-role.md).
- A custom setting (`myapp.user_id`) is removed by `RESET`.

## Differences from PostgreSQL

- After `RESET` of a custom setting, `SHOW` of it is 42704 (`unrecognized configuration parameter`); PostgreSQL
  shows an empty value.

## Examples

### A. One setting, and all

<!-- example: postgresql -->
```sql
SET statement_timeout = 5000;
SET max_recursion = 10;
RESET statement_timeout;
SHOW statement_timeout;
SHOW max_recursion;
RESET ALL;
SHOW max_recursion;
```

```text
SET
SET
RESET
 statement_timeout
-------------------
 0
(1 row)

 max_recursion
---------------
 10
(1 row)

RESET
 max_recursion
---------------
 1000
(1 row)
```

### B. The time zone and a custom setting

<!-- example: postgresql -->
```sql
SET TIME ZONE 'Asia/Tokyo';
RESET TIME ZONE;
SHOW TimeZone;
SET myapp.mode = 'test';
RESET myapp.mode;
SHOW myapp.mode;
```

```text
SET
RESET
 TimeZone
----------
 UTC
(1 row)

SET
RESET
ERROR:  unrecognized configuration parameter "myapp.mode"
```

## See also

[SET](set.md) · [SHOW](show.md)
