# GRAPH_TABLE

Finds the vertices and edges of a property graph that match a pattern, in the `FROM` clause of a
[SELECT](select.md), and returns a row for each match (SQL/PGQ).

**Door:** PostgreSQL. **Follows:** SQL:2023 property graph queries (SQL/PGQ, ISO/IEC 9075-16). PostgreSQL 18 has no
`GRAPH_TABLE`; lexdb adds it to this door with PostgreSQL's identifier folding, types, expressions, `$n` parameters and
SQLSTATEs.

## Syntax

```
GRAPH_TABLE ( [ schema. ] graph
    MATCH path_pattern [, path_pattern ]...
    [ WHERE condition ]
    [ ONE ROW PER MATCH ]
    COLUMNS ( { expression [ AS name ] | variable.* } [, ...] )
) [ [ AS ] alias [ ( column_alias [, ...] ) ] ]

path_pattern:
    vertex_pattern [ { edge_pattern [ quantifier ] | ( edge_pattern vertex_pattern [ ... ] ) quantifier } vertex_pattern ]...

vertex_pattern:
    ( [ variable ] [ IS label_expression ] [ WHERE condition ] )

edge_pattern:
    -[ [ variable ] [ IS label_expression ] [ WHERE condition ] ]->      source to destination
    <-[ [ variable ] [ IS label_expression ] [ WHERE condition ] ]-      destination to source
    -[ [ variable ] [ IS label_expression ] [ WHERE condition ] ]-       either way
    ->  |  <-  |  -                                                      any edge, without a variable

label_expression:
    label [ { '|' | '&' } label ]...

quantifier:
    { n } | { m, n } | { , n }
```

## Arguments

*graph*
: A property graph made by [CREATE PROPERTY GRAPH](create-property-graph.md), optionally schema-qualified. One that
  does not exist is 42704.

`MATCH` *path_pattern*
: Vertices and the edges between them. A vertex pattern in parentheses binds its variable to one vertex: a row of a
  vertex table of the graph. An edge pattern binds its variable to one edge, a row of an edge table, whose two ends are
  the vertices on its left and right. Several path patterns, separated by commas, are matched together: a variable
  they share is the same element in each, and patterns that share none give every combination of their matches.

*variable*
: The name the pattern's columns and conditions use for the element (`a.name`). A pattern may leave it out. The same
  variable twice in a pattern is one element: `(a) -> (b) -> (a)` is a cycle back to `a`. A vertex and an edge of the
  same name are 42P10.

`IS` *label_expression*
: The labels the element must have. `person|company` is either, `person&manager` both. Without `IS` the element may be
  of any table. A label the graph does not have is 42704; `!` (not) is 0A000.

`WHERE` *condition*
: Inside a vertex or edge pattern, a condition on that element (`(a IS person WHERE a.city = 'Oslo')`); after the path
  patterns, a condition on all of them. Besides properties and PostgreSQL expressions, it may test:
  - *variable* `IS [ NOT ] LABELED` *label*: whether the element has the label;
  - *vertex* `IS [ NOT ] SOURCE OF` *edge* and `IS [ NOT ] DESTINATION OF` *edge*: which end of the edge the vertex is,
    useful with an edge matched either way;
  - `VERTEX_ID(v) = VERTEX_ID(w)`: whether two variables are the same element.

`->`, `<-`, `-`, and the arrows around `[ ... ]`
: `-[e]->` goes from the edge's source to its destination, `<-[e]-` the other way, and `-[e]-` either way: each edge
  is matched once in each direction, so a pattern `(a) -[e]- (b)` gives both `(x, y)` and `(y, x)`. An edge from a
  vertex to itself is matched once. `->`, `<-` and `-` are the same without a variable or label: any edge.

*quantifier*
: The number of edges of a path: `{n}` exactly *n*, `{m,n}` from *m* to *n*, `{,n}` from 0 to *n*. It follows an edge
  pattern (`-[k IS knows]->{1,3}`) or a parenthesized path of edges and vertices (`(-[k]-> (m)){1,2}`). Zero edges is a
  path from a vertex to itself. A path may use an edge more than once. Only bounded quantifiers exist: `+`, `*` and `?`
  are 0A000, `{m,}`, `{0}`, `{3,1}` and a quantifier after a vertex pattern are 42601.

`ONE ROW PER MATCH`
: The default, and the only form lexdb has: one row for each match.

`COLUMNS (` ... `)`
: The columns of the result:
  - *variable*`.`*property*, alone (the column is named after the property) or in any expression with `AS`: functions,
    `CASE`, casts, arithmetic. An expression without `AS` is 42601, and two columns of one name are 42702.
  - *variable*`.*`: every property of the variable's labels, in the order the labels have them.
  - `VERTEX_ID(v)` and `EDGE_ID(e)`: the element's identity (graph, element table, key value) as JSON text.
  - `MATCHNUM()`: a number for each match.
  - aggregates of a quantified variable: `count`, `sum`, `min`, `max`, `avg`, `string_agg(x, separator)` and
    `listagg(x [, separator])` over the elements of the path, in its order (`count(k.since)` is the path's length,
    `string_agg(m.name, ',')` the vertices it passes).

