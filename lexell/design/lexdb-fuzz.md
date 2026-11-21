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

**W3, W4 and W5 fixed (2026-11-21, on 18321855; each note below).** These
are the three wrong results above: W4 was lexdb's (numeric division's
scale), W3 and W5 the fuzzer's (a nondeterministic query; a comparison of
truncated results). `repro --pg`: w0-0428, every configuration
PostgreSQL's 36 places; w0-0697, every configuration and PostgreSQL 205,200
rows (the first 200,000 kept); w0-0257 as stored still pairs the two
windows' values differently from PostgreSQL in every configuration, as it
may (the generator no longer writes it). A 329 s run with the same seed (1
worker, `--seed 1`, all checks, ~/tpch-w/fuzz/fz2run: 95 seeds, 14,182
queries, 8,332 TLP and 9,039 NoREC forms) found none of the three again.
Besides the gaps G1-G5 and H1-like timeouts (w0-0979) it reported, new and
not chased:
- w0-1774 (pg, wrong): `case when true then c else cast(null as text) end`
  over a char(3) `c` is of type character in lexdb, so `''` shows as three
  blanks; PostgreSQL resolves it to text and drops the padding (main too).
- w0-1920 (batch, hang): batches give 0 rows; the row engine times out at
  5 s on a CTE cross-joined with LATERAL and a FULL JOIN (speed, not rows).
- Errors by evaluation order, integer only: `1 % 0` over an empty table
  (PostgreSQL folds it and fails, lexdb returns no rows: w0-1465);
  `1 / (1 % nullif(1, 0))` in a subquery under `case when false` (lexdb
  fails 22012, PostgreSQL never runs it: w0-1627); bigint overflow in a join
  or WHERE condition that one plan reaches and another does not (rules,
  alt, noidx: w0-1483..1485; on, w0-0218 as in the first run).
- w0-0421 (pg, a-error): `1.5 / nullif(1.5 / nullif(bigint, 0), 0)` failed
  22003 with W4's first version (19 integer digits at 36 places); W4 now
  keeps the places that fit (its note), and `repro --pg` agrees.

**W6, E4 and E5 fixed (2026-11-21, on b14475f1; each note below).** W6 is
w0-1774 (CASE's common type and a char's blanks), E4 the sum and avg of
bigints past 2^63 (W4's note), E5 the errors by evaluation order (w0-1627
fixed; w0-1465, w0-1483..1485 and w0-0218 decided and explained there).
`repro --pg`: w0-1774 and w0-1627 (reduced and original) give PostgreSQL's
rows in every configuration; w0-1465, w0-1483..1485 and w0-0218 are as
before, by the decisions in E5. A 314 s run with the same seed
(~/tpch-w/fuzz/fz3run: 1 worker, `--seed 1`, all checks, 95 seeds, 14,182
queries) reports the fz2run's failures less these two (no pg:wrong left)
and nothing new: the gaps G1-G5, H1-like timeouts (w0-0978, w0-1917), the
E5 order differences, and `round(round(0), 1)`, which lexdb answers and
PostgreSQL rejects (round(double precision, integer); as before).
TPC-H (SF1, ~/tpch-w/fz3, alternated twice with main b14475f1): all 22
checksums equal and PostgreSQL's; the queries over 1.5% in that pair
(q11, q13-q17, q19, q20) have main's instructions within 0.15% (iq.sh) and,
timed twice more (best of 3), are at 0.92 to 1.03 of main (q20's +3% at
+0.05% instructions: placement). Point selects, single-row INSERT and
UPDATE by key, in process with LXL_HASH_SEED=1: main's instructions per
statement exactly (a first version that carried the door into each
statement's Names cost 21 instructions; `pgRules` reads the session
collation the statement already has).

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

### W3. `row_number()` repeats within a partition over a cross join with LATERAL (pg; w0-0257)

