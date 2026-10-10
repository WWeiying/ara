import unittest
import build_itlb_asid_exec_linear as pre


class LinearOracle(unittest.TestCase):
    def test_actual_exact_source_only_validation_changed(self):
        pre.exact_change(pre.old.APP.read_text(),pre.APP.read_text())

    def test_code_guard_removal_rejected(self):
        text=pre.APP.read_text().replace('entry<16;entry++) for (unsigned word=0;word<512;',
            'entry<1;entry++) for (unsigned word=0;word<512;')
        self.assertNotEqual(text,pre.APP.read_text())
        with self.assertRaisesRegex(ValueError,'outside'):pre.exact_change(pre.old.APP.read_text(),text)

    def test_asid_change_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            pre.exact_change(pre.old.APP.read_text(),pre.APP.read_text().replace('0xaaaaul','0xfful'))

    def test_check_count_change_rejected(self):
        with self.assertRaisesRegex(ValueError,'outside'):
            pre.exact_change(pre.old.APP.read_text(),pre.APP.read_text().replace('checks!=10966','checks!=42'))

    def test_ecall_or_mapping_change_rejected(self):
        for a,b in [('0x73ul','0x13ul'),('0x4b','0xcf')]:
            with self.assertRaisesRegex(ValueError,'outside'):
                pre.exact_change(pre.old.APP.read_text(),pre.APP.read_text().replace(a,b))

    def test_frozen_proof_and_current_successor(self):
        proof,pins=pre.source_contract()
        self.assertTrue(proof['stimulus_unchanged']);self.assertEqual(proof['checks_unchanged'],10966)
        self.assertEqual(proof['code_guards_unchanged_bytes'],65536)
        self.assertIn(str(pre.PRIOR),pins)


if __name__=='__main__':unittest.main()
