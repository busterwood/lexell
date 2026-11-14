#!/usr/bin/env python3
"""PL/SQL through python-oracledb (thin) against lexdb's TNS door (design/lexdb-oracle.md, stage O6): anonymous blocks,
control flow, exceptions, cursors, records, SELECT INTO, EXECUTE IMMEDIATE, DBMS_OUTPUT, procedures and functions
(callproc / callfunc), OUT binds, REF CURSOR OUT and implicit results.

    python3 lexell/tests/lexdb/oracledb_o6.py [--lexdb PATH] [--tns-port 15215]      # against a built lexdb
    python3 lexell/tests/lexdb/oracledb_o6.py --oracle app/PASSWORD@127.0.0.1:1521/FREEPDB1 --record   # regenerates EXPECT

Each scenario is a list of steps (a statement, with its binds); a step's result is its rows, its OUT binds or its
error. The expected results were recorded from Oracle Database Free (oracle_o6_expect.json); this runs the same
scenarios against lexdb and compares. Needs python-oracledb."""
import argparse, datetime, decimal, json, os, re, shutil, subprocess, sys, tempfile, time
import oracledb

HERE = os.path.dirname(os.path.abspath(__file__))
EXPECT = os.path.join(HERE, 'oracle_o6_expect.json')

ap = argparse.ArgumentParser()
ap.add_argument('--lexdb', default='lexdb')
ap.add_argument('--tns-port', type=int, default=15215)
ap.add_argument('--pg-port', type=int, default=15216)
ap.add_argument('--oracle', default=None, help='user/password@host:port/service of an Oracle to run against')
ap.add_argument('--record', action='store_true', help='write the results to oracle_o6_expect.json (with --oracle)')
ap.add_argument('--only', default=None)
ap.add_argument('--verbose', action='store_true')
a = ap.parse_args()

CLEAN = ['drop table t1', 'drop table t2', 'drop table t3', 'drop procedure p1', 'drop procedure p2', 'drop procedure p3',
         'drop function f1', 'drop function f2', 'drop function f3', 'drop sequence s1', 'drop package pk1', 'drop package pk2']


def norm(v):
    if isinstance(v, decimal.Decimal):
        return int(v) if v == int(v) else float(v)
    if isinstance(v, float) and v == int(v) and abs(v) < 1e15:
        return int(v)
    if isinstance(v, (datetime.datetime, datetime.date)):
        return v.isoformat()
    if isinstance(v, oracledb.LOB):
        return v.read()
    if isinstance(v, (list, tuple)):
        return [norm(x) for x in v]
    return v


def errtext(e):
    """The lines of an error: Oracle's long PLS-00103 lists and the names of constraints are cut, columns dropped."""
    s = str(e.args[0]) if e.args else str(e)
    out = []
    for l in s.split('\n'):
        if not l.strip() or l.startswith('Help:') or l.startswith('ORA-03301') or l.startswith(' '):
            continue
        l = re.sub(r'^ORA-06550: line (\d+), column \d+:', r'ORA-06550: line \1', l)
        if l.startswith('PLS-00103'):
            l = 'PLS-00103'
        l = re.sub(r'^(ORA-00001: unique constraint) \(.*', r'\1 violated', l)
        l = re.sub(r'\bSA\.', 'APP.', l)
        out.append(l)
    return out


# -- the scenarios: (name, [steps]); a step is sql or (sql, binds) where a bind is a value or ('out', type[, size]) or ('inout', type, value)
S = []


def sc(name, *steps):
    S.append((name, list(steps)))


OUT_NUM = ('out', int)
OUT_STR = ('out', str, 400)
OUT_FLT = ('out', float)


def blk(body, decl='', binds=None):
    t = ('declare\n' + decl + '\n' if decl else '') + 'begin\n' + body + '\nend;'
    return (t, binds or {})


sc('arith', blk(":r := 1 + 2 * 3; :s := 'a' || 'b' || 5; :f := 7 / 2; :m := mod(17, 5);", binds={'r': OUT_NUM, 's': OUT_STR, 'f': OUT_FLT, 'm': OUT_NUM}))
sc('vars', blk("v := 10; w := v * 2; :r := w + 1; :t := s || '!';", 'v number := 5; w number; s varchar2(10) := \'hi\';',
               {'r': OUT_NUM, 't': OUT_STR}))
