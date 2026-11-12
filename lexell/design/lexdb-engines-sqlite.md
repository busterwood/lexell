<!-- Research notes, 2026-11-12: written by a subagent reading the SQLite source (tip 3b703ebf, 3.55.0) for lexdb-engines.md. Bytecode from sqlite3 3.54 on empty tables; source read, not benchmarked. -->

# How SQLite executes the query shapes where lexdb loses to PostgreSQL

Source: `github.com/sqlite/sqlite` shallow clone, tip 3b703ebf (VERSION 3.55.0, 2026-11-12). Line numbers refer to that tree.
Bytecode listings come from the installed `sqlite3` 3.54.0, running `EXPLAIN` on empty in-memory tables with the benchmark schema (`w(id INTEGER PRIMARY KEY, a int, b int, c bigint, name text, city text, price numeric(10,2), flag bool, note text)`, `create index w_b on w(b)`, plus `d(k,grp)`, `t(id integer primary key, x)` and `cr(city, r)`). The tables were empty and had no ANALYZE statistics, so the plans on 1M-row tables could differ. Where that matters, it is noted.
Anything marked **(inferred)** is my reasoning, not something read in the source. No benchmarks were run.

## 0. Background shared by all areas

- **Register VM.** A statement compiles to a flat array of opcodes that operate on an array of `Mem` registers (`vdbe.c`, `sqlite3VdbeExec`, one big `switch`). There is no tree-walk at run time and no lookup of columns by name: `OP_Column P1 P2 P3` means "cursor P1, column index P2, into register P3".
- **Record format.** A row is `[header-size varint][serial-type varint per column][column bodies]`. The serial type encodes both type and width: 0 = NULL, 1–6 = big-endian int of 1/2/3/4/6/8 bytes, 7 = float64, 8/9 = the constants 0/1, N≥13 odd = text of (N-13)/2 bytes, N≥12 even = blob (`sqlite3VdbeSerialGet`, vdbeaux.c:4122).
- **Rowid tables.** An `INTEGER PRIMARY KEY` column *is* the B-tree key (a 64-bit int stored as a varint in the cell) and is not stored in the record. `OP_Rowid` reads it from the cell header.
- **NUMERIC columns hold binary numbers.** `numeric(10,2)` gets NUMERIC affinity (`sqlite3AffinityType`, build.c:1737: none of INT/CHAR/CLOB/TEXT/BLOB/REAL/FLOA/DOUB matches). On write, `applyNumericAffinity` (vdbe.c:354) converts '12.50' to a REAL or an INT. Reading `price` is therefore an 8-byte float decode (OP_Column serial type 7); no decimal parsing happens on read. This is a semantic difference: SQLite's NUMERIC is not exact decimal.

---

## 1. Sort

### 1a. In-memory sort (vdbesort.c)
- **What is sorted.** `ORDER BY c` compiles to `SorterOpen / MakeRecord(c, id) / SorterInsert` per row, then `SorterSort / SorterData / Column(pseudo-cursor) / SorterNext`. Each sorter entry is one serialized record holding the key columns followed by the payload columns (`pushOntoSorter`, select.c:774). There is no array of value objects.
- **Storage.** `sqlite3VdbeSorterWrite` (vdbesort.c:1944) memcpy's the record into one bulk buffer `list.aMemory`, which doubles with realloc (2016–2033). Each entry carries a 16-byte header, `SorterRecord {int nVal; union{ptr,int iNext}}` (vdbesort.c:448), and entries are linked by offset. That means one allocation for the whole sort, not one per row.
- **Algorithm.** `vdbeSorterSort` (vdbesort.c:1571) is a bottom-up merge sort of a linked list. It keeps 64 slots of sorted runs whose sizes are powers of two and merges them with `vdbeSorterMerge` (1513). There is no quicksort and no array of pointers.
- **Specialised comparator.** `sqlite3VdbeSorterWrite` maintains `typeMask` from the serial type of the *first* field of every record (1957–1969). `vdbeSorterGetCompare` (1555) then picks one of these:
  - `vdbeSorterCompareInt` (853): reads the two serial types (`p[1]`). If they are equal it compares the big-endian bytes in a loop, fixing up only the sign. 0/1 constants and mixed widths are handled arithmetically. No value is decoded into a `Mem`.
  - `vdbeSorterCompareText` (810): a `memcmp` of the two text bodies located through the header, then the lengths. Used only for BINARY collation.
  - `vdbeSorterCompareReal` (1024).
  - Generic `vdbeSorterCompare` (791): unpacks key 2 into an `UnpackedRecord` once and caches it with the `bCached` flag across consecutive comparisons in a merge (see `vdbeSorterMerge`, which resets `bCached` only when p2 advances). It then calls `sqlite3VdbeRecordCompare`.
  - The fast paths are enabled only when there are fewer than 13 fields, the first key uses default collation and the first key is not NULLS-LAST (vdbesort.c:1180–1185). Ties on the first field fall to `vdbeSorterCompareTail` (764), which runs the generic comparator on the remaining fields.
