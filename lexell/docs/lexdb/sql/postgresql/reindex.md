# REINDEX

Accepted for PostgreSQL's tools: lexdb's indexes do not need rebuilding.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
REINDEX [ ( option [, ...] ) ] { INDEX | TABLE | SCHEMA } [ CONCURRENTLY ] name
REINDEX [ ( option [, ...] ) ] { DATABASE | SYSTEM } [ CONCURRENTLY ] [ name ]

option:
    CONCURRENTLY [ boolean ] | TABLESPACE new_tablespace | VERBOSE [ boolean ]
```

## Arguments

*name*
: The index, table or schema; for `DATABASE` and `SYSTEM`, `lexdb` or nothing.

## Remarks

- The index, table or schema named must exist. Then `REINDEX` does nothing: lexdb's B+trees reuse their pages as
  rows are freed.
- `REINDEX DATABASE`, `REINDEX SYSTEM` and `REINDEX ... CONCURRENTLY` cannot run inside a transaction block
  (25001), as in PostgreSQL.

## Differences from PostgreSQL

- Nothing is rebuilt.

## Examples

<!--setup: postgresql
CREATE TABLE item (id int PRIMARY KEY, kind int);
CREATE INDEX item_kind ON item (kind);
-->

The examples use one table with an index:

```sql
CREATE TABLE item (id int PRIMARY KEY, kind int);
CREATE INDEX item_kind ON item (kind);
```

### A. Its forms

<!-- example: postgresql -->
```sql
REINDEX INDEX item_kind;
REINDEX TABLE item;
REINDEX SCHEMA public;
REINDEX DATABASE lexdb;
```

```text
REINDEX
REINDEX
REINDEX
REINDEX
```

### B. Errors

<!-- example: postgresql -->
```sql
REINDEX INDEX nosuch;
REINDEX DATABASE other;
BEGIN;
REINDEX DATABASE;
ROLLBACK;
```

```text
ERROR:  relation "nosuch" does not exist
ERROR:  can only reindex the currently open database
BEGIN
ERROR:  REINDEX DATABASE cannot run inside a transaction block
ROLLBACK
```

## See also

[CREATE INDEX](create-index.md) · [VACUUM](vacuum.md)
