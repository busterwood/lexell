# Idioms

The patterns this codebase prefers, found in `lib/`, `cmd/` (jq, eza, grep,
httpd) and `design/`. Each has a **Do** that compiles and runs (checked by
`lexell/tools/doc_check.py`), a **Don't** and a **Why**. The language is in
[tour.md](tour.md), the messages in [errors.md](errors.md).

## 1. Read-only strings are `&str`; views to look, `.clone()` to keep

**Do**

```lxl
import "strings"

type Entry = record { key: str; value: str }

fn parse(line: &str): Option[Entry] {
    return match strings.cut(line, "=") {          // views of line
        Some(c) { Some(Entry{key: c.before.clone(), value: c.after.clone()}) }
        None { None }
    }
}

fn main() {
    let s = "name=" + "lexell"
    println(parse(s).unwrap().value)               // s is borrowed, not moved
}
// expect: lexell
```

**Don't** declare `line: str` for a function that only reads, or clone pieces
before you know you keep them (`strings.owned(&parts)`, `parts[0].clone() == "x"`).

**Why** a `str` parameter takes ownership, so a caller holding a `&str` cannot
call it. `split`, `cut`, `fields`, `lines` and `s[a..b]` return views that cost
nothing, and the compiler asks for `.clone()` exactly where a piece is stored.
`lxlc --borrow-report prog.lxl` lists the `str` parameters a program only reads;
the gate fails a library one. SPEC 4.1, 10.

## 2. Build strings in place

**Do**

```lxl
fn render(xs: &[]int): str {
    var out = ""
    for i in 0..len(xs) {
        if i > 0 { out += ", " }
        out.addInt(xs[i])
    }
    out.addLine("")
    return out
}

fn main() {
    print(render(&[1, 2, 3]))
}
// expect: 1, 2, 3
```

**Don't** write `out = out + piece` or `out += n.toStr()` in a loop.

**Why** `+=` on an owned string appends to its own buffer (linear over a run of
appends); `a + b` makes a new string each time. `addByte`, `addInt` and
`addLine` append without a temporary, `clear()` keeps the buffer for reuse and
`bytes()` lends it as `&[byte]`. For an array of known size use
`var rows: []&str = withCapacity(n)`.

## 3. Closed errors, `Result`, `try`, and checked numbers

**Do**

```lxl
import "strings"

type SumError = closed { Parse(str); Overflow }

fn describe(e: &SumError): str {
    return match e {
        SumError.Parse(w) { "not a number: " + w }
        SumError.Overflow { "sum overflows" }
    }
}

fn sum(text: &str): Result[int, SumError] {
    var total = 0
    for w in strings.fields(text) {
        let n = try strings.parseInt(w).mapErr(fn(e: strings.ParseError): SumError {
            return SumError.Parse(w.clone())
        })
        total = match total.checkedAdd(n) {
            Some(t) { t }
            None { return Err(SumError.Overflow) }
        }
    }
    return Ok(total)
}

fn main() {
    println(sum("1 2 3").unwrap())
    match sum("9223372036854775807 1") {
        Ok(t) { println(t) }
        Err(e) { println(describe(&e)) }
    }
}
// expect: 6
// expect: sum overflows
```

**Don't** return `Result[T, str]` and compare messages, `unwrap()` input,
`panic` on bad data, or add numbers from input with `+`.

**Why** a closed error is matched exhaustively, so a new case breaks every
caller that ignores it. `try` needs the same `E` in callee and caller; `mapErr`
converts. `panic` and a failed `unwrap` stop the program (exit 12), for bugs
only. `+ - *` stop it on overflow (exit 10), which is right for a program's own
counters; `checkedAdd`, `checkedSub`, `checkedMul`, `checkedDiv` and
`checkedRem` (every integer type) return `None` instead. SPEC 7.1, 7.6.

## 4. `Decimal` for money

**Do**

```lxl
fn main() {
    let total = 19.99m * Decimal.fromInt(3)
    println(total)
    println(total.round(1).unwrap())
    println(0.1m + 0.2m == 0.3m)
}
// expect: 59.97
// expect: 60.0
// expect: true
```

**Don't** use `float` for amounts: `0.1f + 0.2f == 0.3f` is false.

**Why** `Decimal` is exact base 10 and keeps its scale (`2.50m` prints `2.50`).
Rounding is explicit (`round`, `quantize`, `floor`), and `Decimal.parse` and the
`...Exact` methods return a `Result` instead of stopping.

## 5. `value record` for small plain data

**Do**

```lxl
type Span = value record { start: int; end: int }

fn (s: Span) len(): int { return s.end - s.start }

fn main() {
    let a = Span{start: 2, end: 9}
    let b = a                          // a copy: both stay usable
    println(a.len() + b.len())
}
// expect: 14
```