- **Reading back.** `SorterData` copies the record into a register, and a pseudo-cursor (`OpenPseudo`) lets `OP_Column` decode it lazily (see area 3).

### 1b. Spilling and worker threads
- **Memory limit.** The in-memory limit is `mxPmaSize = max(szPma*pgsz, cache_size bytes)`, capped at 512 MiB (`SQLITE_MAX_PMASZ`, vdbesort.c:155). See `sqlite3VdbeSorterInit` 1154–1170. With the defaults this is small: `SQLITE_SORTER_PMASZ` = 250 pages (global.c:190) × 4096 = 1 MB, and `SQLITE_DEFAULT_CACHE_SIZE` = -2000, i.e. 2 MB (sqliteLimit.h:161). So the limit is **about 2 MB**.
- **Spilling.** Past that limit, the list is sorted and written as a "PMA" (sorted run) to a temp file (`vdbeSorterFlushPMA`, 1874). The runs are then merged incrementally by a `MergeEngine` tournament tree, at most `SORTER_MAX_MERGE_COUNT` = 16 runs at a time (466).
- **When the sort stays in memory (inferred arithmetic).** A 1M-row `(c,id)` sort needs about 30 bytes per entry, so roughly 30 MB. With default settings that is about 15 PMAs on temp files, all in one thread. If temp storage is in memory (`sqlite3TempInMemory`), the whole limit block is skipped: there is no spill, and records are malloc'd one by one instead of going into the bulk buffer (1154).
- **Worker threads.** `SQLITE_MAX_WORKER_THREADS` defaults to 8 and `SQLITE_DEFAULT_WORKER_THREADS` to **0** (sqliteInt.h:748–757). So the sorter is single-threaded unless `PRAGMA threads=N` is set.
  - With threads, each flush (sort the list, then write the PMA) runs on a background thread, round-robin over N subtasks (`vdbeSorterFlushPMA` 1890–1935). Merging can also run in background threads (`vdbeIncrBgPopulate`, header comment lines 116–134).
  - Threads are forced to 0 when temp storage is in memory (1101). So an all-in-memory sort is always single-threaded.
- **Sort elimination.** The benchmark query `select id, b from w order by b` performs **no sort at all** in SQLite. It becomes `SCAN w USING COVERING INDEX w_b`: `Rewind/IdxRowid/Column/ResultRow/Next` on the index B-tree. The index key is (b, rowid), so it is covering for `id, b`. Only `ORDER BY c` (not indexed) used the sorter.

### 1c. ORDER BY … LIMIT
- **Bounded B-tree instead of a sorter.** When a LIMIT is present, `SORTFLAG_UseSorter` is not set (select.c:8585–8588). The "sorter" is then an ephemeral **index B-tree** (`OpenEphemeral`) that holds at most LIMIT+OFFSET entries. Code is in `pushOntoSorter`, select.c:880–914. Bytecode for `select id,b,name from w order by c desc limit 10`:
  ```
  5  Column   w.c -> r2          ; ORDER BY key only
  6  Sequence
  7  IfNotZero r1 (LIMIT counter) -> 11   ; still filling: insert
  8  Last     eph                 ; current largest entry
  9  IdxLE    eph, r2 -> 16 (Next) ; new key not better: skip row
  10 Delete   eph                 ; evict largest
  11 Rowid / Column b / Column name   ; payload loaded only now
  14 MakeRecord ; 15 IdxInsert
  ```
- **Deferred payload loading.** The non-key result columns are computed only after the row is known to enter the top-N. `SortCtx.pDeferredRowLoad` (select.c:1362–1369) and `makeSorterRecord` (752) call `innerLoopLoadRow` only at that point. A rejected row therefore costs one `OP_Column`, an `OP_Last` on a tiny tree (its pages are already cached; `BTCF_AtLast` makes repeated Last nearly free, btree.c:5815), and one `IdxLE` record compare. **(inferred)**
- **Early exit for nested loops.** If the inner loop already produces rows in order, `sqlite3WhereOrderByLimitOptLabel` (where.c:101) makes a rejected row skip the rest of the inner loop.
- **Sorter references.** `SQLITE_ENABLE_SORTER_REFERENCES` (store the PK, not large columns, in the sorter) exists (select.c:1088) but is a compile-time option and is off by default.

### Why it is cheap, and whether SQLite is fast here
- **Most plausible reasons:**
  1. The sort entry is one contiguous serialized record in a bulk buffer, compared with type-specialised byte comparators that never materialise values (`vdbeSorterCompareInt/Text`).
  2. For top-N, a LIMIT-sized B-tree with a single compare against the current maximum, and payload columns loaded only for rows that get in.
- **Is SQLite fast at a 1M-row single-threaded sort?** Probably not especially **(inferred, not measured)**. It is a pointer-chasing linked-list merge sort, worker threads are off by default, and above 2 MB it spills to temp files by default. Its practical advantage on `order by b` is that it avoids the sort through the covering index. The top-N case, however, is genuinely cheap.

## 2. DISTINCT and GROUP BY

