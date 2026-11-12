<!-- The page-layout study, 2026-11-12: by a Fable subagent for lexdb-engines.md. Marks: [M] measured, [C] computed from the real pages, [E] estimated. Its prototype patch (against 25a7b4e2) and scripts are kept in ~/Work/lexdb-bench/saved/ (pages-prototype.patch, pages/). -->

# lexdb page layout: compression and column leaves, measured

2026-11-12. Code: branch `lexdb` at 25a7b4e2. Data: `vec/ldata` (w 1M rows, t 1M rows, d 1,000 rows).
Every number is marked **[M]** measured, **[C]** computed from the real pages, **[E]** estimated from measured parts, or **[old]** from the old branch's notes.

## Answers in short

- **Would page compression save I/O?** Bytes, yes: 1.8 times (lz4) to 2.5 times (zstd) per 4 KiB leaf of w [M]. Time, no: on this NVMe a cold scan is mostly CPU, not disk wait.
- **Would it make queries faster?** No. Warm queries are unchanged at best. A cold sequential scan gains about 6% with lz4 and loses about 40% with zstd [E]. A copy of the data file that btrfs had already compressed with zstd read 5 to 14% slower cold than the uncompressed copy [M].
- **Would column leaves (PAX) with light encodings be faster?** Yes. With the prototype in the real executor, scan-bound queries ran 13 to 42% faster and wide scans 6 to 10% faster [M]. The table gets 45% smaller [C].
- **Point reads and writes:** a point read's decode is the same or slightly faster [M]. A write costs up to about 27 µs more CPU per dirty leaf per checkpoint with the unoptimised prototype encoder [M parts, E total].
- **Build first:** column leaves for table trees. Separately and cheaply, front-code the secondary index leaves and drop their duplicated value. Do not build page compression now.

Two corrections to the brief:
- **Numeric is already binary** in the fixed layout (`Decimal.toBin`, 9.50). A price in w is 6 bytes: flags, scale, exponent, 3 coefficient bytes [M, read from the pages].
- **Decoding is more than 10 to 30% of a scan.** Counting `bRunInto` with its helpers (`rt_str_view`, `valView`, `fixedVal`, `fromBin`), it is about 40% of `expr_agg` and about 60% of `filt1pct` [M, perf with the symbol map].

## 1. Space

### Now [M]

| Tree | Rows | Pages | MB | Bytes/row on disk | Leaf fill | Rows/leaf |
|---|---:|---:|---:|---:|---:|---:|
| w (table) | 1,000,000 | 23,332 | 95.6 | 95.6 | 98.5% | 43.1 |
| w_b (index) | 1,000,000 | 10,339 | 42.3 | 42.3 | 69.7% | 97.8 |
| t (table) | 1,000,000 | 7,644 | 31.3 | 31.3 | 99.6% | 131.4 |
| d (table) | 1,000 | 10 | 0.04 | 41.0 | 92.4% | 111 |

- The data file is 169.3 MB (41,335 pages). The other 128 MB of the 290 MB directory are two preallocated 64 MB log segments.
- A w leaf entry is 93.3 bytes: 4 of lengths, 8 of key, 81.3 of value.
- The value: header 5 (tag, layout, NULL bitmap), id 4, a 4, b 4, c 8, name 13.0, city 7.5, price 7.9, flag 1, note 27.0. The id is stored twice, in the key and in the row.
- A w_b entry is 29 bytes: 4 of lengths, a 17-byte key, an 8-byte value. The value equals the key's last 8 bytes in all 1,000,000 entries.

### Against PostgreSQL 18.6 and SQLite 3.54 [M]

| | lexdb | PostgreSQL | SQLite |
|---|---:|---:|---:|
| w rows | 95.6 MB (clustered on the key) | 108.3 heap + 22.5 pkey = 130.8 | 77.3 |
| w_b index | 42.3 | 9.3 | 11.7 |
| w total | 137.9 | 140.1 (`pg_total_relation_size`) | 89.0 |
| t total | 31.3 | 44.3 heap + 22.5 pkey = 66.8 | 18.0 |
| Whole file | 169.3 | | 107.0 |

