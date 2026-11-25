# JSON and SQL/JSON (Oracle)

The `JSON` data type, `IS JSON`, the query functions `JSON_VALUE`, `JSON_QUERY` and `JSON_EXISTS`, the constructors
`JSON`, `JSON_OBJECT` and `JSON_ARRAY`, the aggregates `JSON_ARRAYAGG` and `JSON_OBJECTAGG`, `JSON_SERIALIZE`,
`JSON_MERGEPATCH`, `JSON_EQUAL`, `JSON_TRANSFORM`, and `JSON_TABLE`.

**Door:** Oracle (TNS). **Follows:** Oracle Database 23ai (checked on Oracle Free 23.26.3).

## Syntax

```
JSON ( expression [ { WITH | WITHOUT } UNIQUE [ KEYS ] ] )                                → JSON
expression IS [ NOT ] JSON [ VALUE | SCALAR | ARRAY | OBJECT ] [ { WITH | WITHOUT } UNIQUE [ KEYS ] ]

JSON_VALUE ( expression , path [ RETURNING type ] [ { ERROR | NULL | DEFAULT literal } ON EMPTY ]
             [ { ERROR | NULL | DEFAULT literal } ON ERROR ] )
JSON_QUERY ( expression , path [ RETURNING type ] [ { WITHOUT | WITH [ CONDITIONAL | UNCONDITIONAL ] } [ ARRAY ] WRAPPER ]
             [ { ERROR | NULL | EMPTY [ ARRAY | OBJECT ] } ON EMPTY ] [ { ERROR | NULL | EMPTY [ ARRAY | OBJECT ] } ON ERROR ] )
JSON_EXISTS ( expression , path [ PASSING value AS "name" [, ...] ] [ { ERROR | TRUE | FALSE } ON ERROR ] )

JSON_OBJECT ( [ [ KEY ] key VALUE value | key : value [, ...] ] [ { NULL | ABSENT } ON NULL ]
              [ RETURNING type ] [ { WITH | WITHOUT } UNIQUE [ KEYS ] ] )
JSON_ARRAY ( [ value [, ...] ] [ { NULL | ABSENT } ON NULL ] [ RETURNING type ] )
JSON_ARRAYAGG ( expression [ ORDER BY ... ] [ { NULL | ABSENT } ON NULL ] [ RETURNING type ] )
JSON_OBJECTAGG ( [ KEY ] key VALUE value [ { NULL | ABSENT } ON NULL ] [ RETURNING type ] [ { WITH | WITHOUT } UNIQUE [ KEYS ] ] )

JSON_SERIALIZE ( expression [ RETURNING type ] [ PRETTY ] )
JSON_MERGEPATCH ( target , patch [ RETURNING type ] [ PRETTY ] )
JSON_EQUAL ( expression , expression )
JSON_TRANSFORM ( expression , operation [, ...] [ RETURNING type ] )
   operation: { SET | INSERT | REPLACE | APPEND } path = value | REMOVE path

JSON_TABLE ( expression , path COLUMNS ( column_definition [, ...] ) [ { ERROR | NULL | EMPTY } ON ERROR ] ) [ alias ]
   column_definition: name FOR ORDINALITY
                    | name type [ FORMAT JSON ] PATH path [ wrapper ] [ ON EMPTY ] [ ON ERROR ]
                    | name type EXISTS PATH path
                    | NESTED [ PATH ] path COLUMNS ( column_definition [, ...] )
```

## Arguments

`JSON`
: The type. A `JSON` column holds a valid JSON document (an object, an array or a scalar), `NULL` for none. It is
  shown as text, in the form it was given. `USER_TAB_COLUMNS.DATA_TYPE` is `JSON`. A `VARCHAR2` or `CLOB` column holds
  JSON as text, usually with a `CHECK (col IS JSON)` constraint.

*path*
: A SQL/JSON path: `$` the document, `.name` a member, `[n]` an element, `[*]` every element, and a filter `? (@.score >
  80)`. A name in `PASSING` is a quoted identifier (`PASSING 80 AS "min"`, used as `$min`).

