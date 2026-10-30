"""Host profile invariants; exporter syntax is proved separately on real FSDB."""
import copy
from pathlib import Path
import sys
import unittest

sys.dont_write_bytecode = True
sys.path.insert(0, str(Path(__file__).resolve().parent))
import adapter
import member_profile as m


class MemberProfileTests(unittest.TestCase):
    def profile(self, shared=False):
        return adapter.c.prep.wave.profile(shared)

    def test_exact_45_path_delta_both_topologies_and_input_unchanged(self):
        for shared in (False, True):
            original = self.profile(shared)
            saved = copy.deepcopy(original)
            new = m.successor(original)
            self.assertEqual(original, saved)
            self.assertEqual(set(new), set(original))
            changed = 0
            for before, after in zip(original['signals'], new['signals']):
                if before['alias'] in m.members():
                    root, member = m.members()[before['alias']]
                    self.assertEqual(after['path'], m.CUT+root+'.'+member)
                    self.assertEqual({**after, 'path':before['path']}, before)
                    changed += 1
                else:
                    self.assertEqual(before, after)
            self.assertEqual(changed, 45)
            for key in set(original)-{'signals'}:
                self.assertEqual(new[key], original[key])

    def test_missing_duplicate_changed_path_and_member_properties_reject(self):
        original = self.profile()
        index = next(i for i, row in enumerate(original['signals']) if row['alias'] == 'up_ar_addr')
        mutations = [('path', m.CUT+'slv_req_i/ar/wrong'), ('format', 'b'),
                     ('required', False), ('alias', 'unknown_alias')]
        for field, value in mutations:
            bad = copy.deepcopy(original); bad['signals'][index][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.successor(bad)
        for mutation in ('missing', 'duplicate'):
            bad = copy.deepcopy(original)
            if mutation == 'missing': del bad['signals'][index]
            else: bad['signals'].append(copy.deepcopy(bad['signals'][index]))
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                m.successor(bad)

    def test_clock_edge_unit_and_double_application_reject(self):
        for field, value in (('clock', '/wrong/clk'), ('edge', 'posedge'), ('raw_time_unit', 'ns')):
            bad = self.profile(); bad[field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                m.successor(bad)
        with self.assertRaises(ValueError): m.successor(m.successor(self.profile()))

    def test_no_hierarchy_rewrite(self):
        original = self.profile()
        new = m.successor(original)
        rows = {row['alias']:row for row in new['signals']}
        self.assertEqual(rows['up_ar_addr']['path'], m.CUT+'slv_req_i.ar.addr')
        self.assertEqual(rows['down_r_resp']['path'], m.CUT+'cut_resp.r.resp')
        self.assertEqual(rows['bus_ar_valid']['path'], m.CUT+'mst_req_o.ar_valid')
        for alias in ('cut_ar_a_full_q', 'r_ar_stalled_q', 'shim_state_q'):
            old = next(row for row in original['signals'] if row['alias'] == alias)
            self.assertEqual(rows[alias], old)


if __name__ == '__main__': unittest.main()
