# lexdb against PostgreSQL and SQLite: where lexdb loses, and why

Status: research, 2026-11-12, for the user's decision. Nothing is changed by
it. The detail, with source locations, is in two notes written from the
engines' source:
[lexdb-engines-postgres.md](lexdb-engines-postgres.md) (PostgreSQL 18) and
[lexdb-engines-sqlite.md](lexdb-engines-sqlite.md) (SQLite 3.55). This page
puts them against lexdb's measurements and profiles.

## 1. Measured

The same data in all three: w (1M rows), d (1,000), t (1M), cr (20), as in
lexdb.md 9.102. lexdb at 25a7b4e2 (9.103). Server CPU in ms, median of
three:
- **PostgreSQL 18.6:** `max_parallel_workers_per_gather = 0`; its
  parallel wall time is in the last column.
- **SQLite 3.54:** process CPU of `sqlite3` with the output to /dev/null,
  less a `select 1`. In SQLite, `id` is an INTEGER PRIMARY KEY (the rowid)
  and `price` holds floats (NUMERIC affinity).

The plans are from EXPLAIN ANALYZE and EXPLAIN QUERY PLAN on these tables.

| query | lexdb | PostgreSQL (its plan) | SQLite (its plan) | PG parallel, wall |
|---|---|---|---|---|
| `select id, b from w order by b` | 4,095 | 400: index scan on w_b, **no sort** | 152: covering index w_b, **no sort** | 450 |
| `... order by c desc limit 10` | 401 | 90: top-N heapsort | 42: a 10-row B-tree | 43 |
| join, then `order by d.label, w.id` (103k rows) | 550 | 100 | 1,166 | 62 |
| `select distinct city from w` | 333 | 100: HashAggregate | 62: a temporary B-tree | 45 |
| `select * from w` | 490 | 250 | 523 | 527 |
| `select id, a + b, price * 2, upper(city) from w` | 1,600 | 310 | 407 | 426 |
| `where a = 5` (1%) | 71 | 40 | 36 | 27 |
| `where note like '%item 77%'` | 136 | 80 | 59 | 41 |
| `select city, count(*), avg(price) ... group by city` | 192 | 130 | 247: sorts | 56 |
| hash join on a text key (cr), count | 113 | 80 | 80: Bloom filter, automatic index | 41 |
| `w join t on t.id = w.b` (1M × 1M), count | 582 | 80: **merge join of two index-only scans** | 29: covering index w_b, then the rowid in order | 37 |
| `where b > 90000` (100k rows) | 170 | 40: bitmap heap scan | 149: index, then each row | 48 |
| `where a in (select k from d where grp = 3)` | 468 | 50: **hash join** (pulled up) | 49: a temporary index and a Bloom filter | 30 |
| `where exists (select 1 from d where d.k = w.a ...)` | 602 | 50: **hash join** (pulled up) | 44: semi-join, Bloom filter | 30 |
| `row_number() over (partition by a order by c)` | 967 | 130: sort (spilled to disk), WindowAgg | 180 | 148 |

From the agents' earlier report (lexdb.md 9.100's series), the DML, wall
ms, lexdb against PostgreSQL:
- INSERT ... SELECT of 103k rows: 692 against 144;
- UPDATE of 10k rows: 255 against 64;
- DELETE of 10k rows from a table with an index: 4,390 against 50;
- DELETE of 100k rows, no index: 547 against 75.

**Most of the largest gaps are plans, not execution.** In five of the
cases neither engine does the work lexdb does:
- the 1M-row sort and the 1M × 1M join use an index's order;
- IN and EXISTS become joins;
- the index range reads the table's pages in order.

## 2. Where lexdb's time goes (profiles, 25a7b4e2)

- **Sort** (4.1 s): `ordCmp` and `sortCmp` 53%, `sortBy` 7%. Each
  comparison walks the ORDER BY keys and compares two values by their kinds.
- **Top-N, DISTINCT:**
  - `batchLevel`'s direct emit, about 31%, makes a row of values per
    scanned row.
  - `execSel`'s closure then evaluates the outputs by name per row
    (`colIndex`, `eval`, 5 to 10%).
- **Window:** `rt_str_eq` 14.5% (a column found by its name per row), a
  general sort, and values pushed one by one.