```sql
create table t1 (b0 date, b1 bool);
create table t2 (c0 bigint primary key, c1 text, c2 int);
insert into t1 values ('2024-02-29', false), ('2024-01-09', false);
insert into t2 values (29, 'b', 8), (35, 'a_c', 2);
select sum(1.5) over (partition by q1.b0, q12.c2 order by q1.b0, q1.b1, l2.x10, l2.x11, q12.c0, q12.c1, q12.c2
                      rows between 1 preceding and current row) as x13,
       row_number() over (partition by q12.c0, l2.x10 order by q1.b0, q1.b1, l2.x10, l2.x11, q12.c0, q12.c1, q12.c2) as x14
from t1 as q1 cross join lateral (select 'a' as x10, 1.5 as x11 from (select 1.5 as x8 from t1 as q4) as d3) as l2, t2 as q12;
-- lexdb: (1.5,3) (1.5,3) (3.0,4) (3.0,4) (1.5,1) (1.5,1) (3.0,2) (3.0,2); PostgreSQL: x14 1-4 with x13 alternating
```

**Fixed (e9a9b596): the fuzzer's, not lexdb's.** The repeats are across
partitions (x14 does not show its partition): lexdb numbers each partition
1-4, as PostgreSQL does. The two LATERAL rows are equal, so each (q1, q12)
pair gives two rows that tie in both windows' orders, and the two windows
pair their values with those rows independently: sum's 1.5 may go with
row_number's 3 or its 4. Both answers are right. The original query
(t1 with a duplicate row, a LATERAL of 96 rows showing two of their
columns) had the same ties; counted by peers (partition and order keys:
count, min and max of row_number, the sums' multiset) lexdb, batches on and
off, gives PostgreSQL's answer on main 18321855. The generator ordered the
order-dependent functions (row_number, ntile, lag, lead, first_value, the
ROWS sum) by every column in scope but the floats. It now orders them by
every column, floats included, so rows tied in that order are equal in every
column the query can show and one such function has one answer; and a select
list gets at most one of them (a second one is left out). exec_fuzzfix2 has
the case, counted by peers, and row_number, rank, dense_rank, lag, lead,
running and ROWS sums, ntile, first_value, min and max over cross joins with
LATERAL (one that reads the outer row, one with a window inside, a comma
after it, LEFT JOIN LATERAL with no rows, an empty side, identical rows,
text keys), against PostgreSQL 18: lexdb agreed before and after.

### W4. Numeric division's result scale (pg; w0-0428)

```sql
create table t0 (a1 bigint);
insert into t0 values (9223372036854775807);
select 1.5 / nullif(a1, 0) from t0;
-- lexdb: 0.0000000000000000; PostgreSQL: 0.000000000000000000162630325872825665
```

**Fixed (ae659853).** Cause: lexdb divided numerics at max(16, either
operand's display scale), rounding half to even. PostgreSQL's
`select_div_scale` (numeric.c) works in its base-10000 digits: the
quotient's weight is estimated as weight(a) - weight(b), one less when a's
first digit is not above b's; the scale is 16 - 4 * that weight, at least
either display scale, within 0..1000; `div_var` rounds half away from zero.
So a quotient below 1 gets more places (36 above), one of several digits
fewer (`99999999999999999999 / 0.01` has 2), and one whose integer part is
long fits where 16 places overflowed 38 digits
(`123456789012345678901234567890.5 / 3`). Where PostgreSQL's scale needs
more than lexdb's 38 digits (`1.5 / (1.5 / 9223372036854775807)`: 19 integer
digits and 36 places; the run below found it as w0-0421), the quotient has
as many places as fit, as a product's display scale is capped, not 22003.
`lexdb_ops.divScale` computes the scale;
`arith`'s OP_DIV, the one numeric division of both evaluators (eval and the
batches' bxEval: the typed kernels do not divide numerics), of avg and of the
variances, uses it with HALF_AWAY. As PostgreSQL's
`numeric_stddev_internal`, a standard deviation is now the square root at
the variance's scale (16 places before) and a numerator at or below zero
gives 0 (`0.00...` before). Checked against PostgreSQL 18: exec_fuzzfix2
(numeric / bigint, int / numeric, numeric / numeric, int / int, through
nullif and casts, in expressions, WHERE and ORDER BY; ties; zero dividends;
long and short quotients; avg, by group, empty; the variances and standard
deviations; window avg; NULLs, division by zero), batches on and off, and
a random comparison (40 seeds of 300 rows, 15 division expressions, the
aggregates and window avg and stddev, batches on and off: equal).
exec_agg's avg of one value and variance and stddev of numeric(6,2) changed
to PostgreSQL's text. The doors: T-SQL's typed division and AVG (`#tdiv`,
`#tavg`, SQL Server's scales) and Oracle's (`#ora_div`) are not this path and
are unchanged; a T-SQL `/` whose precision lexdb_bind does not know (not a
literal, column, cast or parameter) and its AVG of such a value still fall
to this path and now get PostgreSQL's scale (neither is SQL Server's).
TPC-H (SF1, alternated twice with main 18321855, ~/tpch-w/fz2): the
text of q1, q8 and q17 changed and now has PostgreSQL's checksum (they were
the three "different result" queries; all 22 agree now). q1's avg_price
has 12 places (16 before: a sum of weight 2 over a count of weight 1) and
avg_disc 20, q8's mkt_share 20, q17's avg_yearly 12 (a sum of weight 1 over
7.0); q1's avg_qty and q14 and q22 are as they were. No query slower (total
0.997 of main, and a third run of the final binary 0.996); q13's +2.4% has
main's instructions (code placement). Point selects, single-row INSERT and
UPDATE by key, in process with LXL_HASH_SEED=1: main's instructions per
statement within one instruction.

