import json
from pathlib import Path
import unittest

import system_rvfi_native_el as m


class ActualNative(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.out = m.sealed.life.OUT / 'system-rvfi788-native-agent-20261007-03'
        cls.c = m.sealed.life.read_bound(cls.out/'config.json', 'c610434fd6f2d8d20487c01bd61160487e5260b8b646a861b529f8ae9b2a9480')
        cls.text = (cls.out/'first.el').read_text()

    def reject(self, text):
        with self.assertRaises(ValueError):
            m.records(text, self.c)

    def test_actual_full788(self):
        self.assertEqual(len(m.records(self.text, self.c)), 788)
        self.assertEqual(len(m.sealed.inventory(self.out, self.c, 'before')), 1206)
        self.assertEqual((self.out/'cleanup-empty.el').read_bytes(), b'')

    def test_direction_order_irrelevant(self):
        a = 'Toggle 0to1 rvfi_to_iti.ex_valid "logic rvfi_to_iti.ex_valid"'
        b = a.replace('0to1', '1to0')
        self.assertEqual(m.records(self.text.replace(a+'\n'+b, b+'\n'+a), self.c), m.records(self.text, self.c))

    def test_missing_direction(self):
        self.reject(self.text.replace('Toggle 1to0 rvfi_to_iti.ex_valid "logic rvfi_to_iti.ex_valid"\n', '', 1))

    def test_duplicate_direction(self):
        self.reject(self.text.replace('Toggle 1to0 rvfi_to_iti.ex_valid', 'Toggle 0to1 rvfi_to_iti.ex_valid', 1))

    def test_reversed_bounds(self):
        self.reject(self.text.replace('rvfi_csr.acc_cons.rdata[63:0]', 'rvfi_csr.acc_cons.rdata[0:63]', 1))

    def test_nonzero_bit(self):
        self.reject(self.text.replace('issue_instr_ack [0]', 'issue_instr_ack [1]', 1))

    def test_out_of_bounds(self):
        self.reject(self.text.replace('issue_instr_ack[0:0]', 'issue_instr_ack[1:1]', 1))

    def test_scalar_selector_forbidden(self):
        self.reject(self.text.replace('0to1 rvfi_to_iti.ex_valid "', '0to1 rvfi_to_iti.ex_valid [0] "', 1))

    def test_foreign_protected(self):
        self.reject(self.text+'Toggle clk_i "logic clk_i"\n')

    def test_pair_attribute_mutation(self):
        self.reject(self.text.replace('1to0 rvfi_to_iti.ex_valid "logic', '1to0 rvfi_to_iti.ex_valid "wire', 1))

    def test_checksum_scope_annotation(self):
        for before, after in [('3385959260', '3385959261'), ('INSTANCE: ara_tb.dut.i_ara_soc.i_system', 'INSTANCE: ara_tb'),
                              ('Observation-only parent RVFI net', 'Foreign annotation')]:
            self.reject(self.text.replace(before, after, 1))

    def test_mixed_whole_pair(self):
        self.reject(self.text+'Toggle rvfi_to_iti.ex_valid "logic rvfi_to_iti.ex_valid"\n')


if __name__ == '__main__':
    unittest.main()
