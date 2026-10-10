"""Actual Spike rejection fixtures are required, never counted as skipped PASS."""
from dataclasses import replace
import json
import os
from pathlib import Path
import struct
import unittest

import build_vnclipu_reject_preflight as p


class StaticTests(unittest.TestCase):
    def test_encoding(self):
        self.assertEqual((46 << 26) | (1 << 25) | (10 << 20) | (4 << 12) | (16 << 7) | 0x57, p.BAD)
        self.assertEqual((p.BAD >> 15) & 31, 0)

    def test_recovery_bytes(self):
        self.assertEqual(p.expected_register(16, 2)[:4], bytes.fromhex('3412ffff'))
        self.assertEqual(p.expected_register(16, 2)[4:], p.expected_register(16)[4:])

    def test_reject_keeps_all_registers(self):
        for reg in range(32): self.assertEqual(p.expected_register(reg), p.expected_register(reg, 1))

    def test_source_is_unsigned32(self):
        self.assertEqual(struct.unpack('<II', p.expected_register(8)[:8]), (0x1234, 0x10001))

    def test_unknown_store_rejected(self):
        with self.assertRaises(ValueError): p.shared.store_width(0x13)

    def test_live725_exact_targets_with_line_index_holes(self):
        targets = p.target_binding()[0]
        self.assertEqual(len(targets), 5)
        self.assertEqual([(t['raw_index'], t['compiled_id'], t['line']) for t in targets if t['metric'] == 'line'],
                         [(557, '549', '2251'), (564, '556', '2254')])


class ActualTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = Path(os.environ.get('VNCLIPU_PREFLIGHT', str(p.PRE))).absolute()
        cls.pre = json.loads((cls.out / 'preflight-manifest.json').read_text())
        cls.commits = p.shared.parse_spike_commits(cls.out / 'spike.trace')
        cls.symbols = cls.pre['symbols']; cls.trace = (cls.out / 'spike.trace').read_text()

    def validate(self, commits=None, trace=None):
        return p.validate(self.commits if commits is None else commits, self.symbols, self.trace if trace is None else trace)

    def corrupt(self, name, offset, value):
        c = replace(self.commits[-1], instruction=0x0002b023, vector_writes={}, memory_accesses=((self.symbols[name] + offset, value),))
        with self.assertRaises(ValueError): self.validate(self.commits + [c])

    def test_actual_complete(self): self.assertEqual(self.validate(), self.pre['validation'])
    def test_missing_trap(self):
        with self.assertRaises(ValueError): self.validate(trace='')
    def test_duplicate_trap(self):
        with self.assertRaises(ValueError): self.validate(trace=self.trace + 'exception trap_illegal_instruction, epc 0x80000000\n')
    def test_wrong_fault_pc(self):
        with self.assertRaises(ValueError): self.validate(trace=self.trace.replace('epc 0x%x' % self.symbols['gvc_bad'], 'epc 0x80000000'))
    def test_bad_retired(self):
        with self.assertRaises(ValueError): self.validate(self.commits + [replace(self.commits[-1], pc=self.symbols['gvc_bad'])])
    def test_wrong_cause(self): self.corrupt('gvc_ledger', 0, 3)
    def test_wrong_tval(self): self.corrupt('gvc_ledger', 16, p.BAD ^ 1)
    def test_wrong_ledger_pc(self): self.corrupt('gvc_ledger', 8, self.symbols['gvc_bad'] + 4)
    def test_vstart_lost(self): self.corrupt('gvc_post', 32, 0)
    def test_vtype_wrong(self): self.corrupt('gvc_cfg', 8, 9)
    def test_vl_wrong(self): self.corrupt('gvc_cfg', 0, 0)
    def test_t2_clobbered(self): self.corrupt('gvc_post', 16, 0)
    def test_restore_csr_lost(self): self.corrupt('gvc_restore', 17 * 8, 1)
    def test_snapshot_guard(self): self.corrupt('gvc_dump', 0, 0)
    def test_input_guard(self): self.corrupt('gvc_seed', 17 * 8, 0)
    def test_far_register_changed(self): self.corrupt('gvc_dump', (32 * 18 + 31 * 18 + 8) * 8, 0)
    def test_recovery_tail_changed(self): self.corrupt('gvc_dump', (2 * 32 * 18 + 16 * 18 + 16) * 8, 0)
    def test_saturation_lost(self): self.corrupt('gvc_recovery_cfg', 24, 4)
    def test_wrong_check_count(self): self.corrupt('g75_result', 0, p.CHECKS - 1)
    def test_false_tohost(self): self.corrupt('tohost', 0, 3)
    def test_missing_full_readback(self):
        start = self.symbols['gvc_dump']
        cs = [replace(c, memory_accesses=tuple((a, v) for a, v in c.memory_accesses if not (v is None and a == start))) for c in self.commits]
        with self.assertRaises(ValueError): self.validate(cs)
    def test_illegal_vector_write(self):
        with self.assertRaises(ValueError): self.validate(self.commits + [replace(self.commits[-1], vector_writes={31: 0})])
    def test_recovery_corrupt(self):
        cs = [replace(c, vector_writes={16: 0}) if c.pc == self.symbols['gvc_recovery'] else c for c in self.commits]
        with self.assertRaises(ValueError): self.validate(cs)
    def test_handler_extra_store(self):
        c = replace(self.commits[-1], pc=self.symbols['gvc_handler'] + 4, instruction=0x0002b023,
                    vector_writes={}, memory_accesses=((self.symbols['gvc_post'], 0),))
        with self.assertRaises(ValueError): self.validate(self.commits + [c])
    def test_handler_protected_csr(self):
        cs = [replace(c, csr_writes={8: 0}) if c.pc == self.symbols['gvc_handler'] else c for c in self.commits]
        with self.assertRaises(ValueError): self.validate(cs)
    def test_handler_other_gpr(self):
        cs = [replace(c, gpr_writes={8: 0}) if c.pc == self.symbols['gvc_handler'] else c for c in self.commits]
        with self.assertRaises(ValueError): self.validate(cs)
    def test_fault_word_changed(self):
        blob = bytearray((self.out / 'input.elf').read_bytes()); pos = blob.find(p.BAD.to_bytes(4, 'little'))
        self.assertGreaterEqual(pos, 0); blob[pos] ^= 1
        with self.assertRaises(ValueError): p.verify_elf(blob, self.symbols)


if __name__ == '__main__': unittest.main()
