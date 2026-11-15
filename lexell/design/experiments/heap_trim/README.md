# heap_trim: the probes behind runtime-memory.md section 7

The instrumentation is not part of the runtime. It adds two experimental entry
points to `native/rt.c` and records the main heap's 2 MB chunks:

- `lxllib_heapstat()` walks the free lists and reports, per 4 KB page, how many
  bytes are covered by free blocks and unused chunk ends. It prints the bytes on
  wholly free pages, the bytes that a page-level return would lose at page
  boundaries, and the number of whole 2 MB chunks that are wholly free.
- `lxllib_heaptrim()` is a prototype of the whole-chunk policy: it returns every
  whole, 2 MB, wholly free chunk but the current one with `MADV_DONTNEED`, keeps
  them in a pool, and lets `heap_chunk` reuse them.

It walks the main heap only: a program with `par` workers would need the worker
heaps too, so the probes do not use `par`.

## Build

From the branch this directory is on (the patch applies to the commit that adds
this directory):

    git apply lexell/design/experiments/heap_trim/heap-trim.patch
    python3 lexell/compiler/gen_rtx.py
    lexell/compiler/build.sh
    lexell/compiler/out/lxlc lexell/compiler/main.lxl --native -o /tmp/lxlc-exp

Then, for each probe:

    LXL_LIB="$PWD/lexell/lib" /tmp/lxlc-exp lexell/design/experiments/heap_trim/same.lxl \
        --native -o /tmp/same
    /tmp/same

The report goes to stderr. `reuse.lxl` prints its three reports around a trim;
the report of a program with no chunks says so.

## Probes

| File | Allocation pattern |
|---|---|
| `same.lxl` | 1,000,000 allocations of 16 bytes, all freed at once |
| `mixed.lxl` | 800,000 allocations of mixed sizes (8 to 504 bytes), all freed |
| `live_before.lxl` | 20,000 live blocks, then 800,000 16-byte blocks, the latter freed |
| `interleave.lxl` | 800,000 transient blocks with a live block every 50th, transient freed |
| `batches.lxl` | 20 rounds of 50,000 transient blocks with 1,000 live blocks between; all transient freed at the end |
| `reuse.lxl` | fill, free, trim, fill again: the trim's chunks are reused |

The numbers they produced are in `../runtime-memory.md` section 7.

Remove the experiment by reverting `native/rt.c` and `native/lxlrt.h` and
regenerating `rtx.lxl`; it is not for merging.
