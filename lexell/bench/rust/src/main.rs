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

// ---------------------------------------------------------------- bitpack

fn pack_col(vals: &[i64], bits: usize) -> Vec<u8> {
    let n = vals.len();
    let total_bits = n * bits;
    let mut out = vec![0u8; (total_bits + 7) / 8 + 8];
    let mut bit_pos = 0usize;
    for &v in vals {
        let mut b = 0usize;
        while b < bits {
            let byte_idx = (bit_pos + b) >> 3;
            let bit_off = (bit_pos + b) & 7;
            let take = 8 - bit_off;
            let rem = bits - b;
            let k = if take < rem { take } else { rem };
            let mask = (1i64 << k) - 1;
            let chunk = (v >> b) & mask;
            out[byte_idx] = (out[byte_idx] as i64 | (chunk << bit_off)) as u8;
            b += k;
        }
        bit_pos += bits;
    }
    out
}

fn unpack_batch(buf: &[u8], start_idx: usize, count: usize, bits: usize, base_val: i64, dst: &mut [i64]) {
    let mask = (1i64 << bits) - 1;
    let mut bit_pos = start_idx * bits;
    for i in 0..count {
        let byte_idx = bit_pos >> 3;
        let bit_off = bit_pos & 7;
        let w = (buf[byte_idx] as i64)
            | ((buf[byte_idx + 1] as i64) << 8)
            | ((buf[byte_idx + 2] as i64) << 16)
            | ((buf[byte_idx + 3] as i64) << 24);
        dst[i] = base_val + ((w >> bit_off) & mask);
        bit_pos += bits;
    }
}

fn bench_bitpack() {
    let n = black_box(1_000_000usize);
    let batch = 1024usize;
    let mut raw_qty = vec![0i64; n];
    let mut raw_disc = vec![0i64; n];
    let mut raw_price = vec![0i64; n];
    let mut s = 123_456_789i64;
    for i in 0..n {
        s = (s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407)) & 4611686018427387903;
        raw_qty[i] = (s >> 16) & 63;
        raw_disc[i] = (s >> 24) & 15;
        raw_price[i] = (s >> 30) & 131071;
    }
    let p_qty = pack_col(&raw_qty, 6);
    let p_disc = pack_col(&raw_disc, 4);
    let p_price = pack_col(&raw_price, 17);

    let mut qty = vec![0i64; batch];
    let mut disc = vec![0i64; batch];
    let mut price = vec![0i64; batch];
    let mut sel = vec![0usize; batch];

    let mut total = 0i64;
    for round in 0..60i64 {
        let lo_disc = 4 + (round & 3);
        let hi_disc = lo_disc + 4;
        let max_qty = 30 + (round & 7);
        let mut pos = 0usize;
        while pos < n {
            let cnt = if n - pos < batch { n - pos } else { batch };
            unpack_batch(&p_qty, pos, cnt, 6, 1, &mut qty);
            unpack_batch(&p_disc, pos, cnt, 4, 0, &mut disc);
            unpack_batch(&p_price, pos, cnt, 17, 90000, &mut price);
            let mut nsel = 0usize;
            for i in 0..cnt {
                let d = disc[i];
                if d >= lo_disc && d <= hi_disc && qty[i] < max_qty {
                    sel[nsel] = i;
                    nsel += 1;
                }
            }
            let mut acc = 0i64;
            for j in 0..nsel {
                let idx = sel[j];
                acc += price[idx] * disc[idx];
            }
            total += acc;
            pos += cnt;
        }
    }
    println!("{}", total);
}

// ---------------------------------------------------------------- btree

const BT_MAX_KEYS: usize = 31;
const BT_MID: usize = 15;

struct BtNode {
    leaf: bool,
    keys: Vec<i64>,
    vals: Vec<i64>,
    kids: Vec<Box<BtNode>>,
}

struct BtSplit {
    promoted: bool,
    key: i64,
    right: Option<Box<BtNode>>,
}

fn bt_new_leaf() -> Box<BtNode> {
    Box::new(BtNode {
        leaf: true,
        keys: Vec::new(),
        vals: Vec::new(),
        kids: Vec::new(),
    })
}

