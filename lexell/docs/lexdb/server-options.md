# Server options

```
lexdb DATADIR [ADDR ...] [--tds HOST:PORT ...] [--tns HOST:PORT ...] [--tcps HOST:PORT ...]
      [--tns-ro-service NAME]
      [--replicas N [--replica-addr ADDR ...] [--replica-tds HOST:PORT ...]
                    [--replica-tns HOST:PORT ...] [--replica-tcps HOST:PORT ...]]
      [--log-dir DIR] [--cache-mb N] [--unsafe-no-sync]
      [--auth trust|scram-sha-256] [--auth-local trust|scram-sha-256]
      [--tls-cert FILE [--tls-key FILE]] [--require-tls]

lexdb --replica DATADIR [ADDR ...] [--tds HOST:PORT ...] [--tns HOST:PORT ...] [--tcps HOST:PORT ...]
      [--tns-ro-service NAME] [--log-dir DIR] [--cache-mb N] [--unsafe-no-sync] [AUTH options]
```

The options may come in any order. An unknown option, or an option without its value, prints the usage and exits
with code 2.

## The common ones

| Option | Default | What it does |
|---|---|---|
| `DATADIR` | (required) | The data directory. Made, with its parents, when it does not exist. |
| `ADDR ...` | `127.0.0.1:5433` | Where the PostgreSQL door listens (see [Addresses](#addresses)). |
| `--tds HOST:PORT` | none | Also listen for SQL Server clients (TDS 7.4) there. SQL Server's own port is 1433. |
| `--tns HOST:PORT` | none | Also listen for Oracle clients (TNS) there. Oracle's own port is 1521. |
| `--cache-mb N` | a quarter of the memory, at least 128 MB | The page cache budget, 1 to 1048576 MB. |
| `--auth METHOD` | `trust` | How TCP logins are checked: `trust` or `scram-sha-256`. |
| `--tls-cert FILE` | none | A PEM certificate (and key, if the file holds it) for TLS in all doors. |
| `--replicas N` | 0 | Run N read-only replicas beside the master (0 to 64). |

A typical server for all three doors:

```sh
lexdb /srv/lexdb 127.0.0.1:5432 --tds 127.0.0.1:1433 --tns 127.0.0.1:1521
```

## Addresses

Each positional `ADDR` after `DATADIR` is one listener of the PostgreSQL door:

- `HOST:PORT`: TCP. `0.0.0.0:5432` listens on every interface.
- an existing directory: a Unix socket in it named as PostgreSQL names one, `.s.PGSQL.PORT`, where PORT is the first TCP address's port (5433 without one). `psql -h DIR -p PORT`
  finds it.
- any other path with a `/`: the Unix socket file itself.

A socket file left by a server that is gone is replaced; one that a live server still answers on is an error. lexdb
removes its socket files when it stops.

`--tds`, `--tns` and `--tcps` take TCP addresses only, and each may be given more than once.

## Doors

| Option | What it does |
|---|---|
| `--tds HOST:PORT` | SQL Server's protocol, TDS 7.4, with T-SQL. lexdb reports itself as SQL Server 2022 (16.0.4315) at login. |
| `--tns HOST:PORT` | Oracle's protocol, TNS with TTC, with Oracle SQL and PL/SQL. The service names `lexdb` and `FREEPDB1` are the database. |
| `--tcps HOST:PORT` | Oracle's protocol inside TLS (TCPS), with the certificate of `--tls-cert`. |
| `--tns-ro-service NAME` | The Oracle service that the master redirects to a replica. Default: `lexdb_ro` and `freepdb1_ro`. See [replicas](replicas.md#oracle). |

The connection pages say how each door logs in and which clients are known to work:
[PostgreSQL](connect/postgresql.md), [SQL Server](connect/sqlserver.md), [Oracle](connect/oracle.md).

## Authentication and TLS

| Option | Default | What it does |
|---|---|---|
| `--auth trust\|scram-sha-256` | `trust` | Logins over TCP. `trust` lets any user name in; `scram-sha-256` checks the role's password. |
| `--auth-local trust\|scram-sha-256` | `trust` | Logins over a Unix socket. |
| `--tls-cert FILE` | none | A PEM certificate chain. With it, every door offers TLS. |
| `--tls-key FILE` | the certificate's file | The PEM private key, when it is not in the certificate's file. |
| `--require-tls` | off | Refuse TCP logins that do not use TLS (Unix socket logins are not affected). |

Under `trust` there are no passwords: keep TCP listeners on loopback, and the socket directory readable only by its
users. A role's password is set with `CREATE ROLE ... PASSWORD` (PostgreSQL door), `CREATE ROLE ... LOGIN PASSWORD`
(SQL Server door, which has no `CREATE LOGIN`) or `CREATE USER ... IDENTIFIED BY` (Oracle door). See [security](security.md).

## Replicas

| Option | Default | What it does |
|---|---|---|
| `--replicas N` | 0 | Run a supervisor with the master and N read-only replicas, each a process of its own. |
| `--replica-addr ADDR` | each master ADDR, port + 1 | The replicas' PostgreSQL listeners. All replicas share them (`SO_REUSEPORT`; one Unix socket). |
| `--replica-tds HOST:PORT` | each `--tds`, port + 1 | The replicas' SQL Server listeners. |
| `--replica-tns HOST:PORT` | each `--tns`, port + 1 | The replicas' Oracle listeners. |
| `--replica-tcps HOST:PORT` | each `--tcps`, port + 1 | The replicas' Oracle TCPS listeners. |
| `--replica` | | Run one replica by hand, of a master already serving `DATADIR`. It takes `ADDR` (default `127.0.0.1:5434`), `--tds`, `--tns` and `--tcps` for its own listeners. |

A door the master does not serve, the supervised replicas do not serve either. A replica started with `--replica`
serves only the doors it is given. See [replicas](replicas.md).

## Storage

| Option | Default | What it does |
|---|---|---|
| `--cache-mb N` | a quarter of the memory, at least 128 MB | The cache budget of each process (master and every replica), 1 to 1048576 MB. Beats `LEXDB_CACHE_MB`. |
| `--log-dir DIR` | the data directory | Keep the write-ahead log segments in DIR, for example on another device. Fixed when the database is made. |
| `--unsafe-no-sync` | off | **For tests only.** Never call `fdatasync` or `fsync`. A clean stop keeps everything; a power cut or kernel crash can lose or corrupt data. Prints a warning. |

`--log-dir` is checked at every start: a data directory made with a log directory is refused without `--log-dir` or
with another database's log directory, and one made without it is refused with it. `--replica` and `--replicas`
need the same `--log-dir` as the master.

## Environment variables

| Variable | Default | What it does |
|---|---|---|
| `LEXDB_CACHE_MB` | as `--cache-mb` | The cache budget in MB; `--cache-mb` wins. |
| `LEXDB_AUTOANALYZE` | on | `off`: no automatic statistics. `ANALYZE` still works. |
| `LEXDB_SEG_KB` | 65536 (64 MB) | A log segment's size in KB. |
| `LEXDB_CKPT_KB` | 32768 (32 MB) | The log written between checkpoints, in KB. |
| `LEXDB_LOG_DSYNC` | 1 | `0`: write the log and then `fdatasync` it, in place of `O_DSYNC` writes. |
| `LXL_HELPERS` | 32 | The runtime's file reads in flight. |

## Running and stopping

- lexdb prints a line per listener as it starts, for example:

  ```
  lexdb: listening on 127.0.0.1:5433, data in /srv/lexdb
  lexdb: TDS (SQL Server) on 127.0.0.1:1433
  lexdb: TNS (Oracle) on 127.0.0.1:1521
  ```

- One server per data directory. A second lexdb on the same `DATADIR` exits with code 1 ("is in use by another
  lexdb") while the first holds `DATADIR/lock`.
- `SIGTERM` or `SIGINT` stops it: no new connections, the open ones are cut off, a checkpoint is written, and it
  prints a line of statistics before it exits.
- Exit codes: 0 after a clean stop; 1 when it cannot start (the data directory in use, a store that will not open, a
  listener that will not bind); 2 for a bad command line. Under `--replicas`, a master that cannot start is not
  restarted; the supervisor stops with code 1.
- lexdb runs in the foreground and logs to standard output and standard error. Use your service manager (systemd,
  a container) to run it in the background.
