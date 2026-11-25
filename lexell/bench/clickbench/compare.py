#!/usr/bin/env python3
"""Compare ClickBench TSVs written by bench.py and load times from run.sh.

    python3 compare.py OUTDIR [REFDIR]
"""
import os
import statistics
import sys

# Queries with LIMIT and no deterministic tie-breaker (0-indexed: q17 has no ORDER BY;
# several top-N queries can tie on equal counts/timestamps across engines).
NONDET_ORDER = {
    "q8", "q9", "q10", "q11", "q12", "q13", "q14", "q15", "q16", "q17", "q18",
    "q21", "q22", "q23", "q24", "q25", "q26", "q27", "q28",
    "q30", "q31", "q32", "q33", "q34", "q35", "q36", "q37", "q38",
    "q39", "q40", "q41", "q42",
}


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


def fmt(x, places=1):
    if x is None:
        return "-"
    return ("%%.%df" % places) % x


def main():
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: compare.py OUTDIR [REFDIR]")
    outdir = sys.argv[1]
    lex = load_queries(os.path.join(outdir, "lexdb.tsv"))
    pg1 = load_queries(os.path.join(outdir, "pg1.tsv"))
    pg4 = load_queries(os.path.join(outdir, "pg4.tsv"))
    if not (lex or pg1 or pg4):
        raise SystemExit("no lexdb.tsv, pg1.tsv or pg4.tsv in " + outdir)

    ref = pg1
    if not ref and len(sys.argv) == 3:
        ref = load_queries(os.path.join(sys.argv[2], "pg1.tsv"))

    names = sorted(set(lex) | set(pg1) | set(pg4), key=lambda q: int(q[1:]))
    lines = []
    lines.append("# ClickBench\n")
    lines.append("Times in milliseconds; ratios are lexdb / PostgreSQL (below 1 favours lexdb).\n")
    lines.append("| query | lexdb wall | PG 1 core wall | ratio | "
                 "lexdb CPU | PG CPU | ratio | PG 4 proc wall | ratio | check |")
    lines.append("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")

    wall_ratios, cpu_ratios, wall4_ratios = [], [], []
    sum_l = sum_g1 = sum_g4 = sum_cl = sum_cg1 = 0.0
    level = failed = diff_exact = tie_diff = 0

    for q in names:
        l, g, g4 = lex.get(q), pg1.get(q), pg4.get(q)
        r = ref.get(q)
        status = "ok"
        if (l and l["status"] != "ok") or (g and g["status"] != "ok") or (g4 and g4["status"] != "ok"):
            status = "fail"
            failed += 1
        elif l and r and r["status"] == "ok":
            if l["rows"] != r["rows"]:
                status = "row mismatch (%d vs %d)" % (l["rows"], r["rows"])
                diff_exact += 1
            elif l["md5"] != r["md5"]:
                if q in NONDET_ORDER:
                    status = "rows ok (tie/order)"
                    tie_diff += 1
                else:
                    status = "different result"
                    diff_exact += 1
        elif l:
            status = "ran, unchecked"

        usable = (l and g and l["status"] == "ok" and g["status"] == "ok")
        if usable:
            rw = ratio(l["wall"], g["wall"])
            wall_ratios.append(rw)
            cpu_ratios.append(ratio(l["cpu"], g["cpu"]))
            sum_l += l["wall"]
            sum_g1 += g["wall"]
            sum_cl += l["cpu"]
            sum_cg1 += g["cpu"]
            if rw <= 1.10:
                level += 1
        if l and g4 and l["status"] == "ok" and g4["status"] == "ok":
            wall4_ratios.append(ratio(l["wall"], g4["wall"]))
            sum_g4 += g4["wall"]

        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            q,
            fmt(l and l["status"] == "ok" and l["wall"] or None),
            fmt(g and g["status"] == "ok" and g["wall"] or None),
            fmt(ratio(l["wall"], g["wall"]) if usable else None, 2),
            fmt(l and l["status"] == "ok" and l["cpu"] or None),
            fmt(g and g["status"] == "ok" and g["cpu"] or None),
            fmt(ratio(l["cpu"], g["cpu"]) if usable else None, 2),
            fmt(g4 and g4["status"] == "ok" and g4["wall"] or None),
            fmt(ratio(l["wall"], g4["wall"]) if (l and g4 and l["status"] == "ok" and g4["status"] == "ok") else None, 2),
            status,
        ))

    n = len(wall_ratios)
    lines.append("")
    if n:
        lines.append("- sum, wall (%d queries): lexdb **%.1f ms** vs PG 1 core **%.1f ms** (ratio **%.2f**)"
                     % (n, sum_l, sum_g1, ratio(sum_l, sum_g1)))
        lines.append("- geometric mean, wall, lexdb / PG one core: **%.2f** (%d queries)"
                     % (gm(wall_ratios), n))
        lines.append("- geometric mean, server CPU, lexdb / PG one core: **%.2f**"
                     % gm(cpu_ratios))
        lines.append("- level or ahead on wall (ratio <= 1.10): **%d of %d**" % (level, n))
    if wall4_ratios:
        lines.append("- sum, wall vs PG 4 proc (%d queries): **%.1f ms** vs **%.1f ms** (ratio **%.2f**)"
                     % (len(wall4_ratios), sum_l, sum_g4, ratio(sum_l, sum_g4)))
        lines.append("- geometric mean, wall, lexdb / PG four processes: **%.2f** (%d queries)"
                     % (gm(wall4_ratios), len(wall4_ratios)))
    if failed:
        lines.append("- queries that failed: **%d**" % failed)
    if diff_exact:
        lines.append("- queries with different result: **%d**" % diff_exact)
    if tie_diff:
        lines.append("- top-N/unordered queries with matching row count and tie/order difference: **%d**" % tie_diff)

    ltab = load_tables(os.path.join(outdir, "load-lexdb.tsv"))
    ptab = load_tables(os.path.join(outdir, "load-pg.tsv"))
    if ltab or ptab:
        lines.append("\n## Load\n")
        lines.append("| table | lexdb rows | lexdb s | PG rows | PG s | lexdb / PG |")
        lines.append("|---|---:|---:|---:|---:|---:|")
        lr = ltab.get("hits")
        pr = ptab.get("hits")
        lines.append("| hits | %s | %s | %s | %s | %s |" % (
            lr[0] if lr else "-", fmt(lr and lr[1] / 1000, 2),
            pr[0] if pr else "-", fmt(pr and pr[1] / 1000, 2),
            fmt(ratio(lr[1], pr[1]) if lr and pr else None, 2),
        ))
        for label in ("lexdb", "pg"):
            path = os.path.join(outdir, "analyze-%s.ms" % label)
            if os.path.exists(path):
                lines.append("\nANALYZE, %s: %s s" % (label, fmt(int(open(path).read()) / 1000, 2)))

    text = "\n".join(lines) + "\n"
    with open(os.path.join(outdir, "summary.md"), "w") as f:
        f.write(text)
    print(text, end="")
    return 0


if __name__ == "__main__":
    sys.exit(main())
