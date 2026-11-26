# Lexell performance

Measured on 24–26 November 2026 on `main` (regex and microbenchmarks at `9f684cea`; applications and commands at `b28afb4c`).
Every number compares Lexell only with external tools.
Lexell's own C backend and earlier builds are not compared.
For LexDB database benchmarks against PostgreSQL 18, see [LEXDB.md](LEXDB.md) and the dedicated [LexDB performance report](lexell/docs/lexdb/performance.md).

Host: AMD Ryzen 7 8745HS (8 cores, 16 threads), 46 GB RAM, Linux 7.2 (Arch).
Versions: rustc and cargo 1.99.1, Go 1.27.3, Node.js 26.13.1, Java 21.0.13, .NET SDK 10.0.113, Python 3.14.8,
cmark 0.31.2, jq 1.7.1 (built from its tarball with `-O2`) and jq 1.8.2 from the system,
GNU grep, sort and tail, and eza 0.23.5 from the system.

Method: wall times are best of N; instruction counts are user-mode
`perf stat` instructions, the stable figure. Benchmark processes are pinned
(server CPUs 0-3, client CPUs 4-7 and 12-15). Lexell runs with
`LXL_HASH_SEED=42`. One benchmark ran at a time.

## Summary

| Area | Against | Result |
|---|---|---|
| Compile time | Rust | Much faster: about 3.6 times for hello world, about 24 times for nine programs |
| Microbenchmarks | Rust, Java, Go | Faster than Rust on eleven of nineteen, level on two; faster than warmed-up Java on eleven of twenty, near-level on one; task switching about 1.9 times Go's speed; 2–31 MB on nineteen of twenty against the JVM's 51 MB–2.36 GB |
| Regex | Go, Rust | Faster than Go on all; slower than Rust on six of seven |
| JSON | Python, jq | Faster to parse and write, slower to query; faster than jq on every filter (0.44 to 0.68 times jq 1.7.1) |
| Markdown | cmark | Slightly slower on long documents, faster on the spec examples |
| Decimal | Java, .NET | Faster than .NET on all but 19-digit add; slower than Java on division and comparison |
| HTTP server | Go net/http, Node.js | Faster at 1, 10 and 100 clients: about 1.5 times Go's requests a second, 1.2 to 1.3 times Node's |
| LexDB | PostgreSQL 18 | Moved to its own pages: see [LEXDB.md](LEXDB.md) for the high-level summary and [lexell/docs/lexdb/performance.md](lexell/docs/lexdb/performance.md) for full TPC-H, ClickBench, analytic, OLTP, materialized view, and bulk load tables |
| Command-line tools | GNU grep, sort, tail, eza | Faster on grep and eza, slower on sort, level on tail |

## Compile time

Rust (rustc with cargo) is the reference here: it is the compiled-language toolchain that the microbenchmark ports use.

From `bench/compile.py -n 3`. The Rust toolchain sizes are missing: the sizing
step fails on a broken system symlink.

| case | Lexell | Rust |
|---|---:|---:|
| hello world, compile | 13.4 ms | 47.7 ms |
| hello world, binary | 20 KB | 330 KB |
| nine benchmark programs, clean compile | 130.6 ms | 3,190 ms |
| nine benchmark programs, binaries | 196 KB | 495 KB |

The compiler's own self-build takes 502 ms (no external reference).

## Microbenchmarks

Rust is the reference: the ports in `bench/rust` are built with `opt-level = 3`, thin LTO and one codegen unit, the strongest mainstream native reference for the same work.
Java is the managed-runtime reference: the ports in `bench/java/Bench.java` run on OpenJDK 21.0.13
(default tiered C1/C2), one JVM per program, timed inside the JVM as the best of 5 runs after a
warm-up run, so the JIT has compiled the hot code and JVM startup is not counted, with a 64 MB
thread stack (`-Xss64m`) for the 10,000-deep recursion of `lists`. Arithmetic
that Lexell checks for overflow uses `Math.addExact` and `multiplyExact` in Java.

