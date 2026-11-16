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
