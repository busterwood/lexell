# lexdb: the row-only gaps, moved to batches

Status: plan, 2026-11-20, on main `ab9c8a3e` (item 11 done on its branch, section 4). Source: the review of the
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
| 3 | worktree-agent-afe32cba03d1569d1 | merged (8ce8e766; with item 11 TPC-H 0.991 of f8758e0e, q16 0.84, checksums equal) (2026-11-20, from main 32e8ac9e): 333a804a (3a: `lexdb_agg`, the generic `BA_GEN` call kind, every aggregate admitted, DISTINCT and ORDER BY in the call too), 17a5fd2a (3b: kernels `BA_AND/BA_OR`, `BA_CNTD` for `count(DISTINCT int)`, `BA_VAR` for float columns; a call the typed kernels refuse, such as a float's sum or avg, now takes the generic step instead of the whole aggregate going row by row), 418b60cf (an op code in `add`). Suite 192/192. `lexdb_exec` 23,765 -> 23,582 lines, `lexdb_agg` 270. 200,000 rows, exclusive lock, base -> branch ms: `count(distinct k)` 32 -> 4, grouped (50) 51 -> 8, 5,000 groups 62 -> 15; `bool_and/or` 34 -> 4; `stddev/variance(float)` 73 -> 15; `string_agg` 74 -> 37; `string_agg ... order by` 146 -> 109 (the sort); `count/sum/avg/min/max` unchanged (2, 4, 6, 16, 26 ms); `count, sum, avg(float)...` 106 -> 40. Left: a non-exact collation's argument or key (`pipeAgg`, `aggShape`) stays row; numeric and integer `stddev/var*` and `count(DISTINCT text)` are generic (no kernel); the row-by-row grouping fallback (a key the batches do not evaluate) is about 3% slower than before; TPC-H q16 not run (coordinator). Within one batch a call's FILTER, argument, separator and keys are evaluated each over the whole batch in turn, so where two of them fail on different rows the error is the first step's, not strictly the first row's (as before for FILTER and argument). |
| 4 | `worktree-agent-adb56b613f1267a19`, 511ee7d2 | merged (fef54780; TPC-H 0.982 of main, checksums equal): `#tdiv`/`#tavg` are `lexdb_lib` entries (`tdivFn`, `tavgFn`; eval calls `tdiv`/`tavg` direct), bound by `fnRefOf`; test `exec_tsqlbatch`. Left: reg casts (`::regclass`, `::regtype`): `regCast` reads the catalog through the session's `SeqEnv`, which `Ctx`/`Up` do not carry (stateless entries; workers' contexts would each need one) |
| 5 | `worktree-agent-adb56b613f1267a19`, 8b6a488f | merged (fef54780): `bSubNode`/`condSubVals`/`subOnce`/`subCalls` in `lexdb_exec`: a first-table condition holding an uncorrelated scalar subquery, NOT IN, `x op ANY/ALL (subquery)` or EXISTS binds with `bindSubs` over the values `prepareIn` copies into `Mats.ce.subs`; test `exec_subbatch`. Left: a positive IN / `= ANY` (subquery) is a semi join level, not a condition, so unchanged; conditions of later levels (`post`, k > 0) |
| 6 | `worktree-agent-a57374a89398cf617`, 43f32f1e (6a), 6873e7e0 (6b) | merged (6545bf67; TPC-H 1.007 of c4ce9df1, checksums equal; q7/q8 +3-12% across two noisy runs, an in-process A/B of a derived-table aggregate is 10% faster: at the next gate (10a) q7 and q8 were back to their pre-item-6 times: noise); done on the branch, not merged. New module `lexdb_held` (below `lexdb_pipe`; `tests/lexdb/imports.py` knows it): held rows (`[][]Val`, from `runFrom`/`execSrf`/`catRows`) cut into batches of BROWS by the columns' kinds (`putRef`: rows borrowed, never moved, so a join that gives way as a whole leaves them for the row engine), or an integer `generate_series` (smallint, integer, bigint; `lazySeries`) cut into batches as it is made (`Series`, never held: no rows are taken). exec: `heldRead`/`firstRead` in `pipeShape` and `aggShape`, `scanArm` marks `PScan.held` (its subquery's number), `pipeSrcQ` gives `lexdb_pipe.srcHeld`, `runPipe` and `pipeGroups` give the run the rows by reference; exec grew 23,793 to 23,859 lines (glue only). pipe: `runScan`, `aggBatches`, `aggRows`, `readRows` (a join's first table; `eachChunk` shared with its row-by-row branch) read held rows beside a table's ranges; fewer than `HELD_BATCH` (64) rows go row by row straight from the held row (`rowsHeld`, `aggRows`), a value a column cannot hold gives its batch up and the reader goes on row by row from the batch's start; `compile` narrows the scan's columns (`lexdb_plan.needs`). Test `exec_held` (539 queries against off). Measured: view WHERE + GROUP BY, 200,000 rows, 80 to 51 ms; CTE ORDER BY LIMIT 10, 119 to 88; `generate_series(1, 1000000)` WHERE + sum 248 to 18 ms; VALUES of 10,000 grouped 22.6 to 18.7; view joined to t by lookup 151 to 58; series joined to t 195 to 40. Tiny inputs: below 64 rows instructions per statement equal base (-30% to +0.7%), PK point select within noise (+0.06 to +0.3%); a join whose held first level has under 64 rows (3-row VALUES, `unnest($1)` of 3, a 6-row series joined to a table) is decided at run time, after the subqueries ran and before anything is given, for the row engine as before item 6: `runPipe`/`pipeGroups` give `batErr`, the subqueries' results kept in `Run.pre`/`Share.pre` for `runSubs` (not run again), instructions per statement +1.0 to +1.3% of base (+25-30% before: 76.7k, 89.4k, 112.3k base); 64 rows and more take the batched join. Left: a recursive CTE's working table (`Level.work`) as first level, LATERAL, locks, semi/anti first levels, `levelsProg` (the row engine's joins) and `bLevelPlan` (its batch conditions) still refuse a virtual first level; a derived table holding a volatile call (not a CTE: those are cached and shared) that the pipeline gives up on after running it (a sort of a column of mixed kinds, `batErr`) is run again by the row engine, as a scalar subquery already is; a held first level is not pushed predicates into (R work) |
| 7 | `worktree-agent-aff456ec79a7d8b6f`, 7a50512f, 189a2ec9 (+ the design commit) | merged (bd6c08fa; TPC-H 0.967 of 5b1abb47, checksums equal; no TPC-H query is DML: noise); done on its branch (2026-11-20, from main 6545bf67), not merged. The joins of `UPDATE ... FROM`, `DELETE ... USING` (T-SQL's `UPDATE/DELETE ... FROM t JOIN s` too) and MERGE run as a levels program: `update`, `delete` (with FROM/USING) and `merge` (join not RIGHT/FULL) call `levelsProgQ` after `endScope`, which sets `Query.jp`; `runQuery` already ran it for the row engine. `levelsProg` is now `levelsProgQ(q, held)` over a Query (`scanArm` and `joinsOver` take `&Query`); with `held` a MERGE's first level may be rows the run holds (`heldRead`: a view, VALUES, derived table, series) and `runLevelsProg` gives `joinSrcsQ` their count. `fewSource` (merge): a held source of under 64 rows (`heldSmall`) drops `q.jp` and builds the hashes, so a small MERGE joins row by row as a SELECT's join does. Unchanged: `onceEach` (first match, same arrival order), `rs.writes`, `lockFound`, `firstN` (TOP, MERGE's first-clause rule), RETURNING/OUTPUT, FK/CHECK. A plain DML without FROM/USING (one level, or semi levels of a WHERE subquery) is untouched. Test `exec_dmljoin` (62 statements, each rolled back, batches off against on: tag, RETURNING rows, error with detail, a digest of the tables after; hash and primary-key lookup joins of 3,000 rows, a view, VALUES and derived-table sources of 1,100 to 1,500 rows, a target matched twice, FK 23503 / CHECK 23514 / 21000 / 23505 in a later batch, ON DELETE CASCADE, T-SQL TOP, OUTPUT, LEFT JOIN, MERGE TOP and $action; counter `joinCounts()[0]` 62 runs with batches on, 0 with them off). Suite 202/202. `lexdb_exec` 23,638 -> 23,658 lines (glue only). 200,000-row target, in-process, pinned CPU 4, exclusive lock, base -> branch, interleaved: UPDATE ... FROM 100,000 matched 365 -> 222 ms, DELETE ... USING 50,000 rows 270 -> 118, MERGE of 100,000 source rows (half matched) 250 -> 178; batches off unchanged (371-381, 195-228, 247-258 against 393-409, 226-233, 273-276); single-row UPDATE by primary key 125.2k instructions per statement both. Left: MERGE with BY SOURCE (RIGHT/FULL join) is row by row until item 9; a held MERGE source under 64 rows is row by row; DML without FROM/USING reads its first table through `batchLevel` as before; a lookup join (a joined table read by primary key per row) is batched but its rows are looked up one at a time as for a SELECT; TPC-H not run (coordinator) |
| 8 | `worktree-agent-a6212d16a9ebd09a1`: `bca6f411` (8a), `f3847b09` (8b) | merged (c6344eb6; TPC-H 1.005 of 2e270f70, checksums equal). **8a** (the superlinear INSERT ... SELECT): the cause was `Txn.ownRange` in `lexdb_store`: it kept a written tree's keys in one sorted list and, when keys had been added since its last call, merged them in by copying every key into a new list (profile at 20k rows: `ownRange`, `malloc`, `rt_free`, `rt_str_cmp`, `memcpy` about 75% of the time). A unique index's check (`ixClash`) scans the index's tree after each row's own entry was put, so every row re-merged the whole list: quadratic in the rows (a secondary index alone does not scan, so it needs a unique index; the primary key's check is a `get`). Fixed in `ownRange`: the keys are in sorted runs, each less than half the one before (`ownFold`, `Txn.runs` for `sortedKeys`); a call reads the fewer than 64 keys added since as they are, merging them with the runs' keys in range, and folds them in once they are 64 or more, so a key is merged O(log n) times in all; the rows and their order are unchanged. Sim disk, pinned, 10k / 30k / 100k rows into a table with a secondary index and a unique text index: 695 / 5,590 / 97,600 ms before, 90 / 182 / 590 ms after (the sim disk's `File.grow` and `flush` are now over half of what is left). Test `store_ownrange` (against a model: bursts, a scan after every put, a savepoint undone, a range delete; a time ratio that fails at the old code); `exec_fkchunk` times the 30,000 rows (2.5 s bound; 0.2 s measured, 5.6 s before). **8b**: `lexdb_fkprobe` (new module, 161 lines) and `lexdb_access.hasMany`; `lexdb_exec`: `childSide` asks the statement's probes first, `fkProbes`, `fkAhead`, `plainDefaults`, `insertSelRows` (INSERT ... SELECT holds up to a chunk), `insertRows` (VALUES chunks from literals and parameters), `copyStmt` (records parsed ahead), `Upsert.fk`; exec 23,793 to 23,955 lines. A miss was never an immediate error (it waits for `fkFinish`, which looks again), so the chunk only adds to what is known to be there, and a key it does not know is looked up as before: same errors, SQLSTATEs and failing rows. 200,000 rows (sim disk, pinned, base then branch twice): INSERT ... SELECT with one FK 474 to 371 ms (no FK: 335), two FKs 630 to 452, random keys of a 300k-row parent 624 to 544, COPY with one FK 437 to 357 (no FK: 173); VALUES in 1,000-row statements 472 to 460 (no FK: 353: the parse dominates, the keys are distinct in a statement); single-row INSERT about 133,500 instructions per statement either way (noise 1.5%). Test `exec_fkchunk` (the output is the same at the base). Left: unique checks per row (`ixClash`); an INSERT ... SELECT whose table has a serial, identity or function default for a column it does not give is not chunked (`plainDefaults`; the query's own `nextval` calls would interleave differently), nor is the `stmtReads` branch (a query reading its target); a foreign key to a unique index (not the primary key) is checked per row; VALUES keys that are expressions (not literals or parameters) are looked up per row; `bulkStmt` (T-SQL INSERT BULK) and UPDATE's `childSide` unchanged; the per-row part of the check (the key encoded again, a hash probe) is most of what is left of the cost |
| 9 | | not started |
| 10 | `worktree-agent-a980f5bfcb9611e69`: `5c04dcc3` (10a); `worktree-agent-ad101079d964ba2f4`: `5e70af11` (10b) | merged 10a (5b1abb47; TPC-H 1.013 of 6545bf67, noise), merged 10b (MERGE_10B); **10a done** (2026-11-20, from main c4ce9df1); **10b done** (2026-11-20, from main 5b1abb47; the 10b paragraph follows), **10c done on its branch** (2026-11-20, from main b0196294, not merged; the 10c paragraph is at the end of this row). New module `lexdb_window` (538 lines): `covers` (a call it takes), `sortRows` (the rows' permutation by partition then order over lexdb_sort keys, read from the rows' own columns where the key is a plain column, else from the values the engine evaluated; where partitions and peer groups start, by position), `values` (a call's value as a column: row_number, rank, dense_rank, percent_rank, cume_dist, ntile, lag, lead, first/last/nth_value under the default frame, ROWS UNBOUNDED PRECEDING to CURRENT ROW, or the whole partition's; arguments by `ArgSrc`: a rows' column, a constant, or the engine's hook `ev(arg, row)`, evaluated at the row the row path reaches, so errors are the same). Moved out of exec into it: `WinPlan`, `WinRow`, `winCmp`, `winSpecText`, `frameBounds`, `firstNot`, `rangeTarget`, `excluded`, `offInt` (exec 23,572 to 23,509 lines). In `lexdb_exec.winValues`: `fast` = batch on and every call covered; then per window group the key columns (`KeyCol`) go to `sortRows` and each call's `values` fills a column (`cols`, put in the rows' value arrays at the end, `byCol`); a key of mixed kinds (`sortRows` false) runs that group through the old code. `lexdb_sort.skIntOf` is public. `imports.py`: WINDOW rules (imports base, sql, ops, sort, agg; only exec imports it). Test `exec_winbatch` (825 + 80 queries against `lexdb_batch = off`; the counter `lexdb_exec.winRuns`). Suite 201 of 201. 200,000 rows, exclusive lock, base to branch ms: row_number 134 to 118 (50 partitions) and 151 to 132 (20k), rank 134 to 117 / 163 to 144, lag 150 to 141 / 174 to 154, lead(v,2,0) 158 to 140, first_value 152 to 137 / 162 to 147, dense_rank+ntile 180 to 137, last_value (whole partition) 146 to 132, top 3 per partition 128 to 127 (50) and 138 to 133 (20k). Left for 10b/10c: aggregates over frames (`winPartition`'s `w.agg` branches: running accumulators, prefix sums, deques), frames with offsets, GROUPS, RANGE with offsets, EXCLUDE (`frameBounds`, `excluded`, `winPartition` stay the row code; a query with any such call takes the old path whole). Hand-over: new calls go in `lexdb_window.covers` (add a function code, a branch in `byArgs`/`ranks`) and take their frame from `Sorted` (`partBreak`, `peerBreak`: positions); 10c can run the rest per partition through `winPartition` (needs `grp/gStart/gEnd` from `peerBreak`, as it builds them now) so that one query mixes both. What is left of the time at 200,000 rows is the input rows (`winBatch`: a `[]Val` per row), the per-row value arrays and the outputs (`winValues`' caller loop with `bxEval` per row), not the window code: next is giving the window values to the outputs as columns, and a radix sort of wide keys (lag's two-key sort is about 20 ms of its 140). Not changed: a window in a grouped query uses the same path (its aggregates are in `WinRow.aggs`; keys and arguments that read them are evaluated by the hook). **10b** (`5e70af11`, one commit, suite 203 of 203): `lexdb_window.covers` takes window aggregates (`aggCovers`): count(*), count, sum, avg, min, max, bool_and/bool_or/every, array_agg and the variances (not string_agg, not DISTINCT/FILTER/ORDER BY in the call) over ROWS with any bounds and constant or parameter offsets, and over RANGE without offsets (UNBOUNDED/CURRENT ROW; peers), none excluded. `values` now takes the frame offsets (`so`, `eo`, from `frameOff` in the glue) and for an aggregate calls `aggValues`, per partition: `starPart` (count(*): the frame's size), `growPart` (frame from UNBOUNDED PRECEDING: one `lexdb_agg` accumulator, rows added as the frame's end passes them, value made again only when that end moves: the row path's own algorithm, so every aggregate, float order and numeric scale included), `slidePart` (other frames: modes M_COUNT and M_INT keep a count and an integer total, rows leaving subtracted and entering added, exact while |value| times the frame's most rows (`frameMax`) stays under 2^62, else (or on a value that is not an integer) the call drops to M_SLOW from that frame on, which adds the frame's rows again in order as the row path does, so the overflow error and its row are the row path's; M_DEQ for min/max keeps a monotone deque of one kind of value (`kindTag`, `cmpAgg`; ties as the row path keeps: the last, the first under a collation); anything else is M_SLOW). `fastAdd` is the integer and double-precision (sum) step with `lexdb_agg.add`'s checks and errors, everything else goes through `admit` and `add`. `frameOf` is `frameBounds` for ROWS and RANGE without offsets. An argument is evaluated only for rows that are in some frame, in the row path's order, so an error in a row no frame has is none, and the first error is the row path's; an argument that is a column of the rows is read from them without a copy (`direct`, `valAt`), any other is evaluated by the engine's hook (`eval`, plainly, as `accumulate` does, not `evalX`). Glue: `winValues` computes `frameOff` per covered call and `lexdb_window.argSrcs` (moved out of exec) gives the argument sources; `lexdb_exec` 23,575 to 23,556 lines. `lexdb_agg`: the `OP_*` codes are public. Two row-path faults found by the new test and fixed in both paths: `winPartition`'s running aggregate used -2 as its "end moved" sentinel, so a first row whose frame ends at -2 (END n PRECEDING with n = 2) kept NULL (count gave NULL, not 0); and `frameBounds` added a ROWS/GROUPS offset to k unchecked, so an offset near 2^63 trapped (now clamped to 2^40, past any partition). Tests: new `exec_winagg` (about 2,100 queries against batches off: 612 aggregate x spec x frame rotations, 992 frames x kinds, 424 overflow, 34 mixed, 9 not covered, 32 errors, 25 sizes, by hand), `exec_winbatch`'s 13 aggregate queries that it listed as not covered moved to exec_winagg as covered (9 stay: offsets on a value function, GROUPS, EXCLUDE, RANGE with offsets, string_agg, FILTER) and its counter query uses a call still not covered; `exec_window` and `exec_batchsort` unchanged. 200,000 rows, exclusive lock, pinned, base to branch ms (50 partitions / 20k): sum running with peers 180 to 137 / 217 to 157, count(v) running 230 to 163 / 255 to 174, avg 3 preceding and 3 following 302 to 196 / 332 to 217, sum same frame 305 to 171 / 324 to 172, min 100 preceding to current row 1,205 to 147 / 280 to 171, max 1,244 to 183 / 308 to 185, count(*) over (partition by k) 97 to 84 / 122 to 93, sum(float) 3/3 341 to 242 / 342 to 244, sum(numeric) running 213 to 182 / 246 to 199, sum over the whole partition 158 to 122 / 201 to 153. Left for 10c: GROUPS, RANGE with offsets (`rangeTarget`, `firstNot`, needs the order key's values per partition, `ocols`), EXCLUDE, offsets on `first/last/nth_value` (ROWS frames; the value of the frame's first/last/nth row, by position: `frameOf` gives it), the aggregates not covered (string_agg, FILTER; DISTINCT and aggregate ORDER BY are refused by `winPlan`) and a mixed-kind order key (`sortRows` false), which still send the whole query (or that group, for the key) to the old code: the plan is `winPartition` per partition for the calls `covers` refuses, fed from `Sorted` (`grp/gStart/gEnd` from `peerBreak` as `winPartition` builds them), so one query mixes both, then delete `winValues`' old-path sort and `covers`' use as a whole-query switch. Hand-over: new aggregate shapes go in `aggCovers` and `slidePart`/`growPart` (a frame is `frameOf`'s a..b, both ends non-decreasing; keep that or the deque and the totals are wrong); the running sum could also be made with a typed int/float column kernel (growing sum costs about 270 ns a row, avg's Decimal division in `finish` about 100 ns of a sliding avg), and sliding float/numeric sums still add each frame again (O(rows x frame), as the row path; a numeric total with subtraction needs every value at one scale). The rest of the time is the input rows and outputs, as 10a said. **10c** (`worktree-agent-a6e2a818e83f81c8c`; every window call takes the batches' path): `lexdb_window.covers` and `aggCovers` are gone; `winValues` no longer chooses a path per query. New in `lexdb_window` (1,012 to about 1,680 lines): the frame code `FrameCtx`, `startFrames`, `nextFrame` (ROWS and the no-offset frames of RANGE/GROUPS by `frameOf`; GROUPS with offsets by the peer groups' starts; RANGE with offsets by the order key's values, the start and end seeked from where the row before found them: exponential then binary search, with the keys all of one kind, else `firstNot`'s bisection; both ends only move forward), `exclOf` / `clipLen` / `lastIn` / `nthIn` (EXCLUDE CURRENT ROW, GROUP, TIES as at most two intervals), `byFrame` (first/last/nth_value over any frame, offsets and EXCLUDE), and for the aggregates `Cells` / `cellEval` / `addAt` / `reAdd` / `reString` (a row's cell is its FILTER, argument and string_agg separator, evaluated once, when a frame first reaches the row, in accumulate's order: so FILTER and string_agg work on every frame and an error is at the row the row path reaches), `exclPart` (EXCLUDE: count(x), sum and avg of an integer column from prefix counts and totals with the excluded rows taken away; anything else adds the frame's rows again without the excluded, each cell evaluated when first touched, so the first error is the row path's), `growPart`/`slidePart`/`starPart` on `nextFrame` (count(*) minus the excluded; FILTER as NULL for the kept modes). The row path moved out of exec into the module: `sortVals` (the order by values, also used for keys of mixed kinds, which now feed the same column code instead of the old path), `rowValues`/`rowPart`/`accRow` (the old `winPartition` over the engine's hook) and `compute(batch, ...)`, so with `lexdb_batch = off` the row path is the tests' reference (it keeps `frameBounds`, `firstNot`, `excluded`, which the new frame code does not call except `firstNot`/`rangeTarget`). exec: `winValues` is one loop (sort by `sortRows` or `sortVals`, then `compute` per call, a column per call), `winPartition` deleted; `lexdb_exec` 23,576 to 23,342 lines. `argsOf` appends the FILTER to the call's arguments. `imports.py`: WINDOW may import `lexdb_access` (for `sortVals`' partition keys). Counters `winRuns` (calls by columns) and `winRowRuns` (calls by the row path). **Window shapes that still fall back to the old code: none** with batches on (every query's every call is made by `values`; the test counts 0 row-path calls over about 2,700 queries); the row path runs only with `lexdb_batch = off`. Two row-path faults fixed (both paths): `frameOff` compared a RANGE offset with the integer 0, so an interval offset (`RANGE BETWEEN interval '3 days' PRECEDING ...` on a date or timestamp key) always failed with 42883 (an interval is now compared with a zero interval; the same message at a negative one); nothing else changed in results. Tests: new `exec_winframe` (about 2,700 queries against batches off, rows and order compared as text: 600 GROUPS, 594 RANGE with offsets over int, float, numeric, date and timestamp keys with interval offsets, DESC, NULLS FIRST/LAST, NULL keys, mixed kinds; 373 EXCLUDE; 691 first/last/nth_value over offset frames; 410 string_agg/FILTER; 13 mixed-kind keys; 30 queries mixing every kind of call, grouped queries, joins, subqueries; 30 at the batch edges and with partitions of one row and of more than 1,024; 46 errors, 21 with value-specific messages so another row is another text, among them a first error not at the first erroring position under EXCLUDE; hand-computed values equal PostgreSQL's; counters: every call by columns, none by the row path, and the other way with batches off); `exec_winbatch` and `exec_winagg` unchanged but the 9 + 9 queries each listed as "not covered" now expect the batches' path ("10c" lines), and their counter lines 3 0 0 become 3 2 0 (the second query has a call that 10b/10a refused: now run by columns); `exec_window`, `exec_batchsort` unchanged. Suite 205 of 205. 200,000 rows, exclusive lock, pinned CPU 6, base to branch ms (50 partitions of 4,000 rows / 20,000 partitions of 10): sum RANGE 10 PRECEDING to 10 FOLLOWING over an int key 480 to 150 / 233 to 186; the same over a date key with int offsets (100,000 rows) 250 to 80 / 115 to 90; with an interval offset the base fails (42883), the branch 115 ms on 100,000 date rows and 220 ms on 200,000 timestamps (either partitioning); GROUPS 1 PRECEDING to 1 FOLLOWING 233 to 123 / 240 to 158; sum with EXCLUDE CURRENT ROW over 50 rows each way 1,465 to 135 / 295 to 126; EXCLUDE TIES over a running 30-row frame 560 to 112 / 275 to 150; nth_value over ROWS 5 each way 175 to 162 / 157 to 119; first_value over RANGE 10 each way 197 to 171 / 215 to 185; string_agg over 20 rows preceding 670 to 340 / 340 to 235; sum FILTER running 175 to 155 / 218 to 190; running string_agg (20,000 rows) unchanged (its cost is the result strings); branch only: sum EXCLUDE CURRENT ROW over the whole 4,000-row partition 109 ms (the row path is quadratic: not run), `count` EXCLUDE GROUP over the default frame 133 ms. The floor of about 105 ms at 200,000 rows is still the input rows and outputs (`winBatch`, per-row value arrays, `winValues`' last loop). Left: EXCLUDE with an expression argument (not a plain column), min/max, floats, numerics and string_agg adds the frame's rows again (O(rows x frame), as the row path, but without the engine's Env); a RANGE offset seek over keys of mixed kinds is the row path's bisection; the floor above (giving window values to the outputs as columns, a radix sort of wide keys); TPC-H not run (coordinator). |
| 11 | `worktree-agent-a4b1bd5f4d52444ba` (bdcef23d 11a, 883e640e 11b, 7041572a 11c, 446ac0c6 the move) | merged (2e270f70; TPC-H as item 3). 11a: ORDER BY [LIMIT] [OFFSET] over a set operation to a sink feeds the parts into `lexdb_pipe.setSort` (a `SortSt`: top-N of LIMIT + OFFSET), OFFSET alone skipped as the rows come; UNION ALL ORDER BY LIMIT 100 at 200,000 rows a side 188 to 21 ms, ORDER BY with 400,000 rows out 320 to 51 ms. 11b: INTERSECT ALL and EXCEPT ALL streamed by counted keys, 93 to 66 and 86 to 55 ms. 11c: keys from the batch's columns (`lexdb_pipe.obKey`, `keyInt`): texts -33%, integers 0 to -13%; most of what is left of an integer UNION/INTERSECT (about 55 ms at 400,000 rows) is the string-keyed map and the rows given one by one. The runners are in `lexdb_setop` (488 lines), run parts through a hook; exec 23,765 to 23,562 lines. Suite 192 of 192. Left: a typed set for a single integer column (`Map[int, int]`) and giving kept rows as a chunk (a selection of the batch) instead of row by row; WITH TIES, coercion (`sel.conv`) and recursion still run held; a value the sort does not hold (keys of mixed kinds) re-runs the statement held (parts run twice: a volatile non-CTE expression in a part would be evaluated twice) |
| 12 | `worktree-agent-a9756e2abe8513f0a` | merged (c4ce9df1; TPC-H 1.008 of c6344eb6, checksums equal); done on its branch (2026-11-20, from main d19b7864): GROUPING SETS, ROLLUP, CUBE, `GROUP BY DISTINCT` and `()` run in the pipeline. `aggShape` drops its `gsets` refusal (the one condition), `pipeAgg` gives `PAgg.sets` (the sets' places in the keys) and the `Agg` bool, `opsOf` no longer refuses them; `lexdb_pipe.AggSets` (`aggSets`) holds one `AggSt` per set, each keyed by its set's keys (`aggState` takes the key places), every batch fed to each in turn (`eat`; a key or call the batches do not run: the whole aggregate falls to the scalar step as before); each group records the place of the row that made it (`AggSt.born`), `finish` merges the sets' groups by (born row, set), the row engine's order, via `groupAt` (the old `finish` body); the groups' `give` hook gains the set number, `pipeGroups` fills `Groups.sets`, and the HAVING, outputs, GROUPING() (constants per set, `Sel.gx/gh/gord`), ORDER BY and LIMIT are the row engine's views as before (the fused HAVING is off for sets). The scalar fallback (`groupRow`) has `groupRowSets`, as `addToGroup`. A non-exact collation's key stays row (as plain GROUP BY). Test `exec_aggsets` (336 + 75 + 18 + 11 + 3 queries and 12 parameter runs, batched against off, rows in order). `lexdb_exec` 23,407 -> 23,410 lines, `lexdb_pipe` 6,544 -> 6,679. 200,000 rows, exclusive lock, base -> branch ms: rollup of 3 columns 215 -> 75, cube of 3 columns 390 -> 125, four grouping sets 189 -> 45, with `count(DISTINCT)` 213 -> 69, 405 -> 130, 154 -> 39, `rollup(k1)` 70 -> 10, rollup of two with sum(float), min 144 -> 67; plain GROUP BY unchanged (46, 5.5 ms). Left: each set evaluates its keys and calls' arguments again (a set's cost is about a plain GROUP BY's; no sharing of key columns, no merging a finer set's groups into a coarser one); an expression key the batches do not evaluate (`upper(b)`) groups row by row, as plain GROUP BY does; a non-exact collation's key; max_statement_mem is checked per set and over the sets together after each batch, so the error may come within one batch of where the row engine's does; TPC-H not run (coordinator) |

Open points found in review:
- Item 3: in a batch, an aggregate call's FILTER, argument, separator and
  keys are each evaluated over the whole batch in turn, so when two of
  them fail on different rows of one batch the error raised is the first
  step's, not strictly the first failing row's (the typed kernels already
  behaved so). Same SQLSTATE class in every case tested; a fix would
  re-run a failing batch row by row on copies of its groups'
  accumulators.
- Items 4+5: reg casts (`::regclass`, `::regtype`) stay row by row: they
  need the session's catalog (SeqEnv), which the pipeline's Up hook does
  not carry.
- Items 1+2: the aggregate and join pipelines' first-table readers read a
  lookup list one range at a time (batched per range, not chunked); a
  joined table's list and `bLevelPlan` still refuse lists.
- Item 11: integer set operations are bound by the string-keyed map and
  by giving rows one at a time (next: `Map[int, int]` for one integer
  column, kept rows given as a selection of the batch).
- Item 6: if the pipeline gives up after running a volatile derived table
  that is not a CTE (a sort key mixing value kinds was the one trigger
  found), the row engine runs that table again (scalar subqueries already
  behave so; CTEs are shared and never rerun). A held first level of a
  join under 64 rows goes to the row engine (the join pipeline's set-up
  cost), at +1% instructions against base for a 3-row VALUES join.
