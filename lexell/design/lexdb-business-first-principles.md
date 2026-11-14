# LexDB: a business database designed from first principles

Status: design analysis, 2026-11-14. This is a discussion document, not a
specification. It argues for a direction and names the tradeoffs; it does not
commit to an implementation order.

Scope: LexDB — a Linux-only relational database using `io_uring` for disk and
socket IO, targeting NVMe, compiled for AVX2 and above, aimed at internal
business systems rather than planet-scale workloads.

## The short version

The optimal design for this workload is not a faster Postgres. It is a
single-node primary (with a standby), memory-first, `io_uring`-driven engine
that stores immutable, checksummed extents behind manifest snapshots; uses
MVCC without vacuum; treats bulk loads, time travel, and workload isolation as
first-class; and speaks Postgres wire protocol with finance-native types and
semantics. Most databases miss this because they were designed for a different
physics — spinning disks, small RAM, one workload — and a different buyer: a
DBA with a benchmark, not a finance IT team with a month-end close.

The rest of this document explains why, and what the design should look like.

## 1. The frame: a database is a truth-maintenance system

A business database is not a query engine with storage attached. It is a
system for preserving the invariants of a business under concurrent change and
failure, and for explaining — years later — what it knew, when it knew it, who
changed it, and why.

That gives seven first-class concerns:

1. **Facts** — relations, types, semantics.
2. **Invariants** — constraints, domains, periods, approvals.
3. **Transitions** — transactions, isolation, durability.
4. **Time** — system time, valid time, snapshots, retention.
5. **Provenance** — lineage, load IDs, audit, who/what/why.
6. **Authority** — authentication, authorization, separation of duties.
7. **Presentation** — views, materialized views, reports, exports.

Most databases do the first three reasonably well, the next three partially,
and the last one poorly. That gap is the opportunity.

"Optimal" also has to be workload-specific. There is no universally optimal
database. The right design for a few hundred business users doing OLTP plus
nightly bulk loads plus month-end reporting is very different from the right
design for a global consumer app or a petabyte warehouse.

## 2. The workload envelope — and why it kills the usual assumptions

Put rough numbers on the target world, because the numbers drive the
architecture:

- **Users:** hundreds registered, a few hundred active; maybe 50–500
  concurrent connections, but most are idle or thinking. This is not a
  concurrency problem in the "millions of users" sense; it is a *mixed
  workload* problem.
- **Data:** hundreds of GB to a few TB. The hot working set is often 10–50% of
  that. A modern server with 256 GB–1 TB of RAM can hold most of what matters.
- **OLTP:** point lookups, small transactions, order entry, postings, status
  changes. Latency-sensitive; p99 in the low milliseconds or better.
- **Bulk writes:** nightly or periodic loads of millions to hundreds of
  millions of rows. Throughput-sensitive; failure must be cheap.
- **Reporting:** medium ad hoc queries plus month-end scans, joins,
  aggregations, window functions. Long-running read-only queries concurrent
  with OLTP.
- **Correctness:** exact decimal money, temporal validity, referential
  integrity, audit, reproducibility, period close.
- **Operations:** a small IT team, Active Directory, backup/restore, HA,
  upgrades, compliance. They are generalists, not database researchers.

Now the physics:

- **NVMe** random 4K reads are roughly 10–20 µs, not 5–10 ms. Random IO is
  cheap enough that index lookups remain viable. Sequential bandwidth is
  3–7 GB/s per drive. Queue depth is deep.
- **`io_uring`** lets you batch submission and completion, use registered
  buffers, polled IO, and zero-copy. It changes the cost of syscalls and
  asynchronous IO by an order of magnitude.
- **RAM** is large and cheap relative to the working set. Memory latency is
  ~100 ns; bandwidth is 10–20 GB/s per socket.
- **AVX2** gives 256-bit SIMD as a baseline. Scans, filters, hash tables,
  aggregations, decimal arithmetic, string comparisons, and bitmap operations
  can all be vectorized. AVX-512 is available on some server chips; runtime
  dispatch is worth it, but AVX2 is the safe baseline.
- **Network** is 10–25 GbE. At a few hundred users, network latency and
  protocol overhead matter more than raw bandwidth.

The implications are strong:

