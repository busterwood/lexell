#!/usr/bin/env python3
"""The ceiling measurements of design/simd.md.

Builds each workload four ways -- scalar C, gcc's auto-vectorised C, a hand-written
AVX2 version (where one exists) and native lxl -O -- and times them on one core with
`perf stat -e instructions:u,cycles:u`, best of three, the candidates of a workload
interleaved.

    python3 lexell/bench/simd/run.py [--only NAME ...] [--reps 3] [--core 8]

The workloads are the scalar loops of bench/ (array, loop, sieve, tokens, strings)
and a float dot product (dot.lxl, dot.c, dot_avx2.c), plus the exact instruction
sequence the proposed SIMD extension would emit for dot (dot_lxlstyle.c and
dot_kernels.s: 1, 4 or 8 bounds checks per 16 doubles).

Needs gcc, perf and a free core 8; all numbers are user-mode instructions and cycles.
"""
import argparse
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
LXLC = os.environ.get('LXLC') or os.path.join(ROOT, 'compiler', 'out', 'lxlc')
TOKENS_INPUT = os.path.join(ROOT, 'compiler', 'sema.lxl')
C = os.path.join(ROOT, 'bench', 'c')

CC = ['gcc', '-O2', '-fno-optimize-sibling-calls']
AVX = ['gcc', '-O2', '-march=x86-64-v3']


def sh(cmd, **kw):
    r = subprocess.run(cmd, capture_output=True, text=True, **kw)
    if r.returncode != 0:
        sys.exit('failed: ' + ' '.join(cmd) + '\n' + (r.stderr or r.stdout)[:3000])
    return r


def build(tmp):
    """name -> path of every executable."""
    b = {}

    def gcc(src, out, flags):
        sh(flags + ['-o', os.path.join(tmp, out), src])

    gcc(os.path.join(C, 'array.c'), 'array_scalar', CC + ['-fno-tree-vectorize'])
    gcc(os.path.join(C, 'array.c'), 'array_auto', AVX)
    gcc(os.path.join(HERE, 'array_avx2.c'), 'array_hand', AVX)

    gcc(os.path.join(C, 'loop.c'), 'loop_scalar', CC + ['-fno-tree-vectorize'])
    gcc(os.path.join(C, 'loop.c'), 'loop_auto', AVX)
    gcc(os.path.join(HERE, 'loop_avx2.c'), 'loop_hand', AVX)

    gcc(os.path.join(C, 'sieve.c'), 'sieve_scalar', CC + ['-fno-tree-vectorize'])
    gcc(os.path.join(C, 'sieve.c'), 'sieve_auto', AVX)
    gcc(os.path.join(HERE, 'sieve_avx2.c'), 'sieve_hand', AVX)

    gcc(os.path.join(C, 'tokens.c'), 'tokens_scalar', CC + ['-fno-tree-vectorize'])
    gcc(os.path.join(C, 'tokens.c'), 'tokens_auto', AVX)

    gcc(os.path.join(C, 'strings.c'), 'strings_scalar', CC + ['-fno-tree-vectorize'])
    gcc(os.path.join(C, 'strings.c'), 'strings_auto', AVX)

    gcc(os.path.join(HERE, 'dot.c'), 'dot_scalar', CC + ['-fno-tree-vectorize', '-ffp-contract=off'])
    gcc(os.path.join(HERE, 'dot.c'), 'dot_auto', AVX)
    gcc(os.path.join(HERE, 'dot_avx2.c'), 'dot_hand', AVX + ['-ffp-contract=off'])
    sh(AVX + ['-o', os.path.join(tmp, 'dot_lxlstyle'),
              os.path.join(HERE, 'dot_lxlstyle.c'), os.path.join(HERE, 'dot_kernels.s')])
    sh(AVX + ['-o', os.path.join(tmp, 'array_lxlstyle'),
              os.path.join(HERE, 'array_lxlstyle.c'), os.path.join(HERE, 'array_kernels.s')])

    env = dict(os.environ, LXL_LIB=os.path.join(ROOT, 'lib'))
    for name, src in [('array', 'array'), ('loop', 'loop'), ('sieve', 'sieve'),
                      ('tokens', 'tokens'), ('strings', 'strings')]:
        sh([LXLC, os.path.join(ROOT, 'bench', name + '.lxl'), '--native', '-O',
            '-o', os.path.join(tmp, name + '_lxl')], env=env)
    sh([LXLC, os.path.join(HERE, 'dot.lxl'), '--native', '-O',
        '-o', os.path.join(tmp, 'dot_lxl')], env=env)
    return tmp


