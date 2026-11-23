# Lexell performance

Measured on 22 and 23 November 2026 on `main`: the HTTP server section on 23 November at
5284326a, the microbenchmarks on 23 November at 22c30d63, the LexDB section on 23 November at 4506a2e8, the decimal section at 8fcae995, the JSON section at d08f41f5, the compile-time and regex sections at 236c8513, the others
at 86e20e87 (236c8513 with documentation only).
Every number compares Lexell only with external tools or databases.
Lexell's own C backend and earlier builds are not compared.

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
| Compile time | Rust | Much faster: about 3 times for hello world, about 23 times for nine programs |
| Microbenchmarks | Rust, Java, Go | Faster than Rust on seven of fourteen, level on two; faster than warmed-up Java on seven of fifteen; task switching about twice Go's speed; at most an eleventh of the JVM's memory |
| Regex | Go, Rust | Faster than Go on all; slower than Rust on five of seven |
| JSON | Python, jq | Faster to parse, slower to query; faster than jq on every filter |
| Markdown | cmark | Slightly slower |
| Decimal | Java, .NET | Faster than .NET on all but 19-digit add; slower than Java on division and comparison |
| HTTP server | Go net/http, Node.js | Faster at 1, 10 and 100 clients: about 1.5 times Go's requests a second, 1.2 to 1.3 times Node's |
| LexDB | PostgreSQL 18 | Faster on one core than PostgreSQL on one core in TPC-H (level with its four processes in total), point selects through replicas, updates, analytic queries; slower on point selects from one process at 8 and 32 clients, and on bulk loads into tables with secondary indexes or no key |
| Command-line tools | GNU grep, sort, tail, eza | Faster on grep and eza, slower on sort, level on tail |

## Compile time

Rust (rustc with cargo) is the reference here: it is the compiled-language toolchain that the microbenchmark ports use.

From `bench/compile.py -n 3`. The Rust toolchain sizes are missing: the sizing
step fails on a broken system symlink.

| case | Lexell | Rust |
|---|---:|---:|
| hello world, compile | 14.2 ms | 46.2 ms |
| hello world, binary | 20 KB | 330 KB |
| nine benchmark programs, clean compile | 131.3 ms | 3,050 ms |
| nine benchmark programs, binaries | 192 KB | 457 KB |

The compiler's own self-build takes 483 ms (no external reference).

## Microbenchmarks

Rust is the reference: the ports in `bench/rust` are built with `opt-level = 3`, thin LTO and one codegen unit, the strongest mainstream native reference for the same work.
Java is the managed-runtime reference: the ports in `bench/java/Bench.java` run on OpenJDK 21.0.13
(default tiered C1/C2), one JVM per program, timed inside the JVM as the best of 5 runs after a
warm-up run, so the JIT has compiled the hot code and JVM startup is not counted. Arithmetic
that Lexell checks for overflow uses `Math.addExact` and `multiplyExact` in Java.

