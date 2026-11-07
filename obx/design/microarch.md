# The v3 feature set and code shape in the native backend

Status: audit and measured prototypes, 2026-11-07, on `microarch` (from
`2120ae02`). **No change survived the cycle gate; this branch is `2120ae02`
plus this note.** The audit found one large instruction-count win (`rorx` on
SipHash: -5.6% on `maps`) and one real but narrow win (`andn`: -2.7% cycles on
a tight `a & ~b` loop), neither of which moves any of the required benchmarks
enough to keep. The placement experiments (function alignment, loop
alignment, code placement) are also level. The rest of this note is the
evidence, so the next person does not repeat it.

The question: the language requires x86-64-v3 (`obx/SPEC.md` section 14) and
the runtime is built with `-march=x86-64-v3`, but the generated code is
baseline x86-64. Which of v3's instructions (BMI1/BMI2, LZCNT, POPCNT, VEX
scalar float, FMA3) and which code-shape choices are worth selecting, and
where?

Short answer: on a Zen 4 (and on a Haswell-class core, from the public port
data) the remaining v3 candidates in generated code are all **front-end**
wins: they remove a `mov` that the renamer already eliminates, or a `not` that
is one ALU uop. The first kind does not move cycles at 3 IPC; the second does
where it occurs, but no required benchmark has it hot. The generated code's
gaps are the ones `codegen-audit.md` already ranked: destination-directed
selection, boolean folding, the allocator, and vectorisation, not the ISA.

Gates: `obx/tools/gate.sh quick` passes at HEAD (seed fixed point,
conformance, compiler tests, lib, native lib+run and native -O lib+run 613 of
613, native self-build fixed point). `optcost.py -n 2 --pin 2` on a
native-built compiler reports -O/default +15.7% instructions and +15.4%
cycles (geometric mean), inside the 30% budget; with no compiler change kept,
the default path is HEAD's.

## 1. Method

- The seed `obx/compiler/seed/obxc.c` is the compiler at HEAD (the last
  compiler change is `eaf2bc55`; nothing under `obx/compiler` changed between
  it and `2120ae02`), so `out/obxc` and a native stage 2 generate the same
  code apart from the prototype.
- Prototypes: patch `x64.obx`/`x64gen.obx`, rebuild `out/obxc` from the seed,
  build stage 2 (`out/obxc main.obx --native -O`), then build every benchmark
  with stage 2. The prototype compiler's own binary is not the measurement;
  the binaries it generates are.
- Binaries: `obxc BENCH.obx --native -O -o NAME`, with
  `OBX_NATIVE_MAP=NAME.map`. Native text has no section headers, so it is
  disassembled with
  `objdump -D -b binary -m i386:x86-64 --adjust-vma=0x400000`; the map file
  names the functions (design/native.md section 4). Profile with
  `perf record -F 999` and resolve sampled IPs through the map file.
- Every number is `taskset -c 2 perf stat -x, -e instructions:u,cycles:u`,
  best of N interleaved. The machine is shared and cycles move 5% to 20%
  between windows: a 25-run `maps` sample spans 677M to 776M cycles (15%).
  Instruction counts repeat to 0.05%; a cycle claim is only made where the
  whole min/median range agrees. `maps` runs set `OBX_HASH_SEED=42` so both
  builds hash the same way.
- Benchmarks as required: `tokens` (`obx/compiler/sema.obx`), `regex \w+`
  (`regex_bench CORPUS 3 words`, about 670k matches), `loop`, `array`,
  `maps`, `sieve`, and the compiler self-build (the native compiler compiling
  `obx/compiler/main.obx --native -O`). Decimal and math cases are used only
  to test an instruction that has no required benchmark.

Baseline at HEAD, core 2, user mode:

| program | instructions (M) | cycles (M) |
|---|---:|---:|
| `fib` | 3642.8 | 1534.1 |
| `loop` | 7000.0 | 1004.0 |
| `array` | 2413.0 | 413.9 |
| `sieve` | 1414.4 | 565.9–567.7 |
| `tokens` | 126.11 | 47.1 |
| `maps` | 2101.8 | 673.6 min, 701.4 median (25 runs) |
| `regex \w+` x3 | 1444.92 | 376.8 |
| compiler self-build | 5556.3 | 3022.7 (noisy) |
| Decimal `dbench M2:tz` | 2489.6 | 563.3 |
| Decimal `dbench M3:big` | 2450.4 | 660.2 |
| math `calls exp` | 250.02 | 47.1 |

