# lexdb: MATCH_RECOGNIZE (row pattern recognition) in all three doors

Design only (2026-11-14); nothing is built. This is the design an implementer follows without asking
questions. Read design/lexdb.md 9.10, 9.12, 9.46 and 9.121 first (FROM subqueries, LATERAL, window
functions, and MERGE, which is the model: one shared Stmt, planner and executor with three parser front
ends). Facts marked **(V)** were checked on Oracle Database Free 23ai (gvenzl/oracle-free:slim, by hand
through sqlplus, 2026-11-14). Facts marked **(U)** are not verified; M5 verifies them.

## 1. What and why

SQL:2016 row pattern recognition (feature R010, "MATCH_RECOGNIZE in FROM") finds sequences of rows that
match a regular expression over row predicates: V-shapes in prices, sessions, runs, gaps. Oracle has had
it since 12c. PostgreSQL 18 and SQL Server 2022 do not have it. lexdb gets it once, in the shared
planner and executor, and accepts the same clause in all three doors:

- **Oracle door:** Oracle's syntax and semantics, its errors (ORA-62500 to ORA-62521) and its result
  names (upper case unless quoted).
- **PostgreSQL and T-SQL doors:** the same clause (it is the SQL:2016 standard's) after a FROM item,
  with that door's identifier folding, quoting, ORDER BY NULL order, aggregate types and errors.
  Section 11, D1 is the decision.

Not in scope: the window form (R020: `WINDOW w AS (... PATTERN ... DEFINE ...)` with INITIAL/SEEK,
which is also what PostgreSQL's unfinished row pattern patch does). INITIAL and SEEK are only allowed
there in the standard, so they are not accepted here. The matcher below could later serve R020 too.

## 2. Syntax (all doors)

```
from_item MATCH_RECOGNIZE (
    [ PARTITION BY col [, col ...] ]
    [ ORDER BY sort_item [, sort_item ...] ]          sort_item: col [ASC|DESC] [NULLS FIRST|LAST]
    [ MEASURES expr [AS] alias [, ...] ]
    [ ONE ROW PER MATCH
    | ALL ROWS PER MATCH [ SHOW EMPTY MATCHES | OMIT EMPTY MATCHES | WITH UNMATCHED ROWS ] ]
    [ AFTER MATCH SKIP { PAST LAST ROW | TO NEXT ROW | TO [FIRST | LAST] var } ]
    PATTERN ( pattern )
    [ SUBSET name = ( var [, var ...] ) [, ...] ]
    DEFINE var AS condition [, ...]
) [ [AS] alias [ ( col, ... ) ] ]
```

The clauses come in exactly this order **(V)**. ORDER BY may be left out (rows in input order) **(V)**;
DEFINE may not **(V)**. Defaults: ONE ROW PER MATCH; for ALL ROWS, SHOW EMPTY MATCHES **(V)**; AFTER
MATCH SKIP PAST LAST ROW. `SKIP TO var` is `SKIP TO LAST var`.

```
pattern := alt
alt     := seq { '|' seq }                    an empty seq is an error (Oracle: ORA-00931)
seq     := term { term }
term    := primary [ quant ]
primary := var | '^' | '$' | '(' alt ')' | '{-' alt '-}' | PERMUTE '(' alt { ',' alt } ')'
quant   := ( '*' | '+' | '?' | '{' n '}' | '{' [n] ',' [m] '}' ) [ '?' ]     a trailing ? is reluctant
```

`from_item` is a table or view, a subquery, a CTE, a FROM function, or (non-Oracle doors) a LATERAL
subquery or T-SQL `CROSS/OUTER APPLY` item. The input may have its own alias (`FROM t x
MATCH_RECOGNIZE (...)`) **(V)**, but that alias is visible neither inside the clause (ORA-62504) nor
outside it (ORA-00904) **(V)**. Only the output alias names the result.

Restrictions lexdb takes from Oracle in **all** doors (each also refused by Oracle **(V)**):

- PARTITION BY and ORDER BY take simple column names only. Oracle: a qualified name is ORA-01748, and an
  expression is ORA-02000 "missing PATTERN keyword". PG and T-SQL: 42601. Exception (D3): the PG and
  T-SQL doors accept any expression in ORDER BY, which the standard allows.
- No empty pattern `()`, and no empty alternative `(a | )` (ORA-00931).
- No quantified group that can match empty: `(a*)*`, `(a?)+`, `(^)?` (ORA-62513). A quantifier on a
  single variable is always allowed.
- `{0}`, `{0,0}` and `{n,m}` with m < n are ORA-62501.
- `CLASSIFIER(var)` is ORA-00907 (Trino accepts it; Oracle does not).
- Aggregates: COUNT, SUM, AVG, MIN and MAX only, with no DISTINCT, FILTER or ORDER BY. Anything else is
  ORA-62512 (COUNT(DISTINCT) and LISTAGG are refused **(V)**).

Where the SQL:2016 standard differs from Oracle (as far as this design relies on it): the standard
allows `()` and empty-capable quantified groups (with rules that stop empty loops), and expressions in
ORDER BY. Neither Oracle nor lexdb accepts these, except ORDER BY expressions outside the Oracle door.

## 3. Semantics (Oracle's, which are the standard's for everything lexdb accepts)

**Matching.** Each partition is sorted by ORDER BY (equal keys: input order; Oracle's tie order is
unspecified). A search starts at a row and tries the pattern **anchored there**, in *preference order*:
- alternatives left to right;
- a greedy quantifier tries more iterations first, a reluctant one fewer;
- `PERMUTE(a, b, c)` is the alternation of all permutations in lexicographic order of the list
  (abc | acb | bac | bca | cab | cba) **(V)**.

The first mapping found is the match, not the longest. If the start row has none, the search moves to
the next row. Each row consumed is mapped to one primary variable. A variable's DEFINE must be TRUE for
the row (NULL or FALSE fails). A variable with no DEFINE is always true, but it still needs a row. `^`
matches only at the partition's first row, `$` only after its last **(V)**.

**Empty matches.** A pattern such as `a*` may match no rows. That is still a match: it gets a
MATCH_NUMBER, gives a row in ONE ROW PER MATCH (COUNT(*) 0, the other measures NULL) **(V)**, and the
next search starts at the next row.

**After a match** [s, e) (rows s..e-1; s = e if empty), the next search starts at:

| SKIP | next start |
|---|---|
| PAST LAST ROW | e, or s + 1 for an empty match |
| TO NEXT ROW | s + 1 |
| TO FIRST v / TO LAST v (v a variable or a subset) | the first / last row mapped to v. No such row: ORA-62514 "AFTER MATCH SKIP TO variable is not bounded in the match found." **(V)**. The row is s: ORA-62517 "Next match starts at the same point last match started." **(V)**. Both are errors at run time. |

**MATCH_NUMBER()** counts the matches of a partition from 1, empty ones included **(V)**.

**Rows out.**
- ONE ROW PER MATCH: one row per match. Its columns are the PARTITION BY columns, then the measures.
- ALL ROWS PER MATCH: one row per matched row that is not excluded, in match order. Its columns are the
  PARTITION BY columns (in PARTITION BY order), then the ORDER BY columns (in ORDER BY order; in the
  PG/T-SQL doors only the items that are plain columns), then the measures, then the input's other
  columns in input order **(V)**.
- SHOW EMPTY MATCHES: an empty match gives one row: the start row's columns, COUNT 0, the other
  measures NULL.
- OMIT EMPTY MATCHES: an empty match gives no row.
- WITH UNMATCHED ROWS: also shows empty matches, and adds each row that is in no match, with every
  measure NULL, MATCH_NUMBER included **(V)**.
- With SKIP TO NEXT ROW or TO var, matches overlap and a row can be output more than once **(V)**.
- A row "in no match": a failed start row at or past the end of every match found before it.
- A duplicate output name is ORA-00918 "NAME: column ambiguously specified - appears in  and " **(V)**.
  This also catches a measure named like an input column under ALL ROWS, and a column in both PARTITION
  BY and ORDER BY. PG: 42701 `column "v" specified more than once`. T-SQL: 8156 "The column 'v' was
  specified multiple times for 'mr'."
- No output column at all (ONE ROW, no PARTITION BY, no MEASURES) is ORA-30732 "table contains no
  user-visible columns" **(V)**; PG and T-SQL: 42601.

**Exclusion** `{- ... -}`. The rows it matches are mapped and counted (COUNT(*), navigation and
CLASSIFIER see them), but ALL ROWS PER MATCH does not output them **(V)**. ONE ROW's measures see them
too: a match ending in an excluded row has that row's CLASSIFIER **(V)**. Exclusion with WITH UNMATCHED
ROWS is ORA-62515 **(V)**.

**Expressions in MEASURES and DEFINE.** A column reference is `col` (the universal variable: every row of
the match) or `v.col` (v a primary variable or a subset). In DEFINE the row being tested counts as
mapped to the variable being defined. RUNNING means the rows of the match up to the current row; FINAL
means the whole match.

| form | value |
|---|---|
| `col`, `v.col` | LAST(...) with offset 0 |
| `LAST(x [, n])`, `FIRST(x [, n])` | x on the n-th row (from 0) counting back from the last, or on from the first, of the rows mapped to x's variable; none: NULL **(V)**. Stays inside the match. |
| `PREV(x [, n])`, `NEXT(x [, n])` (n defaults to 1) | x on the row n rows before / after the row x names (x may be FIRST/LAST(...)). It may leave the match but not the partition: outside it, NULL **(V)**. |
| COUNT(*) | rows of the match; `COUNT(v.*)` rows mapped to v; `COUNT(x)`, SUM, AVG, MIN, MAX over x on the rows mapped to x's variable |
| CLASSIFIER() | the current row's variable, as written (Oracle: upper case unless quoted **(V)**); NULL in an empty match. In DEFINE: the variable being defined **(V)**. |
| MATCH_NUMBER() | the match's number; allowed in DEFINE **(V)** |

- RUNNING or FINAL may come before an aggregate or FIRST/LAST only. FINAL is not allowed in DEFINE
  (ORA-62509 for both **(V)**).
- The default is RUNNING. In ONE ROW PER MATCH, RUNNING and FINAL are the same (the last row).
- An aggregate in DEFINE includes the row being tested **(V)**.
- Binds are allowed **(V)**.
- Window functions are ORA-30483 **(V)**; PG 42P20; T-SQL 4108.

Rules for navigation and aggregate arguments (all **(V)**):
- The column references inside one navigation or aggregate argument all name the same variable:
  `SUM(a.v * 2)` is allowed, `SUM(a.v + b.v)` and `PREV(a.v + b.v)` are ORA-62508. A measure such as
  `a.v + b.v` is fine.
- Nesting: `PREV(FIRST(v))` and `NEXT(LAST(a.v), 2)` are allowed. `PREV(PREV(v))`, `FIRST(PREV(v))`,
  `SUM(PREV(v))` and an aggregate inside a navigation are ORA-62506.
- A navigation offset is a non-negative integer literal: ORA-62520 for `-1` or a column.
- CLASSIFIER() or MATCH_NUMBER() inside a navigation or aggregate is ORA-62507.
- Outside MATCH_RECOGNIZE these names are unknown functions: Oracle ORA-00904 "CLASSIFIER": invalid
  identifier; PG 42883.

## 4. Data structures

### 4.1 New file `cmd/lexdb_match.lxl` (types, compiler, matcher; imports `./lexdb_base` only)

```
pub type PNode = closed {
    Var(int)                    // a primary variable, by index into MatchRec.vars
    Begin                       // ^
    End                         // $
    Seq([]PNode)
    Alt([]PNode)
    Perm([]PNode)               // PERMUTE(...)
    Excl(PNode)                 // {- ... -}
    Quant(PNode, int, int, bool)  // min, max (-1 unbounded), reluctant
}
pub const OP_VAR = 1            // a: var; b: 1 if inside an exclusion. Needs a row whose DEFINE holds; maps it; pos += 1
pub const OP_SPLIT = 2          // try a, then b (a choice point); c: this split's ordinal (0..nSplits-1)
pub const OP_JMP = 3            // a
pub const OP_BEGIN = 4          // pos == lo
pub const OP_END = 5            // pos == hi
pub const OP_MATCH = 6
pub type MrIns = value record { pub op: int; pub a: int; pub b: int; pub c: int }
pub type Prog = record { pub ins: []MrIns; pub nSplits: int; pub nVars: int }
pub const MR_MAX_PROG = 10000   // instructions; also the largest quantifier bound
pub const MR_MAX_DEPTH = 64     // pattern nesting (the compiler and canEmpty recurse)
pub const CE_EMPTY_LOOP = 1     // compile's error codes
pub const CE_TOO_LARGE = 2
```

**`pub fn compile(p: &PNode, nVars: int): Result[Prog, int]`** turns the pattern into a program.

- Checks:
  - `Quant(x, ..)` where x is not `Var` and `canEmpty(x)` gives CE_EMPTY_LOOP. canEmpty: Var false;
    Begin and End true; Seq all; Alt any; Perm all; Excl its part; Quant min == 0 or its part.
  - The nesting depth is at most MR_MAX_DEPTH, and the size is at most MR_MAX_PROG; either over gives
    CE_TOO_LARGE. The size is worked out *before* emitting anything, with saturating arithmetic: test
    `size > MR_MAX_PROG / n` before multiplying. PERMUTE's k! alternatives count against it the same way.
- Emitting:
  - Seq in order. Alt(x1..xk): `SPLIT L1, M1; L1: x1; JMP end; M1: SPLIT L2, M2; ...; xk; end:`.
  - Quantifiers are unrolled, so the matcher's state is only (pc, pos):
    - `x{n,m}`: n copies of x, then m - n nested optional copies (`SPLIT body, exit` each).
    - `x{n,}`: n copies, then `L: SPLIT body, exit; body: x; JMP L; exit:`.
    - Reluctant swaps each SPLIT's a and b.
  - Perm: the Alt of the permutations, in lexicographic order of the index lists.
  - Excl sets b = 1 on the OP_VARs inside it. Begin and End become OP_BEGIN and OP_END.
  - End with OP_MATCH. SPLITs get consecutive ordinals.
- Since no loop body can match empty, the program has no cycle that consumes no row.

**`pub type Found = record { pub ok: bool; pub end: int; pub lab: []int; pub exc: []bool; pub over: bool }`**
- `lab[i]` and `exc[i]` are the variable and the exclusion flag of row s + i.
- `over` means the step limit was hit.

**`pub type Matcher`** is the state kept between attempts of one search: the stack, the visited bits,
the DEFINE cache, `base`, and `memoOff`.
- **`pub fn newMatcher(): Matcher`** makes one.
- **`pub fn (m: mut &Matcher) reset(base: int)`** starts a search at row `base`.
- **`pub fn (m: mut &Matcher) attempt(pr: &Prog, lo: int, hi: int, s: int, memo: bool, maxSteps: int,
  holds: &fn(int, int, &[]int): Result[bool, DbErr], tick: &fn(): Result[Unit, DbErr]): Result[Found, DbErr]`**
  tries one start row s. `holds(v, pos, lab)` evaluates v's DEFINE on row `pos`, given the labels of
  rows s..pos-1. `tick` is the executor's `Run.tick`.

The attempt is iterative: an explicit stack of (pc, pos) pairs, **never recursion**, because a stack
overflow kills the server. The mapping length is always pos - s, so a choice point needs only (pc, pos):
on backtrack, `lab` and `exc` are cut to pos - s.

```
push (0, s)
while stack not empty:
  (pc, pos) = pop; truncate lab/exc to pos - s
  loop:
    steps += 1; try tick(); if (!memo || memoOff) && maxSteps > 0 && steps > maxSteps: return over
    SPLIT: if memo && !memoOff: if seen(c, pos) fail; mark(c, pos).  push (b, pos); pc = a
    JMP: pc = a          BEGIN: pos == lo or fail     END: pos == hi or fail
    VAR: pos < hi or fail; cached (memo) or holds(a, pos, lab) must be true, else fail;
         append a to lab, b == 1 to exc; pos += 1
    MATCH: return Found{ok: true, end: pos, ...}
  fail: continue with the next pop
return Found{ok: false}
```

**Memo (local mode).** It is used only when every DEFINE is *local* (section 4.3). Then whether a state
(pc, pos) leads to a match depends on nothing else, so:
- A SPLIT state reached a second time in one search has already failed. It cannot be on the current path,
  because there are no empty cycles. So it is pruned.
- `holds` results are cached per (v, pos) for the search. Both tables are kept across the start rows of
  a search: a state that failed from an earlier start fails again.
- `reset` clears them after a match, because states on a successful path are marked too.
- The bits are indexed `(pos - base) * nSplits + c`, the cache bytes `(pos - base) * nVars + v`
  (0 unknown, 1 true, 2 false). Both grow by doubling in rows.
- Past 64 MB (`MR_MEMO_MAX`) `memoOff` is set for the rest of the search, and then the step limit
  applies.

**Complexity.**
- Local mode: each (split, row) and each (var, row) is visited at most once per search. A search costs
  O((S + V) · W), where W is the rows it touches. With SKIP PAST LAST ROW searches barely overlap:
  O((S + V) · N) per partition. The worst case is O((S + V) · N²): SKIP TO NEXT ROW over long matches,
  as in Oracle.
- Dependent mode: exponential in the worst case, for example `((a | b)+ c)` with
  `c AS SUM(a.v) < 0`. Each attempt is bounded by `maxSteps`.
- Both modes keep one stack entry per choice point on the current path: a greedy `a+` over n rows keeps
  n entries of 16 bytes. The executor counts its growth with `Run.hold`, so max_statement_mem's 53200
  error stops runaway memory.

### 4.2 AST (`cmd/lexdb_sql.lxl`)

```
pub const MR_ONE = 0
pub const MR_ALL = 1          // SHOW EMPTY MATCHES
pub const MR_OMIT = 2
pub const MR_UNMATCHED = 3
pub const SKIP_PAST = 0
pub const SKIP_NEXT = 1
pub const SKIP_FIRST = 2
pub const SKIP_LAST = 3
pub type MrSubset = record { pub name: str; pub spell: str; pub vars: []int }
pub type MrDefine = record { pub v: int; pub cond: Expr }
pub type MatchRec = record {
    pub part: []str               // PARTITION BY (folded names)
    pub order: []WinOrder         // ORDER BY (as winSpec reads it; T-SQL NULLs first going up)
    pub measures: []SelItem       // expr, alias (folded), spell
    pub rows: int                 // MR_*
    pub skip: int                 // SKIP_*
    pub skipTo: str               // TO FIRST/LAST name (folded): a variable or a subset
    pub pattern: lexdb_match.PNode
    pub vars: []str               // primary variables, in order of first appearance in PATTERN (folded)
    pub shown: []str              // ... as CLASSIFIER() returns them (section 5)
    pub subsets: []MrSubset
    pub defines: []MrDefine
    pub dialect: int              // MD_PG, MD_TSQL, MD_ORA
}
```

`Stmt` gains `pub mr: []MatchRec` (zero or one). Add `mr: []` to `newStmt` and to the other `Stmt{kind:`
literal in `cmd/lexdb_tsqlparse.lxl`.

**The wrapper.** `t MATCH_RECOGNIZE (...) mr` becomes a subquery in FROM:
- **The wrapper Stmt:** `S_SELECT`, `use = SUB_FROM`, `items = [*]`, `from = [the input item]` (with
  `join = J_FIRST`, `comma = true`, `on = None`), and `mr = [the clause]`.
- **The outer FromItem:** `sub` is the wrapper's index in the outer `p.subs`, `alias` is the output alias
  (default `unnamed_subquery`, as for subqueries), and `cols` is the output column list.
- **Laterality:** the outer item's `lateral` is the input's (a LATERAL subquery or an APPLY item), in all three doors
  (D8; Oracle itself refuses it with 62521).

Because the wrapper is an ordinary FROM subquery, joins, CTEs, views, LATERAL, nested MATCH_RECOGNIZE
(input is a subquery with its own) **(V)**, GROUP BY over the result **(V)** and EXPLAIN all work through
existing code.

### 4.3 Plan (`cmd/lexdb_exec.lxl`)

```
pub const NV_LAST = 1         // MrNav.kind
pub const NV_FIRST = 2
pub const NV_AGG = 3
pub const NV_CLS = 4
pub const NV_MNO = 5
type MrNav = record {
    kind: int
    set: []bool               // the variables it reads; [] the universal variable
    off: int                  // FIRST/LAST offset
    phys: int                 // then PREV (-n) or NEXT (+n); 0 none
    final: bool               // FINAL (MEASURES only)
    arg: Expr                 // evaluated on the target row, against inCols (resolved)
    col: int                  // arg is a bare column: its index (a fast path); -1
    spec: AggSpec             // NV_AGG: count/sum/avg/min/max (star: COUNT(*) or COUNT(v.*))
}
type MrPlan = record {
    inCols: []lexdb_sql.ColDef    // the input's columns, bare names (from the wrapper's sel.outs)
    keyX: []Expr                  // PARTITION BY then ORDER BY, resolved against inCols
    np: int
    desc: []bool
    nullsFirst: []bool
    prog: lexdb_match.Prog
    shown: []str                  // per variable, CLASSIFIER's text
    sets: [][]bool                // per subset, its variables
    navs: []MrNav                 // slot k of every rewritten expression
    defs: []Option[Expr]          // per variable: its DEFINE, rewritten (slots); None always true
    defNavs: [][]int              // ... the slots each uses
    meas: []Expr                  // MEASURES, rewritten
    measNavs: [][]int
    local: bool                   // every DEFINE local: the matcher's memo
    rows: int
    skip: int
    skipSet: []bool               // TO FIRST/LAST: the variables named
    outs: []OutCol                // the output columns
    outFrom: []int                // per output column: input column j (j >= 0) or measure -1 - i
    dialect: int
}
```

- `Sel` gains `mr: []MrPlan`. Add `mr: []` to the two `Sel{q:` literals in planSelect and planSet.
- `planSub`: after `planSelect` and before the srf line, call
  `if len(s.mr) > 0 { try planMatch(st, txn, &s.mr[0], mut &sel, params, sc) }`.
  `sel.outs` stays the input's (execSelTo needs it); the output columns go in `mr[0].outs`.
- New `fn fromCols(sel: &Sel): &[]OutCol` gives `mr[0].outs` when there is an MR plan, else `outs`.
  `buildQuery`'s naming of a FROM subquery's columns (the `len(f.cols) > len(sp.sel.outs)` check and the
  loop after it, about lines 8475-8484) uses it. No other `sp.sel.outs` use concerns a FROM item.

**planMatch.** Errors go through `mrErr(d, ora, oraText, pg, ts, msg)`:
- Oracle door: state `"ORA" + pad5(ora)` with Oracle's text.
- T-SQL door: `"TS" + ts` when ts > 0, else pg (lexdb_tsql.sqlNumber maps it).
- PG door: pg with msg.

Its steps, in order:
1. `inCols` from `sel.outs` (`lexdb_sql.colDef(o.name, outType(&o), false)`, coll copied). PARTITION BY
   names must be among them (42703 / ORA-00904). ORDER BY: a name (Oracle), or an expression resolved
   with `resolve` against inCols (PG and T-SQL).
2. Pattern: `lexdb_match.compile`. CE_EMPTY_LOOP gives ORA-62513 "Quantified subpatterns that can have
   empty matches are not yet supported." (PG and T-SQL: 0A000). CE_TOO_LARGE gives ORA-62518
   "MATCH_RECOGNIZE pattern is too large." (54001).
3. **Rewrite** each DEFINE and MEASURE with `mrRewrite(x, ctx, curVar)`. It walks the Expr, and every
   navigation, aggregate, CLASSIFIER and MATCH_NUMBER becomes a marker
   `Call("#mrnav", [Lit(k), stand-in])` with a new `MrNav` k:
   - `Col("q.c")`: q must be a variable or a subset, else ORA-62504 "illegal variable reference" (PG
     42P01 `missing FROM-clause entry for table "q"`; T-SQL 4104 `The multi-part identifier "q.c" could
     not be bound.`). The input's alias is no exception. c must be an input column (42703 / ORA-00904).
   - `Col("c")`: the universal variable. Every column becomes a NV_LAST with off 0, so a plain column is
     never read from an Env row directly.
   - `prev`/`next`/`first`/`last` calls, aggregates (`count` `sum` `avg` `min` `max`; `count(v.*)` is
     `Call("count", [Lit(Text v)], true)`), `#running`/`#final`, `classifier()` and `match_number()`
     follow the rules of section 3.
     - Each argument's columns name one variable (else 62508). Its qualifiers are stripped and it is
       resolved with `resolve` against inCols.
     - An aggregate call is resolved as a whole, so the door's rewrites apply (T-SQL's AVG becomes
       `#tavg(avg(x), mode)`). The AggSpec is made from the inner aggregate call, and the wrapper stays
       around the marker.
     - Any other aggregate name (AGGS), a DISTINCT, FILTER or ORDER BY aggregate: ORA-62512 (0A000).
       `#win`: the window error.
     - `#sub`/`#exists`/`#in` (a subquery): 0A000, Oracle ORA-03001 (D5).
     - An outer reference cannot happen: every Col was checked in this step, before any `resolve`.
   - Stand-ins are for types only: the resolved argument (navigation), the resolved aggregate call,
     `Cast(Lit(Text "") as text)` for CLASSIFIER, and `Cast(Lit(Int 0) as int8)` for MATCH_NUMBER.
   - The rewritten expression is then resolved as a whole (literal casts, T-SQL collations). Next,
     `exprOid` gives the measure's type: add `"#mrnav"` with 2 arguments to exprOid as `"#win"` is (the
     stand-in's type). Last, each marker becomes `slotRef(k)` (`#agg k`), which `eval` reads from
     `Env.aggs`.
4. **Local:** a DEFINE of v is local when each of its navs is NV_LAST with off 0 (any phys), over the
   universal variable, v itself, or a subset holding v. It may also use NV_CLS (v's name, a constant).
   It may use no aggregate, no FIRST, no MATCH_NUMBER and no other variable. The plan is local when every
   DEFINE is.
5. **Outs** (section 3's order and its duplicate-name errors). Partition and input columns copy the
   input's OutCol. A measure's OutCol is `{name: alias, oid: from step 3, spell: SelItem.spell, coll:
   "", scale: -1}`. CLASSIFIER is text in every door (Oracle sends VARCHAR2). MATCH_NUMBER and COUNT are
   int8. Every other measure's type is whatever the same expression has in a GROUP BY query of that door.
6. Static checks:
   - TO var must name a variable or subset (ORA-62504).
   - WITH UNMATCHED ROWS with an exclusion is ORA-62515 "Exclusion syntax cannot be used with WITH
     UNMATCHED ROWS." (42601).
   - Output columns: ORA-30732 / ORA-00918 as in section 3.

## 5. Parser (`cmd/lexdb_sql.lxl`), per door

- **Lexer** (`lexOra`): add `{`, `}`, `?` and a `$` not followed by a digit to the one-character
  operators. They are refused everywhere else by the parser, as 42601, as before. A `$` after a name
  character stays part of the name, as in Oracle: write `b $`, not `b$`.
- **`fromItem`**: rename it `fromItem0`. The new `fromItem` calls it, then
  `if p.isKw("match_recognize") && p.peekAt(1) is "(" { f = try p.matchRecognize(f) }`.
  `aliasOf` must not take `match_recognize` followed by `(` as an alias.
- **`matchRecognize(f)`**:
  - A recursive CTE's working table (`f.work >= 0`) is 0A000.
  - If `f.sub >= 0` it is `len(p.subs) - 1` (subquery, CTE, catalog, DUAL and VALUES all append last;
    else XX000). Pop it and run `saved = replace(mut &p.subs, [it])` with `f.sub = 0`.
  - Also save `p.wins`, run `p.depth += 1` and `p.mr += 1` (a new P field).
  - Parse the clause, then restore everything and append the wrapper.
  - A window call made inside is the window error.
- **Clause keywords** are contextual (`p.acceptKw`); none becomes reserved.
- **Oracle's missing-clause errors.** In the Oracle door a token that fits no clause is ORA-02000
  "missing PATTERN keyword" before PATTERN, and "missing DEFINE keyword" after it **(V)**. For example
  SKIP written after PATTERN gives "missing DEFINE keyword", and `ORDER BY v + 1` gives "missing PATTERN
  keyword". PG and T-SQL: `near()` (42601; T-SQL 102).
- **MEASURES.** `expr [AS] name`.
  - With no alias, before `,` or `)`: ORA-62505 "expression needs to be aliased" **(V)** (42601).
  - The Oracle door takes any name as an alias, as Oracle does: so `count(*) pattern (...)` fails later
    with "missing PATTERN keyword" **(V)**.
  - PG and T-SQL do not take ONE, ALL, AFTER, PATTERN, SUBSET or DEFINE as a bare alias.
- **RUNNING / FINAL.** In `primary`, when `p.mr > 0` and the token is `running` or `final` followed by a
  name and `(`, parse the next primary and wrap it as `Call("#running" | "#final", [x])`.
- **`COUNT(v.*)`.** In the call-argument code, when `p.mr > 0` and the arguments are `name . *`.
- **PATTERN.** It is parsed from tokens by `p.mrPattern()`, following the grammar in section 2.
  - A `{` after a term is a quantifier unless the next token is `-`, which starts an exclusion.
  - A variable is a T_IDENT that is not reserved (`isReserved`), or a T_QIDENT. Else ORA-00931 "missing
    identifier" **(V)**; 42601.
  - Variables get indexes in order of first appearance.
  - Bounds are T_NUM digits. Over MR_MAX_PROG is ORA-62518. `{0}`, `{0,0}` and m < n are ORA-62501
    "invalid value specified for bounded quantifier in MATCH_RECOGNIZE clause".
- **CLASSIFIER text** (`MatchRec.shown`): the variable token's `spell` when it is not empty, else its
  `text`, taken from its first occurrence in PATTERN. Oracle gives upper case (bare) or as written
  (quoted); PG gives lower case unless quoted; T-SQL gives the spelling (D2).
- **SUBSET** names must be new (not a variable, not repeated: ORA-62503 "illegal variable definition"),
  and their members must be primary variables (ORA-62504).
- **DEFINE** names must be pattern variables, each defined at most once (ORA-62503 **(V)**). A subset
  name in DEFINE is also ORA-62503.
- **Errors** are made with `oraErr` (Oracle), `lexdb_base.err("42601", ...)` (PG), and the PG state or
  `TS` states for T-SQL, as `P.merge` does. `MatchRec.dialect` is set as `merge` sets `mdialect`.
- **`pub fn mrText(m: &MatchRec): str`** is a canonical one-line text of the clause, for EXPLAIN and the
  M1 test.

## 6. Execution

- **The hook.** `execSel` (the wrapper that `runChild` calls) becomes:
  `if len(sel.mr) > 0 { let r = try execSelTo(..., -1, rs, false, noEachB); return execMatch(st, txn,
  &sel.mr[0], r, params, cap, rs) }`. Every FROM subquery path goes through runChild then execSel:
  runFrom, a LATERAL subquery per row, a CTE (cached) and a view. Top-level streaming (`toSink`) never
  sees an MR Sel.
- **execMatch.**
  1. The input rows are already held by the run. Each row's keys are `keyX` (a bare column read at its
     index).
  2. Sort and partition. Move the sort out of `winValues` into
     `fn partOrder(vcols: &[][]Val, np: int, desc: &[]bool, nf: &[]bool, typed: bool, n: int): PartSort`
     (`PartSort{idx: []int; partBreak: []bool; peerBreak: []bool}`). It keeps the typed path
     (`newSKey`/`skOfValsRef`/`skEnc`/`skSort`/`skCmp`) and the fallback (`encIdxPart` and a comparator
     made from `winCmp` taking desc/nf arrays). winValues calls it too, so its tests guard the move.
  3. Per partition [lo, hi) (positions into idx), with `m = lexdb_match.newMatcher()` and `mno = 0`,
     `s = lo`, `covered = lo`, and `m.reset(s)`:

     ```
     while s < hi:
       f = m.attempt(prog, lo, hi, s, plan.local, maxSteps, holds, tick)
       if f.over: error (D4)
       if !f.ok: if rows == MR_UNMATCHED && s >= covered: emit unmatched(s); s += 1; continue
       mno += 1; emit(f); covered = max(covered, f.end)
       next = skip target (section 3, errors ORA-62514 / ORA-62517: 22000 elsewhere); s = next; m.reset(s)
     ```

  4. **`holds(v, pos, lab)`:** with no DEFINE, true. Else fill the slots of `defNavs[v]` in the DEFINE
     context: rows s..pos, with row pos mapped to v. Then `eval(cond, Env{aggs: &slots, ...})` must be
     `Val.Bool(true)`. Dependent mode adds the rows an aggregate or FIRST/LAST scan reads to the steps
     (through `tick` and the count).
  5. **Navigation** in a context (lo, hi, s, upto, lab, final):
     - The rows of a set are the positions s..upto whose label is in it. `final` widens upto to the last
       row of the match.
     - LAST/FIRST pick the off-th row from the end or the start, then phys moves it. Outside [lo, hi), or
       no row: NULL.
     - The value is `arg` on that row: `rows[idx[t]][col]` when col >= 0, else `eval` with
       `Env{cols: &inCols, row: &that row, ...}`.
     - Aggregates use `newAccs`, `accumulate` and `finish` over the set's rows, with `Env.row` the row.
     - NV_CLS gives `shown[lab]` (in DEFINE: `shown[v]`). NV_MNO gives mno (in DEFINE: mno + 1).
     - An empty match: COUNT 0, the rest NULL.
  6. **Emitting.**
     - ONE ROW: measures at upto = e - 1 (final). Partition values come from row s.
     - ALL ROWS: for each r in s..e-1 with `!exc[r - s]`, the row's input columns, and the measures at
       upto = r (FINAL navs at e - 1). This must be O(L × measures) per match, not O(L²):
       - per set, a list of the match's positions;
       - per row, a moving count into each list;
       - running aggregates fed one row at a time into their Acc (`finish` per output row);
       - FINAL values computed once per match.
     - Unmatched and empty-match rows are as section 3 says.
     - Each emitted row costs `try rs.tick()`. Output bytes are counted against `rs.room()` (53200), as
       execSrf counts its rows.
  7. Return `Res{cols: plan.outs, rows: out, tag: "", hasRows: true, copy: COPY_NONE}`.
- **Lexell constraints.**
  - No recursion over rows. Recursion over the pattern is bounded by MR_MAX_DEPTH, and over expressions
    as elsewhere.
  - Integers: steps and counts are int64. A bound is parsed with `strings.parseIntOpt` and compared with
    MR_MAX_PROG before any arithmetic. All size arithmetic saturates (4.1).
  - Every matcher step and every output row goes through `Run.tick()`, which takes turns (9.15) and
    honours statement_timeout (57014).
- **Step limit.** Add the session setting `max_match_steps` (default 10,000,000; 0 for no limit) wherever
  `max_recursion` is: `Session.maxRecursion`, `applySetting`, `settingValue`, `SHOWN`, RESET and its
  rollback copy, `Limits.rounds`, `Run.maxRounds`, `Run.limit` and `runChild`'s copy. It counts steps per
  attempt (start row), and only in dependent mode or with the memo off.
- **EXPLAIN.** `selLines` puts one line first for an MR Sel:
  `match_recognize: partition by g order by id; pattern (strt down+ up+); one row per match; skip to
  last up; memo` (or `steps`), from `mrText` and `local`. The input's plan follows as usual.

## 7. Error table (Oracle numbers and texts verified **(V)** unless marked)

| case | Oracle | PG | T-SQL |
|---|---|---|---|
| a clause out of order or a token that fits no clause | 02000 missing PATTERN / DEFINE keyword | 42601 | 102 |
| empty pattern, empty alternative, reserved word as a variable | 00931 missing identifier | 42601 | 102 |
| bad bound `{0}`, `{3,2}` | 62501 | 42601 | 102 |
| DEFINE of a non-variable, DEFINE twice, bad SUBSET name | 62503 | 42601 | 102 |
| unknown qualifier, the input's alias as a qualifier, a non-variable in SUBSET or SKIP TO | 62504 | 42P01 | 4104 |
| an outer query's column in the clause | 62504 | 42P01 | 4104 |
| a measure without an alias | 62505 | 42601 | 102 |
| bad nesting (PREV(PREV()), FIRST(PREV()), SUM(PREV()), agg in nav) | 62506 | 42601 | 102 |
| CLASSIFIER / MATCH_NUMBER in an agg or nav | 62507 | 42601 | 102 |
| two variables in one nav or agg argument | 62508 | 42601 | 102 |
| RUNNING / FINAL misplaced, FINAL in DEFINE | 62509 | 42601 | 102 |
| unsupported aggregate (DISTINCT, LISTAGG, ...) | 62512 | 0A000 | 50000 |
| a quantified group that can be empty | 62513 | 0A000 | 50000 |
| SKIP TO variable not in the match (run time) | 62514 | 22000 | 50000 |
| exclusion with WITH UNMATCHED ROWS | 62515 | 42601 | 102 |
| next match at the same start (run time) | 62517 | 22000 | 50000 |
| pattern too large | 62518 | 54001 | 50000 |
| bad navigation offset | 62520 | 42601 | 102 |
| window function in the clause | 30483 window  functions are not allowed here | 42P20 | 4108 |
| qualified name in PARTITION BY / ORDER BY | 01748 only simple column names allowed here | 42601 | 102 |
| duplicate output column | 00918 | 42701 | 8156 |
| no output column | 30732 | 42601 | 102 |
| unknown column | 00904 | 42703 | 207 |
| CLASSIFIER(var) | 00907 missing right parenthesis | 42601 | 102 |
| subquery in MEASURES / DEFINE (lexdb: not yet, D5) | 03001 (Oracle allows uncorrelated ones **(V)**) | 0A000 | 50000 |
| step limit exceeded (lexdb only, D4) | 20000 | 54001 | 50000 |

Oracle's texts for 62500 to 62521 (from `sqlerrm`, **(V)**):
- 62501 invalid value specified for bounded quantifier in MATCH_RECOGNIZE clause
- 62502 invalid variable name
- 62503 illegal variable definition
- 62504 illegal variable reference
- 62505 expression needs to be aliased
- 62506 illegal nesting of operators in MATCH_RECOGNIZE clause
- 62507 illegal use of MATCH_NUMBER or CLASSIFIER in MATCH_RECOGNIZE clause
- 62508 illegal use of aggregates or navigation operators in MATCH_RECOGNIZE clause
- 62509 illegal use of RUNNING or FINAL in MATCH_RECOGNIZE clause
- 62510 Correlated subqueries are not allowed in MATCH_RECOGNIZE clause.
- 62511 Correlation variables are not allowed in MATCH_RECOGNIZE clause.
- 62512 This aggregate is not yet supported in MATCH_RECOGNIZE clause.
- 62513 Quantified subpatterns that can have empty matches are not yet supported.
- 62514 AFTER MATCH SKIP TO variable is not bounded in the match found.
- 62515 Exclusion syntax cannot be used with WITH UNMATCHED ROWS.
- 62516 The PARTITION BY, ORDER BY, or MEASURES clause is too large for MATCH_RECOGNIZE.
- 62517 Next match starts at the same point last match started.
- 62518 MATCH_RECOGNIZE pattern is too large.
- 62519 Subquery inside MATCH_RECOGNIZE cannot contain MATCH_RECOGNIZE.
- 62520 illegal offset for MATCH_RECOGNIZE navigation operators
- 62521 MATCH_RECOGNIZE is not supported on lateral views.

Notes on the table:
- 62500 ("function is not allowed outside of MATCH_RECOGNIZE clause") was never seen: CLASSIFIER()
  outside the clause gave ORA-00904.
- ORA-00918's 23ai text is `NAME: column ambiguously specified - appears in  and ` (with two blanks);
  lexdb sends exactly that.
- `oraOf` passes `ORAnnnnn` states through.
- T-SQL's 4104, 4108 and 8156 are SQL Server's own numbers for the same failures elsewhere. The 102 and
  50000 rows come from `sqlNumber`'s existing mapping.

## 8. Stages

Each stage is one Sonnet agent run, committed on a branch from main and merged into main. The lexdb tests
run natively: `LXL_NOCACHE=1 python3 lexell/tests/lexdb.py [filter]`.

| stage | contents | done when | parallel |
|---|---|---|---|
| M1 | `cmd/lexdb_match.lxl`: PNode, MrIns, Prog, `compile`, Matcher, `attempt`, `reset`, memo, step limit. Test `tests/lexdb/run/match_vm.lxl`: patterns built with small constructors; DEFINE truth tables per (var, row) as the callback. It checks preference order (alternation, greedy, reluctant, {n,m}, PERMUTE), anchors, exclusion flags, empty matches, CE_EMPTY_LOOP, CE_TOO_LARGE, memo and no memo giving the same Found on 1,000 random tables and patterns, a brute-force reference matcher (all mappings enumerated in preference order, at most 8 rows), the step limit on `((a|a)+ b)`, and the stack never recursing. | the test passes; mutants are caught: greedy/reluctant swapped, memo not reset after a match, BEGIN at any row, exclusion flag dropped | first; commit the types in a first commit |
| M2 | Parser: lexer tokens, `MatchRec` and the related types, the wrapper in `fromItem`, `aliasOf`, `p.mr`, RUNNING/FINAL, `COUNT(v.*)`, PATTERN, SUBSET, DEFINE, `mrText`, all parse-time errors of the three doors; `planSub` refuses `mr` with 0A000 "MATCH_RECOGNIZE is not supported yet". Test `exec_mrparse.lxl`: about 60 statements through `lexdb_sql.parse`, `oraParse` and a T-SQL `Parser`, printing `mrText` or the error state. | the test passes; every existing lexdb test still passes (the lexer and fromItem changes) | after M1's types commit; parallel with the rest of M1 |
| M3 | `planMatch`, `fromCols`, the `#mrnav` exprOid case, the execSel hook, `execMatch` for ONE ROW PER MATCH with every SKIP, navigation, aggregates, CLASSIFIER, MATCH_NUMBER, subsets, local and dependent DEFINEs; `partOrder` moved out of winValues; plan-time and run-time errors. Test `exec_mr.lxl` (PG door, executor, hand-checked): sections 3 and 7's ONE ROW cases, with the answers in section 10 as fixtures. | exec_mr and exec_window pass; mutants caught: PREV clamped to the match, FIRST offset counted from the end, DEFINE without the current row, RUNNING read as FINAL in ONE ROW, skip errors not raised | after M1 and M2 |
| M4 | ALL ROWS PER MATCH: SHOW/OMIT EMPTY MATCHES, WITH UNMATCHED ROWS, exclusion in the output, RUNNING/FINAL incremental, overlapping matches; `max_match_steps` with SET/SHOW/RESET; memo memory cap; EXPLAIN line. Tests: exec_mr grows; new `exec_mrlimits.lxl`: catastrophic patterns (local: fast; dependent: 54001 at a small max_match_steps), statement_timeout during matching, max_statement_mem on a long greedy run, `exec_turns`-style yielding during a long match | tests pass; ALL ROWS over 100,000 rows in one match takes linear time (a test of 10^5 rows that would time out at O(L²)) | after M3 |
| M5 | `tests/lexdb/gen_mr.py` and `tests/lexdb/mr_cases.txt` (section 9), answers recorded on the Oracle container; the **(U)** facts and 62502/62510/62511/62516/62519/62521 probed and the error table corrected; the three generated tests `tns_mr.lxl`, `exec_mrdoors.lxl` (PG door through the executor) and `tds_mr.lxl`. | the generator runs end to end and writes the tests; the cases file has at least 150 entries | parallel with M2 to M4 (only new files) |
| M6 | The three generated suites pass. Fix the differences; a difference that is a dialect rule (section 9) goes in the cases file's per-door fixups, not in the code. Write design/lexdb.md 9.122 "as built" (as 9.121 is) and an "as built" section 12 here. | all three suites and the whole lexdb test set pass; native self-build gate (`tools/gate.sh`) passes | last |

## 9. Test plan

**Oracle as the oracle of truth for all three doors.**

The cases file `tests/lexdb/mr_cases.txt` has one entry per line, `#` lines are comments, and fields are
separated by tabs:

```
s   label   oracle-statement   pg-statement   tsql-statement     setup (DDL/DML); "=" means the Oracle text
q   label   query                                                 one query text for all three doors
q3  label   oracle-query   pg-query   tsql-query                  per-door text, one answer
e   label   query   pg-state   tsql-number                        an error: Oracle's number recorded, the others as section 7 says
```

**`gen_mr.py`**
- It reuses gen_oracle.py's connection and `render`, by importing it. It connects as gen_oracle.py does
  (python-oracledb, `~/.obo-oracle-dsn`), in a fresh user. Use the container as earlier agents did: by
  hand, without TLS, removed afterwards.
- It records each `q` and `q3` answer: the column names and the rows (`render`; text quoted, NULL as
  NULL). For `e` it records the ORA number.
- It writes three tests:
  - `run/tns_mr.lxl` expects Oracle's answers exactly, through the TNS endpoint (as `tns_merge.lxl`
    does).
  - `run/exec_mrdoors.lxl` runs the PG texts through `lexdb_exec` in the PG dialect.
  - `run/tds_mr.lxl` runs the T-SQL texts through the TDS endpoint (as `tds_merge.lxl` does).
- The PG and T-SQL tests embed Oracle's answers as data and compare cell by cell. The program prints
  `ok label`, or the label and both values, and its expect lines are the `ok` lines. The comparison:
  - numbers by value (2 = 2.0 = 2.0000000000000000);
  - text and NULL exactly, except values in a column whose name starts with `CLS`, which are compared
    with Oracle's lower-cased (CLASSIFIER, D2; cases name classifier measures `cls...` and write
    variables in lower case);
  - column names as `lower(oracle name)`, unless Oracle's name has a lower-case letter (it was quoted:
    then exactly).

