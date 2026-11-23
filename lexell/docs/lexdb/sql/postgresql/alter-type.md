# ALTER TYPE

Adds a label to an enum type.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
ALTER TYPE name ADD VALUE [ IF NOT EXISTS ] 'new_label' [ { BEFORE | AFTER } 'existing_label' ]
```

## Arguments

*name*
: The enum type, optionally schema-qualified.

`IF NOT EXISTS`
: If the label is there, does nothing.

*new_label*
: The label to add. Without `BEFORE` or `AFTER` it goes last.

`BEFORE`, `AFTER` *existing_label*
: Where the new label goes in the order.

## Remarks

- Rows already stored keep their values, and sort by the new order.
- `ALTER TYPE ... ADD VALUE` is transactional, and may run inside a transaction block.

## Differences from PostgreSQL

- Only `ADD VALUE`: `RENAME VALUE`, `RENAME TO`, `OWNER TO`, `SET SCHEMA` and the forms for composite types are
  refused (0A000, `lexdb: ALTER TYPE supports ADD VALUE only`).

## Examples

<!--setup: postgresql
CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy');
-->

The examples use one enum:

```sql
CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy');
```

### A. Add labels

<!-- example: postgresql -->
```sql
ALTER TYPE mood ADD VALUE 'angry' BEFORE 'sad';
ALTER TYPE mood ADD VALUE 'ecstatic' AFTER 'happy';
ALTER TYPE mood ADD VALUE 'calm';
ALTER TYPE mood ADD VALUE IF NOT EXISTS 'calm';
SELECT enumlabel FROM pg_enum ORDER BY enumsortorder;
```

```text
ALTER TYPE
ALTER TYPE
ALTER TYPE
ALTER TYPE
 enumlabel
-----------
 angry
 sad
 ok
 happy
 ecstatic
 calm
(6 rows)
```

### B. What is refused

<!-- example: postgresql -->
```sql
ALTER TYPE mood ADD VALUE 'calm';
ALTER TYPE mood RENAME VALUE 'ok' TO 'fine';
ALTER TYPE mood RENAME TO feeling;
```

```text
ERROR:  enum label "calm" already exists
ERROR:  lexdb: ALTER TYPE supports ADD VALUE only
ERROR:  lexdb: ALTER TYPE supports ADD VALUE only
```

## See also

[CREATE TYPE](create-type.md) · [DROP TYPE](drop-type.md)