fn bt_lower_bound(keys: &[i64], key: i64) -> usize {
    let mut lo = 0usize;
    let mut hi = keys.len();
    while lo < hi {
        let mid = (lo + hi) >> 1;
        if keys[mid] < key {
            lo = mid + 1;
        } else {
            hi = mid;
        }
    }
    lo
}

fn bt_search(mut cur: &BtNode, key: i64) -> i64 {
    loop {
        let i = bt_lower_bound(&cur.keys, key);
        if cur.leaf {
            if i < cur.keys.len() && cur.keys[i] == key {
                return cur.vals[i];
            }
            return -1;
        }
        if i < cur.keys.len() && cur.keys[i] == key {
            cur = &cur.kids[i + 1];
        } else {
            cur = &cur.kids[i];
        }
    }
}

fn bt_range_sum(node: &BtNode, lo: i64, hi: i64) -> i64 {
    let i = bt_lower_bound(&node.keys, lo);
    let mut sum = 0i64;
    if node.leaf {
        let mut j = i;
        while j < node.keys.len() && node.keys[j] <= hi {
            sum += node.vals[j];
            j += 1;
        }
        return sum;
    }
    let mut j = i;
    while j < node.keys.len() {
        sum += bt_range_sum(&node.kids[j], lo, hi);
        if node.keys[j] > hi {
            return sum;
        }
        j += 1;
    }
    sum += bt_range_sum(&node.kids[node.keys.len()], lo, hi);
    sum
}

fn bt_insert_rec(node: &mut BtNode, key: i64, val: i64) -> BtSplit {
    let pos = bt_lower_bound(&node.keys, key);
    if node.leaf {
        if pos < node.keys.len() && node.keys[pos] == key {
            node.vals[pos] = val;
            return BtSplit { promoted: false, key: 0, right: None };
        }
        node.keys.insert(pos, key);
        node.vals.insert(pos, val);
        if node.keys.len() <= BT_MAX_KEYS {
            return BtSplit { promoted: false, key: 0, right: None };
        }
        let rkeys = node.keys.split_off(BT_MID);
        let rvals = node.vals.split_off(BT_MID);
        let pkey = rkeys[0];
        return BtSplit {
            promoted: true,
            key: pkey,
            right: Some(Box::new(BtNode { leaf: true, keys: rkeys, vals: rvals, kids: Vec::new() })),
        };
    }
    let ci = if pos < node.keys.len() && node.keys[pos] == key { pos + 1 } else { pos };
    let sp = bt_insert_rec(&mut node.kids[ci], key, val);
    if !sp.promoted {
        return sp;
    }
    let right_node = sp.right.unwrap();
    node.keys.insert(ci, sp.key);
    node.kids.insert(ci + 1, right_node);
    if node.keys.len() <= BT_MAX_KEYS {
        return BtSplit { promoted: false, key: 0, right: None };
    }
    let pkey = node.keys[BT_MID];
    let rkeys = node.keys.split_off(BT_MID + 1);
    node.keys.pop();
    let rkids = node.kids.split_off(BT_MID + 1);
    BtSplit {
        promoted: true,
        key: pkey,
        right: Some(Box::new(BtNode { leaf: false, keys: rkeys, vals: Vec::new(), kids: rkids })),
    }
}

fn bt_insert_root(root: &mut Box<BtNode>, key: i64, val: i64) {
    let sp = bt_insert_rec(root, key, val);
    if sp.promoted {
        let right_node = sp.right.unwrap();
        let old_root = std::mem::replace(root, bt_new_leaf());
        *root = Box::new(BtNode {
            leaf: false,
            keys: vec![sp.key],
            vals: Vec::new(),
            kids: vec![old_root, right_node],
        });
    }
}

fn bench_btree() {
    let n = black_box(100_000i64);
    let mut root = bt_new_leaf();
    let mut s = 987_654_321i64;
    for i in 0..n {
        s = (s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407)) & 4611686018427387903;
        let k = (s >> 12) & 1048575;
        bt_insert_root(&mut root, k, i + 1);
    }

    let mut total = 0i64;
    s = 987_654_321i64;
    for _round in 0..10 {
        for _i in 0..n {
            s = (s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407)) & 4611686018427387903;
            let k = (s >> 12) & 1048575;
            let v = bt_search(&root, k);
            if v >= 0 {
                total += v;
            }
        }
    }
    for i in 0..30_000i64 {
        let lo = (i * 31) & 1048575;
        total += bt_range_sum(&root, lo, lo + 200);
    }
    println!("{}", total);
}

