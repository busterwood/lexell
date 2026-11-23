//! Idiomatic Rust ports of the nine lxl benchmarks that have a hand-written
//! C reference in `lexell/bench/c/`. Each subcommand does the same work as
//! `lexell/bench/NAME.lxl` and prints the same checksum, so bench.py can require
//! identical output.
//!
//! No unsafe, no external crates, no threads. `std::hint::black_box` and
//! command-line sizes (where the C reference has them) keep LLVM from
//! constant-folding or closing the work up. Bounds checks stay on, and the
//! release profile leaves overflow checks on (`Cargo.toml`).

use std::collections::HashMap;
use std::env;
use std::hint::black_box;
use std::rc::Rc;

// ---------------------------------------------------------------- fib

#[inline(never)]
fn fib(n: i64) -> i64 {
    if n < 2 {
        return n;
    }
    // The black box keeps the two recursive calls: no tail-call turning of
    // the second call and no closed form.
    let a = black_box(fib(n - 1));
    let b = fib(n - 2);
    a + b
}

// ---------------------------------------------------------------- loop

fn bench_loop() {
    // loop.lxl's constant bound, so LLVM can prove the two overflow checks
    // cannot fail, as Lexell's native `-O` does. The checks stay on in the build;
    // only the proof is shared.
    let n: i64 = 2_000_000_000;
    let mut s: i64 = 0;
    let mut i: i64 = 0;
    while i < n {
        s = s + i * 2;
        i = i + 1;
    }
    println!("{}", s);
}

// ---------------------------------------------------------------- array

fn bench_array() {
    let n: i64 = 1_000_000;
    let mut a: Vec<i64> = Vec::new();
    let mut i: i64 = 0;
    while i < n {
        a.push(i);
        i += 1;
    }
    let mut total: i64 = 0;
    for r in 0..800i64 {
        for i in 0..n as usize {
            a[i] = a[i] + r;
            total = total + a[i];
        }
    }
    println!("{}", total);
}

// ---------------------------------------------------------------- alloc

struct Cell {
    v: i64,
    w: i64,
}

fn bench_alloc() {
    let n: i64 = 80_000_000;
    let mut total: i64 = 0;
    let mut i: i64 = 0;
    while i < n {
        // black_box keeps the allocation from being folded away.
        let c = black_box(Box::new(Cell { v: i, w: 2 }));
        total = total + c.v + c.w;
        i += 1;
    }
    println!("{}", total);
}

// ---------------------------------------------------------------- lists

struct Node {
    value: i64,
    next: Option<Box<Node>>,
}

fn push(list: Option<Box<Node>>, v: i64) -> Option<Box<Node>> {
    Some(Box::new(Node {
        value: v,
        next: list,
    }))
}

fn sum_list(list: &Option<Box<Node>>) -> i64 {
    match list {
        Some(n) => n.value + sum_list(&n.next),
        None => 0,
    }
}

fn bench_lists() {
    let mut keep: Option<Box<Node>> = None;
    for i in 0..1000 {
        keep = push(keep, i);
    }
    let mut total: i64 = 0;
    for _round in 0..2000 {
        let mut l: Option<Box<Node>> = None;
        for i in 0..10000 {
            l = push(l, i);
        }
        total += sum_list(&l) % 7;
    }
    println!("{}", total + sum_list(&keep));
}

// ---------------------------------------------------------------- strings

// The lxl source and the C reference allocate a fresh block at every `+`
// (`"word" + i`, then `+ "-"`, then `+ round`). concat does the same.
fn concat(a: &str, b: &str) -> String {
    let mut s = String::with_capacity(a.len() + b.len());
    s.push_str(a);
    s.push_str(b);
    s
}

fn concat_rc(a: &str, b: &str) -> Rc<str> {
    let mut s = String::with_capacity(a.len() + b.len());
    s.push_str(a);
    s.push_str(b);
    Rc::from(s)
}

fn bench_strings() {
    let mut keep: Vec<String> = Vec::new();
    for i in 0..1000 {
        keep.push(concat("k", &i.to_string()));
    }
    let mut total: i64 = 0;
    for round in 0..1000 {
        let mut words: Vec<String> = Vec::new();
        for i in 0..5000 {
            let w = concat("word", &i.to_string());
            let w2 = concat(&w, "-");
            words.push(concat(&w2, &round.to_string()));
        }
        for w in &words {
            total += w.len() as i64;
        }
    }
    println!("{}", total);
}

