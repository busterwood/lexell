# Calling C

How to declare a C function, what may cross the boundary, and how to wrap the
result in a module that cannot be misused. The rules are
[SPEC.md](../../SPEC.md) 12, the linker's side is
[design/native.md](../../design/native.md) section 5a, the memory helpers are
`python3 lexell/tools/libapi.py ffi`, and the worked example is
[lib/sqlite.lxl](../../lib/sqlite.lxl). Calls to C are unchecked: a wrong
argument is undefined behaviour, so a program calls C through a wrapper.

## Declaring an extern

```lxl-frag
extern "c" fn strlen(s: &str): int
extern "c" fn cAbs(x: i32): i32 as "abs"
extern "m" fn hypot(x: float, y: float): float pure
extern "sqlite3" fn sqlite3_step(st: ptr): i32 blocking
extern "c" fn printf(fmt: &str, ...): i32
```

The string names the library: `"c"` for libc, `"m"` for libm, `"sqlite3"` links
`-lsqlite3`. `as "name"` gives the C name when the Lexell name differs. An
extern is always private to its module (`pub extern` is an error). Two externs
with one C name must have the same types, and a C name may not be `main`,
start with `rt_` or `lxl_` (the runtime's, apart from its documented helpers
such as `lxl_errno`), or look like a name the compiler generates (`f1_x`,
`g1_x`, `S1_x`).

C's `int` is `i32` and `long` is `int`, and nothing converts on its own:
`let n: int = atoi("5")` is `the initializer of 'n' is i32, not int`.

| Position | Allowed |
|---|---|
| parameter | integers, `float`, `bool`, `ptr`; `mut &ptr` and `mut &int` (out parameters); `&str`; `&[]T`, `mut &[]T`, `&[T]`, `mut &[T]` for integer, `float` and `ptr` elements (`bool` read-only); `extern fn(...)` |
| result | integers, `float`, `bool`, `ptr`, `str`, or none |

A record, a closure, a `Map` or an owned `str` parameter is a compile error. A
`str` parameter is refused with `extern parameter s is read by C: declare it
&str`, because C cannot take ownership of a Lexell string.

## Strings and arrays

A `&str` is passed as a NUL-terminated pointer valid for the call (a substring
is copied first). A string with a NUL byte stops the program, exit 12. A `str`
result copies the NUL-terminated `char *` C returns (a NULL gives `""`) and does
not free it. `strFromC(p)` copies the string at a `ptr` you hold.

An array or slice parameter is passed as a pointer to its elements, borrowed for
the call only. C gets no length: pass `len(a)` too. With `mut`, C may write the
elements. An empty array passes a valid pointer, never NULL. The element type
fixes the layout: `[]i32` is a C `int[]`, `[]byte` a `char[]`.

```lxl
import "ffi"

extern "c" fn qsort(base: mut &[]i32, n: int, size: int, cmp: extern fn(ptr, ptr): i32)
extern "c" fn memset(dst: mut &[]byte, c: i32, n: int): ptr
extern "c" fn snprintf(buf: mut &[]byte, n: int, fmt: &str, ...): i32

fn descending(a: ptr, b: ptr): i32 {
    let x = ffi.peekI32(a, 0)
    let y = ffi.peekI32(b, 0)
    return if x < y { 1 } else if x > y { -1 } else { 0 }
}

fn main() {
    var xs: []i32 = [30, 10, 20]
    qsort(mut &xs, len(xs), 4, descending)    // C calls descending back
    println(xs[0])
    println(int(xs[2]))
    var buf: []byte = array(16, byte(0))
    memset(mut &buf, 46, len(buf))
    let n = snprintf(mut &buf, len(buf), "%s=%d", "n", i32(42))
    println(strFromBytes(&buf[0..int(n)]))
}
// expect: 30
// expect: 10
// expect: n=42
```

## Variadics, callbacks, `pure`, `blocking`

- **Variadics.** `...` after at least one parameter, in an extern only. The extra
  arguments are integers (not `i128`), `float`, `bool`, `ptr` or `str`, each
  with its own type: an integer literal is an `int`, a C `long`, so `%d` needs
  `i32(n)`, and a fractional literal must be `2.5f`. C's default promotions
  apply. The format string is not checked. Lexell's output is buffered: call
  `io.flushStdout()` before C writes to stdout and `fflush` after, to keep the
  lines in order.
- **Callbacks.** A parameter of type `extern fn(T1, ...): R` takes a top-level
  function (or an instance of a generic one) of the same types, which are
  integers, `float`, `bool` and `ptr`. A closure and an extern are refused.
  C calls it with the C calling convention while the call runs, or later if
  C keeps the pointer. Pass user data as a `ptr` argument; the callback cannot
  reach the caller's locals, only its arguments and globals. A panic or runtime
  error in it ends the program. `tests/run/lang11_user_data.lxl` has `qsort_r`
  with user data and `signal`.
- **`pure`** after the declaration promises that the function does no I/O, keeps
  no state and calls no callback; what it computes depends only on its
  arguments. A `par.map` kernel may call it ([concurrency.md](concurrency.md)),
  otherwise only the maths functions. The compiler cannot check the promise.
- **`blocking`** (after `as`) marks a call that may take long: it runs on a helper
  thread while other tasks go on ([concurrency.md](concurrency.md)). It cannot
  take an `extern fn` parameter, be variadic or be `pure`, and inside
  `Shared.with` it is exit 13. The C function must be safe to call from another
  thread than its other calls.

