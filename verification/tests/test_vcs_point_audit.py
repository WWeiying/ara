"""Point-union checks: unchanged shape, preserved history, exact new hits."""
import copy
from pathlib import Path
import sys
import unittest
import xml.etree.ElementTree as ET

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'coverage'))
import vcs_point_audit as audit


def record(bits):
    return {'inputs': 'sample', 'tests': 1, 'instances': {'dut': {'branch': {
        'checksum': '123', 'bits': bits, 'total': len(bits), 'covered': bits.count('1'),
        'missing': [{'bit_index': i, 'vector': str(i)} for i, b in enumerate(bits) if b == '0']}}}}


class PointAuditTest(unittest.TestCase):
    def test_union_and_precise_gain(self):
        old, new = record('1000'), record('0100')
        result = audit.union(old, new)
        self.assertEqual(result['instances']['dut']['branch']['bits'], '1100')
        self.assertEqual(old['instances']['dut']['branch']['bits'], '1000')
        gain = audit.gains(old, result)['dut']['branch']
        self.assertEqual(gain['new_points'], 1)
        self.assertEqual(gain['points'][0]['bit_index'], 1)
        self.assertEqual(result['tests'], 2)

    def test_no_gain(self):
        old = record('1010')
        gain = audit.gains(old, audit.union(old, record('0010')))
        self.assertEqual(gain['dut']['branch']['new_points'], 0)

    def test_shape_mismatch(self):
        old, new = record('1000'), record('0100')
        new['instances']['dut']['branch']['checksum'] = '456'
        with self.assertRaises(ValueError):
            audit.union(old, new)
        with self.assertRaises(ValueError):
            audit.gains(old, new)

    def test_history_cannot_disappear(self):
        with self.assertRaises(ValueError):
            audit.gains(record('1000'), record('0100'))

    def test_malformed_bits(self):
        with self.assertRaises(ValueError):
            audit.union(record('1000'), record('01X0'))

    def test_branch_shape(self):
        shape = ET.fromstring('<shape><branch_def chksum="1"><branch_spec id="2" totalbranches="2">'
            '<branch_expr linenum="40"/><branch_vector id="0" vector="F"/>'
            '<branch_vector id="1" vector="T"/></branch_spec></branch_def></shape>')
        points = audit.points(shape, 'branch', '1')
        self.assertEqual([p['vector'] for p in points], ['F', 'T'])
        self.assertEqual(points[0]['expressions'][0]['linenum'], '40')
        with self.assertRaises(ValueError):
            audit.points(shape, 'branch', '2')


if __name__ == '__main__':
    unittest.main()
