# LexDB: transactional event streams with a waiting SELECT

Status: design proposal, 2026-11-12. Not implemented. Revised the same day
after a review against the code (section 12 lists what the review
changed). Syntax and sequence allocation are provisional.

## 1. Idea

An event stream is an ordinary append-only SQL table. Consumers retrieve rows after a sequence number using an indexed SELECT. If no qualifying committed rows exist, the SELECT parks the connection's coroutine until a new commit or a timeout. There is no separate message broker or storage engine.

Producers can update business data and publish events in one LexDB transaction. Consumers can process an event and store their progress in another transaction. The application event table is distinct from LexDB's internal, checkpoint-recycled recovery log (see `lexell/design/lexdb.md`, sections 4.4 and 4.6).

This borrows durable log/replay from Kafka and blocking receive from NATS/JetStream, but makes the transaction boundary the primary abstraction.

## 2. Proposed SQL

```sql
CREATE TABLE events (
    seq bigint PRIMARY KEY,
    subject text NOT NULL,
    payload bytea NOT NULL
);

BEGIN;
SELECT seq, subject, payload
FROM events
WHERE seq > $1
ORDER BY seq
LIMIT 100
WAIT 30000;

-- Process the returned events, then advance the consumer cursor,
-- only from the position this batch was read after (section 6).
UPDATE consumer_offsets
SET last_seen = $2
WHERE consumer_id = $3 AND last_seen = $1;
COMMIT;
```

`WAIT 30000` waits up to 30 seconds. `$1` is the last successfully processed sequence. Return immediately when matching rows exist; otherwise wait, re-evaluate, and return a nonempty batch or an empty result at timeout. Each independent consumer has its own durable offset, stored as ordinary SQL data. No server-side consumer groups or individual acknowledgments are required initially (section 7 shows how groups are built from what LexDB has).

**Spelling: `SELECT ... WAIT ms`, not `RECEIVE`.**
- It reuses the whole S_SELECT path: Describe, the plan cache and the row description.
- `wait` is not a keyword today; only `nowait` is.
- `RECEIVE` would be a new statement kind duplicating all that. T-SQL's `WAITFOR (RECEIVE ...), TIMEOUT` can map onto `WAIT` later, for the TDS front end (`lexdb-tds.md`).
- `WAIT $n` is allowed, as LIMIT allows a parameter.

Initially support only an easily recognisable indexed query: one table, `seq > parameter`, `ORDER BY seq ASC`, bounded `LIMIT`. Arbitrary predicates, joins and general waiting SELECTs create a much larger query-dependency problem and are not needed to test the design. Correctness does not depend on the shape: every wake re-runs the whole query (section 5). The restriction keeps the re-run cheap. Section 7's partitioned groups widen it to an equality prefix, `part = $p AND seq > $1`, on an index over `(part, seq)`.

The table is an ordinary one, not a marked event table. A marked table becomes worthwhile with commit-time sequence numbers and an enforced append-only rule (section 4).

## 3. Transaction and snapshot semantics

**The waiting SELECT must be the first SQL statement after BEGIN.** No preceding statement may have established a snapshot, performed writes or accumulated a serializable read set. It is also possible to use waiting SELECT in autocommit mode, but then processing and offset updates cannot be part of that same transaction.

The operation *defers transaction activation* rather than restarting a transaction that has already returned data:

1. `BEGIN` establishes transaction/session context. **Today BEGIN takes its snapshot at once**, for both `BEGIN READ ONLY` (`Store.beginSnapshot`) and read-write blocks (`Store.beginBlock`); only replicas take theirs at the first read. So a waiting SELECT that is the first statement ends the BEGIN snapshot and takes a fresh one for each attempt.
2. An indexed SELECT probes the committed database in a candidate view. If rows exist, it completes as the transaction's first read.
3. If empty, release the provisional view and park, without pinning old versions. A snapshot held while parked would pin old versions and could be cancelled with 72000.
4. When notified, establish a fresh candidate view and re-evaluate the query. Once qualifying rows exist, the query returns and establishes the transaction's first read.
5. Subsequent SQL follows **existing LexDB isolation semantics**. Read-only transactions keep a snapshot; read-write transactions are serializable through recorded page versions and commit validation. Do not claim that existing read-write transactions use a single immutable MVCC snapshot.
6. Timeout performs one last current evaluation, returning zero rows if still empty and establishing the transaction's first read. Cancellation or connection loss must clean up the waiter and abort the operation (but see section 8 for what the first version can do).

