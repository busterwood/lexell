# Parallel map: pure closures on more cores

Status: built, 2026-11-14, on the `par` branch (stages 1 to 5 of section 4;
section 6 records what was built and measured). The note
narrows the "no threads" decision of [concurrency.md](concurrency.md)
section 0 by one exception, like the helper pool's.

- The helper pool's threads run only C.
- The par pool's threads run only **kernels**: closures that the compiler
  has proved do no I/O, never park, touch no mutable global and reach no
  runtime state.

## 0. The feature

```lxl
import "par"

let parts = par.map(&chunks, fn(c) { sumChunk(&rates, c) })
```

`par.map(&xs, f)` returns what a loop of `f` over `xs` would return, in
order. The work is spread over a pool of threads. The compiler refuses the
call if `f` could do I/O.

```lxl
pub fn map[A, T](xs: &[A], f: &fn(&A): T, w: Where): [T]
```

What a user has to know:

1. **`f` must be pure.** It may not do I/O, park, read or write a `var` or
   `once` global, or call a C function. The compiler checks `f` and
   everything `f` can reach. An error names the chain of calls to the first
   offending call.
2. **`f` may read the variables around it, but not change them.** A capture
   that the closure assigns or borrows mutably is an error.
3. **`f` is written at the call.** It is a closure literal or a named
   function, so the compiler knows exactly what runs. A closure passed in
   from elsewhere is refused.
4. **Results come back in order.** The result is the same as a loop's,
   whatever the number of threads.

Everything else follows from those:

- The calling task waits, as it would for a socket, and other tasks keep
  running.
- When nothing else could run, the calling thread works through items as
  well.
- `par.map` takes a `Where`: inside `Shared.with` it is exit 13, like
  every park.
- It is not cancellable. Cancellation and deadlines take effect at the
  task's next wait.
- A trap in `f` stops the program, as a trap in a loop would, with `f`'s
  message and line.
- The runtime decides how items are shared out: workers take ranges of
  indices. A cheap `f` over many items is fine.
- For aggregates, map over pieces (chunks, index ranges) and merge the
  partial results on the caller.

### The pool

- **Size:** `LXL_PAR=N` threads, at most 64. The default is the number of
  CPUs the process may use (`sched_getaffinity`), less one for the calling
  thread.
- **`LXL_PAR=0`:** every `par.map` runs as a loop on the calling thread,
  with the same results.
- **Start:** the pool starts at the first `par.map` of a process.
  `task.workers` refuses to fork after that, as it does once the helper pool
  has started. A forked worker process starts its own pool.
- **Other backends:** the C backend always runs the loop.

### Later, maybe

- An Occam-style `par { ... }` block of different calls, and `par for`.
  They would compile to the same machinery: one job per branch, or a map. Wait
  for programs that want them.
- A `kernel` marker on a `fn`, which puts the purity error at the edit that
  breaks it.

## 1. Why this is sound with Lexell's rules

While `par.map` runs, workers read `xs` and whatever `f` captured. The
caller's task is parked, and other tasks run on the main thread meanwhile.

- **Nothing the workers read can change or go away.** A closure is a
  second-class borrow (SPEC 4.6). While a call that takes it runs, its
  captured roots are held (SPEC 10, rule 3), and `xs` is borrowed for the
  call. No other task can reach those roots, because borrows are rooted in
  their own task's frame (concurrency.md 4). Globals cannot be borrowed. A
  `with` cannot be open, because `par.map` parks.
- **Strings never change once made**, so reading a block's bytes on a worker
  while the main thread changes its count is a read of bytes that nobody
  writes. A count is changed by one thread only (2.3).
- **Workers never touch the same data mutably.** `f` captures nothing
  mutably (rule 2). Each item's result is built in its own worker's heap
  (2.2).
- **Kernels are pure** (rule 1), so no worker reaches a socket, the event
  loop, the output buffer, a global or a C library.

## 2. How it runs

### 2.1 Which thread am I on?

- **Stacks:** worker stacks come from one reserved region, one 8 MiB slot
  per worker, each with a guard page. The worker's context (heap, drop
  stack, count log, trap slot) sits at the top of its slot.
- **The test:** `rsp - base < span` says "a worker", and the slot gives the
  context. It needs no TLS, so it works in static builds (no libc) and
  dynamic ones (libc owns `%fs`).
- **Thread creation:** raw `clone` in both builds. Workers never call libc.

### 2.2 Heaps: one per thread, results handed over in place

- **Per-thread allocator state.** The allocator's state (`free_list`,
  `chunk_at`, `chunk_left`, `large_kept`) becomes a struct. The main
  thread's is the static one, and each worker has its own. `malloc`, `free`
  and `realloc` pick theirs with the test in 2.1.