sc('const and default', blk(":r := c + d;", 'c constant number := 3; d number default 4;', {'r': OUT_NUM}))
sc('if', blk("if :x > 10 then :r := 'big'; elsif :x > 5 then :r := 'mid'; elsif :x is null then :r := 'null'; else :r := 'small'; end if;",
             binds={'x': 7, 'r': OUT_STR}),
   blk("if :x > 10 then :r := 'big'; elsif :x > 5 then :r := 'mid'; elsif :x is null then :r := 'null'; else :r := 'small'; end if;",
       binds={'x': 70, 'r': OUT_STR}),
   blk("if :x > 10 then :r := 'big'; elsif :x > 5 then :r := 'mid'; elsif :x is null then :r := 'null'; else :r := 'small'; end if;",
       binds={'x': 1, 'r': OUT_STR}),
   blk("if :x > 10 then :r := 'big'; elsif :x > 5 then :r := 'mid'; else :r := 'small'; end if;", binds={'x': None, 'r': OUT_STR}))
sc('loops', blk("i := 0; loop i := i + 1; exit when i >= 5; end loop; :a := i;"
                " j := 0; while j < 10 loop j := j + 3; end loop; :b := j;"
                " for k in 1..4 loop s := s + k; end loop; :c := s;"
                " for k in reverse 1..3 loop t := t || k; end loop; :d := t;",
                'i number; j number; s number := 0; t varchar2(20);', {'a': OUT_NUM, 'b': OUT_NUM, 'c': OUT_NUM, 'd': OUT_STR}))
sc('exit continue labels', blk("<<outer>> for i in 1..5 loop for j in 1..5 loop if j = 3 then continue outer; end if; if i = 4 then exit outer; end if; n := n + 1; end loop; end loop; :r := n;"
                               " for i in 1..10 loop continue when mod(i, 2) = 0; m := m + i; end loop; :q := m;",
                               'n number := 0; m number := 0;', {'r': OUT_NUM, 'q': OUT_NUM}))
sc('case', blk("for i in 1..4 loop case i when 1 then s := s || 'a'; when 2 then s := s || 'b'; else s := s || 'z'; end case; end loop;"
               " case when :x < 0 then t := 'neg'; when :x = 0 then t := 'zero'; else t := 'pos'; end case; :r := s || t;",
               's varchar2(20); t varchar2(10);', {'x': 3, 'r': OUT_STR}),
   blk("case :x when 1 then null; end case;", binds={'x': 2}))
sc('case expr', blk(":r := case when :x > 1 then 'y' else 'n' end || case :x when 1 then 'one' when 2 then 'two' end;", binds={'x': 2, 'r': OUT_STR}))
sc('nulls and empty strings', blk("s := ''; if s is null then :a := 1; end if; t := 'x'; t := null; :b := nvl(t, 'dflt'); :c := length(s);",
                                  's varchar2(5); t varchar2(5);', {'a': OUT_NUM, 'b': OUT_STR, 'c': OUT_NUM}))
sc('too long', blk("s := 'abcdef';", 's varchar2(3);'))
sc('number overflow', blk("n := 123456;", 'n number(4);'))
sc('boolean', blk("b := 3 > 2; if b then :a := 1; end if; b := not b; if not b then :c := 2; end if; if b is null then :d := 1; end if;",
                  'b boolean;', {'a': OUT_NUM, 'c': OUT_NUM, 'd': OUT_NUM}))
sc('select into', 'create table t1 (a number, b varchar2(20))', "insert into t1 values (1, 'one')", "insert into t1 values (2, 'two')",
   blk("select b into s from t1 where a = :x; :r := s; select count(*), max(a) into n, m from t1; :c := n * 100 + m;",
       's varchar2(20); n number; m number;', {'x': 2, 'r': OUT_STR, 'c': OUT_NUM}),
   blk("select b into s from t1 where a = 99;", 's varchar2(20);'),
   blk("select b into s from t1;", 's varchar2(20);'))
sc('no data found handlers', 'create table t1 (a number, b varchar2(20))',
   blk("begin select b into s from t1 where a = 1; exception when no_data_found then s := 'none'; end; :r := s; :c := sqlcode;"
       " begin select b into s from t1; exception when others then :e := sqlerrm; end;", 's varchar2(20);',
       {'r': OUT_STR, 'c': OUT_NUM, 'e': OUT_STR}),
   "insert into t1 values (1, 'x')", "insert into t1 values (2, 'y')",
   blk("begin select b into s from t1; exception when too_many_rows then :r := 'many'; :c := sqlcode; :e := sqlerrm; end;", 's varchar2(20);',
       {'r': OUT_STR, 'c': OUT_NUM, 'e': OUT_STR}))
