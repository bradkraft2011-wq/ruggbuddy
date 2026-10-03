#!/usr/bin/env python3
"""mintcheck - read-only Solana token safety check. No wallet, no keys, no signing, no spending.
Usage: python3 mintcheck.py <MINT> [--json] [--strict-venues]
Checks (free public endpoints): mint/freeze authority, risky Token-2022 extensions, pump.fun bonding-curve state,
trading venues (DexScreener), curve-vs-quoted market-cap mismatch (off-curve pool / pulled-liquidity pattern),
top-holder concentration, RugCheck summary. Verdict FAIL (any hard flag) / WARN / PASS. Fail-closed: unreadable => FAIL.
A filter for obvious traps, NOT a guarantee a token is safe. Not financial advice."""
import json,sys,time,struct,base64,hashlib,urllib.request,urllib.error
RPCS=['https://solana-rpc.publicnode.com','https://api.mainnet-beta.solana.com']
PUMP='6EF8rrecthR5Dkzon8Nwu78hRvfCKubJ14M5uBEwF6P'
OK_DEX={'pumpfun','pumpswap'}
RISKY_EXT={'permanentDelegate','transferHook','transferFeeConfig','nonTransferable','confidentialTransferMint','defaultAccountState','pausableConfig'}
# well-known mints with legitimately held authorities (stablecoins / majors): authority flags are expected, not a rug
KNOWN={'EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v':'USDC (Circle)','Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB':'USDT (Tether)','So11111111111111111111111111111111111111112':'wSOL'}
STRICT='--strict-venues' in sys.argv   # treat any non-pump.fun/PumpSwap venue as FAIL
A58='123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz'
def b58d(s):
    n=0
    for c in s: n=n*58+A58.index(c)
    return b'\0'*(len(s)-len(s.lstrip('1')))+n.to_bytes((n.bit_length()+7)//8,'big')
def b58e(b):
    n=int.from_bytes(b,'big'); o=''
    while n: n,r=divmod(n,58); o=A58[r]+o
    return '1'*(len(b)-len(b.lstrip(b'\0')))+o
P=2**255-19; D=-121665*pow(121666,P-2,P)%P
def oncurve(b):
    y=int.from_bytes(b,'little')&((1<<255)-1)
    if y>=P: return False
    u=(y*y-1)%P; v=(D*y*y+1)%P; x2=u*pow(v,P-2,P)%P
    return x2==0 or pow(x2,(P-1)//2,P)==1
def curve_pda(mint):
    for bump in range(255,-1,-1):
        h=hashlib.sha256(b'bonding-curve'+b58d(mint)+bytes([bump])+b58d(PUMP)+b'ProgramDerivedAddress').digest()
        if not oncurve(h): return b58e(h)
def rpc(m,p,tries=6):
    for i in range(tries):
        try:
            r=json.load(urllib.request.urlopen(urllib.request.Request(RPCS[i%len(RPCS)],data=json.dumps({"jsonrpc":"2.0","id":1,"method":m,"params":p}).encode(),headers={'Content-Type':'application/json','User-Agent':'mintcheck'}),timeout=12))
            if 'result' in r: return r['result']
        except Exception: pass
        time.sleep(.4*(i+1))
def get(u,tries=5):
    for i in range(tries):
        try:
            body=urllib.request.urlopen(urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0'}),timeout=12).read()
            return json.loads(body) if body.strip() else []   # empty 200 body = indexer has no pools for this mint
        except urllib.error.HTTPError as e:
            ra=e.headers.get('Retry-After') if e.code==429 else None
            time.sleep(min(float(ra),20)+1 if ra and ra.replace('.','',1).isdigit() else .5*(i+1))
        except Exception: time.sleep(.5*(i+1))
def sol_usd():
    d=get('https://lite-api.jup.ag/price/v3?ids=So11111111111111111111111111111111111111112')
    try: return float(d['So11111111111111111111111111111111111111112']['usdPrice'])
    except Exception: return None
def check(mint):
    fails,warns,info=[],[],{}
    try: b58d(mint)
    except Exception: return {'mint':mint,'verdict':'FAIL','fails':['invalid base58 address'],'warns':[],'info':{}}
    a=rpc('getAccountInfo',[mint,{"encoding":"jsonParsed"}])
    if not a or not a.get('value'): return {'mint':mint,'verdict':'FAIL','fails':['mint account unreadable / does not exist'],'warns':[],'info':{}}
    v=a['value']; info['token_program']=v['owner']
    pr=v['data'].get('parsed') if isinstance(v.get('data'),dict) else None
    if not pr or pr.get('type')!='mint': return {'mint':mint,'verdict':'FAIL','fails':['account is not an SPL mint'],'warns':[],'info':info}
    mi=pr['info']; info.update(supply=int(mi['supply'])/10**mi['decimals'],decimals=mi['decimals'])
    known=KNOWN.get(mint)
    if known: info['known']=known
    if mi.get('mintAuthority'):
        (info.setdefault('expected_authorities',[]) if known else fails).append(f"mint authority set ({mi['mintAuthority'][:6]}..)" if known else f"mint authority NOT renounced ({mi['mintAuthority'][:6]}..): supply can be inflated")
    if mi.get('freezeAuthority'):
        (info.setdefault('expected_authorities',[]) if known else fails).append(f"freeze authority set ({mi['freezeAuthority'][:6]}..)" if known else f"freeze authority set ({mi['freezeAuthority'][:6]}..): balances can be frozen")
    for e in mi.get('extensions',[]) or []:
        if e.get('extension') in RISKY_EXT: fails.append(f"Token-2022 extension '{e['extension']}' (can tax/block/seize transfers)")
    cp=curve_pda(mint); c=rpc('getAccountInfo',[cp,{"encoding":"base64"}]); curve_mc=None
    if c and c.get('value') and c['value']['owner']==PUMP:
        d=base64.b64decode(c['value']['data'][0]); vt,vs,rt,rs,ts=struct.unpack('<5Q',d[8:48]); complete=bool(d[48])
        info.update(pump_curve=cp,curve_complete=complete,curve_real_sol=rs/1e9)
        px=sol_usd()
        if px and rt: curve_mc=(vs/1e9)/(rt/1e6)*1e9*px; info['curve_mc_usd']=round(curve_mc)
    else:
        if not known: warns.append('not a pump.fun bonding-curve token (liquidity must be verified another way)')
    pairs=get(f'https://api.dexscreener.com/token-pairs/v1/solana/{mint}')
    if pairs is None: fails.append('DexScreener unreadable (fail closed)'); pairs=[]
    elif not pairs: fails.append('no trading pools found (dead / liquidity pulled)')
    dex=sorted({str(p.get('dexId')) for p in pairs}); info['dexes']=dex
    bad=[x for x in dex if x not in OK_DEX]
    if bad and not known:
        msg=f"trades on venue(s) whose liquidity is not verifiable from the pump.fun curve: {bad} (Meteora/other pools can be pulled by the creator)"
        if STRICT or (info.get('pump_curve') and not info.get('curve_complete')): fails.append(msg)   # un-graduated pump coin trading elsewhere = FOMP pattern
        else: warns.append(msg)
    mcs=[p.get('marketCap') for p in pairs if p.get('marketCap')]
    if mcs: info['quoted_mc_usd']=max(mcs)
    if curve_mc and mcs and not info.get('curve_complete') and max(mcs)>2.5*curve_mc:
        fails.append(f"quoted MC ${max(mcs):,.0f} >> on-chain curve MC ${curve_mc:,.0f}: trading is OFF the curve (FOMP-style rug pattern)")
    liq=sum((p.get('liquidity') or {}).get('usd',0) or 0 for p in pairs); info['liquidity_usd']=round(liq)
    if info.get('pump_curve') and not info.get('curve_complete'):
        px2=sol_usd(); exit_liq=info['curve_real_sol']*(px2 or 0)    # SOL actually sitting in the curve = what sellers can exit into
        info['curve_exit_liquidity_usd']=round(exit_liq)
        if info['curve_real_sol']<0.5: fails.append(f"only {info['curve_real_sol']:.3f} SOL ({'~$%d'%exit_liq if px2 else 'USD price n/a'}) left in the curve: effectively no exit liquidity (liquidity pulled / dead coin, FOMP-style)")
        elif info['curve_real_sol']<3: warns.append(f"low curve liquidity {info['curve_real_sol']:.2f} SOL")
    elif pairs and liq<3000 and not known: warns.append(f'thin liquidity ${liq:,.0f}')
    h=rpc('getTokenLargestAccounts',[mint])
    if h and info.get('supply') and not known:
        top=sorted([float(x.get('uiAmount') or 0) for x in h['value']],reverse=True)
        skip=1 if info.get('pump_curve') and not info.get('curve_complete') else 0
        t10=sum(top[skip:skip+10])/info['supply']*100; info['top10_pct_excl_curve']=round(t10,1)
        if t10>50: fails.append(f'top-10 holders own {t10:.0f}% of supply (excluding curve)')
        elif t10>30: warns.append(f'top-10 holders own {t10:.0f}% of supply')
    r=get(f'https://api.rugcheck.xyz/v1/tokens/{mint}/report/summary')
    if r:
        risks=r.get('risks',[]) or []; info['rugcheck_score_norm']=r.get('score_normalised'); info['rugcheck_risks']=[f"{x.get('name')}:{x.get('level')}" for x in risks]
        if any(x.get('level') in ('danger','critical') for x in risks) and not known: fails.append('RugCheck danger-level risk(s): '+'; '.join(info['rugcheck_risks']))
    else: warns.append('RugCheck unavailable')
    return {'mint':mint,'verdict':'FAIL' if fails else ('WARN' if warns else 'PASS'),'fails':fails,'warns':warns,'info':info}
if __name__=='__main__':
    if len(sys.argv)<2: sys.exit(__doc__)
    r=check(sys.argv[1])
    if '--json' in sys.argv: print(json.dumps(r,indent=1))
    else:
        print(f"{r['verdict']}  {sys.argv[1]}")
        for x in r['fails']: print('  [FAIL]',x)
        for x in r['warns']: print('  [warn]',x)
        print('  info:',json.dumps(r.get('info',{})))
    sys.exit(0 if r['verdict']!='FAIL' else 2)
