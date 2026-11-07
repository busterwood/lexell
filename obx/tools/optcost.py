#!/usr/bin/env python3
"""What -O costs to compile: the same programs built with --native and --native -O.

    python3 obx/tools/optcost.py [-n RUNS] [--pin CPU] [--compiler PATH] [--only WORD ...]

The compiler is out/obxc, or $OBXC, or --compiler (use a native-built compiler to
measure what a user runs). For each program it is timed compiling that program both
ways (perf stat, user mode, best of RUNS). The table shows the -O cost as a ratio
over the default. PERFORMANCE.md's budget is +30% when optimizing; the default is
the fast path, so -O may do much more work there. The binary sizes make the growth
explicit.
"""
import argparse, math, os, subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
OBXC = os.environ.get('OBXC') or os.path.join(ROOT, 'obx', 'compiler', 'out', 'obxc')
OBX = os.path.join(ROOT, 'obx')
LIB = os.path.join(OBX, 'lib')

# (label, source, working directory)
JOBS = [
    ('compiler', os.path.join(OBX, 'compiler', 'main.obx'), os.path.join(OBX, 'compiler')),
    ('eza', os.path.join(OBX, 'cmd', 'eza.obx'), os.path.join(OBX, 'cmd')),
    ('grep', os.path.join(OBX, 'cmd', 'grep.obx'), os.path.join(OBX, 'cmd')),
    ('zoxide', os.path.join(OBX, 'cmd', 'zoxide.obx'), os.path.join(OBX, 'cmd')),
    ('jq', os.path.join(OBX, 'cmd', 'jq.obx'), os.path.join(OBX, 'cmd')),
    ('cmark', os.path.join(OBX, 'cmd', 'cmark.obx'), os.path.join(OBX, 'cmd')),
    ('tokens', os.path.join(OBX, 'bench', 'tokens.obx'), os.path.join(OBX, 'bench')),
    ('maps', os.path.join(OBX, 'bench', 'maps.obx'), os.path.join(OBX, 'bench')),
]


def measure(comp, src, flags, cwd, exe, runs, pin):
    cmd = ['perf', 'stat', '-x,', '-e', 'instructions:u,cycles:u']
    if pin is not None:
        cmd = ['taskset', '-c', str(pin)] + cmd
    cmd += [comp, src] + flags + ['-o', exe]
    best = None
    for _ in range(runs):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                           env=dict(os.environ, OBX_LIB=LIB))
        if r.returncode != 0:
            raise SystemExit('%s: %s' % (' '.join(cmd), (r.stdout + r.stderr)[-800:]))
        vals = {}
        for line in r.stderr.splitlines():
            f = line.split(',')
            if len(f) > 2 and f[0].isdigit():
                vals[f[2].split(':')[0]] = int(f[0])
        if 'instructions' not in vals or 'cycles' not in vals:
            raise SystemExit('perf did not report instructions/cycles: %s' % r.stderr[-400:])
        cur = (vals['instructions'], vals['cycles'])
        best = cur if best is None else (min(best[0], cur[0]), min(best[1], cur[1]))
    return best[0], best[1], os.path.getsize(exe)


def geo(xs):
    return math.prod(xs) ** (1 / len(xs))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=3)
    ap.add_argument('--pin', type=int)
    ap.add_argument('--compiler', default=OBXC)
    ap.add_argument('--only', nargs='*')
    a = ap.parse_args()
    comp = os.path.abspath(a.compiler)
    print('| program | default Minstr | -O Minstr | -O/default | default Mcyc | -O Mcyc | -O/default | '
          'default KiB | -O KiB |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|')
    gi, gc = [], []
    for label, src, cwd in JOBS:
        if a.only and not any(w in label for w in a.only):
            continue
        di, dc, ds = measure(comp, src, ['--native'], cwd, '/tmp/optcost-%s-d' % label, a.n, a.pin)
        oi, oc, osz = measure(comp, src, ['--native', '-O'], cwd, '/tmp/optcost-%s-o' % label, a.n, a.pin)
        ri, rc = oi / di, oc / dc
        gi.append(ri)
        gc.append(rc)
        print('| %s | %.0f | %.0f | %+.1f%% | %.0f | %.0f | %+.1f%% | %d | %d |' % (
            label, di / 1e6, oi / 1e6, 100 * (ri - 1), dc / 1e6, oc / 1e6, 100 * (rc - 1),
            ds // 1024, osz // 1024), flush=True)
    if gi:
        print('\ngeometric mean: -O/default instructions %+.1f%%, cycles %+.1f%%' % (
            100 * (geo(gi) - 1), 100 * (geo(gc) - 1)))


if __name__ == '__main__':
    main()
