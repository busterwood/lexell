# Lexell benchmarks

Twenty small programs, each built with the default native backend and, with
`--c`, through C. Each has a Java port, and all but `pingpong` a hand-written Rust
port (`pingpong` has a Go one instead: Rust's lightweight tasks are an async runtime
crate, and the ports use none):

- `fib` (calls), `loop` (integer arithmetic), `array` (indexing), `sieve`, `alloc`
  (a record per iteration), `lists` and `trees` (owned boxed nodes), `strings`
  (building strings), `tokens` (scanning with views), `maps` (std Map);
- `nbody` (floating point), `interp` (a stack machine: an enum with payloads run
  by a match), `closures` (stable sorts with comparator closures, calls through an
  array of functions), `matmul` (a 400 x 400 product over arrays of rows) and
  `pingpong` (two tasks handing a counter back and forth through promises);
- `bitpack` (columnar bit-packed integer decode, filter and multiply-sum),
  `btree` (in-memory order-32 B-tree inserts, splits, lookups and range scans),
  `hashagg` (open-addressing columnar hash aggregation), `varint_csv`
  (delimited text parsing and LEB128 varint encoding) and `enum_eval` (boxed
  closed-type SQL expression AST evaluation over columnar batches).

    python3 lexell/bench/bench.py [-n RUNS] [--only NAME ...] [--obo] [--opt] [--perf]
                              [--no-rust] [--no-java]

`--opt` adds a `native -O` build and its columns; `--perf` adds instructions
and cycles (`perf stat`, user mode) beside the wall times. The compile cost
of `-O` itself is `python3 lexell/tools/optcost.py --compiler <native-built
lxlc>`.

## Compile time and size

`python3 lexell/bench/compile.py -n 3` times a hello world, the nine benchmark
programs and the compiler self-build, and reports the resulting binary
sizes, against rustc and gcc. It is the source of PERFORMANCE.md's compile
table. The builds are not identical: Lexell emits nine small executables, the
Rust project one binary with nine subcommands, and cargo measures its own
build system.

## Like-for-like comparisons

There are three different questions, and they must not be mixed:

1. **Same Lexell source, native against the C backend.** The two builds are the
   same algorithm, the same checks and the same runtime semantics; the
   difference is the code generator (and the runtime implementation). This is
   an internal regression check: the C backend stays for the bootstrap seed,
   portability and differential testing. It is the `native/C` column, kept
   in [design/native-vs-c.md](../design/native-vs-c.md).
2. **Same algorithm written in C, against native Lexell.** This is the
   language/runtime comparison: allocation, strings, records, the ABI, the
   checks the language requires. `lexell/bench/c/NAME.c` holds these
   references, built with `gcc -O2 -fno-optimize-sibling-calls`; the table's
   `plain C` and `native/plain C` columns are this question.
3. **The same algorithm written in Rust, against native Lexell.** This is a
   second language/runtime comparison, and the closest external one because
   Lexell's ownership model is close to Rust's. `lexell/bench/rust/` holds the
   ports, built once with `cargo build --release`; the table's `Rust` and
   `native/Rust` columns are this question. It is not a compiler-backend
   comparison: the Rust code is an independent, idiomatic implementation of
   each program, not the same IR lowered by another backend.
4. **The same algorithm in Java, on a warmed-up JVM.** `lexell/bench/java/Bench.java` holds the
   ports (OpenJDK 21, default tiered C1/C2; `pingpong` on virtual threads), compiled once with `javac`; the table's
   `Java (warm)` column is one JVM per program, the best of RUNS runs inside it after a warm-up
   run, so the JIT has compiled the hot code and JVM startup is not counted. Arithmetic that
   Lexell checks uses `Math.addExact` and `multiplyExact`; the checksum must match. This is the
   managed-runtime comparison: a JIT with profile-guided inlining, escape analysis and a
   generational collector against an ahead-of-time compiler with owned memory.
5. **Another implementation (Rust regex, Go regexp, GNU grep, jq, cmark,
   OpenSSL).** These are usually a different algorithm. They answer "is our
   algorithm competitive", not "is our compiler generating good code". The
   regex and JSON benchmark scripts report them; keep them out of the
   compiler's verdict.

The hand-written C reference must execute the same work as the Lexell program.
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

The Rust ports in `rust/` are one dependency-free Cargo project (`dbench`,
one subcommand per benchmark, plus `strings-rc`). They do the same work and
print the same checksum as the Lexell programs; `bench.py` requires the outputs
to be equal. The build is deliberately fair and fixed in the project:

- `opt-level = 3`, `lto = "thin"`, `codegen-units = 1`, `panic = "abort"`.
- `-C target-cpu=x86-64-v3`, the ISA the native backend requires.
- `overflow-checks = true`: Lexell's `+`, `-` and `*` are checked, and `loop`
  measures two checked operations per iteration, so the Rust build must keep
  them too.
- no `unsafe`, no `get_unchecked`, no external crates, no threads or
  `std::arch` intrinsics; the bounds checks stay on.
