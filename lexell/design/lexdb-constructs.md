# lexdb: the construct inventory (redesign step 0)

Status: 2026-11-19, based on main `a7489c10`. Step 0 of
[lexdb-layers.md](lexdb-layers.md) section 6: every SQL construct lexdb
accepts in queries and DML, mapped to its owner in the layered design, with
where it lives today, which executor path runs it, and its tests.

**Owners.** **B** binder (layer 4: names, scopes, types, star, GROUP BY and
ORDER BY resolution, views, CTE names, folding). **R** optimizer rewrite
(layer 5). **O:x** physical operator x of lexdb-layers.md 4.6. **S**
statement logic (layer 7: writes, RETURNING, ON CONFLICT, constraints,
locking, per-row side effects).

**Path today.** `both`: batches when the named guard allows, else the row
path (`runLevel`/`tryRow`). `row`: never in a batch. `once`: run once per
execution before the scan. `rewrite`: turned into other constructs by the
parser or planner. `row*`: DML writes, one row at a time, over a query that
runs `both`. `none`: no rows read. "as X": runs as row X does. Functions are
in `lexdb_exec` unless a module is named; `(parse)` is `lexdb_parse`.
Batches come from the pipeline (`lexdb_pipe`: exec's `pipeShape`,
`sortShape`, `aggShape` and `joinsOver` choose what it gets; `compile`,
`opsOf`, `aggOps`, `joinOps` check it) or, for a query it does not take,
the row engine's first table (`batchLevel`, `bLevelPlan`) and its joins as a
levels program (`levelsProg`, `Query.jp`). The pipeline reads a table whose
`PScan.batch` is false row by row; that is not a batch.

**Tests.** Names are files in `tests/lexdb/run/` without `.lxl`;
`x_queries` is `tests/lexdb/x_queries.txt`, run by `exec_x` (`mssql_*` by
`tds_*`, `oracle_*` by `tns_*`, `vscode_queries` by `tds_vscode`,
`mr_cases` by `exec_mrdoors`, `tds_mr`, `tns_mr`).

## 1. Expressions

### 1.1 Scalar operators and forms

