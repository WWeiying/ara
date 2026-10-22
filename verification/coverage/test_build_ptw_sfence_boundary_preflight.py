import copy
from types import SimpleNamespace
import unittest

import build_ptw_sfence_boundary_preflight as p


class PreflightTests(unittest.TestCase):
    def fixture(self):
        symbols = {name: 0x81000000 + i * 0x1000 for i, name in enumerate(p.geometry.SYMBOLS)}
        symbols.update(gcb_page=0x80010000, gcb_entry=0x80010f00,
                       gcb_second=0x80011000, gcb_s_ecall=0x80011020, gpf_sfence=0x80010ffc)
        writes = {symbols['tohost']: 1, symbols['g75_result']: 35,
                  symbols['g75_result'] + 4: 0, symbols['num_failed']: 0, symbols['gcb_count']: 2,
                  symbols['gcb_root'] + 8: (symbols['gcb_mid'] >> 12 << 10) | 1,
                  symbols['gcb_mid']: (symbols['gcb_leaf'] >> 12 << 10) | 1}
        rows = []
        for phase, slot in enumerate((3, 35)):
            va = 0x40000000 + slot * 4096
            for offset, name in enumerate(('gcb_page', 'gcb_second')):
                writes[symbols['gcb_leaf'] + (slot + offset) * 8] = (symbols[name] >> 12 << 10) | 0xcb
            for i, value in enumerate([p.geometry.GUARD, *p.expected_words(), p.geometry.GUARD]):
                writes[symbols['gcb_out'] + phase * 80 + i * 8] = value
            for i, value in enumerate([9, va + 4096 + 32, 0, 0x800]):
                writes[symbols['gcb_traps'] + phase * 32 + i * 8] = value
            rows += [SimpleNamespace(pc=pc, instruction=0x12000073 if pc == va + 4092 else 0x13,
                                     vector_writes={}, memory_accesses=[], gpr_writes={})
                     for pc in range(va + 3840, va + 4096 + 32, 4)]
            rows.append(SimpleNamespace(pc=0x80002000, instruction=0x34202573,
                                        vector_writes={}, memory_accesses=[], gpr_writes={10: 9}))
        rows.append(SimpleNamespace(pc=0x80003000, instruction=0x13, vector_writes={},
                                    memory_accesses=list(writes.items()), gpr_writes={}))
        return rows, symbols

    def test_complete_architecture_not_window(self):
        rows, symbols = self.fixture()
        result = p.validate(rows, symbols)
        self.assertFalse(result['runtime_window_verified'])
        self.assertFalse(result['coverage_admitted'])

    def test_wrong_opcode(self):
        rows, symbols = self.fixture()
        next(c for c in rows if c.pc == 0x40003ffc).instruction = 0x13
        with self.assertRaises(ValueError): p.validate(rows, symbols)

    def test_missing_retirement(self):
        rows, symbols = self.fixture()
        with self.assertRaises(ValueError): p.validate(rows[1:], symbols)

    def test_wrong_output(self):
        rows, symbols = self.fixture()
        rows[-1].memory_accesses.append((symbols['gcb_out'] + 8, 0))
        with self.assertRaises(ValueError): p.validate(rows, symbols)

    def test_duplicate_tohost(self):
        rows, symbols = self.fixture()
        rows[-1].memory_accesses.append((symbols['tohost'], 1))
        with self.assertRaises(ValueError): p.validate(rows, symbols)

    def test_wrong_trap(self):
        rows, symbols = self.fixture()
        rows[-1].memory_accesses.append((symbols['gcb_traps'], 2))
        with self.assertRaises(ValueError): p.validate(rows, symbols)

    def test_wrong_layout(self):
        rows, symbols = self.fixture()
        symbols['gpf_sfence'] -= 4
        with self.assertRaises(ValueError): p.validate(rows, symbols)

    def test_window_exact(self):
        self.assertTrue(p.window_target(21, 'WAIT_GRANT', True))
        self.assertFalse(p.window_target(21, 'WAIT_GRANT', True, grant=True))
        self.assertTrue(p.window_target(25, 'WAIT_RVALID', True, rvalid=True))
        self.assertFalse(p.window_target(25, 'WAIT_RVALID', True))
        self.assertFalse(p.window_target(25, 'WAIT_RVALID', False, rvalid=True))
        self.assertFalse(p.window_target(21, 'PTE_LOOKUP', True))

    def test_target_hit_rejected(self):
        bitmap = dict(tests=list(range(737)), metrics=dict(fsm={p.SCOPE:
            dict(checksum='3345966803', width=35, bits='0')}))
        self.assertEqual(len(p.targets(bitmap)), 2)
        bad = copy.deepcopy(bitmap)
        bad['metrics']['fsm'][p.SCOPE]['bits'] = hex(1 << (34 - 21))
        with self.assertRaises(ValueError): p.targets(bad)


if __name__ == '__main__':
    unittest.main()
