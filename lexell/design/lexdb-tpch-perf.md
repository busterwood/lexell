# TPC-H performance: closing the gap to PostgreSQL

Status: started 2026-11-16 at main `1744ef99`. The goal is to bring lexdb
level with, or close to, PostgreSQL 18.6 on one core across the 22 TPC-H
queries at SF1 (`bench/tpch`). `lexdb-tpch-plans.md` has the first plan
comparison and the fixes so far. This note is the plan, the rules every
workstream follows, and the record of what each experiment found.

The method: read how PostgreSQL does the thing we are slow at (its source
is at `~/Work/postgres`, tag `REL_18_6`), understand why it is fast, and
build lexdb's own version in Lexell. We study its algorithms and cost
reasoning; we do not copy its code.

## 1. Baseline

`~/tpch/out-baseline-1744ef99`: lexdb at `1744ef99` against PostgreSQL
with parallel query off, both pinned to CPUs 0-3, warm, median of three.
**Geometric mean lexdb / PG one core: 3.77**; level or ahead on 2 of 22.

| query | lexdb ms | PG one core ms | ratio | lexdb behind by |
|---|---:|---:|---:|---:|
| q1 | 15924 | 2833 | 5.6 | 13092 |
| q2 | 61 | 149 | 0.4 | -88 |
| q3 | 2642 | 489 | 5.4 | 2154 |
| q4 | 4004 | 180 | 22.2 | 3824 |
| q5 | 1703 | 260 | 6.5 | 1443 |
| q6 | 1061 | 468 | 2.3 | 592 |
| q7 | 5113 | 565 | 9.1 | 4548 |
| q8 | 425 | 236 | 1.8 | 189 |
| q9 | 4296 | 1605 | 2.7 | 2691 |
| q10 | 1612 | 625 | 2.6 | 987 |
| q11 | 197 | 55 | 3.6 | 142 |
| q12 | 1231 | 832 | 1.5 | 398 |
| q13 | 5938 | 818 | 7.3 | 5120 |
| q14 | 696 | 137 | 5.1 | 559 |
| q15 | 1413 | 532 | 2.7 | 881 |
| q16 | 580 | 220 | 2.6 | 360 |
| q17 | 37 | 515 | 0.1 | -478 |
| q18 | 2731 | 1050 | 2.6 | 1681 |
| q19 | 463 | 36 | 12.7 | 427 |
| q20 | 1140 | 114 | 10.0 | 1027 |
| q21 | 13525 | 687 | 19.7 | 12838 |
| q22 | 1200 | 76 | 15.9 | 1124 |
| all | 66.0 s | 12.5 s | | 53.5 s |

By time behind, q1 and q21 are 48% of the gap; q13, q7, q4, q9, q3 and
q18 most of the rest. By ratio, the semi/anti-join queries (q4, q21, q22)
and q19, q20 and q7 are furthest off.

## 2. Rules for every workstream

**Correctness first.** A change is kept only if:

- the lexdb suite passes (`LXL_NOCACHE=1 taskset -c 4-7,12-15 python3
  lexell/tests/lexdb.py --compiler /home/chris/Work/lexell/lexell/compiler/out/lxlc -j 2`,
  native builds, never the gcc path);
- all 22 TPC-H queries give the same rows and checksums as before (run with
  `TPCH_REF=~/tpch/out-baseline-1744ef99`: 19 match PostgreSQL exactly, and
  q1, q8 and q17 differ only in decimal scale, with checksums `0d3d0dc5`,
  `30016240` and `3f7be248` in lexdb);
- a new plan shape or operator has its own test in `tests/lexdb/run/`
  comparing its results with batches on and off and against an independent
  formulation (a join, NOT IN, a count).

**Measuring.** Only one benchmark runs at a time on this machine:

- Anything that starts a TPC-H server (`run.sh`, or `systemd-run` on ports
  5598/5599) or times anything runs under `flock ~/tpch/.bench.lock ...`.
