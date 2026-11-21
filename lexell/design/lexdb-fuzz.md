# lexdb-fuzz: a differential and metamorphic SQL fuzzer for lexdb

## Hand-over note (2026-11-21, paused by the coordinator)

**State.** `lexell/tools/lexdb_fuzz.py` works end to end: it generates data, runs
every check, reduces failures and writes a report. It has had **one short
run**: 1 worker, 158 s, 217 seeds, 12,969 queries, 133,362 statements, plus
7,617 TLP and 8,295 NoREC forms, against main 757c4cee. The several-hour run
across seeds has **not** been done yet. The bugs below come from that short
run and from a few manual probes. I did not fix any of them in lexdb.

**How to resume.**

1. Build the switch-aware binary (about 5 s; takes the shared bench lock;
   needs `lexell/compiler/out/lxlc`, which `lexell/compiler/build.sh` builds):
   `python3 lexell/tools/lexdb_fuzz.py build --out ~/tpch-w/fuzz/lexdb-fuzz-<rev>-O`
2. Run it at low priority. Every server is pinned to CPUs 8-11 at nice 15:
   `nice python3 lexell/tools/lexdb_fuzz.py run --bin ~/tpch-w/fuzz/lexdb-fuzz-<rev>-O --out ~/tpch-w/fuzz/run1 --workers 3 --duration 10800 --seed 1000`
   Give a later run a new `--seed` and a new `--out`.
3. `python3 lexell/tools/lexdb_fuzz.py report ~/tpch-w/fuzz/run1` prints the
   distinct failures. Each one comes with its reduced setup, query and results.
   The case files are in `run1/w*/cases/*.json`.
4. `python3 lexell/tools/lexdb_fuzz.py repro CASE.json --bin BIN [--pg]`
   reruns one case under every configuration.

**Which checks work.** All of these ran in the short run: batch, rules, alt,
force, noidx, tlp (where, group, having, agg), norec and pg. In the short run
batch, tlp and norec found nothing. Everything below was found by pg, alt,
noidx or rules.

**Unfinished (do these first when resuming).**
- The fix for a reduction false positive is applied but has not been run.
  Reduction can remove ORDER BY, and the reduced case was still compared in
  order. It now takes `ordered` from the candidate in `reduce_case`. Two
  reports from the short run were this artefact and are left out below.
- Gap G1 floods the pg check: 1,074 of 13k queries. While lexdb does not
  accept a parenthesised first operand of a set operation, the generator
  should write `select ... union select ...` without parentheses when neither
  side has ORDER BY or LIMIT, or it should make the parentheses optional. G2
  and G3 are similar. Until then, these gaps hide the pg check on every query
  with a set operation.
- Hangs: a statement timeout on lexdb is reported as a hang. The check should
  run the query on PostgreSQL and drop the report when PostgreSQL is slow too
  (H1 is probably just slow).
- Reductions per check:class are capped (`--reduce-wrong 25`,
  `--reduce-err 2` per worker), so a long run reduces each family only a few
  times. `report` groups by signature: check, class, error messages and the
  SQL features of the reduced query.
- Not done: comparison against SQL Server (gen_mssql.py), and the T-SQL and
  Oracle doors. All queries are PostgreSQL dialect.

## The tool

`lexell/tools/lexdb_fuzz.py` needs only Python 3 and PostgreSQL 18's
`initdb`/`postgres`. It speaks the wire protocol itself (psycopg is not
installed). Each worker starts its own lexdb servers, each with its own data
directory under `--out/wN/`, its own port (`--port + 10N .. +3`),
`--unsafe-no-sync`, `--cache-mb 64`, pinned with `taskset -c 8-11` at nice 15:

| server | binary environment | connections (configurations) |
|---|---|---|
| s0 | defaults | `on` (cost planner, batches on), `off` (`SET lexdb_batch = off`), `rules` (`SET lexdb_planner = rules`) |
| alt | `LEXDB_FUZZ_UNNEST=0 _REWRITES=0 _BUSHY=0 _KEYORDER=1` (setUnnest/setRewrites/setBushy/setKeyOrder: all off, never key order) | `on` |
| force | `LEXDB_FUZZ_BUSHY=2` (BU_FORCE), `_KEYORDER=2` or `3` (KO_SORTED/KO_PLAIN, alternating by worker) | `on` |
| noidx | defaults; the same setup without its `create index` statements (primary keys kept) | `on` |

