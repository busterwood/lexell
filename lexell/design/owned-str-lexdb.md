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

| H | Issue 3, SPEC 9.1: a field of a temporary record can be moved out (`make().name`); the other fields drop at once | 15ef7d47 | yes (only accepts more programs) | none |
| I | Issue 6, SPEC 8: `for x in` a temporary array of owned elements (a call result, a literal, `move(xs)`) consumes it: `x` is an owned element, not a `&T` | aef5031a | yes: verified, every program compiled before and after. A body that relied on `x` being a borrow still works, through the implicit borrow (E). | **Drop timing:** each element drops at the end of its turn instead of with the array after the loop. On early exit the untaken elements drop last to first. Only visible through `drop` methods with side effects. |
| J | Issues 5 and 11: `toStr`/`eq` on string-holding library error and value types take `&Self` (cli, crypto, json, httpserver, redis, sqldialect `Value`/`DbError`, url, uuid, mssql `Diag`); `Option.is(&x)` | b4bbea4a | yes | none |
| K | Issue 7, SPEC 7.4: `s += f(mut &s)` on an owned type is a borrow conflict. No compiler change: it follows from the existing rules once `str` is owned. | (spec only) | yes until the switch | At the switch, such code needs `let t = f(mut &s); s += t`. |

| L | Issue 8, SPEC 5.2: global `var`s of owned types (str, and value records or value closed types built from them) with value-only access: built-in reads in place, `g.clone()`, `g = v`. A borrow (`f(g)`, `g.m()`), a move (`return g`) or `for x in g` is an error. Boxed and array globals must be `once`. | acacd80a | yes. Changed error texts: a global moved out now says "read a copy with g.clone()"; an owned non-array global that used to be rejected as "has the owned type" now compiles, or gets the boxed-type error. | none |

| M | Issue 2, SPEC 4.2: in an array literal of shared borrows `&T`, an element that is a `T` is borrowed (a temporary lives to the end of the statement). `redis.command`, `send` and their method forms take `&[&str]`. | d11e72ae | yes: `&[]str` arguments still convert, and literals now need no clones. Code that passed `&[...]` literals of owned strings to redis keeps compiling. | none |

| N | `rc T`, SPEC 4.9: counted handles to immutable values. `rc(v)` makes one; `share()`/`clone()` add a handle; transparent reads (fields, methods, `&T` arguments, `for`); `unshare()` gives `mut &T` (copy-on-write). `rc` is a keyword only in type position. | 48716697 | yes. New std names `Rc` and `rc`: a local variable named `rc` still works, but calling `rc(...)` inside its scope does not. | none |

| O | `rc` reads, SPEC 4.9: `len`, indexing, slicing, operators, value parameters, returns and `let`s of `&T` all reach an `rc` handle's value. The TDS and TNS clients keep replies in an `rc str`; their cursors share them. | 64bf43d0 | yes (lexdb's TDS and TNS programs compile; the offline suites pass) | none |

| P | par.map's kernel check refuses `rc` count changes (reading through a handle is fine). httpserver keeps its router in an `rc`; `Next[A]` (handed to middleware) holds a handle and `run` consumes it. | 8b69affc | yes | none for lexdb (it has its own servers) |
| Q | `Shared` gets `share()`; `LXL_OWNED_SHARED=1` measures the owned-handle version (as `LXL_OWNED_STR` does for strings); a `copy` type parameter satisfies `Clone`; httpserver's app type is `A: Clone` and each connection gets `app.clone()`. 76 implicit `Shared` copies outside lexdb now say `share()`/`clone()`. | 6d3a55cc, e7244cff | yes: `Shared` is still a copy type, so `share()` is optional today | none |
| R | `task.Frozen` is deprecated in favour of `rc T`: pool keeps its config in an `rc`, so `pool.Pool` is owned (copies are `clone()`). `Frozen` stays only for lexdb. | b33aa25b | yes | none |

