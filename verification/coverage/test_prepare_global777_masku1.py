import copy
import inspect
import json
import unittest
from unittest.mock import patch

import prepare_global777_masku1 as p


class Global777Tests(unittest.TestCase):
    def test_frozen776_no_changes(self):
        p.life.check(p.FROZEN)
        c = p.life.read_bound(p.PREP776 / 'config.json', p.PREP776_SHA)
        self.assertEqual(c['population'], 776)
        self.assertEqual(c['masku776']['qualified_seal'], p.predecessor.QUAL_SHA)

    def test_actual775_776_777_chain(self):
        pins = {}; ledger = p.chain(pins)
        self.assertEqual(len(ledger), 778)
        self.assertEqual(pins[str(p.BASE / 'admission-manifest.json')], p.BASE_SHA)

    def test_prefix_OR_scope_and_duplicate_negatives(self):
        rows = {str(k): dict(width=1, checksum='1', bits='0') for k in range(6162)}
        a = dict(tests=['a'], design={'checksum': 'frozen'}, metrics={'m': rows})
        b = dict(a, tests=['a', 'b']); single = dict(a, tests=['b'])
        p.chain_gate(a, b, single, 2, ['design', 'a'], ['design', 'a', 'b'])
        for ledger in (['design', 'a', 'a'], ['design', 'other', 'b'], ['different', 'a', 'b']):
            with self.assertRaises(ValueError): p.chain_gate(a, b, single, 2, ['design', 'a'], ledger)
        bad = copy.deepcopy(b); bad['metrics']['m']['0']['bits'] = '1'
        with self.assertRaises(ValueError): p.chain_gate(a, bad, single, 2, ['design', 'a'], ['design', 'a', 'b'])

    def test_private_anchors_and_missing_anchor_rejected(self):
        text = inspect.getsource(p.predecessor.inherited_check)
        self.assertEqual(text.count('"c[\'population\']==776"'), 1)
        self.assertEqual(text.count("==776,'Actual776 full population'"), 1)
        with self.assertRaises(ValueError): p.private_function(p.chain_gate, {'not present': 'x'}, {})

    def test_no_run_or_additional_scope(self):
        with patch.object(p.predecessor, 'namespace', return_value={'verify': lambda out, seal: None}):
            ns = p.namespace()
        self.assertNotIn('run', ns)
        self.assertEqual(p.TCL.read_text().count('source'), 1)
        self.assertIn(str(p.predecessor.TCL), p.TCL.read_text())

    def test_exact_local_five_stages_still_required(self):
        native = p.life.read_bound(p.predecessor.Q / 'config.json', p.predecessor.strict.NATIVE_SHA)
        for stage in p.predecessor.STAGES:
            for index in range(26):
                p.predecessor.strict.qualification.inventory(p.predecessor.Q, native, stage, index)
        self.assertEqual(sum(b['role'] == 'target' for i in native['instances'] for b in i['bindings']), 1)


if __name__ == '__main__': unittest.main()