Twenty programs, native `-O`, wall time, best of 5 (`bench/bench.py --opt`): `fib`, `loop`,
`array`, `sieve`, `alloc`, `strings`, `lists`, `trees`, `tokens`, `maps`, `nbody` (floating
point), `interp` (a stack machine: an enum with payloads run by a match), `closures` (stable sorts
with comparator closures and calls through an array of functions), `matmul` (a 400 x 400 product
over arrays of rows), `pingpong` (two tasks handing a counter back and forth 2,000,000 times),
`bitpack` (columnar bit-packed integer decode, filter and multiply-sum), `btree` (in-memory
order-32 B-tree inserts, splits, lookups and range scans), `hashagg` (open-addressing columnar
hash aggregation with COUNT/SUM/MIN/MAX), `varint_csv` (delimited text parsing and LEB128 varint
encoding) and `enum_eval` (boxed closed-type SQL expression AST evaluation over columnar batches).
`pingpong` has no Rust port (Rust's lightweight tasks are an async runtime crate, and the ports
use none); its Go port uses goroutines and channels, its Java port virtual threads and a
`SynchronousQueue`. The `maps` ports use std `HashMap` (Rust, with its default SipHash) and
`java.util.HashMap`, whose layouts differ from Lexell's `Map` (insertion-ordered, with u32 index
slots), so for `maps` the comparison is of the same operations and keys, not the same data
structure. Every port prints the same checksum.

| program | Lexell | Rust | Lexell / Rust | Java (warm) | Lexell / Java |
|---|---:|---:|---:|---:|---:|
| fib | 557 ms | 928 ms | 0.60 | 641 ms | 0.87 |
| loop | 409 ms | 412 ms | 0.99 | 460 ms | 0.89 |
| array | 257 ms | 345 ms | 0.75 | 277 ms | 0.93 |
| sieve | 306 ms | 464 ms | 0.66 | 530 ms | 0.58 |
| alloc | 35 ms | 370 ms | 0.09 | 28 ms | 1.25 |
| strings | 78 ms | 273 ms | 0.29 | 47 ms | 1.66 |
| lists | 88 ms | 505 ms | 0.17 | 63 ms | 1.39 |
| trees | 61 ms | 329 ms | 0.18 | 41 ms | 1.48 |
| tokens | 102 ms | 95 ms | 1.07 | 181 ms | 0.56 |
| maps | 402 ms | 779 ms | 0.52 | 284 ms | 1.42 |
| nbody | 249 ms | 161 ms | 1.55 | 259 ms | 0.96 |
| interp | 167 ms | 212 ms | 0.78 | 342 ms | 0.49 |
| closures | 108 ms | 68 ms | 1.60 | 228 ms | 0.47 |
| matmul | 90 ms | 146 ms | 0.62 | 32 ms | 2.83 |
| pingpong | 199 ms | - | - | 841 ms | 0.24 |
| bitpack | 423 ms | 341 ms | 1.24 | 590 ms | 0.72 |
| btree | 103 ms | 105 ms | 0.99 | 100 ms | 1.03 |
| hashagg | 167 ms | 131 ms | 1.27 | 128 ms | 1.30 |
| varint_csv | 78 ms | 83 ms | 0.93 | 110 ms | 0.71 |
| enum_eval | 150 ms | 135 ms | 1.11 | 121 ms | 1.24 |

Go runs `pingpong` in 372 ms (Lexell / Go 0.54), with its default threads or with one.

`alloc` runs about 35 ms: its records never escape, so neither Lexell nor the JVM
allocates them (`lexell/design/opt-experiments.md`, section 18), while Rust's `Box` does.

Peak resident memory of the same runs (the Java figure is the JVM's over its warm-up and timed
runs, with its default heap, which may grow to a quarter of RAM):

| program | Lexell | Rust | Java |
|---|---:|---:|---:|
| fib | 2.0 MB | 2.3 MB | 51 MB |
| loop | 2.0 MB | 2.3 MB | 51 MB |
| array | 9.5 MB | 10.1 MB | 206 MB |
| sieve | 12.0 MB | 11.8 MB | 327 MB |
| alloc | 2.0 MB | 2.2 MB | 67 MB |
| strings | 2.0 MB | 2.7 MB | 548 MB |
| lists | 2.2 MB | 2.6 MB | 537 MB |
| trees | 6.0 MB | 7.1 MB | 1,364 MB |
| tokens | 3.8 MB | 3.6 MB | 552 MB |
| maps | 180 MB | 208 MB | 2,357 MB |
| nbody | 2.0 MB | 2.3 MB | 52 MB |
| interp | 2.0 MB | 2.3 MB | 54 MB |
| closures | 13.6 MB | 21.4 MB | 160 MB |
| matmul | 4.0 MB | 5.7 MB | 92 MB |
| pingpong | 2.0 MB | - | 549 MB |
| bitpack | 31.2 MB | 27.9 MB | 246 MB |
| btree | 4.0 MB | 4.9 MB | 93 MB |
| hashagg | 27.8 MB | 26.2 MB | 233 MB |
| varint_csv | 5.0 MB | 5.2 MB | 375 MB |
| enum_eval | 18.0 MB | 17.4 MB | 134 MB |