Not changed, seen while checking: a quotient whose integer part has more
than 38 digits is out of lexdb's range (22003 where PostgreSQL has a value,
as before); a product's display scale is capped at 38 minus its integer
digits (Decimal.mulExact), so `a / b * 2` with a quotient of more than 38
places shows fewer trailing zeros than PostgreSQL (the same value); and
`sum` and `avg` of bigint fail "bigint out of range" past 2^63 where
PostgreSQL sums in numeric.

### W5. A 200,000-row result reported as different (pg; w0-0697)

```sql
select q1.c5 as x12 from t2 as q1,
  (select 1 as x11 from (select 1.5 as x7 from t0 as q4, t2 as q5 join t0 as q6 on (q5.c4 = q6.a2)) as d3,
                        t0 as q8 cross join t1 as q9) as d2;
-- 205,200 rows in lexdb and in PostgreSQL; reported "wrong"; the reduction did not end
```

**Fixed (318ee2ec): the fuzzer's.** `Conn.query` keeps the first 200,000
rows, each server in its own order, and `compare` took the two prefixes of
an unordered result as multisets: they hold different rows of two equal
results. The reduction kept every candidate with more than 200,000 rows,
since all of them "differed". `Res` now has the count the server sent
(`total`; `truncated()`); `compare` reports different counts, compares an
ordered result's prefixes, and an unordered truncated one by its count only.
repro shows "205200 rows (the first 200000 kept)" for every configuration
and PostgreSQL; grouped by value (`x12, x13, count(*)`), the original
query's rows are PostgreSQL's.

### W6. A CASE of a char and a text is a char (pg; w0-1774)

```sql
create table t0 (a0 char(3));
insert into t0 values ('');
select case when true then a0 else cast(null as text) end from t0;
-- lexdb: '   ' (character); PostgreSQL: '' (text)
```

