"""Independent arithmetic/buffer oracle and strict rejection tests; no EDA."""
import unittest
from unittest.mock import patch
import build_narrow_source_group_preflight as p


class Tests(unittest.TestCase):
    def test_instruction_decode_source_group_rejection(self):
        self.assertEqual(p.FAULT,0xba9a0c57)
        self.assertEqual((p.FAULT>>26,p.FAULT>>20&31,p.FAULT>>15&31,p.FAULT>>7&31),
                         (46,9,20,24))
        self.assertEqual(9&7,1)
        self.assertEqual((20&3,24&3),(0,0))

    def test_independent_guard_tail_oracle(self):
        source=p.expected_buffer('ng_source');recovered=p.expected_buffer('ng_recovered')
        self.assertEqual(len(source),528)
        for name in ('ng_source','ng_old','ng_dump','ng_recovered'):
            data=p.expected_buffer(name)
            self.assertEqual(data[:8]+data[520:],bytes([0xa5]*16))
        self.assertEqual(recovered[8:16],bytes((x+3)&255 for x in source[8:16]))
        self.assertEqual(recovered[16:520],bytes([0xa5]*504))
        self.assertEqual(p.expected_buffer('ng_dump'),p.expected_buffer('ng_old'))

    def test_unknown_buffer_rejected(self):
        with self.assertRaises(ValueError):p.expected_buffer('other')

    def test_check_count_not_reduced(self):
        self.assertEqual(p.CHECKS,4*528+2*6+4+1+1)
        self.assertIn('checks!=2130',p.APP.read_text())

    def test_wrong_trap_or_missing_trap_rejected(self):
        for text in ('','exception trap_load_access_fault, epc 0x80002000',
                     'exception trap_illegal_instruction, epc 0x80002004'):
            with self.assertRaises(ValueError):p.validate([],{'ng_fault':0x80002000},text)

    def test_existing_output_rejected_before_static_or_build(self):
        with patch.object(p,'static') as static:
            with self.assertRaises(ValueError):p.build(p.REFERENCE)
            static.assert_not_called()


if __name__=='__main__':unittest.main()
