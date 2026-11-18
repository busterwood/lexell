#!/usr/bin/env python3
"""Generated stress test of value records with heap fields passed through small functions, for the
native backend's inlining and record rewrites (compiler/opt.lxl, design/native.md section 8).

usage: python3 lexell/tests/vrgen.py [--compiler PATH] [-n N] [--seed S] [-j N] [--keep DIR]

Each program passes value records with `str` fields (every other program also an `Option` field)
around small functions: by value, by borrow, as receivers, results, moves, clones, array elements,
`replace`, `swap`, `pop`, match arms, loops and `x = f(x)`. `str` is owned, so the records are
owned: the generator tracks which variables hold a value and moves or clones them by the rules of
SPEC section 9.1, so every program it writes is valid Lexell. Each program also has a part for
native -O's load reuse (compiler/cse.lxl): straight-line reads of int fields of heap records (in
locals, an array, and through `mut &` parameters of functions too big to inline), written
between the reads directly or by callees that take `mut &` (small ones, inlined, and big ones,
left calls), then read again, the same field or another. Each program is built through C and
with --native and with --native -O, all three run under LXL_CHECK=1 (a leak exits 5), and their
exit codes, stdout and stderr must be equal; the C run must also exit 0 with output. A program either build rejects
counts as `not compiled`, and like `differ` (outputs differ, or a timeout) and `failed alike`
(both exit nonzero) it fails the step: exit 1 unless every program is `same`. Failing programs
are kept (in --keep, or a temporary directory the summary names).

Seeds: program k of a run is a function of (S, k) only, so `--seed S -n N` writes the same N
programs on every run and machine, and `-n` larger extends the run with more programs. Without
--seed a random S is chosen; the summary line prints it, to rerun the same programs.
"""
import argparse, os, random, resource, shutil, subprocess, sys, tempfile
from concurrent.futures import ThreadPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.normpath(os.path.join(HERE, '..'))
LXLC = os.environ.get('LXLC') or os.path.join(ROOT, 'compiler', 'out', 'lxlc')

HEAD = '''type U = value record { k: int; t: str }
type T = value record { a: int; s: str; u: U; b: int@OF@ }
type W = value record { x: T; y: T }

fn mk(i: int): T { return T{a: i, s: "s" + intToStr(i), u: U{k: i * 2, t: "t" + intToStr(i)}, b: i@OMK@} }
fn mkw(i: int): W { return W{x: mk(i), y: mk(i + 1)} }
fn (x: T) ra(): int { return x.a }
fn (x: T) rs(): str { return move(x).s }
fn (x: T) ru(): U { return move(x).u }
fn (x: T) rt(): str {
    let u = move(x).u
    return u.t
}
fn (x: T) none(): int { return 7 }
fn (x: T) all(): str { return intToStr(x.a) + x.s + intToStr(x.u.k) + x.u.t + intToStr(x.b)@OALL@ }
fn (x: &T) bs(): str { return x.s.clone() }
fn (x: &T) ba(): int { return x.a + x.u.k }
fn pa(x: T): int { return x.a + 1 }
fn ps(x: T): str { return move(x).s }
fn pn(x: T, y: T): int { return x.b + y.b }
fn pick(x: T, y: T): T { return if x.a > y.a { x } else { y } }
fn same(x: T): T { return x }
fn upd(x: T): T {
    var y = x
    y.a += 1
    return y
}
fn sets(x: T, v: str): T {
    var m = x
    m.s = v
    return m
}
fn swp(x: T): T {
    let T{a, s, u, b} = move(x)
    let U{k, t} = move(u)
    return T{a: a, s: t, u: U{k: k, t: s}, b: b@OSWP@}
}
fn wx(w: W): T { return move(w).x }
fn (w: W) wy(): str {
    let y = move(w).y
    return y.s
}
fn get(i: int): Result[int, T] { return if i % 2 == 0 { Ok(i) } else { Err(mk(i)) } }
fn opt(i: int): Option[T] { return if i % 3 == 0 { None } else { Some(mk(i)) } }
fn hash(s: str): int { return len(s) }
fn hb(s: &str): int { return len(s) }
'''

RO = '''fn (x: T) ro(): str {
    let o = move(x).o
    match o {
        Some(q) { return q.t }
        None { return "" }
    }
}
'''


