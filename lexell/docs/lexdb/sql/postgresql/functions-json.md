# JSON and SQL/JSON

The `json` and `jsonb` types, PostgreSQL's JSON operators, functions, aggregates and set-returning functions, and the
ISO SQL/JSON constructors, predicates, query functions and `JSON_TABLE`.

**Door:** PostgreSQL. **Follows:** PostgreSQL 18.

## Syntax

```
-- types
json | jsonb                                   json '...'   jsonb '...'   '...'::json   '...'::jsonb

-- operators
json | jsonb  ->   text | integer              → json | jsonb
json | jsonb  ->>  text | integer              → text
json | jsonb  #>   text[]                      → json | jsonb
json | jsonb  #>>  text[]                      → text
jsonb  @>  jsonb    jsonb  <@  jsonb           → boolean
jsonb  ?  text      jsonb  ?|  text[]          jsonb  ?&  text[]       → boolean
jsonb  ||  jsonb                               → jsonb
jsonb  -   text | text[] | integer             → jsonb
jsonb  #-  text[]                              → jsonb
jsonb  @?  jsonpath | text                     jsonb  @@  jsonpath | text   → boolean

-- construction
to_json ( any ) → json                         to_jsonb ( any ) → jsonb
array_to_json ( anyarray [, pretty ] ) → json
json_build_object ( [ key, value [, ...] ] ) → json      jsonb_build_object ( ... ) → jsonb
json_build_array ( [ value [, ...] ] ) → json            jsonb_build_array ( ... ) → jsonb
json_object ( text[] ) → json                  json_object ( keys text[], values text[] ) → json   (and jsonb_object)
JSON ( text [ { WITH | WITHOUT } UNIQUE [ KEYS ] ] ) → json
JSON_SCALAR ( value ) → json
JSON_SERIALIZE ( json_value [ RETURNING type ] ) → text
JSON_OBJECT ( [ [ KEY ] key VALUE value | key : value [, ...] ]
              [ { NULL | ABSENT } ON NULL ] [ { WITH | WITHOUT } UNIQUE [ KEYS ] ] [ RETURNING type ] ) → json
JSON_ARRAY ( [ value [, ...] ] | ( query ) [ { NULL | ABSENT } ON NULL ] [ RETURNING type ] ) → json

-- inspection and modification
json_typeof ( json ) | jsonb_typeof ( jsonb ) → text
json_array_length ( json ) | jsonb_array_length ( jsonb ) → integer
json_extract_path ( json, path [, ...] ) | jsonb_extract_path ( ... ) → json | jsonb      (and *_text → text)
json_strip_nulls ( json [, strip_in_arrays ] ) | jsonb_strip_nulls ( jsonb [, strip_in_arrays ] )
jsonb_set ( target jsonb, path text[], new jsonb [, create_if_missing boolean ] ) → jsonb
jsonb_insert ( target jsonb, path text[], new jsonb [, insert_after boolean ] ) → jsonb
jsonb_pretty ( jsonb ) → text
jsonb_path_exists | jsonb_path_match ( target jsonb, path jsonpath [, vars jsonb [, silent boolean ] ] ) → boolean
jsonb_path_query_array | jsonb_path_query_first ( ... ) → jsonb

-- SQL/JSON predicate and query functions
expression IS [ NOT ] JSON [ VALUE | SCALAR | ARRAY | OBJECT ] [ { WITH | WITHOUT } UNIQUE [ KEYS ] ] → boolean
JSON_EXISTS ( json, path [ PASSING value AS name [, ...] ] [ { TRUE | FALSE | UNKNOWN | ERROR } ON ERROR ] ) → boolean
JSON_VALUE ( json, path [ PASSING value AS name [, ...] ] [ RETURNING type ]
             [ { NULL | ERROR | DEFAULT expression } ON EMPTY ] [ { NULL | ERROR | DEFAULT expression } ON ERROR ] )
JSON_QUERY ( json, path [ PASSING value AS name [, ...] ] [ RETURNING type ]
             [ { WITHOUT | WITH [ CONDITIONAL | UNCONDITIONAL ] } [ ARRAY ] WRAPPER ]
             [ { KEEP | OMIT } QUOTES [ ON SCALAR STRING ] ]
             [ { ERROR | NULL | EMPTY { ARRAY | OBJECT } | DEFAULT expression } ON EMPTY ]
             [ { ERROR | NULL | EMPTY { ARRAY | OBJECT } | DEFAULT expression } ON ERROR ] )

-- aggregates
json_agg ( any [ ORDER BY ... ] ) → json                jsonb_agg ( any [ ORDER BY ... ] ) → jsonb
json_object_agg ( key, value ) → json                   jsonb_object_agg ( key, value ) → jsonb
JSON_ARRAYAGG ( value [ ORDER BY ... ] [ { NULL | ABSENT } ON NULL ] [ RETURNING type ] ) → json
JSON_OBJECTAGG ( [ KEY ] key VALUE value | key : value
                 [ { NULL | ABSENT } ON NULL ] [ { WITH | WITHOUT } UNIQUE [ KEYS ] ] [ RETURNING type ] ) → json

-- in FROM
json_each ( json ) | jsonb_each ( jsonb ) → setof ( key text, value json | jsonb )      (and *_each_text)
json_array_elements ( json ) | jsonb_array_elements ( jsonb ) → setof json | jsonb      (and *_text)
json_object_keys ( json ) | jsonb_object_keys ( jsonb ) → setof text
jsonb_path_query ( target jsonb, path jsonpath [, vars jsonb [, silent boolean ] ] ) → setof jsonb
JSON_TABLE ( json, path [ PASSING value AS name [, ...] ]
             COLUMNS ( column_definition [, ...] ) [ { ERROR | EMPTY [ ARRAY ] } ON ERROR ] ) [ [ AS ] alias ]
```

