# Lexell performance

Measured on 24–25 November 2026 on `main` (LexDB sysbench OLTP at `0b924405`; ClickBench at `15890292`;
TPC-H at `1990a3c7`; microbenchmarks at `870cb22a`; applications, commands and the remaining LexDB suites at `b28afb4c`).
Every number compares Lexell only with external tools or databases.
Lexell's own C backend and earlier builds are not compared.

Host: AMD Ryzen 7 8745HS (8 cores, 16 threads), 46 GB RAM, Linux 7.2 (Arch).
Versions: rustc and cargo 1.99.1, Go 1.27.3, Node.js 26.13.1, Java 21.0.13, .NET SDK 10.0.113, Python 3.14.8,
PostgreSQL 18.6, sysbench 1.0.20, cmark 0.31.2, jq 1.7.1 (built from its tarball with `-O2`) and jq 1.8.2 from the system,
GNU grep, sort and tail, and eza 0.23.5 from the system.

Method: wall times are best of N; instruction counts are user-mode
`perf stat` instructions, the stable figure. Benchmark processes are pinned
(server CPUs 0-3, client CPUs 4-7 and 12-15). Lexell runs with
`LXL_HASH_SEED=42`. One benchmark ran at a time.

## Summary

| Area | Against | Result |
|---|---|---|
| Compile time | Rust | Much faster: about 3.6 times for hello world, about 24 times for nine programs |
| Microbenchmarks | Rust, Java, Go | Faster than Rust on eleven of nineteen, level on two; faster than warmed-up Java on ten of twenty, level on one; task switching about 1.8 times Go's speed; 2–31 MB on nineteen of twenty against the JVM's 51 MB–2.35 GB |
| Regex | Go, Rust | Faster than Go on all; slower than Rust on six of seven |
| JSON | Python, jq | Faster to parse and write, slower to query; faster than jq on every filter (0.44 to 0.68 times jq 1.7.1) |
| Markdown | cmark | Slightly slower on long documents, faster on the spec examples |
| Decimal | Java, .NET | Faster than .NET on all but 19-digit add; slower than Java on division and comparison |
| HTTP server | Go net/http, Node.js | Faster at 1, 10 and 100 clients: about 1.5 times Go's requests a second, 1.2 to 1.3 times Node's |
| LexDB | PostgreSQL 18 | Faster on one core than PostgreSQL on one core in TPC-H (ahead of its four processes in total, 7.48 against 8.84 s; geomean 0.52 vs one core, 0.84 vs four processes; 22 of 22 level or ahead), durable updates (pgbench 1.75–2.51×; sysbench non-index 1.32–2.78×, index 1.90–2.38× at 1–8 threads), and analytic queries (CPU 0.49 of one core, wall 0.98 of four processes); ahead on all 6 sysbench OLTP workloads at 1 thread, and with 3 replicas ahead on both `oltp_point_select` and `oltp_read_only` at 32 threads (~25% less CPU); level on ClickBench 1M single-core CPU (geomean 0.98 CPU, 1.03 wall; 28 of 43 level or ahead); slower from one process on multi-thread reads and multi-statement write blocks |
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
| fib | 571 ms | 916 ms | 0.62 | 628 ms | 0.91 |
| loop | 408 ms | 408 ms | 1.00 | 459 ms | 0.89 |
| array | 253 ms | 337 ms | 0.75 | 273 ms | 0.93 |
| sieve | 299 ms | 467 ms | 0.64 | 544 ms | 0.55 |
| alloc | 33 ms | 361 ms | 0.09 | 28 ms | 1.18 |
| strings | 74 ms | 267 ms | 0.28 | 45 ms | 1.65 |
| lists | 83 ms | 491 ms | 0.17 | 58 ms | 1.44 |
| trees | 62 ms | 324 ms | 0.19 | 42 ms | 1.47 |
| tokens | 104 ms | 95 ms | 1.10 | 187 ms | 0.56 |
| maps | 328 ms | 637 ms | 0.52 | 274 ms | 1.20 |
| nbody | 241 ms | 159 ms | 1.52 | 242 ms | 1.00 |
| interp | 154 ms | 206 ms | 0.74 | 328 ms | 0.47 |
| closures | 98 ms | 61 ms | 1.60 | 162 ms | 0.61 |
| matmul | 88 ms | 140 ms | 0.63 | 31 ms | 2.84 |
| pingpong | 190 ms | - | - | 1,655 ms | 0.12 |
| bitpack | 407 ms | 334 ms | 1.22 | 606 ms | 0.67 |
| btree | 101 ms | 101 ms | 1.00 | 96 ms | 1.05 |
| hashagg | 154 ms | 125 ms | 1.24 | 121 ms | 1.28 |
| varint_csv | 75 ms | 77 ms | 0.97 | 103 ms | 0.73 |
| enum_eval | 141 ms | 130 ms | 1.09 | 112 ms | 1.26 |

