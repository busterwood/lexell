# COPY's serial fast path: text straight into the stored row

Status: prototype, 2026-11-14, `exp/copy-fast`. It implements the serial
path recommended by [par-db-perf.md](par-db-perf.md) 6: PostgreSQL's COPY is
single-threaded, so the first goal is a serial load at its level, not a
parallel one.

## What it replaces

The generic COPY calls `copyRecord` (text to `Val`), `insertOne` (defaults,
checks, `coerce`), `encRowOf`/`encFixed` (a second walk to the stored form),
and `putRow` (a per-key own-writes map entry). The fast path parses each
field once, from its text span into its place in the fixed stored row. There
is no `Val` row and no `encFixed` walk.

`copyStmt` tries `fastCopyPlan` before the generic reader. A `None` plan, a
non-empty table, or a transaction block leaves the generic path unchanged.

## When it applies

- The COPY names every column, in table order.
- Text format, default delimiter (`\t`) and NULL (`\N`); no CSV, header,
  FORCE options, `batch_rows`, or INSERT BULK.
- One integer primary key, or none (the hidden ROWID); no dropped columns,
  unique, filtered or expression indexes, checks, foreign keys, defaults,
  identities, sequences, or collations. Plain secondary indexes are built
  (below).
- Scalar columns only: int2/int4/int8, bool, numeric, float4/float8, date,
  time, timestamp, timestamptz, text/varchar, uuid. No bytea, char(n),
  enum, array, interval, or other tagged forms.
- The table starts empty (checked with `countRange`), and the COPY is its
  own statement (`!txn.inBlock()`), so no later statement can read the load
  through the transaction's own-writes map.

Otherwise the generic path runs.

## How a row is made

`FastCopyPlan` copies the table's current `kinds` and computes each place's
fixed offset and the fixed part's length `v0`. The row is the fixed form
`encFixed` writes: `FIXED`, the layout number, the null bitmap, the fixed
values or variable ends, then the variable bytes.

- `fastCopyRow` scans tabs directly, not through `strings.split` (no per-row
  field array).
- `fastCopyOne` handles NULL, text-format escapes (through
  `lexdb_sql.unescape`), and the plain field.
- `fastCopyField` writes the typed value at its place: integers, bool,
  float bits, date/time/timestamp microseconds, numeric `toBin`, text bytes,
  uuid bytes.
- The key is the integer PK in `encKeyPart`'s byte order, built directly.
- `putRowLoad` appends the write without `noteWrite`'s map entry.
- Ascending keys use `putRowLoad`. An out-of-order key calls
  `Txn.indexWrites()` (the earlier rows enter the map), then checks
  `st.get` and uses the ordinary `putRow`; duplicates are still 23505.

## Results

Same machine and 1M-row wide file as par-db-perf.md, fresh table per run,
`-O` native, server CPU from `/proc/<pid>/stat`, wall from the client:

| load | wall | server CPU | peak RSS |
|---|---:|---:|---:|
| generic COPY | 3.13 s | 3.00 s | 621 MB |
| serial fast path | 1.50–1.57 s | 1.39–1.45 s | 582 MB |
| PostgreSQL 18, one thread (9.118 data) | 1.42 s | | |

All 1M rows of the fast load were compared with a generic load of the same
file, column by column, and are byte-identical. The COPY tests
(`exec_copy`, `exec_copystream`, `wire_copy`) pass.

The fast profile's remaining large shares are the store's page encoding
(`lexdb_cols.encodeOne`/`encDict`, ~14%), the row builder and field dispatch
(~15%), UUID parse plus `uuidBytes` (~7%), decimal (~6%), timestamp/date
fast paths (~4%), and the commit's `logWrites` scan (~2%). The B-tree insert
and log are now a large part of the load, as expected once parsing is cheap.

## Why no par.map yet

The serial path already reaches PostgreSQL's wall time, and it does not need
the kernel purity rules (float bit moves, a pure timestamp path) or the
worker-result handoff. `par.map` remains a later multiplier for very large
loads or for loads on machines where the store can overlap with the next
chunk's parse. It is not the first fix for COPY.

## Next steps

1. Parse date/time/timestamp and numeric directly for the plain ISO and
   decimal forms, as the par_copy kernel does.
2. Parse a canonical uuid once to its 16 bytes (the earlier attempt was
   inconclusive under load; retry with the lookup tables).
3. Fold `logWrites`' two passes, and note the inserted rows in bulk rather
   than one `noteChg` call per row.
4. Then consider `par.map` over chunks, if the serial path is not enough.

## Tables without a primary key (2026-11-23)

