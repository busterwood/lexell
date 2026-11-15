# lexdb: the architecture we are consolidating toward

Status: 2026-11-15, branch `arch/deep-modules`, based on `04fa4b80`
(lexdb.md 9.136). This is the **current-state design**, not the
chronological record. [lexdb.md](lexdb.md) remains the record of how each
mechanism was measured and chosen; this note is the map we hold the code
to.

Progress (2026-11-15): the test tooling builds natively by default; the
`rs.batch` split and the `LEXDB_ROWFMT` removal are done; `lexdb_rows`
owns the leaf, fixed, tagged/long and column body codecs, `Projection`,
the batch decoders and `LeafView`. `page` imports `rows`, and the
`rows → page → rows` cycle is gone; `cols` is now below both. Exec imports
only `rows` and `store` for data. A replica or a range the transaction has
written now reaches the same batch decoder through synthetic leaves
(`scanLeavesMerged`), so the follower's scan is no longer row-at-a-time.
The universal column leaf, the old-format deletion, the rest of `ReadView`
and the dialect port remain.

## 1. Why this exists

The code is a successful performance research log. Each design section
added a path to test an idea; the winning idea stayed, but so did the
scaffolding of the losing one. Three forks now multiply:

- **Execution style:** interpreted row (`eval` / `tryRow` / `runLevel`),
  compiled row (`CX` / `cEval`), vector batch (`Batch` / `BNode` /
  `bEval`), and five hand-rolled batch drivers.
- **Storage layout:** tagged vs fixed row; `T_LEAF` / `T_FLEAF` /
  `T_CLEAF`; layout per row vs per table; row vs column leaf at rest;
  lazy vs loosened vs column leaf in memory.
- **Read view:** live tree, snapshot, follower. The follower is now
  base + delta with epochs and pushed frames (9.135).

A new type, operator or feature must be handled across the product. The
symptoms are visible: 17 row/batch representations, four expression IRs,
five batch drivers, six comparators, two hash tables, two COPY paths, and
`rs.batch` / `st.fo` acting as master switches.

The goal is not fewer mechanisms. It is **one implementation of each
mechanism, with an explicit policy at one seam.**

## 2. Principles

Parnas (1972): decompose by information hiding, not by flow of control.
Each module hides a design decision ("secret") likely to change; minimize
the knowledge each module has of the others.

Ousterhout (APoSD): deep modules with small interfaces; no information
leakage; pull complexity downwards; define errors out of existence;
different layer, different abstraction; strategic rather than tactical
programming.

One rule:

> Each module owns one decision likely to change, and exposes the smallest
> stable abstraction over it.

## 3. Modules

`lexdb_core` is the shared vocabulary, not a behavior module: `Val`,
`DbErr`, `TypeName`, `Stmt`, and the `Catalog` / `Plan` interfaces. Keep it
small; behavior belongs in the deep modules.

| Module | Secret it hides | Interface | Leak today |
|---|---|---|---|
| **`lexdb_store`** | How bytes become durable and visible: COW B+tree, slots, versions, snapshots, cache, log, checkpoint cut, free space, follower push/epochs | `open/begin/commit/abort`, `cursor/lookup/lookupMany/count`, `checkpoint/follow` | 12 read operations; `Node` callbacks; `st.fo` at many sites |
| **`lexdb_rows`** (new) | How a row is represented: fixed/tagged/column, layouts, overflow, conversion, projection | `Rows.of`, `encodeRow`, `decodeRow`, `encodeLeaf`, `decodeLeaf`, `convert`, one `Projection` | leaf, fixed, tagged/long, column body, batch decoders, `Spec` and `LeafView` moved; the lazy two-step orchestration stays in exec over `LeafView`; universal column leaf and old-format deletion remain |
| **`lexdb_catalog`** | Metadata, DDL, dependencies, temp objects | `lookup/define/alter/drop/list` | lives inside exec |
| **`lexdb_plan`** | Path search, join order, cost model, subquery strategy | `plan(catalog, stmt, params) -> Plan`, `explain` | `Sel`/`Query`/`Level`/`Path` leak into exec |
| **`lexdb_exec`** | Execution: vectorization, operators, sinks, fallback | `execute(plan, params, sink)`, `collect` | 1,381 functions; 17 representations |
| **`lexdb_pg`** | PG wire, `pg_catalog`/`information_schema`, auth, PG type/function names, error text | one `Dialect` facade | dialect code in exec; `lexdb_wire` / `lexdb_pgcat` / `lexdb_auth` |
| **`lexdb_mssql`** | T-SQL grammar/quirks, TDS, `sys.*`, T-SQL functions, temp-table semantics | one `Dialect` facade | `lexdb_tsql*` / `lexdb_tds` / `lexdb_sys*` |
| **`lexdb_oracle`** | PL/SQL, TNS, Oracle data dictionary, functions/types, error text | one `Dialect` facade | `lexdb_plsql` / `lexdb_tns` / `lexdb_ora*` |

`lexdb_page`, `lexdb_cols` and `lexdb_repl` are **internal** to Store,
Rows and the dialects. They are not public modules.