`JSON_VALUE`
: One scalar at the path, as `VARCHAR2(4000)` or the `RETURNING` type (`NUMBER`, `DATE`, `VARCHAR2(n)`, `CLOB`...). A path that finds
  nothing gives `NULL` (or what `ON EMPTY` says), an object or array there gives `NULL` (`ON ERROR`).

`JSON_QUERY`
: An object, an array, or with a wrapper any items, as JSON text. `WITH WRAPPER` always puts the items in an array, `WITH CONDITIONAL
  WRAPPER` only when there is not exactly one object or array. `EMPTY ARRAY ON EMPTY` gives `[]` where nothing is found.

`JSON_EXISTS`
: True when the path finds an item. It is a condition, used in `WHERE` and `CASE`.

`JSON_OBJECT`, `JSON_ARRAY`
: JSON built from values. `ABSENT ON NULL` leaves a `NULL` out; `NULL ON NULL` (the default of `JSON_OBJECT`) writes `null`.
  The default of `JSON_ARRAY` is `ABSENT ON NULL`.

`JSON_ARRAYAGG`, `JSON_OBJECTAGG`
: An array of a group's values, an object of its key/value pairs.

`JSON_SERIALIZE`
: A JSON value as text (`VARCHAR2`, or `RETURNING CLOB`); `PRETTY` indents it.

`JSON_MERGEPATCH`
: RFC 7396 merge patch: members of the patch replace the target's, a `null` removes one.

`JSON_EQUAL`
: True when two JSON values are the same whatever the order of the keys and the spacing. A condition.

`JSON_TRANSFORM`
: Changes a document with `SET` (replace or add), `INSERT` (add; error when it exists), `REPLACE` (only when it exists), `APPEND` (to an array)
  and `REMOVE`.

`JSON_TABLE`
: Rows of a document: the path picks the items, each column reads its own path. `FOR ORDINALITY` numbers the rows, `EXISTS PATH` gives
  `true` or `false`, `FORMAT JSON` keeps an object or array, `NESTED PATH ... COLUMNS` unnests an array into more rows.
  It may use the columns of tables to its left in `FROM`.

## Remarks

- A `JSON` value is stored and shown as text. `ORDER BY`, `GROUP BY` and `DISTINCT` of a `JSON` column work, as in Oracle 23ai.
- `JSON_VALUE`, `JSON_QUERY` and `JSON_TABLE` name a path in single quotes. A filter uses `@` and `$name`.
- `JSON_EXISTS` and `JSON_EQUAL` are conditions, not values: use them in `WHERE` or `CASE WHEN`.

## Differences from Oracle

- **Errors** have lexdb's own text, mostly under ORA-20000 or ORA-01722 where Oracle says ORA-40441 (invalid JSON text), ORA-40456 (not a scalar), ORA-40462
  (no value), ORA-40473 (duplicate key), ORA-40597 (bad path) or ORA-40656. Text that is not JSON in an `INSERT` into a `JSON` column is ORA-01722 (Oracle:
  ORA-40441 `JSON syntax error`); a `CHECK (col IS JSON)` violation is `ORA-02290: check constraint violated` without the constraint's name. A path that is
  not well formed gives `NULL` (Oracle: ORA-40597). `JSON_VALUE` with `RETURNING NUMBER` of a string is ORA-01722 (Oracle: ORA-03302 with details).
- **`PASSING`**: a quoted name (`PASSING 80 AS "min"`, which Oracle requires) does not bind in lexdb: the filter finds nothing, so `JSON_EXISTS` is false and
  `JSON_VALUE` is `NULL` (example F). An unquoted name (`PASSING 80 AS min`) works, which Oracle refuses with ORA-40656.
