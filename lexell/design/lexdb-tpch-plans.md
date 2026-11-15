# TPC-H plans: what lexdb's planner is missing

Status: findings from the SF1 run on 2026-11-15 at main `04fa4b80`, with
`bench/tpch`'s conventional index set and PostgreSQL 18.6 at
`max_parallel_workers_per_gather = 0` for the one-core column. One run per
query; the timings are in `~/tpch/out/summary.md`. This note is about the
plans, not about proving the last percent.

The headline: **lexdb / PostgreSQL is 4.28x on the geometric mean of the 20
queries that complete**, and 7.96x against PostgreSQL at four processes.
q19 and q21 do not complete in 120 s on lexdb; PostgreSQL runs them in 34
and 718 ms. The gaps are concentrated in a few planner decisions, and q17
shows that when the choice is right lexdb can be faster than PostgreSQL.

## 1. How the plans were taken

Both engines had the same data, the same `ANALYZE`, and the same secondary
indexes (`indexes.sql`: lineitem part/supp and shipdate, orders
customer/date and date, part brand/container, partsupp supplier, customer
and supplier nation). `EXPLAIN` only, no execution, except the timings
from the benchmark. PostgreSQL was run with parallel query off so its plan
is the one the `pg1` column used.

The query text is the TPC-H text with one spelling change: lexdb's parser
takes `interval '3 months'`, not the specification's `interval '3' month`.
q15 is not in this note because its view DDL is not a single `EXPLAIN`.

## 2. The numbers

| query | lexdb | PG one core | ratio | first cause in the plans |
|---|---:|---:|---:|---|
| q1 | 16095.8 | 2703.0 | 6.0 | index range over 98% of lineitem |
| q2 | 111.8 | 140.6 | 0.8 | |
| q3 | 3429.8 | 455.0 | 7.5 | index range over 48% of orders |
| q4 | 7667.3 | 172.5 | 44.4 | EXISTS per row (57k probes) |
| q5 | 1777.0 | 242.8 | 7.3 | join order starts from the orders date range |
| q6 | 1117.3 | 435.1 | 2.6 | |
| q7 | 12140.4 | 526.3 | 23.1 | join order starts from a 30% lineitem range |
| q8 | 435.4 | 207.0 | 2.1 | part's filter is not pushed into its scan |
| q9 | 4442.0 | 1499.7 | 3.0 | join order starts from the lineitem scan |
| q10 | 1591.9 | 569.5 | 2.8 | join order starts from the customer scan |
| q11 | 198.2 | 53.5 | 3.7 | |
| q12 | 6834.6 | 805.5 | 8.5 | 6M primary-key lookups instead of a hash/merge join |
| q13 | 5729.5 | 704.9 | 8.1 | outer join is a lookup per customer |
| q14 | 706.6 | 140.6 | 5.0 | plain index range instead of a bitmap scan |
| q15 | 1598.4 | 545.9 | 2.9 | |
| q16 | 671.4 | 225.4 | 3.0 | part's filter is not pushed; NOT IN is a subplan |
| q17 | 39.4 | 526.2 | **0.1** | lexdb starts from the selective part index |
| q18 | 2969.1 | 1063.3 | 2.8 | IN subquery becomes a lookup per value |
| q19 | timeout | 34.0 | | OR-of-ANDs becomes a cross join |
| q20 | 1118.5 | 110.0 | 10.2 | scalar aggregate per partsupp row |
| q21 | timeout | 718.4 | | two EXISTS per lineitem row |
| q22 | 1124.9 | 75.1 | 15.0 | NOT EXISTS per customer row |

The three checksum differences (q1, q8, q17) are decimal scale only:
q17 is `348406.0542857142857143` in lexdb and `348406.054285714286` in
PostgreSQL. They are not wrong values.

## 3. What the plans show

### 3.1 A full-range index scan is chosen over a sequential scan

q1's plan is:

```
scan lineitem: index lineitem_shipdate range (estimated 5898972 rows)
aggregate
order: sort
```

PostgreSQL's one-core plan is `Seq Scan on lineitem` with a
`HashAggregate`. The predicate `l_shipdate <= date '1998-09-02'` keeps
5.9M of 6.0M rows: the index is pure overhead. This is not a close call
that a different constant would fix. A predicate that matches every row
still plans through the index:

```
select sum(l_quantity) from lineitem where l_shipdate <= '1998-12-31';
scan lineitem: index lineitem_shipdate range (estimated 6001215 rows)
aggregate
```

