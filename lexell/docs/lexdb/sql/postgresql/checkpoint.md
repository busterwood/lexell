# CHECKPOINT

Writes a checkpoint and waits until it is on disk.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CHECKPOINT
```

## Remarks

- A checkpoint writes the pages that commits have changed into the data file, so that recovery after a crash has
  less of the log to replay. lexdb takes them on its own; `CHECKPOINT` takes one now (design/lexdb.md 9.136).
- Only a superuser may run it (42501 otherwise), as in PostgreSQL.
- On a replica it does nothing.
- It may run inside a transaction block.

## Differences from PostgreSQL

None known.

## Examples

### A. A checkpoint, and a role that may not take one

<!-- example: postgresql -->
```sql
CHECKPOINT;
CREATE ROLE plain;
SET ROLE plain;
CHECKPOINT;
RESET ROLE;
```

```text
CHECKPOINT
CREATE ROLE
SET
ERROR:  permission denied to execute CHECKPOINT command
RESET
```

## See also

[VACUUM](vacuum.md) · [Server options](../../server-options.md)
