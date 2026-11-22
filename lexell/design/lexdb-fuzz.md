# lexdb-fuzz: a differential and metamorphic SQL fuzzer for lexdb

## Hand-over note (2026-11-22, after the long run)

**State.** The long run is done: 9 chunks of 1,200 s, 3 workers, against
9899f603 (main 45981146 with G1-G3 and C1 fixed): 10,958 s, 13,807 seeds,
2,068,887 queries, 19,885,108 statements, 1,230,791 TLP and 1,337,454 NoREC
forms ("The long run" below). Fixed on this branch (each with exec_fuzzfix4
or exec_fuzzfix5, batches on and off, against PostgreSQL 18; the doors' in
tds_fuzzfix2 and tns_fuzzfix2): wrong rows W7-W17 (but W18 and one ORDER BY
form), the server stops C1 and C2, the errors E6-E8, the gaps G1-G3. `recheck`
of every reduced case with the last binary leaves the kinds in "Left, ranked"
(W18 first).

**After (2026-11-22, on main 236c8513).** W18 (72f60d9c) and the set
operation's ORDER BY over chars of two lengths, V (970c0932, with the Oracle
door's set operation chars), are fixed; E9 is planned, not built (its section).
Tests exec_fuzzfix6, tds_fuzzfix3, tns_fuzzfix3.

Commits (on 45981146): 5313647f, bf99c8a8, 97746bac, 7b177a5f (the tool);
ba930de4 (G1-G3), 9899f603 (C1), 325e775e (E6), fd6aa85a (E7, E8), 9be8e932
(W7, W8), 9901d72c (W9, W10), 7d620fe7 (W12, W14, W15), 831983e3 (W14's IN),
35fc6e6d (W16), b2414cee (TPC-H q9 after W10), f8b9633d (W17), 7ccfe97b (C2),
9336f004 (W13), 48e5d608 (W11).

**How to resume.**

1. Build the switch-aware binary (needs `lexell/compiler/out/lxlc`, which
   `lexell/compiler/build.sh` builds): `python3 lexell/tools/lexdb_fuzz.py
   build --out ~/tpch-w/fuzz/lexdb-fuzz-<rev>-O`.
2. Run it in chunks under the shared bench lock, so timings can get in
   between (the long run's `~/tpch-w/fuzz/long/run.sh`):
   `flock -s ~/tpch/.bench.lock nice python3 lexell/tools/lexdb_fuzz.py run
   --bin BIN --out DIR --workers 3 --duration 1200 --seed S`, a new seed and
   out per chunk. Every server is pinned to CPUs 8-11 at nice 15.
3. `report DIR` prints a run's distinct failures with their reduced cases;
   `recheck DIR... --bin BIN` checks each reduced case again with another
   binary (after a fix: gone or STILL); `repro CASE.json --bin BIN --pg`
   reruns one case under every configuration. A `--work` (or `--out`) path
   must be short: PostgreSQL's socket path has 107 bytes at most.

**The tool's changes in this round.**
- reduce_case: the `ordered` fix checked (25 reductions of ordered queries,
  532 candidates without ORDER BY, none compared in order); its second pass
  reduced the base query also for a TLP or NoREC form's crash (the min_sql was
  the base query): the tree is reduced only when the failing statement is the
  query.
- G1 no longer floods the pg check: lexdb reads the syntax now (G1-G3 below);
  the generator is unchanged.
- A hang is not reported when PostgreSQL also takes the 5 s statement timeout
  (counted as `hang_pg_slow`); a hang's reduction keeps candidates PostgreSQL
  finishes.
- Ordered results are compared in order with trailing blanks dropped, and as
  multisets exactly (char(n) peers 'a' and 'a  ' in ORDER BY); a column both
  sides give as bpchar is compared without trailing blanks (which of two
  equal chars DISTINCT, UNION, GROUP BY, GREATEST or LEAST shows depends on
  the order rows come in).
- `recheck`.

Not done, still: comparison against SQL Server (gen_mssql.py) and the T-SQL
and Oracle doors in the fuzzer itself; all queries are PostgreSQL dialect (the
fixes were checked in the doors by tds_fuzzfix2 and tns_fuzzfix2).

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

## The long run (2026-11-22)

Nine chunks of 1,200 s, 3 workers each, every check, under the shared bench
lock (`~/tpch-w/fuzz/long/run.sh`: `flock -s ~/tpch/.bench.lock nice python3
lexdb_fuzz.py run --bin ~/tpch-w/fuzz/lexdb-fuzz-9899f603-O --workers 3
--duration 1200 --seed N*100000 --out ~/tpch-w/fuzz/long/cN`, a pinned copy
of the tool, 20 s between chunks so that timings got in), against 9899f603:
main 45981146 with G1-G3 and C1 fixed. A chunk's s is its workers' longest
elapsed; its cases are the failures recorded (each reduced, up to the caps),
by class; the last column counts timeouts not reported because PostgreSQL
timed out too.

| chunk | seed | s | seeds | queries | statements | TLP | NoREC | failures (wrong/crash/hang/error) | timeouts PG too |
|---|---|---|---|---|---|---|---|---|---|
| c1 | 100000 | 1211 | 931 | 139316 | 1342690 | 82618 | 89949 | 22/1/15/895 | 10 |
| c2 | 200000 | 1201 | 1599 | 239613 | 2302139 | 142606 | 154638 | 28/2/8/1671 | 10 |
| c3 | 300000 | 1234 | 1566 | 234651 | 2258208 | 139934 | 151680 | 31/0/6/1558 | 8 |
| c4 | 400000 | 1220 | 1910 | 286247 | 2752488 | 170007 | 184968 | 47/2/7/1942 | 13 |
| c5 | 500000 | 1219 | 1738 | 260381 | 2497871 | 155040 | 168665 | 24/0/9/1756 | 23 |
| c6 | 600000 | 1239 | 1349 | 202077 | 1936621 | 119754 | 130460 | 16/2/9/1317 | 20 |
| c7 | 700000 | 1222 | 1032 | 154724 | 1495115 | 92114 | 99950 | 21/0/15/1034 | 25 |
| c8 | 800000 | 1207 | 1816 | 272119 | 2612761 | 161866 | 176188 | 32/2/8/1826 | 21 |
| c9 | 900000 | 1204 | 1866 | 279759 | 2687215 | 166852 | 180956 | 29/0/8/1783 | 18 |
| total | | 10958 | 13807 | 2068887 | 19885108 | 1230791 | 1337454 | 250/9/85/13782 | 148 |

Every reduced case (one per signature, and every wrong result, crash and
hang) was checked again with the branch's last binary (`recheck`,
~/tpch-w/fuzz/long/recheck-*.txt): 1,000 cases (951 signatures). Wrong
results: 250, 7 still (four of one kind: a set operation's ORDER BY over chars
of two lengths; the two PostgreSQL bugs; W18). Server stops: 9, none. Hangs:
84, 42 still (timing: half of those first reported finish under 5 s the
second time). Errors (a-error, b-error, errcode): 651 cases, 560 still, by
far the most E9 (an unused derived column computed), the literal-only integer
overflow E6 leaves (22003 at PostgreSQL's planning), evaluation order (rules
and alt against on: bigint out of range, division by zero, where one plan
computes a value another does not), round(double precision, integer) that
lexdb accepts, and 53200 (max_statement_mem). The rechecks of the first five
chunks were run again after the last fix.

