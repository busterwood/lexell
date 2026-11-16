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
- Tests, probe builds and probe runs hold the same lock *shared*
  (`flock -s ~/tpch/.bench.lock ...`): they run alongside each other but
  never during a benchmark. All-core load lowers this CPU's boost clock and
  shares its L3 and memory bandwidth; a full run came out 10-25% slower
  under it. Never run tests inside an exclusive section (it deadlocks).
- `run.sh` turns CPU boost off for a run and restores it after
  (`bench/tpch/cpu-boost`; README "CPU boost"), so every recorded run is at
  the base clock; `config.txt` records the clock a run had. Runs with boost
  on and off are not comparable.
- Leave no background process running: kill what you start.
- A/B against the baseline binary `~/tpch/bin/lexdb-1744ef99`, both
  measured in the same session; report medians of three warm runs and the
  run-to-run spread. Separate runs of an unchanged query move up to about
  8%, so a smaller difference is not a result.

**PostgreSQL's settings (a follow-up).** PostgreSQL runs natively (the
Arch package, a transient systemd unit pinned to the same CPUs, no
container), with only `shared_buffers=12GB` and the parallel settings
set: `work_mem` 4 MB, `random_page_cost` 4, `effective_cache_size` 4 GB
and JIT are its defaults. A tuned column (`work_mem`, `random_page_cost`
for NVMe, JIT on and off, chosen by measurement) should sit beside the
default one before the comparison is called final.

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

**Decision, 2026-11-16: refactor the executor as the `exec` work, not
before it.** The review of the TPC-H merge found three regressions where
the batch path re-implemented row-path semantics and drifted (the "<>"
summary's batch key map and its crash, batched IN lists ignoring the
session's zone), and every speed-up has to be written twice while the two
paths exist. `lexdb-architecture.md` section 8's phases 6-8 (one batch
driver, one expression IR with scalar and vector backends, a chunked
pipeline with one hash table and comparator) are close to the executor
that closes q1's gap. So `exec` designs those phases from PostgreSQL's
executor and the q1/q6/q14 profiles, and builds them in shippable steps,
each gated by the suite, the checksums and an A/B. New executor code goes
in new modules below exec where it can. The plan-side workstreams
(`semi`, `joinorder`, `outer`) carry on: their changes are local. Once
their first branches merge, the orchestrator splits `lexdb_exec.lxl`
mechanically (the planner search into `lexdb_plan`, the batch engine into
its own module) and catches `arch/exec-extract` up with main, so the split
has nothing in flight to conflict with.

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
the 8% noise rule and was not explained here; the orchestrator's
interleaved A/B (base, exec, base, exec) found it noise (exec 3% slower in
one pair, 1% faster in the other, the baseline itself moving 12% between
pairs).

Profile after step 1 (q1, 2.0 s): decoding 30% (`fillBatch`,
`colsInto`, and a new batch allocated per fill: `newBatch` 9.4%); the
aggregates' expressions 33% (`bEval` with `lexdb_vec.arith` 16%, the
constant 1 scaled per row by `scaleUp` 3%, the shared product computed
twice); grouping by the two char(1) keys about 17%; `Val` copies of the
key texts 11% (`dup`). q6 after step 1: its date conditions compared as
`Val`s (`compare`, `compareTime`, `memcmp`) are the largest item. These
are steps 2 to 4.

#### 4.1.6 Step 1's review: nothing slower than before units

The review of step 1 found one plausible regression by reading: with a
numeric(p, s) column typed as units in a grouped single-table query, a
condition the units do not compile (`k IN (...)`, `k LIKE ...`, `k >
1.5::float8`: the IN branch takes only integer, boolean and value
columns, `bValCol` only value columns) sent the query to the row path,
where before units it ran over batches with the numeric as a value.
`batchGroups` now tries units first and, when the query read a numeric
as units and that gave way (a condition not compiled, a value not of its
scale, a result past its units), runs the batches again with numerics as
values before the row path: nothing that ran over batches before step 1
runs on the row path now (commit `58bac6c4`). `exec_batchdec` adds the
review's gaps: data before its first checkpoint; GROUP BY a numeric column
and expression; a product of exactly -2^63 units (kept) and its negation
(past units: the row path); the IN list, LIKE and float constant (over
batches as values); comparisons with a float column, a plain numeric
column and another numeric(18,0); a scale changed by ALTER TYPE and a
column added with a numeric default, before and after a checkpoint. A
native units IN list was not built: the retry covers it, and no TPC-H
query has one.

#### 4.1.7 Step 2a: every join condition compiles (the generic node)

