import unittest
from pathlib import Path
from unittest.mock import patch
import run_tlb_asid_matrix as r


class Runner(unittest.TestCase):
    def test_exact_trace_coverage_no_wave(self):
        c=r.command(Path('/input.elf'),Path('/fresh'))
        self.assertIn('+NO_FSDB',c)
        self.assertEqual(c[c.index('-cm')+1],'line+cond+fsm+tgl+branch')
        self.assertFalse(any('force' in s or 'ucli' in s for s in c))

    def test_reject_command_timeout_and_retry(self):
        q=dict(schema='TLB_MATRIX_FROZEN_ONE_RUN_V1',case='tlb_asid_vpn_rsw_matrix',output='/nonexistent-tlb-matrix-fixture',
               command=[],timeout_s=600,preflight='/input/preflight.json',automatic_retry=False,
               coverage_admitted=False)
        for change in ({},{'timeout_s':601},{'automatic_retry':True},{'coverage_admitted':True}):
            with patch.object(r.life,'read_bound',return_value=dict(q,**change)),patch.object(r.life,'run') as run:
                with self.assertRaises(ValueError):r.run(Path('/prepared'),'seal')
                run.assert_not_called()

    def test_unqualified_preflight(self):
        with patch.object(r.life,'read_bound',return_value={'status':'FAILED'}):
            with self.assertRaises(ValueError):r.prepare(Path('/preflight'),'seal',Path('/fresh'))

    def test_actual_life_schema_requires_exact_case(self):
        output=Path('/nonexistent-tlb-matrix-fixture')
        q=dict(schema='TLB_MATRIX_FROZEN_ONE_RUN_V1',case='tlb_asid_vpn_rsw_matrix',output=str(output),
               command=r.command(Path('/input/input.elf'),output),timeout_s=600,preflight='/input/preflight.json',
               automatic_retry=False,coverage_admitted=False,pins={'/input/input.elf':'a'*64})
        with patch.object(r.life,'read_bound',return_value=q),patch.object(r.life,'run') as run:
            r.run(Path('/prepared'),'b'*64)
            self.assertEqual(run.call_args[0][1]['case'],'tlb_asid_vpn_rsw_matrix')


if __name__ == '__main__':unittest.main()
