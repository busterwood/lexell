# Decimal against .NET and Java

Status: measured 2026-11-07 at `a5169764`, on the WSL2 Ryzen 7 8745HS, with
.NET 8.0.427 (SDK 8.0.427) and Temurin/OpenJDK 21.0.13, against obx's
`--native -O` build. The harnesses are in
[bench/decimal/compare](../bench/decimal/compare/run.sh).

obx's `Decimal` is a 32-byte value record: a 128-bit coefficient (38 decimal
digits), an exponent, a display scale and a sign, with SQL `numeric`
semantics. The two types it is most often compared with are:

- **.NET `System.Decimal`**: 16 bytes, a 96-bit integer mantissa (28-29
  significant decimal digits), a scale 0-28 and no exponent. A value type,
  with no allocation on any operation.
- **Java `BigDecimal`**: an immutable reference type: an unscaled
  `BigInteger` (arbitrary precision) and an `int` scale. Every result is a
  new object, and the magnitude is a `BigInteger` of its own.

They are not the same job, so the comparison is a speed check, not a
semantic equivalence: .NET is the small value-decimal reference, Java is the
arbitrary-precision reference, and obx is the 38-digit value type with SQL
semantics.

## Method

Three matched harnesses build 4,096 inputs from the same splitmix64 seed
with the same construction (d-digit coefficients, `1` to `9` leading digit,
the stated scale), run each operation over them, and print ns per operation,
best of 7 runs; each program is run three times and the least is taken. They
are pinned to one CPU (`taskset -c 2`) and run one at a time.

- .NET is built in Release and run with `DOTNET_TieredCompilation=0` so the
  first timed run is already fully optimised.
- Java is run with `-Xms2g -Xmx2g`. A volatile sink keeps one result per
  iteration alive, so the JIT cannot scalar-replace the allocations away;
  the always-sink and once-per-1024 variants measured the same, so the
  numbers are real allocation-inclusive times.
- obx is built with `--native -O`.
- Every result feeds a checksum (addition of a low word, a hash or a length)
  so no loop can be dead-code eliminated.

The operations are the public API of each type:

| case | obx | .NET | Java |
|---|---|---|---|
| add | `a.add(b)` | `a + b` | `a.add(b)` |
| mul | `a.mul(b)` | `a * b` | `a.multiply(b)` |
| div | `a.div(b, 2, HALF_EVEN)` | `Math.Round(a / b, 2, ToEven)` | `a.divide(b, 2, HALF_EVEN)` |
| parse | `Decimal.parse(s)` | `decimal.Parse(s)` | `new BigDecimal(s)` |
| format | `a.toStr()` (scale 2) | `a.ToString("F2")` | `a.toPlainString()` |
| cmp | `a.cmp(&b)` | `a.CompareTo(b)` | `a.compareTo(b)` |

.NET has no scale-directed divide: the harness divides to full precision and
rounds, the idiomatic way to get a scale-2 `HALF_EVEN` result. That is a real
cost of the .NET type as used here; it is marked in the table.

## What .NET can represent

Matched cases: 19-digit add, 6x6 multiply, 12/6 divide at scale 2, 20-digit
parse, 19-digit format and 19-digit compare. ns per operation, lower is
better:

| operation | obx Decimal | .NET decimal | Java BigDecimal | obx/.NET | obx/Java |
|---|---:|---:|---:|---:|---:|
| add, 19 digits at 2 places | 29.5 | **11.8** | 16.0 | 2.5 | 1.8 |
| mul, 6x6 digits | 27.1 | **12.1** | 12.3 | 2.2 | 2.2 |
| div, 12/6 digits at scale 2 | 53.2 | 78.5* | **15.5** | 0.68 | 3.4 |
| parse, 20 digits | **52.3** | 106.5 | 107.7 | 0.49 | 0.49 |
| format, 19 digits fixed 2 | 55.7 | 88.3 | **50.6** | 0.63 | 1.1 |
| compare, 19 digits | 8.8 | 2.9 | **1.7** | 3.0 | 5.2 |

\* full-precision divide then `Math.Round`; .NET's decimal has no
scale-directed divide.

## Beyond .NET's 28 digits

`System.Decimal` cannot hold 38 digits or a 19x19-digit product, so this
table is obx against Java only. The 37-digit add keeps the sum inside obx's
38-digit coefficient.

