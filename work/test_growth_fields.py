import datetime as dt,unittest
from growth_fields import growth,table_amount,historical_reports,apply_selection
class GrowthTests(unittest.TestCase):
    def amount(self,x,c='USD',s='actual',b='GAAP'):return {'amount':x,'currency':c,'status':s,'basis':b}
    def test_positive_actual_and_forecast_reference(self):
        r=growth(self.amount(120),self.amount(100));self.assertEqual(r['value'],'20.00%');self.assertFalse(r['red'])
        r=growth(self.amount(120,s='estimate'),self.amount(100));self.assertEqual(r['value'],'20.00%');self.assertTrue(r['red'])
    def test_known_currency_mismatch_never_divides(self):
        self.assertEqual(growth(self.amount(100),self.amount(90,'KRW'))['kind'],'currency_mismatch')
        self.assertEqual(growth(self.amount(120,'CAD'),self.amount(100,'CAD'))['value'],'20.00%')
    def test_negative_base_states(self):
        self.assertEqual(growth(self.amount(5),self.amount(-10))['value'],'扭亏为盈')
        self.assertEqual(growth(self.amount(-5),self.amount(-10))['value'],'亏损收窄50.00%')
        self.assertEqual(growth(self.amount(-20),self.amount(-10))['value'],'亏损扩大100.00%')
        self.assertEqual(growth(self.amount(-5),self.amount(10))['value'],'转亏（利润变化-150.00%）')
    def test_zero_and_missing(self):
        self.assertEqual(growth(self.amount(5),self.amount(0))['value'],'由零转盈')
        self.assertEqual(growth(self.amount(0),self.amount(0))['kind'],'zero_base')
        self.assertEqual(growth(self.amount(None),self.amount(10))['kind'],'missing')
    def test_native_currency_is_explicit(self):
        self.assertEqual(table_amount('47.2亿加元（未换汇）'),(47.2,'CAD'))
        self.assertEqual(table_amount('429192.8700亿韩国元（未换汇）'),(429192.87,'KRW'))
        self.assertEqual(table_amount('未取得'),(None,None))
    def test_explicit_historical_fiscal_year_survives_changed_year_end(self):
        row={'SECURITY_CODE':'X','SECUCODE':'X.N','REPORT_TYPE':'2025/FY','DATE_TYPE_CODE':'001','CURRENCY_ABBR':'USD','START_DATE':'2024-08-01','REPORT_DATE':'2025-07-31','NOTICE_DATE':'2026-02-27','PARENT_HOLDER_NETPROFIT':1e8}
        env={'url':'source','retrieved_utc':'date','data':{'result':{'data':[row]}}}
        self.assertEqual(historical_reports(env,'X',dt.date(2026,11,9))[2025]['value'],1)
        row['START_DATE']='2025-05-01';self.assertEqual(historical_reports(env,'X',dt.date(2026,11,9)),{})
    def test_changed_annual_amounts_require_rebuild(self):
        rows=[['h']*90,['']*90];rows[1][3]='X';rows[1][14:17]=[1,2,3]
        rec={'bases':{},'values':['1%']*4,'red_offsets':[],'note':'source','periods':{str(y):self.amount(v) for y,v in zip((2026,2027,2028),(1,2,3))}}
        result,_,_=apply_selection(rows,{'X':rec});self.assertEqual(result[1][14:17],[1,2,3])
        rows[1][14]=5
        with self.assertRaises(ValueError):apply_selection(rows,{'X':rec})
if __name__=='__main__':unittest.main()
