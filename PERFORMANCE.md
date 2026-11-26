# Lexell performance

Measured on 24–26 November 2026 on `main` (LexDB ClickBench 1M, TPC-H SF1, Data Skipping Indexes, and Two-Level Hash Aggregation at `e59eecc2`;
OLTP, analytic queries, bulk loads, and dedicated Materialized Views at `5d93ced1` / `2b5b92a2`; regex and microbenchmarks at `9f684cea`; applications and commands at `b28afb4c`).
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
| Microbenchmarks | Rust, Java, Go | Faster than Rust on eleven of nineteen, level on two; faster than warmed-up Java on eleven of twenty, near-level on one; task switching about 1.9 times Go's speed; 2–31 MB on nineteen of twenty against the JVM's 51 MB–2.36 GB |
| Regex | Go, Rust | Faster than Go on all; slower than Rust on six of seven |
| JSON | Python, jq | Faster to parse and write, slower to query; faster than jq on every filter (0.44 to 0.68 times jq 1.7.1) |
| Markdown | cmark | Slightly slower on long documents, faster on the spec examples |
| Decimal | Java, .NET | Faster than .NET on all but 19-digit add; slower than Java on division and comparison |
| HTTP server | Go net/http, Node.js | Faster at 1, 10 and 100 clients: about 1.5 times Go's requests a second, 1.2 to 1.3 times Node's |
| LexDB | PostgreSQL 18 | Faster on one core than PostgreSQL on one core in TPC-H (ahead of its four processes in total, 7.44 against 8.84 s; geomean 0.51 vs one core, 0.82 vs four processes; 22 of 22 faster than one core), ClickBench 1M (ahead on total wall 17.06 vs 22.36 s; geomean 0.75 wall, 0.70 CPU; 40 of 43 level or ahead; 11.80 s total and geomean 0.10 vs PG1 / 0.23 vs PG4 with 8 transparently rewritten MVs covering 21 queries; up to 4.07× faster on point/LIKE filters with explicit data skipping indexes), durable updates (pgbench 2.51–2.71×; sysbench non-index 2.40–3.15×, index 1.28–2.54× at 1–32 threads), bulk COPY loads (0.37–0.68× on all 5 cases), analytic queries (CPU 0.48 of one core, wall 0.95 of four processes; 0.30 / 0.49 with 4 transparently rewritten MVs), and incremental materialized views (0.48–0.72 ms `FAST` update vs 60–364 ms PG `REFRESH`; sketch MV build 224 vs 372 ms); ahead on all 6 sysbench OLTP workloads at 1 thread, on `oltp_write_only` through 8 threads, and with 3 replicas ahead on pgbench (500–504k/s vs 408k/s) and sysbench `oltp_point_select` (1.13×) and `oltp_read_only` (1.03×) at 32 threads (28–33% less CPU); slower from one process on multi-thread reads and multi-statement read-write blocks |
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
| all 22 queries, summed (wall) | 7,437 ms | 14,670 ms | 8,839 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | 0.51 | 0.82 |
| geometric mean of LexDB / PostgreSQL (CPU) | | 0.47 | |
| queries faster than one core | | 22 of 22 | |

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| q1 | 1,150.1 ms | 3,365.9 ms | 0.34 | 1,145.2 ms | 3,375.3 ms | 0.34 | 873.5 ms | 1.32 |
| q2 | 37.3 ms | 160.9 ms | 0.23 | 37.2 ms | 166.9 ms | 0.22 | 137.6 ms | 0.27 |
| q3 | 514.9 ms | 551.7 ms | 0.93 | 510.9 ms | 579.3 ms | 0.88 | 353.6 ms | 1.46 |
| q4 | 124.1 ms | 184.9 ms | 0.67 | 123.5 ms | 211.6 ms | 0.58 | 102.9 ms | 1.21 |
| q5 | 157.3 ms | 312.6 ms | 0.50 | 156.7 ms | 341.2 ms | 0.46 | 173.2 ms | 0.91 |
| q6 | 193.3 ms | 274.8 ms | 0.70 | 191.9 ms | 294.1 ms | 0.65 | 203.4 ms | 0.95 |
| q7 | 393.5 ms | 585.8 ms | 0.67 | 391.8 ms | 615.2 ms | 0.64 | 287.6 ms | 1.37 |
| q8 | 155.4 ms | 226.2 ms | 0.69 | 154.7 ms | 253.5 ms | 0.61 | 141.9 ms | 1.10 |
| q9 | 1,474.2 ms | 1,743.2 ms | 0.85 | 1,467.4 ms | 1,770.1 ms | 0.83 | 750.9 ms | 1.96 |
| q10 | 275.8 ms | 389.0 ms | 0.71 | 274.3 ms | 417.2 ms | 0.66 | 167.3 ms | 1.65 |
| q11 | 52.9 ms | 61.4 ms | 0.86 | 52.6 ms | 67.7 ms | 0.78 | 61.5 ms | 0.86 |
| q12 | 435.0 ms | 854.9 ms | 0.51 | 433.1 ms | 880.7 ms | 0.49 | 253.6 ms | 1.72 |
| q13 | 682.3 ms | 839.8 ms | 0.81 | 678.9 ms | 843.9 ms | 0.80 | 825.6 ms | 0.83 |
| q14 | 139.2 ms | 141.6 ms | 0.98 | 138.7 ms | 159.8 ms | 0.87 | 95.1 ms | 1.46 |
| q15 | 160.0 ms | 331.9 ms | 0.48 | 159.8 ms | 348.1 ms | 0.46 | 333.9 ms | 0.48 |
| q16 | 206.9 ms | 267.9 ms | 0.77 | 204.4 ms | 273.4 ms | 0.75 | 105.3 ms | 1.96 |
| q17 | 22.3 ms | 551.2 ms | 0.04 | 22.4 ms | 569.9 ms | 0.04 | 554.7 ms | 0.04 |
| q18 | 541.8 ms | 2,753.9 ms | 0.20 | 539.4 ms | 2,722.6 ms | 0.20 | 2,933.0 ms | 0.18 |
| q19 | 29.8 ms | 40.2 ms | 0.74 | 29.8 ms | 53.6 ms | 0.56 | 37.5 ms | 0.79 |
| q20 | 27.7 ms | 125.8 ms | 0.22 | 27.7 ms | 149.3 ms | 0.19 | 127.8 ms | 0.22 |
| q21 | 615.1 ms | 818.4 ms | 0.75 | 612.7 ms | 846.4 ms | 0.72 | 269.6 ms | 2.28 |
| q22 | 47.8 ms | 88.4 ms | 0.54 | 47.7 ms | 94.1 ms | 0.51 | 49.5 ms | 0.97 |
| **sum** | **7,436.7 ms** | **14,670.4 ms** | **0.51** | **7,400.7 ms** | **15,033.9 ms** | **0.49** | **8,839.0 ms** | **0.84** |
| **geomean** | | | **0.51** | | | **0.47** | | **0.82** |

