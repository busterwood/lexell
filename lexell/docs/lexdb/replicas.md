# Read replicas

A replica is a read-only lexdb process that follows a master on the same machine. Replicas add cores for reads: each
replica is a process with its own SQL thread, and the master's single SQL thread is left for writes.

## How they work

- **Same machine, same data directory.** A replica reads the master's data file and log directly; nothing is copied.
  The master and its replicas talk over a Unix socket in the data directory (`repl.sock`).
- **The log is pushed.** After each commit's flush the master sends the new log frames to every replica, and each
  replica applies them in memory. The log files are read only to catch up (at start, or after falling far behind).
- **Durable commits only.** A replica sees a commit only after the master has made it durable, never before.
- **Lag.** A commit is visible on a replica about 0.1 ms after the master acknowledges it when idle, and under 1.1 ms
  at the 99th percentile under load (16,700 updates/s on the master and 220,000 selects/s on three replicas;
  design/lexdb.md 9.135).
- **Snapshots.** Every statement, and every read-only transaction, on a replica reads one consistent state of the
  database: the commits applied when it began.
- **Checkpoints are held.** The master does not reuse pages or log a replica still reads; each replica tells the
  master what it holds.
- **Writes are refused**, in each door with the product's own error for a read-only secondary. In the SQL Server
  door, `#temp` tables and table variables work on a replica, as on a readable secondary (below).

## Starting replicas

### Under one command: --replicas N

```sh
lexdb ./data 127.0.0.1:5432 --tds 127.0.0.1:1433 --tns 127.0.0.1:1521 --replicas 2
```

```
lexdb: supervising a master and 2 replicas of ./data
lexdb: listening on 127.0.0.1:5432, data in ./data
lexdb: TDS (SQL Server) on 127.0.0.1:1433
lexdb: TNS (Oracle) on 127.0.0.1:1521
lexdb: replica listening on 127.0.0.1:5433, following the master of ./data
lexdb: replica listening on 127.0.0.1:5433, following the master of ./data
lexdb: replica TDS (SQL Server) on 127.0.0.1:1434
lexdb: replica TDS (SQL Server) on 127.0.0.1:1434
lexdb: replica TNS (Oracle) on 127.0.0.1:1522
lexdb: replica TNS (Oracle) on 127.0.0.1:1522
```

- A supervisor process runs the master and N replicas (1 to 64), each a process of its own.
- **Addresses.** By default the replicas listen on each of the master's addresses with the port one higher, for
  every door the master serves. `--replica-addr`, `--replica-tds`, `--replica-tns` and `--replica-tcps` give other
  addresses. All replicas share each address: TCP ports with `SO_REUSEPORT` (the kernel spreads connections), and one
  Unix socket that every replica accepts from.
- **Restarts.** A replica that ends badly is started again. When the master ends badly, the supervisor starts it
  again, and the replicas with it. A master that cannot start at all (its data directory refused, a port taken) is not
  restarted: the supervisor stops with exit code 1.
- `SIGTERM` or `SIGINT` to the supervisor stops them all.

### By hand: --replica

```sh
lexdb ./data 127.0.0.1:5432 --tds 127.0.0.1:1433 --tns 127.0.0.1:1521      # the master
lexdb --replica ./data 127.0.0.1:6432 --tds 127.0.0.1:2433 --tns 127.0.0.1:2521
```

`--replica DATADIR` follows the master already serving DATADIR. It takes its own listeners; a door it is not given,
it does not serve (without any address it serves PostgreSQL on 127.0.0.1:5434). It waits up to 10 seconds for the
master to be there, and ends when the master stops. Several may run at once.

Options that apply to the data directory apply to replicas too: a master made with `--log-dir` needs the same
`--log-dir` for `--replica`. Each replica has its own cache (`--cache-mb`).

## Reading your own writes: WAIT FOR LSN

lexdb's LSN is the number of the master's last group commit, written as PostgreSQL writes an LSN (`0/0000002A`). In
the PostgreSQL door:

