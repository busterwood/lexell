# Compile errors and run-time stops

The errors an agent meets most, grouped. `lxlc` stops at the first error and
prints `file:line: message`; messages are quoted as printed, with `<...>` for
the variable parts. Each example is a program that `lexell/tools/doc_check.py`
compiles and finds to fail with the words in its `// error:` line (a failing
example needs no `main`). Related:
[tour.md](tour.md), [idioms.md](idioms.md), [../../SPEC.md](../../SPEC.md).

## Syntax and newlines

**`expected an expression, found '+'`**. A newline ended the statement, so a
line cannot start with an operator. End the previous line with it.

```lxl
fn f(): int {
    let a = 1 + 2
        + 3
    return a
}
// error: expected an expression, found '+'
```

**`expected ;, found ':'`**. In an `if`, `while`, `for` or `match` header `{`
starts the block, so `P{x: 1}` is not a literal there. Wrap it in parentheses:
`if p == (P{x: 1, y: 2}) { ... }`.

```lxl
type P = value record { x: int; y: int }

fn f(p: P): bool {
    if p == P{x: 1, y: 2} { return true }
    return false
}
// error: expected ;, found ':'
```

## Literals

**`<lit>: a fractional literal needs a suffix: 0.5m for a Decimal, 0.5f for a
float`**. Add `m` for money and exact values, `f` for a `float`.

```lxl
fn f(): float { return 0.5 }
// error: a fractional literal needs a suffix
```

**`the initializer of '<x>' is float, not Decimal`**. An `f` literal is always a
`float`, and nothing converts it. Where a `Decimal` is wanted write `1.5m`.

```lxl
fn f() { let d: Decimal = 1.5f }
// error: is float, not Decimal
```

**`expected ;, found '<type>'`** after `[]`. There is no `[]T{}` literal. An
empty array takes its type from where it goes: `let xs: []int = []`, or
`f([])` for a `&[]T` parameter.

```lxl
fn f() { let xs = []int{} }
// error: expected ;, found 'int'
```

## Names and imports

**`unknown name '<x>'`**. The name is misspelt or undeclared, a library function
is used without its module (`split` for `strings.split`), or a variant is written
bare (`A(3)` for `E.A(3)`). Only `Some`, `None`, `Ok` and `Err` may be bare.

```lxl
import "strings"

fn f(): int { return len(split("a,b", ",")) }
// error: unknown name 'split'
```

**`'<x>' is already declared in this function (no shadowing)`**. A local,
parameter or closure parameter reuses a name in scope. Pick another name.

```lxl
fn f(a: int) {
    if a == 1 {
        let a = 2
    }
}
// error: already declared in this function
```

**`cannot assign to '<x>': it is declared with let, not var`**. Also for a loop
variable, and for a `let` that a closure assigns. Declare it `var`.

```lxl
fn f() {
    let n = 0
    n += 1
}
// error: declared with let, not var
```

## Types and conversions

**`operator + needs operands of the same type, not int and float`**. There are
no implicit conversions (also for `==` and `<`). Convert one side with
`float(n)`, `int(b)` or `byte(n)`.

```lxl
fn f(a: int, b: float): float { return a + b }
// error: needs operands of the same type
```

**`argument <n> of <f> is <P>, not <A>`**, **`the initializer of '<x>' is <A>,
not <D>`**, **`the returned value is <A>, not <D>`**. The value has the wrong
type. The argument form names the parameter type first (`P`) and the type given
second (`A`); the other two name the value first. Convert it or fix the
declaration.

```lxl
fn g(a: int) {}

fn f() { g("a") }
// error: argument 1 of g is int, not str
```

**`<f> may reach its end without a return`**. Some path of a function with a
result type does not return. Add a final `return`.

```lxl
fn f(a: int): int {
    if a > 0 { return 1 }
}
// error: may reach its end without a return
```

**`cannot infer the element type of [] here: it needs an expected type`**, **`cannot
infer the type argument <T> of <f>; give it explicitly or declare the result
type`**. Give the variable a type, `let xs: []int = []`, or write the argument,
`mk[int]()`. `None` needs one too.

```lxl
fn f() { let xs = [] }
// error: cannot infer the element type
```

**`try needs a function whose result type has an Err variant (like Result), and
<f> returns <type>`**. `try` returns the error from its function, so that must
return a `Result`. In `main`, which returns nothing, `match` instead.

```lxl
fn g(): Result[int, str] { return Ok(1) }

fn main() {
    let x = try g()
}
// error: try needs a function whose result type has an Err variant
```

