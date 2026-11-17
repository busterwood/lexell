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

- index upkeep and the writes (done in 1c and 1d, 4.2.2);
- `Txn.sql` (`ExecTxn` not made yet);
- catalog trees, read and written directly (`CATALOG`, sequences, roles,
  ACLs), and `relSize`, which counts pages by tree number from the catalog
  lines.

#### 4.2.2 As built: the write side (step 1c, 1d)

Status: 2026-11-16, branch `redesign/access`. Exec's table and index
writes go through `lexdb_access`; `Scan.lo`/`hi` are private.

**What an index needs from above** comes as closures, so evaluation stays
where it is and its order is unchanged:

- `pred: &fn(&Index, &[]Val): Result[bool, DbErr]`, a filtered index's
  predicate (exec's `inIndex`);
- `expr: &fn(&Index, int, &[]Val): Result[Val, DbErr]`, an expression
  part's value of its type (exec's `idxVal`);
- `wrote: &fn(&Txn)`, called once a row's own tree is written and before
  its entries, where exec counted the row for the automatic statistics.

Access calls `pred` and `expr` only for an index that has a predicate or
an expression part. A part's value is now made once per row and index,
where exec made it up to three times. Index expressions must be immutable,
so the values and the first error are the same.

**Interface.**

```
const NO_CONFLICT = -2; const PK_CONFLICT = -1        // else an index's number
type Conflict { at, ix }                              // a chunk's first conflict
insert(st, txn, rel, rows: &[]&[]Val, pred, expr, wrote): Conflict
update(st, txn, rel, olds, news, pred, expr, wrote): Conflict
delete(st, txn, rel, rows, pred, expr, wrote)
conflicts(st, txn, rel, arb, rows, pred, expr): []Option[[]Val]   // ON CONFLICT's arbiters
hasKeys(st, txn, rel, via, rows, expr): []bool                    // a foreign key's parent
insertRow / updateRow / deleteRow / conflictRow / hasKey          // the same for one row
encRow(rel, row); rowidKeyed(rel); ixPart(rel, ix, k, row, expr); ROWID

newBuild(redo) / buildAdd(rel, b, row, pred, expr) / buildWrite(st, txn, rel, b, sorted, wrote): Dup
buildIndex(st, txn, rel, ix, pred, expr): Option[[]Val]           // CREATE INDEX
exactRange(eqs, lower, lowIncl, upper, upIncl, ix): Scan          // a range delete's bounds
rangeLocked(st, txn, rel, sc); deleteRange(st, txn, rel, main, ixs, ixr, slow, need, pred, expr): int
newLoad() / loadRow(st, txn, rel, id, row, ld): bool              // COPY's fast path
setSpec(st, rel); upgrade(st, rel, from, most); anyRow(st, txn, rel)
```

**Conflicts are reported, not raised.** A key taken, or a unique index's
value that another row holds, comes back as `PK_CONFLICT` or the index's
number, with the rows before it written. Exec makes the error (`dupKey`,
`uniqueErr`, `dupMade`) as before: UNIQUE, ON CONFLICT, foreign keys,
CHECK and deferred checks stay in layer 7.

**Chunks of one, for now.** The chunk calls loop over the one-row calls.
Exec calls the one-row calls, because building a one-element array of
row borrows per row cost about 2.5% on the 1M-row INSERT ... SELECT load
(one allocation a row). When DML runs in chunks (4.9), exec calls the
chunk forms. Their per-row loop is where the batched probes and the
chunk's own-key hash go.

**Gate (steps 1c–1e against main `b222bca3`, built the same session;
medians of three).** Suite 184 passed. TPC-H: all 22 checksums equal the
`1744ef99` baseline's, per-query ratios 0.968–1.038, geometric mean 0.997.
OLTP point selects 83.3k/136.9k/131.2k tps at 1/8/32 clients against
82.9k/136.3k/131.3k; updates 3,831/18,131/39,936 against
3,831/18,151/39,830. INSERT ... SELECT of 1M rows (three fresh runs):
acct 1.18 s against 1.17 s, t 2.37 s against 2.36 s; 30k rows into a
table with an index and a unique text index 2.92 s both; UPDATE of an
indexed column (8 clients) 21,422 against 21,510 tps. COPY: narrow
0.51 s against 0.50 s (after `relOf` was hoisted out of the fast path's
row loop; 0.52–0.53 s before), wide 1.54 s against 1.53 s, wide with two
indexes 7.14 s against 7.08 s.

**Still in exec after step 1d:**

- the fast COPY's text-to-row encoder (`fastCopyField` and friends). It
  builds a row's stored bytes, so it belongs with `lexdb_rows`. Its key
  and write moved (`loadRow`).
- creating and dropping a table's or index's trees (`st.createTree`,
  `txn.dropTree`) in DDL. These go with the catalog's define/alter/drop
  (4.3), since the catalog row names the trees.
- `rs.after`/`win.after`, a batched statement's resume key, is made with
  `lexdb_access.after` and kept opaque.
- `Txn.sql` (`ExecTxn`): after step 2.

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

#### 4.4.1 Design: the bound plan, the expression IR and the transition (step 2)

Written 2026-11-16 on `redesign/bind`. Slice 2a is built (below); the rest
is the plan.

**What is there today.** Types are worked out on demand: `exprOid` labels
an expression by its OID only (no typmod, no collation), `resolve` rewrites
names and inserts a few casts (COALESCE's literals, T-SQL's bit, char(n)'s
trim and pad), and the run-time operators decide by the values' kinds
(`binVal` matches the operator as a string and then `kindOf` both sides).
A union's, CASE's and VALUES' column was labelled from its first branch,
and its values were left in whatever type each branch gave. That is the
week's binding bugs in one sentence.

**Types.** One descriptor, used for every column and every expression node:

```
Ty = value record {
    oid: int          // the type (lexdb_sql.OID_*, an enum's OID, an array's)
    mod: int          // typmod: numeric p << 16 | s, varchar/char n, time precision; -1 none
    coll: int         // collation id (0 none, 1 the session's default)
    collLevel: int    // none, default, implicit, explicit (parse_collate.c's strengths)
    notNull: bool     // nullability, for the optimizer (outer-join sides are nullable)
}
```

`TypeName` (the parse tree's) converts to `Ty` once. OID 705 (unknown) is
kept for an untyped literal or parameter until the binder decides it from
context, as PostgreSQL does; it never reaches a plan's output (it becomes
text there).

**The bound plan.** A tree of logical operators, each with output columns
`[]BCol{slot, name, spell, ty}`; an expression refers to its input's columns
by slot. The operators match lexdb-constructs.md's B rows:

| Logical operator | From | Notes |
|---|---|---|
| `Get(rel, cols)` | a table, a view (inlined), a catalog relation | `rel` is layer 2's handle; a view's text is bound once per statement |
| `Values(rows)`, `Func(fn, args, ordinality)` | VALUES, SRFs in FROM | column types from all rows (common type) |
| `CteRef(id)`, `Recursive(id, anchor, step)` | WITH | bound once, referenced by id (the inventory's re-parse per use goes) |
| `Filter(pred)`, `Project(exprs)` | WHERE, select list | volatile exprs flagged (4.9 rule 1) |
| `Join(kind, lateral, l, r, on)` | FROM | kind: inner, left, right, full, cross; semi, anti, mark after step 5 |
| `Apply(kind, outer, sub, refs)` | correlated subqueries, LATERAL | what step 5 unnests; until then the executor runs it as today |
| `Agg(keys, sets, aggs)`, `Window(part, order, frame, calls)` | GROUP BY, GROUPING SETS, windows | aggregates referenced by slot (`#agg` today) |
| `Sort`, `Limit(count, offset, ties, percent)`, `Distinct(on)` | ORDER BY, LIMIT/FETCH/TOP, DISTINCT [ON] | |
| `SetOp(op, all, l, r)` | UNION, INTERSECT, EXCEPT | each side projected to the common types first |
| `Match(def)`, `Lock(mode, tables, wait)` | MATCH_RECOGNIZE, FOR UPDATE | |

DML stays a layer-7 statement holding a bound source plan and bound
SET/VALUES/RETURNING expressions over the target's columns.

**The typed expression IR (`BX`).**

```
BX = closed {
    Const(Val, Ty)                 // folded; already of its type (1 as numeric is Num(1))
    Param(int, Ty)                 // $n, cast to its use's type when the client gave none
    Col(int, Ty)                   // input slot
    Outer(int, int, Ty)            // an enclosing query's slot (correlation), until unnested
    Op(OpId, []BX, Ty)             // operator or function, chosen by signature
    Cast(BX, CastId, Ty)
    Case([]BX, []BX, BX, Ty)       // WHENs, THENs, ELSE: every THEN already of Ty
    And([]BX), Or([]BX), Not(BX), IsNull(BX, bool)
    Coalesce([]BX, Ty)
    Sub(int, int, Ty)              // a subquery's result (scalar, EXISTS, IN) until unnested
    Agg(int, Ty), Win(int, Ty)     // slots of the operator below
}
```

`OpId` and `CastId` index tables of definitions, one entry per signature:

```
OpDef = value record {
    name: str; args: []Ty; result: Ty
    scalar: fn(&[]Val, &Ctx): Result[Val, DbErr]     // the one semantics
    kernel: int                                      // a typed vector kernel (lexdb_vec), or 0
    strict: bool        // NULL in, NULL out: the evaluators skip NULL rows
    volatile: bool      // random, nextval, clock_timestamp, set_config
    canFail: bool       // overflow, division by zero, bad input
}
```

The scalar functions are today's `binVal`/`unaryVal`/`castVal`/`callAt`
arms, split per signature so nothing matches a string or a kind per row.
They move into a module below exec (`lexdb_ops`, as lexdb-tpch-perf.md
4.1.4 planned) so that the binder can fold constants with them and the
planner can coerce bounds with them: that is the `Fold` record and the
"coercion in a core module" of followups 5, and the `keyVal`/`coerceZ`
coercion the access layer now leaves to the binder.

**Scalar and vector from one definition.** A bound expression is compiled
once per plan into a flat program (PostgreSQL's `ExprState` steps): each
step is an `OpId` with input and output registers. The scalar evaluator
runs the steps on one row's values. The vector evaluator runs each step on
a chunk: the op's kernel when it has one and the registers are typed
vectors, else the op's `scalar` over the selected rows (the generic step,
today's `Gen`). So a kernel is an optimisation of an op, never a second
semantics; a test runs every op with a kernel both ways on the same
inputs, as the "three ways" tests do for whole queries. A kernel that
cannot represent a result (a units overflow) spills that step to the
generic step for the chunk, which gives the exact value or the row's error.

**Errors and short-circuits under a selection vector.** Every step runs on
the selection it is given, never on rows outside it:

- `And`/`Or`: the right side runs only on rows the left side left
  undecided (true for AND, false for OR, or NULL).
- `Case`: WHEN k runs on the rows no earlier WHEN took; THEN k on the rows
  WHEN k made true; ELSE on the rest. `CASE WHEN x <> 0 THEN 1/x END`
  never divides by zero.
- `Coalesce`: argument k runs only on rows still NULL.
- Strict ops skip NULL rows; a `canFail` op checks only selected rows.
- An error is raised exactly when the scalar evaluation of some selected
  row would raise it; the reported row is the lowest selected row of the
  first failing step. (Which row PostgreSQL reports is not specified
  either.)
- A volatile op is evaluated once per selected row, in row order, at the
  place 4.9's rule 1 puts it; the binder marks the expression volatile so
  the optimizer never moves or duplicates it.

**Dialect typing as data.** The binder has one algorithm; a dialect
supplies tables (`Typing`, chosen at connection with the `Dialect` record):

- per type, its category and whether it is its category's preferred type,
  and the implicit casts. PostgreSQL's are pg_type's `typcategory` /
  `typispreferred` and pg_cast's castcontext `i` (REL_18_6). The common type
  of a union, CASE, COALESCE, GREATEST/LEAST or VALUES column is
  `select_common_type` over them: a left fold where a type gives way to a
  later one of its category when it is not preferred and casts to it
  implicitly but not back. SQL Server's data type precedence fits the same
  form (one category per family, implicit casts from lower to higher
  precedence); Oracle's datatype families likewise;
- how an untyped literal is read (PostgreSQL: unknown, decided by context;
  T-SQL: `''` as 0 for numbers);
- the collation rule for a comparison (PostgreSQL lets a non-default
  implicit collation win over the default; SQL Server treats it as a
  conflict: the open question of lexdb-tpch-perf.md 4.2);
- function and operator signatures beyond the core's (Oracle's
  `lexdb_orafn.resultOid` today), and decimal rules such as T-SQL's
  division scale (`#tdiv` today).

**The transition: the old executor consumes the bound form.** No big-bang;
each slice merges with the suite, the 22 checksums and an A/B.

| Slice | What | The old executor sees |
|---|---|---|
| 2a (built) | `lexdb_bind` owns expression typing (`exprOid` moved) and PostgreSQL's common-type rule as data; set operations, VALUES, CASE, COALESCE, GREATEST/LEAST typed from every branch | the same `Expr`, with the implicit casts made explicit (`Cast` nodes, constants folded) and the set operation's per-side conversions (`Sel.conv`) |
| 2b (built) | `BX`, `OpDef` and `lexdb_ops`; `cxOf` becomes the binder's `bindExpr`, `cEval` runs `BX`; delete `CX` and `FnB` | `BX` for compiled expressions; `eval` over `Expr` for the rest |
| 2c | `bCompile` builds its batch nodes from `BX` (the generic node is a `BX` step); constants pre-scaled and common subexpressions once per chunk | `BX` in both evaluators; `BNode` shrinks to the kernels |
| 2d | Scope and naming: `resolve`/`resolveName`/`Scope` frames, star, GROUP BY and ORDER BY resolution move to the binder; columns by slot | `Query.cols` as `BCol`s; `eval`'s name lookup (`colIndex`) gone |
| 2e | The binder emits the logical plan for SELECT and DML sources; `planSelect`/`buildQuery` read it instead of the `Stmt` | step 3 then turns it into the operator tree |

Each later slice deletes the code it replaces; nothing keeps two typings.

**Slice 2a as built.** `lexdb_bind` holds `exprOid` (moved unchanged,
with Oracle's result types passed in as `Typing.fnOid`), `commonOid`
(select_common_type) and `converts` (whether a value must be converted
to the common type: numbers and date/time types along an implicit cast,
and untyped literals). The facts are `lexdb_dialect.TYPE_FACTS` and
`IMPLICIT_CASTS`; only PostgreSQL's exist yet, and they serve all three
dialects, as exec's one rule did before. Where two branches are of
different categories (PostgreSQL's 42804, `1 UNION SELECT 'a'::text`),
the old first-branch rule is kept rather than adding an error a T-SQL or
Oracle session would not raise; with each dialect's tables that becomes
the dialect's own answer.

Fixed, each checked against PostgreSQL 18.6 and in `exec_bindtypes`
(batches off and on):

- a set operation's column takes both sides' common type, and the side of
  another type is converted (`runSet`): `1 UNION ALL 2.5` is numeric (was
  an integer column holding 2.5), a date UNION a timestamp a timestamp, so
  EXISTS and IN against a timestamp column find the dates too (72 rows,
  was 36; the join gave 216 before and after);
- a VALUES column takes all its rows' common type: `VALUES (1),
  (3000000000)` is bigint (was "integer out of range"), `VALUES (1), (2.5)`
  gives 1 and 2.5 (was 1 and 3);
- CASE, COALESCE, GREATEST and LEAST: values of the common type, constants
  converted when bound: `CASE WHEN c THEN 1 ELSE 2.5 END / 2` divides
  numerics (was integer division, 0), a date beside a timestamp shows as a
  timestamp.

Not changed, found on the way: NULLIF's type (PostgreSQL types
`nullif(1, 2.5)` numeric, through its `=`); a numeric division's scale
(lexdb gives 16 places where PostgreSQL gives 20); typmods of a common
type (`numeric(10,2) UNION numeric(12,2)`), since exprOid has none; and
an untyped literal in the first side of a set operation is typed only in a
plain select list (`branchOid`).

**Slice 2b as built.**

- `lexdb_bind.BX` is the compiled scalar expression: `bindExpr` binds it
  with `cxOf`'s rules (columns by slot, parameters as constants), and
  `CX`, `FnB` and `cxOf` are gone.
  - Its binary operators carry a code (`lexdb_ops.OPS`), its unary ones
    `UN_*`, so nothing matches an operator's text per row.
  - Its nodes carry no type yet. A first version labelled each operator,
    CASE and call with `exprOid` while binding, and q20 lost 5%.
    `bindExpr` runs once per run of a correlated subquery (8,508 times in
    q20), because parameters are bound as constants. Types come with 2c,
    once per plan and bottom-up, with parameters as slots.
  - A function binds through the executor's hook (`Typing.fnBind`:
    exec's `fnRefOf`, which also lists what only `eval` evaluates) into
    a `FnRef`.
  - exec's `bxEval` and `callRef` evaluate it, as `cEval` and `callB`
    did.
- `lexdb_ops` (new, below the binder and the executor) holds the value
  operations:
  - conversion (`coerce`, `coerceZ` and their parts);
  - comparison (`compare`, `compareZ`, `compareTime`);
  - arithmetic (`arith`, `arithZ`, `arithTime`, `arithFloat`, `powOp`)
    and `unaryVal`;
  - the operator table, `binOp` (an operator by its code) and `castTo`
    (a cast other than a reg type's).
  - A session's zone reaches them as a closure, asked for only where a
    value needs it, so no per-row copy is made.
  - exec keeps its names as one-line forwarders. `binVal` and `castVal`
    stay in exec as eval's entry points over the session (a reg cast
    reads the catalog).
- IN and = ANY over a subquery compare as `=` does
  (`lexdb_bind.inReadOid`): an untyped or text side is read as the other
  side's type. This fixes an untyped date parameter IN a date set and
  `true IN (SELECT 't'::text)`.
- Not yet:
  - the function library (`callAt`, `callFn`, `callMisc`, `callTime`)
    is not split per signature: it moves with 2c's generic node;
  - `arith` still takes the operator's text inside;
  - exec calls `lexdb_ops` directly (496 call sites renamed); it keeps
    `pub` forwarders only for the names other modules and tests use. A
    forwarder per call to `isNull` or `compare` measurably slowed q20;
    `opCode` reads bytes, not a match of texts, because q18's HAVING
    reaches `binVal` 1.5M times;
  - `bxEval` walks the tree rather than running flat steps.

**Slice 2c, first part, as built.**

- Binding bugs fixed, each against PostgreSQL 18.6 (`exec_bindfix`):
  - `COLLATE "C"` on char(n);
  - `'2024-1-2'::date`;
  - an explicit `::varchar(n)` now truncates;
  - `= ANY (ARRAY[...])` and `<> ALL (...)` under a case-insensitive
    collation.
- **Rule 1 of 4.9:** where the row path rechecks a level's conditions, a
  volatile one (`random()`) is no longer also evaluated by the batch
  filter.
- `arith`, `arithZ`, `arithTime` and `arithFloat` take operator codes.
- **Not fixed: EXISTS with a derived table's text column compared to a
  date** (0 rows where 1 is right). The subquery is hashed on `b.d = a.t`
  (`keyConj`/`hashKeyTypes` let an untyped outer parameter key a hash).
  Its date keys and the outer text value never meet. It needs the outer
  reference typed from the derived column's label, which 2a made
  trustworthy for unions, VALUES and CASE but not yet everywhere.

**Slice 2c, item 1, as built: bound once per plan.**

- `BX.Param(i)` is a parameter slot. `bindExpr` with no parameter values
  binds each `$n` as a slot; the run's values are in `CEnv.params`.
- `bindSel` binds every level's conditions once per plan: its own, its
  set operation's parts' and its subqueries', recursively. They are held
  in `Query.cc`/`cp`, after all planning rewrites. `runCached` (plans
  kept for prepared and repeated statements) and `selectWith` call it.
- `prepare` uses them when they still match the levels one for one
  (`boundOnce`). Otherwise, as in DML's queries and EXPLAIN, it binds per
  run as before.
- The output plan, the aggregates' outputs and the batches' generic node
  still bind per run, with values as constants: `bGenVals`' constant
  shape needs them. They follow with item 2.
- Node types are not added yet: nothing reads them until item 2 chooses
  kernels from them.

**Slice 2c, item 2, first step as built: outputs bound once.** A
plan's output expressions are bound with its conditions (`bindSel`,
`Sel.ox`, parameters as slots). `outC` reads them, and binds per run only
for a plan not bound once (DML, EXPLAIN). The window path's outputs and
`bGenOf` still bind per run.

**Why the rest of item 2 is split.** `bCompile`'s `BT_*` types are not
only SQL types:

- `BT_DEC + s` is a column leaf's units scale (`BK_DEC`), known per batch,
  not per plan.
- `BT_INT`, `BT_BOOL` and `BT_OTHER` follow the batch's column kinds
  (`BK_*`).

So the kernels need both the binder's type and the batch's physical kind,
and "BNode's separate typing" cannot simply be deleted. What can move:

- the SQL-level decisions (which operator, integer or numeric
  arithmetic, comparisons by value) to the bound node;
- `bTimeVal`'s two jobs to the binder:
  - a text constant beside a date column read as a date: an untyped
    literal cast to the column's type in `resolve`, as PostgreSQL types
    it;
  - another time kind compared in the session's zone: a cast made when
    bound, which ties the plan to the zone, so the plan cache must key
    on it.

Steps, each with q1, q6 and the scan queries as its gate:

- 2-ii: `bCompile` reads `BX` instead of `Expr`. Constants come from
  `bxEval`; IN and LIKE are read from the bound call. No new types.
- 2-iii: node types bottom-up in `bindExpr` (once per plan). `bCompile`
  chooses a kernel from the node's type and the batch's kind. `bValCmp`,
  `bColPair` and `bTimeVal` are deleted once the binder casts constants.
  (As built, without a type on every node: see "2-iii as built".)
- 2-iv: `bGenOf` from the plan's bound expression. Its slots are the
  batch row's places, so it re-slots a bound tree instead of binding
  again.
  (As built: see "2-iv as built".)

**2-ii as built: `bCompile` reads `BX`.** The batch nodes it makes are
the same as before, node for node; only what it reads changed.

- `bCompile`/`bCompileD` take a `BX` bound over the query's columns by
  place (`BX.Col(i)` is query column `i`, the batch's `i - base`) and a
  `CEnv`, the run's (`Mats.ce`: its parameters, session and zone).
- Where the plan bound the expression, that binding is read, not bound
  again: a level's conditions from `Mats.cc`/`cp` or `Query.cc`/`cp`
  (`bCompileCond`), the outputs from `Sel.ox` (`bCompileOut`). The rest
  (join keys, a semi/anti join's value, ORDER BY keys, group keys,
  aggregate arguments and FILTERs) are bound when compiled (`bxOf`:
  parameters as slots).
- A constant subtree (`bxConst`: literals and parameters under
  operators, casts and `#bppad`, as `bConst` was for `Expr`) is
  evaluated once by `bxEval`. An IN list's values are those `bxFixed`
  allows (no column, no clock, session or volatile function:
  `immutableName`, shared with `immutable`). IN and LIKE are read from the
  bound call (`FnRef.name`).
- Operators by code: `cmpOf` and `arithOf` map `lexdb_ops.OP_*` to
  `BNode`'s codes; `cmpCode` and `arithCode` (by text) are gone.
- Not changed: `BT_*` and `bTimeVal` (2-iii), `bGenOf` (2-iv), and
  `bConst` over `Expr`, which `rangePath` still reads.
- One difference in what reaches the batches, not in results: an
  expression with a part that does not bind (a reg cast, a session or
  catalog function in an IN list) was compiled before when that part was
  a constant; now it goes to the row path, with the same result. Such
  conditions are mostly on catalog relations, which batches do not scan
  (`lv.virt()`).

**Follow-up: the outputs' parameters.** `outC` copied the run's
parameters into its `CEnv` on every execution of a plan bound once, which
cost point selects 0.5–0.9%. `bindSel` now notes whether any bound output
reads a parameter slot (`Sel.oxParam`, `lexdb_bind.hasParam`), and `outC`
copies them only then.

**Where 2-ii left off, and how to start 2-iii.** All in `lexdb_exec`
unless named; search for the names, since line numbers move.

- The batch compiler: `bCompile`/`bCompileD` (over `BX`), with its entry
  points `bCompileCond` (a level's conditions, from `Mats.cc`/`cp` or
  `Query.cc`/`cp`), `bCompileOut` (`Sel.ox`), `bCompileX` (bind now:
  `bxOf`). Its helpers are `bxConst`, `bxFixed`, `cmpOf`, `arithOf` and
  `bAndOr`. Its typing, which 2-iii replaces, is the `BT_*` constants
  (`BT_INT`, `BT_BOOL`, `BT_NULL`, `BT_OTHER`, `BT_DEC + scale`),
  `intLike`/`boolLike`/`isDecT`/`decSc`, and `bValCmp`, `bColPair`,
  `bValCmpOf` and `bTimeVal`.
- `BT_*` reaches past `bCompile`: `BComp.typ` is read by
  `bKeyVal`, `JLevel.keyTyp` (`JK_INT`/`JK_TEXT` choice), `outNode`, and
  `batchGroupsIn` (`dsc`, `vcol`, group keys). Kernels: `BNode`,
  `bEval`, `lexdb_vec` (`arith`, `cmp`, `sum`).
- `bTimeVal` matters only for a `BK_VAL` column of date, timestamp or
  timestamptz: `ValCmp` and the IN list (`InVals`). `BK_DEC` occurs only
  in `batchGroupsIn` over one table (`dec`).
- The binder: `lexdb_bind.bindExpr`/`bindIn`, `BX`, `exprOid`; exec's
  `typing()` and `fnRefOf`. Plans are bound once in `bindSel`/
  `bindQuery` (`cxsOf`, `boundOnce`); `prepare` binds per run when the
  plan's bindings no longer match (DML, EXPLAIN), and `bxOf` binds join
  keys, ORDER BY and group keys and aggregate arguments per run. So node
  types computed inside `bindExpr` run per run on those paths: 2b found
  that typing per bind cost q20 5%. Compute types once per plan (in
  `bindSel`) or keep them cheap. The plan cache is `PlanCache` (`ver`);
  a zone key for bind-time time casts goes there.
- Traps:
  - `BX` is boxed and owned. `return cs[k][i]` out of a borrow does not
    compile; match on it and compile inside the arm (as
    `bCompileCond` does).
  - The suite compiles each test as it runs it: do not edit the sources
    while it runs.
  - `bConst` (over `Expr`) is still read by `rangePath`; `immutable`
    and `immutableName` are shared.
- Build, test and measure:
  - Build: `flock -s ~/tpch/.bench.lock env LXL_NOCACHE=1 taskset -c
    4-7,12-15 lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -o OUT`
    (the native backend; never the gcc path).
  - Suite: `flock -s ~/tpch/.bench.lock python3 lexell/tests/lexdb.py
    --compiler .../lxlc -j 2` (187 tests; a test's name as an argument
    runs it alone).
  - The A/B scripts are in `~/tpch-w/bind/bench`: `tpch_ab.sh TAG
    LABEL...` (run.sh per binary `~/tpch-w/bind/lexdb-LABEL`, out to
    `out-LABEL-TAG`) with `tpcmp.py A B TAG...` (medians, checks, checksums
    against `~/tpch/out-baseline-1744ef99`); `ab35.sh` with `cmp35.py`
    (the 35 queries); `oltp.sh` (vspg, lexdb only, `vspg-lex.sh`).
  - The main baseline is built from `git archive <main> lexell/cmd` into
    `~/tpch-w/bind/src-main`.
  - Five of the 35 queries fail on both binaries with la/base2's data
    ("page N: type 2"): known.
- 2-ii's A/B against main 540106ec: TPC-H total 1.000, all checksums the
  baseline's. q1 was 1.1% slower in all three rounds and q6 0.8% faster,
  with the same batch nodes; probably code layout, not verified. 35
  queries 1.001. Point selects 0.988/0.994/0.993 at 1/8/32 clients
  (a path 2-ii does not touch), updates level. With the follow-up: TPC-H
  1.001 (q1 1.015 again), point selects 0.999/0.994/0.999, updates
  level. So the follow-up's saving was not visible against 540106ec.

**2-iii as built: a constant beside a time column typed by the binder.**

- `resolve` casts an untyped value beside a column of a date or time type
  to the column's type (`timeLitOid`), as PostgreSQL types an untyped
  literal from the other side: a text literal, or a parameter of no type
  or a text's (`ptypesOf`: its value is a text), in a comparison and in
  an IN list. The cast is to the bare type (`lexdb_sql.timeType`, no
  precision), which is what `compareTime` read a text as, and it is
  evaluated where the plan runs, in the run's zone (`bxEval` with
  `Mats.ce`, `eval` with the session). So the batches see the column's
  own kind, and nothing in a plan depends on the zone. The plan cache
  already keys on the zone (9.95), so no key was added.
- `bCompileD` chooses the kernel for a comparison from the types of its
  two sides and the batch's kinds, in the `BX.Op` arm: a column of values
  (`BK_VAL`) beside a column is `VCmp`, beside a constant `ValCmp`, when
  `bCmpKinds` allows the pair. The same rule guards the IN list's chain
  and sorted set (`InVals`). `bCmpKinds`: the batches compare in UTC
  (`lexdb_ops.compare`) and the row path in the session's zone
  (`compareZ`), so a pair is allowed when it is of one kind, when neither
  is a date or time kind, or in UTC; a text beside a date or time column
  never (resolve casts the untyped ones, and a sorted set must be in the
  column's order).
- Deleted: `bValCmp`, `bColPair`, `bValCmpOf` and `bTimeVal`. `BT_*`
  stays: it is the batch's physical kind of a result (`BK_*`, `BK_DEC`'s
  scale), which `bKeyVal`, `JLevel.keyTyp`, `outNode` and
  `batchGroupsIn` read; none of it became dead.
- Decisions:
  - **No type stored on every `BX` node.** No kernel reads an inner
    node's SQL type: the comparisons that need one read their leaves, a
    column's type (`q.cols`, fixed when the plan is made) and a
    constant's kind (its value, evaluated once per run; a parameter's
    kind is only certain then). Typing every node in `bindExpr` would run
    per run on the `bxOf` paths (join, group and ORDER BY keys, aggregate
    arguments), which is what cost q20 5% in 2b. Node types come with
    the first consumer (2-iv's `bGenOf` or the function library, 3).
  - **"Another time kind" is not cast.** A constant of a lower date or
    time kind (a date beside a timestamp column) could be cast up exactly,
    but one of a higher kind cannot be cast down: `d < timestamp
    '2020-01-05 12:00'` keeps 2020-01-05, `d < '2020-01-05'::date` does
    not, and q6's `l_shipdate < date '1994-01-01' + interval '1 year'` is
    a date column beside a timestamp. Casting the column up instead takes
    the condition off the batches. So the batch compares a pair of
    different time kinds only in UTC, as before, as a kernel choice made
    per run from the run's zone (`bCmpKinds`), not a cast in the plan.
  - Pairs that reached a batch before and now do not, or the other way
    round, with the same results: two columns of different time kinds in
    UTC now batch (`VCmp`; `bColPair` declined them in every zone); a
    text column beside a date or time constant outside UTC, and a text
    constant beside a date or time column that resolve did not cast (a
    parameter with no type given at all, `run` with fewer types than
    values), now go to the row path (`bTimeVal` read the text once; the
    former compared in UTC where the row path compared in the zone).
- One difference in results, PostgreSQL's (`exec_timelit`): a literal the
  column's type refuses (`tz = 'bad'`) is refused even where the column
  is NULL. lexdb compared only the rows not NULL, so `tz is null and tz =
  'bad'` gave 0 rows; PostgreSQL 18.6 types the literal when parsing and
  refuses the statement. As before, a statement that reads no row
  (`where 1 = 0 and tz = 'bad'`) still gives 0 where PostgreSQL refuses
  it.
- A/B against main 445bc9cf (built from `git archive`), medians of 3
  rounds, binaries alternating: TPC-H total 1.002, all 22 checksums the
  baseline's; q1 0.988 (2-ii's 1.1% back), q6 1.005, q20 1.013 (1.012 to
  1.027 per round in `run.sh`, but 0.986 in a direct A/B of q20 alone, 15
  runs per server, three rounds; its per-run path runs the same work, so
  probably layout). 35 queries 1.004 (filt_agg 1.037 on 27 ms, the rest
  within 2%). Point selects 0.989/0.996/0.993 at 1/8/32 clients (prepared:
  none of 2-iii's code runs per execution; 2-ii saw the same against
  540106ec), updates 1.000/1.002/0.989. `timeLitOid` first asked for the
  parameters' types (`ptypesOf`, a copy) for every parameter compared;
  reading them last took q20 from 309.0 to 302.8 ms (main 306.2).

**Where 2-iii left off, and how to start 2-iv.** All in `lexdb_exec`
unless named; search for the names.

- The batch compiler is as 2-ii left it (`bCompile`/`bCompileD` over
  `BX`, `bCompileCond`, `bCompileOut`, `bCompileX`/`bxOf`, `bxConst`,
  `bxFixed`, `cmpOf`, `arithOf`, `bAndOr`), with the comparisons'
  kernel choice inline in `bCompileD`'s `BX.Op` arm and the IN list's,
  both through `bCmpKinds`; `colOf` and `bValCol` find the columns.
- 2-iv is `bGenOf`: it binds the expression again per run
  (`lexdb_bind.bindExpr` with `direct` false, the batch row's places as
  `slots`, parameters as constants for `bGenVals`' constant shape). The
  plan already holds the expression bound by query column (`Query.cc`/
  `cp`, `Sel.ox`); 2-iv re-slots that tree (a `BX.Col(i)` to the place
  of query column `i` in the batch row) instead of binding again, and
  reads a `Param` slot from `Mats.ce` where `bGenVals` wants a constant.
  Measure q20 (8,508 subquery runs) and q18's HAVING as well as q1, q6.
- Types: `BX` nodes still carry none (see the decision above). If 2-iv
  or the function library needs a node's type, compute it once in
  `bindSel` (where plans are bound), not in `bindExpr`, which `bxOf`
  runs per run.
- The resolve cast is `timeLitOid`, called from `resolve`'s comparison
  arm and its `in` call. Its parameters' types come from `ptypesOf`
  (the statement's, then the refs' `refOids`); a statement run with
  fewer types than values is not cast and goes to the row path.
- Traps, build, suite and A/B are as 2-ii's paragraph says. The suite is
  188 tests now (`exec_timelit`). A differential check that helped:
  the same queries (date, timestamp, timestamptz, time and interval
  columns against literals, parameters, other kinds, IN lists, EXPLAIN)
  in UTC, Asia/Kolkata and America/New_York, batches on and off,
  compiled against main's sources and the branch's, outputs diffed.
  For one query, a server per binary on the TPC-H data with the query
  run 15 times through psql (median), three rounds alternating, gave a
  steadier number than `run.sh` did for q20.

**2-iv as built: `bGenOf` re-slots the plan's bound tree.**

- `bGenOf(x: &BX, kinds, base, need, ce)` takes the tree the plan bound
  over the query's columns by place and re-slots it
  (`lexdb_bind.reslot`): a `BX.Col(i)` becomes `Col(s)`, where `s` is the
  place of query column `i` in the `BGen`'s own row (`BGen.cols[s]` is the
  batch's column `i - base`), in first-read order, as `bindExpr` with
  `direct` false numbered them. No name is looked up and no function is
  bound again (`typing()`, `fnBind`); the walk only copies.
- Parameters stay slots. The `BGen` gets the run's `CEnv` (`Mats.ce`: its
  session, transaction start and zone), with its parameters copied only
  when the tree reads one (`reslot`'s `par`), as `outC` does for
  `Sel.oxParam`. `bGenVals`' "column op constant" shape takes a
  `BX.Param` given in that `CEnv` as its constant (`cxLit`), so `col ||
  $1` keeps the shape it had when parameters were bound as constants.
- Where the tree comes from:
  - a level's conditions: `bCondNode(q, m, k, i, post, kinds, base,
    need)`, which reads `Mats.cc`/`cp` or `Query.cc`/`cp` as
    `bCompileCond` does (else `bxOf`), then `bCondOf`: the batch kernel
    when `bCompile` gives a boolean, else `bGenOf` of the same tree. It
    serves the first level (`bLevelPlan`) and the joins (`bJoinPlan`'s
    conditions and post).
  - outputs: `outNodeOut` (`Sel.ox`; else `bxOf`, which is a plain column
    the plan does not bind) and ORDER BY keys `outNodeX` (`bxOf`: the
    plan holds no binding for them), both into `outNode(x: &BX, ...)`,
    which tries `bCompile` and then `bGenOf` of the same tree.
- Deleted: `bJoinCond` (now `bCondNode`), `bLevelPlan`'s inline copy of
  it, `bCompileOut` (now `outNodeOut`), `bGenOf`'s `Expr`, `params` and
  `seq` arguments, and the `cenvOf(seqEnv(st, txn))` it made per
  `BGen`. Per run, a condition or output that falls back to `Gen` is
  bound once (or not at all, when the plan holds it) where it was bound
  twice before (`bCompileX`, then `bGenOf`).
- No change in results. A tree the plan could not bind (`None`: a
  subquery, a correlated reference, a function only `eval` evaluates)
  gave `None` from `bGenOf`'s own `bindExpr` too: the same functions
  decide both (`bindIn`, `hasCorr` implies a subquery call). A parameter
  past the ones given is the same error from `bxEval` as before.
- No types added: no consumer needed one. `bGenVals` reads a constant's
  value and the batch's kinds, as before.
- Lines: `lexdb_exec` 30522 to 30549 (+27, mostly the new entry
  points' comments), `lexdb_bind` 704 to 755 (`reslot`).
- A/B against main 3457f377 (built from `git archive`), medians of 3
  rounds, binaries alternating: TPC-H total 0.999, all 22 checksums the
  baseline's; q1 0.986, q6 0.994, q18 0.984, q20 0.995 (`run.sh`).
  Direct A/B (`qab.sh`, 15 runs per server, 7 for q1): q20 1.011
  (368.4 to 372.6 ms, all three rounds), q18 1.008 (109.9 to 110.8),
  q1 1.002, q6 0.998, q22 1.000. 35 queries 1.006 (window 1.036 on
  279 ms, pk_point20k 1.021, the rest within 1.3%). Point selects
  0.998/0.987/0.997 at 1/8/32 clients, updates 0.997/1.000/1.023.
- None of the changed code runs per run in q20, q18, q1 or q6: a build
  printing in `bGenOf` showed no call in q20, q18, q1, q6, q7, q8 and q13,
  and 2 per run in q22 (its `substring` IN a list), which is level. So
  q20's and q18's 1% in the direct A/B is not `bGenOf`; layout, most
  likely, as 2-iii's q20 was (not verified with a profile).

**Where 2-iv left off, and how to start item 3 (the function library).**
All in `lexdb_exec` unless named; search for the names, since line
numbers move.

- What evaluates a bound call today: `bxEval`'s `BX.Call` arm evaluates
  the arguments and calls `callRef(fb, vs, ce)`. `callRef` switches on
  `FnRef.way` (`lexdb_bind.FN_ONE`: `call1(id, ...)`; `FN_COALESCE`:
  `coalesceOf`; `FN_SUBSTR`: `substrOf`; `FN_CONCAT`: `concatOf`), then a
  dialect function (`FnRef.dialect`: `callDialectFn`, `lexdb_tsqlfn`,
  `lexdb_orafn`), then `callAt(name, vs, now, zone)`. `bGenVals` has its
  own fast shape for `FN_ONE` over one column (`call1`, else `callAt`).
  `eval`'s `Expr.Call` path reaches `callAt` by name too (search
  `callAt(`; `call(` is `callAt` in UTC with no clock).
- `callAt` is a chain of name tests: `callMisc(name, vs)`, then
  `callFn(name, vs, z)`, then a few inline (`gen_random_uuid`, `random`,
  `encode`/`decode`), then `callTime(name, vs, now, z)`, then `array`,
  the quantified comparisons (`lexdb_sql.isQuant`), `in`, and more down
  to its end. Each returns `Option` (None: not mine), so a call that
  reaches the end has matched dozens of strings. Sizes on 3457f377+2-iv:
  `callFn` ~490 lines, `callAt` ~190, `callMisc` ~160, `callTime` ~125,
  `call1` ~40 (with `fn1Of` and the `F1_*` ids).
- The binding side: `fnRefOf(name, n)` (exec, given to the binder as
  `Typing.fnBind` by `typing()`) decides `FN_NONE` (what only `eval`
  evaluates: aggregates, window calls, `isSeqFn`, `isSessFn`,
  `isAdvFn`, `lexdb_sql.isCatFn`, `current_schema`, `#tdiv`, `#tavg`)
  and otherwise the way. `FnRef` (`lexdb_bind`) is `name`, `way`, `id`,
  `dialect`. Item 3's "`FnRef` gains the signature's entry point" is
  where a function value (or an id into a table in `lexdb_ops`) goes;
  `reslot` copies `FnRef` field by field (it is not a copy type), so a
  new field must be added there too.
- What moves and what stays: the pure functions (text, numeric, time,
  `encode`/`decode`, arrays, `call1`'s) move to `lexdb_ops` (or a module
  beside it, below the binder), split per signature so nothing matches
  a name per row. The session-bound calls stay in exec (sequences,
  catalog, settings, advisory locks: `isSeqFn`, `isSessFn`, `isAdvFn`,
  `isCatFn`; these are already `FN_NONE`). A time function gets the zone
  and transaction start as arguments, as `lexdb_ops` takes them today
  (a closure for the zone in `binOp`, `CEnv.now`/`zone` in `callRef`).
- Before moving, list each function's helpers: `callFn` and `callMisc`
  call many exec helpers (`text`, `intArg`, `substrOf`, `concatOf`,
  formatting and regex helpers); each moves with its callers or is
  already in `lexdb_ops`. 2b's rule holds: exec calls `lexdb_ops`
  directly and keeps a `pub` forwarder only for names other modules and
  tests use. A forwarder on a per-row path measurably slowed q20, and a
  string match on a per-row path cost q18's HAVING (1.5M `binVal`s).
- Traps:
  - `BX` and `FnRef` are owned and not copy types: match a borrowed
    `BX` and build a new one inside the arm (`reslot`), and copy a
    `FnRef` by its fields.
  - The suite compiles each test as it runs it: do not edit the sources
    while it runs.
  - `bxOf` binds per run (join, group and ORDER BY keys, aggregate
    arguments): nothing costly may be added to `bindExpr`. A per-call
    entry point found by name belongs in `fnRefOf` only if it is a cheap
    lookup; else bind once in `bindSel`.
  - Errors must keep their text and SQLSTATE: the row path (`eval`)
    and the batches (`bxEval`, `bGenVals`) both reach the library, and a
    batch whose row gives an error goes to the row path, which must give
    the same one.
- Gates: the suite (188), TPC-H all 22 (checksums against
  `~/tpch/out-baseline-1744ef99`, fields [0] and [8]; q1, q8 and q17 show
  "different result" in `run.sh`'s text check on every binary: formatting,
  not checksums), q1, q6, q20 (8,508 subquery runs), q18's HAVING, the
  35 queries (five fail on both binaries with la/base2's data: known) and
  OLTP point selects and updates. Methods, scripts and build as 2-ii's
  paragraph says; for one query, `qab.sh QFILE N LABEL...` (a server per
  binary on `~/tpch-w/bind/lexdb`, the query N times through psql, the
  median, three rounds alternating; take `flock ~/tpch/.bench.lock` and
  turn boost off with `sudo /usr/local/sbin/cpu-boost off` first, as
  `run.sh` does, and on after). A copy of `qab.sh` is in
  `~/tpch-w/bind/bench`. Function-heavy queries to add: q22
  (`substring` IN a list), q7's and q8's `extract`, q13's `like`, and the
  35 queries' text ones.

**Item 3 as built: the function library is `lexdb_lib`, one entry per
signature.** Three commits on `redesign/bind` (6df59bd7: call1's and
callTime's functions; 03e2c288: callFn's; 714fa6d0: callMisc's and the rest
of callAt's, and `FnRef.f`).

- `lexdb_lib` (new, 2189 lines) sits beside `lexdb_ops`, below the binder
  and the executor. `imports.py` has its rule (`LIB_MAY_IMPORT`: ops' list
  plus `lexdb_ops`, `lexdb_like`, `lexdb_rows`, `lexdb_access`,
  `lexdb_catalog`), and the binder may import it.
- An entry is a function value of one of two types:
  - `LibFn = fn(name, args, now, zone)`: `name` as called, for its errors;
    `now` the transaction's start (0: the clock); `zone` the session's.
  - `Lib1 = fn(name, value)`, a function of one argument given a value not
    NULL (the caller gives NULL for NULL). It needs no argument list, so
    a bound call and the batches' one-column shape (`bGenVals`) call it per
    row without allocating.
- Finding an entry:
  - `entry1Of(name)` gives the `Lib1` of a one-argument name: call1's
    (lower, upper, the trims, length, octet_length, abs, round, floor,
    ceil, trunc, sign), sqrt, cbrt, exp, ln, log10 and log (with callFn's
    numeric semantics), the 22 trigonometric functions, and `#ci`, `#pad`
    and `#cifold`.
  - `entryOf(name, n)` gives a `LibFn` for every name and count. It is the
    first of the old chain (callMisc, callFn, the inline ones, callTime,
    the rest of callAt) that took that name and count, so where names met,
    the old order holds (`to_timestamp` of two arguments is to_char's kin,
    else seconds since 1970). It gives `restFn` when none does.
  - `rest` is what callAt gave at its end: NULL for one NULL argument, else
    42883 "function X with n arguments does not exist" (`noSuch`).
- Split per signature: no entry tests its name per call.
  - Names that branched inside one arm are an entry each: lpad/rpad,
    regexp_match/matches/like, the regexp splits, array append/prepend/cat,
    remove/replace, position(s), `@>`/`<@`/`&&`, mod/div/gcd/lcm, to_date
    and to_timestamp, the `~` operators, the trims of two, greatest/least,
    left/right, like/ilike, encode/decode.
  - Shared bodies take a code instead of the name: `trig` (`T_*`),
    `intMathOf` (`IM_*`), `cutOf` (`CUT_*`), `floatMath` (`M_*`),
    `arrCmpOf` (`AR_*`).
  - A quantified comparison ("any =", "all not ilike") gets its operator
    from the name once (`quantEntry`, twenty entries over `quantOf`).
    Before, `quantified` matched the operator's text for every element.
- What a value a function does not take gives: where the old chain
  answered "not mine" from a value (abs or round of a text, isfinite of a
  number, `regexp_replace` with a text fourth argument and more than four
  arguments, round of two with a non-integer scale), the entry returns
  `rest`/`noSuch`. That is what the chain reached, since nothing later in
  it took those names. The typed functions (`to_hex`, array_remove,
  array_replace, array_position(s), `@>`, `<@`, `&&`) count their
  arguments without resolve's hint (`argsOf`), as callFn did. Other
  functions no longer look for a hint: resolve adds one only to
  `TYPED_FNS`.
- `lexdb_bind.FnRef` is `name`, `way` (`FN_NONE`, `FN_GEN`, `FN_ONE`),
  `f` (the `LibFn`), `f1` (the `Lib1`; `lexdb_lib.no1` when not
  `FN_ONE`), and `dialect`.
  - `fnRefOf` finds both entries once per bind: two string matches,
    `entry1Of` and exec's `entryAt`. `bindExpr` is unchanged.
  - `FN_COALESCE`, `FN_SUBSTR`, `FN_CONCAT` and the call1 `id` are gone.
  - `reslot` copies `f` and `f1` with the other fields.
- Evaluating:
  - `callRef` calls the dialect's function first when `dialect`
    (`callDialectFn`: `lexdb_tsqlfn`, `lexdb_orafn`), then `f1` for
    `FN_ONE` (NULL for NULL), else `f`.
  - A one-argument call of a T-SQL or Oracle name the library also takes
    is `FN_ONE` now. `bGenVals`' one-column shape skips it
    (`!fb.dialect`), since its dialect call comes first.
  - `eval`'s way in is `callAt` (and `call`, in UTC with no clock). It
    finds the entry per call: `entry1Of` for one argument, else
    `entryAt`. That is two matches where the chain matched dozens of
    texts.
- Stays in exec:
  - The session-bound calls, which `fnRefOf` makes `FN_NONE` and `eval`
    runs: `seqCall` (`isSeqFn`), `sessCall` (`isSessFn`), `advCall`
    (`isAdvFn`), `callCat` (`lexdb_sql.isCatFn`, `current_schema`), `#tdiv`
    and `#tavg`.
  - The dialect functions (`callDialectFn`).
  - `format_type` and `pg_size_pretty` (`entryAt`, `formatTypeFn`,
    `sizePrettyFn`), because they read `lexdb_pgcat` and `lexdb_pg`, which a
    core module below the binder may not import.
- Deleted from exec: call1, fn1Of, `F1_*`, arithInt, callFloat, callTime,
  truncTstz, atTimeZone, tsAt, tsOfVal, callFn, reFlagsAt, noGlobal,
  posArg, decScale, gcdInt, hintOids, arrOf, partsVal, elemVal, elemIs,
  hintElem, arrContains, fArg, the sind/cosd helpers, trig, isTrig, intArg,
  srfMark, callMisc, callAt's chain, substr, substrOf, concatOf,
  coalesceOf, likeMatch, quantified, randomFloat, randomUuid, getrandom,
  encodeBytes, decodeBytes, ciVal, ciFold, jsonText, and the `unicode` and
  `base64` imports.
  - exec calls `lexdb_lib.intArg`, `srfMark` and `likeMatch` (the batches'
    LIKE) directly; `HINT` and `SRF_MARK` are `lexdb_lib`'s.
  - No `pub` forwarder was needed: no other module or test used these
    names.
- Lines:

  | Module | Before | After |
  |---|---|---|
  | `lexdb_exec` | 30549 | 28901 |
  | `lexdb_lib` | (new) | 2189 |
  | `lexdb_ops` | 1424 | 1424 (comment) |
  | `lexdb_bind` | 755 | 754 |

  The library is larger than what left exec because of the per-signature
  wrappers and their comments.
- No change in results:
  - the suite (188);
  - a differential battery, compiled once from main 71b196b9 and once from
    the branch, outputs diffed: about 150 calls and their errors, over
    NULLs, numbers, texts, dates, timestamps, arrays and bytea, through
    the batch shapes (5,000 and 20,000 rows), two zones, and errors
    raised on the batch path. Messages and
    SQLSTATEs were both compared (`VERBOSITY verbose`, 41 errors);
  - TPC-H's 22 checksums.
- Not done (later slices):
  - no node types and no `OpDef` metadata (strict, volatile, canFail);
  - `immutableName` and `bxFixed` still decide by name;
  - the binder does not yet fold constants with the library;
  - the dialect functions (`lexdb_tsqlfn.call`, `lexdb_orafn.call`) still
    match names per call.
- A/B against main 71b196b9 (built from `git archive`), binaries
  alternating, medians of 3 rounds:
  - TPC-H (`run.sh`, 3 runs a round): total 0.981; all 22 checksums are
    the baseline's.
    - q22 0.612 (754 to 461 ms) and q16 0.801 (724 to 580 ms), the same
      in all three rounds. q22's `substring(c_phone from 1 for 2) IN
      (...)` and q16's `NOT LIKE`, `IN` and `NOT IN` reach the library
      per row: before through callAt's chain of name tests, now through
      one entry. That this is the cause was not checked with a profile.
    - q9 0.975, q7 0.984, q5 1.014; the rest within 1.2%.
  - Direct A/B (`qab.sh`, 15 runs per server, 7 for q1, three rounds):
    q20 1.002, q18 0.994, q1 1.009, q6 1.001, q22 0.608, q7 0.991, q8
    0.987, q13 0.993.
  - The 35 queries: total 1.000, expr_mix 0.958.
    - distinct2 (`select distinct a, city from w`) is 1.107 in all three
      rounds of `ab35.sh` (253 to 280 ms), and window 1.032 (2-iv saw
      1.036 there). distinct2 calls no function. A direct run, a server
      per binary with 5 runs each, gave 252 against 257 ms (1.02). perf
      (`LXL_NATIVE_MAP`) shows the same functions in the same shares on
      both (sortBatches, encBytesKey, malloc, dup, colsInto); none of
      them is changed code. So layout and allocation, most likely; not
      resolved further.
  - OLTP, medians of 3:

    | Clients | Point selects | Updates |
    |---|---|---|
    | 1 | 0.995 | 0.994 |
    | 8 | 1.001 | 0.999 |
    | 32 | 0.997 | 0.989 |

**Where item 3 left off, and how to start 2d (scope and naming).** 2d
moves name resolution out of the executor into the binder, so that
expressions refer to columns by slot and `eval` stops finding columns by
name (4.4.1's table: "`resolve`/`resolveName`/`Scope` frames, star, GROUP
BY and ORDER BY resolution move to the binder; columns by slot;
`Query.cols` as `BCol`s; `eval`'s name lookup (`colIndex`) gone"). All of
it is in `lexdb_exec` unless named. Search for the names, since line
numbers move.

- What resolves names today:
  - `resolve(x, cols, n, sc: mut &Scope)` rewrites an `Expr` over a
    query's columns. It turns a bare or qualified name into the
    `alias.column` name `cols` holds (`resolveName`, `colPart`, `DUPSEP`
    for a name repeated in one FROM item), finds outer references
    (`outerRef`: a correlated name becomes a parameter past `Scope.base`,
    recorded in the frame's `refs`/`refOids`), and inserts the binder's
    casts (2a's common types, `timeLitOid`, char(n)'s `#bptrim`/`#bppad`,
    the collation calls `collateCall`/`#ci`/`#pad`). It is called about
    30 times (`resolve(`).
  - `Scope` (with `Frame` per query level: `cols`, `exact`, `refs`,
    `subRefs`, `hidden` for a non-LATERAL FROM subquery) also carries
    planning state that is not naming: privileges (`asRole`, `whos`,
    `scCheck`), `looks`, `early`, `locking`, `ordBy`/`ordLim`,
    `noRefKeys`, `works` (recursive CTEs). 2d should split the naming part
    (frames, base, ptypes, coll) from the planner's hints rather than move
    `Scope` whole.
  - Star and the select list: `selectCols`/`itemCols` (select items to
    `OutCol`s and expressions). ORDER BY: `resolveOrder` (output names and
    positions first, then input columns). GROUP BY: `resolveGroup`
    (output names, positions, expressions). `endScope` closes a frame
    into its `Query`.
  - The typing helpers that read a `Scope` (`numPS`, `exprColl`,
    `textOrUnknown`, `isTextExpr`, `cmpKind`, `exprKind`, `ptypesOf`,
    `unifyVals`) are the binder's work too. They use `lexdb_bind.exprOid`
    with the frame's columns.
- What reads names at run time: `eval`'s `Expr.Col(name)` arm
  (`colIndex(&env.cols, &name)`, a linear search per row; 80 `colIndex(`
  sites in all), `Query.colAt` (`levelOf`'s map), `keyedCol`, and every
  pass that matches `Expr.Col` by name (`bpFix`, the planner's key
  finders). The bound path (`BX.Col(i)`) is by slot already: `bindExpr`
  maps names to places through `cols` once per plan (`bindSel`/
  `bindQuery`) or per run (`bxOf`).
- A way in, in slices that each keep results and speed:
  1. A `BCol` (slot, name, spell, `Ty`) list per query level, built where
     `Query.cols` is built (`buildQuery`), with `cols` derived from it.
     Nothing reads it yet.
  2. `resolve` emits slots as well as names (a resolved `Expr.Col` that
     carries its slot, or a side table), so that `bindExpr` stops
     searching `cols` by name.
  3. Move `resolve`, `resolveName`, `outerRef` and the select, ORDER BY
     and GROUP BY resolution into `lexdb_bind`, with the naming part of
     `Scope`. exec keeps the planner's hints.
  4. `eval` reads slots; `colIndex` goes. `eval` still runs what does not
     bind (subqueries, aggregates, DML's expressions), so every `Env`
     must carry rows in its query's slot order. Check `Env.cols` users
     first.
- Traps:
  - `Expr.Col`'s name is load-bearing beyond lookup: the planner matches
    columns by name for keys, implied equalities and index paths
    (`keyedCol`, `colAt`, `rangePath`). Keep the name alongside the slot
    until those read slots.
  - Correlation: an outer reference becomes a parameter numbered past
    `Scope.base` (`refs`, `Query.base`, `subFixed`, `isSubCall`). The
    subquery machinery (`SubPlan`, the `#in` and other sub calls, `subValue`) and
    hashing on `refs` (9.104 `noRefKeys`, `keyConj`) depend on that
    numbering.
  - A repeated column name in one FROM item is `name DUPSEP position`.
    USING and NATURAL merge columns (`usingSide`, and the join handling in
    `buildQuery`). A view's text is resolved under its owner (`asRole`).
  - `bindExpr` runs per run on the `bxOf` paths (join, group and ORDER BY
    keys, aggregate arguments): keep it cheap (2b lost 5% on q20 typing
    there). `fnRefOf` now finds the library entries there (two string
    matches per call node).
  - `BX` and `FnRef` are owned and not copy types. `FnRef` holds function
    values (`f`, `f1`); copy it by its fields (`reslot`).
  - The suite compiles each test as it runs it: do not edit the sources
    while it runs (about 3.5 minutes at `-j 2`).
- Gates, as for item 3:
  - the suite (188);
  - TPC-H all 22, checksums against `~/tpch/out-baseline-1744ef99`
    (fields [0] and [8]; q1, q8 and q17 show "different result" in
    `run.sh`'s text check on every binary: formatting, not checksums),
    with q20 (8,508 subquery runs), q18's HAVING, q2, q17, q21 and q22
    (correlation) watched;
  - the 35 queries (five fail on both binaries with la/base2's data:
    known);
  - OLTP point selects and updates (prepared: the plan cache must still
    hit; `PlanCache`).
- Methods: as 2-ii's and 2-iv's paragraphs say (`tpch_ab.sh`/`tpcmp.py`,
  `ab35.sh`/`cmp35.py`, `oltp.sh`, `qab.sh`, all in
  `~/tpch-w/bind/bench`). The baseline is built from `git archive <main>
  lexell/cmd`. For a differential check of naming, compile the same SQL
  over joins, USING/NATURAL, LATERAL, correlated subqueries, views, CTEs,
  ORDER BY/GROUP BY by position and by output name, and star with
  repeated names, against main's sources and the branch's, and diff the
  outputs (`probe.sh`-style: a fresh data directory per binary, psql with
  `ON_ERROR_STOP=0`, so errors are compared too).

**The rest of 2c, planned:**

1. **Bind once per plan.**
   - `BX.Param(i)` reads the run's parameters (`CEnv` gets an owned copy
     per run), and the binding moves from `cxsOf`, the output plan and
     `bGenOf` (per run) into the plan (`Query`, `Sel`), done when it is
     built.
   - Node types are then computed once, bottom-up.
   - `bGenVals`' constant shape reads a `Param` slot as a constant.
2. **`bCompile` builds from `BX`.**
   - `BNode`'s typed kernels (Arith, Cmp, DArith/DCmp, Like, InVals) are
     chosen from the node's bound type instead of `bCompile`'s own
     typing.
   - `Gen` becomes a `BX` step.
   - `BNode`'s duplicate typing and `bTimeVal` are deleted.
   - Gate: the scan-heavy queries (q1, q6, the 35-query suite's scans).
3. **The function library moves into `lexdb_ops` per signature.**
   - `callAt`, `callFn`, `callMisc`, `callTime`, `call1` move; the
     session-bound calls (sequences, catalog, settings) stay in exec.
   - `FnRef` gains the signature's entry point.
   - (Built, in `lexdb_lib` beside `lexdb_ops`: see "Item 3 as built".)

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

### 4.9 Everything runs in chunks

The inventory (lexdb-constructs.md) lists 13 "row-only" features. They mix
two different things:

- **Constraints on where and in what order an expression is evaluated:**
  - exactly once per qualifying row;
  - in input order;
  - not on rows past a LIMIT.
- **A true dependency of one row on the one before it.**

Neither needs a row-at-a-time interface. Batching is about the size of the
interface: one call per chunk, not per row. An operator with a sequential
dependency keeps the chunk interface and runs a plain loop inside it.

| Feature | In chunks |
|---|---|
| Sequences, identity defaults | Reserve a block of n values per chunk (one sequence update), assign them in selection order |
| Volatile functions, `set_config`, advisory locks | One call per selected row, in order, in a Project placed where the row set is final: after every filter and after Limit |
| Correlated subqueries | Unnested to joins (step 5). What remains runs as a batched dependent join: dedupe the chunk's correlation values, run the inner plan once per distinct value or with a chunk of parameters, join back. bRange already does this for index lookups. |
| FOR UPDATE / NOWAIT / SKIP LOCKED | A LockRows operator locks a chunk's keys in key order. SKIP LOCKED clears locked rows from the selection before Limit counts them. The rerun after a wait stays in layer 7. |
| RETURNING, OUTPUT | The DML operator writes a chunk and emits a chunk of the written rows |
| MERGE clauses | First matching clause: evaluate each clause's condition on the rows no earlier clause took (selection vectors), then one write per clause per chunk |
| ON CONFLICT | Look up the chunk's keys at once (getMany) and find duplicates within the chunk with a hash. DO NOTHING: the first occurrence wins. DO UPDATE: a second hit on a row is PostgreSQL's cardinality error, so there is no row-to-row dependency to honour. |
| CHECK | A vector predicate |
| UNIQUE, FK | Batched probes plus a hash of the chunk's own keys. Deferred checks collect keys and check them at commit in one batch. |
| UPDATE/DELETE TOP (n), `batch_rows` | A Limit in the DML pipeline (truncates the selection) |
| T-SQL `SELECT @v = f(@v)` | A fold operator. Common forms become aggregates: `@v = @v + x` is a sum, `@s = @s + col` an ordered string_agg, `@v = col` the last value. The general form is a loop inside the operator. |
| MATCH_RECOGNIZE | Partitions are independent. DEFINE predicates that don't use PREV/NEXT or running aggregates are computed per chunk as a bitmask per variable, and the pattern automaton then runs over the bitmasks |
| DISTINCT ON, WITH TIES, ROWNUM, MIN/MAX by index | Properties of order the optimizer preserves. ROWNUM is a running counter. WITH TIES compares with the boundary row. TOP PERCENT counts first (two phases). |
| WAIT n SECONDS | Statement-level rerun. The query inside runs in chunks |

Two rules for the planner and executor follow:

1. **A volatile or side-effecting expression is evaluated exactly once per
   row, where its row set is final.** It is never evaluated speculatively on
   a chunk that a later filter or Limit will cut. This also fixes the
   double-evaluation bug the inventory found, where the batch filter calls
   `random()` and then the row path calls it again.
2. **Order is a plan property.** An operator that needs order states it, and
   the optimizer keeps it or adds a Sort. Nothing relies on the row path
   happening to run in order.

So the target is that every operator takes and gives chunks. "Row-only"
survives only as a loop inside an operator, never as a separate path.

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
