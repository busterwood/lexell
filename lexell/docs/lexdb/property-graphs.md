# Property graphs in LexDB (SQL/PGQ)

LexDB implements **SQL:2023 Property Graph Queries (SQL/PGQ)** directly over your existing relational tables across all three doors (PostgreSQL, SQL Server, and Oracle) — with **zero data duplication**, **zero ETL pipelines**, and **full ACID / MVCC transactional consistency**.

Instead of copying your operational tables into a separate graph database and dealing with sync lag, you declare a property graph view over your tables once and query multi-hop traversals, cyclic patterns, and shortest paths right alongside regular SQL joins, aggregations, CTEs, and transactions.

---

## Defining a property graph

A property graph maps existing relational tables to **vertex tables** and **edge tables**. No data is copied when you create the graph — queries read directly from your live B+trees:

```sql
CREATE TABLE people (
    id INT PRIMARY KEY,
    name TEXT,
    country TEXT,
    city TEXT
);

CREATE TABLE companies (
    id INT PRIMARY KEY,
    name TEXT,
    industry TEXT
);

CREATE TABLE knows (
    src INT NOT NULL REFERENCES people(id),
    dst INT NOT NULL REFERENCES people(id),
    since INT NOT NULL,
    weight INT NOT NULL,
    PRIMARY KEY (src, dst)
);
CREATE INDEX knows_dst_src ON knows (dst, src);

CREATE TABLE works_at (
    pid INT NOT NULL REFERENCES people(id),
    cid INT NOT NULL REFERENCES companies(id),
    PRIMARY KEY (pid, cid)
);

CREATE PROPERTY GRAPH social
    VERTEX TABLES (
        people KEY (id) LABEL person PROPERTIES (id, name, country, city),
        companies KEY (id) LABEL company PROPERTIES (id, name, industry)
    )
    EDGE TABLES (
        knows
            SOURCE KEY (src) REFERENCES people (id)
            DESTINATION KEY (dst) REFERENCES people (id)
            LABEL knows PROPERTIES (src, dst, since, weight),
        works_at
            SOURCE KEY (pid) REFERENCES people (id)
            DESTINATION KEY (cid) REFERENCES companies (id)
            LABEL works_at PROPERTIES (pid, cid)
    );
```

---

## Querying with `GRAPH_TABLE` and `ANY SHORTEST`

Use `GRAPH_TABLE` anywhere a table or subquery is allowed in `FROM` — then join, filter, group, or order its results with standard SQL.

### Multi-hop traversals and pattern matching

Find distinct people reachable in 1 to 3 hops, or count triangles across the entire graph:

```sql
-- 1..3-hop neighborhood
SELECT count(DISTINCT dst)
FROM GRAPH_TABLE (social
    MATCH (a IS person WHERE a.id = 42)-[k IS knows]->{1,3}(b IS person)
    WHERE b.id <> 42
    COLUMNS (b.id AS dst)
);

-- Directed triangles
SELECT count(*)
FROM GRAPH_TABLE (social
    MATCH (a IS person)->(b IS person)->(c IS person)->(a)
    WHERE a.id < b.id AND b.id < c.id
    COLUMNS (a.id AS aid)
);
```

### Shortest paths with SQL:2023 `ANY SHORTEST`

Traditional SQL requires slow `WITH RECURSIVE` CTEs to compute shortest paths. LexDB supports SQL:2023 **`ANY SHORTEST`** (and `ANY SHORTEST PATH`) with both bounded (`{m,n}`, `{n}`, `{,n}`, `?`) and unbounded (`+`, `*`, `{m,}`) quantifiers, `path_length(p)`, `count(e.key)`, directed (`->`), reverse (`<-`), and undirected (`-`) traversals, edge `WHERE` filters, and vertex property projections:

```sql
-- Point-to-point shortest path (unbounded + or bounded {1,6})
SELECT hops
FROM GRAPH_TABLE (social
    MATCH p = ANY SHORTEST (a IS person WHERE a.id = 42)-[k IS knows]->+(b IS person WHERE b.id = 98955)
    COLUMNS (path_length(p) AS hops)
);

-- Single-source shortest paths to an entire target cohort
SELECT count(*), sum(hops)
FROM GRAPH_TABLE (social
    MATCH p = ANY SHORTEST (a IS person WHERE a.id = 42)-[k IS knows]->+(b IS person WHERE b.city = 'city_JP_3')
    COLUMNS (path_length(p) AS hops)
);

-- Shortest path with edge filter and vertex properties joined back
SELECT dst, name, hops
FROM GRAPH_TABLE (social
    MATCH p = ANY SHORTEST (a IS person WHERE a.id = 42)
          -[k IS knows WHERE k.since >= 2022]->+(b IS person WHERE b.country = 'UK')
    COLUMNS (b.id AS dst, b.name AS name, path_length(p) AS hops)
)
ORDER BY hops, dst
LIMIT 20;
```

---

## How LexDB executes property graphs fast

Naive SQL/PGQ implementations rewrite every graph pattern into verbose multi-table joins or recursive CTEs, leaving 10×–1,000× performance on the table. LexDB combines five graph-aware optimizations inside its relational engine:

1. **FK-verified vertex-table elimination, `GRAPH_TABLE` flattening & edge-local predicate rewriting.**
   When an edge table has an enforced, non-deferred foreign key referencing a vertex table's unique key — and the query only uses that vertex for traversal or its key column — LexDB eliminates the redundant vertex table join completely, caps FK distinct counts using persisted `ANALYZE` row counts of the referenced table, emits direct edge-to-edge join equalities, and rewrites key comparisons like `b.id < c.id` onto the edge table itself (`e.src < e.dst`) so they filter at scan time. Single-branch `GRAPH_TABLE` clauses joined with outer `JOIN` / `LEFT JOIN` tables flatten directly into the outer query instead of materializing intermediate match sets, and `LEFT JOIN ... WHERE right_col IS NULL` compiles into a hash anti-join. A 3-edge triangle pattern drops from a 6-table join down to a tight 3-way self-join on `knows`.
2. **Direct-indexed integer hash joins, 64-bit composite keys (`JK_INT2_64`), and weighted count-only probes.**
   Single-column dense integer build sides use a flat direct-indexed lookup array (one bounds-checked array load per probe, no hashing). Two-column integer join keys such as `(src, dst)` probe flat open-addressed 64-bit pair tables (`FastInt2Map` / `FastInt2Count`) without tuple encoding or heap allocation. When no payload columns are needed from the build side (such as closing a triangle, cycle, or multi-hop pattern under `SELECT count(*)`), LexDB uses weighted count-only probes that multiply per-row match counts instead of expanding intermediate rows — evaluating billion-match patterns directly in cache with zero row materialization, including inline `<>` integer residual checks.
3. **Dictionary-preserving low-cardinality text propagation.**
   When a hash join carries low-cardinality text dimensions (such as `country` or `industry`) through millions of edges into a downstream `GROUP BY`, LexDB deduplicates the build-side text buffer and passes a single shared dictionary per chunk so the downstream two-level hash aggregator hits its 64-slot word cache on ~100% of rows without re-hashing strings.
4. **Cold point-to-point bidirectional index-only BFS.**
   For single-source to single-target `ANY SHORTEST` queries, LexDB uses covering forward `(src, dst)` and reverse `(dst, src)` B+tree indexes to run bidirectional BFS directly off 8-byte integer leaf keys — **without scanning the edge table or building a CSR**. Finding a 5-hop shortest path in a 1M-edge graph takes **0.70 ms cold** (`0.38 ms` warm).
