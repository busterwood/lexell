#!/usr/bin/env python3
"""Manual tool: random MATCH_RECOGNIZE queries, run on Oracle Database Free and on lexdb's Oracle door
(through its TNS endpoint, in the same process as a throwaway lexdb), and compared: columns, rows
(numbers by value, text exactly, the column names without regard to case) and error numbers.
Not part of the suite (it needs Oracle). design/lexdb-match-recognize.md, section 12.

    # a throwaway Oracle (or lexell/tools/oracle_container.sh create, which also makes the APP user):
    podman run -d --name lxl-oracle-fuzz -p 127.0.0.1:15219:1521 -e ORACLE_PASSWORD=pw docker.io/gvenzl/oracle-free:slim
    # wait for "DATABASE IS READY TO USE" in `podman logs lxl-oracle-fuzz`, then a scratch user:
    #   sqlplus-less: python3 -c "import oracledb; c=oracledb.connect(user='system',password='pw',dsn='127.0.0.1:15219/FREEPDB1'); \\
    #   c.cursor().execute('create user mrt identified by mrt quota unlimited on users'); \\
    #   c.cursor().execute('grant create session, create table to mrt')"
    python3 lexell/tests/lexdb/fuzz_mr.py --dsn mrt/mrt@127.0.0.1:15219/FREEPDB1 --seed 1 -n 2000 [--save found.txt]
    podman rm -f lxl-oracle-fuzz        # when done; never touch lxl-mssql

The table f (id, g, v: 8 to 16 rows, g with NULLs, v with NULLs) is made by the seed and dropped and made again
on Oracle. Queries are the same text on both sides; no LATERAL (Oracle: 62521), no subqueries in the clause (D5),
no ORDER BY expressions (D3), no quoted variables (D7). Needs python-oracledb, and lxlc built (LXL_NOCACHE=1,
native). A failing query is shrunk (fewer measures, no SKIP, no PARTITION, simpler rows form) and printed with
both answers; --save appends it as `q<TAB>label<TAB>query` lines for mr_cases.txt (whose table is t: replace f).
"""
import argparse, decimal, importlib.util, os, random, re, subprocess, sys, tempfile
import oracledb

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))      # .../lexell (the repository's lexell directory)
spec = importlib.util.spec_from_file_location('gen_oracle', os.path.join(HERE, 'gen_oracle.py'))
go = importlib.util.module_from_spec(spec)
spec.loader.exec_module(go)
VARS = ['a', 'b', 'c']


# ---- the generator

