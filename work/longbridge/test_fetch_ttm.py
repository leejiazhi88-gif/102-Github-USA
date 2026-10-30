import unittest
from fetch_ttm import validate

class TTMChecks(unittest.TestCase):
 def baseline(self):return dict(symbol='SKHY.US',currency='USD',pe_ttm_ratio=24.05,eps_ttm=6.85,calc_last_done=164.7,regular_last_done=164.7)
 def test_rounded_screenshot_values_consistent(self):self.assertEqual(validate(self.baseline())['issues'],[])
 def test_generic_pe_not_accepted_as_ttm(self):
  r=self.baseline();r['pe_ttm_ratio']=11.22;self.assertTrue(validate(r)['issues'])
 def test_missing_ttm_not_replaced_by_computed_number(self):
  r=self.baseline();r['pe_ttm_ratio']=None;out=validate(r);self.assertIsNone(out['pe_ttm_ratio']);self.assertTrue(out['issues'])
 def test_non_us_listing_rejected(self):
  r=self.baseline();r['symbol']='000660.KS';self.assertTrue(validate(r)['issues'])
 def test_pre_market_not_used_for_regular_pe(self):
  r=self.baseline();r['pre_market_price_separate']=161.19;self.assertEqual(validate(r)['issues'],[])
 def test_changed_snapshot_flagged(self):
  r=self.baseline();r['regular_last_done']=161.19;self.assertTrue(validate(r)['issues'])
 def test_nonpositive_eps_not_normalized_into_positive_pe(self):
  r=self.baseline();r['eps_ttm']=-1;self.assertTrue(validate(r)['issues'])

if __name__=='__main__':unittest.main()
