import json, os, sys, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import ruggbuddy as rb
def fx(n):
    with open(os.path.join(os.path.dirname(__file__), "..", "fixtures", n + ".json")) as f: return json.load(f)
class T(unittest.TestCase):
    def test_template_fail_says_avoid(self): self.assertIn("Do not buy", rb.template(fx("fomp")))
    def test_guard_blocks_safe_on_fail(self): self.assertFalse(rb.guard("This looks safe, go ahead.", fx("fomp")))
    def test_guard_requires_avoid_on_fail(self): self.assertFalse(rb.guard("It has little money in it.", fx("fomp")))
    def test_guard_accepts_grounded_fail(self): self.assertTrue(rb.guard("Do not buy this: the curve only holds 0.218 SOL, so you likely cannot sell.", fx("fomp")))
    def test_guard_blocks_invented_numbers(self): self.assertFalse(rb.guard("Do not buy; it lost 97% already.", fx("fomp")))
    def test_pass_allows_safeish_words_but_not_hype(self): self.assertFalse(rb.guard("This will moon.", fx("usdc")))
    def test_no_llm_fallback(self):
        t, s = rb.explain(fx("bonk"), use_llm=False); self.assertEqual(s, "template"); self.assertIn("Be careful", t)
    def test_guard_blocks_ungrounded_claims(self): self.assertFalse(rb.guard("Be careful. This pump.fun token has low liquidity.", fx("bonk")))
    def test_guard_blocks_wrong_low_liquidity_claim(self): self.assertFalse(rb.guard("Do not buy this. It has low pool liquidity and concentrated holders.", fx("top10")))
    def test_guard_allows_thin_when_fact(self): self.assertTrue(rb.guard("Be careful. Liquidity is thin at $1,800.", fx("thin")))
if __name__ == "__main__": unittest.main()
