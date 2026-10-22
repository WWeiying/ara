import unittest
import preflight_gap71_canonical779 as m


class CanonicalTests(unittest.TestCase):
    def test_both_windows_and_complement(self):
        for window in m.WINDOWS.values(): m.window_gate(window)
        self.assertEqual(m.WINDOWS['positive'] ^ m.WINDOWS['negative'], ((1<<64)-1) & ~((1<<21)-1))

    def test_noncanonical_alignment_overflow_and_identity_collision_rejected(self):
        for window in (1, 1<<39, 0x80000000, (1<<64)-(1<<21), False):
            if window == (1<<64)-(1<<21):
                # This last canonical window has ample space for our three pages.
                m.window_gate(window)
            else:
                with self.assertRaises(ValueError): m.window_gate(window)

    def test_complete_PTE_relocation_and_missing_leaf(self):
        for window in m.WINDOWS.values():
            p = m.pages(0x80040000,False,True,window)
            self.assertEqual([i for i,v in enumerate(p[0]) if v], [2,window>>30&511])
            self.assertEqual([i for i,v in enumerate(p[1]) if v], [window>>21&511])
            self.assertEqual(p[2][2],0)
            self.assertEqual(p[3][1],window+0x1080)
            self.assertEqual(m.pages(0x80040000,False,False,window)[2][2],0x20011043)

    def test_PMA_fault_override_guard_mutations_rejected(self):
        text=(m.ROOT/m.RTL[0]).read_text();m.driver_gate(text)
        for bad in (text.replace('!mmu_exception_valid_i &&','',1),
                    text.replace('(!en_ld_st_translation_i || mmu_valid_i);','1\'b1;',1),
                    text.replace('planner_fault_mmu_exception = mmu_exception_i;','planner_fault_mmu_exception = \'0;')):
            with self.assertRaises(ValueError): m.driver_gate(bad)

    def test_AKV_exact_24_32_40_byte_pointer_offsets_and_reserved(self):
        window=m.WINDOWS['positive'];p=m.pages(0x80040000,True,True,window)
        self.assertEqual(p[3][3:7],[window+0x1080,window+0x2080,window+0x2200,0])

    def test_old_address_literals_absent_and_recovery_added(self):
        for window in m.WINDOWS.values():
            text=m.source_header(window)+m.source_data(window)
            self.assertNotIn('0x40002080',text)
            self.assertIn('canon_recovery_site:',text)
            self.assertIn(hex(window+0x2080),text)
            self.assertEqual(m.oracle(window)['checks']('gap71_qbs_fault'),160)


if __name__=='__main__':unittest.main()
