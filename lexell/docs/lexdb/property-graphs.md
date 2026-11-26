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

Naive SQL/PGQ implementations rewrite every graph pattern into verbose multi-table joins or recursive CTEs, leaving 10×–1,000× performance on the table. LexDB combines four graph-aware optimizations inside its relational engine:

1. **FK-verified vertex-table elimination & transitive edge equalities.**
   When an edge table has an enforced, non-deferred foreign key referencing a vertex table's unique key — and the query only uses that vertex for traversal or its key column — LexDB eliminates the redundant vertex table join completely and emits direct edge-to-edge join equalities. A 3-edge triangle pattern drops from a 6-table join down to a tight 3-way self-join on `knows`.
2. **Packed composite integer hash joins (`JK_INT2`) and count-only hash tables.**
   Two-column integer join keys such as `(src, dst)` pack directly into a single 64-bit integer key without tuple encoding or re-checking individual predicates. When no payload columns are needed from the build side (such as closing a triangle or cycle), LexDB builds a compact count-only hash table (`24 B/key`) with zero row storage.
3. **Cold point-to-point bidirectional index-only BFS.**
   For single-source to single-target `ANY SHORTEST` queries, LexDB uses covering forward `(src, dst)` and reverse `(dst, src)` B+tree indexes to run bidirectional BFS directly off 8-byte integer leaf keys — **without scanning the edge table or building a CSR**. Finding a 5-hop shortest path in a 1M-edge graph takes **0.71 ms cold** (`0.41 ms` warm).
4. **MVCC-safe cached CSR (Compressed Sparse Row) engine.**
   For single-source to many-targets (`G11`), multi-source, or repeated shortest-path queries, LexDB scans only the `(src, dst)` columns from its columnar B+tree leaves to build a compact dense CSR (~8.8 MB for 100k vertices and 1M edges; automatically switching to sparse 64-bit ID mapping for arbitrary IDs), caches it in a bounded LRU, and runs flat generation-stamped level-synchronous BFS (automatically flipping direction when the target set is smaller than the source set).
   - **Zero stale reads, full MVCC:** Every B+tree tracks a monotonic commit stamp (`treeStamp`), updated once per written tree at commit time. Committed `INSERT`/`UPDATE`/`DELETE` statements invalidate stale CSR entries in O(1); uncommitted writes inside an open transaction (`BEGIN ... INSERT ... ROLLBACK`) and older MVCC snapshots bypass the cache so read-your-writes and isolation semantics stay 100% exact.

---

## Benchmark: LexDB vs PostgreSQL 18, DuckDB + DuckPGQ, and Kùzu

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
| **G1** | 1-hop neighborhood + weight sum | **0.28 ms** | 0.45 ms | 0.20 ms | 1.28 ms | 1.20 ms | 1.42× | **0.22×** | **0.23×** |
| **G2** | 2-hop distinct friends-of-friends | **0.55 ms** | 0.69 ms | 0.85 ms | 2.87 ms | 55.60 ms | **0.65×** | **0.19×** | **0.01×** |
| **G3** | 1..3-hop distinct neighborhood (hub) | **36.37 ms** | 36.81 ms | 49.04 ms | 52.95 ms | 189.51 ms | **0.74×** | **0.69×** | **0.19×** |
| **G4** | 1..4-hop distinct neighborhood | **2.48 ms** | 3.17 ms | 2.69 ms | 50.66 ms | 12.01 ms | **0.92×** | **0.05×** | **0.21×** |
| **G5** | Full-graph 1M-edge country rollup | 110.22 ms | 111.12 ms | 338.80 ms | **14.95 ms** | 19.80 ms | **0.33×** | 7.37× | 5.57× |
| **G6** | Co-workers who know each other (Tech) | 52.13 ms | 53.89 ms | 80.00 ms | **10.21 ms** | 49.18 ms | **0.65×** | 5.10× | 1.06× |
| **G7** | Filtered 2-hop star (`UK` + `>=2022` + `Tech`) | 41.54 ms | 45.03 ms | 73.03 ms | **6.34 ms** | 85.96 ms | **0.57×** | 6.55× | **0.48×** |
| **G8** | Directed triangles (subset `id <= 5000`) | 313.81 ms | 318.74 ms | 957.65 ms | **177.89 ms** | 343.94 ms | **0.33×** | 1.76× | **0.91×** |
| **G9** | Full-graph 1M-edge directed triangles | 541.30 ms | 539.66 ms | 1,813.83 ms | **518.85 ms** | 521.31 ms | **0.30×** | 1.04× | 1.04× |
| **G10** | Shortest path (5 hops, `42 -> 98955`) | **0.41 ms** | **0.71 ms** | 1,080.53 ms | 61.89 ms | 40.59 ms | **0.0004×** | **0.007×** | **0.010×** |
| **G11** | Single-source shortest paths (`42 -> 2k` targets) | **6.34 ms** | **23.55 ms** | 1,263.90 ms | 64.31 ms | 48.26 ms | **0.005×** | **0.10×** | **0.13×** |
| **Sum** | All 11 queries | **1,105.4 ms** | — | 5,660.5 ms | 962.2 ms | 1,367.4 ms | **5.12× faster** | 1.15× | **1.24× faster** |
| **Geomean** | Geometric mean across all 11 queries | — | — | **0.19× (5.17× faster)** | **0.49× (2.03× faster)** | **0.26× (3.89× faster)** | | | |

### Key takeaways

- **Overall geometric mean:** On a single core, LexDB is **5.17× faster than PostgreSQL 18**, **2.03× faster than DuckDB + DuckPGQ**, and **3.89× faster than Kùzu** across the full 11-query suite — all through standard SQL:2023 `GRAPH_TABLE` over live transactional tables.
- **Shortest paths (`G10`, `G11`):**
  - Point-to-point 5-hop shortest path (`G10`) runs in **0.71 ms cold** (index-only bidirectional BFS) and **0.41 ms warm** — **~2,600× faster than PostgreSQL**, **151× faster than DuckPGQ**, and **99× faster than Kùzu**.
  - Single-source shortest paths to 2,000 targets (`G11`) run in **23.55 ms cold** (including scanning 1M edges to build the CSR — still 2.7× faster than warm DuckPGQ and 2.0× faster than warm Kùzu) and **6.34 ms warm** (**199× faster than PostgreSQL**, **10.1× faster than DuckPGQ**, and **7.6× faster than Kùzu**).
- **Local multi-hop traversals (`G1`–`G4`):** LexDB is the fastest engine on 2-hop, 1..3-hop, and 1..4-hop traversals, running **5–20× faster than DuckPGQ and Kùzu** on localized point-seeded patterns thanks to direct B+tree index lookups.
- **Full-graph triangle counting (`G8`, `G9`):** Through pure `GRAPH_TABLE` syntax, LexDB matches DuckPGQ (`519 ms`) and Kùzu (`521 ms`) within 4% on full-graph 1M-edge triangle counting (`541 ms`), while running **3.35× faster than hand-written PostgreSQL** (`1,814 ms`).
- **Where pure OLAP / columnar engines remain faster today:** On unfiltered full-graph scan-and-aggregate joins (`G5`–`G7`), DuckDB's in-memory columnar scan and specialized hash-join kernels run 5–7× faster than LexDB's B+tree-backed engine (though LexDB still beats PostgreSQL by 1.5–3.1× on all three).

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
