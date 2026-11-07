# Explicit SIMD for obx: measured ceiling, minimal extension, cost

Status: research note and prototype, 2026-11-07, branch `simd-design` based on
`7fc83733`. This turns the "explicit SIMD rather than automatic vectorization"
proposal of [small-fast-compiler.md](small-fast-compiler.md) into a concrete
design. It does not change the language spec and does not change the default
compiler path: the prototype's x86-64 encoder additions live on branch
`simd-design` at `4ead14e4` (not merged, since they are unreachable from the
language and would only churn the seed); this tree holds the note and the
instruction-sequence harnesses in `bench/simd/`. The language surface, IR and
x64gen lowering are a plan, not implemented code.

**Recommendation in one line: do not build an automatic vectorizer; add a
deliberately small explicit SIMD extension (`f64x4`, `i64x4`, `i32x8`, with
loads/stores, element-wise arithmetic, reductions and masks) in two stages, about
1,600 lines for the first stage, native-first and also printed by the C backend.
It captures 4–5x on compute-bound numeric loops and ~2x on bandwidth-bound array
loops, and nothing on tokenizing, strings, allocation or the sieve's marking — so
it should be sold as a numeric/systems extension, not a general speedup.**

## 1. Method

All measurements:

- pinned to **core 8** with `taskset -c 8`, best of 3, the candidates of a
  workload **interleaved** (forward, reverse, forward);
- `perf stat -e instructions:u,cycles:u` (user mode only: the runtime's syscalls
  and startup are outside the interesting code);
- best of 3 by cycles; instruction counts are deterministic and did not vary;
- the machine is an AMD Ryzen 7 8745HS (Zen 4, 8 cores / 16 threads, 32 KiB L1d
  and 1 MiB L2 per core, 16 MiB L3), under WSL2. Other work on the machine uses
  cores 0, 2, 4 and 6; cycles still vary by up to 20% between sessions. Every
  table below is one interleaved session, so its ratios are comparable; the
  instruction counts are the stable part.

Variants:

| label | build |
|---|---|
| scalar C | `gcc -O2 -fno-tree-vectorize -fno-optimize-sibling-calls` |
| auto-vec C | `gcc -O2 -march=x86-64-v3 -fno-optimize-sibling-calls` (GCC 13 vectorises at -O2) |
| hand AVX2 | `gcc -O2 -march=x86-64-v3`, intrinsics (`<immintrin.h>`), FMA where useful |
| native obx -O | `obxc file.obx --native -O` (the compiler's own optimal path) |

The C references for the scalar loops are the existing, semantically matched
`obx/bench/c/*.c`; the hand versions and the dot product are in
[`../bench/simd/`](../bench/simd/), which has the runner:

    python3 obx/bench/simd/run.py [--only NAME ...] [--reps 3] [--core 8]

The scalar C and auto-vec C builds of `array`, `loop`, `sieve`, `tokens` and
`strings` are the same source (the obx benchmark's C reference), so the only
difference is the vectorizer. The hand versions change only the inner loop.
The dot scalar row also uses `-ffp-contract=off`; the auto-vec and hand rows use
FMA (the hand version explicitly), so the dot speedup includes both 4-wide SIMD
and FMA. A hand version without FMA measured 262.9M instructions and the same
cycles as the FMA version in a controlled run: the ~5x is the 4-wide SIMD, not
FMA; FMA saves 25% of the instructions and shortens the dependency chain.

## 2. Measured ceiling

Cycles and instruction counts are in millions (Mcyc / Minstr). The parenthesised
number is cycles relative to scalar C: above 1 is faster.

| workload | scalar C | auto-vec C (AVX2) | hand AVX2 | native obx -O |
|---|---:|---:|---:|---:|
| `array` (1M int64, 200 rounds of `a[i]+=r; total+=a[i]`) | 218.3 / 1407.1 | 103.8 / 307.1 (2.10x) | 106.2 / 307.1 (2.06x) | 422.2 / 2413.0 (0.52x) |
| `loop` (1e9 iterations of `s += i*2`, asm barrier) | 1021.8 / 4000.1 | 1015.4 / 4000.1 (1.01x) | 252.4 / 1250.1 (4.05x) | 1010.6 / 8000.0 (1.01x) |
| `sieve` (10M, 10 rounds) | 1063.4 / 1414.4 | 1044.2 / 1414.4 (1.02x) | 879.5 / 933.1 (1.21x) | 1222.5 / 1414.4 (0.87x) |
| `tokens` (scan+intern `compiler/sema.obx`, 10 rounds) | 40.4 / 90.6 | 43.1 / 90.8 (0.94x) | — | 48.7 / 126.1 (0.83x) |
| `strings` (200 rounds of concatenation) | 446.6 / 1620.3 | 450.4 / 1620.3 (0.99x) | — | 205.4 / 931.3 (2.17x) |
| `dot` (65536 doubles, 4000 rounds, FMA) | 876.3 / 1573.7 | 200.4 / 459.4 (4.37x) | 169.4 / 197.4 (5.17x) | 875.5 / 3672.6 (1.00x) |

`—` means there is no honest hand-vectorised version: those workloads have
nothing to vectorise (section 2.2).

### 2.1 What the wins are

- **Dot product: about 5x (4.8–5.2x across sessions).** The scalar loop has a
  serial `s = s + a[i]*b[i]` chain (multiply latency + add latency per element);
  four FMA accumulators give four independent chains and 4 lanes each, and the
  hand version runs at about 0.65 cycles per FMA. This is the clearest case for
  explicit SIMD.
- **Tight integer reduction: 4.05x.** The scalar loop is one cycle per iteration;
  four int64 lanes in one vector make four iterations per vector add. The
  instruction count falls exactly 4x (4000M to 1250M). Auto-vectorisation cannot
  help here because the benchmark's empty asm keeps `s` live across the
  iteration; a hand vector version with the same barrier can.
- **8 MB array element-wise + reduction: about 2.1x, not 4.6x.** The instruction
  count falls 4.6x (1407M to 307M), but the loop reads and writes 8 MB per round
  and is limited by L3 bandwidth: cycles fall only about 2.1x. This is the
  realistic ceiling for large arrays. With a smaller array the compute part
  dominates and the speedup approaches 4x.
- **Sieve: 1.18–1.21x at best.** The marking loop is a strided scatter (`prime[j]
  = false; j += i`); AVX2 has no scatter and the branch is data-dependent. Only
  the final "count the true bytes" loop vectorises (`sad_epu8`), and it is a
  small part of the time. The hand version reduces instructions by 34% and
  cycles by about 20%; the marking loop bounds the result (Amdahl).
- **Native obx is already competitive on `loop` and `dot`** (1.01x and 1.00x of
  scalar C), despite 2x the instructions on `loop` and 2.3x on `dot`: its bounds
  checks and loop bookkeeping issue in parallel with the dependency chain. On
  `array` it is 0.52x of scalar C because each element carries a bounds check
  that the C reference does not; SIMD amortises one check over four or eight
  elements. On `strings` it is 2.0–2.2x *faster* than C (the runtime's
  size-class allocator), which no SIMD work can improve.

### 2.2 Where vectorisation is impossible or unprofitable

- **`tokens`:** byte-at-a-time branching (`isLetter`/`isDigit`), `malloc` per
  identifier, and a serial djb2-style hash `h = h*33 + byte` — a loop-carried
  dependency with no independent lanes. GCC's auto-vectoriser changes nothing
  (90.6M vs 90.8M instructions; 0.94–0.99x cycles across sessions), and a hand
  SIMD classifier would only move work into the same branchy scanner. This is
  exactly the category the design must not promise.
- **`strings`:** allocation, reference counting and `snprintf`-style conversion;
  the bytes are short. The C reference's `strlen`/`memcpy` are already vectorised
  inside libc. Auto-vectorisation changes nothing (1620.3M instructions both
  ways, 0.99–1.00x); native obx wins 2x through the allocator, not through SIMD.
- **Sieve marking:** strided stores and branches; AVX2 has no scatter. The count
  loop is vectorisable but only a sixth of the work.
- **Pointer chasing, records, lists, trees, maps, GC/allocation:** no contiguous
  independent lanes. A vector load of pointers does not help following them.
- **Large arrays:** when the working set exceeds L3, bandwidth, not instruction
  count, is the limit; SIMD's 4x instruction reduction becomes ~2x cycles (the
  `array` row) and can become 1x at DRAM bandwidth.

The honest summary: on this six-workload sample the geometric mean of hand AVX2
over scalar C is about 1.9x, but that number is carried by two of six workloads
(4.05x and 5.17x). The design should target those, not claim a broad speedup.

### 2.3 The compiler-generated sequence reaches the ceiling

The prototype (section 7) writes the exact x86-64 sequences that x64gen would
emit for a 16-double, four-accumulator dot product, with 1, 4 or 8 vector bounds
checks per iteration:

| variant | instructions (M) | cycles (M) | vs scalar C |
|---|---:|---:|---:|
| scalar C | 1573.7 | 881.3 | 1.00x |
| hand AVX2+FMA | 197.4 | 174.4 | 5.05x |
| x64gen sequence, 1 check | 279.3 | 177.3 | 4.97x |
| x64gen sequence, 4 checks | 426.8 | 183.4 | 4.81x |
| x64gen sequence, 8 checks | 607.0 | 181.0 | 4.87x |

All four vector versions are within measurement noise of each other in cycles
(174–183M): the checks add 80M–410M instructions but issue in the spare slots of
a loop limited by the four FMA chains and the loads. This is the key result for
the design: **one checked `vload` per vector (2 instructions) is affordable; a
bounds check does not eat the SIMD win on a compute-bound loop.** On a
bandwidth-bound array it costs instructions but little time as well (section 7).

The integer array sequence, also in the prototype:

| variant | instructions (M) | cycles (M) | vs scalar C |
|---|---:|---:|---:|
| scalar C | 1407.1 | 248.8 | 1.00x |
| hand AVX2 | 307.1 | 108.0 | 2.30x |
| x64gen sequence, 1 check | 457.1 | 117.7 | 2.11x |
| x64gen sequence, no check | 357.1 | 125.2 | 1.99x |

The checked sequence is within the hand ceiling's range across sessions: 117.7M
cycles here against 108.0M hand and 248.8M scalar C. Under external load the
absolute cycles move by up to 2x but the instruction counts and the ordering do
not. The check costs about 100M instructions (0.5 per element) and roughly
5–10% of the cycles in a quiet session (more when the machine is loaded); the
no-check variant shows the upside of a future fact pass that proves the
loop-bound check.

## 3. The minimal language surface

### 3.1 Types

Three vector types cover every measured win:

| type | lanes | element | bytes | x86-64-v3 register |
|---|---:|---|---:|---|
| `f64x4` | 4 | `float` (f64) | 32 | `ymm` |
| `i64x4` | 4 | `int` (i64) | 32 | `ymm` |
| `i32x8` | 8 | `i32` | 32 | `ymm` |

They are new primitive types (not `Vec[T,N]`: the language has no const
generics, and a type constructor would add inference, layout and ABI rules for no
benefit). They are copy types, like `float` and `int`; no drop/dup glue.

Deliberately not in the minimal set:

- **`f32x8`**: the language has no `f32` scalar type; adding one is a separate
  language change. If `f32` is added later, `f32x8` is a new row in the type
  table and the same ops with `ps` instructions — cheap, but not needed for the
  measured wins (the dot product is f64 because that is what obx has).
- **`u8x32`**: byte scanning (`tokens`) is branchy and serial; no measured win.
- **128-bit (`f64x2`, `i64x2`)**: the throughput case is 256-bit; 128-bit forms
  can be added with the same encoder work later if a 2-lane algorithm wants them.
- **`f64x8`/512-bit**: AVX-512 is not in x86-64-v3; the target is v3.

An integer vector of the same width is the mask type of a comparison:
`f64x4` compares to `i64x4`, `i64x4` to `i64x4`, `i32x8` to `i32x8`. A mask lane
is all ones (true) or zero. This avoids a separate mask type and maps directly to
AVX2's compare results.

### 3.2 Operations

Builtins (prelude names; they need the expected-type mechanism, so they are
compiler builtins rather than library functions):

```
vzero()                    -> T          // the expected vector type
vbroadcast(x)              -> T          // x: the element type
vload(p, i)                -> T          // p: array/slice place, i: int
vstore(p, i, v)            -> ()         // p: mutable array/slice place
vsum(v)                    -> E          // E: the element type
vmin(v), vmax(v)           -> E
vfmadd(a, b, c)            -> T          // f64x4 only, explicit fused multiply-add
vselect(m, a, b)           -> T          // m: the same-width integer mask, a/b: T
vany(m), vall(m)           -> bool
vlane(v, k)                -> E          // k a constant, stage 3
vwithLane(v, k, x)         -> T          // stage 3
vzipLo(a, b), vzipHi(a, b) -> T          // stage 3
vswapHalves(v)             -> T          // stage 3
```

Operators on two vectors of the same type:

| operator | `f64x4` | `i64x4` | `i32x8` | result |
|---|---|---|---|---|
| `+ - *` | IEEE, per lane | — | — | vector |
| `/` | IEEE, per lane | — | — | vector |
| `+% -% *%` | — | wrapping | wrapping | vector |
| `& \| ^ ~` | — | yes | yes | vector |
| `== != < <= > >=` | yes | yes | yes | mask vector |

Integer vector arithmetic **wraps**, and is spelled with the language's existing
wrapping operators `+% -% *%`; plain `+ - *` on an integer vector is a compile
error ("use `+%`"). Per-lane checked arithmetic would need a compare, a mask and
a branch per operation, which defeats the purpose; requiring the explicit form
keeps the language's checked-arithmetic rule visible in the source. A program
that wants a check can write it with a comparison and `vany` (unsigned add
overflow: `vany(sum < a)`). There is no integer `/` or `%` (AVX2 has no vector
integer divide); a library can provide one. `i64x4 *%` has no AVX2 instruction
(`vpmullq` is AVX-512): the surface defines it, stage 1 rejects it, and stage 3
synthesises it from three `vpmuludq` plus shifts and adds. `i32x8 *%` is one
`vpmulld`.

Floating-point ops are per-lane IEEE, with **no reassociation** by the compiler.
`vfmadd` is explicit because fusing `a*b + c` changes the rounding; the language
already has a scalar `fma` in `math`, so this is the same rule. `vsum`/`vmin`/
`vmax` define their reduction order (section 3.4): a tree, not a left-to-right
scalar loop, and the difference is documented.

No implicit broadcast in operators: `v + 1` is a type error; write
`v +% vbroadcast(1)`. This keeps the checker's rules trivial (operands of the
same type, as everywhere else).