- Servers run on CPUs 0-3 (`TPCH_CPUS=0-3`); 8-11, their SMT siblings, stay
  idle. Builds and tests run on 4-7,12-15 (`taskset -c 4-7,12-15`, `-j 2`).
- A/B against the baseline binary `~/tpch/bin/lexdb-1744ef99`, both
  measured in the same session; report medians of three warm runs and the
  run-to-run spread. Separate runs of an unchanged query move up to about
  8%, so a smaller difference is not a result.

**Where to work.**

- Each workstream has its own git worktree and branch from main, and its
  own TPC-H work directory `~/tpch-w/<name>` (the dbgen data and
  PostgreSQL's data directory are shared through symlinks; the lexdb data
  directory is a private copy). Never write to `~/tpch` itself.
- Do not change lexdb's on-disk format: the data directories are shared
  between binaries.
- Commit small, explained steps on the branch. The orchestrator merges into
  main.

**Recording.** Each workstream keeps its findings in section 4 of this note
(its own subsection): what PostgreSQL does and where in its source, what
lexdb does, the experiment, the numbers, and what was kept.

## 3. Workstreams

Split by cause, not by query, so each owns a part of the engine. Worktree
`~/Work/lexell-perf-<name>`, branch `perf/<name>`, work directory
`~/tpch-w/<name>`.

| name | owns | queries | PostgreSQL to read |
|---|---|---|---|
| `exec` | scan, expression and aggregate speed: how rows and values flow (batches, decimals, per-row `[]Val`) | q1, q6, q14, and the cost of streaming any wide scan | `executor/execExprInterp.c`, `executor/nodeAgg.c`, `utils/adt/numeric.c` (its aggregate states), `access/heap/heapam.c` (page-at-a-time scans) |
| `semi` | semi and anti joins: where they sit in the join order, a batched index-lookup semi/anti join, hash build and probe | q21, q4, q22, q20 | `executor/nodeNestloop.c`, `nodeHashjoin.c`, `nodeHash.c`, `optimizer/plan/subselect.c`, `optimizer/path/costsize.c` (semi/anti costing) |
| `joinorder` | the join order search and its estimates: selectivity, pushing a table's filters into its path before the search, equivalence classes, starting from the selective dimension | q5, q7, q8, q9, q10, q3's order | `optimizer/path/joinrels.c`, `allpaths.c`, `clausesel.c`, `equivclass.c`, `costsize.c`, `utils/adt/selfuncs.c` |
| `outer` | join methods for large and outer joins (hash right join, hash vs a lookup per row), IN over a grouped subquery, top-N and group aggregation on the sort | q13, q18, q12, q3/q10's sort and LIMIT | `nodeHashjoin.c` (right/full), `optimizer/path/joinpath.c`, `utils/sort/tuplesort.c` (bounded heap), `nodeAgg.c` (sorted grouping) |

Boundaries: `semi` owns semi/anti levels (`semiJoins`, `semiLevel`,
`materialize` and `bProbe` for them); `joinorder` owns the order of the
ordinary tables; `outer` owns the choice of join method for ordinary
levels; `exec` owns the batch engine's representation and evaluation.
Anything another workstream owns is raised with the orchestrator, not
changed.

## 4. Findings

