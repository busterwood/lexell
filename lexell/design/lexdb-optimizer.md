# lexdb: from a rule-based planner toward estimates

Status: research, decisions and a first build, on branch `exp/optimizer` (a
worktree off `lexdb`, 2026-11-11). The first build is the index-to-scan switch
(section 19); nothing else in the planner has changed yet. The decision this
revisits is design/lexdb.md section 0, "No cost-based optimizer for now"
(2026-11-09). Its reason was that D4's indexes and joins were not built yet;
they are built now, so the question is open again. The choices below are the
user's, except where marked as a review suggestion.

Experiments: design/experiments/optimizer_skew.lxl and counts_experiments.lxl
(EXPLAIN ANALYZE row counts only; no timings were taken).

Sections 1 to 7 were written first and walked through with the user; sections 8
to 19 were added as the discussion went on. Where they disagree, the later
section and the decision list below win.

**Decisions so far (user, 2026-11-11):**
- Advanced planning may reorder joins, and even the order in which statements
  run, as long as results are the same.
- Statistics start with manual `ANALYZE` only. Automatic `ANALYZE` is deferred,
  because it is where surprises happen.
- Plans should vary with parameter values where the values matter. The user
  has been bitten by SQL Server reusing one plan for unrepresentative
  parameters (parameter sniffing).
- The first thing to build is the budgeted index-to-scan switch (section 5.1).
- Fixed budget for the first switch; constraint-bound join ordering as a separate
  step after the switch (section 6). After review, the fixed budget was
  replaced by counting the table as well, because a fixed budget made large
  tables slower (section 19). The 1024-entry budget remains for short ranges.
- **Direction (user, 2026-11-11): cost-based, using SQLite's ideas, with
  per-parameter plans, and a fallback to rule-based planning through a SET
  command.** Section 18 has the consequences.

**Built so far (on `exp/optimizer`, rebased onto `lexdb` 9.94 on 2026-11-12):**
the index-to-scan switch (section 19); ANALYZE, the tie-break and `SET
lexdb_planner` (20); the review fixes (21); plans kept per parameter
outcome (22); per-value estimates (23); estimates deciding beyond ties and
primary-key statistics (24); the join order bound by keys (25) and by cost
(26); implied equalities (27); SQLite's N-best search (28); the join-order
review's fixes with filter and range estimates (29); the search to 24
tables (30); the integration with lexdb 9.94 (31); ORDER BY ... LIMIT read
in order (32); the second review's fixes (33); a workload comparison (34);
the fast path for pinned joins (35); the read costs measured and
calibrated (36); ANALYZE's samples, the rest of SQLite's stat4 (37); and
the switch's threshold from the measured costs in the cost mode (38,
uncommitted). Code comments cite these sections as "optimizer N".

## 1. Summary

- The rules are predictable and cheap, but they cannot see data. Two failures
  show up in the planner as it is (section 3): a path is taken on an index
  that matches 99% of the table, and ties between indexes are broken by
  creation order. Joins run in FROM order, and nothing reorders them.
- Both failures are about row counts, and a row count per table plus a
  distinct-value count per index would have avoided each. That is a small
  model, which the 2026-11-09 decision already allowed for.
- Recommendation: keep the rules as the default and as the fallback, add an
  explicit `ANALYZE` that stores row counts and per-index distinct counts,
  and let the planner use those numbers only for choices the rules already
  leave open (which index, and the order of inner joins over at most a few
  tables). With no statistics, the plan is exactly today's. Plans change only
  when the user runs `ANALYZE` or DDL, never because data drifted. That keeps
  the predictability the user asked for, and makes it checkable.
- A full Cascades-style memo or a learned optimizer is not worth it for OLTP
  at this size. The useful outside ideas are SQLite's bounded search, DuckDB's
  robust predicate transfer for later OLAP work, and a run-time switch when an
  estimate turns out to be wrong. Section 5 gives the reasons.
- **Superseded by the decisions above.** The recommendation in the third bullet
  was the starting point. The direction now is: cost-based planning on SQLite's
  ideas, with `stat4`-style samples and plans made per parameter value (as
  SQLite does when STAT4 is enabled, section 17), estimates deciding plans, the
  rule planner kept behind a SET command, and a run-time index-to-scan switch,
  which needs no statistics and is built (section 19).

## 2. What the planner does today

- **Path per table.** `choosePath` (cmd/lexdb_exec.lxl:3670) scores each
  candidate: the primary key and each index, in catalog order. An equality on
  every key column scores 1000 for the primary key, 999 for a unique index.
  Otherwise the score is 2 per equality, plus 1 for a range, plus 1 for a
  filtered index, and an IN list counts as an equality. A candidate replaces
  the best only with a strictly higher score, so the primary key wins a tie,
  then the earliest-created index.
- **No statistics.** `IN_LOOKUP_MAX` has a comment saying "no row counts to
  choose by yet" (cmd/lexdb_exec.lxl:2996). The catalog has no row counts and
  no distinct counts, and `ANALYZE` exists only as `EXPLAIN ANALYZE`.
- **Joins in FROM order.** `planSelect` (cmd/lexdb_exec.lxl:7690) builds the
  levels in the order written. A level's path is looked up per row when its
  values come from the tables before it; otherwise the table is read once and
  hashed. Nothing moves a table earlier, and that is the user's job (design/
  lexdb.md 9.5).
