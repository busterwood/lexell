# Lexell

Lexell is a small, straightforward language for command-line tools and database-backed services. It writes Linux executables directly, checks ownership and borrowing at compile time, and has a built-in decimal type.

I wanted the quick edit–compile–run loop I remember from Turbo Pascal, with runtime performance competitive with established native toolchains. The compiler is about 3 MB and rebuilds itself in about 0.48 seconds. The [benchmarks](#performance) compare compile time and generated code with Rust, and the regex, JSON, jq, Markdown, decimal and command-line programs with their usual external tools.

**In active development.** The language and library APIs may change. The native target is Linux x86-64-v3, which includes AVX2. You can try it today from a source checkout.

[Performance](#performance) · [Quick start](#quick-start) · [Why I built Lexell](#why-i-built-lexell) · [Documentation](#documentation)

## Performance

- **Compile time.** Hello world compiles in about 14 ms, against Rust's 46 ms, and produces a 20 KB native executable. The nine benchmark programs compile in about 131 ms, 23 times faster than Rust's 3.05 s.
- **Generated code.** With `-O`, Lexell is faster than Rust on six of the ten microbenchmarks and level on three more. It runs the tree and list benchmarks about 2.5 times faster, strings and maps 1.8 times, the sieve 1.5 times and allocation 1.3 times. Rust is ahead on the token scanner.
- **Other programs.** Lexell is faster than Go's regexp on all eight regex patterns, from twice as fast to several hundred times faster. Its jq is 1.4 to 2.2 times faster than jq 1.7.1 on every filter, with identical output. It parses JSON 2.1 times faster than Python and writes it about 1.4 times faster. Its grep is 1.4 to 1.5 times faster than GNU grep, and its eza lists a tree 3.3 times faster than eza. Lexell is behind cmark on Markdown, Python on JSON queries, Rust's regex crate on most patterns, and GNU sort.
- **Decimal.** Against Java `BigDecimal`, Lexell parses 38-digit values 4.6 times faster and formats them 3.3 times faster, multiplies 19-digit values 1.5 times faster, and adds 1.1 to 1.35 times faster. Against .NET `System.Decimal`, it divides 4.4 times faster, parses 2.7 times faster, formats 1.7 times faster, compares 1.6 times faster and multiplies 1.2 times faster. Java is ahead on division and comparison, and .NET slightly ahead on 19-digit addition.

The [performance report](PERFORMANCE.md) gives the full results, workload definitions and reproduction commands. These measurements come from one AMD Ryzen 7 8745HS machine running Linux 7.2 (not WSL2), on 22 November 2026.

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
| [Performance](PERFORMANCE.md) and [native versus C](lexell/design/native-vs-c.md) | Measurements, caveats and the two backends. |
| [Repository guide](lexell/README.md) and [project history](HISTORY.md) | The source tree, test suites and how the project evolved. |

## Status and feedback

The specification is a draft. Record the commit you build from if you want to reproduce an example later. The compiler finds the standard library in the source tree. Some library features use system libraries, including OpenSSL for TLS and libsqlite3 for SQLite.

If you try Lexell, I’d like to know what you built and where you got stuck. For a bug, include the commit, your platform, a small reproducer and the output you expected. For a library or documentation gap, an example of what you were trying to do is a good place to start.

Contributors can run the quick test suite from the repository root with `lexell/tools/gate.sh quick`. See the [repository guide](lexell/README.md) for the other checks.

## License

Lexell is licensed under the Apache License, Version 2.0. See [LICENSE](LICENSE) for the full text and [NOTICE](NOTICE) for copyright information. Unless a file says otherwise, the compilers, runtimes, tools, tests and documentation are covered.

Contributions are accepted under the same license. By contributing, you agree that your contribution is licensed under the Apache License, Version 2.0.
