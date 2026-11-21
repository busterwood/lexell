# Optimization experiments from two outside reviews (2026-11-21)

Status: experiments on branch `exp/opt-ideas` (worktree `~/Work/lexell-optexp`), from
main `5f30415d`. One change is kept on the branch (`3a6f4ddf`); the rest were measured
or counted and not built. The goal stays the one in
[small-fast-compiler.md](small-fast-compiler.md): a small, fast compiler, so an idea is
judged by "Judging a pass" (HISTORY.md) and by its size and compile cost, and is counted
before it is built where a count can bound it.

Two reviews proposed about seventeen ideas. Some had already been measured here: the
SSA/GVN oracle, interprocedural registers (`perf18`), branch layout (`perf20`), bool
folding, live-range splitting, and check removal (HISTORY.md, "Tried and shelved").
Others no longer apply: `str` reference counts went away with owned strings
(`5c4dd44f`).

## Method

- **Compilers are compared as matched stage-2 builds without `-O`.** Each compiler is
  built by the seed-built compiler, then builds itself. An earlier comparison had `-O`
  on the base build only. That alone looked like +4% compile cost, and it was an
  artifact: `-O` is not the default, and perfsuite builds its compilers without it.
- **perfsuite inputs are frozen at `5f30415d` (`--frozen`).** The script's default,
  `af99f933`, predates the `lexell/` rename, so `git archive` of it fails.
- **Point selects** use the in-process harness, `pt.lxl`, from the R3 work:
  20,000 statements, `LXL_HASH_SEED=1`, instructions per statement.
- **The machine was shared** with another session's suite. Two byte-identical copies
  of one binary differed by up to 9.7% in cycles, so instructions decide and cycles
  only have to agree in sign.

## 1. Kept: jump tables and bit tests (`3a6f4ddf`)

The native backend lowered every `match` on a closed type, every int if-chain and every
`S_SWITCH` as a linear compare chain. lexdb has 22 matches with 8-15 arms and 2 with
16-31. Among them are `sql.text`, `ops.kindOf`, `rows.encVal` and `access.encKeyPart`,
all per value. The compiler's own dispatch is `k == E_A || k == E_B || ...` sets.

The change is about 160 lines in `x64gen.lxl` and 20 in `x64.lxl`:

- **Jump tables.** `genChain` matches `if x == a {..} else if x == b || x == c {..} ...`
  in three shapes: a plain if, an if alone in a block, and the fused
  `bool c = ...; if (c)`. x must be a load that cannot fail (`loadOnly`, the same tree
  each time). With three or more arms and four or more constants (span <= 4 per
  constant, <= 1024), the chain becomes `sub; cmp; ja default; lea rcx,[rip+T];
  movsxd rax,[rcx+rax*4]; add rax,rcx; jmp rax`, with a table of 32-bit offsets in
  the text. The assembler's fix-ups gained a base label for table entries.
- **Bit tests.** In `branch`, `branchBits` turns an `||` of four or more `x == c`
  within 64 of each other into `cmp; ja; mov rcx,mask; bt rcx,x; jc/jnc`.

Counts: 62 chains and 51 bit tests in the self-build.

Results:

| measure | instructions | cycles |
|---|---:|---:|
| perfsuite compile suite (geomean) | -0.34% | -0.27% |
| perfsuite run suite (geomean) | +0.01% | +0.00% |
| `compiler --native` | -0.43% | -0.17% |
| eza `-T` (the run suite's worst case) | +0.18% | +1.34% (noise band) |
| lexdb point select / sel1 / gs / insert / update | -0.06 / -0.12 / -0.12 / -0.10 / -0.05% | not decidable on this machine |

It passes the second rule of "Judging a pass" (the compile suite gains and the run suite
is not worse). `gate.sh quick` passes, and the native self-build reaches its fixed point.
The win is small, because the run suite and the compiler have few long chains. Its natural
target is lexdb's per-value matches, and TPC-H shows it there.

**TPC-H** (SF1, lexdb only; lexdb at main `52fe2606` built `-O` by main's compiler and by
this one):

- **Order:** runs ABBA, one at a time, each under the exclusive bench lock
  (`~/tpch-w/opt/ab.sh`).
- **Results:** identical on all 22 queries in all four runs, all `ok` against PostgreSQL's.
- **Instructions:** the server's user instructions per query (`iq.sh`) fall on 20 of 22
  queries. Geomean -0.68%; q6 -3.07%, q7 -2.03%, q22 -1.96%, q1 -1.37%, q12 -1.28%,
  q19 -1.02%. Up: q5 +0.15%, q17 0.00%.
- **Time:** CPU total 11,731 to 11,512 ms (-1.86%), geomean -1.84%. Same sign as the
  instructions, inside the placement noise.
- **lexdb suite:** 271/271 with the new compiler (`LXL_NOCACHE=1`).

## 2. Counted, not built

**Sethi-Ullman ordering (review 1, 1.3).** x64gen is an accumulator generator. `pairC`
already evaluates b first when a is simple, constant, in a register, or a pure load. The
order only matters at the general fall-through, where a waits in a "hold" while b is
generated. If b contains a call, the hold goes to a frame slot or a callee-saved register.
Counted over the whole self-build:

- the fall-through runs at 381 static sites;
- 53 of them have a call-free a that could go second (41 frame slots, 12 callee-saved);
- lexdb has 349 such sites out of about 10 MB of code.

Each site saves at most one store and one load. That is below any gate, so it was not
built.

**Niche-filled `Option` (review 1, 1.1).**

- The compiler has no `Option` of a pointer.
- lexdb has 59 such instantiations, held in 39 struct fields. Of those fields, 26 are
  `Option[Expr]`, plus `Option[Prog]` and `Option[BNode]`: AST and plan nodes built once
  per statement, not per row.
- The representation change touches check, emit, lower, the drop glue and both backends.

The likely gain is a fraction of a percent of point-select instructions. Deferred, not
rejected: worth revisiting if per-row data structures start holding optional boxes.

**Interprocedural registers (review 2, 5).** `perf18`: 761 of 25,358 static call sites
(3%) reach a leaf function. The runtime is C, so its clobber set is everything, and most
non-leaf calls reach it. Nothing in the compiler has changed that since.

## 3. Built, measured, dropped: profile-ordered function placement (review 1, 1.7)

**How it was built.** A post-generation relayout: functions move as whole blocks, with
their labels, fix-ups and relocations. They are relocatable because labels are
function-local and calls go through symbol relocations. Under an experimental
`LXL_NATIVE_ORDER`, the 442 functions that cover 99% of the self-build's instructions
were placed first, ordered by instruction samples. Output was byte-identical. The code
is kept in the session scratchpad, not on the branch.

**Results** (8 alternated rounds, fresh copies, median, profile order against source
order):

| compile of | cycles | L1i misses | iTLB misses |
|---|---:|---:|---:|
| compiler (training input) | +0.17% | +5.9% | 2.7x (from ~10K) |
| lexdb `-O` | +0.27% | +9.7% | 4.4x |
| jq | +0.18% | +5.4% | 2.8x |

**Reading.** Hotness order alone is worse than source order. Source order already groups
callers with their callees by module. The ceiling is small too: 2.3M L1i misses against
2.17G cycles is about 1-2% of the compiler's cycles.

**What it leaves open.** A call-graph (Pettis-Hansen) clustering might beat source order,
but it can win at most that 1-2%. It does not touch the lexdb point-select placement swing,
which shows up as branch misses at equal instructions (pts.sh, R1/R6), not as i-cache misses.

## 4. Not pursued, and why

| idea | reason |
|---|---|
| borrow-aware RC elimination (1.4) | `str` counts are gone with owned strings; `rc T` handles are rare |
| region allocation (1.5) | a library or runtime design question for lexdb's per-query temporaries; needs the allocation-site census first |
| BURG selection (1.6) | the measured selection misses were covered by hand (`lea`); a generated matcher is a large step for the remaining addressing-mode cases (codegen-audit rank 5, 80-150 lines by hand) |
| superoptimizer (1.8) | research; no candidate patterns are known to be hot |
| park as an all-clobber call (2.1) | `rt_ctx_swap` is a 51-byte routine (the self-build's map); the saves are small next to a park's run-queue work |
| exact task stack sizes (2.2) | memory, not speed; listed in concurrency.md 7 |
| balanced polling (2.3) | there are no back-edge checks yet to place |
| globals across non-parking calls (2.4) | not counted; globals are first-use initialized and changed with `G.with`, and the hot loops measured here (compiler, lexdb point selects) are not global-bound |
| loop inversion (2.7) | loops are already rotated (`perf20`: 1,926 backward jcc against 275 backward jmp) |
| Perceus reuse (2.8) | plausible: allocation is about 5% of the compiler's samples (malloc, rt_free, pools). The ceiling is the share of drop-then-same-size-alloc pairs, which needs a runtime census first |
| multi-return Result (2.9) | the review itself expects it below the gate |

## 5. Next, in order

1. Done: TPC-H (section 1); merged into main.
2. A census of drop-then-alloc pairs of one size class (runtime counters), to bound
   Perceus-style reuse.
3. Scalar replacement of small records (review 1, 1.2) remains the largest structural
   lever. mid-ir.md's M1 found frame aggregates dominate the spills; it is a project, not
   an experiment.
