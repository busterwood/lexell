# Borrow inference for str parameters: a measurement

Status: built, 2026-11-14, on branch `exp/borrow`, taken from `par`.
Sections 1 to 4 are the measurement that came first. Section 6 is the pass
as built (`compiler/borrow.lxl`, `-O` only), with its results.

## 1. The idea

Today a `str` parameter is owned:
- the caller increments the count to pass a copy (`f(rt_str_dup(x))`);
- the callee decrements it when it is done (`rt_str_drop(p)`).

Many functions only read the parameter: its length, bytes or comparisons.
If the compiler knows that, it can pass the string without the increment and
skip the decrement. Lean 4 calls this borrow inference.

With `-O`, `opt.lxl` already does this for calls it inlines (`lends`,
`M_LENT`). This note measures what is left after the optimisations, at calls
that were not inlined.

The rule, per `str` parameter `p` that its function drops (the owned
convention; a `&str` parameter is never dropped), in a function whose
address is never taken. `p` is **borrowed** when every use is:
- a read: a member of it;
- an argument of a runtime function other than a drop;
- the argument of a dup (a new count of its own);
- an argument for another function's parameter that is borrowed or lent.

Anything else makes `p` owned: a store, an initializer, a return, a move into
a parameter that keeps it, or a call through a pointer.

Candidates start borrowed and are made owned until nothing changes, which
handles recursion.

## 2. The instrument

`LXL_RCSTAT=1 lxlc prog.lxl -O` runs `compiler/rcstat.lxl` after the
optimisations, on the IR the native backend compiles. Each `rt_str_dup` and
`rt_str_drop` becomes `rt_str_dup_k` or `rt_str_drop_k`, tagged with a kind:

- **kind 1:** a dup passed, at a direct call, for a borrowed parameter;
- **kind 2:** a borrowed parameter's drop in its own function;
- **kind 0:** everything else.

The program prints the counts at exit, with literals' blocks (count -1, a
test and no write) apart.

## 3. Results

Counted operations only, literals not included:

| program (workload) | parameters borrowed | dups removable | drops of borrowed parameters |
|---|---:|---:|---:|
| the compiler, compiling itself (605 ms) | 222 of 253 | 2.30M of 9.09M (25%) | 2.60M of 10.54M |
| cmark (2.2 MB of design notes and SPEC, 31 ms) | 49 of 51 | 193k of 425k (45%) | 235k of 698k |
| jq (a query over 5 MB of bench/json data, 60 ms) | 120 of 129 | 0.81M of 3.44M (23%) | 0.90M of 4.09M |
| bench/json (5 MB, 335 ms) | 27 of 28 | 4.41M of 13.0M (34%) | 4.41M of 16.5M |
| bench strings, maps | none left after inlining | 0 | 0 |

The saving is the kind-1 dups plus as many drops. A borrowed parameter's
drop can only go when its dup goes. Where the argument was a fresh temporary
(`f(a + b)`), the drop moves to the caller instead. That is why the
compiler's kind-2 drops (2.60M) exceed its kind-1 dups (2.30M).

## 4. What it is worth

A quarter to a half of the counted `str` changes in these programs pass a
string to a function that only reads it.

**On one thread** an inline change costs about a nanosecond while the block
is in cache. These counts then come to roughly:
- 1% of the self-compile;
- 2.5 to 3% of cmark, jq and bench/json.

These are estimates, not measurements. The real gain also depends on cache
misses on the blocks' counts: a dup writes the block's first line, which an
uncounted borrow never touches.

**In par.map kernels** each change is an out-of-line call on a worker (and,
for an input string, a log entry), several times the cost of the inline one.
So the same removal is worth more there (design/parallel.md 6.2, the user
time column).

## 5. Next, as planned before it was built

