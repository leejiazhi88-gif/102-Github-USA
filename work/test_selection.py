import unittest
from build_selection_sheet import choose

class SelectionTests(unittest.TestCase):
    def test_inclusive_threshold_and_group_top_two(self):
        rows=[{'symbol':'A','group':'g1','cap':30e9},{'symbol':'B','group':'g1','cap':29e9},{'symbol':'C','group':'g1','cap':28e9},{'symbol':'D','group':'g2','cap':40e9},{'symbol':'E','group':'g2','cap':35e9},{'symbol':'F','group':'g2','cap':31e9}]
        got=choose(rows)
        self.assertEqual({x['symbol'] for x in got},{'A','B','D','E','F'})
        self.assertIn('补足',next(x['reason'] for x in got if x['symbol']=='B'))
    def test_both_below_threshold_still_take_two(self):
        got=choose([{'symbol':s,'group':'g','cap':c} for s,c in [('A',1e9),('B',2e9),('C',3e9)]])
        self.assertEqual([x['symbol'] for x in got],['C','B'])
    def test_ties_deterministic(self):
        got=choose([{'symbol':s,'group':'g','cap':2e9} for s in ['C','B','A']])
        self.assertEqual([x['symbol'] for x in got],['A','B'])

if __name__=='__main__':unittest.main()