The sequential alternative is not absent: `EXPLAIN ANALYZE` shows the
runtime switch taking it, but too late. q1 reads 6,001,210 rows through
the range in 5,861 batches and then reports
`switched to scan: cheaper than the range, by the measured costs`; it has
already paid for the index. The cost model should have started with the
scan. PostgreSQL uses a bitmap scan for medium selectivity (q4, q5, q14)
and a sequence scan for the broad ones; lexdb has no bitmap path in these
plans.

The same initial choice appears in q3 (48% of orders), q7 (30% of
lineitem), and q14 (plain range instead of PostgreSQL's bitmap scan).
q1's 16 s against 2.7 s is mostly this.

### 3.2 EXISTS, NOT EXISTS and IN stay per-row subplans

q4:

```
scan orders: index orders_date range (estimated 57291 rows)
aggregate
order: sort
subquery 1 (exists): per row, on orders.o_orderkey
  scan lineitem: primary key range (estimated 5 rows)
```

PostgreSQL turns the same predicate into a `Nested Loop Semi Join`. The
plan's textual order is misleading: `EXPLAIN ANALYZE` shows the EXISTS
running 57,218 times, so it is applied to the orders before the
aggregate, not after it. The cost is the per-row subplan plus the scan's
runtime switch (1,499,996 rows read to keep 52,523), and q4 is 44x
slower.

q21 is two per-row EXISTS over 6M lineitem rows; PostgreSQL has a
`Nested Loop Semi Join` and a `Nested Loop Anti Join`. q22 is a per-row
NOT EXISTS; PostgreSQL has a `Nested Loop Anti Join`. q18's IN over a
grouped subquery becomes `primary key lookup for each value` (up to 1.5M
keys); PostgreSQL hashes the grouped subquery and hash joins it. q16's
NOT IN is a subplan in lexdb; PostgreSQL hashes it.

The semi-join machinery exists (optimizer 42), but these shapes do not
reach it: derived tables (q22), correlation with an extra inequality
(q21), IN with GROUP BY/HAVING (q18), and EXISTS under an aggregate (q4).
Widening the eligibility rules is the highest-value planner change.

### 3.3 OR-of-ANDs becomes a cross join

q19 is the clearest missing rule:

```
scan lineitem: full scan
cross join part: loop over full scan
aggregate
```

PostgreSQL plans the same OR as a `BitmapOr` of three
`part_brand_container` index scans, then a nested loop with an index probe
into `lineitem_part_supp` for each part. The three OR branches are
disjoint, so this is a union of three joins; even without a general OR
rule, decomposing the OR and reusing the branch's predicates would avoid
the product.

There is no bitmap-OR path in lexdb's plan output. The minimum fix is to
extract per-branch join predicates and let each branch drive an index
nested loop; the full fix is a BitmapOr operator.

### 3.4 Join order starts from the broad side

q5 starts from the orders date range (227k rows), then hashes customer,
nation and region, then probes lineitem:

```
scan orders: index orders_date range (estimated 227686 rows)
join customer: hash on (c_custkey) over full scan
join nation: hash on (n_nationkey) over full scan
join region: hash on (r_regionkey) over full scan
join lineitem: primary key range (estimated 5 rows) per row
join supplier: hash on (s_suppkey, s_nationkey, s_nationkey) over full scan
```

PostgreSQL starts from the one region row, its five nations, the 6k
customers, then uses `orders_cust_date` for each customer and
`lineitem_pkey` for each order. It reads orders through a much narrower
key. The duplicate `s_nationkey` in lexdb's hash key is also a sign that
the equality class `c_nationkey = s_nationkey = n_nationkey` is not
collapsed.

The same pattern runs through q7 (lineitem shipdate range instead of the
two-nation customer/supplier filters), q8 (`scan part: full scan` with no
`p_type` filter, then a lineitem probe for all 200k parts), q9 (lineitem
full scan first, then part by hash), and q10 (customer full scan first,
then the orders date range). PostgreSQL starts from the filtered
dimension in each case.

The cost-based order is active: `SET lexdb_planner = rules` gives a
different, worse plan for q5 and q10. The problem is the model or the
search's starting candidates, not that the code is off. It prices a broad
index range and a per-row lookup too cheaply, and it does not push a
single-table predicate into the scan that would make a dimension small
(q8's `p_type`, q9's `p_name`).

### 3.5 Large-to-large joins become lookup-per-row

q12:

```
scan lineitem: full scan
join orders: primary key lookup per row
aggregate
order: sort
```

PostgreSQL filters lineitem to 28k rows (shipmode, dates), sorts it, and
merge joins orders. lexdb does one orders lookup for every lineitem row,
6M of them, before the aggregate. q13 has the same shape for an outer
join: 150k lookups per customer, where PostgreSQL hashes the right side
and does a hash right join. The cost model's lookup cost (one descent,
one row) does not account for the outer side being millions of rows, and
outer joins keep FROM order by design.

