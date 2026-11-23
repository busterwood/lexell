# String functions (Transact-SQL)

Functions that measure, cut, search, change and build text.

**Door:** SQL Server (TDS). **Follows:** SQL Server 2022 and 2025.

## Syntax

```
LEN ( string_expression ) → int
DATALENGTH ( expression ) → int
LEFT ( character_expression, integer_expression ) → varchar | nvarchar
RIGHT ( character_expression, integer_expression ) → varchar | nvarchar
SUBSTRING ( expression, start, length ) → varchar | nvarchar
CHARINDEX ( expressionToFind, expressionToSearch [, start_location ] ) → int
PATINDEX ( '%pattern%', expression ) → int
REPLACE ( string_expression, string_pattern, string_replacement ) → varchar | nvarchar
REPLICATE ( string_expression, integer_expression ) → varchar | nvarchar
REVERSE ( string_expression ) → varchar | nvarchar
STUFF ( character_expression, start, length, replaceWith_expression ) → varchar | nvarchar
SPACE ( integer_expression ) → varchar
UPPER ( character_expression ) → varchar | nvarchar
LOWER ( character_expression ) → varchar | nvarchar
LTRIM ( character_expression [, characters ] ) → varchar | nvarchar
RTRIM ( character_expression [, characters ] ) → varchar | nvarchar
TRIM ( [ LEADING | TRAILING | BOTH ] [ characters FROM ] string ) → varchar | nvarchar
CONCAT ( argument1, argument2 [, argumentN ] ... ) → varchar | nvarchar
CONCAT_WS ( separator, argument1, argument2 [, argumentN ] ... ) → varchar | nvarchar
QUOTENAME ( 'character_string' [, 'quote_character' ] ) → nvarchar
CHAR ( integer_expression ) → char(1)
NCHAR ( integer_expression ) → nchar(1)
ASCII ( character_expression ) → int
TRANSLATE ( inputString, characters, translations ) → varchar | nvarchar
UNISTR ( character_expression ) → nvarchar
BASE64_ENCODE ( binary_expression ) → varchar
BASE64_DECODE ( string_expression ) → varbinary
STRING_AGG ( expression, separator ) [ WITHIN GROUP ( ORDER BY ... ) ] → varchar | nvarchar
```

`FORMAT` is on [its own page](functions-format.md). The pattern functions `REGEXP_LIKE` and the others, and the fuzzy
matching functions, are on [another](functions-regex-fuzzy.md). Conversion between types (`CAST`, `CONVERT`) is on the
[conversion page](functions-conversion.md).

## Functions

`LEN`
: The number of characters in the string, without trailing spaces. Leading spaces count. `LEN(NULL)` is NULL.

`DATALENGTH`
: The number of bytes a value takes. lexdb counts two bytes for each character of a `char`, `varchar`, `nchar` or
  `nvarchar` value, so `DATALENGTH('abc')` is 6 (see Differences).

`LEFT`, `RIGHT`
: The first or last *n* characters. A string shorter than *n* comes back whole; 0 gives an empty string.

`SUBSTRING`
: The *length* characters from position *start* (the first is 1). A *start* before 1 uses up part of *length*
  (`SUBSTRING('abcdef', 0, 3)` is `ab`); a *start* past the end gives an empty string.

`CHARINDEX`
: The position of the first *expressionToFind* in *expressionToSearch*, from *start_location*, or 0. The search
  follows the collation, which is case-insensitive here. An empty search string gives 0; NULL gives NULL.

`PATINDEX`
: The position of the first match of a `LIKE` pattern, or 0. The pattern needs `%` at its ends to match inside a
  string. It takes `_`, `%`, `[a-z]` and `[^a-z]`.

`REPLACE`
: The string with every *string_pattern* replaced by *string_replacement*. The match is case-insensitive.

`REPLICATE`
: The string repeated *n* times. 0 or less gives an empty string.

`REVERSE`
: The characters in the opposite order.

`STUFF`
: Removes *length* characters from *start* and inserts *replaceWith_expression* there. A *start* of 0 or below, or
  past the end plus one, gives NULL.

`SPACE`
: A string of *n* spaces.

`UPPER`, `LOWER`
: The string in upper or lower case. Only ASCII letters change (see Differences).

`LTRIM`, `RTRIM`
: The string without its leading or trailing spaces, or, with *characters*, without any of those characters
  (`LTRIM('xxabc', 'x')` is `abc`). A tab or a line feed is not a space and stays.

`TRIM`
: The string without spaces at both ends, or, with `characters FROM`, without any of those characters at the end
  `LEADING`, `TRAILING` or `BOTH` (the default) names. *characters* is a set: `TRIM('ab' FROM 'baabcab')` is `c`.

