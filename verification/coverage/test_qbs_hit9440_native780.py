import copy
import unittest
import qbs_hit9440_native780 as n


class BatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof, cls.template, cls.path, cls.definition = n.proof_inputs()
        cls.instances = n.instances(cls.proof, cls.template, cls.definition)
        cls.config = dict(instances=cls.instances)
        cls.text = n.primitive.candidate(cls.config)

    def test_exact9440_and128_disjoint(self):
        bits = n.primitive.bitset(self.config)
        self.assertEqual(len(n.parse_el(self.text, self.config)), 9440)
        old = {(n.local.SCOPE, name, bit, direction) for name, selected in n.local.target_names().items()
               for bit in selected for direction in ('0to1', '1to0')}
        self.assertFalse(bits & old)
        self.assertEqual(sum(len(i['signals']) for i in self.instances), 688)
        self.assertEqual(sum(len(i['protected']) for i in self.instances), 5698)
        self.assertEqual(sum(len(b) for i in self.instances for b in i['retained_target_signal_bits'].values()), 13456)

    def test_scope_checksum_whole_and_extra_rejected(self):
        line = next(x for x in self.text.splitlines() if x.startswith('Toggle '))
        variants = (self.text.replace('bank0.', 'unknown.'), self.text.replace('3657545390', '1'),
                    self.text.replace(line, line.rsplit(' ', 1)[0], 1), self.text + line + '\n',
                    self.text.replace(line + '\n', '', 1), self.text + 'Condition 1 01\n')
        for value in variants:
            with self.assertRaises(ValueError): n.parse_el(value, self.config)

    def test_HOLD_cannot_be_target(self):
        p = copy.deepcopy(self.proof)
        group = copy.deepcopy(p['HOLD_groups'][0])
        group['classification'] = 'HOLD_MAPPING_NOT_RUNTIME_PROOF'
        p['target_groups'].append(group)
        with self.assertRaises(ValueError): n.instances(p, self.template, self.definition)

    def test_wrong_writer_raw_coordinate_and_duplicate_rejected(self):
        for mode in ('writer', 'coordinate', 'duplicate', 'qualified'):
            p = copy.deepcopy(self.proof)
            g = next(x for x in p['target_groups'] if x['classification'] == 'NEW_ZERO_NATIVE_REQUIRED')
            bit = next(iter(g['bit_missing_coordinates']))
            if mode == 'writer': g['original_writer_slots'][bit][1] ^= 1
            elif mode == 'coordinate': g['bit_missing_coordinates'][bit][0] += 1
            elif mode == 'qualified': g['classification'] = 'QUALIFIED128_NOT_APPLIED'
            else: p['target_groups'].append(copy.deepcopy(g))
            with self.assertRaises(ValueError): n.instances(p, self.template, self.definition)

    def test_real_native_before_complete_both_banks(self):
        template = {i['scope']: k for k, i in enumerate(self.template['instances'])}
        for i in self.instances:
            text = (n.local.TEMPLATE / ('native_before_' + str(template[i['scope']]) + '.tsv')).read_text()
            stages = {s: text for s in ('before', 'selected', 'reset', 'reloaded', 'final')}
            self.assertEqual(n.local.audit_inventory(i, stages), [3193, len(i['protected'])])
            bad = dict(stages, final=text.rsplit('\n', 2)[0] + '\n')
            with self.assertRaises(ValueError): n.local.audit_inventory(i, bad)

    def test_native_signature_type_and_bounds(self):
        i = self.instances[0]
        sig = i['signals'][0]
        line = next(x for x in self.text.splitlines() if x.startswith('Toggle ') and sig['name'] in x)
        native = self.text.replace(line, line + ' "net ' + sig['native_label'] + '"', 1)
        self.assertEqual(len(n.parse_el(native, self.config)), 9440)
        with self.assertRaises(ValueError): n.parse_el(native.replace('net ', 'reg ', 1), self.config)


if __name__ == '__main__': unittest.main()