## `ptr` and the `ffi` module

`ptr` is a copy type that holds a C pointer. Its only operations are `==`, `!=`
and `isNull(p)`, and only an extern or `nullPtr()` makes one. A wrapper record
may hold one. `ffi` has the memory a wrapper needs: `ffi.alloc(n)` zeroed bytes,
`ffi.cstr(s)` a NUL-terminated copy, `ffi.copyBytes(s)`, each an owned `Mem` that
frees itself when dropped and checks its index (`get`, `set`, `getI32`,
`getPtr`, `ptr()`, `size()`, `toStr()`); and `peek`, `poke`, `peekI32`,
`peekPtr` and `bytes(p, n)` on memory C owns, which are unchecked. Memory from
`malloc` is C's, and `free` it in a `drop`; memory from `ffi.alloc` is counted by
`LXL_CHECK=1`.

```lxl
import "ffi"

extern "c" fn strtol(s: ptr, end: mut &ptr, base: i32): int
extern "c" fn strlen(s: ptr): int

type NumError = closed { Empty; Trailing(str) }

// The safe face: no ptr in the signature, nothing for the caller to free.
pub fn parse(s: &str): Result[int, NumError] {
    let text = ffi.cstr(s)                    // a NUL-terminated copy, freed at the end of the call
    var end = nullPtr()
    let n = strtol(text.ptr(), mut &end, 10)  // C stores where it stopped
    if end == text.ptr() { return Err(NumError.Empty) }
    if ffi.peek(end, 0) != 0 { return Err(NumError.Trailing(ffi.bytes(end, strlen(end)))) }
    return Ok(n)
}

fn show(r: Result[int, NumError]): str {
    return match r {
        Ok(n) { "ok " + n.toStr() }
        Err(e) {
            match e {
                NumError.Empty { "empty" }
                NumError.Trailing(rest) { "trailing " + rest }
            }
        }
    }
}

fn main() {
    println(show(parse("42")))
    println(show(parse("12ab")))
    println(show(parse("")))
}
// expect: ok 42
// expect: trailing ab
// expect: empty
```

## Wrapping an extern safely

A module that needs C exposes types and functions, never the raw extern. The
pattern, which `lib/sqlite.lxl` follows throughout:

1. The externs are private, at the top of the module. Declare the ones that can
   park (`sqlite3_step`, `sqlite3_exec`) `blocking`.
2. The C handle is a field of an owned `record`, and `drop` releases it:
   `fn (d: mut &Db) drop()` calls `sqlite3_close_v2`. Then an early `return` or a
   `try` cannot leak it, and the type cannot be copied.
3. A constructor returns `Result[T, Error]`: `open` passes a `mut &ptr` for the
   handle, checks the result code, closes the half-made handle and converts the
   code and `sqlite3_errmsg` (a `str` result) into the module's error type.
4. Inputs C cannot take are refused before the call (`sqldialect.noNul`), so
   the exit 12 for a NUL cannot be reached from the safe API. Bounds C does not
   check are checked in Lexell, as `ffi.Mem` does.
5. Borrowed C memory is copied before it can dangle: `ffi.cstr(sql)` is kept
   alive across `sqlite3_prepare_v2` because C returns a pointer into it.
6. A counter (`openHandles()`) lets a test check that every handle was released,
   as `LXL_CHECK=1` does for Lexell memory.

The same shape in 25 lines, around `malloc` and `free`:

```lxl
import "ffi"

extern "c" fn malloc(n: int): ptr
extern "c" fn free(p: ptr)
extern "c" fn memset(p: ptr, c: i32, n: int): ptr

pub type Buf = record { p: ptr; n: int }

fn (b: mut &Buf) drop() {
    println("freed " + b.n.toStr())
    free(b.p)
}

pub fn newBuf(n: int, fill: byte): Buf {
    let p = malloc(n)
    if isNull(p) { panic("out of memory") }
    memset(p, i32(fill), n)
    return Buf{p: p, n: n}
}

pub fn (b: &Buf) get(i: int): byte {
    if i < 0 || i >= b.n { panic("Buf.get: index out of range") }   // C would not check
    return ffi.peek(b.p, i)
}

fn main() {
    let b = newBuf(16, 'x')
    println(int(b.get(15)))
}
// expect: 120
// expect: freed 16
```

## Linking

Every `extern "name"` adds `-lname`, and an extern's library is found as
`libname.so`, or the first `libname.so.N` when only versioned files exist. A
program whose C calls are all in the native runtime's own set (a subset of libc
that [native.md](../../design/native.md) section 2 lists: `strlen`, `getenv`,
`malloc`, `free`, `getpid`, `usleep`, ..., and libm's maths) is a static
executable. A program that calls any other function is linked dynamically
against the named libraries, libm and libc, and then calls every C function
from them, so `errno`, the environment and `malloc` are libc's. `lxlc` stops
with `native: undefined C function 'f' (not in libm.so.6, libc.so.6)` when no
library defines one. A test of a program that needs a C library carries
`// needs: name` ([testing.md](testing.md)).

```lxl
extern "c" fn strlen(s: str): int

fn main() { println(strlen("lexell")) }
// error: declare it &str
```
