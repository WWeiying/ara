"""Synthetic Host fixtures only; no original stalled tuple is recovered."""
import copy
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
import unittest
import decode as d


def fixture(k, cap=512):
    sp = 0x40001000
    seed, s, l, m, t = k//896, (k%896)//112, (k%112)//16, (k%16)//4, k%4
    vl = (0, 1, 2, 3, cap//2, cap-1, cap)[l]
    scalar = (0, 1, cap-1, cap, cap+1, d.MASK, 1 << 63, (1 << 63)-1)[s]
    return dict(schema='R168_REGS_STACK_V1', source_elf_sha256=d.ELF_SHA,
        capture_id='HOST_SYNTHETIC_NOT_AN_ARCHIVE_DUMP', same_context_regs_stack=True,
        regs=dict(pc=0x10642, sp=sp, ra=0x103ce, s4=t, s7=sp+160+s*8, s8=3,
            s9=sp+128+l*4, a3=vl, a4=cap, a6=scalar, a7=(1, vl//2, vl, cap-1)[t]),
        csrs={'vlenb': cap//4},
        stack=dict(address=sp, byte_order='little', data_hex=struct.pack('<QQQQ', m, seed, cap+1, k).hex()))


class Decoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.binding = d.binding()

    def test_all_original2688_ordinals(self):
        for k in range(2688):
            x = d.decode(fixture(k), self.binding)
            self.assertEqual(x['unreturned_original_ordinal'], k+1)
            self.assertEqual(x['preceding_original_ordinals']['count'], k)
            self.assertFalse(x['historical_stall_closed'])

    def test_capacity_and_duplicate_trial_boundaries(self):
        for cap in (32, 64, 128, 256, 512, 1024):
            for k in (0, 1, 2, 15, 16, 65, 111, 112, 895, 896, 1792, 2687):
                d.decode(fixture(k, cap), self.binding)
        self.assertEqual(d.decode(fixture(65), self.binding)['original_tuple'], [0, 3, 0, 4, 0, 1])

    def test_no_dump_no_tuple(self):
        for value in ({}, None, {'schema': 'R168_REGS_STACK_V1'}, {'core': {'last_pc': 0x1063e}}):
            with self.assertRaises(ValueError):
                d.decode(value, self.binding)
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp)/'input.json';p.write_text('{}')
            r = subprocess.run([sys.executable, '-B', str(Path(d.__file__)), str(p)], capture_output=True, text=True)
            self.assertEqual(r.returncode, 1)
            self.assertEqual(json.loads(r.stdout)['status'], 'REJECTED_NO_TUPLE')
            self.assertNotIn('original_tuple', json.loads(r.stdout))

    def test_conflicting_regs_context_arguments(self):
        for key in ('pc', 'ra', 's4', 's7', 's8', 's9', 'a3', 'a4', 'a6', 'a7'):
            x = fixture(65);x['regs'][key] += 1
            with self.subTest(key=key), self.assertRaises(ValueError):d.decode(x, self.binding)
        x = fixture(65);x['regs']['x2'] = x['regs']['sp']+16
        with self.assertRaises(ValueError):d.decode(x, self.binding)
        x = fixture(65);x['regs']['a3'] = True
        with self.assertRaises(ValueError):d.decode(x, self.binding)

    def test_bad_stack_fields_and_complete_boundary(self):
        for slot in range(4):
            x = fixture(65);values = list(struct.unpack('<QQQQ', bytes.fromhex(x['stack']['data_hex'])))
            values[slot] += 1;x['stack']['data_hex'] = struct.pack('<QQQQ', *values).hex()
            with self.subTest(slot=slot), self.assertRaises(ValueError):d.decode(x, self.binding)
        x = fixture(65);x['stack']['data_hex'] = '00'*31
        with self.assertRaises(ValueError):d.decode(x, self.binding)
        x = fixture(65);x['stack']['data_hex'] = struct.pack('<QQQQ', 0, 3, 513, 2688).hex()
        with self.assertRaises(ValueError):d.decode(x, self.binding)

    def test_identity_endian_and_csr_rejected(self):
        for field, value in [('source_elf_sha256', '0'*64), ('capture_id', ''), ('same_context_regs_stack', False)]:
            x = fixture(65);x[field] = value
            with self.assertRaises(ValueError):d.decode(x, self.binding)
        for field, value in [('address', 0), ('byte_order', 'big')]:
            x = fixture(65);x['stack'][field] = value
            with self.assertRaises(ValueError):d.decode(x, self.binding)
        x = fixture(65);x['csrs']['vlenb'] = 64
        with self.assertRaises(ValueError):d.decode(x, self.binding)


if __name__ == '__main__':
    unittest.main(verbosity=2)