### OLTP

`pgbench`, prepared statements over Unix sockets, 1M rows, median of three 10 s rounds:

| | LexDB | PostgreSQL | LexDB / PostgreSQL |
|---|---:|---:|---:|
| point selects, 1 client | 98,794/s | 81,548/s | 1.21 |
| point selects, 8 / 32 clients, one process | 188,196 / 180,704/s | 440,141 / 407,971/s | 0.43 / 0.44 |
| point selects, 32 clients, three read replicas | 499,549–503,649/s | 407,971/s | 1.22–1.23 |
| updates, 1 / 8 / 32 clients (a durable commit each) | 4,079 / 18,296 / 67,022/s | 1,627 / 6,743 / 25,923/s | 2.51 / 2.71 / 2.59 |

LexDB runs every session on one thread; it scales reads with replica processes, which follow the
master with a lag of 0.21–0.23 ms at the median and 0.48 ms at p99 under a mixed load
(408,400–415,600/s replica selects alongside 16,050–16,400/s master updates). Its commit latency
with 8 clients is 0.41 ms at the median and 0.81–0.83 ms at p99.

#### sysbench OLTP (1M rows)

`bench/sysbench/run.sh`: sysbench 1.0.20, 4 tables × 250,000 rows (`sbtest1..4` with secondary index `k_i`),
prepared statements (`--db-ps-mode=auto`), Unix sockets, 10 s per run at a fixed clock (`cpu-boost off`),
servers on CPUs 0–3 and client on CPUs 4–7 and 12–15. Both servers run durable (`fsync` and `synchronous_commit` on).
LexDB defaults to `SERIALIZABLE` isolation and also supports opt-in `READ COMMITTED`; PostgreSQL runs at its default `READ COMMITTED`.
Both isolation levels are shown for `oltp_read_write`.
Prepare (1M rows + 4 secondary indexes + `ANALYZE`): LexDB 5.60 s vs PostgreSQL 2.55 s.

LexDB (1 process) vs PostgreSQL 18 (4 cores):

