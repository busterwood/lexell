# SSA value numbering on the tree IR: measured and shelved

Status: experiment, 2026-11-07, branch `ssa-gvn` from `363c42ba`. **Negative.**
The prototype was not merged. This note records the counts, the oracle
measurement and what the experiment does and does not prove.

The question: is an SSA-based redundancy elimination pass on the *existing*
tree IR worth building, before (or instead of) the mid-IR programme of
[mid-ir.md](mid-ir.md)? The prior is M1, which built 3,070 lines of mid IR,
liveness and a linear-scan model and missed its gate: 3.02K instructions per
mid instruction, -8.4% loop-weighted stack accesses against a 30% target.
[codegen-audit.md](codegen-audit.md) says the remaining microbenchmark gaps
are code shape (bool locals, addressing, frames), not redundancy. This
experiment tests the redundancy half directly, with an oracle rather than an
estimate.

## 0. Summary

| question | answer |
|---|---|
| Redundancy left after `opt`, `loops` and `cse`, self-build | 5,132 reuses; 39,206 weighted by 10^depth |
| Ceiling, if every reuse saved one dynamic instruction | ~39K of 4.55G instructions: under 0.001% |
| Oracle on the self-build (current `-O` -> `-O` + GVN) | instructions **+1.95%**, cycles -0.51% |
| Oracle on applications | `array` **+58.0% instructions**; `grep` +2.67%; `tokens` +1.78%; `lists` -1.99%; the rest level |
| Compile cost of the pass | +79% for construction alone, +84.6% with numbering and rewrite (budget +10%) |
| `optcost.py`, pass on | `-O`/default +51.1% instructions, +42.8% cycles (budget +30%) |
| Correctness | 613 native tests pass with `--opt --lib` under `LXL_GVN=1` |
| Decision | stop; do not merge; close M2/M3 as a route to GVN |

## 1. What was built

The Braun et al. construction (*Simple and Efficient Construction of SSA Form*,
CC 2013) was recovered from the throwaway probe on branch `ssa-probe`
(`ad0a150`, `lexell/compiler/ssaprobe.lxl`, 481 lines) and ported to the current
tree. Two new files, both removed again with this note:

| file | lines | contents |
|---|---:|---|
| `ssa.lxl` | 904 | the Braun construction, value keys, per-occurrence reference counts, dominator bitsets |
| `gvn.lxl` | 316 | value numbering over SSA values, memory versions for loads, and the rewrite |

It ran only under `--native -O`, after `opt`, `loops` and `cse`:
`gvn.optimize(cse.optimize(loops.optimize(opt.optimize(p))))`.
`main.lxl` changed only for the import and that one call. `LXL_GVN=1` enabled
the rewrite, `LXL_GVN=count` counted without rewriting. Everything below is
the current sources (`363c42ba`), compiled by a native compiler built from
them.

The construction on the self-build (after `opt`, `loops`, `cse`):

| what | count |
|---|---:|
| functions | 1,316 |
| SSA instructions (non-leaf expressions and frame/pointer loads) | 130,926 |
| blocks | 35,416 |
| SSA variables (scalar locals whose address is never taken) | 47,635 |
| variable reads | 310,910 |
| phis left after trivial-phi removal | 22,351 |

The probe's figures (1,131 functions, 221K instructions, 30K blocks, 40K
variables, 55K phis made / 18.7K left) counted every frame load and store as
an instruction, which is why the instruction count differs.

## 2. What was found, before rewriting

