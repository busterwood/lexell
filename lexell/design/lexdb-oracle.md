# lexdb speaks Oracle: a TNS/TTC endpoint and an Oracle SQL dialect

Design only (2026-11-13); nothing is built. Parallel to design/lexdb-tds.md
(SQL Server); read that first, this one only says where Oracle differs.

## 1. What and why

lexdb already has two front doors: the PostgreSQL protocol (design/lexdb.md)
and TDS 7.4 with T-SQL (design/lexdb-tds.md). This adds a third: a listener,
by default on Oracle's port 1521, that speaks TNS with TTC on top (the
protocol of "thin" drivers: python-oracledb thin, JDBC thin, node-oracledb
6+, ODP.NET managed, Lexell's own `oracle` client), and on that connection
an Oracle SQL and PL/SQL subset. All three doors share one store: a table
made over TNS is there for psql and sqlcmd.

Goal, as for TDS: a defined, growing subset, each piece checked against a
real Oracle, not "any Oracle program". Thick (OCI) clients, Net Native
Encryption (NNE), Kerberos/RADIUS, RAC/Data Guard services, objects and
collections, XMLTYPE, AQ and DBMS_* packages beyond a handful are out.

Oracle is harder than SQL Server in two ways. The authentication needs a
password-derived verifier that lexdb does not keep (section 5). And Oracle
SQL has semantics, not just syntax, that differ from PostgreSQL's: the empty
string is NULL, DATE has a time, `||` of NULL is not NULL, and so on
(section 7).

## 2. The oracle (the test oracle)

