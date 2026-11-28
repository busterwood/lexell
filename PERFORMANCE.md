# Lexell performance

Measured on 28 November 2026 on `main` at `0907ea85` (Markdown updated at `0907ea85`; HTTP/1.1 & HTTP/2 from `20b4f54f`; other sections from `ab29758c`).
Every number compares Lexell only with external tools.
Lexell's own C backend and earlier builds are not compared.
For LexDB database benchmarks against PostgreSQL 18, see [LEXDB.md](LEXDB.md) and the dedicated [LexDB performance report](lexell/docs/lexdb/performance.md).

Host: AMD Ryzen 7 8745HS (8 cores, 16 threads), 46 GB RAM, Linux 7.2 (Arch).
Versions: rustc and cargo 1.99.1, Go 1.27.3, Node.js 26.13.1, Java 21.0.13, .NET SDK 10.0.113, Python 3.14.8,
cmark 0.31.2, jq 1.7.1 (built from its tarball with `-O2`) and jq 1.8.2 from the system,
GNU grep, sort and tail, ripgrep, and eza 0.23.5 from the system.

Method: wall times are best of N; instruction counts are user-mode
`perf stat` instructions, the stable figure. Benchmark processes are pinned
(server CPUs 0-3, client CPUs 4-7 and 12-15). Lexell runs with
`LXL_HASH_SEED=42`. One benchmark ran at a time.

## Summary

| Area | Against | Result |
|---|---|---|
| Compile time | Rust | Much faster: about 3.0 times for hello world, about 18 times for nine programs |
| Microbenchmarks | Rust, Java, Go | Faster than Rust on fourteen of nineteen, level on one (`array` 3.8×, `matmul` 2.5×, `maps` 2.3×, `bitpack` 2.0× via explicit `vector[T]` SIMD); faster than warmed-up Java on ten of twenty, level on one; task switching about 1.8 times Go's speed; 2–31 MB on nineteen of twenty against the JVM's 51 MB–2.37 GB |
| Regex | Go, Rust | Faster than Go on all; slower than Rust on six of seven, 4.1 times faster on `(?m)^ERROR .*timeout$` |
| JSON | Python, jq | 3.3 times faster than Python to parse and 1.6–1.7 times faster to write, slower to query; 2.0 to 3.5 times faster than jq 1.7.1 on every filter |
| Markdown | cmark | Faster on repository Markdown (`0.97×`) and the spec examples (`0.93×`), slightly slower on the spec text (`1.08×`) |
| Decimal | Java, .NET | Faster than .NET on every operation (1.3 to 5.8 times); faster than Java on nine of ten (only slower on 19-digit cmp) |
| HTTP/1.1 server | Go net/http, Node.js | Faster at 1, 10 and 100 clients: 1.6 times Go's requests a second, 1.4 to 1.5 times Node's (up to 203k req/s on one core, 5.4× lower p99 than Go at 100 clients) |
| HTTP/2 server | Go net/http, Node.js | Faster than both Go and Node.js on every `h2c` and TLS case: 1.6 to 6.7 times Go and 1.1 to 3.5 times Node.js (up to 368k req/s `h2c` and 317k req/s TLS 1.3 on one core at 7–13 MB RSS) |
| LexDB | PostgreSQL 18 | Moved to its own pages: see [LEXDB.md](LEXDB.md) for the high-level summary and [lexell/docs/lexdb/performance.md](lexell/docs/lexdb/performance.md) for full TPC-H, ClickBench, analytic, OLTP, materialized view, property graph, and bulk load tables |
| Command-line tools | GNU grep, sort, tail, rg, eza | 1.9 times faster than GNU grep (and ahead of ripgrep with half the instructions) on `grep -c`, 1.4 times faster on `grep -o -w`, 1.6–3.5 times faster on `eza`, level on `tail`, slower on multi-threaded GNU `sort` |

## Compile time

Rust (rustc with cargo) is the reference here: it is the compiled-language toolchain that the microbenchmark ports use.

From `bench/compile.py -n 3`. The Rust toolchain sizes are missing: the sizing
step fails on a broken system symlink.

