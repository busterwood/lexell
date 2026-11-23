# Oracle door: SQL and PL/SQL reference

The Oracle door takes Oracle SQL and PL/SQL. lexdb follows Oracle AI Database 26ai (23.26) and 23ai, and reports
itself as Oracle Database 23ai Free. The empty string is NULL, `DATE` has a time of day, and `||` ignores NULLs, as in
Oracle. Each page names what lexdb lacks or does differently.

This index lists everything the door takes today. Pages not written yet are listed without a link.

## SQL statements

### Queries

| Statement | What it does |
|---|---|
| SELECT | Joins (also `(+)`), grouping, `GROUP BY ALL`, analytic functions, `FETCH FIRST`, `ROWNUM`, set operations, `FROM DUAL` (or no `FROM`), `MATCH_RECOGNIZE`, `FOR UPDATE`. |
| Hierarchical queries | `START WITH`, `CONNECT BY [NOCYCLE]`, `PRIOR`, `LEVEL`, `CONNECT_BY_ROOT`, `SYS_CONNECT_BY_PATH`, `ORDER SIBLINGS BY`. |
| WITH | Subquery factoring, recursive `WITH`. |

### Changing data

| Statement | What it does |
|---|---|
| [INSERT](insert.md) | Adds rows; multi-row `VALUES`, `INSERT ... SET` and `BY NAME` (26ai), `RETURNING ... INTO`. |
| UPDATE | Changes rows; `RETURNING ... INTO`. |
| DELETE | Removes rows; `RETURNING ... INTO`. |
| MERGE | Inserts, updates or deletes by a join. |
| TRUNCATE TABLE | Empties a table. |

### Schema objects

| Statement | What it does |
|---|---|
| CREATE TABLE | Constraints, identity columns, `DEFAULT ON NULL`, virtual columns, `GLOBAL TEMPORARY ... ON COMMIT`. |
| ALTER TABLE | `ADD`, `MODIFY`, `DROP`, `RENAME COLUMN`, constraints. |
| DROP TABLE | `CASCADE CONSTRAINTS`, `PURGE`. |
| CREATE INDEX, DROP INDEX | Unique and function-based indexes. |
| CREATE VIEW, DROP VIEW | `OR REPLACE`. |
| CREATE SEQUENCE, ALTER SEQUENCE, DROP SEQUENCE | `NEXTVAL`, `CURRVAL`. |
| RENAME | Tables, views, sequences. |
| COMMENT ON | Accepted; comments are not kept. |

### PL/SQL units

| Statement | What it does |
|---|---|
| CREATE PROCEDURE, CREATE FUNCTION | `OR REPLACE`; IN, OUT and IN OUT parameters. A unit with errors is stored invalid (ORA-24344). |
| CREATE PACKAGE, CREATE PACKAGE BODY | Packages of procedures, functions, variables and cursors. |
| DROP PROCEDURE, DROP FUNCTION, DROP PACKAGE | |
| ALTER PROCEDURE / FUNCTION / PACKAGE ... COMPILE | Accepted. |
| CALL, EXECUTE | Calls a procedure (`EXEC` as SQL\*Plus and SQLcl write it). |

### Users and privileges

| Statement | What it does |
|---|---|
| CREATE USER, ALTER USER, DROP USER | `IDENTIFIED BY`, `ACCOUNT LOCK / UNLOCK`, `CASCADE`. A user is a schema. |
| GRANT, REVOKE | System privileges and roles (`CREATE SESSION`, `CONNECT`, `RESOURCE`, `DBA`) and object privileges. |
| CREATE ROLE | |

### Transactions and session

| Statement | What it does |
|---|---|
| COMMIT, ROLLBACK, SAVEPOINT, ROLLBACK TO SAVEPOINT | |
| SET TRANSACTION | Accepted; every read-write transaction is serializable. |
| ALTER SESSION | `SET CURRENT_SCHEMA`, `TIME_ZONE`, the `NLS_*` parameters; many others accepted and ignored. |

