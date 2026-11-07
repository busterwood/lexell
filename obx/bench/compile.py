#!/usr/bin/env python3
"""Compile time and binary size: obx against Rust and C.

    python3 obx/bench/compile.py [-n RUNS] [--no-rust]

Times, best of RUNS, on one core:
- a hello world: obxc --native -O, rustc -O, gcc -O2;
- the nine benchmark programs: obx compiles each one, Rust builds the
  obx/bench/rust project (one binary with all nine), from a clean target;
- the obx compiler compiling itself with --native.

and the resulting sizes. The comparisons are not identical builds: obx emits
nine small executables, the Rust project emits one binary with nine
subcommands; cargo includes its own overhead, while obxc is invoked directly.
The point is the order of magnitude, not a byte-for-byte build-system
comparison.
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
OBXC = os.environ.get('OBXC') or os.path.join(ROOT, 'obx', 'compiler', 'out', 'obxc')
RUST_DIR = os.path.join(HERE, 'rust')
NAMES = ['fib', 'loop', 'array', 'alloc', 'lists', 'strings', 'trees', 'tokens', 'sieve']
HELLO_OBX = 'fn main() { println("hello") }\n'
HELLO_RS = 'fn main() { println!("hello"); }\n'
HELLO_C = '#include <stdio.h>\nint main(void){puts("hello");return 0;}\n'


def run(cmd, cwd=None, env=None):
    subprocess.run(cmd, cwd=cwd, env=env, check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def best(cmd, n, cwd=None, before=None):
    ts = []
    for _ in range(n):
        if before:
            before()
        t0 = time.perf_counter()
        run(cmd, cwd=cwd)
        ts.append(time.perf_counter() - t0)
    return min(ts)


def size(path):
    return os.path.getsize(path)


def fmt_s(t):
    return f'{t * 1000:.1f} ms' if t < 1 else f'{t:.2f} s'


def fmt_b(n):
    return f'{n / 1024:.0f} KB' if n < 1024 * 1024 else f'{n / 1048576:.1f} MB'


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=3)
    ap.add_argument('--no-rust', action='store_true')
    a = ap.parse_args()
    rustc, cargo, gcc = shutil.which('rustc'), shutil.which('cargo'), shutil.which('gcc')
    rust = not a.no_rust and rustc and cargo
    if not rust:
        print('note: rustc/cargo not found; the Rust columns are omitted', file=sys.stderr)
    tmp = tempfile.mkdtemp(prefix='obxcompile_')
    try:
        hello_obx = os.path.join(tmp, 'hello_obx')
        hello_c = os.path.join(tmp, 'hello_c')
        hello_rs = os.path.join(tmp, 'hello_rs')
        for name, text in (('hello.obx', HELLO_OBX), ('hello.c', HELLO_C), ('hello.rs', HELLO_RS)):
            with open(os.path.join(tmp, name), 'w') as f:
                f.write(text)
        t_obx = best([OBXC, os.path.join(tmp, 'hello.obx'), '--native', '-O', '-o', hello_obx], a.n)
        t_c = best([gcc, '-O2', os.path.join(tmp, 'hello.c'), '-o', hello_c], a.n)
        t_rs = best([rustc, '-O', '-C', 'target-cpu=x86-64-v3', '-C', 'strip=symbols',
                     os.path.join(tmp, 'hello.rs'), '-o', hello_rs], a.n) if rust else None

        # The nine benchmark programs: obx builds nine executables, Rust one
        # binary with nine subcommands.
        def compile_obx_suite():
            for name in NAMES:
                run([OBXC, os.path.join(HERE, name + '.obx'), '--native', '-O',
                     '-o', os.path.join(tmp, name + '.bin')])
        ts = []
        for _ in range(a.n):
            t0 = time.perf_counter()
            compile_obx_suite()
            ts.append(time.perf_counter() - t0)
        t_obx_suite = min(ts)
        obx_total = sum(size(os.path.join(tmp, n + '.bin')) for n in NAMES)
        t_rs_suite = None
        rs_bin = os.path.join(RUST_DIR, 'target', 'release', 'dbench')
        if rust:
            def clean_build():
                run(['cargo', 'clean'], cwd=RUST_DIR)
                run(['cargo', 'build', '--release', '--offline'], cwd=RUST_DIR)
            ts = []
            for _ in range(a.n):
                t0 = time.perf_counter()
                clean_build()
                ts.append(time.perf_counter() - t0)
            t_rs_suite = min(ts)

        self_exe = os.path.join(tmp, 'obxc_self')
        t_self = best([OBXC, os.path.join(ROOT, 'obx', 'compiler', 'main.obx'),
                       '--native', '-o', self_exe], a.n)

        print('| what | obx | Rust | C |')
        print('|---|---:|---:|---:|')
        print(f'| hello, compile ({a.n} best) | {fmt_s(t_obx)} | '
              f'{fmt_s(t_rs) if t_rs is not None else "-"} | {fmt_s(t_c)} |')
        print(f'| hello, binary | {fmt_b(size(hello_obx))} | '
              f'{fmt_b(size(hello_rs)) if t_rs is not None else "-"} | {fmt_b(size(hello_c))} |')
        print(f'| nine benchmarks, clean compile | {fmt_s(t_obx_suite)} | '
              f'{fmt_s(t_rs_suite) if t_rs_suite is not None else "-"} | - |')
        print(f'| nine benchmarks, binaries | {fmt_b(obx_total)} | '
              f'{fmt_b(size(rs_bin)) if t_rs_suite is not None else "-"} | - |')
        print(f'| compiler self-build | {fmt_s(t_self)} | - | - |')
        print(f'| compiler binary | {fmt_b(size(self_exe))} | - | - |')
        print()
        print('Note: obx emits nine executables; the Rust project emits one binary with nine')
        print('subcommands and cargo measures its own build system. Compare orders of')
        print('magnitude, not the build systems byte for byte.')
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    main()
