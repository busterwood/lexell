# Owned strings: what lexdb will need

Status: running log, started 2026-11-17. Keep it up to date as each language
change lands on `lang/owned-str`.

lexdb was left out of the owned-`str` migration on purpose: it is large, and
another line of work develops it on `main`. When `lang/owned-str` merges into
`main`, lexdb meets every change below at once. This note says, for each
change:

- whether existing lexdb code still compiles unchanged;
- what behaviour changes;
- what edits the change makes possible or necessary.

The last section is the procedure for migrating lexdb itself. The design and
the reasons are in [owned-str.md](owned-str.md).

## 1. Language and library changes, in the order they landed

| # | Change | Commit | lexdb compiles unchanged? | Behaviour change |
|---|---|---|---|---|
| A | `Clone` interface in std, `str.clone()`; `x.clone()` built in for every type that is copied while `str` is counted | 19aa4f28 and earlier | yes (new names only) | none |
| B | Copy types satisfy `Clone`. `Map.get`, `getOr`, `keys`, `values`, `Set`/`UniqueList` operations, `copyOf`, `copyRange`, `extend`, `filter`, `setOf`, `uniqueListOf` and `Frozen.get` take `Clone` instead of `copy`. `min` and `max` need only `Ord`. | 19aa4f28 | yes: verified, every lexdb test program compiled before and after | none. The one visible difference is an error message: "X does not satisfy Clone" instead of "X is not a copy type". |
| C | Library receivers that borrow: `ProcError`, `IoError`, `strings.ParseError`, `http.Error` and `tls.Error` methods take `&Self` | batches 1 and 5 | yes (method calls borrow either way) | none |
| D | Issue 1, SPEC 10 rule 4: a `let` or `for` borrow freezes only the place it borrows. `let s = &d.f` no longer blocks writes to `d.g`. | ab25df41 | yes (only accepts more programs) | none |
| E | Issue 10, SPEC 7: a value passed to a shared `&T` parameter is borrowed implicitly (`f(x)` means `f(&x)`); `mut &` stays explicit. `print`, `println`, `eprint` and `eprintln` take `&T`. | 1fce2acb | yes: verified over every program | none |
| F | Issue 9, SPEC 9.3: `match x` on a local of an owned closed type (no `drop` method) that is not used again consumes `x`, as `match move(x)` does | 76fe0863 | yes in the tested code (the compiler, the library, every test). In principle an arm that relied on its binding being a borrow could stop compiling; none did. | **Drop timing:** fields that the arm does not bind, or a value that the arm binds and then drops, are dropped at the end of the arm instead of at the end of the enclosing scope. Only visible through `drop` methods that print or do I/O. Check lexdb tests that assert on drop order or close resources in `drop`. |
| G | Issue 4, SPEC 4.7: built-in deep `clone` for arrays, records and closed types whose parts are cloneable, generated like drop code; a type's own `clone` method wins; types with a `drop` method are not cloneable. `Map.get` and the others now work with record values. | 1480a126 | yes (only accepts more programs). An error test that expected `Map.get` to reject a plain record was changed: it now uses a record with a `drop` method. | none |

Not yet decided (design/owned-str.md section 6): issues 2, 3, 5, 6, 7, 8 and
11. Add them here as they land.

**The switch itself**, when `str` becomes an owned, uncounted type, is the
change that breaks code. Everything above is groundwork that lets code be
migrated ahead of it while it still builds both ways.

## 2. What the changes let you remove

After D, E and F, many edits the migration agents made in the library and
tests are no longer needed. A clean-up pass on lexdb should prefer the new
forms from the start:

- **D:** `let s = &p.field` works even when other fields of `p` are written
  afterwards. Don't clone a field just to read it (the agents did this in
  json, regex_syntax, markdown, pgwire and jq_parse).
- **E:** `println(x)` and any `f(x)` with `f(x: &T)` need no `&` and no
  `.clone()`. A private read-only helper that takes `str` should take `&str`;
  its callers need no edit.
- **F:** in `let r = f(); match r { Err(e) { wrap(e) } }`, `wrap(e)` needs no
  `e.clone()` and no `match move(r)`, as long as `r` is not used after the
  match.
- **G:** a record or array that is really duplicated gets `x.clone()`; no
  hand-written clone methods (lexdb has `copyInts`-style helpers that become
  `xs.clone()`).

## 3. Procedure for lexdb

1. **Merge.** Merge `lang/owned-str` into `main`, or `main` into the branch,
   once the lexdb work there is at a stable point. Changes A to G need no
   lexdb edits. Run the lexdb suite (with `LXL_NOCACHE=1`, native lxlc) and
   check the drop-timing note for F.
2. **Worklist.** `tools/owned_str_sweep.sh` leaves lexdb out (it filters
   `lexdb` from the program list). Add the lexdb programs, for example
   `cmd/lexdb.lxl` and `tests/lexdb/run/*.lxl`, or a flag to include them.
   Then run it with the lexdb module names
   (`tools/owned_str_sweep.sh lexdb_exec.lxl ...`).
3. **Rules.** The migration rules are in the agent brief, which is in this
   session's scratchpad. They are summarised here because the scratchpad does
   not last:
   - A value that is only read afterwards becomes a borrow (`let n = &p.name`,
     a typed `let x: &str = if ...`, or pass `x` to a `&T` parameter).
   - A private function that only reads a `str` parameter takes `&str`.
   - A by-value receiver on a type that holds strings becomes `&Self`, even
     on `pub` methods: callers are unaffected.
   - Anything stored, appended, returned, assigned or put in a literal gets
     `.clone()`.
   - Shift array elements with `swap`, not by copying.
   - Never change a `pub` signature or field during the mechanical pass.
   - Never edit a test's `// expect:` lines.
   - Skip the kinds `tcopy`, `gvar`, `recv`, `fill`, `apart` and `global`
     and list them: they need a language decision or a person.
4. **Parallel batches.** Haiku agents in separate worktrees, one batch of
   about 100 sites each, worked well for the library and tests: about 1,600
   sites with no wrong edit found in review. Review every diff, merge, then
   run the gate.
5. **Shared buffers.** Clones of large buffers on hot paths (the cursor
   pattern in tds and tns) become `rc str` shares at the switch. Expect the
   same in lexdb's storage and wire layers: list them, don't optimise them in
   the mechanical pass.
