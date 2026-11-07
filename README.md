# obx

**A 2.9 MB compiler that builds itself in 0.66 s, turns a hello world into a
16 KB native binary in 12 ms, and produces code as fast as Rust — and often
faster than C.**

obx is a small systems language with Rust-style ownership, generics and no
garbage collector. The compiler is the interesting part: 39,436 lines of obx,
no LLVM, no optimiser framework, writing x86-64 ELF directly. It is one
static binary, and it rebuilds itself from source in 0.66 s.

- **The code is fast.** Level with or ahead of idiomatic Rust on eight of
  nine microbenchmarks; Rust is ahead only on `tokens` (21%). Against the
  same source built through obx's C backend, `-O` wins nine of ten. Against
  hand-written C, obx is 2x on allocation, 1.7x on strings and 1.8x on the
  sieve, and ahead on lists and trees. C wins only on `array` (3.7x, AVX2
  auto-vectorisation), `tokens` (22%) and slightly `fib` (4%).
- **Building is fast.** The nine benchmark programs compile in 104 ms
  against 2.95 s for the Rust suite. Rust's `rustc` plus its driver and LLVM
  is 316 MB; with the rest of the toolchain it is 1.3 GB.
- **It is a real language with a real library.** Regex (RE2 syntax, linear
  time), JSON and a jq port, CommonMark, HTTP, TLS, tasks, and clients for
  SQLite, PostgreSQL, SQL Server and Oracle. A million database rows stream
  in 8 to 14 MB.

It targets Linux on x86-64. The numbers, method and caveats are in
[PERFORMANCE.md](PERFORMANCE.md).

## Quick start

Run these from the repository root. The first build uses the checked-in C
seed.

```
obx/compiler/build.sh                            # build the compiler from its seed
obx/compiler/out/obxc prog.obx -o prog           # a native x86-64 program, no gcc
obx/tools/gate.sh quick                          # run the test suites
```

The C backend is still available for the bootstrap, portability and
differential checks:

```
obx/compiler/out/obxc prog.obx --c -o prog       # the same program through C
```

A small program:

```
fn main() {
    let price = 19.99m
    let total = price * 3.0m
    println("total: " + total.toStr())
    let rate = 0.5f
    println("rate: " + rate.toStr())
}
```

It prints `total: 59.970` and `rate: 0.5`.

Language and platform notes:

- A number with a fraction needs a suffix. `1.5m` is a Decimal and `1.5f` is a float.
  A bare `1.5` is a compile error.
- Programs are Linux x86-64 executables. The CPU must support AVX2: Intel
  Haswell (2013) or AMD Excavator (2015) and later. There is no Windows,
  macOS or ARM support. On an older CPU a program stops with exit code 16.
- The owner frees a value. The compiler checks that borrows never outlive
  the value they lend.

## What is in it

### The compiler

- Two backends share one intermediate form.
  - **Native:** writes an ELF executable with no gcc. The program is static,
    or dynamically linked when it calls C libraries.
  - **C:** writes C and runs gcc.
- The compiler is about 39,000 lines of obx. Under a third of that is
  generated runtime tables.
- Its C is checked in as a seed. A first build needs only gcc.

### The library

The library is in [obx/lib/](obx/lib/README.md). Its main areas:

| Area | Modules |
|---|---|
| Core | `std` (the prelude: `Option`, `Result`, `Decimal`, `Map`), `collections`, `strings`, `money`, `math` |
| Files and time | `io`, `fs`, `os`, `time`, `tz` (time zones) |
| Text and data | `regex` (RE2 syntax, linear time), `json`, `markdown` (CommonMark), `codepage` |
| Network | `net` (TCP), `tls` (OpenSSL 3), `url`, `http` (client), `httpserver` (server) |
| Tasks and processes | `task` (tasks, futures, worker processes), `proc` (other programs) |
| Databases | `sqlite`, `postgres`, `sqlserver`, `mssql`, `oracle`, with `sqlrows` and `sqldialect` |
| C interop | `ffi` (C memory), `crypto` (digests and AES from libcrypto) |

Tasks run concurrently on one thread. A task pauses while it waits, so one
thread can serve many connections. For more cores, `task.workers` forks
worker processes. The design is in
[obx/design/concurrency.md](obx/design/concurrency.md).

### The programs

The programs are in [obx/cmd/](obx/cmd/README.md):

- **eza**: the common subset of eza 0.23.3, including the long view (`-l`, `-lh`).
- **cat, wc, sort, head, tail, grep**: subsets of the GNU tools, with their output and exit codes.
- **zoxide**: the `cd` helper. It reads and writes the real zoxide's database.
- **jq**: a port of jq 1.7.1. It has no modules.
- **cmark**: a CommonMark renderer, like cmark 0.31.2.
- **httpd** and **httpload**: an HTTP/1.1 server and its load client.
- **tlsbench**: a TLS benchmark.

### Database clients

| Client | Database | How it connects |
|---|---|---|
| `sqlite` | SQLite | libsqlite3 |
| `postgres` | PostgreSQL | native, over the protocol 3.0 (`pgwire`): TLS, SCRAM |
| `postgres_libpq` | PostgreSQL | libpq; kept as the test oracle for `postgres` |
| `sqlserver` | SQL Server | native, over the TDS protocol |
| `mssql` | SQL Server | ODBC |
| `oracle` | Oracle Database | native, over the TNS protocol, ported from python-oracledb |

