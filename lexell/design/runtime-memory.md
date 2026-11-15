# The native runtime: giving freed memory back to the system

Status: an exploration, 2026-11-12, for the user's decision. Nothing in the
runtime is changed. It follows lexdb's memory report (`lexdb.md` 9.99): a
server's RSS stays at its highest, because the native runtime's allocator
never gives memory back.

## 1. How the allocator works now

The allocator is `compiler/native/rt.c`, "the heap". lexdb uses it, not
glibc's: lexdb is linked dynamically, but imports no `malloc`.
- **Small blocks** (up to 64 kB) have 40 size classes. They are cut in turn
  from 1 MB chunks that are mapped and never unmapped. (Since 2026-11-15
  the chunks are 2 MB, on huge pages where the kernel allows them: section 6.) Each class has a free
  list threaded through its free blocks.
  - A free block goes back on its own class's list, and only that class
    reuses it.
  - A chunk is shared by every class, so a page holds blocks of many
    classes.
- **Large blocks** are each their own mapping, unmapped when freed. The
  last one freed, up to 32 MB, is kept for reuse.

So after a peak the small-block memory stays mapped and resident. Its free
blocks are reused only by allocations of the same class.

## 2. What could be given back: measured

A prototype added a report to `rt.c`. It walks every free list and counts,
per 4 kB page, the bytes covered by free blocks (their headers too) and by
chunks' unused ends. A page wholly covered holds nothing live, so it could
be returned (`madvise`) without moving anything. lexdb called the report at
shutdown, before the store closed, so its cache was still live. That is the
state of an idle server after a statement. Each run was 200k rows of
`(int, text)` on a fresh server:

| Workload | Peak | RSS idle | Small-block chunks | On free lists | **Wholly free pages** | Partly free pages | Large block kept |
|---|---|---|---|---|---|---|---|
| `INSERT ... SELECT` (streamed, 9.99) | 74 MB | 49 MB | 31 MB | 22 MB | **16 MB** | 13 MB | 14 MB |
| COPY FROM | 73 MB | 48 MB | 31 MB | 22 MB | **16 MB** | 13 MB | 14 MB |
| then `SELECT ... ORDER BY code` (held and sorted) | 218 MB | 210 MB | 199 MB | 190 MB | **184 MB** | 13 MB | 6 MB |

