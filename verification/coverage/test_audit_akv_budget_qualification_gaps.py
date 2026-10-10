import unittest
from unittest.mock import patch

import audit_akv_budget_qualification_gaps as audit


class Tests(unittest.TestCase):
    def test_seed(self):
        self.assertEqual(audit.expected_halfword(0,255),0x9000+255*13)

    def test_row_and_tail(self):
        self.assertEqual(audit.expected_halfword(24,63),0x7700+63*7)
        self.assertEqual(audit.expected_halfword(24,64),0x9000+64*13)
        self.assertEqual(audit.expected_halfword(25,0),0x9000)

    def test_bounds(self):
        for p,i in [(-1,0),(26,0),(0,256)]:
            with self.assertRaises(ValueError): audit.expected_halfword(p,i)

    def test_actual_descriptor_readback(self):
        record,_ = audit.inspect(audit.old.DESCRIPTOR,audit.RUNS[audit.old.DESCRIPTOR])
        self.assertEqual(record['independent_destination_readback']['independently_checked_bytes'],13312)
        self.assertFalse(record['full_ISA_qualified'])

    def test_corrupt_independent_expected_rejected(self):
        with patch.object(audit,'expected_halfword',return_value=0):
            with self.assertRaisesRegex(ValueError,'Independent destination mismatch'):
                audit.inspect(audit.old.DESCRIPTOR,audit.RUNS[audit.old.DESCRIPTOR])


if __name__ == '__main__': unittest.main()
