# lexdb after owned strings: what the old language shaped (2026-11-18)

A review of lexdb (on `main` at fea3ca7a) for designs chosen when `str`
was a counted, copy-type value: a copy was a count bump, so passing,
storing and returning strings by value cost nothing. Under owned `str`
the same code copies bytes and calls `malloc`/`free`. The language now
also has things it lacked: free `&str` views and slices, `var` of a
borrow, `rc T` (shareable between tasks, which all run on one thread,
SPEC 16), borrows returned from methods and set-once globals.

## Measurements

All 22 TPC-H queries at SF1, once each after a warm-up, `perf record` of
the server (56,504 samples, pinned as for benchmarks). Point selects:
20,000 `select * from w where id = N` (hp/points.sql) twice. Copy counts
from an `LXL_RCSTAT=sites` build (tools/strsites.py). "Incl." is the
share of samples with the function on the stack.

| | TPC-H | point selects |
|---|---:|---:|
| the runtime's `malloc` + `rt_free` (self) | 6.9% | 11.9% |
| `Val` clone + drop glue (`gl112_dup`, `gl114_drop`) | 5.3% | 1.1%+ |
| everything under allocation, copy and drop | 16.8% | |
| heap string copies | 23.9M (337 MB) | 110 per statement |

The cost is spread over many sites, not one. The findings below are the
places where the spread comes from one design decision.

## Findings, largest first

### 1. Index and key lookups move rows as encoded strings (TPC-H: up to 10%)

`Store.getMany` (19.9% incl. of TPC-H) returns each row as an owned
`Option[str]` and `access.fetchMany` decodes it into a batch. On a column
leaf the row is first rebuilt from the columns (`lexdb_cols.rowOf`,
9.6% incl.), copied out, then decoded column by column again. Scans do
not do this: `scanLeaves` hands the leaf to `colsInto` under the lock.
Also, per lookup:
- `fetchMany` clones every probe key into `ks` (1.4M copies) only to
  pass them as `&[]str`;
- `getMany` tests `lf.key(li) == keys[i]`, copying the key to compare it.

Fix: give `getMany` the scan's shape, a callback with the leaf view and
the entry index inside the lock (`f(&LeafView, i)`), decoding straight
into the batch as `colsInto` does. Values stored apart still go the slow
way. The probe keys become `[]&str` views of `pr.keys`, and the compare
uses a view (`Node.keyView`, the twin of `valView`).

### 2. Batch text is one owned string per value (TPC-H: most of the remaining 7%)

`Batch.vals: [][]Val` holds each text value as its own `Val.Text(str)`.
Every value decoded is a `malloc`, every batch reused drops them
(`colsInto` → `Val` drop, 1.3%), and every gather, projection and key read
clones them (`bGather`, `bValAt`, `bKeyVal`, `newBatch`, `bxEval`:
`Val` clone 2.8%). With counted strings these were count bumps; this is
why q10 (+14.5%) and q13 (+6.8%) are still slower than before the switch.
The static dictionary pool (`lexdb_rows.dictVals`) works around one case.

Fix: a text column as one byte buffer plus offsets (a new `BVec` kind).
Decoding appends bytes; a gather copies a run of bytes into the new
batch's buffer; comparisons, hashing and LIKE read `&buf[a..b]` views.
Values become `Val.Text` only at the row engine's edge. With finding 3,
a scan's text column can instead share the leaf's bytes (`rc str` plus
offsets) and copy nothing. The dictionary pool then goes. This is the
largest change here and belongs with the executor work (P3, E-slices).

### 3. Page bodies are plain strings (writes; enables 1 and 2)

`Node.body` and `Node.cols` are `str`. `copyNode` (copy-on-write for
snapshot versions) clones both, so the first write to a clean leaf copies
the page. That was a count bump before. And nothing can hold a leaf's
bytes past the store's lock. As `rc str` both are shared in O(1). Tasks
run on one thread, so a handle may pass between tasks and outlive the
lock, and `par.map` may read through one. The cost is one more box per
page read, which is small. Not measured: TPC-H is read-only. Measure
with a write workload before and after.

