# heap_trim: the probes behind runtime-memory.md sections 7 and 8

This branch carries the experimental chunk-local allocator itself, not a patch:
`native/rt.c` has the per-chunk free lists, the live counts, the retire queue
and the idle trim; `native/lxlrt.h` declares `lxllib_heapstat` and
`lxllib_heaptrim`. The report and trim arrays (`hp_chunk`, `hp_freechunk`,
the 64k-entry each) are experiment code and about 1 MiB of BSS.

## Build

    lexell/compiler/build.sh
    lexell/compiler/out/lxlc lexell/compiler/main.lxl --native -o /tmp/lxlc-exp

Then, for each probe:

    LXL_LIB="$PWD/lexell/lib" /tmp/lxlc-exp \
        lexell/design/experiments/heap_trim/same.lxl --native -o /tmp/same
    /tmp/same

The report goes to stderr. `reuse.lxl` and `chunk_trim.lxl` print reports
around a trim and a refill.

## Runtime entry points

- `lxllib_heapstat()` walks the main heap's chunks and prints the bytes on
  wholly free 4 KiB pages, the bytes a page-level pass would lose at page
  boundaries, and the whole 2 MiB chunks that are wholly free. It also prints
  how many chunks are queued to retire.
- `lxllib_heaptrim()` retires **one** queued chunk: detach its per-class
  lists, `MADV_DONTNEED` its 2 MiB, pool it for reuse. Returns 1 if it took a
  chunk off the queue, 0 when the queue is empty. It is O(NCLASS), no scan.
- The trim is on by default: the event loop calls `lxllib_heaptrim()` after it
  has been idle for 300 ms (`LXL_TRIM_MS=n` changes the delay; `LXL_TRIM=0`
  turns it off), only while the queue holds at least four chunks, with a 250 µs
  budget per park.

## Probes

| File | Allocation pattern |
|---|---|
| `same.lxl` | 1,000,000 allocations of 16 bytes, all freed at once |
| `mixed.lxl` | 800,000 allocations of mixed sizes (8 to 504 bytes), all freed |
| `live_before.lxl` | 20,000 live blocks, then 800,000 16-byte blocks, the latter freed |
| `interleave.lxl` | 800,000 transient blocks with a live block every 50th, transient freed |
| `batches.lxl` | 20 rounds of 50,000 transient blocks with 1,000 live blocks between; all transient freed at the end |
| `reuse.lxl` | fill, free, trim all, fill again: the trim's chunks are reused |
| `chunk_trim.lxl` | fill, free, trim all, report, refill, free, report |

The numbers they produced are in `../runtime-memory.md` sections 7 and 8.

## lexdb

`lexell/cmd/lexdb.lxl` on this branch has, guarded by `LXL_HEAPSTAT`, an
extern `heapReport` and a loop of `heapTrim` at shutdown (before the store
closes, so the cache is still live). A 1M-row measurement:

    rm -rf /tmp/lexdb-h && mkdir /tmp/lexdb-h
    LXL_PAR=0 LEXDB_CACHE_MB=64 LXL_HEAPSTAT=1 \
        /tmp/lexdb-exp /tmp/lexdb-h 127.0.0.1:55432 &
    psql "host=127.0.0.1 port=55432 user=me dbname=lexdb" \
        -c "create table t (id int, code text)" \
        -c "insert into t select i, 'ABC' || i from generate_series(1, 1000000) i"
    # sample VmRSS here, then SIGTERM the server

The trim is on by default and is what retires the chunks at idle; `LXL_TRIM=0`
leaves the heap at its peak. The 1M insert went from 210 MB RSS to 113 MB, 80
chunks to 40.