// ---------------------------------------------------------------- hashagg

#[inline]
fn hashagg_hash2(k1: i64, k2: i64) -> i64 {
    let mut h = k1.wrapping_mul(2654435761) ^ k2.wrapping_mul(2246822519);
    h = (h ^ (h >> 16)).wrapping_mul(2246822519);
    h = h ^ (h >> 13);
    h & 4611686018427387903
}

fn bench_hashagg() {
    let n = black_box(1_000_000usize);
    let mut col_k1 = vec![0i64; n];
    let mut col_k2 = vec![0i64; n];
    let mut col_val = vec![0i64; n];
    let mut s = 42_424_242i64;
    for i in 0..n {
        s = (s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407)) & 4611686018427387903;
        col_k1[i] = (s >> 16) & 255;
        col_k2[i] = (s >> 24) & 63;
        col_val[i] = ((s >> 32) & 65535) - 32768;
    }

    let cap = 32768usize;
    let mask = cap - 1;
    let mut slots = vec![-1i64; cap];
    let mut g_k1 = vec![0i64; cap];
    let mut g_k2 = vec![0i64; cap];
    let mut g_cnt = vec![0i64; cap];
    let mut g_sum = vec![0i64; cap];
    let mut g_min = vec![0i64; cap];
    let mut g_max = vec![0i64; cap];

    let mut checksum = 0i64;
    for round in 0..10i64 {
        slots.fill(-1);
        let mut ng = 0usize;
        for i in 0..n {
            let k1 = col_k1[i];
            let k2 = col_k2[i];
            let v = col_val[i] + round;
            let mut h = (hashagg_hash2(k1, k2) as usize) & mask;
            loop {
                let g = slots[h];
                if g < 0 {
                    slots[h] = ng as i64;
                    g_k1[ng] = k1;
                    g_k2[ng] = k2;
                    g_cnt[ng] = 1;
                    g_sum[ng] = v;
                    g_min[ng] = v;
                    g_max[ng] = v;
                    ng += 1;
                    break;
                }
                let gu = g as usize;
                if g_k1[gu] == k1 && g_k2[gu] == k2 {
                    g_cnt[gu] += 1;
                    g_sum[gu] += v;
                    if v < g_min[gu] { g_min[gu] = v; }
                    if v > g_max[gu] { g_max[gu] = v; }
                    break;
                }
                h = (h + 1) & mask;
            }
        }
        for g in 0..ng {
            checksum += g_cnt[g] + g_sum[g] + g_min[g] + g_max[g];
        }
    }
    println!("{}", checksum);
}

// ---------------------------------------------------------------- varint_csv

fn put_varint(out: &mut Vec<u8>, mut v: i64) {
    while v >= 128 {
        out.push(((v & 127) | 128) as u8);
        v >>= 7;
    }
    out.push(v as u8);
}

fn parse_csv_int(buf: &[u8], start: usize, end: usize) -> i64 {
    let mut i = start;
    let mut neg = false;
    if i < end && buf[i] == b'-' {
        neg = true;
        i += 1;
    }
    let mut acc = 0i64;
    while i < end {
        acc = acc * 10 + (buf[i] - b'0') as i64;
        i += 1;
    }
    if neg { -acc } else { acc }
}

fn append_csv_int(out: &mut Vec<u8>, mut v: i64) {
    if v < 0 {
        out.push(b'-');
        v = -v;
    }
    if v == 0 {
        out.push(b'0');
        return;
    }
    let mut tmp = Vec::new();
    while v > 0 {
        tmp.push(b'0' + (v % 10) as u8);
        v /= 10;
    }
    while let Some(b) = tmp.pop() {
        out.push(b);
    }
}

fn build_csv(rows: usize) -> Vec<u8> {
    let mut buf = Vec::new();
    let codes = b"ABCDEFGHIJKLMNOP";
    let mut s = 7_777_777i64;
    for i in 0..rows {
        s = (s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407)) & 4611686018427387903;
        append_csv_int(&mut buf, (i + 1) as i64);
        buf.push(b'|');
        append_csv_int(&mut buf, ((s >> 16) & 63) + 1);
        buf.push(b'|');
        append_csv_int(&mut buf, ((s >> 24) & 65535) + 1000);
        buf.push(b'|');
        let c1 = ((s >> 40) & 15) as usize;
        let c2 = ((s >> 44) & 15) as usize;
        buf.push(codes[c1]);
        buf.push(codes[c2]);
        buf.push(codes[(c1 + c2) & 15]);
        buf.push(b'\n');
    }
    buf
}