- `JSON_QUERY ... WITH CONDITIONAL WRAPPER` wraps a single scalar (`["x"]`; Oracle: `"x"`).
- `JSON_SERIALIZE ... PRETTY` and `JSON_MERGEPATCH ... PRETTY` indent by two spaces with `"a": 1` (Oracle: `"a" : 1`, and `[` on a line of its own).
- `JSON_OBJECT` with two members of one key keeps the last (`{"a":2}`; Oracle keeps both); `WITH UNIQUE KEYS` is ORA-20000 (Oracle: ORA-40473).
  `JSON(' {"a" : 1 } ')` keeps the spaces (Oracle: `{"a":1}`). `JSON_OBJECTAGG` writes a `VARCHAR2` column that has a `CHECK (... IS JSON)` constraint as embedded
  JSON (`{"1":{"a":1}}`; Oracle: a string `"{\"a\":1}"`). `JSON_EXISTS ... TRUE ON ERROR` gives true for text that is not JSON (Oracle: ORA-40441).
  `IS JSON ARRAY`, `OBJECT`, `SCALAR` and `WITH UNIQUE KEYS` of text are accepted (Oracle: ORA-61763, they are for the `JSON` type only: the examples
  apply them to `JSON(...)`).
- `JSON_TRANSFORM(... INSERT '$.name' = 'x')` of a member that exists returns the document unchanged (Oracle: ORA-40763).
- `JSON_TABLE`: an `EXISTS PATH` column shows `t` or `f` (Oracle: `true` or `false`), and a column whose value does not convert gives ORA-01722 whatever its
  `ON ERROR` says (`NULL ON ERROR DEFAULT 0 ON EMPTY` of a string is ORA-01722; Oracle gives `NULL`).
- **Not supported** (each is ORA-00900 or ORA-00904): the simple dot notation (`d.doc.name`, `d.doc.tags[0]`, `d.doc.score.number()`), `IS JSON STRICT` and `LAX`,
  `JSON_OBJECT(*)`, `FORMAT JSON` in `JSON_ARRAY`, `JSON_ARRAY ( query )`, `PRETTY` in `JSON_QUERY`, `JSON_TRANSFORM`'s `KEEP`, `PREPEND`, `NESTED PATH`, `IGNORE ON`,
  `RETURNING`, `FORMAT JSON` and `JSON(...)` as a value (and its `RENAME`, which sets the value instead of renaming the key), `TREAT(... AS JSON)`, `CAST(... AS JSON)`,
  a `JSON_TABLE` column list without types (`COLUMNS (a, b)`), and `CREATE SEARCH INDEX ... FOR JSON`
  (a function-based index `ON t (JSON_VALUE(doc, '$.name'))` works).

## Examples

### A. A `JSON` column

<!-- example: oracle -->
```sql
CREATE TABLE jdocs (id NUMBER PRIMARY KEY, doc JSON, note VARCHAR2(200) CHECK (note IS JSON));
INSERT INTO jdocs VALUES (1, '{"name":"Ann","score":90,"tags":["x","y"],"addr":{"city":"Oslo"}}', '{"a":1}');
INSERT INTO jdocs VALUES (2, '{"name":"Bob","score":75,"tags":[]}', '[1,2]');
INSERT INTO jdocs VALUES (3, NULL, NULL);
INSERT INTO jdocs (id, note) VALUES (5, 'not json');
SELECT id, doc FROM jdocs ORDER BY id;
SELECT column_name, data_type FROM user_tab_columns WHERE table_name = 'JDOCS' ORDER BY column_id;
```

```text
Table created.

1 row created.

1 row created.

1 row created.

ERROR:
ORA-02290: check constraint violated

ID DOC
-- -----------------------------------------------------------------
 1 {"name":"Ann","score":90,"tags":["x","y"],"addr":{"city":"Oslo"}}
 2 {"name":"Bob","score":75,"tags":[]}
 3

3 rows selected.

COLUMN_NAME DATA_TYPE
----------- ---------
ID          NUMBER
DOC         JSON
NOTE        VARCHAR2

3 rows selected.
```

### B. `JSON_VALUE`, `JSON_QUERY` and `JSON_EXISTS`

