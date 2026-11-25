# JSON and SQL/JSON

The `json` and `jsonb` data types, PostgreSQL JSON operators, functions, aggregates and set-returning functions, and the
ISO SQL/JSON constructors, query functions, predicates and `JSON_TABLE`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Data types

`json`
: Stores an exact copy of valid RFC 8259 JSON text (OID 114). Whitespace and object key order are preserved.

`jsonb`
: Stores canonicalized JSON (OID 3802). Duplicate object keys keep the last value; object keys are sorted by length
  then lexicographically, matching PostgreSQL `jsonb`. Supports `=`, `<>`, `<`, `<=`, `>`, `>=` (ordering `null` <
  string < number < boolean < array < object), `ORDER BY`, `GROUP BY`, `DISTINCT` and indexes.

Typed literals (`json '{...}'`, `jsonb '{...}'`) and casts (`::json`, `::jsonb`, `::int`, `::numeric`, `::boolean`,
`::text`) are supported, as are `json[]` and `jsonb[]`.

## Operators

| Operator | Left | Right | Result | Description |
|---|---|---|---|---|
| `->` | `json`/`jsonb` | `text` / `int` | `json`/`jsonb` | Extract object field or array element (negative index from end) |
| `->>` | `json`/`jsonb` | `text` / `int` | `text` | Extract object field or array element as text |
| `#>` | `json`/`jsonb` | `text[]` | `json`/`jsonb` | Extract value at path |
| `#>>` | `json`/`jsonb` | `text[]` | `text` | Extract value at path as text |
| `@>` | `jsonb` | `jsonb` | `boolean` | Does the left value contain the right value? |
| `<@` | `jsonb` | `jsonb` | `boolean` | Is the left value contained in the right value? |
| `?` | `jsonb` | `text` | `boolean` | Does top-level object contain key (or array contain string element)? |
| `?|` | `jsonb` | `text[]` | `boolean` | Does any of the keys exist at top level? |
| `?&` | `jsonb` | `text[]` | `boolean` | Do all of the keys exist at top level? |
| `||` | `jsonb` | `jsonb` | `jsonb` | Concatenate arrays or merge objects (right overrides left) |
| `-` | `jsonb` | `text` / `text[]` / `int` | `jsonb` | Delete object key(s) or array element |
| `#-` | `jsonb` | `text[]` | `jsonb` | Delete field or array element at path |
| `@?` | `jsonb` | `text` | `boolean` | Does JSON path return any item? |
| `@@` | `jsonb` | `text` | `boolean` | Returns result of JSON path predicate check |

## Functions

### Construction and conversion

- `to_json(any)`, `to_jsonb(any)` — converts a SQL value (including 1-D arrays and existing `json`/`jsonb`) to JSON/JSONB.
- `array_to_json(array [, pretty_bool])` — converts a SQL array to a JSON array.
- `json_build_object([k, v, ...])`, `jsonb_build_object([k, v, ...])` — builds an object from alternating keys and values.
- `json_build_array([v, ...])`, `jsonb_build_array([v, ...])` — builds an array from arguments.
- `json_object(text[])`, `jsonb_object(text[])`, `json_object(keys text[], vals text[])`, `jsonb_object(keys text[], vals text[])`.
- `JSON(expr [{WITH | WITHOUT} UNIQUE [KEYS]])` — validates JSON text and optionally enforces unique keys.
- `JSON_OBJECT([ [KEY] k VALUE v | k : v, ... ] [{NULL | ABSENT} ON NULL] [{WITH | WITHOUT} UNIQUE [KEYS]] [RETURNING type])`.
- `JSON_ARRAY([v, ...] | (subquery) [{NULL | ABSENT} ON NULL] [RETURNING type])` — defaults to `ABSENT ON NULL`.
- `JSON_SCALAR(expr)` — converts a scalar SQL value to JSON.
- `JSON_SERIALIZE(expr [RETURNING type] [PRETTY])` — serializes JSON to text (or requested type).

### Inspection, extraction and modification

- `json_typeof(json)`, `jsonb_typeof(jsonb)` — `'object'`, `'array'`, `'string'`, `'number'`, `'boolean'`, `'null'`.
- `json_array_length(json)`, `jsonb_array_length(jsonb)` — number of elements in top-level array.
- `json_extract_path(j, k1, ...)`, `jsonb_extract_path(...)`, `json_extract_path_text(...)`, `jsonb_extract_path_text(...)`.
- `json_strip_nulls(j [, strip_in_arrays])`, `jsonb_strip_nulls(jb [, strip_in_arrays])` (PostgreSQL 18 `strip_in_arrays` supported).
- `jsonb_set(target, path text[], new_value jsonb [, create_if_missing])`.
- `jsonb_insert(target, path text[], new_value jsonb [, insert_after])`.
- `jsonb_pretty(jsonb)` — indented JSON text.
- `jsonb_path_exists(target, path [, vars [, silent]])`, `jsonb_path_match(...)`, `jsonb_path_query_first(...)`, `jsonb_path_query_array(...)`.

