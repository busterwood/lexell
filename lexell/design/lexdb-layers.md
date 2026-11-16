# lexdb: the layered redesign

Status: 2026-11-16, design only, based on main `f629bc6c`. Nothing here is
implemented.

This note builds on [lexdb-architecture.md](lexdb-architecture.md) and
[lexdb-refactor-followups.md](lexdb-refactor-followups.md) and keeps their
principles, performance kernels (section 6 there), invariants (section 7)
and gates. It replaces their executor and planner phases (architecture 6–9,
followups "6. executor" and "Planner option B"): the operator tree that was
deferred there is taken here. It also adds two layers the earlier notes did
not have: an **access layer** between the store and the executor, and a
**binder** between the parser and the planner.

## 1. Why now

The TPC-H work (lexdb-tpch-perf.md) took lexdb from 3.77× to 2.48× PostgreSQL
on one core, and q3, q5 and q19 have improved a lot since. The way it got
there shows the limits of the current shape:

- **Most of the week's wrong results were binding bugs:**
  - IN (subquery) across number and time types;
  - derived columns typed from a union's first branch;
  - char(n) collation;
  - hash-key types that differed between the row path and the batch path;
  - EXPLAIN counts after a batch gave way.

  None of them was a storage bug. They come from types being worked out in
  several places, at run time, and from two executors that must agree.
- **The plan can only be left-deep.** A query is a chain of levels run as
  nested loops (`runLevel(k)` calls `runLevel(k+1)`). q21's bushy hash join,
  and most of what remains in q21 and q22, cannot be expressed directly.
- **Everything runs on one thread.** That is half the gap to PostgreSQL with
  4 processes (4.51×, against 2.48× on one core).
- **The executor is too big to change safely:**
  - `lexdb_exec.lxl` is 33,372 lines;
  - about 11–12k of them execute queries, with join, aggregate and sort each
    implemented twice (row and batch) plus the give-way code between them;
  - three expression forms (`eval` over the AST, `CX`, `BNode`) must be
    fixed in step: the `#bppad` folding and char(n) collation each had to be.

## 2. Requirements

The workload is mixed, and every layer is judged against all of it:

| Workload | Needs | Where lexdb stands (benchmark record, lexdb-benchmarks.md) |
|---|---|---|
| Interactive and UI | Point selects and small joins with low, steady latency; cancellation; no stalls | Point selects 376–378k/s with 3 replicas at 32 clients (PG on 4 cores 386.6k). Commit max 8–11 ms since the checkpoint cut. |
| OLTP writes | Insert, update, delete one row; index maintenance; constraints; commit latency | Updates 1.5–2.6× PG; commits 3,843/s against 1,577 |
| Batch processes | Bulk insert and COPY; big UPDATE, DELETE and MERGE; long transactions | 1M narrow rows load in 0.55 s (PG 0.58); 10M in 5.32 s (PG 5.81) |
| Analytics | Scans, joins, aggregates, sorts over millions of rows; parallel | 35-query suite 0.78× PG one core; TPC-H 2.48× PG one core (94536d12) |
| Replicas | Same reads on followers, low lag | Lag p99 0.8–1.3 ms under load |
| Three dialects | PostgreSQL, T-SQL and Oracle over one core | In place; dialect boundary partly closed (architecture 5) |

What this says: **the storage engine and the write path are lexdb's
strength.** OLTP and bulk loads are level with or ahead of PostgreSQL.
Analytics over one table is ahead of it. The gap is joins, subqueries and
plan shape, which belong to the planner and executor. The redesign must not
give up the first to fix the second.

## 3. What leaks today

Measured on main `f629bc6c`:

- **The store's interface is wide and used in many places:**
  - 91 public functions, about 36 of them called from exec;
  - 403 references to `lexdb_store` in exec;
  - five scan methods (`scan`, `scanPart`, `scanBack`, `scanBackPart`,
    `scanLeaves`) plus `get`, `getPart`, `getMany`, `getUnnoted`.
