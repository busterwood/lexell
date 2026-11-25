# JSON and SQL/JSON (Oracle)

The `JSON` data type, `JSON(...)` constructor, `IS [NOT] JSON`, `JSON_VALUE`, `JSON_QUERY`, `JSON_EXISTS`,
`JSON_OBJECT`, `JSON_ARRAY`, `JSON_ARRAYAGG`, `JSON_OBJECTAGG`, `JSON_SERIALIZE`, `JSON_MERGEPATCH`, `JSON_EQUAL`,
`JSON_TRANSFORM`, and `JSON_TABLE`.

**Door:** Oracle (TNS). **Follows:** Oracle Database 23ai / 26ai.

## Data type

`JSON`
: Stores validated RFC 8259 JSON values. `USER_TAB_COLUMNS` reports `DATA_TYPE = 'JSON'`. Invalid JSON input raises
  an error on insert or conversion.

## Functions and predicates

- `JSON(expr [{WITH | WITHOUT} UNIQUE [KEYS]])` — validates and constructs a `JSON` value.
- `expr IS [NOT] JSON [VALUE | SCALAR | ARRAY | OBJECT] [{WITH | WITHOUT} UNIQUE [KEYS]]` — validates JSON text and structure.
- `JSON_VALUE(doc, path [PASSING val AS name, ...] [RETURNING type] [{NULL | ERROR | DEFAULT expr} ON EMPTY] [{NULL | ERROR | DEFAULT expr} ON ERROR])` — extracts a scalar value.
- `JSON_QUERY(doc, path [PASSING ...] [RETURNING type] [{WITHOUT | WITH [CONDITIONAL | UNCONDITIONAL]} [ARRAY] WRAPPER] [{KEEP | OMIT} QUOTES [ON SCALAR STRING]] [ON EMPTY] [ON ERROR])` — extracts a JSON fragment.
- `JSON_EXISTS(doc, path [PASSING ...] [{TRUE | FALSE | UNKNOWN | ERROR} ON ERROR])` — tests whether a JSON path matches.
- `JSON_OBJECT([ [KEY] k VALUE v | k : v, ... ] [{NULL | ABSENT} ON NULL] [{WITH | WITHOUT} UNIQUE [KEYS]] [RETURNING type])` — builds a JSON object.
- `JSON_ARRAY([v, ...] | (subquery) [{NULL | ABSENT} ON NULL] [RETURNING type])` — builds a JSON array (defaults to `ABSENT ON NULL`).
- `JSON_ARRAYAGG(expr [ORDER BY ...] [{NULL | ABSENT} ON NULL] [RETURNING type])` — aggregates values into a JSON array.
- `JSON_OBJECTAGG([KEY] k VALUE v | k : v [{NULL | ABSENT} ON NULL] [{WITH | WITHOUT} UNIQUE [KEYS]] [RETURNING type])` — aggregates key/value pairs into a JSON object.
- `JSON_SERIALIZE(expr [RETURNING type] [PRETTY])` — serializes JSON to text (optionally pretty-printed).
- `JSON_MERGEPATCH(target, patch [RETURNING type] [PRETTY])` — applies an RFC 7396 JSON Merge Patch.
- `JSON_EQUAL(a, b)` — compares two JSON values for semantic equality regardless of key order or whitespace.
- `JSON_TRANSFORM(doc, op path [= val], ... [RETURNING type])` — transforms a JSON document with `SET`, `INSERT`, `REPLACE`, `REMOVE`, `APPEND`, and `KEEP`.

## `JSON_TABLE`

```
JSON_TABLE (
    expr , path [ PASSING val AS name [, ...] ]
    COLUMNS (
        col_name FOR ORDINALITY
      | col_name data_type [ FORMAT JSON ] [ EXISTS ] PATH 'path' [ wrapper ] [ on_empty ] [ on_error ]
      | NESTED [ PATH ] 'path' COLUMNS ( ... )
      [, ...]
    )
    [ on_error ]
) [ alias ]
```

Supports implicit lateral references to preceding tables in `FROM` (`FROM docs d, JSON_TABLE(d.doc, ...) jt`).

## Examples

### A. `JSON` column, `JSON_VALUE`, `JSON_EXISTS` and `JSON_TRANSFORM`

<!-- example: oracle -->
```sql
CREATE TABLE jdocs (id NUMBER PRIMARY KEY, doc JSON);
INSERT INTO jdocs VALUES (1, '{"name":"Ann","score":90,"tags":["x","y"]}');
INSERT INTO jdocs VALUES (2, '{"name":"Bob","score":75,"tags":["z"]}');

SELECT id,
       JSON_VALUE(doc, '$.name') AS nm,
       JSON_VALUE(doc, '$.score' RETURNING NUMBER) AS sc
FROM jdocs
WHERE JSON_EXISTS(doc, '$.score ? (@ > $min)' PASSING 80 AS min)
ORDER BY id;

SELECT JSON_TRANSFORM(doc, SET '$.score' = 95, APPEND '$.tags' = 'vip') AS updated
FROM jdocs
WHERE id = 1;
```

### B. `JSON_TABLE` with `NESTED PATH`

<!-- example: oracle -->
```sql
SELECT d.id, jt.ord, jt.nm, jt.tag
FROM jdocs d,
     JSON_TABLE(d.doc, '$' COLUMNS (
       ord FOR ORDINALITY,
       nm VARCHAR2(20) PATH '$.name',
       NESTED PATH '$.tags[*]' COLUMNS (tag VARCHAR2(10) PATH '$')
     )) jt
ORDER BY d.id, jt.tag;
```

## See also

[Data types](data-types-other.md) · [Aggregate functions](functions-aggregate.md) · [SELECT](select.md)
