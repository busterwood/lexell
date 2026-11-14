#!/usr/bin/env python3
"""Regenerates lexdb's MATCH_RECOGNIZE tests, checked against Oracle (design/lexdb-match-recognize.md, 9):
the cases in mr_cases.txt are run on Oracle Database Free through python-oracledb, and three tests are
written that run the same cases through lexdb and compare with Oracle's answers:

    run/tns_mr.lxl        Oracle's texts through the TNS endpoint (lib/oracle)
    run/exec_mrdoors.lxl  the PostgreSQL texts through lexdb_exec (the PostgreSQL door's executor)
    run/tds_mr.lxl        the T-SQL texts through the TDS endpoint (lib/sqlserver)

    python3 lexell/tests/lexdb/gen_mr.py --dsn mrt/PASSWORD@127.0.0.1:1521/FREEPDB1

The account (a scratch user that can create tables and views; the tables are dropped first and
left behind) is the only thing the script writes to. Needs python-oracledb. gen_oracle.py's
render() and error parsing are used.

mr_cases.txt has one entry per line, tab separated, `#` lines are comments:
  s  label  oracle-statement  pg-statement  tsql-statement   setup ("=" is the Oracle text)
  d  table  columns  rows                                     one INSERT a row in all three doors
  q  label  query                                             one text for all three doors
  q3 label  oracle-query  pg-query  tsql-query                a text for each door, one answer
  e  label  query  pg-state  tsql-number                      an error: Oracle's number is recorded; the others
                                                              are the PostgreSQL SQLSTATE and the T-SQL number

An answer is the columns' names, " = ", the rows (cells apart by |, rows by ;, text quoted, NULL as NULL),
or "error N" (Oracle's ORA- number). The PostgreSQL and T-SQL tests compare the cells by value for numbers
(2 = 2.0), exactly for text and NULL, except in a column whose name starts with CLS (CLASSIFIER: lexdb's
PostgreSQL and T-SQL doors give the variable as written, Oracle in upper case), and names as lower(oracle
name) unless Oracle's has a lower-case letter. Every query has an outer ORDER BY on unique keys.
"""
import argparse, importlib.util, os, re, sys
import oracledb

HERE = os.path.dirname(os.path.abspath(__file__))
spec = importlib.util.spec_from_file_location('gen_oracle', os.path.join(HERE, 'gen_oracle.py'))
go = importlib.util.module_from_spec(spec)
spec.loader.exec_module(go)

TABLES = ['t', 'ticker', 'ev', 'gp', 'px', 'nv', 'tie']
VIEWS = ['tv']


def load():
    out = []
    for l in open(os.path.join(HERE, 'mr_cases.txt'), encoding='utf-8'):
        l = l.rstrip('\n')
        if not l.strip() or l.startswith('#'):
            continue
        out.append(l.split('\t'))
    return out


def inserts(table, cols, rows):
    return ['insert into %s (%s) values (%s)' % (table, cols, r) for r in rows.split(';')]


