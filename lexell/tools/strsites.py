#!/usr/bin/env python3
"""The string copies a program makes, by the clone site that makes them (the costliest first).

    LXL_RCSTAT=sites lexell/compiler/out/lxlc prog.lxl --native -o prog 2> map.txt
    ./prog ... 2> counts.txt
    python3 lexell/tools/strsites.py map.txt counts.txt [N]

The compiler lists each rt_str_dup site as "strsite K FUNCTION LINE"; the program prints the heap
strings (cap > 0) copied at each and their bytes as "strsite K COPIES BYTES" at exit
(compiler/rcstat.lxl). Copies of static strings (literals, strStatic) cost nothing and are not
counted. A site in a glue function (glNN_...) is a record or array clone."""
import sys
m={}
for l in open(sys.argv[1]):
    p=l.split()
    if len(p)==4 and p[0]=="strsite": m[p[1]]=p[2]
rows=[]
for l in open(sys.argv[2]):
    p=l.split()
    if len(p)==4 and p[0]=="strsite": rows.append((int(p[2]),int(p[3]),m.get(p[1],"?")))
rows.sort(key=lambda r:-r[0])
print("heap str copies:",sum(r[0] for r in rows),"bytes",sum(r[1] for r in rows))
for c,b,f in rows[:int(sys.argv[3]) if len(sys.argv) > 3 else 30]: print("%8d %9d  %s"%(c,b,f))
