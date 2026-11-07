# By-value record copies: the ceiling before a by-reference ABI

Status: measured 2026-11-07 on `record-abi` (from `5ba4f734`). One safe change
is kept ("receiver temporaries", 167 lines in `opt.obx`); the by-reference
oracle is throwaway and **not merged**. Measured on the AMD Ryzen 7 8745HS,
pinned to core 0, `taskset -c 0 perf stat -x, -e instructions:u,cycles:u`,
best of 9 (Decimal microbenchmarks) or 7 (applications), base and candidate
interleaved. Instructions decide; cycles are reported and must agree in sign.
Every output was compared; the oracle also reproduces them except where noted.

The question: two profiles (Decimal `add`; the cmark text/softbreak path) put
by-value record copies in the gap to C. How much can be removed, and is a
by-reference internal ABI worth building? The answer, measured: the copy
ceiling is **-1.8% instructions for the whole Decimal suite** and **at most
-0.3% instructions for cmark, json, jq and the compiler**; a 167-line safe
pass captures -1.7% of the Decimal suite (94% of that ceiling). So the safe
pieces are worth having and the ABI is not justified by instructions.

## 1. The sizes and the method

`ir` lays records out as gcc does, so the copies are SysV by-value copies:

| type | layout | size |
|---|---|---:|
| `Decimal` | `u128 coef`, `int exp`, `int dscale`, `bool neg` (16-aligned) | 48 |
| `Result[Decimal, DecError]` | `int tag` + union of `Decimal`/`DecError` (16-aligned) | 64 |
| `U256` (`makeDec`'s parameter) | `u128 hi`, `u128 lo` | 32 |
| `markdown.Node` | Kind, 5 ints, 3 `str`, ints, bools/bytes | 192 |
| `obx_str` header | pointer, length | 16 |

A record over 16 bytes is passed on the stack and returned through a hidden
pointer (`design/native.md` section 3). The callee reads its record
parameters **from the caller's stack**, so the only copies are at the call
site: the front end's consume temporary for a method receiver, the copy into
the outgoing-argument area, and the copy of a record result into the next
call's outgoing area. Result *returns* are already forwarded
(`retInPlace`/`RET_MEM`, below).

Two compilers are used. **Base** is `HEAD`'s seed compiled with gcc
(`git show HEAD:obx/compiler/seed/obxc.c`). The **oracle** is a throwaway
patch of `opt.obx` and `x64gen.obx` (560 diff lines, kept as
`/tmp/opencode/record-abi/oracle.patch` in the measurement tree, never
committed) that does, behind env vars:

- `OBX_BYREF=1`: every internal function parameter of an aggregate over 16
  bytes whose call sites all pass a place becomes a `T*`; the body's reads
  become `p->f` and the call sites `&place` (no read-only or escape proof:
  deliberately unsound, that is the point);
- `OBX_FWD=1`: `T t = init; f(..., t, ...)` and `T t = init; *p = t` become
  `f(..., init, ...)`/`*p = init` for a single-use temp and a pure init;
- `OBX_INPLACE=1`: `*rt_arr_push(...) = CLIT` builds the literal directly in
  the new array element instead of a frame temporary.

`OBX_BYREF` miscompiles the compiler itself (the compiler built with it dies
with `index out of range at check.obx:1415` when compiling `main.obx`); its
self-build ceiling therefore uses `FWD`+`INPLACE` only. That is itself a
result: an unsound by-reference ABI is not merely hard to prove, it changes
programs.

## 2. Inventory: what is copied, where, and what it costs

Static sites were read in the `-O` IR (`OBX_NATIVE_IR`, printed as C) and in
the disassembly (`OBX_NATIVE_MAP`, `objdump -D -b binary`). Dynamic counts
are per operation; the Decimal microbenchmarks run 4,096 operations 1,000
times (4.096M per case), and `M2:19` executes 2,112.5M instructions, i.e.
515.7 per add.

A "memory instruction" below is one `mov`/`movdqu`/`rep movsb` (load or
store); at 48/64 bytes a copy is 3 or 8 such pairs.

### 2.1 Decimal `add` (`M2:19`) — the full trace

`m2`'s hot loop calls `xs[i].addExact(ys[i])` and passes the `Result` to
`errSum`; the base disassembly at `0x412850`–`0x413172` has exactly these
copies per operation:

| # | site | what is copied | bytes | memory instr | static in the loop |
|---:|---|---|---:|---:|---|
| 1 | `m2`: `t32 = xs[i]` | array element to the receiver temporary | 48 | 6 (3 `movdqu`) | yes |
| 2 | `m2`: `t32` → `(%rsp)` | temporary to outgoing arg 0 | 48 | 12 (6×8 bytes) | yes |
| 3 | `m2`: `ys[i]` → `0x30(%rsp)` | element to outgoing arg 1 | 48 | 6 (3 `movdqu`) | yes |
| 4 | `m2`: `t34` → `(%rsp)` for `errSum` | 64-byte `Result` to outgoing | 64 | 16 (8×8 bytes) | yes |
| 5 | `errSum`: `v_d = sp1->u.V_Ok.f_0` | `Ok` payload to a local, then `&v_d` | 48 | 6 (3 `movdqu`) | yes |

That is **46 memory instructions, 256 bytes moved, per add** (8.9% of the
515.7 instructions; site 5 belongs to the benchmark's `errSum`, sites 1–4 to
the library call). Sites 1–4 alone are 40 instructions, 7.8%: the earlier
"about four copies, 5% of add's instructions" estimate
(`design/decimal-perf-research.md` section 9, `PERFORMANCE.md` Decimal)
counted the same four copies but was low by the memory instructions of each
copy and the result's extra eightbyte. The callee adds no copy: `addExact` reads `a`/`b` at
`0x10(%rbp)`…, `makeDec`'s `U256` literal is built in the outgoing area
(`fillEntries`, `outFree`), and `makeDec`'s `Result` is returned through
`addExact`'s own hidden pointer (`mov -0x30(%rbp),%rdi; call makeDec`), which
it forwards to the caller.

The same shape costs, per operation:

| case | receiver temp (1+2) | other args | `Result` → `errSum` | `errSum` payload | total mem instr | instructions/op |
|---|---|---:|---:|---:|---:|---:|
| `addExact` M2:19 | 18 | 6 | 16 | 6 | 46 | 515.7 |
| `mulExact` M3:19 | 18 | 6 | 16 | 6 | 46 | 533.2 |
| `quantize` M6:6 | 18 | — | 16 | 6 | 40 | 467.6 |
| `cmp` M10:same | 18 | — (`&ys[i]` already a pointer) | — | — | 18 | 243.1 |
| `parse` M7:20 | — (type method) | — | 16 | 6 | 22 | 347.7 |

### 2.2 cmark: one 192-byte literal copy per node, not a chain

`Parser.newNode`/`blankNode` are inlined into every node-building function
(`textNode`, `addChild`, …). The IR after `opt` still names three
temporaries, but `x64gen`'s literal-in-place code builds the literal once in
a frame temporary and then copies it to the element an `append` made:

```
struct S12_markdown_Node t1_3675 = (struct ...){.f_kind=..., .f_parent=-1, ...};
rep movsb        ; 192 bytes, frame temporary -> *rt_arr_push(&d.nodes, 192)
```

The copy is **one `rep movsb` of 192 bytes per node** (one instruction,
roughly 12–24 cycles); the ~40 stores that build the 192-byte literal are the
native cost, and the literal's constant fields (`-1`, `0`, `""`) are why the
C build spends fewer instructions. So the 87-vs-58 instruction gap per
append is **literal construction**, not copies: the copy itself is one
instruction. The `text` field adds a `str` dup/drop pair (16-byte header
moves), not a record copy.

### 2.3 json, jq and the compiler

No hot by-value record copy was found. json's boxed `Value` is a small
struct written into arrays once at parse time; jq reads it through pointers.
The compiler's big structures (`Ir`, `Opt`, `Gen`, the AST) are already
passed by `&`/`mut &`. The by-reference oracle changes their instruction
counts by -0.13% (json), -0.19% (jq) and -0.31% (the compiler compiling
itself), which is the noise floor of "no copies to remove".

## 3. The oracle ceiling

Best variant per workload: the oracle is not a single monotone transform
(its by-ref pass *adds* instructions in `addExact`, see section 5), so the
table gives the best instruction count and the best cycle count any oracle
variant reached. `%` is against base. `Mcyc` in millions.

| workload | base Minstr | safe Minstr | oracle Minstr | d% | base Mcyc | safe Mcyc | oracle Mcyc | d% |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Decimal add M2:19 | 2112.5 | 2059.3 | 2112.5 | **−0.00** ¹ | 477.4 | 450.4 | 430.2 | −9.9 |
| Decimal mul M3:19 | 2183.8 | 2130.6 | 2114.1 | −3.19 | 494.2 | 464.6 | 434.1 | −12.2 |
| Decimal parse M7:20 | 1424.2 | 1424.2 | 1407.0 | −1.21 | 305.8 | 306.2 | 293.5 | −4.0 |
| Decimal quantize M6:6 | 1915.2 | 1915.2 | 1820.9 | −4.92 | 472.4 | 468.8 | 357.3 | −24.4 |
| Decimal cmp M10:same | 995.7 | 942.4 | 954.6 | −4.12 | 202.2 | 178.1 | 168.8 | −16.5 |
| **Decimal, all 40 cases** | **53922.9** | **53012.9** | **52958.4** | **−1.79** | **12530** | **12154** | **11405** | **−9.0** |
| cmark 10 MB spec | 1370.9 | 1370.9 | 1370.1 | −0.06 | 523.7 | 533.0 | 504.7 | −3.6 ² |
| json 20 MB | 4417.2 | 4417.2 | 4411.5 | −0.13 | 1888.8 | 1956.4 | 1891.2 | +0.1 ² |
| jq (20 MB, `-c .`) | 4288.6 | 4288.6 | 4280.4 | −0.19 | 1636.8 | 1698.7 | 1694.8 | +3.5 ² |
| compiler self-build | 5180.4 | 5180.4 | 5164.2 | −0.31 | 2501.0 | 2562.3 | 2445.7 | −2.2 ² |

¹ the best oracle variant is *worse* in instructions than the safe pass for
`add`: `OBX_BYREF` removes site 4 but makes `addExact` bigger (section 5).
By-ref alone is 2096.1M (−0.78%, −10.4% cycles); `safe` is better on
instructions and worse on cycles.
² the jq/json/cmark/compiler cycles in this table are not a measurement of
the oracle: the machine's cycle counts for these workloads move 5–10% between
runs (jq's base cycled 1.637–1.699 G over the session), and the safe builds
are *byte-identical* to base for cmark, json and regex, so their cycle
differences are noise. Instructions, which repeat to 0.01%, decide.

**The ceiling, stated plainly:** a by-reference internal ABI can remove at
most ~1.8% of instructions from the Decimal suite, ~1.2–4.9% from individual
Decimal cases, and ≤0.31% from cmark/json/jq/the compiler. It buys larger
cycle reductions on Decimal (up to −9% for the suite, −24% for quantize)
because the copies are store-forwarding stalls, not issue slots — the
cycle/instruction ratio of `quantize` falls from 0.247 to 0.196.

## 4. Safe candidates

### 4.1 Kept: receiver temporaries (`opt.obx`, 167 lines)

The front end lowers `a[i].f(x)` as `T t = a[i]; f(t, x)` so the by-value
receiver is captured before the argument is evaluated. When

- `t` is named exactly once in the function, as argument 0 of a direct call
  in the same block,
- `t`'s initializer is a member or dereference place and is pure (no
  assignment, and no call but the checked `rt_idx`/`rt_sidx`/str readers),
- the statements between are declarations with pure initializers that do not
  name `t`,
- every argument after the first is pure,

then `t` is replaced by the place and the declaration removed: `f(a[i], x)`.
Sound because the copy `f` makes of argument 0 happens after those
statements (which cannot write the place) and before the other arguments are
evaluated (which cannot write it either); no other use of `t` exists. The one
observable change is that a bounds check inside the place may run one
statement later, so a program in which two checks fail may report the other;
`SPEC` does not order failed checks, and no test suite checks it.

Measured, best of 9, core 0, instructions and cycles:

| case | base Minstr | new Minstr | d% | base Mcyc | new Mcyc | d% |
|---|---:|---:|---:|---:|---:|---:|
| Decimal add M2:19 | 2112.5 | 2059.3 | **−2.52** | 477.4 | 450.4 | **−5.65** |
| Decimal mul M3:19 | 2183.8 | 2130.6 | −2.44 | 494.2 | 464.6 | −5.99 |
| Decimal cmp M10:same | 995.7 | 942.4 | −5.35 | 202.2 | 178.1 | −11.94 |
| Decimal parse M7:20 | 1424.2 | 1424.2 | 0.00 | 305.8 | 306.2 | +0.12 |
| Decimal quantize M6:6 | 1915.2 | 1915.2 | 0.00 | 472.4 | 468.8 | −0.76 |
| Decimal, all 40 cases | 53922.9 | 53012.9 | −1.69 | 12530 | 12154 | −3.00 |
| cmark / json / jq / regex | — | — | 0.00 | — | — | noise |
| 10 microbenchmarks (`fib`…`maps`) | — | — | 0.00 | — | — | 0.00 |

The ten microbenchmark binaries are **byte-identical**; cmark, json and
regex are byte-identical, and jq differs only in a segment address (code and
data shifted by 199 KB) and executes +924 instructions of 4.29 G (0.00002%).
In the Decimal add/mul/cmp
loops the six changed functions remove 12–13 instructions per operation
(one 48-byte copy instead of two).

The gate is met on Decimal add (−5.65% cycles, −2.52% instructions), the
whole suite is −1.69%/−3.00%, and nothing is worse than 1%.

### 4.2 Measured, not kept: build a literal into a fresh array element

`*rt_arr_push(&a, n) = CLIT` built the literal in a frame temporary and
`rep movsb`'d it to the element. Building it at the element (30 lines in
`x64gen.genAssign`, oracle `OBX_INPLACE`) is sound for a fresh `rt_arr_push`
destination, and on the 10 MB cmark spec it removes 845K instructions of
1,370,942K (**−0.06%**) and no measurable cycles. Below the gate; recorded,
not shipped. The general `arr[i] = Record{...}` form is harder to use safely
(an initializer entry may read the destination) and is not needed: the hot
cmark case is `append`, and it is 0.06%.

