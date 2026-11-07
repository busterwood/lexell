# A small, fast, competitive native compiler

Status: research note recorded 2026-11-07 (main at `9298038f`). This states the
goals, the survey of other small compilers and the candidate optimizations for
the native backend; it is a direction to test, not a decided pipeline. The
measurements that decide each step belong in [../../PERFORMANCE.md](../../PERFORMANCE.md)
and the pass-by-pass history in [../../HISTORY.md](../../HISTORY.md).

## Goals

The goal is to develop a small, extremely fast native compiler for an
Oberon-derived language that incorporates group borrowing for deterministic
memory management.

The compiler should produce machine code competitive with established
optimizing compilers such as GCC, Clang and Rust, without inheriting the
enormous size and complexity of their optimization infrastructure.

Ideally, generated programs would run within a few percentage points of
equivalent highly optimized native programs. Matching or occasionally exceeding
their performance would be welcome, but isn't a requirement. Achieving this
consistently across every workload is probably unrealistic without substantial
additional complexity.

The important objectives are:

- **Runtime performance:** Produce code in the same performance class as the
  best native compilers, particularly for ordinary scalar and systems
  programming workloads.
- **Compilation speed:** Compile extremely quickly, potentially making
  compilation inexpensive enough to happen during software installation.
- **Implementation size:** Keep the compiler small, preferably measured in tens
  of thousands rather than hundreds of thousands or millions of lines. A
  compiler executable of only a few megabytes would be attractive.
- **Simplicity:** Prefer straightforward, understandable algorithms and a
  limited number of optimization passes.
- **Maintainability:** Keep the entire compiler small enough that its design can
  be understood and evolved without a large compiler engineering team.
- **Pragmatism:** Concentrate on optimizations with the greatest performance
  benefit relative to their implementation complexity and compilation cost.

The initial target is x86-64, with x86-64-v3 as the baseline architecture. This
provides AVX2, FMA, BMI1/BMI2 and other useful instructions available on
processors dating back roughly to the 2013–2015 era.

We may also support compiling specifically for the machine performing the
build. Rather than distributing multiple implementations and selecting between
them at runtime, the compiler could generate a single executable using the
instruction set available on that machine.

Given a sufficiently small and fast compiler, compiling software at installation
time may be a reasonable alternative to distributing generic precompiled
executables.

## Research into existing compilers

We have looked at several established and smaller compilers to understand the
relationship between implementation size, compilation speed and generated-code
performance.

The most interesting examples so far are:

- **QBE — approximately 10,000 lines of C.**

  QBE explicitly aims to deliver around 70% of the performance of industrial
  compilers using roughly 10% of their implementation complexity.

  It uses an SSA-based intermediate representation, constant propagation,
  dead-code elimination, value optimizations, register allocation and
  instruction selection.

  It deliberately avoids expensive features such as automatic function
  inlining and extensive interprocedural optimization.

  QBE demonstrates how much can be achieved with a small, deliberately
  restricted compiler backend, although its generated-code performance leaves a
  substantial gap on some workloads.

- **MIR — approximately 23,400 lines for the JIT backend and supporting core.**

  MIR is particularly interesting because it prioritizes fast compilation
  while generating relatively competitive machine code.

  Its optimization pipeline includes function inlining, SSA, global value
  numbering, conditional constant propagation, dead-code elimination,
  loop-invariant code motion, instruction combining and relatively simple
  register allocation.

  The project's published benchmarks report generated-code performance around
  91% of GCC `-O2` on the geometric mean of 15 small C benchmarks.

  The complete C-to-MIR compiler is larger, approximately 55,000 lines,
  including the C frontend and supporting components.

  These are project-reported measurements rather than an independently
  established performance guarantee, but MIR is probably the most interesting
  example of the size/performance trade-off we're investigating.

- **Cranelift — approximately 200,000 lines.**

  Cranelift aims to provide fast, secure native compilation without all the
  optimization complexity of LLVM.

  It uses SSA, fast instruction lowering, register allocation and increasingly
  sophisticated optimizations, including work involving acyclic e-graphs.

  It deliberately avoids some expensive techniques, including advanced alias
  analysis and reliance on undefined-behaviour assumptions.

  Although much larger than MIR or QBE, Cranelift is interesting because its
  developers consciously evaluate which optimizations justify their cost.

- **Java HotSpot C1 and C2.**

  HotSpot demonstrates two different optimization strategies within the same
  runtime.

  C1 uses SSA, relatively simple optimizations and fast register allocation to
  prioritize compilation speed. C2 uses much more sophisticated global
  optimization, inlining, escape analysis, loop transformations and
  vectorization to maximize runtime performance.

  The contrast is useful because it shows that SSA does not imply a heavyweight
  optimization pipeline. Much of the complexity lies in the analyses and
  transformations built around it.

- **.NET RyuJIT — historically estimated at approximately 360,000 lines.**

  RyuJIT combines SSA-based analysis with value numbering, common-subexpression
  elimination, inlining, loop optimizations and linear-scan register
  allocation.

  It is explicitly designed to balance compilation cost against runtime
  performance. Tiered compilation allows inexpensive initial code generation
  followed by more aggressive optimization of hot methods.

  The historical source-size estimate covers a much broader production
  compiler than the small backends above and is not a directly comparable
  measurement.

  RyuJIT is worth studying for its optimization choices and practical
  engineering trade-offs, even though its overall implementation is much larger
  than our intended compiler.

