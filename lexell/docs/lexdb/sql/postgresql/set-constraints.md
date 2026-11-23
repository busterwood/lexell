# SET CONSTRAINTS

Sets when a transaction block checks its deferrable foreign keys: at the end of each statement, or at the commit.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
SET CONSTRAINTS { ALL | name [, ...] } { DEFERRED | IMMEDIATE }
```

## Arguments

`ALL`
: Every deferrable constraint.

*name*
: A constraint, optionally schema-qualified. It must be a foreign key declared `DEFERRABLE` (42809 otherwise; 42704
  if there is no constraint of the name).

`DEFERRED`
: The checks wait for `COMMIT`.

`IMMEDIATE`
: The checks run at the end of each statement. The checks that were waiting run at once, and one that fails is an
  error now.

## Remarks

- It lasts until the end of the block. A constraint's own setting (`INITIALLY DEFERRED` or `INITIALLY IMMEDIATE`)
  applies again in the next block.
- Only foreign keys can be deferrable in lexdb, so only they are affected.

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

## See also

[BEGIN](begin.md) · [COMMIT](commit.md) · [CREATE TABLE](create-table.md)
