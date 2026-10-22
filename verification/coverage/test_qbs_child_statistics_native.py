import copy
import unittest

import qbs_child_statistics_native as n


class NativeChildTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.candidate = n.life.read_bound(n.SOURCE, n.SOURCE_SHA)
        cls.base = n.life.read_bound(n.NATIVE / 'config.json', n.CONFIG_SHA)

    def test_real_complete_field_grammar_and_control_protection(self):
        config = dict(instances=n.instances(self.candidate, self.base))
        self.assertEqual(len(n.prior.predecessor.namespace()['parse_el'](n.q.candidate(config), config)), 798)
        child = config['instances'][0]
        self.assertIn('entry_occupancy', {p['name'] for p in child['protected']})
        self.assertIn('fflags_q', {p['name'] for p in child['protected']})
        self.assertEqual(sum(len(i['signals']) for i in config['instances']), 15)

    def test_source_replay_is_exact(self):
        self.assertEqual(n.reviewed_source(), self.candidate)

    def test_partial_statistics_field_rejected(self):
        candidate = copy.deepcopy(self.candidate)
        candidate['groups'][0]['fields'][0]['bits'] -= 1
        with self.assertRaisesRegex(ValueError, 'Incomplete whole'):
            n.instances(candidate, self.base)

    def test_real_occupancy_is_not_statistics(self):
        candidate = copy.deepcopy(self.candidate)
        f = candidate['groups'][0]['fields'][0]
        f['name'] = f['compiled']['name'] = 'entry_occupancy'
        with self.assertRaisesRegex(ValueError, 'Foreign/previous'):
            n.instances(candidate, self.base)

    def test_non_target_native_field_rejected(self):
        config = dict(instances=n.instances(self.candidate, self.base))
        text = n.q.candidate(config).replace('fp_uop_issue_o', 'entry_occupancy', 1)
        with self.assertRaises(ValueError):
            n.prior.predecessor.namespace()['parse_el'](text, config)


if __name__ == '__main__':
    unittest.main()