def head(opt_field):
    subs = {'@OF@': '; o: Option[U]', '@OMK@': ', o: Some(U{k: i, t: "o" + intToStr(i)})',
            '@OALL@': ' + (match x.o { Some(q) { q.t.clone() } None { "-" } })', '@OSWP@': ', o: None'}
    h = HEAD
    for k, v in subs.items():
        h = h.replace(k, v if opt_field else '')
    return h + (RO if opt_field else '')


# Reads of a T. A by-value read takes its T by value (a receiver `x: T` or a parameter), so on a
# variable it either moves it or reads a clone; a borrow read leaves the T where it is.
MOVE_READS = ['%s.ra()', '%s.none()', 'hash(%s.rs())', 'hash(%s.rt())', 'hash(%s.all())', 'pa(%s)',
              'hash(ps(%s))', '%s.ru().k', 'hash(%s.ru().t)']
BORROW_READS = ['%s.ba()', 'hb(%s.bs())', '%s.a', 'hb(%s.s)', '%s.u.k', 'hb(%s.u.t)']
MOVE_P = 0.3       # chance that a by-value use of a live variable moves it instead of cloning it


def gen(rng, opt_field):
    """One program's main. `T` is owned (it holds `str`s), so the generator tracks which variables
    hold a value: a by-value use either moves the variable (it is then dead until assigned again;
    a `let` stays dead) or reads `v.clone()`. Moves happen only at the top level of main or in an
    `if` arm (SPEC 9.1: a variable moved on one path is moved after the join), never in a loop
    over a variable declared outside it. Array elements are read by borrow, cloned, or taken out
    with `replace`, `swap` and `pop`, never moved out (SPEC 9.1)."""
    lines = []
    vs = {}        # T variable name -> [mutable, live]
    order = []     # T variable names in declaration order
    alen = 4       # length of arr: indexes 0..3 are always valid
    n = 0
    move_reads = MOVE_READS + (['hash(%s.ro())'] if opt_field else [])

    def newname():
        nonlocal n
        n += 1
        return 'v%d' % n

    def declare(nm, mutable):
        vs[nm] = [mutable, True]
        order.append(nm)

    def live(mut=False):
        return [x for x in order if vs[x][1] and (vs[x][0] or not mut)]

    def operand(avoid=None):
        """A T value, evaluated where it is written: moves or clones a live variable."""
        al = live()
        if not al:
            return 'mk(%d)' % rng.randrange(9)
        x = rng.choice(al)
        if x != avoid and rng.random() < MOVE_P:
            vs[x][1] = False
            return x
        return x + '.clone()'

    def place():
        """A T place to read by borrow: a live variable or an element."""
        al = live()
        if al and rng.random() < 0.8:
            return rng.choice(al)
        return 'arr[%d]' % rng.randrange(4)

    def read():
        """An int read of a variable (or element), in evaluation order."""
        t = rng.choice(move_reads + BORROW_READS)
        return t % (place() if t in BORROW_READS else operand())

    def read_local(nm):
        """An int read of `nm`, a T local of a loop body or match arm that owns it."""
        t = rng.choice(move_reads + BORROW_READS)
        if t in BORROW_READS or rng.random() < 0.7:
            return t % nm
        return t % (nm + '.clone()')

    lines.append('    var arr: []T = []')
    lines.append('    for i in 0..4 { append(mut &arr, mk(i + 10)) }')
    lines.append('    var acc = 0')
    for i in range(3):
        nm = newname()
        declare(nm, True)
        lines.append('    var %s = mk(%d)' % (nm, rng.randrange(50)))
    lines.append('    var w1 = mkw(3)')
    for _ in range(rng.randrange(15, 45)):
        r = rng.randrange(20)
        if r == 6 and not live(mut=True):
            r = 7
        if r == 15 and not live(mut=True):
            r = 18
        if r < 5:
            lines.append('    acc += %s' % read())
        elif r == 5:
            c = rng.randrange(9)
            if c == 0:
                src = operand()
            elif c == 1:
                src = 'arr[%d].clone()' % rng.randrange(4)
            elif c == 2:
                src = 'same(%s)' % operand()
            elif c == 3:
                a1 = operand()
                src = 'pick(%s, %s)' % (a1, operand())
            elif c == 4:
                src = 'swp(%s)' % operand()
            elif c == 5:
                src = 'upd(%s)' % operand()
            elif c == 6:
                src = 'wx(w1.clone())' if rng.random() < 0.5 else 'wx(w1)\n    w1 = mkw(acc % 7)'
            elif c == 7:
                src = 'mk(%d)' % rng.randrange(9)
            else:
                src = 'sets(%s, "z" + intToStr(acc))' % operand()
            nm = newname()
            lines.append('    let %s = %s' % (nm, src))
            declare(nm, False)
        elif r == 6:
            t = rng.choice(live(mut=True))
            f = rng.choice(['upd(%s)', 'same(%s)', 'swp(%s)', 'sets(%s, "q")', 'pick(%s, mk(acc %% 30))'])
            lines.append('    %s = %s' % (t, f % t))
        elif r == 7:
            t = rng.choice([x for x in order if vs[x][0]])
            c = rng.randrange(3)
            src = ['arr[%d].clone()' % rng.randrange(4), None, 'mk(acc % 20)'][c] or operand(avoid=t)
            lines.append('    %s = %s' % (t, src))
            vs[t][1] = True
        elif r == 8:
            if alen > 4 and rng.random() < 0.3:
                o = newname()
                lines.append('    let %s = pop(mut &arr)\n    acc += %s' % (o, read_local(o)))
                alen -= 1
            else:
                lines.append('    append(mut &arr, %s)' % operand())
                alen += 1
        elif r == 9:
            lines.append('    match get(acc + %d) {\n        Ok(q) { acc += q }\n        Err(e) { acc += %s }\n    }'
                         % (rng.randrange(5), read_local('e')))
        elif r == 10:
            lines.append('    match opt(acc + %d) {\n        Some(e) { acc += %s }\n        None { acc += 1 }\n    }'
                         % (rng.randrange(5), read_local('e')))
        elif r == 11:
            lines.append('    for i in 0..3 {\n        let c = arr[(i + acc) %% len(arr)].clone()\n        acc += %s\n    }'
                         % read_local('c'))
        elif r == 12:
            a1 = read()
            lines.append('    if acc %% 2 == 0 { acc += %s } else { acc += %s }' % (a1, read()))
        elif r == 13:
            a1 = operand()
            lines.append('    acc += pn(%s, %s)' % (a1, operand()))
        elif r == 14:
            if rng.random() < 0.5:
                lines.append('    acc += hash(w1.clone().wy()) + wx(w1.clone()).a')
            else:
                lines.append('    acc += hash(w1.clone().wy()) + wx(w1).a\n    w1 = mkw(acc % 7)')
        elif r == 15:
            t = rng.choice(live(mut=True))
            if rng.random() < 0.7:
                lines.append('    %s.s = %s.s + "m"' % (t, place()))
            else:
                lines.append('    acc += hash(replace(mut &%s.s, "r" + intToStr(acc)))' % t)
        elif r == 16:
            i, j = rng.randrange(4), rng.randrange(4)
            lines.append('    acc += hb(arr[%d].s) + %s' % (i, rng.choice(['arr[%d].clone().ra()', 'arr[%d].ba()']) % j))
        elif r == 17:
            i = rng.randrange(4)
            if rng.random() < 0.25:
                lines.append('    swap(mut &arr, %d, %d)' % (i, rng.randrange(4)))
            else:
                o = newname()
                lines.append('    let %s = replace(mut &arr[%d], %s)\n    acc += %s' % (o, i, operand(), read_local(o)))
        elif r == 18:
            a1 = operand()
            lines.append('    acc += %s.ra() + hash(%s.rs())' % (a1, operand()))
        else:
            lines.append('    println(intToStr(acc) + " " + %s.all())' % operand())
    lines.append('    println(intToStr(acc))')
    for nm in live():
        lines.append('    println(%s.all())' % nm)
    lines.append('    println(w1.wy())')
    lines.append('    for x in arr { println(x.all()) }')
    return head(opt_field) + 'fn main() {\n' + '\n'.join(lines) + '\n}\n'