- `std::hint::black_box` and the command-line sizes (where `c/NAME.c` has
  them) keep LLVM from constant-folding or closing the work up. `fib` is
  `#[inline(never)]` and both recursive calls stay.
- `loop` keeps `loop.lxl`'s constant bound, with no argv and no barrier, so
  LLVM can prove the two overflow checks cannot fail as the native `-O` pass
  does. The C reference's argv bound and asm barrier exist only to stop gcc
  closing the form; the Rust port matches the Lexell source, not that harness.

`strings` is measured with idiomatic `String` in the table; `dbench
strings-rc` runs the same concatenations on `Rc<str>`, which matches Lexell's
refcounted `str`, and that number is reported beside the table.

`maps` has no plain C reference yet, and no Rust one: the Lexell map's
insertion order, keyed hash and `u32` index slots have no direct Rust std
equivalent, so a port would approximate rather than compare the same work.

For each program it builds `NAME.lxl` with `lexell/compiler/out/lxlc` (or
`$LXLC`) twice, with the default native build and through C (`--c`, `gcc -O2`). It checks that the
two print the same result and are leak free (`LXL_CHECK=1`), then reports the
best wall time of N runs (default 5) with `LXL_CHECK` unset. A program with a
hand-written C reference in `c/NAME.c` is also built with `gcc -O2` and timed,
as the "plain C" column. The Rust binary is built once (offline) and every
port must print the Lexell checksum; `maps` shows `-` because it has no port.
When cargo is not installed (or `--no-rust` is given) the note is printed and
the Rust column is `-`.

The runs set `LXL_HASH_SEED=42` (`--hash-seed N`, or `--random-hash` for the
production default), so `maps` hashes the same way in both builds and in every
run. The runtime reads that variable once, in `lxllib_hash_key`, and derives
the same key for the two builds; without it, the key stays the per-process
random one from `AT_RANDOM`. `Map` keeps insertion order, so the program's
output does not depend on the seed.

| program | what it does |
|---|---|
| `fib` | recursive calls |
| `loop` | two overflow-checked operations per iteration |
| `array` | checked indexing |
| `alloc` | 20 million records allocated and freed |
| `lists` | a linked list built, summed and dropped |
| `strings` | concatenation and `toStr` |
| `trees` | binary trees |
| `tokens` | byte scanning and hashing; reads `lexell/compiler/sema.lxl` (any text file works) |
| `sieve` | the sieve of Eratosthenes up to 10 million, ten rounds; `c/sieve.c` is the same in plain C |
| `maps` | `std.Map`: 200,000 short and 200,000 long `str` keys and 200,000 `int` keys put, looked up four times, and missed |
| `bitpack` | columnar bit-packed integer decode (6/4/17-bit), selection filter and multiply-sum |
| `btree` | in-memory order-32 B-tree inserts/splits, lookups and range scans |
| `hashagg` | open-addressing columnar hash aggregation (COUNT/SUM/MIN/MAX over 16K groups) |
| `varint_csv` | delimited text field parsing and LEB128 varint encoding |
| `enum_eval` | boxed closed-type SQL expression AST evaluation over columnar batches |

The results, with eza and the compiler, are in
[PERFORMANCE.md](../../PERFORMANCE.md).

## Explicit SIMD microbenchmarks

The twenty programs in `bench.py` are strictly plain, non-vectorized code in
Lexell, Rust and Java (no explicit `vector[T]`, `std::arch` or
`jdk.incubator.vector`). Explicit 256-bit AVX2 SIMD kernels live in a separate
suite so all three languages use their explicit vector APIs side by side:

    python3 lexell/bench/simd_bench.py [-n RUNS] [--only NAME ...] [--opt] [--no-rust] [--no-java]

- **Lexell** (`simd/{array,sieve,matmul,bitpack,dot}_vec.lxl`): built-in,
  bounds-checked `vector[T]` (no `unsafe`).
- **Rust** (`rust/src/main.rs`, `*_vec` subcommands): `std::arch::x86_64`
  AVX2/FMA intrinsics (`unsafe`, since `std::simd` is nightly-only on stable
  `rustc`).
- **Java** (`java/SimdBench.java`): OpenJDK 21 `jdk.incubator.vector` Vector API
  (`--add-modules jdk.incubator.vector`, warmed up).

Every port must print the exact same checksum, and Lexell builds are checked for
leaks under `LXL_CHECK=1`.

## Application suite

`python3 lexell/bench/apps.py [-n RUNS] [--only APP ...] [--json] [--json-out FILE]
[--tsv FILE] [--pin CORE] [--no-perf] [--no-opt] [--json-mb MB] [--md-mb MB]`
is the Tier-1 table for applications: each source is built with the native
backend (`-O`) and through C (`--c`), the two builds must print the same counts or checksums
(timings in their output are ignored), and both are timed with `perf stat -e
instructions:u,cycles:u`, best of RUNS, pinned to one core (default 4). It
reuses the existing harnesses rather than their input generation: `regex`
(`regex_bench.lxl` and `gen_corpus.py`), `json` (`json_bench.lxl` and
`gen_data.py`, 20 MB by default), `jq` (`cmd/jq.lxl`, `-c .` on that data,
output SHA-256 compared), `cmark` (`cmd/cmark.lxl` on the CommonMark spec
repeated to 10 MB, the `tests/markdown.py --perf` input) and `decimal`
(`dbench.lxl`, every case, checksums compared; its row sums the cases). The
table is also available as JSON (`--json`, `--json-out`) and TSV (`--tsv`) for
regression tracking.