### 4.3 Verified already complete: record result forwarding

`T t = f(...)`, `t = f(...)` (local, address not taken) and `return f(...)`
all give the callee the destination's own slot or the caller's hidden result
pointer. Evidence in base `addExact`: `mov -0x30(%rbp),%rdi; call makeDec`
passes its own hidden result pointer on. The remaining `Result` copy in the
Decimal loop is **site 4, an argument copy into `errSum`'s outgoing area**,
not a return: removing it needs `errSum` to take `&Result` (a by-ref
parameter) or a separate outgoing area per call depth, because the callee's
own outgoing area is the same `rsp` region while it runs.

### 4.4 Safe `Result[T]` temporaries at the source (Decimal)

`add`/`sub`/`mul` still call `orStop(a.addExact(b))`, which copies the
`Result` into `orStop`'s argument. It does not appear in the microbenchmarks
(they call `addExact`/`mulExact` directly), and changing the public
`Decimal` API to return `Result` everywhere is an API change, not a
codegen one; not attempted.

## 5. Why the by-reference oracle is not an instruction win for add

On the base (without the safe pass), `OBX_BYREF` removes sites 1–4 (40
memory instructions per add). Measured on top of the safe pass, where sites
1–3 are already gone, it removes only site 4 (16 memory instructions) and
changes 2059.3M to 2096.1M instructions (+36.8M, +1.8%) while cycles go
450.4M → 427.9M (−5.0%): the callee costs about **25 extra instructions per
operation**, more than the 16 the copy saved. `addExact` is 384 bytes larger
(3008 → 3392) and its register allocation moves values around. Pinning the
pointer parameters in callee-saved registers (`OBX_PTRREG`, a throwaway
allocator bias) left the instruction count unchanged at 2124.7M, so this is
not simply an allocator spill; it is the callee's code shape around indirect
parameters. For `add`, the by-ref instruction count is *worse* than the safe
pass (2096.1M vs 2059.3M) while its cycles are better (427.9M vs 450.4M).
A by-reference ABI is therefore a cycles lever, not an instruction lever, on
this profile.