`lib/sqlserver` and `lib/tds` are the **client** libraries; they are not
the server's SQL Server dialect. The server dialect is `lexdb_mssql` /
`cmd/lexdb_tds`. Keep the dependency directions separate.

## 4. Dependencies

```
main
 ├── lexdb_pg ───────┐
 ├── lexdb_mssql ────┤
 └── lexdb_oracle ───┤
                     ▼
                lexdb_core
                 ├── lexdb_like    (simple LIKE pieces)
                 ├── lexdb_store   (page, repl internal)
                 ├── lexdb_rows    (cols, page internal)
                 ├── lexdb_catalog
                 ├── lexdb_plan
                 └── lexdb_exec
```

- Dialects depend on core; core **never** depends on a dialect.
- No dialect depends on another dialect.
- `main` composes them; a test checks the imports.
- The core's hot paths contain no dialect branch and no per-row flag.
- Current storage layering: `cols` (byte codec) ← `rows` ← `page`/`store`.
  `page` imports `rows` for column bodies and makes `LeafView` from a
  `Node`; exec imports `rows` and `store` only, never `page` or `cols`.
  `lexdb_like` is a small shared matcher below exec and rows.

## 5. Seams

A seam is where the alternative implementations meet one interface and one
selection point. The selection is at connection, statement, plan or leaf
granularity — never per row.

| Seam | Implementations | Selected at | Removes |
|---|---|---|---|
| **ReadView** | live tree, snapshot, follower | session / statement | `st.fo` branches; the replica batch-scan gap |
| **Rows / LeafCodec** | column table leaf, front-coded index/catalog leaf, overflow value | table / leaf | tagged/mixed-layout/row-leaf fallbacks; `LEXDB_COLUMNS`, `LEXDB_ROWFMT` |
| **ExecStrategy** | batch, chunk-of-one row, test-only old row | plan / session | `rs.batch` as a four-subsystem switch; five driver skeletons |
| **CostModel** | cost, rules as no-statistics fallback / test oracle | plan | `lexdb_planner` branches; two disagreeing cost models |
| **Dialect** | PG, MSSQL, Oracle | connection | dialect code in exec; core/dialect leakage |
| **Checkpoint** | cut (the path), locked (fallback to delete), pool (config) | store | `ckptLocked` / `CUT_TRIES` fallback; two checkpoint implementations |
| **Replication input** | pushed frames, log poll | follower | two apply paths; hides `Epoch`, `PushFrame` |

### ReadView is batch-level, not leaf-level

The master can scan a leaf in place; the follower cannot cheaply produce a
`Node`. `scanLeaves` returns `false` on a follower today, which is why
replica scans fall back to row-at-a-time and why 9.134 measured them 40×
slower than the master. The interface should yield decoded batches:

- master: `scanLeaves` in place, then `Rows.decodeLeaf` into a batch;
- follower: merge base pages and delta into a batch, then `Rows.decode`;
- executor: sees `nextBatch(projection)`, never `Node`.

This keeps the master's in-place optimization and gives the follower the
same batch path.

### Rows owns the leaf encoder

9.136 already factored the checkpoint's leaf encoding into the pure
function `encodeLeafK`. That is the `Rows.encodeLeaf(cutLeaf)` seam. The
store's cut/checkpoint calls it; `packedLeaf` / `adopt` stay internal to
the page layer. Extracting `Rows` now, while the cut code is fresh, is
cheaper than after it ossifies.

### Checkpoint: cut first, locked only while proving it

9.136 added a second checkpoint implementation: the cut, and the whole
checkpoint under one `with` (`ckptLocked`) after `CUT_TRIES` or a cancelled
snapshot. The target is one cut path with a retry; the locked path is a
fallback to delete once `store_ckptcut` (including the cancelled-snapshot
case) is proven. `CUT_POOL` is an opt-in encode experiment, not a module:
keep it behind the encoder seam and delete it if it does not win.

## 6. Performance kernels — do not cross

These are load-bearing. Refactors may move their call sites, not rewrite
their inner loops without a measured replacement.

- **Storage:** `descend` / `lastLeaf`, in-place `scanLeaves`, `loadAhead`,
  `getMany`, front-coded leaves, COW/versions, group commit and O_DSYNC.
- **Checkpoint:** the cut, `encodeLeafK`, `cutPages`, page runs.
- **Decode:** `bRunInto`, `cRunInto`, `bRunCols`, `cCols`, `fillPickIn`,
  `bRowInto`.
- **Indexes:** `fillIdxOnly`, `bIdxInto`, `fillIdxRows`, `bLookup`.
- **Joins:** `bJoinAll`, `bProbe`, `bJoinTail`.
- **Sort/aggregate:** `skSort` / radix / top-N, `bAccum`.
- **Output:** `outPlan` / `OutBatch`, `dataBatch`, PG/TDS/TNS encoders.

The interfaces are at leaf, batch or statement granularity, so the kernels
stay inside a module and the caller pays one dispatch, not one per value.

## 7. Invariants

1. One serving implementation per decision; alternates are test-only or an
   old binary used as the A/B control.
