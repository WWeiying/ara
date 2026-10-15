"""Narrow successor contract: real metadata and typed pins, no simulator/raw."""
import re
import unittest
from scope import *
import replay_successor as r

class Tests(unittest.TestCase):
    def test_exact_successor_delta(self):
        old=(HERE/'replay.py').read_text()
        expected=old.replace(
            "pins=merge_pins(read(REF/'input_pins.json'),read(STAGE/'generated01/artifact_pins.json'),bindings)",
            "pins=merge_pins(read(REF/'input_pins.json'),read(STAGE/'generated01/artifact_pins.json'),\n                    {str(path):digest for path,digest in bindings.items()})")
        for a,b in [('replay.py','replay_successor.py'),('collect.py','collect_successor.py'),
                    ('exit_hook.py','exit_hook_successor.py')]:
            expected=expected.replace("HERE/'"+a+"'","HERE/'"+b+"'")
        self.assertEqual(expected,(HERE/'replay_successor.py').read_text())
        self.assertEqual((HERE/'collect.py').read_text().replace('import replay as r','import replay_successor as r'),
                         (HERE/'collect_successor.py').read_text())
        self.assertEqual((HERE/'exit_hook.py').read_text().replace('from replay import durable','from replay_successor import durable')
                         .replace("HERE/'collect.py'","HERE/'collect_successor.py'"),
                         (HERE/'exit_hook_successor.py').read_text())

    def test_all_real_pin_keys_and_values(self):
        ledger,repo,_=r.common.image_context(IMAGE)
        sources=[r.reference_pins(),r.owned_pins(),read(r.HOST)['pins'],r.common.image_pins(IMAGE,ledger,repo)]
        for source in sources:
            for key,value in source.items():
                self.assertIs(type(key),str)
                self.assertTrue(Path(key).is_absolute())
                self.assertIs(type(value),str)
                self.assertRegex(value,r'^[0-9a-f]{64}$')
        merged=r.merge_pins(*sources)
        self.assertEqual(merged[str(ELF)],ELF_SHA)
        self.assertNotIn(str(REF/'reference01/commits.log'),merged)

    def test_reference_schema_and_three_actual_exits(self):
        review=read(REVIEW);complete=read(REF/'reference01/COMPLETE.json')
        self.assertEqual(review['status'],'ACCEPTED_REFERENCE_FULL17920_SOURCE_ONLY_NOT_DUT')
        self.assertEqual(complete['status'],'REFERENCE_EXECUTOR_PASS_PENDING_TERMINAL_REVIEW_NOT_DUT')
        self.assertTrue(complete['input_pins_unchanged'])
        for key in ('actual_reference','actual_audit'):
            self.assertIs(type(complete[key]['actual_wait_exit']),int)
            self.assertEqual(complete[key]['actual_wait_exit'],0)
            self.assertIs(complete[key]['timed_out'],False)
        outer=read(REF/'execution_receipt01/outer.wait.json')
        self.assertIs(type(outer['actual_wait_exit']),int);self.assertEqual(outer['actual_wait_exit'],0)
        self.assertIs(outer['timed_out'],False)
        self.assertEqual(review['CAP'],16);self.assertEqual(review['vtype'],23)
        self.assertEqual(review['firmware_to_HTIF'],2941812)

    def test_conflicting_string_pin_still_rejected(self):
        self.assertEqual(r.merge_pins({'/a':'0'*64},{'/a':'0'*64}),{'/a':'0'*64})
        with self.assertRaises(ValueError):r.merge_pins({'/a':'0'*64},{'/a':'1'*64})

    def test_actual_stop_contract_uses_successors(self):
        c=r.service_contract()
        self.assertIs(c['RemainAfterExit'],False)
        self.assertEqual(c['exit_hook'],str(HERE/'exit_hook_successor.py'))
        self.assertEqual(c['collector'],str(HERE/'collect_successor.py'))
        self.assertEqual(c['collector_bound_s'],180)

def main():
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Tests))
    r.durable(HERE/'prepare_contract.json',dict(status='PASS_PREPARE_CONTRACT_NOT_DUT' if result.wasSuccessful() else 'NOT_PASS',
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
        pins=r.owned_pins(),DUT_started=False,reference_rerun=False))
    return int(not result.wasSuccessful())
if __name__=='__main__':raise SystemExit(main())
