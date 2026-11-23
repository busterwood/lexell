# Advisory lock functions

Locks on numbers that the application chooses, for its own use: one job runner at a time, one writer for a key.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
pg_advisory_lock ( key bigint ) → void
pg_advisory_lock ( key1 integer, key2 integer ) → void
pg_advisory_lock_shared ( key ) → void
pg_try_advisory_lock ( key ) → boolean
pg_try_advisory_lock_shared ( key ) → boolean
pg_advisory_xact_lock ( key ) → void
pg_advisory_xact_lock_shared ( key ) → void
pg_try_advisory_xact_lock ( key ) → boolean
pg_try_advisory_xact_lock_shared ( key ) → boolean
pg_advisory_unlock ( key ) → boolean
pg_advisory_unlock_shared ( key ) → boolean
pg_advisory_unlock_all ( ) → void
```

Each function that takes *key* also takes two `integer` keys, as `pg_advisory_lock` does.

## Functions

`pg_advisory_lock`, `pg_advisory_lock_shared`
: Takes the lock for the session, waiting while another session holds it in a mode that conflicts. An exclusive
  lock conflicts with every other; shared locks do not conflict with each other.

`pg_try_advisory_lock`, `pg_try_advisory_lock_shared`
: The same without waiting: true if the lock was taken, false if another session holds it.

`pg_advisory_xact_lock`, `pg_advisory_xact_lock_shared`, `pg_try_advisory_xact_lock`, `pg_try_advisory_xact_lock_shared`
: The same for the transaction: the lock goes at `COMMIT` or `ROLLBACK`, and cannot be unlocked before.

`pg_advisory_unlock`, `pg_advisory_unlock_shared`
: Gives up one hold of a session lock in that mode: true if there was one, false if not.

`pg_advisory_unlock_all`
: Gives up every lock the session holds.

## Remarks

- A session's locks are its own: it may take the same lock again, and must unlock it as many times as it took it.
- Session locks outlast transactions, and go when the session ends.
- The one-`bigint` keys and the two-`integer` keys are separate: `pg_advisory_lock(1, 2)` and
  `pg_advisory_lock(4294967298)` are different locks.
- A NULL key gives NULL and takes no lock.

## Differences from PostgreSQL

- `pg_locks` does not exist (42P01), so the locks held cannot be listed.
- `pg_advisory_unlock` of a lock the session does not hold returns false without the `WARNING` PostgreSQL gives.
- `pg_typeof` of the `void` results says `text`.

## Examples

### A. Take and give up a session lock

A second hold of the same lock needs a second unlock; a third unlock finds nothing.

<!-- example: postgresql -->
```sql
SELECT pg_advisory_lock(42);
SELECT pg_try_advisory_lock(42) AS again;
SELECT pg_advisory_unlock(42) AS u1, pg_advisory_unlock(42) AS u2, pg_advisory_unlock(42) AS u3;
```

```text
 pg_advisory_lock
------------------

(1 row)

 again
-------
 t
(1 row)

 u1 | u2 | u3
----+----+----
 t  | t  | f
(1 row)
```

### B. Two-integer keys and shared locks

<!-- example: postgresql -->
```sql
SELECT pg_advisory_lock(1, 2), pg_try_advisory_lock_shared(7) AS shared;
SELECT pg_advisory_unlock_shared(7) AS unshared, pg_advisory_unlock(1, 2) AS unlocked;
```

```text
 pg_advisory_lock | shared
------------------+--------
                  | t
(1 row)

 unshared | unlocked
----------+----------
 t        | t
(1 row)
```

### C. Transaction locks

A transaction lock cannot be unlocked by hand; it goes at the end of the transaction.

<!-- example: postgresql -->
```sql
BEGIN;
SELECT pg_advisory_xact_lock(5), pg_try_advisory_xact_lock(6) AS tried, pg_advisory_xact_lock_shared(8),
       pg_try_advisory_xact_lock_shared(9) AS tried_shared;
SELECT pg_advisory_unlock(5) AS unlocked;
COMMIT;
```

```text
BEGIN
 pg_advisory_xact_lock | tried | pg_advisory_xact_lock_shared | tried_shared
-----------------------+-------+------------------------------+--------------
                       | t     |                              | t
(1 row)

 unlocked
----------
 f
(1 row)

COMMIT
```

### D. Giving up everything

<!-- example: postgresql -->
```sql
SELECT pg_advisory_lock(3), pg_advisory_lock(4);
SELECT pg_advisory_unlock_all();
SELECT pg_advisory_unlock(3) AS still_held;
```

```text
 pg_advisory_lock | pg_advisory_lock
------------------+------------------
                  |
(1 row)

 pg_advisory_unlock_all
------------------------

(1 row)

 still_held
------------
 f
(1 row)
```

### E. A NULL key and errors

<!-- example: postgresql -->
```sql
SELECT pg_advisory_lock(NULL) IS NULL AS null_key;
SELECT pg_advisory_lock('a');
SELECT * FROM pg_locks;
```

```text
 null_key
----------
 t
(1 row)

ERROR:  invalid input syntax for type bigint: "a"
ERROR:  relation "pg_locks" does not exist
```

## See also

[SELECT](select.md) (`FOR UPDATE`, `SKIP LOCKED`) · [SET](set.md) (`statement_timeout`) ·
[Session information functions](functions-session.md)
