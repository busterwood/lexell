# GRAPH_TABLE (Transact-SQL)

Finds the vertices and edges of a property graph that match a pattern, in the `FROM` clause of a
[SELECT](select.md), and returns a row for each match (SQL/PGQ).

**Door:** SQL Server (TDS). **Follows:** SQL:2023 property graph queries (SQL/PGQ, ISO/IEC 9075-16). SQL Server has no
`GRAPH_TABLE`; lexdb adds the standard operator to this door with SQL Server's case-insensitive identifiers, `[bracket]`
quoting, `dbo` default schema, `@variable` parameters, expressions, and error numbers.

## Syntax

```
GRAPH_TABLE ( [ schema_name . ] graph_name
    MATCH path_pattern [ ,...n ]
    [ WHERE search_condition ]
    [ ONE ROW PER MATCH ]
    COLUMNS ( { expression [ AS column_name ] | variable.* } [ ,...n ] )
) [ [ AS ] table_alias [ ( column_alias [ ,...n ] ) ] ]

path_pattern ::=
    vertex_pattern [ { edge_pattern [ quantifier ] | ( edge_pattern vertex_pattern [ ... ] ) quantifier } vertex_pattern ]...

vertex_pattern ::=
    ( [ variable ] [ IS label_expression ] [ WHERE search_condition ] )

edge_pattern ::=
    -[ [ variable ] [ IS label_expression ] [ WHERE search_condition ] ]->      source to destination
    <-[ [ variable ] [ IS label_expression ] [ WHERE search_condition ] ]-      destination to source
    -[ [ variable ] [ IS label_expression ] [ WHERE search_condition ] ]-       either way
    ->  |  <-  |  -                                                             any edge, without a variable

label_expression ::=
    label_name [ { '|' | '&' } label_name ]...

quantifier ::=
    { n } | { m, n } | { , n }
```

## Arguments

*graph_name*
: A property graph made by [CREATE PROPERTY GRAPH](create-property-graph.md), optionally schema-qualified
  (`dbo.social`). One that does not exist is error 208 (`Invalid object name`).

`MATCH` *path_pattern*
: Vertices and the edges between them. A vertex pattern in parentheses binds its variable to one vertex: a row of a
  vertex table of the graph. An edge pattern binds its variable to one edge, a row of an edge table, whose two ends are
  the vertices on its left and right. Several path patterns, separated by commas, are matched together: a variable
  they share is the same element in each, and patterns that share none give every combination of their matches.

*variable*
: The name the pattern's columns and conditions use for the element (`a.name`). A pattern may leave it out. The same
  variable twice in a pattern is one element: `(a) -> (b) -> (a)` is a cycle back to `a`. A vertex and an edge of the
  same name are error 50000.

`IS` *label_expression*
: The labels the element must have. `person|company` is either, `person&manager` both. Without `IS` the element may be
  of any table. A label the graph does not have is error 50000; `!` (not) is error 50000.

`WHERE` *search_condition*
: Inside a vertex or edge pattern, a condition on that element (`(a IS person WHERE a.city = N'Oslo')`); after the path
  patterns, a condition on all of them. Besides properties and T-SQL expressions (including `@variables`), it may test:
  - *variable* `IS [ NOT ] LABELED` *label_name*: whether the element has the label;
  - *vertex* `IS [ NOT ] SOURCE OF` *edge* and `IS [ NOT ] DESTINATION OF` *edge*: which end of the edge the vertex is,
    useful with an edge matched either way;
  - `VERTEX_ID(v) = VERTEX_ID(w)`: whether two variables are the same element.

`->`, `<-`, `-`, and the arrows around `[ ... ]`
: `-[e]->` goes from the edge's source to its destination, `<-[e]-` the other way, and `-[e]-` either way: each edge
  is matched once in each direction, so a pattern `(a) -[e]- (b)` gives both `(x, y)` and `(y, x)`. An edge from a
  vertex to itself is matched once. `->`, `<-` and `-` are the same without a variable or label: any edge. Inside
  `MATCH`, `-[ ... ]-` uses brackets as edge delimiters; `[column]` bracketed identifiers still work inside `WHERE`
  and `COLUMNS`.

