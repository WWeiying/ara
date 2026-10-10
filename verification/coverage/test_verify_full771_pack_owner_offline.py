import copy
import json
import unittest
import verify_full771_pack_owner_offline as p


class ExactOwnerTests(unittest.TestCase):
    def fixture(self):
        groups, instances, bindings, authority = {}, [], {}, set()
        for index in range(16):
            scope = 'vector.pack%d' % index
            ref = []
            targets = []
            for name, (left, right, typ) in p.NAMES.items():
                b = dict(left=left, right=right, native_type=typ, design_checksum='1', toggle_checksum='2')
                bindings[scope, name] = b
                authority.add((scope, name, json.dumps(b, sort_keys=True)))
                ref.append(['path', 'meta', '%s[%d:%d]' % (name, left, right)])
                targets.append(dict(name=name))
            ref.append(['port', 'port', 'vfdsu_ex4_expnt_rst[12:0]'])
            groups['pack323%d' % index] = dict(scope=scope, reference=ref, targets=[])
            instances.append(dict(scope=scope, module='ct_vfdsu_pack', targets=targets,
                                  design_checksum='1', toggle_checksum='2'))
        groups['pack323scalar'] = dict(scope='scalar.pack', reference=[], targets=[])
        instances.append(dict(scope='scalar.pack', module='ct_vfdsu_pack', targets=[]))
        return groups, instances, bindings, authority

    def test_exact_and_immutable(self):
        args = self.fixture()
        original = copy.deepcopy(args[0])
        groups, proof, expected = p.corrected_groups(*args)
        self.assertEqual(args[0], original)
        self.assertEqual((len(proof), len(expected)), (16, 48))
        self.assertEqual(groups['pack323scalar']['targets'], [])
        self.assertNotIn('vfdsu_ex4_expnt_rst[12:0]', groups['pack3230']['targets'])

    def test_missing_owner(self):
        args = self.fixture(); args[3].pop()
        with self.assertRaises(ValueError): p.corrected_groups(*args)

    def test_wrong_bounds(self):
        args = self.fixture(); args[2]['vector.pack0', 'ex4_expnt_rst']['left'] = 11
        with self.assertRaises(ValueError): p.corrected_groups(*args)

    def test_wrong_native_type(self):
        args = self.fixture(); args[2]['vector.pack0', 'ex4_frac']['native_type'] = 'reg'
        with self.assertRaises(ValueError): p.corrected_groups(*args)

    def test_wrong_checksum(self):
        args = self.fixture(); args[1][0]['toggle_checksum'] = '3'
        with self.assertRaises(ValueError): p.corrected_groups(*args)

    def test_duplicate_label(self):
        args = self.fixture(); args[0]['pack3230']['reference'].append(args[0]['pack3230']['reference'][0])
        with self.assertRaises(ValueError): p.corrected_groups(*args)

    def test_unknown_owner(self):
        args = self.fixture(); args[1][0]['targets'][0]['name'] = 'normal_result'
        with self.assertRaises(ValueError): p.corrected_groups(*args)

    def test_scalar_cannot_replace_vector(self):
        args = self.fixture(); args[1][0]['targets'] = []
        with self.assertRaises(ValueError): p.corrected_groups(*args)


if __name__ == '__main__':
    unittest.main()
