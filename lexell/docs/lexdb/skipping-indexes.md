# Data skipping indexes

Data skipping indexes let lexdb skip large chunks of a table during analytical scans without reading or scanning rows
that cannot possibly match your `WHERE` clause.

Unlike a traditional B+tree index — which stores an entry for every single row and must be updated on every write — a
data skipping index stores a tiny **summary per block of rows** (and rolls those summaries up the table's B+tree so
entire subtrees can be skipped in one check). That gives you three practical advantages:

- **Tiny footprint:** kilobytes instead of gigabytes, even on wide analytical tables.
- **Zero OLTP write slowdown:** `INSERT`, `UPDATE`, and `DELETE` never synchronously rebuild Bloom filters or summaries.
- **Accelerates queries B+trees cannot:** including leading-wildcard `LIKE '%google%'` substring searches and unsorted
  high-cardinality filters across wide tables.

Data skipping works identically across the PostgreSQL, Oracle (TNS), and SQL Server (TDS) doors, respects MVCC snapshot
isolation, and persists across restarts.

## What you already get for free (automatic zone maps)

You do **not** need to create an index for basic numeric or date/time range filtering. Whenever lexdb checkpoints rows
into its columnar format, every integer, date, time, and timestamp column automatically tracks its minimum and maximum
values per block and rolls them up the B+tree.

With zero configuration, lexdb automatically skips non-matching subtrees and blocks for:

- Range and equality filters (`=`, `<`, `<=`, `>`, `>=`, `BETWEEN`) — e.g. `WHERE created_at >= '2026-11-01'` or
  `WHERE amount > 50000`
- Not-equal filters (`<>` / `!=`) when a whole block contains only the excluded value
- Membership lists (`IN (...)`) and `OR` chains of equalities
- Top-N queries (`ORDER BY score DESC LIMIT 10`) — as lexdb finds high values, it raises a live threshold and skips any
  remaining blocks whose maximum cannot make the top 10

## When to use a skipping index vs a regular B+tree index

| Situation | Use a regular B+tree `CREATE INDEX` | Use a skipping index |
|---|---|---|
| OLTP point lookups expecting sub-millisecond reads of 1–10 rows (`WHERE email = '...'`) | **Yes** — jumps straight to exact rows | No — skips blocks, still scans matching blocks |
| Enforcing `UNIQUE` constraints or avoiding sorts (`ORDER BY`) | **Yes** | No |
| Wide append-mostly / analytical tables where you filter on many different columns | Expensive (large indexes, slower writes) | **Yes** — tiny, zero write amplification |
| Substring or keyword search (`WHERE url LIKE '%google%'`) | Cannot use a normal B+tree | **Yes** (`ngrambf` or `tokenbf`) |
| Filtering by an unsorted ID or rare value in a 10M-row log table (`WHERE user_id = 42`) | Good if queried constantly; heavy otherwise | **Yes** (`bloom_filter`) |

## Quick guide: which skipping index should I pick?

| What your query looks like | Recommended index |
|---|---|
| `WHERE created_at BETWEEN ...` or `WHERE amount > 1000` (numeric/date) | **None needed** (automatic zone maps already handle it; add `minmax` if you also want cold-start disk skipping) |
| `WHERE code BETWEEN 'US-001' AND 'US-099'` (clustered/ordered **text**) | **`minmax`** (alias `brin`) |
| `WHERE status = 'failed'` or `WHERE country IN ('JP', 'KR')` (**few distinct values** per block, unsorted) | **`set`** |
| `WHERE user_id = 435090932899640449` or `WHERE trace_id = '...'` (**many distinct values**, exact `=` / `IN`) | **`bloom_filter`** (alias `bloom`) |
| `WHERE url LIKE '%google%'` or `WHERE title LIKE '%error%'` (**any substring** match in text) | **`ngrambf`** |
| `WHERE log_msg LIKE '% timeout %'` or `WHERE url LIKE '%/checkout/%'` (**delimiter-bounded whole-word / token** match in long text) | **`tokenbf`** |

## The five index types explained

### 1. `minmax` (alias `brin`) — ranges on clustered data

**What it stores:** Only the smallest and largest value in each block (and the combined min/max of each parent subtree).

**When it helps:**
- **Text columns with natural ordering or clustering**, such as ISO timestamp strings (`'2026-11-26T...'`), sequential
  invoice/order numbers (`'INV-000142'`), or data loaded grouped by region or tenant. Automatic zone maps cover numbers
  and dates, so `minmax` brings the same range and Top-N pruning to `text` / `varchar` / `nvarchar` columns.
