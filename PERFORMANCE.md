# Lexell performance

Measured on 18 November 2026 on the `bench/perf-main` branch (commit 591cf112): `main` at 8a890f21 with the command-program fixes and the tuned
PostgreSQL settings merged in. Every number here is from that build and
compares Lexell only with external tools or databases. Lexell's own C backend
and earlier builds are not compared.

Host: AMD Ryzen 7 8745HS (8 cores, 16 threads), 46 GB RAM, Linux 7.2 (Arch).
Versions: rustc and cargo 1.99.1, Go 1.27.3, Java 21.0.13, Python 3.14.8,
cmark 0.31.2, ripgrep 15.2.0, eza 0.23.5, jq 1.7.1 (built from its tarball),
GNU grep and sort from the system.

Method: wall times are best of N; instruction counts are user-mode
`perf stat` instructions, the stable figure. Benchmark processes are pinned
(server CPUs 0-3, client CPUs 4-7 and 12-15). Lexell runs with
`LXL_HASH_SEED=42`. One benchmark ran at a time.

## Summary

| area | Lexell against | result |
|---|---|---|
| Compile, hello world | Rust | 14 ms against 44 ms; 20 KB against 330 KB |
| Compile, nine benchmarks | Rust | 131 ms against 2,780 ms |
| Microbenchmarks, native `-O` | Rust | level or ahead on eight of the nine with a Rust port; `tokens` 2.0 times slower |
| Regex, literal and class searches | Go regexp | ahead on most; `dates` about 100 times slower |
| JSON, parse and output | Python json | 1.25 to 2 times faster |
| JSON, query and visit | Python json | about 4 times slower |
| jq filters (80 MB) | jq 1.7.1 | 1.4 to 2.2 times faster |
| Markdown | cmark 0.31.2 | 1.17 to 1.28 times slower |
| Decimal | Java BigDecimal | mixed: 0.27 to 5.2 times the Java time |
| grep, `-c` | GNU grep | 1.5 times faster in wall time, 2.1 times the instructions |
| grep, `-o -w` | GNU grep | 1.3 times faster |
| sort (100 MB) | GNU sort | 1.8 times slower |
| tail, `-n 5` of 100 MB | GNU tail | level |
| eza, `-T` (tree) | eza 0.23.5 | 4 times faster |

## Compile time

From `bench/compile.py -n 3`. The table is from the run that printed it; the
script then crashed while sizing the Rust sysroot (a broken system symlink),
so the Rust toolchain sizes are missing.

| case | Lexell | Rust |
|---|---:|---:|
| hello world, compile | 14 ms | 43.5 ms |
| hello world, binary | 20 KB | 330 KB |
| nine benchmark programs, clean compile | 131 ms | 2,780 ms |
| nine benchmark programs, binaries | 188 KB | 430 KB |

The compiler's own self-build takes 464 ms (no external reference).

## Microbenchmarks

Ten programs, native `-O`, wall time, best of 5. Nine have a Rust port in
`bench/rust`; `maps` has none.

| program | Lexell | Rust | Lexell / Rust |
|---|---:|---:|---:|
| fib | 823 ms | 826 ms | 1.00 |
| loop | 415 ms | 416 ms | 1.00 |
| array | 343 ms | 349 ms | 0.98 |
| sieve | 302 ms | 393 ms | 0.77 |
| alloc | 292 ms | 342 ms | 0.85 |
| strings | 210 ms | 277 ms | 0.76 |
| lists | 191 ms | 450 ms | 0.42 |
| trees | 136 ms | 334 ms | 0.41 |
| tokens | 186 ms | 93 ms | 2.00 |
| maps | 365 ms | no reference | |

`tokens` was rewritten for this run to use views of the source (identifiers are
`&str` slices, and the intern table holds them), in both languages, with the same
output. The same source compiled through the C backend takes 96 ms, level with Rust;
the native backend executes about 1.6 times the instructions on the scanning loop.
That gap is the native code generator's, not the program's; the native
backend's code for the scanning loop is the cause, and the work on it is tracked
in `lexell/design/codegen-audit.md`.

## Applications

### Regex

`bench/regex/bench.py`, a 3.2 MB corpus; match counts agree across Lexell,
Go and ripgrep. Times are as the script prints them, best of 5 runs of 5
searches. The Rust regex column is missing: the `regex` crate is not in the
offline cargo cache.

| pattern | Lexell | Go regexp | Lexell / Go |
|---|---:|---:|---:|
| literal `Sherlock Holmes` | 0.20 ms | 0.41 ms | 0.49 |
| alternation `Sherlock\|Holmes\|Watson\|Irene` | 0.59 ms | 132.6 ms | 0.004 |
| `\w+` | 19.6 ms | 120.3 ms | 0.16 |
| `(?i)sherlock` | 0.55 ms | 71.0 ms | 0.008 |
| email | 0.09 ms | 75.2 ms | 0.001 |
| `(?m)^ERROR .*timeout$` | 0.38 ms | 30.2 ms | 0.013 |
| dates `(?P<y>\d{4})-(?P<m>\d{2})-(?P<d>\d{2})` | 7,025 ms | 69.2 ms | 101.6 |
| `(a*)*b` on 100 KB | below timer resolution | 3.2 ms | |