| # | Construct | Owner | Today | Path | Row-only feature | Tests |
|---|---|---|---|---|---|---|
| E1 | literals, typed literals (`DATE '…'`, `INTERVAL '1' DAY`, `0x…`), Oracle `''` as NULL | B (fold) | `primary` (parse), `castVal`, `constVal` | both | — | exec_time, exec_types, tns_oracle |
| E2 | column refs: `c`, `t.c`, `s.t.c`; `*`, `t.*` | B | `resolve`, `resolveName`, `selectCols`, `itemCols` (`lexdb_bind`); `colIndex` (by name at run time) | both | — | exec_sql, exec_joinusing |
| E3 | parameters `$n`; T-SQL `@v` (also `@@IDENTITY`, `SCOPE_IDENTITY()`), Oracle `:b`, all as parameters | B (types) | `paramTypes`, `guessParams`, `castParams`; `lexdb_bind.bindIn` binds a given value as a constant, else a slot (`BX.Param`) | both | — | exec_inparams, exec_plancache, wire_prepared, tns_binds, tds_tsql |
| E4 | arithmetic `+ - * / % ^`, unary `-`, bitwise `& \| # << >> ~`, `\|\|` (text and arrays) | B (operator by type) + O:Project/Filter | `binVal`; `arith`, `arithTime`, `unaryVal` (`lexdb_ops`); `arrayConcat` (`lexdb_bind`); `BNode.Arith`, `BNode.DArith` (`lexdb_pipe`) | both | — | exec_ops, exec_batchexpr, exec_batchdec, exec_funcs |
| E5 | comparisons `= <> != < <= > >=`, `OPERATOR(pg_catalog.=)` | B (+collation) | `compare` (`lexdb_ops`), `cmpColl`, `bpCmp` (`lexdb_bind`); `BNode.Cmp/ValCmp/VCmp/DCmp` (`lexdb_pipe`) | both | — | exec_ops, exec_batch, exec_charcoll, exec_timelit |
| E6 | `AND`, `OR`, `NOT` | B + R (`pullCommonOr`; OR hull `orLevels`) | `eval` short-circuit; `BNode.And/Or/Not` | both | errors in row order (a batch that errors is read again row by row from its start: `runScan`, `batchLevel`) | exec_orpush, exec_joingen, exec_batch |
| E7 | `IS [NOT] NULL / TRUE / FALSE / UNKNOWN`; row `IS NULL` | B (parse: `IS TRUE` → `distinct from`) | `isTail` (parse); `BNode.IsNull` | both | — | exec_ops |
| E8 | `IS [NOT] DISTINCT FROM` (rows too) | B | `isTail` (parse); `distinctFn` (`lexdb_lib`) | both | — | exec_ops, forms_queries |
| E9 | `[NOT] BETWEEN [SYMMETRIC]` | B (parse → `>= AND <=`) | `cmpExpr0` (parse) | rewrite | — | exec_ops, exec_rangedel, forms_queries |
| E10 | `CASE` (simple, searched), `COALESCE`, `NULLIF`, `GREATEST/LEAST`; T-SQL `IIF`, `CHOOSE`, `ISNULL`; Oracle `NVL`, `NVL2`, `DECODE` | B (dialect forms → `case`/`coalesce` at parse) | `caseExpr`, `tsqlCall`, `oraCall` (parse); `eval`, `BX.Case` (`lexdb_bind`) | both | short-circuit: only the branch taken is evaluated | exec_ops, exec_batchexpr, exec_bindtypes, tds_tsql, tns_oracle |
| E11 | `CAST`, `::`; T-SQL `CONVERT(t, x [, style])`, CAST to n chars; `::regclass/regtype` | B | `castVal`, `coerce` (`lexdb_ops`), `tsqlCast` (parse), `regCast` | both; reg casts row (`lexdb_bind.bindIn` refuses `K_REG`: `regCast` reads the catalog through the session's `SeqEnv`, which `Ctx`/`Up` do not carry) | — | exec_types, exec_intypes, exec_float, exec_bindfix, altertab_queries |
| E12 | T-SQL `TRY_CAST`, `TRY_CONVERT` | B | `#try`; `eval`, `BX.Try` (`lexdb_bind`) | both | — | tds_tsql |
| E13 | `COLLATE`, column collations, `char(n)` padding | B | `#collate/#coll/#ci/#pad/#bppad`; `exprColl`, `collateCall` (`lexdb_bind`), `bpFix`, `lexdb_sqlcoll` | both as filters and sorts; the pipeline's aggregates and hash joins refuse non-exact collations (`aggShape`, `pipeAgg`, `joinsOver`; `joinOps` needs `PJoin.exact`) | — | exec_sqlcoll, exec_charcoll, exec_bindfix, tds_bulk, exec_migrate |
| E14 | `[NOT] LIKE/ILIKE [ESCAPE]`; T-SQL LIKE with `[sets]` | B | `likeMatch` (`lexdb_lib`), `lexdb_like`, `#tlike` (`lexdb_tsqlfn`); `BNode.Like`; `likeBounds` (index range) | both | — | exec_like, exec_ops |
| E15 | `x [NOT] LIKE ANY/ALL (array \| subquery)` | B (subquery → `arrayOfSub`) | `quantOf` (`lexdb_lib`) | both for an array; a subquery as E37 | — | forms_queries |
| E16 | `SIMILAR TO [ESCAPE]`, `substring(x SIMILAR p ESCAPE e)` | B | `similarFn`, `substringFn` (`lexdb_lib`; `lexdb_func`) | both | — | forms_queries, funcs_queries |
| E17 | regex `~ ~* !~ !~*` | B | `reOpFn` and kin (`lexdb_lib`) | both | — | funcs_queries, forms_queries |
| E18 | `x [NOT] IN (list)` | B (compares as `=`) + O:Filter / O:IndexLookup | `inFn` (`lexdb_lib`), `inList`; `BNode.InVals/InInts/InGen` (`lexdb_pipe`); `Path.ins` lookups (`pathScans`, `lexdb_access.inScans`) | both as a filter; a primary key's IN list as the first table's scan is read in batches (`lexdb_plan.firstBatches`; `srcFor` marks its points `pts`, `pointsPick` reads them with `fillPoints`, one `fetchMany` per chunk of 32 keys doubling to 1,024); an index's IN list, and a composite primary key's prefix list, too: `srcFor` marks the ranges `multi`, `rangesPick` reads a chunk of keys with `fillRanges` (`rangeManyIn`: one pass over the sorted ranges, 32 keys doubling to 1,024, 2 doubling where the read may stop; rows in index order, reversed when backward; a chunk past 8 MB read in halves), forward and backward; an aggregate's or a join's first table reads such a list one range at a time (batches per range, not chunked); `scanBatches` still refuses `p.ins` (a joined table's list), `bLevelPlan` refuses them, `lookupPath`/`rangePath` refuse them per row | — | exec_ops, exec_inlookup, exec_inparams |
| E19 | row constructors and comparisons: `(a,b) op (c,d)`, `(a,b) IN ((…),(…))` | B (parse: `rowCmp` expands to scalar AND/OR) | `rowCmp`, `rowItems` (parse) | rewrite | — | forms_queries, upsert_queries |
| E20 | `x op ANY/SOME/ALL (array)` | B + O:Filter / O:IndexLookup | `quantOf` (`lexdb_lib`); `= ANY` lookups `anyOf` (`Path.inArr`) | both as a filter; a `= ANY` list as the first table's scan: in batches as E18 (`firstBatches`, a primary key's or an index's); a joined table's: row by row (`scanBatches` refuses `p.inArr`) | — | exec_any, exec_intypes, exec_bindfix |
| E21 | arrays: `ARRAY[…]`, `'{…}'`, `x[i]`, `@> <@ &&` | B | `#elem` (`elemFn`), `arrContains` (`lexdb_lib`), `arrayText` (`lexdb_ops`) | both | — | funcs_queries, exec_srf, exec_any |
| E22 | `AT TIME ZONE`, `AT LOCAL`, `EXTRACT`, `CURRENT_DATE` and kin, `now()` | B (→ `timezone`, `date_part`) | `atTimeZone`, `nowFn`, `datePartFn`, `timezoneFn` (`lexdb_lib`); `lexdb_pipe.callAt` (transaction time) | both | — | exec_tz, tz_queries, time_queries |
| E23 | scalar functions: built-in and dialect (`lexdb_func`, `lexdb_tsqlfn`, `lexdb_orafn`; DATEADD, EOMONTH, TO_CHAR, DBMS_LOB, …) | B (by signature) | `fnRefOf` (bound once to `lexdb_lib.entryOf`/`entry1Of`), `lexdb_pipe.callAt`, `callDialectFn` | both | — | funcs_queries, tds_tsql, tns_oracle, tns_java |
| E24 | T-SQL forms: `+` on strings (`t+`), decimal `/` and `AVG` (`#tdiv`, `#tavg`), bit arithmetic (`#bitint`, `#bitnot`) | B | `binVal`, `eval` | both; `#tdiv`/`#tavg` bound as `lexdb_lib` entries (`tdivFn`, `tavgFn`; eval calls `lexdb_lib.tdiv`/`tavg` direct) | — | tds_tsql, mssql_tsql_queries, exec_tsqlbatch |
| E25 | Oracle forms: `\|\|` with NULL (`#ora_cat`), NUMBER `/` (`#ora_div`), date ± number (`#ora_add/#ora_sub`), SYSDATE | B | `oraArith` (parse), `lexdb_orafn` | both | — | tns_oracle, tns_review |
| E26 | session and catalog functions: `current_setting`, `set_config`, `pg_backend_pid`, `txid_current`, `has_*_privilege`, `pg_get_*`, `object_id`, `current_schema` | B; S for `set_config` | `sessCall`, `callCat`, `sysCall`, `hasPrivFn` | row (`fnRefOf`: `FN_NONE`) | `set_config` writes session state | funcs_queries, catalog_queries, altertab_queries, tds_vscode |
| E27 | sequences: `nextval/currval/setval/lastval`, Oracle `s.NEXTVAL/CURRVAL` | S | `seqCall`, `nextVal`, `bindSeqs`; `oraSeq` (parse) | row (`fnRefOf`: `FN_NONE`) | side effect per row, in order | exec_seq, exec_seqcrash, tns_oracle |
| E28 | advisory locks `pg_advisory_*`, `pg_try_advisory_*` | S | `advCall` | row (`fnRefOf`: `FN_NONE`) | side effect | exec_locks, migrate_queries |
| E29 | volatile: `random()`, `clock_timestamp()`, `gen_random_uuid()`, T-SQL `NEWID()` | B (mark volatile) | `randomFn`, `clockFn`, `uuidFn` (`lexdb_lib`); `isVolatile` (defaults; `bLevelPlan` leaves a volatile condition to the row path where it rechecks) | both (see section 9) | a new value per evaluation | exec_orpush, exec_types, exec_bindfix |
| E30 | `ROW(a, b)` as a value (not compared) | — | `eval` refuses (0A000) | — | rejected | — |

### 1.2 Subquery expressions

| # | Construct | Owner | Today | Path | Row-only feature | Tests |
|---|---|---|---|---|---|---|
| E31 | scalar subquery, uncorrelated | B + O (run once, a constant) | `planSub`, `runSub` (stops at 2nd row), `lexdb_pipe.subValue`; in a pipeline plan `BX.Sub` (`lexdb_bind.bindSubs`) | once; the expression holding it batches in the pipeline (`BX.Sub`) and in the row engine's first table (`bSubNode`: `condSubVals` copies the value into `Mats.ce.subs`; `bxOf` itself does not bind `#sub`) | — | exec_sub, exec_with, exec_pipe, exec_subbatch |
| E32 | scalar subquery, correlated (WHERE, select list, GROUP BY key, aggregate argument) | B + R:unnest (to a grouped join) + O:HashProbe(left) | per row `fillCur`, `runSub`, memo `cacheAt` (`MEMO_MAX`); per-key aggregate `runHashed`/`hashSub` (9.26); select list: rows kept, then evaluated (`execSelIn`); GROUP BY: rows kept, then grouped | row (`pipeShape`, `aggShape`, `levelsProg` refuse `q.corr`) | correlated | exec_sub, exec_groupcorr, exec_corrkey, exec_semires |
| E33 | `[NOT] EXISTS`, uncorrelated | B | `runSub` (stops at first row) | once | — | exec_sub |
| E34 | `[NOT] EXISTS`, correlated | B + R:unnest + O:HashProbe(semi/anti) or IndexLookup(semi) | `semiJoins`, `semiLevel`, `semiLook` (a level); `runHashed` (keyed hash); else per row `fillCur` | both as a semi/anti level (`joinsOver`: a hash of its rows, or a range per row, `rangePath`); row when hashed (`RUN_HASHED`: `joinRuns1` refuses) or per row | correlated (when not a level) | exec_semijoin, exec_semilook, exec_semires, exec_sub, exec_pipe |
| E35 | `x [NOT] IN (subquery)`, `= ANY` / `<> ALL (subquery)`, uncorrelated | B (types as `=`, collation) + O:HashProbe(semi/anti/mark) | set built once, `inProbe`, `inValKeys` (`lexdb_pipe`); drives lookups (`Path.inSub`); or `semiJoins` | both as a semi/anti level; else the set is built once and probed, in batches in the pipeline (`BX.Sub`) and in the row engine's first table conditions that are not semi levels (NOT IN, IN under OR: `bSubNode`); `inSub` lookups as the first table's scan: in batches as E18 (`firstBatches`, a primary key's or an index's; past `inMax` the whole table is read, as before); a joined table's, row by row (`scanBatches` refuses `p.inSub`) | NOT IN's NULL rule | exec_insub, exec_intypes, exec_intext, exec_semijoin |
| E36 | `x [NOT] IN (subquery)`, correlated | B + R:unnest + O:HashProbe(semi/anti/mark) | `runHashed` (keyed), `semiLevel`; else per row | as E34 | correlated | exec_semires, exec_intypes |
| E37 | `x op ANY/ALL (subquery)`, op not `=`/`<>` | B (parse: `arrayOfSub`, an `array_agg` scalar subquery) + R | `arrayOfSub` (parse), `quantOf` (`lexdb_lib`) | both when uncorrelated: in the pipeline (`bindSubs` binds its `#sub`) and in the row engine's first table conditions (`bSubNode`); row when correlated | correlated if it has refs | exec_any, forms_queries, exec_subbatch |
| E38 | `(a,b) op (subquery)`, `(a,b) [NOT] IN (subquery)` | B (parse: `rowSub`, a scalar subquery of `max(case …)`) + R | `rowSub` (parse) | row | correlated (the row is outer) | forms_queries |
| E39 | `ARRAY(subquery)` | B (parse: `arrayOfSub`) | `arrayOfSub` (parse) | as E37 | — | catalog_queries |

### 1.3 Aggregates and windows

| # | Construct | Owner | Today | Path | Row-only feature | Tests |
|---|---|---|---|---|---|---|
| E40 | `count(*)`, `count`, `sum`, `avg`, `min`, `max` | B + O:HashAgg | `collectAggs`, `accumulate`, `addToGroup` (exec); `lexdb_agg` `admit`/`add`/`finish`; pipe `runAgg`, `runAggJ` (`AggSt`), `bAccum` | both (guard: `aggShape`, `pipeAgg`, `aggOps`) | — | exec_agg, exec_hashagg, exec_batchdec, exec_pipe, exec_aggpipe |
| E41 | `string_agg`, `array_agg`, `bool_and/bool_or/every`, `stddev*`, `var*`; T-SQL `COUNT_BIG`; Oracle `LISTAGG` | B + O:HashAgg | `lexdb_agg` `add`/`finish`; pipe `AggSt` (`BA_GEN`: an `Acc` per group, a value at a time; kernels `BA_AND/BA_OR`, `bAccVar` for float columns) | both (item 3a/3b: every aggregate runs in the pipeline; numeric/integer `stddev*`/`var*` take the generic `Acc`) | — | exec_agg, exec_aggorder, exec_aggpipe, tns_oracle, tds_app |
| E42 | `agg(DISTINCT x)` | B + O:HashAgg | `lexdb_agg` `admit`; pipe `AggSt` (`BA_GEN`; `BA_CNTD`/`bAccDist`: a per-group integer set for `count(DISTINCT int)`) | both (a non-exact collation's argument: row) | — | exec_agg, exec_groupcorr, exec_aggpipe |
| E43 | `agg(…) FILTER (WHERE c)` | B + O:HashAgg | name `" filter"`; `PCall.filter`, `BSpec.filter` | both | — | exec_agg, exec_batch, exec_like |
| E44 | `agg(x ORDER BY …)`; `STRING_AGG/LISTAGG … WITHIN GROUP (ORDER BY …)` | B + O:HashAgg (sorted per group) or SortAgg | name `" order:"`; `lexdb_agg` `orderedParts`; `PCall.more`/`dirs` (separator and keys per value) | both (`BA_GEN`) | order within group | exec_aggorder, exec_aggpipe, tds_tsql, tns_oracle |
| E45 | `count(v.*)` (MATCH_RECOGNIZE) | B | `primary` (parse) | row | — | exec_mr |
| E46 | `GROUPING(a, …)` | B | `setSubst`, `hasGrouping` | both (a constant per grouping set: the groups' views, `Sel.gx`, hold it; the sets run in the pipeline, C4) | — | forms_queries |
| E47 | window calls `f(…) OVER (PARTITION BY … ORDER BY …)`: `row_number`, `rank`, `dense_rank`, `percent_rank`, `cume_dist`, `ntile`, `lag/lead`, `first/last/nth_value`, aggregates | B (`winPlan`, `mergeWin`) + O:Window | `winValues`, `winPartition`, `winCmp`; input rows by `winBatch` | row (window values); its input rows batch for one table (`winBatch`) or over joins by a levels program (`Query.jp`) | order within partition | exec_window, exec_batchsort |
| E48 | frames `ROWS/RANGE/GROUPS BETWEEN … PRECEDING/FOLLOWING`, `EXCLUDE CURRENT ROW/GROUP/TIES` | O:Window | `frameBounds`, `frameOff`, `rangeTarget`, `excluded` | row | — | exec_window |
| E49 | named windows `WINDOW w AS (…)`, `OVER w`, `OVER (w …)` | B | `mergeWin`, `winSpecText` | row | — | exec_window |
| E50 | Oracle `ROWNUM` outside WHERE's simple tests | B (parse → `row_number() OVER ()`) + O:Window | `oraPrimary` (parse) | row | scan order | tns_oracle |

## 2. FROM and joins

| # | Construct | Owner | Today | Path | Row-only feature | Tests |
|---|---|---|---|---|---|---|
| F1 | base table: full scan, PK range, index range, index-only, backward | B + R (`choosePath`) + O:Scan/IndexLookup/Fetch | `buildQuery`, `pathScans`, `fetch`, `fillPick`; `fillPickIn`, `fillIdxRows` (`lexdb_access`) | both; in batches: a PK range, a PK read backward (`fillBackBatch`, 32 rows doubling to 1,024), a PK point list (`fillPoints`, as E18), an index's range, also where the read may stop early (a LIMIT: `IxRead.small`, `fillIdxRows` and `fillIdxOnly` take the cursor's 32 entries doubling to 1,024, not 1,024), an index's IN list (`fillRanges`, as E18); a PK point is in batches only for an aggregate (`scanBatches`). A single PK point row by row (`srcFor`); `bLevelPlan` refuses the lookup shapes | — | exec_scanchoice, exec_index_diff, exec_batch, exec_batchindex, exec_pipe |
| F2 | no FROM (`SELECT 1`) | O:Values | `runQuery` (no levels), `allTrueX` | row | — | exec_any, forms_queries |
| F3 | `[INNER] JOIN … ON`, comma join with WHERE equalities | R (`joinOrder`, `costOrder`) + O:HashBuild/HashProbe(inner), IndexLookup, NestedLoop | `runLevel`/`tryRow` (per-row lookup or `materialize`d hash); `joinsOver`, levels programs (`levelsProg`, `runLevelsProg`); pipe `joinRows`, `joinFrom`, `hashBuild`; `fetchMany`, `rangeMany` (`lexdb_access`) | both (guard: `joinsOver`, `joinOps`: first table in batches, keys of no collation, a per-row level only a whole-key lookup or a range, none under a LIMIT that stops the scan) | — | exec_join, exec_batchjoin, exec_joinrange, exec_joinorder, exec_pipe |
| F4 | `CROSS JOIN`, comma join without an equality | O:NestedLoop | `runLevel` | row (`joinsOver` needs a hash key, a whole-key lookup or a range) | — | exec_join, exec_with |
| F5 | `LEFT [OUTER] JOIN` | O:HashProbe(left), IndexLookup | `runLevel` NULL row, `Level.post`; pipe `tailEnd`, `PJoin.post` | both (guard as F3) | — | exec_join, exec_rightjoin, exec_batchjoin, exec_pipe |
| F6 | `RIGHT [OUTER] JOIN` | O:HashProbe(right) | `rs.seen`, unmatched rows at `runRows`' end; pipe `joinRows` (after the scan) | both: one RIGHT JOIN, by a hash (`joinsOver`, `joinOps`) | — | exec_rightjoin, exec_join, exec_pipe |
| F7 | `FULL [OUTER] JOIN` | O:HashProbe(full) | `runRows`, `keepsRight` | row (`joinsOver`, `joinOps` refuse FULL) | — | exec_join, joinusing_queries |
| F8 | `NATURAL JOIN`, `JOIN … USING (…)` (FULL USING: COALESCE) | B | `buildQuery` (`ColDef.using`), `usingSide`, `resolveName` (`lexdb_bind`) | as the join | — | exec_joinusing |
| F9 | Oracle `(+)` outer join | B (parse → LEFT JOIN) | `oraOuterJoins` (parse) | as F5 | — | tns_catalog, tns_oracle |
| F10 | derived table `(SELECT …) AS x(a, …)` | B + O:CTE scan (held rows) | `runFrom`, `materialize`, `Level.src`; `narrowSub` | inner query both; as the first level row (`tableRead`, `bLevelPlan` refuse virtual levels); as a later level joined by an equality, a hash of its rows (`JH_ROWS`) | — | exec_with, exec_limits, exec_groupkeys |
| F11 | `LATERAL (…)`; T-SQL and Oracle `CROSS APPLY`, `OUTER APPLY` | B (scope) + R:decorrelate + O:NestedLoop | `Level.lateral`, run per row in `runLevel` | row (`joinsOver`, `tableRead` refuse LATERAL) | correlated | exec_with, tns_oracle, tds_app, mssql_app_queries |
| F12 | CTE `WITH x [(cols)] AS [NOT] MATERIALIZED (…)` (the hint is parsed and ignored) | B (naming) + O:CTE scan | `withList`, `cteRef` (parse; re-parsed per use); `SubPlan.cte`, `cacheAt` (rows shared) | as F10 | — | exec_with, exec_insertsel |
| F13 | `WITH RECURSIVE` (UNION [ALL]; `max_recursion`) | B + O:CTE scan + a recursive union (not in 4.6's table) | `runRecursive`, `Level.work` | row (rounds); each round's query both, its working table as a later level a hash (`JH_ROWS`) | — | exec_with, exec_limits |
| F14 | `(VALUES …) AS x(…)`; `VALUES` as a query; Oracle `DUAL` | B + O:Values | `valuesSub` (parse), `execSrf` (`#values:`) | as F10 | — | merge_queries, catalog_queries, tns_client |
| F15 | `generate_series(…)` in FROM (integer series made as read) | O:function scan (not in 4.6's table; Values-like) | `execSrf`, `lazySeries`, `seriesRes` | as F10 (as the first level a lazy series) | — | exec_srf |
| F16 | `unnest(…)`, `regexp_matches`, `regexp_split_to_table`, `string_to_table`, `pg_partition_ancestors`; `WITH ORDINALITY` | O:function scan | `execSrf`, `srfCols` | as F10 | — | exec_srf, funcs_queries |
| F17 | set-returning call in the select list (`SELECT unnest(a)`) | B + O:ProjectSet (not in 4.6's table) | `hasSrfCall`, `expandSrfs` | row (`streams`, `sortShape` refuse `hasSrfCall`) | — | forms_queries, catalog_queries |
| F18 | Oracle `FROM dual CONNECT BY LEVEL <= n` | B (parse text rewrite → `generate_series`) | `connectLevel` (parse) | row | — | tns_oracle |
| F19 | catalog relations: `pg_catalog.*`, `information_schema.*`, `sys.*`, Oracle `ALL_*`/`V$*`; a sequence read as a relation | B + O:Values | `catRows` (`lexdb_pgcat`, `lexdb_syscat`, `lexdb_oracat`), `execSrf` | as F10 | — | catalog_queries, tds_pgcatalog, tns_catalog |
| F20 | views | B (expanded as a derived table) | `viewQuery`, `buildQuery` | as F10 | — | exec_views, exec_viewsx |
| F21 | temporary tables; T-SQL table variables (`DECLARE @t TABLE`) and table-valued parameters | B (name → session temp table) + S (TVP rows loaded) | `tempRel` (`lexdb_catalog`); `tableVariables`, `renameVars` (`lexdb_tsqlparse`), `lexdb_tds` | as F1 | — | exec_temp, tds_tvp, tds_tvp_wire, tds_batch |

## 3. SELECT clauses

| # | Construct | Owner | Today | Path | Row-only feature | Tests |
|---|---|---|---|---|---|---|
| C1 | `WHERE` | B + R (conjuncts to levels, bounds, OR hull) + O:Filter, Scan bounds | `conjuncts`, `bounds`, `Level.cond`, `pathScans`; row engine `bLevelPlan`/`bCondNode`; pipeline `Filter` (`planConds`) | both (row engine: a conjunct that does not bind runs per row, `bCondNode`; pipeline: every one must bind, `planConds`) | — | exec_batch, exec_join, exec_sub |
| C2 | `GROUP BY` exprs, ordinals, output names | B (`resolveGroup`) + R (columns of a grouped PK dropped from the key) + O:HashAgg | `addToGroup`; pipe `runAgg`/`runAggJ` (`AggSt`) | both (guard: `aggShape`: no set op, SRF, window, lock, correlation, MIN/MAX by the scan, virtual first table, collation's key; `pipeAgg`/`aggOps`: every call, E40–E44 (a non-exact collation's argument: row); joins as F3) | — | exec_agg, exec_groupkeys, exec_hashagg, exec_narrow, exec_pipe |
| C3 | `MIN/MAX` read from an index's order | R + O:Scan + O:Limit | `minMax`, `Sel.first` | row (`aggShape` refuses `sel.first`) | order | exec_index_diff |
| C4 | `GROUPING SETS`, `ROLLUP`, `CUBE`, `()`, `GROUP BY DISTINCT` | B (parse expands sets) + O:HashAgg per set | `groupBy`, `groupItem` (parse); `setSubst`, `Sel.gsets/gx`; pipe `AggSets`, `aggSets` | both (one `AggSt` per set in `lexdb_pipe.AggSets`, every batch fed to each, the groups merged in the row engine's order by the row that made them, a row's in the sets' order; a key the batches do not evaluate: `groupRowSets`, row by row; a non-exact collation's key: row) | — | forms_queries, exec_aggsets |
| C5 | `HAVING` | B + O:Filter | `execSelIn`; `pipeGroups` (drops groups first) | both (with C2); evaluated per group | — | exec_agg, exec_groupkeys |
| C6 | `SELECT DISTINCT` | O:Distinct | `seen` map in `execSelIn`; pipe `SortSt` (`DistSet`) | both (guard: `sortShape`) | — | exec_batchsort, exec_agg |
| C7 | `DISTINCT ON (…)` | B (ORDER BY reordered) + O:Sort + Distinct (first per key) | `Sel.donKey`, `execSelIn` | row (`sortShape` refuses `donKey`) | order | forms_queries |
| C8 | `ORDER BY` exprs, ordinals, aliases, `ASC/DESC`, `NULLS FIRST/LAST` (T-SQL: NULLs first ascending) | B (`resolveOrder`) + R (order from an index: `servesOrder`, `orderedScan`) + O:Sort | `sortOutRows`, `skSort` (`lexdb_sort`); pipe `SortSt` | both (guard: `sortShape`); grouped, windowed and set rows sorted by `sortOutRows` | — | exec_batchsort, exec_topn, exec_window |
| C9 | `LIMIT`, `OFFSET`, `FETCH FIRST n ROWS ONLY`, `LIMIT ALL` | O:Limit (stops the scan: `Level.stops`) | `evalInt`, `rs.limit`; pipe `Limit` | both; an OFFSET without ORDER BY or DISTINCT is the row engine's (`streams`, `opsOf`) | order | exec_topn, exec_limits |
| C10 | `ORDER BY … LIMIT` (top-N) | O:TopN | `execSelIn` (cut at the bar, `keepFirst`); pipe `SortSt` (heap; the scan's bar, `lexdb_access.Bar`) | both (guard: `sortShape`) | — | exec_topn |
| C11 | `FETCH FIRST n ROWS WITH TIES` | O:TopN (with ties) | `execSelIn` | row (`pipeShape`, `sortShape` refuse `withTies`) | order | forms_queries |
| C12 | T-SQL `TOP n`, `TOP (expr)` | B (→ limit) + O:Limit | `top` (parse) | both | order | tds_tsql, vscode_queries |
| C13 | T-SQL `TOP n PERCENT`, `TOP … WITH TIES` | O:Limit over a counted input (not in 4.6's table) | `Sel.topMode/topN`, `execSelIn` | row (`pipeShape`, `sortShape` refuse `topMode`) | needs the row count first | tds_tsql |
| C14 | `FOR UPDATE / NO KEY UPDATE / SHARE / KEY SHARE [OF t] [NOWAIT \| SKIP LOCKED]` | S | `runLocking`, `applyLocks`, `lockOf`, `lexdb_locks` | both, row engine only (the pipeline refuses locks: `streams`, `sortShape`, `aggShape`, `tableRead`); `bLevelPlan` has no lock test, so the first table's conditions batch | locks per row in order; reruns after a wait | exec_locks, exec_updrand, migrate_queries |
| C15 | `MATCH_RECOGNIZE` (PG, T-SQL, Oracle); `PREV/NEXT/FIRST/LAST`, `CLASSIFIER`, `MATCH_NUMBER`, `RUNNING/FINAL` | B (`mrRewrite`, `planMatch`) + O:MATCH_RECOGNIZE | `execMatch`, `mrPartition`, `lexdb_match` | row (its input query both, in the row engine: `pipeShape` refuses `sel.mr`) | order | exec_mr, exec_mrparse, exec_mrdoors, tds_mr, tns_mr |
| C16 | `WAIT n SECONDS \| MILLISECONDS` | S (rerun on commits) | `waitShape`, `waitFits`, `waitForRun` | as its query | waits for commits | exec_waitfor, tds_wait, tns_wait |
| C17 | `SELECT … INTO [TEMP] t`, `CREATE TABLE … AS` | B + S | `statement` (parse: made a CREATE TABLE AS); `createTableAs` | row* | writes | temp_queries, keyless_queries |
| C18 | Oracle `WHERE ROWNUM <= n` | B (parse → LIMIT; a subquery when ordered) | `oraRownum`, `oraLimit` (parse) | rewrite | order | tns_oracle, tns_wait |
| C19 | T-SQL `SELECT @v = expr, …` | B + S (last row assigned; `lexdb_tsql`) | `itemListAssign` (parse), `feedbackOf`, `Sel.feedback` | both, unless an item reads a variable it assigns (`Sel.feedback`: `pipeShape`, `sortShape` refuse it): then row, in order | feedback | tds_batch, vscode_queries |

## 4. Set operations

| # | Construct | Owner | Today | Path | Row-only feature | Tests |
|---|---|---|---|---|---|---|
| D1 | `UNION [ALL \| DISTINCT]` | O:SetOp | `planSet`, `runSet`, `runChild` (held); `lexdb_setop`: `combine`, `distinctRows`, `rowKeyIn` (held), `runUnsorted`, `runSorted`, `giveSet` (streamed); `streamsSet`, `setPartRun`, `runSelToIn` (exec) | both, streamed to a sink (no coercion, lock, MATCH_RECOGNIZE, recursion or WITH TIES): UNION ALL passes each branch's batches on as it makes them; UNION DISTINCT keeps a set of row keys (`runSetKeys`), each row given once, keys charged to max_statement_mem, a chunk's keys made from its columns (`lexdb_pipe.obKey`); OFFSET skipped and LIMIT counted as the rows come; each branch both through its pipeline row plan (`pipeSelMain`, rows true for branches) | — | exec_with, exec_limits, exec_bindtypes, exec_setstream, exec_setkey |
| D2 | `INTERSECT [ALL]` | O:SetOp | as D1 | both, streamed (`runSetKeys`: the right part's keys first, with ALL counted; ALL gives a left row while its key's count lasts, in the left's order); branches both | — | exec_with, exec_index_diff, exec_setstream |
| D3 | `EXCEPT [ALL]`, Oracle `MINUS` | O:SetOp | as D1 (MINUS lexed as EXCEPT) | both, streamed (`runSetKeys`, as INTERSECT; EXCEPT ALL skips a left row while its key's count lasts); branches both | — | exec_with, tns_oracle, exec_setstream |
| D4 | set operation with `ORDER BY/LIMIT/OFFSET`; a parenthesised branch with its own | B + O:Sort/Limit over SetOp | `planSet`, `execSelIn` (held); `lexdb_setop.runSorted`, `lexdb_pipe.setSort` (streamed) | ORDER BY [LIMIT] [OFFSET] to a sink: both; the branches' rows and chunks feed the pipeline's sort (`SortSt`: a top-N of LIMIT + OFFSET rows with a LIMIT), OFFSET counted after it, the rows kept given as one chunk; a value it does not sort (keys of mixed kinds) runs held, as does WITH TIES; OFFSET alone skips rows as they come; a branch with its own ORDER BY/LIMIT is a SELECT run as a part. Held (no sink): row | — | exec_with, exec_sub, exec_setstream |

## 5. DML

| # | Construct | Owner | Today | Path | Row-only feature | Tests |
|---|---|---|---|---|---|---|
| M1 | `INSERT … VALUES (…), (…)` | S + B (targets, coercion) | `insert`, `insertRows`, `insertOne`, `storeRow` | row* | defaults and `nextval` per row; checks per row | exec_sql, exec_unique, exec_check, exec_fkey |
| M2 | `INSERT … SELECT` (parenthesised too), `WITH … INSERT` | S + its query | `insert` → `planSelect` + `eachRow` (or `runSel` first when it reads its target: `stmtReads`), `insertSelRow` | row* | as M1 | exec_insertsel |
| M3 | `DEFAULT` in VALUES/SET, `DEFAULT VALUES`, column defaults, serial and identity | S + B | `defaultsOf`, `defAt`, `defaultValue`, `idDefault` | row* | `nextval` per row | exec_default, exec_seq |
| M4 | `OVERRIDING SYSTEM/USER VALUE`; T-SQL `SET IDENTITY_INSERT` | S | `insert`, `identityInsertOf` | row* | identity moves past a given value | exec_seq, tds_tsql |
| M5 | `ON CONFLICT [(cols) [WHERE p] \| ON CONSTRAINT c] DO NOTHING` | S | `upsertOf`, `conflictOf`, `insertOne` | row* | a conflict check per row | exec_upsert, exec_keyless |
| M6 | `ON CONFLICT … DO UPDATE SET … [WHERE]`, `EXCLUDED.c` | S + B (EXCLUDED's scope) | `upsertOf`, `upsertOld`, `insertOne` | row* | per row | exec_upsert |
| M7 | `UPDATE … SET … [WHERE]`, `SET (a, b) = (x, y)` | S + its query | `update`/`updateB` (`runQuery`), `lockFound`, `updRow`, `checkRow` | row* | rows locked; FK and CHECK per row | exec_updrand, exec_batchexpr |
| M8 | `UPDATE … FROM` (T-SQL: target named in FROM) | S + B + O:HashProbe(inner/left) | `dmlFrom`, `onceEach`; `tsqlDml` (parse) | row*; its joins per row (`update` builds a Query, not a Sel: no levels program), its first table's conditions in batches (`batchLevel`) | one change per target row (first match) | joinwrite_queries |
| M9 | `DELETE … [WHERE]` | S + its query | `delete`/`deleteB`, `delRow`, `parentSide`, `fkFinish` | row* | FK actions (CASCADE, SET NULL/DEFAULT) per row | exec_fkaction, exec_dmlscale |
| M10 | `DELETE … USING`; T-SQL `DELETE … FROM` | S + O:HashProbe(inner/left) | `dmlFrom`, `onceEach` | row*; as M8 | — | joinwrite_queries |
| M11 | range delete (a DELETE whose WHERE is a key range) | S + access `deleteRange` | `rangeDelete`, `rangePlan`, `rangeDeletes`; `lexdb_access.deleteRange` | none (no row read) | — | exec_rangedel, exec_rangedel_ix, tds_rangedel, tns_rangedel |
| M12 | `UPDATE/DELETE … WITH (batch_rows n)` | S | `batchDml`, `winEnd` | row* | commits every n rows | exec_batchdml |
| M13 | T-SQL `UPDATE TOP (n)`, `DELETE TOP (n)` | S | `firstN` after `onceEach` | row* | which rows: scan order | mssql_tsql_queries, tds_rangedel |
| M14 | `MERGE` (PostgreSQL): `WHEN [NOT] MATCHED [BY SOURCE \| BY TARGET] [AND c] THEN UPDATE/DELETE/INSERT/DO NOTHING`, `RETURNING merge_action()` | S + O:HashProbe(inner/left/right/full) | `merge`, `mergeFrom` (join kind from the clauses), `mergeItems` | row*; source join as M8 (per row, `runQuery` over `buildQuery`'s Query) | first matching clause, per row, in order | merge_queries (exec_merge) |
| M15 | `MERGE` (T-SQL): `TOP (n)`, `BY SOURCE`, `OUTPUT $action, INSERTED.*, DELETED.*` | S | as M14; `tsqlMergeCheck`, `mergeOutput` (parse) | row* | as M14 | mssql_merge_queries (tds_merge) |
| M16 | `MERGE` (Oracle): `UPDATE SET … WHERE … DELETE WHERE …`, `INSERT … WHERE` | S | as M14; `MergeClause.delWhere`, `oraTarget` | row* | as M14 | oracle_merge_queries (tns_merge) |
| M17 | `RETURNING` (INSERT, UPDATE, DELETE, MERGE) | S + B | `retOf`, `retAdd`, `retAddOld`, `retRes` | row* | per written row | exec_returning, exec_dmlscale |
| M18 | T-SQL `OUTPUT INSERTED.c, DELETED.c` | B (parse → RETURNING, `#old`) + S | `tsqlDml`, `outputRefs`, `mergeOutput` (parse) | row* | per written row | mssql_app_queries, tds_merge, tds_rangedel |
| M19 | `COPY t FROM STDIN` (text, CSV, options, `batch_rows`) | S | `copyStmt`, `copyRecord`, `fastCopyPlan`, `fastCopyRun` | row* | checks per row | exec_copy, exec_copy_fast, exec_copystream, wire_copy |
| M20 | `COPY t TO STDOUT`, `COPY (query) TO STDOUT` | S + its query | `copyOut`, `copyStream` | query both | — | exec_copy, wire_copy |
| M21 | T-SQL `INSERT BULK` | S | `bulkStmt`, `lexdb_tds` | row* | — | tds_bulk |
| M22 | T-SQL `INSERT INTO t EXEC proc` | S | `insertExec` (`lexdb_tsqlparse`), `lexdb_tsql` | row* | — | tds_java |
| M23 | `TRUNCATE … [RESTART IDENTITY] [CASCADE]` | S | `truncate` | none | — | joinwrite_queries |
| M24 | constraints on writes: NOT NULL, CHECK, UNIQUE, FK (immediate, deferred, actions); no triggers exist | S | `checkChecks`, `lexdb_access.insertRow`/`updateRow` (`ixClash`), `uniqueErr`, `childSide`, `parentSide`, `fkLater`, `checkPending`, `fkFinish` | row* | per row; deferred to statement or commit end | exec_check, exec_unique, exec_fkey, exec_fkaction, migrate_queries |
| M25 | PL/SQL blocks (Oracle): `SELECT … INTO`, cursors, DML in blocks | S (a client of layers 4–6) | `lexdb_plsql` | as each statement | per statement | tns_plsql |

## 6. Dialect-specific forms (index)

Most dialect forms are rewritten by the parser and appear in the rows above.
Only T1 is not listed elsewhere.

| Form | Row |
|---|---|
| T-SQL `TOP`, `TOP PERCENT`, `WITH TIES` | C12, C13 |
| T-SQL `SELECT @v =` | C19 |
| T-SQL `OUTPUT` | M18, M15 |
| T-SQL `CROSS/OUTER APPLY` | F11 |
| T-SQL table variables, TVPs | F21 |
| T-SQL `TRY_CAST`, `TRY_CONVERT`, `CONVERT` | E12, E11 |
| T-SQL `IIF`, `CHOOSE`, `ISNULL` | E10 |
| T-SQL `+` concat, decimal `/`, bits, LIKE `[sets]`, date functions | E24, E14, E23 |
| T-SQL `SCOPE_IDENTITY`, `@@IDENTITY`, `IDENTITY_INSERT` | E3, M4 |
| T-SQL `UPDATE/DELETE TOP`, `MERGE`, `INSERT BULK`, `INSERT … EXEC` | M13, M15, M21, M22 |
| **T1** T-SQL table hints `WITH (NOLOCK, …)`, `(NOLOCK)`: parsed and ignored (`tableHints`, parse). Owner B (drop). Tests: mssql_app_queries, vscode_queries | — |
| Oracle `DUAL`, `CONNECT BY LEVEL` | F14, F18 |
| Oracle `ROWNUM` | C18, E50 |
| Oracle `(+)` | F9 |
| Oracle `MINUS` | D3 |
| Oracle `DECODE`, `NVL`, `NVL2`, `''` as NULL, `\|\|`, NUMBER `/`, date arithmetic, SYSDATE | E10, E1, E25 |
| Oracle `s.NEXTVAL/CURRVAL` | E27 |
| Oracle `FETCH FIRST`, `APPLY`, `LISTAGG … WITHIN GROUP` | C9, F11, E44 |
| Oracle `MERGE … DELETE WHERE`, `INSERT … WHERE` | M16 |
| Oracle PL/SQL | M25 |

## 7. Headline

Counted from the tables above by a script over their columns: 120
constructs (E1–E50, F1–F21, C1–C19, D1–D4, M1–M25, T1). E30 is rejected
today and left out below, so 119 are supported.

- **Owners** (a construct counts under each owner it has):
  - B: 78;
  - R: 13;
  - O: 53;
  - S: 33.
- **Path today:**
  - both: 55 (including the rows that run "as" a `both` row: E36, E39, F8,
    F9, F12, F14–F16, F19, F20, F21);
  - row only: 31;
  - once: 2 (E31, E33);
  - rewrite, runs as its parts: 4 (E9, E19, C18, T1);
  - row\*, statement writes one row at a time over a `both` query: 22;
  - statement around an ordinary query: 3 (C16, M20, M25);
  - no rows read: 2 (M11, M23).
- **Batch-capable today:** the 55 `both` rows, plus the source queries of
  the 22 `row*` rows and the 3 statement-wrapped queries. No construct runs
  only in batches.

A construct that is both as a filter and row as an index lookup (E18, E20)
counts as both; E47 (window values row, input rows batch) counts as row;
F10's kin (first level row, later level a hash) count as both.

## 8. Row-only constructs that need special handling in a chunk pipeline

These carry row semantics, not just a missing batch implementation. For each:
why, and what the new design does.

1. **Sequence calls and identity defaults** (E27, M3). Side effect per row,
   numbers in row order. Evaluate per selected row, in order, inside the DML
   operator (layer 7) or a Project marked volatile that runs after every
   filter and before any LIMIT that could drop rows; never inside a
   vectorised filter.
2. **`set_config`, advisory locks** (E26, E28). Side effects on session and
   lock state. Same rule as 1; the binder marks them volatile.
3. **Volatile functions** (E29). A value per evaluation; today they run in
   batches, and where the row path rechecks a level's conditions
   `bLevelPlan` leaves them to it. The binder marks them; the optimizer must not push
   them below a join or LIMIT or evaluate them twice; the vector evaluator
   evaluates them only for rows in the selection vector, once.
4. **Correlated subqueries**: scalar (E32), EXISTS (E34 per-row forms), IN
   (E36), ANY/ALL (E37), row comparisons (E38), LATERAL and APPLY (F11).
   Per outer row today, with a memo. Step 5 unnests them: EXISTS/IN to
   semi/anti/mark joins, scalar aggregates to a grouped left join, LATERAL to
   a dependent join; what cannot be unnested runs as a NestedLoop whose inner
   plan is re-run per outer chunk row, keeping today's memo.
5. **`FOR UPDATE` and kin, `NOWAIT`, `SKIP LOCKED`** (C14). Locks per row in
   output order; SKIP LOCKED changes which rows count toward LIMIT; a wait
   reruns the query. A lock operator below Limit that takes rows one at a
   time in order (as PostgreSQL's LockRows), with the rerun kept in layer 7.
6. **RETURNING / OUTPUT** (M17, M18) and **MERGE's clauses** (M14–M16).
   Per written row, after its write; MERGE takes the first clause that holds,
   in order. Row-at-a-time logic over chunks inside the DML operator.
7. **ON CONFLICT** (M5, M6). Each row's conflict depends on earlier rows of
   the same statement. Per row, in order, in the DML operator.
8. **FK, CHECK, UNIQUE, deferred checks** (M24). Per row, some at statement
   or commit end. Stay in layer 7, fed chunks.
9. **UPDATE/DELETE TOP (n)**, **`batch_rows`** (M12, M13). Which rows and
   when to commit depend on scan order. The DML operator counts rows in
   arrival order; the access layer's key-ordered scan keeps the cursor.
10. **T-SQL `SELECT @v = f(@v)` feedback** (C19). Each row sees the previous
    row's assignment. Run row by row, in order, in one Project-like operator
    (or layer 7); never vectorised.
11. **MATCH_RECOGNIZE** (C15). Order-dependent automaton. Keep it row-based
    inside one operator over sorted partitions, as lexdb-layers.md 4.6 says.
12. **Order-dependent output cuts**: DISTINCT ON (C7), WITH TIES (C11), TOP
    PERCENT (C13), ROWNUM (C18, E50), MIN/MAX by index order (C3). Plain
    operators over sorted chunks (Distinct-on-key, TopN with ties, Limit after
    a count, Window row_number), but they need a defined input order: the
    optimizer must keep it.
13. **WAIT n SECONDS** (C16). The statement reruns as commits arrive. Stays
    in layer 7 around an ordinary plan.

Row-only today only because no batch code exists (no row semantics; plain
operators in the new design): FULL JOIN (F7), CROSS JOIN without a key (F4),
derived tables, CTEs, VALUES, function scans and catalog relations as a first
level (F10–F16, F19), recursive CTEs (F13), SRFs in the select list (F17),
set operations (D1–D4), grouping sets and GROUPING (C4, E46: done, `AggSets`), aggregates
other than count/sum/avg/min/max and DISTINCT/ORDER BY aggregates
(E41, E42, E44), window values (E47–E49), IN-list, `= ANY` and IN-subquery
lookups and PK point reads (E18, E20, E35, F1), uncorrelated subqueries
inside an expression in the row engine (E31, done: `bSubNode`), `#tdiv`/`#tavg`
(E24, done: `lexdb_lib`) and reg casts (E11, left: they need the session's
catalog, which the pipeline's `Ctx` does not carry).

Operators these need that lexdb-layers.md 4.6's table does not list: a function scan
(F15, F16; or fold into Values), ProjectSet (F17), a recursive union with a
working table (F13), Limit-after-count for TOP PERCENT (C13), and a lock step
(C14). The table should gain them or say which operator absorbs them.

## 9. Gaps and oddities found

**Accepted by the parser, refused by the executor (0A000 and the like):**

- a window aggregate with `DISTINCT`, `ORDER BY` or `FILTER` (`winPlan`);
- window functions with `ROLLUP/CUBE/GROUPING SETS` (`planSelect`);
- window functions in a set operation's ORDER BY (`planSet`);
- `FOR UPDATE … WITH TIES` (`planSelect`; PostgreSQL, as I recall, refuses
  only `SKIP LOCKED` with `WITH TIES`, which lexdb's parser also does). The other
  FOR UPDATE refusals (GROUP BY, HAVING, DISTINCT, UNION, windows,
  aggregates, the nullable side of an outer join) match PostgreSQL;
- RIGHT and FULL joins in `UPDATE … FROM` / `DELETE … USING` (`dmlFrom`);
- `UPDATE/DELETE WITH (batch_rows n)` with RETURNING/OUTPUT, FROM/USING or
  TOP, and UPDATE that sets a PK column (`batchDml`, `updateB`);
- `ROW(a, b)` as a value (`eval`);
- MATCH_RECOGNIZE: a subquery in the clause, some aggregates, quantified
  subpatterns that can match empty (`mrRewrite`, `planMatch`);
- `a correlated subquery is not supported here` and `a subquery is not
  supported here` in `eval`: guards for an `Env` without subquery results.
  I could not confirm which statement contexts reach them.

**Refused by the parser:** parenthesised joins `(a JOIN b) JOIN c`; an alias
on `JOIN … USING`; `LATERAL` before a table name; a row before `op ANY/ALL`
other than `= ANY` / `<> ALL` (subquery); a subquery inside a row compared
with a subquery; multi-dimensional arrays and arrays of enums; MERGE `TOP …
PERCENT`; MATCH_RECOGNIZE over a recursive CTE; WAIT with SELECT INTO;
Oracle `(+)` in some positions; Oracle CONNECT BY other than `dual CONNECT
BY LEVEL <= n` (fails as unsupported); T-SQL `DECLARE … CURSOR`; T-SQL
`OUTPUT … INTO` (not parsed). A CTE body must be a SELECT (`subquery`
expects SELECT), so writable CTEs and `WITH x AS (VALUES …)` are refused.

**Oddities:**

- The batch path evaluates conditions over whole batches, so a condition can
  run on rows past a LIMIT. Errors are handled (the batch is read again row
  by row); a volatile function's extra calls are not.
- `DECLARE @t TABLE` is rewritten to a temp table by `tableVariables` before
  parsing, yet `lexdb_tsqlparse` still has a "DECLARE of a table … not
  supported yet" error; I did not confirm which forms reach it.
- `ON CONFLICT (cols) WHERE p`: the partial index predicate is parsed and
  dropped (the index is chosen by its columns). CTE `[NOT] MATERIALIZED` and
  T-SQL table hints are parsed and ignored too.
- A CTE's text is re-parsed at each use (`cteRef`), though its rows are
  shared (`SubPlan.cte`). The binder should bind it once.
- Only one `RIGHT JOIN` per query batches, and only by a hash (`joinsOver`).
- `UPDATE … FROM`, `DELETE … USING` and MERGE join per row: their Query is
  built without a Sel, so it gets no levels program (M8, M10, M14).
- No outer-to-inner join conversion and no predicate pushdown into derived
  tables were found in today's planner; both are new R work, not a port.

**Not confirmed:** which contexts reach `eval`'s subquery guards. Counts in
section 7 are by a script over the columns.
