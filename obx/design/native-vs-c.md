# Native against the C backend

Status: measured 2026-11-07 at `fb50b4f1` (application suite and Decimal) and
`b6777cf4` (the rest), on the WSL2 Ryzen 7 8745HS. This document is the
internal code-generator comparison. The external comparisons — hand-written
C, Rust, Go, jq, cmark, .NET and Java — stay in [PERFORMANCE.md](../../PERFORMANCE.md)
and the harness notes it links.

## Why this document exists

obx has two backends built from one IR:

- **native**: `obxc --native`, the compiler's own x86-64 code generator.
- **C**: `obxc`, which prints C and runs gcc with
  `-O2 -march=x86-64-v3 -mmove-max=128 -mstore-max=128 -ffp-contract=off
  -falign-functions=64 -falign-loops=32`.

The C backend stays for three jobs that are not performance:

1. **Bootstrap.** The checked-in seed (`obx/compiler/seed/obxc.c`) is the
   C backend's output; a first build needs only gcc.
2. **Differential oracle.** Both backends must produce identical output on
   every test. The C build has caught native code-generation bugs that no
   native-only test did.
3. **Portability and sanitizers.** The C build is the path that can be
   compiled with other compilers and instrumentation.

It is not the external performance target. A native/C ratio answers "did the
native code generator regress against the same IR?", not "is obx fast?".
This document keeps that internal comparison in one place and current.

## Method

The same source is built both ways. Native is `--native -O` for the
application and microbenchmark tables (the default `--native` is noted where
used). C is the same IR through gcc with the flags above. Timings are wall
clock, best of N, warm cache, output to `/dev/null` or a pipe; instruction
and cycle counts are `perf stat`, user mode, least of N, pinned to one core.
The ratios come from interleaved same-run builds. Absolute times move by
5-10% between runs, and the memory-bound rows by more; instruction counts
are the stable figure.

## Microbenchmarks

`python3 obx/bench/bench.py --opt --perf -n 11`, best of 11, one core:

| benchmark | via C | native -O | -O/C | what it does |
|---|---:|---:|---:|---|
| fib | 349 ms | 346 ms | 0.99 | recursive calls |
| loop | 286 ms | 228 ms | 0.80 | two overflow-checked operations per iteration |
| array | 112 ms | 100 ms | 0.90 | checked indexing |
| alloc | 132 ms | 66 ms | 0.50 | 20 million records allocated and freed |
| lists | 40 ms | 33 ms | 0.82 | linked list build, sum, drop |
| strings | 85 ms | 46 ms | 0.54 | concatenation and `toStr` |
| trees | 27 ms | 21 ms | 0.78 | binary trees |
| tokens | 22 ms | 13 ms | 0.61 | byte scanning and hashing |
| sieve | 203 ms | 141 ms | 0.70 | the sieve of Eratosthenes to 10 million, ten rounds |
| maps | 254 ms | 243 ms | 0.96 | `Map[str, int]` with short and long keys, `Map[int, int]` (keyed hashing) |

The plain fast-compile path (`--native`, no `-O`) is slower where the loop
passes matter: loop 446 ms, array 183 ms, sieve 187 ms; it is 0.50 on alloc
and 0.54 on strings either way.

Native `-O` over the C backend, cycles (best of 11):

| | fib | loop | array | alloc | lists | strings | trees | tokens | sieve | maps |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `-O`/C | 1.00 | 0.80 | 0.88 | 0.50 | 0.79 | 0.53 | 0.74 | 0.60 | 0.70 | 0.97 |

## The optimization level

Compile cost of `-O` over the default is reported in PERFORMANCE.md; it is
not a C-backend comparison. What `-O` buys against the C build is the table
above. The `-O` code is level with or ahead of C on every benchmark.

## Application suite

`python3 obx/bench/apps.py -n 5 --pin 2`, native `-O` against the C build,
identical output required, `OBX_HASH_SEED=42`, core 2:

| application | native | C | native/C (wall) | instructions native/C | cycles native/C |
|---|---:|---:|---:|---:|---:|
| regex (8 patterns, 3 MB) | 44 ms | 40 ms | 1.10 | 1.03 | 1.13 |
| json (20 MB, parse/query/visit) | 481 ms | 488 ms | 0.99 | 1.14 | 0.99 |
| jq (`-c .`, 20 MB) | 377 ms | 393 ms | 0.96 | 1.13 | 0.93 |
| cmark (10 MB) | 159 ms | 159 ms | 1.00 | 1.27 | 1.08 |
| decimal (all cases) | 2,211 ms | 2,393 ms | **0.92** | 1.18 | **0.93** |

