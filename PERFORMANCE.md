# Lexell performance

Measured on 19 November 2026 on `main` at commit 0f326631. Every number here is from that build and
compares Lexell only with external tools or databases. Lexell's own C backend
and earlier builds are not compared.

Host: AMD Ryzen 7 8745HS (8 cores, 16 threads), 46 GB RAM, Linux 7.2 (Arch).
Versions: rustc and cargo 1.99.1, Go 1.27.3, Java 21.0.13, Python 3.14.8,
cmark 0.31.2, jq 1.7.1 (built from its tarball; the 1.7.1 binary was used, not the system jq 1.8.2), GNU grep and sort from the system.

Method: wall times are best of N; instruction counts are user-mode
`perf stat` instructions, the stable figure. Benchmark processes are pinned
(server CPUs 0-3, client CPUs 4-7 and 12-15). Lexell runs with
`LXL_HASH_SEED=42`. One benchmark ran at a time.

## Summary

| Area | Against | Result |
|---|---|---|
| Compile time | Rust | Much faster: about 3 times for hello world, about 20 times for nine programs |
| Microbenchmarks | Rust | Level or faster on nine of ten |
| Regex | Go, Rust | Faster than Go on all; slower than Rust on most |
| JSON | Python, jq | Faster to parse, slower to query; level with jq |
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
| hello world, compile | 15 ms | 49.5 ms |
| hello world, binary | 20 KB | 330 KB |
| nine benchmark programs, clean compile | 132 ms | 2,860 ms |
| nine benchmark programs, binaries | 200 KB | 430 KB |

The compiler's own self-build takes 473 ms (no external reference).

## Microbenchmarks

Rust is the reference: the ports in `bench/rust` are built with `opt-level = 3`, thin LTO and one codegen unit, the strongest mainstream native reference for the same work.

Ten programs, native `-O`, wall time, best of 5. All ten have a Rust port in
`bench/rust`. The `maps` port uses std `HashMap`, whose layout differs from Lexell's
`Map` (insertion-ordered, with u32 index slots), so for `maps` the comparison is of the
same operations and keys, not the same data structure. Both print the same checksum.

| program | Lexell | Rust | Lexell / Rust |
|---|---:|---:|---:|
| fib | 820 ms | 914 ms | 0.90 |
| loop | 416 ms | 416 ms | 1.00 |
| array | 339 ms | 343 ms | 0.99 |
| sieve | 303 ms | 423 ms | 0.72 |
| alloc | 290 ms | 339 ms | 0.86 |
| strings | 213 ms | 276 ms | 0.77 |
| lists | 189 ms | 453 ms | 0.42 |
| trees | 138 ms | 332 ms | 0.42 |
| tokens | 125 ms | 101 ms | 1.23 |
| maps | 380 ms | 664 ms | 0.57 |

`tokens` uses views of the source (identifiers are `&str` slices, and the intern
table holds them), in both languages, with the same output. The same source
compiled through the C backend takes 104 ms, level with Rust (101 ms); over the
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
| literal `Sherlock Holmes` | 0.20 ms | 0.41 ms | 0.07 ms | 0.49 | 2.86 |
| alternation `Sherlock\|Holmes\|Watson\|Irene` | 0.59 ms | 131.8 ms | 0.40 ms | 0.004 | 1.47 |
| `\w+` | 19.5 ms | 121.4 ms | 15.7 ms | 0.16 | 1.25 |
| `(?i)sherlock` | 0.55 ms | 69.5 ms | 0.43 ms | 0.008 | 1.28 |
| email | 0.09 ms | 74.7 ms | 0.08 ms | 0.001 | 1.12 |
| `(?m)^ERROR .*timeout$` | 0.38 ms | 30.0 ms | 0.57 ms | 0.013 | 0.67 |
| dates `(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})` | 2.43 ms | 69.6 ms | 1.21 ms | 0.035 | 2.01 |
| `(a*)*b` on 100 KB | below timer resolution | 3.2 ms | below timer resolution | | |

Against Rust, the regex crate is faster on six patterns and Lexell is faster on
`errors`; `(a*)*b` is below timer resolution for both.

Against Rust, the gap on `literal`, alternation and `(?i)sherlock` is probably on
the library side: the `regex` crate searches literals with SIMD `memchr` and
Teddy, and `regex.lxl` makes no SIMD call. The `\w+` and dates gaps are more
likely the native backend's code generation, the performance side. Neither is
profiled yet, so this split is a reading of the source, not a measurement.

### JSON

Python's `json` module and jq 1.7.1 are the common tools for parsing and filtering JSON.

`bench/json/bench.py --jq jq`, an 80.2 MB generated document. Library times are
best of 3, in-process; jq times are whole-process wall time, best of 3. Each
driver's output is identical (sha256 checked).

| step | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| parse | 429 ms | Python json 870 ms | 0.49 |
| compact output | 452 ms | Python json 620 ms | 0.73 |
| pretty output | 501 ms | Python json 642 ms | 0.78 |
| query (sum of qty) | 196 ms | Python json 48 ms | 4.1 |
| visit (eachItem) | 199 ms | Python json 48 ms | 4.1 |
| jq `.` | 1,040 ms | jq 1.7.1 1,030 ms | 1.01 |
| jq `-c .` | 960 ms | jq 1.7.1 960 ms | 1.00 |
| jq `length` | 650 ms | jq 1.7.1 650 ms | 1.00 |
| jq `[.[].items[].qty] \| add` | 800 ms | jq 1.7.1 790 ms | 1.01 |
| jq `map(select(...))` | 820 ms | jq 1.7.1 810 ms | 1.01 |
| jq `group_by(.address.city)` | 1,120 ms | jq 1.7.1 1,120 ms | 1.00 |