### 4. Each statement re-decodes its tables from the catalog (point selects: 10–15%)

`exec.findTable` reads the table's catalog entry and decodes it on every
statement (`decTable`, 5.8% incl. of a point select). The binder then
copies each column name several times (`colDef` 18 copies per statement,
and `bindFrom`, `bcolOf`, `itemCols`, `runSelTo` and `OutCol.label` 9
each), and `bindFrom` is 14.4% incl. Cache the decoded table as an
`rc Table`, keyed by the catalog's change counter, as `lexdb_wire` already
keys described columns with `w.st.changes()`. Then let the binder and the
output description borrow names (`&str`) from it. `lexdb_memo` stores
`Map[str, str]`, values serialized to strings, which is the old language's
shape; typed `rc` values are now the natural cache.

### 5. Hash keys copied or built per row to look them up

- `AggSt.eat` (GROUP BY on one text column) clones each row's key
  (`ktext = x.clone()`) before `byText.get`, and keeps the copy only when
  the group is new. Look up by the view, and clone on insert.
- On composite keys it builds a new `StrBuf` and `toStr()` per row. Keep
  one buffer, clear it per row, look up `&buf`, and copy only on insert.
  `Map.get` takes `&K` already.

### 6. Small functions that return owned strings

- `lexdb_sql.text(&Val): str`: 1.44M copies in TPC-H. Add a view form for
  `Val.Text`.
- `lexdb_ops.bpTrim(&str): str`: 667K copies, applied to `text()`'s copy,
  so two copies. It can return `&s[0..k]`.
- `Node.key(i): str`: 8.6M copies. Its callers compare or keep the last key
  of a leaf, so a `keyView` serves them.

### 7. Expression evaluation returns owned values

`bxEval` (column, constant, parameter), `bValAt` and `bKeyVal` return
`Val` by value, cloning text. Accessors that return `&Val` for the cases
that only read remove those clones. Finding 2 removes most of them anyway.

### Language and runtime, not lexdb

- `malloc` and `rt_free` are Lexell's own allocator (compiler/native/rt.c):
  size classes, free lists per 2 MB chunk, and a fast path through the
  current chunk's lists. The samples sit on two loads, not on the
  allocator's logic. In `malloc` (4.3% of TPC-H, 7.6% of a point select)
  about 55% fall on popping a block from an older chunk's list: reading
  the freed block's next pointer and adding to the chunk's `live` count.
  In `rt_free` (2.6%, 4.3%) they fall on reading the block's header word
  and, for a block of an older chunk, on its chunk's list head and
  `live` count. So this is the cost of touching cold memory per
  allocation; fewer allocations (the findings above) is the fix. One
  thing to try in the runtime (not measured): every chunk's header is
  2 MB-aligned, so the headers of all chunks share the same cache sets,
  and each allocation or free in an older chunk writes one of them.
- Correction to fea3ca7a: it said a set-once global set by two tasks at
  once stops the program. Tasks run on one thread and `set` does not
  park, so that cannot happen; `par.map` kernels may not touch set-once
  globals. `initGlobals` is not needed; it is removed again.

## Not caused by the language

`memcmp` in tree descents (5.7%: `getMany`, `fingerTo`, `snapDescend`,
`scanLeaves`) is key comparison, and `readRows`'s pushed-key filter
(`Map[int, int]`, 2.5%) is an integer hash. Both are worth their own
look, but owned strings did not shape them.

## Status (2026-11-18, evening)