## 6. Recommendation: (b) keep the safe piece; do not build the ABI now

1. **Keep receiver-temporary forwarding** (`opt.obx`, 167 lines). It captures
   94% of the whole-suite Decimal instruction ceiling (−1.69% of −1.79%) and
   −5.7%/−6.0%/−11.9% cycles on add/mul/cmp for one sound, local pass. The
   default `--native` compile cost of the pass itself is +1.1% (measured by
   gating it off in the same compiler: 4,095.0M → 4,140.9M instructions to
   compile `main.obx`); `-O`/default stays at +12.4% instructions / +11.6%
   cycles (budget +30%).
2. **Do not build the by-reference ABI for instructions.** Its measured
   ceiling is ≤0.31% for cmark/json/jq/the compiler and +0.1% over the safe
   pass for the whole Decimal suite. The only case for it is Decimal cycles
   (store-forwarding stalls: suite −9% vs −3% for the safe pass, quantize
   −24%), and that is a minority of the gap to C (Decimal is at 1.06× C's
   cycles in the application table).
3. **If it is revisited, stage it** (estimates; none built):
   - **Stage A** (300–450 lines, `opt.obx`): read-only record parameters by
     pointer. Reuse `Opt.ro` (already computed for inlining) as the
     read-only proof; require every call site to pass a place, else
     materialize a temporary and pass its address; update the function type,
     the parameter local and every call node's type. Expected (oracle upper
     bound): whole Decimal suite −9% cycles, individual cases −4 to −24%
     cycles, **but** −1.8% instructions at best, and add's instruction count
     would get *worse* than today's safe pass unless the callee code shape
     is fixed first.
   - **Stage B** (150–250 lines, `x64gen`): an outgoing-argument area per
     call depth, so a record result can be written straight into the next
     call's argument slot. Removes site 4 (16 memory instructions per
     add/mul/quantize/parse operation): a ≤2–5% instruction ceiling on those
     cases, none elsewhere.
   - **Stage C**: by-reference `Result` returns/arguments internally
     (subsumed by A+B).
   The risk is the soundness work A needs (writes, escapes, aliases through
   pointers passed in later arguments) and the measured fact that an
   unsound version of exactly this transform miscompiled the compiler.