1. **Make the rule a real optimisation.**
   - The caller passes the place: no dup, and no drop of a fresh temporary
     until after the call.
   - The callee skips the drop.
   - Address-taken functions keep the owned convention, or get a wrapper.
   - Checked as `opt.lxl`'s `lends` is: nothing during the call may replace
     or free the caller's string. Lexell's borrow rules make that the common
     case, but the arguments after it, and the callee's writes through
     `mut &` parameters, must be checked.
2. **Measure the times,** not only the counts, on the four workloads above
   and on `bench/par.lxl`.
3. **Records holding strings passed by value** (their dup glue) are not
   counted here. They are the same idea one level up.

## 6. As built (2026-11-14)

`compiler/borrow.lxl` runs on the IR before the inliner (`opt.lxl`), under
`-O` only. `LXL_NOBORROW=1` turns it off, for measurements.

For each function `f` with parameters found borrowed:
- **`f_b`.** `f`'s body moves to a new function `f_b`. In it, the borrowed
  parameters' drops are empty statements. `f_b` keeps `f`'s kernel mark
  (design/parallel.md 2.4).
- **The wrapper.** `f` becomes a wrapper with the old convention: it calls
  `f_b(params)`, drops the borrowed parameters and returns the result. A
  caller that passes a fresh string or a moved local, a call through a
  pointer, and the runtime's callbacks all keep calling `f`. The inliner then
  puts small wrappers in place.
- **The call rewrite.** A direct call of `f` becomes `f_b(y)` when the
  argument for each borrowed parameter is `rt_str_dup(y)`, provided:
  - `y` is a local, or members of a local;
  - the caller never takes that local's address;
  - no other argument of the call names the local except to copy it.

  Then nothing can change or free `y` during the call: the callee cannot
  reach the caller's locals, and globals cannot be borrowed. A task that
  parks inside `f_b` changes nothing, because other tasks cannot reach the
  caller's frame either.

The rule (section 1) has one change. A parameter passed straight on as an
argument, without a copy, counts as a read only when the other function's
parameter is lent (a `&str`: never dropped, never kept). Passed to an owned
parameter, it is a move, so the parameter is owned.

**The analysis** is one walk of every body. For each candidate it records
its drops, the uses that keep it, and the parameters it is passed to. A fixed
point over those records follows. Only bodies that call a function with
candidates are walked again for the rewrite. The first version walked each
body once per parameter per round, and cost 46 ms of the compiler's 470 ms
self-compile.

### 6.1 Results

**Counts** with `LXL_RCSTAT=1`. Counted dups, against `LXL_NOBORROW=1`:

| program | dups before | dups after | drops removed |
|---|---:|---:|---:|
| the compiler, compiling itself | 9.16M | 6.17M (−33%) | 2.99M |
| bench/json (5 MB) | 13.0M | 9.97M (−23%) | 3.04M |
| jq (5 MB) | 3.44M | 2.63M (−24%) | 0.81M |
| cmark (2.2 MB) | 425k | 328k (−23%) | 98k |

The compiler gains more than section 3 predicted, because the pass sees its
calls before inlining. bench/json and cmark gain less: many of their copies
are of array elements (`rt_str_dup(*(slice.data + i))`), which the rewrite
does not take (section 6.2).

**Instructions and cycles,** `-O`, `perf stat`, against `LXL_NOBORROW=1`:

| program | instructions | cycles |
|---|---:|---:|
| the compiler, compiling itself | −1.2% | −0.7% |
| bench/json | −2.0% | −0.9% |
| jq | −2.3% | −1.7% |
| cmark | −1.2% | −0.9% |
| bench strings, maps, trees, lists, alloc | 0 to −0.7% (time) | |
| bench/par hash, decimal, 8 threads | | −9% and −10% (wall time) |

The par kernels gain most: on a worker, each count change is an out-of-line
call (design/parallel.md 2.4).

**Costs:**
- **Compile time:** none without `-O` (491 against 489 ms for the compiler).
  With `-O`, 615 against 596 ms (+3%): the pass, and the extra functions the
  inliner and the code generator see.
