#!/usr/bin/env python3
"""The Tier-1 application suite: the same lxl source, built natively with -O and
through C, checked for identical output and timed.

    python3 lexell/bench/apps.py [-n RUNS] [--only APP ...] [--json] [--json-out FILE]
                              [--tsv FILE] [--pin CORE] [--no-perf] [--no-opt]
                              [--hash-seed N | --random-hash] [--json-mb MB]
                              [--work DIR] [--keep]

README.md's three tiers put the "same lxl source, native against the C backend"
comparison first: it is the one that decides whether the C backend can go. The
microbenchmarks in bench.py answer it for small programs; this script answers it
for applications that already have a stable correctness mode. Each application
is built both ways, its two builds must print the same thing (timings in their
output are ignored, counts and checksums are not), then both are timed under
`perf stat -e instructions:u,cycles:u`, on one core, best of RUNS.

Reused harnesses (no input generation is reimplemented here):

  regex    bench/regex/regex_bench.lxl and gen_corpus.py (8 patterns, 3 MB)
  json     bench/json/json_bench.lxl and gen_data.py (--json-mb, default 20)
  jq       cmd/jq.lxl on the same JSON data, `-c .`, output hashed
  cmark    cmd/cmark.lxl on the 0.31.2 spec repeated to about 10 MB (--md-mb),
           the input of tests/markdown.py --perf
  decimal  bench/decimal/dbench.lxl, every case, checksums compared

Rows are one per application (decimal sums its cases); the table has the wall
times, instructions and cycles of each build and their ratios. `--json` prints
the same rows as JSON for regression tracking; `--json-out` and `--tsv` also
write files. Timings run with LXL_HASH_SEED=42 (as bench.py) so the map hash is
not random per process; --random-hash restores the default and --hash-seed
changes it. Outputs do not depend on the seed (Map keeps insertion order).
"""
import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LXLC = os.environ.get('LXLC') or os.path.join(ROOT, 'lexell', 'compiler', 'out', 'lxlc')
CMARK_SRC = os.path.join(ROOT, 'lexell', 'cmd', 'cmark.lxl')
JQ_SRC = os.path.join(ROOT, 'lexell', 'cmd', 'jq.lxl')
APPS = ['regex', 'json', 'jq', 'cmark', 'decimal']

HASH_SEED = '42'
PIN = 4
PERF = True
NATIVE_OPT = True
RUNS = 3


def fail(msg):
    sys.exit('apps: ' + msg)


def base_env(extra=None):
    env = dict(os.environ)
    env.pop('LXL_CHECK', None)
    if HASH_SEED is None:
        env.pop('LXL_HASH_SEED', None)
    else:
        env['LXL_HASH_SEED'] = str(HASH_SEED)
    env.update(extra or {})
    return env


def build(src, out, native):
    cmd = [LXLC, src, '-o', out]
    if native:
        cmd.append('--native')
        if NATIVE_OPT:
            cmd.append('-O')
    else:
        cmd.append('--c')
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        fail('building %s failed:\n%s' % (os.path.relpath(src, ROOT), (r.stdout + r.stderr)[-1500:]))
    return out


def run(exe, args, env, capture=True):
    """One run: (wall seconds, stdout bytes, stderr bytes, return code, instructions, cycles)."""
    cmd = [exe] + args
    if PERF:
        cmd = ['perf', 'stat', '-x,', '-e', 'instructions:u,cycles:u'] + cmd
    if PIN:
        cmd = ['taskset', '-c', str(PIN)] + cmd
    ins = cyc = None
    t0 = time.perf_counter()
    p = subprocess.run(cmd, stdout=subprocess.PIPE if capture else subprocess.DEVNULL,
                       stderr=subprocess.PIPE, env=env)
    dt = time.perf_counter() - t0
    if PERF:
        vals = {}
        for line in p.stderr.decode('utf-8', 'replace').splitlines():
            f = line.split(',')
            if len(f) > 2 and f[0].isdigit():
                vals[f[2].split(':')[0]] = int(f[0])
        if 'instructions' not in vals or 'cycles' not in vals:
            fail('%s: perf did not report instructions/cycles:\n%s' %
                 (os.path.basename(exe), p.stderr.decode('utf-8', 'replace')[-800:]))
        ins, cyc = vals['instructions'], vals['cycles']
    if p.returncode != 0:
        fail('%s exited %d: %s' % (os.path.basename(exe), p.returncode,
                                   p.stderr.decode('utf-8', 'replace')[-800:]))
    return dt, p.stdout, p.stderr, p.returncode, ins, cyc