fn bench_varint_csv() {
    let csv = black_box(build_csv(120_000));
    let n = csv.len();
    let mut total = 0i64;
    for round in 0..25i64 {
        let mut out = Vec::new();
        let mut pos = 0usize;
        let mut row_hash = 0i64;
        while pos < n {
            let f0 = pos;
            while csv[pos] != b'|' { pos += 1; }
            let id = parse_csv_int(&csv, f0, pos);
            pos += 1;

            let f1 = pos;
            while csv[pos] != b'|' { pos += 1; }
            let qty = parse_csv_int(&csv, f1, pos);
            pos += 1;

            let f2 = pos;
            while csv[pos] != b'|' { pos += 1; }
            let price = parse_csv_int(&csv, f2, pos);
            pos += 1;

            let mut code_h = 0i64;
            while csv[pos] != b'\n' {
                code_h = code_h * 31 + csv[pos] as i64;
                pos += 1;
            }
            pos += 1;

            put_varint(&mut out, id);
            put_varint(&mut out, qty);
            put_varint(&mut out, price);
            row_hash += code_h;
        }
        let mut sum_b = 0i64;
        for &b in &out { sum_b += b as i64; }
        total += out.len() as i64 + sum_b + row_hash + round;
    }
    println!("{}", total);
}

// ---------------------------------------------------------------- enum_eval

enum Expr {
    Col(usize),
    Lit(i64),
    Add(Box<Expr>, Box<Expr>),
    Sub(Box<Expr>, Box<Expr>),
    Mul(Box<Expr>, Box<Expr>),
    Lt(Box<Expr>, Box<Expr>),
    And(Box<Expr>, Box<Expr>),
    If(Box<Expr>, Box<Expr>, Box<Expr>),
}

fn eval_row(e: &Expr, c0: &[i64], c1: &[i64], c2: &[i64], c3: &[i64], row: usize) -> i64 {
    match e {
        Expr::Col(k) => match *k {
            0 => c0[row],
            1 => c1[row],
            2 => c2[row],
            _ => c3[row],
        },
        Expr::Lit(v) => *v,
        Expr::Add(a, b) => eval_row(a, c0, c1, c2, c3, row) + eval_row(b, c0, c1, c2, c3, row),
        Expr::Sub(a, b) => eval_row(a, c0, c1, c2, c3, row) - eval_row(b, c0, c1, c2, c3, row),
        Expr::Mul(a, b) => eval_row(a, c0, c1, c2, c3, row) * eval_row(b, c0, c1, c2, c3, row),
        Expr::Lt(a, b) => if eval_row(a, c0, c1, c2, c3, row) < eval_row(b, c0, c1, c2, c3, row) { 1 } else { 0 },
        Expr::And(a, b) => {
            if eval_row(a, c0, c1, c2, c3, row) == 0 { return 0; }
            if eval_row(b, c0, c1, c2, c3, row) != 0 { 1 } else { 0 }
        }
        Expr::If(cond, t, f) => {
            if eval_row(cond, c0, c1, c2, c3, row) != 0 {
                eval_row(t, c0, c1, c2, c3, row)
            } else {
                eval_row(f, c0, c1, c2, c3, row)
            }
        }
    }
}