### 3.3 Loads, stores, bounds, alignment, borrowing

`vload(p, i)` reads `lanes` elements of `p` starting at `i`; `vstore(p, i, v)`
writes them. Both are **checked**: `0 <= i` and `i + lanes <= len(p)`, else exit
3, like `p[i]`. The check is one per vector, not one per element.

- `p` is an array place (`[]T`), a slice (`&[T]`), or a `mut &[T]`. The checker
  treats `vload`/`vstore` like indexing `p[i]`: the address is computed first,
  then the value, then the store, so `vstore(a, i, vload(a, j) +% vr)` is the
  same as `a[i] = a[j] + r` and is allowed. They are not ordinary calls taking
  borrows; otherwise the existing borrow rule would reject that expression.
- `vstore` needs a mutable place, exactly as `p[i] = v` does.
- **No alignment requirement**: the load is `vmovupd`/`vmovdqu`, which accepts
  any address. The programmer cannot observe a vector's alignment in stage 1
  because `&v` is not allowed. The cost of unaligned access is a cache-line split
  when it happens; the programmer can align arrays for speed but not for
  correctness.
- **Aliasing**: group borrowing already rules out overlapping mutable slices
  passed to one call. Vector accesses are emitted in program order and are not
  reordered across stores or calls, so no new alias analysis is needed. The only
  vector peephole is FMA fusion, which combines pure register arithmetic.
- No gather and no scatter. Data must be contiguous per vector; AoS layouts use
  the stage-3 shuffles. AVX2 `vpgatherdd` is slow and is not exposed.
