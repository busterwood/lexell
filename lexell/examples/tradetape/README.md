# Live Trade Tape — Lexell + LexDB (`SELECT ... WAIT`) + HTTP/2 SSE Demo

A self-contained demo hooking Lexell's HTTP/1.1 & HTTP/2 server directly to **LexDB** over the PostgreSQL wire protocol, streaming live Server-Sent Events (SSE) using LexDB's `SELECT ... WAIT` clause—with **no polling**, **no message broker**, and **no database connection pool**.

## Two Streaming Architectures (`--mode hub` vs `--mode direct`)

The server supports both patterns so you can compare them directly:

1. **`--mode hub` (default, production pattern — [hub.lxl](hub.lxl)):**
   - **One** background task per process holds **one dedicated LexDB connection** running a prepared `SELECT ... WHERE seq > $1 ORDER BY seq LIMIT 64 WAIT 10 SECONDS`.
   - Each committed trade wakes that single relay task immediately and fans out in memory via `lib/sse.lxl` (`sse.Feed`) to an all-symbols feed plus lazy per-symbol feeds.
   - Reconnecting clients within the 64-event ring buffer resume from memory (`Last-Event-ID`); older cursors run a one-shot LexDB catch-up query and hand off seamlessly to the live feed without gaps or duplicates.
   - Scales to thousands of concurrent HTTP/2 SSE subscribers with **$O(1)$ database load** (~23 MB constant LexDB RSS, 0 DB connections per SSE client), and works across multiple worker processes (`task.workers`) because every worker tails LexDB independently.
2. **`--mode direct` (minimal 1-to-1 pattern — `handleStreamDirect` in [main.lxl](main.lxl)):**
   - Each `GET /api/stream` subscriber opens its own dedicated LexDB connection (`postgres.connect` + `conn.setCloseOnCancel(true)`), prepares `SELECT ... WAIT` once, and keeps it open until the HTTP/1.1 or HTTP/2 stream closes.
   - Zero hub code and < 5 ms p99 latency up to ~100–200 concurrent streams.

## Endpoints

- `GET /`: single-page live browser dashboard ([ui.lxl](ui.lxl)) embedded in the native binary.
- `POST /api/trades`: decodes JSON via derived `Deserialize`, validates exact 38-digit `Decimal` prices (`numeric(14, 4)` in LexDB), commits in a serializable transaction (`UPDATE seq_counter ... RETURNING n`, retrying on `40001`), and returns `201 Created`.
- `GET /api/stream[?symbol=EURUSD&after=0]`: long-lived SSE stream (`RouteOpts{deadlineMs: 0}`) supporting `Last-Event-ID` resume and keep-alive comments.
- `GET /api/trades[?symbol=...&limit=50]`: JSON snapshot with automatic `zstd`/`gzip`/`deflate` compression (`httpserver.compress`).
- `GET /api/trades/export.csv[?format=excel|pg|tsv]`: CSV/TSV export via `lib/csv.lxl`.
- `GET /api/stats` & `POST /api/shutdown`: live stream/request stats and graceful drain.

## Build & Run

From the repository root (after `lexell/compiler/build.sh`):

