#!/usr/bin/env python3
"""Compare two lxl compilers on frozen inputs: compile speed and run speed.

    python3 lexell/tools/perfsuite.py BASE NEW [-n RUNS] [--only WORD ...]
                                   [--frozen REV] [--work DIR] [--placements N]

BASE and NEW are each a git revision (main, HEAD, a branch, a hash), a
source tree (a lexell/ directory, such as a worktree's), or the path of a
native-built compiler. For a revision or a tree the script builds its
native compiler: gcc builds its seed (seed/lxlc.c), and that compiler
builds the tree's main.lxl with --native. A tree's seed must be current
(reseed.sh).

Every input comes from one frozen revision of the sources (FROZEN below,
or --frozen), so the inputs do not grow with each pass.

- Compile suite: each compiler compiles the frozen compiler (--native and
  --emit-c) and the frozen eza, grep and zoxide (--native). This is the
  compile speed a user sees. It counts both the cost of the new analysis
  and whatever the compiler gains from being compiled better itself.
- Run suite: each compiler builds the frozen bench programs and the
  frozen grep, sort, wc and eza with --native. The programs then run on
  fixed inputs; the 100 MB text is generated once, the same every time.
  Both builds must print the same output.

Instructions are the least of RUNS and cycles the best of RUNS (user
mode), with base and new interleaved. The summary is the geometric mean
of new/base for each suite. PERFORMANCE.md, "Judging a pass", says how
the two numbers are weighed. Needs perf and gcc.

--placements N measures every program at N code placements instead of one:
each is built with LXL_PADB = 0, 64/N, ... bytes before every function's
alignment (tools/placement.py), which moves functions as growth of the
code ahead of them would. The compilers of the compile suite are built the
same way, when BASE and NEW are revisions or trees (a compiler given as a
path has one placement). Cycles are then the median over the placements of
each placement's best of RUNS, and each row adds the spread (max over min)
of base and new across placements. A row is marked "apart" when the two
ranges do not overlap: a change that one unlucky layout cannot explain.
Runs are interleaved over placements and compilers, so a cycles difference
is not a drift of the machine.

--cpu N runs every measured command on CPU N (taskset). On this machine
(SMT siblings N and N+8) a core whose sibling is busy with other work runs
fib about 10% slower in cycles at the same instructions, and an unpinned
process lands on whichever core is free: that, more than code placement, made
single-run cycles move between runs of one binary (2026-11-24). The load
average is printed before and after: above 1, cycles are less reliable.
"""
import hashlib
import argparse
import math
import os
import random
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FROZEN = 'a1c47b3c'         # move only on purpose, and say so in HISTORY.md, "Judging a pass" (was
                            # 7d519d1 until the literal suffixes of 2026-11-06, then af99f933, which
                            # predates the lexell/ rename: 5f30415d was given with --frozen until
                            # a1c47b3c, the first with the five programs added on 2026-11-23)
BENCH = ['fib', 'loop', 'array', 'alloc', 'lists', 'strings', 'trees', 'tokens', 'sieve', 'maps',
         'nbody', 'interp', 'closures', 'matmul', 'pingpong']
TOOLS = ['grep', 'sort', 'wc', 'eza']


def sh(cmd, **kw):
    return subprocess.run(cmd, check=True, **kw)


def extract(rev, work):
    """The lexell/ tree of rev, under work/src-REV (once)."""
    h = sh(['git', '-C', ROOT, 'rev-parse', '--short=12', rev], capture_output=True, text=True).stdout.strip()
    d = os.path.join(work, 'src-' + h)
    if not os.path.isdir(d):
        tmp = d + '.tmp'
        shutil.rmtree(tmp, ignore_errors=True)
        os.makedirs(tmp)
        arc = subprocess.Popen(['git', '-C', ROOT, 'archive', h, 'lexell/compiler', 'lexell/lib', 'lexell/cmd', 'lexell/bench'],
                               stdout=subprocess.PIPE)
        sh(['tar', '-x', '-C', tmp], stdin=arc.stdout)
        if arc.wait() != 0:
            sys.exit(f'git archive {rev} failed')
        os.rename(tmp, d)
    return h, d