- `pg_current_wal_lsn()` on the master gives its last durable commit;
- `pg_last_wal_replay_lsn()` and `pg_last_wal_receive_lsn()` on a replica give the last one it has applied;
- `WAIT FOR LSN 'lsn' [WITH (TIMEOUT ..., NO_THROW)]` (PostgreSQL 19) on a replica waits until it has applied that
  commit.

A program that writes on the master and then must read the write on a replica takes `pg_current_wal_lsn()` after its
commit and runs `WAIT FOR LSN` on the replica before reading. The SQL Server and Oracle products have no such
statement, and lexdb adds none to those doors.

## PostgreSQL

A replica's PostgreSQL door answers as a PostgreSQL hot standby:

- writes and DDL give 25006 "cannot execute INSERT in a read-only transaction";
- `CREATE TEMP TABLE` gives 25006 too, as on a standby;
- `pg_is_in_recovery()` is true; `SHOW transaction_read_only` and `in_hot_standby` are `on`;
- `default_transaction_read_only` is `on` (a standby set up with it in `postgresql.conf` says the same), and it is
  sent at login with `in_hot_standby`, so clients know a replica without a query.

**Routing.** PostgreSQL's protocol has no redirect: the client chooses. libpq (psql, psycopg) takes a list of hosts
and `target_session_attrs`; pgjdbc takes `targetServerType`:

| Client | Master | Replica |
|---|---|---|
| libpq | `target_session_attrs=read-write` or `primary` | `standby`, `read-only` or `prefer-standby` |
| pgjdbc | `targetServerType=primary` | `targetServerType=secondary` or `preferSecondary` |

```
host=127.0.0.1,127.0.0.1 port=5432,5433 dbname=lexdb target_session_attrs=standby
jdbc:postgresql://127.0.0.1:5432,127.0.0.1:5433/lexdb?targetServerType=secondary&binaryTransfer=false
```

Both were checked: libpq (psql 18.6) and pgjdbc 42.7.14 each picked the replica for `standby` / `secondary` and the
master for `read-write` / `primary`, whichever host came first in the list.

A session, with a master on port 25540 and its replicas on 25541 (psql 18.6):

```
$ psql -h 127.0.0.1 -p 25540 -U postgres lexdb -c "CREATE TABLE acct (id int PRIMARY KEY, owner text, balance numeric(12,2))" \
       -c "INSERT INTO acct VALUES (1, 'ann', 100.00), (2, 'bob', 50.00)" -c "SELECT pg_current_wal_lsn()"
CREATE TABLE
INSERT 0 2
 pg_current_wal_lsn
--------------------
 0/00000004
(1 row)

$ psql -h 127.0.0.1 -p 25541 -U postgres lexdb -c "SELECT pg_is_in_recovery(), pg_last_wal_replay_lsn()" \
       -c "SHOW transaction_read_only" -c "SELECT * FROM acct ORDER BY id"
 pg_is_in_recovery | pg_last_wal_replay_lsn
-------------------+------------------------
 t                 | 0/00000004
(1 row)

 transaction_read_only
-----------------------
 on
(1 row)

 id | owner | balance
----+-------+---------
  1 | ann   |  100.00
  2 | bob   |   50.00
(2 rows)

$ psql -h 127.0.0.1 -p 25541 -U postgres lexdb -c "UPDATE acct SET balance = 0 WHERE id = 1"
ERROR:  cannot execute UPDATE in a read-only transaction

$ psql -h 127.0.0.1 -p 25541 -U postgres lexdb -c "CREATE TEMP TABLE t (a int)"
ERROR:  cannot execute CREATE TABLE in a read-only transaction

$ # on the master: INSERT INTO acct VALUES (3, 'cy', 10.00); SELECT pg_current_wal_lsn() gave 0/00000005
$ psql -h 127.0.0.1 -p 25541 -U postgres lexdb -c "WAIT FOR LSN '0/00000005' WITH (TIMEOUT '1s')" -c "SELECT count(*) FROM acct"
 status
---------
 success
(1 row)

 count
-------
     3
(1 row)

$ psql -h 127.0.0.1 -p 25541 -U postgres lexdb -c "WAIT FOR LSN 'FFFF/00000000' WITH (TIMEOUT 100, NO_THROW)"
 status
---------
 timeout
(1 row)

$ psql "host=127.0.0.1,127.0.0.1 port=25540,25541 user=postgres dbname=lexdb target_session_attrs=standby" -c "SELECT pg_is_in_recovery()"
 pg_is_in_recovery
-------------------
 t
(1 row)

$ psql "host=127.0.0.1,127.0.0.1 port=25541,25540 user=postgres dbname=lexdb target_session_attrs=read-write" -c "SELECT pg_is_in_recovery()"
 pg_is_in_recovery
-------------------
 f
(1 row)
```