### What the backend emits today

Instruction census of the generated-code range of the native compiler built
at HEAD (1,265 user functions, 520,537 static instructions; the range is
between the compact runtime at 0x401000 and the gcc-built libm at 0x66f000):

| category | static count |
|---|---:|
| `shlx`/`shrx`/`sarx`/`rorx`/`mulx`/`andn`/`bzhi`/`lzcnt`/`tzcnt`/`popcnt` | **0** |
| `shl`/`shr`/`sar` with `%cl` (variable count) | 56 |
| `rol` (from `rotl`, x64gen.obx 5263-5287) | 30 |
| `idiv` | 138 |
| `imul` (mostly constant strength-reduced multiplies) | 5,303 |
| `addsd`/`mulsd`/`subsd`/`divsd`/`sqrtsd` | 15 |

The occurrences of BMI/LZCNT/POPCNT anywhere in the binary are all in the
gcc-built runtime and libm (5 `lzcnt`, 5 `tzcnt`, 5 `shlx`, 6 `shrx`, 1
`sarx`, 4 `mulx`, 1 `andn`, 1 `bzhi`), not in generated code.

Hot-function census (static instructions in the whole function):

| function | ins | mixed-integer facts |
|---|---:|---|
| `f32_std_Map_find` (str keys) | 201 | 2 variable shifts, 2 `imul`, 22 conditional branches |
| `f13_std_Map_find` (int keys) | 189 | 2 variable shifts, 1 `imul`, 18 conditional branches |
| `f37_std_sipKeyedStr` | 311 | **30 `rol`**, 1 variable shift, 1 `imul` |
| `tokens scan` | 340 | no shifts or multiplies; 49 conditional branches, 14 `jmp` |
| `regex Dfa_forward` | 675 | no shifts or rotates; 98 conditional branches, 28 `jmp` |

The shape is the point: the hot loops are branchy table walks and memory
accesses. There is very little arithmetic for BMI to replace.

## 2. Feature-by-feature audit

`current` is what the backend emits at HEAD; `candidate` is the v3
instruction. Uop/latency/port data are from uops.info and the AMD Zen 4 SOG
(references at the end); Zen 4 and Haswell figures are both given because the
target is the v3 class.

### 2.1 LZCNT, TZCNT, POPCNT

| | |
|---|---|
| Current | `std.clz64` (std.obx 1626-1635) is a six-step binary search: `if y >> 32 == 0 { n += 32; y <<= 32 }` … `if y >> 63 == 0 { n += 1 }`. About 19 instructions and six conditional branches. |
| Candidate | `lzcnt r64, r64` (1 uop, latency 1, throughput 0.25 on Zen 4, port ALU; p06 on Haswell). `tzcnt` likewise. |
| Where | `clz64` has exactly one caller, `divLong` (std.obx 1644-1652), the Knuth division used only for U256/U128 division with a divisor ≥ 2^64. TZCNT has no source pattern at all: the Decimal “strip trailing zeros” loops (std.obx 963 and 1442) test divisibility by 5 with `(x >> 1) *% INV5`, not trailing zero bits. |
| Measured/estimated | Not hot. In `dbench M3:big` (2.45G instructions, 660M cycles) the top functions are `std.mul128` 51.6% and `divSmall` 10.7%; `clz64` is outside the top 15 (under 1.6% of samples). `M2:tz` spends 8.5% in `makeDec`, but the strip loop is multiply/by-5, not `clz`. Replacing an unexecuted binary search moves nothing. |
| Recommendation | **Do not add an intrinsic.** Add a `clz`/`ctz` builtin only when U256 division is a measured hot spot; then `lzcnt` is worth it (six branches to one uop). |

`popcnt`: the library has no bit-count intrinsic at all (grep finds only the
C runtime's `__builtin_popcountll` over a CPU-set, native/rt.c 2470 and the
rt.obx string at 1674, and gcc already emits `popcnt` there under
`-march=x86-64-v3`). There is no obx code to select it for. Adding a `popcnt`
builtin would be a language feature with no caller; no.

