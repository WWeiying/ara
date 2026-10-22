"""One corrected Host assertion; production observer and old receipts unchanged."""
import time
import unittest
from scope import *
from test_host import ready, helper_row
import replay

class Supplement(unittest.TestCase):
    def test_full_array_mask_upper_and_output_tail(self):
        for name,offset in [('mask',127),('output',129),('a',63),('b',63),('a',64),('b',4095)]:
            with self.subTest(name=name,offset=offset):
                c=ready();c.memory[c.a[name]+offset]^=1
                message='Unmodified unused backing BSS' if name in ('a','b') and offset>=64 else 'Full initialized '+name
                with self.assertRaisesRegex(ValueError,message):
                    c.consume(helper_row(c,0))

def main():
    prior=read(HERE/'host02.json');wait=read(HERE/'host02.wait.json')
    require(prior['tests']==35 and prior['failures']==1 and prior['errors']==0,'Exact prior34 passes/one assertion mismatch')
    require(type(wait['actual_wait_exit'])is int and wait['actual_wait_exit']==1 and wait['timed_out'] is False,
            'Preserve actual prior Host1, not DUT')
    log=(HERE/'host02.log').read_text()
    require(sha(HERE/'host02.log')==wait['log_sha256'] and
            log.count('FAIL: test_full_array_mask_upper_and_output_tail')==1 and
            'does not match "Unmodified unused backing BSS"' in log,'Exact known assertion-text failure only')
    unchanged=['scope.py','specification.py','strict.py','checker.py','detail_monitor.py','test_host.py']
    for name in unchanged:
        p=HERE/name
        require(prior['pins'][str(p)]==sha(p),'No change to checker/source/tests since34 passes '+name)
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(Supplement))
    replay.durable(HERE/'host_final.json',dict(status='PASS_HOST_ONLY_NOT_DUT' if result.wasSuccessful() else 'FAIL_HOST_ONLY_NOT_DUT',
        tests=35,failures=len(result.failures),errors=len(result.errors),inherited_passed_methods=34,
        corrected_methods=1,corrected_subcases=6,pins=replay.owned_pins(),
        unchanged_accepted_files=unchanged,actual_DUT_execution=False,full_reference_rerun=False,
        prior_host_sha256=sha(HERE/'host02.json'),prior_wait_sha256=sha(HERE/'host02.wait.json'),
        prior_actual_wait_exit=1,prior_failure_preserved=True))
    return int(not result.wasSuccessful())

if __name__=='__main__':raise SystemExit(main())
