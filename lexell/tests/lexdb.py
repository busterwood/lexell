#!/usr/bin/env python3
"""Runs the lexdb tests (tests/lexdb/run) with the conformance runner
(run.py: the same // expect: directives; run tests under LXL_CHECK=1).

    python3 lexell/tests/lexdb.py [--compiler PATH] [-j N] [--no-bundle]
                                  [--bundle-size N] [filters...]

lexdb is the SQL server in cmd/lexdb*.lxl (design/lexdb.md). The module
dependency rule (tests/lexdb/imports.py) is checked first.

By default, eligible single-file run tests are grouped by import tier (core,
exec, wire, tds, tns) into a small number of bundled binaries so lexdb is
compiled ~10 times instead of 370+ times. Each test still executes in its own
subprocess with its own temp directory, timeout, and LXL_CHECK=1 leak check.
If a bundle fails to compile, its tests automatically fall back to standalone
compilation so diagnostics point to the exact failing file. Pass --no-bundle
to compile every test individually."""
import argparse
import importlib.util
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, '..', 'tools'))
import cbuild  # noqa: E402


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


MAIN_LINE_RE = re.compile(r'^\s*(?:pub\s+)?fn\s+main\b')
REL_IMPORT_RE = re.compile(r'^(\s*import\s+")(\.\.?/[^"]+)(".*)$')
MOD_IMPORT_RE = re.compile(r'^\s*import\s+"[^"]+/([A-Za-z0-9_]+)"')
TIMEOUT_RE = re.compile(r'^\s*//\s*timeout:\s*([0-9]+(?:\.[0-9]+)?)')
ENTRY_FN = '_lxl_bundle_run'
BUNDLE_COMPILE_TIMEOUT = 180
DEFAULT_RUN_TIMEOUT = 30  # lexdb tests can take 4-6s uncontended, >10s under heavy SMT load


def classify_and_check(kind, path):
    """Return (eligible, tier, src, timeout) for a test.

    Ineligible tests (error tests, multi-file main.lxl directories, tests with
    // needs:, non-standard main(), or args() usage) run standalone via run.py.
    """
    if kind != 'run' or os.path.basename(path) == 'main.lxl':
        return False, None, None, 0.0
    try:
        with open(path, encoding='utf-8', errors='replace') as f:
            src = f.read()
    except OSError:
        return False, None, None, 0.0
    if ENTRY_FN in src:
        return False, None, None, 0.0
    lines = src.splitlines()
    main_idx = []
    imps = set()
    timeout = 0.0
    for i, line in enumerate(lines):
        if runner.NEEDS.match(line):
            return False, None, None, 0.0
        tm = TIMEOUT_RE.match(line)
        if tm:
            timeout = float(tm.group(1))
        if MAIN_LINE_RE.match(line):
            main_idx.append(i)
        s = line.lstrip()
        if s.startswith('import '):
            if ('./' in s or '../' in s) and not REL_IMPORT_RE.match(line):
                return False, None, None, 0.0
            m = MOD_IMPORT_RE.match(line)
            if m:
                imps.add(m.group(1))
        elif not s.startswith('//') and re.search(r'\bargs\s*\(', line):
            return False, None, None, 0.0
    if len(main_idx) != 1 or lines[main_idx[0]].strip() != 'fn main() {':
        return False, None, None, 0.0
    if 'lexdb_tns' in imps:
        tier = 'tns'
    elif 'lexdb_tds' in imps:
        tier = 'tds'
    elif 'lexdb_wire' in imps:
        tier = 'wire'
    elif 'lexdb_exec' in imps:
        tier = 'exec'
    else:
        tier = 'core'
    return True, tier, src, timeout


def rewrite_test_src(src, orig_path, bundle_dir):
    """Rewrite a single test source into a bundleable module in bundle_dir.

    Preserves line numbers 1:1 so stack traces and panic line numbers match.
    """
    orig_dir = os.path.dirname(os.path.abspath(orig_path))
    out = []
    replaced_main = False
    for line in src.splitlines():
        if not replaced_main and MAIN_LINE_RE.match(line):
            out.append(line.replace('fn main() {', f'pub fn {ENTRY_FN}() {{', 1))
            replaced_main = True
            continue
        m = REL_IMPORT_RE.match(line)
        if m:
            target = os.path.normpath(os.path.join(orig_dir, m.group(2)))
            rel = os.path.relpath(target, bundle_dir).replace(os.sep, '/')
            if not rel.startswith('./') and not rel.startswith('../'):
                rel = './' + rel
            out.append(m.group(1) + rel + m.group(3))
            continue
        out.append(line)
    return '\n'.join(out) + '\n'