<!-- example: oracle -->
```sql
SELECT JSON_VALUE(doc, '$.name') AS nm,
       JSON_VALUE(doc, '$.score' RETURNING NUMBER) + 1 AS sc,
       JSON_VALUE(doc, '$.addr.city') AS city,
       JSON_VALUE(doc, '$.zz') AS missing,
       JSON_VALUE(doc, '$.tags') AS not_scalar
FROM jdocs WHERE id = 1;
SELECT JSON_VALUE(doc, '$.zz' DEFAULT 'none' ON EMPTY) AS dflt,
       JSON_VALUE(doc, '$.name' RETURNING NUMBER DEFAULT -1 ON ERROR) AS bad_number
FROM jdocs WHERE id = 1;
SELECT JSON_QUERY(doc, '$.addr') AS obj, JSON_QUERY(doc, '$.tags') AS arr,
       JSON_QUERY(doc, '$.name') AS scalar_, JSON_QUERY(doc, '$.name' WITH WRAPPER) AS wrapped,
       JSON_QUERY(doc, '$.zz' EMPTY ARRAY ON EMPTY) AS empty_arr
FROM jdocs WHERE id = 1;
SELECT JSON_QUERY(doc, '$.tags[*]' WITH WRAPPER) AS w, JSON_QUERY(doc, '$.tags[*]' WITH CONDITIONAL WRAPPER) AS c
FROM jdocs WHERE id = 1;
SELECT id FROM jdocs WHERE JSON_EXISTS(doc, '$.addr');
SELECT id FROM jdocs WHERE JSON_EXISTS(doc, '$.score ? (@ > 80)');
SELECT id FROM jdocs WHERE NOT JSON_EXISTS(doc, '$.addr') AND doc IS NOT NULL;
SELECT CASE WHEN '{"a":1}' IS JSON THEN 'yes' ELSE 'no' END AS obj,
       CASE WHEN 'x' IS JSON THEN 'yes' ELSE 'no' END AS bad,
       CASE WHEN JSON('[1]') IS JSON ARRAY THEN 'yes' ELSE 'no' END AS arr,
       CASE WHEN JSON('1') IS JSON SCALAR THEN 'yes' ELSE 'no' END AS scalar_
FROM dual;
```

```text
NM  SC CITY MISSING NOT_SCALAR
--- -- ---- ------- ----------
Ann 91 Oslo

1 row selected.

DFLT BAD_NUMBER
---- ----------
none         -1

1 row selected.

OBJ             ARR       SCALAR_ WRAPPED EMPTY_ARR
--------------- --------- ------- ------- ---------
{"city":"Oslo"} ["x","y"] "Ann"   ["Ann"] []

1 row selected.

W         C
--------- ---------
["x","y"] ["x","y"]

1 row selected.

ID
--
 1

1 row selected.

ID
--
 1

1 row selected.

ID
--
 2

1 row selected.

OBJ BAD ARR SCALAR_
--- --- --- -------
yes no  yes yes

1 row selected.
```

### C. Building JSON

<!-- example: oracle -->
```sql
SELECT JSON_OBJECT('a' VALUE 1, 'b' VALUE NULL, 'c' VALUE 'x') AS keeps_null,
       JSON_OBJECT('a' VALUE 1, 'b' VALUE NULL ABSENT ON NULL) AS drops_null,
       JSON_OBJECT(KEY 'k' VALUE 'v') AS key_value,
       JSON_OBJECT('k': 5) AS colon,
       JSON_OBJECT() AS empty_obj
FROM dual;
SELECT JSON_ARRAY(1, 'a', NULL, 2.5) AS arr,
       JSON_ARRAY(1, NULL NULL ON NULL) AS keeps_null,
       JSON_ARRAY() AS empty_arr,
       JSON_ARRAY(JSON_OBJECT('x' VALUE 1), JSON_ARRAY(1)) AS nested
FROM dual;
SELECT JSON_ARRAYAGG(id ORDER BY id) AS ids FROM jdocs;
SELECT JSON_OBJECTAGG(KEY TO_CHAR(id) VALUE note) AS notes, JSON_OBJECTAGG(KEY TO_CHAR(id) VALUE note NULL ON NULL) AS with_nulls FROM jdocs;
SELECT JSON('{"a":1,"b":[true,null]}') AS j, JSON_SERIALIZE('{"a" : [1, 2]}') AS s FROM dual;
SELECT JSON_SERIALIZE(doc RETURNING CLOB) AS s FROM jdocs WHERE id = 2;
```