(Each workstream's subsection.)

### 4.1 `exec`: scan, expression and aggregate speed

Branch `perf/exec`. Queries q1, q6, q14 and the cost of streaming a wide
scan. Design below (4.1.4) is phases 6-8 of `lexdb-architecture.md`
section 8, shaped by these measurements; step 1 of it is done and
measured (4.1.5).

#### 4.1.1 What the plans and profiles show (baseline `1744ef99`)

EXPLAIN ANALYZE, both pinned to CPUs 0-3, PostgreSQL with parallel query
off (`~/tpch-w/exec/adhoc/explain1.txt`):

| query | lexdb plan | lexdb ms | PostgreSQL plan | PG ms |
|---|---|---:|---|---:|
| q1 | full scan of lineitem (6.0M read, 5.92M kept), aggregate, sort | 16,588 | Seq Scan (428 ms) + HashAggregate + Sort | 2,850 |
| q6 | full scan (6.0M read, 114k kept), aggregate | 1,059 | Bitmap Heap Scan on `lineitem_shipdate` (0.91M rows, 2.9M rechecked lossy) + Aggregate | 418 |
| q14 | part full scan; hash join to lineitem's `lineitem_shipdate` range (76k) | 672 | Bitmap Heap Scan + Hash Join to a Seq Scan of part | 152 |

The plans are already the right shape; the time is execution. Profiles
(`perf record -e cpu-clock:u --call-graph fp --user-callchains` on the
server, resolved through `LXL_NATIVE_MAP`; `-g` alone is refused at
`perf_event_paranoid` 2):

- **q1, 15.3 s.** `batchGroups` refuses the query: an aggregate's
  argument must be an integer expression or a bare numeric column, and
  `sum(l_extendedprice * (1 - l_discount))` is neither. So the whole
  query runs on the row path: the batches are decoded (8.6% of samples,
  about 1.3 s, all the scan costs) and then every row is made a `[]Val`
  and grouped by `addToGroup` -> `accumulate` -> `eval` (inclusive 72%):
  `eval` 40% (by column *name*: `colIndex` + `rt_str_eq` + `memcmp` 8.6%),
  `arith` 28% (the operator matched as a string, `kindOf`, `asNum`, then
  `Decimal.addExact`/`mulExact`/`makeDec`), and copying values (`dup`
  13.9%, `drop` 4.6%).
- **q6, 1.03 s.** Batched scan and filter (`batchLevel`), with the
  aggregate again on the row path (114k rows only). The cost is decoding
  numerics into boxed `Val.Num` (`Decimal.fromUnits`/`fromFraction`
  12.6% inclusive) and comparing `Val`s per row (`compare`, `compareTime`
  for the date conditions, about 10%).
- **q14** is a join (hash build of part: `materialize` 24% of its share);
  numerics were not its cost.

Measured costs underneath (from section 6 of `lexdb-tpch-plans.md`,
re-checked here): `count(*)` over lineitem 0.50 s; the scan itself is not
the gap (PostgreSQL's Seq Scan is 0.43 s, lexdb's decode of q1's seven
columns about 0.6 s after step 1).

#### 4.1.2 What PostgreSQL does (REL_18_6)

- **Scan.** `heapam.c`: `heap_prepare_pagescan` / `page_collect_tuples`
  collect a page's visible tuples once under one buffer lock, and
  `heapgettup_pagemode` returns them one at a time; a tuple is deformed
  only up to the last attribute the plan needs (`EEOP_SCAN_FETCHSOME`,
  here JIT-deformed). No value is copied out of the page for a
  pass-by-reference type.
- **Expressions.** `execExprInterp.c`: each expression is compiled once
  into a flat array of steps run by `ExecInterpExpr` (computed goto); a
  column is a slot index, an operator a resolved function pointer. No
  name lookup, no string dispatch at run time.
- **Aggregation.** `nodeAgg.c`: all aggregates' transitions are one
  compiled expression (`ExecBuildAggTrans`, steps
  `EEOP_AGG_PLAIN_TRANS_BYVAL` etc.), run by `advance_aggregates` per row;
  hash grouping hashes the key once per row (`lookup_hash_entries`,
  `TupleHashTable` over simplehash).
- **Numeric aggregate states.** `numeric.c`: `sum`/`avg` of numeric keep a
  `NumericAggState` whose `NumericSumAccum` adds a value's base-10000
  digits into int32 digit arrays (positives and negatives apart), carrying
  only every NBASE-1 additions (`accum_sum_add`, `accum_sum_carry`): no
  allocation per row. Integer sums use `Int128AggState` (128-bit).
  Products are still `numeric_mul` on variable-length base-10000 values,
  which is most of PostgreSQL's 2.4 s HashAggregate on q1.

lexdb's own path (proposed by the orchestrator and confirmed by the
profile): a column of `numeric(p, s)` holds values of display scale s
(coerce quantizes them, 1.234 -> 1.23) below 10^p, so for p <= 18 each is
an integer count of 10^-s ("units", which column leaves already store:
`C_UNITS`). Sums, products and comparisons are then integer arithmetic,
with the scale tracked at compile time; PostgreSQL does not do this.