## 7. What the ceiling does not prove

- It is a **copy-elimination** bound, not a bound on inlining, a mid IR or a
  register allocator. gcc wins these loops largely by inlining; removing the
  copies while keeping the call reaches 94% of the instruction ceiling but
  not C's numbers (Decimal add is still 1.14× C's cycles in
  `PERFORMANCE.md`).
- For cmark it proves the opposite of the working hypothesis: the 192-byte
  node append is **one** copy instruction, and the parse gap (1.38× C's
  instructions) is literal construction and the surrounding code, not
  by-value records. cmark's copy ceiling is 0.06%.
- It does not cover the C ABI boundary, public API changes (`&Decimal` in
  std) or the cost of a *sound* by-ref pass. The oracle skips the proofs and
  miscompiles the compiler itself (`check.obx:1415`), so a sound Stage A
  would reach less than these numbers, not more.
- Cycle figures on this machine move 5–10% between runs; the json/jq/cmark
  cycle columns in section 3 are noise, and the byte-identical binaries show
  it. Every claim above that matters is an instruction count.
- The oracle's own layout changes and its `addExact` regression show that
  the union of the transformations is not a strict upper bound per metric:
  where they disagree, the table gives the best variant and section 5 says
  why.

## 8. Reproducing

    D=/tmp/record-abi
    git show HEAD:obx/compiler/seed/obxc.c > $D/old.c
    gcc -O2 -w -std=gnu11 -o $D/obxc_base $D/old.c -lm          # base
    obx/compiler/build.sh                                       # candidate out/obxc
    for v in base new; do ... done                              # build the workloads
    taskset -c 0 perf stat -x, -e instructions:u,cycles:u dbench M2:19

