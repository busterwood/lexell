# Where the x64 backend's code shape loses to gcc -O2

Status: audit, 2026-11-07, on `codegen-audit` (from `7fc83733`). Ten
microbenchmarks built three ways, profiled on core 6, hot loops read
instruction by instruction. One cheap selection change was measured and kept
(`bbcb32f1`, section 5); the rest is quantified, not built.

The question: native `-O` is level with or ahead of the same source through
the C backend on eight of ten programs, and behind hand-written gcc -O2 only
on `fib` (1.10), `tokens` (1.21), `loop` (1.00, same cycles but twice the
instructions) and `sieve` (1.02), plus `array` (3.62), whose hand-written C
gcc auto-vectorises. Deleting every inline check was already measured and
buys ~3% instructions and no cycles (`7fc83733`, HISTORY.md "Tried and
shelved"). So the remaining gap is not the checks. This note says, per
benchmark, which emitted instructions are worse than gcc's and what each kind
of fix would cost.

## 1. Method

Builds, from `obx/compiler/out/obxc` (the seed, then the modified compiler for
the prototype):

- native: `obxc obx/bench/NAME.obx --native -O -o NAME_nO`, with
  `OBX_NATIVE_MAP=NAME.map` so `perf report` addresses resolve to functions
  (design/native.md, section 4, "the map file");
- C backend, same IR: `obxc obx/bench/NAME.obx -o NAME_c` (gcc -O2);
- hand-written C: `gcc -O2 -fno-optimize-sibling-calls obx/bench/c/NAME.c`.

Measurements are `taskset -c 6 perf stat -x, -e instructions:u,cycles:u`,
three runs of each binary interleaved, best of three. The machine is shared
with other jobs: instruction counts repeat to 0.01%, cycles move 5% to 20%
between windows. Every claim below that matters is an instruction count; a
cycle number is given only where the same change was seen in a quiet window,
and the prototype was re-measured five times.

Hot functions: `perf record -F 999`, then `perf report`; the map file names
native functions, `objdump -d` gives the C builds. Native text has no section
headers, so the raw segment is disassembled with
`objdump -D -b binary -m i386:x86-64 --adjust-vma=0x400000`. The IR after
`opt`/`loops` was read with `OBX_NATIVE_IR=file` to see which checks and
copies survive.

## 2. Per-benchmark numbers

Best of three, core 6. `native/C` and `native/hand C` are cycle ratios (below
1 is native faster). Hand C exists for nine programs; `maps` has none.

| program | native -O Minstr | Mcyc | C backend Minstr | Mcyc | hand C Minstr | Mcyc | native/C | native/hand C |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| fib | 3973.9 | 1693.2 | 4636.4 | 1530.9 | 4636.4 | 1539.4 | 1.106 | 1.100 |
| loop | 8000.0 | 1007.8 | 9000.2 | 1268.5 | 4000.1 | 1009.7 | 0.794 | 0.998 |
| array | 2413.0 | 430.6 | 3007.2 | 486.2 | 707.1 | 118.8 | 0.886 | 3.623 |
| alloc | 1280.0 | 283.4 | 3080.2 | 568.2 | 2880.1 | 548.6 | 0.499 | 0.517 |
| lists | 453.3 | 134.7 | 764.2 | 173.4 | 630.7 | 137.2 | 0.777 | 0.982 |
| strings | 931.3 | 194.5 | 1551.2 | 370.3 | 1620.3 | 398.5 | 0.525 | 0.488 |
| trees | 254.1 | 70.6 | 412.5 | 105.1 | 352.0 | 94.1 | 0.672 | 0.750 |
| tokens | 126.1 | 47.2 | 265.9 | 80.1 | 90.8 | 39.1 | 0.589 | 1.206 |
| sieve | 1414.4 | 745.4 | 1427.8 | 949.7 | 1414.4 | 728.6 | 0.785 | 1.023 |
| maps | 2103.6 | 924.9 | 1822.9 | 871.8 | - | - | 1.061 | - |

Read the same-source column (`native/C`) as the code generator contest: the
runtime is the same in both builds, and gcc is compiling the very IR x64gen
compiled. Native wins it everywhere except `fib` (+10.6%) and `maps` (+6.1%).
The hand C column also contains what the language costs (refcounted `str`,
checked allocation, the obx record layout); `tokens`, `strings`, `trees` and
`alloc` are dominated by that and the runtime's allocator, not by selection
(through C, `tokens` spends 40% of its samples in libc's malloc, memcpy and
strcmp, native in its own `rt_alloc` and `memcpy`). The categories below separate the two.

## 3. Hot loops, instruction by instruction

Dynamic counts: fib(40) is 165,580,140 internal calls and 165,580,141 leaf
calls; `loop` is 10^9 iterations; `array` is 200 x 10^6 inner iterations;
`sieve` is 10 rounds, about 220M marking stores and 100M counting iterations;
`tokens` scans 84,217 bytes ten times (the identifier path is ~40% of them).

| program | hot code | native | C backend | gcc hand C | iterations |
|---|---|---:|---:|---:|---:|
| fib | one call | 20 (leaf 4) | 17 (leaf 11) | 17 (leaf 11) | 165.6M + 165.6M |
| loop | the loop body | 8 | 9 | 4 | 10^9 |
| array | the inner body | 12 | 15 | 10 per 4 elements | 2x10^8 |
| sieve | mark / count | 4 / 5 | 4 / 7 | 4 / 7 | 220M / 100M |
| tokens | identifier byte | 54 (common path) | - | ~8 | ~340K |
| maps | map probe | 8 empty, ~25 occupied | - | - | ~3M lookups |

The three gaps that are not allocation or refcounting:

**fib: 20 instructions per internal call against gcc's 17, but a 4-instruction
leaf path against gcc's 11.** The leaf path is shrink-wrapping
(`genGuards`, x64gen.obx 791-844): `cmp rdi,2; jge; mov rax,rdi; ret`. gcc still
pushes `rbp`, `rbx`, subtracts 8 and restores on every leaf. That is why
native executes 0.86 of gcc's instructions yet used to run 1.10 of its cycles.
The internal path's excess was two `mov`+`sub` pairs for `n - 1` and `n - 2`:
`mov rdi,rbx; sub rdi,1` where gcc emits `lea rdi,[rdi-1]`. `arithInto`
(x64gen.obx 6719-6775) cannot see that the source is already in a register and
the destination is another one. The prototype in section 5 fixes exactly this
and takes fib to 18 instructions and 0.99 of gcc's cycles.

**array: 12 instructions per element against gcc's 2.5 (vectorised) and 15
through the C backend.** Of the 12, one (`mov rsi,rax`) is a copy of a
temporary that has a register (`t12` in the IR) but is computed into `rax`:
`staticMem` (x64gen.obx 3469-3485) does not name `*(p + i)` as a memory
operand, so `arithInto` refuses and the general `gen -> rax -> mov -> store`
path runs. Two `jo`, one bounds `cmp/jae` and the loop test are the rest.
gcc's hand-written C has no checks and is auto-vectorised four elements at a
time (10 instructions per four); the same source through the C backend is 15
because `rt_idx`'s inline check blocks gcc's vectoriser. Native is 20% below
the C backend on instructions, 11% on cycles; the 3.6x against hand C is
almost entirely vectorisation.

**tokens: 54 instructions for the common identifier byte against gcc's ~8.**
The IR has already lowered `&&`/`||` into `bool` locals (`b1_130`, `t2`,
`c4`); x64gen materialises each as `setcc`+`movzx` and tests it again, and
reloads the string's base and length from the frame every byte. One pass over
`i < len(src) && (isLetter(c) || isDigit(c))` is
`cmp rbx,[rbp-0x48]; setl al; movzx eax,al; mov rsi,rax; mov rax,rsi;
test rax,rax; je` (7 instructions where `cmp; jge` is 2), then one
`setcc`/`movzx`/`mov`/`test`/`jcc` chain per `isLetter`/`isDigit` clause
(about 25 instructions where gcc's compare/bit-test sequence is 5), and
`mov rax,[rbp-0x50]` before every byte load (`sd` and `sl` are loop-invariant
locals that the register allocator spilled). gcc also inlines the whole scan
into `main` and folds `isLetter(c) || isDigit(c)` into `lea/cmp/jbe/bt`.
`tokens` is 1.21x gcc because of the refcounting too (the `intern` loop moves
`str` pairs and bumps reference counts around `rt_str_eq`), but the scan loop
is the largest single code-shape miss.

**loop: 8 instructions against gcc's 4, but one cycle an iteration either
way.** `s = s + i * 2` is `mov rax,rsi; imul rax,rax,2; add rax,rbx; jo;
mov rbx,rax; add rsi,1; cmp; jl`. gcc strength-reduces `i * 2` into an
induction variable stepping by 2 and drops the multiply and the final copy
(`add rdx,rcx; add rcx,2; cmp; jne`). Native's extra instructions are issue
slots, not a dependency chain: both run at 1.0 cycle per iteration. It is a
2x instruction-count gap with no cycle gap, and the prototype's `lea` removes
1 of the 8 (12.5%) with no cycle change.

**sieve is at parity** (native 1414.4M against gcc 1414.4M instructions, 1.02
cycles). The marking loop is `mov byte [r8+rsi],0; add rsi,rdi; cmp rsi,rbx;
jle` against gcc's four. The counting loop is native's win:
`cmp byte [r8+rsi],1; sbb r12,-1; add; cmp; jl` (branchless, from `incIf`,
x64gen.obx 3034-3073) against gcc's `cmp; je; add; jo` (7.19M branch misses
through C, 17K native). No selection work is justified here.

**maps: native is 15% above the C backend on instructions and 6% on cycles.**
`f32_std_Map_find` (2,103.6M total, 28.8% of samples in its probe loop) keeps
the bucket hash in a frame slot and reloads it every occupied probe
(`mov edi,[rbp-0x40]`), does `sub rax,1; jo` where gcc has `lea rbx,[rax-1]`,
and `imul rcx,r14,0x10; lea` where an addressing mode `[r12+r14*16]` would do.
The hash itself is a chain of `movabs`/`imul`/shifts; gcc's C build has the
same constants and 15% fewer instructions around them. This is the
register-allocation and addressing-mode bucket, not a new algorithm.

## 4. The misses, ranked

Costs are dynamic instructions over the whole run, from the static counts in
section 3 times the iteration counts. Cycle estimates are ranges because the
machine is noisy; where a fix was built, the measured number is used.

| rank | miss | where and count in the hot loop | estimated cost | fix |
|---:|---|---|---|---|
| 1 | two-operand `rax` evaluation: no `lea` for `x + k`, `x - k`, `x * 2..9` | fib 2 per internal call (331M, 8.3%); loop 2 per iter before the fix (2G, 25%); array 1 copy per element (200M, 8.3%); maps 1-2 per probe | fib 331M instr, 164M cycles measured; loop 1G instr by `lea` alone (12.5%), 2G with strength reduction; array/maps 1-3% cycles | 66 lines in `genBin`/`arithInto`/`inlineRt` (`leaMul`, x64gen.obx 5044-5155, 6755-6825); **built, section 5** |
| 2 | boolean/branch materialisation: `bool` locals from `&&`/`||` become `setcc`+`movzx`+`test` | tokens 7 instructions for `i < len` instead of 2, plus ~25 per `isLetter`/`isDigit` clause instead of 5 (~40 extra per identifier byte; ~10-15M total, 8-12% of tokens) | tokens up to 8-12% instructions and ~5-10% cycles; the same pattern is common in the compiler's own sources | extend the tree-level bool folding in `opt`/`loops`, or teach `branch` (x64gen.obx 5792-5820) and `genAssign` (4799) to consume a bool local's defining comparison; 150-350 lines |
| 3 | callee-saved and frame overhead: `push rbp; mov rbp,rsp`, 2-5 pushes, `leave`, and one prologue for all paths | fib 8 of 18 per internal call (the leaf path is 4 instructions, already shrink-wrapped); maps find 5 pushes + `sub rsp` per call; regex per match (see below) | dropping the `rbp` frame saves 3 per fib call (0.5G, 12.5% of old fib) but few cycles; 1-3% general | shrink-wrap past callee-saved saves, or omit `rbp` when there are no temp slots and pop instead of load: `genFunc` 618-790, `epilogue` 2514-2535, 100-250 lines |
| 4 | register allocation: spilled loop invariants, values reloaded after calls, no caller-saved locals across statements | tokens `sd`, `sl` reloaded 2-3 times per byte (~2.5M); maps hash low word spilled and reloaded per probe; array's `t12` copy; mid-ir.md's self-build: stack loads 7.4% + stores 5.6% of instructions, callee-saved saves ~4% | 3-8% instructions and 5-10% cycles on non-allocation programs; mid-ir.md estimates 8-12% of the compiler's cycles | linear-scan RA with live-range splitting, all 14 GPRs, caller-saved for values not live across calls: 900-1,400 lines (mid-ir.md 438-455; M1's `midra.obx` was 1,518, mid-ir.md 577) |
| 5 | addressing modes: `staticMem` cannot name `*(p + i)`, so no memory operand in arithmetic/compare and an extra copy | array 1 per element (200M); maps `imul`+`lea` where `[base+index*16]` fits (1-2 per probe) | 2-8% instructions on array/lists/trees/maps, 1-3% cycles | teach `staticMem`/`viaReg` (3469-3500) about `E_PADD` with a register index and a local base; 80-150 lines |
| 6 | loop strength reduction: constant multiplies in induction variables, `i*i` hoisting | loop 2 of the 7 remaining per iteration (2G, 28.6%); sieve's `i*i` check is per outer iteration only (negligible) | loop up to ~28% fewer instructions, ~0-2% cycles (already 1/iter); little elsewhere | `loops.obx`: turn `i * k` in a loop into a stepping temporary when `i` is the induction variable; 100-200 lines |
| 7 | checks: bounds (array 1/iter), overflow (array 2/iter, loop 1/iter) | array 3 checks = 600M (25%); loop 1 = 1G (12.5% of its old 8) | measured: -3.9% instructions, no cycles (7fc83733) | do not repeat; only a pass that also changes code shape (vectorisation) should own them |
| 8 | vectorisation, array only | 12 instructions per element against gcc's 2.5; hand C 707M/118.8M against native 2413M/430.6M | 3.4x instructions, 3.6x cycles on array; nothing else | auto-vectoriser 1,500-3,000 lines, or SIMD in the language (small-fast-compiler.md's recommendation); not a peephole |

