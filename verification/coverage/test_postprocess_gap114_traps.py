import unittest
import postprocess_gap114_traps as m


class Traps(unittest.TestCase):
    def fixture(self):
        symbols = dict(g114_trap_a=0x800020a8, g114_trap_b=0x800020bc, g114_trap_recovery=0x800020d8)
        pcs = [symbols[n] for phase in range(4) for n in
               ('g114_trap_a' if phase < 2 else 'g114_trap_b', 'g114_trap_recovery')]
        return symbols, [dict(event='retire', order=str(i), pc=hex(pc), insn='00000073', trap='1')
                         for i, pc in enumerate(pcs)]

    def test_exact(self):
        symbols, rows = self.fixture(); self.assertEqual(m.traps_exact(rows, symbols)['traps'], 8)

    def test_mutations(self):
        for field, value in [('pc', '0x80002000'), ('insn', '00000013'), ('trap', '2'), ('order', '99')]:
            symbols, rows = self.fixture(); rows[0][field] = value
            with self.assertRaises(ValueError): m.traps_exact(rows, symbols)

    def test_missing(self):
        symbols, rows = self.fixture()
        with self.assertRaises(ValueError): m.traps_exact(rows[:-1], symbols)


if __name__ == '__main__': unittest.main()