| operation | obx Decimal | Java BigDecimal | obx/Java |
|---|---:|---:|---:|
| add, 37 digits at 2 places | 30.7 | **17.5** | 1.8 |
| mul, 19x19 digits (38-digit product) | 26.0 | **23.0** | 1.1 |
| parse, 38 digits | **71.9** | 238.7 | 0.30 |
| format, 38 digits fixed 2 | **86.9** | 264.3 | 0.33 |

## What the numbers say

- **.NET's 16-byte decimal is the speed reference for arithmetic.** Its
  96-bit add, multiply and compare are inline JIT code over a value that
  never leaves registers. obx is 2.2 to 2.5 times slower on add and multiply
  and 3 times slower on compare.
- **obx wins where the library does the work.** Its parser reads eight
  digits at a time and its writer emits 10^19 chunks; it is about twice as
  fast as both at parsing 20 digits and 1.6 times .NET's formatting time.
  At 38 digits it is 3.3 times faster than Java's parse and format.
- **Java's BigDecimal is much faster than its reputation on small values.**
  Add 16.0, multiply 12.3 and divide 15.5 ns: HotSpot inlines the
  small-magnitude paths and TLAB allocation is cheap, and the escaping sink
  shows the allocations still happen. Its parse (108 ns) and its 38-digit
  format (264 ns) are the expensive operations.
- **The gap is not the 128-bit arithmetic.** obx's `addExact` is about 97
  cycles (25 ns) on the same inputs; the public `add` operator adds a
  `Result`, its copy and `orStop`. That record-ABI cost is the remaining
  lever ([record-abi.md](record-abi.md)), not the width of the coefficient.
- **At 38 digits the arithmetic gap narrows** to 1.1-1.8 times (Java's
  small-value shortcuts stop helping), while obx's parse and format are
  3.3 times faster. A 38-digit value is the case obx was built for.

## Why .NET and Java win the arithmetic

The answer is not that their arithmetic is better. In obx the 128-bit
coefficient operation is almost free; nearly all of the time is the
normalisation, the `Result` and the copies around it. The same 19-digit and
6x6 inputs, measured three ways (ns per operation, same harness):

| case | public operator | `...Exact` + `match` | bare 128-bit coefficient op |
|---|---:|---:|---:|
| add, 19 digits | 29.6 | 20.5 | **1.25** |
| mul, 6x6 digits | 27.0 | 21.2 | **1.36** |

The bare operation is the `u128` add (or the low half of a multiply) plus
the loop and checksum: about 5 cycles. Everything else is:

- `addExact`: two `digits()` calls for the 38-digit bound, the exponent
  alignment, a `u256` add, and `makeDec` (trailing-zero strip, a third
  `digits()` and the range checks);
- `mulExact`: `mul128` (one 64x64 product when both factors fit, as
  they do here), then `makeDec`;
- the public `add`/`mul` operator: a `Result` return and an `orStop` match,
  which copies the 32-byte `Decimal` out again (6 to 9 ns).

.NET and Java avoid both layers, and each also specialises by size:

**.NET `decimal`.** The value is a 96-bit integer in registers; `+` is a
scale compare and a 96-bit add, with no allocation and no normalisation
loop (trailing zeros stay in the scale). Multiply has three code paths:
32x32 (one multiply), 96x32, and 96x96 (nine 32x32 partial products). On a
separate threshold harness:

| multiply digits | ns/op | path |
|---:|---:|---|
| 6 | 9.4 | 32x32, one multiply |
| 9 | 9.4 | 32x32 |
| 10 | 13.4 | leaves the 32-bit path |
| 13 | 14.2 | 96x96 |

Add is flat — about 9.7 ns at 9, 19 and 26 digits — because it is
always the same 96-bit add.

**Java `BigDecimal`.** Its `intCompact` keeps the unscaled value in a
`long` when it fits, and add/multiply then use 64-bit arithmetic; only the
result `BigDecimal` is allocated. When the value or result does not fit,
it falls back to `BigInteger`. The threshold harness shows the jumps:

| operation | digits | ns/op | path |
|---|---:|---:|---|
| mul | 6 | 7.8 | compact `long` |
| mul | 9 | 8.0 | compact `long` |
| mul | 10 | 21.8 | product overflows `long`, `BigInteger` |
| mul | 19 | 16.5 | `BigInteger` |
| mul | 38 | 21.3 | `BigInteger`, four limbs |
| add | 9 | 7.7 | compact `long` |
| add | 18 | 7.9 | compact `long` |
| add | 19 | 14.9 | sums start to overflow `long` |
| add | 26 | 18.8 | `BigInteger` |
| add | 38 | 19.1 | `BigInteger` |