sc('user exceptions', blk("begin raise my_err; exception when my_err then :r := 'caught'; :c := sqlcode; :e := sqlerrm; end;"
                          " begin raise_application_error(-20005, 'custom'); exception when others then :r2 := sqlerrm; :c2 := sqlcode; end;",
                          'my_err exception;', {'r': OUT_STR, 'c': OUT_NUM, 'e': OUT_STR, 'r2': OUT_STR, 'c2': OUT_NUM}),
   blk("raise my_err;", 'my_err exception;'),
   blk("raise_application_error(-20001, 'boom');"),
   blk("raise_application_error(-19999, 'boom');"),
   blk("declare e1 exception; pragma exception_init(e1, -20010); begin raise_application_error(-20010, 'zz'); exception when e1 then :r := 'got e1 ' || sqlcode; end;",
       binds={'r': OUT_STR}),
   blk("x := 1 / 0;", 'x number;'),
   blk("begin x := 1 / 0; exception when zero_divide then :r := sqlcode || ':' || sqlerrm; end;", 'x number;', {'r': OUT_STR}),
   blk("x := to_number('abc');", 'x number;'),
   blk("begin x := to_number('abc'); exception when invalid_number then :r := 'inv'; when value_error then :r := 've'; end;", 'x number;', {'r': OUT_STR}),
   blk("n := 'abc';", 'n number;'))
sc('nested handlers', blk("begin begin raise_application_error(-20001, 'in'); exception when others then :a := 'inner ' || sqlerrm; raise; end;"
                          " exception when others then :b := 'outer ' || sqlerrm; end;", binds={'a': OUT_STR, 'b': OUT_STR}),
   blk("begin raise_application_error(-20001, 'in'); exception when no_data_found then :a := 'no'; end;", binds={'a': OUT_STR}),
   blk("begin null; exception when others then null; end; :r := 1;", binds={'r': OUT_NUM}))
sc('dml and rowcount', 'create table t1 (a number, b varchar2(20))',
   blk("insert into t1 values (1, 'a'); :i := sql%rowcount; insert into t1 values (2, 'b'); insert into t1 values (3, 'c');"
       " update t1 set b = 'z' where a > 1; :u := sql%rowcount; delete from t1 where a = 99; :d := sql%rowcount;"
       " if sql%notfound then :nf := 1; end if; delete from t1 where a = 1; if sql%found then :f := 1; end if;",
       binds={'i': OUT_NUM, 'u': OUT_NUM, 'd': OUT_NUM, 'nf': OUT_NUM, 'f': OUT_NUM}),
   'select a, b from t1 order by a')
sc('returning into', 'create table t1 (a number, b varchar2(20))',
   blk("insert into t1 values (7, 'q') returning a, b into n, s; :n := n; :s := s; update t1 set a = a + 1 where a = 7 returning a into n; :m := n;",
       'n number; s varchar2(20);', {'n': OUT_NUM, 's': OUT_STR, 'm': OUT_NUM}))
sc('block atomicity', 'create table t1 (a number primary key)', "insert into t1 values (100)",
   blk("insert into t1 values (1); insert into t1 values (2); insert into t1 values (1);"),
   'select a from t1 order by a',
   blk("insert into t1 values (5); begin insert into t1 values (5); exception when dup_val_on_index then :r := 'dup'; end; insert into t1 values (6);", binds={'r': OUT_STR}),
   'select a from t1 order by a',
   blk("insert into t1 values (7); raise_application_error(-20001, 'x');"),
   'select a from t1 order by a')
sc('commit rollback in block', 'create table t1 (a number)',
   blk("insert into t1 values (1); commit; insert into t1 values (2); rollback; insert into t1 values (3);"),
   'select a from t1 order by a',
   blk("savepoint sp1; insert into t1 values (4); rollback to sp1; insert into t1 values (5);"),
   'select a from t1 order by a')
sc('explicit cursor', 'create table t1 (a number, b varchar2(20))', "insert into t1 values (1, 'a')", "insert into t1 values (2, 'b')", "insert into t1 values (3, 'c')",
   blk("open c; loop fetch c into n, s; exit when c%notfound; t := t || s; end loop; :cnt := c%rowcount; close c; :r := t;",
       'cursor c is select a, b from t1 order by a; n number; s varchar2(20); t varchar2(20);', {'cnt': OUT_NUM, 'r': OUT_STR}),
   blk("open c(2); fetch c into r; :a := r.a; :b := r.b; if c%isopen then :o := 1; end if; close c; if not c%isopen then :p := 1; end if;",
       'cursor c(lim number) is select a, b from t1 where a >= lim order by a; r c%rowtype;', {'a': OUT_NUM, 'b': OUT_STR, 'o': OUT_NUM, 'p': OUT_NUM}),
   blk("fetch c into n;", 'cursor c is select a from t1; n number;'))
