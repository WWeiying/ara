"""Actual sealed R2 preflight gates and command rejection; no simulation calls."""
from copy import deepcopy
import unittest
import run_memory_emul_r2_simulation as r


class RunnerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre=r.life.read_bound(r.PRE/'preflight-manifest.json','1f3ae5b8faf7195a6eca0f29688ed8d8b4e03c90ee09fc6f7fc806fd76514245')
    def test_actual_contract(self):r.validate(self.pre)
    def test_fixed_budget(self):self.assertEqual(r.BUDGET,1200)
    def test_single_old_image_command(self):
        cmd=r.command(r.life.OUT/'unused-r2-test');self.assertEqual(cmd[0],str(r.life.IMAGE))
        self.assertEqual(sum(x.startswith('+PRELOAD=') for x in cmd),1)
        self.assertIn('+NO_FSDB',cmd);self.assertNotIn('dve',' '.join(cmd).lower())
    def reject(self,pre):
        with self.assertRaises(ValueError):r.validate(pre)
    def test_missing_snapshot(self):
        pre=deepcopy(self.pre);pre['validation']['snapshots']=6;self.reject(pre)
    def test_missing_trap(self):
        pre=deepcopy(self.pre);pre['validation']['illegal_traps']=2;self.reject(pre)
    def test_missing_guard(self):
        pre=deepcopy(self.pre);pre['validation']['memory_buffer_bytes']=863;self.reject(pre)
    def test_missing_check(self):
        pre=deepcopy(self.pre);pre['validation']['checks']=4228;self.reject(pre)
    def test_vill_forged_valid(self):
        pre=deepcopy(self.pre);pre['validation']['actual_prefault_vtypes'][0]=24;self.reject(pre)
    def test_lower_qualified_forgery(self):
        pre=deepcopy(self.pre);pre['lower_EMUL_targets_qualified']=True;self.reject(pre)
    def test_native_point_drift(self):
        pre=deepcopy(self.pre);pre['targets'][0]['point']['raw_index']+=1;self.reject(pre)
    def test_bad_elf_binding(self):
        pre=deepcopy(self.pre);pre['input_elf']='wrong.elf';self.reject(pre)
    def test_baseline_drift(self):
        pre=deepcopy(self.pre);pre['baseline_tests']=719;self.reject(pre)


if __name__=='__main__':unittest.main()
