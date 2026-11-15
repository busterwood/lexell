# lexdb: deferred refactor work

Status: 2026-11-15, branch `arch/deep-modules-2`, based on `273b8229`.
This note records the refactor work we deliberately did **not** take on
now. It is the design we had reached, kept so it does not have to be
re-derived. Nothing here is a promise to implement it.

## Scope of this branch

Agreed, in this order:

1. **Dialect boundary (option B).** Move `catSnap` into `lexdb_catalog`
   behind a small `Naming` interface; move TDS/TNS describe into
   `lexdb_tds`/`lexdb_tns`; keep the connection-time `Dialect` record
   small (function dispatch, auth hooks). Do not build an 80-function
   facade. Success: `tests/lexdb/imports.py` has no core→dialect
   exception and catalog output is byte-identical.
2. **Parser split.** `lexdb_sql` stays the language model (values, types,
   expressions, column and statement representation, naming and
   formatting helpers); `lexdb_parse` owns tokens, grammar and
   dialect-specific parsing. `lexdb_sql` stops importing
   `lexdb_dialect`. Catalog's `tabTypeCols` parser call is replaced by
   storing the parsed `[]ColDef` on `TabType` at `CREATE TYPE`.
4. **Catalog seam, staged.**
   - 4a: catalog codec and readers (`encTable`/`decTable`, `findTable`,
     `seenTables`, sequence/enum/type readers, temp keys, `CatSnap`).
   - 4b: DDL behind `lookup / define / alter / drop`, with exec
     translating statements into semantic catalog changes.
   - 4c: opaque `Table`/`Index` mutation and semantic `CatErr` mapped to
     dialect errors by exec.
   `ANALYZE`/`VACUUM` data scans and leaf rewrites stay out of catalog.
5. **Planner (option A).** `lexdb_plan` owns the plan types (`Query`,
   `Level`, `Sel`, `Path`, `SubPlan`, `Est`, `WinPlan`, `MrPlan`,
   `OutCol`, `SelLock`) and the decision logic (`choosePath`, `pathFig`,
   `costOrder`, `wayCands`, statistics estimates, `EXPLAIN`). Exec
   executes the shared representation. SELECT planning only; DML
   planning, T-SQL batches and PL/SQL execution stay where they are.

Explicitly out of scope: point 3 (storage seam), point 6 (executor),
point 7 (continuous cleanup), and planner option B.

## Deferred: 3. storage seam

Highest-risk phase and the one the owner was least comfortable with. Do
not start it as part of the current branch.

### 3a. `ReadView`

`st.fo` is now entirely inside `lexdb_store` (25 references, none in
exec), so this is a store-internal consolidation rather than an
exec-wide rewrite. Today the store branches live/snapshot/follower at
each read operation (`getBaseIn`, `countRange`, `noteRange`, `scan`,
`scanLeaves`, `snapGet`, follower paths). Target: one selection point at
statement or scan construction; a `Scan`/`Reader` that holds the choice
and yields `Entry` or `LeafView` batches; point reads select once, not
per row; the follower merges base + delta into the same batch decoder as
the master. No virtual dispatch per row and no `Node` above store.

### 3b. `Txn`

`Txn` has 33 fields, about a third of them SQL-session state (`path`,
`sess`, `rules`, `memMax`, `now`, `zone`, `pending`, deferred
constraints, temp/on-commit state) that the store does not read. Take
the small step first: one opaque `sql: Option[SqlTxn]` payload with
accessors, so store carries but never inspects it. Test: store code must
never read `txn.sql`. Only introduce an `ExecTxn` wrapper (store calls
take `&e.txn`, exec calls take `&e`) if the payload starts attracting
behavior.

### 3c. `ckptLocked`

Four references. It is the fallback when a cut's snapshot is cancelled
because the old-version budget is exhausted; it takes the checkpoint
whole under one `with` (correct, stop-the-world). Options: pin the cut's
snapshot; abandon and retry; reserve a cut budget; keep the fallback.
Instrument first — count cancellations and the write rate at which they
happen — then choose. Do not delete it on design grounds alone.

