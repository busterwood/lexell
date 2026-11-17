# Owned strings and declared reference counting

Status: proposal and first measurement, 2026-11-17. Branch `lang/owned-str`.

## 1. The problem

SPEC section 1 says one owner per value: copy types are copied, every other
type is moved. `str` gets around that rule. It is reference counted in the
runtime and calls itself a copy type (SPEC 4.1). That one exception brings
special cases with it:

- `rt_str_dup`/`rt_str_drop` traffic, and copy and drop code for records that
  hold strings;
- borrow inference for `str` parameters (borrow-inference.md), which removes
  counts that the model forces;
- `&[]str` used as `&[]&str`, and the `&str` → `str` conversion that takes a
  count;
- non-atomic counts as the first thing that breaks with threads
  (concurrency.md, "What breaks", item 1);
- a second counted type, `Shared[T]` (concurrency.md), with its own machinery.

## 2. The proposal

1. **`str` is owned.** It is an owned byte string (a wrapper around `[]byte`),
   moved like any other owned type and borrowed as `&str` / `mut &str`. With
   one owner it may also be appended to in place.
2. **`rc T` is declared reference counting**, marked where it is used, like
   `&T`. It is not marked on the declaration, so one `[]Node` or `str` can be
   unique in one place and shared in another.
   - `rc T` is owned and moves by default.
   - The payload is immutable: an `rc T` gives out only `&T`. Mutation goes
     through copy-on-write when the count is 1, or through a `with` block in
     the style of `Shared.with`.
   - Because payloads are immutable they are built bottom-up, so they cannot
     form cycles and need no cycle collector.
3. **Borrows are transparent.** `&` of an `rc T` is a plain `&T`. Code that
   receives a borrow cannot tell how the value is kept alive. A `&str` view
   already works this way.
4. **Copies are implicit only when they are free.** Bitwise copy types (no drop,
   no count) are copied implicitly, as now. Everything else needs one of:
   - `x.share()`: another handle to an `rc T`, O(1);
   - `x.clone()`: a deep copy, through a library `Clone` interface, O(n).

   This replaces the mix of `copy()` and `clone()` methods in the library
   (`http.Headers.copy`, `json.Json.clone`, ...). It also replaces the
   `copyInts` helper, which is copied into four compiler modules.
5. **Shared substrings** come from `rc str` slices: the handle carries a block,
   an offset and a length, as `str` does today. A borrowed slice `&s[a..b]`
   stays free.
6. **Literals.** A literal where a `&str` is expected stays a rootless static
   view. Where an owned `str` is expected it **allocates** a copy (decided
   2026-11-17). An immortal `rc str` or a static flag inside the owned string
   would also have worked, but each brings back special cases. A `str`
   constant behaves the same way. Neither needs a source edit, so the sweep
   does not count the `global` kind as an edit.

## 3. Migration plan

1. Measure (this note, section 4).
2. Add the new pieces without changing existing behaviour: `rc T`, `share`,
   and the `Clone` interface. Under counted `str`, `clone` on a `str` takes a
   count.
3. Migrate the lib, then the compiler, so their source compiles in both modes
   (the compiler is self-hosted and must keep building from the seed).
4. Flip the default: owned, uncounted `str` in the runtime, then reseed.
5. Move `Shared[T]` onto `rc`. Remove the special cases: borrow inference for
   `str`, and the `&[]str` → `&[]&str` coercion.
6. Migrate lexdb last.

## 4. Measurement

`LXL_OWNED_STR=1` makes the checker treat `str` as owned. Every type that is
copied today and would be owned under this mode is "soft". For each soft type,
the move and copy errors are logged to stderr instead of stopping the build.
After logging, the value is copied as today and checking goes on. Each line
has this form:

    OWNED_STR <kind> <file>:<line> <name> <what took it>

The kinds:

- `move`: a legal move. The value is not used again, so no edit is needed.
- `clone`: a move that a later use shows needed a second owner. It is logged
  at the move.
- `borrow`: the value is moved out through a borrow.
- `place`: the value is moved out of a field or element.
- `loop`, `held`: other moves that need a second owner (inside a loop, or
  while a call holds a borrow of the value).
- `tcopy`: a `T: copy` parameter instantiated with a soft type.
- `gvar`: a global `var` of a soft type.
- `fill`, `apart`: `array(n, v)` with a soft `v`, and destructuring a place of
  a soft type.

The check runs only on code that is reached, so the library is covered by
what the compiler, the tests and the commands use. With the flag off the
output is byte-identical: the compiler, `cmd/jq`, `cmd/grep` and
`lib/examples` were compared with `--emit-c`.

To reproduce:

    LXL_LIB=$PWD/lib LXL_OWNED_STR=1 out/lxlc compiler/main.lxl --emit-c 2>&1 >/dev/null | grep ^OWNED_STR | sort -u

### Results (main at 9835e4c0, lexdb excluded)