def measure(exe, args, n):
    """Best wall time and least instructions/cycles of n runs."""
    row = {'wall': None, 'instr': None, 'cycles': None}
    for _ in range(n):
        dt, _, _, _, ins, cyc = run(exe, args, base_env(), capture=False)
        row['wall'] = dt if row['wall'] is None else min(row['wall'], dt)
        if ins is not None:
            row['instr'] = ins if row['instr'] is None else min(row['instr'], ins)
            row['cycles'] = cyc if row['cycles'] is None else min(row['cycles'], cyc)
    return row


def check(native_exe, c_exe, args, norm, label):
    """Run both builds once under LXL_CHECK=1 and compare their normalised output."""
    outs = []
    for exe in (native_exe, c_exe):
        _, out, err, _, _, _ = run(exe, args, base_env({'LXL_CHECK': '1'}))
        outs.append(norm(out))
    if outs[0] != outs[1]:
        fail('%s: native and C outputs differ:\n  native: %.500r\n  C:      %.500r' %
             (label, outs[0], outs[1]))


def norm_lines(out, fields):
    rows = []
    for line in out.decode('utf-8', 'replace').strip().split('\n'):
        f = line.split()
        if len(f) >= fields:
            rows.append(tuple(f[:fields]))
    return rows


def norm_digest(out):
    return hashlib.sha256(out).hexdigest()


def row(name, native, c, outputs, runs):
    def ratio(a, b):
        return a / b if a is not None and b else None
    return {
        'app': name,
        'native_s': native['wall'],
        'c_s': c['wall'],
        'wall_ratio': ratio(native['wall'], c['wall']),
        'native_instr': native['instr'],
        'c_instr': c['instr'],
        'instr_ratio': ratio(native['instr'], c['instr']),
        'native_cycles': native['cycles'],
        'c_cycles': c['cycles'],
        'cycles_ratio': ratio(native['cycles'], c['cycles']),
        'outputs': outputs,
        'runs': runs,
    }


def ms(x):
    return 'n/a' if x is None else ('%.0f ms' % (x * 1000))


def m(x):
    return '-' if x is None else '%.1f' % (x / 1e6)


def app_regex(tmp, n, args):
    corpus = os.path.join(tmp, 'corpus.txt')
    subprocess.run([sys.executable, os.path.join(HERE, 'regex', 'gen_corpus.py'), corpus], check=True)
    src = os.path.join(HERE, 'regex', 'regex_bench.lxl')
    native = build(src, os.path.join(tmp, 'regex_n'), True)
    c = build(src, os.path.join(tmp, 'regex_c'), False)
    run_args = [corpus, str(args.regex_reps)]
    norm = lambda out: norm_lines(out, 2)     # pattern, matches (the driver's ms field is not output)
    check(native, c, run_args, norm, 'regex')
    return row('regex', measure(native, run_args, n), measure(c, run_args, n), 'matches', n)


def make_json_data(tmp, mb):
    data = os.path.join(tmp, 'data.json')
    subprocess.run([sys.executable, os.path.join(HERE, 'json', 'gen_data.py'), data, str(mb)], check=True)
    return data


