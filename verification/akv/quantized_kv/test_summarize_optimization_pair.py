import copy
import unittest
from summarize_optimization_pair import numeric_summary


def receipt(mechanism):
    prefill = mechanism == 'prefill'
    field = 'shared' if prefill else 'candidate'
    candidate_key = 'shared_cycles' if prefill else 'candidate_cycles'
    return dict(state='PASS', performance_measured=True,
        independent_protocol_checked=True, post_pins_match=True,
        measured=dict(paired_bitexact=True, baseline_cycles=202, speedup=202/101,
            outputs_per_trial=1024 if prefill else 256,
            commands_per_trial=4 if prefill else 1, scope='test fixture',
            trials=[dict(cycles=c, **{field:v}) for c,v in
                    zip((200,100,102,204),(0,1,1,0))], **{candidate_key:101}))


class SummaryTest(unittest.TestCase):
    def test_pair(self):
        for mechanism in ('prefill', 'register-pv'):
            got = numeric_summary(receipt(mechanism), mechanism)
            self.assertEqual(got['speedup'], 2)
            self.assertEqual(got['cycle_reduction_percent'], 50)
            self.assertFalse(got['whole_model'])

    def test_gate_and_scope_mutations(self):
        for key in ('performance_measured','independent_protocol_checked','post_pins_match'):
            r=receipt('prefill');r[key]=False
            with self.subTest(key=key), self.assertRaises(ValueError):
                numeric_summary(r,'prefill')
        for key,value in [('speedup',3),('baseline_cycles',0),('shared_cycles',3),
                          ('outputs_per_trial',256),('paired_bitexact',False)]:
            r=receipt('prefill');r['measured'][key]=value
            with self.subTest(key=key), self.assertRaises(ValueError):
                numeric_summary(r,'prefill')
        for variant in ('incomplete','order','zero','failed'):
            r=copy.deepcopy(receipt('prefill'))
            if variant=='incomplete':r['measured']['trials'].pop()
            if variant=='order':r['measured']['trials'][1]['shared']=0
            if variant=='zero':r['measured']['trials'][0]['cycles']=0
            if variant=='failed':r['state']='FAIL'
            with self.subTest(variant=variant), self.assertRaises(ValueError):
                numeric_summary(r,'prefill')


if __name__ == '__main__':
    unittest.main()
