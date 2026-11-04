import datetime as dt,unittest
from quarter_fields import quarter_key,quarter_forecasts,actual_quarters,fiscal_month,extend_selection,HEADERS,archived_main_value

class QuarterFieldsTests(unittest.TestCase):
    def test_fiscal_year_not_calendar_year(self):
        self.assertEqual(quarter_key(dt.date(2026,4,26),1),'FY2027Q1')
        self.assertEqual(quarter_key(dt.date(2026,1,25),1),'FY2026Q4')
    def test_53_week_boundary(self):
        self.assertEqual(quarter_key(dt.date(2025,11,2),10),'FY2025Q4')
        self.assertEqual(quarter_key(dt.date(2026,9,3),8),'FY2026Q4')
    def test_no_forced_mapping_when_month_mismatches(self):
        self.assertIsNone(quarter_key(dt.date(2026,2,20),12))
    def test_negative_forecast_keeps_loss(self):
        env={'url':'source','retrieved_utc':'date','data':{'data':{'symbol':'X','quarterlyForecast':{'rows':[{'fiscalEnd':'Mar 2027','consensusEPSForecast':-2,'noOfEstimates':3}]}}}}
        result=quarter_forecasts(env,'X',12,{'symbol':'X','shares':1e8})
        self.assertEqual(result['FY2027Q1']['value'],-2)
        self.assertEqual(result['FY2027Q1']['status'],'estimate')
    def test_no_implicit_shares_and_wrong_currency(self):
        env={'url':'source','retrieved_utc':'date','data':{'data':{'symbol':'X','currency':'TWD','quarterlyForecast':{'rows':[{'fiscalEnd':'Mar 2027','consensusEPSForecast':2}]}}}}
        self.assertEqual(quarter_forecasts(env,'X',12,{'symbol':'X','shares':1e8})['FY2027Q1']['status'],'eps_only')
    def test_actual_units_and_quarter_marker(self):
        env={'url':'source','retrieved_utc':'date','data':{'data':{'symbol':'X','incomeStatementTable':{'headers':{'value1':'Quarterly Ending:','value2':'3/31/2026'},'rows':[{'value1':'Net Income Applicable to Common Shareholders','value2':'$1,200,000'}]}}}}
        self.assertEqual(actual_quarters(env,{},'X',12)[0],{})
        rows,_=actual_quarters(env,{'usd_thousands_label':True,'url':'page'},'X',12)
        self.assertEqual(rows['FY2026Q1']['value'],12)
        env['data']['data']['incomeStatementTable']['headers']['value1']='Period Ending:'
        self.assertEqual(actual_quarters(env,{'usd_thousands_label':True},'X',12)[0],{})
    def test_old_numeric_cell_is_not_a_future_actual(self):
        self.assertIsNone(archived_main_value('FY2027Q4',377.01,8))
        self.assertEqual(archived_main_value('FY2026Q4',377.01,8)['status'],'unverified_archive')
    def test_no_annual_divide_four(self):
        env={'data':{'data':{'symbol':'X','yearlyForecast':{'rows':[{'fiscalEnd':'Dec 2027','consensusEPSForecast':8}]}}}}
        self.assertEqual(quarter_forecasts(env,'X',12,{'shares':1e8}),{})
    def test_extension_preserves_existing_columns_and_is_idempotent(self):
        rows=[['head']*72,['v']*72];rows[1][3]='X'
        payload={'headers':HEADERS,'records':{'X':{'values':list(range(18)),'red_offsets':[0]}}}
        result,red=extend_selection(rows,payload)
        self.assertEqual(result[1][:72],rows[1]);self.assertEqual(len(result[0]),90)
        self.assertEqual(extend_selection(result,payload)[0],result);self.assertEqual(red,[(2,72)])

if __name__=='__main__':unittest.main()
