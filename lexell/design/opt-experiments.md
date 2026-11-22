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

## 5. The allocator's size class (runtime, `native/rt.c`)

Allocation was 4-11% of instructions:

| program | share |
|---|---:|
| the compiler | 4.8% |
| lexdb point selects | 4.1% |
| cmark | 6.4% |
| json | 8.9% |
| jq | 11.4% |

That came to 25-37 instructions per `malloc`. The fast path itself is a free-list pop
(5 instructions). The rest was `class_of`, a linear scan of the 32 size classes above
120 bytes:

- gcc vectorized the scan with AVX2, ending in `vzeroupper`.
- It also hoisted the vector set-up above the test for small sizes, so every allocation
  paid for it.

The fix:

- **Small sizes** (8-120 bytes) keep their arithmetic, `(n + 7) >> 4`.
- **Larger sizes** take one load from a 4 KB table. Every class size is 16k + 8, so the
  sizes in (16(k-1) + 8, 16k + 8] share the smallest class of at least 16k + 8: entry k.
  The classes are unchanged.

Two lessons came out of it:

- **A table load for the small sizes made bench alloc 29% slower**, at some heap addresses
  only. It was deterministic with ASLR off: 1,760M against 1,360M cycles, and 1,245-1,762M
  with ASLR on. The blocks' stores and the load collided. So the small sizes keep their
  arithmetic, and that version runs at 1,202-1,341M.
- **Filling the table one entry at a time cost about 40K instructions at start** (`tail -n 5`
  +14%). It is now filled a class at a time: +1.1K.

Results against main's compiler (`e3`). Every timed step ran under the exclusive bench lock,
interleaved where it says so:

| measure | instructions | cycles |
|---|---:|---:|
| lexdb point select / sel1 / gs / insert / update (fixed seed) | -2.41 / -2.92 / -2.90 / -2.24 / -2.34% | battery round -1% to -19%, later rounds ±9% noise from an unlocked suite on the machine |
| TPC-H, server instructions per query | **-1.03%** geomean, all 22 down (q2 -2.67, q20 -2.09, q13 -1.55, q9 -1.45, q22 -1.44, q7 -1.42; least q1 -0.17%) | results identical, all `ok` |
| perfsuite run suite / compile suite | -1.34 / -0.98% | -1.35 / -0.02% |
| bench alloc / lists / trees / strings / maps (interleaved, 5 rounds) | -8.33 / -3.85 / -3.34 / -3.27 / -0.70% | -4.8 / -3.5 / -6.1 / -1.3 / -0.5% (medians) |
| cmark / jq / json / the compiler compiling itself (interleaved) | -0.81 / -1.44 / -1.31 / -0.72% | -0.90 / +0.60 / +0.22 / -0.04% (medians) |
| regex, decimal | -0.08 / -0.48% | +0.78 / -0.38% |
| fib, loop, array, sieve, tokens | level | level |
| grep, sort, eza `-T`, eza `-l` | -0.00 to -1.58% | -2.1 to -0.1% |
| HTTP server, 1/10/100 clients, 2 alternated rounds | | level |
| startup (`tail` on two lines) | +0.4% (268K to 269K) | |

`gate.sh quick` passes, and the lexdb suite passes 271/271. This passes "Judging a pass" on
its first rule: the run suite gains at least 1%, and the compile suite costs nothing.

## 6. Frame set-up and tear-down (the ceiling for shrink-wrapping)

**Method.** Instruction samples (`perf record -e instructions:u`) landing on the program
functions' pushes of callee-saved registers, `mov rbp,rsp`, the entry `sub rsp`, `leave` and
`ret`. The epilogue's restores are loads and are not counted, so this is a lower bound.

| program | frame share | in leaf functions | elsewhere |
|---|---:|---:|---:|
| the compiler (built without `-O`) | 6.10% | 1.46% | 4.64% |
| cmark | 4.38% | 1.04% | 3.34% |
| jq | 4.59% | 1.64% | 2.96% |
| lexdb point select | 0.99% | 0.13% | 0.86% |

A leaf function here makes no call but the traps. The hottest one is jq's
`json.Decoder.skipSpace`, at 1.25% of samples:

- It is a leaf, yet keeps `d` in `rbx` (a callee-saved register it must save).
- It copies the string header to two frame slots and reads them back.
- So it needs a full frame; about 8 of its roughly 25 instructions a call are frame work.