def app_json(tmp, n, args, data):
    src = os.path.join(HERE, 'json', 'json_bench.lxl')
    native = build(src, os.path.join(tmp, 'json_n'), True)
    c = build(src, os.path.join(tmp, 'json_c'), False)
    run_args = [data, str(args.json_reps)]
    norm = lambda out: norm_lines(out, 2)     # step, size (the driver's ms field is not compared)
    check(native, c, run_args, norm, 'json')
    return row('json', measure(native, run_args, n), measure(c, run_args, n), 'sizes', n)


def app_jq(tmp, n, args, data):
    native = build(JQ_SRC, os.path.join(tmp, 'jq_n'), True)
    c = build(JQ_SRC, os.path.join(tmp, 'jq_c'), False)
    run_args = ['-c', '.', data]
    check(native, c, run_args, norm_digest, 'jq')
    return row('jq', measure(native, run_args, n), measure(c, run_args, n), 'sha256', n)


def app_cmark(tmp, n, args):
    spec_path = os.path.join(HERE, '..', 'tests', 'markdown.py')
    spec = importlib.util.spec_from_file_location('lxl_markdown', spec_path)
    md = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(md)
    with open(md.fetch('spec.txt'), 'rb') as f:
        text = f.read()
    reps = max(1, int(args.md_mb * 1e6 // max(1, len(text))))
    data_path = os.path.join(tmp, 'spec.md')
    with open(data_path, 'wb') as f:
        f.write(text * reps)
    native = build(CMARK_SRC, os.path.join(tmp, 'cmark_n'), True)
    c = build(CMARK_SRC, os.path.join(tmp, 'cmark_c'), False)
    run_args = ['--unsafe', data_path]
    check(native, c, run_args, norm_digest, 'cmark')
    return row('cmark', measure(native, run_args, n), measure(c, run_args, n), 'sha256', n)


def app_decimal(tmp, n, args):
    src = os.path.join(HERE, 'decimal', 'dbench.lxl')
    native = build(src, os.path.join(tmp, 'dbench_n'), True)
    c = build(src, os.path.join(tmp, 'dbench_c'), False)
    cases = subprocess.run([native, 'list'], capture_output=True, text=True, check=True).stdout.split()
    total_n = {'wall': 0.0, 'instr': 0, 'cycles': 0}
    total_c = {'wall': 0.0, 'instr': 0, 'cycles': 0}
    for case in cases:
        check(native, c, [case], lambda out: out.decode('utf-8', 'replace').strip(), 'decimal ' + case)
        rn, rc = measure(native, [case], n), measure(c, [case], n)
        for k in total_n:
            total_n[k] += rn[k] or 0
            total_c[k] += rc[k] or 0
    if not PERF:
        for k in ('instr', 'cycles'):
            total_n[k] = total_c[k] = None
    return row('decimal', total_n, total_c, '%d checksums' % len(cases), n)


def print_table(rows):
    print('| application | native -O | C | native/C | native Minstr | C Minstr | instr native/C | '
          'native Mcyc | C Mcyc | cyc native/C | checked |')
    print('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|')
    for r in rows:
        print('| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |' % (
            r['app'], ms(r['native_s']), ms(r['c_s']),
            'n/a' if r['wall_ratio'] is None else '%.2f' % r['wall_ratio'],
            m(r['native_instr']), m(r['c_instr']),
            '-' if r['instr_ratio'] is None else '%.2f' % r['instr_ratio'],
            m(r['native_cycles']), m(r['c_cycles']),
            '-' if r['cycles_ratio'] is None else '%.2f' % r['cycles_ratio'],
            r['outputs']))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=3, help='runs per program (best is reported; default 3)')
    ap.add_argument('--only', nargs='*', choices=APPS)
    ap.add_argument('--json', action='store_true', help='print the rows as JSON instead of the table')
    ap.add_argument('--json-out', help='also write the rows to this JSON file')
    ap.add_argument('--tsv', help='also write the rows to this tab-separated file')
    ap.add_argument('--pin', type=int, default=4, help='CPU to pin every run to (0: no pinning; default 4)')
    ap.add_argument('--no-perf', action='store_true', help='wall time only (no instructions/cycles)')
    ap.add_argument('--no-opt', action='store_true', help='build native without -O')
    ap.add_argument('--hash-seed', type=int, default=42, help='LXL_HASH_SEED for the runs (default 42)')
    ap.add_argument('--random-hash', action='store_true', help='use the production random hash key')
    ap.add_argument('--json-mb', type=float, default=20, help='size of the JSON input in MB (default 20)')
    ap.add_argument('--md-mb', type=float, default=10, help='size of the Markdown input in MB (default 10)')
    ap.add_argument('--regex-reps', type=int, default=1, help='searches per pattern inside a regex run')
    ap.add_argument('--json-reps', type=int, default=1, help='steps per JSON run')
    ap.add_argument('--work', help='scratch directory (default: a new temporary one)')
    ap.add_argument('--keep', action='store_true', help='keep the scratch directory')
    a = ap.parse_args()

    global HASH_SEED, PIN, PERF, NATIVE_OPT, RUNS
    HASH_SEED = None if a.random_hash else str(a.hash_seed)
    PIN, PERF, NATIVE_OPT, RUNS = a.pin, not a.no_perf, not a.no_opt, a.n
    if PIN and shutil.which('taskset') is None:
        fail('taskset not found; use --pin 0')
    if PERF and shutil.which('perf') is None:
        print('note: perf not found; instructions and cycles are omitted', file=sys.stderr)
        PERF = False
    names = a.only or APPS
    tmp = a.work or tempfile.mkdtemp(prefix='lxlapps_')
    os.makedirs(tmp, exist_ok=True)
    t0 = time.perf_counter()
    rows = []
    try:
        data = make_json_data(tmp, a.json_mb) if ('json' in names or 'jq' in names) else None
        if 'regex' in names:
            rows.append(app_regex(tmp, RUNS, a))
        if 'json' in names:
            rows.append(app_json(tmp, RUNS, a, data))
        if 'jq' in names:
            rows.append(app_jq(tmp, RUNS, a, data))
        if 'cmark' in names:
            rows.append(app_cmark(tmp, RUNS, a))
        if 'decimal' in names:
            rows.append(app_decimal(tmp, RUNS, a))
    finally:
        if not a.keep:
            shutil.rmtree(tmp, ignore_errors=True)
    elapsed = time.perf_counter() - t0
    if a.json:
        print(json.dumps({'rows': rows, 'runs': RUNS, 'pin': PIN, 'hash_seed': HASH_SEED,
                          'native_opt': NATIVE_OPT, 'elapsed_s': elapsed}, indent=2))
    else:
        print_table(rows)
        print('\nbest of %d, pinned to core %s, hash seed %s%s; %.1f s wall' % (
            RUNS, PIN or 'any', HASH_SEED or 'random',
            ', native -O' if NATIVE_OPT else ', native (no -O)', elapsed), file=sys.stderr)
    if a.json_out:
        with open(a.json_out, 'w') as f:
            json.dump({'rows': rows, 'runs': RUNS, 'pin': PIN, 'hash_seed': HASH_SEED,
                       'native_opt': NATIVE_OPT, 'elapsed_s': elapsed}, f, indent=2)
    if a.tsv:
        with open(a.tsv, 'w') as f:
            f.write('app\tnative_s\tc_s\twall_ratio\tnative_instr\tc_instr\tinstr_ratio\t'
                    'native_cycles\tc_cycles\tcycles_ratio\toutputs\truns\n')
            for r in rows:
                f.write('\t'.join('' if r[k] is None else str(r[k]) for k in
                                  ('app', 'native_s', 'c_s', 'wall_ratio', 'native_instr', 'c_instr',
                                   'instr_ratio', 'native_cycles', 'c_cycles', 'cycles_ratio',
                                   'outputs', 'runs')) + '\n')


if __name__ == '__main__':
    main()
