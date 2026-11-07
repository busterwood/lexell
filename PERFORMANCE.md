# obx performance

obx builds a program in two ways:

- **native**: `obxc --native`, the compiler's own x86-64 backend. It writes an
  ELF executable directly, with no gcc and, unless the program calls C
  libraries, no libc.
- **via C**: `obxc`, which writes C and runs gcc (`-O2 -march=x86-64-v3
  -mmove-max=128 -mstore-max=128 -ffp-contract=off -falign-functions=64
  -falign-loops=32`).

Both are built from the same IR and must behave identically; the gate checks
that on every test program. Native is the program's build; the C backend is
kept for the bootstrap seed, portability and differential testing. Its
performance comparison is not part of this report: it is in
[design/native-vs-c.md](obx/design/native-vs-c.md).

This page is the current state: the measured tables and what they say about
the code today, against external references and in absolute terms. The
figures are from 7 November 2026, the application suite and Decimal tables
at `fb50b4f1`, the rest at `b6777cf4`, and the benchmark table with the Rust
column measured on the `bench-rust` branch; where a table comes from an
earlier sweep it says so. Three references could not be re-run in this
environment: the jq 1.7.1 column, the cmark column of the Markdown table, and
the Go and Node columns of the HTTP tables.

The host is shared and variable: absolute times for I/O-bound and
process-heavy tables (eza, grep, Markdown, HTTP, TLS) move by up to 2x
between runs. Those tables use the best observed run; every ratio is from an
interleaved same-run comparison and is stable to a few percent.
The instruction columns are the most reproducible figure. The numbers are
host-dependent: use them to compare the columns, not as portable constants.

The history behind these numbers — earlier figures, the passes that got the
code here, and the experiments that did not pay — is in
[HISTORY.md](HISTORY.md), "The performance record".

## Host and method

- AMD Ryzen 7 8745HS (8 cores, 16 threads; CPUs 2k and 2k+1 are the two
  hardware threads of core k, and all cores share one L3), WSL2, Linux 6.18,
  gcc 13.3, glibc 2.39. Programs require an x86-64-v3 CPU (SPEC, exit code
  16).
- Wall clock, best of N runs (11 for the benchmarks and the compiler, 9 for
  eza, 5 or 3 where a table says so), warm cache, output to `/dev/null` or a
  pipe. Cycle and instruction counts are `perf stat`, user mode, least of N,
  pinned to one CPU. Timings vary by 5–10% between runs on this machine;
  below about 50 ms, process start-up is part of the figure.
- A server and its load client, or two measurements at once, never share a
  core: the HTTP and TLS benchmarks put the server on CPU 0 and the client
  on CPU 2.
- This machine's memory-bound figures move with its state from day to day:
  the plain C sieve, whose code does not change, varies by about 14% between
  consecutive days. Compare columns within this page, not with the figures
  in HISTORY.md.
- Every row checks its outputs first: both builds print the same result and
  are leak free under `OBX_CHECK=1`, and the tools' outputs equal the
  reference tool's.

## Benchmarks

`python3 obx/bench/bench.py --opt -n 11`
([obx/bench/](obx/bench/README.md)); the instruction and cycle counts quoted
below are from `--perf`, measuring the Rust binary the same way:

| benchmark | native -O | plain C | Rust | native/Rust | native/plain C | what it does |
|---|---:|---:|---:|---:|---:|---|
| fib | 347 ms | 348 ms | 349 ms | 0.99 | 1.00 | recursive calls |
| loop | 229 ms | 230 ms | 460 ms | 0.50 | 0.99 | two overflow-checked operations per iteration |
| array | 107 ms | 35 ms | 102 ms | 1.05 | 3.01 | checked indexing |
| alloc | 70 ms | 126 ms | 126 ms | 0.55 | 0.55 | 20 million records allocated and freed |
| lists | 31 ms | 31 ms | 40 ms | 0.79 | 1.02 | linked list build, sum, drop |
| strings | 45 ms | 91 ms | 79 ms | 0.57 | 0.49 | concatenation and `toStr` |
| trees | 20 ms | 24 ms | 25 ms | 0.82 | 0.86 | binary trees |
| tokens | 12 ms | 11 ms | 12 ms | 1.06 | 1.14 | byte scanning and hashing |
| sieve | 148 ms | 158 ms | 247 ms | 0.60 | 0.94 | the sieve of Eratosthenes to 10 million, ten rounds |
| maps | 238 ms | - | - | - | - | `Map[str, int]` with short and long keys, `Map[int, int]` (keyed hashing) |

The hand-written C references are in `obx/bench/c/` (nine programs; `maps`
has none), built with `gcc -O2`. The Rust ports are in `obx/bench/rust/`, one
dependency-free Cargo project built once with `cargo build --release
--offline`; `maps` has no Rust reference either (obx's map is
insertion-ordered and keyed-hashed, with `u32` index slots, and has no direct
Rust std equivalent). Their build settings and anti-optimisation rules are in
[obx/bench/README.md](obx/bench/README.md). The same-IR C build's column is in
[design/native-vs-c.md](obx/design/native-vs-c.md).

The plain fast-compile path (`--native`, no `-O`) is slower where the loop passes
matter: loop 446 ms, array 183 ms, sieve 187 ms; it is 0.50 on alloc and 0.54
on strings either way. `maps` moves with the hash seed;
[design/codegen-audit.md](obx/design/codegen-audit.md) records the remaining
code-shape gaps.

- **Allocation and strings are cheap** (alloc, lists, strings, tokens,
  trees). Small functions and glue are inlined before code generation; the
  freestanding runtime has a size-class allocator with no locks or libc
  bookkeeping and an 8-byte block header; the string and index checks are
  generated inline.
