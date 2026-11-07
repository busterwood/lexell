# obx benchmarks

Nine small programs, each building the same program with both backends,
native and via C:

    python3 obx/bench/bench.py [-n RUNS] [--only NAME ...] [--obo] [--opt] [--perf]

`--opt` adds a `native -O` build and its columns; `--perf` adds instructions
and cycles (`perf stat`, user mode) beside the wall times. The compile cost
of `-O` itself is `python3 obx/tools/optcost.py --compiler <native-built
obxc>`.

## Like-for-like comparisons

There are three different questions, and they must not be mixed:

1. **Same obx source, native against the C backend.** The two builds are the
   same algorithm, the same checks and the same runtime semantics; the
   difference is the code generator (and the runtime implementation). This is
   the number that decides whether the C backend can go. It is the
   `native/C` column.
2. **Same algorithm written in C, against native obx.** This is the
   language/runtime comparison: allocation, strings, records, the ABI, the
   checks the language requires. `obx/bench/c/NAME.c` holds these
   references, built with `gcc -O2 -fno-optimize-sibling-calls`; the table's
   `plain C` and `native/plain C` columns are this question.
3. **Another implementation (Rust regex, Go regexp, GNU grep, jq, cmark,
   OpenSSL).** These are usually a different algorithm. They answer "is our
   algorithm competitive", not "is our compiler generating good code". The
   regex and JSON benchmark scripts report them; keep them out of the
   compiler's verdict.

The hand-written C reference must execute the same work as the obx program.
gcc -O2 will otherwise remove it: it constant-folds `fib(40)`, turns the sum
in `loop` into a closed form, and vectorises `array`. The references say how
they are held to the same work:

- `fib.c`: `n` comes from the command line, the function is `noinline`, and
  an empty asm keeps the two recursive calls from being turned into a loop
  (`-fno-optimize-sibling-calls` as well).
- `loop.c`: `n` comes from the command line and an empty asm keeps `s` in a
  register across the iteration, so the loop cannot become a closed form or
  a vector loop.
- `alloc.c`: the allocations go through volatile function pointers, so
  malloc/free cannot be folded away.
- `array.c` is deliberately left as gcc compiles it: its 3x lead over native
  is auto-vectorisation (fewer instructions, same work), which is a real
  target, not an artifact.

`maps` has no plain C reference yet: the obx map's index layout and keyed
hash would have to be ported, not approximated.

For each program it builds `NAME.obx` with `obx/compiler/out/obxc` (or
`$OBXC`) twice, with `--native` and through C (`gcc -O2`). It checks that the
two print the same result and are leak free (`OBX_CHECK=1`), then reports the
best wall time of N runs (default 5) with `OBX_CHECK` unset. A program with a
hand-written C reference in `c/NAME.c` (no checks; so far `sieve`) is also
built with `gcc -O2` and timed, as the "plain C" column.

| program | what it does |
|---|---|
| `fib` | recursive calls |
| `loop` | two overflow-checked operations per iteration |
| `array` | checked indexing |
| `alloc` | 20 million records allocated and freed |
| `lists` | a linked list built, summed and dropped |
| `strings` | concatenation and `toStr` |
| `trees` | binary trees |
| `tokens` | byte scanning and hashing; reads `obx/compiler/sema.obx` (any text file works) |
| `sieve` | the sieve of Eratosthenes up to 10 million, ten rounds; `c/sieve.c` is the same in plain C |
| `maps` | `std.Map`: 200,000 short and 200,000 long `str` keys and 200,000 `int` keys put, looked up four times, and missed |

The results, with eza and the compiler, are in
[PERFORMANCE.md](../../PERFORMANCE.md).

`regex/` is the regex library's benchmark (design/regex.md section 4):
`python3 obx/bench/regex/bench.py` times eight patterns over a generated
3 MB corpus with obx (native and via C), Go's `regexp`, Rust's `regex`
crate (built offline; skipped if it cannot be) and ripgrep.

`json/` is the JSON library's benchmark (design/json.md, section 9).
`python3 obx/bench/json/bench.py` generates an 80 MB file. On it, it
compares:

- the library (native and through C) with Python's `json`;
- `cmd/jq.obx` (native and through C) with jq 1.7.1, running the same
  filters.

`--obo` adds a column for obx's predecessor, the archived obo 0.19
(`archive/obo/obo`; build it with `make -C archive/obo`), running the same
programs from `archive/obo/bench/*_obo.obx`. The programs came from obo's
benchmarks and do the same work, written the obx way: `Option[Node]` links
instead of nullable references, the list `sum` recursing over borrows,
`StrBuf` for building identifiers.

## Notes

- **Native and C.** The native backend is ahead on allocation and strings
  (its own size-class allocator, checks generated inline) and, since its
  loop pass, on the tight loops too (loop, array); fib is level.
- **`loop`** is two overflow-checked operations per iteration. The native
  backend proves both cannot overflow (`i < n` bounds `i` and `i * 2`) and
  runs the loop at one cycle an iteration; gcc keeps the checks.
- **`array`** keeps one bounds check per element natively: the loop runs to
  `n`, which the compiler cannot relate to the array's length.
- **Allocation-bound programs** (lists, trees): through C, about half the
  time is libc's `malloc` and `free`, one block per node.
- **`strings`**: every `+` allocates a new reference-counted block, and
  `"word" + i.toStr() + "-" + round.toStr()` makes two intermediate blocks.
  Building one block for a whole `a + b + c` chain would remove them.
- **Live-object counting** (`OBX_CHECK`) is a branch on a flag read once at
  start-up: about 3% of instructions on `alloc` at most, within noise in
  cycles.
