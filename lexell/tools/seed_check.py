#!/usr/bin/env python3
"""The C seed's fixed point, as compiler/reseed.sh checks it, without writing the seed.

    python3 lexell/tools/seed_check.py

1. out/lxlc is built from compiler/seed/lxlc.c, as compiler/build.sh does (stage 1);
2. rt.lxl must be up to date with rt.h (compiler/gen_rt.py --check);
3. stage 1 builds the current sources (stage 2), stage 2 builds them again (stage 3);
4. the C of stages 2 and 3 must be identical, and equal to the seed;
5. on x86-64 Linux, stage 1 builds the compiler natively, and that becomes out/lxlc, as
   compiler/build.sh does: every later step of the gate uses the compiler as it is shipped.

So the seed is the compiler that the sources describe, and it reproduces itself. Every gcc
build goes through the tools/cbuild.py cache, so when nothing changed the check takes
seconds. Run compiler/reseed.sh after changing the compiler.
"""
import json, os, platform, subprocess, sys, tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
COMP = os.path.normpath(os.path.join(HERE, '..', 'compiler'))
sys.path.insert(0, HERE)
import cbuild  # noqa: E402

SEED = os.path.join(COMP, 'seed', 'lxlc.c')
MAIN = os.path.join(COMP, 'main.lxl')
LXLC = os.path.join(COMP, 'out', 'lxlc')
BUILD = ['gcc', '-O2', '-w', '-std=gnu11', '-o', '@OUT@', '@SRC@', '-lm']    # as build.sh


def fail(msg):
    sys.exit(f"seed_check: {msg}")


def emit(exe):
    """(C text, gcc command) of the compiler sources, compiled by exe."""
    r = subprocess.run([exe, MAIN, '--emit-c-json'], capture_output=True, text=True,
                       env=dict(os.environ, LXL_LIB=os.path.join(COMP, '..', 'lib')))
    if r.returncode:
        fail(f"{os.path.relpath(exe, COMP)} cannot compile main.lxl:\n{r.stderr.strip()[:2000]}")
    j = json.loads(r.stdout)
    return j['c'], j['cmd']


def build(csrc, cmd, out, private=False):
    rc, err = cbuild.cc_build(csrc, cmd, out, private=private)
    if rc:
        fail(f"gcc failed building {os.path.basename(out)}:\n{err[:2000]}")


def main():
    seed = open(SEED).read()
    os.makedirs(os.path.dirname(LXLC), exist_ok=True)
    build(seed, BUILD, LXLC, private=True)   # its own file: people replace out/lxlc
    r = subprocess.run([sys.executable, os.path.join(COMP, 'gen_rt.py'), '--check'])
    if r.returncode:
        sys.exit(1)
    with tempfile.TemporaryDirectory(prefix='lxlseed_') as t:
        c1, cmd = emit(LXLC)
        build(c1, cmd, os.path.join(t, 's2'))
        c2, cmd = emit(os.path.join(t, 's2'))
        build(c2, cmd, os.path.join(t, 's3'))
        c3, _ = emit(os.path.join(t, 's3'))
    if c2 != c3:
        fail("no fixed point: the C of stages 2 and 3 differ")
    if c2 != seed:
        fail("the seed is stale: stage 2's C differs from seed/lxlc.c (run compiler/reseed.sh)")
    how = 'built from it'
    if platform.system() == 'Linux' and platform.machine() == 'x86_64':
        tmp = LXLC + '.native.tmp'
        r = subprocess.run([LXLC, MAIN, '--native', '-o', tmp], capture_output=True, text=True,
                           env=dict(os.environ, LXL_LIB=os.path.join(COMP, '..', 'lib')))
        if r.returncode:
            fail(f"out/lxlc cannot build the compiler natively:\n{r.stderr.strip()[:2000]}")
        os.replace(tmp, LXLC)
        how = 'built from it, then natively by that build (as compiler/build.sh)'
    print(f"seed/lxlc.c: fixed point, stage 2 == stage 3 == seed ({len(seed.encode())} bytes); "
          f"out/lxlc {how}")


if __name__ == '__main__':
    main()