*alias* [ `(` *column_alias* `, ... )` ]
: Optional name for the result, with or without `AS`, and optional column aliases (`) AS g (src, dst)`).

## Remarks

- A variable reads the properties of its labels. Without `IS`, or with `|`, it may be bound to elements of several
  tables: it reads the properties of all their labels, and a property the bound element's labels do not have is NULL
  (`e.since` of a `works_at` edge, example D). A property no label of the graph has, one the variable's labels do not
  have, or a label expression no element satisfies is 42703.
- A quantified edge's variable stands for several edges: it may be used only inside an aggregate in `COLUMNS` (42P10
  elsewhere in `COLUMNS` or in the pattern's `WHERE`), and an aggregate must reference one (42P10, `count(*)` too).
  `count(e)` without a property is 42601.
- No subquery inside `GRAPH_TABLE` (0A000), and no column of the query around it (42704): join the result instead
  (example F).
- Protocol bind parameters (`$1`, `$2`, ...) work in the conditions and `COLUMNS`, and parameter type inference sees
  them (`WHERE a.id = $1` infers `integer`).
- `GRAPH_TABLE` is a `FROM` item. It may be joined with tables, used in a subquery, a `WITH` query, an `EXPLAIN` or a
  view, and its rows grouped, ordered and filtered as any others. The rows come in no particular order: use `ORDER BY`.
- lexdb rewrites `GRAPH_TABLE` as SQL before planning: the joins of the element tables on the graph's keys, one for
  each way the pattern's variables can be bound to tables and each length of its quantifiers, and the `UNION ALL` of
  them. A query of `GRAPH_TABLE` alone is flattened into the underlying join.
- Unquoted names fold to lower case, and double-quoted names keep their case, as elsewhere in the PostgreSQL door.

## Differences from the standard

- `ONE ROW PER VERTEX` and `ONE ROW PER STEP` (and `ELEMENT_NUMBER`) are not supported (0A000; `ELEMENT_NUMBER` alone
  is 42P10).
- Unbounded quantifiers (`*`, `+`, `{m,}`) and `?` are not supported (0A000 / 42601); use a bounded `{m,n}` quantifier.
- `DISTINCT` inside a quantified aggregate and `WITHIN GROUP` / `OVER` after one are not supported (0A000).
- A pattern that expands to more than 4,096 joins is refused (0A000).
- `VERTEX_ID` and `EDGE_ID` return JSON text (`text`), as lexdb has no `json` type.
- The [Oracle](../oracle/graph-table.md) and [SQL Server](../tsql/graph-table.md) doors have the same `GRAPH_TABLE`
  operator.

## Examples

<!-- setup: postgresql
CREATE TABLE people (id int PRIMARY KEY, name text, city text);
CREATE TABLE companies (id int PRIMARY KEY, name text, city text);
CREATE TABLE knows (id int PRIMARY KEY, src int REFERENCES people (id), dst int REFERENCES people (id), since int);
CREATE TABLE works_at (pid int REFERENCES people (id), cid int REFERENCES companies (id), role text, PRIMARY KEY (pid, cid));
INSERT INTO people VALUES (1, 'Ann', 'Oslo'), (2, 'Bob', 'Rome'), (3, 'Cid', 'Oslo'), (4, 'Dee', 'Pisa');
INSERT INTO companies VALUES (10, 'Acme', 'Oslo'), (11, 'Bolt', 'Rome');
INSERT INTO knows VALUES (100, 1, 2, 2010), (101, 2, 3, 2012), (102, 3, 4, 2015), (103, 1, 3, 2018);
INSERT INTO works_at VALUES (1, 10, 'dev'), (2, 10, 'ops'), (3, 11, 'dev');
CREATE PROPERTY GRAPH social
  VERTEX TABLES (
    people KEY (id) LABEL person PROPERTIES (id, name, city),
    companies KEY (id) LABEL company PROPERTIES (id, name, city)
  )
  EDGE TABLES (
    knows SOURCE KEY (src) REFERENCES people (id) DESTINATION KEY (dst) REFERENCES people (id)
      LABEL knows PROPERTIES (id, since),
    works_at SOURCE KEY (pid) REFERENCES people (id) DESTINATION KEY (cid) REFERENCES companies (id)
      LABEL works_at PROPERTIES (role)
  );
-->

The examples use the `social` graph: four people (`Ann`, `Bob`, `Cid`, `Dee`), two companies (`Acme`, `Bolt`), four
`knows` edges and three `works_at` edges.

```sql
CREATE PROPERTY GRAPH social
  VERTEX TABLES (
    people KEY (id) LABEL person PROPERTIES (id, name, city),
    companies KEY (id) LABEL company PROPERTIES (id, name, city)
  )
  EDGE TABLES (
    knows SOURCE KEY (src) REFERENCES people (id) DESTINATION KEY (dst) REFERENCES people (id)
      LABEL knows PROPERTIES (id, since),
    works_at SOURCE KEY (pid) REFERENCES people (id) DESTINATION KEY (cid) REFERENCES companies (id)
      LABEL works_at PROPERTIES (role)
  );
```