# Heap records for the native -O load reuse (compiler/cse.lxl): a field read through memory in
# two loads or more (`h.r.a` of a local, `r.a` of a `mut &CA` parameter, `arr[i].a`) is held
# along straight-line code, and a statement that writes memory or calls must drop what it held.
# The callees take `mut &CA` (or `mut &CH`) and write one field: csa and csb are small, so the
# inliner (compiler/opt.lxl, limit 25 nodes) makes their writes direct; cwa, cwb, cva, cvb and
# cwd are bigger than that limit and stay calls. Field c of CA is written only directly, so a
# read of c after a call checks that a call does not change what it cannot reach.
CSE_HEAD = '''
type CA = record { a: int; b: int; c: int }
type CH = record { r: CA; d: int }

fn csa(r: mut &CA, k: int) { r.a = r.a + k + 1 }
fn csb(r: mut &CA, k: int) { r.b = r.b + k + 2 }
fn cwa(r: mut &CA, k: int) {
    var t = k * 7 + r.c % 13
    t = t * 5 % 101 + 3
    if t > 50 { t = t - 17 } else { t = t + 11 }
    let u = t * 3 % 11 + r.b % 5
    r.a = r.a + 1 + t % 13 + u
}
fn cwb(r: mut &CA, k: int) {
    var t = k * 11 + r.a % 7
    t = t * 3 % 97 + 5
    if t > 40 { t = t - 13 } else { t = t + 7 }
    let u = t * 5 % 13 + r.c % 3
    r.b = r.b + 2 + t % 11 + u
}
fn cva(r: mut &CA, k: int): int {
    var t = k * 5 + r.b % 11
    t = t * 7 % 89 + 1
    if t > 30 { t = t - 9 } else { t = t + 4 }
    let u = t * 3 % 7 + r.c % 5
    r.a = r.a + 3 + t % 17 + u
    return t % 10 + u
}
fn cvb(r: mut &CA, k: int): int {
    var t = k * 13 + r.c % 9
    t = t * 3 % 83 + 2
    if t > 35 { t = t - 11 } else { t = t + 6 }
    let u = t * 7 % 9 + r.a % 4
    r.b = r.b + 1 + t % 19 + u
    return t % 8 + u
}
fn cwd(h: mut &CH, k: int) {
    var t = k * 3 + h.d % 17
    t = t * 7 % 61 + 2
    if t > 25 { t = t - 8 } else { t = t + 5 }
    let u = t * 3 % 5 + h.r.a % 3
    h.d = h.d + 1 + t % 7
    h.r.c = h.r.c + 2 + u
}
'''

