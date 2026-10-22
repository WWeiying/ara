"""Read-only tests of the actual sealed three-ELF fixture; no simulation."""
from pathlib import Path
import unittest
from elftools.elf.elffile import ELFFile
import prepare_fpu_reset_matrix as fixture

SEAL = '2f77429d088359d1f0904b125e31bb61ea26e45cb6d76804a2270a1341991e33'


def elf_bytes(path, address, size):
    with Path(path).open('rb') as stream:
        chunks = [s.data()[address-s['p_vaddr']:address-s['p_vaddr']+size]
                  for s in ELFFile(stream).iter_segments()
                  if s['p_type'] == 'PT_LOAD' and s['p_vaddr'] <= address
                  and address+size <= s['p_vaddr']+s['p_filesz']]
    fixture.require(len(chunks) == 1, 'ELF address ambiguous or missing')
    return chunks[0]


def shape(elf, symbols, sew):
    words = {name: int.from_bytes(elf_bytes(elf, symbols[name], 4), 'little')
             for name in ('fpar_mul', 'fpar_div', 'fpar_first_ar_load')}
    fixture.require(words['fpar_mul'] == 0x92001457 and
                    words['fpar_div'] == 0x82881c57, 'MUL v8/v0/v0 -> DIV v24/v8/v16')
    fixture.require(words['fpar_first_ar_load'] ==
                    {16: 0x020ad007, 32: 0x020ae007, 64: 0x020f7007}[sew],
                    'Exact first Ara load/EEW/base/register')
    begin = symbols['fpar_div']+4
    fixture.require(symbols['fpar_first_ar_load']-begin == 128 and
                    elf_bytes(elf, begin, 128) == bytes.fromhex('13000000')*32,
                    'Fixed NOP window (not a stage latency proof)')


class BoundShape(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pre = fixture.life.read_bound(fixture.PRE/'preflight.json', SEAL)

    def test_all_pins_and_745_identity(self):
        fixture.life.check(self.pre['pins'])
        self.assertEqual(self.pre['baseline'], 745)
        self.assertEqual([c['sew'] for c in self.pre['cases']], [16, 32, 64])
        self.assertEqual(len(self.pre['targets']), 16)

    def test_actual_three_instruction_shapes(self):
        for c in self.pre['cases']:
            shape(c['ELF'], c['symbols'], c['sew'])

    def test_wrong_sew_rejected(self):
        c = self.pre['cases'][0]
        with self.assertRaises(ValueError):
            shape(c['ELF'], c['symbols'], 32)

    def test_wrong_site_rejected(self):
        c = self.pre['cases'][0]
        symbols = dict(c['symbols'], fpar_div=c['symbols']['fpar_mul'])
        with self.assertRaises(ValueError):
            shape(c['ELF'], symbols, 16)

    def test_actual_spike_vtype_before_div(self):
        for c in self.pre['cases']:
            commits = fixture.old.shared.shared.spike_trace.parse_spike_commits(
                Path(c['spike_trace']))
            setup = [x for x in commits if x.pc < c['symbols']['fpar_mul']
                     and x.instruction & 127 == 87 and x.instruction >> 12 & 7 == 7]
            self.assertTrue(setup)
            # Last vsetvli immediate: LMUL8, requested SEW, undisturbed tail/mask.
            self.assertEqual(setup[-1].instruction >> 20 & 0x7ff,
                             {16: 11, 32: 19, 64: 27}[c['sew']])
            self.assertEqual(c['active_cores'], {16: 16, 32: 8, 64: 4}[c['sew']])


if __name__ == '__main__':
    unittest.main()