Java's speed here does not depend on that memory. With its heap capped at 64 MB (`-Xmx64m`),
`lists`, `strings` and `trees` run in 60, 46 and 42 ms at a peak of 86 to 105 MB; at 16 MB they
run 10 to 45% slower. Where Java leads on the allocation-heavy programs (`lists`, `trees`,
`strings`), the work is per object: the JVM allocates by bumping a pointer and its
young-generation collector spends its time only on live objects, so short-lived objects cost
nothing to free, whereas Lexell frees each node when its owner is dropped. Lexell's nodes are no
larger: an `Option` of a box is a pointer, so its `lists` and `trees` nodes are 16 and 24 bytes
with their headers, against Java's 24.

On `matmul` (90 ms), Lexell is 1.62× faster than Rust (146 ms), while Java's C2 JIT auto-vectorises
the inner loop (32 ms). On `nbody` (249 ms), Lexell edges ahead of Java (259 ms) and is behind Rust
(161 ms), where LLVM unrolls and vectorises the pairwise force loop. Rust's `sort_by` leads on
`closures` (68 vs 108 ms), while Lexell is more than twice as fast as Java's `List.sort` (228 ms). `interp` (167 ms)
is 21% ahead of Rust (212 ms) and more than twice Java's speed (342 ms). In `pingpong`, a round
trip of two task hand-overs takes 100 ns in Lexell, against 186 ns over Go channels and 421 ns for
Java virtual threads. `tokens` uses `&str` views of the source in all three languages (102 ms vs
Rust's 95 ms and Java's 181 ms).

On the five database-kernel benchmarks, Lexell leads Java on `bitpack` (423 vs 590 ms) and leads
both Rust and Java on `varint_csv` (78 vs 83 and 110 ms), matches Rust on `btree` (103 vs 105 ms;
Java 100 ms), and trails Rust and Java on `enum_eval` (150 vs 135 and 121 ms) and `hashagg` (167 vs
131 and 128 ms).

## Applications

### Regex

Go's `regexp` is the reference because Lexell's regex library is a port of it (`lib/regex.lxl`), with the same algorithms and semantics. Rust's `regex` crate is the other mature engine, and the one ripgrep uses.

Lexell's regex is deliberately much smaller than Rust's. Lines of code, without
comments, blank lines or generated Unicode tables:

| implementation | lines of code |
|---|---:|
| Lexell (`regex.lxl`, `regex_syntax.lxl`, `regex_dfa.lxl`) | 5,783 |
| Rust `regex` 1.12.3, `regex-syntax` 0.8.10, `regex-automata` 0.4.14 (inline unit tests included) | 50,536 |
| `aho-corasick` and `memchr`, used by `regex` by default for literal search | 20,770 |

`bench/regex/bench.py`, a 3.2 MB corpus; match counts agree across Lexell,
Go, Rust and ripgrep. Times are as the script prints them, best of 5 runs of 5
searches. The Rust column is the `regex` crate 1.12.3 from `Cargo.lock`, built
with the same target flags as the other Rust ports (`opt-level = 3`,
`target-cpu=x86-64-v3`).

| pattern | Lexell | Go regexp | Rust regex | Lexell / Go | Lexell / Rust |
|---|---:|---:|---:|---:|---:|
| literal `Sherlock Holmes` | 0.16 ms | 0.41 ms | 0.07 ms | 0.39 | 2.29 |
| alternation `Sherlock\|Holmes\|Watson\|Irene` | 0.55 ms | 132.5 ms | 0.40 ms | 0.004 | 1.38 |
| `\w+` | 19.7 ms | 121.5 ms | 16.0 ms | 0.16 | 1.23 |
| `(?i)sherlock` | 0.51 ms | 69.6 ms | 0.43 ms | 0.007 | 1.19 |
| email | 0.10 ms | 74.4 ms | 0.09 ms | 0.001 | 1.11 |
| `(?m)^ERROR .*timeout$` | 0.24 ms | 30.4 ms | 0.57 ms | 0.008 | 0.42 |
| dates `(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})` | 2.80 ms | 68.6 ms | 1.25 ms | 0.041 | 2.24 |
| `(a*)*b` on 100 KB | below timer resolution | 3.25 ms | below timer resolution | | |

