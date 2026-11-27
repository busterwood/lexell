#!/usr/bin/env python3
"""HTTP/2 server benchmark: Lexell httpserver (native -O) vs Go net/http vs Node.js http2.

    python3 lexell/cmd/http2_bench.py [--servers lexell,go,node]
                                      [--modes h2c,tls]
                                      [--cases 1x1,1x10,1x100,10x10]
                                      [--seconds 5]

Each server answers GET / with "hello, world\\n" (text/plain) on one core
(CPU 0; GOMAXPROCS=1 for Go, single process for Lexell and Node.js).
A shared neutral Go HTTP/2 load client runs on CPUs 4-7,12-15 (separate
physical cores from CPU 0 / SMT sibling CPU 8) with C independent HTTP/2
connections and S concurrent streams per connection (CxS), verifying
ProtoMajor == 2 and body length 13 on every reply.
"""
import argparse
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
LEXELL = os.path.dirname(HERE)
DEFAULT_LXLC = os.path.join(LEXELL, 'compiler', 'out', 'lxlc')

LXL_SRV_SRC = r'''import "httpserver" as http
import "net"
import "os"
import "tls"

type App = value record {}

fn hello(app: &App, rq: mut &http.Request, w: mut &http.Response): Result[Unit, http.Error] {
    return w.text("hello, world\n")
}

fn main() {
    let mode = os.envOr("H2_MODE", "h2c")
    var r = http.router[App]()
    r.handle("GET /{$}", hello)
    var cfg = http.defaults()
    cfg.logFd = -1
    cfg.h2 = true
    cfg.h2c = mode == "h2c"
    cfg.maxConcurrentStreams = 256
    let ln = net.listen("127.0.0.1:0").unwrap()
    eprintln("listening on " + ln.localAddr())
    if mode == "tls" {
        var to = tls.defaults()
        to.certFile = os.envOr("H2_CERT", "")
        to.keyFile = os.envOr("H2_KEY", "")
        to.alpn = "h2"
        let ctx = tls.server(to).unwrap()
        let _s = http.serveTls(ln, ctx, App{}, r, cfg).unwrap()
    } else {
        let _s = http.serve(ln, App{}, r, cfg).unwrap()
    }
}
'''

GO_SRV_SRC = r'''package main

import (
	"crypto/tls"
	"fmt"
	"net"
	"net/http"
	"os"
)

func main() {
	mode := os.Getenv("H2_MODE")
	mux := http.NewServeMux()
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "text/plain")
		w.Write([]byte("hello, world\n"))
	})
	var p http.Protocols
	if mode == "tls" {
		p.SetHTTP2(true)
	} else {
		p.SetUnencryptedHTTP2(true)
	}
	srv := &http.Server{Handler: mux, Protocols: &p}
	ln, err := net.Listen("tcp", "127.0.0.1:0")
	if err != nil {
		fmt.Fprintln(os.Stderr, err)
		os.Exit(1)
	}
	if mode == "tls" {
		cert, err := tls.LoadX509KeyPair(os.Getenv("H2_CERT"), os.Getenv("H2_KEY"))
		if err != nil {
			fmt.Fprintln(os.Stderr, err)
			os.Exit(1)
		}
		tlsCfg := &tls.Config{Certificates: []tls.Certificate{cert}, NextProtos: []string{"h2"}}
		ln = tls.NewListener(ln, tlsCfg)
	}
	fmt.Fprintln(os.Stderr, "listening on", ln.Addr().String())
	srv.Serve(ln)
}
'''

NODE_SRV_SRC = r'''const http2 = require('http2');
const fs = require('fs');
const mode = process.env.H2_MODE || 'h2c';
const onStream = (stream, headers) => {
  stream.respond({ ':status': 200, 'content-type': 'text/plain', 'content-length': 13 });
  stream.end('hello, world\n');
};
let srv;
if (mode === 'tls') {
  srv = http2.createSecureServer({
    key: fs.readFileSync(process.env.H2_KEY),
    cert: fs.readFileSync(process.env.H2_CERT),
    settings: { maxConcurrentStreams: 256 },
  });
} else {
  srv = http2.createServer({ settings: { maxConcurrentStreams: 256 } });
}
srv.on('stream', onStream);
srv.listen(0, '127.0.0.1', () => {
  process.stderr.write('listening on 127.0.0.1:' + srv.address().port + '\n');
});
'''