Regex is the one application where native is behind on wall time. Its
instruction count is level on `\w+` alone (1.03 for the row) and its 1.13
cycle ratio is the byte loop: native takes two taken branches per byte where
gcc takes one, so the same instructions run about 13% slower. cmark is level
in wall time but 1.27 in instructions because its parse builds node text
literally where gcc does less; the cycles follow. JSON is 1.14 in
instructions but slightly ahead in time, and jq is ahead on both. Decimal is
ahead on both.

## Compiler self-build

`obx/compiler/main.obx`, built each way, best of 11, interleaved:

| | gcc-built | native-built |
|---|---:|---:|
| self-build to an executable (`--native`) | 671 ms | 733 ms |
| self-build to C (`--emit-c`) | 476 ms | 457 ms |
| full build through gcc (`build.sh`, from the seed) | 22 s, nearly all of it gcc | — |
| compiler binary | 2,881,448 bytes (dynamic, glibc) | 3,068,417 bytes (static, no libc) |

The native-built compiler is about 1.09 times slower on `--native` and
slightly faster on `--emit-c`. The gcc-built `--native` self-build runs
4,342M instructions in 2,880M cycles; the native-built one 5,009M (1.15
times) in 2,999M (1.04 times). The compiler is the largest program where
the native code generator is behind, and it is call-heavy and branchy,
which is gcc's strength. The remaining code-shape levers are in
[design/codegen-audit.md](codegen-audit.md).

## Tools

### Regex

The full regex table (Go, Rust and ripgrep references) is in PERFORMANCE.md.
The C-backend column, plain `--native` and `--native -O`:

| pattern | native | native -O | via C |
|---|---:|---:|---:|
| `Sherlock Holmes` | 0.21 | — | 0.25 |
| alternation | 0.88 | 0.82 | 0.71 |
| `\w+` (all matches) | 34.41 | 30.9 | 23.39 |
| `(?i)sherlock` | 0.79 | 0.74 | 0.65 |
| email | 0.19 | — | 0.12 |
| `ERROR` lines | 0.35 | — | 0.42 |
| captures | 4.11 | 4.01 | 3.18 |

With `-O`, `\w+` is 30.9 ms against 23.6 via C: 1.31 wall, instructions
level at 1.00 (4,323M against 4,321M over ten searches), cycles 1.13. The
whole row is 1.03 instructions and 1.13 cycles. The per-match overhead is
16 instructions; the remaining gap is the byte loop's two taken branches
per byte.

### eza

`LC_ALL=C TZ=UTC`, best of 9; both builds write byte-identical listings:

| listing | output | via C | native |
|---|---:|---:|---:|
| `-T /usr/share` (tree) | 2.1 MB | 116 ms | 119 ms |
| `-T -l /usr/share` (long tree) | 3.7 MB | 226 ms | 234 ms |
| `-l /usr/lib/x86_64-linux-gnu` | 51 KB | 5 ms | 5 ms |

### grep

100 MB of generated text, best of 5, output to a pipe, `LC_ALL=C`:

| search | native | via C |
|---|---:|---:|
| `needle5007` (a literal) | 17 ms | 17 ms |
| `-c omega` | 64 ms | 60 ms |
| `-c '[0-9]*7 alpha'` | 18 ms | 18 ms |
| `-c -w eta` | 182 ms | 168 ms |
| `-c -v '^0'` (every line) | 51 ms | 46 ms |
| `-c -E 'a.*z.*e'` | 115 ms | 93 ms |
| `-n omega` | 211 ms | 173 ms |
| `-o -w eta` | 323 ms | 284 ms |

`-n omega` is the one clear loss: 2,191M instructions / 629M cycles natively
against 1,830M / 509M, 1.24 times the cycles, in the line-numbering and
match walk rather than the DFA. The rest are at or within a few percent of
C.

A 1 GB run (21 cases, earlier sweep) is in PERFORMANCE.md with the GNU and
ripgrep columns; native and C are within a few percent on every case.

### jq

80 MB input, best of 3, outputs identical:

| filter | native | via C |
|---|---:|---:|
| `.` | 1.74 s | 1.75 s |
| `-c .` | 1.62 s | 1.67 s |
| `length` | 1.15 s | 1.07 s |
| `[.[].items[].qty] \| add` | 1.31 s | 1.21 s |
| `map(select(...))` | 1.39 s | 1.46 s |
| `group_by(.address.city) \| ...` | 1.95 s | 1.79 s |

The JSON library on the same file (ms, best of 3):

| step | native | via C |
|---|---:|---:|
| parse | 771 | 607 |
| compact output | 542 | 286 |
| pretty output | 654 | 439 |
| query | 209 | 109 |
| visit | 200 | 99 |