One baseline, `-n 3`, core 4, hash seed 42, 47.3 s end to end (`feat/simd-vector` at `ab29758c`):

| application | native -O | C | native/C | native Minstr | C Minstr | instr native/C | native Mcyc | C Mcyc | cyc native/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| regex | 49 ms | 48 ms | 1.01 | 522.6 | 494.2 | 1.06 | 128.9 | 118.5 | 1.09 |
| json | 213 ms | 275 ms | 0.78 | 2757.9 | 2771.1 | 1.00 | 878.0 | 998.9 | 0.88 |
| jq | 161 ms | 213 ms | 0.76 | 2423.3 | 2319.4 | 1.04 | 624.2 | 715.0 | 0.87 |
| cmark | 101 ms | 102 ms | 0.98 | 1092.5 | 928.3 | 1.18 | 341.6 | 333.2 | 1.03 |
| decimal | 2464 ms | 2503 ms | 0.98 | 41135.4 | 31569.5 | 1.30 | 8334.2 | 8551.4 | 0.97 |

Native `-O` is level with or ahead of the C backend on all five applications: `json` (0.78×) and `jq` (0.76×) lead by 22–24% on wall time, `cmark` and `decimal` edge ahead at 0.98×, and `regex` is level at 1.01×. The suite also sets `LXL_HASH_SEED` (42 by default, `--random-hash` to opt out), so map-using programs hash identically in both builds.

`regex/` is the regex library's benchmark (design/regex.md section 4):
`python3 lexell/bench/regex/bench.py` times eight patterns over a generated
3 MB corpus with Lexell (native and via C), Go's `regexp`, Rust's `regex`
crate (built offline; skipped if it cannot be) and ripgrep.

`json/` is the JSON library's benchmark (design/json.md, section 9).
`python3 lexell/bench/json/bench.py` generates an 80 MB file. On it, it
compares:

- the library (native and through C) with Python's `json`;
- `cmd/jq.lxl` (native and through C) with jq 1.7.1, running the same
  filters.

`simd/` measures the size of the explicit-SIMD prize (design/simd.md):
`python3 lexell/bench/simd/run.py` builds scalar C, gcc auto-vectorised C and
hand AVX2 versions of `array`, `loop`, `sieve`, `tokens`, `strings` and a
float dot product, plus the exact instruction sequence the proposed vector
extension would emit, pinned to one core.

`--obo` adds a column for Lexell's predecessor, the archived obo 0.19
(`archive/obo/obo`; build it with `make -C archive/obo`), running the same
programs from `archive/obo/bench/*_obo.obx`. The programs came from obo's
benchmarks and do the same work, written the Lexell way: `Option[Node]` links
instead of nullable references, the list `sum` recursing over borrows,
`StrBuf` for building identifiers.

## Parallel map

`par.lxl` measures `par.map`'s kernels and the cost of a call
(design/parallel.md 6.2). `par_db.lxl` and `par_copy.lxl` apply it to work
shaped like lexdb's (aggregation, DISTINCT, hash probes, expressions, and
the wide COPY parse/encode). `par_db_run.py` runs the matrix and writes its
TSV; design/par-db-perf.md gives the results, the profiles and the
projections.

## TPC-H, derived

`tpch/` runs the 22 TPC-H queries over dbgen data against lexdb and
PostgreSQL on one machine. It is derived from TPC-H, not an audited TPC
result, and it has no refresh functions: see
[tpch/README.md](tpch/README.md) for the rules, modes and output. First
`bench/tpch/fetch.sh WORKDIR/tpch-kit`; then
`bench/tpch/run.sh LEXDB WORKDIR [SCALE] [RUNS]`.

## Notes

- **Native and C.** The native backend is ahead on allocation and strings
  (its own size-class allocator, checks generated inline) and, since its
  loop pass, on the tight loops too (loop, array); fib is level.
- **`loop`** is two overflow-checked operations per iteration. The native
  backend proves both cannot overflow (`i < n` bounds `i` and `i * 2`) and
  runs the loop at one cycle an iteration; gcc keeps the checks.
- **`array`** hoists its bounds check out of the inner loop via loop
  versioning (`versionLoop` in `loops.lxl`), leaving only the checked
  additions in the hot loop.
- **Allocation-bound programs** (lists, trees): through C, about half the
  time is libc's `malloc` and `free`, one block per node.
- **`strings`**: every `+` allocates a new reference-counted block, and
  `"word" + i.toStr() + "-" + round.toStr()` makes two intermediate blocks.
  Building one block for a whole `a + b + c` chain would remove them.
- **Live-object counting** (`LXL_CHECK`) is a branch on a flag read once at
  start-up: about 3% of instructions on `alloc` at most, within noise in
  cycles.
