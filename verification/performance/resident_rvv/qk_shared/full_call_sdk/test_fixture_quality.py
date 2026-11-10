import copy
import unittest

import fixture_quality as q


class FixtureQualityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture,cls.meta,cls.data,_,_ = q.baseline()
        cls.reference = cls.meta['fixture']['results'][2]

    def test_six_rows_unique_after_real_half_conversion(self):
        values = q.uniqueness(self.fixture,self.fixture.CASES[2],self.data[2],self.reference)
        for key in ('query_f32_active','query_f16_active','output_f32'):
            self.assertEqual(len(set(values[key])),6)

    def test_both_active_kv_groups_unique(self):
        values = q.uniqueness(self.fixture,self.fixture.CASES[2],self.data[2],self.reference)
        for key in ('key_active_groups','value_active_groups'):
            self.assertEqual(len(set(values[key])),2)

    def test_duplicate_query_rejected(self):
        data = dict(self.data[2],query=self.data[2]['query'][:512]*6)
        with self.assertRaisesRegex(ValueError,'query_f32'):
            q.uniqueness(self.fixture,self.fixture.CASES[2],data,self.reference)

    def test_duplicate_key_or_value_group_rejected(self):
        for role in ('key','value'):
            data = dict(self.data[2])
            data[role] = data[role][:65*256]*2
            with self.subTest(role=role),self.assertRaisesRegex(ValueError,'KV group'):
                q.uniqueness(self.fixture,self.fixture.CASES[2],data,self.reference)

    def test_duplicate_golden_rejected(self):
        result = copy.deepcopy(self.reference)
        result['bits'][96:192] = result['bits'][:96]
        with self.assertRaisesRegex(ValueError,'output_f32'):
            q.uniqueness(self.fixture,self.fixture.CASES[2],self.data[2],result)

    def test_actual_wrong_base_and_stale_full_oracles_differ(self):
        report,_ = q.audit()
        self.assertEqual(report['state'],'PASS')
        self.assertFalse(report['fixture_changed'])
        self.assertEqual(len(report['mutations']),4)
        self.assertEqual(report['original_d128_golden_sha256'],self.fixture.NATIVE_SHA)
        for mutation in report['mutations']:
            self.assertNotEqual(mutation['golden_sha256'],report['derived_golden_sha256'])
            self.assertTrue(all(mutation['differing_f32_per_head'][h] > 0
                                for h in mutation['changed_heads']))


if __name__ == '__main__':
    unittest.main()