// The same work with lxl-like refcounted strings (Lexell's `str` is refcounted;
// a `+` makes a new block and the old one is dropped when its last reference
// goes).
fn bench_strings_rc() {
    let mut keep: Vec<Rc<str>> = Vec::new();
    for i in 0..1000 {
        keep.push(concat_rc("k", &i.to_string()));
    }
    let mut total: i64 = 0;
    for round in 0..1000 {
        let mut words: Vec<Rc<str>> = Vec::new();
        for i in 0..5000 {
            let w = concat_rc("word", &i.to_string());
            let w2 = concat_rc(&w, "-");
            words.push(concat_rc(&w2, &round.to_string()));
        }
        for w in &words {
            total += w.len() as i64;
        }
    }
    println!("{}", total);
}

// ---------------------------------------------------------------- trees

struct Tree {
    left: Option<Box<Tree>>,
    right: Option<Box<Tree>>,
}

fn build(d: i32) -> Box<Tree> {
    if d == 0 {
        Box::new(Tree {
            left: None,
            right: None,
        })
    } else {
        Box::new(Tree {
            left: Some(build(d - 1)),
            right: Some(build(d - 1)),
        })
    }
}

fn check(t: &Tree) -> i64 {
    let mut n: i64 = 1;
    if let Some(l) = &t.left {
        n += check(l);
    }
    if let Some(r) = &t.right {
        n += check(r);
    }
    n
}

fn bench_trees() {
    let long = build(16);
    let mut total: i64 = 0;
    for _ in 0..400 {
        let t = build(14);
        total += check(&t);
    }
    println!("{}", total + check(&long));
}

// ---------------------------------------------------------------- tokens

struct Token<'a> {
    kind: i32,
    text: &'a str,
    #[allow(dead_code)] // recorded as in the lxl and C references, not counted
    line: i64,
}

fn is_letter(c: u8) -> bool {
    c.is_ascii_alphabetic() || c == b'_'
}

fn is_digit(c: u8) -> bool {
    c.is_ascii_digit()
}

// Identifiers are views of `src`. Slicing is always on a char boundary: an
// identifier starts and ends next to an ASCII byte.
fn scan<'a>(src: &'a str) -> Vec<Token<'a>> {
    let bytes = src.as_bytes();
    let mut toks: Vec<Token<'a>> = Vec::new();
    let mut i = 0usize;
    let mut line: i64 = 1;
    while i < bytes.len() {
        let c = bytes[i];
        if c == b'\n' {
            line += 1;
            i += 1;
        } else if is_letter(c) {
            let start = i;
            while i < bytes.len() && (is_letter(bytes[i]) || is_digit(bytes[i])) {
                i += 1;
            }
            toks.push(Token {
                kind: 1,
                text: &src[start..i],
                line,
            });
        } else if is_digit(c) {
            while i < bytes.len() && is_digit(bytes[i]) {
                i += 1;
            }
            toks.push(Token {
                kind: 2,
                text: "",
                line,
            });
        } else if c == b' ' || c == b'\t' {
            i += 1;
        } else {
            toks.push(Token {
                kind: 3,
                text: "",
                line,
            });
            i += 1;
        }
    }
    toks
}

fn hash(s: &str) -> usize {
    let mut h: u32 = 5381;
    for &b in s.as_bytes() {
        h = (h * 33 + b as u32) & 0xFF_FFFF;
    }
    h as usize
}

// The table holds views of the source, not copies: a name is added only if no
// equal view is in its bucket.
fn intern<'a>(table: &mut [Vec<&'a str>], s: &'a str) -> bool {
    let k = hash(s) % table.len();
    for name in &table[k] {
        if *name == s {
            return false;
        }
    }
    table[k].push(s);
    true
}

fn bench_tokens(path: &str) {
    let bytes = std::fs::read(path).unwrap_or_else(|e| {
        eprintln!("tokens: cannot read {path}: {e}");
        std::process::exit(1);
    });
    let src = std::str::from_utf8(&bytes).unwrap_or_else(|e| {
        eprintln!("tokens: {path} is not UTF-8: {e}");
        std::process::exit(1);
    });
    let mut tokens: i64 = 0;
    let mut unique: i64 = 0;
    for _round in 0..200 {
        let toks = scan(src);
        let mut table: Vec<Vec<&str>> = vec![Vec::new(); 1024];
        for t in &toks {
            if t.kind == 1 && intern(&mut table, t.text) {
                unique += 1;
            }
        }
        tokens += toks.len() as i64;
    }
    println!("{} {}", tokens, unique);
}

