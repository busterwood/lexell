# Binary, boolean and other types

`RAW`, `BLOB`, `BOOLEAN`, `ROWID`, and the types lexdb does not have.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
RAW ( size )
LONG RAW
BLOB
BOOLEAN
ROWID
UROWID
```

## Arguments

`RAW(n)`, `LONG RAW`, `BLOB`
: Bytes. A `RAW` literal is written with `HEXTORAW('0A0B')`; `RAWTOHEX` gives the hexadecimal text back.
  `UTL_RAW.CAST_TO_RAW` and `UTL_RAW.CAST_TO_VARCHAR2` convert between text and bytes.

`BOOLEAN`
: `TRUE`, `FALSE` or NULL (Oracle 23ai). Columns of this type, `TRUE` and `FALSE` as values, and `TO_BOOLEAN`
  work; a boolean column can be a condition in `WHERE`.

`ROWID`, `UROWID`
: Accepted as column types.

## Remarks

- A client sees a `RAW` as hexadecimal digits.
- `BOOLEAN` values print as `true` and `false`.
- `TO_BOOLEAN('true')`, `TO_BOOLEAN(0)` and similar convert text and numbers.
- `UUID()`, `IS_UUID`, `RAW_TO_UUID` and `UUID_TO_RAW` (26ai) work with `RAW(16)` values: see
  [functions](README.md#functions).
- `SYS_GUID()` gives a 16-byte `RAW`.

## Differences from Oracle

- **`RAW(n)` is not limited:** `HEXTORAW('0102030405')` is stored in a `RAW(4)` column without an error.
- `USER_TAB_COLUMNS` shows a `RAW` column as `BLOB`.
- **The pseudo-column `ROWID`** does not exist (ORA-00904); a `ROWID` column has no values of its own.
- `BFILE`, `XMLTYPE`, `VECTOR`, object types, `VARRAY` and nested tables are not supported: `XMLTYPE`
  and `VECTOR` are ORA-00902, and `CREATE TYPE ... AS OBJECT` is ORA-03001. (For `JSON` columns see
  [JSON and SQL/JSON](functions-json.md).)

## Examples

### A. RAW

<!-- example: oracle -->
```sql
CREATE TABLE b (a RAW(4), b BLOB, c LONG RAW);
INSERT INTO b (a) VALUES (HEXTORAW('0A0B'));
SELECT a, RAWTOHEX(a) AS hex, UTL_RAW.CAST_TO_VARCHAR2(UTL_RAW.CAST_TO_RAW('hi')) AS text FROM b;
INSERT INTO b (a) VALUES (HEXTORAW('0102030405'));
SELECT COUNT(*) AS rows_in_b FROM b;
```

```text
Table created.

1 row created.

A    HEX  TEXT
---- ---- ----
0A0B 0A0B hi

1 row selected.

1 row created.

ROWS_IN_B
---------
        2

1 row selected.
```

### B. BOOLEAN

<!-- example: oracle -->
```sql
CREATE TABLE o (a BOOLEAN, note VARCHAR2(10));
INSERT INTO o VALUES (TRUE, 'yes');
INSERT INTO o VALUES (FALSE, 'no');
SELECT * FROM o;
SELECT note FROM o WHERE a;
SELECT TO_BOOLEAN('true') AS t, TO_BOOLEAN(0) AS f FROM dual;
```

```text
Table created.

1 row created.

1 row created.

A     NOTE
----- ----
true  yes
false no

2 rows selected.

NOTE
----
yes

1 row selected.

T    F
---- -----
true false

1 row selected.
```

### C. UUIDs and GUIDs

<!-- example: oracle -->
```sql
SELECT IS_UUID('6F9619FF-8B86-D011-B42D-00C04FC964FF') AS is_uuid,
       RAW_TO_UUID(HEXTORAW('6F9619FF8B86D011B42D00C04FC964FF')) AS as_text,
       UUID() IS NOT NULL AS made, SYS_GUID() IS NOT NULL AS guid FROM dual;
```

```text
IS_UUID AS_TEXT                              MADE GUID
------- ------------------------------------ ---- ----
true    6f9619ff-8b86-d011-b42d-00c04fc964ff true true

1 row selected.
```

### D. Types that do not exist

<!-- example: oracle -->
```sql
CREATE TABLE x1 (a XMLTYPE);
CREATE TABLE x3 (a VECTOR);
CREATE TYPE ot AS OBJECT (a NUMBER);
/
SELECT ROWID FROM dual;
```

```text
ERROR:
ORA-00902: invalid datatype

ERROR:
ORA-00902: invalid datatype

ERROR:
ORA-03001: unimplemented feature: lexdb: CREATE TYPE supports AS ENUM only

ERROR:
ORA-00904: "ROWID": invalid identifier
```

## See also

[Numeric types](data-types-number.md), [Character types](data-types-character.md),
[CREATE TABLE](create-table.md)
