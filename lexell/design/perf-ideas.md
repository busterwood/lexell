# CPU-level performance ideas for Lexell and lexdb: a backlog

Future work, not started (2026-11-13). Another agent surveyed Daniel Lemire's
blog and related research and wrote a brief of experiments for Lexell and
lexdb. This note is that brief reviewed against the code as it stands on
`main` at 804acb57: what is already done, what our own measurements say is
worth most, and in what order to try the rest. It also adds what the brief
missed. The brief's guardrails, method and reading list hold, and are kept
in section 5.

Nothing here is measured as a gain until it is built and benchmarked. Where
a number is quoted it is ours, measured on this machine, not a figure from
the articles.

## 1. Where the time goes now (our measurements)

The brief starts from the column leaves' scans. Our measurements put the
largest gaps elsewhere:

- **Parallelism.** PostgreSQL with 4 processes runs parallel aggregates and
  joins 2.5 to 5 times faster than lexdb (lexdb-engines.md section 6; the
  wall-clock ratio over 34 queries is 1.28). On one core, lexdb is already
  faster overall: a geometric mean of 0.72 of PostgreSQL's time. This is a
  design decision the user wants to discuss first: worker processes, or a
  narrow parallel primitive in the language with a heap per worker.
- **Single-core gaps against PostgreSQL** (lexdb-engines.md 6): `select *`
  1.7x, `expr_mix` 1.3x, hashing texts, window functions, a join of `w` and
  `t`. These are output and expression costs more than scan costs.
- **Bulk loads** (lexdb.md 9.118, 9.119): 1M wide rows load in 3.15 s against
  1.96 s for PostgreSQL. What is left is spread thin: the store's put and
  commit, the key's read, reference counts and allocation (`dup`, `drop`,
  `malloc`: about 10% in every profile so far).
- **Formatting doubles.** `rt_float_to_str` tries `%.15g`, `%.16g` and
  `%.17g` in turn. Each try is made with big integers and parsed back.
  Measured over 3M conversions: about 164 ns per value for values like
  `421.92`, and 5.3 us for doubles of every magnitude. lexdb's `fmt8` then
  re-parses that text into digits (`digitsOf`).

So scans of the column leaves, the brief's Priority A, are the part where
lexdb already does well. That does not make them wrong to try, only later.

## 2. The brief's items, checked

| Item | State on main | Verdict |
|---|---|---|
| A1 predicates on packed data | Min/max skipping per leaf exists (ints, and since 9.113 dates and times). LIKE runs on a dictionary's entries in place (9.112). `count(*)` decodes nothing already. Equality on dictionary codes and frame-of-reference deltas: not done. | Valid. Only the equality cases are new. |
| A2 selection bitmaps | Batches carry index arrays. | Valid as an experiment; whole-query gain uncertain. |
| A3 specialised unpacking | `lexdb_cols.unpack` reads a byte at a time, for every width. | Valid and cheap. A word-at-a-time scalar version (u64 loads), specialised for widths 1/2/4/8/16/32, needs no SIMD language work. Do this first of the A items. |
| B1 interleaved descents | `getMany`, sorted keys and finger paths exist. | Weakest fit. Lexell code cannot control when loads issue, and node keys are arrays of reference-counted strings, so a descent chases pointers through string blocks. Would need runtime or compiler support. Last. |
| C1 fast number parsing | **Done for doubles** (Eisel-Lemire in the runtime, native.md 2; 9.118). ISO dates and timestamps, canonical uuids and plain doubles have fast paths (9.119). Open: integers (`parseIntOpt`, about 2.5% of a load) and fixed-scale numerics (`Decimal.parse`, quantize). | Remaining part valid, modest gains: 8-digit SWAR parsing for ints and decimals. |
| C2 direct formatting to the wire | Every value becomes a `str`, then a message. Doubles go through the slow `rt_float_to_str` above. | **Strongest item.** A shortest round-trip formatter in the runtime (Ryu, Schubfach or Dragonbox family), then integers, numerics and doubles appended straight into the output buffer. Targets `select *`, the largest single-core gap. |
| C3 delimiter classification | Done for COPY's text format: `indexOfAny`, 16 bytes at a time (9.119). CSV still goes a byte at a time. | Mostly done; CSV left. |
| D1 constant-string `match` | `isReserved` already uses `match`. | Low priority; only with a profile showing it. |
| D2 division by a constant per execution | Not measured to matter anywhere. | Low priority. |
| D3 explicit SIMD API | simd.md argues for a small explicit extension, built on evidence. | Agree: let A3 and C2 say which primitives are needed. |
| Roaring, binary fuse filters, prefetch, AVX-512 | Not needed by any workload we have. | Agree they are later, if ever. |

## 3. Proposed order

1. **Double formatting in the runtime**, a shortest round-trip algorithm
   replacing the big-integer `%.Ng` tries. It is checked like the parser:
   every result must parse back to the same bits and be the shortest such,
   tested against Python's `repr` on random doubles of every class. Then
   `lexdb_float.fmt8` and `fmt4` format from its digits instead of
   re-parsing text. It is one runtime function, and every Lexell program
   that prints a float gains.
2. **Direct formatting into the wire buffer** (C2): ints, numerics and
   doubles appended to the DataRow, COPY TO and TDS row buffers without a
   `str` per value. Measure `select *` and the COPY TO of 1M rows, with the
   allocations per row.
3. **Word-at-a-time unpacking** (A3, scalar), then equality on packed data
   (A1: dictionary codes, frame-of-reference deltas) for the scan shapes the
   benchmark queries use.
