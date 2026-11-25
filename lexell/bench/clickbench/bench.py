#!/usr/bin/env python3
"""Time ClickBench queries against one running server.

    python3 bench.py --label lexdb --unit cb-lexdb --port 5594 \
        --user cb --db cb --queries queries --out out/lexdb.tsv --runs 3

Each query runs once unrecorded (the warm run), then RUNS times. Wall time
comes from psql's \\timing; server CPU comes from systemd cgroup CPUUsageNSec.
Output is one TSV line per query:

    name  rows  wall_med  wall_min  wall_max  cpu_med  cpu_min  cpu_max  md5  status
"""
import argparse
import hashlib
import os
import re
import shutil
import statistics
import subprocess
import sys
import time

TIME_RE = re.compile(r"^Time: ([0-9.]+) ms(?: \([0-9:.]+\))?$", re.M)
NOISE_RE = re.compile(r"^(Timing is on\.|Timing is off\.|SET|RESET)$")


def cpu_ns(unit):
    try:
        out = subprocess.check_output(
            ["systemctl", "--user", "show", "-p", "CPUUsageNSec", "--value", unit],
            text=True,
        ).strip()
        return int(out) if out.isdigit() else 0
    except (subprocess.CalledProcessError, FileNotFoundError):
        return 0


def parse_result(path):
    try:
        with open(path, "rb") as f:
            raw = f.read().decode("utf-8", errors="replace")
            lines = [line for line in raw.splitlines() if not NOISE_RE.match(line)]
    except FileNotFoundError:
        return 0, hashlib.md5(b"").hexdigest()
    return len(lines), hashlib.md5("\n".join(lines).encode("utf-8")).hexdigest()


def first_line(text):
    text = (text or "").strip()
    return text.splitlines()[0] if text else "psql failed"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--port", required=True)
    ap.add_argument("--user", default="cb")
    ap.add_argument("--db", default="cb")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--queries", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=300)
    ap.add_argument("--only", default="", help="query numbers, e.g. 0,1,28")
    ap.add_argument("--pre", default="", help="SQL before each query (e.g. SET)")
    args = ap.parse_args()

    if args.runs < 1:
        raise SystemExit("--runs must be at least 1")

    psql = shutil.which("psql")
    if not psql:
        raise SystemExit("psql is not on PATH")

    only = set()
    if args.only:
        for part in args.only.replace(",", " ").split():
            only.add(part[1:] if part.startswith("q") else part)

    files = []
    for name in os.listdir(args.queries):
        m = re.fullmatch(r"q([0-9]+)\.sql", name)
        if m and (not only or m.group(1) in only):
            files.append((int(m.group(1)), os.path.join(args.queries, name)))
    files.sort()
    if not files:
        raise SystemExit("no q*.sql files in " + args.queries)

    base = [
        psql, "-X", "-q", "-A", "-t", "-v", "ON_ERROR_STOP=1",
        "-h", args.host, "-p", args.port, "-U", args.user, "-d", args.db,
    ]
    outdir = os.path.dirname(os.path.abspath(args.out))
    os.makedirs(outdir, exist_ok=True)
    tmp = os.path.join(outdir, "query.sql")
    result = "result.txt"
    result_path = os.path.join(outdir, result)

    failed = 0
    out = open(args.out, "w")
    print("query\twall_ms\tcpu_ms\trows\tstatus", flush=True)

    for number, path in files:
        name = "q%d" % number
        with open(path) as f:
            sql = f.read()
        with open(tmp, "w") as f:
            f.write("\\timing on\n")
            if args.pre:
                f.write(args.pre)
                if not args.pre.endswith("\n"):
                    f.write("\n")
            f.write("\\o " + result + "\n")
            f.write(sql)
            if not sql.endswith("\n"):
                f.write("\n")
            f.write("\\o\n")

        def run():
            try:
                os.unlink(result_path)
            except OSError:
                pass
            return subprocess.run(
                base + ["-f", tmp],
                capture_output=True,
                text=True,
                timeout=args.timeout,
                cwd=outdir,
            )

        def attempt():
            before = cpu_ns(args.unit)
            started = time.perf_counter()
            proc = run()
            elapsed = (time.perf_counter() - started) * 1000
            after = cpu_ns(args.unit)
            return proc, elapsed, max(0, after - before) / 1e6

        try:
            warm, _, _ = attempt()
        except subprocess.TimeoutExpired:
            warm = None
            error = "warm run timed out after %gs" % args.timeout
        else:
            error = None if warm.returncode == 0 else first_line(warm.stderr)

        if error:
            failed += 1
            print("%-4s  FAIL  %s" % (name, error), flush=True)
            out.write("%s\t0\t0\t0\t0\t0\t0\t0\t-\terror\n" % name)
            out.flush()
            continue

        walls, cpus = [], []
        rows, digest = parse_result(result_path)
        for _ in range(args.runs):
            try:
                proc, elapsed, cpu = attempt()
            except subprocess.TimeoutExpired:
                error = "timed out after %gs" % args.timeout
                break
            if proc.returncode != 0:
                error = first_line(proc.stderr)
                break
            times = [float(x) for x in TIME_RE.findall(proc.stdout)]
            n, d = parse_result(result_path)
            walls.append(max(times) if times else elapsed)
            cpus.append(cpu)
            if n != rows:
                error = "row count changed between runs (%d vs %d)" % (rows, n)
                break
        else:
            if not walls:
                error = "no timed runs"
            else:
                s = "%s\t%d\t%.1f\t%.1f\t%.1f\t%.2f\t%.2f\t%.2f\t%s\tok" % (
                    name, rows,
                    statistics.median(walls), min(walls), max(walls),
                    statistics.median(cpus), min(cpus), max(cpus),
                    digest,
                )
                print("%-4s  %9.1f ms  %8.2f ms cpu  %5d rows  %s" % (
                    name, statistics.median(walls), statistics.median(cpus),
                    rows, digest[:8],
                ), flush=True)
                out.write(s + "\n")
                out.flush()
                continue

        failed += 1
        print("%-4s  FAIL  %s" % (name, error), flush=True)
        out.write("%s\t%d\t0\t0\t0\t0\t0\t0\t%s\terror\n" % (name, rows, digest))
        out.flush()

    out.close()
    for path in (tmp, result_path):
        try:
            os.unlink(path)
        except OSError:
            pass
    if failed:
        print("%s: %d of %d queries failed" % (args.label, failed, len(files)),
              file=sys.stderr)
        return 1
    print("%s: %d queries, %d runs each" % (args.label, len(files), args.runs))
    return 0


if __name__ == "__main__":
    sys.exit(main())
