# Package functions usable in SQL

`UTL_MATCH`, `UTL_ENCODE`, `UTL_RAW` and `DBMS_LOB` functions that a query can call.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
UTL_MATCH.EDIT_DISTANCE ( s1, s2 )
UTL_MATCH.EDIT_DISTANCE_SIMILARITY ( s1, s2 )
UTL_MATCH.JARO_WINKLER ( s1, s2 )
UTL_MATCH.JARO_WINKLER_SIMILARITY ( s1, s2 )
UTL_ENCODE.BASE64_ENCODE ( r )
UTL_ENCODE.BASE64_DECODE ( r )
UTL_RAW.CAST_TO_RAW ( c )
UTL_RAW.CAST_TO_VARCHAR2 ( r )
DBMS_LOB.GETLENGTH ( lob )
DBMS_LOB.SUBSTR ( lob [, amount [, offset ] ] )
```

The PL/SQL packages (`DBMS_OUTPUT` and the others) are on the [built-in packages page](plsql-builtin-packages.md).

## Functions

`UTL_MATCH.EDIT_DISTANCE`
: The Levenshtein distance: the number of single-character insertions, deletions and replacements that turn *s1*
  into *s2*. The comparison is case-sensitive.

`UTL_MATCH.EDIT_DISTANCE_SIMILARITY`
: The edit distance as a similarity from 0 (nothing alike) to 100 (equal), a whole number.

`UTL_MATCH.JARO_WINKLER`
: The Jaro-Winkler similarity from 0 to 1, as a fraction. Strings with a common beginning score higher.

`UTL_MATCH.JARO_WINKLER_SIMILARITY`
: The Jaro-Winkler similarity from 0 to 100, a whole number.

`UTL_ENCODE.BASE64_ENCODE`
: The Base64 text of a `RAW` value, returned as a `RAW` of the Base64 characters (shown as hexadecimal). Wrap it in
  `UTL_RAW.CAST_TO_VARCHAR2` to read it as text.

`UTL_ENCODE.BASE64_DECODE`
: The bytes (a `RAW`) for a Base64 text given as `RAW`. Text that is not Base64 is ORA-29261.

`UTL_RAW.CAST_TO_RAW`
: The bytes of a string (UTF-8) as a `RAW`.

`UTL_RAW.CAST_TO_VARCHAR2`
: The string for the bytes of a `RAW`.

`DBMS_LOB.GETLENGTH`
: The length of a `CLOB` (in characters) or a `BLOB` or `RAW` (in bytes). NULL gives NULL.

`DBMS_LOB.SUBSTR`
: *amount* characters of a `CLOB` from *offset* (1 by default). *amount* defaults to the whole value and may exceed
  the length.

## Remarks

- A function of a package is called with the package name: `UTL_MATCH.JARO_WINKLER('a', 'b')`.
- Other members of these packages, and `DBMS_RANDOM`, `DBMS_UTILITY.GET_TIME` and `UTL_I18N`, are not available in
  SQL (ORA-00904). `UTL_RAW.LENGTH`, `UTL_RAW.CONCAT` and `DBMS_LOB.INSTR` are among them.
- A call with the wrong number of arguments is ORA-00909.

## Differences from Oracle

- `UTL_MATCH.EDIT_DISTANCE` with an empty string or NULL gives -1; Oracle gives NULL for NULL.
- `UTL_RAW.CAST_TO_VARCHAR2('414243')` returns the text `414243`; Oracle converts the string to `RAW` first and
  gives `ABC`.
- `UTL_ENCODE.BASE64_ENCODE('Hello')` takes a string; Oracle needs a `RAW`.
- `DBMS_LOB.SUBSTR` on a `RAW` does not return bytes: `DBMS_LOB.SUBSTR(HEXTORAW('414243'), 2, 2)` is `14`; Oracle
  gives `4243`. Use it on a `CLOB`.

## Examples

### A. Edit distance

<!-- example: oracle -->
```sql
SELECT UTL_MATCH.EDIT_DISTANCE('kitten', 'sitting') AS distance, UTL_MATCH.EDIT_DISTANCE('abc', 'abc') AS equal,
       UTL_MATCH.EDIT_DISTANCE('Abc', 'abc') AS case_matters, UTL_MATCH.EDIT_DISTANCE('', 'abc') AS empty_string
FROM dual;
SELECT UTL_MATCH.EDIT_DISTANCE_SIMILARITY('kitten', 'sitting') AS kitten, UTL_MATCH.EDIT_DISTANCE_SIMILARITY('abc', 'abc') AS equal,
       UTL_MATCH.EDIT_DISTANCE_SIMILARITY('abc', 'xyz') AS different,
       UTL_MATCH.EDIT_DISTANCE_SIMILARITY('shackleford', 'shackelford') AS names
FROM dual;
```

```text
DISTANCE EQUAL CASE_MATTERS EMPTY_STRING
-------- ----- ------------ ------------
       3     0            1           -1

1 row selected.

KITTEN EQUAL DIFFERENT NAMES
------ ----- --------- -----
    58   100         0    82

1 row selected.
```

### B. Jaro-Winkler

<!-- example: oracle -->
```sql
SELECT UTL_MATCH.JARO_WINKLER('shackleford', 'shackelford') AS names, UTL_MATCH.JARO_WINKLER('abc', 'abc') AS equal,
       UTL_MATCH.JARO_WINKLER('abc', 'xyz') AS different