// ---------------------------------------------------------------- sieve

fn bench_sieve() {
    let n: usize = 10_000_000;
    let mut count: i64 = 0;
    for _round in 0..30 {
        let mut prime: Vec<u8> = vec![1; n + 1];
        prime[0] = 0;
        prime[1] = 0;
        let mut i = 2usize;
        while i * i <= n {
            if prime[i] != 0 {
                let mut j = i * i;
                while j <= n {
                    prime[j] = 0;
                    j += i;
                }
            }
            i += 1;
        }
        count = 0;
        for k in 0..=n {
            if prime[k] != 0 {
                count += 1;
            }
        }
    }
    println!("{}", count);
}

// ---------------------------------------------------------------- maps
// Port of lexell/bench/maps.lxl (no C reference): std HashMap with its
// default SipHash, keys built the same way, same checksum line.

const MAP_N: usize = 400_000;
const PAD: &str = "a fairly long common prefix for every key of the table: ";

fn str_round(keys: &[String], miss: &[String]) -> i64 {
    let mut m: HashMap<String, i64> = HashMap::new();
    for (i, k) in keys.iter().enumerate() {
        m.insert(k.clone(), i as i64);
    }
    let mut sum: i64 = 0;
    for _r in 0..4 {
        for k in keys {
            sum += m.get(k.as_str()).copied().unwrap_or(-1);
        }
    }
    for k in miss {
        if m.contains_key(k.as_str()) {
            sum += 1;
        }
    }
    sum + m.len() as i64
}

fn int_round(n: usize) -> i64 {
    let mut m: HashMap<i64, i64> = HashMap::new();
    for i in 0..n {
        m.insert(i as i64 * 4096, i as i64);
    }
    let mut sum: i64 = 0;
    for _r in 0..4 {
        for i in 0..n {
            sum += m.get(&(i as i64 * 4096)).copied().unwrap_or(-1);
        }
    }
    for i in 0..n {
        if m.contains_key(&(i as i64 * 4096 + 1)) {
            sum += 1;
        }
    }
    sum + m.len() as i64
}

fn bench_maps() {
    let n = MAP_N;
    let mut short: Vec<String> = Vec::with_capacity(n);
    let mut long: Vec<String> = Vec::with_capacity(n);
    let mut short_miss: Vec<String> = Vec::with_capacity(n);
    let mut long_miss: Vec<String> = Vec::with_capacity(n);
    for i in 0..n {
        short.push(format!("k{}", i as i64 * 7919));
        long.push(format!("{PAD}{i}"));
        short_miss.push(format!("m{i}"));
        long_miss.push(format!("{PAD}x{i}"));
    }
    let s = str_round(&short, &short_miss);
    let l = str_round(&long, &long_miss);
    println!("{} {} {}", s, l, int_round(n));
}

// ---------------------------------------------------------------- main

// ---------------------------------------------------------------- nbody

#[derive(Clone, Copy)]
struct Body { x: f64, y: f64, z: f64, vx: f64, vy: f64, vz: f64, mass: f64 }

const SOLAR: f64 = 39.47841760435743;
const DPY: f64 = 365.24;

fn nbody_bodies() -> Vec<Body> {
    let mut bs = vec![
        Body { x: 0.0, y: 0.0, z: 0.0, vx: 0.0, vy: 0.0, vz: 0.0, mass: SOLAR },
        Body { x: 4.84143144246472090e+00, y: -1.16032004402742839e+00, z: -1.03622044471123109e-01,
            vx: 1.66007664274403694e-03 * DPY, vy: 7.69901118419740425e-03 * DPY, vz: -6.90460016972063023e-05 * DPY,
            mass: 9.54791938424326609e-04 * SOLAR },
        Body { x: 8.34336671824457987e+00, y: 4.12479856412430479e+00, z: -4.03523417114321381e-01,
            vx: -2.76742510726862411e-03 * DPY, vy: 4.99852801234917238e-03 * DPY, vz: 2.30417297573763929e-05 * DPY,
            mass: 2.85885980666130812e-04 * SOLAR },
        Body { x: 1.28943695621391310e+01, y: -1.51111514016986312e+01, z: -2.23307578892655734e-01,
            vx: 2.96460137564761618e-03 * DPY, vy: 2.37847173959480950e-03 * DPY, vz: -2.96589568540237556e-05 * DPY,
            mass: 4.36624404335156298e-05 * SOLAR },
        Body { x: 1.53796971148509165e+01, y: -2.59193146099879641e+01, z: 1.79258772950371181e-01,
            vx: 2.68067772490389322e-03 * DPY, vy: 1.62824170038242295e-03 * DPY, vz: -9.51592254519715870e-05 * DPY,
            mass: 5.15138902046611451e-05 * SOLAR },
    ];
    let (mut px, mut py, mut pz) = (0.0, 0.0, 0.0);
    for b in &bs {
        px += b.vx * b.mass;
        py += b.vy * b.mass;
        pz += b.vz * b.mass;
    }
    bs[0].vx = -px / SOLAR;
    bs[0].vy = -py / SOLAR;
    bs[0].vz = -pz / SOLAR;
    bs
}

