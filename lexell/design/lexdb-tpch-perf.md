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