- **Cold-restart disk pruning** on numeric/date columns: running `CREATE SKIPPING INDEX ... USING minmax` (and
  `ANALYZE`) persists summaries in a companion index so lexdb can skip non-matching pages without even reading them
  from disk after a restart.

**When it does not help:** Randomly shuffled values (like random UUIDs or hashed IDs). If every block contains values
spanning from `'000...'` to `'fff...'`, the min/max range covers everything and nothing can be skipped.

```sql
CREATE SKIPPING INDEX ix_logs_iso_ts ON app_logs (iso_timestamp) USING minmax;
-- Helps: WHERE iso_timestamp >= '2026-11-20' AND iso_timestamp < '2026-11-21'
-- Helps: ORDER BY iso_timestamp DESC LIMIT 50
```

### 2. `set` — low-cardinality columns (even when unsorted)

**What it stores:** The exact set of distinct values present in each block, up to `max_rows` (default `32`). If a block
has more than `max_rows` distinct values, that block is marked saturated and skipped checks conservatively fall back
to scanning it.

**When it helps:**
- **Status codes, event types, tenants, countries, device types, or categories** where each block only contains a
  handful of distinct values — especially when those values are **not** sorted or clustered cleanly enough for `minmax`.
  For example, if a block contains only `{'AU', 'GB', 'US'}`, `minmax` sees the range `'AU'..'US'` and cannot skip
  `WHERE country = 'JP'`, whereas `set` knows `'JP'` is absent and skips the entire block.
- Supports `=`, `<>`, `<`, `<=`, `>`, `>=`, `BETWEEN`, `IN (...)`, and case-sensitive `LIKE` (checking each distinct
  value in the set against the pattern).

**When it does not help:** High-cardinality columns (`user_id`, `url`, `email`) where every block has hundreds of
distinct values. Those blocks will immediately exceed `max_rows` and saturate.

```sql
CREATE SKIPPING INDEX ix_events_status ON events (status) USING set WITH (max_rows = 64);
-- Helps: WHERE status = 'refunded'
-- Helps: WHERE status IN ('failed', 'timeout')
```

### 3. `bloom_filter` (alias `bloom`) — needle-in-a-haystack equality lookups

