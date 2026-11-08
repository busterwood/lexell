# SIMD ceiling measurements

The measurements behind [../../design/simd.md](../../design/simd.md): what explicit
SIMD could buy, measured against the scalar and auto-vectorised C references.

    python3 lexell/bench/simd/run.py [--only NAME ...] [--reps 3] [--core 8]

It builds every candidate into a temporary directory and times it with
`perf stat -e instructions:u,cycles:u` pinned to one core, best of three, the
candidates of a workload interleaved (forward, reverse, forward). It needs gcc,
perf and a free core (8 by default; other work on this machine uses 0, 2, 4, 6).

| workload | scalar C | auto-vectorised C | hand AVX2 |
|---|---|---|---|
| `array` | `bench/c/array.c` | same, `-march=x86-64-v3` | `array_avx2.c` |
| `loop` | `bench/c/loop.c` | same | `loop_avx2.c` |
| `sieve` | `bench/c/sieve.c` | same | `sieve_avx2.c` (counting loop only) |
| `tokens` | `bench/c/tokens.c` | same | — (serial scan and hash) |
| `strings` | `bench/c/strings.c` | same | — (allocation) |
| `dot` | `dot.c` | same | `dot_avx2.c` (FMA, 4 accumulators) |
| `dot_proto` | `dot.c` | — | `dot_kernels.s` |

`dot_proto` is the prototype: the exact x86-64 instruction sequence the proposed
extension would emit for a 16-double dot-product loop, with 1, 4 or 8 vector
bounds checks per iteration, written by hand in `dot_kernels.s` and called from
`dot_lxlstyle.c`. It is a model of x64gen's output, not a compiler change.

The C variants use `-O2 -fno-tree-vectorize -fno-optimize-sibling-calls` for
"scalar" and `-O2 -march=x86-64-v3` for "auto-vectorised". The dot scalar row
also uses `-ffp-contract=off`; the hand version uses FMA explicitly.

`dot.lxl` is the scalar Lexell dot product, built with `lxlc ... --native -O`.

The encoder prototype is separate: `python3 lexell/tools/x64_vex_test.py` compares
the VEX encodings added to `compiler/x64.lxl` with GNU as.