Sites are distinct after removing repeats (generic instances report once per
instance).

| code | lines | edit sites | of which an argument | free moves | `T: copy` | globals |
|---|---|---|---|---|---|---|
| compiler | 42k | 529 | 242 | 479 | 19 | 0 |
| lib (reached part) | 52k | 304 | 118 | 184 | 1 | 3 |
| tests and cmd | 30k | 306 | 131 | 232 | 3 | 7 |
| **total** | | **1139** | **491** | **895** | **23** | **10** |

Seven programs also stop on errors this mode does not soften:

- a closure that moves a captured string (`regex.lxl:2035`, `httpload.lxl:160`,
  `tlsbench.lxl:85`);
- a string borrow kept in a `var` (`pgwire.lxl:533`);
- one mutable-borrow overlap (a test).

What took the value, for the 1139 edit sites:

- **812 are probably borrows.** The value goes to a call argument, a `let`, or
  an `if` or `match` arm. These become `&x`, often with the callee's parameter
  changed to `&str`.
- **327 are stored.** The value is appended, returned, assigned, or put in an
  array literal. These are the real second owners: `clone`, `share`, or a
  change of design (`replace`, `swap`).

Edits per file are concentrated: `check.lxl` has 197 and `sema.lxl` 104, then
`redis.lxl` 88 and `emit.lxl` 60. Everything else has under 45.

### Reading

- **The cost is about 1,150 mechanical edits outside lexdb**: roughly one per
  80 lines in the compiler and one per 170 in the library. Seven in ten are
  borrows, which cost nothing at run time. About 330 sites need a real second
  owner; those decide how often `clone`/`share` appear in practice.
- **Most moves are already free.** 895 string moves need no edit at all.
- **Generics need attention.** There are 23 `T: copy` instantiations with
  strings or records that hold strings (`Map`/`Set` keys and similar). The
  library's generics will need `Clone` in places where they now rely on
  `copy`.
- **The log is the worklist.** It lists every site per file, so the migration
  can go file by file.

## 5. Follow-ups found during the migration

These were found while migrating the library. None of them is a regression
yet: while `str` is counted, a `clone` is a count change, exactly as the
implicit copy was. They need doing before or at the switch to owned `str`.

- **Shared buffers become `rc str`.** For example, the TDS cursor `Cur` takes
  a `clone` of the whole reply buffer for every token it reads
  (`tds.cursor`, `sub`, `other`). Once strings are owned, each of those would
  copy the buffer, which can be quadratic on large replies. These are the
  read-only, shared values `rc T` is for: the field becomes `rc str`, and
  `clone()` becomes `share()`.
- **Argument arrays of views.** `redis.command` takes `&[str]`, so callers
  clone every key into a temporary array (`c.command(&["GET", key.clone()],
  w)`, about 40 sites). Taking `&[&str]` would remove those clones. The
  change is source-compatible for array arguments, but not for array
  literals with an owned temporary element (`seconds.toStr()`): such an
  element cannot be used as a view today. The language change is to let a
  temporary inside an array literal that is an argument live to the end of
  the statement, as a temporary argument does.
- **Borrows should freeze only the field they borrow.** `let s = &d.s`
  freezes all of `d`, so a later write to another field (`d.pos += 1`) or a
  `mut &` call on another field is rejected. With copied strings,
  `let s = d.s` sidestepped this; with owned strings, borrowing a field is the
  normal pattern. Batches 2 and 5 worked around it, by reading through the
  field each time (json, regex_syntax) or with a clone (http). Rule 3 already
  compares paths for borrows taken at a call; a `let` borrow should freeze
  just its path in the same way.
- **Moving a field out of a temporary** (`c.poll(false).ev`) is cloned today.
  Moving out of a temporary is safe, because the rest of it is dropped, so it
  could be allowed.
- **`array(n, v)`** should clone `v` for each element when `v` is
  `Clone`-able. It needs no source edits, so the `fill` kind does not count
  as an edit.
- **Empty strings need no buffer.** An empty owned `str` is a header with
  capacity 0, so creating and dropping it costs nothing. The same capacity-0
  check could make every literal a free view of static bytes (copied before
  any write) if literal allocations prove costly. Measure that at the switch.

## 6. Language issues the migration exposed

**Decided 2026-11-17:** implement 1 (freeze only the borrowed path), 10
(implicit shared borrow of arguments), 9 (a match moves a local at its last
use) and 4 (generated `clone`) first, before the compiler migration. The
others come back for discussion after that.

The user asked (2026-11-17) for deeper language issues found during this
work to be collected and presented at the end, since this redesign is the
time to change the language. Each entry says what was seen, where, and
whether it was confirmed with a test.