fn bench_enum_eval() {
    let expr = black_box(Expr::If(
        Box::new(Expr::And(
            Box::new(Expr::Lt(Box::new(Expr::Col(0)), Box::new(Expr::Lit(25)))),
            Box::new(Expr::Lt(Box::new(Expr::Col(1)), Box::new(Expr::Lit(8)))),
        )),
        Box::new(Expr::Mul(
            Box::new(Expr::Col(2)),
            Box::new(Expr::Sub(Box::new(Expr::Lit(100)), Box::new(Expr::Col(1)))),
        )),
        Box::new(Expr::Add(
            Box::new(Expr::Mul(
                Box::new(Expr::Col(2)),
                Box::new(Expr::Sub(Box::new(Expr::Lit(100)), Box::new(Expr::Col(3)))),
            )),
            Box::new(Expr::Col(0)),
        )),
    ));

    let n = black_box(500_000usize);
    let mut c0 = vec![0i64; n];
    let mut c1 = vec![0i64; n];
    let mut c2 = vec![0i64; n];
    let mut c3 = vec![0i64; n];
    let mut s = 135_792_468i64;
    for i in 0..n {
        s = (s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407)) & 4611686018427387903;
        c0[i] = (s >> 16) & 63;
        c1[i] = (s >> 22) & 15;
        c2[i] = ((s >> 26) & 4095) + 100;
        c3[i] = (s >> 38) & 15;
    }

    let mut total = 0i64;
    for round in 0..8i64 {
        let mut acc = 0i64;
        for i in 0..n {
            acc += eval_row(&expr, &c0, &c1, &c2, &c3, i);
        }
        total += acc + round;
    }
    println!("{}", total);
}

// ---------------------------------------------------------------- explicit SIMD (std::arch::x86_64 AVX2/FMA)
// Separate explicit-SIMD benchmark suite (`bench/simd_bench.py`), comparing
// Lexell's safe `vector[T]`, Rust's `std::arch::x86_64` AVX2 intrinsics
// (`std::simd` is nightly-only on stable rustc), and Java's `jdk.incubator.vector`.

#[cfg(target_arch = "x86_64")]
fn bench_array_vec() {
    use std::arch::x86_64::*;
    let n: usize = 1_000_000;
    let mut a: Vec<i64> = Vec::new();
    for i in 0..n as i64 {
        a.push(i);
    }
    let mut total: i64 = 0;
    for r in 0..800i64 {
        unsafe {
            let vr = _mm256_set1_epi64x(r);
            let mut acc = _mm256_setzero_si256();
            let mut i = 0usize;
            let ptr = a.as_mut_ptr();
            while i + 4 <= n {
                let v = _mm256_add_epi64(_mm256_loadu_si256(ptr.add(i) as *const __m256i), vr);
                _mm256_storeu_si256(ptr.add(i) as *mut __m256i, v);
                acc = _mm256_add_epi64(acc, v);
                i += 4;
            }
            let mut lanes = [0i64; 4];
            _mm256_storeu_si256(lanes.as_mut_ptr() as *mut __m256i, acc);
            total = total.wrapping_add(lanes[0] + lanes[1] + lanes[2] + lanes[3]);
            while i < n {
                a[i] = a[i].wrapping_add(r);
                total = total.wrapping_add(a[i]);
                i += 1;
            }
        }
    }
    println!("{}", total);
}

#[cfg(target_arch = "x86_64")]
fn bench_sieve_vec() {
    use std::arch::x86_64::*;
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
        unsafe {
            let vzero = _mm256_setzero_si256();
            let ptr = prime.as_ptr();
            let m = n + 1;
            let mut k = 0usize;
            while k + 32 <= m {
                let v = _mm256_loadu_si256(ptr.add(k) as *const __m256i);
                let eq = _mm256_cmpeq_epi8(v, vzero);
                let mask = !(_mm256_movemask_epi8(eq) as u32);
                count += mask.count_ones() as i64;
                k += 32;
            }
            while k < m {
                if prime[k] != 0 {
                    count += 1;
                }
                k += 1;
            }
        }
    }
    println!("{}", count);
}

#[cfg(target_arch = "x86_64")]
fn matmul_axpy_avx2(dst: &mut [f64], src: &[f64], a: f64) {
    use std::arch::x86_64::*;
    let n = dst.len().min(src.len());
    unsafe {
        let va = _mm256_set1_pd(a);
        let dp = dst.as_mut_ptr();
        let sp = src.as_ptr();
        let mut j = 0usize;
        while j + 8 <= n {
            let s0 = _mm256_loadu_pd(sp.add(j));
            let s1 = _mm256_loadu_pd(sp.add(j + 4));
            let d0 = _mm256_loadu_pd(dp.add(j));
            let d1 = _mm256_loadu_pd(dp.add(j + 4));
            _mm256_storeu_pd(dp.add(j), _mm256_fmadd_pd(va, s0, d0));
            _mm256_storeu_pd(dp.add(j + 4), _mm256_fmadd_pd(va, s1, d1));
            j += 8;
        }
        while j + 4 <= n {
            let s0 = _mm256_loadu_pd(sp.add(j));
            let d0 = _mm256_loadu_pd(dp.add(j));
            _mm256_storeu_pd(dp.add(j), _mm256_fmadd_pd(va, s0, d0));
            j += 4;
        }
        while j < n {
            dst[j] = a.mul_add(src[j], dst[j]);
            j += 1;
        }
    }
}

