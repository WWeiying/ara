import re
import unittest

from check_strided_attention import capability, entry, check_log
import test_attention_check as original_checks


class StridedAttentionCheck(unittest.TestCase):
    def transcript(self, kind):
        original_checks.AttentionCheckTest.setUpClass()
        original = original_checks.AttentionCheckTest()
        lines = [capability(kind)]
        for line in original.transcript(kind).splitlines():
            for trial in (1, 2):
                if line.startswith(f'QUANT_ATTN_RESULT trial={trial} '):
                    lines.append(entry(kind, trial))
            lines.append(line)
        return '\n'.join(lines), original.gold, original.rtl

    def test_both_profiles(self):
        for kind in (0, 1):
            text, gold, rtl = self.transcript(kind)
            result = check_log(text, kind, gold, rtl)
            self.assertTrue(result['gather_timed'])
            self.assertTrue(result['same_rvv_value_decoder'])
            self.assertEqual(result['copied_key_bytes'], 18432 if kind else 34816)
            self.assertFalse(result['deployment_approved'])

    def test_missing_or_false_layout_work(self):
        text, gold, rtl = self.transcript(0)
        for old, new in [(capability(0), ''), (capability(0), capability(1)),
                         ('gather_timed=1', 'gather_timed=0'), ('workspace=13120', 'workspace=8192'),
                         ('panels=4', 'panels=8'), ('copied=17408', 'copied=34816'),
                         ('k_token_stride=272', 'k_token_stride=136'),
                         ('v_token_stride=272', 'v_token_stride=136'),
                         ('commands=8', 'commands=7'), ('selection=0', 'selection=5'),
                         (entry(0, 1), ''), (entry(0, 2), entry(0, 1))]:
            with self.subTest(new=new), self.assertRaises(ValueError):
                check_log(text.replace(old, new, 1), 0, gold, rtl)
        for extra in (entry(0, 1), capability(0), 'QUANT_COMMON_CAP map_timed=1'):
            with self.assertRaises(ValueError):
                check_log(text + '\n' + extra, 0, gold, rtl)

    def test_independent_math_protocol_and_csr(self):
        text, gold, rtl = self.transcript(0)
        for altered in (text.replace('hex=3f800000', 'hex=7fc00000', 1),
                        text.replace('calls=8 ', 'calls=7 ', 1),
                        text.replace('success=1', 'success=0', 1),
                        text.replace('UVM_ERROR : 0', 'UVM_ERROR : 1', 1)):
            with self.assertRaises(ValueError):
                check_log(altered, 0, gold, rtl)
        # Change both candidate flag reports: same-mode repetition alone would
        # accept these, so the added cross-mode CSR check is necessary.
        candidate_flags, mutations = re.subn(
            r'(QUANT_ATTN_RESULT trial=[12] shared=1 [^\n]*? fcsr=)1 ', r'\g<1>3 ', text)
        self.assertEqual(mutations, 2)
        with self.assertRaises(ValueError):
            check_log(candidate_flags, 0, gold, rtl)


if __name__ == '__main__':
    unittest.main()