```text
KEEPS_NULL               DROPS_NULL KEY_VALUE COLON   EMPTY_OBJ
------------------------ ---------- --------- ------- ---------
{"a":1,"b":null,"c":"x"} {"a":1}    {"k":"v"} {"k":5} {}

1 row selected.

ARR         KEEPS_NULL EMPTY_ARR NESTED
----------- ---------- --------- -------------
[1,"a",2.5] [1,null]   []        [{"x":1},[1]]

1 row selected.

IDS
-------
[1,2,3]

1 row selected.

NOTES                                  WITH_NULLS
-------------------------------------- --------------------------------------
{"1":"{\"a\":1}","2":"[1,2]","3":null} {"1":"{\"a\":1}","2":"[1,2]","3":null}

1 row selected.

J                       S
----------------------- -----------
{"a":1,"b":[true,null]} {"a":[1,2]}

1 row selected.

S
-----------------------------------
{"name":"Bob","score":75,"tags":[]}

1 row selected.
```

### D. `JSON_MERGEPATCH`, `JSON_EQUAL` and `JSON_TRANSFORM`

<!-- example: oracle -->
```sql
SELECT JSON_MERGEPATCH('{"a":1,"b":2}', '{"b":null,"c":3}') AS patched FROM dual;
SELECT CASE WHEN JSON_EQUAL('{"a":1,"b":2}', '{"b":2,  "a":1}') THEN 'equal' ELSE 'different' END AS same,
       CASE WHEN JSON_EQUAL('{"a":1}', '{"a":2}') THEN 'equal' ELSE 'different' END AS other
FROM dual;
SELECT JSON_TRANSFORM(doc, SET '$.score' = 95, APPEND '$.tags' = 'vip') AS set_append FROM jdocs WHERE id = 1;
SELECT JSON_TRANSFORM(doc, REMOVE '$.tags', INSERT '$.new' = 1, REPLACE '$.name' = 'Zed') AS remove_insert_replace FROM jdocs WHERE id = 1;
SELECT JSON_TRANSFORM(doc, SET '$.addr.zip' = '0150') AS nested_set FROM jdocs WHERE id = 1;
SELECT JSON_TRANSFORM(doc, INSERT '$.name' = 'x') AS insert_existing FROM jdocs WHERE id = 1;
UPDATE jdocs SET doc = JSON_TRANSFORM(doc, SET '$.score' = 99) WHERE id = 2;
SELECT JSON_VALUE(doc, '$.score') AS score FROM jdocs WHERE id = 2;
```

```text
PATCHED
-------------
{"a":1,"c":3}

1 row selected.

SAME  OTHER
----- ---------
equal different

1 row selected.

SET_APPEND
-----------------------------------------------------------------------
{"name":"Ann","score":95,"tags":["x","y","vip"],"addr":{"city":"Oslo"}}

1 row selected.

REMOVE_INSERT_REPLACE
--------------------------------------------------------
{"name":"Zed","score":90,"addr":{"city":"Oslo"},"new":1}

1 row selected.

NESTED_SET
------------------------------------------------------------------------------
{"name":"Ann","score":90,"tags":["x","y"],"addr":{"city":"Oslo","zip":"0150"}}

1 row selected.

INSERT_EXISTING
-----------------------------------------------------------------
{"name":"Ann","score":90,"tags":["x","y"],"addr":{"city":"Oslo"}}

1 row selected.

1 row updated.

SCORE
-----
99

1 row selected.
```

### E. `JSON_TABLE`