### SQL/JSON predicates and query functions

- `expr IS [NOT] JSON [VALUE | SCALAR | ARRAY | OBJECT] [{WITH | WITHOUT} UNIQUE [KEYS]]`.
- `JSON_VALUE(expr, path [PASSING val AS name, ...] [RETURNING type] [{NULL | ERROR | DEFAULT expr} ON EMPTY] [{NULL | ERROR | DEFAULT expr} ON ERROR])`.
- `JSON_QUERY(expr, path [PASSING ...] [RETURNING type] [{WITHOUT | WITH [CONDITIONAL | UNCONDITIONAL]} [ARRAY] WRAPPER] [{KEEP | OMIT} QUOTES [ON SCALAR STRING]] [ON EMPTY] [ON ERROR])`.
- `JSON_EXISTS(expr, path [PASSING ...] [{TRUE | FALSE | UNKNOWN | ERROR} ON ERROR])`.

### Aggregates

- `json_agg(expr [ORDER BY ...])`, `jsonb_agg(expr [ORDER BY ...])` — preserves SQL NULLs as JSON `null`.
- `json_object_agg(key, value)`, `jsonb_object_agg(key, value)`.
- `JSON_ARRAYAGG(expr [ORDER BY ...] [{NULL | ABSENT} ON NULL] [RETURNING type])` — defaults to `ABSENT ON NULL`.
- `JSON_OBJECTAGG([KEY] k VALUE v | k : v [{NULL | ABSENT} ON NULL] [{WITH | WITHOUT} UNIQUE [KEYS]] [RETURNING type])`.

### Set-returning functions and `JSON_TABLE`

- `json_each(j)`, `jsonb_each(jb)`, `json_each_text(j)`, `jsonb_each_text(jb)` — `(key text, value json|jsonb|text)`.
- `json_array_elements(j)`, `jsonb_array_elements(jb)`, `json_array_elements_text(j)`, `jsonb_array_elements_text(jb)`.
- `json_object_keys(j)`, `jsonb_object_keys(jb)`.
- `jsonb_path_query(target, path [, vars [, silent]])`.
- `JSON_TABLE(expr, path [PASSING ...] COLUMNS (col_def, ...) [ON ERROR]) [AS] alias` — supports `FOR ORDINALITY`,
  `FORMAT JSON`, `EXISTS PATH`, `WRAPPER`, `ON EMPTY`, `ON ERROR`, `NESTED [PATH] ... COLUMNS (...)`, and implicit
  lateral references to earlier `FROM` tables.

## Examples

### A. `jsonb` columns, operators and path queries

<!-- example: postgresql -->
```sql
CREATE TABLE docs (id int PRIMARY KEY, body jsonb);
INSERT INTO docs VALUES
  (1, '{"user": "Ann", "tags": ["sql", "json"], "score": 90}'),
  (2, '{"user": "Bob", "tags": ["db"], "score": 75}');

SELECT id, body ->> 'user' AS usr, body -> 'tags' ->> 0 AS first_tag
FROM docs
WHERE body @> '{"tags": ["sql"]}'
ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 2
 id | usr | first_tag
----+-----+-----------
  1 | Ann | sql
(1 row)
```

### B. SQL/JSON constructors, aggregates and `JSON_TABLE`

<!-- example: postgresql -->
```sql
SELECT JSON_OBJECT('id': 1, 'tags': JSON_ARRAY('a', NULL, 'b')) AS obj;

SELECT jt.ord, jt.usr, jt.tag
FROM docs d,
     JSON_TABLE(d.body, '$' COLUMNS (
       ord FOR ORDINALITY,
       usr text PATH '$.user',
       NESTED PATH '$.tags[*]' COLUMNS (tag text PATH '$')
     )) AS jt
ORDER BY d.id, jt.tag;
```

```text
            obj
---------------------------
 {"id":1,"tags":["a","b"]}
(1 row)

 ord | usr | tag
-----+-----+------
   1 | Ann | json
   1 | Ann | sql
   1 | Bob | db
(3 rows)
```

### C. Errors

<!-- example: postgresql -->
```sql
SELECT '{bad}'::jsonb;
SELECT json_build_object(NULL, 1);
SELECT JSON_OBJECT('a': 1, 'a': 2 WITH UNIQUE KEYS);
```

```text
ERROR:  invalid input syntax for type jsonb: "{bad}"
ERROR:  null value not allowed for object key
ERROR:  duplicate JSON object key value: "a"
```

## See also

[Operators](operators.md) · [Aggregate functions](functions-aggregate.md) · [Set-returning functions](functions-srf.md)
