import datetime as dt,unittest
from forecast_fields import annual_forecasts,reference_pe,usd_actuals,apply_rows

class ForecastFieldsTests(unittest.TestCase):
    def test_year_is_period_end_not_current_calendar(self):
        envelope={'ok':True,'url':'source','retrieved_utc':'date','data':{'data':{'symbol':'nvda','yearlyForecast':{'rows':[{'fiscalEnd':'Jan 2027','consensusEPSForecast':9.3}]}}}}
        records,status=annual_forecasts(envelope,'NVDA')
        self.assertEqual(set(records),{2027});self.assertEqual(records[2027]['eps'],9.3)
    def test_price_eps_does_not_require_shares(self):
        p={'symbol':'NVDA','currency':'USD','price':217.94,'source':'quote'};e={'symbol':'NVDA','eps':9.3,'source':'forecast','period':'Jan 2027','currency':None}
        value,status=reference_pe(p,e)
        self.assertAlmostEqual(value,217.94/9.3);self.assertIn('not_independently_verified',status)
    def test_known_currency_mismatch_blocked(self):
        value,status=reference_pe({'symbol':'TSM','currency':'USD','price':400,'source':'x'},{'symbol':'TSM','eps':50,'currency':'TWD','period':'Dec 2026','source':'x'})
        self.assertIsNone(value);self.assertEqual(status,'currency_mismatch')
    def test_us_symbol_does_not_override_identity_mismatch(self):
        self.assertEqual(reference_pe({'symbol':'TSM','currency':'USD'},{'symbol':'2330.TW'})[1],'security_mismatch')
    def test_negative_eps_not_positive_pe(self):
        p={'symbol':'X','price':5,'currency':'USD','source':'s'};e={'symbol':'X','eps':-1,'source':'s','period':'Dec 2026'}
        self.assertEqual(reference_pe(p,e)[1],'nonpositive_eps')
    def test_usd_unit_evidence_required(self):
        e={'ok':True,'url':'api','retrieved_utc':'date','data':{'data':{'symbol':'TSM','incomeStatementTable':{'headers':{'value1':'period','value2':'12/31/2025'},'rows':[{'value1':'Net Income Applicable to Common Shareholders','value2':'$53,949,600'}]}}}}
        self.assertEqual(usd_actuals(e,{'ok':True},'TSM',dt.date(2026,11,3)),{})
        result=usd_actuals(e,{'ok':True,'usd_thousands_label':True,'url':'page'},'TSM',dt.date(2026,11,3))
        self.assertAlmostEqual(result[2025]['net_income_100m_usd'],539.496)
    def test_missing_annual_rows_distinguished(self):
        self.assertEqual(annual_forecasts({'ok':True,'data':{'data':{'symbol':'X','yearlyForecast':None}}},'X')[1],'provider_no_annual_rows')
    def test_provider_symbol_error_not_network_error(self):
        envelope={'ok':False,'http':'200','data':{'data':None,'status':{'rCode':400,'bCodeMessage':[{'errorMessage':'Symbol not exists.'}]}}}
        self.assertEqual(annual_forecasts(envelope,'KVUE')[1],'provider_symbol_unavailable')
    def test_no_total_forecast_income_created(self):
        rows=[['h']*120,['']*120];rows[1][3]='X';rows[1][13]='未取得同口径美股来源数据';rows[1][5]=100
        f={'symbol':'X','period':'Jan 2027','eps':10,'source':'s','estimates':3,'low':8,'high':12,'currency':None}
        r={'X':{'forecasts':{'2027':f},'actuals':{},'price':{'symbol':'X','currency':'USD','price':100,'source':'s'},'forecast_status':'available','forecast_url':'s'}}
        result,red=apply_rows(rows,'main',r)
        self.assertEqual(result[1][8],10);self.assertEqual(result[1][13],'有预测EPS，无直接预测净利润');self.assertIn((1,8),red)

if __name__=='__main__':unittest.main()