CSE_WRITERS = {'a': ['csa', 'cwa', 'cva'], 'b': ['csb', 'cwb', 'cvb']}
CSE_VALUED = ('cva', 'cvb')


def gen_cse(rng):
    """The functions of the load-reuse part and the line of main that runs it. Each csefN takes
    `r: mut &CA` and `h: mut &CH` (too big to be inlined, so its reads go through the
    pointers); csetop has its own records, in locals and an array, and calls the csefN. All of
    it is straight-line code (no loop or match between reads), mostly runs of a read of a
    field, a write of it (direct, or through a callee that takes `mut &`) and a read of the
    same field or another of the same record, whose values reach acc (returned) and the
    output."""
    out = [CSE_HEAD]

    def body(places, borrow, hname, lines, xs, ind='    '):
        """Statements over places (CA places as written; borrow[p] passes p as `mut &CA`) and
        hname (the CH as written, and as passed to cwd), appended to lines; xs, the int locals
        declared so far, grows."""

        def newx():
            nm = 'x%d' % (len(xs) + 1)
            xs.append(nm)
            return nm

        def fld():
            return rng.choice('abc')

        def write(p, f):
            """A statement that changes field f of place p (directly or by a call)."""
            if f == 'c' or rng.random() < 0.35:
                v = rng.choice(['%s.%s + %d' % (p, f, rng.randrange(1, 9)),
                                '(%s.%s + %s) %% 1000 + %d' % (p, f, rng.choice(xs) if xs else 'k', rng.randrange(1, 9)),
                                '%s.%s * 3 %% 1000 + %d' % (p, rng.choice('abc'), rng.randrange(1, 9))])
                return '%s%s.%s = %s' % (ind, p, f, v)
            w = rng.choice(CSE_WRITERS[f])
            arg = '%s(%s, %s)' % (w, borrow[p], rng.choice([str(rng.randrange(10)), 'k % 10', 'acc % 10']))
            if w in CSE_VALUED:
                if rng.random() < 0.5:
                    return '%sacc += %s' % (ind, arg)
                return '%slet %s = %s' % (ind, newx(), arg)
            return ind + arg

        for _ in range(rng.randrange(6, 16)):
            r = rng.randrange(10)
            p = rng.choice(places)
            if r < 5:
                # read, write, read again: the same field or another of the same record
                f = fld()
                if f == 'c' and rng.random() < 0.5:
                    f = rng.choice('ab')
                x1 = newx()
                lines.append('%slet %s = %s.%s' % (ind, x1, p, f))
                if rng.random() < 0.3:
                    lines.append('%sacc = acc + %s.%s' % (ind, p, rng.choice('abc')))
                lines.append(write(p, f))
                g = f if rng.random() < 0.6 else rng.choice([c for c in 'abc' if c != f])
                if rng.random() < 0.5:
                    x2 = newx()
                    lines.append('%slet %s = %s.%s' % (ind, x2, p, g))
                    lines.append('%sacc += %s * %d + %s' % (ind, x2, rng.randrange(1, 9), x1))
                else:
                    lines.append('%sacc = acc + %s.%s * %d + %s' % (ind, p, g, rng.randrange(1, 9), x1))
                if rng.random() < 0.3:
                    lines.append('%sprintln("%s " + intToStr(%s) + " " + intToStr(%s.%s))' % (ind, x1, x1, p, g))
            elif r == 5:
                # reads with nothing written between: reused
                x1 = newx()
                f = fld()
                lines.append('%slet %s = %s.%s + %s.%s' % (ind, x1, p, f, rng.choice(places), fld()))
                lines.append('%sacc = acc + %s.%s + %s' % (ind, p, f, x1))
            elif r == 6:
                lines.append(write(p, fld()))
            elif r == 7:
                # the CH: its own field, and its record's c through cwd
                if rng.random() < 0.5:
                    lines.append('%s%s.d = %s.d + %d' % (ind, hname[0], hname[0], rng.randrange(1, 9)))
                else:
                    lines.append('%scwd(%s, %d)' % (ind, hname[1], rng.randrange(10)))
                lines.append('%sacc = acc + %s.d + %s.c' % (ind, hname[0], p))
            elif r == 8 and xs:
                lines.append('%sprintln("v " + intToStr(%s) + " " + intToStr(%s.%s))' % (ind, rng.choice(xs), p, fld()))
            else:
                lines.append('%sacc = acc + %s.%s * %d' % (ind, p, fld(), rng.randrange(1, 9)))

    nf = rng.randrange(1, 4)
    for i in range(nf):
        lines = ['    var acc = k']
        xs = []
        body(['r', 'h.r'], {'r': 'r', 'h.r': 'mut &h.r'}, ('h', 'h'), lines, xs)
        lines.append('    println("f%d " + %s)' % (i, ' + " " + '.join('intToStr(%s)' % x for x in xs[-6:]) or '""'))
        lines.append('    return acc + r.a + r.b + r.c + h.r.a + h.r.b + h.r.c + h.d')
        out.append('fn csef%d(r: mut &CA, h: mut &CH, k: int): int {\n%s\n}\n' % (i, '\n'.join(lines)))
    lines = ['    var r = CA{a: k, b: k + 1, c: k + 2}',
             '    var h = CH{r: CA{a: k + 3, b: k + 4, c: k + 5}, d: k + 6}',
             '    var arr: []CA = []',
             '    for i in 0..3 { append(mut &arr, CA{a: i + k, b: i * 2, c: i + 7}) }',
             '    var acc = 0']
    places = ['r', 'h.r', 'arr[0]', 'arr[1]', 'arr[2]']
    borrow = {p: 'mut &' + p for p in places}
    xs = []
    for i in range(nf + rng.randrange(2)):
        body(places, borrow, ('h', 'mut &h'), lines, xs)
        lines.append('    acc += csef%d(mut &%s, mut &h, acc %% 10)' % (i % nf, rng.choice(['r', 'arr[%d]' % rng.randrange(3)])))
    lines.append('    for x in arr { acc = acc + x.a + x.b + x.c }')
    lines.append('    println("top " + intToStr(r.a) + " " + intToStr(h.r.b) + " " + intToStr(h.d))')
    lines.append('    return acc + r.a + r.b + r.c + h.r.a + h.r.b + h.r.c + h.d')
    out.append('fn csetop(k: int): int {\n%s\n}\n' % '\n'.join(lines))
    return '\n'.join(out), '    println("cse " + intToStr(csetop(%d)))' % rng.randrange(20)


