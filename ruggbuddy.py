#!/usr/bin/env python3
"""RuggBuddy - a 100% on-device 'is this memecoin a trap?' explainer for a friend.

Pipeline (read-only, no wallet, no keys, no funds):
  1. mintcheck.py   -> deterministic on-chain facts + verdict (PASS / WARN / FAIL)
  2. a LOCAL open-weight model (Qwen2.5-0.5B-Instruct, 494M params, Apache-2.0)
     turns those facts into 3 plain-English sentences a non-technical friend can act on.
  3. a guard rejects any model sentence that contradicts the verdict or invents numbers,
     and falls back to a template. The model NEVER decides the verdict and can never say
     'safe' unless the rules said PASS.

Usage:  python ruggbuddy.py <MINT>            # live (needs network for RPC/DexScreener/RugCheck)
        python ruggbuddy.py --fixture fomp    # fully offline demo (fixtures/*.json)
        python ruggbuddy.py --fixture fomp --no-llm   # template only
Not financial advice. Passing checks does not make a token a good investment.
"""
import sys, json, re, os, time
HERE = os.path.dirname(os.path.abspath(__file__))
MODEL = os.environ.get("RUGGBUDDY_MODEL", "Qwen/Qwen2.5-0.5B-Instruct")  # 494M params (<=500M)

def facts_from(res):
    """Flat list of short factual strings the model is allowed to use."""
    f = [f"Verdict from the rule checker: {res['verdict']}."]
    f += [f"Red flag: {x}" for x in res.get("fails", [])]
    f += [f"Caution: {x}" for x in res.get("warns", [])]
    i = res.get("info", {})
    if i.get("liquidity_usd") is not None: f.append(f"Pool liquidity is about ${i['liquidity_usd']:,.0f}.")
    if i.get("curve_real_sol") is not None: f.append(f"The pump.fun curve still holds {i['curve_real_sol']:.3f} SOL.")
    if i.get("known"): f.append(f"This is the well-known token {i['known']}.")
    return f

def template(res):
    v = res["verdict"]
    head = {"FAIL": "Do not buy this. The checker found a deal-breaker, so you would probably not be able to sell.",
            "WARN": "Be careful. Nothing fatal was found, but some things could not be verified.",
            "PASS": "No red flags were found by these checks, but that does not mean the price will go up."}[v]
    why = " ".join("- " + x.rstrip(".") + "." for x in (res.get("fails") or res.get("warns") or [])[:2])
    return (head + (" Why: " + why if why else "") + " This is not financial advice.").strip()

def guard(text, res):
    """True if the model text is consistent with the rules."""
    t = text.lower(); v = res["verdict"]
    if re.search(r"\b(no risk|guaranteed|can't lose|moon|to the moon|100x)\b", t): return False   # hype: never
    if re.search(r"\b(safe|safely|sufficient|trustworthy|increase in value|go up|will rise|stable|profit|gain|buy this token)\b", t): return False   # a rule checker cannot certify safety
    if v == "FAIL" and not re.search(r"\b(do not|don't|avoid|stay away|not buy)\b", t): return False
    fx = " ".join(facts_from(res)).lower()
    for term in ("pump.fun", "low liquidity", "thin liquidity", "collapsed", "rug"):   # claims must appear in the facts
        if term in t and term not in fx: return False
    liq = res.get("info", {}).get("liquidity_usd")
    thin_ok = ("thin liquidity" in fx) or (liq is not None and liq < 3000) or ("no exit liquidity" in fx)
    if re.search(r"\b(low|thin|insufficient|poor|little)\b[^.]{0,25}liquidity", t) and not thin_ok: return False
    allowed = " ".join(facts_from(res)) + " " + json.dumps(res.get("info", {}))
    nums = set(re.findall(r"\d[\d,\.]*", text))
    for n in nums:
        n2 = n.rstrip(".,")
        if n2 and n2 not in allowed and n2 not in {"3", "1", "2"}: return False
    return True

_pipe = None
def llm_explain(res, max_new_tokens=110):
    global _pipe
    from transformers import AutoTokenizer, AutoModelForCausalLM
    import torch
    if _pipe is None:
        tok = AutoTokenizer.from_pretrained(MODEL); m = AutoModelForCausalLM.from_pretrained(MODEL, torch_dtype=torch.float32); m.eval(); _pipe = (tok, m)
    tok, m = _pipe
    FORCED = {"FAIL": "Do not buy this.", "WARN": "Be careful.", "PASS": "No red flags were found."}[res["verdict"]]
    opener = f"Your answer must begin with '{FORCED}' and then give the main reason from the facts. Never predict prices."
    sysmsg = ("You explain crypto token checks to a non-technical friend in at most 3 short sentences. "
              "Use ONLY the facts given. Do not add numbers that are not in the facts. " + opener +
              " Never say a token is 'safe'. No hype, no predictions.")
    msgs = [{"role": "system", "content": sysmsg},
            {"role": "user", "content": "Facts:\n" + "\n".join("- " + x for x in facts_from(res)) + "\nExplain in plain English."}]
    prompt = tok.apply_chat_template(msgs, add_generation_prompt=True, tokenize=False)
    prompt += FORCED   # prefill: the model can only continue a verdict-consistent opening (a 0.5B model is otherwise able to say 'Buy this' on FAIL)
    enc = tok(prompt, return_tensors="pt")
    with torch.no_grad():
        out = m.generate(**enc, max_new_tokens=max_new_tokens, do_sample=False, repetition_penalty=1.1)
    return (FORCED + tok.decode(out[0][enc["input_ids"].shape[1]:], skip_special_tokens=True)).strip()

def explain(res, use_llm=True):
    """Returns (text, source) where source in {'local-llm','template'}."""
    if use_llm:
        try:
            t = llm_explain(res)
            if t and guard(t, res): return t, "local-llm"
        except Exception as e:
            print("[ruggbuddy] LLM unavailable:", type(e).__name__, file=sys.stderr)
    return template(res), "template"

def main(argv):
    if len(argv) < 2: sys.exit(__doc__)
    use_llm = "--no-llm" not in argv
    if "--fixture" in argv:
        res = json.load(open(os.path.join(HERE, "fixtures", argv[argv.index("--fixture") + 1] + ".json")))
    else:
        import mintcheck; res = mintcheck.check(argv[1])
    t0 = time.time(); text, src = explain(res, use_llm)
    print(f"{res['verdict']}  {res['mint']}")
    print(text); print(f"[explanation by: {src}; {time.time()-t0:.1f}s; model={MODEL if src=='local-llm' else 'n/a'}; verdict by rules]")
    return 0 if res["verdict"] != "FAIL" else 2

if __name__ == "__main__": sys.exit(main(sys.argv))
