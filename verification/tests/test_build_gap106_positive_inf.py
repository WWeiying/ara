import copy
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest import mock

import build_gap106_positive_inf as m


class PreflightTests(unittest.TestCase):
    def oracle(self, command):
        return dict(scope='host-reference-only',independent_native_decode=True,
            row_major_bytes_checked=True,m=1,n=1,custom_instruction_execution_prechecked=False,
            fflags=0,integer_dot=[256],integer_correction=[0],
            expected_bits=[[0x43800000],[0x7f800000]][command],
            activation_hex=m.fixtures(0x3c00)[1].hex())

    def test_real_source_native_zero_binding(self):
        pins,targets=m.source_targets()
        self.assertEqual([p['raw_index'] for p in targets],[4,7])
        self.assertEqual([p['vector'] for p in targets],['1','0'])
        self.assertEqual(pins[str(m.DISPATCHER)],m.DISPATCHER_SHA)

    def test_fixture_only_scale_changes(self):
        finite,a=m.fixtures(0x3c00); inf,b=m.fixtures(0x7c00)
        self.assertEqual(a,b)
        self.assertEqual(finite[2:],inf[2:])
        self.assertEqual(struct.unpack('<H',inf[:2])[0],0x7c00)
        self.assertEqual(struct.unpack('<HH',inf[:4]),(0x7c00,0))
        self.assertEqual(struct.unpack('<16h',a[260:]),(16,)*16)

    def test_zero_dot_or_zero_activation_not_accepted(self):
        for key,value in [('integer_dot',[0]),('activation_hex','00'*292),
                          ('integer_correction',[1]),('fflags',16)]:
            row=self.oracle(1);row[key]=value
            with self.assertRaises(ValueError):m.oracle_check(row,1)

    def test_no_spike_or_full_isa_invention(self):
        row=self.oracle(1);row['custom_instruction_execution_prechecked']=True
        with self.assertRaises(ValueError):m.oracle_check(row,1)

    def test_positive_inf_and_control_exact(self):
        m.oracle_check(self.oracle(0),0);m.oracle_check(self.oracle(1),1)
        row=self.oracle(1);row['expected_bits']=[0x7fc00000]
        with self.assertRaises(ValueError):m.oracle_check(row,1)

    def test_only_reviewed_scale(self):
        for value in (0,0x7e00,0xfc00,0x7bff):
            with self.assertRaises(ValueError):m.fixtures(value)

    def test_template_full_buffers(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory);m.header(p,[self.oracle(0),self.oracle(1)])
            raw=(p/'gap106_data.h').read_text()
            self.assertIn('{1,1,4,1,0,176,292,0,',raw)
            self.assertIn('0x7f800000',raw)
            self.assertIn('gap106_weights0',raw)
            self.assertIn('gap106_weights1',raw)

    def test_asm_m1_word_csr_before_snapshot(self):
        text=(m.APP/'execute.S').read_text()
        self.assertEqual(text.count('MATRIX_EXEC 0, 1, 0x00b5045b'),1)
        self.assertEqual(text.count('MATRIX_EXEC 1, 1, 0x00b5045b'),1)
        self.assertLess(text.index('sd t0, 88(a4)'),text.index('vse32.v v0'))

    def test_bound_bytes_not_current_hash(self):
        with tempfile.TemporaryDirectory() as directory:
            p=Path(directory)/'data';p.write_text('{}')
            seal=m.sha(p);p.write_text('{"changed":true}')
            with self.assertRaises(ValueError):m.bound(p,seal)


if __name__=='__main__':unittest.main()
