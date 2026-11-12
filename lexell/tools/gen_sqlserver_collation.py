#!/usr/bin/env python3
"""Generates lexell/cmd/lexdb_sqlcoll.lxl, SQL Server's order for its default
collation (SQL_Latin1_General_CP1_CI_AS, nvarchar), and the test of it,
lexell/tests/lexdb/run/exec_sqlcoll.lxl, from a running SQL Server: the
oracle container (tools/mssql_container.sh). design/lexdb-tds.md, L2.

    python3 lexell/tools/gen_sqlserver_collation.py [--check N]

Every code point of the BMP is put to the oracle: whether it is ignored
('a' + c + 'b' = 'ab'), a combining mark (equal to 'ab' only accent-
insensitively), a hyphen-like mark (after 'ab', before 'aba': ignored by
the letters, it breaks ties), or a letter; a letter's primary weight is its
rank accent-insensitively, its secondary its rank among the letters of
that weight. A single character equal to two (ae, ss, th, ...) is an
expansion. Each is ranked as c + 'a', so that a space is not trailing.

The key lexdb makes from these (lexdb_exec.ciKey): the primary weights,
then the secondary ones, then the hyphen-like marks with how many letters
come before each; a combining mark after a letter composes with it where
Unicode has the composed letter; trailing spaces and ignored characters
dropped. --check N ranks N random strings in the oracle and compares (the
model below is the key's).
"""
import argparse, os, random, subprocess, sys, unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, 'cmd', 'lexdb_sqlcoll.lxl')
TEST = os.path.join(ROOT, 'tests', 'lexdb', 'run', 'exec_sqlcoll.lxl')
COLL = 'SQL_Latin1_General_CP1_CI_AS'
COLL_AI = 'SQL_Latin1_General_CP1_CI_AI'

def sql(text):
    p = subprocess.run([os.path.join(HERE, 'mssql_container.sh'), 'sql', '-d', 'tempdb', '-h', '-1', '-f', '65001', '-i', '/dev/stdin'],
                       input=text.encode('utf-8'), stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=True)
    out = p.stdout.decode('utf-8')
    if 'Msg ' in out:
        sys.exit('the oracle refused the query:\n' + out[:2000])
    return [l for l in out.split('\n') if '|' in l]

CHARS = """set nocount on;
create table #c (cp int primary key, ch nvarchar(2));
with n as (select top (65536) row_number() over (order by (select null)) - 1 as cp from sys.all_objects a cross join sys.all_objects b)
insert #c select cp, nchar(cp) from n where cp >= 1 and not (cp between 55296 and 57343);
"""

def extract():
    rows = sql(CHARS + f"""
create table #k (cp int primary key, ai int, asr int, kind int);
insert #k select cp,
 dense_rank() over (order by ch + N'a' collate {COLL_AI}),
 dense_rank() over (order by ch + N'a' collate {COLL}),
 case when N'a'+ch+N'b' = N'ab' collate {COLL} then 0
      when N'a'+ch+N'b' = N'ab' collate {COLL_AI} then 2
      when N'a'+ch+N'b' > N'ab' collate {COLL} and N'a'+ch+N'b' < N'aba' collate {COLL} then 3
      else 1 end
from #c;
select k.cp, k.ai, k.asr, k.kind,
 case when k.kind = 3 then dense_rank() over (partition by case when k.kind = 3 then 1 else 0 end order by N'a'+c.ch+N'b' collate {COLL}) else 0 end,
 case when k.kind = 2 then dense_rank() over (partition by case when k.kind = 2 then 1 else 0 end order by N'a'+c.ch collate {COLL}) else 0 end
from #k k join #c c on c.cp = k.cp order by k.cp;
""")
    data = [list(map(int, r.split('|'))) for r in rows]
    exp = sql(CHARS + f"""
create table #l (ch nvarchar(2));
insert #l select ch from #c where (cp between 33 and 126 or cp between 880 and 1279)
  and not (N'a'+ch+N'b' = N'ab' collate {COLL_AI})
  and not (N'a'+ch+N'b' > N'ab' collate {COLL} and N'a'+ch+N'b' < N'aba' collate {COLL});
select c.cp, lower(a.ch + b.ch), max(case when c.ch = a.ch + b.ch collate {COLL} then 1 else 0 end)
from #c c cross join #l a cross join #l b
where c.ch = a.ch + b.ch collate {COLL_AI} and not (N'a'+c.ch+N'b' = N'ab' collate {COLL}) and len(a.ch + b.ch) = 2
group by c.cp, lower(a.ch + b.ch) order by c.cp;
""")
    expansions = {}
    for r in exp:
        cp, pair, eq = r.split('|')
        expansions.setdefault(int(cp), (pair, int(eq)))
    return data, expansions