5. **MVCC-safe cached CSR (Compressed Sparse Row) engine.**
   For single-source to many-targets (`G11`), multi-source, or repeated shortest-path queries, LexDB scans only the `(src, dst)` columns from its columnar B+tree leaves to build a compact dense CSR (~8.8 MB for 100k vertices and 1M edges; automatically switching to sparse 64-bit ID mapping for arbitrary IDs), caches it in a bounded LRU, and runs flat generation-stamped level-synchronous BFS (automatically flipping direction when the target set is smaller than the source set).
   - **Zero stale reads, full MVCC:** Every B+tree tracks a monotonic commit stamp (`treeStamp`), updated once per written tree at commit time. Committed `INSERT`/`UPDATE`/`DELETE` statements invalidate stale CSR entries in O(1); uncommitted writes inside an open transaction (`BEGIN ... INSERT ... ROLLBACK`) and older MVCC snapshots bypass the cache so read-your-writes and isolation semantics stay 100% exact.

---

## Benchmark 1: Social-network graph suite (11 queries, 1.1M edges)

To measure property graph performance apples-to-apples against both a relational database and dedicated graph engines, we ran an 11-query social-network graph suite covering local k-hop traversals, full-graph aggregations, filtered multi-hop joins, triangle counting, and shortest-path queries.

### Test environment and dataset

- **Host:** AMD Ryzen 7 8745HS, 46 GB RAM, Linux 7.2, fixed CPU clock (`cpu-boost off`).
- **Strict single-core / single-thread execution:** Every engine pinned to CPU 0 with intra-query parallelism disabled (`max_parallel_workers_per_gather = 0` on PostgreSQL, `threads = 1` on DuckDB and Kùzu, single-core LexDB).
- **Engines compared:**
  - **LexDB** (`GRAPH_TABLE` SQL/PGQ, `--cache-mb 2048`)
  - **PostgreSQL 18.6** (hand-written equivalent joins and `WITH RECURSIVE` CTEs; `shared_buffers = 2GB`, `work_mem = 256MB`)
  - **DuckDB 2.0.1 + DuckPGQ** (SQL/PGQ `GRAPH_TABLE` + `ANY SHORTEST`)
  - **Kùzu 0.11.3** (native Cypher property graph database)
- **Dataset:** 100,000 `people`, 2,000 `companies`, 100,000 `works_at` edges, and 1,000,000 directed `knows` edges with community clustering and Zipfian degree skew.
- **Verification:** Exact result parity verified across all four engines on **11 of 11 queries**.

### Results (median ms, single core / single thread, `cpu-boost off`)

| Query | Pattern | LexDB (warm) | LexDB (cold) | PG 18 (1 core) | DuckPGQ (1T) | Kùzu (1T) | LexDB / PG1 | LexDB / DuckPGQ | LexDB / Kùzu |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **G1** | 1-hop neighborhood + weight sum | **0.27 ms** | 0.49 ms | **0.20 ms** | 1.28 ms | 1.20 ms | 1.37× | **0.21×** | **0.22×** |
| **G2** | 2-hop distinct friends-of-friends | **0.52 ms** | 0.66 ms | 0.85 ms | 2.87 ms | 55.60 ms | **0.61×** | **0.18×** | **0.009×** |
| **G3** | 1..3-hop distinct neighborhood (hub) | **36.54 ms** | 36.88 ms | 49.04 ms | 52.95 ms | 189.51 ms | **0.75×** | **0.69×** | **0.19×** |
| **G4** | 1..4-hop distinct neighborhood | **2.27 ms** | 3.00 ms | 2.69 ms | 50.66 ms | 12.01 ms | **0.85×** | **0.045×** | **0.19×** |
| **G5** | Full-graph 1M-edge country rollup | 53.45 ms | 53.73 ms | 338.80 ms | **14.95 ms** | 19.80 ms | **0.16×** | 3.58× | 2.70× |
| **G6** | Co-workers who know each other (Tech) | 31.39 ms | 30.97 ms | 80.00 ms | **10.21 ms** | 49.18 ms | **0.39×** | 3.07× | **0.64×** |
| **G7** | Filtered 2-hop star (`UK` + `>=2022` + `Tech`) | 22.85 ms | 24.69 ms | 73.03 ms | **6.34 ms** | 85.96 ms | **0.31×** | 3.60× | **0.27×** |
| **G8** | Directed triangles (subset `id <= 5000`) | 278.50 ms | 281.37 ms | 957.65 ms | **177.89 ms** | 343.94 ms | **0.29×** | 1.57× | **0.81×** |
| **G9** | Full-graph 1M-edge directed triangles | **388.46 ms** | 388.33 ms | 1,813.83 ms | 518.85 ms | 521.31 ms | **0.21×** | **0.75×** | **0.75×** |
| **G10** | Shortest path (5 hops, `42 -> 98955`) | **0.41 ms** | **0.71 ms** | 1,080.53 ms | 61.89 ms | 40.59 ms | **0.0004×** | **0.007×** | **0.010×** |
| **G11** | Single-source shortest paths (`42 -> 2k` targets) | **7.37 ms** | **23.92 ms** | 1,263.90 ms | 64.31 ms | 48.26 ms | **0.006×** | **0.11×** | **0.15×** |
| **Sum** | All 11 queries | **822.0 ms** | — | 5,660.5 ms | 962.2 ms | 1,367.4 ms | **6.89× faster** | **1.17× faster** | **1.66× faster** |
| **Geomean** | Geometric mean across all 11 queries | — | — | **0.16× (6.38× faster)** | **0.40× (2.50× faster)** | **0.21× (4.79× faster)** | | | |

