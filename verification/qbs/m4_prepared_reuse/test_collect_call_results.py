import copy
import importlib.util
from pathlib import Path
import unittest

spec=importlib.util.spec_from_file_location('call_summary',Path(__file__).with_name('collect_call_results.py'))
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)


def receipt(kind):
    result=dict(state='PASS',performance_measured=True,post_pins_match=True,
                simulations_launched=1,independent_protocol_checked=True)
    if kind=='projection':
        trials=[dict(id=i,reuse=m,total=t,errors=0) for i,(m,t) in enumerate(zip((0,1,1,0),(100,70,80,110)))]
        measured=dict(state='PASS',performance_measured=True,trials=trials,
                      traffic=dict(commands=256,result_bytes=131072))
    else:
        trials=[dict(trial=i,enabled=m,cycles=t,commands=8,values=128)
                for i,(m,t) in enumerate(zip((0,1,1,0),(100,110,120,100)))]
        measured=dict(state='COMPACT_ABBA_AND_WORK_CHECKED',trials=trials,
                      on_target_full_numerical_checks=True,same_elf=True,hardware_records=[{}]*32)
    result['measured']=measured;return result


class CallResults(unittest.TestCase):
    def test_exact_pairs_not_average_of_ratios(self):
        out=module.summarize(receipt('projection'),'projection')
        self.assertEqual((out['baseline_cycles'],out['candidate_cycles']),(210,150))
        self.assertEqual(out['speedup'],1.4);self.assertFalse(out['whole_model'])
    def test_regression_is_not_hidden(self):
        out=module.summarize(receipt('attention'),'attention')
        self.assertFalse(out['improved']);self.assertLess(out['cycle_reduction'],0)
    def test_incomplete_or_qemu_rejected(self):
        for key,value in (('state','RUNNING'),('state','FAIL'),('performance_measured',False),
                          ('post_pins_match',False),('simulations_launched',0)):
            data=receipt('projection');data[key]=value
            with self.subTest(field=key),self.assertRaises(ValueError):module.summarize(data,'projection')
    def test_wrong_work_rejected(self):
        data=receipt('projection');data['measured']['traffic']['commands']=255
        with self.assertRaises(ValueError):module.summarize(data,'projection')
        data=receipt('attention');data['independent_protocol_checked']=False
        with self.assertRaises(ValueError):module.summarize(data,'attention')
    def test_order_and_partial_results_rejected(self):
        for kind in ('projection','attention'):
            data=receipt(kind)
            for trials in (data['measured']['trials'][:3],list(reversed(data['measured']['trials']))):
                bad=copy.deepcopy(data);bad['measured']['trials']=trials
                with self.subTest(kind=kind),self.assertRaises(ValueError):module.summarize(bad,kind)


if __name__=='__main__':unittest.main()