#[cfg(target_arch = "x86_64")]
fn bench_matmul_vec() {
    let n = black_box(400usize);
    let a = matmul_matrix(n, 3);
    let b = matmul_matrix(n, 5);
    let mut total = 0i64;
    for r in 0..5 {
        let mut c = Vec::with_capacity(n);
        for i in 0..n {
            let mut row = vec![0.0f64; n];
            for k in 0..n {
                matmul_axpy_avx2(&mut row, &b[k], a[i][k]);
            }
            c.push(row);
        }
        let mut s = 0.0f64;
        for i in 0..n {
            for j in 0..n {
                s += c[i][j] * (((i * n + j) % 13 + r) as f64);
            }
        }
        total += s as i64;
    }
    println!("{}", total);
}

fn unpack_batch_i32(buf: &[u8], start_idx: usize, count: usize, bits: usize, base_val: i64, dst: &mut [i32]) {
    let mask = (1i64 << bits) - 1;
    let mut bit_pos = start_idx * bits;
    for i in 0..count {
        let byte_idx = bit_pos >> 3;
        let bit_off = bit_pos & 7;
        let w = (buf[byte_idx] as i64)
            | ((buf[byte_idx + 1] as i64) << 8)
            | ((buf[byte_idx + 2] as i64) << 16)
            | ((buf[byte_idx + 3] as i64) << 24);
        dst[i] = (base_val + ((w >> bit_off) & mask)) as i32;
        bit_pos += bits;
    }
}

#[cfg(target_arch = "x86_64")]
fn bench_bitpack_vec() {
    use std::arch::x86_64::*;
    let n = black_box(1_000_000usize);
    let batch = 1024usize;
    let mut raw_qty = vec![0i64; n];
    let mut raw_disc = vec![0i64; n];
    let mut raw_price = vec![0i64; n];
    let mut s = 123_456_789i64;
    for i in 0..n {
        s = (s.wrapping_mul(6364136223846793005).wrapping_add(1442695040888963407)) & 4611686018427387903;
        raw_qty[i] = (s >> 16) & 63;
        raw_disc[i] = (s >> 24) & 15;
        raw_price[i] = (s >> 30) & 131071;
    }
    let p_qty = pack_col(&raw_qty, 6);
    let p_disc = pack_col(&raw_disc, 4);
    let p_price = pack_col(&raw_price, 17);

    let mut qty = vec![0i32; batch];
    let mut disc = vec![0i32; batch];
    let mut price = vec![0i32; batch];

    let mut total = 0i64;
    for round in 0..60i64 {
        let lo_disc = (4 + (round & 3)) as i32;
        let hi_disc = lo_disc + 4;
        let max_qty = (30 + (round & 7)) as i32;
        unsafe {
            let v_lo = _mm256_set1_epi32(lo_disc);
            let v_hi = _mm256_set1_epi32(hi_disc);
            let v_maxq = _mm256_set1_epi32(max_qty);
            let mut pos = 0usize;
            while pos < n {
                let cnt = (n - pos).min(batch);
                unpack_batch_i32(&p_qty, pos, cnt, 6, 1, &mut qty);
                unpack_batch_i32(&p_disc, pos, cnt, 4, 0, &mut disc);
                unpack_batch_i32(&p_price, pos, cnt, 17, 90000, &mut price);
                let mut v_acc = _mm256_setzero_si256();
                let dp = disc.as_ptr();
                let qp = qty.as_ptr();
                let pp = price.as_ptr();
                let mut i = 0usize;
                while i + 8 <= cnt {
                    let vd = _mm256_loadu_si256(dp.add(i) as *const __m256i);
                    let vq = _mm256_loadu_si256(qp.add(i) as *const __m256i);
                    let vp = _mm256_loadu_si256(pp.add(i) as *const __m256i);
                    let lt_lo = _mm256_cmpgt_epi32(v_lo, vd);
                    let gt_hi = _mm256_cmpgt_epi32(vd, v_hi);
                    let lt_q = _mm256_cmpgt_epi32(v_maxq, vq);
                    let m = _mm256_andnot_si256(_mm256_or_si256(lt_lo, gt_hi), lt_q);
                    let prod = _mm256_and_si256(_mm256_mullo_epi32(vp, vd), m);
                    v_acc = _mm256_add_epi32(v_acc, prod);
                    i += 8;
                }
                let mut lanes = [0i32; 8];
                _mm256_storeu_si256(lanes.as_mut_ptr() as *mut __m256i, v_acc);
                for &v in &lanes {
                    total += v as i64;
                }
                while i < cnt {
                    let d = disc[i];
                    if d >= lo_disc && d <= hi_disc && qty[i] < max_qty {
                        total += (price[i].wrapping_mul(d)) as i64;
                    }
                    i += 1;
                }
                pos += cnt;
            }
        }
    }
    println!("{}", total);
}