*column_definition* is one of

```
name FOR ORDINALITY
name type [ FORMAT JSON ] [ PATH path ] [ wrapper ] [ quotes ] [ ON EMPTY ] [ ON ERROR ]
name type EXISTS [ PATH path ] [ { TRUE | FALSE | UNKNOWN | ERROR } ON ERROR ]
NESTED [ PATH ] path [ AS name ] COLUMNS ( column_definition [, ...] )
```

## Data types

`json`
: Valid JSON text (RFC 8259), stored as written: white space, the order of the keys and repeated keys are kept (OID 114).
  `json` has no equality operator in PostgreSQL; lexdb's `=` on `json` compares the text.

`jsonb`
: Valid JSON, stored in a canonical form (OID 3802): a repeated key keeps its last value, and the keys of an object
  are ordered by length, then by their bytes. It prints as PostgreSQL's `jsonb` does: `{"a": 1, "b": [1, 2]}`. It has
  `=`, `<>`, `<`, `<=`, `>`, `>=` (`null` < string < number < boolean < array < object), so `ORDER BY`, `GROUP BY`, `DISTINCT` and a primary key or `btree` index work.

A JSON `null` is a value, not an SQL `NULL`: `'null'::jsonb IS NULL` is false, and `-> 'missing'` gives an SQL `NULL`.
A string that is not valid JSON is 22P02 `invalid input syntax for type json` (also for `jsonb`).
`json[]` and `jsonb[]` columns work.

Casts: `text`, `json`, `jsonb`, and from a JSON number, string or boolean to `int`, `bigint`, `numeric`, `float8`,
`boolean` and `text` (`('{"n":5}'::jsonb -> 'n')::int`).

## Operators

| Operator | Result | What it gives |
|---|---|---|
| `json -> text`, `json -> integer` | `json` | The member of an object, or the element of an array (a negative index counts from the end); `NULL` if there is none. Also on `jsonb`. |
| `json ->> text`, `json ->> integer` | `text` | The same as text: a string without its quotes. |
| `json #> text[]`, `json #>> text[]` | `json`, `text` | The value at a path of keys and indexes. |
| `jsonb @> jsonb`, `jsonb <@ jsonb` | `boolean` | Whether the left value contains the right one, or is contained in it. |
| `jsonb ? text` | `boolean` | Whether the text is a key of the object, or a string element of the array. |
| `jsonb ?\| text[]`, `jsonb ?& text[]` | `boolean` | Whether any, or all, of the texts are keys. |
| `jsonb \|\| jsonb` | `jsonb` | Two objects joined (the right one wins on a repeated key), or two arrays joined. |
| `jsonb - text`, `jsonb - text[]`, `jsonb - integer` | `jsonb` | Without a key, without keys, without an array element. |
| `jsonb #- text[]` | `jsonb` | Without the value at a path. |
| `jsonb @? jsonpath`, `jsonb @@ jsonpath` | `boolean` | Whether a path finds an item; the result of a path predicate. |

## Functions

`to_json`, `to_jsonb`
: A value as JSON: numbers and booleans as JSON ones, text as a string, an array as a JSON array, a `json` or `jsonb`
  value as itself, a date or time as a quoted string.

`array_to_json`
: A one-dimensional array as a JSON array.

`json_build_object`, `jsonb_build_object`, `json_build_array`, `jsonb_build_array`
: An object from alternating keys and values, an array from its arguments. A `NULL` key is an error. `json_build_object()`
  gives `{}`.

`json_object`, `jsonb_object`
: An object from one array of alternating keys and values, or from an array of keys and one of values. The values are strings.

`JSON`, `JSON_SCALAR`, `JSON_SERIALIZE`
: `JSON` checks that text is JSON (with `WITH UNIQUE KEYS`, that no object repeats a key: 22030) and gives it unchanged.
  `JSON_SCALAR` gives a number, string or boolean as JSON, and `NULL` for `NULL`. `JSON_SERIALIZE` gives the JSON as text.

