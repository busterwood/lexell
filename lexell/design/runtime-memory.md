# The native runtime: giving freed memory back to the system

Status: an exploration, 2026-11-12, for the user's decision. Nothing in the
runtime is changed. It follows lexdb's memory report (`lexdb.md` 9.99): a
server's RSS stays at its highest, because the native runtime's allocator
never gives memory back.

## 1. How the allocator works now

The allocator is `compiler/native/rt.c`, "the heap". lexdb uses it, not
glibc's: lexdb is linked dynamically, but imports no `malloc`.
- **Small blocks** (up to 64 kB) have 40 size classes. They are cut in turn
  from 1 MB chunks that are mapped and never unmapped. Each class has a free
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