The other workstreams' profiles put 75-90% of q3, q5, q7, q8 and q10 in
`tryRow`/`runLevel`: `bJoinPlan` sends a whole multi-table query to the
row path when one join condition does not compile for batches, or when a
level after the first is neither a hash nor a whole-primary-key lookup.
A debug build (each refusal's reason printed; q3, 4, 5, 7, 8, 9, 10, 12,
13, 18, 20, 21, 22) finds the first cause in q7 only (its cross-table
`(n1.n_name = .. and n2.n_name = ..) or (..)`) and in q21 (`o_orderstatus
= 'F'`, a char(1) constant: `#bppad('F', 1)` is a call, so `bConst`
refuses it); every other refusal is `bJoinPlan`'s first check, which
holds the second cause (a `perRow` level that is not a whole-key lookup:
by the plans, q3/q5/q10's lineitem by `l_orderkey`, a primary key prefix,
and q8/q9's secondary index lookups) and the join types batches do not
run (the debug build did not tell the two apart).

The first cause is the IR's generic node, which exists already for the
first level (`bLevelPlan`: `BNode.Gen`, a compiled `CX` run per row over
the batch). `bJoinCond` gives a join level's conditions and post
conditions the same fallback: compiled for batches, else compiled per
row. Semantics are the row path's own (`cEval`), and a row on which a
condition gives an error sends its batch to the row path, as before.
Test: `exec_joingen` (an OR across tables against a UNION ALL of its
branches; a char(n) constant on a lookup level against a semi join count;
a substring IN a list; a CASE; a function of both tables; division by
zero on some rows; grouped; in a transaction): with batches as without,
and the joins ran over batches with a compiled condition.

A/B, same session, nothing else running on 4-7 (medians of three, spread):

| query | before ms | after ms | ratio | PG one core |
|---|---:|---:|---:|---:|
| q7 | 5,021 (4,861-5,033) | 1,621 (1,599-1,637) | 0.32 | 565 |
| q8 | 432 (425-436) | 411 (408-415) | 0.95 | 236 |
| q10 | 1,645 (1,608-1,664) | 1,543 (1,535-1,627) | 0.94 | 625 |
| q21 | 14,391 (14,126-14,579) | 13,767 (13,625-13,773) | 0.96 | 687 |

(An earlier pair, taken while the suite ran on 4-7, showed q8 +14% and
q10 +8%: the debug build shows neither query reaches the change, and the
clean pair puts both within noise.) q21 needs the second cause too: its
orders lookup now compiles, and a later level is a per-row range.

All 22 at `a2718e8b` (main with `perf/joinorder` merged, one run of
three, `~/tpch-w/exec/out-jc2-all`): every checksum unchanged (q1, q8,
q17 keep theirs). q7 1,575 ms; q3 2,048 and q5 937 owe their change to
`joinorder`'s merge, not to this step (the debug build shows neither
reaches it).

Next (step 6 brought forward): batch a per-row level that reads a key
range or an index per outer row, with `perf/semi`'s `bRange` (each
batch's distinct keys in key order straight from the leaves) once it is
on main, rather than a second reader.

#### 4.1.8 Step 2b: inner and LEFT levels read by a range per row (bRange)

`bJoinPlan` now takes a per-row level that is not a whole-key lookup but
reads a range by its path's leading equalities only (`rangePath`: a
primary key's leading columns or an index's equalities, no range bound,
not backward) and joins it over batches with `perf/semi`'s `bRange`, as
semi and anti levels are: each batch's distinct keys read in key order
straight from the leaves, an index's entries decoded or their rows read
by primary key. For an inner or LEFT level the whole range is read (a
semi or anti level still stops at its first row when it has no filter).
Also: `bConst` takes `#bppad` of constants as a constant, so a char(n)
column compared with a literal (q21's `o_orderstatus = 'F'`, q7's nation
names) is a batch comparison (`ValCmp`), not a per-row compiled one. The
EXPLAIN ANALYZE double count when a batch gives way is `semi`'s fix
(7f350792, the callers of `bJoinAll` restore the counts); this branch's
own restore in `bJoinAll` was dropped in the merge so it is done once.

Test: `exec_joinrange` (orders, lineitem keyed by order and line with an
index by part, parts; orders without lines, NULL keys and filters):
fixed and random INNER and LEFT queries over two and three tables, rows,
sorted and grouped, residual conditions on the looked-up table, against
batches off and against a hash form of the same join (`l.lk + 0 =
o.ok`); EXPLAIN ANALYZE's counts the same with batches on and off,
including where a batch gives way (division by zero on some row); in a
transaction with its own writes. `exec_join`'s index lookup now runs over
batches (its EXPLAIN shows `batches 1`); `exec_joingen` counts batch join
plans (`joinPlans`), since the char(n) and OR conditions now compile
outright. Suite: 179 passed in the full run; the three it failed (these two
expectations, and `exec_joinrange` past its time under load, now smaller
with a 90 s timeout) pass when rerun.

A/B, same session, boost off (run.sh's fixed clock: about 20-25% slower
than the boosted figures above), medians of three; main `5917302b`
against this step:

| query | main ms | step 2b ms | ratio |
|---|---:|---:|---:|
| q3 | 2,450 (2,447-2,451) | 2,408 (2,404-2,414) | 0.98 |
| q5 | 1,150 (1,150-1,151) | 1,165 (1,163-1,166) | 1.01 |
| q8 | 480 (479-481) | 362 (361-363) | 0.75 |
| q9 | 5,373 (5,242-5,411) | 5,327 (5,224-5,345) | 0.99 |
| q10 | 1,816 (1,797-1,817) | 1,192 (1,174-1,195) | 0.66 |
| q21 | 8,568 (8,566-8,594) | 8,450 (8,403-8,479) | 0.99 |

All 22 (`~/tpch-w/exec/out-rg3-all`): every checksum unchanged (q1, q8,
q17 keep theirs). EXPLAIN ANALYZE says why four did not move:

- q3 and q5: their orders level is `index orders_cust_date range` per
  row, the customer's equality *and a range on o_orderdate* (`p.rng`),
  which `rangePath` leaves out, so the query stays on the row path (q5's
  first scan shows no batches). Next: let `bRange` read an equality
  prefix with a bound on the next column, as `pathScan` builds it.
- q9: over batches already (its levels are hashes and whole-key lookups);
  its 5.3 s is elsewhere (319k rows through three lookups and the
  derived table).