| workload | threads | LexDB TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio | LexDB err | PG err |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 70,293 | 65,124 | 1.08 | 0.02 | 0.02 | 14.2 | 10.1 | 1.40 | 0 | 0 |
| `oltp_point_select` | 8 | 127,440 | 369,540 | 0.34 | 0.07 | 0.03 | 7.8 | 10.7 | 0.73 | 0 | 0 |
| `oltp_point_select` | 32 | 125,879 | 334,053 | 0.38 | 0.27 | 0.15 | 7.9 | 11.9 | 0.66 | 0 | 0 |
| `oltp_read_only` | 1 | 2,778 | 2,418 | 1.15 | 0.37 | 0.43 | 357.6 | 326.2 | 1.10 | 0 | 0 |
| `oltp_read_only` | 8 | 3,937 | 11,547 | 0.34 | 2.35 | 0.80 | 252.9 | 341.0 | 0.74 | 0 | 0 |
| `oltp_read_only` | 32 | 3,742 | 10,241 | 0.37 | 9.06 | 4.18 | 266.2 | 389.9 | 0.68 | 0 | 0 |
| `oltp_read_write` (`SERIALIZABLE`) | 1 | 1,190 | 829 | 1.44 | 0.90 | 1.32 | 641.7 | 565.8 | 1.13 | 0 | 0 |
| `oltp_read_write` (`SERIALIZABLE`) | 8 | 1,429 | 4,082 | 0.35 | 11.24 | 2.22 | 698.5 | 607.1 | 1.15 | 6,642 | 14 |
| `oltp_read_write` (`SERIALIZABLE`) | 32 | 871 | 5,553 | 0.16 | 95.81 | 8.28 | 1,145.2 | 690.3 | 1.66 | 13,642 | 66 |
| `oltp_read_write` (`READ COMMITTED`) | 1 | 1,207 | 829 | 1.46 | 0.89 | 1.32 | 627.5 | 565.8 | 1.11 | 0 | 0 |
| `oltp_read_write` (`READ COMMITTED`) | 8 | 2,030 | 4,082 | 0.50 | 4.41 | 2.22 | 492.7 | 607.1 | 0.81 | 0 | 14 |
| `oltp_read_write` (`READ COMMITTED`) | 32 | 2,048 | 5,553 | 0.37 | 18.61 | 8.28 | 490.0 | 690.3 | 0.71 | 0 | 66 |
| `oltp_write_only` | 1 | 2,636 | 1,326 | 1.99 | 0.44 | 0.80 | 197.3 | 200.4 | 0.98 | 0 | 0 |
| `oltp_write_only` | 8 | 8,150 | 5,964 | 1.37 | 1.27 | 1.39 | 123.4 | 152.4 | 0.81 | 0 | 28 |
| `oltp_write_only` | 32 | 6,524 | 18,505 | 0.35 | 7.04 | 2.35 | 153.6 | 137.4 | 1.12 | 0 | 318 |
| `oltp_update_index` | 1 | 3,434 | 1,501 | 2.29 | 0.41 | 0.70 | 110.1 | 138.5 | 0.79 | 0 | 0 |
| `oltp_update_index` | 8 | 14,945 | 5,882 | 2.54 | 0.63 | 1.96 | 52.7 | 82.8 | 0.64 | 0 | 0 |
| `oltp_update_index` | 32 | 26,915 | 20,992 | 1.28 | 1.86 | 2.22 | 37.2 | 55.0 | 0.68 | 0 | 0 |
| `oltp_update_non_index` | 1 | 3,894 | 1,381 | 2.82 | 0.30 | 0.80 | 73.0 | 139.2 | 0.52 | 0 | 0 |
| `oltp_update_non_index` | 8 | 18,563 | 5,898 | 3.15 | 0.46 | 1.96 | 28.1 | 70.5 | 0.40 | 0 | 0 |
| `oltp_update_non_index` | 32 | 55,171 | 23,015 | 2.40 | 0.95 | 1.55 | 18.2 | 48.6 | 0.38 | 0 | 0 |

LexDB (3 read replicas, 4 processes) vs PostgreSQL 18 (4 cores) — read workloads:

