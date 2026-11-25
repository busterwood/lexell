# SET CONSTRAINTS

Sets when a transaction block checks its deferrable foreign keys and assertions: at the end of each statement, or at the commit.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SET CONSTRAINTS { ALL | name [, ...] } { DEFERRED | IMMEDIATE }
```

## Arguments

`ALL`
: Every deferrable constraint and assertion.

*name*
: A constraint or an [assertion](create-assertion.md), optionally schema-qualified. It must be a foreign key or an
  assertion declared `DEFERRABLE` (42809 otherwise; 42704 if there is no constraint or assertion of the name).

`DEFERRED`
: The checks wait for `COMMIT`.

`IMMEDIATE`
: The checks run at the end of each statement. The checks that were waiting run at once, and one that fails is an
  error now.

## Remarks

- It lasts until the end of the block. A constraint's own setting (`INITIALLY DEFERRED` or `INITIALLY IMMEDIATE`)
  applies again in the next block.
- Only foreign keys and assertions can be deferrable in lexdb, so only they are affected.
- An assertion set `IMMEDIATE` is checked at once for the writes made since it was deferred: a violation is 23514
  `assertion "name" is violated`, and the transaction is aborted as after any error. At `COMMIT` a deferred assertion
  that fails gives 23514 and the transaction is rolled back (see [CREATE ASSERTION](create-assertion.md), example C).
- `SET CONSTRAINTS` is the standard's statement (ISO/IEC 9075-2, 17.4); PostgreSQL has no assertions, and this form is
  lexdb's own.

## Differences from PostgreSQL

- Unique, primary key and exclusion constraints cannot be `DEFERRABLE` (see [CREATE TABLE](create-table.md)).
- Outside a block, `SET CONSTRAINTS` does nothing and gives no `WARNING`, even for a name that does not exist.

## Examples

<!--setup: postgresql
CREATE TABLE owner (id int PRIMARY KEY);
CREATE TABLE pet (name text, owner_id int CONSTRAINT pet_owner REFERENCES owner DEFERRABLE);
CREATE TABLE toy (name text, owner_id int CONSTRAINT toy_owner REFERENCES owner);
-->

The examples use these tables; `pet_owner` is deferrable and `toy_owner` is not:

```sql
CREATE TABLE owner (id int PRIMARY KEY);
CREATE TABLE pet (name text, owner_id int CONSTRAINT pet_owner REFERENCES owner DEFERRABLE);
CREATE TABLE toy (name text, owner_id int CONSTRAINT toy_owner REFERENCES owner);
```

### A. Insert the child first

<!-- example: postgresql -->
```sql
BEGIN;
INSERT INTO pet VALUES ('rex', 1);
ROLLBACK;
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
INSERT INTO pet VALUES ('rex', 1);
INSERT INTO owner VALUES (1);
COMMIT;
SELECT * FROM pet;
```

```text
BEGIN
ERROR:  insert or update on table "pet" violates foreign key constraint "pet_owner"
DETAIL:  Key (owner_id)=(1) is not present in table "owner".
ROLLBACK
BEGIN
SET CONSTRAINTS
INSERT 0 1
INSERT 0 1
COMMIT
 name | owner_id
------+----------
 rex  |        1
(1 row)
```

### B. IMMEDIATE runs the waiting checks

<!-- example: postgresql -->
```sql
BEGIN;
SET CONSTRAINTS pet_owner DEFERRED;
INSERT INTO pet VALUES ('tom', 2);
SET CONSTRAINTS pet_owner IMMEDIATE;
ROLLBACK;
```

```text
BEGIN
SET CONSTRAINTS
INSERT 0 1
ERROR:  insert or update on table "pet" violates foreign key constraint "pet_owner"
DETAIL:  Key (owner_id)=(2) is not present in table "owner".
ROLLBACK
```

### C. A failing check at COMMIT

<!-- example: postgresql -->
```sql
BEGIN;
SET CONSTRAINTS pet_owner DEFERRED;
INSERT INTO pet VALUES ('tom', 2);
COMMIT;
SELECT count(*) FROM pet;
```

```text
BEGIN
SET CONSTRAINTS
INSERT 0 1
ERROR:  insert or update on table "pet" violates foreign key constraint "pet_owner"
DETAIL:  Key (owner_id)=(2) is not present in table "owner".
 count
-------
     1
(1 row)
```

### D. Errors

<!-- example: postgresql -->
```sql
BEGIN;
SET CONSTRAINTS toy_owner DEFERRED;
ROLLBACK;
BEGIN;
SET CONSTRAINTS nosuch DEFERRED;
ROLLBACK;
```

```text
BEGIN
ERROR:  constraint "toy_owner" is not deferrable
ROLLBACK
BEGIN
ERROR:  constraint "nosuch" does not exist
ROLLBACK
```

### E. An assertion

<!-- example: postgresql -->
```sql
CREATE TABLE cap (n int);
CREATE ASSERTION cap_small CHECK (NOT EXISTS (SELECT 1 FROM cap WHERE n > 10)) DEFERRABLE;
BEGIN;
SET CONSTRAINTS cap_small DEFERRED;
INSERT INTO cap VALUES (50);
SET CONSTRAINTS cap_small IMMEDIATE;
ROLLBACK;
BEGIN;
SET CONSTRAINTS ALL DEFERRED;
INSERT INTO cap VALUES (50);
UPDATE cap SET n = 5;
COMMIT;
SELECT n FROM cap;
```

```text
CREATE TABLE
CREATE ASSERTION
BEGIN
SET CONSTRAINTS
INSERT 0 1
ERROR:  assertion "cap_small" is violated
ROLLBACK
BEGIN
SET CONSTRAINTS
INSERT 0 1
UPDATE 1
COMMIT
 n
---
 5
(1 row)
```

## See also

[BEGIN](begin.md) · [COMMIT](commit.md) · [CREATE TABLE](create-table.md) · [CREATE ASSERTION](create-assertion.md)