`build` writes a temporary `cmd/lexdb_fuzzmain.lxl`: a copy of `lexdb.lxl`
whose `main` first reads `LEXDB_FUZZ_*` and calls `lexdb_plan`'s test
switches. It compiles that file with `-O` and then deletes it. No lexdb source
changes. With a plain binary, use `--no-variants`: alt and force are skipped.

PostgreSQL gets its own cluster in `--out/pg`, made by `initdb --locale=C`,
so text orders bytewise as in lexdb. It runs with fsync off, autovacuum off,
no parallel workers, on port `--pg-port`, with one database `fzN` per worker.

**Data.** There are 1 to 4 tables `t0..t3`, with columns `a0..`, `b0..`
(names unique across tables). The column types are int, bigint, smallint,
numeric, numeric(6,2), text, varchar(4), char(3), date, bool and float8. Some
tables have a primary key or NOT NULL columns. Each table has 0 to 20 rows
from small domains, so duplicates and join matches are common, with 0-35%
NULLs and 3% extreme integers. A setup can also have:
- 0 to 3 indexes: one, two or three columns; 20% partial; 10% on an expression;
- a DELETE or UPDATE after the load;
- a view `v0`;
- ANALYZE, 60% of the time.

**Queries.** Expressions are typed, so PostgreSQL accepts about 99% of the
queries. The generator produces:
- joins: inner, left, right, full (equi conditions), cross, comma, LATERAL;
- semi and anti joins: EXISTS / NOT EXISTS, IN / NOT IN over subqueries and
  lists, ANY / ALL / SOME, correlated and not;
- scalar subqueries, derived tables, CTEs;
- aggregates, also with DISTINCT and FILTER, string_agg ordered;
- GROUP BY / HAVING, DISTINCT;
- window functions: rank, dense_rank, count, sum, avg, min, max, row_number,
  ntile, lag, lead, first_value, and ROWS frames;
- set operations, including ALL;
- ORDER BY every output column (so the result is deterministic and compared
  in order), LIMIT / OFFSET;
- CASE, COALESCE, NULLIF, casts, LIKE / ILIKE, BETWEEN, IS DISTINCT FROM;
- text, date and numeric functions.

A window ordering that is not total orders by every column in scope.

**Checks** (`--checks`, comma list; default all):
- `batch`: on vs off, on s0.
- `rules`: cost vs rules, on s0.
- `alt` and `force`: the switched binaries vs s0 on.
- `noidx`: no secondary indexes vs s0 on.
- `tlp`: SQLancer's ternary logic partitioning, run on s0 on:
  - tlp-where: `q` = `q and p` UNION ALL `q and not p` UNION ALL
    `q and p is null`, with UNION for DISTINCT;
  - tlp-group: the group keys, UNION of the partitions;
  - tlp-having: HAVING partitioned;
  - tlp-agg: count/sum/min/max/bool_and/bool_or recombined over the
    partitions' UNION ALL.

  `p` is a fresh random predicate and may contain subqueries. Errors on
  either side are skipped, since evaluation order is free.
- `norec`: `count(*) where p` vs `coalesce(sum(case when p then 1 else 0 end), 0)`.
- `pg`: s0 on vs PostgreSQL.

How results are compared:
- lexdb against lexdb: rows exactly, except that numerics are compared by
  value (equal values of different scale) and floats to 12 digits.
- Against PostgreSQL, every number is compared to 12 significant digits.
- Unordered results are compared as multisets.
- Errors must have the same SQLSTATE.
- A crash (connection lost or server exit) or a hang (5 s statement timeout,
  30 s socket timeout) is always reported. The server is then restarted and
  reloaded.

The failure classes:

| class | meaning |
|---|---|
| `wrong` | the rows differ |
| `errcode` | both sides fail, with different SQLSTATEs |
| `a-error` | lexdb s0 fails where the other side has rows; against pg, this is a gap |
| `b-error` | the other configuration (or PostgreSQL) fails where s0 has rows |
| `crash`, `hang` | as described above |

