"""Offline unit tests (no network). Run: python3 -m unittest discover -s tests -v   (from the deliverable directory)"""
import sys,os,unittest,struct,base64
sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..'))
import mintcheck as m
FOMP='jjVuJvbvQZ2jgaqBnYPB3gb78hAkG6np47WZwJipump'
class T(unittest.TestCase):
    def test_b58_roundtrip(self):
        b=m.b58d(FOMP); self.assertEqual(len(b),32); self.assertEqual(m.b58e(b),FOMP)
    def test_curve_pda_known_vector(self):   # verified on-chain 2026-10-02: this account exists, owned by the pump program
        self.assertEqual(m.curve_pda(FOMP),'G9ByEqvdm7633VV9gQxb3geuJFbywsv5zd24ecWBeRGA')
    def test_pda_is_off_curve(self):
        self.assertFalse(m.oncurve(m.b58d(m.curve_pda(FOMP))))
    def _run(self,mint_info,curve=None,pairs=None,holders=None,rug=None):
        acct={'value':{'owner':'TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA','data':{'parsed':{'type':'mint','info':mint_info}}}}
        def fake_rpc(method,params,tries=6):
            if method=='getAccountInfo' and params[1].get('encoding')=='jsonParsed': return acct
            if method=='getAccountInfo': return curve if curve else {'value':None}
            if method=='getTokenLargestAccounts': return holders
        def fake_get(u,tries=5):
            if 'dexscreener' in u: return pairs
            if 'rugcheck' in u: return rug
            return {'So11111111111111111111111111111111111111112':{'usdPrice':100.0}}
        m.rpc,m.get=fake_rpc,fake_get
        return m.check(FOMP)
    def curve(self,real_sol,complete=False):
        d=bytearray(49+8); d[8:48]=struct.pack('<5Q',30*10**9,10**15,10**15,int(real_sol*1e9),10**15); d[48]=1 if complete else 0
        return {'value':{'owner':m.PUMP,'data':[base64.b64encode(bytes(d)).decode(),'base64']}}
    base={'supply':'1000000000000000','decimals':6,'mintAuthority':None,'freezeAuthority':None}
    holders={'value':[{'uiAmount':1e7}]*10}
    def test_fail_when_curve_empty(self):
        r=self._run(self.base,self.curve(0.2),[{'dexId':'pumpfun','marketCap':3000,'liquidity':{'usd':0}}],self.holders,{'risks':[]})
        self.assertEqual(r['verdict'],'FAIL'); self.assertTrue(any('exit liquidity' in x for x in r['fails']))
    def test_fail_on_offcurve_venue(self):
        r=self._run(self.base,self.curve(5),[{'dexId':'meteora','marketCap':20000,'liquidity':{'usd':9000}}],self.holders,{'risks':[]})
        self.assertEqual(r['verdict'],'FAIL'); self.assertTrue(any('venue' in x for x in r['fails']))
    def test_fail_on_mint_authority(self):
        b=dict(self.base,mintAuthority='Abc'+'1'*40)
        r=self._run(b,self.curve(5),[{'dexId':'pumpfun','marketCap':9000,'liquidity':{'usd':9000}}],self.holders,{'risks':[]})
        self.assertEqual(r['verdict'],'FAIL')
    def test_fail_closed_when_dex_unreadable(self):
        r=self._run(self.base,self.curve(5),None,self.holders,{'risks':[]})
        self.assertEqual(r['verdict'],'FAIL')
    def test_pass_clean_curve_coin(self):
        r=self._run(self.base,self.curve(10),[{'dexId':'pumpfun','marketCap':9000,'liquidity':{'usd':9000}}],self.holders,{'risks':[],'score_normalised':1})
        self.assertEqual(r['verdict'],'PASS',r)
    def test_fail_on_concentration(self):
        r=self._run(self.base,self.curve(10),[{'dexId':'pumpfun','marketCap':9000,'liquidity':{'usd':9000}}],{'value':[{'uiAmount':1e9}]*11},{'risks':[]})
        self.assertEqual(r['verdict'],'FAIL')
if __name__=='__main__': unittest.main()
