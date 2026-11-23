# Catalog: functions and procedures

`pg_proc`, `pg_language`, `information_schema.routines` and `information_schema.parameters`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SELECT ... FROM [ pg_catalog. ] pg_proc
SELECT ... FROM [ pg_catalog. ] pg_language
SELECT ... FROM information_schema.routines
SELECT ... FROM information_schema.parameters
```

## Views

Each relation has all of PostgreSQL 18's columns. The columns below are the ones lexdb fills in; the others are
NULL, zero, false or empty.

`pg_proc`: one row per function and procedure the user made
: `oid`, `proname`, `pronamespace`, `proowner`, `prolang` (14, `sql`), `procost`, `prokind` (`f` function, `p`
  procedure), `prosecdef`, `proisstrict`, `proretset`, `provolatile`, `proparallel`, `pronargs`,
  `pronargdefaults`, `prorettype` (2278 `void` for a procedure), `proargtypes`, `proallargtypes`, `proargmodes`,
  `proargnames`, `prosrc` (the body), `proacl`.

`pg_language`: three rows
: `internal`, `c` and `sql`, with `oid`, `lanname`, `lanispl`, `lanpltrusted`, `lanvalidator`.

`information_schema.routines`: one row per function and procedure
: `specific_catalog`, `specific_schema`, `specific_name` (the name and the oid), `routine_catalog`,
  `routine_schema`, `routine_name`, `routine_type` (`FUNCTION`, `PROCEDURE`), `data_type` and the `type_udt_`
  columns (a function's result), `routine_body` (`SQL`), `routine_definition`, `external_language`,
  `parameter_style`, `is_deterministic`, `sql_data_access`, `is_null_call`, `security_type`.

`information_schema.parameters`: one row per parameter
: `specific_catalog`, `specific_schema`, `specific_name`, `ordinal_position`, `parameter_mode` (`IN`, `OUT`,
  `INOUT`), `parameter_name`, `data_type`, `udt_name`, `parameter_default`.

## Remarks

- `pg_get_functiondef`, `pg_get_function_arguments` and `pg_get_function_result` show a function's definition
  (see [catalog functions](functions-catalog.md)).
- psql's `\df` lists functions and procedures.

## Differences from PostgreSQL

- `pg_proc` has no rows for built-in functions (`now`, `upper` ...), so `'now'::regproc` is 42883 and tools that
  list every function see only the user's.
- `pg_language` has no `plpgsql`: functions are `LANGUAGE sql` only.

## Examples

<!--setup: postgresql
CREATE FUNCTION tax(p numeric, rate numeric DEFAULT 0.2) RETURNS numeric LANGUAGE sql IMMUTABLE AS 'SELECT p * rate';
CREATE PROCEDURE log_it(msg text) LANGUAGE sql AS 'SELECT 1';
-->

The examples use this function and procedure:

```sql
CREATE FUNCTION tax(p numeric, rate numeric DEFAULT 0.2) RETURNS numeric LANGUAGE sql IMMUTABLE AS 'SELECT p * rate';
CREATE PROCEDURE log_it(msg text) LANGUAGE sql AS 'SELECT 1';
```

### A. pg_proc

<!-- example: postgresql -->
```sql
SELECT proname, prokind, provolatile, pronargs, pronargdefaults, prorettype::regtype AS returns, proargnames, prosrc
FROM pg_proc ORDER BY proname;
```

```text
 proname | prokind | provolatile | pronargs | pronargdefaults | returns | proargnames |     prosrc
---------+---------+-------------+----------+-----------------+---------+-------------+-----------------
 log_it  | p       | v           |        1 |               0 | void    | {msg}       | SELECT 1
 tax     | f       | i           |        2 |               1 | numeric | {p,rate}    | SELECT p * rate
(2 rows)
```

### B. pg_language

<!-- example: postgresql -->
```sql
SELECT lanname, lanpltrusted FROM pg_language ORDER BY oid;
```

```text
 lanname  | lanpltrusted
----------+--------------
 internal | f
 c        | f
 sql      | t
(3 rows)
```

### C. information_schema.routines and parameters

<!-- example: postgresql -->
```sql
SELECT routine_name, routine_type, data_type, routine_body, routine_definition FROM information_schema.routines
ORDER BY routine_name;
SELECT r.routine_name, p.ordinal_position, p.parameter_name, p.data_type, p.parameter_default
FROM information_schema.parameters p JOIN information_schema.routines r ON r.specific_name = p.specific_name
ORDER BY 1, 2;
```

```text
 routine_name | routine_type | data_type | routine_body | routine_definition
--------------+--------------+-----------+--------------+--------------------
 log_it       | PROCEDURE    |           | SQL          | SELECT 1
 tax          | FUNCTION     | numeric   | SQL          | SELECT p * rate
(2 rows)

 routine_name | ordinal_position | parameter_name | data_type | parameter_default
--------------+------------------+----------------+-----------+-------------------
 log_it       |                1 | msg            | text      |
 tax          |                1 | p              | numeric   |
 tax          |                2 | rate           | numeric   | 0.2
(3 rows)
```

### D. psql's list of functions

<!-- example: postgresql -->
```sql
\df
```

```text
                                List of functions
 Schema |  Name  | Result data type |         Argument data types         | Type
--------+--------+------------------+-------------------------------------+------
 public | log_it |                  | IN msg text                         | proc
 public | tax    | numeric          | p numeric, rate numeric DEFAULT 0.2 | func
(2 rows)
```

## See also

[CREATE FUNCTION](create-function.md) · [CREATE PROCEDURE](create-procedure.md) ·
[Catalog functions](functions-catalog.md) · [Catalog: roles and privileges](catalog-roles.md)
