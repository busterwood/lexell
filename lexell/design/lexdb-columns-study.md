<!-- The second column-page study, 2026-11-13: by a Fable subagent. Its prototype, scripts and result files are on branch study/columns (lexell/bench/columns/, results in out/), kept as the reference; a copy is in ~/Work/lexdb-bench/saved/columns/. Measured on 78731801, before 9.107 to 9.109 merged. -->

<!-- The column-leaf study, 2026-11-13: by a subagent, following design/lexdb-pages.md. Marks: [M] measured, [C] computed from the real pages or rows, [E] estimated from measured parts. Prototype and scripts: branch study/columns, lexell/bench/columns/. -->

# lexdb column leaves: plain, lightly encoded, and what they cost — measured

2026-11-13. Branch `study/columns` (from `lexdb` at 78731801), worktree `/tmp/claude-1000/-home-chris-Work/5a17a94d-be2c-4171-b822-688c945b7212/scratchpad/wt-columns`.
Data: the 1M-row table `w` (and `d`, `t`, `cr`), plus a table `e` made for the zone-map tests.
Every number is marked **[M]** measured, **[C]** computed from the real pages or rows, or **[E]** estimated from the measured parts named beside it.

This follows `design/lexdb-pages.md` and does not repeat it. That study measured bit-packed column leaves against rows. This one measures plain column arrays end to end, each encoding step apart, rows per page and page size, block skipping, FSST, and the write side in the real write path.

## Answers in short

1. **Plain column arrays, no encoding: faster to read, slower to change, no smaller.**
   - Reads [M]: `count(*)` 42% faster, filters 17 to 19%, `expr_agg` 10%, a three-column scan 8%, `select *` 6%. A primary-key point read is unchanged: its row decode goes from 0.50 to 0.66 µs in a 31 µs query.
   - Writes [M, timed inside the real write path]: a random single-row UPDATE or DELETE costs 9 to 15 µs more CPU, which is 24% of a 38 µs update when the log flush is not counted, 6% of an autocommit update on this disk. An ascending INSERT costs 0.2 µs more.
   - Whole lists [M]: `queries.txt` 4.7% less total time, `qL.txt` 4.5%; the geometric mean of the per-query ratios is 0.90.
   - Space [C]: 89.1 bytes a row against 93.3 today. So plain arrays give most of the scan gain and none of the rows-per-page gain.
2. **Each encoding step adds little scan speed at the same leaf size; what the steps buy is bytes.** Plain arrays already take the geometric mean to 0.895; all five steps together reach 0.859 [M]. Bytes per row fall from 89.1 to 55.7, so a 4 KiB leaf holds 73 rows instead of 46 [C].
   - **Bit-packed against byte-aligned:** bit-packed is 11% smaller, as fast or slightly faster to scan, the same on point reads (0.49 µs both) and the same to encode (10.2 against 10.6 µs a leaf) [M]. HyPer's reasons for avoiding it do not apply to lexdb today (section 9). Use bit-packing.
3. **Rows per page: keep 4 KiB pages and put more rows in them.**
   - More rows per leaf helps scans whether it comes from encoding or from larger pages: column leaves of 87 rows ran `count(*)` 29% and `filt1pct` 13% faster than column leaves of 43 rows [M].
   - A cold sequential scan pays by the byte, not by the page: its cold surcharge is 119 to 134 ms for `w` at every page size from 4 to 32 KiB [M]. Encoded leaves cut the bytes by 40%, so a cold `count(*)` should fall from 159 ms to about 94 ms [E].
   - A cold random read pays by the page: 59 µs a leaf at 4 KiB, 98 µs at 32 KiB [M]. Larger pages buy fewer of them but need more cache: the same 20,000 point reads fit in a 64 MB cache at 4 KiB and thrash it at 8 and 16 KiB [M].
   - Writes: a random update rewrites about 0.85 leaf pages whatever the page size, so the copy-on-write bytes per update go from 3.6 KB at 4 KiB to 27.6 KB at 32 KiB [C from M counts].
4. **Block skipping works only where the column follows the key, and there it works well.** On a column that follows the key, a 0.1% to 1% range filter ran 3.4 to 6 times faster than the row format and 2.5 to 4 times faster than column leaves without skipping [M]. On a random column it skips nothing and costs nothing measurable [M]. Keeping the summaries is free with frame of reference, 0.4 µs a leaf without it [M]. PSMAs do not fit leaves this small.
5. **FSST: not now.** It nearly halves `w` again (57 to 33 bytes a row) [M], but:
   - a symbol table per leaf is not possible: building one takes 136 µs, thirteen times the whole leaf's encode [M];
   - one table per column goes stale: built from the first 16,384 rows, it compressed `name` only 1.15 times against 2.75 [M];
   - the Lexell decoder makes text scans slower than today's rows: the LIKE scan went from 117 ms to 189 ms (143 ms today), `select *` from 696 to 770 ms (745 today) [M];
   - on natural prose the ratio is 1.66, not the 3.46 these synthetic notes give [M].
6. **Build:** column leaves on 4 KiB pages for table trees, bit-packed, with a changed leaf held as rows in memory and encoded at checkpoint, and min/max kept per leaf. Expected on the benchmark: scan-bound queries 13 to 54% faster, `select *` 6%, point and index queries unchanged, the table 40% smaller. Expected cost: about 14 µs of CPU per random single-row update before any tuning, on a 38 µs statement (section 7).

Four things I found on the way that are outside this study are listed in section 10; one of them (about 56 to 72 KB written to disk per single-row commit) looks worth a look.

## 1. Plain column arrays against the row format

"Plain" here is PAX with nothing clever: integers at their declared width, a boolean as a byte, texts and numerics as end offsets and bytes (the numeric in today's `Decimal.toBin` form), and a NULL byte per row per column.

### Reads, decode only [M]

`pagebench`: the real `Batch` filled from the real leaves of `w`, 1M rows, median of 5, ns per row. Checksums of every batch equal the row format's. Spread under 5%; the machine had other work running, so differences under about 1.5 ns are noise.

| Columns decoded | Rows today | Plain columns | Speed-up |
|---|---:|---:|---:|
| none (`count(*)`) | 15.0 | 0.3 | 50× |
| a | 19.9 | 7.4 | 2.7× |
| a, b | 24.6 | 12.8 | 1.9× |
| a, b, c | 31.1 | 20.5 | 1.5× |
| flag | 19.4 | 7.1 | 2.7× |
| city | 49.1 | 25.3 | 1.9× |
| price (numeric) | 65.4 | 43.0 | 1.5× |
| name | 46.9 | 25.4 | 1.8× |
| note | 48.0 | 26.1 | 1.8× |
| id, b, name | 57.0 | 34.6 | 1.6× |
| city, price | 98.9 | 66.5 | 1.5× |
| `*` | 183.5 | 138.1 | 1.33× |

- One row's nine columns (a point read's decode): 502 ns from a row, 658 ns from plain columns [M, median of 9, quiet machine]. A row is two cache lines; a column leaf's values for one row are spread over nine places.
- The earlier study's finding holds for plain arrays too: the row format pays 12 to 15 ns a row before it reads any column, because every row's bytes pass through the cache.

### Reads, whole queries [M]

The prototype hooked into `fillBatch`: `LEXDB_PAXPROTO=w:0`. Eight servers up at once, each with its own copy of the data; each query run in rounds, once per server per round, 7 rounds; wall ms, median (min–max). "Off 2" is a second unhooked server, to show the noise. Every query's output is identical across all servers (md5).

