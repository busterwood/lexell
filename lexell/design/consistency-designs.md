# Design notes: findings 2, 5 and 7 (branch lang/consistency)

Status: proposals for review, 2026-11-18. The smaller findings (1, 3, 4, 6, 8)
and lexdb's requests are done on this branch (design/consistency.md). These
three change the language more, so each is written up before it is built.

## Finding 2: any type may hold borrows (not only value types)

**Now.** SPEC 10 rule 1: a value holding borrows may be a field of a *value*
record or closed type, an array element, or the argument of a `borrow` type
parameter; not a field of a boxed type. So `[]&str` is allowed, but
`Map[&str, int]` is not (Map's `K` is not `borrow`), and a recursive syntax
tree cannot hold `&str` views of its source (recursion needs a boxed type).
Word counts, symbol tables and parsers must clone every key and name.

**Proposal.**
1. A boxed record or closed type may hold borrows, under the rules a value
   type follows: such a type is borrow-class, so its values are second class
   (a parameter, receiver, `let`, `var` with fixed roots, field, element,
   result rooted at its sources; never a global, a constant, a task's
   argument or result, or behind `intoPtr`). Its roots are the roots of what
   it holds, as for `[]&T` (an array is a heap object too, so the heap is not
   the reason for the rule). It may not have a `drop` method (already the
   rule for types holding borrows).
2. The library's containers declare `borrow` type parameters where storing a
   borrow is sound: `Map[K: borrow, V: borrow]`, `Set[T: borrow]`,
   `UniqueList`, `Heap`, `Option`/`Result` already are. A `Map[&str, int]` is
   then a borrow-class local: `var counts: Map[&str, int] = newMap()` over
   `strings.split(&text, " ")` counts words with no copies, and the map's
   roots (`text`) stay frozen while it lives.
3. A constant may be of a boxed type: static data, never freed, read as a
   new value (a clone) where an owned value is wanted, as `str` constants
   are. (Independent of 1 and 2.)

**What it costs.** The checker's borrow-class test stops excluding boxed
types (sema `isBorrowClass` and the field rule); the library adds `borrow`
to type parameters and checks that its generic bodies do not store a `T` in
a global or a task. Emit needs no change: a borrow is a pointer or view in a
field like any other. Risk: generic library code that moves a `T` into a
place that outlives the call (a task, a `Shared`) must be refused for borrow
instances; the instance check already does this for `borrow` parameters.

**What it breaks.** Nothing: it only accepts more programs. lexdb can then
key per-statement maps by views of its input (finding 5 of its review).

**As built (2026-11-18).** Point 1 is done: the field rule was the only
thing tying borrows to value types (declBC already covered boxed types); one
walk (holdsMut) had to learn that recursive types can now hold borrows.
Point 2 is blocked by two limits of the checker, found when `Map`'s
parameters were declared `borrow`:
- **Lending from a borrow-holding value.** `Map.at`, `find`, `atMut` and
  iteration return borrows of the map's own storage. For a parameter whose
  type holds borrows, design/borrow-types.md D5 lets a result borrow only
  what the parameter holds, never the parameter itself ("no lending"), so
  these methods cannot be written for `Map[&str, V]`. Allowing it needs
  results with two roots (the container, and what it holds).
- **Interfaces through a borrow type.** `&str` does not satisfy `Ord`
  (`cmp` is declared on `str` with a `&Self` receiver), so even `sort` of a
  `[]&str` is refused; `Eq` and `Hash` likewise, which a map key needs.
Also, `Set`'s `union`/`filter` build a set from two others inside closures,
and a `var`'s fixed roots (rule 7) cannot express "what a or b borrows".
Point 3 (boxed constants) is not done yet.

## Finding 5: `s[a..b]` is always a view

**Now.** SPEC 4.1: `s[a..b]` is a view (`&str`) where a `&str` is expected
and a new owned `str` (a copy) elsewhere; `xs[a..b]` on an array is always a
slice (a borrow). The same syntax has opposite costs on the two sequence
types, and on strings the cost depends on context the reader cannot see
(`let t = s[0..5]` copies; `let t: &str = s[0..5]` does not).

**Proposal.** `s[a..b]` is always a `&str` view, like `xs[a..b]`. An owned
substring is written `s[a..b].clone()`. Literals and constants keep their
rule (a static view, a new value where an owned one is wanted).

**Migration.** Like the owned-str switch, with the compiler driving it:
1. A migration mode (`LXL_SLICE_VIEW=1`) where a slice used as an owned
   value is accepted and logged (file, line, what takes it: a `str`
   parameter, a field, a return, a `let` kept past a change of `s`).
2. The sweep tool lists the sites; each becomes `.clone()` (a mechanical
   edit, Haiku batches as before), or a borrow where the value is only read
   (`f(s[a..b])` with `f(x: str)` that only reads `x`: make `x: &str`).
3. Switch: the mode's logging becomes an error naming `.clone()`.

**What it costs.** A checker change in one place (the slice expression's
type) plus the mode; the sweep reuses tools/owned_str_sweep.sh. Expect a few
hundred sites in the library and commands and more in lexdb (its parsers
slice constantly); most become borrows, which is the point.

**What it breaks.** Every site that keeps a substring as an owned value
(until migrated). lexdb gets a recipe entry and the sweep's `-l` worklist.

## Finding 7: tasks that borrow

**Now.** `task.scope`, `within`, `par.map` and `workers` take closures that
may capture the caller's locals; `Scope.start` and `spawn` take a plain
`fn(A): T` and an owned argument. A scope already guarantees that its tasks
end before it returns (SPEC 16), which is what borrowing needs, so read-only
context (a config, a TLS context, a router) is moved into `rc`s and shared
per task only because `start` cannot borrow.

**Proposal.**
1. `s.run(f: &fn(): T): Future[T]` (and `s.go(f: &fn())` for `spawn`): a
   task running a closure that may capture, **read-only**, the variables the
   scope's own closure captures from outside the `task.scope` call (the
   scope's frame and everything outside it outlive every task of the scope).
   `start` and `spawn` stay for owned arguments.
2. Checking: a closure passed to `run` may not capture mutably, and may not
   capture a variable declared inside the scope closure (it may be gone
   before the task runs: the scope closure's locals die when it returns,
   which is before the scope waits for its tasks). The captured variables
   are frozen (rule 4) for the whole `task.scope` call, as the scope
   closure's captures already are.
3. Runtime: the task gets the closure's function and environment pointer;
   the environment lives in the frame that called `task.scope`, which is
   parked in the scope's wait until every task is done, so it stays valid.
   Cancellation does not change this: a cancelled task still runs to its
   next park and unwinds before the scope returns (no task is killed from
   outside).
4. `task.both(a, b)` and `task.forEach(xs, f)` (planned in concurrency.md)
   follow from the same check and can be added with it.

**What it costs.** A new closure kind check in the checker (captures from
outside the scope closure only, shared only), a runtime entry taking a
function and environment, and library methods. Not built: mutable captures
(they need the effect rules of SPEC 13).

**What it breaks.** Nothing (new methods). Servers can drop the `rc` and
`share()` plumbing for read-only context.

## Order

2, then 5, then 7. 2 and 7 only accept more programs; 5 is a switch and gets
lexdb's recipe entry and worklist like the owned-str switch.
