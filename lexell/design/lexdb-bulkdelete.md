# lexdb: bulk deletes without partitioning (a design, 2026-11-14)

The two steps of [lexdb-gaps.md](lexdb-gaps.md) 2.5. Nothing here is built.
Line numbers are as of 2026-11-14. Statements marked [read] come from
reading the code and were not run; [estimate] means not measured.

## 0. In short

1. **Range delete as a subtree drop: build it.** A new write op,
   `OP_DELRANGE (tree, lo, hi)`, goes into the transaction's write set and
   the log as one record. At commit it detaches every subtree that lies
   wholly inside `[lo, hi)` and frees it the way `applyDrop` frees a
   dropped table (9.32). Rows are deleted one by one only in the two edge
   leaves. The executor uses it only for a DELETE whose WHERE is exactly a
   range on a primary-key prefix, on a table with no secondary indexes and
   no foreign keys pointing at it, with no RETURNING, TOP or LIMIT.
   Anything else takes today's path. The row count stays exact: it comes
   from the leaf page headers, read raw and not put in the cache.
2. **Bounded memory: a batched form, not spilling.** `DELETE ... WITH
   (batch_rows n)` and the same for UPDATE, as COPY's (9.87): each batch
   is committed, and the statement as a whole is not all or nothing. Spilling
   would need a multi-frame log commit, a commit that loads in parts, and
   own-write reads merged from disk. The user already chose batches over
   spilling for COPY.
3. Step 1 removes most of the need for step 2 in the purge case: a range
   delete holds one write, whatever its size. Step 2 is still needed for
   purges by a column that is not the key, for tables with indexes until
   stage 6, and for large UPDATEs. It can come after step 1.

## 1. What a DELETE does today

- **Statement** (`lexdb_exec.delete`, exec:14468):
  1. It runs the query and keeps a copy of every row found: `found`, plus
     `2 * rowBytes` counted against `max_statement_mem` (exec:14490).
  2. It locks them (`lockFound`, exec:16529).
  3. Then `delRow` per row (exec:20097) calls `txn.del` on the table key
     and on each index entry, and queues FK work (`parentSide`), which
     `fkFinish` runs at the statement's end.
  4. The default `MAX_STATEMENT_MEM` is 256 MB (exec:18723), so one DELETE
     of more than roughly a million narrow rows fails with 53200 rather
     than running out of memory [estimate from `rowBytes`: 32 + 24 per
     column, times 2].
- **Write set** (`Txn`, store:254):
  - `writes: []TxWrite`, a per-tree map from key to its last write
    (`idx`), and sorted copies of those keys (`sortedKeys`). All of it is
    in memory: about 176 B a row (9.84).
- **Commit** (`commitLive`, store:2933):
  1. It sorts the writes per tree and key (`commitOrder`, store:2871).
     Creates and drops stay where they are and act as barriers.
  2. It loads every leaf the writes touch: `writeNeeds` (store:1589), then
     `loadMany` repeatedly until nothing is missing. A commit cannot load
     while it applies, so for a large DELETE every touched leaf is in
     memory at once, and dirty until a checkpoint.
  3. It checks the reads against `wlog` (`validate`, store:2731).
  4. It applies the writes inside one `st.sh.with`. That blocks every
     session for the whole apply (lexdb runs SQL on one thread, 9.15).
  5. It appends one log record per write (`addRecord`, store:1796) to the
     batch.
  6. `logWrites` (store:2766) keeps the writes for later checks: one
     inclusive key range per tree when a tree has more than `WLOG_RANGE`
     writes.
- **Snapshots:**
  - Before a node changes, `willChange` (store:620) copies it into
    `hist[s]`.
  - A slot freed while a snapshot may still reach it is kept on
    `deferred` (`freeSubtree`, store:537) until `prune` (store:635)
    releases it.
  - A row-by-row purge copies every leaf it changes into `hist`. With a
    long report running, that can push `histCount` over `snapNodes` and
    cancel the report (72000, `overBudget`, store:3036).
- **Drop** (`applyDrop`, store:1543):
  - Every loaded node goes through `freeSubtree`. A slot that is not
    loaded goes to `Db.dropped` as `(page, height)` (`releaseSlot`,
    store:546).
  - Each checkpoint's `walkDropped` (store:3711) reads up to
    `DROP_READS` internal pages of those subtrees and frees their leaves
    without reading them.
  - At every point a page is in exactly one of: a tree, `dropped`,
    `freeAfterNext`/`pendingFree`/`free`.
