# obx benchmarks

Ten small programs, each building the same program with both backends,
native and via C. Nine of them also have a hand-written Rust port:

    python3 obx/bench/bench.py [-n RUNS] [--only NAME ...] [--obo] [--opt] [--perf]
                              [--no-rust]

`--opt` adds a `native -O` build and its columns; `--perf` adds instructions
and cycles (`perf stat`, user mode) beside the wall times. The compile cost
of `-O` itself is `python3 obx/tools/optcost.py --compiler <native-built
obxc>`.

## Like-for-like comparisons

There are three different questions, and they must not be mixed:

1. **Same obx source, native against the C backend.** The two builds are the
   same algorithm, the same checks and the same runtime semantics; the
   difference is the code generator (and the runtime implementation). This is
   an internal regression check: the C backend stays for the bootstrap seed,
   portability and differential testing. It is the `native/C` column, kept
   in [design/native-vs-c.md](../design/native-vs-c.md).
2. **Same algorithm written in C, against native obx.** This is the
   language/runtime comparison: allocation, strings, records, the ABI, the
   checks the language requires. `obx/bench/c/NAME.c` holds these
   references, built with `gcc -O2 -fno-optimize-sibling-calls`; the table's
   `plain C` and `native/plain C` columns are this question.
3. **The same algorithm written in Rust, against native obx.** This is a
   second language/runtime comparison, and the closest external one because
   obx's ownership model is close to Rust's. `obx/bench/rust/` holds the
   ports, built once with `cargo build --release`; the table's `Rust` and
   `native/Rust` columns are this question. It is not a compiler-backend
   comparison: the Rust code is an independent, idiomatic implementation of
   each program, not the same IR lowered by another backend.
4. **Another implementation (Rust regex, Go regexp, GNU grep, jq, cmark,
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

The Rust ports in `rust/` are one dependency-free Cargo project (`dbench`,
one subcommand per benchmark, plus `strings-rc`). They do the same work and
print the same checksum as the obx programs; `bench.py` requires the outputs
to be equal. The build is deliberately fair and fixed in the project:

- `opt-level = 3`, `lto = "thin"`, `codegen-units = 1`, `panic = "abort"`.
- `-C target-cpu=x86-64-v3`, the ISA the native backend requires.
- `overflow-checks = true`: obx's `+`, `-` and `*` are checked, and `loop`
  measures two checked operations per iteration, so the Rust build must keep
  them too.
- no `unsafe`, no `get_unchecked`, no external crates, no threads or
  `std::arch` intrinsics; the bounds checks stay on.
- `std::hint::black_box` and the command-line sizes (where `c/NAME.c` has
  them) keep LLVM from constant-folding or closing the work up. `fib` is
  `#[inline(never)]` and both recursive calls stay.
- `loop` keeps `loop.obx`'s constant bound, with no argv and no barrier, so
  LLVM can prove the two overflow checks cannot fail as the native `-O` pass
  does. The C reference's argv bound and asm barrier exist only to stop gcc
  closing the form; the Rust port matches the obx source, not that harness.

`strings` is measured with idiomatic `String` in the table; `dbench
strings-rc` runs the same concatenations on `Rc<str>`, which matches obx's
refcounted `str`, and that number is reported beside the table.

`maps` has no plain C reference yet, and no Rust one: the obx map's
insertion order, keyed hash and `u32` index slots have no direct Rust std
equivalent, so a port would approximate rather than compare the same work.

For each program it builds `NAME.obx` with `obx/compiler/out/obxc` (or
`$OBXC`) twice, with `--native` and through C (`gcc -O2`). It checks that the
two print the same result and are leak free (`OBX_CHECK=1`), then reports the
best wall time of N runs (default 5) with `OBX_CHECK` unset. A program with a
hand-written C reference in `c/NAME.c` is also built with `gcc -O2` and timed,
as the "plain C" column. The Rust binary is built once (offline) and every
port must print the obx checksum; `maps` shows `-` because it has no port.
When cargo is not installed (or `--no-rust` is given) the note is printed and
the Rust column is `-`.

The runs set `OBX_HASH_SEED=42` (`--hash-seed N`, or `--random-hash` for the
production default), so `maps` hashes the same way in both builds and in every
run. The runtime reads that variable once, in `obxlib_hash_key`, and derives
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
| `tokens` | byte scanning and hashing; reads `obx/compiler/sema.obx` (any text file works) |
| `sieve` | the sieve of Eratosthenes up to 10 million, ten rounds; `c/sieve.c` is the same in plain C |
| `maps` | `std.Map`: 200,000 short and 200,000 long `str` keys and 200,000 `int` keys put, looked up four times, and missed |

The results, with eza and the compiler, are in
[PERFORMANCE.md](../../PERFORMANCE.md).

## Application suite

`python3 obx/bench/apps.py [-n RUNS] [--only APP ...] [--json] [--json-out FILE]
[--tsv FILE] [--pin CORE] [--no-perf] [--no-opt] [--json-mb MB] [--md-mb MB]`
is the Tier-1 table for applications: each source is built natively (`--native
-O`) and through C, the two builds must print the same counts or checksums
(timings in their output are ignored), and both are timed with `perf stat -e
instructions:u,cycles:u`, best of RUNS, pinned to one core (default 4). It
reuses the existing harnesses rather than their input generation: `regex`
(`regex_bench.obx` and `gen_corpus.py`), `json` (`json_bench.obx` and
`gen_data.py`, 20 MB by default), `jq` (`cmd/jq.obx`, `-c .` on that data,
output SHA-256 compared), `cmark` (`cmd/cmark.obx` on the CommonMark spec
repeated to 10 MB, the `tests/markdown.py --perf` input) and `decimal`
(`dbench.obx`, every case, checksums compared; its row sums the cases). The
table is also available as JSON (`--json`, `--json-out`) and TSV (`--tsv`) for
regression tracking.

One baseline, `-n 3`, core 4, hash seed 42, 59 s end to end:

| application | native -O | C | native/C | native Minstr | C Minstr | instr native/C | native Mcyc | C Mcyc | cyc native/C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| regex | 87 ms | 64 ms | 1.36 | 1215.9 | 961.1 | 1.27 | 319.9 | 217.0 | 1.47 |
| json | 629 ms | 643 ms | 0.98 | 4418.6 | 3858.5 | 1.15 | 2183.8 | 2205.6 | 0.99 |
| jq | 461 ms | 493 ms | 0.93 | 4288.6 | 3783.9 | 1.13 | 1620.3 | 1760.1 | 0.92 |
| cmark | 214 ms | 187 ms | 1.14 | 1489.6 | 1169.4 | 1.27 | 645.7 | 559.2 | 1.15 |
| decimal | 3158 ms | 2830 ms | 1.12 | 56393.8 | 44082.3 | 1.28 | 13287.9 | 11773.7 | 1.13 |

`regex` still pays for the native backend's per-match work; `json` and `jq`
are level on wall time, `cmark` within 1.14, all with more instructions
natively (the C build's libc does more per call); `decimal` is about 1.1 times
C. The suite also sets `OBX_HASH_SEED` (42 by default, `--random-hash` to opt
out), so map-using programs hash identically in both builds.

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

`simd/` measures the size of the explicit-SIMD prize (design/simd.md):
`python3 obx/bench/simd/run.py` builds scalar C, gcc auto-vectorised C and
hand AVX2 versions of `array`, `loop`, `sieve`, `tokens`, `strings` and a
float dot product, plus the exact instruction sequence the proposed vector
extension would emit, pinned to one core.

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
