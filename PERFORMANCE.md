# Lexell performance

Measured on 27 November 2026 on `main` at `4565eaaf`.
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
| Compile time | Rust | Much faster: about 4.1 times for hello world, about 26 times for nine programs |
| Microbenchmarks | Rust, Java, Go | Faster than Rust on twelve of nineteen, level on two; faster than warmed-up Java on eleven of twenty, level on one; task switching about 1.8 times Go's speed; 2–31 MB on nineteen of twenty against the JVM's 50 MB–2.14 GB |
| Regex | Go, Rust | Faster than Go on all; slower than Rust on six of seven, 3.8 times faster on `(?m)^ERROR .*timeout$` |
| JSON | Python, jq | 2.9 times faster than Python to parse and 1.5 times faster to write, slower to query; 1.8 to 3.1 times faster than jq 1.7.1 on every filter |
| Markdown | cmark | Faster on repository Markdown and the spec examples, slightly slower on the spec text |
| Decimal | Java, .NET | Faster than .NET on every operation (1.3 to 5.8 times); faster than Java on nine of ten (only slower on 19-digit cmp) |
| HTTP/1.1 server | Go net/http, Node.js | Faster at 1, 10 and 100 clients: 1.7 to 2.1 times Go's requests a second, 1.2 to 1.3 times Node's |
| HTTP/2 server | Go net/http, Node.js | Faster than Go on all `h2c` and TLS cases (1.5 to 5.4 times); faster than Node.js on all `h2c` cases (1.2 to 2.4 times) and multi-connection TLS (2.2 times, 181k req/s on one core), slightly behind Node.js on single-connection TLS at 100 streams (0.90 times, with 2.4 times lower p99) |
| LexDB | PostgreSQL 18 | Moved to its own pages: see [LEXDB.md](LEXDB.md) for the high-level summary and [lexell/docs/lexdb/performance.md](lexell/docs/lexdb/performance.md) for full TPC-H, ClickBench, analytic, OLTP, materialized view, and bulk load tables |
| Command-line tools | GNU grep, sort, tail, eza | 2.6 times faster on `grep -c`, faster on `grep -o -w` and eza, slower on sort, level on tail |

## Compile time

Rust (rustc with cargo) is the reference here: it is the compiled-language toolchain that the microbenchmark ports use.

From `bench/compile.py -n 3`. The Rust toolchain sizes are missing: the sizing
step fails on a broken system symlink.

| case | Lexell | Rust |
|---|---:|---:|
| hello world, compile | 14.4 ms | 58.9 ms |
| hello world, binary | 22 KB | 330 KB |
| nine benchmark programs, clean compile | 139.5 ms | 3,580 ms |
| nine benchmark programs, binaries | 219 KB | 517 KB |

The compiler's own self-build takes 585 ms (no external reference).

## Microbenchmarks

Rust is the reference: the ports in `bench/rust` are built with `opt-level = 3`, thin LTO and one codegen unit, the strongest mainstream native reference for the same work.
Java is the managed-runtime reference: the ports in `bench/java/Bench.java` run on OpenJDK 21.0.13
(default tiered C1/C2), one JVM per program, timed inside the JVM as the best of 5 runs after a
warm-up run, so the JIT has compiled the hot code and JVM startup is not counted, with a 64 MB
thread stack (`-Xss64m`) for the 10,000-deep recursion of `lists`. Arithmetic
that Lexell checks for overflow uses `Math.addExact` and `multiplyExact` in Java.