class Gen:
    def __init__(self, rnd):
        self.r = rnd

    def quant(self):
        if self.r.random() < 0.45:
            return ''
        return self.r.choice(['*', '+', '?', '{2}', '{1,2}', '{2,}', '{,2}', '*?', '+?', '??', '{1,3}?', '{2,3}?'])

    def pat(self, depth=0):
        parts = []
        for _ in range(self.r.randint(1, 3)):
            if depth < 2 and self.r.random() < 0.2:
                inner = self.pat(depth + 1)
                if self.r.random() < 0.5:
                    inner += ' | ' + self.pat(depth + 1)
                parts.append('(' + inner + ')' + self.r.choice(['', '', '+', '*', '?', '{2}']))
            else:
                parts.append(self.r.choice(VARS) + self.quant())
        return ' '.join(parts)

    def full_pat(self):
        p = self.pat()
        x = self.r.random()
        if x < 0.1:
            p = '^ ' + p
        elif x < 0.2:
            p += ' $'
        elif x < 0.27:
            p = 'permute(a, b' + (', c' if self.r.random() < 0.5 else '') + ')'
        return p

    def pred(self, dep):
        r = self.r
        ch = ['v > %d' % r.choice([5, 10, 15, 20]), 'v < %d' % r.choice([10, 15, 25]), 'v < prev(v)', 'v > prev(v)', 'v is null',
              'v is not null', 'mod(id, 2) = 0', 'mod(id, 3) <> 0', '1 = 1', 'v >= next(v)', 'coalesce(v, 0) > prev(coalesce(v, 0))',
              'v > prev(v, 2)', 'lower(classifier()) = \'a\'', 'match_number() < 3']
        if dep:
            ch += ['v > first(a.v)', 'sum(a.v) < 40', 'v > last(a.v)', 'count(*) < 4', 'v <= max(a.v) + 5', 'v > avg(b.v)',
                   'v < first(b.v, 1) + 10', 'count(a.*) < 3', 'min(c.v) is null or v > 3']
        return r.choice(ch)

    def query(self):
        r = self.r
        dep = r.random() < 0.35
        p = self.full_pat()
        used = [v for v in VARS if re.search(r'\b%s\b' % v, p)]
        defs = ['%s as %s' % (v, self.pred(dep)) for v in used if r.random() < 0.85]
        if not defs:
            defs.append('%s as 1 = 1' % used[0])
        skip = r.choice(['', '', 'after match skip past last row', 'after match skip to next row'])
        subset = ''
        if len(used) >= 2 and r.random() < 0.15:
            subset = 'subset s = (%s, %s)' % (used[0], used[1])
        if r.random() < 0.15 and len(used) > 1:
            skip = 'after match skip to %s %s' % (r.choice(['first', 'last']), r.choice(used + (['s'] if subset else [])))
        part = 'partition by g ' if r.random() < 0.6 else ''
        order = r.choice(['order by id', 'order by id', 'order by id desc', 'order by v nulls first, id', 'order by v desc nulls last, id'])
        one = r.random() < 0.5
        if one:
            ms = ['match_number() as mno', 'count(*) as n', 'first(id) as f', 'last(id) as l', 'classifier() as cls', 'max(v) as mx']
            rows, outer = '', 'order by %smno' % ('g, ' if part else '')
        else:
            ms = ['match_number() as mno', 'running count(*) as n', 'first(id) as f', 'final last(id) as l', 'classifier() as cls',
                  'final max(v) as mx', 'running sum(v) as rs']
            rows = r.choice(['all rows per match', 'all rows per match show empty matches', 'all rows per match omit empty matches',
                             'all rows per match with unmatched rows'])
            outer = 'order by id, mno'
        if r.random() < 0.3:
            ms += ['prev(v, 2) as pv', 'next(v) as nx', 'last(v, 1) as l1', 'first(v, 1) as f1']
        if subset:
            ms += ['count(s.*) as cs', 'last(s.v) as ls']
        if '{-' not in p and r.random() < 0.2 and not (rows and 'unmatched' in rows):
            p = re.sub(r'\ba\b', '{- a -}', p, count=1)
        return dict(part=part, order=order, ms=ms, rows=rows, skip=skip, pat=p, subset=subset, defs=defs, outer=outer)

    @staticmethod
    def text(q):
        return ("select * from f match_recognize (%s%s measures %s %s %s pattern (%s) %s define %s) m %s"
                % (q['part'], q['order'], ', '.join(q['ms']), q['rows'], q['skip'], q['pat'], q['subset'], ', '.join(q['defs']), q['outer'])
                ).replace('  ', ' ')


def variants(q):
    """Simpler queries than q (for shrinking)."""
    out = []
    for i in range(len(q['ms'])):
        if len(q['ms']) > 1:
            v = dict(q); v['ms'] = q['ms'][:i] + q['ms'][i + 1:]
            if not any('mno' in m for m in v['ms']):
                v['outer'] = 'order by id' if q['rows'] else v['outer'].replace('mno', 'id') if False else v['outer']
            out.append(v)
    for k, val in (('skip', ''), ('part', ''), ('subset', ''), ('rows', ''), ('order', 'order by id')):
        if q[k] != val and not (k == 'subset' and 's' in q['skip'].split()[-1:]):
            v = dict(q); v[k] = val
            out.append(v)
    for i in range(len(q['defs'])):
        if len(q['defs']) > 1:
            v = dict(q); v['defs'] = q['defs'][:i] + q['defs'][i + 1:]
            out.append(v)
    return out


# ---- Oracle

def oracle_answers(cur, qs):
    out = []
    for sql in qs:
        try:
            cur.execute(sql)
            names = [d[0] for d in cur.description]
            rows = cur.fetchall()
            out.append(','.join(names) + ' = ' + ';'.join('|'.join(go.render(x) for x in r) for r in rows))
        except oracledb.DatabaseError as e:
            m = re.match(r'ORA-(\d+)', str(e))
            out.append('error ' + (str(int(m.group(1))) if m else str(e)))
    return out


