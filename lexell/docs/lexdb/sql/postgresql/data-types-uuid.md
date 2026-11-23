# UUID type

`uuid`: a 128-bit universally unique identifier.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
uuid
```

## Remarks

- A `uuid` is read from 32 hex digits, in either case, with or without hyphens after any group of four digits,
  and optionally in braces. It is shown in lower case in the standard 8-4-4-4-12 form.
- Values compare and sort by their bytes, so a `uuid` column can be a key or be indexed.
- `gen_random_uuid()` and `uuidv4()` make random (version 4) values; `uuidv7()` makes time-ordered (version 7)
  ones. `uuid_extract_version` and `uuid_extract_timestamp` read a value. See [UUID
  functions](functions-uuid.md).
- A `uuid` casts to `text` and to `bytea` (16 bytes).
- Text that is not a uuid is 22P02.

## Differences from PostgreSQL

None known.

## Examples

### A. Forms that are read

<!-- example: postgresql -->
```sql
SELECT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid AS standard,
       'A0EEBC999C0B4EF8BB6D6BB9BD380A11'::uuid AS upper_no_hyphens,
       '{a0eebc99-9c0b4ef8-bb6d6bb9-bd380a11}'::uuid AS braces;
```

```text
               standard               |           upper_no_hyphens           |                braces
--------------------------------------+--------------------------------------+--------------------------------------
 a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11 | a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11 | a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11
(1 row)
```

### B. A uuid key with a default

<!-- example: postgresql -->
```sql
CREATE TABLE account (id uuid PRIMARY KEY DEFAULT gen_random_uuid(), name text);
INSERT INTO account (name) VALUES ('ann'), ('bob');
SELECT count(DISTINCT id) AS ids, min(uuid_extract_version(id)) AS version FROM account;
```

```text
CREATE TABLE
INSERT 0 2
 ids | version
-----+---------
   2 |       4
(1 row)
```

### C. Comparison and casts

<!-- example: postgresql -->
```sql
SELECT 'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid < 'b0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid AS less,
       length('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid::text) AS text_length,
       'a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11'::uuid::bytea AS bytes;
```

```text
 less | text_length |               bytes
------+-------------+------------------------------------
 t    |          36 | \xa0eebc999c0b4ef8bb6d6bb9bd380a11
(1 row)
```

### D. Errors

<!-- example: postgresql -->
```sql
SELECT 'a0eebc99-9c0b-4ef8'::uuid;
```

```text
ERROR:  invalid input syntax for type uuid: "a0eebc99-9c0b-4ef8"
```

## See also

[UUID functions](functions-uuid.md) · [Binary type](data-types-binary.md) · [CREATE TABLE](create-table.md)