A preceding SQL query must never be silently discarded or have its transactional view replaced. "First statement" needs a new session flag, set by BEGIN and cleared by any statement:
- read counts cannot tell, because a `READ ONLY` block's reads are not noted;
- under TDS every statement in a transaction runs under a savepoint (`lexdb-tds.md`), so "no savepoint yet" is not the test either.

**The waiting SELECT's reads are not noted.** A scan that reaches the end of a tree notes the range from its cursor to the end, at the snapshot's sequence. Any event a producer commits after that snapshot falls in the range. So a caught-up consumer, whose batch is shorter than LIMIT, would fail at COMMIT with 40001 whenever a producer committed in the meantime: under steady production, almost always. The waiting SELECT therefore reads quietly, as FOR UPDATE already does (`Txn.quiet`, `lexdb.md` 9.86). This is safe because:
- the stream is append-only;
- section 4 guarantees that later events never become visible before earlier ones;
- the offset row is still read and validated, so section 6's guarantee holds.

## 4. Event sequence numbers must follow commit visibility

A sequence allocated at INSERT time is unsafe:

- Transaction A allocates `124` and has not committed.
- Transaction B allocates `125` and commits.
- Consumer reads `125`, advancing its offset.
- A commits `124`, which the consumer can now never see.

The guarantee required is **a sequence greater than an observed cursor never becomes visible before an event with a lower sequence that will commit later**. Gaps are permissible; out-of-order visibility is not.

LexDB's `nextval` is non-transactional, as PostgreSQL's is (`lexdb.md` 9.43), so ordinary sequences and identity columns allocated before commit do not solve the problem.

The first implementation uses a single counter row updated within the same transaction as event insertion:

```sql
BEGIN;
UPDATE event_sequences
SET next_seq = next_seq + 1
WHERE stream = 'orders'
RETURNING next_seq;
INSERT INTO events (seq, subject, payload)
VALUES ($allocated_seq, 'orders.shipped', $payload);
COMMIT;
```

This is correct: the row lock and commit validation force counter order to equal commit order, and visibility is a prefix of commit order.

**Producers on one stream queue; they do not retry.** In a block the UPDATE takes the counter row's lock, and `commit` releases its locks only after the durable flush. A second producer waits on the lock rather than failing. So producers on one stream get no group commit: roughly one producer transaction per fsync. Advise:
- several events per transaction;
- one counter row per stream, never one shared by all streams.