Against Rust, the regex crate is faster on six patterns (email is 0.10 against 0.09 ms, near
the script's 0.01 ms resolution) and Lexell is more than twice as fast on `errors` (0.24 vs 0.57 ms);
`(a*)*b` is below timer resolution for both.

Against Rust, the remaining gap on `literal`, alternation and `(?i)sherlock` is on
the library side: Lexell uses AVX2/SSE2 runtime string search (`strFind`, `strFindPair`, `strFindByte`),
while Rust's `regex` crate adds multi-literal Teddy prefilters and specialized capture DFAs.

### JSON

Python's `json` module and jq 1.7.1 are the common tools for parsing and filtering JSON.

`bench/json/bench.py --no-c --jq <jq 1.7.1>`, an 80.2 MB generated document. Library times are
best of 3, in-process; jq times are whole-process wall time, best of 3. Each
driver's output is identical (sha256 checked).

| step | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| parse | 466 ms | Python json 825 ms | 0.56 |
| compact output | 397 ms | Python json 587 ms | 0.68 |
| pretty output | 440 ms | Python json 611 ms | 0.72 |
| query (sum of qty) | 143 ms | Python json 46 ms | 3.1 |
| visit (eachItem) | 145 ms | Python json 46 ms | 3.2 |
| jq `.` | 970 ms | jq 1.7.1 2,220 ms | 0.44 |
| jq `-c .` | 890 ms | jq 1.7.1 1,990 ms | 0.45 |
| jq `length` | 610 ms | jq 1.7.1 1,030 ms | 0.59 |
| jq `[.[].items[].qty] \| add` | 740 ms | jq 1.7.1 1,280 ms | 0.58 |
| jq `map(select(...))` | 770 ms | jq 1.7.1 1,270 ms | 0.61 |
| jq `group_by(.address.city)` | 1,020 ms | jq 1.7.1 1,510 ms | 0.68 |

The jq times are rounded to 10 ms by the script. Lexell's jq takes 0.44 to 0.68
times jq 1.7.1's time, with identical output on every filter. The query and visit steps read values
through `get()` and `eachItem`, which borrow, so they copy nothing.

### Markdown

cmark is the reference CommonMark implementation in C.

`tests/markdown.py --perf`, against cmark 0.31.2, wall time, best of 3.
The perf mode checks no output.

| input | Lexell | cmark | Lexell / cmark |
|---|---:|---:|---:|
| spec text, 49 times (10.0 MB) | 108 ms | 97 ms | 1.11 |
| repository Markdown, 2 times (13.5 MB) | 156 ms | 147 ms | 1.06 |
| spec examples, 643 times (10.0 MB) | 322 ms | 338 ms | 0.95 |

### Decimal

Java `BigDecimal` and .NET `System.Decimal` are the standard decimal types in those languages.

`bench/decimal/compare/run.sh`: the Lexell benchmarks (`decbench.lxl`, `decbench-big.lxl`,
native `-O`), the Java harness, and the .NET harness, nanoseconds per operation, on CPU 2.
Java is OpenJDK 21.0.13; .NET is SDK 10.0.113 (runtime 10.0.13), targeting net10.0.
The .NET harness has no 37- and 38-digit cases.

| operation | Lexell | .NET System.Decimal | Java BigDecimal | Lexell / .NET | Lexell / Java |
|---|---:|---:|---:|---:|---:|
| add, 19 digits | 11.6 ns | 10.9 ns | 13.3 ns | 1.06 | 0.87 |
| mul, 6 by 6 digits | 8.8 ns | 11.0 ns | 9.7 ns | 0.80 | 0.91 |
| div, 12 by 6, scale 2 | 14.0 ns | 63.1 ns | 12.0 ns | 0.22 | 1.16 |
| parse, 20 digits | 31.6 ns | 91.2 ns | 116.1 ns | 0.35 | 0.27 |
| format, 19 digits | 43.1 ns | 74.2 ns | 45.3 ns | 0.58 | 0.95 |
| cmp, 19 digits | 2.2 ns | 3.6 ns | 1.6 ns | 0.61 | 1.39 |
| add, 37 digits | 11.6 ns | not in harness | 15.5 ns | | 0.75 |
| mul, 19 digits | 13.3 ns | not in harness | 19.7 ns | | 0.68 |
| parse, 38 digits | 44.8 ns | not in harness | 207.0 ns | | 0.22 |
| format, 38 digits | 72.7 ns | not in harness | 235.5 ns | | 0.31 |

The outputs are not verified against each other. The harnesses print different
checksums for most cases, so those cases cannot be compared. The format cases print
the same checksum in Lexell and Java (the 19-digit format case also in .NET).

### HTTP server

Go's `net/http` and Node.js's `http` module are the references: plain servers
that answer `GET /` with the same body as Lexell's `cmd/httpd.lxl` (native).
Each runs on one core: the Go server with `GOMAXPROCS=1`, Node in its single
process. The load client is `cmd/httpload.lxl`: one HTTP/1.1 keep-alive
connection per client, one request at a time, for 5 seconds each. Run by
`cmd/http_gate.py --servers native,go,node --conns 1,10,100 --seconds 5 --idle 10000`,
with 10,000 idle connections held open for the memory figures. The server is on
CPU 0 and the load client on CPU 1, the gate's pinning, not the CPU ranges above.

| clients | Lexell, req/s | Go, req/s | Node.js, req/s | Lexell / Go | Lexell / Node.js |
|---:|---:|---:|---:|---:|---:|
| 1 | 108,188 | 72,412 | 83,589 | 1.49 | 1.29 |
| 10 | 179,624 | 118,426 | 142,371 | 1.52 | 1.26 |
| 100 | 174,460 | 115,866 | 142,095 | 1.51 | 1.23 |

| at 100 clients | Lexell | Go | Node.js |
|---|---:|---:|---:|
| latency p50 | 553 µs | 810 µs | 682 µs |
| latency p99 | 608 µs | 3,064 µs | 865 µs |
| memory per idle connection | 19.6 KB | 20.4 KB | 13.9 KB |
| server RSS before the idle connections | 7 MB | 8 MB | 52 MB |
| server RSS after the load | 199 MB | 341 MB | 225 MB |

## Commands

GNU grep, sort and tail, and eza are the common tools for the same jobs.

The programs in `lexell/cmd`, built with the native backend (without `-O`), against the
system tools. Wall time is measured around each process, best of 5 rounds,
interleaved, with `LC_ALL=C` and the benchmark CPUs (4-7 and 12-15), stdout written to a
temporary file. Instruction counts are user-mode. GNU sort runs several threads. The driver
does not compare outputs; they were compared separately. Every output is identical to the system
tool's except `eza -l`, which differs on one of 4,140 lines: eza 0.23.5 marks a file with
extended attributes with `@`, and Lexell's eza does not.

| case | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| grep `-c omega`, 100 MB, wall | 57 ms | GNU grep 95 ms | 0.60 |
| grep `-c omega`, instructions | 738 M | GNU grep 364 M | 2.03 |
| grep `-o -w eta`, 100 MB, wall | 236 ms | GNU grep 344 ms | 0.69 |
| grep `-o -w eta`, instructions | 3,213 M | GNU grep 3,483 M | 0.92 |
| sort, 100 MB, wall | 252 ms | GNU sort 194 ms | 1.30 |
| sort, instructions | 3,929 M | GNU sort 2,136 M | 1.84 |
| tail `-n 5`, 100 MB file, wall | 8 ms | GNU tail 8 ms | level (1 ms resolution) |
| eza `-T /usr/share`, wall | 202 ms | eza 0.23.5 931 ms | 0.22 |
| eza `-T /usr/share`, instructions | 1,080 M | eza 0.23.5 3,044 M | 0.35 |
| eza `-l /usr/lib`, wall | 26 ms | eza 0.23.5 44 ms | 0.58 |
| eza `-l /usr/lib`, instructions | 110 M | eza 0.23.5 187 M | 0.59 |

## Not measured

- **Rust toolchain sizes** in the compile table: the sizing step fails on a
  broken system symlink.
- **Plain C references** for the microbenchmarks are in the run's log but not in the table above.
- **ripgrep** in the command programs: not included.
- **HTTP client, TLS, tasks and database streaming.** Each needs its own
  references and runs.