### 2.2 ANDN (BMI1)

| | |
|---|---|
| Current | `a & ~b` is `mov rcx, b; not rcx; and rax, rcx` (the `~` is `E_BNOT`; `pairSrc` cannot name it as a source, so it goes through `rcx`). |
| Candidate | `andn dst, b, a` = `~b & a` (1 uop, latency 1; Zen 4 ALU 0.25/cycle, Haswell p15 0.5/cycle). |
| Where | 19 `& ~` expressions in the library: 17 in the regex files (`regex.obx`, `regex_dfa.obx`, `regex_syntax.obx`) and 2 in `std.Map` (`tagOf`, 1827, and the index update at 1962). The compiler has none. In `std.Map` both sides are computed expressions, so the prototype's “one side is already a register” guard leaves them to `not`+`and`. |
| Prototype | A 30-line selection in `genBin` for `OP_AND` with a direct `E_BNOT` child, guarded to matching widths (`g.size(bnot.ty) >= g.size(c)`; a narrower `~x` is widened, and the one-width `andn` cannot express the top bits). It produces andn for `a & ~b` and `~b & a`, and falls back otherwise. |
| Measured | On a tight synthetic loop (`s = (s +% (a & ~b)) ^ (b & ~a)`, 2 x 10^8 iterations) it removes 13.3% of instructions (3,000.0M to 2,600.0M) and **2.7% of cycles** (1649.6M to 1604.8M, spread under 0.2%). On the required benchmarks it does nothing: `tokens` and `maps` have no `& ~`; the `\w+` DFA hot loops (`Dfa_forward`/`Dfa_backward`) do not contain the pattern (it is in `Cache_next`, a cold cache-miss path), so `regex \w+` stays at 1444.918M instructions. |
| Recommendation | **Not kept.** The instruction is a genuine cycle win where it fires, but nothing the project measures fires it. Keep the prototype in this note; add it, with the width guard, when a real `& ~`-heavy workload appears. |

### 2.3 SHLX / SHRX / SARX (BMI2)

| | |
|---|---|
| Current | A variable shift is `mov rcx, count; cmp rcx, width-1; ja trap; shl/shr/sar rax, cl`. The check is required (a count outside 0..width-1 traps, SPEC section 7.1). The `mov` puts the count where `cl` needs it. |
| Candidate | `shlx rax, rax, count` (1 uop, latency 1, throughput 0.33 on Zen 4, 0.5 on Haswell p06), which names the count in any register and leaves flags alone; the same range check stays. |
| Where | 56 variable shifts in the compiler, 2 per `Map.find` (`home` and `tagOf`, std.obx 1824-1827), a handful in `Map_grow`, `Cse.maskOf`, `num.magDivMod`, and `sipKeyedStr`'s tail. |
| Prototype | Replace `srcRCX` + `shiftCL` with `shx` when the count is already in a register, in `inlineDiv` (checked shifts) and `genBin` (unchecked ones). Saves the `mov rcx, r` (1 instruction) per shift; the check and the shift remain. |
| Measured | `maps` 2101.8M to 2097.4M instructions (-0.20%), cycles unchanged (832.8M against 834.7M in the same window, i.e. noise). Compiler self-build -0.036% instructions, -0.43% cycles (noise). |
| Recommendation | **Not kept.** The saved `mov` is rename-eliminated; there is no execution-port saving and no cycle effect. |

### 2.4 MULX (BMI2)

| | |
|---|---|
| Current | `mul128` (x64gen.obx 5619-5627) is 7 instructions: two `imul` for the cross products, two `mov`s to preserve `a0`/`a1`, one `add`, one `mul r8` (implicit `rax:rdx`), one `add`. |
| Candidate | `mulx high, low, src` (2 uops, latency 3/4, throughput 1.0 on Zen 4; 2 uops p1+p5 on Haswell) computes `rdx * src` into two named registers, without clobbering `rax` or the flags. |
| Where | `mul128` is used by u128 multiply (Decimal mul, `u128` values in user code) and by the checked multiply in `inlineU128`. `std.mul128` (U256) is 51.6% of `dbench M3:big`. |
| Estimate | No win. `mulx` takes one operand implicitly in `rdx`, so `pair128` has to move `a0` from `rax` to `rdx` first; and the cross products still need two `imul`s and the saved `a0`/`a1`. A hand count gives 8 instructions (move `a1` aside, move `a0` to `rdx`, `mulx`, two `imul`, two `add`, move the high word back), one more than now. The multiply unit already has the same 3-cycle latency and 2-uop cost as `mul` on both targets. |
| Recommendation | **Do not implement.** |

