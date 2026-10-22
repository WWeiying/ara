"""Correct only m2-specific setter assertion; inherit all other actual tests."""
from copy import deepcopy
import unittest
import checker as c
from host_records import Builder
import host_gate

class CorrectedFixture(unittest.TestCase):
    def test_actual_m4_SD_setter_and_all_skipped_assertions(self):
        spec=c.specification();b=Builder(spec)
        for pc,insn,size,offset in spec['init_stores']:
            desc=c.memory_op(insn)
            self.assertEqual((desc['kind'],desc['size'],desc['register']),('write',8,15))
            self.assertEqual(spec['source_lifecycle']['asm'][str(pc)]['args'].split(',')[0],'a5')
            self.assertIn(desc['register'],b.setters)
            rows=list(b.write(spec['backend']['symbols']['out']+offset,91,size,pc))
            self.assertEqual(int(rows[-1]['mem_wdata'],16),0x5b)
            self.assertEqual(rows[-1]['mem_wmask'],'ff')
        summary=c.read(c.HERE/'host02.json')['full_positive_summary']
        self.assertEqual(spec['init_stores'][0][2],8)
        self.assertEqual(summary['FP_input_stores'],241920)
        self.assertEqual(summary['mask_clear_stores'],35280)
    def test_preserved_full_positive_and_only_fixture_failure(self):host_gate.verify_old()
    def test_extra_or_other_failure_rejected(self):
        host=c.read(c.HERE/'host02.json');exit=c.read(c.HERE/'host02_process_exit.json');log=(c.HERE/'host02.log').read_text()
        for h,l in ((dict(host,errors=1),log),(host,log.replace('FAIL: test_actual_u64_constant_setter','FAIL: test_real_data_error'))):
            with self.assertRaises(ValueError):host_gate.old_outcome(h,exit,l)
    def test_partial_scope_or_missing_owner_rejected(self):
        for field in ('full_positive_summary','owner_summary'):
            host=c.read(c.HERE/'host02.json');host[field]=dict(host[field]);key='calls' if field=='full_positive_summary' else 'required_target_owners'
            host[field][key]-=1
            with self.assertRaises(ValueError):host_gate.old_outcome(host,c.read(c.HERE/'host02_process_exit.json'),(c.HERE/'host02.log').read_text())
    def test_actual_builder_console_component_evidence(self):
        p=c.read(c.HERE/'console_fixture_probe01.json')
        self.assertEqual(p['status'],'PASS_ACTUAL_BUILDER_CSV_UART_COMPONENT_NOT_DUT')
        self.assertEqual(p['positive']['source_sha256'],c.sha(c.HERE/'host_records.py'))
        self.assertLess(p['positive']['core_elapsed_s'],1)
        self.assertGreater(p['positive']['actual_events'],p['positive']['uart_bytes'])
        c.console_gate(p['positive']['decoded_console'],simulator=False)

if __name__=='__main__':
    import replay as r
    command=c.read(c.HERE/'host03_command.json');pins=command['input_pins'];c.common.base.verify_pins(pins)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(CorrectedFixture))
    c.common.base.verify_pins(pins)
    r.durable(c.HERE/'host03.json',dict(status='PASS_NARROW_HOST_SUCCESSOR' if result.wasSuccessful() else 'FAIL_NARROW_HOST_SUCCESSOR',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),pins=pins,pins_unchanged=True,
        underlying_full_host_actual_exit=1,underlying_full_host_not_overwritten=True))
    raise SystemExit(not result.wasSuccessful())