**Reduction** is automatic. It works on the query tree:
- an expression is replaced by a same-typed child, a literal or NULL;
- select items, FROM items, WHERE, HAVING, GROUP BY keys, DISTINCT, the set
  operation, CTEs, LIMIT, OFFSET and ORDER BY are dropped;
- a join is replaced by one of its sides, made inner, or given `on true`.

It then works on the data: statements after the load, unused tables, rows
(ddmin per table), unused columns and NOT NULL. It keeps a change only if the
same check still fails with the same class (and the same SQLSTATEs). One
reduction is limited to `--reduce-secs`.

## Bugs found (main 757c4cee), ranked

Wrong results come first, then errors on valid queries, then hangs, then gaps
(lexdb rejects SQL that PostgreSQL accepts).

**W1, W2, E1, E2 and E3 fixed (2026-11-21, on 11c4e049; each note below).**
`repro --pg` of the 28 reduced cases of the first run (~/tpch-w/fuzz/t1)
that were these bugs: every configuration agrees with PostgreSQL. A 310 s
run with the same seed (1 worker, `--seed 1`, all checks: 48 seeds, 7,115
queries) found none of them again; besides the gaps G1-G5 it reported, as
new and not chased: a window's `row_number()` repeated within a partition
over a cross join with LATERAL (w0-0257: lexdb 3,3,4,4,1,1,2,2 where
PostgreSQL numbers 1-4; the same on 11c4e049), `1.5 / nullif(bigint, 0)`
with 16 decimals where PostgreSQL gives 36 (w0-0428), a 200,000-row cross
join reported different whose reduction stopped (w0-0697; the same rows
shown, also on 11c4e049), and a statement timeout like H1 (w0-0981).

### W1. `a, b RIGHT/FULL JOIN c` joins the whole comma list (pg; 17 reduced cases)

```sql
create table t0 (a1 bigint);
create table t1 (b0 bool);
insert into t0 values (9);
select 1 from t1 as q1, t0 as q2 right join t0 as q3 on true;
-- lexdb: 1 row; PostgreSQL: 0 rows (t1 is empty)
create table t2 (a1 int);
insert into t2 values (8), (4);
select true from t2 as q1, (select 1 from t2 as q3) as d2 full join t2 as q10 on false;
-- lexdb: 6 rows; PostgreSQL: 8
```
Expected (SQL and PostgreSQL): JOIN binds tighter than the comma, giving
`q1 × (q2 RIGHT JOIN q3)`. lexdb computes `(q1 × q2) RIGHT JOIN q3`. With two
rows each that gives 2·2 + 2 = 6 rows instead of 2·(2+2) = 8. It shows with
tables, views, derived tables, CTEs and inside LATERAL. Inner joins are
unaffected because there the grouping does not matter. Likely cause: the
FROM-list parser or binder attaches a join's left operand to the item list
built so far, not to the last comma item. I have not looked at the code.

**Fixed (d5ad2b8a).** Cause: the parser keeps FROM as a flat list, and the
levels join left-deep, each to all the tables before it, so a RIGHT or FULL
JOIN after a comma kept the rows of every earlier item, not only its tree's.
The parser now reads the list from its first comma on with `fromTrees`: a
join tree after a comma (or an UPDATE's FROM or DELETE's USING first tree,
after the target) with a RIGHT or FULL JOIN is read again as a subquery of its
own (`nestTree`: `SELECT` of its every column under its own name,
`TREE_STAR`) and joined as a LATERAL item, its columns named as the tree's
(alias.column) and USING's merges kept. The doors share the parser: checked
against PostgreSQL (exec_fuzzfix), SQL Server 2022 (tds_fuzzfix) and Oracle
Free (tns_fuzzfix). Left as it was: an ON that names an item before the comma
(PostgreSQL: 42P01) is accepted.

### W2. char(n) comparisons with text / varchar / ANY (pg)

