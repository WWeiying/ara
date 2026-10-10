"""Supplement the sealed preflight with an actual exception-PC mutation."""
import json
import re
import unittest

import build_vnclipu_reject_preflight as preflight


class ExceptionPCMutationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.record = json.loads((preflight.PRE / 'preflight-manifest.json').read_text())
        cls.trace = (preflight.PRE / 'spike.trace').read_text()
        cls.commits = preflight.shared.parse_spike_commits(preflight.PRE / 'spike.trace')

    def test_actual_wrong_pc_rejected_without_changing_retirement(self):
        symbols = self.record['symbols']
        pattern = r'(exception trap_illegal_instruction, epc )(0x[0-9a-fA-F]+)'
        matches = list(re.finditer(pattern, self.trace))
        self.assertEqual(len(matches), 1)
        self.assertEqual(int(matches[0][2], 16), symbols['gvc_bad'])
        wrong_pc = symbols['gvc_bad'] + 4
        changed, count = re.subn(
            pattern, lambda match: match[1] + f'0x{wrong_pc:016x}', self.trace)
        self.assertEqual(count, 1)
        self.assertNotEqual(changed, self.trace)
        self.assertEqual(int(re.search(pattern, changed)[2], 16), wrong_pc)
        with self.assertRaisesRegex(ValueError, 'exactly one illegal exception'):
            preflight.validate(self.commits, symbols, changed)

    def test_actual_correct_pc_still_passes(self):
        self.assertEqual(preflight.validate(self.commits, self.record['symbols'], self.trace),
                         self.record['validation'])


if __name__ == '__main__':
    unittest.main()
