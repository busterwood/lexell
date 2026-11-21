#!/usr/bin/env python3
"""The lexdb census (design/lexdb-layers.md 6.4): which runs the row engine
still makes, and why the pipeline declined each.

    lexell/tools/lexdb_census.py copy DIR [--cover=MOD,...] [--force-batch]
                                               a census copy of lexell in DIR
    lexell/tools/lexdb_census.py sum FILE...   the lines summed per reason
    lexell/tools/lexdb_census.py uncovered MOD FILE...
                                               MOD's functions no run entered

--cover=lexdb_exec,...: each top-level function of those modules notes its
first entry in a process (a "cover" line); --force-batch: with
LEXDB_CENSUS_FORCE=1 set, SET lexdb_batch = off is ignored, so a covered
suite run shows the code only the tests' reference (the row engine with
batches off) reaches.

copy: DIR/lexell holds cmd, lib, tests, tools and compiler/out/lxlc (build
the compiler first) with cmd/lexdb_census.lxl's ON set true, every
`// census: <call>` hook comment made code (the hooks on the paths the
pipeline takes, which a normal build must not pay for), and the suite's
runner setting LEXDB_CENSUS_TEST to each test's name. Then, from DIR:

    LEXDB_CENSUS=FILE python3 lexell/tests/lexdb.py --compiler lexell/compiler/out/lxlc
    lexell/compiler/out/lxlc lexell/cmd/lexdb.lxl -O -o lexdb-census

and a server run with LEXDB_CENSUS=FILE (and LEXDB_CENSUS_TEST=a label)
writes its lines too. sum: per engine, then per reason of the row engine's
runs (and the writes' and set operations'): runs, distinct statements,
tests, an example."""
import collections
import os
import re
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
HOOK = re.compile(r'^(\s*)// census: (.*)$')


FN = re.compile(r'^(?:pub )?fn (?:\([^)]*\) )?([A-Za-z_][A-Za-z0-9_]*)\(')


def cover(lines, name, base):
    """Each top-level function of a module's lines entered through lexdb_census.hit (one-line ones left out)."""
    out = []
    i = 0
    k = 0
    while i < len(lines):
        l = lines[i]
        out.append(l)
        m = FN.match(l)
        if m and not l.rstrip().endswith('}'):
            j = i
            while not lines[j].split('//')[0].rstrip().endswith('{'):
                j += 1
                out.append(lines[j])
            out.append('    lexdb_census.hit(%d, "%s.%s")' % (base + k, name, m.group(1)))
            k += 1
            i = j
        i += 1
    return out, k


BLOCK = re.compile(r'^(?:if |\} else if |\} else \{$|else \{$|else if |for |while |[A-Za-z_"0-9-][A-Za-z0-9_.", -]*(?:\(.*\))? \{$|.*\bfn\(.*\{$)')
NOT_BLOCK = re.compile(r'^(?:match |let |var |return |fn |pub )|[A-Za-z0-9_]\{$')


EXPR_HEAD = re.compile(r'(?:=|return|\(|,|:) *match\b')


def blocks(lines, name, base):
    """Each block of a module's functions that holds statements (an if's, an else's, a loop's, a match arm's, a
    closure's: a line ending with "{"; not a branch of an if or match expression) entered through
    lexdb_census.hit, named MOD:LINE (the source's line)."""
    out = []
    k = 0
    body = False
    depth = 0
    head = ''
    stack = []          # per open brace: 'stmt', 'expr' (an expression's branch), 'xmatch' (a match expression), 'other'
    for i, l in enumerate(lines):
        out.append(l)
        if FN.match(l):
            body = not l.rstrip().endswith('}')
            depth = 0
            stack = []
            continue
        if l == '}':
            body = False
            continue
        if not body:
            continue
        code = l.split('//')[0].rstrip()
        s = code.strip()
        bare = re.sub(r'"(?:[^"\\]|\\.)*"', '""', s)
        bare = re.sub(r"'(?:[^'\\]|\\.)'", "''", bare)
        d0 = depth
        if d0 == 0:
            head = bare
        depth = max(0, depth + bare.count('(') + bare.count('[') - bare.count(')') - bare.count(']'))
        # the braces: leading closes, then (a line ending with "{") one block opened, others balanced
        lead = len(bare) - len(bare.lstrip('}'))
        popped = []
        for _ in range(lead):
            if stack:
                popped.append(stack.pop())
        rest = bare[lead:]
        opens = rest.endswith('{')
        net = rest.count('{') - rest.count('}') - (1 if opens else 0)
        for _ in range(-net if net < 0 else 0):
            if stack:
                stack.pop()
        for _ in range(net if net > 0 else 0):
            stack.append('other')
        if not opens:
            continue
        top = stack[-1] if stack else 'stmt'
        whole = head if d0 > 0 else bare
        closure = re.search(r'\bfn\(', rest) is not None and '}' not in rest[rest.rfind('fn('):]
        if closure:
            kind = 'stmt'                                   # a closure's body
        elif re.match(r'^ *(?:\} *)?else', bare) and popped and popped[-1] == 'expr':
            kind = 'expr'                                   # an if expression's else
        elif top in ('xmatch', 'expr'):
            kind = 'expr'                                   # a match expression's arm, a branch inside one
        elif re.search(r'\bmatch\b', whole):
            kind = 'xmatch' if EXPR_HEAD.search(whole) else 'other'
        elif re.search(r'(?:=|return|\(|,|:) *if\b', whole):
            kind = 'expr'                                   # an if expression's first branch
        else:
            kind = 'stmt'
        stack.append(kind)
        if kind != 'stmt':
            continue
        # the end of a statement written over lines: a block only after an if's, a loop's or a closure's head
        if d0 > 0 and depth == 0 and not re.match(r'^(?:if |\} else if |for |while )', head) and not closure:
            continue
        if not BLOCK.match(s) or NOT_BLOCK.search(s):
            continue
        ind = len(code) - len(code.lstrip())
        out.append(' ' * (ind + 4) + 'lexdb_census.hit(%d, "%s:%d")' % (base + k, name, i + 1))
        k += 1
    return out, k


