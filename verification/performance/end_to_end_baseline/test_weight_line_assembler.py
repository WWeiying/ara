import unittest

from run_weight_line_assembler import check, NORMAL_CASES, NORMAL_BYTES, ABORT_BYTES


def fixture():
    lines = [f'WEIGHT_LINE_MODE_PASS mode={mode} cases={4096*(mode+1)}' for mode in range(4)]
    lines.append(f'WEIGHT_LINE_COMPONENT_PASS cases={NORMAL_CASES} abort_cases=4 '
                 f'accepted_bytes={NORMAL_BYTES+ABORT_BYTES} written_bytes={NORMAL_BYTES}')
    return '\n'.join(lines)


class WeightLineCheckerTests(unittest.TestCase):
    def test_exact_modes_bytes_and_abort_loss(self):
        result = check(fixture())
        self.assertEqual(result['discarded_bytes'], 78)
        self.assertEqual(result['cases'], 16387)
        self.assertEqual(result['written_bytes'], 1057025)

    def test_incomplete_duplicate_or_fatal_rejected(self):
        text = fixture()
        for wrong in (text.replace('mode=2', 'mode=1'), text + '\n' + text.splitlines()[-1],
                      text.replace('abort_cases=4', 'abort_cases=3'), text + '\nFatal: broken',
                      '\n'.join(text.splitlines()[1:])):
            with self.subTest(wrong=wrong), self.assertRaises(ValueError):
                check(wrong)

    def test_no_missing_or_invented_bytes(self):
        text = fixture()
        for old, new in ((f'accepted_bytes={NORMAL_BYTES+ABORT_BYTES}', f'accepted_bytes={NORMAL_BYTES}'),
                         (f'written_bytes={NORMAL_BYTES}', f'written_bytes={NORMAL_BYTES+1}')):
            with self.assertRaises(ValueError):
                check(text.replace(old, new))


if __name__ == '__main__':
    unittest.main()