- **DISTINCT on an unindexed column.** `select distinct city from w` compiles to:
  - `OpenEphemeral k(1,B)` with p5 = `BTREE_UNORDERED`;
  - per row, `Column city / Found eph,r1 (skip if present) / MakeRecord / IdxInsert p5=OPFLAG_USESEEKRESULT / ResultRow`. See `codeDistinct`, select.c:977, default branch.
  - `OP_Found` with P4 = field count compares the **unpacked registers** against the B-tree directly; no probe record is built (vdbe.c, OP_Found, `r.aMem = pIn3` path).
  - `OPFLAG_USESEEKRESULT` lets `IdxInsert` reuse the cursor position left by the `Found` seek (`sqlite3BtreeInsert`, btree.c:9575), so a new value costs one descent, not two.
  - `BTREE_UNORDERED` ("Use of a hash implementation is OK", btree.h:63) is only a hint. btree.c uses it in a single assert, so the set is still a B-tree.
  - With few distinct cities the tree is a single page, so each row is one binary search using `vdbeRecordCompareString` (memcmp) **(inferred from data shape)**.
- **Other DISTINCT kinds.** `WHERE_DISTINCT_UNIQUE` (sqliteInt.h:3517) produces no code. `WHERE_DISTINCT_ORDERED` (input already ordered by an index) compares with the previous row (`OP_Ne/OP_Eq` against `regPrev`). `fixDistinctOpenEph` (select.c ~1065) then turns the ephemeral open into a no-op.
- **GROUP BY without a usable index.** It sorts; SQLite has **no hash aggregation**. `select city, count(*), avg(price) from w group by city` compiles to:
  - `SorterOpen`, then per row `Column city, Column price, MakeRecord, SorterInsert`. Only the grouping and argument columns go into the sorter.
  - Then `SorterSort` and a streaming pass: `Compare` with the previous key, then `Jump`. On a key change, `Gosub` emits the group (`AggFinal`) and resets the accumulators. Each row runs `AggStep`.
  - With an index on the group key, the sort disappears and the same streaming code runs over the index.
- **Aggregate steps.** `OP_AggStep` (vdbe.c:8097) builds the `sqlite3_context` on its **first** execution and rewrites itself to `OP_AggStep1`, so later rows pay only an indirect call to `xSFunc`. The accumulators are `sqlite3_aggregate_context` blobs: `countStep` func.c:2123, `sumStep` func.c:1988 (Kahan-Babuska-Neumaier for reals, func.c:1932).
- **Why it is cheap / is it fast:**
  1. DISTINCT costs one B-tree probe per row on a tiny tree, probing with the column register directly. This is cheap.
  2. GROUP BY on an unindexed column pays a full external sort, the same cost as area 1. **(inferred)** For this query SQLite is not structurally faster than a hash aggregate. Its per-row gain is in decoding (area 3) and in `avg(price)` reading a float.

## 3. Record decoding and column access (OP_Column, vdbe.c:3047)

- **Per-cursor header cache.** Each `VdbeCursor` holds `aType[nField]` (serial types) and `aOffset[nField+1]` (byte offsets), plus `nHdrParsed` and `iHdrOffset` (vdbeInt.h:125–138). The cache is keyed by `cacheStatus == p->cacheCtr` (vdbe.c:3078). Any cursor movement bumps the counter, which invalidates it.
- **Lazy, incremental header parse.** On the first `OP_Column` after a move, SQLite reads the header size and, if the header fits on the page, jumps straight into the header-parse loop. The comment there says this branch skips tests and gives a "measurable performance gain", vdbe.c:3150.
  - The parse loop (`op_column_read_header`, 3191) walks serial types only **up to column p2** (`while i<=p2`) and records offsets as it goes.
  - The next `OP_Column` for a higher column resumes from `nHdrParsed`. For a lower column it is a direct array lookup.
  - Reading column 1 of a 9-column row never touches the headers of columns 2–8. Reading all 9 in order is a single pass over the header.
- **No copy of the row.** `pC->aRow` points directly into the B-tree page (`sqlite3BtreePayloadFetch`).
  - Value extraction is an inlined switch on the serial type (3265–3354): ints are read as big-endian 1–8 bytes, and 0/1 come straight from the serial type (zero body bytes).
  - Text is `memcpy`'d into the destination register's **existing buffer** when `szMalloc >= len+2` (3338). Steady state therefore performs no allocation per row: a register's buffer is reused for every row.
  - The generic `sqlite3VdbeSerialGet` (vdbeaux.c:4122) does not copy text at all. It sets `MEM_Ephem` with `z` pointing into the page; it is used for record unpacking in comparisons.