Programs with no input (`jq -n`), best of 5 (`group_by` best of 9):

| program | native | via C |
|---|---:|---:|
| `1` (start-up) | 5 ms | 3 ms |
| `reduce range(3000000) as $i (0; . + $i)` | 540 ms | 364 ms |
| `[range(1000000)] \| map(. * 2) \| add` | 281 ms | 236 ms |
| `[range(200000) \| tostring] \| sort \| length` | 91 ms | 67 ms |
| `def fib: ...; 25 \| fib` | 111 ms | 94 ms |
| `[limit(100000; repeat(1))] \| length` | 11 ms | 11 ms |
| `group_by(.a % 10)` | 285 ms | 252 ms |
| `test("7$")` | 79 ms | 61 ms |

The large-input rows are mostly writer-bound and close; the computation
rows are where C's inlining and the native runtime's allocation differ.

### Markdown

10 MB documents, `--unsafe` to a pipe, best of 3, seconds:

| document | native | via C |
|---|---:|---:|
| the spec | 0.20 | 0.18 |
| the repo's Markdown files | 0.25 | 0.22 |
| the spec's examples | 0.72 | 0.59 |

With `-O` the spec is 0.169 s against 0.163: 1343.0M instructions / 487.3M
cycles against 1055.7M / 459.4M, so native is 1.27 instructions and 1.06
cycles of its own C build, with the parse at 1.38 and the render at 1.06.

## Decimal

`dbench.obx` under `perf stat`, least of 5, one core, cycles per operation:

| operation | native | via C |
|---|---:|---:|
| add, 6 / 19 digits at 2 places (M2) | 66 / 66 | 73 / 73 |
| mul, 6 / 19 digits (M3) | 80 / 83 | 130 / 131 |
| div, 12 by 6 digits at scale 2 (M5:s2) | 237 | 257 |
| quantize to 2 places from 6 digits (M6) | 73 | 76 |
| parse, 20 digits (M7) | 247 | 180 |
| format, 38 digits fixed (M8:f38) | 452 | 357 |
| cmp, same leading digit position (M10:diff) | 50 | 39 |
| `Decimal.fromUnits(u, 2)` and one add, a 10M-row sum | 191 | 199 |

Native is level or ahead on the arithmetic (add 0.90, mul 0.62-0.63, div
0.92, quantize 0.96) and behind on parse (1.37), format (1.27) and cmp
(1.28). Parse carries the digit loop's checks and its 128-bit accumulation
through a pointer; format is `rt_digits` plus an allocation and a copy per
call; cmp spends half its branch misses in `digits`' compare tree. The
application row is 0.92-0.93 wall / 0.93 cycles.

The C build's `-mmove-max=128 -mstore-max=128` exist for Decimal. At
x86-64-v3 gcc otherwise copies a 32-byte value passed by value with one
32-byte load straight after the 8- and 16-byte stores that wrote it; store
forwarding cannot serve that load, and every such call stalls (C Decimal add
1.4 times the cycles of the same build without AVX). A 16-byte load straight
after a callee's two 8-byte stores (a returned Decimal) still stalls; passing
such values by pointer in the generated C would remove it.

## Tasks

`obx/bench/tasks.obx`, ns per operation, best of 3:

| operation | via C | native |
|---|---:|---:|
| task switch (`task.yield`) | 7.4 | 7.7 |
| start a task (stack reused) | 41.9 | 21.3 |
| start plus a wait that parks (round trip) | 111.6 | 82.1 |
| the same inside `task.within` | 126.2 | 93.9 |
| wait on a finished task | 28.7 | 12.9 |
| promise complete | 11.8 | 11.3 |
| `Shared.with` | 3.5 | 5.8 |
| a `task.sleep(1)` that fires, beyond a yield | 21.7 | 53.2 |
| a socket read that finds data (no park) | 767 | 742 |
| a one-byte round trip between two tasks over loopback TCP | 197,553 | 196,853 |
| a `blocking` extern call run inline | 3.0 | 3.5 |
| the same through the pool, the process on one CPU | 8,323 | 6,465 |

The native switch is slower than C's because it goes through more of the
generic task code; it has not been tuned. The `sleep` row is one run and
noisy (the overshoot is divided among 10,000 tasks). The unpinned
helper-pool row is from an earlier sweep: 271-304 ns (C) and 433-451 ns
(native).

## HTTP server

`python3 obx/cmd/http_gate.py --servers native,c,go,node`; server on CPU 0,
load client `httpload` (native, one thread) on CPU 2; 10,000 idle keep-alive
connections open during the load; 5 s per row.