def copy(dest, covered=(), force=False, blocked=()):
    out = os.path.join(dest, 'lexell')
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(os.path.join(out, 'compiler', 'out'))
    for d in ('cmd', 'lib', 'tests', 'tools'):
        shutil.copytree(os.path.join(ROOT, d), os.path.join(out, d), ignore=shutil.ignore_patterns('__pycache__'))
    shutil.copy2(os.path.join(ROOT, 'compiler', 'out', 'lxlc'), os.path.join(out, 'compiler', 'out', 'lxlc'))
    cmd = os.path.join(out, 'cmd')
    hooks = 0
    for name in sorted(os.listdir(cmd)):
        if not name.endswith('.lxl'):
            continue
        p = os.path.join(cmd, name)
        lines = open(p, encoding='utf-8').read().split('\n')
        n = 0
        for i, l in enumerate(lines):
            m = HOOK.match(l)
            if m:
                lines[i] = m.group(1) + m.group(2)
                n += 1
        if name == 'lexdb_census.lxl':
            s = '\n'.join(lines)
            a = 'pub const ON: bool = false'
            assert s.count(a) == 1, 'lexdb_census.lxl: no ON to set'
            lines = s.replace(a, 'pub const ON: bool = true').split('\n')
            n += 1
        if name[:-4] in blocked:
            lines, k = blocks(lines, name[:-4], 30000 + 8192 * sorted(blocked).index(name[:-4]))
            if 'import "./lexdb_census"' not in lines:
                at = max(i for i, l in enumerate(lines) if l.startswith('import '))
                lines.insert(at + 1, 'import "./lexdb_census"')
            n += 1
            print('%s: %d blocks covered' % (name, k))
        if name[:-4] in covered:
            lines, k = cover(lines, name[:-4], 4096 * sorted(covered).index(name[:-4]))
            if 'import "./lexdb_census"' not in lines:
                at = max(i for i, l in enumerate(lines) if l.startswith('import '))
                lines.insert(at + 1, 'import "./lexdb_census"')
            n += 1
            print('%s: %d functions covered' % (name, k))
        if force and name == 'lexdb_exec.lxl':
            s = '\n'.join(lines)
            a = '    rs.batch = l.batch\n'
            assert s.count(a) == 1, 'lexdb_exec.lxl: Run.limit moved'
            lines = s.replace(a, '    rs.batch = l.batch || lexdb_census.forced()\n').split('\n')
            n += 1
        if n:
            open(p, 'w', encoding='utf-8').write('\n'.join(lines))
            hooks += n
    run = os.path.join(out, 'tests', 'run.py')
    s = open(run, encoding='utf-8').read()
    a = "env = dict(os.environ, LXL_CHECK='1')"
    assert s.count(a) == 1, 'tests/run.py: the test environment line moved'
    open(run, 'w', encoding='utf-8').write(s.replace(a, "env = dict(os.environ, LXL_CHECK='1', LEXDB_CENSUS_TEST=rel)"))
    print('census copy in %s (%d changes: hooks, ON, coverage, forcing)' % (out, hooks))