| Query | Off | Off 2 | Plain columns | Ratio |
|---|---:|---:|---:|---:|
| `count` | 24 (24–25) | 25 (24–25) | 14 (14–15) | 0.58 |
| `minmax_text` | 123 (122–123) | 123 (123–124) | 97 (97–98) | 0.79 |
| `filt1pct` | 77 (77–80) | 77 (76–81) | 62 (61–68) | 0.81 |
| `filt10pct` | 92 (91–97) | 92 (91–93) | 75 (75–80) | 0.82 |
| `filt_agg` | 36 (36–38) | 37 (35–38) | 30 (29–31) | 0.83 |
| `sort_lim` | 93 (93–94) | 94 (94–94) | 77 (77–78) | 0.83 |
| `distinct`, `sub_in`, `sub_exists` | 103, 42, 42 | | 85, 35, 35 | 0.83 |
| `filt_like` | 146 (143–148) | 144 (142–146) | 123 (122–124) | 0.84 |
| `join_hash_rows`, `join_text_agg` | 63, 116 | | 55, 101 | 0.87 |
| `grp_text`, `join_hash_agg` | 193, 56 | | 170, 49 | 0.88 |
| `grp_int` | 55 (55–56) | 56 (55–56) | 49 (48–49) | 0.89 |
| `expr_agg` | 67 (67–68) | 67 (67–68) | 60 (60–61) | 0.90 |
| `scan3` | 231 (225–233) | 229 (221–232) | 212 (209–215) | 0.92 |
| `distinct2`, `join_hash_sort` | 209, 95 | | 195, 89 | 0.93 |
| `scan9` (`select *`) | 787 (752–814) | 788 (764–818) | 742 (726–786) | 0.94 |
| `sub_corr_sel`, `pk_range100k` | 171, 27 | | 162, 26 | 0.95 |
| `expr_int`, `window`, `sort_all` | 201, 330, 307 | | 195, 323, 301 | 0.97–0.98 |
| `expr_mix`, `join_lookup_agg`, index ranges, `pk_point20k`, `scan2` | | | | 0.99–1.01 |

- **Lists:** `queries.txt` totals 6,888 ms off, 6,561 ms plain (0.953); `qL.txt` 4,801 against 4,587 (0.955). Geometric means of the ratios: 0.895 and 0.899. Off 2 against off: 1.003 and 1.006 [M]. The totals move little because `expr_mix` alone is 1,715 ms and does not depend on the format.
- `pk_point20k`: 627 against 628 ms. The hook does not cover key lookups; the decode difference above is 0.16 µs in a 31 µs query, 0.5% [E from M].
- **What the hook leaves out.** The column leaves are held in memory beside the row leaves, and the store still walks the row leaves; the hook takes a lock and a call per leaf. Real column leaves would do slightly better on per-leaf overhead and would also read fewer bytes from disk, which the hook cannot show.

### Writes [M]

How a column leaf would be changed is a design choice. I measured the simplest one, which is also WiredTiger's: a leaf about to change is turned back into rows (today's in-memory form), changed as today, and encoded into columns at the next checkpoint. The prototype runs exactly that extra work inside the real store, beside the real write (`LEXDB_PXWRITE=1`), and times it there: column leaf to rows when a clean leaf is first changed, rows to column leaf when a checkpoint writes it. The real page is still written in the row format, so today's 4 µs encode is also paid; see "net" below.

20,000 statements; 5 fresh copies each for the one-transaction runs, 3 for autocommit.

**In one transaction** (one log flush, so the CPU figures are clean). Server CPU µs per statement, counting the server's final checkpoint:

| | Rows today | Plain columns | Byte-aligned | Bit-packed |
|---|---:|---:|---:|---:|
| UPDATE one column, random keys: CPU with the hook's untimed setup | 38.2 | 51.8 | 58.1 | 57.7 |
| of which the column work itself (timed in place) | | 9.0 | 12.6 | 12.5 |
| — column leaf to rows, µs per leaf | | 7.7 | 8.9 | 8.8 |
| — rows to column leaf, µs per leaf | | 5.7 | 9.9 | 9.8 |
| leaves changed per statement | 0.67 | 0.67 | 0.67 | 0.67 |
| UPDATE, 20,000 consecutive keys: CPU | 28.0 | 28.6 | 28.5 | 28.8 |
| of which the column work | | 0.35 | 0.47 | 0.47 |

A second unhooked run gave 38.2 and 27.8: the base is steady to 0.2 µs.

**Autocommit, on the NVMe** (a log flush per statement; wall is 15 to 18 s per 20,000 statements, and server CPU varied from 156 to 294 µs a statement between runs, so only the in-place timers are usable):

| Column work, µs per statement | Plain | Byte-aligned | Bit-packed | Leaves changed per statement |
|---|---:|---:|---:|---:|
| UPDATE one column, random keys | 14.9 | 20.5 | 18.7 | 0.86 |
| DELETE, random keys | 15.0 | 20.6 | 19.5 | 0.86 |
| INSERT, ascending keys | 0.20 | 0.25 | 0.22 | 0.02 |
| UPDATE, consecutive keys | 0.54 | 0.65 | 0.64 | 0.02 |

- **Why autocommit costs more than the one-transaction run:** four checkpoints ran during the 20,000 statements, so leaves were turned to rows and re-encoded more often (0.86 against 0.67 per statement), and the per-leaf times are higher when the server sits idle between log flushes (11 to 12 µs to rows, against 7.7 to 8.9).
- **In proportion:** plain columns add 9.0 µs to a 38.2 µs random update, 24% [M]. Against the autocommit update's 230 to 260 µs of CPU on this disk it is about 6% [M parts, noisy base].
- **Net of what it replaces [E]:** real column leaves would not also pay today's `loosen` (0.5 µs) and `encodeNode` without its checksum (3.5 µs) [M]. Per changed leaf that is 4.0 µs back: 2.7 µs per random update in the one-transaction run. Net: plain about +6.3 µs (17%), bit-packed about +9.8 µs (26%).
- **INSERT and dense updates** share leaves, so the cost per statement is under 1 µs.
- SELECT by key with the write hooks on: 33.3 against 32.9 µs [M]: unchanged.
- Not measured: DELETE and INSERT in one transaction, which hit an unrelated slowdown (section 10).

## 2. The encodings, step by step

Each step adds to the one before. The step numbers are the prototype's flags.

| Step | What changes |
|---|---|
| 0 plain | as section 1 |
| 1 + frame of reference, whole bytes | an integer column as its least value and 0, 1, 2, 4 or 8 bytes a row |
| 3 + dictionary | a text column of few values as its values and a 1-byte code a row |
| 7 + bitmaps | a boolean as a bit; NULLs as a bitmap, left out when the leaf has none |
| 15 + numeric as units | `numeric(10,2)` as an integer of cents, then as an integer column |
| 31 + bit-packed | integers, units and dictionary codes at their exact bit width |

### Space [C]

Bytes per row of `w`. The body is measured on the prototype's leaves. The leaf total takes the key as a column and stores `id` once (today it is stored twice).