#[cfg(target_arch = "x86_64")]
fn bench_dot_vec() {
    use std::arch::x86_64::*;
    let n = black_box(65536usize);
    let rounds = 4000usize;
    let mut a = Vec::with_capacity(n);
    let mut b = Vec::with_capacity(n);
    for i in 0..n {
        a.push(i as f64 * 0.5);
        b.push(i as f64 * 0.25 + 1.0);
    }
    let mut total = 0.0f64;
    let ap = a.as_ptr();
    let bp = b.as_ptr();
    for _ in 0..rounds {
        unsafe {
            let mut s0 = _mm256_setzero_pd();
            let mut s1 = _mm256_setzero_pd();
            let mut s2 = _mm256_setzero_pd();
            let mut s3 = _mm256_setzero_pd();
            let mut i = 0usize;
            while i + 16 <= n {
                s0 = _mm256_fmadd_pd(_mm256_loadu_pd(ap.add(i)), _mm256_loadu_pd(bp.add(i)), s0);
                s1 = _mm256_fmadd_pd(_mm256_loadu_pd(ap.add(i + 4)), _mm256_loadu_pd(bp.add(i + 4)), s1);
                s2 = _mm256_fmadd_pd(_mm256_loadu_pd(ap.add(i + 8)), _mm256_loadu_pd(bp.add(i + 8)), s2);
                s3 = _mm256_fmadd_pd(_mm256_loadu_pd(ap.add(i + 12)), _mm256_loadu_pd(bp.add(i + 12)), s3);
                i += 16;
            }
            while i + 4 <= n {
                s0 = _mm256_fmadd_pd(_mm256_loadu_pd(ap.add(i)), _mm256_loadu_pd(bp.add(i)), s0);
                i += 4;
            }
            let sum_v = _mm256_add_pd(_mm256_add_pd(s0, s1), _mm256_add_pd(s2, s3));
            let mut lanes = [0.0f64; 4];
            _mm256_storeu_pd(lanes.as_mut_ptr(), sum_v);
            let mut acc = (lanes[0] + lanes[1]) + (lanes[2] + lanes[3]);
            while i < n {
                acc = a[i].mul_add(b[i], acc);
                i += 1;
            }
            total += acc;
        }
    }
    println!("{:.12e}", total);
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
        "bitpack" => bench_bitpack(),
        "btree" => bench_btree(),
        "hashagg" => bench_hashagg(),
        "varint_csv" => bench_varint_csv(),
        "enum_eval" => bench_enum_eval(),
        #[cfg(target_arch = "x86_64")]
        "array_vec" => bench_array_vec(),
        #[cfg(target_arch = "x86_64")]
        "sieve_vec" => bench_sieve_vec(),
        #[cfg(target_arch = "x86_64")]
        "matmul_vec" => bench_matmul_vec(),
        #[cfg(target_arch = "x86_64")]
        "bitpack_vec" => bench_bitpack_vec(),
        #[cfg(target_arch = "x86_64")]
        "dot_vec" => bench_dot_vec(),
        other => {
            eprintln!("dbench: unknown benchmark {other}");
            std::process::exit(2);
        }
    }
}