*quantifier*
: The number of edges of a path: `{n}` exactly *n*, `{m,n}` from *m* to *n*, `{,n}` from 0 to *n*. It follows an edge
  pattern (`-[k IS knows]->{1,3}`) or a parenthesized path of edges and vertices (`(-[k]-> (m)){1,2}`). Zero edges is a
  path from a vertex to itself. A path may use an edge more than once. Only bounded quantifiers exist: `+`, `*` and `?`
  are error 50000; `{m,}`, `{0}`, `{3,1}` and a quantifier after a vertex pattern are error 102.

`ONE ROW PER MATCH`
: The default, and the only form lexdb has: one row for each match.

`COLUMNS (` ... `)`
: The columns of the result:
  - *variable*`.`*property*, alone (the column is named after the property) or in any expression with `AS`: functions,
    `CASE`, `CAST`/`CONVERT`, arithmetic. An expression without `AS` is error 102, and two columns of one name are
    error 50000.
  - *variable*`.*`: every property of the variable's labels, in the order the labels have them.
  - `VERTEX_ID(v)` and `EDGE_ID(e)`: the element's identity (graph, element table, key value) as JSON text.
  - `MATCHNUM()`: a number for each match.
  - aggregates of a quantified variable: `COUNT`, `SUM`, `MIN`, `MAX`, `AVG`, `STRING_AGG(x, separator)` and
    `LISTAGG(x [, separator])` over the elements of the path, in its order (`COUNT(k.since)` is the path's length,
    `STRING_AGG(m.name, ',')` the vertices it passes).

*table_alias* [ `(` *column_alias* `, ... )` ]
: Optional name for the result, with or without `AS`, and optional column aliases (`) AS g (src, dst)`).

## Remarks

- A variable reads the properties of its labels. Without `IS`, or with `|`, it may be bound to elements of several
  tables: it reads the properties of all their labels, and a property the bound element's labels do not have is NULL
  (`e.since` of a `works_at` edge, example D). A property no label of the graph has, one the variable's labels do not
  have, or a label expression no element satisfies is error 207.
- A quantified edge's variable stands for several edges: it may be used only inside an aggregate in `COLUMNS` (error
  50000 elsewhere in `COLUMNS` or in the pattern's `WHERE`), and an aggregate must reference one (error 50000,
  `COUNT(*)` too). `COUNT(e)` without a property is error 102.
- No subquery inside `GRAPH_TABLE` (error 50000), and no column of the query around it (error 50000): join the result
  instead (example F).
- T-SQL local variables (`@x`) and `sp_executesql` parameters work in the conditions and `COLUMNS` (example G). An
  undeclared variable is error 137.
- `GRAPH_TABLE` is a `FROM` table source. It may be joined with tables, used in a subquery, a `WITH` query, `TOP`, or a
  view, and its rows grouped, ordered and filtered as any others. The rows come in no particular order: use `ORDER BY`.
- lexdb rewrites `GRAPH_TABLE` as SQL before planning: the joins of the element tables on the graph's keys, one for
  each way the pattern's variables can be bound to tables and each length of its quantifiers, and the `UNION ALL` of
  them. A query of `GRAPH_TABLE` alone is flattened into the underlying join.
- Identifiers (graph names, labels, variables and property names) are matched without regard to case, as elsewhere in
  the SQL Server door.

## Differences from SQL Server and the standard

- `ONE ROW PER VERTEX` and `ONE ROW PER STEP` (and `ELEMENT_NUMBER`) are not supported (error 50000).
- Unbounded quantifiers (`*`, `+`, `{m,}`) and `?` are not supported (error 50000 / 102); use a bounded `{m,n}`
  quantifier.
- `DISTINCT` inside a quantified aggregate and `WITHIN GROUP` / `OVER` after one are not supported (error 50000).
- A pattern that expands to more than 4,096 joins is refused (error 50000).
- `VERTEX_ID` and `EDGE_ID` return JSON text (`nvarchar(max)`).
- The [PostgreSQL](../postgresql/graph-table.md) and [Oracle](../oracle/graph-table.md) doors have the same
  `GRAPH_TABLE` operator.

## Examples

