# Borrow inference for str parameters: a measurement

Status: an experiment, 2026-11-14, on branch `exp/borrow`, taken from `par`.
Nothing is optimised. The compiler only counts what borrow inference would
remove.

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

## 5. Next, if it is built

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