#### 4.1.3 Why lexdb is slow here

The batch engine has two expression systems that disagree on coverage:
`BNode`/`bEval` (vector, integers and booleans only, plus special nodes
for text, `IN`, `LIKE`) and `CX`/`cEval` (scalar, everything), glued by
`BNode.Gen` (a `CX` run per row over a row built from the batch). Anything
`bCompile` does not take sends the whole operator back to the row path,
which evaluates `Expr` trees by name over `[]Val`. Numerics and dates are
boxed `Val`s in batches (`BK_VAL`), so even batched they are compared and
added as `Decimal`/`Val` per row. Each operator (`batchLevel`,
`batchGroups`, `eachOut`, `sortBatches`, `winBatch`) has its own driver
and its own "give way to the row path" rule.

#### 4.1.4 Design: one typed expression IR over one Chunk (phases 6-8)

**Chunk** (`lexdb_rows`, extending `Batch`): per column a typed vector
and NULL flags, plus a selection vector. Kinds: `I64` (int2/4/8),
`BOOL`, `DEC(s)` (numeric(p, s), p <= 18, as units; step 1 adds it as
`BK_DEC + s`), `DAY` (date as days), `MICROS` (time, timestamp,
timestamptz as their words), `F64`, `CODE` (a dictionary text's code
with the leaf's dictionary, for keys, `=`, `IN` and `LIKE` matched once
per entry), and `VAL` (anything else, boxed). The decoders fill typed
vectors straight from the column leaf's codecs (`C_FOR`, `C_UNITS`,
words), so most queries never make a `Val`. A row is a chunk of one.

**One expression IR** (new module `lexdb_vx`, below exec; kernels in
`lexdb_vec`, step 1). A bound tree: each node has an operator, a result
kind (from the input kinds) and children; constants are folded and
converted to the kind they are used at when bound (a numeric constant to
units at its operand's scale, a date literal to days in the session's
zone, an IN list sorted once). Two evaluators over the same tree:

- the vector backend runs typed kernels (`lexdb_vec`) for the typed kinds;
- a *generic* node (functions, casts, text, anything without a kernel)
  runs the row path's own scalar operation (`unaryVal`, `binVal`,
  `castVal`, `callAt`, `coerce`, `compare`) per row over boxed inputs.
  The same functions serve the row path, so there is one semantics, not
  two;
- a kernel never raises a SQL error: where a typed result does not fit
  (a units overflow), it *spills*: that node is evaluated generically for
  that chunk, which gives the exact Decimal result or the row path's
  error. (Step 1 spills the whole operator back to the row path; the
  per-node spill comes with the IR.)