class Model:
    def __init__(self, data, expansions):
        self.k = {r[0]: r for r in data}
        self.gmin = {}
        for cp, ai, asr, kind, sw, dw in data:
            if kind == 1: self.gmin[ai] = min(self.gmin.get(ai, asr), asr)
        self.exp = expansions

    def kind(self, cp):
        r = self.k.get(cp)
        return 1 if r is None else r[3]

    def letter(self, cp):
        # (primary, secondary) elements of a letter
        if cp in self.exp:
            pair, eq = self.exp[cp]
            out = []
            for c in pair: out += self.letter(ord(c))
            if not eq: out[-1] = (out[-1][0], out[-1][1] + 200)
            return out
        r = self.k.get(cp)
        if r is None: return [((1 << 20) + cp, 0)]
        return [(r[1], r[2] - self.gmin[r[1]])]

    def key(self, s):
        cs = []
        for ch in s:
            if cs and self.kind(ord(ch)) == 2:
                c = unicodedata.normalize('NFC', cs[-1] + ch)
                if len(c) == 1 and self.kind(ord(c)) == 1:
                    cs[-1] = c
                    continue
            cs.append(ch)
        while cs and (cs[-1] == ' ' or self.kind(ord(cs[-1])) == 0): cs.pop()
        prim, sec, spec = [], [], []
        for ch in cs:
            cp = ord(ch)
            kd = self.kind(cp)
            if kd == 0: continue
            if kd == 2:
                if sec: sec[-1] += 1000 + self.k[cp][5]
                continue
            if kd == 3:
                spec.append((len(prim), self.k[cp][4]))
                continue
            for p, s2 in self.letter(cp):
                prim.append(p)
                sec.append(s2)
        return (prim, sec, spec)

def runs(vals):
    cps = sorted(vals)
    out = []
    i = 0
    while i < len(cps):
        j = i
        step = None
        while j + 1 < len(cps) and cps[j + 1] == cps[j] + 1:
            d = vals[cps[j + 1]] - vals[cps[j]]
            if step is None: step = d
            elif d != step: break
            j += 1
        out.append((cps[i], j - i + 1, vals[cps[i]], step or 0))
        i = j + 1
    return out

def ints(name, xs, per=12):
    lines = [f'pub const {name}: []i32 = [']
    for i in range(0, len(xs), per):
        lines.append('    ' + ', '.join(str(x) for x in xs[i:i + per]) + ',')
    lines.append(']')
    return '\n'.join(lines)

def write_module(m, data):
    vals = {}
    for cp, ai, asr, kind, sw, dw in data:
        if kind == 1: vals[cp] = (1 << 24) | (ai << 8) | (asr - m.gmin[ai])
        elif kind == 0: vals[cp] = 0
        elif kind == 2: vals[cp] = (2 << 24) | dw
        else: vals[cp] = (3 << 24) | sw
    rs = runs(vals)
    exp_cp, exp_at, exp_n, exp_el = [], [], [], []
    for cp in sorted(m.exp):
        els = m.letter(cp)
        exp_cp.append(cp); exp_at.append(len(exp_el)); exp_n.append(len(els))
        for p, s in els: exp_el.append((p << 8) | s)
    comps = []
    marks = [r[0] for r in data if r[3] == 2]
    for cp in sorted(vals):
        if vals[cp] >> 24 != 1: continue
        for mk in marks:
            c = unicodedata.normalize('NFC', chr(cp) + chr(mk))
            if len(c) == 1 and m.kind(ord(c)) == 1: comps.append((cp, mk, ord(c)))
    comps.sort()
    src = f"""// lexdb_sqlcoll: SQL Server's order for its default collation, {COLL}
// on nvarchar (generated; do not edit). design/lexdb-tds.md, L2.
//
// Generated by lexell/tools/gen_sqlserver_collation.py from SQL Server 2022
// (the oracle): per code point of the BMP, a value: kind << 24 | data.
// Kind 0: ignored. 1: a letter, data its primary weight << 8 | its
// secondary (its accent's rank among its letter's). 2: a combining mark,
// data its weight. 3: a hyphen-like mark, ignored by the letters, data its
// weight. In runs: RUN_START[i] .. + RUN_LEN[i] - 1 have RUN_VAL[i] + k *
// RUN_STEP[i]. A code point in none: a letter weighted after all of these.

{ints('RUN_START', [r[0] for r in rs])}

{ints('RUN_LEN', [r[1] for r in rs])}

{ints('RUN_VAL', [r[2] for r in rs])}

{ints('RUN_STEP', [r[3] for r in rs])}

// The values of code points 0 to 127 (-1: in no run), as the runs give them.
{ints('ASCII', [vals.get(c, -1) for c in range(128)], 8)}

// Expansions: EXP_CP[i] is EXP_N[i] letters, EXP_EL[EXP_AT[i] ..] (primary << 8 | secondary).
{ints('EXP_CP', exp_cp)}

{ints('EXP_AT', exp_at)}

{ints('EXP_N', exp_n)}

{ints('EXP_EL', exp_el)}

// A letter and a combining mark after it that make one letter: COMP_TO[i]
// is COMP_BASE[i] then COMP_MARK[i] (sorted by base, then mark).
{ints('COMP_BASE', [c[0] for c in comps])}

{ints('COMP_MARK', [c[1] for c in comps])}

{ints('COMP_TO', [c[2] for c in comps])}
"""
    with open(OUT, 'w', encoding='utf-8') as f: f.write(src)
    print(f'{OUT}: {len(rs)} runs, {len(exp_cp)} expansions, {len(comps)} compositions')

