# One connection pool for every client

Status: agreed with the user (2026-11-09). Stages 1 to 4 are built on
branch `pool`: `lib/pool.lxl` with its test `pool_fake`, then postgres,
redis, sqlserver and oracle on it (sections 7 to 10). Stage 5, sqlserver's
cleanup after a cancelled request, is next.

## 1. Why

`postgres` has a pool (`newPool`, `Pool`, `Lease`, `PoolStats`, `handOn`), and
`redis` has a copy of it with the names unchanged. `sqlserver` and `oracle`
have none, and TDS stage T3 (design/tds.md) needs one, both for the load test
and for cleaning up a connection after a cancelled request (decision D2
there). Four copies of the same waiting and handoff code would drift apart, so
the pool becomes one generic module that each client plugs into.

Lexell has no interface values (SPEC section 13), but its interfaces work as
constraints and may have associated functions (SPEC 5.4). That is enough: the
pool is generic over the connection type, and each instance is compiled for
its client.

## 2. The interface

```lxl
// What a connection type gives the pool. Cfg is what it opens from, E its error.
pub type Pooled[Cfg, E] = interface {
    fn open(cfg: &Cfg, w: Where): Result[Self, E]     // associated: Conn.open
    fn waitFailed(why: task.Cancelled): E             // acquire's error when its wait ends
    fn (mut &Self) release(): bool                    // given back: no I/O; false closes it
    fn (mut &Self) reuse(w: Where): Result[Unit, E]   // before an idle one is handed out
}

pub type Pool[C: Pooled[Cfg, E], Cfg, E]              // a copy handle: stats(), acquire(w)
pub type Lease[C: Pooled[Cfg, E], Cfg, E]             // conn(): mut &C; gives it back when dropped
pub type PoolStats = value record { pub open: int; pub idle: int; pub waiting: int }
pub fn newPool[C: Pooled[Cfg, E], Cfg, E](cfg: Cfg, size: int): Pool[C, Cfg, E]
```

A client adds the four members to its `Conn` and aliases the instance. A
program never writes the type arguments:

```lxl
pub type Pool = pool.Pool[Conn, Settings, Error]
pub type Lease = pool.Lease[Conn, Settings, Error]
pub type PoolStats = pool.PoolStats

// Parses once: a bad string is an error here, not at the first acquire.
pub fn newPool(connStr: str, size: int): Result[Pool, Error] {
    let st = try parseConnString(connStr)
    return Ok(pool.newPool[Conn, Settings, Error](st, size))
}
```

`Where` reaches `open` and `reuse` explicitly: a call through a constraint
cannot supply it implicitly (SPEC section 15), so `acquire` passes its own.

### Why two hooks and not `idle()`

The pool used to ask one question, `idle()`, when a lease was dropped. There
are really two moments, and they allow different things:

- **`release()`** runs in a lease's `drop`, often in a task whose deadline has
  just passed or that was cancelled. That task cannot do I/O, so `release`
  only decides whether the connection may be kept, and may mark it (to be
  reset, or to be settled).
- **`reuse(w)`** runs in the task that acquires an idle connection. That task
  is healthy, so `reuse` may do I/O: finish a cleanup that `release` could
  not, or check that the connection is still alive. An `Err` closes the
  connection, and `acquire` opens a new one in its place; the error itself is
  not reported.

This answers design/tds.md's D2 (who cleans up after a cancellation) as it
recommended, the next user, with no runtime change.

| client | `release()` | `reuse(w)` |
|---|---|---|
| postgres | `idle()` | `Ok`; later the alive check of pgwire-stages P4 |
| sqlserver | `idle()`, or true when the only problem is a cancelled request whose reply is unread; marks RESETCONNECTION (section 5) | sends ATTENTION and reads the rest of that reply (T3); the reset goes out with the next request |
| oracle | `idle()` (not broken; a statement outside `transaction[T]` commits with its execute, so a lease is never dropped inside a transaction) | `idle()`; later a ping after the connection has been idle a while |
| redis | `idle()` (no MULTI, not in subscribe mode, not broken) | `Ok` |

## 3. How it works

The algorithm is postgres's, unchanged: `acquire` takes an idle connection,
or takes a place and opens one while fewer than `size` are open, or else
queues a promise and parks on its future. `handOn` gives a connection, or a
place (None), to the first waiter, or else keeps it idle or frees the place.
A waiter whose wait ends (deadline or cancellation) leaves the queue; if it
was already served, what came was dropped with its future and goes on to the
next waiter. A failed open gives its place on, so a task queued behind it
opens its own.

