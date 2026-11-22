# Lexell performance

Measured on 22 November 2026 on `main`: the compile-time, microbenchmark and regex
sections at commit 236c8513, the JSON and decimal sections at d08f41f5, the others at
86e20e87 (236c8513 with documentation only).
Every number compares Lexell only with external tools or databases.
Lexell's own C backend and earlier builds are not compared.

Host: AMD Ryzen 7 8745HS (8 cores, 16 threads), 46 GB RAM, Linux 7.2 (Arch).
Versions: rustc and cargo 1.99.1, Go 1.27.3, Java 21.0.13, .NET SDK 10.0.113, Python 3.14.8,
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
| Microbenchmarks | Rust | Level or faster on nine of ten |
| Regex | Go, Rust | Faster than Go on all; slower than Rust on five of seven |
| JSON | Python, jq | Faster to parse, slower to query; faster than jq on every filter |
| Markdown | cmark | Slightly slower |
| Decimal | Java, .NET | Mixed |
| HTTP server | Go net/http | Faster at 1, 10 and 100 clients, about 1.5 times |
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

Ten programs, native `-O`, wall time, best of 5. All ten have a Rust port in
`bench/rust`. The `maps` port uses std `HashMap`, whose layout differs from Lexell's
`Map` (insertion-ordered, with u32 index slots), so for `maps` the comparison is of the
same operations and keys, not the same data structure. Both print the same checksum.

| program | Lexell | Rust | Lexell / Rust |
|---|---:|---:|---:|
| fib | 856 ms | 868 ms | 0.99 |
| loop | 422 ms | 424 ms | 0.99 |
| array | 346 ms | 354 ms | 0.98 |
| sieve | 301 ms | 452 ms | 0.67 |
| alloc | 263 ms | 348 ms | 0.76 |
| strings | 216 ms | 276 ms | 0.78 |
| lists | 189 ms | 481 ms | 0.39 |
| trees | 131 ms | 343 ms | 0.38 |
| tokens | 126 ms | 103 ms | 1.22 |
| maps | 357 ms | 651 ms | 0.55 |

A second run of the same build gave every ratio within 0.01 of these.

`tokens` uses views of the source (identifiers are `&str` slices, and the intern
table holds them), in both languages, with the same output. The same source
compiled through the C backend takes 105 ms, level with Rust (103 ms); over the
whole program the native backend executes about 1.2 times the instructions of the
C build. That gap is the native code generator's, not the program's; the native
backend's code for the scanning loop is the cause, and the work on it is tracked in
`lexell/design/codegen-audit.md`.

## Applications

### Regex

Go's `regexp` is the reference because Lexell's regex library is a port of it (`lib/regex.lxl`), with the same algorithms and semantics. Rust's `regex` crate is the other mature engine, and the one ripgrep uses.

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
The .NET SDK is 10.0.113. The repo's `DecBench.csproj` targets net8.0 and only the
.NET 10 runtime is installed, so the .NET program was built from a copy retargeted
to net10.0. The .NET harness has no 37- and 38-digit cases.

| operation | Lexell | .NET System.Decimal | Java BigDecimal | Lexell / .NET | Lexell / Java |
|---|---:|---:|---:|---:|---:|
| add, 19 digits | 11.7 ns | 10.9 ns | 13.9 ns | 1.08 | 0.84 |
| mul, 6 by 6 digits | 16.7 ns | 11.1 ns | 9.7 ns | 1.51 | 1.71 |
| div, 12 by 6, scale 2 | 22.7 ns | 63.1 ns | 11.4 ns | 0.36 | 1.99 |
| parse, 20 digits | 32.4 ns | 88.4 ns | 105.8 ns | 0.37 | 0.31 |
| format, 19 digits | 45.6 ns | 82.9 ns | 45.8 ns | 0.55 | 1.00 |
| cmp, 19 digits | 2.7 ns | 3.7 ns | 1.6 ns | 0.74 | 1.73 |
| add, 37 digits | 11.7 ns | not in harness | 16.0 ns | | 0.73 |
| mul, 19 digits | 18.6 ns | not in harness | 19.8 ns | | 0.94 |
| parse, 38 digits | 46.5 ns | not in harness | 216.0 ns | | 0.22 |
| format, 38 digits | 72.8 ns | not in harness | 239.9 ns | | 0.30 |

The outputs are not verified against each other. The harnesses print different
checksums for most cases, so those cases cannot be compared. The format cases print
the same checksum in Lexell and Java (the 19-digit format case also in .NET).

### HTTP server

Go's `net/http` is the reference: a plain server that answers `GET /` with the
same body as Lexell's `cmd/httpd.lxl` (native). The Go server runs with
`GOMAXPROCS=1`. The load client is `cmd/httpload.lxl`: one HTTP/1.1 keep-alive
connection per client, one request at a time, for 5 seconds each. Run by
`cmd/http_gate.py --servers native,go --conns 1,10,100 --seconds 5 --idle 10000`,
with 10,000 idle connections held open for the memory figures. The server is on
CPU 0 and the load client on CPU 1, the gate's pinning, not the CPU ranges above.

| clients | Lexell native, req/s | Go, req/s | Lexell / Go |
|---:|---:|---:|---:|
| 1 | 107,516 | 72,305 | 1.49 |
| 10 | 177,822 | 118,543 | 1.50 |
| 100 | 173,043 | 116,162 | 1.49 |

At 100 clients the p50 latency is 557 µs for Lexell and 806 µs for Go, and the
p99 is 585 µs and 3,024 µs. The memory per idle connection is 19.6 KB for Lexell
and 20.4 KB for Go. After the load, the server's RSS is 199 MB for Lexell and
341 MB for Go.

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
- **HTTP client, TLS, tasks, database streaming, and LexDB.** Each
  needs its own references and runs; LexDB has its own document,
  `lexell/design/lexdb-benchmarks.md`, which is to be redone.
- **Oracle** comparison: dropped for now, to be added back later.
