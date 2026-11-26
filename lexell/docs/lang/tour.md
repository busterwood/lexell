# A tour of Lexell

The language by example, for someone who knows Rust. Each section names the
[SPEC](../../SPEC.md) section with the fine print. Every `lxl` block is a
complete program that `lexell/tools/doc_check.py` compiles and runs. Traps are
in [AGENTS.md](../../../AGENTS.md), preferred patterns in [idioms.md](idioms.md),
compile errors in [errors.md](errors.md).

## Modules and imports

`import "strings"` names a library module, used qualified (`strings.split`).
`import "./money"` names a file beside the importing one, and `as` renames the
qualifier. The prelude (`lib/std.lxl`) needs no import. Declarations may come
in any order; only `pub` ones are visible to importers. SPEC 5.1.

```lxl-frag
import "strings"
import "./money" as m
pub fn total(xs: &[]str): int { return len(xs) }
```

## let, var and primitive types

`let` binds once, `var` can be assigned, and a name cannot be declared twice in
a function. Integers are `int` (64 bit), `i32`, `u32`, `u64`, `byte`, `i128`
and `u128`. Conversions are calls, never implicit. Arithmetic stops the
program on overflow; `+% -% *%` wrap. A fractional literal needs a suffix: `f`
for `float`, `m` for `Decimal`. SPEC 2, 4.1, 7.

```lxl
fn main() {
    let n = 1_000 + 0xff + 0b101
    let b: byte = 'a'
    var h = 255
    h = h *% 3                         // wrapping multiply
    println(int(b) + 1)
    println(float(n) * 1.5f)
    println(2.50m + 1m)                // Decimal keeps its scale
    println(h)
}
// expect: 98
// expect: 1890
// expect: 3.50
// expect: 765
```

## Strings

`str` is an owned, immutable byte string; `&str` is a view (pointer and
length). `s[a..b]` is always a view and `.clone()` makes an owned copy.
`s += x` appends in place; `addByte`, `addInt`, `addLine`, `clear` and `bytes`
make a string its own buffer. `s[i]` is a `byte`. SPEC 4.1.

```lxl
fn main() {
    var s = "hello"
    s += ", world"
    let view: &str = s[0..5]           // no copy
    println(view)
    println(s[1])                      // a byte: 101
    let own = s[7..].clone()
    s.clear()                          // keeps the buffer
    s.addByte('x')
    s.addInt(42)
    s.addLine(own)
    print(s)
}
// expect: hello
// expect: 101
// expect: x42world
```

## Arrays and slices

`[]T` is a growable array that owns its elements and moves. `&[T]` and
`mut &[T]` are slices (pointer and length); `xs[a..b]` makes one. The
built-ins are `len`, `append`, `pop`, `swap`, `array(n, v)` and
`withCapacity(n)`. SPEC 4.2, 4.2a, 11.

```lxl
fn sum(xs: &[int]): int {
    var t = 0
    for x in xs { t += x }
    return t
}

fn bump(xs: mut &[int]) {
    for i in 0..len(xs) { xs[i] += 1 }
}

fn main() {
    var xs: []int = [1, 2, 3]
    append(mut &xs, 4)
    let last = pop(mut &xs)
    bump(mut &xs[1..3])
    swap(mut &xs, 0, 2)
    println(sum(&xs) + last)
}
// expect: 12
```

## Records and methods

`record` is boxed and owned; `value record` is inline, and a copy type when all
its fields are. A literal names every field. A receiver is `&T` to read,
`mut &T` to write, or has no name for an associated function; methods are
declared in the type's module. A type with no `eq`, `hash` or `toStr` of its
own gets them derived. SPEC 4.3, 5.3, 7.4.

