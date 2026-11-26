#!/usr/bin/env python3
"""The public API of the Lexell library, read from the sources, without bodies.

    python3 lexell/tools/libapi.py                    # every module: what it is, its most-called functions
    python3 lexell/tools/libapi.py strings            # every pub declaration of lib/strings.lxl, with its comment
    python3 lexell/tools/libapi.py collections Map    # only names containing Map (types, functions, receivers)
    python3 lexell/tools/libapi.py strings split -s   # -s: the first sentence of each comment only

Each declaration is printed as `file:line`, then its doc comment (the `//`
lines just above it), then its signature: a function up to its body, a type
with its pub fields, variants or members (private fields are counted, not
shown). std is the prelude: its names need no import or qualifier. The
library root is $LXL_LIB, else lexell/lib. Nothing here is generated or
committed, so it cannot go stale."""
import os
import textwrap
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
LIB = os.environ.get('LXL_LIB') or os.path.normpath(os.path.join(HERE, '..', 'lib'))
USES = [os.path.normpath(os.path.join(HERE, '..', d)) for d in ('cmd', 'lib', 'compiler', 'tests')]


def modules():
    return sorted(f[:-4] for f in os.listdir(LIB) if f.endswith('.lxl'))


def header(lines):
    """The module's opening comment, up to its first blank comment line."""
    out = []
    for line in lines:
        s = line.strip()
        if not s.startswith('//'):
            break
        text = s[2:].strip()
        if not text:
            if out:
                break
            continue
        out.append(text)
    return ' '.join(out)


def first_sentence(text):
    """Up to the first full stop outside parentheses and quotes."""
    depth, quote = 0, False
    for i, c in enumerate(text):
        if c == '"':
            quote = not quote
        elif quote:
            continue
        elif c in '([':
            depth += 1
        elif c in ')]':
            depth = max(0, depth - 1)
        elif c == '.' and depth == 0 and (i + 1 == len(text) or text[i + 1] == ' '):
            return text[:i + 1]
    return text


def comment_above(lines, i):
    out = []
    j = i - 1
    while j >= 0 and lines[j].strip().startswith('//'):
        out.append(lines[j].strip()[2:].strip())
        j -= 1
    out.reverse()
    # a section rule such as "// ---------- integers" is not documentation
    out = [c for c in out if not re.fullmatch(r'-+.*', c)]
    return ' '.join(c for c in out if c)


def match_group(text, i, open_, close):
    depth = 0
    for k in range(i, len(text)):
        if text[k] == open_:
            depth += 1
        elif text[k] == close:
            depth -= 1
            if depth == 0:
                return k
    return len(text) - 1


def fn_signature(lines, i):
    """`pub fn ...` up to the `{` of its body, joined onto one line."""
    text = ''
    for k in range(i, min(len(lines), i + 12)):
        text += (' ' if text else '') + lines[k].strip()
        pos = len('pub fn ')
        if text[pos:].startswith('('):                 # the receiver
            pos = match_group(text, pos, '(', ')') + 1
        p = text.find('(', pos)                        # the parameters
        if p < 0:
            continue
        q = match_group(text, p, '(', ')')
        b = text.find('{', q)                          # types hold no braces: this is the body
        if b >= 0:
            return re.sub(r'\s+', ' ', text[:b]).strip()
    return re.sub(r'\s+', ' ', text).strip()


def type_decl(lines, i):
    """A pub type: its head, then pub fields, variants or members."""
    head = re.sub(r'\s*//.*$', '', lines[i].strip())
    m = re.match(r'(.*?\{)(.*)\}$', head)
    if m:                                              # all on one line
        keep_all = 'closed' in m.group(1) or 'interface' in m.group(1)
        items = [x.strip() for x in m.group(2).split(';') if x.strip()]
        shown = [x for x in items if keep_all or x.startswith('pub ')]
        inner = '; '.join(shown) if shown else '...'
        return [m.group(1) + ' ' + inner + ' }'], len(items) - len(shown)
    if not head.endswith('{'):
        return [head], 0
    body, hidden, k, depth = [], 0, i + 1, 1
    closed = ' closed ' in head or 'closed {' in head
    iface = 'interface {' in head
    while k < len(lines) and depth > 0:
        s = lines[k].strip()
        depth += s.count('{') - s.count('}')
        if depth <= 0:
            break
        item = re.sub(r'\s*//.*$', '', s)
        if item and depth == 1:
            if closed or iface or item.startswith('pub '):
                body.append('    ' + item)
            else:
                hidden += 1
        elif item and depth == 2 and closed:
            body.append('        ' + item)
        k += 1
    if not body:
        return [head + ' ... }'], hidden
    return [head] + body + ['}'], hidden