`CONCAT`
: The arguments joined as strings. A NULL counts as an empty string, and a number or date is converted first.
  `+` joins strings too, and gives NULL when either side is NULL.

`CONCAT_WS`
: As `CONCAT`, with *separator* between the arguments. NULL arguments are left out, with their separators.

`QUOTENAME`
: The string as a delimited identifier: `[name]`, with a `]` doubled. The optional second argument is `'['`, `']'`,
  `'"'`, `'''`, `'('`, `')'`, `'<'`, `'>'`, `'{'`, `` '`' `` or `'}'`. Any other character gives NULL.

`CHAR`, `NCHAR`
: The character with the given code. `CHAR` takes 0 to 255 (NULL beyond); `NCHAR` takes a Unicode code point.

`ASCII`
: The code of the first character of the string.

`TRANSLATE`
: Replaces each character of *characters* by the character at the same place in *translations*.

`UNISTR`
: A string in which `\xxxx` stands for the character with that four-digit hex code and `\+xxxxxx` for one with a
  six-digit code. `\\` is a backslash. (SQL Server 2025.)

`BASE64_ENCODE`, `BASE64_DECODE`
: The Base64 text of a `binary` or `varbinary` value, and the bytes of a Base64 text. (SQL Server 2025.)

`STRING_AGG`
: An aggregate: it joins the values of a group, with a separator. It is described on the aggregate functions page
  (functions-aggregate.md, not written yet); example K gives a first look.

## Remarks

- A NULL argument gives NULL, except in `CONCAT` and `CONCAT_WS`.
- A string comparison, `CHARINDEX`, `REPLACE` and `PATINDEX` ignore case, as under SQL Server's default collation.
- A number given where a string is expected is converted to a string first: `LEFT(12345, 2)` is `12`.
- `LEN` counts characters, not bytes: `LEN(N'日本語')` is 3.

## Differences from SQL Server

- `DATALENGTH` of a string is always twice its length in characters: `DATALENGTH('abc')` is 6 where SQL Server says 3
  for a `varchar`, and `DATALENGTH(CAST('ab' AS char(5)))` is 4 where SQL Server says 5.
- `UPPER` and `LOWER` change ASCII letters only: `UPPER('héllo')` is `HéLLO` (SQL Server: `HÉLLO`).
- `LEFT('abc', -1)` is `ab`, and `SUBSTRING('abcdef', 2)` is `bcdef`. SQL Server refuses both: a negative length is
  error 536, and `SUBSTRING` needs all three arguments (error 174). `CONCAT` with one argument gives that argument
  (SQL Server: error 189).
- `TRANSLATE('abc', 'abc', 'xy')` gives `xy` (SQL Server: error 9828, the two lists differ in length).
- `ASCII('')` is 0 (SQL Server: NULL).
- `BASE64_DECODE` gives a `varbinary`, but `CAST(BASE64_DECODE('aGVsbG8=') AS varchar(10))` gives its hex text
  (`\x68656c6c`) and not the characters. `0x41` and the other hex literals are numbers, so they cannot be passed
  to `BASE64_ENCODE` (see the [conversion page](functions-conversion.md)). Cast a string to `varbinary`.
- Not available (error 195): `UNICODE`, `SOUNDEX`, `DIFFERENCE`, `STR`, `ISNUMERIC`, `STRING_SPLIT`,
  `STRING_ESCAPE`, `HASHBYTES`, `COMPRESS`, `DECOMPRESS` (example M).
- `STRING_AGG` is on its own page; here it is only mentioned.

## Examples

<!--setup: tsql
CREATE TABLE dbo.person (id int PRIMARY KEY, name nvarchar(40), email varchar(60));
INSERT dbo.person VALUES (1, N'  Ada Lovelace ', 'ada@analytical.example'), (2, N'Grace Hopper', 'grace@navy.example'),
                         (3, N'Alan Turing', NULL);
-->

The examples that read a table use this one:

```sql
CREATE TABLE dbo.person (id int PRIMARY KEY, name nvarchar(40), email varchar(60));
INSERT dbo.person VALUES (1, N'  Ada Lovelace ', 'ada@analytical.example'), (2, N'Grace Hopper', 'grace@navy.example'),
                         (3, N'Alan Turing', NULL);
```

### A. Length

`LEN` leaves out trailing spaces; `DATALENGTH` counts bytes.

<!-- example: tsql -->
```sql
SELECT LEN('héllo') AS len, LEN('abc   ') AS len_trailing, LEN('  abc') AS len_leading, LEN(NULL) AS len_null,
       LEN(N'日本語') AS len_wide, DATALENGTH('abc') AS datalength_abc, DATALENGTH(12345) AS datalength_int;
```

