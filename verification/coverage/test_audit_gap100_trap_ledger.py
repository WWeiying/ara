import json
import unittest
from pathlib import Path

import audit_gap100_trap_ledger as m


class LedgerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pre = m.runner.life.read_bound(m.runner.PRE / 'preflight-manifest.json', m.runner.PRE_SEAL)
        cls.symbols = dict(pre['symbols'], g100_return=m.software.shared._elf_symbol(Path(pre['input_elf']),
                          m.software.shared.LLVM / 'llvm-readelf', 'g100_return'))
        cls.text = (m.runtime.RUN / 'trace_hart_0.log').read_text()
        cls.rows = m.runtime.commit_rows(m.runtime.RUN / 'commit_trace.csv')

    def test_actual_full_ledger(self):
        result = m.audit(self.rows, self.text, self.symbols)
        self.assertEqual(result['exceptions'], 23)
        self.assertEqual(sum(x['rvfi_trap'] is not None for x in result['ledger']), 15)

    def test_unknown_or_missing_exception(self):
        for text in (self.text.replace('Illegal Instruction', 'Unknown Trap', 1),
                     self.text.replace('Exception @', 'Omitted @', 1)):
            with self.assertRaises(ValueError):
                m.audit(self.rows, text, self.symbols)

    def test_wrong_tval(self):
        text = self.text.replace('tval: 00000000c0302f73', 'tval: 00000000c0302f72', 1)
        self.assertNotEqual(text, self.text)
        with self.assertRaises(ValueError):
            m.audit(self.rows, text, self.symbols)

    def test_extra_rvfi_trap(self):
        rows = [dict(r) for r in self.rows]
        rows[0]['trap'] = 1
        with self.assertRaises(ValueError):
            m.audit(rows, self.text, self.symbols)

    def test_wrong_handler_return(self):
        rows = [dict(r) for r in self.rows]
        ret = next(r for r in rows if r['insn'] == 0x30200073 and r['pc'] < self.symbols['g100_s_table'])
        ret['insn'] = 0x10200073
        with self.assertRaises(ValueError):
            m.audit(rows, self.text, self.symbols)

    def test_terminal_tail_not_arbitrary(self):
        for text in (self.text.replace('0000a001', '0000a005'), self.text + self.text.splitlines()[-1] + '\n'):
            self.assertNotEqual(text, self.text)
            with self.assertRaises(ValueError):
                m.audit(self.rows, text, self.symbols)

    def test_wrong_resume_epc_write(self):
        rows = [dict(r) for r in self.rows]
        write = next(i for i, r in enumerate(rows) if r['insn'] >> 20 == 0x341 and
                     (r['insn'] >> 12) & 7 == 1 and
                     self.symbols['g100_m_table'] <= r['pc'] < self.symbols['g100_s_table'])
        rs = (rows[write]['insn'] >> 15) & 31
        previous = next(r for r in reversed(rows[:write]) if r['rd'] == rs)
        previous['rd_wdata'] += 4
        with self.assertRaisesRegex(ValueError, 'EPC write'):
            m.audit(rows, self.text, self.symbols)


if __name__ == '__main__':
    unittest.main()
