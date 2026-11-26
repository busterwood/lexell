# Working on Lexell: a guide for coding agents

Lexell is a systems language: single ownership, `&T` borrows, no garbage
collector, generics checked where they are written. The compiler, `lxlc`, is
written in Lexell and emits x86-64 ELF directly (or C with `--c`). The
repository also holds the library (`lexell/lib/`), command-line programs
(`lexell/cmd/`), and lexdb, a SQL server written in Lexell (`lexell/cmd/lexdb*.lxl`).

This page is the root. Read it whole, then open only the pages the table at
the end points you to for the task in hand. `lexell/SPEC.md` is the normative
definition of the language; you should rarely need to read all of it.

## A program

```lxl
import "strings"

type Item = record { name: str; qty: int; price: Decimal }

type LineError = closed { Fields(int); Qty { line: int; text: str } }

fn parseItem(line: &str, n: int): Result[Item, LineError] {
    let parts = strings.split(line, ",")              // []&str: views of line
    if len(parts) != 3 { return Err(LineError.Fields(n)) }
    let qty = match strings.parseInt(parts[1]) {
        Ok(q) { q }
        Err(_) { return Err(LineError.Qty{line: n, text: parts[1].clone()}) }
    }
    let price = Decimal.parse(parts[2]).unwrap()
    return Ok(Item{name: parts[0].clone(), qty: qty, price: price})
}

fn total(items: &[]Item): Decimal {
    var sum = 0m
    for it in items { sum = sum + it.price * Decimal.fromInt(it.qty) }
    return sum
}

fn describe(e: &LineError): str {
    return match e {                                  // patterns are one level deep
        LineError.Fields(n) { "line " + n.toStr() + ": want 3 fields" }
        LineError.Qty(line, text) { "line " + line.toStr() + ": bad qty " + text }
    }
}

fn main() {
    var items: []Item = []
    var n = 0
    for line in strings.split("tea,2,3.50\ncake,x,4.25", "\n") {
        n += 1
        match parseItem(line, n) {
            Ok(it) { append(mut &items, it) }
            Err(e) { eprintln(describe(&e)) }
        }
    }
    var out = "total "
    out += total(&items).toStr()
    println(out)
}
// expect: total 7.00
// stderr: line 2: bad qty x
```

It prints `line 2: bad qty x` to stderr and `total 7.00` to stdout.

## What trips up agents who know Rust or Go

1. **No semicolons needed** (`;` is accepted). A newline ends a statement after a name, a literal,
   `)`, `]` or `}`. To continue a long expression, end the line with an
   operator or stay inside `( )`.
2. **A fractional literal needs a suffix:** `0.5m` is a `Decimal`, `0.5f` a
   `float`. `0.5` alone is a compile error. Money is `Decimal`, never `float`.
3. **`let` cannot be reassigned, `var` can.** No shadowing inside a function.
4. **`str` is owned and moves.** `let t = s` moves `s`. `&str` is a view
   (pointer and length), and `s[a..b]` is always a view. Write `.clone()` to
   get an owned copy. A parameter that only reads a string is `&str`: the
   gate's borrow check fails on a library `str` parameter that could be one.
5. **Borrows at a call:** `show(x)` borrows `x` for a `&T` parameter without
   writing `&`, but a `mut &T` parameter needs `mut &x` written out.
6. **Variants are qualified by their type:** `LineError.Fields(n)`, in
   expressions and in `match` arms. Only the prelude's `Some`, `None`, `Ok`
   and `Err` may be written bare. Patterns are one level deep (bind, then
   `match` again), and a variant with named fields binds them by position, in
   declaration order: `LineError.Qty(line, text)`.
7. **`record` is boxed on the heap and owned; `value record` is stored inline**,
   and is a copy type when all its fields are. Pick `value record` for small
   plain data.
8. **Methods are declared with a receiver:** `fn (p: &Point) norm(): int`,
   `fn (m: mut &Buf) push(b: byte)`, `fn (Decimal) parse(s: &str)` for an
   associated function. They can only be declared in the type's own module.
9. **Generics see only their constraints:** `fn max[T: Ord + copy](a: T, b: T): T`.
   An unconstrained `T` is owned and has no methods. Interfaces are
   structural and are used only as constraints; there are no interface values.
