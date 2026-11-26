# Changing the compiler

The compiler, `lxlc`, is written in Lexell and builds itself. Its own C is
checked in as a seed, so a change has an extra step: the seed must be rebuilt
and must reproduce itself. This page gives the cycle, where things live, what to
turn off when you suspect a miscompile, and what to run before a merge. The
files and passes are described in [compiler/README.md](../../compiler/README.md),
the native backend in [design/native.md](../../design/native.md).

## Where things live

`compiler/README.md` has the table of files with their sizes. In short: the
front end is `syntax.lxl` (lexer, parser), `sema.lxl` (modules, types,
constraints) and `check.lxl` (bodies: moves, borrows, drops, the order of
run-time checks), which writes templates (`tmpl.lxl`). `emit.lxl` instantiates
them and `lower.lxl` builds the IR (`ir.lxl`). The IR passes run in this
order: `borrow.lxl` (`-O` only), `opt.lxl` (inlining), then with `-O` `bfold.lxl`,
`loops.lxl` and `cse.lxl`; `kernel.lxl` checks `par.map` closures. Two back
ends read the IR: `cgen.lxl` prints C, and `x64gen.lxl`, `x64.lxl` and `elf.lxl`
write the executable. `main.lxl` is the driver.

Two things come in pairs. The runtime exists twice: `rt.h` for the C backend
and `native/rt.c` for the native one, so a change to run-time behaviour goes in
both, followed by `python3 lexell/compiler/gen_rt.py` (writes `rt.lxl` from
`rt.h`) and `python3 lexell/compiler/gen_rtx.py` (compiles `native/rt.c` with
gcc and writes `rtx.lxl`). And the language exists in three places that change
together: `SPEC.md`, the compiler and the tests ([testing.md](testing.md)). The
examples in `AGENTS.md` and `docs/lang/` are tests too: `doc_check.py` fails
when one stops compiling.

## The cycle: edit, build beside, test, reseed, gate

`compiler/out/lxlc` is the compiler everything uses. Do not overwrite it while
you work: build the changed sources into a scratch directory with it, and point
the runners at the result with `LXLC`. `build.sh`, `reseed.sh` and the gate
write `compiler/out/` or `compiler/seed/`, so run them as the last steps, not
as the loop.

```sh
T=$(mktemp -d)                                   # or any scratch directory
export LXL_LIB=$PWD/lexell/lib                   # a compiler outside out/ cannot find the library
cp lexell/compiler/out/lxlc $T/lxlc-old          # the compiler you started from

# 1. build the changed sources (the compiler compiles itself in about 0.6 s)
lexell/compiler/out/lxlc lexell/compiler/main.lxl -o $T/lxlc1

# 2. test with it
LXLC=$T/lxlc1 python3 lexell/tests/run.py s10_
LXLC=$T/lxlc1 python3 lexell/tests/compiler/run_tests.py
LXLC=$T/lxlc1 python3 lexell/lib/run_tests.py -j 8

# 3. self-hosting: the new compiler builds itself, and that build builds itself again
$T/lxlc1 lexell/compiler/main.lxl -o $T/lxlc2
$T/lxlc2 lexell/compiler/main.lxl -o $T/lxlc3
cmp $T/lxlc2 $T/lxlc3                            # must be identical
```

`lxlc1` was built by the old code generator and `lxlc2` by the new one, so they
differ when the change affects generated code; `lxlc2` and `lxlc3` must not.
Without `-o`, a compiler writes its output next to the source: always give `-o`.

When a language change is used by the compiler's own source, it takes two
rounds: implement it and reseed, then use it.

Then, as the last steps, which do write the tree:

1. `python3 lexell/compiler/gen_rt.py` and `gen_rtx.py`, if you changed the
   runtime.
2. `lexell/compiler/reseed.sh`. It has `out/lxlc` build the sources through C
   (stage 2, with gcc), stage 2 build them again (stage 3), requires the C of
   the two to be equal, and writes it to `compiler/seed/lxlc.c`. Commit the seed
   with the change.