`sqlserver`, `postgres` and `oracle` can stream rows. `conn.stream` decodes
each row into the program's own record. Memory stays flat: it is the same
at 100,000 and at 1,000,000 rows. See
[obx/design/db-streaming.md](obx/design/db-streaming.md).

The Oracle client supports OUT binds, REF CURSORs and TLS.

## Status and limitations

obx is new: the project restarted on 2 November 2026. The language
specification is draft 1, there is no package manager or third-party
ecosystem yet, and the compiler, library and programs in this repository are
the project. APIs may still change.

- **Linux x86-64 only.** The native backend writes a Linux ELF executable;
  there is no Windows, macOS or ARM backend.
- **AVX2 required.** Intel Haswell (2013) or AMD Excavator (2015) and later;
  older CPUs stop with exit code 16.
- **gcc for the first build.** The checked-in C seed needs gcc once. After
  that `obxc` writes native executables directly and needs no C compiler.
- **Some libraries use C.** TLS uses OpenSSL, SQLite uses libsqlite3, and
  the ODBC SQL Server client links ODBC; the native runtime itself is
  freestanding. Programs that use those libraries are dynamically linked.
- **Not 1.0.** There is no stable API or release process yet; the test
  suites and `gate.sh` are the contract.

## Performance

These figures come from [PERFORMANCE.md](PERFORMANCE.md); the internal
native-vs-C measurement is kept separately in
[design/native-vs-c.md](obx/design/native-vs-c.md). They were measured on
one 8-core test machine, so compare the columns, not the absolute numbers.

obx is small and fast. The compiler is 39,436 lines and a 2.9 MB static
binary, and builds itself in 0.66 s. Rust's `rustc` plus its driver and
LLVM is 316 MB (560 MB installed, 1.3 GB with docs), and a full rustc
self-build is over 30 minutes on a moderately powerful laptop, according to
the [Rust compiler development guide](https://rustc-dev-guide.rust-lang.org/);
tests are separate. A hello world
compiles in 12 ms to a 16 KB executable; Rust takes 162 ms and 357 KB
(stripped), and gcc 86 ms. The nine benchmark programs compile in 104 ms
with obx against 2.95 s for the Rust suite.

- **Competitive with Rust:** on the nine microbenchmarks obx is level with
  or ahead of idiomatic Rust on eight; Rust is clearly ahead only on
  `tokens` (21%). Plain C is ahead on `array` (3.7 times, AVX2
  auto-vectorisation), `tokens` (22%) and slightly `fib` (4%); obx is ahead
  on allocation, strings, lists, trees and sieve. The table and the Rust
  ports are in [PERFORMANCE.md](PERFORMANCE.md) and
  [obx/bench/rust/](obx/bench/rust/).
- **Applications:** regex 44 ms, `json`/`jq` 0.4 to 0.5 s, Markdown 0.16 s,
  Decimal 2.2 s. The external references (Rust, Go, jq, cmark, .NET and
  Java) are in [PERFORMANCE.md](PERFORMANCE.md).
- **Decimal:** 13.3 ns for a 19-digit add and 17.1 ns for a 6x6 multiply;
  1.2 times .NET on add and 1.5 on multiply.
- **Float math** takes within about 15% of C's cycles per call.
- **HTTP server:** one thread serves 60,763 requests a second to 100 clients.
  Go's `net/http` serves 44,500 on the same setup. With 8 worker processes
  the server reaches about 124,000.
- **Database streaming:** 1,000,000 rows take 8 to 14 MB of memory when
  streamed. Buffering the same rows takes 91 to 365 MB.
- **Small programs:** hello world is 16 KB, static, with no libc.

## Where to read more

| Document | What it covers |
|---|---|
| [obx/README.md](obx/README.md) | the language and the layout of the repository |
| [obx/SPEC.md](obx/SPEC.md) | the language definition |
| [obx/PLAN.md](obx/PLAN.md) | the stages, their gates and their state |
| [PERFORMANCE.md](PERFORMANCE.md) | the measured numbers and how they were taken |
| [design/native-vs-c.md](obx/design/native-vs-c.md) | native against the C backend, as an internal check |
| [HISTORY.md](HISTORY.md) | how the project got here, with dated entries |
| [obx/design/](obx/design/) | design notes for each stage and subsystem |
| [obx/lib/README.md](obx/lib/README.md) | the library: every module |
| [obx/cmd/README.md](obx/cmd/README.md) | the programs and their tests |
| [obx/tests/README.md](obx/tests/README.md) | the test suites and the gate |

## Where it came from

obx grew out of two earlier compilers. Both are archived.

- **Mainline obx** ([archive/obx/](archive/obx/)) was the original Oberon
  dialect, with a garbage collector.
- **obo** ([archive/obo/](archive/obo/README.md)) was an ownership fork. Its
  borrowing drew on Nick Smith's and Evan Ovadia's
  [group borrowing](https://verdagon.dev/blog/valen-group-borrowing). It
  reached version 0.19. Every new kind of value had to be wired through the
  whole compiler.

On 2 November 2026 the project restarted as obx. It kept obo's ownership
model and added generics. The full story is in [HISTORY.md](HISTORY.md).

## License

obx is licensed under the Apache License, Version 2.0. The full text is in
[LICENSE](LICENSE); [NOTICE](NOTICE) records the copyright. Unless a file says
otherwise, the compilers, runtimes, tools, tests and documentation are covered.

Contributions are accepted under the same license; by contributing you agree that
your contribution is licensed under the Apache License, Version 2.0.
