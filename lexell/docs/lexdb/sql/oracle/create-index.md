# CREATE INDEX

Creates an index on one or more columns, or on an expression.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE [ UNIQUE ] INDEX [ schema. ] index
    ON [ schema. ] table [ USING { btree | minmax | brin | set | bloom_filter | ngrambf | tokenbf } [ ( param [, ...] ) ] ]
    ( { column | expr } [ ASC | DESC ] [, { column | expr } [ ASC | DESC ] ]... )
    [ annotations_clause ]

CREATE SKIPPING INDEX [ IF NOT EXISTS ] [ schema. ] index
    ON [ schema. ] table ( column )
    [ USING { minmax | brin | set | bloom_filter | ngrambf | tokenbf } [ ( param [, ...] ) ] ]

DROP [ SKIPPING ] INDEX [ IF EXISTS ] [ schema. ] index

ALTER INDEX [ schema. ] index RENAME TO new_name
ALTER INDEX [ schema. ] index annotations_clause
ALTER INDEX [ schema. ] index { REBUILD [ ONLINE ] | COALESCE | PARALLEL | NOPARALLEL | LOGGING | NOLOGGING }

annotations_clause:
    ANNOTATIONS ( [ ADD [ IF NOT EXISTS ] | DROP [ IF EXISTS ] | REPLACE ] name [ 'value' ] [, ...] )
```

## Arguments

`UNIQUE`
: Refuses two rows with the same key (ORA-00001). NULLs do not clash.

*column*, *expr*
: The key. An expression (`UPPER(name)`, `a + c`, `CASE WHEN ... END`) makes a function-based index. A key may be
  `DESC`.

`ANNOTATIONS`
: Names, with or without a value, kept for the index and shown in `USER_ANNOTATIONS_USAGE` (`OBJECT_TYPE`
  `INDEX`). `CREATE INDEX` adds them, `ALTER INDEX` adds, drops and replaces them; they follow `ALTER INDEX ...
  RENAME TO` and go with `DROP INDEX`. A primary key's index takes them by the key's index name. See
  [annotations](annotations.md) and example G below.

## Remarks

- A query that matches the indexed expression can use the index; the optimiser decides.
- The dictionary lists the index in `USER_INDEXES`, its key in `USER_IND_COLUMNS` and the text of an expression in
  `USER_IND_EXPRESSIONS`. A function-based index shows a hidden column named `SYS_NCnnnnn$`.
- A unique index over rows that already clash is ORA-01452. An index name that is taken is ORA-00955.
- Constraints (`PRIMARY KEY`, `UNIQUE`) make their own indexes.
- A `CASE` expression over a column gives a unique index that covers some rows only.

## Differences from Oracle

- **Not supported (ORA-00900):** `BITMAP` indexes, `TABLESPACE`, `COMPRESS` and the other physical clauses.
- **`ALTER INDEX` changes only the name and the annotations.** `REBUILD [ONLINE]`, `COALESCE`, `[NO]PARALLEL` and
  `[NO]LOGGING` are accepted and do nothing (example H). `UNUSABLE` and the other clauses are ORA-03001, where
  Oracle marks the index unusable.
- An index on an expression that a virtual column's index already covers is accepted (Oracle: ORA-01408).

## Examples

<!--setup: oracle
CREATE TABLE ix (a NUMBER, b VARCHAR2(10), c NUMBER);
-->

The examples use a table `ix (a NUMBER, b VARCHAR2(10), c NUMBER)`.

### A. Indexes and their dictionary rows

<!-- example: oracle -->
```sql
CREATE INDEX ix_ab ON ix (a, b DESC);
CREATE UNIQUE INDEX ix_c ON ix (c);
CREATE INDEX ix_up ON ix (UPPER(b));
SELECT index_name, uniqueness FROM user_indexes WHERE table_name = 'IX' ORDER BY index_name;
SELECT index_name, column_name, column_position, descend FROM user_ind_columns
WHERE table_name = 'IX' ORDER BY index_name, column_position;
SELECT index_name, column_expression FROM user_ind_expressions WHERE table_name = 'IX';
```

```text
Index created.

Index created.

Index created.

INDEX_NAME UNIQUENESS
---------- ----------
IX_AB      NONUNIQUE
IX_C       UNIQUE
IX_UP      NONUNIQUE

3 rows selected.

INDEX_NAME COLUMN_NAME  COLUMN_POSITION DESCEND
---------- ------------ --------------- -------
IX_AB      A                          1 ASC
IX_AB      B                          2 DESC
IX_C       C                          1 ASC
IX_UP      SYS_NC00004$               1 ASC

4 rows selected.

INDEX_NAME COLUMN_EXPRESSION
---------- -----------------
IX_UP      UPPER("B")

1 row selected.
```

### B. A unique index

<!-- example: oracle -->
```sql
INSERT INTO ix VALUES (1, 'a', 1);
INSERT INTO ix VALUES (2, 'b', 1);
INSERT INTO ix VALUES (3, 'c', NULL);
INSERT INTO ix VALUES (4, 'd', NULL);
SELECT COUNT(*) AS rows_in_table FROM ix;
```

```text
1 row created.

