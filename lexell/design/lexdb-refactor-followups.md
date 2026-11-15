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

## What landed on `arch/deep-modules-2`

- **Parser split (point 2): done.** `lexdb_parse` has the tokens,
  lexer, parser, T-SQL cursor and Oracle read mode; `lexdb_sql` is the
  language model and imports no dialect. A table type stores its columns,
  so the catalog never parses CREATE TABLE text.
- **Catalog (4a): codec, readers, snapshot and naming moved.** What
  remains from 4a is name resolution (`catKey`, temp keys, `createKey`)
  and the writers (`findTable`'s `setSpec` is exec's), because both still
  reach schema creation and store specs. `findTable` resolves the name in
  exec and then calls the catalog reader.
- **Planner (5): the data vocabulary moved.** `Path`, `Bound`, `Look`,
  `Cmp`, `EqClass`, `BindCol`, `WayCand`, `Way`, `Est`, `Common`, `Fig`
  and the cost constants are in `lexdb_plan`; `Query`/`Level`/`Sel`,
  `choosePath`, `pathFig`, `costOrder` and EXPLAIN are still in exec.
- **Dialect boundary (1): naming and the snapshot moved.** The seven
  exec→dialect imports remain.
- **Session memo moved out of Store.** `lexdb_memo.Memo` owns the map and
  its lock; `Store` carries a handle (`Store.memo`) and never reads a key.
  The three `memo*` methods left the Store interface (Store 118 → 115
  public functions).

## Remaining: 1. closing the dialect imports

The remaining edges are auth (`applyRoleOpts`), function dispatch
(`isDialectFn`/`callDialectFn`, `orafn.resultOid`), catalog rows
(`catRows`), catalog binding (`bindCatalog`), type describe
(`declOf`/`tableDecls`/`DescribeDecl`/`oraDecl`/`typPS`/`typScale`/
`outType`) and the PG catalog-function helpers (`callCat`, `callMisc`,
`sysCall`, `srfCols`, `regCast`, `enumOf`, `waitShape`, `createView`'s
relation checks).

The shape that closes them without moving thousands of lines:

1. Define a `Dialect` record in exec (the hook signatures use exec types
   such as `SeqEnv`, `Env` and `OutCol`), with one field per cluster:
   `naming`, `catalogRows`, `bindCatalog`, `srfCols`, `isFn`, `callFn`,
   `fnOid`, `authParse`, `authMake`, `authParseOra`, `authMakeOra`, and
   `describe`.
2. Build the union in a new **composition module** (`lexdb_server`) that
   imports exec and every dialect family. The import gate treats it as a
   protocol/composition module, not core. `lexdb_wire`, `lexdb_tds` and
   `lexdb_tns` already import exec; they import the composition module
   and pass the record to `newSession(st, dialect)`.
3. Move the T-SQL describe (`DeclCol`, `declOf`, `tableDecls`,
   `describeDecl`, tag helpers) into `lexdb_tds`, and the Oracle describe
   into `lexdb_tns`; the protocols call their own.
4. Keep `bindCatalog` in exec but split it: neutral lines
   (`u/U/R/A/p/T/n`) stay, the PG relation/index/view lines move to
   `lexdb_pg.bindCatalog`, `lexdb_syscat.bind` stays, and the hook calls
   both.
5. Delete `KNOWN_CORE_DIALECT` from `tests/lexdb/imports.py` and make the
   gate exact.

`Session` must carry the record; `newSession` grows a parameter and the
four call sites (wire, TDS twice, TNS) plus the two LXL generators supply
it. Function evaluation gets it through `Env`/`SeqEnv` for the paths that
can call a dialect function; paths with `seq: None` are constant folding
and do not.

## Remaining: 4. catalog DDL (4b/4c)

`encTable`/`decTable` and the readers are in catalog; the writers and
name resolution are not. The next cut is the DDL translation:

- Move `catKey`, `createKey`, `createSchema`, temp-key handling and
  `bumpCatalog`/`tmpBump` into catalog, behind a `Catalog` handle.
- Exec translates `CREATE/ALTER/DROP` statements into `TableDef` and
  semantic `Alter` values; catalog applies them and enforces dependency
  checks (FKs, views, owned sequences, indexes on dropped columns).
- Then make `Table`/`Index` mutation opaque and map `CatErr` to dialect
  errors in exec. `ANALYZE`/`VACUUM` data scans and leaf rewrites stay
  out of catalog.

## Remaining: 5. the planner's search and plan types

Moving `Query`/`Level`/`Sel` needs two things first:

- the value coercion (`coerce`/`coerceZ`/`coerceFloat`/`coerceTime`) and
  the index-key encoding (`encIdxPart` and its value encoder) in a core
  module that both plan and exec can use; today they are exec-local;
- a `Fold` record for the constant evaluator: `constVal` and `litValue`
  call `eval`, which cannot move. `Query` can carry `fold: Fold` so its
  methods call `q.fold.constVal`/`litValue` without threading a parameter
  through every signature.

Then the types and all their methods move together (LXL methods live with
their type), `choosePath`/`pathFig`/`costOrder`/`wayCands` follow, and
EXPLAIN moves with the plan. Fields are public while exec reads them.


## Deferred: 3. storage seam

Highest-risk phase and the one the owner was least comfortable with. Do
not start it as part of the current branch.

### 3a. `ReadView`

`st.fo` is now entirely inside `lexdb_store` (25 references, none in
exec), so this is a store-internal consolidation rather than an
exec-wide rewrite. **Started on `arch/deep-modules-2`:** `Store.viewOf`
returns `View.Live`, `View.Snap` or `View.Repl`, and `get`, `getMany`,
`warm`, `scan`, `scanBack`, `scanLeaves`, `countRange`, `noteRange` and
`liveStale` select once through it. Internal-only frame/CRC helpers are
private; `isSnapshot` and `Follower.applied` are deleted. Store exports
went 141 → 134 (lines/export 55.9 → 59.0).

What remains: the live and snapshot loops still branch on
`view == View.Snap` internally, and the scan family is five public
methods (`scan`, `scanPart`, `scanBack`, `scanBackPart`, `scanLeaves`).
The next cut is one reader over a `Sink` (entries or leaves) with
`back`/`part` options, so exec's scan call sites choose a mode instead of
a method. That is where the Store interface starts to shrink rather than
just select better.

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
