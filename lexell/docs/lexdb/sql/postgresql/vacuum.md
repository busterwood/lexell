# VACUUM

Rewrites a table's leaves into the column layout; with `ANALYZE`, also gathers statistics.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
VACUUM [ ( option [, ...] ) ] [ table_name [ ( column_name [, ...] ) ] [, ...] ]
VACUUM [ FULL ] [ FREEZE ] [ VERBOSE ] [ ANALYZE ] [ table_name [ ( column_name [, ...] ) ] [, ...] ]
```

*option* is one of PostgreSQL's: `FULL`, `FREEZE`, `VERBOSE`, `ANALYZE`, `DISABLE_PAGE_SKIPPING`, `SKIP_LOCKED`,
`INDEX_CLEANUP`, `PROCESS_MAIN`, `PROCESS_TOAST`, `TRUNCATE`, `PARALLEL`, `SKIP_DATABASE_STATS`,
`ONLY_DATABASE_STATS`, `BUFFER_USAGE_LIMIT`.

## Arguments

*table_name*
: A table. Without one, every table.

`ANALYZE`
: Also runs [ANALYZE](analyze.md). A column list needs it.

The other options
: Accepted.

## Remarks

- lexdb has no dead rows to reclaim: a `DELETE` or `UPDATE` frees its space when it commits. `VACUUM` writes the
  table's leaves that still hold rows in the older row form (after `ALTER TABLE`, say) as column leaves, which
  scans read faster.
- `VACUUM` cannot run inside a transaction block (25001), as in PostgreSQL.

## Differences from PostgreSQL

- `VACUUM` reclaims nothing, as nothing is left to reclaim. `VACUUM FULL` does what `VACUUM` does, and the data
  file never shrinks (lexdb-gaps.md 2.4).

## Examples

<!--setup: postgresql
CREATE TABLE item (id int PRIMARY KEY, kind int);
INSERT INTO item SELECT g, g % 7 FROM generate_series(1, 500) AS g;
-->

The examples use one table:

```sql
CREATE TABLE item (id int PRIMARY KEY, kind int);
INSERT INTO item SELECT g, g % 7 FROM generate_series(1, 500) AS g;
```

### A. VACUUM and its options

<!-- example: postgresql -->
```sql
VACUUM item;
VACUUM FULL item;
VACUUM (VERBOSE, ANALYZE) item;
VACUUM;
```

```text
VACUUM
VACUUM
VACUUM
VACUUM
```

### B. Errors

<!-- example: postgresql -->
```sql
VACUUM item (kind);
VACUUM (FULL, PARALLEL 2) item;
BEGIN;
VACUUM item;
ROLLBACK;
```

```text
ERROR:  ANALYZE option must be specified when a column list is provided
ERROR:  VACUUM FULL cannot be performed in parallel
BEGIN
ERROR:  VACUUM cannot run inside a transaction block
ROLLBACK
```

## See also

[ANALYZE](analyze.md) · [CHECKPOINT](checkpoint.md)
