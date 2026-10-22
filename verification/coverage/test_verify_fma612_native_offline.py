from pathlib import Path
import unittest
import verify_fma612_native_offline as checker

OUTPUT = Path(__file__).resolve().parents[1] / 'out' / 'fma_expanded_native_612-agent-20261007-04'
SEAL = 'b07201c920d2a952f08d263758cd54c4d5093e5eeac81a419d4512f2e8f7b492'


class ReadOnlyFmaTests(unittest.TestCase):
    def test_complete_replay_preserves_sealed_result_and_stdout_snapshot(self):
        paths = [OUTPUT / 'capture-result.json', OUTPUT / 'service-output-before-seal.log']
        before = [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths]
        self.assertEqual(checker.verify(OUTPUT, SEAL),
                         'EXACT_612_FMA_EXPANDED_TOGGLE_OBJECTS_NATIVE_ROUNDTRIP_PASS')
        self.assertEqual(before, [(path.read_bytes(), path.stat().st_mtime_ns) for path in paths])

    def test_wrong_seal_rejected(self):
        with self.assertRaises(ValueError):
            checker.verify(OUTPUT, '0' * 64)


if __name__ == '__main__':
    unittest.main()