### 2.5 RORX (BMI2) and the existing `rol`

| | |
|---|---|
| Current | `rotl` (x64gen.obx 5263-5287) recognises `x << k \| x >> (64-k)` and emits `mov rax, x; rol rax, k` when the local is not already in `rax`. Where it is (the unrolled SipHash rounds on locals), it is already a single `rol`. |
| Candidate | `rorx rax, x, 64-k` (1 uop, latency 1; Zen 4 ALU1/2 0.5/cycle, Haswell p06) writes the rotated value where it is wanted, so the `mov` disappears; it also does not write flags. |
| Where | `std.sipKeyedStr` (std.obx 548-632), the hash of every `str` key: 30 `rol` static, 6 per 8-byte block, in `maps` and in every compiler `Map[str, …]`. Also `std.Sip.round`, which is startup only. |
| Prototype | `rotl` returns the matched local node, and `genBin` emits `rorx` when the local is in a register other than `rax`, else the existing `rol`. 25 lines, including the encoder. |
| Measured | Correctness first: the first version used the wrong tree node and produced a different SipHash (caught by comparing `sipHash13` output with the C build; the compiler then failed with `std.obx:1525: unknown type U256`). After fixing that and the VEX high-register encoding: `maps` instructions 2101.8M to 1983.4M (**-5.60%**) — the largest instruction-count win in this audit — but cycles are not moved: over 25 interleaved runs, `maps` best 677.3M against 659.2M (-2.7%), median 701.4M against 698.0M (-0.5%); an earlier 15-run window had the base best (673.6M) below the prototype (682.9M). Spread is 15%. Compiler self-build: -0.41% instructions, +0.50% cycles. `tokens`, `loop`, `regex` unchanged (regex has 30 `rorx` static but they are not in the hot DFA loops). |
| Recommendation | **Not kept.** 5.6% of `maps`'s instructions are the rename-eliminated `mov`s (Agner: an eliminated `mov` is zero latency and uses no execution port, but still takes decode bandwidth). At `maps`'s 3 IPC the 6-wide front end is not the bottleneck, so the cycles do not follow. The best-of-N cycle numbers straddle zero; this is exactly the bool-folding lesson (`HISTORY.md`): instructions agree in sign, cycles do not. It is the first ISA selection to add if the project ever optimises for code size or a narrower front end. |

### 2.6 VEX scalar float and FMA3

| | |
|---|---|
| Current | `addsd`/`mulsd`/`subsd`/`divsd`/`sqrtsd` are legacy two-operand SSE (`x64.obx` `sse`/`sseM`). |
| Candidate | `vaddsd xd, xs2, xs3` etc. (VEX, 3 operands; the same 1 uop, 3-cycle latency as the legacy form on Zen 4 and Haswell, but the destination is independent and the upper YMM bits are zeroed). |
| Where | Only 15 static arithmetic SSE instructions in the whole compiler, plus the math benchmark and user float code. Every call site has the accumulator in the destination (`pairF` puts the left operand in `xmm0`, `sseSrc` adds into it), so `xd` is already `xs2`: the encoding change breaks no false dependency and the 3-operand form has nothing extra to name. |
| Measured | Swapping all scalar arithmetic to VEX (including memory forms): `math calls exp` 250.024M to 250.004M instructions (-0.008%), 47.13M to 47.48M cycles (+0.75%); `log` +0.40% cycles; `sin` -0.13%. The code is one byte longer per instruction and cycles are if anything worse. |
| FMA3 | Already used: `genBin` maps the language's `fma(x, y, z)` to `vfmadd213sd` (x64gen.obx 5926-5936), and `std.fma` is the extern; no other contraction is legal because the language (and the C backend's `-ffp-contract=off`) requires separate rounding. Nothing to add. |
| Recommendation | **Not kept.** `HISTORY.md` already measured the legacy/VEX mix as neutral; this confirms it. |