`tools/oracle_container.sh create` runs Oracle Database Free
(`gvenzl/oracle-free:slim`, rootless podman, container `lxl-oracle`, ports
1521 and 2484 on 127.0.0.1, PDB FREEPDB1, test user APP) and writes
`~/.obo-oracle-dsn`; `tls` adds a TCPS listener (it already exists for the
client's tests, design/oracle.md "Testing"). Port 1521 is taken by that
container on this machine, so lexdb's test listener uses another port
(for example 15210) or the container is stopped; the same care as
mssql_container.sh using 14330. Oracle 23ai is the oracle: its answers are
the ones copied, including 23ai-only features (BOOLEAN, `FROM`-less SELECT)
only when lexdb is meant to accept them (open decision R4).

Tests are made as `tests/lexdb/gen_mssql.py` makes them: a new
`tests/lexdb/gen_oracle.py` plus queries files `oracle_*_queries.txt`
(one batch per line, `#` comments), run on the container through
`lib/oracle.lxl` (`oracle`), recording per statement the column names and
TTC type codes, rows (names: v|v;v|v, NULL as NULL), row counts, and errors
by ORA- number; and a test (`tests/lexdb/tns_*.lxl`, as `tds_*.lxl`) that
runs the same file through lexdb's TNS endpoint in the same process
expecting those answers. Each suite runs in a new schema (user) on the
oracle; Oracle has no `CREATE DATABASE` inside a PDB, so the unit of
isolation is a user, which is also what lexdb maps to (section 8).

Other clients, each sending its own start-up queries: python-oracledb thin
(a pip install in a throwaway venv or container; the primary acceptance
client for O1), SQLcl (Java, JDBC thin; in the `full` image), SQL Developer
and JDBC (for the catalog queries, O4), and sqlplus in the container
(`podman exec lxl-oracle sqlplus`) which is **thick** (OCI) and so is not a
client of this endpoint; it is only the generator's cross-check.

## 3. Architecture

```
  1521 ── lexdb_tns.lxl ── Oracle front end ──┐
  1433 ── lexdb_tds.lxl ── T-SQL front end ───┤
                                              ├── lexdb_exec Session ── store
  5433 ── lexdb_wire.lxl ── lexdb_sql ────────┘
```

- **`cmd/lexdb_tns.lxl`** (new): the server side of TNS/TTC, shaped like
  `cmd/lexdb_tds.lxl` (a `Conn` per connection, an `Out` buffer with token
  writers, `serve(ConnArg)`, `acceptAll(ListenArg)`).
- **`cmd/lexdb_ora*.lxl`** (new): the Oracle front end: `lexdb_orasql.lxl`
  (dialect lexing/rewriting, section 7), `lexdb_orafn.lxl` (functions),
  `lexdb_oracat.lxl` (catalog views), later `lexdb_plsql.lxl` (PL/SQL).
  As for T-SQL (decision L1 there): a dialect flag on `lexdb_sql`'s lexer
  and parser (`:name` binds, `"quoted"` upper-fold, `||`, `(+)` refused,
  `FROM dual`-less rules, `FETCH FIRST`) so an Oracle statement and its
  PostgreSQL twin give the same `Stmt`; Oracle-only statements in the new
  files.
- **Listening:** `--tns ADDR` (repeatable), next to `--tds ADDR` in
  `cmd/lexdb.lxl`: parse in the argument loop (beside the `--tds` branch
  near line 101), thread a `tnsAddrs` list through `supervise`/`runMaster`,
  `lexdb_wire.listenAll`, and start `lexdb_tns.acceptAll` as a task next to
  the TDS one (about line 335). Also the usage text. Replicas do not listen.
- **Sessions, users, privileges, TLS:** shared with the other doors
  (`--auth`, `--tls-cert`). TCPS is the TNS listener with TLS first, as
  `tns` already does on the client side with `tcps`; no in-protocol
  upgrade, so it is simpler than TDS's PRELOGIN TLS.
- **Service names:** the CONNECT descriptor's `SERVICE_NAME` (or `SID`) is
  matched against the database names lexdb has; an unknown one is answered
  with REFUSE `(ERR=12514)`, which `tns.refuseError` already parses on the
  client side. `FREEPDB1`-style default: the single service `lexdb` plus any
  database name.

### 3.1 Reuse from `lib/tns.lxl` and `lib/crypto.lxl`

`tns` is a client; its codecs are mostly symmetric and are to be used
as they are (export what is private as needed, they are `fn`, not `pub`).

| reuse | where |
|---|---|
| packet header writer, `packet()`, constants (types, flags, function codes, TTC message numbers, ORA type codes) | `tns.packet`, `putHeader`, `FN_*`, `T_*` |
| TTC primitives: `putUb`, `putBytes`, `putSb4`, the reader `Cur` (`ub2/ub4/ub8`, `bytes`, `take`, `str2`) | `tns` |
| value codecs both ways: `encodeNumber`/`decodeNumber`, `encodeDate/Timestamp/TimestampTz`, `decodeStamp`, `encodeDouble/decodeDouble`, UTF-16BE, `rowidText` | `tns` |
| `Column`/`Cell`/`Bind` records, `columnWidth`, `typeNameOf` | `tns` |
| compile/runtime capability tables (`compileCaps`, `runtimeCaps`): the server's own version of them | `tns` (starting point) |
| AES-CBC, PBKDF2-SHA512/SHA256, SHA-1/512, MD5, HMAC, random | `lib/crypto.lxl` |
| the verifier arithmetic, **run backwards**: `tns.verifier` computes the client side; the server side needs the same formulas in the other direction | `tns` (reference) |
| the Execute body reader's mirror: `executeBody` writes; the server needs `parseExecute` | `tns.executeBody` (reference) |

Recommendation: move the shared packet/primitive/value-codec part of
`lib/tns.lxl` out of the client-only half, only if a parallel agent run
would not collide with `tns` edits (decision R6); otherwise `lexdb_tns`
imports `tns` and the missing `pub`s are added in a small first commit.

### 3.2 What is new (server only)

1. **Listener side of the handshake**: read CONNECT (version, SDU/TDU, flags,
   the descriptor, including the follow-on DATA packet when the descriptor is
   over 230 bytes); write ACCEPT (version `min(319, client)`, SDU, flags with
   "NA required" off so no NNE is requested), or REFUSE `(ERR=12514)`.
   Switch the length field to 32 bits after ACCEPT when version >= 315.
2. **TTC Protocol (1) reply**: server banner ("Oracle Database 23ai Free
   ..." by default, setting-driven), char set 873, national set 2000, the FDO
   block, compile-time and run-time capability bytes. The field version the
   client takes is the lesser of the two, so the capability set decides which
   encodings the rest of the server must speak; advertise a **low, fixed
   field version** (the lowest python-oracledb and JDBC thin accept, 18 to
   start) so the server implements one encoding of each message.
3. **TTC DataTypes (2)**: read and discard the client's table, answer with
   the server's (a short, fixed one).
4. **Auth phase 1 (function 118)**: parse user and session data; answer
   key/value pairs: `AUTH_VFR_DATA` (the salt, flags field = verifier type
   0x939 for 12c), `AUTH_SESSKEY` (96 hex chars: part A, AES-CBC encrypted
   under the verifier hash), `AUTH_PBKDF2_CSK_SALT`, `AUTH_PBKDF2_VGEN_COUNT`,
   `AUTH_PBKDF2_SDER_COUNT`. An unknown user gets a **fake** salt derived
   from the user name and a server secret, so the failure comes at phase 2
   as ORA-01017, as Oracle does (no user enumeration).
5. **Auth phase 2 (function 115)**: decrypt the client's `AUTH_SESSKEY` and
   `AUTH_PASSWORD` (and `AUTH_PBKDF2_SPEEDY_KEY`), verify the password
   (section 5), answer `AUTH_SVR_RESPONSE` (which the client checks decrypts
   to contain `SERVER_TO_CLIENT`), plus session data (`AUTH_SESSION_ID`,
   `AUTH_SERIAL_NUM`, `AUTH_VERSION_NO`, `AUTH_DB_ID`...). Failure: ORA-01017.
6. **Request reader**: message type 3 (function) with sequence number and
   (field version >= 18) token: EXECUTE (94) incl. parse+execute+fetch flags,
   bind metadata and values (`parseExecute`), FETCH (5), COMMIT (14),
   ROLLBACK (15), LOGOFF (9), CLOSE_CURSORS piggyback (105, type 17),
   PING (147), SESSION_GET/SESSION_RELEASE (pool), LOB_OP (96) later,
   ALTER/SET piggybacks (the client sends `ALTER SESSION SET TIME_ZONE`
   as plain EXECUTE text).
7. **Reply writer**: DESCRIBE_INFO (8) from lexdb's `OutCol`s, ROW_HEADER
   (6) and ROW_DATA (7) per row (the BIT_VECTOR (21) duplicate-column
   optimisation is optional: never send it), ERROR (4) with the cursor id,
   row count, ORA- number and text (error 0 for "more rows", 1403 for "no
   more rows", the row count for DML), STATUS (9), END_OF_RESPONSE (29),
   MARKER packets for break/reset, PARAMETER/IO_VECTOR (11) for OUT binds
   later, WARNING (15) (`ORA-` warnings on connect, none to start).
8. **Server cursors**: a table of open cursors per connection (id, the
   lexdb result and position, the column list), FETCH reads the next
   `n` rows, CLOSE_CURSORS frees; cursor reuse by id for re-execution of
   the same text (python-oracledb's statement cache re-sends EXECUTE with
   the cursor id and no SQL).
9. **Breaks**: MARKER packet interrupt (Oracle's cancel) handled between
   statements and, once lexdb has query cancel, mid-statement.

## 4. Stages

| stage | contents | done when |
|---|---|---|
| O1 | the listener and `--tns`; CONNECT/ACCEPT/REFUSE; TTC Protocol and DataTypes; auth phases 1 and 2 with 12c verifier, against a verifier made at password-set time (R1) and `trust`; EXECUTE parse+execute+fetch of lexdb's own SQL plus `SELECT ... FROM dual`; DESCRIBE_INFO/ROW_DATA/ERROR(1403); FETCH for more rows; COMMIT/ROLLBACK/LOGOFF/CLOSE_CURSORS; errors with an ORA- number; no binds | python-oracledb thin and `lib/oracle.lxl` (`oracle`) connect with user/password, run `SELECT 1 FROM dual`, a multi-row query that needs a FETCH, an error, a commit and a close, against `lexdb DIR --tns 127.0.0.1:15210`, wrong password gives ORA-01017 |
| O2 | binds: `:1` and `:name`, parameter types (NUMBER, VARCHAR2, DATE, TIMESTAMP, RAW, BOOLEAN), NULL; `executemany` (array DML, `iters` > 1), `RETURNING ... INTO`; cursor reuse by id; the full type map of section 6 on the output side; TCPS | the `oracle` client's parameter, type and pool tests pass against lexdb; python-oracledb's `executemany`, a pooled connection and `fetchmany`; TCPS login |
| O3 | the Oracle surface of SQL (section 7): `dual`, `sysdate`/`systimestamp`, `rownum`, `FETCH FIRST`/`OFFSET`, sequences with `.nextval/.currval`, `NVL`/`NVL2`/`DECODE`, `\|\|`, `TO_CHAR/TO_DATE/TO_NUMBER`, `SUBSTR/INSTR`, `TRUNC`, `ADD_MONTHS`, `MONTHS_BETWEEN`, `LISTAGG`, `MINUS`, `(+)` joins refused, Oracle type names in DDL, empty-string-is-NULL, identifier fold-up; `CREATE TABLE ... GENERATED ... AS IDENTITY`; `MERGE` | gen_oracle suites `oracle_sql` and `oracle_dml` pass against the 23ai container |
| O4 | catalog: `NLS_*`/`V$VERSION`/`V$INSTANCE`/`V$SESSION`/`V$PARAMETER`, `ALL_/USER_/DBA_` TABLES, TAB_COLUMNS, INDEXES, IND_COLUMNS, CONSTRAINTS, CONS_COLUMNS, OBJECTS, SEQUENCES, VIEWS, USERS, SYNONYMS, `SYS_CONTEXT('USERENV', ...)`, `ALL_SOURCE` (empty); `DESCRIBE` data for SQLcl | python-oracledb connect with its post-login queries; SQLcl and SQL Developer (JDBC thin) connect, list schemas, tables, columns, indexes and open a table's data; `oracle_catalog` suite passes |
| O5 | NLS and session state: `ALTER SESSION SET NLS_DATE_FORMAT / NLS_TIMESTAMP_FORMAT / TIME_ZONE / CURRENT_SCHEMA`, `NLS_SESSION_PARAMETERS`, `TO_CHAR` formats following them; LOBs (CLOB/BLOB as LONG fetch, then LOB_OP locators); errors table complete; MARKER/break handling; `CREATE USER/GRANT` in Oracle syntax | `oracle_nls` and `oracle_errors` suites pass; python-oracledb `fetch_lobs=True` reads a CLOB; Ctrl-C in SQLcl cancels |
| O6 | PL/SQL: anonymous blocks (`BEGIN ... END;`, `DECLARE`, `:out` binds, `DBMS_OUTPUT.PUT_LINE` read back by `DBMS_OUTPUT.GET_LINES`), `CREATE PROCEDURE/FUNCTION`, `CALL`, `EXCEPTION WHEN ... THEN`, cursors loops, `%TYPE/%ROWTYPE`, REF CURSOR OUT, implicit results; triggers and packages are after O6 | `oracle`'s OUT bind, REF CURSOR and implicit-result tests (design/oracle.md O5) pass against lexdb; a stored procedure made by SQLcl is called from python-oracledb `callproc` |

Parallelism: **O1 first, alone** (it fixes the `Conn`/`Out` shape, the
cursor table and `--tns`). After O1: **O2 (protocol side: binds, types,
TLS) and O3 (SQL surface) can run in parallel**; they touch
`lexdb_tns.lxl` versus `lexdb_orasql/orafn`. **O4 is independent of O2/O3**
once O1 exists: only `lexdb_oracat.lxl` (views over lexdb's catalog, as
`lexdb_syscat.lxl` does for `sys.*`), so it can start alongside O2/O3 but
its done-when needs O2's binds for the JDBC clients. O5 needs O3 (`TO_CHAR`)
and O2 (LOB types out). **O6 needs O2 (OUT binds) and O3**, and is the
largest; split it as O6a (anonymous blocks, control flow, exceptions), O6b
(procedures, functions, CALL), O6c (cursors, REF CURSOR OUT, DBMS_OUTPUT).
Sub-slices of O3 and O4 (functions; DDL; MERGE; each catalog view group) are
independent and each can be a separate agent, in its own worktree.

## 5. Authentication and password verifiers

lexdb stores one verifier per role: SCRAM-SHA-256 text in
`Role.verifier` (`lexdb_auth.makeVerifier`, `parseVerifier`;
`cmd/lexdb_exec.lxl` `encRole`, set at `CREATE/ALTER ROLE ... PASSWORD`).
SCRAM keeps (salt, iterations, StoredKey, ServerKey), none of which lets
the server compute an Oracle exchange: both Oracle verifiers are functions
of the **clear password** that the client proves knowledge of by encrypting
with a key derived from them.

Oracle's two verifiers, in the notation of `tns.verifier`:

- **12c (0x939)**: `salt` = 16 random bytes (`AUTH_VFR_DATA`); `key =
  PBKDF2-HMAC-SHA512(password, salt + "AUTH_PBKDF2_SPEEDY_KEY", 64 bytes,
  VGEN_COUNT)`; `hash = SHA-512(key + salt)[0:32]` is what encrypts
  `AUTH_SESSKEY`. The server needs to store `(salt, VGEN_COUNT, hash)`
  or `(salt, VGEN_COUNT, key)`; `hash` suffices for the exchange and is
  not reversible to the password but is password-equivalent for this login
  (as Oracle's own `SPARE4` `T:` verifier is).
- **11g (0xb152)**: `hash = SHA-1(password + 10-byte salt)`, a weak
  unsalted-in-effect verifier. Not offered unless a client needs it (R2).

Exchange, server side: phase 1: pick `partA` (32 random bytes), send
`AES-CBC-encrypt(hash, partA)` as `AUTH_SESSKEY`, with the salt and counts.
Phase 2: decrypt client's `AUTH_SESSKEY` with `hash` to get `partB`; derive
the combined key (as `tns.verifier` does: PBKDF2 with `CSK_SALT` and
`SDER_COUNT` for 32-byte parts); decrypt `AUTH_PASSWORD` with it; **the
check is that the decrypted blob's password verifies**: either by deriving
`hash'` from it and comparing to the stored `hash`, or (simplest) because
the session key only worked if the client knew `hash`, accept when the
decrypted password re-derives to the stored `hash` (this also catches a
client that knew only the hash). Return `AUTH_SVR_RESPONSE` =
AES-CBC(combined key, random 16 bytes + "SERVER_TO_CLIENT" + padding),
which proves the server knew the verifier.

Storing it: at `CREATE/ALTER ROLE ... PASSWORD 'x'` and `CREATE USER ...
IDENTIFIED BY x`, the clear password is in hand, so lexdb makes the SCRAM
verifier and the Oracle 12c verifier together and stores both
(`encRole`'s third field gets a second verifier; old roles without it
cannot log in over TNS until the password is set again, ORA-01017). The
verifier in the stored form, like PostgreSQL's `SCRAM-SHA-256$...`, is
dumped and restored as given (as `lexdb_exec.lxl` line 31503 keeps a given
verifier). **This is decision R1.** Alternatives: derive at login from a
stored reversible password (no: insecure); or accept only `trust` for TNS
(O1 only, for demos).

Under `--auth trust` TNS accepts any password; the exchange still runs
(clients insist on it) and the server's `AUTH_SVR_RESPONSE` is built from the
password the client sent, with a fixed salt. Users that do not exist under
trust are refused as in PostgreSQL's door (same role table). `SYS`, `SYSDBA`
and `AS SYSDBA` (`AUTH_...MODE` 0x20) logins are refused (ORA-01031).
Kerberos/RADIUS/OS/external and token (OAuth, IAM) logins are refused.

## 6. Types out and in

Each result column's lexdb type becomes a DESCRIBE_INFO column (ORA type
code, size, precision, scale, nullable, charset form):

| lexdb | Oracle column type |
|---|---|
| int2/4/8, numeric(p,s), numeric | NUMBER(p,s) (int2/4/8: NUMBER(5/10/19,0); unconstrained numeric: NUMBER with precision 0, scale -127, as Oracle's own) |
| float4/8 | BINARY_FLOAT/BINARY_DOUBLE (`FLOAT`/`DOUBLE PRECISION` DDL names map back) |
| bool | NUMBER(1,0) before 23ai semantics; BOOLEAN (code 252) when R4 says 23ai and the client's field version is >= `FV_23_1` (`s.hasBoolean()`) |
| text, varchar(n), char(n) | VARCHAR2(n CHAR) (n bytes cap 4000 or 32767), CHAR(n); `text` as VARCHAR2(4000) when it fits, else CLOB at DDL |
| date (lexdb) | DATE (7 bytes, time 00:00:00) |
| timestamp | TIMESTAMP(6) (11 bytes); a column made as Oracle `DATE` is lexdb `timestamp(0)` (see below) |
| timestamptz | TIMESTAMP(6) WITH TIME ZONE (13 bytes, offset only; named regions become offsets) |
| bytea | RAW(n) up to 2000 (32767 extended), else BLOB |
| uuid | RAW(16) |
| json, arrays, other | VARCHAR2 text (CLOB when long); JSON as Oracle JSON type (code 119) is later |
| interval | INTERVAL DAY TO SECOND / YEAR TO MONTH where it fits, else text |

**Oracle DATE includes a time.** `CREATE TABLE t (d DATE)` must store a
second-precision timestamp, so the Oracle DDL maps `DATE` to lexdb
`timestamp(0)` (written to the catalog with a marker so that `ALL_TAB_COLUMNS`
says DATE and DESCRIBE sends type 12), whereas a PostgreSQL `date` column seen
from Oracle is also sent as DATE (no time loss: midnight). `sysdate` returns
this type; `date '2024-01-01'` is a midnight timestamp(0); `date + 1` adds a
day (Oracle's date arithmetic: DATE +/- number is days, DATE - DATE is a
NUMBER of days, which lexdb must special-case on `timestamp(0)`).
`TIMESTAMP` is `timestamp(6)` (Oracle's default); `TIMESTAMP WITH LOCAL TIME
ZONE` is `timestamptz` shown in the session zone.

Other mappings: `NUMBER` DDL: `NUMBER` is `numeric` with no limits,
`NUMBER(p)`/`NUMBER(p,s)` numeric(p,s); `NUMBER(p)` with p<=18 may be stored
as an integer type internally but is described as NUMBER; `INTEGER`/`INT`/
`SMALLINT` are NUMBER(38,0) in Oracle (a view of the same). `VARCHAR2(n
BYTE|CHAR)`, `NVARCHAR2`, `NCHAR` map to varchar/char; `LONG` to text;
`CLOB`/`NCLOB` to text, `BLOB`/`RAW(n)`/`LONG RAW` to bytea; `FLOAT(p)`
to float8; `ROWID`/`UROWID` to a text pseudo-column built from the row's
key (`tns.rowidText` reversed: `ROWID` is a deterministic function of the
row's physical id, used by clients to update the row they fetched).
Out of range: NUMBER exceeding 38 digits is rounded to 38 as Oracle does.

In (binds): bind metadata and value to a lexdb `Val`: NUMBER via
`tns.decodeNumber`, VARCHAR2/CHAR/NVARCHAR/LONG as text (empty string and
a zero-length bind are NULL: the same quirk), DATE/TIMESTAMP via
`decodeStamp`, RAW, BINARY_DOUBLE/FLOAT, BOOLEAN (23ai), cursor/OUT types
at O6. Binds are positional in the order the placeholders appear
(`tns.placeholders` finds them on the client; the server's rewriter finds
`:1`/`:name` in the same way, ignoring quoted text and comments, and
**reuses a name's bind** where the name repeats, as Oracle does for SQL but
not for PL/SQL, where binds are by position of appearance).

## 7. The Oracle dialect

As L1 for T-SQL: a dialect flag in `lexdb_sql`'s lexer/parser plus a rewrite
or analysis pass; semantics changes that cannot be a rewrite go in the
executor behind a per-session `dialect` setting (`Session.dialect = "oracle"`
set at TNS login, "tsql" at TDS login, "pg" otherwise). All of the
following is checked against the oracle suites, not assumed.

- **The empty string is NULL.** On the way in: an empty VARCHAR2 bind or the
  literal `''` becomes NULL (`''` in a comparison is NULL: `WHERE c = ''` is
  never true; `c IS NULL` is). On the way out: lexdb text columns that hold
  `''` (written over pg) are sent as NULL (the DESCRIBE says nullable).
  `LENGTH('')` is NULL; `'a' || NULL` is `'a'` (concat ignores NULL, unlike
  pg); `NVL(c, 'x')` fires for `''`. For NOT NULL columns, an insert of `''`
  fails with ORA-01400. Done in the executor under the dialect flag.
- **Identifiers fold to UPPER CASE** unless double-quoted (`create table t`
  is `T`; DESCRIBE and the catalog views say `T`; `"t"` stays lower). The
  tds design's L6 (identifier case) and `lexdb_sqlcoll` give the mechanism:
  names are stored folded as the dialect folds them; the PostgreSQL door
  folds to lower, so the same table is `t` for psql and `T` for Oracle.
  Open decision R3: store as given at creation time (Oracle-made names
  upper-case, so a psql user must quote them: this is what Babelfish does
  for its own names) versus a case-insensitive lookup. Recommendation: store
  as folded by the creating door, look names up in the current dialect's
  fold, and fall back to a case-insensitive unique match from the other.
- **`dual`**: a one-row, one-column (`DUMMY VARCHAR2(1)` = `'X'`) view in the
  Oracle schema search path; `SELECT expr FROM dual` is the same as
  `SELECT expr`. `SELECT 1` with no `FROM` is ORA-00923 in Oracle (R4: 23ai
  accepts it; recommendation: accept).
- **`sysdate`, `systimestamp`, `current_date`, `current_timestamp`,
  `localtimestamp`, `user`, `uid`, `sys_guid()`**, `rownum`, `rowid`, `level`
  (`CONNECT BY` is O6+; refused with ORA-00933 first).
- **`rownum`**: a pseudo-column numbering rows *after* WHERE and before
  ORDER BY: `WHERE rownum <= n` is a limit applied before sort (the classic
  trap). Implement `rownum <= n` / `rownum < n` / `rownum = 1` predicates in a
  top-level WHERE as a LIMIT without a sort, and general `rownum` as a
  numbering node in the planner's scan; `rownum > 1` yields no rows, which is
  Oracle's behaviour. Subquery-in-FROM `rownum` (the pre-12c pagination
  idiom) must work.
- **`FETCH FIRST n ROWS ONLY`, `OFFSET n ROWS`, `FETCH FIRST n PERCENT`,
  `WITH TIES`**: map to LIMIT/OFFSET (pg already has `FETCH FIRST`).
- **Sequences**: `seq.nextval`, `seq.currval` in expressions and in
  `INSERT ... VALUES`; mapped to `nextval('seq')`/`currval('seq')`, with
  Oracle's rule that `currval` before `nextval` in the session is ORA-08002;
  `CREATE SEQUENCE s START WITH 1 INCREMENT BY 1 NOCACHE NOCYCLE`;
  `GENERATED ALWAYS AS IDENTITY` over a sequence; 23ai `DEFAULT s.nextval`.
- **Binds**: `:1`, `:2` and `:name` are rewritten to the executor's `$n`;
  a bind inside a quoted string or comment is text.
- **Operators and functions**: `||` (NULL-ignoring as above), `NVL`, `NVL2`,
  `DECODE`, `COALESCE`, `NULLIF`, `TO_CHAR` (number and date formats),
  `TO_DATE`, `TO_NUMBER`, `TO_TIMESTAMP`, `SUBSTR` (position 0 is 1, negative
  from the end), `INSTR`, `LPAD/RPAD`, `TRIM`, `REPLACE`, `TRANSLATE`,
  `INITCAP`, `TRUNC` (number and date), `ROUND`, `MOD`, `CEIL/FLOOR`,
  `ADD_MONTHS`, `MONTHS_BETWEEN`, `LAST_DAY`, `NEXT_DAY`, `EXTRACT`,
  `LISTAGG ... WITHIN GROUP`, `REGEXP_*`, `GREATEST/LEAST`, `CASE`;
  set operators `MINUS` (for `EXCEPT`) and `UNION ALL`; `TRUNCATE TABLE`;
  `COMMENT ON`; `MERGE` (O3); `INSERT ALL` (late); `(+)` outer join syntax
  (refused ORA-... unless asked for: R5).
- **Transactions**: Oracle starts a transaction at the first DML and has no
  `BEGIN`; DDL commits implicitly (before and after); `COMMIT`/`ROLLBACK` as
  statements and as function messages; `SET TRANSACTION`, `SAVEPOINT`.
  DDL auto-commit is a real semantic (a program may rely on it); under the
  Oracle dialect `CREATE/DROP/ALTER/TRUNCATE` commits the open transaction
  first and after, even though lexdb's DDL is transactional for the other
  doors. Autocommit is a client setting (a flag on EXECUTE).
- **Data change reporting**: DML's row count in the ERROR message
  (`rowcount`), `RETURNING ... INTO :x`, `SQL%ROWCOUNT` (PL/SQL).
- **Session setup the drivers send**: `ALTER SESSION SET TIME_ZONE = ...`,
  `... NLS_DATE_FORMAT`, `... NLS_TIMESTAMP_FORMAT`, `... CURRENT_SCHEMA`,
  `... NLS_LANGUAGE/TERRITORY`, `... ISOLATION_LEVEL`: accepted and kept in
  the Session (O1 accepts and ignores, O5 honours).
- **NLS**: lexdb's defaults mirror Oracle's `AMERICAN_AMERICA.AL32UTF8`:
  `NLS_DATE_FORMAT = DD-MON-RR` (affects `TO_CHAR(date)` and implicit
  date/text conversion), `NLS_TIMESTAMP_FORMAT = DD-MON-RR HH.MI.SSXFF AM`,
  `NLS_NUMERIC_CHARACTERS = '.,'`, `NLS_SORT = BINARY`, `NLS_COMP =
  BINARY` (string comparison is binary: case-sensitive, trailing spaces
  significant, unlike SQL Server; no L2-style collation work). Honoured in
  `TO_CHAR/TO_DATE/TO_NUMBER` and the V$/NLS_* views at O5.
- **Errors**: lexdb's SQLSTATE becomes an ORA- number (the error text is
  `ORA-NNNNN: message`, in the ERROR message with the number in its field;
  the table is generated against the oracle, as for 208/2627 on TDS):

  | SQLSTATE | ORA- | text |
  |---|---|---|
  | 42P01 | 00942 | table or view does not exist |
  | 42703 | 00904 | invalid identifier |
  | 42601 | 00900 / 00933 / 00923 | invalid SQL statement / SQL command not properly ended / FROM keyword not found where expected |
  | 23505 | 00001 | unique constraint (SCHEMA.NAME) violated |
  | 23503 | 02291 / 02292 | integrity constraint violated: parent key not found / child record found |
  | 23502 | 01400 | cannot insert NULL into (...) |
  | 23514 | 02290 | check constraint violated |
  | 22001 | 12899 | value too large for column |
  | 22012 | 01476 | divisor is equal to zero |
  | 22003 | 01426 / 01438 | numeric overflow / value larger than specified precision |
  | 22P02 | 01722 / 01858 | invalid number / non-numeric character where numeric expected (dates) |
  | 42P07 | 00955 | name is already used by an existing object |
  | 28P01, 28000 | 01017 | invalid username/password; logon denied |
  | 42501 | 01031 / 00942 | insufficient privileges |
  | 40001, 40P01 | 08177 / 00060 | cannot serialize access / deadlock detected |
  | 57014 | 01013 | user requested cancel of current operation |
  | no row (`SELECT INTO`) | 01403 (as ORA error; the fetch end marker is the same number) | no data found |
  | other | 00600-like fallback 06512 / 20000 | `RAISE_APPLICATION_ERROR` uses 20000-20999 |

## 8. Schema, user, database mapping

Oracle's namespace is **user = schema**; one PDB (service) per connection. So
a TNS login as role `app` has `CURRENT_SCHEMA = APP`, and unqualified names
resolve there first. Mapping: an Oracle schema is a lexdb schema of the same
name in the connection's database; the service name chooses the database
(`FREEPDB1` and `lexdb` both mean the default). `CREATE USER app IDENTIFIED
BY x` is `CREATE ROLE ... LOGIN PASSWORD` plus `CREATE SCHEMA app
AUTHORIZATION app`; `ALTER SESSION SET CURRENT_SCHEMA = other` sets the
search path; `SELECT ... FROM other.tab` works with privileges. The
search path is `current_schema` then a `public`-like visibility
(Oracle's PUBLIC synonyms: `dual` and the catalog views live in a pseudo
schema `SYS` found everywhere). The `lexdb`'s existing PostgreSQL `public`
schema is visible from Oracle as the user `PUBLIC`'s objects only when asked
(R3). `GRANT SELECT ON t TO u`, `GRANT CONNECT, RESOURCE TO u` (`CONNECT`
-> LOGIN, `RESOURCE`/`DBA` -> create rights) are mapped in O5.

## 9. The catalog, as drivers use it (O4)

Queried at or soon after connect, to be served by `lexdb_oracat.lxl` as views
over lexdb's own catalog (the `lexdb_syscat.lxl`/`lexdb_sysdata.lxl` pattern
that serves `sys.*` to SQL Server clients):

- python-oracledb thin: nothing of its own beyond `ALTER SESSION`, and
  `SELECT ... FROM v$...` only on `connection.version` (no: it reads the
  version from the Protocol message and `AUTH_VERSION_NO`), `SYS_CONTEXT`
  on `connection.current_schema`, `select sys_context('userenv',
  'service_name') from dual`; `DUAL`; `cursor.description` from DESCRIBE.
- JDBC thin: `SELECT ... FROM v$instance`, `SELECT
  sys_context('USERENV','CURRENT_SCHEMA')`, `ALTER SESSION SET NLS_*`,
  DatabaseMetaData: `ALL_TABLES`, `ALL_TAB_COLUMNS`, `ALL_OBJECTS`,
  `ALL_CONSTRAINTS`/`ALL_CONS_COLUMNS` (keys), `ALL_INDEXES`/`ALL_IND_COLUMNS`,
  `ALL_SYNONYMS`, `ALL_TAB_COMMENTS`/`ALL_COL_COMMENTS`, `ALL_USERS`,
  `ALL_SEQUENCES`, `ALL_VIEWS`, `ALL_SOURCE`, `ALL_ARGUMENTS`
  (procedure params), `NLS_DATABASE_PARAMETERS`, `V$VERSION`.
- SQL Developer and SQLcl additionally: `V$SESSION`, `V$PARAMETER`,
  `V$SQL` (empty), `USER_*` and `DBA_*` twins, `ALL_DB_LINKS`, `ALL_EDITIONS`,
  `ALL_DIRECTORIES`, `ALL_MVIEWS`, `ALL_RECYCLEBIN`/`USER_RECYCLEBIN`,
  `DBMS_METADATA.GET_DDL` (a function: later), `ORA_DATABASE_NAME`, hints
  `/*+ ... */` (comments, ignored), `DBMS_SESSION`, `DBMS_APPLICATION_INFO`
  calls (accepted as no-ops).

Method as for the SQL Server catalog (design/lexdb-tds.md section 13):
capture the actual queries each client sends with a proxy (`tests/lexdb/
tds_proxy.py` is the TDS model: a TNS one decodes EXECUTE's SQL text), run
each against the oracle for its result shape, then implement the views
column-for-column. Views are generated from lexdb's catalog tables, not
stored. Unimplemented views fail with ORA-00942, so a client's missing query
shows up as a clean error to fix, not a hang.

## 10. PL/SQL (O6)

A block is a unit parsed whole (`lexdb_plsql.lxl`, run as `lexdb_tsql.lxl`
runs T-SQL batches, producing events the front end turns into replies):
`DECLARE` (variables with `%TYPE/%ROWTYPE`, constants, cursors), `BEGIN` ...
`EXCEPTION WHEN NO_DATA_FOUND | TOO_MANY_ROWS | OTHERS | named THEN` ...
`END;`, `IF/ELSIF/ELSE`, `CASE`, `LOOP/EXIT WHEN`, `WHILE`, `FOR i IN a..b`,
`FOR r IN (SELECT ...)`, `:=`, `SELECT ... INTO`, `INSERT/UPDATE/DELETE`
with `RETURNING INTO`, `EXECUTE IMMEDIATE`, `RAISE`/`RAISE_APPLICATION_ERROR`,
`SQLCODE/SQLERRM`, `SQL%ROWCOUNT/%FOUND`, `DBMS_OUTPUT.PUT_LINE`
(buffered; fetched by clients with `DBMS_OUTPUT.GET_LINES` or by SQLcl
with `SET SERVEROUTPUT ON`), `COMMIT`/`ROLLBACK` inside blocks. Binds in
blocks are by name and by position of appearance, and OUT/IN OUT binds are
sent back in an IO_VECTOR/PARAMETER message (the `oracle` client's `Out`).
Stored code goes in a catalog table (`USER_SOURCE`/`ALL_PROCEDURES`/
`ALL_ARGUMENTS`); a procedure compile error is a warning (ORA-24344,
"created with compilation errors") with `SHOW ERRORS` reading
`USER_ERRORS`. Packages, types, triggers, `PRAGMA AUTONOMOUS_TRANSACTION`,
bulk collect/FORALL, `UTL_*` are after O6. Where the T-SQL interpreter's
control-flow machinery (`lexdb_tsql.lxl`) fits, reuse its evaluator and
transaction handling; the grammar and the exception model are different.

## 11. Risks and known hard parts

- **Capabilities negotiation** is the largest source of "works with one
  driver, not another": each driver reads the Protocol reply's compile-time
  capability vector and picks encodings. Pin the server's field version low
  and test python-oracledb, JDBC thin and ODP.NET each at O1/O2; a TNS
  capture proxy is the first tool to build (R6).
- **DESCRIBE_INFO and ROW_DATA layouts vary with field version**; implement
  only the pinned one, and refuse (ACCEPT with a low version) higher.
- **Large replies**: SDU and packet chunking, DATA flags, and the
  "more data" continuation; a row may span packets, the client handles it.
- **Statement caching and cursor ids**: re-execution with a cursor id and
  empty SQL text must find the parsed statement; invalid ids give
  ORA-01001.
- **Per-session semantics** (empty string, DATE) are dialect-gated; a column
  made through Oracle may confuse psql users (a `''` that reads back NULL)
  unless data written through the Oracle door is normalized at write.
- **23ai vs 19c**: clients send different field versions. We pick one
  behaviour set and say so in the banner.

## 12. Open decisions (the user's), with recommendations

- **R1. Password verifier storage.** Oracle auth needs an Oracle 12c
  verifier (salt, iteration count, derived hash), not derivable from a SCRAM
  verifier. Recommendation: at every password set (`CREATE/ALTER ROLE`,
  `CREATE USER`) store the 12c verifier next to the SCRAM one in `encRole`'s
  record; roles that predate it log in over TNS only after a password reset
  (and under `trust`). Never store the clear password. The 11g verifier and
  10g not stored.
- **R2. 11g verifier and old drivers.** Recommendation: 12c only; clients
  too old for it (pre-12.1) are not a target.
- **R3. Identifier case across doors.** Oracle folds up, lexdb folds down.
  Recommendation: fold by the creating door, resolve by the current door's
  fold with a unique case-insensitive fallback, and report so in
  `ALL_TABLES` (as made); revisit with the L6 machinery from the TDS work.
- **R4. Which Oracle version is mimicked.** Recommendation: 23ai Free (the
  container's), banner and `V$VERSION` say so; accept 23ai conveniences
  (`SELECT 1`, BOOLEAN, `IF NOT EXISTS`, `FROM`-less) since they cost nothing
  and harm nobody; do not claim 19c compatibility.
- **R5. Oracle-only legacy syntax** (`(+)` outer joins, `CONNECT BY`,
  `ROWNUM` general numbering, `MODEL`, `PIVOT`). Recommendation: `ROWNUM` yes
  (O3), `PIVOT`/`CONNECT BY` after O6 by demand, `(+)` and `MODEL` never
  unless a target program needs them (rewrite `(+)` to LEFT JOIN if so).
- **R6. Shared codec module.** Recommendation: do not restructure
  `lib/tns.lxl` for O1; add `pub` to what the server needs and import it.
  Revisit if two agents conflict. Build a TNS capture proxy (like
  `tds_proxy.py`) in O1 as the debugging tool.
- **R7. Port and listener flags.** Recommendation: `--tns ADDR`, no default
  1521 bind (the user's Oracle container may be there); tests use 15210.
- **R8. DDL auto-commit.** Recommendation: honour it under the Oracle
  dialect (a program may rely on it); the PostgreSQL and TDS doors keep
  transactional DDL.
- **R9. DATE.** Recommendation: Oracle `DATE` columns are `timestamp(0)` with
  a catalog marker; lexdb `date` columns present as DATE too.
- **R10. Who may log in as SYS/SYSTEM.** Recommendation: nobody over TNS
  (ORA-01017/01031); the role named `system` is only a role if the user
  creates one.

## 13. As built: O1 (2026-11-13)

`lexdb DIR --tns HOST:PORT` (repeatable, TCP only, no default; replicas do not
serve it) starts `cmd/lexdb_tns.lxl` (`acceptAll`, `acceptLoop`, `serve`, as
`lexdb_tds`). Checked with `tests/lexdb/run/tns_client.lxl` (lib/oracle against
the listener in the same process: login under trust and scram, `SELECT ...
FROM dual`, every type, a 1000-row result by FETCH at the client's default and
at Fetch Size 7, 5000-byte rows, errors by ORA- number, transactions, DDL
commit, ALTER SESSION, service names, wrong password, SYS) and by hand with
python-oracledb 26.1 thin (connect, `SELECT 1 FROM dual`, `fetchmany`,
`fetchall`, DML row counts, commit, rollback, autocommit, duplicate key and
unknown table errors, ORA-01017, a second connection). The whole lexdb suite
passed (135 tests). Not run: JDBC, SQLcl, ODP.NET.

Built as specified: CONNECT/ACCEPT/REFUSE (the long descriptor in a second
DATA packet; 32-bit lengths from TNS 315), Protocol, DataTypes, the two
authentication phases (R1: the role's 12c verifier, `Role.oraVerifier`, the
fourth tab field of `encRole`, text `ORA12C$salt$count$hash` in hex, made with
the SCRAM verifier at every `CREATE/ALTER ROLE ... PASSWORD`; a SCRAM verifier
given instead clears it, an `ORA12C$...` one given is kept; an unknown user or
one without a verifier gets a salt made from its name and a per-listener
secret, so the failure is ORA-01017 at phase two; SYS and AS SYSDBA/SYSOPER
are refused), EXECUTE (parse, execute, first rows), FETCH, COMMIT, ROLLBACK,
LOGOFF, PING, the CLOSE_CURSORS piggyback, DESCRIBE_INFO, ROW_DATA, ERROR
(0 more rows, 1403 no more, the row count for DML), STATUS; field version 18
fixed, 32K strings off, no END_OF_RESPONSE and no fast authentication
advertised (the replies end at ERROR or STATUS); BOOLEAN for bool (NUMBER(1)
below field version 17); R2 to R10 as recommended where they apply. Shared
codecs: `lib/tns.lxl` only got `pub` on what the server reads with (`Cur`'s
readers, `compileCaps`, `runtimeCaps`), per R6; nothing moved.

Deviations and additions:

- **`--auth trust` does not take any password.** Oracle's exchange proves the
  password through keys derived from it, and the server must answer
  AUTH_SVR_RESPONSE under the client's key, so it must know the password.
  Under trust a user with no stored verifier (no such role, or a role made
  before this stage) logs in with its own name as the password (the
  verifier is made from it at phase one); roles with a verifier are checked
  against it in every mode. Section 5's "any password under trust" cannot be
  done with a standard client. Roles that predate the verifier need their
  password set again for TNS under scram-sha-256.
- **AUTH_SESSKEY is 64 hex characters** (a 32-byte part A, no padding), not
  96: the clients take 96 as the 11g layout. The verifier type in the flags
  of AUTH_VFR_DATA is 0x4815 (what the clients check), not 0x939.
- **DataTypes**: the client's table is answered with itself, not a fixed
  short one. ROW_HEADER is sent once before the rows of a reply, not before
  each row.
- **REEXECUTE (4) and REEXECUTE_AND_FETCH (78) are done**, pulled forward from
  O2: python-oracledb's statement cache sends them for any statement run a
  second time, so without them its second `execute` fails. A cursor stays in
  the table after a failed statement (the client re-runs it by id); it is
  freed by CLOSE_CURSORS or the end of the connection.
- Cursors hold their whole result (`Session.run` materializes), FETCH slices
  it; a query that returns millions of rows takes the memory for them.
- **Binds are refused** with ORA-01008. `FROM dual` is dropped from the text
  (outside quotes and comments), not a `dual` table; `ALTER SESSION` is
  accepted and ignored; PL/SQL blocks are refused (ORA-03001).
- Column names are lexdb's (lower case, `?column?` for `SELECT 1`), not
  Oracle's upper-cased expression text: with the O3 identifier work.
  Empty-string-is-NULL and the DATE-has-a-time mapping are not done either
  (O3); `date` columns come out as DATE and `timestamp` as TIMESTAMP.
- Oracle's transactions on lexdb's: the first DML does `BEGIN` (when none is
  open; a failure rolls it back), inside an open one each DML is under a
  savepoint so a failed statement is undone alone; the EXECUTE commit flag
  commits; DDL commits the open transaction first (R8). The call status's
  "transaction in progress" bit follows `Session.status()`.
- An ORA- number for each SQLSTATE of the section 7 table that lexdb raises;
  the others are ORA-20000 with lexdb's message (0A000 is ORA-03001), and
  an unsupported function code is ORA-03115.
- Services accepted: `lexdb`, `freepdb1` (any case) and none; any other is
  REFUSE (ERR=12514). `--require-tls` makes every TNS login fail (no TCPS yet).
- MARKER and CONTROL packets are ignored (no break handling); the TNS
  capture proxy of R6 is not built; no TCPS (O2).

## 14. As built: O3 (2026-11-13)

The Oracle SQL surface, as a mode of `lexdb_sql` (`P.ora`, `oraParse`; the lexer's
`lexOra`) plus `cmd/lexdb_orafn.lxl` (functions named `#ora_*`, reached through
`lexdb_tsqlfn.isTsqlFn`/`call`, result types through `lexdb_exec.exprOid` ->
`lexdb_orafn.resultOid`). The TNS door reads statements with `lexdb_sql.oraParse`
(one line in `lexdb_tns.lxl`, plus ORAnnnnn states mapped to their number in
`oraOf`). **No Oracle server was available** (no image, no container): every
expected answer in `tests/lexdb/run/tns_oracle.lxl` is written from Oracle's
documentation and memory, marked UNVERIFIED, and there is no `gen_oracle.py` yet.

Done: names folded up (the spelling, as L6: labels and `*` show `ID`; a quoted
name keeps its case, but is matched without regard to case); expression columns
named by their text, upper case, blanks dropped; `''` is NULL (literals, `||`,
SUBSTR, REPLACE, LENGTH, comparisons); DUAL (a one-row VALUES, so `select * from
dual` works); SYSDATE, SYSTIMESTAMP, CURRENT_DATE, USER, UID, SYS_GUID; ROWNUM
(WHERE tests of it become a limit before any sort, with ORDER BY on one table in a
subquery; elsewhere a row_number() window, so the pre-12c pagination idiom
works); FETCH FIRST/OFFSET (an existing feature; `FETCH` after a table is no
alias); `seq.NEXTVAL/CURRVAL`; NVL, NVL2, DECODE (null-safe), COALESCE, `||`
(NULL-ignoring, at + and - level), NUMBER division (38 digits), `+`/`-` on dates
(days, date - date), TO_CHAR/TO_DATE/TO_TIMESTAMP/TO_NUMBER with Oracle's format
models, SUBSTR, INSTR, REPLACE, TRUNC (number, date), ADD_MONTHS,
MONTHS_BETWEEN, LAST_DAY, NEXT_DAY, LISTAGG ... WITHIN GROUP, REGEXP_SUBSTR/
REPLACE, BITAND, MINUS; Oracle's type names (VARCHAR2, NUMBER(p,s), DATE as
timestamp(0), TIMESTAMP [WITH [LOCAL] TIME ZONE], CLOB, BLOB, RAW, INTEGER as
bigint, BINARY_FLOAT/DOUBLE, ...); GENERATED ... AS IDENTITY [ON NULL]; sequence
options NOCACHE/NOCYCLE/...; `DELETE t WHERE`, `ALTER TABLE ADD (...)`, MODIFY,
DROP (...), `DROP TABLE ... PURGE | CASCADE CONSTRAINTS`, COMMENT ON (ignored);
views made in Oracle mode keep their text tagged (`ORA_VIEW`); `(+)` refused
(ORA-03001).

**MERGE is built** (2026-11-14) as one feature for PostgreSQL, SQL Server and Oracle
(design/lexdb.md 9.121): this door's front end is `P.merge` with `p.ora` (ON in
parentheses, UPDATE ... WHERE ... DELETE WHERE, INSERT ... WHERE, the clauses in either
order, ORA-30926, ORA-38104, ORA-38101, ORA-02000 and its kin), checked against Oracle
Database Free 23ai by `tns_merge` (gen_oracle.py merge).

Deviations / left: DATE is timestamp(0) and comes out as TIMESTAMP (not DATE),
and casting to it rounds; no `CONNECT BY` (ORA-00900), `INSERT ALL`, `FETCH ...
PERCENT`; DECODE/NVL typing is lexdb's; `''` read from a text column written
over pg is not sent as NULL; Oracle's NUMBER with negative scale refused;
identity BY DEFAULT ON NULL does not turn a NULL into a generated value
(ORA-01400); ROWNUM with ORDER BY over joins or GROUP BY is limited after the
sort; currval-before-nextval is not ORA-08002; DDL errors the table of section 7
lists as 01438 (precision) and 32795 (identity value given) come out as 01426 and
20000 (the first needs `22003` + "field overflow" -> 1438 in `oraOf`; a SELECT
error inside an open transaction aborts it, as O1 only undoes DML alone).
Tests: `tns_oracle` (new) passes; the rest of the suite passes but `tns_client`,
which does not compile against O2's in-progress `AcceptArg`.

## 15. As built: O2 (2026-11-13)

Checked with `tests/lexdb/run/tns_binds.lxl` (lib/oracle against the listener in
the same process), `tns_client.lxl`, and `tests/lexdb/oracledb_o2.py` (python-oracledb
26.1 thin against a built lexdb: positional and named binds, every bind type, NULL,
a 7000-character text, `executemany` of 2000 rows, `arraydmlrowcounts`,
`batcherrors`, RETURNING INTO of one and many rows, a statement run again,
`fetchmany`, a pool, an error inside a transaction, TCPS).

- **Binds.** The request's bind descriptions and values are read in the parser
  (`readMeta`, `readValues`: non-LONG values first, a BOOLEAN NULL is the escape
  byte and 1); a re-execute carries values only, typed by the cursor's last
  description, so a cursor keeps its `meta`, its placeholder sites
  (`tns.bindSites`, new in lib/tns.lxl, `placeholders` is built on it) and its
  parsed statement. The text is rewritten once per cursor: the nth placeholder
  that is not RETURNING INTO's becomes `$n` (one value per occurrence, as
  python-oracledb and `lib/oracle` send them), `INTO :a, :b` is cut, `FROM dual`
  dropped; the values reach `Session.runCached` as `params`/`ptypes` as TDS's
  sp_executesql ones do. NUMBER is an int when it fits one (oid int8) else a
  numeric, text has no type (0) so lexdb coerces it as it does PG's unknown;
  DATE/TIMESTAMP are timestamps, TIMESTAMP WITH TIME ZONE a timestamptz, RAW
  bytea, BOOLEAN, BINARY_FLOAT/DOUBLE, INTERVAL DS/YM intervals. Fewer values
  than placeholders is ORA-01008. The cursor's plan cache is dropped when the
  types of the values change.
- **Array DML.** `iters` runs, each under its own savepoint (the transaction is
  begun first when none is open). Without batch errors the run that fails ends
  the call with its error and the rows of the runs before it stay (Oracle's,
  not an all-or-nothing statement); with `batcherrors` it is recorded (offset,
  ORA- number, text; ORA-24381 ends the call as python-oracledb expects) and the
  next run goes on. `arraydmlrowcounts` is a PARAMETER message of each run's
  count. A query that fails in an open transaction is under a savepoint too, so
  it does not abort the transaction as PostgreSQL's would.
- **RETURNING INTO** (DML kinds only): lexdb's RETURNING runs, and each run's
  rows are sent as a ROW_DATA of, per bind, its row count and each value in the
  bind's declared type (each followed by the sb4 python reads), then the ERROR
  message's row count. Types: NUMBER, text (also NCHAR), RAW, DATE/TIMESTAMP/
  TIMESTAMP TZ, BINARY_*, BOOLEAN, intervals.
- **Cursor reuse**: REEXECUTE, REEXECUTE_AND_FETCH and a full EXECUTE with a
  cursor id use the cursor's parsed statement; DESCRIBE_INFO is sent again when
  the columns differ from the last run's (python-oracledb re-uses its
  statement for a different set of bind types).
- **Types out**: INTERVAL DAY TO SECOND (11 bytes), or YEAR TO MONTH when only
  months are set; `lib/tns` reads both (as `+000000001 02:03:04.500000000`).
  The rest of section 6 was already O1's; numeric(p,s) precision, varchar(n)
  and a DATE-typed `timestamp(0)` need the column's declared type, which the
  executor's `OutCol` does not carry (O3/O4).
- **TCPS**: `--tcps HOST:PORT` (repeatable; stored in lexdb.lxl's address list
  as `tcps:HOST:PORT`) with the certificate and key of `--tls-cert`/`--tls-key`
  (any TLS version): TLS first, TNS inside it. `--require-tls` now refuses only
  the plain TNS logins. New entry points `lexdb_tns.acceptAllTls`; `acceptLoop`
  and `acceptAll` are unchanged.
- **Not done**: PL/SQL OUT binds, array binds, LOB binds (O5/O6); a bind of a
  named time zone region; the `executemany` of a RETURNING statement is one
  ROW_DATA per run but is untested with python-oracledb.

## 16. As built: O4 (2026-11-13)

Oracle's catalog views for the Oracle door, built as `lexdb_syscat` does SQL Server's.
**A real Oracle was available**: tools/oracle_container.sh's image
(`gvenzl/oracle-free:slim`, Oracle AI Database 26ai Free, 23.26.3) ran rootless under
podman, so every shape and the test answers are Oracle's, not written from memory.

- **Data** (`cmd/lexdb_oradata.lxl`, GENERATED by `tools/gen_oracle_catalog.py`, run as
  `python3 tools/gen_oracle_catalog.py --system-dsn system/PW@host:port/FREEPDB1 --app-dsn app/PW@...`):
  228 views with exactly Oracle's columns (name, type, length, precision, scale, nullability, in
  SYS's order), the rows lexdb takes as they are (`V$VERSION`, `V$OPTION`, `V$NLS_PARAMETERS`,
  `NLS_DATABASE/INSTANCE/SESSION_PARAMETERS`, `PRODUCT_COMPONENT_VERSION`, `DATABASE_PROPERTIES`
  without the passwords, `*_TABLESPACES`, `ALL/DBA_EDITIONS`, `SESSION_PRIVS/ROLES`,
  `USER_ROLE_PRIVS`, 120 `V$PARAMETER` rows, SYS/SYSTEM and others in `ALL_USERS`/`DBA_USERS`,
  `DICTIONARY` for the served views), a template row of each kind of object (the demo
  schema's rows of `ALL_TABLES`, `ALL_TAB_COLUMNS` of each data type, `ALL_INDEXES`,
  `ALL_CONSTRAINTS` of each type, `ALL_OBJECTS` of each type, ...) and the PUBLIC synonyms.
  Version strings are made 23ai (banner `Oracle Database 23ai Free Release 23.0.0.0.0`, full
  version 23.4.0.24.05) to match the Protocol message of O1.