<!--setup: tsql
CREATE TABLE dbo.people (id int PRIMARY KEY, name nvarchar(30), city nvarchar(30));
CREATE TABLE dbo.companies (id int PRIMARY KEY, name nvarchar(30), city nvarchar(30));
CREATE TABLE dbo.knows (id int PRIMARY KEY, src int REFERENCES dbo.people (id), dst int REFERENCES dbo.people (id), since int);
CREATE TABLE dbo.works_at (pid int REFERENCES dbo.people (id), cid int REFERENCES dbo.companies (id), role nvarchar(20), PRIMARY KEY (pid, cid));
INSERT dbo.people VALUES (1, N'Ann', N'Oslo'), (2, N'Bob', N'Rome'), (3, N'Cid', N'Oslo'), (4, N'Dee', N'Pisa');
INSERT dbo.companies VALUES (10, N'Acme', N'Oslo'), (11, N'Bolt', N'Rome');
INSERT dbo.knows VALUES (100, 1, 2, 2010), (101, 2, 3, 2012), (102, 3, 4, 2015), (103, 1, 3, 2018);
INSERT dbo.works_at VALUES (1, 10, N'dev'), (2, 10, N'ops'), (3, 11, N'dev');
CREATE PROPERTY GRAPH dbo.social
  VERTEX TABLES (
    dbo.people KEY (id) LABEL person PROPERTIES (id, name, city),
    dbo.companies KEY (id) LABEL company PROPERTIES (id, name, city)
  )
  EDGE TABLES (
    dbo.knows SOURCE KEY (src) REFERENCES people (id) DESTINATION KEY (dst) REFERENCES people (id)
      LABEL knows PROPERTIES (id, since),
    dbo.works_at SOURCE KEY (pid) REFERENCES people (id) DESTINATION KEY (cid) REFERENCES companies (id)
      LABEL works_at PROPERTIES (role)
  );
-->

The examples use the `dbo.social` graph: four people (`Ann`, `Bob`, `Cid`, `Dee`), two companies (`Acme`, `Bolt`), four
`knows` edges and three `works_at` edges.

```sql
CREATE PROPERTY GRAPH dbo.social
  VERTEX TABLES (
    dbo.people KEY (id) LABEL person PROPERTIES (id, name, city),
    dbo.companies KEY (id) LABEL company PROPERTIES (id, name, city)
  )
  EDGE TABLES (
    dbo.knows SOURCE KEY (src) REFERENCES people (id) DESTINATION KEY (dst) REFERENCES people (id)
      LABEL knows PROPERTIES (id, since),
    dbo.works_at SOURCE KEY (pid) REFERENCES people (id) DESTINATION KEY (cid) REFERENCES companies (id)
      LABEL works_at PROPERTIES (role)
  );
```

### A. One hop and two hops

<!-- example: tsql -->
```sql
SELECT * FROM GRAPH_TABLE (dbo.social
  MATCH (a IS person) -[k IS knows]-> (b IS person)
  COLUMNS (a.name AS who, b.name AS knows, k.since)
) ORDER BY who, knows;

SELECT * FROM GRAPH_TABLE (dbo.social
  MATCH (a IS person) -> (b IS person) -> (c IS person)
  COLUMNS (a.name AS from_p, b.name AS via, c.name AS to_p)
) ORDER BY from_p, via, to_p;
```

```text
who knows since
--- ----- -----
Ann Bob   2010
Ann Cid   2018
Bob Cid   2012
Cid Dee   2015

(4 rows affected)

from_p via to_p
------ --- ----
Ann    Bob Cid
Ann    Cid Dee
Bob    Cid Dee

(3 rows affected)
```

### B. Bounded paths and quantified aggregates

<!-- example: tsql -->
```sql
SELECT * FROM GRAPH_TABLE (dbo.social
  MATCH (a IS person WHERE a.name = N'Ann') (-[k IS knows]-> (m IS person)){1,3}
  COLUMNS (
    a.name AS start_p,
    COUNT(k.id) AS hops,
    SUM(k.since) AS sum_since,
    STRING_AGG(m.name, ' -> ') AS path
  )
) ORDER BY hops, path;
```

