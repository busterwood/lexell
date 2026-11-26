# Data skipping indexes

lexdb prunes non-matching B+tree leaves and entire internal subtrees during analytical scans using two complementary
mechanisms: **automatic zero-config zone maps** on columnar leaves, and **explicit hierarchical data skipping indexes**
(`minmax`/`brin`, `set`, `bloom_filter`, `ngrambf`, `tokenbf`).

Both mechanisms work identically across the PostgreSQL, Oracle (TNS), and SQL Server (TDS) doors, incur zero extra
index maintenance on OLTP writes, respect MVCC snapshot isolation, and persist summaries across restarts.

## Automatic zone maps

When a checkpoint packs a table leaf into lexdb's columnar format (`T_CLEAF`), each numeric, date, time, and timestamp
column carries an inline min/max header. lexdb automatically rolls those headers up post-order into ancestor internal
nodes in the B+tree, pruning entire subtrees and individual leaves with zero configuration for:

- Range and equality filters: `=`, `<`, `<=`, `>`, `>=`, `BETWEEN`
- Not-equal filters: `<>` / `!=` (prunes nodes whose min equals max equals the excluded value)
- Membership lists: `IN (...)` and `OR` chains of equalities
- Dynamic Top-N pruning: `ORDER BY col ASC|DESC LIMIT k` (tightens a live bound as the top `k` rows are found and skips
  subtrees whose min/max cannot beat the bound)

## Explicit skipping index methods

Create an explicit skipping index when you need pruning on text columns, high-cardinality point lookups (`UserID`),
low-cardinality value sets, or substring/token `LIKE` filters (`URL LIKE '%google%'`):

| Method (aliases) | Parameters & defaults | `WITH (...)` options | Valid bounds | Supported types | Predicates pruned |
|---|---|---|---|---|---|
| `minmax` (`brin`) | none | none | — | integer, date, time, timestamp, `text`/`varchar`/`nvarchar` | `=`, `<>`, `<`, `<=`, `>`, `>=`, `BETWEEN`, `IN`, dynamic Top-N |
| `set` | `(max_rows)` — default `32` | `max_rows` | `1..4096` | integer, date, time, timestamp, `text`/`varchar`/`nvarchar` | `=`, `<>`, `<`, `<=`, `>`, `>=`, `BETWEEN`, `IN`, `LIKE` (case-sensitive text) |
| `bloom_filter` (`bloom`) | `(bits_per_key, size_bytes, hashes)` — default `(10, 2048, 3)` | `bits_per_key`, `size` / `size_bytes`, `hashes` | `size`: `64..65536`, `hashes`: `1..8` | integer, date, time, timestamp, `text`/`varchar`/`nvarchar` | `=`, `IN`, `OR` of equalities |
| `ngrambf` (`ngrambf_v1`) | `(n, size_bytes, hashes)` — default `(3, 2048, 3)` | `n` / `ngram`, `size` / `size_bytes`, `hashes` | `n`: `2..8`, `size`: `128..65536`, `hashes`: `1..8` | `text`/`varchar`/`nvarchar` | `=`, `IN`, `LIKE` (any literal piece of length `>= n`; case-insensitive on `COLL_CI` columns such as T-SQL `NVARCHAR`) |
| `tokenbf` (`tokenbf_v1`) | `(size_bytes, hashes)` — default `(2048, 3)` | `size` / `size_bytes`, `hashes` | `size`: `128..65536`, `hashes`: `1..8` | `text`/`varchar`/`nvarchar` | `=`, `IN`, `LIKE` (complete alphanumeric tokens in literal pieces; case-insensitive on `COLL_CI` columns) |

### Saturation and hierarchical rollup

- Leaf summaries roll up into parent internal B+tree nodes (union of min/max bounds, union of `set` values up to
  `max_rows`, bitwise OR of Bloom/n-gram/token bitsets).
- If a node's `set` exceeds `max_rows` or a Bloom/n-gram/token filter fills past its density threshold, that node is
  marked saturated and never skips (zero false negatives; child subtrees below a saturated parent can still skip).

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
- Case-insensitive `NVARCHAR` columns under SQL Server (`COLL_CI`) automatically fold ASCII case when building and
  querying `ngrambf` and `tokenbf` summaries so `LIKE` pruning matches T-SQL semantics.

## Write path, MVCC, and persistence

- **Zero OLTP write amplification:** `INSERT`, `UPDATE`, and `DELETE` never update Bloom filters or min/max summaries
  synchronously. Instead, mutating a leaf bumps an integer `subVer` counter up its ancestor path (`O(tree height)`).
  Stale cached summaries are ignored immediately (zero false negatives) and refreshed lazily on the next scan or eagerly
  on `ANALYZE`.
- **MVCC safety:** Each B+tree node tracks `subSeq` (the commit sequence of the last mutation in its subtree). Under
  `REPEATABLE READ` / `SERIALIZABLE` snapshots, a node summary is only consulted when `subSeq <= snapSeq` and the
  node's version visible to the snapshot matches the cached summary.
- **Persistence across restarts:** `CREATE [SKIPPING] INDEX` and `ANALYZE` persist per-page `IdxSum` records in a
  companion B+tree keyed by disk page number. After a cold restart, clean disk pages are pruned before reading the
  table page from disk.
- **Lifecycle:** `TRUNCATE TABLE` invalidates and clears skipping summaries; `DROP TABLE` drops all companion skipping
  index trees; `CREATE`/`DROP` skipping indexes participate in transactions (`ROLLBACK` restores previous state).
