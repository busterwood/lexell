# JSON functions, OPENJSON and FOR JSON (Transact-SQL)

The `json` data type, the JSON functions (`ISJSON`, `JSON_VALUE`, `JSON_QUERY`, `JSON_PATH_EXISTS`, `JSON_MODIFY`,
`JSON_CONTAINS`, `JSON_OBJECT`, `JSON_ARRAY`, `JSON_ARRAYAGG`, `JSON_OBJECTAGG`), `OPENJSON`, and `FOR JSON PATH` / `FOR JSON AUTO`.
lexdb also takes the ISO SQL/JSON forms that SQL Server does not have: `IS JSON`, `JSON_EXISTS`, `RETURNING`, `PASSING` and
`JSON_TABLE`.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022; the `json` type, `JSON_CONTAINS`, `JSON_ARRAYAGG` and
`JSON_OBJECTAGG` follow SQL Server 2025.

## Syntax

```
ISJSON ( expression [ , { VALUE | SCALAR | ARRAY | OBJECT } ] )                      → int
JSON_VALUE ( expression , path )                                                       → nvarchar(4000)
JSON_QUERY ( expression [ , path ] )                                                   → nvarchar(max)
JSON_PATH_EXISTS ( expression , path )                                                 → int
JSON_MODIFY ( expression , path , new_value )                                          → nvarchar(max)
JSON_CONTAINS ( target , search_value [ , path ] )                                     → int
JSON_OBJECT ( [ key : value [, ...] ] [ { NULL | ABSENT } ON NULL ] )                  → json
JSON_ARRAY ( [ value [, ...] ] [ { NULL | ABSENT } ON NULL ] )                         → json
JSON_ARRAYAGG ( expression [ ORDER BY ... ] [ { NULL | ABSENT } ON NULL ] )            → json
JSON_OBJECTAGG ( key : value [ { NULL | ABSENT } ON NULL ] )                           → json

OPENJSON ( expression [ , path ] )                                      -- key, value, type
OPENJSON ( expression [ , path ] ) WITH ( column type [ column_path ] [ AS JSON ] [, ...] )

SELECT ... FOR JSON { PATH | AUTO } [ , ROOT [ ( 'root' ) ] ] [ , INCLUDE_NULL_VALUES ] [ , WITHOUT_ARRAY_WRAPPER ]
```

*path* is `[ lax | strict ] $[.key | [index]]...`. Not in SQL Server, accepted by lexdb:

```
expression IS [ NOT ] JSON [ VALUE | SCALAR | ARRAY | OBJECT ] [ { WITH | WITHOUT } UNIQUE [ KEYS ] ]
JSON_EXISTS ( expression , path [ PASSING value AS name [, ...] ] [ { TRUE | FALSE | UNKNOWN | ERROR } ON ERROR ] )
JSON_VALUE ( expression , path [ PASSING ... ] [ RETURNING type ] [ ... ON EMPTY ] [ ... ON ERROR ] )
JSON_QUERY ( expression , path [ PASSING ... ] [ RETURNING type ] [ { WITH | WITHOUT } [ CONDITIONAL | UNCONDITIONAL ] [ ARRAY ] WRAPPER ]
             [ { KEEP | OMIT } QUOTES ] [ ... ON EMPTY ] [ ... ON ERROR ] )
JSON_TABLE ( expression , path COLUMNS ( ... ) [ ... ON ERROR ] )
```

## Arguments

*expression*
: The JSON text (`nvarchar`, `varchar`, or the `json` type). `NULL` gives `NULL`.

*path*
: A JSON path. `$` is the whole value, `.name` a member (`."a b"` quotes a name), `[n]` an element. `lax` (the
  default) gives `NULL` where the path finds nothing; `strict` raises 13608.

`ISJSON`
: 1 when the text is a valid JSON object or array, 0 when it is not, `NULL` for `NULL`. The second argument asks for one kind.

`JSON_VALUE`
: The scalar at *path* as text. An object or an array there is `NULL` in lax mode, an error in strict mode.

`JSON_QUERY`
: The object or array at *path* (the whole text without a path) as JSON text. A scalar there is `NULL` in lax mode.
  Its result is not escaped again when it goes into `JSON_MODIFY`, `JSON_OBJECT`, `JSON_ARRAY` or `FOR JSON`.