- **Scale up, don't shard.** A 32–64 core, 512 GB–1 TB RAM, NVMe server is
  enormous for this workload. Distributed transactions and sharding add
  complexity and latency for no business benefit. Use a standby/replica for HA
  and reporting.
- **Be memory-first.** Keep hot data in memory; use NVMe for durability, cold
  data, and spill. Don't double-buffer through the OS page cache.
- **Use asynchronous, batched IO everywhere.** Disk and sockets. One ring per
  core, coroutine-per-connection, not process-per-connection.
- **Vectorize the CPU-bound work.** Sequential scans and aggregations are
  CPU-bound, not IO-bound, on NVMe. SIMD is not a niche optimization; it is
  table stakes.
- **Design for mixed workloads.** The hard problem is not 10,000 concurrent
  users; it is a month-end report not starving order entry.
- **Make operations boring.** The database is a product, not a research
  project.

## 3. The non-negotiables

Before the interesting parts, don't lose the boring fundamentals. A relational
database still has to:

1. **Represent relations with a strong type system** — exact numerics,
   temporal types, strings, JSON, arrays, ranges, domains, enums.
2. **Enforce invariants** — `NOT NULL`, `CHECK`, `UNIQUE`, foreign keys,
   exclusion constraints, assertions, deferrable constraints.
3. **Provide atomic, isolated, durable transactions** — with well-defined
   semantics: snapshot isolation, serializable, explicit locking.
4. **Provide efficient access paths** — B-tree, hash, bitmap, columnar scans,
   zone maps, joins, aggregation, window functions.
5. **Manage schema and metadata** — online DDL, dependencies, comments,
   statistics, ownership.
6. **Secure and govern access** — authentication, roles, row-level security,
   masking, audit.
7. **Survive failure** — WAL, checkpoints, recovery, PITR, replication,
   backup verification.
8. **Be operable** — install, configure, monitor, upgrade, troubleshoot.
9. **Interoperate** — SQL standard, drivers, BI tools, CDC, import/export.

Everything else is differentiation. If you get these wrong, the clever parts
don't matter.

## 4. What most databases missed

The misses group into four themes: the write path, time and truth, the
workload mix, and the human layer.

### 4.1 The write path

**Bulk load is treated as many small transactions.** This is the biggest miss.
Most engines make you `INSERT` or `COPY` row by row: WAL record per row, MVCC
version per row, index update per row, rollback cost proportional to load
size. A 100-million-row nightly load becomes 100 million tiny transactions
wearing a trench coat.

The right abstraction is a *physical* bulk operation:

- Parse and validate in parallel.
- Sort by the clustering key.
- Write immutable columnar extents.
- Compute zone maps, statistics, and control totals.
- Validate constraints with set-based operations — sort/hash for uniqueness,
  anti-join for foreign keys, vectorized filters for checks.
- Publish atomically via a manifest swap.

Rollback is discarding files. Load time improves by an order of magnitude,
failure is cheap, and you can support "load, validate, quarantine bad rows,
publish" as a first-class workflow. This is the single most valuable thing a
business database can do.

**The write path is designed around pages and double writes.** Most engines
write the WAL, then write the page, then write full-page images to avoid torn
pages, and double-buffer through the OS page cache. On NVMe, that is wasteful.
The better design is append-only, checksummed, immutable extents; group commit
for durability; and physiological redo at extent granularity for bulk
operations, with row-level redo only for the small delta. No full-page writes,
no double buffering, no random 8 KB page writes.

**Schema evolution is treated as a rare event.** Business schemas change
constantly: new columns, new codes, new dimensions, new regulations. Most
databases lock or rewrite tables. Versioned row formats, metadata-only
changes, lazy backfill, and online index builds make schema change a
non-event.

### 4.2 Time and truth

**History is garbage, not an asset.** Postgres-style MVCC plus vacuum treats
old versions as bloat. But business systems need audit, time travel, period
close, and "what did the ledger look like at close?" A report holding a
snapshot can block vacuum for hours. That is backwards.

If data files are immutable extents and a snapshot is a manifest reference,
history becomes cheap. Long-running reports don't block anything. GC respects
retention policy, not active queries. Time travel and audit fall out of the
storage design instead of being bolted on.