- **"Tables, rows and indexes" has no module; it lives in exec:**
  - key encoding: `encPart`, `encIdxPart`, `keyOf`, `idxEntry`, `keyVal`,
    `succ`, and the NULL marker byte;
  - row reading: `rowOf`, `fetch`, `fillIdxRows`, and `LeafView` decoding in
    `bRange`;
  - index upkeep: 85 `txn.put`/`txn.del` calls in exec, at least 23 of them
    for index entries;
  - the executor therefore knows key bytes and leaf layout.
- **The transaction carries SQL state.** The store never reads `Txn.sql`,
  but exec reads `txn.sql.` 122 times. A store handle is doing the job of an
  executor context.
- **There is no bound, typed form of a query:**
  - `resolve` (exec:5137) rewrites names but returns the same `Expr`;
  - types are worked out on demand (`exprType`, `boundType`, `semiTypes`,
    the IN set's classes);
  - `eval` finds a column by comparing names (`colIndex`) every time it runs.
- **The plan is not a value of its own.** `Query`/`Level`/`Sel` mix what was
  decided (path, join order) with run-time state (`lv.est`, memo tables), and
  they live in exec. `lexdb_plan` holds only the vocabulary.

## 4. The layer stack

Each layer owns one decision likely to change, and depends only on the
layers below it.

```
 8  Protocols and dialects   pg wire, TDS, TNS; dialect facades; auth
 7  Statements and sessions  DDL, DML, transactions, PL/SQL, T-SQL batches, COPY
 6  Executor                 operators in push pipelines over Chunks; one expression evaluator
 5  Optimizer                logical plan -> physical operator tree; cost model; statistics
 4  Binder                   parse tree -> bound, typed logical plan; the expression IR
 3  Catalog                  tables, indexes, types, constraints, views, privileges
 2  Access                   relations: rows, keys, indexes, scans, fetches, writes
 1  Storage engine           byte-keyed COW B+trees, versions, snapshots, WAL, checkpoint, followers
```

`lexdb_rows` (row and leaf codecs, `Batch`, `Projection`) stays where
architecture.md put it: the codec shared by layers 1 and 2. `lexdb_sql`
(values, types, the parse tree) is the vocabulary for layers 3–8.

### 4.1 Layer 1, storage engine (`lexdb_store`)

**Secret:** how bytes become durable and visible.

Kept as it is inside: the COW B+tree, column leaves, front-coded index
leaves, group commit with O_DSYNC, the checkpoint cut, snapshots and the
follower. These are the performance kernels in architecture.md section 6.

Interface target, about 20 operations:

```
open / close / checkpoint / follow
begin(view) -> Txn            // view: live, snapshot or replica, chosen once (ReadView)
commit / abort / savepoint / rollbackTo
get(tree, key) / getMany(tree, sorted keys, sink)
read(tree, lo, hi, opts{back, part}, sink)   // one scan, entries or leaves
put / del / delRange(tree, ...)
createTree / dropTree / lockRow / waitDurable
```

Changes:

- `Txn.sql` leaves the store. The executor's context holds the store `Txn`,
  not the other way round.
- The five scan methods become one `read` with options, as followups 3a
  proposed.
- Test and admin hooks move off the serving interface.
- Your storage duplication list stays inside this layer and can run as its
  own workstream at any time (followups 3a–3c, memory "Store cleanup
  deferred"):
  - seven `descend` implementations;
  - three meta-page readers;
  - two frame loops;
  - the follower's re-implemented read path.

### 4.2 Layer 2, access (new: `lexdb_access`)

**Secret:** how a relation is laid out in trees. That covers the primary
key's encoding, the clustered rows, the secondary index entries, the hidden
row id of a table without a primary key, large values stored apart, and
column leaves.

This is the missing layer, and it is where a format change would be
contained (section 5).

```
type Rel        // an open table: its trees, codecs, index set
type Bounds     // per key column: equal, or a lo/hi with inclusivity; NULLs in or out
type Want       // the columns needed (a Projection) and simple filters to push down

scan(rel, path, bounds, want, sink: fn(&Chunk))           // table or index, in key order
fetch(rel, keys: &Chunk, want, sink)                      // by primary key, batched and sorted
lookup(rel, index, keys: &Chunk, bounds, want, sink)      // many prefixes at once (today's bRange)
count(rel, path, bounds)                                  // for the planner
insert(rel, rows: &Chunk) / update(rel, keys, set) / delete(rel, keys)
                                                          // keeps every index; returns conflicts
```

What moves in:

- from exec: `encPart`, `encIdxPart`, `keyOf`, `idxEntry`, `keyVal`, `succ`,
  `pathScan` (bounds to key ranges), `fetch`, `rowOf`, `fillIdxRows`, the
  leaf-reading half of `bRange`/`fillLevel`, and index upkeep from
  `insertRows`, `delRow` and the UPDATE paths;
- from the store: `putRow`/`putRowLoad`, `setColSpec`, `upgradeTree`.

After this step nothing above layer 2 sees a key byte, a leaf or a tree.

Two properties make this the right seam for the mixed workload:

- **Batched by default, cheap for one row.** `fetch` with a chunk of one row
  is a point read; with 1,024 rows it is today's sorted `getMany`. Point
  selects and q20's fetches go through the same code.
- **Writes keep indexes in one place.** INSERT, UPDATE, DELETE, MERGE, COPY,
  ON CONFLICT and range delete all reach indexes through `insert`, `update`
  and `delete`. Today each of these does its own index upkeep.

#### 4.2.1 As built: the read side (step 1a, 1b)

Status: 2026-11-16, branch `redesign/access`. The read side is in
`lexdb_access`; the write side (index upkeep) and `ExecTxn` are not yet.

**Where it sits.** `lexdb_access` imports `lexdb_store`, `lexdb_rows`,
`lexdb_sql`, `lexdb_base`, `lexdb_time`, `lexdb_sqlcoll`, `lexdb_like` and
`lexdb_vec`; `lexdb_catalog`, `lexdb_plan` and `lexdb_exec` import it. The
import gate (tests/lexdb/imports.py) checks both directions.

Because access is below the catalog it cannot see `Table`. So:

- `Index` (tree, parts, expressions, predicate, and the catalog's
  presentation fields) moved to `lexdb_access`; `lexdb_catalog.Index` is an
  alias.
- `Rel` is a value record of borrows of a `Table`'s layout fields (name,
  tree, columns, primary key, indexes, slots, width, layouts), made by
  `lexdb_catalog.relOf(t)` per call. It copies nothing, like
  `lexdb_rows.Rows`.

**Interface.**

```
type Rel; type Index; type Scan; type Cursor; type Tail
type IdxDec; type IxRead; type Lazy; type Bar; type Picked
type RowRead; type Probes; type Fetched; type Ranged

// ranges, from bound values (exec evaluates and coerces; keyVal stays there)
noScan() / wholeScan() / allScan(): Scan
rangeScan(rel, ix, eqs: &[]Val, los: &[]Val, his: &[]Val, noNulls): Scan
inScans(rel, ix, eqs, vals, desc): []Scan
prefixScan(rel, ix, row, n): Scan                    // a foreign key's lookup
tailOf(ix, los, his, capNulls): Tail                 // a join's bounds, made once
afterScans(scans, from): []Scan; sameRange(a, b); newCursor()

// rows
rowRead(rel, need): RowRead; getRow(st, txn, rel, rr, key): Option[[]Val]
fetch(st, txn, rel, ix, desc, sc, need, cur, out: mut &[][]Val)
rowOf(st, txn, rel, key, v, n, need, missing)        // a stored value decoded (large values read whole)

// batches
idxDecOf(rel, ix, needCol): Option[IdxDec]           // index-only reads
fillLevel(st, txn, rel, rd: &IxRead, sc, part, cur, bp): Option[Batch]
fillPickIn(st, txn, rel, sc, part, cur, bp, rd, lz: &Lazy,
           narrow: &fn(skip, &Batch, idx): Option[[]int], bar, spare): Option[Picked]
probes(ix, n): Probes; p.part(v) / p.intKey(x) / p.again() / p.end() / p.clear()
fetchMany(st, txn, rel, pr, part, bp): Option[Fetched]            // bLookup's reads
rangeMany(st, txn, rel, ix, pr, tail, noRange, one, bp, part,
          room, perRow): Option[Ranged]                           // bRange's reads

// counts and the rest
countRows(st, txn, rel, most); countEntries(st, txn, rel, ix, sc, cur, n, lim, keep, keys)
pages(st, rel); rowCount(st, txn, rel); warmPoints(st, txn, rel, scans)
keyOf(rel, row): str                                 // a row's identity (locks, rows changed)
encKeyPart / encIdxPart / encNum / floatKey / collKeyVal / ciKey / padKey
fixedRows / layoutRows / leafKinds / treeDump        // test hooks
```

**What differs from the sketch above.**

- *Bounds are values, not expressions.* Exec still evaluates a path's
  values and makes them the column's type (`keyVal`, `coerceZ`); that is
  the binder's work (layer 4). Access only turns bound values into key
  ranges.
- *Filters are a closure, not a `Want`.* The two-step decode (9.108)
  needs the level's conditions between its two steps. They reach access as
  `narrow`, a closure over exec's `bNarrow`, called once per run of rows.
  A raw LIKE's pattern pieces travel in `Lazy`. After step 2 the closure
  is over the expression IR's vector evaluator; nothing in access changes.
- *Lookups are made a part at a time.* `Probes` keeps a batch's keys
  opaque without a `[]Val` per row; `fetchMany` and `rangeMany` sort,
  deduplicate, read and decode them. `rangeMany` takes the statement's
  memory room as two numbers, so the budget stays the executor's.
- *Exec keeps the value encoding for in-memory keys.* Groups, hash joins,
  partitions, DISTINCT and ANALYZE's sketches use `encIdxPart` as an
  order-preserving codec. Exec reaches it through thin wrappers. It could
  become a codec of its own (in `lexdb_rows` or `lexdb_vec`) if keys held
  in memory and keys on disk ever need to differ.
- *Collation keys moved too.* `ciKey`/`padKey` make the bytes a
  collated text's key holds, so they are in access. Exec keeps wrappers
  for its comparisons.
- `radixPerm` moved to `lexdb_vec`: both the sort and `sortKeysPerm` use
  it.

**Gate (step 1b against main `ae3e370a`, both built the same session).**
Suite 184 passed. TPC-H SF1, 3 runs each: all 22 checksums equal the
`1744ef99` baseline's; median wall time per query within 0.980–1.020 of
main's, geometric mean 1.004, total 31.36 s against 31.29 s. OLTP (vspg,
lexdb only, 3 rounds of 10 s, medians): point selects 82.2k/135.8k/131.0k
tps at 1/8/32 clients against 83.1k/137.5k/132.5k (about 1% lower,
server CPU per select 1% higher); updates 3,822/18,198/41,131 against
3,830/18,192/40,602; the five aggregates equal. Loads: 1M-row INSERT ...
SELECT 1.21 s and 2.43 s against 1.17 s and 2.38 s (one run each); COPY
narrow 0.51 s both, wide with two indexes 7.07 s both.