| case | Lexell | Rust |
|---|---:|---:|
| hello world, compile | 19.0 ms | 57.6 ms |
| hello world, binary | 22 KB | 330 KB |
| nine benchmark programs, clean compile | 187.1 ms | 3,360 ms |
| nine benchmark programs, binaries | 219 KB | 517 KB |

The compiler's own self-build takes 682 ms (no external reference; compiler binary 3.55 MB).

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
`array`, `matmul`, `bitpack`, and `collections.Map` (used by `maps`) use Lexell's built-in explicit
`vector[T]` AVX2 SIMD operations. `pingpong` has no Rust port (Rust's lightweight tasks are an async
runtime crate, and the ports use none); its Go port uses goroutines and channels, its Java port
virtual threads and a `SynchronousQueue`. The `maps` ports use std `HashMap` (Rust, with its default
SipHash) and `java.util.HashMap`, whose layouts differ from Lexell's `Map` (insertion-ordered, with
u32 index slots and 8-wide SIMD probing), so for `maps` the comparison is of the same operations and
keys, not the same data structure. Every port prints the same checksum.

| program | Lexell | Rust | Lexell / Rust | Java (warm) | Lexell / Java |
|---|---:|---:|---:|---:|---:|
| fib | 546 ms | 899 ms | 0.61 | 618 ms | 0.88 |
| loop | 407 ms | 407 ms | 1.00 | 516 ms | 0.79 |
| array | 90 ms | 340 ms | 0.27 | 273 ms | 0.33 |
| sieve | 252 ms | 439 ms | 0.57 | 510 ms | 0.49 |
| alloc | 33 ms | 350 ms | 0.09 | 27 ms | 1.22 |
| strings | 74 ms | 268 ms | 0.28 | 45 ms | 1.65 |
| lists | 83 ms | 484 ms | 0.17 | 58 ms | 1.43 |
| trees | 60 ms | 326 ms | 0.18 | 40 ms | 1.50 |
| tokens | 109 ms | 101 ms | 1.09 | 186 ms | 0.59 |
| maps | 281 ms | 640 ms | 0.44 | 265 ms | 1.06 |
| nbody | 241 ms | 160 ms | 1.51 | 241 ms | 1.00 |
| interp | 148 ms | 213 ms | 0.69 | 331 ms | 0.45 |
| closures | 106 ms | 63 ms | 1.69 | 164 ms | 0.65 |
| matmul | 55 ms | 140 ms | 0.39 | 31 ms | 1.77 |
| pingpong | 194 ms | - | - | 2,564 ms | 0.08 |
| bitpack | 163 ms | 334 ms | 0.49 | 568 ms | 0.29 |
| btree | 100 ms | 102 ms | 0.98 | 96 ms | 1.04 |
| hashagg | 147 ms | 125 ms | 1.18 | 122 ms | 1.21 |
| varint_csv | 75 ms | 78 ms | 0.96 | 103 ms | 0.73 |
| enum_eval | 120 ms | 130 ms | 0.92 | 108 ms | 1.11 |

Go runs `pingpong` in 349 ms (Lexell / Go 0.56), with its default threads or with one.

`alloc` runs about 33 ms: its records never escape, so neither Lexell nor the JVM
allocates them (`lexell/design/opt-experiments.md`, section 18), while Rust's `Box` does.

Peak resident memory of the same runs (the Java figure is the JVM's over its warm-up and timed
runs, with its default heap, which may grow to a quarter of RAM):

| program | Lexell | Rust | Java |
|---|---:|---:|---:|
| fib | 2.0 MB | 2.3 MB | 51.1 MB |
| loop | 2.0 MB | 2.3 MB | 50.6 MB |
| array | 9.6 MB | 9.9 MB | 205.5 MB |
| sieve | 12.0 MB | 11.8 MB | 325.0 MB |
| alloc | 2.0 MB | 2.3 MB | 68.9 MB |
| strings | 2.0 MB | 2.7 MB | 661.2 MB |
| lists | 2.2 MB | 2.5 MB | 747.1 MB |
| trees | 6.0 MB | 7.2 MB | 1,363.4 MB |
| tokens | 3.8 MB | 3.5 MB | 547.5 MB |
| maps | 162.8 MB | 207.8 MB | 2,368.0 MB |
| nbody | 2.0 MB | 2.3 MB | 52.5 MB |
| interp | 2.0 MB | 2.4 MB | 53.9 MB |
| closures | 12.9 MB | 21.5 MB | 161.3 MB |
| matmul | 4.0 MB | 5.6 MB | 92.5 MB |
| pingpong | 2.0 MB | - | 547.8 MB |
| bitpack | 31.2 MB | 28.3 MB | 245.8 MB |
| btree | 4.0 MB | 5.2 MB | 90.1 MB |
| hashagg | 27.8 MB | 26.2 MB | 232.4 MB |
| varint_csv | 5.0 MB | 5.2 MB | 376.4 MB |
| enum_eval | 18.0 MB | 17.4 MB | 134.3 MB |