- **IN (subquery):** the row path whole: `tryRow` 14%, `decFixed` 13%,
  `allTrueX`, `eval`. An IN is not a condition the batches compile.
- **The 1M lookups:** the store's descent per key, about 40%: `memcmp`,
  `rt_str_cmp`, `Node.lower`, `childIndex`, the snapshot's descent.
- **Text hash join and GROUP BY:** SipHash (`hash_sipKeyedStr`) 6 to 8%,
  the gather of values (reference counts) and the text decode.

## 3. What the other two do, by theme

**A. Plans that avoid the work.**
- **An index's order instead of a sort.** PostgreSQL reads `w_b` in order
  for `order by b`: 320 ms for a million rows, each fetched by its
  address. SQLite reads the index alone, since it covers `(b, id)`.
  - lexdb uses an index's order only for ORDER BY with a LIMIT
    (optimizer 32). Its sort is so dear (about 2.4 µs a row) that the
    index would win here too.
- **Index-only scans.**
  - PostgreSQL: `Index Only Scan ... Heap Fetches: 0`, through the
    visibility map.
  - SQLite: a covering index. Both read only the index for the 1M × 1M
    join's outer side, and get the keys in order for free.
  - lexdb's index entries hold the indexed columns and the primary key, so
    an index-only scan is possible. The executor always fetches the row.
- **Merge join** (PostgreSQL): two ordered inputs, no hashing and no
  descents.
  - SQLite gets the same effect another way. Its lookups arrive in key
    order, and `sqlite3BtreeTableMoveto` checks the current and next
    entries before descending.
  - lexdb has neither: no merge join, and no reuse of a descent.
- **IN and EXISTS become joins.**
  - PostgreSQL: `convert_ANY_sublink_to_join`,
    `convert_EXISTS_sublink_to_join` (a semi-join, here a hash join).
  - SQLite: `existsToJoin`, plus an ephemeral index and a Bloom filter for
    IN.
  - lexdb runs IN through a hashed set on the row path, and a correlated
    EXISTS per row (memoised). Neither reaches 9.102's batched joins.
- **A bitmap scan** (PostgreSQL) for 100k index entries: the rows' places
  are collected, then the pages are read in order, once each.
  - lexdb fetches each entry's row by its primary key: one descent each,
    in the index's order.
  - Sorting the batch's keys first would read the table in key order.

**B. Typed work, bound once.**
- **Sort:**
  - PostgreSQL's `SortTuple` holds the first key inline (24 bytes a row).
  - `btint4sortsupport` gives a plain C comparator, and
    `tuplesort_sort_memtuples` picks a qsort specialised for it with the
    comparator inlined. It also checks first whether the input is already
    sorted.
  - Top-N is a bounded heap: a row the heap's root beats costs one
    comparison.
  - SQLite sorts serialized records in one buffer, with comparators chosen
    by the first key's type. Top-N keeps an N-row B-tree, and the other
    columns are loaded only for rows that get in.
- **Expressions:**
  - PostgreSQL compiles them to step arrays with computed-goto dispatch.
    Each function is bound once at plan time and constant arguments are
    evaluated once.
  - SQLite compiles them to register opcodes.
  - Neither looks a column up by name at run time. lexdb's row path does
    (`colIndex`, `rt_str_eq` in the profiles), and its batches compile
    integer and boolean expressions only.
- **Hashing:**
  - PostgreSQL stores each entry's 32-bit hash and compares it before the
    key.
  - It hashes text with lookup3 and a murmur finaliser, not SipHash.
  - Its hash join's rows sit in 32 kB chunks.
  - SQLite's Bloom filter hashes the length and the first and last 8
    bytes.

**C. Decoding: lazy and in place.**
- **PostgreSQL:**
  - `slot_getsomeattrs` decodes a row only to the last column needed, with
    cached offsets.
  - The qual's step decodes up to its own column first, so a rejected row
    of `a = 5` is decoded to column 2 only.
  - Texts and numerics are pointers into the page.
- **SQLite:** `OP_Column` parses a row's header lazily, caching types and
  offsets per cursor, with no allocation per value.
