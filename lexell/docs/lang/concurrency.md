# Concurrent code: tasks, timers, sockets, C calls, `par.map`

Lexell runs Lexell code on one thread. Tasks are coroutines that switch where
they wait, a pool of helper threads runs blocking C calls, and `par.map`
spreads a pure closure over more cores. For several cores in a server, use
several processes. [idioms.md](idioms.md) sections 9 and 10 show the first
patterns; this page covers what they leave out. The rules are
[SPEC.md](../../SPEC.md) 16 and 12, the reasons
[design/concurrency.md](../../design/concurrency.md) and
[design/parallel.md](../../design/parallel.md), the API
`python3 lexell/tools/libapi.py task` (also `net`, `par`).

## The model

A task runs until it parks: at `wait`, `task.all`, `task.any`, `task.yield()`,
`task.sleep(ms)`, a `net` call that would block, a blocking extern, `par.map`,
and the end of a scope. The next runnable task then runs, first in first out. A
task that never parks keeps every other task and socket waiting: call
`task.yield()` in a long loop. `main` is the first task. Each task has its own
256 KiB stack (overflow is exit 4).

## Scopes, tasks and cancellation

`task.scope(f)` runs a closure with a `Scope` and returns when every task
started on it has finished; `task.scoped(f)` is the same for an `f` with a
result. `s.start(fn, arg)` gives a `Future[T]`; `s.spawn(fn, arg)` gives
nothing. A started task first runs when its starter parks. The task function is
a plain `fn(A): T`, `arg` is moved in, and a function with no result is
rejected (`type parameter T cannot be inferred as no result`): return `0`. A
closure cannot move a captured variable into a task, so make the value inside
the scope's closure.

- `f.wait()` and `f.waitFor(ms)` park and give `Result[T, Cancelled]`
  (`Cancelled`, `Abandoned` or `Timeout`). `task.all(fs)` gives the results in
  order; `task.any(fs)` the first to finish, and cancels the rest.
- A `Future` is owned. Dropping it cancels its task, and the scope still waits
  for it. Cancellation is cooperative: the task runs on until it next parks,
  then every wait (`yield` and `sleep` too) gives `Err(Cancelled)` and every
  `net` call fails with `ECANCELED`. Its drops always run. Cancelling a task
  cancels the scopes it has open, and a task started by a cancelled one starts
  cancelled. `task.cancelled()` asks. Ending a scope cannot be cancelled.

```lxl
import "task"

type Guard = record { name: str }

fn (g: mut &Guard) drop() { println("drop " + g.name) }

fn nap(ms: int): int {
    let g = Guard{name: "nap " + ms.toStr()}
    match task.sleep(ms) {
        Ok(_) { return ms }
        Err(_) { return -1 }                  // woken by a cancellation
    }
}

fn main() {
    let first = task.scoped(fn(s: mut &task.Scope): int {
        var fs: []task.Future[int] = []
        append(mut &fs, s.start(nap, 5000))
        append(mut &fs, s.start(nap, 10))
        return task.any(fs).unwrap()          // the loser is cancelled, and any waits for it
    })
    println("first " + first.toStr())
}
// expect: drop nap 10
// expect: drop nap 5000
// expect: first 10
```

## Promises, timers and deadlines

A `Promise[T]` is a future completed by hand: `task.promise[T]()` gives a
`Handoff` with both ends, `complete` never parks, and a promise dropped without
`complete` gives its future `Err(Abandoned)`. `task.within(ms, f)` gives the
calls in `f`, and in the tasks started during it, a deadline: once it passes,
each call that can park returns `Err(Timeout)` (`ETIMEDOUT` for `net`). The
earlier of nested deadlines wins, and the deadline ends with `f`. Timers fire in
the order of their times.

