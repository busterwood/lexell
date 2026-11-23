# DROP SEQUENCE

Removes sequences.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
DROP SEQUENCE [ IF EXISTS ] name [, ...] [ CASCADE | RESTRICT ]
```

## Arguments

`IF EXISTS`
: A sequence that does not exist is skipped with a notice.

*name*
: A sequence, optionally schema-qualified.

`CASCADE`
: For a sequence a column owns (a `serial` column's): also drops the column's default.

`RESTRICT`
: Refuses to drop a sequence that a column owns (2BP01). This is the default.

## Remarks

- The sequence of a `serial` or identity column goes with its column or table; it is refused on its own unless
  `CASCADE` is given.

## Differences from PostgreSQL

- A column default that only names the sequence (`DEFAULT nextval('s')`, without `OWNED BY`) does not stop the drop:
  the sequence goes, and the next `INSERT` that uses the default fails with 42P01. PostgreSQL refuses the drop
  (2BP01), because `nextval('s')` keeps the sequence as a dependency.
- `DROP SEQUENCE` of a table says `sequence "t" does not exist` (42P01); PostgreSQL says `"t" is not a sequence`
  (42809).
- The refusal puts what `CASCADE` would do in its message (`with CASCADE its default is dropped`); PostgreSQL gives
  a `DETAIL` and a `HINT`.

## Examples

<!--setup: postgresql
CREATE SEQUENCE a_seq;
CREATE SEQUENCE b_seq;
CREATE SEQUENCE c_seq;
CREATE TABLE note (id serial PRIMARY KEY, body text);
-->

The examples use these sequences:

```sql
CREATE SEQUENCE a_seq;
CREATE SEQUENCE b_seq;
CREATE SEQUENCE c_seq;
CREATE TABLE note (id serial PRIMARY KEY, body text);
```

### A. Drop sequences

<!-- example: postgresql -->
```sql
DROP SEQUENCE a_seq;
DROP SEQUENCE IF EXISTS a_seq;
DROP SEQUENCE b_seq, c_seq;
```

```text
DROP SEQUENCE
NOTICE:  sequence "a_seq" does not exist, skipping
DROP SEQUENCE
DROP SEQUENCE
```

### B. A serial column's sequence

<!-- example: postgresql -->
```sql
DROP SEQUENCE note_id_seq;
DROP SEQUENCE note_id_seq CASCADE;
\d note
```

```text
ERROR:  cannot drop sequence note_id_seq because column id of table note requires it (with CASCADE its default is dropped)
DROP SEQUENCE
                Table "public.note"
 Column |  Type   | Collation | Nullable | Default
--------+---------+-----------+----------+---------
 id     | integer |           | not null |
 body   | text    |           |          |
Indexes:
    "note_pkey" PRIMARY KEY, btree (id)
```

### C. A sequence named in a default

<!-- example: postgresql -->
```sql
CREATE SEQUENCE ref_no;
CREATE TABLE ticket (no int DEFAULT nextval('ref_no'));
DROP SEQUENCE ref_no;
INSERT INTO ticket DEFAULT VALUES;
```

```text
CREATE SEQUENCE
CREATE TABLE
DROP SEQUENCE
ERROR:  relation "ref_no" does not exist
```

### D. Errors

<!-- example: postgresql -->
```sql
DROP SEQUENCE a_seq;
DROP SEQUENCE note;
```

```text
ERROR:  sequence "a_seq" does not exist
ERROR:  sequence "note" does not exist
```

## See also

[CREATE SEQUENCE](create-sequence.md) · [ALTER SEQUENCE](alter-sequence.md) · [DROP TABLE](drop-table.md)
