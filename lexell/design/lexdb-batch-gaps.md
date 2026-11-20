# lexdb: the row-only gaps, moved to batches

Status: plan, 2026-11-20, on main `ab9c8a3e`. Source: the review of the
batching commits e1cc5c26, 19e016f7 and f82e0a94, and the construct
inventory [lexdb-constructs.md](lexdb-constructs.md) (sections 1-5 and 8).
Each item below is a construct that runs row by row today only because no
batch code exists: it has no row semantics a batch would break. The
constructs with real row semantics (sequences, locks, RETURNING, ON
CONFLICT, MERGE clause order, feedback, MATCH_RECOGNIZE: constructs
section 8, items 1-11, 13) are out of scope.

Every item follows the same rules (section 2). Section 3 says how the work
is run: two Sonnet agents at a time, each in its own worktree, reviewed and
merged by the coordinator. Section 4 is the per-item status, which each
agent updates before it reports.

## 1. The items

Sizes: S under a day of agent work, M one to two slices, L three or more
(deliver slice by slice; each slice mergeable).

### Item 1. An index's rows where the read may stop early (S-M)

Today: `lexdb_plan.scanBatches` and `firstBatches` refuse `p.index >= 0 &&
!covers && stops`, so `SELECT * FROM t WHERE c > x ORDER BY c LIMIT 20`
(and DESC, the app's "latest n") reads index entries then each row by key,
one at a time. The refusal exists because `fillIdxRows` reads BROWS
(1,024) entries and their rows per batch, far past a small LIMIT.

Approach: give `fillIdxRows` (and `fillIdxOnly`'s backward branch, for
symmetry) the cursor's batch size from e1cc5c26 (`Cursor.want`,
`nextWant`: 32 doubling to BROWS) when the level may stop, then drop the
refusal. The rows are fetched with `getMany` per chunk, in entry order, as
now. Check the join pipeline's first-table reader (`lexdb_pipe` around
`fillPickIn` in the join run) and `runScan`'s fallback (`cur = saved`)
with the smaller batches. A level that does not stop keeps BROWS.

Semantics: the rows and their order exactly as the row path's; a LIMIT
reads at most about twice its rows past the first batch.