Java's speed here does not depend on that memory. With its heap capped at 64 MB (`-Xmx64m`),
`lists`, `strings` and `trees` run in 60, 46 and 42 ms at a peak of 86 to 105 MB; at 16 MB they
run 10 to 45% slower. Where Java leads on the allocation-heavy programs (`lists`, `trees`,
`strings`), the work is per object: the JVM allocates by bumping a pointer and its
young-generation collector spends its time only on live objects, so short-lived objects cost
nothing to free, whereas Lexell frees each node when its owner is dropped. Lexell's nodes are no
larger: an `Option` of a box is a pointer, so its `lists` and `trees` nodes are 16 and 24 bytes
with their headers, against Java's 24.

With explicit `vector[T]` AVX2 kernels, `array` runs in 90 ms (3.8× faster than Rust's 340 ms and
3.0× faster than Java's 273 ms), `matmul` runs in 55 ms (2.5× faster than Rust's 140 ms, while
Java's C2 JIT reaches 31 ms), and `bitpack` runs in 163 ms (2.0× faster than Rust's 334 ms and
3.5× faster than Java's 568 ms). Vectorized `collections.Map` probing brings `maps` to 281 ms (2.3×
faster than Rust's 640 ms and within 6% of Java's 265 ms at 163 MB vs 2.37 GB RSS). On `nbody`
(241 ms), Lexell matches Java (241 ms) and is behind Rust (160 ms), where LLVM unrolls and
vectorises the pairwise force loop. Rust's `sort_by` leads on `closures` (63 vs 106 ms), while
Lexell is 1.55× faster than Java's `List.sort` (164 ms). `interp` (148 ms) is 1.44× faster than Rust
(213 ms) and 2.24× faster than Java (331 ms). In `pingpong`, a round trip of two task hand-overs
takes 97 ns in Lexell, against 175 ns over Go channels and 1,282 ns for Java virtual threads.
`tokens` uses `&str` views of the source in all three languages (109 ms vs Rust's 101 ms and Java's
186 ms).

On the five database-kernel benchmarks, Lexell leads both Rust and Java on `bitpack` (163 vs 334
and 568 ms) and `varint_csv` (75 vs 78 and 103 ms), leads Rust on `btree` (100 vs 102 ms; Java
96 ms) and `enum_eval` (120 vs 130 ms; Java 108 ms), and trails Rust and Java on `hashagg` (147 vs
125 and 122 ms).

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
| literal `Sherlock Holmes` | 0.09 ms | 0.41 ms | 0.07 ms | 0.22 | 1.29 |
| alternation `Sherlock\|Holmes\|Watson\|Irene` | 0.55 ms | 132.1 ms | 0.40 ms | 0.004 | 1.38 |
| `\w+` | 18.8 ms | 118.5 ms | 15.7 ms | 0.16 | 1.20 |
| `(?i)sherlock` | 0.52 ms | 69.6 ms | 0.43 ms | 0.007 | 1.21 |
| email | 0.09 ms | 75.2 ms | 0.08 ms | 0.001 | 1.13 |
| `(?m)^ERROR .*timeout$` | 0.14 ms | 30.3 ms | 0.57 ms | 0.005 | 0.25 |
| dates `(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})` | 2.17 ms | 67.6 ms | 1.22 ms | 0.032 | 1.78 |
| `(a*)*b` on 100 KB | below timer resolution | 3.18 ms | below timer resolution | | |