- **Replicas:**
  - The follower keeps a per-tree `Delta` of key versions over a base
    checkpoint (store:5215).
  - `Fol.apply` (store:5431) handles PUT, DEL, CREATE and DROP.
  - It reads base pages on demand, and `prune` (store:5556) drops
    versions once a newer base covers them.
- **No triggers, no row security, no generated columns** exist
  (lexdb-gaps 2.3). TRUNCATE is already a drop plus a new tree (exec:11810).

## 2. Step 1: the range delete

### 2.1 When the executor uses it

`rangeDelete(st, txn, s, &q, params)` is called in `delete()` after
`buildQuery` and before the `runQuery` loop. When it returns `None`, the
statement goes on as today. It takes the fast path only when all of these
hold:

| Condition | Why |
|---|---|
| One target table, no USING/FROM, not a view | one tree |
| No RETURNING/OUTPUT, no `s.limit` (T-SQL TOP), no ROWNUM | these need the rows |
| `t.indexes` empty (stage 6 relaxes this) | index order differs (2.4) |
| `t.refBy` empty (stage 7 relaxes this) | FK actions need the rows |
| Every WHERE conjunct is `pkcol op c` on a leading PK prefix: `=` on the first k columns, at most one `<`, `<=`, `>`, `>=` or BETWEEN on column k+1 (or no WHERE at all) | then the range is the whole predicate |
| Each `c` is fixed for the statement: a literal, a parameter, a stable function such as `now()`, or an uncorrelated scalar subquery | evaluated once |
| PK columns of exact kinds: integers, numeric, date, time, timestamp(tz), uuid, text under the exact collation | `floatKey`'s NaN and -0, and CI/PAD keys, are not range-exact |
| The bound coerces exactly: `coerce(c, coltype)` cast back equals `c` | `id < 10.5` on an int is rounded (exec:8270 says why the scan's bounds are inclusive) |
| No other transaction holds a row lock on a key of `t.tree` in range | today's path waits for it properly |
| Not inside a transaction block (stage 5 relaxes this) | own-view reads (2.3) |
| `SET lexdb_range_delete` is on (the default) | a switch for tests and for diagnosis |

The detector works from the WHERE itself, not from `Path`: `pathScan`'s
bounds are deliberately supersets (exec:8244), and the WHERE is checked
again on every row.

**Exact bounds.** Let `p` be the encoded equality prefix and `e` the
encoded bound (`encKeyPart`).

| WHERE | Bound |
|---|---|
| `>= v` | `lo = p‖e` |
| `> v` | `lo = succ(p‖e)` |
| `< v` | `hi = p‖e` |
| `<= v` | `hi = succ(p‖e)` |
| no range column | `lo = p`, `hi = succ(p)` (`""` when `p` is `""`) |
| no WHERE | `["", "")` (the whole table, with a count) |

`succ` is exec:3109. The key encoding is prefix-free per column (fixed
widths, and `encBytesKey`'s `00 00` end), so `succ` excludes exactly the
keys that start with `p‖e`. A NULL bound gives `DELETE 0`.

**What it does then:**
1. `st.noteRange(txn, tree, lo, hi)`: a read mark at the live `db.seq`,
   noted before counting.
2. `n = st.countRange(txn, tree, lo, hi)` (2.2).
3. `txn.delRange(tree, lo, hi)`.
4. `noteChg` with n deletes, for automatic statistics (exec:4841).
5. Tag `DELETE n`.

On a conflict, the session's retry loop (exec:19555) runs the statement
again, as it does today.

### 2.2 The row count

`DELETE n` must be exact: drivers report it (JDBC's `executeUpdate`,
psycopg's `rowcount`). Internal pages hold no counts (lexdb_page `Node`),
so `countRange` works like this:
- It counts edge leaves and loaded leaves from memory (`Node.count()`).
- For each unloaded covered subtree, it reads the pages raw, as
  `walkDropped` does, on the helper pool, in runs of consecutive pages. An
  internal page gives its children's page numbers. A leaf page gives its
  `n` at bytes [16..18), the same in T_LEAF, T_FLEAF and T_CLEAF. Nothing
  is decoded or installed, so a large purge does not flush the cache.
- **Staleness.** Before trusting a subtree's count, it checks again that
  the slot it came from has the same `gen`, `disk` and `loaded == false`.
  Any change below that slot would have loaded and dirtied it (`markDirty`
  sets `disk = -1`). If the slot changed, the count starts again; after 3
  restarts the statement falls back to the row path.
- **Concurrent writes.** A write by another commit into the range during
  the count fails this transaction's validation, so the statement runs
  again. The count and the commit always describe the same rows.

**What the count costs** [estimate]:
- Warm, close to nothing.
- Cold, one read of every covered leaf page. That is still I/O, but no
  decoding, no write per row, no log per row and no commit work per row.
- An exact count without reading leaves needs subtree counts in internal
  pages: a new internal page type, kept up on every `applyPut`/`applyDel`
  (which already dirty the whole path) and through splits. That is
  decision D1.

### 2.3 The store

**The write.** `Txn.delRange(tree, lo, hi)` appends
`TxWrite{op: OP_DELRANGE (6), tree, key: lo, val: hi, head: 0}`, where
`hi == ""` means to the end.
- Earlier writes of this transaction to keys in `[lo, hi)` of that tree
  are found through `sortedKeys`. An `OP_DEL` is added first for each of
  them, so the transaction's own view stays right for those keys without
  any new rule (stage 5 needs this).
- `undoTo` (savepoints) needs nothing new: the op is an ordinary write.

**The log record.** Same layout as every record (`addRecord`): op byte,
tree, key = lo, val = hi.
- `parseRecords` accepts op 6.
- `frameLen` and `reserveBatch` already count key and value.
- **Also in stage 1:** `parseRecords` rejects any unknown op as corrupt.
  Today an unknown op parses, and `applyWrite` and `Fol.apply` skip it
  without a word. An older binary would do that to a range delete and
  bring the deleted rows back [read]. Once the check is in, a newer op
  stops an older binary loudly. As with T_FLEAF and T_CLEAF, going back to
  an older binary is not supported.

**Conflicts.**
- `logWrites` adds `WEntry{seq, tree, key: lo, hi, open: true}`, a new
  flag meaning the range is half-open with `""` as the end.
- `validate` gets one more case: a mark `[m.lo, m.hi)` conflicts with it
  when `(hi == "" || hi > m.lo) && (m.hi == "" || lo < m.hi)`.
- Other transactions that read any key of the range and commit after this
  one fail (40001), as they would against a row-by-row DELETE. One that
  inserted into the range and committed first makes this one fail, and the
  statement runs again and deletes that row too.
- The existing check that each written tree still exists covers a
  concurrent DROP.

**commitOrder** treats the op as a barrier, since it is neither PUT nor
DEL. Writes before it and after it keep their order relative to it.

**writeNeeds** returns the first missing slot on the path to `lo`
(`descend(tree, lo)`), then on the path to `hi` (`descend(tree, hi)`, or
the last leaf, `descendBack(tree, "")`, when `hi == ""`), then the
companion paths (below). Nothing inside the range is loaded.

**applyDelRange(tree, lo, hi).** Let L and H be the two paths, both
loaded, and A their lowest common node.
1. If L and H end in the same leaf, delete its keys in `[lo, hi)` and
   stop.
2. In A, remove the children strictly between L's child and H's child,
   with their separators.
3. In every node of L below A, remove the children to the right of the
   path child. In every node of H below A, remove the children to its
   left. Remove their separators too.
4. Each removed child's range goes to a neighbour whose edge chain is L or
   H, which is loaded. A later write of the same commit therefore never
   descends into a node that is not loaded: the condition `applyDel`'s
   `edgeLoaded` guards.
5. Free each removed child with the body of `applyDrop`'s loop, made into
   `dropSubtree(s, h)`. The tree is balanced, so a child removed from the
   node at depth d of a path has height `len(path) - 2 - d`. Loaded nodes go through `freeSubtree`; unloaded ones go to
   `dropped` or `deferred`.
6. Delete the edge leaves' keys in `[lo, hi)` as one slice removal each
   (`loosen`, then recompute `size`), not with `applyDel` per key. An edge
   leaf left empty stays, as `applyDel` already allows.
7. Collapse a root left with one loaded child, as `applyDel` does.
8. On every changed node: `willChange` first; then `markDirty`, `version
   += 1`, `packed = false`, `recost`; and `db.shape += 1` (the `lastLeaf`
   finger).

The commit then:
- costs O(height × fanout) node operations, plus the two edge leaves;
- adds a few nodes to `hist` and none per row;
- holds `st.sh.with` for microseconds rather than for the rows' whole
  apply [estimate].

**Snapshots.** A snapshot from before the commit reads the old versions
of the changed internal nodes from `hist`. They name the removed child
slots, which `freeSubtree` keeps (pinned, on `deferred`) until `prune`
finds no snapshot that needs them. Their pages stay valid until then. This
is the mechanism `applyDrop` already relies on. See P1 in section 7 for a
case to check first.

**Large values.** The companion tree `tree + OVF` keeps a key's chunks
under `u16(len key)‖key‖u32(i)` (`chunkKey`, store:1658), so for keys of
one length L those chunks are contiguous.
- When the companion exists, the apply finds the lengths present by
  skipping: descend to `u16(L)`, read the first key's length, go on from
  `u16(L+1)`.
- For each length it runs the same `applyDelRange` on the companion over
  `[cb(L, lo), cb(L, hi))`, where `cb` maps a main-tree bound to a
  chunk-key bound. When `len(b) ≤ L`, `cb = u16(L)‖b`. When `len(b) > L`,
  `cb = u16(L)‖b[0..L]` followed by the point after every chunk of that
  key.
- `writeNeeds` loads those edge paths too, one pass per level, as today.
- Typical keys have one length (integers, timestamps, uuids), so this is
  one more range [estimate].

**Recovery** replays the record through `applyRecovered` (store:4719),
i.e. the same `writeNeeds`/`applyDelRange`.
- The op is logical: it means "no key of `[lo, hi)` is left", whatever
  the tree's shape. So replay gives the same rows as the master, though
  maybe a different shape, which `commitOrder` already permits.
- Replaying it over a checkpoint that already holds later batches is
  safe, because those later batches are replayed after it, in order.
- **On a crash:**
  - Before the checkpoint that writes the changed parents, the old tree
    on disk still holds the subtrees, and the log redoes the delete.
  - After it, the subtrees are in `Meta.dropped` or already free.
  - The invariant of 9.32 holds unchanged, and `audit` checks it.

**Checkpoint and free lists.** Nothing new:
- Freed pages of loaded nodes go to `freeAfterNext`, then `pendingFree`,
  then `free` (runs, 9.33).
- Unloaded subtrees go to `dropped`, which `walkDropped` frees over the
  following checkpoints at `DROP_READS` pages each. A 5 GB purge has
  about 5,000 internal pages: about 20 checkpoints (9.32's "not done":
  reads several at once would shorten that).
- Followers' holds keep freed pages from reuse (`heldFree`), as for a
  drop.

**Column leaves.** Their least and greatest values (9.112, 9.113) live
inside the leaf, so they leave with it. An edge leaf that changes is
written again by the checkpoint as any dirty leaf is. A queued upgrade
(`upgKey`) descends by key, so a leaf that was detached is not touched.

### 2.4 The rest of the interactions

- **Row locks:**
  - Outside a block, today's path only waits for other holders and keeps
    nothing (`lockFound`). The fast path falls back when another
    transaction holds a lock in the range, which is a scan of `db.locks`
    for `tree:`; it is usually tiny.
  - In a block (stage 5), a concurrent `SELECT ... FOR UPDATE` and UPDATE
    of a row in the range either commits first, and the range delete
    fails 40001 and runs again, or commits second and fails itself.
    That is correct, but the conflict lands where today's lock would have
    made the other side wait.
  - A range lock (an entry in `db.locks` named per range, plus a per-tree
    list that `lockRow` checks) would restore the waiting. It is left out
    unless it is wanted: decision D4.
- **Foreign keys:**
  - Child-side FKs (this table referencing others) need nothing: deleting
    a child row never violates one.
  - Parent side (`refBy`) falls back for v1. Stage 7 would do two things:
    - RESTRICT and NO ACTION by one probe for any child key in range,
      when the child has an index or PK leading with the FK columns and
      the FK references this table's PK prefix;
    - CASCADE as a range delete of the child, when its FK columns lead
      its PK.
  - SET NULL and SET DEFAULT always fall back.
- **Triggers:** none exist. When they come, a row-level DELETE trigger
  forces the fallback.
- **RETURNING:** falls back; it needs the rows.
- **Secondary indexes (D2):**
  - v1 requires none.
  - Cheap to add: an index whose leading columns are the very PK columns
    of the range, at the same collation, with no expression. Its entries
    `1‖v…‖pk` (`encIdxPart`) for rows in range are exactly
    `[idx(lo), idx(hi))` with the marker bytes, so it takes the same op.
    A partial index works the same way. Such indexes are rare.
  - Stage 6, the common case: read the range's rows (only the index
    columns, `delNarrow`) and delete their index entries one by one,
    while the table's subtrees are still dropped. That saves the table
    half of the writes, log and commit loads.
  - The index side still costs about what it costs today per row, and
    leaves sparse index leaves, since leaves never merge. Its write set is
    bounded by step 2 or by `max_statement_mem`.
- **Temporary tables:** fine. They are logged like any table (9.96).
- **Statistics:** `noteChg` with n. `ANALYZE` estimates go stale until
  auto-analyze, as today.
- **WAITFOR consumers** (lexdb-events): producers append above the
  cursor and the purge removes below it, so there is no conflict. The
  `floor` column is the application's.

### 2.5 What fraction of real purges it covers

[estimate; nothing measured]
- **v1 (no indexes, no referencing FKs, autocommit):**
  - covered: append-only logs and queues keyed by id or time, event
    streams keyed `(stream, seq)`, staging tables, `DELETE FROM t` with no
    WHERE, and test cleanup (gaps 2.7);
  - not covered: most application tables, which have at least one
    secondary index; and purges from Python, since psycopg2 opens a block
    by default.
- **With stage 5 (blocks) and stage 6 (indexes):** most purges by a key
  range.
- **Never covered:** a purge by a column that is not the key (`created_at`
  when the PK is a serial or a uuid).
  - The user can rewrite it as `id < (SELECT min(id) FROM t WHERE
    created_at >= $1)`, which the detector accepts when ids rise with
    time.
  - A later option is out of scope here: column leaves whose greatest
    `created_at` is below the cutoff could become key ranges. That reads
    the leaves but writes nothing per row.

## 3. Step 2: bounded memory for a large transaction

| | Spill past a size, all or nothing | Batched: `WITH (batch_rows n)` |
|---|---|---|
| Write set | sorted runs on disk; `get`, `getMany`, scans and `ownRange` merge them; there is no spill code to reuse (sorts do not spill either) | n rows, then commit, as COPY (exec:21848) |
| Commit apply | must not load, so all touched leaves are in memory at once (section 1): spilling the write set alone does not bound memory. Applying in parts needs the partial state hidden while loads yield: a new mechanism | n rows' leaves |
| Log | the records of one commit are one frame, and its length is u32 (`frame`, store:1839). Needs commits over several frames, recovery that applies a commit only after its last frame (two passes), and a follower that holds back the same way | unchanged |
| Single-thread stall | the whole apply in one `with`: seconds to minutes for 100M rows | n rows' apply per commit |
| Semantics | atomic | not atomic: a failure keeps earlier batches, and the error says how many rows were committed; refused in a block (25001) |
| Size | large: store, log, recovery, follower | small: parser and executor |

**What users of each system expect:**
- **PostgreSQL:** any DELETE is atomic and runs in bounded memory, with
  VACUUM and bloat paid later. DBAs still split large purges, to limit WAL
  bursts and replica lag, and use partition DROP for retention.
- **SQL Server:** atomic too, but the log grows and locks escalate past
  about 5,000. The usual idiom is a loop:
  `WHILE 1=1 BEGIN DELETE TOP (n) ... ; IF @@ROWCOUNT < n BREAK END`.
  lexdb's T-SQL has TOP, WHILE and `@@ROWCOUNT` [read], so that loop
  should work today, each DELETE committing alone.
- **Oracle:** atomic, with undo growth and ORA-01555 for others. There is
  no built-in batched DML: people write PL/SQL loops with `ROWNUM <= n`
  and COMMIT (lexdb's PL/SQL has COMMIT [read]) or use
  DBMS_PARALLEL_EXECUTE.
- **In short:** none of them has a batched DELETE statement. lexdb's
  would be its own, like COPY's `batch_rows`. Spilling is the only option
  that matches PostgreSQL's "it just works", at the cost in the table.

**Recommendation: batched.** It follows the user's own decision for COPY
(9.87). The spill row of the table is a project on the scale of the log
format, and step 1 takes away its main reason.

**Its design:**
- **Grammar:** `DELETE ... [WHERE ...] WITH (batch_rows n)` and `UPDATE
  ... SET ... [WHERE ...] WITH (batch_rows n)`. The option list reuses
  COPY's parsing (sql:5942). n must be positive (22023).
- **Refused:**
  - inside a block (25001);
  - with RETURNING or OUTPUT (0A000), whose rows would grow without bound;
  - for UPDATE, when SET assigns a PK column (0A000), since rows would move
    past the cursor.
- **Each batch:**
  1. Run the query for at most n rows.
  2. `delRow` or `updRow` them, then `fkFinish`.
  3. Commit, and start a fresh `Txn` with the same path, session, temp
     schema and `now()`, as COPY does.
- **Where the next batch starts:**
  - For a PK-ordered path (a full scan or a PK range), a key cursor:
    the next batch's lower bound is just after the last key scanned.
    Without one, each batch would scan again the rows that did not match,
    which is quadratic when matches are sparse.
  - For an index path in DELETE, run the query again. The deleted rows'
    entries are gone, so each run starts at the next match.
  - UPDATE always uses a PK-ordered path with the cursor, so that updated
    rows are never visited twice (the Halloween problem across batches).
- **Conflicts:** a conflict at a batch's commit runs that batch again from
  the cursor, up to 10 times. The statement as a whole is not run again.
- **What it does not see:** rows committed behind the cursor by others
  during the run are not deleted. The documentation says so.
- **Its tag** is the total: `DELETE n` or `UPDATE n`.
- **A shape that takes the range path** ignores `batch_rows` and commits
  once. It is already bounded, and atomic.

Does step 1 make step 2 less needed? Yes, for the case 2.5 names (a key
range purge): it holds one write. Step 2 remains for purges by a column
that is not the key, for tables with indexes before stage 6, for large
UPDATEs, and for blocks of many statements. Step 2 can wait until one of
those is asked for.

## 4. Decisions for the user

Each has a recommendation.

- **D1. The count.**
  - (a) Exact, from raw leaf headers: the leaves are read, but nothing per
    row.
  - (b) Subtree counts in a new internal page type: no leaf reads at all,
    a format change, and also a faster `count(*)`.
  - (c) No exact count: refuse it, since the protocol needs a number.
  - *Recommend (a) now. Take (b) only if cold purges measure too slow.*
- **D2. Secondary indexes.**
  - (a) v1 only for tables without them, and those whose indexes lead
    with the same columns.
  - (b) Then stage 6: index entries deleted per row, the table's subtrees
    still dropped.
  - (c) Never.
  - *Recommend (a), then (b).*
- **D3. Foreign keys referencing the table.**
  - (a) Fall back always.
  - (b) Stage 7: RESTRICT and NO ACTION by a range probe, CASCADE as a
    child range delete where the child's PK leads with the FK.
  - *Recommend (a) until a real schema needs it.*
- **D4. Transaction blocks.**
  - (a) v1 only for a statement's own transaction.
  - (b) Stage 5 adds blocks, where a concurrent locker gets 40001 rather
    than waiting.
  - (c) (b) plus a range lock.
  - *Recommend (a), then (b). Take (c) only if the conflicts show up.*
- **D5.** A switch, `SET lexdb_range_delete = on|off` (default on), for
  the differential tests and for benchmarks. *Recommend yes.*
- **D6. Step 2's form.**
  - (a) `WITH (batch_rows n)` on DELETE and UPDATE.
  - (b) A session setting that batches every DELETE and UPDATE: silently
    not atomic, and dangerous.
  - (c) Spill.
  - (d) Nothing: point users to client-side loops (T-SQL TOP and
    `@@ROWCOUNT`, PL/SQL ROWNUM and COMMIT, PostgreSQL's
    `id IN (SELECT ... LIMIT n)`).
  - *Recommend (a), after step 1. (d) is acceptable meanwhile.*
- **D7. The unknown-op check in `parseRecords`** (2.3): it makes an older
  binary fail loudly rather than lose deletes. *Recommend yes, in stage 1.*

## 5. Stages

Each stage is meant to fit one Sonnet-level session. Each ends with the
whole suite:
`cd /home/chris/Work/lexell && LXL_NOCACHE=1 python3 lexell/tests/lexdb.py -j 4`.
The crash tests use the simulated Fs (`lexdb_disk.sim(seed)`, as
`store_crash` and `store_drop` do).

0. **Check P1 and P2 (section 7) first.**
   - Extend `store_drop`: a snapshot scans a dropped tree that is mostly on
     disk, loading its internal nodes, and ends. Then the walk runs, and
     `audit` must show `lost 0`.
   - If it leaks, `releaseSlot` must free a loaded node's child slots, as
     `applyDrop`'s loop does.
   - Add a guard against a batch whose payload would not fit u32: the
     commit fails with 54000.
1. **Store: OP_DELRANGE.**
   - The work:
     - `Txn.delRange`;
     - the record, `parseRecords` (and the unknown-op check, D7);
     - `logWrites`, and `WEntry.open` with its case in `validate`;
     - `writeNeeds`, `applyDelRange` and `dropSubtree`;
     - the companion ranges per key length.
   - New test `store_delrange`, against a `Map` model, with a 256 KB
     cache so that most covered subtrees are on disk:
     - Random keys of mixed lengths, every 40th value 20 KB.
     - Ranges: empty, inside one leaf, across levels, from the start, to
       the end, the whole tree, and a bound equal to a separator.
     - After each step, `audit`. Also after the walk: every freed page
       free, and writing again does not grow the file.
     - A snapshot taken before a range delete reads every old row (get,
       scan, scanBack) while checkpoints run. After it ends, `audit` is
       clean.
     - Conflicts: a transaction that read a key in the range fails; one
       that read just outside (at `hi`, and below `lo`) commits; a range
       to the end against an insert at the tail.
     - In one transaction: put, range delete, put of the same key; and
       put, then a range delete covering it.
     - 12 crashes at random points (the commit, the checkpoint, the walk),
       with commits to another tree going on: each recovers to the model.
   - Planted bugs to catch: a separator left in place, a height off by
     one, a child at the range's edge removed, an edge leaf's key at `hi`
     deleted, a companion length skipped, the `validate` case missing.
2. **Store: `countRange` and `noteRange`.**
   - Raw reads on the helper pool, the slot check and its restart.
   - Tests in `store_delrange`:
     - counts equal scan counts, cold and warm;
     - a checkpoint and an eviction during the count;
     - the cache's contents unchanged by a count.
3. **Follower: range tombstones.**
   - `Delta.cuts: [](lo, hi, batch)`.
   - `Fol.apply` adds a gone version for each delta key in range, then the
     cut.
   - `get`: a delta version wins; else a visible cut means gone; else the
     base.
   - `scan`/`scanBack`/`baseScan` scan around the cut ranges, so base
     leaves in a purged range are not read.
   - `prune` drops cuts below the floor.
   - Tests:
     - a `follow_basic`-style `follow_delrange`: snapshots before and
       after, a base adopted across the delete, puts after a cut in one
       batch;
     - `exec_replica`, with a range DELETE on the master read on the
       replica;
     - `tests/lexdb/replica.py`.
4. **Executor: the statement.**
   - `rangeDelete` and its detector, the exact bounds and the
     coerce-back check, the lock check, `noteChg`, the tag,
     `SET lexdb_range_delete`, and EXPLAIN's line.
   - New `exec_rangedel`: about 60 DELETE shapes, each run with the switch
     on and off on identical tables, comparing the tags, the rows left
     and an `audit`. The shapes:
     - those that take the path: one- and two-column PKs, int, bigint,
       numeric, date, timestamptz, uuid and text keys, `=`, `<`, `<=`,
       `>`, `>=`, BETWEEN, parameters, `now()`, a scalar subquery, no
       WHERE;
     - those that must fall back: an index, `refBy`, RETURNING, TOP,
       ROWNUM, a residual conjunct, a float PK, a CI collation,
       `id < 10.5`, an OR, IN.
   - Also: a NULL bound; T-SQL and Oracle spellings, through
     `tds_tsql`-like cases.
   - Add range deletes to `tests/lexdb/crash/client.lxl`, and run
     `crash.py` for 6 rounds in each I/O mode.
5. **Blocks.**
   - `Txn.cuts`, filtered in `getIn`, `getMany`, `scanIn`, `scanLeaves`,
     `scanBackIn` and `snapGet`, where the transaction's own writes
     override.
   - The fast path then runs in blocks.
   - Tests, in `exec_rangedel`:
     - in a block, DELETE a range, then SELECT it, INSERT into it, count
       it;
     - ROLLBACK TO a savepoint before the delete;
     - two sessions: serializable 40001 both ways (as `exec_dmlscale`'s
       case);
     - a concurrent `FOR UPDATE`.
6. **(D2-b) Tables with indexes.**
   - Read the rows' index columns, delete the index entries one by one,
     and still drop the table's subtrees.
   - Indexes that lead with the PK's columns take the range op directly.
   - Tests: `exec_dmlscale`-style counts through every index against
     counts by scan; expression and partial indexes.
7. **(D3-b, optional) Referencing FKs:** the probe and the cascading
   range. Tests: cases from `exec_fkaction` and `exec_fkey` run with the
   switch on and off.
8. **Step 2: `WITH (batch_rows n)`.**
   - The work:
     - the parser, at the end of DELETE and UPDATE (sql:5447, sql:5463);
     - the batch loop, after COPY's;
     - the cursor or the re-run;
     - the refusals.
   - New `exec_batchdml`:
     - 10 rows in batches of 3;
     - a failure in the third batch keeps 6 rows, with the error's
       context;
     - the refusals;
     - UPDATE that moves no row twice;
     - a sparse predicate over a large table, which must not scan
       quadratically (rows read counted through EXPLAIN ANALYZE's
       counts);
     - `held` stays under n rows' bytes;
     - a conflict on one batch runs that batch again.
9. **Measure (section 6), then write it up in `lexdb.md`** as a new 9.x
   section, and update gaps 2.4 and 2.5.

## 6. Benchmarks

The rules:
- Run one benchmark at a time, the median of 3.
- The harness is in `~/Work/lexdb-bench/saved/vec/` (`dml.py`, `bench.py`,
  `mem.sh`), on copies of `../ldata` in a `chattr +C` directory.
- PostgreSQL 18 is `saved/pg18`, with
  `max_parallel_workers_per_gather = 3` and
  `max_parallel_maintenance_workers = 3` (the leader plus 3 workers).

The baseline from 9.109 (warm): DELETE of 10k rows with an index 164 ms
(PostgreSQL 52); the w2 DELETE of about 190k rows with no index 349 ms
(PostgreSQL 99). Note that the w2 one is `WHERE a >= x AND a < y`, and `a`
is not the key, so it would not take the new path. Add PK-range variants.

1. **w2, `id` ranges of 1%, 10% and 50%:**
   - each with the switch off (today's path) and on, warm and cold (a
     server started per round, as 9.109's cold runs);
   - on lexdb: wall time, server CPU, `Stats.logBytes`, and the
     checkpoints until `dropped` is empty;
   - PostgreSQL: DELETE, then VACUUM, timed apart.
2. **A 10M-row events table (about 1 GB), the oldest half purged:**
   - lexdb with the switch off (max_statement_mem 0) and on;
   - PostgreSQL DELETE plus VACUUM;
   - PostgreSQL with the table partitioned by day and the partitions
     dropped, as the reference for what partitioning gives;
   - measured: RSS at its peak (`mem.sh`), the commit time, the file size
     after refilling the half.
3. **Stall:** a second client inserting at the tail at a fixed rate during
   (2). Its p50 and p99 latency, with the switch off and on.
4. **Replica:** `exec_replica`'s setup, timing the follower's apply of the
   one record against 5M row records.
5. **Step 2** (after stage 8): 5M rows deleted by a column that is not the
   key. One statement (max_statement_mem 0) against `batch_rows 100000`:
   wall time and peak RSS.

Expected, [estimate] to be replaced by the numbers: a warm range delete
commits in milliseconds, as a drop does (9.32: 1.5 to 13 ms for 105 MB). A
cold one is bounded by reading the covered leaves for the count (D1).

## 7. Found while reading, not caused by this design

- **P1. Page leak: confirmed and fixed (9.127)** (stage 0). A snapshot
  that began before a DROP/TRUNCATE and read the dropped tree afterwards
  loaded deferred slots; `installOnly` gave their children slots no
  deferral named, and `releaseSlot` freed only the loaded node's own page.
  Test `store_dropsnap` (3,000-row tree of 747 pages, snapshot opened,
  tree dropped, snapshot reads 5 keys or scans 400 rows, checkpoints,
  snapshot released, checkpoints until the walk ends): `audit` showed
  `lost 107` (one path) and `lost 179` (scan), and `lost 179` for
  TRUNCATE (a drop plus a refill). Fix: a `whole` flag on `Deferred`
  (set by `applyDrop`); at release, `releaseWhole` frees the unpinned
  loaded children first (pinned ones have their own entries, which come
  later), then `releaseSlot` the node. The immediate path is unchanged
  (its children are on `applyDrop`'s stack). Now `lost 0`. A range delete
  beside a long report is the same scenario, so stage 1 may rely on it.
- **P2. Log frame length u32: confirmed and fixed (9.127).** `frame` wrote
  the payload length with `setU32LE` and nothing checked the batch's size.
  Now `commitLive` refuses a commit whose records (`recordsLen`) pass
  `FRAME_MAX` (4 GiB less a page) with 54000 before applying or logging
  it; a commit that fits alone but not the pending batch waits until the
  writer takes the batch (so the limit holds across commits too). Test
  `store_framemax` lowers the limit with `setFrameMax`.
- **P3.** 9.109's "DELETE with no index" benchmark deletes by a column
  that is not the key (section 6).