- q21: over batches already (`semi`'s work); `o_orderstatus = 'F'` now
  compiles for batches outright.

### 4.2 `semi`: semi and anti joins

**What PostgreSQL does.** `pull_up_sublinks` (prep/prepjointree.c)
turns a WHERE conjunct `EXISTS (...)` or `x IN (...)` into a join-tree
node of type JOIN_SEMI, and `NOT EXISTS` into JOIN_ANTI
(`convert_EXISTS_sublink_to_join`, `convert_ANY_sublink_to_join` in
plan/subselect.c). The subquery's tables then take part in the ordinary
join search, constrained only so that the semi join's inner side is
joined as a unit after the tables its outer values come from: the join
search places it wherever it is cheapest. For q21 it puts the anti join
after the hash join of lineitem with (supplier, nation), on 156,739 rows,
and the semi join after that, on 13,859. The join itself is a nested loop
whose inner side is an index scan with the correlation as its index
condition (nodeNestloop.c: `single_match` for JOIN_SEMI stops the inner
scan at the first match, JOIN_ANTI emits the outer row only when the scan
found none). Its cost (costsize.c, `final_cost_nestloop` with
`semifactors`): a matched outer row pays a fraction 2/(match_count+1) of
the inner scan, an unmatched one only the index descent when every join
qual is an index qual (`has_indexed_join_quals`). q4 and q22 are the same
shape: 57,218 and 19,000 index probes, 0.007 and 0.002 ms each.

**What lexdb did.** A correlated EXISTS whose outer values are equality
keys was either hashed (the whole inner side read once: q21's 6M and 3.8M
lineitem rows, q4's 3.8M) or left a subquery run per outer row, at about
140 us a run for a primary-key range and 26 us for a secondary index's
(the run's setup, not its reads). And the semi level was placed directly
after the first table its outer values come from, before the joins that
cut the rows: q21's semi and anti joins ran on lineitem's 3.79M rows.

**Changed (kept).**

- *A semi or anti join looked up per row as a join's level*
  (`semiLookable`, `semiLook`, `runLevel`'s `semiSub` branch, `bRange`).
  An EXISTS / NOT EXISTS over one table whose path is its outer values'
  leading equalities becomes a level of that table, perRow, its filters
  the subquery's (the residual `l3.l_suppkey <> l1.l_suppkey` too) with
  its columns renamed to hidden ones; the subquery is no longer run. The
  row path reads the range until a row passes; the batches read each
  batch's distinct key prefixes in key order, each range in place
  (`scanLeaves`, column leaves decoded a run at a time), and hand the
  rows to `bJoinTail` (first passing candidate per outer row for a semi
  join, none for an anti join). An integer key's equality with its own
  path value is dropped from the filters, so a range with no other filter
  stops at its first entry (q22's NOT EXISTS reads one index entry per
  customer, index only).
- *Cost.* `semiLookRun`: a descent and the first row (COST_DESCENT +
  COST_KEY_ROW), then 1.8 per further row of a primary key's or a covering
  index's range, 49 an index entry and its row; compared with the hash's
  `inner * (COST_SCAN + HASH_BUILD) + outer * HASH_PROBE` at the outer
  rows of the semi level's place. PostgreSQL's 2/(match_count+1) fraction
  is not modelled (the whole range is charged): it only matters near the
  crossover.
- *Placement.* `orderRows` estimates the rows after each level of the
  chosen order (the join search's own estimates: each table's rows by its
  own conditions, an equality class by its distinct values), and
  `semiJoins` places each semi/anti level after the level, from the one
  where its outer values are known, with the fewest rows (not past an
  outer join). q21's two levels now run after supplier, nation and
  orders.

A/B, `run.sh` lexdb only, pinned, medians of three warm runs (min-max),
the baseline binary `lexdb-1744ef99` and this change measured in the same
session; all four checksums unchanged:

| query | before ms | after ms | PG one core ms |
|---|---:|---:|---:|
| q4 | 4,272 (4,159-4,290) | **543** (543-557) | 180 |
| q21 | 14,076 (13,995-14,140) | **10,962** (9,907-10,979) | 687 |
| q22 | 1,239 (1,180-1,240) | **598** (592-607) | 76 |
| q20 | 1,254 (1,252-1,260) | 1,220 (1,194-1,222) | 114 |

A run of all 22 (`out-t3all`, one session): every result as before (19
match PostgreSQL's, q1, q8 and q17 keep lexdb's checksums 0d3d0dc5,
30016240, 3f7be248); q4 539 ms, q21 9,140 ms (9,092-9,215), q22 596 ms;
the 22 sum to 56.3 s against the baseline's 66.0 s. q21 moves 9.1-11.0 s
between sessions.

The first version read each range with `Store.scan`, which copies every
entry and rebuilds a column leaf's row value (`Node.val`, 25% of q4's
time): q4 was 1,050-1,500 ms with it; reading the ranges in place
(`scanLeaves`, decoding a run of a column leaf at a time as the first
table's batches do) is the 543 ms.

**Where the rest of the time is (profiled, `perf` on the server).**

- q21 (10.9 s): the semi and anti joins are now small (75,871 and
  73,089 lookups, 92,139 and 134,711 rows read). The time is the plan
  before them, and it runs on the row path: `bJoinPlan` gives up on the
  join because the orders level's condition `o_orderstatus = 'F'` (a
  char(1) comparison) does not compile for batches (`bCompile` returns
  None), so every one of lineitem's 3.79M kept rows goes through
  `tryRow` and `runLevel` (63% of the samples) and two row-path hash
  probes (supplier, nation). Without that conjunct (an experiment, not
  the same query) the joins run over batches and the query takes 7.9 s,
  the rest being lineitem's 6M-row scan and its filter. Both are the
  `exec` workstream's (char(n) comparison in `bCompile`; the scan).
  PostgreSQL's plan also hashes supplier joined to nation (411 rows) and
  probes it once per lineitem row, where lexdb's left-deep order probes
  supplier's 10,000 and then nation's 1 for each of the 3.79M rows: a
  hash of a join (a bushy plan) is the `joinorder` workstream's.
- q22 (598 ms): the anti join is 19,000 index-only lookups reading one
  entry each. The time is `substring(c_phone from 1 for 2) in (...)` on
  two scans of customer's 150,000 rows, evaluated by the row path's
  function calls (`callFn`, `cEval`, `callMisc`: 30% self time): the
  `exec` workstream's.
- q4 (543 ms): orders' full scan of 1.5M rows (36% before the in-place
  reads) and 57,218 range lookups (229,691 rows). PostgreSQL reads the
  57,218 orders through a bitmap scan of `orders_date` (37 ms); lexdb's
  `choosePath` takes the scan for a range over 1/32 of the table (this
  one is 3.8%), as it has no bitmap scan.
- q20 is not a semi join in the sense above: its `ps_suppkey IN (...)`
  is a lookup per value, and the time is the correlated scalar `sum`
  over lineitem run per partsupp row (8,508 runs, about 100 us each, the
  run's setup: `runChild` builds a `Run`, `prepare` compiles every
  level's conditions, the batch plan is made again) and partsupp's scan:
  2,127 part keys are over `IN_LOOKUP_MAX` (1,000), so partsupp is read
  whole (800,000 rows) instead of by 2,127 key ranges. PostgreSQL runs
  the same subplan per row at 27 us. Unchanged here.

**Not done, and next.**

- Not modelled: PostgreSQL's early-stop fraction 2/(match_count+1) for
  a matched outer row; lexdb charges the key's whole range. The batches
  also read the whole range when the level has a filter (the row path
  stops at the first row that passes); a semi join with a filter could
  stop a key's range once one row passes, at the cost of evaluating the
  filter during the read.
- Only EXISTS / NOT EXISTS over one table with an equality-keyed path
  becomes a lookup level. A two-table EXISTS, an IN whose value is the
  inner table's key, and a range-keyed path stay hashed or per row.
- q20: an IN over a subquery whose values exceed `IN_LOOKUP_MAX` could
  choose its key lookups by cost against the table's rows (2,127 ranges
  against 800,000 rows); and the per-run cost of a correlated subquery
  (about 100 us) is setup, not reading: caching the run's prepared state
  across runs is the larger part of q20.
- For the other workstreams: char(n) comparisons in `bCompile` (q21's
  joins run on the row path for `o_orderstatus = 'F'`), `substring` over
  batches (q22), and a hash of a join for q21's (supplier, nation).

**Review fixes (after eec0db53).** An independent review found a wrong
result in the lookup level, and the new tests found three faults that
main has too:

- An EXISTS nested in another subquery, its filter on the outermost
  query's value, became a lookup level whose condition the middle
  subquery's unnesting (`hashSub`) took for its own key and dropped:
  wrong rows, and a crash over batches. `semiLookable` now refuses
  conditions on the query's own outer values. `hashSub` now refuses a
  subquery whose semi or anti level has a condition on an outer value
  (`80d960e0`).
- Over batches, a hash semi level's residual on its own columns and an
  outer value only was skipped (`bJoinPlan` took it for one that
  `materialize` applies). Fixed in the same commit; main has it.
- A NULL outer value matched a mixed key of a "<>" summary over batches
  (`bProbe`; `06c8b1c7`). Main has it; TPC-H has no such NULLs.
- An outer char(n) value was compared as an untyped text, blanks
  included (`faea665f`). Main has it.
- Reverted: `d665f217` gave an outer column of the default collation an
  implicit collation, so that EXISTS raised the join's 42P21 against a
  case-insensitive column. A second review judged it wrong for
  PostgreSQL, where the non-default implicit collation wins over the
  default (parse_collate.c), and harmful: it failed at plan time,
  CREATE VIEW too, and for outer columns made of literals. **Open
  question:** how an outer reference's collation is derived, per
  dialect. PostgreSQL lets the non-default implicit collation win;
  lexdb's join, like SQL Server, treats it as a conflict; EXISTS on main
  follows PostgreSQL. In a T-SQL session `exists (select 1 where o.t =
  'K1')` therefore does not compare as the outer query does.
- `bRange` now counts the rows it holds against max_statement_mem.
  Past the limit it hands the scan to the row path. "joined" counts
  the same on every semi/anti path (`6eb8597b`).

**Second review's pre-existing bugs (step 3).**

- An outer value is now typed as its column (`10b78163`). Before, only
  an outer char(n) was typed (`faea665f`); any other outer column was an
  untyped parameter, read as the other side's type. So an outer text
  'x ' was padded as an inner char(3) and equalled 'x'. Separately, the
  hashed subquery (9.9) keyed `timestamp = date`, `text = integer` and
  `float = numeric`, which = compares and a hash's keys do not. The join
  found 28 rows for one of these where EXISTS found none. Now
  `outerRef` casts the parameter to the column's type, `substRefs`
  drops that cast again, and the hints see through it. `keyConj` keys a
  hash only on types it compares as = does. The exec reviewer's case (a
  filter on an outer char(3) alone, run per row) has been right since
  `faea665f` and has a test now.
- A char(n) column's collation was ignored (`8bdbbfaf`): `isTextOid`
  left out bpchar. A case-insensitive char column now compares, matches
  and groups as a case-insensitive text column does.
- When a batch's join gave way to the row path, its counts were counted
  twice (`7f350792`). `bRange`'s memory room also did not include rows a
  grouping or a sort held in its own count; `Run.aside` now carries
  them. A row-path consumer's count is still not seen.
- A third review found that typing every outer column truncated values.
  lexdb labels some derived columns narrower than their values: int
  UNION ALL numeric is labelled int, date UNION ALL timestamp is
  labelled date. So `(select o.x)` turned 2.5 into 3. Now only a base
  table's column is typed; a derived table's column stays an untyped
  parameter, as on main. Same-type char(n) and float keys of a hashed
  subquery are hash keys again, as on main. **Open:** the union column
  labels themselves are wrong. On both builds, a join on a
  date-UNION-timestamp column gives 216 rows where EXISTS gives 432.

### 4.3 `joinorder`: the join order and its estimates

**How the plans were compared.** EXPLAIN ANALYZE on both engines (lexdb
at `1744ef99`, PostgreSQL one core), lexdb profiled with `perf` (user
call chains; the map from `LXL_NATIVE_MAP`), and alternative orders timed
by forcing them through the cost search (an experiment-only hook, not
committed: the search's own costs of each step were printed beside the
times). Warm, three runs each after one discarded, CPUs 0-3.

**What PostgreSQL does.** `set_baserel_size_estimates` (costsize.c) puts
every restriction clause of a base relation into its row estimate before
`standard_join_search` (allpaths.c, DP by levels in joinrels.c; GEQO only
from 12 relations) sees it; `clauselist_selectivity` (clausesel.c)
multiplies the clauses' selectivities, ranges paired into one
(`addRangeClause`). An index path's rows per loop
(`genericcostestimate`, selfuncs.c) count every index clause, the
equality on the outer value and a constant range on the next column
together. A LIKE without a usable histogram is `patternsel`'s heuristic
(like_support.c: a fixed prefix `DEFAULT_MATCH_SEL` 0.005, then 1/5 a
fixed character, 0.9 a `_`, 5 a `%`, held to 0.0001..0.9999).
Equivalence classes (equivclass.c) give one join clause per class for
each join (`generate_join_implied_equalities`), never two keys for one
class. Join sizes are `calc_joinrel_size_estimate` with `eqjoinsel`'s
1/max(nd1, nd2) per clause, independently multiplied: PostgreSQL's own q9
estimate of lineitem joined on (partkey, suppkey) is 73 rows against
319,404 (it has no multi-column distinct count here either).

PostgreSQL's plans for the target queries are mostly bushy: q5 and q8
hash the region's customers (region, nation, customer by
`customer_nation`: 30k rows) and probe that hash with the orders; q7 hashes
supplier joined to its two nations. lexdb's search is left-deep only.

