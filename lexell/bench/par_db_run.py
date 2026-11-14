#!/usr/bin/env python3
# par_db_run.py: the par.map database-kernel experiments (design/par-db-perf.md).
#
#   python3 lexell/bench/par_db_run.py kernels [ROUNDS] [OUT.tsv]
#   python3 lexell/bench/par_db_run.py copy DATA.tsv [ROUNDS] [OUT.tsv] [CHUNKS]
#
# kernels: aggregation, DISTINCT, hash-join probes and output expressions over
# 1M rows built in memory. copy: the wide COPY of design/lexdb.md 9.118,
# parsed and encoded from a TSV file. Each mode runs as a loop at LXL_PAR=0
# and on 2, 4 and 8 threads (LXL_PAR=1, 3, 7). The time is the program's own
# monotonic clock around the kernel, so reading and building the input are
# outside it; the first round is dropped (the pool starts lazily).
import os, resource, statistics, subprocess, sys, tempfile, time

HERE = os.path.dirname(os.path.abspath(__file__))
COMPILER = os.path.join(HERE, "..", "compiler", "out", "lxlc")
OUT = os.path.join(tempfile.gettempdir(), "par_db_bin")

def build(name):
    src = os.path.join(HERE, name + ".lxl")
    out = OUT + "_" + name
    subprocess.run([COMPILER, src, "-O", "-o", out], check=True)
    return out

def run(binary, args, par, rounds):
    env = dict(os.environ, LXL_PAR=str(par))
    before = resource.getrusage(resource.RUSAGE_CHILDREN)
    t0 = time.perf_counter()
    p = subprocess.run([binary] + args + [str(rounds)], stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=env, text=True)
    wall = time.perf_counter() - t0
    after = resource.getrusage(resource.RUSAGE_CHILDREN)
    user = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
    if p.returncode != 0:
        raise SystemExit(p.stderr.strip()[:400])
    times = []
    check = ""
    for line in p.stdout.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            times.append(float(parts[1])); check = parts[2]
    steady = times[1:] if len(times) > 1 else times
    return statistics.median(steady), min(times), user, wall, check

def table(rows, out_path):
    lines = ["bench\tmode\tLXL_PAR\tthreads\tmedian_ms\tmin_ms\tuser_s\twall_s\tcheck"]
    lines += ["\t".join(str(x) for x in r) for r in rows]
    text = "\n".join(lines) + "\n"
    print(text, end="")
    if out_path:
        open(out_path, "w").write(text)

def kernels(rounds, out_path):
    binary = build("par_db")
    rows = []
    for mode in ["group1", "groupN", "distinct1", "distinctN", "join1", "joinN", "expr1", "exprN"]:
        for par in [0, 1, 3, 7]:
            med, low, user, wall, check = run(binary, [mode, "1000000"], par, rounds)
            rows.append(("par_db", mode, par, par + 1, round(med), round(low), round(user, 2), round(wall, 2), check))
    table(rows, out_path)

def copy(data, rounds, out_path, chunks):
    binary = build("par_copy")
    rows = []
    for mode in ["split1", "splitN", "splitB1", "splitBN", "parse1", "parseN", "parseB1", "parseBN", "all1", "allN", "borrow1", "borrowN"]:
        for par in [0, 1, 3, 7]:
            # par_copy takes MODE FILE N ROUNDS [CHUNKS]
            env = dict(os.environ, LXL_PAR=str(par))
            before = resource.getrusage(resource.RUSAGE_CHILDREN)
            t0 = time.perf_counter()
            p = subprocess.run([binary, mode, data, "1000000", str(rounds), str(chunks)],
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE, env=env, text=True)
            wall = time.perf_counter() - t0
            after = resource.getrusage(resource.RUSAGE_CHILDREN)
            user = (after.ru_utime - before.ru_utime) + (after.ru_stime - before.ru_stime)
            if p.returncode != 0:
                raise SystemExit(p.stderr.strip()[:400])
            times = [float(l.split("\t")[1]) for l in p.stdout.splitlines() if l.count("\t") >= 2]
            check = p.stdout.splitlines()[-1].split("\t")[2] if times else ""
            steady = times[1:] if len(times) > 1 else times
            rows.append(("par_copy", mode, par, par + 1, round(statistics.median(steady)),
                         round(min(times)), round(user, 2), round(wall, 2), check))
    table(rows, out_path)

if __name__ == "__main__":
    what = sys.argv[1]
    if what == "kernels":
        rounds = int(sys.argv[2]) if len(sys.argv) > 2 else 5
        out = sys.argv[3] if len(sys.argv) > 3 else ""
        kernels(rounds, out)
    elif what == "copy":
        data = sys.argv[2]
        rounds = int(sys.argv[3]) if len(sys.argv) > 3 else 3
        out = sys.argv[4] if len(sys.argv) > 4 else ""
        chunks = int(sys.argv[5]) if len(sys.argv) > 5 else 16
        copy(data, rounds, out, chunks)
    else:
        raise SystemExit(__doc__)
