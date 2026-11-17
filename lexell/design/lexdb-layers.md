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
| `One`, `Sub(view, src, plan)` | no FROM; a FROM item that is a query | added in 2e slice 1: `Sub` renames its plan's outputs into the joined row (alias.column at the row's slots); `CteRef(id, work)` also stands for a recursive CTE's working table |

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
| 2e (slice 1 built) | The binder emits the logical plan for SELECT and DML sources; `planSelect`/`buildQuery` read it instead of the `Stmt` | step 3 then turns it into the operator tree |

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

**2d slices 1–2 as built: a `BCol` per column, and each resolved column
carries its slot.** One commit on `redesign/bind` (65cf9972), from main
285a089f.

- Slice 1, `lexdb_bind`:
  - `Ty` (`oid`, `mod`, `coll`, `collLevel`, `notNull`) and `BCol`
    (`slot`, `name`, `spell`, `ty`), with `tyOf(TypeName, coll, notNull)`
    and `bcolOf(slot, ColDef)`. `mod` is the design's: numeric
    `p << 16 | s`, varchar/char `n`, a time type's precision; -1 none.
  - One departure from the design: `Ty.coll` is the collation's name as
    written (`ColDef.coll`'s), not an id, because there is no collation
    catalog to number them yet. `collLevel` is `CL_NONE`/`CL_DEFAULT`/
    `CL_IMPLICIT`/`CL_EXPLICIT`, and exec's `COLL_*` constants are now
    those. A column's level is `CL_IMPLICIT` for a text, else `CL_NONE`,
    as `exprColl` gives it.
- Slice 1, `lexdb_exec`:
  - `Query.bcols` sits beside `Query.cols`: `bcols[i]` is `cols[i]` at
    slot `i`.
  - Every column added to a query's row goes through `addCol`, which
    appends to both. That covers `buildQuery`'s FROM items and the
    semi-joins' hidden columns (`semiLookAdd` and `semiJoins`' `\x00sjN`
    keys and residual columns). Nothing else appends to a `Query.cols`.
  - `cols` is kept rather than derived from `bcols`. It still carries
    what the binder's column does not: `using`, `pos`, `def`, `identity`.
    Nothing reads `bcols` yet.
- Slice 2, a resolved column carries its slot:
  - `Expr.Col(str)` is `Expr.Col(str, int)`: the name (`alias.column`, as
    before) and its slot in the row it was resolved over, -1 when not
    known.
  - The parser and every construction outside resolution give -1 (134
    sites changed mechanically, in `lexdb_sql`, `lexdb_parse`,
    `lexdb_pg`, `lexdb_syscat`, `lexdb_bind` and `lexdb_exec`). The clones
    (`cloneExpr`, parse's `cloneE`, `clone`) keep the slot. A rename
    keeps it for the names it leaves alone.
  - `resolveName` returns the column's place instead of its name
    (`cols[i].name` is the name). Its callers changed with it:
    `orderedLevel`, `outerRef`, MERGE's `onCols`.
  - These give a slot:
    - `resolve`, `resolveOrder` and `resolveGroup` (their `Expr.Col`
      arms);
    - `colExpr`, which now takes the place, with FULL JOIN USING's
      COALESCE arguments found once by name;
    - star in `itemCols`, both the plain order and USING's order;
    - USING's ON;
    - `outerRef`'s ref: the outer frame's place, since a frame's `cols`
      are its query's in order;
    - the implied equalities (`q.slotOf`, the `colAt` map, else by name);
    - the semi-joins' renamed columns. `renameCol` takes the new name's
      slot: `semiLook`'s `first + j`, `semiJoins`' `first + w + j`, and
      ALTER TABLE -1.
  - An output column named in ORDER BY or GROUP BY (`resolveOrder`'s
    `Expr.Col(n, -1)`) has no slot, as it is not an input column.
- Slice 2, reading the slot: `lexdb_bind.colSlot(cols, name, slot)`
  replaces bind's `colAt`. It gives `slot` when `cols[slot].name ==
  name`, else the first column of that name, else -1. Its readers:
  - `bindExpr`'s `Expr.Col` arm (so `bxOf`, `cxsOf`, `bindSel`, `outC`
    and the window outputs);
  - `exprOid`'s `Expr.Col` arm;
  - the plain-column places of the outputs (`outC`, `bindSel`'s `col`,
    the windowed outputs' `at`, `winValues`' partition and order `at`).
  - Why the name is checked: expressions are typed and bound over other
    column lists than the one they were resolved over, so a slot alone
    can name the wrong column there. Examples are DML's target columns,
    index and CHECK expressions, and the `g.g` of the suite's `exec_*`
    tests. A check with a build that panicked on any mismatch found 40
    of the suite's tests doing this. In every one the name was absent
    from the list (slot set, no column of that name), so the old search
    found nothing too.
  - With the panic narrowed to a slot that names a different column
    than the first of its name, the whole suite passed. So where the
    name is in the list, the slot is the column the search finds.
  - TPC-H's 22 queries, counted with a build that logged each lookup,
    made 12,872 lookups. All of them took the slot, except 7 lookups of
    output names (`revenue`, `numwait`, and so on: ORDER BY by alias),
    which have no slot and miss as before.
- Deleted:
  - bind's `colAt`;
  - `bindExpr`'s `direct`/`slots` mode and `bindIn` (every caller passed
    `direct` true; `reslot` is the re-slotting way, as `bGenOf` uses it);
  - the callers' `var sl` lists;
  - `resolveName`'s second search in `outerRef` and `orderedLevel`.
- Found, not changed (both binaries): `ORDER BY s`, where `s` is an
  output alias and also an input column, takes the input column, so
  `select x, sum(id) s from a group by x order by s` fails with 42803.
  PostgreSQL takes the output column (findTargetlistEntrySQL92).
  `resolveOrder` tries input columns first. Slice 3 moves that rule; it
  should keep it unless the fix is its own commit with a test.
- The planner still matches columns by name (`keyedCol`, `levelOf`,
  `colAt`, `rangePath`, `bpFix`), and `eval` still finds a column by name
  per row (`colIndex`). Both are later slices' work. 74 `colIndex(` sites
  remain in exec.
- Lines:

  | Module | Before | After |
  |---|---|---|
  | `lexdb_exec` | 28901 | 28912 |
  | `lexdb_bind` | 754 | 798 |

- No change in results:
  - the suite (188);
  - TPC-H's 22 checksums;
  - a differential battery, compiled from main 285a089f and from the
    branch, outputs diffed: the same, 623 lines. It ran 83 statements, 14 of
    them errors, with errors in verbose form: joins, USING (inner, LEFT, RIGHT, FULL),
    NATURAL, repeated names in a FROM subquery, LATERAL, correlated
    EXISTS, NOT EXISTS, IN and scalar subqueries (one nested two deep),
    a view, CTEs (one recursive over a join), GROUP BY and ORDER BY by
    position, by output name and by expression, HAVING with a subquery,
    windows, DISTINCT ON, INTERSECT, row IN, UPDATE ... FROM, DELETE ...
    USING, ON CONFLICT, parameters through the extended protocol (psql's
    `\bind`) for a join and a semi-join, star over USING and over a view
    of a view, and the naming errors (42703, 42P01, 42702, 42712, 42803,
    42P10). The files are
    `~/tpch-w/bind/bench/naming/` (`naming.sql`, `run.sh BIN OUT`).
- A/B against main 285a089f (built from `git archive`), binaries
  alternating, medians of 3 rounds:
  - TPC-H (`run.sh`): total 1.001; all 22 checksums are the baseline's.
    - q1 1.022 and q18 1.028, the same in all three rounds.
    - q20 0.989, q2 0.994, q17 1.007, q21 0.998, q22 0.998; the rest
      within 1%.
  - Direct A/B (`qab.sh`, 15 runs per server, 7 for q1):
    - q18 1.000 (110.3 against 110.3 ms; q18's file in `qab.sh` runs
      110 ms against `run.sh`'s 1246).
    - q1 1.019 (2526 to 2573 ms, in all three rounds).
    - q20 0.997 (366.6 to 365.6 ms), q2 0.993, q17 1.003.
  - q1 under perf (`LXL_NATIVE_MAP`, 4 runs each): the same functions in
    the same shares on both binaries (dup, colsInto, vec_sum, bEval,
    checkedMul, vec_arith, batchGroupsIn). The hot functions are byte
    for byte the same size, at other addresses. None of the changed code
    shows, and q1 binds per run, not per row. So most likely layout, as
    2-ii's q1 (1.1% and 1.5%); not resolved further.
  - The 35 queries (`ab35.sh`, boost off): total 0.996.
    - grp_text 1.043 (115 to 120 ms, all three rounds). A direct run, a
      server per binary, 15 runs each, three rounds alternating: 111.9
      against 112.4 ms (1.004). Under perf the shares are the same.
    - pk_range100k 1.032 (31 to 32 ms); the rest within 2%.
  - OLTP, tps ratios, medians of 3:

    | Clients | Point selects | Updates |
    |---|---|---|
    | 1 | 1.002 | 0.999 |
    | 8 | 1.010 | 1.003 |
    | 32 | 1.009 | 0.980 |

    Main's updates at 32 clients ranged from 39.6k to 41.0k tps across
    its rounds, and the branch's from 39.4k to 39.8k. Point selects are
    level, so the plan cache hits; the cache itself was not inspected.

**Where 2d slice 2 left off, and how to start slice 3.** Slice 3 moves
name resolution into `lexdb_bind`: `resolve`, `resolveName`, `outerRef`
and the select-list, ORDER BY and GROUP BY resolution, with the naming
part of `Scope`. The planner's hints stay in exec. Results and speed must
not change; this is a move, not a rewrite. Everything named is in
`lexdb_exec` unless the note says otherwise. Search for the names, since
line numbers move.

- What is there after slice 2:
  - `Expr.Col(name, slot)` (`lexdb_sql`). `resolve` and its kin give the
    slot, -1 elsewhere.
  - `lexdb_bind.colSlot` reads the slot, after checking the name.
  - `Query.bcols` (`lexdb_bind.BCol`) is kept with `Query.cols` by
    `addCol`. Nothing reads it yet; slice 3 may make it the frames'
    column list.
- What moves (exec's names):
  - Names and scope: `resolveName`, `colPart`, `dotAt`, `DUPSEP`,
    `hiddenName`, `colExpr`, `usingSide`, `outerRef`, `refTyped`,
    `refParam`, `ptypesOf`, `endScope`.
  - The resolver itself: `resolve` (about 210 lines), `resolveOrder`,
    `resolveGroup`, `selectCols`/`itemCols`, `orderOut` and
    `checkGrouped` (GROUP BY's checks).
  - The typing helpers resolve calls: `timeLitOid`, `isBp`, `trimmed`,
    `bpCmp`, `bpCall`, `bpAssign`, `numPS`, `exprColl`, `cmpColl`,
    `Coll`, `collKeyOf`, `collateCall`, `cmpKind`, `textOrUnknown`,
    `isTextExpr`, `exprKind`, `unifyVals`, `isTypedFn`/`TYPED_FNS`,
    `isHint`, `oidType`, `isIntOid`, `isCmp`, and exec's wrappers of
    bind's (`exprOid`, `arrayConcat`, `isTextOid`, `typing()`).
  - Get the full list of what resolve calls first. Its body, cut out and
    run through `grep -o '\b[a-zA-Z_][a-zA-Z0-9_.]*('`, gives what must
    move with it or be passed in.
- The `Scope` split:
  - `Frame` is all naming: `cols`, `exact`, `refs`, `refOids`,
    `subRefs`, `subOids`, `subNames`, `subColls`, `subKinds`,
    `subReads`, `hidden`. It moves.
  - In `Scope`, `frames`, `base`, `ptypes` and `coll` are naming.
  - The rest are the planner's hints and stay in exec: `works`,
    `asRole`, `whos`, `target`, `looks`, `early`, `locking`, `ordBy`,
    `ordLim`, `noRefKeys`.
  - A way to split it: a `lexdb_bind.Names` record (frames, base,
    ptypes, coll) held by exec's `Scope` as one field, with
    `resolve(x, cols, n, nm: mut &Names)`. Then every `sc.frames`,
    `sc.base`, `sc.ptypes` and `sc.coll` in exec becomes `sc.names.…`.
    Count those sites first (`grep -c 'sc\.frames'`): they are many, in
    `buildQuery`, `planSub`, `planSelect` and the DML planners.
- Blockers to check before moving:
  - Import rules: `lexdb_bind` may import only `lexdb_base`,
    `lexdb_sql`, `lexdb_catalog`, `lexdb_dialect`, `lexdb_time`,
    `lexdb_float`, `lexdb_ops` and `lexdb_lib` (`tests/lexdb/imports.py`,
    `BIND_MAY_IMPORT`). resolve calls `lexdb_syscat.tsqlBlank` (T-SQL's
    `''` as 0), so move that function down or pass it in, as
    `Typing.fnOid`/`fnBind` pass the dialect's functions. Errors are
    `lexdb_base.DbErr`; exec's `e()` is `lexdb_base.err`.
  - `enumOrder` reads the store (an enum's order). It is called on
    resolve's result in `buildQuery`, not inside resolve, so it stays in
    exec, as do `planSub` (resolve does not plan subqueries: they come in
    as `#sub`/`#in`/`#exists` calls numbered by the frame's `sub*`
    lists, which `buildQuery` fills).
  - `outerRef`'s numbering (refs past `Scope.base`) and `endScope`
    (`q.refs`, `Query.base`) are what `SubPlan`, `subFixed`, `isSubCall`,
    `subValue`, `keyConj` and `noRefKeys` (9.104) depend on. Move them
    unchanged.
- Traps:
  - The slot is relative to the column list resolve was given. A
    frame's `cols` are its query's `q.cols` in order, but only when that
    query has subqueries (`buildQuery` fills `sc.frames[me].cols` only
    then). Keep `colSlot`'s name check until `eval` and every binder
    read one column list per query level (slice 4). Expressions are
    still typed and bound over other lists: DML's targets, index and
    CHECK expressions.
  - `resolveName` returns a place now. `cols[i].name` is the resolved
    name, and the first column of a name wins, as before.
  - A name repeated in one FROM item is `name DUPSEP k`. USING and
    NATURAL mark columns `USING_HIDDEN` and list FULL JOIN's other sides
    in `using`. `pos` is star's order after USING. A view resolves under
    its owner (`asRole`, the planner's: keep the view's planning in exec
    and only its naming in the binder).
  - `Expr.Col`'s name is still load-bearing (`keyedCol`, `levelOf`,
    `colAt`, `rangePath`, `bpFix`, `exprText`, `sameExpr`, `colNames`).
    Keep both fields.
  - `bindExpr` runs per run on the `bxOf` paths. Slice 2 made its column
    arm one compare; keep it so.
  - `BX` and `FnRef` are owned, not copy types. Copy a `FnRef` by its
    fields (`reslot`).
  - The suite compiles each test as it runs it: do not edit the sources
    while it runs (about 4 minutes at `-j 2`). That includes a source
    copy that the suite run reads. An instrumented copy elsewhere (a
    scratch tree with `cmd`, `tests`, `lib` and `tools`) is fine.
  - When waiting for a process, do not `pgrep -f` a pattern that also
    appears in your own waiting command line: it matches itself and
    never ends. Wait on the PID.
