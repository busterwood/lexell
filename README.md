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

Measured on one AMD Ryzen 7 8745HS running Linux 7.2, 24–26 November 2026. The [performance report](PERFORMANCE.md) has every result, what each benchmark does, and how to reproduce them.

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

LexDB is a full-featured, single-binary SQL database server written in Lexell (`lexell/cmd/lexdb.lxl`), designed from the ground up for NVMe/SSD storage to handle both OLTP and analytical workloads in one engine — with no locks, no page latches, and no separate analytics cluster.

One server speaks **three native wire protocols and SQL dialects simultaneously** — PostgreSQL, SQL Server (TDS / T-SQL), and Oracle (TNS / PL/SQL) — over the same tables. Existing clients and drivers (`psql`, `pgbench`, JDBC, ODBC, `sqlcmd`, and Lexell's own clients) connect unchanged.

### Highlights

- **Lock-free, crash-safe storage on `io_uring`.** Every session runs as a lightweight task on one thread, eliminating page latches and lock contention. Copy-on-write B+trees prevent torn writes on power loss, durable commits group-flush automatically, transactions default to `SERIALIZABLE` (with opt-in `READ COMMITTED`), and separate read-replica processes scale reads linearly across cores.
- **Hybrid OLTP + columnar analytics.** Tables pack into columnar leaves and execute through vectorized batch operators, adaptive two-level hash aggregation, and a cost-based optimizer — supporting joins, window functions, CTEs, subqueries, and full ACID transactions on the same data.
- **Incremental [materialized views & transparent query rewrite](lexell/docs/lexdb/materialized-views.md).** Views stay current automatically in under a millisecond (`FAST` incremental updates), support contention-free real-time delta merging for hot keys, cascading rollup DAGs, and composable HyperLogLog++ / t-digest sketches, and transparently accelerate unmodified base-table queries with zero application changes.
- **Automatic zone maps & [data skipping indexes](lexell/docs/lexdb/skipping-indexes.md).** Always-on hierarchical min/max pruning (including dynamic Top-N) plus optional `minmax`/`brin`, `set`, `bloom_filter`, `ngrambf`, and `tokenbf` skipping indexes cut selective point and `LIKE '%substring%'` filters by up to **4.1×** with tiny storage overhead and zero write slowdown.
- **Unique & rare SQL features across doors.** SQL-standard [`CREATE ASSERTION`](lexell/docs/lexdb/assertions.md) cross-table invariants (currently only in Oracle 26ai, available here in all three doors), transactional event streaming via [`SELECT ... WAIT`](lexell/docs/lexdb/sql/postgresql/select-wait.md) (enabled by lightweight cooperative tasks so thousands of consumers can wait for commits without polling) plus replica [`WAIT FOR LSN`](lexell/docs/lexdb/sql/postgresql/wait-for-lsn.md), SQL:2016 [`MATCH_RECOGNIZE`](lexell/docs/lexdb/sql/postgresql/match-recognize.md) row pattern recognition (in PostgreSQL and Oracle doors), SQL:2023 [`GRAPH_TABLE`](lexell/docs/lexdb/sql/postgresql/graph-table.md) property graphs, plus secondary B+tree indexes, foreign keys, views, stored procedures and functions, roles, and fast native bulk loading (`COPY`, `bcp`/`SqlBulkCopy`, Oracle array DML).

### Performance against PostgreSQL 18

| Workload | LexDB | PostgreSQL 18 | Result |
|---|---:|---:|---:|
| **TPC-H SF1** (22 queries, 1 core) | 7.20 s | 14.67 s (1 core) / 8.84 s (4 proc) | **2.0× faster** than 1 core (22/22); **1.23× faster** than 4 proc |
| **ClickBench 1M** (43 queries, 105 cols, 1 core) | 14.10 s | 22.36 s (1 core) / 11.33 s (4 proc) | **1.59× faster** than 1 core (40/43 level or ahead) |
| **ClickBench 1M + 8 MVs** (unmodified queries, 1 core) | **9.07 s** | 11.33 s (4 proc) | **1.25× faster than 4-core PG on one core** (21 rewritten) |
| **35 Analytic Queries** (1M rows, 1 core) | 0.46× CPU / 0.91× wall | 1 core / 4 proc | **2.2× less CPU** than 1 core; ahead of 4 proc on wall time |
| **Durable updates** (pgbench / sysbench, 1–32 clients) | up to 63.3k / 54.2k/s | 25.7k / 23.0k/s | **2.4–3.1× faster** (indexed updates **1.3–2.5×**) |
| **Point selects** (3 read replicas, 32 clients) | 470–490k/s (pgbench) | 397k/s (4 cores) | **1.18–1.23× faster** (sysbench **1.05×**, 29% less CPU) |
| **Bulk `\copy` loads** (5 cases, 1M–10M rows) | 0.24–2.44 s | 0.61–5.93 s | **1.1–2.7× faster** on all 5 workloads |
| **Materialized view maintenance** (1M rows, 1-row insert) | **0.43–0.66 ms** (`FAST`) | 60–369 ms (`REFRESH`) | **90–780× faster** incremental updates |

PostgreSQL is ahead on single-process multi-thread reads and multi-statement read-write blocks.

Read **[LEXDB.md](LEXDB.md)** for the full introduction (architecture, scaling with read replicas, materialized views, skipping indexes, and quick start), the **[LexDB performance report](lexell/docs/lexdb/performance.md)** for query-by-query numbers, or browse the [LexDB documentation](lexell/docs/lexdb/README.md) and [internals](lexell/design/lexdb.md).

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
| [LexDB](LEXDB.md), [documentation](lexell/docs/lexdb/README.md), and [performance](lexell/docs/lexdb/performance.md) | Introduction, shared-nothing design, benchmarks, materialized views, skipping indexes, and SQL references for all three doors. |
| [Lexell performance](PERFORMANCE.md) and [native versus C](lexell/design/native-vs-c.md) | Language, library, HTTP server, and CLI measurements, caveats, and the two backends. |
| [Repository guide](lexell/README.md) and [project history](HISTORY.md) | The source tree, test suites and how the project evolved. |

## Status and feedback

The specification is a draft. Record the commit you build from if you want to reproduce an example later. The compiler finds the standard library in the source tree. Some library features use system libraries, including OpenSSL for TLS and libsqlite3 for SQLite.

If you try Lexell, I’d like to know what you built and where you got stuck. For a bug, include the commit, your platform, a small reproducer and the output you expected. For a library or documentation gap, an example of what you were trying to do is a good place to start.

Contributors can run the quick test suite from the repository root with `lexell/tools/gate.sh quick`. See the [repository guide](lexell/README.md) for the other checks.

## License

Lexell is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text and [NOTICE](NOTICE) for copyright information. Unless a file says otherwise, the compilers, runtimes, tools, tests and documentation are covered.

Contributions are accepted under the same license. By contributing, you agree that your contribution is licensed under the Apache License, Version 2.0.