**Where lexdb's time goes.** The profiles of q3, q5, q7, q8 and q10 put
75-90% of the time in `tryRow`, the row path: the batch join
(`bJoinPlan`) runs a join only when every table after the first is a hash
or a lookup by the whole primary key, and its conditions compile. q5, q3
and q10 have a primary-key range lookup on lineitem (by `l_orderkey`),
q8 and q9 an index lookup: the whole query then runs row by row, a hash
probe included. q7's plan is all hashes and primary-key points, but its
cross-table OR (`(n1.n_name = .. and n2.n_name = ..) or ..`) at `nation
n2` does not compile for the batch join (`bJoinPlan`'s condition
`bCompile` returns None; unlike `bLevelPlan` it has no `bGenOf`
fallback), so its 1.83M lineitem rows go through supplier and nation
probes on the row path (about 2 us a row) and the date condition is
checked again per row (`allTrueC`, 18% of q7). That is `exec`'s area and
the largest single cause in q7.

The cost model is calibrated on batched work (a scan row of one integer
column 12 ns, a probe 24 ns); measured on lineitem warm: `count(*)` 10
ns a row, one integer column 22, four 53, four with a two-sided date
range 88, and a batched hash probe on supplier about 150 ns; the row path
is 1-2 us a row a level. The model is right in direction for batched
plans (q9: estimated 2.1 s, ran 4.7 s) and 4-12x low for row-path plans
(q7: 0.39 s estimated, 4.8 s ran), so the order search underrates a plan
that pushes millions of rows through the row path.