WORK = {
    'array': [('scalar C', 'array_scalar', []), ('auto-vec C (AVX2)', 'array_auto', []),
              ('hand AVX2', 'array_hand', []), ('native lxl -O', 'array_lxl', [])],
    'loop': [('scalar C', 'loop_scalar', []), ('auto-vec C (AVX2)', 'loop_auto', []),
             ('hand AVX2', 'loop_hand', []), ('native lxl -O', 'loop_lxl', [])],
    'sieve': [('scalar C', 'sieve_scalar', []), ('auto-vec C (AVX2)', 'sieve_auto', []),
              ('hand AVX2 (count loop)', 'sieve_hand', []), ('native lxl -O', 'sieve_lxl', [])],
    'tokens': [('scalar C', 'tokens_scalar', [TOKENS_INPUT]), ('auto-vec C (AVX2)', 'tokens_auto', [TOKENS_INPUT]),
               ('native lxl -O', 'tokens_lxl', [TOKENS_INPUT])],
    'strings': [('scalar C', 'strings_scalar', []), ('auto-vec C (AVX2)', 'strings_auto', []),
                ('native lxl -O', 'strings_lxl', [])],
    'dot': [('scalar C', 'dot_scalar', []), ('auto-vec C (AVX2+FMA)', 'dot_auto', []),
            ('hand AVX2+FMA', 'dot_hand', []), ('native lxl -O', 'dot_lxl', [])],
    'dot_proto': [('scalar C', 'dot_scalar', []), ('hand AVX2+FMA', 'dot_hand', []),
                  ('x64gen sequence, 1 check', 'dot_lxlstyle', ['1']),
                  ('x64gen sequence, 4 checks', 'dot_lxlstyle', ['4']),
                  ('x64gen sequence, 8 checks', 'dot_lxlstyle', ['8'])],
    'array_proto': [('scalar C', 'array_scalar', []), ('hand AVX2', 'array_hand', []),
                    ('x64gen sequence, 1 check', 'array_lxlstyle', ['check']),
                    ('x64gen sequence, no check', 'array_lxlstyle', ['nocheck'])],
}


def perf(tmp, exe, args, core):
    p = sh(['taskset', '-c', str(core), 'perf', 'stat', '-x,', '-e',
            'instructions:u,cycles:u', os.path.join(tmp, exe)] + args)
    vals = {}
    for line in p.stderr.splitlines():
        f = line.split(',')
        if len(f) > 2 and f[0].isdigit():
            vals[f[2].split(':')[0]] = int(f[0])
    if 'instructions' not in vals or 'cycles' not in vals:
        sys.exit('perf did not report counters for ' + exe + ':\n' + p.stderr)
    return vals['instructions'], vals['cycles'], p.stdout.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--reps', type=int, default=3)
    ap.add_argument('--core', type=int, default=8)
    a = ap.parse_args()
    names = a.only or list(WORK)
    tmp = tempfile.mkdtemp(prefix='lxlsimd')
    build(tmp)
    print(f'# SIMD ceiling measurements (core {a.core}, best of {a.reps}, interleaved)')
    for name in names:
        cands = WORK[name]
        best = {v: None for v, _, _ in cands}
        outs = {}
        for rep in range(a.reps):
            order = cands if rep % 2 == 0 else list(reversed(cands))
            for variant, exe, args in order:
                ins, cyc, out = perf(tmp, exe, args, a.core)
                outs.setdefault(variant, out)
                if outs[variant] != out:
                    print(f'note: {name}/{variant}: output differs across runs', file=sys.stderr)
                if best[variant] is None or cyc < best[variant][1]:
                    best[variant] = (ins, cyc)
        rows = [(v, best[v][0], best[v][1], outs[v]) for v, _, _ in cands]
        print(f'\n## {name}\n')
        print('| variant | instructions (M) | cycles (M) | IPC | output |')
        print('|---|---:|---:|---:|---|')
        for v, ins, cyc, out in rows:
            print(f'| {v} | {ins/1e6:.1f} | {cyc/1e6:.1f} | {ins/cyc:.2f} | `{out[:40]}` |')
        base = rows[0]
        print('\nspeedup vs scalar C (cycles): ' + ', '.join(
            f'{v} {base[2]/cyc:.2f}x' for v, ins, cyc, out in rows[1:]))


if __name__ == '__main__':
    main()