Shared tables use integer and text columns only. A day number stands in for a date (Oracle's DATE
renders differently). AVG appears only over `number(10,2)` / `numeric(10,2)` / `decimal(10,2)` columns,
because T-SQL's AVG of integers is an integer. Every query has an outer ORDER BY on unique keys (ties
inside MATCH_RECOGNIZE are unspecified in Oracle).

**Cases** (at least these; many are already verified by hand and their answers are in section 10):
1. Oracle's ticker V-shape: ONE ROW, SKIP TO LAST UP.
2. The same with ALL ROWS, CLASSIFIER, MATCH_NUMBER, and RUNNING/FINAL COUNT.
3. W-shape: `(strt down+ up+ down+ up+)`.
4. Runs of increasing values: `(a b*)`, `b AS v > PREV(v)`.
5. Sessionization: events (user, ts) with a gap over 10 starting a session. MATCH_NUMBER as the session
   id, and COUNT, FIRST(ts), LAST(ts).
6. Top-N per group: `PATTERN (^ a{1,3})`, PARTITION BY g, ORDER BY v DESC, ALL ROWS.
7. Gap detection: `(a b)`, `b AS id > PREV(id) + 1`, SKIP TO NEXT ROW.
8. Empty matches: `a*` with ONE ROW, ALL ROWS SHOW, ALL ROWS OMIT, and WITH UNMATCHED ROWS; `a+` with
   UNMATCHED.
