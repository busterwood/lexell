# Catalog: statistics and other relations

`pg_stat_user_tables`, `pg_settings`, and the catalog relations that exist for clients but have no rows.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SELECT ... FROM [ pg_catalog. ] pg_stat_user_tables
SELECT ... FROM [ pg_catalog. ] pg_settings
SELECT ... FROM [ pg_catalog. ] { pg_description | pg_shdescription | pg_inherits | pg_trigger | pg_policy
    | pg_statistic_ext | pg_publication | pg_publication_namespace | pg_publication_rel | pg_extension
    | pg_foreign_table }
```

## Views

Each relation has all of PostgreSQL 18's columns.

`pg_stat_user_tables`: one row per table
: `relid`, `schemaname`, `relname`; lexdb keeps `n_tup_ins`, `n_tup_upd`, `n_tup_del`, `n_live_tup`,
  `n_mod_since_analyze`, `last_analyze`, `last_autoanalyze`, `analyze_count`, `autoanalyze_count`,
  `total_analyze_time` and `total_autoanalyze_time`. The scan and vacuum counters are 0.

`pg_settings`
: No rows. Use `SHOW` or `current_setting`.

`pg_description`, `pg_shdescription`
: No rows: lexdb has no `COMMENT ON`.

`pg_inherits`, `pg_trigger`, `pg_policy`, `pg_statistic_ext`, `pg_publication`, `pg_publication_namespace`,
`pg_publication_rel`, `pg_extension`, `pg_foreign_table`
: No rows: lexdb has no table inheritance or partitions, triggers, row security policies, extended statistics,
  publications, extensions or foreign tables. They exist so that psql's `\d` and drivers' metadata queries work.

## Remarks

- `n_live_tup` is the row count the planner uses; `ANALYZE` (or lexdb's automatic analyze, `lexdb_autoanalyze`)
  sets `last_analyze` and `n_mod_since_analyze` back to 0.

## Differences from PostgreSQL

- `pg_settings` has no rows; `SHOW ALL` gives lexdb's settings.
- `pg_stats`, `pg_statistic`, `pg_stat_activity`, `pg_stat_all_tables`, `pg_statio_user_tables`, `pg_locks`,
  `pg_operator`, `pg_cast`, `pg_authid`, `pg_timezone_names`, `information_schema.triggers` and
  `information_schema.domains` do not exist (42P01).
- `pg_class.reltuples` is not kept (see [catalog: tables](catalog-tables.md)).

## Examples

### A. Table statistics

<!-- example: postgresql -->
```sql
CREATE TABLE item (id int PRIMARY KEY, name text);
INSERT INTO item SELECT g, 'item ' || g FROM generate_series(1, 100) g;
DELETE FROM item WHERE id > 90;
UPDATE item SET name = upper(name) WHERE id <= 5;
SELECT relname, n_tup_ins, n_tup_upd, n_tup_del, n_live_tup, analyze_count FROM pg_stat_user_tables;
ANALYZE item;
SELECT n_live_tup, n_mod_since_analyze, analyze_count, last_analyze IS NOT NULL AS analyzed FROM pg_stat_user_tables;
```

```text
CREATE TABLE
INSERT 0 100
DELETE 10
UPDATE 5
 relname | n_tup_ins | n_tup_upd | n_tup_del | n_live_tup | analyze_count
---------+-----------+-----------+-----------+------------+---------------
 item    |       100 |         5 |        10 |         90 |             0
(1 row)

ANALYZE
 n_live_tup | n_mod_since_analyze | analyze_count | analyzed
------------+---------------------+---------------+----------
         90 |                   0 |             1 | t
(1 row)
```

### B. Relations with no rows

<!-- example: postgresql -->
```sql
SELECT (SELECT count(*) FROM pg_settings) AS settings, (SELECT count(*) FROM pg_description) AS descriptions,
       (SELECT count(*) FROM pg_trigger) AS triggers, (SELECT count(*) FROM pg_inherits) AS inherits,
       (SELECT count(*) FROM pg_extension) AS extensions;
```

```text
 settings | descriptions | triggers | inherits | extensions
----------+--------------+----------+----------+------------
        0 |            0 |        0 |        0 |          0
(1 row)
```

### C. Errors

<!-- example: postgresql -->
```sql
SELECT * FROM pg_stat_activity;
SELECT * FROM pg_stats;
```

```text
ERROR:  relation "pg_stat_activity" does not exist
ERROR:  relation "pg_stats" does not exist
```

## See also

[ANALYZE](analyze.md) · [SHOW](show.md) · [Catalog: tables and columns](catalog-tables.md)