**Still in exec after step 1b:**

- index upkeep and the writes (`insertRows`, `storeRow`, `updRow`,
  `delRow`, `conflictOf`, `checkUnique`, `changeIndexes`, `fillIndex`,
  `rewrite`, `rangeDelete`/`delEntries`, `fastCopyRow`, `idxPrefix`/
  `idxVal`, `parentHas`), with their `txn.put`/`txn.del`/`putRow` calls;
- `Txn.sql` (`ExecTxn` not made yet);
- catalog trees, read and written directly (`CATALOG`, sequences, roles,
  ACLs), and `relSize`, which counts pages by tree number from the catalog
  lines.

### 4.3 Layer 3, catalog (`lexdb_catalog`)

Already half done (architecture 5, followups 4).

- Remaining: name resolution (`findTable`, `catKey`, temp keys) and DDL
  behind `lookup / define / alter / drop`.
- The catalog hands out `Rel` handles from layer 2; it does not encode rows.

### 4.4 Layer 4, binder (new: `lexdb_bind`)

**Secret:** what a query means.

- **In:** a parse tree and a catalog snapshot.
- **Out:** a bound logical plan, a tree of relational operators. Each output
  column has a slot, a type (with typmod and collation) and nullability.
  Every expression is in the **typed expression IR**.