| Step | a | b | c | name | city | price | flag | note | Leaf total | Rows per 4 KiB leaf |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| Rows today | 4 | 4 | 8 | 13.0 | 7.5 | 7.9 | 1 | 27.0 | 93.3 | 43.7 |
| 0 plain | 5.0 | 5.0 | 9.0 | 14.0 | 8.5 | 8.9 | 2.0 | 28.0 | 89.1 | 45.8 |
| 1 + FOR bytes | 2.2 | 5.2 | 9.2 | 14.0 | 8.5 | 8.9 | 2.0 | 28.0 | 79.8 | 51.1 |
| 3 + dictionary | 2.2 | 5.2 | 9.2 | 14.0 | 5.5 | 8.9 | 2.0 | 28.0 | 76.8 | 53.1 |
| 7 + bitmaps | 1.2 | 4.2 | 8.2 | 13.0 | 4.5 | 7.9 | 0.13 | 27.1 | 68.1 | 59.9 |
| 15 + numeric units | 1.1 | 4.1 | 8.1 | 13.0 | 3.3 | 4.2 | 0.12 | 27.1 | 62.8 | 65.0 |
| 31 + bit-packed | 1.0 | 2.3 | 5.1 | 13.0 | 3.0 | 2.7 | 0.12 | 27.1 | 55.7 | 73.3 |

- Steps 0 to 7 are measured at 43 rows a leaf; steps 15 and 31 at 64 rows a leaf, near the fill they reach, because the dictionary and the per-leaf headers depend on it.
- The plain rows above include a NULL byte per value; the bitmap step removes it, which is why every column drops by 1 there.
- `c` is a random bigint below 10^12: 40 bits, so whole bytes cannot shrink it and bit-packing takes 3 bytes off. `b` is 17 bits: 4 bytes whole, 2.3 packed.
- The dictionary gains with fuller leaves, because a leaf of 43 rows already holds about 17 of the 20 cities: bit-packed it is 4.1 bytes a row at 43 rows a leaf, 3.0 at 64, 1.2 at 256 [C].
- After every step `name` and `note` are 40.1 of the 55.7 bytes. Only section 6 touches them.

### Decode alone [M]

ns per row, same leaves as the rows (43 a leaf), median of 5.

| Columns | Rows | 0 plain | 1 FOR | 3 dict | 7 bitmap | 15 numeric | 31 bits |
|---|---:|---:|---:|---:|---:|---:|---:|
| a | 19.9 | 7.4 | 7.6 | 6.2 | 4.5 | 4.0 | 4.1 |
| a, b | 24.6 | 12.8 | 13.5 | 11.5 | 9.3 | 7.9 | 8.6 |
| a, b, c | 31.1 | 20.5 | 21.4 | 19.8 | 16.3 | 15.6 | 13.4 |
| flag | 19.4 | 7.1 | 7.1 | 7.2 | 5.2 | 5.9 | 5.0 |
| city | 49.1 | 25.3 | 26.3 | 31.2 | 27.5 | 28.5 | 28.5 |
| price | 65.4 | 43.0 | 43.6 | 42.8 | 39.5 | 37.6 | 37.8 |
| name | 46.9 | 25.4 | 25.5 | 24.3 | 21.7 | 22.3 | 21.8 |
| id, b, name | 57.0 | 34.6 | 35.9 | 35.8 | 29.1 | 29.2 | 27.3 |
| city, price | 98.9 | 66.5 | 67.1 | 72.5 | 65.4 | 65.0 | 64.1 |
| `*` | 183.5 | 138.1 | 138.9 | 144.9 | 129.6 | 131.2 | 126.0 |

### Whole queries [M]

Same run as section 1 (8 servers, 7 rounds, wall ms median). Ratios are to "off".

| Query | Off | 0 plain | 1 FOR | 3 dict | 7 bitmap | 15 numeric | 31 bits |
|---|---:|---:|---:|---:|---:|---:|---:|
| `count` | 24 | 14 | 14 | 15 | 15 | 16 | 14 |
| `filt1pct` | 77 | 62 | 61 | 61 | 52 | 52 | 51 |
| `filt10pct` | 92 | 75 | 76 | 74 | 66 | 67 | 66 |
| `filt_agg` | 36 | 30 | 31 | 31 | 28 | 29 | 26 |
| `expr_agg` | 67 | 60 | 60 | 60 | 55 | 56 | 54 |
| `grp_int` | 55 | 49 | 48 | 48 | 45 | 45 | 45 |
| `sort_lim` | 93 | 77 | 78 | 78 | 69 | 70 | 67 |
| `filt_like` | 146 | 123 | 124 | 122 | 119 | 122 | 118 |
| `grp_text` | 193 | 170 | 171 | 180 | 171 | 172 | 170 |
| `minmax_text` | 123 | 97 | 98 | 108 | 100 | 103 | 102 |
| `distinct` | 103 | 85 | 85 | 95 | 90 | 91 | 90 |
| `join_hash_agg` | 56 | 49 | 49 | 48 | 46 | 48 | 46 |
| `join_text_agg` | 116 | 101 | 100 | 110 | 102 | 104 | 102 |
| `scan3` | 231 | 212 | 211 | 213 | 202 | 205 | 204 |
| `scan9` | 787 | 742 | 738 | 747 | 754 | 758 | 753 |
| **Geometric mean, `queries.txt`** | 1 | 0.895 | 0.894 | 0.907 | 0.867 | 0.878 | 0.859 |
| **Geometric mean, `qL.txt`** | 1 | 0.899 | 0.896 | 0.914 | 0.872 | 0.880 | 0.865 |
| **Total, `queries.txt`, ms** | 6,888 | 6,561 | 6,551 | 6,623 | 6,503 | 6,524 | 6,479 |

The full table of all 32 queries with ranges is in `bench/columns/out/e2e-steps.md`.

**What each step is worth, at the same leaf size:**

- **Plain:** the largest step by far: 0.895.
- **Frame of reference, whole bytes:** nothing for speed (0.894). It saves 9.3 bytes a row.
- **Dictionary, decoded to values:** slightly slower where the column is used (`grp_text` 171 to 180, `distinct` 85 to 95, `minmax_text` 98 to 108): each leaf builds its entries as values first. It saves 3 bytes a row at this leaf size. The dictionary pays only when the executor works on codes, which the earlier study measured at 4 to 18 times faster for that step; that is not built.
- **Bitmaps:** the second largest step for speed (`filt1pct` 61 to 52, `expr_agg` 60 to 55). Almost all of it is the NULL column disappearing when a leaf has no NULLs, not the packing of bits. A plain layout that left out the NULL bytes when it could would get this too.
- **Numeric as units:** `price` decodes 5% faster (39.5 to 37.6 ns); making the `Decimal` value still dominates. It saves 3.7 bytes a row.
- **Bit-packing:** a little faster where integers dominate (`filt_agg` 29 to 26, three integer columns 15.6 to 13.4 ns), otherwise the same. It saves 7.1 bytes a row.

### Byte-aligned against bit-packed [M]

| | Byte-aligned (15) | Bit-packed (31) |
|---|---:|---:|
| Leaf bytes per row [C] | 62.8 | 55.7 |
| Rows per 4 KiB leaf [C] | 65.0 | 73.3 |
| Scan decode, a / a,b,c / `*`, ns per row | 4.0 / 15.6 / 131.2 | 4.1 / 13.4 / 126.0 |
| The same at 256 rows a leaf | 2.5 / 10.8 / 114.0 | 2.2 / 9.0 / 113.4 |
| `filt1pct`, `filt_agg`, `expr_agg`, `scan9`, ms | 52, 29, 56, 758 | 51, 26, 54, 753 |
| Geometric mean, `queries.txt` | 0.878 | 0.859 |
| Point read, one row's 9 columns, ns | 492 (478–512) | 494 (487–591) |
| Encode a 43-row leaf, µs | 10.6 | 10.2 |
| Encode, timed in the write path, µs | 9.9 | 9.8 |
| Leaf back to rows, µs | 8.6 | 8.6 |