Fifteen programs, native `-O`, wall time, best of 5 (`bench/bench.py --opt`). The first ten are
the original set; `nbody` (floating point), `interp` (a stack machine: an enum with payloads run
by a match), `closures` (stable sorts with comparator closures, calls through an array of
functions), `matmul` (a 400 x 400 product over arrays of rows) and `pingpong` (two tasks handing
a counter back and forth 2,000,000 times) were added on 23 November. `pingpong` has no Rust port
(Rust's lightweight tasks are an async runtime crate, and the ports use none); its Go port uses
goroutines and channels, its Java port virtual threads and a `SynchronousQueue`. The `maps` ports
use std `HashMap` (Rust, with its default SipHash) and `java.util.HashMap`, whose layouts differ
from Lexell's `Map` (insertion-ordered, with u32 index slots), so for `maps` the comparison is of
the same operations and keys, not the same data structure. Every port prints the same checksum.

| program | Lexell | Rust | Lexell / Rust | Java (warm) | Lexell / Java |
|---|---:|---:|---:|---:|---:|
| fib | 509 ms | 813 ms | 0.63 | 620 ms | 0.82 |
| loop | 407 ms | 407 ms | 1.00 | 458 ms | 0.89 |
| array | 332 ms | 338 ms | 0.98 | 273 ms | 1.22 |
| sieve | 290 ms | 384 ms | 0.76 | 510 ms | 0.57 |
| alloc | 34 ms | 347 ms | 0.10 | 27 ms | 1.25 |
| strings | 91 ms | 269 ms | 0.34 | 44 ms | 2.07 |
| lists | 110 ms | 456 ms | 0.24 | 58 ms | 1.90 |
| trees | 94 ms | 323 ms | 0.29 | 40 ms | 2.35 |
| tokens | 102 ms | 93 ms | 1.10 | 166 ms | 0.61 |
| maps | 333 ms | 629 ms | 0.53 | 262 ms | 1.27 |
| nbody | 250 ms | 159 ms | 1.57 | 242 ms | 1.03 |
| interp | 238 ms | 215 ms | 1.10 | 329 ms | 0.72 |
| closures | 104 ms | 62 ms | 1.68 | 153 ms | 0.68 |
| matmul | 157 ms | 104 ms | 1.51 | 29 ms | 5.42 |
| pingpong | 183 ms | - | - | 1,261 ms | 0.15 |

Go runs `pingpong` in 353 ms (Lexell / Go 0.52), with its default threads or with one.

A second run of the same build gave every ratio within 0.03 of these, except Java's `strings`
(2.02), `trees` (2.28), `matmul` (5.24) and `pingpong` (1,381 ms: 0.13), and Rust's `interp`
(1.16). `alloc` runs about 33 ms: its records never escape, so neither Lexell nor the JVM
allocates them (`lexell/design/opt-experiments.md`, section 18), while Rust's `Box` does.

Peak resident memory of the same runs (the Java figure is the JVM's over its warm-up and timed
runs, with its default heap, which may grow to a quarter of RAM):

| program | Lexell | Rust | Java |
|---|---:|---:|---:|
| fib | 2.0 MB | 2.2 MB | 51 MB |
| loop | 2.0 MB | 2.2 MB | 51 MB |
| array | 9.5 MB | 9.9 MB | 206 MB |
| sieve | 12.0 MB | 11.7 MB | 327 MB |
| alloc | 2.0 MB | 2.4 MB | 69 MB |
| strings | 2.0 MB | 2.6 MB | 549 MB |
| lists | 2.4 MB | 2.5 MB | 699 MB |
| trees | 8.0 MB | 7.1 MB | 1,364 MB |
| tokens | 3.8 MB | 3.4 MB | 547 MB |
| maps | 180 MB | 208 MB | 2,372 MB |
| nbody | 2.0 MB | 2.4 MB | 53 MB |
| interp | 2.0 MB | 2.3 MB | 54 MB |
| closures | 13.7 MB | 21.9 MB | 162 MB |
| matmul | 4.0 MB | 5.7 MB | 93 MB |
| pingpong | 2.0 MB | - | 545 MB |

Java's speed here does not depend on that memory. With its heap capped at 64 MB (`-Xmx64m`),
`lists`, `strings` and `trees` run in 60, 46 and 42 ms at a peak of 86 to 105 MB; at 16 MB they
run 10 to 45% slower. Where Java leads on the original ten, the work is per object: `lists`,
`trees` and `strings` allocate and free a node or string at a time. The JVM allocates by bumping
a pointer and its young-generation collector spends its time on the objects still live, so the
many that die young cost nothing to free: collection is about 1% of its time here, while freeing
each node when its owner is dropped is 18% of Lexell's `lists` and 35% of `trees`. Java's walks
over the nodes are also faster: its nodes are 24 bytes against Lexell's 32 and 48, where an
`Option` of a node is a tag and a pointer (section 22). `array` uses 4-byte `int` elements in Java against Lexell's 8-byte `int`.
`fib` is ahead of both because a recursive function is inlined into itself one level, as C2 does
(section 18).

The added programs found the generated code's weak cases, and the first fixes are in
(`lexell/design/opt-experiments.md`, sections 20 and 21: doubles computed in their registers,
elements as SSE operands, element addresses kept across stores; one string comparison in
`str.cmp`, a faster `sortBy`). `nbody` is within 4% of Java's time and 1.57 times Rust's: what
remains is copies between the compiler's temporaries. Lexell does not vectorise loops: Java's
JIT runs `matmul`'s inner loop with vector instructions (29 ms). Rust's `sort_by` is still ahead
of `sortBy` in `closures`, which is ahead of Java's `List.sort`. The interpreter loop is 10 to
16% behind Rust's over the two runs (a temporary of each arithmetic case kept in the frame) and
ahead of Java's pattern `switch`. A task switch is Lexell's own: a round trip of two hand-overs
takes 92 ns, against Go's 177 ns over channels and 630 to 690 ns for Java's virtual threads.

`tokens` uses views of the source (identifiers are `&str` slices, and the intern
table holds them), in all three languages, with the same output. The gap to Rust is in the
native code generator, not the program: the token list's header and the identifier
slices go through the stack frame where Rust keeps them in registers
(`lexell/design/opt-experiments.md`, section 14).

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
| alternation `Sherlock\|Holmes\|Watson\|Irene` | 0.60 ms | 133.6 ms | 0.42 ms | 0.004 | 1.43 |
| `\w+` | 19.8 ms | 122.0 ms | 16.1 ms | 0.16 | 1.23 |
| `(?i)sherlock` | 0.55 ms | 70.2 ms | 0.43 ms | 0.008 | 1.28 |
| email | 0.09 ms | 76.5 ms | 0.09 ms | 0.001 | 1.00 |
| `(?m)^ERROR .*timeout$` | 0.38 ms | 30.4 ms | 0.58 ms | 0.012 | 0.66 |
| dates `(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})` | 2.47 ms | 69.8 ms | 1.25 ms | 0.035 | 1.98 |
| `(a*)*b` on 100 KB | below timer resolution | 3.31 ms | below timer resolution | | |

Against Rust, the regex crate is faster on five patterns, email is level at the
script's 0.01 ms resolution, and Lexell is faster on `errors`; `(a*)*b` is below
timer resolution for both. A second run gave the same ratios within 0.05, except the
literal (3.0), whose Rust time of 0.07 ms is near the script's resolution.

Against Rust, the gap on `literal`, alternation and `(?i)sherlock` is probably on
the library side: the `regex` crate searches literals with SIMD `memchr` and
Teddy, and `regex.lxl` makes no SIMD call. The `\w+` and dates gaps are more
likely the native backend's code generation, the performance side. Neither is
profiled yet, so this split is a reading of the source, not a measurement.

### JSON

Python's `json` module and jq 1.7.1 are the common tools for parsing and filtering JSON.

`bench/json/bench.py --jq <jq 1.7.1>`, an 80.2 MB generated document. Library times are
best of 3, in-process; jq times are whole-process wall time, best of 3. Each
driver's output is identical (sha256 checked).

| step | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| parse | 381 ms | Python json 815 ms | 0.47 |
| compact output | 405 ms | Python json 587 ms | 0.69 |
| pretty output | 448 ms | Python json 617 ms | 0.73 |
| query (sum of qty) | 152 ms | Python json 45 ms | 3.4 |
| visit (eachItem) | 152 ms | Python json 45 ms | 3.4 |
| jq `.` | 1,010 ms | jq 1.7.1 2,220 ms | 0.45 |
| jq `-c .` | 930 ms | jq 1.7.1 1,970 ms | 0.47 |
| jq `length` | 630 ms | jq 1.7.1 990 ms | 0.64 |
| jq `[.[].items[].qty] \| add` | 770 ms | jq 1.7.1 1,240 ms | 0.62 |
| jq `map(select(...))` | 790 ms | jq 1.7.1 1,230 ms | 0.64 |
| jq `group_by(.address.city)` | 1,070 ms | jq 1.7.1 1,480 ms | 0.72 |

The jq times are rounded to 10 ms by the script. Lexell's jq takes 0.45 to 0.72
times jq 1.7.1's time, with identical output on every filter. jq 1.8.2, the system's
jq, is slower than 1.7.1 here: in a separate best-of-3 run of the same six filters
on the same data it took 1.08 to 1.17 times 1.7.1's time, also with identical output. The query and visit steps read values
through `get()` and `eachItem`, which borrow, so they copy nothing.

### Markdown

cmark is the reference CommonMark implementation in C.

`tests/markdown.py` perf mode, against cmark 0.31.2, wall time, best of 3.
The perf mode checks no output.

| input | Lexell | cmark | Lexell / cmark |
|---|---:|---:|---:|
| spec text, 49 times (10.0 MB) | 118 ms | 97 ms | 1.22 |
| repository Markdown, 3 times (13.9 MB) | 167 ms | 148 ms | 1.13 |
| spec examples, 643 times (10.0 MB) | 341 ms | 328 ms | 1.04 |

### Decimal

Java `BigDecimal` and .NET `System.Decimal` are the standard decimal types in those languages.

`bench/decimal/compare`: the Lexell benchmarks (`decbench.lxl`, `decbench-big.lxl`),
the Java harness, and the .NET harness, nanoseconds per operation, all from one run.
Java is OpenJDK 21.0.13; .NET is SDK 10.0.113 (runtime 10.0.13), targeting net10.0.
The .NET harness has no 37- and 38-digit cases.

| operation | Lexell | .NET System.Decimal | Java BigDecimal | Lexell / .NET | Lexell / Java |
|---|---:|---:|---:|---:|---:|
| add, 19 digits | 11.8 ns | 11.0 ns | 13.5 ns | 1.07 | 0.88 |
| mul, 6 by 6 digits | 9.0 ns | 11.2 ns | 9.9 ns | 0.81 | 0.91 |
| div, 12 by 6, scale 2 | 14.3 ns | 63.5 ns | 12.0 ns | 0.23 | 1.19 |
| parse, 20 digits | 33.3 ns | 89.3 ns | 114.0 ns | 0.37 | 0.29 |
| format, 19 digits | 44.6 ns | 75.2 ns | 46.1 ns | 0.59 | 0.97 |
| cmp, 19 digits | 2.2 ns | 3.6 ns | 1.6 ns | 0.61 | 1.39 |
| add, 37 digits | 11.8 ns | not in harness | 15.9 ns | | 0.74 |
| mul, 19 digits | 13.5 ns | not in harness | 19.9 ns | | 0.68 |
| parse, 38 digits | 47.5 ns | not in harness | 217.3 ns | | 0.22 |
| format, 38 digits | 74.1 ns | not in harness | 243.8 ns | | 0.30 |

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
The table is the second of two runs; the first agreed within 1% except Lexell
at 100 clients (144,440 requests a second, p99 2.0 ms), which the second did not
repeat.

| clients | Lexell, req/s | Go, req/s | Node.js, req/s | Lexell / Go | Lexell / Node.js |
|---:|---:|---:|---:|---:|---:|
| 1 | 107,663 | 72,155 | 83,689 | 1.49 | 1.29 |
| 10 | 178,337 | 117,085 | 141,524 | 1.52 | 1.26 |
| 100 | 171,917 | 114,310 | 141,374 | 1.50 | 1.22 |

| at 100 clients | Lexell | Go | Node.js |
|---|---:|---:|---:|
| latency p50 | 555 µs | 817 µs | 682 µs |
| latency p99 | 778 µs | 3,150 µs | 890 µs |
| memory per idle connection | 19.6 KB | 20.2 KB | 13.9 KB |
| server RSS before the idle connections | 7 MB | 10 MB | 52 MB |
| server RSS after the load | 199 MB | 343 MB | 224 MB |

## LexDB

PostgreSQL 18.6 is the reference: the same machine, data, disk and transport, both servers on
the same four physical cores (their SMT siblings idle) with the clients on the other four, and
PostgreSQL's parallel queries capped at four processes, LexDB's shape (a main process and three
replicas). Both are durable by default (PostgreSQL with `fsync` and `synchronous_commit` on).
The full record, the rules and the commands are in `lexell/design/lexdb-benchmarks.md`.

TPC-H derived (22 queries, SF1, warm, median of 3, at a fixed clock with boost off; every result
checked against PostgreSQL's):

| | LexDB (one core) | PostgreSQL, one core | PostgreSQL, four processes |
|---|---:|---:|---:|
| all 22 queries, summed | 8,943 ms | 14,610 ms | 8,818 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | 0.67 | 1.08 |
| queries level or ahead (within 10%) | | 17 of 22 | |

OLTP (pgbench, prepared statements over Unix sockets, 1M rows, median of three 10 s rounds):

| | LexDB | PostgreSQL | LexDB / PostgreSQL |
|---|---:|---:|---:|
| point selects, 1 client | 92,300/s | 82,100/s | 1.12 |
| point selects, 8 / 32 clients, one process | 164,800 / 160,100/s | 448,500 / 408,400/s | 0.37 / 0.39 |
| point selects, 32 clients, three read replicas | 434,000-439,000/s | 408,400/s | 1.07 |
| updates, 1 / 8 / 32 clients (a durable commit each) | 3,654 / 16,400 / 42,300/s | 1,644 / 6,735 / 26,260/s | 2.22 / 2.43 / 1.61 |

LexDB runs every session on one thread; it scales reads with replica processes, which follow the
master with a lag of 0.24-0.26 ms at the median and 0.49-0.55 ms at p99 under a mixed load. Its
commit latency with 8 clients is 0.44 ms at the median and 1.35-1.40 ms at p99.

Analytic queries (35 queries over 1M-row tables: scans, joins, groups, windows; median of 5):
LexDB's CPU is 0.54 of PostgreSQL's on one core (geometric mean), and its wall time 1.04 of
PostgreSQL's on four processes; 33 of 35 are level with or ahead of PostgreSQL on one core.

Bulk loads (`\copy`, median of 3, not pinned): LexDB is faster on narrow rows (1M: 0.46 against
0.59 s; 10M: 4.85 against 5.72 s) and wide rows (1.44 against 1.81 s), slower with two secondary
indexes (6.31 against 4.74 s) and with no primary key (2.98 against 1.52 s).

## Commands

GNU grep, sort and tail, and eza are the common tools for the same jobs.

The programs in `lexell/cmd`, built with the native backend (without `-O`), against the
system tools. Wall time is measured around each process, best of 5 rounds,
interleaved, with `LC_ALL=C` and the benchmark CPUs (4-7 and 12-15). Instruction
counts are user-mode. GNU sort runs several threads. The driver does not compare
outputs; they were compared separately. Every output is identical to the system tool's
except `eza -l`, which differs on one of 4,140 lines: eza 0.23.5 marks a file with
extended attributes with `@`, and Lexell's eza does not.

| case | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| grep `-c omega`, 100 MB, wall | 58 ms | GNU grep 88 ms | 0.66 |
| grep `-c omega`, instructions | 791 M | GNU grep 375 M | 2.1 |
| grep `-o -w eta`, 100 MB, wall | 253 ms | GNU grep 354 ms | 0.71 |
| grep `-o -w eta`, instructions | 3,861 M | GNU grep 4,063 M | 0.95 |
| sort, 100 MB, wall | 565 ms | GNU sort 249 ms | 2.3 |
| sort, instructions | 5,986 M | GNU sort 2,683 M | 2.2 |
| tail `-n 5`, 100 MB file, wall | 7 ms | GNU tail 8 ms | level (1 ms resolution) |
| eza `-T /usr/share`, wall | 201 ms | eza 0.23.5 664 ms | 0.30 |
| eza `-T /usr/share`, instructions | 1,404 M | eza 0.23.5 3,041 M | 0.46 |
| eza `-l /usr/lib`, wall | 25 ms | eza 0.23.5 35 ms | 0.71 |
| eza `-l /usr/lib`, instructions | 121 M | eza 0.23.5 187 M | 0.64 |

## Not measured

- **Rust toolchain sizes** in the compile table: the sizing step fails on a
  broken system symlink.
- **Plain C references** for the microbenchmarks are in the run's log but not in the table above.
- **ripgrep** in the command programs: not included.
- **HTTP client, TLS, tasks and database streaming.** Each needs its own
  references and runs.
- **SQL Server** against LexDB: its container was not running for this run.
- **Oracle** comparison: dropped for now, to be added back later.