## SQL Server

A replica's SQL Server door answers as a readable secondary of an availability group:

- writes and DDL on tables give error 3906, severity 16: `Failed to update database "lexdb" because the database is
  read-only.`;
- `DATABASEPROPERTYEX('lexdb', 'Updateability')` is `READ_ONLY`, and `sys.databases.is_read_only` is 1;
- **`#temp` tables, `SELECT ... INTO #t` and table variables work**, as they do on a secondary, where they live in
  tempdb: `CREATE TABLE`, `DROP TABLE`, `INSERT`, `UPDATE`, `DELETE`, `MERGE`, `TRUNCATE`, `ALTER TABLE` and `CREATE
  INDEX`, when every table they write is a `#name` or a table variable (they may read the replicated tables). Each
  session's temporary tables are kept in the replica's memory, never reach the master's log, and are dropped when
  the session ends.

**Routing.** A client that logs in to the master with `ApplicationIntent=ReadOnly` is sent to a replica, as SQL
Server's read-only routing sends it: the master's login answer carries a routing message (ENVCHANGE 20) naming a
replica's address, and the driver connects there. Replicas are given round robin. With no replica running, the
master serves the session itself, as SQL Server falls back to the primary. A replica serves every login, read-only
intent or not.

| Client | Option |
|---|---|
| ADO.NET, Microsoft.Data.SqlClient | `ApplicationIntent=ReadOnly` |
| ODBC, sqlcmd | `ApplicationIntent=ReadOnly`; sqlcmd `-K ReadOnly` |
| mssql-jdbc | `applicationIntent=ReadOnly` |
| Lexell `sqlserver` | `ApplicationIntent=ReadOnly` |

```
$ # mssql-jdbc 13.6.2 to the master's port, applicationIntent=ReadOnly: routed to a replica
SELECT DATABASEPROPERTYEX('lexdb', 'Updateability') AS updateability;
SELECT name, is_read_only FROM sys.databases WHERE name = 'lexdb';
UPDATE acct SET balance = 0 WHERE id = 1;

updateability
-------------
READ_ONLY

(1 row affected)

name  is_read_only
----- ------------
lexdb 1

(1 row affected)

Msg 3906, Level 16, State 1, Line 1
Failed to update database "lexdb" because the database is read-only.

$ # the same without applicationIntent: the master
updateability
-------------
READ_WRITE

(1 row affected)

name  is_read_only
----- ------------
lexdb 0

(1 row affected)

(1 row affected)
```

T-SQL's temporary objects on a replica (mssql-jdbc, `applicationIntent=ReadOnly` to the master, so on a replica;
built from main f8e3d6d6):

```
CREATE TABLE #recent (id int PRIMARY KEY, owner nvarchar(40));
INSERT INTO #recent SELECT id, owner FROM dbo.acct WHERE balance > 0;
DECLARE @t TABLE (id int);
INSERT INTO @t SELECT id FROM #recent;
SELECT count(*) AS n FROM @t;
SELECT id, owner INTO #copy FROM #recent;
UPDATE #copy SET owner = UPPER(owner);
SELECT * FROM #copy ORDER BY id;

(2 rows affected)

(2 rows affected)

n
-
2

(1 row affected)

(2 rows affected)

id owner
-- -----
1  ANN
2  BOB

(2 rows affected)
```

## Oracle

A replica's Oracle door answers as an Active Data Guard physical standby:

- DML, DDL, `CREATE SEQUENCE` and `SELECT ... FOR UPDATE` give `ORA-16000: Attempting to modify database or
  pluggable database that is open for read-only access.`;