lexdb's rows are smaller than PostgreSQL's, but its secondary index is 4.5 times PostgreSQL's.

### What each option saves on w

Leaf bytes per row; today 93.3.

| Option | Bytes/row | Saving | Source |
|---|---:|---:|---|
| Front-coded keys (the old branch's format) | 87.8 | 5.9% | C |
| PAX, no encodings (the old branch's milestone 1) | 81.5 | 12.6% | C |
| PAX, byte-aligned frame of reference, dictionary, numeric as units | 58.3 | 37.5% | C |
| PAX, bit-packed, plus a shared text prefix | 51.2 | 45.2% | C |
| The same, leaves refilled to 4 KiB | 12,159 leaves, 82 rows each | 47.7% fewer pages | C |
| lz4 per 4 KiB page | 52.5 | 1.78 times | M |
| zstd-1 per 4 KiB page | 36.6 | 2.55 times | M |
| zstd-1 per page, pages kept on 512-byte sectors | 47.0 | 1.99 times | M |
| zstd-1 on 16 KiB / 64 KiB blocks | 32.1 / 30.7 | 2.91 / 3.04 times | M |
| PAX bit-packed, then zstd-1 per page | 29.3 | 3.2 times | M |
| PAX bit-packed, then zstd-1 with a 16 KiB trained dictionary | 21.8 | 4.3 times | M |
| btrfs `compress=zstd:3` on a copy-on-write copy, whole file | | about 3.6 times | E (zstd-3 on 128 KiB extents, rounded to 4 KiB; `compsize` is not installed; `filefrag` shows the extents encoded) |

Per column in bit-packed PAX, bytes per row, today to PAX [C]:
- **Integers:** id 4 to 0.98, a 4 to 1.03, b 4 to 2.35, c 8 to 5.21.
- **Texts:** name 13.0 to 3.7 (shared prefix), city 7.5 to 3.65 (dictionary), note 27.0 to 26.1 (nothing light helps).
- **Others:** price 7.9 to 2.74 (units in 20 bits), flag 1 to 0.14.
- **Keys:** 12 to 4.5 with front coding. A frame of reference on the key would take about 1.
- **Run-length encoding** gains nothing on these tables: no column has runs.
- After PAX, note is half of what is left. Only a general codec shrinks it.

Other trees [C]:
- **t:** front coding saves 17.9%; bit-packed PAX saves 68% (30.9 to 9.8 bytes/row); zstd-1 per page gives 5.8 times. Its `code` is 'ABC' plus the id, so these flatter the encodings.
- **w_b:** front coding takes an entry from 29 to 17.2 bytes (40.5%). Dropping the duplicated value as well gives 9.2 bytes (68%).

### Codec speed on real w leaf pages [M]

One thread, median of 5 passes, spread under 10%.

| Codec, per 4 KiB page | Ratio | Compress MB/s | Decompress MB/s | Compress µs/page | Decompress µs/page | Decompress ns/row |
|---|---:|---:|---:|---:|---:|---:|
| lz4 | 1.78 | 1,140 | 5,756 | 3.5 | 0.70 | 16 |
| lz4hc-9 | 1.88 | 214 | 5,632 | 18.8 | 0.71 | 17 |
| zstd-1 | 2.55 | 387 | 909 | 10.4 | 4.42 | 103 |
| zstd-3 | 2.51 | 333 | 879 | 12.1 | 4.57 | 106 |
| zstd-9 | 2.51 | 83 | 898 | 48.2 | 4.48 | 104 |
| zstd-19 | 2.78 | 11 | 824 | 372 | 4.88 | 113 |
| zstd-1 with dictionary | 2.69 | 330 | 930 | 12.2 | 4.32 | 100 |

## 2. I/O against CPU

**Method.** The scratch folder was RAM when I started, so all disk measurements were made on the NVMe (WD Blue SN570, under LUKS, btrfs), in a NOCOW directory: lexdb's default O_DIRECT, and buffered mode with `posix_fadvise(DONTNEED)` before each start (`fincore` confirmed 0 bytes cached). A fresh server per cold run, 5 runs each. Run three times: twice before the reboot and once after. The run after the reboot was noisier and the disk slower.

### The disk, fio with O_DIRECT on the data file [M]

| Read pattern | Before the reboot | After the reboot |
|---|---:|---:|
| Sequential 256 KiB (lexdb's read-ahead size) | 1,970–1,990 MB/s, 2.1 µs per page | 1,580–1,600 MB/s, 2.5 µs |
| Sequential 4 KiB | 171 MB/s, 23 µs | 171 MB/s |
| Random 4 KiB, one at a time | 65 µs | 90 µs |

### Cold against warm [M]

Wall ms, median (range over the three runs' medians where they differ).

| Query | Warm | Cold, O_DIRECT | Cold, buffered | Cold, btrfs-zstd copy, buffered |
|---|---:|---:|---:|---:|
| `count(*)` from w | 24 | 156–174 | 121–122 | 128–139 |
| `expr_agg` | 66 | 201–218 | 162–165 | 173–183 |
| `grp_text` | 191–194 | 328–348 | 288–296 | 301–310 |
| `count(*)` from t | 14 | 71–73 | 53–55 | 52–56 |
| `idx_range_agg` (100K rows through w_b) | 162 | 1,299–1,595 | 711–919 | 563–586 |

- **A cold sequential scan of w costs 132 to 150 ms more than warm,** for 23,332 pages: 5.7 to 6.4 µs a page.
  - 79 to 84 ms of that is server CPU (3.5 µs a page): installing pages, the CRC, page faults.
  - 55 to 66 ms is waiting for the disk (2.4 to 2.8 µs a page).
- **So compression can save at most the disk wait times (1 − 1/ratio)** [E]:
  - lz4: saves up to 1.1 µs and costs 0.7 µs a page. Net about 10 ms of 160, 6% faster at best.
  - zstd-1: saves up to 1.6 µs and costs 4.4 µs a page. Net about 65 ms slower, 40%.
- **Check against a real compressed file:** the btrfs-zstd copy reads 3.6 times fewer bytes and its cold scans are 5 to 14% slower than the uncompressed buffered copy [M].
- **Random reads are different.** The cold index query pays 49 to 61 µs per leaf read [M]. That is latency, not bytes, so a compressed 4 KiB page saves nothing; only fewer pages help. Column leaves refilled to 82 rows halve w's leaves; the cold index query would go from about 1,300 ms to about 760 ms [E].

### Cache capacity

- **Rows per cache byte.** A cached w leaf costs 4,521 bytes (`nodeCost`), 105 bytes a row. A refilled column leaf holds 82 rows in about the same space: 1.77 times the rows [C]. A cache of compressed pages would hold 1.8 times (lz4) or 2.5 times (zstd) but pay 0.7 or 4.4 µs on every access.
- **What a miss costs [M].** 20,000 random primary-key reads, repeated, O_DIRECT; the leaves they touch take about 60 MB of cache.

| Cache | µs per query, before / after reboot |
|---|---:|
| 64 MB and over (all hits) | 32 / 36 |
| 48 MB | 94 / 104 |
| 32 MB | 110 / 125 |
| 16 MB | 127 / 141 |
| First pass, all misses | 106 / 130 |

  A miss costs 74 to 95 µs. Replaying the same reads through a cache 20% too small missed on about 80% of them, far more than the 20% a uniform model predicts.
- **What 1.77 times buys.** For a densely used working set, a cache that is up to 1.77 times too small becomes large enough. For sparse random reads the gain is smaller: these 20,000 reads would touch about 9,800 refilled leaves instead of 13,400, 20% less cache [E].

## 3. Scan speed in memory

**Prototype.** PAX leaves built in Lexell from w's real leaves, with a decoder (`pxRunInto`) that fills the executor's real `Batch`. Timed against the real `bRunInto` on the same rows, and against a tuned row decoder (`rfRunInto`: no view per row). Checksums of every batch match. Codecs: frame of reference (bit-packed or whole bytes), bitmap, dictionary with byte codes, text with 2-byte ends, optional shared prefix, numeric as units plus a scale.

### Decode alone [M]

ns per row, 1M rows, median of 7; spread under 5% except the 3 ns cells.

| Columns | Rows today | Rows, tuned | PAX bit-packed, same leaves | PAX whole bytes, same leaves | PAX bit-packed, 82 rows/leaf |
|---|---:|---:|---:|---:|---:|
| none (`count(*)`) | 15.0 | 12.5 | 0.3 | 0.3 | 0.2 |
| a | 19.5 | 18.1 | 3.0 | 3.5 | 2.4 |
| a, b | 24.2 | 22.5 | 8.4 | 8.2 | 5.5 |
| a, b, c | 30.6 | 30.5 | 13.9 | 15.3 | 11.4 |
| flag | 18.3 | 18.9 | 5.7 | 4.6 | 3.7 |
| city (dictionary) | 48.2 | 35.2 | 28.6 | 28.4 | 24.4 |
| price (numeric) | 63.3 | 54.1 | 37.5 | 37.2 | 35.1 |
| name | 46.2 | 34.4 | 21.9 | 22.0 | 19.0 |
| name, with shared prefix | | | 30.5 | | 29.4 |
| id, b, name (`scan3`) | 56.0 | 45.3 | 28.2 | 28.5 | 25.8 |
| city, price (`grp_text`) | 95.9 | 77.4 | 64.4 | 65.2 | 59.7 |
| `*` | 180.7 | 150.1 | 123.7 | 125.6 | 116.9 |

- **1 to 3 integer columns: 2.2 to 6.5 times faster.** `select *`: 1.45 times.
- **Where the gain comes from.** The row format must touch every row, about 12 to 15 ns a row before any column is read: the whole 93 MB passes through the processor's cache. The tuned row decoder barely helps, so this is the layout, not the code.
- **The encodings cost little.** Bit unpacking is as fast as whole bytes, or faster. A dictionary is no slower than plain text.
- **The shared prefix is slower** (30.5 against 21.9 ns): each value must be joined into a new string. It saves 8 bytes a row. Leave it out of a first version.
- **Texts and numerics gain least:** making a `Val` per row dominates.

### Working on dictionary codes [M]

Micro-benchmark, same rows, ns per row including the decode.

| | Rows today | PAX values | PAX codes, 43 rows/leaf | PAX codes, 82 rows/leaf |
|---|---:|---:|---:|---:|
| `GROUP BY city` (hash map, count) | 74.5 | 56.2 | 17.0 | 8.7 |
| `WHERE city = 'Oslo'` (count) | 52.3 | 34.3 | 7.6 | 2.9 |

4 to 9 times faster on codes for GROUP BY and 7 to 18 times for the filter. The dictionary is per leaf, so each leaf maps its 20 entries first; fuller leaves gain more. This is not wired into the executor.

### End to end [M]

The prototype hooked into `fillBatch` (`LEXDB_PAXPROTO=w:bits`): scans of w decode from PAX leaves held in memory beside the row leaves. Results are identical to the unhooked server on all 29 queries. `vec/bench.py`, 5 runs, wall ms median (min–max). "Off" is the same binary without the variable.

| Query | Off | PAX bit-packed | Ratio |
|---|---:|---:|---:|
| `count` | 24 (24–25) | 14 (14–14) | 0.58 |
| `filt1pct` | 77 (76–78) | 51 (51–51) | 0.66 |
| `filt10pct` | 91 (91–92) | 66 (65–66) | 0.73 |
| `filt_agg` | 35 (35–41) | 27 (27–27) | 0.77 |
| `expr_agg` | 69 (68–69) | 54 (54–54) | 0.78 |
| `join_hash_rows` | 63 (63–64) | 50 (50–51) | 0.79 |
| `grp_int`, `join_hash_agg` | 56 | 45 | 0.80 |
| `minmax_text` | 123 (122–123) | 99 (99–100) | 0.80 |
| `filt_like` | 142 (141–142) | 116 (116–116) | 0.82 |
| `grp_text` | 193 (193–193) | 168 (168–171) | 0.87 |
| `scan3` | 212 (211–220) | 190 (189–194) | 0.90 |
| `expr_int` | 196 (193–197) | 182 (180–183) | 0.93 |
| `scan9` | 742 (739–762) | 699 (694–728) | 0.94 |
| `sort_lim`, `sub_corr_sel` | 405, 234 | 384, 222 | 0.95 |
| `distinct`, `distinct2`, `join_lookup_agg`, `sub_in` | | | 0.97–0.98 |
| `expr_mix`, `sort_all`, `window`, `sub_exists`, `pk_point20k`, index ranges, `scan2` | | | 0.99–1.01 |

- The hook takes a lock and a closure call per leaf, so real column leaves would do slightly better.
- The whole-byte variant gains less end to end (for example `filt1pct` 57 ms, `expr_agg` 62 ms).
- Queries bound by sorting, hashing, expression evaluation or the wire do not move. `scan2` reads t, which the hook does not cover.
- The qL.txt list was not run separately. Of its queries not in the table, only `join_text_agg` scans w and would gain; `join_hash_sort` is sort-bound.

## 4. Point reads and writes

### Point read [M]

| Step | Cost |
|---|---:|
| Decode one row's 9 columns, row format (`decFixed`) | 467 ns |
| The same from a PAX leaf (`pxRow`) | 381–455 ns |
| `pk_point20k` end to end, PAX hook on or off | 630 / 632 ms (the hook does not touch lookups) |
| A whole point query, server CPU | 31 µs |
| Page read into a lazy leaf: `decodeNode` + CRC | 0.85 + 0.51 µs |
| Decompress on a miss: lz4 / zstd-1 | + 0.7 / 4.4 µs, on a miss that costs 74–95 µs |

Neither PAX nor compression changes a point read measurably, provided the cache holds decoded pages. Bit-packed columns are read at a computed offset, so one row needs no leaf decode.

### Writes

Today, on a fresh copy, 20,000 single-row statements [M]:

| Statement | Server CPU per statement |
|---|---:|
| `UPDATE` one column by key | 64 µs |
| `INSERT` (ascending or scattered keys) | 51–53 µs |
| `SELECT` by key, for scale | 31 µs |

Encoding a leaf [M]:

| | µs per leaf |
|---|---:|
| `encodeNode` today, with CRC | 4.0 |
| PAX encode from row strings (prototype) | 31, of which 12.8 is decoding the rows to values |
| Compress the page: lz4 / zstd-1 | + 3.5 / + 10.4 |

- **What copy-on-write implies.** A changed leaf is held loose in memory and encoded once per checkpoint, not once per write. So the extra cost is per dirty leaf per checkpoint.
- **Worst case** (every update dirties its own leaf, one checkpoint each): PAX adds about 27 µs to a 64 µs update, 42% [E]. Updates that share leaves between checkpoints pay proportionally less. An encoder that works from row bytes without making values should cost about a third [E].
- **Compression on write:** 5% (lz4) or 16% (zstd-1) in the same worst case [E].
- **Not built or measured:** a column leaf changed in place in memory, splits and merges by column, and the store learning the schema. That is the large part of the work, as 9.48 said.

## 5. The old branch (`exp/page-layout`, based on dc341662)

**What it built** (uncommitted diffs, 921 lines):
- front-coded leaf keys (a shared-length byte, a restart every 16 keys; a lazy leaf expands the keys when the page is read);
- milestone 1 of column leaves: page type `T_COLS`, each column stored plain, no encodings; a `ColSpec` per tree passed from the executor to the store; `lexdb_fixed.lxl` splitting and joining rows.

**What it measured [old]:** only synthetic data (an `orders` table of 30,000 rows); no result files, only three scripts. Its estimates per value: bigint 8 to about 3.4 bytes, decimal(12,2) 7.7 to 3.4, increasing timestamps 8 to 1.4, a status code 8 to under 1. zlib on long text: 36 µs to write, 2.6 µs to read per note. Its dump script notes two rows with ids below 1 that a full scan could not decode.

**Still valid:**
- The design in `lexdb-columns.md`: codecs chosen per column per leaf, a fallback codec, numeric as shape plus coefficient, keys kept apart, index leaves left alone.
- Its size estimates are in line with the real tables: b 4 to 2.35, c 8 to 5.2, price 7.9 to 2.7, city 7.5 to 3.65.
- The `lexdb_page.lxl` diff applies cleanly to today's code: that file has not changed since dc341662.

**No longer valid:**
- The store and executor diffs do not apply: 2 hunks fail in each. `lexdb_exec.lxl` has gained 14,322 lines since, the batch executor among them.
- Its reader turns a column page back into row strings (`decodeNodeCols`), so it would get the space but none of the scan speed. Today the gain is in decoding columns straight into batches.
- "Front coding of keys" on table leaves is worth 5.9% on w. Its better use is index leaves (40%, or 68% with the value dropped), which the design left as they are.

## 6. Recommendation

1. **Build column leaves for table trees.**
   - Codecs: bit-packed frame of reference, bitmaps, dictionary, numeric as units. Leave out the shared text prefix at first.
   - Expected on the benchmark, from the prototype in the executor [M]: `count` −42%, filters −18 to −34%, `expr_agg`, `grp_int` and hash joins −20%, `grp_text` −13%, wide scans −6 to −10%; sorts, sub-queries, index and point queries unchanged.
   - Space: w 45% smaller, t 68% [C]. Cold random reads through an index about 40% faster [E].
   - Cost: up to 27 µs per dirty leaf per checkpoint before the encoder is optimised, and the store must know the schema.
   - Next step after it: GROUP BY and filters on dictionary codes, 4 to 18 times faster on that step in the micro-benchmark [M].
2. **Front-code index leaves and drop the duplicated value.** w_b goes from 29 to 9.2 bytes an entry [C]; at today's fill, about 42 MB to about 14 MB [E]. The page-layer code exists on the old branch and applies cleanly. This is the cheapest space gain, and it is where lexdb is furthest behind PostgreSQL.
3. **Do not build page compression now.**
   - It gives no speed on this disk and costs CPU on every cold read and write.
   - Where space matters, a copy-on-write file on btrfs already gets about 3.6 times. But lexdb sets NOCOW on its data directory (9.61), so today it gets none.
   - If wanted later, compress only long text. After column leaves, `note` is half of w, and zstd with a trained dictionary takes PAX pages a further 2.3 times [M].

## Files

All under `/tmp/claude-1000/-home-chris-Work/5a17a94d-be2c-4171-b822-688c945b7212/scratchpad/`.

- **Prototype patch:** `pages-prototype.patch` (against 25a7b4e2). It adds the PAX encoder and decoders, the `fillBatch` hook and `cmd/pagebench.lxl`. It applies and builds after the reboot. The lexdb suite passes with it, hook off: 109 of 109.
- **Scripts and outputs,** in `pages/`:

| Script | What it does | Output |
|---|---|---|
| `lxpages.py`, `space.py` | read the data file; sizes and encodings | `space.out` |
| `codec.c` | zstd and lz4 per page (`gcc -O2 codec.c -lzstd -llz4`) | `codec.out` |
| `cold.py` | cold against warm, a server per run | `cold-{nocow,cow}-{direct,buffered}.out` (the run after the reboot) |
| `fio.sh` | disk throughput, read only | `fio.out` |
| `cachehit.py` | point reads under small caches | `cachehit.out` |
| `writes.py` | single-row writes | `writes.out` |
| `proto.lxl`, `hook.lxl`, `apply.py` | the prototype's source and how it is applied | |
| `pagebench DATADIR w 7 "SETS" "0,82"` | decode benchmark | `pagebench-w.out` |
| `lexdb-pax` with `LEXDB_PAXPROTO=w:bits` | end-to-end runs | `e2e-{off,off2,bits,bytes}.tsv` |
| `prof.sh` | profiles of every query | `prof-all.out` |
| | the old branch's diffs, saved | `old-branch.diff` |

- **Cleaned up:** my worktree and my disk copies (`/home/chris/Work/lexdb-bench/pages-agent`) are removed. Nothing was committed. The page-layout worktree and the main checkout were not touched.
- **Noise:** the measurements before the reboot were steady (load about 1). The disk measurements after it were slower by 20 to 40% on fio and on the index query; both sets are shown.
