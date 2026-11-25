# Lexell performance

Measured on 24–25 November 2026 (applications, LexDB and commands at `b28afb4c`; microbenchmarks
updated on `main` at `9614ce09` after the further compiler optimization series: single-pointer
immutable borrows for boxed records and closed types, forward consuming `for` loops, `const`
`cap == 0` string drop elision, `quietRt` inline float math, loop mask/shift range facts with
`MAX_FACTS = 256`, fused 2- and 4-byte little-endian loads, 8-arm exhaustive `match` jump tables,
and self-tail-call optimization, on top of the earlier `b28afb4c` series).
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
| Compile time | Rust | Much faster: about 3.6 times for hello world, about 24 times for nine programs |
| Microbenchmarks | Rust, Java, Go | Faster than Rust on ten of nineteen, level on two; faster than warmed-up Java on nine of twenty, level on one; task switching about 1.8 times Go's speed; 2–31 MB on nineteen of twenty against the JVM's 51 MB–2.4 GB |
| Regex | Go, Rust | Faster than Go on all; slower than Rust on six of seven |
| JSON | Python, jq | Faster to parse and write, slower to query; faster than jq on every filter (0.44 to 0.68 times jq 1.7.1) |
| Markdown | cmark | Slightly slower on long documents, faster on the spec examples |
| Decimal | Java, .NET | Faster than .NET on all but 19-digit add; slower than Java on division and comparison |
| HTTP server | Go net/http, Node.js | Faster at 1, 10 and 100 clients: about 1.5 times Go's requests a second, 1.2 to 1.3 times Node's |
| LexDB | PostgreSQL 18 | Faster on one core than PostgreSQL on one core in TPC-H (ahead of its four processes in total, 8.1 against 8.8 s), updates, and analytic queries (CPU 0.49 of one core, wall 0.98 of four processes); slower on point selects from one process at 8 and 32 clients |
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