The jq times are rounded to 10 ms by the script. The Lexell jq times are level with
jq 1.7.1 on every filter, within 1.3 percent.

### Markdown

cmark is the reference CommonMark implementation in C.

`tests/markdown.py` perf mode, against cmark 0.31.2, wall time, best of 3.
The perf mode checks no output.

| input | Lexell | cmark | Lexell / cmark |
|---|---:|---:|---:|
| spec text, 49 times (10.0 MB) | 120 ms | 96 ms | 1.25 |
| repository Markdown, 3 times (12.4 MB) | 162 ms | 140 ms | 1.16 |
| spec examples, 643 times (10.0 MB) | 356 ms | 334 ms | 1.07 |

### Decimal

Java `BigDecimal` and .NET `System.Decimal` are the standard decimal types in those languages.

`bench/decimal/compare/run.sh`, Lexell against Java BigDecimal and .NET
`System.Decimal`, nanoseconds per operation, from one run. The .NET SDK is 10.0.113.
The repo's `DecBench.csproj` targets net8.0 and only the .NET 10 runtime is
installed, so the .NET program was built from a copy retargeted to net10.0. The
All three columns come from the same run. The .NET harness has no 37- and
38-digit cases.

| operation | Lexell | .NET System.Decimal | Java BigDecimal | Lexell / .NET | Lexell / Java |
|---|---:|---:|---:|---:|---:|
| add, 19 digits | 13.1 ns | 11.4 ns | 13.7 ns | 1.15 | 0.96 |
| mul, 6 by 6 digits | 16.5 ns | 11.5 ns | 10.1 ns | 1.43 | 1.64 |
| div, 12 by 6, scale 2 | 22.6 ns | 65.8 ns | 11.3 ns | 0.34 | 2.00 |
| parse, 20 digits | 37.4 ns | 91.7 ns | 115.0 ns | 0.41 | 0.33 |
| format, 19 digits | 48.4 ns | 77.5 ns | 47.6 ns | 0.63 | 1.02 |
| cmp, 19 digits | 3.6 ns | 3.6 ns | 1.6 ns | 1.00 | 2.24 |
| add, 37 digits | 13.5 ns | not in harness | 16.5 ns | | 0.82 |
| mul, 19 digits | 18.6 ns | not in harness | 20.4 ns | | 0.91 |
| parse, 38 digits | 51.1 ns | not in harness | 227.7 ns | | 0.22 |
| format, 38 digits | 75.8 ns | not in harness | 246.9 ns | | 0.31 |

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
| 1 | 100,649 | 67,405 | 1.49 |
| 10 | 167,450 | 111,141 | 1.51 |
| 100 | 161,358 | 109,796 | 1.47 |

At 100 clients the p50 latency is 589 µs for Lexell and 846 µs for Go, and the
p99 is 744 µs and 3,186 µs. The memory per idle connection is 19.6 KB for Lexell
and 20.6 KB for Go. After the load, the server's RSS is 199 MB for Lexell and
345 MB for Go.

## Commands

GNU grep, sort and tail, and eza are the common tools for the same jobs.

The programs in `lexell/cmd`, built with the native backend, against the
system tools. Wall time is measured around each process, best of 5 rounds,
interleaved, with `LC_ALL=C` and the benchmark CPUs (4-7 and 12-15). Instruction
counts are user-mode. These figures are from a single run. GNU sort runs several threads. The driver does not compare
outputs; the sort outputs and the grep counts were checked by hand and agree.

| case | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| grep `-c omega`, 100 MB, wall | 58 ms | GNU grep 88 ms | 0.66 |
| grep `-c omega`, instructions | 795 M | GNU grep 375 M | 2.1 |
| grep `-o -w eta`, 100 MB, wall | 268 ms | GNU grep 352 ms | 0.76 |
| grep `-o -w eta`, instructions | 3,887 M | GNU grep 4,063 M | 0.96 |
| sort, 100 MB, wall | 604 ms | GNU sort 256 ms | 2.4 |
| sort, instructions | 5,989 M | GNU sort 2,683 M | 2.2 |
| tail `-n 5`, 100 MB file, wall | 7 ms | GNU tail 7 ms | level |
| eza `-T /usr/share`, wall | 198 ms | eza 0.23.5 605 ms | 0.33 |
| eza `-T /usr/share`, instructions | 1,306 M | eza 0.23.5 2,760 M | 0.47 |
| eza `-l /usr/lib`, wall | 25 ms | eza 0.23.5 35 ms | 0.71 |
| eza `-l /usr/lib`, instructions | 122 M | eza 0.23.5 187 M | 0.66 |

## Not measured

- **Rust toolchain sizes** in the compile table: the sizing step fails on a
  broken system symlink.
- **Plain C references** for the microbenchmarks are in the run's log but not in the table above.
- **ripgrep** in the command programs: not included.
- **HTTP client, TLS, tasks, database streaming, and LexDB.** Each
  needs its own references and runs; LexDB has its own document,
  `lexell/design/lexdb-benchmarks.md`, which is to be redone.
- **Oracle** comparison: dropped for now, to be added back later.
