# DROP TYPE

Removes enum types.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
DROP TYPE [ IF EXISTS ] name [, ...] [ RESTRICT ]
```

## Arguments

`IF EXISTS`
: A type that does not exist is skipped with a notice.

*name*
: An enum type, optionally schema-qualified.

`RESTRICT`
: Refuses to drop a type that a column uses (2BP01). This is the default.

## Remarks

- A type a column uses must have the column dropped or changed first.
- `DROP TYPE` is transactional.

## Differences from PostgreSQL

- `DROP TYPE ... CASCADE` is refused (0A000, `lexdb: DROP TYPE ... CASCADE is not supported (drop or change the
  columns first)`) (lexdb-gaps.md 2.2).

## Examples

<!--setup: postgresql
CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy');
CREATE TYPE size AS ENUM ('s', 'm', 'l');
CREATE TYPE colour AS ENUM ('red', 'blue');
CREATE TABLE person (name text, current mood);
-->

The examples use three enums; a column uses `mood`:

```sql
CREATE TYPE mood AS ENUM ('sad', 'ok', 'happy');
CREATE TYPE size AS ENUM ('s', 'm', 'l');
CREATE TYPE colour AS ENUM ('red', 'blue');
CREATE TABLE person (name text, current mood);
```

### A. Drop types

<!-- example: postgresql -->
```sql
DROP TYPE size, colour;
DROP TYPE IF EXISTS size;
```

```text
DROP TYPE
NOTICE:  type "size" does not exist, skipping
DROP TYPE
```

### B. A type in use

<!-- example: postgresql -->
```sql
DROP TYPE mood;
DROP TYPE mood CASCADE;
ALTER TABLE person DROP COLUMN current;
DROP TYPE mood;
```

```text
ERROR:  cannot drop type mood because other objects depend on it
ERROR:  lexdb: DROP TYPE ... CASCADE is not supported (drop or change the columns first)
ALTER TABLE
DROP TYPE
```

## See also

[CREATE TYPE](create-type.md) · [ALTER TYPE](alter-type.md)