**Fixed (4e7a5ded).** Cause: lexdb_bind's common type (`commonOid`,
PostgreSQL's select_common_type) took CASE's values THENs first, but
PostgreSQL's transformCaseExpr puts the ELSE first; in the string category,
where text, varchar and char cast to each other implicitly, the first known
type wins (text only because it is preferred), so `THEN char ELSE text` is a
text and `THEN varchar ELSE char` a char. And a char's value made a text or a
varchar by a common type kept its blanks (`converts`: "texts are the same
values"), where PostgreSQL's bpchar to text drops them: in CASE, COALESCE,
GREATEST and LEAST (`unifyVals` now wraps it in `#bptrim`), in a UNION,
INTERSECT or EXCEPT column (`convRows`, conv bits 4 and 8) and a VALUES
column (`planSubIn`). Seen while checking: NULLIF(a, b) had a's type, but
PostgreSQL's is the type its `a = b` operator reads a as (`nullifOid`): a
char beside a text a text, a varchar a text but beside a char a char, an
integer beside a numeric a numeric and beside a float a double precision,
an untyped a b's type; a is converted to it. And a set operation's char
column (a text or a char of another length on the other side) compared with
its blanks, where bpchar's = does not (UNION gave 'a' and 'a  ' twice,
INTERSECT lost them): `setKindsOf` gives such a column COLL_PAD. The numeric
category already agreed (its implicit casts go one way only). Applies where no session collation is set (`lexdb_bind.pgRules`,
`Names.coll`): the T-SQL door, whose sessions have one, keeps a char's
blanks and NULLIF's type as before; the Oracle door gets PostgreSQL's, as
its casts already drop a CHAR's blanks (Oracle keeps them: a gap of that
door's, as W2's). CASE's order is the binder's for every door (only the
declared type of a CASE mixing char, varchar and text changes there). exec_fuzzfix3 has the cases (each statement batches on and off,
against PostgreSQL 18): CASE in every order of char, varchar and text, no
ELSE, a NULL ELSE, literals, simple and nested CASE, chars of two lengths,
in GROUP BY and WHERE; COALESCE, GREATEST, LEAST; NULLIF of chars and of
every pair of number types, in expressions and aggregates; UNION [ALL],
INTERSECT [ALL], EXCEPT of chars beside texts, varchars and chars of other
lengths, with an empty side; VALUES; the number types of CASE, COALESCE,
GREATEST, UNION; an empty table. A random comparison (2,400 expressions of
nested CASE, COALESCE, NULLIF, GREATEST and LEAST over chars, varchars,
texts and every number type, set operations and VALUES, batches on and off,
against PostgreSQL 18) leaves only the gaps below.