`JSON_OBJECT`, `JSON_ARRAY`
: Objects and arrays built from SQL values. `NULL ON NULL` (the default for `JSON_OBJECT`) keeps a `NULL` as JSON
  `null`, `ABSENT ON NULL` (the default for `JSON_ARRAY`) leaves the member out. `KEY` may be left out, and `key : value`
  is `KEY key VALUE value`. `JSON_ARRAY ( query )` makes an array of the query's one column. `RETURNING jsonb` gives `jsonb`.

`json_typeof`, `jsonb_typeof`
: `object`, `array`, `string`, `number`, `boolean` or `null`.

`json_array_length`, `jsonb_array_length`
: The number of elements of an array (22023 for anything else).

`json_extract_path`, `json_extract_path_text`, `jsonb_extract_path`, `jsonb_extract_path_text`
: The same as `#>` and `#>>`, with the path as separate arguments.

`json_strip_nulls`, `jsonb_strip_nulls`
: The value without object members that are `null`; with `strip_in_arrays` true, also without `null` elements of arrays.

`jsonb_set`
: The target with the value at *path* replaced by *new*. If the last key is not there it is added unless
  *create_if_missing* is false. A `NULL` argument gives `NULL`.

`jsonb_insert`
: The target with *new* inserted before the array element at *path* (after it if *insert_after* is true), or as a new
  object member.

`jsonb_pretty`
: The value as indented text.

`jsonb_path_exists`, `jsonb_path_match`, `jsonb_path_query_array`, `jsonb_path_query_first`, `jsonb_path_query`
: SQL/JSON path queries. *vars* is a `jsonb` object whose members are the path's `$name` variables. `jsonb_path_exists`
  says whether the path finds an item, `jsonb_path_match` gives the one boolean a path predicate evaluates to,
  `jsonb_path_query_array` and `jsonb_path_query_first` the items as an array and the first one, `jsonb_path_query`
  the items as rows. `lax` (the default) and `strict` modes work; a path can use filters (`? (@ > 1)`), `like_regex`,
  `starts with`, `exists`, arithmetic and the methods `type()`, `size()`, `floor()` and the like.

`IS JSON`
: Whether text is JSON; the kinds tell a scalar, an array and an object apart. `NULL IS JSON` is `NULL`.

`JSON_EXISTS`
: Whether the path finds an item. `ON ERROR` says what an error (not JSON, or `strict` and no member) gives: the default
  is `FALSE`.

`JSON_VALUE`
: One scalar at a path, as `text` or as the `RETURNING` type. When there is no item the result is `NULL` or *ON EMPTY*'s
  choice, and when there are several or the item is not a scalar, or the conversion fails, *ON ERROR*'s choice. (The default
  of both is `NULL`.) `PASSING` gives the path's variables.

`JSON_QUERY`
: An object, an array or a scalar at a path, as `jsonb` or the `RETURNING` type. `WITH WRAPPER` puts the items in an array,
  `WITH CONDITIONAL WRAPPER` only if there is more than one; `OMIT QUOTES` takes the quotes off a string.

`json_agg`, `jsonb_agg`, `json_object_agg`, `jsonb_object_agg`, `JSON_ARRAYAGG`, `JSON_OBJECTAGG`
: A group's values as an array, or its key/value pairs as an object. SQL `NULL`s are JSON `null` in `json_agg` and
  `jsonb_agg`, and left out by `JSON_ARRAYAGG` (the default `ABSENT ON NULL`). Of no rows, an aggregate gives `NULL`.

`json_each`, `jsonb_each`, `json_each_text`, `jsonb_each_text`, `json_array_elements`, `jsonb_array_elements`, `json_array_elements_text`, `jsonb_array_elements_text`, `json_object_keys`, `jsonb_object_keys`
: Rows of the members of an object, the elements of an array, or the keys of an object. They are used in `FROM` (and
  `CROSS JOIN LATERAL`); `WITH ORDINALITY` numbers the rows.

`JSON_TABLE`
: Rows of a JSON document: *path* picks the items, and each column is read from an item with its own path. A column
  `FOR ORDINALITY` numbers the rows, `EXISTS PATH` gives whether the path finds something, `FORMAT JSON` keeps the JSON,
  and `NESTED PATH ... COLUMNS` unnests an array of the item into more rows (the parent's columns repeat; an empty
  array leaves one row with `NULL`s). It may refer to earlier tables of the `FROM` list.

## Remarks

- A `jsonb` value prints as PostgreSQL prints it (`{"a": 1, "b": [1, 2]}`), a `json` value as it was written. The JSON that
  the functions build is compact text (`{"a":1}`, `[1,2]`), except `json_build_object` (`{"a" : 1, "b" : 2}`).
- A JSON column needs no special syntax: `CREATE TABLE docs (id int PRIMARY KEY, body jsonb)` (example C). A `btree`
  index on an expression such as `(body ->> 'user')` works.
- The text of a path (`'$.a[*] ? (@ > 1)'`) is checked when the function runs; a path that cannot be parsed is 42601.

## Differences from PostgreSQL