**Temporal semantics are pushed into the application.** SQL:2011 has
system-versioned and application-time period tables, but most databases
implement subsets or nothing. So business systems rebuild temporal logic with
triggers and app code, badly. A business-native database should make
bitemporal tables — system time and valid time — first-class, with efficient
`AS OF` queries and `FOR PORTION OF` updates.

**Provenance and audit are log files, not data.** "Where did this number come
from?" is a daily question in finance. Most databases can tell you the current
row, not the source file, load ID, transaction, user, or reason. Every row
should carry provenance; every change should be auditable; audit writes should
survive a rollback. That last point needs autonomous transactions, which most
databases don't have.

### 4.3 The workload mix

**OLTP and OLAP are separate systems, so business data is copied and stale.**
The batch/online split is an artifact of engine limitations, not business
reality. You should be able to run a consistent report on live data without
ETL and without slowing order entry.

The tractable version of HTAP is not "make every table columnar" or "make
every query run on both engines." It is the **fact/dimension split**:

- **Facts** — transactions, postings, movements, orders — are large,
  append-only, and queried by date/entity/account with aggregations. Columnar,
  compressed, clustered, zone-mapped.
- **Dimensions** — customers, accounts, products, org units — are smaller,
  update-heavy, and queried by key. Row-oriented, B-tree/hash indexed.
- **Updates to facts** are corrections; model them as new versions or
  tombstones, not in-place updates.

That is a business-shaped hybrid, not a generic one.

**Workload governance is an enterprise add-on.** A month-end report can starve
order entry. Most databases have crude priorities or none. Business systems
need workload classes — interactive, batch, reporting, maintenance — with
SLOs, admission control, memory/IO/CPU limits, and a "month-end mode" that
protects interactive latency while using idle capacity for batch.

**Plan stability and reproducibility are afterthoughts.** Finance hates "the
report was fast yesterday and slow today" and "the numbers changed because the
plan changed." Optimizers flip plans on statistics changes. You need plan
pinning, plan history, "explain why it changed," deterministic semantics, and
query budgets. Peak speed matters less than predictable latency and
reproducible results.

**The optimizer doesn't know the workload.** It knows table statistics, not
that a query is interactive versus batch, that a table is hot in memory, that
a materialized view exists, or that a plan was pinned. A workload-aware
optimizer can choose better access paths and stay stable. Incremental view
maintenance and result caching for repetitive reports are also huge misses.

### 4.4 The human layer

**The last mile is ignored.** Importing messy CSV/Excel, validating,
reconciling, exporting, cloning for test, scheduling batch jobs — this is the
daily reality of business IT. Databases leave it to ETL tools and scripts. A
database that does bulk load with error tables, control totals, instant clone,
and scheduled jobs is dramatically more useful.

**Operations is treated as someone else's problem.** Postgres has hundreds of
knobs, vacuum tuning, bloat monitoring, extension management, and fragile
failover. Internal business IT has generalists. A business database should be
an appliance: single binary, auto-tuning, automatic maintenance, health
checks, backup verification, one-click clone/restore/failover, Active
Directory integration, clear diagnostics.

**Cloning is a copy problem.** Test, dev, and audit need a copy of production.
Most databases make you restore a backup or `pg_dump`. Copy-on-write/reflink
plus manifest snapshots give instant clones at negligible cost. This is a
killer feature for business IT.

**CDC and integration are afterthoughts.** Business systems feed warehouses,
reporting, and downstream apps. Postgres logical replication slots are fragile
and can bloat; triggers are slow. A first-class change stream with transaction
boundaries, schema evolution, and exactly-once delivery is a differentiator.

**The database doesn't understand the business.** It doesn't know about
periods, ledgers, control totals, reconciliation, hierarchies, currency, or
approvals. These are left to the application. A domain-aware layer — types,
constraints, table kinds, functions — could make invalid business states
unrepresentable.

Here is the summary:

| What most databases assume | What a business system actually needs | Design consequence |
|---|---|---|
| Bulk load is many `INSERT`s | 10M–500M row nightly loads | Physical stage/validate/publish |
| Old versions are bloat | Audit, time travel, period close | Immutable extents, manifest snapshots, no vacuum |
| OLTP and OLAP are separate | Reports on live data | Row delta + columnar extents, one snapshot |
| One workload class | Interactive + batch + reporting | Workload governance, SLOs, admission control |
| A DBA tunes it | Generalist IT runs it | Appliance defaults, auto-maintenance, diagnostics |
| Proprietary protocol | Existing drivers/BI tools | Postgres wire + catalog compatibility |
| Schema changes are rare | Constant change | Versioned rows, online DDL, lazy backfill |
| History is a log file | "Where did this number come from?" | Provenance columns, autonomous audit, lineage |