`JSON_PATH_EXISTS`
: 1 when *path* finds an item, else 0.

`JSON_MODIFY`
: The text with the value at *path* set to *new_value*; a `NULL` *new_value* deletes the member in lax mode (or sets it to JSON `null` in
  strict mode); `append $.array` appends to an array; a missing member is added in lax mode. The new value is a string unless it is the
  result of `JSON_QUERY` (which is JSON).

`JSON_CONTAINS`
: 1 when the document at *path* has *search_value* among its scalar values.

`JSON_OBJECT`, `JSON_ARRAY`
: JSON built from values. `NULL ON NULL` (the default of `JSON_OBJECT`) keeps a `NULL` as JSON `null`; `ABSENT ON NULL` (the default of `JSON_ARRAY`) leaves it out.

`OPENJSON`
: Rows of an object's members or an array's elements. Without `WITH`: `key`, `value` and `type` (0 null, 1 string, 2 number, 3
  boolean, 4 array, 5 object). With `WITH`: the columns named, each from its path (by default `$.column`); `AS JSON` returns an object or array as JSON text.
  It is used in `FROM` and with `CROSS APPLY` and `OUTER APPLY`.

`FOR JSON`
: Writes the rows of a query as JSON text in one column named `JSON_F52E2B61-18A1-11d1-B105-00805F49916B`. `PATH` takes the nesting from the
  aliases (`[a.b]` makes the object `a`); `AUTO` nests by table. `ROOT('r')` wraps the result in an object, `INCLUDE_NULL_VALUES`
  writes the `NULL`s, `WITHOUT_ARRAY_WRAPPER` writes one object without the array's brackets. Inside a subquery or a column, `FOR JSON` gives nested JSON.

`JSON_ARRAYAGG`, `JSON_OBJECTAGG`
: A group's values as an array, or its key/value pairs as an object.

## Remarks

- In T-SQL a JSON document is text: `nvarchar`, `varchar` or, as in SQL Server 2025, the `json` type. A `json` column checks the text on
  `INSERT` and `CAST` (error 245 for text that is not JSON), and holds it as given; `CAST(... AS nvarchar(max))` gives the text back.
  A `json` column shows as `json` in `INFORMATION_SCHEMA.COLUMNS` and as `nvarchar` in `sys.types`.
- `JSON_VALUE(doc, '$.a' RETURNING int)` converts the value in the call (a lexdb form, see example I).
- `JSON_QUERY(x)` without a path is the same as `JSON_QUERY(x, '$')`.

## Differences from SQL Server

- `ISJSON` of a scalar (`ISJSON('1')`, `ISJSON('"x"')`) is 1; SQL Server says 0 (it counts objects and arrays only). `ISJSON(x, SCALAR)` is 1 for them.
- **Errors.** The numbers are SQL Server's, the texts shorter. In strict mode the missing member is 13608 with `JSON object does not contain key "zz"`
  (SQL Server: `Property cannot be found on the specified JSON path.`, followed by a second error, 13623 or 13624, `Scalar value cannot be found in the specified JSON
  path` or `Object or array cannot be found ...`; lexdb gives the second as another 13608). Text that is not JSON is 13609 without the position of the
  character (`Unexpected character 'n' is found at position 0.`), and 245 for a `json` column or `CAST`. A path that is not
  well formed (`'a'` without `$`) is not an error here (SQL Server: 13607); `JSON_PATH_EXISTS` of text that is not JSON is an error here (SQL Server: 0).
  The states of the errors differ from SQL Server's.