Not changed, seen while checking: chars of different lengths in one value
column (a CASE or COALESCE of a char(3) and a char(5), a varchar made a
char) still compare with their blanks in GREATEST and LEAST (PostgreSQL:
bpchar's comparison; which of two equal values it returns differs), and in
DISTINCT and GROUP BY over such a column; lexdb accepts a CASE, COALESCE or
GREATEST of a number and a text expression that PostgreSQL rejects (42804);
`pg_typeof` names varchar `varchar` and char(n)[] `bpchar[]` (PostgreSQL:
`character varying`, `character[]`); ARRAY[...] takes the widest type, not
the first (ARRAY[t, a] of a text and a char is a char array, PostgreSQL's
text[]); smallint +
smallint is an integer (PostgreSQL: smallint).

### E4. sum and avg of bigints fail "bigint out of range" past 2^63 (pg)

```sql
create table t0 (b bigint);
insert into t0 values (9223372036854775807), (9223372036854775807);
select sum(b), avg(b) from t0;
-- lexdb: ERROR 22003 bigint out of range; PostgreSQL: 18446744073709551614 | 9223372036854775807
```

**Fixed (0850a8bd).** Cause: every engine summed integers in an int64 and
failed on overflow (lexdb_agg.add's arith, the batches' bAccum and
bAccVal, the window's fastAdd), and sum of a bigint was a bigint, where
PostgreSQL's sum(int8) is a numeric (int128 inside) and avg of any integer
a numeric. Now `lexdb_agg.sumAdd` adds integers as integers while they
fit and past 2^63 as a numeric (the row engine, the batches' value
aggregates, the window's rows added again); the batches' int64 sums
(`bAccum`) give batErr on overflow and `AggSt.eat` gives way to the row
path, so a sum that fits costs what it did; the window's fastAdd leaves
such a value to lexdb_agg.add (its moving totals and EXCLUDE prefixes
already fell back past 2^62 / frame size). lexdb_bind casts sum of a
bigint to numeric (`wideType`; a window's sum the same, its call kept plain:
`wideInner`); at the T-SQL door to bigint, so SQL Server's type and its
overflow error stay. sum of int and smallint is still a bigint
(PostgreSQL's), avg's type is unchanged (numeric). pg_typeof and the
wire's OID of sum(bigint) are now numeric (1700), as PostgreSQL's.
exec_fuzzfix3 checks against PostgreSQL 18, batches on and off: grouped and
not, FILTER, DISTINCT, HAVING, ORDER BY, a join, a cross join, UNION ALL,
an empty input, 6,000 rows through the batches, a total back in range,
window sums and averages (running, moving, EXCLUDE, whole partition, named
window). exec_aggpipe, exec_batch, exec_winagg and exec_winframe expected
the old 22003 for their overflow cases; they now give PostgreSQL's numerics
(spot-checked against PostgreSQL 18 by md5 of every row). Not changed: a
sum of int past 2^63 (2^32 rows) is a numeric value where PostgreSQL
fails; variance and stddev of bigints still compute in lexdb's 38 digits.

### E5. A subquery's error raised where PostgreSQL never runs it (pg; w0-1627, w0-1465, w0-1483..1485, w0-0218)

```sql
create table t0 (a5 text);
create table t1 (b5 text);
insert into t0 values ('');
select case when false then (select 0.5 from t0 where 1 <> any (select 1 / (1 % nullif(1, 0)) from t0)) end from t1;
-- lexdb: ERROR 22012; PostgreSQL: 0 rows
```

What PostgreSQL does. It folds constants at plan time (eval_const_expressions:
an immutable call of constants is evaluated, an error included), simplifying
as it goes: CASE WHEN false drops its branch and COALESCE stops after a
non-NULL constant before they are folded, but every branch of a CASE with a
non-constant condition is folded (so `case when k > 5 then 1/0 else 1 end`
fails at plan time; PostgreSQL's documentation warns of it). A sublink is
planned only after that, so a dropped branch's subquery is never planned. At
run time an uncorrelated subquery is an initplan run when its value is first
needed, a correlated one per evaluation, and CASE evaluates only the branch
it takes.

**Fixed (1376301c): the CASE case.** Cause: not folding; lexdb ran every
uncorrelated scalar, EXISTS and IN subquery before the query (`runSubs`) and a
correlated one before each row's expression (`fillCur`), so a branch not
taken, or a query with no rows, raised its error. Now a subquery's data error
(SQLSTATE class 22, and 21000) is kept with its value (`SubVal.late`; per row
`lateVal`, memoized) and raised where eval, bxEval or a batch condition reads
it (`bSubNode` leaves such a condition to the row path; an IN path reads the
table whole, so its condition raises it). exec_fuzzfix3's 29 E5 cases (the reduced
and the original w0-1627; CASE false, a branch not taken and taken, run once
and per row, two rows (21000), no rows, an empty table, WHERE, an aggregate's
argument, a later row and a later batch, IN, EXISTS, under a false EXISTS)
agree with PostgreSQL 18, batches on and off; tds_fuzzfix's ten E5 batches
agree with SQL Server 2022 (it runs them lazily too). Oracle's door shares
the executor (not checked against Oracle Free: python-oracledb is not
installed). exec_apply's `case when t.id > 0 then true else (select 1 / 0
...) = 1 end` now counts its rows (it failed 22012 before).

Decided, not changed:
- Constant folding over an empty table (w0-1465, `select 1 % 0 from t0`):
  PostgreSQL fails at plan time, lexdb returns no rows (it evaluates a select
  list only for rows; a constant's error is left to the row that reaches it). Matching would mean
  evaluating, at plan time, every constant subexpression of every statement,
  including CASE branches lexdb never takes (`case when k > 5 then 1 / 0 else
  1 end`, which lexdb answers and PostgreSQL rejects), to fail queries that
  would never compute them: per-statement work for no correct answer gained.
- COALESCE evaluates all its arguments in lexdb (`coalesce(1, 1 / 0)` fails,
  PostgreSQL gives 1; `coalesce(k, (select 1 / 0 ...))` too): not changed
  (lazy COALESCE in both evaluators would be a change of its own).
- A semi-join's subquery still runs before the query (`k > 5 and k in (select
  1 / 0 ...)` fails where PostgreSQL's plan never probes it).
- Plan-dependent bigint overflow is an order difference, not a wrong result:
  w0-1483..1485, `t0 left join t1 on a0 = b1 where b1 = a1 * 6` with t1
  empty: the cost planner makes the LEFT JOIN inner (the WHERE is strict on
  t1) and evaluates the conjunct at the join, so with no t1 row a1 * 6 is never
  computed (as PostgreSQL); the rules planner and the alt and noidx variants
  keep the LEFT JOIN and evaluate the WHERE on the NULL-extended row, and
  a1 * 6 overflows. w0-0218, `(select ... where 1 = b4 + 1) d join t1 on
  false`: lexdb runs the derived table (b4 + 1 overflows) before the join;
  PostgreSQL plans a join ON false as empty and never scans. Both orders are
  SQL's; lexdb gives the same rows wherever it does not fail.

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
