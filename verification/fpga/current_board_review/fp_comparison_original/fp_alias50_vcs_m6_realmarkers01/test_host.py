"""Narrow genuine-ELF marker successor Host; no DUT or reference execution."""
import importlib.util
import sys
import time
import unittest
from pathlib import Path
sys.dont_write_bytecode=True
import replay
from replay import checker as c
from newscope import *

def private(name,path):
    spec=importlib.util.spec_from_file_location(name,path)
    mod=importlib.util.module_from_spec(spec);sys.modules[name]=mod;spec.loader.exec_module(mod)
    return mod

old_checker=private('sealed_alias50_false_begin_checker',OLD/'checker.py')
old_host=private('sealed_alias50_host_witnesses',OLD/'test_host.py')

class Markers(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.entry=replay.cases()[0]
        cls.elf=Path(cls.entry['elf'])
        cls.lines=cls.entry['pass_markers']+[c.common.SUCCESS,'$finish']
        cls.console='\n'.join(cls.lines)+'\n'

    def test_actual_wrapper_and_elf_marker_contract(self):
        wrapper=REF/'soc'/(NAME+'_main.c')
        source=wrapper.read_text();binary=self.elf.read_bytes()
        self.assertEqual(c.sha(self.elf),c.read(READY)['soc_elf_sha256'])
        self.assertNotIn('BOARD_CASE_BEGIN',source)
        self.assertNotIn(b'BOARD_CASE_BEGIN',binary)
        self.assertEqual(self.entry['pass_markers'],
            [MARKER,'BOARD_CASE_PASS '+NAME,'BOARD_REPLAY_PASS'])
        # Original C prints the FP marker via separate text/num calls.
        case=REF/'prepared'/NAME/'case.c'
        original=case.read_text()
        for literal in (b'RVV_FP_COMPARE_PASS sew=',b' cases=',b' errors='):
            self.assertTrue(literal in binary, literal.decode())
        self.assertIn('num(SEW)',original)
        self.assertIn('if(cases==50)goto prefix_done;',original)
        self.assertIn('num(cases)',original)
        self.assertIn('num(errors)',original)
        for marker in self.entry['pass_markers'][1:]:
            self.assertTrue(marker.encode() in binary, marker)
        self.assertIn('BOARD_CASE_PASS '+NAME,source)
        self.assertIn('BOARD_REPLAY_PASS',source)

    def test_genuine_no_begin_discriminates_predecessor(self):
        c.console_gate(self.console)
        with self.assertRaisesRegex(ValueError,'BOARD_CASE_BEGIN'):
            old_checker.console_gate(self.console)

    def test_each_real_marker_missing_duplicate_and_wrong(self):
        for line in self.lines:
            with self.subTest(marker=line):
                with self.assertRaises(ValueError):
                    c.console_gate(self.console.replace(line+'\n',''))
        for line in self.lines[:-1]:
            with self.assertRaises(ValueError):c.console_gate(self.console+line+'\n')
        for before,after in [(MARKER,MARKER.replace('cases=50','cases=49')),
            ('BOARD_CASE_PASS '+NAME,'BOARD_CASE_PASS wrong'),
            ('BOARD_REPLAY_PASS','BOARD_REPLAY_PASS wrong')]:
            with self.assertRaises(ValueError):c.console_gate(self.console.replace(before,after))
        with self.assertRaises(ValueError):c.console_gate(self.console,'historical_wrong')

    def test_raw_failure_veto_preserved(self):
        for veto in ('FAIL','DETAIL','ABORT','ABORTED','BOARD_CASE_FAIL '+NAME,
                     'BOARD_REPLAY_VLEN_FAIL','Core Test *** FAILED ***'):
            with self.assertRaises(ValueError):c.console_gate(self.console+veto+'\n')

    def test_full_immutable_source_scope_specification(self):
        plan=c.read(OLD/'prepared01/plan.json')
        self.assertEqual(c.specification(self.elf),plan['specs'][NAME])
        self.assertEqual(replay.cases(),plan['cases'])
        self.assertIs(c.source.audit,old_checker.source.audit)
        host=c.read(OLD/'host02.json')
        self.assertEqual((host['tests'],host['failures'],host['errors']),(9,0,0))
        c.common.base.verify_pins(host['pins'])
        self.assertEqual(EVENTS,{'retire','cvx_req','cvx_resp','arch_start','uop_alloc','uop_done'})

if __name__=='__main__':
    started=time.monotonic()
    suite=unittest.defaultTestLoader.loadTestsFromTestCase(Markers)
    for name in ('test_actual_frozen_parent_monitor_before_early_postcheck0_17',
                 'test_timeout_negative_preserved_before_metadata'):
        suite.addTest(old_host.Gates(name))
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    paths=[HERE/f for f in ('newscope.py','checker.py','replay.py','test_host.py')]
    paths += [OLD/f for f in ('newscope.py','model.py','elf.py','dut_strict.py','checker.py','replay.py',
                             'test_host.py','host02.json')]
    paths += [REF/'soc'/(NAME+'_main.c'),REF/'prepared'/NAME/'case.c',Path(replay.cases()[0]['elf'])]
    replay.durable(HERE/replay.HOST_REPORT,dict(
        status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        elapsed_s=time.monotonic()-started,pins={str(p):c.sha(p) for p in paths},
        inherited_full_source_host=str(OLD/'host02.json'),actual_elf_no_BEGIN=True,
        actual_frozen_parent_postcheck_codes=[0,17],timeout_negative_code=-9,
        DUT_started=False,reference_started=False))
    raise SystemExit(not result.wasSuccessful())
