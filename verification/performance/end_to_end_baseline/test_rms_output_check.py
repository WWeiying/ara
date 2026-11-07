import unittest
import json

from check_rms_output import check, signature, activity
from test_rms_norm_check import fixture
from build_rms_output import replace_object, parent_acceptance, ACCEPTED

SUMMARY = 'RMS_OUTPUT_CHECK cases=155 vector_calls=110 empty_calls=5 scalar_fallbacks=40 errors=0 digest=12345'


class RMSOutputCheckTests(unittest.TestCase):
    def test_requires_old_and_new_results_even_when_slower(self):
        text,p,d = fixture()
        result = check(SUMMARY+'\n'+text, p, d)
        self.assertEqual(result['cases'][0]['call_speedup'], 0.5)
        self.assertNotIn('cycles', str(signature(result)))
        for a,b in (('cases=155','cases=154'), ('errors=0','errors=1'), ('vector_calls=110','vector_calls=0'),
                    ('digest=12345','digest=4294967296')):
            with self.subTest(a=a), self.assertRaises(ValueError): check(SUMMARY.replace(a,b)+'\n'+text,p,d)
        with self.assertRaises(ValueError): check(text,p,d)
        with self.assertRaises(ValueError): check(SUMMARY+'\n'+SUMMARY+'\n'+text,p,d)

    def test_cycle_independent_signature_keeps_observed_state(self):
        text,p,d = fixture()
        a = check(SUMMARY+'\n'+text,p,d)
        b = check(SUMMARY+'\n'+text.replace('cycles=200','cycles=300'),p,d)
        self.assertEqual(signature(a), signature(b))
        b['output_checks']['digest'] += 1
        self.assertNotEqual(signature(a), signature(b))

    def test_actual_new_stores_required_alongside_ordered_reductions(self):
        header = 'cycle,event,arch_seq,insn,vl,vstart,nr_lanes,vlen_bits\n'
        insn = (0b110011<<26)|(1<<25)|(1<<12)|0x57
        trace = header+'0,config,0,00000000,0,0,4,1024\n'+''.join(
            f'{i},alloc,{i},{insn:08x},128,0,4,1024\n' for i in range(288))+''.join(
            f'{i+1000},alloc,{i+1000},02006027,128,0,4,1024\n' for i in range(458))
        self.assertEqual(activity(trace)['vector_output_store_allocations'],458)
        with self.assertRaises(ValueError): activity(trace.rsplit('\n',2)[0]+'\n')

    def test_object_replacement_is_exactly_one_member(self):
        self.assertEqual(replace_object(['a.o','b.o'],'a.o','new.o'), ['new.o','b.o'])
        for link in (['b.o'],['a.o','a.o']):
            with self.assertRaises(ValueError): replace_object(link,'a.o','new.o')

    def test_actual_parent_receipt_schema_is_used(self):
        value = json.loads(ACCEPTED.read_text())
        parent_acceptance(value)
        value['order_sensitive_sum_cases'] = 0
        with self.assertRaises(ValueError): parent_acceptance(value)


if __name__ == '__main__': unittest.main()
