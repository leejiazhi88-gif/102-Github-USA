import datetime as dt,unittest
from annual_profit_fields import estimate,reported_annual,apply_selection,eastmoney_annual

class AnnualProfitTests(unittest.TestCase):
    def fixture(self):
        return {'symbol':'X','currency':'USD','eps':2,'source':'eps'},{'symbol':'X','shares':1e8,'source':'shares'}
    def test_direct_shares_and_negative_zero_eps(self):
        eps,shares=self.fixture()
        for value in (2,0,-3):
            eps['eps']=value;self.assertEqual(estimate(eps,shares,'X')[0],value)
    def test_never_derive_shares_from_cap_and_price(self):
        eps,shares=self.fixture();shares.pop('shares');shares.update(price=10,cap=1e9)
        self.assertIsNone(estimate(eps,shares,'X')[0])
    def test_known_mismatches_stop_calculation(self):
        for field,value,target in [('symbol','Y','eps'),('currency','TWD','eps'),('symbol','Y','shares'),('per_share_basis_mismatch',True,'shares')]:
            eps,shares=self.fixture();(eps if target=='eps' else shares)[field]=value
            self.assertIsNone(estimate(eps,shares,'X')[0])
    def annual(self):
        return {'ok':True,'url':'api?frequency=1','retrieved_utc':'date','data':{'data':{'symbol':'X','incomeStatementTable':{'headers':{'value1':'Period Ending:','value2':'2/1/2026'},'rows':[{'value1':'Net Income Applicable to Common Shareholders','value2':'$1,000,000'}]}}}},{'ok':True,'usd_thousands_label':True,'url':'page','retrieved_utc':'date'}
    def test_reported_annual_maps_53_week_end(self):
        env,page=self.annual();result=reported_annual(env,page,'X',1,dt.date(2026,11,9))
        self.assertEqual(result[2026]['value'],10)
    def test_no_future_actual_or_unverified_units_or_quarter(self):
        env,page=self.annual()
        self.assertEqual(reported_annual(env,page,'X',1,dt.date(2026,1,1)),{})
        self.assertEqual(reported_annual(env,{},'X',1,dt.date(2026,11,9)),{})
        env['data']['data']['incomeStatementTable']['headers']['value1']='Quarterly Ending:'
        self.assertEqual(reported_annual(env,page,'X',1,dt.date(2026,11,9)),{})
    def test_eastmoney_requires_full_year_usd_and_published_us_security(self):
        row={'SECURITY_CODE':'X','SECUCODE':'X.N','DATE_TYPE_CODE':'001','CURRENCY_ABBR':'USD','START_DATE':'2025-10-01','REPORT_DATE':'2026-09-30','NOTICE_DATE':'2026-11-04','PARENT_HOLDER_NETPROFIT':3e8}
        env={'url':'source','retrieved_utc':'date','data':{'result':{'data':[row]}}}
        self.assertEqual(eastmoney_annual(env,'X',9,dt.date(2026,11,9))[2026]['value'],3)
        for field,value in [('DATE_TYPE_CODE','007'),('CURRENCY_ABBR','EUR'),('NOTICE_DATE','2026-12-01'),('START_DATE','2026-07-01'),('SECUCODE','X.HK'),('SECURITY_CODE','Y')]:
            original=row[field];row[field]=value
            self.assertEqual(eastmoney_annual(env,'X',9,dt.date(2026,11,9)),{})
            row[field]=original
    def test_overlay_only_target_columns_and_idempotent(self):
        rows=[['head']*90,['v']*90];rows[1][3]='X'
        records={'X':{'years':{str(y):{'status':'actual' if y==2026 else 'estimate','value':y} for y in (2026,2027,2028)},'note':'source'}}
        result,red,black=apply_selection(rows,records)
        self.assertTrue(all(rows[i][j]==result[i][j] for i in range(2) for j in range(90) if j not in (14,15,16,51)))
        self.assertEqual(red,[(2,15),(2,16)]);self.assertEqual(black,[(2,14)])
        self.assertEqual(apply_selection(result,records)[0],result)
if __name__=='__main__':unittest.main()
