# INSERT

Adds rows to a table.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
INSERT INTO [ schema. ] table [ t_alias ] [ ( column [, column ]... ) ]
    { VALUES ( { expr | DEFAULT } [, ...] ) [, ( ... ) ]...
    | subquery
    | [ WITH ... ] subquery }
    [ returning_clause ]

-- 26ai
INSERT INTO [ schema. ] table [ t_alias ]
    SET column = { expr | DEFAULT } [, column = ... ]...
    [ returning_clause ]

INSERT INTO [ schema. ] table [ t_alias ] [ ( column [, ...] ) ]
    BY { NAME | POSITION } subquery

returning_clause:
    { RETURN | RETURNING } [ OLD | NEW ] expr [, [ OLD | NEW ] expr ]...
        INTO data_item [, data_item ]...
```

## Arguments

*schema*
: The schema (user) that owns the table. Without it, the session's current schema: the login user, or the one
  `ALTER SESSION SET CURRENT_SCHEMA` set. Tables of the PostgreSQL door's `public` schema are `PUBLIC.table`.

*t_alias*
: A name for the table in the `RETURNING` clause.

*column*
: The columns the values go to, in order. A column left out gets its `DEFAULT`, or NULL.

`VALUES`
: One row, or several rows separated by commas (23ai's table value constructor). `DEFAULT` gives a column its
  default.

*subquery*
: A query whose rows are inserted, optionally with a `WITH` clause.

`SET` (26ai)
: The values by column name, as an `UPDATE` writes them.

`BY NAME` / `BY POSITION` (26ai)
: Match the subquery's columns to the table's by name or by position.

*returning_clause*
: Returns values of the inserted row into bind variables (from a client) or PL/SQL variables. `OLD` and
  `NEW` (23ai) name the row before and after; in an `INSERT`, `OLD` is NULL.

## Remarks

- The empty string is NULL, as in Oracle: inserting `''` into a `NOT NULL` column is ORA-01400.
- A value is converted to its column's type: a `NUMBER(p,s)` rounds to s places and is ORA-01438 when it does not
  fit; a string too long for `VARCHAR2(n)` is ORA-12899. A `DATE` keeps a time of day.
- A column's `DEFAULT ON NULL` is used when the value given is NULL. Identity columns (`GENERATED ... AS IDENTITY`)
  and sequences (`seq.NEXTVAL`) give keys.
- Constraint errors: ORA-00001 (unique), ORA-01400 (NULL), ORA-02290 (CHECK), ORA-02291 (no parent key).
- The first `INSERT` begins a transaction, which `COMMIT` or `ROLLBACK` ends. A failed statement is undone alone; the
  transaction and the rows of earlier statements stay.
- Many rows go fastest as one statement with an array of binds (JDBC `executeBatch`, python-oracledb
  `executemany`): see [bulk loading](../../bulk-load.md#oracle-array-dml).
- On a replica, `INSERT` into a table is ORA-16000; global temporary tables can be used there.

## Differences from Oracle

- Multitable inserts (`INSERT ALL`, `INSERT FIRST`) are not supported.
- `RETURNING` is not taken after an `INSERT ... SELECT` (ORA-03049), nor in Oracle. `RETURNING ... BULK COLLECT
  INTO` is not supported (PL/SQL collections are not).
- Error logging (`LOG ERRORS INTO`), hints (`/*+ APPEND */` is read as a comment), partitions and `INSERT INTO`
  a subquery or a view are not supported.
- Error texts are shorter than Oracle's: ORA-02290 names no constraint (Oracle: `check constraint (SA.SYS_C008)
  violated`), ORA-12899 names no column and no lengths, and ORA-00001 names lexdb's constraint (`SA.PRODUCT_PKEY`)
  where Oracle names its own (`SA.SYS_C008`, unless the constraint was named).

## Examples

<!--setup: oracle
CREATE TABLE product (id NUMBER(6) PRIMARY KEY, name VARCHAR2(40) NOT NULL, price NUMBER(10,2) DEFAULT 0 CHECK (price >= 0), stock NUMBER DEFAULT 0);
-->

### A. Insert one row, and several rows

<!-- example: oracle -->
```sql
INSERT INTO product VALUES (1, 'pencil', 0.50, 100);
INSERT INTO product (id, name, price) VALUES (2, 'eraser', 0.75), (3, 'ruler', 1.20);
SELECT * FROM product ORDER BY id;
```

```text
1 row created.

