"""Strict result/set replay tests; the actual artifact replay is run separately."""
import copy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
from run_sealed_queue_extension import require_exact_replay


class SealedReplayTest(unittest.TestCase):
    def setUp(self):
        self.result = {'status': 'PASS', 'elf_sha256': 'a' * 64,
                       'scope': 'Spike-only', 'checks': 1274}
        self.files = {'elf': 'a' * 64, 'compiler': 'b' * 64}
        self.saved = {'status': 'PASS', 'read_only_validation': True,
                      'result': copy.deepcopy(self.result), 'checked_files': dict(self.files)}

    def test_exact(self):
        require_exact_replay(self.result, self.files, self.saved)

    def test_changed_tool(self):
        self.files['compiler'] = 'c' * 64
        with self.assertRaises(ValueError):
            require_exact_replay(self.result, self.files, self.saved)

    def test_missing_file(self):
        del self.files['compiler']
        with self.assertRaises(ValueError):
            require_exact_replay(self.result, self.files, self.saved)

    def test_extra_file(self):
        self.files['unreviewed'] = 'd' * 64
        with self.assertRaises(ValueError):
            require_exact_replay(self.result, self.files, self.saved)

    def test_wrong_elf(self):
        self.result['elf_sha256'] = 'e' * 64
        with self.assertRaises(ValueError):
            require_exact_replay(self.result, self.files, self.saved)

    def test_changed_result(self):
        self.result['checks'] -= 1
        with self.assertRaises(ValueError):
            require_exact_replay(self.result, self.files, self.saved)

    def test_unchecked_report(self):
        self.saved['read_only_validation'] = False
        with self.assertRaises(ValueError):
            require_exact_replay(self.result, self.files, self.saved)


if __name__ == '__main__':
    unittest.main()
