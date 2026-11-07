//! Idiomatic Rust ports of the nine obx benchmarks that have a hand-written
//! C reference in `obx/bench/c/`. Each subcommand does the same work as
//! `obx/bench/NAME.obx` and prints the same checksum, so bench.py can require
//! identical output.
//!
//! No unsafe, no external crates, no threads. `std::hint::black_box` and
//! command-line sizes (where the C reference has them) keep LLVM from
//! constant-folding or closing the work up. Bounds checks stay on, and the
//! release profile leaves overflow checks on (`Cargo.toml`).

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

fn bench_loop(n: i64) {
    let mut s: i64 = 0;
    let mut i: i64 = 0;
    while i < n {
        // Two checked operations per iteration, exactly as in loop.obx.
        s = s + i * 2;
        // Keep s live across the iteration: no closed form, no vector loop.
        s = black_box(s);
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
    for r in 0..200i64 {
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
    let n: i64 = 20_000_000;
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
    for _round in 0..300 {
        let mut l: Option<Box<Node>> = None;
        for i in 0..10000 {
            l = push(l, i);
        }
        total += sum_list(&l) % 7;
    }
    println!("{}", total + sum_list(&keep));
}

// ---------------------------------------------------------------- strings

// The obx source and the C reference allocate a fresh block at every `+`
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
    for round in 0..200 {
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

// The same work with obx-like refcounted strings (obx's `str` is refcounted;
// a `+` makes a new block and the old one is dropped when its last reference
// goes).
fn bench_strings_rc() {
    let mut keep: Vec<Rc<str>> = Vec::new();
    for i in 0..1000 {
        keep.push(concat_rc("k", &i.to_string()));
    }
    let mut total: i64 = 0;
    for round in 0..200 {
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
    for _ in 0..40 {
        let t = build(14);
        total += check(&t);
    }
    println!("{}", total + check(&long));
}

// ---------------------------------------------------------------- tokens

struct Token {
    kind: i32,
    text: String,
    #[allow(dead_code)] // recorded as in the obx and C references, not counted
    line: i64,
}

fn is_letter(c: u8) -> bool {
    c.is_ascii_alphabetic() || c == b'_'
}

fn is_digit(c: u8) -> bool {
    c.is_ascii_digit()
}

fn scan(src: &[u8], toks: &mut Vec<Token>) {
    let mut i = 0usize;
    let mut line: i64 = 1;
    while i < src.len() {
        let c = src[i];
        if c == b'\n' {
            line += 1;
            i += 1;
        } else if is_letter(c) {
            let start = i;
            while i < src.len() && (is_letter(src[i]) || is_digit(src[i])) {
                i += 1;
            }
            let text = String::from_utf8_lossy(&src[start..i]).into_owned();
            toks.push(Token {
                kind: 1,
                text,
                line,
            });
        } else if is_digit(c) {
            while i < src.len() && is_digit(src[i]) {
                i += 1;
            }
            toks.push(Token {
                kind: 2,
                text: String::new(),
                line,
            });
        } else if c == b' ' || c == b'\t' {
            i += 1;
        } else {
            toks.push(Token {
                kind: 3,
                text: String::new(),
                line,
            });
            i += 1;
        }
    }
}

fn hash(s: &str) -> usize {
    let mut h: u32 = 5381;
    for &b in s.as_bytes() {
        h = (h * 33 + b as u32) & 0xFF_FFFF;
    }
    h as usize
}

// The table stores indices into the token stream: that is the same 8-byte
// entry per name as the C reference's char *, without a new allocation per
// interned identifier (obx shares the refcounted text).
fn intern(table: &mut [Vec<usize>], toks: &[Token], idx: usize) -> bool {
    let s = &toks[idx].text;
    let k = hash(s) % table.len();
    for &j in &table[k] {
        if toks[j].text == *s {
            return false;
        }
    }
    table[k].push(idx);
    true
}

fn bench_tokens(path: &str) {
    let src = std::fs::read(path).unwrap_or_else(|e| {
        eprintln!("tokens: cannot read {path}: {e}");
        std::process::exit(1);
    });
    let mut tokens: i64 = 0;
    let mut unique: i64 = 0;
    for _round in 0..10 {
        let mut toks: Vec<Token> = Vec::new();
        scan(&src, &mut toks);
        let mut table: Vec<Vec<usize>> = vec![Vec::new(); 1024];
        for (i, t) in toks.iter().enumerate() {
            if t.kind == 1 && intern(&mut table, &toks, i) {
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
    for _round in 0..10 {
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

// ---------------------------------------------------------------- main

fn main() {
    let mut args = env::args().skip(1);
    let bench = args.next().unwrap_or_else(|| {
        eprintln!("usage: dbench <fib|loop|array|alloc|lists|strings|strings-rc|trees|tokens|sieve> [args]");
        std::process::exit(2);
    });
    let rest: Vec<String> = args.collect();
    match bench.as_str() {
        "fib" => {
            let n = rest.first().map(|s| s.parse().unwrap()).unwrap_or(40);
            println!("{}", fib(n));
        }
        "loop" => {
            let n = rest
                .first()
                .map(|s| s.parse().unwrap())
                .unwrap_or(1_000_000_000);
            bench_loop(n);
        }
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
        other => {
            eprintln!("dbench: unknown benchmark {other}");
            std::process::exit(2);
        }
    }
}
