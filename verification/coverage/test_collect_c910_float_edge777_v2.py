import copy
import csv
import unittest
import collect_c910_float_edge777_v2 as q


class RawStoreContext(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = q.life.OUT / 'c910-float-edge-vcs777-parent-20261007-01'
        cls.symbols = q.old.runner.preflight()['symbols']
        cls.reference = q.old.reference_prefix(q.old.runner.preflight())
        _, _, cls.activities = q.old.vc._parse_vector_trace(cls.directory / 'vector_trace.csv')
        s, r, x = q.old.vc._parse_architecture_mapping(cls.directory / 'commit_trace.csv')
        cls.mapping = q.old.vc._map_spike_commits(q.old.vc._map_architecture_retires(s, r, x), cls.reference)
        with (cls.directory / 'vector_trace.csv').open(newline='') as stream:
            cls.rows = list(csv.DictReader(stream))
        cls.index = next(i for i, row in enumerate(cls.rows) if row['event'] == 'alloc' and row['arch_seq'] == '6')

    def bind(self, rows):
        return q.store_context(rows, self.reference, self.activities, self.mapping, self.symbols)

    def test_actual48_store_context_and_all192_operations(self):
        bound = self.bind(self.rows)
        self.assertIsNone(self.activities[6].eew)
        self.assertEqual((bound[6].eew, bound[6].vl, bound[6].vstart), (1, 16, 0))
        result = q.old.native_state(self.reference, bound, self.mapping, self.symbols)
        self.assertEqual(result['operations']['store'], 48)
        self.assertEqual(result['defined_bytes'], 4608)
        for seq in self.activities:
            if self.reference[self.mapping[seq]].pc not in {self.symbols['edge_store'+str(w)] for w in (16,32,64)}:
                self.assertIs(bound[seq], self.activities[seq])

    def test_wrong_raw_store_metadata_rejected(self):
        for key, value in [('eew','3'), ('vl','15'), ('vstart','1'), ('use_vd','1'),
                           ('vd','24'), ('insn','00000000'), ('vid','7'), ('arch_seq','7')]:
            rows = copy.deepcopy(self.rows); rows[self.index][key] = value
            with self.assertRaises(ValueError, msg=key): self.bind(rows)

    def test_missing_duplicate_or_write_store_rejected(self):
        for case in ('missing', 'duplicate', 'write'):
            rows = copy.deepcopy(self.rows)
            if case == 'missing': rows.pop(self.index)
            elif case == 'duplicate': rows.append(copy.deepcopy(rows[self.index]))
            else:
                row = copy.deepcopy(rows[self.index]); row['event'] = 'write'; rows.append(row)
            with self.assertRaises(ValueError, msg=case): self.bind(rows)


if __name__ == '__main__': unittest.main()