```lxl
type Point = value record { x: int; y: int }
type Node = record { name: str; kids: []Node }

fn (p: &Point) norm2(): int { return p.x * p.x + p.y * p.y }
fn (p: mut &Point) shift(dx: int) { p.x += dx }
fn (Point) origin(): Point { return Point{x: 0, y: 0} }

fn main() {
    var p = Point{x: 3, y: 4}
    p.shift(1)
    let q = p                          // a copy
    println(p.norm2() + q.x)
    println(Point.origin().toStr())
    let n = Node{name: "root", kids: [Node{name: "kid", kids: []}]}
    println(n.kids[0].name)
}
// expect: 36
// expect: Point{x: 0, y: 0}
// expect: kid
```

## Closed types, match and try

A `closed` type has a fixed set of variants, always written qualified by the
type. A `match` covers every variant or ends in `else`; patterns are one level
deep and fields bind by position. `if` and `match` are also expressions with
one expression per branch. `Option` and `Result` are closed types whose
variants (`Some`, `None`, `Ok`, `Err`) may be written bare. `try e` yields the
`Ok` value, or returns the `Err` from a function with the same error type.
SPEC 4.4, 7.6, 8.

```lxl
import "strings"

type Shape = closed { Circle(int); Rect { w: int; h: int }; Dot }

fn area(s: &Shape): int {
    return match s {
        Shape.Circle(r) { 3 * r * r }
        Shape.Rect(w, h) { w * h }
        Shape.Dot { 0 }
    }
}

fn twice(s: &str): Result[int, strings.ParseError] {
    let n = try strings.parseInt(s)
    return Ok(n * 2)
}

fn main() {
    println(area(&Shape.Rect{w: 2, h: 3}))
    println(twice("21").unwrapOr(0))
    println(twice("x").isErr())
    let n = 5
    println(match n { 0 { "none" } 1, 2 { "few" } else { "many" } })
}
// expect: 6
// expect: 42
// expect: true
// expect: many
```

## Generics and interfaces

A generic body sees only what its constraints promise. An unconstrained `T` is
owned and has no methods; `copy` allows copies (a `str` is not a copy type).
An interface lists method signatures over `Self`, is satisfied structurally and
is used only as a constraint. The prelude has `Eq`, `Ord`, `Hash`, `Show` and
`Clone`. SPEC 5.4, 6.

```lxl
type HasArea = interface { fn (&Self) area(): int }
type Sq = value record { s: int }
fn (q: &Sq) area(): int { return q.s * q.s }

fn total[T: HasArea](xs: &[]T): int {
    var t = 0
    for x in xs { t += x.area() }
    return t
}

fn largest[T: Ord + copy](a: T, b: T): T { return if a > b { a } else { b } }

fn main() {
    let xs: []Sq = [Sq{s: 2}, Sq{s: 3}]
    println(total(&xs))
    println(largest(3, 9))
}
// expect: 13
// expect: 9
```

## Closures

`&fn(A): R` is a closure: a borrow of the surrounding locals. It is a
parameter or a `let`, never a field, a result or a task argument. It assigns
only to captured `var`s. Its types may be left out when the callee declares
them, and a named function converts to one. `fn(A): R` is a plain function
value. SPEC 4.6.

```lxl
fn apply(xs: &[]int, f: &fn(int): int): []int {
    var out: []int = []
    for x in xs { append(mut &out, f(x)) }
    return out
}

fn double(x: int): int { return x * 2 }

fn main() {
    let k = 10
    var calls = 0
    let xs: []int = [1, 2, 3]
    let a = apply(&xs, fn(x) { calls += 1; return x + k })
    println(a[2] + apply(&xs, double)[2])
    println(calls)
}
// expect: 19
// expect: 3
```

## Ownership: moves, drops, clone

An owned value (`str`, arrays, records, `rc` and `Shared` handles) has one
owner. Passing, assigning or returning it moves it, and the source has no value
until assigned again. A value is dropped when its owner goes out of scope, in
reverse order of declaration; a `drop` method releases a resource there. You
cannot move out of a field, an element or a borrow (a field of a local that is
not used again is the exception): use `replace`, `swap`, `pop` or `move(x)`.
SPEC 9.

