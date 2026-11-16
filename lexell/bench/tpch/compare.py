#!/usr/bin/env python3
"""Compare the TSVs written by bench.py and the loads from run.sh.

    python3 compare.py OUTDIR [REFDIR]

Reads OUTDIR/lexdb.tsv, pg1.tsv and pg4.tsv (any may be missing), and
OUTDIR/load-lexdb.tsv and load-pg.tsv. Writes OUTDIR/summary.md and prints
the same text.

The check column compares lexdb's rows and checksum with PostgreSQL's
(pg1.tsv). A lexdb-only run has none of its own: REFDIR names an earlier
run's directory whose pg1.tsv is used for the check only (not for times).
Without either, a query that ran says "ran, unchecked", not "ok".

Ratios are lexdb over PostgreSQL: below 1 favours lexdb for both times and
load seconds. Wall is the median of the timed runs; CPU is the server's
cgroup over the same runs.
"""
import os
import statistics
import sys


def load_queries(path):
    rows = {}
    if not os.path.exists(path):
        return rows
    for line in open(path):
        if not line.strip():
            continue
        f = line.rstrip("\n").split("\t")
        if len(f) < 10:
            continue
        rows[f[0]] = {
            "rows": int(f[1]),
            "wall": float(f[2]),
            "cpu": float(f[5]),
            "md5": f[8],
            "status": f[9],
        }
    return rows


def load_tables(path):
    tables = {}
    if not os.path.exists(path):
        return tables
    for line in open(path):
        if not line.strip():
            continue
        f = line.rstrip("\n").split("\t")
        if len(f) < 3:
            continue
        tables[f[0]] = (int(f[1]), int(f[2]))
    return tables


def gm(xs):
    xs = [x for x in xs if x > 0]
    return statistics.geometric_mean(xs) if xs else float("nan")