def build_bundle(items, compiler):
    """Generate and compile one bundle containing items=[(kind, path, src), ...].

    Returns (bundle_dir, exe_path_or_None). Caller owns bundle_dir cleanup.
    """
    bundle_dir = tempfile.mkdtemp(prefix='lxlbundle_')
    imports = []
    dispatch = []
    for idx, (_kind, path, src) in enumerate(items):
        mod = f't{idx}'
        mod_path = os.path.join(bundle_dir, mod + '.lxl')
        with open(mod_path, 'w', encoding='utf-8') as f:
            f.write(rewrite_test_src(src, path, bundle_dir))
        imports.append(f'import "./{mod}"')
        dispatch.append(f'    if k == "{idx}" {{\n        {mod}.{ENTRY_FN}()\n        return\n    }}')

    driver_src = (
        '\n'.join(imports) + '\n\n'
        'fn main() {\n'
        '    let argv = args()\n'
        '    if len(argv) < 2 {\n'
        '        eprintln("lexdb bundle: missing test index")\n'
        '        exit(2)\n'
        '    }\n'
        '    let k = &argv[1]\n'
        + '\n'.join(dispatch) + '\n'
        '    eprintln("lexdb bundle: unknown test " + k)\n'
        '    exit(2)\n'
        '}\n'
    )
    driver_path = os.path.join(bundle_dir, 'driver.lxl')
    with open(driver_path, 'w', encoding='utf-8') as f:
        f.write(driver_src)

    exe = os.path.join(bundle_dir, 'bundle')
    timeout = max(runner.COMPILE_TIMEOUT, BUNDLE_COMPILE_TIMEOUT)
    try:
        rc, _out, _err = cbuild.build_lxl(
            driver_path, exe, lxlc=os.path.abspath(compiler), timeout=timeout, cwd=bundle_dir)
    except (subprocess.TimeoutExpired, OSError):
        return bundle_dir, None
    if rc != 0:
        return bundle_dir, None
    return bundle_dir, exe


def run_bundled_test(exe, idx, path):
    """Execute one test from a compiled bundle with the exact run.py contract."""
    rel = os.path.relpath(path, runner.HERE)
    d = runner.parse_directives(path)
    with tempfile.TemporaryDirectory(prefix='lxltest_') as tmp:
        env = dict(os.environ, LXL_CHECK='1')
        stdin = ''.join(l + '\n' for l in d['stdin'])
        try:
            r = subprocess.run(
                [exe, str(idx)], input=stdin, capture_output=True, text=True,
                errors='replace', timeout=d['timeout'] or DEFAULT_RUN_TIMEOUT,
                env=env, cwd=tmp)
        except subprocess.TimeoutExpired:
            return rel, 'run timeout'
        if r.returncode == runner.SKIP_EXIT and d['exit'] != runner.SKIP_EXIT:
            return rel, runner.SKIP
        want = ''.join(l + '\n' for l in d['expect'])
        if r.stdout != want:
            return rel, 'stdout differs\n  want: %r\n  got:  %r\n  stderr: %s' % (
                want, r.stdout, r.stderr.strip()[:200])
        if r.returncode != d['exit']:
            return rel, 'exit code %d, want %d (stderr: %s)' % (
                r.returncode, d['exit'], r.stderr.strip()[:200])
        werr = ''.join(l + '\n' for l in d['stderr'])
        if d['stderr'] and r.stderr != werr:
            return rel, 'stderr differs\n  want: %r\n  got:  %r' % (werr, r.stderr)
        return rel, None


def _split_chunks(items, bundle_size, bundles, standalone):
    if len(items) < 2:
        for kind, path, _src in items:
            standalone.append((kind, path))
        return
    n_chunks = max(1, math.ceil(len(items) / bundle_size))
    base, rem = divmod(len(items), n_chunks)
    pos = 0
    for c in range(n_chunks):
        sz = base + (1 if c < rem else 0)
        chunk = items[pos:pos + sz]
        pos += sz
        if len(chunk) < 2:
            for kind, path, _src in chunk:
                standalone.append((kind, path))
        else:
            bundles.append(chunk)