```lxl
import "task"

fn producer(p: task.Promise[str]): int {
    task.yield()
    p.complete("ready")
    return 0
}

fn say(ms: int): int {
    task.sleep(ms)
    println("woke " + ms.toStr())
    return 0
}

fn main() {
    task.scope(fn(s: mut &task.Scope) {
        let task.Handoff{promise: p, future: f} = task.promise[str]()
        s.spawn(producer, p)
        println(f.waitFor(2000).unwrap())
        s.spawn(say, 150)
        s.spawn(say, 50)
        s.spawn(say, 100)
    })
    let r = task.within(30, fn(): Result[Unit, task.Cancelled] { return task.sleep(5000) })
    println(r.unwrapErr().toStr())
}
// expect: ready
// expect: woke 50
// expect: woke 100
// expect: woke 150
// expect: timeout
```

## Shared state: `Shared`, `with`, `Weak`

`task.shared(v)` makes a counted handle, `sh.share()` another, and a handle
passed to a task is moved. The only access is `sh.with(fn(x: mut &T) { ... })`.
No other task runs during `with`, so it is not a lock, and nothing in it may
park: `yield`, `wait`, `sleep`, a `net` call, a blocking extern or `par.map` there
stops the program with exit 13, whether or not it would have parked, and so does
a `with` on a value whose `with` is open (`with` on different values may nest).
`sh.weak()` makes a `Weak[T]` that does not keep the value, and `w.upgrade()`
gives `Some(Shared[T])` while a handle exists. Use it for a pointer back to an
owner, because handles that form a cycle are refused.

```lxl
import "task"

type Parent = record { name: str }
type Child = record { parent: task.Weak[Parent] }

fn release(p: task.Shared[Parent]) {}            // the last strong handle: dropped here

fn main() {
    let p = task.shared(Parent{name: "root"})
    let c = Child{parent: p.weak()}
    match c.parent.upgrade() {                   // Some while a strong handle lives
        Some(sp) { sp.with(fn(x: mut &Parent) { println(x.name) }) }
        None {}
    }
    release(p)
    println(c.parent.upgrade().isSome())
}
// expect: root
// expect: false
```

## Sockets

`net.listen(addr)` (port 0 picks a free port, `localAddr()` tells which),
`accept`, `net.connect`, `read`, `write` and `writeStr` park the task until the
socket is ready. `closeWrite` ends the sending side, and `read` gives `Ok(0)` at
the end of the stream. A write to a closed peer is an error, never `SIGPIPE`.
Unix sockets, `listenReusePort`, name lookup and the `...For` variants that
ignore cancellation (for cleanup) are in `libapi.py net`.

```lxl
import "net"
import "task"

fn serve(ln: net.Listener): int {
    let c = ln.accept().unwrap()             // parks until the client connects
    var buf = array(64, byte(0))
    let n = c.read(mut &buf).unwrap()        // parks until bytes arrive
    c.writeStr("echo: " + strFromBytes(&buf[0..n])).unwrap()
    return n
}

fn main() {
    task.scope(fn(s: mut &task.Scope) {
        let ln = net.listen("127.0.0.1:0").unwrap()
        let addr = ln.localAddr()
        let srv = s.start(serve, ln)         // the listener moves into the server task
        let c = net.connect(&addr).unwrap()  // main is a task too: it parks, the server runs
        c.writeStr("ping").unwrap()
        var buf = array(64, byte(0))
        let n = c.read(mut &buf).unwrap()
        println(strFromBytes(&buf[0..n]))
        println(srv.wait().unwrap())
    })
}
// expect: echo: ping
// expect: 4
```

## Blocking C calls and the helper pool