**`try: the error type <A> is not the Err type <B> of <f>`**. `try` does not
convert errors. Convert with `mapErr`, or return the same type.

```lxl
type A = closed { X }
type B = closed { Y }

fn g(): Result[int, A] { return Err(A.X) }

fn f(): Result[int, B] {
    let x = try g()
    return Ok(x)
}
// error: the error type A is not the Err type B
```

## Ownership and moves

**`'<x>' was moved and has no value here`**. `x` was moved by `let t = x`, a
by-value argument or a `return`. Pass `&x` to read it, or `x.clone()` to keep
one. A plain `record` moves on `let b = a`; a `value record` of copy fields
copies. An unconstrained `T` is owned, so a generic body moves it too.

```lxl
fn f() {
    let s = "ab" + "cd"
    let t = s
    println(s)
}
// error: 's' was moved
```

**`cannot move a str out of a field or element of '<x>'; use replace, swap or
pop`**. Only a whole local can be moved. `replace(mut &h.name, "")` takes the
value and leaves another; `.clone()` copies.

```lxl
fn f() {
    var xs: []str = ["a" + "b"]
    let s = xs[0]
}
// error: cannot move a str out of a field or element
```

**`cannot move a str out of a borrow (<x>): it is not a copy type`**. A `&str`
is a view and does not become a `str` by itself. It appears when a view is
passed for a `str` parameter, returned as `str`, or kept in a `str` variable.
Write `.clone()`, or make the parameter `&str`.

```lxl
fn f(s: &str): str { return s[0..1] }
// error: cannot move a str out of a borrow
```

## Borrows

**`'<x>' is borrowed by '<y>' and cannot be assigned while that borrow is in
scope`**. Also `cannot be moved` and `cannot be mutably borrowed`. `y` is a
`let` borrow, a closure, a `match` binding or a `for` loop (`borrowed by the for
loop`) that is used later. Finish with `y` first, or clone.

```lxl
fn f() {
    var xs: []int = [1, 2]
    for x in xs { append(mut &xs, x) }
}
// error: borrowed by the for loop
```

**`'<x>' is borrowed mutably twice in one call: a mut & argument may not overlap
another borrowed or moved argument`**. Two arguments of one call reach the same
place. Split the call, or copy a value out first.

```lxl
fn two(a: mut &[]int, b: mut &[]int) {}

fn f() {
    var xs: []int = [1]
    two(mut &xs, mut &xs)
}
// error: borrowed mutably twice in one call
```

**`argument <n> of <f> needs a mut borrow, not &[]int ('<x>' is a shared
borrow)`**, **`cannot mutably borrow '<x>': it is declared with let, not var`**,
**`cannot assign through '<p>': it is a shared borrow (&), not mut &`**. A write
needs `mut &x` at the call, `var` at the declaration and `mut &T` in the
parameter type.

```lxl
fn add(xs: mut &[]int) { append(xs, 1) }

fn f() {
    var xs: []int = []
    add(&xs)
}
// error: needs a mut borrow
```

**`cannot return a borrow of '<x>': <f> has no borrowed parameter, so its result
may only borrow static data (...)`**. A function cannot return a view of its own
local. Return an owned value (`s.clone()`), or take the source as a parameter.

```lxl
fn f(): &str {
    let s = "ab" + "cd"
    return &s
}
// error: cannot return a borrow of 's'
```

**`'<y>' cannot hold borrows of '<x>': '<x>' does not live as long as '<y>'`**.
A view (the result of `split`, say) is stored in a variable declared in an outer
scope, and its source in an inner one. Declare the source first, or clone the
pieces.

```lxl
import "strings"

fn f() {
    var parts: []&str = []
    {
        let line = "a,b" + ",c"
        parts = strings.split(&line, ",")
    }
}
// error: does not live as long as
```

## match

**`match on <T> is not exhaustive: missing <V>`**. Add an arm for each missing
variant, or an `else`. A `match` on an `int`, `byte` or `str` always needs
`else` (`a match on int needs an else arm`).

```lxl
type E = closed { A; B; C }

fn f(e: &E) {
    match e {
        E.A { println("a") }
        E.B { println("b") }
    }
}
// error: is not exhaustive: missing C
```

**`<V> has <n> fields, but the pattern binds <m>`**. Bind every field in
declaration order, with `_` to ignore one.

```lxl
type E = closed { A(int, int); B }

fn f(e: &E) {
    match e {
        E.A(x) { println(x) }
        E.B {}
    }
}
// error: A has 2 fields, but the pattern binds 1
```

