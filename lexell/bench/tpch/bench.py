#!/usr/bin/env python3
"""Time TPC-H queries against one running server.

    python3 bench.py --label lexdb --unit tpch-lexdb --port 5598 \
        --user tpch --db tpch --queries queries --out out/lexdb.tsv --runs 3

Each query runs once unrecorded (the warm run), then RUNS times. The wall
time is psql's own \\timing around the statements, so psql's start-up is
outside it (when a query reports no time, the wall around psql is used and
the line says so). The CPU is the server's cgroup: CPUUsageNSec of the
systemd unit the shell started, before and after the psql call.

The output is one TSV line per query, no header:

    name  rows  wall_med  wall_min  wall_max  cpu_med  cpu_min  cpu_max  md5  status

Times are milliseconds. status is ok or error. The shell turns a failed
query into a finding, not a stopped run: the line is still written, with
zeros for the times.

q15 creates and drops the revenue0 view; the view is dropped before every
attempt in case an earlier attempt failed between the two.
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

TIME_RE = re.compile(r"^Time: ([0-9.]+) ms$", re.M)
# psql prints these around a query; they are not result rows. -q suppresses
# most command tags, but not all versions suppress all of them.
NOISE_RE = re.compile(
    r"^(Time: [0-9.]+ ms|Timing is on\.|Timing is off\.|SET|RESET|"
    r"CREATE VIEW|DROP VIEW|CREATE TABLE|DROP TABLE|ANALYZE|VACUUM.*)$"
)


def cpu_ns(unit):
    out = subprocess.check_output(
        ["systemctl", "--user", "show", "-p", "CPUUsageNSec", "--value", unit],
        text=True,
    ).strip()
    return int(out) if out else 0


def parse_result(out):
    """Rows, md5 and the largest psql-reported time in a run."""
    times = [float(x) for x in TIME_RE.findall(out)]
    lines = [line for line in out.splitlines() if not NOISE_RE.match(line)]
    digest = hashlib.md5("\n".join(lines).encode()).hexdigest()
    return len(lines), digest, (max(times) if times else None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--label", required=True)
    ap.add_argument("--unit", required=True)
    ap.add_argument("--port", required=True)
    ap.add_argument("--user", default="tpch")
    ap.add_argument("--db", default="tpch")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--queries", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--runs", type=int, default=3)
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--only", default="", help="query numbers, e.g. 3,5,15")
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
    tmp = os.path.join(os.path.dirname(os.path.abspath(args.out)), "query.sql")
    os.makedirs(os.path.dirname(os.path.abspath(args.out)), exist_ok=True)

    failed = 0
    out = open(args.out, "w")
    print("query\twall_ms\tcpu_ms\trows\tstatus", flush=True)

    for number, path in files:
        name = "q%d" % number
        with open(path) as f:
            sql = f.read()
        with open(tmp, "w") as f:
            f.write("\\timing on\n")
            f.write(sql)
            if not sql.endswith("\n"):
                f.write("\n")

        def run():
            return subprocess.run(
                base + ["-f", tmp],
                capture_output=True,
                text=True,
                timeout=args.timeout,
            )

        def drop_view():
            subprocess.run(
                base + ["-c", "drop view if exists revenue0"],
                capture_output=True,
                text=True,
                timeout=args.timeout,
            )

        def attempt():
            if name == "q15":
                drop_view()
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
        rows = parse_result(warm.stdout)[0]
        digest = parse_result(warm.stdout)[1]
        for _ in range(args.runs):
            try:
                proc, elapsed, cpu = attempt()
            except subprocess.TimeoutExpired:
                error = "timed out after %gs" % args.timeout
                break
            if proc.returncode != 0:
                error = first_line(proc.stderr)
                break
            n, d, reported = parse_result(proc.stdout)
            walls.append(reported if reported is not None else elapsed)
            cpus.append(cpu)
            # The result must be the same on every run; keep the first
            # result's checksum and count in the line.
            if d != digest or n != rows:
                error = "result changed between runs"
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

    out.close()
    try:
        os.unlink(tmp)
    except OSError:
        pass
    if failed:
        print("%s: %d of %d queries failed" % (args.label, failed, len(files)),
              file=sys.stderr)
        return 1
    print("%s: %d queries, %d runs each" % (args.label, len(files), args.runs))
    return 0


def first_line(text):
    text = (text or "").strip()
    return text.splitlines()[0] if text else "psql failed"


if __name__ == "__main__":
    sys.exit(main())
