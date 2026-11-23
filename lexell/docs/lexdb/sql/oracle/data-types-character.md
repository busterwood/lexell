# Character types

`VARCHAR2`, `CHAR`, `NVARCHAR2`, `NCHAR`, `CLOB`, `NCLOB` and `LONG`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
VARCHAR2 ( size [ BYTE | CHAR ] )
VARCHAR ( size )
CHAR [ ( size [ BYTE | CHAR ] ) ]
NVARCHAR2 ( size )
NCHAR [ ( size ) ]
CLOB | NCLOB | LONG
```

## Arguments

`VARCHAR2(n)`, `NVARCHAR2(n)`
: A string of at most *n* characters. A longer value is ORA-12899 (`value too large for column`).

`CHAR(n)`, `NCHAR(n)`
: A string that is shown padded with spaces to *n* characters (example A). A value compares equal to the same text
  without padding.

`CLOB`, `NCLOB`, `LONG`
: Long text. lexdb keeps all of them as text, with no size limit.

## Remarks

- **The empty string is NULL**, as in Oracle: `'' IS NULL` is true, `LENGTH('')` is NULL and `NVL('', 'x')` is `x`.
  An `INSERT` of `''` into a `NOT NULL` column is ORA-01400.
- `||` joins strings and ignores NULLs: `'a' || NULL || 'b'` is `ab`.
- Comparisons are case sensitive and trailing spaces count in `VARCHAR2`; a `CHAR` value is padded before it is
  compared (example C).
- All text is UTF-8; `LENGTH` counts characters and `LENGTHB` counts bytes.
- `UPPER('héllo')` is `HÉLLO` here (example C).

## Differences from Oracle

- `LENGTH` of a `CHAR(5)` value `'ab'` is 2 (Oracle: 5), though it prints padded.
- `CLOB`, `NCLOB` and `LONG` have no size limit, and a `CLOB` shows `DATA_LENGTH` 4000 in `USER_TAB_COLUMNS`.
- `NLS_SORT` and `NLS_COMP` are accepted and ignored (see [ALTER SESSION](alter-session.md)).

## Examples

### A. CHAR is padded, VARCHAR2 is not

<!-- example: oracle -->
```sql
CREATE TABLE s (a VARCHAR2(5), b VARCHAR2(5 CHAR), c CHAR(5), d NCHAR(3), e NVARCHAR2(5), f CLOB);
INSERT INTO s (a, b, c, d, e) VALUES ('ab', 'ab', 'ab', 'ab', 'ab');
SELECT '[' || a || ']' AS a, '[' || c || ']' AS c, LENGTH(c) AS len_c, LENGTHB(a) AS bytes_a FROM s;
INSERT INTO s (a) VALUES ('abcdef');
```

```text
Table created.

1 row created.

A    C       LEN_C BYTES_A
---- ------- ----- -------
[ab] [ab   ]     2       2

1 row selected.

ERROR:
ORA-12899: value too large for column
```

### B. The empty string is NULL

<!-- example: oracle -->
```sql
SELECT CASE WHEN '' IS NULL THEN 'empty is null' END AS e, LENGTH('') AS len, 'a' || NULL || 'b' AS cat,
       NVL('', 'x') AS nv FROM dual;
CREATE TABLE r (v VARCHAR2(5) NOT NULL);
INSERT INTO r VALUES ('');
```

```text
E             LEN CAT NV
------------- --- --- --
empty is null     ab  x

1 row selected.

Table created.

ERROR:
ORA-01400: cannot insert NULL into ("SA"."R"."V")
```

### C. Comparison

<!-- example: oracle -->
```sql
SELECT CASE WHEN 'abc' = 'ABC' THEN 'equal' ELSE 'different' END AS case_,
       CASE WHEN 'abc' = 'abc ' THEN 'equal' ELSE 'different' END AS padding,
       CASE WHEN CAST('abc' AS CHAR(5)) = CAST('abc' AS VARCHAR2(5)) THEN 'equal' ELSE 'different' END AS char_padding,
       UPPER('héllo') AS upper_
FROM dual;
```

```text
CASE_     PADDING   CHAR_PADDING UPPER_
--------- --------- ------------ ------
different different equal        HÉLLO

1 row selected.
```

### D. CLOB

<!-- example: oracle -->
```sql
SELECT TO_CLOB('abc') || 'def' AS joined, DBMS_LOB.GETLENGTH(TO_CLOB('abcdef')) AS dbms_lob_length,
       LENGTH(TO_CLOB('abc')) AS length_ FROM dual;
```

```text
JOINED DBMS_LOB_LENGTH LENGTH_
------ --------------- -------
abcdef               6       3

1 row selected.
```

## See also

[Numeric types](data-types-number.md), [Binary and other types](data-types-other.md),
[CREATE TABLE](create-table.md)