- **Overflow pages.** If the column lies past the locally stored part of the payload (`szRow < aOffset[p2+1]`), `vdbeColumnFromOverflow` reads the overflow chain (3355). For `typeof()`, `length()` of a blob, or zero-length values it skips reading the content entirely (`OPFLAG_TYPEOFARG/LENGTHARG`). With 4K pages a table-leaf cell keeps up to about 4061 bytes locally, so typical rows never touch this path. **(inferred from maxLocal = usable-35)**
- **Cursor width.** `OpenRead` P4 = the number of columns needed (for example 5 for `where a=5` selecting `id,b,name`), so `aType/aOffset` are sized to the highest column used.
- **`select *`.** `Rowid` plus 8 `Column` opcodes into consecutive registers, then `ResultRow`. `ResultRow` hands out the registers without building a row object.
- **Why it is cheap:**
  1. Columns are decoded on demand by index, with the header parse amortised across columns of the same row and done only as far as needed.
  2. Fixed-width decodes come straight from the page, and text copies go into reused register buffers, so nothing is allocated or reference-counted per value. NUMERIC is a float decode, not a decimal parse.

## 4. Expression evaluation

- **Compiled to opcodes.** `select id, a+b, price*2, upper(city) from w` becomes:
  ```
  Rowid->r1; Column a->r5; Column b->r6; Add r6,r5->r2;
  Column price->r6; Multiply r7,r6->r3;          (r7 = constant 2)
  Column city->r6; Function upper(r6)->r4; ResultRow r1..r4
  ```
  - Temporary registers are reused: r6 holds three different columns in sequence (`sqlite3GetTempReg/ReleaseTempReg`, `sqlite3ExprCodeTemp`, expr.c:6034).
- **Constant factoring.** `sqlite3ExprCodeRunJustOnce` (expr.c:5955) moves constant subexpressions into the initialisation section at the end of the program: `Integer 2 -> r7` runs once at address 15, before the loop. Identical constants share a register. Constants that involve function calls are instead guarded by `OP_Once`. Factoring is applied through `sqlite3ExprCodeTemp` and `sqlite3ExprCodeFactorable` (expr.c:6103).
- **Arithmetic.** `OP_Add/Multiply` (vdbe.c:1952): if both flags have `MEM_Int`, it does an overflow-checked i64 op (`sqlite3AddInt64`). Otherwise it does double arithmetic, so `price*2` is one float multiply.
- **Function calls.** The `FuncDef` is resolved at prepare time and stored in P4 as an `sqlite3_context` (`P4_FUNCCTX`). `OP_Function` (vdbe.c:9109) re-initialises `argv` only if the output register changed, then makes one indirect call `pCtx->pFunc->xSFunc(pCtx, argc, argv)`. There is no name lookup and no per-call setup.
- **`upper()`.** `upperFunc` (func.c:545) **does** `sqlite3Malloc(n+1)` per row (`contextMalloc`) and loops `sqlite3Toupper` (ASCII table) over the bytes. The result is handed to the register with `sqlite3_free` as destructor. So upper() costs one malloc/free per row; it is not free.
- **LIKE.**
  - `note like '%item 77%'` → `Function like(pattern_reg, note_reg)`. The pattern is a factored constant (`String8` in the init section).
  - `likeFunc` (func.c:959) → `patternCompare` (func.c:769). After a leading `%`, if the next pattern char is ASCII, it uses **`strcspn(zString, zStop)`** to jump to candidate positions. `zStop` holds both cases, because the default LIKE is case-insensitive. It then checks the following char inline before recursing (func.c:842).
  - libc `strcspn` is typically SIMD-accelerated **(inferred)**.
  - The "LIKE optimization" (rewrite to an index range) requires a pattern that does **not** start with a wildcard (`isLikeOrGlob`, whereexpr.c:215 header comment), so it does not apply to `'%item 77%'`.
- **Why it is cheap:**
  1. Expressions are flat opcodes over typed registers, with constants hoisted out of the loop and functions pre-bound.
  2. Int and float arithmetic works directly on `Mem.u.i/u.r` with no boxing.

## 5. Filters: order of WHERE terms relative to column reads

- **Columns read only when a term runs.** The residual WHERE terms are emitted by `sqlite3WhereCodeOneLoopStart` (wherecode.c:2799–2878) as `sqlite3ExprIfFalse(..., addrCont)`. That is a conditional jump to the loop's `Next`, so terms short-circuit one by one. Each term's `OP_Column` reads are emitted inside that term's code.
  - `where a = 5`: `Column a → Ne r1, const5 → Next`. `Rowid`, `Column b` and `Column name` come only **after** the test.
- **Pass ordering.** Up to three passes order the terms (comment at wherecode.c:2799–2817):
  1. iLoop 1: terms covered entirely by the index being scanned. They run *before* the table row is fetched, which is possible because the table seek is deferred.
  2. iLoop 2: terms without correlated subqueries.
  3. iLoop 3: everything else.
  Within a pass, terms keep WHERE-clause order.
- **Why it is cheap:** a row that fails the first term costs one lazy `OP_Column` (partial header parse) and one compare. Nothing else is decoded for it.

## 6. Joins

### 6a. No hash join: nested loops with an automatic index and a Bloom filter
- **Plan for the text-key join.** `select count(*) from w join cr on w.city=cr.city` produces `SCAN w`, `BLOOM FILTER ON cr (city=?)`, `SEARCH cr USING AUTOMATIC COVERING INDEX (city=?)`:
  ```
  Once -> { OpenAutoindex; Blob 10000 (filter);
            for each cr row: Column city, Rowid, MakeRecord, FilterAdd, IdxInsert }
  for each w row: Column city; IsNull; Filter (skip if not in bloom);
                  SeekGE autoidx; IdxGT; AggStep; Next
  ```