**Forced orders** (cost mode, warm median of three, ms):

| query | chosen order | ms | forced order | ms |
|---|---|---:|---|---:|
| q7 | lineitem, supplier(h), n1(h), orders, customer, n2(h) | 4,805 | n2, customer (`customer_nation`), orders (`orders_cust_date`), lineitem (pk range), supplier(h), n1(h) | 1,501 |
| q5 | orders, customer(h), nation(h), region(h), lineitem, supplier(h) | 1,735 | region, nation(h), customer (`customer_nation`), orders (`orders_cust_date` + date range), lineitem, supplier(h) | 750 |
| q9 | lineitem, part(h), partsupp, supplier, orders, nation(h) | 4,729 | part, partsupp (pk range), lineitem (`lineitem_part_supp`), supplier, orders, nation(h) | 4,174 |
| q10 | customer, orders(h), nation(h), lineitem | 1,614 | orders, customer, nation(h), lineitem | 1,343 |

The model priced q7's forced order at 36.7M against the chosen 32.5M and
q5's at 30.8M against 25.3M: both wrong in direction.

**Fixed (kept):**

1. *A lookup's range after its equalities.* `wayInto` applied a constant
   range on the column after the equalities only to a table read by its
   constants, never to a lookup per row. q5's `orders_cust_date` lookup
   (`o_custkey =` then the year's `o_orderdate` range) was priced at 16
   rows a customer; it reads 1.5. Now the range's share (from the
   samples of `orders_date`, which leads with the column) narrows the
   lookup's rows too. q5 now starts from customer, its nation and region
   (30k customers), then `orders_cust_date` with the date range; q3
   starts from the BUILDING customers and reads their orders through the
   same index and range.