What it decides once, in one place:

- name and scope resolution, including correlation and lateral references;
- types and implicit casts, for each dialect. A union's or CASE's column type
  comes from all its branches. `IN` and `= ANY` compare the way `=` does.
- collation;
- functions and operators, by signature;
- constant folding (`#bppad` and the like);
- star expansion, GROUP BY and ORDER BY resolution, views, CTEs.

The expression IR replaces `eval` over the AST, `CX` and `BNode`. Each node
has its operator already chosen (no string dispatch at run time) and its
result type. Two evaluators are generated from one definition: scalar for
one row, vector over a `Chunk` with a selection vector. Errors and
short-circuits follow the selection vector, so `CASE WHEN x <> 0 THEN 1/x`
never divides for rows that take the other branch.

The dialect differences in typing are tables the dialect supplies. They are
not branches in the binder's code.

### 4.5 Layer 5, optimizer (`lexdb_plan`)

**In:** the bound logical plan. **Out:** a physical operator tree, which is
a value: it can be cached, shown by EXPLAIN, and holds no run-time state.

Steps:

1. **Rewrites:**
   - subquery unnesting: correlated subqueries become joins, semi-joins,
     anti-joins or mark joins (Neumann and Kemper 2015);
   - predicate pushdown and the OR-derived filters (joinorder's orHull);
   - outer-to-inner join conversion;
   - constant folding.
2. **Join order and shape.** Today's cost model and statistics
   (`choosePath`, `pathFig`, `costOrder`, `wayCands`, ANALYZE samples) move
   here. The search widens from left-deep to bushy where cost says so.
3. **Physical choice:**
   - the access path: `scan`, `lookup` or `fetch` from layer 2;
   - the join operator: hash, index lookup, nested loop or merge;
   - hash aggregate or sorted aggregate;
   - top-N;
   - where pipelines break.

### 4.6 Layer 6, executor (`lexdb_exec`, much smaller)

**Secret:** how a physical plan runs.

**Chunk.** Today's `Batch` with a selection vector. It holds typed vectors
(int, bool, scaled decimal) and `Val` columns, and keeps its capacity across
uses. A single row is a chunk of one.

**Operators:**

| Group | Operators |
|---|---|
| Access | Scan, IndexLookup, Fetch (over layer 2) |
| Row-by-row | Filter, Project |
| Join | HashBuild; HashProbe (inner, left, right, full, semi, anti, mark); NestedLoop |
| Grouping and order | HashAgg, SortAgg, Sort, TopN, Distinct |
| Other | Window, Limit, SetOp, Values, CTE scan; MATCH_RECOGNIZE (row-based inside, one operator outside) |

**Pipelines.** The plan is cut where all input must be read first: a hash
build, an aggregate or a sort. Each pipeline is a source, a chain of
row-by-row operators and a sink, and chunks are pushed along it.

- LIMIT sends a stop signal upstream.
- A sink may spill when memory runs out. The `Run` memory budget becomes the
  pipeline's.

**Parallel.** A pipeline's source is split into morsels (key ranges of a
tree) and run on N workers; a sink merges their state. This needs no change
below layer 2, because the store already serves concurrent snapshot reads.

