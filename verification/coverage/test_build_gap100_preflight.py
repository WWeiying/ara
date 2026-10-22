import unittest
import struct
from types import SimpleNamespace

import build_gap100_preflight as m


class Gap100Test(unittest.TestCase):
    def test_hpm_permission_matrix(self):
        self.assertEqual([m.phase(i)[3] for i in range(12)],
                         [0, 0, 0, 0, 2, 2, 0, 0, 2, 2, 2, 0])

    def test_independent_signature(self):
        self.assertEqual(m.oracle(9)[9], 0x5a5)
        self.assertEqual(m.oracle(11)[9], 0)
        self.assertEqual(m.oracle(13)[4], (1 << 63) | 1)
        self.assertEqual(m.oracle(13)[7:9], [1, 1])
        self.assertEqual(m.oracle(14)[7:9], [0, 1])

    def test_phase_bounds(self):
        for row in (-1, 15):
            with self.assertRaises(ValueError):
                m.phase(row)

    def test_exact_static_population(self):
        self.assertEqual(len(m.TARGETS['cond']), 12)
        self.assertEqual(m.TARGETS['line'], {890})
        self.assertEqual(m.TARGETS['branch'], {587})

    def test_explicit_counter_isa(self):
        self.assertIn('_zicntr_zihpm', m.SPIKE_ISA)

    def test_unknown_trap_rejected(self):
        with self.assertRaises(ValueError):
            m.trap_distribution('core 0: exception trap_load_access_fault, epc 0x80000000')

    def test_exact_traps_and_duplicate_rejection(self):
        names = ['trap_illegal_instruction'] * 6 + ['trap_breakpoint', 'interrupt #1'] + \
                ['trap_user_ecall'] * 5 + ['trap_supervisor_ecall'] * 5 + ['trap_machine_ecall'] * 5
        trace = '\n'.join('exception ' + name + ', epc 0x80000000' for name in names)
        self.assertEqual(sum(m.trap_distribution(trace).values()), 23)
        for extra in ('\nexception interrupt #1, epc 0x80000000', '\nexception malformed'):
            with self.assertRaises(ValueError):
                m.trap_distribution(trace + extra)

    def test_entire_elf_window(self):
        blob = bytearray(1152)
        blob[:6] = b'\x7fELF\x02\x01'
        struct.pack_into('<HHIQQQIHHHHHH', blob, 16, 2, 243, 1, 0x80000000, 0, 64, 0, 64, 0, 0, 64, 1, 0)
        struct.pack_into('<IIQQQQIIQQ', blob, 64, 0, 1, 6, 4096, 128, 1024, 0, 0, 4, 0)
        blob[128:] = b'\x13\0\0\0' * 256
        symbols = dict(g100_irq_begin=4096, g100_irq_end=5120)
        m.validate_elf_window(blob, symbols)
        blob[-4] = 0x93
        with self.assertRaises(ValueError):
            m.validate_elf_window(blob, symbols)
        with self.assertRaises(ValueError):
            m.validate_elf_window(blob[:100], symbols)

    def commit(self, pc, **updates):
        fields = dict(pc=pc, instruction=0x13, gpr_writes={}, fpr_writes={},
                      vector_writes={}, csr_writes={}, memory_accesses=())
        fields.update(updates)
        return SimpleNamespace(**fields)

    def test_window_prefix(self):
        self.assertEqual(m.validate_window([self.commit(4096), self.commit(4100)],
                         dict(g100_irq_begin=4096, g100_irq_end=5120)), 2)

    def test_window_skip_rejected(self):
        with self.assertRaises(ValueError):
            m.validate_window([self.commit(4100)], dict(g100_irq_begin=4096, g100_irq_end=5120))

    def test_window_effect_rejected(self):
        for fields in (dict(gpr_writes={1: 0}), dict(memory_accesses=((0x80000000, 1),)),
                       dict(csr_writes={0x144: 2}), dict(instruction=0x100013)):
            with self.assertRaises(ValueError):
                m.validate_window([self.commit(4096, **fields)], dict(g100_irq_begin=4096, g100_irq_end=5120))

    def test_timeout_rejected(self):
        with self.assertRaises(ValueError):
            m.validate_window([self.commit(5120)], dict(g100_irq_begin=4096, g100_irq_end=5120))


if __name__ == '__main__':
    unittest.main()
