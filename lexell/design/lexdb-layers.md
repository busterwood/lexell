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
    4-7,12-15 lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -O -o OUT`
    (the native backend; never the gcc path; always `-O`: section 6.3's Q1
    bisect found binaries built without it about 14% slower on q1).
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

**2e slice 2 as built: `buildQuery` is `bindFrom` then `planFrom`.**
Three commits on `redesign/bind` from main caaa5cfc, each built and
through the suite (188, imports ok): 22566849 (the semi-join alternatives
planned after the FROM pass), 81f83bfd (the split), dc60df84 (WHERE's
semi-join candidates found in place), and a fourth with this note. Way in
steps 1 and 2 of "Where 2e slice 1 left off"; `bindFrom` stays in
`lexdb_exec` (step 3, the move, waits for slice 3). No plan and no result
changes.

- `buildQuery` keeps its signature (its 13 callers do not change) and is
  now three parts:
  - the prologue (phase 1): the `Scope`'s hints taken as before (`early`,
    `locking`, `noRefKeys` onto `q`, `ordBy`, `ordLim`) with WHERE's
    semi-join candidates into a `FromHints` record. The candidates come
    from the parsed WHERE (`semiCands`: the AND tree walked in place,
    `semiParsed` on each conjunct; it used to copy every conjunct first,
    dc60df84), not from the resolved one: `pullCommonOr` can make a new
    top-level conjunct, so `semiResolved` on `q.lp`'s `Filter` would not
    give the same set.
  - `bindFrom(st, txn, from, where, params, subs, sc, q: mut &Query):
    FromBound` (phases 2-4, 6-7's resolve): pushes the frame, walks FROM
    (items, `addCol`, `Frame.cols`, USING/NATURAL, `pos`), plans and
    numbers the expression subqueries with the frame's `sub*` lists (the
    views' after them), resolves ON and USING's ON into each `Join`'s `on`
    and WHERE (after `pullCommonOr`, kept here for q19) into the `Filter`,
    and sets `q.lp`. `FromBound` is `anyUsing` (the right-join switch reads
    it) and `where`: whether `q.lp`'s top is WHERE's `Filter`. It still
    calls the planner in three places: `planSub` of a FROM subquery or a
    view and of each expression subquery (binds and plans), and `loadEst`
    of each table (phase 2).
  - `planFrom(st, txn, q: mut &Query, hs: &FromHints, bf: &FromBound,
    params, subs, selNames, star, sc, reorder)` (phases 3's alternatives,
    5, 6-7's placement, 8): the semi-join alternatives, `colAt`,
    `lastRight`, then `fromConds(&q.lp, bf.where, ms, cs)`, then the
    placement, `need`, implied equalities, join order, paths, hashing and
    semi-joins as before.
- `fromConds`/`onConds`: the k-th left-deep `Join`'s `on` conjuncts go to
  `ms[k]` (the leaf is level 0), WHERE's `Filter`'s to the list the
  placement walks. `conjuncts` copies, so the cost is today's: one copy of
  each ON and of WHERE (before, `bindFrom`'s part copied them out of the
  resolved trees and moved the trees into the plan; now it moves them in
  and `planFrom` copies them out). Level ranges come from `q.levels`, not
  the plan. A first FROM item's ON (SQL's grammar makes none; nor do
  `dmlFrom`, `mergeFrom`, `tsqlDml`, `oneTable`) would be a `Filter` over
  that item, read as level 0's, as `ms[0]` had it.
- The semi-join alternatives (a candidate's correlated EXISTS/IN planned
  again with `sc.noRefKeys`) moved from inside the subquery loop (between
  subquery i's plan and i+1's) to `planFrom`'s start, after ON and WHERE
  are resolved; the test reads `q.subs[i]` (`use`, `sel.q.refs`, `hashed`,
  `cte`) and the plan `subs[i]`. Why the move changes nothing: the frame's
  columns and USING marks are complete at both points; `outerRef` finds the
  refs the first plan of the subquery already added to the frames between
  (by text, so the same numbers); the `sub*` lists are read for the top
  frame only (the subquery's own); `sc.looks` gets the alternatives' looks
  later, and `looksHold` reads them as a set. A plan that fails is
  dropped as before, and the frame it may leave is now popped (before,
  it would have been the "top" the next subquery's lists went to).
- The scratch check (`~/tpch-w/bind/e5/tools/mspatch.py` on a copy of
  `lexell/cmd`; it finds main's `buildQuery` or the branch's `planFrom` by
  anchors, asserted): one `LPCHK MSPS` line per FROM pass after the
  placement (each level's `ms` and `ps`, and `q.top`, by `exprText`) and
  one `LPCHK MSEND` at its end (each level's alias, join, semi/anti,
  perRow, path index, `semiSub`, `src`, `cond`, `post`, `local`,
  `hashVals`; `q.top`). Builds of main caaa5cfc (`lexdb-chk-m`) and
  dc60df84 (`lexdb-chk-b`):
  - the suite (snapshots with slice 1's patched `run.py`, `LPCHK_OUT`):
    215,780 lines on main, 215,722 on the branch; sorted, identical but for
    58 lines (29 FROM passes) of `exec_autostats` and `exec_turns`, point
    selects that their concurrent tasks run "until it is done", whose
    count varies by run (balanced MSPS/MSEND in both);
  - the naming battery: 328 FROM passes, identical line for line;
  - TPC-H's 22: 194 lines, identical sorted; in order, q21's alternative
    for `l2` (the EXISTS planned without its outer keys) comes after the
    next subquery's plan instead of before, the move above.
- Gates: the suite on each commit's snapshot (188, imports ok); the naming
  battery (1,505 lines) identical from main, 81f83bfd, dc60df84 and both
  check builds; TPC-H all 22 checksums the baseline's (fields [0] and [8]
  against `~/tpch/out-baseline-1744ef99`) on every run below (main, the
  branch, their copies, both check builds).
- Speed, one pass against main caaa5cfc (`lexdb-mca`, built from `git
  archive` into `~/tpch-w/bind/e5/src-mca`; the branch at dc60df84,
  `lexdb-c`), as asked for an intermediate refactor slice:
  - TPC-H (`~/tpch-w/bind/e5/tpch1.sh`: `run.sh` SF1, 1 run, boost off by
    `run.sh`): total 29,433 against 29,445 ms (1.000). Past 1.5%: q1 1.027
    and q18 1.019; q20 0.976. One repeat on byte-identical copies
    (`lexdb-mcac`, `lexdb-cc`): total 29,378 against 29,364; q1 0.992 (the
    known copy noise), q18 1.029 (1,277 to 1,314 ms). q18 is +2.4% on both
    pairs. Its plan is planned once and is the same (the check's MSPS and
    MSEND lines for it are main's; `planSelect` is unchanged); the
    executor's code is unchanged but moved in the binary. Read as layout,
    not verified further (no more rounds, as asked).
  - `~/tpch-w/bind/e2/simple.sh` (pgbench `-M simple`, 4 clients, 10 s,
    boost off, one round, binaries alternating): point selects 37,505
    against 37,286 tps (0.994), updates 9,047 against 9,028 (0.998), the
    3-table join 15,671 against 15,480 (0.988). Within the floor: the
    split adds two calls and two small records per FROM pass and saves a
    copy of WHERE; it does not take back slice 1's cost (below).
  - Not run: the 35 queries, OLTP and the loads (`oltp.sh`), the plan
    cache count (`pc.sh`), `qmulti.sh`, `pstat.sh`, `pts.sh`: not asked
    for this slice, and the simple-protocol pass did not regress.
- Lines:

  | Module | main caaa5cfc | after |
  |---|---|---|
  | `lexdb_exec` | 27936 | 28042 |
  | `lexdb_bind` | 1936 | 1936 |

**Where 2e slice 2 left off, and how to start slice 3.** Slice 3 makes
`planSelect` (then `planSet`, `planMatch`, DML) read its clauses from the
`LPlan` instead of the `Stmt` (way in, 3, in "Where 2d left off"), and
should take back slice 1's +5% CPU on simple-protocol SELECT planning.
Everything named is in `lexdb_exec` unless the note says otherwise; search
for the names, since line numbers move.

- What is there after slice 2:
  - `buildQuery` = prologue (`FromHints`, `semiCands`) + `bindFrom` +
    `planFrom` (above). `planFrom` reads the FROM part's conditions from
    `q.lp` (`fromConds`, `onConds`); everything else it reads from `q`
    (`levels`, `cols`, `subs`) and from `subs` (the `Stmt`s, for the
    alternatives' re-plan).
  - `planSelect` is as slice 1 left it: it resolves each clause into the
    planner's variables and clones them into the plan (`lpExprs` the select
    list, `lpGroup`, `lpOrder` after DISTINCT ON's keys are added,
    `lpHaving`, `lpWins`; `lpOn` moved), then `selPlan` and `topPlan` wrap
    `q.lp` (Agg, Filter, Window, Project, Distinct, Sort, Limit), each with
    a copy of its input's columns (`lpCols`) or `outBCols(outs)`.
- Where slice 1's cost is (its profile: `selPlan` 1.8% inclusive,
  `outBCols` 0.8%, `lpCols` 0.6%, `copyBCols` 0.6%, plus the select list's
  clone and the plan's drop), and how slice 2's pattern takes it back: the
  binder moves the resolved expression into the plan, and the planner
  copies out only what it rewrites. The planner's rewrites already build
  new trees from a borrow (`collectAggs(&x, ...)`, `winMarks(&x)`,
  `winSlots(&x, n)`, `setSubst(&x, ...)` return an `Expr`), so where one
  runs the slice-1 clone is redundant: build the rewrite from the plan's
  expression. Where none runs (a point select: no aggregate, window or
  grouping set), `Sel.exprs` is the resolved list itself and the plan's
  copy is the extra cost; the saving needs the executor to read the
  `Project`'s expressions out of `Sel.lp` (or `Sel.exprs` to be the
  plan's, taken by `replace` when the plan is no longer needed: it is read
  by nothing yet), and `outBCols`' list to be made once. One clause per
  commit, as the way in says: the select list first (it is the one a point
  select pays), then ORDER BY (`lpOrder`: `enumPos` and DISTINCT ON's
  added keys are binder work; `ordKinds`, `desc`/`nullsFirst` from
  `s.order`), GROUP BY and HAVING (`resolveGroup`; the redundant keys
  dropped later are planner work), windows (`mergeWin`, `collKeyOf`),
  DISTINCT, LIMIT (`Limit` keeps expressions; `evalInt` and `sc.looks`
  stay planner), locking (`applyLocks`, `Level.lock`: no `Lock` operator
  yet).
- Then the move of `bindFrom` into `lexdb_bind` (slice 2's way in, step 3):
  it needs, from exec, the catalog (`findTable`, `findSeq`, `viewQuery`,
  `readAcl` for a view's owner, `scCheck` with `sc.asRole`/`sc.whos`,
  `enumOrder`'s enum types), and it calls the planner: `planSub` for FROM
  subqueries, views and expression subqueries (the binder half of
  `planSub`/`planSelect` must be separable first: that is slice 3's
  ground), and `loadEst`. `loadEst(.., false)` (statistics where a table
  has two candidate paths) reads only the level's `Table`, so it can move
  to `planFrom`'s start (every level with `t.tree >= 0`; a view's level has
  `tree` -1 and gets `noEst` either way) as a first, separate commit.
- Traps (slice 1's still hold; and):
  - `FromBound.where` tells WHERE's `Filter` from a first item's ON
    `Filter` (one level, no WHERE): do not drop it in favour of "the top
    `Filter` is WHERE".
  - `pullCommonOr` runs in `bindFrom` on the parsed WHERE; the semi-join
    candidates are found on the parsed WHERE (`semiCands`), not on
    `q.lp`'s resolved one (`pullCommonOr` changes the top-level set).
    Moving either is its own commit with q19's (and q4's, q21's, q22's)
    plan and checksum as the gate.
  - The alternatives in `planFrom` re-plan from `subs[i]`: when
    subqueries are bound once into an `Apply` (step 5), they need the bound
    form planned twice, or the planner's own copy with `noRefKeys`.
  - `exec_autostats` and `exec_turns` run a variable number of point
    selects: a check that counts or diffs per-statement lines must allow
    for them (sort, and look at what differs).
  - The suite compiles each test against the sources: run it from a
    snapshot (`cp -r lexell/{cmd,tests,lib,tools}`;
    `~/tpch-w/bind/e5/suite.sh TAG` does it). To commit one step while the
    tree holds the next, commit the snapshot's file and copy the next back.
- Gates (as slice 2's): the suite (188, imports ok); the naming battery
  (`~/tpch-w/bind/bench/naming/run.sh BIN OUT`, 1,505 lines) identical; TPC-H
  all 22 against `~/tpch/out-baseline-1744ef99` (fields [0] and [8]),
  watching q1 and q18 (layout-sensitive here) and q2, q4, q17, q19, q20,
  q21, q22; the simple-protocol A/B (`~/tpch-w/bind/e2/simple.sh OUT ROUNDS
  LABEL BIN ...`) and `pk_point20k` (`~/tpch-w/bind/e2/pts.sh`), which is
  where slice 3 must show slice 1's +5% coming back; the plan cache
  (`pc.sh`, `~/tpch-w/bind/e2/chk/pcpatch.py`): whatever moves into
  `Sel.lp` is cached with the `Sel`, so nothing of a run in it; the
  scratch checks: slice 1's (`~/tpch-w/bind/e2/chk/patch.py`, the plan's
  columns against the `Sel`'s; its anchors are asserted and need updating
  for `bindFrom`) and slice 2's (`mspatch.py`, while `planFrom`'s
  placement stays), plus for each clause moved a check that the planner's
  expressions read from the plan have the same `exprText`s as from the
  `Stmt`.

**2e slice 3a as built: the select list and ORDER BY go into the plan,
not copies.** Three commits on `redesign/bind` from main f8cc121e, each
built and through the suite (188, imports ok): 4806e9dd (the select list),
0f61fd0d (ORDER BY), 8cd7279d (`loadEst` at `planFrom`'s start), and a
fourth with this note. The first part of "planSelect reads its clauses
from the LPlan" (way in of "Where 2e slice 2 left off"); GROUP BY, HAVING,
windows, DISTINCT, LIMIT, locking, `planSet`, `planMatch` and DML are
slice 3b. No plan and no result changes.

- The select list (4806e9dd). `planSelect` no longer clones the resolved
  list (`lpExprs` is gone). `exprs` is the list `selectCols` resolves; the
  planner reads it in place (GROUP BY's and DISTINCT ON's matching, the
  aggregate and DISTINCT tests, `orderCols`, `minMax`, `feedbackOf`), and
  its first rewrite builds the planner's own list from it with
  `rewriteList(xs, nx, keep, done)`: the new list becomes `exprs`, the
  resolved one goes to `bx` for the plan (no clone; a second rewrite just
  replaces `exprs`). The rewrites are `winMarks`, `collectAggs` and
  `winSlots`; `setSubst`'s lists (`gx`) are built from `collectAggs`'
  output, so they come after the first rewrite.
  - Where no rewrite runs (no aggregate, grouping or window: every point
    select), `Sel.exprs` is the resolved list and the `Project`'s is []:
    the plan lends it. `lexdb_bind.lpLentExprs(p)` gives the `Project`'s
    column count n where it lends (`Sel.exprs`' first n: FOR UPDATE's key
    columns are appended after them, `semiJoins` appends a subquery's
    key columns after them), else -1; it looks under the `Sel`'s own
    operators (Match, Limit, Sort, Distinct). A list of no expressions
    has no columns either, so [] with columns is unambiguous; no flag.
  - `takeLp(sel)` takes a `Sel`'s plan whole: where the plan lends, the
    `Project` gets a copy of `Sel.exprs`' first n (`lpRestore`). It is used
    where a plan leaves its `Sel` (`bindFrom`'s FROM subquery and view,
    the two sides of `planSet`) and where the `Sel`'s lists change after
    planning (`hashSub` replaces `exprs` and empties `order`: its
    `sp.sel.lp = takeLp(...)` comes first). So the copy is paid where the
    plan is moved into another plan (as slice 1 paid it, once), and a
    plan in a `Sub`, `SetOp` or `Recursive` never lends.
  - A function's or VALUES' `Sel` lent as slice 1 left it ([]): `planSub`
    replaces its plan by `Func`/`Values` (arguments cloned from
    `Sel.exprs`, as before).
  - `outBCols` and `copyBCols` make their lists with `withCapacity(n)`
    (one allocation, no growth). Read as "make outBCols' list once".
- ORDER BY (0f61fd0d), the same way: the keys as resolved (enum positions,
  DISTINCT ON's added keys) are `order`; the first rewrite (`winMarks`,
  `collectAggs`, `winSlots`) sets them aside in `bo` for the `Sort`; where
  none runs `Sel.order` is the list and the `Sort`'s keys are []
  (`lexdb_bind.lpLentOrder`: [] keys with `desc` non-empty). `topPlan`
  makes a `Sort` where `desc` has entries (it was `len(order) > 0`; equal
  lengths). `lpRestore(p, xs, order)` fills either; `takeLp` copies
  `Sel.order` for a lending `Sort`. `desc`, `nullsFirst` and `ordKinds` stay
  as they were (copies of bools; not moved). `planSet`'s own ORDER BY
  keeps its clone (slice 3b).
- `loadEst` (8cd7279d): `bindFrom` no longer calls it. `planFrom` starts
  by loading each table level's statistics (`src < 0 && work < 0`, which
  is `bindFrom`'s old `f.sub < 0 && f.work < 0`: a view's level has its
  `work` set, a FROM subquery's its `src`) before anything reads `est`.
  `bindFrom` now calls the planner only through `planSub`.
- The scratch check (`~/tpch-w/bind/e6/tools/xpatch.py` on a copy of
  `lexell/cmd`, main's or the branch's; anchors asserted): one `LPCHK
  XSEL` line at the end of `planSelect` and `planSet` and of `hashSub`,
  with `Sel.exprs`, `Sel.order`, `desc`/`nullsFirst`, `gx`/`gord` (the
  planner's lists) and every `Project`'s list and `Sort`'s keys in the
  `Sel`'s plan by `exprText` (a list the top lends read from the `Sel`;
  one lent anywhere else printed `LENT`). Builds of main f8cc121e
  (`lexdb-chk-m`) and 0f61fd0d (`lexdb-chk-b2`):
  - the suite (snapshots with slice 1's patched `run.py`): 99,967 lines
    on main, 98,694 on the branch; sorted, identical but for 1,273
    lines of `exec_autostats` (one point select repeated "until it is
    done", whose count varies by run). No `LENT` in either;
  - the naming battery: 284 lines, identical line for line (also at
    4806e9dd); TPC-H's 22: 105 lines, identical line for line;
  - a throwaway build counting what lends, over the battery: of 260
    `planSelect`s, 214 lend the select list (46 have the planner's own:
    aggregates, windows) and 87 lend their ORDER BY keys.
  - `loadEst`'s move, slice 2's check (`~/tpch-w/bind/e5/tools/mspatch.py`:
    `ms`/`ps` per level, and each level's path, join and semi-join at
    the end) on main and 8cd7279d: the battery's 656 lines and TPC-H's
    194 identical line for line.
- Gates: the suite on each commit's snapshot (188, imports ok); the naming
  battery (1,505 lines) identical from main, each commit and the check
  builds; TPC-H all 22 checksums the baseline's (fields [0] and [8]
  against `~/tpch/out-baseline-1744ef99`) on every run (main, the branch,
  their copies, the four check builds).
- Speed, one pass, against main f8cc121e (`lexdb-mf8`) and 76118b8a from
  before slice 1 (`lexdb-m761`), both built from `git archive` into
  `~/tpch-w/bind/e6/src-*`; the branch at 8cd7279d (`lexdb-b`):
  - TPC-H (`~/tpch-w/bind/e6/tpch1.sh`, SF1, 1 run, boost off by
    `run.sh`): total 29,332 against 29,396 ms (0.998). Past 1.5%: q1 1.037
    (2,259 to 2,342 ms), and q2 0.983, q18 0.981, q22 0.985 the other
    way. One repeat on byte-identical copies (`lexdb-mf8c`, `lexdb-bc`):
    total 29,322 against 29,335 (1.000), q1 0.997 (main's copy took
    2,370 ms: its first run was the outlier); past 1.5% only faster ones
    (q5 0.974, q18 0.984, q20 0.981).
  - `~/tpch-w/bind/e2/simple.sh` (pgbench `-M simple`, 4 clients, 10 s,
    boost off, one round, binaries alternating), tps:

    | | m761 | main f8cc121e | branch | branch / main | branch / m761 |
    |---|---|---|---|---|---|
    | point selects | 38,832 | 37,398 | 37,303 | 0.997 | 0.961 |
    | updates | 9,077 | 9,110 | 9,077 | 0.996 | 1.000 |
    | 3-table join, ORDER BY, LIMIT | 16,527 | 15,365 | 15,798 | 1.028 | 0.956 |

  - `pk_point20k` (`~/tpch-w/bind/e2/pts.sh`, 20,000 `select * from w
    where id = n` by the simple protocol; 5 runs per server, one round,
    boost off), server CPU ms, medians (range): m761 832 (828-835), main
    884 (883-885), branch 866 (865-874); wall 894, 947, 931.
  - How much of slice 1's cost came back: on `pk_point20k`, main is +6.3%
    over m761 and the branch +4.1%: 18 of the 52 ms, about a third. On the
    join, 433 of the 1,162 tps lost (37%). On pgbench's point select
    (`SELECT abalance`, one output column, no ORDER BY) nothing measurable:
    there the clone saved is one `Expr.Col`, within the round's noise.
    The rest is the per-operator column lists the FROM part builds (the
    `Get`'s `bcolOf` per table column, the `Filter`'s copy of them), the
    `Project`'s `outBCols` and the plan's drop: slice 1's scratch variant
    without the `Get`, `Join` and `Filter` columns (`x2`) measured +1.4%
    where the branch then was +5.3%. Not in this slice's scope.
  - Not run (as asked): more rounds, the 35 queries, OLTP and the loads,
    the plan cache count (`pc.sh`), `qmulti.sh`, `pstat.sh`, a profile.
    No simple-protocol result regressed against main.
- Lines:

  | Module | main f8cc121e | after |
  |---|---|---|
  | `lexdb_exec` | 28042 | 28089 |
  | `lexdb_bind` | 1936 | 1982 |

**Where 2e slice 3a left off, and how to start slice 3b.** Slice 3b moves
the rest of `planSelect`'s clauses the same way, then `planSet`,
`planMatch` and DML, and should take back what is left of slice 1's cost
on simple-protocol SELECT planning. Everything named is in `lexdb_exec`
unless the note says otherwise; search for the names, since line numbers
move.

- What is there after slice 3a:
  - `planSelect`'s select list and ORDER BY are the binder's lists, read
    in place and moved into the plan (`bx`, `bo` by `rewriteList`), or
    lent to the `Sel` where no rewrite runs (`lexdb_bind.lpLentExprs`,
    `lpLentOrder`, `lpRestore`; `takeLp`). `lpGroup`, `lpHaving`, `lpWins`
    are still clones; `lpOn` (DISTINCT ON) was already moved; LIMIT's
    `Limit` clones `s.limit`/`s.offset` (`optClone`).
  - `bindFrom` calls the planner only through `planSub` (FROM subqueries,
    views, expression subqueries); statistics load in `planFrom`.
- The pattern, for each remaining clause: find where the planner first
  rewrites it and whether a rewrite always runs.
  - GROUP BY (`lpGroup`): resolved by `resolveGroup` (binder); the planner
    then drops redundant keys (`gb`, by the primary keys: a rebuild with
    `clone`), so where `aggQ` and one set, `groupBy` is rebuilt by clones
    anyway. Move the resolved list into the `Agg` and build `gb` from it
    (the redundant-key loop reads `groupBy[gi]`; clone only the kept
    ones, as today). `Sel.groupBy` is also replaced by `hashSub` (a
    scalar subquery's keys): `takeLp` already runs first there, so a lent
    group list would need `lpRestore` to fill the `Agg` too.
  - HAVING (`lpHaving`): `collectAggs` always rewrites it where present
    (it is only present with `aggQ`), so the resolved tree can move into
    the `Filter` and `collectAggs` read it there; no lending needed.
  - Windows (`lpWins`): `winPlan` and the `collectAggs` pass over
    `wdefs` rewrite them only with aggregates; `wins` (`WinPlan`) is the
    planner's form, so `wdefs` can move into the `Window` after `winPlan`
    has read it (`winPlan(&d)` borrows), with the `collectAggs` pass
    building its own copies first.
  - DISTINCT and LIMIT: `Distinct` takes `lpOn` already; `Limit` holds
    the parsed `s.limit`/`s.offset` (not resolved: `evalInt` reads the
    `Stmt`'s per plan): a clone of a literal, cheap; moving it needs the
    `Stmt` owned, which it is not (the plan cache's statements are
    borrowed).
  - Locking: no `Lock` operator yet; `applyLocks` sets `Level.lock`.
- Where the remaining cost is: not in `planSelect`'s clauses. For a point
  select every list is now built once, except the column lists: the
  `Get`'s (`bcolOf` of each table column, in `bindFrom`), the `Filter`'s
  copy of them (`lpCols`), the `Project`'s (`outBCols`), each with its
  strings counted, and dropping the plan. Slice 1's `x2` measured those
  FROM-part lists at about 2% of `pk_point20k`'s CPU. Ways to take them
  back, for a coordinator to choose (each changes slice 1's "every
  operator with its list" shape, which the user asked for): the
  pass-through operators' columns read from their input (`x3`, measured
  small); or the `Get`'s columns made once per table version (kept with
  the catalog's `Table`) and shared. Profile first (`~/tpch-w/bind/e2/
  profg.sh`, `incl.py`; symbols from `LXL_NATIVE_MAP`).
- Traps (slice 2's still hold; and):
  - A plan that lends (`Project` [] with columns, `Sort` [] keys with
    `desc`) is only whole beside its `Sel`. Anything that moves a `Sel`'s
    plan out of it, or changes `Sel.exprs`' first n or `Sel.order` after
    `planSelect`, must call `takeLp` first (today: `bindFrom` twice,
    `planSet`, `hashSub`). Appending after the first n is fine
    (`semiJoins`, FOR UPDATE). A reader of `Sel.lp` reads the lent lists
    from the `Sel` (or takes the plan with `takeLp`). Slice 1's check
    (`patch.py`'s `lpValid`: a `Project`'s expressions one per column, a
    `Sort`'s keys as many as `desc`) would flag every lending plan; it
    was not run or updated in 3a.
  - `rewriteList` moves the resolved list aside only on the first
    rewrite; a later plain assignment (`exprs = replace(mut &gx[0], [])`)
    is right only because `collectAggs` has already run. A new rewrite
    placed before the first must go through `rewriteList`.
  - `topPlan` makes a `Sort` where `desc` has entries, not `order`: a
    caller must pass `desc` as long as the keys.
  - `rewrite` is taken (a table rewrite for ALTER); the helper is
    `rewriteList`.
- Gates (as slice 3a's): the suite (188, imports ok); the naming battery
  (1,505 lines) identical; TPC-H all 22 against
  `~/tpch/out-baseline-1744ef99` (fields [0] and [8]), q1 and q18
  layout-sensitive; the simple-protocol A/B (`simple.sh`) and
  `pk_point20k` (`pts.sh`) against m761 and main; and for each clause
  moved the `exprText` check: `xpatch.py` prints the `Sel`'s lists and
  every `Project`'s and `Sort`'s; extend `xTree` to print `Agg`'s keys,
  `Filter`'s predicate and `Window`'s definitions as their clauses move.

**2e slice 3b as built: GROUP BY, HAVING and windows go into the plan,
and pass-through operators hold no column list.** Four commits on
`redesign/bind` from main 3bad2694: e219bc3c (GROUP BY), 4ed2d3e4 (HAVING),
da7a587b (windows), bd99ed3d (pass-through operators), and a fifth with this
note. The suite passed (188, imports ok) on snapshots of 4ed2d3e4 (GROUP BY
and HAVING), da7a587b and bd99ed3d; e219bc3c alone was not run. No plan and
no result changes. DISTINCT, LIMIT, locking, `planSet`, `planMatch` and DML
are as slice 3a left them (slice 3c).

- GROUP BY (e219bc3c). `lpGroup` (a clone) is gone. `groupBy` is the list
  `resolveGroup` gives; the planner reads it in place (the window and
  aggregate checks, `gtexts`, `okLevels`, the redundant-key loop). With one
  grouping set (plain GROUP BY) the redundant-key loop builds the
  planner's list by clones of the kept keys (`gb`, as before) and the
  resolved list moves into the `Agg` (`bg = replace(mut &groupBy, gb)`).
  With grouping sets the `Sel` keeps the resolved list (`Sel.groupBy` is
  the sets' key list) and the `Agg` gets a copy (`cloneAll`, as `lpGroup`
  was). No lending: `hashSub` replaces `Sel.groupBy` only where it is
  empty.
- HAVING (4ed2d3e4). `lpHaving` is gone. HAVING is present only with
  aggregates, and `collectAggs` always rewrites it there, so the rewrite
  replaces it and the resolved tree goes to the `Filter` (`bh =
  replace(mut &having, rh)`).
- Windows (da7a587b). `lpWins` is gone. With aggregates, the `collectAggs`
  pass over the definitions builds new ones (it rewrote them in place
  after a clone of each call) and the resolved ones go aside (`bw =
  replace(mut &wdefs, cw)`); the aggregates' slots come in the same order
  (each call's arguments, then its partitions, then its order). Without,
  nothing rewrites them, and they move into the `Window` after `winPlan`
  has read them (`winPlan(&d)` copies what it keeps). `wdefs` is read by
  nothing after `winPlan`.
- Pass-through operators (bd99ed3d), the coordinator's choice of the two
  ways "Where 2e slice 3a left off" gave. `Filter`, `Agg`, `Window`,
  `Distinct`, `Sort` and `Limit` keep their `[]BCol` field and hold []:
  their columns are their input's. `lexdb_bind.lpColumns(p): &[]BCol`
  gives any operator's columns as a borrow (a pass-through's from its
  input, recursively; one that holds a list gives its own, so a later
  `Agg` with its own outputs needs no type change); `lpCols` is
  `copyBCols(lpColumns(p))`. `bindFrom`'s WHERE and first-item `Filter`s,
  `selPlan`'s and `topPlan`'s operators are built with []. A `Join`'s
  list is its sides' copied once (it copied the right side's twice:
  `lpCols` then a second loop). The plan stays self-describing: nothing
  needs the `Sel` to read a column list (the lent `Project` list and
  `Sort` keys are expressions, not columns). The other way, the `Get`'s
  columns made once per table version and shared, is not simple: the
  catalog decodes a `Table` per statement (`findTable`, `decTable`) and has
  no per-version cache to keep them in.
- Tried and not kept: `BCol` as a `value record` (inline in its arrays, no
  allocation per column), on top of bd99ed3d's change: `pk_point20k`
  CPU 665 against 660 ms, no gain in one round.
- The scratch checks, on builds of main 3bad2694 (`lexdb-ck-m`) and
  bd99ed3d (`lexdb-ck-b`) with both patches applied
  (`~/tpch-w/bind/e7/tools/xpatch.py` and `patch.py`, anchors asserted;
  the suite from snapshots with slice 1's patched `run.py`, `LPCHK_OUT`):
  - `xpatch.py` (the `exprText` check), extended: `xTree` prints each
    `Agg`'s keys, sets and aggregate count, each `Filter`'s predicate
    (WHERE's and HAVING's) and each `Window`'s definitions (call,
    partitions, order with directions, frame); the `XSEL` line adds the
    `Sel`'s `groupBy`, `having`, the aggregates' specs (name, arguments,
    filter, order, text) and the window plans (`WinPlan`: function,
    arguments, partitions, order, directions, the aggregate's spec). The
    naming battery's 284 `XSEL` lines and TPC-H's 105 identical line for
    line (also at da7a587b against main, xpatch alone); the suite's,
    sorted, identical but for `exec_autostats` (2,387 more point selects
    of one shape, different keys) and `exec_turns` (one), whose counts vary
    by run.
  - `patch.py` (slice 1's plan check), updated: its anchors are in
    `bindFrom` (the FROM part's columns against `q.cols` where `q.lp` is
    set) and at `planFrom`'s end; `lpValid` accepts a lending plan (a
    `Project` of [] expressions with columns, or a `Sort` of [] keys with
    `desc`, only on the `Sel`'s own chain of Match, Limit, Sort, Distinct
    and Project, and only as many as the `Sel` has: `Sel.exprs` at least
    the `Project`'s columns, `Sel.order` as many as `desc`) and a
    pass-through operator with [] (one with a list is compared with its
    input's, as before); a `Filter` with no predicate or a `Window` with
    no definition is flagged. The top's columns (`lpCols`, through the
    pass-through operators) against `fromCols(sel)` at `select`,
    `selectWith` and `planSub`, as before, with an `LPCHK OK` line per
    `Sel` checked. Results identical on main and the branch: the battery
    233 `Sel`s checked, TPC-H's and the suite's lines identical (sorted,
    but for `exec_autostats` and `exec_turns` as above). Nothing flagged
    but slice 1's three by-design differences (the semi-joins' hidden
    columns at `planFrom`'s end, `from-cols-end`; oid, name and the like
    as text in a FROM subquery's or view's row, `subty`; a view's column
    list renaming its plan's outputs, `sub-name`). No lent list was found
    off the `Sel`'s chain or longer than the `Sel`'s.
- Gates: the suite on the snapshots above (188, imports ok); the naming
  battery (1,505 lines) identical from main, da7a587b, bd99ed3d and both
  check builds; TPC-H all 22 checksums the baseline's (fields [0] and [8]
  against `~/tpch/out-baseline-1744ef99`) on every run (main, the branch,
  the check builds).
- Speed, one pass, against main 3bad2694 (`~/tpch-w/bind/e7/lexdb-m3ba`,
  from `git archive`; byte-identical to slice 3a's `lexdb-b`) and
  76118b8a from before slice 1 (`~/tpch-w/bind/e6/lexdb-m761`); the
  branch at bd99ed3d (`lexdb-b`). CPU boost on (left on as asked; slice
  3a's simple-protocol numbers were with it off, so only the ratios
  compare):
  - TPC-H (`~/tpch-w/bind/e7/tpch1.sh`, SF1, 1 run): total 29,214 against
    29,284 ms (0.998). Past 1.5%: q2 1.022 (63.6 to 65.0 ms), and q18 0.984
    the other way. One repeat on byte-identical copies (`lexdb-m3bac`,
    `lexdb-bc`): total 29,241 against 29,285 (0.999), q2 1.011 (63.7 to
    64.4 ms); past 1.5% only faster ones (q9 0.985, q18 0.978). q2 plans
    once; read as noise.
  - `~/tpch-w/bind/e2/simple.sh` (pgbench `-M simple`, 4 clients, 10 s,
    one round, binaries alternating), tps:

    | | m761 | main 3bad2694 | branch | branch / main | branch / m761 |
    |---|---|---|---|---|---|
    | point selects | 50,646 | 48,855 | 49,106 | 1.005 | 0.970 |
    | updates | 9,487 | 9,481 | 9,478 | 1.000 | 0.999 |
    | 3-table join, ORDER BY, LIMIT | 21,405 | 20,226 | 20,643 | 1.021 | 0.964 |

  - `pk_point20k` (`~/tpch-w/bind/e6/pts.sh`, 5 runs per server, one
    round), server CPU ms, medians (range): m761 643 (641-645), main 669
    (667-670), branch 657 (656-659); wall 691, 717, 705. Main is +4.0%
    over m761, the branch +2.2%: 12 of the 26 ms come back, short of the
    ~1.5% asked. An exploratory round before the commit (the profile
    step): m761 646, main 669, bd99ed3d's change 660, with `BCol` a value
    record as well 665.
  - The profile (`~/tpch-w/bind/e2/profg.sh`, `incl.py`; maps in
    `~/tpch-w/bind/e7/*.map`), inclusive, at da7a587b: `selPlan` 1.05%
    (`outBCols` 0.82%), `lpCols` 0.51% (the WHERE `Filter`'s copy),
    `copyBCols` 0.34%, `bcolOf` 0.29% (m761 0.46%: its `Query.bcols`);
    after the pass-through change `lpCols` is gone from the path and
    `outBCols` is 0.63%. What remains over m761 is the `Project`'s
    columns, the plan's three nodes and their drop, and layout: slice 1's
    scratch build with no plan lists at all (`x2`) was still +1.4% over
    m761.
  - Not run (as asked): more rounds, the 35 queries, OLTP and the loads,
    the plan cache count, `qmulti.sh`, `pstat.sh`.
- Lines:

  | Module | main 3bad2694 | after |
  |---|---|---|
  | `lexdb_exec` | 28089 | 28087 |
  | `lexdb_bind` | 1982 | 1990 |

**Where 2e slice 3b left off, and how to start slice 3c.** Slice 3c makes
`planSet`, `planMatch` and DML read from the plan, as slices 3a-3b did
`planSelect`'s clauses; then `bindFrom` can move into `lexdb_bind` (slice
2's way in, step 3). Everything named is in `lexdb_exec` unless the note
says otherwise; search for the names, since line numbers move.

- What is there after slice 3b:
  - `planSelect` keeps no clone of a resolved clause but LIMIT's
    (`topPlan`'s `optClone` of the parsed `s.limit`/`s.offset`, cheap: a
    literal) and DISTINCT ON's (`lpOn`, moved since slice 1). The select
    list and ORDER BY lend where no rewrite runs (`lpLentExprs`,
    `lpLentOrder`, `lpRestore`, `takeLp`); GROUP BY, HAVING and windows
    never lend (the `Agg`, `Filter` and `Window` always hold theirs).
  - Pass-through operators hold [] columns; read any operator's columns
    with `lexdb_bind.lpColumns` (a borrow) or `lpCols` (a copy), never by
    matching the arm's last field.
  - `planSet` builds `SetOp`/`Recursive` over `takeLp` of each side and
    clones its own ORDER BY for `topPlan` (slice 3a left it); `planMatch`
    wraps in `Match`; DML (`insert`, `update`, `delete`, `merge`) builds
    the FROM/WHERE part (`q.lp`) and nothing over it.
- The pattern for 3c, as before: find where the planner first rewrites a
  list and whether a rewrite always runs; move the resolved list into the
  plan where one does, lend it where none does (and teach `lpRestore`,
  `takeLp`, `lpLent*` and `patch.py`'s `lpValid` any new lending).
  - `planSet`'s ORDER BY: the parsed keys (an output's name or number,
    checked against `outs`, not resolved) cloned into `Sel.order`, then
    cloned again for the `Sort` (`topPlan(set, s, cloneAll(&order), ...)`).
    The `Sort` can lend them as `planSelect`'s does, but `lpRestore`
    panics where a lending `Sort` has no `Project` under it (a `SetOp`):
    teach it that first, since `takeLp` runs on a set that is a side of
    another set.
  - DML: UPDATE and DELETE are planned per run (no plan cache), so what
    they build is per-statement cost; they read `q.lp`'s `Filter` only
    through `planFrom`. A `Lock` operator (FOR UPDATE, `applyLocks`,
    `Level.lock`) and DML operators (`Insert`, `Update`, `Delete`,
    `Merge`) are new arms: add them to `lpColumns`, `lpValid`, `xTree`.
  - LIMIT: moving `s.limit`/`s.offset` needs an owned `Stmt` (the plan
    cache's statements are borrowed); not worth it alone.
- Where the remaining planning cost is: `pk_point20k` (9 columns: `Get`,
  `Filter`, `Project`) builds the `Get`'s columns (`bcolOf` per table
  column, as m761's `Query.bcols` did) and the `Project`'s (`outBCols`,
  0.6% of the server's cycles in the profile), allocates three plan nodes
  and drops them. Profiles of byte-different builds move single functions
  by 2-4% (the parser, unchanged since m761, at 13.9%, 13.3% and 17.3% of
  three profiles), so below about 1% they do not tell layout from cost:
  use `~/tpch-w/bind/e7/tools/selfdiff.py` (self or inclusive counts of
  two profiles side by side) and `under.py` (callees and leaves under a
  function) for direction, and `pts.sh` for the number. Ways left, none
  simple: the `Project`'s columns made from the `Get`'s where the select
  list is `*` (the same names and types but the alias); a per-table-version
  `BCol` list kept by a catalog cache, which does not exist (`findTable`
  decodes per statement).
- Traps (slice 3a's still hold; and):
  - `bw` holds the resolved window definitions only where the
    `collectAggs` pass ran; otherwise `wdefs` moves after `winPlan`. A
    reader of `wdefs` added after `winPlan` would find it empty.
  - With grouping sets `Sel.groupBy` is the resolved list (the sets' key
    list) and the `Agg` a copy; with plain GROUP BY `Sel.groupBy` is the
    planner's (redundant keys dropped) and the `Agg` the resolved list.
    `exprText` of both appear in the check's `XSEL` line.
  - `lpColumns` returns a borrow into the plan: copy (`lpCols`,
    `copyBCols`) before moving or replacing the plan it came from.
  - `patch.py`'s `lpValid` and `xpatch.py`'s `xTree` name every arm
    with its arity; new arms or fields need both updated.
- Gates (as slice 3b's): the suite (188, imports ok) from a snapshot of
  the commit (`~/tpch-w/bind/e7/suitec.sh TAG REV`, a `git archive`);
  the naming battery (1,505 lines) identical; TPC-H all 22 against
  `~/tpch/out-baseline-1744ef99`; `xpatch.py` and `patch.py` together
  on builds of main and the branch (`~/tpch-w/bind/e7/ckchain.sh`: TPC-H
  and the suite on both; the battery by `run.sh`), identical but for
  `exec_autostats`/`exec_turns`; `simple.sh` and `pts.sh` against m761
  and main, with the updates (DML is planned per run) watched.

**2e slice 3c as built: a set's ORDER BY lends, MATCH_RECOGNIZE's
definition, FOR UPDATE and DML go into the plan.** Four commits on
`redesign/bind` from main 0b147ed9: 18a8952d (`planSet`'s ORDER BY),
a07055e1 (`planMatch`), d7663151 (`Lock`), b3cc2219 (DML), and a fifth
with this note. The suite passed (188, imports ok) on the snapshot of each.
No plan and no result changes. Nothing reads the new arms but the checks.

- A set's ORDER BY (18a8952d). `planSet` clones the parsed keys once,
  into `Sel.order`; the `Sort` lends them (`[]` keys, `desc` as long:
  `lpLentOrder`), as `planSelect`'s does where no rewrite runs. It was
  cloned twice (`topPlan(set, s, cloneAll(&order), ...)`).
  `lexdb_bind.lpRestore` keeps a lending `Sort`'s input as it is where
  nothing under it lends (`xs` [], so no `Project` is looked for: a
  `SetOp` or `Recursive` there), so `takeLp` restores a set that is a side
  of another set, a FROM subquery, a view, a hashed subquery's or an
  INSERT ... SELECT's source.
- MATCH_RECOGNIZE (a07055e1). `planMatch` builds the `Match` over the
  `Sel`'s plan (`planSub` wrapped it, with its columns only).
  `LPlan.Match(input, MatchDef, cols)`; `lexdb_bind.MatchDef`: PARTITION
  BY's input columns (`[]int`: they are names), ORDER BY's keys as
  resolved with `desc`/`nullsFirst`, each pattern variable's DEFINE
  (`None`: always true) and the MEASURES as resolved, navigations marked
  (`#mrnav(k, arg)`, `k` the `MrPlan.navs` entry). DEFINE and MEASURES move
  into the plan after `mrSlots` has built the planner's slotted trees from
  them (no clone); ORDER BY's keys are cloned once for the planner's
  collation keys (`collKeyOf` takes its argument; a key per MR clause,
  planned once per statement). The pattern program, AFTER MATCH SKIP and
  the navigations' kinds and offsets stay in `MrPlan`, the planner's.
  - "Read from the plan": `planMatch` still reads its input columns from
    `Sel.outs`, not from the plan's columns (`lpColumns(&sel.lp)`, the
    same names and spells): `inCols` is built by `outType`, which carries
    a dialect's wire hint (`OutCol.scale`: T-SQL's datetime, varchar(n),
    int widths) into the `TypeName` that typing and `exprScale` read. A
    `BCol`'s `Ty` keeps only the typmod (`tyOf`), so a `TypeName` rebuilt
    from it differs for the T-SQL doors (`tds_mr`). Reading the plan's
    columns there needs the hint on `Ty` (or `BCol`) first.
- FOR UPDATE (d7663151). `LPlan.Lock(input, mode, wait, levels, [])`
  over the FROM and WHERE part (under any `Agg`, `Project`, `Sort`,
  `Limit`: FOR UPDATE allows no grouping or DISTINCT, and its rows are the
  base tables'), `lexdb_sql.LOCK_*`, `WAIT_*`, and the query levels
  `applyLocks` set `Level.lock` on (FOR ... OF's named ones, else every
  table level). A pass-through (`lpColumns`); not on the `Sel`'s own chain,
  so `lpLentExprs`, `lpLentOrder` and `lpRestore` need no arm.
- DML (b3cc2219). Four arms, each with RETURNING's columns (`retBCols`:
  `outBCols(&ret.outs)`, [] without RETURNING), built as a local beside
  the executor's structures and dropped (no plan cache for DML: the
  check reads it where it is built):
  - `Insert(table, targets, source, cols)`: the target's name, the
    columns the source's values go to in order, and the source: an
    INSERT ... SELECT's plan, taken from its `Sel` by `takeLp` (the `Sel`
    still runs; its lent lists are copied, once per statement); VALUES as
    `Values(width, [], [])`, its rows the statement's (`insertRows` reads
    `s.rows`, or its own resolved `rows` where there are subqueries or
    RETURNING), each value coerced to its target column's type, so the
    `Values` has no columns of its own. ON CONFLICT stays the executor's
    (`Upsert`).
  - `Update(source, targets, cols)`: the FROM and WHERE part (`q.lp`
    moved out of the `Query`: nothing reads it after `planFrom`), the
    target first; the columns SET assigns (`copyInts`). The SET
    expressions stay the executor's (`sets`, resolved and `bpAssign`ed).
  - `Delete(source, cols)`: as `Update`, USING's items after the target.
  - `Merge(source, cols)`: the source item joined to the target (the
    last item, `mergeFrom`) by ON; the WHEN clauses (`MClause`) stay the
    executor's.
  - Per run, UPDATE builds the `Update` node and a copy of SET's column
    numbers, DELETE the `Delete` node; RETURNING adds `outBCols`. No
    expression is cloned.
- Found, not fixed (on main 0b147ed9 and on m761 76118b8a alike): FOR
  UPDATE inside a FROM subquery (`select * from (select id from a where id
  < 3 for update) s`) kills the server, "index out of range" in `tryRow`
  (`lexdb_exec.lxl:5818` on main): the subquery's `Sel.exprs` has the
  lock's key columns appended (`SelLock`) and its row is read as the outer
  level's. Left out of the checks' statements.
- The scratch checks (`~/tpch-w/bind/e8/tools/xpatch.py` and `patch.py`,
  anchors asserted; each finds whether it patches main or a build with
  3c's arms, `NEW`, and patches each at the same places):
  - `xpatch.py`: `xTree` takes the `Sel`'s lists (`sx`, `so`) instead of
    the `Sel`, so a plan can be printed with none (a DML source). On a 3c
    build `xTree` prints a `Lock` as its input and a `Match` as before, so
    `XSEL` lines compare with main's; three new lines compare the rest:
    `XMR` at `planMatch`'s end (the `MatchDef` on the branch; on main the
    same texts gathered from `planMatch`'s locals as it resolves them:
    partitions, keys, directions, DEFINEs, MEASURES, the outputs' names and
    OIDs), `XLOCK` beside each `planSelect` `XSEL` (the `Lock`'s mode, wait
    and levels; on main from `Level.lock`), `XDML` per DML statement (the
    source's tree, the targets, RETURNING's names and OIDs; on main from
    `q.lp` or the INSERT ... SELECT's `Sel`, `targets` and `Ret.outs`).
  - `patch.py`: `lpValid` checks a `Match`'s definition (keys as many as
    their directions, PARTITION BY's columns within its input, no more
    MEASURES than columns) and a `Lock` (a mode, some levels, its columns
    its input's); `lpDml` checks each DML operator (its source by
    `lpValid`, a VALUES source of the lent form and no wider than its
    targets, RETURNING's columns against `Ret.outs` by `lpCmpOuts`, none
    without RETURNING) and prints `LPCHK OK dml-KIND`; main prints the same
    line after `lpValid` of its FROM part (or `lpValidT` of the INSERT ...
    SELECT's `Sel`, lending at its top).
  - Statements added for them (`~/tpch-w/bind/e8/extra.sql`, run by the
    battery's `run.sh` with the file as its third argument; the battery's
    tables a, b, c first): a set with ORDER BY as a FROM subquery, as an
    operand of another set, in IN, EXISTS and a correlated scalar subquery
    (hashed), in a CTE (used twice), a view and an INSERT ... SELECT, under
    a recursive CTE; three MATCH_RECOGNIZE (ALL ROWS PER MATCH with
    MATCH_NUMBER, CLASSIFIER, FIRST and COUNT; no PARTITION BY, two keys
    one descending, NEXT; over a FROM subquery); FOR UPDATE, FOR SHARE, FOR
    UPDATE OF over a join, FOR NO KEY UPDATE OF ... NOWAIT, FOR KEY SHARE
    SKIP LOCKED, OF a missing table, an outer join's nullable side, with an
    aggregate, in an IN subquery; INSERT VALUES (several rows, a column
    list, DEFAULT), INSERT ... SELECT with ORDER BY and RETURNING, of a
    UNION, ON CONFLICT DO NOTHING and DO UPDATE with RETURNING, a scalar
    subquery in VALUES; UPDATE with and without RETURNING, UPDATE ... FROM,
    a correlated SET; DELETE with RETURNING and USING; MERGE from a UNION,
    from a table with DELETE and RETURNING `merge_action()`, from VALUES
    with RETURNING *. 266 output lines, identical from main, the branch
    and both check builds.
- Gates: the suite on the snapshot of each commit (`~/tpch-w/bind/e8/
  suitec.sh`, tags c1-c4: 188, imports ok); the naming battery (1,505
  lines) identical to main from a build of each commit and from both
  check builds; `extra.sql` identical from main and each commit's build (each
  run with the statements added up to it) and both check builds; TPC-H
  all 22 checksums the baseline's (fields [0] and [8] against
  `~/tpch/out-baseline-1744ef99`) on every run (the check builds, main,
  the branch and their copies).
- The check chain (`~/tpch-w/bind/e8/ckchain.sh`; main 0b147ed9 as
  `lexdb-ck-m`, b3cc2219 as `lexdb-ck-b`, both patches applied, the suite
  from the snapshots `ck-m`, `ck-b` with slice 1's patched `run.py`):
  - TPC-H's 214 `LPCHK` lines identical line for line (105 `XSEL`, 95
    `OK`, slice 1's by-design `from-cols-end` and `sub-name`);
  - the battery's 638 server lines and `extra.sql`'s 200 identical when
    sorted (main prints `OK dml-insert-values` later in `insert`, after the
    subqueries are planned; the branch where it builds the `Insert`);
  - the suite's 227,267 and 226,231 lines, sorted: identical but for
    1,042 lines of `exec_autostats` and 6 of `exec_turns`, whose counts
    vary by run. Among them 15,624 DML checks (9,883 INSERT VALUES, 923
    INSERT ... SELECT, 3,238 UPDATE, 1,422 DELETE, 158 MERGE), 465 `XMR`,
    125 `XLOCK`; nothing flagged but slice 1's three by-design kinds
    (`from-cols-end`, `subty`, `sub-name`).
- Speed, one pass against main 0b147ed9 (`~/tpch-w/bind/e8/lexdb-m0b`,
  from `git archive`, byte-identical to slice 3b's `lexdb-b`) and m761
  (`~/tpch-w/bind/e6/lexdb-m761`); the branch at b3cc2219 (`lexdb-b`).
  Boost on, a browser busy on the machine through both passes (main's
  `pk_point20k` 668 and then 703 ms where slice 3b measured 657 for the
  same binary): read the ratios, not the levels.
  - TPC-H (`~/tpch-w/bind/e8/tpch1.sh`, SF1, 1 run): total 30,409
    against 29,574 ms (1.028), most of it after q7 (q8 1.646: 369 to 607
    ms; q11, q13, q17, q20 1.09-1.10). Against slice 3b's runs of the same
    main binary (`~/tpch-w/bind/e7/out-b`, `out-bc`): 1.041, 1.040. The
    one repeat, on byte-identical copies (`lexdb-bc` first, then
    `lexdb-m0bc`): 29,744 against 29,317 (1.015); past 1.5%: q1 1.022,
    q5 1.030, q7 1.035, q8 1.053, q13 1.043, q16 1.045, q17 1.053, q19
    1.055, q20 1.033, q18 1.020; none faster. Nothing this slice adds runs
    per row or per run of a SELECT (the `Lock` and `Match` only where the
    statement has them, `planSet`'s change per set operation, the DML
    nodes per DML statement), and TPC-H plans each query once, so read as
    layout (the binary is 4 KB longer) or the machine's noise; not
    verified further (no more runs, as asked). The branch's run kept for
    main's stored result: `~/tpch-w/bind/e8/out-bc` (and `out-b`).
  - `~/tpch-w/bind/e2/simple.sh` (pgbench `-M simple`, 4 clients, 10 s,
    one round, binaries alternating), tps:

    | | m761 | main 0b147ed9 | branch | branch / main | repeat (copies): branch / main |
    |---|---|---|---|---|---|
    | point selects | 49,312 | 46,238 | 45,278 | 0.979 | 46,849 / 46,568 = 1.006 |
    | updates | 9,443 | 9,187 | 9,293 | 1.012 | 9,366 / 9,352 = 1.002 |
    | 3-table join, ORDER BY, LIMIT | 21,110 | 19,245 | 19,466 | 1.012 | 19,857 / 19,546 = 1.016 |

    The updates (planned per run, now building an `Update` node and a copy
    of SET's columns) do not move.
  - `pk_point20k` (`~/tpch-w/bind/e6/pts.sh`, 5 runs per server, one
    round), server CPU ms, medians (range): m761 653 (646-658), main 668
    (662-713), branch 683 (674-690), +2.2%; the repeat on copies: branch
    709 (702-722), main 703 (700-706), +0.9%. A point select runs none of
    this slice's code but `planSelect`'s `lockMode` test.
  - Not run (as asked): more rounds, the 35 queries, OLTP and the loads,
    `qmulti.sh`, `pstat.sh`, a profile.
- Lines:

  | Module | main 0b147ed9 | after |
  |---|---|---|
  | `lexdb_exec` | 28087 | 28124 |
  | `lexdb_bind` | 1990 | 2025 |

**Where 2e slice 3c left off, and how to start slice 3d (`bindFrom`
into `lexdb_bind`).** Slice 3d moves the binder's FROM pass out of
`lexdb_exec` (slice 2's way in, step 3). Everything named is in
`lexdb_exec` unless the note says otherwise; search for the names, since
line numbers move.

- What is there after slice 3c:
  - Every statement kind builds an `LPlan`: SELECT (`Sel.lp`, with `Match`
    and `Lock` where it has them), set operations (`SetOp`, `Recursive`,
    their ORDER BY lent), INSERT, UPDATE, DELETE, MERGE (a local `lp`,
    dropped: read by nothing). What still lives only in the executor's
    structures: LIMIT's count and offset (parsed, `optClone`), the SET and
    VALUES expressions, ON CONFLICT (`Upsert`), MERGE's WHEN clauses
    (`MClause`), RETURNING's expressions (`Ret.exprs`; only its columns are
    in the plan), MATCH_RECOGNIZE's pattern and navigations (`MrPlan`).
  - Lending: a SELECT's `Project` list and `Sort` keys, and a set
    operation's `Sort` keys, are the `Sel`'s where no rewrite runs
    (`lpLentExprs`, `lpLentOrder`; `takeLp` restores them). An INSERT's
    VALUES is `Values(width, [], [])`: the statement's rows.
- `bindFrom` (about 300 lines) and what it needs that `lexdb_bind` may not
  import (`BIND_MAY_IMPORT` in `tests/lexdb/imports.py`: `lexdb_base`,
  `lexdb_sql`, `lexdb_catalog`, `lexdb_dialect`, `lexdb_time`,
  `lexdb_float`, `lexdb_ops`, `lexdb_lib`):
  - the store and catalog: `findTable`, `findSeq`, `seqRelation`,
    `viewQuery`, `readAcl` (a view's owner), `scCheck` (privileges),
    `relObj`; all take `st`/`txn`;
  - the planner, through `planSub` (three calls: a FROM subquery, a view,
    each expression subquery) and `takeLp`; `pullCommonOr` (a planner
    rewrite on the unresolved WHERE, kept in `bindFrom` for q19's sake:
    slice 2's note);
  - exec's types: `Query` (levels, `cols`, `subs`, `lp`), `Level`
    (`newLevel`, `addCol`), `Scope`, `SubPlan`, `FromBound`; `outType` and
    `outBCols` (a dialect's wire hint into a FROM subquery's row: a
    `BCol`'s `Ty` cannot carry it, the same gap `planMatch` hits);
    `unnest`'s columns, `hiddenName`.
  So the move is not a cut and paste. Two shapes, as slice 2's note gave
  them: exec fetches what the FROM names first (each item's `Table`, a
  view's parsed `Stmt` and owner, a sequence's relation, the working
  tables) and passes it in; or the binder returns what it lacks and is
  called again. Either way the subqueries recurse: a FROM subquery is
  bound and planned by one `planSub`, and the outer pass needs only its
  output columns. A first step that keeps results: split `planSub`'s
  binder half (`planSelect` up to the plan: `selectCols`, `srfCols`,
  `#values:` typing, `planMatch`'s outputs) from its planner half, so
  `bindFrom` can ask for a subquery's columns without planning it; then
  replace `Level`/`addCol` in the binder by the `Get`/`Sub` columns it
  already builds (`icols`).
- Found on the way, not fixed: FOR UPDATE in a FROM subquery kills the
  server (above; main and m761 alike). PostgreSQL accepts it.
- Traps (3b's still hold; and):
  - `lpRestore` restores under a lending `Sort` only where the `Project`
    lends too (`xs` non-empty): a new lending operator under a set's
    `Sort` would need its own case.
  - The DML operators take `q.lp` out of the `Query` after binding;
    nothing reads it then (`planFrom` has run). A reader added later must
    read the operator, not `q.lp`.
  - INSERT ... SELECT's `Sel` keeps running after `takeLp` has taken its
    plan: fine while the executor reads `Sel.exprs`/`Sel.order`, not the
    plan.
  - `MatchDef`'s DEFINE and MEASURES hold `#mrnav(k, arg)` marks whose `k`
    is `MrPlan.navs`' entry: the plan alone does not say a navigation's
    kind or offset.
  - The check tools now detect main or a 3c build (`NEW`: `LPlan.Insert(`
    in exec) and patch each at its own anchors (single lines, so either
    tool can go first). A new arm needs `xTree`, `xLockOf` (xpatch) and
    `lpValidT`/`lpDml` (patch) updated, and a line main can print from its
    own structures if the two are to compare.
- Gates (as slice 3c's): the suite per commit (`~/tpch-w/bind/e8/
  suitec.sh TAG REV`); the battery and `~/tpch-w/bind/e8/extra.sql`
  identical; TPC-H all 22; the check chain (`~/tpch-w/bind/e8/
  ckchain.sh`, the two tools in `~/tpch-w/bind/e8/tools`); `simple.sh` and
  `pts.sh` against main.

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

**Revised order (agreed with the owner, 2026-11-17, second revision,
after step 3a; supersedes the first, which put unnesting before step 4):**
2 (through 2e slice 3c) → 3a → **4** → 5 → 6 → 7, with the sorted row-id
scan and bushy joins slotted in when convenient.

- The first revision rested on TPC-H gaps measured at `94536d12` (q19
  14×, q20 12×). At `2b605b2b` the geometric mean is 1.86× PostgreSQL on
  one core (3.39× against four processes), q19 3.0×, q20 3.3×, and 6.1
  shows every TPC-H subquery query already has PostgreSQL's plan shape.
  Unnesting would make none of q4, q20, q21, q22 faster.
- So step 4 comes next. Its first slices take the measured items: q21's
  semi and anti levels under grouped batches (about 5 s of 7.2), then
  scan, filter and project (q1, q6, q22's `substring`). Step 5 follows
  for generality (6.1's 5a-5f). The sorted row-id scan (q4, q14, q19) and
  step 6's bushy joins (q21) need neither step 3 nor step 5.
  (6.2 found q21's 5 s to be column narrowing, a small fix in today's
  code, slice 4.1; the pipeline's first slice is then scan, filter,
  project and aggregate.)
- **Modules are a goal equal to speed.** `lexdb_exec` (28,224 lines at
  step 3a) still holds the planner and cost model, the plan structures
  mixed with run-time state, statements and sessions, and two
  evaluators. So:
  - step 4's operators and chunk machinery live in their own module, and
    each operator ported deletes the code it replaces from exec;
  - step 4 starts with a map of exec by target module (lines per secret,
    and what each depends on);
  - every slice reports exec's line count and which secret left it;
  - extraction slices with no behaviour change (the planner into
    `lexdb_plan`, with 2e slice 3d; statements into layer 7) alternate
    with the speed slices.
- Deferred until needed: 2e slice 4 (expressions bound against their
  operator's input; eval's name check dropped).
- Gates for refactor steps are light: the suite, the 22 checksums, and
  one TPC-H run of the branch against main's stored result
  (`~/tpch-w/int/out-main-<commit>`); point selects only where
  per-statement planning or the row path changes.

### 6.1 Step 3 and step 5: the plan, slice by slice

Written 2026-11-17 on `redesign/bind` at main 413100d1, before step 3.
The measurements are main's binary (`~/tpch-w/bind/e8/lexdb-bc`, b3cc2219,
the same code), SF1, boost on, one run each after a warm-up pass: read
them as shares, not levels. Scripts and outputs in `~/tpch-w/bind/s3`.

**What the measurements say first.** The revised order rests on "TPC-H's
worst gaps are plan shape". On main that no longer holds for the
subquery queries. Their figures (q19 14×, q20 12×) are from 94536d12;
at 2b605b2b (`~/tpch-w/int/out-main-2b605b2b`, against PostgreSQL at
one core) q19 is 3.0× and q20 3.3×. Today's planner already gives each
subquery query the plan shape PostgreSQL uses:

| query | lexdb / PG | the subquery's plan on main | PostgreSQL | where the rest of the time is |
|---|---:|---|---|---|
| q21 | 9.6 | semi and anti join, looked up per row (`semiLook`) | nested loop semi and anti join | executor: see below |
| q22 | 5.2 | anti join, index only, per row | nested loop anti join | the two customer scans' `substring(...) in (...)`, about 115 ms each of 458 |
| q4 | 2.9 | semi join, looked up per row | nested loop semi join | orders read whole (1.5M rows for 57k): PostgreSQL takes a bitmap scan of `orders_date` |
| q20 | 3.3 | scalar per row (8,508 runs) | subplan per row | reading 63,832 lineitem rows by index (lexdb-tpch-perf.md, q20 round 2: the reading, not the setup) |
| q2, q17 | 0.4, 0.1 | scalar per row | q17: subplan per row over a lineitem scan | ahead |
| q18 | 1.0 | IN over a grouped subquery: a key lookup per value | hash join | level |
| q16 | 2.2 | NOT IN, uncorrelated: a set, run once | hashed subplan | part's scan |

q21 in parts (`probe*.sql`): the joins through orders, counted, 1.07 s;
with the EXISTS and NOT EXISTS added, counted, 2.77 s; the query as
written (grouped by `s_name`) 6.65 s, against 1.60 s for the same grouping
without them. So about 5 s of q21's 7.2 s is the semi and anti levels
under the grouped batches. With `lexdb_batch = off` the counted query
takes 14.3 s. Why the grouped run is so much slower than the counted one
was not diagnosed. (6.2 diagnoses it: the cause is not the semi and anti
levels but the `*` in their subqueries, which turns column narrowing off
for every table.)

So unnesting, done as step 5 now, would make none of q4, q20, q21 or q22
faster. Their gaps are the executor (q21's grouped semi and anti path,
q22's `substring`, the scans), the access path (a bitmap or sorted
row-id scan for q4, q14 and q19's middle selectivities) and, for q21, a
hash of supplier joined to nation (step 6's bushy join). The owner should
weigh this against the revised order: the proposal at the end puts step
4 before step 5.

**1. What the physical plan is.**

- Today's `Sel` tree is the physical plan in all but name:
  - the `Sel` holds what sits above the joins (aggregate, HAVING,
    windows, the select list, DISTINCT, sort or top-N, LIMIT, FOR UPDATE,
    MATCH_RECOGNIZE) and a set operation's parts;
  - its `Query` holds the level chain: each table's path and join method,
    hash keys, and semi and anti levels;
  - each `SubPlan` holds a subquery's own `Sel` and how it runs.

  It holds no run-time state (`Run` and `Mats` do), the plan cache keeps
  it (`PlanCache.sels`), and EXPLAIN prints it. What it lacks is
  operators: `execSel` reads the `Sel`'s fields in one fixed order.
- Step 3's type is `lexdb_plan.PPlan`, a closed type with one arm per
  operator. Each arm holds its input, and `Levels` is today's chain
  whole:
  `Levels(n, subs)`, `Result(subs)`, `Func(name, ordinality, subs)`,
  `SetOp(op, all, rec, parts)`, then `MinMax`, `Agg`, `Having`,
  `Window`, `Project`, `Distinct`, `Sort(sorted)`, `Lock`,
  `Limit(stops)` and `Match`, in the order `execSel` applies them.
  - Each subquery is a `PSub{use, run, anti, plan}`, where `run` says
    how the executor runs it: `RUN_ONCE`, `RUN_PER_ROW` (step 4's Apply),
    `RUN_HASHED` (decorrelated, 9.9), `RUN_SEMI` (a hashed semi or anti
    level's rows) or `RUN_LOOKED` (not run: a looked-up level).
  - The `run` modes are step 5's vocabulary. A future rewrite moves a
    subquery from one mode to another.
- **The first cut is a view.** `lexdb_exec.physOf(&Sel)` builds the tree
  when asked. It holds no expressions, so:
  - nothing is cloned;
  - the plan cache still keeps only the `Sel`;
  - planning does no extra work (only EXPLAIN builds the tree).

  EXPLAIN prints by walking the tree, with the same text, and `execSel`
  does not change. This is slice 3a.
- **The tree then grows with step 4, not before.** When step 4 ports an
  operator:
  - that operator's arm takes its details, moved out of the `Sel`, not
    copied;
  - the planner stores the tree in the `Sel`, so it is cached with it;
  - the pipeline runs a plan only if it supports every arm (a walk of
    `PPlan`); otherwise `execSel` runs the `Sel`;
  - `Levels` splits into scan and join arms when the hash join is ported.

  A tree stored now would be a second copy of the `Sel` that nothing
  runs, so step 3 has no slice beyond 3a.
- Step 3 does not need the planner to move into `lexdb_plan` or to read
  the `LPlan` (2e slice 3d). Both stay deferred, as the revised order
  says.

**2. Where unnesting plugs in.**

- Today's unnesting is physical. It is decided after the subquery is
  planned, from its paths and costs, and it rewrites `Query` and
  `SubPlan`:
  - `hashSub` (9.9) keys a subquery whose outer values appear only in
    `inner = outer` conjuncts, with any other conditions kept as
    residuals;
  - `semiJoins` (9.104) makes a hashed semi or anti level and places it
    by `orderRows`;
  - `semiLook` makes a looked-up level;
  - the `noRefKeys` alternative plans a semi candidate again without
    outer values as keys, and its hash is taken if it costs less.
- Coverage by shape:

  | shape | today | missing |
  |---|---|---|
  | EXISTS / IN, correlated by equalities | hashed semi level, or looked up per row (one table, EXISTS only), chosen by cost | `semiLook` for IN, for two tables, for a range-keyed path |
  | NOT EXISTS | anti level (hashed or looked up) | as above |
  | NOT IN | uncorrelated: a set run once (9.8's NULL rules); correlated: per row | a null-aware anti join |
  | EXISTS / IN under OR, in the select list, in an outer join's ON | per row (or once, uncorrelated) | the mark join |
  | scalar aggregate, correlated | `hashSub` groups by the keys when no outer value is a path key; else per row (q2, q17, q20) | a cost choice between the two (the `noRefKeys` alternative is for semi candidates only); restricting the grouped side to the outer keys (magic set) |
  | correlated FROM subquery (LATERAL) | per row | join plus grouping |
  | IN over a grouped subquery (q18) | a lookup per value, or a hash | nothing for TPC-H |

- **Recommendation: extend unnesting in today's structures, not in the
  `LPlan`.**
  - The choices are cost choices on planned subqueries: hash or lookup,
    and where the level goes.
  - Rewriting the `LPlan` first needs the planner to read FROM, WHERE and
    subqueries from it: 2e slice 3d, an `Apply` arm, and `planSub`
    split. That is large work with no gain.
  - Step 4 throws none of it away: each kind of level maps to one
    operator (a semi, anti or mark `HashProbe` over a build, or a semi or
    anti index lookup), and `RUN_PER_ROW` is the Apply operator.
  - The `Apply` arm, and moving the rules to rewrite the `LPlan`, come
    once the planner reads the `LPlan`. That is a refactor, as step 5's
    last slice.
- None of these shapes makes q4, q20, q21 or q22 faster, as shown above.
  Step 5's value now is generality (the missing rows of the table) and
  deleting the per-row machinery once step 4 has an Apply operator. It
  is not TPC-H speed.

**3. The slices.**

Step 3:

| slice | what | gate |
|---|---|---|
| 3a | `PPlan`, `PSub` and `RUN_*` in `lexdb_plan`; `physOf` and `subsOf` in exec; EXPLAIN prints from the tree | the suite; the naming battery; EXPLAIN of the 22 queries byte-identical to main (`s3/explain.sh`); one TPC-H run |
| (3b) | none: the tree is stored and owns data from step 4's first operator on | |

Step 5, each slice in today's structures. Each gate is the suite, a test
of the shape (batches on and off, against an independent formulation),
the 22 checksums, and the shape's own A/B:

| slice | what |
|---|---|
| 5a | NOT IN, correlated or not, as a null-aware anti join: a hashed anti level that also tracks NULLs on both sides |
| 5b | the mark join: EXISTS and IN under OR and in the select list, as a hashed level that marks its rows instead of filtering them |
| 5c | `semiLook` widened: IN whose value is the inner key; EXISTS over two tables (the second hashed); a range-keyed path |
| 5d | a correlated scalar aggregate: per row or hashed, by cost (the `noRefKeys` alternative for scalars); a magic-set restriction where the outer side is small and has no index |
| 5e | a correlated FROM subquery with an aggregate: a join and a grouping |
| 5f | after step 4's Apply operator and the planner reading the `LPlan` (2e slice 3d): the `Apply` arm, the rules as `LPlan` rewrites, and the per-row machinery (`runSub`'s memo) deleted where unnested |

**Proposed order:** 3a, then step 4, with step 5 after it. Step 4's
first slices should take the measured TPC-H items:

- q21's semi and anti levels under the grouped batches (about 5 s);
- scan, filter and project (q1, q6, q21's lineitem scan, q22's
  `substring`).

Step 6's hash of a join (q21) and a sorted row-id scan (q4, q14, q19)
are the plan-side gains, and neither needs step 3 or step 5. If the owner
keeps 3 then 5, 5a to 5c are the most useful (correctness and
generality), but the TPC-H totals will not move.

**Step 3a as built.** There are two commits on `redesign/bind` from main
413100d1: af5da38f (this note) and 3d48e049 (the code). The suite passed
on the code commit's snapshot.

- `lexdb_plan` gained the following, with no new imports:
  - `PPlan`, the arms as in 1 above;
  - `PSub{use, run, anti, plan}`;
  - `RUN_ONCE`, `RUN_PER_ROW`, `RUN_HASHED`, `RUN_SEMI`, `RUN_LOOKED`;
  - `pSubs(&PPlan)`, which returns the leaf's subqueries;
  - `pLeaf(&PPlan)`.
- `lexdb_exec`:
  - `physOf(&Sel)` and `subsOf(&Query)` build the tree. `subsOf` uses
    the classification `subLines` made inline before: looked up, then
    semi, hashed, once, per row.
  - `selLines` is `physOf` followed by `planLines`. `planLines` walks the
    operators (`opLines`), then the subqueries (`subLines`, which now
    takes the `PSub`s and recurses with each one's plan).
  - `setLines` takes the parts' plans from the `SetOp` leaf.
  - DML's EXPLAIN calls `subLines(&q, &subsOf(&q), ...)`.
  - Only EXPLAIN builds the tree. Planning, the plan cache and
    `execSel` are unchanged.
- The order is kept for EXPLAIN:
  - `Match` prints its line before its input's;
  - `Func` and `Result` print the level lines first, as before;
  - `Window`, `Project` and `Lock` print nothing;
  - `Limit` prints only when it stops the scan;
  - a set is still printed by `setLines`: its `Sort` always as "order:
    sort", its `Limit` never.
- Lines:

  | Module | main 413100d1 | after |
  |---|---|---|
  | `lexdb_exec` | 28124 | 28224 |
  | `lexdb_bind` | 2025 | 2025 |
  | `lexdb_plan` | 154 | 229 |

- Gates:
  - the suite from a snapshot of 3d48e049
    (`~/tpch-w/bind/e7/suitec.sh s3a`): 188 passed, imports ok;
  - the naming battery: 1,505 lines, identical to main's
    (`~/tpch-w/bind/s3/nam-*.out`);
  - EXPLAIN of the 22 TPC-H queries (`s3/explain.sh`, 188 lines) is
    byte-identical to main's binary;
  - `s3/exx.sql`, 45 EXPLAINs over this slice's shapes, identical to
    main once the times are masked (309 lines). It covers every `RUN_*`
    mode, sets, a recursive CTE, functions, VALUES, MIN/MAX, DISTINCT
    ON, windows, grouping sets, LIMIT and OFFSET, FOR UPDATE and FOR
    SHARE, LATERAL, MATCH_RECOGNIZE, DML, and EXPLAIN ANALYZE;
  - TPC-H: all 22 checksums match the baseline's (fields [0] and [8]) on
    every run.
    - The first run against main's stored result
      (`~/tpch-w/int/out-main-2b605b2b`) was 30,756 against 29,744 ms
      (1.034), with q21 at 1.077.
    - The repeat used byte-identical copies, the branch first
      (`s3/lexdb-ac`) and then main's binary (`s3/lexdb-mc`, a copy of
      `e8/lexdb-bc`): 30,389 against 30,489 ms (0.997). q21 was 0.987,
      and nothing moved past 4% (q20 1.039, q3 1.023).
    - So the first run's gap was the machine, not the change. That fits:
      the code runs only under EXPLAIN. The outputs are in `s3/out-a`,
      `out-ac` and `out-mc`.
  - Not run, as planning per statement does not change: `simple.sh`
    and `pts.sh`.

**Where 3a left off, and how to start step 4 (or step 5).**

- The tree is a view, and nothing runs from it. Step 4's first slice
  does three things:
  - stores the tree in the `Sel`: built at the end of `planSelect` and
    `planSet`, cached with the `Sel`. `pts.sh` and `simple.sh` measure
    this, because it is per statement on the simple protocol;
  - adds the check that the pipeline supports a plan (a walk of
    `PPlan`, its subqueries included);
  - moves the first ported operator's details into its arm, out of the
    `Sel`. The `Sel` field goes when its last reader does.

  Splitting `Levels` into scan and join arms is part of porting the
  hash join.
- For step 5 slices, in today's structures:
  - a new way to run a subquery gets a `RUN_*` value, its line in
    `subLines`, and its case in `subsOf`;
  - a new kind of level (a mark join) gets its line in `explainLines`.
- Traps:
  - `pSubs` is exhaustive over the arms, and `pLeaf` ends in `else`. A
    new unary arm needs a case in both.
  - `Agg` and `MinMax` can both be present (EXPLAIN printed both lines
    whenever both conditions held). `Limit` is also present for TOP
    PERCENT and WITH TIES (`topMode`, `limit` -1).
  - Lexell: the tree is built with `let` chains (`p1` ... `p9`). Each
    arm moves its input in, and nothing is reassigned.

### 6.2 Step 4: the map, q21, and the pipeline module

Written 2026-11-17 on `redesign/bind` at main 386438df (slice 4.0:
analysis and design, no code change). Scripts and outputs are in
`~/tpch-w/bind/s4`:

- `execmap.py` (with `decls.py`) makes the map; `run.sh` writes `map.txt`,
  `slices.txt` and `groups.tsv`;
- `probe.sh`, `prof.sh` and `callers.py` are the q21 probes and profiles.

Measurements are the native build of 386438df (`s4/lexdb-m`, with
`LXL_NATIVE_MAP`), SF1, boost on, the server on CPUs 0-3, run twice. The
second run is quoted.

#### 6.2.1 The map of `lexdb_exec`

**How it is made.**

- Each top-level declaration runs from its comments to the next one's.
- It is put in a group by line ranges (the file is mostly in sections),
  then by name overrides. Both tables are in `execmap.py`.
- A reference is an identifier in a declaration that names another
  declaration of exec. A method counts only as `.name(`, and only when its
  receiver's type is named in the declaration.
- So the line counts are good to a few percent per group, and the
  references are a crude call graph: they count edges, not calls.

**Summary.** 28,224 lines: 54 of imports, and 28,170 in 1,409
declarations.

| group | lines | main declarations | goes to |
|---|---:|---|---|
| access (layer 2) | 561 | `pathScans`, column-leaf ranges (`cRangesOf`, `bNarrow`), `lazyOf`, the row-layout constants, `idxVal`, `inIndex` | `lexdb_access` (step 1 left these) |
| binder | 1,653 | `bindFrom` 312, MATCH_RECOGNIZE's rewrite 335, `srfCols` 111, `collectAggs`, `setSubst`, `exprScale`, `Scope`, `bindSel` | `lexdb_bind` |
| planner, cost, statistics | 5,799 | `planSelect` 475, `planFrom` 290, `choosePath` 176, `semiLevel` 171, `Query.costOrder` 168, `planMatch` 187; statistics 1,003 (`analyzeTable` 216, samples, `loadEst`, autoanalyze 327) | `lexdb_plan`; statistics `lexdb_stats` |
| plan structures and EXPLAIN | 705 | `Query`, `Level`, `Sel`, `SubPlan`, `JPlan`/`JLevel`/`OutPlan`, `physOf`, `subsOf`, `explainLines`, `opLines` | `lexdb_plan` |
| batch engine | 3,717 | `batchGroupsIn` 556, `sortBatches` 302, `bEval` 257, `bCompileD` 245, `bJoinPlan` 214, `batchLevel` 144, `bProbe`, `bJoinTail`, `bRange`, `bLookup`, `eachOut` | `lexdb_pipe` |
| row evaluator | 1,205 | `eval` 169, `bxEval` 67, `callAt`, `entryAt`, `Env`, `CEnv` (485 in all); the catalog and session functions `sysCall` 219, `callCat` 153, `sessCall`, `seqCall`, `advCall`, `hasPrivFn` (720) | the BX evaluator to `lexdb_pipe`; the functions to layer 7, behind a hook |
| executor proper | 4,308 | `execSelTo` 352, `runLevel` 331, windows 533, MATCH_RECOGNIZE 395, `execSrf` 157, `materialize`, `runSub`/`fillCur`, row aggregates 282, row sort and `sk*` 463, `Run` 188 | `lexdb_pipe` as operators; the row engine is deleted (decision 1) |
| statements and sessions (layer 7) | 9,020 | DDL 2,272 (`alterTable` 362, `rewrite` 160), DML 1,767 (`merge` 254, `rangePlan`, `updateB`, `deleteB`, `insert`), COPY 935, sequences 772, foreign keys 771, privileges and views 841, `Session.runStmt` 405, SET 196, WAITFOR 210 | layer-7 modules |
| catalog relations and lookups | 537 | `bindCatalog`, `relOidOf`, `catRows`, `findTable`, `createKey`, `bootstrap`, catalog versions | `lexdb_catalog` (lookups), layer 7 (catalog relations) |
| protocol glue | 359 | `describe`, `guessParams`, `paramTypes`, `Session.runRows`/`runIn`/`copyIn`, `Session.exec` | layer 7/8 |
| small helpers | 104 | `copyRow`, `copyStrs`, `iv`, `num`, `span`, `toHex` | `lexdb_base` or their users |
| one-line forwards | 202 | 136 aliases and forwards to `lexdb_catalog`, `lexdb_plan`, `lexdb_access`, `lexdb_ops` | deleted: callers call the module |

**Edges that block a move.** The full matrix is in `map.txt`. The ones
that decide the order:

- **`Query` carries 1,402 lines of methods, and 1,354 of them are the
  planner's** (`costOrder`, `nBest`, `wayCands`, `implied`, the shares).
  Lexell declares methods only in the type's module (SPEC 5.3). So the
  plan structures cannot leave exec without the planner, unless those
  methods first become functions. `Session` likewise carries 1,145 lines
  of methods.
- **The evaluator is named everywhere, and it reaches up:**
  - it is named from statements 68 times, from the executor 67, from the
    batch engine 26 and from the planner 15 (`Env`, `eval`, `seqEnv`,
    `CEnv`, `bxEval`);
  - through `callAt` and `entryAt` it calls the catalog and session
    functions (`sysCall`, `callCat`, `sessCall`, `seqCall`, `advCall`),
    which read the `Session`, the catalog relations and sequences.
  - So the scalar evaluator can sit below exec only once those calls go
    through a hook in its context.
- **The batch engine names:**
  - the plan structures 76 times (`Query` 23, `JPlan`, `Sel`, `Level`);
  - the run state 60 (`Mats` 13, `Run` 13, `Run.tickN`);
  - access 38 (forwards only);
  - the evaluator 26.

  It reads plans through `Query`, so its drivers are ported, not moved.
  Its kernels (`bEval`, `bAccum`, the probe and gather loops, `skSort`)
  move.
- **The planner names the binder's functions 80 times** (`Scope`,
  `hasAgg`, `immutable`, `boundType`, `exprOid`, `keyType`). They are
  still in exec: the binder leftovers go to `lexdb_bind` before the
  planner can leave.
- **Statements name the executor 84 times** (`Limits` 21, `prepare`,
  `runQuery`, `SubRes`), because DML runs queries. They name the access
  helpers 71 times and the catalog lookups 54. Layer 7 sits above exec,
  so these edges are allowed. What blocks it is the reverse: 116
  references from what stays into layer 7 (catalog and session functions
  22, catalog relations 19, `execSelTo` 13 for `Res` and the COPY
  constants).

**Extraction order, smallest risk first.** Each is a refactor slice with
the light gates of the revised order: the suite, the 22 checksums, and
one TPC-H run against main's stored result. `pts.sh` and `simple.sh` are
added where per-statement planning moves.

| # | slice | lines leaving exec | to | blockers | risk |
|---|---|---:|---|---|---|
| E0 | forwards and helpers | ~300 | callers call `lexdb_catalog`/`access`/`plan`/`ops`; helpers to `lexdb_base` | none | none |
| E1 | **the BX evaluator and the run state** (`bxEval`, `callRef`, `callAt`, `entryAt`, `CEnv` 176; `Run`, `Limits`, `Counts`, budget and ticks 195) | ~370 | `lexdb_pipe` (slice P1) | the catalog and session functions (720 lines) stay in exec behind a hook in the pipe's context; `SubRes` of a `#sub` arrives as a value | medium |
| E2 | statistics: ANALYZE, samples, estimates, autoanalyze | ~1,000 | `lexdb_stats` (layer 5) | 16 references out: temporary tables' names, `findTable`, three index helpers, the `Limits` of autoanalyze's statement, `nextVersion`. In: DML's change counts (`noteChg`, `chgEnd`), the planner's `loadEst` | low |
| E3 | binder leftovers (`bindFrom`, MATCH's rewrite, `srfCols`, types, scope, aggregates' slots) | ~1,650 | `lexdb_bind` (with 2e slice 3d) | 73 references out: `bindSel`/`bindQuery` take a `Query` (they stay with the planner); `scCheck` and sequence names need the catalog snapshot; `colIndex` | medium |
| E4 | layer 7 top down. First the dispatcher, sessions, SET, notices and protocol glue (~1,750); then COPY (935); then DML (1,767); then DDL with foreign keys, sequences, privileges and views (~4,900, which name each other 76, 65 and 108 times) | ~9,400 | layer-7 modules above exec | `Session`'s methods move with it. What stays below must stop reading the session first: catalog and session functions, catalog relations, DDL's `notice`. Their reads go through the evaluation context (4.7's `ExecTxn`). | medium to high |
| E5 | planner and plan structures | ~6,500 | `lexdb_plan` | after E3: `Query`'s methods (move together, or become functions first, a mechanical slice); constant evaluation (`eval`, `evalInt`: `lexdb_ops` folding); `Limits`/`SubRes`; batch-ability checks (`ixCovers`, `colKind`: to `lexdb_rows`/`access`); temporary and catalog lookups | high (per-statement planning, the OLTP gate) |

- **Step 4's operators need only E1 first.** E0 is free and can ride
  along.
- Step 4 does not need the planner moved:
  - the pipe reads `PPlan` arms, and the planner fills them in exec
    (6.1's handover);
  - E5 stays deferred with 2e slice 3d;
  - E2 to E4 alternate with the speed slices, as the revised order says.
- The `sk*` sort keys (361 lines) move with slice P1's Sort, and exec's
  row sort then calls them.

#### 6.2.2 q21: the cause is column narrowing

**Measured** (`s4/ea-m.txt`, `star-m2.txt`, `star-f.txt`; ms, second
run):

| query | main 386438df | `select 1` for `select *` | scratch fix (both changes below) |
|---|---:|---:|---:|
| q21 as written (grouped) | 5,910 | 1,986 | 1,491 |
| q21's joins + EXISTS + NOT EXISTS, counted | 2,772 | | 1,312 |
| q21's joins, grouped by `s_name`, no subqueries | 1,530 | | 1,169 |
| q21's joins, counted | 1,032 | | 1,023 |
| q4 | 442 | 293 | 282 |
| q22 | 355 | 345 | 346 |

- All results were identical across the three builds and the rewrites.
- PostgreSQL at one core (`~/tpch/out-baseline-1744ef99`) takes 687 ms
  for q21 and 180 ms for q4. So q21 goes from 8.6× to 2.2×, and q4 from
  2.5× to 1.6×.

**The questions 6.1 left:**

- **Do batches fall back to rows?** No. `runLevel` and `tryRow` are not in
  the profile. EXPLAIN ANALYZE shows one pass of 5,861 batches. The
  units retry in `batchGroups` is for one table only (`dec = !jn`).
- **Do the semi and anti lookups repeat per group?** No. The counted and
  grouped runs show the same counts: semi 75,871 lookups and 378,274 rows
  read; anti 73,089 and 375,492.
- **What does the memo do?** Nothing here. The levels run in `bRange`,
  whose `rangeMany` reads a repeated key once. `runSub`'s per-row memo is
  not involved. The batch path reads whole ranges (378k rows, against the
  row path's 92k, which stops at the first passing row). That costs
  about 0.27 s after the fix.

**The cause, with evidence.** Two things compound:

1. **Every table is read whole.**
   - TPC-H writes `exists (select * from lineitem ...)`.
   - `stmtNames` (exec:13975) sets `star` for a `*` anywhere in the
     statement, subqueries included. `narrow` (exec:14006) then returns
     without narrowing any level.
   - So lineitem l1 decodes all 16 columns for 6M rows, its four numerics
     as `Val`s. The counted profile is 58% `decodeCols` and 20%
     `Decimal.fromUnits` (`s4/pcnt`).
   - That is all of the counted query's extra time:
     - with `select 1` it drops to the joins' cost plus the levels;
     - the same `*` costs q4 a third of its time (orders read whole).
2. **With GROUP BY, the joins carry every column read.**
   - `bJoinPlan` finishes the plan with every column the statement reads
     (`jpFinish(.., &all)`). `batchGroupsIn` narrows it to the
     aggregates' columns only when there is no GROUP BY (`if jn &&
     len(keys) == 0`, exec:24609).
   - So the grouped query gathers every needed column through every join
     level, and with (1) that is every column: 3.79M rows at the first
     level and at the supplier probe, dates, text and numerics as `Val`s.
   - The grouped profile (`s4/pgrp`) is 45% `bGather`, half of it `dup`
     (copying `Val`s). The counted one (`s4/pcnt`) is 2.6%.
   - By caller: `bGather < bJoinTail < bProbe` is 25% of samples, and the
     first level's gather in `bJoinAll` 12%.
   - Without the subqueries there is no `*`, so the same gather moves only
     the needed columns: that is the 1.53 s against 1.03 s.

**The fix.**

- **Slice 4.1, in today's code, worth doing first (about 25 lines, both
  measured above in a scratch build that was not committed):**
  - `stmtNames` ignores the `*` of an EXISTS subquery that is not a set
    operation. PostgreSQL ignores EXISTS's select list.
  - `batchGroupsIn` calls `jpFinish` with GROUP BY too: the keys', the
    aggregates' and filters' columns, and the names its outputs, HAVING
    and ORDER BY read (the set it already keeps for a group's first row).
  - Gates: the suite (not yet run on the fix), the 22 checksums, one TPC-H
    run.
  - Expected: q21 about 5.9 to 1.5 s and q4 440 to 280 ms, the TPC-H
    total about 4.5 s lower.
- **In the pipeline, the structure takes it:**
  - Required columns are a plan property. A top-down pass over `PPlan`
    gives each operator the columns its consumer reads, per table
    instance (alias and slot), not per bare name, so `l2.*` cannot widen
    `l1`. The binder never binds an EXISTS's select list.
  - Each operator's output chunk holds only those columns. A filter
    narrows the selection vector and copies nothing. A join gathers only
    its output columns, once.
  - This belongs to slice P2's join operators. The pass itself is in
    `lexdb_plan`.
- **What is left of q21 after the fix** (1.49 s, `s4/pq21f`):
  - the scan and decode of l1, 28%;
  - `l_receiptdate > l_commitdate` compared as `Val`s, 19%: dates are
    `BK_VAL` in batches, through `lexdb_ops.compare`;
  - the semi and anti ranges, 18%;
  - the orders lookups, 14%;
  - gathers, 13%.

  The pipe's Chunk takes dates as integer vectors (the compare becomes a
  kernel). Step 6's bushy join (supplier with nation hashed first) cuts
  the 3.79M-row probe to 157k.

#### 6.2.3 The pipeline module

**Name: `lexdb_pipe`.**

- Its secret is how a physical plan runs: push pipelines of operators
  over chunks.
- The alternatives say less: `lexdb_run` is not specific, and `lexdb_vexec`
  names an implementation choice.
- At step 4's end the row engine is deleted (decision 1), so `lexdb_pipe`
  is layer 6. What is left of `lexdb_exec` is layer 7, and is renamed
  then (for example to `lexdb_stmt`).

**Place and interface.**

- It sits below `lexdb_exec` and above `lexdb_plan`, `lexdb_bind`,
  `lexdb_access` and `lexdb_rows`. Exec calls it; it never calls exec.

  ```
  compile(p: &PPlan, cols: &[]ColDef): Option[Prog]
      // None: an arm or an expression it does not run. Called once at
      // plan time (end of planSelect/planSet); the Prog is kept in the
      // Sel with the PPlan, so the plan cache keeps it.
  run(st, txn, prog: &Prog, cx: &Ctx, bud: mut &Budget, sink: fn(&Chunk): Result[bool, DbErr]): Result[Unit, DbErr]
      // the sink returns false to stop (LIMIT, a client's cancel)
  Ctx    { params; subs (RUN_ONCE results, as values); zone; now;
           callOut: fn(name, args, ...) for catalog and session functions;
           nextval hook }     // 4.7's ExecTxn, the part a run reads
  Budget { maxHeld; held; deadline tick; counts per operator }
           // from Run; EXPLAIN ANALYZE prints the counts
  ```

- **To the plan:**
  - the pipe reads `lexdb_plan.PPlan` arms only, never `Query`, `Level`
    or `Sel`;
  - an arm takes its operator's details when ported (6.1's handover): a
    `Scan` arm holds the table (`lexdb_catalog.Table`), the `Path`, the
    columns needed and its conditions as `BX`;
  - `Agg` holds keys and calls;
  - `Sort` holds keys;
  - `Limit` holds its count and offset.
- **To access:** today's batched calls, unchanged: `fillLevel`/`fillBatch`
  (scan), `fetchMany` (by primary key), `rangeMany` (a range per key),
  `Probes`, `idxDecOf` (index-only reads). Nothing in the pipe sees a key
  byte.
- **Expressions:**
  - `BX` is compiled to today's `BNode` kernels. The generic step is the
    scalar BX evaluator, which moves into the pipe (E1), so there is one
    evaluator, scalar and vector, as 4.4.1 says;
  - exec's row path calls the pipe's scalar evaluator;
  - columns stay addressed by the query's slots (the `q.cols` positions,
    as `Batch` is today, an absent column holding no vector), so 2e
    slice 4 is not needed first.

**Chunk.**

- `Chunk { b: lexdb_rows.Batch; sel: []int; all: bool }`: today's `Batch`
  plus a selection vector (`all`: every row 0..n).
- Filters narrow `sel`, and Project and the sinks read through it.
- A join emits pairs of rows (outer, inner) and gathers only the columns
  above it needs.
- Kinds:
  - `BK_INT`, `BK_BOOL` and `BK_DEC`, as now;
  - dates and timestamps join `BK_INT` (days and microseconds; q21's
    compare above);
  - `BK_VAL` for the rest.
- A chunk keeps its capacity across uses (`lexdb_rows.reuse`).

**Choosing it, and deleting the old code.**

- `compile` is the support check: it walks the `PPlan` with its `PSub`s
  and every expression.
- `execSel` runs the `Prog` when there is one and `lexdb_batch` is on,
  else today's path. Nothing gives way mid-query, so each of today's
  give-way reasons gets an answer inside the operator:

  | today's give-way | in the pipe |
  |---|---|
  | numeric units overflow (`batchGroups` runs again with values) | the kernel's chunk falls back to the generic step (4.4.1) |
  | a value its column's batch cannot hold | that chunk's column as `BK_VAL` |
  | a range's rows past the room (`bRange`'s `room0`) | ranges read in bounded pieces per chunk of keys |
  | an expression error (the row path raises it) | the evaluator raises it, at the lowest selected row of the first failing step (4.4.1) |
  | memory | `max_statement_mem`'s error, as the row path; spilling later |

- A driver of today's batch engine is deleted in the slice whose
  `compile` accepts every plan the driver accepted. Its accept conditions
  are the guards at its top, for example the first 30 lines of
  `batchGroupsIn`.
- The proof is the "three ways" tests (`lexdb_batch` on and off), the
  checksums, and the drivers' test counters (`groupRuns`,
  `rangeJoinBatches`), which move to the pipe's counters.
- The row engine stays as the path for plans the pipe does not compile,
  until it compiles all of them.

**Import rules** (`tests/lexdb/imports.py`, next to `BIND` and `ACCESS`):

- `lexdb_pipe` joins `CORE`.
- It may import `lexdb_base`, `lexdb_sql`, `lexdb_time`, `lexdb_float`,
  `lexdb_rows`, `lexdb_vec`, `lexdb_like`, `lexdb_sqlcoll`, `lexdb_ops`,
  `lexdb_lib`, `lexdb_catalog`, `lexdb_bind`, `lexdb_plan`,
  `lexdb_access` and `lexdb_store`, plus lexell's own libraries.
- From `lexdb_store` it may use the `Store` and `Txn` handles only (a
  check like the `Txn.sql` one), and it never reads `txn.sql.`: session
  state arrives in `Ctx`.
- No module it may import, and none below access, imports it. Only
  `lexdb_exec` (and later layer 7) do.
- No dialect and no protocol module is imported.

**The first three code slices** (after 4.1). The lines are estimates
from the map. Each slice's gate is step 4's: the suite, the checksums,
an A/B against main's binary per operator, and `pts.sh` and `simple.sh`,
because the `Prog` is made per statement.

| slice | operators | queries it runs (expected, not verified) | lines leaving exec |
|---|---|---|---:|
| P1 | the module, `Chunk`, the BX evaluator and `BNode` compile and eval (E1, `batch.core` 1,064, `bAccum` 97); `Scan` (full, primary key or index range, index-only), `Filter`, `Project`, `Agg` and `HashAgg` over one table (numerics as units), `Sort` of the output rows (`sk*` keys, 361), `Limit`; RUN_ONCE subqueries as values | q1, q6, q22's scalar subquery; the 35-query suite's one-table scans and aggregates | ~2,000: ~1,700 moved, ~300 deleted (`batchGroupsIn`'s one-table branch and the units retry, `eachOut`'s and `outPlan`'s one-table output) |
| P2 | `HashBuild`; `HashProbe` (inner, left, semi, anti); `IndexLookup` (by whole primary key: `bLookup`; a range per key: `bRange`); `Levels` splits into scan and join arms; required columns per operator (6.2.2) | q3, q4, q5, q7, q8, q9, q10, q12, q14, q19, q21, and q22's inner query; q11, q15, q18 if their RUN_ONCE parts compile | ~1,700: `batch.join`, `batch.lookup`, `batch.plan`, `batch.level` (1,227) and the join branches of `batchGroupsIn`, `eachOut` and `outPlan` |
| P3 | `Sort`, `TopN` and `Distinct` over chunks with the memory budget (`sortBatches`, `SortSet`, the heap) | the suite's ORDER BY and DISTINCT over many rows; nothing new in TPC-H (its sorts are over grouped output, P1's) | ~550: `batch.sort` 440, what is left of `batch.out` |

After P3 the batch engine (3,717 lines) is out of exec, and exec is about
24,000 lines. Next come windows (`winBatch`, `winPartition`), Apply for
RUN_PER_ROW (q2, q17, q20, before step 5's 5f), `Fetch` for point
selects (the OLTP gate), and the row engine's deletion.

#### 6.2.4 4.1 and E0 as built

Built 2026-11-17 on `redesign/bind` from main 5f4ce91e. Scripts and
outputs are in `~/tpch-w/bind/s41`.

**Slice 4.1** (172df168), from the scratch fix of 6.2.2, reviewed:

- `stmtNames`: the `*` of an EXISTS subquery reads nothing, unless the
  rows it counts depend on their values. Those keep `*` reading every
  column:
  - a set operation (its members' `use` is not EXISTS anyway);
  - GROUP BY or grouping sets: `group by 1, 2 having count(*) > 1` names
    `*`'s columns by position, which no name list sees;
  - DISTINCT and DISTINCT ON: `select distinct * ... offset 1` counts
    distinct rows.

  The other `*`s are unchanged: the outer select list's, an IN
  subquery's, a view's or FROM subquery's (`SUB_FROM`), NATURAL's.
  `count(*)` was never a `*` item.
- `stmtNames` also reads DISTINCT ON's keys. They were missing: `select
  distinct on (b) k from t` read no `b` and gave one row, with batches
  and without (a bug on main, found in the review).
- `batchGroupsIn`: a grouped join gathers the keys', the aggregates' and
  `afterCols` (the names a group's first row keeps: outputs, HAVING, ORDER
  BY, which holds DISTINCT ON's keys). `afterCols` is the list the first
  row already used, so the first row cannot read a column the join did
  not gather. Windows and grouping sets do not take this path.
- Where a dropped column would have shown: in batches a key or output on
  a column not decoded is an index out of range (`bEval`), not a NULL. A
  build without the GROUP BY and DISTINCT exceptions crashed on the GROUP
  BY shape; one without `afterCols` in the gather gave no rows for the
  HAVING shape. The test catches both.
- Test `exec_narrow.lxl`: 24 shapes (q21's and q4's, NOT EXISTS, IN
  (select *), the outer `*`, a view, LATERAL, `count(*)` in EXISTS, the
  three exceptions, grouped joins whose outputs, HAVING and ORDER BY read
  non-key columns, an outer join's ON filter, a window, DISTINCT ON,
  EXISTS with a join, ORDER BY with OFFSET, a window, uncorrelated, nested
  under IN). Each runs with batches off and on, and both must give
  PostgreSQL 18's rows. 13 of them run grouped over batches, the five
  grouped joins (1, 13, 14, 17, 19) among them.

**E0** (38a9568d, 74c6ff09):

- 147 one-line forwards deleted (functions and constants that only call
  or name another module's): exec, the protocol and dialect modules, 112
  tests and the two generators now call the owner. 12 of them were used
  outside exec (`text` by about 110 tests, `isNull`, `coerce`, the catalog
  and syscat constants).
- Exec's type aliases are all private now (`OutCol` and `TabType` were
  re-exported: the protocol modules name `lexdb_bind.OutCol` and
  `lexdb_catalog.TabType`). A private alias stays: it is every module's
  import idiom, as `e()` is: 48 remain.
- Adapters that add exec's context stay: `typing()` (`exprOid`,
  `arrayConcat`), `parseExpr` (`decTable`, `allTables`), a `Table`'s `Rel`
  (`keyOf`, `rowOf`, `fetch`, `fillLevel`, `placesMissing`,
  `placesNeeded`, `idxDecOf`), and `tempKey`, `sameExpr`, `isDialectFn`,
  `tabTypeId`.
- Helpers: `copyRow`, `copyStrs`, `copyInts`, `copyBools` became
  `collections.copyOf`; `nullRow(n)` became `array(n, Val.Null)`; `bv`,
  `tv`, `iv` were unused; `num` and `hasStr` went to `lexdb_base`, with
  `lexdb_catalog`'s copies. Staying with their users: `toHex`, `intsOf`,
  `intsText` (statistics, E2), `fmax`, `fmin` (the planner, E5; not std's
  `max`, which differs on NaN), `span` (sequences), `quoted`, `append1`,
  `copyRows`.
- Import edges 185 to 198, all allowed by `imports.py` (unchanged): the
  protocol and dialect modules (`lexdb_wire`, `lexdb_tds`, `lexdb_tns`,
  `lexdb_tsql`, `lexdb_plsql`) import `lexdb_ops` and `lexdb_bind`, and
  three of them `lexdb_catalog`, where they went through exec before.
- No secret left exec in E0: what went were other modules' secrets that
  exec re-exported (the row format's place kinds, the cost constants, the
  catalog's encodings, value display and coercion). Exec stops being the
  door to them, which is what the later moves need: code that leaves
  exec names the owner already.

**Line counts:**

| | main 5f4ce91e | 4.1 | E0 |
|---|---:|---:|---:|
| `lexdb_exec` | 28,224 | 28,245 | 27,989 |
| `lexdb_base` | 108 | 108 | 119 |
| `lexdb_catalog` | 1,358 | 1,358 | 1,351 |
| `lexdb_rows` | 1,642 | 1,642 | 1,647 (LONG's comment) |

The protocol and dialect modules gained 2 or 3 import lines each.

**Gates:**

- Suite, from a snapshot of each commit: 189 passed (188 and
  `exec_narrow`), imports ok (185 edges, then 198).
- Naming battery (`bench/naming`): identical to main's build for both.
- TPC-H, SF1, one run each, the 22 checksums as the baseline's (1744ef99),
  against main's stored result (`out-main-d32f5fb8`, the same code):

  | query | main | 4.1 | E0 |
  |---|---:|---:|---:|
  | q21 | 8,266 | 1,964 | 1,957 |
  | q4 | 581 | 359 | 358 |
  | q13 | 1,328 | 1,118 | 1,125 |
  | total | 30,389 | 23,026 | 23,110 |

  - q21 is 76% down and q4 38%, as 6.2.2 expected. q13 (a grouped left
    join whose ON reads `o_comment`) is 16% down, probably from the
    gather (not profiled). No query was more than 3% slower.
  - main's stored run is slower than 6.2.2's second runs (q21 8,266
    against 5,910 ms, q4 581 against 442): one pass per query (RUNS 1),
    as the 4.1 and E0 runs are, against 6.2.2's second of two.
  - E0 against 4.1's run: the total +0.4%. q1 (+3.6%) and q20 (+4.0%)
    were repeated on copies of the binaries (`s41/rep`, 3 runs, medians):
    q20 383 ms main, 386 E0, level. q1 2,330 and 2,363 main, 2,311 4.1,
    2,405 and 2,398 E0: 2 to 4% slower, reproduced.
  - q1's perf profiles (`rep/self-p1.txt`, `rep/self-e0.txt`) have the
    same functions in the same shares, and E0's has 1.4% fewer samples.
    E0 changes nothing on q1's path but who is called by name (the same
    functions, directly). Not explained; code placement is the likely
    cause. Not resolved.
- `simple.sh` and `pts.sh` were not run: E0 does not touch the
  per-statement path, beyond names.

#### 6.2.5 E1 as built

Built 2026-11-17 on `redesign/bind` from main fde5d3aa. Scripts and
outputs are in `~/tpch-w/bind/e1`.

**The hook** (fc35f5ea, in exec first, then moved as it was):

- The pipe's context is `lexdb_pipe.Ctx { now; zone; params; up: Up }`,
  exec's `CEnv` renamed. Its `seq` went: nothing read it.
- `Up` is a value record of two functions, exec's to supply (`execUp`):
  - `entry: EntryFn`, `fn(&str, int): Option[lexdb_lib.LibFn]`: a
    function's entry where it is not lexdb_lib's. Exec's is `catEntry`:
    `format_type` and `pg_size_pretty`, which read PostgreSQL's dialect
    (`lexdb_pgcat`, `lexdb_pg`).
  - `dialect: DialectFn`: a T-SQL or Oracle function's call
    (`FnRef.dialect`). Exec's is `callDialectFn` (`lexdb_tsqlfn`,
    `lexdb_orafn`).
- `callAt` and `entryAt` take the entry hook as an argument
  (`entryAt(name, n, up)`: `up`'s entry, else `lexdb_lib.entryOf`). The
  row evaluator (`eval`), `call` and `fnRefOf` stay in exec and pass
  `catEntry`; `bxEval` passes `ctx.up.entry`.
- 6.2.3's sketch had a `callOut` for the catalog and session functions
  and a nextval hook. They are not needed yet: those functions (and
  sequences, `sysCall`, `callCat`, `sessCall`, `advCall`) do not bind
  (`fnRefOf`'s `FN_NONE`), so only `eval` calls them, in exec. The hook
  grows when the pipe compiles one of them.

**What moved** (a03b7de1, 96abac48), unchanged but for names:

- The evaluator: `Ctx`, `Up`, `EntryFn`, `DialectFn`, `bxEval`,
  `callRef`, `callAt`, `entryAt`, `unName`, `looksArray`.
- The budget: `Budget` (a value record: `held`, `aside`, `maxHeld`,
  `deadline`, `ticks`, `turnEnd`, out of `Run`) with `hold`, `room`,
  `tick`, `tickN`, `checkTime`; `newBudget`, `memErr`, `TURN_NS`,
  `rowBytes`, `rowsBytes`.
- `Counts` (EXPLAIN ANALYZE's per table), with `noCounts`.
- Exec reaches them as `lexdb_pipe.*`; `Run` holds `bud: Budget`, so
  `rs.tick()` is `rs.bud.tick()`. `runChild` passes the budget's fields
  to a child run one by one, as before (the child's `held` is not
  copied back, as before).
- Exec keeps `type Ctx = lexdb_pipe.Ctx` (the private alias idiom) and
  the context's maker `cenvOf(seq)`.

**What was left, and why:**

- `Run` (the rest: 21 lines). It is the row engine's run state: the
  correlated subqueries' memo (`[]SubRes`), `SubStat`, the CTE cache
  (`CteCache`), the RIGHT and FULL join `seen` flags, the first level's
  switch. Moving it would take `SubRes` and the subquery machinery with
  it, which 6.2's table keeps in exec (`SubRes` reaches the pipe as a
  value). The pipe's operators take `mut &Budget`, which exec lends as
  `mut &rs.bud`.
- `Limits` and `noLimits`. They are the session's SET values for a
  statement (recursion, MATCH steps, memory, timeout, `lexdb_batch`, the
  planner mode, autoanalyze, range delete), read by statements and
  sessions (layer 7). `Run.limit` copies the memory and deadline into the
  budget.
- `resBytes` (it reads `SubRes`), `seqEnv` and `SeqEnv` (the session),
  `fnRefOf` (binding policy: which names are `FN_NONE` reads
  `isSeqFn`, `isSessFn`, `isAdvFn`), `call`.

**Line counts:**

| | main fde5d3aa | hook | evaluator | budget |
|---|---:|---:|---:|---:|
| `lexdb_exec` | 27,989 | 28,016 | 27,874 | 27,782 |
| `lexdb_pipe` | | | 179 | 291 |

So 207 lines left exec (6.2 estimated ~370; the rest is `Run` and
`Limits`, above). `lexdb_bind` and `lexdb_lib` changed a comment each.
`imports.py` gained 6.2.3's rules for `lexdb_pipe`: what it may import,
`Store` and `Txn` only from the store, no `.sql.`, and only `lexdb_exec`
imports it (198 edges, then 205). Each rule was checked to fail on a
planted import.

**Gates:**

- Suite, from a snapshot of each commit (`e7/suite-e1a`, `e1b`, `e1c`):
  189 passed, imports ok (198 edges, then 205 from the second commit on).
- Naming battery (`bench/naming`): identical to main's build for each of
  the three builds (`e1/nam-*.out`).
- TPC-H, SF1, one run of the last commit's build (`e1/out-e1`): the 22
  checksums are the baseline's (1744ef99). Against main's stored run
  (`out-main-fde5d3aa`, the same code as main): total 23,110 to 22,937
  ms (-0.75%). Every query was within 3%: q1 -3.0%, q3 -2.1%, q20
  -1.9%; the most slower q22 +2.9% (441 to 454 ms) and q18 +0.8%. No
  repeat: the total is better, not 1.5% worse.
- Row path, one pass each, main's build (fde5d3aa) against E1's:
  - `simple.sh` (pgbench, 4 clients, 10 s): point select 47,493 and
    48,535 tps (+2.2%), update 9,503 and 9,522 (+0.2%), 3-table join
    20,195 and 20,525 (+1.6%).
  - `pts.sh` (20,000 planned point selects, 5 runs, means): wall 727 and
    716 ms, server CPU 679 and 668 ms (-1.6%).
  - One pass is within noise; nothing is slower. The entry hook adds an
    indirect call per `eval` function call (`callAt`), which these do
    not show.

**Hand-over to P1** (the first pipe operators, 6.2.3):

- The evaluator is in place: the batch kernels that move with P1 call
  `lexdb_pipe.bxEval` already (`bCompileD`'s constant folding,
  `bGenVals`), so they lose a prefix. `bCompile*`, `bCondOf`, `outNode*`
  and `bGenOf` take `&Ctx`; `Mats.ce`, `OutC.ce` and `BGen.ce` hold one.
- The budget is in place: the batch engine reaches it only as `rs.bud`
  (`tickN` 11 times, `aside`, `held`, `hold`, `tick`, `maxHeld`, `room`). P1's `run` takes `bud: mut &Budget`; exec
  passes `mut &rs.bud`.
- What still ties the batch core to exec (map `pipe1`, at 386438df):
  `Query` (for the columns' kinds and slots: `bCompile`'s `q`), `Mats`,
  `BSpec`, `Sel`, `OutPlan` and `ONode`. P1 takes them from the `PPlan`
  arm instead (6.2.3, "To the plan"). `execmap.py` groups by line
  ranges, which E0 and E1 shifted: re-base its tables before using the
  map again.
- `Ctx` has no subquery results yet. A RUN_ONCE subquery's value must
  reach it as a value (a scalar's `Val`, IN's set), not as `SubRes`,
  whose memo and data are the row engine's. This is P1's "RUN_ONCE
  subqueries as values".
- `Counts` is per table today (`Run.cnt`, per level). P1's operators
  need counts per operator for EXPLAIN ANALYZE; `Budget` has room for
  them (6.2.3's "counts per operator").
- The q1 placement effect of E0 (6.2.4) is still there; read q1 against
  main's stored run with that in mind.

#### 6.2.6 P1 as built: slice P1a (scan, filter, project)

Built 2026-11-17 on `redesign/bind` from main 9aa2c0b2. Scripts and
outputs are in `~/tpch-w/bind/p1`. P1 was split in three (P1a scan,
filter and project; P1b aggregates over one table; P1c sort and limit
over them, and the deletions). This section is P1a; P1b is 6.2.7, P1c
6.2.8 (built as RUN_ONCE subqueries and the deletions; sort and limit
went to P3).

**Commits:**

- 44b8cc2d, the batch kernels move to `lexdb_pipe`, unchanged but for
  their columns: `BNode`, `BComp`, `BGen`, `BSpec`, `LikePat`, their
  compile (`bCompile`, `bCompileD`, `bAndOr`, the constant and kind
  helpers), their evaluation (`bEval`, `bGenVals`, `bTrue`, `bNarrow`,
  `bAddVals`), the two-step decode's plan (`lazyOf`, `placesOnly`), the
  column leaves' ranges (`cRanges`), the aggregates' accumulation
  (`bAccum`, `bAccVal`, `bAccDec`), `bRow`, `bFirstVals`, `bKeyVal`,
  `bColsOf`, `bValAt`, `sortCmp`, `valExtra`. `bCompile` reads the
  query's `ColDef`s, not its `Query` (the only thing it read of it).
  `immutableName`, `isSeqFn` and `isAdvFn` go to `lexdb_bind` (binding
  policy; `bxFixed` needs the first). Exec names the rest as
  `lexdb_pipe.*`, with private aliases for the five types.
- 37d6788b, the pipeline's first operators (below), `outNode`,
  `bOutVal`, `ONode` and `condNode` (exec's `bCondOf`) into the pipe,
  `OutBatch` into `lexdb_rows` (the wire writes it and may not import
  the pipe; exec keeps a private alias), and the test `exec_pipe`.

**The plan.**

- `lexdb_plan.PPlan` gains `Scan(PScan, []PSub)` and `Filter(PPlan,
  []BX)`; `Project` holds its outputs as `[]BX` ([] in a view); `Limit`
  holds its count and offset (`Limit(PPlan, stops, count, offset)`).
  `PScan` holds the level, the first slot, the query's columns' kinds,
  the table's columns decoded, `part`, and whether its ranges are read
  in batches (`batch`: false where bLevelPlan declined, below).
- `pipeSel` (exec), after `bindSel` in `select()`, in EXPLAIN and in
  EXPLAIN ANALYZE, builds `Limit? (Sort? (Project (Filter? (Scan))))`,
  the Sort only the scan's order. The outputs `bindSel` bound (`Sel.ox`)
  and the table's bound conditions (`Query.cc[0]`) are **moved** into
  the Project and Filter arms; a column output is `BX.Col(slot)`.
  `lexdb_pipe.compile(PPlan, cols): Result[Prog, PPlan]` checks it; on
  `Ok` the `Prog` (which owns the plan) is kept in `Sel.pipe`, so the
  plan cache keeps it; on `Err` the plan comes back and `unplan` returns
  its outputs and conditions to the Sel.
- The table and its path stay in `Query.levels[0]` (EXPLAIN's lines and
  the row engine read them); `Sel.limit` stays (the row engine and
  locking read it), so the Limit arm's count is a copy of an int. The
  Level's fields move when `Levels` splits into scan and join arms (P2).
- EXPLAIN prints the kept plan (`selLines`: `Sel.pipe`'s, else
  `physOf`'s view). `Scan` prints as `Levels` did, `Filter` prints
  nothing: the 22 TPC-H EXPLAINs are byte-identical to main's.

**What compile accepts** (`opsOf`, and `pipeShape` in exec, which says
what the Sel must give):

- a SELECT that streams (`streams`: no sort, grouping, DISTINCT, window,
  set, OFFSET, lock, set-returning call, correlated output), with no
  MATCH_RECOGNIZE, `SELECT @v = ...` feedback, TOP PERCENT or WITH TIES,
  MIN/MAX by the scan;
- one table level read per row: not a subquery's or CTE's rows, not
  LATERAL, no post-join WHERE, not a semi or anti level;
- **no subqueries at all** (`scanRuns`: RUN_ONCE values in `Ctx` are not
  built, below);
- every output a column or bound for the plan, every condition bound,
  each reading only the table's decoded columns (`reads`);
- a Limit with a count and no offset, over the rest.

Everything else is rejected and runs as before: joins, aggregates,
sorts, DISTINCT, windows, sets, subqueries, DML's queries (they are not
bound: `bindSel` runs only in `select()` and EXPLAIN), a subquery's own
Sel.

**What run does** (`lexdb_pipe.run`, `runScan`):

- Exec gives it the table, a `Src` per run (`pipeSrc`: `pathScans` with
  the run's parameters, `afterScans`, and optimizer 19's switch,
  `firstSwitch`, as bLevelPlan and runLevel decide it), the context
  (`cenvOf` and the parameters), `mut &rs.bud`, a cap, and one sink:
  `give(txn, &OutBatch, &[]Val)`, a chunk as an OutBatch or one row
  (two sinks would capture the same state mutably twice, which Lexell
  rejects).
- **In batches** when the plan's scan reads batches and a scan is a
  range: `fillPickIn` with the conditions compiled per run (`condNode`:
  a kernel, else `Gen`) narrowing the selection, two-step decode and
  column-leaf ranges as before; the outputs over the chunk (`outNode`,
  `bOutVal`); the chunk to the sink as an OutBatch, cut at the limit.
  This is `eachOut`'s single-table branch, counted the same.
- **Row by row** (a chunk of one) otherwise: a primary key's point, a
  primary key read backward, IN lists, a non-covering index where the
  reading may stop, a switched range's keys (`getRow`), scans of points
  only. Each row through `bxEval`: conditions in order, then outputs, as
  `tryRow` and `outRow` run them. Point selects take this path.
- **A chunk the kernels cannot evaluate** (a value its batch cannot
  hold, a condition's or an output's error on one of its rows) is read
  again from its start row by row, with the rest of its scan, as the
  batch drivers gave way. So an error is the row engine's (its first
  failing row, its conditions before its outputs), and the rows before it
  reach the sink first. This is a mode of the pipe's own scan, not a
  hand-over to the row engine; a per-chunk return to batches is left
  for later (it would change the tests' OutBatch counts and EXPLAIN
  ANALYZE's batches in that case).
- Held rows (`execSel` → `pipeHeld`) and streamed rows (`eachRowB`, for
  the wire's OutBatches and for `eachRow`'s rows) both run the
  pipeline when `lexdb_batch` is on; `pipeHeld` counts
  `max_statement_mem` per row as execSel's row path does. With
  `lexdb_batch` off the row engine runs the Sel, binding its outputs and
  conditions per run (they are in the plan now).
- Counts: `run` keeps one `Counts` per operator; the scan's (starts,
  read, kept as `joined`, batches) go to the run's table counts, so
  EXPLAIN ANALYZE prints what it printed (`exec_pipe` compares 24 shapes
  with the pipeline on and off, batches included). The Project's rows
  given are counted, not printed.
- `runCounts` (runs, runs that read batches) and exec's `setPipe` (a
  test's switch: off, `pipeSel` makes nothing and the batch drivers run)
  are for the tests.

**Behaviour change, one:** under LIMIT 0 the held rows' path read a
first row and gave its error (`select x / 0 from t limit 0` failed when
held, and gave no rows when streamed). The pipeline reads nothing, as
the streamed path did and PostgreSQL's Limit does. Unavoidable: the two
old paths disagreed, and the pipeline serves both.

**Line counts:**

| | main 9aa2c0b2 | 44b8cc2d | 37d6788b |
|---|---:|---:|---:|
| `lexdb_exec` | 27,782 | 26,498 | 26,691 |
| `lexdb_pipe` | 291 | 1,598 | 2,049 |
| `lexdb_plan` | 229 | 229 | 259 |
| `lexdb_bind` | 2,025 | 2,043 | 2,043 |
| `lexdb_rows` | 1,647 | 1,647 | 1,666 |

1,091 lines left exec. The secret that left is the batch kernels'
(how an expression and an aggregate run over a batch's columns: 6.2.1's
`batch.core` and `bAccum`, 1,284 lines), and the output nodes. Exec
gained the glue (`pipeSel`, `pipeShape`, `unplan`, `runPipe`,
`pipeSrc`, `pipeHeld`, `obRow`, ~230 lines). **Nothing was deleted**:
the old drivers still run what compile rejects, and compile does not yet
accept everything the single-table drivers accepted (see the hand-over).
Import edges 205 to 214, all within `imports.py`'s rules.

**Gates:**

- Suite from a snapshot of each commit (`e7/suite-p1a1`, `p1a2`): 189,
  then 190 passed (with `exec_pipe`), imports ok.
- `exec_pipe`: 500 random queries committed and 120 in a transaction
  with its own writes, 30 fixed shapes, each four ways (rows; batch
  drivers; pipeline held; pipeline sunk), rows and errors the same, the
  sinks' rows before an error the same; every path; errors on one row of
  a batch before and past a LIMIT; short-circuits under AND, OR and
  CASE; NULLs; casts that fail; an integer's overflow; 12 runs of a
  prepared statement with parameters from one plan cache against the row
  engine; `max_statement_mem` (the same 53200 four ways, and the same
  rows under it); EXPLAIN ANALYZE and EXPLAIN of 24 shapes the same with
  the pipeline on and off.
- Naming battery (`p1/nam-*.out`, 1,505 lines): identical to main's.
- EXPLAIN of the 22 TPC-H queries (`p1/exp-*.txt`, 188 lines):
  byte-identical to main's build.
- TPC-H, SF1, one run of 37d6788b's build (`p1/out-a`): the 22 checksums
  are the baseline's (1744ef99). Against `out-main-9aa2c0b2`: total
  22,937 to 23,176 ms (+1.04%); q1 2,282 to 2,360 (+3.4%), q6 606 to
  611 (+0.8%); q8 +2.2%, q13 +2.3%, every other query within 2%. No
  TPC-H query runs in the pipeline (all aggregate or sort).
  - q1 was repeated on copies (`p1/rep.sh`, 3 runs a pass, alternating,
    two passes, medians): q1 2,428 and 2,421 ms for the branch against
    2,343 and 2,338 for main (+3.6%), reproduced; q6 609 and 604 against
    606 and 604, level.
  - The first commit alone (44b8cc2d, the move, no new path; `p1/repk.sh`)
    gives the same: q1 2,422 and 2,405 against 2,369 and 2,342 (+2.5%).
  - Profiles of q1 (`p1/pq1-m.txt`, `pq1-k.txt`, resolved with the
    native maps by `p1/res.py`): main's and the move's builds have the
    same functions in the same order (the same numbers, `f2439` for
    `bEval` in both), the same shares to 0.3 points but `dup` (7.6% and
    5.6%), and the move's profile has 1.9% fewer samples. So the move
    does not add work on q1's path: the harness's 2-4% is the effect 6.2.4
    saw on E0, a placement or data-layout effect not explained. Not
    resolved.
- Point selects, main's build against 37d6788b's, one pass:
  `simple.sh` point select 48,115 and 48,521 tps (+0.8%), update 9,491
  and 9,491, 3-table join 20,406 and 20,428; `pts.sh` (20,000 planned
  `select * from w where id = k`, now the pipeline's row-by-row scan)
  wall 716 and 722 ms, server CPU 668 and 674 ms (+0.8%).
  - Repeated on the copies (two rounds, 10 runs each): wall 713 and 723
    ms, CPU 666 and 674 ms (+1.2%). So point selects are about 1% slower
    in the pipeline's row-by-row scan, consistently, and within the
    1.5% the TPC-H gate allows. A profile of each (`p1/ppts-*.txt`,
    5,800 samples) is too coarse to place 1%: `dup` 2.2% to 3.1%, the
    scan's `oneRow` 0.9%, the rest the same. Candidates: the plan-time
    work per statement (`pipeSel`'s arrays and the plan, made for every
    simple-protocol statement) and the run's (`pipeSrc`'s NULL row,
    the counts array, the scan's row) against what it skips (`prepare`'s
    `Mats`, `outC`). The OLTP gate (section 7) should see this profiled
    at a finer grain before P1b adds to the path.

**Hand-over (P1a's rest, then P1b and P1c):**

- **RUN_ONCE subqueries as values** are the first gap. The binder does
  not bind `#sub`, `#in` or `#exists`, so a condition or output that
  reads one has no `BX`, and `scanRuns` rejects any subquery. The plan:
  `Ctx` gains the values (a scalar's `Val`, an EXISTS's bool, an IN's
  set keyed as `inValKeys` keys it), a `BX` arm reads them, and exec
  runs the RUN_ONCE subqueries (prepare's `runSub`) before `run`. Until
  then the single-table drivers still run plans with an uncorrelated
  subquery (in a path bound, or in a condition the plan does not bind).
- **Deletions.** Once compile accepts those: `outPlan`'s and `eachOut`'s
  single-table branches (`op.joined` false), `batchLevel`'s
  single-level `direct` branch become dead with the pipeline on;
  `setPipe` goes with them. The joined branches go in P2. `pipeSrc` repeats bLevelPlan's
  scan setup (`pathScans`, the switch, the index read): it should move
  to `lexdb_access` with `pathScans` (6.2.1's access group), so the
  pipe makes its own scans and exec stops building `Src`.
- **P1b** (aggregates over one table, q1 and q6): `batchGroupsIn`'s
  one-table branch becomes an `Agg` arm (keys, calls, FILTERs as `BX`,
  moved from `Sel.groupBy` and `Sel.specs`, bound in `bindSel`) and a
  hash-aggregate operator over the scan's chunks, units first. Notes
  from reading it:
  - its conditions and keys compile without `Gen` (`bCompileCond`,
    `bCompileX`), so it declines `upper(x) = ...` or a text key of a
    function; the pipe should take `condNode`'s generic step for
    conditions, and needs a generic key and argument step (values
    through `bxEval`, grouped by `encIdxPart`, accumulated as the row
    path's `accumulate`) to accept everything the row path groups;
  - which conditions compile as units depends on parameter values
    (`bCompileD` folds constants), so compile at plan time cannot know;
    the units retry (`batchGroups`: units, then values, then the row
    path) becomes the operator's: on a spill, run its chunks again with
    values, from the start (the groups are made at the end);
  - a condition's error in a batch is raised from the batch (it does not
    give way), so the reported row is the lowest of the first failing
    step, as 4.4.1 says, not the row engine's;
  - HAVING (`fuse`), the outputs and ORDER BY over the groups stay exec's
    (`Groups`) until P1c brings Project and Sort over the Agg arm.
- **P1c**: Sort, TopN and Limit over chunks (6.2.3's P3 moves
  `sortBatches`); Limit with OFFSET; then the deletions above.
- Traps: `pSubs`, `pLeaf` and `opLines` need a case for each new arm
  (Scan, Filter were added). `Limit` has four fields now. A Sel's `ox`
  and `q.cc[0]` are empty when `Sel.pipe` is set: code that reads them
  must take the arms' (`runPipe`), or bind per run as the row engine
  does. Two closures capturing the same state mutably are rejected:
  give the pipe one sink.

#### 6.2.7 P1b as built: aggregates over one table, and two checks

Built 2026-11-17 on `redesign/bind` from main 51aa78b7. Scripts and
outputs are in `~/tpch-w/bind/p1b`.

**Check 1: q1's 2-4% after E0 and P1a is code placement.**

- main 51aa78b7's source built six times with the native backend's
  placement knobs (`bplace.sh`: `LXL_PADB` 0, 16, 32, 48 with
  `LXL_FALIGN` 64; `LXL_PADB` 0 and 32 with `LXL_FALIGN` 128), q1 alone,
  3 runs each, two passes in opposite orders (`q1place.sh`,
  `q1place.log`). Medians, ms:

  | PADB / FALIGN | pass 1 | pass 2 |
  |---|---:|---:|
  | 0 / 64 (the default: main's binary, byte-identical) | 2,353 | 2,344 |
  | 16 / 64 | 2,398 | 2,383 |
  | 32 / 64 | 2,400 | 2,385 |
  | 48 / 64 | 2,356 | 2,365 |
  | 0 / 128 | 2,390 | 2,412 |
  | 32 / 128 | 2,304 | 2,332 |

- The same code moves q1 by 3.6% (pass means 2,318 to 2,401), up to
  4.7% between single passes. Placement explains the 2-4% of E0 and
  P1a; it is not chased further. Read a q1 difference under about 4% as
  noise until a build pins placement.

**Check 2: point selects.**

- Profiles (`profpts.sh`: perf at 20 kHz with frame-pointer call graphs,
  10 runs of `points.sql`, about 158,000 samples each; `ppts-e1.data`
  for main's pre-P1a build `e1/lexdb-e1`, `ppts-a.data` for main
  51aa78b7; resolved with `p1/m.map` and `p1/a.map` by
  `e7/tools/selfdiff.py` and `under.py`). Inclusive shares:
  - the statement's run (`runSelTo`) fell from 28.83% to 26.42%;
  - `pipeSel`, the pipeline's plan made per simple-protocol statement,
    is 2.23% (`pipeShape` 0.83%, its own loops 0.74%, `compile` 0.48%);
  - so the executor's part is level (-0.18 points);
  - the rest of the +1.2% samples is in code P1a did not change:
    parsing (`parseIn` 12.85% to 13.80%), `planSelect` (28.78% to
    29.80%), `choosePath`. That is placement again.
- pts.sh, 3 rounds of 5 runs alternating (`pts-place.txt`), server CPU
  means: e1 666.1 ms; main 51aa78b7 672.7 (+0.99%); the same source with
  `PADB 32 / FALIGN 128` 662.1 (-0.59%) and `PADB 16 / FALIGN 64` 663.1
  (-0.45%). Main's own code, placed otherwise, is faster than e1. So the
  +0.8-1.2% is placement, within a 1.6% spread; the executor's path
  costs no more than the old one. Nothing was changed for it: trimming
  `pipeSel` (0.9 µs a statement) is cheap later, but would not show
  under this noise.

**Commits:**

- c1d6e547 (1/n): the Agg arm with its details; `lexdb_pipe.runAgg`;
  exec's glue; `exec_pipe` extended.
- db22f0bd (2/n): the aggregates of subqueries, set parts and statements'
  queries; the one-table branch of the batch driver deleted.
- 93fcf5bd (3/n): a group's states given in one array used again, and
  exec's accumulators made only for a group it keeps (q18).

**The plan.**

- `PPlan.Agg(PPlan, bool, Option[PAgg])`: `PAgg { keys: []BX; calls:
  []PCall; keep: []bool }`, `PCall { fname; star; arg: Option[BX];
  filter: Option[BX] }`. None in a view (physOf).
- `pipeAgg` (exec), from `pipeSelIn`: binds the GROUP BY keys and the
  calls' arguments and FILTERs (`bxOf`), moves the table's bound
  conditions (`Query.cc[0]`) into the Filter, and makes
  `physAbove(sel, Agg (Filter? (Scan)))`: physOf's operators over the
  groups (Having, Project([]), Distinct, Sort, Limit, Match) as views.
  physOf was split for it (`physAbove`), so EXPLAIN prints the kept plan
  as before: the 22 TPC-H EXPLAINs are byte-identical.
- With no GROUP BY, the scan's `need` is the conditions' and calls'
  columns (a column outside a call is 42803), as the driver narrowed it.
- `keep` is `afterCols` (the outputs', HAVING's and ORDER BY's columns):
  a group's first row holds only those.
- What stays in the Sel: `groupBy` and `specs` as `Expr`s, which the row
  engine (`lexdb_batch` off) and the output's `finish` read. As in P1a,
  the bound forms moved, the expressions stay until the row engine goes.

**What compile accepts** (`aggOps`, and `aggShape` and `pipeAgg` in
exec):

- an aggregate over one table read per row whose columns are the
  query's (`first` 0), no grouping sets, no window, no MIN/MAX by the
  scan's order, no lock, no subquery of its own, not a correlated
  query's (`q.corr`; a correlated subquery's own Sel is accepted: its
  outer values are its parameters);
- keys of any type with no collation's keys; calls count(*), count,
  sum, avg, min, max, not DISTINCT, no ORDER BY, no collation; FILTER;
  each key, argument, FILTER and condition bound and reading the
  table's decoded columns;
- any HAVING, outputs, DISTINCT, ORDER BY, LIMIT, OFFSET, TOP and
  MATCH_RECOGNIZE over the groups (exec's views).

It rejects (the row engine runs them, as before): DISTINCT or ORDER BY
in a call, string_agg, array_agg, bool_and, the variances, collations'
keys, grouping sets, joins (the batch driver's, `batchGroupsIn`), and an
aggregate with a subquery (RUN_ONCE values, below).

**Where plans are made.** `pipeSelIn(sel, rows)`: the SELECT's own plan
(rows: P1a's scan too), then for its subqueries and set parts, and for
CREATE TABLE AS, INSERT ... SELECT and COPY (query) TO, aggregates only
(those statements now call `bindSel`; their scans stay the row
engine's, as P1a left them). So a correlated subquery's aggregate (q17,
q20) and q18's IN subquery run in the pipe.

**What runAgg does** (`aggRun`):

- Over batches, numerics as units (BK_DEC, sums in 128 bits); if the
  units give way (a numeric past them, `XXDEC`, or an expression they
  do not compile) again with numerics as values; if batches give way (a
  value a batch cannot hold, an expression the kernels do not compile, a
  text key that is not a text) row by row. Each from the start, the
  counts reset: the groups are given at the end, none yet. This is
  `batchGroups`' retry and its give-way, now the operator's.
- The batch passes are `batchGroupsIn`'s one-table code, moved: the
  grouping by one integer key (a map, or by the primary key's order with
  no map: q18), by a text key's text, or by the keys' encoding; the
  first rows' columns kept; `bAccum`, `bAccDec`, `bAccVal`; the memory
  counted per group as before.
- The row pass (`aggRows`) reads the scan as `runScan` does (in batches
  where it can, its conditions over the batch with the generic step, as
  the row engine's first level reads them in `batchLevel`; else row by
  row) and groups each row it keeps by the scalar evaluator
  (`groupRow`, `accOne`: `addToGroup` and `accumulate` for the five
  calls). Its memory is counted as the row engine counts it.
- The groups go to exec's `give(first, states)` (`PAcc { n; sum; val }`,
  an `Acc`'s fields). exec checks a fused HAVING first (no volatile
  function, no subquery: `fuse`, as before), keeping only the groups it
  passes, then makes the outputs over `Groups` as before.
- An aggregate's primary-key points are read as a batch, as the driver
  read them (`pipeSrc`), so EXPLAIN ANALYZE prints what it printed.
- Counts: the scan's go to the run's table counts; `decCounts` adds the
  pipe's (`aggCounts`: units runs, spills, grouped runs over batches),
  which `exec_batchdec` and `exec_narrow` read unchanged.

**Deleted** (db22f0bd): the one-table branch of `batchGroupsIn`
(numerics as units, the narrowing of a key-less aggregate's columns,
its scans and index reads, the sorted grouping), `batchGroups`' units
retry, exec's `decRuns` and `decSpills`. `batchGroupsIn` is the joins'
driver now (`len(q.levels) >= 2`). `obRow` moved to the pipe.

**Line counts:**

| | main 51aa78b7 | c1d6e547 | db22f0bd | 93fcf5bd |
|---|---:|---:|---:|---:|
| `lexdb_exec` | 26,691 | 26,901 | 26,762 | 26,770 |
| `lexdb_pipe` | 2,049 | 2,708 | 2,709 | 2,710 |
| `lexdb_plan` | 259 | 281 | 281 | 281 |

Exec is 79 lines longer. The first commit added the glue (`pipeAgg`,
`aggShape`, `pipeGroups`, `pipeRows`/`pipeAggs`, `bxUses`,
`physAbove`, `prepareIn`: 249 lines in, 39 out); the deletion removed
202 lines and added 63 (`pipeSelIn`, the statements' bindings, the
joins-only driver's head). Less left than 6.2.3 hoped because the
driver's one-table and join code were one function: what was only the
one table's is gone, the rest is the joins'. The pipe gained 661: the
aggregate (the driver's one-table passes and its retry, ~430), the row
pass and the scalar accumulate (~120, new), `compile`'s checks. The
big deletions (`eachOut`'s, `outPlan`'s and `batchLevel`'s single-table
branches, ~300 lines) wait for RUN_ONCE values.

**Gates:**

- Suite from a snapshot of each commit (`e7/suite-p1b1`, `p1b2`,
  `p1b3`): 190 passed, imports ok (214 edges: no new import).
- `exec_pipe` gained the aggregates, four ways (rows; the pipeline off;
  pipeline held; pipeline sunk): 400 random queries committed and 80 in
  a transaction with its own writes, 26 fixed ones. Keys of each type
  with NULL keys, expressions and several keys; count, sum, avg, min,
  max of each type; FILTER; numerics' scales (`sum(nu * 2)`,
  `avg(nu * x)`); HAVING fused and not; DISTINCT over the groups; ORDER
  BY and LIMIT; empty input with and without GROUP BY; an integer's
  overflow (`sum(y * 1000000000)`) and a division by zero in a call;
  shapes the batches do not run (a float's sum, a text function's key:
  the row pass) and shapes compile rejects (DISTINCT and ORDER BY in a
  call, string_agg, ROLLUP); 12 runs of a prepared aggregate from one
  plan cache against the row engine; `max_statement_mem` (53200 four
  ways, the row pass's too, and the same rows under it); EXPLAIN ANALYZE
  and EXPLAIN of 12 aggregate shapes the same with the pipeline on and
  off. The first commit ran it against the batch driver (all the same);
  after the deletion the "off" way is the row engine.
  `exec_batchdec` (units, spills, values) and `exec_narrow` pass
  unchanged through the pipe's counters.
- Naming battery (`nam-p1b2.out`, `nam-p1b3.out`): identical to main's.
- EXPLAIN of the 22 TPC-H queries (`exp-*.txt`): byte-identical to
  main's.
- TPC-H, SF1, one run each of db22f0bd's (`out-p1b2`) and 93fcf5bd's
  (`out-p1b3`) builds: the 22 checksums are the baseline's (1744ef99).
  Against `out-main-51aa78b7` (ms):

  | | main | db22f0bd | 93fcf5bd |
  |---|---:|---:|---:|
  | total | 23,176 | 23,146 (-0.13%) | 23,161 (-0.06%) |
  | q1 | 2,360 | 2,396 (+1.5%) | 2,383 (+0.9%) |
  | q6 | 611 | 602 (-1.5%) | 617 (+1.1%) |
  | q18 | 1,274 | 1,342 (+5.4%) | 1,207 (-5.2%) |
  | q20 | 396 | 380 (-3.8%) | 380 (-3.9%) |

  Every other query within 3.3% (q13 -3.3%, q21 +1.7%, q8 +1.5%).
- Repeated on copies (`rep.sh`, `rep18.sh`, 3 runs a pass, alternating,
  two passes, medians):
  - db22f0bd against main: q1 2,303 and 2,347 against 2,378 and 2,395
    (-2.5%), q6 601 and 605 against 604 and 616 (-1.1%); q18 1,355 and
    1,361 against 1,243 and 1,265 (+8%, reproduced). The cause was a
    new accumulator (with its DISTINCT map) and a states array made for
    each of q18's 1.5M groups, which HAVING drops; 93fcf5bd fixed it.
  - 93fcf5bd: q18 1,211 and 1,209 against 1,272 and 1,274 (-5%).
  - q1 and q6 are in the pipe now; within check 1's placement spread
    they are level with main.
- Point selects, one pass each against main (copies):
  - `pts.sh` (2 rounds of 5 runs, `pts-c3.txt`), server CPU means: e1
    665.2 ms, main 670.3 (+0.77%), 93fcf5bd 671.0 (+0.87%; +0.1%
    against main). Against e1 that is the placement of check 2 (main's
    own code placed otherwise ran -0.5% against e1), not under the 0.5%
    gate by measurement. Nothing P1b did shows on this path.
  - `simple.sh` (`simple-c3.txt`): point select 49,271 and 50,003 tps
    (+1.5%), update 9,488 and 9,474 (-0.1%), 3-table join 20,228 and
    20,394 (+0.8%).

**Hand-over (P1b's rest, then P1c):**

- **RUN_ONCE subqueries as values: not built.** It is the next item and
  gates every remaining deletion. What it takes, from reading the code:
  - `lexdb_bind`: a `BX.Sub(kind, i, probe)` arm (scalar, EXISTS, IN with
    its probe), bound only where the subquery is RUN_ONCE (`#sub`,
    `#exists`, `#in` with no correlated arguments). Six exhaustive BX
    matches gain a case (`bxEval`, `reads`, `reslot`, `hasParam`,
    `bxConst`/`bxFixed`, `bCompileD`).
  - `Ctx` gains `subs: []SubVal { rows; val; set; hasNull; numeric }`,
    exec's `SubRes` result as a value. Every `Ctx` a bound expression
    with a Sub is evaluated in needs them, including `BGen.ce` (bGenOf
    copies only now, zone, params) and `outC`'s: bind the Sub only for
    plans the pipe keeps, or fill `subs` wherever `cenvOf` makes a Ctx
    for a query with subqueries.
  - IN's keys move to the pipe as a section (`setKey`, `inClass`,
    `fKey`, `wholeF`, `exactInt`, `isInstantClass`, `inValKeys`,
    `inProbeKeys`, `inProbe`, `keyPart`; ~200 lines, used by exec's
    semi-joins and hashed subqueries too: exec calls them there).
  - `bCompileD` takes a Sub as a constant of the run (as a Param), IN
    as the generic step.
  - exec runs the RUN_ONCE subqueries before `run`/`runAgg` (prepare's
    loop; `pipeHeld` does not call prepare today) and passes the values.
  - `scanRuns` and `aggShape` accept subs whose `PSub.run` is RUN_ONCE
    and not FROM.
- **Then the deletions** P1a listed: `outPlan`'s and `eachOut`'s
  single-table branches and `batchLevel`'s `direct` branch, and
  `setPipe`. Note for the tests: with the one-table driver gone,
  `setPipe(false)` runs one-table aggregates in the row engine (with
  batches on), so `exec_pipe`'s "drivers" way for aggregates is the row
  engine now.
- `pipeSrc` (exec) still makes the pipe's `Src`; it should move to
  `lexdb_access` with `pathScans`.
- The batch passes compile conditions without the generic step (as the
  driver did, so `exec_narrow`'s "grouped over batches" is unchanged): a
  condition like `upper(tx) = 'L1'` sends the aggregate to the row
  pass, which reads it in batches anyway. Taking `condNode` in the
  batch passes, and a generic key and argument step (values through
  `bGenVals`, grouped by their encoding, accumulated as `accOne`), would
  keep such aggregates in batches; `exec_narrow`'s expectations would
  change.
- P1c: Project, Having, Distinct, Sort and Limit over the Agg arm as
  operators (they are exec's views over `Groups` today), Sort and TopN
  over chunks, Limit with OFFSET.
- Traps: `underViews` (pipe) and `unplan` (exec) must learn each new
  view arm; `Prog.groups` says whether `run` or `runAgg` runs a plan;
  `pipeRows`/`pipeAggs` are exec's two tests of it. `pipeSelIn`
  recurses into subqueries and set parts before the Sel itself.

#### 6.2.8 P1c as built: subqueries run once, and the deletions

Built 2026-11-17 on `redesign/bind` from main 5ab955fd. Scripts and
outputs are in `~/tpch-w/bind/p1c`. P1c was scoped to RUN_ONCE
subqueries as values, the deletions they unblock and the glue; Sort,
TopN and Limit over chunks stay with P3.

**Commits:**

- 75f33509 (1/n): a subquery's value (`SubVal`: rows, a scalar's value,
  IN's set, numeric, NULL seen) is the pipe's type; exec's `SubRes` holds
  one (`SubRes.v`). IN's keys (`setKey`, `inClass`, `typeClass`, `fKey`,
  `FLOAT_EXACT`, `wholeF`, `exactInt`, `isInstantClass`, `inValKeys`,
  `inProbeKeys`, `inProbe`), `subValue` and the hash key part `keyPart`
  move unchanged to `lexdb_pipe`; exec calls them (semi-joins, hashed
  subqueries, hash joins' keys, `eval`).
- 29faf843 (2/n): RUN_ONCE subqueries as values in the pipeline; the
  glue reworked (below); `exec_pipe` extended.
- cca0b1dd (3/n): `eachOut`'s one-table branch and `setPipe` deleted;
  where a run reads its table moves to the pipe (`srcOf`); a key-less
  aggregate's columns to `lexdb_plan` (`callsNeed`).
- 4f620bf1 (4/n): dead code (`allTrue`, `sysIntVal`: no caller, older
  than P1) and the `pipeRuns` forward deleted.
- 3a4512a2 (5/n): the plan's glue allocates less per statement (the
  point selects' profile, below).

**The plan and the run.**

- `lexdb_bind.BX.Sub(use, i, probe)`: a scalar, EXISTS or IN subquery
  (`lexdb_sql.SUB_*`), its number, IN's value as `[x]` ([] the others).
  It is bound only by `bindSubs`, only for a call with no outer values
  (exactly `subFixed` arguments), and only for a plan's arms (exec's
  `planX`). So the row engine never meets one: `bindExpr`, `bindSel`,
  `prepare` and `outC` bind as before. `unplan` gives back an arm that
  reads a Sub as unbound (`unbound`), so a rejected plan leaves the Sel
  as the row engine needs it. `hasParam`, `reslot` (a Sub sets `par`:
  the run's context), `bxEval`, `bxConst`, `bxFixed`, `reads` learn the
  arm; `hasSub` is new.
- `Ctx.subs: []SubVal`, by subquery number. `bxEval` reads a scalar's
  value, EXISTS's rows > 0, IN through `inProbe` (its value evaluated
  first, as `eval`). `bCompileD` takes a scalar's and EXISTS's value as
  the run's constant (`bxConst`), as a parameter; IN goes to the generic
  step (`Gen`), whose context copies the subqueries' values
  (`copySubs`, only when its expression reads one).
- `compile` (`scanRuns`) accepts a scan or aggregate whose subqueries
  are all RUN_ONCE and not in FROM; the PSubs are the Scan arm's now
  (`subsOf`), so EXPLAIN prints them from the kept plan.
- exec: `runSubs` (prepare's loop, extracted) runs them before the plan,
  with the run's `Run` (EXPLAIN ANALYZE's runs per subquery are counted
  as before, the bytes held too). `runPipe` runs them itself; the path
  reads their results (`pathScans`: `id = (select ...)`, `id in (select
  ...)`'s lookups), then their values are moved into the run's context
  (`pipeCtx`, `subVals`). `pipeGroups` lends `prepare`'s results the same
  way and puts them back (`subsBack`): HAVING and the outputs over the
  groups still read them through `Env`.

**What compile accepts now:** P1a's scans and P1b's aggregates as
before, plus any whose conditions, outputs, keys, arguments and FILTERs
read uncorrelated scalar, EXISTS and IN subqueries (in WHERE, in the
select list, under OR, NOT, CASE; NOT IN; in the path's bounds and
lookups). **It rejects** a correlated subquery of any kind (per row or
hashed: `q.corr`, or a call with outer values), a subquery in FROM, and
a semi or anti join. Note that an uncorrelated `x IN (select ...)` or
EXISTS conjunct of WHERE is planned as a semi join (9.104: two levels),
so most of those are P2's; P1c's IN is the one in the select list, under
OR or NOT, and NOT IN.

**Deleted, and what blocks the rest:**

- `eachOut`'s one-table branch: no one-table query reaches it with the
  pipeline on. Checked by a build that fails any query reaching it, over
  the whole suite (`inst.log`): none did. The cases the pipeline still
  rejects (a correlated subquery; MATCH_RECOGNIZE, TOP, WITH TIES, a
  `SELECT @v =` feedback) were rejected by `outPlan` too, or now go to
  `runQuery`, which gives the same rows. `eachRowB` asks the batch engine
  for joins only.
- `setPipe`/`pipeOn`: deleted; `exec_pipe` compares the pipeline with
  the row engine.
- **`outPlan`'s one-table branch is not deleted:** `sortBatches` (ORDER
  BY, top-N and DISTINCT over batches, 9.105) builds its OutPlan for one
  table through it. It goes with P3's Sort and TopN.
- **`batchLevel`'s `direct` one-table branch is not deleted:** it is the
  row engine's first level, and the row engine still runs every one-table
  query the pipeline does not: sorts and DISTINCT that `sortBatches`
  gives up, windows, set operations' parts, subqueries' own rows
  (`pipeSelIn` makes only aggregates for them), CREATE TABLE AS, INSERT
  ... SELECT and COPY (query) TO, a query with a correlated subquery. A
  build that fails any query reaching it failed 105 of the suite's
  190 tests (`inst2.log`). It goes when those are the pipeline's (P3 and
  the row engine's deletion).
- `prepare`'s per-run binding and `outC` stay for `lexdb_batch = off`.

**The glue** (exec's part of handing over a plan: 433 lines with
`pipeHeld` and the comments, from 455, though it now binds and runs the
subqueries too):

- moved out: where a run reads its table, in batches or row by row, the
  index read alone (its decoding) or by its range's keys, is the pipe's
  (`lexdb_pipe.srcOf`); exec gives it the path's scans and optimizer
  19's switch (`pipeSrc`, 19 lines with its comment, from 61). The path test the batch
  engine and the pipeline share is `lexdb_plan.scanBatches` (`bLevelPlan`,
  `batchGroupsIn` and the pipeline's scan had three copies of it). A key-less
  aggregate's decoded columns are `lexdb_plan.callsNeed` (required
  columns are the plan's, 6.2.2).
- shared, not duplicated: `scanArm` (the PScan), `planConds` (the
  table's conditions moved, or bound for the plan), `filterOver`,
  `pipeCtx`, `scanCounts`, `tableRead`.
- stays exec's: what reads `Sel`, `Query` and `Level` (`pipeShape`,
  `aggShape`, `pipeSelIn`, `pipeAgg`, `scanArm`, `unplan`), the runs'
  hand-over (`runPipe`, `pipeGroups`, whose groups are exec's `Groups`),
  and the held rows' sink (`pipeHeld`, exec's `Res`). They move with the
  planner (E5).

**Line counts:**

| | main 5ab955fd | 75f33509 | 29faf843 | cca0b1dd | 4f620bf1 | 3a4512a2 |
|---|---:|---:|---:|---:|---:|---:|
| `lexdb_exec` | 26,770 | 26,518 | 26,579 | 26,494 | 26,475 | 26,481 |
| `lexdb_pipe` | 2,710 | 2,980 | 3,013 | 3,055 | 3,055 | 3,055 |
| `lexdb_plan` | 281 | 281 | 293 | 320 | 320 | 320 |
| `lexdb_bind` | 2,043 | 2,043 | 2,101 | 2,101 | 2,101 | 2,101 |

Exec is 289 lines shorter. The secrets that left it: subqueries' values
and IN's keying (how a value is found in a set as = compares, 252
lines), how a run reads its table (`srcOf`), and a key-less aggregate's
columns. The pipe gained 345 lines (the moved keys 270, Sub and the
context 33, `srcOf` 42); bind 58 (the arm, `bindSubs`, `hasSub`); plan
39 (`scanBatches`, `callsNeed`). No new import edge.

**Gates:**

- Suite from a snapshot of each commit (`e7/suite-p1c1`, `p1c2b`,
  `p1c3`, `p1c4`, `p1c5`): 190 passed, imports ok (214 edges). The first
  run of 2/n failed two expectations that the slice changes on purpose,
  amended into it: `exec_batchexpr` gives 286 of 600 queries as
  OutBatches (267: its queries with `(select max(id) from g)` in WHERE
  are the pipeline's now), and `exec_narrow`'s query 12 (`count(*)` with
  an uncorrelated EXISTS over EXCEPT) is grouped over batches.
- `exec_pipe` gained the subqueries: 300 random queries (scalar, EXISTS,
  IN and NOT IN in WHERE, in the select list, in an aggregate's
  conditions, keys and calls; IN of integers, numerics, texts, dates;
  sets with a NULL, empty ones; a primary key or index path through
  them) and 34 fixed ones: a scalar of more than one row (21000) in WHERE
  and in the select list, empty results and NULLs, a division by zero
  through a subquery's value, a path's point and lookups per value, a
  correlated one (rejected: the row engine), an aggregate over a
  subquery that has its own. Then 12 runs of a prepared statement with
  parameters in its subqueries from one plan cache against the row
  engine, and EXPLAIN ANALYZE of 10 shapes. Run four ways at 2/n (all the
  same; EXPLAIN ANALYZE the same but for batches: the drivers read rows
  the pipeline reads in batches); from 3/n two ways (the drivers and
  `setPipe` deleted), the earlier shapes too: all the same.
- Naming battery (`nam-c2.out`, `nam-c4.out`) and EXPLAIN of the 22
  TPC-H queries (`exp-c2.txt`, `exp-c4.txt`): identical to main's.
- TPC-H, SF1, one run of 4f620bf1's build (`out-c4`; 2/n's too,
  `out-c2`): the 22 checksums are the baseline's (1744ef99). Against
  `out-main-5ab955fd`: total 23,161 to 23,003 ms (-0.68%; 2/n -0.72%);
  q1 +0.2%, q6 -2.9%, q21 -3.1%; every query within 3% but q16, +6.9%
  (2/n: +6.0%).
  - q16 repeated on copies (`rep.sh`, 3 runs a pass, alternating, two
    passes, medians): 2/n's build 570.7 and 565.2 against main's 556.6
    and 560.9 (+1.6%); 4f620bf1's, after q14 and q15 as in the full run,
    557.1 and 556.2 against 557.1 and 555.0 (level). Not reproduced.
    q16's NOT IN probes go through the moved `inProbe`; that is the only
    code it runs that changed.
  - 3a4512a2 (5/n) changes only plan-making; it was not run through
    TPC-H.
- Point selects (copies of main's and the branch's builds):
  - 4f620bf1: `pts.sh` (2 rounds of 5) server CPU 680.4 against 674.0 ms
    (+0.95%); `simple.sh` point select 48,550, 49,247, 49,018 tps
    against 50,047, 49,693, 50,765 (three passes, -2.4%), update and join
    level.
  - Profile (`ppts-m`, `ppts-b`; 10 runs of `points.sql`, the same work):
    the run (`runSelTo`) level, `pipeSelIn` (the plan made per
    statement) 3.34% against 2.54%, its mallocs 0.14% against 0.02%. 5/n
    trimmed it: 2.86% (`ppts-c`), +0.34% of the samples over main's.
    Samples in all: 157,225 (main), 158,566 (5/n): +0.85%, of which
    `planSelect`, unchanged, +1.1%.
  - 3a4512a2: `pts.sh` 678.9 against 667.9 ms (+1.65%); `simple.sh`
    point select 48,593 and 48,677 against 50,351 and 50,735 (-3.6%).
  - Placement (`place.sh`, as 6.2.7's check 2): 3a4512a2's source
    built with `LXL_PADB 32 / LXL_FALIGN 128` gives 49,877 and 49,950
    tps (-1.0% against main's 50,066 and 50,702 in the same rounds) and
    `pts.sh` CPU 669.8 against 668.8 ms (+0.15%); with `PADB 16 / FALIGN
    64`, 48,593 and 48,905 tps. So most of the -3.5% is placement; what
    the code adds is the plan glue's +0.34% (profile) to about 1%. Not
    chased further: placement is not pinned.

**Hand-over to P2 (hash joins, semi and anti, index lookups):**

- **What P2 starts from.** The pipe holds the hash key part
  (`keyPart`) and IN's keys, so a HashBuild and HashProbe key rows the
  way today's hash levels, semi-joins and hashed subqueries do (exec calls
  the same functions). `scanBatches` (lexdb_plan) and `srcOf` (lexdb_pipe)
  are per table: a join's inner tables each get a Scan arm with its own
  Src, or an IndexLookup arm whose keys come from the outer chunk
  (`fetchMany`, `rangeMany`: today's `bLookup`, `bRange`). `callsNeed`
  is the start of 6.2.2's required-columns pass: put the per-operator
  pass next to it.
- **Semi and anti joins.** An uncorrelated IN or EXISTS conjunct of WHERE
  is a semi level (9.104: RUN_SEMI, its rows a level's hash), not a
  `BX.Sub`: it is P2's HashJoin(semi/anti) with the subquery's plan as the
  build side, not a value in `Ctx`. A correlated one decorrelated by 9.9
  is RUN_HASHED (its keys and IN's per-key set, `runHashed`); a
  `SubVal` per key does not fit `Ctx.subs`, so it should become a build
  side too. `semiLook` (RUN_LOOKED) is an IndexLookup(semi/anti).
- **What then goes from exec.** `eachOut` is joins-only now; with joins in
  the pipe it goes, with `outPlan`'s joined branch (`bJoinPlan`,
  `jpFinish`), `batchLevel`'s joined branch, `bJoinAll`, `bProbe`,
  `bJoinTail`, `bLookup`, `bRange` and `batchGroupsIn` (the joins'
  aggregate driver: `pipeAgg`'s Agg over a join arm replaces it).
- **Still blocked after P2:** `outPlan`'s one-table branch (`sortBatches`:
  P3) and `batchLevel`'s `direct` branch (the row engine's first level for
  every query the pipeline does not run: 105 of the suite's tests reach
  it). Making subqueries' own rows, set parts and the statements' queries
  (`pipeSelIn`'s `rows` false) the pipeline's would shrink that list
  without new operators.
- **Costs to watch.** A Gen node that reads an IN subquery copies the
  subqueries' values into its context per run (`copySubs`): free for the
  sets seen so far, linear in a big set. The plan-making glue is ~3% of a
  point select's server time (`pipeSelIn`); it is made per
  simple-protocol statement.
- **Traps.** `BX.Sub` exists only in plan arms: code that binds with
  `bindExpr` never sees one, and `unplan`/`oxBack` must keep turning one
  back into "unbound". `pipeGroups` lends `prepare`'s results to the run
  and puts them back (`subsBack`) after it, also on error. `Scan` carries
  its query's PSubs now (EXPLAIN reads them there). `exec_pipe` compares
  against the row engine: a scan that stops inside a batch (a LIMIT, an
  EXISTS's first row) reads more rows in batches, so EXPLAIN ANALYZE shapes
  must not stop mid-batch.

#### 6.2.9 Point-select planning cost

Measured and cut 2026-11-17 on `redesign/bind` from main fa606bd2.
Scripts and outputs are in `~/tpch-w/bind/pt`. A simple-protocol
statement is planned on every run, and 2e, P1a and P1c each added a
little planning work, each judged against placement noise. This note
measures the total source against source and takes it back.

**Method.** Each source built three times: the default placement,
`LXL_PADB 32 / LXL_FALIGN 128` and `LXL_PADB 16 / LXL_FALIGN 64`
(`bld.sh`). `pts.sh` (2 rounds of 5 runs) and `simple.sh` (2 rounds)
over all the binaries, alternating (`meas.sh`); a source's figure is the
mean of its three placements' means. Beside them, the server's user
instructions per statement over 3 runs of `points.sql` (`icount.sh`,
`perf stat`), which placement does not move (the three placements of one
source agree within 0.15%).

**Source against source** (the second session, `pts-s2.txt`,
`simple-s2.txt`, all four in one run; tps of 4 clients):

| source | pts CPU ms | vs e1 | point select tps | vs e1 | update tps | join tps | instructions | cycles |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| m761 (76118b8a, before 2e) | 643.4 | -3.96% | 51,543 | +5.59% | 9,472 | 21,421 | 199,015 | 103,583 |
| e1 (9aa2c0b2, before the pipeline) | 669.9 | 0 | 48,815 | 0 | 9,485 | 20,356 | 203,091 | 109,234 |
| main fa606bd2 | 675.1 | +0.77% | 49,382 | +1.16% | 9,484 | 20,434 | 206,287 | 110,461 |
| final fd0b6662 | 652.9 | -2.55% | 50,864 | +4.20% | 9,480 | 20,934 | 197,398 | 105,034 |

The first session (`pts-s1.txt`, `simple-s1.txt`, the first three only)
agrees: m761 642.7 ms and 51,438 tps, e1 671.9 and 48,917, main 677.5
(+0.83%) and 49,616 (+1.43%). So 2e cost about 4% of a point select's
server CPU (4,100 instructions, +2.0%; user cycles +5.5%), and P1's glue
another 3,200 instructions (+1.6%), less in time (+0.8%: its run reads a
row more cheaply than the row engine did). The placements of one source still
spread by up to 5% (e1: 651 to 687 ms): that is why a single build
pair could not see this.

**The profile.** `perf record -e instructions:u -c 20000` with frame
pointers (`profpts.sh`, `pi-*.data`; maps `*.map`, `incl.py`,
`subdiff.py`, `callers.py`). Instruction samples skid, so a function's
own count is only good to a few percent (`parseIn`, unchanged, reads 6%
apart between builds); the cuts were judged by `perf stat`'s totals.
What the profile showed per statement, in instructions: the Sel's
logical plan (`selPlan`, `outBCols`) about 1,900, built for a statement's
own SELECT and read by nothing; `pipeSelIn` about 5,300 and `pipeSrc`
4,700 (its `pathScans` 3,000 as before), against a run 5,000 cheaper
than the row engine's (`runQuery`, `prepare`, `outC`); and, older than
both, `select`'s plan-cache version (the catalog's and the statistics'
versions, the role and session user from the memo, the strings joined)
made for a one-shot plan that keeps nothing.

**What was cut** (each commit built and passed the suite):

- dab6d0ad (1/n): a statement's own SELECT builds no logical plan
  (`Scope.noLp`, set by `select`, taken by `planSelect`: `selPlan` is not
  called; FROM and WHERE's plan, which `planFrom` reads, is built as
  before; a subquery's, a view's, a set part's and a statement's query's
  are built, `takeLp` reads them). 206,221 to 203,293 instructions (the
  profile put 1,900 in `selPlan`; the rest is the plan's drop).
- 3e05cad0 (2/n): the plan-cache version (`planVersion`) is made only for
  a kept plan; a one-shot plan reads the catalog's version as before (a
  read the transaction notes). 203,293 to 197,513.
- fd0b6662 (3/n): `oneRow` moves the read row's values into the run's
  row instead of copying them. 197,513 to 197,360.

Not done: a Fetch→Project fast path in `pipeSelIn` (the plan's arrays
and checks are what it makes; `compile` is about 1,200 instructions, and
a second plan shape would be code to keep for under 1%); skipping the
Prog for a plan not kept (the pipeline's run is the cheaper path now).

**Result.** The final build is 2.6% under e1's server CPU and 4.2% over
its point-select tps, 0.8% under m761 in instructions but 1.5% over it
in pts CPU (1.3% under in tps): the same work runs at a lower IPC than
m761's. Update tps is level (DML is not `select`); the 3-table join gains
2.8% (it is planned by `select` too).

**What is left, for later.** `findTable` reads and decodes the table's
catalog entry on every statement (about 17,000 instructions, 8.7% of a
point select); `decTable`'s instructions are the same in every build but its
cycles are not (2.5% of samples in m761's default build, 4.3% in
main's): much of the placement spread is there. A cache of the decoded
table keyed by its stored bytes would take the decoding, not the read.
The pipeline glue left is `pipeSelIn` (about 5,500) and `pipeSrc`'s own
part (about 1,700).

**Gates:** the suite from a snapshot of each commit (`e7/suite-pt1`,
`pt2`, `pt3`): 190 passed, imports ok (214 edges). Naming battery
(`nam-f1.out`) and EXPLAIN of the 22 TPC-H queries (`exp-f1.txt`):
identical to main's. TPC-H SF1, one run of fd0b6662 (`out-f1`): the 22
checksums are the baseline's; total 23,003 to 22,924 ms against
`out-main-fa606bd2` (-0.35%; q1 -5.2%, q16 -3.6%, q20 +3.2%, every other
query within 1.8%).

**Line counts:** `lexdb_exec` 26,481 to 26,503, `lexdb_pipe` 3,055 to
3,056.

#### 6.2.10 P2 as built: joins in the pipeline

Built 2026-11-17 on `redesign/bind` from main 9835e4c0. Scripts and
outputs are in `~/tpch-w/bind/p2` (`qt.sh`, `rep.sh`, `rep2.sh`,
`dbg.sh`, `icount.sh`; profiles `pq*-m`, `pq*-c`; TPC-H runs `out-a2`,
`out-c1`, `out-c3`). The sub-slices were reordered: the lookups and
ranges per row (planned for P2c) came with the hash joins in P2a,
because the batch driver's probe, lookup and range share one tail and
almost every TPC-H join mixes them; P2c became the row engine's joins
and the deletions.

**Commits:**

- 373e1963 (P2a 1/n): inner and LEFT joins over chunks: hashes built in
  batches, lookups and ranges per row, late gathering, the
  required-columns pass, aggregates over joins.
- 0f4f9db4 (P2a 2/n): a FROM subquery's rows by its pipeline plan (q7,
  q8, q9's joins).
- 956041c5 (P2b): semi and anti joins (a RUN_SEMI subquery's rows as a
  hash, RUN_LOOKED as a range per row, the "inner <> outer" summary), a
  FROM subquery's rows as a hash, one RIGHT JOIN; a single row's range past
  `max_statement_mem` read in pieces; generic-step aggregate arguments.
- fdcda546 (P2c 1/n): the row engine's joins run by the pipeline (levels
  programs); the batch join driver deleted.
- aa841ad6 (P2c 2/n): the scan's batch used again under a join; a levels
  program's hashes not built twice.

**The plan** (`lexdb_plan`):

- `PPlan.Join(PPlan, PJoin)`: the rows below joined with one more table.
  `PJoin` holds how its table is read (`JH_HASH` once by its path,
  `JH_ROWS` a subquery's or working table's rows, `JH_LOOK` per row by its
  whole primary key, `JH_RANGE` per row by its path's leading equalities
  and constant bounds), the kind (inner, LEFT, RIGHT), the mark (join,
  semi, anti), its table's arm (`PScan`), the hash's own conditions
  (`build`, Level.local), key columns and keys (`hcols`, `keys`, `ktypes`),
  the conditions per candidate (`conds`, the key's equality `keq` left out
  where the hash compares by value), a LEFT JOIN's WHERE conjuncts
  (`post`), a range's bounds, and a summary's column and outer value.
- `lexdb_plan.needs` is the required-columns pass (6.2.2), next to
  `callsNeed`: each table decodes the columns some operator of the plan
  reads, by slot, so per table instance (a `*` elsewhere widens nothing).
  `compile` runs it for every plan with joins. Above a join only row
  numbers are carried, so "per operator" is what each operator gathers.
- exec's `joinsOver` makes the arms from the levels as the planner chose
  them (the batch driver's choices: a lookup or range per row only where
  the first table's reading does not stop early). The joins' expressions
  are bound for the plan (`planX`); the first table's conditions moved as
  in P1.

**What the pipe does** (`lexdb_pipe`, the joins section):

- **Late materialisation.** A chunk carries per level its rows' places
  (the scan's batch, the hash's rows, a lookup's rows read for the chunk;
  -1 a LEFT JOIN's NULL row). Each operator gathers only what it reads
  (`gatherAt`): a join's keys, then its conditions over the candidates,
  then the consumer's columns once. Nothing is copied from level to level
  but row numbers (`compose`).
- **Late decoding.** With a first hash join of one integer key read from
  the scanned table, the scan's narrowing drops the rows the hash does not
  hold, inside the two-step decode (`lazyOf`'s extra column): their other
  columns are never decoded (q9: 95% of lineitem's decimals).
- **Hashes** are built in batches by the pipe (`Builder`): the table read
  by its path with its own conditions compiled once, buckets as first/next
  chains in read order, NULL keys out (a RIGHT JOIN's kept), integer and
  text keys by value, others by their encoding (`encIdxPart` after
  `keyVal`'s coercion; a subquery's rows by `keyPart`). No `materialize`.
- **Lookups and ranges** are bLookup's and bRange's (`fetchMany`,
  `rangeMany`), keyed from the gathered keys; a chunk whose ranges are
  past `max_statement_mem` is joined in halves, a single row's range is
  read in pieces (`rangeOne`, as the row engine reads it).
- **Semi, anti, RIGHT:** a semi join gives each outer row once (its first
  passing candidate), an anti join the rows with none; both count
  candidates read as the row engine does (up to the first passing one);
  a RIGHT JOIN's rows that joined nothing go on after the scan with NULLs
  before them.
- **Errors** (exactness): an expression's error in a chunk joins the
  chunk again row by row (`one` mode: each row's candidates in order, as
  `runLevel` tries them), skipping the rows already given, so an error past
  a LIMIT is not reached and the rows before an error are the row
  engine's. A condition's error in the scan's batch gives the batch whole
  to the same row-by-row join. Aggregates raise from the chunk (4.4.1).
- **XXBAT** ("a value or key a join's batch cannot hold": a key the
  kernels do not compile, a value of the wrong kind) is raised before any
  row is given where the caller holds them; exec then runs the row engine
  (execSelTo, eachRowB when nothing was streamed, pipeGroups, runQuery).
- **Consumers:** `runJ` (Project over joins: OutBatches, a LIMIT),
  `runAggJ` (P1b's aggregate, its state now `AggSt` shared with one
  table's: units, then values, then the joined rows grouped by the scalar
  evaluator), `runLevels` (each joined row to the row engine's emit).
- **Generic aggregate arguments:** a sum, min or max whose argument the
  kernels do not evaluate takes its values by the generic step (a values
  column per batch, `bAccVal`) instead of the row pass (q14's CASE of a
  LIKE; `exec_batchdec`'s "negated past units" now over batches).

**What compile accepts:**

- Project (streamed or held rows, a LIMIT) and Agg over a join tree whose
  first table is read in batches (`PScan.batch`; its points row by row),
  its subqueries run once, RUN_SEMI or RUN_LOOKED;
- levels: inner, CROSS and LEFT joins by a hash of a table or of rows, a
  lookup or a range per row; semi and anti joins by a hash of a
  subquery's rows (with a summary) or a range per row; one RIGHT JOIN by a
  hash; a FROM subquery's or a recursive CTE's working table's rows as a
  hash; keys of no collation;
- for the row engine (levels programs, `Query.jp`): the same joins under
  any query the pipeline does not run whole (sorted, DISTINCT, windows,
  set parts, statements' queries, aggregates it does not accumulate).

**It rejects** (the row engine runs them): FULL joins; LATERAL; locked
tables; a correlated query (`q.corr`, or a correlated path); a per-row
level that is neither a whole-key lookup nor a range (a nested loop, an
IN list per row); a lookup or range under a LIMIT that stops the scan; a
collation's key; a first table that is a subquery's rows or not read in
batches; generate_series in FROM.

**Deleted from exec** (fdcda546): `eachOut`; `outPlan`'s and
`batchLevel`'s joined branches; `sortBatches`' joins; `bJoinPlan`,
`jpFinish`, `bJoinAll`, `bProbe`, `bJoinTail`, `bLookup`, `bRange`,
`bUnmatched`, `bGather`, `bJoined`, `JLevel`, `JPlan`, `noJoins`;
`batchGroups`, `batchGroupsIn` (`pipeAgg`'s Agg over a join arm replaces
it); `bCompileCond`, `bCompileX`, `bChoose`, `copyCounts`. A query's
joins have one implementation now, the pipe's. Kept in exec: the path
tests the planner's choice needs (`lookupPath`, `rangePath`, `isKeyEq`,
`bCondNode` for the first level's one-table batches).

**Line counts:**

| | main 9835e4c0 | 373e1963 | 0f4f9db4 | 956041c5 | fdcda546 | aa841ad6 |
|---|---:|---:|---:|---:|---:|---:|
| `lexdb_exec` | 26,503 | 26,705 | 26,706 | 26,757 | 25,304 | 25,312 |
| `lexdb_pipe` | 3,056 | 4,565 | 4,565 | 4,954 | 5,039 | 5,055 |
| `lexdb_plan` | 320 | 446 | 446 | 461 | 461 | 461 |

Exec is 1,191 lines shorter: the secret that left it is how a join runs
(the batch join driver, 1,450 lines, and its aggregate driver); exec
gained the glue (`joinsOver` 120, `joinSrcs`, `levelCounts`,
`levelsProg`, `runLevelsProg`, the fallbacks: ~260). The pipe gained
2,000 (the joins ~1,500, the shared aggregate state, the levels program);
the plan 141 (`PJoin`, `needs`). No new import edge (214).

**Gates:**

- Suite from a snapshot of each commit (`e7/suite-p2a1`, `p2b`, `p2c1`,
  `p2c2`; 2/n's in the working tree): 190 passed, imports ok. Counters
  that moved, with the same rows: `exec_batchexpr` OutBatches 286 to 290
  and `exec_batchjoin` batched joins 206 to 208 (joins past an error now
  batched), `exec_semijoin` 167 to 189 over batches, `exec_joinrange` 14
  to 15, `exec_batchdec` "negated past units" over batches; and two that
  went down because sorted joins are no longer sorted as OutBatches
  (`sortBatches` is one table's until P3): `exec_batchsort` 198 to 155,
  `exec_batchindex` 164 to 134.
- `exec_pipe` gained joins, two ways (row engine and pipeline): 400
  random joins committed and 100 in a transaction with its own writes
  (inner, LEFT, hash, lookup, range, three tables, two keys, expression
  keys, text keys, duplicate and NULL keys, an empty table, rows and
  aggregates, errors), 26 fixed shapes (errors before and past a LIMIT
  in a join's condition, an output, a call; empty build and probe; a LEFT
  JOIN's WHERE), 12 runs of a prepared join, `max_statement_mem` (the
  same 53200, the same rows under it), 10 EXPLAIN ANALYZE shapes; then
  300 random semi and anti joins (EXISTS, NOT EXISTS, IN, NOT IN with
  NULLs in the set and an empty set, a range per row with a filter, the
  summary), 12 fixed semi, anti and RIGHT shapes, 6 EXPLAIN ANALYZE
  shapes: all the same. (Its run takes 12 s: `timeout: 120`.)
- Naming battery (`nam-a1.out`, `nam-c1.out`) and EXPLAIN of the 22 TPC-H
  queries (`exp-a1.txt`, `exp-c1.txt`): identical to main's.
- Point selects (`icount.sh`, `perf stat` over 3 runs of `points.sql`,
  two rounds): main 197,338 and 197,404 instructions a statement,
  aa841ad6 197,857 and 197,890 (+0.26%; cycles 105,561 to 103,852).
- TPC-H, SF1, one run of each build; all 22 checksums are the baseline's
  (1744ef99). Against `out-main-9835e4c0` (ms):

  | query | main | 0f4f9db4 (P2a) | fdcda546 | aa841ad6 | change |
  |---|---:|---:|---:|---:|---:|
  | q3 | 1,338 | 968 | 957 | 966 | -27.8% |
  | q5 | 401 | 246 | 249 | 254 | -36.7% |
  | q7 | 1,907 | 1,758 | 1,776 | 1,533 | -19.6% |
  | q9 | 5,026 | 3,106 | 3,041 | 2,888 | -42.5% |
  | q10 | 1,163 | 590 | 587 | 597 | -48.7% |
  | q11 | 215 | 167 | 168 | 172 | -19.8% |
  | q12 | 1,502 | 1,635 | 1,605 | 1,358 | -9.6% |
  | q13 | 1,120 | 1,108 | 771 | 777 | -30.6% |
  | q14 | 788 | 380 | 339 | 338 | -57.0% |
  | q16 | 581 | 569 | 354 | 358 | -38.3% |
  | q21 | 1,940 | 1,956 | 1,925 | 1,796 | -7.4% |
  | q22 | 445 | 442 | 334 | 334 | -25.1% |
  | q2, q4, q8 | 64, 354, 363 | | | 59, 339, 355 | -8%, -4%, -2% |
  | total | 22,924 | 19,593 | 18,663 | 18,000 | -21.5% |

  Worse in the last run: q1 +3.7%, q17 +15.8% (44 to 51 ms), q18 +3.0%,
  q6 +2.1%. Repeated on copies through the harness (`rep2.sh`, 3 runs a
  pass, two passes): q17 44.7 and 44.5 against 44.7 and 45.9 (level), q18
  1,220 and 1,225 against 1,210 and 1,215 (+0.9%), q1 2,492 and 2,418
  against 2,363 and 2,402 (+3.0%); q1 again at `LXL_PADB 32 / LXL_FALIGN
  128` (`rep2p.txt`): 2,451 and 2,456 against 2,414 and 2,420 (+1.5%).
  q1 runs no join; its code changed only by the aggregate state's move
  into `AggSt` (its grouping loop reads the state through a borrow). Within
  the 4% placement spread of 6.2.7, but consistently 1.5-3% slower: not
  resolved.
  - q12 was +6.8% at fdcda546: the join's scan moved each batch into its
    consumer, so `lexdb_rows.reuse` allocated a new one per batch
    (`newBatch` 15% of the profile, `pq12-c`); aa841ad6 lends it and takes
    it back. q20 was +3.3%: its sorted outer query's supplier lookups were
    read twice (prepare's `materialize` and the levels program's hash);
    aa841ad6 skips materialize for a levels program (`rep-q20b.txt`: level).

**Where the remaining join time goes** (profiles at P2a): q9 is now 30%
`fetchMany` (325k lookups each of partsupp, supplier, orders: the plan's
choice; PostgreSQL hashes them), q3 77% `rangeMany` (orders by customer,
lineitem by order, per row), q14 60% the build's index range read row by
row by primary key (`getMany`; PostgreSQL's bitmap scan), q7 the lookups
and dates compared as values (`lexdb_ops.compare` 8%). The next gains are
the planner's (hash instead of lookups where the probe side is large) and
the chunk's (dates as integers), not the join operators'.

**Hand-over:**

- **P3 (Sort, TopN, Distinct over chunks)** now also owns sorted joins:
  `sortBatches` is one table's, so ORDER BY over a join sorts the levels
  program's rows in exec's row sort (`exec_batchsort`'s OutBatches went
  down). A Sort operator over `runJ`'s chunks would take them back.
- **Levels programs** (`Query.jp`) are the row engine's joins now; they
  disappear when the row engine's consumers (sort, DISTINCT, windows, set
  parts, statements' queries) are pipeline operators. Their glue
  (`runLevelsProg`) copies the subqueries' values and rows per run.
- **XXBAT** is the only give-way left. A key the kernels do not compile
  could take the generic step (`bGenOf`'s values, keyed by encoding)
  instead; a value of the wrong kind for its column could make that
  chunk's column BK_VAL (6.2.3's table). The fallbacks (execSelTo,
  eachRowB, pipeGroups, runQuery) go with them.
- **Not taken:** FULL joins; a per-row level other than a whole-key lookup
  or a range (nested loops, IN lists per row: the planner's
  `loop over primary key lookup` lines); LATERAL; correlated queries
  (RUN_HASHED as a build side was not built: its per-key values feed
  expressions, not a level); the first table read from a subquery's rows
  (q7, q8, q9's outer aggregates over their FROM subquery still run in the
  row engine: a Scan of rows would take them).
- **Costs to watch:** the memory a hash holds is now its kept rows'
  (`Builder.held`), not every row read (`materialize` counted those): a
  statement near `max_statement_mem` may now pass where it failed. A
  levels program holds its hashes in its run, prepare none.
- **Traps:** `readRows` lends its batch to the consumer (`mut &Batch`) and
  takes it back for `reuse`: a consumer must leave the table's columns as
  they were. `joinFrom`'s `one` mode and `Skip` must stay in step (the
  rows given before an error are skipped by count). `opLines` prints a
  Join arm as nothing: the Scan's `explainLines` prints every level.
  `pipeGroups` must read its path's values before lending the subqueries'
  values (`pipeCtx`), or a path bound by a subquery is empty.

#### 6.2.11 E2 as built: the statistics in `lexdb_stats`

Built 2026-11-17 on `redesign/bind` from main f42569c2 (1eb8a6e3). Scripts
and outputs are in `~/tpch-w/bind/st2`.

**What moved** (unchanged but for the interface) into `lexdb_stats`
(layer 5; 1,164 lines):

- the estimates the planner reads: `Est`, `Common`, `COMMON_MAX`,
  `rowsFor`, `commonOf`, `entriesOf`, `rowsOf`, `noEst`, `noCommon` (from
  `lexdb_plan`), and the samples' share of a range, now
  `Est.sampShare(e, ...)` (exec's `parseSamp(...).rangeShare(...)`);
- the statistics' row and version: `statKey`, `toHex`, `STAT_VERSION`,
  `statVersion`, `moveStats`, `loadEst`;
- ANALYZE's counting: `analyzeTable`, the samples (`Samp`, `Sampler`,
  `mapSamples`, `sortTakingTurns`, `sampText`, `parseSamp`), the KMV
  sketch, `keepCommon`, `spanNum`, `spanText`;
- the automatic statistics and their state: the `CHG_*` and
  `AUTO_STATE` globals, `noteChg`, `noteChgN`, `chgFlush`, `chgEnd`, the
  memo's counts and states (`acCounts`, `acState`, `acDone`, ...),
  `statRows`, `autoLook`, `autoOne`, `autoAnalyzeStep`, `autoAnalyzer`,
  `setAutoAnalyze`.

**The interface** (28 public names):

- `Up { idxVal, inIndex, decTable }`, a value record of functions as
  `lexdb_pipe.Up`: what needs exec's evaluator (an index expression's
  value, a partial index's predicate) and the parser (a catalog row's
  expressions). Exec's is `statsUp()`.
- The session's settings come as arguments, so the module reads no
  `Txn.sql`: `loadEst(st, txn, t, join, rules)`, `noteChg(st, sess, t,
  kind)`, `noteChgN(st, sess, t, n)`, `analyze(st, txn, tabs, deadline,
  up)` (the statement's `Limits` were read for the deadline only).
- The planner reads estimates through `loadEst` and `Est`'s methods
  (`rowsFor`, `commonOf`, `entriesOf`, `sampShare`) and `spanNum` for a
  literal; DML reports through `noteChg`, `noteChgN`, `chgEnd`; DDL
  through `moveStats`, `dropStats`; the plan cache reads `statVersion`;
  `pg_stat_user_tables` takes `tabStat(st, txn, t)` (a
  `lexdb_catalog.TabStat`).
- ANALYZE the statement stays in exec (layer 7, E4): `maint`, the
  tables by name (`findTable`, `catScan`), then `lexdb_stats.analyze`,
  `tmpBump` for a temporary table, `lexdb_stats.bumpVersion` for a
  permanent one, in the old order.
- `autoAnalyzer` and `autoAnalyzeStep` stay in exec as one-line adapters
  that add `statsUp()`: `lexdb.lxl` starts the task and the test calls the
  step by those names.

**Moved down instead of hooked:** `tempRel` and `nextVersion` (with
`VERSION_BUMPS`) to `lexdb_catalog` (a relation key's kind; the catalog's
and the statistics' versions; `dependentViews`' inline copy of `tempRel`
now calls it); `TURN_NS` to `lexdb_base` (the pipe's budget and ANALYZE
take turns by it). Exec's `fetch` adapter is not needed: `analyzeTable`
calls `lexdb_access.fetch` on `relOf(t)`, as the adapter did. The one
`fmax` became its expression (`r` is never NaN there).

**Deleted:** exec's stale comments of the estimates (left by an earlier
move), `lexdb_plan`'s `lexdb_catalog` import (unused once `Est` left),
exec's `hash` and `os` imports.

**Imports:** `lexdb_stats` imports `lexdb_base`, `lexdb_sql`,
`lexdb_time`, `lexdb_float`, `lexdb_ops`, `lexdb_store`,
`lexdb_catalog`, `lexdb_access`; `lexdb_plan` and `lexdb_exec` import it.
`imports.py` checks that list, the two users and no `.sql.`: 214 edges
to 223. `lexdb_plan` above `lexdb_stats` keeps E5 open: the planner can
move into `lexdb_plan` and call `loadEst` without a cycle.

**Line counts:**

| | main f42569c2 | E2 |
|---|---:|---:|
| `lexdb_exec` | 25,312 | 24,271 |
| `lexdb_stats` | | 1,164 |
| `lexdb_plan` | 461 | 394 |
| `lexdb_catalog` | 1,351 | 1,374 |
| `lexdb_base` | 119 | 124 |
| `lexdb_pipe` | 5,055 | 5,050 |

So 1,041 lines left exec (6.2 estimated ~1,000).

**Gates:**

- Suite: 190 passed, imports ok (47 modules, 223 edges).
- Naming battery and the 22 TPC-H EXPLAINs: identical to main's build
  (`p2/lexdb-c3`) (`nam-*.out`, `exp-*.txt`).
- TPC-H, SF1: the 22 checksums are main's (and the baseline's, 1744ef99;
  q1, q8 and q17 differ in text as on main). The one run (`out-e2`)
  against `out-main-f42569c2`: total 17,999.6 to 18,458.9 ms (+2.6%), q13
  +29%, q20 +11%, q14 +7%, q19 +6%, q3 +3%. Another session's compiler
  gates ran without the bench lock during these runs (up to 12 `lxlc`
  processes), so they were repeated on copies of both binaries:
  - `rep2.sh` (those five, 3 runs, two passes) twice: level within each
    pass, but passes moved 20-60% with the other load (`rep2-first`,
    `rep2-second`);
  - `full2.sh` (the 22, one run each, main E2 E2 main), the least of two
    per query (`full-min.txt`): total 17,946 main, 17,653 E2 (-1.6%); no
    query more than 3% slower (q19 +1.7%); q13 775 and 747.
  - Nothing E2 changed runs in a query: planning calls `loadEst` across
    a module, and DML `noteChg`.
- Point selects (`icount.sh`, 3 runs of `points.sql`, two rounds): main
  200,151 and 199,256 instructions a statement, E2 200,169 and 198,156
  (-0.3%).

**Hand-over:**

- E3 (the binder leftovers into `lexdb_bind`) was not started: it is not
  low risk. `bindFrom` fills `Query`'s levels and plans FROM's subqueries
  and views (`planSub`, `SubPlan`), and `Scope` carries the planner's
  state (`looks`, `early`, `locking`, `ordBy`, `noRefKeys`, `noLp`) and
  the privilege checks (`scCheck` reads the session's role, `whoIs`).
  Before it moves: split `Scope` into the binder's names (`Names`, already
  `lexdb_bind`'s) and the planner's flags; pass the catalog snapshot and
  the role in; keep `bindFrom`'s planning of subqueries as a callback.
  The small leaves (`srfCols`, `colIndex`, `exprScale`, `collectAggs`,
  `setSubst`, `hasAgg`, `boundType`, `immutable`) can go first, one commit.
- ANALYZE the statement and the two autoanalyze adapters leave with E4
  (statements). `lexdb_stats.Up.decTable` is exec's `decTable`
  (`lexdb_catalog.decTable` with `lexdb_parse.parseExpr`); if the catalog
  takes the parser as its own hook later, it can drop out of `Up`.
- `Est`'s fields are public: the planner reads `rows`, `trees`, `cm`,
  `cols`, `cnd`, `lo`, `hi`, `span` directly. Narrowing that is E5's,
  with the planner's move.

#### 6.2.12 P3 as built: Sort, top-N and DISTINCT in the pipeline

Built 2026-11-18 on `redesign/bind` from main f0dddc5e. Scripts and
outputs are in the session scratchpad's `p3/` (`qc.sh`: per statement,
the server's instructions and the output's md5).

**Commits:**

- 25aeed14 (P3a): the sort keys move unchanged into a new module,
  `lexdb_sort` (412 lines): `SKey`, `skSort` and its helpers (from exec),
  `sortCmp` (from the pipe), `collVal` (from exec). The pipe's Sort and
  the row engine's sorts and windows share them. `imports.py`: it imports
  values, their operations and encodings only (`lexdb_sql`, `lexdb_ops`,
  `lexdb_vec`, `lexdb_access`); only the pipe and exec import it.
- 783e3c1e (P3b and P3c): the operator, the plan's keys, the deletions,
  and the top-N bar.

**The plan** (`lexdb_plan`):

- `Sort(PPlan, bool, Option[PSort])`: a sort the pipeline runs holds its
  keys (`PSort`: per key the Project's column it reads, DESC, NULLS
  FIRST, its collation's kind; `shown`, the outputs given). `None` in a
  view (physOf's).
- `Distinct(PPlan, bool, []int)`: the outputs' collation kinds (`[]` in a
  view).
- exec's `pipeSelMain` makes `Limit? (Sort? (Distinct? (Project (...))))`
  as `physAbove` makes them, so EXPLAIN prints the same lines. An ORDER BY
  key that is an output (by position or name: `orderOut`) reads it; any
  other is bound for the plan (`planX`) and made by the Project after the
  outputs (a "hidden" column the Sort does not give). `sortShape` is the
  accept check: no grouping, window, set operation, lock, DISTINCT ON,
  WITH TIES, TOP, SELECT @v, function returning rows, or correlated
  output or key.

**What the pipe does** (`lexdb_pipe`, the section "ORDER BY, top-N and
DISTINCT over chunks"): the Sort sits over the Project's output, so the
scan, the joins and the Project are unchanged. Its state (`SortSt`) takes
each chunk (`eat`: an OutBatch, or a row read one by one) into typed
columns (`SortSet`), keeps a bounded heap for ORDER BY with LIMIT, a set
of seen outputs for DISTINCT (`DistSet`, made only for a DISTINCT), stops
the scan for DISTINCT with LIMIT and no ORDER BY, and at the end sorts by
the typed keys and gives the rows kept as one OutBatch (`finish`), their
bytes held in the budget. It is `sortBatches`' logic, now fed by any
Project the pipe runs, so it serves:

- one table, in batches or row by row (point lookups, a range's keys
  read first): the row path is no longer a give-way;
- joins (`runJ`'s chunks): ORDER BY and DISTINCT over joins are the
  pipeline's again (P2 had sent them to the row engine's sort);
- the top-N bar (P3c, 9.108): for ORDER BY with LIMIT whose first key is
  an integer column of the first table, the scan decodes that column first
  and drops the rows the heap's last row beats before decoding the rest.
  The sort's state is passed down the one-table scan (`runOp`, `runScan`,
  `rowsFrom`, `oneRow` take a `SortRun`: one state, or none when the rows
  stream), so the scan reads the bar per batch; joins feed the sort
  through their callback (no bar).

A column's kind is its first input's (a row read one by one: values).
Keys of values of mixed kinds, or a DISTINCT text output that is not a
text, end the run in `batErr` before any row is given, and exec runs the
row engine, as `sortBatches` gave way.

**Exec:** `pipeHeld` does not count a sorted program's rows again (the
Sort held them); `runSelTo` streams a sorted program's one OutBatch to the
client's sink (asked once; refused, the rows are held), and falls back to
`runSel` on `batErr`.

**Deleted from exec:** `sortBatches`, `SortSet`, `ssKeys`, `ssOuts`,
`bCell`, `cellVal`, the heap (`hCmp`, `hUp`, `hDown`), `sortSinks`,
`outPlan`, `OutPlan`, `outNodeX`, `outNodeOut`; `execSelTo`'s sink
parameters (it is `execSelIn`). The batch engine's sort is the pipe's now.

**Line counts:**

| | main f0dddc5e | P3a | P3b+c |
|---|---:|---:|---:|
| `lexdb_exec` | 24,315 | 23,929 | 23,474 |
| `lexdb_pipe` | 5,087 | 5,074 | 5,645 |
| `lexdb_sort` | | 412 | 412 |
| `lexdb_plan` | 394 | 394 | 410 |

841 lines left exec (6.2.3 estimated ~550 for `batch.sort` and the rest
of `batch.out`; the sort keys' module is the difference). The secrets
that left it: how rows are put in order (`lexdb_sort`), and how a sort,
top-N and DISTINCT run over batches (the pipe).

**Gates:**

- Suite: 190 passed, imports ok (48 modules, 229 edges), at P3a and at
  the end. Two counters moved up, as intended: `exec_batchsort` "given as
  an OutBatch" 155 to 198 of 400 (P2's 198 again: sorted joins), and
  `exec_batchindex` 134 to 171 (164 before P2). Every query the same three
  ways; the counts of a sort, a top-N and a DISTINCT stopped by its LIMIT
  the row path's.
- TPC-H, SF1: the 22 results are main's (md5 of each output); instructions
  -0.01% (its sorts are over grouped output: unchanged).
- 16 sort statements over the TPC-H data (`qc.sh`), against main: all
  the same results; a sorted join -40%, top-N by an integer column not in
  the scan's order -43% (before the bar: +257%, so P3c is needed), DISTINCT
  over two columns -6%, top-N by a numeric -8.5%, the rest within 1%
  (two read an index in order and do not sort).
- Point selects (`icount.sh`, three rounds): instructions +0.12% (187.4k
  to 187.6k a statement); cycles +1.5% to 2.2%, P3a alone +0.0% to 0.9%;
  with `LXL_PADB 32 / LXL_FALIGN 128` +1.2% to 2.0%. A cycles profile of
  both shows no function changed (5,757 against 5,776 samples). Not
  resolved: an empty `SortRun` per run and the plan's larger arms are what
  a point select pays. An earlier form that made two empty maps per run
  cost +1.1% instructions.

**Hand-over:**

- Not taken: DISTINCT ON, WITH TIES, TOP (PERCENT), the sort of a set
  operation's rows, of grouped rows (the views over an aggregate's groups
  are still exec's), of windowed rows. A Sort over the Agg's groups is the
  next step for these (TPC-H's final sorts).
- The bar is one table's: a top-N over joins sorts every joined row.
- `runSelTo` streams a sort's rows as one OutBatch; a large sort's output
  could go in pieces.

#### 6.2.13 After P3: three measured fixes

Built 2026-11-18 on `redesign/bind` from main 96e2663f, each chosen from a
profile of the 22 TPC-H queries and their ratios to PostgreSQL one core.

- **48c22c45, q22 (-46% instructions).** `x IN (constants)` whose `x` is
  not a column but an expression (`substring(c_phone from 1 for 2)`) was
  wholly the generic step: per row, the list's seven texts copied and
  compared. `BNode.InGen` makes `x` by the generic step once per row and
  looks it up in the list sorted; a value of another kind than the list's
  is compared with the list in order, as `lexdb_lib.inFn` does (errors and
  NULLs as the row path's). `substring` cuts an ASCII text by bytes and
  reads its arguments where they are (`lexdb_sql.text` copies since
  strings are owned; `lexdb_sql.textIn(v, buf)` is the view form).
- **0b7624eb, numerics read as values (-1.0%; q7 -5%).** `Decimal.fromUnits`
  (lib/decimal) builds a 64-bit value directly instead of through the
  256-bit path and a `Result`.
- **89cf0a59, a hash cut by the next level's hash (q7 -20%, q21 -17%).**
  q7 and q21 hash all of `supplier`, then join `nation` on `s_nationkey`
  with a hash of one or two nations: 1.83M (3.79M) lineitem rows passed the
  supplier join for 146k (157k) to survive nation. After the hashes are
  built, `reduceHashes` unlinks a hash's rows whose key column the next
  level's inner integer-keyed hash does not hold; the scan's narrowing by
  the first hash's keys (P2's late decoding) then drops those lineitem
  rows before decoding their other columns. Only between adjacent levels
  joined by plain columns with no condition per candidate (exactness: no
  row whose condition would raise an error is skipped). The rows cut are
  counted per bucket and added back where a probe or the narrowing meets
  them, so EXPLAIN ANALYZE's counts stay the row engine's (`exec_pipe`,
  `exec_semilook` compare them). Open: q13 +0.75% instructions with no
  cut.

TPC-H at 89cf0a59 (lexdb-benchmarks.md 1.6): summed 13.52 s against
PostgreSQL's 13.96 s on one core, geometric mean 1.03. Point selects
level (instructions), cycles 1.5% to 2.7% lower than at 48c22c45.

- **a71052de, an index's ranges per key in one pass (-0.44%; q3 -3.3%, q4
  -3.1%, q5 -4.8%).** `Store.scanRanges`: rangeMany's ranges, sorted, under
  one lock, each leaf found from the last one's path (a Finger, as
  getManyIn's keys) instead of a descent from the root with its bounds
  copied per range; a range crossing its leaf's fence or meeting the
  transaction's own writes or cuts, a replica's view, or noted reads: by
  scanLeaves as before. Smaller than hoped: a chunk's keys are sparse
  (about a thousand orders over 6M lineitem rows), so the ranges rarely
  share a leaf, and the cost left is the search itself (below).

**q20 and q11, profiled (2026-11-18).** Both are index lookups whose rows
are then fetched by primary key (`rowsOfKeys`, `getManyIn`: 48% of q20,
40% of q11), where PostgreSQL fetches by tuple id. q20 also pays its
correlated subquery's setup per run (8,508 runs: the aggregate's state,
batches and kernels compiled again; malloc and free 13.5%): an Apply that
prepares once and runs per row (6.2.3's hand-over) is the fix. q11 runs
the same join twice (the HAVING's subquery), as PostgreSQL does. Across
q3, q11, q20 the B-tree search is the rest: the in-leaf binary search
(`Node.lower`) and descents compare keys through `rt_str_cmp`, which
always calls `memcmp`; most keys are 8 to 16 bytes, so a runtime fast path
(the first 8 bytes compared as a byte-swapped integer) would serve every
string comparison. That is the language runtime's (rt.h, native/rt.c).

The largest ratios left: q19 2.6× (plan: PostgreSQL drives from part by a
BitmapOr; the parked orHull), q20 2.3×, q11 2.1×, q22 1.9×; the largest
absolute gaps q21 (+406 ms), q7 (+357), q3 (+304), q15 (+272), q12 (+240).

### 6.3 After the batch and dialect work: the queue (2026-11-20)

Written at main 9cfcbe8e, after design/lexdb-batch-gaps.md (all twelve
items merged) and design/lexdb-dialect-gaps.md (packages A-E, F1-F2 merged;
F3 running). The owner is away and asked the coordinator to drive this in
an order of its choosing, with these rules (owner, 2026-11-20):

- **Optimizer and planner changes: one Opus subagent at a time** ("this is
  hard stuff"). Mechanical work (the bisect, dialect follow-ups) may use a
  Sonnet agent alongside it: at most one Opus and one Sonnet at once.
- **Step 7 (parallel pipelines) is on hold** until the owner is back: take
  everything as far as it goes sequentially first (par.map is an option to
  discuss then, not now).
- Gates as before: the suite; TPC-H once per merge alternated with the
  previous main (the machine drifts), 22 checksums equal; point selects must
  not get slower (instructions per statement, A/B, any real increase fixed
  before merging); every slice reports lexdb_exec's line count.

State at the start (from lexdb-optimizer.md and this note): the cost-based
planner of lexdb-optimizer.md 18-46 is built and on main (switch, ANALYZE
and automatic statistics, stat4 samples, per-parameter plans, cost join
order with SQLite's bounded search to 24 tables, implied equalities, LEFT
and semi joins by cost, measured read costs, `SET lexdb_planner`); step 4
is far along (P1-P3 and the batch gaps); TPC-H on 2026-11-18 was level
with PostgreSQL on one core (geomean 0.98). Not built: bushy joins,
a row-id-ordered (bitmap-style) index read, predicate pushdown into
derived tables, outer-to-inner join conversion, unnesting (step 5),
retiring the row engine, step 7.

The queue, in order:

| # | What | Who | Why now |
|---|---|---|---|
| Q1 | Bisect the q1 (+14%) / q21 (+11%) regression between aaadeb1e and 39451078 | Sonnet | every later TPC-H comparison stands on it |
| Q2 | Virtual columns computed on read (dialect-gaps open decision, section 8 there) | Sonnet | the coordinator's recommendation, taken as the owner did not choose. Built (branch `worktree-agent-a6cb66b9db918f762`, suite 244 of 244): dialect-gaps.md section 8, "Q2" |
| Q3 | Exec extraction: the planner and cost model into lexdb_plan (2e slice 3d), and the glue the dialect packages added (routines, privileges, doors) out of exec | Opus | the module goal; makes Q4-Q7 easier to do in isolation |
| Q4 | A row-id-ordered index read for middling selectivities (PostgreSQL's bitmap heap scan): collect the matching primary keys from the index, sort, read the rows in key order; by cost | Opus | q4, q14, q19: the largest plan-shape gap left in TPC-H |
| Q5 | Rewrites that keep results: predicate pushdown into derived tables and views; outer-to-inner join conversion when WHERE rejects the NULL rows | Opus | app workloads; pairs with batch-gaps item 6 (views in batches) |
| Q6 | Bushy join search (step 6) | Opus | q21's (supplier, nation) hash |
| Q7 | Step 5, unnesting for generality: null-aware anti join, mark join; correlated subqueries in batches (batch-gaps section 8 item 4) | Opus | the last per-row machinery |
| Q8 | Retire the row engine where the pipeline covers everything (step 4's end), behind the OLTP gate | Opus | decision 1 of section 8; before step 7 |
| -- | Step 7, parallel pipelines | on hold | the owner decides |

Each Opus item starts with a design section of its own (here or in
lexdb-optimizer.md), then slices, each merged with the gates. A TPC-H run
against PostgreSQL (one core and four processes, lexdb-benchmarks.md) is
recorded after Q1 and again after Q4-Q6.

#### Q1 bisect result (2026-11-20)

**There is no code regression of 14%: the two binaries were built with
different compiler flags.** `~/tpch-w/bind/os/lexdb-aaadeb1e` (built 18 Nov)
is `lxlc lexdb.lxl -O`; `~/tpch-w/bind/os/lexdb-39451078` (and every binary
from 20 Nov) is `lxlc lexdb.lxl -o ...` with no `-O` (what
`bench/tpch/README.md` and `cmd/README.md` say to type). Rebuilt here from
each commit's own compiler (gcc build of its seed; the rebuilt `-O` good
binary is byte-identical to the stored one, the rebuilt no-`-O` bad binary
to the stored bad one), then alternated in one session on the same data
(`TPCH_QUERIES=q1,q21`, 1 run each, 3 rounds, medians, ms; checksums equal
in every run):

| build | q1 | q21 |
|---|---:|---:|
| aaadeb1e `-O` | 1,696 | 1,107 |
| aaadeb1e no `-O` | 1,961 | 1,162 |
| 39451078 `-O` | 1,725 | 1,132 |
| 39451078 no `-O` | 1,971 | 1,190 |

Like for like the gap is q1 +1.7% / +0.5% (`-O` / not) and q21 +2.2% / +2.4%;
the `-O` flag alone is worth 13-14% on q1 and 5% on q21. A q1 profile
(perf, `LXL_NATIVE_MAP` symbol map; 7,121 samples with `-O`, 7,972 without)
puts the `-O` gain in the loop and load-reuse passes (`bEval` 950 to 652
samples, `vec_arith` 466 to 284, `rows_bvec` 288 to 63, `vec_sum` 759 to
625, `encKeyPart`, `sipKeyedStr`); the same `-O` builds of aaadeb1e and
39451078 have 7,121 and 7,032 samples, with the same functions in the same
order (only inlining of `encKeyPart` into `bKeyEnc` moves samples).

The residual `-O` drift over the candidate commits (medians of 3 alternated
rounds, `-O`, ms; q1 / q21; noise per build about 1%, code placement up to
2-4% on q7):

| commit | q1 | q21 |
|---|---:|---:|
| aaadeb1e | 1,675 | 1,167 |
| eababf57 | 1,707 (+1.9%) | 1,201 (+2.9%) |
| f387f7f0 | 1,687 | 1,201 |
| d0f00b92 | 1,700 | 1,208 (+3.5%) |
| 800ff80b | 1,690 | 1,201 |
| 448b8bef | 1,694 | 1,189 |
| 2c0df08b | 1,683 | 1,197 |
| 5c42570d | 1,690 | 1,202 |
| dbee498f | 1,702 | 1,202 |
| 39451078 | 1,702 (+1.6%) | 1,217 (+4.3%) |

q21 steps up once, at eababf57 (the leaf's keys as one counted array; q21
samples +1.3%, spread over `colsPick`, `Node.lower`, `drop`, `malloc`, no
single hotspot), and later commits add nothing measurable; q1 is flat
within code placement. The decimal, bfold, cse, x64gen and runtime commits
are not culprits. q7 +2-3% and q12 +0.5% (not +9% and +8%) at the same
steps. Consequences: build every TPC-H binary the same way (decide `-O` or
not once, and write it in `bench/tpch/README.md`; the `-O` build is the
faster one and the one the 18 Nov numbers used), and compare only
binaries built with the same flags. The 20 Nov series of `~/tpch-w/bind/os`
binaries (q1 near 1,950 ms) is probably all built without `-O` (only
39451078's was checked byte for byte), so it is not comparable with the
18 Nov record (q1 near 1,690). The q18 -21% and q10 -7% "gains" of the same
pair were not examined here.

#Q3 merged as 95b9968d (2026-11-20): suite 236; TPC-H 1.003 of 0f96fee9 alternated, both built with
`-O`, checksums equal; point selects level (the agent's A/B, -0.05% to +0.02%).

Q2 merged as a85d6a02 (2026-11-20): virtual columns computed on read; suite 244; TPC-H 1.023 of bc0c6a21
alternated, server instructions equal within 0.01% on q20, q13, q3 (placement); point selects +0.07%, INSERT level.
Open: a column alias list on a table with virtual columns breaks their expressions; its new Oracle
answers were written by hand; the T-SQL ones were regenerated from SQL Server 2022 (podman container lxl-mssql) and equal the hand-written ones.

### 6.3.Q3 as built (2026-11-20)

Built on `worktree-agent-a6093c872adedcdc3` from main 0f96fee9. No
behaviour change: the moved code is unchanged but for names, the hook and
the arguments below. Tools (a declaration mover, a dependency counter over
6.2.1's `decls.py`, a pass that makes private what no other file names)
were scratch scripts, not kept.

**Slices and line counts:**

| commit | what | `lexdb_exec` | other |
|---|---|---:|---|
| main 0f96fee9 | | 24,744 | `lexdb_plan` 441 |
| b6d5e5e9 | `hasAgg`, `immutable`, `renameCol`, `colIndex` to `lexdb_bind`; `lexdb_gen`'s copies deleted | 24,690 | |
| 1aa01466 | slice 1: the planner and the plan structures to `lexdb_plan`; dead code | 20,298 | `lexdb_plan` 4,860 |
| 65732940 | slice 2: `lexdb_priv`; routine, UDF and generated-column glue | 19,827 | `lexdb_priv` 373, `lexdb_routine` 953, `lexdb_gen` 273 |
| 987206dd | slice 3: the physical plan's builders to `lexdb_plan` | 19,290 | `lexdb_plan` 5,414 |

So 5,454 lines left exec (22%). They moved: `lexell/cmd` as a whole is 27
lines longer than at main (the hook, two module headers and aliases,
against about 150 lines of dead code, duplicates and forwards deleted).

**Slice 1: the planner (`lexdb_plan`).** 180 declarations, 4,367 lines:

- The plan structures: `Query` with its 46 methods (the planner's: they
  had to move with the type, SPEC 5.3), `Level`, `SubPlan`, `Sel`,
  `SelLock`, `MrPlan`, `MrNav`, `Scope` (the planning state, privileges'
  `Who` with it: `Who` went to `lexdb_catalog`), `Work`, `FromHints`,
  `FromBound`; and `lexdb_pipe.Prog` (pure data; the pipe keeps `compile`
  and an alias), which `Query.jp` and `Sel.pipe` hold. Their fields are
  public: exec builds and reads them.
- Path choice: `choosePath`, the bounds and IN lists, filtered indexes'
  implication (`impliesOne`, `looksHold`), `pathFig`, `pathEst`,
  `figCost`, `servesOrder`, `orderedScan`, `orderLookups`, `minMax`,
  `ixCovers`, `pathText`/`estText` (EXPLAIN's text of a path).
- The cost model and the join order: `costOrder`, `nBest`, `joinStep`,
  `wayCands`, `wayInto`, `setRows`, the shares (`localShare`, `andShare`,
  `rangeShare`, `eqShare`, ...), `outerReadOnce`, `rightCheaper`,
  `joinOrder`, `pinnedOrder`, implied equalities and the classes of equal
  columns.
- `planFrom` (the conjuncts placed per level, the join order, the paths,
  hashing), the semi and anti joins (`semiJoins`, `semiLevel`,
  `semiLook`, `semiCheaper`, `semiRun`, `semiKeys`, `orderRows`),
  `hashSub`'s decorrelation, `narrowSub`, `physOf`/`subsOf` (the physical
  plan's view).
- **The hook** `lexdb_plan.Up`, a value record set once (`lexdb_plan.hook`,
  a set-once global) by `newSession`: `eval` (an expression with no row,
  exec's evaluator: the planner's constant folding in `constVal`,
  `litValue`, `evalInt`), `typing` (the dialects' typing for `exprOid`),
  `planSub` (`planFrom`'s semi-join alternative planned again). A global
  rather than an argument: about 30 planner functions fold constants, few
  of them with the query at hand.
- **No `Txn.sql`**: the planner mode and the statement's memory limit
  come in `FromHints` (`rules`, `memMax`, filled by `buildQuery`),
  `semiRows`' mode as an argument. `imports.py` checks it, with
  `lexdb_plan`'s imports (base, sql, bind, stats, catalog, access, store's
  `Store` and `Txn` only, ops, rows, agg, window, match) and its users
  (`lexdb_pipe`, `lexdb_exec`).
- 118 of the moved functions are private (no other file names them).
- Dead code deleted on the way: exec's `rowKey`, `rowOf`, `fillLevel`,
  `placeKinds`, `cloneOptE` and 23 unused aliases; pipe's `isValKind`.

**Slice 2: the glue.**

- `lexdb_priv` (new): roles' rows, owners and grants (ACLs), who a session
  acts as (`currentRole`, `sessionUser`, `whoIs`, `whoNow`, `setRoleIn`,
  the door memo `doorKey`/`doorOf`), the checks with each door's errors
  (`needRel`, `needOwner`, `needCreate`, `needRelOwner`, `needGrantor`),
  `renameInAcls`. It imports base, sql, store, catalog; exec and the
  protocol modules (for `roles`, authentication) import it. GRANT, REVOKE,
  ALTER ... OWNER and the ROLE statements stay in exec: they resolve their
  objects through exec's catalog lookups (`findTable`, `findSeq`,
  `schemaExists`, the temporary schemas), which are layer 7's (E4).
  `applyRoleOpts` stays: it needs `lexdb_auth` (a protocol module).
- `lexdb_routine`: `routinesIn`, CALL's procedure choice (`pickProc`, its
  42809/42883), `bodyTables`, the T-SQL UDF publication (`udfKey`,
  `udfFind`) and the table-reading function hook (`setUdfQuery`: lexdb_tds
  sets it on `lexdb_routine` now). `Session.routines`, `callRoutine`,
  `tsqlFunctions`, `inlineFunctions` stay as the session's drivers (they
  run statements); `udfEval` stays with the evaluator; `createRoutine`'s
  body check stays (it names `lexdb_pgcat`, a dialect module).
- `lexdb_gen`: `checkWrite` (was `genTarget`, `genSet`) and
  `checkConstraint` (was `genConstraint`), over the columns. `genFill` and
  `genSetup` stay: they need exec's evaluator and typing, and moving them
  would add a closure at each of the seven call sites.

**Slice 3: the physical plan's builders.** `planX`, `planConds`,
`scanArm`, `filterOver`, `joinsOver` (the `Join` arms of a level chain),
`pipeShape`, `sortShape`, `pipeAgg`, `aggShape`, `unplan`, `oxBack`,
`tableRead`, `heldRead`, `firstRead`, `isKeyEq`, `rangePath`,
`lookupPath`, `afterCols`, `streams`, `lazySeries`, `boundOnce` (551
lines). `pipeAgg` returns its plan; exec's `pipeSelMain` compiles it
(`lexdb_pipe.compile`, which the planner cannot import) as it compiles the
others.

**Gates.** Suite 236 of 236 after each slice (imports ok: 59 modules and
307 edges after slice 1, 60 and 316 after slice 2). Point selects: a
program of 20,000 primary-key point selects through `Session.exec` in
process (`pts.lxl`, 1,000 rows), built `-O` against main's tree (`git
archive 0f96fee9`) and the branch, `perf stat -e instructions:u taskset -c
6`, alternated twice under the bench lock (about 187k instructions a
statement, setup included):

| | main 0f96fee9 | branch | |
|---|---:|---:|---:|
| after slice 1, round 1 | 3,744.01M | 3,744.57M | +0.015% |
| after slice 1, round 2 | 3,745.71M | 3,745.56M | -0.004% |
| after slice 3, round 1 | 3,746.36M | 3,745.56M | -0.021% |
| after slice 3, round 2 | 3,746.92M | 3,745.20M | -0.046% |

Level (the spread is about 0.15%). TPC-H is the coordinator's.

**What is left in exec of planning, and why:**

- `bindFrom` (334), `buildQuery`, `planSub`/`viewPlanned`, `scCheck`:
  binding FROM resolves tables, views, sequences and temporary objects
  through exec's catalog lookups and checks privileges as the view's
  owner; it plans FROM's subqueries and views recursively (planSub to
  planSelect). This is E3 (6.2.1, 6.2.11's hand-over): the lookups must
  come in as a catalog snapshot first.
- `planSelect` (479), `planSet`, `planMatch` with MATCH_RECOGNIZE's
  rewrite: the select list, aggregates (`collectAggs`), windows
  (`winPlan`), grouping sets, ORDER BY, LIMIT, locks; they name the
  binder's leftovers in exec (`srfCols`, `outType`, `enumOrder`,
  `stmtNames`, `checkGrouped`). With E3.
- The plan cache (`select`, `planVersion`, `PLAN_VARIANTS`, `PlanCache`):
  session state (the cache is the prepared statement's); its variant test
  is `lexdb_plan.looksHold` already.
- The run-time switch from an index to a scan (`indexOrScan`,
  `firstSwitch`, optimizer 19): it counts entries as the statement runs.
- EXPLAIN's lines with run counts (`explainLines`, `subLines`,
  `opLines`): they read `Run`'s counts (`SubStat`, `lexdb_pipe.Counts`).

**Seams for Q4-Q7** (all in `lexdb_plan` now):

- Q4, a row-id-ordered index read: a path's choice is `choosePath` (a
  flag on `Path` beside `stats`), its figure and cost `pathFig`/`figCost`
  and the join order's first-table cost (`wayInto`, `constWay`; the
  `SCAN_SHARE` switch constants), its text `pathText`. The reading itself
  is the executor's: exec's `pathScans`/`runLevel` for the row engine,
  `lexdb_pipe.srcOf` for batches; the counted switch (`indexOrScan`) stays
  in exec.
- Q5, predicate pushdown and outer-to-inner: `planFrom` places WHERE's
  conjuncts per level (`ms`, `ps`, `lastRight`) and is where a LEFT JOIN
  whose NULL rows WHERE rejects can become inner (before
  `q.innerOnly()` decides the join order). Pushdown into a derived table
  or view must happen before its subquery is planned, which is
  `bindFrom`/`planSub` (still exec): either a rewrite of the statement
  before binding, or E3 first.
- Q6, bushy joins: the search is `costOrder`/`nBest`/`joinStep`/`setRows`
  over sets of levels (`Way`); its result is a permutation of the level
  chain (`perm` in `planFrom`), and the pipeline's joins are built
  left-deep by `joinsOver` (`PPlan.Join(outer, PJoin)`). A bushy plan
  changes both, and the row engine's level chain cannot run it: bushy
  plans are the pipeline's only.
- Q7, unnesting: `hashSub` (9.9's decorrelation), `semiJoins`,
  `semiLevel`, `semiLook`, `semiKeys`, `semiAltOk`, with `planFrom`'s
  semi-join alternative through `Up.planSub`.

### 6.3.Q4 as built (2026-11-20)

Index ranges read in key order (PostgreSQL's bitmap heap scan for an
index-organised table), chosen by cost: lexdb-optimizer.md 47 (47.8 as
built, 47.9 the calibration). The reading is `lexdb_access`'s
(`sortedChunk`, `fillSorted`, `fetchSorted`), the choice and EXPLAIN text
`lexdb_plan`'s (`Path.sorted`, `keyOrdered`, `scanFirst` by
`COST_SORTED_ROW`), `lexdb_pipe.srcFor` passes it on; exec has glue only
(19,680 -> 19,687 lines). TPC-H q4 291 -> 188 ms, q14 228 -> 171 (medians
of four alternated); q15's view range now by its index (instructions
-67%); no query slower. q19's OR of index paths (BitmapOr) is left as the
next step.

### 6.3.Q5 as built (2026-11-20)

Rewrites that keep results: lexdb-optimizer.md 48 (48.1 where they run,
48.2 and 48.3 the validity rules, 48.5 as built, 48.6 plans, 48.7
measured). Branch `worktree-agent-aac772f0b27ea504a` from main cbd664a6.

- **Outer to inner** (`lexdb_plan.innerJoins`, in `planFrom` before
  WHERE's conjuncts are placed): a LEFT JOIN whose NULL rows a conjunct
  above it rejects (WHERE's, or the ON of a later inner or RIGHT join),
  RIGHT likewise, FULL to LEFT, RIGHT or inner. The join is then searched
  and hashed as any inner join.
- **Pushdown** (`lexdb_plan.pushDown`, in `planFrom` after it): a WHERE
  conjunct on one derived level (a FROM subquery, a view, a CTE used once)
  is written in the derived query's terms and ANDed into its WHERE (or
  HAVING over an aggregate; into every part of a set operation), and the
  derived query is planned again through `Up.planSub`. Why not a rewrite
  before binding: the derived query's columns, and which FROM item an
  unqualified name means, are known only after `bindFrom` has planned it;
  so `bindFrom` (exec, glue only) keeps each view's query, owner and
  renames on its `SubPlan` (`view`), `planFrom` gets WHERE as written
  (`buildQuery`'s), and the planner plans the
  derived query a second time when it has something to push (E3 would
  let the binder do this once).
- Both off under `SET lexdb_planner = rules`; `lexdb_plan.setRewrites`
  switches each off for tests. `exec_rewrite` runs 110 queries (outer
  joins of all three kinds, nested, USING, LATERAL; views, derived tables,
  CTEs, parameters, a view as its owner and after a rename) with the
  rewrites, without, with batches off and under the rules: the same rows.
  `tns_ddl`: a view filtered through the Oracle door.
- `lexdb_exec` 19,687 -> 19,694 lines; `lexdb_plan` 5,496 -> 5,898.
- Measured (48.7, a 200,000-row table): a view filtered on its key 46 ms
  -> 0.04 ms, an aggregate view on its group key 5.6 -> 0.18 ms, a LEFT
  JOIN made inner and reordered 9.9 -> 0.09 ms.
- TPC-H: no plan changes (q13's filter is in its LEFT JOIN's ON; q15's
  view conjuncts are a join and a subquery comparison); timings level
  (totals +0.0% and -0.0% in two alternated rounds), checksums equal.
- Point selects: +0.05% mean over six alternated rounds (-0.01% to
  +0.09%; spread 0.15%); a first version's +0.10% (CTE counts in the
  parser's state) fixed.
- Point-select cost found and removed (2026-11-20): with `LXL_HASH_SEED`
  fixed the count is exact (spread ~100 instructions a run), Q5 +0.073%
  (+118 instructions a select). Bisected, one piece at a time: `FromBound` growing an
  `Option[Expr]` and a `[]ViewSrc` +74 (no longer a plain record), the
  `viewSrcs` local in `bindFrom` +31, `markCtes(mut &s)` in `parseIn`'s
  loop +21, `planFrom`'s tests a few. Now the views' queries ride on their
  `SubPlan` (`view`), `planFrom` gets `buildQuery`'s WHERE (pushDown
  applies `pullCommonOr` again), and the CTE marks go on the statement in
  `out`: +0.009% (+14), six random-seed rounds -0.024% mean (-0.071% to
  +0.057%).
- Left: pushing an uncorrelated scalar-subquery comparison into a
  derived query's HAVING (q15's), pushing a LEFT JOIN's own ON conjunct on
  a derived right side into it, pushing past a window on its PARTITION BY
  keys, and planning a derived query once (E3: the binder settles which
  conjuncts it gets before planning it).

### 6.3.Q6 as built (2026-11-20)

Bushy joins, one shape: a hash whose build side is a join (a *build
group*: a hub and one or two member tables hashed inside the build, the
joined rows hashed and probed as one): lexdb-optimizer.md 49 (49.3 the
search and the cost, 49.5 the row engine, 49.8 as built and measured).
Branch `worktree-agent-a0cb1a031d1cae494` from main 1ccb366c.

- **The plan:** the level chain stays left-deep with the group marked
  (`Level.grp`); `joinsOver` makes the group one arm (`PJoin.how =
  JH_JOIN`, its build a join plan in `PJoin.sub`). The pipeline runs the
  build with `joinRows` into a hash builder (`lexdb_pipe.grpSetup`) and
  probes it as any hash; the row engine runs the same chain left-deep
  (each table hashed), and where no pipeline program holds the joins the
  marks are cleared (`flatGroups`, exec's glue), so EXPLAIN shows what
  runs. Not planned where the pipeline will not run the joins (a
  correlated subquery that stays one: `grpRuns`).
- **The choice:** a pass over the order the search chose (`grpPass`): a
  run of it made one group where the group costs less than the steps it
  replaces and the plan with groups costs under 0.9 of the order's
  (`GRP_GAIN`); the hub's read priced as a hashed table's is (a first
  version priced it as a batched scan and flipped a plan of exec_joincost
  to one 2.9 times slower; a first version inside the exact DP took a
  8-table star's planning from 246 to 2,065 us: the pass adds 1-5%).
  `SET lexdb_planner = rules` makes none; `lexdb_plan.setBushy` (`BU_OFF`,
  `BU_COST`, `BU_FORCE`) for tests.
- **TPC-H:** q7 (supplier with nation n1, customer with nation n2: the
  146k customer lookups now a hash) 934 -> 712 ms (-24%; instructions
  -15%); q21 (supplier with nation) 1,218 -> 1,096 ms (-10%; instructions
  -4%); no other plan changed; all 22 -3.1%, no query slower by more than
  1.9%, checksums equal (two alternated rounds).
- **Gates:** suite 247 of 247 (new: `exec_bushy`); point selects +0.001%
  (`LXL_HASH_SEED=1`, three rounds); `lexdb_exec` 19,688 -> 19,700 lines
  (glue only).
- **Left:** the hashed read's price for the pipeline (section 45's
  row-by-row figure overprices every hash the pipeline builds, a group's
  and a left-deep one's; re-pricing it moves left-deep plans too); groups
  whose tables are not adjacent in the chosen order; q5's and q8's
  (region, nation, customer) shape (PostgreSQL's), which the model now
  prices within 4% of left-deep; q9's supplier lookups (the rows estimated
  low).

### 6.3.Q7 as built (2026-11-20)

Step 5's slices 5a-5c (6.1, "The slices"), each a kind of level in
today's structures, run by the row engine and by the pipeline's joins:
lexdb-optimizer.md 50 (50.2 the NULL rules, 50.3 validity, 50.6 as built
and measured). Branch `worktree-agent-a7ed8cb9808946f75` from main
01b0250c.

- **5a, NOT IN as a null-aware anti join** (`LV_NOTIN`, `MK_NOTIN`): `x
  NOT IN (subquery)` and `x <> ALL`, a top-level WHERE conjunct,
  uncorrelated or correlated by equalities (hashed as 9.9 planned it, or
  planned again without outer keys and taken by cost); the subquery's rows
  hashed on (keys, value) with a summary per key (rows; rows and a NULL),
  the row kept when IN is false. Placed right after its level, where no
  error moves.
- **5b, the mark join** (`LV_MARK`, `MK_MARK_EX`/`MK_MARK_IN`, `RUN_MARK`):
  a correlated EXISTS or IN under OR, NOT, CASE or IS NULL in WHERE (its
  conjunct the level's condition), or in the select list and ORDER BY of
  a query that does not group (`selMarks`, from `bindSel`): every row
  goes on once with the subquery's value (true, false, NULL) in the
  level's last column, which the expression reads.
- **5c, semiLook widened** (`inLook`, `semiLookOf`, `twoKey`/`twoSet`): IN
  looked up per row by its value where it leads the inner table's primary
  key or an index (by cost); EXISTS whose path has a range after its
  equalities; EXISTS over two tables, one looked up, the other's rows a
  set run once (a new IN subquery).
- **The switch:** `lexdb_plan.setUnnest` (`UN_NOTIN`, `UN_MARK`,
  `UN_LOOK`; 0 today's plans). Under `SET lexdb_planner = rules` no
  alternative is planned and nothing is chosen by cost (the levels from
  subqueries already hashed or uncorrelated are made).
- **What a query gains:** with no correlated subquery left, the pipeline
  takes it (`q.corr`). In `tds_unnest`, 14 of 16 T-SQL queries ran
  through the pipeline's joins with the new levels, 1 with today's.
- **Measured (50.6):** per shape 2.3x to 64x faster (NOT IN 47 -> 21 ms
  uncorrelated, 198 -> 46 hashed, 201 -> 47 indexed; OR EXISTS 173 -> 23;
  the select list's EXISTS 28 -> 10; IN by its key 4.4 -> 0.11; a range
  5.2 -> 2.2; EXISTS over two tables 264 -> 4.1). TPC-H: q16 248 ms
  from 276 (-10%; instructions -11.8%), its plan the only one changed;
  all 22 0.988 of main alternated twice, checksums equal. Point selects:
  -21.9 instructions a select (-0.012%; `LXL_HASH_SEED=1`, three rounds).
- **Gates:** suite 250 of 250 (new: `exec_unnest`, `tds_unnest`,
  `tns_unnest`); `lexdb_exec` 19,700 -> 19,737 lines (glue).
- **Left:** 5d and 5e; a select list's subquery that 9.9 could not hash
  stays per row; marks with a residual, in ON, HAVING, grouped queries
  and DML; a null-aware lookup; a numeric or collated key's lookup; outer
  bounds of a range lookup in the pipeline; EXISTS over three tables.

### 6.3.Q7 as built, second half (2026-11-20)

Step 5's slices 5d and 5e (6.1, "The slices"): lexdb-optimizer.md 51 (51.2
keys with no rows, 51.3 validity, 51.7 q20 measured, 51.8 as built). Branch
`worktree-agent-a0afd47b5b6049e6d` from main b519a837.

- **5d, a correlated scalar aggregate as a grouped level** (`scalarJoins`,
  `selScalars`, `groupLevel`, `RUN_GROUPED`): `x op (select agg(...) from
  ... where inner.k = outer.k ...)` in a WHERE conjunct, the select list or
  ORDER BY. The subquery run once, grouped by its keys (9.9's form), its
  rows a level LEFT joined by a hash on them; the call read from the
  level's columns (the expression per group where it cannot fail, else
  the aggregates and the expression per outer row), a key with no group
  given the expression over no rows (count 0) by a CASE on the first key
  column. 9.9's grouped subqueries become levels (the query then the
  pipeline's: it was the row engine's, `q.corr`); one with an index on the
  key is planned again without outer keys (`scalarAlt`, only where a
  grouping could cost less than the runs) and taken by cost
  (`groupCheaper`: the groups' rows, a join's later tables a lookup each,
  the statement's memory); with few outer rows it stays per row.
- **5e, a correlated FROM subquery with an aggregate as a join and a
  grouping** (`lateralGroup`, `lateralOn`, `lateralMs`): LATERAL, CROSS JOIN
  LATERAL, LEFT JOIN LATERAL ... ON true, T-SQL's and Oracle's CROSS and
  OUTER APPLY. The keys added to its GROUP BY and, hidden, to its columns;
  run once, hashed on them, the equalities its ON. With a GROUP BY: CROSS
  drops an outer row with no group, LEFT keeps it with NULLs; without: one
  row for every outer row (LEFT), count's 0 read through a CASE (the
  column made virtual, as Q2's). Per row where an index serves the key
  (9.9's rule), or anything run once could fail where a run per row would
  not.
- **The switch:** `setUnnest`'s `UN_SCALAR` and `UN_LATERAL` (default on;
  `setUnnest(7)` gives the first half's plans). Under `SET lexdb_planner =
  rules` nothing is planned again or chosen by cost (9.9's grouped
  subqueries still become levels).
- **A fix:** 9.9's hashed probe evaluated a scalar's value over no rows
  once, eagerly: `100 / count(v)` failed (22012) where every key had rows;
  the level evaluates it only for a row whose key has no group.
- **Measured (51.9):** per shape 3x to 85x (a WHERE count over 200,000
  rows 158 -> 36 ms, by cost with an index 156 -> 13, the select list's
  max 32 -> 10, LATERAL count 1,292 -> 30, LEFT JOIN LATERAL ... GROUP BY
  1,297 -> 15; per row where it stays: level). TPC-H: no plan changed
  (q2, q17 and q20 stay per row by cost: their runs cost a fraction of
  grouping partsupp or lineitem), checksums equal, all 22 1.004 and 1.010
  of main in two alternated rounds with instructions equal (q22 +0.14%,
  inlining). q20 analysed (51.7): 230 ms warm, of which the 8,508 runs
  read 63,832 lineitem rows by primary key (about 100 ms) and pay about
  4.6 us of setup each (39 ms); the hash would exceed the statement's
  memory, and a magic set reads the same rows; its gap to PostgreSQL's 133
  ms is the row fetch and the per-run setup, not the plan.
- **Gates:** suite 253 of 253 (new: `exec_unnest_agg`, `tds_unnest_agg`
  with SQL Server 2022's answers, `tns_unnest_agg`); point selects -0.08
  instructions a select (`LXL_HASH_SEED=1`; a first version's +251 from
  `bindFrom`'s per-item state removed); `lexdb_exec` 19,737 -> 19,747 lines
  (glue), `lexdb_plan` 7,204 -> 8,024.
- **Left:** 51.9's list (q20's per-row cost; a magic set for an inner
  side with no index; 5d in ON, HAVING, grouped queries and DML; 5e by
  cost where an index serves the key, and outputs that may fail).

### 6.3.Q8 as built (first part, 2026-11-21)

Q8's first part: the census (6.4), Fetch for point selects, the dead
code, and the deletion plan (6.5). Branch
`worktree-agent-a7a4819d7382d2516` from main 4fa2acec. The row engine's
live paths and `SET lexdb_batch = off` are untouched.

**Commits and line counts:**

| commit | what | `lexdb_exec` | other |
|---|---|---:|---|
| main 4fa2acec | | 19,747 | `lexdb_pipe` 7,301, `lexdb_plan` 8,024 |
| 161b5d55 | stage 1: the census (`lexdb_census` 112 lines, `tools/lexdb_census.py`), its reasons in the planner and the pipeline; 6.4 | 19,785 | `lexdb_plan` +167 (the reasons: `shapeWhy`, `aggWhy`, `censusKey`, ...), `lexdb_pipe` +~90 (`opsWhy`, `scanWhy`) |
| f0c154c2 | stage 2: Fetch -> Project for point selects (`pipeFetch`, `lexdb_pipe.runPoint`, `lexdb_plan.pointRead`); test `exec_fetch` | 19,818 | `lexdb_pipe` +~55 |
| 6b512c36 | stage 3: dead code | 19,814 | `lexdb_pipe` 7,432 |
| 8d38f00b | the census's calls in declined branches made hooks too (the join's +24); 6.3.Q8, 6.5 | 19,825 | `lexdb_pipe` 7,543, `lexdb_plan` 8,271 (the hooks on lines of their own) |

**Stage 2: Fetch for point selects.** The census found every point
select already the pipeline's (P1a: Scan of one point -> Project, a chunk
of one read row by row), 2.5% fewer instructions than the row engine's
(6.4). What Fetch takes away is the generic run's glue around one row:

- `runPipe`, for a plan whose only table is read by its whole primary key
  (`lexdb_plan.pointRead`: a table, no index, every key column equal, no
  IN list) with no subquery, no join and no batched write's resume key,
  calls `pipeFetch`: the one scan from the key's values (`pathScan`, as
  `pathScans` makes it for such a path), the context with the run's
  parameters (one session environment, not three: no `runSubs`, no
  `subVals`, no `firstSwitch`, whose answer for a primary key path is
  always -1, no `srcOf`).
- `lexdb_pipe.runPoint` runs `Limit? (Sort of the scan's order)? (Project
  (Filter? (Scan)))` over that scan: the row read (`lexdb_access.fetch`,
  one point), then `oneRow` as `runScan`'s row path runs it (the tick, the
  counts, the conditions in order, the outputs by `bxEval`, given as a row).
  Any other shape (a Sort or Distinct, a scan that reads batches or held
  rows, a scan that is not one point) goes to `lexdb_pipe.run` with
  `srcOf`'s Src, exactly as before.
- `execSelIn` makes its session environment (`seqEnv`) after the
  pipeline's rows, for the row path only (every pipeline SELECT paid it).
- The same rows, errors and EXPLAIN ANALYZE counts as with batches off:
  `exec_fetch` (30 queries: integer, text and two-column keys; missing,
  NULL, out-of-range and other-typed keys; outputs and conditions that fail
  or drop the row; LIMIT 0 and 1; ORDER BY, DISTINCT, FOR UPDATE), 27 of
  them by the point path (`lexdb_pipe.runCounts()[3]`).

Measured (variants built from the same tree, `LXL_HASH_SEED=1`, in
process, the 1-select run subtracted from the 20,000-select one,
instructions a select):

| build | instructions | vs main |
|---|---:|---:|
| main 4fa2acec | 132,512 | |
| the census in (stage 1) | 132,512 | 0 |
| `pipeFetch` with `lexdb_pipe.run` (its Src made directly) | 131,428 | -1,085 (-0.82%) |
| ... and `runPoint` | 130,402 | -2,111 (-1.59%) |
| ... and `execSelIn`'s `seqEnv` after the pipeline (stage 2 as committed) | 130,132 | -2,381 (-1.80%) |
| stage 3 and 8d38f00b (three and two rounds) | 130,131.6 | -2,381 (-1.80%) |

Over the wire (base 4fa2acec against the branch, both `-O`, alternated):
`pts.sh` (`points.sql`, 20,000 point
selects by the simple protocol, server CPU, means of 5-10 runs): 669.5 ->
657.6 ms (-1.8%) with stage 2's binary, 658.2 -> 643.2 ms (-2.3%) with the
final one. `simple.sh` (pgbench `-M simple`, 4 clients, 10 s, two rounds,
the final binary): point select 47,188 -> 52,462 tps (main's first round
44,813, an outlier; the second 49,562 against 52,305), update 9,311 ->
9,286 (-0.3%), 3-table join 19,945 -> 19,931 (-0.1%; with stage 2's
binary it read 20,249 -> 19,608, -3.2%, at +24 instructions a statement:
the census's calls in the join's declined branches, then made hooks,
8d38f00b; its instructions are main's now, 426,944.4 a statement in
process).

So point selects are switched (they were the pipeline's already; Fetch is
now their path).

**Stage 3: dead code.** The coverage census (6.4's tool: `copy
--cover=lexdb_exec,lexdb_pipe,lexdb_plan --blocks=lexdb_exec,lexdb_pipe`,
the suite, TPC-H's 22 and the OLTP runs; then the suite again with `SET
lexdb_batch = off` ignored, `--force-batch`):

- Functions: 646 of exec's 652 entered, 216 of the pipe's 217, 275 of
  the plan's 277 (the 2 the census's own). Not entered: `fastCopyFloat`,
  `ownSeq`, `sysSuper`, `formatTypeFn`, `bxOf`, `seenTables` (COPY of
  floats, OWNED BY, T-SQL's IS_SRVROLEMEMBER, `format_type` with two
  arguments, `batchLevel`'s binding of a condition the plan did not bind,
  VACUUM's tables): untested, not unreachable; and the pipe's `levelsOf`,
  which nothing calls (dead).
- Blocks (an if's, a loop's, a match arm's, a closure's; 2,054 in exec,
  755 in the pipe): 139 and 49 not entered, all error paths and rare
  values (DDL corners, catalog functions, T-SQL and Oracle forms, a
  window's order key of mixed kinds, `execSrf`'s unused catalog
  relations): none of them provably unreachable.
- With batches forced on, the same 1,130 functions are entered: **no
  function of exec, the pipe or the plan is there for the tests'
  reference alone.** Ten blocks are entered only with batches off:
  `runLevel`'s read of the keys optimizer 19's switch counted (2220-2235)
  and `winValues`' row path (the window calls by value, 15750-15767). They
  are the reference's and stay while `SET lexdb_batch = off` does.
- Every function the pipeline made redundant was deleted in its own slice
  (P1-P3, the batch gaps, Q3): what is left of the row engine is reached
  by statements the pipeline declines (6.4), so nothing more of it can go
  before 6.5's slices.
- Deleted (dead by name, no caller in the tree or the tests): the pipe's
  `levelsOf`, `hashCutRows` and its counter `hashCuts` (written per hash
  reduction, never read); exec's `noLimits` and `tabTypeId`. 4 lines out
  of exec, 13 out of the pipe. (Other modules have a few more, outside the
  row engine: `lexdb_time`'s `instantOf` family, `lexdb_bind`'s `lpCols`,
  `lpLentExprs`, `copyBCols`, `lexdb_catalog`'s `tabTypeObj`,
  `tabTypeCols`; left.)

**Gates.** Suite: 253 of 253 after stage 1 (and in the census copy), 254
of 254 after stages 2 and 3 (new: `exec_fetch`). Point selects: stage 1
level (132,512.3 against 132,512.4), stages 2-3 -2,381 a select.
TPC-H (base 4fa2acec and the branch, `-O`, alternated twice, `TPCH_REF`
1744ef99, one run each, `~/tpch-w/q8`), the final binary (8d38f00b): all
22 1.000 of main (23,820 and 23,820 ms), checksums equal, no plan changed;
over 1.5%: q15 +2.6% (its first round 629 against 601 ms, the second 605
against 602), its server instructions main's within 0.01% (`iq.sh`):
code placement. Stage 3's binary (6b512c36) read 0.990, with q9 +2.1%,
q13 +3.3%, q17 +2.3% at instructions within 0.03% of main's. Imports: 62 modules (new: `lexdb_census`, which
`lexdb_plan`, `lexdb_pipe`, `lexdb_exec` and `lexdb_wire` import).

### 6.3.Q8 R1 as built (2026-11-21)

R1 of 6.5: every SELECT's rows offered to the pipeline. Branch
`worktree-agent-a5a46464f3e4a17f4` from main a75aa5d0. `SET lexdb_batch
= off` (the row engine, the tests' reference) is untouched, and no
row-engine code was deleted: all of it is still reached (6.4 after R1,
below).

**Commits and line counts:**

| commit | what | `lexdb_exec` | other |
|---|---|---:|---|
| main a75aa5d0 | | 19,825 | `lexdb_pipe` 7,543, `lexdb_plan` 8,271 |
| baed363a | stage 1: a subquery's own rows (`pipeSelMain` offers every subquery's rows, not only its aggregates), INSERT ... SELECT's, CREATE TABLE AS's and COPY (query)'s query (`pipeSel`), a write's subqueries (`pipeSubs`: UPDATE, DELETE, MERGE, INSERT VALUES and RETURNING, EXPLAIN of a write); UPDATE and DELETE call `onceEach` and `firstN` only with FROM or TOP | 19,847 | |
| cb5a4329 | stage 2: a correlated subquery's own rows (its outer values are parameters: `pipeShape` no longer declines `q.refs`); a subquery a semi or anti level looks up per row not planned (`subRuns`: `semiLook` took its table); `lexdb_pipe.runJProj` returns a consumer's error rather than joining the chunk again row by row; T-SQL 512 and ORA-01427 for 21000; tests `exec_subrows`, `tds_subrows`, `tns_subrows` | 19,854 | `lexdb_pipe` 7,553, `lexdb_plan` 8,272, `lexdb_tsql` +1, `lexdb_oratext` +1 |
| 106b8455 | stage 3: `pipeSelIn`'s `rows` flag gone (always true): one `pipeSel`; `subRuns` and `evalTop` in `lexdb_plan` | 19,837 | `lexdb_plan` 8,277 |
| c50f681b | stage 4: an EXISTS's unread select list made NULL (`lexdb_plan.existsUnread`), a hashed subquery's key outputs let through (`hashedOuts`) | 19,838 | `lexdb_plan` 8,301 |

**What is offered now.** Every Sel `pipeSel` sees, at every depth: the
statement's own, its subqueries' (IN, NOT IN, EXISTS, a scalar's, ANY and
ALL, a semi, anti or mark level's set, a FROM subquery's, a CTE's), a set
operation's parts, and the queries of INSERT ... SELECT, CREATE TABLE AS
and COPY (query) TO; a write's subqueries are bound once and planned the
same way. Which of them the pipeline then runs is `pipeShape`'s and
`compile`'s answer, as for a top-level SELECT; the rest run as before.

- **A correlated subquery's own rows** (EXISTS, IN, a scalar subquery
  run per outer row) are the pipeline's: its outer values are the run's
  parameters, as a correlated aggregate's already were (q17, q20), so
  `pipeShape` no longer declines `q.refs`. A subquery read by its whole
  primary key per row takes `pipeFetch`'s point path. The per-run cost,
  measured before deciding (below), is lower than the row engine's for
  every shape, so there is no plan-time choice between the two.
- **A subquery a semi or anti level looks up per row** (`semiLook`, which
  moved its table into the level: it is no longer run) is not planned
  (`lexdb_plan.subRuns`); planning it crashed on its emptied level.
- **An EXISTS's select list**: its `*` reads no column (`stmtNames`, q21's
  narrowing), so its scan decodes none and the pipeline refused outputs
  of undecoded columns. `existsUnread` (in `planSubIn`) makes each column
  output NULL, the value the row engine read of it, unless the rows it
  counts depend on their values (a set operation, grouping, DISTINCT, an
  aggregate). PostgreSQL drops an EXISTS's select list the same way.
- **A hashed subquery** (correlated, run once into a hash: `hashSub`)
  outputs its keys and its value, more columns than its select list.
  `pipeShape` takes more outputs than the list when the Sel neither sorts
  nor is DISTINCT (`hashedOuts`; `hashSub` is the only maker of such a
  Sel; `runHashed` reads the rows by position, not `outs`). The test is a
  statement of its own: written into `pipeShape`'s return it cost a point
  select 12 instructions.
- **Writes** (`pipeSubs`, after `endScope`): UPDATE's SET and WHERE,
  DELETE's WHERE and RETURNING, MERGE's source and conditions, INSERT
  VALUES' and RETURNING's subqueries; INSERT plans them inside its test
  for subqueries (`resolved`), so INSERT VALUES pays nothing. The rows a
  write changes are still found by `runQuery` (R5).
- **A bug the switch exposed**, in the pipeline's joins: `joinChunk`
  joins a chunk again row by row when an expression of the joins fails
  (to give the row engine's first failing row), and took a failure of the
  rows' consumer for one: an INSERT ... SELECT over a join whose row 11
  broke NOT NULL wrote rows 1-10 again and failed with 23505.
  `runJProj` now keeps a consumer's error and stops, as `runLevels` did.
- **The doors**: 21000 (a scalar subquery with two rows) was T-SQL's
  50000 and Oracle's ORA-20000; now 512 and ORA-01427, their own.

**Still not offered, and why:** every planner path to a run goes
through `pipeSel` now; the census still notes six runs as "not offered"
(no reason kept under the Sel's key), one each of six `exec_unnest` look
queries' IN subqueries (`select id, c from t1 where id < 20 and c in
(select id from t3 where t3.v > 20)` and five like it), not traced
further: a Sel planned outside `pipeSel`, or a census key another Sel
of the statement holds. What the pipeline still declines among the
subqueries R1 offered shows under their next reason in 6.4 (after R1):
a correlated subquery left per row inside them (R6), a correlated
subquery in their outputs (R6/R7), a function in FROM (R3), no FROM
(R2), and a few of the small ones.

**The per-run cost, measured first** (in process, `LXL_HASH_SEED=1`, the
tables loaded by the row engine in both builds so their layout is the
same; 1,000 outer rows, unnesting off so the subquery runs per outer row;
instructions a query of 1,000 runs, the 1-query run subtracted from the
21-query one; main a75aa5d0 against the branch's final tree):

| subquery, per outer row | main (row engine) | R1 (pipeline) | |
|---|---:|---:|---:|
| `(select v from f where f.id = o.k)` (the point path) | 29,697,213 | 24,877,093 | -16.2% |
| `... where f.id = o.k and f.v > 0` | 30,526,657 | 25,681,865 | -15.9% |
| `o.id in (select xf from f where f.xf = o.k)` (an index, index only) | 51,730,448 | 49,131,694 | -5.0% |
| `exists (select 1 from f where f.xf = o.k)` in the select list | 44,880,315 | 42,937,397 | -4.3% |
| `(select v from f where f.xf = o.k limit 1)` | 47,633,495 | 45,566,442 | -4.3% |
| `(... order by v desc limit 1)` | 54,291,562 | 51,064,111 | -5.9% |
| `(select o2.z from f join o2 ... limit 1)` (a join under LIMIT: still the row engine's, R4) | 50,534,633 | 50,519,634 | -0.03% |
| `o.k in (select distinct xf from f where f.id = o.id)` (hashed, run once) | 59,298,344 | 53,243,153 | -10.2% |

So the pipeline's setup a run (`runSubs`, `pipeSrc`, `pipeCtx`, the
program's run) costs less than the row engine's (`prepareIn`,
`runQuery`, `outRow`), and there is nothing to choose at plan time.
q20's 8,508 runs (51.7) are a correlated aggregate's, the pipeline's
before R1 and after: unchanged (its instructions below).

**The census again** (6.4's tool on the final tree, the same 254 tests as
6.4's run at main: the three new tests' lines left out; batches on):

| engine | main a75aa5d0 | R1 |
|---|---:|---:|
| the pipeline's rows | 38,940 | 188,801 |
| the pipeline's groups | 790,243 | 790,602 |
| the row engine | 310,731 | 162,204 |
| a write's rows found | 3,001 | 3,003 |
| a set operation | 553 | 553 |
| batches off | 737,799 | 737,799 |

- R1's rows of 6.4: "a subquery's own rows (rows false)" (151,024 runs
  at main, with its "; and ..." variants) is gone; "not offered" fell
  from 800 runs (274 statements) to 6 (above).
- Run by run (the census lines of a test in order, in the 244 tests whose
  run counts are the same): of 104,534 runs of R1's reasons, 91,325 are
  the pipeline's now and 13,208 the row engine's under their next reason
  (a correlated subquery left per row 6,849; one in the outputs 6,024;
  a function in FROM 121; no FROM 77; an output that does not bind 48;
  MIN/MAX by the scan's order 30; 59 in eight small ones). Of 70,972
  runs of the other reasons none moved. The ten tests whose run counts
  changed (plans changed: `exec_autostats`, `exec_unnest`,
  `exec_semijoin`, ...) held 47,290 runs of R1's reasons and hold 6.
- Beyond R1's rows: "a correlated subquery's own run (refs)" (22,198
  runs, 59 statements), which 6.4 counted with R6's "correlated per row",
  is gone too: those are correlated subqueries' own rows, now offered.
  The R6 row keeps its other three parts (a correlated subquery left per
  row in a query: those queries are still the row engine's).
- TPC-H (the 22 once through a census build): the row engine's runs fall
  from 6 to 4: q16's NOT IN subquery (the supplier scan) and q20's inner
  IN subquery (part by name) are the pipeline's. q20's outer IN subquery
  (partsupp, with the correlated sum in its WHERE) is now the row
  engine's for that sum (`q.corr`: R6), as are q2's and q17's outer
  queries; the fourth is a `select 1`.

**Gates.** Suite: 254 of 254 at stage 1, 257 of 257 after (new:
`exec_subrows`, `tds_subrows`, `tns_subrows`). Each new test runs every
statement with batches on and off (the same rows or error, a write's
table after it the same); `tds_subrows`' answers are SQL Server 2022's
(the `lxl-mssql` container, through its own program with `LEXDB_MSSQL`
set), `tns_subrows`' are lexdb's (no Oracle at hand; Oracle's forms,
NULLs first under DESC, `||` reading NULL as ''). `exec_subrows`' groups
and their pipeline runs (main / R1, the same rows on both): where 752 /
767, per row 13 / 3,740, select list 4 / 715, from 11 / 20, writes 12 /
888, INSERT ... SELECT 27 / 379. Expectations changed: `exec_subbatch`
(its nested subquery's condition is the pipeline's, no `s`),
`exec_unnest` (one more look query through the pipeline's joins).

Point selects, single-row INSERT, UPDATE by key (in process,
`LXL_HASH_SEED=1`, the 1-statement run subtracted from the 20,000 one,
the simulated disk; INSERT and UPDATE in one transaction, so the
simulated disk's commit, which copies its files, is not in the count;
their table loaded by the row engine in both, as R1 changes how INSERT
... SELECT lays a table out, which moves later statements' counts):

| statement | main a75aa5d0 | R1 (c50f681b) | |
|---|---:|---:|---:|
| point select | 119,396.8 | 119,382.8 | -14 (the table loaded by the pipeline in R1's build: 119,525.8 against 119,516.8, -9, with the same layout) |
| INSERT VALUES, one row | 106,288.9 | 106,271.9 | -17 |
| UPDATE ... WHERE id = k | 148,487.3 | 148,293.2 | -194 |

On the way: `if len(q.subs) > 0 { pipeSubs }` after INSERT's `endScope`
cost INSERT 4 instructions (moved into its `resolved` test: -17), the
same test cost UPDATE 4 (paid back by skipping `onceEach` and `firstN`'s
calls without FROM or TOP: -194), and `hashedOuts` written into
`pipeShape`'s return 12 a point select (a statement of its own: 0).
Instruction counts on a real directory vary by about ±80 a write (the
log's group commits); the simulated disk is exact.

TPC-H (base a75aa5d0 and the branch, `-O`, alternated twice, one run
each, `TPCH_REF` 1744ef99, `~/tpch-w/r1`; best of the two): with the
final binary (c50f681b) checksums equal on all 22, 11,898 against 11,814
ms (0.993), none over 1.5% slower (the most q5 +1.1%, q13 +0.8%); q16
-2.3%, q17 -1.7%, q20 -1.6%. Stage 3's binary (106b8455): 0.994, q20
+1.8% (278.5 against 283.6 ms) at 0.19% fewer server instructions than
main (`iq.sh`: 1,755,126,930 against 1,751,834,444), q16 -0.04%, q17
-0.03%: placement. The final binary's server instructions against main's
(`iq.sh` over `~/tpch-w/r1`'s copy of the data): q20 -0.19%, q16 +0.06%,
q5 +0.04%.

OLTP over the wire (base a75aa5d0 against c50f681b, `-O`, alternated,
two rounds; logs in `~/tpch-w/r1/logs`):

- `icount.sh` (points.sql, the server's instructions and cycles a
  statement): instructions 186,982 / 187,035 / 187,030 against 186,967 /
  186,990 / 186,916 (equal, R1 15-115 fewer); cycles 103,092 / 103,189 /
  102,721 against 104,674 / 105,443 / 105,129 (+1.5% to +2.3%). Stage 3's
  binary (106b8455): the same instructions, cycles 107,539 and 107,439
  (+4.6%); stages 1 and 2 104.0k and 103.8k. Instructions equal and
  cycles swinging by 3.6% between two stages a few lines apart (stage 3
  to 4 lowered the instructions) is code placement: with the final
  binary L1 i-cache misses fell (387 -> 268 a statement), iTLB misses
  too (125 -> 54), branch misses rose by 22.
- `pts.sh` (20,000 point selects by the simple protocol, wall / server
  CPU ms, means of 5): round 1 690.8 / 642.2 against 705.0 / 654.6, round
  2 694.4 / 646.0 against 709.6 / 660.8 (+2.0% to +2.3%): the cycles above.
- `simple.sh` (pgbench `-M simple`, 4 clients, 10 s): point select
  50,821 and 51,270 tps against 49,992 and 50,017 (-1.6%, -2.4%); update
  9,222 and 9,239 against 9,269 and 9,320 (+0.5%, +0.9%); the 3-table
  join 19,695 and 19,765 against 20,042 and 20,071 (+1.8%, +1.5%).

The instruction gates pass (point select, INSERT and UPDATE fewer); the
point select's cycles over the wire do not, by placement; left for the
owner's call (6.3.Q8's first part met the same: its stage 3 read q9, q13,
q17 slower at main's instructions).

### 6.3.Q8 R2 as built (2026-11-21)

R2 of 6.5: the small arms. Branch `worktree-agent-abb792d96b0d125de` from
main 757c4cee. `SET lexdb_batch = off` (the row engine, the tests'
reference) is untouched, and no row-engine code was deleted: all of it is
still reached (6.4 after R2).

**Commits and line counts:**

| commit | what | `lexdb_exec` | other |
|---|---|---:|---|
| main 757c4cee | | 19,838 | `lexdb_pipe` 7,553, `lexdb_plan` 8,301, `lexdb_bind` 2,256 |
| 9a41dfee | a recursive CTE's working table as held rows; test `exec_arms` | 19,857 | `lexdb_plan` 8,304 |
| 4524ea6e | no FROM: a Result arm (`runResult`), `lexdb_bind.evalMark`, `Prog.run` | 19,899 | `lexdb_pipe` 7,664, `lexdb_plan` 8,385, `lexdb_bind` 2,273 |
| d5e0cc71 | MIN/MAX by the scan's order (`MinMax`, `aggFirst`) | 19,903 | `lexdb_pipe` 7,753, `lexdb_plan` 8,391 |
| 9aaf659d | OFFSET on streamed rows (the Limit skips) | 19,903 | `lexdb_pipe` 7,786, `lexdb_plan` 8,401 |
| 0866529f | DISTINCT ON, WITH TIES, TOP n PERCENT and WITH TIES in the Sort (`SortSt.cutOf`) | 19,905 | `lexdb_pipe` 7,835, `lexdb_plan` 8,414 |
| 6c770081 | tests `tds_arms` (SQL Server 2022's answers), `tns_arms` | 19,905 | |
| 93707dc9 | a collation's GROUP BY keys and calls, row by row | 19,905 | `lexdb_pipe` 7,850 |
| 9d521027 | a point select's planning back to main's instructions (pipeShape's TOP test; no Limit arm for TOP) | 19,906 | `lexdb_plan` 8,413 |

`lexdb_exec` +68: `pipeResult` (eval's outputs need exec's `eval`, `Env`
and `runSubs`), `workRows`/`workLen` (the run's cache), `pipeTake`,
`PSort`'s new fields, EXPLAIN's MinMax line; the arms are the pipeline's
and the plan's.

**The arms, in the order of the census runs they cover** (6.4's runs at
main 757c4cee: the suite, batches on):

- **A recursive CTE's working table** (47,240 runs, 44 statements): the
  recursive part's first level is rows the run holds (`heldRead`; its
  `PScan.held` past the query's subqueries; the rows the round before
  added copied from the run's cache, as `prepare` copies them:
  `workRows`), row by row under 64 rows, in batches from 64. A join over
  a few of them is the row engine's, as a join over a few held rows of a
  subquery is (`heldSmall`): those runs now show as "gave way at the
  run".
- **No FROM** (42,883 runs, 842 statements): a Result arm, `Limit?
  (Project (Filter? (Result)))` (`lexdb_plan.resultShape`, `resultPlan`;
  `lexdb_pipe.runResult`): its WHERE (`Query.top`) bound for the plan,
  then its outputs evaluated (an error in one is the statement's, as the
  row engine raises it, under LIMIT 0 too), its one row given unless the
  LIMIT, OFFSET or the run's cap leaves it out; its subqueries run once
  first. Not with ORDER BY (its keys are evaluated on the one row and may
  fail), grouping, a window, a set, a lock, TOP, WITH TIES, SELECT @v, a
  set-returning function or a correlated subquery left in it. An output
  or condition that does not bind (a sequence, session or catalog
  function's call: `nextval`, `current_setting`, `pg_backend_pid`,
  `current_schema`, ...) is marked (`lexdb_bind.evalMark`, way `FN_EVAL`)
  and evaluated by `eval` in the session at the run (`pipeResult`'s hook;
  `Prog.run` `PR_EVAL`); not with a subquery in it (eval would not see
  the subquery's value: the row engine's then). Tried first: binding
  those calls for the scalar evaluator, with the session in the
  evaluator's context (`Ctx`): an `Option` of a store handle there cost
  every point select 18 instructions (its drop; an `int` field cost 1, an
  array 62), and a registry of sessions by token cost `nextval` 1,600; the
  mark costs neither. Binding an output bindSel did not bind cost
  `nextval` as much again (bindIn's failed call binding): an output
  without a subquery that bindSel did not bind is marked without trying.
  `Prog.run` (`PR_*`, set once by the planner) also holds the point
  select's test (no subquery, no join, `pointRead`), made per run before.
- **MIN or MAX by the scan's order** (`Sel.first`; 10,689 runs, 273
  statements): `Agg (MinMax (Filter (Scan)))` over one table
  (`aggFirst`): the scan in its path's order through the conditions and
  the column's `IS NOT NULL` (added by `pipeAgg`, dropped by `unplan`),
  the first row only (LIMIT 1), the calls accumulating it, as the row
  engine's one group. Its scan is an aggregate's (`scanArm(q, true)`): an
  index's IN list is read in batches, which the row engine's batch driver
  read row by row (`exec_batchindex`'s look: alone 79 -> 82, with rows
  113 -> 114), and EXPLAIN ANALYZE's counts are the batch driver's
  ("rows read 1, kept 1, batches 1"). EXPLAIN as the view's (no
  "aggregate" line). Over joins: the row engine's (2 runs).
- **OFFSET** on streamed rows (135 runs; `offsetShape`): the pipeline's
  Limit reads limit + offset rows and gives those after the offset (a
  chunk the offset cuts given row by row; a point select's offset goes to
  `run`); not over joins (3 runs). The skipped rows' outputs are
  evaluated, as the row engine's and PostgreSQL's (SQL Server's are not:
  `tds_arms` leaves that case out).
- **DISTINCT ON, FETCH ... WITH TIES, TOP n PERCENT, TOP n WITH TIES**
  (36 + 12 + 2 runs): the pipeline's Sort when sorted (`PSort`'s `don`,
  `ties`, `pct`, `top`): every row held (no top-N), then cut as
  `execSelIn` cuts them (`SortSt.cutOf`): DISTINCT ON's first row of each
  run of equal leading keys, the OFFSET, then LIMIT, TOP n or n PERCENT
  rounded up (TS1031 outside 0..100), WITH TIES the rows that sort as the
  last given. Under a run's cap of 1 (EXISTS) nothing is sorted and, as
  the row engine's, every row ties.
- **A collation's GROUP BY keys and calls** (10 + 7 runs): `PAgg.kinds`,
  `PCall.kind`: a collated key groups by its collated value
  (`lexdb_sort.collVal`, as `addToGroup`), a collated call (count(DISTINCT
  c), min, max) compares by its collation (`lexdb_agg`'s spec kind); such
  an aggregate runs row by row (`exactAgg`: not the batch kernels), over
  one table or joins; not in grouping sets (3 runs).

**Left, and why:**

- A set-returning function in the select list (22 runs): its expansion is
  exec's (`expandSrfs`) after the rows, before ORDER BY and LIMIT; taking
  it means a ProjectSet operator in the pipeline, or a test in
  `pipeHeld` every point select would pay. With R3 (a function's rows).
- A collation's hash join key (6 runs): the join's hash (`bKeyEnc`, the
  probe's keys) is built from batch columns by value; a collated key
  needs its collated value on both sides in the kernels. With R4.
- The binder raising the row path's errors (`select row_number() from
  emp`, `where count(*) > 1`: 2 runs): raised at bind time they would be
  raised for an empty table too, where the row engine (the reference)
  raises nothing; a behaviour change for both engines, the owner's call.
- Outputs and conditions that do not bind over a table (721 runs: catalog
  and session functions, `::regclass`, `nextval(x)` per row, ...): a
  table's rows are evaluated by the scalar evaluator or in batches, which
  the evalMark hook does not reach (the order of `nextval` across a
  batch's outputs is not the row engine's); case by case, with R3's
  catalog relations.
- Found on the way, dialect gaps (both engines alike): the T-SQL door does
  not run a recursive CTE in T-SQL's form (`WITH r(n) AS (... UNION ALL
  ... FROM r)`: 208), nor the Oracle door Oracle's (ORA-00942); the Oracle
  door has no `FETCH FIRST n PERCENT ROWS` (ORA-00900).

**The census again** (6.4's tool, the final tree; main 757c4cee's run of
257 tests against the branch's 260, the three new tests' lines left out;
batches on):

| engine | main 757c4cee | R2 |
|---|---:|---:|
| the pipeline's rows | 195,747 | 280,987 |
| the pipeline's groups | 791,046 | 801,752 |
| the row engine | 159,490 | 58,603 |
| a write's rows found | 3,027 | 3,033 |
| a set operation | 553 | 553 |
| batches off | 747,634 | 747,634 |

- R2's rows of 6.4 fell by 101,006 runs: those above, less the 8 left
  (MIN/MAX over joins 2, OFFSET over joins 3, a collated key in grouping
  sets 3).
- Grown, by R2's statements showing their next reason: "gave way at the
  run" +115 (`exec_index_diff`'s and `exec_with`'s recursive CTEs joining
  a working table of a few rows: the row engine joins them, as before),
  a join under a stopping first table +2, a set-returning function in the
  select list +2. Nothing else moved; the writes' +6 are `exec_turns`',
  whose run counts depend on the clock (its turns).

**Tests.** 257 of 257 at main, 260 of 260 at every commit (new:
`exec_arms`, `tds_arms`, `tns_arms`). `exec_arms` runs every statement
with batches on and off (the same rows or error; a write's table after it
the same): recursive 13, no FROM 34, MIN/MAX 17, OFFSET 15, sort variants
16, collations 9 (all the same, and the pipeline's but EXPLAIN's two and
one IN subquery unnested). `tds_arms`' answers are SQL Server 2022's (the
`lxl-mssql` container, a database of its own, dropped after); `tns_arms`'
are lexdb's (no Oracle at hand). Expectations changed: `exec_held`
(refused: 5 held, 4 batched), `exec_subbatch` (DISTINCT ON and WITH TIES
not the batch driver's: no `s`), `exec_batchindex` (alone 82, with rows
114).

**Gates.** In process (`LXL_HASH_SEED=1`, the 1-statement run subtracted
from the 20,000 one, instructions a statement; the table loaded with
batches off in both builds; INSERT and UPDATE in one transaction on the
simulated disk; two rounds alternated, main 757c4cee against the branch):

| statement | main 757c4cee | R2 | |
|---|---:|---:|---:|
| point select | 119,543.8 | 119,541.8 | -2 (0866529f read 119,545.8: +4, its TOP test in planning; fixed, 9d521027) |
| INSERT VALUES, one row | 106,271.9 / 106,272.0 | 106,271.7 / 106,271.8 | -0.2 |
| UPDATE ... WHERE id = k | 148,293.3 / 148,293.3 | 148,293.3 / 148,293.3 | 0 |
| `select 1` | 46,333.0 / 46,333.0 | 45,418.0 / 45,418.0 | -915 (-2.0%) |
| `select nextval('s')` | 132,425.9 / 132,186.9 | 132,017.6 / 132,047.1 | -270 (the sequence's writes spread its counts by about 250 a run) |

By commit (point selects, the same harness): 9a41dfee and before main's,
4524ea6e to 9aaf659d 119,541.8, 0866529f 119,545.8, 9d521027 119,541.8.
On the way the Result arm's first forms cost what 6.3.Q8 R2's "No FROM"
says (a session in `Ctx` +18 a point select, a registry +1,600 a
`nextval`, binding again what bindSel had not bound +1,600 a `nextval`):
none of them is in the branch.

Over the wire (`pts.sh`, 20,000 point selects by the simple protocol,
wall / server CPU ms, means of 5, three rounds alternated, both `-O`;
`~/tpch-w/r2/logs`): main 749.6 / 695.2, 789.6 / 730.4, 760.8 / 702.0;
R2 742.8 / 684.6, 752.6 / 695.4, 750.6 / 693.0: server CPU -1.5%, -4.8%,
-1.3% (R1's +1.7% of placement did not come back here; instructions are
level).

TPC-H (base 757c4cee and the branch's final binary, `-O`, alternated
twice, one run each, `TPCH_REF` 1744ef99, `~/tpch-w/r2`; best of the
two): checksums equal on all 22 in all four runs; 12,203 against 12,227
ms (1.002). Over 1.5%: q5 +2.6%, q8 +2.8%, q10 +2.1%, q13 +2.1%, q15
+4.2% (its rounds 639 / 675 against 666 / 690 ms); their server
instructions (`iq.sh` over `~/tpch-w/r2`'s copy of the data): q5 -0.05%,
q8 -0.01%, q10 -0.003%, q13 +0.016%, q15 +0.005%: code placement. Faster
by over 1.5%: q1 -2.1%, q18 -2.5%, q21 -1.5%, q16 -1.5%. R2's arms are
not in TPC-H's 22 (their statements' plans did not change).

### 6.3.Q8 R6 as built (2026-11-21)

R6 of 6.5: Apply for RUN_PER_ROW. Branch `worktree-agent-ae36805e4cd1b098e`
from main 757c4cee. `SET lexdb_batch = off` (the row engine, the tests'
reference) is untouched, and no row-engine code was deleted: the per-row
subquery runs (`fillCur`, `runSub`, the memo) are what the Apply calls.

**Commits and line counts:**

| commit | what | `lexdb_exec` | other |
|---|---|---:|---|
| main 757c4cee | | 19,838 | `lexdb_pipe` 7,553, `lexdb_plan` 8,301, `lexdb_bind` 2,256 |
| f5eafcb1 | the Apply; `bxFold`, `foldConds`; `hasJoin`'s arms reordered; tests `exec_apply`, `tds_apply`, `tns_apply`; seven tests' counters | 19,935 | `lexdb_pipe` 7,732, `lexdb_plan` 8,545, `lexdb_bind` 2,354 |
| 304c898b | a 9.9 hashed probe declined in the plan (`hashedProbe`), not by compile; the new code moved to its modules' ends (the point select's iTLB misses, below) | 19,933 | `lexdb_pipe` 7,734, `lexdb_plan` 8,558, `lexdb_bind` 2,356 |

exec's +95 is the glue that needs a `Run` (`runApplyJ`, `pipeGroups`'
ask, `applyTrue`, `applyCtx`, `budBack`) and `levelRows`, taken out of
`runPipe` for both its callers.

**What it does.** A query whose correlated subqueries left per row
(`q.corr`) are all called in the WHERE conjuncts of one level is the
pipeline's (`lexdb_plan.applyLevel`: that level's last conjuncts,
`subsLast`; not in a path's key, a hash's value or build condition, an
outer join's ON, a semi, anti or mark level, a build group's level,
conditions on no table, a 9.9 hashed probe; for an aggregate not in a key
or argument; `applyWhy` names the census's reason otherwise). Its plan is
its joins (none or more) under a new arm `PPlan.Apply(input,
PApply{level, reads})`, under the Project or the Agg, its scan's per-row
subqueries `RUN_APPLY` (EXPLAIN prints them "per row", as before); the
joins' arms leave the Apply's conjuncts out (`planCondsA`, `applied` in
`joinsOver`).

- **The pipe** (`lexdb_pipe`) runs every Apply plan as joins (`hasJoin`;
  `runJ`, `runAggJ`; its first table may be read row by row, `joinOpsIn`).
  `joinFrom`, entering the level after the Apply's (`JRun.apAt`), gives the
  rows joined so far to its consumer as an ask (`applyFrom`: a batch of
  the Apply's columns and one column more, `askOf`); the consumer
  (`runJProj`'s, `aggJoin`'s) gives each row to `ask` and puts the places
  of those that pass in that column (`askRows`); those rows are joined on.
  The pipe never calls exec: `ask` is a closure parameter of `runJ`,
  `runAggAny` and `runAggJ`, and the ask reaches the consumer through the
  `out` closure the joins already pass down, so no other signature
  changed.
- **Exec**'s `ask` is `applyTrue`: the level's correlated conjuncts in
  order through `evalX`, as the row engine's `allTrueX` evaluates them
  (`fillCur`: each subquery of the conjunct run for the row's outer
  values, eagerly, under a CASE too, the results kept per outer values in
  the run's memo, MEMO_MAX; then the conjunct). So the same rows, errors,
  subquery runs and cache hits: EXPLAIN ANALYZE's counts are the row
  engine's (the rows the Apply drops are taken off its level's joined
  count; `exec_apply` checks it). `runApplyJ` and `pipeGroups` give the
  run's context the subqueries' values copied, not moved (`applyCtx`), and
  the pipeline a copy of the run's budget, adding back what the
  subqueries' runs held and ticked meanwhile (`budBack`).
- **Order and errors.** The Apply's conjuncts are their level's last, so a
  row meets the level's other conditions first, as in the row engine. A
  chunk's rows are asked in order; an error (a subquery's, its outer
  values', the conjunct's) goes back through the join, which joins the
  chunk again row by row (a rows plan, `joinChunk`'s exact mode), each row
  then asked alone before its later levels. Under a LIMIT that stops the
  scan (the plan's, or an EXISTS's or a scalar subquery's cap) each first
  row is joined and asked alone (`Apply.one`): no row past the limit is
  asked. With an Apply no hash is cut by a later level's (`reduceHashes`),
  and at the first level the first hash's key does not narrow the scan
  (`pushCol`): no row the Apply would ask is dropped before it.
- **Constants once.** A correlated subquery's conditions bound for the plan
  have their constant operators folded once, at plan time
  (`lexdb_bind.bxFold` from `lexdb_plan.foldConds`, `bindQuery`): a
  unary, binary or cast over constants whose evaluation reads no time zone
  (the zone's closure not called; a text cast to an interval or a time)
  and gives no error. q20's `date '1994-01-01' + interval '1 year'` was
  evaluated by `bCompile` per run (`parseIval`, `castTo`: about 3% of q20).
- **Not taken** (the row engine's as before, under their reasons in 6.4):
  a correlated subquery in the outputs or ORDER BY (the row engine
  evaluates those after the scan, from its rows kept: their errors come
  after the WHERE's), conjuncts of two levels, a hashed probe, LATERAL, a
  path's key.

**Measured.** Census (6.4's tool, the 257 tests of main, the three new
ones' lines left out; TPC-H's 22 once through a census build):

| engine | main 757c4cee | R6 |
|---|---:|---:|
| the pipeline's rows | 189,344 | 201,032 |
| the pipeline's groups | 791,049 | 792,082 |
| the row engine | 159,618 | 151,912 |
| a write's rows found | 3,019 | 3,033 |
| TPC-H, the row engine | 4 | 1 (`select 1`) |

- R6's rows of 6.4 ("a correlated subquery left per row", 34,674 runs
  at main with its "agg:" variant) now name why they stay (`applyWhy`):
  LATERAL 20,189 (a function in FROM over outer values, nearly all one
  statement, `select (select count(*) from big(t.v)) from t`: R3's), a
  9.9 hashed probe 6,157, a path's key 157, a hash's key or build
  condition 50, not in WHERE 20, conjuncts of two levels 9. The rest are
  the pipeline's: its rows +11,688 runs, its groups +1,033; a recursive
  CTE's working table +384 (correlated queries inside one now show that
  reason first). Nothing else moved by more than 14 runs.
- "a correlated subquery in the outputs or ORDER BY" (6,331 runs) is
  unchanged: the row engine evaluates those after the scan (`late`), and
  an Apply over the rows as they are read would move their errors before
  the WHERE's of later rows.
- TPC-H: q2's and q17's outer queries and q20's partsupp subquery are the
  pipeline's; the row engine's one run left is a `select 1`.

TPC-H (SF1, base 757c4cee and the branch, `-O`, alternated twice, one run
each, `TPCH_REF` 1744ef99, `~/tpch-w/r6`; best of two, ms): with
304c898b checksums equal on all 22, 11,929 against 12,030 ms (1.008);
f5eafcb1 (before the
code moved and `hashedProbe`) 12,109 against 11,999 (0.991). Over 1.5%
in the final round: q15 +4.9%, q9 +3.1%, q13 +1.8%, q16 +1.7%, all with
the server's instructions equal (`iq.sh`: q9 15,679.7M against 15,679.4M,
q13 4,878.7M / 4,877.4M, q15 4,022.6M / 4,022.6M, q16 2,220.6M /
2,220.1M) and their slow runs the branch's second round (q15 728 against
656, q18 764 against 717, q19 112 against 95); in f5eafcb1's rounds q9,
q15 and q16 were 0.975, 1.006 and 0.991 (q13 1.042, again at equal
instructions). Warm (`qtq.sh`, a first round) q9 1,504 -> 1,488 ms, q13
655 -> 647, q16 202 -> 203.

| query | main | R6 | | PostgreSQL, one core | server instructions (`iq.sh`) |
|---|---:|---:|---:|---:|---|
| q2 | 48.9 | 41.8 | 0.855 | 167 | 383.98M -> 363.50M (-5.3%) |
| q17 | 34.7 | 28.5 | 0.821 | 564 | 246.60M -> 154.67M (-37.3%) |
| q20 | 284.3 | 280.4 | 0.986 | 133 | 1,751.0M -> 1,671.0M (-4.6%) |

Warm medians (`qt.sh`: a warm server, each query 7 times, two alternated
rounds): q2 39.7 -> 35.0 ms, q17 28.8 -> 24.3, q20 234.0 -> 216.7.

**q20's runs, measured** (a profile of 10 warm runs, `LXL_NATIVE_MAP`):
the 8,508 runs are 81% of q20; inside them the 63,832 lineitem rows by
primary key (`getManyIn` 47%, its `fingerTo` 17%) and the index ranges
(`scanLeaves` 8.5%); the per-run setup about 25% (exec's `runChild`,
`execSelIn`, `prepareIn` 4%, `pipeSrcQ` and `pathScans` 3%, `bCompileD`
2.8% after the fold, from 4.9, the aggregate's state 2.6%, allocation
5%). R6's instructions are 4.7% fewer, its time about level: the rows by
key, each from a different leaf of lineitem's tree, are the cost. Batching
them (a chunk's distinct outer values run as one grouped read of the
index's ranges, their rows read in key order across the chunk) is the
batched dependent join of 6.1's table; not built: none of today's paths
reads them so (a lookup list of 2,127 parts plans a full scan, past
`inMax`; the join by the index, 51.7, is 336 ms against 205 for the runs,
its rows read per outer row), and with the keys sorted per chunk of
~1,000 runs (~7,600 rows of 6M) each row is still in its own leaf (about
790 rows apart), so what it saves is the finger's descent above the
leaves (part of `fingerTo`'s 17%), not the leaf reads; the per-run setup
(~25%) it would save too. The gap to PostgreSQL's 133 ms stays the rows'
reads and the setup.

**Gates.** Suite 260 of 260 (new: `exec_apply` 36 queries with unnesting
off, each with batches on and off, the same rows or error: 32 through the
Apply, a hashed probe's and the three that stay the row engine's (outputs,
two levels, ORDER BY) not; EXPLAIN ANALYZE's counts as the row engine's;
`tds_apply` 13 T-SQL batches with SQL Server 2022's answers, all 13
through the Apply;
`tns_apply` 13 statements with Oracle Database 23ai Free's answers, the
`lxl-oracle` container, all 13 through the Apply). Expectations changed
(counters only, the same rows): `exec_sub` (EXPLAIN ANALYZE's
"batches 1"), `exec_subrows`, `exec_unnest`, `exec_unnest_agg`,
`exec_narrow`, `exec_semijoin`, `tds_unnest`, `tns_unnest` (more queries
piped).

Point selects, single-row INSERT, UPDATE by key (in process,
`LXL_HASH_SEED=1`, the 1-statement run subtracted from the 20,001 one,
alternated twice): point select 130,370.5 -> 130,366.6
(-4.0), INSERT VALUES of one row 94,864.0 -> 94,864.0, UPDATE ... WHERE
id = k 131,207.0 -> 131,207.0. On the way: a test for the Apply in
`planConds`' loop cost a point select 42 instructions (a function of its
own, `planCondsA`), the Apply's arm in `opsOf` and `hasJoin` and the
`q.corr` tests 19 more; `hasJoin`'s arms reordered (Scan, Project and
Filter first: they are compared in order) paid them back.

Over the wire: f5eafcb1 read `pts.sh` +5.6% server CPU (665.7 -> 702.9
ms, means of 15) at the same instructions (`icount.sh`: 187,134 / 187,008 against 187,083 / 186,980 a
statement), cycles +3.5% / +2.6%, with iTLB misses 46 -> 145 a statement
(L1 i-cache misses 409 -> 320, branch misses 423 -> 409): the new code in
the middle of the modules spread the point select's path over more pages.
With it moved to the modules' ends (304c898b): `icount.sh` instructions
186,971 against 187,077 a statement (within its ~100), cycles 106,650 against 104,639, iTLB misses 105 against
38 (the base's own vary from 46 to 105 between server starts), i-cache
misses 360 against 324; `pts.sh` (points.sql, three rounds, server CPU
ms, means of 15): 715.1 -> 692.7 (-3.1%), wall 773.5 -> 749.7.

**Merged with R2** (main 3b462107): the Apply is not taken under R2's OFFSET, TOP PERCENT or WITH TIES (`applyR2`), nor under MIN/MAX by the scan's order (`aggShape`): each stops early, and the Apply's first-row asks (`Apply.one`) were built for a plain LIMIT; such queries stay the row engine's, as before both.

### 6.3.Q8 R3 as built (2026-11-21)

R3 of 6.5: a function in FROM as the pipeline's source, a set-returning
function in the select list, set operations finished by `lexdb_setop`,
MATCH_RECOGNIZE fed by the pipeline. Branch
`worktree-agent-a3fe187488aaca949` from main 5f30415d. `SET lexdb_batch =
off` (the row engine, the tests' reference) is untouched: its paths stay
(`execSrf`'s arguments by `eval`, `expandSrfs`, `runSet`'s row tail,
`runLevel`'s LATERAL arm), now the reference only for these shapes.

**Commits and line counts:**

| commit | what | `lexdb_exec` | other |
|---|---|---:|---|
| main 5f30415d | | 20,092 | `lexdb_pipe` 8,049, `lexdb_plan` 8,682, `lexdb_setop` 488 |
| 00922cf8 | (1) a function in FROM as a source, `lexdb_srf` (new, 248: `execSrf`'s rows moved out of exec, `expandSrfs`' expansion); LATERAL at the first level over outer values; test `exec_r3` (from, lateral) | 20,055 | `lexdb_plan` 8,772 |
| afd7fc39 | (3) a held set operation's ORDER BY, OFFSET and LIMIT by `lexdb_setop`; `exec_r3` (set operations) | 20,118 | `lexdb_plan` 8,780, `lexdb_setop` 542 |
| 745d53bd | (2) a set-returning function in the select list with no FROM: `PPlan.ProjectSet` over a Result; `exec_r3` (select list sets) | 20,134 | `lexdb_pipe` 8,088, `lexdb_plan` 8,816 |
| 613c1e9a | (4) MATCH_RECOGNIZE's input from the pipeline; `exec_r3` (match_recognize) | 20,134 | |
| d53afcf0 | (3b) the held set tail and its bytes into `lexdb_setop.held` | 20,104 | `lexdb_setop` 571 |
| ca4200dd | (5) planning's instructions (below) | 20,104 | `lexdb_plan` 8,822 |
| fa33c527 | (6) tests `tds_r3` (SQL Server 2022's answers), `tns_r3` (Oracle Free's, `gen_oracle.py --check`) | 20,104 | |
| 0601105c | (7) a held set sorted as a SELECT's held rows are (typed keys), not by the pipeline's chunked sort | 20,104 | `lexdb_setop` 594 |

`lexdb_exec` +12: `execSrf`'s rows (-150) moved to `lexdb_srf`; what
stays needs a `Run` or the session: `pipeFunc`, `srfRows` (the catalog's
relations and a sequence's state read the store), `lat0Rows`,
`lat0Refs`, `lat0Memo` (`runChild`, `eval`, the run's memo), `pipeSub`,
`srfPipe`, `setHeldRes`; `srfRows` beside `execSrf`, the others at the
module's end.

**What it does.**

- **A function in FROM** (generate_series of integers, numerics and
  timestamps, unnest, regexp_matches, regexp_split_to_table,
  string_to_table, VALUES, pg_partition_ancestors, the catalog's
  relations, a sequence's state) gets a program of its own
  (`lexdb_plan.funcProg`: `Project (Func)`, the Project's expressions its
  arguments bound for the plan, `PR_FUNC`), made in `pipeSelMain`'s
  declined path when every argument binds (a sequence's or a session's
  call, a catalog cast such as `::regclass` do not: the row engine's).
  Its run with batches on (`pipeFunc`) runs its subqueries once,
  evaluates the arguments by `bxEval` and makes the rows; the row
  engine's `execSrf` evaluates them by `eval` and makes the same rows.
  The rows are made by a new module, `lexdb_srf` (imports values only:
  a series' end by its step's sign and its type's range, a zero step,
  arrays side by side padded with NULL, VALUES' coercions and T-SQL's ''
  as 0, the bytes and steps counted through its caller's hook); the
  catalog's relations and a sequence's state stay exec's (`srfRows`).
  The rows reach the query that reads them as any subquery's (held,
  `lexdb_held`), in FROM or as a join's level. A series made as it is
  read (`lazySeries`) never runs its Sel: it is not planned for the
  pipeline (`pipeSub`; its arguments' subqueries are).
- **LATERAL at the first level over outer values** (`lexdb_plan.lat0`: a
  correlated derived table or function a query reads first, nothing
  else of the query run per row): with no level before it its outer
  values are the run's, so the pipeline runs it once a run before the
  query (`lat0Rows`, as `runLevel`'s LATERAL arm runs it for the first
  row: its outer values evaluated with no row, its rows' bytes held as
  the memo holds them) and reads its rows as a FROM subquery's
  (`lat0Read`; the plan's subquery marked run once, `lat0Once`, in
  `applyOver`, which only a correlated query reaches). A run that gives
  way to the row engine (a join over fewer than 64 held rows) leaves
  the rows in the run's memo (`lat0Memo`), so the subquery is not run
  twice. 6.4's LATERAL row (after R6) was nearly all this shape:
  `exec_limits`' `select count(*) from big x where (select count(*) from
  (select s.id from small s, small t where s.id <> x.id) q) > 0`, 20,000
  runs of its subquery; `select (select count(*) from big(t.v)) from t`
  ran 4.
- **A set-returning function in the select list with no FROM** (unnest,
  generate_subscripts, regexp_matches, regexp_split_to_table,
  string_to_table, pg_partition_ancestors, which psql's \d asks in an
  IN): its Result under a new operator, `PPlan.ProjectSet`
  (`lexdb_plan.srfShape`, `srfPlan`, offered in `pipeSelMain`'s declined
  path, so a SELECT with no FROM pays no test; `lexdb_pipe.resultSet`):
  the one row's sets made rows in lockstep, the shorter padded with
  NULL, none if every one is empty (`lexdb_srf.expand`, PostgreSQL 10's
  ProjectSet; the row engine's `expandSrfs` uses it too), at most the
  run's cap (a scalar subquery's second row: 21000). Not under LIMIT,
  OFFSET or DISTINCT, which apply to the rows made, nor over a table (a
  scan's outputs are evaluated in batches, where a set's value is not its
  column's type): those stay the row engine's.
- **A held set operation** (a subquery's, a derived table's, a CTE's,
  INSERT ... SELECT's, a recursive CTE's result, and a statement's where
  `streamsSet` declines: a part's values coerced, `select 2 union select
  2.0`): its parts run and combine as before (`runSet`, `combine`: the
  left part, then the right, so the first error is the same); its ORDER
  BY, OFFSET and LIMIT are `lexdb_setop.held`'s: the rows' ORDER BY
  values (by their collations) sorted by `lexdb_sort`'s typed keys, as a
  SELECT's held rows are (a stable comparison sort when a key's values
  are of mixed kinds), then `cut`; the bytes held as the row tail holds
  them (those values), no longer `execSelIn`'s row tail. Not with TOP or
  WITH TIES (`setHeld`). (R3 (3) fed the pipeline's set sort, `setSort`,
  row by row and read its chunk back: about 1,300 instructions a row
  more; (7) replaced it.)
- **MATCH_RECOGNIZE**: its input Sel is offered to the pipeline as any
  (`pipeShape` no longer declines `Sel.mr`); `execMatch` with
  `lexdb_match` stays the row operator over the input's rows.

**Left, and why:**

- A LATERAL level after the first (`from t, lateral f(t.v)`, CROSS
  APPLY: 180 runs): a dependent join, its subquery run per row of the
  levels before; with R4's joins (the Apply's ask gives a row's pass or
  fail, not its rows).
- A set-returning function over a table, or under LIMIT, OFFSET or
  DISTINCT (1 run in the suite). The row engine applies DISTINCT before
  it expands (`select distinct unnest(array[2, 1, 2])` gives 2, 1, 2;
  PostgreSQL 1, 2), and a set inside an expression is not one
  (`unnest(array[1, 2]) / 0`: 42883): both engines alike, found here, the
  reference untouched.
- `select generate_series(1, 3)`: neither engine has generate_series in
  the select list (42883, batches on and off); PostgreSQL does. Not
  added: a function, not an engine's path.
- A function whose argument does not bind (13 runs, all of psql's \d
  footer query, `pg_partition_ancestors` of a literal OID: its regclass
  is a catalog lookup), and outputs that do not bind over a catalog
  relation (psql's \d column query's `format_type`, `pg_get_expr`): R2's
  "outputs that do not bind".
- TOP and WITH TIES over a set operation (2 runs).

**Measured.** The census: 6.4's "After R3". The gates:

In process (`LXL_HASH_SEED=1`, the setup's run subtracted from the
20,000-statement one, 200 for the catalog's and the set operations';
INSERT and UPDATE in one transaction on the simulated disk; main 5f30415d
against the branch alternated, two rounds (alike within a tenth of an
instruction); the set operations' at 0601105c, one round, the others
at fa33c527, the same code for them):

| statement | main 5f30415d | R3 | |
|---|---:|---:|---:|
| point select | 135,388.7 | 135,371.7 | -17 |
| INSERT VALUES, one row | 98,994.0 | 98,994.0 | 0 |
| UPDATE ... WHERE id = k | 135,808.4 | 135,808.4 | 0 |
| `select 1` | 45,001.0 | 44,983.0 | -18 |
| `select generate_series(1, 3)` (42883 in both) | 81,808.5 | 81,790.5 | -18 |
| `select * from generate_series(1, 3)` | 111,733.0 | 110,952.0 | -781 |
| its EXPLAIN (planning) | 99,105.0 | 98,715.0 | -390 |
| `select unnest(array[1, 2, 3])` | 120,676.0 | 118,192.0 | -2,484 |
| `select count(*) from pg_class where relkind = 'r'` | 2,020,575.9 | 2,020,168.0 | -408 |
| `select attname, atttypid from pg_attribute where attrelid = 'p'::regclass and attnum > 0 order by attnum` | 588,109,358.7 | 588,106,292.0 | -3,067 |
| psql's \d column query (pg_attribute, two subqueries per row) | 595,463,811.6 | 595,449,985.8 | -13,826 |
| a derived table's UNION, ORDER BY, LIMIT 40 (100 rows) | 836,045 | 789,659 | -5.5% |
| an IN over a UNION ALL | 1,820,258 | 1,796,068 | -1.3% |

On the way, each found by these counts and fixed before hand-back: a
fourth field in `PPlan.Func` (the bound arguments) cost every SELECT
from a function +84 (an empty array made and dropped by every view's
Func: now a Project over the Func in the program only); planning a lazy
series' Sel for the pipeline +588 (`pipeSub`: not planned); the lazy
test itself about +300 a call (`lazySeries` read the type through
`oidType`, whose search of the array types was the cost: now the OID;
`heldRead` gains it too, hence the -781); the lateral test in
`scanRuns` +4 a point select's compile (two callee-saved registers: the
subquery is marked run once in the plan instead, `lat0Once`); a match
arm added before an `else` +1 to +2 on `select 1` and the point select
(`pLeaf`'s fall-through: a Scan and a Result now compared first); the
pipeline's chunked set sort +127k a 100-row held UNION (the typed keys
instead). The catalog relations are made whole per statement
(`catRows`: pg_attribute's every column of every relation, 588M
instructions a lookup by `attrelid`); R3 does not change that.

TPC-H (SF1, base 5f30415d and the branch, `-O`, alternated twice, one run
each, `TPCH_REF` 1744ef99, `~/tpch-w/r3`; best of the two, ms): with
fa33c527, checksums equal on all 22 in all four runs, 11,461 against
11,465 ms (1.000); over 1.5%: q3 +1.9%, q15 +6.5% (main's own runs 529
and 568), their server instructions equal (`iq.sh`: q3 4,384.02M ->
4,384.08M, q15 4,022.84M -> 4,022.98M). With the final binary
(0601105c, which changes only a held set operation's sort, in none of
the 22) alternated twice again: checksums equal on all 22 in all four
runs, 11,808 against 11,606 ms (0.983; the branch's first run slow
throughout, q1 1,910 ms, a disturbance of the machine: best of two);
over 1.5%: q1 +1.9%, q12 +2.8%, q22 +2.8%, their server instructions
equal (q1 25,992.4M -> 25,993.9M, q12 14,280.4M -> 14,284.1M, q22
1,771.9M -> 1,771.9M): placement. R3's shapes are not in TPC-H's 22.

Over the wire (base 5f30415d against the final binary, fresh copies of
both, `-O`; `~/tpch-w/r3/logs`): `pts.sh` (20,000 point selects by the
simple protocol, wall / server CPU ms, means of 5, three rounds
alternated): main 685.6 / 639.0, 688.2 / 642.4, 683.0 / 635.6; R3 683.0 /
635.4, 683.4 / 634.6, 679.0 / 631.4 (server CPU -0.6%, -1.2%, -0.7%).
`icount6.sh` (points.sql three times, the server's counts a statement,
alternated twice): instructions 186,861 / 186,867 against 186,908 /
186,902 (+40, within its ~100), cycles 102,720 / 102,933 against 101,655
/ 102,002 (-1.0%), L1 i-cache misses 429 / 432 against 376 / 377, iTLB
misses 35 / 35 against 31 / 33, branch misses 418 / 418 against 384 /
382.

**Tests.** Suite: 268 of 268 at main; the full suite at every commit: 269
of 269 from 00922cf8 to ca4200dd, 271 of 271 from fa33c527 (new:
`exec_r3`, `tds_r3`, `tns_r3`). `exec_r3` runs every statement with
batches on and off (the same rows or error): from 30 (all piped but a
zero step's error), lateral 16, set operations 28, select list sets 18
(16 piped: LIMIT and DISTINCT not; over VALUES the VALUES' run piped, its
expansion the row engine's), match_recognize 8. `tds_r3`: 21 T-SQL
batches, SQL Server 2022's answers (the `lxl-mssql` container, a database
of its own, dropped after). `tns_r3`: 22 statements, Oracle Database
Free's answers (`gen_oracle.py --check tns_r3`: 22 checked, no
difference). Expectations changed: `exec_subrows` (its per-row ALL
subqueries over a derived table the pipeline's: 7 more runs). Found on
the way (both engines alike, dialect gaps): a VALUES text column against
a table's collated one gives 468 (T-SQL); SQL Server and Oracle do not
evaluate a derived table's output nothing reads (lexdb raises its
division by zero); `2 union 2.0` shows 2 where SQL Server shows 2.0; a
parenthesized set operation in FROM gives 50000 (T-SQL), ORA-03001
(Oracle), 0A000 (PostgreSQL's door).

### 6.3.Q8 R4 as built (2026-11-21)

R4 of 6.5: the joins the row engine still ran. Branch
`worktree-agent-a0d20a1cfe28cb753` from main 52fe2606, main 8bf070ae merged in (the compiler's jump tables and bit tests; the gates are against it). `SET lexdb_batch =
off` (the row engine, the tests' reference) is untouched: `runLevel` and
the levels program stay, now the reference only for these shapes.

**Commits and line counts:**

| commit | what | `lexdb_exec` | other |
|---|---|---:|---|
| main 52fe2606 | | 20,104 | `lexdb_pipe` 8,088, `lexdb_plan` 8,822, `lexdb_bind` 2,531 |
| 6fbe8d75 | a join over a point (`PR_POINTJ`, `runPointJ`), a point first table in any join, lookups and ranges under a stopping first table (`joinGrow`), LEFT/RIGHT/FULL with no key, a collation's hash key, `colsRead`/`colsIn`; tests `exec_r4`, `tds_r4`, `tns_r4`; eight tests' counters | 20,133 | `lexdb_pipe` 8,379, `lexdb_plan` 8,847, `lexdb_bind` 2,595 |
| 24b75e65 | the stopping first table's lookups by the point path (`stopRows`) | 20,142 | `lexdb_pipe` 8,439 |
| eeb55ab7 | main 8bf070ae merged (the compiler) | 20,142 | |
| d2d138ad | `PR_STOPJ` (`pipeStopJ`, `runStopJ`): the point join pays no test for it | 20,159 | `lexdb_pipe` 8,479, `lexdb_plan` 8,850 |

`lexdb_exec` +55: `pipeFetchJ` and `pipeStopJ` (their scans need exec's
`pathScan`, `pipeSrcQ`, `Env`, `seqEnv`) and their dispatch in `runPipe`;
the paths are the pipe's.

**What it does.**

- **A join over a point** (the OLTP 3-table join, `simple.sh`'s: a first
  table read by its whole primary key, every table after it looked up by
  its whole primary key, inner or LEFT, no mark): its own path, as Fetch is
  a point select's (6.3.Q8 first part). `compileP` marks the program
  `PR_POINTJ` (`lexdb_pipe.pointJoins`: `Limit? (Sort? | Distinct?
  (Project (Join (... (Filter? (Scan)), JH_LOOK) ...)))`, the first table
  not batched); exec's `pipeFetchJ` makes its one scan (`pathScan`, as
  `pipeFetch`) and `lexdb_pipe.runPointJ` reads the row (`getRow`), then
  each level by the scalar evaluator: its keys by `bxEval`, made keys as
  the row engine makes them (`keyOf`: NULL or out of the column's range,
  no row), its row by `getRow`, its conditions in order, a LEFT JOIN's
  NULL row, its WHERE conjuncts after it, the outputs given (to the Sort
  or Distinct if the plan has one). Counted as the joins count a lookup's
  chunk of one (EXPLAIN ANALYZE as the row engine's); an error is the
  first failing row's. The general join path (`runJ`) for such a chunk of
  one cost 567k instructions a statement against the row engine's 459k;
  `runPointJ` the row engine's (below). Its plan skips `needs` (the rows read whole,
  as the row engine reads them).
- **A point first table in any join** (6.4's "a join's first table not read
  in batches", 6,085 runs, nearly all `exec_unnest`'s nested correlated NOT
  IN): `joinOps` takes a first table read row by row (its points, an IN
  list: `readRows` puts them in batches), as R6 had for an Apply's plan
  only; the `rows` flag is gone. The row engine's levels program
  (`compileLevels`) takes them too.
- **Lookups and ranges per row under a first table that stops early** (a
  LIMIT, an EXISTS's or a scalar subquery's first rows; 329 runs):
  `joinsOver` no longer declines them. Where every table after the first
  is a whole-key lookup, the point path runs them too (`pointJoins`: a
  first table that stops early, `PR_STOPJ`; exec's `pipeStopJ` makes its
  `Src` as `pipeSrcQ` does, a plain scan's batches only, `plainSrc`, and
  `lexdb_pipe.runStopJ` joins it): the first
  table's batches read as the first level's are (an index alone where it
  covers the table's columns, the first batch small), each row joined by
  the scalar evaluator before the next (`stopRows`, `pointFirst`), so no
  row past the LIMIT is joined and EXPLAIN ANALYZE's counts are the row
  engine's. R1's `(select o2.z from f join o2 ... limit 1)` per outer row
  cost 43.1k instructions a run in the row engine, 56k through `runJ`,
  33.6k this way. Other joins under such a table (a range per row, a hash)
  take `runJ`, whose joins (`JRun.grow`: `PScan.stops`, no Apply) join the
  first table's chunk in slices that double from one row (`joinGrow`, the
  width kept across chunks, up to a batch): at most twice the rows the
  consumer takes are joined, where the chunk was joined whole before (a
  hash join under LIMIT 10 probed 670 rows, now 15). An error in a slice
  is the existing exact mode's (the slice joined again row by row), so an
  error in a row past the LIMIT is not raised, as the row engine does not
  reach it; the rows of the chunk after the slice that stopped are not
  counted read or kept.
- **LEFT, RIGHT and FULL JOINs with no key** (25 runs): a hash with no key
  as an inner one's (`crossFrom`), its LEFT JOIN's NULL rows from
  `joinTail`, a RIGHT or FULL JOIN's unmatched rows from the marks as a
  keyed hash's; a LEFT or FULL JOIN over a hash of more than a batch's rows
  (an outer row's pairs in several pieces) joins each row alone
  (`joinFrom`'s one-row path: its candidates in order, its NULL row after
  them), and over an empty hash gives each row its NULL row.
- **A collation's hash join key** (9 runs, R2's left-over): `PJoin.colls`
  (per key, `lexdb_sql.COLL_*`), set for a table's hash of a plain join
  (`MK_JOIN`, not a subquery's rows); both sides' keys are made their
  collated values (`lexdb_sort.collVal`, as R2's GROUP BY keys) in the
  build (`Builder.add`) and the probe (`JK_GEN`), the key's value without
  L2's `#ci`/`#pad` wrapper (`unColl`); the equality stays a condition per
  candidate.
- **Planning a join's plan, cheaper**: the columns an expression reads are
  found by a walk that makes no tree (`lexdb_bind.colsRead`, `colsIn`),
  where `readsOf1`, `allIn` and `lexdb_plan.uses` re-slotted a copy of it
  (`reslot`) and dropped it.

**Left, and why:**

- **LATERAL after the first level** (`from t, lateral f(t.v)`, CROSS and
  OUTER APPLY; 180 runs): a dependent join, its subquery run per row of the
  levels before. It does not fit R6's Apply (the ask gives a row's pass or
  fail, not its rows) nor a nested-loop level of today's arms (their rows
  are a table's or held rows read once). Plan: a join arm `JH_APPLY` whose
  rows come per outer row from the consumer through the ask the joins
  already pass down: `joinFrom` gives the chunk's rows' outer values as an
  ask batch, exec's `ask` runs the subquery per distinct outer values with
  the run's memo (as `runLevel`'s LATERAL arm) and puts the rows back held,
  with each one's outer row (`lexdb_held`), joined on as a hash level's
  candidates; an error joins the chunk again row by row (exact mode), and
  under a stopping first table each row alone (`Apply.one`). Medium (about
  250 lines: plan arm, pipe arm, exec's ask); gated by `exec_r3`'s lateral
  cases and the T-SQL and Oracle doors' APPLY. Census reason as before
  ("LATERAL after the first level (a join per row)").
- **An `= any(array)` lookup** (7 runs): a lookup per element of a row's
  array (coerced to the key's type, unique, in key order, as `pathScans`
  makes an IN list's scans), several probes a row in `fetchMany`. Small,
  not built for 7 runs; its reason stays ("read per row, neither a key
  lookup nor a range").
- A collated key whose value is an expression (`a.c = b.t`, a char and a
  text: the key a cast) gives way at the run (a hash key of values the
  batch keys do not hold, R8's), as other such keys do.
- OFFSET over joins (6 runs, 2 more as stopping first tables now reach it).

**Measured.** The census (6.4's tool; main 52fe2606's run of 271 tests,
`exec_batchexpr`'s and `exec_semilook`'s lines from a second run with
their timeouts raised, as both timed out under the census's writes,
against the branch at 6fbe8d75 with the same two raised, its three new
tests' lines left out; batches on): the row engine's runs 27,495 ->
21,055, the pipeline's rows 306,529 -> 338,144. Gone: a join's first table
not read in batches (6,085), joins under a stopping first table (329),
no hash key not inner (25), a collation's hash key (9; 4 left: a
subquery's rows or a semi join's, "not a table's join"; one more gives way
at the run, `a.c = b.t`'s cast). Grown by their next reason: OFFSET over
joins +2, gave way +2. Nothing else moved. The OLTP runs (`points.sql`,
pgbench's point select, update and 3-table join through a census build in
process): the join is the pipeline's, as the point selects; every UPDATE
still finds its row by `runQuery` (R5). R4's shapes are not in TPC-H's
22 (their plans did not change).

In process (`LXL_HASH_SEED=1`, the 1-statement run subtracted from the
N-statement one; INSERT and UPDATE in one transaction on the simulated
disk; base 8bf070ae against d2d138ad, both built by 8bf070ae's compiler,
two rounds alternated, alike to a tenth):

| statement | main 8bf070ae | R4 | |
|---|---:|---:|---:|
| point select | 119,392.8 | 119,392.8 | 0 |
| INSERT VALUES, one row | 106,115.4 | 106,115.4 | 0 |
| UPDATE ... WHERE id = k | 148,249.1 | 148,249.1 | 0 |
| `simple.sh`'s 3-table join (2,000) | 458,801.9 | 458,783.3 | -19 |
| `(select o2.z from f join o2 on o2.id = f.id where f.xf = o.k limit 1)` per outer row, a run | 43,115 | 33,565 | -22.2% |
| `exists (select 1 from f join o2 ... where f.xf = o.k and o2.z > 100)` per outer row | 43,594 | 33,816 | -22.4% |
| `(select o2.z from o2 join f on f.id = o2.id where o2.id = o.id)` per outer row (a point first table) | 41,146 | 33,595 | -18.4% |

On the way, each found by these counts and fixed before hand-back: the
3-table join through `runJ` (a chunk of one) 567k against the row engine's
459k; with `runPointJ` 473.5k, then `needs` skipped for it (-12.6k), the
columns read without `reslot`'s tree (`colsRead`, `colsIn`: -6k), the first
row by `getRow` and a lookup's `rowRead` without a copied need (-0.6k):
main's. Deciding `PR_POINTJ` in `compileP`'s `how` cost a point select +2
(decided in `needsOf`, which a point select does not reach: 0), the
dispatch before `runSubs` +1 (in the joins' block: 0); `pointJoins`
without compileP's `point` +1 (passed down: 0); the stop path's test in
`pipeFetchJ` and `runPointJ` +130 a join (`PR_STOPJ`, functions of its
own: 0). The per-row subquery over a join under LIMIT through `runJ` cost
56k a run (the row engine's 43k), with its rows fetched by `fetch` 64k
(an index read with its rows, not alone): the first level's batches
instead (`stopRows`), 33.6k.

Over the wire (base 8bf070ae against d2d138ad, fresh copies of both
binaries, `-O`; logs in `~/tpch-w/r4/logs`):

- `pts.sh` (20,000 point selects by the simple protocol, wall / server CPU
  ms, means of 5, three rounds alternated): main 761.0 / 706.2, 744.6 /
  691.8, 744.0 / 690.8; R4 744.8 / 693.0, 735.6 / 685.4, 728.0 / 678.4
  (server CPU -1.9%, -0.9%, -1.8%).
- `icount6.sh` (points.sql three times, the server's counts a statement,
  four rounds alternated): instructions 186,814 / 186,810 / 186,837 /
  186,814 against 187,222 / 186,907 / 186,756 / 186,817 (the first +408,
  the others within the tool's ~100), cycles 106,517 / 106,176 / 104,985 /
  103,827 against 105,439 / 106,473 / 104,225 / 103,583.
- `simple.sh`'s workload with the server's CPU (`~/tpch-w/r4/simplecpu.sh`:
  pgbench `-M simple`, 4 clients, 10 s; tps and server CPU a transaction,
  four rounds alternated): point select 44,883 / 44,087 / 42,388 / 44,751
  against 47,262 / 46,806 / 45,559 / 46,554 tps (+4% to +7%); update 9,113 /
  9,076 / 8,894 / 9,096 against 9,092 / 9,097 / 9,087 / 9,118; **the 3-table
  join 18,700 / 18,643 / 18,401 / 18,403 against 18,366 / 18,563 / 18,283 /
  18,360 tps (-1.8%, -0.4%, -0.6%, -0.2%), 50.57 / 50.75 / 51.47 / 51.44
  against 51.61 / 51.02 / 51.83 / 51.63 us of server CPU a transaction
  (+2.1%, +0.5%, +0.7%, +0.4%)**.
- The join's server counters (`~/tpch-w/r4/icj.sh`: one client, 20,000
  joins, the server under `perf stat` from its start less a run without
  them, two rounds alternated): instructions 471,678 / 471,591 against
  471,681 / 471,821 a join (equal), cycles 216,985 / 222,305 against
  221,189 / 222,698 (+1.9%, +0.2%), L1 i-cache misses 758.6 / 760.2 against
  652.9 / 669.7 (-13%), iTLB misses 21.9 / 21.7 against 27.9 / 27.2, branch
  misses 883.6 / 904.5 against 944.4 / 957.3 (+6%). In process the branch's
  branch misses on the same join are 2.6% fewer than main's (perf record
  of `branch-misses:u`, by function: the differences are as large in the
  parser, whose code is the same, as in the join's: placement).

So the join takes the pipeline at main's instructions and reads fewer
instructions' worth of i-cache, but its cycles over the wire are level to
0.5% more by the branch predictor's aliasing: the gate "should get
faster" is not met, "not slower" is met in instructions and within about
0.5% in CPU; left for the owner's call, as R1's point-select cycles were.

TPC-H (SF1, base 8bf070ae and the branch's final binary, `-O`, alternated
twice, one run each, `TPCH_REF` 1744ef99, `~/tpch-w/r4`; best of the two,
ms): checksums equal on all 22 in all four runs; 12,144 against 12,113 ms
(0.997). Over 1.5%: q8 +2.2% (212.6 against 217.2; the branch's runs 217.2
and 233.7), its server instructions equal (`iq.sh`, two rounds: 1,164.20M /
1,164.15M against 1,164.18M / 1,164.17M); q13 +1.5% (851.4 against 864.1),
4,868.8M / 4,868.6M against 4,868.7M / 4,869.4M: placement. Faster by
over 1.5%: q15 -3.0%, q20 -2.3%.

**Tests.** Suite 274 of 274 at d2d138ad (new: `exec_r4`, `tds_r4`,
`tns_r4`; 271 at main). `exec_r4` runs every statement with batches on
and off (the same rows or error): point joins 32 (66 runs of the point
path), stopping 20 (46), no key 16, collation 8 (one, a FULL JOIN of
derived tables, stays the row engine's: its hash is a subquery's rows).
`tds_r4`: 23 T-SQL batches, SQL Server 2022's answers (the `lxl-mssql`
container, a database of its own, dropped after). `tns_r4`: 22 statements,
Oracle Database Free's answers (`gen_oracle.py --check tns_r4`: 22
checked, no difference). Expectations changed (counters only, the same
rows): `exec_batchjoin`, `exec_batchsort`, `exec_held`, `exec_joinrange`,
`exec_subrows` (more runs piped), `exec_joincost`, `exec_joinreview`
(EXPLAIN ANALYZE of a hash join under LIMIT: fewer probes).

### 6.3.Q8 R5 as built (2026-11-21)

R5 of 6.5: a write's rows found by a pipeline program. Branch
`worktree-agent-a545e704d39953a2b` from main d75a735c, with the paused
first attempt (0f68bb76, from main 757c4cee) merged in and brought up to
R2-R4. `SET lexdb_batch = off` (the row engine, the tests' reference) is
untouched, and no row-engine code was deleted: `runLevel` stays the
reference, and the writes it still finds (below) reach it.

**Commits and line counts:**

| commit | what | `lexdb_exec` | other |
|---|---|---:|---|
| main d75a735c | | 20,159 | `lexdb_pipe` 8,479, `lexdb_plan` 8,850 |
| 909f92dc | the paused WIP merged: `writeProg`, `writePrep`, `writePoint`; `compileRows` (a join to `compileLevels`, a point `PR_POINT`, else the first arm alone), `pointRows`; census `pipe-dml`; test `exec_writerows`; `exec_subrows`' counter | 20,215 | `lexdb_pipe` 8,556, `lexdb_plan` 8,856 |
| e08ae0cf | tests `tds_r5` (SQL Server 2022's answers), `tns_r5` (Oracle Free's; `gen_oracle.py --check` knows it) | 20,215 | |
| 3b52ca15 | a point by key as a light program (`pointProg`); the point join's path left as main's; `exec_writerows`' batched writes | 20,220 | `lexdb_pipe` 8,577 |
| 2aa30269 | main 028fd9e9 merged (the runtime's size classes, a new seed; lxlc rebuilt) | 20,220 | |
| 60a77ffa | the point's conditions bound once, by prepare (`Mats.cc`), not by the plan: the statements after point UPDATEs back to main's instructions (below); a DELETE's narrowed columns in `pointProg`; a point with subqueries the first arm's | 20,229 | `lexdb_pipe` 8,566 |
| 134ae1d7 | the point's row made only when found, the table's row itself when whole | 20,230 | `lexdb_pipe` 8,572 |

`lexdb_exec` +71 (20,159 at d75a735c and at 028fd9e9): `writePoint`
(its scan needs `pathScan`, `Env`, `seqEnv`, `Mats`), `writeProg`,
`writePrep`, the dispatch in `runQuery` and the four writes' calls; the
program and its run are the pipe's.

**What it does.**

- **Every UPDATE, DELETE, MERGE and ALTER TABLE ... USING** builds a
  program for its rows after its subqueries are offered (`writeProg`:
  `levelsProgQ`, now for one table too). A join tree is the levels program
  as before (`compileLevels`, R4's point first table included); one table
  is its first arm alone (`Filter? (Scan)`, `compileRows`, run by
  `runLevels`: its batches, or row by row for IN lists and a point with
  subqueries); a point of the whole primary key (`lexdb_plan.pointRead`)
  of a query without subqueries is a program of its own (`Prog.run`
  `PR_POINT`, `lexdb_pipe.pointProg`). DELETE's range path (`rangeDelete`) is
  tried first, as before (it finds no rows: one store write).
- **A point** is run by exec's `writePoint`: the key's scan (`pathScan`;
  a batched write's next batch from the key after the last one's,
  `afterScans`), then `lexdb_pipe.pointRows`: the row read as a join over
  a point reads its first table (`getRow`; the emitted row made only when
  one is found, the table's row itself when it is the query's whole row),
  its conditions in order by the scalar evaluator, the row to the write;
  counted as `runLevel` and `tryRow` count it (EXPLAIN ANALYZE as before).
- **A point's program is light and its conditions are bound once.**
  `levelsProgIn` makes it directly (`pointProg`): a Scan without the batch
  arm's kinds (a DELETE's narrowed columns kept), no Filter, no
  `joinsOver` or `compileRows`. Its conditions are bound by `prepare` as
  the row engine's are (`writePrep` binds for a point: `Mats.cc`,
  evaluated by `pointRows` in `Mats.ce`, as `allTrueC` evaluates them); a
  condition that does not bind gives the run to the row engine. Measured
  by variants (in process, UPDATE by key, at d75a735c): the first form
  (the WIP's `Filter (Scan)` through `levelsProgIn`) cost +556.6 a
  statement: binding the condition (`planX`) about 1,170, `scanArm` 796,
  `filterOver`/`subsOf` and the plan's drop 475, `joinsOver` and
  `compileRows` 366.
- **The statements after point UPDATEs.** 3b52ca15's form (the conditions
  bound by the plan, `planX`, held in the program; `prepare`'s binding
  skipped) left later statements of the process +22 instructions each:
  the coordinator's harness (`pt2.lxl`: 200 INSERTs and 200 UPDATEs by key,
  autocommit, then 20,000 point selects or INSERTs) read point selects
  132,084.7 -> 132,106.7 and INSERTs +21, deterministic, on d75a735c and
  on 028fd9e9; mine (no UPDATEs before the selects) read them equal. What
  was measured: without the UPDATE warm-up both 132,113.8 / 132,113.7;
  after 150, 200 or 250 UPDATEs +22.0 every time, after 400 (a checkpoint
  in both) equal; a new session after the UPDATEs +22 still; 30,000 small
  strings made and freed before the selects moved both by -1,755 and kept
  +22. Of the variants, only binding the conditions in `prepare` and
  holding them in `Mats.cc` to the statement's end (as the row engine
  does) gave main's count; binding them and dropping them at once, or
  freeing `Mats.cc` before the write, or holding a clone of the plan's
  bound conditions there, or binding by `bindExpr` into the program, did
  not; the select path's code is unchanged. So the cause is where the
  UPDATE's allocations land (a state the heap and the store's unflushed
  nodes keep until a checkpoint), not more work on the select path; the
  binding is now the row engine's, made where it made it, and the count
  is main's.
- **The rows are all held before any is changed**, as before: each found
  row is copied into `found` by the write's emit, then locked
  (`lockFound`), then written; so the Halloween problem cannot come from
  the program (`exec_writerows`' rows moved past the scan's end, key
  shifts, `x = x + 50 where x < 100`; `tds_r5`'s and `tns_r5`'s, checked
  against SQL Server and Oracle).
- **Binding.** A write with a program skips `prepare`'s binding of its
  levels' conditions for the row engine (`writePrep`); when the program
  gives way at the run (`batErr` before any row), `runQuery` prepares
  again with them bound, as before. MERGE still binds (`fewSource`).
- **Reuse.** `pointRows`' read is `pointJProj`'s (R4's point join) made
  a function of its own (`pointGet`); `pointJProj` and `stopRows` keep
  their inline copies: calling the shared function from them cost the
  3-table join +84 instructions and a stopping join (`limit 3` over a
  lookup) +941 (about 50 a row: the call's arguments). `writePoint`
  mirrors `pipeFetchJ`.
- **Census.** `censusDml` notes `pipe-dml` with the shape for a write
  with a program, else `dml` with the reason `levelsProgIn` gave (kept
  under "dml" by a hook in `writeProg`); a program that gives way at the
  run is noted again as `dml` ("gave way at the run").
- **Counters** for the tests: `lexdb_pipe.rowsRuns()` (`pointRows`' runs,
  `runLevels`' runs).

**Left, and why** (the census's 350 writes the row engine still finds,
the suite's old tests):

- A correlated subquery left per row or conditions on no table (220 runs:
  `update t set x = (select v from u where u.k = t.g) where id < 10`, a
  correlated EXISTS with unnesting off, a correlated RETURNING): the
  levels program has no Apply; R6's Apply over a write's program is the
  next step (its asks would run in `runLevelsProg`).
- MERGE with a source of fewer than 64 held rows (120 runs, 58
  statements: `fewSource`, the upsert's `using (values (...))`): kept on
  purpose. With `fewSource` off the suite gives the same rows, but a
  one-row VALUES upsert costs 309,031 -> 355,165 instructions (+14.9%)
  through the levels program (a hash built for one row); a 21-row source
  1,223,514 -> 1,177,261 (-3.8%). The threshold (`heldSmall`'s 64) is a
  cost question for R8's give-ways, not taken here.
- A program that gives way at the run (46 runs: a value a batch cannot
  hold, `update u set v = 'dup' where not b`): R8's.
- A join per row that is neither a lookup nor a range (9 runs, `from g
  where g.id between u.s and u.s + 2`), a condition that does not bind
  (1).

**Measured.** The census (6.4's tool; main d75a735c's run of 274 tests
against the branch's, its three new tests' lines left out; batches on):

| engine | main d75a735c | R5 |
|---|---:|---:|
| the pipeline's rows | 331,650 | 337,399 |
| the pipeline's groups | 824,421 | 824,431 |
| the row engine | 21,066 | 21,066 |
| a write's rows by a program (`pipe-dml`) | 0 | 2,674 (46 of them gave way) |
| a write's rows found by the row engine (`dml`) | 3,028 | 350 (+46 gave way) |
| a set operation | 2 | 2 |
| batches off | 775,247 | 775,251 |

The programs' 2,674 by shape: DELETE scan or range 777, UPDATE scan or
range 716, UPDATE by key (a point) 528, UPDATE by index 237, MERGE 108,
DELETE by key 105, DELETE by index 77, UPDATE ... FROM 73, ALTER TABLE
... USING 33, DELETE ... USING 20. The pipeline's rows grew by
`exec_limits`' and `exec_autostats`' clock-bound runs (+3,456, +2,293),
nothing else moved. OLTP (a census build serving pgbench `-M simple`: 300
UPDATEs by key, then 300 TPC-B-like transactions): all 1,200 UPDATEs are
the point program's, every point select the pipeline's; no write is
found by the row engine.

In process (`LXL_HASH_SEED=1`; main 028fd9e9 against 134ae1d7, both built
by 028fd9e9's compiler, alternated, alike to a tenth). Mine (`ip.lxl`: the
1-statement run subtracted from the N-statement one; INSERT, UPDATE and
DELETE in one transaction on the simulated disk) and the coordinator's
(`pt2.lxl`: autocommit, after 200 INSERTs and UPDATEs, a mode's run less
the setup's, over 20,000):

| statement | main 028fd9e9 | R5 | |
|---|---:|---:|---:|
| UPDATE ... WHERE id = k (mine) | 144,685.6 | 143,017.6 | -1,668 (-1.15%) |
| DELETE ... WHERE id = k, missing (mine, 2,000) | 92,917.4 | 92,610.5 | -307 |
| point select (mine) | 116,192.8 | 116,192.8 | 0 |
| INSERT VALUES, one row (mine) | 103,754.0 | 103,754.0 | 0 |
| the 3-table join (mine, 2,000) | 449,327.3 | 449,327.4 | 0 |
| a join under a stopping first table (`limit 3`, mine, 2,000) | 604,104.7 | 604,104.7 | 0 |
| point select after UPDATEs (coordinator's) | 132,084.7 | 132,084.7 | 0 (3b52ca15: +22.0) |
| INSERT after UPDATEs (coordinator's, autocommit) | 55,122,052.8 | 55,122,052.7 | 0 (3b52ca15: +21.0) |
| UPDATE by key (coordinator's, autocommit) | 55,144,553.9 | 55,143,232.6 | -1,321 |

At d75a735c, before the merge (3b52ca15, mine): UPDATE by key 148,237.1 ->
147,926.6, point select, INSERT, the 3-table join and a stopping join
(`limit 3`) equal.

Over the wire (base d75a735c against 3b52ca15, fresh copies of both
binaries, `-O`; `~/tpch-w/r5/logs`; the select path's code is the same in
134ae1d7):

- `pts.sh` (20,000 point selects by the simple protocol, wall / server CPU
  ms, means of 5, three rounds alternated): main 701.2 / 652.6, 692.0 /
  645.2, 704.6 / 656.6; R5 692.4 / 643.6, 696.4 / 647.4, 700.2 / 651.6
  (server CPU -1.4%, +0.3%, -0.8%).
- `icount6.sh` (points.sql three times, the server's counts a statement,
  two rounds alternated): instructions 186,831 / 187,048 against 187,095 /
  186,864 (within the tool's ~100's spread of the two), cycles 105,884 /
  107,100 against 104,441 / 104,415 (-1.4%, -2.5%), L1 i-cache misses
  390 / 387 against 428 / 425, iTLB misses 34 / 35 against 32 / 31, branch
  misses 434 / 435 against 424 / 422.
- `simplecpu.sh` (pgbench `-M simple`, 4 clients, 10 s; tps and server
  CPU a transaction, two rounds alternated): **update 9,233 / 9,229
  against 9,283 / 9,216 tps, 47.35 / 47.70 against 45.57 / 47.86 us a
  transaction (-3.8%, +0.3%)**; point select 47,554 / 47,192 against
  49,668 / 48,973 tps; the 3-table join 19,143 / 18,960 against 19,900 /
  19,643 tps, 49.56 / 50.01 against 47.60 / 48.24 us.
- `tpcb.sh` (new: pgbench's tpcb-like script, three UPDATEs by key, a
  point select and an INSERT in a transaction; scale 10, 4 clients, 10 s,
  `-M simple`; two rounds alternated): **3,742 / 3,770 against 3,958 /
  3,890 tps (+5.8%, +3.2%), 250.2 / 247.8 against 236.1 / 240.1 us of
  server CPU a transaction (-5.6%, -3.1%)**, no failed transactions.

TPC-H (SF1, base d75a735c and 3b52ca15, `-O`, alternated twice, one run
each, `TPCH_REF` 1744ef99, `~/tpch-w/r5`; best of the two, ms): checksums
equal on all 22 in all four runs; 11,472 against 11,421 ms (0.996). No
query over 1.5% slower (the most q12 +1.1%, q16 +1.1%), so no `iq.sh`
run; faster by over 1.5%: q13 -3.3%, q15 -2.7%, q17 -2.6%, q20 -3.7%. R5's
writes are not in TPC-H's 22 (no refresh functions).

**Tests.** Suite 277 of 277 at 3b52ca15, 60a77ffa and 134ae1d7 (274 at main; new:
`exec_writerows`, `tds_r5`, `tns_r5`). `exec_writerows` runs each write
with batches on and off in a transaction rolled back (the same tag, rows
or error, and the table after it the same): by key 19 (the point
program's but a key from a subquery: the first arm's), ranges and scans 17 (16 a program's; `delete from t2 where a
= 3` is the range delete), joins 5, MERGE 3 (a 5-row source the row
engine's, `fewSource`), ALTER ... USING 2, batched writes 7 (by key on two
copies of a table, a next batch after the key: the point program's; a key
range the range delete), a correlated EXISTS with unnesting off (the row
engine's) and two constant conditions (the program's). `tds_r5`: 43 T-SQL
batches (UPDATE and DELETE by key with OUTPUT, 8134, 2627 and 547; UPDATE
TOP and DELETE TOP of a scan, of a key, TOP (0); ranges, Halloween-shaped
updates, an error in a late row; UPDATE ... FROM and DELETE ... FROM; MERGE
with DELETE, NOT MATCHED, NOT MATCHED BY SOURCE and a source of 299 rows),
SQL Server 2022's answers (the `lxl-mssql` container, a database of its
own, dropped after), all the same with batches on and off. `tns_r5`: 31
statements (UPDATE and DELETE by key, ORA-01476, ORA-00001, ORA-02290,
ranges, IN subqueries, MERGE with DELETE WHERE), Oracle Database Free's
answers (`gen_oracle.py --check tns_r5`: 31 checked, no difference).
Expectations changed: `exec_subrows` (its writes' own runs: pipeline runs
888 -> 896).
### 6.3.Q8 R7 as built (windows) (2026-11-21)

R7's window part of 6.5. Branch `worktree-agent-ae4dbd05871d1984b` from
main 3aabcade, with the paused first attempt (56aa2201, from main
757c4cee: stage 1, the window driver moved into `lexdb_window`; stage 2,
the Window operator, written but never compiled) merged in and brought up
to R2-R6. `SET lexdb_batch = off` (the row engine, the tests' reference)
is untouched; no row-engine code was deleted (`winValues` is the row
engine's glue to `lexdb_window.allValues` now, `winBatch` stays). R7's
other parts, the views over the groups as operators and FOR UPDATE's lock
operator, are **not built** (left below).

**Commits and line counts:**

| commit | what | `lexdb_exec` | other |
|---|---|---:|---|
| main 3aabcade | | 20,230 | `lexdb_pipe` 8,572, `lexdb_plan` 8,838, `lexdb_window` 1,684 |
| e91fcacb | 56aa2201 merged (both sides kept: R2's Result, R3's ProjectSet and function in FROM, R6's Apply); built on today's main (`Prog.run`, R2's `PSort` fields, R6's `ask` through the Window); the outputs always through a `SortSt` (one OutBatch, as a Sort gives its rows); `max_statement_mem` checked as the row engine checks it before any row is given | 20,152 | `lexdb_pipe` 8,816, `lexdb_window` 1,825 |
| 7da894c7 | windows over an aggregate's groups the pipeline makes; a Window whose input keeps no column; test `exec_winpipe` | 20,152 | `lexdb_plan` 9,065 |
| 036e7cc2 | tests `tds_winpipe` (SQL Server 2022's answers), `tns_winpipe` (Oracle Free's; `gen_oracle.py --check` knows it); T-SQL's NTILE(0) error 4116 (was 50000) | 20,152 | `lexdb_tsql` +1 |
| 2b9585b3 | the Window under DISTINCT ON, TOP, TOP PERCENT and WITH TIES when sorted | 20,152 | `lexdb_plan` 9,073 |
| 9a7fed1a | the input's chunk values put at their slots (no `obRow` and copy); unsorted rows given one by one (runSel's sorted path takes rows too) | 20,154 | `lexdb_pipe` 8,842 |
| 7fec138f | outputs that are a column or a call's value read at their place | 20,154 | `lexdb_pipe` 8,862 |

`lexdb_exec` -76: the window driver (`winValues`' 100 lines of partition
and order keys, the shared sort, `frameOff`) is `lexdb_window.allValues`
and `frameOff`; exec keeps the hook (`ev(H_KEY | H_ARG | H_OFF, call, i,
row)`: a key or argument by `evalX`, an aggregate's argument and FILTER
plainly, a frame's offset once) and `pipeWinSel` (14 lines, reached only
where `pipeShape` said no: no cost on the point-select planning path);
+2 in `runSel`'s sorted path (a row given alone, not in an OutBatch).

**What it does.**

- **A query of window calls over rows** (`lexdb_plan.winShape`: not
  grouped, one table or joins, no correlated subquery left, no set
  operation, function in FROM, lock, MATCH_RECOGNIZE, `SELECT @v =` or
  set-returning function in the list; DISTINCT ON, TOP and WITH TIES when
  sorted and not DISTINCT, as `sortShape`) is planned by `pipeWin`:
  `Limit? (Sort? (Distinct? (Project (Window (Project (the input))))))`,
  the input the conditions, scan and joins as `pipeShape`'s plan has them;
  `PPlan.Window(PPlan, Option[PWin])` (None: a view, `physAbove`'s), its
  `PWin` the calls, per call its keys, arguments (`argsOf`) and frame
  offsets bound by `lexdb_bind.bindSubsAggs` (subqueries run once, `#agg
  i` the calls' values), and the query's columns a row keeps (`slots`:
  those read above it, and a single table's decoded ones, so a row holds
  what the row engine's row holds; none: a Project of one NULL). EXPLAIN
  prints `physOf`'s plan as before.
- **The operator** (`lexdb_pipe.compileWin`, `runWin`, `winBody`; `run`'s
  and `runJ`'s `sorts` branch): the input run whole (`runOp`, or
  `runJProj` with R6's `ask`), its rows held as `WinRow`s of the query's
  width, counted against `max_statement_mem` row by row as the row engine
  counts them (`winTake`: `rowBytes`, the room at the run's start); every
  call's values by `lexdb_window.allValues(true, ...)` (the batches' path
  the row engine takes: partitions and peer groups sorted by
  `lexdb_window.sortRows`, windows of one specification sharing the sort,
  frames over the held rows), hooks by `bxEval`; then every row's outputs
  in the input's order (a column or a call's value read at its place, the
  rest by `bxEval`) to a `SortSt` (P3's: sorted, DISTINCT, DISTINCT ON,
  TOP, TOP PERCENT, WITH TIES), its own room and early stop off, which
  gives one OutBatch; with none of those, the rows LIMIT and OFFSET keep,
  given one by one as the row engine gives them (a `SortSt`'s OutBatch
  cost the 1M-row rank +8.7% server samples against main; now -17.8%).
  Every row's outputs are made, past a LIMIT too, so the first error is
  the row engine's. The bytes held are the row engine's (its rows, then
  every output row with its ORDER BY values: `winBytes`), checked before
  any row is given (a `SortSt`'s own count set aside).
- **Windows over an aggregate's groups**: `aggShape` no longer refuses
  them; the pipeline makes the groups (`pipeGroups`) and exec's view over
  them computes the windows, as HAVING (`afterCols` keeps the columns the
  calls' PARTITION BY, ORDER BY, arguments and FILTER name; `underViews`
  and `unplan` go through `Window(_, None)`). ROLLUP, CUBE and grouping
  sets with windows stay 0A000 both ways.
- **Give-ups.** A `SortSt` that cannot hold a value (`bad`: a sort key of
  mixed kinds, while eating or at `finish`) returns `batErr` before any
  row is given and before anything is held; the row engine runs the query
  again (as P3's Sort; the outputs it made are made again: no volatile
  call binds, `bindSubsAggs` refuses them). A key, argument, offset,
  output or ORDER BY key that does not bind gives the Sel back
  (`unplanWin`: its conditions; the outputs were never `ox`).
- **The open questions of the paused note.** `max_statement_mem` at a
  partition's edge for joins: the same; `exec_winpipe` finds each query's
  edge (the least kB the row engine runs it in, by halving) over six input
  sizes and runs it there and a kB under, a join with wide columns it does
  not read included: 48 the same. A `SortSt` that gives up after the
  outputs were made: the row engine again, nothing given (tested with a
  column of mixed kinds, an error in a later row too).
- **Counters** for the tests: `lexdb_pipe.winRuns()`.

**Tests.** `exec_winpipe` (new; each statement batches off, on, and
through a sink): 500 generated window queries (every function, ROWS,
RANGE with offsets, GROUPS, EXCLUDE, FILTER, several partitionings,
NULLs, duplicates and text keys, a collation's, DISTINCT, ORDER BY,
LIMIT/OFFSET, joins, left joins, held rows, an empty table: all on the
Window), 39 fixed (errors in a later row before and past a LIMIT and in a
row DISTINCT ON drops, frame offsets NULL and negative, ntile and
nth_value of 0, DISTINCT ON, WITH TIES, mixed kinds, a correlated
subquery: the row engine), 48 at the memory edges, 13 grouped.
`tds_winpipe` (30 T-SQL batches, SQL Server 2022's answers, the same both
ways; TOP, TOP PERCENT, TOP WITH TIES and OFFSET ... FETCH among them) and
`tns_winpipe` (30 statements, `gen_oracle.py --check`: 0 differences;
NTH_VALUE, GROUPS, EXCLUDE, FETCH ... WITH TIES among them). Expectations
moved: `exec_batchexpr`'s and `exec_batchsort`'s OutBatch counts (327 ->
360 of 600, 200 -> 215 of 400: the sorted windows), `exec_held`'s held window, `exec_narrow`'s
grouped window over batches. Suite: 280 tests pass. Found, not fixed (not
windows): over the Oracle door `sum(10 / (id - 3001))` of 3,000 rows is
ORA-01426 (numeric overflow) in lexdb, both engines; Oracle sums it.

**Census** (the suite at main 3aabcade, 277 tests, against the branch,
its three new tests' lines left out): the row engine's runs with batches
on 21,066 -> 14,476; the pipeline's rows 337,788 -> 344,685. Gone: "a
window (winValues)" 6,597 runs (5,952 statements, 21 tests) and "agg: a
window over the groups" 11. Left, named: a window over a LATERAL level
after the first (12 runs, one statement each: R4's dependent join), a
frame offset that is a subquery (1: does not bind).

**Gates.**

All at 7fec138f against main 3aabcade.

- Point select, INSERT and UPDATE by key, in process (the coordinator's
  `pt2.lxl`, `LXL_HASH_SEED=1`, two rounds alternated, main's binary its
  `r5f`; per statement = (mode - setup) / 20,000): point select 132,084.7
  -> 132,084.7, INSERT 55,122,052.74 -> 55,122,052.75, UPDATE
  55,143,232.59 -> 55,143,232.59: equal (the rounds' spread is about 200
  instructions of a run, 0.01 a statement).
- Over the wire: `pts.sh` (3 rounds, 15 runs each) server CPU 642.9 ->
  633.7 ms, wall 692.0 -> 679.2 ms; `icount6.sh` on fresh copies, per
  statement instructions 182,191 / 182,100 -> 182,037 / 182,062, cycles
  103,748 / 104,295 -> 103,519 / 102,299, branch misses 419.6 / 422.7 ->
  438.5 / 428.9 (L1i and iTLB misses a little up, 357 / 338 -> 377 / 394
  and 32 / 31 -> 37 / 38, by placement; the cycles did not follow).
- TPC-H SF1 (no windows; `~/tpch-w/r7`, base and branch alternated twice,
  best of two): 22 checksums equal, total 11,426 -> 11,397 ms (0.997).
  Over 1.5%: q22 163.6 -> 166.6 ms (1.018), its server instructions
  1,708,293,388 / 1,708,712,814 -> 1,708,287,904 / 1,708,266,369: equal,
  placement (q14 1.014 the same, 1,321.4M both). An earlier round (at
  2b9585b3) read q15 1.032 at equal instructions (3,980.7M-3,980.9M both).
- Window benchmark (`~/tpch-w/r7/wbench.sh`; `wb(id int primary key, g
  int, v int)`, 1M rows, g = id % 1000; the server on CPUs 0-3, psql on
  4-7,12-15; best of six runs for lexdb (three in each of two alternated
  rounds), of three for PostgreSQL 18.6, `work_mem` 256MB, at most leader
  + 3 workers; ms):

  | query | main | branch | branch / main | PostgreSQL 18 |
  |---|---:|---:|---:|---:|
  | row_number per partition (`partition by g order by id`), summed | 317 | 268 | 0.845 | 317 |
  | running sum (`sum(v) over (order by id)`), its max | 371 | 286 | 0.771 | 267 |
  | moving average (`avg(v)`, 10 rows), its max | 518 | 443 | 0.855 | 369 |
  | rank (`rank() over (order by v)`), its max | 329 | 299 | 0.909 | 267 |
  | row_number per partition, 1M rows to the client | 425 | 438 | 1.031 | 430 |
  | running sum, rows to the client | 455 | 399 | 0.877 | 393 |
  | moving average, rows to the client | 595 | 514 | 0.864 | 514 |
  | rank, rows to the client | 424 | 367 | 0.866 | 445 |

  The first four wrap the window in a derived table under an aggregate
  (one row out). The partitioned row_number to the client is +3% (server
  samples +5%: `winTake`'s rows and the per-row `give` against
  `winBatch`'s rows and the held result's; `lexdb_window.keyOf` reads
  the same rows slower here, by their place in memory).

**Left, and why.**

- R7's other parts: the views over the pipeline's groups (HAVING, the
  select list, DISTINCT, ORDER BY, LIMIT; and now the windows over the
  groups) as operators, and FOR UPDATE's lock operator (200 runs): not
  this agent's scope.
- A window with a correlated subquery left per row (q.corr; the suite's
  only one is a LATERAL level after the first, 12 runs): R6's Apply under
  the Window is the way (`runJProj` already carries `ask`); `winShape`
  refuses it.
- DISTINCT with WITH TIES or TOP over windows (as `sortShape`), windows
  with grouping sets (0A000 anyway), a frame offset that does not bind.
- The operator is row by row past the scan (a `WinRow` per input row,
  `bxEval` per evaluated output); the input's chunks kept as columns and
  chunked outputs (which the partitioned row_number to the client needs
  to beat main) are R9's or later.

### 6.4 Q8: what the row engine still runs (the census, 2026-11-21)

Measured at main 4fa2acec (Q4-Q7 merged) with the census of Q8's first
part: every run of a query (a SELECT's, a subquery's, a set operation's
part, a write's rows found) noted with the engine that made its rows and,
for the row engine's, the first reason the pipeline declined it.

**The instrument.** `lexdb_census` (new, imports only lexell's
libraries) and `lexell/tools/lexdb_census.py`:

- A build-time switch: `lexdb_census.ON` is false in every build. A
  census is a copy of the tree (`lexdb_census.py copy DIR`) with ON true,
  the `// census: <call>` hook comments made code, and the suite's runner
  naming each test (`LEXDB_CENSUS_TEST`); its programs append a line per
  run to `$LEXDB_CENSUS`: test, top or sub (inside a subquery's run),
  engine, reason, statement. `lexdb_census.py sum` adds them up.
- Where the reasons come from: the planner's and the pipeline's give-ups
  each name themselves (`lexdb_census.no`, first one wins): `pipeSelMain`'s
  branches, `pipeShape`'s and `aggShape`'s conditions (`shapeWhy`,
  `aggWhy`: the same tests again, in order), `pipeAgg`, `joinsOver`'s
  levels, `lexdb_pipe.compile` (`opsWhy`, again `opsOf`'s tests),
  `aggOps`, `joinOps`, `grpOps`, `levelsProgIn`. A declined Sel's reason
  is kept under a key of its tables, outputs and kind; the run looks it
  up. A run's own give-way (`batErr`) is noted where it is caught.
- What it costs: nothing. A `const` test is not compiled away (`if
  lexdb_census.ON { ... }` costs about five instructions where it runs,
  measured on a loop), and a call in a declined branch is paid where a
  statement declines every time (the OLTP 3-table join: +24 instructions
  a statement), so a normal build holds no census call at all: every
  hook is a comment (101 of them), the reasons' functions
  (`shapeWhy`, `opsWhy`, ...) are called from hooks only, and `opsOf` is
  untouched (an instruction there had cost a point select: its frame
  grew). A global array costs about 500 instructions at a program's
  start: the coverage's is a hook too. Point selects, `LXL_HASH_SEED=1`,
  in process, the 1-select run subtracted from the 20,000-select one, two
  rounds: 132,512.4 instructions a select (main) against 132,512.3 (the
  census in, off); the 3-table join 426,944.4 against 426,944.4.
- `copy --cover=MOD,...` notes each function's first entry, `copy
  --blocks=MOD,...` each block's (an if's, a loop's, a match arm's, a
  closure's); `copy --force-batch` with `LEXDB_CENSUS_FORCE=1` ignores
  `SET lexdb_batch = off`, so the code only the tests' reference reaches
  shows (6.3.Q8 as built, 6.5).

**Runs by engine** (the suite, 253 tests; TPC-H's 22 queries at SF1, one
run; OLTP: 2,000 of `points.sql` through psql, 300 each of pgbench's
point select, update, 3-table join, insert and a TPC-B-like transaction,
`-M simple`):

| engine | suite runs | suite tests | TPC-H runs | OLTP runs |
|---|---:|---:|---:|---:|
| the pipeline's rows | 37,413 | 184 | 6 | 2,600 (every point select) |
| the pipeline's groups (exec makes HAVING, the select list, DISTINCT, ORDER BY over them) | 790,244 (9,000 statements) | 188 | 9,484 | 0 |
| the row engine | 311,366 | 196 | 6 | 303 |
| a write's rows found (`runQuery`) | 3,003 | 109 | 0 | 600 (every UPDATE) |
| a set operation (`runSet`, its parts on their own) | 553 | 33 | 0 | 0 |
| `SET lexdb_batch = off` (the tests' reference) | 737,768 | 58 | 0 | 0 |

207 of the 216 tests that run a query make at least one row-engine, write
or set-operation run; 9 run nothing but the pipeline. Only 58 tests run
anything with batches off.

- **TPC-H:** all 22 run their main work in the pipeline. The row engine
  makes q2's outer query (a correlated scalar subquery left per row:
  `q.corr`; its 747 runs are the pipeline's aggregates), q17's outer
  aggregate (`q.corr`; 204 runs), q16's NOT IN subquery's own rows (the
  supplier scan) and q20's two IN subqueries' own rows (its 8,508 runs of
  the correlated sum are the pipeline's).
- **OLTP:** every point select is the pipeline's (Scan of one point ->
  Project: a chunk of one already, P1a). Every UPDATE finds its row in the
  row engine (`runQuery` -> `runLevel`'s point read). The 3-table join
  (`b.aid = a.aid + 1 ... ORDER BY 1 LIMIT 5`) is the row engine's: its
  lookups are per row under a first table that may stop early. INSERT
  VALUES runs no query.
- **Point select, pipeline against row engine** (in process, 20,000,
  `LXL_HASH_SEED=1`, the same binary, `SET lexdb_batch = off` for the row
  engine; the 1-select run subtracted): 132,512 instructions a select
  against 135,953, the pipeline 2.5% fewer.

**The row engine's runs by reason** (the suite, batches on: statements
are distinct texts, tests those with one; the reasons in the order the
planner tests them, the first one that held; a run of the census copy, all
253 passing, and a second for the subqueries' split, where `exec_batchexpr`
times out under the census's writes, a line a run):

| reason | statements | tests | runs | example | to cover | size |
|---|---:|---:|---:|---|---|---|
| a subquery's own rows (IN, EXISTS, a scalar's, a semi, anti or mark level's: `pipeSelIn(sel, false)`), INSERT ... SELECT's rows: 1,980 statements (129 tests) for that alone, 1,633 (32 tests, 138,873 runs) correlated per row as well | 3,360 | 135 | 151,021 | q16's `ps_suppkey not in (select s_suppkey from supplier where ...)`; per row: `exists (select 1 from f where f.xf = tn.k)` | offer their rows (`rows` true): `runChild`'s `execSel` already takes `pipeHeld`; the per-row ones need Apply as well (below). **Done, R1 (6.3.Q8 R1): the reason is gone; the per-row ones' own rows are offered too (the pipeline cheaper a run); 13,208 of their runs are the row engine's under their next reason** | small (a switch, measured per run: q20's 8,508) |
| a window (`winValues`) | 5,931 | 19 | 6,572 | `select id, sum(v) over (partition by g order by id) from t` | a Window operator: partitions sorted (P3's Sort), frames over chunks, `lexdb_window`'s evaluators. **Done, R7 (6.3.Q8 R7): the Window operator; left 13 runs (a LATERAL level after the first, a frame offset that is a subquery)** | large (exec's window code: `winValues`, `winBatch`, `winPlan`, 260 lines) |
| no FROM (`runQuery` with no level) | 814 | 116 | 42,808 | `select nextval('s')`, `select 1` | a Result arm: one row, its outputs by `bxEval` | small; a driver's `select 1` is point-select-like: OLTP gate |
| a correlated subquery left per row: in an aggregate's query (392), in a plain query (303), in the outputs or ORDER BY (238), a correlated subquery's own run (59; offered by R1, gone) | 903 | 47 | 44,277 | q2, q17; `select (select count(*) from big(t.v)) from t` | Apply (6.2.3's "Apply for RUN_PER_ROW"): the per-row call of the subquery's program from an arm, its memo. **R6 (6.3.Q8 R6): those in one level's WHERE conjuncts are the pipeline's (the Apply; q2, q17, q20's partsupp query); left: LATERAL (R3), a 9.9 hashed probe, a path's key, two levels** | large |
| a function in FROM as the query (`execSrf`: generate_series, unnest, the catalog's relations) | 429 | 77 | 2,268 | `select count(*) from pg_class where relkind = 'r'` | a function-scan source (`lexdb_held` reads its rows already) **Done, R3 (6.3.Q8 R3): a program of its own, its arguments bound, its rows by `lexdb_srf`; left: 13 runs whose argument does not bind (psql's `::regclass`)** | medium (`execSrf` 172 lines) |
| not offered to the pipeline (a write's subqueries: RETURNING, SET, WHERE) | 274 | 21 | 800 | `delete from fp returning id, (select count(*) from fc)` | `pipeSel` for a write's subqueries. **Done, R1: 6 runs left (six `exec_unnest` IN subqueries, not traced)** | small |
| MIN or MAX by the scan's order (`Sel.first`) | 245 | 17 | 10,661 | `select max(c) from f` (an index on c) | a first-row aggregate over an ordered scan that stops | small |
| joins the pipeline does not join: per row under a first table that stops early (161), a point first table (44), RIGHT/FULL with no key (14), a collation's key (5), an `= any(array)` lookup (4), an expression (2) | 230 | 28 | 374 | OLTP's 3-table join; `select * from v11 where id = 3` (a view of a join) | lookups under a stopping first table, a chunk of one as a join's input, collated keys | medium |
| MATCH_RECOGNIZE (`execMatch` over its input's rows) | 196 | 6 | 473 | `select * from mv order by g` | stays a row operator over the input (`lexdb_match`), fed by the pipeline; out of exec. **Done, R3: its input the pipeline's; `execMatch` stays in exec** | medium |
| OFFSET (not a stopping LIMIT) | 131 | 11 | 135 | `order by id desc limit 2 offset 1` | Limit with an offset | small |
| FOR UPDATE (`runLocking`) | 98 | 7 | 199 | `select id from acct where id = 2 for update` | a lock operator (runs again after a wait) | medium |
| an expression that does not bind for the plan: an output (81), a condition (47), ORDER BY (2) | 130 | 44 | 694 | `select row_number() from emp`, `where count(*) > 1` (errors the row path raises), a session function | the binder raises the errors; the rest case by case | small each |
| gave way at the run (a value a batch cannot hold: `batErr`), rows (84) and groups (37) | 119 | 38 | 182 | `select distinct sqrt(abs(e.n)) from e` | each operator's own fallback (6.2.3's table: a `BK_VAL` column), no whole-query give-way | medium |
| a recursive CTE's working table as the first level | 44 | 5 | 50,312 | `with recursive t(n) as (select 1 union all select n + 1 from t where n < 10) ...` | the working table as rows the run holds (`heldRead`) | small |
| aggregates it does not run: a window over the groups (11; **R7: the pipeline's groups, exec's view computes the windows**), a collation's key or call (13), calls, keys or conditions that do not bind (11) | 35 | 23 | 51 | `select count(distinct c) from w` (c a collated text) | collated keys and calls in `HashAgg` | small-medium |
| DISTINCT ON (25), WITH TIES and TOP PERCENT (12), a set-returning function in the select list (8), `SELECT @v =` (1) | 46 | 10 | 66 | `values (1), (1), (2) order by 1 fetch first 1 row with ties` | Sort and Distinct variants | small each |

**After R1** (6.3.Q8 R1, the same 254 tests): the row engine's runs with
batches on 310,731 -> 162,204, the pipeline's rows 38,940 -> 188,801.
Gone: R1's two rows and "a correlated subquery's own run" (22,198 runs).
Grown, by R1's statements now showing their next reason: a correlated
subquery left per row 390 -> 13,244 runs (R6), one in the outputs or
ORDER BY 288 -> 6,312, a join's first table not read in batches 70 ->
6,085 (`exec_unnest`'s nested correlated NOT IN), a recursive CTE's
working table 49,672 -> 50,056, MIN/MAX by the scan's order 10,661 ->
10,689, no FROM 42,808 -> 42,881, smaller ones by tens. TPC-H's
row-engine runs 6 -> 4 (q16's and one of q20's subqueries).

**After R2** (6.3.Q8 R2; main 757c4cee's run, 257 tests, against the
branch's, the same tests, its three new ones left out): the row engine's
runs with batches on 159,490 -> 58,603, the pipeline's rows 195,747 ->
280,987, its groups 791,046 -> 801,752. Gone: a recursive CTE's working
table (47,240), no FROM (42,883), MIN/MAX by the scan's order (10,689;
2 over joins left), OFFSET (135; 3 over joins left), DISTINCT ON (36),
WITH TIES (12), TOP PERCENT (2), a collation's GROUP BY key (10; 3 in
grouping sets left), a call by a collation (7). Grown by their next
reason: "gave way at the run" 174 -> 289 (a recursive CTE's working
table of a few rows joined: the row engine's, as a few held rows of a
subquery joined are), two each of a join under a stopping first table
and a set-returning function in the select list. The rest is R3-R9's:
correlated per row (R6) 34,674, windows 6,572, a correlated subquery in
the outputs 6,331, a join's first table not read in batches 6,085, a
function in FROM 2,269, outputs and conditions that do not bind 721,
MATCH_RECOGNIZE 473 (6.3.Q8 R2's "Left").

**After R6** (6.3.Q8 R6; main 757c4cee against the branch, the 257 tests
of main): the row engine's runs with batches on 159,618 -> 151,912, the
pipeline's rows 189,344 -> 201,032, its groups 791,049 -> 792,082. "A
correlated subquery left per row" (34,674 runs with its "agg:" variant)
is the pipeline's where its subqueries are all in one level's WHERE
conjuncts (the Apply); what stays names its reason: LATERAL 20,189 (a
function in FROM over outer values: R3), a 9.9 hashed probe 6,157, a
path's key 157, others 79. "One in the outputs or ORDER BY" (6,331) is
unchanged. TPC-H's row-engine runs 4 -> 1 (a `select 1`).

**After R3** (6.3.Q8 R3; main 5f30415d's run, 268 tests, against the
branch's 271, its three new tests' lines left out): the row engine's runs
with batches on 50,926 -> 27,461, the set operations' (`runSet`'s tail)
581 -> 2, the pipeline's rows 326,244 -> 326,531, its groups 803,885 ->
824,090. Gone: a function in FROM (2,283; 13 left whose argument does not
bind), MATCH_RECOGNIZE (473, and its second note, the match's own, 473),
a set operation held (579; TOP or WITH TIES 2 left), a set-returning
function in the select list (21; 1 over a table left), LATERAL (20,422
with its "agg:" variant: 20,230 at the first level over outer values,
20,000 of them `exec_limits`' one statement, now the pipeline's groups;
left, named: a LATERAL level after the first 180, one at the first level
beside another subquery run per row 12). Nothing else moved but the runs
of statements bounded by a limit or a clock (`exec_limits`' recursive CTE
without an end, 34,816 -> 33,152 runs; `exec_autostats`' point selects
while its analysis runs; `exec_turns`' UPDATEs, by the clock), which is
why the pipeline's rows grew by less than R3's runs. The rest is R4-R9's:
windows 6,597, a correlated subquery in the outputs 6,382, a join's first
table not read in batches 6,085, a 9.9 hashed probe 6,158, outputs and
conditions that do not bind 721, joins under a stopping first table 329.

**After R4** (6.3.Q8 R4; main 52fe2606's run, 271 tests, against the
branch's, its three new tests' lines left out): the row engine's runs with
batches on 27,495 -> 21,055, the pipeline's rows 306,529 -> 338,144. Gone:
a join's first table not read in batches (6,085), joins under a stopping
first table (329), RIGHT/FULL/LEFT with no key (25), a collation's hash key
(9; 4 left over a subquery's rows or a semi join, "not a table's join").
OLTP: the 3-table join is the pipeline's (`runPointJ`). Left of the joins:
a LATERAL level after the first 180 (a plan in 6.3.Q8 R4), an `= any(array)`
lookup 7, OFFSET over joins 6. The rest is R5-R9's: windows 6,597, a
correlated subquery in the outputs 6,402, a 9.9 hashed probe 6,158,
outputs and conditions that do not bind 723, gave way 363 + 52, FOR
UPDATE 200.

**After R5** (6.3.Q8 R5; main d75a735c's run, 274 tests, against the
branch's, its three new tests' lines left out): a write's rows found by
the row engine 3,028 -> 350 runs; by a pipeline program (`pipe-dml`)
2,674 (46 of which gave way at the run). OLTP: every UPDATE (pgbench's
and TPC-B's) is the point program's (`pointProg`, `pointRows`). Left of
the writes: a correlated subquery left per row or conditions on no table
220 (an Apply over a write's program), MERGE with a source of under 64
held rows 120 (`fewSource`, kept: the pipeline costs a one-row upsert
+14.9%), gave way 46 (R8), a join per row neither a lookup nor a range 9,
a condition that does not bind 1. The rest of the row engine's runs are
as after R4 (21,066).

**After R7** (6.3.Q8 R7, windows; main 3aabcade's run, 277 tests,
against the branch's, its three new tests' lines left out): the row
engine's runs with batches on 21,066 -> 14,476, the pipeline's rows
337,788 -> 344,685. Gone: "a window (winValues)" 6,597 runs (5,952
statements, 21 tests), "agg: a window over the groups" 11. Left of the
windows: one over a LATERAL level after the first 12 (R4's dependent
join), a frame offset that is a subquery 1. The rest is R7's other parts
and R8-R9's: a correlated subquery in the outputs or ORDER BY 6,411, a
9.9 hashed probe 6,158, outputs and conditions that do not bind 723, gave
way 368 + 52, FOR UPDATE 200.

**The writes** (the rows a write changes, found by `runQuery` over its
query: `runLevel`, with batches its first level by `batchLevel`, its
joins by the levels program `Query.jp`): UPDATE 1,391 statements, DELETE
301, MERGE 112, ALTER TABLE's rewrite 29, in 109 tests; OLTP's every
UPDATE. To cover: a write's source as a pipeline program giving its rows
to the write operator (layer 7); medium; gated by pgbench's update tps
and instructions. **Done, R5 (6.3.Q8 R5): every write builds a program
(`writeProg`), a point by key its own light one; left: 350 runs (above).**

**Set operations:** 349 statements in 33 tests combine their parts in
exec (`runSet`); `lexdb_setop` streams the others already. Medium.
**R3 (6.3.Q8 R3): a held one's ORDER BY, OFFSET and LIMIT are
`lexdb_setop`'s (`held`); `runSet` still runs its parts and combines
them; left: TOP and WITH TIES (2 runs).**

**Over the pipeline's groups:** HAVING, the select list, DISTINCT, ORDER
BY and LIMIT of every aggregate the pipeline runs (9,000 statements, 188
tests, TPC-H's 18 grouped queries) are made by exec's row code
(`execSelIn`'s group loop, `sortOutRows`). They are views over few rows
(physAbove's), but they are the row engine's code: medium (Having,
Project and the Sort over the groups as operators).

### 6.5 Q8: the row engine's deletion, in slices (plan, 2026-11-21)

What is left before the row engine (`runQuery`, `runLevel`, `materialize`,
`batchLevel`, the row aggregates, sort, windows, `execSrf`, `execMatch`'s
feeding, the subquery runs per row) can be deleted (decision 1), from
6.4's census and 6.3.Q8's coverage.

**What the coverage says first** (6.3.Q8 as built, stage 3). With `SET
lexdb_batch = off` ignored (`lexdb_census.py copy --force-batch`), the
suite enters the same 1,130 functions of exec, the pipe and the plan as
with it honoured: no function is there for the tests' reference alone;
every row-engine function is still reached by some statement the
pipeline declines with batches on. Only ten blocks are the reference's
alone (`runLevel`'s read of the keys optimizer 19's switch counted,
`winValues`' row path). So the row engine goes when the last declined
shape is covered, not before, and slice by slice the census counts what
is left.

**The slices.** Each merges with 6.3's gates (the suite; TPC-H alternated
twice against the previous main, checksums equal, no query slower; point
selects by instructions with `LXL_HASH_SEED=1`, any increase fixed;
`lexdb_exec`'s lines) plus the census run again: the row engine's runs
with batches on fall by the slice's rows of 6.4 and by nothing else.

| slice | what the pipeline takes | 6.4 rows | own gate | size |
|---|---|---|---|---|
| R1 (built: 6.3.Q8 R1) | every SELECT's rows offered: a subquery's own rows (`pipeSelIn(sel, true)`), a write's subqueries, INSERT ... SELECT's rows | subquery own rows, not offered | q16, q20 (the subqueries' rows; 8,508 per-row runs must not cost more: the per-run setup is 51.7's 4.6 us); `exec_unnest*` | small |
| R2 (built: 6.3.Q8 R2; left: a set-returning function in the select list, a collation's hash join key, the binder's errors and the outputs that do not bind) | the small arms: a Result arm (no FROM), Limit with an offset, the recursive CTE's working table as held rows, a first-row aggregate (`Sel.first`), DISTINCT ON, WITH TIES, TOP PERCENT, a set-returning function in the select list, collated keys in HashAgg and the hash join, the binder raising the errors the row path raises | no FROM, OFFSET, recursive CTE, MIN/MAX, variants, aggregates not run, does not bind | `select 1` and `select nextval()` by instructions (a driver's ping is point-select-like) | small each, ~600 lines in all |
| R3 (built: 6.3.Q8 R3) | a function in FROM as a source (`execSrf`'s rows as `lexdb_held` reads them), MATCH_RECOGNIZE fed by the pipeline (`lexdb_match` stays a row operator over its input), set operations all through `lexdb_setop`. **Built: a function's program (`lexdb_srf` makes its rows), LATERAL at the first level over outer values run once a run, a set-returning function in a select list with no FROM (ProjectSet), a held set operation's ORDER BY, OFFSET and LIMIT, MATCH_RECOGNIZE's input; left: LATERAL after the first level (a dependent join: R4), a set-returning function over a table or under LIMIT/DISTINCT, TOP and WITH TIES over a set** | function in FROM, MATCH_RECOGNIZE, set operations | the catalog queries' (`pg_class`, `pg_attribute`) instructions | medium |
| R4 (built: 6.3.Q8 R4) | the joins left: lookups per row under a first table that stops early, a point first table as a join's input (a chunk of one), RIGHT/FULL with no key, an `= any(array)` lookup. **Built: a join over a point (`runPointJ`, the OLTP join), a point first table in any join, lookups and ranges under a stopping first table (slices that double, `joinGrow`), LEFT/RIGHT/FULL with no key, a collation's hash key; left: LATERAL after the first level (a dependent join: a plan in 6.3.Q8 R4), an `= any(array)` lookup (7 runs)** | joins | `simple.sh`'s 3-table join tps (today the row engine's) | medium |
| R5 (built: 6.3.Q8 R5) | a write's rows found by a pipeline program (UPDATE, DELETE, MERGE, ALTER TABLE's rewrite): the program's rows to the write operator (layer 7), `batchLevel`'s work then the program's. **Built: every write's program (`writeProg`: a table's first arm, its joins, a point by key as `pointProg` run by `pointRows`, its conditions bound by prepare); UPDATE by key 1,668 instructions fewer (-1.15%), TPC-B +3% to +6% tps; left: a correlated subquery per row (an Apply over a write's program), MERGE's few-row sources (`fewSource`, kept for cost), the give-ways (R8)** | writes | pgbench update and TPC-B tps; instructions per UPDATE by key A/B (today `runLevel`'s point read) | medium |
| R6 (built: 6.3.Q8 R6) | Apply for RUN_PER_ROW: a correlated subquery left per row called from an arm (its program's run per outer row, its memo of results by outer values, MEMO_MAX); the outer query is then the pipeline's. **Built for one level's WHERE conjuncts (the joins ask the consumer, exec evaluates them as the row engine does); left: the outputs and ORDER BY (evaluated after the scan), conjuncts of two levels, a 9.9 hashed probe, a path's key; a chunk's runs batched (q20's rows by key)** | correlated per row | TPC-H q2, q17 (outer queries the row engine's today), q20; `exec_sub`, `exec_unnest*` per-row shapes | large |
| R7 (windows built: 6.3.Q8 R7) | windows as an operator (partitions by P3's Sort, frames over chunks, `lexdb_window`'s evaluators); the views over the pipeline's groups (HAVING, the select list, DISTINCT, ORDER BY, LIMIT) as operators; FOR UPDATE's lock operator (a run again after a wait). **Built: the Window operator over a query's rows (one table or joins; sorted, DISTINCT, DISTINCT ON, TOP, WITH TIES, LIMIT/OFFSET over it), windows over the pipeline's groups (exec's view); left: the views over the groups as operators, FOR UPDATE's lock operator, a window with a correlated subquery left per row (R6's Apply under the Window)** | window, over the groups, FOR UPDATE | TPC-H's 18 grouped queries (their views move); `exec_win*` | large |
| R8 | the give-ways: every operator's own fallback (6.2.3's table: a `BK_VAL` chunk column, a numeric past its units), no `batErr` to the row engine | gave way | the suite's "batched" counts; no query slower | medium |
| R9 | the deletion: `runQuery` and below (`runRows`, `runLevel`, `materialize`, `batchLevel`, `bLevelPlan`, `winBatch`, `fillPick`), `execSelIn`'s row branches, `addToGroup`, `sortOutRows`, `eachRowBIn`'s row path, `runSub`/`fillCur`'s per-row machinery, the levels program for the row engine (`Query.jp`, `levelsProg`), `Run`'s row-engine fields; `SET lexdb_batch` | (the census: no row-engine run with batches on, suite, TPC-H, OLTP) | the oracle in place first (below); the suite; TPC-H; OLTP | about 3,000 lines out of exec (the row engine proper: `materialize` to `runRows` 640, the subquery runs 600, `execSelIn`'s row branches 300, windows 260, `batchLevel` and its plan 300, `execSrf` 170, the row aggregates and sort 250, `eachRowBIn`'s and `outRow` 150; some of it moves into operators rather than going) |

R1-R8 are independent; R1 and R2 first (small, many tests), then R5 and
R4 (the OLTP gate), R6, R7, R8. After R9 `lexdb_pipe` is layer 6 and the
rest of exec layer 7 (6.2.3).

**The oracle after R9 (proposal).** Today every "three ways" test runs
its queries with batches on and off and compares; 58 tests do so. Once
the row engine is gone there is no second engine to compare with. The
proposal keeps the comparisons, with other references, in this order of
weight:

1. **The pipeline's own scalar path as the reference for its kernels.**
   Every operator already has a row-at-a-time path (a chunk of one, every
   expression by `bxEval`: what runs today when a batch gives way). A
   test setting (`SET lexdb_vector = off`, test-only like decision 5's)
   forces it everywhere: the same operators, no vector kernels, no
   numeric units, no batch narrowing. It keeps the oracle for what the
   tests compare most (expressions, NULLs, errors and their first failing
   row, overflow to values), at the cost of not checking the operators'
   own logic (joins, grouping, sorting), which 2-4 check.
2. **Plans against plans (metamorphic).** The planner's switches give the
   same query in other plans that must give the same rows:
   `SET lexdb_planner = rules`, `lexdb_plan.setUnnest(0)`, `setBushy`,
   `setRewrites`, `setKeyOrder`, the index paths (`SET
   enable_indexscan`-like hints, or a query with its index dropped), the
   hash against the per-row lookup (`semiCheaper`'s choice forced). A test
   runs its corpus under each and compares, as it compares on and off
   today. These check joins, semi, anti and mark joins, grouping
   placement and the rewrites against each other.
3. **Independent formulations** (SQLancer's ternary-logic partitioning
   and NoREC, generated from each corpus query): `q` = `q where p` union
   all `q where not p` union all `q where p is null`; `count(*) ... where
   p` = `sum(case when p then 1 else 0 end)`; an aggregate as its
   decomposition (`avg` = `sum/count`); a join as `exists` for a semi
   join. Cheap to generate, no second engine.
4. **The real databases' answers.** For the dialect corpora the
   expected rows come from PostgreSQL, SQL Server 2022 (podman,
   `lxl-mssql`) and Oracle as `gen_mssql.py` and the `tds_*`/`tns_*`
   generators do now, stored in the tests; the random corpora of
   `exec_batch`-style tests get a PostgreSQL run once (the scratch
   PostgreSQL in `~/Work/lexdb-bench`) and keep its answers.
5. **The stored answers** the suite has already (`// expect:`), which do
   not need a second engine.

The decision is the owner's: 1 is the cheapest to build (the operators
have the path) and closest to today's on/off; 2 and 3 are the ones that
keep checking the operators; 4 is the strongest per query and the most
work to keep. Until R9, `SET lexdb_batch = off` stays as it is.

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
