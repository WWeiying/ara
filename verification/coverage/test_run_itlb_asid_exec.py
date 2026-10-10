import unittest
from pathlib import Path
import run_itlb_asid_exec as run


class Runner(unittest.TestCase):
    def test_command_exact_frozen_no_fsdb(self):
        out=run.life.OUT/'synthetic-itlb';elf=out/'input.elf';c=run.command(elf,out)
        self.assertEqual(c[0],str(run.life.IMAGE));self.assertIn('+NO_FSDB',c)
        self.assertIn('+PRELOAD='+str(elf),c);self.assertIn('+COMMIT_TOHOST=80001000',c)
        self.assertEqual(c[c.index('-cm')+1],'line+cond+fsm+tgl+branch')
        self.assertEqual(c[c.index('-do')+1],str(run.PROBE))
        self.assertNotIn('+RESET_ON_AXI',c)

    def test_no_simulator_from_unqualified_preflight(self):
        from unittest.mock import patch
        with patch.object(run.life,'read_bound',return_value={'status':'FAIL'}) as read:
            with self.assertRaises((KeyError,ValueError)):
                run.prepare(Path('/tmp/not-qualified'),'0'*64,run.life.OUT/'not-created')
        self.assertEqual(read.call_count,1)

    def test_run_rejects_changed_command_before_launch(self):
        from unittest.mock import patch
        r=dict(schema='ITLB_EXEC_FROZEN600_AUTOQUALIFY_V1',case=run.CASE,timeout_s=600,
            baseline_seal=run.pre.BASE_SHA,coverage_admitted=False,automatic_retry=False,
            preflight='/tmp/f.json',output=str(run.life.OUT/'not-created'),command=['wrong'])
        with patch.object(run.life,'read_bound',return_value=r),patch.object(run.life,'run') as launch:
            with self.assertRaisesRegex(ValueError,'Exact authorized'):run.run(Path('/tmp/x'),'0'*64)
            launch.assert_not_called()


if __name__=='__main__':unittest.main()