fn nbody_advance(bs: &mut [Body], dt: f64) {
    let n = bs.len();
    for i in 0..n {
        for j in i + 1..n {
            let dx = bs[i].x - bs[j].x;
            let dy = bs[i].y - bs[j].y;
            let dz = bs[i].z - bs[j].z;
            let d2 = dx * dx + dy * dy + dz * dz;
            let mag = dt / (d2 * d2.sqrt());
            let mj = bs[j].mass * mag;
            bs[i].vx -= dx * mj;
            bs[i].vy -= dy * mj;
            bs[i].vz -= dz * mj;
            let mi = bs[i].mass * mag;
            bs[j].vx += dx * mi;
            bs[j].vy += dy * mi;
            bs[j].vz += dz * mi;
        }
    }
    for b in bs.iter_mut() {
        b.x += dt * b.vx;
        b.y += dt * b.vy;
        b.z += dt * b.vz;
    }
}

fn nbody_energy(bs: &[Body]) -> f64 {
    let mut e = 0.0;
    let n = bs.len();
    for i in 0..n {
        let b = bs[i];
        e += 0.5 * b.mass * (b.vx * b.vx + b.vy * b.vy + b.vz * b.vz);
        for j in i + 1..n {
            let dx = b.x - bs[j].x;
            let dy = b.y - bs[j].y;
            let dz = b.z - bs[j].z;
            e -= b.mass * bs[j].mass / (dx * dx + dy * dy + dz * dz).sqrt();
        }
    }
    e
}

fn bench_nbody() {
    let mut bs = nbody_bodies();
    let before = (nbody_energy(&bs) * 1e9) as i64;
    let steps = black_box(5_000_000);
    for _ in 0..steps { nbody_advance(&mut bs, 0.01); }
    println!("{} {}", before, (nbody_energy(&bs) * 1e9) as i64);
}

// ---------------------------------------------------------------- interp

#[derive(Clone, Copy)]
enum Op { Push(i64), Load(usize), Store(usize), Add, Mul, Mod, Lt, Jz(usize), Jmp(usize), Halt }

fn interp_run(code: &[Op], n: i64) -> i64 {
    let mut stack = [0i64; 16];
    let mut sp = 0usize;
    let mut locals = [0i64, 0, n];
    let mut pc = 0usize;
    loop {
        match code[pc] {
            Op::Push(v) => { stack[sp] = v; sp += 1; pc += 1; }
            Op::Load(k) => { stack[sp] = locals[k]; sp += 1; pc += 1; }
            Op::Store(k) => { sp -= 1; locals[k] = stack[sp]; pc += 1; }
            Op::Add => { sp -= 1; stack[sp - 1] = stack[sp - 1] + stack[sp]; pc += 1; }
            Op::Mul => { sp -= 1; stack[sp - 1] = stack[sp - 1] * stack[sp]; pc += 1; }
            Op::Mod => { sp -= 1; stack[sp - 1] = stack[sp - 1] % stack[sp]; pc += 1; }
            Op::Lt => { sp -= 1; stack[sp - 1] = if stack[sp - 1] < stack[sp] { 1 } else { 0 }; pc += 1; }
            Op::Jz(t) => { sp -= 1; pc = if stack[sp] == 0 { t } else { pc + 1 }; }
            Op::Jmp(t) => { pc = t; }
            Op::Halt => return locals[1],
        }
    }
}

fn bench_interp() {
    use Op::*;
    let code = vec![
        Load(0), Load(2), Lt, Jz(17),
        Load(1), Load(0), Load(0), Mul, Push(7), Mod,
        Add, Store(1),
        Load(0), Push(1), Add, Store(0),
        Jmp(0),
        Halt,
    ];
    println!("{}", interp_run(black_box(&code), black_box(10_000_000)));
}

