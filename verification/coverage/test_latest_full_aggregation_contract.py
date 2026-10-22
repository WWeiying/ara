import copy
import unittest
import latest_full_aggregation_contract as c


def row(family='mfpu272', role='target', **kwargs):
    value = dict(metric='Toggle', scope='ara_tb.dut.i_mfpu', checksum='123 456',
                 object='data[63:0]', direction='0to1', array=False,
                 low=0, high=63, role=role, family=family)
    value.update(kwargs)
    return value


class ContractTest(unittest.TestCase):
    def test_disjoint(self):
        self.assertEqual(c.intersection_review([row(), row('closed771', low=64, high=127)], []), [])

    def test_unreviewed_protection_collision(self):
        with self.assertRaises(ValueError):
            c.intersection_review([row(), row('closed771', 'protected')], [])

    def test_explicit_partial_ownership(self):
        a, b = row(low=32), row('closed771', 'protected')
        approval = c.identity(a) + (32, 63, 'closed771', 'mfpu272')
        result = c.intersection_review([a, b], [approval])
        self.assertEqual((result[0]['low'], result[0]['high']), (32, 63))

    def test_overbroad_approval(self):
        a, b = row(low=32), row('closed771', 'protected')
        with self.assertRaises(ValueError):
            c.intersection_review([a, b], [c.identity(a) + (0, 63, 'closed771', 'mfpu272')])

    def test_duplicate_target(self):
        with self.assertRaises(ValueError):
            c.intersection_review([row(), row()], [])

    def test_arrays_remain_opaque(self):
        with self.assertRaises(ValueError):
            c.identity(row(array=True))
        self.assertEqual(c.intersection_review([row('closed771', 'protected', array=True)], []), [])

    def test_index_identity_not_stripped(self):
        self.assertNotEqual(c.identity(row(object='a[0]')), c.identity(row(object='a')))

    def test_direction_distinct(self):
        self.assertEqual(c.intersection_review([row(), row('closed771', direction='1to0')], []), [])

    def test_metric_distinct(self):
        self.assertEqual(c.intersection_review([row(), row('branch720', metric='Branch', direction='selector')], []), [])

    def test_unknown_family_and_metric(self):
        for change in ({'family': 'pending'}, {'metric': 'Condition'}, {'low': True}):
            with self.assertRaises(ValueError):
                c.identity(row(**change))

    def test_final_population(self):
        previous = list(map(str, range(773)))
        final = dict(coverage_admitted=True, design='frozen', tests=previous + ['774'], metric_instances=6162)
        value = c.population_gate(final, previous, 'frozen', 'a' * 64)
        self.assertFalse(value['launch_authorized'])
        for key, bad in [('tests', previous), ('design', 'other'), ('metric_instances', 6161)]:
            changed = dict(final, **{key: bad})
            with self.assertRaises(ValueError):
                c.population_gate(changed, previous, 'frozen', 'a' * 64)

    def test_all_five_stages(self):
        rows = [row(), row('closed771', 'protected', low=64, high=127)]
        for stage in c.STAGES:
            flags = {c.identity(r) + (r['low'], r['high']): int(r['role'] == 'target' and
                     stage in ('applied', 'reloaded')) for r in rows}
            c.stage_gate(stage, rows, flags)
            broken = copy.deepcopy(flags)
            broken.pop(next(iter(broken)))
            with self.assertRaises(ValueError):
                c.stage_gate(stage, rows, broken)
        with self.assertRaises(ValueError):
            c.stage_gate('raw', [row()], {c.identity(row()) + (0, 63): True})


if __name__ == '__main__':
    unittest.main()