- **Numeric** is binary in both: PostgreSQL's base-10000 digits, SQLite's
  floats. So is lexdb's in the fixed layout (`Decimal.toBin`, 9.50): a
  price in w is 6 bytes. Only the older tagged layout keeps a numeric's
  text. An earlier version of this page said lexdb stores the text; the
  page-layout study corrected it. Decoding is still costly:
  `Decimal.fromBin` makes a value per row.
- **lexdb's batches** decode every column a level uses before the first
  condition runs. Each text becomes a reference-counted value.

**D. Data changes.**
- **PostgreSQL's DELETE never touches an index.** `heap_delete` sets xmax;
  dead index entries go later (VACUUM, index scans marking them,
  bottom-up deletion). INSERT ... SELECT is row by row, as lexdb's. HOT
  updates skip the indexes when no indexed column changes.
- **SQLite's DELETE is lexdb's design:** each index entry deleted at once,
  with a descent. So lexdb's 4.4 s for 10k rows (2 to 12 s across runs) is
  not explained by its design. It is a store problem to profile (the
  agents' earlier profile: 72% in the store).

**E. Parallelism** (PostgreSQL only): 2 workers and the leader by default
for SELECT, never for DML. It is why PostgreSQL's wall times for scans,
aggregates and joins are about half its CPU. lexdb's single SQL thread is
a design choice (lexdb.md section 0); this is left out of the plan below.

## 4. What lexdb could do, in a proposed order

The effects are estimates, from the profiles and the other engines'
numbers. None has been built.

1. **IN and EXISTS as semi-joins.** A planner rewrite that puts the
   subquery in FROM as a semi-join level: at most one match per row, no
   columns. 9.102's batched hash join runs it, with an "any match" probe.
   - Expected: 468 and 602 ms to about 50 to 60 (the hash join's 53).
   - Small to medium.
2. **The sort:**
   - extract ORDER BY's keys once per row into typed arrays (an int key
     into `[]int`);
   - sort a permutation with a comparator specialised by key types (or a
     radix sort for int keys: 6 ms for 1M in the agents' microbenchmark);
   - check whether the input is already sorted;
   - a batched top-N with a bounded heap that rejects a row by one
     comparison before making its row.

   DISTINCT through `batchGroups`' hash, as GROUP BY of the outputs. Window
   functions take the new sort, with their columns found once.
   - Expected: the 1M-row sort 4,095 to about 300 to 500. Top-N 401 to
     about 50. DISTINCT 333 to about 60. The window query 967 to about
     200.
   - Medium.
3. **Index-only scans, and keys in order.**
   - **Index-only scans:** where an index holds every column a level uses,
     read the index alone. Visibility is no issue: lexdb's index entries
     are versioned with the store.
   - **Order:** the outer keys then arrive in order. Batched lookups
     (9.103) can then reuse their last leaf (SQLite's check before a
     descent), or a merge join can step through both.
   - **ORDER BY over a whole index:** cost it against the real sort.
   - **An index range:** sort a batch's primary keys and fetch them in
     order (a bitmap scan's effect).
   - Expected: the 1M × 1M join 582 to about 50 to 100. The index range
     170 to about 60.
   - Medium to large: the planner and the store's cursor.
4. **Lazy decoding for filters.** Decode the columns of the batch's first
   condition, choose, then decode the rest for the rows kept.
   - Expected: `where a = 5` 71 to about 40; LIKE 136 to about 90.
   - Small to medium.
5. **Expressions of other types in the batches** (text, numeric, function
   calls bound once at plan time; a per-value adapter at worst), and the
   row path's columns found by place, not by name.
   - Expected: `a + b, price * 2, upper(city)` 1,600 to about 400.
   - Medium.
6. **DELETE with an index:** profile the 2 to 12 s.
7. **The page layout** ([lexdb-pages.md](lexdb-pages.md), measured):
   - column leaves for table trees (PAX, with light encodings): scan-bound
     queries 13 to 42% faster end to end, w 45% smaller;
   - front-coded index leaves without their duplicated value: w_b from
     42 MB to about 14;
   - no page compression.
8. **Hash tables:** keep each entry's hash, and compare it before the key.
   A cheaper hash than SipHash needs care: a client's values reach these
   maps, so hash flooding matters. SipHash's keyed design is there for
   that. A cheaper keyed hash, or a fallback on long chains, would be
   needed.
   - Expected: 5 to 8% of hash joins and GROUP BY.

Not proposed:
- **Parallel query** (E).
- **JIT:** PostgreSQL's JIT is on by default (`jit_above_cost` 100,000),
  and some of these queries cost more than that. Whether it ran in the
  timings above was not checked (EXPLAIN ANALYZE shows a JIT section when
  it does).

## 5. Results (2026-11-13)

Items 1 to 6 of section 4 were built by agents, reviewed, and merged:
- semi-joins: lexdb.md 9.104;
- the sort, top-N, DISTINCT and windows: 9.105;
- indexes in batches: 9.107;
- expressions and two-step decoding: 9.108;
- data changes and front-coded leaves: 9.109.

The column-page study is lexdb-pages.md and a second one in progress.

Server CPU ms, median of three, the same data and harness as section 1.
- **start:** c66474b0 (before 9.101).
- **mid:** 25a7b4e2 (9.103, when this page was written).
- **now:** fd437e6b.

The machine had other work on it (load 2 to 3): an A/B of `select *` gave 510 to 531 for mid and 514 to 518 for now, so differences of about 5% are noise.

| query | start | mid | now | PG 1 core | SQLite |
|---|---:|---:|---:|---:|---:|
| `order by b` (1M rows) | 4,110 | 4,095 | **82** | 400 | 161 |
| `order by c desc limit 10` | 390 | 401 | **49** | 90 | 40 |
| join, then sorted (103k) | 919 | 550 | **93** | 110 | 1,157 |
| `distinct city` | 350 | 333 | **105** | 100 | 74 |
| `select *` | 783 | 490 | **531** | 270 | 538 |
| `a + b, price * 2, upper(city)` | 1,580 | 1,600 | **454** | 310 | 424 |
| `where a = 5` | 70 | 71 | **50** | 40 | 36 |
| `note like '%item 77%'` | 140 | 136 | **67** | 80 | 62 |
| `group by city, avg(price)` | 240 | 192 | **195** | 130 | 250 |
| hash join, text key, count | 788 | 113 | **119** | 90 | 81 |
| `w join t` (1M × 1M) | 1,584 | 582 | **106** | 80 | 30 |
| index range, 100k rows | 170 | 170 | **77** | 40 | 144 |
| `in (subquery)` | 470 | 468 | **39** | 50 | 50 |
| `exists (...)` | 590 | 602 | **49** | 50 | 43 |
| `row_number() over (...)` | 940 | 967 | **247** | 130 | 184 |
| `select id, b, name` | 364 | | **135** | 130 | 226 |
| `where a < 10` | 103 | | **60** | 60 | 54 |
| `id, a + b, c % 1000` | 550 | | **124** | 140 | 213 |
| `count(*)` | 20 | | **20** | 30 | 3 |
| `group by a` | 50 | | **51** | 100 | 167 |
| index range, aggregate | 160 | | **52** | 30 | 110 |
| key range, 100k rows | 38 | | **17** | 20 | 25 |
| 20k point lookups | 560 | | **586** | 460 | |
| hash join, rows (103k) | 584 | | **53** | 50 | |
| hash join, text key, rows | 630 | | **121** | 80 | |
| LEFT JOIN, rows (200k) | 304 | | **36** | 40 | |

**Where lexdb is still behind PostgreSQL on one core:**
- `select *`: 2 times;
- windows: 1.9 times;
- `expr_mix`: 1.5 times;
- GROUP BY a text with avg(numeric): 1.5 times;
- a text-keyed hash join: 1.3 to 1.5 times;
- the index range: 1.9 times, or 1.7 with an aggregate;
- point lookups: 1.3 times.

Everything else is level or ahead. PostgreSQL in parallel is still about twice as fast in wall time on scans and aggregates (section 3E).

**Row format.** The page studies' column leaves address the first of these (decoding whole rows); see lexdb-pages.md and its sequel.

**Data changes** (9.109, wall ms): DELETE of 10k rows with an index fell from 2 to 12 s to 0.16 to 0.37 (PostgreSQL 0.05). INSERT … SELECT of 103k rows fell from 738 to 486 (PostgreSQL 202). UPDATE is unchanged (257 against 66); its scan decodes whole rows.
