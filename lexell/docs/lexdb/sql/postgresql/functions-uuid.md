# UUID functions

Functions that make and read `uuid` values.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
gen_random_uuid ( ) → uuid
uuidv4 ( ) → uuid
uuidv7 ( [ shift interval ] ) → uuid
uuid_extract_version ( uuid ) → smallint
uuid_extract_timestamp ( uuid ) → timestamptz
```

## Functions

`gen_random_uuid`, `uuidv4`
: A random version 4 UUID. `uuidv4` is PostgreSQL 18's name for it.

`uuidv7`
: A version 7 UUID (PostgreSQL 18): the current time in milliseconds, then random bits, so values made later sort
  later. *shift* moves the time it holds.

`uuid_extract_version`
: The version of a UUID of the standard variant (PostgreSQL 17), or NULL for another variant.

`uuid_extract_timestamp`
: The time held in a version 1 or 7 UUID, or NULL for other versions.

## Remarks

- The values are random, so the examples show versions, counts and comparisons, not the values.
- `gen_random_uuid()` is the usual default for a `uuid` key; `uuidv7()` gives keys that arrive in order, which
  suits an index.

## Differences from PostgreSQL

None known.

## Examples

### A. Random and time-ordered UUIDs

<!-- example: postgresql -->
```sql
SELECT uuid_extract_version(gen_random_uuid()) AS v_gen, uuid_extract_version(uuidv4()) AS v4,
       uuid_extract_version(uuidv7()) AS v7, length(uuidv7()::text) AS text_length;
```

```text
 v_gen | v4 | v7 | text_length
-------+----+----+-------------
     4 |  4 |  7 |          36
(1 row)
```

### B. The time in a version 7 UUID

<!-- example: postgresql -->
```sql
SELECT abs(extract(epoch FROM uuid_extract_timestamp(uuidv7()) - clock_timestamp())) < 5 AS now_ish,
       uuid_extract_timestamp(uuidv7(INTERVAL '-1 day')) < now() - INTERVAL '23 hours' AS shifted,
       uuid_extract_timestamp(gen_random_uuid()) AS v4_has_none;
```

```text
 now_ish | shifted | v4_has_none
---------+---------+-------------
 t       | t       |
(1 row)
```

### C. A fixed UUID

<!-- example: postgresql -->
```sql
SELECT uuid_extract_version('a0eebc99-9c0b-4ef8-bb6d-6bb9bd380a11') AS version,
       uuid_extract_timestamp('019535d9-3df7-79fb-b466-fa907fa17f9e') AS v7_time;
```

```text
 version |          v7_time
---------+----------------------------
       4 | 2025-02-24 02:46:24.503+00
(1 row)
```

### D. Keys in order

<!-- example: postgresql -->
```sql
CREATE TABLE event (id uuid PRIMARY KEY DEFAULT uuidv7(), n int);
INSERT INTO event (n) SELECT g FROM generate_series(1, 5) g;
SELECT count(*) AS rows, count(DISTINCT id) AS ids FROM event;
```

```text
CREATE TABLE
INSERT 0 5
 rows | ids
------+-----
    5 |   5
(1 row)
```

## See also

[UUID type](data-types-uuid.md) · [CREATE TABLE](create-table.md)