**What goes away:**

- `runLevel`/`tryRow` and the level chain;
- the batch path's give-way;
- `rs.batch`;
- the five batch drivers;
- the duplicate aggregate and sort code.

The kernels in architecture.md section 6 (`bRunInto`, `bProbe`, `bJoinTail`,
`skSort`, `bAccum`) move into the operators. Their inner loops are not
rewritten without a measured replacement.

### 4.7 Layers 7 and 8

**Statements:**

- DML plans its source rows as a query, and its writes go through layer 2.
- RETURNING, ON CONFLICT, foreign-key and CHECK constraints, triggers and
  deferred checks stay here, as row-at-a-time logic over chunks.
- PL/SQL and T-SQL batches call into layers 4–6 like any client.
- The executor context (`ExecTxn`) holds the store `Txn` and the SQL state
  that is now in `Txn.sql`.

**Protocols and dialects:** as architecture.md section 5 and followups 1
describe. The connection-time `Dialect` record also supplies the binder's
typing tables.

### 4.8 Estimated size

These are estimates from section sizes, not measurements.

- **Executor.** Today about 11–12k lines run queries, plus about 4k of
  planner in exec. The aim is about 7–8k for layers 4–6's execution side,
  plus a binder of 2–3k that partly replaces code now spread through
  planning and execution.