- `JSON_OBJECT('a': 1, 'a': 2)` keeps the last (`{"a":2}`; SQL Server writes both keys). A `NULL` key is a syntax error here (SQL Server: 13638).
- **`FOR JSON`:** a repeated column name (`SELECT 1 AS a, 2 AS a FOR JSON PATH`) writes the last (`[{"a":2}]`; SQL Server: 13601). `FOR JSON AUTO, ROOT` with no name uses
  `root` (SQL Server uses the table's name). A `datetime2` value is written `2020-01-02 03:04:05` (SQL Server: `2020-01-02T03:04:05`), and a `uniqueidentifier` in lower case (SQL Server: upper case).
  A column of the outer query read inside a `FOR JSON` subquery (`(SELECT name FOR JSON PATH)` with `name` from the outer table) is named `#coll` there; name the column in the subquery's own `SELECT` as example F does.
- **The `json` type:** the text of a value is kept as written (`{"a" : 1}`; SQL Server 2025 writes it compact), `DATALENGTH` is the text's length (SQL Server: the length of its binary form), `sys.types` says `nvarchar` for the column (SQL Server: `json`), and a
  `json` value can be compared (`WHERE Payload = Payload` works; SQL Server: 13636).
- `JSON_CONTAINS` takes text too (SQL Server 2025: 8116, its first argument must be `json`).
- **Beyond SQL Server:** `IS JSON`, `JSON_EXISTS`, `RETURNING`, `PASSING`, `ON EMPTY`, `ON ERROR` and `JSON_TABLE` are SQL/JSON forms that SQL Server 2022 and 2025 reject (error 156, 102 or 195).

## Examples

### A. The `json` type

A `json` column is checked on `INSERT`. (SQL Server 2025.)

<!-- example: tsql -->
```sql
CREATE TABLE dbo.Orders (Id int PRIMARY KEY, Customer nvarchar(30), Payload json);
INSERT dbo.Orders VALUES
  (1, N'Ann', N'{"total":120,"items":[{"sku":"A1","qty":2},{"sku":"B2","qty":1}]}'),
  (2, N'Bob', N'{"total":50,"items":[{"sku":"C3","qty":5}]}'),
  (3, N'Cy', NULL);
GO
SELECT Id, JSON_VALUE(Payload, '$.total') AS total, JSON_PATH_EXISTS(Payload, '$.items[1].sku') AS has_second,
       JSON_CONTAINS(Payload, 'A1', '$.items[*].sku') AS has_a1
FROM dbo.Orders
ORDER BY Id;
GO
UPDATE dbo.Orders SET Payload = JSON_MODIFY(Payload, '$.total', 55) WHERE Id = 2;
SELECT Payload FROM dbo.Orders WHERE Id = 2;
GO
INSERT dbo.Orders VALUES (4, N'Dee', N'{"bad');
GO
```

```text
(3 rows affected)

Id total has_second has_a1
-- ----- ---------- ------
1  120   1          1
2  50    0          0
3  NULL  NULL       NULL

(3 rows affected)

(1 row affected)

Payload
-------------------------------------------
{"total":55,"items":[{"sku":"C3","qty":5}]}

(1 row affected)

Msg 245, Level 16, State 1, Line 1
invalid input syntax for type json: "{"bad"
```

### B. `ISJSON`, `JSON_VALUE`, `JSON_QUERY` and `JSON_PATH_EXISTS`

<!-- example: tsql -->
```sql
SELECT ISJSON(N'{"a":1}') AS obj, ISJSON(N'[1,2]') AS arr, ISJSON(N'nope') AS bad, ISJSON(NULL) AS nul,
       ISJSON(N'{"a":1}', ARRAY) AS obj_as_array;
GO
SELECT JSON_VALUE(N'{"a":{"b":7},"s":"x","n":null,"arr":[1,2]}', '$.a.b') AS b,
       JSON_VALUE(N'{"a":{"b":7},"s":"x","n":null,"arr":[1,2]}', '$.s') AS s,
       JSON_VALUE(N'{"n":null}', '$.n') AS n,
       JSON_VALUE(N'{"arr":[1,2]}', '$.arr') AS arr,
       JSON_VALUE(N'{"arr":[1,2]}', '$.arr[1]') AS el,
       JSON_VALUE(N'{"a":1}', '$.zz') AS missing,
       JSON_VALUE(N'{"a b":"x"}', '$."a b"') AS quoted;
GO
SELECT JSON_QUERY(N'{"a":{"b":[1,2]}}', '$.a') AS obj,
       JSON_QUERY(N'{"a":{"b":[1,2]}}', '$.a.b') AS arr,
       JSON_QUERY(N'{"a":1}', '$.a') AS scalar,
       JSON_QUERY(N'{"a":1}', '$.zz') AS missing,
       JSON_QUERY(N'[1,2]') AS whole;
GO
SELECT JSON_PATH_EXISTS(N'{"a":[1,2]}', '$.a[1]') AS yes, JSON_PATH_EXISTS(N'{"a":[1,2]}', '$.a[5]') AS no,
       JSON_PATH_EXISTS(NULL, '$.a') AS nul;
GO
```

```text
obj arr bad nul  obj_as_array
--- --- --- ---- ------------
1   1   0   NULL 0

(1 row affected)

b s n    arr  el missing quoted
- - ---- ---- -- ------- ------
7 x NULL NULL 2  NULL    x

(1 row affected)

obj         arr   scalar missing whole
----------- ----- ------ ------- -----
{"b":[1,2]} [1,2] NULL   NULL    [1,2]

(1 row affected)

yes no nul
--- -- ----
1   0  NULL

(1 row affected)
```

### C. Strict mode and errors

<!-- example: tsql -->
```sql
SELECT JSON_VALUE(N'{"a":1}', 'strict $.zz') AS m;
GO
SELECT JSON_VALUE(N'{"arr":[1,2]}', 'strict $.arr') AS m;
GO
SELECT JSON_QUERY(N'{"a":1}', 'strict $.a') AS m;
GO
SELECT JSON_VALUE(N'not json', '$.a') AS m;
GO
SELECT JSON_MODIFY(N'{"a":1}', 'strict $.b', 3) AS m;
GO
```

```text
Msg 13608, Level 16, State 1, Line 1
JSON object does not contain key "zz"
Msg 13608, Level 16, State 1, Line 1
Scalar value cannot be found in the specified JSON path.
Msg 13608, Level 16, State 1, Line 1
Object or array cannot be found in the specified JSON path.
Msg 13609, Level 16, State 1, Line 1
JSON text is not properly formatted. Unexpected character.
Msg 13608, Level 16, State 1, Line 1
Property cannot be found on the specified JSON path.
```

### D. `JSON_MODIFY`

<!-- example: tsql -->
```sql
SELECT JSON_MODIFY(N'{"a":1}', '$.a', 2) AS updated,
       JSON_MODIFY(N'{"a":1}', '$.b', N'x') AS added,
       JSON_MODIFY(N'{"a":1,"b":2}', '$.b', NULL) AS deleted,
       JSON_MODIFY(N'{"a":1}', '$.a', 1.5) AS number_,
       JSON_MODIFY(N'{}', '$.a.b', 1) AS deep,
       JSON_MODIFY(N'[1,2]', '$[0]', 9) AS element;
GO
SELECT JSON_MODIFY(N'{"a":[1]}', 'append $.a', 2) AS appended,
       JSON_MODIFY(N'{"a":[1]}', '$.c', JSON_QUERY(N'{"x":1}')) AS nested,
       JSON_MODIFY(N'{"a":[1]}', '$.c', N'{"x":1}') AS escaped;
GO
```

```text
updated added           deleted number_   deep element
------- --------------- ------- --------- ---- -------
{"a":2} {"a":1,"b":"x"} {"a":1} {"a":1.5} {}   [9,2]

(1 row affected)

appended    nested                escaped
----------- --------------------- -------------------------
{"a":[1,2]} {"a":[1],"c":{"x":1}} {"a":[1],"c":"{\"x\":1}"}

(1 row affected)
```

### E. `OPENJSON`

<!-- example: tsql -->
```sql
SELECT * FROM OPENJSON(N'{"a":1,"b":"x","c":true,"d":null,"e":[1,2],"f":{"g":1}}');
GO
SELECT [key], [type], CASE [type] WHEN 0 THEN 'null' WHEN 1 THEN 'string' WHEN 2 THEN 'number'
       WHEN 3 THEN 'boolean' WHEN 4 THEN 'array' WHEN 5 THEN 'object' END AS typename
FROM OPENJSON(N'[10,"x",null]');
GO
SELECT * FROM OPENJSON(N'{"a":{"b":[1,2]}}', '$.a.b');
GO
SELECT * FROM OPENJSON(N'[{"id":1,"name":"Ann","tags":["x"]},{"id":2,"name":"Bob"}]')
  WITH (id int '$.id', name nvarchar(20) '$.name', tags nvarchar(max) '$.tags' AS JSON, tag0 nvarchar(5) '$.tags[0]');
GO
SELECT * FROM OPENJSON(N'[{"Id":1,"Name":"Ann"}]') WITH (Id int, Name nvarchar(20), Missing int);
GO
SELECT o.Id, j.sku, j.qty
FROM dbo.Orders o
CROSS APPLY OPENJSON(o.Payload, '$.items') WITH (sku nvarchar(20) '$.sku', qty int '$.qty') j
ORDER BY o.Id, j.sku;
GO
SELECT * FROM OPENJSON(N'[{"id":"abc"}]') WITH (id int '$.id');
GO
```

```text
key value   type
--- ------- ----
a   1       2
b   x       1
c   true    3
d   NULL    0
e   [1,2]   4
f   {"g":1} 5

(6 rows affected)

key type typename
--- ---- --------
0   2    number
1   1    string
2   0    null

(3 rows affected)

key value type
--- ----- ----
0   1     2
1   2     2

(2 rows affected)

id name tags  tag0
-- ---- ----- ----
1  Ann  ["x"] x
2  Bob  NULL  NULL

(2 rows affected)

Id Name Missing
-- ---- -------
1  Ann  NULL

(1 row affected)

Id sku qty
-- --- ---
1  A1  2
1  B2  1
2  C3  5

(3 rows affected)

Msg 245, Level 16, State 1, Line 1
Conversion failed when converting the varchar value 'abc' to data type int.
```

### F. `FOR JSON PATH`

<!-- example: tsql -->
```sql
SELECT Id, Customer, Payload FROM dbo.Orders WHERE Id < 3 ORDER BY Id FOR JSON PATH;
GO
SELECT Id, Customer AS [info.name] FROM dbo.Orders WHERE Id < 3 ORDER BY Id FOR JSON PATH, ROOT('orders');
GO
SELECT Id, Customer FROM dbo.Orders ORDER BY Id FOR JSON PATH, INCLUDE_NULL_VALUES;
GO
SELECT Id, Customer FROM dbo.Orders WHERE Id = 1 FOR JSON PATH, WITHOUT_ARRAY_WRAPPER;
GO
SELECT Id, JSON_QUERY((SELECT Customer FOR JSON PATH)) AS sub FROM dbo.Orders WHERE Id < 3 ORDER BY Id FOR JSON PATH;
GO
SELECT CAST(1 AS bit) AS b, 1.50 AS n, N'a"b' AS s, CAST(NULL AS int) AS nul FOR JSON PATH, INCLUDE_NULL_VALUES;
GO
SELECT Id FROM dbo.Orders WHERE 1 = 0 FOR JSON PATH;
GO
```

```text
JSON_F52E2B61-18A1-11d1-B105-00805F49916B
---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------
[{"Id":1,"Customer":"Ann","Payload":{"total":120,"items":[{"sku":"A1","qty":2},{"sku":"B2","qty":1}]}},{"Id":2,"Customer":"Bob","Payload":{"total":55,"items":[{"sku":"C3","qty":5}]}}]

(1 row affected)

JSON_F52E2B61-18A1-11d1-B105-00805F49916B
--------------------------------------------------------------------------
{"orders":[{"Id":1,"info":{"name":"Ann"}},{"Id":2,"info":{"name":"Bob"}}]}

(1 row affected)

JSON_F52E2B61-18A1-11d1-B105-00805F49916B
------------------------------------------------------------------------------
[{"Id":1,"Customer":"Ann"},{"Id":2,"Customer":"Bob"},{"Id":3,"Customer":"Cy"}]

(1 row affected)

JSON_F52E2B61-18A1-11d1-B105-00805F49916B
-----------------------------------------
{"Id":1,"Customer":"Ann"}

(1 row affected)

JSON_F52E2B61-18A1-11d1-B105-00805F49916B
-------------------------------------------------------------------------
[{"Id":1,"sub":[{"Customer":"Ann"}]},{"Id":2,"sub":[{"Customer":"Bob"}]}]

(1 row affected)

JSON_F52E2B61-18A1-11d1-B105-00805F49916B
-------------------------------------------
[{"b":true,"n":1.50,"s":"a\"b","nul":null}]

(1 row affected)

JSON_F52E2B61-18A1-11d1-B105-00805F49916B
-----------------------------------------

(0 rows affected)
```

### G. `FOR JSON AUTO`

<!-- example: tsql -->
```sql
SELECT Id, Customer FROM dbo.Orders WHERE Id < 3 ORDER BY Id FOR JSON AUTO;
GO
SELECT o.Id, o.Customer FROM dbo.Orders o WHERE o.Id < 3 ORDER BY o.Id FOR JSON AUTO, ROOT('rows');
GO
```

```text
JSON_F52E2B61-18A1-11d1-B105-00805F49916B
-----------------------------------------------------
[{"Id":1,"Customer":"Ann"},{"Id":2,"Customer":"Bob"}]

(1 row affected)

JSON_F52E2B61-18A1-11d1-B105-00805F49916B
--------------------------------------------------------------
{"rows":[{"Id":1,"Customer":"Ann"},{"Id":2,"Customer":"Bob"}]}

(1 row affected)
```

### H. `JSON_OBJECT` and `JSON_ARRAY`

<!-- example: tsql -->
```sql
SELECT JSON_OBJECT('a': 1, 'b': NULL, 'c': 'x') AS keeps_null,
       JSON_OBJECT('a': 1, 'b': NULL ABSENT ON NULL) AS drops_null,
       JSON_OBJECT() AS empty_obj;
GO
SELECT JSON_ARRAY(1, 'a', NULL, 2.5) AS arr,
       JSON_ARRAY(1, NULL NULL ON NULL) AS keeps_null,
       JSON_ARRAY() AS empty_arr,
       JSON_ARRAY(JSON_OBJECT('x': 1), JSON_ARRAY(1)) AS nested;
GO
SELECT JSON_ARRAYAGG(Customer ORDER BY Id) AS names, JSON_OBJECTAGG(Customer : Id) AS ids FROM dbo.Orders;
GO
```

```text
keeps_null               drops_null empty_obj
------------------------ ---------- ---------
{"a":1,"b":null,"c":"x"} {"a":1}    {}

(1 row affected)

arr         keeps_null empty_arr nested
----------- ---------- --------- -------------
[1,"a",2.5] [1,null]   []        [{"x":1},[1]]

(1 row affected)

names              ids
------------------ ------------------------
["Ann","Bob","Cy"] {"Ann":1,"Bob":2,"Cy":3}

(1 row affected)
```

### I. The SQL/JSON forms lexdb adds

<!-- example: tsql -->
```sql
SELECT N'{"a":1}' IS JSON AS obj, N'x' IS NOT JSON AS bad, N'[1]' IS JSON ARRAY AS arr,
       N'{"a":1,"a":2}' IS JSON WITH UNIQUE KEYS AS unique_keys;
GO
SELECT JSON_VALUE(N'{"a":1}', '$.a' RETURNING int) + 1 AS a1,
       JSON_QUERY(N'{"a":[1]}', '$.a' WITH WRAPPER) AS wrapped,
       JSON_EXISTS(N'{"a":1}', '$.a') AS yes;
GO
SELECT * FROM JSON_TABLE(N'[{"id":1,"tags":["x","y"]},{"id":2,"tags":[]}]', '$[*]' COLUMNS (
  n FOR ORDINALITY, id int PATH '$.id', NESTED PATH '$.tags[*]' COLUMNS (tag nvarchar(5) PATH '$'))) AS jt;
GO
```

```text
obj bad arr unique_keys
--- --- --- -----------
1   1   1   0

(1 row affected)

a1 wrapped yes
-- ------- ---
2  [[1]]   1

(1 row affected)

n id tag
- -- ----
1 1  x
1 1  y
2 2  NULL

(3 rows affected)
```

### J. A document from variables

<!-- example: tsql -->
```sql
DECLARE @j nvarchar(max) = N'{"p":[{"n":"x","v":1},{"n":"y","v":2}]}';
SELECT p.n, p.v FROM OPENJSON(@j, '$.p') WITH (n nvarchar(5), v int) p ORDER BY p.v DESC;
SELECT SUM(CAST(JSON_VALUE(value, '$.v') AS int)) AS total FROM OPENJSON(@j, '$.p');
GO
DROP TABLE dbo.Orders;
GO
```

```text
n v
- -
y 2
x 1

(2 rows affected)

total
-----
3

(1 row affected)
```

## See also

[SELECT](select.md) · [FROM](from.md) · [Other types](data-types-other.md)