2. No dialect branch in `tryRow`, `runLevel`, `bEval`, `bRunInto`,
   `cRunInto`, `bJoinAll`, `skSort`, or the store's read/write paths.
3. No per-row flag check. Selection is at connection / plan / leaf.
4. `Node`, `CkCut`, `Epoch` and `PushFrame` do not cross the Store/Rows
   boundary; `Rows`, `Projection`, `Batch` and `LeafView` are the boundary.
5. Public types are opaque handles; interfaces are at batch / leaf /
   statement granularity.
6. Every runtime flag has a named seam and a deletion phase.
7. The correctness oracle lives outside the serving build: PostgreSQL and
   an old binary, not a second engine in production.

## 8. Phases

0. **Architecture and inventory** (this branch). No code changes.
1. **Dead switches and the `rs.batch` split.** `LEXDB_ROWFMT`, dead test
   hooks. Done on this branch. The format deletions wait for Rows, so the
   old-format fixtures are retargeted once. Split `rs.batch`: compiled
   expressions and typed sort always on; the flag controls vector scans only.
2. **Rows / codec.** Progress: `encodeLeaf`, the fixed row codec, the
   tagged/long row codec, `encodeRowOf`, the column body codec, `Projection`,
   the batch decoders and `Spec` are moved; `LeafView` is the page-to-codec
   adapter. `page` imports `rows`, and `cols` is below both. Exec keeps thin
   adapters, `rowOf`/`placesOf` (large-value I/O), table metadata and the
   lazy two-step orchestration over `LeafView`; it imports only `rows` and
   `store`. Next: the universal column leaf, one layout per leaf, overflow
   for long/odd values (`C_ANY` / `C_STUB`), and the deletion of `T_LEAF`,
   the old layout compatibility, the tagged-row general form and
   mixed-layout leaves.
3. **ReadView, batch-level.** Live/snapshot/follower; master in-place and
   follower base+delta; replica batch scans. Progress: `scanLeaves` yields
   `LeafView`; a replica or own-write range is gathered by `scanPart` into
   synthetic leaves (`scanLeavesMerged`) and decoded by the same
   `decodeRun`/`decodeRow` path. Next: one `ReadView` selection over the
   remaining `st.fo` branches, and the follower's apply paths.
4. **Checkpoint unification.** Cut-only; delete `ckptLocked`; decide
   `CUT_POOL`.
5. **Dialect port.** PG first, then MSSQL and Oracle. Normalise syntax into
   the common plan; no dialect branches in exec.
6. **ExecStrategy / one batch driver.** Sink and fallback policies; one
   `BPlan` builder; compiled expressions and typed sort always on.
7. **One expression IR.** Scalar and vector backends; delete `BNode` /
   `Gen` / duplicate type and error logic.
8. **Chunked pipeline.** One `Chunk`; one hash table, comparator, output
   projection and COPY; the row path becomes chunk-of-one or test-only.
9. **Planner and module split.** One cost model; `Plan` opaque; split the
   catalog/plan/exec remains only if the interfaces earn it.

Phases 2 and 3 are designed together; implement Rows first. Phase 5 can run
in parallel once the port is stable. Phases 6–8 are sequential.

## 9. Gates

Tests build natively by default; `LXL_CC=1` opts into the C-backed compile
cache when a C build is wanted. The machine is shared with benchmarks, so
gates are targeted and interleaved:

- storage: `store_ckptcut`, `follow_basic`, `follow_covers`,
  `exec_replica`, `replica.py`;
- execution: `exec_batchjoin`, `exec_batchsort`, `exec_batchexpr`,
  `exec_batchindex`;
- correctness: PostgreSQL and the old binary;
- performance: `bench.py`, `qL.txt`, point selects, updates, loads, replica
  scans. Stop on a regression beyond the phase's noise threshold (5%).

A full suite, crash test or replica run is a milestone gate, not every
commit, while background benchmarks are running.

## 10. Change locality

| Likely change | Today touches | Target |
|---|---|---|
| Physical row format | exec, cols, page, store, tests | `lexdb_rows` |
| Read view | store (many sites), exec fallback | `lexdb_store` |
| New operator | plan, row exec, batch exec, sort/agg, tests | `lexdb_exec` |
| Cost model | `choosePath`, `pathFig`, `costOrder`, `wayCands` | `lexdb_plan` |
| New PG catalog view | exec + `lexdb_pgcat` | `lexdb_pg` |
| New T-SQL function | exec + `lexdb_tsqlfn` | `lexdb_mssql` |
| Checkpoint change | store/page/cols | `lexdb_store` + `lexdb_rows` |

## 11. Open decisions

- Is `SET lexdb_batch=off` still user-facing, or test-only after the split?
- Universal column leaves, or an explicit per-table row option for
  point-read-heavy tables?
- Is `CUT_POOL` worth keeping after the encode is tunable?
- Does `lexdb_catalog` earn its own module, or does it live inside Plan/Exec?
- How much of the `Dialect` facade is needed before Oracle/Postgres
  differences stop being normalisable?
- Do we keep the SQL Server client (`lib/sqlserver` / `lib/tds`) on a
  separate dependency line from the server dialect? (Yes, but state it.)
