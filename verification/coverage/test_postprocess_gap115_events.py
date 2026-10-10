import unittest
import postprocess_gap115_events as m


class Events(unittest.TestCase):
    def test_reused_id_not_concurrent(self):
        events = [(1, 1, 0, 0x13, 1, 0, 0), (2, 1, 0, 0x17, 1, 0, 0)]
        self.assertEqual(m.traffic(events), dict(requests=2, responses=2, aborted=0))

    def test_duplicate_orphan_exception(self):
        for events in [[(1, 0, None, None, 1, 0, 0)],
                       [(1, 1, 0, 0x13, 0, None, None), (2, 1, 0, 0x13, 0, None, None)],
                       [(1, 1, 0, 0x13, 1, 0, 1)]]:
            with self.assertRaises(ValueError): m.traffic(events)

    def fixture(self):
        rows = [dict(event='arch_start', order='37', cycle='10', insn='8602e457'),
                dict(event='uop_alloc', order='37', port='1', cycle='11')]
        vectors = [dict(event='alloc', arch_seq='37', vid='1', cycle='11', insn='8602e457')]
        return rows, vectors

    def test_exact_cancel(self):
        rows, vectors = self.fixture()
        self.assertEqual(m.backend(rows, vectors, {37})['aborted'], 1)

    def test_missing_cancel_or_owner(self):
        rows, vectors = self.fixture()
        with self.assertRaises(ValueError): m.backend(rows, vectors, set())
        vectors[0]['arch_seq'] = '38'
        with self.assertRaises(ValueError): m.backend(rows, vectors, {37})

    def test_write_after_done(self):
        rows, vectors = self.fixture()
        rows.append(dict(event='uop_done', order='37', port='1', cycle='12'))
        vectors.extend([dict(vectors[0], event='done', cycle='12'),
                        dict(vectors[0], event='write', cycle='13', lane='0', be='ff')])
        with self.assertRaises(ValueError): m.backend(rows, vectors, set())


if __name__ == '__main__': unittest.main()