4. **Integer and fixed-scale decimal parsing** (C1's remainder), with SWAR
   for 8 digits, for COPY and text parameters.
5. **Selection masks** (A2), only if 3 shows the selection lists are the
   cost.
6. **Interleaved descents** (B1), only with a profile of random point
   lookups showing memory stalls, and a way to express them in Lexell.

## 4. What the brief did not cover

- **Parallelism**, above: the largest gap, a separate decision.
- **Reference counts and allocation.** `dup`, `drop`, `malloc` and `free`
  are 7 to 10% of most profiles. That is a compiler and runtime matter:
  moves instead of copies of values, and borrowed views kept borrowed.
  Probably worth more than several items above, and it is general.
- **`StrBuf` handing its bytes over** as a `str` without a copy (the
  runtime would allocate the array in a string block's layout). Worth 2 to
  3% of a load; useful wherever text is built.
- **The store's commit path for loads.** The narrow load is mostly the
  commit's puts and the key's read. Leave it until the page-layout work in
  progress elsewhere lands.

## 5. The original brief

Kept as written, with these corrections:
- the target is `main`; the `lexdb` branch is retired;
- its baseline commit was 0378113a, before 9.118 and 9.119.

### Working rules

- Read the current code first, and record the commit used.
- Prototype one experiment at a time, in its own branch or worktree. Never
  merge just because a microbenchmark wins.
- Keep SQL semantics, crash safety and the existing performance switches.
  Test against the unchanged implementation and, where PostgreSQL's
  behaviour is the contract, against PostgreSQL. Every new path has a
  fallback.
- Measure the whole query, load or dump, not just the inner loop. Use
  realistic row widths, distributions, cache sizes and selectivities.
- Report the method, raw results, perf counters, correctness checks,
  regressions and maintenance cost, with a keep, modify or discard
  recommendation.

### Correctness that may not change

- SQL's three-valued logic: NULL; AND, OR and NOT; short circuits and which
  errors show.
- Every supported type, cast, collation and encoding; integer overflow;
  floating point's edge cases.
- Rows in different layouts: long and tagged rows, spilled values, changed
  leaves, checkpointed column leaves and the row-leaf fallbacks.
- Prepared statements' parameters, schema changes, skewed data, secondary
  and covering indexes, joins, ordered results.
- A transaction's own writes, serializable read tracking, snapshots,
  replication and crash recovery, for any change to the storage path.
- No unchecked or out-of-bounds memory access on short buffers or at their
  edges.
- Differential tests against current lexdb (`lexdb_batch` on and off,
  `LEXDB_COLUMNS`) and PostgreSQL: values, row counts, errors and SQLSTATEs.

### Method

- Record the commit, compiler flags, kernel, CPU, memory, storage,
  filesystem, cache size and buffered or direct I/O, and whether the run is
  cold or warm.
- Pin server and client to different cores. Alternate A and B runs.
- Report instructions, cycles, branch and cache misses, allocations and
  bytes moved where they mean something. Give the statistic used and the
  spread.
- Keep scripts, seeds and raw results.

### Stages to a decision

1. A microbenchmark: correct at the boundaries, with a repeatable saving.
2. The integrated path: a whole statement, load or dump improves, with no
   regression at other selectivities or cache states.
3. A complexity review: lines, permanent code paths, code size, testing
   burden.

The provisional threshold: about 5% on a real target query, consistently,
with no significant regression. A general runtime primitive that many
callers use may earn its place with less. Reject a 2x microbenchmark that
changes no application.

### Reading list

- Lemire, [Fast integer compression: decoding billions of integers per second](https://lemire.me/blog/2012/09/12/fast-integer-compression-decoding-billions-of-integers-per-second/) (2012).
- [Really fast bitset decoding for average densities](https://lemire.me/blog/2019/05/03/really-fast-bitset-decoding-for-average-densities/) (2019).
- [Faster bitset decoding using Intel AVX-512](https://lemire.me/blog/2022/05/10/faster-bitset-decoding-using-intel-avx-512/) (2022), beyond the x86-64-v3 baseline.
- [Speeding up independent binary searches by interleaving them](https://lemire.me/blog/2019/09/14/speeding-up-independent-binary-searches-by-interleaving-them/) (2019).
- [Faster intersections between sorted arrays with shotgun](https://lemire.me/blog/2019/01/16/faster-intersections-between-sorted-arrays-with-shotgun/) (2019).
- [Quickly parsing eight digits](https://lemire.me/blog/2018/10/03/quickly-parsing-eight-digits/) (2018).
- [Telling your number parser what to expect](https://lemire.me/blog/2026/11/10/telling-your-number-parser-what-to-expect/) (2026).
- [Converting floats to strings quickly](https://lemire.me/blog/2026/02/) (February 2026), and the [float serialization benchmark](https://github.com/fastfloat/float_serialization_benchmark).
- [Billion-query-per-second lookup tables in C++](https://lemire.me/blog/2026/10/26/billion-query-per-second-lookup-tables-in-c/) (2026).
- [Recognizing string prefixes with SIMD instructions](https://lemire.me/blog/2023/07/14/recognizing-string-prefixes-with-simd-instructions/) (2023).
- [Beating the compiler at signed 32-bit division](https://lemire.me/blog/2026/10/31/beating-the-compiler-at-signed-32-bit-division/) (2026).
- [Redis now has compressed bitmaps: Roaring](https://lemire.me/blog/2026/10/15/redis-now-has-compressed-bitmaps-roaring/) (2026).
- In this repository: lexdb.md (9.103, 9.107 to 9.119), lexdb-columns-study.md,
  lexdb-pages.md, lexdb-optimizer.md, simd.md, native.md (section 2,
  parsing floats), PERFORMANCE.md.
