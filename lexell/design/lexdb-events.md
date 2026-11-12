# LexDB: transactional event streams with a waiting SELECT

Status: design proposal, 2026-11-12, revised the same day after a review
against the code (section 13 lists what the review changed). **The first
version is built: `lexdb.md` 9.98**, as sections 2, 3, 5, 8 and 11
describe. Filters on other columns followed (section 2). Not built yet:
- commit-time sequence numbers;
- the keyed wake-one;
- a wake on replicas.

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
WAITFOR (
    SELECT seq, subject, payload
    FROM events
    WHERE seq > $1
    ORDER BY seq
    LIMIT 100
), TIMEOUT 30000;

-- Process the returned events, then advance the consumer cursor,
-- only from the position this batch was read after (section 6).
UPDATE consumer_offsets
SET last_seen = $2
WHERE consumer_id = $3 AND last_seen = $1;
COMMIT;
```

`TIMEOUT 30000` waits up to 30 seconds. `$1` is the last successfully processed sequence. Return immediately when matching rows exist; otherwise wait, re-evaluate, and return a nonempty batch or an empty result at timeout. Each independent consumer has its own durable offset, stored as ordinary SQL data. No server-side consumer groups or individual acknowledgments are required initially (section 7 shows how groups are built from what LexDB has).

**Spelling: `WAITFOR (SELECT ...), TIMEOUT ms`**, from SQL Server Service Broker's `WAITFOR (RECEIVE ...), TIMEOUT ms`, the closest precedent (section 12):
- The same form serves both front ends. Under TDS a suffix clause would be confusing: T-SQL needs no separator between statements, and `WAITFOR` already begins a statement there (`WAITFOR DELAY`, `WAITFOR TIME`; not done yet, `lexdb-tds.md`).
- The parser turns it into an ordinary S_SELECT with a `waitMs` field. It still reuses the whole SELECT path: Describe, the plan cache and the row description. Only a SELECT may be inside; `RECEIVE`, which consumes rows as it reads them, is not needed, because the offset is ordinary data (section 6).
- `waitfor` is not a keyword in PostgreSQL's grammar or in lexdb's today.
- Without `TIMEOUT`, the wait runs to the cap (section 8). `TIMEOUT $n` is allowed, as LIMIT allows a parameter.

**The parentheses take one query shape, enforced (0A000 otherwise):**
- one ordinary table: not a view, a catalog relation or a temporary table;
- `ORDER BY c` ascending, and a LIMIT (or T-SQL's TOP);
- in WHERE, `c > v` (or `>=`), v a literal or a parameter;
- an index, or the primary key, that begins with columns WHERE gives as
  `k = v` (any or none), then c;
- every other WHERE condition a filter on the row itself: no subqueries,
  and no `nextval`, `set_config` and the like;
- no aggregates, grouping, DISTINCT, windows, subqueries, OFFSET or locking
  clause.

The equality prefix is section 7's partitions: `part = $p AND seq > $1`, on
an index over `(part, seq)`.

**Correctness depends on this shape, not only cost.** Every wake re-runs the
whole query (section 5), but that is not enough:
- **The read's open end.** The waiting SELECT's read is checked at commit
  except past the last key it read (section 3). That gap is sound only for
  rows appended after a cursor. A join would read another table, whose
  open end would be a real gap.
- **"Not empty" must mean "something new arrived".** An aggregate or an
  outer join always gives a row, so it would never wait.
- **The ordering guarantee is about a cursor.** Section 4 only means
  something for `c > cursor ORDER BY c`.
- **Cost:** every waiter's query runs again at every flush, on the one SQL
  thread. For this shape that is one index probe that comes back empty.

**Filters on the event row itself** (`AND subject = 'x'`, `OR`, functions)
are safe: they read nothing but the row. The rows a filter skips are
checked at commit like those returned, so a filter on a column others
change (`status = 'pending'`) fails the commit (40001) if one of them
changes. Their cost is rescanning the rows after the cursor that fail
them, at every wake, since the client cannot advance past rows it never
saw. A filter on the index's leading columns costs nothing: with an index on
`(subject, seq)`, `subject = 'x'` reads only x's rows. Anything that reads
another table stays refused.

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

**The waiting SELECT's read has an open end.** A scan that reaches the end of a tree notes the range from its cursor to the end, at the snapshot's sequence. Any event a producer commits after that snapshot falls in the range. So a caught-up consumer, whose batch is shorter than LIMIT, would fail at COMMIT with 40001 whenever a producer committed in the meantime: under steady production, almost always.

So the waiting SELECT's scans note their reads only up to the last key they read (`Txn.openEnd`). The first version left its reads out entirely; the review showed two workers could then both commit an update of the same row.
- **Checked:** every row it read, returned or skipped, and the gaps between them. An update or delete of one, or an event slipped in between, fails the commit (40001).
- **Not checked:** only rows added after the last key read. This is safe because:
  - the stream is appended to;
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
- LexDB notices a dead client only when its wait ends (section 8), so failover can take up to the wait's cap.

**2. Members in parallel, ordered per key (partitions).**
- Events carry a `part` column, a hash of their key modulo N.
- There is one offset row per (group, part).
- A worker takes parts with `pg_try_advisory_lock` and waits with `WHERE part = $p AND seq > $1`, on an index over `(part, seq)`.
- Acquiring locks is the whole rebalancing scheme: crude, but nothing new.

**3. A work queue: any free worker takes any message, with no ordering.**
- Per-message claims with `SELECT ... FOR UPDATE SKIP LOCKED`, or a claimed/done state column.
- `WAITFOR` is used only when nothing is claimable.
- This is not an ordered stream. It suits jobs, not event processing.

**Later, if measured: a keyed wake-one.**
- Spelling: `WAITFOR (SELECT ...), TIMEOUT 30000, GROUP 'billing'` or similar. Waiters with the same key form a queue, and a flush wakes the first of each queue rather than every waiter.
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
- caps the wait, at 60 s say, and lets the cap bound cleanup;
- waits for the smaller of `TIMEOUT` and the remaining `statement_timeout`, and raises 57014 if the latter ends first;
- documents that client command timeouts must exceed `TIMEOUT`. Npgsql and SqlClient default to 30 s, exactly the example's value.

Real cancellation needs the connection loop to wait on "socket or wake": a separate project, shared with `LISTEN`/`NOTIFY`.

**Refused with 0A000** (besides the shapes of section 2):
- **`WAITFOR` around a locking clause** (FOR UPDATE and the rest), which reads live data rather than a snapshot. It would break section 5's durability argument.
- **`WAITFOR` on a replica.** Nothing flushes locally on a replica; the follower advances in its poll, and writes fail at commit. A wake from the follower's poll can come later, for autocommit consumers only.
- **`WAITFOR` on a temporary table.** It is session-private (`lexdb.md` 9.96), so no other session can ever add to it.

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

Built as `lexdb.md` 9.98 describes. It follows this section's plan, with
`Store.releaseSnapshot` and `Store.renewSnapshot` for the snapshot swap, and
the test `exec_waitfor`.

Start with one stream/table, a constrained indexed SELECT, timeout, generation-based notification and offsets held in SQL tables. Avoid a new messaging protocol, consumer group subsystem or partitioning requirement. Subject filtering came just after version one (section 2): with a filter, the cursor cannot advance past rows that do not match, so each wake rescans them, unless the index leads with the filtered column.

**What it touches:**
- **`lexdb_sql.lxl`:** `WAITFOR (SELECT ...) [, TIMEOUT n]` as a statement, in the PostgreSQL and T-SQL dialects, giving an S_SELECT with a `waitMs` field (beside `lockWait`).
- **`lexdb_store.lxl`:**
  - `waitDurable(afterSeq, ms)`, modelled on `waitChange` and woken in the log writer's post-flush section;
  - an accessor for `Txn.snapSeq`.
- **`lexdb_exec.lxl`, `Session.runIn`:**
  - autocommit: within the existing snapshot-retry loop, take a snapshot and run; if the result is empty, abort, wait and repeat;
  - in a block: the first-statement flag, the snapshot swap and the open-ended reads (section 3);
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

## 12. Precedents

From memory, 2026-11-12; check the details before relying on them. None of these is a waiting SELECT on an ordinary table, but each has a piece of the design.

**Blocking receive inside a transaction: the closest.**
- **SQL Server Service Broker** (since 2005):
  - `WAITFOR (RECEIVE TOP (n) ... FROM queue), TIMEOUT ms` is a blocking read inside a transaction, beside business writes, and a rollback puts the message back. It is where this design's spelling comes from (section 2).
  - Its conversation-group locks give one reader per group: section 7's wake-one.
  - It differs in two ways: queues are special objects, not tables, and a message is consumed once, not re-read from an offset.
- **Oracle Advanced Queuing, now Transactional Event Queues:**
  - `DBMS_AQ.DEQUEUE` takes a wait time and runs in the caller's transaction. Events published in the same commit as business changes are its main selling point.
  - Since 21c it has a Kafka-compatible client API over the same queues: the nearest to "Kafka's semantics, transactional, in the database".

**Streaming SQL statements, with no transaction around consumption:**
- **CockroachDB's core changefeeds** (`EXPERIMENTAL CHANGEFEED FOR t`): a SQL statement that never ends, streaming changes as rows.
- **Materialize's `SUBSCRIBE`** (formerly `TAIL`) and **ksqlDB's** `EMIT CHANGES` push queries: long-running queries that send results as they change.

These push; they do not return a batch and wait. The client keeps its position, and no transaction ties it to processing.

**PostgreSQL:**
- **`LISTEN`/`NOTIFY`:** delivered at commit, but not durable and not replayable. It is section 5's wake hint without the log.
- **Queues with `SKIP LOCKED`,** and extensions such as pgmq: work queues, polled (section 7's third pattern).
- **Logical replication slots:** a durable, ordered change stream with a position kept per consumer, read over the replication protocol rather than by SELECT.

**Sequence numbers that follow commit order (section 4)** are a known trap, with known answers:
- **Kafka**, with transactions: a `read_committed` consumer never reads past the "last stable offset", the first transaction still open. It is section 4's guarantee.
- **FoundationDB:**
  - versionstamps fill a key's sequence in from the commit version: section 4's commit-time alternative;
  - watches are a wake hint that must be rechecked, as in section 5.
- **SQL Server's `rowversion`** is assigned at write time and has exactly the gap problem. `MIN_ACTIVE_ROWVERSION()` exists so readers can stop below writes not yet committed.
- **PostgreSQL outbox and event-store libraries** filter by transaction ids and snapshots, or serialize their writers (Message DB with an advisory lock).

**Not SQL, the same shape:**
- **Redis Streams' `XREADGROUP ... BLOCK`:** a blocking read, with consumer groups and a pending-entries list per group.
- **NATS JetStream's pull consumers:** the blocking receive section 1 names.

**What is new here is the combination:**
- the stream is an ordinary table;
- the subscription is an ordinary indexed SELECT that can wait, not a queue object or a protocol;
- the consumer's offset is ordinary data, committed in the same serializable transaction as the processing.

Service Broker and Oracle AQ have the transaction but special queues. Changefeeds, `SUBSCRIBE` and replication slots re-read the log, outside any transaction.

## 13. Review, 2026-11-12

The proposal was reviewed against the code the day it was written. What changed:
- **Section 3:** BEGIN takes its snapshot at once today, so the waiting SELECT swaps it. It also needs a first-statement flag, and reads quietly so that a caught-up consumer does not fail with 40001.
- **Section 4:** the counter row queues producers, one per flush; they do not retry.
- **Section 5:** the generation is `durableSeq`, woken after the flush, with an atomic check-and-register.
- **Section 6:** the offset update must be a compare-and-set. Otherwise two competing workers can both commit.
- **Sections 7 to 9 and 12 are new:** consumer groups, the first version's limits and refusals, `LISTEN`/`NOTIFY`, and the precedents.
- **The open questions are settled:**
  - `WAITFOR (SELECT ...), TIMEOUT ms`, after Service Broker (changed from `SELECT ... WAIT ms` once the precedents were listed);
  - a counter row first;
  - an ordinary table;
  - a timeout as zero rows, and retention as a `floor` column;
  - no subject filter in version one.

**Still open:**
- the counter row's throughput, to be measured;
- whether a keyed wake-one is ever needed.

**Later the same day:**
- the query shape was made an enforced rule, and section 2 corrected: the
  shape matters for correctness, not only cost;
- the first version was built (`lexdb.md` 9.98);
- then filters on other columns;
- then a second review, of the code. It found:
  - the unnoted reads let two workers commit the same row's update: the reads are now noted, with an open end;
  - a block could go on without a snapshot after an error during the wait;
  - the client's parameter types were dropped;
  - timed-out waiters gathered on an idle store;
  - smaller points: column alias lists, `seq > -1`, the shape checked once, and no 72000 retry.

  All of these are fixed (`lexdb.md` 9.98).

**The event log is the table; the waiting SELECT is the subscription API.**
