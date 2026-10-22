import copy
import gzip
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import coverage_bitmap_delta as cov

SCOPE = 'ara_tb.dut.i_ara_soc.i_system'


def sample(test, bits, checksum=None):
    return {'design': {'shape': 'abc'}, 'tests': [test], 'input_hashes': {},
            'metrics': {'branch': {SCOPE + '.dut': {'width': 4, 'checksum': checksum, 'bits': hex(bits)}}}}


class BitmapTest(unittest.TestCase):
    def test_inherited_checksum_preserved_without_source_mapping(self):
        before, new = sample('old', 8), sample('new', 3)
        merged = cov.combine(before, new)
        self.assertEqual(merged['tests'], ['old', 'new'])
        delta = cov.delta(before, merged)
        self.assertEqual(delta['metrics']['branch'], 2)
        self.assertEqual(delta['instances'][0]['after_hit'], 3)
        self.assertEqual(before['metrics']['branch'][SCOPE + '.dut']['bits'], '0x8')

    def test_no_increment(self):
        old = sample('a', 15)
        self.assertEqual(cov.delta(old, cov.combine(old, sample('b', 1)))['metrics']['branch'], 0)

    def test_reject_duplicate_and_mixed_design(self):
        with self.assertRaises(ValueError):
            cov.combine(sample('a', 1), sample('a', 2))
        bad = sample('b', 2)
        bad['design']['shape'] = 'xyz'
        with self.assertRaises(ValueError):
            cov.combine(sample('a', 1), bad)

    def test_reject_mixed_width_or_checksum(self):
        bad = sample('b', 2)
        bad['metrics']['branch'][SCOPE + '.dut']['width'] = 5
        with self.assertRaises(ValueError):
            cov.combine(sample('a', 1), bad)
        with self.assertRaises(ValueError):
            cov.combine(sample('a', 1), sample('b', 2, 'other'))

    def test_reject_loss(self):
        with self.assertRaises(ValueError):
            cov.delta(sample('a', 8), sample('b', 1))

    def test_gzip_metric(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / 'branch.xml'
            p.write_bytes(gzip.compress(b'<covdata><instance_data name="dut" value="0101"/></covdata>'))
            self.assertEqual(cov.read_metric(p)['dut'], {'width': 4, 'checksum': None, 'bits': '0x5'})
            p.write_bytes(gzip.compress(b'<covdata><instance_data name="dut" value="X"/></covdata>'))
            with self.assertRaises(ValueError):
                cov.read_metric(p)


if __name__ == '__main__':
    unittest.main()