What the run found, wrong rows first:
- Wrong rows, all fixed but two: W7 (a semi join's residual on its key column;
  by far the most frequent: EXISTS, IN and NOT EXISTS, through pg, rules,
  alt, noidx, norec and tlp-where), W11 (an untyped value of a DISTINCT side
  of a set operation), W13 (a char IN a list of texts), W12 (a FROM
  subquery's hash on a float or date key), W14 (a subquery with a LATERAL over
  its own FROM), W15 (IN by a filtered index), W8 (MIN/MAX's first row with a
  HAVING), W16 (ORDER BY chars of two lengths), W17 (-2147483648's type); the
  known W9 and W10. Left: W18 (a hashed scalar subquery's float outer value)
  and a set operation's ORDER BY over chars of two lengths.
- Server stops, all fixed: W7's anti join (w0-0227), C2 (a constant IN as a
  semi join over empty tables; 4 cases), and C1 before the run.
- Errors: E6 (integer overflow: the most frequent difference of all, pg
  b-error, thousands of queries), E8 (= ANY / ALL of numerics), E7 (COALESCE),
  fixed; the kinds left are under "Left, ranked".
- Two PostgreSQL 18.6 bugs (at the end of the ranked list).
- The tool's own false positives: char peers in ORDER BY and DISTINCT (fixed in
  the tool).

### The fixes, as built

### G1-G3. A query in parentheses as a set operation's first operand (fixed before the run)