A value was numbered and counted when a later occurrence had the same SSA
value (same expression operands, or the same load place and the same memory
version), the earlier definition dominated it, the node had exactly one
parent edge, and the two occurrences were in different statements. Ambiguous
or shared nodes were skipped deliberately: the tree is sometimes a DAG (an
lvalue's dereference can be shared with an rvalue), and the native backend's
evaluation order within a statement is its own.

Counts on the inputs that decide the gate. "Weighted" is the number of
reuses times 10^loop-depth, capped at depth 6, the convention of
[mid-ir.md](mid-ir.md) section 6.

| program | pure | load | addr | call | total | weighted |
|---|---:|---:|---:|---:|---:|---:|
| compiler self-build | 851 | 3,494 | 738 | 49 | **5,132** | **39,206** |
| grep | 172 | 534 | 62 | 11 | 779 | 7,655 |
| tokens | 17 | 3 | 1 | 0 | 21 | 1,101 |
| maps | 9 | 34 | 7 | 0 | 50 | 50 |
| array | 1 | 0 | 0 | 0 | 1 | 100 |
| lists | 0 | 2 | 0 | 0 | 2 | 2 |
| trees | 0 | 2 | 0 | 0 | 2 | 2 |
| fib, loop, alloc, strings, sieve | 0 | 0 | 0 | 0 | 0 | 0 |

The ceiling is small before any measurement: even if every reuse removed one
dynamic instruction, 39K instructions is 0.0009% of the 4.55G self-build. The
load majority is expected: `cse` already removes straight-line loads and
`loops` hoists the loop-invariant ones, so what is left is cross-block reuse.

## 3. The oracle

The pass was run as the real rewrite, not as a count. Every later node with
the value of an earlier, dominating definition was replaced by a local holding
it; the first definition was materialised where it stands (`gv = X`), so no
check or load moved.

### 3.1 Self-build

Each compiler below compiles `main.lxl --native` (the self-build workload).
Best of three, core 6, interleaved; `perf stat -e instructions:u,cycles:u`.

| build | instructions | vs current `-O` | cycles | vs current `-O` |
|---|---:|---:|---:|---:|
| **A** current `--native -O` | 4,552,470,801 | | 2,150,145,708 | |
| **B** `--native -O` + GVN | 4,641,400,880 | **+1.95%** | 2,139,203,633 | -0.51% |
| **C** plain `--native` | 4,743,550,913 | +4.20% | 2,189,275,818 | +1.82% |

Instructions decide: GVN makes the compiler **1.95% slower to run**, not
faster. The cycles agree in sign (-0.51%, within the machine's noise), so
there is no cycle win to argue from. The whole `-O` chain is worth only 4.2%
of instructions and 1.8% of cycles on this workload; GVN gives back half of
that.

### 3.2 Applications

Built with and without `LXL_GVN=1` by the same compiler; best of three,
core 6, interleaved. `grep` scans 53 MB of C; `tokens` reads
`compiler/sema.lxl`; the rest are the ten microbenchmarks.

| program | base Minstr | GVN Minstr | instr | base Mcyc | GVN Mcyc | cyc |
|---|---:|---:|---:|---:|---:|---:|
| fib | 3,642.8 | 3,642.8 | 0.00% | 1,527.1 | 1,525.8 | -0.08% |
| loop | 7,000.0 | 7,000.0 | 0.00% | 1,007.3 | 1,004.4 | -0.29% |
| **array** | 2,413.0 | 3,813.0 | **+58.02%** | 416.5 | 549.1 | **+31.86%** |
| alloc | 1,280.0 | 1,280.0 | 0.00% | 282.2 | 282.2 | +0.01% |
| lists | 453.3 | 444.3 | -1.99% | 133.4 | 126.5 | -5.18% |
| strings | 931.3 | 931.3 | 0.00% | 193.5 | 194.5 | +0.51% |
| trees | 254.1 | 257.0 | +1.13% | 75.7 | 71.3 | -5.83% |
| tokens | 126.1 | 128.4 | +1.78% | 47.7 | 48.3 | +1.27% |
| sieve | 1,414.4 | 1,414.4 | 0.00% | 560.4 | 566.5 | +1.09% |
| maps | 2,101.5 | 2,098.9 | -0.12% | 761.7 | 741.6 | -2.65% |
| grep | 374.4 | 384.3 | +2.67% | 104.7 | 104.3 | -0.37% |

`lists` is the only repeatable instruction win, and it is 2% on a program that
already matches gcc. `array` is a disaster: one numbered pure expression
changed the hot loop's shape and cost 58% instructions.

### 3.3 Why `array` loses

The single reuse was the cast `(int64_t*)hd_34` of the array's data pointer,
which occurs in both the element load and the element store of the inner loop.
The rewrite made it a local:

```c
int64_t* gv;
int64_t t12 = rt_add_int(*((gv = (int64_t*)hd_34) + rt_idx(...)), ...);
*(gv + ix13) = t12;
```

x64gen already rematerialises and folds that address at each use. With the
local, the allocator spilled `gv` to the frame and the loop grew from 12 to
21 instructions per element: a store and reload of the pointer at
`-0x40(%rbp)`, plus extra `mov`/`lea`, on 200M inner iterations. That is
+1.4G instructions and +130M cycles. The static count said "one reuse at
depth 2"; the code shape said "do not create that local".

This is the central finding: on this backend, a repeated *pure address
expression* is often cheaper to recompute than to keep in a tree-level local.
GVN's counts do not know what x64gen's `remat`, `forward` and `staticMem`
already do.

## 4. Compile cost

Measured on the self-build, compiler compiling `main.lxl --native -O`, user
instructions:

| configuration | instructions | over current `-O` |
|---|---:|---:|
| current `-O` (no pass) | 5,932,311,004 | |
| SSA construction only (`LXL_GVN_SSAONLY=1`) | 10,625,538,898 | **+79.1%** |
| construction + numbering (`LXL_GVN=count`) | 10,793,496,306 | +82.0% |
| construction + numbering + rewrite (`LXL_GVN=1`) | 10,951,549,282 | **+84.6%** |

The construction is not tuned. The old probe cost 306M (+6.9%) on its source
set; this port adds value/expression tables, per-occurrence reference counts,
dominators and a `Map` per variable, and the per-function bookkeeping still
scales with the whole program's node and local arrays. It is two orders of
magnitude over the +10% pass budget and would need a different implementation
before it could be judged as production code. It does not change the
conclusion: the oracle's run-time sign is wrong.

`optcost.py` (`--compiler` the native compiler, `--pin 6 -n 2`), geometric
mean of eight programs:

| configuration | `-O`/default instructions | cycles |
|---|---:|---:|
| pass off (current `-O`) | +15.8% | +17.6% |
| pass on (`LXL_GVN=1`) | **+51.1%** | **+42.8%** |

The pass-on row breaks the +30% total budget; the compiler program itself goes
from +25.1% to +130.8% instructions.

## 5. Correctness

With `LXL_GVN=1`:

    python3 lexell/tests/run_native.py --compiler /tmp/lxlc2 --opt --lib -j 8
    native: 613 pass, 0 differ, 0 unsupported, 613 total

The native build (with the pass) matched the C build on stdout, stderr and
exit status, with and without `LXL_CHECK=1`. The self-build reached a working
compiler and compiled the benchmarks.

`reseed.sh`, the seed fixed point and `gate.sh quick` were **not** run: the
pass is not being kept, and reseeding would encode dead code in the seed. That
is why this note is the only commit.

## 6. What SSA-on-the-tree does not prove

This experiment bounds one family, on one IR, with one code generator.

- **It does not test M2.** There is no mid IR, no three-address vregs, no
  selection from a mid IR, no addressing modes, no machinize, no emission,
  no frame or ABI change. The SSA here is constructed over the same tree that
  x64gen already walks, and the rewrite materialises locals into the same
  tree. M2's selection and emission — the bulk of the mid-IR cost and of its
  possible gain — are untouched.
- **It does not reopen M1's allocator result.** M1 measured 3.02K compiler
  instructions per mid instruction and a forecast of -8.4% loop-weighted
  stack accesses against a 30% gate. That forecast was about frame objects,
  copies and spills; SSA value numbering cannot change it.
- **It does not measure GVN's value inside a mid IR.** In a mid IR, GVN
  operates on vregs with no materialisation cost and can feed copy
  propagation and DCE. Here every reuse must become a tree local, which is
  exactly what `array` showed can lose. The negative oracle says the tree is
  the wrong place for this pass; it does not by itself price a mid-IR GVN.
- **It says nothing about the other gaps.** Boolean/branch materialisation,
  addressing modes, callee-saved/frame overhead, register allocation and
  vectorisation are outside this experiment. The gcc ablation in
  [mid-ir.md](mid-ir.md) section 2.3 still says the whole redundancy family
  is worth 5.3% of the compiler's cycles; this experiment found the tree-level
  share after `loops`/`cse` is far smaller than that.
- **It is not a fair price for SSA construction.** The +79% here is a naive
  port; the probe's +6.9% is the better estimate of the walk. Neither number
  tests Braun construction inside a linear IR with vregs.

## 7. Recommendation for the mid-IR programme

**Close M2/M3 as a route to redundancy elimination; keep the programme
closed as a default path unless run speed from `--native` becomes a stated
goal.** The evidence is now two independent negatives:

1. M1: the allocator model missed its 30% stack-traffic gate (-8.4%) at 3.02K
   instructions per mid instruction, and most of the model's weight was frame
   objects and copies that an allocator does not remove.
2. This note: after `opt`, `loops` and `cse`, the tree has 5,132 redundancy
   candidates (39,206 loop-weighted) on the self-build; the real oracle makes
   the compiler 1.95% slower and one benchmark 58% slower. The candidate is
   not worth a pass, let alone a mid IR to host it.

If more `--native` run speed is wanted, spend it where
[codegen-audit.md](codegen-audit.md) measured it, on the tree:

- bool/branch folding (rank 2), the largest remaining code-shape gap on
  `tokens` and the compiler's own sources;
- destination-directed arithmetic and addressing modes (ranks 1 and 5);
- shrink-wrapping past callee-saved saves / a frame-free leaf path (rank 3);
- a linear-scan register allocator with splitting (rank 4) only as a
  deliberate project, with scalar replacement of small records and `str`,
  and with M1's stack-traffic model as its gate.

Do not build M2 or M3 to get GVN. If a mid IR is ever revisited, it should be
for allocation and selection first, and its GVN should be judged inside that
IR against a code generator that can keep values in vregs, not against this
tree.

## 8. Reproducing

The prototype is not in this branch. It was:

    ssa.lxl   904 lines   (Braun construction, value keys, refcounts, dominators)
    gvn.lxl   316 lines   (value numbering, memory versions, rewrite)
    main.lxl             one import and one call: gvn.optimize(...) under -O

From `lexell/compiler`, with the native compiler `out/lxlc`:

    LXL_LIB=../lib ./out/lxlc main.lxl --native -o lxlc_host
    LXL_LIB=../lib LXL_GVN=count ./lxlc_host main.lxl --native -O -o x 2> counts
    LXL_LIB=../lib LXL_GVN=1 ./lxlc_host main.lxl --native -O -o lxlc_gvn
    # self-build: lxlc_host (current -O) and lxlc_gvn (with GVN) compile main.lxl --native
    taskset -c 6 perf stat -e instructions:u,cycles:u ./lxlc_gvn main.lxl --native -o x
    # applications: the same host with and without LXL_GVN=1 builds each bench with -O
    python3 ../tests/run_native.py --compiler ./lxlc_host --opt --lib -j 8   # LXL_GVN=1
    python3 ../tools/optcost.py --compiler ./lxlc_host --pin 6 -n 2          # LXL_GVN=1

The earlier SSA cost probe is on branch `ssa-probe`, commit `ad0a150`
(`ssaprobe.lxl`, `LXL_PROBE=ssa`); it is not merged.
