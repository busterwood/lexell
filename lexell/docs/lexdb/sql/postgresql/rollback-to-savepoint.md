# ROLLBACK TO SAVEPOINT

Undoes what a transaction block did after a savepoint.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
ROLLBACK [ WORK | TRANSACTION ] TO [ SAVEPOINT ] savepoint_name
```

## Arguments

*savepoint_name*
: The savepoint. If the name was used more than once, the newest.

## Remarks

- The block goes back to where it was at the savepoint: rows and DDL. Values taken by `nextval` are not given back.
- The savepoint stays, and can be rolled back to again; the savepoints made after it are released.
- After an error, `ROLLBACK TO SAVEPOINT` ends the abort, and the block goes on.
- A name that is not a savepoint of the block is 3B001, which aborts the block. Outside a block it is 25P01.

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

### A. Roll back, and roll back again

<!-- example: postgresql -->
```sql
BEGIN;
INSERT INTO item VALUES (1, 'pen');
SAVEPOINT a;
INSERT INTO item VALUES (2, 'ink');
ROLLBACK TO a;
INSERT INTO item VALUES (3, 'pad');
ROLLBACK TO SAVEPOINT a;
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
ROLLBACK
COMMIT
 id | name
----+------
  1 | pen
(1 row)
```

### B. DDL rolled back to a savepoint

<!-- example: postgresql -->
```sql
BEGIN;
CREATE TABLE note (body text);
SAVEPOINT made;
DROP TABLE note;
ROLLBACK TO made;
INSERT INTO note VALUES ('kept');
COMMIT;
SELECT * FROM note;
```

```text
BEGIN
CREATE TABLE
SAVEPOINT
DROP TABLE
ROLLBACK
INSERT 0 1
COMMIT
 body
------
 kept
(1 row)
```

### C. Ending an error's abort

<!-- example: postgresql -->
```sql
BEGIN;
SAVEPOINT s;
SELECT 1 / 0;
SELECT 2;
ROLLBACK TO s;
SELECT 3;
COMMIT;
```

```text
BEGIN
SAVEPOINT
ERROR:  division by zero
ERROR:  current transaction is aborted, commands ignored until end of transaction block
ROLLBACK
 ?column?
----------
        3
(1 row)

COMMIT
```

### D. Errors

<!-- example: postgresql -->
```sql
BEGIN;
ROLLBACK TO nosuch;
ROLLBACK;
ROLLBACK TO s;
```

```text
BEGIN
ERROR:  savepoint "nosuch" does not exist
ROLLBACK
ERROR:  ROLLBACK TO SAVEPOINT can only be used in transaction blocks
```

## See also

[SAVEPOINT](savepoint.md) · [RELEASE SAVEPOINT](release-savepoint.md) · [ROLLBACK](rollback.md)