9. Reluctant: `a+? b`, `a b*?`, `a b?? c{1,3}?`.
10. Bounded: `{2}`, `{2,}`, `{,2}` (it gives an empty match), `{1,2} b`.
11. Anchors: `^ a a`, `a a $`, `^ a* $`.
12. PERMUTE: three variables, and `PERMUTE(a+, b)`, `PERMUTE(a b, c)`.
13. Exclusion with ALL ROWS and ONE ROW, an exclusion at the end, everything excluded (no output rows).
14. ALL ROWS with navigation: PREV with offset 2, NEXT, FIRST/LAST with offset 1, FINAL LAST(a.id, 1),
    RUNNING and FINAL SUM.
15. SKIP: PAST LAST ROW, TO NEXT ROW, TO FIRST/LAST var, TO a subset; the 62514 and 62517 errors.
16. Partitions: a NULL partition key, PARTITION BY two columns (the output order), ORDER BY DESC NULLS
    FIRST, and the default NULL placement.
17. Ties: only queries whose answer does not depend on tie order (counts with `a+` always true).
18. NULLs in DEFINE comparisons and in COUNT(v) against COUNT(*).
19. SUBSET in MEASURES and in DEFINE.
20. CLASSIFIER() and MATCH_NUMBER() in DEFINE.
21. History-dependent DEFINE (`SUM(a.v) <= 30`, `v > FIRST(b.v)`, `v > a.v`).
22. Input forms: a subquery, a CTE, a view, a join of the result, a LATERAL subquery around the query,
    nested MATCH_RECOGNIZE, GROUP BY over the result, an input alias, an output alias with
    `mr.col` and `mr.*`.