def treeHash(lx):
    """A hash of a lexell/ tree's compiler and library sources."""
    m = hashlib.sha1()
    for sub in ('compiler', 'lib'):
        for dp, dns, fns in os.walk(os.path.join(lx, sub)):
            dns[:] = sorted(x for x in dns if x not in ('out', 'tests', '__pycache__'))
            for fn in sorted(fns):
                f = os.path.join(dp, fn)
                m.update(os.path.relpath(f, lx).encode() + b'\0')
                with open(f, 'rb') as fh:
                    m.update(fh.read())
    return m.hexdigest()[:12]


def compiler(spec, work, pad=0):
    """A native-built compiler: the path given, or built from a revision or a tree
    (with LXL_PADB=pad when pad)."""
    if os.path.isfile(spec):
        return os.path.abspath(spec), os.path.basename(spec)
    if os.path.isdir(spec):
        lx = os.path.abspath(spec)
        if not os.path.isfile(os.path.join(lx, 'compiler', 'seed', 'lxlc.c')):
            sys.exit(f'{spec}: not a lexell/ tree (no compiler/seed/lxlc.c)')
        h = 'tree-' + treeHash(lx)
    else:
        h, d = extract(spec, work)
        lx = os.path.join(d, 'lexell')
    out = os.path.join(work, 'lxlc-' + h)
    if not os.path.exists(out + '.seed'):
        print(f'building the seed compiler of {spec} ({h})', file=sys.stderr, flush=True)
        sh(['gcc', '-O2', '-w', '-std=gnu11', '-o', out + '.seed.tmp', os.path.join(lx, 'compiler', 'seed', 'lxlc.c'), '-lm'])
        os.rename(out + '.seed.tmp', out + '.seed')
    if pad:
        out += f'-p{pad}'
    if not os.path.exists(out):
        print(f'building the native compiler of {spec} ({h}{f", placement {pad}" if pad else ""})', file=sys.stderr, flush=True)
        env = dict(os.environ, LXL_LIB=os.path.join(lx, 'lib'), LXL_PADB=str(pad))
        sh([os.path.join(work, 'lxlc-' + h + '.seed'), 'main.lxl', '--native', '-o', out + '.tmp'],
           cwd=os.path.join(lx, 'compiler'), env=env)
        os.rename(out + '.tmp', out)
    return out, f'{spec} ({h})'


def text100(work):
    """100 MB of numbered lines of Greek letter names, some with needles."""
    p = os.path.join(work, 'text100.txt')
    if os.path.exists(p):
        return p
    words = ('alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu nu xi omicron '
             'pi rho sigma tau upsilon phi chi psi omega').split()
    rng = random.Random(20261104)
    out, size, i = [], 0, 0
    while size < 100_000_000:
        ws = [rng.choice(words) for _ in range(rng.randint(1, 12))]
        if rng.random() < 0.01:
            ws.append(f'needle{i % 100}')
        line = f'{i:07d} ' + ' '.join(ws) + '\n'
        out.append(line)
        size += len(line)
        i += 1
    data = ''.join(out)[:100_000_000]
    with open(p + '.tmp', 'w') as f:
        f.write(data[:data.rfind('\n') + 1])
    os.rename(p + '.tmp', p)
    return p


PIN = []


def load():
    with open('/proc/loadavg') as f:
        return float(f.read().split()[0])