sc('cursor for loop', 'create table t1 (a number, b varchar2(20))', "insert into t1 values (1, 'a')", "insert into t1 values (2, 'b')", "insert into t1 values (3, 'c')",
   blk("for r in (select a, b from t1 order by a desc) loop t := t || r.b || r.a; end loop; :r := t;"
       " for r in c loop n := n + r.a; end loop; :n := n;", 'cursor c is select a from t1; t varchar2(20); n number := 0;', {'r': OUT_STR, 'n': OUT_NUM}),
   blk("for r in (select a from t1 where a > 100) loop :r := 'never'; end loop; :q := 'done';", binds={'r': OUT_STR, 'q': OUT_STR}))
sc('records and types', 'create table t1 (a number, b varchar2(20))', "insert into t1 values (1, 'a')",
   blk("select * into r from t1 where a = 1; :a := r.a; :b := r.b; r2 := r; r2.b := 'zz'; :c := r2.b || r.b; x := r.a; y := r.b; :d := x || y;",
       'r t1%rowtype; r2 t1%rowtype; x t1.a%type; y t1.b%type;', {'a': OUT_NUM, 'b': OUT_STR, 'c': OUT_STR, 'd': OUT_STR}),
   blk("r.id := 5; r.nm := 'hi'; :a := r.id; :b := r.nm;", 'type rt is record (id number, nm varchar2(10)); r rt;', {'a': OUT_NUM, 'b': OUT_STR}))
sc('execute immediate', 'create table t1 (a number, b varchar2(20))',
   blk("execute immediate 'insert into t1 values (:1, :2)' using 5, 'five'; execute immediate 'select b from t1 where a = :x' into s using 5; :r := s;"
       " execute immediate 'create table t2 (z number)'; execute immediate 'insert into t2 values (1)'; commit; execute immediate 'drop table t2';"
       " n := 3; execute immediate 'begin :1 := :2 * 2; end;' using out n, 21; :n := n;", 's varchar2(20); n number;', {'r': OUT_STR, 'n': OUT_NUM}),
   blk("execute immediate 'select b from t1 where a = 99' into s;", 's varchar2(20);'),
   blk("execute immediate 'garbage';"),
   'select a, b from t1')
sc('dbms_output', blk("dbms_output.put_line('hello'); dbms_output.put('a'); dbms_output.put('b'); dbms_output.new_line; dbms_output.put_line(1.5 || 'x'); dbms_output.put_line(42);"),
   ('begin dbms_output.enable(null); end;', {}),
   blk("dbms_output.put_line('hello'); dbms_output.put('a'); dbms_output.put('b'); dbms_output.new_line; dbms_output.put_line(1.5 || 'x'); dbms_output.put_line(42); dbms_output.put_line(null);"),
   ('begin dbms_output.get_line(:l, :s); end;', {'l': OUT_STR, 's': OUT_NUM}),
   ('begin dbms_output.get_line(:l, :s); end;', {'l': OUT_STR, 's': OUT_NUM}),
   ('GETLINES', 100),
   ('begin dbms_output.get_line(:l, :s); end;', {'l': OUT_STR, 's': OUT_NUM}))
sc('procedures', 'create table t1 (a number, b varchar2(20))',
   ("create or replace procedure p1(x in number, y out number, z in out varchar2) is begin y := x * 2; z := z || '!'; insert into t1 values (x, z); end;", {}),
   ("begin p1(:x, :y, :z); end;", {'x': 5, 'y': OUT_NUM, 'z': ('inout', str, 'hey')}),
   ("begin p1(x => 6, y => :y, z => :z); end;", {'y': OUT_NUM, 'z': ('inout', str, 'abc')}),
   ('CALLPROC', 'p1', [7, ('out', int), ('inout', str, 'q')]),
   'select a, b from t1 order by a',
   blk("p1(1, n, s); :a := n; :b := s;", 'n number; s varchar2(20) := \'v\';', {'a': OUT_NUM, 'b': OUT_STR}),
   blk("p1(1);"),
   blk("p9(1);"),
   'drop procedure p1',
   blk("p1(1, n, s);", 'n number; s varchar2(20);'))
sc('functions', ("create or replace function f1(a number, b number default 10) return number is begin return a * b; end;", {}),
   ("create or replace function f2(n number) return number is begin if n <= 1 then return 1; end if; return n * f2(n - 1); end;", {}),
   ("create or replace function f3(s varchar2) return varchar2 is begin return upper(s) || '!'; end;", {}),
   ("begin :r := f1(3); end;", {'r': OUT_NUM}),
   ("begin :r := f1(3, 4) + f2(5); end;", {'r': OUT_NUM}),
   ("begin :r := f3('abc') || f3('d'); end;", {'r': OUT_STR}),
   ("begin :r := f1(b => 2, a => 5); end;", {'r': OUT_NUM}),
   ('CALLFUNC', 'f1', int, [6, 7]),
   ('CALLFUNC', 'f3', str, ['x']),
   ('CALLFUNC', 'f2', int, [10]),
   blk("n := f2(6); :r := n; if f1(2) = 20 then :q := 'yes'; end if;", 'n number;', {'r': OUT_NUM, 'q': OUT_STR}),
   ("create or replace function f1(a number) return number is begin null; end;", {}),
   ("begin :r := f1(1); end;", {'r': OUT_NUM}))
