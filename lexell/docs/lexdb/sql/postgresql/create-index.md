# CREATE INDEX

Makes an index on a table's columns or expressions.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CREATE [ UNIQUE ] INDEX [ CONCURRENTLY ] [ [ IF NOT EXISTS ] name ] ON table_name [ USING btree ]
    ( { column_name | ( expression ) | function_call } [ COLLATE collation ] [ opclass ]
      [ ASC | DESC ] [ NULLS { FIRST | LAST } ] [, ...] )
    [ WHERE predicate ]
```

## Arguments

`UNIQUE`
: No two rows may have equal values in the index. NULLs are distinct, so several rows may hold NULL. The rows already
  there are checked (23505 for a duplicate).

`CONCURRENTLY`
: Accepted. The index is built as without it.

*name*
: The index's name, in the table's schema. Without one, it is named as PostgreSQL names it: `table_column_idx`
  (`table_column_idx1` and so on if that is taken). `IF NOT EXISTS` needs a name, and skips an index or other
  relation of that name with a notice.

*table_name*
: A table, optionally schema-qualified. A view cannot have an index.

`USING btree`
: The index method. B-tree is the only one.

*column_name*, `(` *expression* `)`, *function_call*
: What the index holds: columns, or expressions of the row's columns (`lower(email)`, `(a + b)`), with no
  subqueries. A query uses an expression index when it uses the same expression.

`COLLATE`, *opclass*, `ASC`, `DESC`, `NULLS FIRST`, `NULLS LAST`
: Accepted and shown in `pg_indexes`; they change nothing. Text compares by its bytes, as the `C` collation and the
  `text_pattern_ops` class do, and the index is read in either direction. An operator class must be one of
  PostgreSQL's B-tree classes for a type lexdb has (42704 otherwise).

`WHERE` *predicate*
: A partial index: only the rows for which the predicate is true are in it. A query whose `WHERE` implies the
  predicate can use it; a partial unique index enforces uniqueness among those rows only.

## Remarks

- An index is a B+tree of its values and each row's primary key. A query that needs only the index's columns and the
  key reads the index alone (`index only` in `EXPLAIN`).
- The planner chooses indexes by cost, with the statistics of `ANALYZE` (gathered on its own by default).
- `CREATE INDEX` is transactional: in a block, `ROLLBACK` takes it back.
- Inside a read-only transaction, and on a replica, `CREATE INDEX` gives 25006.

## Differences from PostgreSQL

- Only B-tree indexes: `USING hash`, `gin`, `gist`, `brin` and `spgist` are refused (0A000).
- `INCLUDE (...)`, `WITH ( storage_parameter )`, `TABLESPACE` and `NULLS NOT DISTINCT` are not supported.
- `CONCURRENTLY` is accepted and does not change how the index is built.
- `pg_indexes.indexdef` shows an index on `(n + 1)` as `(((n + 1)))`; PostgreSQL shows `((n + 1))`.

## Examples

<!--setup: postgresql
CREATE TABLE customer (id int PRIMARY KEY, email text, city text, score int, joined date);
INSERT INTO customer SELECT g, 'user' || g || '@example.com', (ARRAY['york', 'leeds', 'hull'])[1 + g % 3], g % 10, DATE '2026-01-01' + g FROM generate_series(1, 300) AS g;
INSERT INTO customer VALUES (301, 'Ann@Example.com', 'york', NULL, NULL);
ANALYZE customer;
-->

The examples use a table of 301 rows:

```sql
CREATE TABLE customer (id int PRIMARY KEY, email text, city text, score int, joined date);
INSERT INTO customer
SELECT g, 'user' || g || '@example.com', (ARRAY['york', 'leeds', 'hull'])[1 + g % 3], g % 10, DATE '2026-01-01' + g
FROM generate_series(1, 300) AS g;
INSERT INTO customer VALUES (301, 'Ann@Example.com', 'york', NULL, NULL);
ANALYZE customer;
```

### A. An index on a column

<!-- example: postgresql -->
```sql
CREATE INDEX customer_score ON customer (score);
EXPLAIN SELECT id FROM customer WHERE score = 3;
SELECT count(*) FROM customer WHERE score = 3;
```

```text
CREATE INDEX
                       QUERY PLAN
--------------------------------------------------------
 scan customer: index customer_score lookup, index only
(1 row)

 count
-------
    30
(1 row)
```

### B. A unique index on an expression

<!-- example: postgresql -->
```sql
CREATE UNIQUE INDEX customer_email_lower ON customer (lower(email));
INSERT INTO customer (id, email) VALUES (302, 'ANN@example.com');
EXPLAIN SELECT id FROM customer WHERE lower(email) = 'ann@example.com';
```

```text
CREATE INDEX
ERROR:  duplicate key value violates unique constraint "customer_email_lower"
DETAIL:  Key (lower(email))=(ann@example.com) already exists.
                    QUERY PLAN
--------------------------------------------------
 scan customer: index customer_email_lower lookup
(1 row)
```

### C. A partial index, and a name chosen for it

<!-- example: postgresql -->
```sql
CREATE INDEX ON customer (joined) WHERE score IS NOT NULL;
CREATE INDEX ON customer (city, score DESC NULLS LAST);
SELECT indexname, indexdef FROM pg_indexes WHERE tablename = 'customer' ORDER BY indexname;
```

```text
CREATE INDEX
CREATE INDEX
        indexname        |                                              indexdef
-------------------------+----------------------------------------------------------------------------------------------------
 customer_city_score_idx | CREATE INDEX customer_city_score_idx ON public.customer USING btree (city, score DESC NULLS LAST)
 customer_email_lower    | CREATE UNIQUE INDEX customer_email_lower ON public.customer USING btree (lower(email))
 customer_joined_idx     | CREATE INDEX customer_joined_idx ON public.customer USING btree (joined) WHERE (score IS NOT NULL)
 customer_pkey           | CREATE UNIQUE INDEX customer_pkey ON public.customer USING btree (id)
 customer_score          | CREATE INDEX customer_score ON public.customer USING btree (score)
(5 rows)
```

### D. IF NOT EXISTS, and a rolled-back index

<!-- example: postgresql -->
```sql
CREATE INDEX IF NOT EXISTS customer_score ON customer (city);
BEGIN;
CREATE INDEX customer_city ON customer (city);
ROLLBACK;
SELECT count(*) FROM pg_indexes WHERE indexname = 'customer_city';
```

```text
NOTICE:  relation "customer_score" already exists, skipping
CREATE INDEX
BEGIN
CREATE INDEX
ROLLBACK
 count
-------
     0
(1 row)
```

### E. Errors

<!-- example: postgresql -->
```sql
CREATE INDEX customer_score ON customer (city);
CREATE INDEX customer_h ON customer USING hash (city);
CREATE INDEX customer_i ON customer (city) INCLUDE (score);
CREATE INDEX customer_x ON customer (nosuch);
CREATE UNIQUE INDEX customer_city_u ON customer (city);
```

```text
ERROR:  relation "customer_score" already exists
ERROR:  index method "hash" is not supported
ERROR:  syntax error at or near "include"
ERROR:  column "nosuch" does not exist
ERROR:  could not create unique index "customer_city_u"
DETAIL:  Key (city)=(hull) is duplicated.
```

## See also

[ALTER INDEX](alter-index.md) · [DROP INDEX](drop-index.md) · [CREATE TABLE](create-table.md) · EXPLAIN · ANALYZE