- **Names** (`cmd/lexdb_oracat.lxl`): in FROM, in Oracle mode, `ALL_TABLES`, `SYS.ALL_TABLES`,
  `PUBLIC.x`, `V$VERSION` (`V_$VERSION`) and a PUBLIC synonym (`TABS`, `COLS`, `DICT`, `DICTIONARY`,
  `USER_CATALOG`...) become the function `#ora.NAME` (`lexdb_sql`, one line next to the T-SQL one);
  rows are made when the statement runs (`lexdb_exec.oraRows`, at the end of the file). Not
  made synonyms: `TAB SYN SEQ IND OBJ CLU CAT COL` (too likely a table of the user's; a user
  table does not otherwise shadow a view of these names as it does in Oracle).
- **Served from lexdb's catalog** (ALL_, USER_ and DBA_ of each): TABLES, TAB_COLUMNS,
  TAB_COLS, INDEXES, IND_COLUMNS, CONSTRAINTS (P, U, R, C; no NOT NULL ones), CONS_COLUMNS,
  OBJECTS (tables, indexes, views, sequences), SEQUENCES, VIEWS, TAB_COMMENTS, COL_COMMENTS,
  TAB_IDENTITY_COLS, CATALOG; `ALL_USERS`, `DBA_USERS`, `USER_USERS`; `V$SESSION` (the
  session's row), `V$INSTANCE`, `V$DATABASE` (template rows with lexdb's values). Served empty
  with Oracle's shape: SYNONYMS, SOURCE, TRIGGERS, PROCEDURES, ARGUMENTS, DB_LINKS, MVIEWS,
  TYPES, LOBS, IND_EXPRESSIONS, TAB_PRIVS, RECYCLEBIN, ERRORS, DEPENDENCIES, DIRECTORIES,
  and some 40 more, `V$SQL`, `V$MYSTAT`, `V$OPEN_CURSOR`, ... Everything else is ORA-00942.
  ALL_x and DBA_x list every schema (lexdb has no visibility test), USER_x the session user's.