def stat(cmd, env, cwd=None):
    r = subprocess.run(PIN + ['perf', 'stat', '-x,', '-e', 'instructions:u,cycles:u'] + cmd, env=env, cwd=cwd,
                       stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if r.returncode != 0:
        sys.exit(f'failed: {" ".join(cmd)}\n{r.stderr.decode(errors="replace")[-2000:]}')
    lines = r.stderr.decode().strip().splitlines()[-2:]
    return [int(l.split(',')[0]) for l in lines], r.stdout


def measure(cmds, runs, env, cwd=None):
    """cmds[p] = [base command, new command] at placement p. Interleaved over runs,
    placements and compilers; per placement the least instructions and best cycles."""
    np = len(cmds)
    best = [[[math.inf, math.inf], [math.inf, math.inf]] for _ in range(np)]
    outs = [[None, None] for _ in range(np)]
    for _ in range(runs):
        for p in range(np):
            for k in (0, 1):
                (ins, cyc), out = stat(cmds[p][k], env, cwd)
                best[p][k] = [min(best[p][k][0], ins), min(best[p][k][1], cyc)]
                outs[p][k] = out
    return best, outs


def median(xs):
    xs = sorted(xs)
    n = len(xs)
    return xs[n // 2] if n % 2 else (xs[n // 2 - 1] + xs[n // 2]) / 2


def row(label, best):
    """best[p][k]: one placement prints as before; several print the median cycles over
    the placements, each side's spread, and "apart" when the ranges do not overlap."""
    bi, ni = (min(b[k][0] for b in best) for k in (0, 1))
    bcs, ncs = ([b[k][1] for b in best] for k in (0, 1))
    bc, nc = median(bcs), median(ncs)
    line = (f'{label:24s} {bi / 1e6:9.1f}M {ni / 1e6:9.1f}M {100 * (ni / bi - 1):+6.2f}%   '
            f'{bc / 1e6:8.1f}M {nc / 1e6:8.1f}M {100 * (nc / bc - 1):+6.2f}%')
    if len(best) > 1:
        sb, sn = (100 * (max(c) / min(c) - 1) for c in (bcs, ncs))
        apart = max(ncs) < min(bcs) or min(ncs) > max(bcs)
        line += f'   {sb:5.1f}% {sn:5.1f}%  {"apart" if apart else ""}'
    print(line, flush=True)
    return ni / bi, nc / bc


def geo(xs):
    return math.exp(sum(math.log(x) for x in xs) / len(xs)) if xs else 1.0


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('base')
    ap.add_argument('new')
    ap.add_argument('-n', type=int, default=5, help='runs of each (default 5)')
    ap.add_argument('--only', nargs='*', default=[], help='only the workloads whose label contains a word')
    ap.add_argument('--frozen', default=FROZEN, help=f'revision of the inputs (default {FROZEN})')
    ap.add_argument('--work', default=os.path.join(os.environ.get('TMPDIR', '/tmp'), 'lxl-perfsuite'),
                    help='cache of sources, compilers, programs and inputs')
    ap.add_argument('--placements', type=int, default=1, metavar='N',
                    help='measure at N code placements (LXL_PADB steps of 64/N bytes; default 1)')
    ap.add_argument('--cpu', type=int, default=None, metavar='N', help='run every measured command on CPU N')
    a = ap.parse_args()
    if a.cpu is not None:
        PIN[:] = ['taskset', '-c', str(a.cpu)]
    if not 1 <= a.placements <= 8:
        sys.exit('--placements: 1 to 8')
    pads = [64 * i // a.placements // 8 * 8 for i in range(a.placements)]
    os.makedirs(a.work, exist_ok=True)
    cs = [compiler(a.base, a.work), compiler(a.new, a.work)]
    # the compilers of the compile suite, per placement; a compiler given as a path has one
    fixed = os.path.isfile(a.base) or os.path.isfile(a.new)
    ccs = [cs] + [[compiler(spec, a.work, pad) for spec in (a.base, a.new)] for pad in pads[1:] if not fixed]
    fh, fd = extract(a.frozen, a.work)
    flxl = os.path.join(fd, 'lexell')
    env = dict(os.environ, LXL_LIB=os.path.join(flxl, 'lib'))
    env.pop('LXL_CHECK', None)
    env.pop('LXL_PADB', None)
    want = lambda label: not a.only or any(w in label for w in a.only)
    print(f'base {cs[0][1]}\nnew  {cs[1][1]}\ninputs frozen at {fh}, best of {a.n}'
          + (f', on CPU {a.cpu}' if a.cpu is not None else ''))
    la = load()
    print(f'load average {la:.2f} at the start' + (' (busy: cycles less reliable)' if la > 1 else ''))
    if len(pads) > 1:
        print(f'placements {" ".join(map(str, pads))} (LXL_PADB): cycles are the median over them'
              + ('; compile suite at one placement (a compiler given as a path)' if fixed else ''))
    print()
    head = f'{"":24s} {"base instr":>10s} {"new instr":>10s} {"":7s}   {"base cyc":>9s} {"new cyc":>9s}'
    print(head + (f' {"":7s}   {"spread b":>6s} {"spread n":>6s}' if len(pads) > 1 else ''))

    tmp = os.path.join(a.work, 'out')
    os.makedirs(tmp, exist_ok=True)
    print('compile suite')
    comp = []
    jobs = [('compiler --native', 'compiler', 'main.lxl', ['--native']),
            ('compiler --emit-c', 'compiler', 'main.lxl', ['--emit-c']),
            ('eza --native', 'cmd', 'eza.lxl', ['--native']),
            ('grep --native', 'cmd', 'grep.lxl', ['--native']),
            ('zoxide --native', 'cmd', 'zoxide.lxl', ['--native'])]
    for label, sub, src, flags in jobs:
        if not want(label):
            continue
        out = ['-o', os.path.join(tmp, 'c.out')] if '--native' in flags else []
        best, _ = measure([[[c, src] + flags + out for c, _ in pc] for pc in ccs], a.n, env, cwd=os.path.join(flxl, sub))
        comp.append(row(label, best))

    print('run suite')
    progs = {}
    def prog(k, name, src, pad):
        p = os.path.join(tmp, f'{name}-{k}-p{pad}')
        sh([cs[k][0], os.path.basename(src), '--native', '-o', p], cwd=os.path.dirname(src),
           env=dict(env, LXL_PADB=str(pad)))
        return p
    for name in BENCH:
        progs[name] = [[prog(k, name, os.path.join(flxl, 'bench', name + '.lxl'), pad) for k in (0, 1)] for pad in pads]
    for name in TOOLS:
        progs[name] = [[prog(k, name, os.path.join(flxl, 'cmd', name + '.lxl'), pad) for k in (0, 1)] for pad in pads]
    t = text100(a.work)
    runs = [(b, b, [os.path.join(flxl, 'compiler', 'sema.lxl')] if b == 'tokens' else []) for b in BENCH]
    runs += [('grep -n omega', 'grep', ['-n', 'omega', t]), ('grep -cE a.*z.*e', 'grep', ['-c', '-E', 'a.*z.*e', t]),
             ('grep -cw eta', 'grep', ['-c', '-w', 'eta', t]), ('sort', 'sort', [t]), ('wc -w', 'wc', ['-w', t]),
             ('eza -T /usr/share', 'eza', ['-T', '/usr/share'])]
    run = []
    for label, name, args in runs:
        if not want(label):
            continue
        best, outs = measure([[[pp[k]] + args for k in (0, 1)] for pp in progs[name]], a.n, env)
        if any(o != outs[0][0] for po in outs for o in po):
            sys.exit(f'{label}: the builds print different output')
        run.append(row(label, best))

    la = load()
    print(f'\nload average {la:.2f} at the end' + (' (busy: cycles less reliable)' if la > 1 else ''))
    print('\ngeometric mean of new/base     instructions   cycles')
    for label, rs in (('compile suite', comp), ('run suite', run)):
        if rs:
            gi, gc = geo([r[0] for r in rs]), geo([r[1] for r in rs])
            print(f'{label:30s} {100 * (gi - 1):+10.2f}%  {100 * (gc - 1):+7.2f}%')


if __name__ == '__main__':
    main()