- **Automatic index.** `constructAutomaticIndex` (where.c:1016) builds a transient covering index on the inner table once (`OP_Once`). It is a B-tree; SQLite never builds a hash table.
  - Planner cost (where.c:4180–4225): a one-time X·N·log2(N) build, with X = 7 for tables and 0.5 for views and subqueries. Each lookup is assumed to yield 20 rows.
  - `addrDeleteCont` (where.c:7753) deletes an auto-index entry that found no inner match, so later probes for it fail sooner.
- **Bloom filter (3.38+).** The filter is a `Blob` register: 10,000 bytes (80K bits) for auto-indexes (where.c:1236). For `sqlite3ConstructBloomFilter` it is sized from `sqlite_stat1` row estimates, clamped to 10K–10M bytes (where.c:1361–1383).
  - `OP_FilterAdd/OP_Filter` (vdbe.c:9214, 9250) use `filterHash` (vdbe.c:696). The hash is cheap: ints add `u.i`; strings add the length, the first 8 bytes and the last 8 bytes, with no SipHash. It is followed by one bit test.
  - A miss skips the B-tree seek entirely.
  - On real tables, a Bloom filter on a normal index requires ANALYZE stats, and is used when the search count exceeds the table's row count and some searches are expected to miss (`whereCheckIfBloomFilterIsUseful`, where.c:6774).
- **Omit-noop-join** (`whereOmitNoopJoin`, where.c:6682) only drops unused LEFT-JOINed tables. **Push-down** (`pushDownWhereTerms`, select.c:5365) pushes WHERE terms into subqueries and views. Neither applies to these inner joins.

### 6b. Join on the integer primary key
- **Plan.** `w join t on t.id = w.b`, count: `SCAN w USING COVERING INDEX w_b` (the narrowest structure that has b), then `SEARCH t USING INTEGER PRIMARY KEY`:
  ```
  Column w_b.b -> r2; SeekRowid t, r2 (skip if absent); AggStep; Next
  ```
- **`OP_SeekRowid` → `sqlite3BtreeTableMoveto`** (vdbe.c:5663 → btree.c:5846).
  - The key is a raw i64 compared with `<`/`>` against varint-decoded cell keys (`sqlite3VarintValue`) during a binary search over the page's 2-byte cell-pointer array (`findCellPastPtr`, btree.c:1193).
  - There is no memcmp and no key encoding. Interior pages hold only (child page, int key), so their fanout is high. For 1M rows the tree is probably 3 levels deep **(inferred)**.
  - The cursor keeps the root page pinned. `moveToRoot` with `iPage>0` just releases the child pages and reuses `apPage[0]` (btree.c:5605–5613), so the root needs no page-cache lookup. Each child level is a `sqlite3PagerGet` hash lookup.
- **Fast paths before descending** (btree.c:5862–5890):
  - Cursor already on `intKey` (`BTCF_ValidNKey`, same key): return at once.
  - Cursor at the last entry (`BTCF_AtLast`) and key > current: return "not found / append position" at once.
  - **Key == current + 1:** try `sqlite3BtreeNext` (btree.c:6425). `Next` is usually just `++ix` on the same leaf, plus a key check.
  - There is **no** general "the key is on the current leaf" check for table B-trees. Anything else does a full descent from the root.
- **Ordering effect (inferred).** Because the outer loop scans `w_b`, the probe keys `w.b` arrive in **ascending order**. Duplicate b values hit the same-key fast path, consecutive values hit the +1 path, and other probes touch the same few recently used pages, which stay hot in cache.

### 6c. Index seeks and the record comparator
- **`sqlite3BtreeIndexMoveto`** (btree.c:6077). It picks a comparator once per seek with `sqlite3VdbeFindCompare` (vdbeaux.c:5117):
  - `vdbeRecordCompareInt` (vdbeaux.c:4975): reads 8 bytes and does an arithmetic shift by `aShift[serial_type]` to sign-extend a 1/2/3/4/6/8-byte big-endian int without a switch. The comment says the switch "tends to mispredict when a key column contains integers of varying sizes". It then compares one i64.
  - `vdbeRecordCompareString` (vdbeaux.c:5047): a single `memcmp` of the text body against the probe string, then the lengths.
  - Both apply only when the key has 13 or fewer fields, a one-byte header and BINARY collation. Otherwise the generic `sqlite3VdbeRecordCompareWithSkip` is used.
- **The probe is unpacked registers.** The probe is an `UnpackedRecord` pointing at registers (typed `Mem`s). Only the on-page cell is parsed, and only its first field unless there is a tie.
- **Cells inside the page are compared in place.** `indexCellCompare`, and the binary search at btree.c:6175–6200, compare the record directly from the page when the size varint is 1–2 bytes. A buffer is malloc'd only for overflow cells.
- **Skip-the-descent for index seeks:** only for the **last page of the tree**. If the cursor is on the rightmost leaf and the key is ≥ its first cell, the search starts on that page; if it is ≥ the last cell, nothing moves (btree.c:6110–6136). This serves append-order inserts and seeks, not general locality.

