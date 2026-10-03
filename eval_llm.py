"""How often does the local 0.5B model's text pass the guard? (honest reliability number)"""
import json, glob, os, sys
import ruggbuddy as rb
rows=[]
for f in sorted(glob.glob(os.path.join(rb.HERE,"fixtures","*.json"))):
    with open(f) as fh: r=json.load(fh)
    t=rb.llm_explain(r); ok=rb.guard(t,r); rows.append((os.path.basename(f),r["verdict"],ok,t))
    print(f"{os.path.basename(f):14s} {r['verdict']:5s} guard_pass={ok}\n   {t}")
n=sum(1 for x in rows if x[2]); print(f"\nlocal-LLM text accepted by guard: {n}/{len(rows)}; the rest fall back to the template.")