```lxl
type Cell = record { name: str; n: int }

fn main() {
    var c = Cell{name: "a" + "b", n: 1}
    let old = replace(mut &c.name, "z")      // takes the old value out
    println(old + c.name)
    var s = "keep" + "me"
    let t = move(s)                          // s has no value now
    s = "again"                              // assigned again: usable
    let u = t.clone()                        // a second owner
    println(t + s + u)
    let h = Cell{name: "q" + "r", n: 2}
    let nm = h.name                          // h is not used again: allowed
    println(nm)
}
// expect: abz
// expect: keepmeagainkeepme
// expect: qr
```

## Borrows at calls

A `&T` parameter takes the argument with no `&` written; a `mut &T` parameter
needs `mut &x`, and `x` must be a `var`. A borrow freezes what it borrows until
its last use. Borrows are second class: parameters, `let`s, results and fields
of value records, never globals. A function that returns a borrow returns one of
its parameters'. A string literal is a view with no root and may go anywhere.
SPEC 7.5, 10.

```lxl
type Tok = value record { text: &str; n: int }

fn longest(a: &str, b: &str): &str { return if len(a) >= len(b) { a } else { b } }

fn drain(xs: mut &[]int) { while len(xs) > 0 { pop(xs) } }

fn main() {
    var xs: []int = [1, 2]
    drain(mut &xs)
    let src = "long enough"
    let t = Tok{text: src, n: len(xs)}       // holds a view of src
    println(longest(t.text, "short"))
}
// expect: long enough
```

## for loops

`for i in a..b` counts over `int`. `for x in xs` over an array gives a copy for
a copy element and a `&T` otherwise. Over a temporary array, or a local not
used again, the loop consumes it and `x` owns each element. Any other value is
an iterator: a type with `fn (it: mut &I) next(): Option[X]`. SPEC 8.

```lxl
import "strings"

type Count = value record { n: int; max: int }

fn (c: mut &Count) next(): Option[int] {
    if c.n >= c.max { return None }
    c.n += 1
    return Some(c.n)
}

fn main() {
    var out: []str = []
    for line in strings.split("a\nb", "\n") { append(mut &out, line.clone()) }
    for s in out { print(s) }                // consumes out
    for x in Count{n: 0, max: 3} { print(x) }
    println("")
}
// expect: ab123
```

## rc T

`rc T` is a counted handle to a value that does not change while shared.
`rc(v)` makes one and `r.share()` another. Reads go through the handle
(`len(r)`, `r == "x"`, `r.field`). `r.unshare()` gives a `mut &T`, first cloning
the value if other handles exist. SPEC 4.9.

```lxl
fn main() {
    let a = rc("shared" + " text")
    let b = a.share()
    println(len(a) + len(b))
    var c = rc("x" + "y")
    let w = c.unshare()
    w += "z"
    println(c)
}
// expect: 22
// expect: xyz
```

## Tasks and par.map

Tasks are cooperative coroutines on one thread, started on a `task.Scope` that
returns only when they finish. A task takes a plain `fn` value and an owned
argument. `par.map(&xs, f)` runs a closure over a slice on a thread pool; the
closure must be pure: no I/O, no global state, no writes to what it captures.
SPEC 16; see also [idioms.md](idioms.md).

```lxl
import "task"
import "par"

fn work(n: int): int { return n * n }

fn main() {
    let r = task.scoped(fn(s: mut &task.Scope): int {
        let f1 = s.start(work, 3)
        let f2 = s.start(work, 4)
        return f1.wait().unwrap() + f2.wait().unwrap()
    })
    let xs: []int = [1, 2, 3, 4]
    let k = 3
    let ys = par.map(&xs, fn(x: &int): int { return x * k })
    println(r + ys[3])
}
// expect: 37
```

## C interop

`extern "lib" fn` declares a C function; it is private to its module, so a
module wraps it. Parameters are integers, `float`, `bool`, `ptr`, `&str` and
arrays or slices of numbers. `blocking` runs a long call on a helper thread;
`pure` promises no side effects. SPEC 12.

```lxl
extern "c" fn labs(x: int): int pure

fn main() {
    println(labs(-5))
}
// expect: 5
```