ALPHABET = ([chr(c) for c in range(0x20, 0x7f)] + [chr(c) for c in range(0xa0, 0x180)] + [chr(c) for c in range(0x391, 0x3ca)] +
            [chr(c) for c in range(0x410, 0x450)] + ['‐', '–', '—', '‘', '’', '“', '”', '…',
            '€', '­', 'é', 'ö', 'Ǆ', 'ǣ', 'ẞ'])

def oracle_ranks(ws):
    lines = ['set nocount on;', 'create table #w (id int primary key, w nvarchar(40));']
    for i in range(0, len(ws), 500):
        vals = ','.join("(%d, N'%s')" % (j, ws[j].replace("'", "''")) for j in range(i, min(i + 500, len(ws))))
        lines.append('insert #w values ' + vals + ';')
    lines.append(f'select id, dense_rank() over (order by w collate {COLL}) from #w order by id;')
    rk = {}
    for r in sql('\n'.join(lines) + '\n'):
        i, k = r.split('|')
        rk[int(i)] = int(k)
    return [rk[i] for i in range(len(ws))]

def strings(n, seed):
    rnd = random.Random(seed)
    ws = set()
    while len(ws) < n:
        ws.add(''.join(rnd.choice(ALPHABET) for _ in range(rnd.randint(1, 6))))
    return sorted(ws)

def compare(m, ws, rk):
    ks = [m.key(w) for w in ws]
    idx = sorted(range(len(ws)), key=lambda i: rk[i])
    bad = []
    for a, b in zip(idx, idx[1:]):
        if rk[a] == rk[b] and ks[a] != ks[b]: bad.append(('=', ws[a], ws[b]))
        elif rk[a] != rk[b] and not ks[a] < ks[b]: bad.append(('<', ws[a], ws[b]))
    return bad

def lxl_str(s):
    out = []
    for ch in s:
        if ch == '"' or ch == '\\': out.append('\\' + ch)
        elif ord(ch) < 0x20 or ord(ch) == 0x7f or ord(ch) == 0xad or unicodedata.category(ch) in ('Mn', 'Cf'):
            out.append(''.join('\\x%02x' % b for b in ch.encode('utf-8')))     # Lexell's escapes are bytes
        else: out.append(ch)
    return '"' + ''.join(out) + '"'

def write_test(ws, rk):
    order = sorted(range(len(ws)), key=lambda i: (rk[i], i))
    body = ',\n'.join('    ' + lxl_str(ws[i]) for i in order)
    ranks = ints('RANKS', [rk[i] for i in order], 20).replace('pub const', 'const')
    src = f"""// lexdb_exec.ciKey against SQL Server's order (generated by
// lexell/tools/gen_sqlserver_collation.py; do not edit): {len(ws)} strings
// as the oracle ({COLL}) ranks them, ties alike. Keys must give the same
// order and the same ties. design/lexdb-tds.md, L2.
// expect: ok {len(ws)}
import "../../../cmd/lexdb_exec"

const WORDS: []str = [
{body}
]

{ranks}

fn main() {{
    var bad = 0
    var prev = lexdb_exec.ciKey(&WORDS[0])
    for i in 1..len(WORDS) {{
        let k = lexdb_exec.ciKey(&WORDS[i])
        let want = RANKS[i] == RANKS[i - 1]
        let ok = if want {{ k == prev }} else {{ prev < k }}
        if !ok {{
            if bad < 20 {{ println("wrong: " + WORDS[i - 1] + " then " + WORDS[i] + (if want {{ " (equal)" }} else {{ "" }})) }}
            bad += 1
        }}
        prev = k
    }}
    if bad == 0 {{ println("ok " + len(WORDS).toStr()) }} else {{ println(bad.toStr() + " wrong") }}
}}
"""
    with open(TEST, 'w', encoding='utf-8') as f: f.write(src)
    print(f'{TEST}: {len(ws)} strings')

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--check', type=int, default=0, help='rank N more random strings in the oracle and compare')
    ap.add_argument('--test', type=int, default=1500, help='strings in the generated test')
    a = ap.parse_args()
    data, expansions = extract()
    m = Model(data, expansions)
    write_module(m, data)
    ws = strings(a.test, 2026)
    rk = oracle_ranks(ws)
    bad = compare(m, ws, rk)
    print(f'test strings: {len(bad)} the model orders otherwise')
    write_test(ws, rk)
    if a.check:
        ws = strings(a.check, 7)
        bad = compare(m, ws, oracle_ranks(ws))
        print(f'check: {len(ws)} strings, {len(bad)} ordered otherwise')
        for b in bad[:40]: print('  ', b[0], repr(b[1]), repr(b[2]))

if __name__ == '__main__':
    main()