- No vector fields in records, no arrays of vectors, no `&vector`, no vector in a
  generic type argument in stage 1. These need layout/ABI rules and are stage 4.
  Vector parameters and results are allowed (section 5).

### 3.4 Reduction order

`vsum(v)` for `f64x4` is defined as `(v0 + v2) + (v1 + v3)` — the sequence
`vextractf128; vaddpd; vunpckhpd; vaddsd` that x64gen emits. For `i64x4` it is
the same tree with `vpaddq`; for `i32x8` the tree of 8 lanes corresponding to the
target sequence. This is deterministic and documented, so a native/C difference
is a compiler bug. It is not the same value as a scalar left-to-right sum; that
is the price of the horizontal reduction and must be in the spec.

`vmin`/`vmax` are order-independent. Integer `vsum` wraps, like the element-wise
integer operators; a checked sum is built from the same pieces (add with a
carry/overflow mask and `vany`) or by summing in a wider lane layout. The usual
numeric code knows its range or wants the wrapping form.

### 3.5 Examples

```obx
// dot product: the workload of section 2
fn dot(a: &[float], b: &[float]): float {
    var acc: f64x4 = vzero()
    var i = 0
    while i + 4 <= len(a) {
        let va: f64x4 = vload(a, i)
        let vb: f64x4 = vload(b, i)
        acc = vfmadd(va, vb, acc)
        i += 4
    }
    var r = vsum(acc)
    while i < len(a) {
        r = r + a[i] * b[i]
        i += 1
    }
    return r
}
```

```obx
// a[i] = a[i] + r, the array benchmark's inner loop
fn addScaled(xs: mut &[int], r: int) {
    let vr: i64x4 = vbroadcast(r)
    var i = 0
    while i + 4 <= len(xs) {
        let v: i64x4 = vload(xs, i)
        vstore(xs, i, v +% vr)
        i += 4
    }
    while i < len(xs) {
        xs[i] = xs[i] + r
        i += 1
    }
}
```

```obx
// clamp, once masks exist (stage 2)
fn clamp(xs: mut &[float], lo: float, hi: float) {
    let vlo: f64x4 = vbroadcast(lo)
    let vhi: f64x4 = vbroadcast(hi)
    var i = 0
    while i + 4 <= len(xs) {
        let v: f64x4 = vload(xs, i)
        let below: i64x4 = v < vlo
        let above: i64x4 = v > vhi
        let c: f64x4 = vselect(below, vlo, v)
        vstore(xs, i, vselect(above, vhi, c))
        i += 4
    }
    while i < len(xs) {
        if xs[i] < lo { xs[i] = lo }
        if xs[i] > hi { xs[i] = hi }
        i += 1
    }
}
```

### 3.6 Alternatives considered

- **A parallel array type / `Vec[T,N]` with const generics**: more type-system
  work (const parameters, inference, layout) for the same machine code. Rejected.
- **Methods (`v.add(w)`, `v.load(s, i)`) instead of builtins**: the language's
  operators on non-primitives are method calls; making vectors primitive types
  with built-in operators is smaller in `check` and `lower` (the existing
  `binop` already dispatches on a primitive kind). Methods would need a method
  table per vector type and receiver-borrow rules. Rejected.
- **Raw intrinsics in a library** (`vaddpd`, `vperm2f128`, ...): exposes VEX
  encodings and immediates, is target-specific, and every value still needs the
  vector type. The named, portable builtins are the surface; the intrinsics are
  the lowering.
- **Vector values as small value records**: no new type kind, but every op goes
  through memory (load/store per operation) and cannot use ymm registers; the
  measured ceiling would be lost. Rejected.

## 4. Lowering to the IR

The existing IR is the right seam: add one type kind and one expression kind,
and reuse `E_BIN` for all element-wise arithmetic and comparisons.

### 4.1 Types and nodes

```
TY_VEC = 17                       // after TY_FN
Ty{k: TY_VEC, size: elem.size * lanes, align: size, base: elem, n: lanes, sid: -1}

E_VECOP = 25                      // one new expression kind
    v: the opcode (V_LOAD, V_STORE, V_SPLAT, V_ZERO, V_SUM, V_MIN, V_MAX,
                   V_SELECT, V_ANY, V_ALL, V_EXTRACT, V_INSERT, V_PERM, V_FMADD)
    ty: the result type (the vector, or the element for a reduction)
    a, b, c: operands
KIDS[E_VECOP] = K_ABC

// element-wise: E_BIN(OP_ADD, vecty, a, b)      (c = the operand vector type)
// comparison:    E_BIN(OP_LT, maskty, a, b)     (ty = mask, c = operand vector)
```

A vector `E_BIN` has `ty = c =` the vector type; a comparison has `ty` = the mask
vector and `c` = the operand vector. Existing walks (`opt`, `loops`, `cse`) treat
it as any other binary node; they need only know that a vector value is not a
scalar for their value records (the `isAggr`/`isScalar` predicates). `opt` must
not inline a function in a way that splits a vector value; the usual rule that
records are not split applies. Stage 1 can simply make `opt` and `loops` leave
functions containing `E_VECOP` alone (a one-line guard in each pass), which is
the smallest safe choice; vector loops are the ones the programmer wrote, not the
ones the loop pass needs to rewrite.

`TY_VEC` is not `isAggr` (it does not live in memory by rule) and not `isArith`
(no implicit conversions). Add `isVec(t)`; leave `isScalar` false so no existing
integer/float path silently accepts a vector. Type identity is structural on
`(base, n)`, so `ptrTo` etc. work; `typeName` prints `f64x4` (or the C typedef for
`cgen`).

