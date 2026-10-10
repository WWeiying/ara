import json
import unittest
import qualify_qbs_payload_phase763 as q


class TestQualification(unittest.TestCase):
    def test_actual_independent_gold_and_complete_elf(self):
        items=q.independent_native();self.assertEqual([len(i['result_bits']) for i in items],[64,64])
        v=q.view();symbols,data,sites=v.elf_view()
        self.assertEqual(len(sites),2)
        for phase in (0,1):self.assertEqual(len(q.full8.regions(phase,symbols,data,items)['actual']),4224)
    def test_mutated_native_source_rejected(self):
        w,a,g=q.recipe.fixture(0);b=bytearray(a);b[64+12+3]=0
        with self.assertRaises(ValueError):q.full8.unpack(w[64:944],b[76:2412])
    def prediction(self):return json.loads((q.runner.PRE/'target-prediction.json').read_bytes())
    def test_measured_not_automatic_prediction_pass(self):
        p=self.prediction();s={t['scope']:dict(checksum='3657545390',width=66340,bits='0x0') for t in p['targets']}
        self.assertEqual(sum(len(t['measured_new_coordinates']) for t in q.measured_targets(p,s)),0)
        for t in p['targets']:
            row=s[t['scope']];bits=int(row['bits'],16)
            for c in t['missing_serialized_coordinates']:bits|=1<<(66339-c)
            row['bits']=hex(bits)
        self.assertEqual(sum(len(t['measured_new_coordinates']) for t in q.measured_targets(p,s)),288)
    def test_wrong_checksum_and_bounds_rejected(self):
        p=self.prediction();s={t['scope']:dict(checksum='0',width=66340,bits='0x0') for t in p['targets']}
        with self.assertRaises(ValueError):q.measured_targets(p,s)
        for row in s.values():row['checksum']='3657545390'
        p['targets'][0]['missing_serialized_coordinates']=[-1,66340]
        with self.assertRaises(ValueError):q.measured_targets(p,s)


if __name__=='__main__':unittest.main()
