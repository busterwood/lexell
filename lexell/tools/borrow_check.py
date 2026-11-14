#!/usr/bin/env python3
"""The library's str parameters that every program only reads (design/borrow-inference.md 7).

Runs `lxlc --borrow-report` (with LXL_BORROW_REPORT=all) over the compiler, the programs in cmd/,
bench/ and every library and conformance test, and combines the verdicts: a parameter of a module
in lib/ declared str that no program keeps should be declared &str. Exits 1 when there is one
that tools/borrow_allow.txt does not list (with the reason it stays str).

    python3 lexell/tools/borrow_check.py [-j N]
"""
import glob, os, re, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

R = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LXLC = os.environ.get('LXLC', os.path.join(R, 'compiler', 'out', 'lxlc'))
LINE = re.compile(r"^(?P<at>[^:]+:\d+): parameter '(?P<p>[^']+)' of (?P<f>\S+) is declared str (?P<v>but only read|and kept)")


def programs():
    pats = ['compiler/main.lxl', 'cmd/*.lxl', 'bench/*.lxl', 'bench/json/json_bench.lxl', 'lib/tests/run/*.lxl',
            'lib/tests/run/*/main.lxl', 'tests/run/*.lxl', 'tests/lexdb/run/*.lxl']
    out = []
    for p in pats:
        out += sorted(glob.glob(os.path.join(R, p)))
    return out


def report(prog):
    env = dict(os.environ, LXL_BORROW_REPORT='all')
    r = subprocess.run([LXLC, '--borrow-report', prog], capture_output=True, text=True, env=env, timeout=120)
    return r.stdout.splitlines()


def main():
    j = int(sys.argv[sys.argv.index('-j') + 1]) if '-j' in sys.argv else 8
    libdir = os.path.realpath(os.path.join(R, 'lib'))
    allow = set()
    path = os.path.join(R, 'tools', 'borrow_allow.txt')
    if os.path.exists(path):
        for l in open(path):
            l = l.split('#')[0].strip()
            if l:
                allow.add(tuple(l.split()[:2]))
    verdict = {}
    with ThreadPoolExecutor(j) as ex:
        for lines in ex.map(report, programs()):
            for l in lines:
                m = LINE.match(l)
                if not m or os.path.dirname(os.path.realpath(m['at'].rsplit(':', 1)[0])) != libdir:
                    continue
                k = (m['at'], m['f'], m['p'])
                kept = m['v'] == 'and kept'
                verdict[k] = verdict.get(k, False) or kept
    hits = sorted(k for k, kept in verdict.items() if not kept and (k[1], k[2]) not in allow)
    for at, f, p in hits:
        print(f"{os.path.relpath(at, R)}: parameter '{p}' of {f} is declared str but only read: declare it &str")
    print(f'borrow check: {len(verdict)} library str parameters seen, {len(hits)} should be &str')
    sys.exit(1 if hits else 0)


if __name__ == '__main__':
    main()
