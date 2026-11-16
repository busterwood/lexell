-- The conventional TPC-H secondary indexes, applied to both engines.
--
-- TPC-H fixes the logical schema but leaves the physical design to the
-- implementation, so any published comparison has to state the index set.
-- These are the ones a deployment would normally add; each is a trade
-- against load time and the planner may still choose a sequential scan.
--
-- Built after the load and timed separately (run.sh, TPCH_INDEXES). The
-- baseline with primary keys only is TPCH_INDEXES=none.

-- q17 and q20's correlated aggregates: without this both engines scan
-- lineitem inside the SubPlan for every candidate row.
create index lineitem_part_supp on lineitem (l_partkey, l_suppkey);

-- Date-range filters: q1, q6, q12, q14, q15, q20.
create index lineitem_shipdate on lineitem (l_shipdate);

-- orders by customer, for the customer/orders joins: q3, q5, q10, q13, q18.
create index orders_cust_date on orders (o_custkey, o_orderdate);

-- Date ranges on orders: q3, q4, q5, q10.
create index orders_date on orders (o_orderdate);

-- part by brand and container: q2, q16, q19.
create index part_brand_container on part (p_brand, p_container);

-- partsupp by supplier: q2, q11, q16, q20.
create index partsupp_supp on partsupp (ps_suppkey);

-- Foreign-key joins on the smaller tables: q5, q7, q8, q9, q10, q21.
create index customer_nation on customer (c_nationkey);
create index supplier_nation on supplier (s_nationkey);
