import unittest
import tempfile
import json
from pathlib import Path
from unittest.mock import patch
from provider_reliability import parse_em,parse_futu,num
from ttm_source import select
import ttm_source

class SourceTests(unittest.TestCase):
    def test_exact_field_not_generic_pe(self):
        r=parse_em({'rc':0,'data':{'diff':[{'f12':'SKHY','f13':105,'f9':11.22,'f115':9.14,'f2':164.7}]}})[0]
        self.assertEqual(r['pe_ttm'],9.14)
        self.assertIsNone(r['eps_ttm'])
    def test_missing_and_zero_no_fallback(self):
        for value in (None,0,'-','NaN'):
            r=parse_em({'rc':0,'data':{'diff':[{'f12':'TSM','f13':106,'f9':28.29,'f115':value}]}})[0]
            self.assertIsNone(r['pe_ttm'])
    def test_wrong_market_rejected(self):
        with self.assertRaises(ValueError):parse_em({'rc':0,'data':{'diff':[{'f12':'TSM','f13':105,'f115':20}]}})
    def test_negative_pe_preserved(self):
        r=parse_em({'rc':0,'data':{'diff':[{'f12':'INTC','f13':105,'f115':-42.78}]}})
        selected=select([{'ok':True,'provider':'eastmoney','records':r}])
        x=next(x for x in selected['records'] if x['symbol']=='INTC')
        self.assertEqual(x['pe_ttm'],-42.78);self.assertTrue(x['issues'])
    def test_no_tencent_fallback(self):
        s=select([{'ok':True,'provider':'tencent','records':[{'symbol':'SKHY','generic_pe':11.22}]}])
        x=next(x for x in s['records'] if x['symbol']=='SKHY')
        self.assertIsNone(x['pe_ttm'])
    def test_snapshot_conflict_retained(self):
        s=select([{'ok':True,'provider':'eastmoney','records':[{'symbol':'SKHY','pe_ttm':9.14,'quote_epoch':1234}]}])
        x=next(x for x in s['records'] if x['symbol']=='SKHY')
        self.assertTrue(any('长桥' in i for i in x['issues']));self.assertEqual(x['quote_epoch'],1234)
    def test_futu_identity_not_guess(self):
        with self.assertRaises(ValueError):parse_futu('window.__INITIAL_STATE__={"stock_info":{"stockCode":"TSM","marketLabel":"TW"}}','TSM')
    def test_failed_request_keeps_original_time(self):
        with tempfile.TemporaryDirectory() as directory:
            cache=Path(directory)/'selected.json'
            original={'fetch_status':'fresh_request','records':[{'symbol':'SKHY','pe_ttm':9.14,'quote_epoch':1234,'retrieved_utc':'old','issues':['conflict']}]}
            cache.write_text(json.dumps(original))
            with patch.object(ttm_source,'CACHE',cache),patch.object(ttm_source,'fetch',return_value={'ok':False,'http':'429','error':'rate limited'}):
                result=ttm_source.refresh()
            self.assertEqual(result['records'],original['records'])
            self.assertEqual(result['fetch_status'],'request_failed_using_last_success')

if __name__=='__main__':unittest.main()