23. Binds (`:x` / `$1` / `@x`).
24. Every error of section 7 that Oracle shares.

**lexdb-only tests** (hand-checked):
- `exec_mrlimits.lxl`: the step limit; memo against no memo on random data (the matcher's two modes
  must agree; a test hook forces `local = false`); timeouts; memory.
- `exec_mrparse.lxl`: as in M2.
- `match_vm.lxl`: as in M1.

## 10. Recorded answers (Oracle 23ai, by hand), fixtures for M3

The tables:
- `t(id, g, v)` = (1,a,10) (2,a,20) (3,a,15) (4,a,NULL) (5,a,30) (6,b,5) (7,b,6) (8,b,4).
- `ticker(symbol, tstamp, price)`: ACME, days 1..20, prices
  12 17 19 21 25 12 15 20 24 25 19 15 25 25 14 12 14 24 23 22.

The answers:
- V-shape: `PARTITION BY symbol ORDER BY tstamp MEASURES strt.tstamp, LAST(down.tstamp), LAST(up.tstamp)
  ONE ROW PER MATCH AFTER MATCH SKIP TO LAST up PATTERN (strt down+ up+) DEFINE down AS down.price <
  PREV(down.price), up AS up.price > PREV(up.price)` gives three rows of (start, bottom, end) in days:
  (5,6,10), (10,12,13), (14,16,18).