- **Elsewhere.** Layers 1, 3, 7 and 8, and the value code, stay roughly the
  size they are.
- **Where the real gain lies.** Not mainly in the line count: in one
  implementation of each thing, files that each fit one task, and
  workstreams that don't conflict.

## 5. The on-disk format

**Is it a constraint? No, but nothing in this plan needs it changed.**
Sections 4.1–4.7 can be built over today's format unchanged. After layer 2
exists, a format change touches only layers 1–2 and `lexdb_rows`, which is
when one is cheap to make. So: keep the format during the restructuring, and
decide format changes on their own measurements afterwards.

The format questions that do matter, and their trade-offs:

**1. Clustered primary key vs a heap with row locators.**

- Today rows live in the primary key's B+tree, and a secondary index entry
  holds the primary key. A lookup through a secondary index therefore costs
  a second B-tree descent per row. That is the per-row fetch cost left in
  q19 and q20 (`fillIdxRows`/`getMany`, about 3.5 µs a row).
- PostgreSQL's heap with tuple ids avoids the second descent, but pays for
  it elsewhere:
  - VACUUM;
  - HOT chains;
  - index bloat;
  - every index must be touched when a row moves.
- In a copy-on-write tree a row's physical place changes at every
  checkpoint, so stable locators would need an indirection table, which is
  itself another lookup.
