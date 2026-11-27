#!/usr/bin/env python3
"""End-to-end test for the Lexell + LexDB Live Trade Tape demo.

Compiles lexdb, tradetape, and client_test, starts a fresh LexDB instance and
tradetape server on ephemeral loopback ports with LXL_CHECK=1, runs the HTTP/2
+ SSE + SELECT ... WAIT verification suite, and checks clean shutdown with zero
memory leaks.
"""
import os
import re
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
LXLC = ROOT / "lexell/compiler/out/lxlc"
LIB = ROOT / "lexell/lib"
DEMO = Path(__file__).resolve().parent


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def wait_tcp(host: str, port: int, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"timed out waiting for {host}:{port}")


def compile_lxl(src: Path, out: Path) -> None:
    env = os.environ.copy()
    env["LXL_LIB"] = str(LIB)
    subprocess.run([str(LXLC), str(src), "-o", str(out)], env=env, check=True)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="lexell_tradetape_") as tmp:
        tmp_path = Path(tmp)
        lexdb_bin = tmp_path / "lexdb"
        server_bin = tmp_path / "tradetape"
        client_bin = tmp_path / "client_test"
        data_dir = tmp_path / "data"

        print("Compiling lexdb, tradetape, and client_test...")
        compile_lxl(ROOT / "lexell/cmd/lexdb.lxl", lexdb_bin)
        compile_lxl(DEMO / "main.lxl", server_bin)
        compile_lxl(DEMO / "client_test.lxl", client_bin)

        pg_port = free_port()
        http_port = free_port()

        env = os.environ.copy()
        env["LXL_CHECK"] = "1"

        lexdb_proc = subprocess.Popen(
            [str(lexdb_bin), "--unsafe-no-sync", str(data_dir), f"127.0.0.1:{pg_port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        server_proc = None
        try:
            wait_tcp("127.0.0.1", pg_port, timeout=10.0)
            dsn = f"host=127.0.0.1 port={pg_port} dbname=lexdb user=postgres"

            server_proc = subprocess.Popen(
                [str(server_bin), f"127.0.0.1:{http_port}", "--dsn", dsn, "--wait-sec", "5"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                env=env,
            )
            # Wait for listening line
            line = server_proc.stdout.readline()
            if not line or "listening on" not in line:
                err = server_proc.stderr.read() if server_proc.stderr else ""
                raise RuntimeError(f"tradetape failed to start: stdout={line!r} stderr={err!r}")
            print(f"Server: {line.strip()}")
            wait_tcp("127.0.0.1", http_port, timeout=5.0)

            res = subprocess.run(
                [str(client_bin), f"http://127.0.0.1:{http_port}"],
                env=env,
                capture_output=True,
                text=True,
                timeout=30,
            )
            print(res.stdout, end="")
            if res.stderr:
                print(res.stderr, file=sys.stderr, end="")
            if res.returncode != 0:
                return res.returncode

            srv_out, srv_err = server_proc.communicate(timeout=10)
            if srv_out:
                print(f"Server exit: {srv_out.strip()}")
            if srv_err:
                print(f"Server stderr: {srv_err}", file=sys.stderr)
            if server_proc.returncode != 0:
                print(f"tradetape exited with {server_proc.returncode}", file=sys.stderr)
                return 1
            if "leak" in srv_err.lower() or "leak" in res.stderr.lower():
                print("Memory leak detected under LXL_CHECK=1!", file=sys.stderr)
                return 1
            return 0
        finally:
            if server_proc is not None and server_proc.poll() is None:
                server_proc.send_signal(signal.SIGTERM)
                try:
                    server_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    server_proc.kill()
            if lexdb_proc.poll() is None:
                lexdb_proc.send_signal(signal.SIGTERM)
                try:
                    lexdb_proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    lexdb_proc.kill()


if __name__ == "__main__":
    sys.exit(main())
