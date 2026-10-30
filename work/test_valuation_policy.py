import unittest
from valuation_policy import forward_pe, earnings_from_eps

class ValuationPolicyTests(unittest.TestCase):
    def setUp(self):
        self.price = dict(value=200,currency='USD',security_id='issuer:US_ADS',verified=True,source='official quote')
        self.eps = dict(value=10,currency='USD',security_id='issuer:US_ADS',verified=True,source='forecast with metadata',period='FY2027',basis='IFRS_diluted')
        self.shares = dict(value=100,security_id='issuer:US_ADS',verified=True,source='forecast diluted denominator',period='FY2027',basis='forecast_weighted_average_diluted')

    def test_verified_same_security_pe(self):
        self.assertEqual(forward_pe(self.price,self.eps),20)

    def test_us_quote_cannot_use_local_currency_eps(self):
        self.eps['currency']='TWD'
        with self.assertRaises(ValueError): forward_pe(self.price,self.eps)

    def test_same_currency_does_not_make_ads_and_ordinary_identical(self):
        self.eps['security_id']='issuer:ordinary'
        with self.assertRaises(ValueError): forward_pe(self.price,self.eps)

    def test_currency_label_alone_is_not_verification(self):
        self.eps['verified']=False
        with self.assertRaises(ValueError): forward_pe(self.price,self.eps)

    def test_unknown_eps_accounting_basis(self):
        self.eps['basis']='unknown'
        with self.assertRaises(ValueError): forward_pe(self.price,self.eps)

    def test_negative_eps_is_not_positive_pe(self):
        self.eps['value']=-10
        with self.assertRaises(ValueError): forward_pe(self.price,self.eps)

    def test_verified_matching_eps_and_forecast_diluted_shares(self):
        self.assertEqual(earnings_from_eps(self.eps,self.shares),1000)

    def test_market_cap_divided_by_price_is_not_forecast_denominator(self):
        self.shares['basis']='market_cap_div_price'
        with self.assertRaises(ValueError): earnings_from_eps(self.eps,self.shares)

    def test_current_shares_are_not_forecast_weighted_average(self):
        self.shares['basis']='current_outstanding'
        with self.assertRaises(ValueError): earnings_from_eps(self.eps,self.shares)

    def test_forecast_period_mismatch(self):
        self.shares['period']='FY2026'
        with self.assertRaises(ValueError): earnings_from_eps(self.eps,self.shares)

    def test_ads_eps_cannot_multiply_ordinary_share_count(self):
        self.shares['security_id']='issuer:ordinary'
        with self.assertRaises(ValueError): earnings_from_eps(self.eps,self.shares)

if __name__=='__main__': unittest.main()