| | obx native | obx via C |
|---|---:|---:|
| RSS per idle connection | 15.0 KB | 14.5 KB |
| RSS with 10,000 idle connections | 150 MiB | 145 MiB |
| 1 client: requests/s | 4,185 | 4,151 |
| 10 clients: requests/s | 35,839 | 35,723 |
| 100 clients: requests/s | 60,763 | 62,168 |
| 1 client: latency p50 / p99 | 230 / 403 µs | 228 / 511 µs |
| 10 clients: latency p50 / p99 | 272 / 415 µs | 271 / 418 µs |
| 100 clients: latency p50 / p99 | 1.63 / 2.40 ms | 1.58 / 2.42 ms |

The two builds are within noise at one and ten clients; C is about 2%
ahead at 100. The Go and Node references are in PERFORMANCE.md.

### The HTTP client

`httpload --client`, native columns, median of three alternating rounds:

| connections | raw, native | client, native | raw, via C | client, via C |
|---:|---:|---:|---:|---:|
| 1: requests/s | 4,360 | 4,030 | 4,440 | 3,891 |
| 100: requests/s | 68,800 | 57,653 | 68,700 | 55,259 |
| 1,000: requests/s | 57,200 | 44,022 | 54,000 | 46,659 |
| 1: latency p50 / p99 | 219 / 380 µs | 233 / 556 µs | 214 / 383 µs | 244 / 554 µs |
| 100: latency p50 / p99 | 1.43 / 2.59 ms | 1.72 / 2.46 ms | 1.41 / 2.53 ms | 1.79 / 2.68 ms |
| 1,000: latency p50 / p99 | 16.4 / 21.6 ms | 21.9 / 28.2 ms | 17.5 / 25.0 ms | 20.3 / 29.1 ms |

At 1,000 connections the native client is about 6% behind the C build
(44,022 against 46,659), the one HTTP row where C leads. The client does
more work per request than the raw loop: a full request, every reply
header, the framing and the pool. With the loader's core full that is 83%
to 87% of the raw throughput from 100 connections on; with one connection
the loopback round trip is the limit and they are level.

### With a Postgres pool

`http_gate.py --servers native,c --db 4,16`, two complete gate runs (each
cell the best of the two), PostgreSQL 16 on the same machine:

| | native, pool 4 | via C, pool 4 | native, pool 16 | via C, pool 16 |
|---|---:|---:|---:|---:|
| 1 client: requests/s | 2,594 | 2,620 | 2,633 | 2,656 |
| 10 clients: requests/s | 20,818 | 21,310 | 20,310 | 20,080 |
| 100 clients: requests/s | 20,016 | 20,448 | 21,217 | 21,785 |
| 1 client: latency p50 / p99 | 368 / 665 µs | 367 / 634 µs | 362 / 693 µs | 354 / 700 µs |
| 10 clients: latency p50 / p99 | 469 / 739 µs | 457 / 710 µs | 483 / 746 µs | 484 / 799 µs |
| 100 clients: latency p50 / p99 | 4.88 / 6.37 ms | 4.80 / 5.89 ms | 4.63 / 6.14 ms | 4.51 / 6.02 ms |

### With worker processes

`http_gate.py --workers 1,2,4,8 --db 4`, two complete gate runs, native
client, requests/s:

| workers | native `/` | via C `/` | native `/db` | via C `/db` |
|---:|---:|---:|---:|---:|
| 1 | 56,215 | 60,894 | 19,275 | 18,921 |
| 2 | 95,292 | 98,047 | 31,919 | 32,495 |
| 4 | 122,990 | 124,723 | 47,674 | 48,070 |
| 8 | 124,333 | 125,134 | 60,852 | 62,347 |

The native `/` row is 1% to 8% behind C at 2 to 8 workers; `/db` is within
noise. Most cells move by 2% to 6% between runs.

## TLS

`python3 obx/cmd/tls_bench.py`, median of three runs, OpenSSL 3.0.13:

| | obx native | obx via C | OpenSSL / curl |
|---|---:|---:|---:|
| handshakes/s (s_server is the limit) | 752 | 752 | 560 (`openssl s_time -new`) |
| client CPU per handshake | 527 µs | 529 µs | 595 µs (`s_time`) |
| GET 1 GiB: MB/s | 1,961 | 1,945 | 2,021 (curl) |
| GET 1 GiB: client CPU | 0.47 s | 0.45 s | 0.44 s (curl) |
| requests/s, 1 connection | 3,887 | 3,931 | 2,986 (curl) |
| requests/s, 10 connections | 29,399 | 29,466 | |