```sql
create table t0 (a0 char(3));
insert into t0 values ('c');
select 'a' from t0 as q4 where q4.a0 >= any (select q5.a0 from t0 as q5);
-- lexdb: 0 rows; PostgreSQL: 1 ('c' >= 'c')

create table t1 (a0 varchar(4), a4 char(3));
insert into t1 values ('bb', ' a'), (' a', 'a ');
select 'a' from t1 as q1 where exists (select 1 from t1 as q4 where q4.a0 = q1.a4);
-- lexdb: 0 rows; PostgreSQL: 1 (varchar ' a' = char(3) ' a ': pad spaces are insignificant)

create table t2 (a2 text, a4 char(3));
insert into t2 values ('ab', 'ab');
select (select 1 from t2 as q3 where q3.a2 = q2.a4) from t2 as q2;
-- lexdb: NULL; PostgreSQL: 1 (bpchar to text drops the padding)
```
Likely cause: inside a subquery (ANY, EXISTS, scalar), a char(n) value is
compared padded, or the comparison is not resolved as bpchar/text as it is at
the top level. Look at how the subquery and semi-join key paths type a char
key (lexdb_plan's semi or hash keys).

**Fixed (b14e49ae).** On 11c4e049 the second and third cases above pass
over tables; the reduced cases that failed were over a view (w0-0703,
w0-0706). Three causes, all in lexdb_bind: (1) an outer column of a view or
derived table was an untyped parameter in a subquery (only a table's is
typed, so that a UNION's wider values are not cut), so it took the other
side's type and a char's padding counted; a derived char, varchar or text is
now cast to its type without a length. (2) `x op ANY | ALL (array)`, and so
`op ANY | ALL (subquery)` other than `=` and `<>`, trimmed x but not an array
of chars' elements; now each pair is compared as `bpCmp` compares
(`#bptrims`). (3) `IN (subquery)` between a char and a varchar (or an untyped
value) compared one side padded; both now compare as chars (the set's
varchars trimmed, `readAs` `OID_BPCHAR`). Not done: Oracle compares a CHAR
beside a VARCHAR2 without padding; the Oracle door compares those as
PostgreSQL does, at the top level as in subqueries (a dialect gap of its own).

### E1. `there is no parameter $1` (08P01) on a valid correlated query (alt; also default s0 against pg: 9 cases)

```sql
create table t0 (a3 numeric(6,2));
create table t1 (b2 int);
create table t3 (d1 int);
insert into t1 values (0);
select (exists (select 1 from t1 as q7
                join lateral (select count(*) from t3 as q9 where q9.d1 = d1.x6) as l8 on true
                where q7.b2 = d1.x6)) as x15
from (select 1 as x6 from t0 as q2) as d1;
-- s0 (defaults): 0 rows; alt (setUnnest(0), ...): ERROR 08P01 there is no parameter $1
```
A correlated LATERAL aggregate inside a correlated subquery names an outer
derived table's column. That outer reference is never bound to its parameter.
The pg check saw the same message under the default configuration, with a
correlated LATERAL inside `IN (subquery)`:
`select q1.a3 from t0 q1 join t0 q2 on ... where (...) in (select 0 from t0 q3 join lateral (select ..., q1.a3 from t0 q5 where q5.a4 = q2.a4 ...) ...)`.
The full text is in the w0 cases with code 08P01. Likely in the correlation
or parameter numbering of LATERAL under a subquery (lexdb_plan unnesting,
UN_LATERAL, and the per-row path when unnesting is off).

**Fixed (f657e1a2).** Cause: `hashSub` (lexdb_plan) made a correlated EXISTS,
IN or scalar subquery run once and hashed on its keys when each outer value
in its conditions was a key, without looking into its own subqueries; a
LATERAL or derived table in it that read the outer query's column then ran
with no parameter. Such a subquery now stays per row.

### E2. `round(numeric, int)` exists or not depending on the plan (rules, alt, noidx, pg)

```sql
create table t0 (c0 int, c2 numeric(10,2));
insert into t0 values (1, 1.5), (2, null), (3, -2.25);
select round(c2, 1) from t0;          -- ERROR 42883 function round with 2 arguments does not exist (batches on and off)
select round(c2, 1) from t0 limit 1;  -- 1.5
```
Expected: `round(numeric, int)` everywhere, as in PostgreSQL. One evaluator
(the one used with LIMIT 1, a chunk of one) knows round/2 and the other does
not. Whether it fails depends on the plan, which is why alt, noidx and rules
all report it as error-vs-rows. Likely cause: the function table of the
batch/pipeline evaluator (lexdb_pipe or bxEval) lacks round with a scale.

**Fixed (3bf78d10).** Cause: not the evaluators (both use lexdb_lib's
`round2Fn`): it took a NULL value or scale for a call it had no function for,
so a query failed when a plan reached a row with a NULL (LIMIT 1 stopped
before row 2). It is strict now. exec_batchexpr's count of failing random
queries drops by six (its `round(e.n, 1)` over NULLs).

### E3. An index path casts a constant to the column's numeric(p,s) and overflows (noidx)

```sql
create table t0 (a0 numeric(6,2));
create table t1 (b2 int);
create index t0_i0 on t0 (a0);
select 1.5 from t1 as q1 join t0 as q2 on (q2.a0 > 2147483647);
-- with the index: ERROR 22003 numeric field overflow (precision 6, scale 2);
-- without it, and PostgreSQL: 0 rows
```
Likely cause: the range bound of an index scan is coerced to the column's
declared type (typmod) instead of being compared as an unconstrained numeric.
That is in the index range or key building (lexdb_plan's range from
conjuncts).

**Fixed (f732012a).** Cause: a range bound was coerced to the key column's
type when the scan ran (the row engine's `pathScan`, the pipeline's range
join), and a value past the type's range failed; a smallint's or an int's
too (`2147483647 > c0` over an indexed smallint, also in the run). Equality
keys already matched nothing (`keyVal`). `lexdb_ops.boundInto` now takes a
bound past the type's range as past every row's: on the rows' side (a lower
bound below them, an upper one above) it bounds nothing, else the range is
empty.

### H1. A 5 s statement timeout (on; probably only slow, not checked against PostgreSQL)

```sql
create table t0 (a0 date not null, a1 int, a2 char(3), a3 int, a4 text);
-- 10 rows (see case w0-1800 in the run's directory); indexes on (a4) and (a0, a2)
with cte0 as (select date '2024-01-03' as x6, 'a' as x7 from t0 as q1 cross join t0 as q2 join t0 as q3 on true)
select max(q15.x6) from cte0 as q8
  join lateral (select coalesce(q10.x7, q10.x7), q8.x6 as x12, q10.x6 from cte0 as q10) as l9 on true
  right join cte0 as q15 on (l9.x12 = q15.x6);
```
cte0 has 1,000 rows and the lateral side 1,000 per outer row. Every x6 is
equal, so the right join meets about 10^9 pairs. PostgreSQL is probably slow
too, so this is not a bug until timed against it.

### Gaps: lexdb errors where PostgreSQL returns rows (pg)

- **G1** (1,074 of the 12,969 queries): a set operation whose first operand is
  parenthesised, `(select ...) union (select ...)`, fails with 42601 syntax
  error at or near "(". Inside an expression,
  `x in ((select ...) intersect (select ...))` fails with a syntax error at or
  near "intersect", "union" or "except".
- **G2** (261): a derived table whose body is a parenthesised set operation,
  `from ((select ...) union (select ...)) as d`, fails with 0A000
  "parenthesized joins are not supported". The parser takes the `((` for a
  parenthesised join.
- **G3** (193): `with c as (...) (select ...) union all (select ...)` fails
  with 42601 "WITH must be followed by SELECT, INSERT, UPDATE or DELETE".
- **G4** (54 cases where lexdb returns rows and PostgreSQL fails): int4
  arithmetic does not overflow. `select 2147483647::int + 1` gives 2147483648
  in lexdb and 22003 "integer out of range" in PostgreSQL. The same holds for
  `int_col * int_col` and for unary minus of -2147483648. The opposite also
  occurs, with lexdb failing "bigint out of range" where PostgreSQL has rows
  (9 cases), probably from evaluation order. Not triaged.
- **G5** (manual probes): `int::bool` is not supported (lexdb: "column is of
  type boolean but the expression is of another type"). `num_nonnulls`,
  `scale`, `min_scale` and `trim_scale` do not exist.

### Excluded

Two reports from the short run were the tool's own false positive: an ordered
comparison after reduction had dropped ORDER BY (fixed, see the hand-over
note). They are not listed above.