Bit-packing loses nowhere and holds 13% more rows per leaf. A bit-packed value is still read at a computed position, so a point read does not decode the leaf.

## 3. Rows per page, and page size

Two ways to get more rows on a leaf: encode them (same 4 KiB), or make the page larger. I measured both. For the second I built lexdb with 8, 16 and 32 KiB pages (three constants) and loaded the same tables into each.

| | 4 KiB | 8 KiB | 16 KiB | 32 KiB |
|---|---:|---:|---:|---:|
| Leaves of `w` [M] | 23,228 | 11,480 | 5,714 | 2,855 |
| Rows per leaf | 43 | 87 | 175 | 350 |

### Scans in memory [M]

Same method as section 1 (8 servers, 7 rounds). "Columns" is the bit-packed hook on that build, so its leaves have the rows of that page size; a real 4 KiB column leaf holds 73.

| Query, wall ms | Rows 4K | Rows 8K | Rows 16K | Rows 32K | Columns, 43 a leaf | Columns, 87 | Columns, 175 | Columns, 350 |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `count` | 25 | 18 | 15 | 15 | 14 | 10 | 9 | 8 |
| `filt1pct` | 82 | 73 | 72 | 69 | 53 | 46 | 44 | 43 |
| `filt_agg` | 42 | 32 | 31 | 28 | 29 | 24 | 20 | 18 |
| `expr_agg` | 71 | 65 | 61 | 60 | 58 | 50 | 48 | 48 |
| `grp_int` | 56 | 50 | 47 | 47 | 45 | 39 | 37 | 35 |
| `sort_lim` | 95 | 87 | 83 | 84 | 68 | 62 | 60 | 59 |
| `minmax_text` | 124 | 116 | 112 | 110 | 100 | 91 | 86 | 83 |
| `grp_text` | 196 | 189 | 185 | 181 | 171 | 162 | 158 | 154 |
| `filt_like` | 150 | 143 | 141 | 137 | 123 | 117 | 113 | 111 |
| `scan9` | 759 | 754 | 751 | 743 | 718 | 701 | 692 | 682 |
| Geometric mean, 24 scan and aggregate queries | 1 | 0.935 | 0.908 | 0.900 | 0.858 | 0.794 | 0.774 | 0.758 |

- Doubling the rows per leaf is worth 6 to 8% on the mean for either format; the next doubling 2 to 3%; then it flattens. The per-leaf cost (finding the leaf, the call, the block headers, the per-leaf dictionary) is spread over more rows.
- This machine was running other agents' work during this run; the interleaving spreads that over all eight servers. The join and sub-query rows are left out of the mean because these freshly loaded directories had no statistics and planned them differently (section 10).
- **A 4 KiB column leaf of 73 rows** lies between the "43" and "87" columns, about 81% of the way by leaves saved [E]: `count` about 11 ms, `filt1pct` 46, `expr_agg` 48.

Decode alone at more rows per leaf [M, ns per row]:

| Columns | Bit-packed, 43 | 64 | 128 | 256 | 1,024 |
|---|---:|---:|---:|---:|---:|
| a | 4.1 | 3.6 | 3.0 | 2.2 | 2.3 |
| a, b, c | 13.4 | 12.6 | 11.0 | 9.0 | 9.3 |
| city | 28.5 | 25.0 | 22.5 | 21.0 | 21.4 |
| `*` | 126.0 | 119.9 | 116.0 | 113.4 | 121.3 |

### Cold sequential scans: bytes against CPU [M]

O_DIRECT, the file evicted, a fresh server per run, 5 runs; on defragmented copies (section 10 explains why). Wall ms, median.

| `count(*)` from w | 4 KiB | 8 KiB | 16 KiB | 32 KiB |
|---|---:|---:|---:|---:|
| Warm | 25 | 19 | 17 | 15 |
| Cold | 159 (159–160) | 148 (145–149) | 136 (134–137) | 143 (133–149) |
| Cold less warm | 134 | 129 | 119 | 128 |
| Server CPU, cold | 104 | 127 | 123 | 130 |

- The cold surcharge is the same at every page size: about 1.3 to 1.4 ms per MB, whether the 93 MB come as 23,228 pages or 2,855. So on this drive a cold scan pays by the byte (read, checksum, copy), and fewer, larger pages save nothing.
- At 4 KiB it splits into about 83 ms of CPU and 55 ms of waiting, as the earlier study found. The standard data directory (15 extents) gave 175 ms cold (173–177), 150 ms over warm.
- **Encoded leaves cut the bytes:** `w` goes from 93.7 MB to 55.9 MB [C]. Cold surcharge 134 × 0.60 = 80 ms, plus the warm 14 ms: about 94 ms against 159, 41% faster [E]. Plain column leaves: 89.5 MB, about 142 ms [E].
- The disk itself, fio, O_DIRECT [M]: sequential 256 KiB reads 1,580 to 1,595 MB/s; sequential 4 KiB 171 MB/s (22.7 µs each).

### Random point reads [M]

| | 4 KiB | 8 KiB | 16 KiB | 32 KiB | 64 KiB |
|---|---:|---:|---:|---:|---:|
| fio, random read, one at a time, µs | 90–99 | 95–96 | 105–108 | 120 | 137–160 |
| `idx_range_agg` cold (100,000 rows through the index), ms | 1,525 | 928 | 584 | 436 | |
| — per leaf read, µs | 59 | 67 | 75 | 98 | |
| 20,000 random key reads, first pass from a cold cache, ms | 2,469 | 1,988 | 1,554 | | |

- **One read is latency-bound:** 8 times the bytes (4 to 32 KiB) cost 30% more time. So fewer bytes barely matter, and a compressed 4 KiB page would save nothing here.
- **Fewer leaves do matter, when the reads are dense enough to land on the same leaf.** Both tests above read 2 to 10% of a 1M-row table, so larger leaves mean fewer distinct leaves to fetch. On a table much larger than the reads, every read is its own miss and only the top row of the table applies: larger pages are then 2 to 30% slower per read.
- **Column leaves get the "fewer leaves" without the larger read:** 13,650 leaves of 4 KiB at 59 µs each. `idx_range_agg` cold: about 965 ms against 1,525, 37% faster [E].

### Cache capacity and hit rate [M]

20,000 random key reads, repeated; ms for the fourth pass. A pass with all hits takes about 660 ms.

| Cache | 4 KiB | 8 KiB | 16 KiB |
|---|---:|---:|---:|
| 96 MB | 662 | 674 | 666 |
| 64 MB | 663 | 1,779 | 1,776 |
| 48 MB | 2,227 | 2,124 | 2,315 |
| 32 MB | 2,556 | 2,554 | 2,623 |
| 16 MB | 2,902 | 2,927 | 3,104 |

- The 13,300 leaves these reads touch take 60 MB at 4 KiB. At 8 KiB the 9,500 leaves touched take 81 MB, and a 64 MB cache thrashes. Larger pages hold more rows nobody asked for.
- **Column leaves go the other way:** the same reads touch about 10,500 leaves of 73 rows, 47.5 MB instead of 60.3 MB, 21% less cache [C]. For a scan-heavy working set a cache holds 1.67 times the rows.
- As the earlier study saw, a cache slightly too small misses on most reads, not on a few.