FROM dual;
SELECT UTL_MATCH.JARO_WINKLER_SIMILARITY('shackleford', 'shackelford') AS names,
       UTL_MATCH.JARO_WINKLER_SIMILARITY('abc', 'abc') AS equal, UTL_MATCH.JARO_WINKLER_SIMILARITY('abc', 'xyz') AS different,
       UTL_MATCH.JARO_WINKLER_SIMILARITY('dixon', 'dicksonx') AS dixon
FROM dual;
```

```text
             NAMES EQUAL DIFFERENT
------------------ ----- ---------
0.9818181818181818   1.0       0.0

1 row selected.

NAMES EQUAL DIFFERENT DIXON
----- ----- --------- -----
   98   100         0    81

1 row selected.
```

### C. Fuzzy search in a table

<!-- example: oracle -->
```sql
CREATE TABLE cities (name VARCHAR2(30));
INSERT INTO cities VALUES ('Berlin');
INSERT INTO cities VALUES ('Bern');
INSERT INTO cities VALUES ('Paris');
INSERT INTO cities VALUES ('Brelin');
SELECT name, UTL_MATCH.EDIT_DISTANCE('Berlin', name) AS dist FROM cities
WHERE UTL_MATCH.EDIT_DISTANCE_SIMILARITY('Berlin', name) >= 60 ORDER BY dist, name;
```

```text
Table created.

1 row created.

1 row created.

1 row created.

1 row created.

NAME   DIST
------ ----
Berlin    0
Bern      2
Brelin    2

3 rows selected.
```

### D. Base64 and RAW

<!-- example: oracle -->
```sql
SELECT UTL_ENCODE.BASE64_ENCODE(UTL_RAW.CAST_TO_RAW('Hello, World')) AS encoded_raw,
       UTL_RAW.CAST_TO_VARCHAR2(UTL_ENCODE.BASE64_ENCODE(UTL_RAW.CAST_TO_RAW('Hello, World'))) AS encoded_text,
       UTL_RAW.CAST_TO_VARCHAR2(UTL_ENCODE.BASE64_DECODE(UTL_RAW.CAST_TO_RAW('SGVsbG8sIFdvcmxk'))) AS decoded
FROM dual;
SELECT UTL_ENCODE.BASE64_DECODE(UTL_RAW.CAST_TO_RAW('AP8Q')) AS bytes,
       UTL_RAW.CAST_TO_VARCHAR2(UTL_ENCODE.BASE64_ENCODE(HEXTORAW('00FF10'))) AS encoded
FROM dual;
SELECT UTL_RAW.CAST_TO_RAW('ABC') AS abc_bytes, UTL_RAW.CAST_TO_VARCHAR2(UTL_RAW.CAST_TO_RAW('ABC')) AS back,
       UTL_RAW.CAST_TO_RAW('é') AS utf8, UTL_RAW.CAST_TO_RAW(NULL) AS null_in
FROM dual;
```

```text
ENCODED_RAW                      ENCODED_TEXT     DECODED
-------------------------------- ---------------- ------------
534756736247387349466476636D786B SGVsbG8sIFdvcmxk Hello, World

1 row selected.

BYTES  ENCODED
------ -------
00FF10 AP8Q

1 row selected.

ABC_BYTES BACK UTF8 NULL_IN
--------- ---- ---- -------
414243    ABC  C3A9

1 row selected.
```

### E. DBMS_LOB

<!-- example: oracle -->
```sql
SELECT DBMS_LOB.GETLENGTH(TO_CLOB('hello')) AS clob_len, DBMS_LOB.GETLENGTH('héllo') AS text_len,
       DBMS_LOB.GETLENGTH(HEXTORAW('414243')) AS raw_len, DBMS_LOB.GETLENGTH(NULL) AS null_in
FROM dual;
SELECT DBMS_LOB.SUBSTR(TO_CLOB('abcdefgh'), 3, 2) AS amount_offset, DBMS_LOB.SUBSTR(TO_CLOB('abcdefgh'), 3) AS amount_only,
       DBMS_LOB.SUBSTR(TO_CLOB('abcdefgh')) AS whole, DBMS_LOB.SUBSTR(TO_CLOB('abcdefgh'), 100, 7) AS past_end
FROM dual;
```

```text
CLOB_LEN TEXT_LEN RAW_LEN NULL_IN
-------- -------- ------- -------
       5        5       3

1 row selected.

AMOUNT_OFFSET AMOUNT_ONLY WHOLE    PAST_END
------------- ----------- -------- --------
bcd           abc         abcdefgh gh

1 row selected.
```

### F. Errors and members that are not available

<!-- example: oracle -->
```sql
SELECT UTL_ENCODE.BASE64_DECODE(UTL_RAW.CAST_TO_RAW('!!!')) FROM dual;
SELECT UTL_MATCH.EDIT_DISTANCE('a') FROM dual;
SELECT UTL_RAW.LENGTH(HEXTORAW('4142')) FROM dual;
SELECT UTL_RAW.CONCAT(HEXTORAW('41'), HEXTORAW('42')) FROM dual;
SELECT DBMS_LOB.INSTR(TO_CLOB('abc'), 'b') FROM dual;
SELECT DBMS_RANDOM.VALUE FROM dual;
```

```text
ERROR:
ORA-29261: bad argument

ERROR:
ORA-00909: invalid number of arguments

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier

ERROR:
ORA-00904: invalid identifier
```

## See also

[Character functions](functions-character.md), [Regular expression functions](functions-regex.md),
[Built-in PL/SQL packages](plsql-builtin-packages.md), [Other data types](data-types-other.md)
