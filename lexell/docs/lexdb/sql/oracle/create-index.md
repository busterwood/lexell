# CREATE INDEX

Creates an index on one or more columns, or on an expression.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
CREATE [ UNIQUE ] INDEX [ schema. ] index
    ON [ schema. ] table ( { column | expr } [ ASC | DESC ] [, { column | expr } [ ASC | DESC ] ]... )

ALTER INDEX [ schema. ] index RENAME TO new_name
```

## Arguments

`UNIQUE`
: Refuses two rows with the same key (ORA-00001). NULLs do not clash.

*column*, *expr*
: The key. An expression (`UPPER(name)`, `a + c`, `CASE WHEN ... END`) makes a function-based index. A key may be
  `DESC`.

## Remarks

- A query that matches the indexed expression can use the index; the optimiser decides.
- The dictionary lists the index in `USER_INDEXES`, its key in `USER_IND_COLUMNS` and the text of an expression in
  `USER_IND_EXPRESSIONS`. A function-based index shows a hidden column named `SYS_NCnnnnn$`.
- A unique index over rows that already clash is ORA-01452. An index name that is taken is ORA-00955.
- Constraints (`PRIMARY KEY`, `UNIQUE`) make their own indexes.
- A `CASE` expression over a column gives a unique index that covers some rows only.

## Differences from Oracle

- **Not supported (ORA-00900):** `BITMAP` indexes, `TABLESPACE`, `COMPRESS` and the other physical clauses.
- **`ALTER INDEX` takes only `RENAME TO`;** `REBUILD` and the others are ORA-03001.
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
ALTER INDEX ix_c2 REBUILD;
```

```text
ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-00900: invalid SQL statement

ERROR:
ORA-03001: unimplemented feature: lexdb: ALTER INDEX takes RENAME TO only
```

## See also

[DROP INDEX](drop-index.md), [CREATE TABLE](create-table.md), [Data dictionary views](README.md#data-dictionary)