```text
len len_trailing len_leading len_null len_wide datalength_abc datalength_int
--- ------------ ----------- -------- -------- -------------- --------------
5   3            5           NULL     3        6              4

(1 row affected)
```

### B. LEFT, RIGHT and SUBSTRING

<!-- example: tsql -->
```sql
SELECT LEFT('abcdef', 2) AS l, RIGHT('abcdef', 2) AS r, LEFT('abc', 10) AS l_long, RIGHT('abc', 0) AS r_zero,
       SUBSTRING('abcdef', 2, 3) AS s1, SUBSTRING('abcdef', 0, 3) AS s0, SUBSTRING('abcdef', 4, 100) AS s_long,
       SUBSTRING('abcdef', 10, 2) AS s_past, LEFT(12345, 2) AS from_int;
```

```text
l  r  l_long r_zero s1  s0 s_long s_past from_int
-- -- ------ ------ --- -- ------ ------ --------
ab ef abc           bcd ab def           12

(1 row affected)
```

### C. CHARINDEX and PATINDEX

<!-- example: tsql -->
```sql
SELECT CHARINDEX('c', 'abcabc') AS first_c, CHARINDEX('c', 'abcabc', 4) AS c_from_4, CHARINDEX('z', 'abc') AS none,
       CHARINDEX('B', 'abc') AS ignores_case, PATINDEX('%c_e%', 'abcdef') AS p_underscore,
       PATINDEX('%[0-9]%', 'ab12') AS p_digit, PATINDEX('%[^a-z]%', 'abc1') AS p_not_letter,
       PATINDEX('abc', 'abcdef') AS p_no_wildcards;
```

```text
first_c c_from_4 none ignores_case p_underscore p_digit p_not_letter p_no_wildcards
------- -------- ---- ------------ ------------ ------- ------------ --------------
3       6        0    2            3            3       4            0

(1 row affected)
```

### D. REPLACE, REPLICATE, REVERSE, SPACE and STUFF

<!-- example: tsql -->
```sql
SELECT REPLACE('a-b-c', '-', '+') AS replaced, REPLACE('abc', 'B', 'x') AS ignores_case, REPLACE('abc', 'b', '') AS removed,
       REPLICATE('ab', 3) AS repeated, REVERSE('abc') AS reversed, '[' + SPACE(3) + ']' AS spaces,
       STUFF('abcdef', 2, 3, 'XY') AS stuff_replace, STUFF('abcdef', 2, 0, 'XY') AS stuff_insert,
       STUFF('abc', 10, 1, 'x') AS stuff_past_end;
```

```text
replaced ignores_case removed repeated reversed spaces stuff_replace stuff_insert stuff_past_end
-------- ------------ ------- -------- -------- ------ ------------- ------------ --------------
a+b+c    axc          ac      ababab   cba      [   ]  aXYef         aXYbcdef     NULL

(1 row affected)
```

### E. Case and trimming

<!-- example: tsql -->
```sql
SELECT UPPER('abc') AS upper_, LOWER('ABC') AS lower_, '[' + LTRIM('  a  ') + ']' AS ltrim_, '[' + RTRIM('  a  ') + ']' AS rtrim_,
       '[' + TRIM('  a  ') + ']' AS trim_, TRIM('xy' FROM 'xyaxy') AS trim_set, TRIM(LEADING 'x' FROM 'xxaxx') AS trim_leading,
       TRIM(TRAILING 'x' FROM 'xxaxx') AS trim_trailing, LEN(TRIM(CHAR(9) + 'x')) AS tab_stays;
```

```text
upper_ lower_ ltrim_ rtrim_ trim_ trim_set trim_leading trim_trailing tab_stays
------ ------ ------ ------ ----- -------- ------------ ------------- ---------
ABC    abc    [a  ]  [  a]  [a]   a        axx          xxa           1

(1 row affected)
```

### F. CONCAT, CONCAT_WS and NULL

`+` gives NULL when a side is NULL; `CONCAT` treats NULL as an empty string.

<!-- example: tsql -->
```sql
SELECT CONCAT('a', 1, NULL, 'b') AS concat_, 'a' + NULL AS plus_null, CONCAT_WS('-', 'a', NULL, 'b', 3) AS concat_ws_,
       CONCAT(NULL, NULL) AS all_null, CONCAT_WS(', ', 'a') AS one_value,
       CONCAT(1, 2.5, CAST('2026-03-05' AS date)) AS mixed_types;
```

```text
concat_ plus_null concat_ws_ all_null one_value mixed_types
------- --------- ---------- -------- --------- --------------
a1b     NULL      a-b-3               a         12.52026-03-05

(1 row affected)
```

