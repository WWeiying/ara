import copy
import unittest
from run_real_runtime import compare_outputs


class RealRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.record={'trials':[dict(trial=i,checksum='1234',fcsr=1,vcsr=5,
                                  cycles=100,hardware_totals={'busy_cycles':80}) for i in range(4)]}

    def test_identical(self):
        result=compare_outputs(self.record,copy.deepcopy(self.record))
        self.assertTrue(result['per_call_counters_identical'])
        self.assertTrue(result['task_cycles_identical'])

    def test_latency_difference_recorded_not_hidden(self):
        other=copy.deepcopy(self.record)
        other['trials'][0]['cycles']+=1
        other['trials'][0]['hardware_totals']['busy_cycles']+=1
        result=compare_outputs(self.record,other)
        self.assertFalse(result['task_cycles_identical'])
        self.assertFalse(result['per_call_counters_identical'])

    def test_wrong_result_fails(self):
        other=copy.deepcopy(self.record)
        other['trials'][2]['checksum']='changed'
        with self.assertRaises(ValueError):
            compare_outputs(self.record,other)

    def test_incomplete_fails(self):
        with self.assertRaises(ValueError):
            compare_outputs(self.record,{'trials':[]})

    def test_quantized_output_and_command_records(self):
        record={'trials':[dict(trial=0,cycles=100,output_bits=[123,456],fcsr=1,vcsr=5)],
                'hardware_records':[dict(busy_cycles=10)]}
        result=compare_outputs(record,copy.deepcopy(record))
        self.assertFalse(result['per_call_counters_available'])
        self.assertIsNone(result['per_call_counters_identical'])
        self.assertTrue(result['command_counters_identical'])
        bad=copy.deepcopy(record)
        bad['hardware_records'][0]['busy_cycles']+=1
        self.assertFalse(compare_outputs(record,bad)['command_counters_identical'])


if __name__=='__main__':
    unittest.main()