### A. One hop and two hops

<!-- example: postgresql -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person) -[k IS knows]-> (b IS person)
  COLUMNS (a.name AS who, b.name AS knows, k.since)
) ORDER BY who, knows;

SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person) -> (b IS person) -> (c IS person)
  COLUMNS (a.name AS from_p, b.name AS via, c.name AS to_p)
) ORDER BY from_p, via, to_p;
```

```text
 who | knows | since
-----+-------+-------
 Ann | Bob   |  2010
 Ann | Cid   |  2018
 Bob | Cid   |  2012
 Cid | Dee   |  2015
(4 rows)

 from_p | via | to_p
--------+-----+------
 Ann    | Bob | Cid
 Ann    | Cid | Dee
 Bob    | Cid | Dee
(3 rows)
```

### B. Bounded paths and quantified aggregates

<!-- example: postgresql -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Ann') (-[k IS knows]-> (m IS person)){1,3}
  COLUMNS (
    a.name AS start_p,
    count(k.id) AS hops,
    sum(k.since) AS sum_since,
    string_agg(m.name, ' -> ') AS path
  )
) ORDER BY hops, path;
```

```text
 start_p | hops | sum_since |       path
---------+------+-----------+-------------------
 Ann     |    1 |      2010 | Bob
 Ann     |    1 |      2018 | Cid
 Ann     |    2 |      4022 | Bob -> Cid
 Ann     |    2 |      4033 | Cid -> Dee
 Ann     |    3 |      6037 | Bob -> Cid -> Dee
(5 rows)
```

### C. Undirected edges, `IS SOURCE OF` and `IS LABELED`

<!-- example: postgresql -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Bob') -[k IS knows]- (b IS person)
  COLUMNS (
    a.name AS a,
    b.name AS b,
    CASE WHEN a IS SOURCE OF k THEN 'out' ELSE 'in' END AS dir
  )
) ORDER BY dir, b;
```

```text
  a  |  b  | dir
-----+-----+-----
 Bob | Ann | in
 Bob | Cid | out
(2 rows)
```

### D. Label disjunction and heterogeneous properties

Without `IS` (or with `|`), a variable may bind to multiple element tables; properties absent on the bound table are
NULL.

<!-- example: postgresql -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (a IS person WHERE a.name = 'Ann') -[e]-> (b IS person|company)
  COLUMNS (
    a.name AS src,
    b.name AS dst,
    CASE WHEN b IS LABELED company THEN 'company' ELSE 'person' END AS kind,
    e.since,
    e.role
  )
) ORDER BY kind, dst;
```

```text
 src | dst  |  kind   | since | role
-----+------+---------+-------+------
 Ann | Acme | company |       | dev
 Ann | Bob  | person  |  2010 |
 Ann | Cid  | person  |  2018 |
(3 rows)
```

### E. `AS` alias, column aliases and `MATCHNUM()`

<!-- example: postgresql -->
```sql
SELECT g.num, g.p1, g.p2
FROM GRAPH_TABLE (social
  MATCH (a IS person) -[k IS knows]-> (b IS person)
  ONE ROW PER MATCH
  COLUMNS (matchnum() AS n, a.name AS a, b.name AS b)
) AS g (num, p1, p2)
ORDER BY g.p1, g.p2;
```

```text
 num | p1  | p2
-----+-----+-----
   1 | Ann | Bob
   2 | Ann | Cid
   3 | Bob | Cid
   4 | Cid | Dee
(4 rows)
```

### F. `VERTEX_ID` and joining `GRAPH_TABLE` with a table

<!-- example: postgresql -->
```sql
SELECT * FROM GRAPH_TABLE (social
  MATCH (p IS person WHERE p.name = 'Ann')
  COLUMNS (p.name, vertex_id(p) AS vid)
);

SELECT c.city, count(*) AS staff
FROM GRAPH_TABLE (social
  MATCH (p IS person) -[w IS works_at]-> (c IS company)
  COLUMNS (c.id AS cid, p.id AS pid)
) AS g
JOIN companies c ON c.id = g.cid
GROUP BY c.city
ORDER BY c.city;
```

```text
 name |                                            vid
------+-------------------------------------------------------------------------------------------
 Ann  | {"GRAPH_OWNER":"public","GRAPH_NAME":"social","ELEM_TABLE":"people","KEY_VALUE":{"id":1}}
(1 row)

 city | staff
------+-------
 Oslo |     2
 Rome |     1
(2 rows)
```

## See also

[CREATE PROPERTY GRAPH](create-property-graph.md) · [DROP PROPERTY GRAPH](drop-property-graph.md) ·
[SELECT](select.md) · [MATCH_RECOGNIZE](match-recognize.md)