### The write side [M, C]

| Random single-row UPDATE, autocommit | 4 KiB | 8 KiB | 16 KiB | 32 KiB |
|---|---:|---:|---:|---:|
| Leaf pages written per update [M] | 0.88 | 0.855 | 0.846 | 0.841 |
| Page bytes written per update [C] | 3.6 KB | 7.0 KB | 13.9 KB | 27.6 KB |
| Checkpoints during 20,000 updates [M] | 4 | 6 | 11 | 21 |
| Leaf pages written per ascending INSERT [M] | 0.138 | 0.071 | 0.038 | 0.024 |

- Random updates each dirty their own leaf at every size here, so the copy-on-write bytes grow with the page: 7.7 times from 4 to 32 KiB. Haas and Leis count the same effect as "I/O amplification" (section 9).
- A fuller column leaf costs more to re-encode, in proportion to its rows [M, bit-packed]:

| Rows per leaf | 43 | 72 | 128 | 256 | 1,024 |
|---|---:|---:|---:|---:|---:|
| Rows to column leaf, µs | 10.2 | 17.1 | 24.5 | 50.9 | 185 |
| Column leaf to rows, µs | 8.6 | 14.7 | 22.7 | 48.6 | 222 |
| Both, per changed leaf | 18.8 | 31.8 | 47.2 | 99.5 | 407 |

  So a real 4 KiB column leaf of about 73 rows costs about 32 µs per changed leaf per checkpoint, against about 4.5 µs today. A 64 KiB leaf of 1,024 rows would cost 0.4 ms for one changed row.
- **Splits.** A leaf's encoded size is not known until it is encoded, and it does not add up row by row (the frame of reference and the dictionary depend on all the rows). Today a leaf splits when its row bytes pass 4,078. The clean answer is WiredTiger's: let the in-memory leaf grow, and at checkpoint encode it and write one page or two. A cheap upper bound per row (its row-format size) can trigger an early split so a leaf never encodes to more than two pages. lexdb has no merges today (an empty leaf leaves its parent), so there is nothing to add there.
- Not built or measured: the split at checkpoint, and a leaf changed in place in column form.

### Keep 4 KiB or go larger?

Keep 4 KiB.
- Encoding gets 73 rows on a 4 KiB leaf; that is most of what an 8 KiB page gets (87), with none of its costs.
- Larger pages cost what the tables above show: more cache for point reads, 2 to 8 times the bytes per random update, slower single reads, and no gain on cold scans.
- The scan gain from still more rows per leaf flattens after about 175.
- A hot/cold split would change this: cold data that is never updated can sit in large blocks (HyPer and BtrBlocks use 64,000 rows), where the write costs do not apply and where per-block dictionaries, min/max tables and FSST tables become cheap. That is the place for large blocks, not the B+tree's leaves.

## 4. Block skipping

**What was tested.** The prototype keeps the least and greatest value of each integer column per column leaf. `LEXDB_PXSKIP=column:lo:hi` makes a scan skip leaves whose range misses the filter's. Table `e` is `w` with two columns that follow the key: `ts` (key × 10 plus a random 0 to 5,000: arrival order with noise) and `day` (365 values in runs of 2,740 keys). The planner does not push filters into scans, so the range is given by hand and the query filters on the same range; results are identical with and without skipping.

### How much can be skipped [C]

Share of blocks a scan must still read, by rows per block:

| Filter | Rows matching | 43 | 72 | 256 | 1,024 | 8,192 | 65,536 |
|---|---:|---:|---:|---:|---:|---:|---:|
| `ts` in a 0.1% range | 0.10% | 0.15% | 0.15% | 0.15% | 0.31% | 1.6% | 6.3% |
| `ts` in a 1% range | 1.0% | 1.05% | 1.05% | 1.07% | 1.2% | 2.4% | 6.3% |
| `ts` in a 10% range | 10% | 10.05% | 10.05% | 10.06% | 10.1% | 11.4% | 18.8% |
| `day = 180` | 0.27% | 0.28% | 0.28% | 0.31% | 0.41% | 0.81% | 6.3% |
| `a = 5` (a cycles 0 to 99 with the key) | 1.0% | 49% | 79% | 100% | 100% | 100% | 100% |
| `b between 500 and 600` (random; the range is at the low edge) | 0.11% | 23% | 35% | 78% | 99.5% | 100% | 100% |
| `b between 50000 and 50100` (random, mid-range) | 0.10% | 100% | 100% | 100% | 100% | 100% | 100% |
| `c > 900000000000` (random, 10%) | 10% | 99% | 99.9% | 100% | 100% | 100% | 100% |

Small leaves are an advantage here: 43-row summaries skip almost exactly the rows that do not match. A random column is skipped only by accident (a range at the edge of its domain, small leaves).

### What it saves [M]

5 servers, 7 rounds, wall ms median (min–max). "Rows" is the unhooked server.

| Query on `e` | Rows | Columns | Columns + skip, 43 a leaf | + skip, 72 | + skip, 1,024 |
|---|---:|---:|---:|---:|---:|
| count, sum where `ts` in 0.1% | 47 (46–49) | 35 (34–37) | 13 (13–15) | 17 (17–18) | 13 (13–15) |
| three columns where `ts` in 0.1% | 86 (85–88) | 58 (57–60) | 14 (13–15) | 17 (17–19) | 14 (13–15) |
| count, sum where `ts` in 1% | 47 | 34 | 14 | 17 | 13 |
| count, sum where `ts` in 10% | 50 | 36 | 17 | 20 | 17 |
| three columns where `ts` in 10% | 104 (98–111) | 76 (73–108) | 36 (34–46) | 40 (37–41) | 34 (33–38) |
| count, sum where `day = 180` | 43 | 31 | 13 | 17 | 13 |
| count, sum where `a = 5` | 43 | 30 | 22 | 30 | 27 |
| count, sum where `b` 500–600 | 43 | 31 | 18 | 24 | 28 |
| count, sum where `b` 50000–50100 | 46 (42–47) | 31 (31–32) | 31 (31–33) | 36 (34–37) | 29 (28–30) |
| count, sum where `c` > 9×10^11 | 47 | 32 | 33 | 38 | 30 |

- **Where the column follows the key:** 2.5 to 4 times faster than column leaves without skipping, 3.4 to 6 times faster than rows.
- **The floor is 13 ms,** the time to walk every leaf, which is `count(*)`'s time. The summary is in the leaf, so the leaf is still visited. With the summaries in the parent node the walk would visit 100 parents instead of 23,000 leaves: about 1 ms [E]. Cold, the skipped leaves would not be read from disk at all, which the hook cannot show: a 1% range would read 1% of the 134 ms cold surcharge [E].
- **Where it cannot skip, it costs nothing measurable:** 31 against 31 ms and 33 against 32 ms. The "72" and "1,024" columns are a little slower or faster for the hook's own reasons (it is called once per row leaf of 43 and splits the work at column-leaf edges), not because of skipping.

### What it costs to keep