The scalar ops the generic node needs (`arith`, `compare`, `coerce`,
`binVal`, `castVal`, the pure functions of `callAt`) move first into a
module below exec (`lexdb_ops`); session-bound calls (sequences, catalog
functions, subqueries) stay exec's and are never compiled, as `cxOf`
already excludes them. Deleted when the IR serves every operator:
`BNode` (17 variants), `BGen`/`bGenVals`, `CX`/`cEval`/`cxOf`,
`bCompile`/`bValCmp`/`bColPair`, `outNode`'s `ONode`, and the duplicated
type and zone rules (`bTimeVal`, the IN list's constant conversion), which
the binder does once for both evaluators. The IR also does what step 1's
profile asks for: common subexpressions computed once per chunk (q1's
`l_extendedprice * (1 - l_discount)` is evaluated twice), and constants
pre-scaled (q1's `1 - l_discount` scales the constant 1 per row).

**ExecStrategy and one driver.** One choice per plan: chunks (default) or
row (a chunk of one: point lookups, and the test-only reference). One
driver: scan -> filter -> join probes -> sink, the sink one of aggregate,
sort/top-N, output projection, window buffer. It replaces the five
skeletons and their restarts on the row path; `rs.batch` becomes the
strategy, chosen once.

**Aggregation.** One hash table keyed by typed keys: up to two or three
small keys (I64, DAY, DEC, CODE) packed into one int64 for an
open-addressing integer table; other keys by their encoded bytes (as
now). Typed states: count, i128 sum for I64 and DEC (step 1), Decimal sum
for `VAL` numerics, typed min/max; finished into the existing `Acc` so
`finish` (avg's rounding, NULL for no rows) stays the one place of those
semantics. The same table serves hash join builds (phase 8).

**Output.** The output projection reads typed vectors; DEC is formatted
from units directly, DAY from days, without a `Val`.

**Order of steps.** Each is shippable alone: the suite, the 22 TPC-H
checksums, a new test where a shape is new (batches on/off and an
independent formulation), and an A/B against the baseline binary with no
query slower past noise.

1. *Done (4.1.5).* `DEC(s)` in batches, `lexdb_vec` kernels (+ - *
   compare, i128 sums), in single-table grouped aggregation only
   (`batchGroups`); a units overflow gives way to the row path.
2. `lexdb_ops` (the scalar operations below exec) and `lexdb_vx`: the
   bound IR with typed kinds; `bCompile` and the batch evaluator move onto
   it, `Gen` becomes the generic node; constant pre-scaling and CSE.
   Delete `BNode`/`BGen`. Neutral or better on the 22 queries.
3. `DAY`, `MICROS` and `DEC` in every operator through the IR
   (`batchLevel`, joins' gathered columns, sort keys, output): q6's date
   conditions as integer compares, q3/q5/q10/q12/q14's dates and money.
4. Typed hash aggregation (packed keys, `CODE` keys for char(1) and
   dictionary texts): q1's two char(1) keys cost about 17% after step 1
   (`bKeyVal`, `encIdxPart`, `sipKeyedStr`, `Map.find`).
5. ExecStrategy and the one driver; the row path becomes a chunk of one;
   delete `CX`/`cEval`, the per-operator restarts and `rs.batch` as a
   switch.
6. The chunked pipeline across joins (`bJoinAll`/`bProbe` on `Chunk`, one
   hash table for builds and groups), one comparator for sorts, COPY.

#### 4.1.5 Step 1: numeric(p, s) as units in grouped batches

What changed (commit on `perf/exec`):

- `lexdb_rows`: `BK_DEC + s` (`decKind`), chosen by `decColKind` for a
  numeric(p, s) column with 0 < p <= 18. The column-leaf decoder reads a
  `C_UNITS` place of the same scale straight into the integer vector
  (`intsInto`, no `Decimal`); other numeric leaves, fixed and tagged rows
  and a column's missing value go through `put`, which takes a `Val.Num`
  only if its display scale is s and its units fit (`decUnits`), else the
  batch gives way (the decoders' existing "not of the column's kind").
- `lexdb_vec` (new, below exec): `arith` (+ and - at the larger scale, *
  at the sum, checked, false on overflow), `cmp` (by value, aligned in
  128 bits), `sum` (128-bit accumulators per group), `sumVal` (the Decimal
  of a 128-bit sum, None past 38 digits).
- `lexdb_exec`: `bCompileD(..., dec)` types numerics as `BT_DEC + s`
  (columns, numeric constants, integers read as scale 0, as `arith` reads
  them) with `DArith`/`DCmp` nodes; only `batchGroups` asks for it, and
  only for one table (`dec = !jn`), so every other operator compiles as
  before. Sums and averages of a DEC argument keep i128 sums; min and max
  units; `count` as before. The groups end as `Acc`s holding the same
  `Val.Num` the row path's `addExact` chain gives (display scale s), so
  `finish` (avg's division and rounding) is unchanged. A units overflow
  raises an internal `XXDEC` that `batchGroups` turns into "give way":
  the row path reruns the query from the start (nothing was emitted).

Why the results are exactly the row path's: numeric(p, s) values all have
display scale s; Decimal's `addExact` gives scale max(sa, sb) and
`mulExact` sa + sb (capped at 38 minus the integer digits, which units
below 2^63 never reach) and both are exact, so units arithmetic at those
scales is the same value at the same display scale; sums of 2^63-bounded
values in 128 bits cannot overflow before 2^64 rows, and a result past
38 digits gives the row path's 22003 (`decErr`).

Test: `tests/lexdb/run/exec_batchdec.lxl`: 400 random grouped queries
(sum, avg, min, max, count, FILTER; products, mixed scales, numeric
constants, integers mixed in; one key, two char(1) keys, an expression
key; NULLs) over 3,000 rows, each run with batches off (Decimal), on, and
over a copy with plain `numeric` columns (never units): all agree, display
scale included, and all 400 ran as units. Also q1's and q6's shapes, a
product past 2^63 (gives way: same result), a sum past 2^63 (kept in 128
bits), a typmod-less numeric and a numeric(20,2) (not units), and 100
queries in a transaction with its own writes. Suite: 174 passed.

A/B, same session, `run.sh` medians of three warm runs (spread min-max):

| query | baseline `1744ef99` ms | step 1 ms | speed-up | PG one core ms |
|---|---:|---:|---:|---:|
| q1 | 15,546 (15,511-15,630) | 2,127 (2,095-2,134) | 7.3x | 2,833 |
| q6 | 1,019 (1,019-1,023) | 549 (539-552) | 1.9x | 468 |
| q14 | 678 (613-692) | 682 (619-686) | 1.0 | 137 |

q1's checksum stays `0d3d0dc5`; q6 and q14 match PostgreSQL. q1 is now
ahead of PostgreSQL on one core (2.1 s vs 2.8 s). q14 is a join (the
units kind is not used there yet: step 3).

All 22 (`~/tpch-w/exec/out-dec2-all`, one run of three): every checksum
unchanged (19 match PostgreSQL; q1, q8, q17 keep `0d3d0dc5`, `30016240`,
`3f7be248`). Total 66.0 s -> 53.2 s against the baseline run (different sessions). Single-table
grouped sums elsewhere gain too; a second same-session A/B (baseline
then step 1, medians of three):

| query | baseline ms | step 1 ms | ratio |
|---|---:|---:|---:|
| q9 | 4,667 (4,559-4,737) | 4,721 (4,632-4,735) | 1.01 |
| q13 | 6,077 (5,991-6,087) | 6,888 (6,846-6,959) | 1.13 |
| q15 | 1,550 (1,482-1,557) | 1,062 (1,049-1,062) | 0.68 |
| q18 | 2,947 (2,311-2,969) | 2,332 (1,753-2,344) | 0.79 |
| q20 | 1,259 (1,239-1,264) | 1,210 (1,190-1,211) | 0.96 |
| q21 | 14,345 (14,240-15,156) | 14,243 (14,193-14,351) | 0.99 |

q15 (the revenue view's grouped sum of `l_extendedprice * (1 -
l_discount)`) and q18 (its grouped `sum(l_quantity)`) now run as units.
q13 has no numeric and does not reach the changed code (its grouping is
over a join and a derived table: `dec` is off, and `batchGroups` refuses a
derived table before compiling anything); its 13% in this pair is past
the 8% noise rule and is NOT explained here: see 4.1.6.

Profile after step 1 (q1, 2.0 s): decoding 30% (`fillBatch`,
`colsInto`, and a new batch allocated per fill: `newBatch` 9.4%); the
aggregates' expressions 33% (`bEval` with `lexdb_vec.arith` 16%, the
constant 1 scaled per row by `scaleUp` 3%, the shared product computed
twice); grouping by the two char(1) keys about 17%; `Val` copies of the
key texts 11% (`dup`). q6 after step 1: its date conditions compared as
`Val`s (`compare`, `compareTime`, `memcmp`) are the largest item. These
are steps 2 to 4.