sc('proc errors', ("create or replace procedure p1(n number) is begin if n = 0 then raise_application_error(-20002, 'zero!'); end if; insert into t1 values (n, 'x'); end;", {}),
   'create table t1 (a number, b varchar2(20))',
   ("begin p1(0); end;", {}), ("begin p1(1); end;", {}),
   blk("begin p1(0); exception when others then :r := sqlerrm; end;", binds={'r': OUT_STR}),
   "select a from t1",
   ("create or replace procedure p2 is begin p1(0); end;", {}), ("begin p2; end;", {}),
   ("create or replace procedure p3 is begin select a into x from t1 where a = 99; end;", {}),
   ("begin p3; end;", {}))
sc('ref cursor', 'create table t1 (a number, b varchar2(20))', "insert into t1 values (1, 'a')", "insert into t1 values (2, 'b')", "insert into t1 values (3, 'c')",
   ('REFCUR', "begin open :c for select a, b from t1 order by a; end;"),
   ("create or replace procedure p1(n number, rc out sys_refcursor) is begin open rc for select a, b from t1 where a >= n order by a; end;", {}),
   ('REFCUR2', 'p1', 2),
   ("create or replace function f1(n number) return sys_refcursor is rc sys_refcursor; begin open rc for select a from t1 where a = n; return rc; end;", {}),
   ('REFFUNC', 'f1', 3))
sc('implicit results', 'create table t1 (a number, b varchar2(20))', "insert into t1 values (1, 'a')", "insert into t1 values (2, 'b')",
   ('IMPLICIT', "declare c1 sys_refcursor; c2 sys_refcursor; begin open c1 for select a from t1 order by a; dbms_sql.return_result(c1); open c2 for select b from t1 order by b desc; dbms_sql.return_result(c2); end;"))
sc('call', ("create or replace procedure p1(x number, y out number) is begin y := x + 1; end;", {}),
   ("create or replace function f1(x number) return number is begin return x * 3; end;", {}),
   ("call p1(1, :y)", {'y': OUT_NUM}),
   ("call f1(4) into :r", {'r': OUT_NUM}))
sc('dates', blk("d := to_date('2024-03-05', 'YYYY-MM-DD'); :a := to_char(d + 1, 'YYYY-MM-DD'); :d := d + 1; n := to_date('2024-03-05 10:11:12', 'YYYY-MM-DD HH24:MI:SS'); :n := n;",
                'd date; n date;', {'a': OUT_STR, 'd': ('out', datetime.datetime), 'n': ('out', datetime.datetime)}))
sc('bind in out', ("begin :x := :x * 2; :y := :y || 'z'; end;", {'x': ('inout', int, 21), 'y': ('inout', str, 'ab')}),
   ("begin :a := :b; end;", {'a': OUT_STR, 'b': None}),
   ("begin if :a is null then :b := 1; else :b := 2; end if; end;", {'a': None, 'b': OUT_NUM}))
sc('compile errors', blk("x := ;", 'x number;'), blk("y := 1;"), blk("select b into s from nosuch;", 's varchar2(5);'), blk("for i in 1..3 loop"),
   blk("null;", "x nosuchtype;"))
sc('sequence', 'create sequence s1', blk("n := s1.nextval; :a := n; :b := s1.nextval;", 'n number;', {'a': OUT_NUM, 'b': OUT_NUM}),
   blk("select s1.nextval into n from dual; :a := n;", 'n number;', {'a': OUT_NUM}))
sc('stored in sql', ("create or replace function f1(a number) return number is begin return a + 100; end;", {}),
   'select f1(5) from dual')
sc('long loop', 'create table t1 (a number)',
   blk("for i in 1..200 loop insert into t1 values (i); end loop; select sum(a) into n from t1; :r := n;", 'n number;', {'r': OUT_NUM}),
   blk("n := 0; for i in 1..2000 loop n := n + i; end loop; :r := n;", 'n number;', {'r': OUT_NUM}))
sc('after error txn ok', 'create table t1 (a number primary key)', "insert into t1 values (1)",
   blk("insert into t1 values (2); x := 1 / 0;", 'x number;'), 'select a from t1 order by a', "insert into t1 values (3)", 'select a from t1 order by a')