| workload | threads | LexDB 3-rep TPS | PG TPS | TPS ratio | LexDB p95 (ms) | PG p95 (ms) | LexDB CPU µs/tx | PG CPU µs/tx | CPU ratio |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `oltp_point_select` | 1 | 71,169 | 65,124 | 1.09 | 0.01 | 0.02 | 14.0 | 10.1 | 1.39 |
| `oltp_point_select` | 8 | 343,266 | 369,540 | 0.93 | 0.03 | 0.03 | 8.7 | 10.7 | 0.81 |
| `oltp_point_select` | 32 | 376,129 | 334,053 | 1.13 | 0.10 | 0.15 | 8.0 | 11.9 | 0.67 |
| `oltp_read_only` | 1 | 2,801 | 2,418 | 1.16 | 0.37 | 0.43 | 354.7 | 326.2 | 1.09 |
| `oltp_read_only` | 8 | 10,825 | 11,547 | 0.94 | 1.01 | 0.80 | 275.9 | 341.0 | 0.81 |
| `oltp_read_only` | 32 | 10,589 | 10,241 | 1.03 | 5.09 | 4.18 | 282.1 | 389.9 | 0.72 |

### ClickBench (1M rows)

`bench/clickbench/run.sh`: official ClickBench `hits` schema (105 columns, wide web-analytics table) and all 43 queries
(`q0`–`q42`) on the first 1,000,000 rows, warm, median of 3, at a fixed clock (`cpu-boost off`), both servers on CPUs 0–3.
All 43 queries pass (31 exact MD5 matches; 12 top-N/unordered queries with matching row counts).

The baseline columns (`LexDB wall`, `PG 1-core`, `PG 4-proc`) run strictly apples-to-apples with no materialized views
and no explicit skipping indexes (automatic zero-config `T_CLEAF` zone maps and adaptive two-level hash aggregation
with bump-arena string keys and direct Top-N group pruning are always on by default).
The final column (`LexDB + MV`) shows a separate run of the **exact same unmodified queries** after adding eight
general-purpose incremental `ENABLE QUERY REWRITE` rollup views (`mv_hits_adv` 6 rows / 869 ms build,
`mv_hits_counter` 7 rows / 709 ms, `mv_hits_region_user` 80,309 rows / 648 ms, `mv_hits_mobile` 2,522 rows / 299 ms,
`mv_hits_search` 28,357 rows / 446 ms, `mv_hits_url` 275,494 rows / 1,776 ms, `mv_hits_ip` 68,330 rows / 447 ms,
`mv_hits_minute` 4,346 rows / 969 ms; total build 6.16 s), exercising exact `COUNT(DISTINCT)` rollups (`q4`, `q8`–`q11`,
`q13`), wide (`>512`-byte) hashed group keys (`q12`–`q14`, `q20`, `q33`, `q34`), and functionally dependent exact-grain
`GROUP BY` matching (`q34`, `q35`). All 21 rewritten queries were verified against `query_rewrite_enabled = off` (19
bit-for-bit identical; `q10` and `q11` match exact counts with tie-breaking at count 12). After data load, inserting
1 / 100 new `hits` rows while maintaining all 8 views live (`REFRESH FAST ON STATEMENT`) takes **5.57 / 10.30 ms**.