### Why it is cheap / is it fast
1. The int-PK join is a nested loop whose inner step is an int-keyed binary search with no encoding. Probes arrive in sorted order (from the covering-index outer scan), which makes them cache-friendly and often lets them hit the same-key or +1 fast paths. **(The ordering point is inferred from the plan.)**
2. Text-key joins against a small table cost one cheap hash plus one bit test per outer row (Bloom), and a probe of a tiny B-tree only on a possible hit.
   - Against a large inner table with no index, SQLite would build an auto-index costing N log N, B-tree inserts rather than hash inserts. **(inferred)** That is not obviously cheaper than a hash join.

## 7. B-tree layout

- **Page layout** (btreeInt.h:107–200): a page header, then an array of 2-byte cell pointers, then cell content growing from the end of the page.
  - Binary search uses the pointer array: `findCellPastPtr(P,I) = aDataOfst + get2byteAligned(&aCellIdx[2*I])`.
  - `MemPage.intKey` distinguishes table B-trees from index B-trees (btreeInt.h:275).
- **Table B-trees (rowid).** Interior cells are `(4-byte child, varint key)`. Leaf cells are `(varint payload size, varint rowid, record)`. The data lives only in the leaves (B+tree).
- **Index B-trees.** The key *is* the record `(indexed cols..., rowid)`, with no separate data. Interior cells hold full keys.
- **Covering indexes.** When every column needed is in the index, there is no table access: `SCAN w USING COVERING INDEX w_b` for `select id,b ... order by b` and for the join outer loop. The rowid comes from the index record (`IdxRowid`).
- **`OP_DeferredSeek`** (vdbe.c:6932). `where b > 90000` selecting `id,b,name` gives:
  ```
  SeekGT w_b; loop: DeferredSeek w <- w_b.rowid; IdxRowid; Column w_b.b; Column w.name; ResultRow; Next w_b
  ```
  - The table seek is recorded, not performed. It happens inside `OP_Column` (`sqlite3VdbeFinishMoveto`, vdbeaux.c:3844 → `sqlite3BtreeTableMoveto`) only when a column absent from the index is read.
  - P4's `aAltMap` redirects reads of columns that are in the index (here `b`) to the index cursor (vdbe.c:3099–3102).
  - Index-covered WHERE terms run before the deferred seek (area 5, iLoop 1), so rejected rows never touch the table.
  - For rows that are returned and need `name`, it is still one full table descent per row, unless rowids happen to be consecutive (+1 fast path).

**Why it is cheap / is it fast:** in the 100k-row index-range case, SQLite does essentially what lexdb does, an index entry plus a PK fetch per row. Its edge is the cheaper int-key descent of area 6b, and the `aAltMap`/covering reads that avoid table access for indexed columns. SQLite has no bitmap-heap-scan equivalent. **(inferred)** It is not structurally different here.

## 8. Subqueries

### IN (subquery)
- **Ephemeral index plus Bloom filter.** `count(*) from w where a in (select k from d where grp=3)` gives `SCAN w` and `LIST SUBQUERY 1`, with `CREATE BLOOM FILTER`:
  ```
  BeginSubrtn/Once -> { OpenEphemeral k(1,B); Blob 10000 (bloom);
                        scan d: Column grp; Ne 3; Column k; MakeRecord; IdxInsert; FilterAdd }
  per w row: Column a; Copy; Affinity; IsNull; Filter (bloom, skip) ; NotFound eph (skip); AggStep
  ```
- **`sqlite3FindInIndex`** (expr.c:3309; header comment just above it) chooses one of:
  - an existing table (IN_INDEX_ROWID, when the RHS is an INTEGER PRIMARY KEY);
  - an existing index whose leftmost column matches (IN_INDEX_INDEX_ASC/DESC);
  - an ephemeral B-tree (IN_INDEX_EPH);
  - for literal lists, a chain of compares (IN_INDEX_NOOP).
- **`sqlite3CodeRhsOfIN`** (expr.c:3678) fills the ephemeral table once (uncorrelated → `OP_Once`, and as a subroutine). Since this version it also fills a **Bloom filter** (expr.c:3816–3828). The filter is used only for BINARY collation (tag-202607231411).
- **Per-row probe.** `OP_NotFound` with P4 = field count probes with the register directly (no record build), after the Bloom test.
- **IN as a loop driver.** If `w.a` were indexed, the planner could use the IN set to drive the loop instead (`WHERE_COLUMN_IN`, the `IN_INDEX_LOOP` mode): iterate the RHS values and seek the index for each.