// ---------------------------------------------------------------- closures

#[derive(Clone)]
struct Rec { key: i64, name: String }

fn closures_digest(rs: &[Rec]) -> i64 {
    let mut h = 0i64;
    for r in rs { h = (h * 31 + r.key) % 1_000_000_007; }
    h
}

fn inc(v: i64) -> i64 { v + 1 }
fn triple(v: i64) -> i64 { v * 3 }
fn low(v: i64) -> i64 { v % 1000 }
fn seventh(v: i64) -> i64 { v / 7 }

fn bench_closures() {
    let n = black_box(200_000usize);
    let mut rs: Vec<Rec> = Vec::new();
    let mut x: i64 = 12345;
    for _ in 0..n {
        x = (x * 1103515245 + 12345) % 2147483648;
        rs.push(Rec { key: x % 1_000_000, name: format!("n{}", x / 1000 % 50000) });
    }
    rs.sort_by(|a, b| a.key.cmp(&b.key));
    let h1 = closures_digest(&rs);
    rs.sort_by(|a, b| a.name.cmp(&b.name).then(a.key.cmp(&b.key)));
    let h2 = closures_digest(&rs);
    let dir = black_box(-1i64);
    rs.sort_by(|a, b| {
        let c = a.key.cmp(&b.key) as i64 * dir;
        c.cmp(&0)
    });
    let h3 = closures_digest(&rs);
    let fs: [fn(i64) -> i64; 4] = [inc, triple, low, seventh];
    let fs = black_box(fs);
    let mut t = 0i64;
    for round in 0..20 {
        for i in 0..n { t += fs[(i + round) % 4](rs[i].key); }
    }
    println!("{} {} {} {}", h1, h2, h3, t);
}

// ---------------------------------------------------------------- matmul

fn matmul_matrix(n: usize, seed: usize) -> Vec<Vec<f64>> {
    (0..n).map(|i| (0..n).map(|j| ((i * seed + j * 7) % 11) as f64 - 5.0).collect()).collect()
}

fn matmul_mul(a: &[Vec<f64>], b: &[Vec<f64>], n: usize) -> Vec<Vec<f64>> {
    let mut c = Vec::with_capacity(n);
    for i in 0..n {
        let mut row = vec![0.0f64; n];
        for k in 0..n {
            let aik = a[i][k];
            let bk = &b[k];
            for j in 0..n { row[j] += aik * bk[j]; }
        }
        c.push(row);
    }
    c
}

fn bench_matmul() {
    let n = black_box(400usize);
    let a = matmul_matrix(n, 3);
    let b = matmul_matrix(n, 5);
    let mut total = 0i64;
    for r in 0..5 {
        let c = matmul_mul(&a, &b, n);
        let mut s = 0.0f64;
        for i in 0..n {
            for j in 0..n { s += c[i][j] * (((i * n + j) % 13 + r) as f64); }
        }
        total += s as i64;
    }
    println!("{}", total);
}

fn main() {
    let mut args = env::args().skip(1);
    let bench = args.next().unwrap_or_else(|| {
        eprintln!("usage: dbench <fib|loop|array|alloc|lists|strings|strings-rc|trees|tokens|sieve> [args]");
        std::process::exit(2);
    });
    let rest: Vec<String> = args.collect();
    match bench.as_str() {
        "fib" => {
            let n = rest.first().map(|s| s.parse().unwrap()).unwrap_or(42);
            println!("{}", fib(n));
        }
        "loop" => bench_loop(),
        "array" => bench_array(),
        "alloc" => bench_alloc(),
        "lists" => bench_lists(),
        "strings" => bench_strings(),
        "strings-rc" => bench_strings_rc(),
        "trees" => bench_trees(),
        "tokens" => {
            let path = rest.first().unwrap_or_else(|| {
                eprintln!("tokens: missing input file");
                std::process::exit(2);
            });
            bench_tokens(path);
        }
        "sieve" => bench_sieve(),
        "maps" => bench_maps(),
        "nbody" => bench_nbody(),
        "interp" => bench_interp(),
        "closures" => bench_closures(),
        "matmul" => bench_matmul(),
        other => {
            eprintln!("dbench: unknown benchmark {other}");
            std::process::exit(2);
        }
    }
}
