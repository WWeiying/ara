import copy
from pathlib import Path
import unittest
from unittest.mock import patch

import run_narrow_clip_reject_simulation_450 as r


class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.old = r.life.read_bound(r.OLD_PREPARED, r.OLD_SEAL)
        cls.state = r.life.read_bound(r.OLD/'simulation-status.json',r.TIMEOUT_PINS[str(r.OLD/'simulation-status.json')])

    def test_actual_sealed_timeout_and_no_drift(self):
        self.assertEqual(r.timeout_evidence(),self.old)

    def test_private_source_budget_no_predecessor_mutation(self):
        ns=r.namespace()
        self.assertEqual(ns['BUDGET'],450)
        self.assertEqual(r.prior.BUDGET,300)
        self.assertEqual(r.life.digest(Path(r.prior.__file__)),r.PRIOR_SHA)

    def test_actual_manifest_sameELF_targets_fullpins(self):
        ns=r.namespace();out=r.life.OUT/'synthetic-clip17-450'
        record=ns['manifest'](out)
        self.assertEqual(record['timeout_s'],450)
        self.assertEqual(record['systemd_policy']['RuntimeMaxSec'],510)
        self.assertEqual(record['elf_sha256'],self.old['elf_sha256'])
        self.assertEqual(record['targets'],self.old['targets'])
        self.assertEqual(record['scalar_reference_counts'],self.old['scalar_reference_counts'])
        self.assertTrue(self.old['pins'].items() <= record['pins'].items())
        self.assertTrue(r.TIMEOUT_PINS.items() <= record['pins'].items())
        self.assertFalse(record['automatic_retry'])
        self.assertFalse(record['coverage_admitted'])
        self.assertEqual(record['command'],r.prior.command(out))
        allowed={'output','command','pins','timeout_s','systemd_policy','predecessor_run','predecessor_prepared',
                 'predecessor_prepared_seal','predecessor_status','predecessor_timeout_pins','budget_successor',
                 'budget_change_only','original_timeout_preserved'}
        self.assertEqual({k:v for k,v in record.items() if k not in allowed},
                         {k:v for k,v in self.old.items() if k not in allowed})

    def test_unclean_timeout_and_non_timeout_rejected(self):
        original=r.life.read_bound
        for key,value in [('timeout',False),('process_group_cleanup',False),('post_failure_pin_error','drift'),
                          ('returncode',0),('status','SIMULATION_EXITED_NOT_ADMITTED')]:
            state=copy.deepcopy(self.state);state[key]=value
            def read(path,seal):
                return state if Path(path)==r.OLD/'simulation-status.json' else original(path,seal)
            with patch.object(r.life,'read_bound',side_effect=read),patch.object(r.life,'check'):
                with self.assertRaises(ValueError):r.timeout_evidence()

    def test_live_old_simulator_HOLD(self):
        with patch.object(Path,'exists',return_value=True),patch.object(r.life,'check'):
            with self.assertRaises(ValueError):r.timeout_evidence()

    def test_original_directory_never_overwritten(self):
        ns=r.namespace()
        with self.assertRaises(ValueError):ns['prepare'](r.OLD)
        with self.assertRaises(ValueError):ns['manifest'](r.OLD)

    def test_no_authorization_no_reads_or_run(self):
        ns=r.namespace()
        with patch.object(r.life,'read_bound') as read:
            with self.assertRaises(ValueError):ns['main'](['run','--output',str(r.life.OUT/'synthetic-450'),
                                                         '--prepared-seal','a'*64])
            read.assert_not_called()

    def test_single_foreground_run450_and_restoration(self):
        ns=r.namespace();record={'timeout_s':450};out=r.life.OUT/'synthetic-450'
        keys=('BUDGET','PRE','ELF_SEAL','IMAGE_SEAL','preflight','command')
        old={k:getattr(r.prior.frozen,k) for k in keys}
        def fail(output,prepared):
            self.assertEqual(r.prior.frozen.BUDGET,450)
            self.assertEqual(r.prior.frozen.PRE,r.prior.PRE)
            self.assertEqual(r.prior.frozen.command(out),r.prior.command(out))
            raise RuntimeError('mock no EDA')
        ns['prepare']=lambda output:record
        with patch.object(r.prior.frozen,'run',side_effect=fail) as run:
            with self.assertRaises(RuntimeError):ns['invoke_run'](out,record)
            self.assertEqual(run.call_count,1)
        self.assertEqual({k:getattr(r.prior.frozen,k) for k in keys},old)


if __name__=='__main__':unittest.main()
