# obx

**A 2.9 MB compiler that builds itself in 0.65 s, turns a hello world into a
16 KB native binary in 13 ms, and produces code as fast as Rust — and often
faster than C.**

obx is a small language in the Oberon line — the family Go also draws on. It
looks a bit like Go, but has generics and uses single ownership with group
borrowing —
[simpler memory management than Rust](https://verdagon.dev/blog/valen-group-borrowing),
with no lifetime annotations. There is no garbage collector. Strings are
reference counted, and generic code is checked where it is written and
compiled per instance.

The rest is deliberately familiar: modules (one source file each, with
explicit imports and `pub` visibility), records with methods, structural
interfaces as generic constraints, growable arrays and slices, string
slicing and views, closures and function values, `Option` and `Result` with
`try`, `match` expressions, and destructors.

**Concurrency without the concurrency bugs.** Handlers are plain blocking
code — no `async`/`await`, no function colouring — running as many tasks on
one OS thread over an epoll loop. If there are no threads, there is no
threading bug to write: nothing to lock, no data races, nothing to coordinate
between cores. Tasks return `Future[T]` values; a `Promise[T]` completes one
by hand, and `Shared[T]` holds state that several tasks need. More cores
means shared-nothing worker processes, the nginx model: each worker owns its
state, and the database is the only thing they share. One thread serves
60,763 HTTP requests a second; eight workers reach about 124,000.

The compiler is 39,436 lines of obx, a 2.9 MB static binary with no LLVM
behind it, rebuilding itself in 0.65 s. It writes x86-64 ELF directly.

- **The code is fast.** It is level with or ahead of idiomatic Rust on eight
  of nine microbenchmarks, and beats the same source built through obx's C
  backend on nine of ten. Against hand-written C it is 2x on allocation and
  strings, 1.3x on trees, and ahead on lists and the sieve.
- **Building is fast.** The nine benchmark programs compile in 124 ms
  against 2.23 s for the Rust suite. Rust's `rustc` plus its driver and LLVM
  is 316 MB; with the rest of the toolchain it is 1.3 GB.
- **It is a real language with a real library.** Regex (RE2 syntax, linear
  time), JSON and a jq port, CommonMark, HTTP, TLS, tasks, and clients for
  SQLite, PostgreSQL, SQL Server and Oracle. A million database rows stream
  in 8 to 14 MB.
- **Exact decimals, not floats.** `1.25m` is a 38-digit `Decimal` with a
  display scale: the full precision of SQL Server's `decimal` and Oracle's
  `NUMBER`, exact arithmetic, and no binary-float rounding.

It targets Linux on x86-64. The numbers, method and caveats are in
[PERFORMANCE.md](PERFORMANCE.md).

## A taste of obx

```
type Point = value record { x: int; y: int }

fn (p: &Point) norm2(): int { return p.x * p.x + p.y * p.y }
fn ident[T](v: T): T { return v }
fn firstPositive(xs: &[int]): Option[int] {
    for x in xs { if x > 0 { return Some(x) } }
    return None
}

fn main() {
    let p = Point{x: 3, y: 4}
    println(p.norm2())
    println(ident("obx"))
    match firstPositive(&[0, 7]) {
        Some(n) { println(n) }
        None { println("none") }
    }
    let price = 19.99m
    println((price * 3.0m).toStr())
}
```

It prints `25`, `obx`, `7` and `59.970`. It shows a value record with a
method, a generic function, a slice with `Option` and `match`, and an exact
`Decimal`.

## Quick start

Run these from the repository root, with the program above saved as
`prog.obx`. The first build uses the checked-in C seed and takes about 22 s
because it runs gcc; later self-builds take 0.65 s.

```
obx/compiler/build.sh                            # build the compiler from its seed
obx/compiler/out/obxc prog.obx -o prog           # a native x86-64 program, no gcc
./prog                                           # 25, obx, 7, 59.970
obx/tools/gate.sh quick                          # run the test suites
```

The C backend is still available for the bootstrap, portability and
differential checks:

```
obx/compiler/out/obxc prog.obx --c -o prog       # the same program through C
```

Language and platform notes:

- A number with a fraction needs a suffix. `1.5m` is a Decimal and `1.5f` is a float.
  A bare `1.5` is a compile error.
- Programs are Linux x86-64 executables. The CPU must support AVX2: Intel
  Haswell (2013) or AMD Excavator (2015) and later. There is no Windows,
  macOS or ARM support. On an older CPU a program stops with exit code 16.
- The owner frees a value. The compiler checks that borrows never outlive
  the value they lend.

## What's in the box

### The compiler

- Two backends share one intermediate form.
  - **Native:** writes an ELF executable with no gcc. The program is static,
    or dynamically linked when it calls C libraries.
  - **C:** writes C and runs gcc.
- The compiler is 39,436 lines of obx. Under a third of that is
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

Decimals are exact end to end. The 38-digit `Decimal` matches the precision
of SQL Server's `decimal`/`numeric` and Oracle's `NUMBER`; SQLite has no
decimal type, so its client stores them as exact text and checks the declared
precision and scale when binding.

The Oracle client supports OUT binds, REF CURSORs and TLS.

## Performance

The short version: obx compiles like a script and runs like Rust. One 8-core
test machine; full tables, method and caveats in
[PERFORMANCE.md](PERFORMANCE.md).

| | obx | Rust | C |
|---|---:|---:|---:|
| hello world, compile | 13 ms | 154 ms | 61 ms |
| hello world, binary | 16 KB static | 357 KB | 16 KB |
| nine programs, compile | 124 ms | 2.23 s | - |
| self-build | 0.65 s | over 30 min* | - |
| toolchain | 2.9 MB | 316 MB | system gcc |

- **Code:** level with or ahead of idiomatic Rust on eight of nine
  microbenchmarks. Against the same source built through obx's C backend,
  `-O` wins nine of ten; against hand-written C, obx is 2x on allocation and
  strings, 1.3x on trees, and ahead on lists and the sieve.
- **Applications:** regex 44 ms, `json`/`jq` 0.4 to 0.5 s, Markdown 0.16 s,
  Decimal 2.2 s. External references (Rust, Go, jq, cmark, .NET and Java)
  are in [PERFORMANCE.md](PERFORMANCE.md).
- **Decimal:** 13.3 ns for a 19-digit add and 17.1 ns for a 6x6 multiply;
  1.2 times .NET on add and 1.5 on multiply.
- **Float math** takes within about 15% of C's cycles per call.
- **HTTP:** one thread serves 60,763 requests a second to 100 clients; Go's
  `net/http` serves 44,500. With 8 worker processes the server reaches about
  124,000.
- **Streaming:** 1,000,000 rows take 8 to 14 MB of memory; buffering the same
  rows takes 91 to 365 MB.

\* Rust self-build: the
[Rust compiler development guide](https://rustc-dev-guide.rust-lang.org/)'s
estimate, not measured here; tests are separate. Rust's 316 MB is `rustc`,
its driver and LLVM (560 MB installed, 1.3 GB with docs). The nine-program row
builds nine obx executables against one Rust binary with nine subcommands, and
cargo measures its own build system.

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

## Where to read more

| Start here | What it covers |
|---|---|
| [obx/SPEC.md](obx/SPEC.md) | the language definition |
| [obx/lib/README.md](obx/lib/README.md) | the library: every module |
| [obx/cmd/README.md](obx/cmd/README.md) | the programs and their tests |
| [PERFORMANCE.md](PERFORMANCE.md) | the measured numbers and how they were taken |
| [design/native-vs-c.md](obx/design/native-vs-c.md) | native against the C backend |
| [HISTORY.md](HISTORY.md) | how the project got here |

The repository map, design notes, plans and test suites are in
[obx/README.md](obx/README.md).

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