Twenty programs, native `-O`, wall time, best of 5 (`bench/bench.py --opt -n 5`): `fib`, `loop`,
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
| fib | 584 ms | 960 ms | 0.61 | 652 ms | 0.90 |
| loop | 430 ms | 431 ms | 1.00 | 486 ms | 0.89 |
| array | 265 ms | 356 ms | 0.74 | 287 ms | 0.92 |
| sieve | 308 ms | 466 ms | 0.66 | 543 ms | 0.57 |
| alloc | 35 ms | 376 ms | 0.09 | 29 ms | 1.19 |
| strings | 78 ms | 281 ms | 0.28 | 46 ms | 1.69 |
| lists | 88 ms | 513 ms | 0.17 | 60 ms | 1.47 |
| trees | 63 ms | 343 ms | 0.18 | 43 ms | 1.46 |
| tokens | 105 ms | 96 ms | 1.09 | 176 ms | 0.60 |
| maps | 329 ms | 664 ms | 0.50 | 266 ms | 1.24 |
| nbody | 255 ms | 168 ms | 1.52 | 256 ms | 1.00 |
| interp | 163 ms | 223 ms | 0.73 | 345 ms | 0.47 |
| closures | 109 ms | 64 ms | 1.72 | 171 ms | 0.64 |
| matmul | 92 ms | 146 ms | 0.63 | 31 ms | 2.96 |
| pingpong | 203 ms | - | - | 1,574 ms | 0.13 |
| bitpack | 413 ms | 353 ms | 1.17 | 642 ms | 0.64 |
| btree | 106 ms | 107 ms | 0.99 | 102 ms | 1.04 |
| hashagg | 158 ms | 134 ms | 1.18 | 128 ms | 1.24 |
| varint_csv | 78 ms | 81 ms | 0.96 | 108 ms | 0.72 |
| enum_eval | 121 ms | 137 ms | 0.88 | 125 ms | 0.97 |

Go runs `pingpong` in 367 ms (Lexell / Go 0.55), with its default threads or with one.

`alloc` runs about 35 ms: its records never escape, so neither Lexell nor the JVM
allocates them (`lexell/design/opt-experiments.md`, section 18), while Rust's `Box` does.

Peak resident memory of the same runs (the Java figure is the JVM's over its warm-up and timed
runs, with its default heap, which may grow to a quarter of RAM):

| program | Lexell | Rust | Java |
|---|---:|---:|---:|
| fib | 2.0 MB | 2.3 MB | 51 MB |
| loop | 2.0 MB | 2.3 MB | 51 MB |
| array | 9.7 MB | 10.1 MB | 206 MB |
| sieve | 12.0 MB | 11.9 MB | 327 MB |
| alloc | 2.0 MB | 2.1 MB | 67 MB |
| strings | 2.0 MB | 2.8 MB | 648 MB |
| lists | 2.2 MB | 2.7 MB | 537 MB |
| trees | 6.0 MB | 7.2 MB | 1,404 MB |
| tokens | 3.8 MB | 3.4 MB | 549 MB |
| maps | 180 MB | 208 MB | 2,135 MB |
| nbody | 2.0 MB | 2.2 MB | 50 MB |
| interp | 2.0 MB | 2.3 MB | 54 MB |
| closures | 13.0 MB | 22.3 MB | 155 MB |
| matmul | 4.0 MB | 5.7 MB | 92 MB |
| pingpong | 2.0 MB | - | 542 MB |
| bitpack | 31.2 MB | 28.3 MB | 245 MB |
| btree | 4.0 MB | 5.1 MB | 91 MB |
| hashagg | 27.8 MB | 26.2 MB | 233 MB |
| varint_csv | 5.2 MB | 5.2 MB | 399 MB |
| enum_eval | 18.0 MB | 17.5 MB | 134 MB |

Java's speed here does not depend on that memory. With its heap capped at 64 MB (`-Xmx64m`),
`lists`, `strings` and `trees` run in 60, 46 and 42 ms at a peak of 86 to 105 MB; at 16 MB they
run 10 to 45% slower. Where Java leads on the allocation-heavy programs (`lists`, `trees`,
`strings`), the work is per object: the JVM allocates by bumping a pointer and its
young-generation collector spends its time only on live objects, so short-lived objects cost
nothing to free, whereas Lexell frees each node when its owner is dropped. Lexell's nodes are no
larger: an `Option` of a box is a pointer, so its `lists` and `trees` nodes are 16 and 24 bytes
with their headers, against Java's 24.