- **Owner tags.** A block's header word keeps its class in the low 8 bits,
  and the owner's tag in the other 56.
  - Each worker takes a fresh tag (an atomic counter) for every `par.map`
    it works on. The main thread's tag is 0.
  - A large block's header gets the large-block mark 0xFF, and its mapping
    size moves to word 0 of the mapping, which is free.
- **Results are handed over, not copied.** When the call ends, the results'
  blocks simply belong to the main thread:
  - the main thread frees them onto its own free lists;
  - it reallocates them through its own `realloc`;
  - it changes their counts as for any of its blocks.
  A worker never touches a block it no longer owns, because its next call
  has a new tag. Memory therefore moves from workers to main, and main
  reuses it. There is no transfer glue and no deep copy.

### 2.3 Reference counts

A worker changes the count of a string only if it owns the block: the
header tag is its current tag.

- **Foreign blocks** (from `xs`, from a capture, or literals) are not
  counted. A dup or drop of one adds +1 or −1 to the worker's **count log**,
  a small hash table from block to net change.
- **The main thread applies the log when the call ends.** A kernel that
  returns a string from `xs` inside its result thus gets its count raised, on
  the main thread, where that is allowed. Most entries net to 0.
- **Literals** have count −1 and stay immortal.

### 2.4 Kernel functions