```sh
# 1. Build LexDB and the tradetape demo
LXL_LIB=lexell/lib lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -o /tmp/lexdb
LXL_LIB=lexell/lib lexell/compiler/out/lxlc lexell/examples/tradetape/main.lxl -o /tmp/tradetape

# 2. Start LexDB on port 5433
/tmp/lexdb /tmp/tradetape-data 127.0.0.1:5433 &

# 3. Start the web server (HTTP/1.1 + HTTP/2 h2c on port 8080, --mode hub by default)
/tmp/tradetape 127.0.0.1:8080 --dsn "host=127.0.0.1 port=5433 dbname=lexdb user=postgres"

# Or run the direct 1-connection-per-client mode:
/tmp/tradetape 127.0.0.1:8080 --mode direct --dsn "host=127.0.0.1 port=5433 dbname=lexdb user=postgres"
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

Tests **both** `--mode hub` and `--mode direct` under `LXL_CHECK=1` (HTTP/2 SSE wakeup, per-symbol filtering, disconnect cleanup, `Last-Event-ID` resume, compressed JSON, CSV export, and zero leaks):

```sh
python3 lexell/examples/tradetape/test_e2e.py
```

## Scaling & Waiter Latency (`bench_waiters.py`)

Measured with `-O` native builds of `lexdb` (`--unsafe-no-sync`), `tradetape`, and `bench_waiters.lxl` (multiplexed HTTP/2 `h2c` SSE clients, 0 errors across all runs; Ryzen 7 8745HS, Linux 7.2). Both modes sit at **0.00% idle CPU** while parked.

```sh
python3 lexell/examples/tradetape/bench_waiters.py
```

### Broadcast fan-out (`GET /api/stream`, every trade wakes all `N` waiters)

| Server mode | Waiters (`N`) | Connect all `N` | Wake p50 | Wake p99 | `lexdb` CPU / trade | `tradetape` CPU / trade | `lexdb` RSS | `tradetape` RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `direct` | 100 | 73 ms | 2.9 ms | 4.0 ms* | 4.0 ms | 4.0 ms | 35.1 MB | 20.3 MB |
| `direct` | 500 | 129 ms | 7.7 ms | 15.1 ms | 20.0 ms | 10.0 ms | 84.5 MB | 62.4 MB |
| `direct` | 1,000 | 207 ms | 12.1 ms | 23.8 ms | 36.0 ms | 18.0 ms | 146.2 MB | 109.1 MB |
| **`hub`** | **100** | **52 ms** | **2.3 ms** | **10.8 ms*** | **< 1 ms** | **< 1 ms** | **22.8 MB** | **11.1 MB** |
| **`hub`** | **500** | **60 ms** | **3.4 ms** | **6.8 ms** | **< 1 ms** | **4.0 ms** | **22.7 MB** | **15.1 MB** |
| **`hub`** | **1,000** | **56 ms** | **5.3 ms** | **12.1 ms** | **≤ 2.0 ms** | **4.0 ms** | **22.8 MB** | **19.3 MB** |
| **`hub`** | **2,000** | **85 ms** | **9.0 ms** | **22.5 ms** | **< 1 ms** | **6.0 ms** | **22.8 MB** | **29.6 MB** |

*\*First-write cold latency occasionally reflects initial WAL segment allocation (~40 ms on `POST` #1); steady-state `POST` p50 is 1.5–1.9 ms across all runs.*

### Sharded by symbol (`GET /api/stream?symbol=SYMxx`, 20 symbols, `N/20` match each trade)

| Server mode | Waiters (`N`) | Matching | Wake p50 | Wake p99 | `lexdb` CPU / trade | `tradetape` CPU / trade | `lexdb` RSS | `tradetape` RSS |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| `direct` | 100 | 5 | 2.8 ms | 3.0 ms | < 1 ms | < 1 ms | 34.8 MB | 20.6 MB |
| `direct` | 1,000 | 50 | 13.1 ms | 14.0 ms | 14.0 ms | 2.0 ms | 142.3 MB | 119.9 MB |
| **`hub`** | **100** | **5** | **1.7 ms** | **1.9 ms** | **≤ 2.0 ms** | **< 1 ms** | **22.8 MB** | **11.4 MB** |
| **`hub`** | **1,000** | **50** | **2.0 ms** | **2.2 ms** | **≤ 2.0 ms** | **2.0 ms** | **22.8 MB** | **26.5 MB** |
| **`hub`** | **2,000** | **100** | **2.3 ms** | **3.0 ms** | **≤ 2.0 ms** | **2.0 ms** | **22.8 MB** | **42.6 MB** |

### Summary

- At **`N = 1,000` broadcast**, switching from `direct` to `hub` cuts **`lexdb` CPU by ~18×** (36 ms → ≤ 2 ms/trade), **`lexdb` RSS by 6.4×** (146 MB → 22.8 MB, completely flat regardless of `N`), **`tradetape` RSS by 5.7×** (109 MB → 19.3 MB), and **halves p50/p99 wake latency** (12.1 → 5.3 ms p50).
- At **`N = 2,000` sharded**, per-symbol `sse.Feed` routing keeps wake latency at **2.3 ms p50 / 3.0 ms p99** with only **22.8 MB** in `lexdb` and **42.6 MB** in `tradetape`, because non-matching symbol subscribers never wake at all.