### Key takeaways

- **Fastest overall on both total time and geometric mean:** On a single core, LexDB completes the full 11-query suite in **822.0 ms total** — **6.89× faster than PostgreSQL 18**, **1.17× faster than DuckDB + DuckPGQ**, and **1.66× faster than Kùzu** (geometric mean **6.38× faster than PostgreSQL**, **2.50× faster than DuckPGQ**, and **4.79× faster than Kùzu**), all through standard SQL:2023 `GRAPH_TABLE` over live transactional tables. LexDB beats PostgreSQL on **10/11**, beats Kùzu on **10/11**, beats DuckPGQ on **7/11**, and is **#1 fastest on 6 of 11 queries**.
- **Shortest paths (`G10`, `G11`):**
  - Point-to-point 5-hop shortest path (`G10`) runs in **0.71 ms cold** (index-only bidirectional BFS) and **0.41 ms warm** — **~2,635× faster than PostgreSQL**, **151× faster than DuckPGQ**, and **99× faster than Kùzu**.
  - Single-source shortest paths to 2,000 targets (`G11`) run in **23.92 ms cold** (including scanning 1M edges to build the CSR — still 2.7× faster than warm DuckPGQ and 2.0× faster than warm Kùzu) and **7.37 ms warm** (**171× faster than PostgreSQL**, **8.7× faster than DuckPGQ**, and **6.5× faster than Kùzu**).
- **Full-graph triangle counting (`G9`):** Through pure `GRAPH_TABLE` syntax, LexDB is the **fastest engine of all four** on full-graph 1M-edge directed triangle counting (**388 ms** vs **519 ms** DuckPGQ, **521 ms** Kùzu, and **1,814 ms** PostgreSQL — **1.34× faster than DuckPGQ/Kùzu** and **4.67× faster than hand-written PostgreSQL**).
- **Local multi-hop traversals (`G1`–`G4`):** LexDB is the fastest engine on 2-hop, 1..3-hop, and 1..4-hop traversals, running **5–22× faster than DuckPGQ and Kùzu** on localized point-seeded patterns thanks to direct B+tree index lookups.
- **Where pure OLAP engines remain faster today:** On unfiltered full-graph scan-and-aggregate joins (`G5`–`G7`), DuckDB's pure in-memory columnar scan remains ~3.1–3.6× faster than LexDB's B+tree-backed engine — though LexDB beats PostgreSQL by **2.6–6.3×** on all three and beats Kùzu on both `G6` (`31.4` vs `49.2 ms`) and `G7` (`22.9` vs `86.0 ms`, **3.76× faster**).