### G. QUOTENAME

<!-- example: tsql -->
```sql
SELECT QUOTENAME('my table') AS brackets, QUOTENAME('a]b') AS bracket_doubled, QUOTENAME('abc', '''') AS single_quotes,
       QUOTENAME('abc', '(') AS parens, QUOTENAME('abc', '"') AS double_quotes, QUOTENAME('x', 'q') AS bad_quote;
```

```text
brackets   bracket_doubled single_quotes parens double_quotes bad_quote
---------- --------------- ------------- ------ ------------- ---------
[my table] [a]]b]          'abc'         (abc)  "abc"         NULL

(1 row affected)
```

### H. CHAR, NCHAR and ASCII

<!-- example: tsql -->
```sql
SELECT CHAR(65) AS char_65, NCHAR(233) AS nchar_233, NCHAR(8364) AS euro, ASCII('A') AS ascii_a,
       ASCII('abc') AS first_only, CHAR(300) AS char_too_big;
```

```text
char_65 nchar_233 euro ascii_a first_only char_too_big
------- --------- ---- ------- ---------- ------------
A       é         €    65      97         NULL

(1 row affected)
```

### I. TRANSLATE and UNISTR

<!-- example: tsql -->
```sql
SELECT TRANSLATE('2*[3+4]/{7-2}', '[]{}', '()()') AS translated, TRANSLATE('a-b_c', '-_', '  ') AS to_spaces,
       UNISTR('\00e9') AS e_acute, UNISTR('a\+0020ac') AS a_euro;
```

```text
translated    to_spaces e_acute a_euro
------------- --------- ------- ------
2*(3+4)/(7-2) a b c     é       a€

(1 row affected)
```

### J. BASE64_ENCODE and BASE64_DECODE

<!-- example: tsql -->
```sql
SELECT BASE64_ENCODE(CAST('hello' AS varbinary(10))) AS encoded, BASE64_DECODE('aGVsbG8=') AS decoded;
```

```text
encoded  decoded
-------- ----------
aGVsbG8= 68656C6C6F

(1 row affected)
```

### K. STRING_AGG

<!-- example: tsql -->
```sql
SELECT STRING_AGG(name, ', ') WITHIN GROUP (ORDER BY name DESC) AS names, COUNT(*) AS n
FROM (VALUES ('b'), ('a'), (NULL), ('c')) AS v(name);
```

```text
names   n
------- -
c, b, a 4

(1 row affected)
```

### L. On a table

Cut the names of the `person` table, and the part of each address before the `@`:

<!-- example: tsql -->
```sql
SELECT id, UPPER(TRIM(name)) AS name, LEN(name) AS len, LEFT(email, CHARINDEX('@', email) - 1) AS user_part,
       CONCAT_WS(' / ', TRIM(name), email) AS label
FROM dbo.person ORDER BY id;
```

```text
id name         len user_part label
-- ------------ --- --------- -------------------------------------
1  ADA LOVELACE 14  ada       Ada Lovelace / ada@analytical.example
2  GRACE HOPPER 12  grace     Grace Hopper / grace@navy.example
3  ALAN TURING  11  NULL      Alan Turing

(3 rows affected)
```

### M. Functions that do not exist

Each statement is in its own batch, because error 195 ends a batch.

<!-- example: tsql -->
```sql
SELECT UNICODE('A') AS code;
GO
SELECT STR(12.5) AS text_;
GO
SELECT ISNUMERIC('12') AS is_number;
GO
SELECT SOUNDEX('Smith') AS sound;
```

```text
Msg 195, Level 15, State 1, Line 1
'unicode' is not a recognized built-in function name.
Msg 195, Level 15, State 1, Line 1
'str' is not a recognized built-in function name.
Msg 195, Level 15, State 1, Line 1
'isnumeric' is not a recognized built-in function name.
Msg 195, Level 15, State 1, Line 1
'soundex' is not a recognized built-in function name.
```

### N. Wrong argument types and bad data

<!-- example: tsql -->
```sql
SELECT BASE64_ENCODE('hello') AS bad_type;
GO
SELECT BASE64_DECODE('!!') AS bad_data;
```

```text
Msg 8116, Level 16, State 1, Line 1
Argument data type nvarchar is invalid for argument 1 of base64_encode function.
Msg 9803, Level 16, State 1, Line 1
Invalid data for type "Base64Decode".
```

## See also

[FORMAT](functions-format.md) · [Regular expressions and fuzzy matching](functions-regex-fuzzy.md) ·
[Conversion functions](functions-conversion.md) · [Logical functions](functions-logical.md) ·
[SELECT](select.md)