The oracle is the saved 560-line patch of `opt.obx`/`x64gen.obx`; apply it
to a scratch tree and build the compiler with `out/obxc main.obx -o obxc_or`,
then build each workload with `OBX_BYREF=1 OBX_FWD=1 OBX_INPLACE=1`. The
oracle prints `OBX_NATIVE_IR`/`OBX_NATIVE_MAP` like any native build.

## 9. Gate and cost

- `bash obx/tools/gate.sh quick`: **PASS** (seed fixed point, 797 conformance,
  136+5 compiler, 282 lib, `run_native.py --lib` 613/613,
  `--lib --opt` 613/613, native self-build fixed point 3,039,745 bytes).
  One run of the `lib` step hit the known flaky SCRAM-error line in
  `pgwire_fake.obx`; it passed alone and on the next full run.
- Ten microbenchmarks: native binaries byte-identical to base.
- cmark 10 MB / json 20 MB / regex: native binaries byte-identical to base;
  jq: +924 of 4.29 G instructions (0.00002%, a shifted segment address);
  Decimal (all 40 cases) −1.69% instructions, −3.00% cycles.
- `optcost.py --compiler out/obxc -n 3 --pin 0`: `-O`/default **+12.4%
  instructions, +11.6% cycles** (geomean; budget +30%; the cycle figure moved
  11.6–14.1% between runs). The pass's own cost
  in the default path is +0.7…+1.1% per program (+1.1% to compile the
  compiler).