### 4.2 Lowering a load and a store

For `vload(p, i)` with element type `E`, lanes `L`, and `p`'s data pointer `d` and
length `n` (the array header / slice fields that lower already reads for `p[i]`):

```
limit = E_BIN(OP_SUB, TY_I64, n, E_INT(L - 1))     // n >= 0, no overflow
idx   = E_CALL(rt_idx, [i, limit, where])           // the existing runtime check
addr  = E_PADD(d, idx, sizeof(E))                   // d: the data pointer
load  = E_VECOP(V_LOAD, vecty, addr, -1, -1)
```

`rt_idx(i, limit)` traps unless `0 <= i < limit`, i.e. `i + L <= n`. It is the
same helper scalar indexing uses, with the same message and exit code, so there
is no new runtime function and the existing inline lowering (`cmp i, limit;
jae trap`) and the facts pass apply. Nothing underflows: `n >= 0` and `L <= 32`.

`vstore(p, i, v)` is the same with `V_STORE` (`ty = void`, `b = v`).

Because the check and the address are ordinary IR, the existing `loops.obx`
facts can (in a later step) prove the check from a loop condition written as
`i + 4 <= n` or `i < n - 3`; the prototype measured both the checked and
unchecked sequences (section 2.3) and the check is cheap even when it stays.

### 4.3 Instruction selection

| IR | x86-64-v3 |
|---|---|
| `V_LOAD` f64x4 | `vmovupd ymm0, [rax]` |
| `V_LOAD` i64x4 / i32x8 | `vmovdqu ymm0, [rax]` |
| `V_STORE` | `vmovupd [rax], ymm0` / `vmovdqu` |
| `V_SPLAT` f64 | `vbroadcastsd ymm0, xmm0` (or `[rip+c]` for a constant) |
| `V_SPLAT` i64 | `vmovq xmm0, r`; `vpbroadcastq ymm0, xmm0` |
| `V_SPLAT` i32 | `vmovd xmm0, r`; `vpbroadcastd ymm0, xmm0` |
| `V_ZERO` | `vxorpd ymm0, ymm0, ymm0` (or `vpxor`) |
| `E_BIN +` f64 | `vaddpd ymm0, ymm0, ymm1` |
| `E_BIN - * /` f64 | `vsubpd`, `vmulpd`, `vdivpd` |
| `V_FMADD` f64 | `vfmadd231pd ymm0, ymm1, ymm2` |
| `E_BIN +% -%` i64 | `vpaddq`, `vpsubq` |
| `E_BIN +% -% *%` i32 | `vpaddd`, `vpsubd`, `vpmulld` |
| `E_BIN & \| ^` | `vpand`, `vpor`, `vpxor` |
| `E_BIN <` f64 | `vcmppd ymm0, ymm1, ymm2, 1` (predicate 1 = lt; 2 le, 0 eq, 4 neq) |
| `E_BIN <` i64/i32 | `vpcmpgtq`/`vpcmpgtd` with the operands swapped (signed) |
| `V_SELECT` f64 | `vblendvpd ymm0, ymmB, ymmC, ymmMask` |
| `V_SELECT` int | `vpblendvb ymm0, ymmB, ymmC, ymmMask` |
| `V_SUM` f64 | `vextractf128 xmm0, ymm8, 1`; `vaddpd ymm8, ymm8, ymm0`; `vunpckhpd ymm1, ymm8, ymm8`; `vaddsd xmm0, xmm8, xmm1` |
| `V_SUM` i64 | `vextracti128`; `vpaddq`; `vpshufd 0x4E`; `vpaddq`; `vmovq` |
| `V_ANY`/`V_ALL` f64 | `vmovmskpd eax, ymm0`; `test`/`cmp` |
| `V_ANY`/`V_ALL` int | `vpmovmskb eax, ymm0`; `test`/`cmp` |
| `V_EXTRACT` | `vextractf128` + `vmovsd`/`vpextrq`/`vpextrd` |
| `V_PERM` | `vunpcklpd/hpd`, `vperm2f128`, `vpshufd`, `vpermq` |

Two important AVX2 facts:

- **There is no 64-bit vector multiply in AVX2.** `vpmullq` is AVX-512DQ. `i64x4
  *%` must be synthesised from three `vpmuludq` plus shifts and adds (about six
  instructions), or left out of stage 1. The measured `array`/`loop` loops use
  only add and shift-by-one (`v +% v`), so stage 1 can omit `i64x4 *%`; `i32x8`
  has `vpmulld`.
- **FMA is explicit.** `vfmadd231pd` needs VEX.66.0F38.W1 B8 and W=1. Without it,
  `vmulpd` + `vaddpd` measures the same cycles on this machine (both ~220M in a
  controlled run) but uses 25% more instructions; keep `vfmadd` for the shorter
  dependency chain and the Intel case, not as a claimed ~5x by itself.

### 4.4 C backend

`cgen` prints the same type and ops with GCC vector extensions and intrinsics:

```c
typedef double obx_f64x4 __attribute__((vector_size(32)));
typedef long long obx_i64x4 __attribute__((vector_size(32)));
typedef int obx_i32x8 __attribute__((vector_size(32)));
```

- element-wise `+ - * /` and comparisons are plain C operators on these types
  (GCC gives a vector of -1/0 for a comparison);
- `vload`/`vstore` are `__builtin_memcpy` to/from a vector variable (GCC turns
  them into `vmovupd`) or `_mm256_loadu_pd`/`_mm256_storeu_pd`;