The compiler marks every function that a kernel can reach (2.5's set K).

- **Inside K functions,** the native backend does not inline `str` dup and
  drop (x64gen.lxl's `inlineRt`). Those functions call the runtime's
  `rt_str_dup` and `rt_str_drop`, which make the test in 2.1 and follow 2.3.
- **Code outside K is unchanged**, because no worker ever runs it.
- **The cost on the main thread:** K functions pay a call per dup and drop.
  Every program pays a stack-range compare in `malloc`, `free`, `realloc`
  and the runtime's out-of-line dup and drop. Measure both (section 5).

The runtime's own functions that kernels may reach must be safe on any
thread:

- **The drop-action stack** (`rt_ds`, used by drop glue) becomes
  per-thread.
- **`rt_live`** (`LXL_CHECK`) is added atomically on workers.
- **The float parser and printer** keep their scratch on the stack, not in
  statics (rt.c:1208, 1323).
- **`lxllib_hash_key`** (rt.c:548) fills its key before the pool starts.
- **lib/hash.lxl's key globals** (`sipKeyed`, `sipK0`, `sipK1`, `mapSeed`,
  written lazily on the first hash) must stop being written from code a
  kernel reaches, or no kernel could use a `Map`.

### 2.5 The guard

There are two parts.

**At the call (check.lxl).** A call of `par.map` with an argument that is
not a closure literal or a named function is an error. So is a closure that
captures mutably.

**After monomorphisation (a new IR pass, `kernel.lxl`).**

- **Roots.** The pass finds every call of a `par.map` instance and takes the
  closure argument's function as a root. For a literal that is the lifted
  body; for a named function it is the trampoline glue.
- **The walk.** It walks callees from each root:
  - **Direct calls** are followed.
  - **Indirect calls** (function values, closures called inside the kernel)
    are followed to every address-taken function of the same IR type. This
    is Q9's conservative rule. `par.map`'s own call of `f`, in
    lib/par.lxl's item function, is the one exception: its targets are the
    roots of that instance's call sites.
  - **Runtime calls** must be on the kernel list: strings, arrays, slices,
    allocation, checks and traps, the drop stack, hashing, maths and float
    text. Nothing that parks, does I/O, or touches tasks, `Shared`, the
    loop, arguments or the environment.
  - **Extern calls** (C libraries) are refused.
  - **Globals:** reading or writing an `E_GLOBAL` that is not `isConst` is
    refused. A string literal's block is exempt: it is in writable data
    only because its count field lives there, and it is never written.
- **K.** The functions reached become K (2.4).
- **The error.** The first failure is a compile error at the `par.map` call,
  with the chain from the root:

```
report.lxl:14: par.map: the closure is not pure: it can reach I/O
    the closure        report.lxl:14
    Rates.of           rates.lxl:40
    log.warn           log.lxl:22
    println            std.lxl:494    (calls writeFd: I/O)
```

**Run-time backstop.** `rt_park` and the loop's entry points trap when
called on a worker (2.1's test). This cannot happen if the pass is right.

### 2.6 Dispatch

- **Calling the runtime.** `par.map` (lib/par.lxl) calls the runtime's
  `lxllib_par_run`. It passes `n`, the item function (an `extern fn` instance
  `item[A, T]`), and the addresses of the closure and of the slice. The
  item function calls the closure on element i and boxes the result.
- **The job.** The runtime publishes one job: the item function, the two
  addresses, a next-index counter, a done counter and the result slots.
  It then wakes the pool with a futex.
- **Taking work.** Workers take ranges of indices with an atomic fetch-add.
  The range is sized from `n` and the thread count, so that small items are
  cheap.
- **Waking the caller.** The worker that finishes the job last wakes the
  calling task through the event loop's eventfd, as a finished helper call
  does.
- **The calling thread works too.** If no other task could run (the
  helper pool's test in `rt_blocking`), the calling thread takes ranges
  instead of parking. On the main thread a kernel is ordinary code: it
  allocates in the main heap and counts normally.
- **Several jobs at once:** several tasks may each have a job running. Jobs
  queue in order, and workers drain the oldest first.
- **Results.** When the job is done, `par.map` unboxes the results in order,
  and the runtime applies the workers' count logs.

### 2.7 Traps and stack overflow on a worker

- **A trap** (`rt_trap`, `rt_panic`, or out of memory) on a worker writes its
  code and message into the job, marks the job failed, wakes the caller and
  blocks the worker for good. The main thread then traps with that code and
  message, so stdout is flushed by the thread that owns it.
- **A stack overflow:** each worker has its own `sigaltstack`. `rt_segv`
  recognises a fault in a worker's guard page and does the same as a trap,
  with exit 4.
- **The rest of the program:** the main thread's exit (`exit_group`) ends
  the workers.

## 3. Rejected alternatives

| | why not |
|---|---|
| futures for kernels (`s.start` on another core) | two kinds of start, a scope to bound the borrow, cancellation that cannot reach a running kernel, results out of order; and calling `par.map` inside an ordinary task already gives overlap with I/O |
| copying results back (transfer glue) | generated deep-copy code for every result type; owner tags make it unnecessary |
| copying inputs (Node workers, Python subinterpreters) | the borrow rules already prove the inputs read-only |
| atomic counts (Lean 4, Koka) | a cost on every count change in every program |
| worker copies of every kernel function | a second instance of each function and a table to map pointers; marking K and calling the runtime's dup and drop is simpler |
| process futures (concurrency.md 9) | right for coarse isolated jobs and work that needs I/O; wrong for CPU work over data the process holds |

## 4. Stages

1. **Runtime groundwork, which changes no behaviour:**
   - per-thread allocator state and owner tags;
   - a per-thread drop stack;
   - float scratch on the stack;
   - the hash key filled eagerly, and lib/hash.lxl's key globals.
2. **`par.map` as a loop:**
   - lib/par.lxl;
   - the two library intrinsics: an address of a closure or slice, and a
     closure or slice read back from that address;
   - `lxllib_par_run` running items inline, in both runtimes;
   - the checks at the call;
   - tests.
3. **The kernel pass:** roots, the walk, K, the error chain, and tests of
   each refusal.
4. **The pool:**
   - clone, worker stacks and contexts;
   - the futex job queue and completion through the loop;
   - out-of-line dup and drop in K functions;
   - the count logs;
   - traps and overflow on workers;
   - `LXL_PAR`.
   Tests: stress, `LXL_CHECK` leak accounting, and `LXL_PAR=0` against
   `LXL_PAR=N` on the same inputs.
5. **Measure:**
   - the per-call overhead;
   - the speed-up at 1, 2, 4 and 8 threads on hashing, decimal and
     formatting kernels;
   - the cost on the main thread of 2.4's compare (the quick benchmarks, and
     the self-build).

## 6. As built (2026-11-14)

### 6.1 Where the build differs from sections 2 to 4

- **lib/par.lxl.** `map` passes `rawAddr(f)` and `rawAddr(xs)` to the
  runtime: the addresses of the closure and the slice in its frame, which
  stay put while the call parks.
  - `rawAddr` and `rawAt` are two new library-only intrinsics, like `intoPtr`.
    `rawAt` reads a closure or slice back from such an address.
  - The item function `item[A, T]` boxes `callAt(f, xs, i)`.
  - `callAt` makes the call through the closure. It exists because a slice
    read back with `rawAt` may be an argument but not a `let`.
- **The hash key.** `hash.keyReady()` derives the process key on the calling
  thread before any worker runs. The kernel pass then allows hash.lxl's four
  key globals: emit marks them, as it marks string literals' blocks (their
  count is -1 and nothing writes them).
- **Stops.** A function whose result is `never` may reach `rt_write_fd`,
  `rt_exit` and `rt_flush`. Emit marks such functions. This is how `Decimal`'s
  overflow (`decStop`) and `money`'s stop stay usable in kernels. On a worker,
  `rt_write_fd` writes unbuffered, `rt_flush` does nothing, and `rt_exit` is a
  stop forwarded to the main thread (2.7).
- **Externs allowed.** The C maths of lib/std.lxl (the native runtime's own
  libm), `lxllib_hash_key` and `lxllib_hash_crc32c`.
- **Roots.** The pass finds a closure argument either in the call's
  expression, or in the initializer of, or an assignment to, the local the
  closure was spilled into. par's `item` and `callAt` instances are marked
  kernel too. Their call through the closure is not followed: the roots
  cover it.
- **Error messages.** IR nodes carry no lines, so emit records each
  function's source (`label (file:line)`), each lifted closure's line and
  each global's name. The call's location comes from its `Where` argument.
- **The main thread's paths.** Each keeps the one test it had before workers
  existed:
  - `malloc` tests a flag that is set until the heap is set up, and again
    once a pool starts.
  - `free` tests its header word: a worker's tag makes the word large, so a
    worker's block and a large block take the same branch.
  - `rt_str_dup`, `rt_str_drop`, `rt_dpush` and `rt_drun`, the out-of-line
    versions, test `rt_par_span` once.
  - Every pool path is a hook that `rt_par_start` sets, behind an empty `asm`
    so that gcc cannot fold in the one function stored in it. A program
    without `par.map` links none of the pool: hello world is 16,416 bytes, as
    on main.
  - An earlier version of stage 1 seemed to cost nothing. That was gcc
    folding `rt_par_span`, which nothing wrote yet, to 0.
- **Worker stacks.** A worker's drop-action stack is a mapping of its own,
  because it outlives its jobs and a heap block belongs to one job's tag.
  `rt_wme()` reads `rsp` with `asm`, not `__builtin_frame_address`, so its
  callers need no frame.
- **Sharing with the helper pool.** Jobs queue under the helper pool's lock,
  and finish through its done list and eventfd. The eventfd is opened by
  whichever pool starts first. Workers take ranges of `n / (8 * (threads +
  1))` items, at least 1.

### 6.2 Measured

8-core Ryzen (16 hardware threads), Linux, `-O`, wall and user time, single
runs while other sessions were active (load 2.5 to 3.5). `bench/par.lxl`
maps 64 chunks:

| kernel | 1 thread | 2 | 4 | 8 | speed-up at 8 | user time at 8 vs 1 |
|---|---:|---:|---:|---:|---:|---:|
| `hash`: strings built and counted in a Map | 0.437 s | 0.263 | 0.133 | 0.070 | 6.2 × | 1.19 |
| `decimal`: parse, sum, multiply and round | 0.772 s | 0.444 | 0.229 | 0.121 | 6.4 × | 1.18 |
| `format`: floats to text | 0.857 s | 0.441 | 0.218 | 0.115 | 7.5 × | 1.05 |

The user-time column is the price of a worker's paths: `str` counts out of
line, with the log for foreign blocks, and `malloc` and `free` through the
hooks.

**One call.** `calls` runs 100,000 maps of 8 trivial items:

- as a loop (`LXL_PAR=0`), 0.08 µs a call;
- with a pool, 0.8 µs a call at 2 threads and 1.6 µs at 8 (futex wakes, and
  the caller working too).

So `par.map` suits calls of tens of microseconds or more.

**Programs without `par.map`** (bench, `-O`, instructions against main):

| bench | instructions |
|---|---:|
| alloc | +1.4% |
| strings | +0.8% |
| trees | +1.7% |
| maps | +0.1% |
| lists | +2.0% |
| fib, sieve, loop | 0 |

Wall times are level within noise.

**Tests.** lib/tests: 7 run tests and 7 error tests (`par_*`) on both
backends:
- results;
- strings whose counts the main thread makes;
- other tasks running meanwhile;
- each refusal of the kernel pass;
- traps, overflow, stack overflow and Decimal's stop on workers.

Two stress programs, both with no leak under `LXL_CHECK=1` in any run:
- **Smaller:** 4 tasks mapping 300 rounds of up to 200 records with strings,
  Maps and arrays. The same output at the default pool size (6 runs), at
  `LXL_PAR` 1, 2 and 15, at `LXL_PAR=0`, and on the C backend.
- **Larger:** 600 rounds of up to 2,000 records. Its output matched
  `LXL_PAR=0`'s in every one of 85 runs at the default pool size, spread over
  the builds of stages 4 and 5.

### 6.3 Not done

- **The C backend** runs the loop. TSan therefore sees no pool, and the
  stress program and `LXL_CHECK` carry that weight.
- **Speed of a worker's paths.** Inline worker versions of dup and drop in
  kernel functions would recover some of the 5 to 19% user time.
- **Tiny maps.** No inline threshold by size: `par.map` cannot know an item's
  cost.
- **A `kernel` marker, and a `par` block or `par for`** (section 0).