Twenty programs, native `-O`, wall time, best of 5 (`bench/bench.py --opt`). The first ten are
the original set; `nbody` (floating point), `interp` (a stack machine: an enum with payloads run
by a match), `closures` (stable sorts with comparator closures, calls through an array of
functions), `matmul` (a 400 x 400 product over arrays of rows) and `pingpong` (two tasks handing
a counter back and forth 2,000,000 times) were added on 23 November; five LexDB-shaped kernels —
`bitpack` (columnar bit-packed integer decode, filter and multiply-sum), `btree` (in-memory
order-32 B-tree inserts, splits, lookups and range scans), `hashagg` (open-addressing columnar
hash aggregation with COUNT/SUM/MIN/MAX), `varint_csv` (delimited text parsing and LEB128 varint
encoding) and `enum_eval` (boxed closed-type SQL expression AST evaluation over columnar batches)
— were added on 25 November. `pingpong` has no Rust port
(Rust's lightweight tasks are an async runtime crate, and the ports use none); its Go port uses
goroutines and channels, its Java port virtual threads and a `SynchronousQueue`. The `maps` ports
use std `HashMap` (Rust, with its default SipHash) and `java.util.HashMap`, whose layouts differ
from Lexell's `Map` (insertion-ordered, with u32 index slots), so for `maps` the comparison is of
the same operations and keys, not the same data structure. Every port prints the same checksum.

| program | Lexell | Rust | Lexell / Rust | Java (warm) | Lexell / Java |
|---|---:|---:|---:|---:|---:|
| fib | 579 ms | 935 ms | 0.62 | 634 ms | 0.91 |
| loop | 416 ms | 419 ms | 0.99 | 497 ms | 0.84 |
| array | 345 ms | 349 ms | 0.99 | 281 ms | 1.23 |
| sieve | 306 ms | 484 ms | 0.63 | 533 ms | 0.57 |
| alloc | 35 ms | 364 ms | 0.10 | 29 ms | 1.21 |
| strings | 75 ms | 278 ms | 0.27 | 47 ms | 1.60 |
| lists | 87 ms | 504 ms | 0.17 | 64 ms | 1.35 |
| trees | 62 ms | 336 ms | 0.18 | 42 ms | 1.48 |
| tokens | 102 ms | 95 ms | 1.08 | 173 ms | 0.59 |
| maps | 355 ms | 660 ms | 0.54 | 282 ms | 1.26 |
| nbody | 249 ms | 163 ms | 1.53 | 249 ms | 1.00 |
| interp | 158 ms | 210 ms | 0.75 | 341 ms | 0.46 |
| closures | 106 ms | 64 ms | 1.66 | 187 ms | 0.57 |
| matmul | 102 ms | 148 ms | 0.69 | 31 ms | 3.27 |
| pingpong | 196 ms | - | - | 1,814 ms | 0.11 |
| bitpack | 444 ms | 347 ms | 1.28 | 589 ms | 0.75 |
| btree | 107 ms | 104 ms | 1.03 | 97 ms | 1.10 |
| hashagg | 166 ms | 130 ms | 1.28 | 126 ms | 1.31 |
| varint_csv | 77 ms | 81 ms | 0.96 | 105 ms | 0.74 |
| enum_eval | 159 ms | 134 ms | 1.19 | 118 ms | 1.35 |

Go runs `pingpong` in 360 ms (Lexell / Go 0.54), with its default threads or with one.

`alloc` runs about 35 ms: its records never escape, so neither Lexell nor the JVM
allocates them (`lexell/design/opt-experiments.md`, section 18), while Rust's `Box` does.

Peak resident memory of the same runs (the Java figure is the JVM's over its warm-up and timed
runs, with its default heap, which may grow to a quarter of RAM):

| program | Lexell | Rust | Java |
|---|---:|---:|---:|
| fib | 2.0 MB | 2.3 MB | 51 MB |
| loop | 2.0 MB | 2.2 MB | 51 MB |
| array | 9.5 MB | 9.9 MB | 205 MB |
| sieve | 12.0 MB | 11.8 MB | 325 MB |
| alloc | 2.0 MB | 2.3 MB | 71 MB |
| strings | 2.0 MB | 2.7 MB | 549 MB |
| lists | 2.1 MB | 2.7 MB | 537 MB |
| trees | 6.0 MB | 7.2 MB | 1,364 MB |
| tokens | 3.8 MB | 3.5 MB | 551 MB |
| maps | 180 MB | 208 MB | 2,370 MB |
| nbody | 2.0 MB | 2.3 MB | 53 MB |
| interp | 2.0 MB | 2.4 MB | 54 MB |
| closures | 13.7 MB | 21.9 MB | 164 MB |
| matmul | 4.0 MB | 5.7 MB | 93 MB |
| pingpong | 2.0 MB | - | 548 MB |
| bitpack | 31.2 MB | 28.3 MB | 246 MB |
| btree | 4.0 MB | 5.0 MB | 92 MB |
| hashagg | 27.8 MB | 26.2 MB | 233 MB |
| varint_csv | 5.2 MB | 5.2 MB | 376 MB |
| enum_eval | 18.0 MB | 17.5 MB | 134 MB |

Java's speed here does not depend on that memory. With its heap capped at 64 MB (`-Xmx64m`),
`lists`, `strings` and `trees` run in 60, 46 and 42 ms at a peak of 86 to 105 MB; at 16 MB they
run 10 to 45% slower. Where Java leads on the original ten, the work is per object: `lists`,
`trees` and `strings` allocate and free a node or string at a time. The JVM allocates by bumping
a pointer and its young-generation collector spends its time on the objects still live, so the
many that die young cost nothing to free: collection is about 1% of its time here, while Lexell
frees each node when its owner is dropped (section 22). Lexell's nodes are no larger: since an
`Option` of a box is a pointer (section 24), its `lists` and `trees` nodes are 16 and 24 bytes
with their headers, against Java's 24, and a tree's drop makes no call but the inline free
(section 26). What remains of Java's lead in `lists` is the recursive walk. `array` uses 4-byte `int` elements in Java against Lexell's 8-byte `int`.
`fib` is ahead of both because a recursive function is inlined into itself one level, as C2 does
(section 18).

The added programs found the generated code's weak cases, and the fixes are in
(`lexell/design/opt-experiments.md`, sections 20, 21, 23, 25 and 30, plus direct float memory
stores in `genAssign` and `0.0f` `fillLoop` at `615087ea`): `matmul` dropped from 148 ms to
98 ms and is now ahead of Rust (104 ms, 0.94), though Lexell still does not vectorise loops
as Java's C2 JIT does (30 ms). `nbody` is level with Java and 1.54 times Rust's, where LLVM
unrolls the loop over the five bodies and computes two pairs at a time with vector instructions.
Rust's `sort_by` is still ahead of `sortBy` in `closures`, which is ahead of Java's `List.sort`.
The interpreter loop (`interp`, 151 ms) is 26% ahead of Rust's (205 ms) and more than twice
Java's speed (327 ms). A task switch is Lexell's own: a round trip of two hand-overs takes 96 ns,
against Go's 185 ns over channels and 924 ns for Java's virtual threads in this run.

`tokens` uses views of the source (identifiers are `&str` slices, and the intern
table holds them), in all three languages, with the same output; at 102 ms it is within 8% of
Rust (95 ms) and ahead of Java (173 ms).

The five LexDB-shaped benchmarks added on 25 November exposed four specific native-backend gaps
that were closed in the same series (`9614ce09`): fused 2- and 4-byte little-endian loads cut
`bitpack` instructions by 42% (now 444 ms, 25% ahead of Java's 589 ms); raising `loops.lxl`'s
`MAX_FACTS` to 256 and tracking loop-invariant local masks (`h = (h + 1) & mask`) cut `hashagg`
instructions by 21.5% (166 ms, within 1.28× of Rust); and counting the exhaustive `else` arm in
`genChain` plus self-tail-call optimization cut `enum_eval` instructions by 23% (159 ms, within
1.19× of Rust). `varint_csv` (77 ms) is ahead of both Rust (81 ms) and Java (105 ms), and `btree`
(107 ms) is within 3% of Rust (104 ms) and 10% of Java (97 ms). On LexDB itself (`lexdb.lxl`), the
same compiler series shrank the binary by 573 KB (14.51 to 13.94 MB) and reduced TPC-H SF1
geometric mean query time by 1.27% (sum −0.64%, all 22 checksums unchanged).

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

TPC-H derived (22 queries, SF1, warm, median of 3, at a fixed clock with boost off; every result
checked against PostgreSQL's):

| | LexDB (one core) | PostgreSQL, one core | PostgreSQL, four processes |
|---|---:|---:|---:|
| all 22 queries, summed | 8,059 ms | 14,670 ms | 8,839 ms |
| geometric mean of LexDB / PostgreSQL (wall) | | 0.63 | 1.01 |
| queries level or ahead (within 10%) | | 20 of 22 | |

OLTP (pgbench, prepared statements over Unix sockets, 1M rows, median of three 10 s rounds):

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

Analytic queries (35 queries over 1M-row tables: scans, joins, groups, windows; median of 5):
LexDB's CPU is 0.49 of PostgreSQL's on one core (geometric mean), and its wall time 0.98 of
PostgreSQL's on four processes; 33 of 35 are level with or ahead of PostgreSQL on one core on
CPU (34 of 35 on wall time).

Bulk loads (`\copy`, median of 3, not pinned): LexDB is faster on narrow rows (1M: 0.48 against
0.61 s; 10M: 4.82 against 5.84 s), wide rows (1.40 against 2.15 s) and wide rows with two
secondary indexes (2.60 against 4.92 s), and slower with no primary key (1.75 against 1.39 s).

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