- `vsum`, `vselect`, `vany`, `vmin/max`, lane/shuffle are small `static inline`
  helpers in the generated C or `rt.h`, using `_mm256_*` and
  `__builtin_shufflevector`; the C backend already compiles with
  `-march=x86-64-v3`, so the intrinsics are available.

This is about 120 lines in `cgen` plus a header include, and it keeps native and
C in the differential test. If that is deferred, `cgen` should print a clean
"vector types are native-only" error rather than wrong C.

## 5. ABI

The SysV x86-64 ABI is the one the language already follows, and `__m256d` /
`__m256i` have a simple convention:

- a 32-byte vector is class **SSE** and is passed in one **YMM** register
  (`ymm0`–`ymm7` for the first eight vector arguments), not in two XMM registers
  and not in memory;
- a vector result is returned in `ymm0`;
- a 16-byte vector (`f64x2`, if added) is class SSE in one XMM; a vector is never
  split across an eightbyte boundary;
- the existing `classify` must special-case `TY_VEC` **before** its
  `size > 16 -> CL_MEM` rule: a 32-byte vector is one `CL_SSE`, and the argument
  allocator consumes one vector register;
- vectors in records or arrays are stage 4; if one is added, the ABI is the same
  as a C struct containing `__m256d` (memory, 32-byte alignment).

The existing register allocator gives doubles `xmm8`–`xmm14` when their live
range has no call (`fpLoud`). Vector locals reuse the same set and the same
`freg` array: a physical register number is the same for `xmm8` and `ymm8`, and
the allocator's interference rules keep two values out of it while both are
live. Width does not need a separate class: a 256-bit VEX op zeroes the upper
half, and any 128-bit value sharing the number is dead there by construction.
Vector locals live in memory (a 32-byte slot) when their range includes a call
that is not generated in place (or another `fpLoud` position), exactly as doubles;
spills use `vmovupd`/`vmovdqu`, so the slot needs no 32-byte absolute alignment.
The math runtime (`native/math.c`, compiled `-ffixed-xmm8`–`-ffixed-xmm15`) leaves
those registers alone, so calls to it do not make a vector local spill; verify
that `-ffixed-xmm8` also fixes `ymm8` (it should: the register number is fixed),
and if not, treat all math calls as loud for vectors too.

Vector parameters are moved from their argument YMM registers in the prologue
(or into their slots if spilled), like double parameters. Call arguments: the
smallest correct stage-1 rule is to evaluate vector arguments into temporary
32-byte slots and load them into their YMM registers at the call, reusing the
existing "last double in `xmm0`" logic or, simpler, loading all of them at the
call. The outgoing-argument area needs 32-byte alignment if a vector is passed on
the stack (more than eight vector args); stage 1 can restrict vector parameters
to the register case and report an error otherwise.

**`vzeroupper`.** The generated scalar double code uses legacy SSE (`addsd`,
`movsd`); a function that also executes 256-bit VEX ops leaves the upper YMM
halves dirty. On Intel, a later legacy SSE instruction in the same function can
incur a false dependency, and a call into non-AVX code can pay a transition
penalty. Plan: (a) emit an explicit `vzeroupper` once before a non-inlined call
and before a return from a function that has executed a 256-bit op since the
last one (one uop; negligible); (b) in a function that uses vectors, encode its
scalar double operations with VEX (`vaddsd`, `vmulsd`, `vmovsd`, ...) instead of
the legacy forms, so the function is uniformly VEX. The second is a per-function
flag and about 60 lines in the SSE paths; it does not change functions without
vectors, so the default path's code is untouched. On Zen 4 neither penalty
applies, but the design must not depend on that.

**CPU level.** x86-64-v3 is already the language baseline: SPEC 14 says programs
require AVX2/BMI/FMA and the runtime checks CPUID at startup, exiting 16 if a
feature is missing (`compiler/native/rt.c`). The C backend already compiles with
`-march=x86-64-v3` (`main.obx`, `gccCmd`). So no new build flag is needed to emit
AVX2; vector ops are just a new use of an instruction set every obx program may
already use. The compiler *binary* stays at the seed's `gcc -O2` baseline (it does
not need to use AVX); `compiler/build.sh` need not change. A `--cpu=baseline`
mode for pre-v3 CPUs is not useful while SPEC requires v3.

## 6. Implementation plan and line estimates

The estimates are lines of obx added or changed, counted as the code is today
(50,720 lines in `compiler/`). They include comments and tests but not the
generated runtime (`rtx.obx`), which does not change.

| component | stage 1 | stage 2 | stage 3 | stage 4 |
|---|---:|---:|---:|---:|
| `sema.obx`: primitive ids/names, size/align/copy, `primOf` | 45 | — | — | 60 |
| `check.obx`: operator rules, builtin typing, expected type, place rules | 150 | 90 | 30 | 60 |
| `emit.obx` / `cgen.obx`: type names, intrinsics, vector printing | 130 | 40 | 40 | 60 |
| `lower.obx`: TY_VEC, vector `E_BIN`, builtin `E_VECOP`, checked load/store | 260 | 50 | 40 | 60 |
| `ir.obx`: TY_VEC, E_VECOP, predicates, typeName | 45 | 10 | — | 20 |
| `x64gen.obx`: types/ABI/args/returns | 170 | — | — | 80 |
| `x64gen.obx`: register allocation, spills, prologue, `vzeroupper` | 130 | — | — | 40 |
| `x64gen.obx`: `E_BIN` vector + FMA + comparisons/select/reductions | 180 | 180 | 60 | 60 |
| `x64gen.obx`: `E_VECOP` load/store/splat/zero/sum/lane/perm | 220 | 40 | 80 | 60 |
| `x64.obx`: VEX helper and encodings | 140* | 60 | 50 | 30 |
| tests (native/C differential, traps, ABI, encoder) | 150 | 80 | 50 | 80 |
| **total** | **~1,600** | **~550** | **~350** | **~610** |

