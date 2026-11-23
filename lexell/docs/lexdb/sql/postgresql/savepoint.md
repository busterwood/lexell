# SAVEPOINT

Marks a point in a transaction block that the block can roll back to.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SAVEPOINT savepoint_name
```

## Arguments

*savepoint_name*
: A name for the point. A name used again makes a new savepoint; the older one stays, hidden until the newer is
  released.

## Remarks

- `ROLLBACK TO SAVEPOINT` undoes what the block did after the savepoint, and ends an error's abort; `RELEASE
  SAVEPOINT` forgets the savepoint and keeps what was done.
- Savepoints exist only inside a block: outside one, `SAVEPOINT` is 25P01.
- Drivers use savepoints to recover from an error in a block without losing it (psql's `ON_ERROR_ROLLBACK`, JDBC's
  `autosave`).

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

### A. Roll back part of a block

<!-- example: postgresql -->
```sql
BEGIN;
INSERT INTO item VALUES (1, 'pen');
SAVEPOINT before_ink;
INSERT INTO item VALUES (2, 'ink');
ROLLBACK TO SAVEPOINT before_ink;
INSERT INTO item VALUES (3, 'pad');
COMMIT;
SELECT * FROM item ORDER BY id;
```

```text
BEGIN
INSERT 0 1
SAVEPOINT
INSERT 0 1
ROLLBACK
INSERT 0 1
COMMIT
 id | name
----+------
  1 | pen
  3 | pad
(2 rows)
```

### B. Recover from an error

<!-- example: postgresql -->
```sql
BEGIN;
SAVEPOINT try_insert;
INSERT INTO item VALUES (1, 'again');
ROLLBACK TO try_insert;
UPDATE item SET name = 'again' WHERE id = 1;
COMMIT;
SELECT * FROM item ORDER BY id;
```

```text
BEGIN
SAVEPOINT
ERROR:  duplicate key value violates unique constraint "item_pkey"
DETAIL:  Key (id)=(1) already exists.
ROLLBACK
UPDATE 1
COMMIT
 id | name
----+-------
  1 | again
  3 | pad
(2 rows)
```

### C. A name used twice

<!-- example: postgresql -->
```sql
BEGIN;
SAVEPOINT s;
INSERT INTO item VALUES (4, 'clip');
SAVEPOINT s;
INSERT INTO item VALUES (5, 'tape');
ROLLBACK TO s;
SELECT id FROM item ORDER BY id;
RELEASE s;
ROLLBACK TO s;
SELECT id FROM item ORDER BY id;
COMMIT;
```

```text
BEGIN
SAVEPOINT
INSERT 0 1
SAVEPOINT
INSERT 0 1
ROLLBACK
 id
----
  1
  3
  4
(3 rows)

RELEASE
ROLLBACK
 id
----
  1
  3
(2 rows)

COMMIT
```

### D. Outside a block

<!-- example: postgresql -->
```sql
SAVEPOINT s;
```

```text
ERROR:  SAVEPOINT can only be used in transaction blocks
```

## See also

[RELEASE SAVEPOINT](release-savepoint.md) · [ROLLBACK TO SAVEPOINT](rollback-to-savepoint.md) · [BEGIN](begin.md)
