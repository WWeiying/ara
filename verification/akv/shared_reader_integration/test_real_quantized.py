from pathlib import Path
import unittest
from run_real_quantized import counter_flags


class CounterPolicyTests(unittest.TestCase):
    def command(self, kind='q4_0'):
        return [Path('/image/simv'), '-no_save', '+PRELOAD=/input/test.elf',
                '+TESTCASE=shared_real_quant_'+kind, '+AKV_PERF', '+AKV_SUMMARY']

    def test_qbs_only_both_profiles(self):
        for kind in ('q4_0','q8_0'):
            command=self.command(kind)
            result=counter_flags(command,'RUNNING')
            self.assertEqual(result,command[:-2]+['+QBS_PERF'])
            self.assertNotIn('+AKV_SUMMARY',result)
            self.assertNotIn('+AKV_PERF',result)

    def test_non_simulator_phase_unchanged(self):
        command=['python3','checker.py']
        self.assertEqual(counter_flags(command,'CHECKING'),command)

    def test_wrong_command_rejected(self):
        for command in (self.command()+['+QBS_PERF'],self.command()+['+AKV_SUMMARY'],
                        self.command('bad'),['simv','+AKV_PERF']):
            with self.assertRaises(ValueError):
                counter_flags(command,'RUNNING')


if __name__=='__main__':
    unittest.main()
