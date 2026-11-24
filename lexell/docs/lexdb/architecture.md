# Architecture, for a user

Where lexdb keeps its data, what a checkpoint is, how it recovers after a crash, and what the cache does. The design
and its measurements are in [design/lexdb.md](../../design/lexdb.md) and [design/lexdb-architecture.md](../../design/lexdb-architecture.md).

## The files

A database is a **data directory** (`DATADIR` on the command line) with:

| File | What it is |
|---|---|
| `data.lxdb` | The data file: pages of 4 KiB holding tables, indexes and the catalog, in B+trees. Every page ends with a checksum, so a corrupt or misplaced page is detected. |
| `log.N` | The write-ahead log, in segments (64 MB by default, `LEXDB_SEG_KB`). `--log-dir` puts them on another device. |
| `lock` | Held by the running server: a second server on the same directory exits ("is in use by another lexdb"). |

There is one catalog in the data file, whatever door made an object. Objects live in schemas: the PostgreSQL and SQL
Server doors work in `public` (`dbo`), and each Oracle login works in a schema of its name, then `public`. A table
reaches the other doors by its schema name (see [overview](overview.md#one-engine-three-doors)).

Memory holds a cache of pages (`--cache-mb`, by default a quarter of the memory) and nothing else that must survive.
The design assumes SSD or NVMe storage.

## A commit

1. The transaction's writes were kept in the session's own memory. At `COMMIT` lexdb checks that nothing the
   transaction read has changed (see [transactions](transactions.md)).
2. The changes are written to the log, and the log is flushed to disk. Commits that arrive together share one write
   and one flush (group commit). The commit is acknowledged after the flush.
3. The changes are applied to the cached pages. The pages are written to the data file later, by a checkpoint.
   If a flush of the data file fails, the server stops and recovers on restart; it does not retry.

`--unsafe-no-sync` skips the flushes. It is for tests only: a power cut can lose or corrupt data.

## Checkpoints

A checkpoint writes the changed pages to **new places** in the data file, then switches one of two meta pages to point
at them. A page that the last checkpoint refers to is never overwritten, so a crash in the middle of a checkpoint
cannot damage the database, and there are no full-page images in the log. A checkpoint is written after about 32 MB
of log (`LEXDB_CKPT_KB`), and when the server stops cleanly.

## Recovery

After a crash lexdb opens the data file at the last checkpoint and **replays the log** from there. Only committed
transactions are in the log, so there is no undo pass. Recovery takes as long as it takes to replay the log written
since the last checkpoint.

## Replicas

A read replica is another process that reads the same data directory and receives the master's log as it is written.
See [replicas](replicas.md).

## See also

[Overview](overview.md), [Server options](server-options.md), [Transactions](transactions.md)
