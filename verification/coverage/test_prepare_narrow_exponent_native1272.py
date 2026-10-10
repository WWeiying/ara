import copy
import json
from pathlib import Path
import unittest

import prepare_narrow_exponent_native1272 as p


class ExponentCoordinateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.inventory = json.loads(p.INVENTORY.read_bytes())
        static = json.loads(p.flags.STATIC.read_bytes())
        cls.design = p.prep.compiled.Design(Path(static['design_vdb']))
        cls.row = next(r for r in cls.inventory['targets'] if r['scope'].endswith('x_ct_vfdsu_srt'))
        definition = cls.design.definition(cls.row['scope'], 'branch')
        cls.spec = next(n for n in definition.iter('branch_spec') if n.get('id') == cls.row['point']['native_id'])

    def test_exact_signed_arm_and_WIDTH64_protection(self):
        target, item = p.classify(self.row['point'], self.spec, 1, False, p.OWNERS['x_ct_vfdsu_srt'])
        self.assertTrue(target)
        self.assertEqual(item['name'], "13'h1bce ")
        self.assertFalse(p.classify(self.row['point'], self.spec, 0, True, p.OWNERS['x_ct_vfdsu_srt'])[0])

    def test_explicit_default_remains_protected(self):
        row = next(r for r in self.inventory['protected'] if r['scope'] == self.row['scope'] and
                   r['point']['native_id'] == self.row['point']['native_id'])
        target, item = p.classify(row['point'], self.spec, 1, row['hit'], p.OWNERS['x_ct_vfdsu_srt'])
        self.assertFalse(target)
        self.assertEqual(item['name'], 'default')

    def test_hit_candidate_and_wrong_vector_rejected(self):
        with self.assertRaises(ValueError):
            p.classify(self.row['point'], self.spec, 1, True, p.OWNERS['x_ct_vfdsu_srt'])
        point = copy.deepcopy(self.row['point'])
        point['native_vector']['vector'] = '1' * 54
        with self.assertRaises(ValueError):
            p.classify(point, self.spec, 1, False, p.OWNERS['x_ct_vfdsu_srt'])

    def test_constant_default_and_source_corruption_rejected(self):
        for field, value in (('name', "13'h0000 "), ('file_id', 'wrong')):
            spec = copy.deepcopy(self.spec)
            spec.find('branch_cexpr/branch_citem').set(field, value)
            with self.subTest(field=field), self.assertRaises(ValueError):
                p.classify(self.row['point'], spec, 1, False, p.OWNERS['x_ct_vfdsu_srt'])
        spec = copy.deepcopy(self.spec)
        spec.find('branch_cexpr').remove(spec.find('branch_cexpr/branch_citem'))
        with self.assertRaises(ValueError):
            p.classify(self.row['point'], spec, 1, False, p.OWNERS['x_ct_vfdsu_srt'])

    def test_pack_or_other_group_not_a_target(self):
        point = dict(self.row['point'], line='178')
        self.assertEqual(p.classify(point, self.spec, 1, False, p.OWNERS['x_ct_vfdsu_srt']), (False, None))

    def test_exact_instance_net_connections(self):
        good = 'ff1 inst (.frac_bin_val (id_expnt[12:0]), .frac_num(frac));'
        self.assertEqual(p.connection(good, 'ff1', 'inst', 'frac_bin_val', 'id_expnt[12:0]')['net'], 'id_expnt[12:0]')
        for bad in ('// '+good, good+good, good.replace('id_expnt', 'wrong'),
                    good.replace('.frac_num(frac)', '.frac_bin_val(id_expnt[12:0])')):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                p.connection(bad, 'ff1', 'inst', 'frac_bin_val', 'id_expnt[12:0]')


if __name__ == '__main__':
    unittest.main()
