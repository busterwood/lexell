# Lexell performance

Measured on 18 November 2026 on `main` at commit 800ff80b. Every number here is from that build and
compares Lexell only with external tools or databases. Lexell's own C backend
and earlier builds are not compared.

Host: AMD Ryzen 7 8745HS (8 cores, 16 threads), 46 GB RAM, Linux 7.2 (Arch).
Versions: rustc and cargo 1.99.1, Go 1.27.3, Java 21.0.13, Python 3.14.8,
cmark 0.31.2, jq 1.7.1 (built from its tarball), GNU grep and sort from the system.

Method: wall times are best of N; instruction counts are user-mode
`perf stat` instructions, the stable figure. Benchmark processes are pinned
(server CPUs 0-3, client CPUs 4-7 and 12-15). Lexell runs with
`LXL_HASH_SEED=42`. One benchmark ran at a time.

## Summary

| area | Lexell against | result |
|---|---|---|
| Compile, hello world | Rust | 14 ms against 48 ms; 20 KB against 330 KB |
| Compile, nine benchmarks | Rust | 132 ms against 2,830 ms |
| Microbenchmarks, native `-O` | Rust | level or ahead on eight of the nine with a Rust port; `tokens` 1.9 times slower |
| Regex, literal and class searches | Go regexp | ahead on most; `dates` about 100 times slower |
| JSON, parse and output | Python json | 1.2 to 2 times faster |
| JSON, query and visit | Python json | about 4 times slower |
| jq filters (80 MB) | jq 1.7.1 | 1.4 to 2.2 times faster |
| Markdown | cmark 0.31.2 | 1.14 to 1.29 times slower |
| Decimal | Java BigDecimal | mixed: 0.30 to 3.9 times the Java time |
| grep, `-c` | GNU grep | 1.5 times faster in wall time, 2.1 times the instructions |
| grep, `-o -w` | GNU grep | 1.3 times faster |
| sort (100 MB) | GNU sort | 2.4 times slower in wall time, 2.2 times the instructions |
| tail, `-n 5` of 100 MB | GNU tail | level |
| eza, `-T` and `-l` | eza 0.23.5 | 3.1 times faster on `-T`, 1.4 times on `-l` |

## Compile time

From `bench/compile.py -n 3`. The table is from the run that printed it; the
script then crashed while sizing the Rust sysroot (a broken system symlink),
so the Rust toolchain sizes are missing.

| case | Lexell | Rust |
|---|---:|---:|
| hello world, compile | 14 ms | 48.3 ms |
| hello world, binary | 20 KB | 330 KB |
| nine benchmark programs, clean compile | 132 ms | 2,830 ms |
| nine benchmark programs, binaries | 184 KB | 430 KB |

The compiler's own self-build takes 465 ms (no external reference).

## Microbenchmarks

Ten programs, native `-O`, wall time, best of 5. Nine have a Rust port in
`bench/rust`; `maps` has none.

| program | Lexell | Rust | Lexell / Rust |
|---|---:|---:|---:|
| fib | 820 ms | 908 ms | 0.90 |
| loop | 416 ms | 416 ms | 1.00 |
| array | 341 ms | 346 ms | 0.98 |
| sieve | 302 ms | 424 ms | 0.71 |
| alloc | 291 ms | 342 ms | 0.85 |
| strings | 210 ms | 277 ms | 0.76 |
| lists | 190 ms | 443 ms | 0.43 |
| trees | 136 ms | 334 ms | 0.41 |
| tokens | 190 ms | 101 ms | 1.88 |
| maps | 365 ms | no reference | |

`tokens` was rewritten for this run to use views of the source (identifiers are
`&str` slices, and the intern table holds them), in both languages, with the same
output. The same source compiled through the C backend takes 105 ms, level with
Rust (101 ms); over the whole program the native backend executes about 1.4 times
the instructions of the C build. That gap is the native code generator's, not the
program's; the native backend's code for the scanning loop is the cause, and the
work on it is tracked in `lexell/design/codegen-audit.md`.

## Applications

### Regex

`bench/regex/bench.py`, a 3.2 MB corpus; match counts agree across Lexell,
Go and ripgrep. Times are as the script prints them, best of 5 runs of 5
searches. The Rust regex column is missing: the `regex` crate is not in the
offline cargo cache.

| pattern | Lexell | Go regexp | Lexell / Go |
|---|---:|---:|---:|
| literal `Sherlock Holmes` | 0.20 ms | 0.41 ms | 0.49 |
| alternation `Sherlock\|Holmes\|Watson\|Irene` | 0.59 ms | 131.9 ms | 0.004 |
| `\w+` | 19.5 ms | 120.5 ms | 0.16 |
| `(?i)sherlock` | 0.54 ms | 70.0 ms | 0.008 |
| email | 0.09 ms | 74.8 ms | 0.001 |
| `(?m)^ERROR .*timeout$` | 0.38 ms | 30.1 ms | 0.013 |
| dates `(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})` | 7,047 ms | 69.0 ms | 102.2 |
| `(a*)*b` on 100 KB | below timer resolution | 3.2 ms | |

The dates pattern is the one case where Lexell is much slower. The cause has
not been checked yet.

### JSON