**Reading.** Shrink-wrapping proper only helps the non-leaf share on paths that make no
call. In leaf functions the levers are caller-saved registers and fewer frame slots: the
second is item 3's scalar replacement. The gain is at most 1-2% of instructions for
cmark, jq and the compiler, and almost nothing for lexdb.

## 7. `str` as `{p, len, cap}`: a stall on store-to-load forwarding

**Found in** jq's `json.canonicalLiteral`, at 5.7% of samples. The hot instructions were
an 8-byte store into a string's slot, then a 4-byte load of `len` from the upper half of
that same word (`mov %r10,-0x58(%rbp)`; `mov -0x54(%rbp),%eax`).

**Measured on this CPU (Zen 4):** that load cannot take its value from the store. A
store-then-load chain runs 8 cycles at offset 4 and 1 cycle at offset 0
(`scratchpad/stlf.c`). Strings are copied 8 bytes at a time, so every read of `len`
soon after a copy paid the stall: `len` was at offset 12 in `{p, cap, len}`.

**The change.** The layout is now `{p, len, cap}`, putting `len` at offset 8, the start
of a word. `cap` is read where `len` is too (appends), so those paths stall once, as before.
What changed:

- `rt.h` and `native/lxlrt.h`;
- the 16 positional initializers in `rt.c` and `rt.h`, made designated;
- `emit.lxl`'s two literal initializers;
- x64gen's view builder, index checks and inline `rt_str_eq`;
- `loops.lxl`'s three matches of `len` as "member 12, u32" (two of them made the first
  build lose the string-header hoisting, so tokens ran +7% instructions until they were
  fixed).

Results against main (`a3`); every timed step ran under the exclusive bench lock:

| measure | instructions | cycles |
|---|---:|---:|
| interleaved, 5 rounds: jq / json / maps / the compiler / cmark | -0.23 / -0.19 / -0.34 / -0.14 / -0.20% | -4.8 / -3.6 / -2.4 / -1.1 / -0.7% (medians) |
| regex / json / jq / cmark / decimal (apps.py) | -0.04 / -0.19 / -0.23 / -0.21 / -0.12% | -6.4 / -3.3 / -4.1 / -1.4 / -1.0% |
| grep `-o -w`, eza `-T`, eza `-l` | -0.28 / -0.35 / -0.85% | -3.4 / -2.6 / -2.6% |
| TPC-H, server instructions per query | -0.49% geomean (q8 -1.36, q15 -1.10; worst q1 +0.03%) | results identical, all `ok` |
| perfsuite compile suite / run suite | -0.21 / -0.19% | -0.66 / -0.82% |
| lexdb point selects (5 modes) | -0.09% to -0.42% | within noise |
| compile.py self-build | | 468 to 464 ms |
| HTTP server, 2 alternated rounds | | level |
| bench lists | identical | +2-2.7% |

The lists rise is placement: the same instructions and data-cache misses, branch misses
175K to 348K over 3G instructions. No string is involved; the runtime's string functions
changed size and everything after them moved.

**Follow-up:** the same stall hits any value record whose 4-byte (or smaller) field sits at
a non-zero offset within an 8-byte word, read soon after an 8-byte copy. `str` was the
frequent case. A census of narrow reads at offset 4 within a word of frame slots right
after copies would size the rest.

## 8. Forwarding stalls by counter, and `Decimal` as `{v: i128, exp, dscale}`

**The counter.** Zen 4's `ls_bad_status2.stli_other` counts loads that cannot complete
because an older store cannot forward to them. A census on main (f51abd4a), per million
user instructions: loop, array and sieve near 0; fib 2,900 (pushes reloaded through rbp);
lists 610; the compiler 10,400; jq, json, regex 6,400-6,900; strings 7,300; Decimal
13,000-53,000. The event counts retries, so its totals overstate the cycles lost. Its
samples skid a few instructions, and IBS on this CPU has no forwarding-failure bit.

A microbenchmark (two loads and stores in a dependent chain, ticks per round trip) gives
the rule: a load forwards from one older store that contains it at the same start (0.8; a
16-byte SSE store also at +8, 8.5); a load wider than the store (8-byte store, 16-byte load:
18.5), or spanning stores (two 8-byte stores, one 16-byte load: 18.5; two 4-byte stores,
one 8-byte load: 14.6) does not. copyMem's 8-byte copies and the literal stores of a lone
narrow field as its whole word (native.md) already follow it; no other frame-slot pair in
one function breaks it. Decimal's stalls are its by-value copies across calls
(record-abi.md); `strings`' are in the runtime's string building (not attributed yet).

