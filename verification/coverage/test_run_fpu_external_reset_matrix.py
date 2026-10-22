import copy
import unittest
import run_fpu_external_reset_matrix as m


class Matrix(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.pre=m.life.read_bound(m.PRE/'preflight.json',m.PRE_SHA)

    def test_exact_remaining11(self):
        self.assertEqual(len(m.CASES),11);self.assertNotIn((16,'EX2'),m.CASES)
        self.assertEqual(len(set(m.CASES)),11)

    def test_all_stage_codes_and_precision_guards(self):
        for sew,stage in m.CASES:
            c,row,active=m.select(self.pre,sew,stage)
            self.assertEqual(c['ext_value'],m.STAGES[stage][0]);self.assertEqual(len(active),{16:16,32:8,64:4}[sew])
            if stage=='EX2':self.assertTrue(c['ext_guard'].endswith('vfdsu_ex2_'+{16:'half',32:'single',64:'double'}[sew]))
            else:self.assertTrue(c['ext_guard'].endswith('vfdsu_dp_fdiv_busy'))
            self.assertEqual(row['sew'],sew);self.assertNotIn('force',m.text(c))

    def test_no_automatic_reset_or_wrong_ELF(self):
        for sew,stage in m.CASES:
            c,row,active=m.select(self.pre,sew,stage)
            out=m.life.OUT/'synthetic';cmd=m.command(out,row,out/'entry',stage)
            self.assertIn('+PRELOAD='+row['ELF'],cmd);self.assertFalse(any(x.startswith('+ARA_UVM_RESET_') for x in cmd))
            self.assertIn('+NO_FSDB',cmd);self.assertEqual(cmd[0],str(m.life.IMAGE))

    def test_unapproved_or_injected_selection_rejected(self):
        with self.assertRaises(ValueError):m.select(self.pre,16,'EX2')
        with self.assertRaises(ValueError):m.select(self.pre,8,'RF')
        c,_,_=m.select(self.pre,16,'RF');c=copy.deepcopy(c);c['ext_dump_objects'][0]='ara_tb.clk;force'
        with self.assertRaises(ValueError):m.text(c)

    def test_pin_conflict(self):
        with self.assertRaises(ValueError):m.life.merge_pins({'/pin':'a'*64},{'/pin':'b'*64})


if __name__=='__main__':unittest.main()
