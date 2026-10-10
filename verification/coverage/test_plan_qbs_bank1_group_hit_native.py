import unittest

import plan_qbs_bank1_group_hit_native as p


class ExactContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.plan = p.collect()
        cls.expected = []
        for scope, nodes in cls.plan['protected_scopes'].items():
            for n in nodes:
                a = n['attributes']
                if n['tag'] == 'arrays':
                    cls.expected.append((scope, a['name'], 'array', 'whole-protected'))
                    continue
                lo, hi = sorted((int(a.get('left', '0')), int(a.get('right', '0'))))
                cls.expected.extend((scope, a['name'], b, d) for b in range(lo, hi+1)
                                    for d in ('0to1', '1to0'))

    def stages(self):
        selected = p.atoms(self.plan)
        return {s: [(k, k in selected and s in ('selected', 'reloaded')) for k in self.expected]
                for s in p.STAGES}

    def rejects(self, stages):
        with self.assertRaises((ValueError, RuntimeError, AssertionError)):
            p.check_stages(self.plan, stages)

    def test_exact_partition(self):
        self.assertEqual((len(p.atoms(self.plan)), self.plan['parent_non_target_objects'],
                          self.plan['target_vector_retained_bits']), (3232, 3214, 688))
        self.assertEqual(self.plan['mapping_permitted_missing_coordinates_protected'], 704)

    def test_equivalent_reordered_directions(self):
        stages = self.stages()
        stages['reloaded'].reverse()
        self.assertFalse(p.check_stages(self.plan, stages)['native_qualified'])

    def test_missing_stage(self):
        s = self.stages(); del s['final']; self.rejects(s)

    def test_duplicate_direction(self):
        s = self.stages(); s['reloaded'][1] = s['reloaded'][0]; self.rejects(s)

    def test_foreign_bit(self):
        s = self.stages(); k, v = s['selected'][0]
        s['selected'][0] = ((k[0], k[1], 999, k[3]), v); self.rejects(s)

    def test_foreign_direction(self):
        s = self.stages(); k, v = s['selected'][0]
        s['selected'][0] = ((*k[:3], 'whole'), v); self.rejects(s)

    def test_protected_bit_changed(self):
        s = self.stages()
        i = next(i for i, (k, _) in enumerate(s['selected']) if k not in p.atoms(self.plan))
        k, _ = s['selected'][i]; s['selected'][i] = (k, True); self.rejects(s)

    def test_missing_target_direction(self):
        s = self.stages(); i = next(i for i, (_, v) in enumerate(s['selected']) if v)
        k, _ = s['selected'][i]; s['selected'][i] = (k, False); self.rejects(s)

    def test_reset_not_empty(self):
        s = self.stages(); k, _ = s['reset'][0]; s['reset'][0] = (k, True); self.rejects(s)

    def test_excluded_int_not_boolean(self):
        s = self.stages(); k, _ = s['before'][0]; s['before'][0] = (k, 0); self.rejects(s)

    def test_actual791_rebase(self):
        self.assertEqual(self.plan['measured_population'], 791)
        self.assertEqual(self.plan['actual790_791_target_new_directions'], 0)

    def test_child_array_not_excludable(self):
        s = self.stages()
        i = next(i for i, (k, _) in enumerate(s['selected']) if k[2] == 'array')
        k, _ = s['selected'][i]; s['selected'][i] = (k, True); self.rejects(s)


if __name__ == '__main__':
    unittest.main()