# ---- lexdb's Oracle door

PROGRAM = r'''import "task"
import "net"
import "strings"
import "oracle"
import "../../../cmd/lexdb_store"
import "../../../cmd/lexdb_disk"
import "../../../cmd/lexdb_exec"
import "../../../cmd/lexdb_tns"

const QUERIES = "QUERIES_HERE"
const SETUP = "SETUP_HERE"

fn values(rows: &oracle.Rows, row: int): str {
    var out: []str = []
    for i in 0..rows.columnCount() {
        match rows.isNull(row, i) {
            Ok(n) {
                if n { append(mut &out, "NULL") } else {
                    match rows.value(row, i) {
                        Ok(v) { append(mut &out, v.toStr()) }
                        Err(e) { append(mut &out, "error " + e.code.toStr() + " " + e.msg) }
                    }
                }
            }
            Err(e) { append(mut &out, "error " + e.code.toStr()) }
        }
    }
    return strings.join(&out, "|")
}

fn qtext(c: mut &oracle.Conn, sql: &str): str {
    match c.query(sql.toStr(), &[]) {
        Ok(rows) {
            var names: []str = []
            for j in 0..rows.columnCount() { append(mut &names, rows.columnName(j).unwrap()) }
            var rs: []str = []
            for i in 0..rows.rowCount() { append(mut &rs, values(&rows, i)) }
            return strings.join(&names, ",") + " = " + strings.join(&rs, ";")
        }
        Err(e) { return "error " + e.code.toStr() }
    }
}

fn client(port: &str) {
    var c = match oracle.connect("User Id=app;Password=app;Data Source=127.0.0.1:" + port.toStr() + "/lexdb") {
        Ok(c0) { c0 }
        Err(e) { exit(1) }
    }
    for l in strings.lines(&SETUP) {
        match c.run(l.toStr(), &[]) {
            Ok(n) {}
            Err(e) { println("setup failed: " + e.code.toStr() + " " + l) }
        }
    }
    for l in strings.lines(&QUERIES) { println(qtext(mut &c, &l)) }
    c.logoff()
}

fn body(st: lexdb_store.Store): int {
    lexdb_exec.bootstrap(&st).unwrap()
    task.scope(fn(s: mut &task.Scope) {
        let ln = net.listen("127.0.0.1:0").unwrap()
        let addr = ln.localAddr()
        let f = s.start(lexdb_tns.acceptLoop, lexdb_tns.AcceptArg{ln: ln, st: st})
        client(&addr[10..len(addr)])
        { let stop = f }
    })
    return 0
}

fn main() {
    lexdb_store.run(lexdb_disk.sim(5), lexdb_store.Options{cacheBytes: 64 * 1024 * 1024, segBytes: 256 * 1024, ckptBytes: 128 * 1024, snapNodes: 50000, bufferedPages: false}, body).unwrap()
}
'''


def lxl_str(s):
    return s.replace('\\', '\\\\').replace('"', '\\"')


def lexdb_answers(qs, setup, compiler):
    prog = PROGRAM.replace('QUERIES_HERE', '\\n'.join(lxl_str(q) for q in qs)).replace('SETUP_HERE', '\\n'.join(lxl_str(s) for s in setup))
    # the program imports ../../../cmd: it lives in tests/lexdb/run while it is compiled
    path = os.path.join(HERE, 'run', 'zz_fuzz_mr_tmp.lxl')
    try:
        with open(path, 'w') as f:
            f.write(prog)
        with tempfile.TemporaryDirectory() as tmp:
            exe = os.path.join(tmp, 'fz')
            r = subprocess.run([compiler, path, '-o', exe], capture_output=True, text=True, env=dict(os.environ, LXL_NOCACHE='1'))
            if r.returncode:
                sys.exit('fuzz_mr.py: compile: ' + r.stdout + r.stderr)
            r = subprocess.run([exe], capture_output=True, text=True, timeout=1800, cwd=tmp)
    finally:
        if os.path.exists(path):
            os.remove(path)
    lines = r.stdout.split('\n')
    if len(lines) < len(qs) or any(l.startswith('setup failed') for l in lines[:1]):
        sys.exit('fuzz_mr.py: lexdb answered %d of %d: %s %s' % (len(lines), len(qs), r.stdout[:300], r.stderr[:300]))
    return lines[:len(qs)]