### Not in this door

`INSERT ALL` / `INSERT FIRST`, triggers, synonyms (other than the dictionary's), database links, materialized
views, `LOCK TABLE` outside PL/SQL, `FLASHBACK`, `PURGE`, `AUDIT`, `EXPLAIN PLAN`, object types, collections.

## PL/SQL

| Construct | What it does |
|---|---|
| Blocks | `DECLARE ... BEGIN ... EXCEPTION ... END`, nested blocks, labels. |
| Declarations | Variables and constants, `%TYPE`, `%ROWTYPE`, records (`TYPE ... IS RECORD`), `REF CURSOR` and `SYS_REFCURSOR`, cursors with parameters, exceptions, `PRAGMA EXCEPTION_INIT`. |
| Control | `IF`, `CASE`, `LOOP`, `WHILE`, `FOR i IN [REVERSE] a .. b`, cursor `FOR` loops, `EXIT`, `CONTINUE`, `RETURN`, `NULL`. |
| SQL in PL/SQL | `SELECT ... INTO`, DML with `RETURNING ... INTO`, `OPEN`, `FETCH`, `CLOSE`, `OPEN ... FOR`, `EXECUTE IMMEDIATE ... INTO ... USING`, `COMMIT`, `ROLLBACK`, `SAVEPOINT`. |
| Errors | `RAISE`, `RAISE_APPLICATION_ERROR`, `SQLCODE`, `SQLERRM`, the predefined exceptions (`NO_DATA_FOUND`, `TOO_MANY_ROWS`, `DUP_VAL_ON_INDEX`, `ZERO_DIVIDE`, `VALUE_ERROR`, `INVALID_NUMBER` and others). |
| Attributes | `SQL%ROWCOUNT`, `%FOUND`, `%NOTFOUND`, `%ISOPEN`. |
| Packages | `DBMS_OUTPUT` (`PUT_LINE`, `PUT`, `NEW_LINE`, `ENABLE`, `DISABLE`, `GET_LINE`, `GET_LINES`), `DBMS_SQL.RETURN_RESULT`, `DBMS_LOCK.SLEEP`, `DBMS_SESSION.SLEEP`, `DBMS_UTILITY.NAME_RESOLVE`; `DBMS_STATS`, `DBMS_APPLICATION_INFO`, `DBMS_METADATA.SET_TRANSFORM_PARAM` accepted. |

Not available: collections (nested tables, varrays, associative arrays), `FORALL`, `BULK COLLECT`, `GOTO`,
subprograms declared inside a block, DDL directly in a block (use `EXECUTE IMMEDIATE`).

## Data types

| Type | Names |
|---|---|
| Numbers | `NUMBER(p, s)`, `NUMBER`, `FLOAT(p)`, `INTEGER`, `INT`, `SMALLINT`, `DECIMAL`, `NUMERIC`, `BINARY_FLOAT`, `BINARY_DOUBLE` |
| Character | `VARCHAR2(n [BYTE | CHAR])`, `NVARCHAR2(n)`, `CHAR(n)`, `NCHAR(n)`, `CLOB`, `NCLOB`, `LONG` |
| Binary | `RAW(n)`, `BLOB`, `LONG RAW` |
| Date and time | `DATE`, `TIMESTAMP(p)`, `TIMESTAMP WITH TIME ZONE`, `TIMESTAMP WITH LOCAL TIME ZONE`, `INTERVAL YEAR TO MONTH`, `INTERVAL DAY TO SECOND` |
| Other | `BOOLEAN` (23ai), `ROWID`, `UROWID` |
| PL/SQL only | `PLS_INTEGER`, `BINARY_INTEGER`, `SIMPLE_INTEGER`, `NATURAL`, `POSITIVE`, `SIGNTYPE`, `STRING`, `SYS_REFCURSOR` |

Not available: `XMLTYPE`, `JSON`, `VECTOR`, `BFILE` contents, object and collection types, negative `NUMBER` scales.

## Functions

| Family | Functions |
|---|---|
| Character | `SUBSTR`, `INSTR`, `LENGTH`, `LENGTHB`, `UPPER`, `LOWER`, `INITCAP`, `LPAD`, `RPAD`, `LTRIM`, `RTRIM`, `TRIM`, `REPLACE`, `TRANSLATE`, `CONCAT`, `CHR`, `ASCII`, `UNISTR`, `RAWTOHEX`, `HEXTORAW`, `TO_CLOB`, `SYS_GUID` |
| Regular expressions | `REGEXP_LIKE`, `REGEXP_REPLACE`, `REGEXP_SUBSTR`, `REGEXP_INSTR`, `REGEXP_COUNT` |
| Numeric | `ABS`, `CEIL`, `FLOOR`, `ROUND`, `TRUNC`, `MOD`, `SIGN`, `POWER`, `SQRT`, `EXP`, `LN`, `LOG`, `BITAND`, `WIDTH_BUCKET`, and the trigonometric functions |
| Date and time | `SYSDATE`, `SYSTIMESTAMP`, `CURRENT_DATE`, `CURRENT_TIMESTAMP`, `ADD_MONTHS`, `MONTHS_BETWEEN`, `LAST_DAY`, `NEXT_DAY`, `EXTRACT`, `TRUNC` and `ROUND` of dates, `SYS_EXTRACT_UTC`, `FROM_TZ`, `NUMTODSINTERVAL`, `NUMTOYMINTERVAL`, `SESSIONTIMEZONE`, `DBTIMEZONE`, `TIME_BUCKET`, `DATEADD`, `DATEDIFF`, `TIMESTAMPDIFF` (26ai) |
| Conversion | `TO_CHAR`, `TO_NCHAR`, `TO_DATE`, `TO_TIMESTAMP`, `TO_NUMBER`, `TO_BOOLEAN`, `CAST` |
| Null handling | `NVL`, `NVL2`, `NULLIF`, `COALESCE`, `DECODE`, `GREATEST`, `LEAST` |
| Aggregate | `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `LISTAGG`, `STDDEV`, `VARIANCE`, `ANY_VALUE`, `PERCENTILE_CONT`, `PERCENTILE_DISC`, `BIT_AND_AGG`, `BIT_OR_AGG`, `BIT_XOR_AGG`, `BOOLEAN_AND_AGG`, `BOOLEAN_OR_AGG`, `KURTOSIS_POP`, `KURTOSIS_SAMP`, `SKEWNESS_POP`, `SKEWNESS_SAMP` |
| Analytic | `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `PERCENT_RANK`, `CUME_DIST`, `NTILE`, `LAG`, `LEAD`, `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE` (with `IGNORE NULLS`), and aggregates with `OVER` |
| UUID (26ai) | `UUID`, `IS_UUID`, `RAW_TO_UUID`, `UUID_TO_RAW` |
| Environment | `USER`, `UID`, `SYS_CONTEXT('USERENV', ...)`, `ORA_DATABASE_NAME` |
| Packages in SQL | `DBMS_LOB.GETLENGTH`, `DBMS_LOB.SUBSTR`, `UTL_RAW.CAST_TO_RAW`, `UTL_RAW.CAST_TO_VARCHAR2`, `UTL_ENCODE.BASE64_ENCODE`, `UTL_ENCODE.BASE64_DECODE`, `UTL_MATCH.EDIT_DISTANCE`, `UTL_MATCH.EDIT_DISTANCE_SIMILARITY`, `UTL_MATCH.JARO_WINKLER`, `UTL_MATCH.JARO_WINKLER_SIMILARITY` |

Not available: `NANVL`, `LNNVL`, `SOUNDEX`, `ORA_HASH`, `STANDARD_HASH`, `VSIZE`, `DUMP`, `TO_DSINTERVAL`,
`TO_YMINTERVAL`, `MEDIAN`, `STATS_MODE`, `CORR`, `COVAR_*`, `REGR_*`, `RATIO_TO_REPORT`, the XML and JSON functions.

## Operators

Arithmetic `+ - * /` (also on dates and intervals); `||` concatenation (NULL-ignoring); comparison `= <> != ^= < <=
> >=`; `LIKE`, `IN`, `BETWEEN`, `EXISTS`, `ANY`/`SOME`/`ALL`, `IS [NOT] NULL`, `IS [NOT] DISTINCT FROM` (lexdb's
extension); `AND`, `OR`, `NOT`; `PRIOR`; the outer join marker `(+)`.

## Data dictionary

- **ALL_, DBA_ and USER_ views** of lexdb's catalog: `TABLES`, `TAB_COLUMNS`, `TAB_COLS`, `INDEXES`, `IND_COLUMNS`,
  `IND_EXPRESSIONS`, `CONSTRAINTS`, `CONS_COLUMNS`, `OBJECTS`, `SEQUENCES`, `VIEWS`, `TAB_COMMENTS`,
  `COL_COMMENTS`, `TAB_IDENTITY_COLS`, `CATALOG`, `SOURCE`, `PROCEDURES`, `TAB_PRIVS`, `USERS`; and many more that
  tools read, empty where lexdb has no such object (`SYNONYMS`, `TRIGGERS`, `MVIEWS`, `PART_TABLES`, ...).
- **Other views**: `DICTIONARY`, `DICT_COLUMNS`, `NLS_SESSION_PARAMETERS`, `NLS_DATABASE_PARAMETERS`,
  `NLS_INSTANCE_PARAMETERS`, `DATABASE_PROPERTIES`, `PRODUCT_COMPONENT_VERSION`, `SESSION_PRIVS`, `SESSION_ROLES`;
  `TABS`, `COLS`, `DICT`; `DUAL`.
- **Dynamic performance views**: `V$DATABASE`, `V$INSTANCE`, `V$SESSION`, `V$VERSION`, `V$PARAMETER`,
  `V$NLS_PARAMETERS`, `V$TIMEZONE_NAMES`, `V$MYSTAT`, `V$SESSTAT`, `V$STATNAME`, `V$TRANSACTION`, `V$LOCK`,
  `V$SQL` and others.

## Session parameters

`ALTER SESSION SET`: `CURRENT_SCHEMA`, `TIME_ZONE`, `NLS_DATE_FORMAT`, `NLS_TIMESTAMP_FORMAT`,
`NLS_TIMESTAMP_TZ_FORMAT`, `NLS_TIME_FORMAT`, `NLS_NUMERIC_CHARACTERS`, `NLS_LANGUAGE`, `NLS_TERRITORY`,
`NLS_DATE_LANGUAGE`, `NLS_CURRENCY`, `NLS_ISO_CURRENCY`, `NLS_SORT`, `NLS_COMP`, `NLS_LENGTH_SEMANTICS` and the other
`NLS_*` parameters, `GROUP_BY_POSITION_ENABLED`. `OPTIMIZER_*`, `SQL_TRACE`, `ISOLATION_LEVEL`, `CURSOR_SHARING`
and many others are accepted and ignored; an unknown name is ORA-02248.

## Errors

Errors carry Oracle's `ORA-` numbers: ORA-00001 (unique constraint), ORA-01400 (NULL), ORA-02290 (check),
ORA-02291 and ORA-02292 (foreign key), ORA-00942 (no such table or view), ORA-00904 (invalid identifier), ORA-00900
and ORA-00933 (syntax), ORA-01722 (invalid number), ORA-01438 and ORA-12899 (value too large), ORA-01476 (divisor is
zero), ORA-01403 (no data found), ORA-08177 (serialization failure: retry), ORA-16000 (read-only replica),
ORA-03001 (not supported by lexdb), and PL/SQL's `PLS-` errors under ORA-06550.
