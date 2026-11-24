# Environment and sequence functions

`USER`, `UID`, `SYS_CONTEXT`, `SYS_GUID`, `UUID`, `ROWNUM`, `NEXTVAL` and `CURRVAL`.

**Door:** Oracle (TNS). **Follows:** Oracle AI Database 26ai (23.26) and 23ai.

## Syntax

```
USER
UID
SYS_CONTEXT ( 'USERENV', parameter )
SYS_GUID ( )
UUID ( )    IS_UUID ( text )    RAW_TO_UUID ( raw )    UUID_TO_RAW ( text )
ROWNUM
sequence.NEXTVAL    sequence.CURRVAL
```

## Functions

`USER`
: The name of the login (`SA` for the checker's login). It is a pseudo-column, written without brackets.

`UID`
: The numeric id of the login.

`SYS_CONTEXT('USERENV', parameter)`
: A property of the session. The parameters lexdb knows include `SESSION_USER`, `CURRENT_USER`, `CURRENT_SCHEMA`,
  `SESSION_SCHEMA`, `DB_NAME`, `INSTANCE_NAME`, `NLS_DATE_FORMAT`, `NLS_TERRITORY`, `NLS_SORT`, `NLS_CURRENCY`,
  `NLS_DATE_LANGUAGE`, `LANGUAGE`, `SESSIONID` and others; an unknown parameter is NULL. `CURRENT_SCHEMA` and the
  `NLS_*` ones follow `ALTER SESSION` (see [ALTER SESSION](alter-session.md)).

`SYS_GUID`
: A new 16-byte `RAW` identifier.

`UUID`, `IS_UUID`, `RAW_TO_UUID`, `UUID_TO_RAW`
: Make a version 4 UUID as text, test text for being one, and convert between `RAW(16)` and the text form
  (Oracle 26ai).

`ROWNUM`
: The number of the row in the result, from 1, before sorting: see [SELECT](select.md).

`NEXTVAL`, `CURRVAL`
: The next value of a sequence, and the one `NEXTVAL` last gave in the session: see
  [CREATE SEQUENCE](create-sequence.md).

## Remarks

- Values of `USER`, `UID`, `SYS_GUID` and `UUID` differ between sessions and runs; the examples test them rather than
  print them.
- `SYSDATE` and the other clock functions are on the [date and time functions](functions-datetime.md) page.

## Differences from Oracle

- `SYS_CONTEXT('USERENV', 'NLS_CURRENCY')` is `$` until a territory is set.
- `ROWID` is not a pseudo-column here (ORA-00904), and `ORA_DATABASE_NAME` is ORA-00904 (use
  `SYS_CONTEXT('USERENV', 'DB_NAME')`).

## Examples

### A. The session

<!-- example: oracle -->
```sql
SELECT USER AS login, CASE WHEN UID > 0 THEN 'has id' END AS uid_ FROM dual;
SELECT ORA_DATABASE_NAME FROM dual;
SELECT SYS_CONTEXT('USERENV', 'SESSION_USER') AS session_user, SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS schema_,
       SYS_CONTEXT('USERENV', 'DB_NAME') AS db_name, SYS_CONTEXT('USERENV', 'NO_SUCH_PARAMETER') AS unknown
FROM dual;
```

```text
LOGIN UID_
----- ------
SA    has id

1 row selected.

ERROR:
ORA-00904: "ORA_DATABASE_NAME": invalid identifier

SESSION_USER SCHEMA_ DB_NAME UNKNOWN
------------ ------- ------- -------
SA           SA      LEXDB

1 row selected.
```

### B. Identifiers

<!-- example: oracle -->
```sql
SELECT CASE WHEN SYS_GUID() IS NOT NULL THEN 'made' END AS guid, LENGTH(RAWTOHEX(SYS_GUID())) AS hex_digits,
       IS_UUID('6F9619FF-8B86-D011-B42D-00C04FC964FF') AS is_uuid, IS_UUID('not a uuid') AS not_uuid,
       RAW_TO_UUID(HEXTORAW('6F9619FF8B86D011B42D00C04FC964FF')) AS as_text,
       RAWTOHEX(UUID_TO_RAW('6f9619ff-8b86-d011-b42d-00c04fc964ff')) AS as_raw,
       CASE WHEN LENGTH(UUID()) = 36 THEN 'uuid' END AS new_uuid
FROM dual;
```

```text
GUID HEX_DIGITS IS_UUID NOT_UUID AS_TEXT                              AS_RAW                           NEW_UUID
---- ---------- ------- -------- ------------------------------------ -------------------------------- --------
made         64 true    false    6f9619ff-8b86-d011-b42d-00c04fc964ff 6F9619FF8B86D011B42D00C04FC964FF

1 row selected.
```

### C. ROWNUM and sequences

<!-- example: oracle -->
```sql
CREATE SEQUENCE sq START WITH 10 INCREMENT BY 5;
CREATE TABLE t (v VARCHAR2(5));
INSERT INTO t VALUES ('a');
INSERT INTO t VALUES ('b');
INSERT INTO t VALUES ('c');
SELECT v, ROWNUM AS n, sq.NEXTVAL AS next_value FROM t;
SELECT sq.CURRVAL AS current_value FROM dual;
SELECT ROWID FROM t;
```

```text
Sequence created.

Table created.

1 row created.

1 row created.

1 row created.

V N NEXT_VALUE
- - ----------
a 1         10
b 2         15
c 3         20

3 rows selected.

CURRENT_VALUE
-------------
           20

1 row selected.

ERROR:
ORA-00904: "ROWID": invalid identifier
```

## See also

[Date and time functions](functions-datetime.md), [CREATE SEQUENCE](create-sequence.md), [ALTER SESSION](alter-session.md)
