import unittest
import preflight_akv_canonical_kfault as p


class TestCanonicalK(unittest.TestCase):
    def test_addresses(self):
        for a in p.ADDRESSES: p.address_gate(a)
        self.assertEqual(p.ADDRESSES[0] ^ p.ADDRESSES[1], 0xfffffffffffffff8)

    def test_bad_addresses(self):
        for a in (0, p.ADDRESSES[0]+1, 0x40002080, 0x8000000000):
            with self.assertRaises(Exception): p.address_gate(a)

    def test_pages(self):
        for i, a in enumerate(p.ADDRESSES):
            pages = p.pages(0x80040000, i, True)
            self.assertEqual(pages[2][a >> 12 & 511], 0)
            self.assertEqual(pages[3][4], a)
            self.assertNotEqual(pages[2][2], 0)
            repaired = p.pages(0x80040000, i, False)
            changed = [(j,k) for j in range(6) for k in range(512) if pages[j][k] != repaired[j][k]]
            self.assertEqual(changed, [(2, a >> 12 & 511)])

    def test_generated_contract(self):
        for i, a in enumerate(p.ADDRESSES):
            data, header, unit = p.phase_sources(i)
            self.assertIn(hex(a), data)
            self.assertIn(hex(a), header)
            self.assertIn('.word 0x00b5205b', header)
            self.assertIn('.word 0x0000505b', header)
            self.assertNotIn('void rvtest_init', header)
            self.assertIn('int akvc%d_run(void)' % i, header)
            self.assertIn('0x43', data)

    def test_source_drift(self):
        with self.assertRaises(Exception): p.replace_one('a a', 'a', 'b')
        with self.assertRaises(Exception): p.replace_one('x', 'a', 'b')

    def test_empty_trace(self):
        with self.assertRaises(Exception): p.software_trace('', {})


if __name__ == '__main__': unittest.main()