Against Rust, `email` (0.09 vs 0.08 ms) and `literal` (0.09 vs 0.07 ms) are within 0.02 ms
(the script's resolution), Lexell is 4.07× faster on `errors` (0.14 vs 0.57 ms), and Rust's
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
| parse | 252 ms | Python json 819 ms | 0.31 |
| compact output | 337 ms | Python json 579 ms | 0.58 |
| pretty output | 373 ms | Python json 615 ms | 0.61 |
| query (sum of qty) | 123 ms | Python json 42 ms | 2.93 |
| visit (eachItem) | 124 ms | Python json 42 ms | 2.94 |
| jq `.` | 660 ms | jq 1.7.1 2,290 ms | 0.29 |
| jq `-c .` | 600 ms | jq 1.7.1 2,010 ms | 0.30 |
| jq `length` | 370 ms | jq 1.7.1 1,040 ms | 0.36 |
| jq `[.[].items[].qty] \| add` | 490 ms | jq 1.7.1 1,290 ms | 0.38 |
| jq `map(select(...))` | 510 ms | jq 1.7.1 1,290 ms | 0.40 |
| jq `group_by(.address.city)` | 770 ms | jq 1.7.1 1,520 ms | 0.51 |

The jq times are rounded to 10 ms by the script. Lexell's jq takes 0.29 to 0.51
times jq 1.7.1's time (2.0 to 3.5× faster), with identical output on every filter. The query and
visit steps read values through `get()` and `eachItem`, which borrow, so they copy nothing.

### Markdown

cmark is the reference CommonMark implementation in C.

`tests/markdown.py --perf`, against cmark 0.31.2, wall time, best of 3.
The perf mode checks no output.

| input | Lexell | cmark | Lexell / cmark |
|---|---:|---:|---:|
| spec text, 49 times (10.0 MB) | 110 ms | 102 ms | 1.08 |
| repository Markdown, 2 times (15.5 MB) | 170 ms | 176 ms | 0.97 |
| spec examples, 643 times (10.0 MB) | 326 ms | 351 ms | 0.93 |

### Decimal

Java `BigDecimal` and .NET `System.Decimal` are the standard decimal types in those languages.

`bench/decimal/compare/run.sh`: the Lexell benchmarks (`decbench.lxl`, `decbench-big.lxl`,
native `-O`), the Java harness, and the .NET harness, nanoseconds per operation, on CPU 2.
Java is OpenJDK 21.0.13; .NET is SDK 10.0.113 (runtime 10.0.13), targeting net10.0.
The .NET harness has no 37- and 38-digit cases.

| operation | Lexell | .NET System.Decimal | Java BigDecimal | Lexell / .NET | Lexell / Java |
|---|---:|---:|---:|---:|---:|
| add, 19 digits | 7.5 ns | 10.9 ns | 13.3 ns | 0.69 | 0.57 |
| mul, 6 by 6 digits | 8.4 ns | 11.1 ns | 9.7 ns | 0.76 | 0.87 |
| div, 12 by 6, scale 2 | 10.9 ns | 63.2 ns | 11.4 ns | 0.17 | 0.95 |
| parse, 20 digits | 32.5 ns | 88.6 ns | 116.0 ns | 0.37 | 0.28 |
| format, 19 digits | 41.5 ns | 80.0 ns | 46.0 ns | 0.52 | 0.90 |
| cmp, 19 digits | 2.1 ns | 3.6 ns | 1.6 ns | 0.59 | 1.34 |
| add, 37 digits | 8.1 ns | not in harness | 15.3 ns | | 0.53 |
| mul, 19 digits | 13.1 ns | not in harness | 19.8 ns | | 0.66 |
| parse, 38 digits | 45.5 ns | not in harness | 212.2 ns | | 0.21 |
| format, 38 digits | 69.4 ns | not in harness | 245.9 ns | | 0.28 |

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
| 1 | 124,461 | 77,027 | 85,703 | 1.62 | 1.45 |
| 10 | 203,301 | 127,669 | 141,557 | 1.59 | 1.44 |
| 100 | 198,103 | 125,970 | 141,802 | 1.57 | 1.40 |

| at 100 clients | Lexell | Go | Node.js |
|---|---:|---:|---:|
| latency p50 | 489 µs | 747 µs | 687 µs |
| latency p99 | 510 µs | 2,738 µs | 847 µs |
| memory per idle connection | 19.6 KB | 20.4 KB | 13.8 KB |
| server RSS before the idle connections | 7 MB | 10 MB | 52 MB |
| server RSS after the load | 202 MB | 345 MB | 222 MB |

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
| 1 × 1 | 43,873 | 27,512 | 30,887 | 1.59 | 1.42 |
| 1 × 10 | 115,338 | 56,159 | 94,534 | 2.05 | 1.22 |
| 1 × 100 | 123,251 | 55,668 | 114,887 | 2.21 | 1.07 |
| 10 × 10 | 367,998 | 55,292 | 111,746 | 6.66 | 3.29 |

HTTPS HTTP/2 (TLS 1.3 ALPN `h2`):

| conns × streams | Lexell, req/s | Go, req/s | Node.js, req/s | Lexell / Go | Lexell / Node.js |
|---|---:|---:|---:|---:|---:|
| 1 × 1 | 42,712 | 26,566 | 27,739 | 1.61 | 1.54 |
| 1 × 10 | 124,851 | 52,792 | 77,991 | 2.36 | 1.60 |
| 1 × 100 | 128,775 | 52,483 | 105,812 | 2.45 | 1.22 |
| 10 × 10 | 317,074 | 52,278 | 89,478 | 6.07 | 3.54 |

Latency and server RSS at 10 × 10 (100 concurrent streams):

| at 10 × 10 | Lexell | Go | Node.js |
|---|---:|---:|---:|
| `h2c` latency p50 / p99 | 254 µs / 701 µs | 1,808 µs / 2,880 µs | 679 µs / 6,497 µs |
| `tls` latency p50 / p99 | 302 µs / 688 µs | 1,885 µs / 2,979 µs | 920 µs / 6,329 µs |
| `h2c` / `tls` server RSS | 6.9 MB / 12.6 MB | 16.3 MB / 17.1 MB | 161 MB / 160 MB |

## Commands

GNU grep, sort and tail, ripgrep (`rg`), and eza are the common tools for the same jobs.

The programs in `lexell/cmd`, built with `--native -O`, against the system tools. Wall time is
measured around each process (including `perf stat` wrapper), best of 5 interleaved rounds, with
`LC_ALL=C TZ=UTC` pinned to CPUs 4–7 and 12–15, stdout written to a temporary file. Instruction
counts are user-mode. GNU sort runs several threads. Every output is byte-identical to the system
tool's except `eza -l /usr/lib`, which differs on a single file with extended attributes where
eza 0.23.5 prints `@` and Lexell's eza does not.

| case | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| grep `-c omega`, 100 MB, wall | 50.9 ms | GNU grep 98.5 ms (rg 52.3 ms) | 0.52 (0.97 vs rg) |
| grep `-c omega`, instructions | 220 M | GNU grep 375 M (rg 434 M) | 0.59 (0.51 vs rg) |
| grep `-o -w eta`, 100 MB, wall | 254 ms | GNU grep 363 ms | 0.70 |
| grep `-o -w eta`, instructions | 3,351 M | GNU grep 4,063 M | 0.82 |
| sort, 100 MB, wall | 514 ms | GNU sort 336 ms | 1.53 |
| sort, instructions | 4,453 M | GNU sort 2,683 M | 1.66 |
| tail `-n 5`, 100 MB file, wall | 18.1 ms | GNU tail 18.3 ms | 0.99 (level) |
| eza `-T /usr/share`, wall | 335 ms | eza 0.23.5 1,178 ms | 0.28 |
| eza `-T /usr/share`, instructions | 874 M | eza 0.23.5 3,180 M | 0.27 |
| eza `-l /usr/lib`, wall | 34.7 ms | eza 0.23.5 55.6 ms | 0.62 |
| eza `-l /usr/lib`, instructions | 90.4 M | eza 0.23.5 188.1 M | 0.48 |

## Not measured

- **Rust toolchain sizes** in the compile table: the sizing step fails on a
  broken system symlink.
- **Plain C references** for the microbenchmarks are in the run's log but not in the table above.
- **HTTP client, tasks and database streaming.** Each needs its own
  references and runs.
