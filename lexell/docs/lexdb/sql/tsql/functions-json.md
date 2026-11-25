# JSON functions, OPENJSON and FOR JSON (Transact-SQL)

The `json` data type, SQL Server JSON functions (`ISJSON`, `JSON_VALUE`, `JSON_QUERY`, `JSON_PATH_EXISTS`,
`JSON_MODIFY`, `JSON_CONTAINS`, `JSON_OBJECT`, `JSON_ARRAY`, `JSON_ARRAYAGG`, `JSON_OBJECTAGG`), `OPENJSON`,
`JSON_TABLE`, `IS [NOT] JSON`, and `FOR JSON PATH` / `FOR JSON AUTO`.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Data type

`json`
: Stores validated RFC 8259 JSON text (sent as `nvarchar(max)` over TDS 7.4). Invalid JSON is rejected on insert or cast.

## Functions and predicates

- `ISJSON(expr [, VALUE | SCALAR | ARRAY | OBJECT])` — returns `1`, `0`, or `NULL`.
- `expr IS [NOT] JSON [VALUE | SCALAR | ARRAY | OBJECT] [{WITH | WITHOUT} UNIQUE [KEYS]]` — SQL/JSON predicate.
- `JSON_VALUE(doc, path)` — extracts a scalar value as `nvarchar(max)` (`lax` returns `NULL` on missing or non-scalar; `strict` raises error 13608; invalid JSON raises error 13609). Also accepts SQL/JSON `RETURNING`, `PASSING`, `ON EMPTY`, `ON ERROR`.
- `JSON_QUERY(doc [, path])` — extracts an object or array (`path` defaults to `'$'`). Returns typed JSON so nesting inside `JSON_MODIFY` or `JSON_OBJECT` embeds the object/array without double-escaping. Also accepts SQL/JSON `WRAPPER`, `QUOTES`, `RETURNING`, `ON EMPTY`, `ON ERROR`.
- `JSON_PATH_EXISTS(doc, path)` — returns `1` if `path` matches, `0` otherwise, or `NULL`.
- `JSON_EXISTS(doc, path [PASSING ...] [ON ERROR])` — SQL/JSON boolean predicate.
- `JSON_MODIFY(doc, path, new_value)` — updates, inserts, deletes (when `new_value` is `NULL` in `lax` mode), or appends (`'append $.arr'`) values in a JSON document.
- `JSON_CONTAINS(target, search [, path])` — SQL Server 2025 membership/containment check (`1`, `0`, or `NULL`).
- `JSON_OBJECT([k : v, ...] [{NULL | ABSENT} ON NULL] [{WITH | WITHOUT} UNIQUE [KEYS]])` — builds a JSON object.
- `JSON_ARRAY([v, ...] [{NULL | ABSENT} ON NULL])` — builds a JSON array (defaults to `ABSENT ON NULL`).
- `JSON_ARRAYAGG(expr [ORDER BY ...] [{NULL | ABSENT} ON NULL])` / `WITHIN GROUP (ORDER BY ...)` — aggregates values into a JSON array.
- `JSON_OBJECTAGG(key : value [{NULL | ABSENT} ON NULL] [{WITH | WITHOUT} UNIQUE [KEYS]])` — aggregates pairs into a JSON object.

## Table-valued functions

`OPENJSON(doc [, path])`
: Returns `(key nvarchar(max), value nvarchar(max), type int)` where `type` is `0` (null), `1` (string), `2` (number), `3` (boolean), `4` (array), `5` (object).

`OPENJSON(doc [, path]) WITH (col type ['path' [AS JSON]], ...)`
: Projects typed columns from JSON objects/arrays. Works with `CROSS APPLY` and `OUTER APPLY`.

`JSON_TABLE(doc, path [PASSING ...] COLUMNS (...) [ON ERROR])`
: Standard SQL/JSON table function supporting `FOR ORDINALITY`, `EXISTS PATH`, `FORMAT JSON`, `NESTED PATH`, and implicit lateral references.

## `FOR JSON`

```
SELECT ...
FOR JSON { PATH | AUTO }
    [ , ROOT [ ( 'root_name' ) ] ]
    [ , INCLUDE_NULL_VALUES ]
    [ , WITHOUT_ARRAY_WRAPPER ]
```

Returns a single column named `JSON_F52E2B61-18A1-11d1-B105-00805F49916B`. In `FOR JSON PATH`, column aliases containing
`.` create nested JSON objects (`Customer AS [info.name]`). `FOR JSON` also works inside scalar subqueries
(`SELECT (SELECT ... FOR JSON PATH)`).

## Examples

### A. Extracting, modifying and building JSON

<!-- example: tsql -->
```sql
CREATE TABLE dbo.Orders (Id int PRIMARY KEY, Customer nvarchar(30), Payload json);
INSERT dbo.Orders VALUES
  (1, N'Ann', N'{"total":120,"items":[{"sku":"A1","qty":2},{"sku":"B2","qty":1}]}'),
  (2, N'Bob', N'{"total":50,"items":[{"sku":"C3","qty":5}]}');

SELECT Id,
       JSON_VALUE(Payload, '$.total') AS total,
       JSON_PATH_EXISTS(Payload, '$.items[1].sku') AS has_second
FROM dbo.Orders
ORDER BY Id;
GO

SELECT JSON_MODIFY(N'{"a":1,"tags":["sql"]}', 'append $.tags', N'json') AS updated;
GO
```

### B. `OPENJSON` with `CROSS APPLY` and `FOR JSON PATH`

<!-- example: tsql -->
```sql
SELECT o.Id, j.sku, j.qty
FROM dbo.Orders o
CROSS APPLY OPENJSON(o.Payload, '$.items')
  WITH (sku nvarchar(20) '$.sku', qty int '$.qty') j
ORDER BY o.Id, j.sku;
GO

SELECT Id, Customer AS [info.name]
FROM dbo.Orders
ORDER BY Id
FOR JSON PATH, ROOT('orders');
GO
```

## See also

[SELECT](select.md) · [FROM](from.md) · [Other types](data-types-other.md)