### EXISTS
- **EXISTS-to-JOIN (`existsToJoin`, select.c:7601, called at 8229, optimization flag `SQLITE_ExistsToJoin`).** A WHERE-clause `EXISTS(SELECT … FROM one_table WHERE …)` without aggregates or LIMIT is rewritten into a join. The subquery's table is appended to the FROM list with `fg.fromExists=1` and its WHERE is ANDed in. In `sqlite3WhereEnd` the loop for that table ends with `Goto addrBrk` after the first match ("EXISTS break", where.c:7748), which makes it a semi-join.
- **Planning as a join.** Once rewritten, the correlated EXISTS is planned like any join. On the test schema it got `BLOOM FILTER ON d (k=? AND grp=?)` and `SEARCH d EXISTS USING AUTOMATIC PARTIAL COVERING INDEX (k=? AND grp=?)`. The auto-index is *partial*: only rows with `grp=3` are inserted. Per w row: `Column a; IsNull; Filter; SeekGE autoidx; IdxGT; AggStep; Goto break`.
- **When the rewrite does not apply,** a correlated subquery is re-run per outer row. There is subquery-result caching for some correlated scalar subqueries via `OP_BeginSubrtn`/`subrtnsig`, which is not examined in detail here.

**Why it is cheap:**
1. The subquery is materialised **once** into an ephemeral index with a Bloom filter. For most outer rows, IN reduces to a column read, a cheap hash and a bit test.
2. EXISTS is turned into a semi-join, so it gets the same auto-index and Bloom machinery instead of per-row subquery execution.

## 9. Window functions (window.c)

- **Rewrite** (window.c header, lines 17–75): the query is rewritten as `SELECT <window stuff> FROM (SELECT … FROM w WHERE … ORDER BY <partition>, <order>)`. The inner query is a **coroutine** that sorts with the ordinary sorter (area 1).
- **Bytecode for `row_number() over (partition by a order by c) where a<20`:**
  - The coroutine filters `a<20` first (lazy `Column a`, `Ge`), then `MakeRecord(a, c, rowid) / SorterInsert`. After `SorterSort` it yields one row at a time.
  - The outer code, per row: `MakeRecord`, then `Compare` the partition key with the previous one. On a change it calls the `flush_partition` subroutine.
  - It then does `NewRowid/Insert` into an ephemeral intkey table (the partition buffer), `AggStep row_number`, `AggValue`, `Gosub` the output subroutine, and `Delete` the buffered row.
- **`row_number`.** `row_numberStepFunc` (window.c:147) increments an i64 in the aggregate context; the frame is forced to `ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW`. Whether a whole partition is cached before output depends on the frame and functions (`windowCacheFrame`, window.c:2052). For row_number it is not: each row is inserted and deleted immediately. **(read from bytecode)**
- **Inserting into the buffer.** `NewRowid` and append-biased `Insert` into the ephemeral table hit the `BTCF_AtLast` fast path (btree.c:5868), so buffering is cheap.
- **Why it is cheap / is it fast:**
  1. The WHERE filter runs before the sort, so only matching rows are sorted.
  2. Window evaluation is a streaming pass over sorted output, with an O(1) step per row.
  The dominant cost is the sort plus a B-tree insert and delete per row. **(inferred)** That is reasonable, but not a special trick.

## 10. DML

### INSERT
- **General `INSERT … SELECT … WHERE`.** The select runs as a coroutine that yields registers. Per row:
  - `NotExists` checks the rowid.
  - `Affinity`, then `MakeRecord` for the index entry `(b, rowid)` and `MakeRecord` for the row.
  - `IdxInsert w2_b` (p5 = USESEEKRESULT; it re-seeks, see below).
  - `Insert w2` with p5 = 0x31 = NCHANGE|USESEEKRESULT|LASTROWID. It reuses the cursor position from `NotExists`: `sqlite3BtreeInsert` skips the seek when `seekResult != 0` (btree.c:9555–9560).
- **Append bias.**
  - `OPFLAG_APPEND/BTREE_APPEND` passes `biasRight=1` to `sqlite3BtreeTableMoveto`, so the binary search starts at the last cell (`idx = upr>>(1-biasRight)`, btree.c:5929).
  - More importantly, the insert path tries to leave the cursor on the last entry. The source says (btree.c:9710–9723): *"If the cursor is left pointing to the last entry in the table, and the next row inserted has an integer key larger than the largest existing key, it is possible to insert the row without seeking the cursor. This can be a big performance boost."*
  - When the rightmost leaf overflows, `balance_quick` (btree.c:8046) just starts a new right sibling instead of a three-way rebalance.
  - The index insert for random `b` is a full `sqlite3BtreeIndexMoveto` descent per row; the last-page shortcut helps only ascending keys.
- **`xferOptimization`** (insert.c:3109). Header: *"transfers raw records from tab2 over to tab1. Columns are not decoded and reassembled, which greatly improves performance. Raw index records are transferred in the same way."*
  - It applies only to `INSERT INTO t1 SELECT * FROM t2` with no WHERE, compatible schemas, and an empty destination if there are unique indexes.
  - Bytecode: `Rowid; NotExists; RowData; Insert p5=APPEND|...` per row. Then, **per index**, a separate loop `RowData; IdxInsert p5=OPFLAG_APPEND` that scans the source index **in key order**, so every index insert is an append. The destination cursor is opened with `OPFLAG_BULKCSR`.
  - Without the pre-update hook, `OP_RowCell` + `OPFLAG_PREFORMAT` copies the cell bytes unchanged (insert.c:3422–3433). In VACUUM mode, `OP_SeekEnd` avoids even the seek.
  - The benchmark's 103k-row INSERT…SELECT, presumably with a WHERE, would take the general path, not xfer. **(inferred)**