- **Plans are cached** per prepared statement, while the schema is unchanged
  and the plan looked at no parameter's value (`select`,
  cmd/lexdb_exec.lxl:7125). If the planner did look at a value (a filtered
  index's predicate, for example), the plan is made again on every execution.
  So lexdb already plans per parameter value in those cases. A prepared point
  select plans in a few microseconds (design/lexdb.md 9.4), so planning time
  is not the problem. The cost of a wrong plan is.

## 3. What the experiment shows

`design/experiments/optimizer_skew.lxl`, run through the in-memory simulated
disk. Row counts are from EXPLAIN ANALYZE.

| Case | What the rules did | Rows touched | Better choice (by hand) |
|---|---|---|---|
| `ev` (1,000 rows), `kind = 1` (990 rows), index on `kind` | index lookup | 990 read, 990 kept | a scan reads the 1,000 rows once; the index path reads 990 index entries and then looks up 990 rows by primary key, so it does more work for the same result |
| `kind = 1 and uid = 5`, indexes on `kind` and on `uid` (100 values) | `ev_kind` (the tie goes to the first index created) | 990 read, 10 kept | `ev_uid`: about 10 read |
| `big` (1,000) join `small` (10), `small.label = 'g3'`, index on `big.grp`, FROM written big first | scan `big`, 1,000 primary-key lookups into `small` | 1,000 read, 1,000 lookups, 100 joined | start from `small`: 10 read, 1 lookup, 100 read through the index |

The third case is a 10x difference in rows touched, and the planner cannot
see it, because `small.label` has no index and the rules do not estimate
selectivity. The second case is settled by distinct counts: `kind` has 2
values, so about 500 rows per value, and `uid` has 100 values, so about 10
rows per value. The first case is not. Distinct counts give 500 rows for both
`kind = 1` (990 rows) and `kind = 2` (10 rows), so they cannot tell the two
values apart. That needs per-value statistics, or a run-time check (section
5.1). These are hand estimates, not measured results.

## 4. What the literature and systems say

Sources are listed at the end. Items marked "memory" are from memory and were
not checked in this session.

- **System R (Selinger et al. 1979, memory).** Dynamic programming over join
  orders, with a cost model from statistics and "interesting orders". This is
  the baseline any cost-based design is compared with.
- **SQLite's next-generation planner (NGQP, since 3.8.0, 2013).** It searches
  loop orders with a bounded N-best set per level, so planning time stays
  small and the search is not exhaustive. Costs are rough estimates on a log
  scale. Statistics come from `ANALYZE` into `sqlite_stat1`, which the planner
  loads when the schema is read; the documented way to force a reload is
  `ANALYZE sqlite_master`. Statistics are not refreshed when data changes.
  Without statistics SQLite uses fixed defaults (memory: a large nominal table
  size, and a few rows per equality on a non-unique index). The defaults are
  the part that matters for lexdb, and they should be checked in the SQLite
  source before anything is copied.
  Why it fits: it trades the best plan for a fast, bounded choice, which is
  the trade-off the user raised.
- **Cascades and Volcano (Graefe 1993 and 1995, memory).** An extensible memo
  of equivalent expressions with rules and cost. Powerful, but the search
  space and tuning are large. Tian (2025) notes that System R, Volcano,
  Cascades and Starburst still underlie most production optimizers.
- **DPccp (Moerkotte and Neumann 2006, memory).** Dynamic programming over
  connected subgraphs, so no cross products are enumerated. For at most about
  six tables, plain DP over subsets is enough.
- **Robust predicate transfer (DuckDB, SIGMOD 2025).** Bloom filters pass
  predicates along the join graph before the joins run. With a join tree
  chosen by a maximum spanning tree (LargestRoot) and a safety check for
  subjoins (SafeSubjoin), the authors report a worst-to-best execution-time
  ratio of 1.6x across random join orders on acyclic queries, and about 1.5x
  overall gain. Cyclic queries are not covered. This is the most relevant
  result for OLAP, and it is about making join order matter less rather than
  finding the best order.
- **Free Join (Wang, Willsey and Suciu, SIGMOD 2023).** One framework that
  covers both binary joins and worst-case optimal joins, built from a binary
  plan. It matters for many-way joins over cyclic patterns, which is not the
  OLTP case.
- **Learned optimizers.** Bao (SIGMOD 2021) keeps the existing optimizer and
  picks a hint set per query, so it can only steer, and it can regress on
  some queries. Balsa is end-to-end and needs much more training. A
  NeurIPS 2025 ML-for-systems workshop paper (DataSwift) argues for a
  regression-free design that keeps the default plan as a candidate; I did not
  check its results. All of these need training data, a feedback loop, and
  ways to detect regressions, which lexdb does not have.
- **Robust query processing.** A VLDB 2025 retrospective on the Join Order
  Benchmark (Leis et al.; reported in a search summary, not read) finds that
  cardinality errors are the dominant cause of bad plans. The taxonomy in
  arXiv 2502.15181 splits the fixes into robust plans and re-optimization.
  Progressive optimization (POP, Markl et al. 2004, memory) checks an estimate
  at a checkpoint during execution and re-plans if it is far off. The switch in
  section 5.1 is a simpler relative of POP.
- **Industrial view (Tian 2025).** Three trends: a tighter loop between the
  optimizer and execution, optimization across a workload rather than one
  query, and composable optimizers. The second matters less for lexdb.

## 5. Options for lexdb

The order below follows the decisions. Option 5.1 comes first and needs no
statistics. Options 5.2 to 5.4 depend on whether we decide to go cost-based,
which the user has not yet settled (section 7, question 2). Per-value
statistics are the part of that which is deferred.

### 5.1 Budgeted index-to-scan switch (first step)

(Built differently from this first sketch: the count is taken before any row
is read, so no rows need skipping, and the table is counted too. Section 19
has what was built.)

**The idea.** A statement that reads through an index starts with a budget
equal to what a full scan would cost. If the index path uses up the budget, it
stops and a full scan takes over. The scan does not repeat rows the index path
already returned. The result is at most about twice the cost of the better
path, without any statistics (the ski-rental argument; the bound is from the
review in section 9, not checked here).

**Why it can skip exactly the rows already returned.** Each index entry is
keyed by the indexed columns, then the primary key (design/lexdb.md 9.5), and
its key is a byte string that compares in index order. So each row has one
position in index order. The index path returns rows up to some last position.
The switched scan reads the table in primary-key order, computes each row's
index key, and keeps only rows whose key comes after that position. It does
not need to remember which rows it has already returned. Both paths read the
same snapshot inside one transaction, so the rows agree.

**What it gives.**
- Parameter sniffing is handled with one fixed plan and no cache key. A
  `kind = $1` with a common value switches to a scan after its budget. A rare
  value never switches.
- Plans still do not change because data drifted, since nothing is replanned.
  But behaviour now depends on the data read at run time. `EXPLAIN ANALYZE`
  must show when a switch happened, so it can be explained.

**Limits to settle before building.**
- **ORDER BY that the index provides.** The switched scan returns rows in
  primary-key order, which breaks the index order. The first version should
  not switch when the index supplies the ORDER BY. The other option is to sort
  the rest, which is more code.
- **The budget needs the table's size.** The store does not track row counts
  today. A per-table counter updated on every write would be a hot row, and
  design/lexdb.md section 6 already says hot rows cause 40001 aborts. The
  better option is to take the size from `ANALYZE`, which the user has chosen
  as manual. Without `ANALYZE`, use a fixed budget, to be chosen when measured.
- **Scope of the first version.** Start with a single-table scan and the first
  table of a join. A per-row lookup inside a join needs a budget per lookup,
  which is a separate question.
- **Executor work.** This adds code to the scan path (cmd/lexdb_exec.lxl:3891,
  `fetch`, is the place to start). I have not read it closely enough to know
  how hard the resume is.

### 5.2 Stored statistics for the open choices (after 5.1)

`ANALYZE` writes a row count per table and a distinct count per index into the
catalog, in the same transaction machinery as DDL. `choosePath` uses them to
break ties and to compare an index with a scan. Without statistics the answer
is the rule answer. This fixes the `kind`/`uid` tie. It cannot tell `kind = 1`
from `kind = 2`; that would need per-value statistics, which is deferred
(section 7, question 2). Whether this option is a cost-based step at all is
the open decision: see section 7.

### 5.3 Join ordering

- **Constraint-bound order first, with no statistics.** Start from a table
  that a unique-key equality pins to at most one row, then follow unique and
  foreign-key lookups. This covers most OLTP joins, and it never changes with
  the data (review, section 9).
- **Cost-based order later.** For up to 12 inner-join tables (decided, user,
  2026-11-11; the bound matches exact search in DuckDB and ClickHouse, section
  16). The bound is a design limit. It ships only after planning time is measured
  on a point select and on a join of the largest size, and that measurement needs
  approval first (section 8). If the measured planning time is too high for OLTP,
  the bound drops and the constraint-bound rule carries the rest. The search
  itself is dynamic programming over join orders (DPccp, or a bounded N-best
  like SQLite's), using the statistics from 5.2. The cost is rows read through the
  path, plus a primary-key lookup for each index row. The `big`/`small` case
  needs a default selectivity for `small.label`, which the doc does not yet
  specify.
- **Reordering outer joins** is harder and needs its own rules. Until those
  exist, outer joins keep their written order.

### 5.4 Per-parameter plans (only if we go cost-based; deferred)

The user wants plans to fit their parameter values. The review (section 9)
proposes this design, which is not yet checked against the planner. It is
deferred with section 7, question 2:
- **Guarded variants.** A statement keeps at most about four plan variants.
  Each variant is valid while a guard holds, such as "the estimated rows for
  `kind = $1` are above 250". The cache key is the outcomes of the guards, not
  the raw values, so most values reuse a plan.
- **Keys skip statistics.** A full primary-key or unique-key equality never
  reads statistics, so most OLTP point lookups stay on the fast path.
- **Explainable.** `EXPLAIN` names the variant and its guard, for example
  "variant 2 of 3: est(kind=$1)=990 > 250".
- **The risk.** With distinct counts alone, a guard cannot tell values apart,
  and the planner would replan on every execution, as `select` already does
  when a parameter is read (section 2). So this option needs per-value
  statistics first.

### 5.5 Run-time checks beyond the switch (POP-style)

Switching a join to a hash join or a scan when a lookup has read far more
rows than estimated. This is the same idea as 5.1 applied to joins. Defer until
5.1 and 5.3 exist and measurements show where the estimates go wrong.

### 5.6 Predicate transfer, Free Join

Relevant to large OLAP joins, not the OLTP path. Deferred.

### 5.7 Full memo (Cascades) or learned steering

Not recommended for this size and workload. The search space and the feedback
loop cost more than the gain.

**What still holds from the earlier draft.** No automatic `ANALYZE`. No plan
changes on its own because of an `ANALYZE` or DDL that nobody ran. The switch
in 5.1 is the one place where behaviour depends on the data at run time, and
the doc should say so plainly.

## 6. Recommended order

1. **Visibility first, no behaviour change.** Turn `optimizer_skew.lxl` into a
   conformance test with its current output as the expectation, so later
   changes in plans are seen. (Its current output is the baseline.)
2. **The budgeted switch (5.1).** First on single-table scans with no ORDER BY
   that the index supplies, with a fixed budget. Decided (user, 2026-11-11): a
   fixed budget for the first version. Table size from `ANALYZE` comes later,
   once measurements show whether it is needed. Test: the `ev` cases, and a
   check that results match a full scan. Measure the switch on the existing
   tests before anything else.
3. **Stage A (5.2), gated by the cost-based decision.** `ANALYZE [table]`
   stores row counts and distinct counts. `choosePath` uses them for ties.
   Test: the `ev` tie case, and that without `ANALYZE` every existing `exec_*`
   expectation is unchanged. This waits until we decide whether to go
   cost-based (section 7).
4. **Join ordering (5.3).** The constraint-bound part needs no statistics and
   is not gated, so it can go ahead. Decided (user, 2026-11-11): it goes in as
   a separate step after the switch, so each change can be tested and reverted
   on its own. The cost-based part waits for the same
   decision as step 3, and then the planning cost is measured on a point
   select and on a 4-table join.
5. **Per-parameter variants (5.4)**, only if we decide to go cost-based and
   the per-value question is settled.
6. **Stage C (5.5)**, if measurements show overruns in practice.

No timing run without asking first (the user's rule on benchmarks).

## 7. Open questions for the user

1. **Manual or automatic `ANALYZE`?** Decided (user, 2026-11-11): manual
   first. Automatic is deferred, because it is where surprises happen.
2. **Per-value statistics (most common values)?** Deferred (user,
   2026-11-11): the user is not yet sold on cost-based optimization, and this
   question only matters if we go that way. Open with it: is stage A (distinct
   counts for tie-breaks, section 5.2) itself a step toward cost-based
   optimization? If yes, the cost-based decision comes before stage A.
   Recommendation when it is revisited: distinct counts first, and
   most-common values only after the switch is built and measured.
3. **Reordering inner joins.** Decided (user, 2026-11-11): yes, when the
   result stays the same. Note that row order without `ORDER BY` can change.
4. **How far to go on the test suite.** Decided (user, 2026-11-11): cheap
   experiments now, to test the ideas. A small test suite for those
   experiments. The full conformance suite waits until the direction is
   decided, and the experiment file is not turned into a conformance test
   before then.

## 8. What was not done

- No timings. The user asked to be asked before performance runs. Stage B's
  planning-cost measurement and any before-and-after comparison need that
  approval.
- No code change to the planner. The experiment file is not in the conformance
  suite: it has no `// expect:` lines, so the runner would report it as
  failing. It is in design/experiments/ and is built by hand.
- The uncommitted changes in the main checkout (`lexell/lib/tls.lxl`, the
  untracked `lexell/cmd/lexdb_auth.lxl`) are not in this worktree, because the
  worktree starts from the `lexdb` commit.
- The SQLite default-estimate figures are from memory. Check them against the
  SQLite source before using them.
- The switch's resume logic in the executor has not been read closely enough
  to estimate.

## 9. Review notes (Fable review, 2026-11-11)

A review agent read this doc, the design sections and the code, and returned
these points. Items marked "checked" were read in the code during this
session; the rest are from the review and from memory.

- **Checked: the plan cache.** `select` (cmd/lexdb_exec.lxl:7136) drops the
  plan when the planner read a parameter's value. With distinct counts that
  cannot tell values apart, every such statement would replan on every
  execution.
- **Distinct counts cannot give per-value choices.** Correct; section 3 now
  says so.
- **Stage B's join order rests on a default selectivity** that the doc did not
  state. Section 5.3 now says so.
- **Rows touched is not a cost.** A secondary-index path pays an index entry
  plus a primary-key lookup per row. The cost model in section 5.3 includes it.
- **One `ANALYZE` can flip every plan.** Hence the dry run below.
- **Per-parameter variants** (guard outcomes as the cache key, at most about
  four variants, most-common-value lookups at execution). Section 5.4.
- **Keys skip statistics.** Section 5.4.
- **Budgeted switch (ski rental, at most about twice the optimum).** Section
  5.1. The review also proposed this as the first step, which the user chose.
- **Constraint-bound join ordering before any statistics.** Section 5.3.
- **Dry run for `ANALYZE`.** Before new statistics are installed, list which
  prepared plans would change, by plan fingerprint. Not yet in the plan; it
  should be added to the `ANALYZE` design in stage A.
- **Prior art (from memory).** SQL Server 2022 parameter-sensitive plans
  (a dispatcher with about three buckets), Oracle adaptive cursor sharing, and
  Graefe and Ward's choose-plan operators.
- **Other fields, from memory.** Inline caches and deoptimization in JIT
  compilers (monomorphic, polymorphic, megamorphic maps onto guarded variants);
  profile-guided optimization (statistics as an exportable, reviewable file,
  so production plans can be reproduced in tests); branch and bound (the rule
  plan as the starting bound); minimax regret (keys and foreign keys give hard
  bounds); hysteresis (keep the old plan across an `ANALYZE` unless the new
  one wins by a set factor, so plans do not flap at a crossover); queueing
  (OLTP tail latency follows variance, so bounded worst cases matter more than
  the mean); sampling for distinct counts (provably poor, Charikar et al.).
  Bandits do not fit a predictable planner, and integer programming is too
  slow for microsecond planning.
- **Sketch idea.** An index is sorted, so one ordered pass gives exact distinct
  counts, top values and an equi-depth histogram. Sketches such as
  HyperLogLog are needed only for unindexed columns. Not checked.
- **Hysteresis as a rule for `ANALYZE`.** Not in the plan yet. It is a
  candidate for stage A.
- **The biggest worry** (review): per-parameter planning on distinct counts
  alone would replan every time and still not fix parameter sniffing. Section
  7, question 2 is where this gets settled.

## 10. First-principles review (Fable, 2026-11-11, literature set aside)

A second review agent was asked to ignore the literature and reason from this
system: NVMe, concurrent I/O, OLTP shapes (EXISTS, IN, index lookups). Its
scope, honestly: it read the design sections and the planner and scan code
(cmd/lexdb_exec.lxl), and it grepped the store for page counts. It did not
review the B-tree store itself (cmd/lexdb_store.lxl) or the I/O layer. So its
points are about the planner's shapes on this hardware, not a full review of
the B-tree. Its main points:

- **One question per table access:** keep doing separate tree descents, or
  make one pass over the tree. The same question covers an index range versus
  a scan, an IN-subquery lookup per value versus one read, a correlated EXISTS
  probed per outer row versus one hashed read, and a join level looked up per
  outer row versus read once and hashed.
- **Two numbers decide it:** the size of the one pass (leaf pages of the
  target tree), and the number of descents this execution will make. The
  second is unknown at prepare time but observable while running.
- **Per-row fetch is serial.** Checked: the index path calls `st.get` once per
  index entry, in a loop (cmd/lexdb_exec.lxl, about line 3965). Each cold
  fetch parks and wakes in turn, so the device's concurrency goes unused. This
  is a real cost on NVMe and was not in the doc. Batching the gets is a
  candidate for its own step.
- **Read amplification is asymmetric.** Reading an index range is cheap; the
  primary-key fetch behind each entry is the cost.
- **Decided by fixed rules:** a whole primary key or unique index equal is
  always a lookup; order with a LIMIT goes to the index; hash when no index
  serves a correlation.
- **Decided from data at run time:** index versus scan; lookup versus hash for
  IN, EXISTS and join levels; ties between indexes.
- **Proposed mechanism, "count, then commit":**
  - Prepare time: `choosePath` rules unchanged. Each lookup site keeps a
    precomputed alternative (scan or hash build), and tied index candidates are
    both kept. No parameter value is read, so plans stay cacheable.
  - Execution: read index entries only, up to a budget, before fetching rows.
    Within budget, fetch the rows (sorting the keys and issuing the gets
    concurrently if no order is needed). Over budget, scan; nothing has been
    returned yet, so nothing needs skipping. Ordered or LIMIT queries stream and
    use the switch in 5.1.
  - Tied indexes: count each candidate's range up to one batch, and take the
    one that ends first. This is exact for the value given.
  - IN subqueries: compare the number of values with the budget, replacing the
    fixed 1,000 (`IN_LOOKUP_MAX`).
  - Correlated EXISTS and join lookups: count probes. At the budget, build the
    hash once from a scan and probe it for the rest. Probes are stateless, so
    the answers are the same.
  - Budget: the target tree's leaf count times a constant.
- **Checked: the leaf count is not kept.** The store keeps a page count for the
  whole database (cmd/lexdb_store.lxl, `npages`), not a count per tree. So the
  "exact counter" in the proposal needs either a count kept per tree, which
  must be maintained on writes (the hot-row problem in 5.1 again), or the count
  taken from `ANALYZE`, which matches the manual decision. This also answers
  step 2's question in section 6: a fixed budget is the simple first version,
  and the table size comes from `ANALYZE` later.
- **EXPLAIN form proposed:** `index ev_kind, budget 40 pages (ev: 40 leaves),
  else scan`, and with ANALYZE, `counted 990 > 40: scanned`.
- **Where it may be wrong:**
  1. The budget's unit. Pages fit a cold cache. Warm, a short index fetch can
     beat decoding many rows, so one page constant may switch too early. Test:
     extend `optimizer_skew.lxl` to report pages loaded, descents and rows
     decoded for both paths, at several selectivities, cold and warm.
  2. The hash switch for semi-joins. Repeated outer keys make probes cheap
     when pages are cached, while a big inner table makes the hash build costly
     in memory. Test: count the distinct pages missed per probe against the
     repetition of outer keys.
- **Not checked by that review:** whether the store offers batched or concurrent
  gets; per-statement page-miss counters (9.49 suggests they exist); tree depths
  and entries per leaf; where IN values are deduplicated relative to the 1,000
  check.

## 11. Abstract first-principles review (Fable, 2026-11-11, no lexdb detail)

A third agent got a description of the problem only: a declarative request over
sorted collections on a parallel device, with secondary views, a common case
of many small repeated requests, and the requirements of predictability and
explainability. It was told to ignore database literature and the existing
design, and to consider other fields. Its main points:

- **Essential decisions per request:** which sorted structure to enter and over
  what range; whether to follow a view's pointer back to the full record;
  which collection to start from (fewest surviving records first); whether to
  probe the second collection per record or merge both in order; whether to
  read in the requested order or sort; and when an existence or first-N check
  can stop.
- **Minimum information:** the static structure (keys, uniqueness, view fields
  and order, which gives provable bounds such as "at most one record"), the
  request's own shape, coarse size classes per collection declared by the
  operators, and explicit directives. Observed counts are for reporting only.
  This assumes fine value distributions are not needed for the common case.
- **Proposed approach, all at first sight of a request text:** replace values
  with placeholders and compile one plan with a fixed rule list. Prefer the
  smallest provable bound (unique equality, then equality prefix, then range,
  then full read). Among equals, prefer the one that gives the requested order,
  then the one that avoids pointer-chasing. Start from the smallest declared
  collection. Merge only when both sides are large and already ordered. Break
  ties by declaration order. The plan is a pure function of the normalised
  text, the structure version, the rule-set version and the operators'
  directives, so it cannot drift with data.
- **Parameter values** only enter through guards written into the plan (an
  empty list returns nothing; a missing optional value takes a stated branch).
- **Telemetry** (rows touched and returned per step) is kept and shown, and
  never fed back automatically. Advisories such as "touched 10^6 records to
  return 3; alternative X exists" go to the operator.
- **Large requests** get the same rules, labelled "unbounded" at compile time,
  run as partitioned parallel reads with a work budget. Exceeding the budget
  raises a flag and does not switch the plan.
- **Likely failures:** skew, where the structurally best view matches most of a
  collection, or one request text needs different plans for different values
  (test: touched versus returned per plan key, looking for a high or bimodal
  ratio); and wrong starts in large unbounded multi-collection requests, which
  fall back to declared sizes (test: per-step input versus output on the rare
  large requests).

**How this compares with section 5.1.** This design does not switch at run
time, so a plan never depends on the data read. It answers sniffing by
guards and by operator directives, where section 5.1 answers it with a switch
inside the plan. The trade-off is the one the user has to make: a fixed,
diffable plan that can be wrong for some values, against a plan that adapts
within a request. It is worth weighing both against the decision on
per-parameter plans, which is still open (section 7).

## 12. Learning from execution (blue sky, user's idea, 2026-11-11)

**The idea.** Start from the rule-based planner. Each execution returns facts:
rows touched, rows returned, and lookups made, per step and per value. Future
plans use those facts. The user wants this explored as blue sky.

**Why it is cheap to collect.** The executor already counts these things for
EXPLAIN ANALYZE: rows read, kept and joined per level, and lookups or probes
(cmd/lexdb_exec.lxl, `explainLines`). Collecting them for every execution is
plumbing, not new measurement.

**What it fixes that nothing else here does.** It gives per-value facts with no
`ANALYZE`. The `kind = 1` case becomes "this value matches 99% of rows". The
distinct-count problem in section 3 goes away. Facts are gathered from the
queries actually run, so the statistics match the workload.

**Where it conflicts with decisions already made.** It is automatic learning,
which the user deferred on 2026-11-11 because automatic `ANALYZE` is "where
people get surprised". So the design needs an explicit gate between learning
and acting.

**A design that keeps the gate.**
1. **Collect always, act only when asked.** Facts go into a feedback store,
   keyed by the statement's plan fingerprint, the step, and a value class. They
   are never used to change a plan by themselves.
2. **Adopt by hand.** An `ADOPT` step, like `ANALYZE`, shows which prepared
   plans would change and why (the review's dry run, section 9), and applies
   only the changes the operator accepts.
3. **Adapt among fixed variants, not by replanning.** Each statement has a
   small, enumerable set of plan variants, each guarded by a visible test on
   the observed facts. A variant is chosen by the guard, so every possible plan
   can be listed and tested. This is the guarded-variant design of section 5.4,
   with the facts coming from execution instead of from a statistics pass.
4. **Hysteresis.** A change needs enough observations, and an improvement
   larger than a set factor, before it is proposed. This stops plans flapping
   near a boundary.

**The costs and risks to weigh.**
- **Plans would depend on history.** After a restart the feedback is gone unless
  it is persisted. Persisting it means writing it with the checkpoint, and
  without that a restart changes plans. That undermines reproducibility, so the
  store should be persisted and included in backups.
- **Writes to the feedback store must not conflict.** Counters in the catalog
  would be hot rows, the problem in section 5.1. Keeping them in memory per
  process avoids that, but only until a restart, which is the previous point.
- **A cold start is no worse than today**, because the rules plan runs until
  there are facts. But a workload that changes shape gives stale facts, so they
  need ageing or a decay.
- **Feedback can learn the wrong thing from unrepresentative runs.** That is
  parameter sniffing again, now learned. The fixed-variant design limits the
  damage, because a bad observation can only pick a variant that already exists.
- **Operators must be able to read it.** A change log, the facts behind each
  change, and a way to pin a plan.

**Open question for the user.** Should the facts be persisted, and should
adoption stay manual? My recommendation is yes to both: always collect,
persist with the checkpoint, and adopt by an explicit `ADOPT` after a dry run.
That gives the adaptive behaviour you want without the surprise of an
automatic change.

**Addendum (user, 2026-11-11): adapt only to a provably better plan.** The
user's principle is that adapting to a plan that is provably better is
acceptable, and adapting to a worse one is not. Learned facts are estimates,
so they cannot prove anything about the next execution. Two things follow.

- **Make the decision per execution, from exact counts, not from history.**
  For an access-path choice, the candidates can be counted for this value,
  up to a budget, before any row is returned (the count-then-commit design of
  section 10). The candidate with fewer entries to visit is then the better
  one for this execution, and that is provable, given the work measure. The
  price is bounded: the counting costs at most the budget on the candidate
  that loses.
- **History only proposes.** Facts from execution can order the candidates
  and set the budgets, and they can say which plans are worth trying. They
  never make the choice. So history cannot pick a worse plan than the rules
  would, because the choice is made from exact counts every time.

The principle has two limits to state plainly:
1. **It needs an agreed work measure.** Entries visited and rows fetched can be
   counted. Time cannot be, and a fetch costs more than an entry. So "provably
   better" means better on the measure we define, for example entries plus
   fetches weighted by a constant. That choice is the user's.
2. **It covers access paths, not join order.** A join order can't be counted
   for every alternative without running them. Join reordering stays a
   question, and under this principle it can only change when the order's cost
   is provable from exact counts (for example, a unique key pins one side).

Under this rule plans change for three reasons only: a deliberate `ADOPT`, a
structure change, or a per-execution count that picks a different access path
for this value. The last is not a plan change in the sense the operator sees,
since the plan is the same and only the chosen access differs.

## 13. System R, read again with a critical eye (2026-11-11)

The user asked whether System R's trade-offs were made for slow disks, and
whether they still hold on NVMe. The paper (Selinger et al., SIGMOD 1979, pages
23 to 34) is scanned, so the fetch returned no text. I read the scanned pages
directly. Quotations are from the paper.

**What the paper says, in its own terms**
- **Cost unit.** "COST = PAGE FETCHES + W * (RSI CALLS)", where W is "an
  adjustable weighting factor between I/O and CPU". The paper gives no numeric
  W in the text I read. RSI calls stand in for CPU: "most of System R's CPU
  time is spent in the RSS".
- **Buffer assumption.** For a non-clustered index on a relation too big for the
  buffer, the paper assumes "a page fetch is required for every tuple
  retrieval". That is the worst case, and it penalises index lookups.
- **Statistics are not maintained on writes.** "System R does not update these
  statistics at every INSERT, DELETE, or UPDATE ... Dynamic updating of
  statistics would tend to serialize accesses that modify the relation
  contents." They are refreshed by a user command, UPDATE STATISTICS.
- **Defaults with no statistics.** Equality with no index has selectivity 1/10,
  and a range has 1/3. The paper says: "a lack of statistics implies that the
  relation is small, so an arbitrary factor is chosen."
- **Uniformity and independence.** Equality with an index is 1/ICARD, which
  assumes an even spread of values. Conjuncts multiply, which assumes the
  columns are independent.
- **Search.** Left-deep joins with interesting orders kept; at most 2^n times
  the number of interesting orders of solutions stored. "Joins of 8 tables have
  been optimized in a few seconds" on a 370/158.
- **Join methods.** Nested loops and merge scan only. Citing Blasgen and Eswaran
  (1976): "for other than very small relations, one of two join methods were
  always optimal or near optimal".
- **Amortisation.** "The cost of optimization is approximately equivalent to
  between 5 and 20 database retrievals", justified because "application programs
  are compiled once and run many times".
- **Accuracy.** "The costs predicted ... are often not accurate in absolute
  value, [but] the true optimal path is selected in a large majority of cases.
  In many cases, the ordering among the estimated costs for all paths considered
  is precisely the same as that among the actual measured costs."

**Which choices were made for slow disks**
1. **The unit is page fetches, with CPU as a weight.** In 1979 a page fetch cost
   milliseconds and an RSI call a small fraction of that. Now a fetch from
   NVMe, or from cache, is far cheaper relative to CPU work. So the balance the
   formula assumes has moved. This is the strongest case for your suspicion.
2. **The worst-case buffer assumption.** It makes an index lookup cost one page
   fetch per row. That pushes the index-versus-scan crossover towards a few per
   cent of the table. On fast random reads the crossover should move a long way
   towards index use. Our skew experiment (990 of 1,000 rows) is far past both
   points, so it does not test this. A crossover measurement would.
3. **Small-relation defaults.** "A lack of statistics implies that the relation
   is small" was a reasonable guess then. Here it is backwards: most tables a
   database meets without statistics are large. Our no-statistics fallback
   should not inherit this default.
4. **The search budget.** Pruning was driven by CPU: 8 tables took seconds. A
   CPU-cheap planner now has room for a far larger search. The bounded search
   in SQLite and our stage B were chosen for planning speed in OLTP, not because
   the paper's budget is the limit.
5. **Join methods.** The set (nested loops and merge) came from 1976 evidence.
   In-memory hash joins are cheap now, so a method set limited to nested loops
   and merge would be wrong today. Our planner already uses hashing when no
   index helps, so this point is already on our side.

**Which choices were not about disks, and still hold**
- **Statistics are not updated on writes.** The paper's reason is contention
  on the catalog, not disk speed. My first reading of it for lexdb was wrong:
  I said writes are serialized, so a counter would contend. Writes do run one
  at a time on one thread (design/lexdb.md section 1), but transactions can
  overlap across the I/O parks. Commit validates the leaf versions each
  transaction read (lexdb.md, around line 74), so two overlapping writers that
  both touch a per-table counter would abort one with 40001. The cost is
  aborts and retries, not waiting. A counter read inside a serializable
  transaction also becomes part of its read set, so the planner would make
  transactions depend on it. Keeping statistics as a versioned catalog object
  that only `ANALYZE` changes avoids both problems, and it supports the manual
  `ANALYZE` decision.
- **Uniformity and independence** are data assumptions, not hardware ones. They
  are still wrong for skewed columns, and our experiment shows it.
- **Relative ranking is what matters.** The paper's accuracy claim is that the
  ordering of costs is usually right even when absolute costs are not. That is a
  testable claim for us, and it is cheap to test with counts: does the rule
  plan's ordering of candidates match the counts?
- **Amortisation.** Planning cost is spread over many executions of a prepared
  statement. That still holds for OLTP, but the budget has shrunk: a point
  select now runs in microseconds, so planning has to be microseconds too.

**What the paper does not model, which matters now**
- **Concurrency.** Costs are additive, sequential page fetches. With many
  requests sharing an NVMe queue, the cost of one request depends on the load,
  and the formula has no term for that. This is a gap in the paper, not a
  change in the hardware.
- **Parallel I/O.** Nothing models several fetches in flight at once. Our
  serial fetch loop (section 10) is the same assumption in code.

**Summary of the critique.** Your suspicion is right for the cost unit, the
buffer assumption, the no-statistics default and the join-method set. It is
wrong, or at least not disk-driven, for the statistics-on-write decision, the
uniformity assumptions and the amortisation idea. And the paper omits
concurrency, which is the biggest change on your hardware. The cheapest
checks are: the crossover between index and scan on this device, the
relative-ranking claim using counts, and whether the no-statistics default
should assume a large table.

## 14. Probabilistic data structures (2026-11-11)

These are the structures the user asked about. The useful test for each is
whether it can ever make a wrong answer, or whether it only gives hints. That
matches the principle the user set: adapt only to a provably better plan.

**Filters: one-sided, so answers stay exact.**
- **Bloom or cuckoo filters over an index's keys.** A "no" from the filter is
  certain. A "yes" may be false, and then the lookup runs anyway. A false
  positive costs one descent and never a wrong result. Around 10 bits per key
  gives about 1% false positives.
- **Where they help:** `EXISTS`, `NOT EXISTS`, `IN` and anti-joins whose keys
  are mostly absent. The filter can skip the descent and the leaf read. The gain
  is only large if most probes miss, so the first thing to measure is the miss
  ratio of probes, from counts.
- **Semi-join reduction.** Build a filter over the inner side's join keys during
  its scan, then check it before each outer lookup. This is the mechanism behind
  DuckDB's predicate transfer (section 4). It fits the count-then-commit design
  in section 10, because the filter is built before the probes start.
- **Costs:** a filter must be kept in step with writes. Bloom filters cannot
  delete, so deletes need a counting variant or a cuckoo filter, or a rebuild
  at checkpoint. Memory is the trade: it is a fixed amount per index.

**Estimators: hints only, never proofs.**
- **HyperLogLog** gives distinct counts in a few kilobytes and merges across
  partitions. For indexed columns an ordered pass gives the exact count, so it
  is needed only for unindexed columns during `ANALYZE`.
- **Count-min sketch, SpaceSaving and Misra-Gries** find heavy hitters, which
  is the most-common-values question deferred in section 7. For indexed columns
  one ordered pass gives exact top values. Sketches matter for unindexed ones.
- **KLL or t-digest** give quantiles for range selectivity. Again, only for
  unindexed columns with range predicates.
- **Sampling** is cheap on huge tables, but it is known to be poor for distinct
  counts (review, section 9).
- Their error is a statistical bound, not a guarantee for one query. So they can
  only feed a plan proposal that is then checked by exact counts. That is how
  the principle keeps them out of the final choice.

**A budget does not need exact numbers.** An approximate table size, from a
counter or a sketch, is enough for the switch budget in section 5.1. A bad size
changes only where the switch happens, not the answer.

**Where it does not help.** Filters do not help when most probes hit, which is
the common OLTP case with a foreign-key lookup. Sketches do not help when the
index already gives exact counts, which is the case for indexed columns.

**Cheapest test (counts only, no timing).** Over a recorded workload, count the
fraction of index probes that return no row. If that fraction is high, a filter
is worth building. If it is low, filters will not pay, whatever their memory
cost.

## 15. Count experiments, results (2026-11-11)

File: design/experiments/counts_experiments.lxl (counts only, no timings). Its
output came from a binary built in the scratchpad. The three questions and
what the counts say:

**A. Ranking: does the rule choice match the cheapest path?** Table of 10,000
rows: `a = id % 2` (50%), `b = id % 100` (1%), `c = id % 10000` (values unique
in the data, but not declared unique). Indexes on `a`, `b`, `c`, in that order.

| Query | Rule chose | Rows read (fetches) | Alternative | Rows read |
|---|---|---|---|---|
| `a = 1 and b = 5` | `t_a` (tie, first created) | 5,000 (kept 100) | `t_b` | 100 |
| `a = 1 and c = 7` | `t_a` (tie) | 5,000 | `t_c` | 1 |
| `b = 5 and c = 7` | `t_b` (tie) | 100 (kept 0) | `t_c` | 1 |

Each rule choice read 50 to 5,000 times more rows than the alternative it
passed over. The cause is that the rules see only key shape, and a tie goes to
the first index created. With `c` declared `UNIQUE` (table `u`), the rules
pick `u_c` correctly. So the rules are right only when uniqueness is declared.
This is not a test of the paper's ranking claim (section 13): that claim is
about a cost model's estimates, and the rules make no estimates. It shows that
the rules' order of preference often picks the worst candidate.

**B. Miss ratio: how often does a probe find no row?** One probe per order row,
into `cust` by primary key:
- FK-like workload (90% of orders match): 10,000 lookups, 9,000 joined, so a
  10% miss ratio. A filter would skip at most 1,000 descents.
- Anti-join-like workload (10% match): 10,000 lookups, 1,000 joined, so a 90%
  miss ratio. A filter would skip up to 9,000 descents.

So the filter idea from section 14 pays only in the second workload. The first
measurement to make is the miss ratio of the real workload.

**C. Crossover in counts: index range versus full scan.** `kind = id % 100`,
range `kind < f`:

| f | Index rows read (kept) | Scan rows read |
|---|---|---|
| 1% | 200 (100) | 10,000 |
| 10% | 1,100 (1,000) | 10,000 |
| 50% | 5,100 (5,000) | 10,000 |
| 90% | 9,100 (9,000) | 10,000 |
| 99% | 10,000 (9,900) | 10,000 |

On rows read alone, the index path only ties the scan near 99%. But every
index entry also costs a row fetch, so the index path's work is about twice its
rows read. On that measure the crossover is near 50%. That is still a count
model: whether a random fetch costs more or less than a sequential scan row on
this device needs a timing run, which is on hold until approved.

**A finding from C.** The range `kind < 1` reads 200 rows to keep 100. The
upper bound is inclusive (section 9.5), so the rows with `kind = 1` are fetched
and then rejected. That costs one extra value's fetches on every upper-bounded
range, and at 1% it doubles the reads. For an integer column with an exact
bound, an exclusive end would avoid it. That is a candidate fix, separate from
the switch.

**What this changes in the doc.** Section 3's claim that distinct counts would
settle the `kind`/`uid` tie still holds only with declared uniqueness or
distinct counts. Section 14's filter idea is worth measuring on the real
workload first. Section 13's crossover worry is now a count-level fact: the
index path does roughly twice the fetches, so the device crossover sits well
below the rows-read figure.

## 16. Other engines: DuckDB, ClickHouse, MonetDB, SQLite (2026-11-11)

Read from the official docs by a web-fetch agent. DuckDB pages were the 2.0
versions (the `current` and `stable` URLs redirect there). The MonetDB blog is
dated 2022. Items not on the pages read are marked.

**DuckDB (cost-based, with statistics)**
- Join order: exact dynamic programming below `approximate_join_order_threshold`
  tables (default 12); a greedy algorithm at or above it. Exact search falls
  back to greedy if it exceeds an internal budget.
- Statistics: base-table statistics estimate cardinality. How they are gathered
  and refreshed: not on the pages read.
- Cost: cardinality estimates, with heuristics per operator. Whether work is
  costed: not on the page.
- Control: `disabled_optimizers = 'join_order,build_side_probe_side'` gives a
  left-deep tree in FROM order.
- Runtime: dynamic filters are pushed into scans at run time by the hash join.
  This is a one-sided filter that keeps answers exact, the same kind as the
  filters in section 14.
- Prepared statements save planning mostly for queries under 100 ms.

**ClickHouse (cost-based where it has statistics, otherwise primary-index estimates)**
- Join order: an algorithm list, default `dpsub,greedy`. `dpsub` is exact for at
  most 12 relations; `dphyp` and `dpsize` are other options. At most 10 tables are
  reordered by default (`query_plan_optimize_join_order_limit`).
- Join sides: since 24.12, the smaller estimated input becomes the hash build
  side.
- Filter pushdown: single-input conditions move below the join, with exceptions
  for the outer sides of outer joins.
- Statistics: `use_statistics` (default on) and `materialize_statistics_on_insert`
  (default on, built for new parts). Without statistics, estimates come from the
  primary index and "can be imprecise". An ANALYZE-style command: not on the
  pages read.
- Runtime: `join_algorithm=auto` starts with a hash join and switches to another
  algorithm when the memory limit is exceeded, and grace hash takes over past the
  spill threshold. The choice of algorithm is a priority list, not a cost
  comparison (the page does not describe a cost-based hash-versus-merge choice).
  TopK uses dynamic thresholds.

**MonetDB (rule-based, no statistics)**
- The blog says the optimizers "do not rely on any cost-model or pre-computed
  statistics". Join order is listed among its rewriting rules. The algorithm is
  not described on the page.
- The MAL optimizer pipeline rewrites the program "iteratively" until there are
  no more opportunities or the rewriting quota runs out.
- Sizes are estimated inside operators at run time, sometimes from a sample.
- Algorithms are chosen when the operator runs, from the properties of its
  inputs (sorted, key, dense). The design overview says choosing an algorithm
  "can best be postponed until you need the results and have knowledge on the
  properties of its arguments." This is the closest published analogue to our
  index-order decisions at execution.
- Many MAL optimizers are marked "under consideration", so the list is not the
  default pipeline.
- Inspection: `PLAN` shows the logical plan; `EXPLAIN` shows the optimised MAL
  plan.

**SQLite (cost-based with statistics; bounded search)**
- Search: N-nearest-neighbours (N3). It keeps the N best partial plans at each
  step, with N around 1, 5, 10, and later 12 or 18 for star schemas. The cost is
  O(K·N) against K! for exhaustive search. The page calls costs "logarithmic"
  units.
- Defaults without statistics: about 10 duplicates per value in the leading
  column, and, per the summary of the optimizer overview, a guess of one million
  rows.
- Statistics: `sqlite_stat1` holds row counts and rows per equal prefix.
  `sqlite_stat4` (a compile option) holds samples, typically 10 to 40 per index,
  and "is not hard bounds".
- Refresh: not automatic. The planner reads the statistics when the schema is
  read, so new statistics reach only connections opened after the ANALYZE.
  `PRAGMA optimize` runs ANALYZE as needed.
- Stability: an off-by-default Query Planner Stability Guarantee keeps plans
  fixed until the schema changes, ANALYZE is rerun, or the SQLite version changes.
- Warning on the ANALYZE page: "One can construct pathological cases where
  running ANALYZE could make some subsequent queries run slower."
- Planning time: the polynomial algorithm plans "50- or 60-way joins in a matter
  of microseconds".

**What the four engines say, for lexdb**
1. **Exact join search goes to 12 tables, not 5 or 6 (decided, 2026-11-11).** DuckDB and
   ClickHouse both use exact dynamic programming up to 12, with a cap on how many
   tables are reordered. Our stage B bound was conservative. For OLTP, though,
   the planning budget is far smaller than for analytics, so the bound should be
   set by measured planning time.
2. **Statistics are optional everywhere.** Each engine has a sensible behaviour
   without them: MonetDB never uses them, SQLite guesses one million rows,
   ClickHouse falls back to primary-index estimates. Our rules-only fallback is in
   the same family.
3. **Two engines decide some things at run time, with fixed triggers.**
   ClickHouse switches join algorithm on a memory limit, and DuckDB pushes
   dynamic filters into scans. MonetDB picks the algorithm from the operator's
   input properties during execution. None of these changes a query's plan
   shape; each is a local decision with a fixed rule. That matches the principle
   in section 12, but only the one-sided filter cases keep answers exact by
   construction.
4. **SQLite's stability guarantee and warning match our decisions.** Plans fixed
   unless DDL, ANALYZE or the version changes, and an explicit warning that
   ANALYZE can make some queries slower. That supports manual ANALYZE and the
   dry run in section 9.
5. **Every engine exposes a knob to disable or limit reordering.** We should
   have the same, so that a plan can be pinned when it is wrong.

## 17. Adopting SQLite's planner as the model (user's direction, 2026-11-11)

The user's view: SQLite's planner is the sensible approach. This section says
what that adoption means for lexdb, and which decisions it forces.

**Why the fit is good.** lexdb and SQLite have the same shape. Both run nested
loops over B-trees, index lookups per row, a single-writer commit path, and an
OLTP workload with prepared statements. SQLite's planner was designed for that
shape, not for hash-join analytics.

**What we would take.**
1. **A bounded N-best search over loop orders.** Keep the best N partial plans
   at each step. Planning time is polynomial, which SQLite reports as
   microseconds for 50- to 60-way joins. This replaces the exact search for 12
   tables, so the 12-table decision in section 5.3 becomes a limit on the search
   width, not on exactness.
2. **Costs as estimated work.** Rows through the path plus a lookup per index
   row, in log-scale units as SQLite does.
3. **Statistics from manual `ANALYZE`, in SQLite's form.** A row count and rows
   per equal prefix per index (the `sqlite_stat1` shape), read when the schema is
   read. Samples (the `stat4` shape) later, if needed.
4. **A large default when there are no statistics.** SQLite assumes about one
   million rows, which is the right direction. Section 13 warned against the
   paper's "small relation" default, and this avoids it.
5. **A stability guarantee on by default.** A plan changes only when the schema
   changes, `ANALYZE` is rerun, or the engine version changes. That is the
   predictability the user asked for, written down as a rule.
6. **The ANALYZE warning as a dry run.** SQLite's own page warns that ANALYZE can
   slow some queries. Section 9's dry run answers that warning.

**How SQLite treats parameter values (corrected after review).** An earlier
version of this section said SQLite plans a `?` as an unknown value and keeps
one plan per statement. That is wrong when STAT4 is enabled. A statement
prepared with `sqlite3_prepare_v2` is recompiled, as if the schema had changed,
on the first step after a binding changes, when the value might affect the
plan: a parameter compared with an indexed column (with STAT4), or the left
side of LIKE or GLOB. SQLite's forum notes that this can break its own plan
stability guarantee. Without STAT4 the value is not looked at. So SQLite with
STAT4 already plans per parameter value, and the user's choice in section 18
follows SQLite rather than departing from it. Sources: the SQLite prepare
requirements matrix (https://www2.sqlite.org/matrix/matrix_dprepare.html), the
forum post (https://sqlite.org/forum/forumpost/1df053250dbd2524), and SQLite's
analyze3.test.

**What SQLite does not do, which we would have to decide.**
- **It replans, it does not keep variants.** SQLite recompiles on a binding
  change and keeps one plan at a time. Section 5.4's guarded variants would keep
  several, so a value that comes back does not replan.
- **No run-time adaptation.** The switch in 5.1 is our addition on top.
- **No histograms without the stat4 option.** So range estimates are coarse
  until stat4 exists.

**A possible addition SQLite does not use: transient indexes.** From memory (not
on the pages read): SQLite can build a temporary index for a join with no usable
index, rather than hashing. For lexdb the question is whether a transient B-tree
beats a hash build when the probe side repeats keys. That is a candidate for
the experiment list, counted, not timed.

**Decisions this forces, for the user.**
1. **Search width.** Exact search to 12 tables, or N-best with a width such as
   10 for three or more tables, as SQLite does? SQLite's choice is the one the
   user's direction points to.
2. **Parameter-dependent plans.** Generic plan per statement, with the switch
   handling value-dependent cases, or plans per value? (As first written, this
   said a generic plan was SQLite's answer. With STAT4, SQLite's answer is a plan
   per value: see the correction above. The user chose per-value plans, section
   18.)
3. **Whether to add a cost-based step at all.** SQLite's model is cost-based
   with statistics. Section 7's deferred question is now the central one: adopting
   SQLite's planner means going cost-based, so stage A and stage B follow from
   that decision.

## 18. Decision record: cost-based, SQLite's ideas, per-parameter plans (2026-11-11)

**Decided (user).**
- Cost-based planning, using SQLite's ideas: bounded search, costs as estimated
  work, manual `ANALYZE`, a large default when statistics are missing, and the
  stability rule.
- Plans are made per parameter value where the values matter. This is what
  SQLite does with STAT4 enabled (section 17, corrected): it recompiles a
  statement when a new binding might change the plan.
- A fallback to the rule-based planner, selected by a SET command.

This settles section 7's questions 2 and 3, and the cost-based question that
gated stage A and stage B (section 6). The run-time switch (5.1) remains as the
first step, since it does not need statistics.

**What follows.**

1. **Per-value statistics are now needed.** Per-parameter plans cannot be
   chosen from distinct counts alone, because `kind = $1` looks the same for
   every value (section 9, review). SQLite's own answer to that is `stat4`: a
   sample of index keys, which gives per-value estimates. So "use SQLite's ideas"
   and "per-parameter plans" point to the same statistic. Deferred question 2 is
   therefore live, and I propose the `stat4` shape as the answer. Section 7 needs
   your confirmation of that.

2. **The cache has to key on the choice, not the value.** Section 5.4's guarded
   variants are the mechanism: a statement keeps a small set of plans, each valid
   under a guard on the estimate, and the cache key is the outcome of the guards.
   This keeps the plan cache working, which matters because `select`
   (cmd/lexdb_exec.lxl:7136) currently drops a plan whenever a parameter's value
   is read. That behaviour must change for this design.

3. **The "provably better" principle (section 12) and estimates are in tension.**
   A cost-based choice is an estimate, and it is not provably better. Section 12
   said choices should come from exact counts for the value in hand. Two ways to
   reconcile: (a) cost estimates pick the candidate set and order, and exact
   counting (count-then-commit, section 10) makes the final access choice per
   execution; (b) accept estimate-based choices and drop the principle for
   access paths. This needs your decision, because it decides how far plans can
   be wrong.

4. **The SET fallback needs a definition.** Open points: scope (per session, or
   per database for all sessions); whether the mode is part of the plan-cache
   key, so switching modes never reuses a plan from the other mode; and whether
   EXPLAIN shows the mode. The fallback is the existing rule planner, so it is
   also the regression baseline for the test suite.

5. **Stability still applies, with a change.** SQLite's stability guarantee
   says plans change only on schema changes, `ANALYZE`, or a version change, and
   SQLite itself breaks it when STAT4 recompiles a statement for a new binding.
   Per-parameter plans here add the same trigger: a new parameter value. The
   rule to write down is that a value can only select among the variants that
   already exist, and new variants arise only from an `ANALYZE` or DDL. That
   keeps the set of possible plans finite and listable, which is stricter than
   SQLite's recompilation.

6. **The planning budget is now a per-execution cost.** Per-parameter planning,
   or variant selection through guards, runs on every execution. Keys and
   unique-key equalities must stay on a no-statistics fast path, so point lookups
   pay nothing. The planning-time measurement (section 8) is now required, not
   optional.

7. **Search width.** Decided earlier: a limit of 12 tables. Under SQLite's
   bounded search, that is a width, not exactness. The width still needs a
   number, to be set from the planning measurement.

**Decided (user, 2026-11-11), after the list above.**
- The per-value statistic is `stat4`-style sampling (consequence 1).
- Consequence 3: option (b). Estimates decide plans. The provably-better
  principle (section 12) then applies only to the run-time switch (5.1). It no
  longer governs access-path choice. Plans can be wrong for some values, and the
  fallback and the stat4 samples are the protection.

**Decided (user, 2026-11-11): session override.** The planning mode is a
database-wide setting, stored in the catalog and on by default (cost-based). A
session may override it with SET. Consequences:
- Two connections to the same database can plan differently. That weakens the
  predictability the user asked for, so the mitigations are required: EXPLAIN
  shows the mode in effect for the session, the plan cache key includes the mode,
  and the database-wide setting is logged when it changes.
- The override is not limited to tests. The regression suite runs both modes
  through the same tests, using the override.

**Open.** The exact SET syntax, and whether a session override can be turned off
by an operator (so that a database can be locked to one mode).

## 19. First version built: the index-to-scan switch (2026-11-11, revised after review)

Built on `exp/optimizer`, uncommitted. The first version (a fixed budget of 1024
entries) was reviewed and had four problems; this is the fixed version.

**What it does.** For the first table of a query, when its path is an index
range (not a point, not an IN list), the range is counted before any row is
read (`indexOrScan` in cmd/lexdb_exec.lxl):
- At most `SWITCH_ENTRIES` (1024) entries: the index. The entries' primary keys
  are kept from the count, so the range is read once, not twice.
- More: the range is counted up to n entries and the table up to 2n rows, n
  doubling, until one ends; when the range ends first, the table is counted up
  to twice the range. A scan is taken exactly when the table has at most twice
  the range's entries. The cost model is the one from section 15: an index
  entry costs about two reads (the entry, then its row), a scanned row one.
- The table is counted a leaf at a time (`countRows`, using the store's
  `scanLeaves`), so counting it costs leaf reads, not row decoding.
No statistics are needed, and the rule cannot make a large table slower the
way the fixed budget did. Every row is still checked against the conditions.

**Not switched:**
- a path chosen for ORDER BY or MIN/MAX (`Level.keeps`);
- a correlated subquery or LATERAL subquery (`q.refs`), or a path holding a
  correlated subquery: these run once per outer row, so a scan would be paid per
  row;
- INSERT, UPDATE and DELETE (`Run.writes`), and any statement inside a
  read-write block (`Txn.tracked()`, `Txn.live`). A scan records the whole
  table as read, and commit checks it, so it would conflict with every
  concurrent write to the table. Read-only blocks and statements outside a
  block may switch.

**What the review found, and the fixes.**
1. Correlated subqueries switched on every outer row: 20 outer rows on a
   20,000-row table read 400,000 rows instead of about 40,000. Fixed by the
   `q.refs` guard.
2. Writes and read-write blocks switched, widening the read set to the whole
   table. Fixed by the write and block guards.
3. Every non-unique index lookup read its range twice (count, then fetch).
   Fixed: the keys from the count are used.
4. The fixed budget switched large tables to a scan when the index was cheaper.
   Fixed by counting the table as well (above). This replaces the user's
   "fixed budget" choice for the first version; the 1024-entry budget remains
   only as the short-range cutoff.
Also corrected: SQLite does plan per parameter value with STAT4 (section 17).

**Tests.** `tests/lexdb/run/exec_switch.lxl` covers: a short range and an
equality (index, keys read once); 2,000 entries of 5,000 rows (index); 3,500 of
5,000 (scan); results equal to a plain scan; an ORDER BY the index supplies; a
correlated subquery (no switch); a read-write block (no switch) and a read-only
block (switch); UPDATE and DELETE results; 4,000 entries of a 20,000-row table
(index; the fixed budget would have scanned). It passes.

**Full suite.** After stage A (section 20): 72 passed, 0 failed, run with four
parallel jobs. With one job per CPU, `exec_corrkey` can hit its 10-second limit
under load; it does the same on the base commit.

**Not done.** Plain EXPLAIN shows no sign that a path may switch; only EXPLAIN
ANALYZE does. Adding it would change the expected output of every existing test
that EXPLAINs an index range at the first table, so it waits for the user's
decision on the EXPLAIN format. Joins at later levels keep their paths. No
timings were taken.

## 20. Stage A built: ANALYZE and the tie-break (2026-11-11)

Built on `exp/optimizer`, uncommitted, after the switch (section 19).

**ANALYZE.** `ANALYZE [VERBOSE] [table]` (also spelled `ANALYSE`) reads each
table once and writes one catalog row per table, keyed 5 then the table's
catalog key (between the sequences, 4, and the tables). It holds the table's
tree, its rows, and per index (by its tree) the index's entries and the exact
number of distinct values of each leading prefix of its columns (the
`sqlite_stat1` shape). A filtered index counts only its own rows. ANALYZE bumps
the catalog version, so prepared statements are planned again. Statistics of
an older table of the same name are ignored (the tree differs). It is a write
statement, so it is refused in a read-only block. No statistics are kept on
other writes (section 13): only ANALYZE changes them.

**How the planner uses them.** Only to break a tie the rules leave between two
candidates of the same score: the one with fewer expected rows wins, where
expected rows are the index's entries divided by the distinct values of its
equality prefix. EXPLAIN shows "(estimated N rows)" on an index path when
statistics were available for it. Without statistics, or with the rules mode,
the plan is exactly the rules' plan.

**SET lexdb_planner = cost | rules.** A session setting, default `cost`. `rules`
stops statistics being read. It is saved and restored with a block like the
other settings (a ROLLBACK undoes it), it is part of the plan cache's key, and
SHOW reports it. The database-wide default that the user chose (section 18) is
not built yet: only the session setting exists.

**Also fixed.** `SHOW ALL` panicked: `lexdb_batch` was in the settings list but
had no value to show. That predates this branch.

**Tests.** `tests/lexdb/run/exec_analyze.lxl`: the `ev` tie from section 3
(rules pick `ev_kind`; after ANALYZE `ev_uid`, estimated 10 rows), the rules
mode and RESET, a bad value, a SET undone by ROLLBACK, the undeclared-unique
case from section 15 (`t_a` before, `t_c` after), statistics of a dropped table
not used, an unknown table, and SHOW ALL. The full lexdb suite passes: 72 of
72, run with four parallel jobs (with one job per CPU, changing a shared module
makes every test recompile and many hit the compile timeout).

**Not built yet.**
- `stat4`-style samples, so no per-value estimates: `kind = $1` still looks the
  same for every value. That is the next statistics step (section 18).
- Per-parameter plans, the guarded variants and the plan-cache change they
  need (section 18).
- Estimates for ranges, IN lists, the primary key, and index-versus-scan (the
  run-time switch covers index versus scan).
- Join ordering (constraint-bound, then cost-based).
- The database-wide planner setting.
- A renamed table's statistics are lost (they are keyed by name); a new index
  has none until the next ANALYZE.

## 21. Second review and fixes (2026-11-11, after commit 5a6dae89)

A Fable review of the commit found five bugs; all are fixed, uncommitted. The
full lexdb suite passes, 72 of 72 (four parallel jobs; a first run while
another session loaded the machine had 13 compile timeouts and nothing else).

Testing found one more change needed: a standalone EXPLAIN ran on a live
transaction, whose reads are noted, while the SELECT it explains runs on a
snapshot. With the new guard, EXPLAIN ANALYZE never showed the switch the
SELECT makes. EXPLAIN now runs on a snapshot as SELECT does (it writes
nothing, and EXPLAIN ANALYZE runs only a SELECT).

1. **A cached plan could be reused for another schema.** A version bumped in a
   block that rolled back could equal a version another session committed
   later, and a prepared plan kept under it was reused (the review saw a wrong
   count after a DROP INDEX). Versions are now unique in the process
   (`nextVersion`: the count, a bump counter and the clock). The mechanism
   predated this branch.
2. **LIMIT and EXISTS paid for the count.** `Level.stops` keeps the switch off
   when the first table's reading may stop early: a LIMIT without a sort or
   grouping, EXISTS, a scalar subquery without aggregates.
3. **ANALYZE made read-write blocks fail.** It bumped the catalog's version,
   which every SELECT reads. It now bumps a version of its own
   (`\x02stats`), and both that version and the statistics rows are read
   without noting (`Store.getUnnoted`), since they change plans, never
   results. ANALYZE reads the tables on a snapshot of its own, so its noted
   reads are only the catalog's, and it no longer retries against concurrent
   writes.
4. **The write guard missed autocommit INSERT ... SELECT.** The guard now asks
   the store whether the transaction's reads are noted (`Txn.noting()`).
5. **RESET ALL in a block left the block on the rules.** Fixed.

Smaller fixes: ANALYZE stops counting distinct values per prefix at 100,000
(memory bounded; the estimate is then an upper bound) and honours
`statement_timeout`; statistics rows are deleted with their table and moved on
RENAME and SET SCHEMA; statistics are read only for tables with two indexes or
more, so other plans pay nothing for them.

Not fixed: a candidate without statistics listed first still blocks the
tie-break; the primary key has no estimate; on a replica the table is counted
entry by entry. The plan cache does not yet keep several plans (the reviewer's
step 2 before stat4).

New test cases (passing): exec_switch: a LIMIT, an EXISTS, an INSERT ... SELECT;
exec_analyze: RESET ALL in a block, a renamed table, an ANALYZE rolled back.

## 22. Plans kept per outcome of the parameter looks (2026-11-11)

The plan cache's change the second review put before `stat4`.

**Before.** `select()` kept one plan per prepared statement, and none at all
when planning looked at a parameter's value (`PARAM_LOOKS`): a LIMIT or OFFSET
given as a parameter, or the check whether `x > $1` implies a partial index's
predicate. Such statements were planned on every run.

**Now.** Each look is noted while planning, with what it gave
(`Look`, collected in `Scope.looks`, which every planning function of a
statement shares):
- a partial index's implication: yes or no;
- a LIMIT or OFFSET: its value, which the plan keeps.

`PlanCache` keeps up to `PLAN_VARIANTS` (4) plans per statement, each with its
looks. A run re-evaluates each kept plan's looks with the new parameters
(`looksHold`) and takes the first that gives the same outcomes; otherwise it
plans, and keeps the new plan while there are fewer than four. A plan with no
looks fits every run, as before. The key around them is unchanged: the
catalog's version, the search path, and the statistics' version or the rules
mode.

This is the mechanism the per-parameter plans of section 18 need: a `stat4`
estimate for `kind = $1` becomes one more look (say, "expected rows over a
threshold"), and the cache keeps a plan per outcome without replanning per
value. The set of plans is finite and each is listed by its looks.

**Tests.** `exec_plancache`: LIMIT kept per value and taken again for a value
seen before, the cap of four, a partial index's two outcomes and a third value
taking the first again, and the rolled-back version from the second review
(a plan kept under a version made in a block that rolled back is not taken
for the version another session commits next).

**Not done.** EXPLAIN of a prepared statement does not name the plan it would
take; the cap does not replace old plans (past four, new outcomes are planned
every run).

## 23. Per-value estimates and per-parameter plans (2026-11-11)

The user chose `stat4`-style statistics for per-value estimates (section 18).
What was built is the part of SQLite's `stat4` that equalities need: for each
index's leading column, its most common values with exact counts. SQLite's
`stat4` keeps samples spread over the whole key range with their counts below
and equal, which also serves ranges; that is not built.

**ANALYZE** counts the leading column's values (the counting already kept the
distinct values; it now keeps how many of each) and stores up to
`COMMON_MAX` (16) values above the average, largest first, as hex of their
encoded index parts with their counts. Values past the distinct-value cap
(100,000) are not counted.

**Estimates.** For an equality on an index's leading column whose value is
known at planning (a literal or a parameter), the estimate is its count when it
is a common value, else the average of the other values (`rowsOf`). Two or more
equalities use the distinct counts of the prefix as before. EXPLAIN shows the
estimate for the value given.

**Per-parameter plans.** When candidates tie on the rules' score and a
parameter's value set one of the estimates that decided between them, the
estimate becomes a look (kind 2): its scale (about a power of two) is the
outcome, and the look keeps a copy of that index's common values so a later
run can recompute it without the catalog. The plan cache of section 22 then
keeps a plan per outcome. Looks are recorded only for the candidates that tied,
so a statement whose plan does not depend on the value keeps one plan.

**Example (tested).** `kind = $1 and uid = $2` on `ev`-like data: kind 1 holds
99% of the rows. With kind 1 the plan reads `uid`'s index (about 10 rows
against 990); with kind 2 the two estimates are equal (10) and the rules' order
picks `kind`'s index. A second kind-1 run with another uid takes the first plan
again: two plans for three runs.

**Not built.** Range estimates and even samples (the rest of `stat4`);
estimates deciding beyond ties; join ordering; the database-wide planner
setting; EXPLAIN naming which kept plan a prepared statement would take.

## 24. Estimates decide beyond ties (2026-11-12)

The user's option B (section 18): estimates decide plans. Until now they only
broke ties between candidates the rules ranked equally. Now they decide
between candidates of any rank (`choosePath`). The choices below were made
without asking, under the standing "act without asking" rule; each is easy to
change.

**Each candidate's figure** (`pathFig`), from ANALYZE's statistics:
- equalities: the estimate of section 23 (the first equality's value when it
  is constant, else the distinct counts of the prefix);
- an IN list: a lookup per value, each a literal's own count on a leading
  column, else the next prefix's average; at most the rows of its equalities;
- a range, an IN subquery, or an array: **only a bound**, the rows of its
  equalities (the index's entries when it has none). No fraction is guessed
  (SQLite assumes 1/4 for an open range and 1/64 for a closed one). A range is
  therefore taken only when its bound already beats the others. Range
  estimates wait for samples. EXPLAIN shows a bound as "(at most N rows)".

**The cost** (`figCost`) is section 15's model: an index entry is two reads,
the entry and then its row; a primary key row is one.

**The choice.** The fewest reads wins; ties go to the higher rules score,
then to the rules' order. The rules still decide:
- a whole-key equality on the primary key or a unique index: one row, and
  the no-statistics fast path section 18 asked for;
- when the rules' own choice has no figure (an index created after the last
  ANALYZE). A candidate without a figure takes no part otherwise;
- at a join level after the first, between a path looked up per outer row
  and one read once (hashed). Comparing those needs the number of outer
  rows, which is join ordering's work. Estimates compare only candidates of
  the same kind as the rules' choice. Level 0 has only one kind.

**Primary key statistics.** A primary key of two or more columns now has
statistics like an index's, stored under the table's tree: distinct values
per prefix, and its leading column's common values. ANALYZE counts them
without a map, since rows come in key order: a prefix's distinct values are
counted where it changes, and the leading column's values by their runs. A
single-column primary key needs none, since an equality on it is a whole-key
lookup. Its range is bounded by the table's rows. Statistics are now loaded
for a table with two indexes, or with one index and a primary key of several
columns.

**Per-parameter plans.** Section 23's looks are kept for every candidate
whose figure a parameter set and that took part in the comparison, not only
for tied candidates. The rule from section 23 still holds: a statement whose
plan does not depend on the value keeps one plan.

**Examples (tested, `exec_estimates`).**
- `a = 1 and b = 2 and c = 5`, with indexes `t_ab (a, b)` and `t_c (c)`, and
  `c` unique in the data but not declared. The rules take `t_ab`, which has
  more equalities but about 334 rows; the estimates take `t_c`, about 1 row.
- `a = 1 and b = 2 and c > 1990`: `t_ab` (estimated 334 rows). The range on
  `t_c` is bounded at 2,000, so it is not taken.
- `a = 1 and c in (3, 5, 9)`: `t_c`, a lookup per value (estimated 3 rows).
- `m (tenant, id)` primary key, where tenant 1 holds 95% of the rows, with an
  index on `kind`: `tenant = 1950 and kind = 3` reads the key (estimated 1
  row); `tenant = 1 and kind = 3` reads `m_kind` (40 rows, 80 reads, against
  1,900). The prepared form keeps two plans, one per tenant scale
  (`exec_plancache`).
- A join where the rules take a read-once `t_ab` (334 rows) over a per-row
  `t_c` lookup keeps `t_ab`. This is the limit above: join ordering must
  compare the two kinds.

**Not built.** Comparing a lookup per outer row with a hash join (join
ordering); range estimates (samples); a full scan as a candidate (the
run-time switch covers level 0); EXPLAIN naming the kept plan.

## 25. Join order, step 1: bound by keys (2026-11-12)

The constraint-bound order from section 5.3, built after the rebase onto
`lexdb` (views, privileges, tables without a primary key, indexes on
expressions; the rebase's fixes are in commit e3bff230 and below).

**The rule** (`Query.joinOrder`, `bindOf`). No statistics; the order depends
only on the statement and the schema. A SELECT's inner joins start from the
first table, in FROM order, that a unique key pins to one row: the primary
key or an unfiltered unique index, every column equal to a constant or a
parameter. Then, each time, the first remaining table in FROM order that is:
1. bound by a unique key to the tables placed: at most one row per row;
2. else reached by a key's or an index's leading column: a lookup per row;
3. else linked by any equality: a hash join;
4. else the first remaining: a cross product.
With no pinned table, or when the order found is FROM's, nothing changes.

**What keeps FROM's order.** Outer joins and LATERAL (both need their written
order); `SET lexdb_planner = rules`; UPDATE ... FROM and DELETE ... USING,
whose target must stay first (`buildQuery`'s new `order` argument is true only
for SELECT).

**How it is done.** Levels keep their columns' places in the joined row
(`Level.first`), so `SELECT *`, the output, and every column position stay
where FROM put them; only the order the levels run in changes. The
conjuncts (ON and WHERE together, since all joins are inner) are placed again
at the latest table they use in the new order. Three things assumed the
first table's columns start at 0 and were fixed: `levelOf` (now by range),
`firstCol` (ORDER BY and MIN/MAX use the first table's own column), and the
MIN/MAX stop column (`Sel.first`, a place in the joined row). A batch scan
needs the first table at column 0, so a reordered query reads row by row;
the pinned start is a point lookup, so batches would not apply anyway.

**Examples (tested, `exec_joinorder`).**
- `FROM lines l JOIN orders o ON l.ord = o.id JOIN products p ON p.sku =
  l.sku WHERE o.id = 5`: the rules scan all 5,000 lines; the new order looks
  up the order, its 5 lines through `lines_ord`, and a product per line. Same
  rows as the rules mode.
- The customer by a unique email, its orders hashed on `cust` (no index),
  then their lines by index. Before the hash-join tier was added, the lines
  came second as a cross product (5,000 rows for one customer): the test
  caught it.
- Comma joins with WHERE, a subquery in FROM (hashed after the pinned
  tables), a correlated EXISTS on a moved table, ORDER BY and MIN/MAX on the
  moved first table, `SELECT *` column order, and the cases that keep FROM's
  order.

**Also fixed.** This branch's code comments cited `design/lexdb.md` sections
9.53 to 9.58 for its own work. Those sections are about decoding, sockets
and io_uring. They now cite this document's sections ("optimizer 19" to
"optimizer 25").

**Not done.** The cost-based order (section 5.3, step 2), which also decides
between a lookup per outer row and a hash join; UPDATE ... FROM's join (its
target is scanned in full even when the FROM table is pinned); outer-join
reordering.

## 26. Join order, step 2: by cost (2026-11-12)

Section 5.3's second step. The user's go-ahead (2026-11-12) covered the
planning-time measurement it required.

**When it applies** (`Query.costOrder`). A SELECT's inner join of 2 to
`JOIN_SEARCH_MAX` (12) tables, every one a stored table with ANALYZE's
statistics, and no outer join or LATERAL. A table in a join now loads its
statistics even with fewer than two indexes (`loadEst`'s `join` argument).
Otherwise section 25's order stands, so a database without ANALYZE plans as
before. `SET lexdb_planner = rules` keeps FROM's order.

**The search.** Exact dynamic programming over left-deep orders: for each set
of tables, the cheapest way to have joined them. A set is extended only by a
table that some conjunct links to it, unless no table outside it is linked;
this is the usual "no cross product while a join is left" pruning. At each
step the table is either looked up per row of the set (a key or an index
whose leading columns the set's values bind) or read once and hashed,
whichever costs less. A table chosen to be read once is marked
(`Level.readOnce`), and `choosePath` then takes no path that uses the tables
before it. Ties keep the first order found, which makes the result
deterministic.

**The model**, in reads, as in section 24:
- a lookup: a descent (1), then its rows, 1 each by the primary key or 2 by
  an index;
- read once: the table's cheapest way by its constants (a full scan at
  worst), each row put in the hash `HASH_BUILD` (0.2), each outer row's
  probe `HASH_PROBE` (0.1). The build costing more than the probe makes the
  smaller side the hashed one; without it, the first version hashed a
  20,000-row table to probe it 100 times;
- each row the join gives `ROW_COST` (0.1);
- rows of a set: its tables' rows by their constants, times, for each
  equality between two of its tables' columns, 1 / the larger distinct count
  of the two. Distinct counts come from a one-column primary key or unique
  index (the table's rows), an index's leading column (ANALYZE's count), or
  else about 10 rows per value (SQLite's default). This answers section
  5.3's open question on a default selectivity;
- parameters are unknown values, so the order never depends on a
  parameter, and a prepared join keeps one plan (tested). Literals are
  estimated by value.

**Examples (tested, `exec_joincost`).** `big` has 20,000 rows, 200 per
`small` row; `small` has 100 rows, one labelled `x`.
- `big JOIN small ON b.sid = s.id WHERE s.label = 'x'`. Without statistics,
  or with the rules: `big` is scanned and `small` looked up 20,000 times.
  Now: `small` by its label index (1 row read), then `big` through `big_sid`
  (200 rows).
- The same join without the filter: `big` scanned, `small` hashed (100
  rows), not looked up per row.
- Three tables, `mid` without an index on `sid`: `mid` scanned, `small`
  hashed from its label index, `big` looked up per row by index.
- A table without statistics in the join: section 25's order.

**Planning time** (`design/experiments/plan_time.lxl`, 2026-11-12, an idle
machine). EXPLAIN plans from scratch each time, catalog and statistics reads
included. Each table has 1,000 rows and two indexes, and the joins are chains
`tN.p = tN-1.id` plus a star `tN.p = t1.id`. Microseconds per EXPLAIN:

| Query | Cost mode | Rules mode |
|---|---|---|
| point select | 6 | 6 |
| 2 tables | 14 | 11 |
| 4 tables | 25 | 18 |
| 8 tables | 52 | 34 |
| 12 tables, chain | 147 | 50 |
| 12 tables, star | 636 | 49 |

Before the cross-product pruning, the 12-table chain took 1,031 us (all 4,096
sets). Point selects pay nothing. The star is the worst realistic shape,
since every set holding its centre is connected (2,048 sets). Prepared
statements pay it once, through the plan cache; the simple query protocol
pays it each time. The 12-table bound stands unless the user lowers it.

**Not done.**
- Equalities implied by others (a = b and b = c gives a = c) are not
  derived, so a table linked only through another is not reached directly.
- Range estimates and filters on unindexed columns are not counted: a
  table's rows by its constants count only its key and index equalities.
- The executor may still take another path than the one costed. The model
  plans a lookup, then `choosePath`'s rules or estimates pick the level's
  path; `readOnce` is enforced, a lookup is not.
- Bushy plans, outer-join reordering, and the run-time check of section 5.5.

## 27. Implied equalities (2026-11-12)

**What.** In an inner-join SELECT in cost mode, the equalities make classes
of equal columns, perhaps with a constant (a literal or a parameter):
`a = b` and `b = c` put a, b and c in one class, and `a = 5` gives the class
a constant. The equalities the classes imply and the statement does not
hold are added to the conjuncts (`Query.implied`, `eqClasses`):
- between two columns of different tables: `a = c`;
- of each column with the class's constant: `b = 5`, `c = 5`.
Columns join a class only when their types are of one kind, so that a
derived comparison means what the written ones mean. A row for which the
written equalities are true makes the derived ones true, so results do not
change. Outer joins, LATERAL and the rules mode derive nothing.

**What it gives.**
- A table is reached straight from any table of its class, and a constant
  pins what it reaches: in `lines JOIN orders ON l.ord = o.id JOIN cust ON
  c.id = o.cust WHERE o.cust = 7`, `c.id = 7` is derived, so the customer
  is pinned and runs first. The rules mode scans all 5,000 lines (tested).
- `small`, `big` and `mid` joined through `mid`: `b.sid = s.id` is derived,
  so `big` is looked up from the one `small` row (200 rows), not per `mid`
  row (about 4,000).
- A constant's equality is taken before an outer value's when a key column
  has both (`choosePath`, only where implied equalities were derived). The
  value is the same for every outer row, so the table is read once:
  `orders` pinned, then its lines by `lines_ord` on the constant, hashed.

**The cost model counts a class once.** When a table joins a set, each class
it shares with the set divides the rows by the largest distinct count among
the class's columns there. A per-pair count would apply the same join two
or three times over, since the derived pairs repeat it. A class with a
constant divides nothing: each table's constant condition has counted.

**Planning time.** Measured again with `plan_time.lxl`, load about 1.7, in
microseconds per EXPLAIN:

| Query | Before (section 26) | Now |
|---|---|---|
| point select | 6 | 6 |
| 4 tables | 25 | 28 |
| 8 tables | 52 | 63 |
| 12 tables, chain | 147 | 168 |
| 12 tables, star | 636 | about 1,600 |

The star is the costly case. Every spoke joins the centre's key, so the
derived spoke-to-spoke equalities link every table to every other, and the
search visits all 4,096 sets again. Leaving derived equalities out of the
linking kept the star near 800 us, but it hid the plan in the second
example above (`small` to `big` counted as a cross product), so they link.
Two measurement lessons: the first per-class loop indexed nested arrays of
records in the loop over every set and tripled the chain's time (147 to
450 us); flat arrays fixed it. A `for ... in` over records was measured and
does not copy.

**Open (the user's call), answered.** About 1.6 ms for a 12-table star.
The user chose SQLite's N-best search (section 28).

## 28. SQLite's N-best search past 8 tables (2026-11-12)

The user's choice after section 27's star measurement.

**What.** Up to `JOIN_EXACT_MAX` (8) tables, the search stays exact (section
26). Past that, up to `JOIN_SEARCH_MAX` (12), it is SQLite's: the orders
are built one table at a time, and at each step only the `JOIN_BEST` (10)
cheapest partial orders are kept, one per set of tables (the cheaper of two
orders of the same tables). Each is extended by every table it may take
next. The costs, row estimates, pruning and lookup-or-hash choice are the
exact search's (`joinStep`, shared), so the two can differ only where the N-best
search drops an order that would have become the cheapest. SQLite keeps 10
for three tables or more; the same here.

**Measured** (`plan_time.lxl`, load about 1, microseconds per EXPLAIN; the
exact column is the same build with `JOIN_EXACT_MAX` at 12):

| Query | Exact | N-best |
|---|---|---|
| 12 tables, chain | 167 | 173 |
| 12 tables, star | 1,725 | 441 |

The plans chosen are the same for both queries (compared line by line).
The chain gains nothing: the pruning had already cut it to 78 sets, and the
rest of its time is the setup, the rows of every set (an array of 2^n,
which also keeps the bound at 12 for now). Up to 8 tables nothing changed:
63 us at 8.

**Test.** `exec_joincost` has a 10-table chain written from the far end, its
filtered table last in FROM, so the N-best search runs in the suite. The plan
starts from the filtered table's index (an estimated 10 rows) and looks up
each next table; the count equals the rules mode's.

**Not done.** Raising the 12-table bound: the N-best search itself would
allow it (SQLite plans 64), but the rows of every set are computed up front
(2^n). They would have to be computed as needed first. Also: the filter in
the first version of the test was on an unindexed column, and the model
ignored it (all ten tables estimated alike, FROM order kept). That is the
known gap of section 26: filters on unindexed columns.

## 29. Join-order review and fixes (2026-11-12)

A Fable review of sections 25 and 26 ran about 730 queries under both
planner modes, comparing result rows: about 220 written by hand and 510
random joins of 2 to 13 tables. It found **no wrong results**. It did find
queries that now failed and plans that got worse; each is fixed and has a
case in `tests/lexdb/run/exec_joinreview.lxl`. The review's repro scripts
are kept in the session's scratchpad, not the repository.

1. **A key value the column cannot hold was an error** (22003 out of range,
   22001 too long) in a hash probe or a key lookup. Example: a bigint
   2^40 probing an int key. The bug predates this branch, but reordering
   reached it more often. Now such a value matches no row (`keyVal`), and the
   probe uses the column's type for bounds (`boundType`), as lookups do.
   Other errors stand: `int_col = 'abc'` still gives 22P02. Range bounds
   past a type's range are unchanged (an error in both modes, not reported).
2. **A hash join could break `max_statement_mem`.** The planner now knows
   the session's limit (`Txn.memMax`, in the plan cache's key). A hash is
   chosen over a possible lookup only when its estimated rows
   (`estRowBytes`) fit in half the limit and in 64 MB.
3. **Filters other than index equalities counted for nothing.** A table's
   rows by its own conditions now count:
   - an equality's value by its common values, or 1/distinct;
   - a range by the part of the column's span it covers, using its least
     and greatest values, which ANALYZE now records for the leading column
     of each index and of the primary key (numbers, dates and times; a
     single-column primary key gets an entry too);
   - SQLite's 1/4 or 1/16 when there is no span or the bound is a
     parameter;
   - an IN list n/distinct, `<>` 1 - 1/distinct, anything else 1/2.
   A table's constant way also takes a range on the next key column. The
   review's cases now read 3 to 5 rows, as the rules do, where they read up
   to 20,000.
4. **LIMIT and EXISTS paid for a full hash build.** `Scope.early` marks a
   query whose reading may stop early: a LIMIT without ORDER BY or GROUP
   BY, EXISTS, or a scalar subquery. Its lookups are not turned into
   hashes.
5. **A hash join in a read-write block caused serialization failures.** A
   whole-table read conflicts with every write to the table, as optimizer
   19 noted for the switch. The first fix (lookups only) was not enough:
   the cost order then scanned the other table first, without range
   estimates. Such transactions (`Txn.noting()`) now keep the order bound
   by keys (section 25), which starts only from a pinned row.
6. **Batch scans were skipped** when the first table was not FROM's first.
   `batchLevel` and `bCompile` now offset by the level's place in the
   joined row.

**Known, not fixed.**
- An ORDER BY ... LIMIT that FROM's first table could serve in index
  order: the cost order may read 2,000 rows where the rules read 42 (a
  common label). For a rare label the rules would read most of the table,
  and the cost order a few rows. The search does not yet weigh "read in the
  order and stop early".
- Review finding 7, minor and not demonstrated: a read-once level drops a
  path that mixes a constant and an outer value, where it could keep the
  constant prefix; `wayInto` takes the first value for a column that has
  both a constant and an outer one.
- Hash against lookup, measured on one in-memory join of 20,000 rows: 19.2
  ms against 21.5 ms, so the model's preference for hashing is right but
  stronger than measured. Not calibrated further.

**Planning time** (`plan_time.lxl`, load about 1): point select 7 us; 4
tables 32; 8 tables 72; a 12-table chain 194; a 12-table star 512. The
extra over section 28 is mostly reading the larger statistics rows, once
per table per planning.

## 30. The join search to 24 tables (2026-11-12)

The user's request, after the N-best search (section 28): double the bound.
`JOIN_SEARCH_MAX` is now 24. Exact search stays to 8 tables and N-best
covers 9 to 24. Past 24, the order bound by keys (section 25) stands.

**What had to change.** The rows of every set of tables were computed up
front, an array of 2^n. At 24 tables that is 16.7 million entries. The rows
of a set are now computed when the search reaches it (`setRows`, kept in a
map). They are defined by the set's lowest table, as before, so they do not
depend on the order that reached the set, and the exact search's results
are unchanged. The N-best search also keeps each extension as its parent
and the table added, copying the order only for the 10 kept, and finds a
set's earlier extension through a map instead of a scan.

**Measured** (`plan_time.lxl`, load under 1, microseconds per EXPLAIN):

| Tables | Chain | Star | Rules mode |
|---|---|---|---|
| 12 | 131 | 326 | 51 |
| 16 | 177 | 686 | 69 |
| 24 | 310 | 2,238 | about 105 |

(after the profile below; first measured 133, 401; 198, 877; 365, 2,904)

Up to 12 tables this is faster than section 29 (chain 194, star 512),
because the 2^n rows are no longer computed. The 24-table star is the
costly shape. Its spokes all join the centre's key, so implied equalities
link every pair (276 derived), and each of about 5,760 extensions costs a
lookup estimate and a set's rows. Two tries changed little: checking implied
equalities against a set of texts (3.2 to 3.0 ms), and copying only the
kept orders (3.0 to 2.9 ms). A profile of the native build (perf, with
`LXL_NATIVE_MAP` giving the function names, design/native.md section 4)
then found the cost: `levelOf` searched the query's columns by string
compare (9% of the run), and each table's range estimate scanned every
conjunct of the query (7%). The query now keeps its columns by name
(`Query.colAt`, built for joins), and each table's estimates see only its
own conditions: the 24-table star went from 2.9 to 2.2 ms, the 12-table
star from 401 to 326 us. What is left is spread out: SQL parsing 16% of
the run, set rows 12% (mostly the map's hashing), and lookup estimates 5%.

**Plans.** The 24-table chain and star choose the expected orders: the
filtered table by its index, then each table by lookup. The star hashes a
spoke once the joined rows grow past the lookups' cost; the hash is keyed on
the same column several times (`hash on (p, p, p, ...)`), since the derived
equalities repeat it. That is correct but wasteful, and not fixed.
`exec_joincost`'s chain is now 20 tables, past the old bound, and its count
matches the rules mode's.

**Open (the user's call).** About 2.2 ms to plan a 24-table star, paid once
per prepared statement. If too much: a narrower N past 16 tables, or not
deriving equalities between spokes that only meet at the centre.

## 31. On lexdb 9.94 (2026-11-12)

The branch was rebased onto `lexdb` 9.94: missing functions and operators,
JOIN ... USING and NATURAL JOIN, DISTINCT ON, FETCH FIRST, row comparisons,
char(n). What changed for the optimizer:

- **ANALYZE.** lexdb 9.94 parses VACUUM, ANALYZE, CHECKPOINT, REINDEX and
  CLUSTER as maintenance statements that do nothing (`S_MAINT`). Its parser
  takes ANALYZE's options, several tables and column lists, and VACUUM
  ANALYZE. That parse is kept: an ANALYZE, or a VACUUM with ANALYZE, is
  `S_ANALYZE`, which runs lexdb's checks (`maint`: the tables and columns
  exist, VACUUM not in a block) and then gathers the statistics of the
  tables named, or of every table. A view has none, so `ANALYZE view` does
  nothing and gives no error, as before. This branch's own ANALYZE parse is
  removed. `S_ANALYZE` is 58.
- **Settings.** lexdb 9.94 added custom settings, `set_config` and
  `SET LOCAL`. `lexdb_planner` is listed for SHOW ALL and the settings
  memo, and `set_config('lexdb_planner', ...)` sets it, as SET does.
- **USING and NATURAL joins.** They are inner joins with equalities, so they
  reorder like any other: checked against the rules mode, with and without
  ANALYZE (same rows). `buildQuery`'s argument is now `reorder`, since
  lexdb's USING code has a local `order`.

The full suite passes, 92 of 92, lexdb 9.94's new tests included. The
rebased commits before the integration commit do not compile on 9.94 on
their own: their ANALYZE parse clashes with lexdb's, and so does the name
`order`.

## 32. ORDER BY ... LIMIT read in order (2026-11-12)

Section 29's known gap. A table that FROM put first, read in its key's
order, can stop after a few rows; the cost order took another table first
and sorted. With a common label, `big JOIN small ... ORDER BY b.id LIMIT 5`
read 2,000 rows where the rules read 42.

**What.** `planSelect` passes the ORDER BY and the LIMIT plus OFFSET to the
join order (`Scope.ordBy`, `Scope.ordLim`; a parameter or an expression is
taken as 100, so that the order does not depend on parameters). This
happens only without GROUP BY, DISTINCT, aggregates or windows.
`orderedLevel` finds the table the ORDER BY sorts by: its items must be
plain columns of that one table, in one direction, with NULLs where an
index keeps them, and the table must have a key or an unfiltered index that
gives that order. `costOrder` then costs a second order (`nBest`, now a
method taking its starting tables): that table first, every other table by
lookup. Its cost is the whole order's times LIMIT / the estimated result
rows. It is taken when that is less than the best order's cost plus a sort
of its rows (rows x ROW_COST x log2 rows). It is not taken:
- when the table has a better way by its constants than a full scan (the
  planner turns only a full scan into an index read for an order);
- when any other table would be hashed (a hash is built whole before the
  first row comes out).
`planSelect`'s existing rule then reads the first table through the index
that gives the order, and the LIMIT stops the scan.

**Tested** (`exec_joincost`; results equal the rules mode's):
- a common label, LIMIT 5: big read in order, 42 rows (was 2,000 and a
  sort); DESC: 49 rows, backward;
- LIMIT 1000: small first and a sort (2,000 rows; in order it would read
  about 10,000);
- by hand, a rare label: in order, 406 rows. Starting from small would have
  read about 200; ANALYZE's estimate for that label is the average, 5 rows
  where it has 1;
- by hand, a filter with its own index on big (`b.v = 2`): small first and
  a sort, since big's way is not a full scan.

## 33. Second review and fixes (2026-11-12)

A Fable review of sections 27 to 31, at d745d52f. It compared the cost
planner with the rules mode, with and without ANALYZE, on about 6,000
random joins of 2 to 25 tables and a few hundred targeted queries: type
kinds, char(n), parameters, range estimates, ANALYZE through `maint`, and
the search sizes 8, 9, 24 and 25. Implied equalities, the N-best search,
`keyVal`, the range estimates and the new ANALYZE gave no wrong results.
Its findings, all fixed, with cases in `exec_joinreview` and
`exec_plancache`:

1. **Wrong rows or a crash** (from section 29's batch fix). When the cost
   order put a table that FROM did not list first at level 0, and it was read
   in batches, a text, numeric or date comparison or a LIKE on it tested the
   column at the joined row's place, not the table's: rows were dropped, or
   the process stopped (index out of range). `bValCol` now offsets by the
   level's place, as section 29 did for `bCompile`. The suite had not
   covered it: a reordered first table with a non-integer condition.
2. **A plan made outside a block was reused in a block that notes its
   reads**, so the hash over a whole table came back, and with it the
   serialization failures of section 29. The plan cache's key now records
   whether reads are noted.
3. **A hashed table dropped its constant range** when its key column was
   also joined (`dim.k = ev.k and dim.k < 10`). The path with the join
   equality was discarded for a read-once table, and the range never tried,
   so the table was read whole. A read-once table's path now takes only the
   bounds that are the same for every outer row (`onceBounds`): 9 rows read,
   not 20,000.
4. **"May stop early" was set for queries that read everything:** an
   aggregate, grouped or DISTINCT scalar subquery, a `count(*) ... LIMIT 1`.
   It now needs a statement that does not gather its rows first
   (`stmtGathers`), so such a join is planned as the same query alone.

**Not fixed (minor, from the review).**
- A range bound out of the column's type (`int_col < 3000000000`) is still
  an error, in both modes and before this branch. PostgreSQL returns all
  rows.
- `int_col = '3000000000'` (an untyped literal) returns no rows where
  PostgreSQL raises 22003. lexdb behaves the same on unindexed columns.
- ANALYZE (now also VACUUM ANALYZE) is refused in a read-only transaction.
  PostgreSQL allows it, but lexdb's ANALYZE writes the statistics rows.
- For ill-typed queries, the error code can differ between the cost and
  rules modes (42883 against 22P02). Both are errors.
- `SET LOCAL lexdb_planner` does not show as set.
- One 24-table random join on non-key columns hit a 1 s timeout under the
  cost planner, where the FROM order reached an empty join early. One case
  in 12 such queries; not explained.

**Checked after the fixes:** the review's random joins again, 6,616
queries over six seeds with ANALYZE, against the rules mode: 0 differences.
The suite: 92 of 92.

## 34. A workload: cost against rules (2026-11-12)

The user's go-ahead for a load test. `design/experiments/workload.lxl`
builds a TPC-H-like schema in one process, with everything in the cache,
so the times are the plans' CPU: 5 regions, 25 nations, 1,000 suppliers,
20,000 customers, 20,000 parts, 80,000 partsupp rows, 200,000 orders and
800,000 lineitems, with indexes on the usual foreign keys, dates and
brand. Loading took 22.7 s and ANALYZE 0.6 s. It runs 14 queries under
both planners: the median of 5 runs after a warm-up, both plans, and a
checksum of the rows. Idle machine.

| Query | Cost (us) | Rules (us) | What |
|---|---|---|---|
| Q1 | 53 | 32 | an order's lines and parts |
| Q2 | 24 | 20 | a customer's last 10 orders |
| Q3 | 139 | 110 | a customer's orders, lines, parts |
| Q4 | 42 | 30 | a part's cheapest supplier |
| Q5 | 38 | 918,140 | an order's lines, FROM lists lineitem first |
| Q6 | 105 | 1,655,115 | count of a customer's lines, FROM lists lineitem first |
| Q7 | 36,099 | 1,399,973 | revenue by nation for a month |
| Q8 | 41,436 | 297,281 | a 6-table local-supplier report for a month |
| Q9 | 63,135 | 42,327 | a brand's lines shipped in a month |
| Q10 | 67,159 | 67,035 | top customers of a segment for a quarter |
| Q11 | 111,052 | 110,967 | status, quantity and size filters |
| Q12 | 70,385 | 1,049,675 | a 5-table filtered count |
| Q13 | 11,395 | 10,202 | EXISTS: a nation's customers with a recent order |
| Q14 | 641 | 616 | a brand's 20 latest lines (ORDER BY ... LIMIT) |
| **total** | **401,703** | **5,551,523** | |

**Every query returned the same rows under both planners.**

**Where the cost planner wins.** Q5 and Q6 are written with a poor FROM
order; the rules scan 800,000 lineitems where the cost plan starts from the
pinned order or the customer's orders. Q7, Q8 and Q12 are reports that the
rules start from lineitem. Overall the cost plans take 14 times less time.

**Where it loses.**
- **Q9, 1.5 times slower.** It starts from the brand's 800 parts and looks
  up their 32,000 lineitems, where the rules read a month of lineitems by
  date (about 16,000) and look up each part. The model's two costs are
  within a few percent of each other, so it is a calibration question: an
  index entry's lookup and a range read are both priced at two reads per
  row, and they are not equal in practice.
- **Q1 to Q4, 4 to 30 us slower.** The plans are the same or equivalent.
  The difference is planning: these are not prepared, so each run loads the
  tables' statistics and runs the cost search. A prepared statement keeps
  its plan and pays this once. A fast path would remove most of it: when
  the order bound by keys (section 25) starts from a pinned row, take it
  without loading statistics or searching.

**Next, from this.** The fast path for pinned joins; calibrating the read
costs (index entry, row by key, range) against measurements such as Q9's.

## 35. Pinned joins: a fast path (2026-11-12)

From section 34: the point queries were 4 to 30 us slower under the cost
planner, though their plans were the same or equivalent.

**What.** A join whose key-bound order (section 25) starts from a row that
its key pins (after implied equalities) takes that order at once
(`hasPinned`). It reads no statistics beyond those single-table path choice
already reads, and does not search. Other joins load their tables'
statistics only when they are costed (`loadEst` during FROM is now the
single-table rule). From a pinned row:
- an equality on an outer value is taken before a constant's (`Query.pinned`),
  so each table is looked up per row, one lookup in all;
- the "constant first" rule of section 27 is off, since a hash of what the
  constant reaches costs more than one lookup.
The plan is then the same whatever FROM's order. `exec_joinorder`'s pinned
cases are back to section 25's plans (a lookup per row, not a hash of 5
rows).

**Measured** (`design/experiments/q1_split.lxl`, a small copy of the
schema, 5,000 runs each): planning is EXPLAIN alone, execution the run
minus that.

| | Cost: planning | Cost: execution | Rules: planning | Rules: execution |
|---|---|---|---|---|
| Q1 before | 32.4 us | 13.0 us | 21.8 us | 9.6 us |
| Q1 now | 31.0 us | 11.3 us | 21.9 us | 9.7 us |
| Q2 (one table) | 13.4 us | 10.7 us | 10.1 us | 9.7 us |

Execution is now close to the rules'. Planning stays about 9 us dearer for
Q1 and 3 us for Q2. The workload's run after the first step: Q1 48 us (was
53), Q3 134 (139), the rest unchanged. Most of what is left is reading and
parsing the tables' statistics rows on every planning (about 3 us a table,
`loadEst`), plus the statistics version for the plan cache. Prepared
statements pay it once. Simple queries would need a cache of parsed
statistics that outlives a statement, which the store does not offer (its
memo holds text). Not done.

**Checked:** the suite, 92 of 92; the random differential sets, 6,616
joins, 0 differences.

## 36. The read costs, measured (2026-11-12)

From section 34: Q9 was 1.5 times slower under the cost planner, and the
model's two costs for it were within a few percent of each other. The
model's units were guesses from section 15: a scanned row 1, a row through
an index 2, a descent 1. `design/experiments/calib.lxl` measures them in
memory on a 200,000-row table (median of 5; nanoseconds a row):

| Operation | ns | units |
|---|---|---|
| a scan's row, in batches (the first table) | 25 | 1 |
| a scan's row, row by row (a hashed table's read) | 307 | 12 |
| a primary key range's row (the first table) | 42 | 1.7 |
| an index range's row (the entry, then the row by key) | 972 | 39 |
| a lookup by the whole primary key, per outer row | 1,409 | 56 |
| a lookup by an index, per row (20 rows each) | 1,182 | 47 |
| a hash join per inner row read and hashed, with an outer probe | 1,404 | |
| the same join by lookups, per outer row | 1,425 | |

A row fetched by its key costs 40 to 55 scanned rows, not 2: the batch scan
is fast, and every fetch by key pays a descent and a row's decoding. A hash
join and per-row lookups cost the same on this join. That is the 19 against
21 ms measured on a 20,000-row join in section 29.

**The model now** (units of a batched scan row): a scan's row 1 as the
first table, 12 when read for a hash; a primary key range's row 1.7 first,
12 after; a descent 12; a row by key, through an index or a primary key
point, 45; a hash's row built 22, a probe 22; a joined row 2. Each way into
a table has two costs, as the first table and as a hashed table
(`Way.inner`). `figCost`, which compares one table's paths, uses the same
units, in tenths.

**Also found: `date '2021-06-01'` was not a literal to the estimates.** It
is a cast of a text literal, so ranges written that way got the 1/16
default instead of their span. `litValue` works out literal expressions
(casts and arithmetic of literals, never parameters), and `litNum` and
`constKey` use it.

**The workload again** (section 34's, after this; µs):

| Query | Cost before | Cost now | Rules |
|---|---|---|---|
| Q9 | 63,135 | 31,668 | 42,122 |
| Q7 | 36,099 | 29,170 to 41,408 | 1,390,315 |
| total | 401,703 | 375,769 | 6,037,808 |

Q9 now starts from the brand's parts and hashes the month's lineitems,
found through the ship-date index: faster than the rules. Q7's plan is the
same in both of this section's runs; its time varied by run (29 to 41 ms),
as the rules' Q6 did (1.68 to 2.04 s). The other queries are unchanged.

**A plan that changed in the suite:** the 20-table chain of `exec_joincost`
now starts from the middle and hashes half the chain. Its row estimates
double at each step (two rows of the next table per id), where the data's
real fanout is about one, so starting from the filtered end looks
exponential. Both plans give the same count, and both are small. It is an
estimate error that the cheaper hashes now expose, not a cost error.

**Not changed: the index-to-scan switch (section 19).** It switches when a
range holds over half the table, from the 2:1 guess. The measured ratio of
an index range's row to a batched scan's row is about 39:1, which would put
the break-even near 1/40 of the table. The switch applies in both planner
modes and without statistics, so the change is left for the user to decide.

**Checked:** the suite, 92 of 92; the random differential sets, 6,616
joins, 0 differences.

## 37. Samples: the rest of SQLite's stat4 (2026-11-12)

The user's request. SQLite with STAT4 keeps, per index, about 24 sample keys
with the rows below and equal to each (`sqlite_stat4`). lexdb had the
common values (section 23) and the leading column's least and greatest
(section 29), but no samples, so a clustered or skewed column's ranges were
estimated as if its values were spread evenly.

**What ANALYZE keeps now**, per index and per primary key, for the leading
column: up to `SAMPLES` (24) keys spread evenly over its rows not NULL, each
with the rows below it and equal to it, and its number when the column is
numeric (numbers, dates, times). It also keeps the count of rows not NULL.
- For an index, the keys come from ANALYZE's existing count of the leading
  values: sorted, one at each (k + 1/2)/24 of the rows. There are none when
  that count stopped at its cap (100,000 values).
- For a primary key, rows come in key order, so a sampler keeps every
  stride-th run of equal leading values and doubles the stride when 48 are
  kept. A single-column key gets samples too.
They are stored in the statistics row as a seventh field per entry
(`nn/hex~lt~eq[~number],...`). Older rows simply have none.

**How a range uses them** (`Samp.below`, `Samp.rangeShare`). The rows below
a bound are the sample's own counts when the bound is a sample. Otherwise
they are the rows to the gap the bound falls in, plus part of the gap. For
numbers and dates that part comes from the neighbouring samples' values,
with the column's least and greatest at the ends. For other types it is a
third of the gap for a lower bound and two thirds for an upper one
(SQLite's rule), so a range inside one gap gets a third of it. Keys
compare as encoded index parts, in the index's order, so text works too.
Samples take precedence over min/max interpolation, which takes precedence
over the 1/4 and 1/16 defaults. A bound must be a literal (a cast of one
counts); a parameter is an unknown value, so plans still do not depend on
parameters.

**Where.** The join model's range shares (`rangeShare`, `boundsShare`), and
now also a single table's path figure (`pathFig`): a range on a leading
column with literal bounds is an estimate, not "at most" the table. So the
rules' "a range only when its bound beats the others" (section 24) now
holds only where there are no samples.

**Tested** (`exec_samples`): 20,000 rows, 90% dated in one month.

| Range | Estimated | Actual |
|---|---|---|
| the clustered month | 18,175 | 18,165 |
| a month outside the cluster | 159 | 137 |
| after 1 December | 135 | 135 |
| a text range (`name >= 'n5' and name < 'n6'`) | 1,933 | 2,220 |
| `id between 100 and 199` | 98 | 100 |

With `kind = 1`, the outside month reads the date index (159 rows) and the
clustered month the kind index (6,667 rather than 18,175). A join hashes the
outside month through its index. Before the interpolation within gaps, a
range inside one gap was estimated at 1 row: both bounds landed at the
gap's middle. `exec_estimates` changed for the better: `c > 1990` is 10
rows, exactly, so `a = 1 and b = 2 and c > 1990` reads `t_c` (10 rows), not
`t_ab` (334).

**Planning time.** The first version parsed every sample of every table at
each planning: a point select went from 7 to 22 us, a 4-table join from 40
to 99. Samples are now kept as text and parsed only when a range needs
them. Measured (`plan_time.lxl`, us; "before" is the calibration commit on
the same lexdb 9.95 base):

| | Before | Now | Rules |
|---|---|---|---|
| point select | 8 | 9 | 7 |
| 2 tables | 23 | 26 | 14 |
| 4 tables | 40 | 45 | 22 |
| 8 tables | 81 | 91 | 40 |

What is left is splitting the longer statistics rows, about 1 to 1.5 us a
table. Separately, the 9.95 base plans about 15 to 20% slower than 9.94 in
both modes (rules, 4 tables: 22 us, was 18 to 19), and sections 31 to 35
added a few microseconds of checks in cost mode.

**ANALYZE** on the workload (1.1 million rows): 604 ms, as before. **The
workload** is unchanged (cost 0.39 s, rules 6.1 s); its ranges were already
well estimated by min and max, its dates being spread evenly.

**Checked:** the suite, 96 of 96; the random differential sets, 6,616
joins, 0 differences.

## 38. The switch by the measured costs, in the cost mode (2026-11-12)

After section 36 the planner had two cost models: the join order priced a
row through an index at 45 batched scan rows, while the index-to-scan switch
(section 19) still took a scan only when a range held over half the table
(an index row 2, a scanned row 1). The user chose option B: the measured
costs in the cost mode, section 19's rule kept in the rules mode, which
stays the old planner to fall back to.

**What.** In the cost mode the switch takes a scan when the table has at
most `COST_KEY_ROW / COST_SCAN_INNER` times the range's entries (45/12, about
3.75: a range over about a quarter of the table). It also checks a range
that ends within `SWITCH_ENTRIES_COST` (64) entries, so a small table is
scanned even for a short range. The rules mode is unchanged: twice the
entries, and no check under 1,024 entries. EXPLAIN ANALYZE gives the rule
that applied ("the range holds over half the table", or "cheaper than the
range, by the measured costs").

**A first version used the wrong ratio.** It took 45, a row through an
index against a scanned row *in batches*. But the switched scan is not
batched: the switch replaces the path of a level that `batchLevel` has
already passed over, so its rows are read one at a time (12). With 45, the
workload's Q13 went from 12 to 20.6 ms and Q9 from 31.7 to 41.5 ms. Both
scanned 20,000 rows row by row where the index read 800. With 3.75 they are
back (13.1 and 35.1 ms). Batching the switched scan would make 45 right and
the scans faster; not done.

**Tests.** `exec_switch` runs section 19's cases in the rules mode, as
before, and adds cost-mode cases:
- 5,000 entries of 20,000 rows: the index;
- 6,000 entries: a scan (the rules: the index);
- a 50-row table: a range of 20 is scanned, a range of 10 is not.
`exec_ops`, one of lexdb's tests, has a LIKE range on a small table that is
now scanned, so its two rows (no ORDER BY) come in key order: its
expectation was updated.

**The workload** (µs): total cost 396,081 against rules 6,299,106, Q13
13,088 (rules 11,824), Q9 35,075 (rules 47,615); the rest as before.

**Checked:** the suite, 96 of 96.

## Sources

- SQLite, Query Planner Next Generation: https://sqlite.org/queryplanner-ng.html
- SQLite, Query Optimizer Overview: https://www.hwaci.com/sw/sqlite/optoverview.html (mirror)
- SQLite, ANALYZE: https://sqlite.org/lang_analyze.html
- "Debunking the Myth of Join Ordering: Toward Robust SQL Analytics", SIGMOD 2025, arXiv 2502.15181 (authors not recorded here): https://arxiv.org/abs/2502.15181
- DuckDB research page on robust predicate transfer: https://duckdb.org/science/robust-predicate-transfer
- Wang, Willsey, Suciu, "Free Join: Unifying Worst-Case Optimal and Traditional Joins", arXiv 2301.10841, SIGMOD 2023: https://arxiv.org/abs/2301.10841
- Marcus et al., "Bao: Learning to Steer Query Optimizers", arXiv 2004.03814, SIGMOD 2021: https://arxiv.org/abs/2004.03814
- DataSwift, NeurIPS 2025 ML for Systems workshop (not checked): https://mlforsystems.org/assets/papers/neurips2025/paper69.pdf
- Tian, "Query Optimization in the Wild: Realities and Trends", arXiv 2510.20082: https://arxiv.org/abs/2510.20082
- Yin and Hameurlain, "Robust Query Optimization Methods With Respect to Estimation Errors: A Survey": https://hal.archives-ouvertes.fr/hal-03252281
- Plan-based adaptive query processing evaluation, arXiv 2511.16455 (not read): https://arxiv.org/abs/2511.16455
- Selinger, Astrahan, Chamberlin, Lorie, Price, "Access Path Selection in a Relational Database Management System", SIGMOD 1979. Scanned; read page by page (section 13). Copy: https://people.csail.mit.edu/tdanford/6830papers/selinger-access-path-selection.pdf
- Engines (section 16), read from the official pages: DuckDB join operations, explain and tuning guides (2.0 docs): https://duckdb.org/docs/2.0/guides/performance/join_operations.html ; ClickHouse join execution, query-plan settings, use-statistics, join algorithms: https://clickhouse.com/docs/concepts/features/operations/select/join-execution.md ; MonetDB MAL optimizers and design overview: https://www.monetdb.org/documentation/dev-guide/monetdb-internals/mal-optimizers/ and https://www.monetdb.org/documentation/dev-guide/monetdb-internals/design-overview/ ; SQLite optimizer overview, query planner NG, ANALYZE: https://www.sqlite.org/optoverview.html , https://www.sqlite.org/queryplanner-ng.html , https://www.sqlite.org/lang_analyze.html
- Graefe (1993, 1995), Moerkotte and Neumann (2006), Markl et al. (2004): from memory, not checked.