<!-- example: oracle -->
```sql
SELECT jt.*
FROM jdocs d,
     JSON_TABLE(d.doc, '$' COLUMNS (
       nm VARCHAR2(10) PATH '$.name',
       sc NUMBER PATH '$.score',
       city VARCHAR2(10) PATH '$.addr.city',
       has_addr VARCHAR2(5) EXISTS PATH '$.addr',
       tags VARCHAR2(50) FORMAT JSON PATH '$.tags')) jt
ORDER BY d.id;
SELECT d.id, jt.ord, jt.nm, jt.tag
FROM jdocs d,
     JSON_TABLE(d.doc, '$' COLUMNS (
       nm VARCHAR2(10) PATH '$.name',
       NESTED PATH '$.tags[*]' COLUMNS (ord FOR ORDINALITY, tag VARCHAR2(5) PATH '$'))) jt
WHERE d.id <= 2
ORDER BY d.id, jt.ord;
SELECT * FROM JSON_TABLE('[{"a":1},{"a":"x"},{"b":3}]', '$[*]' COLUMNS (
  rn FOR ORDINALITY, a NUMBER PATH '$.a' NULL ON ERROR DEFAULT 0 ON EMPTY));
```

```text
NM  SC CITY HAS_ADDR TAGS
--- -- ---- -------- ---------
Ann 90 Oslo t        ["x","y"]
Bob 99      f        []

2 rows selected.

ID ORD NM  TAG
-- --- --- ---
 1   1 Ann x
 1   2 Ann y
 2     Bob

3 rows selected.

ERROR:
ORA-01722: invalid number
```

### F. Errors and what is not supported

<!-- example: oracle -->
```sql
INSERT INTO jdocs (id, doc) VALUES (4, 'not json');
SELECT JSON_VALUE(doc, '$.tags' ERROR ON ERROR) AS m FROM jdocs WHERE id = 1;
SELECT JSON_VALUE(doc, '$.zz' ERROR ON EMPTY) AS m FROM jdocs WHERE id = 1;
SELECT id FROM jdocs WHERE JSON_EXISTS(doc, '$.score ? (@ > $min)' PASSING 80 AS "min");
SELECT JSON_VALUE(doc, '$.name ? (@ == $n)' PASSING 'Ann' AS "n") AS m FROM jdocs WHERE id = 1;
SELECT JSON('nope') AS j FROM dual;
SELECT JSON_OBJECT('a' VALUE 1, 'a' VALUE 2 WITH UNIQUE KEYS) AS o FROM dual;
SELECT d.doc.name FROM jdocs d WHERE d.id = 1;
```

```text
ERROR:
ORA-01722: invalid number

ERROR:
ORA-20000: SQL/JSON scalar required

ERROR:
ORA-20000: no SQL/JSON item

no rows selected

M
-


1 row selected.

ERROR:
ORA-01722: invalid number

ERROR:
ORA-20000: duplicate JSON object key value: "a"

ERROR:
ORA-00904: invalid identifier
```

### G. A view and an index over JSON

<!-- example: oracle -->
```sql
CREATE INDEX jdocs_name ON jdocs (JSON_VALUE(doc, '$.name'));
CREATE VIEW jdocs_v AS SELECT id, JSON_VALUE(doc, '$.name') AS nm, JSON_VALUE(doc, '$.score' RETURNING NUMBER) AS score FROM jdocs;
SELECT * FROM jdocs_v ORDER BY id;
SELECT COUNT(*) AS high FROM jdocs WHERE JSON_VALUE(doc, '$.score' RETURNING NUMBER) > 80;
DROP VIEW jdocs_v;
DROP TABLE jdocs;
```

```text
Index created.

View created.

ID NM  SCORE
-- --- -----
 1 Ann    90
 2 Bob    99
 3

3 rows selected.

HIGH
----
   2

1 row selected.

View dropped.

Table dropped.
```

## See also

[Data types](data-types-other.md) · [Aggregate functions](functions-aggregate.md) · [SELECT](select.md)