Go runs `pingpong` in 348 ms (Lexell / Go 0.55), with its default threads or with one.

`alloc` runs about 33 ms: its records never escape, so neither Lexell nor the JVM
allocates them (`lexell/design/opt-experiments.md`, section 18), while Rust's `Box` does.

Peak resident memory of the same runs (the Java figure is the JVM's over its warm-up and timed
runs, with its default heap, which may grow to a quarter of RAM):

| program | Lexell | Rust | Java |
|---|---:|---:|---:|
| fib | 2.0 MB | 2.3 MB | 51 MB |
| loop | 2.0 MB | 2.3 MB | 51 MB |
| array | 9.6 MB | 9.7 MB | 206 MB |
| sieve | 12.0 MB | 11.8 MB | 325 MB |
| alloc | 2.0 MB | 2.2 MB | 69 MB |
| strings | 2.0 MB | 2.6 MB | 549 MB |
| lists | 2.2 MB | 2.7 MB | 537 MB |
| trees | 6.0 MB | 6.9 MB | 1,364 MB |
| tokens | 3.8 MB | 3.4 MB | 553 MB |
| maps | 180 MB | 208 MB | 2,352 MB |
| nbody | 2.0 MB | 2.3 MB | 53 MB |
| interp | 2.0 MB | 2.2 MB | 54 MB |
| closures | 13.7 MB | 21.5 MB | 156 MB |
| matmul | 4.0 MB | 5.7 MB | 93 MB |
| pingpong | 2.0 MB | - | 547 MB |
| bitpack | 31.2 MB | 28.3 MB | 245 MB |
| btree | 4.0 MB | 5.0 MB | 90 MB |
| hashagg | 27.8 MB | 26.2 MB | 233 MB |
| varint_csv | 5.2 MB | 5.2 MB | 375 MB |
| enum_eval | 18.0 MB | 17.3 MB | 134 MB |

Java's speed here does not depend on that memory. With its heap capped at 64 MB (`-Xmx64m`),
`lists`, `strings` and `trees` run in 60, 46 and 42 ms at a peak of 86 to 105 MB; at 16 MB they
run 10 to 45% slower. Where Java leads on the allocation-heavy programs (`lists`, `trees`,
`strings`), the work is per object: the JVM allocates by bumping a pointer and its
young-generation collector spends its time only on live objects, so short-lived objects cost
nothing to free, whereas Lexell frees each node when its owner is dropped. Lexell's nodes are no
larger: an `Option` of a box is a pointer, so its `lists` and `trees` nodes are 16 and 24 bytes
with their headers, against Java's 24.

On `matmul` (88 ms), Lexell is 1.59× faster than Rust (140 ms), while Java's C2 JIT auto-vectorises
the inner loop (31 ms). On `nbody` (241 ms), Lexell is level with Java (242 ms) and behind Rust
(159 ms), where LLVM unrolls and vectorises the pairwise force loop. Rust's `sort_by` leads on
`closures` (61 vs 98 ms), while Lexell is ahead of Java's `List.sort` (162 ms). `interp` (154 ms)
is 26% ahead of Rust (206 ms) and more than twice Java's speed (328 ms). In `pingpong`, a round
trip of two task hand-overs takes 95 ns in Lexell, against 174 ns over Go channels and 828 ns for
Java virtual threads. `tokens` uses `&str` views of the source in all three languages (104 ms vs
Rust's 95 ms and Java's 187 ms).

On the five database-kernel benchmarks, Lexell leads Java on `bitpack` (407 vs 606 ms) and leads
both Rust and Java on `varint_csv` (75 vs 77 and 103 ms), matches Rust on `btree` (101 vs 101 ms;
Java 96 ms), and trails Rust and Java on `enum_eval` (141 vs 130 and 112 ms) and `hashagg` (154 vs
125 and 121 ms).

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
| literal `Sherlock Holmes` | 0.20 ms | 0.42 ms | 0.07 ms | 0.48 | 2.86 |
| alternation `Sherlock\|Holmes\|Watson\|Irene` | 0.59 ms | 132.6 ms | 0.40 ms | 0.004 | 1.48 |
| `\w+` | 19.7 ms | 120.1 ms | 15.9 ms | 0.16 | 1.24 |
| `(?i)sherlock` | 0.55 ms | 70.0 ms | 0.43 ms | 0.008 | 1.28 |
| email | 0.09 ms | 75.0 ms | 0.08 ms | 0.001 | 1.13 |
| `(?m)^ERROR .*timeout$` | 0.38 ms | 29.9 ms | 0.57 ms | 0.013 | 0.67 |
| dates `(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})` | 2.47 ms | 68.0 ms | 1.21 ms | 0.036 | 2.04 |
| `(a*)*b` on 100 KB | below timer resolution | 3.20 ms | below timer resolution | | |