def summary(paths):
    rows = []
    for path in paths:
        for l in open(path, errors='replace'):
            f = l.rstrip('\n').split('\t')
            if len(f) >= 5:
                rows.append(f[:5])
    eng = collections.Counter(r[2] for r in rows)
    tests = collections.defaultdict(set)
    for r in rows:
        tests[r[2]].add(r[0])
    print('runs by engine:', dict(eng.most_common()))
    print('tests by engine:', {k: len(v) for k, v in sorted(tests.items())})
    for want in ('row', 'dml', 'setop', 'pipe-agg'):
        per = collections.defaultdict(lambda: [0, set(), set(), '', collections.Counter()])
        for t, w, e, r, s in rows:
            if e != want:
                continue
            i = r.find(' [joins:')
            b, j = (r[:i], r[i + 2:-1]) if i >= 0 else (r, '')
            p = per[b]
            p[0] += 1
            p[1].add((t, s))
            p[2].add(t)
            if s and (not p[3] or 20 < len(s) < len(p[3])):
                p[3] = s
            p[4][w + (' ' + j.split(';')[0] if j else '')] += 1
        if not per:
            continue
        print('\n== %s: %d reasons\nruns\tstatements\ttests\treason\texample\twhere' % (want, len(per)))
        for b, p in sorted(per.items(), key=lambda kv: (-len(kv[1][1]), -kv[1][0])):
            print('%d\t%d\t%d\t%s\t%s\t%s' % (p[0], len(p[1]), len(p[2]), b or '-', p[3][:140], dict(p[4].most_common(3))))


def uncovered(module, paths):
    """module's functions no run entered (the cover lines of FILEs)."""
    seen = set()
    for path in paths:
        for l in open(path, errors='replace'):
            f = l.rstrip('\n').split('\t')
            if len(f) >= 4 and f[2] == 'cover':
                seen.add(f[3])
    lines = open(os.path.join(ROOT, 'cmd', module + '.lxl'), encoding='utf-8').read().split('\n')
    total = 0
    left = []
    for i, l in enumerate(lines):
        m = FN.match(l)
        if not m or l.rstrip().endswith('}'):
            continue
        j = i + 1
        while j < len(lines) and lines[j] != '}':
            j += 1
        total += 1
        if module + '.' + m.group(1) not in seen:
            left.append((j - i + 1, m.group(1), i + 1))
    print('%s: %d of %d functions not entered, %d lines' % (module, len(left), total, sum(x[0] for x in left)))
    for x in sorted(left, reverse=True):
        print('  %d\t%s\t:%d' % x)


def blocksleft(module, paths):
    """module's blocks (copy --blocks) no run entered, with their functions; then those entered in the first FILE
    (as the tests run) and in none of the others (another run, e.g. one with --force-batch)."""
    def seen(path):
        out = set()
        for l in open(path, errors='replace'):
            f = l.rstrip('\n').split('\t')
            if len(f) >= 4 and f[2] == 'cover' and f[3].startswith(module + ':'):
                out.add(int(f[3].split(':')[1]))
        return out
    sets = [seen(p) for p in paths]
    lines = open(os.path.join(ROOT, 'cmd', module + '.lxl'), encoding='utf-8').read().split('\n')
    names, _ = blocks(lines, module, 0)
    want = [int(l.split('"')[1].split(':')[1]) for l in names if 'lexdb_census.hit(' in l]
    fn = ''
    owner = {}
    for i, l in enumerate(lines):
        m = FN.match(l)
        if m:
            fn = m.group(1)
        owner[i + 1] = fn
    every = set().union(*sets) if sets else set()
    left = [b for b in want if b not in every]
    print('%s: %d of %d blocks not entered' % (module, len(left), len(want)))
    per = collections.Counter(owner[b] for b in left)
    for f, c in per.most_common():
        print('  %d\t%s\t%s' % (c, f, ' '.join(str(b) for b in left if owner[b] == f)[:200]))
    if len(sets) > 1:
        only = [b for b in want if b in sets[0] and not any(b in s for s in sets[1:])]
        print('%s: %d blocks entered in %s only' % (module, len(only), paths[0]))
        per = collections.Counter(owner[b] for b in only)
        for f, c in per.most_common():
            print('  %d\t%s\t%s' % (c, f, ' '.join(str(b) for b in only if owner[b] == f)[:200]))


def main():
    if len(sys.argv) >= 3 and sys.argv[1] == 'copy':
        args = sys.argv[3:]
        covered = [a.split('=', 1)[1] for a in args if a.startswith('--cover=')]
        blocked = [a.split('=', 1)[1] for a in args if a.startswith('--blocks=')]
        copy(sys.argv[2], covered=set(','.join(covered).split(',')) - {''}, force='--force-batch' in args,
             blocked=set(','.join(blocked).split(',')) - {''})
    elif len(sys.argv) >= 4 and sys.argv[1] == 'uncovered':
        uncovered(sys.argv[2], sys.argv[3:])
    elif len(sys.argv) >= 4 and sys.argv[1] == 'blocksleft':
        blocksleft(sys.argv[2], sys.argv[3:])
    elif len(sys.argv) >= 3 and sys.argv[1] == 'sum':
        summary(sys.argv[2:])
    else:
        print(__doc__)
        sys.exit(2)


if __name__ == '__main__':
    main()
