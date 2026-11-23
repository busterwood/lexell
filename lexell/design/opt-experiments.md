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

**Also built, dropped: epilogues that pop.** fib's stall hits are pushes in the prologue
reloaded through rbp in the epilogue. Restoring with `lea -8k(%rbp), %rsp; pop ...; pop rbp`
(as gcc does) cut fib's count by 58% at identical cycles (3,986M), with 4.5% more
instructions; trees took 6% more cycles. Those stalls were hidden behind other work: the
counter locates conflicts, and only cycles say whether they cost anything.

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
the integers in place, with no intermediate strings: section 10 builds the first half.

## 10. A chain of `+` on `str` built once (check.lxl `xChain`, as built)

`a + b + c` was `rt_str_concat(rt_str_concat(a, b), c)`: each intermediate string allocated,
both sides copied in, read straight back by the next `+` (wide loads of bytes just stored:
section 8) and freed. Now a left-nested chain of three or more `+` whose first operand is a
`str` is one call, `rt_str_concat3` to `rt_str_concat8` (`native/rt.c` and `rt.h`), that sums
the lengths, allocates once and copies each part once. As the nested form, a lone non-empty
part is duplicated (a static one shared) and a result of 4 GiB traps.

**Semantics.** The parts are read later than the nested form reads them, so a part stays in
the group only if nothing after it can change it: a temporary, a string literal, or a field
chain of a local or parameter (no run-time check in its C) whose name no later operand has,
except later operands that are themselves such a read (`s + "," + s`). Anything else (a
global, a borrow a call returns, `xs[i]`, a local named inside a later call) makes the group
join before the next operand, where the nested form would have joined it, so evaluation
order, the hold on the left operand while the second runs, trap order and drops are the
nested form's: `s + "" + grab(mut &s)` still compiles and reads the old `s`. Chains longer
than 8 are joined 8 at a time. Non-`str` chains (int, float, operator methods) go through
the nested form operator by operator. `s += a + b + c` builds `a + b + c` once, then appends.

**Chain lengths** (stage-2 C of the compiler / lexdb, parts per chain): 3: 140 / 486,
4: 61 / 112, 5-8: 140 / 394, 9 or more: 36 / 157.

**Arity choice.** Eight register-and-stack functions against one `rt_str_concatn(parts, n)` over
a stack array (`declArr`) for 4 or more parts: the array made the compiler's code 10.5 KB and
lexdb's 15 KB larger, so the fixed arities stayed. Capping groups at 4 parts instead of 8:
lexdb 25 KB larger.

Matched stage-2 compilers without `-O` (main `cbc38895` against this branch); every timed step
under the exclusive bench lock, pinned:

| measure | new/old instructions | cycles |
|---|---:|---:|
| bench strings (-O), 5 interleaved rounds | 4,293M to 3,441M, -19.8% | 934M to 709M, -24.1% (median) |
| a loop of `"word" + i.toStr() + "-" + r.toStr()` and longer chains (-O) | 8,331M to 5,666M, -32.0% | 1,697M to 1,177M, -30.7% |
| perfsuite compile suite / run suite (`--frozen 5f30415d`) | -0.62% / -1.48% | -0.66% / -1.78% |
| perfsuite: compiler `--emit-c`, eza -T | -1.63%, -1.89% | -1.18%, -0.95% |
| apps: regex / json / jq / cmark / decimal (2 rounds) | 0.00 / 0.00 / 0.00 / -0.01 / -1.75% | +0.03 / -0.4 / +0.2 / **+1.2** / -1.6% |
| lexdb point select / insert / update (pt.lxl, instructions per statement) | -0.37 / -0.73 / -0.24% | noise (±20% between rounds) |
| HTTP server, 1 / 10 / 100 clients, 2 alternated rounds | | level (±0.5%); idle RSS level |
| code size: compiler / lexdb / httpd | -0.14% / -1.07% / -1.8% | |
| seed/lxlc.c | 6,520,404 to 6,517,294 bytes | |

cmark's +1.2% is placement: instructions -0.01%, forwarding stalls level, branch misses
2.04M to 2.20M; its only changed hot function is `Doc.html` (128 bytes smaller), and the
three new runtime functions move everything after the string functions by 1,152 bytes.

**Not built: integers formatted in place.** A part `x.toStr()` of an integer still makes its
own string. The ceiling, bench strings with the integers' text made beforehand: 3,441M to
2,507M instructions (-27%), of which the digits themselves stay; the applications above
build few strings that way. It would need a marker part (the integer in the pointer word, a
`cap` no string has) or per-shape runtime functions, and a type test of the receiver before
it is checked.

## 11. Followed up, nothing kept (2026-11-22)

- **Code alignment.** Already done and measured (microarch.md 3.1-3.3): generated functions at
  64 bytes, loop tops at 16 with the 64-byte inner-loop rule, the runtime at
  `-falign-functions=64 -falign-loops=32`. Today's "placement" swings (lists, grep -n, cmark,
  point selects) come with equal instructions and misses after code moved, which alignment does
  not address (predictor and cache-set aliasing between moved functions, presumably).
- **No inlining of never-returning functions.** Skipping `u.stops` in `inlinable`: the -O
  compiler the same size, lexdb -O 37 KB larger (+0.27%). The inlined stop bodies were paying
  for themselves (presumably by showing that the code after the call is unreachable). Dropped.
- **Sign facts for i128 magnitudes.** In `if v < 0 { u128(0 -% v) }` the check of the
  conversion cannot go: for i128's minimum `0 -% v` is still negative, and only the library
  knows a coefficient never is. What could go is the else branch's test and jump, 2 of about 8
  instructions per magnitude: not worth a rule.
