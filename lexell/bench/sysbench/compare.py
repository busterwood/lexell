#!/usr/bin/env python3
"""Render sysbench OLTP comparison markdown from lexdb.tsv, lexdb3.tsv, pg.tsv."""
import argparse
import os
import sys


def read_tsv(path):
    rows = {}
    order = []
    if not os.path.exists(path):
        return rows, order
    with open(path) as f:
        hdr = f.readline().strip().split("\t")
        for line in f:
            parts = line.strip().split("\t")
            if len(parts) < len(hdr):
                continue
            d = dict(zip(hdr, parts))
            key = (d["test"], int(d["threads"]))
            rows[key] = {
                "tps": float(d["tps"]),
                "qps": float(d["qps"]),
                "avg_ms": float(d["avg_ms"]),
                "p95_ms": float(d["p95_ms"]),
                "errors": int(d["errors"]),
                "cpu_us_tx": float(d["cpu_us_tx"]),
                "cpu_us_q": float(d["cpu_us_q"]),
            }
            order.append(key)
    return rows, order


def fmt_ratio(a, b):
    if b <= 0:
        return "—"
    return f"{a / b:.2f}×"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--tables", type=int, default=4)
    ap.add_argument("--table-size", type=int, default=250000)
    ap.add_argument("--seconds", type=int, default=10)
    args = ap.parse_args()

    l1, ord1 = read_tsv(os.path.join(args.out_dir, "lexdb.tsv"))
    l3, ord3 = read_tsv(os.path.join(args.out_dir, "lexdb3.tsv"))
    pg, ordp = read_tsv(os.path.join(args.out_dir, "pg.tsv"))

    keys = []
    for src in (ord1, ordp, ord3):
        for k in src:
            if k not in keys:
                keys.append(k)

    print(f"# sysbench OLTP ({args.tables} tables × {args.table_size:,} rows, {args.seconds}s per run)\n")
    print("Throughput in transactions/sec (higher favours lexdb); p95 latency in ms and server CPU in µs/tx (lower favours lexdb).")
    print("Note: every lexdb transaction block runs at `SERIALIZABLE` isolation; PostgreSQL runs at its default `READ COMMITTED`.\n")

    print("## LexDB (1 process) vs PostgreSQL (4 cores)\n")
    print("| workload | threads | lexdb TPS | PG TPS | TPS ratio | lexdb p95 (ms) | PG p95 (ms) | lexdb CPU µs/tx | PG CPU µs/tx | CPU ratio | lexdb err | PG err |")
    print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
    for k in keys:
        test, th = k
        a = l1.get(k)
        b = pg.get(k)
        if not a and not b:
            continue
        atps = f"{a['tps']:,.0f}" if a else "—"
        btps = f"{b['tps']:,.0f}" if b else "—"
        tr = fmt_ratio(a["tps"], b["tps"]) if (a and b) else "—"
        ap95 = f"{a['p95_ms']:.2f}" if a else "—"
        bp95 = f"{b['p95_ms']:.2f}" if b else "—"
        acpu = f"{a['cpu_us_tx']:.1f}" if a else "—"
        bcpu = f"{b['cpu_us_tx']:.1f}" if b else "—"
        cr = fmt_ratio(a["cpu_us_tx"], b["cpu_us_tx"]) if (a and b) else "—"
        aerr = str(a["errors"]) if a else "—"
        berr = str(b["errors"]) if b else "—"
        print(f"| {test} | {th} | {atps} | {btps} | {tr} | {ap95} | {bp95} | {acpu} | {bcpu} | {cr} | {aerr} | {berr} |")

    if l3:
        print("\n## LexDB (3 read replicas, 4 processes) vs PostgreSQL (4 cores) — Read Workloads\n")
        print("| workload | threads | lexdb3 TPS | PG TPS | TPS ratio | lexdb3 p95 (ms) | PG p95 (ms) | lexdb3 CPU µs/tx | PG CPU µs/tx | CPU ratio |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
        for k in keys:
            if k not in l3:
                continue
            test, th = k
            a = l3[k]
            b = pg.get(k)
            btps = f"{b['tps']:,.0f}" if b else "—"
            tr = fmt_ratio(a["tps"], b["tps"]) if b else "—"
            bp95 = f"{b['p95_ms']:.2f}" if b else "—"
            bcpu = f"{b['cpu_us_tx']:.1f}" if b else "—"
            cr = fmt_ratio(a["cpu_us_tx"], b["cpu_us_tx"]) if b else "—"
            print(f"| {test} | {th} | {a['tps']:,.0f} | {btps} | {tr} | {a['p95_ms']:.2f} | {bp95} | {a['cpu_us_tx']:.1f} | {bcpu} | {cr} |")


if __name__ == "__main__":
    main()
