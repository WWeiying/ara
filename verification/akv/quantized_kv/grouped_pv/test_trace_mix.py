import unittest
from trace_mix import analyze


class TraceMixTest(unittest.TestCase):
    def fixture(self):
        return ''.join(
            f'QUANT_GROUPED_BEGIN trial={i} enabled={mode} api={mode}\n'
            '[ARA_CONTRACT_TRACE] cycle=1 req=1/1 fire=1 id=0 insn=02076207\n'
            '[ARA_CONTRACT_TRACE] cycle=2 req=1/0 fire=0 id=0 insn=02076207\n'
            'UVM_INFO req=1/1 fire=1 id=0 insn=02076207\n'
            f'QUANT_GROUPED_RESULT trial={i} errors=0 differences=0\n'
            for i, mode in enumerate((0, 1, 1, 0))).splitlines()

    def test_only_one_source_and_fire(self):
        self.assertEqual(analyze(self.fixture())['trials'], [{'vector_load': 1}] * 4)

    def test_truncated(self):
        with self.assertRaises(ValueError):
            analyze(self.fixture()[:-1])

    def test_failed(self):
        with self.assertRaises(ValueError):
            analyze([line.replace('errors=0', 'errors=1') for line in self.fixture()])

    def test_reordered(self):
        with self.assertRaises(ValueError):
            analyze([line.replace('trial=0', 'trial=2') for line in self.fixture()])


if __name__ == '__main__':
    unittest.main()
