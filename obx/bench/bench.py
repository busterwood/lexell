#!/usr/bin/env python3
"""obx benchmark table: native against C, and optionally the archived obo.

For each program NAME it builds obx/bench/NAME.obx twice with the compiler
(obx/compiler/out/obxc, or $OBXC): through C (gcc -O2) and with --native.
With --obo it also builds archive/obo/bench/NAME_obo.obx with the archived
obo compiler (archive/obo/obo, if it runs). It checks that the outputs are
equal and that both obx programs are leak free (OBX_CHECK=1), then prints the
best wall time of N runs of each. A program with a hand-written C reference,
obx/bench/c/NAME.c (no checks), also gets it built with gcc -O2 and timed, as
the "plain C" column ("-" for the others). The Rust ports in rust/ are built
once with `cargo build --release` and timed as the "Rust" column ("-" for
`maps`, which has no reference, and when cargo is missing or --no-rust is
given). Their output must equal the obx output.

    python3 obx/bench/bench.py [-n RUNS] [--only NAME ...] [--obo] [--opt] [--perf]
                              [--no-rust] [--hash-seed N | --random-hash]

The primary comparison is the same obx source built both ways (native and
through C). The hand-written C and Rust references in c/ and rust/ are a
second, same-algorithm comparison; README.md says what each reference does to
keep the work equal. --perf adds instructions and cycles (user mode) beside
the wall times.

Every program runs with OBX_HASH_SEED=42 (--hash-seed changes it), so the
random per-process hash key of std.Map does not move the maps timings between
runs or between the two backends; --random-hash runs with the production
default instead. The output is identical either way (Map keeps insertion
order).
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
OBO = os.path.join(ROOT, 'archive', 'obo')
OBO_SRC = os.path.join(OBO, 'bench')
NAMES = ['fib', 'loop', 'array', 'alloc', 'lists', 'strings', 'trees', 'tokens', 'sieve', 'maps']
TOKENS_INPUT = os.path.join(ROOT, 'obx', 'compiler', 'sema.obx')   # any text file; same for both
RUST_DIR = os.path.join(HERE, 'rust')
# maps has no Rust reference: obx's Map is insertion-ordered and keyed-hashed,
# with u32 index slots; there is no direct std equivalent.
RUST_NAMES = {'fib', 'loop', 'array', 'alloc', 'lists', 'strings', 'trees', 'tokens', 'sieve'}
HASH_SEED = None     # set from the command line; see base_env
RUST_EXE = None      # the one dbench binary, once built


def args_for(name):
    return [TOKENS_INPUT] if name == 'tokens' else []


def cmd_for(exe, name):
    """The Rust binary takes the benchmark name as its first argument."""
    return [exe, name] if RUST_EXE is not None and exe == RUST_EXE else [exe]


def base_env(env_extra=None):
    env = dict(os.environ)
    env.pop('OBX_CHECK', None)
    env.pop('OBO_CHECK', None)
    if HASH_SEED is None:
        env.pop('OBX_HASH_SEED', None)
    else:
        env['OBX_HASH_SEED'] = HASH_SEED
    env.update(env_extra or {})
    return env


def run(exe, name, env_extra=None):
    env = base_env(env_extra)
    t0 = time.perf_counter()
    p = subprocess.run(cmd_for(exe, name) + args_for(name), capture_output=True, text=True, env=env)
    return p.returncode, p.stdout.strip(), p.stderr.strip(), time.perf_counter() - t0


def best(exe, name, n):
    ts = []
    for _ in range(n):
        code, out, err, dt = run(exe, name)
        if code != 0:
            raise SystemExit(f"{exe} exited {code}: {err}")
        ts.append(dt)
    return min(ts), out


def perf_run(exe, name, n):
    """Best wall time, and the least instructions/cycles (user mode), of n runs."""
    ts, ins, cyc, outs = [], [], [], set()
    for _ in range(n):
        t0 = time.perf_counter()
        p = subprocess.run(['perf', 'stat', '-x,', '-e', 'instructions:u,cycles:u']
                           + cmd_for(exe, name) + args_for(name),
                           capture_output=True, text=True, env=base_env())
        dt = time.perf_counter() - t0
        if p.returncode != 0:
            raise SystemExit(f"{exe} exited {p.returncode}: {p.stderr}")
        outs.add(p.stdout.strip())
        vals = {}
        for line in p.stderr.splitlines():
            f = line.split(',')
            if len(f) > 2 and f[0].isdigit():
                vals[f[2].split(':')[0]] = int(f[0])
        if 'instructions' not in vals or 'cycles' not in vals:
            raise SystemExit(f"perf did not report instructions/cycles for {exe}")
        ts.append(dt)
        ins.append(vals['instructions'])
        cyc.append(vals['cycles'])
    if len(outs) != 1:
        raise SystemExit(f"{name}: runs print different output: {sorted(outs)}")
    return min(ts), outs.pop(), min(ins), min(cyc)


def build_obx(name, tmp, native=False, opt=False):
    exe = os.path.join(tmp, name + ('_obxn' if native else '_obx') + ('_O' if opt else ''))
    flags = (['--native'] if native else []) + (['-O'] if opt else [])
    subprocess.run([OBXC, os.path.join(HERE, name + '.obx'), '-o', exe] + flags, check=True)
    return exe


def build_c(name, tmp):
    src = os.path.join(HERE, 'c', name + '.c')
    if not os.path.exists(src):
        return None
    exe = os.path.join(tmp, name + '_plainc')
    # No sibling-call optimisation: obx does not turn recursion into a loop,
    # and fib's reference is about the call tree, not gcc removing it.
    subprocess.run(['gcc', '-O2', '-fno-optimize-sibling-calls', src, '-o', exe], check=True)
    return exe


def build_rust():
    """Build the Rust reference once; None when cargo is unavailable."""
    if not shutil.which('cargo'):
        return None
    r = subprocess.run(['cargo', 'build', '--release', '--offline', '--quiet'], cwd=RUST_DIR)
    if r.returncode != 0:
        print('note: the Rust reference did not build; Rust column skipped', file=sys.stderr)
        return None
    return os.path.join(RUST_DIR, 'target', 'release', 'dbench')


def build_obo(name, tmp):
    exe = os.path.join(tmp, name + '_obo')
    compiler = os.path.join(OBO, 'obo')
    r = subprocess.run([compiler, os.path.join(OBO_SRC, name + '_obo.obx'), '-o', exe, '--rt', OBO],
                       capture_output=True, text=True)
    if r.returncode != 0:
        return None
    return exe


def fmt(t):
    return f"{t * 1000:.0f} ms" if t is not None else "n/a"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-n', type=int, default=5, help='runs per program (best is reported)')
    ap.add_argument('--only', nargs='*')
    ap.add_argument('--obo', action='store_true', help='add the archived obo compiler as a column')
    ap.add_argument('--opt', action='store_true', help='also build native with -O and add its columns')
    ap.add_argument('--perf', action='store_true',
                    help='also report instructions and cycles (perf stat, user mode)')
    ap.add_argument('--no-rust', action='store_true', help='skip the Rust reference column')
    ap.add_argument('--hash-seed', type=int, default=42,
                    help='OBX_HASH_SEED for the runs (default 42; makes maps reproducible)')
    ap.add_argument('--random-hash', action='store_true',
                    help='run with the production per-process random hash key')
    a = ap.parse_args()
    global HASH_SEED, RUST_EXE
    HASH_SEED = None if a.random_hash else str(a.hash_seed)
    names = a.only or NAMES
    tmp = tempfile.mkdtemp(prefix='obxbench')
    rows = []
    if not a.no_rust and not a.obo:
        RUST_EXE = build_rust()
        if RUST_EXE is None and shutil.which('cargo') is None:
            print('note: cargo not found; Rust column skipped', file=sys.stderr)

    def timed(exe):
        if exe is None:
            return None, None, None, None
        if a.perf:
            return perf_run(exe, name, a.n)
        t, out = best(exe, name, a.n)
        return t, out, None, None

    for name in names:
        obx = build_obx(name, tmp)
        obxn = build_obx(name, tmp, native=True)
        obxo = build_obx(name, tmp, native=True, opt=True) if a.opt else None
        obo = build_obo(name, tmp) if a.obo else None
        plain = build_c(name, tmp)
        rust = RUST_EXE if name in RUST_NAMES else None
        for exe in (obx, obxn) + ((obxo,) if obxo else ()):
            code, out, err, _ = run(exe, name, {'OBX_CHECK': '1'})
            if code != 0:
                raise SystemExit(f"{name}: {exe} with OBX_CHECK=1 exited {code}: {err}")
        t_obx, out_obx, i_obx, c_obx = timed(obx)
        t_obxn, out_obxn, i_obxn, c_obxn = timed(obxn)
        if out_obxn != out_obx:
            raise SystemExit(f"{name}: outputs differ: C {out_obx!r}, native {out_obxn!r}")
        t_obxo, out_obxo, i_obxo, c_obxo = timed(obxo)
        if obxo is not None and out_obxo != out_obx:
            raise SystemExit(f"{name}: outputs differ: C {out_obx!r}, native -O {out_obxo!r}")
        t_obo, out_obo = (None, None)
        if obo:
            t_obo, out_obo = best(obo, name, a.n)
        if obo and out_obo != out_obx:
            raise SystemExit(f"{name}: outputs differ: obx {out_obx!r}, obo {out_obo!r}")
        t_plain, out_plain, i_plain, c_plain = timed(plain)
        if plain and out_plain != out_obx:
            raise SystemExit(f"{name}: outputs differ: obx {out_obx!r}, plain C {out_plain!r}")
        t_rust, out_rust, i_rust, c_rust = timed(rust)
        if rust and out_rust != out_obx:
            raise SystemExit(f"{name}: outputs differ: obx {out_obx!r}, Rust {out_rust!r}")
        rows.append(dict(name=name, obo=t_obo, c=t_obx, n=t_obxn, o=t_obxo, plain=t_plain, rust=t_rust,
                         out=out_obx,
                         ci=i_obx, ni=i_obxn, oi=i_obxo, pi=i_plain, ri=i_rust,
                         cc=c_obx, nc=c_obxn, oc=c_obxo, pc=c_plain, rc=c_rust))
    if a.obo:
        if all(r['obo'] is None for r in rows):
            print("note: the obo compiler did not build anything; obo columns skipped", file=sys.stderr)
        print("| benchmark | obo | obx via C | obx native | C/obo | native/obo | output |")
        print("|---|---:|---:|---:|---:|---:|---|")
        for r in rows:
            t_obo = r['obo']
            cr = f"{r['c'] / t_obo:.2f}" if t_obo else "n/a"
            nr = f"{r['n'] / t_obo:.2f}" if t_obo else "n/a"
            print(f"| {r['name']} | {fmt(t_obo)} | {fmt(r['c'])} | {fmt(r['n'])} | {cr} | {nr} | {r['out']} |")
        return
    if a.opt:
        print("| benchmark | via C | native | native -O | -O/C | plain C | -O/plain C | Rust | -O/Rust | output |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---|")
        for r in rows:
            pc = fmt(r['plain']) if r['plain'] is not None else "-"
            opc = f"{r['o'] / r['plain']:.2f}" if r['plain'] else "-"
            rs = fmt(r['rust']) if r['rust'] is not None else "-"
            ors = f"{r['o'] / r['rust']:.2f}" if r['rust'] else "-"
            print(f"| {r['name']} | {fmt(r['c'])} | {fmt(r['n'])} | {fmt(r['o'])} | "
                  f"{r['o'] / r['c']:.2f} | {pc} | {opc} | {rs} | {ors} | {r['out']} |")
    else:
        print("| benchmark | via C | native | native/C | plain C | native/plain C | Rust | native/Rust | output |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---|")
        for r in rows:
            pc = fmt(r['plain']) if r['plain'] is not None else "-"
            npc = f"{r['n'] / r['plain']:.2f}" if r['plain'] else "-"
            rs = fmt(r['rust']) if r['rust'] is not None else "-"
            nrs = f"{r['n'] / r['rust']:.2f}" if r['rust'] else "-"
            print(f"| {r['name']} | {fmt(r['c'])} | {fmt(r['n'])} | {r['n'] / r['c']:.2f} | "
                  f"{pc} | {npc} | {rs} | {nrs} | {r['out']} |")
    if a.perf:
        print()
        def m(x):
            return f"{x / 1e6:.1f}" if x is not None else "-"
        if a.opt:
            print("| benchmark | C Mcyc | native Mcyc | -O Mcyc | -O/C | plain Mcyc | -O/plain | "
                  "C Minstr | -O Minstr | -O/C |")
            print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            for r in rows:
                opc = f"{r['oc'] / r['pc']:.2f}" if r['pc'] else "-"
                print(f"| {r['name']} | {m(r['cc'])} | {m(r['nc'])} | {m(r['oc'])} | {r['oc'] / r['cc']:.2f} | "
                      f"{m(r['pc'])} | {opc} | {m(r['ci'])} | {m(r['oi'])} | {r['oi'] / r['ci']:.2f} |")
        else:
            print("| benchmark | C Minstr | native Minstr | native/C | C Mcyc | native Mcyc | native/C | "
                  "plain Minstr | plain Mcyc | native/plain cyc |")
            print("|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|")
            for r in rows:
                npc = f"{r['nc'] / r['pc']:.2f}" if r['pc'] else "-"
                print(f"| {r['name']} | {m(r['ci'])} | {m(r['ni'])} | {r['ni'] / r['ci']:.2f} | "
                      f"{m(r['cc'])} | {m(r['nc'])} | {r['nc'] / r['cc']:.2f} | "
                      f"{m(r['pi'])} | {m(r['pc'])} | {npc} |")


if __name__ == '__main__':
    main()
