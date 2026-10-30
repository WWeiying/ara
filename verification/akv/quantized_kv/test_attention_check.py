#!/usr/bin/env python3
"""Synthetic checker mutations; never treated as actual DUT acceptance."""
from pathlib import Path
import struct
import unittest

from batch_spec import Command
from check_attention import ORDER, SUITE, check_log
from check_batch_qk import schema, TERMINAL

ROOT = Path(__file__).resolve().parents[3]


class AttentionCheckTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rtl = (ROOT/'hardware/src/vlsu/vlsu.sv').read_text()
        cls.fields = schema(cls.rtl)
        cls.gold = struct.pack('<1536f', *([1.0]*1536))

    def transcript(self, kind=0):
        lines = [f'QUANT_ATTN_CAP kind={kind} heads=6 d=128 visible=128 kv_head=0 trials=4 scale=3db504f3']
        seq = 0
        for trial, mode in enumerate(ORDER):
            lines.append(f'QUANT_ATTN_BEGIN trial={trial} shared={mode}')
            if mode:
                for token in range(0, 128, 32):
                    for head, rows in ((0, 4), (4, 2)):
                        c = Command(kind, 0, head, rows, token, 32)
                        seq += 1
                        row = dict.fromkeys(self.fields, 0)
                        row.update(seq=seq, id=1, m=rows, n=32, vlen=1024, lanes=4, success=1,
                            read_ranges=c.read_ranges, payload_bytes=c.payload_bytes,
                            weight_bytes=c.weight_row_bytes*c.n, activation_bytes=136*c.m,
                            useful_pairs=128*c.outputs, busy_cycles=100, ar=c.read_ranges,
                            r_beats=c.read_ranges+4, read_outstanding_max=2, commit_groups=1)
                        lines.append('[QBS_PERF] '+' '.join(f'{k}={row[k]}' for k in self.fields))
            lines.append(f'QUANT_ATTN_RESULT trial={trial} shared={mode} cycles=1000 '
                f'calls={8 if mode else 768} values={128 if mode else 768} fcsr=1 vcsr=5 '
                'max_abs=00000000 pair_max_abs=00000000 pair_bits_differ=0 errors=0 hex='+('3f800000'*768))
        return '\n'.join(lines+[SUITE, TERMINAL, 'UVM_ERROR : 0', 'UVM_FATAL : 0'])

    def test_both_profiles(self):
        for kind in (0, 1):
            parsed = check_log(self.transcript(kind), kind, self.gold, self.rtl)
            self.assertEqual(len(parsed['hardware_records']), 16)
            self.assertEqual(parsed['speedup'], 1.0)
            self.assertFalse(parsed['deployment_approved'])

    def test_reject_mutations(self):
        text = self.transcript()
        work = next(x for x in text.splitlines() if x.startswith('[QBS_PERF]'))
        variants = [text.replace('scale=3db504f3', 'scale=3db504ed', 1),
                    text.replace('trial=0 shared=0', 'trial=0 shared=1', 1),
                    text.replace('values=128', 'values=768', 1),
                    text.replace('calls=8 ', 'calls=7 ', 1),
                    text.replace('errors=0', 'errors=1', 1),
                    text.replace('hex=3f800000', 'hex=7fc00000', 1),
                    text.replace('max_abs=00000000', 'max_abs=3f800000', 1),
                    text.replace('pair_bits_differ=0', 'pair_bits_differ=1', 1),
                    text.replace('fcsr=1', 'fcsr=0', 1),
                    text.replace('context_reuse_count=0', 'context_reuse_count=1', 1),
                    text.replace(work+'\n', '', 1), text.replace(work, work+'\n'+work, 1),
                    text.replace(TERMINAL, ''), text.replace(SUITE, SUITE+'\n'+SUITE, 1),
                    text.replace('UVM_ERROR : 0', 'UVM_ERROR : 1'), text+'\n'+SUITE]
        for i, changed in enumerate(variants):
            with self.subTest(mutation=i), self.assertRaises(ValueError):
                check_log(changed, 0, self.gold, self.rtl)
        with self.assertRaises(ValueError):
            check_log(text, 0, bytes(6144), self.rtl)


if __name__ == '__main__':
    unittest.main()