- **Owner and names**: a schema's objects are owned by its upper-cased name; `public`'s by the
  session user (O1 puts a TNS user's tables in public). A name lexdb has folded to lower case is
  shown in upper case; a table or column with a spelling (L6) as written; constraints and
  indexes by their lexdb names (`EMP_PKEY`, not `SYS_C008754`). Creation times are 2000-01-01.
- **Types back**: VARCHAR2(n), CHAR(n), NUMBER(p,s), NUMBER (INTEGER is NUMBER, precision NULL,
  scale 0, as Oracle shows it), DATE (a `timestamp(0)`), TIMESTAMP(n), TIMESTAMP WITH TIME ZONE,
  BINARY_FLOAT/DOUBLE, BOOLEAN, CLOB (text without a length), BLOB (bytea), RAW(16) (uuid),
  INTERVAL DAY TO SECOND; `RAW(n)` is shown BLOB and NUMBER(p,0) of a pg `int4` NUMBER(10).
- **`SYS_CONTEXT('USERENV', x)`** (a parse-time rewrite, `lexdb_sql.oraSysContext`):
  SESSION_USER, CURRENT_USER, CURRENT_SCHEMA (all the upper-cased user: O5's CURRENT_SCHEMA
  should change that one), SID/SESSIONID (the same number as V$SESSION.SID), DB_NAME,
  CON_NAME/SERVICE_NAME (FREEPDB1), INSTANCE, HOST, IP_ADDRESS, ISDBA (FALSE), LANGUAGE, the
  NLS_* defaults (fixed: O5's session state should replace them, and the rows of
  `NLS_SESSION_PARAMETERS`, which are Oracle's defaults), CURRENT_EDITION_NAME; another
  parameter or namespace is NULL (Oracle: ORA-02003); `ORA_DATABASE_NAME()` is LEXDB.
- **The old outer join `a.x = b.y (+)`** is now done (it was refused in O3; JDBC's
  DatabaseMetaData queries for tables, columns and keys use it): in a SELECT's WHERE each
  AND-ed condition marked on the columns of one comma-listed FROM item (after the items it
  names) moves, unmarked, into that item's ON, which becomes a LEFT JOIN
  (`lexdb_sql.oraOuterJoins`). Other uses (OR, a marked item first, in a list or subquery's
  select list, two items marked in one condition) are refused as before (ORA-03001). Oracle
  ignores a `(+)` in a condition with no other table; lexdb refuses it.
- **Tests.** `tests/lexdb/gen_oracle.py` (new; `python3 tests/lexdb/gen_oracle.py --dsn
  app/PW@127.0.0.1:1521/FREEPDB1`, the account APP with SELECT on SYS.V_$INSTANCE, V_$DATABASE,
  V_$SESSION, V_$PARAMETER, V_$NLS_PARAMETERS and DBA_TABLES) runs the lines of
  `oracle_catalog_queries.txt` on Oracle and writes `run/tns_catalog.lxl` with Oracle's answers
  as its expect lines (105 of them; the test passes, lexdb giving the same). The
  JDBC DatabaseMetaData queries are those written from memory without the bind variables; the
  ones with `(+)` are in it. `tests/lexdb/oracledb_o4.py` runs a built lexdb with python-oracledb
  thin (connect, `connection.version`, `SYS_CONTEXT`, a hint, SQL Developer's and DBeaver's
  queries with binds, `cursor.description`, ORA-00942): all ok. Not run: JDBC thin, SQLcl, SQL
  Developer, DBeaver, ODP.NET (no Java here; the dotnet client was not fetched).
- **Left or different.** COMMENT ON is ignored (O3), so the comment views have NULL; NOT NULL is
  not a constraint row; an identity column's DATA_DEFAULT is NULL (Oracle: its sequence's
  NEXTVAL) and its `ISEQ$$` sequence is not listed; LOB columns have no `SYS_IL` index rows;
  a function-based or DESC index lists the expression/column, not `SYS_NC...`; LAST_NUMBER of a
  sequence is its START WITH; SEQUENCES.CACHE_SIZE is 0 for lexdb's no-cache; a `varchar2`'s
  CHAR_USED is always B; the statistics columns (NUM_ROWS, LAST_ANALYZED) are NULL; `V$` views
  of other sessions, `GV$`, `DBMS_METADATA.GET_DDL` and the no-op `DBMS_SESSION` calls are not
  done; `DESCRIBE` in SQLcl is untested. The suite: 136 of 138 pass; the two failures are
  `tns_client` and `tns_oracle` lines of O5's work in progress (NUMBER(p,s) values as 5000.50,
  DATE type), none of O4's.