- Gates, as for slices 1–2:
  - the suite (188);
  - TPC-H all 22, checksums against `~/tpch/out-baseline-1744ef99`
    (fields [0] and [8]), with q20, q18's HAVING, q2, q17, q21 and q22
    watched;
  - the 35 queries;
  - OLTP point selects and updates.
  - q1 sits 1.5–2% from main on some layouts with no change on its path
    (2-ii, this slice). Confirm with `qab.sh` and a perf profile before
    chasing it.
- Methods:
  - `tpch_ab.sh`/`tpcmp.py`, `ab35.sh`/`cmp35.py`, `oltp.sh` and
    `qab.sh` are in `~/tpch-w/bind/bench`. The baseline is built from
    `git archive <main> lexell/cmd` into `~/tpch-w/bind/src-main`, run
    from there.
  - The differential naming battery is `~/tpch-w/bind/bench/naming/`
    (`run.sh BIN OUT [SQL]`: a fresh data directory, psql with
    `ON_ERROR_STOP=0` and verbose errors). Diff main's output against the
    branch's; add cases for whatever moves.
  - For a slot check, build a scratch copy whose `colSlot` panics when
    `slot >= 0` and the first column of the name is another one, and run
    the suite from that copy.

**2d slice 3 as built: name resolution in `lexdb_bind`.** Five commits on
`redesign/bind` from main 8f482ee7, each built and through the suite (188):
60cfbeeb (part A), cc6241ad (B), 4d74b02c (C), 7a0aecfe (D), and a last
commit with two dead wrappers deleted and this note.

- Part A, the split: exec's `Scope` holds `names: Names` (`frames`, `base`,
  `ptypes`, `coll`); the planner's hints (`works`, `asRole`, `whos`,
  `target`, `looks`, `early`, `locking`, `ordBy`, `ordLim`, `noRefKeys`)
  stay beside it. Every `sc.frames`, `sc.base`, `sc.ptypes` and `sc.coll`
  (62 sites) became `sc.names.…`.
- Part B, to `lexdb_bind`: `Names`, `Frame`, `resolveName`, `colPart`,
  `dotAt`, `DUPSEP`, `colExpr`, `usingSide`, `outerRef`, `refTyped`,
  `refParam`, `ptypesOf`, `isIntOid`. `outerRef` and `ptypesOf` take the
  `Names`. exec's `Frame` and `Names` are aliases (`type Frame =
  lexdb_bind.Frame`), so exec's `Frame{…}` literals did not change.
  `lexdb_bind` now imports `lexdb_base` (`DbErr`, its own `e()`) and
  `lexdb_catalog` (`hiddenName`), both in `BIND_MAY_IMPORT`.
- Part C, to `lexdb_bind`: `resolve(x, cols, n, ns: mut &Names)` and its
  closure: the char(n) rules (`isBp`, `bpLen`, `bpSide`, `bpCmp`,
  `bpKeeps`, `bpCall`, `bpAssign`, `trimmed`, `untyped`), `timeLitOid`,
  the collation rules (`Coll`, `exprColl`, `strongerColl`, `cmpColl`,
  `collOpName`, `collShown`, `cmpKind`, `collateCall`, `collKeyOf`,
  `textOrUnknown`, `isTextExpr`, `exprKind`, `noColl`), T-SQL's numeric
  typing (`PS`, `numPS`, `typPS`, `digitsOf`), `unifyVals`, `castConst`,
  `isCmp`, `subFixed`, `isAgg`/`AGGS`, `isWinFn`/`WIN_FNS`,
  `isTypedFn`/`TYPED_FNS`, `isHint`. exec's `COLL_*` constants are gone
  (bind's `CL_*`). exec calls the ones it still uses as `lexdb_bind.…`
  (eval's call arm calls `lexdb_bind.isAgg`).
- Part D, to `lexdb_bind`: `selectCols`, `itemCols` (star, USING's order,
  `exprName`), `resolveOrder`, `resolveGroup`, `orderOut` (now over the
  query's `cols`, not the `Query`), and `OutCol` with `label()`. exec's
  `OutCol` is a `pub` alias, so `lexdb_wire`, `lexdb_tds`, `lexdb_tns` and
  `lexdb_plsql` did not change (a method on the aliased type is found
  through the alias).
- How the dialect-specific parts come in, as function values on the
  `Names` (`newScope` sets them), not new imports:
  - `ty: Typing`: exec's `typing()`, for `exprOid`, `argOid`,
    `arrayConcat` inside resolve;
  - `blank`: `lexdb_syscat.tsqlBlank` (T-SQL's `''` as 0);
  - `constCast`: exec's new `constLit`, `castVal` with no session, which
    `castConst` used (a reg type's cast reads `lexdb_pgcat`);
  - `colScale`, `outScale`: exec's `typScale` and `exprScale` (an output
    column's `OutCol.scale` from `lexdb_parse.tsqlCode`, `lexdb_syscat`
    and `oraDecl`).
  They are on `Names`, not `Typing`, because `typing()` is built on every
  call of exec's `exprOid` wrapper and per run on the `bindExpr` paths;
  `Names` is built once per statement.
- The char(n) helpers that had no `Scope` take a `ty: &Typing`; exec's
  remaining callers (`bpFix`, DML's assignments through `bpAssign`) pass
  `&typing()`, as exec's `exprOid` wrapper did for them.
- `resolve`'s parameter is `ns`, not `nm`: its call arm binds `nm` to the
  function's name.
- Kept in exec, against the slice-2 note's list:
  - `endScope`: it writes `Query.refs` and the subqueries' `kind` and
    `readAs` (exec's types). It pops `sc.names.frames`.
  - `checkGrouped`: it reads `Query.levelOf` (the planner's levels, for
    the grouped primary key).
  - `typScale`, `exprScale`, `oraDecl` (dialect reads; passed in).
  - exec's wrappers `exprOid`, `arrayConcat`, `isTextOid`, `oidType`,
    `hiddenName`, `colIndex` (eval's: slice 4), `typing()`.
- `lexdb_bind` has its own private `colIndex` (first column of a name) for
  `colExpr`, `bpLen`, `timeLitOid` and `orderOut`; exec's stays for eval.
- Deleted: exec's `COLL_*` constants, `HINT` and its `isFloatOid` wrapper
  (unused after the move; the hint's comment moved to `TYPED_FNS`).
- The ORDER BY difference from PostgreSQL (an input column before an
  output alias of the same name: `select x as s, count(*) from a group by
  x order by s` gives 42803, as on main) is kept; the naming battery now
  shows it.
- Lines:

  | Module | main 8f482ee7 | A | B | C | D | last |
  |---|---|---|---|---|---|---|
  | `lexdb_exec` | 28912 | 28919 | 28655 | 27979 | 27825 | 27818 |
  | `lexdb_bind` | 798 | 798 | 1006 | 1688 | 1850 | 1856 |

- No change in results:
  - the suite (188) at every part; imports ok;
  - the naming battery: identical output from main and from parts A, B,
    C and D (623 lines). Extended for this slice by 32 statements (now
    844 lines, 15 errors): char(n) comparisons, IN, NULLIF and IS DISTINCT
    FROM; date literals and a date parameter; COALESCE, CASE, GREATEST and
    LEAST over mixed types; `coalesce(null::regtype, 'int4')` (castConst's
    reg path) and regclass; `pg_typeof`; array `||`; `to_hex` and
    `array_position` (the type hint); `= any(array[…])`; correlated
    char(n) and numeric outer references; IN subqueries text/varchar and
    int/numeric; the select list's derived names; `COLLATE "C"`; numeric
    division; ORDER BY by alias that is also an input column; GROUP BY
    qualified; three-way USING and FULL JOIN USING star; MERGE; RETURNING
    star and expressions. Identical on main and the branch (parts C, D
    and the last commit). The old file is `naming.sql.s2`.
  - T-SQL's paths (`blank`, `#tdiv`, `#tavg`, bit compares, `#bitint`,
    session collations) and the scale hooks are covered by the suite's
    `tds_*`, `exec_sqlcoll` and `exec_charcoll`, not by the battery (psql
    has no T-SQL session).
  - the plan cache, counted this time: a scratch build of main and of
    the branch that printed a line where `select` planned (`pc.plans +=
    1`) and where its loop over `pc.sels` hit, under `pgbench -M
    prepared`, 4 clients, 3 s of point selects then 3 s of updates: 8
    plans on both binaries, and every other select a hit (235,161 of
    235,169 on main, 240,070 of 240,078 on the branch at part D).
    Updates do not go through the cache (planned per run, on both).