2 rows created.

ID NAME   PRICE STOCK
-- ------ ----- -----
 1 pencil   0.5   100
 2 eraser  0.75     0
 3 ruler    1.2     0

3 rows selected.
```

### B. Defaults, and the empty string

<!-- example: oracle -->
```sql
CREATE TABLE note (id NUMBER GENERATED ALWAYS AS IDENTITY, body VARCHAR2(100) DEFAULT ON NULL 'empty', made DATE DEFAULT DATE '2026-01-01');
INSERT INTO note (body) VALUES ('first');
INSERT INTO note (body, made) VALUES ('', DEFAULT);
SELECT id, body, TO_CHAR(made, 'YYYY-MM-DD') AS made FROM note ORDER BY id;
```

```text
Table created.

1 row created.

1 row created.

ID BODY  MADE
-- ----- ----------
 1 first 2026-01-01
 2 empty 2026-01-01

2 rows selected.
```

### C. Insert the rows of a query

<!-- example: oracle -->
```sql
CREATE TABLE cheap (id NUMBER PRIMARY KEY, name VARCHAR2(40));
INSERT INTO cheap SELECT id, UPPER(name) FROM product WHERE price < 1;
SELECT * FROM cheap ORDER BY id;
```

```text
Table created.

2 rows created.

ID NAME
-- ------
 1 PENCIL
 2 ERASER

2 rows selected.
```

### D. A sequence for the key, and RETURNING INTO in PL/SQL

<!-- example: oracle -->
```sql
CREATE SEQUENCE product_seq START WITH 10;
DECLARE
  new_id product.id%TYPE;
BEGIN
  INSERT INTO product (id, name, price) VALUES (product_seq.NEXTVAL, 'stapler', 6.40)
  RETURNING id INTO new_id;
  DBMS_OUTPUT.PUT_LINE('new id: ' || new_id);
END;
/
```

```text
Sequence created.

new id: 10

PL/SQL procedure successfully completed.
```

### E. INSERT ... SET and BY NAME (26ai)

<!-- example: oracle -->
```sql
INSERT INTO product SET id = 20, name = 'glue', price = 2.10;
INSERT INTO cheap BY NAME SELECT 'tape' AS name, 21 AS id FROM dual;
SELECT id, name FROM cheap WHERE id > 20;
```

```text
1 row created.

1 row created.

ID NAME
-- ----
21 tape

1 row selected.
```

### F. Errors

A failed statement is undone alone; the transaction goes on.

<!-- example: oracle -->
```sql
INSERT INTO product (id, name, price) VALUES (30, 'clip', -1);
INSERT INTO product (id, name) VALUES (31, '');
INSERT INTO product (id, name) VALUES (1, 'again');
INSERT INTO product (id, name, price) VALUES (32, 'globe', 123456789.5);
INSERT INTO cheap (id, name) VALUES (33, 'a name that is far too long for forty characters');
ROLLBACK;
```

```text
ERROR:
ORA-02290: check constraint violated

ERROR:
ORA-01400: cannot insert NULL into ("SA"."PRODUCT"."NAME")

ERROR:
ORA-00001: unique constraint (SA.PRODUCT_PKEY) violated

ERROR:
ORA-01438: value larger than specified precision allowed for this column

ERROR:
ORA-12899: value too large for column

Rollback complete.
```

### G. What lexdb does not take

<!-- example: oracle -->
```sql
INSERT ALL INTO cheap VALUES (40, 'a') INTO cheap VALUES (41, 'b') SELECT * FROM dual;
```

```text
ERROR:
ORA-00900: invalid SQL statement
```

## See also

[UPDATE](update.md) · [DELETE](delete.md) · [MERGE](merge.md) · [SELECT](select.md) · [CREATE SEQUENCE](create-sequence.md) ·
[PL/SQL blocks](plsql-block.md) · [Array DML](../../bulk-load.md#oracle-array-dml)