Native and C are within noise; most of the cost is in OpenSSL itself.

## Database streaming

`python3 obx/bench/dbstream/run.py`, 1,000,000 rows of (bigint, int, text,
decimal(12,2)), buffer of 1,024 rows, peak RSS, least of 5 interleaved runs:

| client | backend | streamed | buffered | streamed, 100,000 rows |
|---|---|---:|---:|---:|
| SQL Server | via C | 479 ms, 11.5 MB | 1,279 ms, 364.9 MB | 114 ms, 11.5 MB |
| SQL Server | native | 417 ms, 12.0 MB | 1,068 ms, 365.8 MB | 107 ms, 12.1 MB |
| PostgreSQL | via C | 453 ms, 8.3 MB | 901 ms, 88.7 MB | 51 ms, 8.2 MB |
| PostgreSQL | native | 388 ms, 9.4 MB | 763 ms, 91.0 MB | 43 ms, 9.2 MB |
| PostgreSQL (libpq) | via C | 646 ms, 8.3 MB | 881 ms, 109.3 MB | 73 ms, 8.3 MB |
| PostgreSQL (libpq) | native | 543 ms, 8.8 MB | 845 ms, 109.8 MB | 61 ms, 8.8 MB |
| Oracle | via C | 451 ms, 14.0 MB | 671 ms, 110.9 MB | 84 ms, 13.7 MB |
| Oracle | native | 473 ms, 13.6 MB | 630 ms, 111.6 MB | 84 ms, 13.6 MB |

Native is 8% to 13% faster on SQL Server and PostgreSQL streaming and
within noise for Oracle. Streaming is 1.3 to 2.7 times faster than buffering
and keeps memory flat.

## Binary sizes

| program | via C | native |
|---|---:|---:|
| empty program | 63,192 bytes (dynamic, glibc) | 12,288 bytes (static) |
| hello | 63,352 bytes | 16,416 bytes (static) |
| `import "regex"`, one call | 63,544 bytes | 20,512 bytes (static) |
| eza | 284,320 bytes (dynamic, glibc) | 304,296 bytes (static) |
| HTTP server | 638,320 bytes | 844,272 bytes (dynamic) |
| compiler | 2,922,408 bytes (dynamic, glibc) | 3,068,417 bytes (static) |

## Math

5M calls of one function in a loop, ms, best of 7, cycles per call in
brackets:

| function | via C | native |
|---|---:|---:|
| exp | 10 (8.1) | 12 (9.6) |
| ln | 14 (11.6) | 15 (12.9) |
| sin | 8 (6.1) | 9 (7.0) |
| pow | 47 (40.5) | 47 (41.7) |
| atan | 19 (16.5) | 19 (15.9) |
| tan | 22 (18.6) | 20 (16.9) |

The native loop calls the kernel; gcc inlines it into the loop and keeps
its polynomial constants in registers (exp: 36 operations an iteration
against native's 49). The native loop is bound by dispatch, not by a
latency chain.

## What it says

- Native is at or ahead on all ten microbenchmarks in wall time (0.50 to
  0.99 of C) and at or ahead on all ten in `-O` cycles (0.50 to 1.00).
- It is at or ahead on four of the five application rows; regex is 1.10
  wall, and its instructions are level. The remaining regex gap is the byte
  loop, not the per-match work.
- Decimal, SQL Server and PostgreSQL streaming are ahead; Oracle and the
  HTTP server are within noise.
- The remaining losses are concentrated: regex cycles, the compiler
  self-build (1.09), the HTTP client at 1,000 connections (6%), and the
  native `task.yield` (7.7 against 7.4 ns). None of them changes the
  decision to keep native as the default and C as the bootstrap and oracle.

## Reproducing

```sh
python3 obx/bench/bench.py --opt --perf -n 11
python3 obx/bench/apps.py -n 5 --pin 2
python3 obx/bench/regex/bench.py -n 7
python3 obx/bench/json/bench.py --jq JQ
python3 obx/tests/markdown.py --perf --ref CMARK
obx/tools/native_selfbuild.sh
obx/compiler/out/obxc obx/bench/tasks.obx --native -o tasks && ./tasks
python3 obx/bench/decimal/run.py --base DIR
python3 obx/cmd/http_gate.py --servers native,c
python3 obx/cmd/http_gate.py --servers native --client --conns 1,100,1000
python3 obx/cmd/http_gate.py --servers native,c --db 4,16
python3 obx/cmd/http_gate.py --workers 1,2,4,8 --db 4
python3 obx/cmd/tls_bench.py
python3 obx/bench/dbstream/run.py
```