- `PARTITION BY g ORDER BY id MEASURES MATCH_NUMBER() m, COUNT(*) c, CLASSIFIER() cl PATTERN (a*) DEFINE a
  AS v > 12`, as (g, m, c, cl):
  - ONE ROW: (a,1,0,NULL), (a,2,2,A), (a,3,0,NULL), (a,4,1,A), (b,1,0,NULL), (b,2,0,NULL), (b,3,0,NULL).
  - ALL ROWS OMIT EMPTY MATCHES, as (id, m, c, cl): (2,2,1,A), (3,2,2,A), (5,4,1,A).
- `ORDER BY id`, SKIP TO NEXT ROW, `(a b+)`, `b AS v > 0`, as (m, FIRST(id), LAST(id)): (1,1,3), (2,2,3),
  (3,4,8), (4,5,8), (5,6,8), (6,7,8).
- `(a+? b)` with both variables always true on t: (1,2), (5,6), (7,8). `(a b*?)`: one row per row.
- `(a{,2})`, `a AS id <> 4`, as (FIRST(id), LAST(id), COUNT(*)): (1,2,2), (3,3,1), (NULL,NULL,0),
  (5,6,2), (7,8,2).
- `(a+)`, `a AS SUM(a.v) <= 30`, as (COUNT, SUM): (2,30), (2,15), (1,30), (3,15).
- ALL ROWS, `PARTITION BY g ORDER BY id`, `(a+ b*)`, `a AS id < 4 OR id > 5`, `b AS 1 = 1`, partition a.
  Measures, in this order: RUNNING LAST(v), FINAL LAST(v), v, RUNNING SUM(v), FINAL SUM(v), FIRST(v,1),
  LAST(v,1), PREV(v,2), NEXT(v), FINAL LAST(a.id,1). Rows by id:
  - id 1: 10, 30, 10, 10, 75, NULL, NULL, NULL, 20, 2
  - id 3: 15, 30, 15, 45, 75, 20, 20, 10, NULL, 2
  - id 4: NULL, 30, NULL, 45, 75, 20, 15, 20, 30, 2