- A/B against main 8f482ee7 (built from `git archive` into
  `~/tpch-w/bind/src-main`), binaries alternating, medians of 3 rounds:
  - TPC-H (`run.sh`, boost off by run.sh): total 1.003; all 22 checksums
    are the baseline's. q20 0.996, q2 0.988, q17 0.998, q21 1.002, q22
    0.989, q18 0.990; the rest within 1%, but q1 1.041 (2468 to 2569 ms,
    the same in all three rounds).
  - q1, looked into (`qab.sh`, boost off, 5 runs per server, 3 rounds):
    main 2478 ms; part A 2514 (1.014), B 2597 (1.048), C 2565 (1.035), D
    2513 (1.014), the last commit 2586 (1.043). The last commit changes
    no code that runs: it deletes two unused definitions (`HINT`,
    `isFloatOid`) and edits comments, and moves q1 by 2.9%. Part A only
    renames fields. So the shift follows the binary's layout, not the
    moved code (none of which runs per row in q1: resolve and the select
    list run once per plan).
  - q1 under perf (`LXL_NATIVE_MAP`, user samples, 4 runs each): the same
    functions on all three binaries. The difference is mostly in
    `lexdb_rows.newBatch` (69 samples on main, 701 on D, 734 on the last
    commit), all of it one store in `array(cap, Val.Null)`'s fill loop
    (identical code bytes on both), with smaller shifts in `dup`,
    `memcpy`, `rt_as_slice`, `realloc` and `batchGroupsIn`: where its
    memory lands (heap reuse, or 4K aliasing between the stack slot the
    loop copies from and the array), not resolved further. Worth a look
    by itself: a fill that touches fresh memory per batch.
  - The 35 queries (`ab35.sh`, boost off): total 1.002; every query
    within 2% but `join_lookup_agg` (3 to 4 ms, rounding) and scan2
    1.017.
  - OLTP (`oltp.sh`, boost off), tps ratios, medians of 3:

    | Clients | Point selects | Updates |
    |---|---|---|
    | 1 | 0.989 | 1.006 |
    | 8 | 0.988 | 1.008 |
    | 32 | 0.995 | 1.000 |

    Point selects at 1 client: main 65.4k to 65.8k, the branch 63.5k to
    65.6k. The instrumented check above ran 1-2% the other way (78.4k
    against 80.0k tps). Nothing moved runs on the cached path.
- Not done: the slot check (a `colSlot` that panics on a slot naming
  another column than the first of its name): resolve's slots were moved,
  not recomputed, and the naming battery is identical.

**After 2d slice 3: q1's drift, looked into.** q1 had moved +1.1% (2-ii),
+2% (slices 1-2) and +4% (slice 3) on merges that did not touch its path.
One commit on `redesign/bind` after main 4ca6a0d9: a scan's batch is used
again (`lexdb_rows.reuse`) in the grouped aggregate's scan.

- Not page faults. The guess was a first touch per batch (each value
  column's array from mmap or fresh top of heap). Over 5 q1 runs the
  server's `minflt` (`/proc/PID/stat`, all threads) did not move on main
  8f482ee7 or on slice 3 (3030 and 3028 before and after); `perf stat`
  gives 1 page fault on both. An array is 1,024 slots of a 64-byte `Val`,
  64 KB, under glibc's 128 KB mmap threshold, and the last batch's freed
  arrays serve the next.
- What moved: the same instructions (177.7G per 5 runs on both), 4.4% more
  cycles, the same L2, L3 and DRAM fills. `ls_bad_status2.stli_other`
  (a load that cannot take its data from an older store and waits for it)
  in `newBatch`: 1.85M per q1 on main, 23.9M on slice 3, nearly all at one
  load of the `array(cap, Val.Null)` loop. Each slot is a call of the
  `Val` glue `dup`: the caller stores the 64-byte argument as eight 8-byte
  moves and `dup` reads it as four 16-byte `movdqu` (a load over two
  stores is never forwarded), then the result goes back through a stack
  slot. About 600M such interlocks per q1 in all, `dup` the most.
- Why the binary decides it: the stack. Queries run on a task's stack,
  so a frame's offset in its page is fixed per binary, not per run.
  `newBatch`'s `rbp` is at page offset 0x100 on every earlier main
  (2iii, 2iv, i3, 2d12, 8f482ee7) and at 0x110 on slice 3 (parts D and
  last): exec's `select` frame went from 0x278 to 0x268 bytes (`Scope`'s
  layout, part A), and every frame under it moved 16 bytes. Same code
  bytes, the copies land 16 bytes over. The samples move between the
  loop and `dup` with it: with callers counted, the fill was about 7% of
  q1 on main and on slice 3 alike (one run each), and slice 3 padded back
  to 0x278 (two locals in `select`) put `rbp` back at 0x100 and moved the
  cost into `dup` (q1 2561 against 2576 ms; the padding also moved the
  code after `select`). So read "69 against 734 samples in newBatch" as
  where the stall is charged, not as the whole difference.
