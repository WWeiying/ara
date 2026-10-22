import unittest
import audit_rr_disabled_formats783 as a


class SourceTests(unittest.TestCase):
    def test_ascending_mask(self):
        self.assertEqual([i for i in range(6) if a.disabled(56,1365,i)],[3,4,5])
        self.assertEqual([i for i in range(6) if a.disabled(32,1365,i)],[1,2,3,4,5])

    def test_disabled_group(self):
        self.assertTrue(all(a.disabled(56,0,i) for i in range(6)))

    def test_active_merged_preserved(self):
        self.assertFalse(a.disabled(56,2730,2))

    def test_unknown_unit_rejected(self):
        with self.assertRaises(Exception): a.disabled(63,4095,0)

    def test_frozen_source_and_mutations(self):
        texts = {a.Path(p).name:(a.m.ROOT/p).read_text() for p in a.m.SOURCE}
        a.source_guard(texts)
        for key,old,new in [('fpnew_pkg.sv',"DONT_CARE = 1'b1", "DONT_CARE = 1'b0"),
                            ('fpnew_opgroup_block.sv','.data_i ( fmt_outputs','.data_i ( opgrp_outputs'),
                            ('fpnew_opgroup_block.sv',"TagType'(fpnew_pkg::DONT_CARE)","TagType'('0)")]:
            changed=dict(texts); changed[key]=changed[key].replace(old,new)
            with self.assertRaises(Exception): a.source_guard(changed)


if __name__ == '__main__': unittest.main()
