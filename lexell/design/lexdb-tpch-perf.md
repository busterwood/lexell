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

### 4.outer: join methods for outer joins, grouped aggregation

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