On `matmul` (92 ms), Lexell is 1.59× faster than Rust (146 ms), while Java's C2 JIT auto-vectorises
the inner loop (31 ms). On `nbody` (255 ms), Lexell matches Java (256 ms) and is behind Rust
(168 ms), where LLVM unrolls and vectorises the pairwise force loop. Rust's `sort_by` leads on
`closures` (64 vs 109 ms), while Lexell is 1.57× faster than Java's `List.sort` (171 ms). `interp` (163 ms)
is 27% ahead of Rust (223 ms) and more than twice Java's speed (345 ms). In `pingpong`, a round
trip of two task hand-overs takes 102 ns in Lexell, against 184 ns over Go channels and 787 ns for
Java virtual threads. `tokens` uses `&str` views of the source in all three languages (105 ms vs
Rust's 96 ms and Java's 176 ms).

On the five database-kernel benchmarks, Lexell leads both Rust and Java on `varint_csv` (78 vs 81
and 108 ms) and `enum_eval` (121 vs 137 and 125 ms), leads Java on `bitpack` (413 vs 642 ms),
matches Rust on `btree` (106 vs 107 ms; Java 102 ms), and trails Rust and Java on `hashagg` (158 vs
134 and 128 ms).

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
| literal `Sherlock Holmes` | 0.09 ms | 0.43 ms | 0.08 ms | 0.21 | 1.13 |
| alternation `Sherlock\|Holmes\|Watson\|Irene` | 0.58 ms | 140.2 ms | 0.43 ms | 0.004 | 1.35 |
| `\w+` | 20.3 ms | 132.3 ms | 17.2 ms | 0.15 | 1.18 |
| `(?i)sherlock` | 0.56 ms | 74.2 ms | 0.45 ms | 0.008 | 1.24 |
| email | 0.10 ms | 81.1 ms | 0.09 ms | 0.001 | 1.11 |
| `(?m)^ERROR .*timeout$` | 0.16 ms | 32.5 ms | 0.60 ms | 0.005 | 0.27 |
| dates `(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})` | 2.23 ms | 74.9 ms | 1.27 ms | 0.030 | 1.76 |
| `(a*)*b` on 100 KB | below timer resolution | 3.32 ms | below timer resolution | | |