Measure before relying on it (a benchmark needs the user's approval first).

The later alternative assigns sequence numbers during LexDB's serialized, non-parking commit stage, after validation: `db.seq` is already assigned there under the commit's critical section (`Store.commitLive`). The cost is a design for deferred primary keys, secondary indexes on the deferred value, and RETURNING.

A consumer's response must obey LexDB's durability promise: it cannot expose a newly committed event before the flush covering that event (see `lexdb.md` 4.4). Section 5's wake gives this for free.

## 5. Park and wake without missed events

LexDB already uses a single SQL thread, coroutines and asynchronous disk reads. Notification is a hint, not a delivery: the SELECT always rechecks its predicate.

**The generation is `db.durableSeq`.**
- Snapshots read as of `db.durableSeq`, the last commit the log holds (`lexdb.md` 9.16; `Txn.snapSeq`), not as of the last commit applied.
- The log writer advances `durableSeq` only after the flush, and in the same post-flush section it drains `Db.changeWake`.
- Waiters are woken there. A waiter woken when a commit is applied, before its flush, would take a snapshot at the old `durableSeq`, see nothing and park again with its wakeup spent: the event would be missed until the next commit or the timeout.
- Woken there, a waiter's fresh snapshot can only show flushed events, which is the durability promise of section 4.

**The race.** The generation check is still needed on one thread. The scan itself parks, on cache misses and on time slices, and the snapshot lags apply anyway. **Do not implement `query empty; then sleep` directly.** The protocol:

1. Take a snapshot; its sequence is `g` (`Txn.snapSeq`).
2. Run the indexed read in that snapshot.
3. If the result is empty, end the snapshot, then in one `Shared.with`: if `db.durableSeq > g`, rescan at once; otherwise append a promise to the wake list.
4. Wait on the promise for at most the remaining time (`Future.waitFor`).

`Shared.with` cannot park, so step 3's check and registration are atomic, and a promise completed before its wait is kept. `Store.lockAs` uses exactly this pattern. `Store.waitChange` is nearly the primitive: it lacks the comparison with `g` and a timeout. The store gains `waitDurable(afterSeq, ms)`, written generally enough for `LISTEN`/`NOTIFY` to reuse (section 9).

Spurious wakeups are acceptable.
- **Timeouts:** a waiter that times out leaves its promise in the list; the next flush drains and completes it. Check that completing a promise whose future is gone is harmless in the runtime.
- **Cost:** every waiter wakes on every flush and pays one index probe per group commit. That is fine for tens of waiters on a stream. A per-tree "last written sequence" map, set in `commitLive`, can filter wakes later. So can section 7's keyed wake-one.

## 6. Processing and acknowledgments

A single logical consumer reads after its last durable offset, applies business changes, updates its offset **in the same transaction**, then commits. On `40001` serialization failure it retries. On rollback, its offset remains unchanged. This is atomic database-side processing, but it cannot guarantee exactly-once execution of external HTTP requests, email or payments; those need idempotency or an outbox.

**The offset update is a compare-and-set.** `$1` comes from outside the transaction, since the first-statement rule forbids reading the offset first. With a plain `UPDATE ... WHERE consumer_id = $3`, two workers sharing an offset can both commit:
- the second waits on the first's row lock;
- it then re-runs its statement with the first try's reads forgotten (`lexdb.md` 9.86);
- so it commits the same transition with no conflict.

So the update is `... WHERE consumer_id = $3 AND last_seen = $1`, and a client that updates 0 rows rolls back: another worker has already taken the batch. An empty batch (a timeout) skips the update.

Independent subscribers maintain independent offsets and do not compete. The offset table's key is what defines a consumer: per user, per service, per group, as fine-grained as the application likes.

## 7. Consumer groups

Kafka's consumer groups are partition ownership, not per-message delivery. Each partition has one owner in its group, so a group runs as many members in parallel as there are partitions, and order holds within a partition. A group sharing one offset row can advance one batch at a time anyway, so its useful form is one active member with standbys.

All three patterns below use what LexDB has today: session advisory locks (`lexdb.md` 9.86) and `SKIP LOCKED`.

**1. One active member with standbys.**
- Each member takes `pg_advisory_lock(<group's key>)` before its waiting SELECT.
- Standbys park on the lock, so only the holder waits for events: only one connection of the group is woken.
- A session's advisory locks go when it closes, so a standby takes over when the active member disconnects.
- LexDB notices a dead client only when its wait ends (section 8), so failover can take up to the WAIT cap.

**2. Members in parallel, ordered per key (partitions).**
- Events carry a `part` column, a hash of their key modulo N.
- There is one offset row per (group, part).
- A worker takes parts with `pg_try_advisory_lock` and waits with `WHERE part = $p AND seq > $1`, on an index over `(part, seq)`.
- Acquiring locks is the whole rebalancing scheme: crude, but nothing new.

**3. A work queue: any free worker takes any message, with no ordering.**
- Per-message claims with `SELECT ... FOR UPDATE SKIP LOCKED`, or a claimed/done state column.
- WAIT is used only when nothing is claimable.
- This is not an ordered stream. It suits jobs, not event processing.

**Later, if measured: a keyed wake-one.**
- Spelling: `WAIT 30000 GROUP 'billing'` or similar. Waiters with the same key form a queue, and a flush wakes the first of each queue rather than every waiter.
- A wake is still only a hint. Waking just one waiter needs a **pass-on rule**, or work stalls. The woken waiter wakes the next in its queue when it:
  - returns a full batch (LIMIT reached: there may be more);
  - finds nothing;
  - fails;
  - times out;
  - or its session ends before it commits.
- Without that rule, a dead or slow member strands its group's events until the next commit, and a backlog larger than one batch waits behind one member.
- Build it only if a benchmark shows wake-all's probes hurting; patterns 1 to 3 do not need it.

## 8. Limits of the first version

**Cancel, disconnect and timeouts.**
- PostgreSQL's CancelRequest is ignored today.
- TDS ATTENTION is acknowledged only after the request answers.
- While a statement runs, the connection task is inside it and not reading its socket. A dead client is noticed only when the wait ends.
- `statement_timeout` is checked only in `Run.tick`, and does not end lock waits today (9.86, "Not done").

So the first version:
- caps WAIT, at 60 s say, and lets the cap bound cleanup;
- waits for the smaller of WAIT and the remaining `statement_timeout`, and raises 57014 if the latter ends first;
- documents that client command timeouts must exceed WAIT. Npgsql and SqlClient default to 30 s, exactly the example's value.

Real cancellation needs the connection loop to wait on "socket or wake": a separate project, shared with `LISTEN`/`NOTIFY`.

**Refused with 0A000:**
- **WAIT with a locking clause** (FOR UPDATE and the rest), which reads live data rather than a snapshot. It would break section 5's durability argument.
- **WAIT on a replica.** Nothing flushes locally on a replica; the follower advances in its poll, and writes fail at commit. A wake from the follower's poll can come later, for autocommit consumers only.
- **WAIT on a temporary table.** It is session-private (`lexdb.md` 9.96), so no other session can ever add to it.

**The rest:**
- **Describe** only plans, so it never waits.
- **Pipelined messages** simply queue behind the wait.
- **Connections:** each waiter holds a connection for its whole wait, and under a transaction-mode pooler, a server connection. Pools must be sized for it.

## 9. LISTEN and NOTIFY

`LISTEN`/`NOTIFY` is still missing (`lexdb-gaps.md`). This design does not subsume it:
- NOTIFY pushes to an idle connection, which the synchronous connection loop cannot do. That is the same limit as cancellation (section 8).
- `waitDurable` is written generally, so that NOTIFY can reuse it when the connection loop changes.

## 10. Retention

The events are normal rows. A first version can delete old rows. Later, time- or sequence-range partitioning could make expiry efficient through dropping whole partitions; partitioning is not required to get the blocking SELECT working.

Keep track of the oldest retained event/offset boundary, in SQL:
- the deleting transaction updates a `floor` column on the stream's row in `event_sequences`;
- the consumer reads it after the waiting SELECT. That read is noted, so it is validated at commit;
- a consumer whose offset is below the floor has missed expired events. It must treat that as an error, not assume all events were consumed.

Legitimate gaps in allocated sequence values are different from retention gaps.

A timeout on the wire is simply zero rows and `SELECT 0`; it needs no new message.

## 11. First implementation and tests

Start with one stream/table, a constrained indexed SELECT, timeout, generation-based notification and offsets held in SQL tables. Avoid a new messaging protocol, consumer group subsystem or partitioning requirement. No subject filtering in version one: with a filter, the cursor cannot advance past rows that do not match, so each wake rescans them.

**What it touches:**
- **`lexdb_sql.lxl`:** a `waitMs` field beside `lockWait`, parsed after LIMIT and the locking clause.
- **`lexdb_store.lxl`:**
  - `waitDurable(afterSeq, ms)`, modelled on `waitChange` and woken in the log writer's post-flush section;
  - an accessor for `Txn.snapSeq`.
- **`lexdb_exec.lxl`, `Session.runIn`:**
  - autocommit: within the existing snapshot-retry loop, take a snapshot and run; if the result is empty, abort, wait and repeat;
  - in a block: the first-statement flag, the snapshot swap and the quiet reads (section 3);
  - the refusals of section 8.
- **The wire and TDS front ends:** nothing.

**The hard parts:**
- swapping the snapshot in a block while keeping the session's state (`setUp`, `adopt`);
- stale promises after timeouts;
- one producer per flush on a stream (section 4).

**Tests,** in the style of `exec_locks` (sessions in tasks of their own), should verify:
- **delivery:** immediately available rows; ordered limited batches; no wake before commit, and none before the flush; rollback not delivered; a correct wake when a commit occurs during an I/O-parked index scan;
- **consumers:** multiple independent consumers; the compare-and-set between competing workers; a caught-up consumer committing while producers commit (no 40001);
- **cleanup and limits:** timeout and disconnect cleanup; `statement_timeout`; the refusals;
- **transactions:** delayed read-only snapshots; serializable read-write retries;
- **ordering and durability:** concurrent writers never exposing out-of-order event sequences; recovery/durability;
- **retention:** explicit retention-expired behaviour.

## 12. Review, 2026-11-12

The proposal was reviewed against the code the day it was written. What changed:
- **Section 3:** BEGIN takes its snapshot at once today, so the waiting SELECT swaps it. It also needs a first-statement flag, and reads quietly so that a caught-up consumer does not fail with 40001.
- **Section 4:** the counter row queues producers, one per flush; they do not retry.
- **Section 5:** the generation is `durableSeq`, woken after the flush, with an atomic check-and-register.
- **Section 6:** the offset update must be a compare-and-set. Otherwise two competing workers can both commit.
- **Sections 7 to 9 are new:** consumer groups, the first version's limits and refusals, and `LISTEN`/`NOTIFY`.
- **The open questions are settled:**
  - `SELECT ... WAIT ms`;
  - a counter row first;
  - an ordinary table;
  - a timeout as zero rows, and retention as a `floor` column;
  - no subject filter in version one.

**Still open:**
- the counter row's throughput, to be measured;
- whether a keyed wake-one is ever needed.

**The event log is the table; the waiting SELECT is the subscription API.**