def answer(cur, sql):
    try:
        cur.execute(sql)
        names = [d[0] for d in cur.description]
        rows = cur.fetchall()
        return ','.join(names) + ' = ' + ';'.join('|'.join(go.render(v) for v in r) for r in rows)
    except oracledb.DatabaseError as e:
        msg = str(e.args[0].message if hasattr(e.args[0], 'message') else e)
        m = re.match(r'ORA-(\d+)', msg)
        return 'error ' + str(int(m.group(1))) if m else 'error ' + msg


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dsn', required=True, help='user/password@host:port/service')
    a = ap.parse_args()
    u, rest = a.dsn.split('/', 1)
    pw, dsn = rest.rsplit('@', 1)
    conn = oracledb.connect(user=u, password=pw, dsn=dsn)
    cur = conn.cursor()
    for v in VIEWS:
        try: cur.execute('drop view ' + v)
        except oracledb.DatabaseError: pass
    for t in TABLES:
        try: cur.execute('drop table %s purge' % t)
        except oracledb.DatabaseError: pass
    entries = load()
    # (kind, label, per door texts, oracle answer)
    setup = []      # (label, oracle, pg, tsql)
    cases = []      # (kind, label, [oracle, pg, tsql], answer, extra)
    for e in entries:
        k = e[0]
        if k == 's':
            o, p, t = e[2], e[3], e[4]
            p = o if p == '=' else p
            t = o if t == '=' else t
            cur.execute(o)
            setup.append((e[1], o, p, t))
        elif k == 'd':
            for sql in inserts(e[1], e[2], e[3]):
                cur.execute(sql)
                setup.append((e[1], sql, sql, sql))
            conn.commit()
        elif k == 'q':
            cases.append(('q', e[1], [e[2]] * 3, answer(cur, e[2]), None))
        elif k == 'q3':
            cases.append(('q', e[1], e[2:5], answer(cur, e[2]), None))
        elif k == 'e':
            ans = answer(cur, e[2])
            if not ans.startswith('error'):
                sys.exit('gen_mr.py: %s: expected an error, got %s' % (e[1], ans[:80]))
            cases.append(('e', e[1], [e[2]] * 3, ans, (e[3], int(e[4]))))
        else:
            sys.exit('gen_mr.py: unknown entry ' + k)
    conn.commit()
    bad = [q for q in cases if q[0] == 'q' and q[3].startswith('error')]
    for q in bad:
        print('gen_mr.py: %s: Oracle says %s' % (q[1], q[3]), file=sys.stderr)
    if bad:
        sys.exit(1)
    write_tns(setup, cases)
    write_exec(setup, cases)
    write_tds(setup, cases)
    print(len(cases), 'cases;', sum(1 for c in cases if c[0] == 'e'), 'errors;', len(setup), 'setup statements')


HEADER = [
    'MATCH_RECOGNIZE (design/lexdb-match-recognize.md, section 9), checked against Oracle Database Free 23ai',
    '(generated by tests/lexdb/gen_mr.py from mr_cases.txt): the answers of Oracle are compared by value for',
    'numbers, exactly for text and NULL (CLASSIFIER, in a column named CLS..., without regard to case), the',
    'column names without regard to the case Oracle gives them; an error by its number. The program prints',
    '"ok label", or the label and what differs.',
]