**What it stores:** A fixed-size Bloom filter bitset per block (and bitwise-OR'd into parent subtrees). A Bloom filter
can guarantee "this value is **definitely not** in this block" (zero false negatives) with only a small chance of a
false positive (reading a block that didn't match).

**When it helps:**
- **Selective `=` or `IN (...)` lookups on high-cardinality, unsorted columns** — such as `user_id`, `session_id`,
  `customer_id`, `order_uuid`, `trace_id`, or `ip_address` in large event/clickstream tables.
- Whenever a single user or trace only appears in a small fraction of blocks across a large table, `bloom_filter` lets
  lexdb skip all the other blocks without paying the disk, memory, or insert cost of a full secondary B+tree index.

**When it does not help:**
- Range queries (`>`, `BETWEEN`) or substring `LIKE '%foo%'` — Bloom filters only test exact equality.
- Very common values that appear on almost every block (e.g., `WHERE is_bot = 0` or a power-user present in every
  block).

```sql
CREATE INDEX hits_uid_bf ON hits USING bloom_filter (userid);
-- Helps: WHERE userid = 435090932899640449
-- Helps: WHERE userid IN (101, 202, 303)
```

### 4. `ngrambf` (alias `ngrambf_v1`) — substring search (`LIKE '%...%'`)

**What it stores:** A Bloom filter containing every `n`-character sliding substring (default `n = 3`, trigrams) of the
text values in the block. For example, `'google'` inserts `'goo'`, `'oog'`, `'ogl'`, and `'gle'`. When you query
`WHERE url LIKE '%google%'`, lexdb checks whether all four trigrams exist in the block's Bloom filter; if any one is
missing, the block is skipped.

**When it helps:**
- **Arbitrary substring matching** (`LIKE '%google%'`, `LIKE '%err_503%'`, `LIKE '%@acme.com'`) in URLs, page titles,
  emails, user agents, or short identifiers — queries where a standard B+tree index cannot help at all because of the
  leading `%`.
- Works for exact `=`, `IN (...)`, and any `LIKE` pattern that has at least one literal segment of length `>= n`.
- Automatically handles SQL Server's case-insensitive `NVARCHAR` columns (`COLL_CI`) by folding ASCII case so pruning
  matches T-SQL's case-insensitive `LIKE` semantics.

**When it does not help:**
- Patterns whose literal pieces are shorter than `n` (e.g., `LIKE '%ok%'` cannot be pruned by a 3-gram index; use
  `n = 2` if you frequently search 2-character substrings, at the cost of faster filter saturation).
- Very common substrings that appear in nearly every block (e.g. `LIKE '%https://%'`).
- Very long prose/log bodies where a single block generates thousands of distinct trigrams and fills up the filter —
  for long multi-word text, prefer `tokenbf` below.

```sql
CREATE SKIPPING INDEX hits_url_ng ON hits (url) USING ngrambf(3, 2048, 3);
-- Helps: WHERE url LIKE '%google%'
-- Helps: WHERE url LIKE '%/checkout/%'
```

### 5. `tokenbf` (alias `tokenbf_v1`) — whole-word / keyword search in long text

**What it stores:** A Bloom filter of **whole alphanumeric tokens** split on non-alphanumeric separators (spaces,
punctuation, slashes, hyphens). For example, `'https://news.example.com/checkout/error-503'` indexes the tokens
`'https'`, `'news'`, `'example'`, `'com'`, `'checkout'`, `'error'`, and `'503'`.

**When it helps:**
- **Whole-word or keyword filtering on verbose text columns** such as application logs, stack traces, descriptions,
  search queries, or long URLs.
- Because a block of long text has far fewer distinct whole words than 3-character n-grams, `tokenbf` stays sparse and
  keeps skipping blocks even on columns where `ngrambf` would saturate.

**When it does not help:**
- **Unbounded or mid-word substring matches:** `WHERE msg LIKE '%timeout%'` (with `%` directly touching the word) will
  *not* prune blocks with `tokenbf` because `%` could match part of a longer word like `'mytimeout'`. Include
  non-alphanumeric separators around the token — such as `LIKE '% timeout %'`, `LIKE '%/checkout/%'`, or
  `LIKE '%.google.%'` — or use `ngrambf` when you need arbitrary `%substring%` matching.

```sql
CREATE SKIPPING INDEX ix_logs_msg_tok ON app_logs (message) USING tokenbf(2048, 3);
-- Helps: WHERE message LIKE '% timeout %'
-- Helps: WHERE message LIKE '%/checkout/%'
-- Helps: WHERE message LIKE '%.google.%'
```

## Measured impact

On the ClickBench 1M benchmark ([LexDB performance report](performance.md#clickbench-1m-rows)), adding three skipping
indexes on the 105-column `hits` table (`bloom_filter` on `UserID`, `ngrambf(3, 2048, 3)` on `URL` and `Title`)
accelerates selective point and substring-`LIKE` queries with exact output parity and zero OLTP write regression:

| Query | Filter pattern | Skipping index used | Baseline | With skipping index | Speedup |
|---|---|---|---:|---:|---:|
| `q19` | `WHERE UserID = 435090932899640449` | `bloom_filter(UserID)` | 173.2 ms | **42.6 ms** | **4.07×** |
| `q21` | `WHERE URL LIKE '%google%'` | `ngrambf(URL)` | 339.9 ms | **167.7 ms** | **2.03×** |
| `q23` | `WHERE Title LIKE '%Google%'` | `ngrambf(Title)` | 331.7 ms | **168.7 ms** | **1.97×** |
| `q22` | `WHERE Title LIKE '%Google%' AND URL NOT LIKE '%.google.%'` | `ngrambf(Title)` | 620.1 ms | **485.4 ms** | **1.28×** |

On the same table with all three skipping indexes present, 1,000 OLTP inserts ran in 303.9 ms vs 304.6 ms without them,
and 1,000 primary-key lookups ran in 44.4 ms vs 45.1 ms.

## Syntax across doors

All three doors accept both `CREATE INDEX ... USING <method>` and `CREATE SKIPPING INDEX ... USING <method>`, as well
as `DROP [SKIPPING] INDEX`:

- **PostgreSQL** ([CREATE INDEX](sql/postgresql/create-index.md), [DROP INDEX](sql/postgresql/drop-index.md)):
  ```sql
  CREATE INDEX hits_uid_bf ON hits USING bloom_filter (userid);
  CREATE SKIPPING INDEX hits_url_ng ON hits (url) USING ngrambf(3, 2048, 3);
  CREATE SKIPPING INDEX hits_status_set ON hits (status) USING set WITH (max_rows = 64);
  DROP SKIPPING INDEX IF EXISTS hits_url_ng;
  ```
- **Oracle (TNS)** ([CREATE INDEX](sql/oracle/create-index.md), [DROP INDEX](sql/oracle/drop-index.md)):
  ```sql
  CREATE SKIPPING INDEX ix_events_uid_bf ON events (user_id) USING bloom_filter;
  CREATE SKIPPING INDEX ix_events_url_ng ON events (url) USING ngrambf(3, 2048, 3);
  DROP SKIPPING INDEX ix_events_url_ng;
  ```
- **SQL Server (TDS)** ([CREATE INDEX](sql/tsql/create-index.md), [DROP INDEX](sql/tsql/drop-index.md)):
  ```sql
  CREATE SKIPPING INDEX ix_events_url_ng ON dbo.events (url) USING ngrambf(3, 2048, 3);
  DROP SKIPPING INDEX IF EXISTS ix_events_url_ng ON dbo.events;
  ```

Constraints:

- Skipping indexes index a single plain column (no expressions, multi-column keys, or `UNIQUE`).
- `ngrambf` and `tokenbf` require a text column (`0A000` otherwise).

## Parameter reference

| Method (aliases) | Positional parameters & defaults | `WITH (...)` options | Valid bounds | Supported types | Predicates pruned |
|---|---|---|---|---|---|
| `minmax` (`brin`) | none | none | — | integer, date, time, timestamp, `text`/`varchar`/`nvarchar` | `=`, `<>`, `<`, `<=`, `>`, `>=`, `BETWEEN`, `IN`, dynamic Top-N |
| `set` | `(max_rows)` — default `32` | `max_rows` | `1..4096` | integer, date, time, timestamp, `text`/`varchar`/`nvarchar` | `=`, `<>`, `<`, `<=`, `>`, `>=`, `BETWEEN`, `IN`, `LIKE` (case-sensitive text) |
| `bloom_filter` (`bloom`) | `(bits_per_key, size_bytes, hashes)` — default `(10, 2048, 3)` | `bits_per_key`, `size` / `size_bytes`, `hashes` | `size`: `64..65536`, `hashes`: `1..8` | integer, date, time, timestamp, `text`/`varchar`/`nvarchar` | `=`, `IN`, `OR` of equalities |
| `ngrambf` (`ngrambf_v1`) | `(n, size_bytes, hashes)` — default `(3, 2048, 3)` | `n` / `ngram`, `size` / `size_bytes`, `hashes` | `n`: `2..8`, `size`: `128..65536`, `hashes`: `1..8` | `text`/`varchar`/`nvarchar` | `=`, `IN`, `LIKE` (any literal piece of length `>= n`; case-insensitive on `COLL_CI`) |
| `tokenbf` (`tokenbf_v1`) | `(size_bytes, hashes)` — default `(2048, 3)` | `size` / `size_bytes`, `hashes` | `size`: `128..65536`, `hashes`: `1..8` | `text`/`varchar`/`nvarchar` | `=`, `IN`, `LIKE` (complete alphanumeric tokens; case-insensitive on `COLL_CI`) |

**Tuning tip:** If a Bloom, n-gram, or token filter on a wide/verbose column is saturating (skipping few blocks),
increase `size_bytes` (for example from `2048` to `8192` or `16384`). For `set`, raise `max_rows` if a low-cardinality
column has slightly more than 32 distinct values per block (for example `max_rows = 128` for country codes).

## How writes, MVCC, and restarts work

- **Hierarchical rollup and saturation:** Leaf summaries roll up into parent B+tree nodes (union of min/max bounds,
  union of `set` values up to `max_rows`, bitwise OR of Bloom/n-gram/token bitsets). If a parent node saturates, lexdb
  never skips at that parent — guaranteeing zero false negatives — while still pruning child subtrees beneath it.
- **Zero OLTP write amplification:** `INSERT`, `UPDATE`, and `DELETE` never update Bloom filters or summaries inline.
  Mutating a block simply bumps an integer version counter up its ancestor path ($O(\text{tree height})$). Stale
  summaries are ignored immediately and refreshed lazily on the next scan or eagerly on `ANALYZE`.
- **MVCC safety:** Each B+tree node tracks the commit sequence of the last mutation in its subtree, so `REPEATABLE READ`
  and `SERIALIZABLE` snapshots only consult summaries that are guaranteed consistent with the reader's snapshot.
- **Persistence and lifecycle:** `CREATE [SKIPPING] INDEX` and `ANALYZE` persist per-page summaries in a companion
  B+tree so cold restarts prune disk pages before reading them. `TRUNCATE TABLE` clears summaries, `DROP TABLE` drops
  companion trees, and `CREATE`/`DROP` skipping indexes are fully transactional (`ROLLBACK` restores previous state).
