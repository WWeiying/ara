import unittest
import build_csr_cause_wlrl788 as m

class GoldTests(unittest.TestCase):
    def test_complete_gold(self):
        result = m.expected(0)
        self.assertEqual(len(result), 42)
        self.assertEqual(result[3:9], [0, 0, 0, 0, (1 << 64)-1, 0])
        self.assertEqual(result[-3:], [0, 0, 0])

    def test_mie_rejected(self):
        with self.assertRaises(ValueError): m.expected(8)

    def test_mprv_rejected(self):
        with self.assertRaises(ValueError): m.expected(1 << 17)

    def test_bool_status_rejected(self):
        with self.assertRaises(ValueError): m.expected(False)

    def test_source_contract(self):
        pins = {}; result = m.source_contract(pins)
        self.assertFalse(result['portable_exception_codes'])
        self.assertEqual(result['write_csrs'], [0x342, 0x142])
        self.assertGreaterEqual(len(pins), 6)

if __name__ == '__main__': unittest.main()