- **Code size:** +0.8% (the compiler: 3,255,232 against 3,230,656 bytes),
  from the `f_b` copies and their wrappers.

**Tests:**
- lib/tests/run/borrow_infer_params.lxl: a borrowed function also called
  with fresh strings and through a function value; recursion; members of a
  record local; one local passed twice; a copy kept in a result; a par.map
  kernel; a task parking inside a borrowed function.
- The native suites (`--lib`, `--lib --opt`, epoll) against the C backend,
  which the pass does not touch, with `LXL_CHECK=1` leak checks: 648 of 648.
- The `-O` self-build reaches a fixed point.
- The full gate passes, but for red-team round 2's `so_big_frames`, which
  fails on main too.

### 6.2 Not done

- **Array elements as the borrowed argument.** An element read through a
  shared slice cannot change during the call: the array is frozen while the
  slice lives, SPEC 10. But the IR does not say whether a slice is shared
  or `mut`. Carrying that through lower, or proving that the call writes no
  memory the slice reaches, would take bench/json and cmark nearer section
  3's figures.
- **Records holding strings passed by value** (their dup glue).
- **A wrapper whose callers are all rewritten** stays until the inliner's
  dead-function removal drops it, when nothing names it.

## 7. The library's signatures (2026-11-14)

The pass removes counts the source could have avoided: many library
functions declared `s: str` for a string they only read. So the signatures
were fixed as well.

**The report.** `lxlc --borrow-report prog.lxl` runs the analysis without
changing anything. It prints each parameter declared `str` that every
instance in the program only reads:

    path:line: parameter 's' of f is declared str but only read: declare it &str

With `LXL_BORROW_REPORT=all` it also prints the parameters that are kept
somewhere ("... is declared str and kept").

**The sweep.** The report was run over the compiler, `cmd/`, `bench/` and
every test.
- 1,026 library parameters that no program keeps became `&str`.
- Their call sites got `&x` or `&(expr)`. A script did this from the
  compiler's errors, and four Haiku agents fixed the rest.
- A `&str` parameter copied into a `var` became `var x: str = s`.
- Interface methods (`Writer.write` for `Sink`) stay `str`.
- `str`'s own methods now borrow their receiver. red-team round 5's
  `m10_receiver_str_field`, which moved the receiver's owner in an argument,
  is now refused, and is an error case.

**The check.** `tools/borrow_check.py` runs the report over the same programs
(11 s) and combines the verdicts. It fails when a module in `lib/` has a
`str` parameter that no program keeps, unless `tools/borrow_allow.txt` lists
it. It is a step of the quick gate.

### 7.1 Results

Counted dups (`LXL_RCSTAT=1`) and instructions, against the library before
the sweep with the pass off:

| workload | sweep only | pass only | both |
|---|---:|---:|---:|
| the compiler, compiling itself | −19% dups, −1.1% instr. | −33%, −1.3% | −43%, −1.9% |
| cmark | −49%, −3.3% | −23%, −1.2% | as the sweep |
| jq | −29%, −3.3% | −24%, −2.3% | as the sweep |
| bench/json | −34%, −4.4% | −23%, −2.0% | as the sweep |

**Where each one pays:**
- **The library's programs.** The signatures do more than the pass ever
  could. They cover every build, not only `-O`, and the calls that pass an
  array element, which the pass does not take. Once they are right, the pass
  adds nothing there.
- **The compiler.** It still gains from the pass, because its own 199
  parameters were not swept.
- **Code outside the sweep, generic instances and interface methods.** The
  pass keeps working there, which is why it stays.

### 7.2 The compiler and cmd/ (2026-11-14)

The same sweep over `compiler/` and `cmd/` changed 463 parameters. The
lexdb server's modules were left for a later sweep (7.3), with only the call
sites the library change needed touched there. The call-site script gained three repairs, and each `let` it adds
goes only at the start of a statement, never into a condition or a branch:
- `var x = s` becomes `var x: str = s`;
- an argument borrowed from the receiver of a `mut` method (`p.node(...,
  &p.toks[t].s)`) is moved into a `let` copy first;