### 2.7 BZHI and AVX2 copies

`bzhi` (zero high bits from a bit index; 1 uop ALU on Zen 4, p15 on Haswell)
has no source pattern: the language traps a shift count outside the width, so
there is no `x & ((1 << n) - 1)` mask to fold. Grep over `obx/lib` found only
`float(1 << s)` conversions in the database adapters, which are constant
shifts. **No.**

32-byte AVX2 copies have a measured reason to stay out: the generated
`copyMem` (x64gen.obx 3324-3353) uses 16-byte `movdqu` only for array
elements that were written long before, and 8-byte pieces for locals and
parameters, because a 16-byte load of two just-written 8-byte stores cannot be
store-forwarded (a ~12-cycle stall; `HISTORY.md`, “Native Decimal”). The C
runtime is built with `-mmove-max=128 -mstore-max=128` for the same reason
(main.obx 155-160); the C Decimal add was 1.4x the cycles with 32-byte AVX
copies. No required benchmark copies 32-byte records out of arrays in a hot
loop. **No**, and the existing 16/8 split is deliberate.

## 3. Placement and shape

All numbers are core 2, best of 5–9 interleaved; instructions are unchanged
unless stated.

### 3.1 Function alignment (`OBX_FALIGN`, default 64)

| cycles (M) | 16 | 32 | 64 | 128 |
|---|---:|---:|---:|---:|
| `fib` | 1689.7 | 1524.1 | 1523.8 | 1523.9 |
| `loop` | 1004.0 | 1005.2 | 1003.5 | 1004.7 |
| `array` | 414.3 | 414.2 | 415.0 | 415.2 |
| `sieve` | 586.1 | 577.2 | 577.6 | 588.3 |