| | LexDB (one core) | PostgreSQL, one core | PostgreSQL, four processes | LexDB + 8 MVs (transparent rewrite) |
|---|---:|---:|---:|---:|
| all 43 queries, summed (wall) | 17,059 ms | 22,363 ms | 11,326 ms | 11,799 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | 0.75 | 1.65 | 0.10 vs PG1 / 0.23 vs PG4 |
| geometric mean of LexDB / PostgreSQL (CPU) | | 0.70 | | |
| queries level or ahead of one core (within 10%) | | 40 of 43 | | 40 of 43 (21 rewritten; 27 of 43 vs PG4) |

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 | LexDB + MV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| q0 | 51.6 ms | 87.5 ms | 0.59 | 51.4 ms | 109.9 ms | 0.47 | 34.7 ms | 1.49 | **0.62 ms** |
| q1 | 224.5 ms | 342.0 ms | 0.66 | 223.6 ms | 361.5 ms | 0.62 | 106.3 ms | 2.11 | **0.62 ms** |
| q2 | 216.2 ms | 392.2 ms | 0.55 | 215.1 ms | 411.9 ms | 0.52 | 107.7 ms | 2.01 | **0.65 ms** |
| q3 | 276.7 ms | 256.2 ms | 1.08 | 275.4 ms | 276.6 ms | 1.00 | 80.0 ms | 3.46 | **0.64 ms** |
| q4 | 173.5 ms | 304.0 ms | 0.57 | 172.7 ms | 323.7 ms | 0.53 | 302.4 ms | 0.57 | **5.93 ms** |
| q5 | 285.6 ms | 429.8 ms | 0.66 | 283.9 ms | 450.0 ms | 0.63 | 419.5 ms | 0.68 | — |
| q6 | 203.6 ms | 252.1 ms | 0.81 | 202.6 ms | 273.4 ms | 0.74 | 79.3 ms | 2.57 | **0.46 ms** |
| q7 | 223.0 ms | 337.2 ms | 0.66 | 222.0 ms | 357.9 ms | 0.62 | 107.1 ms | 2.08 | **0.51 ms** |
| q8 | 186.2 ms | 489.4 ms | 0.38 | 185.3 ms | 509.3 ms | 0.36 | 479.0 ms | 0.39 | **4.61 ms** |
| q9 | 279.8 ms | 624.1 ms | 0.45 | 278.5 ms | 643.1 ms | 0.43 | 604.6 ms | 0.46 | **10.15 ms** |
| q10 | 228.7 ms | 347.7 ms | 0.66 | 227.7 ms | 368.2 ms | 0.62 | 101.3 ms | 2.26 | **0.75 ms** |
| q11 | 229.4 ms | 352.4 ms | 0.65 | 228.3 ms | 371.1 ms | 0.62 | 103.8 ms | 2.21 | **0.82 ms** |
| q12 | 249.8 ms | 365.6 ms | 0.68 | 248.6 ms | 385.4 ms | 0.64 | 113.6 ms | 2.20 | **42.55 ms** |
| q13 | 285.8 ms | 381.5 ms | 0.75 | 284.3 ms | 402.8 ms | 0.71 | 143.7 ms | 1.99 | **33.81 ms** |
| q14 | 266.9 ms | 363.1 ms | 0.74 | 265.6 ms | 383.8 ms | 0.69 | 346.7 ms | 0.77 | **48.21 ms** |
| q15 | 191.3 ms | 336.5 ms | 0.57 | 190.2 ms | 359.0 ms | 0.53 | 132.2 ms | 1.45 | **144.43 ms** |
| q16 | 325.7 ms | 468.6 ms | 0.70 | 324.2 ms | 488.9 ms | 0.66 | 442.8 ms | 0.74 | — |
| q17 | 438.3 ms | 444.5 ms | 0.99 | 436.1 ms | 464.2 ms | 0.94 | 162.0 ms | 2.71 | — |
| q18 | 456.4 ms | 674.1 ms | 0.68 | 454.1 ms | 692.9 ms | 0.66 | 635.6 ms | 0.72 | — |
| q19 | 172.2 ms | 238.6 ms | 0.72 | 171.4 ms | 259.3 ms | 0.66 | 73.6 ms | 2.34 | — |
| q20 | 304.4 ms | 375.3 ms | 0.81 | 303.0 ms | 397.4 ms | 0.76 | 106.5 ms | 2.86 | **55.41 ms** |
| q21 | 345.0 ms | 456.5 ms | 0.76 | 343.5 ms | 476.3 ms | 0.72 | 134.2 ms | 2.57 | — |
| q22 | 634.1 ms | 512.7 ms | 1.24 | 631.3 ms | 533.1 ms | 1.18 | 137.7 ms | 4.60 | — |
| q23 | 336.2 ms | 370.6 ms | 0.91 | 334.7 ms | 390.8 ms | 0.86 | 104.2 ms | 3.23 | — |
| q24 | 252.1 ms | 349.7 ms | 0.72 | 251.0 ms | 370.1 ms | 0.68 | 100.6 ms | 2.51 | — |
| q25 | 243.7 ms | 347.4 ms | 0.70 | 242.6 ms | 367.8 ms | 0.66 | 100.5 ms | 2.42 | — |
| q26 | 255.5 ms | 351.7 ms | 0.73 | 254.3 ms | 371.6 ms | 0.68 | 100.9 ms | 2.53 | — |
| q27 | 492.1 ms | 501.9 ms | 0.98 | 490.0 ms | 523.8 ms | 0.94 | 169.1 ms | 2.91 | **0.60 ms** |
| q28 | 2,829.1 ms | 4,030.8 ms | 0.70 | 2,817.4 ms | 4,039.0 ms | 0.70 | 1,057.0 ms | 2.68 | — |
| q29 | 757.2 ms | 852.2 ms | 0.89 | 754.1 ms | 871.6 ms | 0.87 | 336.3 ms | 2.25 | — |
| q30 | 273.0 ms | 362.4 ms | 0.75 | 271.8 ms | 382.1 ms | 0.71 | 353.7 ms | 0.77 | — |
| q31 | 278.2 ms | 385.5 ms | 0.72 | 276.8 ms | 406.5 ms | 0.68 | 375.7 ms | 0.74 | — |
| q32 | 412.8 ms | 917.0 ms | 0.45 | 410.7 ms | 935.4 ms | 0.44 | 905.7 ms | 0.46 | — |
| q33 | 433.9 ms | 479.2 ms | 0.91 | 431.7 ms | 498.1 ms | 0.87 | 461.8 ms | 0.94 | **38.73 ms** |
| q34 | 432.5 ms | 487.0 ms | 0.89 | 430.0 ms | 506.5 ms | 0.85 | 466.9 ms | 0.93 | **38.80 ms** |
| q35 | 278.7 ms | 396.7 ms | 0.70 | 277.3 ms | 416.7 ms | 0.67 | 156.4 ms | 1.78 | **4.33 ms** |
| q36 | 532.6 ms | 548.0 ms | 0.97 | 529.7 ms | 566.9 ms | 0.93 | 246.7 ms | 2.16 | — |
| q37 | 665.7 ms | 494.2 ms | 1.35 | 662.3 ms | 514.5 ms | 1.29 | 169.9 ms | 3.92 | — |
| q38 | 315.6 ms | 404.5 ms | 0.78 | 314.0 ms | 425.5 ms | 0.74 | 145.8 ms | 2.16 | — |
| q39 | 672.1 ms | 536.6 ms | 1.25 | 668.3 ms | 556.1 ms | 1.20 | 532.5 ms | 1.26 | — |
| q40 | 437.8 ms | 621.5 ms | 0.70 | 435.5 ms | 641.0 ms | 0.68 | 220.6 ms | 1.98 | — |
| q41 | 444.9 ms | 599.1 ms | 0.74 | 442.4 ms | 618.9 ms | 0.71 | 198.9 ms | 2.24 | — |
| q42 | 466.5 ms | 495.3 ms | 0.94 | 464.1 ms | 515.4 ms | 0.90 | 168.0 ms | 2.78 | **2.38 ms** |
| **sum** | **17,058.9 ms** | **22,362.9 ms** | **0.76** | **16,977.7 ms** | **23,217.8 ms** | **0.73** | **11,325.5 ms** | **1.51** | **11,798.8 ms** |
| **geomean** | | | **0.75** | | | **0.70** | | **1.65** | **0.10 / 0.23** |

