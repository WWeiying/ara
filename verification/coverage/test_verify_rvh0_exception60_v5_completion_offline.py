import hashlib
import json
import unittest

import verify_rvh0_exception60_v5_completion_offline as m


class Completion(unittest.TestCase):
    def setUp(self):
        self.result = json.loads((m.OUT / 'capture-result.json').read_bytes())
        self.terminal = json.loads((m.OUT / 'terminal.json').read_bytes())
        self.data = (m.OUT / 'service.log').read_bytes()
        self.sha = self.result['pins'][str(m.OUT / 'service.log')]

    def check(self, data, sha=None, terminal=None, result_sha=None):
        return m.stdout_closure(data, sha or self.sha, terminal or self.terminal,
                                m.OUT / 'capture-result.json', result_sha or m.RESULT_SHA)

    def test_real_stdout_exact_prefix_and_suffix(self):
        result = self.check(self.data)
        self.assertEqual(result['original_snapshot_bytes'], 401)
        self.assertEqual(result['suffix_bytes'], 237)
        self.assertFalse(result['original_whole_file_pin_matches_current'])

    def test_prefix_mutation_rejected(self):
        with self.assertRaises(ValueError):
            self.check(self.data.replace(b'409792', b'409793', 1))

    def test_extra_truncated_and_missing_tail_rejected(self):
        for data in (self.data + b'extra\n', self.data[:-1], self.data.splitlines(keepends=True)[0]):
            with self.assertRaises(ValueError):
                self.check(data)

    def test_wrong_result_seal_path_or_tail_bytes_rejected(self):
        prefix, suffix = self.data.splitlines(keepends=True)
        for bad in (suffix.replace(m.RESULT_SHA.encode(), b'0' * 64),
                    suffix.replace(b'capture-result.json', b'foreign.json'),
                    b' ' + suffix):
            with self.assertRaises(ValueError):
                self.check(prefix + bad)

    def test_prefix_terminal_mismatch_rejected(self):
        terminal = dict(self.terminal, actual_dve=[])
        with self.assertRaises(ValueError):
            self.check(self.data, terminal=terminal)

    def test_no_arbitrary_prefix_resealing(self):
        bad = b'{}\n' + self.data.splitlines(keepends=True)[1]
        with self.assertRaises(ValueError):
            self.check(bad, sha=hashlib.sha256(b'{}\n').hexdigest())

    def test_full_readonly_replay_preserves_original_result(self):
        before = m.native.life.digest(m.OUT / 'capture-result.json')
        result = m.collect()
        self.assertEqual(result['original_whole_file_matches'], 216)
        self.assertEqual(result['actual_inventory_files_checked'], 25)
        self.assertEqual(m.native.life.digest(m.OUT / 'capture-result.json'), before)
        self.assertEqual(before, m.RESULT_SHA)


if __name__ == '__main__':
    unittest.main()