- With frame of reference the least value is already the block's base, and the greatest is found while choosing the width: no extra time. Without it (plain columns), finding both for four integer columns added 0.38 µs to a 6.2 µs leaf encode [M].
- Space: the base is there already; an exact greatest value is up to 8 bytes per integer column per leaf, 0.1 to 0.2 bytes a row.
- In the parent: about 16 bytes per summarised column per child. Four columns take an internal entry from 18 to 82 bytes, the fan-out from about 225 to 50, and `w`'s internal pages from about 100 to about 470: 2% of the table instead of 0.4% [C]. A change to a leaf's summary changes the parent, which copy-on-write rewrites up to the root anyway.
- **PSMAs** (HyPer's lookup tables that narrow the range inside a block) are 2 KB and up per column for 65,536-row blocks. A leaf of 73 rows is decoded whole in under 1 µs; a PSMA has nothing to narrow.

### What it needs

The executor must hand the scan a range for a column (today filters run on the batch after decoding). That is planner and executor work, not storage work.

## 5. Costs of choosing an encoding per leaf

BtrBlocks samples 1% of a 64,000-value block to choose an encoding. A lexdb leaf is smaller than one of its samples, so the prototype computes each candidate's exact size from all the rows:
- integers: least and greatest, one pass;
- text: a dictionary is tried, and given up once 24 or more distinct values are three quarters of the rows seen;
- numeric: units if every value has the same scale.

Encoding a 43-row leaf of `w`, 9 columns [M]: 6.2 µs plain, 9.7 µs with the dictionary attempt, 10.2 µs with everything. Today's `encodeNode` is 4.2 µs with its checksum. The earlier study's prototype took 31 µs because it made a value per field; this one reads the row bytes directly, as that study predicted.

## 6. FSST for long text

### What it is

FSST ("Fast Static Symbol Table", Boncz, Neumann and Leis, VLDB 2020) is a compression scheme made for database text columns.

- It looks at a sample of the column's text and picks up to 255 short byte strings, each 1 to 8 bytes long, that occur often: for English prose things like `"the "`, `"ing"`, `" of "`; for `w.note`, `"note "` and `" about item "`. This list is the symbol table.
- To compress a value it replaces each such string with a single byte, its number in the table. A byte that is in no symbol is written as itself after an escape byte (255), so the worst case doubles a value.
- To decompress it looks each byte up in the table and copies the symbol out. Nothing else is needed: no window of earlier text, as LZ4 and zstd need.
- That last point is why it suits a database: **each value can be decompressed on its own**, given only the table. A point read decodes one value, not a page.
- "Static" means the table is built once, then only read. The table is at most about 2.3 KB.
- The paper reports a compression factor of 2.28 against LZ4's 1.70 on its text corpus, compressing at about 1 GB/s and decompressing at about 2 GB/s (Table 1).

### Ratio and speed on lexdb's columns [M]

The reference C++ library (github.com/cwida/fsst, MIT, built in the scratch folder with `-O3 -march=native`), one thread, best of 3. "Values per table" is how much text shares one symbol table.

**`w.note`** (1M values, 25.2 bytes each):

| Values per table | Bytes per value | Table bytes per value | Ratio, with tables | Build a table, µs | Compress, ns per value | Decompress, ns per value |
|---|---:|---:|---:|---:|---:|---:|
| 43 (a leaf today) | 9.11 | 1.87 | 2.30 | 136 | 32 | 8.8 |
| 82 | 8.21 | 1.69 | 2.55 | 164 | 44 | 8.0 |
| 256 | 6.85 | 1.09 | 3.17 | 289 | 37 | 6.5 |
| 1,024 | 6.66 | 0.47 | 3.53 | 525 | 35 | 4.9 |
| 65,536 | 7.29 | 0.01 | 3.45 | 603 | 36 | 4.9 |
| all | 7.29 | 0 | 3.46 | 808 | 36 | 4.7 |

**`w.name`** (11 bytes each, `name0000001` on):

| Values per table | Bytes per value | Ratio, with tables | Build a table, µs |
|---|---:|---:|---:|
| 43 | 3.06 + 1.07 | 2.67 | 92 |
| 1,024 | 3.16 + 0.28 | 3.20 | 355 |
| all | 3.99 | 2.75 | 964 |
| a table from the first 16,384 values, used for all | 9.54 | **1.15** | |

**Natural prose** (23,682 lines of this repository's design documents, 70 bytes each): ratio 1.66 with one table, 1.39 with a table per 43 values.

- **A table per leaf is out.** Building it costs 136 µs, against 10 µs to encode the whole leaf, and the table itself is 80 bytes of a 400-byte column.
- **So the table must be shared**: per table and column, kept in the catalog. Then the ratio is 3.46 on `note` and compressing costs 36 ns a value in C++.
- **A shared table goes stale.** `name` counts upward; a table trained on the first 16,384 rows knows `name00000` and digit pairs it saw, and compresses the rest 1.15 times instead of 2.75. Any column whose text drifts needs the table rebuilt and the old leaves either re-encoded or tagged with the table they used.
- **These two columns flatter FSST.** Both are a fixed phrase plus digits. On prose it is 1.66.

### In lexdb: LIKE scans and `select *` [M]

I ported the decoder and a simple encoder to Lexell, inside the prototype (`LEXDB_PAXPROTO=w:95`, symbol tables from the C++ library, one per column). Results are identical on every query. 4 servers, 7 rounds, wall ms median (min–max).

| Query | Rows today | Columns, bit-packed | The same + FSST on name and note |
|---|---:|---:|---:|
| `filt_like` (`note like '%item 77%'`) | 143 (142–143) | 117 (116–118) | 189 (188–189) |
| `like_name` (`name like '%99999%'`) | 83 (82–83) | 63 (63–64) | 93 (92–94) |
| `note_eq` (`note = '...'`) | 74 (73–74) | 60 (59–61) | 105 (104–105) |
| `scan9` (`select *`) | 745 (738–747) | 696 (694–699) | 770 (761–774) |
| `scan3` (id, b, name) | 217 (214–218) | 189 (187–204) | 220 (216–227) |
| `minmax_text` | 124 | 100 | 130 |
| `filt1pct` (returns name) | 78 | 50 | 78 |
| `count` | 25 | 14 | 16 |

| | Bit-packed | + FSST |
|---|---:|---:|
| Leaf body bytes per row [M] | 57.5 | 32.6 |
| Rows per 4 KiB leaf [C] | 73 | 125 to 140 |
| Decode `note`, ns per row [M] | 26 | 68 |
| Decode `name`, ns per row [M] | 21 | 45 |
| Point read, one row, ns [M] | 452 | 576 |

- **Text scans get slower than today's row format.** The Lexell decoder runs at about 1.7 ns per byte of text, 600 MB/s, against 3 to 5 GB/s for the C++ one. Lexell has no unaligned 8-byte store, so each symbol is copied a byte at a time with a bounds check; my first version (8 stores per symbol through `binary.setU64LE`) was slower still, 87 ns per note. And each batch's text is decompressed into a new string, where plain text is a slice of the leaf.
- With a decoder at the C++ speed the extra would be about 5 ns a value instead of 42, and the LIKE scan about 125 ms instead of 189 [E]. That needs a compiler intrinsic or a runtime helper, not a port.
- **Why `filt1pct` loses all its gain:** it returns `name`, and the executor decodes every column a query uses for every row before filtering. FSST makes that mistake expensive. Decoding text only for the rows that pass the filter would fix it for any format.
- **Equality** on a compressed column can be done without decompressing, by compressing the constant once (the paper, §3.4). LIKE cannot in general. Neither is built.
- **Encode cost:** my simple Lexell matcher took the leaf encode from 10.5 to 31 µs [M]. At the C++ library's 36 ns a value it would add about 1.5 µs a leaf [E].

### Verdict

Do not build FSST now. The space gain is real (another 43% off `w`), but it needs a fast decoder that Lexell cannot express today, a symbol table per column in the catalog with a plan for going stale, and it slows every query that touches the text. If space becomes the goal, the order should be: decode text only for rows that pass the filter; a runtime helper for the decode loop; then FSST with a table per column, retrained when the ratio drops. A hot/cold split makes it easier: a table per frozen block of 65,536 values costs 603 µs to build, 9 ns a value, and never goes stale.

## 7. What to build

1. **Column leaves for table trees, on 4 KiB pages.**
   - **On disk and in the cache when clean:** one block per column: integers bit-packed against the leaf's least value; booleans as bits; a NULL bitmap only when the leaf has NULLs; `numeric` of one scale as bit-packed units; a text column as a dictionary with bit-packed codes when that is smaller, else end offsets and bytes. The key as a column; the primary-key column stored once.
   - **When changed:** turned back into today's rows-in-memory form, changed as today, encoded at checkpoint. This is WiredTiger's split between in-memory and on-disk formats, and lexdb's store already works this way for rows. The split of a leaf that encodes too large happens at checkpoint.
   - **The store stays ignorant of types.** The executor gives the store an encoder and a decoder per tree; the prototype does exactly this for its write measurements (`setColProto`), which answers question 1 of `lexdb-columns.md`.
   - **Leave out at first:** FSST, the shared text prefix, run-length encoding (no column here has runs), and working on dictionary codes.
2. **Min and max per integer and numeric column per leaf,** from the encoder's own pass. Use them once the executor can pass a range to a scan. Moving them into the parent is a second step, worth it for cold range scans.
3. **Keep 4 KiB pages.**
4. **Not now:** FSST; byte-aligned variants; larger leaves; PSMAs.

### Expected gain on the benchmark

Wall ms. "Same leaves" is measured with the hook at 43 rows a leaf [M]. "Refilled" is my estimate for real 4 KiB leaves of 73 rows: the measured value, moved 81% of the way from the measured 43-row to the measured 87-row column leaves of section 3 [E].

| Query | Today | Column leaves, same leaves [M] | Refilled to 73 rows [E] | Change |
|---|---:|---:|---:|---:|
| `count` | 24 | 14 | 11 | −54% |
| `filt1pct` | 77 | 51 | 46 | −40% |
| `filt_agg` | 36 | 26 | 22 | −39% |
| `filt10pct` | 92 | 66 | 61 | −34% |
| `sort_lim` | 93 | 67 | 62 | −33% |
| `expr_agg` | 67 | 54 | 48 | −28% |
| `grp_int` | 55 | 45 | 40 | −27% |
| `minmax_text` | 123 | 102 | 95 | −23% |
| `filt_like` | 146 | 118 | 113 | −23% |
| `join_hash_agg`, `join_hash_rows`, `sub_in`, `sub_exists` | 56, 63, 42, 42 | 46, 50, 32, 32 | | −18 to −24% [M] |
| `grp_text` | 193 | 170 | 163 | −16% |
| `join_text_agg`, `join_hash_sort`, `distinct` | 116, 95, 103 | 102, 82, 90 | | −12 to −14% [M] |
| `scan3` | 231 | 204 | 201 | −13% |
| `scan9` (`select *`) | 787 | 753 | 741 | −6% |
| `expr_int`, `window`, `sub_corr_sel`, `pk_range100k` | | | | −5 to −8% [M] |
| `expr_mix`, `sort_all`, `join_lookup_agg`, index ranges, `pk_point20k`, `scan2` | | | | within ±3% [M] |

- Lists, same leaves [M]: `queries.txt` total 6,888 to 6,479 ms (−5.9%), geometric mean 0.859; `qL.txt` 4,801 to 4,545 ms (−5.3%), geometric mean 0.865.
- Cold: sequential scans about 40% faster, random reads through an index about 37% faster [E, section 3].
- Space: `w` 93.7 MB to 55.9 MB, 40% smaller [C]. A cache holds 1.67 times the rows.
- With ranges pushed into scans: filters on columns that follow the key 2.5 to 4 times faster again [M, section 4].

### Expected cost to writes

- **A random single-row UPDATE or DELETE:** 12.5 µs more CPU per statement with 43-row leaves, on a 38 µs statement [M, in the write path]. Real leaves of 73 rows cost 1.7 times as much each (32 µs) [M], but the same updates change fewer of them (0.52 a statement instead of 0.67) [C]: about 17 µs, less the 2.7 µs of today's encode it replaces, so about +14 µs per random update [E]. That is about 37% more CPU when the log flush is not counted, and about 8% of an autocommit update on this disk.
- **INSERTs in key order and updates that share leaves:** under 1 µs per statement [M].
- **Checkpoints:** about 32 µs per changed leaf instead of 4.5 [M parts].
- **Point reads:** unchanged [M].
- This is the untuned prototype. The leaf-to-rows step is half of it and exists only because a changed leaf is held as rows; a hot/cold split would remove the cost for hot data altogether, since hot rows would stay rows.

## 8. Method

- **Prototype** (`lexell/bench/columns/proto.lxl`, appended to `cmd/lexdb_exec.lxl` by `apply.py`; nothing runs unless a switch is set):
  - `pxEncode`: a column leaf from row bytes, the encodings chosen by a set of flags. `pxRunInto`: fills the executor's `Batch`. `pxRow`: one row. `pxToRows`: a column leaf back to rows; the rows are byte-identical to the stored ones for all 1M rows at every flag setting [M].
  - `LEXDB_PAXPROTO=table:flags[:rows per leaf]`: scans of that table decode from column leaves built in memory on first use. Read-only tables with a dense integer key only.
  - `LEXDB_PXSKIP=column:lo:hi`: leaf skipping.
  - `LEXDB_PXFSST_<column>=hex,...`: an FSST symbol table for a column (from `fsst_tool FILE dump`).
  - `LEXDB_PXWRITE=1`: in `cmd/lexdb_store.lxl`, a changed table leaf's column work is run and timed beside the real write, and counts are printed at each checkpoint. `=count`: the counts only.
- **Checks:** every hooked configuration returned the same output as the unhooked server on every query (md5 of the output). The lexdb test suite passes with the switches off: 111 of 111.
- **Whole-query timing** (`e2e.py`): up to 8 servers at once on ports 55541 to 55548, each on its own copy of the data; per query one warm-up each, then 7 rounds, each round running the query once on every server, alternating the order. Other agents were compiling and testing on this machine, and a first run that measured one configuration after another showed shifts of 10 to 20% between neighbours on queries the format cannot affect; the interleaved runs do not (off against off 2: within 4% on every query, 0.3% on the total).
- **Writes** (`writes2.py`): a fresh copy of the data directory per run. CPU from `/proc/PID/task/*/schedstat` during the statements and from `wait4` for the server's whole life less a run with no statements, so the final checkpoint is counted.
- **Page sizes** (`build_ps.sh`): the three `PAGE` constants changed in a copy of `cmd/`, tables loaded by `COPY` (`load.sh`).
- **Cold reads** (`cold.py` from the earlier study): O_DIRECT, `posix_fadvise(DONTNEED)`, a fresh server per run.
- **Disk:** every data directory was in the scratch folder on the NVMe (btrfs, copy-on-write off).
- **perf** was not needed; `perf_event_paranoid` is 2, which allows user-space profiles.
- **Noise:** the decode micro-benchmarks of sections 1 to 3 ran while other agents were busy (load 2 to 5); their min–max spread is under 5%, but treat differences under 1.5 ns as noise. The point-read and encode figures were rerun on a quiet machine. The fio runs at queue depth 8 were erratic (11,500 to 59,700 operations a second at 16 KiB) and are not used.

## 9. What the literature says, and how lexdb differs

Facts below were checked against the papers and official docs; two DuckDB points could not be confirmed at the source and are marked.

- **PAX** (Ailamaki, DeWitt, Hill, Skounakis, VLDB 2001).
  - Layout: fixed-length values in minipages with a presence bit per record, variable-length values with end offsets (§3). My "plain" step is this, except that NULLs are a byte per row until the bitmap step.
  - Results: 50 to 75% fewer data-cache misses; range selections and updates in memory 17 to 25% faster; TPC-H queries 11 to 48% faster (abstract, §7). lexdb's plain step gives 6 to 42% on scan-bound queries: the same range.
  - Writes: filling pages to 100% cost 10.1% on bulk load, from reorganising minipages; updates were 10 to 16% faster than row pages (§4.2, §6.4).
  - How lexdb differs: PAX changes minipages in place. lexdb encodes a leaf once per checkpoint, so it never reorganises, but pays a decode and an encode per changed leaf instead.
- **HyPer Data Blocks** (Lang et al., SIGMOD 2016).
  - Blocks of up to 2^16 rows, frozen and immutable; an update is a delete plus an insert into the uncompressed hot part (§1, §3).
  - Encodings: single value, ordered dictionary, truncation (frame of reference) to 1, 2 or 4 bytes (§3.3).
  - Why no bit-packing: "sub-byte encodings ... would indeed allow for greater compression ratios but increase the cost for point accesses and scans with low selectivities by orders of magnitude compared to our byte-addressable encodings" (§3.3). In their test, predicates ran 1.8 times faster on byte-aligned data and fetching 10% of the tuples over 3 times faster; bit-packing won only when every tuple qualified (§5.4). Byte alignment cost them about 25% more space than Vectorwise (Table 1).
  - Point reads through an index ran at about 55% of the uncompressed rate (Table 3).
  - **How lexdb differs, and why my result on bit-packing is the opposite:** their case rests on evaluating predicates with SIMD on the encoded bytes and on fetching a sparse set of positions afterwards. lexdb does neither: it decodes every row of the columns a query uses into a batch, then filters. Lexell has no SIMD. And a leaf is 43 to 73 rows, not 65,536. If lexdb later evaluates filters on encoded columns, this should be measured again.
- **BtrBlocks** (Kuschewski, Sauerwein, Alhomssi, Leis, SIGMOD 2023): 64,000-value blocks; an encoding chosen from a 1% sample (10 runs of 64 values), right 77% of the time and 3.3% from the best size; encodings cascade up to 3 deep (§3.1, §3.2, §6.3). lexdb's leaves are smaller than one such sample, so section 5 computes sizes exactly instead. Cascading (a dictionary whose codes are then run-length coded) has nothing to work on at 73 rows.
- **FSST** (Boncz, Neumann, Leis, VLDB 2020): section 6. The paper says a table per page "is perfectly feasible" (§3.4); at lexdb's page size it is not, by the measurements above. Their table is built from a 16 KB sample of a 4 MB chunk.
- **DuckDB:** row groups of 122,880 rows; column segments in 256 KiB blocks; per segment an analyze pass picks among constant, RLE, bit-packing, frame of reference, dictionary, FSST and others, at checkpoint (storage docs; "Lightweight Compression in DuckDB", 2022). Its bit-packing sets a width per 1,024 values. Its blog measured zstd at ratio 1.72 on 1 KB blocks against 2.54 at 256 KB. Not confirmed at the source: that min/max is kept per segment as well as per row group, and how updates are merged at checkpoint.
  - How lexdb differs: DuckDB has no B+tree of rows, and a point read by key is not what it is built for. "Recompress at checkpoint" is the part that carries over.
- **WiredTiger (MongoDB):** "The format of the in-memory pages is not the same as the format of the on-disk pages"; reconciliation writes an in-memory page as one or more disk pages at eviction and checkpoint. Defaults: leaf pages 32 KB, internal pages 4 KB, allocation unit 4 KB; key prefix compression and block compression are options (tuning docs). This is the write model of section 7. Its 32 KB leaves assume block compression and a row store; section 3 shows what 32 KiB costs lexdb.
- **Page size.**
  - LeanStore used 16 KB pages. Haas and Leis (VLDB 2023, "What Modern NVMe Storage Can Do, And How To Exploit It", §2.2) later found 4 KB "the best choice for systems that optimize for out-of-memory performance": with 16 KB pages and 100-byte records they count 160 times I/O amplification, 4 KB cuts it by 4, and below 4 KB the drive's own translation layer loses. My write table agrees: page bytes per random update grow in step with the page.
  - Umbra uses 64 KiB pages and larger size classes, with PAX leaves, for in-memory speed with data on SSD (Neumann and Freitag, CIDR 2020).
  - Defaults elsewhere: PostgreSQL 8 KB, InnoDB 16 KB, SQLite 4 KB, SQL Server 8 KB.

## 10. Found on the way (outside this study)

- **A single-row autocommit commit writes 56 to 72 KB to disk** (`/proc/PID/io` `write_bytes`: 5.4 MB for 100 updates; 72 KB a statement over 20,000) [M]. That is why four checkpoints ran during 20,000 small updates. I did not look for the cause.
- **20,000 DELETEs in one transaction took 35 s** (1.7 ms each) and 20,000 INSERTs 5.2 s (253 µs each); 20,000 UPDATEs took 0.66 s (31 µs each) [M].
- **A freshly loaded data file is fragmented:** 1,067 extents after `COPY`, reading at 552 MB/s sequentially; a plain copy of it has 7 extents and reads at 1,590 MB/s [M]. Cold scans on the fresh file were 25% slower (198 against 159 ms). The cold figures in section 3 are from copies.
- **Without statistics** (the fresh loads), `join_hash_agg` took 437 ms against 56 ms, and `sub_exists` 645 against 42 [M].

## Files

Branch `study/columns`, under `lexell/bench/columns/`:

| File | What it does |
|---|---|
| `proto.lxl`, `apply.py` | the prototype and how it is put into `cmd/lexdb_exec.lxl` |
| `cmd/pagebench.lxl` | `pagebench DATADIR TABLE REPS SETS PERS FLAGS`: decode, point, encode, to-rows |
| `e2e.py`, `tab.py`, `bench.py`, `qall.txt`, `qfsst.txt` | interleaved whole-query runs and their tables |
| `writes2.py` | the write benchmark |
| `build_ps.sh`, `load.sh` | other page sizes; a fresh load |
| `gen_e.py`, `zone_calc.py`, `zone.sh` | table `e`; what summaries can skip; the skipping runs |
| `fsst_tool.cpp` | FSST ratio and speed; `dump` writes a symbol table for the prototype |
| `fio_ps.sh`, `fio.sh`, `cold.py`, `cachehit.py` | disk, cold and cache runs |
| `out/` | every result file behind the tables here |

The scratch copies of the data directories are removed. The FSST source (a clone of github.com/cwida/fsst) is not kept; `fsst_tool.cpp` says how to build against it.