```text
start_p hops sum_since path
------- ---- --------- -----------------
Ann     1    2010      Bob
Ann     1    2018      Cid
Ann     2    4022      Bob -> Cid
Ann     2    4033      Cid -> Dee
Ann     3    6037      Bob -> Cid -> Dee

(5 rows affected)
```

### C. Undirected edges and `IS SOURCE OF`

<!-- example: tsql -->
```sql
SELECT * FROM GRAPH_TABLE (dbo.social
  MATCH (a IS person WHERE a.name = N'Bob') -[k IS knows]- (b IS person)
  COLUMNS (
    a.name AS a,
    b.name AS b,
    CASE WHEN a IS SOURCE OF k THEN 'out' ELSE 'in' END AS dir
  )
) ORDER BY dir, b;
```

```text
a   b   dir
--- --- ---
Bob Ann in
Bob Cid out

(2 rows affected)
```

### D. Label disjunction and heterogeneous properties

Without `IS` (or with `|`), a variable may bind to multiple element tables; properties absent on the bound table are
NULL.

<!-- example: tsql -->
```sql
SELECT * FROM GRAPH_TABLE (dbo.social
  MATCH (a IS person WHERE a.name = N'Ann') -[e]-> (b IS person|company)
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
src dst  kind    since role
--- ---- ------- ----- ----
Ann Acme company NULL  dev
Ann Bob  person  2010  NULL
Ann Cid  person  2018  NULL

(3 rows affected)
```

### E. `AS` alias, column aliases and `MATCHNUM()`

<!-- example: tsql -->
```sql
SELECT g.num, g.p1, g.p2
FROM GRAPH_TABLE (dbo.social
  MATCH (a IS person) -[k IS knows]-> (b IS person)
  ONE ROW PER MATCH
  COLUMNS (MATCHNUM() AS n, a.name AS a, b.name AS b)
) AS g (num, p1, p2)
ORDER BY g.p1, g.p2;
```

```text
num p1  p2
--- --- ---
1   Ann Bob
2   Ann Cid
3   Bob Cid
4   Cid Dee

(4 rows affected)
```

### F. `VERTEX_ID` and joining `GRAPH_TABLE` with a table

<!-- example: tsql -->
```sql
SELECT * FROM GRAPH_TABLE (dbo.social
  MATCH (p IS person WHERE p.name = N'Ann')
  COLUMNS (p.name, VERTEX_ID(p) AS vid)
);

SELECT c.city, COUNT(*) AS staff
FROM GRAPH_TABLE (dbo.social
  MATCH (p IS person) -[w IS works_at]-> (c IS company)
  COLUMNS (c.id AS cid, p.id AS pid)
) AS g
JOIN dbo.companies c ON c.id = g.cid
GROUP BY c.city
ORDER BY c.city;
```

```text
name vid
---- --------------------------------------------------------------------------------------
Ann  {"GRAPH_OWNER":"dbo","GRAPH_NAME":"social","ELEM_TABLE":"people","KEY_VALUE":{"id":1}}

(1 row affected)

city staff
---- -----
Oslo 2
Rome 1

(2 rows affected)
```

### G. Local variables and `sp_executesql`

<!-- example: tsql -->
```sql
DECLARE @city nvarchar(30) = N'Oslo';
SELECT * FROM GRAPH_TABLE (dbo.social
  MATCH (p IS person WHERE p.city = @city) -[w IS works_at]-> (c IS company)
  COLUMNS (p.name AS person, c.name AS company, w.role)
) ORDER BY person;
GO
EXEC sp_executesql
  N'SELECT * FROM GRAPH_TABLE (dbo.social MATCH (a IS person) -[k IS knows]-> (b IS person) WHERE a.id = @id COLUMNS (a.name AS who, b.name AS knows)) ORDER BY knows',
  N'@id int',
  @id = 1;
```

```text
person company role
------ ------- ----
Ann    Acme    dev
Cid    Bolt    dev

(2 rows affected)

who knows
--- -----
Ann Bob
Ann Cid

(2 rows affected)
```

## See also

[CREATE PROPERTY GRAPH](create-property-graph.md) · [DROP PROPERTY GRAPH](drop-property-graph.md) ·
[SELECT](select.md) · [FROM, JOIN and APPLY](from.md)
