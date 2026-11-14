# lexdb: bulk deletes without partitioning (a design, 2026-11-14)

The two steps of [lexdb-gaps.md](lexdb-gaps.md) 2.5. Stages 1 to 6 are built (see the "as built" notes in section 5).
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
- **Waiting-SELECT consumers** (lexdb-events): producers append above the
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

Each has a recommendation. **Decided 2026-11-14: the user took every
recommendation** (D1 a; D2 a, then b; D3 a; D4 a, then b; D5 yes; D6 a,
after step 1; D7 yes, in stage 1). So stages 1 to 6 and 8 are to be built;
stage 7 (D3-b) waits for a schema that needs it.

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
   - **As built (2026-11-14).** Code in `lexdb_store.lxl`, test
     `store_delrange`; `Txn.delRange`, `OP_DELRANGE` (6), `WEntry.open`,
     `edgeNeeds`/`writeNeeds`, `applyRange`, `applyDelRange`, `cutKids`,
     `cutLeafRange`, `dropSubtree` (`applyDrop` now calls it), `chunkLens`,
     `chunkLo`/`chunkHi`. Where it differs from 2.3 or adds to it:
     - **Record:** the usual one (op 6, tree, key = lo, val = hi, no head).
       `parseRecords` now rejects any op outside 1 to 6 as corrupt (D7).
       `Fol.apply` panics on op 6 until stage 3: a follower that skipped it
       would show the deleted rows.
     - **`delRange` and the write set:** the range is not a key written, so
       it is not in `idx` (a key `lo` there would hide a put of `lo`), and
       `undoTo` skips it when it rebuilds `idx`. Only the transaction's own
       *puts* in the range get an `OP_DEL` first (a key whose last write is
       a delete needs none). Base rows in the range stay visible to the
       transaction's own reads until stage 5.
     - **Which side keeps the range:** at A the separator after L's child
       stays, so the range of the removed middle children goes to H's side;
       below A it goes to the path child, as 2.3 says. Both are in memory.
       No root collapse is needed: A keeps both its L and H children.
     - **Dirty and `willChange`:** a range that changes nothing (empty, or
       no key in it in the edge leaves and no child to remove) marks and
       changes nothing. Otherwise every node on L and H is marked dirty,
       and `willChange` is called on those whose contents change.
     - **`writeNeeds` for the companion:** the lengths present come from
       `chunkLens`, which skips from one length to the next (descend to
       `u16(L+1)`); `edgeNeeds` then loads the two paths of each length's
       range. `cb(L, lo)` and `cb(L, hi)` are as in 2.3; for `hi == ""` the
       end is `u16(L+1)`. One write returns one slot per pass, as before.
     - **Lengths at apply time:** `applyRange` finds them again. A length
       that an earlier write of the same commit made has no chunks in the
       range (the range's own puts were made deletes first) and may have no
       edge paths in memory: it is skipped (`edgeNeeds` finds a slot to
       load). The main tree's paths must be in memory (`panic` otherwise,
       as no later pass can load them).
     - **Found on the way, fixed:** a descent whose root is not in memory
       gives an empty path *and* `need >= 0`; the first version of
       `chunkLens` tested the path first, took the tree for empty, and left
       every chunk behind. `applyDelRange` and `chunkLens` test `need`
       first. `store_delrange` checks the companion against the model for
       this (`companionOf`: the keys it has chunks of are the model's large
       values); `audit` does not see leftover chunks.
     - **Test:** 3,000 random keys of lengths 66, 86 and 106, a 256 KB cache,
       nine range shapes (each in a fresh store, reopened for every step, a
       checkpoint after the commit in half of them and the log's replay
       alone in the others), snapshots, conflicts (also scans up to `lo` and
       from `hi`), same-transaction mixes (also a large value of a new key
       length, a savepoint), the unknown op, 12 crashes. A range delete
       loads at most 40 nodes in all of them.
     - **Planted bugs, all caught:** separator left in place (a page index
       out of range), height one too low at A (`lost` pages in the audit),
       the edge child removed (rows missing), the key at `hi` deleted (one
       row missing), the last companion length skipped (the companion's
       leftover chunks), the `validate` case missing (a read at `hi`, and
       the read of the tail, give the wrong answer). Also freeing the
       removed slots at once instead of through `freeSubtree`: the
       snapshot test fails.
