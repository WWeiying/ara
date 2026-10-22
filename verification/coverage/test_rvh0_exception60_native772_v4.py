"""Real native EL/before evidence and the reused five-stage actual Tcl session."""
import copy
import json
from types import FunctionType
import unittest

import rvh0_exception60_native772_v4 as m
import test_rvh0_exception60_native772_v3 as prior


class ExactNative(unittest.TestCase):
    pass


for name, member in vars(prior.ExactNative).items():
    function = member.__func__ if isinstance(member, classmethod) else member
    if isinstance(function, FunctionType):
        cloned = FunctionType(function.__code__, dict(function.__globals__, m=m), name,
                              function.__defaults__, function.__closure__)
        setattr(ExactNative, name, classmethod(cloned) if isinstance(member, classmethod) else cloned)


class RealGrammar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = json.loads((m.FIXTURE / 'config.json').read_bytes())
        cls.text = (m.FIXTURE / 'first.el').read_text()

    def test_full_real_EL_exact_source_union(self):
        wanted = sorted((i['scope'], b['name']) for i in self.c['instances']
                        for b in i['bindings'] if b['role'] == 'target')
        self.assertEqual(m.records(self.text, self.c), wanted)
        self.assertEqual(m.records(m.candidate(self.c), self.c), wanted)
        self.assertEqual(len(wanted), 60)
        self.assertEqual(self.text.count('ANNOTATION:'), 41)
        self.assertEqual(self.text.count('Toggle 0to1 '), 19)
        self.assertEqual(self.text.count('Toggle 1to0 '), 19)

    def test_all_five_real_before_bindings_unchanged(self):
        actual = json.loads((m.FIXTURE / 'actual-binding.json').read_bytes())
        total = 0
        for index in range(5):
            bound = m.inventory(m.FIXTURE, self.c, 'before', index)
            self.assertEqual(bound, actual['scopes'][index])
            total += len(bound['bindings'])
        self.assertEqual(total, 2854)
        pins = m.grammar_evidence_pins()
        self.assertEqual(len(pins), 15)

    def test_real_negative_grammar_and_members(self):
        annotation = 'ANNOTATION: "' + m.ANNOTATION + '"'
        scalar0 = next(s for s in self.text.splitlines() if s.startswith('Toggle 0to1 '))
        scalar1 = scalar0.replace('0to1', '1to0', 1)
        vector = next(s for s in self.text.splitlines() if s.startswith('Toggle ') and '0to1' not in s and '1to0' not in s)
        cases = [self.text.replace(annotation + '\n', '', 1),
                 self.text.replace(annotation, annotation + '\n' + annotation, 1),
                 self.text + annotation + '\n',
                 self.text.replace(scalar0, annotation + '\n' + scalar0, 1),
                 self.text.replace(scalar1 + '\n', '', 1),
                 self.text.replace(scalar1, scalar0, 1),
                 self.text.replace(scalar0, scalar0.replace('0to1', '1to0', 1), 1),
                 self.text.replace(vector, vector + '\n' + annotation + '\n' + vector, 1),
                 self.text.replace(vector, vector.replace('Toggle ', 'Toggle 0to1 ', 1), 1),
                 self.text.replace(vector, vector.replace(' "logic ', ' [0] "logic ', 1), 1),
                 self.text.replace(vector, vector.replace('[40:0]', '[39:0]'), 1),
                 self.text.replace(annotation, 'ANNOTATION: "foreign"', 1),
                 self.text + 'Line 1\n', self.text + 'FSM 1\n',
                 self.text.replace(vector, 'Toggle store_b_exception_o.cause "logic store_b_exception_o.cause[63:0]"', 1),
                 self.text.replace(vector, vector.replace('store_b_exception_o.tval2', 'store_b_exception_o.tval'), 1),
                 self.text.replace(vector, vector.replace('logic ', 'wire ', 1), 1),
                 self.text.replace(vector, vector.replace('logic ', 'logic signed ', 1), 1)]
        for index, text in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                m.records(text, self.c)

    def test_contract_cannot_expand_targets(self):
        c = copy.deepcopy(self.c)
        c['instances'][0]['bindings'][0]['role'] = 'target'
        with self.assertRaises(ValueError):
            m.contract(c)

    def test_no_native_qualification_from_fixture(self):
        self.assertFalse((m.FIXTURE / 'capture-result.json').exists())
        with self.assertRaises(ValueError):
            m.inspect(m.FIXTURE, m.FIXTURE_SEAL)


if __name__ == '__main__':
    unittest.main()