**Don't** declare it as a `record`:

```lxl
type Span = record { start: int; end: int }

fn main() {
    let a = Span{start: 2, end: 9}
    let b = a
    println(a.start + b.end)
}
// error: 'a' was moved
```

**Why** a `record` is a heap box that moves; a `value record` of copy fields is
inline and copies. Use `record` for what is large, recursive or owns a resource.

## 6. Consume, do not copy

**Do**

```lxl
type Msg = closed { Text(str); Quit }

fn texts(ms: []Msg): []str {
    var out: []str = []
    for m in move(ms) {                // m owns each element
        match m {                      // m is not used again: the match consumes it
            Msg.Text(s) { append(mut &out, s) }
            Msg.Quit {}
        }
    }
    return out
}

fn main() {
    println(texts([Msg.Text("a" + "b"), Msg.Quit])[0])
}
// expect: ab
```

**Don't** `append(mut &out, s.clone())` when the source is dead afterwards.

**Why** a `for` over a temporary array or a local that is not used again gives
`x` ownership, and a `match` on a local or a call result binds its fields owned.
A by-value array parameter is not consumed automatically: write `move(ms)`. To
take a field out of a record you keep, use `replace(mut &c.name, "")`, `swap`
or `pop`. SPEC 8, 9.3.

## 7. Map, Set and sort

**Do**

```lxl
import "collections"

fn main() {
    var counts: Map[str, int] = newMap()           // keys are owned: Map[&str, V] is an error
    for w in ["a", "b", "a"] {
        if counts.has(w) {
            let slot = counts.atMut(w)                // a mut & to the value
            slot += 1
        } else {
            counts.put(w.clone(), 1)                  // clone a key only when it is new
        }
    }
    match counts.find("a") {                      // a borrow, no copy
        Some(n) { println(n) }
        None {}
    }
    var ns: []int = [3, 1, 2]
    sort(mut &ns)
    collections.sortBy(mut &ns, fn(a, b) { return b.cmp(a) })   // descending
    println(ns[0])
}
// expect: 2
// expect: 3
```

**Don't** use `m.get(k)` to look at a large value, or `m.has(k)` and then a
second lookup.

**Why** `Map` keeps insertion order and takes any key with `eq` and `hash`,
including records that get them derived. `get` clones the value; `find` and
`at` borrow it; `atMut` borrows it mutably; `atOrPut(k, d)` inserts and
borrows in one lookup, but takes an owned key, so it clones on every call when
the key is a view. The heap containers take no borrowed type arguments, so a key
or value that is a view must be cloned into the map. `Set` is in
`collections` (`newSet`, `add`, `has`). `sort` is an unstable heap sort;
`sortBy` and `sortStable` are stable merge sorts.

## 8. `rc str` for a buffer several readers share

**Do**

```lxl
type Cur = record { buf: rc str; pos: int }

fn (c: &Cur) rest(): &str { return c.buf[c.pos..] }

fn main() {
    let reply = rc("HEADbody" + "!")
    let a = Cur{buf: reply.share(), pos: 0}
    let b = Cur{buf: reply.share(), pos: 4}
    println(a.rest() + " " + b.rest())
}
// expect: HEADbody! body!
```

**Don't** `.clone()` the buffer once per reader.

**Why** `share()` costs a count and the value cannot change while shared. The
TDS and TNS clients keep a reply this way. `rc` counts are not atomic: a
`par.map` closure may read through a handle but not share or drop one.

## 9. Tasks: scopes, futures, `Shared`

**Do**

```lxl
import "task"

type Stats = record { hits: int }

fn bump(sh: task.Shared[Stats]): int {
    sh.with(fn(s: mut &Stats) { s.hits += 1 })
    return 0
}

fn sq(n: int): int { return n * n }

fn main() {
    let sh = task.shared(Stats{hits: 0})
    let sum = task.scoped(fn(s: mut &task.Scope): int {
        s.spawn(bump, sh.share())      // a plain fn and an owned argument
        s.spawn(bump, sh.share())
        var fs: []task.Future[int] = []
        for i in 1..4 { append(mut &fs, s.start(sq, i)) }
        var t = 0
        for v in task.all(fs).unwrap() { t += v }
        return t
    })
    sh.with(fn(s: mut &Stats) { println(s.hits + sum) })
}
// expect: 16
```

**Don't** pass a closure to `start`:

```lxl
import "task"

fn main() {
    let k = 3
    task.scope(fn(s: mut &task.Scope) {
        let f = s.start(fn(x: int): int { return x + k }, 1)
    })
}
// error: argument 1 of Scope.start
```