Against Rust, the regex crate is faster on six patterns (email is 0.09 against 0.08 ms, near
the script's 0.01 ms resolution) and Lexell is faster on `errors`; `(a*)*b` is below timer
resolution for both.

Against Rust, the gap on `literal`, alternation and `(?i)sherlock` is on
the library side: the `regex` crate searches literals with SIMD `memchr` and
Teddy, and `regex.lxl` makes no SIMD call. The `\w+` and dates gaps are more
on the native backend's code generation side.

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

## LexDB

PostgreSQL 18.6 is the reference: the same machine, data, disk and transport, both servers on
the same four physical cores (their SMT siblings idle) with the clients on the other four, and
PostgreSQL's parallel queries capped at four processes, LexDB's shape (a main process and three
replicas). Both are durable by default (PostgreSQL with `fsync` and `synchronous_commit` on).
The full record, the rules and the commands are in `lexell/design/lexdb-benchmarks.md`.

### TPC-H derived (SF1)

22 queries, SF1, warm, median of 3, at a fixed clock with boost off; every result checked against
PostgreSQL's:

| | LexDB (one core) | PostgreSQL, one core | PostgreSQL, four processes |
|---|---:|---:|---:|
| all 22 queries, summed (wall) | 7,477 ms | 14,670 ms | 8,839 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | 0.52 | 0.84 |
| geometric mean of LexDB / PostgreSQL (CPU) | | 0.48 | |
| queries level or ahead of one core (within 10%) | | 22 of 22 | |

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| q1 | 1,117.9 ms | 3,365.9 ms | 0.33 | 1,114.2 ms | 3,375.3 ms | 0.33 | 873.5 ms | 1.28 |
| q2 | 36.0 ms | 160.9 ms | 0.22 | 35.9 ms | 166.9 ms | 0.22 | 137.6 ms | 0.26 |
| q3 | 499.9 ms | 551.7 ms | 0.91 | 497.6 ms | 579.3 ms | 0.86 | 353.6 ms | 1.41 |
| q4 | 132.7 ms | 184.9 ms | 0.72 | 132.3 ms | 211.6 ms | 0.63 | 102.9 ms | 1.29 |
| q5 | 148.1 ms | 312.6 ms | 0.47 | 147.6 ms | 341.2 ms | 0.43 | 173.2 ms | 0.86 |
| q6 | 179.8 ms | 274.8 ms | 0.65 | 179.2 ms | 294.1 ms | 0.61 | 203.4 ms | 0.88 |
| q7 | 390.7 ms | 585.8 ms | 0.67 | 389.2 ms | 615.2 ms | 0.63 | 287.6 ms | 1.36 |
| q8 | 143.3 ms | 226.2 ms | 0.63 | 142.7 ms | 253.5 ms | 0.56 | 141.9 ms | 1.01 |
| q9 | 1,434.6 ms | 1,743.2 ms | 0.82 | 1,428.7 ms | 1,770.1 ms | 0.81 | 750.9 ms | 1.91 |
| q10 | 425.0 ms | 389.0 ms | 1.09 | 423.0 ms | 417.2 ms | 1.01 | 167.3 ms | 2.54 |
| q11 | 63.4 ms | 61.4 ms | 1.03 | 63.1 ms | 67.7 ms | 0.93 | 61.5 ms | 1.03 |
| q12 | 417.8 ms | 854.9 ms | 0.49 | 416.5 ms | 880.7 ms | 0.47 | 253.6 ms | 1.65 |
| q13 | 619.8 ms | 839.8 ms | 0.74 | 617.1 ms | 843.9 ms | 0.73 | 825.6 ms | 0.75 |
| q14 | 129.2 ms | 141.6 ms | 0.91 | 128.7 ms | 159.8 ms | 0.81 | 95.1 ms | 1.36 |
| q15 | 180.6 ms | 331.9 ms | 0.54 | 180.4 ms | 348.1 ms | 0.52 | 333.9 ms | 0.54 |
| q16 | 205.6 ms | 267.9 ms | 0.77 | 203.2 ms | 273.4 ms | 0.74 | 105.3 ms | 1.95 |
| q17 | 20.4 ms | 551.2 ms | 0.04 | 20.4 ms | 569.9 ms | 0.04 | 554.7 ms | 0.04 |
| q18 | 573.7 ms | 2,753.9 ms | 0.21 | 571.8 ms | 2,722.6 ms | 0.21 | 2,933.0 ms | 0.20 |
| q19 | 36.7 ms | 40.2 ms | 0.91 | 36.6 ms | 53.6 ms | 0.68 | 37.5 ms | 0.98 |
| q20 | 27.1 ms | 125.8 ms | 0.22 | 27.0 ms | 149.3 ms | 0.18 | 127.8 ms | 0.21 |
| q21 | 646.3 ms | 818.4 ms | 0.79 | 643.6 ms | 846.4 ms | 0.76 | 269.6 ms | 2.40 |
| q22 | 48.4 ms | 88.4 ms | 0.55 | 48.3 ms | 94.1 ms | 0.51 | 49.5 ms | 0.98 |
| **sum** | **7,477.0 ms** | **14,670.4 ms** | **0.51** | **7,447.0 ms** | **15,033.8 ms** | **0.50** | **8,839.0 ms** | **0.85** |
| **geomean** | | | **0.52** | | | **0.48** | | **0.84** |

### OLTP

`pgbench`, prepared statements over Unix sockets, 1M rows, median of three 10 s rounds:

| | LexDB | PostgreSQL | LexDB / PostgreSQL |
|---|---:|---:|---:|
| point selects, 1 client | 89,800/s | 81,000/s | 1.11 |
| point selects, 8 / 32 clients, one process | 165,100 / 164,800/s | 447,000 / 406,000/s | 0.37 / 0.41 |
| point selects, 32 clients, three read replicas | 384,700–446,400/s | 406,000/s | 0.95–1.10 |
| updates, 1 / 8 / 32 clients (a durable commit each) | 3,689 / 16,755 / 44,953/s | 1,630 / 6,682 / 25,648/s | 2.26 / 2.51 / 1.75 |

LexDB runs every session on one thread; it scales reads with replica processes, which follow the
master with a lag of 0.22–0.23 ms at the median and 0.47–0.74 ms at p99 under a mixed load
(361,500–370,000/s replica selects alongside 15,600–15,800/s master updates). Its commit latency
with 8 clients is 0.43–0.44 ms at the median and 0.96 ms at p99.

#### sysbench OLTP (1M rows)

`bench/sysbench/run.sh`: sysbench 1.0.20, 4 tables × 250,000 rows (`sbtest1..4` with secondary index `k_i`),
prepared statements (`--db-ps-mode=auto`), Unix sockets, 10 s per run at a fixed clock (`cpu-boost off`),
servers on CPUs 0–3 and client on CPUs 4–7 and 12–15. Both servers run durable (`fsync` and `synchronous_commit` on).
Every LexDB transaction block runs at `SERIALIZABLE` isolation; PostgreSQL runs at its default `READ COMMITTED`.
Prepare (1M rows + 4 secondary indexes + `ANALYZE`): LexDB 9.33 s vs PostgreSQL 2.55 s.

LexDB (1 process) vs PostgreSQL 18 (4 cores):

| workload | threads | LexDB TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio | LexDB err | PG err |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 66,490 | 65,124 | 1.02 | 0.02 | 0.02 | 15.0 | 10.1 | 1.48 | 0 | 0 |
| `oltp_point_select` | 8 | 114,568 | 369,540 | 0.31 | 0.08 | 0.03 | 8.7 | 10.7 | 0.81 | 0 | 0 |
| `oltp_point_select` | 32 | 115,196 | 334,053 | 0.34 | 0.31 | 0.15 | 8.7 | 11.9 | 0.72 | 0 | 0 |
| `oltp_read_only` | 1 | 2,651 | 2,418 | 1.10 | 0.40 | 0.43 | 374.9 | 326.2 | 1.15 | 0 | 0 |
| `oltp_read_only` | 8 | 3,668 | 11,547 | 0.32 | 2.57 | 0.80 | 271.4 | 341.0 | 0.80 | 0 | 0 |
| `oltp_read_only` | 32 | 3,521 | 10,241 | 0.34 | 9.73 | 4.18 | 283.0 | 389.9 | 0.73 | 0 | 0 |
| `oltp_read_write` | 1 | 1,074 | 829 | 1.29 | 1.03 | 1.32 | 729.4 | 565.8 | 1.29 | 0 | 0 |
| `oltp_read_write` | 8 | 1,084 | 4,082 | 0.27 | 14.73 | 2.22 | 913.8 | 607.1 | 1.51 | 5,312 | 14 |
| `oltp_read_write` | 32 | 690 | 5,553 | 0.12 | 118.92 | 8.28 | 1,443.1 | 690.3 | 2.09 | 11,366 | 66 |
| `oltp_write_only` | 1 | 1,965 | 1,326 | 1.48 | 0.60 | 0.80 | 327.9 | 200.4 | 1.64 | 0 | 0 |
| `oltp_write_only` | 8 | 4,700 | 5,964 | 0.79 | 2.00 | 1.39 | 213.3 | 152.4 | 1.40 | 0 | 28 |
| `oltp_write_only` | 32 | 4,928 | 18,505 | 0.27 | 8.28 | 2.35 | 202.1 | 137.4 | 1.47 | 0 | 318 |
| `oltp_update_index` | 1 | 2,851 | 1,501 | 1.90 | 0.50 | 0.70 | 169.2 | 138.5 | 1.22 | 0 | 0 |
| `oltp_update_index` | 8 | 13,999 | 5,882 | 2.38 | 0.78 | 1.96 | 71.1 | 82.8 | 0.86 | 0 | 0 |
| `oltp_update_index` | 32 | 18,670 | 20,992 | 0.89 | 1.93 | 2.22 | 53.3 | 55.0 | 0.97 | 0 | 0 |
| `oltp_update_non_index` | 1 | 3,408 | 1,381 | 2.47 | 0.32 | 0.80 | 106.3 | 139.2 | 0.76 | 0 | 0 |
| `oltp_update_non_index` | 8 | 16,384 | 5,898 | 2.78 | 0.70 | 1.96 | 56.3 | 70.5 | 0.80 | 0 | 0 |
| `oltp_update_non_index` | 32 | 30,400 | 23,015 | 1.32 | 1.18 | 1.55 | 32.8 | 48.6 | 0.67 | 0 | 0 |

LexDB (3 read replicas, 4 processes) vs PostgreSQL 18 (4 cores) — read workloads:

| workload | threads | LexDB 3-rep TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 67,680 | 65,124 | 1.04 | 0.02 | 0.02 | 14.7 | 10.1 | 1.46 |
| `oltp_point_select` | 8 | 221,278 | 369,540 | 0.60 | 0.06 | 0.03 | 9.0 | 10.7 | 0.84 |
| `oltp_point_select` | 32 | 335,186 | 334,053 | 1.00 | 0.12 | 0.15 | 8.9 | 11.9 | 0.75 |
| `oltp_read_only` | 1 | 2,670 | 2,418 | 1.10 | 0.39 | 0.43 | 372.4 | 326.2 | 1.14 |
| `oltp_read_only` | 8 | 9,488 | 11,547 | 0.82 | 1.93 | 0.80 | 314.4 | 341.0 | 0.92 |
| `oltp_read_only` | 32 | 10,304 | 10,241 | 1.01 | 3.68 | 4.18 | 290.1 | 389.9 | 0.74 |

### ClickBench (1M rows)

`bench/clickbench/run.sh`: official ClickBench `hits` schema (105 columns, wide web-analytics table) and all 43 queries
(`q0`–`q42`) on the first 1,000,000 rows, warm, median of 3, at a fixed clock (`cpu-boost off`), both servers on CPUs 0–3.
All 43 queries pass (31 exact MD5 matches; 12 top-N/unordered queries with matching row counts).
Load (`COPY` 1M × 105 cols): LexDB 17.00 s vs PostgreSQL 6.42 s; `ANALYZE`: LexDB 17.24 s vs PostgreSQL 1.19 s.

| | LexDB (one core) | PostgreSQL, one core | PostgreSQL, four processes |
|---|---:|---:|---:|
| all 43 queries, summed (wall) | 42,025 ms | 22,363 ms | 11,326 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | 1.03 | 2.29 |
| geometric mean of LexDB / PostgreSQL (CPU) | | 0.98 | |
| queries level or ahead of one core (within 10%) | | 28 of 43 | |

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| q0 | 52.6 ms | 87.5 ms | 0.60 | 52.5 ms | 109.9 ms | 0.48 | 34.7 ms | 1.52 |
| q1 | 210.5 ms | 342.0 ms | 0.62 | 209.6 ms | 361.5 ms | 0.58 | 106.3 ms | 1.98 |
| q2 | 211.1 ms | 392.2 ms | 0.54 | 210.2 ms | 411.9 ms | 0.51 | 107.7 ms | 1.96 |
| q3 | 274.5 ms | 256.2 ms | 1.07 | 273.4 ms | 276.6 ms | 0.99 | 80.0 ms | 3.43 |
| q4 | 161.8 ms | 304.0 ms | 0.53 | 161.1 ms | 323.7 ms | 0.50 | 302.4 ms | 0.54 |
| q5 | 272.1 ms | 429.8 ms | 0.63 | 271.1 ms | 450.0 ms | 0.60 | 419.5 ms | 0.65 |
| q6 | 195.5 ms | 252.1 ms | 0.78 | 194.7 ms | 273.4 ms | 0.71 | 79.3 ms | 2.47 |
| q7 | 210.1 ms | 337.2 ms | 0.62 | 209.3 ms | 357.9 ms | 0.58 | 107.1 ms | 1.96 |
| q8 | 188.0 ms | 489.4 ms | 0.38 | 187.1 ms | 509.3 ms | 0.37 | 479.0 ms | 0.39 |
| q9 | 278.2 ms | 624.1 ms | 0.45 | 277.2 ms | 643.1 ms | 0.43 | 604.6 ms | 0.46 |
| q10 | 224.3 ms | 347.7 ms | 0.65 | 223.4 ms | 368.2 ms | 0.61 | 101.3 ms | 2.21 |
| q11 | 228.8 ms | 352.4 ms | 0.65 | 227.8 ms | 371.1 ms | 0.61 | 103.8 ms | 2.20 |
| q12 | 293.2 ms | 365.6 ms | 0.80 | 291.9 ms | 385.4 ms | 0.76 | 113.6 ms | 2.58 |
| q13 | 312.0 ms | 381.5 ms | 0.82 | 310.6 ms | 402.8 ms | 0.77 | 143.7 ms | 2.17 |
| q14 | 310.3 ms | 363.1 ms | 0.85 | 308.8 ms | 383.8 ms | 0.80 | 346.7 ms | 0.90 |
| q15 | 356.4 ms | 336.5 ms | 1.06 | 354.6 ms | 359.0 ms | 0.99 | 132.2 ms | 2.70 |
| q16 | 571.1 ms | 468.6 ms | 1.22 | 568.6 ms | 488.9 ms | 1.16 | 442.8 ms | 1.29 |
| q17 | 549.5 ms | 444.5 ms | 1.24 | 547.4 ms | 464.2 ms | 1.18 | 162.0 ms | 3.39 |
| q18 | 2,452.4 ms | 674.1 ms | 3.64 | 2,439.6 ms | 692.9 ms | 3.52 | 635.6 ms | 3.86 |
| q19 | 149.9 ms | 238.6 ms | 0.63 | 149.3 ms | 259.3 ms | 0.58 | 73.6 ms | 2.04 |
| q20 | 284.5 ms | 375.3 ms | 0.76 | 283.2 ms | 397.4 ms | 0.71 | 106.5 ms | 2.67 |
| q21 | 324.4 ms | 456.5 ms | 0.71 | 323.2 ms | 476.3 ms | 0.68 | 134.2 ms | 2.42 |
| q22 | 643.4 ms | 512.7 ms | 1.25 | 640.2 ms | 533.1 ms | 1.20 | 137.7 ms | 4.67 |
| q23 | 1,326.7 ms | 370.6 ms | 3.58 | 1,321.5 ms | 390.8 ms | 3.38 | 104.2 ms | 12.73 |
| q24 | 255.0 ms | 349.7 ms | 0.73 | 254.1 ms | 370.1 ms | 0.69 | 100.6 ms | 2.53 |
| q25 | 241.8 ms | 347.4 ms | 0.70 | 240.7 ms | 367.8 ms | 0.65 | 100.5 ms | 2.41 |
| q26 | 261.3 ms | 351.7 ms | 0.74 | 259.7 ms | 371.6 ms | 0.70 | 100.9 ms | 2.59 |
| q27 | 681.1 ms | 501.9 ms | 1.36 | 678.4 ms | 523.8 ms | 1.30 | 169.1 ms | 4.03 |
| q28 | 17,005.1 ms | 4,030.8 ms | 4.22 | 16,953.6 ms | 4,039.0 ms | 4.20 | 1,057.0 ms | 16.09 |
| q29 | 745.6 ms | 852.2 ms | 0.87 | 743.0 ms | 871.6 ms | 0.85 | 336.3 ms | 2.22 |
| q30 | 346.4 ms | 362.4 ms | 0.96 | 344.9 ms | 382.1 ms | 0.90 | 353.7 ms | 0.98 |
| q31 | 514.4 ms | 385.5 ms | 1.33 | 511.3 ms | 406.5 ms | 1.26 | 375.7 ms | 1.37 |
| q32 | 3,303.9 ms | 917.0 ms | 3.60 | 3,288.2 ms | 935.4 ms | 3.52 | 905.7 ms | 3.65 |
| q33 | 1,193.6 ms | 479.2 ms | 2.49 | 1,187.7 ms | 498.1 ms | 2.38 | 461.8 ms | 2.58 |
| q34 | 1,329.0 ms | 487.0 ms | 2.73 | 1,322.8 ms | 506.5 ms | 2.61 | 466.9 ms | 2.85 |
| q35 | 496.0 ms | 396.7 ms | 1.25 | 493.6 ms | 416.7 ms | 1.18 | 156.4 ms | 3.17 |
| q36 | 970.0 ms | 548.0 ms | 1.77 | 965.5 ms | 566.9 ms | 1.70 | 246.7 ms | 3.93 |
| q37 | 720.4 ms | 494.2 ms | 1.46 | 717.2 ms | 514.5 ms | 1.39 | 169.9 ms | 4.24 |
| q38 | 374.0 ms | 404.5 ms | 0.92 | 372.4 ms | 425.5 ms | 0.88 | 145.8 ms | 2.57 |
| q39 | 2,203.5 ms | 536.6 ms | 4.11 | 2,193.5 ms | 556.1 ms | 3.94 | 532.5 ms | 4.14 |
| q40 | 446.5 ms | 621.5 ms | 0.72 | 444.7 ms | 641.0 ms | 0.69 | 220.6 ms | 2.02 |
| q41 | 405.2 ms | 599.1 ms | 0.68 | 403.2 ms | 618.9 ms | 0.65 | 198.9 ms | 2.04 |
| q42 | 451.0 ms | 495.3 ms | 0.91 | 449.1 ms | 515.4 ms | 0.87 | 168.0 ms | 2.68 |
| **sum** | **42,025.1 ms** | **22,362.9 ms** | **1.88** | **41,852.4 ms** | **23,190.4 ms** | **1.80** | **11,325.5 ms** | **3.71** |
| **geomean** | | | **1.03** | | | **0.98** | | **2.29** |

### Analytic queries

35 queries over 1M-row tables (scans, joins, groups, windows; median of 5):
LexDB's CPU is 0.49 of PostgreSQL's on one core (geometric mean; wall 0.60), and its wall time
0.98 of PostgreSQL's on four processes; 33 of 35 are level with or ahead of PostgreSQL on one core
on CPU (34 of 35 on wall time).

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `scan2` | 112 ms | 143 ms | 0.78 | 56 ms | 90 ms | 0.62 | 141 ms | 0.79 |
| `scan3` | 162 ms | 213 ms | 0.76 | 79 ms | 120 ms | 0.66 | 214 ms | 0.76 |
| `scan9` | 518 ms | 532 ms | 0.97 | 263 ms | 250 ms | 1.05 | 529 ms | 0.98 |
| `filt1pct` | 19 ms | 41 ms | 0.46 | 14 ms | 40 ms | 0.35 | 22 ms | 0.86 |
| `filt10pct` | 35 ms | 59 ms | 0.59 | 23 ms | 50 ms | 0.46 | 59 ms | 0.59 |
| `filt_like` | 39 ms | 82 ms | 0.48 | 34 ms | 80 ms | 0.42 | 32 ms | 1.22 |
| `filt_agg` | 21 ms | 45 ms | 0.47 | 17 ms | 50 ms | 0.34 | 22 ms | 0.95 |
| `expr_int` | 153 ms | 218 ms | 0.70 | 70 ms | 140 ms | 0.50 | 218 ms | 0.70 |
| `expr_mix` | 373 ms | 431 ms | 0.87 | 258 ms | 310 ms | 0.83 | 428 ms | 0.87 |
| `expr_agg` | 31 ms | 58 ms | 0.53 | 27 ms | 60 ms | 0.45 | 26 ms | 1.19 |
| `sort_all` | 122 ms | 438 ms | 0.28 | 66 ms | 380 ms | 0.17 | 438 ms | 0.28 |
| `sort_lim` | 19 ms | 91 ms | 0.21 | 15 ms | 90 ms | 0.17 | 33 ms | 0.58 |
| `count` | 11 ms | 36 ms | 0.31 | 7 ms | 30 ms | 0.23 | 18 ms | 0.61 |
| `grp_int` | 30 ms | 97 ms | 0.31 | 26 ms | 90 ms | 0.29 | 35 ms | 0.86 |
| `grp_text` | 54 ms | 127 ms | 0.43 | 50 ms | 130 ms | 0.38 | 42 ms | 1.29 |
| `minmax_text` | 57 ms | 128 ms | 0.45 | 53 ms | 130 ms | 0.41 | 43 ms | 1.33 |
| `distinct` | 66 ms | 95 ms | 0.69 | 61 ms | 90 ms | 0.68 | 34 ms | 1.94 |
| `distinct2` | 143 ms | 113 ms | 1.27 | 139 ms | 110 ms | 1.26 | 40 ms | 3.58 |
| `idx_range1k` | 5 ms | 10 ms | 0.50 | 1 ms | 10 ms | 0.10 | 9 ms | 0.56 |
| `idx_range100k` | 46 ms | 46 ms | 1.00 | 34 ms | 40 ms | 0.85 | 45 ms | 1.02 |
| `idx_range_agg` | 29 ms | 29 ms | 1.00 | 25 ms | 30 ms | 0.83 | 24 ms | 1.21 |
| `pk_range100k` | 21 ms | 32 ms | 0.66 | 9 ms | 20 ms | 0.45 | 32 ms | 0.66 |
| `pk_point20k` | 618 ms | 618 ms | 1.00 | 574 ms | 410 ms | 1.40 | 638 ms | 0.97 |
| `join_hash_agg` | 40 ms | 98 ms | 0.41 | 36 ms | 100 ms | 0.36 | 35 ms | 1.14 |
| `join_hash_rows` | 38 ms | 63 ms | 0.60 | 28 ms | 60 ms | 0.47 | 63 ms | 0.60 |
| `join_lookup_agg` | 75 ms | 79 ms | 0.95 | 71 ms | 80 ms | 0.89 | 32 ms | 2.34 |
| `sub_in` | 25 ms | 51 ms | 0.49 | 21 ms | 50 ms | 0.42 | 24 ms | 1.04 |
| `sub_exists` | 25 ms | 51 ms | 0.49 | 22 ms | 60 ms | 0.37 | 24 ms | 1.04 |
| `sub_corr_sel` | 109 ms | 149 ms | 0.73 | 96 ms | 150 ms | 0.64 | 150 ms | 0.73 |
| `window` | 130 ms | 143 ms | 0.91 | 111 ms | 130 ms | 0.85 | 89 ms | 1.46 |
| `join_hash_sort` | 66 ms | 115 ms | 0.57 | 53 ms | 110 ms | 0.48 | 54 ms | 1.22 |
| `join_text_agg` | 60 ms | 86 ms | 0.70 | 56 ms | 90 ms | 0.62 | 32 ms | 1.88 |
| `join_text_rows` | 73 ms | 87 ms | 0.84 | 61 ms | 70 ms | 0.87 | 87 ms | 0.84 |
| `join_text_group` | 99 ms | 165 ms | 0.60 | 94 ms | 170 ms | 0.55 | 52 ms | 1.90 |
| `join_left_rows` | 32 ms | 56 ms | 0.57 | 18 ms | 50 ms | 0.36 | 56 ms | 0.57 |
| **geomean** | | | **0.60** | | | **0.49** | | **0.98** |

### Bulk loads

`\copy`, median of 3, not pinned:

| workload | LexDB | PostgreSQL 18 | LexDB / PG | LexDB peak RSS |
|---|---:|---:|---:|---:|
| narrow, 1M rows | 0.48 s | 0.61 s | 0.79 | 338 MB |
| wide, 1M rows | 1.40 s | 2.15 s | 0.65 | 766 MB |
| wide + 2 secondary indexes, 1M rows | 2.60 s | 4.92 s | 0.53 | 1,565 MB |
| wide, no primary key, 1M rows | 1.75 s | 1.39 s | 1.26 | 806 MB |
| narrow, 10M rows | 4.82 s | 5.84 s | 0.83 | 3,258 MB |

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
- **SQL Server** against LexDB: its container was not running for this run.
- **Oracle** comparison: dropped for now, to be added back later.
