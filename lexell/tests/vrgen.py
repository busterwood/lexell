#!/usr/bin/env python3
"""Generated stress test of value records with heap fields passed through small functions, for the
native backend's inlining and record rewrites (compiler/opt.lxl, design/native.md section 8).

usage: python3 lexell/tests/vrgen.py [--compiler PATH] [-n N] [--seed S] [-j N] [--keep DIR]

Each program passes value records with `str` fields (every other program also an `Option` field)
around small functions: by value, by borrow, as receivers, results, moves, clones, array elements,
`replace`, `swap`, `pop`, match arms, loops and `x = f(x)`. `str` is owned, so the records are
owned: the generator tracks which variables hold a value and moves or clones them by the rules of
SPEC section 9.1, so every program it writes is valid Lexell. Each program is built through C and
with --native, both run under LXL_CHECK=1 (a leak exits 5), and their exit codes, stdout and
stderr must be equal; the C run must also exit 0 with output. A program either build rejects
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


def program(seed, k):
    """Program k of a run with this seed: a function of (seed, k) only."""
    return gen(random.Random('vrgen %d %d' % (seed, k)), k % 2 == 1)


def one(k, a, out):
    base = os.path.join(out, 'p%d' % k)
    with open(base + '.lxl', 'w') as f:
        f.write(program(a.seed, k))
    builds = {}
    for mode in ('c', 'native'):
        b = subprocess.run([a.compiler, base + '.lxl', '--' + mode, '-o', base + '_' + mode[0]],
                           capture_output=True, text=True)
        builds[mode] = (b.returncode == 0, 'exit %d: %s' % (b.returncode, (b.stdout + b.stderr).strip()))
    ok = (builds['c'][0], builds['native'][0])
    if not all(ok):
        why = '; '.join('%s build failed: %s' % (m, builds[m][1][:300]) for m in builds if not builds[m][0])
        return ('nocompile', k, why, ok)
    env = dict(os.environ)
    env['LXL_CHECK'] = '1'
    try:
        rc = subprocess.run([base + '_c'], env=env, capture_output=True, timeout=20)
        rn = subprocess.run([base + '_n'], env=env, capture_output=True, timeout=20)
    except subprocess.TimeoutExpired:
        return ('differ', k, 'timeout', ok)
    for f in ('_c', '_n'):
        os.remove(base + f)
    if (rc.returncode, rc.stdout, rc.stderr) != (rn.returncode, rn.stdout, rn.stderr):
        return ('differ', k, 'C exit %d, native exit %d: %r' % (rc.returncode, rn.returncode, rn.stderr[:200]), ok)
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
    c_ok = n_ok = 0
    for kind, k, why, ok in res:
        count[kind] += 1
        c_ok += ok[0]
        n_ok += ok[1]
        if kind == 'differ':
            print('DIFFER p%d.lxl: %s' % (k, why))
        elif kind == 'badexit':
            print('FAILED ALIKE p%d.lxl: %s' % (k, why))
        elif kind == 'nocompile' and count[kind] <= 5:
            print('NOT COMPILED p%d.lxl: %s' % (k, why[:400]))
    bad = a.n - count['same']
    print('vrgen: seed %d: %d programs, %d compiled with --c, %d with --native; '
          '%d same, %d differ, %d failed alike, %d not compiled%s' % (
              a.seed, a.n, c_ok, n_ok, count['same'], count['differ'], count['badexit'], count['nocompile'],
              ' (programs in %s)' % out if bad else ''))
    if not bad and not a.keep:
        shutil.rmtree(out, ignore_errors=True)
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