The dates pattern is the one case where Lexell is much slower. The cause has
not been checked yet.

### JSON

`bench/json/bench.py --jq`, an 80.2 MB generated document. Library times are
best of 3, in-process; jq times are whole-process wall time, best of 3. Each
driver's output is identical (sha256 checked).

| step | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| parse | 395 ms | Python json 808 ms | 0.49 |
| compact output | 455 ms | Python json 585 ms | 0.78 |
| pretty output | 493 ms | Python json 615 ms | 0.80 |
| query (sum of qty) | 190 ms | Python json 44 ms | 4.3 |
| visit (eachItem) | 193 ms | Python json 44 ms | 4.4 |
| jq `.` | 970 ms | jq 1.7.1 2,180 ms | 0.45 |
| jq `-c .` | 910 ms | jq 1.7.1 1,940 ms | 0.47 |
| jq `length` | 620 ms | jq 1.7.1 990 ms | 0.63 |
| jq `[.[].items[].qty] \| add` | 750 ms | jq 1.7.1 1,230 ms | 0.61 |
| jq `map(select(...))` | 770 ms | jq 1.7.1 1,210 ms | 0.64 |
| jq `group_by(.address.city)` | 1,050 ms | jq 1.7.1 1,460 ms | 0.72 |

The jq times are rounded to 10 ms by the script.

### Markdown

`tests/markdown.py` perf mode, against cmark 0.31.2, wall time, best of 3.
The perf mode checks no output.

| input | Lexell | cmark | Lexell / cmark |
|---|---:|---:|---:|
| spec text, 49 times (10.0 MB) | 124 ms | 97 ms | 1.28 |
| repository Markdown, 3 times (12.6 MB) | 173 ms | 142 ms | 1.22 |
| spec examples, 643 times (10.0 MB) | 379 ms | 325 ms | 1.17 |

### Decimal

`bench/decimal/compare/run.sh`, Lexell against Java BigDecimal, nanoseconds
per operation, minimum of 3 runs. The .NET comparison is not run.

| operation | Lexell | Java | Lexell / Java |
|---|---:|---:|---:|
| add, 19 digits | 12.6 ns | 13.0 ns | 0.97 |
| mul, 6 by 6 digits | 15.8 ns | 9.7 ns | 1.63 |
| div, 12 by 6, scale 2 | 42.7 ns | 11.1 ns | 3.8 |
| parse, 20 digits | 36.2 ns | 105.6 ns | 0.34 |
| format, 19 digits | 46.4 ns | 45.4 ns | 1.02 |
| cmp, 19 digits | 8.0 ns | 1.6 ns | 5.2 |
| add, 37 digits | 13.0 ns | 15.5 ns | 0.84 |
| mul, 19 digits | 18.2 ns | 19.5 ns | 0.93 |
| parse, 38 digits | 53.5 ns | 202 ns | 0.27 |
| format, 38 digits | 74.2 ns | 234 ns | 0.32 |

The outputs are not verified against Java. The two harnesses print different
checksums, so eight of the ten cases cannot be compared; the two format cases
print the same checksum in both.

## Commands

The programs in `lexell/cmd`, built with the native backend, against the
system tools. Wall time is best of 5, interleaved; instructions are user-mode
counts. Output was compared with `cmp` where noted.

| case | Lexell | Reference | Lexell / reference |
|---|---:|---:|---:|
| grep `-c omega`, 100 MB, wall | 59 ms | GNU grep 90 ms | 0.66 |
| grep `-c omega`, instructions | 795 M | GNU grep 375 M | 2.1 |
| grep `-c omega`, wall | 59 ms | ripgrep 45 ms | 1.3 |
| grep `-o -w eta`, 100 MB, wall | 269 ms | GNU grep 354 ms | 0.76 |
| sort, 100 MB, wall | 641 ms | GNU sort 359 ms | 1.78 |
| sort, instructions | 5,989 M | GNU sort 2,683 M | 2.2 |
| tail `-n 5`, 100 MB file, wall | 7.9 ms | GNU tail 7.7 ms | 1.02 |
| eza `-T /usr/share`, wall | 198 ms | eza 0.23.5 814 ms | 0.24 |
| eza `-l /usr/lib`, wall | 26 ms | eza 0.23.5 44 ms | 0.60 |

The grep, sort, tail and tree outputs are identical. The `-l` outputs differ in
column padding and in one extended-attribute marker, so that row is indicative
only. The requested `/usr/lib/x86_64-linux-gnu` does not exist on this host.

## Not measured in this round

- **Rust toolchain sizes** in the compile table: the sizing step crashed on a
  broken system symlink.
- **Regex against the Rust crate:** the `regex` crate is not in the offline cargo cache.
- **Plain C references** for the microbenchmarks.
- **HTTP server and client, TLS, tasks, database streaming, and LexDB.** Each
  needs its own references and runs; LexDB has its own document,
  `lexell/design/lexdb-benchmarks.md`, which is to be redone.
- **.NET and Oracle** comparisons: dropped for now, to be added back later.
