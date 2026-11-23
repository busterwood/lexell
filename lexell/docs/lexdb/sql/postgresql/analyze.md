# ANALYZE

Gathers the statistics the planner uses to choose plans.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
ANALYZE [ ( option [, ...] ) ] [ VERBOSE ] [ [ ONLY ] table_name [ ( column_name [, ...] ) ] [, ...] ]

option:
    VERBOSE [ boolean ] | SKIP_LOCKED [ boolean ] | BUFFER_USAGE_LIMIT size
```

## Arguments

*table_name*
: A table to analyze. Without one, every table.

*column_name*
: Only these columns.

*option*, `VERBOSE`, `ONLY`
: Accepted.

## Remarks

- The statistics are each table's row count and, for each column, its number of distinct values, its most common
  values and a sample. The planner uses them for the order of joins and the choice of indexes (see
  [EXPLAIN](explain.md)).
- lexdb also gathers them on its own as tables change (`SET lexdb_autoanalyze`), so `ANALYZE` is needed mostly after
  a large load, before the first queries.
- `ANALYZE` may run inside a transaction block.

## Differences from PostgreSQL

- `pg_stats` does not exist (42P01), and `pg_class.reltuples` stays -1: the statistics are lexdb's own.
  `pg_stat_user_tables.n_live_tup` gives the row count.

## Examples

<!--setup: postgresql
CREATE TABLE item (id int PRIMARY KEY, kind int, name text);
INSERT INTO item SELECT g, g % 7, 'x' || g FROM generate_series(1, 500) AS g;
-->

The examples use a table of 500 rows:

```sql
CREATE TABLE item (id int PRIMARY KEY, kind int, name text);
INSERT INTO item SELECT g, g % 7, 'x' || g FROM generate_series(1, 500) AS g;
```

### A. A table, some columns, and everything

<!-- example: postgresql -->
```sql
ANALYZE item;
ANALYZE VERBOSE item (kind, name);
ANALYZE;
SELECT n_live_tup FROM pg_stat_user_tables WHERE relname = 'item';
```

```text
ANALYZE
ANALYZE
ANALYZE
 n_live_tup
------------
        500
(1 row)
```

### B. Errors

<!-- example: postgresql -->
```sql
ANALYZE nosuch;
ANALYZE item (nosuch);
ANALYZE (FOO) item;
```

```text
ERROR:  relation "nosuch" does not exist
ERROR:  column "nosuch" of relation "item" does not exist
ERROR:  unrecognized "ANALYZE" option "foo"
```

## See also

[EXPLAIN](explain.md) · [VACUUM](vacuum.md) · [SET](set.md)
