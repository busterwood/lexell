# RELEASE SAVEPOINT

Forgets a savepoint, keeping what was done since it.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
RELEASE [ SAVEPOINT ] savepoint_name
```

## Arguments

*savepoint_name*
: The savepoint. If the name was used more than once, the newest.

## Remarks

- The savepoints made after it are released too.
- The changes stay part of the block, and are kept or undone with it.
- A name that is not a savepoint of the block is 3B001, which aborts the block. Outside a block, `RELEASE` is 25P01.

## Differences from PostgreSQL

None known.

## Examples

<!--setup: postgresql
CREATE TABLE item (id int PRIMARY KEY, name text);
-->

The examples use one table:

```sql
CREATE TABLE item (id int PRIMARY KEY, name text);
```

### A. Release savepoints

<!-- example: postgresql -->
```sql
BEGIN;
SAVEPOINT a;
INSERT INTO item VALUES (1, 'pen');
SAVEPOINT b;
INSERT INTO item VALUES (2, 'ink');
RELEASE SAVEPOINT a;
ROLLBACK TO b;
COMMIT;
SELECT * FROM item ORDER BY id;
```

```text
BEGIN
SAVEPOINT
INSERT 0 1
SAVEPOINT
INSERT 0 1
RELEASE
ERROR:  savepoint "b" does not exist
ROLLBACK
 id | name
----+------
(0 rows)
```

### B. A savepoint that does not exist

<!-- example: postgresql -->
```sql
BEGIN;
RELEASE nosuch;
SELECT 1;
ROLLBACK;
RELEASE a;
```

```text
BEGIN
ERROR:  savepoint "nosuch" does not exist
ERROR:  current transaction is aborted, commands ignored until end of transaction block
ROLLBACK
ERROR:  RELEASE SAVEPOINT can only be used in transaction blocks
```

## See also

[SAVEPOINT](savepoint.md) · [ROLLBACK TO SAVEPOINT](rollback-to-savepoint.md)