def partition_bundles(tests, bundle_size):
    """Split tests into (bundles, standalone).

    Tests with explicit // timeout: directives are sorted first (LPT order) and,
    in large tiers, grouped into the first priority bundle(s) so long-running
    tests start executing as soon as the earliest bundle finishes compiling.
    """
    tiers = {}
    standalone = []
    for kind, path in tests:
        ok, tier, src, timeout = classify_and_check(kind, path)
        if not ok:
            standalone.append((kind, path))
        else:
            tiers.setdefault(tier, []).append((timeout, kind, path, src))

    bundles = []
    # Build tiers with the longest-running tests first so critical-path tests
    # begin executing as early as possible.
    for tier in ('exec', 'core', 'tds', 'tns', 'wire'):
        items = tiers.get(tier, [])
        if not items:
            continue
        items.sort(key=lambda x: (-x[0], x[2]))
        if len(items) > bundle_size:
            slow = [(k, p, s) for t, k, p, s in items if t > 0]
            fast = [(k, p, s) for t, k, p, s in items if t <= 0]
            if len(slow) >= 2 and len(fast) >= 2:
                _split_chunks(slow, bundle_size, bundles, standalone)
                _split_chunks(fast, bundle_size, bundles, standalone)
                continue
        _split_chunks([(k, p, s) for _t, k, p, s in items], bundle_size, bundles, standalone)
    return bundles, standalone


def run_all(tests, compiler, workers, use_bundle, bundle_size):
    if not use_bundle or len(tests) < 2 or bundle_size < 2:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            return list(ex.map(lambda t: runner.run_test(t[0], t[1], compiler), tests))

    bundles, standalone = partition_bundles(tests, bundle_size)
    results_by_rel = {}
    bundle_dirs = []

    try:
        # Phase 1: compile bundles in parallel while also running standalone tests.
        # As each bundle finishes compiling, immediately schedule its test runs
        # on the same pool so fast tiers start executing while slower tiers build.
        with ThreadPoolExecutor(max_workers=workers) as ex:
            standalone_futs = [ex.submit(runner.run_test, k, p, compiler) for k, p in standalone]
            build_futs = {ex.submit(build_bundle, items, compiler): items for items in bundles}
            run_futs = []

            for bf in as_completed(build_futs):
                items = build_futs[bf]
                bdir, exe = bf.result()
                bundle_dirs.append(bdir)
                if exe is None:
                    # Bundle failed to compile: fall back to per-test compilation
                    # so errors report the exact failing file and line.
                    for kind, path, _src in items:
                        run_futs.append(ex.submit(runner.run_test, kind, path, compiler))
                else:
                    for idx, (_kind, path, _src) in enumerate(items):
                        run_futs.append(ex.submit(run_bundled_test, exe, idx, path))

            for f in standalone_futs:
                rel, err = f.result()
                results_by_rel[rel] = err
            for f in run_futs:
                rel, err = f.result()
                results_by_rel[rel] = err
    finally:
        for bdir in bundle_dirs:
            shutil.rmtree(bdir, ignore_errors=True)

    return [(os.path.relpath(p, runner.HERE), results_by_rel[os.path.relpath(p, runner.HERE)])
            for _k, p in tests]


def main():
    imports = load('lexdb_imports', os.path.join(HERE, 'lexdb', 'imports.py'))
    if imports.main() != 0:
        sys.exit(1)

    ap = argparse.ArgumentParser()
    ap.add_argument('--compiler', default=cbuild.LXLC)
    ap.add_argument('-j', type=int, default=os.cpu_count() or 4)
    ap.add_argument('--live', action='store_true', help='also the tests that need a live service')
    ap.add_argument('--no-bundle', action='store_true', help='compile every test individually')
    ap.add_argument('--bundle-size', type=int, default=50, help='max tests per compiled bundle (default 50)')
    ap.add_argument('filters', nargs='*')
    a = ap.parse_args()

    all_tests = runner.find_tests(True)
    if a.filters:
        all_tests = [t for t in all_tests
                     if any(f in os.path.relpath(t[1], runner.HERE) for f in a.filters)]
    tests = all_tests if a.live else [t for t in all_tests if not runner.is_live(t[1])]
    live_skipped = len(all_tests) - len(tests)

    results = run_all(tests, a.compiler, a.j, not a.no_bundle, a.bundle_size)

    failed = skipped = 0
    for rel, err in results:
        if err == runner.SKIP:
            skipped += 1
        elif err:
            failed += 1
            print('FAIL %s: %s' % (rel, err))
    print('%d passed, %d failed%s%s' % (
        len(results) - failed - skipped, failed,
        ', %d skipped (a library or service missing)' % skipped if skipped else '',
        ', %d live not run (use --live)' % live_skipped if live_skipped else ''))
    sys.exit(1 if failed else 0)


runner = load('conformance', os.path.join(HERE, 'run.py'))
runner.HERE = os.path.join(HERE, 'lexdb')
runner.RUN_TIMEOUT = DEFAULT_RUN_TIMEOUT

if __name__ == '__main__':
    main()
