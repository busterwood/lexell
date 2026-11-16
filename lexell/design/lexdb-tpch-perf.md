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

### 4.joinorder: the join order and its estimates

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
   both stay.

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