10. **Closures (`&fn(...)`) are borrows.** They can be parameters and `let`s
    but cannot be stored, returned or sent to a task. Tasks take a plain `fn`
    value and an owned argument.
11. **Arithmetic is checked.** Overflow, division by zero, an out-of-range
    index and a lossy conversion stop the program (`Lexell: ... at file:line`,
    exit 10 or 3). `+% -% *%` wrap. There are no implicit conversions:
    `int(b)`, `byte(n)`, `float(n)`.
12. **Errors are values:** return `Result[T, E]` with a `closed` error type
    and propagate with `try e` (the function's `E` must be the same type).
    `panic` is for bugs, not input.
13. **You cannot move out of a field, an element or a borrow.** Use
    `replace(mut &p, v)`, `swap`, `pop` or `move(x)`.
14. **`if` and `match` expressions have one expression per branch**, in
    braces: `let k = if a { 1 } else { 2 }`.
15. **Imports:** `import "strings"` names a library module, used qualified
    (`strings.split`). A program's own modules are `import "./ast"`. The
    prelude (`lib/std.lxl`: `Option`, `Result`, `println`, `Map`, `sort`, ...)
    needs no import.
16. **The compiler stops at the first error** and prints `file:line: message`.
    Messages usually say what to write instead; read them literally.

## Build, run, test

Run these from the repository root (`~/Work/lexell`).

    lexell/compiler/build.sh                       # build lexell/compiler/out/lxlc from the C seed
    lexell/compiler/out/lxlc prog.lxl -o prog      # native x86-64 ELF (the default backend)
    lexell/compiler/out/lxlc prog.lxl -O -o prog   # optimised: use for anything you time
    lexell/compiler/out/lxlc prog.lxl --run        # build and run
    LXL_CHECK=1 ./prog                             # exit 5 if anything leaked
    lexell/compiler/out/lxlc --borrow-report prog.lxl   # str parameters that should be &str
    lexell/compiler/out/lxlc --help                # every option and environment variable
    python3 lexell/tools/libapi.py strings split   # a library function's signature and comment

    lexell/tools/gate.sh quick                     # after every change (seed, conformance, compiler, library, docs; not lexdb)
    lexell/tools/gate.sh full                      # before a merge: adds red-team rounds under sanitizers
    python3 lexell/tests/run.py [filters]          # conformance suite only
    python3 lexell/lib/run_tests.py -j 8 [filters] # library tests only
    LXL_NOCACHE=1 python3 lexell/tests/lexdb.py -j 4 [filters]   # lexdb tests, native builds

- **Build natively.** `lxlc` builds native by default. Do not switch to `--c`
  (gcc) for speed, symbols or profiling: it takes far longer and is not what
  ships. For lexdb tests always set `LXL_NOCACHE=1`; the cached path goes
  through gcc.
- **`-O` is the optimiser.** Without it you get inlining only. With it you also
  get loop optimisation (headers hoisted, bounds and overflow checks proved
  away), reuse of repeated loads, and borrow inference for `str` parameters.
  Every benchmark, A/B comparison and profile uses `-O`: unoptimised times are
  not comparable (TPC-H q1 on lexdb is about 14% slower without it). Each pass
  can be turned off alone to find a miscompile: `LXL_LOOPS=0`, `LXL_CSE=0`,
  `LXL_INLINE=0` (`lxlc --help` lists them).
- **Profiling: perf works on a native build as it is.** The executable has a
  symbol table, so `perf report` shows Lexell's functions. Profile the `-O`
  build, not a gcc one. Names carry a module prefix: `fib` in `hot.lxl` is
  `f1_hot_fib`.

      lexell/compiler/out/lxlc prog.lxl -O -o prog
      perf record -e cycles:u -g ./prog args...
      perf report --stdio --no-children | head -40

  `LXL_NATIVE_MAP=prog.map` also writes a list of every function, one line
  each, `address size name` in hex, in the format of perf's
  `/tmp/perf-PID.map`. The executable loads at 0x400000, so you can match
  addresses from `perf script -F ip` or `objdump -d` against it. For A/B
  comparisons, `perf stat -e instructions:u` counts are steadier than times;
  run both builds with `LXL_HASH_SEED=1`.
- **Tests use one format** (`lexell/tests/README.md`): a `.lxl` file under
  `run/` with `// expect: line` comments for stdout, `// exit: N`, or under
  `error/` with `// error: words` for a compile error that must happen. Run
  tests are checked for leaks. A test needing a live service exits 77 when
  it is missing and has `_live` in its name.
- **A compiler change needs a reseed:** `lexell/compiler/reseed.sh`, then
  the gate (its first step checks the seed's fixed point).
- **Changing the language** means changing `lexell/SPEC.md`, the compiler and
  the tests together.

## Rules of this repository

- Commit to `main`; push after each verified merge. Never commit files you
  did not write: other work may be in progress in the same tree.
- **lexdb:** a SQL feature goes into every dialect that has it natively
  (PostgreSQL, T-SQL, Oracle), each tested through its own door. Single-row
  primary-key selects must never get slower: A/B instructions per statement
  (`perf stat -e instructions:u`, `LXL_HASH_SEED=1`) for any change to
  planning, binding, sessions or the row path. New executor code goes in its
  own module, not `lexdb_exec.lxl`. Builds for timing use `-O`.
- **Benchmarks:** record every comparison with another engine in
  `lexell/design/lexdb-benchmarks.md` (and its tables in
  `lexell/docs/lexdb/performance.md`, where `PERFORMANCE.md` now points for
  lexdb). The published pages hold only the latest numbers, never history. Pin the
  server to CPUs 0-3 and clients to 4-7,12-15 (SMT siblings are N and N+8).
  Other sessions share this machine: take `~/tpch/.bench.lock` exclusively
  for a timing (`flock ~/tpch/.bench.lock taskset -c 4-7 ./prog`) and shared
  for builds and test runs (`flock -s ~/tpch/.bench.lock ...`), so neither
  disturbs the other.

## Where to read next

| Read this | When |
|---|---|
| [lexell/docs/lang/tour.md](lexell/docs/lang/tour.md) | writing Lexell for the first time: the language by example, beside Rust |
| [lexell/docs/lang/idioms.md](lexell/docs/lang/idioms.md) | writing or reviewing code: the preferred patterns, each as do / don't / why |
| [lexell/docs/lang/errors.md](lexell/docs/lang/errors.md) | a compile error you don't understand: message, cause, fix |
| [lexell/docs/lang/testing.md](lexell/docs/lang/testing.md) | adding or running a test: which suite, the directives, the gate tiers, the generators |
| [lexell/docs/lang/performance.md](lexell/docs/lang/performance.md) | timing, profiling or speeding up code: the `-O` and perf recipes, A/B by instructions, pinning and the bench lock |
| [lexell/docs/lang/concurrency.md](lexell/docs/lang/concurrency.md) | writing code with tasks, timers, sockets, `Shared`, blocking C calls or `par.map`, or a program that stops with exit 13, 14 or 15 |
| [lexell/docs/lang/c-interop.md](lexell/docs/lang/c-interop.md) | calling C: externs, `ptr` and `ffi`, strings and arrays, linking, and wrapping an extern safely |
| [lexell/docs/lang/compiler.md](lexell/docs/lang/compiler.md) | changing the compiler: building it beside `out/`, the reseed, debugging a miscompile, what to run before a merge |
| `python3 lexell/tools/libapi.py [MODULE [NAME...]] [-s]` | looking for a library function: no arguments lists the modules and their most-called functions; a module prints its `pub` API (signatures, comments, `file:line`); names filter it |
| [lexell/lib/README.md](lexell/lib/README.md) | what each library module covers, and the library tests |
| [lexell/SPEC.md](lexell/SPEC.md) | a precise rule: ownership (9), borrows (10), C interop (12), tasks (16) |
| [lexell/tests/README.md](lexell/tests/README.md) | adding tests, or a gate step failed |
| [lexell/compiler/README.md](lexell/compiler/README.md) | changing the compiler: its files and passes |
| [lexell/cmd/README.md](lexell/cmd/README.md) | the programs, including running lexdb |
| [lexell/design/lexdb-layers.md](lexell/design/lexdb-layers.md) | working on lexdb's engine: its layers and module boundaries |
| [lexell/docs/lexdb/README.md](lexell/docs/lexdb/README.md) | lexdb as its users see it |
| `lexell/design/` | the decision record for one subsystem; the file is named after it |
