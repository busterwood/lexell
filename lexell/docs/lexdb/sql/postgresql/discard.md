# DISCARD, DEALLOCATE

`DISCARD` drops the session's temporary objects and resets its state; `DEALLOCATE` drops a prepared statement.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
DISCARD { ALL | PLANS | SEQUENCES | TEMPORARY | TEMP }
DEALLOCATE [ PREPARE ] { name | ALL }
```

## Arguments

`ALL`
: Drops the session's temporary objects, runs `RESET ALL`, and releases the session's advisory locks. Connection
  poolers send it when a connection goes back to the pool. It cannot run in a transaction block (25001).

`PLANS`
: Accepted and does nothing: a kept plan follows changes to the catalog anyway.

`SEQUENCES`
: Accepted and does nothing.

`TEMPORARY`, `TEMP`
: Drops the session's temporary tables, views and sequences.

`DEALLOCATE`
: Accepted and does nothing. Prepared statements of the protocol (named in Parse messages) are closed by the
  client's Close message; SQL-level `PREPARE` does not exist in lexdb.

## Remarks

- `DISCARD` changes only the session that runs it.

## Differences from PostgreSQL

- `DISCARD ALL` does not reset the role (`SET ROLE`) or the session authorization.
- After `DISCARD SEQUENCES`, `currval` still gives the last value; PostgreSQL gives 55000 (`currval of sequence
  "s" is not yet defined in this session`).
- `DEALLOCATE` does nothing, as there is no SQL-level `PREPARE`, and its command tag is `SET`.

## Examples

### A. DISCARD TEMP

<!-- example: postgresql -->
```sql
CREATE TEMP TABLE scratch (x int);
DISCARD TEMP;
SELECT * FROM scratch;
```

```text
CREATE TABLE
DISCARD TEMP
ERROR:  relation "scratch" does not exist
```

### B. DISCARD ALL

<!-- example: postgresql -->
```sql
SET statement_timeout = 5000;
CREATE TEMP TABLE scratch (x int);
DISCARD ALL;
SHOW statement_timeout;
SELECT count(*) FROM pg_tables WHERE tablename = 'scratch';
BEGIN;
DISCARD ALL;
ROLLBACK;
```

```text
SET
CREATE TABLE
DISCARD ALL
 statement_timeout
-------------------
 0
(1 row)

 count
-------
     0
(1 row)

BEGIN
ERROR:  DISCARD ALL cannot run inside a transaction block
ROLLBACK
```

### C. DISCARD SEQUENCES

<!-- example: postgresql -->
```sql
CREATE SEQUENCE s;
SELECT nextval('s');
DISCARD SEQUENCES;
SELECT currval('s');
```

```text
CREATE SEQUENCE
 nextval
---------
       1
(1 row)

DISCARD SEQUENCES
 currval
---------
       1
(1 row)
```

### D. DEALLOCATE

<!-- example: postgresql -->
```sql
DEALLOCATE ALL;
DEALLOCATE PREPARE stmt1;
```

```text
SET
SET
```

## See also

[SET](set.md) · [RESET](reset.md)
