"""Mutation tests for checker logic, never DUT performance evidence."""
import unittest

import test_attention_check as old
from check_threeway_attention import ORDER, SUITE, capability, check_log
from check_batch_qk import TERMINAL


class ThreewayCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        old.AttentionCheckTest.setUpClass()
        cls.gold, cls.rtl = old.AttentionCheckTest.gold, old.AttentionCheckTest.rtl

    def transcript(self, kind=0):
        original = old.AttentionCheckTest().transcript(kind).splitlines()
        work = [line for line in original if line.startswith('[QBS_PERF]')]
        lines, cursor = [capability(kind)], 0
        for trial, mode in enumerate(ORDER):
            lines.append(f'QUANT_THREEWAY_BEGIN trial={trial} mode={mode}')
            if mode == 2:
                lines.extend(work[cursor:cursor+8])
                cursor += 8
            native, shared = mode == 2, mode != 0
            lines.append(f'QUANT_THREEWAY_RESULT trial={trial} mode={mode} cycles={3000-mode*1000} '
                         f'calls={8 if shared else 768} dots={0 if native else 768} '
                         f'commands={8 if native else 0} values={128 if shared else 768} '
                         f'panels={4 if native else 0} copied={128*(72 if kind else 136) if native else 0} '
                         f'quantizations=6 map=0 status=0 selection=0 groups={int(native)} executor=0 '
                         'fcsr=1 vcsr=5 max_abs=00000000 pair_max_abs=00000000 '
                         'pair_bits_differ=0 errors=0 hex='+'3f800000'*768)
        return '\n'.join(lines+[SUITE, TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0'])

    def test_exact_same_elf_threeway_accounting(self):
        for kind in (0, 1):
            data = check_log(self.transcript(kind), kind, self.gold, self.rtl)
            self.assertEqual(data['sums'], {'0': 6000, '1': 4000, '2': 2000})
            self.assertEqual(data['shared_schedule_speedup'], 1.5)
            self.assertEqual(data['qbs_incremental_speedup'], 2)
            self.assertEqual(data['combined_speedup'], 3)
            self.assertEqual(len(data['hardware_records']), 16)
            self.assertFalse(data['deployment_approved'])

    def test_work_layout_order_and_terminal_mutations(self):
        text = self.transcript()
        changes = [('dots=768', 'dots=767'), ('quantizations=6', 'quantizations=12'),
                   ('values=128', 'values=768'), ('panels=4', 'panels=0'),
                   ('copied=17408', 'copied=0'), ('groups=1', 'groups=0'),
                   ('map=0', 'map=5'), ('selection=0', 'selection=5'),
                   ('status=0', 'status=1'), ('executor=0', 'executor=1'),
                   ('trial=1 mode=1', 'trial=1 mode=2'), ('k_token_stride=272', 'k_token_stride=136'),
                   ('v_token_stride=272', 'v_token_stride=136'), ('commands=8', 'commands=0'),
                   ('UVM_ERROR : 0', 'UVM_ERROR : 1'), (SUITE, ''), (TERMINAL, '')]
        for before, after in changes:
            with self.subTest(before=before), self.assertRaises(ValueError):
                check_log(text.replace(before, after, 1), 0, self.gold, self.rtl)
        for extra in (SUITE, capability(0), 'QUANT_ATTN_SUITE_PASS', 'QUANT_THREEWAY_JUNK'):
            with self.subTest(extra=extra), self.assertRaises(ValueError):
                check_log(text+'\n'+extra, 0, self.gold, self.rtl)

    def test_numerical_flags_and_native_evidence(self):
        text = self.transcript()
        work = next(line for line in text.splitlines() if line.startswith('[QBS_PERF]'))
        for changed in (text.replace('hex=3f800000', 'hex=7fc00000', 1),
                        text.replace('max_abs=00000000', 'max_abs=3f800000', 1),
                        text.replace('fcsr=1', 'fcsr=3', 1),
                        text.replace(work+'\n', '', 1),
                        text.replace(work, work+'\n'+work, 1),
                        text.replace('success=1', 'success=0', 1),
                        text.replace('pair_bits_differ=0', 'pair_bits_differ=1', 1)):
            with self.assertRaises(ValueError):
                check_log(changed, 0, self.gold, self.rtl)
        with self.assertRaises(ValueError):
            check_log(text, 0, bytes(6144), self.rtl)


if __name__ == '__main__':
    unittest.main()
