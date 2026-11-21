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

## 1. Kept: jump tables and bit tests (`3a6f4ddf`, revised in the next commit)

The native backend lowered every `match` on a closed type, every int if-chain and every
`S_SWITCH` as a linear compare chain. lexdb has 22 matches with 8-15 arms and 2 with
16-31. Among them are `sql.text`, `ops.kindOf`, `rows.encVal` and `access.encKeyPart`,
all per value. The compiler's own dispatch is `k == E_A || k == E_B || ...` sets.

The change is about 160 lines in `x64gen.lxl` and 20 in `x64.lxl`:

- **Jump tables.** `genChain` matches `if x == a {..} else if x == b || x == c {..} ...`
  in three shapes: a plain if, an if alone in a block, and the fused
  `bool c = ...; if (c)`. x must be a load that cannot fail (`loadOnly`, the same tree
  each time). With **eight or more arms and eight or more constants** (span <= 4 per
  constant, <= 1024), the chain becomes `sub; cmp; ja default; lea rcx,[rip+T];
  movsxd rax,[rcx+rax*4]; add rax,rcx; jmp rax`, with a table of 32-bit offsets in
  the text. The assembler's fix-ups gained a base label for table entries.
- **Bit tests.** In `branch`, `branchBits` turns an `||` of four or more `x == c`
  within 64 of each other into `mov rcx,mask; xor edx,edx; cmp x,span; cmova rcx,rdx;
  bt rcx,x; jc/jnc`. There is one branch, on the answer, and none on the range.

### The first version regressed cmark, json and jq (found with PERFORMANCE.md's benchmarks)

The first version (`3a6f4ddf`, merged as `671520bf`) built tables from three arms, and its
bit test had a branch on the range (`cmp; ja`). PERFORMANCE.md's application set, run
interleaved on CPU 4 (`~/tpch-w/opt/perfmd/apps2.sh`, 7 rounds, fresh copies), showed the
problem; perfsuite's run suite has none of these programs.

| | instructions | cycles | branch misses |
|---|---:|---:|---:|
| cmark | -3.40% | **+4.33%** | **+54.7%** |
| json | -0.73% | -0.08% (median +1.51%) | +7.4% |
| jq | -0.64% | +0.60% | +3.5% |

The branch-miss profiles named two causes:

- **cmark: `markdown.Out.escape`.** `c == '&' || c == '<' || c == '>' || c == '"'` runs
  on every output byte. The compare chain is four branches that are almost never taken,
  so they predict perfectly. The bit test's range check (`c > 62`) is taken on letters
  and not on spaces, digits and punctuation: that is the text, and it mispredicts.
  The range check is now a `cmov` that empties the mask.
- **json: `json.writeValue`.** It is a six-arm `match` on `Json`. The chain predicted
  better than one indirect jump on this data. Tables now start at eight arms; lexdb's
  per-value matches have 13-15.

The revised version against main, with every timed step under the exclusive bench lock
(`~/tpch-w/opt/perfmd/all3.sh`):

| PERFORMANCE.md section | instructions | cycles |
|---|---:|---:|
| ten microbenchmarks, `-O` | all identical | within ±0.4% |
| regex / json / jq / decimal | +0.02 / -0.17 / -0.19 / +0.16% | -0.67 / +0.23 / +0.07 / +0.12% |
| cmark | -1.86% | **-3.88%** (interleaved: -3.78%, branch misses -5.1%) |
| json / jq, interleaved | -0.17 / -0.19% | -0.88 / -0.68%, branch misses level |
| compile.py: hello / nine programs / self-build | | 13.4 to 14.3 / 131.8 to 131.1 / 470.6 to 471.2 ms |
| grep, sort, tail, eza (interleaved) | all identical | within ±0.3% (tail's 0.3 ms ±3%, eza -l -1.25%) |
| HTTP server, 1/10/100 clients, 2 alternated rounds | | level (107.6k/177.1k/173.0k against 107.6k/177.5k/172.8k req/s) |
| perfsuite compile suite / run suite | -0.20 / +0.00% | -0.66 / +0.03% |
| lexdb point selects (5 modes, fixed seed) | -0.02% to -0.08% | |
| TPC-H, server instructions per query | **-0.81%** geomean (q6 -3.82, q7 -2.42, q22 -1.93, q12 -1.73, q1 -1.21, q19 -1.16, q21 -1.08; worst q18 +0.04%) | |

TPC-H results are identical and all 22 are `ok`. `gate.sh quick` passes, and the lexdb
suite passes 271/271.

### The first version's TPC-H run, kept for the record

TPC-H (SF1, lexdb only; lexdb at main `52fe2606` built `-O` by main's compiler and by
the first version):

- **Order:** ABBA, one run at a time, each under the exclusive bench lock
  (`~/tpch-w/opt/ab.sh`).
- **Results:** identical in all four runs.
- **Instructions:** geomean -0.68%.
- **Time:** CPU total -1.86%.

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

1. Done: TPC-H and the PERFORMANCE.md set (section 1); merged into main, with the revision.
   Lesson: perfsuite's run suite has no cmark, json or jq. Check a code-shape change against
   PERFORMANCE.md's applications interleaved, with branch misses, before merging.
2. A census of drop-then-alloc pairs of one size class (runtime counters), to bound
   Perceus-style reuse.
3. Scalar replacement of small records (review 1, 1.2) remains the largest structural
   lever. mid-ir.md's M1 found frame aggregates dominate the spills; it is a project, not
   an experiment.