## 11. Open decisions (the user's), with recommendations

- **D1. Syntax in the PG and T-SQL doors.** Options: the SQL:2016 R010 clause in FROM, as in Oracle;
  PostgreSQL's in-progress window form (R020); or none. **Recommended: R010 in all three doors.** It is
  the standard's, the same text works everywhere, and the matcher can serve R020 later.
- **D2. CLASSIFIER()'s text in PG and T-SQL.** Options: the door's identifier rule (PG lower case unless
  quoted, T-SQL as spelled), or the standard's upper case. **Recommended: the door's rule.** It matches
  how each door shows names, and Oracle's own rule is the same idea.
- **D3. Standard features Oracle refuses** (`()`, empty-capable quantified groups, ORDER BY
  expressions). **Recommended: refuse the first two everywhere, as Oracle does.** That keeps loops simple
  and the matcher free of empty cycles. Accept ORDER BY expressions in the PG and T-SQL doors: they cost
  one evaluated key.
- **D4. The step limit.** **Recommended: `max_match_steps`**, 10,000,000 steps per start row, applied
  only when the memo is off (history-dependent DEFINEs). The errors would be PG 54001, Oracle ORA-20000
  with lexdb's text (no Oracle equivalent; `oraOf` maps 54001 to ORA-01792, which would mislead), and
  T-SQL 50000. Alternatives: no limit (Oracle's way; statement_timeout only), or one limit per statement.
- **D5. Subqueries in MEASURES and DEFINE.** Oracle allows uncorrelated ones **(V)**. **Recommended:
  refuse for now** (0A000 / ORA-03001). They need the wrapper's subquery results in execMatch, which
  execSelTo does not return. They can be added later by returning its `Mats`.
- **D6. Pattern size.** Oracle refuses `a{1,300}` (ORA-62518; `a{1,200}` and `a{200} b{200}` pass
  **(V)**); its limit is internal. **Recommended: lexdb's own MR_MAX_PROG = 10,000 instructions.** lexdb
  then accepts some patterns Oracle refuses, which is a documented difference.
- **D7. Quoted against bare variable names.** lexdb matches names folded (L6), so `"a"` and `A` are one
  variable, where Oracle has two. **Recommended: accept the difference**, as for tables and columns.
- **D8. LATERAL inputs.** **Recommended: allow `LATERAL (subq) MATCH_RECOGNIZE` and `CROSS APPLY` in the
  PG and T-SQL doors**, and follow Oracle (the input is not lateral) in the Oracle door.
  **Changed by the user (2026-11-14): the Oracle door supports LATERAL inputs too**, as an extension, and
  does not raise 62521. **Done (2026-11-14):** the Oracle door resolves outer references in a LATERAL input by the
  PG door's own mechanism (the outer item's `lateral` is no longer cleared for Oracle); an unknown column stays
  ORA-00904. Oracle's `CROSS APPLY` and `OUTER APPLY` (12c) are accepted as in the T-SQL door. Tests: `tns_oracle`
  (hand-written, through TNS) and `exec_mr` (the same queries through the PG door).

