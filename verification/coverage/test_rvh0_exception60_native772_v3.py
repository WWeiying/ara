"""Reuse the sealed actual Tcl/session regressions plus singleton negatives."""
import copy
import json
from pathlib import Path
import tempfile
from types import FunctionType
import unittest

import rvh0_exception60_native772_v3 as m
import test_rvh0_exception60_native772_v2 as original


class ExactNative(unittest.TestCase):
    def test_all_scope_bare_protected_singletons_actual_entry_five_stages(self):
        mutation = ''
        for i in self.c['instances']:
            for index, b in enumerate(i['bindings']):
                a = b['attributes']
                if b['role'] == 'protected' and b['kind'] == 'vectornode' and a['left'] == a['right']:
                    mutation += 'lset ::mock_labels(' + i['scope'] + ') ' + str(index) + ' ' + m.atom(b['name']) + '\n'
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out = Path(tmp)
            result = self.execute(out, mutation)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('RVH0_EXCEPTION60_NATIVE_DONE', result.stdout)
            self.assertNotIn('RVH0_EXCEPTION60_FAILED', result.stdout)
            for stage in m.STAGES:
                for index in range(5):
                    m.inventory(out, self.c, stage, index)
                m.check_el(out, self.c, stage)


for name, member in vars(original.ExactNative).items():
    function = member.__func__ if isinstance(member, classmethod) else member
    if isinstance(function, FunctionType):
        namespace = dict(function.__globals__, m=m)
        cloned = FunctionType(function.__code__, namespace, name, function.__defaults__, function.__closure__)
        setattr(ExactNative, name, classmethod(cloned) if isinstance(member, classmethod) else cloned)


class SingletonTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _, cls.before = m.predecessor.proof()
        _, cls.after = m.proof()

    def test_all_scopes_target_and_array_aliases_unchanged(self):
        changed = 0
        for old_i, new_i in zip(self.before, self.after):
            for old, new in zip(old_i['bindings'], new_i['bindings']):
                attrs = old['attributes']
                singleton = old['role'] == 'protected' and old['kind'] == 'vectornode' and attrs['left'] == attrs['right']
                expected = sorted(set(old['allowed_labels']) | {old['name']}) if singleton else old['allowed_labels']
                self.assertEqual(new['allowed_labels'], expected)
                unchanged = copy.deepcopy(new)
                unchanged['allowed_labels'] = old['allowed_labels']
                self.assertEqual(unchanged, old)
                changed += old != new
        self.assertEqual(changed, 1)

    def test_actual_failed_before_now_exact_and_predecessor_unchanged(self):
        out = m.life.OUT / 'rvh0-exception60-native772-v2-parent-prepared-20261007-01'
        config = json.loads((out / 'config.json').read_bytes())
        with self.assertRaisesRegex(ValueError, 'Foreign/duplicate'):
            m.predecessor.inventory(out, config, 'before', 0)
        config['instances'] = self.after
        self.assertEqual(len(m.inventory(out, config, 'before', 0)['bindings']), 692)
        self.assertIsNot(m.inventory.__globals__, vars(m.predecessor))

    def test_arbitrary_offset_only_protected_singletons(self):
        sample = copy.deepcopy(self.before[0])
        b = next(b for b in sample['bindings'] if b['name'] == 'instr.rvftype.repl')
        sample['bindings'] = [b]
        for offset in ('0', '14', '63', '-3'):
            b['attributes']['left'] = b['attributes']['right'] = offset
            b['label'] = b['name'] + '[%s:%s]' % (offset, offset)
            b['allowed_labels'] = [b['label']]
            self.assertEqual(m.singleton_aliases([sample])[0]['bindings'][0]['allowed_labels'],
                             sorted([b['name'], b['label']]))
        b['role'] = 'target'
        self.assertEqual(m.singleton_aliases([sample]), [sample])

    def test_multibit_type_name_range_collision_negatives(self):
        source = copy.deepcopy(self.before[0])
        base = next(b for b in source['bindings'] if b['name'] == 'instr.rvftype.repl')
        source['bindings'] = [base]
        for key, value in [('type', '2'), ('name', 'foreign'), ('left', '15')]:
            c = copy.deepcopy(source)
            c['bindings'][0]['attributes'][key] = value
            with self.assertRaises(ValueError):
                m.singleton_aliases([c])
        c = copy.deepcopy(source)
        b = c['bindings'][0]
        b['attributes']['left'] = '15'
        b['label'] = b['name'] + '[15:14]'
        b['allowed_labels'] = [b['label']]
        b['width'] = 2
        self.assertNotIn(b['name'], m.singleton_aliases([c])[0]['bindings'][0]['allowed_labels'])
        c = copy.deepcopy(source)
        collision = copy.deepcopy(base)
        collision['name'] = 'another'
        collision['attributes']['name'] = 'another'
        collision['label'] = 'another[14:14]'
        collision['allowed_labels'] = [base['name']]
        c['bindings'].append(collision)
        with self.assertRaisesRegex(ValueError, 'collision'):
            m.singleton_aliases([c])


if __name__ == '__main__':
    unittest.main()
