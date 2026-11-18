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

## Suggested order

1. Small and local, about a day: findings 5 and 6, the key views in
   finding 1, and finding 7's accessors where they are hot. Gate: TPC-H
   and point-select instruction counts.
2. Finding 1's decode in the leaf.
3. Finding 4's table cache (point selects).
4. Finding 3, then finding 2, with the executor redesign.