Against Rust, `literal` (0.09 vs 0.08 ms) and `email` (0.10 vs 0.09 ms) are within 0.01 ms
(the script's resolution), Lexell is 3.75× faster on `errors` (0.16 vs 0.60 ms), and Rust's
`regex` crate leads on the remaining four patterns; `(a*)*b` is below timer resolution for both.

Against Rust, the remaining gap on alternation, `(?i)sherlock` and `dates` is on
the library side: Lexell uses AVX2/SSE2 runtime string search (`strFind`, `strFindPair`, `strFindByte`),
while Rust's `regex` crate adds multi-literal Teddy prefilters and specialized capture DFAs.

### JSON

Python's `json` module and jq 1.7.1 are the common tools for parsing and filtering JSON.

`bench/json/bench.py --no-c --jq <jq 1.7.1>`, an 80.2 MB generated document. Library times are
best of 3, in-process; jq times are whole-process wall time, best of 3. Each
driver's output is identical (sha256 checked).

| step | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| parse | 330 ms | Python json 946 ms | 0.35 |
| compact output | 428 ms | Python json 640 ms | 0.67 |
| pretty output | 465 ms | Python json 677 ms | 0.69 |
| query (sum of qty) | 141 ms | Python json 52 ms | 2.7 |
| visit (eachItem) | 146 ms | Python json 52 ms | 2.8 |
| jq `.` | 810 ms | jq 1.7.1 2,520 ms | 0.32 |
| jq `-c .` | 750 ms | jq 1.7.1 2,210 ms | 0.34 |
| jq `length` | 450 ms | jq 1.7.1 1,130 ms | 0.40 |
| jq `[.[].items[].qty] \| add` | 620 ms | jq 1.7.1 1,430 ms | 0.43 |
| jq `map(select(...))` | 650 ms | jq 1.7.1 1,410 ms | 0.46 |
| jq `group_by(.address.city)` | 970 ms | jq 1.7.1 1,700 ms | 0.57 |

The jq times are rounded to 10 ms by the script. Lexell's jq takes 0.32 to 0.57
times jq 1.7.1's time (1.8 to 3.1× faster), with identical output on every filter. The query and
visit steps read values through `get()` and `eachItem`, which borrow, so they copy nothing.

### Markdown

cmark is the reference CommonMark implementation in C.

`tests/markdown.py --perf`, against cmark 0.31.2, wall time, best of 3.
The perf mode checks no output.

| input | Lexell | cmark | Lexell / cmark |
|---|---:|---:|---:|
| spec text, 49 times (10.0 MB) | 124 ms | 108 ms | 1.15 |
| repository Markdown, 2 times (15.4 MB) | 183 ms | 191 ms | 0.96 |
| spec examples, 643 times (10.0 MB) | 355 ms | 391 ms | 0.91 |

### Decimal

Java `BigDecimal` and .NET `System.Decimal` are the standard decimal types in those languages.

`bench/decimal/compare/run.sh`: the Lexell benchmarks (`decbench.lxl`, `decbench-big.lxl`,
native `-O`), the Java harness, and the .NET harness, nanoseconds per operation, on CPU 2.
Java is OpenJDK 21.0.13; .NET is SDK 10.0.113 (runtime 10.0.13), targeting net10.0.
The .NET harness has no 37- and 38-digit cases.

| operation | Lexell | .NET System.Decimal | Java BigDecimal | Lexell / .NET | Lexell / Java |
|---|---:|---:|---:|---:|---:|
| add, 19 digits | 8.0 ns | 11.5 ns | 14.8 ns | 0.69 | 0.54 |
| mul, 6 by 6 digits | 9.0 ns | 11.9 ns | 10.8 ns | 0.76 | 0.83 |
| div, 12 by 6, scale 2 | 11.8 ns | 68.4 ns | 13.3 ns | 0.17 | 0.89 |
| parse, 20 digits | 34.8 ns | 95.0 ns | 114.5 ns | 0.37 | 0.30 |
| format, 19 digits | 46.0 ns | 84.9 ns | 48.3 ns | 0.54 | 0.95 |
| cmp, 19 digits | 2.3 ns | 3.8 ns | 1.7 ns | 0.60 | 1.37 |
| add, 37 digits | 8.8 ns | not in harness | 17.9 ns | | 0.49 |
| mul, 19 digits | 14.3 ns | not in harness | 22.5 ns | | 0.64 |
| parse, 38 digits | 49.3 ns | not in harness | 223.0 ns | | 0.22 |
| format, 38 digits | 74.6 ns | not in harness | 269.8 ns | | 0.28 |

The outputs are not verified against each other. The harnesses print different
checksums for most cases, so those cases cannot be compared. The format cases print
the same checksum in Lexell and Java (the 19-digit format case also in .NET).

### HTTP/1.1 server

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
| 1 | 108,862 | 56,471 | 83,952 | 1.93 | 1.30 |
| 10 | 182,352 | 89,036 | 142,298 | 2.05 | 1.28 |
| 100 | 167,432 | 99,813 | 139,947 | 1.68 | 1.20 |

| at 100 clients | Lexell | Go | Node.js |
|---|---:|---:|---:|
| latency p50 | 549 µs | 909 µs | 680 µs |
| latency p99 | 1,242 µs | 3,866 µs | 1,028 µs |
| memory per idle connection | 19.6 KB | 20.4 KB | 14.0 KB |
| server RSS before the idle connections | 7 MB | 8 MB | 52 MB |
| server RSS after the load | 199 MB | 343 MB | 224 MB |

### HTTP/2 server

Go's `net/http` (built-in HTTP/2) and Node.js's `http2` module (nghttp2 + OpenSSL) are the
references: each answers `GET /` with `"hello, world\n"` (`text/plain`) on one core (CPU 0;
Lexell native `-O`, Go `GOMAXPROCS=1`, Node.js single process). A neutral Go HTTP/2 load
client runs on CPUs 4–7 and 12–15 (`GOMAXPROCS=8`) for 5 seconds per case, with `C`
connections and `S` concurrent multiplexed streams per connection (`CxS`), verifying
HTTP/2 status 200 and body length 13 on every reply (zero errors across all runs). Run by
`cmd/http2_bench.py --servers lexell,go,node --modes h2c,tls --cases 1x1,1x10,1x100,10x10 --seconds 5`.

Cleartext HTTP/2 prior knowledge (`h2c`):

| conns × streams | Lexell, req/s | Go, req/s | Node.js, req/s | Lexell / Go | Lexell / Node.js |
|---|---:|---:|---:|---:|---:|
| 1 × 1 | 40,474 | 22,638 | 22,130 | 1.79 | 1.83 |
| 1 × 10 | 87,356 | 42,704 | 70,990 | 2.05 | 1.23 |
| 1 × 100 | 97,055 | 43,295 | 81,306 | 2.24 | 1.19 |
| 10 × 10 | 235,055 | 43,828 | 99,827 | 5.36 | 2.35 |

HTTPS HTTP/2 (TLS 1.3 ALPN `h2`):

| conns × streams | Lexell, req/s | Go, req/s | Node.js, req/s | Lexell / Go | Lexell / Node.js |
|---|---:|---:|---:|---:|---:|
| 1 × 1 | 29,839 | 19,405 | 21,340 | 1.54 | 1.40 |
| 1 × 10 | 64,723 | 43,715 | 65,378 | 1.48 | 0.99 |
| 1 × 100 | 77,634 | 46,178 | 86,141 | 1.68 | 0.90 |
| 10 × 10 | 180,662 | 44,560 | 82,215 | 4.05 | 2.20 |

Latency and server RSS at 10 × 10 (100 concurrent streams):

| at 10 × 10 | Lexell | Go | Node.js |
|---|---:|---:|---:|
| `h2c` latency p50 / p99 | 404 µs / 952 µs | 2,218 µs / 4,294 µs | 721 µs / 7,306 µs |
| `tls` latency p50 / p99 | 496 µs / 1,725 µs | 2,211 µs / 4,040 µs | 938 µs / 6,834 µs |
| `h2c` / `tls` server RSS | 6.9 MB / 12.5 MB | 16.5 MB / 17.1 MB | 155 MB / 159 MB |

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
| grep `-c omega`, 100 MB, wall | 31 ms | GNU grep 81 ms | 0.38 |
| grep `-c omega`, instructions | 204 M | GNU grep 364 M | 0.56 |
| grep `-o -w eta`, 100 MB, wall | 219 ms | GNU grep 312 ms | 0.70 |
| grep `-o -w eta`, instructions | 3,104 M | GNU grep 3,483 M | 0.89 |
| sort, 100 MB, wall | 213 ms | GNU sort 166 ms | 1.28 |
| sort, instructions | 3,929 M | GNU sort 2,136 M | 1.84 |
| tail `-n 5`, 100 MB file, wall | 1 ms | GNU tail 1 ms | level (1 ms resolution) |
| eza `-T /usr/share`, wall | 313 ms | eza 0.23.5 1,127 ms | 0.28 |
| eza `-T /usr/share`, instructions | 1,058 M | eza 0.23.5 3,185 M | 0.33 |
| eza `-l /usr/lib`, wall | 17 ms | eza 0.23.5 37 ms | 0.46 |
| eza `-l /usr/lib`, instructions | 109 M | eza 0.23.5 188 M | 0.58 |

## Not measured

- **Rust toolchain sizes** in the compile table: the sizing step fails on a
  broken system symlink.
- **Plain C references** for the microbenchmarks are in the run's log but not in the table above.
- **ripgrep** in the command programs: not included.
- **HTTP client, tasks and database streaming.** Each needs its own
  references and runs.