# ---- comparing

def num(s):
    if s == 'NULL' or s.startswith("'"):
        return None
    try:
        return decimal.Decimal(s)
    except decimal.InvalidOperation:
        return None


def same(got, want):
    """names without regard to case, numbers by value, text and NULL exactly, errors by number"""
    if got == want:
        return True
    if got.startswith('error') or want.startswith('error'):
        return False
    gi, wi = got.find(' = '), want.find(' = ')
    if gi < 0 or wi < 0 or got[:gi].lower() != want[:wi].lower():
        return False
    gr = got[gi + 3:].split(';') if got[gi + 3:] else []
    wr = want[wi + 3:].split(';') if want[wi + 3:] else []
    if len(gr) != len(wr):
        return False
    for a, b in zip(gr, wr):
        ac, bc = a.split('|'), b.split('|')
        if len(ac) != len(bc):
            return False
        for x, y in zip(ac, bc):
            if x != y:
                dx, dy = num(x), num(y)
                if dx is None or dy is None or dx != dy:
                    return False
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--dsn', required=True, help='user/password@host:port/service (a scratch user that can create tables)')
    ap.add_argument('--seed', type=int, default=1)
    ap.add_argument('-n', type=int, default=500, help='queries (default 500)')
    ap.add_argument('--batch', type=int, default=250, help='queries per lexdb program (default 250)')
    ap.add_argument('--save', help='append the failing queries, shrunk, as mr_cases.txt lines to this file')
    ap.add_argument('--compiler', default=os.path.join(ROOT, 'compiler', 'out', 'lxlc'))
    a = ap.parse_args()
    u, rest = a.dsn.split('/', 1)
    pw, dsn = rest.rsplit('@', 1)
    rnd = random.Random(a.seed)
    # the data of the seed
    data = []
    for i in range(1, rnd.randint(8, 16) + 1):
        g = rnd.choice(["'x'", "'y'", 'NULL'])
        v = rnd.choice(['NULL', str(rnd.randint(1, 30)), str(rnd.randint(1, 30)), str(rnd.randint(1, 30))])
        data.append((i, g, v))
    setup = ['create table f (id number(10) primary key, g varchar2(10), v number(10))'] + ['insert into f values (%d, %s, %s)' % d for d in data]
    conn = oracledb.connect(user=u, password=pw, dsn=dsn)
    cur = conn.cursor()
    try:
        cur.execute('drop table f purge')
    except oracledb.DatabaseError:
        pass
    for s in setup:
        cur.execute(s)
    conn.commit()
    g = Gen(rnd)
    qd = [g.query() for _ in range(a.n)]
    bad = 0
    errs = 0
    for lo in range(0, a.n, a.batch):
        chunk = qd[lo:lo + a.batch]
        qs = [Gen.text(q) for q in chunk]
        want = oracle_answers(cur, qs)
        got = lexdb_answers(qs, setup, a.compiler)
        errs += sum(1 for w in want if w.startswith('error'))
        for i, q in enumerate(chunk):
            if same(got[i], want[i]):
                continue
            bad += 1
            best, bw, bg = q, want[i], got[i]
            for _ in range(4):                      # shrink: the first simpler variant that still differs, until none does
                vs = variants(best)
                if not vs:
                    break
                vq = [Gen.text(v) for v in vs]
                vw = oracle_answers(cur, vq)
                vg = lexdb_answers(vq, setup, a.compiler)
                nxt = [k for k in range(len(vs)) if not same(vg[k], vw[k])]
                if not nxt:
                    break
                k = nxt[0]
                best, bw, bg = vs[k], vw[k], vg[k]
            text = Gen.text(best)
            print('--- DIFFERENCE (seed %d, query %d)\n%s\n oracle: %s\n lexdb : %s' % (a.seed, lo + i, text, bw[:400], bg[:400]))
            if a.save:
                with open(a.save, 'a') as f:
                    f.write('q\tfuzz seed %d query %d\t%s\n' % (a.seed, lo + i, text.replace('from f ', 'from t ')))
    print('seed %d: %d queries (%d an Oracle error), %d differences' % (a.seed, a.n, errs, bad))
    sys.exit(1 if bad else 0)


if __name__ == '__main__':
    main()