### DELETE
- **One pass, index entries deleted at once.** `delete from w where a < 10`, per matching row:
  - `Column b; Rowid; IdxDelete w_b key=(b,rowid)`;
  - `Delete w p5=OPFLAG_SAVEPOSITION`;
  - `Next`, which continues the same scan.
- **`ONEPASS_MULTI`** (delete.c:496–532, `sqlite3WhereOkOnePass`) deletes while scanning when there are no triggers, FKs or subqueries. Otherwise it collects rowids in a `RowSet` and deletes in a second pass (`OP_RowSetAdd/RowSetRead`, delete.c:580–626).
- **`OP_IdxDelete`** (vdbe.c:6853) is a **full `sqlite3BtreeIndexMoveto` per row** (unpacked registers, no record build), then `sqlite3BtreeDelete(BTREE_AUXDELETE)`. Index deletes are not batched or sorted.
  - `OPFLAG_FORDELETE` on the index cursor (p5 = 8) is only a hint for other storage engines (btree.h:219–239).
- **`sqlite3BtreeDelete`** (btree.c:9886) skips `balance()` when the leaf is still at least one third full: "If the free space is less than 2/3rds of the page, then balance() will always be a no-op" (btree.c:10047). With `SAVEPOSITION` the cursor stays positioned (`CURSOR_SKIPNEXT`), so the scan continues without a re-seek.
- **Same design as lexdb.** SQLite's DELETE has the same shape as the one described for lexdb: row by row, each index entry deleted immediately with one descent per row. **The 10k-row gap therefore cannot come from batching.** On this design SQLite's cost is roughly 10k × (one index descent + one leaf cell removal). **(inferred)**

### Page cache and journal
- **Writes are made per page per transaction, not per row.** `sqlite3PagerWrite` (pager.c:6303) returns immediately if the page is already `PGHDR_WRITEABLE` in this transaction. Only the first write of a page in a transaction calls `pager_write` (6117), which copies the original page to the rollback journal once (tracked in a `pInJournal` bitvec).
- **Durability work happens once per transaction.** fsync happens at commit. In WAL mode, dirty pages are appended as frames at commit.
- **Page-number ordering.** `balance_nonroot` reassigns new page numbers in ascending order to keep scans linear. The source says this "makes the database about 25% faster for large insertions and deletions" (btree.c:8749).

**Why it is cheap:**
1. Appends with integer keys need no seek: the cursor stays at the last entry, NotExists/Insert share one seek, and `balance_quick` handles the right edge. xfer avoids decoding entirely and inserts index entries in sorted order.
2. Journal and cache work is per page per transaction, and DELETE is one pass with no re-seek of the table cursor. For DELETE, SQLite is **not** algorithmically smarter than lexdb's per-row design.

---

## Summary: the main cause per losing case (all inferred from the mechanisms above)
| query | main SQLite mechanism |
|---|---|
| order by b (1M) | No sort: covering index `w_b` scanned in order. A real sort is a single-threaded linked-list merge sort with spill at about 2 MB, which is not especially fast. |
| order by c desc limit 10 | LIMIT-sized ephemeral B-tree: `Last`+`IdxLE` reject, payload columns loaded only for rows that get in. |
| distinct city | `Found`/`IdxInsert` on a tiny ephemeral B-tree, probing with the register directly. |
| select * / expressions | Lazy, incremental header parse; ints read directly from the page; text copied into reused register buffers; constants hoisted; pre-bound functions. NUMERIC is a float. upper() still mallocs. |
| filter a = 5 | Only `Column a` is decoded for rejected rows. |
| LIKE '%x%' | `strcspn` skip-ahead in `patternCompare`; the pattern is constant. |
| group by city | Sorts (no hash agg); avg over floats. |
| text-key hash join | Auto-index on the small side, Bloom filter (cheap additive hash plus one bit). |
| w join t on t.id = w.b | Covering-index outer scan gives ascending int keys; `SeekRowid` int binary search with no encoding; same-key/+1/AtLast fast paths. |
| index range 100k | Same as lexdb (index entry, then deferred PK fetch); cheaper int descent; `aAltMap` reads indexed columns from the index. |
| IN (subquery) | Materialised once into ephemeral index plus Bloom; per row a hash, a bit test and rarely a probe. |
| EXISTS | Rewritten into a semi-join (`existsToJoin`), then auto partial index plus Bloom. |
| row_number | Filter before sort; streaming O(1) step; append-biased buffer inserts. |
| INSERT…SELECT | Seek reuse (`USESEEKRESULT`), `BTCF_AtLast` append without seek, `balance_quick`; xfer only for unfiltered `SELECT *`. |
| DELETE 10k with index | Per-row `IdxDelete` (full descent) plus `Delete` with saved position, the same per-row design as lexdb; no balance unless under a third full. |