ERROR:
ORA-00001: unique constraint (SA.IX_C) violated

1 row created.

1 row created.

ROWS_IN_TABLE
-------------
            3

1 row selected.
```

### C. Expressions

<!-- example: oracle -->
```sql
CREATE INDEX ix_f ON ix (a + c);
CREATE UNIQUE INDEX ix_partial ON ix (CASE WHEN a > 0 THEN a END);
SELECT index_name, column_expression FROM user_ind_expressions WHERE table_name = 'IX' ORDER BY index_name;
```

```text
Index created.

Index created.

INDEX_NAME COLUMN_EXPRESSION
---------- ----------------------------
IX_F       "A"+"C"
IX_PARTIAL CASE WHEN "A">0 THEN "A" END
IX_UP      UPPER("B")

3 rows selected.
```

### D. Rename an index

<!-- example: oracle -->
```sql
ALTER INDEX ix_c RENAME TO ix_c2;
SELECT index_name FROM user_indexes WHERE table_name = 'IX' ORDER BY index_name;
```

```text
Index altered.

INDEX_NAME
----------
IX_AB
IX_C2
IX_F
IX_PARTIAL
IX_UP

5 rows selected.
```

### E. Errors

<!-- example: oracle -->
```sql
CREATE INDEX ix_ab ON ix (a);
CREATE INDEX ix_bad ON ix (nothere);
```

```text
ERROR:
ORA-00955: name is already used by an existing object

ERROR:
ORA-00904: "NOTHERE": invalid identifier
```

### F. What lexdb does not take

<!-- example: oracle -->
```sql
CREATE BITMAP INDEX ix_bm ON ix (a);
CREATE INDEX ix_ab2 ON ix (a) TABLESPACE users;
CREATE INDEX ix_part ON ix (a) COMPRESS;
ALTER INDEX ix_c2 UNUSABLE;
```

```text
ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-03001: unimplemented feature: lexdb: ALTER INDEX takes RENAME TO, ANNOTATIONS, REBUILD, COALESCE, [NO]PARALLEL and [NO]LOGGING only
```

### G. Annotations

<!-- example: oracle -->
```sql
CREATE INDEX ix_b ON ix (b) ANNOTATIONS (Purpose 'lookup by b', Temporary);
ALTER INDEX ix_b ANNOTATIONS (DROP Temporary, ADD Owner 'ops');
ALTER INDEX ix_b RENAME TO ix_b2;
SELECT object_type, object_name, annotation_name, annotation_value FROM user_annotations_usage
WHERE object_type = 'INDEX' ORDER BY annotation_name;
ALTER INDEX ix_b2 ANNOTATIONS (ADD Owner 'ops');
```

```text
Index created.

Index altered.

Index altered.

OBJECT_TYPE OBJECT_NAME ANNOTATION_NAME ANNOTATION_VALUE
----------- ----------- --------------- ----------------
INDEX       IX_B2       OWNER           ops
INDEX       IX_B2       PURPOSE         lookup by b

2 rows selected.

ERROR:
ORA-11552: Provided annotation 'OWNER' already exists for the object 'IX_B2'.
```

### H. Maintenance clauses

`REBUILD`, `COALESCE` and the parallel and logging settings are accepted, as for an index that needs nothing done; an
index that does not exist is ORA-01418.

<!-- example: oracle -->
```sql
ALTER INDEX ix_c2 REBUILD;
ALTER INDEX ix_c2 REBUILD ONLINE;
ALTER INDEX ix_c2 COALESCE;
ALTER INDEX ix_c2 NOPARALLEL;
ALTER INDEX ix_c2 LOGGING;
ALTER INDEX nothere REBUILD;
```

```text
Index altered.

Index altered.

Index altered.

Index altered.

Index altered.

ERROR:
ORA-01418: specified index does not exist
```

### I. Data skipping indexes

lexdb also supports hierarchical B+tree data skipping indexes (`minmax`/`brin`, `set`, `bloom_filter`, `ngrambf`, `tokenbf`) to prune subtrees on analytical equality, `IN`, range, and substring `LIKE` filters with zero OLTP write-path maintenance. Toggle pruning with `SET data_skipping_enabled = on | off`.

<!-- example: oracle -->
```sql
CREATE SKIPPING INDEX ix_b_ng ON ix (b) USING ngrambf(3, 1024, 3);
SELECT COUNT(*) AS hits FROM ix WHERE b LIKE '%a%';
DROP SKIPPING INDEX ix_b_ng;
```

```text
Index created.

HITS
----
   1

1 row selected.

Index dropped.
```

## See also

[DROP INDEX](drop-index.md), [CREATE TABLE](create-table.md), [Data dictionary views](README.md#data-dictionary),
[Annotations](annotations.md)