- **Unnamed columns.** The column of an SQL/JSON function, a JSON operator or `to_json` that has no `AS` is named by an
  internal name of lexdb's (`#jsonb_arrow`, `#json_value`, `#to_json`); PostgreSQL says `?column?` or the function's name.
  Give such a column an alias, as the examples do. A single-column set-returning function in `FROM` names its column
  after the alias (`FROM json_array_elements(...) AS el` gives column `el`; PostgreSQL: `value`).
- **A set-returning JSON function in the select list** (`SELECT json_object_keys(doc)`, `SELECT jsonb_path_query(...)`)
  gives wrong rows (one empty row). Use it in `FROM` (example H).
- **Text of nested values.** `->>`, `#>>`, `jsonb_each_text` and `jsonb_array_elements_text` of an object or an array give
  compact text (`{"b":[10,20,30]}`); PostgreSQL's is `{"b": [10, 20, 30]}`. `json_agg`, `json_object_agg`, `JSON_ARRAYAGG`,
  `JSON_OBJECTAGG`, `JSON_OBJECT`, `JSON_ARRAY`, `JSON_QUERY`, `JSON_SERIALIZE`, `json_object` and `array_to_json` give
  compact JSON (`[1,2,null]`;
  PostgreSQL: `[1, 2, null]`, `{ "a" : 1 }`, `{"a" : "1"}`). `json_object_agg` keeps the last of a repeated key
  (PostgreSQL's keeps both).
- `jsonb_pretty` indents by two spaces and ends with a blank line (PostgreSQL: four spaces).
- `to_json(timestamp '2020-01-02 03:04:05')` is `"2020-01-02 03:04:05"` (PostgreSQL: `"2020-01-02T03:04:05"`), and
  `to_json` of a two-dimensional array makes an array of strings (`["{1,2}","{3,4}"]`; PostgreSQL: `[[1,2],[3,4]]`).
- `JSON_QUERY ... WITH CONDITIONAL WRAPPER` wraps a single item (`[1]`; PostgreSQL: `1`), and with `OMIT QUOTES` and the
  default `jsonb` result a string comes out as `x` (PostgreSQL: `NULL`, since `x` is not `jsonb`). `JSON_EXISTS` and
  `JSON_QUERY` apply their `ON ERROR` to text that is not JSON (`JSON_EXISTS('bad', '$.a' TRUE ON ERROR)` is true);
  PostgreSQL gives 22P02. A `JSON_TABLE` column with `NULL ON ERROR` whose value does not convert (`"a"` as `int`) is
  22P02 (PostgreSQL: `NULL`); `JSON_VALUE ... RETURNING int` applies its `ON ERROR` to such a value.
- **Error texts** are shorter: `invalid input syntax for type json: "{bad}"` (for `jsonb` too) has no `LINE`, `DETAIL`
  or `CONTEXT`; `JSON_VALUE` says `no SQL/JSON item` and `SQL/JSON scalar required` (PostgreSQL: `no SQL/JSON item found
  for specified path`, `JSON path expression in JSON_VALUE must return single scalar item`); a null key in
  `json_object_agg` is `field name must not be null` (PostgreSQL: `null value not allowed for object key`);
  `json_object_keys` of an array says `non-object` (PostgreSQL: `an array`); a jsonpath arithmetic error says
  `arithmetic operands in jsonpath must be single numbers`.
- `IS JSON` of a value that is not text (`5 IS JSON`) is true, as for the text `5`; PostgreSQL: 42804. A path variable that `vars` does not
  give (`$x`) is not an error: the path finds nothing. `jsonb_insert` of an existing object key returns the target
  (PostgreSQL: 22023).
- A JSON number beyond `double` keeps its text (`'1e400'::jsonb` prints `1e400`; PostgreSQL prints the 401 digits).
- **Ordering of `jsonb`.** `null` < string < number < boolean < array < object, but PostgreSQL puts an empty array
  before `null`. `SELECT DISTINCT body ... ORDER BY body` sorts an array before `null`; without `DISTINCT` the order is right.
- `json` has `=` here (PostgreSQL: there is no operator `json = json`).
- **Not supported.** `GIN` indexes (`CREATE INDEX ... USING gin` is refused); subscripts (`body['a']`, `UPDATE ... SET
  body['a'] = ...`); `jsonb_set_lax`, `jsonb_concat`, `jsonb_each` of one argument in the select list, `json_each_text`
  in the select list, and every function that takes a column definition list (`jsonb_to_record`, `jsonb_to_recordset`,
  `json_to_record`, `jsonb_populate_record`, `json_populate_record`); `row_to_json` and `to_jsonb` of a whole row or of a
  subquery's alias (`to_jsonb(d)`); an `ARRAY[[1,2],[3,4]]` literal (a syntax error).
- `JSON_OBJECT(KEY 'k' VALUE 'v')` is accepted (PostgreSQL does not know `KEY`).

## Examples

### A. Values of the two types

`json` keeps the text; `jsonb` sorts the keys, keeps the last of a repeated key and prints with spaces.

<!-- example: postgresql -->
```sql
SELECT '{"b": 1,  "a": [1, 2], "b": 3}'::json AS j,
       '{"b": 1,  "a": [1, 2], "b": 3}'::jsonb AS jb;
SELECT '{"b":1,"aa":2,"a":3}'::jsonb AS keys_sorted,
       '[1,2,3]'::jsonb = '[1, 2, 3]'::jsonb AS same,
       'null'::jsonb IS NULL AS sql_null,
       jsonb_typeof('null') AS json_type;
```

```text
               j                |          jb
--------------------------------+-----------------------
 {"b": 1,  "a": [1, 2], "b": 3} | {"a": [1, 2], "b": 3}
(1 row)

        keys_sorted        | same | sql_null | json_type
---------------------------+------+----------+-----------
 {"a": 3, "b": 1, "aa": 2} | t    | f        | null
(1 row)
```

### B. Operators

<!-- example: postgresql -->
```sql
SELECT '{"a":{"b":[10,20,30]}}'::jsonb -> 'a' -> 'b' -> 1 AS second,
       '{"a":{"b":[10,20,30]}}'::jsonb -> 'a' -> 'b' -> -1 AS last,
       '{"a":{"b":[10,20,30]}}'::jsonb #>> '{a,b,0}' AS first_text,
       '{"a":"x"}'::jsonb ->> 'a' AS as_text,
       '{"a":1}'::jsonb -> 'zz' AS missing;
SELECT '{"a":1,"b":2}'::jsonb @> '{"b":2}' AS contains,
       '{"a":1}'::jsonb <@ '{"a":1,"b":2}' AS contained,
       '{"a":1,"b":2}'::jsonb ? 'a' AS has_key,
       '{"a":1,"b":2}'::jsonb ?| array['z','b'] AS has_any,
       '{"a":1,"b":2}'::jsonb ?& array['a','b'] AS has_all;
SELECT '{"a":1}'::jsonb || '{"b":2,"a":9}'::jsonb AS merged,
       '[1,2]'::jsonb || '[3]'::jsonb AS joined,
       '{"a":1,"b":2}'::jsonb - 'a' AS without_a,
       '["a","b","c"]'::jsonb - 1 AS without_1,
       '{"a":{"b":[1,2,3]}}'::jsonb #- '{a,b,1}' AS without_path;
SELECT '{"a":[1,2,3]}'::jsonb @? '$.a[*] ? (@ > 2)' AS found,
       '{"a":[1,2,3]}'::jsonb @@ '$.a[0] == 1' AS predicate;
```

```text
 second | last | first_text | as_text | missing
--------+------+------------+---------+---------
 20     | 30   | 10         | x       |
(1 row)

 contains | contained | has_key | has_any | has_all
----------+-----------+---------+---------+---------
 t        | t         | t       | t       | t
(1 row)

      merged      |  joined   | without_a | without_1  |     without_path
------------------+-----------+-----------+------------+----------------------
 {"a": 9, "b": 2} | [1, 2, 3] | {"b": 2}  | ["a", "c"] | {"a": {"b": [1, 3]}}
(1 row)

 found | predicate
-------+-----------
 t     | t
(1 row)
```

### C. A table with a `jsonb` column

<!-- example: postgresql -->
```sql
CREATE TABLE docs (id int PRIMARY KEY, body jsonb);
INSERT INTO docs VALUES
  (1, '{"user": "Ann", "tags": ["sql", "json"], "score": 90}'),
  (2, '{"user": "Bob", "tags": ["db"], "score": 75}'),
  (3, NULL);
CREATE INDEX docs_user ON docs ((body ->> 'user'));
SELECT id, body ->> 'user' AS usr, body -> 'tags' ->> 0 AS first_tag
FROM docs
WHERE body @> '{"tags": ["sql"]}'
ORDER BY id;
UPDATE docs SET body = jsonb_set(body, '{score}', to_jsonb((body ->> 'score')::int + 5)) WHERE id = 2;
SELECT id, body ->> 'score' AS score FROM docs ORDER BY id;
INSERT INTO docs VALUES (4, '{"a":');
```

```text
CREATE TABLE
INSERT 0 3
CREATE INDEX
 id | usr | first_tag
----+-----+-----------
  1 | Ann | sql
(1 row)

UPDATE 1
 id | score
----+-------
  1 | 90
  2 | 80
  3 |
(3 rows)

ERROR:  invalid input syntax for type jsonb: "{"a":"
```

### D. Inspecting and changing a value

<!-- example: postgresql -->
```sql
SELECT jsonb_set('{"a":{"b":1}}', '{a,b}', '2') AS replaced,
       jsonb_set('{"a":{"b":1}}', '{a,c}', '3') AS added,
       jsonb_set('{"a":{"b":1}}', '{a,c}', '3', false) AS not_added;
SELECT jsonb_insert('{"a":[1,2]}', '{a,0}', '0') AS before,
       jsonb_insert('{"a":[1,2]}', '{a,1}', '9', true) AS after;
SELECT jsonb_strip_nulls('{"a":null,"b":[1,null]}') AS objects,
       jsonb_strip_nulls('{"a":null,"b":[1,null]}', true) AS arrays_too;
SELECT json_typeof('"x"') AS t1, jsonb_typeof('[1]') AS t2, jsonb_array_length('[1,2,3]') AS n,
       jsonb_extract_path_text('{"a":{"b":5}}', 'a', 'b') AS path_text;
SELECT jsonb_pretty('{"a":[1,2],"b":{"c":1}}');
```

```text
    replaced     |          added          |    not_added
-----------------+-------------------------+-----------------
 {"a": {"b": 2}} | {"a": {"b": 1, "c": 3}} | {"a": {"b": 1}}
(1 row)

      before      |      after
------------------+------------------
 {"a": [0, 1, 2]} | {"a": [1, 2, 9]}
(1 row)

     objects      | arrays_too
------------------+------------
 {"b": [1, null]} | {"b": [1]}
(1 row)

   t1   |  t2   | n | path_text
--------+-------+---+-----------
 string | array | 3 | 5
(1 row)

 jsonb_pretty
--------------
 {           +
   "a": [    +
     1,      +
     2       +
   ],        +
   "b": {    +
     "c": 1  +
   }         +
 }           +

(1 row)
```

### E. Path functions

<!-- example: postgresql -->
```sql
SELECT jsonb_path_exists('{"a":[1,2,3]}', '$.a[*] ? (@ > $x)', '{"x":2}') AS found,
       jsonb_path_match('{"a":[1,2,3]}', 'exists($.a[*] ? (@ > 2))') AS matched,
       jsonb_path_query_array('{"a":[1,2,3]}', '$.a[*] ? (@ > 1)') AS items,
       jsonb_path_query_first('{"a":[1,2,3]}', '$.a[*] ? (@ > 1)') AS first_item,
       jsonb_path_query_array('{"a":[1,2,3]}', '$.a[1] * 10') AS arithmetic,
       jsonb_path_query_array('{"a":"x"}', '$.a.type()') AS the_type;
SELECT * FROM jsonb_path_query('{"a":[1,2,3]}', '$.a[*] ? (@ > 1)') AS item;
SELECT jsonb_path_exists('{"a":1}', 'strict $.b') AS strict_missing;
SELECT jsonb_path_exists('{"a":1}', 'strict $.b', '{}', true) AS silenced;
```

```text
 found | matched | items  | first_item | arithmetic |  the_type
-------+---------+--------+------------+------------+------------
 t     | t       | [2, 3] | 2          | [20]       | ["string"]
(1 row)

 item
------
 2
 3
(2 rows)

ERROR:  JSON object does not contain key "b"
 silenced
----------

(1 row)
```

### F. Building JSON

<!-- example: postgresql -->
```sql
SELECT to_jsonb(ARRAY[1,2,3]) AS arr, to_json('a "q"'::text) AS str, to_jsonb(1.50::numeric) AS num;
SELECT json_build_object('a', 1, 'b', ARRAY[1,2], 'c', NULL) AS obj, jsonb_build_array(1, 'x', NULL, true) AS arr;
SELECT json_object('{a,1,b,2}') AS obj, jsonb_object('{a,b}', '{1,2}') AS obj2;
SELECT JSON_OBJECT('a': 1, 'b': NULL) AS keeps_null,
       JSON_OBJECT('a': 1, 'b': NULL ABSENT ON NULL) AS drops_null,
       JSON_ARRAY(1, 'a', NULL, true) AS arr,
       JSON_ARRAY(1, NULL NULL ON NULL RETURNING jsonb) AS arr_null,
       JSON_ARRAY(SELECT x FROM (VALUES (1), (2)) AS v(x)) AS from_query,
       JSON_SCALAR('a') AS scalar;
SELECT JSON('{"a" : 1}') AS j, JSON_SERIALIZE('{"a" : 1}'::json RETURNING text) AS s;
```

```text
    arr    |    str    | num
-----------+-----------+------
 [1, 2, 3] | "a \"q\"" | 1.50
(1 row)

                obj                 |         arr
------------------------------------+----------------------
 {"a" : 1, "b" : [1,2], "c" : null} | [1, "x", null, true]
(1 row)

        obj        |         obj2
-------------------+----------------------
 {"a":"1","b":"2"} | {"a": "1", "b": "2"}
(1 row)

    keeps_null    | drops_null |     arr      | arr_null  | from_query | scalar
------------------+------------+--------------+-----------+------------+--------
 {"a":1,"b":null} | {"a":1}    | [1,"a",true] | [1, null] | [1,2]      | "a"
(1 row)

     j     |    s
-----------+---------
 {"a" : 1} | {"a":1}
(1 row)
```

### G. Aggregates

<!-- example: postgresql -->
```sql
SELECT json_agg(x) AS j, jsonb_agg(x ORDER BY x DESC) AS jb
FROM (VALUES (1), (2), (NULL)) AS v(x);
SELECT json_object_agg(k, v) AS j, jsonb_object_agg(k, v) AS jb
FROM (VALUES ('b', 1), ('a', 2)) AS t(k, v);
SELECT JSON_ARRAYAGG(x ORDER BY x) AS dropped, JSON_ARRAYAGG(x NULL ON NULL) AS kept
FROM (VALUES (2), (1), (NULL)) AS v(x);
SELECT JSON_OBJECTAGG(k : v) AS obj, JSON_OBJECTAGG(k : v ABSENT ON NULL) AS no_nulls
FROM (VALUES ('a', 1), ('b', NULL)) AS t(k, v);
SELECT g, jsonb_agg(x) AS xs FROM (VALUES (1, 'a'), (1, 'b'), (2, 'c')) AS v(g, x) GROUP BY g ORDER BY g;
SELECT jsonb_agg(x) AS none FROM (SELECT 1 AS x WHERE false) AS v;
```

```text
     j      |      jb
------------+--------------
 [1,2,null] | [null, 2, 1]
(1 row)

       j       |        jb
---------------+------------------
 {"b":1,"a":2} | {"a": 2, "b": 1}
(1 row)

 dropped |    kept
---------+------------
 [1,2]   | [2,1,null]
(1 row)

       obj        | no_nulls
------------------+----------
 {"a":1,"b":null} | {"a":1}
(1 row)

 g |     xs
---+------------
 1 | ["a", "b"]
 2 | ["c"]
(2 rows)

 none
------

(1 row)
```

### H. Rows from JSON

<!-- example: postgresql -->
```sql
SELECT * FROM json_each('{"a":1,"b":[1,2]}') AS e;
SELECT * FROM jsonb_each_text('{"a":1,"b":null}') AS e;
SELECT d.id, t.tag, t.ord
FROM docs d, jsonb_array_elements_text(d.body -> 'tags') WITH ORDINALITY AS t(tag, ord)
ORDER BY d.id, t.ord;
SELECT k FROM jsonb_object_keys('{"b":1,"a":2}') AS k ORDER BY k;
SELECT * FROM json_array_elements('[1,"x",{"a":2}]') AS el;
```

```text
 key | value
-----+-------
 a   | 1
 b   | [1,2]
(2 rows)

 key | value
-----+-------
 a   | 1
 b   |
(2 rows)

 id | tag  | ord
----+------+-----
  1 | sql  |   1
  1 | json |   2
  2 | db   |   1
(3 rows)

 k
---
 a
 b
(2 rows)

   el
---------
 1
 "x"
 {"a":2}
(3 rows)
```

### I. `IS JSON`, `JSON_VALUE`, `JSON_QUERY` and `JSON_EXISTS`

<!-- example: postgresql -->
```sql
SELECT '{"a":1}' IS JSON AS obj, '[1]' IS JSON ARRAY AS arr, '1' IS JSON OBJECT AS not_obj,
       'x' IS NOT JSON AS bad, '{"a":1,"a":2}' IS JSON WITH UNIQUE KEYS AS unique_keys;
SELECT JSON_VALUE('{"a":{"b":7},"s":"x"}', '$.a.b') AS b,
       JSON_VALUE('{"a":{"b":7}}', '$.a.b' RETURNING int) + 1 AS b1,
       JSON_VALUE('{"a":1}', '$.z') AS missing,
       JSON_VALUE('{"a":1}', '$.z' DEFAULT 'none' ON EMPTY) AS dflt,
       JSON_VALUE('{"a":[1,2]}', '$.a') AS not_scalar,
       JSON_VALUE('{"a":"abc"}', '$.a' RETURNING int DEFAULT -1 ON ERROR) AS bad_cast,
       JSON_VALUE('{"a":5}', '$.a ? (@ > $m)' PASSING 3 AS m) AS passing;
SELECT JSON_QUERY('{"a":{"b":[1,2]}}', '$.a') AS obj,
       JSON_QUERY('{"a":[1,2]}', '$.a[*]') AS several_no_wrapper,
       JSON_QUERY('{"a":[1,2]}', '$.a[*]' WITH WRAPPER) AS wrapped,
       JSON_QUERY('{"a":"x"}', '$.a') AS keep_quotes,
       JSON_QUERY('{"a":"x"}', '$.a' RETURNING text OMIT QUOTES) AS omit_quotes,
       JSON_QUERY('{"a":1}', '$.z' EMPTY ARRAY ON EMPTY) AS empty_array;
SELECT JSON_EXISTS('{"a":1}', '$.a') AS yes, JSON_EXISTS('{"a":1}', '$.b') AS no,
       JSON_EXISTS('{"a":[1,5]}', '$.a[*] ? (@ > $x)' PASSING 3 AS x) AS filtered,
       JSON_EXISTS('{"a":1}', 'strict $.b' TRUE ON ERROR) AS on_error;
SELECT JSON_EXISTS('bad', '$.a' TRUE ON ERROR) AS bad_text;
SELECT JSON_VALUE('{"a":1}', '$.z' ERROR ON EMPTY);
SELECT JSON_VALUE('{"a":[1,2]}', '$.a' ERROR ON ERROR);
```

```text
 obj | arr | not_obj | bad | unique_keys
-----+-----+---------+-----+-------------
 t   | t   | f       | t   | f
(1 row)

 b | b1 | missing | dflt | not_scalar | bad_cast | passing
---+----+---------+------+------------+----------+---------
 7 |  8 |         | none |            |       -1 | 5
(1 row)

     obj     | several_no_wrapper | wrapped | keep_quotes | omit_quotes | empty_array
-------------+--------------------+---------+-------------+-------------+-------------
 {"b":[1,2]} |                    | [1,2]   | "x"         | x           | []
(1 row)

 yes | no | filtered | on_error
-----+----+----------+----------
 t   | f  | t        | t
(1 row)

 bad_text
----------
 t
(1 row)

ERROR:  no SQL/JSON item
ERROR:  SQL/JSON scalar required
```

### J. `JSON_TABLE`

<!-- example: postgresql -->
```sql
SELECT * FROM JSON_TABLE('[{"a":1,"b":"x"},{"a":2,"b":"y"}]', '$[*]' COLUMNS (
  n FOR ORDINALITY,
  a int PATH '$.a',
  b text PATH '$.b',
  c text PATH '$.c' DEFAULT 'none' ON EMPTY,
  has_b boolean EXISTS PATH '$.b')) AS jt;
SELECT jt.ord, jt.usr, jt.tag
FROM docs d,
     JSON_TABLE(d.body, '$' COLUMNS (
       ord FOR ORDINALITY,
       usr text PATH '$.user',
       NESTED PATH '$.tags[*]' COLUMNS (tag text PATH '$'))) AS jt
ORDER BY d.id, jt.tag;
SELECT * FROM JSON_TABLE('{"k":[{"n":"p","v":[1,2]}]}', '$.k[*]' COLUMNS (
  n text PATH '$.n', vs jsonb FORMAT JSON PATH '$.v')) AS jt;
SELECT * FROM JSON_TABLE('{"a":1}', '$.q' COLUMNS (i int PATH '$') ERROR ON ERROR) AS jt;
```

```text
 n | a | b |  c   | has_b
---+---+---+------+-------
 1 | 1 | x | none | t
 2 | 2 | y | none | t
(2 rows)

 ord | usr | tag
-----+-----+------
   1 | Ann | json
   1 | Ann | sql
   1 | Bob | db
(3 rows)

 n |   vs
---+--------
 p | [1, 2]
(1 row)

 i
---
(0 rows)
```

### K. Errors

<!-- example: postgresql -->
```sql
SELECT '{bad}'::jsonb;
SELECT '[1,2'::json;
SELECT json_build_object(NULL, 1);
SELECT JSON_OBJECT('a': 1, 'a': 2 WITH UNIQUE KEYS);
SELECT jsonb_array_length('{"a":1}');
SELECT json_object_keys('[1]');
```

```text
ERROR:  invalid input syntax for type jsonb: "{bad}"
ERROR:  invalid input syntax for type json: "[1,2"
ERROR:  null value not allowed for object key
ERROR:  duplicate JSON object key value: "a"
ERROR:  cannot get array length of a non-array
ERROR:  cannot call json_object_keys on a non-object
```

### L. `json` and `jsonb` as column types and in a primary key

<!-- example: postgresql -->
```sql
CREATE TABLE kinds (id int PRIMARY KEY, j json, b jsonb);
INSERT INTO kinds VALUES (1, '{"x": 1,  "y": [1, 2]}', '{"x": 1,  "y": [1, 2]}'), (2, NULL, 'null'), (3, '[1,2,3]', '[3,1,2]');
SELECT * FROM kinds ORDER BY id;
SELECT id, b IS NULL AS sql_null, b = 'null'::jsonb AS json_null FROM kinds ORDER BY id;
SELECT DISTINCT b FROM kinds ORDER BY b;
DROP TABLE kinds;
```

```text
CREATE TABLE
INSERT 0 3
 id |           j            |           b
----+------------------------+-----------------------
  1 | {"x": 1,  "y": [1, 2]} | {"x": 1, "y": [1, 2]}
  2 |                        | null
  3 | [1,2,3]                | [3, 1, 2]
(3 rows)

 id | sql_null | json_null
----+----------+-----------
  1 | f        | f
  2 | f        | t
  3 | f        | f
(3 rows)

           b
-----------------------
 [3, 1, 2]
 null
 {"x": 1, "y": [1, 2]}
(3 rows)

DROP TABLE
```

## See also

[Operators](operators.md) · [Aggregate functions](functions-aggregate.md) · [Set-returning functions](functions-srf.md) ·
[Data types](data-types-other.md) · [CREATE TABLE](create-table.md)