- **Recommendation:** keep the clustered layout. It is what makes PK point
  reads, PK ranges and updates fast. Attack the fetch cost with:
  - sorted batched fetches (`fetch` over a chunk, layer 2);
  - **covering indexes** (`INCLUDE` columns), which are additive: a new
    index can carry them and old indexes still read;
  - choosing the hash join more often when many rows will be fetched (the
    optimizer's job).

**2. Secondary index entries store the primary key twice** (in the key and
as the value; lexdb-pages.md section 1).

- Dropping the copy saves about 28% of an index's size, with no loss.
- It is a leaf-format change that can be read both ways for a release: old
  leaves are read as now, new leaves are written without the copy.
- Do it inside layer 2 once it exists. It is low priority.

**3. Column leaves for tables and row leaves for indexes.** Already the
format. They measured 13–42% faster on scan-heavy queries and 45% smaller,
with point reads the same (lexdb-pages.md). Keep them.

**4. Page compression.** Measured as not worth it (lexdb-pages.md: CPU-bound
on this NVMe). Leave it out.

**5. Versions, snapshots and the checkpoint.** These are internal to layer 1.
Changing them would be a store project with its own risks (followups 3c).
Nothing here needs it.

Rule for any change made later: additive and versioned per leaf or per tree,
read both ways for at least one release, never a dual-write mode.
architecture.md section 12 already records that downgrade is unsupported.

## 6. Order of work

**Recommendation: keep the storage engine as it is and start above it.**
Storage is the strongest layer and gave none of this week's bugs. The
leakiest boundaries are store↔exec (no access layer) and parser↔exec (no
binder), and those are what make the executor rewrite hard. Storage
clean-up runs alongside as its own workstream, because it is internal to
layer 1.

| Step | What | Behaviour | Gate |
|---|---|---|---|
| 0 | This note; the construct inventory (each SQL construct mapped to binder, optimizer rule or operator) | none | review |
| 1 | **Access layer.** Move key encoding, row and index reads, and index upkeep out of exec into `lexdb_access`; `Txn.sql` moves to an `ExecTxn` | identical | suite, 22 checksums, OLTP and bulk-load A/B, 35-query A/B |
| 2 | **Binder and the expression IR.** Bound typed plan; one IR with scalar and vector evaluators; the old executor consumes the bound form | identical, plus the binding bugs fixed | suite; PostgreSQL as oracle on the type-mixing probes |
| 3 | **Optimizer emits an operator tree.** A `Levels` operator first wraps today's level chain, so plans run as before | identical | suite; EXPLAIN unchanged |
| 4 | **Pipeline executor.** Operators one at a time: scan, filter and project; then hash join; aggregate; sort and top-N; window. The plan chooses the new engine only if it supports every construct; nothing gives way mid-query. Old code is deleted per construct. | identical | as step 1, per operator |
| 5 | **Unnesting.** Correlated subqueries to semi, anti and mark joins; the per-row subquery machinery deleted | identical | TPC-H q2, q4, q17, q20, q21, q22 |
| 6 | **Bushy join search** | faster | TPC-H |
| 7 | **Parallel pipelines** (morsels) | faster | TPC-H against PG at 4 processes; OLTP must not regress |
| S | **Storage engine** (any time, at most one agent): ReadView and one `read`, the dedup list, the follower as the store in replay mode | identical | storage gates (architecture 9) |

Steps 1 and 2 are independent and can run at the same time, one agent each
(the two-agent limit). Step 3 needs step 2. Steps 4–7 are sequential.
Main stays green after every step.

## 7. Trade-offs and risks

- **Single-row latency.** A pipeline has setup costs that a nested loop does
  not. The guard:
  - the optimizer plans "primary key equals, then project" as a fixed
    Fetch→Project chain run on a chunk of one;
  - plans are cached per prepared statement;
  - the OLTP point-select run is a gate at every step.

  PostgreSQL's tuple-at-a-time executor is the bar here, and today we match
  it.
- **Errors and short-circuits** under vector evaluation: handled by the
  selection vector (section 4.4). The test is that every probe gives the same
  result as with batches off, as today's "three ways" tests check.
- **Per-row side effects:** `nextval`, volatile functions, `FOR UPDATE`,
  RETURNING and foreign-key checks. They are evaluated per selected row in
  order, inside the DML operator (layer 7).
- **Memory.** Hash builds and sorts must spill or fail with the configured
  error. Today's `Run.aside` and `max_statement_mem` become pipeline
  budgets.
- **The second system effect.** A rewrite that stops shipping is the main
  risk. The guard is the step table: every step merges to main with the
  gates, the old path is deleted as the new one covers it, and there is no
  long-lived branch.
- **Performance kernels.** Moving code must not regress the tuned loops. Each
  operator port is an A/B against main's binary.

## 8. Decisions

Agreed with the owner on 2026-11-16:

1. **The row strategy:** a chunk of one. The row executor is deleted once
   step 4's OLTP numbers confirm it is no slower.
2. **The on-disk format:** kept through steps 1–7 (section 5).
3. **The per-row fetch cost:** answered with covering indexes (`INCLUDE`),
   not a heap layout.
4. **Module names:** `lexdb_access` and `lexdb_bind`.
5. **`SET lexdb_batch = off`:** test-only (architecture 11).

Steps 0–1 and 0–2 start at once, one agent each.
