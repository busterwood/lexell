# lexdb: several databases in one server

Status: DEFERRED (2026-11-14). Design only, nothing built; the user parked this work, so do not implement it until they say so. It supersedes the "one database,
for good" decision of design/lexdb-tds.md section 7 (2026-11-11) once the user
agrees to section 10. Stages D1 to D10 (section 8) are sized for one agent each.
Error messages and states quoted here are the expected ones: where a recorded
answer (section 9) differs, the recording wins.

## 1. What exists today

There is no notion of a database. A data directory is one store and one catalog.

- **Storage.** `cmd/lexdb.lxl` `runMaster` takes `DATADIR/lock`, opens one store
  (`lexdb_store.open(lexdb_disk.real(dir), opts)`: `data.lxdb`, `log.N`,
  `log.spare`) and hands that one `Store` to every door's accept loop
  (`lexdb_wire.acceptAll`, `lexdb_tds.acceptAll`, `lexdb_tns.acceptAll`) and to
  `lexdb_repl.serve`. The store's `Db` holds one tree map, one log, one cache
  (`Options.cacheBytes`), one memo (`Db.memo`, process-local, not durable).
- **Catalog.** One tree, `lexdb_exec.CATALOG = 1`, made by `lexdb_exec.bootstrap`.
  Its keys, by prefix: `\x01` index names, `\x02version` (`CAT_VERSION`),
  `\x02stats` (`STAT_VERSION`), `\x02stat\x00` statistics, `\x02seqs`
  (`SEQ_TREE`: the id of the one sequences' values tree), `\x02acl\x00` owners
  and grants (`ACL_PRE`, objects `r:` relation, `n:` schema), `\x02mem\x00` role
  memberships (`MEM_PRE`), `\x02src\x00` PL/SQL sources (`lexdb_plsql.SRC_PRE`),
  `\x02enum\x00` enums, `\x03` schemas (`schemaKey`), `\x04` sequences
  (`seqRow`), `\x05` roles (`roleKey`), then relations by qualified name.
  Temporary objects are rows under `pg_temp_N` (`lexdb_base.tempCatKey`).
  `CATALOG` appears 142 times in `lexdb_exec.lxl` and 3 in `lexdb_plsql.lxl`.
- **PostgreSQL door.** `lexdb_wire.startup` reads `user` and `TimeZone` from the
  startup packet and ignores `database`: any name connects (tests use `test`,
  `postgres`, `x`, `crash`). `current_database()` is the literal `"lexdb"`
  (`lexdb_exec.lxl` near 2843); `pg_database` is one fixed row, oid 16384
  (`catRows`, `let db = "lexdb"`); `pg_database_size` knows only `lexdb`
  (else 3D000); `GRANT ... ON DATABASE` is accepted and ignored (9.83);
  `REINDEX DATABASE other` is refused at parse time (`lexdb_sql.lxl`, "can only
  reindex the currently open database"). A three-part name is a syntax error.
- **SQL Server door.** `lexdb_tds.DB_NAME = "lexdb"`. `Conn.login` refuses a
  LOGIN7 database other than `lexdb`, `master` or empty with 4060; `welcome`
  sends ENVCHANGE 1 (`lexdb` from `master`) and INFO 5701. `USE`
  (`lexdb_tsqlparse.TS_USE`, run in `lexdb_tsql` `State.call`) accepts `lexdb`
  and `master` (both stay in lexdb's catalog, event `EV_DB`), gives 916 for
  tempdb, model and msdb and 911 for anything else. `sys.databases` lists
  master 1, tempdb 2, model 3, msdb 4 and lexdb 5 (`sysDbRow`,
  `SYS_DB_NAME`, `SYS_DB_ID`, `lexdb_syscat.dbId`/`dbName`). `lexdb_sql`
  `P.qname` parses `[db.][schema.]name` and `db..name` and **drops the database
  part**, so `otherdb.dbo.t` silently reads `dbo.t`. `DB_NAME()` becomes
  `current_database()`; `@@SERVERNAME`-like `f.vals[5]` is `"lexdb"`.
- **Oracle door.** `lexdb_tns.serviceOf` reads SERVICE_NAME or SID;
  `Conn.connect` accepts `lexdb` (`SERVICE`), `freepdb1` (`SERVICE2`) or none,
  else REFUSE 12514. `SYS_CONTEXT('USERENV','CON_NAME'|'SERVICE_NAME')` is folded
  at parse time to `FREEPDB1` (`lexdb_sql.oraSysContext`), `DB_NAME` and
  `CDB_NAME` to `LEXDB`; `V$CONTAINERS`/`V$DATABASE` rows are fixed (`oraRows`,
  CON_ID 3). There is no `V$PDBS` and no `ALTER SESSION SET CONTAINER`
  (`Conn.setParam` knows CURRENT_SCHEMA and NLS parameters).
- **Replication.** `lexdb_repl` serves `DATADIR/repl.sock` for the one store;
  a replica opens the same directory's files (`connect`, `openReplica`).

## 2. The model

### 2.1 One store per database, or one store with a catalog per database

| | A. a store (directory) per database | B. one store, a catalog tree per database (recommended) |
|---|---|---|
| Isolation | a corrupt page or a fatal flush error stops one database's store (the process still dies on a trap) | one store: as today, a fault stops all (PostgreSQL's shared WAL and buffers are the same) |
| DROP DATABASE | remove a directory, space back at once | drop its trees; pages return to the free list (9.32, 9.33), the file does not shrink |
| Backup | per database by copying its directory | the whole directory (as `pg_basebackup`); per database only logical (pg_dump through the PG door) |
| Crash recovery | N logs replayed, N meta pages | unchanged |
| Commits | a flush per database's log; no atomic commit across databases | unchanged group commit; a transaction may span databases |
| Replication | `lexdb_repl` per directory, a replica must discover new databases | unchanged: database rows replicate as catalog rows |
| Page cache | N budgets to balance | one budget, shared, as PostgreSQL's shared_buffers |
| Connection start | open (and replay) a store on first use | one catalog lookup |
| Roles, memberships | cluster-wide rows read across stores, no transaction | rows in tree 1, transactional |
| Session memo state (`roleKeyOf`, `userKey`, `tmpMemo`, `advMemo` ...) | per store: lost or moved on USE | one memo: unchanged |
| Tree ids (`acKey(tree)`, `CHG_TREE`, lock keys `tree:key`) | collide across stores | global: unchanged |
| T-SQL cross-database queries | needs a Store per table through the whole executor | trees are global: only name resolution changes |
| Template copy | copy files (with a checkpoint) | copy rows into new trees (section 3.5) |
| Migration of an old DATADIR | move files into a subdirectory | none: tree 1 is the default database's catalog |

**Recommendation: B.** It is PostgreSQL's own split (shared WAL, buffers and
cluster catalogs `pg_database`/`pg_authid`; per-database catalogs), it needs no
change to the store, the log, recovery or replication, it keeps every
per-session memo key and global tree id valid, and it makes T-SQL's cross-database
reads and transactions cheap. What it gives up (per-database physical backup,
detach/attach, space returned by DROP, separate cache budgets) is listed in
section 10, O2.

### 2.2 Cluster-wide and per-database rows

Tree 1 (`CATALOG`, called GLOBAL below) is both the cluster catalog and the
default database's catalog. Every other database has a catalog tree of its own,
made by `createTree`. A key's tree is decided by its prefix alone:

| Key | Tree |
|---|---|
| `\x05` roles; `\x02mem\x00` memberships | GLOBAL |
| `\x02db\x00` databases, `\x02dbnext`, `\x02dbddl`, `\x02dbgone\x00` (new, 2.3) | GLOBAL |
| `\x02acl\x00d:` a database's owner and grants (new) | GLOBAL |
| any key `lexdb_base.tempCatKey` says is temporary | GLOBAL (temporary objects are cluster-wide: tempdb's semantics) |
| `\x02seqs` and the sequences' values tree it names | GLOBAL only (values are keyed by `Seq.id`, unique in the process and across restarts) |
| everything else: tables, views, indexes, schemas, sequences' definitions, statistics, ACLs `r:`/`n:`, enums, PL/SQL sources, `CAT_VERSION`, `STAT_VERSION` | the database's catalog tree |

There are no tablespaces (`pg_tablespace`'s two fixed rows stay).

### 2.3 New rows in GLOBAL

- **A database:** key `"\x02db\x00" + name` (name folded to lower case as
  identifiers are under L6; `CREATE DATABASE "A"` and `a` collide, 42P04).
  Value: fields joined by `\t`, decoded tolerantly (missing trailing fields take
  their defaults, as `decRole` does):
  `id \t cat \t state \t allowConn \t connLimit \t isTemplate \t spell \t coll \t settings`
  - `id`: the database's number, from `\x02dbnext` (read and incremented by
    CREATE; first value 6). The default database is 5.
  - `cat`: its catalog tree (1 for the default).
  - `state`: `r` ready, `c` being copied from a template (D8; invisible to
    connections and to `pg_database`).
  - `allowConn` `1`/`0`; `connLimit` -1 none, else 0 to 2147483647;
    `isTemplate` `1`/`0`.
  - `spell`: the name as written where it differs from the key (L6), else "".
  - `coll`: the database collation (T-SQL `COLLATE`, D4), "" the door's default.
  - `settings`: `ALTER DATABASE ... SET` defaults, `name\x1fvalue` joined by `\x1e`.
- **`\x02dbddl`**: a blind write (put without a read) by `bumpCatalog` whenever
  the transaction's catalog is not GLOBAL, so the watched tree's change count
  (`Store.watch(CATALOG)`, `Store.changes`) moves on DDL in any database: the
  wire's kept descriptions (`lexdb_wire` describe, `colsAt`) and the
  sessions' database checks (5.8) see it. Blind writes never conflict.
- **`"\x02dbgone\x00" + cat`**: a database being dropped: its remaining tree ids,
  space-separated (5.9). Finished by `bootstrap` after a crash.
- **ACL object `d:` + name**: owner and grants of a database (section 4).

The default database's row is written by `bootstrap` on a master when absent
(`id 5, cat 1, state r, allowConn 1, connLimit -1`); every reader also treats
a missing row for cat 1 as that implicit row (replicas, the simulated tests).

### 2.4 Ids per door

| | default database | database of id N |
|---|---|---|
| name | `lexdb` (`DEFAULT_DB`; `SYS_DB_NAME` kept as an alias) | its name |
| PG oid (`pg_database.oid`, `datdba` from its ACL owner) | 16384 | 16384 + N - 5 |
| TDS `database_id` | 5 (1 to 4 stay master, tempdb, model, msdb) | N |
| Oracle CON_ID / CON_NAME | 3 / `FREEPDB1` (as recorded today) | N - 2 / upper-case name |

### 2.5 The default database, aliases and migration

- An existing DATADIR opens with no flag: tree 1 already is the default
  database's catalog; `bootstrap` adds one row. Nothing is rewritten. Old
  binaries never see a multi-database directory (no downgrade promise).
- Aliases of the default database, resolved in the doors only: PG `postgres`;
  TDS `master` and ""; TNS `lexdb`, `freepdb1` and "". The names `template0`,
  `template1`, `postgres`, `master`, `tempdb`, `model`, `msdb`, `freepdb1`,
  `cdb$root`, `pdb$seed` cannot be created (42P04 / 1801 / ORA-65012).
- The default database cannot be dropped or renamed (0A000 "lexdb: the
  default database cannot be dropped or renamed"; O4).
- A PG startup naming no database means the user's name (PostgreSQL's rule).
  An unknown name connects to the default database (today's behaviour) unless
  `--strict-databases` is given, then FATAL 3D000 (O1).

### 2.6 Templates

`template0` and `template1` are virtual rows of `pg_database`
(`datistemplate` true, `datallowconn` false for template0, true for template1),
both standing for "an empty database"; connecting to either is FATAL 55000
'database "template1" is not currently accepting connections' (O5).
`CREATE DATABASE x` with no TEMPLATE, TEMPLATE template0 or template1, and
T-SQL's model, make an empty catalog. TEMPLATE naming a real database copies
it (D8); before D8, 0A000 "lexdb: TEMPLATE must be template0 or template1".

## 3. Operations

### 3.1 The engine's API (`lexdb_exec.lxl`)

```
pub const DEFAULT_DB = "lexdb"
pub type DbInfo = record { pub name: str; pub spell: str; pub id: int; pub cat: int; pub state: str;
                           pub allowConn: bool; pub connLimit: int; pub isTemplate: bool; pub coll: str; pub settings: []str }
pub fn databases(st: &lexdb_store.Store): Result[[]DbInfo, DbErr]              // committed, ready ones, by id
pub fn findDatabase(st: &lexdb_store.Store, name: &str): Result[Option[DbInfo], DbErr]   // folded match
// Session fields: cat (1), dbId (5), dbName (DEFAULT_DB), dbSeen (Store.changes() when last checked), dead (false)
pub fn (s: mut &Session) attach(name: &str): Result[Unit, DbErr]       // "" the default; at connection start
pub fn (s: mut &Session) useDatabase(name: &str): Result[Unit, DbErr]  // USE, SET CONTAINER
pub fn (s: &Session) database(): str        // the spelled name
pub fn (s: &Session) databaseId(): int
```

`attach` and `useDatabase` check, in order: exists (3D000 'database "x" does
not exist'), `allowConn` (55000), CONNECT privilege (42501 'permission denied
for database "x"', detail 'User does not have CONNECT privilege.'), the
connection limit (53300 'too many connections for database "x"'; superusers
exempt, as PostgreSQL). Then: the session's connection count moves (memo
`"\x00dbconn\x00" + id`, decremented by `close` and by `useDatabase` leaving),
`s.cat`/`dbId`/`dbName` are set, `s.pathAt += 1` (kept descriptions and plans
go), an open block's `s.txn[0].cat` follows, the search path is reset to the
default for `useDatabase`, and the row's `settings` are applied with the
session's SET machinery (an invalid one is skipped with a WARNING, 01000).
`useDatabase` to the current database is a no-op that still succeeds.
`close` runs `chgEnd` before the count moves (it already does), then decrements.

### 3.2 Statements (shared parser, `lexdb_sql.lxl`)

New kinds at the next free `S_` numbers (60 to 62 at the time of writing):
`S_CREATE_DATABASE`, `S_DROP_DATABASE`, `S_ALTER_DATABASE`; the name in
`Stmt.table`, options as `name:value` strings in `Stmt.names`, `ifFlag` for IF
[NOT] EXISTS. Forms, by dialect:

- **PostgreSQL**: `CREATE DATABASE name [WITH] [OWNER [=] role] [TEMPLATE [=] t]
  [ENCODING [=] e] [LOCALE|LC_COLLATE|LC_CTYPE|ICU_LOCALE|LOCALE_PROVIDER|COLLATION_VERSION [=] x]
  [TABLESPACE [=] pg_default] [ALLOW_CONNECTIONS [=] b] [CONNECTION LIMIT [=] n]
  [IS_TEMPLATE [=] b] [STRATEGY [=] s] [OID [=] n]`. ENCODING other than UTF8
  (any case, or 6) is 0A000; the locale options are read and ignored (lexdb is
  C everywhere); `OID` is 0A000. `DROP DATABASE [IF EXISTS] name [[WITH] (FORCE)]`.
  `ALTER DATABASE name RENAME TO new | OWNER TO role | [WITH] ALLOW_CONNECTIONS b
  | CONNECTION LIMIT n | IS_TEMPLATE b | SET p {TO|=} v | RESET p | RESET ALL`.
- **T-SQL** (parsed with `Dialect.tsql`): `CREATE DATABASE name [CONTAINMENT = ...]
  [ON ... [LOG ON ...]] [COLLATE c] [WITH ...]` (file specs and WITH options read
  and ignored); `DROP DATABASE [IF EXISTS] a [, b ...]`; `ALTER DATABASE {name |
  CURRENT} MODIFY NAME = new | COLLATE c | SET SINGLE_USER|RESTRICTED_USER|MULTI_USER
  [WITH ROLLBACK IMMEDIATE|ROLLBACK AFTER n|NO_WAIT] | SET OFFLINE|ONLINE | SET
  <any other option> (accepted, no effect: READ_COMMITTED_SNAPSHOT, RECOVERY,
  COMPATIBILITY_LEVEL, ... as EF Core's EnsureCreated sends)`;
  `ALTER AUTHORIZATION ON DATABASE::name TO login`. SINGLE_USER is connLimit 1,
  MULTI_USER -1, OFFLINE allowConn 0, ONLINE 1.
- **Oracle** (D9): `CREATE PLUGGABLE DATABASE name ADMIN USER u IDENTIFIED BY p
  [any other clause ignored]`, `DROP PLUGGABLE DATABASE name [INCLUDING|KEEP DATAFILES]`,
  `ALTER PLUGGABLE DATABASE name OPEN [READ WRITE] | CLOSE [IMMEDIATE]` (allowConn).

Rules for all: CREATE and DROP are refused in a transaction block (PG 25001
"CREATE DATABASE cannot run inside a transaction block"; T-SQL 226 "CREATE
DATABASE statement not allowed within multi-statement transaction."); ALTER may
run in one. Refused on a replica (25006). A name is 1 to 63 bytes (42602 else).
CONNECTION LIMIT is parsed with `parseIntOpt` and range-checked (-1 to
2147483647, 22003 else). Errors: exists 42P04 'database "x" already exists'
(1801); missing 3D000 (3701 "Cannot drop the database 'x', because it does not
exist or you do not have permission."; IF EXISTS gives the NOTICE 'database "x"
does not exist, skipping' through `noticeKey`); dropping or renaming the
current database 55006 'cannot drop the currently open database' / 'current
database cannot be renamed' (3702); other sessions connected and no FORCE /
ROLLBACK IMMEDIATE: 55006 'database "x" is being accessed by other users',
detail 'There is 1 other session using the database.' (3702 "Cannot drop
database "x" because it is currently in use."; 5030 for MODIFY NAME).

### 3.3 PostgreSQL door

- `lexdb_wire.startup` keeps the `database` startup parameter (default the
  user's name). After `authenticate` and AuthenticationOk, before the
  ParameterStatus messages: resolve the alias (`postgres`), then
  `w.sess.attach(name)`; with no such database and no `--strict-databases`,
  `attach("")`. An error is FATAL with its state and the connection closes.
  `--strict-databases` is a `lexdb.lxl` flag passed like `AuthConf` (a field of
  it, stored with the rest by `configure`).
- `current_database()` and `current_catalog` give `s.database()` (the executor
  sees it through the memo, `"\x00db\x00" + sess`, set by attach/use, as
  `userKey` is). `information_schema` `*_catalog` columns and `catRows`'s `db`
  likewise. `pg_database`: template0, template1, then `databases(st)`, each row
  as today's with oid, datname, datdba, datallowconn, datconnlimit,
  datistemplate and datacl filled. `pg_database_size(name|oid)`: the pages of
  that database's trees (its catalog tree and every table's and index's tree,
  listed with `seenTables` under `txn.cat` = its cat). `REINDEX DATABASE n` is
  checked at run time against the current database.
- **Cross-database names**: `a.b.c` as a relation, where `a` is not the current
  database: 0A000 'cross-database references are not implemented: "a.b.c"'; where
  it is, `b.c`. The parser makes `a.b.c` as for T-SQL (3.4, `DBSEP`); the check
  is in `catKey`. psql's `\c db` is a new connection: nothing more.
- `GRANT|REVOKE {CONNECT|TEMPORARY|TEMP|CREATE|ALL} ON DATABASE x` are kept (D6).

### 3.4 SQL Server door

- **Names.** `P.qname` (T-SQL) keeps the database part: `db.s.t` and `db..t` become
  `db + DBSEP + rest`, `srv.db.s.t` `srv + SRVSEP + db + DBSEP + rest`, with
  `pub const DBSEP = "\x1d"`, `SRVSEP = "\x1c"` in `lexdb_sql` beside `QSEP`;
  the msdb special case stays first. `catKey` (and every other name lookup that
  takes a relation name: `findSeq`, view expansion) strips them: a server part
  must equal `@@SERVERNAME` case-insensitively (else 7202 "Could not find server
  'x' in sys.servers."); a database part equal to the current database is
  dropped; `tempdb` before a `#name` is dropped (as today); another existing
  database is a cross-database reference (D7; before D7, 0A000 "lexdb: a name in
  another database is not supported yet"); a missing one is 911.
- **Login.** `Conn.login` resolves LOGIN7's database (Initial Catalog): "" and
  `master` the default, else `findDatabase`; any `attach` error is 4060 "Cannot
  open database "x" requested by the login. The login failed." `Conn` keeps
  `loginDb`. `welcome` sends ENVCHANGE 1 (new = `sess.database()`, old
  `master`) and INFO 5701 with that name.
- **USE.** `State.call` for `TS_USE`: master is the default database (as now);
  tempdb, model, msdb 916 (as now); else `sess.useDatabase(n)`: 3D000 is 911,
  55000/42501/53300 are 916. On success `EV_DB` carries old and new names;
  `Conn.emit` sends ENVCHANGE 1 (new, old) and INFO 5701. USE inside `EXEC
  ('...')` reverts when the EXEC ends (save `sess.database()`, `useDatabase` back,
  ENVCHANGE again only if it changed); USE inside a procedure body is refused
  where procedures are made (154 "a USE database statement is not allowed in a
  procedure, function or trigger."). USE in an open transaction is allowed.
  `Conn.reset` (RESETCONNECTION) attaches the new session to `loginDb`; whether
  SQL Server then sends ENVCHANGE 1 is checked with `tests/lexdb/tds_proxy.py`
  against the oracle and copied.
- **Functions.** `DB_NAME()` current, `DB_NAME(id)`, `DB_ID()` current,
  `DB_ID(name)`, `HAS_DBACCESS(name)` (1 when attach would succeed),
  `DATABASEPROPERTYEX(name, p)` for every database (Collation from `coll`),
  `ORIGINAL_DB_NAME()` `loginDb`. `lexdb_syscat.dbId`/`dbName` keep only the four
  system databases (the `own` parameter goes); `sysCall` resolves the rest with
  `findDatabase`/`databases`. `OBJECT_NAME(id, dbid)` and `OBJECT_ID('db.s.t')`
  for another database: NULL before D7, that catalog's after.
- **Catalog views.** `sys.databases`: the four system rows, then one
  `sysDbRow` per `DbInfo` (name, database_id, owner_sid `sysSid(owner)` or
  0x01 for a superuser, collation_name, user_access 1 when connLimit is 1,
  state 6 OFFLINE when allowConn is 0). Rows with `database_id` (31383,
  31423) use `s.databaseId()`. `INFORMATION_SCHEMA.*.TABLE_CATALOG` the
  current database. `master.sys.x` / `db.sys.x` stay the current database's
  view (SQL Server's sys views of another database are D7, read-only, or never).
- **Collation (L2).** `CREATE DATABASE ... COLLATE c` and `ALTER DATABASE ... COLLATE c`
  take a collation `lexdb_sqlcoll` has (else 448 "Invalid collation 'c'.");
  tables made over TDS in that database default to it instead of
  `TSQL_COLLATION` (O6).

### 3.5 Oracle door

- **Services are databases.** `Conn.connect`: "" , `lexdb`, `freepdb1` the
  default; else `findDatabase(svc)` (a snapshot read: CONNECT comes before the
  login), REFUSE 12514 when absent. After the login, `attach`: 55000 is
  ORA-01109 "database not open", 42501 ORA-01045 "user X lacks CREATE SESSION
  privilege; logon denied", 53300 ORA-00018 "maximum number of sessions exceeded".
- **SYS_CONTEXT.** `oraSysContext` no longer folds CON_NAME, SERVICE_NAME and
  CON_ID: they become calls (`#con_name`, `#con_id`) evaluated from the session
  (2.4); DB_NAME, CDB_NAME, `ORA_DATABASE_NAME` stay LEXDB.
- **V$PDBS** (new: add it to `tools/gen_oracle_catalog.py`'s views and
  regenerate `lexdb_oradata.lxl`) and V$CONTAINERS give one row, the current
  database, as Oracle does inside a PDB (CON_ID, NAME, OPEN_MODE `READ WRITE`).
  V$DATABASE stays LEXDB. There are no CDB_ views (none exist today).
- **ALTER SESSION SET CONTAINER = x.** In `Conn.setParam`: refused in an open
  transaction (ORA-65023 "active transaction exists in container X"); unknown
  ORA-65011 "Pluggable database X does not exist."; then `useDatabase`,
  `forgetParsed()`, CURRENT_SCHEMA back to the user's. Allowed to any role with
  CONNECT on x (lexdb has no common users).
- `DUAL`, the dictionary views and NLS settings are not per database: they are
  computed per statement from the current catalog. `lexdb_plsql`'s stored
  units are per database: `putSource` and `loadStored` take the catalog tree,
  and `Ip` reloads when `storedCat != cat` as well as on `MEMO_VER`.

### 3.6 Template copy (D8)

`CREATE DATABASE x TEMPLATE y` (PG) where y is a real database, superuser or
y's owner, or y `isTemplate`: commit 1 writes x's row with state `c` and its new
catalog tree. Then, from one snapshot (`beginSnapshot`) of y: for each table
(`seenTables` with `cat` = y's) make new trees for it and each index, copy rows
in commits of at most 10,000 rows or 8 MB (fresh transactions writing only new
trees), then copy y's catalog rows: relations re-encoded with the new tree ids
(`decTable`, `putTable`; `Index.tree` too), sequences with new ids and their
current values written to the sequences' tree, schemas, ACLs `r:`/`n:`, enums,
sources verbatim, statistics dropped; `setSpec` for each new table. The last
commit sets state `r`. A cancelled snapshot (too old) or any error drops x as
5.9 does and reports the error. `bootstrap` drops databases left in state `c`.
Other sessions in y do not block the copy (PostgreSQL's 55006 'source database
"y" is being accessed by other users' is not copied: the snapshot is consistent).

## 4. Authorisation

- **Roles are cluster-wide** (GLOBAL `\x05` and `\x02mem\x00`): `CREATE ROLE`
  in any database is seen in all; `pg_roles` is the same everywhere. DROP ROLE's
  dependency check (2BP01) scans the ACL rows of every database.
- **Creating**: superuser, or a role with CREATEDB. `Role` gets `pub createdb:
  bool`, a fifth field of `encRole` (`decRole` defaults false); `roleOptions`
  keeps `createdb`/`nocreatedb` instead of discarding them; `pg_roles.rolcreatedb`
  shows it. Refused: 42501 'permission denied to create database' (T-SQL 262
  "CREATE DATABASE permission denied in database 'master'."; Oracle ORA-01031).
- **Owner** (ACL `d:name`, `ownNew` at CREATE, `OWNER role` needs the creator to
  be a member of role, as PostgreSQL): may DROP, RENAME (and needs CREATEDB to
  rename, as PostgreSQL), ALTER and GRANT. Others: 42501 'must be owner of
  database x'. Superusers always may.
- **Privileges** on a database: `C` CREATE (schemas in it), `T` TEMPORARY,
  `c` CONNECT, as PostgreSQL's aclitem letters; `defaultGrants("d:...")` is
  PUBLIC `Tc`. CREATE SCHEMA then needs the database's C or ownership instead
  of superuser (changing 9.83's rule); a session's first temporary object needs
  T. CONNECT is checked by `attach`/`useDatabase`. Sessions without a role
  (trust, no such role) are not checked, as 9.83 does.
- T-SQL `sys.database_principals` is the same list in every database (dbo for
  superusers and the database's owner, a user per role with CONNECT).

## 5. Engine implications

1. **Transactions.** One store: a transaction may read and write several
   databases (T-SQL USE inside a block, cross-database reads) and commits
   atomically, serializable as any other. `Txn` gets `pub cat: int` (1 in
   `lexdb_store.begin`), set by `Session.setUp` from `s.cat`. PG sessions never
   switch; TNS refuses to switch in a transaction.
2. **Routing.** `fn catOf(txn: &lexdb_store.Txn, k: &str): int` applies 2.2
   (GLOBAL when `txn.cat == CATALOG` or the prefix is cluster-wide or
   `tempCatKey(k)`); `catGet(st, txn, k)`, `catPut(txn, k, v)`, `catDel(txn, k)`
   wrap `st.get`/`txn.put`/`txn.del` with it. Scans use `catOf(txn, &lo)` for
   their tree, except `catScan` (below) and the role scans (GLOBAL).
3. **`catScan`.** Below and above the temporary range: `txn.cat`. In it: keys of
   `txn.cat` that are not of a temporary schema, and, from GLOBAL, the session's
   own (`sc == txn.tmp`); when `txn.cat != CATALOG` the two lists are merged by
   key before `f` sees them (callers rely on key order). `dropLeftTemps` keeps
   scanning GLOBAL.
4. **Temporary objects** live in GLOBAL whatever the current database (tempdb's
   semantics): a T-SQL `#t` made before `USE b` is still there after it. A
   temporary table's foreign keys and views resolve names in the current
   database at use (SQL Server does not enforce FKs on temporary tables; PG
   sessions never switch).
5. **Sequences.** Definitions per database; values in GLOBAL's one tree
   (`seqTree` reads `CATALOG` explicitly). DROP DATABASE deletes its sequences'
   value rows (`txn.del(tree, d.id)`, as DROP SEQUENCE does).
6. **Caches and plans.** `catVersion` returns `txn.cat.toStr() + "/" + raw`;
   `bumpCatalog` bumps the raw value (`nextVersion` parses the leading count) and
   writes `\x02dbddl` when `txn.cat != CATALOG`. So `select`'s kept plans,
   sequence ids and everything keyed by the version are per database. A plan
   that read another database's catalog (D7) is not kept (`pc.keep = false`).
   The bound catalog (`catMemoKey`) is rebuilt per statement already. PG
   prepared statements and portals belong to a connection, hence to one
   database; TDS `sp_prepare` handles survive USE and plan again; TNS cursors
   are reparsed (`forgetParsed`).
7. **Locks.** Row locks are `tree:key` with global trees: unchanged. Advisory
   locks are per database as in PostgreSQL: `advCall`'s key becomes
   `"adv:" + cat + ":" + ...`, `SeqEnv` gets `cat` (set in `seqEnv` from
   `txn.cat`).
8. **A session's database checked.** At the top of `Session.runIn`: if
   `s.st.changes() != s.dbSeen`, set `dbSeen` and look the session's database up
   by id in `databases(st)`; gone: `s.dead = true` and 57P01 'terminating
   connection due to administrator command'; renamed: `dbName` follows. A dead
   session answers every later statement with 57P01, and each door closes the
   connection after sending it (PG FATAL, TDS error 596 severity 21 then close,
   TNS ORA-01089 then close; `lexdb_wire` already makes 57P01 FATAL: make it
   close). On a replica the follower's watched count moves with the master's
   writes, so the same check works.
9. **DROP DATABASE.** Checks (3.2), then without FORCE the count of other
   sessions (memo) must be 0. Commit 1 (GLOBAL): delete the row and its ACL,
   write `\x02dbgone\x00<cat>` with its trees (catalog tree, every table's and
   index's tree; `tree + OVF` companions go with OP_DROP), delete its sequences'
   values. Its sessions die at their next statement (5.8); their open
   transactions fail at commit (40001: they read catalog rows the drop
   deleted) and writes to dropped trees are ignored by the store
   (`applyPut` on a missing tree returns). Then commits of at most 256
   `dropTree` each, rewriting the gone row, the last deleting it; the catalog
   tree last. `bootstrap` finishes gone rows left by a crash. FORCE and T-SQL's
   `ROLLBACK IMMEDIATE` skip the count check.
10. **Background tasks.** The writer and checkpointer are store-wide: unchanged.
    `autoLook` lists tables of every database (`lt.cat` per `DbInfo`, a
    `task.yield()` between databases) and `autoOne` takes the cat for its
    transactions. `VACUUM` with no tables works on the current database (as
    PostgreSQL): `vacuumTables` via `seenTables` is right once `txn.cat` is.
    `bootstrap`'s `upgradeLayouts` loops over databases. `dropLeftTemps`: GLOBAL.
11. **Memory.** One cache for all databases; no per-database limit (PostgreSQL
    has none). `max_statement_mem` stays per session.
12. **Every fresh transaction** (`lexdb_store.begin()`, `beginSnapshot()`: 28
    sites in `lexdb_exec`, 2 in `lexdb_plsql`) is classified in D1: the
    session's (`setUp` or an explicit `t.cat = s.cat`), GLOBAL (roles,
    sequences' values, temporaries, bootstrap), or a loop over databases.

## 6. Replication and backup

- `lexdb_repl.lxl` needs no change: databases are catalog rows in one log. A
  replica serves every database: `attach` reads the replicated rows; CREATE,
  DROP and ALTER DATABASE on a replica are 25006; a database the master drops
  ends the replica's sessions in it at their next statement (5.8). Replicas of
  TDS and TNS are not served today and this does not change it.
- Backup is the whole data directory, as today (cold copy, or a replica's
  view). Per database: logical, `pg_dump -d name` through the PG door. SQL
  Server's `BACKUP DATABASE`/`RESTORE`/`sp_detach_db` and Oracle's
  unplug/plug stay unsupported (0A000 / their "not supported" mapping).
- Crash recovery is unchanged; the two multi-commit operations (DROP, template
  copy) leave rows `bootstrap` finishes or undoes.

## 7. Lexell constraints

- **Integer overflow and stack overflow kill the process, and with it every
  database.** Parse every number from clients with `parseIntOpt` and range
  checks (CONNECTION LIMIT, OID, ROLLBACK AFTER n, ids in `DB_NAME(id)`: a
  bigint argument outside 1..2^31 is NULL); clamp memo counters at 0 when
  decrementing; no recursion over databases or trees (DROP and copy are
  iterative, the tree list is a list).
- **Scheduling is cooperative.** Nothing long runs inside `Store`'s `with`:
  DROP in chunks of 256 trees, template copy in bounded commits, `autoLook`
  yields between databases. `attach` is a few cached reads. A session holding a
  long statement in a database being dropped is not interrupted (5.8 checks at
  statement start); it ends normally or fails at commit.
- A trap anywhere in this code stops all databases, so every new error path
  (FORCE drops under load, USE in blocks, connect to a database being dropped)
  has a test.

## 8. Stages

Each stage keeps the full lexdb test suite passing (natively, `LXL_NOCACHE=1`,
as the memory notes require) and adds the tests named. Merge order is the
numbering; stages marked parallel may run at once in separate worktrees (they
touch different regions of `lexdb_exec.lxl`; rebase on merge).

- **D1. Catalog routing, no behaviour change.** `Txn.cat`, `Txn.dbCats: Map[str,
  int]` (for D7; empty), `Session.cat`, `setUp`; `catOf`/`catGet`/`catPut`/`catDel`;
  every `CATALOG` use in `lexdb_exec.lxl` and `lexdb_plsql.lxl` replaced or
  marked GLOBAL per 2.2 and 5.2-5.6, 5.12; `catScan` per 5.3; `catVersion`
  prefix and `\x02dbddl`; `seqTree` GLOBAL; advisory key with cat. A test hook
  `pub fn (s: mut &Session) useCatalogTree(tree: int)` (no row needed).
  *Done when* the suite passes unchanged and the new
  `tests/lexdb/run/exec_catroute.lxl` shows, with a second session on a fresh
  catalog tree: its tables invisible from tree 1 and back; roles and
  memberships shared; a temporary table visible after switching; a sequence of
  the same name in both with independent values; a prepared SELECT planned
  again after a switch; DDL in tree N moving `Store.changes()`; `pg_class` lists
  per tree.
- **D2. Databases in the engine, PostgreSQL syntax.** Rows (2.3), `bootstrap`
  row and leftover gone rows, `databases`/`findDatabase`/`attach`/`useDatabase`,
  connection counts, 5.8 check, CREATE/DROP [FORCE]/ALTER DATABASE (PG forms,
  TEMPLATE template0/1 only), `current_database`, `current_catalog`,
  `pg_database` with templates, `pg_database_size`, information_schema catalog
  names, REINDEX DATABASE at run time, PG three-part names (0A000 / same
  database), `autoLook` and `upgradeLayouts` over databases. *Done when*
  `tests/lexdb/run/exec_multidb.lxl` (two and three sessions on a simulated
  store: create, attach, isolation, rename, drop refused while in use, FORCE
  killing the other session with 57P01, drop of a database with 300 tables
  across chunks, a crash between chunks finished by the next open, reopen) and
  the gen_pg suite `multidb` pass.
- **D3. PostgreSQL door** (parallel with D4, D5, D6). `startup` database
  parameter, aliases, `--strict-databases`, FATAL handling and close on 57P01.
  *Done when* `tests/lexdb/multidb.py --lexdb` matches its recorded PostgreSQL
  answers (9), `psql -l` and `psql -d b -c 'select current_database()'` work,
  and the wire tests that use `dbname=test` still pass without the flag.
- **D4. SQL Server door** (parallel). 3.4 without cross-database rows: names
  with DBSEP/SRVSEP, login database, USE with ENVCHANGE old/new, EXEC revert,
  RESETCONNECTION, T-SQL CREATE/DROP/ALTER DATABASE, `sys.databases`, the
  functions, COLLATE. *Done when* the gen_mssql suite `multidb`
  (`mssql_multidb_queries.txt` to `run/tds_multidb.lxl`) passes against lexdb,
  and sqlcmd `-d b` and the `sqlserver` client's connection string `Database=b`
  land in b (`tds.lxl` `ENV_DATABASE` tracking shows it).
- **D5. Oracle door** (parallel). Services, `#con_name`/`#con_id`, V$PDBS and
  V$CONTAINERS, SET CONTAINER, PL/SQL sources per database. *Done when* the
  gen_oracle suite `multidb` passes and `tests/lexdb/oracledb_multidb.py`
  connects to two services and gets 12514 for a third.
- **D6. Authorisation** (parallel). 4 entire: CREATEDB, owner, database ACL,
  GRANT/REVOKE ON DATABASE, CONNECT/TEMPORARY/CREATE checks, CREATE SCHEMA's
  rule, DROP ROLE across databases, `datacl`, `rolcreatedb`. *Done when* the
  gen_pg suite `multidb_privs` and the CONNECT steps of `multidb.py` pass.
- **D7. T-SQL cross-database reads** (after D4). `catKey` resolves another
  database into `txn.dbCats` and returns `name + DBSEP + key`; `catOf`
  understands that prefix (tree from `txn.dbCats`, key without it) so stats,
  ACLs and index lookups of that table go to its catalog; SELECT, joins,
  subqueries, and INSERT/SELECT INTO with the other database as source work;
  DML or DDL whose target is in another database, and views of another
  database, are 0A000 "lexdb: ... in another database is not supported";
  plans not kept. `OBJECT_ID`/`OBJECT_NAME` with another database. *Done when*
  the `multidb` T-SQL suite's cross-database lines (join of `a.dbo.t` and
  `b.dbo.u`, a missing table 208, a missing database 911) pass.
- **D8. Template copy** (after D2). 3.6. *Done when* `exec_multidb_copy.lxl`
  copies a database of tables, indexes, a view, a sequence mid-way, an enum and
  grants while another session writes to the source, the copy equals the
  snapshot, a crash mid-copy leaves no database after reopening, and a
  cancelled snapshot cleans up.
- **D9. Oracle PDB statements** (after D5, optional). 3.2's Oracle forms
  (superusers only, from any database), ADMIN USER as CREATE USER with CONNECT on
  the new database. *Done when* `oracledb_multidb.py --pdb` creates, opens,
  connects to, closes and drops a PDB on lexdb.
- **D10. Replica, crash, migration, documentation** (last). `replica.py` and
  `crash.py` extended (9), old-directory test, `design/lexdb.md` section 9 entry
  and `design/lexdb-tds.md` / `lexdb-oracle.md` notes that the one-database
  decision is superseded. *Done when* those pass and the docs say what was built.

## 9. Test plan

Recording rules as for the existing suites: answers from the real server, ids,
oids, dates and owners masked; names of databases made by a suite are
prefixed `lexdb_gen_` and dropped at the suite's end, so the oracle is left as
found.

- **PostgreSQL** (`tests/lexdb/gen_pg.py`, PostgreSQL 18 as before):
  - suite `multidb` (`multidb_queries.txt` to `run/exec_multidb_pg.lxl`):
    CREATE DATABASE with each option form, ENCODING 'LATIN1' and 'UTF8', twice
    (42P04), in a block (25001), DROP missing, IF EXISTS (notice), dropping the
    current one (55006), RENAME and OWNER, `current_database()`, a cross-database
    name (0A000) and a same-database one, `select datname, datistemplate,
    datallowconn, datconnlimit from pg_database order by datname`,
    `pg_database_size` of a missing name (3D000). If gen_pg runs a suite's lines
    in one transaction, this suite runs them in autocommit (check before use).
  - suite `multidb_privs`: CREATEDB, NOCREATEDB refused, owner rules, GRANT and
    REVOKE ON DATABASE, `datacl`, `has_database_privilege` (today always true, `lexdb_exec.lxl` near 30083: made real in D6).
  - `tests/lexdb/multidb.py` (new; psql subprocesses as gen_pg uses):
    scripted multi-connection steps run with `--pg "host=... port=... user=..."`
    to record `tests/lexdb/multidb_expect.json` and with `--lexdb PATH` (a
    built lexdb on a fresh DATADIR) to compare: connect to a missing database
    (3D000, with `--strict-databases`), to template0 (55000), ALLOW_CONNECTIONS
    false (55000), CONNECTION LIMIT 1 and a second connection (53300), REVOKE
    CONNECT FROM PUBLIC then a plain role (42501), DROP while another session is
    connected (55006 and the detail), DROP ... WITH (FORCE) then the other
    session's next statement (57P01, connection gone), `psql -l`, `\c`.
    Without the flag: `dbname=test` lands in lexdb.
- **SQL Server** (`tools/mssql_container.sh`, `tests/lexdb/gen_mssql.py`):
  suite `multidb` (`mssql_multidb_queries.txt` to `run/tds_multidb.lxl`):
  CREATE DATABASE (twice: 1801), in a transaction (226), USE and `DB_NAME()`,
  `DB_ID()`, `DB_NAME(DB_ID('x'))`, `HAS_DBACCESS`, USE missing (911),
  `select name from sys.databases where name like 'lexdb_gen%'`, a table in each
  database, `a.dbo.t` and `a..t` reads, a join across two databases (D7 lines),
  a missing table (208), ALTER DATABASE MODIFY NAME, SET SINGLE_USER WITH
  ROLLBACK IMMEDIATE, DROP while used by the same connection (3702), DROP of
  two at once, DROP IF EXISTS. Login database: `tds_multidb.lxl` also opens a
  second connection with `Database=` set (lib/sqlserver) and checks the
  ENVCHANGE it got; by hand `sqlcmd -d`. `tests/lexdb/tds_proxy.py` settles
  RESETCONNECTION's ENVCHANGE.
- **Oracle** (`tools/oracle_container.sh`, `tests/lexdb/gen_oracle.py`, user APP
  in FREEPDB1): suite `multidb`: `SYS_CONTEXT('USERENV', 'CON_NAME' | 'CON_ID' |
  'SERVICE_NAME' | 'DB_NAME' | 'CDB_NAME')`, `select con_id, name, open_mode
  from v$pdbs`, `v$containers`. `tests/lexdb/oracledb_multidb.py`
  (python-oracledb thin): services `lexdb`, `freepdb1`, a created database by its
  name, an unknown one (DPY/ORA-12514), ALTER SESSION SET CONTAINER (lexdb only:
  Oracle's APP lacks the privilege), ORA-65011 and ORA-65023.
- **Migration**: `tests/lexdb/run/exec_oldformats/main.lxl` gains, for
  `fixture78` and `fixture61`: `pg_database` lists lexdb (and the templates),
  `current_database()` is lexdb, CREATE DATABASE b and a table in it, reopen,
  both still there, the old queries' answers unchanged.
- **Replica** (`tests/lexdb/replica.py`): a database created on the master is
  attachable on a replica; its tables read there; DDL refused (25006); DROP on
  the master ends the replica's session in it.
- **Crash** (`tests/lexdb/crash.py`): one client of the load works in a second
  database; after every kill both databases' sums match their committed counts,
  and a kill during a large DROP leaves the database gone after recovery.

## 10. Open decisions (the user's)

- **O1. A PG connection naming an unknown database.** (a) connect to the
  default database, as today, `--strict-databases` for PostgreSQL's FATAL 3D000;
  (b) always strict. Strict is what PostgreSQL does, but every existing client
  and test naming `test`, `x` or its user name would fail after the upgrade,
  and the rule is "an existing DATADIR keeps working with no flag".
  **Recommendation: (a)**, with the flag used by the PG-compatibility tests.
  Its cost: a client relying on the fallback silently moves to a new database
  if one of its name is created later. TDS and TNS stay strict (they are now).
- **O2. The storage model.** B (one store, a catalog tree per database) or A
  (a directory and store per database). **Recommendation: B** (2.1). It gives up
  per-database physical backup and restore, detach/attach, space returned to
  the file system by DROP, and per-database cache budgets; A could still be
  added later as a per-database "file group" if those are wanted.
- **O3. T-SQL cross-database references.** (a) none (0A000); (b) reads (D7);
  (c) reads and DML. **Recommendation: (b) now**, (c) later if an application
  needs it: DML must resolve foreign keys, defaults' sequences and triggers in
  the target's catalog, which D7's prefix makes possible but not free. PG and
  Oracle doors refuse other databases (PostgreSQL does; Oracle needs db links).
- **O4. The default database.** Name `lexdb`, id 5, cannot be dropped or renamed.
  **Recommendation: as stated**; renaming is possible (it is cat 1, not a name)
  but every door's aliases and recorded answer mention it.
- **O5. template1.** Virtual and empty (connections refused) or a real database
  whose objects new databases inherit. **Recommendation: virtual**; a real one
  needs D8's copy on every CREATE and tools rarely change template1.
- **O6. Database collation for T-SQL.** Store `COLLATE` and make it the default
  collation of columns made over TDS in that database, or accept and ignore it.
  **Recommendation: store and use it** (L2 stays per column; this only picks the
  default), so `CREATE DATABASE x COLLATE Latin1_General_BIN2` behaves.
- **O7. Oracle PDB statements (D9).** Build CREATE/DROP/ALTER PLUGGABLE
  DATABASE (from any database, superusers), or offer databases to Oracle only as
  services made through PG or T-SQL. **Recommendation: build D9 last, if wanted**;
  services and SET CONTAINER (D5) cover what applications use.
- **O8. Temporary objects.** Cluster-wide in tree 1 (tempdb semantics, survive
  USE) or per database. **Recommendation: cluster-wide** (5.4): no difference
  for PG and Oracle sessions, SQL Server's behaviour for TDS, and
  `dropLeftTemps` unchanged.
- **O9. `ALTER DATABASE ... SET` defaults.** Apply at attach (as PostgreSQL's
  `pg_db_role_setting`, per database only, not per role and database) or leave
  them out. **Recommendation: apply them** (D2): migrations set `timezone` this way.
