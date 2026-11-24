# Oracle door: SQL and PL/SQL reference

The Oracle door takes Oracle SQL and PL/SQL. lexdb follows Oracle AI Database 26ai (23.26) and 23ai, and reports
itself as Oracle Database 23ai Free. The empty string is NULL, `DATE` has a time of day, and `||` ignores NULLs, as in
Oracle. Each page names what lexdb lacks or does differently.

## SQL statements

### Queries

| Statement | What it does |
|---|---|
| [SELECT](select.md) | Queries: select list and `DUAL`, `WHERE`, `ORDER BY`, `FETCH FIRST`, `ROWNUM`, set operations, `FOR UPDATE`. |
| [Joins](select-join.md) | `JOIN ... ON` and `USING`, outer joins, the `(+)` marker, `LATERAL`. |
| [GROUP BY](select-group-by.md) | Grouping, `ROLLUP`, `CUBE`, `GROUPING SETS`, `GROUP BY ALL`, `HAVING`. |
| [QUALIFY](qualify.md) | Filters on window functions, after them: `QUALIFY ROW_NUMBER() OVER (...) = 1`; select aliases visible (26ai). |
| [Hierarchical queries](hierarchical-queries.md) | `START WITH`, `CONNECT BY [NOCYCLE]`, `PRIOR`, `LEVEL`, `CONNECT_BY_ROOT`, `SYS_CONNECT_BY_PATH`, `ORDER SIBLINGS BY`. |
| [WITH](with.md) | Subquery factoring, recursive `WITH`. |
| [MATCH_RECOGNIZE](match-recognize.md) | Pattern matching over rows. |

### Changing data

| Statement | What it does |
|---|---|
| [INSERT](insert.md) | Adds rows; multi-row `VALUES`, `INSERT ... SET` and `BY NAME` (26ai), `RETURNING ... INTO`. |
| [UPDATE](update.md) | Changes rows; `RETURNING ... INTO`. |
| [DELETE](delete.md) | Removes rows; `RETURNING ... INTO`. |
| [MERGE](merge.md) | Inserts, updates or deletes by a join. |
| [TRUNCATE TABLE](truncate-table.md) | Empties a table. |

### Schema objects

| Statement | What it does |
|---|---|
| [CREATE TABLE](create-table.md) | Constraints, identity columns, `DEFAULT ON NULL`, virtual columns, `GLOBAL TEMPORARY ... ON COMMIT`. |
| [ALTER TABLE](alter-table.md) | `ADD`, `MODIFY`, `DROP`, `RENAME COLUMN`, constraints. |
| [DROP TABLE](drop-table.md) | `CASCADE CONSTRAINTS`, `PURGE`. |
| [CREATE INDEX](create-index.md), [DROP INDEX](drop-index.md) | Unique and function-based indexes; `ALTER INDEX ... RENAME`. |
| [CREATE VIEW](create-view.md), [DROP VIEW](drop-view.md) | `OR REPLACE`; views are read-only. |
| [CREATE SEQUENCE](create-sequence.md), [ALTER SEQUENCE](alter-sequence.md), [DROP SEQUENCE](drop-sequence.md) | `NEXTVAL`, `CURRVAL`. |
| [RENAME](rename.md) | Tables, views, sequences. |
| [COMMENT ON](comment-on.md) | Accepted; comments are not kept. |

### PL/SQL units

| Statement | What it does |
|---|---|
| [CREATE PROCEDURE](create-procedure.md), [DROP PROCEDURE](drop-procedure.md) | `OR REPLACE`; `IN`, `OUT` and `IN OUT` parameters. |
| [CREATE FUNCTION](create-function.md), [DROP FUNCTION](drop-function.md) | Functions callable from SQL and PL/SQL. |
| [CREATE PACKAGE](create-package.md), [DROP PACKAGE](drop-package.md) | Packages and package bodies. |
| [ALTER PROCEDURE, FUNCTION, PACKAGE](alter-procedure.md) | `COMPILE`: accepted. |
| [CALL and EXECUTE](call.md) | Calls a procedure (`EXEC` as SQL\*Plus and SQLcl write it). |

### Users and privileges

| Statement | What it does |
|---|---|
| [CREATE USER](create-user.md), [ALTER USER](alter-user.md), [DROP USER](drop-user.md) | `IDENTIFIED BY`, `ACCOUNT LOCK / UNLOCK`, `CASCADE`. A user is a schema. |
| [GRANT](grant.md), [REVOKE](revoke.md) | System privileges and roles (`CREATE SESSION`, `CONNECT`, `RESOURCE`, `DBA`) and object privileges. |
| [CREATE ROLE, DROP ROLE](create-role.md) | |

### Transactions and session

| Statement | What it does |
|---|---|
| [COMMIT](commit.md), [ROLLBACK](rollback.md), [SAVEPOINT](savepoint.md) | Transactions and savepoints. |
| [SET TRANSACTION](set-transaction.md) | Accepted; every read-write transaction is serializable. |
| [ALTER SESSION](alter-session.md) | `SET CURRENT_SCHEMA`, `TIME_ZONE`, the `NLS_*` parameters; many others accepted and ignored. |

