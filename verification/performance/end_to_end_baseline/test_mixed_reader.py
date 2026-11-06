import unittest

from run_mixed_reader import legacy_check, mixed_check


def legacy_fixture(combinational):
    lines = ['QBS read engine PASS', f'QBS_MMU_RESPONSE t=10 combinational={int(combinational)} req=1 valid=1']
    lines += ['[QBS_READ_CASE] '+name+' PASS' for name in
              ('nonidentity_unaligned','noncontiguous_pages','second_page_fault','post_fault_reuse')]
    lines += [f'QBS stalled-AR fault PASS mode={m} delay={d}' for m in range(3) for d in (0,6)]
    return '\n'.join(lines)


def mixed_fixture():
    lines = [f'MIXED_READER_SIZE_PASS size={s} cases={(s+1)*32}' for s in range(6)]
    return '\n'.join(lines+['MIXED_READER_COMPONENT_PASS cases=258 faults=4 footprint_checks=900'])


class MixedReaderChecks(unittest.TestCase):
    def test_exact_modes_required(self):
        self.assertEqual(mixed_check(mixed_fixture())['range_transfer_bytes'], [1,2,4,8,16,32])
        for mode in (False, True):
            self.assertEqual(legacy_check(legacy_fixture(mode), mode)['stalled_ar_faults'], 6)
            with self.assertRaises(ValueError):
                legacy_check(legacy_fixture(mode), not mode)

    def test_failures_and_incomplete_rejected(self):
        text = mixed_fixture()
        for wrong in (text.replace('size=4', 'size=5'), text.replace('faults=4','faults=3'),
                      text+'\n'+text.splitlines()[-1], text+'\nFatal: broken',
                      '\n'.join(text.splitlines()[1:])):
            with self.assertRaises(ValueError):
                mixed_check(wrong)
        text = legacy_fixture(False)
        for wrong in (text.replace('delay=6','delay=0'), text.replace('post_fault_reuse','wrong'), text+'\nError: broken'):
            with self.assertRaises(ValueError):
                legacy_check(wrong, False)


if __name__ == '__main__':
    unittest.main()