## 5. The design I would bet on

Here is the coherent architecture, not a menu.

### 5.1 Storage: the log is the database; data files are materialized views

```
            SQL
             │
      planner / optimizer
             │
     vectorized executor
        ┌────┴────┐
        │         │
   row delta   columnar extents
   (hot, MVCC) (cold, immutable,
   B-tree/hash  compressed, zone maps)
        └────┬────┘
             │
     manifest (snapshot)
             │
      WAL (durability,
      replication, CDC)
```

- **WAL** is the source of truth for recent changes: append-only, checksummed,
  group-committed, written with `io_uring` and `O_DIRECT`. Replication and CDC
  are derived from it.
- **Delta** is an in-memory row store for recent inserts and updates, with
  MVCC version chains and B-tree/hash indexes for point access. It spills to
  disk when large.
- **Extents** are immutable, self-describing, checksummed blocks — columnar or
  row — of 64–256 MB. They contain data, zone maps, bloom filters, and
  statistics. They are sorted by the clustering key.
- **Manifest** is a versioned list of which extents and delta segments make up
  a table at a point in time. A snapshot is a manifest reference plus a WAL
  LSN. Publishing a bulk load is an atomic manifest swap.
- **Compaction** merges delta into extents in the background, rewrites extents
  when updates/deletes exceed a threshold, preserves clustering, and is
  throttled and crash-safe.
- **GC** drops extents and manifests that are no longer needed by retention
  policy or active snapshots. There is no row-level vacuum in the Postgres
  sense.
- **Time travel** is a manifest lookup. Clone is a manifest plus copy-on-write
  extents. Retention policy, legal hold, and tiering to cheaper storage are
  metadata on extents.

This design directly solves several problems at once: no vacuum bloat, cheap
long-running snapshots, atomic bulk publish, fast recovery, simple
replication, and native audit/time travel.

**Layout is adaptive, not universal.** Facts are columnar, append-optimized,
clustered by `(date, entity)`, compressed, zone-mapped. Dimensions are
row-oriented, update-heavy, B-tree/hash indexed. A table can start
row-oriented and become hybrid as it grows. You can expose `CREATE FACT TABLE`
and `CREATE DIMENSION TABLE` with sensible defaults, and let the engine
auto-tune later.

### 5.2 Transactions: snapshot isolation by default, serializable on demand

- **Snapshot isolation** is the default: readers don't block writers, writers
  don't block readers, and long reports get a stable view.
- **Serializable** is available via SSI for critical transactions. Write skew
  is real in finance; don't pretend it isn't.
- **Explicit locking** — `SELECT ... FOR UPDATE`, `SKIP LOCKED`, advisory
  locks — for business logic and job queues.
- **Bulk transactions** are physical: stage extents, validate, publish.
  Rollback is discarding files. No row-level undo. This is what makes nightly
  loads fast and failure cheap.
- **Autonomous transactions** for audit: log failed attempts, rejections, and
  security events even when the business transaction rolls back.
- **Group commit** with configurable `synchronous_commit` levels: off, local,
  remote, quorum. Critical transactions can wait for a standby; bulk loads can
  batch.
- **Savepoints**, statement-level atomicity, deferrable constraints, `SET
  CONSTRAINTS`.
- **Deadlock detection**, lock timeouts, and wait-for graphs that are actually
  understandable.

The key insight is that **long-running read snapshots must be cheap**. If a
snapshot is a manifest reference, a report can run for an hour without
preventing GC or bloating the database. That is a direct consequence of
immutable extents.

### 5.3 Execution: vectorized, adaptive, parallel

- **Push-based, vectorized execution** with batches of 1–8K tuples. Keep data
  in registers and cache; avoid the row-at-a-time Volcano overhead.
- **AVX2 kernels** for filters, projections, hash tables, aggregations, sorts,
  joins, window functions, decimal arithmetic, string comparisons, and
  bitmaps. Runtime dispatch for AVX-512 where available.