def program(seed, k):
    """Program k of a run with this seed: a function of (seed, k) only. The load-reuse part
    has a random stream of its own, so the rest of the program is what it was before it."""
    p = gen(random.Random('vrgen %d %d' % (seed, k)), k % 2 == 1)
    fns, call = gen_cse(random.Random('vrgen cse %d %d' % (seed, k)))
    assert p.endswith('\n}\n')
    return p[:-3] + '\n' + call + '\n}\n' + fns


def one(k, a, out):
    base = os.path.join(out, 'p%d' % k)
    with open(base + '.lxl', 'w') as f:
        f.write(program(a.seed, k))
    builds = {}
    for mode, flags in (('c', ['--c']), ('native', ['--native']), ('opt', ['--native', '-O'])):
        b = subprocess.run([a.compiler, base + '.lxl'] + flags + ['-o', base + '_' + mode[0]],
                           capture_output=True, text=True)
        builds[mode] = (b.returncode == 0, 'exit %d: %s' % (b.returncode, (b.stdout + b.stderr).strip()))
    ok = (builds['c'][0], builds['native'][0], builds['opt'][0])
    if not all(ok):
        why = '; '.join('%s build failed: %s' % (m, builds[m][1][:300]) for m in builds if not builds[m][0])
        return ('nocompile', k, why, ok)
    env = dict(os.environ)
    env['LXL_CHECK'] = '1'
    try:
        rc = subprocess.run([base + '_c'], env=env, capture_output=True, timeout=20)
        rn = subprocess.run([base + '_n'], env=env, capture_output=True, timeout=20)
        ro = subprocess.run([base + '_o'], env=env, capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        return ('differ', k, 'timeout', ok)
    for f in ('_c', '_n', '_o'):
        os.remove(base + f)
    if (rc.returncode, rc.stdout, rc.stderr) != (rn.returncode, rn.stdout, rn.stderr):
        return ('differ', k, 'C exit %d, native exit %d: %r' % (rc.returncode, rn.returncode, rn.stderr[:200]), ok)
    if (rc.returncode, rc.stdout, rc.stderr) != (ro.returncode, ro.stdout, ro.stderr):
        return ('differ', k, 'C exit %d, native -O exit %d: %r' % (rc.returncode, ro.returncode, ro.stderr[:200]), ok)
    if rc.returncode != 0 or not rc.stdout:
        return ('badexit', k, 'both exit %d, %d bytes out: %r' % (rc.returncode, len(rc.stdout), rc.stderr[:200]), ok)
    os.remove(base + '.lxl')
    return ('same', k, '', ok)


def main():
    ap = argparse.ArgumentParser(usage=__doc__.split('usage: ')[1].split('\n')[0])
    ap.add_argument('--compiler', default=LXLC)
    ap.add_argument('-n', type=int, default=200)
    ap.add_argument('--seed', type=int, default=None)
    ap.add_argument('-j', type=int, default=os.cpu_count() or 4)
    ap.add_argument('--keep', default=None)
    a = ap.parse_args()
    a.compiler = os.path.abspath(a.compiler)
    # No core dumps from the programs and compilers run here: a broken backend crashes most of
    # them, and a flood of dumps to systemd-coredump loads the machine enough to kill builds.
    resource.setrlimit(resource.RLIMIT_CORE, (0, resource.getrlimit(resource.RLIMIT_CORE)[1]))
    if a.seed is None:
        a.seed = random.randrange(1 << 30)
    out = a.keep or tempfile.mkdtemp(prefix='vrgen')
    os.makedirs(out, exist_ok=True)
    with ThreadPoolExecutor(max_workers=a.j) as ex:
        res = list(ex.map(lambda k: one(k, a, out), range(a.n)))
    count = {'same': 0, 'differ': 0, 'nocompile': 0, 'badexit': 0}
    c_ok = n_ok = o_ok = 0
    for kind, k, why, ok in res:
        count[kind] += 1
        c_ok += ok[0]
        n_ok += ok[1]
        o_ok += ok[2]
        if kind == 'differ':
            print('DIFFER p%d.lxl: %s' % (k, why))
        elif kind == 'badexit':
            print('FAILED ALIKE p%d.lxl: %s' % (k, why))
        elif kind == 'nocompile' and count[kind] <= 5:
            print('NOT COMPILED p%d.lxl: %s' % (k, why[:400]))
    bad = a.n - count['same']
    print('vrgen: seed %d: %d programs, %d compiled with --c, %d with --native, %d with --native -O; '
          '%d same, %d differ, %d failed alike, %d not compiled%s' % (
              a.seed, a.n, c_ok, n_ok, o_ok, count['same'], count['differ'], count['badexit'], count['nocompile'],
              ' (programs in %s)' % out if bad else ''))
    if not bad and not a.keep:
        shutil.rmtree(out, ignore_errors=True)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
