# Language consistency work (branch lang/consistency)

Status: in progress, started 2026-11-18. The review that found these is
summarised below; each change, as it lands, also gets a row in
[owned-str-lexdb.md](owned-str-lexdb.md) section 6 (what lexdb must change),
and its rule goes into SPEC.md.

Decisions taken by the user (2026-11-18): all eight findings to be fixed, on
this branch, merged to main later. Finding 1: option (a), a static no-cycle
rule.

## Done on this branch

- AE, AF, AG: field moves out of dead locals; several-source borrow results;
  var borrow roots from the first real borrow.
- AH: `G.getOrSet(f)` on set-once globals.
- AI (finding 6): extern string parameters are `&str`; intrinsics documented
  with `&str`.
- AJ (finding 8, part): `Map.find`; `println` without the concatenation. The
  clone in `str.toStr()` stays until `Show` writes into a buffer.
- AK: `for` over a dead local consumes it.
- AL: `pure` externs callable from par.map kernels.
- AM (finding 4): derived `eq`, `hash`, `toStr`. `cmp` is not derived; an
  opt-in (e.g. a `derives Ord` marker) is not done yet.
- AN (finding 1, option a, with weak handles as the user agreed): the cycle
  check, `task.Weak`, `share()` for handle types, httpserver's app in an `rc`.
- AO (finding 3): globals of any type, initialized on first use, `G.with`.
- AP, AQ (lexdb's review): `s += x` in place; `StrBuf.text()`.
- AR (the user, 2026-11-18): `StrBuf` removed; strings are their own buffers
  (`addByte`, `addInt`, `addLine`, `clear`, `bytes`).
- AS, AT (finding 2): boxed types may hold borrows; `&U` satisfies `U`'s
  interfaces. Containers of borrows wait for lending (consistency-designs.md).
- AU (finding 5): `s[a..b]` always a view. Commands migrated by Haiku agents
  (eza, zoxide, redis-cli), the rest by a compiler-driven fixer.

## Plan, in order

1. Small fixes.
   - 6: externs and intrinsics take `&str` for a string they read; a `str`
     parameter on an extern is an error. Call sites unchanged (implicit borrow).
   - 8 (part): `Map.find(&k): Option[&V]`; `print`/`println` write a `str`
     without copying it.
   - `for x in xs` over a local not used afterwards consumes it, as `let`,
     `match`, arguments and `return` already do.
1b. `extern "c" pure fn ...` (user agreed 2026-11-18): the declarer's promise
   that the C function has no I/O, no shared state and no callbacks, so
   par.map kernels may call it (kernel.lxl's extern allowlist then covers
   `pure` externs as well as the built-in names).
2. Finding 4: generated `eq`, `hash`, `toStr` for types without their own
   (all parts having them, no drop method), like clone glue; `cmp` opt-in.
   A fieldless enum's built-in `==` satisfies `Eq`; `==` inside a type's own
   `eq` on fieldless variants does not recurse.
3. Finding 1 (a): a `Shared[T]` or `rc T` instance whose payload type can
   reach a `Shared` of a type that reaches it again is an error (no cycles
   through handles). `clone()` of a `Shared`, or of a type holding one, is an
   error: `share()` (a record holding one needs its own clone method).
   Correct owned-str.md: `Shared` is single-threaded (tasks share a thread).
4. Finding 3: one model for mutable globals. `var G: T = e` for any type
   that holds no borrows: a constant initializer is static data as now,
   anything else runs before `main` (imports first, then declaration
   order). Value-only reads as now; `G.with(fn(g: mut &T) { ... })` lends it
   mutably, with an open flag (a nested `with`, or `G = v` while open, stops
   the program, exit 13, as `Shared.with`). Array globals are copied to the
   heap at start so they can be changed. Dropped at exit like set-once
   globals.
5. Design notes first (design/*.md), then implementation:
   - Finding 2: boxed records, boxed closed types and library collections
     may hold borrows (`Map[&str, int]`, a recursive AST of `&str`), under
     the rules arrays follow; boxed types may be constants (static data).
   - Finding 5: `s[a..b]` is always a view (`&str`); an owned substring is
     `s[a..b].clone()`. A migration like the owned-str switch.
   - Finding 7: `Scope.start` (and `spawn`) take a closure that may borrow,
     read-only, what the scope closure borrows from outside the scope.
6. From lexdb's review (design/lexdb-owned-str-review.md on main, "Language
   and runtime", 2026-11-18), added at the user's request:
   - `s += x` copies the whole string every time: 100k, 200k, 400k one-byte
     appends take 0.07, 0.31, 1.22 s (quadratic). owned-str.md 2.1 says a
     string with one owner may be appended to in place: give an owned heap
     string spare capacity and grow it geometrically, so `s += x` on a
     variable is amortized O(len(x)).
   - A `&str` view of a `StrBuf`'s bytes (no copy), so a reused buffer can
     serve as a lookup key (lexdb's composite GROUP BY and hash-join keys).
7. Finding 8 (rest): `Show` writing into a buffer — later, not in this round.

Smaller splits noted but not decided: by-value receivers consuming silently;
`Where` for programs; a `try` conversion hook.

## The review (2026-11-18), in short

1. Two counted handles; `rc`'s no-cycle claim is false (Shared can cycle,
   also through rc); `clone()` of a `Shared` aliases mutable state.
2. `value` (a layout keyword) decides copy, const, plain global, holding
   borrows and recursion; `Map[&str, V]` and recursive ASTs of views are
   refused while `[]&str` is allowed.
3. Globals: const, var (value-only), once, and `once Shared` in practice;
   `[]int` refused while `Option[[]int]` is allowed.
4. `clone` generated, `eq`/`hash`/`cmp`/`toStr` not; enum `==` is not `Eq`,
   and `eq` written as `a == b` recurses.
5. `s[a..b]` copies or views by expected type; `xs[a..b]` always a view.
6. `str` parameters: move in program functions, read in intrinsics and
   externs; externs cannot say `&str`.
7. `Scope.start` cannot borrow though the scope makes it sound.
8. `toStr` on `str` clones; `println(s)` copies; `Map.get` clones the value
   and no borrowing lookup that tolerates a missing key exists.