Tests: batches on against off (`set lexdb_batch = off`) for ASC and DESC,
with and without a range, a filter that rejects most rows, LIMIT 1, 31,
32, 33, 1,025, OFFSET, a NULL-holding index column, an expression that
errors in a later batch. A counter test (`exec_big`'s style, or `Counts`)
showing a LIMIT 10 reads under 64 rows.

### Item 2. An index's IN list, `= ANY (array)` and IN (subquery) lookups (S-M)

Today: a primary key's list is one pass of `fetchMany` chunks (e1cc5c26:
`srcFor`'s `pts`, `pointsPick`, `fillPoints`). An index's list stays row
by row: `scanBatches` refuses `p.ins`, `p.inSub`, `p.inArr`, and
`firstBatches` admits lists for primary keys only. `inScans` makes an
index's values ranges `[key, succ(key))`, sorted and unique.

Approach: one pass over the sorted ranges, a chunk of keys at a time
(32 doubling to BROWS keys, as `fillPoints`), each chunk read with
`lexdb_access.rangeMany` (it already reads the ranges of many keys, in
key order, an index's entries decoded when they cover the columns used,
else their rows by `getMany`). Give it a `Cursor`-driven wrapper beside
`fillPoints` (`fillRanges`), a source mode in `srcFor`/`runScan` beside
`pts`, and admit index lists in `firstBatches` (forward only at first;
backward if `rangeMany` gives entries in reverse cheaply). A composite
primary key's prefix list (ranges, not points) takes the same path.

Semantics: rows in index order (an ORDER BY the index serves may be
elided); a value repeated in the list reads once; NULL in the list
matches nothing; `inMax` (IN subquery past IN_LOOKUP_MAX: the whole table)
unchanged.

Tests: as item 1 plus lists of 1, 31, 33, 2,000 values; values missing;
duplicates; NULL; a text index under a collation; IN (subquery) and
`= ANY ($1)` with an array parameter; ORDER BY the indexed column with a
LIMIT.

### Item 3. Aggregates beyond count, sum, avg, min and max (M)

Today: `lexdb_pipe.aggOps` takes only those five, and `pipeAgg` refuses
`sp.distinct`, `sp.order` and a non-exact collation, so a query with
`count(DISTINCT x)` (TPC-H q16), `string_agg`, `array_agg`, `bool_and`,
`bool_or`, `every`, `stddev*`, `var*`, T-SQL `COUNT_BIG`, Oracle
`LISTAGG`, or an ORDER BY inside an aggregate runs wholly in the row
engine: its scan, filter, join and grouping too.

Approach, in two slices:
- 3a. The row engine's accumulators (`Acc`, `accumulate`, `finish`, and
  `AggSpec`'s parts they read) move out of `lexdb_exec` into a new module
  `lexdb_agg`, used by both engines (a secret leaving exec). The
  pipeline's `AggSt` gains a generic call kind: per group an `Acc`, fed one
  value at a time from the batch column (the scan, filter, join and hash
  grouping stay batched; only the accumulate step is per value). This
  covers every aggregate the row engine has, with its exact semantics
  (DISTINCT sets, ORDER BY within the group, string_agg's separator,
  numeric stddev). `aggOps`/`pipeAgg` admit them; `count(*)`, `sum`, `avg`,
  `min`, `max` keep their typed kernels.
- 3b. Typed kernels where they pay: `bool_and/or/every` (an AND/OR over
  the column), `count(DISTINCT int)` (a per-group integer set), stddev and
  variance over floats. Numeric stddev/variance stay generic unless the
  kernel gives the row path's exact digits.
- A non-exact collation's key (`groupKinds`) is out of scope; note it if
  it turns out cheap.

Tests: every aggregate batched against off, grouped and not, with NULLs,
empty groups, all-NULL groups, DISTINCT with duplicates across batches,
ORDER BY inside the call, FILTER, more than 1,024 groups and rows, errors
(a cast inside the argument that fails in a later batch). TPC-H q16's
checksum.

### Item 4. T-SQL `#tdiv`, `#tavg` and reg casts in batches (S)

Today: `fnRefOf` gives `FN_NONE` to `#tdiv` and `#tavg` (T-SQL decimal
division and AVG's result scale), and `lexdb_bind.bindIn` refuses
`K_REG` casts (`::regclass`, `::regtype`), so any expression or aggregate
holding them runs row by row: every decimal division and AVG from a TDS
client.

Approach: `#tdiv` as a `lexdb_lib` function entry (its scale rule is the
row path's; reuse that code, do not re-derive it). `#tavg` as an
aggregate kind in the pipeline (avg with T-SQL's result type) or through
item 3a's generic kind if 3a lands first. Reg casts need the catalog: a
function reached through the pipeline's `Up` hook (`lexdb_pipe.Ctx`),
evaluated per distinct value of a batch; leave them row by row if that
needs more than the hook offers, and say so in section 4.

Tests: a `tds_*`-style query set (decimal `/` with mixed scales, AVG over
int, decimal, money-like columns, NULLs, a divide by zero in a later
batch: 8134), batched against off.

### Item 5. Uncorrelated subqueries inside the row engine's batch conditions (S)

Today: the row engine's batch conditions (`bLevelPlan`, `bCondNode`) bind
through `bxOf`, which does not bind `#sub`, so a condition holding an
uncorrelated scalar subquery (E31), `x op ANY/ALL (subquery)` (E37) or an
IN (subquery) set probe (E35) is left to the row path for every row of a
level the pipeline does not take. The pipeline already binds them
(`lexdb_bind.bindSubs`, `BX.Sub`).

Approach: bind them in `bCondNode` as the pipeline does: the subquery's
value (or set) computed once per run, before the level's batches
(`RUN_ONCE`), and the condition compiled over it. Find the places the row
engine computes these once today (`runSub`, `SubRes`) and hand their
result to the batch condition.

Tests: queries the pipeline refuses (a lock, a LATERAL later, DISTINCT
ON, WITH TIES, a correlated output) whose first table's WHERE holds such
a subquery, batched against off; a subquery giving no row, two rows
(21000), NULL.

### Item 6. A derived table, view, CTE, VALUES, function scan or catalog relation as the first table (M-L)

Today: `tableRead` refuses a virtual level (`lv.virt()`), so `pipeShape`,
`aggShape` and `bLevelPlan` refuse a query whose first level is held rows
(F10-F16, F19, F20): `SELECT ... FROM some_view WHERE ...` runs the view's
query in batches, then the outer query over its rows row by row.

Approach: a pipeline source over held rows: a `PPlan.Scan` variant (or a
new `PRows` source) that cuts the level's rows (`[][]Val`, from
`runFrom`/`materialize`/`execSrf`; `lazySeries` for generate_series) into
batches of BROWS, columns typed by the sub's output kinds
(`lexdb_rows.pipeKind` over its OutCols; a value a column cannot hold
gives way to the row path as today). Filter, project, aggregate, sort and
joins then run over it as over a table. Slice 6a: one held level alone
(filter/project/agg/sort); 6b: held rows as the first level of a join.
Later levels that are held rows already join by a hash (`JH_ROWS`).
Predicate pushdown into the derived table is a rewrite (R work), not this
item.

Tests: views, CTEs used once and twice, VALUES, generate_series,
unnest, a catalog relation (`pg_class`), each with filter, aggregate,
ORDER BY LIMIT and a join, batched against off; texts, NULLs, mixed
numeric scales in a VALUES column.

### Item 7. The joins of `UPDATE ... FROM`, `DELETE ... USING` and MERGE (M)

Today: these statements build a `Query` without a `Sel`, so they get no
levels program (`levelsProg`, `Query.jp`): their joins run per row; only
the first table's conditions batch (`batchLevel`).

Approach: build the join's levels program for the DML's query (the
`levelsProg` path: `scanArm`, `joinsOver`, `compileLevels`) and run it
with `runLevelsProg`, the DML consuming each joined row as it consumes
`runQuery`'s today. Keep: one change per target row (`onceEach`: the
first match), `rs.writes` (no index-to-scan switch), the target's row
locks, MERGE's join kind from its clauses (`mergeFrom`), the
statement's reads noted. MERGE's RIGHT/FULL shapes stay row by row unless
item 9 has landed.

Tests: `joinwrite_queries` and `merge_queries` shapes batched against
off; a join that matches a target row twice; a hash join over more than
1,024 source rows; FK and CHECK errors in a later batch; `exec_dmlscale`.

### Item 8. Write-side probes in batches (M-L)

Today: `INSERT ... SELECT`, multi-row VALUES and COPY check each row's
foreign keys (`childSide`: a parent lookup per row) and unique indexes
(`ixClash`) one row at a time. Also open since 2026-11-16: an INSERT ...
SELECT into a table with a secondary index and a unique text index grows
superlinearly (30k rows 2.9 s, 100k rows 53 s); find its cause first.

Approach: slice 8a, the superlinear case: profile (LXL_NATIVE_MAP symbol
map, not a gcc build) and fix. 8b: gather a chunk of rows (up to BROWS)
before writing, probe their FK parent keys together (`fetchMany`, sorted,
a key repeated read once), then write the rows in order, each with its
own checks as now; an FK miss reports the first failing row in row order
(the same error and row as today). Unique checks stay per row unless a
chunked probe is plainly equivalent. Deferred constraints, ON CONFLICT,
RETURNING, sequences and defaults stay per row and in order.

Tests: `exec_fkey`, `exec_unique`, `exec_copy*`, `exec_insertsel` pass;
new: an FK miss in row 700 of 2,000 reports row 700's error; self-
referencing FK inside one statement (a parent inserted earlier in the
same chunk must be seen); deferred FK unchanged.

### Item 9. FULL JOIN, CROSS JOIN without a key, more than one RIGHT JOIN (M)

Today: `joinsOver` and `lexdb_pipe.joinOps` refuse FULL joins (F7), a
level with no hash key, whole-key lookup or range (F4), and a second RIGHT
JOIN (only one per query batches, by a hash).

Approach: FULL as LEFT plus the RIGHT tail the pipeline already makes
for one RIGHT JOIN (unmatched build rows after the probe); then lift the
one-RIGHT limit (each hash build keeps its own matched marks). CROSS JOIN:
a nested loop over batches, the inner level's rows held once (it is small
or the plan would not choose it), each probe batch crossed with them in
chunks of BROWS output rows; its post-conditions as a join's.

Tests: `exec_join`, `exec_rightjoin`, `joinusing_queries` (FULL USING's
COALESCE), batched against off; FULL with NULL keys on both sides, empty
sides, duplicates; CROSS JOIN of 0, 1 and 3,000 rows; two RIGHT JOINs.

### Item 10. Window functions (L)

Today: window values are computed row by row over held rows (`winValues`,
`winPartition`, `frameBounds`); only the input rows batch (`winBatch`).

Approach: a new module `lexdb_window`. Slice 10a: the input sorted by
(partition, order) with `lexdb_sort` over batch columns, partitions and
peer groups found over the sorted key columns, and the rank family
(`row_number`, `rank`, `dense_rank`, `percent_rank`, `cume_dist`,
`ntile`) and `lag/lead/first_value/last_value/nth_value` with the default
frame, as columns. 10b: aggregates over the default frame (running sums,
counts, min/max per peer group) and `ROWS BETWEEN n PRECEDING AND m
FOLLOWING` (prefix sums for sum/count/avg; a deque for min/max). 10c: what
is left (RANGE with offsets, GROUPS, EXCLUDE) per partition through the
row code, so every window query takes the new path. The output order and
the values must be the row path's, NULLs and ties included.

Tests: `exec_window` passes; batched against off for every function,
frames, PARTITION BY none/one/two columns, ORDER BY with ties and NULLS
FIRST/LAST, more than 1,024 rows per partition and across partitions.

### Item 11. Set operations: what is left (S-M)

Today: a set operation with ORDER BY or OFFSET (D4) holds both parts and
sorts with `sortOutRows`; INTERSECT ALL and EXCEPT ALL combine held rows
(`combine`); the distinct streams (f82e0a94) key each row with
`rowKeyIn` over values made by `obRow`.

Approach: 11a, ORDER BY [LIMIT] over a set operation: feed the parts'
batches (or rows) into the pipeline's sort (`lexdb_sort`, top-N with
LIMIT), as a SELECT's sort is fed; OFFSET counted after it. 11b,
INTERSECT ALL and EXCEPT ALL streamed: the right part's keys counted
(`Map[str, int]`), then the left's rows given while their count lasts
(INTERSECT ALL) or past it (EXCEPT ALL), in left order. 11c, typed keys:
build a row's key from the batch columns directly (the int and text
column fast paths), not through `obRow`'s values. Consider moving the
set-operation runners (`runSet`, `runSetTo`, `runSetKeys`, `setPart`,
`giveSet`, `combine`) out of exec into a `lexdb_setop` module.