GO_LOAD_SRC = r'''package main

import (
	"crypto/tls"
	"fmt"
	"io"
	"net/http"
	"os"
	"sort"
	"strconv"
	"sync"
	"time"
)

func main() {
	mode := os.Args[1]
	addr := os.Args[2]
	conns, _ := strconv.Atoi(os.Args[3])
	streams, _ := strconv.Atoi(os.Args[4])
	secs, _ := strconv.Atoi(os.Args[5])

	scheme := "http"
	if mode == "tls" {
		scheme = "https"
	}
	url := scheme + "://" + addr + "/"

	clients := make([]*http.Client, conns)
	for i := 0; i < conns; i++ {
		var p http.Protocols
		var tlsCfg *tls.Config
		if mode == "tls" {
			p.SetHTTP2(true)
			tlsCfg = &tls.Config{InsecureSkipVerify: true}
		} else {
			p.SetUnencryptedHTTP2(true)
		}
		tr := &http.Transport{
			Protocols:       &p,
			TLSClientConfig: tlsCfg,
		}
		clients[i] = &http.Client{Transport: tr}
		// Warm up connection so handshake/SETTINGS happen before timed window
		resp, err := clients[i].Get(url)
		if err != nil {
			fmt.Fprintf(os.Stderr, "warmup failed: %v\n", err)
			os.Exit(1)
		}
		io.Copy(io.Discard, resp.Body)
		resp.Body.Close()
		if resp.ProtoMajor != 2 {
			fmt.Fprintf(os.Stderr, "expected HTTP/2, got %s\n", resp.Proto)
			os.Exit(1)
		}
	}

	totalWorkers := conns * streams
	lats := make([][]int64, totalWorkers)
	errs := make([]int64, totalWorkers)
	var wg sync.WaitGroup
	start := time.Now()
	end := start.Add(time.Duration(secs) * time.Second)

	for c := 0; c < conns; c++ {
		for s := 0; s < streams; s++ {
			idx := c*streams + s
			cl := clients[c]
			wg.Add(1)
			go func(w int, client *http.Client) {
				defer wg.Done()
				buf := make([]byte, 64)
				local := make([]int64, 0, 8192)
				var e int64
				for time.Now().Before(end) {
					t0 := time.Now()
					resp, err := client.Get(url)
					if err != nil {
						e++
						continue
					}
					n := 0
					for {
						k, rerr := resp.Body.Read(buf)
						n += k
						if rerr != nil {
							break
						}
					}
					resp.Body.Close()
					if resp.StatusCode != 200 || resp.ProtoMajor != 2 || n != 13 {
						e++
						continue
					}
					local = append(local, time.Since(t0).Nanoseconds())
				}
				lats[w] = local
				errs[w] = e
			}(idx, cl)
		}
	}
	wg.Wait()
	elapsed := time.Since(start).Seconds()

	var all []int64
	var totalErr int64
	for i := 0; i < totalWorkers; i++ {
		all = append(all, lats[i]...)
		totalErr += errs[i]
	}
	sort.Slice(all, func(i, j int) bool { return all[i] < all[j] })
	n := len(all)
	rps := int64(float64(n) / elapsed)
	var p50, p99 int64
	if n > 0 {
		p50 = all[n*50/100] / 1000
		p99 = all[n*99/100] / 1000
	}
	fmt.Printf("requests %d rps %d p50 %d p99 %d errors %d\n", n, rps, p50, p99, totalErr)
	for _, cl := range clients {
		cl.CloseIdleConnections()
	}
}
'''


def rss_kb(pid):
    try:
        with open(f'/proc/{pid}/status') as f:
            for line in f:
                if line.startswith('VmRSS:'):
                    return int(line.split()[1])
    except OSError:
        pass
    return 0