| finding | status | where |
|---|---|---|
| 1. lookups move rows as encoded strings | **done**: key views (step 1), rows decoded in the leaf (step 2) | ddcc4ef9, 74ddbc6d |
| 2. batch text one owned string per value | **done** in the pipeline: a text column is one buffer per batch plus offsets (`BK_TEXT`); comparisons, LIKE, IN, sort, hash and group keys, min/max, gathers and the wire read the bytes in place. Analytic suite -6.7% CPU, TPC-H level. exec's older batch paths still hold values | d0f00b92 |
| 3. page bodies plain strings | **measured, not taken**: a lazy leaf's body, entries, columns as `rc` made no difference to updates or commit latency (2026-11-18, reverted). A changed leaf's keys and values are counted instead (`Node.keys: rc []str`, `Node.vals: []rc str`), which fixed the update regression | eababf57 |
| 4. tables re-decoded per statement | **done** (shared `rc Table`); the binder's per-statement name copies remain (`colDef`, `bindFrom`, `colPart`, `cloneExpr`: about 20 copies an executed `UPDATE`) | b487153f |
| 5. hash keys built per row | **done**: views for one text key; composite keys in one reused string | ddcc4ef9, fea5295d |
| 6. small functions returning owned strings | **mostly done**: `Node.key` callers read `keyView` (f387f7f0); `lexdb_sql.textIn` (a view of a text, 48c22c45) used by bpchar's trim; `text()` itself still copies at its other callers | 48c22c45, f387f7f0 |
| 7. evaluation returns owned values | **open** (`bxEval`, `bValAt`, `bKeyVal`); finding 2 removed the text cases from the hot paths | |
| runtime: `memcmp` in descents | **done** in the runtime: `rt_str_cmp` compares short strings 8 bytes at a time | aaadeb1e |
| runtime: allocator chunk headers sharing cache sets | **open**, not tried | |

Found since (benchmark refresh, design/lexdb-benchmarks.md 1): updates at
32 clients -52% (fixed, eababf57); commit latency p99 0.81 to 1.39 ms
(open); COPY peak memory +30% (open; not copies: f387f7f0 cut COPY's copies
by 30% and the peak did not move); the clone-site profile's other copies
(f387f7f0).

## Suggested order

1. Small and local, about a day: findings 5 and 6, the key views in
   finding 1, and finding 7's accessors where they are hot. Gate: TPC-H
   and point-select instruction counts.
2. Finding 1's decode in the leaf.
3. Finding 4's table cache (point selects).
4. Finding 3, then finding 2, with the executor redesign.

## Done

**Step 1 (2026-11-18).**
- Finding 1's key views: `getMany`, `warm` and `lookupAhead` take
  `&[]&str`. `fetchMany` and `rangeMany` pass views of the probe keys
  instead of copies. `getMany` compares keys through `Node.keyView`.
- Finding 5, text keys: GROUP BY on one text column looks up the batch's
  own value and copies it only for a new group.
- Finding 7: a column-to-column comparison (`BNode.VCmp`) reads value
  columns in place (`bCmpCols`). A composite group key encodes a value
  column in place (`bKeyEnc`) instead of encoding a copy.

Instructions per query against main (165bd30b), each query counted once
after a warm-up: all 22 down 1.67%. The largest drops are q21 −4.97%,
q1 −3.19%, q12 −2.54% and q4 −1.43%; none went up. Point selects:
207,452 to 207,456 per statement (unchanged; nothing here is on their
path). Checksums unchanged, suite 190, quick gate PASS. Wall times were
not usable: four other processes held CPUs 12 to 15 at 100% during the
runs.

**Left out of step 1, and why:**
- Finding 6's `text()`, `bpTrim` and `Node.key`: by time they are 0.04%
  of TPC-H. A point select's 0.5% in `text()` is numbers and dates being
  formatted (text values are written from the batch already).
- Finding 7's `bxEval`: its leaf clones feed `binOp` and call arguments,
  which take values. 0.4% of TPC-H; finding 2 removes most of it.
