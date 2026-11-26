# Lexell

Lexell is a small, straightforward language for command-line tools and database-backed services. It writes Linux executables directly, checks ownership and borrowing at compile time, and has a built-in decimal type. Servers handle thousands of connections as cooperative tasks, written as plain sequential code, with no threads, locks or `async`.

I wanted the quick edit–compile–run loop I remember from Turbo Pascal, with runtime performance competitive with established native toolchains. The compiler is about 3 MB and rebuilds itself in about half a second. The [benchmarks](#performance) compare compile time and generated code with Rust, and the regex, JSON, jq, Markdown, decimal and command-line programs with their usual external tools.

**In active development.** The language and library APIs may change. The native target is Linux x86-64-v3, which includes AVX2. You can try it today from a source checkout.

[Performance](#performance) · [Concurrency](#concurrency-without-threads-or-locks) · [Quick start](#quick-start) · [LexDB](#lexdb) · [Why I built Lexell](#why-i-built-lexell) · [Documentation](#documentation)

## Performance

### Compile time

| | Lexell | Rust | Lexell is |
|---|---:|---:|---:|
| Hello world (a 20 KB executable) | 13 ms | 48 ms | 3.6× faster |
| The nine benchmark programs | 131 ms | 3.19 s | 24× faster |

### Generated code

Lexell with `-O` against Rust and against Java on a warmed-up JVM (20 benchmarks):

| Benchmark | Faster than Rust | Faster than Java |
|---|---:|---:|
| Allocation | 11× | |
| Lists and trees | 5.4–5.7× | |
| Strings | 3.5× | |
| Maps | 1.9× | |
| Recursive calls (`fib`) | 1.67× | 1.15× |
| Matrix multiplication | 1.62× | |
| Sieve | 1.52× | 1.73× |
| Interpreter loop | 1.27× | 2.0× |
| Array indexing | 1.34× | 1.08× |
| Bit-packed column decode | | 1.39× |
| Varint CSV parsing | 1.06× | 1.41× |
| Switching between tasks | | 4.2× (1.9× Go) |
| Token scanner | | 1.8× |
| Sorting with closures | | 2.1× |
| Floating point (`nbody`) | | 1.04× |
| Loops | level | 1.12× |
| B-tree | level | |
| Peak memory (19 of 20 programs) | | 2–31 MB against the JVM's 51 MB–1.4 GB |

Rust is ahead on floating point (`nbody`), sorting with closures, bit-packed decode (`bitpack`), hash aggregation (`hashagg`), and slightly on the token scanner (1.07×) and expression AST evaluation (`enum_eval`, 1.11×). Java is ahead on the allocation-heavy programs, maps, B-tree (1.03×), hash aggregation, expression evaluation, and vectorised matrix multiplication.

### Real programs

| Program | Compared with | Lexell is |
|---|---|---:|
| Regex, all eight patterns | Go's regexp | 2× to several hundred× faster |
| jq, every filter (identical output) | jq 1.7.1 | 1.5–2.3× faster |
| Tree listing | eza | 4.6× faster |
| JSON parsing | Python | 1.8× faster |
| grep | GNU grep | 1.5–1.7× faster |
| JSON writing | Python | 1.4–1.5× faster |

Lexell is slightly behind cmark on long Markdown documents (ahead on the spec examples), behind Python on JSON queries, Rust's regex crate on most patterns, and GNU sort.

### Decimal

| Operation | Faster than Java `BigDecimal` | Faster than .NET `Decimal` |
|---|---:|---:|
| Parse | 4.6× (38 digits) | 2.9× |
| Format | 3.2× (38 digits) | 1.7× |
| Divide | | 4.5× |
| Compare | | 1.6× |
| Multiply | 1.5× (19 digits) | 1.3× |
| Add | 1.15–1.34× | |

Java is ahead on division and comparison, and .NET is slightly ahead on 19-digit addition.

Measured on one AMD Ryzen 7 8745HS running Linux 7.2, 24–25 November 2026. The [performance report](PERFORMANCE.md) has every result, what each benchmark does, and how to reproduce them.

## Concurrency without threads or locks

A Lexell server runs each connection as a lightweight task on one thread, and you write the handler as plain sequential code. When a task waits for a socket, a database reply or a timer, it parks, and the event loop runs another task until the reply arrives. There is no `async` or `await` to write, and a function that waits looks like any other function.

Only one task runs at a time, and a task can only be switched out where it waits. Code between two waits cannot be interrupted, so there are no data races and nothing to lock: no mutexes, no atomics, no lock ordering. To use more cores, run several worker processes, as nginx does. Each has its own event loop, memory and connections, and they share nothing, so there is still nothing to lock. `task.workers` starts them, restarts any that crash and stops them together.

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

- **HTTP and HTTPS server.** One task per connection, with keep-alive, graceful shutdown, and worker processes sharing one port. On one core it serves 1.5 times as many requests a second as Go's `net/http` and 1.2 to 1.3 times as many as Node.js, each also on one core. At 100 clients its p99 latency is 0.61 ms, against Node's 0.87 ms and Go's 3.1 ms.
- **Database clients.** The PostgreSQL, SQL Server, Oracle and Redis clients speak their wire protocols on the event loop, so a query parks only the task that sent it, and their connection pools hand out connections the same way. SQLite has only a blocking C API, so its calls run on a helper thread, which runs only C code, while the task waits.
- **LexDB.** The database runs every session as a task on one thread. A commit never waits partway through, so no other session can run inside it, and the engine needs no latches on its pages and no locks to keep threads out of each other's way. Commits that arrive in the same turn of the event loop share one flush to disk. Read-only replicas are separate processes that follow the master's log, the same way LexDB uses more cores.

The event loop uses io_uring for sockets and files by default, where the kernel allows it. On older kernels, and in containers that block io_uring, it falls back to epoll and a pool of helper threads for file I/O, with no change to your code and little loss: in LexDB's measurements the fallback kept about seven-eighths of io_uring's select rate and matched it on updates.

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

LexDB is a SQL database server written in Lexell (`lexell/cmd/lexdb.lxl`). It is designed for SSDs and NVMe drives, consumer drives first, and keeps its data on disk with memory as a cache. Pages are copy-on-write, so a write torn by a power cut can never damage a page in use, and its disk I/O goes through io_uring where the kernel allows it. It speaks three wire protocols: PostgreSQL's, SQL Server's TDS and Oracle's TNS, each with its own SQL dialect. Existing clients and drivers, such as `psql`, `pgbench`, the JDBC drivers and Lexell's own database clients, connect unchanged. Read-write transactions default to serializable isolation (with opt-in `READ COMMITTED`), and read-only transactions read from a snapshot. Tables are stored by column and queries run over batches of rows, planned by a cost-based optimizer. A server can run read-only replicas as separate processes.

On TPC-H at scale factor 1, LexDB on one core finishes the 22 queries in less total time than PostgreSQL on four processes (7.44 against 8.84 s) and takes 0.51 of PostgreSQL's time on one core (geometric mean, 22 of 22 faster than one core; 0.82 against four processes). On ClickBench (1M rows, 43 queries on a 105-column wide table), LexDB on one core beats PostgreSQL on one core on both total wall time (17.06 against 22.36 s) and geometric mean (0.75 wall, 0.70 CPU; 40 of 43 level or ahead; adding eight general-purpose `ENABLE QUERY REWRITE` materialized views transparently rewrites 21 unmodified queries — including exact `COUNT(DISTINCT)`, wide `URL`/`SearchPhrase` keys, and derived `GROUP BY` — cutting total wall time to 11.80 s and geomean to 0.10 vs one core / 0.23 vs four processes, with 5.6–10.3 ms live incremental writes across all 8 views, and optional hierarchical data skipping indexes cut selective point and `LIKE` filters by up to 4.07×). On sysbench OLTP (1M rows), LexDB leads PostgreSQL 18 on all six workloads at 1 thread (`1.08×`–`2.82×`), commits durable updates faster from a single process at every concurrency up to 32 threads (`2.40×`–`3.15×` non-indexed, `1.28×`–`2.54×` indexed; pgbench 1M updates `2.51×`–`2.71×` up to 67.0k/s) as well as `oltp_write_only` through 8 threads (`1.37×`–`1.99×`), and with three read replicas beats four-core PostgreSQL on pgbench point selects (`500–504k/s` vs `408k/s`, `1.22×`–`1.23×`) and sysbench `oltp_point_select` (`1.13×`) and `oltp_read_only` (`1.03×`) at 32 threads using 28–33% less CPU. On bulk `\copy` loads, LexDB beats PostgreSQL on all five workloads (`0.37×`–`0.68×`). Incremental materialized views (`FAST`, composable HyperLogLog++/t-digest sketches, `ON QUERY COMPUTATION`, and cascading rollup DAGs) build 40% faster than PostgreSQL on sketch rollups (`224` vs `372 ms`) and update in `0.48–0.72 ms` per row against `60–364 ms` for PostgreSQL `REFRESH MATERIALIZED VIEW`. PostgreSQL is ahead on single-process multi-thread reads and multi-statement read-write blocks ([details](PERFORMANCE.md#lexdb)).

For now, the [program notes](lexell/cmd/README.md#lexdb) cover running it, and the [design](lexell/design/lexdb.md) covers how it works. A full LexDB guide is in progress.

## Why I built Lexell

I’ve been writing software professionally since the 1990s. I remember how fast Turbo Pascal felt. I followed Niklaus Wirth’s work from Pascal to Oberon because I admired his insistence on simplicity. Years later, Rust got me interested in checked ownership, though on my laptop the toolchain felt larger and slower than I wanted. Then I came across [group borrowing](https://verdagon.dev/blog/valen-group-borrowing) on Hacker News. I wondered whether I could get that quick edit–compile–run loop back in a language with braces, a small compiler and borrow checking without lifetime annotations.

Much of my career has been in developing software for Finance. A lot of the web applications I’ve worked on run a query and turn the result into something useful for the person at the other end. That’s why Lexell has a 38-digit `Decimal` and clients for the databases I’ve worked with. If I read an amount from a database and put it in a report, I want to carry it through as a decimal all the way.

When I worked in CFD/FX trading, I used to enjoy working out where to put the locks. Using Node.js showed me how far an event loop could take an application that spends much of its time waiting for I/O. In Lexell I wanted to write the handler in the order it runs. When a task waits on supported I/O, the event loop can run another task on the same thread. To use more cores, run separate worker processes in the style of nginx. The [concurrency design](lexell/design/concurrency.md) explains how that works and where the trade-offs are.

The current Lexell grew out of an Oberon dialect and an ownership fork called `obo`. It restarted on 2 November 2026, carrying over the ownership model and adding generics, and took the name Lexell on 8 November 2026. The [project history](HISTORY.md) covers both predecessors and the restart.

## What’s in the repository

| Area | What you’ll find |
|---|---|
| Language | Modules with explicit imports, records with methods, generics, structural interfaces, slices, closures, `Option`, `Result`, `try`, `match` and destructors. |
| Ownership | Single ownership and checked borrows, for strings too: a `str` is owned and moves, `&str` borrows it, and `clone()` copies it. Reference counting is opt-in: `rc T` is a counted, immutable handle for values you want to share. |
| Compiler | A self-hosted compiler that writes x86-64 ELF directly. The C backend shares the same intermediate representation and is used for bootstrapping and differential testing. |
| Standard library | Collections, text and file I/O, time zones, regex, JSON, CommonMark, HTTP and HTTPS servers and clients, TLS, Redis and tasks. |
| Data stores | Clients for SQLite, PostgreSQL, SQL Server, Oracle and Redis. PostgreSQL, SQL Server and Oracle use their native wire protocols; Redis speaks RESP2 and RESP3. The SQL clients can decode rows into your own record types in bounded batches. |
| Programs | A jq port, a CommonMark renderer, an HTTP/1.1 (and HTTPS) server and load client, a Redis client and `redis-cli`, and ports of everyday tools including `grep`, `eza` and `zoxide`. |

See the [database streaming design](lexell/design/db-streaming.md) for an example of binding columns and reading rows into a caller-owned buffer.

## Documentation

| Start here | What it covers |
|---|---|
| [Language specification](lexell/SPEC.md) | Syntax, types, ownership and borrowing, concurrency and runtime behaviour. |
| [Standard library reference](lexell/lib/README.md) | Modules and APIs. |
| [Programs and examples](lexell/cmd/README.md) | How to build and run the programs, with supported behaviour and test instructions. |
| [Database streaming](lexell/design/db-streaming.md) | How typed row mapping and bounded batches work. |
| [Concurrency](lexell/design/concurrency.md) | Tasks, the event loop and worker processes. |
| [LexDB](lexell/cmd/README.md#lexdb) and [its design](lexell/design/lexdb.md) | Running the database server, and how it works. |
| [Performance](PERFORMANCE.md) and [native versus C](lexell/design/native-vs-c.md) | Measurements, caveats and the two backends. |
| [Repository guide](lexell/README.md) and [project history](HISTORY.md) | The source tree, test suites and how the project evolved. |

## Status and feedback

The specification is a draft. Record the commit you build from if you want to reproduce an example later. The compiler finds the standard library in the source tree. Some library features use system libraries, including OpenSSL for TLS and libsqlite3 for SQLite.

If you try Lexell, I’d like to know what you built and where you got stuck. For a bug, include the commit, your platform, a small reproducer and the output you expected. For a library or documentation gap, an example of what you were trying to do is a good place to start.

Contributors can run the quick test suite from the repository root with `lexell/tools/gate.sh quick`. See the [repository guide](lexell/README.md) for the other checks.

## License

Lexell is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text and [NOTICE](NOTICE) for copyright information. Unless a file says otherwise, the compilers, runtimes, tools, tests and documentation are covered.

Contributions are accepted under the same license. By contributing, you agree that your contribution is licensed under the Apache License, Version 2.0.