Adding three optional hierarchical data skipping indexes on `hits` (`USING bloom_filter` on `UserID`, `USING ngrambf(3, 2048, 3)` on `URL` and `Title`) further accelerates selective point and substring-`LIKE` filters with exact output parity: `q19` drops from 173.2 → **42.6 ms** (4.07×), `q21` from 339.9 → **167.7 ms** (2.03×), `q23` from 331.7 → **168.7 ms** (1.97×), and `q22` from 620.1 → **485.4 ms** (1.28×), with zero OLTP write/read regression (1k inserts 303.9 vs 304.6 ms, 1k PK selects 44.4 vs 45.1 ms).

### Analytic queries

35 queries over 1M-row tables (scans, joins, groups, windows; median of 5).
The baseline columns (`LexDB`, `PG 1-core`, `PG 4-proc`) run strictly apples-to-apples with no materialized views:
LexDB's CPU is 0.48 of PostgreSQL's on one core (geometric mean; wall 0.59), and its wall time
0.95 of PostgreSQL's on four processes; 33 of 35 are level with or ahead of PostgreSQL on one core
on CPU (34 of 35 on wall time).

The rightmost column (`LexDB + MV`) runs the **exact same 35 unmodified queries** after creating four
general-purpose incremental `ENABLE QUERY REWRITE` rollup views (`mv_w_cube` 1,940 rows / 185 ms build,
`mv_w_join_d` 10 rows / 168 ms, `mv_w_join_cr` 17 rows / 133 ms, `mv_w_join_t` 1 row / 208 ms). Nine aggregate
and join-aggregate queries transparently rewrite onto those views with exact result parity, dropping from
8–95 ms to 3–4 ms (0–1 ms server CPU; the remaining ~3 ms is `psql` process startup), while non-matching
point lookups (`pk_point20k`: 649 vs 652 ms) incur zero rewrite overhead, bringing the 35-query
geometric mean to **0.30** against PG 1-core and **0.49** against PG 4-proc. After data load, inserting
1 / 100 / 1,000 new rows into `w` while keeping all four views live (`REFRESH FAST ON STATEMENT`) takes
**4.29 / 7.00 / 25.05 ms** (including `psql` startup and durable commit), whereas PostgreSQL 18 requires
**713.6 ms** (1-core) or **252.1 ms** (4-proc) to `REFRESH MATERIALIZED VIEW` all four views after any write.