Tests: `exec_setstream` extended (held against sink, 60+ shapes), with
ORDER BY ... LIMIT across parts, OFFSET, ALL forms with duplicate counts
on both sides, NULLs, texts under a collation.

### Item 12. GROUPING SETS, ROLLUP and CUBE (M)

Today: `aggShape` and `opsOf` refuse `sel.gsets`; `GROUPING()` (E46) with
them.

Approach: one pass over the batches feeding one hash table per grouping
set (each `AggSt` keyed by its set's columns, the absent keys NULL),
`GROUPING(...)` a constant per set; the groups given in the row path's
order (set by set as the row path gives them), HAVING and the outputs as
today's views over the groups. Depends on item 3 for the generic
aggregates (else only the five kernels' calls are admitted).

Tests: `forms_queries`' grouping sets cases; ROLLUP of two and three
columns, CUBE, `GROUP BY DISTINCT`, `()`, GROUPING() in the select list
and HAVING, NULL key values against a grouping NULL, batched against off.

## 2. The rules every item follows

- **Same results as the row path.** Rows, order (where the query defines
  one, and where tests rely on the row path's), types, errors (the same
  SQLSTATE and the same first failing row), and the counters tests read.
  Every new path is tested against `set lexdb_batch = off` (or held against
  sink) over shapes that cross batch edges (1,023 / 1,024 / 1,025 rows,
  and the 32-doubling sizes), NULLs, empty inputs, and an error in a
  later batch.
- **Never move a test expectation to accept a slowdown.** e1cc5c26 moved
  `exec_big`'s backward chunks from 0 to 20 and called it on purpose; it
  was a regression (ab9c8a3e). A changed expectation needs a reason in the
  commit message that says why the new number is right.
- **Modules.** New executor code goes in `lexdb_pipe`, `lexdb_access`,
  `lexdb_plan`, `lexdb_sort` or a new module (`lexdb_agg`,
  `lexdb_window`, `lexdb_setop`), not `lexdb_exec`; move a secret out of
  exec where the item touches it. Report exec's line count before and
  after. A new module must pass `tests/lexdb/imports.py` (the suite prints
  "imports: ok").
- **Build and test natively.** Compiler:
  `/home/chris/Work/lexell/lexell/compiler/out/lxlc` (the main checkout's;
  do not rebuild it). Tests: `flock -s ~/tpch/.bench.lock env LXL_NOCACHE=1
  python3 lexell/tests/lexdb.py --compiler
  /home/chris/Work/lexell/lexell/compiler/out/lxlc -j 3` from the worktree
  root (a test name as an argument runs it alone). Never the gcc path.
  The whole suite must pass before reporting.
- **Measure in-process, pinned, one at a time.** A scratch program (not
  committed) that times shapes with batches on and off and against the
  branch's base, `taskset -c` on the CPU the brief gives, under the
  exclusive lock: `flock ~/tpch/.bench.lock taskset -c N program`. Tests
  and builds take the lock shared (`flock -s`), so a timing never overlaps
  another agent's suite, a build or a TPC-H run; never run a test or a
  build inside an exclusive section (it deadlocks). Keep a section short
  (seconds to a minute) and interleave base and branch inside it (base,
  branch, base, branch) so drift cancels. Warm the table first (the first
  query after a load pays the cache). The coordinator runs TPC-H; agents
  do not.
- **Lexell notes.** A closure that borrows a local keeps the borrow while
  it is in scope: pass the closure inline (`f(..., fn(...) {...})`) rather
  than binding it to a `let` and using the local after. `&fn` parameters
  take the closure itself, not `&closure`. Borrowed `[]&str` from
  `strings.split` keep their source borrowed.
- **Commits.** On the worktree's branch only; never main, never push.
  Messages in the repo's style (`lexdb: ...`, what changed, measured
  numbers, suite count), ending with
  `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`. Update
  lexdb-constructs.md's rows for the constructs changed, and this note's
  section 4 for the item, in the same branch.
- No background processes left running.

## 3. How the work is run

Two Sonnet agents at a time, each in its own git worktree branched from
main as it is when the agent starts. The coordinator (Opus) reviews each
branch: reads the diff, checks it against the rules, runs the gate,
merges into main and pushes.

Gate per merge (lighter than a full benchmark round): the suite on the
merged tree; TPC-H SF1 once on the branch build (`TPCH_ONLY=lexdb
bench/tpch/run.sh BIN ~/tpch-w/int 1 1` under `flock ~/tpch/.bench.lock`),
22 checksums equal to main's stored run, and no total regression past
1.5% against it (`~/tpch-w/int/out-main-<commit>`, refreshed after each
merge). Point selects only for items that touch per-statement planning
(5, 7).

Queue, two slots; pairs chosen so their files overlap little:

| Slot A | Slot B |
|---|---|
| 1 + 2 (access, plan, pipe sources) | 4 + 5 (bind, lib, the row engine's batch conditions) |
| 3 (aggregates: lexdb_agg, pipe AggSt) | 11 (set operations) |
| 6 (held rows as a pipeline source) | 8 (writes) |
| 7 (DML joins) | 12 (grouping sets; after 3) |
| 9 (FULL, CROSS, RIGHT joins) | 10 (windows) |

A slot takes its next item when its branch is merged. An item of size L
reports per slice; each slice is reviewed and merged before the next. A
branch that main has moved under is merged with main by the agent (and
the suite rerun) before review.

## 4. Status

| Item | Branch | State |
|---|---|---|
| 1 + 2 | `worktree-agent-a4419715dc0aa104e` (`1d3f4fe3` item 1, `23016a1c` item 2) | merged (f8758e0e; TPC-H 1.008 of fef54780, checksums equal). Item 1: `IxRead.small` / `PScan.stops`, `fillIdxRows` and `fillIdxOnly` take the cursor's 32 doubling to BROWS where the read may stop, the `index >= 0 && !covers && stops` refusal dropped from `scanBatches` and `firstBatches`; test `exec_idxlimit`. Item 2: `lexdb_access.fillRanges` (over `rangeManyIn`), `Src.multi`, `lexdb_pipe.rangesPick`, `firstBatches` admits an index's list (both directions) and a composite primary key's prefix list (forward); test `exec_idxin`. Left: the aggregate run's and the join run's first-table readers read a list one range at a time (batches per range), not chunked; a joined table's list (`scanBatches`) and `bLevelPlan` still refuse lists; a pure PK forward range with LIMIT still reads BROWS (not the doubling); a single key whose rows pass 8 MB falls to the row path |
| 3 | | not started |
| 4 | `worktree-agent-adb56b613f1267a19`, 511ee7d2 | merged (fef54780; TPC-H 0.982 of main, checksums equal): `#tdiv`/`#tavg` are `lexdb_lib` entries (`tdivFn`, `tavgFn`; eval calls `tdiv`/`tavg` direct), bound by `fnRefOf`; test `exec_tsqlbatch`. Left: reg casts (`::regclass`, `::regtype`): `regCast` reads the catalog through the session's `SeqEnv`, which `Ctx`/`Up` do not carry (stateless entries; workers' contexts would each need one) |
| 5 | `worktree-agent-adb56b613f1267a19`, 8b6a488f | merged (fef54780): `bSubNode`/`condSubVals`/`subOnce`/`subCalls` in `lexdb_exec`: a first-table condition holding an uncorrelated scalar subquery, NOT IN, `x op ANY/ALL (subquery)` or EXISTS binds with `bindSubs` over the values `prepareIn` copies into `Mats.ce.subs`; test `exec_subbatch`. Left: a positive IN / `= ANY` (subquery) is a semi join level, not a condition, so unchanged; conditions of later levels (`post`, k > 0) |
| 6 | | not started |
| 7 | | not started |
| 8 | | not started |
| 9 | | not started |
| 10 | | not started |
| 11 | | not started |
| 12 | | not started |