sc('name conflicts', 'create table t1 (a number, b varchar2(20))', "insert into t1 values (1, 'x')", "insert into t1 values (2, 'y')",
   blk("insert into t1 (a, b) values (a, b); select count(*) into n from t1 where a = a; :n := n; select b into s from t1 where a = 99; :s := s;",
       'a number := 99; b varchar2(5) := \'vv\'; n number; s varchar2(20);', {'n': OUT_NUM, 's': OUT_STR}),
   blk("update t1 set b = b || '!' where a = :k; :c := sql%rowcount;", 'b varchar2(5) := \'zz\';', {'k': 1, 'c': OUT_NUM}),
   'select a, b from t1 order by a')
sc('cursor params loop', 'create table t1 (a number, b varchar2(20))', "insert into t1 values (1, 'a')", "insert into t1 values (2, 'b')", "insert into t1 values (3, 'c')",
   blk("for r in c(2) loop t := t || r.b; end loop; :r := t; open c(3); fetch c into x; :x := x.a; close c;",
       'cursor c(m number) is select a, b from t1 where a >= m order by a; t varchar2(20); x c%rowtype;', {'r': OUT_STR, 'x': OUT_NUM}))
sc('shadowing and scope', blk("v := 'outer'; declare v varchar2(10) := 'inner'; begin :a := v; end; :b := v; begin v := 'changed'; end; :c := v;",
                              'v varchar2(10);', {'a': OUT_STR, 'b': OUT_STR, 'c': OUT_STR}),
   blk("for i in 1..2 loop declare n number := i * 10; begin :r := nvl(:r, 0) + n; end; end loop;", binds={'r': ('inout', int, 0)}))
sc('declare section errors', blk("begin x := 1; exception when others then :e := 'inner ' || sqlerrm; end;", 'x number := 1 / 0;', {'e': OUT_STR}),
   blk("declare x number := 1 / 0; begin null; exception when others then :e := 'inner ' || sqlerrm; end;", binds={'e': OUT_STR}),
   blk("begin declare x number := 1 / 0; begin null; exception when others then :e := 'inner ' || sqlerrm; end; exception when zero_divide then :e := 'outer'; end;", binds={'e': OUT_STR}))
sc('handler raises', blk("begin raise_application_error(-20001, 'one'); exception when others then raise_application_error(-20002, 'two'); end;"),
   blk("begin begin raise no_data_found; exception when no_data_found then raise too_many_rows; end; exception when too_many_rows then :r := 'tmr'; when others then :r := 'other'; end;", binds={'r': OUT_STR}))
sc('implicit attrs', 'create table t1 (a number)', "insert into t1 values (1)", "insert into t1 values (2)",
   blk("update t1 set a = a + 1; :u := sql%rowcount; select a into n from t1 where a = 3; :s := sql%rowcount; if sql%found then :f := 'f'; end if;"
       " begin select a into n from t1 where a = 99; exception when no_data_found then :nf := sql%rowcount; end;", 'n number;',
       {'u': OUT_NUM, 's': OUT_NUM, 'f': OUT_STR, 'nf': OUT_NUM}))
sc('insert select and dml', 'create table t1 (a number, b varchar2(20))', 'create table t2 (a number, b varchar2(20))',
   "insert into t1 values (1, 'a')", "insert into t1 values (2, 'b')",
   blk("insert into t2 select a, b from t1 where a >= v; :i := sql%rowcount; delete from t2 where a = 2; :d := sql%rowcount;", 'v number := 1;', {'i': OUT_NUM, 'd': OUT_NUM}),
   'select a, b from t2')
sc('null logic', blk("if null = null then :a := 1; else :a := 2; end if; if null is null then :b := 1; end if; x := null; if x = 1 or true then :c := 1; end if; if x = 1 and false then :d := 1; else :d := 2; end if; :e := nvl(x, 7) + nvl2(x, 1, 2);",
                     'x number;', {'a': OUT_NUM, 'b': OUT_NUM, 'c': OUT_NUM, 'd': OUT_NUM, 'e': OUT_NUM}))
sc('strings', blk(":a := upper('abc') || lower('DEF') || substr('hello', 2, 3) || instr('hello', 'l') || length('four') || trim('  x ') || replace('aaa', 'a', 'b'); :b := lpad('7', 3, '0') || rpad('x', 3, '-') || to_char(12.5) || to_char(5, '00') || chr(65);",
                  binds={'a': OUT_STR, 'b': OUT_STR}))
sc('numeric types', blk("a := 7 / 2; b := trunc(a); c := round(2.567, 2); d := floor(-1.5) + ceil(1.2); e := power(2, 10) + sqrt(16) + abs(-3) + sign(-9); i := 7; i := i / 2; j := 2.5; k := 5 mod 3; :a := a; :b := b; :c := c; :d := d; :e := e; :i := i; :j := j; :k := k;",
                       'a number; b number; c number; d number; e number; i pls_integer; j integer; k number;',
                       {'a': OUT_FLT, 'b': OUT_NUM, 'c': OUT_FLT, 'd': OUT_NUM, 'e': OUT_NUM, 'i': OUT_NUM, 'j': OUT_NUM, 'k': OUT_NUM}))