1. **A borrow of a field freezes the whole variable.** Confirmed:
   `let s = &d.s` followed by `d.pos += 1` is rejected ("'d' is borrowed by
   's' and cannot be assigned"), although the fields are disjoint. Liveness
   is already precise: the write is accepted once `s` is dead. Owned strings
   make borrowing a field the normal way to read one, so this will come up
   everywhere. Freezes should record the borrowed path, as rule 3 already
   does for borrows taken at a call. Seen in json, regex_syntax and http
   (batches 2 and 5), markdown and pgwire (batch 8). Worst case:
   `jq_parse.next()` clones the whole jq source for every token, because
   `let s = &p.src` blocks the assignment to `p.tok`. That is a count
   today, but after the switch it copies about 10 KB per token, so this
   issue must be fixed before the switch.
2. **Temporaries inside an array-literal argument cannot be views.**
   `f(&["GET", key, n.toStr()])` with `f(args: &[&str])` is rejected for the
   temporary `n.toStr()`. A temporary argument already lives to the end of
   its statement; an element of a literal argument could do the same. Without
   this, APIs that take a list of strings force a clone of every element
   (redis, about 40 sites).
3. **No moving out of a temporary.** `c.poll(false).ev` must be cloned,
   because a field cannot be moved out, even of a temporary that is about to
   be dropped.
4. **Records and arrays have no `clone`.** Today only types that are copied
   while `str` is counted get the built-in `clone`. Once `str` is owned, a
   record holding a `str`, and any `[]T`, needs one. The options are clone
   code generated for every type whose parts are `Clone` (like drop code),
   or an explicit opt-in on the declaration (like `derive`). This has to be
   decided before the switch.
5. **By-value receivers consume silently.** Many library methods take their
   receiver by value (`fn (e: Error) toStr()`). For a copy type that cost
   nothing; for an owned type, `e.toStr()` moves `e`. Batches 1, 4 and 5
   changed these to `&Self`. The rule that "a by-value receiver on a copy
   type satisfies `&Self`" is itself a special case that owned types expose.
   One option: a by-value receiver on an owned type must be written as
   consuming, so that it is visible.
6. **Iterating an owned array gives borrows, unlike a copy array.**
   `for m in xs { var name = m }` worked with counted `str` and fails with
   owned `str`, because `m` becomes a borrow. The language has no consuming
   loop (`for m in move(xs)`) to take the elements by value. Seen in pgwire
   and the SQL Server tests.
7. **Compound assignment with a mutable borrow of the target.**
   `s += ch(mut &s)` (red-team test rt2_g09) relied on `s` being copied
   before the call. With an owned `s` it is a conflict. The spec for `+=`
   on owned types needs deciding: evaluate the right side first, or reject.
8. **String globals.** SPEC 5.2 allows no global `var` of an owned type
   (only `once`), because borrowing one soundly would need effect rules. With
   counted `str`, string globals were copy globals and were allowed. 28
   exist: caches (`httpserver.DATE_TEXT`, refreshed each second), a log
   (`os.ENV_LOG`), and test fixtures (`ADDR`, `RESULT`). Making `str` owned
   forbids them all. Option: allow owned global `var`s with value-only access
   and no borrows. Reading takes `g.clone()`, writing replaces and drops the
   old value, and `&g` stays an error. No reference into a global ever
   exists, so the soundness argument that ruled them out does not apply.
   Threads still need the separate answer from concurrency.md, as they do
   for copy globals today.
9. **A match on a dead local borrows instead of moving.** Confirmed:
   `let r = f(); match r { Err(e) { wrap(e) } }` binds `e` as a borrow, so
   `wrap(e)` needs `e.clone()`. `match move(r)` moves without a clone. The
   agents wrote `Err(e) { Err(tlsFail(e.clone())) }` dozens of times, because
   `move(r)` is easy to miss. A match on a local that is not used after the
   match could move it implicitly, as `let` and argument passing already do
   for a last use.
10. **Read-only functions that take a value consume it.** `println[T:
    Show](x: T)` and `print` take their argument by value, so with owned
    strings `println(name)` moves `name`, and printing a string that is used
    again needs `println(name.clone())`. The w9 batch found this throughout
    the tests, and user code will hit it constantly. Many other read-only
    library functions are generic over `T` by value. There are two ways out:
    - Such functions take `&T`, and callers write `println(&name)`. That is
      explicit but noisy, and `println(n)` for an `int` would need `&n` too.
    - **An implicit shared borrow for arguments:** where a parameter is
      `&T` and the argument is a place or a temporary, the call borrows it
      without writing `&`. A shared borrow has no effect on the caller's
      ownership, so making it implicit hides nothing that matters. `mut &`
      stays explicit, because it does matter.
    This is probably the biggest ergonomic question the switch raises.
11. **Comparing an `Option[str]` with a borrowed string allocates.**
    `if Some(d.path.clone()) == exclude` (zoxide) builds an owned `Option` to
    compare. This is a library gap rather than a language one:
    `exclude.is(&d.path)` (an `Option[T]` method comparing with `&T`), or
    `==` between `Option[T]` and `Option[&T]`.