---

## Benchmark 2: LDBC LSQB (SF0.1 and SF1, 5 engines)

To test multi-way subgraph pattern matching on an open-source industry benchmark, we ran the **LDBC Labelled Subgraph Query Benchmark (LSQB)** — 9 global pattern-matching queries (`Q1`–`Q9`) spanning 3- to 9-hop chains, 4-cycles, triangles with country joins, stars, optional matches (`LEFT JOIN`), and negated edges (anti-joins) — across five engines at both **SF0.1** and **SF1**.

### Test environment and dataset

- **Host:** AMD Ryzen 7 8745HS, 46 GB RAM, Linux 7.2.
- **Strict single-core / single-thread execution:** Every engine pinned to CPU 0 (`taskset -c 0`) with parallelism disabled (`max_parallel_workers_per_gather = 0` on PostgreSQL, `threads = 1` on DuckDB and Kùzu, single-core LexDB and Neo4j). Median of 3 warm runs per query.
- **Engines compared:**
  - **LexDB** (`GRAPH_TABLE` SQL/PGQ over Projected-FK with `PRIMARY KEY` + `REFERENCES` foreign keys, `--cache-mb 4096`, `max_statement_mem = 8 GB` — 7/9 SF1 queries fit in default `256 MB` and 8/9 in `512 MB`; `Q8` needs >`512 MB` total statement hash memory)
  - **DuckDB 2.0.1 + DuckPGQ** (in-memory `:memory:`, SQL/PGQ `GRAPH_TABLE` over Projected-FK with **matching `PRIMARY KEY` + `REFERENCES` foreign keys** so DuckDB's FK join elimination and factorized group joins are enabled on equal footing with LexDB; without PK/FK constraints — as in the official `ldbc/lsqb/pgq` loader — DuckPGQ runs SF1 in `19.63 s` and plain DuckDB SQL on Merged-FK runs SF1 in `14.85 s`)
  - **PostgreSQL 18.6** (official LSQB SQL over Merged-FK; `shared_buffers = 4GB`, `work_mem = 512MB`, `ANALYZE`; adding PK/FK indexes on PG 18 was also tested and was slower overall at `141.2 s` on SF1 due to index/merge-join regressions on Q4 and Q7)
  - **Kùzu 0.11.3** (official LSQB `ladybug` Cypher over Projected-FK with bidirectional `Person_knows_Person`, default buffer pool, CSR storage)
  - **Neo4j 5.26.0 Community Edition** (official LSQB `neo4j-admin database import full` and Cypher queries, OpenJDK 21, `4 GB` heap / `2 GB` pagecache matching official `ldbc/lsqb/neo4j/start.sh`; note that Community Edition uses the default `slotted` runtime — Enterprise's `pipelined` runtime is proprietary)
- **Datasets (official LDBC LSQB):**
  - **SF0.1:** 432,229 vertices and 2,080,410 edges (10 vertex types, 26 edge types). Timeout: 60 s.
  - **SF1:** 3,955,784 vertices and 22,196,682 edges (10 vertex types, 26 edge types). Timeout: 120 s.
- **Verification:** Every completed query validated for 100% exact count parity against official LDBC `expected-output.csv` (up to 1.67 billion matches on SF1 `Q6`).

### Results — SF1 (4.0M vertices / 22.2M edges, median ms, 1 core / 1 thread)

| Query | Pattern | Matches | LexDB | DuckPGQ 2.0 (+FK) | PG 18 (1c) | Kùzu 0.11.3 | Neo4j 5.26 CE |
|---|---|---:|---:|---:|---:|---:|---:|
| **Q1** | 8-hop path (`Country ← City ← Person ← Forum → Post ← Comment → Tag → TagClass`) | 221,636,419 | 1,001.7 ms | **180.6 ms** | 20,399.4 ms | 32,104.0 ms | 6,710.8 ms |
| **Q2** | 4-cycle (`Person ↔ Person`, `Comment → Post` creators) | 1,085,627 | 818.4 ms | **201.3 ms** | 900.7 ms | 977.7 ms | 2,175.1 ms |
| **Q3** | Triangle of friends in the same country (9 tables) | 753,570 | 1,164.8 ms | **351.4 ms** | 3,218.6 ms | 2,734.2 ms | 15,319.8 ms |
| **Q4** | Star around `Message` (`Tag`, `Creator`, `Liker`, `Comment`) | 14,836,038 | 957.4 ms | **371.1 ms** | 2,964.7 ms | 442.2 ms | 7,362.0 ms |
| **Q5** | 3-hop `Tag1 ← Message ← Comment → Tag2` (`Tag1 ≠ Tag2`) | 13,824,510 | 1,147.5 ms | **351.5 ms** | 3,032.5 ms | 695.7 ms | 7,574.4 ms |
| **Q6** | 3-hop `Person ↔ Person ↔ Person → Tag` (`p1 ≠ p3`) | 1,668,134,320 | **446.1 ms** | 568.6 ms | 57,191.3 ms | 2,827.2 ms | 40,627.8 ms |
| **Q7** | Star with two `OPTIONAL MATCH` / `LEFT JOIN` edges | 26,190,133 | 1,192.2 ms | **478.7 ms** | 5,062.2 ms | 1,189.2 ms | 10,190.1 ms |
| **Q8** | Q5 + negated edge (`Comment` does not have `Tag1`) | 6,907,213 | 2,023.8 ms | **652.0 ms** | 5,325.7 ms | 2,951.6 ms | 14,308.4 ms |
| **Q9** | Q6 + negated edge (`p1` does not know `p3`) | 1,596,153,418 | 5,493.1 ms | **1,408.5 ms** | TIMEOUT (>120s) | 61,042.4 ms | 51,776.5 ms |
| **Total** | All 9 queries | — | 14,245.0 ms | **4,563.7 ms** | 98,095.0 ms *(8/9)* | 104,964.2 ms | 156,044.9 ms |
| **Geomean** | Relative to LexDB (`<1` faster, `>1` slower than LexDB) | — | **1.00×** | **0.34×** *(2.91× faster)* | **5.40× slower** *(8/9)* | **2.39× slower** | **9.48× slower** |

### Results — SF0.1 (432k vertices / 2.1M edges, median ms, 1 core / 1 thread)

| Query | Matches | LexDB | DuckPGQ 2.0 (+FK) | PG 18 (1c) | Kùzu 0.11.3 | Neo4j 5.26 CE |
|---|---:|---:|---:|---:|---:|---:|
| **Q1** | 8,773,828 | 69.1 ms | **16.0 ms** | 1,055.6 ms | 1,301.2 ms | 608.8 ms |
| **Q2** | 82,990 | 54.1 ms | **13.4 ms** | 62.6 ms | 56.0 ms | 192.5 ms |
| **Q3** | 30,456 | 21.6 ms | **12.6 ms** | 54.2 ms | 93.6 ms | 235.4 ms |
| **Q4** | 784,511 | 68.2 ms | 39.7 ms | 263.7 ms | **36.9 ms** | 678.3 ms |
| **Q5** | 1,079,722 | 71.5 ms | **22.0 ms** | 245.1 ms | 48.6 ms | 614.5 ms |
| **Q6** | 55,607,896 | 30.4 ms | **19.7 ms** | 1,589.7 ms | 121.3 ms | 1,464.9 ms |
| **Q7** | 1,628,132 | 77.0 ms | **33.7 ms** | 343.6 ms | 72.6 ms | 926.9 ms |
| **Q8** | 537,142 | 130.7 ms | **47.8 ms** | 319.5 ms | 198.8 ms | 1,246.7 ms |
| **Q9** | 51,009,398 | 117.2 ms | **38.0 ms** | TIMEOUT (>60s) | 2,015.9 ms | 1,632.8 ms |
| **Total** | All 9 queries | 639.9 ms | **242.9 ms** | 3,934.0 ms *(8/9)* | 3,945.0 ms | 7,600.9 ms |
| **Geomean** | Relative to LexDB | **1.00×** | **0.39×** *(2.57× faster)* | **4.91× slower** *(8/9)* | **2.44× slower** | **10.95× slower** |

### Key takeaways (LDBC LSQB)

- **Fastest disk-backed transactional / graph database at both SF0.1 and SF1 (#2 overall behind in-memory DuckDB + DuckPGQ):** At SF1 (22.2M edges), LexDB finishes all 9 queries in **14.25 s** — beating **PostgreSQL 18** (`98.10 s` on 8 queries plus Q9 timeout, **5.40×** geomean), **Kùzu 0.11.3** (`104.96 s`, **7.4×** total / **2.39×** geomean), and **Neo4j 5.26 Community** (`156.04 s`, **11.0×** total / **9.48×** geomean) while serving live durable transactional B+trees.
- **Billion-match queries without row materialization (`Q6`, `Q9`):** On SF1 `Q6` (1.67 billion 3-hop paths), weighted count-only hash joins count all 1.67B matches in **446 ms** — **#1 fastest of all five engines** (ahead of DuckPGQ+FK's `569 ms`, **6.3× faster than Kùzu**, **91× faster than Neo4j**, and **128× faster than PostgreSQL 18**). On SF1 `Q9` (1.60 billion matches with an anti-join), flattening `GRAPH_TABLE` + 64-bit `(p1, p3)` anti-join probing completes in **5.49 s** (**11.1× faster than Kùzu** and **9.4× faster than Neo4j**, while PostgreSQL times out past 120 s).
- **Where pure OLAP / factorized engines lead:** With matching `PRIMARY KEY` and `FOREIGN KEY` constraints, in-memory **DuckDB 2.0 + DuckPGQ** (`4.56 s` SF1 / `243 ms` SF0.1) is ~2.6–2.9× faster than LexDB in geometric mean thanks to pure columnar in-memory storage and general factorized group joins across multi-way chains (`Q1`–`Q5`, `Q7`–`Q9`). **Kùzu** also leads LexDB on pure star queries (`Q4`, `Q5`, and a tie on `Q7` at SF1), though LexDB is far ahead on long paths (`Q1`: `1.0 s` vs `32.1 s`), cycles (`Q2`, `Q3`), and billion-match anti-joins (`Q9`: `5.5 s` vs `61.0 s`).

---

## Tips for getting the best performance

1. **Declare enforced foreign keys on edge tables.**
   Adding `REFERENCES vertex_table(id)` on your edge table's `src` and `dst` columns lets LexDB safely eliminate redundant vertex-table joins whenever a query doesn't read non-key vertex columns.
2. **Index both edge directions.**
   Define `PRIMARY KEY (src, dst)` and `CREATE INDEX ... ON edges (dst, src)` on directed edge tables. This accelerates both reverse/cyclic joins and unlocks sub-millisecond cold bidirectional index-only BFS for point-to-point `ANY SHORTEST` queries.
3. **Use `ANY SHORTEST` instead of `WITH RECURSIVE` for reachability and shortest paths.**
   `ANY SHORTEST` compiles directly to bidirectional index BFS or cached CSR BFS instead of iterating relational joins level by level.

---

## SQL reference

For full syntax, DDL options, label expressions, functions (`VERTEX_ID`, `EDGE_ID`, `PATH_LENGTH`, `MATCHNUM`), and dialect details:

- PostgreSQL door: [CREATE PROPERTY GRAPH](sql/postgresql/create-property-graph.md) · [GRAPH_TABLE](sql/postgresql/graph-table.md)
- SQL Server door: [CREATE PROPERTY GRAPH](sql/tsql/create-property-graph.md) · [GRAPH_TABLE](sql/tsql/graph-table.md)
- Oracle door: [CREATE PROPERTY GRAPH](sql/oracle/create-property-graph.md) · [GRAPH_TABLE](sql/oracle/graph-table.md)
