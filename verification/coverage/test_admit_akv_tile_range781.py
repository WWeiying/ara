import copy
import json
import unittest
import admit_akv_tile_range781 as admit


class Gates(unittest.TestCase):
    def setUp(self):
        self.q=admit.life.read_bound(admit.QUAL/'qualification.json',admit.Q_SHA)
        self.docs=[json.loads((admit.QUAL/n).read_bytes()) for n in ('scalar.json','vector.json','contract.json','native-capture.json','lifecycle.json','perf.json')]
        self.g=json.loads((admit.QUAL/'toggle-gain780.json').read_bytes())

    def test_actual_sealed_qualification(self): admit.qualification(self.q,*self.docs)
    def test_actual_measured_gain(self): admit.gain_gate(self.g)

    def test_wrong_qualification(self):
        q=dict(self.q,baseline_tests=779)
        with self.assertRaises(ValueError): admit.qualification(q,*self.docs)

    def test_scalar_skip(self):
        docs=copy.deepcopy(self.docs); docs[0]['skipped_retirements']=1
        with self.assertRaises(ValueError): admit.qualification(self.q,*docs)

    def test_rejected_VRF_write(self):
        docs=copy.deepcopy(self.docs); docs[1]['rejected_write_bytes']=1
        with self.assertRaises(ValueError): admit.qualification(self.q,*docs)

    def test_extra_exception(self):
        docs=copy.deepcopy(self.docs); docs[2]['exceptions']=4
        with self.assertRaises(ValueError): admit.qualification(self.q,*docs)

    def test_truncated_capture(self):
        docs=copy.deepcopy(self.docs); docs[3]['accepted64_indices'][0]=0xffff
        with self.assertRaises(ValueError): admit.qualification(self.q,*docs)

    def test_wrong_validation(self):
        docs=copy.deepcopy(self.docs); docs[4]['commands'][0]['validation_error']=3
        with self.assertRaises(ValueError): admit.qualification(self.q,*docs)

    def test_payload_read_fault(self):
        docs=copy.deepcopy(self.docs); docs[5][0]['read_payload_bytes']=128
        with self.assertRaises(ValueError): admit.qualification(self.q,*docs)

    def test_missing_measured_direction(self):
        g=copy.deepcopy(self.g); g['requested_tile_new_indices'].pop()
        with self.assertRaises(ValueError): admit.gain_gate(g)

    def test_bad_toggle_checksum(self):
        g=copy.deepcopy(self.g); g['single']['checksum']='1'
        with self.assertRaises(ValueError): admit.gain_gate(g)

    def test_typed_exact_and_offset_drift(self):
        row=dict(name='requested_tile_start_q',left='63',right='0',serialized_offset=4238,
            logical_width=64,portnode='0',excluded='0',missing_coordinates=self.g['requested_tile_new_indices'])
        self.assertEqual(admit.typed_target([row],self.g),row)
        for key,value in [('serialized_offset',4239),('logical_width',32),('excluded','1'),('portnode','1')]:
            with self.subTest(key=key),self.assertRaises(ValueError): admit.typed_target([dict(row,**{key:value})],self.g)
        with self.assertRaises(ValueError): admit.typed_target([row,row],self.g)

    def test_actual_full_OR_prefix(self):
        base=admit.life.read_bound(admit.BASE/'admission-manifest.json',admit.BASE_SHA)
        before=admit.life.read_bound(admit.BASE/'combined-bits.json',base['output_pins'][str(admit.BASE/'combined-bits.json')])
        single=json.loads((admit.QUAL/'single-bits.json').read_bytes())
        after=admit.full_union(before,single)
        self.assertEqual(after['tests'][:780],before['tests']); self.assertEqual(len(after['tests']),781)
        wrong=copy.deepcopy(single); wrong['tests']=[before['tests'][0]]
        with self.assertRaises(ValueError): admit.full_union(before,wrong)


if __name__=='__main__': unittest.main()
