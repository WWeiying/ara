import unittest
from pathlib import Path
import verify_cast168_native_offline as checker

OUTPUT = Path(__file__).resolve().parents[1] / 'out' / 'fpnew-cast-fp-shared168-native745-agent-20261007-04'
SEAL = 'acf46cc867704929ba718e0cf7efd9ffe936de463081f84667f0b4cfa87fe41a'


class ReadOnlyVerificationTests(unittest.TestCase):
    def test_substantive_replay_does_not_write_sealed_result(self):
        path = OUTPUT / 'capture-result.json'
        before = path.read_bytes()
        timestamp = path.stat().st_mtime_ns
        self.assertEqual(checker.verify(OUTPUT, SEAL),
                         'EXACT_CAST168_FIVE_STAGE_NATIVE_QUALIFIED_NOT_APPLIED')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(path.stat().st_mtime_ns, timestamp)

    def test_wrong_seal_rejected_without_writing(self):
        path = OUTPUT / 'capture-result.json'
        timestamp = path.stat().st_mtime_ns
        with self.assertRaises(ValueError):
            checker.verify(OUTPUT, '0' * 64)
        self.assertEqual(path.stat().st_mtime_ns, timestamp)


if __name__ == '__main__':
    unittest.main()
