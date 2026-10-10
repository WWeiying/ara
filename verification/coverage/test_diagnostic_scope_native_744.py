import copy
import json
import unittest

import diagnostic_scope_native_744 as d


class DiagnosticNativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.audit = d.life.read_bound(d.AUDIT, d.AUDIT_SHA)
        cls.config = d.life.read_bound(d.OLD / 'config.json', d.OLD_CONFIG_SHA)

    def test_real_complete_fields(self):
        instances = d.targets(self.audit, self.config)
        c = dict(instances=instances)
        self.assertEqual(len(d.q.bitset(c)), 11038)
        self.assertEqual(len(instances), 6)
        text = d.q.candidate(c)
        self.assertEqual(len(d.predecessor.namespace()['parse_el'](text, c)), 11038)
        self.assertTrue(any('vinsn_retired_q' == n['name'] for i in instances for n in i['protected']))

    def test_partial_field_rejected(self):
        audit = copy.deepcopy(self.audit)
        audit['groups'][0]['fields'][0]['bits'] -= 1
        with self.assertRaisesRegex(ValueError, 'Incomplete whole field'):
            d.targets(audit, self.config)

    def test_duplicate_or_foreign_field_rejected(self):
        audit = copy.deepcopy(self.audit)
        audit['groups'][0]['fields'].append(audit['groups'][0]['fields'][0])
        with self.assertRaisesRegex(ValueError, 'Duplicate/misbound'):
            d.targets(audit, self.config)

    def test_native_extra_metric_rejected(self):
        c = dict(instances=d.targets(self.audit, self.config))
        with self.assertRaises(ValueError):
            d.predecessor.namespace()['parse_el'](d.q.candidate(c) + 'Branch 1 0\n', c)

    def test_native_other_bit_rejected(self):
        c = dict(instances=d.targets(self.audit, self.config))
        text = d.q.candidate(c)
        with self.assertRaises(ValueError):
            d.predecessor.namespace()['parse_el'](text.replace('[0]', '[99]', 1), c)


if __name__ == '__main__':
    unittest.main()