## 12. As built (2026-11-14)

All six stages are built, in the three doors, by one agent run, not committed. Every recommendation of section 11
(D1 to D8) was taken as written.

**What was built.**
- **M1** `cmd/lexdb_match.lxl` (453 lines): `PNode`, the instruction set, `compile` (checks in the order depth, empty
  loop, size; saturating size arithmetic; PERMUTE's k! alternatives; quantifiers unrolled), `Matcher` with `reset`,
  `attempt` (explicit stack, memo bits and DEFINE cache, `MR_MEMO_MAX` 64 MB, step limit) and `bytes()`. Test
  `match_vm.lxl`: 26,185 checks (about 100 hand-written; the rest a brute-force reference matcher, all mappings in
  preference order, against memo and no memo on 2,000 random patterns and tables, a start row at a time as SKIP TO NEXT ROW does and again after a
  reset), the compile errors and limits, `((a|a)+ b)` with 10,000 steps, and a 300,000-row match. Mutants caught: greedy
  and reluctant swapped (and reluctant not applied), memo not cleared by `reset`, BEGIN at any row, exclusion flag
  dropped, DEFINE cache keeping a wrong result.
- **M2** parser in `lexdb_sql.lxl` (about 520 lines): the lexer's `{ } ? $`, `MatchRec` and its types, `fromItem` over
  `fromItem0`, `aliasOf`, `P.mr`, `matchRecognize`, `mrClause`, the pattern parser (depth-bounded: a nesting over 64 is
  62518 before it can recurse far), `mrText`, RUNNING/FINAL, `COUNT(v.*)`, window and CLASSIFIER(x) errors in the clause.
  Test `exec_mrparse.lxl`: 141 lines of output, each statement through `parse`, `oraParse` and a T-SQL `Parser`.
- **M3, M4** in `lexdb_exec.lxl` (about 1,000 lines): `Sel.mr`, `planSub`'s `planMatch`, `fromCols`, `execSel`'s hook,
  `execMatch` (keys, sort, partitions, the search, every SKIP form, running aggregates fed once a row, FINAL values kept,
  `Run.tick` per step and per row, `Run.hold` for the matcher's memory at its peak and for every output row), EXPLAIN's
  line, and the session setting `max_match_steps` (SET, SHOW, RESET, SHOW ALL, rollback of a block, `set_config`).
  Tests `exec_mr.lxl` (all of section 10's answers, then 75 hand-checked queries), `exec_mrlimits.lxl`.
- **M5** `tests/lexdb/gen_mr.py`, `tests/lexdb/mr_cases.txt` (163 cases: 124 queries, 39 errors, and the setup), recorded
  on Oracle Database Free 23ai (the container was made by hand, without TLS, and removed afterwards).
- **M6** `run/tns_mr.lxl`, `run/exec_mrdoors.lxl`, `run/tds_mr.lxl`: 163 cases each, all agreeing with Oracle. This
  file and `design/lexdb.md` 9.122. The whole lexdb suite: 148 tests before, 155 after, all passing.

**Measured** (native, one thread, 200,000 rows of three integer columns in the store, a warm cache):

| query | rows | time |
|---|---|---|
| ONE ROW, `(a+)`, one match | 200,000 | 134 ms |
| ALL ROWS, `RUNNING SUM`, one match | 200,000 | 234 ms |
| V-shapes, 100 partitions | 200,000 | 224 ms (19,980 matches) |
| SKIP TO NEXT ROW, `(a b{1,4})` | 200,000 | 167 ms |
| history-dependent `(a b+)`, one match | 20,000 | 195 ms |
| history-dependent `SUM(a.v) < 3000` | 100,000 | 178 ms (18,700 matches) |
| ALL ROWS, running and FINAL, one match | 100,000 | linear (`exec_mrlimits`) |
| `((a \| a)+ b)`, local, 40 rows | 40 | memo: instant; dependent: 54001 at 20,000 steps; no limit: 57014 at 300 ms |

A differential fuzz (not kept: it needs the container) ran 2,600 random queries (patterns with every operator, local
and history-dependent DEFINEs, every ROWS PER MATCH form and SKIP, NULL keys, three orderings) on Oracle and on lexdb: one
real difference, the one below (empty match and SKIP TO FIRST or LAST).

**Differences from the design.**
- **No `partOrder` refactor.** `winValues`'s sort was left as it is; `execMatch` sorts by its own comparator over the
  key values (`sortBy` on an index array; ties by input order). The typed-key path is not used, so it is a comparison
  sort. winValues' tests are untouched.
- **Empty match and SKIP TO FIRST or LAST var** is not an error: the next search starts at the next row (Oracle: found by
  the fuzz; the design's table said 62514 for any match without a row of var). A non-empty match without one, or whose
  row is its first, are 62514 and 62517 as designed.
- **Dependent DEFINEs** do not add the rows they scan to the step count (their closure and the matcher's tick cannot both
  borrow the run), so `max_match_steps` counts matcher steps. A DEFINE that looks at each navigation once (FIRST, LAST,
  PREV, NEXT, CLASSIFIER) scans the labels without building a list, so those cost the distance to the row; aggregates
  cost the rows they sum (`sum(a.v) < n` is O(rows of a) per step).
- **`exprOid`** knows `#mrnav` (as designed), but the measure's type, collation and scale are taken from the same
  expression with its markers replaced by their stand-ins (`mrUnmark`), which needs nothing else.
- **Fields added**: `MatchRec.exclusion` (62515 is a parse-time check) and `MatchRec.alias` (T-SQL's 8156 names it),
  `MrPlan.keyAt`, `MrPlan.text`.
- **Errors found on Oracle (M5)**: 62502, 62510, 62511 and 62516 were not seen: an outer query's column in the clause is
  62504, too many output columns is ORA-01792, a variable named `classifier` or `match_number` is fine. 62519 (a
  MATCH_RECOGNIZE in a subquery of MEASURES) and 62521 (`LATERAL (...) MATCH_RECOGNIZE`, with or without an outer
  reference; with one, 00904 comes first) exist. lexdb gives 0A000 / ORA-03001 for any subquery in the clause (D5), and in
  the Oracle door accepts a LATERAL input (D8, changed by the user: an extension, no 62521) and resolves its outer
  references as the PG door does. A measure without an alias is always 62505 or 02000 (`MEASURES x PATTERN` takes
  PATTERN for the alias), also for a plain column.
- **Differences in what lexdb accepts**: a column list after the output alias (`m (x, y)`: Oracle refuses it, ORA-03048),
  `{,}` (as `*`; Oracle takes it too), `a{1,300}` (D6), a quoted and a bare variable of one name (D7).
- **Generated tests.** `tns_mr` does not compare text: like the other two it compares numbers by value (Oracle's own
  number text and lexdb's differ for decimals) and names exactly. `gen_mr.py` takes `--dsn user/pw@host:port/service` of
  a scratch user, since there is no `~/.obo-oracle-dsn` here. An answer with AVG needs data whose average terminates
  (Oracle's float and lexdb's numeric differ after 16 digits). T-SQL's default NULL order differs: two cases carry a
  `q3` with a CASE in the T-SQL ORDER BY. T-SQL's syntax errors are 102 or 156 (a keyword) as in the rest of the door.
- **Existing test changed**: `exec_analyze` expects `max_match_steps|10000000` at the end of SHOW ALL.
- **`mr_cases.txt` entries**: 163 cases (the design asked for 150); one design fixture, `(a+? b)` giving (1,2), (5,6),
  (7,8), did not reproduce: on `t` Oracle gives (1,2), (3,4), (5,6), (7,8), as lexdb does.

**Not done.**
- R020 (the window form), and subqueries in MEASURES and DEFINE (D5), as scoped.
- 62519 exactly (62521 is deliberately not raised, D8); `LATERAL` over a `MATCH_RECOGNIZE` input is tested in the
  PostgreSQL and Oracle doors and in the T-SQL parser (APPLY).
- Binds in the TNS and TDS generated tests (the PostgreSQL door's `$1` is in `exec_mr`; Oracle's `:1` was not run).
- The step limit does not count rows scanned inside a DEFINE; the typed sort; MATCH_RECOGNIZE inside PL/SQL blocks and
  T-SQL procedures (the same parser reads them, no test).
- Only `tools/native_selfbuild.sh` of the gate was run (it passes: a fixed point; nothing it builds reads lexdb), not the
  whole `gate.sh`.

**The fuzz tool** (added later): `tests/lexdb/fuzz_mr.py` generates random MATCH_RECOGNIZE queries (every quantifier
including reluctant, alternation, groups, PERMUTE, exclusion, anchors, SUBSET, ONE ROW and the four ALL ROWS forms, every
SKIP, navigation, running and final aggregates, CLASSIFIER, MATCH_NUMBER, local and history-dependent DEFINEs) over a small
seeded table with NULLs, runs each on Oracle and through lexdb's TNS endpoint (the Oracle door), and compares columns, rows
(numbers by value) and error numbers. A difference is shrunk (fewer measures, no SKIP, no PARTITION, simpler rows form) and
printed with both answers; `--save FILE` appends it as `q` lines for `mr_cases.txt`. Options: `--dsn user/pw@host:port/service`
(a scratch user), `--seed`, `-n`, `--batch`, `--save`, `--compiler`. The script header says how to start a throwaway Oracle
container. It leaves out what is known to differ (LATERAL, subqueries in the clause, ORDER BY expressions, quoted
variables). Run against the tree with the Oracle door's LATERAL and APPLY change: 2,700 queries (seeds 21 and 31 to 34; about
13% are Oracle errors, which lexdb matched by number): 0 differences.