\* the prototype already has 177 lines of this (section 7), including the
stage-2 compare/select and stage-3 permute forms; the stage-1 subset is about 140.

Stages:

1. **Stage 1 — f64x4 and i64x4, loads/stores, arithmetic, reductions.**
   Types; `vzero`, `vbroadcast`, `vload`, `vstore`, `vsum`; f64 `+ - * /` and
   `vfmadd`; i64 `+% -% & | ^`; no compares. x64gen: VEX ops, vector locals in
   `ymm8`–`ymm14`, spills, parameters/returns, `vzeroupper`. C backend prints the
   GCC types/intrinsics. Tests: dot (about 5x), saxpy, array add, mixed
   scalar/vector functions, bounds traps, a C caller of a vector function, and a
   native/C differential run. **~1,600 lines.** This is the smallest slice that
   proves the effort.
2. **Stage 2 — masks.** Comparisons for f64/i64/i32, `vselect`, `vany`/`vall`,
   `vmin`/`vmax`, i32x8 arithmetic (`vpaddd`, `vpmulld`), integer shifts by a
   scalar (stage 2b). **~550 lines.** Without this, dot and saxpy work but
   clamp/min/max/masking code does not; most real numeric code wants it.
3. **Stage 3 — data movement.** `vlane`, `vwithLane`, `vzipLo/Hi`, `vswapHalves`,
   a small named permute; `i64x4 *%` synthesised from `vpmuludq`. **~350 lines.**
   Needed for AoS layouts, transposes, and complex arithmetic; not needed for the
   measured wins.
4. **Stage 4 — breadth.** `f32x8` if `f32` is added; `u8x32`; arrays/records of
   vectors; the `loops.obx` fact that proves a vector check from a loop bound
   (owned by another agent; coordinate); a `--cpu` flag only if v3 stops being
   the baseline. **~600 lines.**

Through stage 2 the compiler grows by ~2,150 lines (4.2%); through stage 3 by
~2,500 (4.9%). `x64gen` absorbs ~700 of stage 1, which is proportionate to its
7,528 lines. The compile-time cost for a program without vectors is zero: no new
pass, no new fact, and the `E_BIN`/`E_VECOP` dispatch is one switch. The encoder
adds about 10–15 KiB to the compiler binary (the prototype's 177 lines added 11
KiB).

Compare an automatic vectorizer: a loop vectorizer with dependence analysis,
runtime alias checks, epilogues and a cost model is 10,000–50,000 lines in
GCC/LLVM. The explicit extension is 20–30x smaller and does not need to discover
anything.

## 7. Prototype

Two things are implemented on `simd-design` at `4ead14e4`; neither is
reachable from the language, so the default compiler path is unchanged. The
encoder additions are not merged (they would need a reseed for dead code); the
instruction-sequence harnesses are part of this tree. `compiler/seed/obxc.c` is
not regenerated on that branch, so `compiler/build.sh` still builds the seed.

### 7.1 The VEX encoder

`compiler/x64.obx` gains a VEX prefix helper and the stage-1/2 encodings:
`vaddpd/vsubpd/vmulpd/vdivpd`, `vfmadd231pd`, `vmovupd` (load/store/reg),
`vxorpd/vandpd/vorpd`, `vcmppd`, `vblendvpd`, `vbroadcastsd`, `vpshufd`,
`vextractf128`, `vperm2f128`, `vpaddd/q`, `vpsubd/q`, `vpmulld`, `vpand/vpor/
vpxor`, `vpmovmskb`, `vzeroupper` (177 lines in the prototype, including the stage-2
compare/select and stage-3 permute forms). The helper picks the two-byte C5
form when the map is 0F and the index/base are low, matching GNU as's canonical
encoding; `vmovupd` register-to-register uses the 0F 11 form when that puts the
low register in r/m. The prototype implements the 256-bit forms; the 128-bit
forms the reductions use (`vaddsd`, `vunpckhpd`, 128-bit `vaddpd`, `vpaddq`,
`vpshufd`) are the same helper with `l = false` (and `pp = 3`, the F2 prefix, for
the scalar-double forms); they are part of stage 1's ~140-line encoder subset.

`tools/x64_vex_test.py` (on `simd-design`) generates random register/memory/immediate cases,
encodes them with `obxc --encode-test`, assembles the same instructions with GNU
`as`, and compares the bytes:

    python3 obx/tools/x64_vex_test.py --n 3000
    x64 VEX encoder: 3000 instructions identical to as

The existing encoder test still passes (`python3 tools/x64_encode_test.py --n
3000`: 3000 instructions identical to as), so the addition does not disturb the
existing encoder.

### 7.2 The instruction-sequence harness

`bench/simd/dot_kernels.s` and `array_kernels.s` implement the exact sequences
x64gen would emit for a checked `vload`/`vstore` loop, with 1, 4 or 8 bounds
checks; `dot_obxstyle.c` and `array_obxstyle.c` drive them with the same data and
rounds as the C references. Results are in section 2.3:

- the 16-double dot product at 174–183M cycles, against 174M for hand AVX2+FMA
  and 881M for scalar C: **the proposed lowering reaches the ceiling**;