- **Load reuse.** cse.lxl already reuses loads and checked element addresses across statements
  of a straight-line run. What it leaves out by design: reuse within one statement (the native
  backend's evaluation order is its own) and across writes or program calls. Not attempted.
## 12. bench tokens against Rust: four small changes (as built)

`tokens` was the one microbenchmark behind Rust (1.24) and 1.22 times its C build's cycles. A
profile against the C build found the gap in the bucket loop of `main`, not in the byte scan
(the native identifier loop is 9 instructions a byte, gcc's 11):

- **`rt_as_slice` inline** (x64gen `genAsSlice`, quiet): `for x in a[i]` called the runtime for
  `{a.data, a.len}` and passed the result through the frame.
- **An aggregate argument that is a place of more than a local is copied into a local when the
  inlined body loops** (opt.lxl, `W_LOOPS`). `hash(t.text)` was bound as the expression
  `t.text`, which loops.lxl cannot follow: the hash loop kept a bounds check a byte. With
  `let tx = t.text` or `LXL_INLINE=0` the check was proved, so the binding was the cause.
- **Masked loop-carried locals** (loops.lxl `maskWrites`): a local whose every write in the
  loop is `x & c` (c >= 0) and that is in [0, h] at the entry stays in [0, max(c, h)], so
  `h = (h * 33 + b) & 0xFFFFFF` proves its multiply. With **a local's own kind bounding its
  range** (a byte is 0 to 255) and **a widening conversion having its operand's value**
  (`int(b)` is `rt_cvs_int((i128)b)` in the IR), the add is proved too: the hash loop has no
  check left.
- **`%` by a power of two** (x64gen `inlineDiv`): after the zero check, `lea rdx, [rcx-1]; test
  rdx, rcx`, and with a dividend >= 0 the remainder is `x & (n - 1)`; else the divide as
  before. `hash % len(table)` was an `idiv` per lookup; gcc removed it only by proving the
  table's length is 1024. The test costs a predictable branch where the divisor is not a power
  of two. tests/run/native_rem_pow2.lxl checks every kind, sign and extreme against the C
  build.

| measure | new/old instructions | cycles |
|---|---:|---:|
| bench tokens (-O), 5 interleaved rounds | -3.96% | -3.77% |
| perfsuite compile / run suite | -0.23% / +0.01% | -0.16% / -0.58% |
| apps (regex, json, jq, cmark, decimal) | 0.00% | level |
| TPC-H server instructions per query | -0.12% geomean (all within ±0.21%) | |
| point selects select / insert / update | -0.36 / -0.11 / -0.22% | noise |
| HTTP server, 2 alternated rounds | | level |
| lexdb -O binary | -20 KB (-0.15%) | |

tokens is now 1.16 times its C build's cycles. What remains: the bucket loop's `str` compare
(`rt_str_eq` and memcmp, 7% of the instructions) and frame traffic.

## 13. `str ==` without memcmp for up to 16 bytes (runtime)

`rt_str_eq` (the native code compares the lengths inline first) called memcmp for every equal
length; in bench tokens' bucket loop that was 7% of the instructions. Now up to 16 bytes are two
overlapping words of the widest size that fits (8 or 4 bytes), 1 to 3 bytes the first, middle
and last byte, and longer strings memcmp; native/rt.c and rt.h alike.
tests/run/s04_str_eq_lengths.lxl checks every length 0 to 40 with a difference at each position.

| measure | new/old instructions | cycles |
|---|---:|---:|
| bench tokens (-O), 5 interleaved rounds | -4.8% | -3.9% |
| perfsuite compile / run suite | -0.64% / -0.39% | -0.54% / +0.04% |
| perfsuite tokens / maps / grep -cE | -3.4 / -1.0 / -1.2% | -3.5 / 0.0 / -1.0% |
| perfsuite strings / grep -n | 0.00 / -0.6% | +2.1 / +3.3% (placement: the runtime moved) |
| lexdb point selects select / insert / update | -0.96 / -0.83 / -0.83% | level |
| TPC-H server instructions per query | -0.22% geomean | |
| apps, HTTP | level | level |

## 14. Range tests, bfold before loops, multiplies as shifts (as built)

A profile of bench tokens against Rust after section 13: Lexell 1.09 times Rust's instructions and
about 1.18 times its cycles. Three code-shape gaps in the byte loops, each general:

- **A range test as one compare** (x64gen `branchRange`). In a branch, `x >= lo && x <= hi`
  (either compare strict, either order, x a load that cannot fail, constants of 32 bits) is
  `x - lo` against `hi - lo` unsigned, and `x < lo || x > hi` the jump the other way. Two ranges
  of one x a bit m apart, the first without m and the second with it in every value
  (`'A'..'Z' || 'a'..'z'`, m 0x20), are one compare of `x | m`. `isLetter(c) || isDigit(c)` was
  five compare-and-branch pairs a byte; it is two compares and the `== '_'`.
- **bfold before loops** (main.lxl). loops.lxl saw `while i < n && p(s[i])` as `bool b = i < n;
  if (b) { S; b = V; } if (!b) break;`, which states no fact, so the `i += 1` in the body kept its
  overflow check. After bfold it is `if (!(i < n)) break; S; if (!V) break;`. Proofs: compiler
  +22 bounds and +28 overflow checks, lexdb +55 and +183; lexdb -8 KB of code.
- **Wrapping multiplies by 2^j, 2^j + 1, 2^j - 1** (x64gen `leaMul`) as a move, a shift and an add
  or a subtract: two cycles on the value's path where imul takes three (`h * 33` in a hash loop).
  More instructions (three for one), fewer cycles.

tests/run/native_range_fold.lxl (every kind, both orders, strict and not, the merged ranges, the
extremes) and native_mul_shift.lxl (every constant form, kind and extreme) check them against the
C build.

| measure | new/old instructions | cycles |
|---|---:|---:|
| bench tokens (-O), 5 interleaved rounds | +3.0% | -5.2% |
| perfsuite compile / run suite, two runs | -0.06% / +0.05% | +0.82, -0.22% / -0.41, -0.31% |
| perfsuite tokens / strings / eza -T | +1.95 / 0.00 / -0.94% | -3.2, -2.8 / -1.0, -1.7 / -0.8, -1.0% |
| apps json / jq / cmark | -1.26 / -1.92 / -0.62% | -1.31 / -2.11 / -1.99% |
| apps regex / decimal | 0.00 / -0.19% | level |
| TPC-H server instructions per query | +0.02% geomean (-0.09% to +0.38%) | |
| point selects | within 0.01% | level |
| HTTP server, 2 alternated rounds | | level (noise) |

The first perfsuite run's compile suite (+0.82% cycles at -0.06% instructions) was placement: the
second run had -0.22%.

What remains in tokens is frame traffic (the token list's header and the slice staged through the
frame), scalar replacement's ground.

## 15. Decimal mul, div and cmp fast paths (library, as built)

Against Java BigDecimal and .NET System.Decimal, mul (6 by 6 digits), div (12 by 6, scale 2) and
cmp (19 digits) were behind. The profile showed instructions, not stalls (4.7 per cycle): 383 a
mul, 574 a div, 68 a cmp. Each did the general work for the common small case:

- **mul** went through U256, makeDecCore and digits for every product. Now, with both coefficients
  within 63 bits (18 digits or fewer), the signed i128 product is the result coefficient with its
  sign (below 2^126 < 10^38). Trailing zeros go by the inverse of 5 in 64 bits (stripTens), and the
  digit count only where the display-scale cap can bind. mulExact has the same path written out:
  as a shared function (an out parameter, or a returned Decimal with 0 as "fall back") mul was a
  third slower.
- **div**'s 64-bit path now rounds (HALF_EVEN and HALF_AWAY inline, the other modes through
  roundIncrement), strips and builds the result itself. Its entry test no longer divides
  M64 / 10^t in 128 bits (a runtime call).
- **cmp** is the equal-exponent test alone, under the inliner's 25 nodes, with the rest in
  cmpApart. Reading both coefficients into locals first was a fifth faster than comparing the
  members twice.

lib/tests/run/decimal_fast_edges.lxl checks 36 by 36 values (around 2^63, trailing zeros, the
exponent limits, the scale cap, every rounding mode at five scales) against the old library's
output, on both backends.

| measure | old | new | |
|---|---:|---:|---:|
| decbench mul, 6 by 6 | 17.0 ns | 8.9 ns | -48% |
| decbench div, 12 by 6 | 23.1 ns | 14.1 ns | -39% |
| decbench cmp | 2.72 ns | 2.17 ns | -20% |
| decbench-big mul, 19 digits | 18.8 ns | 13.4 ns | -29% |
| add, parse, format | | | level |
| apps decimal | | | -1.1% cycles |
| TPC-H server instructions per query | | | +0.03% |
| point selects | | | level |

TPC-H does not move: lexdb computes numerics in batches as scaled integers (lexdb_vec.arith) and
uses Decimal only on the row path and where a batch result does not fit.

What remains of mul and cmp is the call and the 32-byte copies in and out: the inliner's 25-node
limit keeps mul out of line. A per-function inline mark would let it in.

## 16. Next, in order

1. Done: TPC-H and the PERFORMANCE.md set (section 1); merged into main, with the revision.
   Lesson: perfsuite's run suite has no cmark, json or jq. Check a code-shape change against
   PERFORMANCE.md's applications interleaved, with branch misses, before merging.
2. A census of drop-then-alloc pairs of one size class (runtime counters), to bound
   Perceus-style reuse.
3. Scalar replacement of small records (review 1, 1.2) remains the largest structural
   lever. mid-ir.md's M1 found frame aggregates dominate the spills; it is a project, not
   an experiment.

## 17. Against Java 21: string chains, drop loops (as built)

**The comparison.** Ten ports of the microbenchmarks to Java (OpenJDK 21.0.13, default tiered
C1/C2, checked arithmetic with `addExact` and `multiplyExact`), checksums equal, on this machine
(`~/Work/bench-results/2026-11-23-java`: `Bench.java`, `run.sh`, two runs that agree). Lexell is
native `-O`, best of 5 wall; Java is the best of 5 in-process runs after one warm-up.

| program | Lexell | Java warm | |
|---|---:|---:|---|
| fib | 1,063 ms | 793 ms | Java 1.34x |
| loop | 534 ms | 677 ms | Lexell 1.27x |
| array | 432 ms | 351 ms | Java 1.23x |
| alloc | 322 ms | 36 ms | Java 9x: escape analysis removes the allocation |
| lists | 224 ms | 73 ms | Java 3.1x |
| strings | 186 ms | 56 ms | Java 3.3x |
| trees | 156 ms | 51 ms | Java 3.1x |
| tokens | 135 ms | 206 ms | Lexell 1.5x |
| sieve | 380 ms | 660 ms | Lexell 1.7x |
| maps | 406 ms | 305 ms | Java 1.33x |

An outside study on another machine found the same causes, with two corrections from the
profiles here: `strings` already builds a chain with one allocation (section 10), and its cost
was elsewhere; and `maps` spends 36% in SipHash here, not 7%.

**What was built** (one commit):

- **Integers written into a chain** (check.lxl `xChain` and `intPart`; section 10's "not
  built"). A part `x.toStr()` or `intToStr(x)` of an `int` (std's: no program function of that
  name) is evaluated into an int local where the string was, and passed as
  `(lxl_str){.p = (char*)x, .len = 2, .cap = 1}`: no string has a cap below its length (an owned
  one has cap >= len, a static one cap 0). `rt_str_concat3` to `8`, and `rt_str_concat` for a
  chain joined early to two parts, count its digits and write them straight into the result.
  The part's string, its allocation and its free are gone.
- **The concat functions** (native/rt.c) read each part's `p` and `len`, never the part as one
  16-byte value: a part passed on the stack is two 8-byte stores in the caller, and gcc's 16-byte
  copy of it could not be forwarded (31M stall events for 5M calls in `strings`). Parts of up to
  16 bytes are copied inline (two overlapping 8- or 4-byte moves, or up to 3 bytes); int parts and
  longer parts go to one out-of-line function. `rt_int_to_str` formats 64-bit values without the
  u128 path.
- **Drop actions that loop** (emit.lxl `selfLoop`). An action that pushes its own action (a
  list's next node, a tree's children) holds each such push back and loops on the last one: that
  action is the next to run when this one returns (the stack is LIFO), so the order of every drop
  and free is the same. A list's drop is a loop with no pushes; a tree's pushes one child a node
  instead of two.
- **Packed literal words** (x64gen `fillEntries`). An 8-byte word of a literal made of two or more
  small integer constants is one 8-byte store, as a lone narrow field already was: the int part's
  `len` and `cap` are read as one word.
- **The consuming `for`'s reverse** (check.lxl `forConsume`) uses two indices, with no `len / 2`
  per turn.

**A regression found and fixed on the way.** The concat functions became more callers of
`rt_str_new`, and gcc then stopped inlining it into `rt_str_of` (and inlined `rt_str_of` into
`rt_str_dup` instead): every `rt_str_dup` paid a call more, +1.0 to 1.2% instructions in json, jq
and cmark. `rt_str_mk` is now always inline in `rt_str_new` and `rt_str_of`.

| measure (main 6c7d3bf5 against this) | instructions | cycles |
|---|---:|---:|
| bench strings / lists / trees (perfsuite, best of 5) | -36.4 / -18.7 / -4.6% | -37.8 / -18.5 / -10.3% |
| bench maps / the other six | -1.7% / level | -1.4% / level |
| perfsuite run suite / compile suite (`--frozen 5f30415d`) | -4.54 / -0.41% | -4.94 / -0.14% |
| apps regex / json / jq / cmark / decimal (5 interleaved rounds) | -0.01 / 0.00 / -0.01 / -0.20 / -0.37% | -0.2 / +0.5 / +0.1 / 0.0 / -0.7% |
| TPC-H SF1, server instructions per query (22) | -0.03% geomean (-0.30 to +0.09%) | |
| lexdb point select (icount6, 4 alternated rounds) | -0.48% (173,438 to 172,595) | +1.9% (97,762 to 99,572) |
| code size: lexdb -O / the compiler built by each | -16 KB / -1.7 KB of program code | runtime +6.5 KB (concat3 to 8) |

The point selects' cycles move against their instructions: L1i misses per statement ranged
296-521 for this build against 281-385 for main's, and a recording of them by function moves
by hundreds both ways between unrelated functions (`Wire.fill` 427 to 21, `gl_act` 491 to 675):
placement, as in sections 3 and 11. Branch misses are +10 a statement (+2.5%), spread the same way,
with `malloc` the largest (+27%: the sequence of sizes changed with fewer temporary strings).

Tests: tests/run/str_chain_int_parts, str_chain_int_shadow, for_consume_order, drop_chain_loop,
native_packed_literal, their expectations from main's compiler.

**Next** (being built): one level of recursive inlining (fib, trees, lists; C2's
MaxRecursiveInlineLevel = 1), and boxed records that never escape kept in a local (alloc).

## 18. Recursion inlined once, records that never escape (as built)

The second half of section 17's plan, both in opt.lxl.

- **One level of recursion** (`visit`, the `selfOnce` pass; C2's `MaxRecursiveInlineLevel = 1`).
  After f is optimized and its form taken, a function that calls itself (the `W_CALLEES` walk
  notes it) and whose form is at most `RECUR_LIMIT` (60) nodes is inlined into its own calls
  once; the copy's calls of f stay calls. fib's real calls are about halved; a tree's walk and
  build do two levels a call, a list's sum two nodes. The limit is above the usual 25 because the
  growth is one copy, as C2 lets a recursive call in from its hot band (`lists.sum` is about 40
  nodes, `trees.build` and `check` up to 60).
  The form shares f's statements, which the pass changes, and f's locals, which the calls'
  arguments name: inlining f into itself with f's own locals bound the caller's `d` in `d - 1`
  (bench trees crashed). So the pass inlines `deep`'s copy of the form, every local renamed, with
  its parameters in `fpList` (`par`, `npar` in `expand` and `copyArg`); callers of f later inline
  the same copy.
- **Boxed records that never escape** (`unbox`, after inlining and before the form is taken).
  `T* p = (T*)rt_alloc(sizeof T)` whose pointer is only copied into locals declared to it,
  dereferenced and freed (`rt_free(p)`: the drop of a record with no field to drop, once the glue
  is inlined) becomes a local `T` of f: the dereferences name it, the allocation and the frees go.
  Locals that are assigned or whose address is taken disqualify their group; anything else that
  names the pointer (a call argument, a store, a comparison, `Some(p)`) is an escape. A
  constructor's literal counts once inlined (`allocs[g]` passes to the caller in `expand`). This
  is the JVM's escape analysis on the alloc benchmark, where Java ran 9 times faster.

**Compile cost.** The first version sized `unbox`'s facts to every local of the program for each
function, and found recursion and allocation with two more walks of each body: compiling the
compiler +50% instructions. Now the facts are kept for the locals a function names (`ubSeen`,
reset after it), and the existing `W_CALLEES` walk sets `recur` and `allocs`: level.

| measure (section 17's build against this) | instructions | cycles |
|---|---:|---:|
| bench fib / alloc / lists / trees (perfsuite, best of 5) | -11.5 / -79.1 / -2.1 / -1.1% | -34.4 / -86.7 / -6.4 / -1.8% |
| the other bench programs, grep, sort, wc, eza | level | level (sort +1.5% at equal instructions) |
| perfsuite run suite / compile suite | -10.19 / -0.23% | -14.48 / -0.20% |
| apps regex / json / jq / cmark / decimal (5 interleaved rounds) | 0.00% each | -0.1 / -0.2 / +0.1 / +0.3 / -0.1% |
| TPC-H SF1, server instructions per query (22) | -0.05% geomean | |
| lexdb point select (icount6, 2 alternated rounds) | +10 a statement (+0.006%) | -1.6% |
| code size: lexdb -O | +8 KB | |

Tests: tests/run/inline_recursive_once (branching recursion, a borrow through a match, a `mut &`
accumulator, records by value, strings, a 100,000-node list), unbox_local_record (unboxed:
loops, copies, string fields, an inlined constructor; kept: passed, returned, stored, moved into
an Option, a drop method). The quick gate, an `-O` self-build fixed point, the lexdb suite,
vrgen and loopgen (200 each) and the native red-team corpus pass.

## 19. Small allocations and frees inline (as built)

After sections 17 and 18, allocation and freeing were 46% of `lists`' instructions and 28% of
`trees`': about 56 instructions a node for a call to `rt_alloc` (which called `malloc`) and one
to `rt_free`, around fast paths of about 15. Java allocates with a bump of about ten inline
instructions and frees nothing per object; with its heap capped at 16 MB it is still about
twice as fast on `lists`, so its lead is the cost per object, not memory.

- **Generated code** (x64gen `memInline`): `rt_alloc(n)` of a constant n of at most 120 bytes
  pops the free list of n's class from the main heap (`rt_mheap.cur_free`, cur_live counted);
  `rt_free(p)` pushes p back when p is in the current chunk and its header is a bare class.
  Anything else (an empty list, another chunk, a large or tagged block) calls `rt_alloc_miss`
  or `rt_free` out of line, the registers they change saved (genStubs, as rt_arr_push's growth).
  Not in kernel functions or dynamically linked programs.
- **The runtime** (native/rt.c): `rt_mheap.inline_ok` is set once the heap is up, and cleared
  under LXL_CHECK (which counts every block) and when a par pool starts (malloc then goes
  through the pool's hooks); static asserts hold the offsets x64gen uses. `rt_alloc_miss` is
  rt_alloc with malloc's paths inline, for the inline code's misses only.
- **Tried and dropped:** the same fast path in the runtime's own `rt_alloc` (strings -3.7%), and
  malloc inlined into `rt_alloc`. Both changed how gcc compiled the allocator around them: json
  +0.5 to 1.6% instructions, jq +2% cycles at fewer instructions (`malloc` and `realloc` slower
  per call). `rt_alloc`, `malloc` and `realloc` are left exactly as they were.

| measure (section 18's build against this) | instructions | cycles |
|---|---:|---:|
| bench lists / trees (5 interleaved rounds) | -20.1 / -14.2% | -14.4 / -13.9% |
| bench strings / maps | level | level |
| apps regex / json / jq / cmark / decimal (5 interleaved rounds) | -0.05 / +0.33 / 0.00 / 0.00 / 0.00% | -0.3 / +0.1 / +0.4 / -0.9 / 0.0% |
| perfsuite compile suite | level | level |
| TPC-H SF1, server instructions per query (22) | 0.00% geomean | |
| lexdb point select (icount6, 2 alternated rounds) | level (172,317 to 172,330) | +1.4% (-0.8% in an earlier pair of rounds of the same generated code); branch misses +17 a statement |

json's +0.33% is the inline check before each miss: it allocates mostly fresh blocks. The point
selects' extra branch misses come with the allocation sites' own branches, which share no
predictor history as malloc's one branch did.

Test: tests/run/native_inline_alloc (lists across several chunks, three size classes, boxes
kept, and the same after a par.map has started its pool), with LXL_CHECK on and off.

## 20. Floating point: memory operands, doubles in their registers, addresses across stores (as built)

The five programs added to the microbenchmarks on 2026-11-23 found the generated code's weak
cases. `nbody` ran 8.78G instructions against Rust's 1.89G: every double went through xmm0 (a
load into xmm0, then into its register; an operand moved back into xmm0 and the other into
xmm1), and `bs[i].x`, `bs[i].y`, ... each multiplied i by the element size again.

- **Elements as SSE operands** (x64gen `fMem`): a double loaded through `place` whose address is
  integer code alone (pure, nothing of a float type below it) is the memory operand of
  addsd/subsd/mulsd/divsd after the left operand is in xmm0; the address uses only the integer
  registers.
- **Doubles in their destination** (`fT`, `genFT`): a double assigned to (or declared as) a local
  in a float register is computed in that register when it is a load, sqrt of such an expression,
  or + - * / of one and a load; at a statement xmm0 and xmm1 are free, so a right operand that is
  itself such an expression is computed in one of them. The destination may be read only as the
  first operand (the one moved into the register first: `fLaterReads`). `pairF` computes such a
  right operand in xmm1 rather than parking the left one.
- **Element addresses across stores** (cse `addrOnly`, `killMem`): an address that is arithmetic
  on locals alone (no load, no local whose address is taken) reads no memory, so a store or a call
  does not change it, only an assignment of one of its locals. It stays available across them,
  and a store's own place and value are visited; it is worth a local when the element size is not
  one an addressing mode scales by (1, 2, 4, 8).

| measure (main fe29b218 against this) | instructions | cycles |
|---|---:|---:|
| bench nbody / matmul (5 interleaved rounds) | -44 / -25% | -31 / -27% |
| bench interp / closures | level | level |
| perfsuite run suite / compile suite | 0.00 / +0.09% | +0.28 / +0.61% |
| apps regex / json / jq / cmark / decimal | -0.10 / -0.09 / -0.10 / -0.05 / 0.00% | -0.7 / +0.1 / -1.4 / -0.3 / +0.1% |
| TPC-H SF1, server instructions per query (22) | -0.13% geomean | |
| lexdb point select (icount6, 2 alternated rounds) | level (172,348 both) | +0.3% |

The compile suite's +0.09% is the new analysis. What remains in `nbody` (4.92G instructions,
1.23G cycles, against Rust's 1.89G and 0.78G) is mostly copies between the IR's temporaries
(`t = dx * dx` into one register, then copied into the next temporary): register coalescing.

Test: tests/run/native_float_targets (a destination read on the right, nested sqrt and
quotients, stores to an element then reads through an equal index, an index reassigned between
uses, a float converted to an index).

## 21. sortBy and str.cmp (library, as built)

`closures` (three stable sorts of 200,000 records with comparator closures) ran 2.2 times
Rust's time. Its profile: the merge loop 37%, `rt_str_cmp` 20%, the comparators 21%, the
permutation's swaps 7%.

- **str.cmp compared twice**: `cmpOf(a < b, a > b)`, two calls of `rt_str_cmp` for every
  unequal pair. `strCmp` is now an intrinsic for the runtime's three-way comparison (added to
  the compiler first, a commit of its own, so that the seed knows it before std uses it), and
  `str.cmp` calls it once.
- **sortBy** (collections.lxl) still sorts indices and permutes the elements at the end (T may
  be owned), but sorts runs of 16 by insertion first, merges between two index arrays instead
  of copying each merged run back, takes two runs already in order as they are (one comparison
  at their boundary: the second sort in `closures` starts from key order), and keeps the current
  left and right indices in locals.

| measure (main e0c96b21 against this) | instructions | cycles |
|---|---:|---:|
| bench closures (5 interleaved rounds) | -28% | -25% |
| apps regex / json / jq / cmark / decimal | 0.00% each | +0.1 / -0.2 / +1.0 / 0.0 / 0.0% |
| TPC-H SF1, server instructions per query (22) | -0.33% geomean (q12 -1.8, q22 -1.8, q19 -1.3, q8 -1.1) | |
| lexdb point select (icount6, 2 alternated rounds) | level (172,309 to 172,315) | +0.3% |

Test: lib/tests/run/collections_sortby_stable (320 cases: sizes around the run and merge widths,
few and many distinct keys, ascending, descending and equal inputs, owned strings; stable, a
permutation, sorted, leak-free).

## 22. Where Java leads on lists, trees and strings (profiles), and a concat fix

**Method.** `perf record -e cycles:u` of the JVM (OpenJDK 21.0.13, default G1) with
`-XX:+UnlockDiagnosticVMOptions -XX:+DumpPerfMapAtExit` for the JIT's symbols and
`-Xlog:gc` for the collections, 40 timed runs in one JVM; Lexell's profiles at main 0846b6de
(LXL_NATIVE_MAP). Milliseconds per run, from each profile's shares:

| | Lexell | Java |
|---|---:|---:|
| lists: the walk (`sum`) / building / freeing | 53 / 36 / 20 | 33 / 25 / 0.5 (collection) |
| trees: `build` / `check` / freeing (drop actions, push, pop) | 32 / 24 / 33 | 19 / 15 / 0.5 |
| strings: the concatenation and digits / the rest | 54 / 37 | 35 in `stringsMain`, everything inlined / 10 |

**Reading.** Collection is about 1% of Java's time: 22 ms of pauses over 42 runs, at most 2.3 ms
each, the young generation holding almost nothing live. Its lead is in three parts:

- **Freeing costs it nothing per object**: 18% of Lexell's `lists` and 35% of `trees`.
- **Its walks and building are 1.6 times faster.** Its nodes are 24 bytes (compressed
  references: a 12-byte header and the fields); Lexell's are 32 (`lists`: value and
  `Option[Node]`, a tag and a pointer, then the 8-byte block header) and 48 (`trees`: two
  options, rounded up to the 40-byte class). A null-pointer `None` for boxed records (section 2's
  deferred niche) would make a tree node 24 bytes with its header and turn each `Some` test into a
  pointer test, in the walks and in the drop actions alike.
- **strings**: C2 inlines the whole concatenation into the method (section 17's notes).

**Fix (native/rt.c).** The concat functions counted an int part's digits twice, for the total
length (`rt_part_len`) and again when writing it (`rt_cat_slow`): `rt_ipart_len` was 18% of
`strings`. The lengths are now counted once and passed to the writes.

| measure (main 0846b6de against this) | instructions | cycles |
|---|---:|---:|
| bench strings (5 interleaved rounds) | -7.1% | -7.9% |
| apps regex / json / jq / cmark / decimal | 0.00 / 0.00 / 0.00 / 0.00 / +0.05% | +0.3 / +0.4 / -0.8 / -0.3 / 0.0% |

Only the concat functions changed size (the runtime's other sections are as they were).

**Next, from this:** a null-pointer `None` for `Option` of a boxed record (the representation:
check, emit, lower, the drop glue, both backends), measured first on `lists` and `trees`. Built:
section 24.

## 23. Doubles: temporaries coalesced, stores from a dying temporary, addresses that set a local (as built)

The IR keeps the left operand of an operation in a temporary when the right one has effects
(a bounds check: `t7 = bs[i].x; dx = t7 - bs[j].x`) and splits sums into temporaries
(`t18 = dx * dx; t19 = t18 + dy * dy; d2 = t19 + dz * dz`). Each temporary had a register of its
own, so every step was a `movapd` into the next one's. Rust's `nbody` is level with this one in
the loop's arithmetic; it leads by unrolling the five bodies and computing two pairs at a time
(`vsqrtpd`, `vmulpd`): vectorisation, not copies.

- **Coalescing** (x64gen `joins`): a double declared with an initializer that reads local o only
  as its first operand (what `genFT` moves into the target register before anything else:
  `firstOpLocal`), where o's range ends, may share o's register. The two ranges meet only at
  that declaration, which reads o's register before it writes the new local's. Both must be
  declared with initializers in the same loop: a temporary declared before a loop and read by
  the body's last declaration is live around the loop, its range widened to the loop's end.
  The allocator tries the partner's register first.
- **Stores from a dying temporary** (`fIntoTemp`): `t = p.vx; p.vx = t - dx * mj` computes the
  value in t's register when the statement before declared t and nothing else reads it (its uses:
  the declaration and this read), then stores from there; before, it went through xmm0.
- **Addresses that set a local** (`addrCode`): a load whose address computation assigns an
  integer local (cse's `rbx = &bs[i]`, kept for the next statements) is a memory operand too,
  as a pure one is: integer code alone, no call.

| measure (main fc9b8580 against this) | instructions | cycles |
|---|---:|---:|
| bench nbody / matmul (5 interleaved rounds) | -17.3 / -6.6% | -2.6 / -6.9% |
| bench interp / closures | level | +0.8 / +0.1% |
| perfsuite run suite / compile suite | 0.00 / +0.15% | -0.02 / -0.06% |
| apps regex / json / jq / cmark / decimal | 0.00% each | -0.1 / 0.0 / -2.2 / +0.2 / -0.1% |
| TPC-H SF1, server instructions per query (22) | +0.01% geomean | |
| lexdb point select (icount6, 2 alternated rounds) | level (172,346-172,422 against 172,330-172,350) | +1.4 / +2.1% |

`nbody`'s cycles moved less than its instructions: the loop is bound by the latency of
`sqrtsd` and `divsd`, not by its instruction count. The compile suite's +0.15% is the new
bookkeeping per local. The point select's cycles: one function of lexdb changed (the planner's
`grpCost`, 64 bytes smaller), so everything after it moved; its instructions are level.

Test: tests/run/native_float_coalesce (nbody's pair loop, a temporary read again on the right,
a temporary live around a loop whose body's last declaration reads it, a temporary read by two
stores, compound assignments of elements).

## 24. An Option of a box is a pointer (as built)

Section 22 found Java's walks over `lists` and `trees` 1.6 times faster, its nodes 24 bytes
against Lexell's 32 and 48: `Option[Node]` was a tag and a pointer. Now a value closed type of
two variants, one without fields and one whose single field is a boxed type (a record or closed
type that is not a value type, not `rc` or `Shared`), is that box's pointer alone, the null
pointer its other variant (sema `niche`). A box is never null, so nothing else changes meaning.
`Option[Node]` is 8 bytes; a `lists` node is 16 bytes with its 8-byte header (the 24-byte class,
from 32), a `trees` node 24 (from 48).

- **Layout** (emit `layout`): `struct { union { struct { Node* f_0 } V_Some } u }`, no tag; the
  payload is where it was, so every `u.V_Some.f_0` reads it as before.
- **Tests** (check `tagIs`): a match arm, `for ... in`'s end and `try` test the pointer
  (`!!p`, `!p`) instead of the tag; the glue's switches on the tag (clone, eq, hash, toStr) switch
  on `p ? some : none` (emit `tagX`); a drop is `if (p) { the box's drop }` (emit `cases`).
- **Construction** (`nicheInit`): `Some(x)` is `{.u.V_Some = {x}}`, `None` a null pointer of the
  field's type; constants alike.
- **Generic bodies**: in `fn (o: &Option[T]) isSome()` whether T is a box is known per instance,
  so the test and the initializer are holes (`H_TAGIS`, `H_VINIT`) that emit fills per instance.

| measure (main 21aade84 against this) | instructions | cycles |
|---|---:|---:|
| perfsuite lists / trees | -8.4 / -4.3% | -18.2 / -19.3% |
| perfsuite run suite / compile suite | -0.81 / +0.06% | -2.75 / -0.06% |
| apps regex / json / jq / cmark / decimal | 0.00% each | +0.2 / +0.1 / -0.1 / -0.1 / 0.0% |
| TPC-H SF1, server instructions per query (22) | -0.04% geomean (q22 -0.6%) | |
| lexdb point select (icount6, 2 alternated rounds) | -0.18% (172,008-172,023 against 172,320) | +1.9 / +0.7% |

lexdb's `Option[Expr]`, `Option[Prog]` and the like are now pointers too: the point select's
instructions fall a little; its cycles rose with more branch misses (463 against 420-432 a
statement), which the instruction counts do not explain: flagged, not traced.

Test: tests/run/option_niche (lists and trees built, walked, cloned and dropped; ==, hash,
toStr; arrays and maps of them; a user type with the empty variant first; an Option of an
Option of a box, which keeps its tag; an iterator whose next returns one; a closed type whose
Ok holds a box; replace; a boxed closed type in an Option), the same on --c, --native and -O.

## 25. r10 and r11 for locals (as built)

`interp` kept a temporary of each arithmetic case in its frame (a store and a load a step):
every register a local could have was taken (rbx and r12-r15 saved, rsi, rdi, r8 and r9 where
nothing calls), while r10 and r11 held nothing between statements: they are the code
generator's scratch registers. Now an integer local used in a loop (raw weight 128) may have one
where no position of its range runs code that uses them (`SCRATCH_REGS`, `loud1011`):

- calls and 128-bit code (loud and loud89 positions, as for the other registers);
- `clobbers1011`: an aggregate copied or built (`copyMem`, `initAt`, `fillEntries`), a store
  through an address it computes or to a global (`genAssign` holds the address in r11), a
  post-increment of a place in memory, a selection (`genConstSel`), a declaration of an
  aggregate, a return;
- an array filled by `rep stos` (rdi kept in r11), at all of the loop's positions;
- the entry (no argument arrives in either).

The stubs of the inline growth and allocation paths save r8-r11 already. Neither register is
saved or restored: the range has no call.

| measure (main 928ada8b against this) | instructions | cycles |
|---|---:|---:|
| bench interp (7 interleaved rounds) | -1.6% | -2.2% (1,147-1,163M; main 1,180-1,191M, or 1,320-1,340M in 3 of 7) |
| perfsuite run suite / compile suite | -0.03 / +0.29% | -0.22 / +0.15% |
| apps regex / json / jq / cmark / decimal | 0.00 / -0.03 / 0.00 / +0.05 / -0.03% | +1.1 / -0.5 / -0.6 / +0.4 / -0.1% |
| TPC-H SF1, server instructions per query (22) | -0.15% geomean | |
| lexdb point select (icount6, 2 alternated rounds) | level (172,022-172,025 against 172,020-172,021) | -3.7 / -2.2% |

The compile suite's +0.29% is the new marks of the scan; without the loop's threshold every
local could take r10 or r11 (TPC-H -0.27%, decimal -0.24%) and the compile suite paid +0.52%.

Test: tests/run/native_scratch_regs (many integers live at once across stores through computed
addresses and to a global, records copied and built, post-increments of elements, selections
between large constants, a fill by rep stos, a return from a branch, 128-bit arithmetic).

## 26. Drops of trees in a stack of their own; an exhaustive match's last arm untested (as built)

After section 24 a census of `lists` and `trees` (profiles, LXL_NATIVE_MAP) showed where Java's
lead now is. `lists` frees in 1.5% of its time: 96% is the recursive walk `sum`. `trees` drops
in a third of its: its drop action (23%), `rt_dpush` (5%) and `rt_drun`'s loop with an indirect
call per pushed node (6%).

- **Drop actions** (emit `selfLoop`): a recursive type's action already followed one child in a
  loop and pushed the others onto the worklist (`rt_dpush`, run by `rt_drun` through a call per
  entry). When no drop method is reachable from the type (`noUserDrop`: nothing can see the order
  of its parts' drops), its own children wait in a stack of the action's own (`void* ls[32]`,
  `DSTACK`) and go to the worklist only beyond it: a tree's drop makes no call but `rt_free`'s
  (inline). A type with a drop method keeps the worklist alone, and its order.
- **An exhaustive match's last arm** (check): when the arms before it name every other variant,
  the last is the `else` of the tests before (no load and test of the tag again). In `sum` this
  ended the re-test of `None` and the register it kept live across the call.

| measure (main f1b607aa against this) | instructions | cycles |
|---|---:|---:|
| perfsuite trees / lists | -13.2 / -2.9% | -18.6 / -3.5% |
| perfsuite run suite / compile suite | -1.06 / -0.22% | -1.33 / -0.44% |
| apps regex / json / jq / cmark / decimal | 0.00 / -0.03 / -0.02 / 0.00 / -0.20% | -0.1 / -0.2 / +0.7 / -0.3 / -0.1% |
| TPC-H SF1, server instructions per query (22) | -0.14% geomean (q5 -0.6%) | |
| lexdb point select (icount6, 2 alternated rounds) | -0.16% (171,760 against 172,030-172,060) | -3.3 / -3.1% |

What remains in `lists` is the walk: `sum` (inlined into itself once) saves and restores four
callee-saved registers a call. Two of them hold values that are only read as the call's
arguments or only written from its result, which the allocator's positions (a statement each)
count as live across the call.

Test: tests/run/drop_local_stack (balanced trees, a left spine of 1,000 nodes, far deeper than
the stack, nodes with strings and arrays, a match whose last arm is untested, a type with a
drop method whose drops keep their order), the same on --c, --native and -O, no leak under
LXL_CHECK=1.