2. *One equality per class into a table* (`oneEqPerClass`): q5's supplier
   was hashed on `(s_suppkey, s_nationkey, s_nationkey)`; the implied
   `n_nationkey = s_nationkey` is dropped where `c_nationkey =
   s_nationkey` already joins the class and `c_nationkey = n_nationkey`
   was applied at an earlier table. Two columns of the same earlier table
   both stay. Only an equality whose two columns are both in the class and
   of one integer type, or both dates, is left out or stands for another
   (`plainEqCols`). The first version checked only the later table's
   column: the classes leave out equalities across types (int = numeric,
   int = float8, date = timestamp), so such an equality was dropped though
   nothing implied it, and gave wrong counts (120 for 4; 5,000 for 0 as a
   hash). A review found this before the merge; `exec_joinest` now checks
   those shapes. Texts (char(n) padding, collations) and floats (NaN, -0)
   are kept as written, so the rewrite never relies on an equality that
   might not be transitive.
   With the fix the 22 plans are unchanged from the first version, every
   checksum matches, and q3/q5 measured again (baseline, branch, baseline
   in one session, a busier machine: load 4-6) were 2,910 / 2,422 / 2,956
   and 1,899 / 1,071 / 1,976 ms.

`tests/lexdb/run/exec_joinest.lxl` covers 1 (plan and counts, batches
on and off, against IN formulations); `exec_joincost`'s three-table case
now hashes `mid` on `(sid)` for 2.

**Tried, not kept: LIKE's share.** A LIKE is a flat 1/2 (`andShare`'s
"anything else"), so q9's part by `'%green%'` (10,664 of 200,000) is
estimated at 100,000. PostgreSQL's estimate without a histogram (above;
lexdb keeps no sample of a column no index leads with, so it cannot do
`histogram_selectivity`), floored at one distinct value's share, made it
320: q9 then started from part (part, `lineitem_part_supp` per part,
then primary-key lookups, all on the row path) and was slower in the
same session, 4,383 -> 4,651 ms (spreads 4,227-4,392 and 4,577-4,719),
though an earlier session had it 4,729 -> 4,588. Only q9's plan changed
of the 22. 320 is as far below the truth (33x) as 100,000 is above it
(9x); the estimate needs the column's values (a sample kept by ANALYZE,
which is an on-disk catalog change) before it is worth taking, and the
part-first plan pays only once index lookups run in batches.

**Measured** (`lexdb-r5`, branch head, against `lexdb-1744ef99`; warm
median of three, with the run's spread; baseline, branch, baseline in one
lock session, ms):

| query | baseline (1st) | branch | baseline (2nd) | plan |
|---|---:|---:|---:|---|
| q3 | 2,573 (2,550-2,602) | **2,076** (2,070-2,094) | 2,696 (2,684-2,714) | customer, orders by `orders_cust_date` + date range, lineitem |
| q5 | 1,737 (1,725-1,740) | **960** (955-963) | 1,786 (1,772-1,792) | customer, nation(h), region(h), orders by `orders_cust_date` + date range, lineitem, supplier(h) on two keys |
| q9 | 4,296 (4,213-4,315) | 4,687 (4,618-4,721) | 4,438 (4,354-4,475) | unchanged |
| q10 | 1,576 (1,543-1,580) | 1,687 (1,665-1,695) | 1,623 (1,600-1,633) | unchanged |

q3 -21%, q5 -45%. q9 and q10 keep the baseline's plans (EXPLAIN of all
22 compared: only q3 and q5 differ); run again branch, baseline,
branch in one session they were q9 4,392 / 4,399 / 4,516 and q10 1,576 /
1,580 / 1,607: the same within the spread.