def decls(mod):
    path = os.path.join(LIB, mod + '.lxl')
    with open(path, encoding='utf-8') as f:
        lines = f.read().split('\n')
    out = []
    for i, line in enumerate(lines):
        if not line.startswith('pub '):
            continue
        doc = comment_above(lines, i)
        if line.startswith('pub fn '):
            sig, hidden = [fn_signature(lines, i)], 0
        elif line.startswith('pub type '):
            sig, hidden = type_decl(lines, i)
        else:
            s = line.strip()
            sig, hidden = [s if len(s) <= 120 else s[:117] + '...'], 0
        out.append((i + 1, doc, sig, hidden))
    return path, lines, out


def name_of(sig):
    s = sig[0]
    m = re.match(r'pub fn (?:\([^)]*\)\s*)?(\w+)', s) or re.match(r'pub (?:type|const|var) (\w+)', s)
    return m.group(1) if m else ''


def receiver_of(sig):
    m = re.match(r'pub fn \((?:var\s+)?(?:\w+\s*:\s*)?(?:mut\s+)?&?\s*(\w+)', sig[0])
    return m.group(1) if m else ''


def call_counts():
    """mod.fn( call sites across the repository's Lexell sources."""
    pat = re.compile(r'\b([a-z_][a-z0-9_]*)\.([a-zA-Z_]\w*)\s*[\[(]')
    counts = {}
    for root in USES:
        for dirpath, _, files in os.walk(root):
            for f in files:
                if f.endswith('.lxl'):
                    try:
                        text = open(os.path.join(dirpath, f), encoding='utf-8', errors='replace').read()
                    except OSError:
                        continue
                    for m in pat.finditer(text):
                        counts[m.groups()] = counts.get(m.groups(), 0) + 1
    return counts


def index():
    counts = call_counts()
    print('Lexell library modules (%s). `libapi.py MODULE` for one module\'s API.' % os.path.relpath(LIB))
    print('std is the prelude: its names need no import. Others: import "name", then name.f(...).\n')
    for mod in modules():
        path, lines, ds = decls(mod)
        what = first_sentence(header(lines)) or '(no header comment)'
        what = re.sub(r'^%s:\s*' % re.escape(mod), '', what)
        fns = sorted({name_of(s) for _, _, s, _ in ds if s[0].startswith('pub fn ') and not receiver_of(s)})
        top = sorted(fns, key=lambda n: -counts.get((mod, n), 0))
        top = [n for n in top if counts.get((mod, n), 0) > 0][:8]
        print('%-16s %4d pub  %s' % (mod, len(ds), what))
        if top:
            print('%-16s           most called: %s' % ('', ', '.join(top)))


def show(mod, filters, short):
    if not os.path.exists(os.path.join(LIB, mod + '.lxl')):
        sys.exit('libapi: no module %r in %s (run with no arguments for the list)' % (mod, LIB))
    path, lines, ds = decls(mod)
    rel = os.path.relpath(path)
    if not filters:
        h = header(lines)
        if h:
            print('// ' + h + '\n')
    if filters:
        keys = lambda sig: [k for k in (name_of(sig), receiver_of(sig)) if k]
        exact = [d for d in ds if any(k in filters for k in keys(d[2]))]
        near = [d for d in ds if d not in exact
                and any(f.lower() in k.lower() for f in filters for k in keys(d[2]))]
        if exact and near:
            print('// also matching: ' + ', '.join(sorted({name_of(d[2]) for d in near})) + '\n')
        ds = exact or near
    shown = 0
    for line, doc, sig, hidden in ds:
        shown += 1
        print('%s:%d' % (rel, line))
        if doc:
            for c in textwrap.wrap(first_sentence(doc) if short else doc, 96):
                print('  // ' + c)
        for s in sig:
            print('  ' + s)
        if hidden:
            print('  (%d private field%s)' % (hidden, '' if hidden == 1 else 's'))
        print()
    if filters and not shown:
        sys.exit('libapi: nothing in %s matches %s' % (mod, ' '.join(filters)))


def main():
    args = sys.argv[1:]
    if args and args[0] in ('-h', '--help'):
        print(__doc__)
        return
    short = '-s' in args
    args = [a for a in args if a != '-s']
    if not args:
        index()
    else:
        show(args[0], args[1:], short)


if __name__ == '__main__':
    main()