3. `lexell/tools/gate.sh quick`. Its first step, `tools/seed_check.py`, repeats
   the fixed point without writing the seed and fails when the seed is stale; it
   also rebuilds `compiler/out/lxlc`, from the seed and then natively, as
   `compiler/build.sh` does (`build.sh` alone is `gcc` on the seed, then the
   native build of the sources). `tools/native_selfbuild.sh` is the gate's last
   step: `out/lxlc` builds the compiler natively twice and the two executables
   must be byte-identical.
4. `lexell/tools/gate.sh full` before a merge ([testing.md](testing.md)).

## When a program is miscompiled

Find the pass first. Each switch is read by the compiler, and `-O` builds are
the ones to try:

```sh
lexell/compiler/out/lxlc prog.lxl -O -o prog && ./prog       # wrong
LXL_LOOPS=0 lexell/compiler/out/lxlc prog.lxl -O -o prog && ./prog
LXL_CSE=0 ...           # repeated-load reuse (cse.lxl)
LXL_INLINE=0 ...        # the inliner (opt.lxl); LXL_INLINE=N sets its size limit (default 25)
LXL_STRS=0 ...          # str values left out of the loop optimisations
LXL_NOBORROW=1 ...      # borrow inference for str parameters (-O)
lexell/compiler/out/lxlc prog.lxl -o prog                    # no -O at all
```

The pass whose switch makes the program right is the one to read. Then look at
what it was given and what it made:

- `lxlc --dump-ast prog.lxl` prints the parse tree (one file, no imports), and
  `lxlc --dump-types prog.lxl` what sema resolved: the scopes, types, variants
  and methods of every module, std included. They isolate a parser or sema bug
  from a code bug.
- `lxlc --emit-c prog.lxl` prints the C of the program. A bug that shows in the
  C is above the back ends (`check`, `emit`, `lower`); one that shows only
  natively is in `opt`, `loops`, `cse` or `x64gen`. It is for reading: do not
  build the output with gcc to time it.
- `LXL_NATIVE_IR=prog.ir lxlc prog.lxl -O -o prog` writes the IR after the
  passes, as C, and builds nothing. `LXL_LOOPS=v` prints what the loop pass
  proved. `LXL_NATIVE_MAP=prog.map` lists every function's address, size and
  name, to match a crash address against: the executable loads at `0x400000`,
  and `objdump -d prog` disassembles it with its symbols.
- Run the program with `LXL_CHECK=1`: exit 5 is a leak.

Then write the smallest program that shows it and add it to the suite
([testing.md](testing.md)): `tests/run` when the spec says what is right.

## Behaviour that must not change

An optimisation or refactor is meant to keep every program's behaviour.
Compare the new compiler against the old one on every test:

```sh
LXL_PREV=$T/lxlc-old python3 lexell/tests/run_prev.py --native --compiler $T/lxlc1
LXL_PREV=$T/lxlc-old python3 lexell/tests/run_prev.py --native --compiler $T/lxlc1 --lib --redteam --gen 200
```

Each program is built by both. They must fail alike, or print and exit alike
under `LXL_CHECK=1`; a `DIFFER` line names the program. `--native` matters:
without it both sides build through C and gcc. For the shape of the generated
code, `tests/vrgen.py` and `tests/loopgen.py` build generated programs three
ways (C, native, native `-O`) and compare, and `LXLC=$T/lxlc1 python3
lexell/compiler/fuzz.py -n 2000 --seed S --keep $T/fuzz` mutates every test
program, which must compile or fail with one `file:line: message`, never crash
(each mutant is written beside its source for a moment, so that its imports
resolve). A change to `-O`'s output also needs its
speed judged, by instructions and by cycles at several placements
([performance.md](performance.md)).

## Before a merge

- The test for the change fails without it, and the suites you touched pass.
- `SPEC.md` says what the compiler now does, and `docs/lang/` and `AGENTS.md`
  still compile (`python3 lexell/tools/doc_check.py`).
- The seed is rebuilt and committed, and `gate.sh quick`, then `gate.sh full`,
  pass; the full gate runs the red-team rounds under sanitizers and the
  generators above.
- When the compiler and the spec disagree, the compiler's behaviour is what
  programs see: fix one of them in the same change, and say which.