Two things are new:

- **The configuration is a `task.Frozen[Cfg]`, outside the `Shared` state.**
  `open` parks, and a task may not park inside `Shared.with` (exit 13).
  Postgres copied its conninfo string out of the state first, but an
  arbitrary `Cfg` cannot be copied. `Frozen.read` may park, so `open` runs
  inside it.
- **A connection that `release()` refuses is dropped (closed) before its
  place goes on**, so a server's connection limit never sees size + 1.

## 4. Decisions (agreed 2026-11-09)

- **D1. What a Lease exposes:** `l.conn()`, a `mut &Conn`, and nothing else.
  `try l.conn().query(...)`. A generic `Lease` cannot have the clients'
  methods (methods are declared only in the type's own module). Forwarding
  methods in a wrapper record per client were the alternative; they would
  keep today's `l.query(...)` but need one method per call in every client
  (postgres's lease forwards 5 today, redis's 7, and each new call on `Conn`
  would need one more). This changes the callers of postgres's and redis's
  leases (section 6).
- **D2. `newPool` returns `Result`** in every client: the string is parsed
  once, when the pool is made. postgres's `newPool` cannot fail today, so a
  bad conninfo shows only at the first `acquire`; redis's already returns a
  Result.
- **D3. The module is `pool`**, not `dbpool`: redis is not SQL.
- **D4. Not now:** an idle timeout, a maximum lifetime and a minimum number of
  idle connections. Each is one change in `pool.lxl` for every client when it
  is needed.

## 5. Open questions

- **Resetting session state.** SQL Server's RESETCONNECTION (a status bit on
  the next request, no round trip) clears temp tables, SET options and the
  database a `USE` chose, as ADO.NET's pool does. Postgres's pool resets
  nothing (DISCARD ALL would cost a round trip), and Oracle has no cheap
  reset. Should the clients agree here, or should each do what its server
  makes cheap? To be decided with sqlserver's stage (6.4).
- **The reuse error.** `reuse`'s `Err` is dropped silently. A count in
  `PoolStats` (`replaced`) would make a server that keeps dropping idle
  connections visible. Not needed yet.

## 6. Stages

| stage | contents | done when |
|---|---|---|
| 1 (built) | `lib/pool.lxl`; `pool_fake`: a scripted connection type, no server | built (2026-11-09): passes on both backends under LXL_CHECK=1 |
| 2 (built) | postgres on `pool`: `Conn.open` from a `pgwire.Config`, `waitFailed` with the errors of today (`E_TIMEOUT`, `E_CANCELLED`, "pool: timeout while waiting for a connection"), `release` = `idle()`, `reuse` = `Ok`; its pool code removed; callers on `l.conn()` and `newPool`'s Result: `cmd/httpd.lxl`, the doc comment in `lib/httpserver.lxl`, `task_postgres_pool`, `postgres_live_stream` | the live postgres tests and `http_gate --db` unchanged |
| 3 (built) | redis on `pool`, its copy removed; `redis_basic`, `redis_live` on `l.conn()` | the redis tests pass |
| 4 (built) | sqlserver and oracle: the four members, the aliases, `newPool`; `sqlserver_live_pool`, `oracle_live_pool` (the shape of `task_postgres_pool`) | the live tests pass on both backends |
| 5 | sqlserver T3: a cancelled request leaves the connection unsettled, not broken; `release` keeps it, `reuse` settles it with ATTENTION; RESETCONNECTION (section 5) | a cancelled query's connection is reused, not reopened, in a live test |

## 7. Stage 1, as built (2026-11-09)

- The shape is accepted as written: `E` appears only in the constraints of
  `Pool` and `Lease`, not in a field, and the instances are named explicitly
  (`pool.newPool[Fake, Cfg, Error]`). The prototype risk noted when this was
  proposed did not happen.
- `pool_fake` covers: eight tasks on a pool of two (never more than two open,
  two opened in all); a waiter's deadline (waitFailed's error, the queue left
  empty); an idle connection handed out again; `release` refusing (closed, a
  new one); `reuse` failing (closed, a new one); a failed open (its place
  freed); a failed open while another task waits for the place (the waiter
  opens its own); and every connection closed once the pools are gone.
- Not covered by a test: a waiter cancelled after it was already served. The
  code path is postgres's, unchanged.

## 8. Stage 2, as built: postgres (2026-11-09)