- **After a large held sort:**
  - 184 of 210 MB could go back: 88%. The live data is about 25 MB
    (the store's cache and the session).
  - Fragmentation costs only the 13 MB of partly free pages. Large
    transient allocations are made close together, so their pages empty
    together.
- **After a streamed load:** about 30 of 49 MB could go back (16 MB of
  pages, and the 14 MB large block kept).

The prototype is saved as a patch (`heapstat-prototype.patch`, in the
session's scratch folder). It only counts; it gives nothing back.

## 3. Ways to give memory back

**A. A scavenger over the free lists.** It runs at an idle point (below)
and changes nothing on `malloc`'s and `free`'s fast paths:
1. Walk the free lists and count each page's free bytes, as the prototype
   does.
2. Rebuild each list without the blocks that touch a wholly free page.
   Their memory is about to be zeroed, and with it the list's links.
3. `madvise(MADV_DONTNEED)` the runs of whole free pages. RSS drops at once.
4. Keep the runs in a page pool. When the current chunk is used up, the
   pool is cut from before a new chunk is mapped. The pages come back as
   zero pages on first touch.

The pool also lets memory freed by one size class serve another, which
today never happens.

**B. As A, with `MADV_FREE`.** The kernel takes the pages only under memory
pressure, and a page reused before then costs no fault. But RSS (and a
cgroup's count) shows them until they are taken. That misses the point of
the user's complaint, which was the RSS shown. It could be an option.

**C. Pages per size class, as mimalloc does.** Chunks aligned to their size,
with a header per page. Each page holds one class and has its own free list
and live count.
- A page whose last block is freed is free at once. It can be returned, or
  given to another class, with no scavenging pass.
- Fragmentation is lower, and locality better.
- But it rewrites the allocator and both its fast paths. Their speed is
  sensitive: `gen_rtx.py` notes that moving the allocator's code cost 26% of
  a benchmark's cycles. So the cost is the largest.

**D. Lower the peaks in the programs.** lexdb's streaming (9.99) is this.
Its held rows (about 890 bytes a row in a sort) are the next. It
complements A to C; it does not replace them, since some statement will
always hold something.

## 4. The trade-off

**What is gained.**
- RSS that follows live data rather than the highest point reached: here
  210 MB becomes about 26 MB.
- Memory for other processes, and a container's limit not used up by
  memory nothing uses.
- The user's measure of the server: the RSS they see.

**What it costs.**
- **Faults when memory is used again.** A returned page is zeroed and
  mapped again on first touch: about 1 to 2 µs a page, so about 0.3 to
  0.5 ms per MB. A server that repeats the same large sort would pay about
  60 to 90 ms each time for the 184 MB above, against a sort that takes
  hundreds of ms. Returning only memory that has stayed free for a while,
  and keeping a floor, bounds this (policy, below).
- **The pass itself:** it is proportional to the free blocks (1.2M after
  the sort above). It is estimated at a few ms to a few tens of ms, at a
  moment when nothing is waiting to run. Not measured.
- **Risk:** it is a change to the allocator of every Lexell program.
  - An error there corrupts memory far from its cause.
  - A's changes stay out of the fast paths: the pass, and the pool's use
    when a chunk runs out. The tests' `LXL_CHECK=1` leak counting and the
    compiler's fixed point exercise it.
- **No help with peaks:** the highest RSS is the same. Only how long it
  lasts changes. A machine must still have room for the peak.

**When to run it** (A and B):
- **When the scheduler is about to park with nothing to run** (all tasks
  waiting on sockets, disk or timers), and the bytes freed since the last
  pass are over a threshold, say 16 MB. A server is idle between
  statements, so this follows its load with no program changes. Go's
  background scavenger works on the same idea.
- **Keep a floor:** keep the larger of a fixed amount (say 32 MB) and a
  share of the recent peak (say a quarter of the last minute's highest use).
  Then a repeated workload faults only what it uses beyond it.
- **Let a program ask:** a library call (`runtime.trimHeap()`, say), so that
  a program can return memory at a point it knows, as glibc's `malloc_trim`
  does.
- **An environment switch to turn it off,** for measurements and in case of
  trouble.

## 5. Recommendation

- **Build A,** with `MADV_DONTNEED`, the page pool, the idle trigger, a
  floor and a switch. It gives back nearly everything there is to give in
  the cases measured (88% after a sort), and leaves the fast paths alone.
- **Keep C for later,** if fragmentation or the speed of the pass is shown
  to matter in a measured workload.
- **Go on with D in lexdb** in any case, starting with held rows.

**Measurements before it lands,** which need the user's go-ahead (they load
the machine):
1. The pass's time at 1M and 10M free blocks.
2. The allocator benchmark (`bench alloc`), to show the fast paths
   unchanged.
3. A repeated large sort with and without A, for the cost of the faults.
4. lexdb's suite and the compiler's fixed point, with `LXL_CHECK=1`.

## 6. Transparent huge pages (done, 2026-11-15)

**Before:** the kernel's setting here is `always`, but lexdb's heap was
almost all on 4 KB pages: 2 MB of 212 MB after a 1M-row load and sort. Each
1 MB chunk was its own mapping, so every 2 MB range was first touched half
at a time, in small pages, and the kernel could not fault a huge page in.
Its background merger (`khugepaged`) had not merged any 12 s later.

**Now** (`compiler/native/rt.c`, `heap_chunk`, `sys_mmap_thp`):
- Chunks are 2 MB, aligned to 2 MB (an over-sized mapping with its ends
  unmapped) and marked `MADV_HUGEPAGE`.
- Large blocks of 2 MB or more are rounded up to whole 2 MB, aligned and
  marked the same way.
- The kernel's setting (`/sys/kernel/mm/transparent_hugepage/enabled`)
  decides: under `always` or `madvise` the marked ranges get huge pages,
  under `never` the mark does nothing. The runtime does not read the
  setting (the first version did, and its open and read put a hello-world
  program over its size budget in `tests/run_native.py`).
- `LXL_THP=0` marks them `MADV_NOHUGEPAGE` instead: no huge pages for the
  heap even under `always`. The native backend only: the C backend's
  runtime (rt.h) is unchanged.
- Mapping a chunk moved out of `malloc`'s inline path (`heap_chunk`).

**Measured** (exp/hugepages, as an opt-in `LXL_THP=1` against off; lexdb on `bd_ob` (w, d, t, cr), the 35 queries
of `bench.py`, 5 runs each, off, on, off, on; Ryzen 7 8745HS, Zen 4;
data and scripts in `~/Work/lexdb-bench/hp`):

| | off | on |
|---|---|---|
| RSS after the queries | 569-571 MB | 570 MB |
| of it on huge pages | 0-2 MB | 538 MB |
| peak RSS | 621 MB | 626 MB |
| server CPU, geometric mean (34 queries) | | -1.4% |
| wall time, geometric mean | | -0.9% |

- 32 of 34 queries used less CPU; the largest gains were 3-4.5% (window,
  correlated subquery, left join, filters). Scans and the 20k point lookups
  moved less than 1%. The two off passes differed by up to 3% per query, so
  only the set's direction is significant.
- `perf stat` on five queries (points, hash join, window, scan, text
  group-by): instructions equal (66.5 G), cycles -4.2%, L1 data-TLB misses
  -60% (29.6 M to 11.9 M), page walks -71% (3.80 M to 1.09 M).
- **Why it is small:** with 4 KB pages there were only 0.06 walks per
  thousand instructions. lexdb reads columns mostly in order, and Zen 4's
  L2 TLB (3072 entries) also coalesces neighbouring 4 KB pages. Larger
  tables and more random access (big hash builds, lookups in a cache of
  several GB) should gain more; not measured.
- The lexdb suite passes with it on.

**Costs:**
- A thread heap's smallest mapping is 2 MB, not 1 MB (each par worker has
  one), whatever the kernel's setting; with huge pages it is also 2 MB of
  RSS at its first touch.
- The first touch of a chunk zeroes 2 MB at once. Under `defrag=madvise`
  (this machine's), a fault in a marked range may compact memory to find a
  free 2 MB page.

**For the scavenger (section 3, A):** `MADV_DONTNEED` on part of a huge
page splits it. The pass should give back runs of whole, aligned 2 MB (or
accept the split where only 4 KB pages are free), and the page pool should
hand out whole 2 MB chunks first.

## 7. Measured on the current 2 MB / THP allocator (2026-11-15)

The section 2 numbers predate the 2 MB chunks. This measures the current
allocator with its own report, on one CPU, with no lexdb and no `par`: a
Lexell probe allocates through `lxllib_alloc` and frees through `lxllib_free`
in a simple pattern, then the runtime reports what is free. Host: Ryzen 7
8745HS, `transparent_hugepage/enabled` is `always`. The instrumentation is
`experiments/heap_trim/`; it is not in the runtime.

| Probe | Chunks | Mapped | On free lists | 4 KiB pages free | Lost to page boundaries | Whole 2 MB chunks |
|---|---:|---:|---:|---:|---:|---:|
| 1M x 16 B, all transient | 16 | 32,768 KiB | 31,399 KiB | 32,768 KiB | 0 | **16 (32,768 KiB)** |
| 800k mixed sizes, all transient | 111 | 227,328 KiB | 227,101 KiB | 227,328 KiB | 0 | **111 (227,328 KiB)** |
| 20k live, then 800k transient freed | 14 | 28,672 KiB | 25,149 KiB | 25,792 KiB (90%) | 16 KiB (5 blocks) | **12 (24,576 KiB, 86%)** |
| live block every 50th, transient freed | 14 | 28,672 KiB | 24,648 KiB | 2,004 KiB (7%) | 11 KiB (9 blocks) | **0** |
| 20 batches with live clusters between | 17 | 34,816 KiB | 31,398 KiB | 31,896 KiB (92%) | 1 KiB (40 blocks) | **0** |

The 4 KiB column is the count if every page covered wholly by free blocks is
returned; the "lost" column is the free bytes on the other side of a page
boundary, which a page-level pass would drop with the block it unlinks. It is
small: 1 KiB in the `batches` probe, 16 KiB in the live-before one.

**The whole-chunk prototype.** `lxllib_heaptrim` returns every whole, 2 MB,
wholly free chunk but the current one, `MADV_DONTNEED`s it, and pools it for
reuse. Measured with `VmHWM`/`VmRSS` from `/proc`:

| Probe | Chunks before -> after | Heap before -> after | VmHWM | VmRSS after |
|---|---:|---:|---:|---:|
| 1M x 16 B, all transient | 16 -> 1 | 32,768 -> 2,048 KiB | 40.0 MiB | 10.1 MiB |
| 20k live, then 800k transient | 14 -> 3 | 28,672 -> 6,144 KiB | 36.2 MiB | 14.2 MiB |
| 20 batches with live clusters | 17 -> 17 | 34,816 -> 34,816 KiB | 42.2 MiB | 42.2 MiB |

`VmHWM` stays at the peak, as the kernel keeps it. A refill after a trim
reused the pooled chunks and reached the same 16 chunks, with no failure and
no lost block. Re-touching 30 MiB of returned chunks cost 10.0 ms, or 0.33 ms a
MiB (median of five: 18.9 ms without the trim, 28.9 ms with it, for the same
two fills of 1M).

**Pass cost.** One trim of 1M free blocks (32 MiB) took 8.5 ms (the difference
between fill+free and fill+free+trim, seven runs). The report, which walks the
lists twice, took 11 ms at 1M, 25 ms at 2M and 55 ms at 4M: the walk is
dominated by cache misses over the free lists, not by the 4 KiB page scan.

**What it means.**

- If the live set is compact and a burst is allocated after it, whole 2 MB
  chunks give back 86 to 100% of the heap with **no THP split and no lost free
  bytes**. That is the section 2 `INSERT/SELECT` and held-sort shape; the 90% here
  is close to the 88% there.
- If live blocks are scattered through the chunks, whole chunks give back
  **nothing** (`batches`: 0 of 17), while 4 KiB pages give back 92%. That is
  the case in which the page pool is essential, and in which returning pages
  splits huge pages.
- The straddling-block loss is negligible (1 to 16 KiB), so the page-level
  pass's real cost is the split, not the abandoned bytes.

So the section 3 recommendation stands, with an order now: **whole 2 MB
chunks first** (simple, no split, no loss), then page-level only if a
measurement of lexdb shows that its cache leaves many pages free in chunks
that are not wholly free. The probes above say that can happen, but they are
synthetic; lexdb's own layout after a held sort and after a load is the next
measurement, and it needs the user's go-ahead because it loads the machine.
If lexdb's cache is scattered, a programme-level fix (allocate the page cache
in its own large blocks or arena, so transient chunks stay whole) may be
cheaper than splitting every huge page.

## 8. Chunk-local free lists: the no-scan retire (experiment, 2026-11-15)

The measurement in section 7 says lexdb's live cache can be scattered through
many chunks, but it also says a large transient heap leaves whole chunks free:
after a 1M-row streamed insert, 37 of 80 chunks were wholly free (75,776 of
163,840 KiB). The next step is to return those with no scan and no
multi-millisecond pass.

**Why a scan is not needed.** A per-chunk live count alone only says *which*
chunk is free; its blocks are still threaded through the heap's global
per-class lists, so taking them out means walking those lists. The experiment
moves the free-list heads **into the chunk**: each chunk has its own 40 free
lists, a live count and the links that put it on a per-class list of chunks.
Then a wholly free chunk is detached with O(40) pointer updates, not a walk
of a million blocks. The current chunk keeps its free lists in the heap for
the fast path (`cur_free`, `cur_live`); when it fills, they move into its
header, and a new chunk is carved.

**Retirement.** A chunk whose live count reaches zero goes on a per-heap
retire queue. Nothing is unmapped on the free path. `lxllib_heaptrim()`
retires one queued chunk: it detaches its class lists, `MADV_DONTNEED`s its
2 MiB, and keeps the mapping for `heap_chunk` to reuse. With the trim on by
default, the event loop calls it after 300 ms with nothing runnable
(`LXL_TRIM_MS` sets the delay; `LXL_TRIM=0` turns it off), with a queue floor
of 4 chunks (8 MiB) and a budget of 250 µs per park; a chunk costs one
`madvise`, not a scan. Retiring the 15 wholly free chunks of the
1M allocation probe added less than 0.1 ms to the run (median 11.9 ms with
the trim against 11.8 without, inside the noise): a chunk is a list detach
and one 2 MiB `MADV_DONTNEED`.

**Measured on lexdb** (one CPU, `LXL_PAR=0`, cache 64 MB, one 1M-row table;
trim on, report at shutdown):

| State | Chunks before -> after | Heap before -> after | VmHWM | VmRSS before -> after |
|---|---:|---:|---:|---:|
| 1M-row `INSERT ... SELECT`, idle | 80 -> 40 | 163,840 -> 81,920 KiB | 346 MB | 210 -> 113 MB |
| 200k-row insert, idle | 18 -> 18 | 36,864 KiB | 87 MB | 64 -> 64 MB |
| 1M rows, restart, `SELECT ... ORDER BY` | 20 -> 20 | 40,960 KiB | 278 MB | 56 MB |

The 1M case is the reported one: **97 MB of RSS returned**, 40 chunks kept
(33 MB of them the live cache). The 200k case shows the limit: its 6 MB cache
is scattered through all 18 chunks, no chunk is wholly free, and the trim has
nothing to take. The 1M held sort mostly uses large blocks (already unmapped
on free); the remaining 20 chunks are the cache.

The page-level report on the 1M insert still sees 106 to 109 MB on wholly
free 4 KiB pages, of which 15.7 MB would be lost at page boundaries; whole
chunks already return 76 MB of that. So chunk-local retire gets the bulk of
this workload at no lost bytes and no huge-page split; pages add about 20 MB
net, at those costs.

**Fast path.** The current-chunk lists keep the common path close to the old
one; the old one list per class is still there for blocks in earlier chunks.
`bench alloc` (8M alloc/free pairs): 26.4 -> 29.8 ms best, 28.6 -> 30.4 ms
median (+6.5%); `strings` +2.9%; `maps` +0.9%. `perf stat` on alloc: +10.6%
instructions, +3.1% cycles. The hello-world build is 624 bytes larger
(20,512 bytes; its test budget is 20,544). All 648 native and library tests
pass, including `LXL_CHECK=1`; lexdb with its usual par workers (16 CPUs) runs
the 1M sort and keeps 20 chunks.

**Limits and next.**

- Only wholly free chunks are returned. A small heap whose live cache is
  spread through every chunk (the 200k case) gains nothing. Page-level
  ownership, or giving the cache its own arena, is still the answer there.
- Worker heaps get the chunk-local lists but no trim: their queues are not
  retired. Blocks that move between heaps go to a per-heap legacy list, and a
  chunk that has lent one never reaches zero; that is conservative and safe.
- The `hp_chunk`, `hp_freechunk`, `lxllib_heapstat` and trim hooks are
  experiment code (about 1 MB of BSS); a production version should keep only
  the chunk header, the retire queue and a small trim entry point, and remove
  the report arrays.
- The floor of four chunks and the 250 µs budget are guesses; the next
  measurement is a repeated-sort loop and a container memory limit, to see
  whether the floor causes refault thrash.

## 9. The applications, before and after (2026-11-15)

The microbenchmark above is the worst case for the allocator: one allocation
and one free, nothing else. This measures the same programs a user runs.

**Method.** Two compilers: the baseline is `main`'s seed (the old runtime);
the new one is this branch's seed. Both build the same source with
`-O --native`, on one core (`taskset -c 4`), output discarded, seven runs,
median wall time and the child's `ru_maxrss`. Inputs: the 20 MB JSON from
`bench/json/gen_data.py`, the 3 MB regex corpus, 10 MB of Markdown, and the
source tree for `eza --tree -L 4`.

**Command-line programs.**

| Program | Base | New | Time | Base RSS | New RSS |
|---|---:|---:|---:|---:|---:|
| `jq -c .` (20 MB JSON) | 247.1 ms | 252.6 ms | +2.2% | 128.6 MB | 128.6 MB |
| `json_bench` (20 MB, 5 reps) | 1793 ms | 1811 ms | +1.0% | 307.6 MB | 307.6 MB |
| `regex_bench` (3 MB, 5 reps) | 170.1 ms | 171.8 ms | +1.0% | 30.4 MB | 30.4 MB |
| `grep -c` (3 MB) | 1.48 ms | 1.48 ms | +0.3% | 8.2 MB | 8.2 MB |
| `sort` (3 MB) | 10.01 ms | 9.99 ms | -0.2% | 9.0 MB | 9.0 MB |
| `eza --tree -L 4` | 4.09 ms | 4.09 ms | 0.0% | 8.2 MB | 8.2 MB |
| `cmark` (10 MB) | 75.4 ms | 76.0 ms | +0.8% | 108.3 MB | 108.3 MB |

The +6.5% of `bench alloc` is not what applications see: they spend most of
their time elsewhere, and the change is under 2.2% here. Peak RSS is
unchanged, as expected: these are short-lived programs that never reach the
event loop's idle point, so no chunk is retired, and the per-chunk header is
1 KiB a chunk.

**lexdb, one server** (`LXL_PAR=0`, cache 64 MB, a 1M-row table with a primary
key; query medians of three; RSS after 2.5 s idle):

| | base | new | new, trim on (default) |
|---|---:|---:|---:|
| insert 1M rows | 1.4 s | 1.4 s | 1.4 s |
| `count(*)` | 8.7 ms | 8.9 ms | 9.3 ms |
| `sum(id)` | 17.7 ms | 17.6 ms | 17.9 ms |
| 100k point joins | 134.2 ms | 132.4 ms | 131.3 ms |
| sort 100k rows | 312.5 ms | 298.9 ms | 299.5 ms |
| filtered count | 48.7 ms | 48.3 ms | 50.4 ms |
| RSS after insert | 210.0 MB | 210.1 MB | **138.1 MB** |
| RSS after queries | 200.6 MB | 200.7 MB | **128.7 MB** |
| peak RSS | 341.0 MB | 341.1 MB | 341.0 MB |

The trim is now the default, after 300 ms with nothing to run (the table's
trim column was measured with `LXL_TRIM=1`, which that delay makes the
default; a fresh 1M run with no variable set settled at 139.1 MB after three
seconds idle, against 214.9 MB with `LXL_TRIM=0`). `LXL_TRIM_MS=n` changes
the delay. Query time is unchanged; the differences are noise (the sort is
slightly faster on the new runtime). The trim returns **72 MB** of steady-state RSS
after the insert and after the queries, and **not** the peak: the highest
point is the same 341 MB, as section 7 said. The 250 µs idle pass is not
visible in these latencies.

Two things this does not settle: a repeated large-sort loop (to see the
refault cost and the 4-chunk floor), and a memory-limited container (where
the peak, not the steady state, is the limit).


