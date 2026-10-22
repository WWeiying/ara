import unittest
from types import SimpleNamespace
from unittest.mock import patch
import diagnose_scalar_fpu_backpressure_v2 as v
import test_scalar_fpu_backpressure as fixture
import test_diagnose_scalar_fpu_backpressure as oldtests

class Logs(oldtests.Tests):
    def test_idle_flush_not_a_stall(self):
        fixture.FRAMES=fixture.frames('none')
        # Copy the frame: the earlier fixture reused the same idle dict twice.
        time,before,after=fixture.FRAMES[1]
        fixture.FRAMES[1]=(time,dict(before,flush_i='1'),dict(after,flush_i='1'))
        with patch.object(v.p,'wave',SimpleNamespace(vcd=fixture.stub)):
            result=v.checked_wave_function()('fixture')
        self.assertFalse(result['observed']);self.assertEqual(len(result['idle_ownerless_flush_times']),1)
    def test_strict_flush_combinations(self):
        for bad in ('pending','valid','state','use_hold','hold'):
            fixture.FRAMES=fixture.frames('none')
            if bad=='pending':fixture.FRAMES=fixture.frames('flush')
            else:
                _,row,_=fixture.FRAMES[1];row['flush_i']='1'
                row[{'valid':'fpu_valid_i','state':'state_q','use_hold':'use_hold','hold':'hold_inputs'}[bad]]='1'
            with self.subTest(bad=bad),patch.object(v.p,'wave',SimpleNamespace(vcd=fixture.stub)),self.assertRaises(ValueError):
                v.checked_wave_function()('fixture')

if __name__=='__main__':unittest.main()
