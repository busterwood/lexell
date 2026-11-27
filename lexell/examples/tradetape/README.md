# Live Trade Tape — Lexell + LexDB (`SELECT ... WAIT`) + HTTP/2 SSE Demo

A self-contained demo hooking Lexell's HTTP/1.1 & HTTP/2 server directly to **LexDB** over the PostgreSQL wire protocol, streaming live Server-Sent Events (SSE) using LexDB's `SELECT ... WAIT` clause—with **no polling**, **no message broker**, and **no database connection pool**.

## What it demonstrates

- **LexDB `SELECT ... WAIT` over PostgreSQL wire protocol** ([main.lxl](main.lxl)):
  - Every `GET /api/stream` subscriber opens **one dedicated LexDB connection** (`postgres.connect`), prepares the waiting query once (`conn.prepare`), and loops on `SELECT ... WHERE seq > $1 ORDER BY seq LIMIT 64 WAIT 10 SECONDS` (or `WHERE symbol = $2 AND seq > $1` using the `(symbol, seq)` composite index).
  - The dedicated connection stays open for the lifetime of the HTTP/1.1 or HTTP/2 stream and closes automatically via RAII (`drop()`) as soon as the client disconnects.
  - Posting a trade via `POST /api/trades`—or inserting directly from `psql`—commits to LexDB and immediately wakes every waiting SSE subscriber.
- **HTTP/1.1 + HTTP/2 (`h2c` & optional TLS ALPN `h2`)** via `httpserver`:
  - `POST /api/trades`: decodes JSON via compiler-derived `Deserialize`, validates exact 38-digit `Decimal` prices (`numeric(14, 4)` in LexDB), commits in a serializable transaction with `UPDATE seq_counter ... RETURNING n` (retrying on `40001`), and returns `201 Created`.
  - `GET /api/stream[?symbol=EURUSD&after=0]`: long-lived SSE stream (`RouteOpts{deadlineMs: 0}`) supporting `Last-Event-ID` catch-up and keep-alive comments.
  - `GET /api/trades[?symbol=...&limit=50]`: JSON snapshot with automatic `zstd`/`gzip`/`deflate` compression (`httpserver.compress`).
  - `GET /api/trades/export.csv[?format=excel|pg|tsv]`: streaming CSV/TSV export via `lib/csv.lxl`.
  - `GET /`: single-page live browser dashboard ([ui.lxl](ui.lxl)) embedded directly in the native executable.

## Build & Run

From the repository root (after `lexell/compiler/build.sh`):

```sh
# 1. Build LexDB and the tradetape demo
LXL_LIB=lexell/lib lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -o /tmp/lexdb
LXL_LIB=lexell/lib lexell/compiler/out/lxlc lexell/examples/tradetape/main.lxl -o /tmp/tradetape

# 2. Start LexDB on port 5433
/tmp/lexdb /tmp/tradetape-data 127.0.0.1:5433 &

# 3. Start the web server (HTTP/1.1 + HTTP/2 h2c on port 8080)
/tmp/tradetape 127.0.0.1:8080 --dsn "host=127.0.0.1 port=5433 dbname=lexdb user=postgres"
```

Open `http://127.0.0.1:8080` in a browser, or drive it over **HTTP/2 (`h2c`)** from two terminals:

```sh
# Terminal 1: stream live trades over HTTP/2 SSE
curl -N --http2-prior-knowledge "http://127.0.0.1:8080/api/stream"

# Terminal 2: post a trade over HTTP/2 (wakes Terminal 1 immediately)
curl --http2-prior-knowledge -X POST http://127.0.0.1:8080/api/trades \
  -H 'Content-Type: application/json' \
  -d '{"symbol":"EURUSD","side":"BUY","price":"1.0845","qty":10000,"note":"desk-1"}'

# Or insert directly via psql—Terminal 1 still wakes up immediately!
psql "host=127.0.0.1 port=5433 dbname=lexdb user=postgres" -c \
  "BEGIN; UPDATE seq_counter SET n = n + 1 WHERE id = 'trades'; INSERT INTO trades SELECT n, 'GBPUSD', 'SELL', 1.2650, 5000, 'from-psql', 0 FROM seq_counter WHERE id = 'trades'; COMMIT;"
```

For **HTTPS with HTTP/2 ALPN**, pass `--tls-cert cert.pem --tls-key key.pem`.