A full 22-query run of the branch gives every checksum of the baseline
(q1 `0d3d0dc5`, q8 `30016240`, q17 `3f7be248`; the other 19 PostgreSQL's).
That run's times are not a comparison: it overlapped this branch's own
test suite on CPUs 4-7 and every query with an unchanged plan ran 2-20%
slower than the baseline file. The suite passes (174).

**Not done, and why:**
- *q7's order.* The forced order is 3.2x faster, but the model ranks it
  lower: its cost is the 121k lineitem primary-key range lookups, while
  the chosen plan's 6M-row scan and 1.8M probes are priced as batched work
  they do not get (the OR above). Once `exec` lets that condition into
  the batch join, the chosen plan's real cost should drop toward its
  estimate; the right comparison is then measured again. Raising the scan
  and probe constants to the TPC-H measurements (per column read, per
  condition) would flip q7 now but rank plans by a row path that `exec`
  is removing; not done before that.
- *Bushy plans.* PostgreSQL's q5 and q8 hash a joined dimension
  (region-nation-customer); a left-deep search cannot express that. The
  left-deep equivalent (start from region) is q5's forced order above,
  750 ms against the 960 ms now chosen: the model still prefers a scan of
  customer with two row-path probes over five `customer_nation` lookups.
- *Multi-column join selectivity.* q9's partsupp-lineitem join on
  (partkey, suppkey) multiplies 1/200k by 1/10k (estimate 1,200 rows,
  really 319k), as PostgreSQL does. `lineitem_part_supp`'s distinct count
  of its two-column prefix (ANALYZE has it) would give the right size.
- *A row-path aware search.* The batch join applies only when every step
  is a hash or a whole-key lookup; a search that knew which plans run in
  batches (two DPs: batch-only steps at batch costs, any step at row-path
  costs) would choose between them on real costs. The constants for the
  row path need measuring first.

### 4.4 `outer`: join methods for outer joins, grouped aggregation

Branch `perf/outer`. Plans re-taken at `1744ef99` with EXPLAIN ANALYZE
(lexdb) and EXPLAIN (ANALYZE, BUFFERS) (PostgreSQL, one core); timings are
warm medians of three from `run.sh` unless marked as EXPLAIN ANALYZE runs.
`perf` could not open any event on this machine during this work, so the
profiles below are stack samples taken by gdb (the server run under gdb,
stopped by SIGUSR2 every 50 ms, its frame-pointer chain resolved against
the `LXL_NATIVE_MAP` map): 40-100 samples a query, enough for shape, not
for small percentages.

**What the plans show now (the brief's list re-verified).**

- q13 was the brief's case: `left join orders: index orders_cust_date
  range per row (lookups 150000, rows read 1500000)`, on the row path,
  6.25 s. PostgreSQL: `Hash Right Join` (the filtered orders seq scan
  probing a hash of customer's 150k keys), then two HashAggregates, 0.82 s.
- q18's IN is no longer the problem: the subquery is run once and orders
  is looked up for its 57 values (`rows read 57`). The cost is the
  subquery itself: lineitem read whole and grouped into 1.5M groups,
  2.2-2.5 s of q18's 2.45 s. PostgreSQL runs it as a `GroupAggregate`
  over `lineitem_pkey` (input already in l_orderkey order), 1.68 s under
  EXPLAIN ANALYZE, about 1.0 s in the timed run.
- q12 is no longer a lookup problem: the batched IN list left 30,988
  orders lookups (from 6M). Its 1.2 s is the 6M-row lineitem scan and
  filter (PostgreSQL's seq scan alone is 0.49 s): `exec`'s area.
- q3 and q10's aggregation, sort and LIMIT are small. Replacing the
  aggregate with `count(*)` takes q3 from 2.54-2.59 s to 2.36-2.38 s and
  q10 from 1.54 s to 1.17 s; the groups are 11,620 and 37,967 (the
  plans' 314k and 55k were estimates), and sorting them is a few ms, so
  a top-N heap would save nothing measurable (PostgreSQL's `top-N
  heapsort` is on the same 11k/38k rows). Both run on the row path
  because their lineitem level is a primary-key *prefix* range per row,
  which `bJoinPlan` does not run (it gives up on the whole query when any
  level is not a hash or a whole-key lookup; `exec`'s to fix). In q10's
  profile `addToGroup` is 8% and the per-row join path most of the rest.

**1. A LEFT JOIN as a hash right join (q13).** PostgreSQL considers both
sides of a left join: `populate_joinrel_with_paths` (joinrels.c) adds
`(rel1, rel2, JOIN_LEFT)` and `(rel2, rel1, JOIN_RIGHT)`, so the hash can
be built on the preserved side; `nodeHashjoin.c` marks the hashed tuples
that match and returns the unmatched ones after the outer side ends
(`HJ_FILL_INNER_TUPLES`, `ExecScanHashTableForUnmatched`). lexdb kept
FROM's order for outer joins and chose per level between a lookup and a
hash of the nullable side (`outerReadOnce`); hashing orders was over the
64 MB cap, so it looked up.

lexdb now does the same for two tables: `rightCheaper` compares the left
join as `outerReadOnce` chose it (a's scan plus b looked up or hashed)
with b's scan by its own ON conditions, a hash of a, and a probe per b
row, with a's hash counted at the columns the statement uses. When
cheaper, `buildQuery` swaps the levels to `b RIGHT JOIN a`: b's own ON
conjuncts filter its scan (its rows that join nothing are dropped either
way), the rest of the ON stays the right join's, WHERE conjuncts on a
alone filter a's rows as they are hashed, other WHERE conjuncts are
checked after the join. Not with subqueries, USING, LATERAL, locking,
volatile functions or an early stop. The batches now run a RIGHT JOIN
level (one per query): the probe notes the rows that joined (`Run.seen`),
`batchGroups` adds the rest after the scans (`bUnmatched`: NULLs for the
tables before, the level's WHERE conjuncts, then the tables after it),
and `batchLevel` leaves them to `runQuery`'s existing row-path loop.
Written RIGHT JOINs take the batches too.

Before the batch support, the swapped plan on the row path was 4.2 s
against the lookups' 5.8 s; the batches are what made it pay. q13
**6254 -> 1289 ms** (spreads 6196-6538 and 1212-1329), the same checksum.
What is left (gdb samples): customer's hash build row by row in
`materialize` (about 20%), the int maps of the probe and the grouping
(15%). `exec_rightjoin` covers nine shapes with batches off, on, and an
independent formulation.

**2. Grouped aggregation over many groups (q18).** The subquery's samples
before: per group a full-width first row (`bRow`: 16 `Val`s copied for
lineitem, 12%; the dup glue of the copies 14%), its accumulators and
their drops (15%), the group map (6.5%), and HAVING evaluated for 1.5M
groups after all were kept (10%); the scan about 20%. Three changes in
`batchGroups`:

- the one table read in primary key order and grouped by the key's first
  column takes each row into the group before it or starts one, with no
  map (PostgreSQL's GroupAggregate over presorted input, `nodeAgg.c`);
  alone it was within the noise;
- a group's first row holds only the columns read after grouping (outputs,
  HAVING, ORDER BY), kept compactly and made whole once;
- a HAVING without volatile functions or subqueries is checked as the
  groups are handed over, so a group it drops is never kept (57 of 1.5M
  on q18); the select checks the kept ones again.

q18's subquery 2.1-2.5 s -> 1.24-1.25 s, q18 2.45-2.53 s -> 1.48-1.55 s
(single-session timings under gdb; the run.sh medians are below). The samples now are
decimal arithmetic of `sum(l_quantity)` (`makeDec`, `arith`: about 30%,
`exec`'s) and the scan.

**3. GROUP BY keys a primary key makes redundant (q10).** PostgreSQL drops
GROUP BY columns of a table whose primary key is grouped
(`remove_useless_groupby_columns`, planmain.c). lexdb now does the same
when it plans the select (the first row of the group still gives their
values); q10 groups by c_custkey and six customer columns, three of them
long texts. On q10 it is not measurable today (the row path's grouping is
8% of the query); it matters once q10's joins run in batches.
`exec_groupkeys` covers these and the sorted grouping with batches off,
on, and an independent formulation.

**Numbers** (`run.sh`, warm median of three, CPUs 0-3, ms). A/B in one
session, the baseline binary then `f9334267`:

| query | baseline | perf/outer | spread (outer) | PG one core |
|---|---:|---:|---:|---:|
| q13 | 5698 | 1119 | 1069-1128 | 818 |
| q18 | 2791 | 1505 | 1493-1506 | 1050 |
| q10 | 1635 | 1547 | 1541-1547 | 625 |
| q12 | 1196 | 1232 | 1221-1237 | 832 |

q10's 5% and q12's 3% are within the noise. A full 22-query run of
`f9334267` (`out-r4all`): every check "ok", q1/q8/q17 at their lexdb
checksums; total 59.7 s against the baseline's 66.0 s, geometric mean
lexdb / PG one core **3.41** (3.77 at the baseline).

**Review fixes.** An independent review found:
- *Early HAVING without GROUP BY gave a row* (f9334267): dropping the one
  implicit group made the select add its empty group and check HAVING on
  no rows (`select count(*) from li having count(*) = 0` gave `0`; also
  correlated scalar, EXISTS and NOT EXISTS subqueries). The early check now
  runs only with grouping keys.
- *The swap could raise 53200 where the lookups succeed* (16e64ad2): the
  hash of a was sized at 32 bytes a text. `rightFits` now sizes it by a's
  stored bytes per row (its tree's pages, long values included, over
  ANALYZE's rows) plus the held row's overhead; an overestimate when the
  statement reads few columns, so a hash that might not fit keeps the
  lookups. It is still an estimate: with stale statistics a chosen hash
  can exceed max_statement_mem at run time and give 53200, as any hash
  join can; there is no run-time fallback to the lookups.
- *An equality with no column of a to hash on was taken as hashable*
  (`c.id + 0 = o.cid` became a loop, 4.2 s against 10 ms): the swap now
  needs a column of a (bare or under its collation's key) equal to a value
  of b's alone.
- *b's ON conjuncts that can fail filtered b's whole scan* (`1 / (o.cid -
  3017)` divided by zero on a row no customer joins): only `cannotFail`
  conjuncts go to b's scan now, as for the OR pushdown; the others stay
  the join's and are evaluated on the joined pairs, as the lookups did.
- *The swap's lock check never fired* (locks are applied after planning):
  the select tells `buildQuery` it will lock (`Scope.locking`), and a
  locking query keeps FROM's join.
After the fixes (A/B in one session, baseline then fixed branch): q13
6324 -> 1088 ms (1032-1090), q18 2891 -> 1550 ms (1508-1557); a full
22-query run (`out-r5all`) has every check "ok" (that run was 10-25%
slower across untouched queries too, q7 and q9 included: the machine's
load, not the change). `exec_rightjoin` and `exec_groupkeys` cover each
case with batches off and on; their results were checked against main's engine (the same test built
on main's `cmd/`). Not ours, found by the same review: FOR UPDATE inside a
FROM subquery with a LEFT JOIN crashes on main (index out of range in
`tryRow`'s `rs.cnt[k]`).

**For other workstreams.** q3 and q10 (and any query with a lineitem
primary-key prefix lookup per row) run their joins and grouping on the
row path because `bJoinPlan` gives up on the whole query when one level
is not a hash or a whole-key lookup (`exec`). q13's remaining time is
the row-by-row hash build (`materialize`) and the int maps; q18's is the
decimal `sum` and the scan (`exec`). q12 is its lineitem scan (`exec`).

**Next steps proposed.** The right-join swap handles two tables; with more
(a LEFT JOIN after inner joins, or several) the same choice belongs in the
join order search as a join method, which needs `joinorder`'s search to
accept outer levels. Sorted grouping could also take the order of an
index read in batches, or a join whose first table is read in key order
(q3 groups by l_orderkey but starts from orders, by o_orderkey). The
early HAVING could skip making the whole first row for dropped groups
entirely when HAVING reads only aggregates.

