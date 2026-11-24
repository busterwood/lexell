# Connecting through the Oracle door

The Oracle door speaks TNS with TTC on top, the protocol of Oracle's **thin** drivers, and Oracle SQL and PL/SQL. It
is opened with `--tns HOST:PORT`, and inside TLS (TCPS) with `--tcps HOST:PORT`. lexdb reports itself as Oracle
Database 23ai Free (23.0.0.0.0). For SQL it follows Oracle 23ai and 26ai.

## Listening

```sh
lexdb ./data --tns 127.0.0.1:1521
lexdb ./data --tns 127.0.0.1:1521 --tcps 127.0.0.1:2484 --tls-cert server.pem --tls-key server.key
```

TCP only. There is no separate listener process and no `listener.ora`: lexdb is its own listener.

## The protocol

- **CONNECT** with a connect descriptor or Easy Connect. The service name (or SID) must be `lexdb` or `FREEPDB1`
  (any case), or none. Another name is refused with ORA-12514. The read-only service names (`lexdb_ro`,
  `freepdb1_ro`) are redirected to a replica: see [replicas](../replicas.md#oracle).
- **Thin drivers only.** Clients that use Oracle's client libraries (OCI, "thick" mode, SQL*Plus, Instant Client
  programs) do not work: they need Net Native Encryption and other negotiations lexdb does not have.
- **Requests**: execute (parse, bind, execute, fetch), fetch, commit, rollback, logoff, ping, cursor close; binds
  by position (`:1`) and by name (`:name`); array DML (`executeBatch`, `executemany`) with row counts and batch
  errors; `RETURNING ... INTO`; PL/SQL blocks with OUT and IN OUT binds; REF CURSOR OUT binds and implicit results
  (`DBMS_SQL.RETURN_RESULT`); LOBs (CLOB, BLOB).
- **Transactions** as Oracle's: the first DML begins one, COMMIT or the driver's commit flag (autocommit) ends it,
  DDL commits the open transaction first, and a failed statement is undone alone (the transaction goes on).
- **Result types.** Integers and numerics as NUMBER, `BINARY_DOUBLE`, `BINARY_FLOAT`, `BOOLEAN` (NUMBER(1) for
  older clients), DATE, TIMESTAMP, TIMESTAMP WITH TIME ZONE (with each value's offset: `OffsetDateTime` in JDBC),
  RAW, VARCHAR2, CLOB and BLOB.
- **Errors** are ORA- numbers: ORA-00942 for a missing table, ORA-00001 for a duplicate key, ORA-01400 for a NULL
  into a NOT NULL column. A failed statement in a session cursor gives ORA-01403 at its end, as Oracle does.

## Logins

- **Password verifiers.** Oracle's login proves the password through keys derived from it (the 12c verifier,
  PBKDF2-SHA512). lexdb keeps such a verifier for every role whose password is set in any door (`CREATE USER ...
  IDENTIFIED BY`, `ALTER USER`, `CREATE ROLE ... PASSWORD`). The 11g verifier is not offered.
- **Under `--auth trust`** a user with no verifier logs in with **its own name as the password**, as the driver sends
  the name: JDBC and SQLcl upper-case an unquoted user name, so the password of `sa` is `SA` there; Lexell's
  `oracle` module sends the name as written, so it is `sa`. A user with a password set logs in with that password.