A table without a primary key (lexdb.md 9.88) is keyed by its hidden ROWID, the last column,
numbered by its identity sequence; the fast path refused it (`len(targets) != len(t.cols)`,
the ROWID's sequence), so its loads took the generic path, a Val row and `insertOne` a row:
2.98 s for the 1M wide rows against PostgreSQL's 1.52. Now `fastCopyPlan` takes it when the
ROWID is the last column (`rid`, and `nIn` fields a record): `fastCopyRun` draws its keys from
the sequence a run at a time, as `insertOne` does (`nextRun`, the run doubled up to
ROWID_RUN), and `fastCopyRow` writes each into the row and loads it under that key, ascending.
A record's shape errors (extra or missing data, 22P04) now give its text as the generic path
does (`COPY t, line 3: "..."`), for keyed tables too.

| 1M wide rows, `\copy`, median of 3 | before | now | PostgreSQL 18 |
|---|---:|---:|---:|
| no primary key | 2.98 s | 1.50 s | 1.52 s |
| a primary key | 1.44 s | 1.45 s | 1.81 s |
| a primary key and two secondary indexes (the generic path) | 6.31 s | 5.82 s | 4.74 s |

(PostgreSQL's from the same day's refresh, `saved/results/2026-11-23-refresh`.) The indexed
load is a little faster because `commitOrder` compares two writes' keys once (`str.cmp`), not
twice; it still takes the generic path, whose profile is half the commit (sorting the 3M writes:
`commitOrder` 25%) and 41% `insertOne`. A fast path that also builds the index entries is what
is left. Test: `tests/lexdb/run/exec_copy_fast_nokey`.

## Tables with secondary indexes (2026-11-23)

The fast path refused a table with any index, so the indexed load took the generic path: a
`Val` row and `insertOne` a row, and an own-writes map entry per index entry, then a commit that
sorted the 3M writes (`commitOrder` 25% of the load). Now `fastCopyPlan` takes plain indexes
(columns only: not unique, not filtered, no expressions), as `FastCopyPlan.ixs`:

- `fastCopyEntries` makes each row's entries from the fixed row it built (`fixedVal` of each
  part, `encIdxPart`, then the row's key: `insertRow`'s form) and keeps them per index. An entry
  too large for the store is the row's error (`lexdb_store.keyFits`: 54000, as the generic path).
- `fastCopyIndexes`, after the last row, sorts each index's entries and writes them in key order
  (`lexdb_access.loadEntry`: no own-writes entry unless an out-of-order key made the load keep
  them). The commit finds each tree's writes in order and does not sort them.
- The sort, `lexdb_access.sortKeysMoved`, is a radix sort (`lexdb_vec.radixPerm`) of the 8 bytes
  after the prefix every entry shares (the part's tag, and often a text's first letters: `cust`),
  then each run of one such word by the whole key. With a comparison sort (`sortBy`) the sorting
  was a quarter of the load (0.85 of 3.40 s); sorting and writing the entries is now 11% (0.3 s).

A unique index stays with the generic path: its clash must be the error of its row, before any
later row's. A text of `lexdb_rows.LONG` bytes or more does not fit the fixed row; the fast path
used to fail the load with 0A000 for it (any table, indexed or not). Now such a row's values are
kept aside (`FastLong`) and the row is stored in the tagged form (`encRow`, with its `rowHead`),
as the generic path stores it.

| 1M wide rows, `\copy`, median of 3 | before | now | PostgreSQL 18 |
|---|---:|---:|---:|
| a primary key and two secondary indexes (`cust` text, `ts` timestamptz) | 5.81 s | 2.71 s | 4.88 s |
| a primary key | 1.45 s | 1.46 s | 1.81 s |

(PostgreSQL's indexed load in the same session: runs 5.45, 4.88, 4.55 s; 4.74 in the day's
refresh. Its unindexed one from the refresh.)

The load's profile now: parsing the fields 38%, the commit's B-tree writes 36%, the index
entries made and sorted 16%. Test: `tests/lexdb/run/exec_copy_fast_index` (the same rows
loaded through the generic path, a table with a check, answer the indexes' queries alike, before
and after rows change; errors; long texts; a table without a primary key).

## Reproduction

```sh
# the compiler and lexdb
lexell/compiler/build.sh
cd lexell
LXL_LIB=$PWD/lib compiler/out/lxlc cmd/lexdb.lxl -O -o /tmp/lexdb-copy-fast

# the wide file (the 9.118 generator, or any file of its 12 columns)
python3 saved/results/2026-11-13-copy/gen.py wide 1000000 /tmp/w1m.tsv

# load it into a fresh table, with psql's \copy
/tmp/lexdb-copy-fast /tmp/lexdata 127.0.0.1:55600 &
psql -h 127.0.0.1 -p 55600 -U lexdb lexdb \
  -c 'create table t (id bigint primary key, a int, b bigint,
       amt numeric(12,2), f float8, cust text, note text, d date,
       ts timestamptz, flag boolean, u uuid, sku varchar(20))'
psql -h 127.0.0.1 -p 55600 -U lexdb lexdb -c "\copy t from '/tmp/w1m.tsv'"
```