Gates when it resumes: `store_ckptcut`, `follow_basic`, `follow_covers`,
`exec_replica`, process-level `replica.py`, the 35-query A/B, an OLTP
update run.

## Deferred: 6. executor

Three separate branches, in order. Each changes hot loops; each needs
its own benchmark and expression/operator test pass.

### 6a. `ExecStrategy`

`rs.batch` is a four-subsystem switch, not one strategy decision. Seven
sites at the time of writing (they will move):

- `Run.limit` copies it from `Limits`; sub-runs copy it from the parent;
- `winBatch` — window functions over batches;
- `batchLevel` — a level's scan/filter over batches, with the row path
  taking over from the batch's start on a bad value or per-row error;
- `outPlan` — the output projection;
- `sortBatches` — sort and DISTINCT over batches;
- `batchGroups` — grouping and aggregation over batches.

Target: one choice per plan or session (row, batch, chunk-of-one), made
once; operators do not consult a global flag; a test hook can force a
strategy. The row path can remain a legitimate strategy for point
lookups and small results instead of a forgotten fallback.

**Open decision, carried forward unanswered:** should the row strategy
remain a supported choice for point/small queries, or become test-only
once the chunk pipeline covers everything?

### 6b. One expression IR

Two engines today: `CX`/`cEval` for scalar/row evaluation and
`BNode`/`BGen`/`bEval` for batch/vector evaluation, with separate
compilation, type handling and error paths. Compile each `Expr` once
into one representation that can evaluate scalar and vector forms;
delete either `CX` or `BNode`/`BGen`, not both into a third parallel
system. The IR owns type coercion, NULL semantics, collation and error
mapping; exec owns when to evaluate. Do not extract a module until the
planner also needs type inference or constant folding.

### 6c. Chunked pipeline

Unify `Batch` and `[]Val` behind one `Chunk`: one hash table and join
build/probe, one comparator and sort keys, one output projection, one
COPY/result stream, one aggregate/window state. Port operators one at a
time, keeping the old implementation until the chunk version passes its
tests and does not regress. Row-only features (MATCH_RECOGNIZE, T-SQL
feedback, unusual set operations) may stay row-based behind
`ExecStrategy` until ported. The chunk representation belongs in
`lexdb_rows`, next to `Batch`/`Projection`; the operator flow stays in
exec.

Gates: `exec_batch*`, `exec_expr`, `exec_sort`, `exec_join*`,
`exec_window`, `exec_mr`, `exec_setop`, `exec_cols`, the 35-query A/B,
an OLTP point-select/update run, the full suite.

## Deferred: 7. continuous cleanup

- Shrink `Store` from 126 public functions toward ~20 operations:
  cursors/scans instead of `Node` callbacks; move test/admin hooks
  (`leafKinds`, `colCounts`, `upgradeCounts`, `audit`) out of the
  serving interface.
- Delete `setUpgradeBudget` and the upgrade queue (eleven references)
  and the row-leaf writer once `setColumns` is test-only.
- Add the fail-closed time-first guard.
- Decide whether `C_ANY` leaves should ever be re-encoded. Do not
  optimize it before measuring.
- Do not split `lexdb_exec` by line ranges; split it by the secrets it
  hides (plan, catalog, expressions, execution).

## Later options

- **Planner option B:** an opaque operator tree (`Scan`, `Filter`,
  `Join`, `Agg`, `Sort`, `Limit`, `Project`, `SetOp`, `Window`,
  `Match`) behind the same `plan()` call. Deferred because every `Sel`
  special case has to become an operator or a property of one and the
  tuned executor would have to re-prove its performance.
- **Session-level `Dialect` facade:** only if function dispatch and auth
  hooks justify more than the small connection-time record.