| S | The compiler is migrated; library parameters it reads now borrow (`fs.mkdir`, `io.openAppend`, `Option.expect`/`Result.expect`'s message, `StrBuf.addLine` and others: `str` became `&str`). Issue 12: `f([])` infers the element type through a `&[]T` parameter. | ad66f390 to the compiler-migration merges | yes: call sites are unchanged (implicit borrow); verified, every lexdb program compiles. A lexdb function passed where a `fn(str)` value of one of these is expected would not, but none is. | none |

| T | **The switch, stage 1.** `str` and `task.Shared` handles are owned types: `let t = s` moves, a copy is `s.clone()` / `sh.share()`, a `&str` does not turn into a `str` by itself, a string global is read with `g.clone()`, a `str` constant or literal read as an owned value is a new value. `array(n, v)` clones an owned `v`. `std`'s `str.clone()` is the built-in one. In the runtime a string is still a counted block (clone is a count), so performance is as before. | 29c51c20 | **no**: lexdb stops at its first error (`lexdb.lxl:113: cannot move out of global LOG_DIR`). `LXL_OWNED_STR=1` (migration mode) compiles all of it and logs every site: 3,459 for cmd/lexdb.lxl, 1,491 of them free moves, so about 1,970 edits (1,188 borrow, 368 place, 157 clone, 38 captured, 2 loop, 2 global). | as for the library: drops happen where an owner ends, not where its last copy ends |

| U | **The switch, stage 2.** A `str` owns a heap buffer (`{p, cap, len}`; static bytes for literals and constants, shared by copies). `clone()` of a heap string copies its bytes, and an owned substring `s[a..b]` copies; a borrowed slice is free. No counts are left, so a `par.map` worker may clone and drop strings. | 5c4dd44f | no source change beyond stage 1 | **Performance:** where lexdb clones a large string (a page, a row buffer, a message), the clone is now a copy. Look for clones of buffers on hot paths after migrating and make them `rc str` (`share()`), as the TDS and TNS clients do. |

| V | Issue 13: a local string indexed, sliced or used as a left operand is held while the later operands run (`s[f(mut &s)]` is an error); a string global read as an operand that a later operand may change is snapshotted with a clone. Early exits drop innermost first. `design/experiments/q1_split.lxl` imports lexdb and is migrated with it. | 5c4dd44f | lexdb code with `s[f(mut &s)]`-style expressions stops compiling; write `let i = f(mut &s); s[i]` | drop order on early exits from inside a statement with temporaries |

| W | `task.Frozen` is deleted: use `rc T` (step 7). | f92dcdb1 | no: lexdb_time.lxl uses it | none |

| X | `strStatic(s)` (SPEC 11): a copy never freed, whose clones are free. Clone glue leaves static `str` fields as copied. `LXL_RCSTAT=sites` and tools/strsites.py count heap string copies by site. | (this commit) | no | none |

**What the switch does to lexdb, beyond strings:** `Shared` handles become
owned, so lexdb's implicit `Shared` copies (32 lines mention `task.Shared`)
need `share()`, and `task.Frozen` goes, so lexdb_time.lxl's three
`task.freeze` sites become `rc(...)` and `Frozen[tz.Zone]` becomes
`rc tz.Zone`. Find the `Shared` sites with
`LXL_OWNED_STR= LXL_OWNED_SHARED=1 tools/owned_str_sweep.sh` after adding
lexdb's programs to the sweep (section 3, step 2). Because these changes
break code that has not been migrated, **lexdb's migration must come before
the switch**.

`rc str` needs no slicing of its own: a reader of a shared buffer is
`rc str` plus positions (the cursor pattern), and a substring is a borrowed
view or an owned copy. Still to come: `task.Shared`/`Frozen` on `rc`, the
generalised borrow report, and the switch itself.

**At the switch, for string globals:** a string global passed to a function,
returned or stored needs `g.clone()` (the sweep's `global` kind lists them;
reads by built-in operators need nothing).

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
- **H:** `make().field` moves the field out; don't clone it.
- **I:** in `for x in f() { append(mut &out, x) }`, `x` is owned; drop the
  `.clone()`. To consume a variable's array, write `for x in move(xs)`.
- **O:** wire-protocol readers (lexdb's pgwire, TDS and TNS servers)
  should follow the client pattern: the received message in an `rc str`,
  cursors holding `r.share()` and a position.
- **N:** a large buffer or structure that several owners read (cursors over
  a reply, a parsed catalog, a plan) is an `rc T`: `share()` instead of
  `clone()`.
- **M:** an API that takes a list of strings to read should take `&[&str]`;
  call sites then pass `&["X", key, n.toStr()]` with no clones.
- **L:** a string global read by a function call or a return becomes
  `g.clone()`; `len(g)`, `g + x` and comparisons stay as they are.
- **J:** `x.clone().toStr()` on those types becomes `x.toStr()`; `Some(y.clone())
  == opt` becomes `opt.is(&y)`.
- **G:** a record or array that is really duplicated gets `x.clone()`; no
  hand-written clone methods (lexdb has `copyInts`-style helpers that become
  `xs.clone()`).

## 3. Procedure for lexdb (on the lexdb refactoring branch)

After `lang/owned-str` is merged into `main`, lexdb on `main` does not compile
until this is done. Do it on the lexdb branch.

1. **Merge `main` into the lexdb branch.** Build the compiler from the seed
   (`lexell/compiler/build.sh`). lexdb stops at its first error.
2. **Worklist.** `tools/owned_str_sweep.sh -l BASENAMES` runs the migration
   mode (`LXL_OWNED_STR=1`) over the lexdb programs too, and lists every site
   in the named files, for example `-l lexdb_exec.lxl lexdb_store.lxl`. With
   no names, it lists every site. When this was written there were about
   1,970 edit sites in cmd/lexdb.lxl's modules (largest: lexdb_exec 669,
   lexdb_store 226, lexdb_parse 138). `design/experiments/q1_split.lxl`
   imports lexdb and is migrated with it.
3. **Parameters first.** `LXL_PARAM_REPORT=1 LXL_OWNED_STR=1 compiler/out/lxlc
   cmd/lexdb.lxl --emit-c 2>&1 >/dev/null | grep 'only reads it' | sort -u`
   lists the by-value parameters that are only read. Make each one `&T`; call
   sites stay as they are (implicit borrow), and many worklist sites go with
   them. Keep a parameter by value if its function is used as a function
   value. Re-run the worklist afterwards.
4. **The sites.** Split the worklist into batches of about 100 sites by file,
   one Haiku agent per batch in its own worktree. The rules that worked for
   the library, tests and compiler, in order of preference:
   - Borrow a field that is only read afterwards: `let n = &p.f`. Writes to
     other fields of `p` stay allowed (change D). A typed borrow:
     `let s: &str = if c { &a.name } else { "x" }`.
   - Pass a value to a `&T` parameter as it is: `f(x)` borrows (change E).
   - A private function that only reads a by-value `str` (or record)
     parameter takes `&str` (`&T`).
   - A `match` on a local that is not used afterwards moves it (F);
     `for x in f()` gives owned elements (I); `make().field` moves (H): no
     clone in those.
   - A by-value receiver on a type holding strings becomes `&Self`, even on
     `pub` methods.
   - Otherwise `.clone()` (`.share()` for a `task.Shared`), at the logged
     line: values stored, appended, returned, assigned, put in a literal, or
     passed by value. A string global read by value is `g.clone()`.
   - Shift array elements with `swap`, not by copying.
   - Never edit a test's `// expect:` lines. A test whose point was implicit
     copying is rewritten for owned semantics, keeping its subject.
   - Kinds `tcopy` (a `T: copy` generic used with a str: change it to
     `T: Clone` and clone in its body), `gvar` and `recv` need a person, not a
     mechanical edit.
5. **Shared buffers.** A large string that several readers walk (a page, a
   message, a row buffer) and that the migration clones per reader becomes an
   `rc str`, with readers holding `r.share()` and a position, as in the TDS
   and TNS clients (change O). Look for these in the storage, wire and
   executor layers after the mechanical pass: a clone there is now a copy of
   the bytes (change U).
   To find the clones that cost the most, build with `LXL_RCSTAT=sites` and
   run a workload: `tools/strsites.py` lists the copies by clone site. Strings
   kept until exit (catalog names, say) can be made with `strStatic(s)`, so
   their clones are free (change X).
6. **Verify.** lexdb compiles. Its suite passes (`LXL_NOCACHE=1`, the native
   compiler; see the project's lexdb test notes). The quick gate passes. Run
   the lexdb benchmarks against `main` before the merge, and log them as the
   project's benchmark record requires.
7. **`task.Frozen` is gone** (deleted after the merge, change W).
   lexdb_time.lxl's three `task.freeze(z)` sites become `rc(z)`, and
   `Option[task.Frozen[tz.Zone]]` becomes `Option[rc tz.Zone]`. Reads that
   used `fr.read(fn(z: &tz.Zone) { ... })` read the value directly
   (`z.field`, or pass the handle where a `&tz.Zone` is expected).
