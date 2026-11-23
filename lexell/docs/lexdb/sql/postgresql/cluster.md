# CLUSTER

Accepted for PostgreSQL's tools: a lexdb table is always kept in the order of its primary key.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
CLUSTER [ ( VERBOSE [ boolean ] ) ] [ VERBOSE ] [ table_name [ USING index_name ] ]
```

## Arguments

*table_name*
: The table.

`USING` *index_name*
: An index of the table.

## Remarks

- The table and index named must exist, and the index must be the table's. Then `CLUSTER` does nothing: the rows
  are stored in a B+tree in primary key order, and stay so.
- `CLUSTER` without a table cannot run inside a transaction block (25001), as in PostgreSQL.

## Differences from PostgreSQL

- The rows are not reordered by the index: a table's order is its primary key's.

## Examples

<!--setup: postgresql
CREATE TABLE item (id int PRIMARY KEY, kind int);
CREATE INDEX item_kind ON item (kind);
-->

The examples use one table with an index:

```sql
CREATE TABLE item (id int PRIMARY KEY, kind int);
CREATE INDEX item_kind ON item (kind);
```

### A. Its forms, and an error

<!-- example: postgresql -->
```sql
CLUSTER item USING item_kind;
CLUSTER item;
CLUSTER;
CLUSTER item USING nosuch;
```

```text
CLUSTER
CLUSTER
CLUSTER
ERROR:  index "nosuch" for table "item" does not exist
```

## See also

[CREATE INDEX](create-index.md) · [VACUUM](vacuum.md)