The separate harness uses a different input scale and one operation per JVM
run, so its absolute values are a little lower than the main table; the
jumps are the point. This is exactly the size dependence you remembered:
Java's cheap path is a single 64-bit operation, and it disappears at 10
digits for a product and at 19 digits for a sum. The 19-digit compare in
the main table sits right at that boundary, which is why Java's add there
(16 ns) is between its 9-digit time (7.7) and its 38-digit time (19).

**Beyond 28 digits.** .NET cannot represent the values, so it is obx
against Java. obx's arithmetic is still only ~1.4 ns; its 26 to 31 ns is
the same fixed normalisation and copy cost. Java has no normalisation and no
`Result`, so its 4-limb `BigInteger` add (19 ns) and multiply (21 ns) beat
it. obx's multiply barely moves from 6 to 38 digits (27 to 26 ns) because
the width was never the cost; Java's multiply rises from 8 to 21 ns because
its path changes. That is the clearest statement of the difference: obx is
overhead-bound at every size, Java is arithmetic-bound only at large sizes.

## What would close it

1. **A `Result`-free internal path for the operators.** `add`/`mul` pay a
   `Result` return and an `orStop` copy for errors that are nearly always
   absent. An internal non-`Result` function used by the operator, or a
   by-pointer return, recovers 6 to 9 ns of the 27 to 30.
2. **One digit count instead of three.** `addExact` calls `digits()` on both
   operands and again inside `makeDec`. A table indexed by the remaining
   room (`10^38` thresholds), or a bit-length estimate, would replace each
   binary-search chain with a load or a few instructions.
3. **Skip the trailing-zero strip when `coef % 10 != 0`.** For random sums
   and products the first test almost always fails; the current loop still
   computes the multiply and compare once.
4. **Do not normalise on every operation.** .NET keeps trailing zeros in the
   scale and normalises only where it must. If obx kept them too (and
   compared/formatted them correctly), `add` and `mul` would not need
   `makeDec` at all. That is a representation change, not a peephole, but it
   is the single largest difference from .NET.

The small-value fast path (one 64-bit multiply instead of four) is *not*
worth much: the bare multiply is 1.36 ns, so the four partial products are
already cheap. The return/ABI and the normalisation are the levers.

## Caveats

- The semantics differ, and the table is not an equivalence claim: .NET is
  96-bit/28-29 digits with no exponent; obx is 128-bit/38 digits with an
  exponent and a display scale; Java is arbitrary precision.
- .NET's divide is a full-precision divide plus `Math.Round`, because the
  type has no scale-directed divide. The row would be different for a
  library that exposes one.
- obx's add and multiply go through the public operators, which build a
  `Result` and call `orStop`; that is what a program pays, not the raw
  `addExact`/`mulExact`.
- Java's results are kept alive by a volatile sink, so allocation is
  included. Without it HotSpot scalar-replaces the whole result and the
  arithmetic appears several times faster (multiply at 5 ns), which is a
  benchmark artifact, not a program's cost.
- The inputs are random d-digit coefficients at the stated scales; all
  operations are exact and no error path is measured.
- ns per operation, best of 7, one core, the same machine. Absolute times
  move by a few percent between runs; the ratios are the stable figure.

## Reproduce

The toolchains can be installed without root, as they were here:

```sh
curl -sSL https://dot.net/v1/dotnet-install.sh | bash -s -- --channel 8.0
# Temurin 21: https://api.adoptium.net/v3/binary/latest/21/ga/linux/x64/jdk/hotspot/normal/eclipse
```

Then:

```sh
cd obx/bench/decimal/compare
XDG_RUNTIME_DIR=/tmp/xdg DOTNET=$HOME/.dotnet/dotnet \
  JAVAC=$HOME/jdk/*/bin/javac JAVA=$HOME/jdk/*/bin/java ./run.sh
```

The harnesses are `decbench.obx`, `decbench-big.obx`, `DecBench.cs`
(+ `DecBench.csproj`) and `DecBench.java`/`DecBenchBig.java` in that
directory. The breakdown and threshold runs above are `diagnose.sh`
(`variants.obx`, `Scale.cs`, `Scale.java`):

```sh
XDG_RUNTIME_DIR=/tmp/xdg DOTNET=$HOME/.dotnet/dotnet \
  JAVAC=$HOME/jdk/*/bin/javac JAVA=$HOME/jdk/*/bin/java ./diagnose.sh
```