- **Morsel-driven parallelism** with work stealing. Separate worker pools for
  interactive and batch; batch uses idle capacity but yields to interactive.
- **Adaptive execution**: runtime filters, bloom joins, join-order switching,
  parallelism adjustment. Statistics are never good enough for skewed
  business data.
- **Spill to NVMe** with compression; per-query memory accounting; no OOM
  killer surprises.
- **`io_uring` for scans and prefetch**, asynchronous and direct, with
  registered buffers.
- **Many connections, few active**: coroutine-per-connection with `io_uring`
  for sockets. Don't pay a process or thread per idle connection like Postgres
  does.

### 5.4 Optimizer: cost-based, constraint-aware, workload-aware, stable

- **Multi-column statistics**, histograms, sketches, and sampling that handles
  skew. Business data is full of "one big customer" and end-of-month spikes.
- **Partition and zone-map pruning** before you touch data. Date-range and
  entity filters should eliminate most extents.
- **Join optimization** for star/snowflake shapes: broadcast small dimensions,
  hash-partition large facts, runtime filters.
- **Constraint-aware optimization**: foreign keys can enable join elimination;
  `NOT NULL` and `CHECK` constraints can simplify expressions; unique
  constraints can remove `DISTINCT`; temporal constraints can prune periods.
  Business schemas are rich in semantics; exploit them.
- **Materialized view matching and incremental maintenance** for repetitive
  reports. This is a huge practical win in finance.
- **Result caching keyed by snapshot**: if the data hasn't changed, reuse the
  result. With manifests, invalidation is tractable.
- **Plan pinning, plan history, and plan diff**: "the plan changed because
  statistics on `postings` changed" is a feature, not a mystery.
- **Query budgets**: time, memory, IO. Spill, degrade, or fail gracefully.

### 5.5 Semantics: business-native

- **Exact decimal** as a native type: 128-bit scaled integers, explicit scale,
  rounding modes. Never use floating point for money.
- **Bitemporal tables**: system time and valid time, `AS OF`, `FOR PORTION OF`,
  retention and legal hold.
- **Period close**: native period metadata and constraints. `CLOSE PERIOD
  '2026-10'`; postings to closed periods are rejected unless authorized;
  reopening is audited.
- **Control totals**: `LOAD ... CONTROL_TOTALS (rows, sum, hash)`; compare
  before publish; fail atomically. This is finance-native and almost nobody
  does it.
- **Provenance columns**: load ID, source, timestamp, transaction ID, user.
  Cheap in columnar storage, invaluable in audit.
- **`MERGE`**, `RETURNING`, `COPY ... ON ERROR`, quarantine tables, `VALIDATE
  CONSTRAINT`.
- **JSONB, arrays, ranges, enums, domains, UUID/ULID**, full-text and trigram
  indexes.
- **Fact/dimension table kinds** with defaults for layout, indexes, statistics,
  and SCD Type 2 dimensions.

The optional next step is a **ledger layer**: append-only double-entry tables,
corrections as reversing entries, balances as incrementally maintained
materialized views, and period close enforced at the storage layer. That makes
invalid financial states unrepresentable, which is a different kind of
guarantee than "fast SQL."

### 5.6 Workload governance: SLOs, not knobs

- **Workload classes** with CPU, memory, and IO reservations/limits,
  priorities, and admission control.
- **Interactive reserved capacity**; batch uses idle cycles; "month-end mode"
  protects latency while draining the backlog.
- **Per-query budgets** and progress/cancel.
- **Read replicas** for reports when needed, with bounded staleness and
  snapshot reads.
- **Observability**: wait events, query fingerprints, per-query CPU/IO/memory,
  lock graphs, plan history, sampling profiler.

This is a product feature, not an ops detail. Business users feel it directly.

### 5.7 Operations: appliance, not toolkit

- **Single binary**, systemd, few knobs, auto-tuning for memory, parallelism,
  compaction, and statistics.
- **Backup**: base + WAL archive, incremental, PITR, verification, restore to
  a sandbox.
- **HA**: three-node Raft for leadership, WAL shipping, synchronous commit,
  fencing, automatic failover, read replicas. No multi-master.
- **Clone**: copy-on-write/reflink plus manifest; instant; for dev, test, and
  audit.