- `V$DATABASE` shows `OPEN_MODE` `READ ONLY WITH APPLY` and `DATABASE_ROLE` `PHYSICAL STANDBY` (the master:
  `READ WRITE`, `PRIMARY`);
- `CREATE GLOBAL TEMPORARY TABLE` gives ORA-16000, as on a standby.
- **DML on a global temporary table is not available on a replica.** An Active Data Guard standby allows it for a
  table the primary defined. In lexdb a global temporary table's definition belongs to the session that made it, on
  the master too (it is not shared with other sessions, as Oracle's is), so a replica's session never has one
  ([known issues](KNOWN-ISSUES.md)).

**Routing.** A client that connects to the master's listener with the read-only service name is redirected to a
replica, as a listener redirects a client to a service that a standby runs (Data Guard's role-based services). The
read-only service names are `lexdb_ro` and `freepdb1_ro` (any case), or the one `--tns-ro-service` gives. With no
replica running, the master refuses the service with ORA-12514, as for a role-based service that runs nowhere. A
replica's own listener takes the plain and the read-only names.

```
User Id=sa;Password=sa;Data Source=127.0.0.1:1521/lexdb_ro          (Lexell, python-oracledb: 127.0.0.1:1521/lexdb_ro)
```

**ojdbc does not follow the redirect yet**: a JDBC thin connection to the master with `lexdb_ro` fails in the driver
with TNS-04605 ([known issues](KNOWN-ISSUES.md)). Point JDBC clients at a replica's own listener
(`jdbc:oracle:thin:@//127.0.0.1:1522/lexdb`) until then.

```
$ # Lexell's oracle module (tests/lexdb/doorsql.lxl) to the master's port, service lexdb_ro: redirected to a replica
$ doorsql tns "User Id=sa;Password=sa;Data Source=127.0.0.1:25560/lexdb_ro" "SELECT open_mode || ' / ' || database_role FROM v\$database"
'READ ONLY WITH APPLY / PHYSICAL STANDBY'
$ doorsql tns "User Id=sa;Password=sa;Data Source=127.0.0.1:25560/lexdb_ro" "INSERT INTO public.acct VALUES (9, 'zed', 1)"
error 16000: ORA-16000: Attempting to modify database or pluggable database that is open for read-only access.

$ # ojdbc 23.26.4 to a replica's own port, service lexdb
SELECT open_mode, database_role FROM v$database;
INSERT INTO public.acct VALUES (9, 'zed', 1);

OPEN_MODE            DATABASE_ROLE
-------------------- ----------------
READ ONLY WITH APPLY PHYSICAL STANDBY

1 row selected.

ERROR:
ORA-16000: Attempting to modify database or pluggable database that is open for read-only access.
```

```
$ # ojdbc 23.26.4 to a replica's own port
CREATE GLOBAL TEMPORARY TABLE work_ids (id NUMBER) ON COMMIT PRESERVE ROWS;

ERROR:
ORA-16000: Attempting to modify database or pluggable database that is open for read-only access.
```

TCPS redirects (`--tcps` with `--replica-tcps`) are built but not yet tested.

## Watching replicas

| Door | On the master | On a replica |
|---|---|---|
| PostgreSQL | `pg_current_wal_lsn()`, `pg_is_in_recovery()` = false | `pg_last_wal_replay_lsn()`, `pg_is_in_recovery()` = true |
| SQL Server | `DATABASEPROPERTYEX('lexdb','Updateability')` = READ_WRITE | READ_ONLY, `sys.databases.is_read_only` = 1 |
| Oracle | `V$DATABASE`: READ WRITE, PRIMARY | READ ONLY WITH APPLY, PHYSICAL STANDBY |

`pg_wal_lsn_diff(master_lsn, replica_lsn)` counts group commits, not bytes.

## Limits

- Replicas run on the master's machine. Replicas on other machines are not built.
- There is no failover: a replica is never promoted. The supervisor restarts a master that crashes.
- `BEGIN READ WRITE` and `SET TRANSACTION READ WRITE` on a replica are accepted (`transaction_read_only` stays `on`)
  and the writes then fail with 25006; PostgreSQL refuses the statement itself (0A000).
- The LSN functions give text: lexdb has no `pg_lsn` type.