- **Tight loops are native's strength** (loop, array). The native backend
  tests at the bottom of loops and aligns their bodies, reads array headers
  once per loop, and drops the bounds and overflow checks that conditions,
  passed checks and induction variables prove cannot fail
  ([design/native.md](obx/design/native.md) sections 4 and 8). obx's checks
  stay where they can fail, so array keeps one bounds check per element (its
  bound is unrelated to the array's length).
- **The sieve is at plain C's speed.** A hand-written C version with no
  checks (`obx/bench/c/sieve.c`, `gcc -O2`, bench.py's "plain C" column)
  took 158 ms in the same run. Native obx runs 1,414M instructions in 626M
  cycles.
- **fib** is calls and returns: native runs 3,643M instructions in 1,524M
  cycles. Rust is level on time (349 vs 347 ms) but runs 5,133M instructions:
  its checked `n - 1` and `n - 2` add the overflow branches that native's
  backend proves away.
- **Rust is level on fib, tokens and array.** fib and tokens are the same
  time as native (349 vs 347 ms, 12 vs 12 ms); Rust's token scanner runs
  104M instructions against native's 126M. `array` is 102 ms against 107:
  both keep one bounds check per element.
- **Rust loses `loop` to checked arithmetic.** It runs 460 ms against 229
  ms, 11,000M instructions and 2,026M cycles against native's 7,000M and
  1,004M. `loop` takes `n` from the command line as the C reference does, so
  LLVM cannot bound `i` and must keep both overflow checks; `loop.obx` has
  the constant `n = 1000000000`, which native `-O` uses to prove them away.
  This is the price of obx's checked operations when the source does not
  give a provable bound.
- **C's auto-vectorisation is the array gap; checks are the sieve gap.**
  gcc turns `array`'s inner loop into AVX2 (35 ms, 3.0x native) while Rust's
  bounds checks keep it scalar (102 ms, level with native's single check).
  On `sieve`, Rust keeps a bounds check on every `prime[j]` and a checked
  `j += i`: 247 ms, 2,106M instructions and 1,209M cycles, against native's
  148 ms and 1,414M/626M; C is 158 ms with no checks.
- **Rust uses the system allocator.** `alloc` is 126 ms, the same as plain C
  (126 ms) and 1.8x native (70 ms): libc `malloc`/`free` against the
  freestanding size-class allocator. `lists` is 40 vs 31 ms (Rust's
  recursive `Drop` walks the 10,000-node list; C frees it iteratively) and
  `trees` 25 vs 20 ms.
- **Strings: `String` and `Rc<str>`.** Native is 45 ms and plain C 91 ms;
  Rust `String` is 79 ms. The `Rc<str>` version (`dbench strings-rc`, the
  closer analogue of obx's refcounted `str`) is 128 ms in an interleaved
  best-of-15 run, 1.6x the `String` version: a safe concatenation builds a
  `String` and then copies it into a fresh `Rc` allocation, two allocations
  per `+`, whereas obx makes one refcounted block per `+` in its size-class
  allocator.
- **maps** runs 878M cycles and 2,102M instructions. `str`, `i128`, `u128`
  and `Decimal` hash with SipHash-1-3 under a per-process key, and `Map`
  mixes a per-process seed into its slots (lib/README.md, "Keyed hashing").
  Map's index slots are `u32`: an entry number with the high bits of the
  mixed hash beside it, so a probe skips other keys' slots without loading
  their entries; a Map holds at most 2^31 entries. The probes wait on memory:
  what is left is the misses on the keys' strings and the entries.
- **Code placement.** The same instructions can take different cycles
  depending on where they fall relative to 32- and 64-byte boundaries. Native
  functions start at multiples of 64 and the native backend aligns loop
  heads; gcc gets `-falign-functions=64 -falign-loops=32`, in programs and in
  the native runtime. `python3 obx/tools/placement.py` builds a benchmark
  eight times with its code shifted by 0, 8, ..., 56 bytes (native:
  `OBX_PADB=n`) and reports the spread. Native fib, loop, array and alloc
  move by under 1%, trees and sieve by 2–4%; maps moves as much between runs
  of one binary on a loaded machine, which is memory, not placement.

## Regex

`python3 obx/bench/regex/bench.py -n 7` ([obx/bench/regex/](obx/bench/regex/bench.py)),
the benchmark set of [design/regex.md](obx/design/regex.md) section 4. The
corpus is 3.2 MB written by `gen_corpus.py` from a fixed seed (prose with the
names the patterns look for, a log, C-like source; ASCII). Each driver times
its own searches after reading the file: the best of 5 searches, best of 7
runs, in ms. "Matches" is the same for every driver (the script checks);
`(a*)*b` runs over 100,000 `a`s. Go is go1.26.4's `regexp`, Rust the `regex`
crate 1.12.3, and rg is ripgrep 14.1.1 counting matches as a whole process,
start-up and file reading included: a reference point, not a like-for-like
figure.

| pattern | matches | obx native | Go | Rust | rg |
|---|---:|---:|---:|---:|---:|
| `Sherlock Holmes` | 926 | 0.21 | 0.48 | 0.08 | 1.7 |
| `Sherlock\|Holmes\|Watson\|Irene` | 7,350 | 0.88 | 139.90 | 0.44 | 2.6 |
| `\w+` (all matches) | 669,532 | 34.41 | 169.42 | 17.77 | 43.6 |
| `(?i)sherlock` | 4,280 | 0.79 | 73.38 | 0.48 | 3.4 |
| `[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}` | 848 | 0.19 | 80.62 | 0.09 | 1.9 |
| `(?m)^ERROR .*timeout$` | 197 | 0.35 | 33.01 | 0.62 | 2.1 |
| `(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})` (captures) | 10,755 | 4.11 | 74.97 | 1.33 | 8.3 |
| `(a*)*b` over 100,000 `a`s | 0 | 0.00 | 3.42 | 0.00 | 1.4 |

The table is the plain `--native` build. With `--native -O`, `\w+` is
30.9 ms, the alternation 0.82, `(?i)` 0.74 and the captures 4.01. The
same-IR C build's column and the per-match instruction ratios are in
[design/native-vs-c.md](obx/design/native-vs-c.md).

- **obx and Rust.** The engine has RE2's lazy DFA and Rust's literal
  searches (design/regex.md, "R2 as built"). Obx takes 1.7 to 3.1 times
  Rust's time on the matching patterns and a little over half on the
  `ERROR` lines (a prefilter on `ERROR ` and the suffix check on `timeout`).
- **Where the gap is.** The literal: Rust's memchr uses AVX2 (32 bytes a
  step), the runtime SSE2 (16). `\w+` and the captures are per-match costs
  (670,000 and 10,755 matches): each match is a forward and a reverse DFA
  run plus, for captures, the backtracker on the span. The span path runs
  `forward` and `backward` in one loop, takes the DFA's text by borrow
  (no dup/drop per call), keys the start-state cache by the byte itself
  (there is no byte-to-context table load on the hot path), and scans ASCII
  in a fast loop whose constant step lets `loops.obx` prove the byte bounds
  check; `findAllIndexN` has a span-specialized driver that appends `Span`
  directly instead of calling a delivery callback with a two-slot `[]int`.
  Per-match overhead is **16 instructions**, and the `-O` `\w+` instruction
  count is level with the same work in the other builds. The byte loop takes
  two taken branches per byte; a one-branch-per-byte loop would run the same
  instructions about 13% faster.
- **`(a*)*b`** takes no time: the text has no `b`, and every match ends with
  one (the suffix check), so the search stops before any matcher runs. The
  DFA on such patterns is covered by the tests (`regex_linear`,
  `regex_dfa`), not by this row.
- **obx and Go.** obx is 2 to 700 times faster than Go's `regexp`, which has
  no DFA.
- **Go's matchers** (the Pike VM, the backtracker and one-pass), which the
  engine uses for short texts (under 128 bytes), for one-pass patterns, and
  when the DFA's cache fills too often, are slower than the DFA path: short
  loops over the fields of a `mut &` record's arrays, each access with its
  bounds check and each index sum with its overflow check.
- **Linear time.** The library test `regex_linear` checks that 100,000 bytes
  take about ten times as long as 10,000 for six such patterns under the
  Pike VM, the backtracker and the DFA (also in a tiny cache), among them
  `(a|b)*a(a|b){20}`, whose DFA has 2^21 states; `regex_dfa` does the same
  on random text, where the cache fills and the search falls back to the
  Pike VM.

## eza

[obx/cmd/eza.obx](obx/cmd/eza.obx), a 1,600-line implementation of the
common subset of eza 0.23.3 at `38e114e` (1,857 lines, with the full long
view). `LC_ALL=C TZ=UTC`; the long listings use
`--bytes --time-style=long-iso -n`, which that build required. Best of 9; both
builds write byte-identical listings.

| listing | output | native |
|---|---:|---:|
| `-T /usr/share` (tree) | 2.1 MB | 119 ms |
| `-T -l /usr/share` (long tree) | 3.7 MB | 234 ms |
| `-l /usr/lib/x86_64-linux-gnu` | 51 KB | 5 ms |

The golden suite (`python3 obx/cmd/eza_gate.py -j 12`) passes on both
builds.

## grep

[obx/cmd/grep.obx](obx/cmd/grep.obx) against GNU grep 3.11 on 100 MB of
generated text (1.8 million lines; the generator is in
[obx/cmd/README.md](obx/cmd/README.md)). Best of 5, output to a pipe,
`LC_ALL=C` (under `C.UTF-8` GNU grep's `-w` takes 2.3 times as long; the obx
port has no locale). Every output equals GNU grep's.

| search | GNU | native |
|---|---:|---:|
| `needle5007` (a literal) | 27 ms | 17 ms |
| `-c omega` | 89 ms | 64 ms |
| `-c '[0-9]*7 alpha'` | 73 ms | 18 ms |
| `-c -w eta` | 213 ms | 182 ms |
| `-c -v '^0'` (every line) | 49 ms | 51 ms |
| `-c -E 'a.*z.*e'` | 218 ms | 115 ms |
| `-n omega` | 237 ms | 211 ms |
| `-o -w eta` | 400 ms | 323 ms |

`-n omega` is the slowest row (2,191M instructions / 629M cycles); the cost
is the line-numbering and match walk, not the DFA. The rest are ahead of GNU
grep except `-c -v '^0'`.

What makes it fast:

- **Lines, not matches.** The regex library's `matchingLines` runs the lazy
  DFA over a chunk and reports the lines with a match. It starts again after
  each such line, with no call per line.
- **A required literal first.** `[0-9]*7 alpha` must contain `7 alpha`; a
  memory search finds it and only its line is checked.
- **`-w` as one regex.** The word with a non-word character or a line end on
  each side.
- **Output in pieces.** The prefix, the line and the newline go into a byte
  buffer; no string is built per line.

### On 1 GB

An earlier sweep (a 1 GB input and 21 cases); the 100 MB figures above scale
linearly.

The same generator run to 10^9 bytes (18.2 million lines), the cases above
and more pattern shapes. Best of 3, output piped to `md5sum`, the file in the
page cache, `LC_ALL=C`. ripgrep (14.1.1, one file; `-E` dropped, since rg's
regexes are extended already) is for reference; it has no `-x` and its `-f`
was not measured. On every case the native build printed exactly what GNU
grep printed, and so did ripgrep.

| search | GNU | ripgrep | native |
|---|---:|---:|---:|
| `needle5007` (a literal, one line) | 283 ms | 85 ms | 186 ms |
| `-c zzz` (no match) | 353 ms | 76 ms | 183 ms |
| `-c omega` | 873 ms | 390 ms | 614 ms |
| `-v -c omega` | 994 ms | 581 ms | 741 ms |
| `-c '[0-9]*7 alpha'` | 725 ms | 96 ms | 192 ms |
| `-c -E '(alpha\|beta) gamma'` | 1,096 ms | 411 ms | 645 ms |
| `-c -i NEEDLE` | 625 ms | 117 ms | 185 ms |
| `-c -i 'OMEGA BETA'` | 714 ms | 455 ms | 227 ms |
| `-c -w eta` | 2,081 ms | 1,689 ms | 1,901 ms |
| `-c -v '^0'` (every line) | 571 ms | 644 ms | 457 ms |
| `-c -E 'a.*z.*e'` | 2,112 ms | 1,702 ms | 1,055 ms |
| `-c -E 'needle(1\|2)[0-9]{3}7'` | 572 ms | 78 ms | 193 ms |
| `-c -E '^[0-9]+7[0-9]'` | 456 ms | 814 ms | 582 ms |
| `-c -E '(alpha\|omega) .*(beta\|psi)$'` | 2,554 ms | 941 ms | 1,233 ms |
| `-c -x '[0-9]* alpha beta gamma delta'` | 411 ms | — | 186 ms |
| `-c -F -f` five fixed strings | 1,295 ms | — | 1,664 ms |
| `-n omega` | 2,201 ms | 1,435 ms | 2,059 ms |
| `omega` (prints 8.8 million lines) | 1,623 ms | 927 ms | 1,557 ms |
| `-o 'needle[0-9]*'` | 605 ms | 103 ms | 196 ms |
| `-o -w eta` | 3,845 ms | 2,946 ms | 3,412 ms |
| `-n -w eta` | 3,885 ms | 3,269 ms | 3,327 ms |

The times scale with the file: each is about ten times its 100 MB figure, so
nothing in the obx port grows worse than linearly. The literal searches
(`needle`, `zzz`, `-o 'needle'`) read the 1 GB at memory speed, so they move
most with the machine's state, for every tool alike.

**Against GNU grep:** obx is ahead on 19 of 21 cases, often by 2 to 4 times.

**Still behind GNU:**
- `-F -f` with several fixed strings, 1.25 to 1.3 times slower. Each string
  becomes a branch of one regex, where GNU and ripgrep use a multi-string
  search (Aho-Corasick, Teddy).
- `^[0-9]+7[0-9]`, 1.2 to 1.3 times slower.

**Against ripgrep:** ripgrep is faster wherever a literal or a rare required
string can be found with SIMD (`needle`, `zzz`, `-x`, `-o`). obx is faster on
case-insensitive patterns (`-i 'OMEGA BETA'`), on `a.*z.*e` and
`^[0-9]+7[0-9]`, and when every line matches (`-v '^0'`). The two are close
on `-w`.

## jq

[obx/cmd/jq.obx](obx/cmd/jq.obx), the jq 1.7.1 port, against jq 1.7.1 built
from its release tarball (`./configure --with-oniguruma=builtin`, the default
`-O2`). Wall times; figures vary by 5–10% between runs. The wall times are
from an earlier quiet window (the host was too variable to re-baseline); the
instruction counts are current.

**Large input.** `python3 obx/bench/json/bench.py --jq JQ`, on an 80 MB file
of 182,290 generated records. Best of 3; the output goes to a file, and the
three outputs of each filter must be identical.

| filter | jq 1.7.1 | native |
|---|---:|---:|
| `.` | 2.50 s | 1.74 s |
| `-c .` | 2.24 s | 1.62 s |
| `length` | 1.59 s | 1.15 s |
| `[.[].items[].qty] \| add` | 1.90 s | 1.31 s |
| `map(select(.active and .score > 0) \| {id, city: .address.city})` | 1.75 s | 1.39 s |
| `group_by(.address.city) \| map({city: .[0].address.city, n: length})` | 2.15 s | 1.95 s |

The jq 1.7.1 column is from an earlier sweep (jq is not installed here); the
obx columns were measured at 80 MB with `--mb 80 -n 3`.

The same script times the JSON library on the file (ms, best of 3), against
Python's `json`:

| step | obx native | Python |
|---|---:|---:|
| parse | 771 | 846 |
| compact output | 542 | 818 |
| pretty output | 654 | 2,952 |
| query | 209 | 50 |
| visit | 200 | 50 |

**Computation.** Programs with no input (`jq -n`), best of 5 (`group_by`
best of 9); the outputs are identical. The table is from an earlier sweep
(it needs the jq reference).

| program | jq 1.7.1 | native |
|---|---:|---:|
| `1` (start-up) | 2 ms | 5 ms |
| `reduce range(3000000) as $i (0; . + $i)` | 503 ms | 540 ms |
| `[range(1000000)] \| map(. * 2) \| add` | 417 ms | 281 ms |
| `[range(200000) \| tostring] \| sort \| length` | 123 ms | 91 ms |
| `def fib: ...; 25 \| fib` (recursive, 250,000 calls) | 61 ms | 111 ms |
| `[limit(100000; repeat(1))] \| length` | 46 ms | 11 ms |
| `[range(100000) \| {a: ., b: "x\(.)"}] \| group_by(.a % 10) \| map(length)` | 251 ms | 285 ms |
| `[range(50000) \| tostring \| test("7$")] \| map(select(.)) \| length` | 74 ms | 79 ms |

**Where the port wins.** Wherever JSON is parsed or written: jq builds a
decNumber for every literal, and its writer goes through `jv_dump_term`; the
JSON library keeps the literal's text and writes it back. Also on simple
generators: `limit`, `range` and `map` are native in the port, and
continuation calls cost less than jq's bytecode with its fork points.
Compiled regexes are cached for the run.

**Where jq wins:**

- **Calls of jq-defined functions.** `fib` is 1.5–2× slower: each call pushes
  frames and closures, and runs its body through a capturing continuation.
- **Start-up.** The port parses and resolves `builtin.jq` on every run
  (2 ms).
- **Sorting objects by key.** `sort_by` and `group_by` on objects are a
  little slower: the comparison walks the counted boxes.
- **Queries over a parsed document**, in the library table: Python's dicts
  are faster to walk than the library's counted boxes.

The library's own design and numbers are in
[obx/design/json.md](obx/design/json.md), section 9.

## Markdown

[obx/cmd/cmark.obx](obx/cmd/cmark.obx) (the `markdown` library) against cmark
0.31.2 (`-O3` release build, cmake), rendering 10 MB documents with
`--unsafe` to a pipe. Best of 3, seconds (`python3 obx/tests/markdown.py
--perf --ref CMARK`). The wall times are from an earlier quiet window: the
host was too variable to re-baseline the pipe-bound times (the same binary
moved by 1.7x between runs). The instruction and cycle ratios below are
current.

| document | cmark | obx native |
|---|---:|---:|
| the spec, repeated to 10 MB | 0.18 | 0.20 |
| the repo's Markdown files, repeated to 10 MB | 0.22 | 0.25 |
| the spec's examples, repeated to 10 MB | 0.62 | 0.72 |

The obx columns are the plain `--native` build, with line endings and inline
text runs found in runs rather than byte by byte.
With `-O` the spec is 0.169 s: 1343.0M instructions / 487.3M cycles. The
cmark column is from an earlier sweep; the same-IR C ratios are in
[design/native-vs-c.md](obx/design/native-vs-c.md).

The obx renderer takes 1.1 to 1.2 times cmark's time in the plain build and
0.94 to 1.10 with `-O`. cmark's pathological
inputs (nested emphasis, brackets and block quotes 30,000 to 100,000 deep, a
million backticks, unclosed constructs) all finish in well under a second,
within a small factor of cmark; the one quadratic case (a run of blank lines
inside deeply nested lists) is cut by the same early exit as cmark's. The
parser keeps the tree in one array of 200-byte nodes: the 10 MB spec takes
114 MB of memory at its peak (cmark: 68 MB).

## The compiler

The obx compiler compiling itself (`obx/compiler/main.obx`), native build,
best of 11:

| | native build |
|---|---:|
| self-build to an executable (`--native`) | 733 ms |
| self-build to C (`--emit-c`) | 457 ms |
| compiler binary | 3,068,417 bytes (static, no libc) |

The compiler is 39,436 lines of obx (1.78 MB, 706 KB of it the generated
runtime tables `rt.obx` and `rtx.obx`; 28,348 hand-written lines) and 5,634
lines of C runtime (the C backend's `rt.h` and the native backend's
freestanding `rt.c`). The native-built compiler runs 5,009M instructions in
2,999M cycles on `--native`. Absolute times move with the host; the
instruction counts are the stable comparison. The gcc-built comparison is in
[design/native-vs-c.md](obx/design/native-vs-c.md).

- What is left is spread thin: it is in the mix (register-to-register moves,
  stores to the stack and compares: spills, and loads and bounds checks
  repeated from one statement to the next), not in a few functions. A
  compiler is call-heavy and branchy; the IR inliner closes much of the gap.
- Both backends start from one IR: `--native` does not print and re-read C,
  and `--emit-c` builds the IR before printing it.

### Judging a change

A backend pass is judged by `obx/tools/perfsuite.py`, not by the self-build
alone: each pass adds to the compiler's own sources, and the compiler is one
program.

    python3 obx/tools/perfsuite.py main BRANCH     # or two compiler paths

It builds both revisions' native compilers from their seeds, then measures
them on inputs frozen at one revision (`af99f933`; they move only on purpose,
with a note in HISTORY.md):

- **Compile suite:** the frozen compiler (`--native` and `--emit-c`) and the
  frozen eza, grep and zoxide, compiled by each compiler. This is the compile
  speed a user sees: the new analysis's cost minus what the compiler gains
  from being compiled better itself.
- **Run suite:** the frozen bench programs and grep, sort, wc and eza, built
  by each compiler and run on fixed inputs (a generated 100 MB text). Both
  builds must print the same output.

Each suite is summarised as the geometric mean of new/base. On two builds of
the same code, instructions are identical and cycles vary by up to ±3% on one
program and ±0.5% on the means, so instructions decide and cycles must agree
in sign. A pass is kept when:

- the run suite gains at least 1% (geometric mean), or 5% on at least two
  programs with none worse than 1%, and the compile suite costs at most 1%;
  or
- the compile suite gains and the run suite is not worse.

The compile suite's total cost over `af99f933` stays under 5%
(`perfsuite.py af99f933 main`). Because the inputs are frozen, a change to
the library (std's Map, say) shows in perfsuite only through the compiler,
not in the frozen programs; measure such changes with bench.py and `perf
stat` as well. The passes tried and shelved are in HISTORY.md.

These rules are for the **default** path. `--native -O` is the optimising
path: it may cost up to **30% more compile time** than the default
(`python3 obx/tools/optcost.py --compiler <native-built obxc>`, instructions
and cycles, best of N). Its target is a compiled program's running time, not
a smaller compile-suite figure.

### The optimization level (`-O`)

`--native` is the fast path. It runs `opt` (small-function inlining) and
nothing else. `--native -O` adds `loops` (array headers and str headers out
of loops, the bounds and overflow facts), perf17's range facts in loop-free
functions, and `cse` (loads and checked element addresses reused along a
straight run). The generated code differs only between `-O` and the default.

Compile cost of `-O` over the default (`optcost.py`, native-built compiler,
best of 3, one core):

| program | default Minstr | -O Minstr | -O/default | default Mcyc | -O Mcyc | -O/default |
|---|---:|---:|---:|---:|---:|---:|
| compiler | 5,009 | 6,181 | +23.4% | 2,852 | 3,708 | +30.0% |
| eza | 513 | 596 | +16.3% | 302 | 358 | +18.4% |
| grep | 1,225 | 1,449 | +18.3% | 635 | 791 | +24.6% |
| zoxide | 499 | 564 | +13.1% | 259 | 330 | +27.5% |
| jq | 2,595 | 3,031 | +16.8% | 1,313 | 1,521 | +15.9% |
| cmark | 609 | 692 | +13.6% | 298 | 316 | +6.1% |
| tokens | 82 | 88 | +7.4% | 37 | 39 | +4.7% |
| maps | 96 | 107 | +11.3% | 43 | 45 | +5.3% |
| **geomean** | | | **+14.9%** | | | **+16.1%** |

The code `-O` makes is judged by `obx/bench/bench.py --opt` (the ten
benchmarks, native `-O` against the hand-written C references) and by the
regex, JSON/jq, Markdown and Decimal harnesses. The ladder pays on loops,
allocation, strings, trees, sieve and Markdown; it does not move the DFA's
per-match work or jq's boxes. The `-O`/C cycle ratios are in
[design/native-vs-c.md](obx/design/native-vs-c.md). Check elimination and branch folding were
measured and rejected: the losses are memory, calls and copies, not
instruction selection. Those experiments are in HISTORY.md, "Tried and
shelved". The application rows below carry their external references; the
remaining gaps are regex's byte loop and cmark's parse instructions, and
Decimal is 1.2 times .NET on add and 1.5 on multiply.

`-O` is part of the quick gate: `run_native.py --lib --opt` builds the
library programs with `-O` and requires the same output, exit code and stderr
as the C build.

### The application suite

`python3 obx/bench/apps.py -n 5 --pin 2` is the Tier-1 table: the same source
built natively with `-O`, output checked, timed with `perf` on one core, best
of N, as a table, JSON and TSV. Measured at `fb50b4f1`
(`OBX_HASH_SEED=42`, core 2, 60 s):

| application | native wall | instructions | cycles |
|---|---:|---:|---:|
| regex (8 patterns, 3 MB) | 44 ms | 582.7M | 157.9M |
| json (20 MB, parse/query/visit) | 481 ms | 4,410.7M | 1,734.9M |
| jq (`-c .`, 20 MB) | 377 ms | 4,282.3M | 1,348.9M |
| cmark (10 MB) | 159 ms | 1,343.0M | 489.2M |
| decimal (all cases) | 2,211 ms | 45,076.7M | 9,672.8M |

The external references for each application are in its own section: Rust,
Go and ripgrep for regex; jq for the jq port; cmark for Markdown; .NET and
Java for Decimal. The same-IR C comparison is in
[design/native-vs-c.md](obx/design/native-vs-c.md). Wall times move by
several percent between runs; instructions are the stable figure.

The benchmark harnesses set `OBX_HASH_SEED` (42 by default, `--hash-seed` or
`--random-hash` to change it), so the map layout is identical across runs and
in both backends; without it production keeps the per-process random key.
The maps instruction count is reproducible across runs and seeds; its cycles
move with the machine and the slot layout.

## Binary sizes

| program | native |
|---|---:|
| empty program | 12,288 bytes (static) |
| hello | 16,416 bytes (static) |
| `import "regex"`, one call (`regex.quote`) | 20,512 bytes (static) |
| eza | 304,296 bytes (static) |
| HTTP server (`cmd/httpd.obx`) | 844,272 bytes (dynamic) |
| compiler | 3,068,417 bytes (static) |

The native backend generates only the functions and globals reachable from
`main` (design/native.md section 5, "Reachability"), as gcc drops a C
program's unused static functions: an imported module costs only what the
program uses of it. The runtime is linked
the same way, by sections, as `ld --gc-sections` would: every function and
datum of rt.c is a section of its own in `rtx.obx`, and the link keeps those
reachable from the runtime functions the program calls. Native functions
start at multiples of 64 bytes (code placement, above), which costs about 1%
of a large program's size.

A native executable carries its own runtime instead of linking libc. When a
program calls C libraries (libssl, sqlite3), it is dynamically linked against
them. A program that imports `postgres_libpq` is linked against libpq too; the
native `postgres` client needs no libpq (it still uses libssl for TLS).

## Math

The float math functions are the runtime's own (musl 1.2.5, one C text for
both backends, `obx/compiler/obxmath.inc`), not libm's. sqrt, floor, ceil,
trunc, round, rint, fabs, copysign and fma are single instructions (sqrtsd,
roundsd, masks, vfmadd213sd). The polynomials of exp, exp2, log, log2, pow,
sin and cos use explicit fma; everything else is compiled with
`-ffp-contract=off`, so a result's bits do not depend on the gcc version or
the backend. The native runtime compiles the text apart (`native/math.c`,
with `-ffixed-xmm8` to `-ffixed-xmm15`), so that a native program keeps its
doubles in `xmm8`-`xmm14` across the calls.

5M calls of one function in a loop, the argument varying
(`obx/bench/math/calls.obx`), ms, best of 7, pinned, both builds interleaved;
both print the same checksum. Cycles per call in brackets (user cycles, least
of 7, divided by 5M):

| function | native |
|---|---:|
| exp | 12 (9.6) |
| ln | 15 (12.9) |
| sin | 9 (7.0) |
| pow | 47 (41.7) |
| atan | 19 (15.9) |
| tan | 20 (16.9) |

What is left on exp and sin is the call: the native loop calls the kernel,
and the kernel loads its polynomial constants on every call (49 operations
an iteration). The loop is bound by dispatch, not by a latency chain
(`perf`: 85% of the dispatch slots used, the rest mostly back-end stalls).
The loop around the call is seven instructions: the argument moved from its
register, the call, `addsd` into the sum's register, `addsd` of a rodata
constant into the argument's, the count and the branch.

Mixing the native code's legacy SSE with the runtime's VEX code costs nothing
here. In a test loop, legacy SSE around a call of VEX code ran at the speed of
VEX everywhere (5.0 cycles an iteration). Only dirty upper halves of the
`ymm` registers slow it (7.2), and gcc's `vzeroupper` keeps them clean.
Explicit fma in more kernels (atan, tan, expm1) is the deterministic way to
get more of the speed that contraction would give.

## Decimal

`obx/bench/decimal`: micro-benchmarks of the Decimal operations
(`dbench.obx`, M0 to M10 on 4096 fixed-seed inputs each) and `run.py`, which
builds them with two trees and compares user cycles and instructions (`perf
stat`, least of N). `diff.py` is the differential test that every change to
Decimal must pass: 11 operations on 10^6 inputs each, old and new tree,
native and C, identical text, errors and scales.

A matched comparison with .NET's `System.Decimal` and Java's `BigDecimal` is
in [design/decimal-performance.md](obx/design/decimal-performance.md):
19-digit add, 6x6 multiply, 12/6 divide at scale 2, 20-digit parse,
19-digit format and compare, plus 38-digit cases that .NET cannot represent.
In short: .NET's 16-byte decimal is 1.2 times faster on add, 1.5 times on
multiply and 3 times on compare; obx is about twice as fast at parse and 1.6
times at format; Java is fast on small arithmetic but its parse is about
twice obx's and its 38-digit format 3 times. At 38 digits obx is ahead of
Java on add and multiply too.

Cycles per operation (dbench under `perf stat`, least of 5, pinned to one
core; measured 7 November 2026 at `fb50b4f1`):

| operation | native |
|---|---:|
| add, 6 / 19 digits at 2 places (M2) | 66 / 66 |
| mul, 6 / 19 digits (M3) | 80 / 83 |
| div, 12 by 6 digits at scale 2 (M5:s2) | 237 |
| quantize to 2 places from 6 digits (M6) | 73 |
| parse, 20 digits (M7) | 247 |
| format, 38 digits fixed (M8:f38) | 452 |
| cmp, same leading digit position (M10:diff) | 50 |
| `Decimal.fromUnits(u, 2)` and one add, a row of a 10M-row sum | 191 |

The last row is from an earlier sweep. The per-operation numbers are noisy
at this size; the aggregate application row below is the reliable one. The
same-IR C comparison is in [design/native-vs-c.md](obx/design/native-vs-c.md).

The expensive operations are parse, format and cmp. Parse carries the digit
loop's checks and its 128-bit accumulation through a pointer; format is
`rt_digits` plus an allocation and a copy per call; cmp spends half its
branch misses in `digits`' compare tree. The records still passed by value
on the stack cost the ABI's copies; the receiver pass removes one of them.
Parse is at the inlining ceiling (`digits` into `cmp`, `sumOf` into
`errSum`); the Stage-B ceiling is design/record-abi.md.

`add`/`mul` return the `Decimal` directly on their hot path, through
`makeDecCore` and a `mut &int` error flag; `addExact`/`mulExact` keep their
`Result` body and `sub` is `a.add(b.neg())`. Equal-exponent `add` skips both
`digits()` bound checks, and `makeDec` counts digits for the exponent check
only when the exponent is above `EXP_MAX` and runs the trailing-zero strip
only when `coef % 10 == 0`. The matched comparison
(`bench/decimal/compare`) puts add at 13.3 ns and 6x6 multiply at 17.1,
against .NET's 11.2 and 11.7; `addExact` is 12.8 and `mulExact` 16.8, and the
bare 128-bit operation is 1.2/1.3 ns. div is 45.9 ns. What is left against
.NET is the normalisation and the 32-byte copy (1.2 times on add, 1.5 on
multiply); compare is 3 times, in `digits` and its branches. Not normalising
at all is the remaining representation change.

The digit count is a compare tree, trailing zeros are stripped by exact
division, long division is Knuth's algorithm D in base 2^64, text is written
in 10^19 chunks two digits at a time, and parse reads eight digits at a time
(design/decimal-perf-research.md, section 8).

## Tasks

The cost of the concurrency primitives (`lib/task.obx`, `lib/net.obx`, SPEC
16), from `obx/bench/tasks.obx`, ns per operation, best of 3 runs:

| operation | native |
|---|---:|
| task switch (`task.yield`) | 7.7 |
| start a task (stack reused) | 21.3 |
| start plus a wait that parks (round trip) | 82.1 |
| the same inside `task.within` (a timer set and removed) | 93.9 |
| wait on a finished task | 12.9 |
| promise complete | 11.3 |
| `Shared.with` | 5.8 |
| a `task.sleep(1)` that fires, beyond a yield | 53.2 |
| a socket read that finds data (no park) | 742 |
| a one-byte round trip between two tasks over loopback TCP | 196,853 |
| a `blocking` extern call run inline (no other task could run) | 3.5 |
| the same through the pool, the process on one CPU | 6,465 |

The `sleep` row is one run and noisy (the overshoot is divided among 10,000
tasks). The unpinned helper-pool row is from an earlier sweep: 433–451 ns.

The task operations are far below a system call. The runtime reads the
clock through the vDSO, as libc does (design/native.md, section 2). The
round trip is this machine's loopback: a Python ping-pong over
loopback TCP takes about 190,000 ns with two blocking threads and 205,000 ns
with epoll on one thread. The switch is not tuned.

The blocking rows call C's `abs` through a `blocking` extern (SPEC 12).
Inline it is a plain extern call plus a test of the scheduler's state.
Through the pool, the task parks, a helper thread runs the call and the event
loop wakes the task: the helpers and the event loop each spin up to 50 µs
before they sleep, so a busy pool round trip needs no system call. When the
process may use only one CPU (`taskset -c 0`) the spinning is off and every
call costs an `eventfd` write and an `epoll_wait`. For scale: one
`sqlite3_step` over a cached table takes 30 ns, so SQLite's steps in a
program with other tasks cost 10 to 20 times more; a query that reads the
disk does not notice.

## HTTP server

`obx/cmd/httpd.obx` on the server library `obx/lib/httpserver.obx`
(design/http-server.md): a keep-alive HTTP/1.1 server on one thread, one task
per connection, with every limit and timeout of the design on, the hangup
cancellation armed around each handler, the request parsed strictly and the
reply built by the library. Measured by `python3 obx/cmd/http_gate.py
--servers native,go,node`: the server on CPU 0, the load client
`obx/cmd/httpload.obx` (native, one thread) on CPU 2, another core. 10,000
idle keep-alive connections are opened first and stay open during the load;
each load client sends `GET /` and waits for the reply, 5 s per row. Go
1.26's net/http (GOMAXPROCS=1) and Node 24's http serve the same reply, as
references. This machine's numbers move by 5 to 10% from one run to the next.

| | obx native | Go net/http | Node 24 |
|---|---:|---:|---:|
| RSS per idle connection | 15.0 KB | 19.8 KB | 9.5 KB |
| RSS with 10,000 idle connections | 150 MiB | 195 MiB | 139 MiB |
| 1 client: requests/s | 4,185 | 3,790 | 3,650 |
| 10 clients: requests/s | 35,839 | 34,800 | 32,900 |
| 100 clients: requests/s | 60,763 | 44,500 | 43,100 |
| 1 client: latency p50 / p99 | 230 / 403 µs | 254 / 410 µs | 260 / 452 µs |
| 10 clients: latency p50 / p99 | 272 / 415 µs | 268 / 503 µs | 289 / 524 µs |
| 100 clients: latency p50 / p99 | 1.63 / 2.40 ms | 2.10 / 6.36 ms | 2.07 / 4.95 ms |

The Go and Node columns are from an earlier sweep (their toolchains were not
re-run).

What a request costs the server beyond reading and writing the socket: the
router's lookup (the router is a `task.Frozen`, read by every connection's
task at once), the strict head parse (every field checked), a `poll` system
call when the hangup cancellation is armed (it checks for a half-close that
came with the request, which must not cancel it), the `Date` and
`X-Content-Type-Options` headers and the counters.

An idle connection's resident cost is two pages of its task's stack (8 KiB;
the stack is 256 KiB of address space), a 4 KiB read buffer, a 512-byte
output buffer, and the request and response records with their header lists,
kept for reuse. Under the gate's `OBX_CHECK=1`, `GET /shutdown` with the
10,000 connections open drains them all and ends the program in 0.5 to 0.6 s,
exit 0, no leak. One client is bound by this machine's loopback round trip;
with 100 clients the single-threaded load client may be the limit as much as
the server. The `ulimit -n` here is 1,048,576; the gate raises the soft
limit when it can and stops when it cannot.

### The HTTP client

`httpload --client` sends the same load through one `http.Client`
(`obx/lib/http.obx`: `get` and `text()` per request, `maxPerHost` equal to
the connections), against the native server on CPU 0, the loader on CPU 2,
5 s per row, the median of three alternating rounds (the native columns:
`http_gate.py --servers native --client --conns 1,100,1000`), beside
httpload's own loop (a fixed request, only Content-Length parsed). No idle
connections are held open here.

| connections | raw, native | client, native |
|---:|---:|---:|
| 1: requests/s | 4,360 | 4,030 |
| 100: requests/s | 68,800 | 57,653 |
| 1,000: requests/s | 57,200 | 44,022 |
| 1: latency p50 / p99 | 219 / 380 µs | 233 / 556 µs |
| 100: latency p50 / p99 | 1.43 / 2.59 ms | 1.72 / 2.46 ms |
| 1,000: latency p50 / p99 | 16.4 / 21.6 ms | 21.9 / 28.2 ms |

The raw columns are from an earlier sweep. The client does more work per
request than the raw loop: it builds a full request, parses every reply
header, works out the framing and goes through the pool. With the loader's
core full, that is 83% to 87% of the raw throughput from 100 connections on;
with one connection the loopback round trip is the limit and they are level.
At 1,000 connections the client is 77% of raw. The design's gate asked for
parity, so it is not met (design/http-client.md, section 8).

### With a Postgres pool

`python3 obx/cmd/http_gate.py --servers native --db 4,16`: the same server
and load, each request `GET /db`, which takes a connection from a
`postgres.Pool` of 4 or 16 connections, runs `SELECT $1::int8 + 1` with the
request's number, and returns the connection. PostgreSQL 16 on the same
machine, over its Unix socket. The queries go through the native client
(`postgres`, over `pgwire`, design/pgwire.md): each request's task parks on
the socket, and the server's one thread serves the 10,000 idle connections
and the load meanwhile.

Two complete gate runs (each cell: requests/s the best of the two, with the
latency of that same run), the one-minute load 1.92 and 2.11 at the start of
each. Each figure is one 5 s
run; the cells moved by 1% to 8% between runs:

| | native, pool 4 | native, pool 16 |
|---|---:|---:|
| 1 client: requests/s | 2,594 | 2,633 |
| 10 clients: requests/s | 20,818 | 20,310 |
| 100 clients: requests/s | 20,016 | 21,217 |
| 1 client: latency p50 / p99 | 368 / 665 µs | 362 / 693 µs |
| 10 clients: latency p50 / p99 | 469 / 739 µs | 483 / 746 µs |
| 100 clients: latency p50 / p99 | 4.88 / 6.37 ms | 4.63 / 6.14 ms |

The libpq comparison is in design/pgwire.md, section 27: the two clients
were within -5% to +8% of each other in every row, in both directions, and
the idle connections cost the same with both (about 15 KB each).

One client pays two round trips, the HTTP one and the server's to
PostgreSQL (about 100 µs). From 10 clients on, the server's one thread is the
limit: 1 / 20,700 requests/s is about 48 µs of it per request (the breakdown
was not measured for the native client). With 100 clients, most of them wait
in the pool's queue (first come, first served), which is where the 5 ms comes
from. After the load, `/shutdown` with the 10,000 idle connections open took
0.53 to 0.59 s, exit 0, no leak under `OBX_CHECK=1`, every pool connection
idle and nobody waiting. An idle connection cost 14.9 to 15.3 KB.

The native client does not wait in a thread for a running query: the task
parks on the socket, so a waiting query can be cancelled (a CancelRequest on
a second connection, design/pgwire.md section 13) when its task is, and its
cost is the one thread's, the same budget the HTTP side uses; more cores come
from processes (below). The libpq client had the same budget through
libpq's asynchronous API (`PQcancel`).

### With worker processes

`python3 obx/cmd/http_gate.py --workers 1,2,4,8 --db 4`: `httpd ADDR POOL
WORKERS`, n worker processes under `task.workers` sharing one listener made
before the fork, each with its own event loop and (for `/db`) its own pool of
4 PostgreSQL connections. No idle connections; 256 keep-alive load
connections spread over 8 load processes (`httpload -p 8`), 5 s per row,
`OBX_CHECK=1`. Pinning: the n workers on the first n of CPUs 0, 2, 4, 6, 1,
3, 5, 7 (1 to 4 workers each have a core of their own; 8 workers share four
cores with SMT), the load on CPUs 8-15 (the other four cores); the gate
stops if the two sets would share a core. PostgreSQL is not pinned.
Two complete gate runs with the native client (each cell: requests/s the best
of the two), the one-minute load 2.15 and 10.07 at the starts (the second run
overlapped the tail of another gate). Requests/s, one 5 s run each:

| workers | native `/` | native `/db` |
|---:|---:|---:|
| 1 | 56,215 | 19,275 |
| 2 | 95,292 | 31,919 |
| 4 | 122,990 | 47,674 |
| 8 | 124,333 | 60,852 |

Most cells moved by 2% to 6% from run to run; the 1-worker native `/` row
moved by 13% (49,102 then 56,215), which is why the table is the best of
two. The libpq comparison is in design/pgwire.md, section 27.

`/` scales 1.5 to 1.7 times at 2 workers and 2.0 to 2.1 at 4, then stops
(2.05 to 2.12 at 8): the ceiling is the machine's, the loopback TCP of both
sides and the WSL2 virtual machine's cross-CPU wake-ups, not the workers.
`/db` keeps scaling to 8 workers (3.3 to 3.6 times): each request is mostly
waiting for PostgreSQL, whose backends run on whatever CPUs are free, and 8
workers keep 32 queries in flight. A listener of its own in each worker
(`httpd ... WORKERS reuseport`, `SO_REUSEPORT`) is the other mode; the shared
listener is the default because connections waiting in a killed worker's own
accept queue are reset with its socket. Only the shared listener is
measured here; the reuseport mode is unchanged.

The kill test (4 workers, `/`, the load reconnecting after an error): a third
of the way in, `SIGKILL` to one worker. It passed in every run. The runs lost
46, 48, 100 and 100 requests,
the ones in flight on the killed worker's connections. The
supervisor started the worker again after 105 to 108 ms (the 100 ms backoff;
a crash after the worker is ready never counts toward giving up), it
accepted from the same queue, and every worker drained at `/shutdown` with
exit 0, the restart counted.

## TLS

`obx/lib/tls.obx` over OpenSSL 3.0.13 (design/tls.md), and https in the http
client. Measured by `python3 obx/cmd/tls_bench.py`:

- `obx/cmd/tlsbench.obx`, built natively, against OpenSSL's own clients and
  curl; the server on CPU 0 and the client on CPU 2;
- a P-256 ECDSA certificate from a test CA, verified by every client; TLS
  1.3, TLS_AES_256_GCM_SHA384, X25519; each row the median of three runs.
- **Handshakes:** full handshakes one after another (connect, handshake,
  close_notify, no resumption) against `openssl s_server -www`.
- **Bulk:** one GET of 1 GiB from `tlsbench serve` (an https server written
  with `tls`, native), its body streamed in 64 KiB reads.
- **Requests:** 20,000 small GETs over kept-alive connections to the same
  server (5,000 for curl, one URL list).

| | obx native | OpenSSL / curl |
|---|---:|---:|
| handshakes/s (s_server is the limit) | 752 | 560 (`openssl s_time -new`) |
| client CPU per handshake | 527 µs | 595 µs (`s_time`) |
| GET 1 GiB: MB/s | 1,961 | 2,021 (curl) |
| GET 1 GiB: client CPU | 0.47 s | 0.44 s (curl) |
| requests/s, 1 connection | 3,887 | 2,986 (curl) |
| requests/s, 10 connections | 29,399 | |

**Handshakes.** A handshake's client side costs what OpenSSL's own client
costs. Most of the 0.5 ms is in OpenSSL 3.0: the per-connection `SSL` setup
(provider lookups), verifying the ECDSA chain and the X25519 exchange. The
engine's memory BIOs and the parking add nothing measurable. The rate is
bound by s_server, which handshakes one connection at a time.

**Bulk.** Bulk throughput is decryption: AES-GCM with AES-NI, under 0.5 s of
client CPU for 1 GiB, the same as curl's. The bulk row moves by up to a third
between runs on this machine.

**Requests.** The one-connection row is the loopback round trip, and it moves
by 15 to 25% from run to run. For scale, plain http to `httpd` reaches about
4,300 per second on one connection (above). These runs are also the H2
gate's "1,000 https requests over kept-alive connections"
(design/http-client.md), under no `OBX_CHECK`; the tests run under
`OBX_CHECK=1` with no leak.

## Database streaming

`conn.stream(sql, args, bind, read)` in the SQL Server, PostgreSQL and
Oracle clients decodes each row straight into the program's own record,
a caller-owned buffer at a time, instead of holding the whole result in
memory ([design/db-streaming.md](obx/design/db-streaming.md): the API,
the column matching, each client's mechanism and early close). Measured
by `python3 obx/bench/dbstream/run.py`: one run of all four clients, pinned
to CPU 10, with the one-minute load
average 0.84 at the start: 1,000,000 rows of (bigint, int, text,
decimal(12,2)), every
value decoded into a record and folded into a checksum, which is equal in
every row of the table; a buffer of 1,024 rows; peak RSS of the process;
each figure the least of 5 interleaved runs. The servers run on the same machine,
unpinned; Oracle runs in a rootless podman container,
whose networking adds about 0.38 ms a round trip. `PostgreSQL` is the native
client; `PostgreSQL (libpq)` is `postgres_libpq`, the old client, kept as
the comparison.

| client | streamed | buffered | streamed, 100,000 rows |
|---|---|---:|---:|
| SQL Server | 417 ms, 12.0 MB | 1,068 ms, 365.8 MB | 107 ms, 12.1 MB |
| PostgreSQL | 388 ms, 9.4 MB | 763 ms, 91.0 MB | 43 ms, 9.2 MB |
| PostgreSQL (libpq) | 543 ms, 8.8 MB | 845 ms, 109.8 MB | 61 ms, 8.8 MB |
| Oracle | 473 ms, 13.6 MB | 630 ms, 111.6 MB | 84 ms, 13.6 MB |

- **Memory is flat while streaming:** the same at 100,000 and 1,000,000
  rows (8.2 to 14.0 MB: the program, its buffer and, for Oracle, a fetch of
  about 10,000 rows). Buffered memory grows with the result: 91 MB for
  PostgreSQL's native client (its whole result), 109 to 110 MB for
  PostgreSQL through libpq (libpq's whole result), 111 MB for Oracle (each
  value's bytes, decoded when read) and 365 MB for SQL Server (a decoded
  cell per value).
- **Streaming is never slower:** 2.6 to 2.7 times faster for SQL Server,
  2.0 times for PostgreSQL's native client (1.6 for libpq) and 1.3 to 1.5
  times for Oracle.
- **How each client streams:** SQL Server decodes the reply a packet at a
  time. The native PostgreSQL client sends one Execute with no row limit and
  reads the rows off the socket as the buffer needs them, at most 256 KB a
  batch (design/pgwire.md, section 12): the server sends the whole result,
  and TCP holds it back while the program reads slowly. The libpq client
  uses libpq's single-row mode, batched into the buffer. Oracle fetches
  about 256 KB a round trip (at the widest row for the first FETCH, then at
  the size the rows took: about 9,900 rows here) and sends the next FETCH
  before the program uses the last rows.
- **Latency:** with a 2.5 ms one-way delay (6.1 to 6.2 ms round trip through
  the proxy), native streams 1M rows in 458 ms against libpq's 633; at 0 ms
  they are 415 and 598 ms (design/pgwire.md, section 28).
- **Client cost per row:** cycles per row (earlier sweep, native,
  streamed / buffered): Oracle 1,169 / 1,010 and SQL Server 1,290 / 2,515.
  Oracle's wall time is mostly the server's work and about 100 round trips. The breakdown (client
  CPU, server, network) and the slow-network runs are in
  design/db-streaming.md, section 7.

## Reproducing

```sh
obx/compiler/build.sh                                  # out/obxc from the seed
python3 obx/bench/bench.py --opt --perf -n 11          # the microbenchmarks (C and native -O)
python3 obx/bench/apps.py -n 5 --pin 2                 # the Tier-1 application suite
python3 obx/bench/regex/bench.py -n 7                  # the regex table (Go, Rust and rg built by it)
python3 obx/bench/json/bench.py --jq JQ                # the JSON library and jq large-input tables
python3 obx/tests/markdown.py --perf --ref CMARK       # the Markdown table
python3 obx/cmd/eza_gate.py -j 12                      # eza correctness on both builds
obx/compiler/out/obxc obx/cmd/eza.obx --native -o eza
obx/tools/native_selfbuild.sh                          # the natively built compiler
obx/compiler/out/obxc obx/bench/tasks.obx --native -o tasks && ./tasks
obx/compiler/out/obxc obx/bench/math/calls.obx --native -o calls && ./calls exp
python3 obx/bench/decimal/run.py --base DIR            # Decimal, two trees compared
python3 obx/tools/placement.py                         # code placement spreads
python3 obx/cmd/http_gate.py                           # the server table (about 2 minutes)
python3 obx/cmd/http_gate.py --servers native --client --conns 1,100,1000   # the client table
python3 obx/cmd/http_gate.py --servers native --db 4,16   # with Postgres ($OBX_PG_DSN)
python3 obx/cmd/http_gate.py --workers 1,2,4,8 --db 4  # worker processes (about 3 minutes)
python3 obx/tests/httpsrvgen.py -n 100000              # the server's parsing against Go and llhttp
python3 obx/cmd/tls_bench.py                           # TLS handshakes, bulk and https requests (about 2 minutes)
python3 obx/bench/dbstream/run.py                      # database streaming against buffered (the servers' DSNs; a quiet machine)
python3 obx/bench/dbstream/run.py --latency 0,0.12,1.75  # Oracle over ~1 ms and ~5 ms round trips (delayproxy.py)
```
