#!/usr/bin/env python3
"""Benchmark N=10, 100, 500, 1000 concurrent SSE waiters on tradetape + LexDB.

Measures idle CPU, active fan-out CPU, RSS (VmHWM), POST latency, and SSE wake
latency (p50/p95/p99/max) for both broadcast ("all") and 20-symbol ("sharded")
workloads.
"""
import os
import resource
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

DEMO = Path(__file__).resolve().parent
ROOT = DEMO.parents[2]
LXLC = ROOT / "lexell/compiler/out/lxlc"
LIB = ROOT / "lexell/lib"
CLK_TCK = os.sysconf(os.sysconf_names["SC_CLK_TCK"])


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_tcp(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.03)
    raise RuntimeError(f"timeout waiting for {host}:{port}")


def proc_cpu_ms(pid: int) -> float:
    with open(f"/proc/{pid}/stat") as f:
        s = f.read()
    rest = s[s.rfind(")") + 2:].split()
    return (int(rest[11]) + int(rest[12])) * 1000.0 / CLK_TCK


def proc_rss_mb(pid: int) -> tuple[float, float]:
    rss = hwm = 0.0
    with open(f"/proc/{pid}/status") as f:
        for line in f:
            if line.startswith("VmRSS:"):
                rss = int(line.split()[1]) / 1024.0
            elif line.startswith("VmHWM:"):
                hwm = int(line.split()[1]) / 1024.0
    return rss, hwm


def compile_opt(src: Path, out: Path) -> None:
    env = os.environ.copy()
    env["LXL_LIB"] = str(LIB)
    subprocess.run([str(LXLC), "-O", str(src), "-o", str(out)], env=env, check=True)


def run_case(lexdb_bin: Path, srv_bin: Path, bench_bin: Path, n: int, trades: int, mode: str) -> None:
    with tempfile.TemporaryDirectory(prefix=f"lexbench_{n}_") as tmp:
        pg_port = free_port()
        http_port = free_port()
        data_dir = Path(tmp) / "data"

        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
        resource.setrlimit(resource.RLIMIT_NOFILE, (min(hard, max(soft, 16384)), hard))

        lexdb_proc = subprocess.Popen(
            [str(lexdb_bin), "--unsafe-no-sync", str(data_dir), f"127.0.0.1:{pg_port}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        srv_proc = None
        try:
            wait_tcp("127.0.0.1", pg_port)
            dsn = f"host=127.0.0.1 port={pg_port} dbname=lexdb user=postgres"
            srv_proc = subprocess.Popen(
                [str(srv_bin), f"127.0.0.1:{http_port}", "--dsn", dsn, "--wait-sec", "15"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            line = srv_proc.stdout.readline()
            if "listening on" not in line:
                raise RuntimeError(f"srv failed: {line!r} {srv_proc.stderr.read()!r}")
            wait_tcp("127.0.0.1", http_port)

            bp = subprocess.Popen(
                [str(bench_bin), f"http://127.0.0.1:{http_port}", str(n), str(trades), mode],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
            )
            ready_line = bp.stdout.readline().strip()
            t_idle0 = time.monotonic()
            db_cpu_idle0 = proc_cpu_ms(lexdb_proc.pid)
            srv_cpu_idle0 = proc_cpu_ms(srv_proc.pid)

            _idle_line = bp.stdout.readline().strip()
            t_idle1 = time.monotonic()
            db_cpu_idle1 = proc_cpu_ms(lexdb_proc.pid)
            srv_cpu_idle1 = proc_cpu_ms(srv_proc.pid)

            res_line = bp.stdout.readline().strip()
            t_burst1 = time.monotonic()
            db_cpu_end = proc_cpu_ms(lexdb_proc.pid)
            srv_cpu_end = proc_cpu_ms(srv_proc.pid)
            db_rss, db_hwm = proc_rss_mb(lexdb_proc.pid)
            srv_rss, srv_hwm = proc_rss_mb(srv_proc.pid)

            bp.wait(timeout=15)
            berr = bp.stderr.read().strip()
            if berr:
                print(f"  bench stderr: {berr}", file=sys.stderr)

            idle_wall_ms = (t_idle1 - t_idle0) * 1000.0
            burst_wall_ms = (t_burst1 - t_idle1) * 1000.0
            db_idle_pct = 100.0 * (db_cpu_idle1 - db_cpu_idle0) / max(1.0, idle_wall_ms)
            srv_idle_pct = 100.0 * (srv_cpu_idle1 - srv_cpu_idle0) / max(1.0, idle_wall_ms)
            db_burst_ms = db_cpu_end - db_cpu_idle1
            srv_burst_ms = srv_cpu_end - srv_cpu_idle1
            db_burst_pct = 100.0 * db_burst_ms / max(1.0, burst_wall_ms)
            srv_burst_pct = 100.0 * srv_burst_ms / max(1.0, burst_wall_ms)

            print(f"\n=== N={n} mode={mode} ({ready_line}) ===")
            print(f"  {res_line}")
            print(
                f"  IDLE (1s parked):   lexdb={db_idle_pct:5.2f}% CPU ({db_cpu_idle1-db_cpu_idle0:.1f}ms) | "
                f"tradetape={srv_idle_pct:5.2f}% CPU ({srv_cpu_idle1-srv_cpu_idle0:.1f}ms)"
            )
            print(
                f"  BURST ({trades} trades): lexdb={db_burst_ms:6.1f}ms CPU ({db_burst_pct:5.1f}% of 1 core, {db_burst_ms/trades:.1f}ms/trade) | "
                f"tradetape={srv_burst_ms:6.1f}ms CPU ({srv_burst_pct:5.1f}% of 1 core, {srv_burst_ms/trades:.1f}ms/trade)"
            )
            print(
                f"  MEMORY:             lexdb RSS={db_rss:.1f}MB (HWM {db_hwm:.1f}MB) | "
                f"tradetape RSS={srv_rss:.1f}MB (HWM {srv_hwm:.1f}MB)"
            )
        finally:
            if srv_proc is not None and srv_proc.poll() is None:
                srv_proc.send_signal(signal.SIGTERM)
                try:
                    srv_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    srv_proc.kill()
            if lexdb_proc.poll() is None:
                lexdb_proc.send_signal(signal.SIGTERM)
                try:
                    lexdb_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    lexdb_proc.kill()


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="lexbench_bins_") as btmp:
        b = Path(btmp)
        lexdb_bin = b / "lexdb"
        srv_bin = b / "tradetape"
        bench_bin = b / "bench_waiters"
        print("Compiling -O binaries (lexdb, tradetape, bench_waiters)...")
        compile_opt(ROOT / "lexell/cmd/lexdb.lxl", lexdb_bin)
        compile_opt(DEMO / "main.lxl", srv_bin)
        compile_opt(DEMO / "bench_waiters.lxl", bench_bin)

        for n in [10, 100, 500, 1000]:
            run_case(lexdb_bin, srv_bin, bench_bin, n, 5, "all")
        for n in [100, 1000]:
            run_case(lexdb_bin, srv_bin, bench_bin, n, 5, "sharded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