def ratio(a, b):
    return a / b if b else float("nan")


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: compare.py OUTDIR [REFDIR]")
    outdir = sys.argv[1]
    lex = load_queries(os.path.join(outdir, "lexdb.tsv"))
    pg1 = load_queries(os.path.join(outdir, "pg1.tsv"))
    pg4 = load_queries(os.path.join(outdir, "pg4.tsv"))
    if not (lex or pg1 or pg4):
        raise SystemExit("no lexdb.tsv, pg1.tsv or pg4.tsv in " + outdir)
    # the results lexdb's are checked against: this run's PostgreSQL, or
    # a reference run's
    ref = pg1
    refnote = ""
    if not ref and len(sys.argv) == 3:
        ref = load_queries(os.path.join(sys.argv[2], "pg1.tsv"))
        if not ref:
            raise SystemExit("no pg1.tsv in " + sys.argv[2])
        refnote = "Checked against PostgreSQL's results in %s.\n" % sys.argv[2]

    names = sorted(set(lex) | set(pg1) | set(pg4), key=lambda q: int(q[1:]))
    lines = []
    lines.append("# TPC-H (derived, unaudited)\n")
    lines.append("Times in milliseconds; ratios are lexdb / PostgreSQL "
                 "(below 1 favours lexdb).\n")
    if refnote:
        lines.append(refnote)
    lines.append("| query | lexdb wall | PG 1 core wall | ratio | "
                 "lexdb CPU | PG CPU | ratio | PG 4 proc wall | ratio | check |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")

    wall_ratios, cpu_ratios, wall4_ratios = [], [], []
    level = 0
    failed = 0
    different = 0
    unchecked = 0
    for q in names:
        l, g, g4 = lex.get(q), pg1.get(q), pg4.get(q)
        r = ref.get(q)
        status = "ok"
        if (l and l["status"] != "ok") or (g and g["status"] != "ok") or (g4 and g4["status"] != "ok"):
            status = "fail"
            failed += 1
        elif l and r and r["status"] == "ok" and (l["rows"] != r["rows"] or l["md5"] != r["md5"]):
            status = "different result"
            different += 1
        elif l and not (r and r["status"] == "ok"):
            # nothing to check lexdb's result against: it ran, no more
            status = "ran, unchecked"
            unchecked += 1
        usable = (l and g and l["status"] == "ok" and g["status"] == "ok")
        if usable:
            r = ratio(l["wall"], g["wall"])
            wall_ratios.append(r)
            cpu_ratios.append(ratio(l["cpu"], g["cpu"]))
            if r <= 1.10:
                level += 1
        if l and g4 and l["status"] == "ok" and g4["status"] == "ok":
            wall4_ratios.append(ratio(l["wall"], g4["wall"]))
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            q,
            fmt(l and l["wall"]), fmt(g and g["wall"]),
            fmt(ratio(l["wall"], g["wall"]) if l and g else None),
            fmt(l and l["cpu"]), fmt(g and g["cpu"]),
            fmt(ratio(l["cpu"], g["cpu"]) if l and g else None),
            fmt(g4 and g4["wall"]),
            fmt(ratio(l["wall"], g4["wall"]) if l and g4 else None),
            status,
        ))

    n = len(wall_ratios)
    lines.append("")
    if n:
        lines.append("- geometric mean, wall, lexdb / PG one core: **%.2f** (%d queries)"
                     % (gm(wall_ratios), n))
        lines.append("- geometric mean, server CPU, lexdb / PG one core: **%.2f**"
                     % gm(cpu_ratios))
        lines.append("- level or ahead on wall (ratio <= 1.10): **%d of %d**" % (level, n))
    if wall4_ratios:
        lines.append("- geometric mean, wall, lexdb / PG four processes: **%.2f** (%d queries)"
                     % (gm(wall4_ratios), len(wall4_ratios)))
    if failed:
        lines.append("- queries that failed: **%d**" % failed)
    if different:
        lines.append("- queries with different result text (check formatting before treating as an error): **%d**" % different)
    if unchecked:
        lines.append("- queries that ran with no PostgreSQL result to check against: **%d** (give a REFDIR)" % unchecked)

    ltab = load_tables(os.path.join(outdir, "load-lexdb.tsv"))
    ptab = load_tables(os.path.join(outdir, "load-pg.tsv"))
    if ltab or ptab:
        lines.append("")
        lines.append("## Load\n")
        lines.append("| table | lexdb rows | lexdb s | PG rows | PG s | lexdb / PG |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        order = ["region", "nation", "part", "supplier", "partsupp",
                 "customer", "orders", "lineitem"]
        for t in order:
            lr = ltab.get(t)
            pr = ptab.get(t)
            lines.append("| %s | %s | %s | %s | %s | %s |" % (
                t,
                lr[0] if lr else "-", fmt(lr and lr[1] / 1000, 2),
                pr[0] if pr else "-", fmt(pr and pr[1] / 1000, 2),
                fmt(ratio(lr[1], pr[1]) if lr and pr else None),
            ))
        lt = sum(v[1] for v in ltab.values()) / 1000 if ltab else None
        pt = sum(v[1] for v in ptab.values()) / 1000 if ptab else None
        lines.append("| **total** | | **%s** | | **%s** | %s |" % (
            fmt(lt, 2), fmt(pt, 2), fmt(ratio(lt, pt) if lt and pt else None)))
        for label in ("lexdb", "pg"):
            ipath = os.path.join(outdir, "index-%s.ms" % label)
            if os.path.exists(ipath):
                lines.append("\nIndex build, %s: %s s" % (label, fmt(int(open(ipath).read()) / 1000, 2)))
            path = os.path.join(outdir, "analyze-%s.ms" % label)
            if os.path.exists(path):
                lines.append("\nANALYZE, %s: %s s" % (label, fmt(int(open(path).read()) / 1000, 2)))

    text = "\n".join(lines) + "\n"
    with open(os.path.join(outdir, "summary.md"), "w") as f:
        f.write(text)
    print(text, end="")
    return 0


def fmt(x, places=1):
    if x is None:
        return "-"
    return ("%%.%df" % places) % x


if __name__ == "__main__":
    sys.exit(main())