- **Upgrade**: online minor, rolling major, rollback.
- **Security**: TLS, SCRAM, Active Directory/LDAP/Kerberos/OIDC, roles,
  row-level security, column masking, TDE, KMS, audit export.
- **Diagnostics**: `EXPLAIN (ANALYZE, BUFFERS, CPU, WAL)`, health checks,
  alerts, `lexdb doctor`.

### 5.8 Interop: meet the ecosystem where it is

- **Postgres wire protocol v3** — startup, SCRAM, extended query, `COPY`,
  notifications — plus `pg_catalog` and `information_schema` compatibility
  views. This gives you JDBC, ODBC, ORMs, BI tools, and DBeaver on day one.
  Test with real tools, not just your own client.
- **SQL surface**: standard plus a pragmatic Postgres subset, plus `MERGE`,
  temporal syntax, and the features business systems actually use. Don't
  invent a new dialect.
- **CDC**: a logical change stream with transaction boundaries, schema
  evolution, exactly-once delivery, a Debezium connector, and an outbox
  pattern.
- **Arrow/Parquet** import/export and foreign tables over files.
- **CLI**: psql-like, plus `load`, `backup`, `restore`, `clone`, `bench`,
  `doctor`.
- **Stored procedures**: PL/pgSQL subset plus WASM UDFs, triggers, and a
  debugger. Finance puts a lot of logic in the database; meet that reality.
- **Active Directory/LDAP** integration is table stakes for internal business
  systems.

### 5.9 The optional business layer

Once the core is solid, the differentiators that make LexDB *LexDB* rather
than "Postgres with a columnar extension":

- Ledger tables with double-entry invariants.
- Fact/dimension types with automatic layout and indexing.
- Period close and control totals.
- Data quality rules, quarantine, reconciliation.
- A scheduler and transactional job queue with dependencies and retries.
- Lineage and "where did this number come from?" queries.

This is where the database starts to encode business semantics instead of
leaving them to every application.

## 6. The hard tradeoffs — and what I would not build

The design above is coherent, but it is not free. Be honest about the
complexity budget.

- **Hybrid storage + MVCC + optimizer + HA is a lot.** Ship a credible OLTP
  core first; add immutable extents, columnar facts, and time travel in
  phases. Don't build the business layer before the storage engine is correct.
- **Postgres compatibility is a tar pit.** Aim for driver/tool compatibility
  and a documented SQL subset, not bug-for-bug semantics. Don't implement
  every extension.
- **Columnar updates are hard.** Don't promise HTAP for update-heavy tables.
  Use row stores for dimensions, columnar for facts, and a delta for recent
  updates. Be honest about the boundary.
- **HA is hard.** Keep it simple: scale up, replicate for HA and reads, use
  consensus only for leadership. No sharding, no distributed transactions, no
  multi-master.
- **Stored procedures and a scheduler expand scope.** They matter in finance,
  but they can come after the engine. Start with SQL functions and WASM UDFs.
- **Security certifications take time.** Start with Active Directory, TLS,
  RLS, and audit. Certifications later.

What I would explicitly **not** build first:

- Sharding or distributed transactions. At this scale, they are complexity
  without benefit.
- Multi-master or active-active. Conflict resolution is a nightmare for
  business data.
- A general-purpose HTAP engine for every table. Be opinionated: facts
  columnar, dimensions row.
- Full Postgres compatibility. Driver/tool compatibility is the goal.
- A JIT/LLVM compiler. Vectorized interpretation plus specialized kernels is
  enough; JIT adds complexity and security risk.
- GPU acceleration. NVMe plus AVX2 is enough for this workload.
- Multi-model (graph, document, vector) in the core. Extensions later, if
  ever.
- Your own network protocol. Use Postgres wire.
- A GUI IDE, BI platform, or ETL tool. Integrate with the ecosystem.
- A Kubernetes operator first. Business systems often run on VMs or bare
  metal.
- Blockchain. Hash-chained audit is enough.
- Serverless or cloud-native first. Focus on the single-node appliance.
- TPCC as the primary benchmark. Optimize for business SLOs.

## 7. How I would phase it

**Phase 0 — correctness infrastructure.** This is non-negotiable and comes
before features: deterministic simulation, crash testing (`kill -9` at random
points), SQLancer for logic bugs, Jepsen for isolation, differential testing
against Postgres for supported SQL, fuzzing the parser/storage/protocol, and
property-based tests. A database without this is a liability.