**Fixed (ba930de4; off the statement path in 325e775e).** lexdb_parse's
parenSelect reads `(SELECT ...)` as a first operand as setBranch reads the
others (nested, with WITH inside), then the set operations (INTERSECT first),
then ORDER BY and LIMIT of the whole; a query alone in parentheses takes them
as its own, one of each (PostgreSQL's insertSelectOptions: "multiple ORDER BY
clauses not allowed"). At the top, after WITH, in FROM (G2), a CTE's body
(G3), IN, ANY / ALL, LIKE ANY, a row IN, EXISTS, a scalar, ARRAY(...), INSERT,
CREATE VIEW, CREATE TABLE AS and COPY; in an expression or FROM a "(" starts
one when after its ")" comes ")", a set operation, ORDER BY or LIMIT
(parenQuery: `((select 1) + 1)` stays an expression, `((select 1), 2)` a
list). A row IN a set operation counted none of its columns (its first
query's now). SQL Server 2022 and Oracle 23ai agree through the doors
(tds_fuzzfix2, tns_fuzzfix2). A smoke run of fz3run's seed had none of the
1,838 pg a-errors G1-G3 gave it. Not supported still: a parenthesised join
(`from ((select 1) d cross join t)`: 0A000).

### W7. A semi join's filter on its key's column read as NULL (pg, rules, alt, noidx, norec, tlp; the run's most frequent wrong result)

```sql
create table t0 (a1 text);
insert into t0 values (NULL), ('a%b');
analyze;
select 'a' from t0 as q1 cross join t0 as q2
where exists (select 1 from t0 as q3 where q3.a1 = q1.a1 and q3.a1 <= q2.a1);
-- lexdb: 0 rows; PostgreSQL: 1
```

**Fixed (9be8e932).** Cause: hashSub (lexdb_plan) runs such a correlated
EXISTS, IN or NOT EXISTS once, hashed on its key (`q3.a1 = q1.a1`), and checks
the other conjunct per candidate row (a residual, `q3.a1 <= q2.a1`). keyLevel
outputs the residual's inner columns after the keys, but skipped a column
already in the subquery's list: the key itself. The level still read it from
the place after the keys, a NULL there, so the residual was never true: EXISTS
matched nothing, NOT EXISTS everything, and an anti join whose one filter is
`inner <> outer` (q21's form) indexed past the row and stopped the server
(w0-0227, "index out of range at lexdb_exec.lxl:1673"). The column is output
after the keys unless it is there already. Found 12 times in the run's first
chunk alone (EXISTS, IN, NOT EXISTS, through norec and tlp-where too:
w0-0173, w2-0191, w0-0223, w2-0183).

### W8. MIN/MAX read as an index's first row with a HAVING (pg; w2-0176)

```sql
create table t1 (b0 int primary key);
insert into t1 values (-1), (37);
select min(b0) from t1 having count(*) > 5;
-- lexdb: -1; PostgreSQL: no row
```

**Fixed (9be8e932).** minMax made a query whose list is MIN (or MAX) of one
column read the first row of an index's order, also with a HAVING, whose
aggregates are every row's (count(*) counted 1, bool_and saw one value). Not
with a HAVING now.

### W9. A set-returning function in the select list made its rows after DISTINCT and ORDER BY (known)

```sql
select distinct unnest(array[2, 1, 2]);       -- lexdb: 2, 1, 2; PostgreSQL: 1, 2
select unnest(array[3, 1, 2]) order by 1 desc; -- lexdb: 3, 1, 2; PostgreSQL: 3, 2, 1
```

**Fixed (9901d72c).** The row path deduplicated and took ORDER BY's
values per row of the query, then expandSrfs made each row into the function's
rows (which kept their row's sort values), and a top-N or an early stop cut
before it. As PostgreSQL's ProjectSet below Sort and Unique: with such a
function, no DISTINCT, top-N or early stop per row; after expandSrfs, ORDER
BY's items that are outputs (a position, a name, the same expression:
lexdb_plan.orderOutAt) are read from the rows made, and DISTINCT goes over
them. An ORDER BY on an expression that is no output keeps its row's value.
Not changed: generate_series in the select list is not supported (42883:
"function generate_series with 2 arguments does not exist").

### W10. Chars of two lengths were two values in GROUP BY and DISTINCT (known; W6's note)

```sql
select x, count(*) from (select 'a'::char(3) as x union all select 'a'::char(5)) d group by x;
-- lexdb: two groups; PostgreSQL: one ('a  ', 2)
```

**Fixed (9901d72c).** A GROUP BY key that is a char of no one length (a
CASE or union of chars of two lengths, a cast with none: lexdb_bind.groupKind;
a char(n) column's values all have n, and stay exact) and every char output of
a DISTINCT (lexdb_bind.distKinds) are compared without trailing blanks
(COLL_PAD), where PostgreSQL's rules hold (pgRules); which of the equal values
is shown is the first read, as PostgreSQL's; an aggregate's argument of that
kind too (count(DISTINCT x) counted 'a  ' and 'a    ' as two). A FROM
subquery's or view's char(n) column now keeps its length (bpLen of its
expression, not for a set operation's column): without it q9's nation
(n_name char(25) through a derived table) was grouped by its padKey, +4.5%
instructions (iq.sh), main's again after (b2414cee). Not changed: GREATEST and LEAST of chars of two
lengths (which of two equal values they give; the fuzzer now compares char
columns without trailing blanks, see "The tool's changes").

### E6. Integer arithmetic past int4 and int2 (G4; known: x * 7919, smallint + smallint)

```sql
select x * 7919 from t;          -- x int up to 1M; lexdb: 7919000000; PostgreSQL: 22003 integer out of range
select pg_typeof(s + s) from t;  -- s smallint; lexdb: integer; PostgreSQL: smallint
```

**Fixed (325e775e).** lexdb computes integers in 64 bits. resolve now casts
+ - * / of smallints and integers, unary minus and abs of one, to their type
(lexdb_bind.intChecked: the wider of the two, two smallints a smallint, as
exprOid now says too), and the cast is the range check, in eval, bxEval and the
batches (BNode.Fit after the integer kernels: a batch condition keeps them).
Not checked, by design: arithmetic of literals alone (`2147483647 + 1`):
Oracle's NUMBER literals are lexdb integers at its door, which shares the
binder; PostgreSQL folds and raises such a constant when it plans (as the
excluded `1 % 0`). UPDATE ... SET col = col + 1 into a smallint or integer
column is not cast (resolveAssign): the column's own check stands for it, and
binding it is cheaper than before (UPDATE by key -223 instructions). An index
on an expression and a partial index's predicate are matched without the casts
(lexdb_plan.sameWritten). T-SQL: 22003 is SQL Server's 8115, and SQL Server
2022 agrees on +, -, *, /, unary minus, ABS and smallint + smallint (a
smallint there too; tds_fuzzfix2). Not changed: << of integers is computed in
64 bits (PostgreSQL's int4shl wraps: `1 << 31` is -2147483648 there); an index
on (x + 1) stores x + 1 of a row without the check (PostgreSQL fails the INSERT
or CREATE INDEX).

### E7. COALESCE evaluated every argument (known; E5's decision reversed)

```sql
select coalesce(id, 1 / (id - id)) from t;   -- lexdb: 22012; PostgreSQL: id
```

**Fixed (fd6aa85a).** eval and bxEval evaluate COALESCE's arguments in
order up to the first not NULL (fnRefOf binds it as FN_LAZY; the batches'
compiled expressions run bxEval). `coalesce(1, 1 / 0)` too, as PostgreSQL's
planner stops folding there. T-SQL's COALESCE and ISNULL agree with SQL
Server 2022. Changed beyond PostgreSQL: Oracle's NVL, which the door reads as
COALESCE, stops at its first value too; Oracle evaluates both (NVL(id, 1 / (id
- id)) is ORA-01476 in Oracle 23ai, a value in lexdb). A door gap, left (an NVL
of its own would need COALESCE's typing again).

### E8. An integer = ANY / ALL of numerics failed 22P02 (pg; w0-0190, w0-0071)

```sql
select 1 = all (select 1.5);   -- lexdb: 22P02 invalid input syntax for type bigint: "1.5"; PostgreSQL: f
```

**Fixed (fd6aa85a).** quantOf read each element of the array (a
subquery's values made one) as x's type, a bigint for an integer x. An element
that is no integer is read as a numeric now (int = numeric). SQL Server and
Oracle agree (tds_fuzzfix2, tns_fuzzfix2).

### W11. An untyped value of a set operation's DISTINCT side (pg; chunks 2-5, 8 cases: w1-0107, w0-0233, w0-0384, w1-0583 ...)

```sql
create table t1 (b1 char(3));
insert into t1 values ('B');
(select distinct 'a' from t3) union all (select b1 from t1);
-- lexdb: a char column ('B  '); PostgreSQL: a text ('B')
```

**Fixed (48e5d608).** A side that sorts or compares its untyped value
(DISTINCT, GROUP BY) resolves it to text in PostgreSQL, and text then comes
first in the operation's common type; lexdb's branchOid took every untyped
value as unknown, so the column was the other side's char. Without DISTINCT or
GROUP BY the column is still a char, as PostgreSQL's.

### W13. A char IN a list with texts compared as texts (pg; chunks 2-5, 7 cases: w1-0247, w2-0145, w1-0418 ...)

`c in ('a ', cast(null as text), '', 'z')` over a char(3) 'a  ' is true in
PostgreSQL: its IN takes the common type of x and the list's values that are no
column, x first, a char, so the text 'a ' is the char 'a'; a column in the
list is compared as = compares it (a char beside a text column as texts).
**Fixed (9336f004):** bpCall trims a list's value of a text type that is no
column too (it trimmed one only when every value was a char, a varchar or
untyped).

### W17. -2147483648 was a bigint (pg; chunk 3 w0-0505, chunk 5 w0-0199)

`1 / nullif(sum(-2147483648), 0)` is a bigint 0 in PostgreSQL (its lexer reads
a negative literal whole: an int4, its sum a bigint) and was a numeric in
lexdb (the negation of the bigint 2147483648; sum of a bigint is a numeric,
E4). **Fixed (f8b9633d):** exprOid types that negation as an integer.

### C2. A constant IN as a semi join stopped the server (on crash; chunks 2 and 4: w0-0345, w1-0324, w1-0162, w2-0304)

```sql
create table t0 (a0 text, a1 text, a4 bigint);
create index t0_i1 on t0 (a4, a0);
create index t0_i2 on t0 (a1);
analyze;
select 1 from t0 as q1 where 'a' in (select q2.a1 from t0 as q2 where q2.a4 = 1);
-- lexdb: "index out of range at lexdb_access.lxl:753" (keyType's, lexdb_plan.lxl:6961, batches off)
```

**Fixed (7ccfe97b).** Over empty tables (after ANALYZE) semiLevel made the
IN a level looked up per row (inLook; with rows a hash was cheaper), whose
table semiLookAdd takes from the subquery's level; a condition of no column is
also checked once, so the subquery then ran over the level it no longer had
(noTable, no indexes). An IN whose value has no column is no semi join now (it
is the subquery's set, run once).

### C1. NOT over a batch's NULLs stopped the server (tlp-group; smoke run)

`select count(*) from t where not (b >= cast(null as int))` over a bigint b
holding -9223372036854775807: BNode.Not computed 1 - v also for a NULL, whose v
is the column's value, and Lexell's checked arithmetic stopped the server.
**Fixed (9899f603):** 0 maps to 1, anything else to 0.

### W12. A FROM subquery hashed on a float key against an integer (pg; chunk 2 w0-0130)

```sql
create table t1 (b0 int primary key, b4 numeric(6,2));
insert into t1 values (0, 0);
select 1 from t1 as q1, (select cast(b4 as float8) as x4 from t1) as d2 where d2.x4 = q1.b0;
-- lexdb: 0 rows; PostgreSQL: 1
```

**Fixed (7d620fe7).** A join's level that is a FROM subquery (a view, a
CTE) is hashed on its rows' values as they are (keyPart), and its probe was
not made the column's type as a table's is (keyVal): a float 0 and an integer
0, a date and a timestamp, are different keys. Such a conjunct is no hash key
of a FROM subquery now unless its kinds hash alike (hashKeyTypes, as a
semi join's: integers and numerics by value, texts and varchars, one type
each); it stays the level's condition.

### W14. A hashed correlated subquery with a LATERAL over its own tables found nothing (pg; chunk 2 w1-0186, w2-0208)

```sql
create table t0 (a0 text, a5 int);
insert into t0 values ('a', 1);
select exists (select 1 from t0 as q2 join lateral (select 1 from t0 as q4 where q4.a5 = q2.a5) as l3 on true
               where q2.a0 = q1.a0) from t0 as q1;
-- lexdb: f; PostgreSQL: t
```

**Fixed (7d620fe7).** E1 kept per row a subquery whose own subquery reads
an outer value; one whose LATERAL reads the subquery's own columns (q2.a5) was
still run once and hashed on its key (a mark, semi or scalar join), and the
LATERAL then gave no rows. Such a subquery is run per row now (hashSub: a correlated
FROM subquery of its own; one in an expression, q20's shape, still hashes:
exec_apply). The same subquery not correlated, IN's set as a semi join (chunk
2 w0-0348), lost the LATERAL's rows too: semiLevel leaves such a subquery to
the subquery paths (IN's set run once, EXISTS per row; 831983e3). Not
chased: why a run once loses the LATERAL's rows (its parameter's place,
presumably, as E1's; or semiJoins' alternative plan).

### W15. IN looked up per row through a filtered index (pg, rules, alt, noidx; chunk 1 w2-0188..0191)

```sql
create table t0 (a0 text, a1 text, a2 int);
insert into t0 values ('bb', 'bb', NULL);
create index t0_i0 on t0 (a1, a2) where a2 > 2;
create index t0_i1 on t0 (a1, a0);
select 1 from t0 as q1, t0 as q2 where q2.a0 in (select q3.a1 from t0 as q3 where q3.a1 = q1.a0);
-- lexdb: 0 rows; PostgreSQL: 1
```

**Fixed (7d620fe7).** inLook (optimizer 50, 5c: x IN (subquery) read
per outer row by the subquery's column) took the first index whose first column
is that column, also a filtered one whose predicate the query does not imply.
Not a filtered one now (as every other path choice: `pred.isSome() { continue }`).

### W18. A correlated scalar subquery hashed on a numeric key against a float outer value (noidx, pg; chunk 9 w1-0263)

```sql
create table t1 (b2 numeric(6,2));
insert into t1 values (1);
select (select sum(1.5) from t1 as q10 where q10.b2 = d2.x9) from (select ceil(1) as x9 from t1) as d2;
-- lexdb without an index on b2: NULL; PostgreSQL, and lexdb with one: 1.5
```

**Fixed (72f60d9c).** hashSub (a correlated scalar subquery, EXISTS, NOT EXISTS
or IN run once and hashed on its key) took any outer value that is a bare
parameter as of the key's kind (hashKeyTypes), and a derived table's column is
one: outerRef types only a table's columns and chars. The hash compares values
as they are (W12's mismatch), so the float 1 found no numeric 1.00. The
parameters' types are known where the subquery is planned: its refs, in the
terms of the query around it, typed there (lexdb_bind.refTypesOf), and
hashKeyTypes takes a typed parameter's kind as a column's (semiTypes: integers
with numerics, one float type with itself). A float beside a numeric or an
integer, or a numeric beside a float, is no hash key now: the subquery runs per
row ("per row, on d.x"); an integer or numeric beside a numeric is still hashed.
A parameter of no known type keys as before.

A matrix over int, bigint, smallint, numeric, numeric(6,2), real and float8 (each
against each, with and without an index on the key; a scalar subquery and EXISTS,
NOT EXISTS, IN, NOT IN over a derived table's column and a table's; a hash join
on a derived table; a LATERAL with an aggregate, plain and grouped; the values
0, -0, 0.1, 1, 1.5, 2.25, NULL) against PostgreSQL 18, batches on and off and the
rules planner: 1,372 queries, 180 differences at main (60 queries, all W18's
shape: a scalar subquery, EXISTS or NOT EXISTS without an index, a float beside
a numeric or integer key either way), none after. The semi joins (semiKeys, which
substitutes the outer values and types them), FROM subquery hash joins (W12) and
lateralKeys gave none at main.

### V. ORDER BY a set operation's char column whose values have two lengths (pg; chunk 2 w1-0284, chunk 7 w1-0085, chunk 8 w1-0281, w1-0406)

```sql
create table t0 (a2 char(3));
insert into t0 values ('z');
(select true as x3, q1.a2 as x4 from t0 as q1) union (select false, reverse(q5.a2) from t0 as q5) order by 2 desc, 1 nulls first;
-- lexdb: t|z  ; f|z    PostgreSQL: f|z; t|z  (bpchar's order: 'z' and 'z  ' tie, the next key decides)
```

**Fixed (970c0932).** planSet's ORDER BY kinds were the outputs' exact kinds
(outRefKind); a set operation's char column (a char(n) beside a text, a literal,
a char of another length: PostgreSQL's common type is bpchar, its values keep
their own lengths) sorts now under setKindsOf's kinds, which its DISTINCT
already used: without trailing blanks where PostgreSQL's rules hold. Sel.ordKinds
carries them to every sort of a set operation: runSorted, lexdb_setop.held (the
held path) and its top-N. A FROM subquery over a set operation was already right
(its char column has no length there, groupKind). Not changed: T-SQL (its
collations already compare without trailing blanks).

The Oracle door: a set operation's column of CHARs of two lengths, or of a CHAR
and a VARCHAR2, is a VARCHAR2 in Oracle (its blanks significant: 'a' < 'a  ',
and UNION keeps both), and a CHAR's value in it keeps its blanks. lexdb took
PostgreSQL's rules there (pgRules holds in the Oracle door): its UNION made 'a  '
and 'a    ' one row, and a CHAR's value in a VARCHAR2 column lost its blanks. A
set operation's statement carries its dialect now (lexdb_parse.setOf:
Stmt.mdialect), and in the Oracle door its kinds are exact and its chars keep
their blanks.

Found, not fixed (T-SQL door, display only): a set operation of a char(3) and a
varchar(10) shows its values as the first side's char(3) (lexdb pads the
varchar's 'a' to 'a  '), and of a varchar first, the char's values without their
blanks; SQL Server's column is a varchar(10) with each value as it is (a char's
padded). Of a char(3) and a char(5), SQL Server pads to 5. Ordering and equality
agree (T-SQL's collations ignore trailing blanks). lexdb's T-SQL char(n) is a
varchar(n) padded where it is sent (Ty prec TS_CHAR), so the fix is the TDS
column's type of a set operation's output.

### E9. An unused derived-table column is computed: the plan (not built)

`select 1 from (select 1 % b0 as x from t1) d` over b0 = 0 fails 22012;
PostgreSQL never computes x (a pulled-up subquery's unused targets are never
evaluated; remove_unused_subquery_outputs makes the others NULL constants).
Not built in this round: the place where it is cheap to do lacks what it needs.

- What is known where. planSelect collects every column name the statement
  and its nested subqueries use (stmtNames: needNames, needStar) before
  buildQuery, which passes them to planFrom for narrow's table columns; but
  bindFrom plans each FROM subquery (planSub) without them, and the subquery's
  Sel, its logical plan (takeLp, the outer item's plan) and its pipeline
  (pipeSelMain) are all made from its select list inside that planSelect. A
  rewrite after planSub would have to change three copies.
- The change. Prune syntactically, before planSub: in bindFrom's `f.sub >= 0`
  branch, plan a copy of subs[f.sub] whose select items no name of the
  statement reads replaced by a NULL under the item's own output name. An item's
  name: f.cols[i] where the FROM item renames its columns, else its alias or
  derived name. Kept whole: needStar (`*`, `d.*` read, NATURAL), the derived
  table's alias read as a name (a whole-row value), a CTE's use, a view. Not
  pruned in a subquery with a set operation, DISTINCT or DISTINCT ON, GROUP BY,
  grouping sets, HAVING or ORDER BY (positions and aliases name the items), a
  set-returning function in its list, or for an item with an aggregate, a window
  function, a volatile function or a subquery. A LATERAL subquery is pruned the
  same way (E9's "a LATERAL's unused column"). The names are conservative (any
  use of the name anywhere keeps it), which is what makes the rule safe.
- The cost. bindFrom needs selNames and star: two more arguments on every
  statement's call (a point select's too, ~2 instructions), or the rewrite in
  planSelect behind `len(s.subs) > 0` (one test per statement). Either has to be
  measured against the point-select gate (must be equal or lower); the pruned
  copy itself costs only statements with a FROM subquery.
- Tests: E9's four shapes (22012, 22003 of bigint, numeric(p,s) overflow, a
  LATERAL), each kept-whole rule above with the error still raised, a renamed
  column list, batches on and off; TPC-H (q7, q8, q9, q13, q22 have FROM
  subqueries: their unused columns, if any, are not computed after).

### Gates

- Suite at every commit (288 tests at the last).
- In process, LXL_HASH_SEED=1, per statement against main (the coordinator's
  bin/pf2: 131,404.7, 55,121,322.8, 55,142,366.9): point select 131,136.7 (-268.0), INSERT 55,121,322.8
  (equal: rounds within 0.05), UPDATE by key 55,142,140.9 (-226.0), at the
  last code commit (48e5d608; 7d620fe7 gave -272.0, equal, -226.0). The UPDATE's
  saving is resolveAssign (no `typing()` per SET, none of resolve's checks
  for `v + 1`), the select's distKinds (no collKind of a text output that has
  no collation). An earlier version that put intArith's check inside resolve's
  Bin arm cost the select +33 (resolve's frame); the check is a helper
  (intChecked) now. Wire (pts.sh) not run.
- TPC-H SF1 (~/tpch-w/fuzzfix2, alternated twice against main f1623851,
  lexdb only): 22 checksums equal and right in every run. Rounds 1 and 2 (the branch at
  the W9/W10 commit): q9 +5.4%, its instructions +4.5% (iq.sh: 15.96G against
  15.26G): W10's GROUP BY kind grouped q9's nation (n_name char(25) through
  the derived table profit) by its padKey; fixed (a FROM subquery's char(n)
  column keeps its length: 15,263.2M against 15,262.3M); q15 +2.7% and q16
  +1.8% with main's instructions (2,788.8M against 2,789.0M; 2,169.9M against
  2,166.6M, +0.15%): placement. Rounds 3 and 4 (the branch at b2414cee): best
  of two each, total 9,429 ms against main's 9,424 (1.000), no query over 1.5%
  (q20 +1.5%: 265.7 against 261.8; q17 +1.2%, q13, q19 +1.0%, q21 -2.0%). The
  commits after b2414cee (W17, C2, W13, W11) change no TPC-H plan or
  expression (a negative literal's type, a constant IN, a char IN a list of
  texts, a set operation's untyped value). The data copy is deleted.
- lexdb_exec: 20,164 lines at 45981146, 20,205 after (the select list's
  set-returning rows sorted and made distinct after expandSrfs, COALESCE's lazy
  eval, ORDER BY's kinds, a FROM subquery's char length, a set operation's
  untyped sides; the helpers in lexdb_bind and lexdb_plan).

Of W18 and V (on main 236c8513):
- Suite at both commits (291 tests).
- In process, LXL_HASH_SEED=1, per statement against main 236c8513 (the
  coordinator's bin/fz2: 131,136.67, 55,121,322.77, 55,142,141.18 in the same
  runs): point select 131,136.67 at both commits (equal), INSERT 55,121,322.72
  (4 rounds; 2 rounds gave 322.86 and 323.18 with main's own rounds 9,000
  instructions apart: noise), UPDATE by key 55,142,141.05 and 55,142,140.84.
  Neither change is on these statements' path (hashSub's call and a set
  operation's planning only). Wire (pts.sh) not run.
- TPC-H SF1 (~/tpch-w/w18, alternated twice against main 236c8513's
  lexdb-fz2-O, lexdb only): 22 checksums equal in every run; best of two, total
  9,432 ms against 9,524 (0.990). Over 1.5%: q17 +2.4% (24.5 against 25.1
  ms) and q11 +1.9% (94.4 against 96.2) with main's instructions (iq.sh, two
  runs each: q17 139.00M and 138.99M against 139.02M and 138.99M; q11 574.72M
  and 574.72M against 574.72M and 574.76M): placement; q16 +1.5% (2,170.9M and
  2,169.7M against 2,170.6M and 2,170.5M). Round 1's base ran right after the
  load (q6 317 ms against 181 after). The data copy is deleted.
- recheck of every reduced case of the long run with 970c0932
  (~/tpch-w/fuzz/long/recheck-w18.txt): 882 cases (817 signatures; one per
  signature, every wrong result, crash and hang), 509 still fail: wrong 250, 2
  still (the two PostgreSQL bugs below; W18's and the four ORDER BY cases
  gone); crashes 9, none; hangs 84, 41 still; errors 539, 466 still.
- lexdb_exec: 20,205 lines at 236c8513, 20,211 after (refKindIn, the set
  operation's kinds; refTypesOf is in lexdb_bind, the keys in lexdb_plan).

### Left, ranked

Wrong rows first, then crashes, then wrong errors, then gaps and speed. None of
these is fixed; each has a reduced case in the run's directories (`recheck`'s
STILL lines, ~/tpch-w/fuzz/long/recheck-all.txt).

W18 and the set operation's ORDER BY over chars of two lengths (1 and 2 of
this list before) are fixed (W18 and V above); after them the run leaves no
wrong row of lexdb's own but those PostgreSQL's two bugs give (below).

1. **The T-SQL door's type of a set operation's char and varchar column**
   (display only; found by tds_fuzzfix3, not the fuzzer): `SELECT a FROM q0
   UNION ALL SELECT b FROM q1` of a char(3) and a varchar(10) is sent as the
   first side's char(3) (a varchar's 'a' shown 'a  '), with the varchar first
   the char's values lose their blanks, and a char(3) beside a char(5) is not
   padded to 5; SQL Server's column is a varchar(10) (a char(5)), each value as
   its side has it. Order and equality agree. See V.
2. **E9. An unused output of a derived table is computed** (pg a-error; the
   most frequent remaining error kind). `select 1 from (select 1 % b0 as x
   from t1) d` fails 22012 over b0 = 0; PostgreSQL never computes x (a pulled-up
   subquery's unused targets; remove_unused_subquery_outputs for the others).
   The same with `a1 + a1` past 2^63 (22003), a LATERAL's unused column, a
   cast past numeric(p,s) (22003 numeric field overflow). Fixing it means
   pruning a FROM subquery's outputs the outer query does not read (not under
   DISTINCT, a set operation, a set-returning or volatile function): a planner
   change of its own, which would also save work. Not built: the plan is under
   E9 above.
3. **Evaluation PostgreSQL skips by its plan** (pg a-error and errcode, a few
   per chunk): HAVING false over an aggregate whose argument fails (PostgreSQL
   plans a One-Time Filter and never reads the input: w0-0174), LIMIT 0 (the
   executor never pulls a row: w0-0083), E5's semi join run before its query,
   and which of two errors comes first (22012 in lexdb, 22003 in PostgreSQL:
   chunk 3 w2-0337). Each is lexdb computing a value PostgreSQL does not; the
   rows agree wherever neither fails. Arithmetic of literals alone (E6's
   exemption: `(2147483647 + 1) < 1` over an empty table, 22003 in
   PostgreSQL at plan time) is the excluded constant folding.
4. **Timeouts PostgreSQL does not have** (on and batch hangs, PostgreSQL under
   5 s; 6 to 15 per chunk, half of them gone on a recheck, so near the
   limit): products of CTEs and LATERAL that PostgreSQL's plan avoids or
   cuts (`... order by <constant> limit 2` over a 10^9-row product: PostgreSQL
   drops the constant sort key and stops after 2 rows; w0-0098), big
   lateral and semi join trees (w2-0199, w1-0108). Speed, not rows.
5. Oracle door: NVL stops at its first value (E7); SUM of quotients of 37
   places fails ORA-01426 where Oracle keeps 40 significant digits (`sum(10 /
   (id - 3001))` over 3,000 rows: Oracle -85.83749889959187114343792091258973719962;
   lexdb's numerics hold 38 digits, so its answer could not be Oracle's anyway); a
   number(6,2) read through a derived table is shown without its scale (0 where
   Oracle shows 0.00; tns_fuzzfix3 multiplies it by 1 instead).
6. Gaps left from before: G5 (int::bool, num_nonnulls, scale, min_scale,
   trim_scale), generate_series in the select list, `round(round(0), 1)`
   accepted where PostgreSQL has no round(double precision, integer),
   parenthesised joins (`from ((select 1) d cross join t)`: 0A000), 53200 for a
   5,000,000-row product PostgreSQL returns (max_statement_mem).

Two PostgreSQL 18.6 bugs, found by the pg check (neither reported):
- chunk 2 w2-0235: `select 'a' from lateral (select q3.b0 as x9, cast(null as
  text) as x10 from t1 as q3 left join (select b5 as x8 from t1 group by b5)
  as d4 on q3.b3 = d4.x8) as l2 full join t0 as q11 on true where l2.x9 =
  l2.x10`, t0 empty, gives a row: its plan (a Nested Loop Left Join) has
  dropped the WHERE, whose `x9 = NULL` is never true. lexdb gives none.
- chunk 3 w2-0223: `create table t0 (a0 int primary key, a1 numeric(6,2));
  insert into t0 values (32, 3.333); select 1 from t0 as q1 join t0 as q2 on
  q1.a1 = q2.a1 and q1.a0 = q2.a0 join t0 as q3 on q1.a0 = q3.a0 and q1.a1 =
  q3.a0` gives a row (3.33 = 32 is false): the plan is one `Seq Scan ...
  Filter: (a1 IS NOT NULL)`, PostgreSQL 18's self-join elimination having
  dropped `q1.a1 = q3.a0`. lexdb gives none.

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

- (G1-G3 are fixed: see "The fixes, as built"; G4 is E6, fixed but for arithmetic of literals alone.)
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
