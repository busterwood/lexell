#!/usr/bin/env python3
"""lib/yaml.lxl against the official YAML 1.2 Test Suite
(github.com/yaml/yaml-test-suite, MIT) and/or a differential round-trip check.

    python3 lexell/tests/yamlsuite.py [--c] [--suite DIR] [-v]

The suite is not in the repository: --suite names a data-branch checkout
(e.g. `git clone -b data-2022-01-17 https://github.com/yaml/yaml-test-suite.git`),
else it is cloned into a temporary directory and removed afterwards.

For every test case:
- Cases with an `error` file must fail `yaml.parseAll` (no crash).
- Cases without an `error` file must parse with `yaml.parseAll` (no crash),
  and if `in.json` exists, `yaml.toJson` of the parsed document(s) is compared
  against `in.json` (plus write -> re-parse round-trip equality!)."""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LEXELL = os.path.dirname(HERE)
LXLC = os.environ.get('LXLC') or os.path.join(LEXELL, 'compiler', 'out', 'lxlc')

CHECK = r'''
import "yaml"
import "json"
import "io"
import "os"

fn main() {
    let args = os.arguments()
    if len(args) < 1 { return }
    match io.read(&args[0]) {
        Ok(b) {
            var opts = yaml.parseDefaults()
            opts.mergeKeys = false
            opts.allowDuplicateKeys = true
            match yaml.parseAllWith(&b, &opts) {
                Ok(docs) {
                    // Check write -> re-parse round-trip
                    let out = yaml.writeAll(&docs, &yaml.writeDefaults())
                    match yaml.parseAllWith(&out, &opts) {
                        Ok(back) {
                            if len(back) != len(docs) {
                                println("roundtrip count mismatch")
                                return
                            }
                            for i in 0..len(docs) {
                                if !back[i].eq(&docs[i]) {
                                    println("roundtrip differs")
                                    return
                                }
                            }
                        }
                        Err(e) {
                            println("roundtrip fails: " + e.toStr())
                            return
                        }
                    }
                    // Also emit JSON array of docs when possible
                    var jdocs: []json.Json = []
                    var allJson = true
                    for d in docs {
                        match yaml.toJson(&d) {
                            Ok(jv) { append(mut &jdocs, jv) }
                            Err(_) { allJson = false }
                        }
                    }
                    if allJson {
                        println("ok " + json.arrayOf(jdocs).toStr())
                    } else {
                        println("ok")
                    }
                }
                Err(e) { println("error " + e.toStr()) }
            }
        }
        Err(_) { println("unreadable") }
    }
}
'''


def iter_cases(suite_dir):
    for root, dirs, files in os.walk(suite_dir):
        dirs.sort()
        if 'in.yaml' in files:
            rel = os.path.relpath(root, suite_dir)
            yield rel, root


def parse_json_stream(text):
    dec = json.JSONDecoder()
    idx = 0
    out = []
    n = len(text)
    while idx < n:
        while idx < n and text[idx].isspace():
            idx += 1
        if idx >= n:
            break
        obj, idx = dec.raw_decode(text, idx)
        out.append(obj)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--c', action='store_true', help='build through C, not native')
    ap.add_argument('--suite', help='a yaml-test-suite data-branch checkout')
    ap.add_argument('-v', action='store_true', help='list failures verbosely')
    a = ap.parse_args()
    tmp = tempfile.mkdtemp(prefix='yamlsuite-')
    try:
        suite = a.suite
        if not suite:
            suite = os.path.join(tmp, 'yaml-test-suite')
            r = subprocess.run(['git', '-c', 'advice.detachedHead=false', 'clone', '-q', '--depth', '1',
                                '-b', 'data-2022-01-17',
                                'https://github.com/yaml/yaml-test-suite.git', suite])
            if r.returncode != 0:
                print('cannot fetch yaml-test-suite; give --suite DIR')
                return 2
        src = os.path.join(tmp, 'check.lxl')
        with open(src, 'w') as f:
            f.write(CHECK)
        exe = os.path.join(tmp, 'check')
        cmd = [LXLC, src, '-o', exe] + (['--c'] if a.c else ['--native'])
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print('build failed:', r.stdout, r.stderr)
            return 1

        env = dict(os.environ, LXL_CHECK='1')
        total = 0
        passed = 0
        crashes = []
        fails = []
        for rel, case_dir in iter_cases(suite):
            total += 1
            in_yaml = os.path.join(case_dir, 'in.yaml')
            is_error = os.path.exists(os.path.join(case_dir, 'error'))
            in_json_path = os.path.join(case_dir, 'in.json')
            r = subprocess.run([exe, in_yaml], capture_output=True, env=env, timeout=15)
            out = r.stdout.decode('utf-8', 'replace').strip()
            if r.returncode != 0:
                crashes.append((rel, f'exit {r.returncode}: {r.stderr.decode("utf-8", "replace").strip()[:200]}'))
                continue
            if is_error:
                if out.startswith('error '):
                    passed += 1
                else:
                    fails.append((rel, f'expected error, got: {out[:120]}'))
            else:
                if out == 'ok' or out.startswith('ok '):
                    if os.path.exists(in_json_path) and out.startswith('ok '):
                        expected = parse_json_stream(open(in_json_path).read())
                        actual = json.loads(out[3:])
                        if expected == actual:
                            passed += 1
                        else:
                            fails.append((rel, f'json mismatch: expected={expected!r} actual={actual!r}'[:200]))
                    else:
                        passed += 1
                else:
                    fails.append((rel, out[:200]))

        if a.v:
            for rel, why in crashes:
                print(f'CRASH {rel}: {why}')
            for rel, why in fails:
                print(f'FAIL  {rel}: {why}')
        print(f'{passed}/{total} passed, {len(fails)} failed, {len(crashes)} crashed ({("C" if a.c else "native")})')
        return 1 if crashes else 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())