- The "dead code" commit: 7a0aecfe and b99601e0 build to the same code
  bytes at the same addresses; the binaries differ only in panic-location
  strings (line numbers, same lengths). Byte-identical copies of one
  binary in different files differ by up to 1.3-1.7% in `qab.sh` medians
  (a copy's pages are new physical pages). The 2.9% above is that floor,
  not layout: in this run 7a0a 2570 and b996 2552 to 2574 ms.
- The change (smallest that keeps results): `fillBatch` takes a `spare`
  as `fillPickIn` does and gets its batch from `lexdb_rows.reuse`
  (`fillLevel` passes it; `fillPickIn`'s whole-read path passes its own);
  `batchGroupsIn` (the grouped aggregate's scan, q1's) gives the batch
  back after each one, the pre-join batch when it joins, and not
  `bUnmatched`'s. `decodeRun`'s NULL paths (a `PK_NONE` place, a
  NULL in a value column) now write `Val.Null` to the slot (`setNull`),
  as `runCols` and `colsInto` already did for `reuse` (9.111), so a batch
  used again holds no value of its last use at a NULL row. The fill runs
  once per scan instead of once per batch.
- A/B (`qab.sh`, boost off, 5 runs per server, medians of 3 rounds; `f`
  is the change on that commit; `c2` a copy of the same file):

  | Build | q1 ms | Copy |
  |---|---|---|
  | main 8f482ee7 | 2475, 2476 | 2479 |
  | slice 3 (b99601e0) | 2552, 2573, 2574 | 2581 |
  | slice 3 part D (7a0aecfe) | 2570, 2570 | |
  | f 8f482ee7 | 2400, 2377 | 2399 |
  | f b99601e0 | 2410, 2384, 2379, 2384 | 2420, 2392 |
  | f 7a0aecfe | 2323, 2336, 2343 | 2373, 2372 |

  Without the change slice 3 is 3.9% over main, on copies too; with it
  main and slice 3 are within the copy-to-copy floor (2377-2399 against
  2379-2420), and the dead-code pair (identical code) within 1.4% on
  average, inside the same floor. q1 is 4-7% faster.
- Gates (the change against main 4ca6a0d9's code, `lexdb-b996`):
  - the suite: 188 passed, imports ok;
  - TPC-H (`tpch_ab.sh`, 3 rounds alternating): all 22 checksums the
    baseline's; total 0.950; q1 0.928, q4 0.856, q6 0.912, q9 0.960,
    q13 0.983, q15 0.898, q21 0.903; the rest within 1% but q19 1.018
    (111 to 113 ms) and q2 1.011;
  - the 35 queries (`ab35.sh`, boost off): total 0.985, again on fresh
    copies 0.978; scan2-9 0.93-0.96, grp_text 0.89-0.92, minmax_text
    0.84-0.86; distinct2 1.027-1.028 and pk_point20k 1.024-1.032 on
    both. Neither reads through the changed path: distinct2 runs the same
    instructions on both binaries (32.13G per 10 runs) and 1.6% more
    cycles, a layout shift;
  - OLTP (`oltp.sh`, boost off), tps ratios: point selects 1.008, 0.995,
    0.993 and updates 0.999, 1.001, 0.997 at 1, 8, 32 clients; the
    `INSERT ... generate_series` loads acct 1.51 s on both (medians), t
    2.96 against 2.93 s.
- Left as it is: every `Val` passed by value still goes through the
  stack as above (`dup`'s 16-byte reads of 8-byte stores), so other
  per-row paths keep a smaller sensitivity to frame offsets and code
  placement (`bKeyVal`'s key copy per row and key in q1's two-key GROUP
  BY, `colsInto`'s per-slot writes). The cure for that is in the native
  backend (copy an aggregate with the same move widths on both sides),
  not in lexdb. A query's A/B under about 1.5% needs copies of each
  binary to tell from the floor.

**Where 2d slice 3 left off, and how to start slice 4.** Slice 4 makes
`eval` read a column by its slot, so that `colIndex` (a linear search by
name, per row) goes from the executor. Everything named is in
`lexdb_exec` unless the note says otherwise; search for the names, since
line numbers move.

- What is there after slice 3:
  - Name resolution is `lexdb_bind`'s: `resolve(x, cols, n, ns: mut
    &Names)`, `resolveName`, `outerRef`, `itemCols`/`selectCols`,
    `resolveOrder`, `resolveGroup`, `orderOut`, `exprKind` and the typing
    helpers. exec calls them as `lexdb_bind.…` with `mut &sc.names` (20
    `lexdb_bind.resolve(` sites).
  - `Scope.names` (`lexdb_bind.Names`: `frames`, `base`, `ptypes`,
    `coll`, and the hooks `ty`, `blank`, `constCast`, `colScale`,
    `outScale`, set in `newScope`). The planner's hints are `Scope`'s
    other fields. `endScope` and `checkGrouped` are still exec's.
  - `Expr.Col(name, slot)`: `resolve` and its kin give the slot of the
    column list they were given; -1 elsewhere (the parser, DML targets,
    stored CHECK and index expressions, an output alias in ORDER BY or
    GROUP BY). `lexdb_bind.colSlot(cols, name, slot)` takes the slot when
    `cols[slot].name == name`, else the first of the name.
  - `Query.bcols` is still written by `addCol` and read by nothing.
- What reads names at run time:
  - `eval`'s `Expr.Col(name, _)` arm: `colIndex(&env.cols, &name)` per
    row, 42703 when absent, NULL for an empty row. 70 `colIndex(` sites
    in exec in all (plan time and run time; count again).
  - `Env.cols` comes from (count of `Env{cols: …` sites): `&q.cols` 39,
    `&noCols` 16, `&pl.inCols` 5 (MATCH_RECOGNIZE), `&t.cols` 4 (a
    table's: CHECK, index expressions, defaults), `&sel.q.cols` 2,
    `env.cols` 2, `&up.cols`, `&sp.sel.q.cols`, `&mi.pl.inCols`, `cols`.
    Only the `&q.cols` ones are the list resolve gave slots over, and only
    when the expression was resolved over the same query's whole row
    (`n` = `len(q.cols)`; `buildQuery`'s ON and USING resolve over a
    prefix, the slots are still the full row's).
- A way in:
  1. Count first: a scratch build whose `eval` column arm compares
     `colIndex`'s answer with the slot (when `slot >= 0`) and logs or
     panics on a difference; run the suite and TPC-H from that copy (a
    scratch tree with `cmd`, `tests`, `lib`, `tools`). Slice 2's check
    of `colSlot` found 40 tests whose expressions are evaluated over
    another list than they were resolved over, all with the name absent
    there; `eval` may differ (the `#agg` slots, `#old`, the semi-joins'
    renamed columns, the window and aggregate rewrites that rebuild
    `Expr.Col` with -1).
  2. Then `eval` takes the slot when `slot >= 0 && slot < len(env.cols)
    && env.cols[slot].name == name` (`colSlot`'s rule, inline), else
    searches. That keeps every result and saves the search where it
    hits; measure it (the row path's eval is hot on non-batched plans:
    q20's subqueries, the 35 queries' non-batched ones, DML).
  3. Only after every `Env` carries its query's slot order, and every
    expression that reaches `eval` carries a slot of that order, can the
    name check and `colIndex` go. Expressions built after resolve
    (`renameCol`, the aggregate and window slot rewrites, `bpFix` over
    a table's columns, the planner's key expressions, `exprText`-keyed
    copies) must be given slots first, or rebound.
- Traps:
  - `Expr.Col`'s name is still load-bearing: the planner matches by name
    (`keyedCol`, `levelOf`, `colAt`, `rangePath`, `bpFix`, `exprText`,
    `sameExpr`, `colNames`, `checkGrouped`'s `exprText` match). Keep both
    fields.
  - The slot is relative to the list resolve was given; `Frame.cols` is
    the query's `q.cols` only when `buildQuery` fills it (queries with
    subqueries). DML's targets, index and CHECK expressions are typed and
    evaluated over other lists.
  - `orderOut`, `outText` and `checkGrouped` use "not an input column"
    (`colIndex < 0`) to mean an output alias; keep that rule (the known
    ORDER BY alias difference from PostgreSQL rests on it; fix it only as
    its own commit with a test).
  - `bindExpr`'s column arm is one compare (`colSlot`); `bxOf` binds per
    run: keep it so. `BX` and `FnRef` are owned, not copy types.
  - `lexdb_bind` has a private copy of `colIndex` for its own plan-time
    uses (`colExpr`, `bpLen`, `timeLitOid`, `orderOut`); it is not
    eval's.
  - Correlation: outer references are parameters past `Names.base`
    (`outerRef`, `Frame.refs`, `endScope`, `Query.base`); `SubPlan`,
    `subFixed`, `isSubCall`, `subValue`, `keyConj` and `noRefKeys` depend
    on the numbering. Slice 4 should not need to touch it.
  - The suite compiles each test as it runs; do not edit the sources it
    reads. Running it from a snapshot copy (`cp -r lexell/{cmd,tests,lib,
    tools}` to a scratch tree, run `python3 lexell/tests/lexdb.py` there)
    lets editing go on meanwhile; commit from the snapshot's files.
  - When waiting for a process, wait on its PID, not `pgrep -f` of a
    pattern in your own command line.
- Gates, as for slice 3:
  - the suite (188), imports ok;
  - the naming battery (`~/tpch-w/bind/bench/naming/run.sh BIN OUT`,
    844 lines of output on main 8f482ee7 and this slice): identical
    output from main and the branch;
  - TPC-H all 22, checksums against `~/tpch/out-baseline-1744ef99`
    (fields [0] and [8]), watching q20 (8,508 subquery runs: eval per
    row), q2, q17, q21, q22, q18's HAVING;
  - the 35 queries; OLTP point selects and updates.
  - The plan cache: a scratch build that prints a line where
    `select`'s loop over `pc.sels` hits (`looksHold`) and where it plans
    (`pc.plans += 1`), run under `pgbench -M prepared` (slice 3 did it:
    4 clients, 3 s, 8 plans on both binaries and every other select a
    hit; updates are planned per run, there is no DML cache).
- Methods: `tpch_ab.sh TAG LABEL…` (binaries
  `~/tpch-w/bind/lexdb-LABEL`), `tpcmp.py`, `ab35.sh`/`cmp35.py`,
  `oltp.sh`, `qab.sh`, all in `~/tpch-w/bind/bench`. The baseline is
  built from `git archive <main> lexell/cmd` into
  `~/tpch-w/bind/src-main` and compiled there. `run.sh` turns boost off
  and back on itself; `ab35.sh` and `oltp.sh` do not (slice 3 ran them
  with `sudo /usr/local/sbin/cpu-boost off`, then on).

**2d slice 4 as built: `eval` reads a column at its slot.** Three commits
on `redesign/bind` from main 21f9386c, each built and through the suite
(188, imports ok), and a fourth with this note: caaae74c (stage 1),
7a0633ac (stage 2), 42d40c6a (stage 3).

- First, counted. A scratch build whose `eval` column arm logged every
  read where the slot was not the column the name search finds (kinds:
  NONE, slot -1; MISS, the slot names another column or is past the
  list; DUP, the slot names a later column of the same name), deduplicated
  per process, with the suite's test name passed in (`SLOT_TEST`, set by a
  scratch `run.py`). Run over the suite, TPC-H's 22, the 35 queries, OLTP
  (vspg: loads, point selects, updates) and the naming battery:
  - no MISS and no DUP anywhere: every `Expr.Col` that carries a slot is
    evaluated over the list it was resolved over, at that slot;
  - NONE only in the suite (80 distinct sites, 0 in the rest): a table's
    stored expressions (CHECK constraints, index expressions and
    predicates, parsed from the catalog with slot -1) evaluated over
    `t.cols` (`passes`, `idxVal`, `inIndex`, `dupMade`, `bpEval`).
  - So slice 3's "every `Env` must carry its query's slot order" holds
    wherever these runs reach: the `&q.cols` Envs read rows of `q.cols`'s
    order, and nothing read through the other lists (`&t.cols` aside:
    `&noCols`, `&pl.inCols`, `&up.cols`, `&sel.q.cols`) missed. Which of
    the 75 `Env{` sites the runs reach was not counted.
- Stage 1, `eval`: its `Expr.Col(name, slot)` arm takes `slot` when `slot
  >= 0 && slot < len(env.cols) && env.cols[slot].name == name`
  (`colSlot`'s rule, inline), else `colIndex` as before (42703 when
  absent, NULL for an empty row, unchanged). `orderValue`'s "not an input
  column" test (an ORDER BY output alias, per row) uses `colSlot`.
- Stage 2, a table's stored expressions carry slots:
  `lexdb_sql.slotted(x, cols)` gives each column its place in `cols` (the
  first of its name; -1 none). `lexdb_catalog.decTable` calls
  `slotExprs(t)` at its end (CHECKs, index expressions, index predicates
  over `t.cols`), and CREATE INDEX and ADD CHECK slot the ones they make
  (they evaluate them over the table's rows at once). A slot made stale by
  ALTER TABLE in the same statement (a dropped or renamed column) fails
  the name check and is searched; the next decode slots it again.
- Stage 3, plan-time lookups that have an `Expr.Col` in hand use
  `lexdb_bind.colSlot` instead of `colIndex`: `checkGrouped`, `firstCol`,
  `orderLookups`, `planSelect` (ORDER BY's collation kind, the
  output-alias check, GROUP BY's redundant keys), `compared` (three),
  `isKeyEq` (two), `outText`, `oldRefs`, `colAtOf`, `mrSlots`. Same answer
  as the search, since a query row's names are unique (`DUPSEP` for a
  repeat in one FROM item, 42712 for a repeated alias, `\x00sjN` for the
  semi-joins' columns) and resolve's slot is the first of its name.
- Decision: the name check stays in `eval`. Without it (`slot <
  len(env.cols)` alone, a scratch build) the row-path queries below moved
  0.1-1.5% more in one round, inside the copy floor; with it, a slot that
  is stale or from another list (none seen, but ALTER TABLE, DML target
  lists and the expressions built after resolve are many paths) still
  gives the right column instead of a wrong value. It can go when every
  expression reaching `eval` is bound against its operator's own column
  list (2e and step 3: see the note below).
- `colIndex(` sites in exec: 70 before (with the definition), 54 after:
  - 1 the definition, 1 `eval`'s fallback;
  - 38 a table's columns by a name the user wrote (`t.cols` 32, `tb.cols`
    4, `p.cols`, `q.levels[0].t.cols`): DDL, DML target lists, COPY,
    foreign keys, ON CONFLICT targets. Binding of names that never were
    `Expr.Col`s; they belong to the binder (2e's DML), not to `eval`;
  - 10 `q.cols` by a name string, no `Expr` in hand: `slotOf` (behind the
    `colAt` map), `likeBounds`, `colKind`, `plainEqCols`,
    `distinctKnown`, `buildQuery` (the frames' USING marks, the hash
    keys' `KeyedCol` names), `batchGroupsIn` (`colNames` of ORDER BY).
    The planner's name matching (kept, as the brief says);
  - 3 `rw.inCols` (MATCH_RECOGNIZE's PARTITION BY names and ORDER BY's
    unresolved items), 1 `sq.cols` (`semiLevel`, by output name).
- Not changed: `Expr.Col` keeps its name (the planner's keys, `levelOf`,
  `colAt`, `rangePath`, `bpFix`, `exprText`, `sameExpr`); `Query.bcols`
  is still read by nothing; `lexdb_bind` is untouched.
- Lines:

  | Module | main 21f9386c | after |
  |---|---|---|
  | `lexdb_exec` | 27826 | 27828 |
  | `lexdb_bind` | 1856 | 1856 |
  | `lexdb_sql` | 1188 | 1210 |
  | `lexdb_catalog` | 1336 | 1358 |

- No change in results:
  - the suite (188) at every stage; imports ok;
  - the naming battery: identical output from main and stages 1, 2 and 3.
    Extended by 51 statements (now 1000 lines, 28 errors; the old file is
    `naming.sql.s3`): CHECKs over several columns and a char(n) one,
    passing and failing on INSERT and UPDATE; ADD CHECK validating
    existing rows (failing and passing); DROP COLUMN before a checked
    column, RENAME COLUMN of one, ADD COLUMN with a CHECK on it; an
    expression index used by a lookup, a unique expression index and a
    unique partial index violated by INSERT, by a multi-row INSERT and by
    UPDATE, then DROP COLUMN before them and the same again; UPDATE and
    DELETE with RETURNING expressions; ON CONFLICT DO UPDATE with
    `excluded` (twice); MERGE with expressions in both arms; UPDATE ...
    FROM, DELETE ... USING with RETURNING; INSERT ... SELECT RETURNING;
    GROUP BY with an ORDER BY over an aggregate alias and an expression;
  - TPC-H's 22 checksums (fields [0] and [8]) on every round.
- A/B against main 21f9386c (built from `git archive` into
  `~/tpch-w/bind/src-m21f`, binary `lexdb-m21f`; the branch at stage 3,
  `lexdb-s4c`), boost off, binaries alternating, medians of 3 rounds:
  - TPC-H (`tpch_ab.sh`, tags g1-g3): total 0.998; all 22 checksums the
    baseline's on every round. q2 0.983, q17 0.980, q20 1.010, q21 0.998,
    q22 1.002, q18 1.005; q10 0.967, q14 0.978, q16 0.968 (the same in all
    three rounds); q1 1.016; the rest within 1%.
  - The watched ones and the row path on copies (`qmulti.sh q4b 5 3`,
    `m21f`, `s4c` and byte-identical copies `m21fc`, `s4cc`; ratio of the
    pairs' means; the floor is copy against copy):

    | Query | main | main copy | slice 4 | slice 4 copy | ratio | floor main, s4 |
    |---|---|---|---|---|---|---|
    | `case` (CASE over lineitem, row path) | 6393 | 6533 | 6188 | 6166 | 0.956 | 1.022, 0.997 |
    | `cat` (max of `l_comment \|\| l_shipinstruct`) | 9403 | 9561 | 9109 | 8953 | 0.952 | 1.017, 0.983 |
    | `md5` (`md5(l_comment) < '1'`) | 4572 | 4612 | 4497 | 4451 | 0.974 | 1.009, 0.990 |
    | q1 | 2449 | 2462 | 2495 | 2457 | 1.008 | 1.005, 0.985 |
    | q2 | 64.4 | 64.2 | 63.6 | 63.8 | 0.991 | |
    | q17 | 43.7 | 43.4 | 43.6 | 43.2 | 0.996 | |
    | q20 | 384.6 | 380.6 | 384.5 | 381.9 | 1.002 | 0.990, 0.993 |
    | q22 | 457.5 | 459.4 | 459.9 | 454.9 | 0.998 | |

    The row path gains 2.6-4.8%, over the floor. q1 and q20 are level,
    inside the floor (`run.sh`'s q1 1.016 and q20 1.010 are that floor).
  - User-space instructions (`pstat.sh`, `perf stat -p` on the server over
    3 runs after a warm-up, one server each): `case`
    189.86G against 185.53G (-2.3%; cycles -3.3%), q1 101.96G against
    101.69G, q20 8.755G against 8.751G, q2 1.832G against 1.825G. So
    q20's 8,508 subquery runs do not read columns through `eval`'s column
    arm in an amount that shows (not looked into further: the bound `BX`
    paths read by slot already); slice 3's note took q20 for an `eval`
    path, and it is not where this slice's gain is.
  - The 35 queries (`ab35.sh`, 3 rounds): total 0.999; every query within
    1.5% (scan2 1.012, grp_text 1.010, join_left_rows 0.982, join_hash_agg
    0.983, expr_agg 0.985). None of them reads columns through `eval` per
    row in an amount that shows (their row paths are bound or batched).
  - OLTP (`oltp.sh`, 3 rounds), tps ratios:

    | Clients | Point selects | Updates |
    |---|---|---|
    | 1 | 1.006 | 0.997 |
    | 8 | 1.013 | 1.004 |
    | 32 | 1.015 | 1.008 |

    The batch-insert loads (`INSERT ... generate_series`, 1M rows):
    acct 1.52 against 1.50 s, t 2.94 against 2.92 s (medians).
  - The plan cache, counted (`~/tpch-w/bind/bench/pc.sh BIN LOG` on
    scratch builds of main and the branch that print `PC PLAN` at `pc.plans
    += 1` and `PC HIT` in `select`'s loop over `pc.sels`; `pgbench -M
    prepared`, 4 clients, 3 s of point selects, then 3 s of updates): 8
    plans on both, every other select a hit (194,490 of 194,498 on main,
    196,183 of 196,191 on the branch); the updates add no plan and no hit
    (planned per run, no DML cache), on both.
- Not verified: T-SQL's and Oracle's paths beyond the suite's `tds_*` and
  `tns_*` tests (the counting build saw no slot misses there either); the
  unguarded `eval` (no name check) beyond one round of the row-path probes.

**Where 2d left off, and how to start 2e (the logical plan).** 2d is done
as far as the old executor allows: names are resolved by `lexdb_bind`,
each resolved `Expr.Col` carries its slot, `bindExpr` and `eval` read the
slot (with the name check), and a table's stored expressions are slotted
when the table is decoded. 2e makes the binder emit the logical plan (the
table of operators in "The bound plan" above: `Get`, `Values`, `Func`,
`CteRef`/`Recursive`, `Filter`, `Project`, `Join`, `Apply`, `Agg`,
`Window`, `Sort`, `Limit`, `Distinct`, `SetOp`, `Match`, `Lock`) for SELECT
and for DML's sources, and `planSelect`/`buildQuery` read it instead of the
`Stmt`. Step 3 (section 6) then turns it into the operator tree, and 4.5's
optimizer takes it over; 2e itself changes no plan and no result.
Everything named is in `lexdb_exec` unless the note says otherwise; search
for the names, since line numbers move.

- What is there after 2d:
  - `lexdb_bind`: `Names` (`frames`, `base`, `ptypes`, `coll`, the hooks
    `ty`, `blank`, `constCast`, `colScale`, `outScale`), `Frame`,
    `resolve(x, cols, n, ns: mut &Names)`, `resolveName`, `outerRef`,
    `selectCols`/`itemCols`, `resolveOrder`, `resolveGroup`, `orderOut`,
    `OutCol`, the typing helpers, `colSlot(cols, name, slot)`, `Ty`,
    `BCol`, `bcolOf`, `BX`, `bindExpr`, `reslot`.
  - exec's `Scope` holds `names: Names` and the planner's hints (`works`,
    `asRole`, `whos`, `target`, `looks`, `early`, `locking`, `ordBy`,
    `ordLim`, `noRefKeys`); `newScope`/`newScopeIn` make it, `endScope`
    closes a frame into its `Query` (`Query.refs`, the subqueries' `kind`
    and `readAs`).
  - `Query` (`levels`, `cols`, `bcols`, `top`, `subs`, `base`, `refs`,
    `colAt`, `cc`/`cp`) and `Sel` (`q`, `exprs`, `outs`, `groupBy`,
    `order`, `having`, `specs`, `wins`, `parts`, `setop`, `gsets`, `mr`,
    `locks`, `ox`, …) are both the bound form and the physical plan today.
    `Query.bcols` is written by `addCol` (every column of a query's row
    goes through it) and read by nothing: it is the natural output
    column list of the `Get`/`Join` part.
  - `buildQuery(st, txn, from, where, params, subs, selNames, star, sc,
    reorder)` (about 1,150 lines) does both jobs in one pass: it walks the
    FROM items (tables, views under their owner, FROM subqueries planned
    first, LATERAL, SRFs, `#values:`), adds their columns (`addCol`),
    builds USING/NATURAL's ON (`usingSide`, `colExpr`), resolves ON and
    WHERE, plans the subqueries (`planSub`, numbered by the frame's
    `sub*` lists), finds semi-joins (`semiLook`, `semiJoins`, hidden
    `\x00sjN` columns), adds implied equalities, then orders the joins
    and chooses paths (`choosePath`, `costOrder`). Its callers: 13 sites
    (`planSelect`, `planSub` through `planSelect`, `insert`, `update`,
    `delete`, `merge`, the batched DML at `dmlFrom`/`mergeFrom`, EXPLAIN's
    and ALTER's uses).
  - `planSelect(st, txn, s: &Stmt, params, sc)` reads the `Stmt`'s
    clauses directly (`s.order`, `s.group`/`s.gsets`, `s.having`,
    `s.distinct`/`s.distinctOn`, `s.wins`/`s.windows`, `s.limit`/`s.offset`,
    `s.withTies`, `s.topMode`, `s.lockMode`, `s.setop` → `planSet`,
    `s.srf`/`s.ordin`, `s.mr` → `planMatch`, `s.items`). The 20
    `lexdb_bind.resolve(` sites are spread over `buildQuery`,
    `planSelect`, `planSet`, `planMatch` and the DML planners.
  - DML: `insert`, `update`, `delete`, `merge` (and `upsertOld`, `Ret` for
    RETURNING, `MClause`) resolve their SET/VALUES/RETURNING over the
    query's `cols`; target column names are found by `colIndex(&t.cols,
    …)` (32 sites): binding work 2e's DML part should take.
- A way in, in slices that each keep results and speed:
  1. Types only: `lexdb_bind.LPlan` (a closed type, one arm per operator,
     each with its output `[]BCol`), built beside today's structures where
     they are built (`buildQuery`'s FROM walk for `Get`/`Join`/`Func`/
     `Values` and FROM subqueries; `planSelect` for `Filter`, `Agg`,
     `Window`, `Sort`, `Limit`, `Distinct`, `Project`; `planSet` for
     `SetOp`), read by nothing, and checked against `Query.cols`/`bcols`
     and `Sel.outs` in a scratch build over the suite and the battery.
     As 2d slice 1 did with `bcols`.
  2. Split `buildQuery` into the binder's FROM pass (FROM items, columns,
     USING/NATURAL, ON and WHERE resolved, subqueries numbered: an
     `LPlan`) and the planner's pass (semi-joins, implied equalities, join
     order, paths), which reads the `LPlan`. Move the FROM pass into
     `lexdb_bind`; it needs the catalog (tables, views) through the hooks
     on `Names` or a catalog snapshot passed in (`lexdb_bind` may import
     only `lexdb_base`, `lexdb_sql`, `lexdb_catalog`, `lexdb_dialect`,
     `lexdb_time`, `lexdb_float`, `lexdb_ops`, `lexdb_lib`:
     `tests/lexdb/imports.py`, `BIND_MAY_IMPORT`).
  3. `planSelect` reads its clauses from the `LPlan` instead of the
     `Stmt`, one clause per commit (ORDER BY, GROUP BY and HAVING,
     windows, DISTINCT, LIMIT, locking), then `planSet`, `planMatch`,
     then DML's sources and target lists.
  4. With every operator's input list known to the binder, bind each
     expression against its operator's own input (`BX.Col(slot)`), and
     drop `eval`'s name check (see "2d slice 4 as built": it costs 0-1.5%
     on the row path and guards against a slot from another list).
- Traps:
  - `Expr.Col`'s name is load-bearing for the planner (`keyedCol`,
    `levelOf`, `colAt`, `slotOf`, `rangePath`, `bpFix`, `exprText`,
    `sameExpr`, `colNames`, `checkGrouped`'s `exprText` match, the hash
    keys' `KeyedCol`). Keep it until those read slots.
  - The slot is relative to the list resolve was given. `Frame.cols` is
    `q.cols` only where `buildQuery` fills it (queries with subqueries);
    ON and USING are resolved over a prefix of the row, their slots are
    the full row's. Semi-joins add hidden columns (`semiLookAdd`,
    `semiJoins`) and rename columns (`renameCol` with the new slot): the
    planner's rewrites change the row after binding, so the `LPlan`'s
    column list and `Query.cols` differ from then on.
  - Correlation: outer references are parameters past `Names.base`
    (`outerRef`, `Frame.refs`, `endScope`, `Query.base`, `Query.refs`);
    `SubPlan`, `subFixed`, `isSubCall`, `subValue`, `keyConj`,
    `noRefKeys` (9.104) and the per-row subquery machinery depend on the
    numbering. `Apply` should carry today's numbering until step 5.
  - Views are planned under their owner (`asRole`, `whos`); CTEs are
    re-parsed per use today (the design's `CteRef` binds once); a
    recursive CTE's working table is `Scope.works`.
  - The plan cache (`PlanCache`: `sels`, `looks`, `ver`, `plans`; the hit
    is `select`'s loop over `pc.sels` with `looksHold`) keeps `Sel`s per
    prepared statement; whatever 2e adds to a `Sel` is cached with it and
    must not hold run-time state. Updates are planned per run (no DML
    cache).
  - `orderOut`, `outText`, `orderValue` and `checkGrouped` read "not an
    input column" (`colSlot`/`colIndex` < 0) as an output alias. The known
    difference from PostgreSQL (an input column before an output alias of
    the same name in ORDER BY: 42803 where PostgreSQL takes the alias) rests
    on it; fix it only as its own commit with a test.
  - `bindExpr` runs per run on the `bxOf` paths (join, group and ORDER BY
    keys, aggregate arguments); keep its column arm one compare. `BX` and
    `FnRef` are owned, not copy types; copy a `FnRef` by its fields.
  - A table's stored expressions are slotted in `decTable`
    (`lexdb_catalog.slotExprs`); a Table changed in memory by ALTER keeps
    stale slots until it is decoded again, which the name check absorbs.
    If the check goes (way in, 4), call `slotExprs` after every in-memory
    change of `t.cols` first (`alterTable`'s arms, `dropColumn`, RENAME COLUMN).
  - The suite compiles each test as it runs: do not edit the sources it
    reads (about 4 minutes at `-j 2`). Run it from a snapshot copy
    (`cp -r lexell/{cmd,tests,lib,tools}` to a scratch tree) so editing can
    go on; commit what the snapshot passed.
  - When waiting for a process, wait on its PID or a file, not `pgrep -f`
    of a pattern in your own command line (it matches itself).
  - Run timings under `flock ~/tpch/.bench.lock` (exclusive); builds and
    the suite take it shared, so they wait while a timing run holds it.
- Gates:
  - the suite (188), imports ok;
  - the naming battery (`~/tpch-w/bind/bench/naming/run.sh BIN OUT`,
    1000 lines on main 21f9386c and on slice 4): identical output from
    main and the branch; extend it for whatever moves (2e: FROM shapes,
    views, CTEs, recursive CTEs, LATERAL, set operations, DML sources);
  - TPC-H all 22, checksums against `~/tpch/out-baseline-1744ef99`
    (fields [0] and [8]), watching q2, q17, q18, q20, q21, q22;
  - the 35 queries; OLTP point selects and updates, and the batch-insert
    loads (`oltp.sh`'s `load` lines);
  - the plan cache, counted: a scratch build that prints a line where
    `select`'s loop over `pc.sels` hits and where it plans (`pc.plans +=
    1`), under `pgbench -M prepared`, 4 clients, 3 s of point selects then
    3 s of updates (`pc.sh` below). On main 21f9386c and slice 4: 8 plans,
    every other select a hit; updates add none (planned per run).
- Methods (`~/tpch-w/bind/bench`):
  - baseline: `git archive <main> lexell/cmd` into a scratch tree, built
    there with the native compiler (`LXL_NOCACHE=1`, `taskset -c
    4-7,12-15`, shared lock);
  - `tpch_ab.sh TAG LABEL…` (binaries `~/tpch-w/bind/lexdb-LABEL`, 3 runs,
    `run.sh` turns boost off and restores it), `tpcmp.py A B TAG…`;
  - `ab35.sh OUT A BINA B BINB [ROUNDS]`, `cmp35.py`; `oltp.sh OUT A BINA B
    BINB [ROUNDS]`; neither sets boost: `sudo /usr/local/sbin/cpu-boost
    off` first and `on` after;
  - `qab.sh QFILE N LABEL…` (one query) and `qmulti.sh QDIR N ROUNDS
    LABEL…` (every `QDIR/*.sql`, N timed runs after a warm-up, per server
    start; added in slice 4). The row-path probes `~/tpch-w/bind/q4b`
    (`case`, `cat`, `md5` over lineitem: eval per row, 4-9 s) with
    q1, q2, q17, q20, q22. Under ~1.5% use byte-identical copies of each
    binary (`cp lexdb-X lexdb-Xc`) as their own labels: a copy's pages
    differ, and copies of one binary differ by that much (the q1 note).

**2e slice 1 as built: `lexdb_bind.LPlan`, built beside the executor's
structures.** Three commits on `redesign/bind` from main 76118b8a, each
built and through the suite (188, imports ok): 5f7ab0ae (the type and its
building), ff290e9d (a fix the scratch check found), 32afed0d (`Query.bcols`
goes into the plan, fewer copies), and a fourth with this note. Nothing
reads the plan yet; no plan and no result changes.

- The type (`lexdb_bind`, after `bcolOf`): a closed `LPlan`, one arm per
  operator, each with its output `[]BCol` last:
  - leaves: `One` (no FROM), `Get(table, alias)`, `Values(width, values
    row by row)`, `Func(name, ordinality, args)`, `CteRef(id, work)`;
  - `Sub(view, src, plan)`: a FROM item that is a query (a subquery, a
    view, a CTE's use, a function, VALUES, a working table) with its
    plan's outputs renamed into the joined row (alias.column at the row's
    slots). `src` is the item's number in `Query.subs` (`Level.src`), so a
    later slice can find the planned `SubPlan`;
  - `Join(kind, lateral, left, right, on)`: left-deep in FROM's order, as
    the executor's levels are; `on` is the resolved ON and the ON that
    USING/NATURAL makes (`[]Expr`, [] none); its columns the left's then
    the right's (all of them: USING's merged columns are marked on
    `ColDef.using`, which `BCol` does not carry);
  - `Filter(pred)` (WHERE after `pullCommonOr`, and HAVING), `Agg(keys,
    sets, nAggs)`, `Window(defs)`, `Project(exprs)`, `Distinct(on)`,
    `Sort(keys, desc, nullsFirst)`, `Limit(count, offset, ties, topMode)`,
    `SetOp(op, all, l, r)`, `Recursive(id, anchor, step)`, `Match`.
  - Helpers: `noPlan()`, `lpCols(p)` (a copy), `copyBCols`, `outBCol(slot,
    o, mod)`; exec's `outBCols(outs)` gives the mod from `outType` when a
    dialect's wire hint is in `OutCol.scale` (below), else -1.
  - `Query.bcols` is gone: 2d slice 1 made it as the natural column list
    of the Get/Join part, read by nothing. The `Get`/`Sub` columns are
    built where `addCol` adds the row's (`icols`, `bcolOf`), a `Join`'s are
    its left's then its right's. (The semi-joins' hidden columns, added
    later by `addCol`, have no `BCol`: the plan keeps the bound row.)
- Where it is built (all `lexdb_exec`):
  - `buildQuery`'s FROM walk appends a `Get` or `Sub` per item to `items`
    (`icols`: the item's columns, `bcolOf` of each `ColDef` it adds);
    a FROM subquery's or view's plan is moved out of its `SubPlan`
    (`sp.sel.lp`), a CTE's use is `CteRef(cte, false)` and its body's plan
    stays in its `SubPlan` (it is re-planned per use today), a working
    table is `CteRef(id, true)`. The ON loop moves each resolved ON into
    the `Join` (after `conjuncts` has copied it); the resolved WHERE is
    moved into a `Filter`. `q.lp` is set before the planner's part
    (implied equalities, join order, paths, semi-joins).
  - `planSelect` keeps clones of the clauses as resolved (`lpExprs`,
    `lpGroup` before the redundant keys are dropped, `lpOrder` after
    DISTINCT ON's items are added, `lpHaving`, `lpWins`, `lpOn` moved)
    and `selPlan` wraps `q.lp`: Agg, Filter (HAVING), Window, Project,
    Distinct, then `topPlan`'s Sort and Limit. The expressions are the
    binder's (resolve, resolveOrder, resolveGroup, enum positions), not
    the planner's (`collectAggs`'s `#agg` slots, `setSubst`, `winSlots`):
    the `Agg` carries the aggregates' number only.
  - `planSet` moves both sides' plans into `SetOp` or `Recursive` (over
    the common-typed `outs`) under `topPlan`.
  - `planSub` replaces a function's or VALUES' plan by `Func`/`Values`
    (with `srfCols`' columns; `planSelect` skips the select list's clone
    for them) and wraps a MATCH_RECOGNIZE in `Match` (`mr[0].outs`).
  - Not built: `Apply` (expression subqueries keep their numbering in
    `Query.subs`, their own `Sel.lp` stays in their `SubPlan`), `Lock`
    (FOR UPDATE is still `Level.lock`), DML (`insert`, `update`, `delete`,
    `merge` keep the FROM/WHERE part in `q.lp` and add nothing).
- Cost: expressions are moved where the executor no longer needs them (ON,
  WHERE, DISTINCT ON) and cloned where it rewrites them (select list,
  GROUP BY, ORDER BY, HAVING, windows, a function's arguments); column
  lists are copied per operator. All per plan: a prepared SELECT is planned
  once (the plan cache keeps the `Sel` with its `lp`); UPDATE and DELETE
  build `Get` and `Filter` per run (no expression cloned).
- The scratch check (`~/tpch-w/bind/e2/chk/patch.py` applied to a copy of
  `lexell/cmd`; the suite from a snapshot whose `run.py` appends each
  test's `LPCHK` stderr lines to `$LPCHK_OUT`): `lpCols(q.lp)` against
  `q.bcols` (all fields; after 32afed0d against `bcolOf` of each of
  `q.cols`) and `q.cols` (slot, name, spell) when `q.lp` is set and again
  at `buildQuery`'s end; each `Sub`'s plan's columns
  against the row's (types, and names where no AS list renames them);
  each operator's columns against its input's (`lpValid`: Join = left ++
  right; Filter, Agg, Window, Distinct, Sort, Limit = input; Project's
  expressions one per column; Sort's keys, desc, nullsFirst alike; SetOp's
  sides as wide); the top's columns against `fromCols(sel)` (name, spell,
  OID, collation) at `select`'s plan, `selectWith` and `planSub`. Over the
  suite, TPC-H's 22, the 35 queries and the naming battery:
  - fixed: a FROM subquery's or view's row column carried the dialects'
    wire hint as its typmod (`outType`: datetime(3) 1114/3, a T-SQL
    varchar's length 1043/10 and /20), the Project's column had -1
    (`OutCol` has no typmod). 929 sites in the suite (T-SQL tests).
    `outBCol` takes a mod and exec's `outBCols` gives `outType`'s
    (ff290e9d);
  - left, by design: the joined row grows after binding: semi-joins'
    hidden `\x00sjN.\x00rowidK` columns (`semiLookAdd`, `semiJoins`), 3,152
    sites in the suite, 6 in TPC-H, 8 in the 35 queries, 9 in the battery
    (`q.bcols` grew with `q.cols` through `addCol`); the `LPlan` keeps the
    bound row. No column was renamed or retyped in
    `q.cols` after binding (no `col` mismatch at the end);
  - left, by design: a view with a column list (`create view v (a, b)`,
    q15's `revenue0 (supplier_no, total_revenue)`) renames its plan's
    outputs in `Sub` (the check's name test flagged it);
  - left, a known difference: a FROM subquery's or view's column of type
    oid (26), "char" (18), name (19), regproc (24), regclass (2205) or
    regtype (2206) is text (25) in the outer row: `outType` goes through
    `lexdb_sql.oidType`, which maps every OID it does not model to text.
    The `Sub`'s plan has the true type; its row columns (from `q.bcols`)
    have text. All in the catalog views (`pg_class`, `pg_attribute`,
    `pg_index`, `pg_namespace`: 15,000 of the suite's 15,800 lines). So a
    query over `pg_class` types `c.oid` as text and sends its client text,
    where PostgreSQL sends oid. Changing `oidType` changes typing and
    results (comparisons of those columns with integers); a commit of its
    own with tests;
  - nothing else: no length, slot or name mismatch, no operator whose
    columns differ from its input's, no top whose columns differ from the
    `Sel`'s outputs (sets with common types, SRFs, VALUES, MATCH_RECOGNIZE,
    views, CTEs, recursive CTEs, LATERAL included).
- The naming battery (`~/tpch-w/bind/bench/naming`): extended by 60
  statements for 2e (now 1,505 output lines, 30 errors; the old file is
  `naming.sql.s4`): VALUES in FROM with and without column lists (and too
  many), functions in FROM with ORDINALITY, unnest of two arrays, LATERAL
  functions and LATERAL subqueries under LEFT JOIN, a CTE used twice and
  CTEs over CTEs, nested FROM subqueries with column lists, views with
  column lists and views over views, UNION/UNION ALL/INTERSECT ALL/EXCEPT
  with ORDER BY, LIMIT and OFFSET, unions of an int and a numeric and of a
  text and a NULL, a column-count mismatch, a recursive CTE, DISTINCT,
  DISTINCT ON (one and two keys), GROUPING SETS, ROLLUP, CUBE, a named
  window, frames, windows over groups, FETCH ... WITH TIES, OFFSET, FOR
  UPDATE, an output alias in ORDER BY, INSERT ... SELECT of a UNION,
  UPDATE ... FROM a grouped subquery, DELETE with a row IN, MERGE from
  VALUES, MATCH_RECOGNIZE (also as a FROM subquery), VALUES in a
  correlated scalar subquery, `= ANY` over a function, a catalog view.
  Identical output from main 76118b8a, the branch and the check build.
- A/B against main 76118b8a (built from `git archive` into
  `~/tpch-w/bind/src-m761`, `lexdb-m761`; the branch at 32afed0d,
  `lexdb-e4`), binaries alternating, medians of 3 rounds:
  - TPC-H (`tpch_ab.sh`, tags k1-k3, boost off by `run.sh`): total 0.993;
    all 22 checksums the baseline's on every round. q1 0.969, q10 0.975,
    q11 0.978; q16 1.015, q17 1.016 (44.6 to 45.3 ms), q19 1.017 (113.4
    to 115.3 ms), q21 1.012; the rest within 1.2%. (At 5f7ab0ae, tags
    h1-h3: total 0.993, q1 0.954, q20 0.962, q18 1.012, q16 1.011.) The
    plan is built once per query here; these are the copy floor.
  - The 35 queries (`ab35.sh`, boost off): total 1.006; `pk_point20k`
    1.050 (909 to 954 ms; below), the rest within 3.2% on 3-260 ms
    queries (filt_agg 1.031, pk_range100k 1.032, distinct2 0.970), as in
    earlier slices' floors. `sort_all`, `idx_range1k`, `idx_range100k`,
    `idx_range_agg` and `join_lookup_agg` fail on both binaries ("page
    23349: type 2", the `la/base2` copy; also on slice 4's runs).
  - Planned per statement (the cost this slice adds):
    - `pk_point20k` (20,000 `select * from w where id = n` by the simple
      protocol, each parsed and planned; `~/tpch-w/bind/e2/pts.sh`, 5 runs
      per server, 3 rounds, server CPU from schedstat), CPU medians:

      | Build | ms | copy | vs main |
      |---|---|---|---|
      | main 76118b8a | 841-850 | 848-855 | |
      | 5f7ab0ae+ff290e9d (every list copied) | 927 | | +9% |
      | ... outputs' typmod only from a hint, one copy fewer | 909 | 902 | +6.5% |
      | 32afed0d (no `Query.bcols`, one copy per operator) | 883-893 | 889 | +5.3% |
      | 32afed0d without `Sel.lp`'s part (scratch `x1`) | 870 | | +3.4% |
      | ... nor `Get` columns, `Join` columns, `Filter` (`x2`) | 853 | | +1.4% |

      A scratch variant whose pass-through operators (Filter, Agg,
      Window, Distinct, Sort, Limit) carry [] instead of a copy (`x3`)
      measured 878 against the branch's 885 and main's 841: the copies
      are a small part, so the shape stays as asked (every operator with
      its list). About 2.1 us per statement of 42 us: the `Filter`'s copy of the
      `Get`'s columns, the `Project`'s columns (`outBCols`), the select
      list's clone and the plan's drop (`rt_drun`). A profile of the
      server (`perf record --call-graph fp --user-callchains -e cycles:u`,
      symbols from `LXL_NATIVE_MAP`; `~/tpch-w/bind/e2/profg.sh`,
      `incl.py`): `selPlan` 1.8% inclusive, `outBCols` 0.8%, `lpCols` 0.6%,
      `copyBCols` 0.6%, `rt_drun` +1.1% before 32afed0d.
    - `~/tpch-w/bind/e2/simple.sh` (pgbench `-M simple`, 4 clients, 10 s,
      boost off, tps medians): point selects 38,390 against 37,386
      (0.974); updates 9,030 against 9,005 (0.997); a 3-table join with
      ORDER BY and LIMIT 16,384 against 15,521 (0.947: three `Get`s, two
      `Join`s, Filter, Project, Sort, Limit, each with a list).
  - DML, planned per run: updates in OLTP (`oltp.sh`, prepared, a commit
    each), tps ratios 0.990, 1.002, 1.006 at 1, 8, 32 clients; by the
    simple protocol 0.997 (above). The batch-insert loads (`INSERT ...
    generate_series`, 1M rows, medians): acct 1.52 against 1.56 s, t 3.00
    against 2.99 s.
  - Prepared point selects (plan-cache hits; nothing of the plan is built
    or read per run): `oltp.sh` 0.988, 0.992, 0.976 at 1, 8, 32 clients;
    on byte-identical copies (`~/tpch-w/bind/e2/prep.sh`, 1M rows, 10 s,
    boost off, tps medians of 3 rounds): 1 client main 48,457 and copy
    48,766, branch 47,440 and copy 48,093 (0.983 of the pairs' means; the
    floor 1.006 and 1.014); 32 clients main 80,461 and 80,374, branch
    80,175 and 78,923 (0.989; floor 0.999 and 0.984). At or just past the
    copy floor; nothing of the plan runs per execution (the `Sel` is
    borrowed), so read it as layout, not verified further.
  - The plan cache, counted (`pc.sh`, builds patched by
    `~/tpch-w/bind/e2/chk/pcpatch.py`): 8 plans on main and the branch,
    every other select a hit (190,483 of 190,491 on main; 214,554 of
    214,562 at 32afed0d); the updates add no plan and no hit.
- Verdict against the noise between byte-identical copies (~1.5%): no
  regression on TPC-H (checksums all the baseline's), the 35 queries but
  `pk_point20k`, prepared point selects (at the floor), updates and the
  loads. A regression past the floor where a SELECT is planned per
  statement by the simple protocol: `pk_point20k` +5% CPU, pgbench point
  selects -2.6% tps, the 3-table join -5.3%. That is the cost of building
  a second representation beside the old one; it goes when the planner
  reads the `LPlan` instead of cloning the clauses (slices 2-3), and
  prepared statements do not pay it. Not run (stopped by the
  coordinator's instruction): more rounds or copies of the simple-protocol
  runs, `qmulti.sh` row-path probes, `pstat.sh` instruction counts, the
  check build over TPC-H and the 35 queries after 32afed0d (it ran at
  5f7ab0ae; the suite and the battery ran on every stage's check build).
- Lines:

  | Module | main 76118b8a | after |
  |---|---|---|
  | `lexdb_exec` | 27828 | 27936 |
  | `lexdb_bind` | 1856 | 1936 |

**Where 2e slice 1 left off, and how to start slice 2.** Slice 2 splits
`buildQuery` into the binder's FROM pass and the planner's pass, the
planner reading the `LPlan`. Everything named is in `lexdb_exec` unless
the note says otherwise; search for the names, since line numbers move.

- What is there after slice 1:
  - `lexdb_bind.LPlan` (arms in "2e slice 1 as built"), `noPlan`,
    `lpCols`, `copyBCols`, `outBCol`; exec's `outBCols`, `selPlan`,
    `topPlan`. `Query.lp` (FROM and WHERE) and `Sel.lp` (the whole SELECT;
    `planSelect` moves `q.lp` into it, so a `Sel`'s `q.lp` is `One`).
    Read by nothing; the only readers are the scratch check's.
  - In `buildQuery`: `items` (per FROM item, `Get` or `Sub`), `item`,
    `viewName`, `spLp` (a FROM subquery's plan, taken out of its
    `SubPlan` before `fromCols` borrows it), `icols` (the item's `BCol`s,
    made beside `addCol`); the ON loop's `jon`,
    `jcols` and the left-deep `lp`; the WHERE's `Filter`; `q.lp = lp`
    before `need`, the join order and the paths.
- `buildQuery`'s phases today, binder (B) or planner (P):
  1. B/P prologue: the hints `planSelect` leaves on the `Scope` (`early`,
     `locking`, `noRefKeys`, `ordBy`, `ordLim`) are taken (P); the
     semi-join candidates (`semiCand`, from WHERE's unresolved conjuncts
     by `semiParsed`) (P).
  2. The FROM walk (B), with three planner calls in it: `planSub` of a
     FROM subquery or a view binds and plans it in one call (both); a
     table's statistics (`loadEst`, P); and the frames' columns for the
     subqueries (`Frame.cols`, `exact`) (B). Privileges (`scCheck`), the
     catalog (`findTable`, `findSeq`, `viewQuery`, `readAcl` for a view's
     owner, `sc.asRole`), USING/NATURAL (`usingSide`, `colExpr`, the
     `using` marks, *'s order in `pos`) are binder work.
  3. The expression subqueries (`for i in 0..len(subs)`): `planSub` each
     (both), the semi-join alternatives planned again with `noRefKeys`
     (`semiLooks`, `semiAlts`, P), then the frame's `subRefs`, `subOids`,
     `subNames`, `subColls`, `subKinds`, `subReads` (B: resolve types a
     `#sub`/`#in` call from them) and `q.corr`.
  4. The views' plans numbered after the statement's subqueries (B: the
     numbering `Level.src` and `Sub`'s `src` use).
  5. `colAt` (P).
  6. ON and USING's ON resolved over the row's prefix, `enumOrder` (B);
     their conjuncts into `ms[k]` (P).
  7. WHERE: `pullCommonOr` on the unresolved tree (P, a rewrite, before
     resolve), resolve and `enumOrder` (B), then the placement into
     `ms`/`ps`, `orLevels` (P).
  8. `need` (from `selNames`), implied equalities, join order
     (`pinnedOrder`, `costOrder`, `joinOrder`, `outerReadOnce`), paths
     (`choosePath`), hashing, `semiJoins` (all P).
- A way in:
  1. Within `lexdb_exec` first: `bindFrom` (phases 2-4 and 6-7's resolve,
     returning the `Query` with its levels' tables, `cols`, `bcols`,
     `subs` and `q.lp`) and `planFrom` (the rest), `buildQuery` calling
     both, so its 13 callers do not change. `planFrom` takes the ON and
     WHERE conjuncts from `q.lp` (walk the left-deep `Join`s: the k-th
     join's `on` is level k's; the `Filter` over them is WHERE's;
     `conjuncts` clones). Keep `pullCommonOr` where it is (on the
     unresolved WHERE, in `bindFrom`) for this slice: resolve adds casts
     and `#bptrim` calls that its text matching may see differently, and
     q19 depends on it. Moving it into the planner is its own commit, with
     q19's plan and checksum as the gate.
  2. The semi-join alternatives (phase 3's second `planSub`) are planner
     work inside the binder's loop: `planFrom` should do them, after
     `bindFrom` has numbered and typed every subquery. They need the
     subquery's `Stmt` (`subs[i]`) and the `Scope` (`sc.noRefKeys`); the
     candidate test reads `sp.use`, `sp.sel.q.refs`, `sp.hashed`, `sp.cte`
     only.
  3. Then move `bindFrom` into `lexdb_bind`. It cannot call the catalog:
     `lexdb_bind` may import only `lexdb_base`, `lexdb_sql`,
     `lexdb_catalog`, `lexdb_dialect`, `lexdb_time`, `lexdb_float`,
     `lexdb_ops`, `lexdb_lib` (`tests/lexdb/imports.py`,
     `BIND_MAY_IMPORT`), and `Names`' hooks are plain functions (no
     captured `Store` or `Txn`: `Typing.fnOid`, `blank`, `constCast`,
     `colScale`, `outScale`). Two ways: exec fetches what the FROM names
     first (a catalog snapshot: each FROM item's `Table`, a view's parsed
     `Stmt` and owner, a sequence's relation, the `Scope`'s working
     tables) and passes it in; or the binder returns what it lacks and is
     called again. Subqueries make either recursive: a FROM subquery is
     bound and planned by one `planSub` today, and the outer FROM pass
     needs only its output columns (binder work: `selectCols`, `srfCols`,
     the `#values:` typing in `planSub`, `planMatch`'s outputs). So the
     binder half of `planSub`/`planSelect` must be separable first: that
     is slice 3's ground (planSelect reading its clauses from the
     `LPlan`), and suggests doing slice 2's step 1-2 in exec, slice 3,
     then the move.
- Traps:
  - Borrows: a field cannot be moved out of a match arm's binding ("cannot
    move a []Expr out of a borrow"); read an `LPlan` by matching a `&LPlan`
    and clone what you keep, or rebuild it. `replace(mut &x.lp,
    lexdb_bind.noPlan())` takes a whole plan. A `let` borrowed by another
    (`fcols = fromCols(&sp.sel)`) blocks `replace(mut &sp.sel.lp, ...)`
    while it is in scope: take the plan first (`spLp`). `[]` in an `if`
    needs the variable's type written.
  - The row changes after binding: semi-joins add hidden
    `\x00sjN.\x00rowidK` columns (`semiLookAdd`, `semiJoins`, through
    `addCol`); `q.lp` keeps the bound row (there is no `Query.bcols` any
    more: the row's `BCol`s are the `Get`/`Sub`/`Join` columns).
    `planFrom` must read the level ranges from `q.levels` (which semi-joins
    extend), not from the `LPlan`.
  - `Join`'s columns include USING's merged-away ones; `*` and NATURAL
    read `ColDef.using` and `pos`, which `BCol` does not carry. Add them
    to `BCol` before anything expands `*` from the `LPlan`.
  - A view's or FROM subquery's oid, "char", name, regproc, regclass and
    regtype columns are text in the outer row (`outType` through
    `lexdb_sql.oidType`), while the `Sub`'s plan has the true type: do not
    "fix" the row from the plan in passing (it changes typing and
    results); its own commit with tests.
  - A CTE's use is `CteRef` with no plan (the body is re-planned per use
    and its `Sel.lp` stays in its `SubPlan`); binding a CTE once is a
    later change. Expression subqueries have no `Apply` yet: they keep
    `Query.subs`' numbering (`SubPlan`, `subFixed`, `isSubCall`,
    `Frame.sub*`, `endScope`'s `kind`/`readAs`), which step 5 replaces.
  - `Agg` carries only the aggregates' number: the `#agg` slots come
    from `collectAggs` (planner), and so does `Sel.specs`. `Sort`'s keys
    are read over the Project's input and outputs (`orderValue`,
    `orderOut`: "not an input column" means an output alias; the known
    42803 difference from PostgreSQL rests on it).
  - The plan cache keeps `Sel`s, and with them `Sel.lp`: nothing of a run
    in it (no `Run`, no parameter values: `Limit` keeps the expressions,
    not `evalInt`'s numbers, which go through `sc.looks`).
  - Everything slice 1 does is per plan. A prepared SELECT is planned once
    (8 plans, every other select a hit, below); simple-protocol queries and
    UPDATE/DELETE are planned per run (UPDATE builds `Get` and `Filter`,
    no clone). Keep the binder's pass free of per-run work.
  - Tests compile against the sources: run the suite from a snapshot
    (`cp -r lexell/{cmd,tests,lib,tools}` to a scratch tree). Wait on a PID
    or file, not on `pgrep -f`. Timings under `flock ~/tpch/.bench.lock`.
- Gates (as 2d's): the suite (188, imports ok); the naming battery
  (`~/tpch-w/bind/bench/naming/run.sh BIN OUT`, 1,505 lines on main
  76118b8a and slice 1) identical; TPC-H all 22 against
  `~/tpch/out-baseline-1744ef99` (fields [0] and [8]), watching q2, q4,
  q17, q19, q20, q21, q22 (the subquery and semi-join shapes slice 2
  moves); the 35 queries; OLTP and the loads (`oltp.sh`); the plan cache
  (`pc.sh` on builds patched by `~/tpch-w/bind/e2/chk/pcpatch.py`); the
  simple-protocol planning A/B (`~/tpch-w/bind/e2/simple.sh OUT ROUNDS
  LABEL BIN ...`: point selects, updates, a 3-table join, each planned per
  run); and the scratch check (`~/tpch-w/bind/e2/chk/patch.py` on a copy
  of `lexell/cmd`; its anchors are asserted, so update them as code moves):
  after the split, `planFrom` reading `q.lp` must give the same `ms`/`ps`
  per level as today (compare their `exprText`s in the check build).

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