- `postgres.lxl` lost its pool code (662 lines to 521): `Pool`, `Lease` and
  `PoolStats` are aliases of `pool`'s, and `Conn` gained `open` (which
  `connect` now calls after parsing), `waitFailed` (the errors and text of
  before: `E_TIMEOUT` 1021 or `E_CANCELLED` 1020, "pool: timeout while
  waiting for a connection"), `release` (`idle()`) and `reuse` (`idle()`
  again: an idle connection that went bad is replaced, as before).
- `newPool` returns `Result` (D2); `cmd/httpd.lxl` reports a bad
  `LXL_PG_DSN` and exits 1, as `cmd/database-example.md` now shows.
- Callers moved to `l.conn()` (D1): `cmd/httpd.lxl`,
  `cmd/database-example.md`, `task_postgres_pool`, `postgres_live_stream`,
  `http_server_pg_cancel`, the httpserver example in lib/README.md.
  `lib/httpserver.lxl`'s comment calls only `acquire()` and is unchanged.
  The libpq oracle (`lib/tests/support/postgres_libpq.lxl`) keeps its own
  copy of the old pool.
- Tests: the postgres, pool and `http_server_pg_cancel` tests pass live on
  the C backend under LXL_CHECK=1 and on the native backend (12 of 12),
  `task_postgres_pool`'s expected lines unchanged. `http_gate.py --servers
  native,c --db 4,16 --seconds 2` passes (nobody waiting after the
  shutdown, no leak); requests/s on `/db` are at or above PERFORMANCE.md's
  in every row (pool 16, 100 clients: 22,963 native and 25,049 C against
  21,217). One short run each, on a machine whose numbers move 1% to 8%
  between runs: no slowdown, not a measured speedup.

## 9. Stage 3, as built: redis (2026-11-09)

- `redis.lxl` lost its copy of the pool (1,530 lines to 1,380). `Pool`,
  `Lease` and `PoolStats` are aliases of `pool`'s over `Config`; `newPool`
  and `newPoolWith` keep their signatures. `Conn.open` is `connectWith`,
  `waitFailed` gives `Kind.Timeout` or `Kind.Cancelled` with the text of
  before, `release` and `reuse` are `idle()` (no MULTI open, not broken).
- The six commands the lease forwarded (`command`, `get`, `set`, `del`,
  `hget`, `hset`) are gone (D1): `l.conn().set(...)`. `conn()` was already
  there. `redis_basic` and `redis_live` are moved.
- Tests: `redis_basic` (a scripted server, a pool shared by six tasks) and
  `pool_fake` pass on both backends under LXL_CHECK=1, and so do
  `redis_live` and `redis_live_extra` against a live Redis 7
  (`redis:7-alpine` in podman, `LXL_REDIS_LIVE=1`; run 2026-11-09 after
  stage 4).
- Still as before: a subscribed connection is not detected. `Conn` does
  not track subscribe mode, so a lease dropped while subscribed goes back
  to the pool. Tracking it would let `release` refuse it; a follow-up.

## 10. Stage 4, as built: sqlserver and oracle (2026-11-09)

- Both clients gained the same section after `close()` (43 lines each):
  the aliases over their `Settings`, `newPool(connStr, size)` returning a
  Result, and the four members: `open` is `connectWith` (Connect Timeout
  applies to each open), `waitFailed` gives `E_TIMEOUT` or `E_CANCELLED`
  with postgres's text, `release` and `reuse` are `idle()`. Nothing else
  in either client changed.
- sqlserver's `idle()` is false while a stream is unfinished, so a lease
  dropped with a stream still open is closed, not settled. Settling it
  (ATTENTION in `reuse`) is stage 5.
- oracle: a lease cannot be left inside a transaction. Every statement
  outside `transaction[T]` commits with its execute (the `inTransaction()`
  of a plain INSERT is false), and inside one the body has the connection
  borrowed. So `oracle_live_pool` tests a broken lease instead (`logoff()`,
  then a failing call), which `release` refuses.
- Tests: `sqlserver_live_pool` and `oracle_live_pool`, the shape of
  `task_postgres_pool`: eight tasks on a pool of two (never more than two
  open), a waiter's deadline, the same session handed out again, a lease
  that is not idle closed and a new session opened, a string that does
  not parse (E_INPUT at `newPool`), a server that cannot be reached (no
  place kept), no handle left. A session is told apart by `@@SPID` and its
  `login_time` (SQL Server) or SID and serial (Oracle), as a server may
  give a closed session's id to the next one. Neither prints the
  connection string or a connect message. Both pass live on the C backend
  under LXL_CHECK=1 (four runs) and on the native backend.