Regex, not modified and not measured here (the files belong to another
change): `7fc83733` measured 1.16x the C build for one match and 1.63x for
669,532 matches, with a 22-instruction byte loop of which 4 to 6 are checks.
The per-match cost is the same shape as rank 3 and 4 (prologue/epilogue per
`forward`/`backward`, `Cache.start`, `str` dup/drop, span appends) rather
than the checks themselves. Rank 3's shrink-wrapping and rank 4's allocator
are the levers there too.

## 5. Prototype: one `lea` for small constant arithmetic

`bbcb32f1` adds `leaMul` (x64gen.obx 5044-5064) and three call sites:

- `genBin` (5067-5175): a 64-bit `x + k`, `x - k` or `x * {2,3,4,5,8,9}` of a
  local in a register becomes `lea rax,[reg+disp]` / `[reg+reg*scale]`,
  where it was `mov rax,reg` and the operation;
- `arithInto` (6719-6775): the same, into the destination register a call
  argument or assignment names (fib's `n-1`, `n-2`);
- `inlineRt` (6781-6825): the wrapping runtime multiply (`rt_wmul_int`,
  loop's `i * 2`), straight from the source register.

Only wrapping operations use it (`w < 0` or `ar.wrap`): `lea` sets no flags,
so the checked forms keep their `add`/`sub` and `jo`. `INT_MIN` as a
subtracted constant is excluded because its negation is not a 32-bit
displacement. The result is still normalized by `normR`, so 32-bit and
8/16-bit types keep their wrapping and sign rules.

Measured against the same tree before the commit (core 6, best of 3,
interleaved):

| program | before Minstr | after Minstr | change | before Mcyc | after Mcyc | change |
|---|---:|---:|---:|---:|---:|---:|
| fib | 3973.9 | 3642.8 | -8.33% | 1693.2 | 1529.2 | -9.8% |
| loop | 8000.0 | 7000.0 | -12.50% | 1007.8 | 1007.9 | level |
| array | 2413.0 | 2413.0 | 0 | 430.6 | 430.6 | level |
| alloc | 1280.0 | 1280.0 | 0 | 283.4 | 283.4 | level |
| lists | 453.3 | 453.3 | 0 | 134.7 | 134.7 | level |
| strings | 931.3 | 931.3 | 0 | 194.5 | 194.5 | level |
| trees | 254.1 | 254.1 | 0 | 70.6 | 70.6 | level |
| tokens | 126.1 | 126.1 | 0 | 47.2 | 47.2 | level |
| sieve | 1414.4 | 1414.4 | 0 | 745.4 | 745.4 | level |
| maps | 2103.6 | 2101.0 | -0.13% | 924.9 | 924.9 | level |

`fib`'s internal path went from 20 instructions to 18 (`mov rbx,rdi;
mov rdi,rbx; sub rdi,1` to `mov rbx,rdi; lea rdi,[rbx-1]`), so native now runs
0.99 of gcc's cycles on it (was 1.10) while still executing 0.79 of gcc's
instructions thanks to its 4-instruction leaf path. `loop` loses exactly one
of eight instructions per iteration. All ten outputs are identical to the C
build, `run_native.py --lib` and `--lib --opt` pass (613 and 612+1 live
MSSQL test, which passed on rerun), `gate.sh quick` passes except that one
live-service timeout, `native_selfbuild.sh` reaches its fixed point, and
`optcost.py` reports -O/default at +15.8% instructions / +18.7% cycles
(geomean), inside the +30% budget.

## 6. What the big levers cost, from x64gen's structure

| lever | parts of x64gen it replaces | lines (estimate) | gain (estimate) |
|---|---|---|---|
| selection on the tree (rank 1 above, and memory operands/address modes) | `genBin` 5067-5175, `arithInto` 6719-6775, `inlineRt` 6781-6835, `staticMem` 3469-3500, `pairSrc`/`pairC` 3840-3975 | 200-350 | 3-8% instructions on array/maps/lists/trees; 1-4% cycles; the `lea` part alone was 66 lines and 8-10% on fib |
| bool/branch folding before selection | `branch` 5792-5820, `genTest` 5769-5790, `genAssign` 4799-4835; or `opt`/`loops` | 150-350 | up to 10% on branchy scans (tokens), 2-5% on the compiler's own sources |
| shrink-wrapping through callee-saved saves / no `rbp` frame | `genFunc` 618-790, `placeCode` 948-990, `epilogue` 2514-2535, `epiJmps` | 100-250 | 2-5% on small call-heavy functions (fib), ~1% general |
| linear-scan RA with splitting | `allocRegs` 991-1157, `spillReg` 1158-1247, `remat` 2331-2430; replaces the register choice, not the whole generator | 900-1,400 | 3-8% instructions, 5-10% cycles on non-allocation code; mid-ir.md's ceiling is 8-12% of the public compiler's cycles, and M1 showed the spills are dominated by frame objects, so scalar replacement of small records/`str` must come with it |
| loop strength reduction | `loops.obx` (2,437 lines today), not x64gen | 100-200 | ~28% of `loop`'s instructions, ~0-2% cycles; the instruction-count win does not move time on a 1-cycle loop |
| auto-vectorisation | none today; a new IR pass or SIMD in the language | 1,500-3,000 | 3.4x on `array` only; small-fast-compiler.md recommends the language-SIMD route |

A full mid IR is not needed for ranks 1-3: they stay on the tree and in the
assembler. The allocator (rank 4) is where mid-ir.md's 6K-8.5K line, 6K-10K
instructions-per-mid-instruction pipeline starts; its own M1 measured 3,070
lines for lowering, liveness and the model, and missed the 30% gate because
x64gen already forwards and rematerialises more than a naive allocator
expects. That is the quantified answer to "would a register-allocator rewrite
pay": 5-10% of the non-allocation benchmarks' cycles for 900-1,400 lines, and
8-12% of the compiler for the whole mid-IR programme, not for the ten
microbenchmarks.

## 7. Recommended order

1. **Keep the `lea` selection** (done). 331M fib instructions and 1G loop
   instructions gone for 66 lines, fib 1.10 -> 0.99 of gcc.
2. **Boolean/branch folding** (rank 2). The biggest remaining code-shape gap
   on branch-heavy code, `tokens` first: ~40 extra instructions per
   identifier byte. Judge it on `tokens` and the compiler self-build (the
   same `&&`/`||` pattern is everywhere), not on the allocation benchmarks.
3. **Destination-directed arithmetic and addressing modes** (ranks 1 and 5):
   `*(p + i)` as an operand, so array's `mov rsi,rax` and maps' `imul`+`lea`
   go. 80-150 lines, safe on the same IR, measured by instruction counts.
4. **Loop strength reduction** in `loops.obx` (rank 6) if instruction count
   is the goal; do not expect cycles on `loop`, which already runs at one.
5. **Shrink-wrap callee-saved saves / drop `rbp` where it is only a frame**
   (rank 3), measured on `fib` and the regex's per-match path.
6. **Register allocator with splitting** (rank 4) only as a deliberate
   mid-IR project: 900-1,400 lines, 5-10% cycles, and it needs scalar
   replacement to show the mid-ir.md ceiling.
7. **Vectorisation last** (rank 8), or express it in the language; it is a
   3.4x win on one benchmark and a pass of its own.

Checks (rank 7) stay shelved: the measured upper bound is 3.9% of
instructions and no cycles.

## 8. Reproducing

    D=/tmp/codegen-audit
    for n in fib loop array alloc lists strings trees tokens sieve maps; do
      OBX_NATIVE_MAP=$D/$n.map obx/compiler/out/obxc obx/bench/$n.obx --native -O -o $D/${n}_nO
      obx/compiler/out/obxc obx/bench/$n.obx -o $D/${n}_c
    done
    for n in fib loop array alloc lists strings trees tokens sieve; do
      gcc -O2 -fno-optimize-sibling-calls obx/bench/c/$n.c -o $D/${n}_gcc
    done
    for r in 1 2 3; do for n in fib loop array alloc lists strings trees tokens sieve maps; do
      for v in nO c gcc; do
        taskset -c 6 perf stat -x, -e instructions:u,cycles:u $D/${n}_$v \
          $( [ $n = tokens ] && echo obx/compiler/sema.obx )
      done
    done; done

`OBX_NATIVE_IR=$D/$n.ir` writes the IR after `opt`/`loops` (the bool locals in
`tokens`, the surviving checks in `array`); `OBX_NATIVE_MAP` names the hot
function in `perf report`, or subtract 0x400000 from the sampled address and
look it up in the map file.