An extern marked `blocking` ([c-interop.md](c-interop.md)) parks its task while
the C function runs on a helper thread, so other tasks go on. When no other task
could run, it runs at once on the program's thread. `LXL_HELPERS=n` sets the pool
(default 4, at most 64; `0` runs every call on the program's thread), and calls
beyond it queue first in first out. `errno` is the task's. A blocking call is not
a cancellation point: the task waits for it, unless it registered
`task.onCancelCall(f, arg)` with an `f` the C library documents as safe to call
meanwhile (`lib/sqlite.lxl` registers `sqlite3_interrupt`).

## `par.map`: more cores for pure work

`par.map(&xs, f)` gives what a loop of `f` over `xs` would, in order, computed
on `LXL_PAR` pool threads (default: the CPUs the process may use, less one, at
most 64; `0` runs it as a loop on the calling thread). The calling task parks
and cannot be cancelled meanwhile. A trap in `f` stops the program as in a loop.
`f` is written at the call, as a closure or a function's name, may read what it
captures and never change it, and must be a kernel: it and everything it can
reach do no I/O, no park, touch no `var` or `once` global, and call no extern
except the maths functions and those declared `pure`. A function whose result is
`never` may print and exit. The compiler checks this after instantiation and
names the chain of calls (`the closure is not a kernel: it can reach the global
hits`). It also refuses a closure that assigns a captured variable and one
passed in as a parameter. Map over chunks and merge on the caller; write the
closure's parameter and result types.

```lxl
import "par"

type Row = value record { price: int; qty: int }

extern "c" fn labs(x: int): int pure

fn sumChunk(rows: &[]Row, c: &[]int): int {
    var t = 0
    for i in c[0]..c[1] { t += rows[i].price * rows[i].qty }
    return t
}

fn main() {
    var rows: []Row = []
    for i in 0..1000 { append(mut &rows, Row{price: i, qty: 2}) }
    let chunks: [][]int = [[0, 250], [250, 500], [500, 750], [750, 1000]]
    let parts = par.map(&chunks, fn(c: &[]int): int { return sumChunk(&rows, c) })
    var total = 0
    for p in parts { total += p }
    println(total)
    println(par.map(&[-1, 2, -3], fn(x: &int): int { return labs(x) })[2])
}
// expect: 999000
// expect: 3
```

## The event loop

The native backend reads sockets and positioned file I/O through io_uring.
`LXL_URING=0`, or a kernel without it, gives epoll and the helper pool instead;
only CPU time and latency change (the gate runs the library tests both ways).
Before sleeping with tasks waiting for I/O the loop polls: `LXL_SPIN_US=N` polls
a fixed N microseconds, `0` never, `aN` adapts up to N (the default adapts up
to 50).

## Stops

| Exit | Meaning | Look for |
|---:|---|---|
| 13 | a park inside `Shared.with`, or a nested `with` on one value | the message names the `with` and the call |
| 14 | deadlock: every task is parked, no socket is waited on, no timer is pending | a promise nobody completes, tasks waiting for each other; the line is the call that found nothing to run |
| 15 | `task.workers` could not fork safely: a pool has started, another task exists, or the loop holds a socket or signal watch | call `workers` first in `main`; make the listener before it |

```lxl
import "task"

fn main() {
    let task.Handoff{promise: p, future: f} = task.promise[int]()
    println("waiting")
    println(f.wait().unwrap())            // p is alive and nobody will complete it
}
// expect: waiting
// exit: 14
```

A task parked in `sleep` or on a socket is not a deadlock.

## Several processes

`task.workers(n, f)` forks `n` processes and runs `f(i)` in process `i`. The
caller supervises them and runs no task: it restarts a crashed worker with a
backoff, gives up after too many crashes (`Err(GaveUp)`), and drains on
`SIGTERM`. `task.workersWith` takes a `WorkerPolicy`, `task.terminated()` waits
for the request to stop, and `task.workerReady()` marks a worker started.
Workers share no memory. Make a listener before the call to share one accept
queue (`let ln = net.listen(addr)`, then `task.workers(4, fn(i: int) { serve(&ln, i) })`).
`cmd/httpd.lxl` is the worked example; SPEC 16 has the signal functions and the
supervisor's rules.