## 17. As built: O5 (2026-11-13)

NLS and session state, LOBs, errors, breaks and users, in `cmd/lexdb_tns.lxl` and the new
`cmd/lexdb_oraadm.lxl` (the words of a statement, the territory and language tables, the ALTER SESSION
parameter lists), with small changes in `lexdb_sql` (`oraParseNls`, CLOB/BLOB marks), `lexdb_orafn` and
`lexdb_exec` (OutCol's declared type). Checked with `tests/lexdb/run/tns_nls.lxl` (lib/oracle) and
`tests/lexdb/oracledb_o5.py` (python-oracledb 26.1 thin against a built lexdb: NLS, time zone,
errors, DESCRIBE, `fetch_lobs` both ways, a temporary LOB bound, cancel, users and grants); the
whole lexdb suite passes (139 tests) and `oracledb_o2.py` still does. Still no Oracle server: every
expected answer is from documentation and memory (UNVERIFIED, as O3's).

- **ALTER SESSION** (`SP_ALTER_SESSION`, handled in `runCursor`): `SET name = value [name = value ...]`.
  `NLS_DATE_FORMAT`, `NLS_TIMESTAMP_FORMAT`, `NLS_TIMESTAMP_TZ_FORMAT` (format models checked: ORA-01821),
  `NLS_TERRITORY` and `NLS_LANGUAGE` (the lists in `lexdb_oraadm`; ORA-12700), `NLS_NUMERIC_CHARACTERS`,
  `NLS_SORT`, `NLS_COMP`, `NLS_LENGTH_SEMANTICS`, `NLS_CURRENCY`, ... are kept as set; `TIME_ZONE`
  (`LOCAL`, `DBTIMEZONE`, `'+hh:mm'`, a region; ORA-01882 for an unknown one) sets the session's zone;
  `CURRENT_SCHEMA` sets the search path to that schema then `public` (ORA-01435 for none; a user without a
  schema of its name may name itself); a list of session parameters drivers send (`ISOLATION_LEVEL`,
  `SQL_TRACE`, ...) is accepted without effect, `ENABLE/DISABLE/FORCE/CLOSE/ADVISE` too, any other
  ORA-02248. At login a user that has a schema of its name works in it. **The state is for O4 to read:**
  every set value is also a custom setting of the session, `current_setting('oracle.nls_date_format')`,
  `oracle.nls_territory`, `oracle.nls_language`, `oracle.nls_numeric_characters` (a territory fills it in),
  ..., `oracle.time_zone` (`LOCAL` when unset), `oracle.current_schema` (upper case, the user's own when
  none set), and from the end-to-end piggyback `oracle.client_identifier`, `oracle.module`,
  `oracle.action`, `oracle.client_info`, `oracle.dbop`. A ROLLBACK undoes custom settings, the zone
  and the path in lexdb, so they are put again before the next statement (`Nls.redo`). Not done: the
  month and day names of `NLS_DATE_LANGUAGE`/`NLS_LANGUAGE`, `NLS_NUMERIC_CHARACTERS` and
  `NLS_CURRENCY` in `TO_CHAR` of numbers, the session time zone in SYSDATE (it follows it: Oracle's
  does not), an `ALTER SESSION` inside PL/SQL.
- **Formats follow the session** through the parser: `oraParseNls(sql, [date, timestamp, tz])` is
  what a cursor is made with (every cursor is read again when an NLS format changes). `TO_CHAR(x)` with no
  format becomes `#ora_tochar1(x, date, timestamp, tz)`, `TO_DATE(x)` and `TO_TIMESTAMP(x)` gain the
  format. Implicit conversions (a date compared to a text, `||`) still use `DD-MON-RR`; lexdb has one
  type for DATE and TIMESTAMP, so a value with a fraction of a second is a timestamp
  (`TO_CHAR` with no format shows `DD-MON-RR HH.MI.SSXFF AM`), one without is a date. `X` (the radix)
  is a format element now.
- **Errors**: the table of section 7 is complete for what lexdb raises: 01438 (`numeric field overflow`
  of a column's precision), 32795 (`428C9`, GENERATED ALWAYS), and more states (22007 to 01861, 42804 to
  00932, 42803 to 00979, 42702 to 00918, 42701 to 00957, 42710/42704/3F000 to 01920/01917/01918, 2BP01
  to 02449, 55P03 to 00054, ...). A table the user cannot even read is ORA-00942, one it can read but not
  change ORA-01031 (`c.oraErr`). A role with a password but no LOGIN gets ORA-01045 after proving its
  password.
- **DESCRIBE**: the Oracle DATE type code (12) goes to a timestamp of scale 0 (a `DATE` column,
  `SYSDATE`, `TO_DATE`, `ADD_MONTHS`, `TRUNC`, ...; `exprScale` says 0 for them), values as 7-byte
  DATE; `TIMESTAMP(n)` carries its scale. `OutCol.scale` holds the declared type as a value below -2
  (`-2 - (tag | a << 8 | b << 24)`; `lexdb_exec.declTag/declA/declB`): `ORA_VARCHAR` (a the length; the
  describe size), `ORA_NUMBER` (precision a, scale b), `ORA_CLOB`, `ORA_BLOB` (a column made `CLOB`/`BLOB`
  has `TypeName.prec = 1` for a text/bytea type). TSQL hints (>= 34) and time scales (0 to 9) are
  untouched; nothing else reads a negative scale. A column made over a view or subquery loses it.
- **LOBs**: a CLOB/BLOB column is described as CLOB (112) / BLOB (113); the first EXECUTE answers with the
  description and no rows (python-oracledb then sends its define: `EXECUTE` with option 0x10 and the
  columns' types), the define answer repeats the description, and FETCH sends the rows as the client
  defined them: LONG (8) / LONG RAW (24) (the value, then the null indicator and return code) or a
  locator. A locator is 40 bytes naming a value held by the connection (`Conn.lobs`, the size in
  characters for a CLOB, 8132 as chunk size; dropped oldest first past 256 MiB); LOB_OP does GET_LENGTH,
  READ (offsets and amounts in characters for a CLOB), WRITE, TRIM, GET_CHUNK_SIZE, CREATE_TEMP, OPEN,
  CLOSE, IS_OPEN; FREE_TEMP (the piggyback too) is accepted and ignored. A CLOB/BLOB bind is its
  locator's value. Not done: BFILE, NCLOB's UTF-16 (an NCLOB is a CLOB), LOB prefetch, a LOB column
  of a re-executed statement when the client changes how it defines it.
- **Breaks**: a MARKER packet (the client's cancel, interrupt or break) is answered as the client
  expects: our BREAK marker, the client's RESET and ours, then ORA-01013 as the call's reply. lexdb has
  no cancel of a statement in flight (the connection's task is the one running it), so the break is read
  when the statement has ended: a long statement is not stopped by it (and its effects stay), an idle
  connection gets ORA-01013 as the reply of the break, as Oracle does.
- **Piggybacks**: SET_SCHEMA (python-oracledb's `connection.current_schema`) and END_TO_END attributes are
  read (kept as above); a piggybacked LOB_OP is skipped.
- **Users** (`SP_ADMIN`, in `c.admin`): `CREATE USER u IDENTIFIED BY p ...` is `CREATE ROLE u NOLOGIN
  PASSWORD p` and `CREATE SCHEMA u AUTHORIZATION u` (ORA-01920 when either exists); the user cannot
  log in (ORA-01045) until `GRANT CREATE SESSION` or `CONNECT` (LOGIN) or `DBA` (LOGIN, SUPERUSER);
  `ALTER USER u IDENTIFIED BY p [REPLACE old]`, `ACCOUNT LOCK` (NOLOGIN) / `UNLOCK` (LOGIN), other clauses
  accepted; `DROP USER u [CASCADE]` (ORA-01922 when its schema has objects, 01918 none, 01940 itself);
  `GRANT`/`REVOKE` of other system privileges and `RESOURCE` is accepted and does nothing (a user owns
  its schema), of a lexdb role is a role grant; `GRANT priv ON [TABLE] obj TO u|PUBLIC` is lexdb's grant
  for SELECT, INSERT, UPDATE, DELETE, REFERENCES, ALL (a sequence, tried after a table, gets USAGE for
  SELECT); the other object privileges are accepted and ignored; `WITH GRANT OPTION`/`WITH ADMIN
  OPTION` are accepted and not kept. DDL commits first, as for other DDL.
- **Tests changed**: `tns_client` (no login is ORA-01045; DATE and `numeric(p,s)` shown as Oracle shows
  them), `tns_oracle` (scales of `NUMBER(p,s)` columns); `oracledb_o5.py` is run as `python3
  lexell/tests/lexdb/oracledb_o5.py --lexdb PATH`.

## 18. As built: O6 (2026-11-13)

PL/SQL: anonymous blocks, `CREATE [OR REPLACE] PROCEDURE | FUNCTION | PACKAGE [BODY]`, `CALL`, `EXEC`, OUT and IN OUT
binds on the wire, REF CURSOR OUT values, implicit results, `DBMS_OUTPUT`. For the first time the expected answers come
from a real Oracle: Oracle Database Free 23ai (`gvenzl/oracle-free:slim`, started by hand without TLS) recorded the answers
of `tests/lexdb/oracledb_o6.py` (55 scenarios, about 250 steps: results, OUT values, and the ORA- and ORA-06512 lines of each
error) into `oracle_o6_expect.json`; lexdb answers every one the same (`python3 lexell/tests/lexdb/oracledb_o6.py --lexdb
PATH`; `--oracle user/pw@host:1521/FREEPDB1 --record` records them again). `tests/lexdb/run/tns_plsql.lxl` does the
same through `lib/oracle` (`call` with Outs, REF CURSORs, implicit results). The whole lexdb suite passes; `oracledb_o2.py`,
`oracledb_o4.py` and `oracledb_o5.py` still do. Not run: SQLcl, JDBC, SQL Developer (no Java here).

**Files.** `cmd/lexdb_plsql.lxl` (new, about 4300 lines: tokens, the compile to a tree, the interpreter, the entry points of the
door) and `cmd/lexdb_oratext.lxl` (new: `oraOf`, `oraText` and `oracleSql` moved out of `lexdb_tns`, which calls them as before).
Edits kept small: `lexdb_tns.lxl` (below), `lexdb_exec.lxl` (the catalog snapshot also holds stored units: `USER_/ALL_/DBA_OBJECTS`,
`_SOURCE`, `_PROCEDURES`), `lexdb_oracat.lxl` (two more built bases). Nothing else.

**How a block runs.** A block is parsed whole before anything runs (a syntax error runs none of it, as Oracle compiles). Every
variable, record field, bind (`:name`), cursor attribute and temporary is a slot of the unit's frame; an expression is the
text `SELECT expr` (a condition: `SELECT CASE WHEN c THEN 1 ELSE 0 END`) with each variable replaced by `$slot`, run by the
executor with the frame as its parameters, as `lexdb_tsql` runs T-SQL's `@v` (a literal, a lone variable and a lone
`NULL`/`TRUE` are not run). SQL statements inside the block are rewritten the same way, parsed once and kept (`Ip.scache`).
A name that is a column of a table the statement reads, or in an INSERT's column list, stays the SQL's (Oracle's scope).
A call of a stored function inside an expression is run first and its value put in a temporary the text names; in a SQL
statement of the block only `f(constants)` is done (see "Not done"). Errors are `DbErr`: an Oracle number is the state
`ORAnnnnn`, a user exception `PLXn`; `context` collects the `ORA-06512: at "OWNER.NAME", line N` lines as an error leaves each
unit. Statements: `:=`, `IF/ELSIF/ELSE`, simple and searched `CASE`, `LOOP`, `WHILE`, `FOR i IN [REVERSE] a..b`, `FOR r IN
(query | cursor[(args)])`, `EXIT/CONTINUE [label] [WHEN]`, labels, `RETURN`, `NULL`, `RAISE [name]`, `RAISE_APPLICATION_ERROR`,
nested blocks, `EXCEPTION WHEN a OR b | OTHERS` (the predefined names, declared ones, `PRAGMA EXCEPTION_INIT`; `RAISE;`
re-raises; `SQLCODE`, `SQLERRM`), `SELECT ... INTO` (NO_DATA_FOUND, TOO_MANY_ROWS), `INSERT/UPDATE/DELETE [... RETURNING ...
INTO]`, `SQL%ROWCOUNT/FOUND/NOTFOUND`, explicit cursors (`OPEN/FETCH/CLOSE`, `%FOUND/%NOTFOUND/%ISOPEN/%ROWCOUNT`, parameters),
`OPEN rc FOR query | string [USING ...]`, `EXECUTE IMMEDIATE ... [INTO] [USING [IN|OUT|IN OUT]]` (DDL commits first; a dynamic
block runs as a block with its binds), `COMMIT`, `ROLLBACK [TO]`, `SAVEPOINT`, `LOCK`. Declarations: variables, constants, `NOT
NULL`, `%TYPE`, `%ROWTYPE` (table or cursor), `RECORD` types, `REF CURSOR` types and `SYS_REFCURSOR`, exceptions, cursors.
Types: NUMBER(p,s), the INTEGER family, VARCHAR2/CHAR (length checked: ORA-06502), BOOLEAN, DATE, TIMESTAMP, RAW, BINARY_FLOAT/
DOUBLE, CLOB/BLOB as text and raw; the empty string is NULL on assignment; `x mod y` as an operator.
Built-in packages: `DBMS_OUTPUT` (`ENABLE`, `DISABLE`, `PUT`, `PUT_LINE`, `NEW_LINE`, `GET_LINE`, `GET_LINES`: lines are kept only
after `ENABLE`, as Oracle's; the buffer is the connection's), `DBMS_SQL.RETURN_RESULT`, `DBMS_LOCK.SLEEP`/`DBMS_SESSION.SLEEP`;
`DBMS_APPLICATION_INFO`, `DBMS_SESSION`, `DBMS_STATS` calls are accepted and do nothing.

**Transactions.** A DML statement begins the transaction when there is none and runs under a savepoint (a failure undoes it
alone); after one that went well the savepoint `lxl_pl_s` is the place a failed read goes back to (PostgreSQL's failed
transaction would otherwise end it). A block that ends in an error is undone whole, as Oracle: back to `lxl_pl_0` made at its
start, or rolled back when it began the transaction. `COMMIT` inside a block forgets those savepoints. The call's commit flag
commits after a block that went well. A recursion nests about 60 levels (a task's stack is 256 KiB): the next is ORA-04030.

**Stored code.** Source is a catalog row (`\x02src\x00` owner, kind, name: PROCEDURE, FUNCTION, PACKAGE, PACKAGE BODY), written in
a transaction of its own (DDL commits first), so every connection sees it and it survives a restart; a store-wide counter
(`plsql.ver`, a memo) says when to compile again. Each connection keeps a `Prog`: all stored units compiled when the catalog or
a DDL changes (signatures first, so units may call one another; then bodies; packages twice, once for what they offer).
A unit that does not compile is stored invalid, with the warning ORA-24344 (python-oracledb's `cursor.warning`); a call of it
is PLS-00905. A package keeps its variables in the session (the copies in each member's frame are saved and loaded around
every call); the body's `BEGIN ... END` runs when the package is first used; creating or dropping it, or another connection
changing its source, discards the state (Oracle says ORA-04068: not told). Members the specification does not declare are
private. Calls are resolved when the caller is compiled (PLS-00201 / PLS-00302 / PLS-00306 with Oracle's second ORA-06550 part).

**On the wire (lexdb_tns).** `execute` sends a block to `runPlsql`: the binds by name (sites of `tns.bindSites`, each name once),
the values into `Frame` slots, the result from `runBlock`. The IO vector says which binds are OUT (16), IN (32), IN OUT (48):
decided by how the block uses each (assigned only, read only, both; as an argument by the parameter's mode). The ROW_DATA that
follows has the OUT values in bind order, each with its actual length 0 (arrays: a count, then each); a REF CURSOR is its
describe and a cursor id (`describeBody`: the part of DESCRIBE_INFO after its header, now shared) of a server cursor that holds
the rows (`handOut`). The client reads it with EXECUTE without the execute option or with FETCH: both send the rows. Implicit
results are an IMPLICIT_RESULTSET message of such cursors. A re-execute sends values only for the binds that are not OUT: the
cursor keeps the directions (`Cursor.dirs`). An array bind (`cursor.arrayvar`) is read and, as OUT, sent back: for
`DBMS_OUTPUT.GET_LINES`. `executemany` of a block runs it once per row. `CALL f(x) INTO :r` and `EXEC p(x)` are made blocks.
`CREATE ... PROCEDURE` and the rest go through `unitDdl`; `SELECT f(1) FROM dual` makes the call at prepare (and prepares again at each
execute). The server now says `AUTH_MAX_OPEN_CURSORS` (300) at login: python-oracledb sizes its list of cursors to close from
it (without it the list had one place and a REF CURSOR overflowed it) and turns its statement cache on.

**Not done.** Collections (`TABLE OF`, `VARRAY`, index-by tables, `BULK COLLECT`, `FORALL`, `MULTISET`), object types, triggers
(no hook in the executor for `:new`/`:old`), `PRAGMA AUTONOMOUS_TRANSACTION` (read and ignored: a commit in such a unit
commits the caller's work), subprograms declared inside a block, `GOTO`, `WHERE CURRENT OF`, `FOR UPDATE` cursors' locks,
`SELECT ... INTO` of several rows, `INTERVAL` variables, `DBMS_SQL` other than `RETURN_RESULT`, `UTL_*`, `ALTER SESSION` and
user administration inside `EXECUTE IMMEDIATE`, a package's public variables and cursors from outside (`pkg.var`), stored
functions inside SQL statements with arguments that are columns (the executor has no user functions), `ALL_ARGUMENTS` and
`USER_ERRORS` (empty), `SHOW ERRORS`. A compile error says what Oracle does in its first lines and line/column, but PLS-00103's
"when expecting one of" lists are not given. DBMS_OUTPUT via SQLcl's `DBMSOUTPUT_LINESARRAY` object bind is not done (the
blocks that loop on `GET_LINE`, and `GET_LINES` into an index-by table bind, are).

**Found in Oracle's answers.** A PL/SQL conversion fails with ORA-06502 ("PL/SQL: value or conversion error: character to
number conversion error"), where SQL says ORA-01722; ORA-01422's text is "exact fetch returned more than the requested number
of rows " (a trailing space); SQLCODE is 100 for NO_DATA_FOUND and 1 for a user exception, SQLERRM "User-Defined Exception";
an unhandled user exception reaches the client as ORA-06510; an error inside a block undoes the block's changes, a handled one
only the failing statement's; the trace line of an error in a DECLARE is that declaration's line; a cursor already open names
the cursor's declaration in its second trace line (not copied); `exec` is a SQL*Plus command (lexdb accepts it).

## 19. Verification pass (2026-11-13)

Every UNVERIFIED expectation (O3's `tns_oracle`, O5's `tns_nls` and `oracledb_o5.py`) was run on a real Oracle
(`gvenzl/oracle-free:slim`, now "Oracle AI Database 26ai Free", 23.26.3; the old `lxl-oracle` container was stuck
stopping and was replaced), the true answers recorded, and lexdb compared statement by statement. An error
battery (about 130 statements: constraint, conversion, syntax, DDL errors) and a function battery were diffed too.

**Differed and fixed.** `SELECT *` from DUAL labelled dummy (DUMMY). Expression labels keep no blanks inside string
literals either (`TRIM('B')`). `seq.NEXTVAL` is labelled NEXTVAL/CURRVAL. A bad NLS value of any parameter is
ORA-12705 (not 12700/12702/12703; NLS_SORT and NLS_CALENDAR are checked); time zone limits -15..15 and ORA-01882's
text. TO_DATE: a year element with no digit is ORA-01841, input that ends early ORA-01840, day 31 of a short month
ORA-01839, 23ai's message texts for 1843, 1858, 1830. SESSIONTIMEZONE and DBTIMEZONE. A wrong argument count of an
`#ora_` function crashed the server (index out of range): now ORA-00938/00939. ORA-01407 (update to NULL), 00913,
01430, 01785, 01789, 02289 (sequence), 00902, 01428, 01858 (implicit date of a non-digit), 01722/00932 for operator
errors; 23ai's message texts with names for 00942, 00904, 01400. Added: CONNECT BY LEVEL <=/< n over DUAL (a row
generator), INTERVAL '1' DAY/MONTH/..., YEAR TO MONTH, DAY TO SECOND (it was read as one second: silently wrong),
ROUND(x, negative) (was ORA-01426, in pg mode too), UPPER/LOWER of non-ASCII, GREATEST/LEAST with a NULL, RAWTOHEX,
HEXTORAW, TO_CLOB, IYYY/IYY/IY, the TH suffix, explicit FF is nine digits. Tests: expectations of `tns_oracle`
now Oracle's own (new lines for the additions), `tns_nls` and `oracledb_o5.py` say 12705; both marked verified.
Whole suite 140/140; `oracledb_o2/o4/o5/o6` pass.

**Remains (known).** ORA-00979 vs 00937 (no GROUP BY) and lexdb accepting a column functionally dependent on the
primary key; syntax errors are ORA-00900 where Oracle says 00936/00903/00907; `INSERT ... VALUES` with too few
values (00947); MOD(x, 0) (Oracle: x); `NEXTVAL` twice in one row, CURRVAL beside NEXTVAL, and ORA-02287 for a
sequence in WHERE; `to_number('1e400')` and `1e300*1e300` give NULL (01426); 23ai says ORA-41900 for a DML
statement without privilege on a table the user can read (lexdb 01031) and ORA-28000 for a locked account (lexdb
01045); constraint names, 12899/01438's detail and 01722's text differ; ROUND/TRUNC(date, 'IW') etc., ROUND of
a date, REMAINDER, MEDIAN, LNNVL, SOUNDEX, DUMP, NUMTODSINTERVAL, FROM_TZ, NEW_TIME, DBMS_RANDOM, PIVOT/UNPIVOT,
TABLE(), TZH/TZM/TZR, RN and TM number formats, `DATE '2024-01-31' + INTERVAL '1' MONTH` (Oracle: 01839, lexdb
clamps), timestamp minus timestamp (a number, not an interval), a label's non-ASCII letters are not upper-cased;
catalog views a user cannot see as Oracle's do (V$SESSION, DBA_USERS for a plain user; ALL_OBJECTS and USER_TABLES
of a schema with objects came out empty in the one case tried: not investigated). The `rownum before order`
answer has no fixed value on Oracle (4;3 seen; lexdb 2;1).

## 20. Review fixes (2026-11-14)

An Opus review of the Oracle door found the faults below; each was checked in the code first, and all were real.
Tests: `tests/lexdb/run/tns_review.lxl` (crash cases, privilege, splice, lock, buffer, catalog and GRANT cases);
the whole lexdb suite passes (141/141). The python-oracledb checks (`oracledb_o*.py`) were not run: the module is not
installed on this machine.

**Crashes (the process stops on any of them).** `lexdb_orafn`: a float that is NaN or past 64 bits as an int is ORA-01426
(`floatInt`); `date + n` bounds the days (ORA-01841) and adds with a check (`tsAdd`); ADD_MONTHS bounds its months and checks
its result; SUBSTR's end and INSTR's start are computed without overflow; TRUNC clamps a scale (a negative one past the 38
digits is 0) and uses `mulExact`; `+`/`-` of numbers use `addExact`/`subExact` (ORA-01426). The shared `callAt` ROUND
(PostgreSQL and TDS too) clamps its scale and uses `mulExact`. **LOB_OP:** `lobBad` refuses a negative or huge offset or
amount (ORA-21560) before any slice, and a WRITE or TRIM that would pass LOB_LIMIT; a connection keeps at most 4096
locators; FREE_TEMP frees a temporary LOB. **Login:** a request before the login is at most 16 KiB (`requestTooBig`), no more
64 MiB re-parsed per packet; a failed phase two resets the challenge and ends the connection (one guess per challenge).
**PL/SQL:** CREATE and DROP of a procedure, function or package take the owner from the name and need the owner to be the
session's user or a superuser (ORA-01031); a spliced call value is in parentheses (`a--1` was a comment); loops yield every
1024 iterations; DBMS_OUTPUT honours `ENABLE(buffer_size)` (default 20000, NULL 16 MiB; ORU-10027 as ORA-20000), a line is at
most 32767 bytes (ORU-10028), and the bytes are counted, not re-measured.

**Other.** SELECT ... FOR UPDATE and LOCK TABLE begin a transaction in an idle session (the locks were released at once).
CREATE, ALTER and DROP USER run in one transaction. More than 300 open cursors is ORA-01000 (REF CURSORs handed out are not
counted). `ALTER ROLE ... PASSWORD 'ORA12C$...'` clears the SCRAM verifier (the old password stopped working on Oracle only).
`(VALUES (x)) v(dummy)` is no longer labelled DUMMY (DUAL's subquery is `#values:01`). The USER_ views list a user's own
schema: objects of the public schema are the login's own only when it has no schema of its name (else the system's).
GRANT ... ON takes a name or schema.name, quoted or not, and nothing else (ORA-00942). A trust login that has no role counts
as a DBA (`isSuper`), as lexdb's role statements treat it.

**Not done.** A client that opens REF CURSORs without closing them is not capped (only EXECUTE's cursors are). `LOCK TABLE`
has no lexdb statement of its own, so the begin-a-transaction rule for it is in place but untested. MERGE is built (design/lexdb.md 9.121).

## 21. Java client pass (2026-11-14)

Oracle's own Java clients had never been run against the door (O1's "Not run: JDBC, SQLcl, ODP.NET"). This pass ran ojdbc11
23.26.4 (thin) and SQLcl 26 against lexdb, and the same programs against a real Oracle Database Free (23ai) to know the right
answer: `tests/lexdb/java/OracleJdbc.java` (about 185 checks: connect by service name, DatabaseMetaData, binds of every type,
batches, every column type, CLOB and BLOB, transactions and savepoints, MERGE, errors by number, CallableStatement with OUT
parameters and a REF CURSOR, DBMS_OUTPUT, Statement.cancel) and `OracleTcps.java`; see its README for how to run them. The real
Oracle passes all of them. JDBC could not log in at all before: python-oracledb is more forgiving than the driver Oracle ships,
and every difference below was found by running JDBC (its own `-Doracle.jdbc.diagnostic.enableLogging` trace shows what it read,
and a copy of the bytes on the wire to and from the real server settled the layout).

**What JDBC wants that python-oracledb did not need (all fixed in `lexdb_tns.lxl`).**

- **ACCEPT.** Version 319 and up has the database UUID (16 bytes after the flags; JDBC read past the packet and threw
  BufferUnderflow); the word at offset 8 is the byte order JDBC reads the FDO's length in (1); flag 0x04 says the server
  has no native network services, else JDBC sends its NA negotiation (`deadbeef`) and waits for an answer lexdb has none of.
- **PROTOCOL.** The port description is read as at most 50 bytes with no NUL: the banner (80 bytes) made JDBC wait for the
  rest of the reply. It is the 44-byte `Oracle Database 23ai Free Release 23.0.0.0.0` now (`PROTOCOL_BANNER`).
- **DATA TYPES.** A table entry whose converted type is 0 has no representation after it (4 bytes, not 8): lexdb read JDBC's
  table past its end and waited for more.
- **Logon.** The user, and later the SQL text, come without a length byte after their length (python's have one): `lenStr` takes
  either (the byte at the position is the length: python's; else the bare bytes). AUTH_SVR_RESPONSE is encrypted *with* padding
  (48 bytes: JDBC's decrypt is PKCS5; python reads bytes 16 to 32 of what it decrypts, so both work). JDBC upper-cases the user
  name, so under trust a role without a verifier logs in with its name upper case as its password (`sa`/`SA`).
- **Function codes.** OVERSION (59: getDatabaseProductVersion; the banner has no length byte, JDBC reads its length first and
  then that many bytes) and the second close-cursors piggyback, 120 (the same body as 105). The call's *sequence number* is echoed
  in the ERROR message's call number: JDBC compares it with its request's, and the error number and the current row come in the
  attributes ahead of the message's own copy (JDBC reads the first, python-oracledb the second: both are sent).
- **Describe.** The scale (and every field read as SB1) is a signed variable-length integer when the client's DataTypes table has
  SB1 (27) as representation 1 (JDBC's; python's is Oracle's 10, a byte): `0` is `00`, 2 is `01 02`, -127 (NUMBER's) is `81 7f`.
  `Out.sb1u` carries it; a connection says which client it is by that table. A bind's scale is a universal integer for NUMBER and the TIMESTAMP types.
- **Rows with the run.** JDBC sends no FETCH bit; its prefetch rows are asked for in the same call (and for a statement run
  again, in the call's iteration count). For a LOB column JDBC defines the columns in a call that also fetches, and takes a describe
  there for a change of columns (it dropped the DATE-to-TIMESTAMP mapping it had made): no describe is sent to JDBC at that
  point, and the rows carry the LOB prefetch layout JDBC asked for (a CLOB: a flag, the form of use and an empty data; a BLOB: the
  empty data) before the locator.
- **DML.** JDBC sets "return row counts" on every DML statement and reads the message with six words first and the counts after:
  `executeBatch` has per-row counts (`[1, 0, 1]`) and `executeUpdate` works.

**Bugs it found that are not JDBC's alone.** `SAVEPOINT` in an open transaction: the guard that undoes a failing statement
alone made its own savepoint and released it, which released the user's too (`ROLLBACK TO sp1`: ORA-20000). The catalog views
named the account of the templates (`APP`) as the OWNER of every object, so `ALL_OBJECTS`, `ALL_TABLES` and `ALL_TAB_COLUMNS`
found nothing for any other login: getTables, getColumns and every JDBC metadata call came back empty. A view's text column was a
CLOB (VARCHAR2 now). `DBMS_LOB.GETLENGTH`/`SUBSTR`, `UTL_RAW.CAST_TO_*` (NULL: no statistics), `ALL_TAB_COL_STATISTICS` and
`USER_TAB_COL_STATISTICS` (empty, Oracle's columns), `DBMS_UTILITY.NAME_RESOLVE` and `DBMS_METADATA.SET_TRANSFORM_PARAM` (a no-op)
were missing; the last two are what SQLcl calls first for INFO. `select 1 fro dual` is ORA-00923, `select 1 from` 00903 and an
unclosed parenthesis 00907 (ORA-00900 stood for all three). Tests: `tests/lexdb/run/tns_java.lxl` (the savepoint, the owners,
the view, the new functions, the error numbers).

**SQLcl** (connect, `desc`, `info`, `info+`, `tables`, `show user/parameter/con_name`, PL/SQL blocks with DBMS_OUTPUT, `spool`,
`variable`/`print` of a REF CURSOR, `set sqlformat json|csv|xml|ansiconsole`, errors) gives the real Oracle's output; `info` needed the
three catalog items above. The same script on both was diffed.

**Known differences left** (marked KNOWN or SKIP in the programs, or not reached).
- `prepareStatement(sql, new String[]{"ID"})`: JDBC describes the table first with function 119 (ODSY, the object describe:
  a long kpcds message); ORA-03115. `Statement.RETURN_GENERATED_KEYS` is not tried (ROWID).
- A result column is always nullable (`isNullable`); `select 1` is NUMBER(10), Oracle's NUMBER(0,-127); CHAR(n) is VARCHAR2, RAW(n) has the
  size of its data; TIMESTAMP WITH LOCAL TIME ZONE is described as WITH TIME ZONE; a time zone offset in a literal or bind is
  kept as the instant (UTC), not as given.
- `ALL_ARGUMENTS` is empty: SQLcl's `desc proc` lists no arguments; `DBMS_METADATA.GET_DDL` is missing (`ddl table` says the object is
  not found); `V$SGA` is empty (`show sga`). SQLcl shows a DATE as `2020-01-15 00:00:00` where Oracle's shows `15-JAN-20`: its
  default format is chosen from something lexdb does not say, not found.
- A foreign key between an `INT` column and a `NUMBER(p)` one is ORA-00932 (lexdb's bigint and numeric; Oracle has one NUMBER).
- `Statement.cancel()` is read after the statement ends (design 13): it works, late, for a long query; constraint names are
  `T_PKEY`, not `SYS_Cnnn`.