**`expected ,, found '.'`**. A pattern is one level deep: `Some(E.A(n))` is not a
pattern. Bind with `Some(e)`, then `match e`.

```lxl
type E = closed { A(int); B }

fn f(o: &Option[E]) {
    match o {
        Some(E.A(n)) { println(n) }
        else {}
    }
}
// error: expected ,, found '.'
```

## Generics and constraints

**`operator < on T needs a method cmp (from a constraint such as Ord)`**, **`T has
no method '<m>' (its constraints do not provide it)`**. A generic body sees only
its constraints. Write `T: Ord` (or `Show`, `Eq`, `Hash`).

```lxl
fn bigger[T](a: T, b: T): bool { return a < b }
// error: needs a method cmp
```

**`<T> does not satisfy Ord (type parameter T): it has no method 'cmp'`**. The
type at the call lacks a method the constraint needs (`cmp` is never derived), or
is owned where `copy` is required (`str is not a copy type`). Declare the method,
drop `copy`, or pass another type.

```lxl
type P = value record { x: int }

fn big[T: Ord + copy](a: T, b: T): T { return if a < b { b } else { a } }

fn f(): int { return big(P{x: 1}, P{x: 2}).x }
// error: does not satisfy Ord
```

**`a borrow type (&str) cannot be a type argument (type parameter K): borrows
are second class, and only a parameter declared K: borrow takes one`**. `Map`,
`Set`, `Heap` and `task.Scope.start` take owned type arguments only; `Option`
and `Result` take borrows. Store owned values (`w.clone()`) in the container.

```lxl
fn f() { var m: Map[&str, int] = newMap() }
// error: a borrow type (&str) cannot be a type argument
```

## Closures and tasks

**`a closure type cannot be stored: closures are second class (a parameter or a
let)`**, and the same `cannot be a result`. A closure borrows its surroundings.
Store a plain `fn(A): R` value instead.

```lxl
type H = record { f: &fn(int): int }
// error: a closure type cannot be stored
```

**`argument 1 of Scope.start is fn(A): T, not &fn(int): int`**. A task takes a
plain function and an owned argument, not a closure. Move what it needs into the
argument.

```lxl
import "task"

fn f() {
    let k = 3
    task.scope(fn(s: mut &task.Scope) {
        let h = s.start(fn(x: int): int { return x + k }, 1)
    })
}
// error: argument 1 of Scope.start
```

**`par.map: the closure is not a kernel: it can reach <what> (<call>)`**, then
the chain of calls. The closure, or something it calls, does I/O, parks, uses a
`var` global, calls a C function that is not `pure`, or touches an `rc` handle.
**`par.map: the closure changes '<x>', which it captures`**: it may only read
what it captures. Compute in the closure and return the value.

```lxl
import "par"

fn f(xs: &[]int) {
    var total = 0
    let ys = par.map(xs, fn(x: &int): int { total += x; return x })
}
// error: the closure changes 'total'
```

## Run-time stops

A stopped program prints `Lexell: <message> at <file>:<line>` to stderr and
exits with a code (SPEC 14). A location in `std.lxl` is the library call
(`unwrap`); the caller's line is the one to look at.

| Exit | Message | Cause |
|---:|---|---|
| 3 | `index out of range`, `string slice out of range`, `pop on an empty array` | bad index or slice bounds, `pop` of `[]` |
| 4 | `stack overflow` | recursion too deep |
| 10 | `integer overflow`, `division by zero`, `conversion out of range`, `shift count out of range` | checked arithmetic and conversions |
| 12 | `panic: <msg>`, `panic: assertion failed`, `panic: unwrap of None` or `of Err` | `panic`, `assert`, `unwrap` |
| 13 | `a task parked inside Shared.with (the with at <f>:<n>) at <f>:<n>` | a call that can park inside `with` |
| 14 | `deadlock: every task is parked at <f>:<n>` | no task can run, no timer or socket pending |

```lxl
fn main() {
    var d = 0
    println(10 / d)
}
// exit: 10
// stderr: Lexell: division by zero at block.lxl:3
```

**`Lexell: leak: <n> live objects at exit at runtime`**, exit 5. Reported only
when the program runs with `LXL_CHECK=1` (the test runners always set it). Safe
code does not leak: a report means a compiler or library bug, or unchecked
library code (`intoPtr`, `ffi`). Reduce it to a small program and run it again
with `LXL_CHECK=1`; `exit(code)` skips the check.