CMP = r'''
// ---- the comparison with Oracle's answers (gen_mr.py)

fn numeric(s: &str): Option[Decimal] {
    if len(s) == 0 || s[0] == '\'' || s == "NULL" { return None }
    match Decimal.parse(s.toStr()) {
        Ok(d) { return Some(d) }
        Err(_) { return None }
    }
}

fn parts(s: &str, sep: &str): []str {
    var out: []str = []
    for p in strings.split(s, sep) { append(mut &out, p.toStr()) }
    return out
}

fn hasLower(s: &str): bool {
    for i in 0..len(s) { if s[i] >= 'a' && s[i] <= 'z' { return true } }
    return false
}

fn sameCell(col: &str, got: &str, want: &str): bool {
    if got == want { return true }
    match numeric(got) {
        Some(a) {
            match numeric(want) {
                Some(b) { return a == b }
                None {}
            }
        }
        None {}
    }
    if strings.startsWith(col, "CLS") && len(want) > 1 && want[0] == '\'' { return got == strings.toLowerAscii(want) }
    return false
}

// "names = rows" against Oracle's: "" when they agree, else why not (exact: the names as Oracle gives them)
fn differ(got: &str, want: &str, exact: bool): str {
    if strings.startsWith(want, "error") || strings.startsWith(got, "error") { return if got == want { "" } else { "got " + got + ", want " + want } }
    let gi = strings.indexOf(got, " = ", 0)
    let wi = strings.indexOf(want, " = ", 0)
    if gi < 0 || wi < 0 { return "got " + got + ", want " + want }
    let gn = parts(&got[0..gi], ",")
    let wn = parts(&want[0..wi], ",")
    if len(gn) != len(wn) { return "columns: got " + got[0..gi] + ", want " + want[0..wi] }
    for i in 0..len(gn) {
        let w = if exact || hasLower(&wn[i]) { wn[i].toStr() } else { strings.toLowerAscii(wn[i]) }
        if gn[i] != w { return "column " + (i + 1).toStr() + ": got " + gn[i] + ", want " + w }
    }
    var gr: []str = []
    var wr: []str = []
    if len(got) > gi + 3 { gr = parts(&got[gi + 3..len(got)], ";") }
    if len(want) > wi + 3 { wr = parts(&want[wi + 3..len(want)], ";") }
    if len(gr) != len(wr) { return "rows: got " + got[gi + 3..len(got)] + ", want " + want[wi + 3..len(want)] }
    for r in 0..len(gr) {
        let gc = parts(&gr[r], "|")
        let wc = parts(&wr[r], "|")
        if len(gc) != len(wc) { return "row " + (r + 1).toStr() + ": got " + gr[r] + ", want " + wr[r] }
        for c in 0..len(gc) {
            if !sameCell(&wn[c], &gc[c], &wc[c]) { return "row " + (r + 1).toStr() + ": got " + gr[r] + ", want " + wr[r] }
        }
    }
    return ""
}

fn report(label: &str, why: &str) {
    if len(why) == 0 { println("ok " + label) } else { println("FAIL " + label + ": " + why) }
}
'''


def lxl_str(s):
    return s.replace('\\', '\\\\').replace('"', '\\"')


def write(out, header, program, calls):
    with open(os.path.join(HERE, 'run', out), 'w', encoding='utf-8') as f:
        for h in header:
            f.write('// ' + h + '\n')
        for c in calls['expect']:
            f.write('// expect: ' + c + '\n')
        f.write(program.replace('SETUP_HERE', '\n'.join(calls['setup'])).replace('CASES_HERE', '\n'.join(calls['cases'])))


def write_tns(setup, cases):
    calls = {'expect': [], 'setup': [], 'cases': []}
    for label, o, p, t in setup:
        calls['setup'].append('    setup(mut &c, "%s", "%s")' % (lxl_str(label), lxl_str(o)))
    for kind, label, texts, ans, extra in cases:
        calls['expect'].append('ok ' + label)
        calls['cases'].append('    case(mut &c, "%s", "%s", "%s")' % (lxl_str(label), lxl_str(texts[0]), lxl_str(ans)))
    write('tns_mr.lxl', HEADER + ['Through lexdb\'s TNS endpoint, with lib/oracle, in the texts Oracle runs.'], TNS_PROGRAM, calls)


def write_exec(setup, cases):
    calls = {'expect': [], 'setup': [], 'cases': []}
    for label, o, p, t in setup:
        calls['setup'].append('    setup(mut &s, "%s", "%s")' % (lxl_str(label), lxl_str(p)))
    for kind, label, texts, ans, extra in cases:
        calls['expect'].append('ok ' + label)
        if kind == 'e':
            calls['cases'].append('    errcase(mut &s, "%s", "%s", "%s")' % (lxl_str(label), lxl_str(texts[1]), extra[0]))
        else:
            calls['cases'].append('    case(mut &s, "%s", "%s", "%s")' % (lxl_str(label), lxl_str(texts[1]), lxl_str(ans)))
    write('exec_mrdoors.lxl', HEADER + ['Through the PostgreSQL door\'s executor (lexdb_exec), in PostgreSQL\'s texts.'], EXEC_PROGRAM, calls)