2. **Store: `countRange` and `noteRange`.**
   - Raw reads on the helper pool, the slot check and its restart.
   - Tests in `store_delrange`:
     - counts equal scan counts, cold and warm;
     - a checkpoint and an eviction during the count;
     - the cache's contents unchanged by a count.
   - **As built (2026-11-14).** `Store.countRange`, `Store.noteRange`
     (`lexdb_store.lxl`, before "many keys at once"), test
     `store_countrange` (a new file, about 2 s). Where it differs from 2.2
     or adds to it:
     - **Nothing is loaded, edge leaves included.** 2.2 counts the edge
       leaves from memory. A leaf that is cut by a bound is read raw and
       decoded for its keys in range (`leafIn`), as is any inner page the
       range cuts, so the count makes no load, no eviction and sets no
       reference bit. `cacheState` (the nodes in memory, with their
       reference and dirty bits and versions) is the same after, as are
       `loads`, `evictions` and `loaded`.
     - **Two steps.** Under one `sh.with` (no I/O) `countSlot` walks what is
       in memory and leaves an item (page, the slot it hangs from, the
       node's key range, whether it lies inside the range) for each slot not
       in memory. Then `countPages` reads the items outside the lock, 2,048
       pages at a time in sorted runs of consecutive pages
       (`READS_IN_FLIGHT` reads at once on the helper pool, as `loadMany`),
       counting a whole leaf from its header (u16 at 16, the same in every
       leaf type) and turning an inner page's children into items: a whole
       inner page reads its entries straight, no decoding. Memory is the
       batch plus the items waiting (about one inner page's children per
       batch page), not the subtree.
     - **The slot check** covers every slot the reads started from (`CTop`:
       slot, `gen`, `disk`), under one `with` after all the reads. Any
       change (`gen` or `disk` differs, loaded, not used) starts the count
       again from the root; the pages read in that try are dropped, and so
       are their errors (a page freed and reused under the read is another
       page: wrong checksum number, type or shape). An error with the slots
       unchanged is real and returned. The first try and 3 restarts, then
       `Ok(-1)`: the caller counts rows (stage 4's fallback to the row
       path). A page chain over 64 deep is corrupt (a loop made by a reused
       page).
     - **Eviction frees the slots.** Evicting a parent frees its children's
       slots (`dropSlot`), so a flush of the cache under a count is a
       restart by `gen`, as a commit and checkpoint are by `disk`. A slot
       whose parent is the root cannot be freed this way, and a flush leaves
       the count as it was (nothing it counted changed).
     - **A snapshot's view.** The design is silent. A transaction that reads
       a snapshot (and is not `live`) counts the snapshot's tree, as of its
       commit: `verOf` picks the version of each node in memory (current or
       from `hist`), a slot not in memory at the snapshot's commit is read
       raw, and a slot changed since has been loaded and has its old version
       in `hist`, so the slot check restarts onto it. Leaves newer than the
       snapshot (splits, inserts) are not reached: the old inner versions do
       not name them. A cancelled snapshot gives 72000.
     - **Own writes are not counted.** The count is of the tree, the
       transaction's own puts and deletes in the range are not applied. The
       executor's range delete (outside a block) has none in that tree. In a
       block (stage 5) it must correct for `Txn.writes` or fall back.
     - **A replica** counts by a scan (stage 3 may read headers).
     - **`noteRange(t, tree, lo, hi)`** is `noteRead` at the commit the
       transaction's reads see (`db.seq` live, the snapshot's own): a commit
       of a put or delete of a key in `[lo, hi)` after it fails the
       transaction (40001) at `validate`, the existing mark case. It does
       nothing for an empty range, a `quiet` transaction, a read-only
       snapshot (not tracked) or a replica. Without it, an insert that
       commits first is removed by the range delete unseen (tested).
     - **Hook for the tests:** `setCountHook(f, mode, arg)`, a plain `fn`
       (a closure cannot be kept in the store), called between the walk and
       the reads, outside the lock.
     - **Tests:** counts against the model and a scan's for 72 ranges
       (cold: 14 in freshly opened stores; mixed; warm: all in memory),
       empty trees and absent tree, a commit and checkpoint, a new row, a
       flush, and a change at every try (-1) during the count, a snapshot
       counting its view through a delete, 600 inserts, changes, a
       checkpoint and a flush, and the `noteRange` conflicts: insert,
       update and delete in the range fail; below `lo`, a write at `hi`,
       past `hi` and another tree commit; the statement run again counts the
       inserted row.
     - **Planted bugs, all caught:** the leaf's `hi` inclusive; the last
       child of a whole inner page skipped; the restart missing (the insert
       during the count is lost: counted 1800, want 1801); a child that
       starts at `lo` skipped; the low edge, and the high edge, taken as
       whole; `noteRange` not noting.
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
   - **As built (2026-11-14).** `Delta.cuts` (`Cut{lo, hi, batch}`),
     `Fol.apply`, `cutBy`, `deltaKeysIn`, `uncut`, `DRange.segs`,
     `FStats.cuts` (`lexdb_store.lxl`); test `follow_delrange`. Where it
     differs from the plan above or adds to it:
     - **Apply:** an empty range is ignored. Each delta key in `[lo, hi)`
       whose last version is not already gone gets a gone version at the
       cut's batch, then the cut is appended. A put of the same batch after
       the cut is a later version, so it wins.
     - **No companion cuts.** The follower reads a large value's chunks
       from the base's companion tree only through the main tree's base
       entry (`unstore`), and keeps delta values whole. A cut that hides
       the main entry hides the chunks, as an `OP_DEL` of a large value
       does (it touches only the main key). So no per-length chunk ranges.
     - **`get`:** `version` gives gone when the key has no delta version at
       or before the batch and a cut at or before it holds the key.
     - **Scans:** `deltaRange` gives `segs`, the parts of `[from, to)` not
       covered by a cut at or before the snapshot's batch (`uncut`);
       `scan` reads the base over each, `scanBack` over each from the last.
       The delta merge runs on across them. Base leaves in a purged range
       are not loaded (tested: a whole-tree cut loads no page).
     - **`prune(floor)`** drops cuts below the floor, as versions; a delta
       with cuts and no versions stays.
     - **Base adopted across the delete:** nothing special. A snapshot on
       the new base sees the delete in its pages (and the cut, kept while an
       older base is in use, hides nothing the base has that a later put
       did not restore: the put's version is in the delta).
     - **Replica `countRange`** stays a scan: correct, and now it skips the
       cut ranges. An exact count from leaf headers would have to correct
       for the delta's versions and cuts over a base range, which is not
       cheap; not done.
     - **Tests:** `follow_delrange`: 15 scripted steps, each
       checked against a master snapshot (whole, backward, point reads) with
       kept snapshots across checkpoints, then a cold follower, then 60
       random rounds with every range shape, at a 48 KB and a 16 MB follower
       cache. Planted bugs, all caught: a cut ignored by `scanBack`, a cut
       visible to an older snapshot, `prune` dropping cuts above the floor
       (needed a check between the snapshots ending and the next
       checkpoint).
     - **`exec_replica`:** done in stage 4 (a range DELETE on the master
       read on the replica), and `replica.py` has range deletes.
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
   - **As built (2026-11-14).** `rangeDelete`, `rangePlan`, `rdRange`,
     `rdBound`, `rdConst`, `noteChgN` (`lexdb_exec.lxl`, after `delete`);
     `Store.locksIn` (`lexdb_store.lxl`); `SET lexdb_range_delete` (parser,
     `Session.rdel`, `Limits.rdel`, SHOW, RESET, a block's ROLLBACK);
     `lexdb_exec.rangeDeletes()` counts the statements that took the path (a
     test's check). Tests: `exec_rangedel` (121 shapes, each with the
     switch on and off), `tds_rangedel`, `tns_rangedel`, `exec_replica`
     (a range DELETE on the master), the crash client (table `ev`), and
     `replica.py` (table `r`). Where it differs from 2.1 or adds to it:
     - **The WHERE is read from the level's conjuncts** (`Level.cond`, all
       of the WHERE for a DELETE), not from the `Path`. A conjunct counts
       when it is `key column op c` (either side), `c` built only from
       literals, parameters, `+ - * / % ||`, casts, a few stable functions
       (`RD_FNS`: now(), current_timestamp, date_trunc, dateadd, ...) and
       uncorrelated scalar subqueries. A function not in the list (user
       functions, random(), sequences) is a residual, so the row path.
     - **At most one equality per key column, in the leading columns, then
       at most one lower and one upper bound on the next.** Two bounds the
       same way (`id > 5 and id > 10`), an equality and a range on one
       column, or an equality after a gap fall back.
     - **A point (all key columns equal) falls back:** it is one row, and
       the lookup is cheaper than a count.
     - **The coerce-back check** is `compareZ(v, coerceZ(v, column type))
       == 0` in the session's zone, so `id < 1500.5` on an int, a numeric
       with a lost scale, a timestamp on a date, a float and a bigint past
       an int (22003) all fall back. An evaluation error also falls back
       (the row path gives it).
     - **Key columns of exact kinds only where the range uses them**: a
       float, a case-insensitive or padded text, `char(n)` or an enum in
       the columns the range names falls back; one in a later column does
       not matter.
     - **Indexes (D2):** an index takes the same op when its leading
       columns are the key columns the range uses (a partial index and an
       index with more columns after them too): its entries are marker,
       value, ..., so the rows of the range are one range of it
       (`rdRange` with the marker). An index that is too short (an index on
       `a` for a range on `(a, b)`), of another column or on an expression
       sends the statement to the row path. **The whole table** (no WHERE)
       takes the path with any indexes: each index's whole range goes.
     - **Not taken inside a transaction block, with any write already in the
       transaction (`hasWrites`), or in a `quiet` transaction** (a locking
       SELECT's). Checked for the doors: T-SQL runs a statement of a batch
       under a savepoint only when the session is already in a transaction
       (`status != 'I'`: a block), and `IMPLICIT_TRANSACTIONS` begins one; a
       DELETE in a TRY block outside a transaction takes the path.
       **Oracle's door begins a block for every DML statement**
       (`lexdb_tns.runCursor`: `BEGIN` when idle, then `SAVEPOINT`s), so a
       DELETE from Oracle never takes the path in v1; `tns_rangedel`
       checks the counts and that it falls back. Stage 5 is what makes
       Oracle's (and psycopg2's) DELETE eligible.
     - **Locks:** `Store.locksIn(tree, lo, hi)` scans the lock table for a
       key of the tree in the range held by another owner; if one is, the
       row path runs (it waits). EXPLAIN on a snapshot does the same check.
     - **`noteChg`:** `noteChgN` adds n deletes to the session's pending
       counts (the same memo the row path's `noteChg` fills).
     - **The count's restarts:** `countRange` giving -1 sends the statement
       to the row path (the statement then runs as today, after the range's
       read mark was noted, which only makes it more likely to conflict).
       `n == 0` writes nothing (`DELETE 0`), as does a NULL bound or an
       empty range.
     - **EXPLAIN** of a DELETE adds a line `range delete: primary key
       range, subtrees dropped` (or `whole table`, with `(n indexes too)`,
       or `no row can match`) when the statement would take the path; the
       bounds are evaluated, so a scalar subquery in them runs.
     - **`ROWNUM` in a DELETE** is refused by lexdb on both paths today
       (`ORA-20000: window functions are not allowed in DELETE`), so
       there was nothing to fall back from; TOP is a `limit` and falls
       back.
     - **Crash and replica tests.** The crash client has a table `ev` (no
       secondary index): each worker inserts into it and range-deletes its
       own rows below a point (count checked against its record; an
       unanswered range delete must be whole or gone, being one write);
       `crash.py --rounds 6` passed with io_uring (the default) and with
       `LXL_URING=0`. `replica.py` has a table `r` with range deletes and
       refills among its writes. `exec_replica`'s step shows the delete on
       the replica (edges, both scan directions, a block that began
       before, a checkpoint adopted).
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
   - **As built (2026-11-14).** `Txn.cuts` (`TCut{tree, lo, hi, pos}`),
     `Txn.cutKey`/`cutsMeet`/`hasCuts`, `Store.getBaseIn`, `Store.countView`
     (`lexdb_store.lxl`); `rangePlan` and `rangeDelete` (`lexdb_exec.lxl`).
     Tests: 12 block scripts and a two-session `blockTest` in
     `exec_rangedel` (now 133 shapes, about 18 s), `tds_rangedel` and
     `tns_rangedel` (the Oracle door and BEGIN TRAN take the path), blocks in
     the crash client's `ev` and in `replica.py`'s `r`. Where it differs from
     the plan or adds to it:
     - **A cut hides stored keys only.** The rule in every read: the
       transaction's own write of a key (`idx`) first, as before; else, if a
       cut of the tree holds the key, gone; else the store. So a later own
       put beats an earlier cut, and an earlier own put inside a cut is
       already a delete (`delRange`, stage 1). `getIn` checks the cut after
       its own-write match and before `getBaseIn` (the old rest of `getIn`,
       with the replica, snapshot and live reads, so `snapGet` is covered);
       `getMany`, `scanIn` and `scanBackIn` skip a stored entry in a cut
       that no own write took the place of; `scanLeaves` gives up (`Ok(false)`,
       as for own writes) when a cut meets its range, and the scan runs
       instead. Raw scans (a companion tree's chunks) have no cuts: chunks
       are reached only through the main entry. A scan through a cut still
       reads the cut's leaves (no jump to `hi`): not worth the own-write
       merge it would need; the leaves of a purged range are often few
       reads after the range delete has run, and the commit drops them.
     - **`undoTo`** pops the cuts whose `pos` is at or after the savepoint's
       write count (the `OP_DELRANGE` write goes with them; the rebuilt `idx`
       never held it).
     - **The count: `countView`**, used by `rangeDelete` in place of
       `countRange` (which still counts the tree only):
       `rows = countRange(range) - sum countRange(earlier cuts inside the
       range, merged into disjoint intervals) - #(own-written keys in the
       range outside those cuts that are stored: one lookup each, not noted)
       + #(own puts in the range)`. An own write is the last write of a key
       (`ownRange`); a put after a cut counts once (its cut interval removed
       the stored row from the first term, if any). Falls back to the row
       path (`Ok(-1)`) when `countRange` gives up, or when the range holds
       more than `COUNT_OWN_MAX` (10,000) own writes (a lookup each). No
       other case falls back: the formula is exact for every mix tested
       (own insert of new keys, updates, deletes, earlier overlapping and
       adjacent cuts, a cut then an own put, savepoints).
     - **`rangePlan`:** only the `inBlock`/`hasWrites` refusal is gone;
       `quiet`, EXPLAIN-snapshot and every other refusal stay.
     - **Locks (D4-b).** The range delete takes no row lock. The row path in
       a block locks each found row and keeps it (`lockFound`: a concurrent
       UPDATE or `FOR UPDATE` then waits for the block's end). The range
       delete keeps what stage 4 has: a lock held by another session on a
       key in the range (`Store.locksIn`) sends the statement to the row
       path, which waits as today; and a session that locks or updates a row
       of the range after it is not made to wait: both go on, and the one
       that commits second fails 40001 (the delete's `noteRange` read mark
       against the locker's write, or the locker's read of the row against
       the `OP_DELRANGE` entry in the write log). `blockTest` shows both
       orders, and an UPDATE or a `SELECT ... FOR UPDATE` taken after the
       delete returns at once. A `SELECT ... FOR UPDATE` alone writes
       nothing and notes no read, so it is not made to fail by the delete
       (not tested alone).
     - **Doors.** Oracle's door (a block for every DML statement) and
       T-SQL inside BEGIN TRAN (each statement under a savepoint, so a
       failed one `undoTo`s its cut) take the path; so do psycopg2 and JDBC
       with autocommit off.
     - **Planted bugs, all caught** (`exec_rangedel`): a cut ignored by
       `scanBackIn`, by `scanIn`, by `getIn`, by `getMany` (the join with
       `u`), by `scanLeaves` (the plain count read); the cut not undone by
       `undoTo` (the savepoint script); the count not adding own puts.
     - **Open for stage 6:** a table with non-qualifying indexes still takes
       the row path; the count correction is already for the main tree only
       (the index trees' cuts need none: their entries are deleted and
       hidden by the same rule).
6. **(D2-b) Tables with indexes.**
   - Read the rows' index columns, delete the index entries one by one,
     and still drop the table's subtrees.
   - Indexes that lead with the PK's columns take the range op directly.
   - Tests: `exec_dmlscale`-style counts through every index against
     counts by scan; expression and partial indexes.
   - **As built (2026-11-14).** `delEntries`, `RPlan.slow`, `treeDump` (a
     test's look at every tree of a table) in `lexdb_exec.lxl`;
     `Db.ovfLens` and a fix in `applyRange` (`lexdb_store.lxl`). Tests: the
     new `exec_rangedel_ix` (68 shapes, about 25 s), three shapes of
     `exec_rangedel` changed from fallbacks to the path plus one new (134),
     the crash client's `ev` (two indexes, checked), `replica.py`
     unchanged. Where it differs from the plan or adds to it:
     - **Which indexes:** `rangePlan` sorts every index of the table into
       `ixs` (leads with the key columns the range uses: cut by range as in
       stage 4) or `slow` (any other: another column, an expression, one
       that is too short). Nothing refuses on an index any more. The whole
       table (no WHERE) still has every index in `ixs`.
     - **`delEntries(st, txn, t, lo, hi, slow)`:** scans the main tree's
       `[lo, hi)` with `scanPart` in batches of `BATCH` (256) rows, so
       the rows are not held, builds each row with `rowOf` from only the
       columns the slow indexes use (`need`: their columns, their
       expressions' and predicates' column names, as `delNarrow` does; a
       large value is read whole only when one of them names it), and for
       each slow index deletes `idxEntry(row, key)` when `inIndex` holds, as
       `delRow` does (the key is the tree's own key, the same as `keyOf`).
       It returns the rows read. The scan goes through the transaction's own
       view (own writes, `Txn.cuts`), so the rows read are exactly the rows
       the statement deletes, whatever the transaction did before: no
       `countView`, and no `COUNT_OWN_MAX` fallback for such a table. The
       batches are read before their deletes are made (a scan is not
       resumed after a write to the transaction). Then `delRange` of the
       table and of the indexes in `ixs`, as before. A statement that finds
       no row writes nothing. The deletes of the index entries are the
       memory the row path holds too (one write each, in the transaction);
       the rows themselves are not.
     - **The same contents as the row path:** unique indexes: the entry of a
       deleted row is deleted, so a re-insert of the same value in the same
       transaction passes `checkUnique` (a put after a delete, own-write
       view). NULLs in a unique index have entries and are deleted the same
       way. A filtered index's entries are deleted for the rows its
       predicate holds for (`inIndex`; deleting the entry of a row it does
       not hold would be a harmless extra delete, but the predicate may
       evaluate an expression that errors).
     - **EXPLAIN:** `range delete: primary key range, subtrees dropped (1 of
       3 indexes cut by range, 2 entry by entry)`; no indexes, no
       parenthesis.
     - **Not changed:** `SET lexdb_range_delete = off` gives the row path
       (tested for every shape); a table others reference falls back (D3-a).
     - **Found and fixed, in the store (stage 1/5):** two range deletes of
       one tree in one commit, the first starting at the tree's beginning,
       on a tree with large values (a companion tree) panicked at apply
       ("range delete's companion not in memory"). `applyRange` finds the key
       lengths of the companion's chunks by skipping from length to length
       (`chunkLens`); after the first range had emptied the leftmost leaf,
       the skip went to the separator's side, passing a node the plan
       (`writeNeeds`) had not loaded. A block with two range deletes
       (stage 5) on such a table hit it. `writeNeeds` now keeps the lengths
       it found (`Db.ovfLens`, per companion tree, as u16s: the map holds
       copy types), and `applyRange` goes by those when its own walk cannot
       finish; they are a superset of the lengths with chunks in the range
       (earlier writes only remove chunks there). Test: `exec_rangedel`'s
       "block: two range deletes, large values", and the big family of
       `exec_rangedel_ix`.
     - **Tests (`exec_rangedel_ix`):** each shape on and off on identical
       tables: tags, rows, `treeDump` (count and a hash of every entry of
       the table's tree and of each index's), 12 pairs of queries (served
       by an index, and by a scan), the audit, EXPLAIN's text and the path
       taken. Families: one index; several (single, two-column with the key
       not first, a text one); unique (with NULLs); expression; partial
       (and a partial unique); two-column; a two-column key with indexes
       (b), (b, a), (a), (a, b, v) for ranges on a; large values (an
       expression over the large column, read whole); everything on one
       table with the key's own indexes too. Statements: `<`, between, `>=`,
       several in a row, delete then re-insert of the very values, the whole
       table, a residual (row path), and blocks: own writes before (inserts,
       updates of indexed columns, deletes), a re-insert of a deleted unique
       value in the same block, earlier range deletes, savepoints,
       ROLLBACK, a table made in the block.
     - **Planted bugs, all caught:** an expression index's entries not
       deleted (trees differ and the pair of queries disagrees); a filtered
       index skipped (trees differ); the unique indexes skipped (trees
       differ, with the row path's re-insert passing where this fails); the
       count one short after a batch (tags differ).
     - **Crash:** the crash client's `ev` has two secondary indexes
       (`worker`, and `worker where id % 2 = 0`); the check compares the
       counts through each with the rows.
     - **For stage 8:** the batch loop of `WITH (batch_rows n)` can use
       `delEntries` as it is on a key range: it already reads in batches and
       holds no rows; its writes (one per index entry) are what a batch
       bounds.
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
   - **As built (2026-11-14).** Parser: `batchOpt` (`lexdb_sql.lxl`),
     after RETURNING at the end of `update` and `delete`; the option lands
     in `Stmt.copy.batchRows`, COPY's own field, so the session's no-retry
     rule for COPY (a batched statement is not run again whole on a 40001)
     now reads `stmt.copy.batchRows > 0` for any kind. Executor
     (`lexdb_exec.lxl`): `batchDml` (the loop), `Win` (one batch's state),
     `deleteB` and `updateB` (the old `delete` and `update`, which call them
     with `n = 0` or hand over to `batchDml`), `Run.after` and `afterScans`,
     `freshTxn`, `winEnd`. Tests: new `exec_batchdml` (18 lines of output),
     about 2 s. Where it differs from the plan or adds to it:
     - **Syntax, all three doors:** `DELETE ... [WHERE ...] WITH (batch_rows
       n)` and `UPDATE ... SET ... [WHERE ...] WITH (batch_rows n)`. The
       three doors share the statement parser, so T-SQL and Oracle take the
       same suffix. In T-SQL `tableHints` leaves `WITH (batch_rows` alone, so
       `DELETE FROM t WITH (batch_rows 3)` is not read as a table hint. With
       RETURNING (or T-SQL's OUTPUT) the suffix goes after it, and is refused.
     - **The batch:** the statement runs with its callback stopping at n
       rows found (the scan's own read-ahead batch is 256 rows, so up to 255
       rows past the nth are read and read again by the next batch); the rows
       are changed, `fkFinish` runs, and the batch commits on a new `Txn`
       (`freshTxn`: path, session, temporary schema, `now()`, and also the
       zone, `rules` and `memMax`, which COPY's loop lost; COPY now uses
       `freshTxn` too). The statement's last batch is committed by the loop
       as well, so a conflict there is retried like the others. The tag is
       the total.
     - **Where the next batch starts:** `Run.after`, the key after the last
       row of the batch (`after(key)`), applied by `afterScans` to the first
       level's primary key scans (in `runLevel` and in `bLevelPlan`, the
       batched reader): points before it are dropped, ranges start at it,
       the whole table becomes a range. DELETE read by the primary key (no
       index path, not backward) uses it; DELETE read by an index runs again
       with no cursor, as the design says. UPDATE always reads by the key:
       an index or backward path is replaced by the key's full scan before
       `prepare`, and the WHERE stays as conditions. The reads of a sparse
       predicate are about one pass over the table in all.
     - **The range path:** only the first batch may take it
       (`rangeDelete` with `noSlow`): one write, atomic, `batch_rows`
       ignored. A range delete that has indexes whose entries go one by one
       (stage 6, `slow`) is not taken in a batched statement: those entries
       are as many writes as rows, so the memory argument does not hold; the
       row path in batches takes it.
     - **Refusals:** in a block 25001; RETURNING or OUTPUT 0A000; UPDATE
       that assigns a primary key column 0A000; n below 1 or not a number
       22023 or 42601 (parse). Added: USING or FROM 0A000 (a joined row has
       no key to resume from, and the join order may not read the target
       first), and T-SQL's TOP 0A000 (a limit of its own).
     - **Failure:** the error is the batch's, with `context` set (or
       appended to) as `DELETE with batch_rows 3: 6 rows committed before
       the error`; rows of the failed batch are rolled back, those of the
       batches before it stay. A conflict found as the batch ran (an old
       read of the live tree) or at its commit runs that batch again on a new
       transaction; the tenth in a row is the error.
     - **Memory:** `rs.held` and the callback's `held` are per batch, so
       `max_statement_mem` bounds a batch: a DELETE of 4,000 rows of 500
       bytes fails with 53200 under 512 kB, and passes in batches of 100.
     - **Tests (`exec_batchdml`):** 10 rows in 4 batches and 9 in 4 (the
       last finds none); the range path (no batches, one range delete) and
       the same with an index (batches); UPDATE with the WHERE on the changed
       column (exactly once), with an index on it, a two-column key, and a
       change that moves the row past the index; a foreign key failing in
       the third batch (6 rows kept, context), a division by zero in the
       third batch of an UPDATE; the refusals; a sparse predicate over
       20,000 rows (20,384 rows read, the pass and one scan batch per
       batch); a DELETE by an index; `max_statement_mem`; a writer between a
       batch and its commit (`setBatchHook`: the batch runs again); the
       suffix in Oracle's parser (run) and T-SQL's (parsed, TOP refused).
     - **Planted bugs, all caught:** the cursor kept at the last key instead
       of after it (rows updated twice: tags and counts differ); a conflict
       that advanced the cursor (a batch's rows skipped); the batch aborted
       instead of committed, an UPDATE read by the planner's index path, no
       cursor for UPDATE (these three loop for ever, so the test times out).
     - **Not covered:** a table others reference by foreign key falls to
       the row path in batches as before (cascades run per batch); rows
       committed behind the cursor by others are not seen; EXPLAIN is not changed for a
       batched statement (not tested).
9. **Measure (section 6), then write it up in `lexdb.md`** as a new 9.x
   section, and update gaps 2.4 and 2.5.
   - **As built (2026-11-14):** items 1 to 5 of section 6 were run and
     written up as `lexdb.md` 9.129; gaps 2.4 and 2.5 are updated. Changes
     to the plan: cold runs drop the data file and the logs from the OS
     cache with `posix_fadvise` (no root), as well as starting a server;
     PostgreSQL was measured warm only; "checkpoints until `dropped` is
     empty" is 1 in every run (the checkpoint at shutdown; the online
     checkpoint's own time was not separated); item 3's inserter is one
     client at 100 inserts a second; item 4 times a marker row's
     appearing on the replica after the purge's commit. The 10M-row table
     is 765 MB in lexdb (the design said about 1 GB). No bug found.

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

Expected ([estimate], from before the measurements): a warm range delete
commits in milliseconds, as a drop does (9.32: 1.5 to 13 ms for 105 MB). A
cold one is bounded by reading the covered leaves for the count (D1).

**Measured (9.129):** as expected. Warm, 3 to 5 ms for 1%, 10% and 50% of
a 1M-row table (the row path 21, 173 and 852 ms; PostgreSQL's DELETE 4, 34
and 158 ms, VACUUM 1, 10 and 28 ms). Cold, 3, 13 and 47 ms: the count's
read of the leaf headers, about 100 ns a row. The purge of 5M of 10M rows:
496 ms and 37 MB (row path 6.9 s and 4.4 GB; PostgreSQL DELETE 1.9 s plus
VACUUM 1.1 s; partitions dropped 90 ms). A tail inserter waited at most 24
ms (4.2 to 4.7 s with the switch off); a replica applied it in 3 to 4 ms
(2.7 s for 5M row records); `batch_rows 100000`: 7.0 s and 712 MB against
7.8 s and 4,990 MB.

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