- **V8 Maglev.**

  Maglev is particularly interesting because it deliberately minimizes
  optimization phases.

  It constructs an SSA-style graph, performs useful optimizations during graph
  construction, uses relatively straightforward register allocation and
  generates machine code directly from its intermediate representation.

  It avoids much of the multi-stage optimization and lowering machinery found
  in V8's higher-tier compilers.

  Its approach suggests that SSA and optimization could be integrated with
  initial intermediate-code construction, potentially keeping both compiler
  size and compilation time low.

- **LuaJIT.**

  LuaJIT uses trace compilation, optimizing frequently executed paths rather
  than entire functions.

  Its trace-based SSA representation supports specialization, constant
  folding, common-subexpression elimination and dead-code elimination.

  The trace-based approach doesn't directly suit an ahead-of-time Oberon
  compiler, but it illustrates the advantages of restricting the scope of
  optimization to a simpler problem.

These size estimates come from different versions, dates and counting methods.
Some refer to a backend, others to a broader compiler implementation. They
should be treated as useful indicators rather than a rigorous comparative
measurement.

## Optimization techniques worth investigating

The research suggests that a relatively small collection of optimizations can
deliver much of the benefit of a considerably larger compiler.

Potentially worthwhile techniques include:

- Constant folding and algebraic simplification.
- Local and global common-subexpression elimination.
- Value numbering and constant propagation.
- Dead-code and dead-store elimination.
- Copy propagation and register coalescing.
- Control-flow and branch simplification.
- Conservative function inlining.
- Simple loop-invariant code motion.
- Efficient register allocation, possibly using linear scan with live-range
  splitting.
- Good x86-64 instruction selection, including addressing modes, instruction
  combining and peephole optimization.

SSA remains an important technique and is used by most of the optimizing
compilers examined. It can simplify several of these transformations, and newer
direct-construction algorithms make it less expensive to introduce than
traditional SSA conversion approaches.

However, SSA should not automatically be treated as a requirement. Non-SSA
approaches, local value numbering and optimizations performed during IR
construction are also worth examining.

Some other interesting ideas include acyclic e-graphs, inexpensive rewrite
systems, declarative instruction selection and optimization rules discovered
or verified offline.

Group borrowing may also provide useful optimization information directly from
the language's type and lifetime rules. Where borrowing establishes that memory
regions cannot overlap, the compiler may be able to avoid some of the expensive
alias analysis needed by C and C++ compilers. However, mutable aliases within a
group must still be respected.

**This is not a complete list of candidate techniques or a proposed final
optimization pipeline.** These are simply approaches that appear promising from
the initial research. There may be other, less familiar compiler designs or
techniques offering better performance for lower implementation cost.

The intention is to experiment, benchmark and retain optimizations whose
benefits justify their complexity, rather than copying the optimization
pipeline of an existing compiler.

## Measuring success

A useful research objective would be to investigate how small an optimizing
compiler can be while achieving performance within approximately 3–5% of GCC or
Clang `-O2` on a representative selection of workloads.

This would be an ambitious target, not an assumption about achievable results.

Comparisons should use equivalent algorithms, equivalent memory-management
strategies and equivalent processor instruction-set targets.

Measurements should include both generated-code execution speed and compiler
performance. Compiler implementation size, executable size and compilation time
are important dimensions of success, not merely secondary concerns.

Particularly useful experiments would identify which optimizations close the
largest performance gaps and how much implementation complexity each requires.

Performance on ordinary scalar code, pointer-heavy code, allocation-heavy
applications and numerical loops should be examined separately. A compiler may
be very competitive in one area while considerably slower in another.

## Explicit vectorization rather than automatic vectorization

One potentially important language-design trade-off is **not to implement
automatic vectorization in the compiler at all**, at least initially.

Automatic vectorization is among the more complex optimizations implemented by
mature compilers. It requires discovering independent computations, analysing
memory dependencies, transforming loops, handling remainder iterations and
deciding whether vectorization is profitable.

An alternative is to make SIMD vector operations explicit in the language.

For example, the language could support fixed-width vector types, element-wise
arithmetic, comparisons, vector loads and stores, reductions and selected
shuffle operations.

The programmer would decide where vectorization is appropriate, while the
compiler would translate those explicitly expressed operations into efficient
native instructions.

These could be portable vector operations rather than direct dependencies on
particular x86 instructions. The compiler could select the appropriate AVX2 or
newer instructions when building for the target machine.

This approach becomes particularly attractive because much of the software
written in the language is expected to be produced by LLM coding agents.

A coding agent can identify computationally expensive loops, choose explicit
vector operations, generate correctness tests and benchmark the resulting
implementation. The compiler would not need to rediscover those opportunities
through sophisticated automatic analysis.

It would still need efficient SIMD instruction selection and register
allocation, but the difficult problem of discovering vectorizable computations
could largely be removed.

Explicit SIMD would not guarantee optimal performance, and some algorithms
would still benefit from sophisticated transformations. Nevertheless, it could
eliminate a substantial category of compiler complexity while preserving access
to modern processor performance.

**The broader principle is to avoid making the compiler infer complicated
information when the language can express that information simply and
explicitly.**

Group borrowing already explores this principle for memory management and
lifetime reasoning. Explicit vectorization could apply the same idea to data
parallelism.

This seems a particularly promising trade-off for the language we're
developing: a small, fast native compiler that performs essential scalar
optimizations well, while allowing programmers and coding agents to express
vectorized computations directly rather than requiring a heavyweight automatic
vectorizer.
