import copy
import unittest
from pathlib import Path

import collect_c910_store_context_parent as adapter


class StoreContextTests(unittest.TestCase):
    def fixture(self):
        activities, rows = {}, []
        for seq in range(48):
            eew = 1 + seq // 16
            insn = 0x02000027 | ((eew + 4) << 12) | (24 << 7)
            activities[seq] = adapter.original.vc.ArchActivity(
                instruction=insn, allocations=1, completions=1, vd=24)
            row = dict(arch_seq=str(seq), insn='%08x' % insn, vid=str(seq % 8),
                       use_vd='0', vd='0', eew=str(eew), vl=str(32 >> eew),
                       vstart='0', nr_lanes='4', vlen_bits='1024')
            rows += [dict(row, event='alloc', cycle=str(seq * 4)),
                     dict(row, event='done', cycle=str(seq * 4 + 3))]
        return activities, rows

    def test_restore_exact_without_changing_input(self):
        activities, rows = self.fixture()
        result = adapter.restore_stores(activities, rows)
        for seq, activity in result.items():
            self.assertEqual((activity.eew, activity.vl, activity.vstart),
                             (1 + seq // 16, 32 >> (1 + seq // 16), 0))
            self.assertIsNone(activities[seq].eew)

    def test_bad_raw_fields_rejected(self):
        for field, value in [('insn', '00000027'), ('eew', '3'), ('vl', '15'),
                             ('vstart', '1'), ('use_vd', '1'), ('vd', '24'),
                             ('vid', '8'), ('nr_lanes', '2'), ('vlen_bits', '512')]:
            activities, rows = self.fixture()
            rows[0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                adapter.restore_stores(activities, rows)

    def test_done_identity_and_order_rejected(self):
        for field, value in [('vid', '1'), ('cycle', '-1'), ('eew', '2'),
                             ('vl', '15'), ('vstart', '1')]:
            activities, rows = self.fixture()
            rows[1][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                adapter.restore_stores(activities, rows)

    def test_missing_duplicate_or_write_rejected(self):
        for mode in ('missing', 'duplicate', 'write'):
            activities, rows = self.fixture()
            if mode == 'missing': rows.pop(0)
            elif mode == 'duplicate': rows.append(copy.deepcopy(rows[0]))
            else: rows.append(dict(rows[0], event='write'))
            with self.subTest(mode=mode), self.assertRaises(ValueError):
                adapter.restore_stores(activities, rows)

    def test_parser_contract_changes_rejected(self):
        for field, value in [('eew', 1), ('use_vd', True), ('completions', 0)]:
            activities, rows = self.fixture()
            setattr(activities[0], field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                adapter.restore_stores(activities, rows)

    def test_actual_frozen_raw_trace_all48_stores(self):
        path = adapter.life.OUT / 'c910-float-edge-vcs777-parent-20261007-01/vector_trace.csv'
        _, _, activities = adapter.original.vc._parse_vector_trace(path)
        rows = adapter.original.common.read_csv(path.read_bytes(), adapter.original.common.VECTOR_FIELDS)
        result = adapter.restore_stores(activities, rows)
        self.assertEqual(sum(a.instruction & 127 == 0x27 for a in result.values()), 48)
        for seq, a in activities.items():
            if a.instruction & 127 != 0x27:
                self.assertEqual(a, result[seq])


if __name__ == '__main__':
    unittest.main()
