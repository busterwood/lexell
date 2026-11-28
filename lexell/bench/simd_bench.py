#!/usr/bin/env python3
"""Explicit-SIMD microbenchmark table: Lexell vector[T] vs Rust std::arch AVX2 vs Java Vector API.

Compares explicit 256-bit AVX2 SIMD implementations of the same workloads across:
  - Lexell (`lexell/bench/simd/<name>.lxl`, safe built-in `vector[T]`), built via C and --native [-O]
  - Rust (`lexell/bench/rust/src/main.rs`, `std::arch::x86_64` AVX2/FMA intrinsics; `std::simd` is nightly-only)
  - Java (`lexell/bench/java/SimdBench.java`, OpenJDK 21 `jdk.incubator.vector`, warmed up)

Every implementation must produce the exact same checksum, and Lexell builds are checked
for leaks under LXL_CHECK=1.

    python3 lexell/bench/simd_bench.py [-n RUNS] [--only NAME ...] [--opt] [--no-rust] [--no-java]
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
LXLC = os.environ.get('LXLC') or os.path.join(ROOT, 'lexell', 'compiler', 'out', 'lxlc')
SIMD_DIR = os.path.join(HERE, 'simd')
RUST_DIR = os.path.join(HERE, 'rust')
JAVA_DIR = os.path.join(HERE, 'java')

NAMES = ['array_vec', 'sieve_vec', 'matmul_vec', 'bitpack_vec', 'dot_vec']

RUST_EXE = None
JAVA_CP = None
PEAK = None


def base_env(env_extra=None):
    env = dict(os.environ)
    env.pop('LXL_CHECK', None)
    env.update(env_extra or {})
    return env


def cmd_for(exe, name):
    return [exe, name] if RUST_EXE is not None and exe == RUST_EXE else [exe]


def run(exe, name, env_extra=None):
    t0 = time.perf_counter()
    p = subprocess.run(cmd_for(exe, name), capture_output=True, text=True, env=base_env(env_extra))
    return p.returncode, p.stdout.strip(), p.stderr.strip(), time.perf_counter() - t0


def best(exe, name, n):
    ts = []
    out = None
    for _ in range(n):
        code, o, err, dt = run(exe, name)
        if code != 0:
            raise SystemExit(f"{exe} exited {code}: {err}")
        ts.append(dt)
        out = o
    return min(ts), out


def build_lxl(name, tmp, native=False, opt=False):
    exe = os.path.join(tmp, name + ('_lxln' if native else '_lxl') + ('_O' if opt else ''))
    flags = (['--native'] if native else ['--c']) + (['-O'] if opt else [])
    subprocess.run([LXLC, os.path.join(SIMD_DIR, name + '.lxl'), '-o', exe] + flags, check=True)
    return exe


def build_rust():
    if not shutil.which('cargo'):
        return None
    r = subprocess.run(['cargo', 'build', '--release', '--offline', '--quiet'], cwd=RUST_DIR)
    if r.returncode != 0:
        print('note: Rust reference did not build; Rust column skipped', file=sys.stderr)
        return None
    return os.path.join(RUST_DIR, 'target', 'release', 'dbench')


def build_java(tmp):
    if not shutil.which('javac') or not shutil.which('java'):
        return None
    out = os.path.join(tmp, 'java_simd')
    os.makedirs(out, exist_ok=True)
    r = subprocess.run(
        ['javac', '--add-modules', 'jdk.incubator.vector', '-d', out,
         os.path.join(JAVA_DIR, 'SimdBench.java')],
        capture_output=True, text=True,
    )
    if r.returncode != 0:
        print('note: Java SimdBench did not build; Java column skipped\n' + r.stderr, file=sys.stderr)
        return None
    return out


def build_peak(tmp):
    if not shutil.which('gcc'):
        return None
    out = os.path.join(tmp, 'peak')
    r = subprocess.run(['gcc', '-O2', '-static', '-o', out, os.path.join(HERE, 'peak.c')])
    return out if r.returncode == 0 else None


def peak_of(stderr):
    for line in stderr.splitlines():
        if line.startswith('peak '):
            return int(line.split()[1]) / 1024
    return None


def peak_run(exe, name):
    if exe is None or PEAK is None:
        return None
    p = subprocess.run([PEAK] + cmd_for(exe, name), capture_output=True, text=True, env=base_env())
    return peak_of(p.stderr)


def java_run(name, n):
    cmd = ['java', '--add-modules', 'jdk.incubator.vector', f'-Dbench.runs={n}',
           '-cp', JAVA_CP, 'SimdBench', name]
    p = subprocess.run(([PEAK] if PEAK else []) + cmd, capture_output=True, text=True, env=base_env())
    if p.returncode != 0:
        raise SystemExit(f"{name}: Java SimdBench exited {p.returncode}: {p.stderr.strip()[-500:]}")
    lines = p.stdout.strip().splitlines()
    warm = [l for l in lines if l.startswith('warm ')]
    return float(warm[0].split()[1]) / 1000, lines[0].strip(), peak_of(p.stderr)


def fmt(t):
    return f"{t * 1000:.0f} ms" if t is not None else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=5, help='runs per program (best is reported)')
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--opt', action='store_true', help='also build native with -O')
    ap.add_argument('--no-rust', action='store_true')
    ap.add_argument('--no-java', action='store_true')
    a = ap.parse_args()

    global RUST_EXE, JAVA_CP, PEAK
    names = a.only or NAMES
    tmp = tempfile.mkdtemp(prefix='lxlsimdbench')
    if not a.no_rust:
        RUST_EXE = build_rust()
    PEAK = build_peak(tmp)
    if not a.no_java:
        JAVA_CP = build_java(tmp)

    rows = []
    for name in names:
        lxl = build_lxl(name, tmp)
        lxln = build_lxl(name, tmp, native=True)
        lxlo = build_lxl(name, tmp, native=True, opt=True) if a.opt else None
        for exe in (lxl, lxln) + ((lxlo,) if lxlo else ()):
            code, _, err, _ = run(exe, name, {'LXL_CHECK': '1'})
            if code != 0:
                raise SystemExit(f"{name}: {exe} with LXL_CHECK=1 exited {code}: {err}")
        t_c, out_c = best(lxl, name, a.n)
        t_n, out_n = best(lxln, name, a.n)
        if out_n != out_c:
            raise SystemExit(f"{name}: outputs differ: C {out_c!r}, native {out_n!r}")
        t_o, out_o = (best(lxlo, name, a.n) if lxlo else (None, None))
        if lxlo and out_o != out_c:
            raise SystemExit(f"{name}: outputs differ: C {out_c!r}, native -O {out_o!r}")
        t_r, out_r = (best(RUST_EXE, name, a.n) if RUST_EXE else (None, None))
        if RUST_EXE and out_r != out_c:
            raise SystemExit(f"{name}: outputs differ: lxl {out_c!r}, Rust {out_r!r}")
        t_j = m_j = None
        if JAVA_CP:
            t_j, out_j, m_j = java_run(name, a.n)
            if out_j != out_c:
                raise SystemExit(f"{name}: outputs differ: lxl {out_c!r}, Java {out_j!r}")
        rows.append(dict(
            name=name, c=t_c, n=t_n, o=t_o, rust=t_r, java=t_j,
            mn=peak_run(lxlo or lxln, name), mr=peak_run(RUST_EXE, name), mj=m_j,
            out=out_c,
        ))

    if a.opt:
        print("| benchmark | via C | native | native -O | -O/C | Rust (AVX2) | -O/Rust | Java (Vector API) | -O/Java | output |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for r in rows:
            rs = fmt(r['rust']) if r['rust'] is not None else "-"
            ors = f"{r['o'] / r['rust']:.2f}" if r['rust'] else "-"
            js = fmt(r['java']) if r['java'] is not None else "-"
            ojs = f"{r['o'] / r['java']:.2f}" if r['java'] else "-"
            print(f"| {r['name']} | {fmt(r['c'])} | {fmt(r['n'])} | {fmt(r['o'])} | "
                  f"{r['o'] / r['c']:.2f} | {rs} | {ors} | {js} | {ojs} | {r['out']} |")
    else:
        print("| benchmark | via C | native | native/C | Rust (AVX2) | native/Rust | Java (Vector API) | native/Java | output |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for r in rows:
            rs = fmt(r['rust']) if r['rust'] is not None else "-"
            nrs = f"{r['n'] / r['rust']:.2f}" if r['rust'] else "-"
            js = fmt(r['java']) if r['java'] is not None else "-"
            njs = f"{r['n'] / r['java']:.2f}" if r['java'] else "-"
            print(f"| {r['name']} | {fmt(r['c'])} | {fmt(r['n'])} | {r['n'] / r['c']:.2f} | "
                  f"{rs} | {nrs} | {js} | {njs} | {r['out']} |")

    if any(r['mn'] is not None for r in rows):
        print()
        def mb(x):
            return f"{x:.1f} MB" if x is not None else "-"
        print(f"| benchmark | {'native -O' if a.opt else 'native'} peak | Rust peak | Java peak |")
        print("|---|---:|---:|---:|")
        for r in rows:
            print(f"| {r['name']} | {mb(r['mn'])} | {mb(r['mr'])} | {mb(r['mj'])} |")


if __name__ == '__main__':
    main()