**Why** a task outlives its starter's statement, so it gets only what was moved
into it: an owned argument, `Shared` and `rc` handles. State that tasks change
lives in a `Shared`, touched inside `with`, where no call may park (exit 13). A
task that never parks starves the others: call `task.yield()` in a long loop.
SPEC 16.

## 10. `par.map` over a pure kernel

**Do**

```lxl
import "par"

fn main() {
    let xs: []int = [1, 2, 3, 4]
    let k = 3
    println(par.map(&xs, fn(x: &int): int { return x * k })[3])
}
// expect: 12
```

**Don't** print, touch a `var` global, write a captured variable or call a
function that does:

```lxl
import "par"

fn main() {
    let xs: []int = [1, 2]
    let ys = par.map(&xs, fn(x: &int): int { println(x); return x })
    println(len(ys))
}
// error: not a kernel
```

**Why** the closure runs on pool threads, so the compiler proves that
everything it reaches is pure and names the chain of calls when it is not. It
may read what it captures. Use it for CPU-bound work over a slice; I/O belongs
to tasks. SPEC 16, `design/parallel.md`.

## 11. Closures are parameters; stored callbacks are `fn` values

**Do**

```lxl
type Op = value record { name: str; f: fn(int): int }

fn inc(x: int): int { return x + 1 }

fn each(xs: &[]int, f: &fn(int)) { for x in xs { f(x) } }

fn main() {
    let op = Op{name: "inc", f: inc}
    var total = 0
    each(&[1, 2, 3], fn(x) { total += x })    // borrowed for the call
    println((op.f)(total))
}
// expect: 7
```

**Don't** put a closure type in a field, global or result: `record { f:
&fn(int): int }` is an error.

**Why** a closure borrows its surroundings and costs no allocation, so it cannot
outlive them. A top-level function is a `fn(A): R` value: it can be stored,
returned and sent to a task, but captures nothing.

## 12. Iterators with `next`; files and stdin with `io`

**Do**

```lxl
import "io"
import "os"
import "strings"

type Words = value record { text: &str; pos: int }

fn (w: mut &Words) next(): Option[&str] {          // any such type works in `for`
    if w.pos >= len(w.text) { return None }
    let rest = w.text[w.pos..]
    let end = strings.indexOf(rest, " ", 0)
    let stop = if end < 0 { len(rest) } else { end }
    w.pos += stop + 1
    return Some(rest[0..stop])
}

fn die(msg: &str): never {
    eprintln("tool: " + msg)
    os.quit(1)
}

fn main() {
    let text = match io.readStdin() {              // a failed read is input, not a bug
        Ok(t) { t }
        Err(e) { die(&e.toStr()) }
    }
    var n = 0
    for l in strings.lines(&text) {                // an iterator of views
        for _w in Words{text: l, pos: 0} { n += 1 }
    }
    println(n)
}
// stdin: a b
// stdin: c d e
// expect: 5
```

**Don't** `.unwrap()` a read, build an array to walk it once, or keep an index
by hand.

**Why** an item never borrows the iterator, only what the iterator borrows. For
large input use `var r = io.stdin()` and `r.readLine()` in a loop; it returns
`Result[Option[str], IoError]`, so match the `Result`, then the `Option`.
`io.Writer` (`io.stdout()`, `io.create(path)`) buffers output: flush or drop it.
The `never` helper keeps `match` arms to one expression.

## 13. Parse arguments with `cli`; errors go to stderr with an exit code

**Do**

```lxl
import "cli"
import "os"

fn flag(short: byte, long: &str, arity: cli.Arity): cli.Spec {
    return cli.Spec{short: short, long: long.clone(), arity: arity, consume: [],
                    accept: [], choices: [], default: ""}
}

fn main() {
    let specs: []cli.Spec = [flag('v', "verbose", cli.Arity.Flag), flag('n', "count", cli.Arity.Value)]
    let args: []str = ["-v", "--count=3", "--bogus"]  // os.arguments() in a program
    match cli.parse(&args, 0, &specs) {
        Ok(cmd) { println(len(cmd.operands)) }
        Err(e) {
            eprintln("tool: " + e.toStr())
            os.quit(2)                                // bad usage
        }
    }
}
// exit: 2
// stderr: tool: unknown option --bogus
```

**Don't** loop over `os.arguments()` comparing strings (unless there are one or
two positional arguments), print errors to stdout, `panic` on bad input, or
declare `fn main(): int`.

**Why** `cli.parse` is the eza grammar (clusters, `--x=v`, `--`). It never
prints and never exits: the caller words the message and picks the code, as
`cmd/eza.lxl` does. `main` returns nothing, so a program leaves with
`os.quit(code)`: it is `exit`, with no drops and no leak check, and stdout is
still written. The programs in `cmd/` mostly use 1 for a failed operation and
2 for bad usage.