### Not in this door

`INSERT ALL` / `INSERT FIRST`, triggers, synonyms (other than the dictionary's), database links, materialized
views, `LOCK TABLE` outside PL/SQL, `FLASHBACK`, `PURGE`, `AUDIT`, `EXPLAIN PLAN`, object types, collections.

## PL/SQL

| Page | What it covers |
|---|---|
| [Blocks](plsql-blocks.md) | `DECLARE ... BEGIN ... EXCEPTION ... END`, nested blocks, labels. |
| [Declarations](plsql-declarations.md) | Variables and constants, `%TYPE`, `%ROWTYPE`, records, the PL/SQL types. |
| [Control statements](plsql-control.md) | `IF`, `CASE`, `LOOP`, `WHILE`, `FOR`, `EXIT`, `CONTINUE`, `RETURN`, `NULL`. |
| [Cursors](plsql-cursors.md) | `OPEN`, `FETCH`, `CLOSE`, cursor `FOR` loops, `REF CURSOR`, the cursor attributes. |
| [SQL in PL/SQL](plsql-sql.md) | `SELECT ... INTO`, `RETURNING ... INTO`, `EXECUTE IMMEDIATE`. |
| [Exceptions](plsql-exceptions.md) | Handlers, predefined exceptions, `RAISE`, `RAISE_APPLICATION_ERROR`, `SQLCODE`, `SQLERRM`. |
| [Built-in packages](plsql-builtin-packages.md) | `DBMS_OUTPUT`, `DBMS_LOCK`, `DBMS_SESSION`, `DBMS_SQL.RETURN_RESULT`, and packages accepted and ignored. |

Not available: collections (nested tables, varrays, associative arrays), `FORALL`, `BULK COLLECT`, `GOTO`,
subprograms declared inside a block, DDL directly in a block (use `EXECUTE IMMEDIATE`).

## Data types

| Page | Types |
|---|---|
| [Numbers](data-types-number.md) | `NUMBER(p, s)`, `FLOAT`, `INTEGER`, `INT`, `SMALLINT`, `DECIMAL`, `NUMERIC`, `BINARY_FLOAT`, `BINARY_DOUBLE` |
| [Character](data-types-character.md) | `VARCHAR2(n [BYTE | CHAR])`, `NVARCHAR2(n)`, `CHAR(n)`, `NCHAR(n)`, `CLOB`, `NCLOB`, `LONG` |
| [Date and time](data-types-datetime.md) | `DATE`, `TIMESTAMP(p)`, `TIMESTAMP WITH TIME ZONE`, `TIMESTAMP WITH LOCAL TIME ZONE`, `INTERVAL YEAR TO MONTH`, `INTERVAL DAY TO SECOND` |
| [Binary, boolean and others](data-types-other.md) | `RAW(n)`, `BLOB`, `LONG RAW`, `BOOLEAN` (23ai), `ROWID`, `UROWID`; PL/SQL-only types are on the [declarations](plsql-declarations.md) page |

Not available: `XMLTYPE`, `JSON`, `VECTOR`, `BFILE` contents, object and collection types, negative `NUMBER` scales.

## Functions

| Page | Functions |
|---|---|
| [Character functions](functions-character.md) | `SUBSTR`, `INSTR`, `LENGTH`, `LENGTHB`, `UPPER`, `LOWER`, `INITCAP`, `LPAD`, `RPAD`, `LTRIM`, `RTRIM`, `TRIM`, `REPLACE`, `TRANSLATE`, `CONCAT`, `CHR`, `ASCII`, `UNISTR`, `RAWTOHEX`, `HEXTORAW`, `TO_CLOB`, `SYS_GUID` |
| [Regular expressions](functions-regex.md) | `REGEXP_LIKE`, `REGEXP_REPLACE`, `REGEXP_SUBSTR`, `REGEXP_INSTR`, `REGEXP_COUNT` |
| [Package functions usable in SQL](functions-packages.md) | `UTL_MATCH.EDIT_DISTANCE`, `EDIT_DISTANCE_SIMILARITY`, `JARO_WINKLER`, `JARO_WINKLER_SIMILARITY`, `UTL_ENCODE.BASE64_ENCODE` and `BASE64_DECODE`, `UTL_RAW.CAST_TO_RAW` and `CAST_TO_VARCHAR2`, `DBMS_LOB.GETLENGTH` and `SUBSTR` |
| [Numeric functions](functions-numeric.md) | `ABS`, `CEIL`, `FLOOR`, `ROUND`, `TRUNC`, `MOD`, `SIGN`, `POWER`, `SQRT`, `EXP`, `LN`, `LOG`, `BITAND`, `WIDTH_BUCKET`, and the trigonometric functions |
| [Date and time functions](functions-datetime.md) | `SYSDATE`, `SYSTIMESTAMP`, `CURRENT_DATE`, `ADD_MONTHS`, `MONTHS_BETWEEN`, `LAST_DAY`, `NEXT_DAY`, `EXTRACT`, `TRUNC` and `ROUND` of dates, `SYS_EXTRACT_UTC`, `FROM_TZ`, `NUMTODSINTERVAL`, `NUMTOYMINTERVAL`, `TIME_BUCKET` |
| [Conversion functions](functions-conversion.md) | `TO_CHAR`, `TO_NCHAR`, `TO_DATE`, `TO_TIMESTAMP`, `TO_NUMBER`, `TO_BOOLEAN`, `CAST` |
| [NULL-handling and conditional functions](functions-null.md) | `NVL`, `NVL2`, `NULLIF`, `COALESCE`, `DECODE`, `GREATEST`, `LEAST`, `CASE` |
| [Aggregate functions](functions-aggregate.md) | `COUNT`, `SUM`, `AVG`, `MIN`, `MAX`, `STDDEV`, `VARIANCE`, `LISTAGG`, `ANY_VALUE`, `PERCENTILE_CONT`, `PERCENTILE_DISC`, `BIT_AND_AGG`, `BIT_OR_AGG`, `BIT_XOR_AGG`, `BOOLEAN_AND_AGG`, `BOOLEAN_OR_AGG`, `KURTOSIS_*`, `SKEWNESS_*` |
| [Analytic functions](functions-analytic.md) | `ROW_NUMBER`, `RANK`, `DENSE_RANK`, `PERCENT_RANK`, `CUME_DIST`, `NTILE`, `LAG`, `LEAD`, `FIRST_VALUE`, `LAST_VALUE`, `NTH_VALUE`, and aggregates with `OVER` |
| [Environment and sequence functions](functions-environment.md) | `USER`, `UID`, `SYS_CONTEXT('USERENV', ...)`, `SYS_GUID`, `UUID`, `IS_UUID`, `RAW_TO_UUID`, `UUID_TO_RAW`, `ROWNUM`, `NEXTVAL`, `CURRVAL` |

Not available: `NANVL`, `LNNVL`, `SOUNDEX`, `ORA_HASH`, `STANDARD_HASH`, `VSIZE`, `DUMP`, `TO_DSINTERVAL`,
`TO_YMINTERVAL`, `MEDIAN`, `STATS_MODE`, `CORR`, `COVAR_*`, `REGR_*`, `RATIO_TO_REPORT`, the XML and JSON functions.

## Operators

[Operators](operators.md): arithmetic `+ - * /`; `||` concatenation (NULL-ignoring); comparison `= <> != < <= > >=`;
`LIKE`, `IN`, `BETWEEN`, `EXISTS`, `ANY`/`SOME`/`ALL`, `IS [NOT] NULL`, `IS [NOT] DISTINCT FROM` (lexdb's extension);
`AND`, `OR`, `NOT`; `PRIOR`; the outer join marker `(+)`.

## Data dictionary

| Page | Views |
|---|---|
| [Tables, columns, indexes and constraints](data-dictionary-tables.md) | `USER_`, `ALL_` and `DBA_` `TABLES`, `TAB_COLUMNS`, `INDEXES`, `IND_COLUMNS`, `IND_EXPRESSIONS`, `CONSTRAINTS`, `CONS_COLUMNS`, `TAB_IDENTITY_COLS`, `OBJECTS`, `CATALOG`; `TABS`, `COLS`, `DICT`, `DICTIONARY`, `DUAL` |
| [Views, sequences, procedures and source](data-dictionary-programs.md) | `VIEWS`, `SEQUENCES`, `SOURCE`, `PROCEDURES`, `ARGUMENTS`, `ERRORS`, `TRIGGERS`, `SYNONYMS` |
| [Users, privileges, parameters and V$ views](data-dictionary-system.md) | `USER_USERS`, `ALL_USERS`, `DBA_USERS`, `USER_TAB_PRIVS`, `SESSION_PRIVS`, `NLS_SESSION_PARAMETERS`, `DATABASE_PROPERTIES`, `PRODUCT_COMPONENT_VERSION`, `V$VERSION`, `V$INSTANCE`, `V$DATABASE`, `V$SESSION`, `V$PARAMETER` |

## Errors

[Errors](errors.md) lists the `ORA-` and `PLS-` errors lexdb gives, with their causes and examples: ORA-00001 (unique
constraint), ORA-01400 (NULL), ORA-02290 (check), ORA-02291 and ORA-02292 (foreign key), ORA-00942 (no such table or
view), ORA-00904 (invalid identifier), ORA-00900 and ORA-00933 (syntax), ORA-01722 (invalid number), ORA-01438 and
ORA-12899 (value too large), ORA-01476 (divisor is zero), ORA-01403 (no data found), ORA-08177 (serialization failure:
retry), ORA-16000 (read-only replica), ORA-03001 (not supported by lexdb), and PL/SQL's `PLS-` errors under ORA-06550.
