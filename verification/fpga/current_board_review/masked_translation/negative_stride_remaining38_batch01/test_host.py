"""Small parameter/oracle negatives; no simulator or sealed-output mutation."""
import copy
import unittest
import prepare as p


class Host(unittest.TestCase):
    def tuple(self, **kw):
        t = dict(unmapped=1, store=0, boundary=3, mode=2, split=0, gap=3)
        t.update(kw)
        return t

    def test_fault_two_not_boundary_one(self):
        g = p.geometry(self.tuple(boundary=1))
        self.assertEqual((g['fault_start'], g['fault_offset'], g['completed']), (2, 4086, []))

    def test_fault_five_with_completed_two(self):
        g = p.geometry(self.tuple())
        self.assertEqual((g['fault_start'], g['fault_offset'], g['completed']), (5, 4078, [2]))

    def test_alloff_no_fault_or_poison(self):
        for b in (1, 3, 5):
            for s in (0, 1):
                g = p.geometry(self.tuple(boundary=b, mode=3, store=s))
                self.assertEqual((g['fault_start'], g['expected_faults'], g['completed']), (None, 0, []))
                self.assertTrue(g['repair_after_target_return'])

    def test_permission_not_refill(self):
        self.assertEqual(p.geometry(self.tuple(unmapped=0))['refill_halfwords'], 0)
        self.assertEqual(p.geometry(self.tuple())['refill_halfwords'], 2048)

    def test_gap_changes_address_not_mask_or_start(self):
        a, b = (p.geometry(self.tuple(gap=n)) for n in (1, 3))
        self.assertEqual((a['stride'], a['fault_offset']), (-4, 4086))
        self.assertEqual((b['stride'], b['fault_offset']), (-8, 4078))
        self.assertEqual(a['fault_start'], b['fault_start'])

    def test_input_fullcap_and_unused_arrays(self):
        rows = list(p.oracle_rows(self.tuple()))
        self.assertEqual(len(rows), 4435)
        self.assertIn('I 63 920 126', rows)
        self.assertIn('I 127 0 254', rows)
        self.assertIn('B 129 91', rows)

    def test_reject_parameter_mutations(self):
        for kw in (dict(unmapped=True), dict(gap=0), dict(split=1), dict(boundary=5), dict(mode=0)):
            with self.subTest(kw=kw), self.assertRaises(ValueError):
                p.geometry(self.tuple(**kw))

    def test_reject_fulloracle_mutations(self):
        t = self.tuple()
        rows = list(p.oracle_rows(t))
        p.compare_rows(t, '\n'.join(rows))
        selectors = ['C ', 'I 63 ', 'I 127 ', 'K 15 ', 'B 0 ', 'B 65 ',
                     'B 129 ', 'V 2 ', 'V 5 ', 'V 63 ', 'D 0 ', 'D 2051 ', 'D 4095 ']
        for selector in selectors:
            bad = copy.copy(rows)
            i = next(i for i, row in enumerate(bad) if row.startswith(selector))
            fields = bad[i].split()
            fields[-1] = str(int(fields[-1]) ^ 1)
            bad[i] = ' '.join(fields)
            with self.subTest(selector=selector), self.assertRaises(ValueError):
                p.compare_rows(t, '\n'.join(bad))
        for bad in (rows[:-1], rows + [rows[-1]], list(reversed(rows))):
            with self.assertRaises(ValueError):
                p.compare_rows(t, '\n'.join(bad))

    def test_alloff_unmodified_original_memory(self):
        for row in p.oracle_rows(self.tuple(mode=3, store=1)):
            fields = row.split()
            if fields[0] == 'D':
                self.assertEqual(fields[2], fields[3])

    def test_store_prefix_poison_distinct_from_load(self):
        store = set(p.oracle_rows(self.tuple(store=1)))
        self.assertIn('V 2 127', store)
        self.assertIn(f'D 2051 {p.original(2051)} 36', store)
        self.assertIn('V 5 166', store)


if __name__ == '__main__':
    unittest.main()
