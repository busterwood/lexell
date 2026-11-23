# WAIT FOR LSN

On a replica, waits until it has applied the master's log up to a position, so that a read after a write sees it.

**Door:** PostgreSQL. **Follows:** PostgreSQL 19.

## Syntax

```
WAIT FOR LSN 'lsn' [ WITH ( option [ value ] [, ...] ) ]

option:
    TIMEOUT duration | NO_THROW
```

## Arguments

*lsn*
: A log position, as `pg_current_wal_lsn()` gives it on the master after a commit (`'0/00000005'`).

`TIMEOUT`
: The longest wait: milliseconds, or a string with a unit (`'1s'`). Without it, the wait has no limit.

`NO_THROW`
: When the time runs out, returns a row saying so instead of an error.

## Remarks

- It returns one row, `status`: `success` when the replica has applied the position, or with `NO_THROW` `timeout`
  or `not in recovery`.
- On the master it is an error (`recovery is not in progress`), or with `NO_THROW` the status `not in recovery`.
- See [Read replicas](../../replicas.md#reading-your-own-writes-wait-for-lsn) for how an application uses it, with
  examples on a replica.

## Differences from PostgreSQL

- PostgreSQL 18 has no `WAIT FOR LSN`; it is PostgreSQL 19's.

## Examples

The examples run on the master; see [Read replicas](../../replicas.md) for the statement on a replica.

### A. On the master

<!-- example: postgresql -->
```sql
SELECT pg_is_in_recovery();
WAIT FOR LSN '0/0';
WAIT FOR LSN 'FFFF/0' WITH (TIMEOUT 100, NO_THROW);
WAIT FOR LSN 'bad';
```

```text
 pg_is_in_recovery
-------------------
 f
(1 row)

ERROR:  recovery is not in progress
HINT:  Waiting for the standby_replay LSN can only be executed during recovery.
     status
-----------------
 not in recovery
(1 row)

ERROR:  invalid input syntax for type pg_lsn: "bad"
```

## See also

[Read replicas](../../replicas.md) · [SHOW](show.md)