sc('large loop', blk("for i in 1..20000 loop n := n + mod(i, 7); end loop; :r := n;", 'n number := 0;', {'r': OUT_NUM}))
sc('exit in nested', blk("loop n := n + 1; for i in 1..10 loop exit when i > 2; m := m + 1; end loop; exit when n >= 3; end loop; :n := n; :m := m;", 'n number := 0; m number := 0;', {'n': OUT_NUM, 'm': OUT_NUM}))
sc('proc defaults and recursion', ("create or replace procedure p1(n number, acc in out number) is begin if n > 0 then acc := acc + n; p1(n - 1, acc); end if; end;", {}),
   blk("a := 0; p1(10, a); :r := a;", 'a number;', {'r': OUT_NUM}),
   ("create or replace procedure p2(a number default 1, b varchar2 default 'z', c out varchar2) is begin c := a || b; end;", {}),
   blk("p2(c => s); :a := s; p2(5, c => s); :b := s; p2(b => 'q', a => 3, c => s); :c := s;", 's varchar2(10);', {'a': OUT_STR, 'b': OUT_STR, 'c': OUT_STR}))
sc('dbms_output enable limits', ('begin dbms_output.enable(1000000); end;', {}),
   blk("for i in 1..5 loop dbms_output.put_line('line ' || i); end loop;"), ('GETLINES', 3), ('GETLINES', 10), ('GETLINES', 10))
sc('transaction control', 'create table t1 (a number)',
   blk("insert into t1 values (1); commit; insert into t1 values (2); rollback; insert into t1 values (3); execute immediate 'create table t2 (z number)'; rollback;"),
   'select a from t1 order by a', 'drop table t2')

PK1 = """create or replace package pk1 is
  e_bad exception;
  c_max constant number := 10;
  procedure inc(n number default 1);
  function get return number;
  function twice(x number) return number;
  procedure fail;
  procedure peek(h out varchar2);
end pk1;"""
PK1B = """create or replace package body pk1 is
  counter number := 0;
  history varchar2(100);
  procedure note(s varchar2) is begin history := history || s; end;
  procedure inc(n number default 1) is
  begin
    counter := counter + n;
    note('i' || n);
  end;
  function get return number is begin return counter; end;
  function twice(x number) return number is begin return x * 2 + c_max; end;
  procedure fail is begin raise e_bad; end;
  procedure peek(h out varchar2) is begin h := history; end;
begin
  counter := 100;
end pk1;"""
sc('packages', (PK1, {}), (PK1B, {}),
   ("begin pk1.inc; pk1.inc(5); :r := pk1.get; :t := pk1.twice(4); end;", {'r': OUT_NUM, 't': OUT_NUM}),
   ("begin pk1.inc(2); :r := pk1.get; pk1.peek(:h); end;", {'r': OUT_NUM, 'h': OUT_STR}),
   ("begin pk1.fail; end;", {}),
   ("begin begin pk1.fail; exception when others then :s := sqlerrm; :c := sqlcode; end; end;", {'s': OUT_STR, 'c': OUT_NUM}),
   ("begin pk1.note('x'); end;", {}),
   ("begin pk1.nosuch; end;", {}),
   ('CALLFUNC', 'pk1.twice', int, [20]),
   ('CALLPROC', 'pk1.inc', [3]),
   ('CALLFUNC', 'pk1.get', int, []),
   'select pk1.twice(1) from dual',
   "drop package pk1",
   ("begin pk1.inc; end;", {}))
sc('packages calling packages', (PK1, {}), (PK1B, {}),
   ("""create or replace package pk2 is function both(n number) return number; end;""", {}),
   ("""create or replace package body pk2 is
        function both(n number) return number is
          x number;
        begin
          pk1.inc(n);
          x := pk1.twice(n) + pk1.get;
          return x;
        end;
      end;""", {}),
   ("begin :r := pk2.both(1); :q := pk2.both(2); end;", {'r': OUT_NUM, 'q': OUT_NUM}),
   ("create or replace procedure p1(n out number) is begin n := pk2.both(0); end;", {}),
   ("begin p1(:n); end;", {'n': OUT_NUM}))

def bindvar(cur, spec):
    if isinstance(spec, tuple):
        if spec[0] == 'out':
            if spec[1] is str:
                return cur.var(str, spec[2] if len(spec) > 2 else 4000)
            return cur.var(spec[1])
        if spec[0] == 'inout':
            v = cur.var(spec[1], spec[3] if len(spec) > 3 else (400 if spec[1] is str else None)) if spec[1] is str else cur.var(spec[1])
            v.setvalue(0, spec[2])
            return v
    return spec