**`Decimal`.** It was `{coef: u128, exp: int, dscale: int, neg: bool}`: 33 bytes used,
48 with the u128's 16-byte alignment. A coefficient is below 10^38 < 2^127, so the sign fits
in a two's-complement i128: `{v: i128, exp: int, dscale: int}`, 32 bytes with no padding.
The magnitude algorithms are unchanged (`mag(v)`, `signed(m, neg)`); add at equal
exponents adds the signed values when the signs differ (same signs: the u128 magnitudes,
whose sum may pass 2^127), and compare at equal exponents, with a zero or with different
signs is one signed compare. toBin, hash and every output are unchanged.

It needed two native backend changes, because main's Decimal used only u128 arithmetic:

- i128 arithmetic was always a runtime call. Now inline: wrapping + - * (the bits of u128's),
  checked + and - (the overflow flag of the high words' ADC or SBB, not the carry), and
  checked negation (0 - a; i128's minimum traps as the runtime does).
- a 128-bit compare with a constant whose low word is 0 is the high words' CMP: `v < 0` and
  `v >= 0` are a sign test (the low words' CMP leaves no borrow, so SBB's flags are CMP's).

Also measured, dropped: the sign in bit 127 of a u128 (`c & MAG` for the magnitude): 10%
more instructions and 5% more cycles over dbench, because the backend rebuilds the
128-bit mask at each use.

| measure | new/old instructions | cycles |
|---|---:|---:|
| dbench, 40 cases (geomean) | +0.9% | -1.5% |
| add at equal exponents (M2, M4) | -7 to -12% | -6 to -14% |
| compare, equal exponents (M10:same) | -20% | -25% |
| compare, different exponents (M1) | +10 to +16% | +5 to +18% |
| quantize (M6) | +8% | +2 to +5% |
| TPC-H server instructions per query | -1.56% geomean, all 22 down (q4 -3.5, q22 -3.3) | results identical |
| json (apps) | 0.00% | -2.0% |
| lexdb point selects | -0.32 to -0.48% | within noise (±15% between rounds) |
| perfsuite compile / run suite | +0.01% / 0.00% | +0.10% / +0.02% |
| lexdb binary | 13,746,808 to 13,599,352 bytes (-1.1%) | |

The remaining cost is the magnitude: a branch, a negation and the checked i128-to-u128
conversion (there is no unchecked one: SPEC 7.2), where the bool was one byte compare.

## 9. Integer to text written straight into the string (runtime)

`rt_i128_to_str` and `rt_u128_to_str` wrote the digits backwards into a stack buffer one byte at
a time and `rt_str_of` then copied it with memcpy, whose 8-byte loads of a 9- to 20-digit number
span byte stores just made (the forwarding rule of section 8). Below 2^64 the digit count now
comes first (the bit length times 1233/4096, then one compare with a power of ten: no loop, no
division), and the digits go straight into the new string. Same in rt.h for the C backend.

| measure | new/old instructions | cycles |
|---|---:|---:|
| a loop of `n.toStr()` and `"row " + i.toStr() + ": " + ...` | -5.6% | -9.7% |
| bench strings | -2.2% | -6.5 to -7.9% |
| perfsuite compile / run suite | -0.02% / -0.23% | +0.27% / -0.49% |
| grep -n omega (560K line numbers) | -0.78% | +2.3% (8 alternated rounds) |
| apps (regex, json, jq, cmark, decimal) | 0.00% (decimal -0.4%) | level |
| TPC-H server instructions, point selects | level | level (point selects ±4% between rounds) |
| HTTP server, 2 alternated rounds | | level to +2% at 100 clients |

grep -n's rise has the same L1 misses, branch misses and stall counts as before; its runtime
functions (rt_find1, rt_str_find) moved, so it reads as placement. The larger fix for chains
(`"word" + i.toStr() + "-" + ...`) is a single concatenation that sizes the result and formats
the integers in place, with no intermediate strings: not built.

## 10. Next, in order

1. Done: TPC-H and the PERFORMANCE.md set (section 1); merged into main, with the revision.
   Lesson: perfsuite's run suite has no cmark, json or jq. Check a code-shape change against
   PERFORMANCE.md's applications interleaved, with branch misses, before merging.
2. A census of drop-then-alloc pairs of one size class (runtime counters), to bound
   Perceus-style reuse.
3. Scalar replacement of small records (review 1, 1.2) remains the largest structural
   lever. mid-ir.md's M1 found frame aggregates dominate the spills; it is a project, not
   an experiment.