| query | LexDB wall | PG 1-core wall | LexDB / PG1 | LexDB CPU | PG1 CPU | CPU ratio | PG 4-proc wall | LexDB / PG4 | LexDB + MV |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| `scan2` | 111 ms | 142 ms | 0.78 | 53 ms | 80 ms | 0.66 | 141 ms | 0.79 | 112 ms |
| `scan3` | 158 ms | 216 ms | 0.73 | 75 ms | 130 ms | 0.58 | 215 ms | 0.73 | 160 ms |
| `scan9` | 521 ms | 534 ms | 0.98 | 252 ms | 260 ms | 0.97 | 533 ms | 0.98 | 519 ms |
| `filt1pct` | 19 ms | 42 ms | 0.45 | 14 ms | 40 ms | 0.35 | 22 ms | 0.86 | 20 ms |
| `filt10pct` | 36 ms | 60 ms | 0.60 | 23 ms | 50 ms | 0.46 | 60 ms | 0.60 | 36 ms |
| `filt_like` | 55 ms | 82 ms | 0.67 | 50 ms | 80 ms | 0.62 | 32 ms | 1.72 | 55 ms |
| `filt_agg` | 21 ms | 46 ms | 0.46 | 17 ms | 50 ms | 0.34 | 23 ms | 0.91 | 21 ms |
| `expr_int` | 151 ms | 217 ms | 0.70 | 69 ms | 130 ms | 0.53 | 219 ms | 0.69 | 151 ms |
| `expr_mix` | 366 ms | 422 ms | 0.87 | 248 ms | 300 ms | 0.83 | 422 ms | 0.87 | 368 ms |
| `expr_agg` | 31 ms | 59 ms | 0.53 | 28 ms | 60 ms | 0.47 | 25 ms | 1.24 | **3 ms** |
| `sort_all` | 117 ms | 443 ms | 0.26 | 61 ms | 390 ms | 0.16 | 446 ms | 0.26 | 116 ms |
| `sort_lim` | 19 ms | 91 ms | 0.21 | 15 ms | 90 ms | 0.17 | 34 ms | 0.56 | 20 ms |
| `count` | 8 ms | 36 ms | 0.22 | 4 ms | 30 ms | 0.13 | 18 ms | 0.44 | **3 ms** |
| `grp_int` | 29 ms | 96 ms | 0.30 | 25 ms | 100 ms | 0.25 | 35 ms | 0.83 | **4 ms** |
| `grp_text` | 53 ms | 128 ms | 0.41 | 49 ms | 130 ms | 0.38 | 43 ms | 1.23 | **4 ms** |
| `minmax_text` | 55 ms | 129 ms | 0.43 | 51 ms | 130 ms | 0.39 | 43 ms | 1.28 | **3 ms** |
| `distinct` | 63 ms | 95 ms | 0.66 | 59 ms | 100 ms | 0.59 | 35 ms | 1.80 | 63 ms |
| `distinct2` | 136 ms | 112 ms | 1.21 | 131 ms | 110 ms | 1.19 | 41 ms | 3.32 | 134 ms |
| `idx_range1k` | 5 ms | 10 ms | 0.50 | 1 ms | 10 ms | 0.10 | 10 ms | 0.50 | 5 ms |
| `idx_range100k` | 47 ms | 46 ms | 1.02 | 34 ms | 40 ms | 0.85 | 47 ms | 1.00 | 47 ms |
| `idx_range_agg` | 30 ms | 29 ms | 1.03 | 26 ms | 30 ms | 0.87 | 25 ms | 1.20 | 30 ms |
| `pk_range100k` | 21 ms | 31 ms | 0.68 | 9 ms | 20 ms | 0.45 | 32 ms | 0.66 | 21 ms |
| `pk_point20k` | 652 ms | 621 ms | 1.05 | 605 ms | 410 ms | 1.48 | 640 ms | 1.02 | 649 ms |
| `join_hash_agg` | 38 ms | 98 ms | 0.39 | 34 ms | 100 ms | 0.34 | 36 ms | 1.06 | **3 ms** |
| `join_hash_rows` | 36 ms | 63 ms | 0.57 | 26 ms | 60 ms | 0.43 | 63 ms | 0.57 | 37 ms |
| `join_lookup_agg` | 74 ms | 78 ms | 0.95 | 70 ms | 80 ms | 0.88 | 32 ms | 2.31 | **3 ms** |
| `sub_in` | 25 ms | 51 ms | 0.49 | 21 ms | 50 ms | 0.42 | 24 ms | 1.04 | 25 ms |
| `sub_exists` | 25 ms | 51 ms | 0.49 | 21 ms | 50 ms | 0.42 | 24 ms | 1.04 | 25 ms |
| `sub_corr_sel` | 113 ms | 151 ms | 0.75 | 98 ms | 150 ms | 0.65 | 151 ms | 0.75 | 112 ms |
| `window` | 107 ms | 146 ms | 0.73 | 92 ms | 130 ms | 0.71 | 97 ms | 1.10 | 109 ms |
| `join_hash_sort` | 59 ms | 111 ms | 0.53 | 46 ms | 100 ms | 0.46 | 54 ms | 1.09 | 59 ms |
| `join_text_agg` | 58 ms | 87 ms | 0.67 | 54 ms | 90 ms | 0.60 | 32 ms | 1.81 | **3 ms** |
| `join_text_rows` | 70 ms | 87 ms | 0.80 | 58 ms | 80 ms | 0.72 | 89 ms | 0.79 | 70 ms |
| `join_text_group` | 95 ms | 171 ms | 0.56 | 91 ms | 170 ms | 0.54 | 54 ms | 1.76 | **3 ms** |
| `join_left_rows` | 32 ms | 56 ms | 0.57 | 18 ms | 40 ms | 0.45 | 55 ms | 0.58 | 31 ms |
| **geomean** | | | **0.59** | | | **0.48** | | **0.95** | **0.30 / 0.49** |