`bench/json/bench.py --jq jq`, an 80.2 MB generated document. Library times are
best of 3, in-process; jq times are whole-process wall time, best of 3. Each
driver's output is identical (sha256 checked).

| step | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| parse | 398 ms | Python json 808 ms | 0.49 |
| compact output | 453 ms | Python json 573 ms | 0.79 |
| pretty output | 492 ms | Python json 602 ms | 0.82 |
| query (sum of qty) | 191 ms | Python json 44 ms | 4.3 |
| visit (eachItem) | 193 ms | Python json 44 ms | 4.3 |
| jq `.` | 980 ms | jq 1.7.1 2,190 ms | 0.45 |
| jq `-c .` | 900 ms | jq 1.7.1 1,940 ms | 0.46 |
| jq `length` | 620 ms | jq 1.7.1 990 ms | 0.63 |
| jq `[.[].items[].qty] \| add` | 750 ms | jq 1.7.1 1,230 ms | 0.61 |
| jq `map(select(...))` | 770 ms | jq 1.7.1 1,220 ms | 0.63 |
| jq `group_by(.address.city)` | 1,050 ms | jq 1.7.1 1,450 ms | 0.72 |

The jq times are rounded to 10 ms by the script.

### Markdown

`tests/markdown.py` perf mode, against cmark 0.31.2, wall time, best of 3.
The perf mode checks no output.

| input | Lexell | cmark | Lexell / cmark |
|---|---:|---:|---:|
| spec text, 49 times (10.0 MB) | 124 ms | 96 ms | 1.29 |
| repository Markdown, 3 times (12.4 MB) | 171 ms | 139 ms | 1.23 |
| spec examples, 643 times (10.0 MB) | 379 ms | 332 ms | 1.14 |

### Decimal

`bench/decimal/compare/run.sh`, Lexell against Java BigDecimal, nanoseconds
per operation, minimum of 3 runs. The .NET comparison is not run. `run.sh` needs a .NET SDK for its .NET step;
without one it stops before the Lexell and Java runs, so the Java numbers here
come from the built binaries and classes with the script's own flags.

| operation | Lexell | Java | Lexell / Java |
|---|---:|---:|---:|
| add, 19 digits | 12.5 ns | 12.6 ns | 0.99 |
| mul, 6 by 6 digits | 15.8 ns | 10.3 ns | 1.54 |
| div, 12 by 6, scale 2 | 42.6 ns | 11.9 ns | 3.6 |
| parse, 20 digits | 33.8 ns | 98.6 ns | 0.34 |
| format, 19 digits | 46.4 ns | 47.2 ns | 0.98 |
| cmp, 19 digits | 8.0 ns | 2.1 ns | 3.9 |
| add, 37 digits | 13.0 ns | 16.8 ns | 0.77 |
| mul, 19 digits | 18.3 ns | 19.2 ns | 0.95 |
| parse, 38 digits | 48.7 ns | 158.7 ns | 0.31 |
| format, 38 digits | 73.9 ns | 248.5 ns | 0.30 |

The outputs are not verified against Java. The two harnesses print different
checksums, so eight of the ten cases cannot be compared; the two format cases
print the same checksum in both.

## Commands

The programs in `lexell/cmd`, built with the native backend, against the
system tools. Wall time is measured around each process, best of 5 rounds,
interleaved, with `LC_ALL=C` and the benchmark CPUs (4-7 and 12-15). Instruction
counts are user-mode. GNU sort runs several threads. The driver does not compare
outputs; the sort outputs and the grep counts were checked by hand and agree.

| case | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| grep `-c omega`, 100 MB, wall | 59 ms | GNU grep 90 ms | 0.66 |
| grep `-c omega`, instructions | 795 M | GNU grep 375 M | 2.1 |
| grep `-o -w eta`, 100 MB, wall | 269 ms | GNU grep 353 ms | 0.76 |
| grep `-o -w eta`, instructions | 3,887 M | GNU grep 4,063 M | 0.96 |
| sort, 100 MB, wall | 607 ms | GNU sort 257 ms | 2.4 |
| sort, instructions | 5,989 M | GNU sort 2,683 M | 2.2 |
| tail `-n 5`, 100 MB file, wall | 8 ms | GNU tail 7 ms | level |
| eza `-T /usr/share`, wall | 197 ms | eza 0.23.5 611 ms | 0.32 |
| eza `-T /usr/share`, instructions | 1,306 M | eza 0.23.5 2,760 M | 0.47 |
| eza `-l /usr/lib`, wall | 25 ms | eza 0.23.5 35 ms | 0.71 |
| eza `-l /usr/lib`, instructions | 122 M | eza 0.23.5 187 M | 0.66 |

## Not measured in this round

- **Rust toolchain sizes** in the compile table: the sizing step crashed on a
  broken system symlink.
- **Regex against the Rust crate:** the `regex` crate is not in the offline cargo cache.
- **Plain C references** for the microbenchmarks are in the run's log but not in the table above.
- **ripgrep** in the command programs: not included in this round.
- **HTTP server and client, TLS, tasks, database streaming, and LexDB.** Each
  needs its own references and runs; LexDB has its own document,
  `lexell/design/lexdb-benchmarks.md`, which is to be redone.
- **.NET and Oracle** comparisons: dropped for now, to be added back later.