`fib` reproduces the known 10% sensitivity (64 keeps the small recursive
function's leaf path in its fetch block); the others are within the 1–2%
noise. 64 is the right default; nothing to change.

### 3.2 Loop alignment (`OBX_LALIGN`, default 16)

A prototype read the loop-top alignment from the environment in `placeCode`
(the same padding and 64-byte inner-loop rule, with the alignment
parameterised).

| cycles (M) | 16 | 32 | 64 |
|---|---:|---:|---:|
| `loop` | 1005.1 | 1005.1 | 1004.0 |
| `array` | 413.9 | 412.3 | 412.0 |
| `tokens` | 47.25 | 47.35 | 47.75 |
| `sieve` | 537.6 | 575.1 | 587.9 (unusable: the window moved) |

There is no consistent direction; `tokens` prefers 16, `array` 64 by 0.5%,
`loop` is flat at one cycle an iteration. Increasing the alignment only adds
int3/nop padding (the compiler is 3 MB). **Keep 16.**

### 3.3 Code placement (`OBX_PADB`, 0..56 bytes before each function)

`loop`: min 1002.8M to 1004.0M cycles across eight placements (0.12%
spread). `tokens`: min 46.7M to 47.3M (1.3%), with the medians in the
opposite order to the minima. With `FUNC_ALIGN=64` these two are stable; the
earlier 10–15% placement sensitivity is specific to `fib`'s 4-instruction
leaf path and is why 64 is the default.

### 3.4 Does the `lea` selection compete for AGU/ALU ports?

No. On Zen 4, two-operand LEA is one single-cycle macro-op in the ALUs, and
three-operand LEA is two macro-ops in the ALUs (Zen 4 SOG 57647, section
2.10.1); AGUs are only for load/store addresses (three AGUs: two loads, one
store). On Haswell, simple LEA goes to p1/p5 (ALU), not the AGUs. The `lea`
selection from `bbcb32f1` replaces `mov`+`add`/`sub` (or `mov`+small `imul`)
with one ALU op, and the moved `mov` was rename-eliminated anyway; it does not
compete with the three AGUs that the token/DFA/Map load-store loops need.
Measured: `loop` is 1.00 cycle an iteration before and after; `fib` gained
9.8% because it removed two instructions from the call chain. There is no
port conflict to fix.

### 3.5 Leaf frames and the red zone

Of 1,265 generated functions in the compiler, 19 contain no `call`, and all
19 still begin `push rbp; mov rbp, rsp` (the largest are
`syntax.sym2` 167 instructions, `fs.kindOfMode` 151, `loops.inKind` 111). The
frame pointer costs 2 instructions in the prologue and `leave` in the
epilogue per call. Removing it means addressing the frame off `rsp` (or a
caller-saved base) instead of `rbp`, because `rbp` is callee-saved; that is a
`genFunc`/`epilogue` change of 100–250 lines and it touches every
`rbp(slot)` use. `genGuards` already shrink-wraps the early-exit path
(`fib`'s leaf is 4 instructions). Not prototyped: it is not an ISA feature
and the payoff is call-heavy small functions, the same item `codegen-audit.md`
ranked 3. The allocator functions were left alone as required.

## 4. What is not worth doing, and why

- **LZCNT/TZCNT/POPCNT/BZHI builtins**: no hot source. `clz64` is the only
  clz and is called from U256 long division, which is not a hot path in the
  Decimal cases that use division; there is no tzcnt/popcnt/bzhi source at
  all. A builtin would be dead code.
- **ANDN** in the hot regex DFA: the pattern is in `Cache_next`, not the
  byte loops; the width promotion rules (`~u32` widened to 64 bits) make the
  unsound cases common. The synthetic win is real, the library does not have
  the shape.
- **SHLX/SHRX/SARX**: removes a rename-eliminated `mov`; no port or cycle.
- **MULX**: no saving over `mul` plus the cross-product `imul`s; one operand
  is implicitly `rdx`, which costs a move.
- **RORX**: the biggest instruction-count win (-5.6% `maps`) and still no
  reliable cycle win; the removed `mov` is free.
- **VEX scalar float**: every site already has the accumulator in the
  destination; measured slightly worse.
- **32-byte copies**: store forwarding, already measured and reverted in
  `HISTORY.md`; the 16-byte-only-for-array-elements rule is correct.
- **Loop alignment**: no consistent direction across benchmarks.
- **Popcnt/AVX2/FMA**: FMA already selected; the others have no callers.

## 5. Ranked short list

1. **No compiler change from this audit.** The tree is `2120ae02` plus this
   note. Nothing met the gate (≥1% cycles on two benchmarks or ≥2% on one
   application, no benchmark >1% worse).
2. If instruction count or code size ever becomes a goal: **`rorx` for
   `rotl`** (25 lines) is the largest measured reduction, -5.60% on `maps`
   and -0.41% on the compiler self-build, with no cycle cost and no
   benchmark above noise. It is a front-end win, so expect it to show only
   on a narrower core or a decode-bound workload.
3. If a real `a & ~b`-heavy loop appears (bit masks, flag tests):
   **`andn`** with the width guard. Measured -2.7% cycles on a tight ALU
   loop; no current benchmark fires it.
4. If U256 division becomes hot: `lzcnt` for `std.clz64` (six branches to
   one uop). Do not add it before then.
5. The real remaining levers are not in this table: destination-directed
   arithmetic and `staticMem` addressing modes, boolean/branch folding (the
   measured change reached tokens only -0.86% cycles), leaf frames /
   shrink-wrapping (19 leaf functions), and the allocator. `codegen-audit.md`
   ranks them; this audit adds no ISA argument for any of them.

## 6. Reproducing

    D=/tmp/microarch
    # baseline: HEAD's seed builds the compiler, which builds the benchmarks
    obx/compiler/build.sh
    obx/compiler/out/obxc obx/compiler/main.obx --native -O -o $D/obxc
    for n in fib loop array maps sieve tokens; do
      OBX_NATIVE_MAP=$D/$n.map obx/compiler/out/obxc obx/bench/$n.obx --native -O -o $D/${n}_nO
    done
    OBX_NATIVE_MAP=$D/regex.map obx/compiler/out/obxc \
      obx/bench/regex/regex_bench.obx --native -O -o $D/regex_nO
    python3 obx/bench/regex/gen_corpus.py $D/corpus.txt
    # measure (best of N, interleaved); maps needs the fixed seed
    OBX_HASH_SEED=42 taskset -c 2 perf stat -x, -e instructions:u,cycles:u $D/maps_nO
    taskset -c 2 perf stat -x, -e instructions:u,cycles:u $D/tokens_nO obx/compiler/sema.obx
    taskset -c 2 perf stat -x, -e instructions:u,cycles:u $D/regex_nO $D/corpus.txt 3 words
    # self-build cost
    cd obx/compiler && OBX_LIB=../lib taskset -c 2 perf stat -x, \
      -e instructions:u,cycles:u $D/obxc main.obx --native -O -o $D/out
    # placement
    for p in 0 8 16 24 32 40 48 56; do
      OBX_PADB=$p obx/compiler/out/obxc obx/bench/loop.obx --native -O -o $D/loop_p$p
    done
    for a in 16 32 64 128; do
      OBX_FALIGN=$a obx/compiler/out/obxc obx/bench/fib.obx --native -O -o $D/fib_f$a
    done

The prototypes are not in the tree. The `rorx` one is: change `rotl` to
return `Rot{k, x}` (the shift and the local's node), use
`g.regOf(rk.x)` in `genBin` and emit
`rorx 8, RAX, rx, 64 - rk.k` when `rx >= 0 && rx != RAX`; the encoder is
VEX.LZ.F2.0F3A.W1 F0 /r ib (`C4`, `0x40 | (~dst>>3)<<7 | (~src>>3)<<5 | 3`,
`0xFB`, `0xF0`, ModRM, imm) — the high bits of the ModRM.rm register are
VEX.B, which the first version got wrong and the SipHash/`U256` check caught.
The `andn` one is a guarded `E_BNOT` arm in `genBin`; the `shx` one replaces
`srcRCX`+`shiftCL` with VEX.NDS.66/F2/F3.0F38.W1 F7 (`C4`,
`0x40 | (~dst>>3)<<7 | (~src>>3)<<5 | 2`, `0x80 | (~cnt&15)<<3 | pp`, `0xF7`,
ModRM), pp 1/3/2 for SHLX/SHRX/SARX.

## References

- AMD, *Software Optimization Guide for the AMD Zen 4 Microarchitecture*,
  publication 57647, rev. 1.00 (April 2023): 6-macro-op dispatch, 4 ALUs and
  3 AGUs, section 2.10.1 (two-operand LEA is one macro-op in the ALUs,
  three-operand LEA is two; the integer multiply is 3 cycles, an extra cycle
  for the second destination).
- AMD, *Ryzen Processor Software Optimization* (GDC 2023/2024): Zen 4
  cache/op-cache table (6.75K ops, 32K L1I/L1D, 1M L2), 6 macro-ops/cycle,
  3 loads / 2 stores; the SSE/AVX transition penalty note.
- Agner Fog, *The microarchitecture of Intel, AMD and VIA CPUs*, sections
  9.8/11.8 “Elimination of move instructions”: a register-to-register move
  is eliminated at rename, zero latency and no execution port, but still
  consumes decoder bandwidth; and *Instruction tables* (MOV r,r 1 op;
  SHLX/RORX 1 op; LEA r,m 1 op in the ALU).
- uops.info: `SHLX R64,R64,R64` (Zen 4 1 uop, latency 1, 0.33/cycle; Haswell
  1 uop p06, 0.5/cycle), `RORX` (Zen 4 ALU1/2 0.5; Haswell p06),
  `ANDN` (Zen 4 ALU 0.25; Haswell p15), `BZHI` (Zen 4 ALU1/2; Haswell p15),
  `LZCNT` (Zen 4 ALU, 1 uop, 0.25/cycle), `MULX` (Zen 4 2 uops, latency
  3/4, 1.0/cycle; Haswell 2 uops p1+p5), `MUL R64` (Zen 4 2 uops, 1.0),
  `ADDSD` (Zen 4 1 uop, latency 3).
- Intel, *64 and IA-32 Architectures Optimization Reference Manual*,
  section 3.4.1.5 “Code Alignment”: branch targets and hot loops on
  16/32-byte boundaries; modern cores with a uop cache care about 32-byte
  fetch blocks, which is why 64-byte function alignment and the 16-byte loop
  tops are checked here rather than assumed.