def make_cert(tmp):
    cert = os.path.join(tmp, 'cert.pem')
    key = os.path.join(tmp, 'key.pem')
    subprocess.run([
        'openssl', 'req', '-x509', '-newkey', 'ec', '-pkeyopt', 'ec_paramgen_curve:prime256v1',
        '-keyout', key, '-out', cert, '-days', '1', '-nodes', '-subj', '/CN=localhost'
    ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return cert, key


def run_one(srv_name, srv_cmd, srv_env, load_bin, mode, cases, secs):
    proc = subprocess.Popen(['taskset', '-c', '0'] + srv_cmd, env=srv_env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
    try:
        line = proc.stderr.readline().strip()
        if not line.startswith('listening on '):
            rest = proc.stderr.read()
            raise RuntimeError(f'{srv_name} failed to start: {line}\n{rest}')
        addr = line.split('listening on ', 1)[1].strip()
        results = {}
        load_env = dict(os.environ, GOMAXPROCS='8')
        for conns, streams in cases:
            r = subprocess.run(['taskset', '-c', '4-7,12-15', load_bin, mode, addr, str(conns), str(streams), str(secs)],
                               capture_output=True, text=True, env=load_env)
            if r.returncode != 0:
                raise RuntimeError(f'load failed on {srv_name} {mode} {conns}x{streams}: {r.stderr}')
            parts = r.stdout.strip().split()
            d = {parts[i]: int(parts[i + 1]) for i in range(0, len(parts), 2)}
            d['rss_mb'] = round(rss_kb(proc.pid) / 1024.0, 1)
            results[(conns, streams)] = d
        return results
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=3)
        except subprocess.TimeoutExpired:
            proc.kill()
            proc.wait()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--servers', default='lexell,go,node')
    ap.add_argument('--modes', default='h2c,tls')
    ap.add_argument('--cases', default='1x1,1x10,1x100,10x10')
    ap.add_argument('--seconds', type=int, default=5)
    ap.add_argument('--compiler', default=DEFAULT_LXLC)
    args = ap.parse_args()

    servers = [s.strip() for s in args.servers.split(',') if s.strip()]
    modes = [m.strip() for m in args.modes.split(',') if m.strip()]
    cases = []
    for c in args.cases.split(','):
        a, b = c.strip().split('x')
        cases.append((int(a), int(b)))

    with tempfile.TemporaryDirectory(prefix='lxl_h2bench_') as tmp:
        cert, key = make_cert(tmp)
        env_lxl = dict(os.environ, LXL_LIB=os.path.join(LEXELL, 'lib'))
        env_go = dict(os.environ, GO111MODULE='off', GOFLAGS='', GOCACHE=os.path.join(tmp, 'gocache'))

        lxl_src = os.path.join(tmp, 'srv.lxl')
        lxl_bin = os.path.join(tmp, 'srv-lxl')
        open(lxl_src, 'w').write(LXL_SRV_SRC)
        subprocess.run([args.compiler, lxl_src, '--native', '-O', '-o', lxl_bin], check=True, env=env_lxl)

        go_load_src = os.path.join(tmp, 'load.go')
        go_load_bin = os.path.join(tmp, 'h2load')
        open(go_load_src, 'w').write(GO_LOAD_SRC)
        subprocess.run(['go', 'build', '-o', go_load_bin, go_load_src], check=True, env=env_go)

        cmds = {}
        if 'lexell' in servers:
            cmds['lexell'] = ([lxl_bin], dict(env_lxl))
        if 'go' in servers and shutil.which('go'):
            go_srv_src = os.path.join(tmp, 'srv.go')
            go_srv_bin = os.path.join(tmp, 'srv-go')
            open(go_srv_src, 'w').write(GO_SRV_SRC)
            subprocess.run(['go', 'build', '-o', go_srv_bin, go_srv_src], check=True, env=env_go)
            cmds['go'] = ([go_srv_bin], dict(os.environ, GOMAXPROCS='1'))
        if 'node' in servers and shutil.which('node'):
            node_src = os.path.join(tmp, 'srv.js')
            open(node_src, 'w').write(NODE_SRV_SRC)
            cmds['node'] = ([shutil.which('node'), node_src], dict(os.environ))

        for mode in modes:
            print(f'\n=== HTTP/2 ({mode}) ===', flush=True)
            all_res = {}
            for name in servers:
                if name not in cmds:
                    print(f'skipping {name} (not installed)', flush=True)
                    continue
                cmd, base_e = cmds[name]
                e = dict(base_e, H2_MODE=mode, H2_CERT=cert, H2_KEY=key)
                all_res[name] = run_one(name, cmd, e, go_load_bin, mode, cases, args.seconds)
            for conns, streams in cases:
                row = f'{conns}x{streams:3d}:'
                for name in servers:
                    if name in all_res:
                        d = all_res[name][(conns, streams)]
                        row += f'  {name}={d["rps"]:7d} rps (p50={d["p50"]:4d}us p99={d["p99"]:5d}us err={d["errors"]} rss={d["rss_mb"]}MB)'
                print(row, flush=True)


if __name__ == '__main__':
    main()