def write_tds(setup, cases):
    calls = {'expect': [], 'setup': [], 'cases': []}
    for label, o, p, t in setup:
        calls['setup'].append('    setup(mut &c, "%s", "%s")' % (lxl_str(label), lxl_str(t)))
    for kind, label, texts, ans, extra in cases:
        calls['expect'].append('ok ' + label)
        if kind == 'e':
            calls['cases'].append('    errcase(mut &c, "%s", "%s", %d)' % (lxl_str(label), lxl_str(texts[2]), extra[1]))
        else:
            calls['cases'].append('    case(mut &c, "%s", "%s", "%s")' % (lxl_str(label), lxl_str(texts[2]), lxl_str(ans)))
    write('tds_mr.lxl', HEADER + ['Through lexdb\'s TDS endpoint, with lib/sqlserver, in T-SQL\'s texts.'], TDS_PROGRAM, calls)


TNS_PROGRAM = r'''import "task"
import "net"
import "strings"
import "oracle"
import "../../../cmd/lexdb_store"
import "../../../cmd/lexdb_disk"
import "../../../cmd/lexdb_exec"
import "../../../cmd/lexdb_tns"
''' + CMP + r'''
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

// A query: its columns' names, then its rows; or error and the number.
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

fn setup(c: mut &oracle.Conn, label: &str, sql: &str) {
    match c.run(sql.toStr(), &[]) {
        Ok(n) {}
        Err(e) { println("setup " + label + " failed: " + e.code.toStr() + " " + e.msg) }
    }
}

fn case(c: mut &oracle.Conn, label: &str, sql: &str, want: &str) { report(label, &differ(&qtext(c, sql), want, true)) }

fn client(port: &str) {
    var c = match oracle.connect("User Id=app;Password=app;Data Source=127.0.0.1:" + port.toStr() + "/lexdb") {
        Ok(c0) { c0 }
        Err(e) { exit(1) }
    }
SETUP_HERE
CASES_HERE
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
    lexdb_store.run(lexdb_disk.sim(5), lexdb_store.Options{cacheBytes: 128 * 1024 * 1024, segBytes: 256 * 1024, ckptBytes: 128 * 1024, snapNodes: 50000, bufferedPages: false}, body).unwrap()
}
'''

EXEC_PROGRAM = r'''import "strings"
import "../../../cmd/lexdb_store"
import "../../../cmd/lexdb_disk"
import "../../../cmd/lexdb_sql"
import "../../../cmd/lexdb_exec"
''' + CMP + r'''
fn cell(v: &lexdb_sql.Val): str {
    if lexdb_exec.isNull(v) { return "NULL" }
    match v {
        lexdb_sql.Val.Text(t) { return "'" + strings.replaceAll(t, "'", "''") + "'" }
        else { return lexdb_exec.text(v) }
    }
}

// the answer as Oracle's is written: names = rows; or error and the state
fn run1(s: mut &lexdb_exec.Session, sql: &str): str {
    match s.exec(sql) {
        Ok(rs) {
            let r = &rs[len(rs) - 1]
            var names: []str = []
            for c in r.cols { append(mut &names, c.label()) }
            var out: []str = []
            for row in r.rows {
                var vs: []str = []
                for v in row { append(mut &vs, cell(&v)) }
                append(mut &out, strings.join(&vs, "|"))
            }
            return strings.join(&names, ",") + " = " + strings.join(&out, ";")
        }
        Err(e) { return "error " + e.state }
    }
}

fn setup(s: mut &lexdb_exec.Session, label: &str, sql: &str) {
    let r = run1(mut &s, sql)
    if strings.startsWith(&r, "error") { println("setup " + label + " failed: " + r) }
}

fn case(s: mut &lexdb_exec.Session, label: &str, sql: &str, want: &str) { report(label, &differ(&run1(mut &s, sql), want, false)) }

fn errcase(s: mut &lexdb_exec.Session, label: &str, sql: &str, state: &str) {
    let got = run1(mut &s, sql)
    report(label, &(if got == "error " + state { "" } else { "got " + got + ", want error " + state }))
}

fn opts(): lexdb_store.Options {
    return lexdb_store.Options{cacheBytes: 256 * 1024, segBytes: 1024 * 1024, ckptBytes: 512 * 1024, snapNodes: 100000, bufferedPages: false}
}

fn main() {
    lexdb_store.run(lexdb_disk.sim(49), opts(), fn(st: lexdb_store.Store): int {
        lexdb_exec.bootstrap(&st).unwrap()
        var s = lexdb_exec.newSession(st)
SETUP_HERE
CASES_HERE
        return 0
    }).unwrap()
}
'''

