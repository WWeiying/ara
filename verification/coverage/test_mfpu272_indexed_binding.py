import copy
import json
import unittest

import mfpu272_indexed_binding as indexed


class IndexedTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = json.loads((indexed.previous.RUN / 'config.json').read_bytes())

    def test_actual_first_scope_equivalence(self):
        instance = self.config['instances'][0]
        text = (indexed.previous.RUN / 'native_before_0.tsv').read_text()
        bound, aliases = indexed.bind_with_aliases(instance, text)
        self.assertEqual(bound, indexed.previous.binder()(instance, text))
        self.assertEqual(aliases, indexed.previous.alias_proof(instance, text))

    def test_generated_name_boundaries_and_complete_array(self):
        instance = self.config['instances'][0]
        resolver = indexed.Resolver(instance)
        rows = indexed.previous.frozen.pack.native.native_rows(
            (indexed.previous.RUN / 'native_before_0.tsv').read_text())
        for label, row in rows.items():
            expected = [(n, indexed.previous.match_label(n, label, row['type']))
                        for n in instance['typed_objects']]
            expected = [(n, m) for n, m in expected if m is not None]
            self.assertEqual(resolver.matches(label, row['type']), expected)

    def test_duplicate_and_unknown_rejected(self):
        instance = copy.deepcopy(self.config['instances'][0])
        instance['typed_objects'].append(instance['typed_objects'][0])
        with self.assertRaises(ValueError):
            indexed.Resolver(instance)
        resolver = indexed.Resolver(self.config['instances'][0])
        self.assertEqual(resolver.matches('foreign_missing[63:0]', 'signal'), [])

    def test_bare_multibit_and_role_not_promoted(self):
        resolver = indexed.Resolver(self.config['instances'][0])
        for n in self.config['instances'][0]['typed_objects']:
            if n['kind'] == 'vectornode' and n['left'] != n['right']:
                self.assertEqual(resolver.matches(n['name'], 'signal'), [])
        n = dict(name='g[1].mask', kind='vectornode', left='0', right='0', portnode='0')
        resolver = indexed.Resolver(dict(typed_objects=[n]))
        self.assertEqual(resolver.matches(n['name'], 'port'), [])
        self.assertEqual(resolver.matches(n['name'], 'register'), [])
        self.assertEqual(len(resolver.matches(n['name'], 'signal')), 1)

    def test_missing_inventory_rejected(self):
        text = (indexed.previous.RUN / 'native_before_0.tsv').read_text()
        lines = text.splitlines(keepends=True)
        with self.assertRaises(ValueError):
            indexed.bind_with_aliases(self.config['instances'][0], ''.join(lines[:1] + lines[2:]))


if __name__ == '__main__':
    unittest.main()