- the int64 array loop at 118M cycles (checked) in the quiet session, against
  108M hand and 249M scalar C there; across sessions the absolute cycles vary by
  up to 2x, but the checked sequence stays ahead of scalar C and in the hand
  version's range;
- the bounds checks add 0.5–1 instruction per element and about 10% of the cycles
  in the array loop, and no measurable cycles in the dot loop.

This is a model of x64gen's output, not a compiler change; it validates the
instruction selection, register pressure (4 vector accumulators plus 8 load
registers fit in `ymm0`–`ymm11`), the reduction sequence, and the cost of the
checks.

### 7.3 Not implemented

The frontend types/rules, `lower`, the `E_VECOP` node, x64gen's vector register
allocation/ABI/code generation, and `cgen` are not implemented. The design above
gives their shape and cost; a full vertical slice is ~1,600 lines (stage 1) and
is the next step if the recommendation is accepted. The branch's prototype is
the encoder plus the measurement harnesses, clearly separate from the default
compiler.

## 8. Risks

| risk | effect | mitigation |
|---|---|---|
| register allocation reuses `xmm8`–`xmm14` for vectors | a double/vector width mix in one register if interference is wrong | the existing `given[16+x]` key is physical-register based; add a test that mixes doubles and vectors in one function and checks the fixed native/C differential |
| 32-byte vectors in the SysV ABI | stack args, returns, C interop | special-case `TY_VEC` before `size > 16 -> CL_MEM`; test a C caller/callee of `__m256d`; restrict stack-passed vectors in stage 1 |
| `vzeroupper` / AVX–SSE transitions | Intel false dependencies and transition stalls | per-function VEX scalar mode and `vzeroupper` at calls/returns; measure on Intel if one is available |
| bounds checks stay | up to ~10–20% on bandwidth-bound loops | measured cheap on compute-bound loops; add the `loops.obx` fact later (coordinate: another agent owns that file); never read past the end |
| integer vector ops wrap | differs from scalar `+` | documented; `+%`-style is the explicit SIMD contract; checked forms can be built with masks |
| reduction order / FMA rounding | native and C must agree | define the tree order in the spec; `vfmadd` explicit; differential tests with exact bytes |
| `i64x4 *%` has no AVX2 instruction | a missing operator or a slow synthesis | omit in stage 1; synthesise in stage 3 (3 `vpmuludq` + shifts/adds) and measure |
| vector values in records/arrays | layout and ABI complexity | stage 4; stage 1 rejects them with a clear error |
| `opt`/`loops` see a new node | a pass could split a vector value or mis-hoist | stage 1 guards both passes on functions containing `E_VECOP`; later teach them the type |
| C backend lags | a language feature only on `--native` | implement the GCC-vector `cgen` in stage 1 (~120 lines); if not, a clean error, never wrong C |
| source-level misuse (unaligned/overrun) | none: loads are checked and unaligned-safe | no gather/scatter, no unchecked load in stage 1; the tail is scalar |

## 9. Recommendation

1. **Do not implement automatic vectorization.** The measured ceiling is reached
   by explicit ops; the discovery problem (dependences, epilogues, profitability)
   is the expensive part of a vectorizer, and the compiler is meant to stay
   small.
2. **Narrow the extension to `f64x4`, `i64x4` and `i32x8`** with loads/stores,
   element-wise arithmetic, `vfmadd`, reductions, and (stage 2) compares/masks/
   select. Skip `f32x8` until `f32` exists, and `u8x32`/shuffles until a measured
   workload needs them.
3. **Do stage 1 now if numeric code is a target**: ~1,600 lines, about 3% of the
   compiler, native and C, no new pass, no compile-time cost for scalar programs.
   It captures the dot product (about 5x), saxpy and array maps (about 2x on
   large arrays in a quiet session; the loop is bandwidth-limited), tight
   integer reductions (4.05x), and amortises the bounds check over 4–8 elements.
4. **Do not advertise a general speedup.** Tokens, strings, allocation, pointer
   chasing and the sieve's marking gain 0–18%; `strings` is already 2x faster in
   obx than in C through the allocator, and SIMD does nothing there. The sample's
   ~1.9x geometric mean is carried by two of six workloads.
5. **Keep x86-64-v3 as the baseline.** It is already required by SPEC 14 and the
   runtime checks it; no new build flag is needed. The compiler binary itself
   stays baseline.
6. **If the project's work stays systems/string-heavy and numeric code is not a
   goal, defer.** The current benchmark suite would gain almost nothing today;
   the 4x wins are a bet on the LLM-agent-written numeric code the proposal
   anticipates. If that bet is taken, the narrow two-stage extension is the
   right size — much cheaper than a vectorizer, and enough to reach the measured
   ceiling.

## 10. Files

- `obx/design/simd.md` — this note.
- `obx/bench/simd/` — the ceiling harness: `run.py`, `README.md`, `dot.obx`,
  `dot.c`, `dot_avx2.c`, `array_avx2.c`, `loop_avx2.c`, `sieve_avx2.c`, the
  instruction-sequence prototypes `dot_obxstyle.c`/`dot_kernels.s` and
  `array_obxstyle.c`/`array_kernels.s`.
- On branch `simd-design` at `4ead14e4` only (not merged):
  `obx/compiler/x64.obx` — prototype VEX encodings (unreachable from the
  language; the default compiler binary is still built from the seed) — and
  `obx/tools/x64_vex_test.py`, the encoder test against GNU as.