- `SYS` and `AS SYSDBA` logins are refused.
- **A user is a schema**, as in Oracle. A login's first connection makes the schema of its name (`sa` works in schema
  `SA`). See [Schemas](#schemas) below.

## Schemas

The Oracle door shares one store and one catalog with the other two doors, and looks names up like this:

- A name without a schema is looked for in the login's own schema first, then in `public`, the PostgreSQL door's
  schema (which the SQL Server door calls `dbo`). `public` takes the part of Oracle's `PUBLIC` synonyms: its tables
  are found by their bare name, or as `public.name`.
- A table, view, sequence or program the login makes is made in its own schema. A table of the same name in `public`
  does not stop it (no ORA-00955), and the login's own table is the one a bare name finds.
- Another user's objects are `user.name`. `ALTER SESSION SET CURRENT_SCHEMA` changes the default schema.

The other doors see the Oracle door's objects by schema and by the name in upper case, which is how the Oracle door
stores a name that was not quoted. A table that the login `sa` made with `CREATE TABLE city` is `sa."CITY"` in the
PostgreSQL door and `sa.CITY` in the SQL Server door; neither finds it as `city` or in `public`/`dbo`. In the other
direction, a table made in the PostgreSQL or SQL Server door is in `public`, and the Oracle door finds it as `city`
or `public.city` (its columns come back in lower case, as they were made).

```sql
-- PostgreSQL door:                     SELECT * FROM sa."CITY";
-- SQL Server door:                     SELECT * FROM sa.CITY;
-- Oracle door, a table of public:      SELECT * FROM public.city;
```

A login's schema is made when the login first connects through the Oracle door, so a role that has not connected
there has none. Objects that an older lexdb made for the login `sa` stay in `public`, and are still found there.
`CREATE USER` makes the schema of the new user at once.

## TCPS (TLS)

`--tcps HOST:PORT` serves TNS inside TLS with the certificate of `--tls-cert`. `--require-tls` refuses plain `--tns`
logins. With a self-signed certificate, give the client a trust store, and connect by a host name the certificate
names (ojdbc checks it: ORA-17965 otherwise):

```sh
keytool -importcert -alias lexdb -file server.pem -keystore ts.jks -storepass changeit -noprompt
java -Djavax.net.ssl.trustStore=ts.jks -Djavax.net.ssl.trustStorePassword=changeit ... \
  'jdbc:oracle:thin:@tcps://localhost:2484/lexdb'
```

## Connection strings

| Client | Example |
|---|---|
| JDBC thin | `jdbc:oracle:thin:@//127.0.0.1:1521/lexdb` |
| a descriptor | `(DESCRIPTION=(ADDRESS=(PROTOCOL=tcp)(HOST=127.0.0.1)(PORT=1521))(CONNECT_DATA=(SERVICE_NAME=lexdb)))` |
| python-oracledb thin | `oracledb.connect(user="sa", password="sa", dsn="127.0.0.1:1521/lexdb")` |
| SQLcl | `sql sa/SA@127.0.0.1:1521/lexdb` |
| Lexell `oracle` | `User Id=sa;Password=sa;Data Source=127.0.0.1:1521/lexdb` |

## Clients known to work

Checked for this documentation (2026-11-23), against a lexdb built from the same tree:

- **ojdbc11 23.26.4** (Oracle's JDBC thin driver).
- **Lexell's `oracle` module** (lib/oracle).

Checked while lexdb was developed (design/lexdb-oracle.md, 9.137): python-oracledb 26.1 in thin mode, SQLcl (its
`INFO` and `DDL` commands), node-oracledb 6 in thin mode. SQL*Plus is a thick client and does not connect.

## A first session

<!-- example: oracle -->
```sql
SELECT banner FROM v$version;
SELECT USER, SYS_CONTEXT('USERENV', 'CURRENT_SCHEMA') AS current_schema, SYS_CONTEXT('USERENV', 'DB_NAME') AS db FROM dual;
SELECT open_mode, database_role FROM v$database;
```

```text
BANNER
-------------------------------------------------------------------------------
Oracle Database 23ai Free Release 23.0.0.0.0 - Develop, Learn, and Run for Free

1 row selected.

USER CURRENT_SCHEMA DB
---- -------------- -----
SA   SA             LEXDB

1 row selected.

OPEN_MODE  DATABASE_ROLE
---------- -------------
READ WRITE PRIMARY

1 row selected.
```

## Java: ojdbc

[OraHello.java](examples/java/OraHello.java) makes a table, inserts rows with a batch of prepared statements (sent as
one array DML call), calls a PL/SQL block with an OUT bind, and shows a transaction rolled back by a CHECK
constraint.

```sh
javac -d out docs/lexdb/connect/examples/java/OraHello.java
java -cp out:ojdbc11-23.26.4.0.0.jar OraHello jdbc:oracle:thin:@//127.0.0.1:1521/lexdb sa SA
```

```
server: Oracle Database 23ai Free Release 23.0.0.0.0 - Develop, Learn, and Run for Free
batch: 3 rows
rows: 3
transaction: rolled back, ORA-02290
1 apple 1.2
2 pear 0.85
3 plum 2.4
```

`getBigDecimal` gives `1.2`, not `1.20`: an Oracle NUMBER keeps no trailing zeros, in Oracle as in lexdb. The driver is
on Maven Central as `com.oracle.database.jdbc:ojdbc11`
(`https://repo1.maven.org/maven2/com/oracle/database/jdbc/ojdbc11/23.26.4.0.0/ojdbc11-23.26.4.0.0.jar`).

## Lexell: lib/oracle

[tns_hello.lxl](examples/lexell/tns_hello.lxl) does the same with Lexell's own client, which speaks TNS itself:

```sh
lexell/compiler/out/lxlc lexell/docs/lexdb/connect/examples/lexell/tns_hello.lxl -o tns_hello
./tns_hello "User Id=sa;Password=sa;Data Source=127.0.0.1:1521/lexdb"
```

```
server: Oracle Database 23ai Free Release 23.0.0.0.0 - Develop, Learn, and Run for Free
transaction: rolled back, ORA-2290
1 apple 1.20
2 pear 1.70
3 plum 2.40
```

Outside `transaction()` the module commits each statement with its execute, as SQL Server clients do.

## See also

- [The Oracle SQL and PL/SQL reference](../sql/oracle/README.md)
- [Bulk loading: array DML](../bulk-load.md#oracle-array-dml)
- [Read replicas](../replicas.md#oracle)