q18 is the same at the subquery level: the IN becomes up to 1.5M primary
key lookups instead of hashing the grouped subquery. PostgreSQL's plan is
a hash join followed by a merge join.

### 3.6 Aggregation and LIMIT

lexdb prints `aggregate` and then `order: sort`; PostgreSQL often uses
`GroupAggregate` with the group key as the sort key, so the aggregate's
input order already satisfies the ORDER BY. For four groups this is
noise; for q3's 314k groups, q10's 55k and q18's 517k it is not.
PostgreSQL also has hash aggregation with partitioning, and its
`Limit` sits above a full sort in these plans rather than a top-N, so
this is a smaller gap than the join issues, but it is part of q3/q10/q18.

### 3.7 EXPLAIN itself

Plain `EXPLAIN` shows an estimated row count only on scan nodes, and no
costs at all; joins and aggregates have neither. `EXPLAIN ANALYZE` adds
rows read and kept, batches, the runtime switch and a subquery's run count,
but not per-node time. q4's plan text puts the EXISTS after the aggregate
while `EXPLAIN ANALYZE` shows it running before: the printer's order is
misleading. Costs and rows on every node, and per-node time, would shorten
the next round of this work.

## 4. Where lexdb is ahead

q17 is the counterexample that keeps this from being a story about
missing operators. lexdb starts from the 205-row part index, probes
`lineitem_part_supp` for each part, and evaluates the scalar subquery 205
times: 39 ms. PostgreSQL scans lineitem, hashes the 205 parts, and applies
the subplan as a join filter; 526 ms. The same pieces (index nested loop,
scalar subquery, aggregate) are enough when the selective side drives the
join. q2 is also faster in lexdb.

## 5. What to build, in order

1. **Subquery unnesting.** Extend the semi/anti-join rewrite to derived
   tables, correlated EXISTS with extra predicates, IN with GROUP BY, and
   EXISTS under an aggregate. Apply the filter before the aggregate.
   Expected to fix q4, q18, q21, q22 and q16; q21/q22 are the difference
   between a timeout and a normal query.
2. **OR predicates.** Per-branch predicate extraction and index nested
   loops first; a BitmapOr operator after. q19.
3. **Access-path cost.** The runtime index-to-scan switch exists but fires
   only after the index has been paid for; price the initial choice so it
   starts with the scan, price a range index by selectivity and by whether
   it must fetch rows, add bitmap scans and index-only scans, and make the
   per-row lookup cost grow with the outer row count. q1, q3, q7, q12,
   q13, q14.
4. **Join order and predicate pushdown.** Push single-table filters into
   the access path before the cost search; use the filtered row count;
   collapse equality classes; start from the selective dimension. q5, q7,
   q8, q9, q10.
5. **Hash and merge joins for large and outer joins.** Do not choose a
   primary-key lookup per row when the outer side is millions of rows;
   allow a hash right join for q13's left join. q12, q13, q18.
6. **Aggregation and top-N.** Group aggregate on the group key, hash
   aggregate with partitions, and a top-N sort for LIMIT. q3, q10, q18,
   q21.
7. **EXPLAIN with estimates.** Rows and cost per node, actual rows under
   ANALYZE. This is diagnostic, not a speedup, but it is what makes the
   rest measurable.

Parallelism is a separate axis: PostgreSQL's four-process column is 7.96x
ahead, and lexdb runs one query on one SQL thread. That is a design
choice, not one of the planner gaps above; fix the single-thread plan
first, then decide what `par.map` should do for query execution.

## 6. Caveats

- One run per query at SF1. The plan shapes are stable; the exact ratios
  are not medians.
- Fixed TPC-H substitution values, no qgen variation, no RF1/RF2.
- The secondary index set is the same on both engines and is stated in
  `bench/tpch/indexes.sql`. q17's advantage and q20's remaining cost both
  depend on it.
- q19 and q21 are timeouts, not completed times; do not read their ratios
  as measurements.
- The three different checksums are decimal scale, not wrong values.
