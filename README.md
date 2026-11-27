# Lexell

Lexell is a memory-safe language that compiles in milliseconds and produces small, fast native executables. Like Rust, it rules out the memory errors behind many of the security holes in C and C++ programs, and it does so without a garbage collector. Unlike Rust, the compiler is about 3 MB, rebuilds itself in about half a second, and needs no lifetime annotations.

- **Memory safe, without a garbage collector.** Every value has one owner, and the compiler checks that a borrow never outlives what it borrows, so there is no use after free and no double free. Memory is released as soon as its owner goes away: no collector, no pauses, and a small footprint (2–31 MB peak in the benchmarks, where the JVM takes 51 MB–1.4 GB). Reference counting is there when you ask for it (`rc T`).
- **No nulls, no unchecked memory access.** A value that may be missing is an `Option`, and the compiler makes you handle the missing case. Indexes are bounds-checked, and integer overflow stops the program instead of wrapping silently. There is no pointer arithmetic and no `unsafe` block; the only unchecked code is a call into a C library declared `extern`, which the standard library wraps.
- **No data races, and scaling by sharing nothing.** A server handles thousands of connections as cooperative tasks on one thread, written as plain sequential code, with no threads, locks or `async`. One thread per process is a performance choice as well as a safety one: to use more cores you run more processes that share nothing, as nginx does, so adding cores adds no locks and no contention (see [concurrency](#concurrency-without-threads-or-locks)).
- **A quick feedback loop.** Hello world compiles in 14 ms, against 59 ms for Rust, and the nine benchmark programs in 140 ms, against 3.58 s.
- **Small, fast executables.** The compiler writes Linux executables directly. Hello world is 22 KB, against Rust's 330 KB, and the generated code is faster than Rust's on 12 of the 19 [benchmarks](#performance) they share, and level on two more.

These guarantees come from the language's rules and the compiler's checks. They have not been formally proved, and the compiler is young, so treat it as you would any new toolchain.

Lexell is aimed at command-line tools and database-backed services. It has a built-in 38-digit decimal type and clients for PostgreSQL, SQL Server, Oracle, SQLite and Redis. [LexDB](#lexdb), a SQL database server written in Lexell, is its largest program.

I wanted the quick edit–compile–run loop I remember from Turbo Pascal, with runtime performance competitive with established native toolchains. The [benchmarks](#performance) compare compile time and generated code with Rust, and the regex, JSON, jq, Markdown, decimal and command-line programs with their usual external tools.

**In active development.** The language and library APIs may change. The native target is Linux x86-64-v3, which includes AVX2. You can try it today from a source checkout.

[Performance](#performance) · [Concurrency](#concurrency-without-threads-or-locks) · [Quick start](#quick-start) · [LexDB](#lexdb) · [Why I built Lexell](#why-i-built-lexell) · [Documentation](#documentation)

## Performance

Measured on an AMD Ryzen 7 8745HS running Linux 7.2 (27 November 2026). Full tables, caveats and reproduction steps are in the [performance report](PERFORMANCE.md) and [LexDB performance](lexell/docs/lexdb/performance.md).

| Area | Headline result | Details |
|---|---|---|
| Compile time | Hello world in 14 ms (4.1× faster than Rust); 9-program suite in 140 ms (26× faster) | [PERFORMANCE.md](PERFORMANCE.md) |
| Generated code (`-O`) | Ahead of Rust on 12 of 19 shared benchmarks (level on 2); ahead of warmed-up Java on most CPU benchmarks | [PERFORMANCE.md](PERFORMANCE.md) |
| Peak memory | 2–31 MB across the benchmark suite (vs. 50 MB–1.4 GB on the JVM) | [PERFORMANCE.md](PERFORMANCE.md) |
| HTTP/1.1 & HTTP/2 server | Up to 235k req/s (`h2c`) and 181k req/s (TLS 1.3) on 1 core — 1.5–5.4× Go and up to 2.4× Node.js at 7–13 MB RSS | [PERFORMANCE.md](PERFORMANCE.md) |
| CLI tools & parsers | Faster than Go's `regexp`, `jq`, `eza`, `grep` and Python JSON | [PERFORMANCE.md](PERFORMANCE.md) |
| 38-digit `Decimal` | Faster than .NET `Decimal` on every operation and Java `BigDecimal` on 9 of 10 | [PERFORMANCE.md](PERFORMANCE.md) |
| LexDB vs. PostgreSQL 18 | 2–3.5× faster on TPC-H and ClickBench analytics, 1.3–3.1× durable updates, 1.2–1.3× 4-core OLTP reads via replicas | [LexDB performance](lexell/docs/lexdb/performance.md) |

Where others are ahead: Rust leads on floating-point (`nbody`), sorting with closures, bit-packed decode and hash aggregation; Java leads on allocation-heavy microbenchmarks and vectorised matrix multiplication; PostgreSQL leads on single-process multi-threaded reads and high-concurrency multi-statement read-write transactions. See the linked reports for the full breakdown.

## Concurrency without threads or locks

A Lexell server runs each connection as a lightweight task on one thread, and you write the handler as plain sequential code. When a task waits for a socket, a database reply or a timer, it parks, and the event loop runs another task until the reply arrives. There is no `async` or `await` to write, and a function that waits looks like any other function.

Only one task runs at a time, and a task can only be switched out where it waits. Code between two waits cannot be interrupted, so there are no data races and nothing to lock: no mutexes, no atomics, no lock ordering.

### One thread per process, by design

A single thread is not a limitation to be fixed later. On a multicore machine, threads that share memory pay for it all the time: in locks, in atomic counters, and in cache lines passed back and forth between cores. Those costs grow as cores are added. The fastest servers avoid them by sharing nothing between cores: nginx runs one process per core, Redis executes commands on one thread, and LMAX matched millions of orders a second on one. A Lexell process pays none of these costs. Reference counts are plain increments, the allocator takes no lock, and nothing waits for another core.

To use more cores, run more processes. Each worker has its own event loop, memory and connections, and they share nothing but the database, so adding a core adds capacity without adding a lock. A crash stops one worker, not the server. `task.workers` starts the workers, restarts any that crash and stops them together. What you give up is memory that every core reads and writes, such as one in-process cache for all workers. Keep that state in the database or Redis, where it is shared safely already. For CPU-bound work on one batch, `par.map` spreads a closure that the compiler has proved pure over a pool of threads ([design](lexell/design/parallel.md)).

This web server runs that way on four cores:

```lexell
import "httpserver" as http
import "net"
import "postgres"
import "task"

type App = value record { db: postgres.Pool }

// Reads as blocking code. Waiting for a pooled connection or for the reply
// parks this request's task; the event loop serves other requests meanwhile.
fn count(db: &postgres.Pool): Result[int, postgres.Error] {
    var c = try db.acquire()
    let rows = try c.conn().query("SELECT count(*) FROM orders", &[])
    return rows.int(0, 0)
}

fn orders(app: &App, rq: mut &http.Request, w: mut &http.Response): Result[Unit, http.Error] {
    match count(&app.db) {
        Ok(n) { return w.text(&("orders: " + n.toStr() + "\n")) }
        Err(e) {
            w.status(503)
            return w.text(&(e.toStr() + "\n"))
        }
    }
}

fn main() {
    // Four processes, one per core, each with its own event loop, listener and
    // connection pool. They share nothing, so nothing needs a lock.
    let ends = task.workers(4, fn(i: int) {
        let ln = net.listenReusePort("127.0.0.1:8080").unwrap()
        let db = postgres.newPool("host=/tmp port=5433 dbname=lexdb", 8).unwrap()
        var r = http.router[App]()
        r.handle("GET /orders", orders)
        http.serve(ln, App{db: db}, r, http.defaults()).unwrap()
    })
}
```

The same design runs through the library and LexDB:

- **HTTP/1.1, HTTP/2 and HTTPS server.** One task per connection (and per HTTP/2 stream), with keep-alive, multiplexing, graceful shutdown, and shared-nothing worker processes on one port. It outperforms Go's `net/http` and Node.js across both HTTP/1.1 and HTTP/2 at a fraction of the memory footprint ([benchmarks](PERFORMANCE.md)).
- **Database clients.** The PostgreSQL, SQL Server, Oracle and Redis clients speak their wire protocols on the event loop, so a query parks only the task that sent it, and their connection pools hand out connections the same way. SQLite has only a blocking C API, so its calls run on a helper thread, which runs only C code, while the task waits.
- **LexDB.** Every session runs as a task on one thread. Commits never yield partway through, so the engine needs no page latches or thread locks, and commits arriving in the same event-loop turn share a single flush to disk. Large analytical scans parallelise across cores with `par.map`, while OLTP reads scale out via separate read-only replica processes following the master's log. See [LEXDB.md](LEXDB.md) and [LexDB performance](lexell/docs/lexdb/performance.md) for architecture and PostgreSQL 18 benchmarks.

The event loop uses `io_uring` for sockets and files by default and falls back automatically to `epoll` plus a helper pool where `io_uring` is unavailable, with no code changes.

The [concurrency design](lexell/design/concurrency.md) explains the choices, what they cost and what is given up.

## Quick start

On Linux x86-64-v3, install GCC and run the following from the repository root. The first command builds `lxlc` from the checked-in C seed. The second compilation step emits a native executable directly.

```sh
lexell/compiler/build.sh

cat > totals.lxl <<'LXL'
fn main() {
    let subtotal = 19.99m
    let delivery = 4.50m
    println((subtotal + delivery).toStr())
}
LXL

lexell/compiler/out/lxlc totals.lxl --native -o totals
./totals
```

It prints `24.49`. Change `4.50m` to `0.01m`, compile again, and the result is `20.00`. The `m` suffix gives these literals the `Decimal` type.

To see a larger program, build the [jq port](lexell/cmd/README.md#jq) and give it a line of JSON:

```sh
lexell/compiler/out/lxlc lexell/cmd/jq.lxl --native -o lexell-jq
printf '%s\n' '{"order":{"total":24.49}}' | ./lexell-jq '.order.total'
```

This also prints `24.49`. The repository includes [other command-line tools, a Redis CLI and an HTTP server](lexell/cmd/README.md).

## LexDB

[LexDB](LEXDB.md) is a SQL database server written in Lexell, and the largest program in the repository. One executable speaks the PostgreSQL, SQL Server and Oracle wire protocols and SQL dialects over the same tables, so `psql`, `sqlcmd`, JDBC and the other usual clients connect unchanged. It runs every session as a task on one thread, with the same no-locks design as Lexell's servers, scales reads across cores with shared-nothing replica processes, and handles both transactions and analytics in one engine.

[LEXDB.md](LEXDB.md) introduces it, with its features and benchmarks against PostgreSQL 18. The [LexDB documentation](lexell/docs/lexdb/README.md) has the SQL references for all three dialects.

## Why I built Lexell

I’ve been writing software professionally since the 1990s. I remember how fast Turbo Pascal felt. I followed Niklaus Wirth’s work from Pascal to Oberon because I admired his insistence on simplicity. Years later, Rust got me interested in checked ownership, though on my laptop the toolchain felt larger and slower than I wanted. Then I came across [group borrowing](https://verdagon.dev/blog/valen-group-borrowing) on Hacker News. I wondered whether I could get that quick edit–compile–run loop back in a language with braces, a small compiler and borrow checking without lifetime annotations.

Much of my career has been in developing software for Finance. A lot of the web applications I’ve worked on run a query and turn the result into something useful for the person at the other end. That’s why Lexell has a 38-digit `Decimal` and clients for the databases I’ve worked with. If I read an amount from a database and put it in a report, I want to carry it through as a decimal all the way.

When I worked in CFD/FX trading, I used to enjoy working out where to put the locks. Using Node.js showed me how far an event loop could take an application that spends much of its time waiting for I/O. In Lexell I wanted to write the handler in the order it runs. When a task waits on supported I/O, the event loop can run another task on the same thread. To use more cores, run separate worker processes in the style of nginx. The [concurrency design](lexell/design/concurrency.md) explains how that works and where the trade-offs are.

The current Lexell grew out of an Oberon dialect and an ownership fork called `obo`. It restarted on 2 November 2026, carrying over the ownership model and adding generics, and took the name Lexell on 8 November 2026. The [project history](HISTORY.md) covers both predecessors and the restart.

## What’s in the repository

| Area | What you’ll find |
|---|---|
| Language | Modules, records with methods, generics, structural interfaces (`box I` / `&I`), slices, borrowed and escaping (`box fn`) closures, string interpolation, derived `Serialize`/`Deserialize`, `Option`, `Result`, `Error`, `try`, `match` and destructors. |
| Ownership | Single ownership and checked borrows, for strings too: a `str` is owned and moves, `&str` borrows it, and `clone()` copies it. Reference counting is opt-in: `rc T` is a counted, immutable handle for values you want to share. |
| Compiler | A self-hosted compiler that emits x86-64 ELF directly, with devirtualization for interface values and escaping closures. A C backend shares the same IR for bootstrapping and differential testing. |
| Standard library | Collections, composable `io.Read`/`io.Write` streams, time zones, regex, JSON, YAML 1.2, CSV/TSV, CommonMark, `zlib`/`zstd` compression, modern crypto, HTTP/1.1 & HTTP/2 servers and clients, TLS, Redis and tasks. |
| Data stores | Clients for SQLite, PostgreSQL, SQL Server, Oracle and Redis. PostgreSQL, SQL Server and Oracle use their native wire protocols; Redis speaks RESP2 and RESP3. The SQL clients can decode rows into your own record types in bounded batches. |
| Programs | A jq port, a CommonMark renderer, an HTTP/1.1 & HTTP/2 (and HTTPS) server and load client, a Redis client and `redis-cli`, and ports of everyday tools including `grep`, `eza` and `zoxide`. |

See the [database streaming design](lexell/design/db-streaming.md) for an example of binding columns and reading rows into a caller-owned buffer.

## Documentation

| Start here | What it covers |
|---|---|
| [Language specification](lexell/SPEC.md) | Syntax, types, ownership and borrowing, concurrency and runtime behaviour. |
| [Standard library reference](lexell/lib/README.md) | Modules and APIs. |
| [Programs and examples](lexell/cmd/README.md) | How to build and run the programs, with supported behaviour and test instructions. |
| [Database streaming](lexell/design/db-streaming.md) | How typed row mapping and bounded batches work. |
| [Concurrency](lexell/design/concurrency.md) | Tasks, the event loop and worker processes. |
| [LexDB](LEXDB.md), [documentation](lexell/docs/lexdb/README.md), and [performance](lexell/docs/lexdb/performance.md) | Introduction, shared-nothing design, benchmarks, materialized views, skipping indexes, and SQL references for all three doors. |
| [Lexell performance](PERFORMANCE.md) and [native versus C](lexell/design/native-vs-c.md) | Language, library, HTTP server, and CLI measurements, caveats, and the two backends. |
| [Repository guide](lexell/README.md) and [project history](HISTORY.md) | The source tree, test suites and how the project evolved. |

## Status and feedback

The specification is a draft. Record the commit you build from if you want to reproduce an example later. The compiler finds the standard library in the source tree. Some library features use system libraries, including OpenSSL for TLS and crypto, `libz` and `libzstd` for compression, and `libsqlite3` for SQLite.

If you try Lexell, I’d like to know what you built and where you got stuck. For a bug, include the commit, your platform, a small reproducer and the output you expected. For a library or documentation gap, an example of what you were trying to do is a good place to start.

Contributors can run the quick test suite from the repository root with `lexell/tools/gate.sh quick`. See the [repository guide](lexell/README.md) for the other checks.

## License

Lexell is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text and [NOTICE](NOTICE) for copyright information. Unless a file says otherwise, the compilers, runtimes, tools, tests and documentation are covered.

Contributions are accepted under the same license. By contributing, you agree that your contribution is licensed under the Apache License, Version 2.0.