- Finding 5's composite keys (GROUP BY and hash join): one reused buffer
  needs a `&str` view of a `StrBuf`'s bytes, or appending to a `str` in
  place. The language has neither. `s += x` copies the whole string each
  time: 100,000, 200,000 and 400,000 one-byte appends take 0.07 s, 0.31 s
  and 1.22 s, so it is quadratic (owned-str.md 2.1 says a string with
  one owner may be appended to in place).

**Step 2 (2026-11-18): finding 1, lookups decode in the leaf.**
- `Store.getManyIn` hands each run of keys found in one leaf to the
  reader inside the store's lock (`f(leaf, es, xs)`). Values not in a leaf
  (the transaction's own writes, a replica's reads) come back as values.
  `getMany` is now built on it, so there is one lookup loop, and its
  read-noting is shared in `noteLookup`.
- `access.rowsOfKeys` decodes the rows where they lie. A column leaf's
  rows go through `lexdb_rows.colsPick` (colsInto with the batch rows
  given apart), a row leaf's are decoded from views, and rows stored apart
  are read with `get`/`getPart` after the lock, as scans do. A few rows
  of a large dictionary read only their entries. `fetchMany`, the
  index-entry fetch and `rangeMany`'s primary-key fetch all use it; none
  rebuilds a row from a column leaf (`rowOf`) any more.

Instructions against step 1, per query counted once: all 22 down 8.35%.
q14 −38.9%, q8 −38.6%, q11 −30.8%, q20 −27.8%, q9 −24.9%, q17 −21.0%,
q3 −15.6%, q7 −13.0%, q19 −11.3%, q2 −9.5%, q10 −9.0%, q21 −6.5%; none
up more than 0.32% (q5). Steps 1 and 2 together: −9.9%. Point selects
207,452 to 205,463 per statement (−1.0%). Checksums unchanged, suite
190, quick gate PASS. Times (best of 2, alternating with 165bd30b, load
from other processes during part of it): 17,958 to 15,452 ms (−14%).
q17 −54%, q8 −31%, q14 −28%, q20 −30%, q9 −21%. q22 +4% and q13 +1%,
which have unchanged instructions.

**Step 3 (2026-11-18): finding 4, tables shared, not decoded per statement.**
- `lexdb_catalog.decTableCached` keeps tables decoded, by catalog key,
  with the bytes each came from. A read of the key that gives the same
  bytes gets the table as an `rc Table` handle; any store, snapshot or
  transaction is fine, because the same bytes decode to the same table.
  The catalog is still read through the store, so the read is noted as
  before and DDL still conflicts. At most 1,024 entries.
- `Level.t` is an `rc Table`, and `bindFrom` takes its table from
  `findTableRc`. Only `t AS x(a, b)` and the binder's own tables change
  a table, through `unshare()`, so a plain `FROM t` copies nothing.
  `findTable` (its 22 other callers: DDL, catalogs) still gives a
  `Table` of its own.
- Caching the decoded table and copying it out (tried first) saved only
  0.4%: the copy cost what the decode did. Sharing it is the saving.

Point selects: 205,400 to 189,100 instructions per statement (−8.0%,
two runs each, alternating), cycles −6.5%. Below the 198,000 before
the owned-str switch. TPC-H instructions unchanged (−0.03%), checksums
unchanged, suite 190, quick gate PASS.

**Finding 5's composite keys, done (2026-11-18, fea5295d)** after the
language changes AP (`s += x` appends in place) and AR (a string is its
own buffer, `clear()` keeps it). The vector aggregate (`AggSt.eat`), the
row-by-row aggregate (`groupRow`, buffer kept in `RowGroups.kb`), the hash
build (`Builder.add`) and the probe (`joinFrom`) clear one string per
operator, look up by it, and copy it only for a new group or bucket.
TPC-H instructions −0.86% (q1 −3.7%, q5 −3.6%, q10 −1.6%); all 22
results unchanged; suite 190. The row engine's keys (`lexdb_exec`: its
GROUP BY, DISTINCT aggregates, materialised hash keys) still build a
string per row; they go with the executor redesign.
