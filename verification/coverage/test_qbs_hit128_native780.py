import copy
import json
import unittest
import xml.etree.ElementTree as ET

import qbs_hit128_native780 as n


class PartialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.proof = n.life.read_bound(n.PROOF, n.PROOF_SHA)
        cls.template = n.life.read_bound(n.TEMPLATE / 'config.json', n.TEMPLATE_SHA)
        path = next(p for p in cls.proof['pins'] if p.endswith('/shape/tgl.verilog.shape.xml'))
        shape = n.primitive.toggle.xml(n.Path(path))
        cls.definition = next(d for d in shape.iter('tgldef') if d.get('name') == 'qbs_payload_buffer')
        cls.config = dict(instances=n.instances(cls.proof, cls.template, cls.definition))

    def test_exact_partial_set(self):
        text = n.primitive.candidate(self.config)
        self.assertEqual(len(n.parse_el(text, self.config)), 128)
        self.assertEqual(len(self.config['instances'][0]['protected']), 3177)
        self.assertEqual(sum(len(x) for x in self.config['instances'][0]['retained_target_signal_bits'].values()), 192)

    def test_wrong_scope(self):
        text = n.primitive.candidate(self.config).replace('bank0.', 'bank1.')
        with self.assertRaises(ValueError): n.parse_el(text, self.config)

    def test_protected_bit(self):
        text = n.primitive.candidate(self.config).replace(' [2]', ' [3]', 1)
        with self.assertRaises(ValueError): n.parse_el(text, self.config)

    def test_wrong_checksum(self):
        text = n.primitive.candidate(self.config).replace('3657545390', '3657545391')
        with self.assertRaises(ValueError): n.parse_el(text, self.config)

    def test_whole_vector_forbidden(self):
        text = n.primitive.candidate(self.config).replace(' [2]', '', 1)
        with self.assertRaises(ValueError): n.parse_el(text, self.config)

    def test_duplicate_missing_extra(self):
        text = n.primitive.candidate(self.config)
        line = next(x for x in text.splitlines() if x.startswith('Toggle '))
        for value in (text + line + '\n', text.replace(line + '\n', '', 1), text + 'Branch 1 01\n'):
            with self.assertRaises(ValueError): n.parse_el(value, self.config)

    def test_native_net_signature(self):
        text = n.primitive.candidate(self.config)
        lines = []
        for line in text.splitlines():
            if line.startswith('Toggle '):
                name = line.split()[2]
                line += ' "net ' + name + '[15:0]"'
            lines.append(line)
        native = '\n'.join(lines)
        self.assertEqual(len(n.parse_el(native, self.config)), 128)
        with self.assertRaises(ValueError): n.parse_el(native.replace('net ', 'reg ', 1), self.config)

    def test_proof_extra_or_observed_target(self):
        for change in ('duplicate', 'scope', 'observed'):
            p = copy.deepcopy(self.proof)
            r = next(x for x in p['records'] if x['classification'] == 'SOURCE_MAPPING_ZERO_NATIVE_REQUIRED')
            if change == 'duplicate': p['records'].append(copy.deepcopy(r))
            elif change == 'scope': r['scope'] = r['scope'].replace('bank0.', 'bank1.')
            else: r['raw_coordinates'].pop()
            with self.assertRaises(ValueError): n.instances(p, self.template, self.definition)

    def test_full_inventory_and_protection(self):
        i = self.config['instances'][0]
        nodes = i['protected'] + [dict(s['shape'], tag='vectornode') for s in i['signals']]
        header = 'handle\tpath\tmeta\tname\tcolumn1\tcolumn2\n'
        rows = []
        for index, node in enumerate(nodes):
            label = node['name'] if node['tag'] == 'node' else node['name'] + '[' + node['left'] + ':' + node['right'] + ']'
            rows.append(str(index) + '\t' + '\t'.join([label] * 3) + '\t\t')
        text = header + '\n'.join(rows) + '\n'
        stages = {s: text for s in ('before', 'selected', 'reset', 'reloaded', 'final')}
        self.assertEqual(n.audit_inventory(i, stages), [3193, 3177])
        for change in ('missing', 'extra', 'protected', 'reload'):
            bad = dict(stages)
            if change == 'missing': bad['before'] = header + '\n'.join(rows[1:]) + '\n'
            elif change == 'extra': bad['selected'] += '9999\textra\textra\textra\t\t\n'
            else: bad['reloaded' if change == 'reload' else 'selected'] = text.replace(rows[0], rows[0] + '1')
            with self.assertRaises(ValueError): n.audit_inventory(i, bad)

    def test_real_qualified_native_before_identity(self):
        text = (n.TEMPLATE / 'native_before_0.tsv').read_text()
        stages = {s: text for s in ('before', 'selected', 'reset', 'reloaded', 'final')}
        self.assertEqual(n.audit_inventory(self.config['instances'][0], stages), [3193, 3177])


if __name__ == '__main__': unittest.main()