TDS_PROGRAM = r'''import "task"
import "net"
import "strings"
import "sqlserver"
import "../../../cmd/lexdb_store"
import "../../../cmd/lexdb_disk"
import "../../../cmd/lexdb_exec"
import "../../../cmd/lexdb_wire"
import "../../../cmd/lexdb_tds"
''' + CMP + r'''
fn rows(r: &sqlserver.Rows): str {
    var names: []str = []
    for j in 0..r.columnCount() { append(mut &names, r.columnName(j).unwrap()) }
    var out: []str = []
    for i in 0..r.rowCount() {
        var cells: []str = []
        for j in 0..r.columnCount() {
            match r.value(i, j) {
                Ok(v) { append(mut &cells, v.toStr()) }
                Err(e) { append(mut &cells, "error " + e.code.toStr()) }
            }
        }
        append(mut &out, strings.join(&cells, "|"))
    }
    return strings.join(&names, ",") + " = " + strings.join(&out, ";")
}

fn run1(c: mut &sqlserver.Conn, sql: &str): str {
    match c.queryAll(sql.toStr(), &[]) {
        Ok(r) {
            if len(r.sets) == 0 { return "ok" }
            return rows(&r.sets[len(r.sets) - 1])
        }
        Err(e) { return "error " + e.code.toStr() }
    }
}

fn setup(c: mut &sqlserver.Conn, label: &str, sql: &str) {
    let r = run1(mut &c, sql)
    if strings.startsWith(&r, "error") { println("setup " + label + " failed: " + r) }
}

fn case(c: mut &sqlserver.Conn, label: &str, sql: &str, want: &str) { report(label, &differ(&run1(mut &c, sql), want, false)) }

fn errcase(c: mut &sqlserver.Conn, label: &str, sql: &str, number: int) {
    let got = run1(mut &c, sql)
    report(label, &(if got == "error " + number.toStr() { "" } else { "got " + got + ", want error " + number.toStr() }))
}

fn batches(dsn: &str) {
    match sqlserver.connect(dsn.toStr()) {
        Ok(c0) {
            var c = c0
SETUP_HERE
CASES_HERE
            c.close()
        }
        Err(e) { println("connect: error " + e.code.toStr() + " " + e.msg) }
    }
}

fn body(st: lexdb_store.Store): int {
    lexdb_exec.bootstrap(&st).unwrap()
    task.scope(fn(s: mut &task.Scope) {
        let ln = net.listen("127.0.0.1:0").unwrap()
        let addr = ln.localAddr()
        lexdb_wire.configure(&st, &lexdb_wire.noAuth()).unwrap()
        let f = s.start(lexdb_tds.acceptLoop, lexdb_tds.AcceptArg{ln: ln, st: st})
        batches(&("Server=127.0.0.1," + addr[10..len(addr)] + ";UID=sa;PWD=x;Encrypt=no"))
        { let stop = f }
    })
    return 0
}

fn main() {
    lexdb_store.run(lexdb_disk.sim(7), lexdb_store.Options{cacheBytes: 64 * 1024 * 1024, segBytes: 256 * 1024, ckptBytes: 128 * 1024,
                                                             snapNodes: 50000, bufferedPages: false}, body).unwrap()
}
'''

if __name__ == '__main__':
    main()