### Materialized views (1M rows)

Direct comparison against PostgreSQL 18 on a 1,000,000-row table (`ev`: 100 groups, 1,000 subgroups,
50,000 distinct user IDs), pinned to CPUs 0–3, `cpu-boost off`, server-side `psql \timing` (median of 5 for LexDB,
median of 3 for PG). PostgreSQL has only full `REFRESH MATERIALIZED VIEW [CONCURRENTLY]`, whereas LexDB maintains
views incrementally in $O(\Delta)$ (including composable HyperLogLog++ / t-digest sketches, cascading multi-level
DAGs, and sharded append-only `ON QUERY COMPUTATION` delta trees):

| workload (1M base rows) | Initial build (LexDB / PG) | LexDB `FAST` (1 / 100 / 1,000 rows) | PG 18 `REFRESH` (1-core) | PG 18 `REFRESH` (4-proc) | LexDB query rewrite (base → MV) |
|---|---:|---:|---:|---:|---:|
| Grouped rollup (`COUNT`, `SUM`, `AVG`, `MIN`, `MAX`) | **70.4** / 70.8 ms | **0.72 / 1.42 / 3.52 ms** | 147.4 ms | 60.3 ms (`CONCURRENTLY`: 60.1 ms) | 28.95 → **0.20 ms** (145×) |
| Sketch rollup (`APPROX_COUNT_DISTINCT` + `APPROX_PERCENTILE` vs PG `COUNT(DISTINCT)` + `PERCENTILE_CONT`) | **223.8** / 372.2 ms | **0.48 / 4.53 / 6.51 ms** | 363.6 ms | 363.9 ms | 239.0 → **0.53 ms** (451×) |
| 3-level cascading DAG (`ev → mv_l1 → mv_l2 → mv_l3`) | **43.3 ms** | **0.50 / 1.75 / 8.97 ms** | 141.5 ms | 142.0 ms | `mv_l3` read: **0.07 ms** |

Hot-key concurrent writes (16 clients × 100 durable autocommit `INSERT`s across 10 shared groups, `LEXDB_MV_FOLD=off`):

| mode | commits/s | errors | live read / fold |
|---|---:|---:|---|
| Plain table (no MV) | 27,639/s | 0 | — |
| `FAST ON STATEMENT` (synchronous in-place) | 19,649/s | 0 | base tree always folded |
| `ON QUERY COMPUTATION` (`refresh = 'realtime'` sharded delta tree) | 23,536/s | 0 | 1.88 ms merge-on-read; 7.10 ms `REFRESH FAST` fold (1,600 deltas) |

### Bulk loads

`\copy`, median of 3, not pinned:

| workload | LexDB | PostgreSQL 18 | LexDB / PG | LexDB peak RSS |
|---|---:|---:|---:|---:|
| narrow, 1M rows | 0.24 s | 0.64 s | 0.38 | 301 MB |
| wide, 1M rows | 1.04 s | 1.92 s | 0.54 | 619 MB |
| wide + 2 secondary indexes, 1M rows | 1.80 s | 4.93 s | 0.37 | 1,330 MB |
| wide, no primary key, 1M rows | 1.05 s | 1.54 s | 0.68 | 651 MB |
| narrow, 10M rows | 2.44 s | 5.78 s | 0.42 | 2,870 MB |

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
