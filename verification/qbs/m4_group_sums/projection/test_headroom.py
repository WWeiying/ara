import copy
import unittest
from analyze_headroom import normalized
from test_analyze_pipeline import fixture


class CurrentHeadroom(unittest.TestCase):
    def pair(self):
        text,rows=fixture()
        for row in rows:
            row['candidate']=row.pop('reuse')
            row.update(hits=2,misses=1,stores=1)
        text=text.replace('M4_QKV_','M4_SUMS_QKV_').replace(' reuse=',' candidate=')
        text=text.replace('hits=0 misses=0 stores=0','hits=2 misses=1 stores=1')
        return text,rows

    def test_preserves_activity_and_cache_scope(self):
        text,rows=self.pair()
        result=normalized(text,rows)
        self.assertEqual(result['optimized_pair']['compute_no_issue'],768)
        self.assertTrue(all(t['trial']['hits']==2 for t in result['trials']))

    def test_receipt_and_order_disagreement(self):
        text,rows=self.pair()
        changed=copy.deepcopy(rows);changed[0]['prep']+=1
        with self.assertRaises(ValueError):normalized(text,changed)
        with self.assertRaises(ValueError):normalized(text.replace('candidate=1','candidate=0',1),rows)
        with self.assertRaises(ValueError):normalized(text+'\n'+text,rows)


if __name__=='__main__':unittest.main()