def rows_of(cur):
    return [[norm(x) for x in r] for r in cur.fetchall()]


def do_step(conn, cur, step):
    res = {}
    try:
        if isinstance(step, str):
            cur.execute(step)
            res['rows'] = rows_of(cur) if cur.description else None
            if cur.description is None and cur.rowcount > 0 and step.split()[0].lower() in ('insert', 'update', 'delete'):
                res['rowcount'] = cur.rowcount
        elif step[0] == 'GETLINES':
            lines = cur.arrayvar(str, step[1], 400)
            n = cur.var(int)
            n.setvalue(0, step[1])
            cur.callproc('dbms_output.get_lines', (lines, n))
            res['n'] = n.getvalue()
            res['lines'] = lines.getvalue()[:n.getvalue()]
        elif step[0] == 'CALLPROC':
            args = [bindvar(cur, x) for x in step[2]]
            cur.callproc(step[1], args)
            res['outs'] = [norm(x.getvalue()) if hasattr(x, 'getvalue') else None for x in args]
        elif step[0] == 'CALLFUNC':
            r = cur.callfunc(step[1], step[2], step[3])
            res['ret'] = norm(r)
        elif step[0] == 'REFCUR':
            rc = conn.cursor()
            cur.execute(step[1], {'c': rc})
            res['rows'] = rows_of(rc)
            res['cols'] = [d[0] for d in rc.description]
        elif step[0] == 'REFCUR2':
            rc = cur.var(oracledb.CURSOR)
            cur.callproc(step[1], [step[2], rc])
            c2 = rc.getvalue()
            res['rows'] = rows_of(c2)
        elif step[0] == 'REFFUNC':
            rc = cur.callfunc(step[1], oracledb.CURSOR, [step[2]])
            res['rows'] = rows_of(rc)
        elif step[0] == 'IMPLICIT':
            cur.execute(step[1])
            res['sets'] = [rows_of(r) for r in cur.getimplicitresults()]
        else:
            sql, binds = step
            bv = {k: bindvar(cur, v) for k, v in binds.items()}
            cur.execute(sql, bv)
            outs = {}
            for k, v in bv.items():
                if hasattr(v, 'getvalue'):
                    outs[k] = norm(v.getvalue())
            if outs:
                res['outs'] = outs
            if cur.description:
                res['rows'] = rows_of(cur)
    except oracledb.Error as e:
        res['err'] = errtext(e)
    except Exception as e:
        res['pyerr'] = repr(e)
    return res


def run_all(conn):
    out = {}
    cur = conn.cursor()
    for name, steps in S:
        if a.only and a.only not in name:
            continue
        for sql in CLEAN:
            try:
                cur.execute(sql)
            except oracledb.Error:
                pass
        conn.commit()
        results = []
        for st in steps:
            r = do_step(conn, cur, st)
            if a.verbose:
                print(name, '|', str(st)[:70].replace('\n', ' '), '->', r)
            results.append(r)
        out[name] = results
        try:
            conn.rollback()
        except oracledb.Error:
            pass
    return out


def compare(got, want):
    failed = 0
    for name, results in got.items():
        w = want.get(name)
        if w is None:
            continue
        for i, (g, x) in enumerate(zip(results, w)):
            if g != x:
                failed += 1
                print('FAIL %s step %d\n   got  %s\n   want %s' % (name, i, json.dumps(g)[:600], json.dumps(x)[:600]))
    return failed


if a.oracle:
    userpw, dsn = a.oracle.split('@')
    user, pw = userpw.split('/')
    conn = oracledb.connect(user=user, password=pw, dsn=dsn)
    got = run_all(conn)
    if a.record:
        old = json.load(open(EXPECT)) if os.path.exists(EXPECT) and a.only else {}
        old.update(got)
        json.dump(old, open(EXPECT, 'w'), indent=1, sort_keys=True)
        print('recorded', len(got), 'scenarios')
    else:
        print(json.dumps(got, indent=1))
    sys.exit(0)

tmp = tempfile.mkdtemp()
srv = subprocess.Popen([a.lexdb, tmp + '/data', '127.0.0.1:%d' % a.pg_port, '--tns', '127.0.0.1:%d' % a.tns_port],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(2)
try:
    conn = oracledb.connect(user='sa', password='sa', dsn='127.0.0.1:%d/lexdb' % a.tns_port)
    got = run_all(conn)
    want = json.load(open(EXPECT))
    failed = compare(got, want)
    print('%d scenarios, %d steps differ' % (len(got), failed))
    sys.exit(1 if failed else 0)
finally:
    srv.terminate()
    shutil.rmtree(tmp, ignore_errors=True)