## End-to-End Test

Run the automated end-to-end suite (compiles `lexdb`, `tradetape`, and `client_test`, runs live HTTP/2 SSE wakeup, symbol filtering, disconnect cleanup, `Last-Event-ID` resume, compressed JSON, and CSV export under `LXL_CHECK=1`):

```sh
python3 lexell/examples/tradetape/test_e2e.py
```

## Scaling & Waiter Latency (`bench_waiters.py`)

Measured with `-O` native builds of `lexdb` (`--unsafe-no-sync`), `tradetape`, and `bench_waiters.lxl` (multiplexed HTTP/2 `h2c` SSE clients, each holding a dedicated LexDB `SELECT ... WAIT 15 SECONDS` connection, 0 errors across all 8,325 deliveries; Ryzen 7 8745HS, Linux 7.2):

```sh
python3 lexell/examples/tradetape/bench_waiters.py
```

### Idle (all `N` waiters parked in `SELECT ... WAIT`)

**0.00% CPU** (0.0 ms) on both `lexdb` and `tradetape` from `N = 10` through `N = 1,000` waiters—no polling and no timer churn.

### Broadcast fan-out (`GET /api/stream`, every trade wakes all `N` waiters)

| Waiters (`N`) | Connect all `N` | `POST` p50 | Wake p50 | Wake p95 | Wake p99 | Wake max | `lexdb` CPU / trade | `tradetape` CPU / trade | `lexdb` RSS | `tradetape` RSS |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 10 | 51 ms | 1.5 ms | 1.8 ms | 2.1 ms | 2.1 ms | 2.1 ms | 2.0 ms | < 1 ms | 23.0 MB | 10.7 MB |
| 100 | 73 ms | 2.0 ms | 3.4 ms | 4.7 ms | 4.9 ms | 5.0 ms | 4.0 ms | 4.0 ms | 35.1 MB | 20.7 MB |
| 500 | 119 ms | 1.7 ms | 8.0 ms | 15.1 ms | 17.4 ms | 17.9 ms | 18.0 ms | 10.0 ms | 84.6 MB | 63.5 MB |
| 1,000 | 206 ms | 1.8 ms | 19.2 ms | 45.4 ms | 48.7 ms | 49.9 ms | 46.0 ms | 24.0 ms | 146.2 MB | 108.6 MB |

### Sharded by symbol (`GET /api/stream?symbol=SYMxx`, 20 symbols, `N/20` match each trade)

| Waiters (`N`) | Matching | Wake p50 | Wake p99 | `lexdb` CPU / trade | `tradetape` CPU / trade | `lexdb` RSS | `tradetape` RSS |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 100 | 5 | 3.0 ms | 3.1 ms | 2.0 ms | < 1 ms | 34.7 MB | 21.1 MB |
| 1,000 | 50 | 14.2 ms | 56.4 ms | 16.0 ms | 2.0 ms | 142.3 MB | 119.9 MB |

### Architectural takeaways

- **Linear $O(N)$ fan-out:** Each broadcast waiter costs ~46 µs in `lexdb` (index re-probe + PG wire encode) and ~24 µs in `tradetape` (PG decode + JSON encode + HTTP/2 DATA frame), with ~125 KB/waiter RSS in `lexdb` and ~100 KB/waiter in `tradetape` (mostly `pgwire`'s 64 KiB read inbox).
- **Direct dedicated `SELECT ... WAIT` per client** is clean and fast up to a few hundred concurrent streams (< 5 ms p99 at `N = 100`, 4 ms CPU per commit).
- **Table-level wakeup on sharded streams:** In the `N = 1,000` sharded test, `tradetape` CPU drops 12× (24 ms → 2 ms/trade), while `lexdb` CPU drops 3× (46 ms → 16 ms/trade, ~16 µs per non-matching waiter) because LexDB currently wakes every waiter on the `trades` table on commit so each re-probes the `(symbol, seq)` index and re-parks.
- **Scaling to 1,000–10,000+ subscribers on a high-write table:** Run a single background `SELECT ... WAIT` reader task feeding `lib/sse.lxl` (`sse.Feed`) in memory—LexDB then holds 1 waiter instead of `N`, cutting database CPU and memory by ~`N`× while keeping zero polling and no external broker.
