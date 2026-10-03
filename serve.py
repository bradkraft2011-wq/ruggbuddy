#!/usr/bin/env python3
"""Tiny local demo UI for mintcheck (stdlib only). Run: python3 serve.py  ->  http://127.0.0.1:8787  (binds to localhost only)"""
import json,re,http.server,urllib.parse
from mintcheck import check
PAGE="""<!doctype html><meta charset=utf-8><title>mintcheck</title>
<style>body{font:15px system-ui;max-width:760px;margin:2em auto;padding:0 1em}input{width:78%;padding:.5em}button{padding:.5em 1em}
.FAIL{color:#b00020}.WARN{color:#b26a00}.PASS{color:#1b7f3b}pre{background:#f5f5f5;padding:1em;overflow:auto}</style>
<h2>mintcheck &mdash; read-only Solana token safety check</h2>
<form onsubmit="go();return false"><input id=m placeholder="paste a token mint address"> <button>Check</button></form>
<div id=o></div><p><small>Read-only. No wallet, no signing. A filter for obvious traps, not a guarantee. Not financial advice.</small></p>
<script>async function go(){const m=document.getElementById('m').value.trim();const o=document.getElementById('o');o.textContent='checking...';
const r=await (await fetch('/api/check?mint='+encodeURIComponent(m))).json();
o.innerHTML='<h3 class='+r.verdict+'>'+r.verdict+'</h3>'+r.fails.map(x=>'<div class=FAIL>FAIL: '+x+'</div>').join('')+r.warns.map(x=>'<div class=WARN>warn: '+x+'</div>').join('')+'<pre>'+JSON.stringify(r.info,null,1)+'</pre>'}</script>"""
class H(http.server.BaseHTTPRequestHandler):
    def do_GET(s):
        u=urllib.parse.urlparse(s.path)
        if u.path=='/api/check':
            m=urllib.parse.parse_qs(u.query).get('mint',[''])[0]
            body=json.dumps(check(m) if re.fullmatch(r'[1-9A-HJ-NP-Za-km-z]{32,44}',m) else {'verdict':'FAIL','fails':['not a valid base58 address'],'warns':[],'info':{}}).encode(); t='application/json'
        else: body=PAGE.encode(); t='text/html'
        s.send_response(200); s.send_header('Content-Type',t); s.end_headers(); s.wfile.write(body)
    def log_message(s,*a): pass
if __name__=='__main__': http.server.ThreadingHTTPServer(('127.0.0.1',8787),H).serve_forever()
