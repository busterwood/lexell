# JSON functions

`json_build_object` and `jsonb_build_object`: a JSON object as text.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
json_build_object ( [ key, value [, ...] ] ) → text
jsonb_build_object ( [ key, value [, ...] ] ) → text
```

## Functions

`json_build_object`, `jsonb_build_object`
: A JSON object of the key and value pairs, in the order given. A key is written as a JSON string; a value as a
  JSON number, `true` or `false`, `null`, or a string with `"` and `\` escaped. The two names do the same.

## Remarks

- There is no `json` or `jsonb` type: the result is `text`, which a client can parse.
- The number of arguments must be even (22023), and a key may not be NULL (22004).

## Differences from PostgreSQL

- The result is `text`, not `json` or `jsonb`. `jsonb_build_object` does not sort the keys or drop repeated ones,
  and spells the object as `json_build_object` does (`{"a" : 1}`).
- There are no other JSON functions or operators: `to_json`, `row_to_json`, `json_agg`, `json_build_array`, `->`,
  `->>`, `jsonb_path_query` and the rest do not exist (lexdb-gaps.md 2.1).

## Examples

### A. An object from values

<!-- example: postgresql -->
```sql
SELECT json_build_object('id', 1, 'name', 'Ann "A"', 'active', true, 'score', 9.5, 'note', NULL) AS obj;
```

```text
                                       obj
---------------------------------------------------------------------------------
 {"id" : 1, "name" : "Ann \"A\"", "active" : true, "score" : 9.5, "note" : null}
(1 row)
```

### B. An object for each row

<!-- example: postgresql -->
```sql
CREATE TABLE person (id int, name text, born date);
INSERT INTO person VALUES (1, 'ann', '1990-07-15'), (2, 'bob', NULL);
SELECT jsonb_build_object('id', id, 'name', name, 'born', born) AS doc FROM person ORDER BY id;
```

```text
CREATE TABLE
INSERT 0 2
                        doc
---------------------------------------------------
 {"id" : 1, "name" : "ann", "born" : "1990-07-15"}
 {"id" : 2, "name" : "bob", "born" : null}
(2 rows)
```

### C. Errors

<!-- example: postgresql -->
```sql
SELECT json_build_object('a');
SELECT json_build_object(NULL, 1);
SELECT to_json('x'::text);
```

```text
ERROR:  argument list must have even number of elements
ERROR:  null value not allowed for object key
ERROR:  function to_json with 1 arguments does not exist
```

## See also

[String conversion functions](functions-string-convert.md) · [Aggregate functions](functions-aggregate.md)