- a temporary that the result keeps a borrow of is moved into a `let`.

The compiler, compiling itself with `-O`:

| | dups | instructions |
|---|---:|---:|
| library swept, pass off | 7.43M | 6.382G |
| library swept, pass on | 5.26M | 6.328G |
| everything swept, pass off | 5.01M | 6.209G |
| everything swept, pass on | 5.01M | 6.209G |

**The pass now finds nothing to do** in any workload measured here, and
leaves the binaries the same size. It costs 1.6% of `-O` compile time (550
against 559 ms). It stays for code the sweeps have not reached, generic
instances and interface methods.

**The compiler is faster from the sweeps:** a default compile of itself
takes 465 ms, against 489 before them, and an `-O` compile 550 against 596.

### 7.3 The lexdb server's modules (2026-11-14)

The same sweep over `cmd/lexdb*.lxl`, with the report run over `cmd/lexdb.lxl`,
every program in `tests/lexdb/run/` and the crash client, combined as in
`tools/borrow_check.py`, changed 152 parameters that no program keeps:
tns 30, store 28, sql 25, exec 21, base 8, plsql 5, disk, lexdb, orafn, tds
and tsql 4 each, wire 3, and 2 each in auth, func, oratext, page, repl and
tsqlfn. Their call sites, in the modules and in 26 test programs, got `&x` or
`&(expr)`. Besides the three repairs of 7.2 there were three more by hand:
- an `if` expression as an argument became `&(if ...)` when every branch
  makes a temporary, and a statement `if` with a call in each branch when one
  branch is a borrow (the two leaf scans of `Store`, `catKey`,
  `logFs`);
- a global cannot be borrowed, so `noCow(LOG_DIR)` copies it into a `let`;
- `t.noteWrite(..., &t.writes[i].key, ...)` and `w.paramStatus(..., &w.tzShown)`
  borrow the receiver of a `mut` method, so the argument is copied into a
  `let` first.

Existing `&(s.toStr())` on a parameter that is already `&str` became `s`.

20 `str` parameters remain, each kept by some program: the `Fs` methods `openWith`,
`exists`, `remove`, `rename` and `holdFlushes`,
`cachePut`, `putSmall`, `Store.getIn`, `snapGet`, `scanIn`,
`scanBackIn`, `scanLeaves`'s `to`, and the `dir` of `supervise`, `runMaster`
and `runReplica`, and the `sql` of `Conn.simple` and `Conn.rowsOf`.

The server's speed does not change. Alternating the binaries three times each
(pgbench, prepared, the 1M-row table): 142.1k against 142.3k tps at 32
clients, 143.7k against 143.1k at 8, 85.7k against 86.6k at 1, 21.86k
against 21.78k for updates, and the same CPU per transaction (7.0 and 32.1
microseconds), peak RSS (172 MB) and scan times. The binary is 2.5% smaller
(11.99 MB against 11.70). The server's reads do not copy strings in the
paths the benchmark runs, so the sweep is for the code that does.

At first dups were not counted: `LXL_RCSTAT=1` printed nothing at exit for
the server or the lexdb test programs, only the compile line (owned-convention
`str` parameters left for the pass in `lexdb.lxl -O`: 35 before, 32 after).
The cause: a program that links libc returns from `main` into libc's `exit`,
not through `rt_quit`, which was the only caller of the report; `rt_finish`
now prints it too (`rt_rc_done`, once). Counted afterwards with the same
compiler, `tests/lexdb/run/exec_agg.lxl -O`, before the sweep (8e5d1b4e)
against after (001b323f): dups 6526 against 6461 (-1%), literal dups 10396
against 10355, drops 11215 against 11150, and literal drops 25273 against
18032 (-29%).
