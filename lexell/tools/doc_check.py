#!/usr/bin/env python3
"""Check the ```lxl blocks of the documentation as conformance tests.

usage: doc_check.py [-j N] [--compiler PATH] [files.md ...]

Default files: every .md under lexell/docs/lang/ and the repo-root AGENTS.md.

A ```lxl block is a complete program in the format of lexell/tests/README.md:
`// expect:` lines (stdout), `// stderr:`, `// exit: N`, or `// error: words`
for a block that must fail to compile with those words in the output. A
```lxl-frag block is not compiled. Blocks are built natively (never through C),
run with LXL_CHECK=1 in a temporary directory, and judged as tests/run.py does.
One line per failure (file:line of the opening fence), then `N passed, M failed`;
exit status 1 on any failure.
"""
import argparse, importlib.util, os, re, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import cbuild  # noqa: E402


def _load_run():
    spec = importlib.util.spec_from_file_location(
        'lxl_conformance_run', os.path.join(HERE, '..', 'tests', 'run.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RUN = _load_run()
FENCE = re.compile(r'^(\s*)```(\S*)\s*$')


def default_files():
    files = [os.path.join(ROOT, 'AGENTS.md')]
    base = os.path.join(ROOT, 'lexell', 'docs', 'lang')
    for dirpath, dirnames, filenames in os.walk(base):
        dirnames.sort()
        files += [os.path.join(dirpath, f) for f in sorted(filenames) if f.endswith('.md')]
    return [f for f in files if os.path.exists(f)]


def blocks(path):
    """(line of the opening fence, source) for each ```lxl block of a markdown file."""
    out, cur, start = [], None, 0
    with open(path, encoding='utf-8') as f:
        for n, raw in enumerate(f, 1):
            line = raw.rstrip('\n')
            m = FENCE.match(line)
            if cur is None:
                if m and m.group(2) == 'lxl':
                    cur, start = [], n
                elif m:
                    cur, start = None, 0
                    # skip other fenced blocks whole, so a ```lxl inside one is not seen
                    cur = ('skip', [])
                continue
            if isinstance(cur, tuple):
                if m and m.group(2) == '':
                    cur = None
                continue
            if m and m.group(2) == '':
                out.append((start, '\n'.join(cur) + '\n'))
                cur = None
            else:
                cur.append(line)
    return out


def check(item, compiler):
    path, line, src, tmp = item
    name = '%s:%d' % (os.path.relpath(path, ROOT), line)
    with tempfile.TemporaryDirectory(prefix='lxldoc_', dir=tmp) as d:
        f = os.path.join(d, 'block.lxl')
        with open(f, 'w', encoding='utf-8') as fh:
            fh.write(src)
        dr = RUN.parse_directives(f)
        out = os.path.join(d, 'out')
        try:
            rc, so, se = cbuild.build_lxl(f, out, lxlc=compiler, timeout=RUN.COMPILE_TIMEOUT,
                                          cwd=d, backend='native')
        except subprocess.TimeoutExpired:
            return name, 'compile timeout'
        msg = (so or '') + (se or '')
        if dr['error']:
            if rc == 0:
                return name, 'compiled, but an error was expected'
            low = msg.lower()
            for want in dr['error']:
                if not any(w.strip().lower() in low for w in want.split('|')):
                    return name, 'message lacks %r; got: %s' % (want, msg.strip()[:200])
            if dr['line'] is not None and (':%d:' % dr['line']) not in msg:
                return name, 'message lacks line :%d:; got: %s' % (dr['line'], msg.strip()[:200])
            return name, None
        if rc != 0:
            return name, 'compile failed: %s' % msg.strip()[:300]
        env = dict(os.environ, LXL_CHECK='1')
        stdin = ''.join(l + '\n' for l in dr['stdin'])
        try:
            r = subprocess.run([out], input=stdin, capture_output=True, text=True, errors='replace',
                               timeout=dr['timeout'] or RUN.RUN_TIMEOUT, env=env, cwd=d)
        except subprocess.TimeoutExpired:
            return name, 'run timeout'
        want = ''.join(l + '\n' for l in dr['expect'])
        if r.stdout != want:
            return name, 'stdout differs; want %r, got %r (stderr: %s)' % (
                want, r.stdout, r.stderr.strip()[:200])
        if r.returncode != dr['exit']:
            return name, 'exit code %d, want %d (stderr: %s)' % (
                r.returncode, dr['exit'], r.stderr.strip()[:200])
        werr = ''.join(l + '\n' for l in dr['stderr'])
        if dr['stderr'] and r.stderr != werr:
            return name, 'stderr differs; want %r, got %r' % (werr, r.stderr)
        return name, None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('-j', type=int, default=os.cpu_count() or 4)
    ap.add_argument('--compiler', default=cbuild.LXLC)
    ap.add_argument('files', nargs='*')
    a = ap.parse_args()
    compiler = os.path.abspath(a.compiler)
    files = [os.path.abspath(f) for f in a.files] or default_files()
    with tempfile.TemporaryDirectory(prefix='lxldocs_') as tmp:
        items = [(p, ln, src, tmp) for p in files for ln, src in blocks(p)]
        with ThreadPoolExecutor(max_workers=a.j) as ex:
            results = list(ex.map(lambda it: check(it, compiler), items))
    failed = 0
    for name, err in results:
        if err:
            failed += 1
            print('FAIL %s: %s' % (name, ' '.join(err.split())))
    print('%d passed, %d failed' % (len(results) - failed, failed))
    sys.exit(1 if failed else 0)


if __name__ == '__main__':
    main()
