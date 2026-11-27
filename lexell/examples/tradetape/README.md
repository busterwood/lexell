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
