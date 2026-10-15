"""Static/negative future eligibility proof, no DUT or raw trace consumption."""
import unittest
from policy import contract,no_work_reason,required_target
class OwnerContractTests(unittest.TestCase):
    def test_actual_source_counts(self):
        c=contract()
        self.assertEqual((c['source_calls'],c['required_helper_memory_owners'],c['required_target_owners'],
            c['required_op24_target_owners']),(4095,20475,2592,117))
        self.assertEqual(c['reason_counts'],dict(vstart_ge_vl=1485,unsigned_vslideup_vi_offset_ge_vl=18))
        self.assertFalse(c['total_uop_count_fixed'])
    def test_actual_vi_offset2_boundaries(self):
        for vl in (0,1,2):self.assertFalse(required_target(0x38813c57,vl,0))
        for vl in (3,16,31,32):self.assertTrue(required_target(0x38813c57,vl,0))
        self.assertTrue(required_target(0x38813c57,3,2))
    def test_not_all_slides_waived(self):
        for vl in (1,2,3,32):self.assertTrue(required_target(0x3c813c57,vl,0))
        self.assertTrue(required_target(0x38803c57,3,0)) # same VI opcode, unsigned offset0
        self.assertTrue(required_target(0x38814c57,3,0)) # VX form is not VI specialization
    def test_unsigned5_not_signed_immediate(self):
        insn=(0x38813c57&~(31<<15))|(31<<15)
        self.assertFalse(required_target(insn,31,0));self.assertTrue(required_target(insn,32,0))
    def test_nonempty_masked_targets_still_required(self):
        c=contract()
        for row in c['target_ledger']:
            if row['op']!=19 and row['vstart']<row['vl']:self.assertTrue(row['required'])
            if row['op']==19 and row['vl']>=3:self.assertTrue(row['required'])
        # mask mode is deliberately not an eligibility argument; alloff data
        # still requires its backend owner unless a proven dispatcher no-op.
    def test_bad_source_dimensions_rejected(self):
        for args in ((0x38813c57,33,0),(0x38813c57,3,-1),(0x38813c57,3,33),(0x38813c57,3.0,0)):
            with self.assertRaises(ValueError):no_work_reason(*args)
if __name__=='__main__':unittest.main(verbosity=2)
