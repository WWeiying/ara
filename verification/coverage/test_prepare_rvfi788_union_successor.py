import copy
import re
import unittest
import prepare_rvfi788_union_successor as r


class RVFIUnion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c=r.life.read_bound(r.BASE/'config.json',r.BASE_CONFIG_SHA)
        cls.q=r.life.read_bound(r.CAPTURE/'capture-result.json',r.CAPTURE_SHA)
        cls.rvfi=r.life.read_bound(r.CAPTURE/'config.json',cls.q['config_seal'])
        cls.text=(r.BASE/'combined.el').read_text()+(r.CAPTURE/'first.el').read_text()

    def test_actual04_complete_boundary(self):
        r.qualification_gate(self.q,self.rvfi)
        wrong=copy.deepcopy(self.q);wrong['protected_objects']=417
        with self.assertRaises(Exception):r.qualification_gate(wrong,self.rvfi)

    def test_actual_whole_and_288_paired_directions_union(self):
        result=r.records(self.text,self.c,self.rvfi)
        self.assertEqual(result['retained'],self.c['expected_union'])
        self.assertEqual(len(result['rvfi788']),788)
        text=(r.CAPTURE/'first.el').read_text()
        pairs={m[1] for m in re.finditer(r'^Toggle 0to1 (\S+)',text,re.M)}
        self.assertEqual(len(pairs),288)

    def test_incomplete_direction_pair_rejected(self):
        text=(r.BASE/'combined.el').read_text()+re.sub(
            r'^Toggle 1to0[^\n]*\n','',(r.CAPTURE/'first.el').read_text(),count=1,flags=re.M)
        with self.assertRaises(Exception):r.records(text,self.c,self.rvfi)

    def test_full_five_stage1206_metadata(self):
        rows=[r.native.inventory(r.CAPTURE,self.rvfi,s) for s in ('before','selected','reset','reloaded','final')]
        self.assertEqual(len(rows[0]),1206)
        self.assertTrue(all(v==rows[0] for v in rows))

    def test_actual_both_qualified_families_keep_all_retained_policies(self):
        q=r.life.read_bound(r.CVA6/'capture-result.json',r.CVA6_SHA)
        c=r.life.read_bound(r.CVA6/'config.json',q['config_seal']);r.cva6_gate(q,c)
        result=r.records(self.text+(r.CVA6/'first.el').read_text(),self.c,self.rvfi,c)
        self.assertEqual(result['retained'],self.c['expected_union'])
        self.assertEqual(len(result['rvfi788']),788)
        self.assertEqual(len(result['cva6rvfi457']),457)

    def test_cva6_no_arrays_or_child_scope_expansion(self):
        q=r.life.read_bound(r.CVA6/'capture-result.json',r.CVA6_SHA)
        c=r.life.read_bound(r.CVA6/'config.json',q['config_seal'])
        wrong=copy.deepcopy(q);wrong['protected_arrays']=30
        with self.assertRaises(Exception):r.cva6_gate(wrong,c)
        rows=[r.cva6.inventory(r.CVA6,c,s)[0] for s in r.cva6.STAGES]
        self.assertEqual(len(rows[0]),1772);self.assertTrue(all(v==rows[0] for v in rows))


if __name__=='__main__':unittest.main()
