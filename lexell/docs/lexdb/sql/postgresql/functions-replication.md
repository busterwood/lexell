# Replication functions

Whether the server is a replica, and the log positions (LSNs) of the master and of a replica.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
pg_is_in_recovery ( ) → boolean
pg_current_wal_lsn ( ) → text
pg_current_wal_insert_lsn ( ) → text
pg_current_wal_flush_lsn ( ) → text
pg_last_wal_replay_lsn ( ) → text
pg_last_wal_receive_lsn ( ) → text
```

## Functions

`pg_is_in_recovery`
: True on a replica, false on the master.

`pg_current_wal_lsn`, `pg_current_wal_insert_lsn`, `pg_current_wal_flush_lsn`
: On the master, the position of its last durable commit. The three give the same value. On a replica they are
  55000 (`recovery is in progress`), as on a PostgreSQL standby.

`pg_last_wal_replay_lsn`, `pg_last_wal_receive_lsn`
: On a replica, the position it has applied; a replica applies what it receives, so the two are the same. On the
  master, NULL.

## Remarks

- An LSN is written as two hex numbers, `0/00000004`, and grows with each commit.
- [`WAIT FOR LSN`](wait-for-lsn.md) on a replica waits until it has applied a position the master gave: a client
  reads `pg_current_wal_lsn()` after its commit on the master and waits for it on the replica, to read its own
  writes. See [replicas](../../replicas.md).

## Differences from PostgreSQL

- The LSNs are `text`: there is no `pg_lsn` type, and `pg_wal_lsn_diff` does not exist. Compare them as text of
  equal length, or by `WAIT FOR LSN`.
- An LSN counts lexdb's commit batches, not bytes of log.
- `pg_last_xact_replay_timestamp`, `pg_stat_replication`, `pg_stat_wal_receiver` and the replication slot functions
  do not exist.

## Examples

These examples run on the master; on a replica, `pg_is_in_recovery()` is true and the replay functions give its
position.

### A. On the master

<!-- example: postgresql -->
```sql
SELECT pg_is_in_recovery() AS replica, pg_last_wal_replay_lsn() AS replayed, pg_last_wal_receive_lsn() AS received,
       pg_current_wal_lsn() = pg_current_wal_insert_lsn() AND pg_current_wal_lsn() = pg_current_wal_flush_lsn() AS same;
```

```text
 replica | replayed | received | same
---------+----------+----------+------
 f       |          |          | t
(1 row)
```

### B. The LSN after a commit

The position grows with each commit.

<!-- example: postgresql -->
```sql
SELECT pg_current_wal_lsn() ~ '^[0-9A-F]+/[0-9A-F]+$' AS form, pg_typeof(pg_current_wal_lsn()) AS type;
CREATE TEMP TABLE before (lsn text);
INSERT INTO before SELECT pg_current_wal_lsn();
CREATE TABLE t (a int);
INSERT INTO t VALUES (1);
SELECT pg_current_wal_lsn() > lsn AS grew FROM before;
```

```text
 form | type
------+------
 t    | text
(1 row)

CREATE TABLE
INSERT 0 1
CREATE TABLE
INSERT 0 1
 grew
------
 t
(1 row)
```

### C. Errors

<!-- example: postgresql -->
```sql
SELECT pg_wal_lsn_diff('0/2', '0/1');
```

```text
ERROR:  function pg_wal_lsn_diff with 2 arguments does not exist
```

## See also

[WAIT FOR LSN](wait-for-lsn.md) · [Replicas](../../replicas.md) · [Session information functions](functions-session.md)