**Phase 1 — credible OLTP core.** WAL, MVCC snapshot isolation, row store,
B-tree/hash indexes, vectorized executor, SQL subset, Postgres wire, `COPY`,
backup/PITR, basic observability, auth/TLS. Target: replace Postgres for small
business applications.

**Phase 2 — the differentiators.** Immutable extents plus manifest snapshots,
columnar facts plus row dimensions, bulk load/publish with control totals,
time travel and instant clone, `MERGE`, workload governance, plan pinning,
incremental materialized views. Target: month-end batch and reporting on live
data without ETL.

**Phase 3 — operations and ecosystem.** HA, Active Directory, RLS/audit/TDE,
CDC, scheduler, stored procedures, BI tool certification, Arrow/Parquet,
upgrade tooling. Target: production-ready for internal business systems.

**Phase 4 — the business layer.** Ledger tables, period close, reconciliation,
data quality, lineage UI, fact/dimension types, hierarchy/rollup, currency
conversion. Target: the database business systems should have had.

Define SLOs early and benchmark against them, not against TPCC: order entry
p99 < 5 ms; 100M-row load < 30 minutes; month-end report < 5 minutes; failover
< 30 seconds; recovery < 5 minutes; clone < 10 seconds.

## 8. The five bets

If I were placing bets on what makes LexDB matter, these are the five:

1. **Bulk load as atomic publish with control totals.** The nightly load goes
   from hours to minutes, and failure is free. This alone justifies the
   product for finance.
2. **History as an asset; no vacuum.** Time travel, audit, period close, and
   long reports without bloat. This is a storage-architecture advantage, not a
   feature.
3. **Fact/dimension hybrid plus workload governance.** Fresh reports on live
   data without starving order entry. This is the practical answer to HTAP.
4. **Appliance operations plus instant clone.** A generalist can run it; test,
   dev, and audit get real data instantly. This is how you win internal
   business IT.
5. **Postgres wire plus business semantics.** Existing drivers and BI tools
   work; decimal, temporal, `MERGE`, RLS, and audit are native. This is how you
   get adopted and how you differentiate.

The optimal design is not a faster Postgres. It is a database that takes the
business model seriously: facts are append-only, time is real, batches are
physical, reports are snapshots, and operations are someone's day job.

If LexDB nails that, it won't compete with Postgres on TPCC. It will compete
with the entire stack business systems currently need.

## 9. Open questions

These are the decisions that need an owner before the design becomes a plan:

1. **What is the compatibility target?** Driver/tool compatibility with
   Postgres is the minimum. Which SQL features and catalog views are required
   by the first cohort of applications and BI tools?
2. **Row-only first, or hybrid from day one?** The differentiators depend on
   immutable extents and columnar facts. Is there a credible phase where the
   engine is row-only, or does that create a storage format that has to be
   replaced?
3. **What is the HA model?** Three-node Raft for leadership plus WAL shipping
   is the simple option. Is a two-node plus witness acceptable for the first
   release?
4. **What is the retention and time-travel policy?** Default retention,
   legal-hold semantics, tiering to cheaper storage, and the cost model for
   long history.
5. **Which workloads define the SLOs?** Order entry, GL posting, nightly load,
   month-end close, and ad hoc reporting have different latency/throughput
   targets. The benchmark suite should be built from these, not from TPCC.
6. **Is the business/ledger layer in scope?** Ledger tables, period close, and
   control totals are strong differentiators, but they are also a product
   decision about how domain-specific LexDB should be.
7. **What is the operational packaging?** Bare metal/VM first, or container
   first? How much of the "appliance" promise is in the database versus a
   separate management tool?

## Related documents

- [lexdb.md](lexdb.md) — the current design and implementation notes.
- [lexdb-gaps.md](lexdb-gaps.md) — where LexDB stands against PostgreSQL today.
- [lexdb-engines.md](lexdb-engines.md) — measured comparisons with PostgreSQL
  and SQLite.
- [lexdb-columns-study.md](lexdb-columns-study.md) — columnar layout study.
- [concurrency.md](concurrency.md) — concurrency and isolation design.
- [pgwire.md](pgwire.md) — Postgres wire protocol.
- [simd.md](simd.md) — SIMD kernels.
