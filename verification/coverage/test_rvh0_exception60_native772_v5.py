"""Actual first/second native fixtures, semantic permutations and strict gates."""
import copy
import json
from pathlib import Path
import random
import tempfile
from types import FunctionType
import unittest

import rvh0_exception60_native772_v5 as m
import test_rvh0_exception60_native772_v4 as prior


class ExactNative(unittest.TestCase):
    def test_actual_second_EL_in_full_five_stage_session(self):
        second = (m.FIXTURE / 'second.el').read_text()
        mutation = 'set ::mock_second {' + second + '}\n'
        mutation += r'''
rename gui_exclusion_file mock_original_file
proc gui_exclusion_file {args} {
    set path [lindex [lindex $args end] 0]
    if {[lsearch -exact $args -save] >= 0 && [file tail $path] eq "second.el"} {
        set stream [open $path w]
        puts -nonewline $stream $::mock_second
        close $stream
        return
    }
    return [eval mock_original_file $args]
}
'''
        with tempfile.TemporaryDirectory(dir=m.life.OUT) as tmp:
            out = Path(tmp)
            result = self.execute(out, mutation)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('RVH0_EXCEPTION60_NATIVE_DONE', result.stdout)
            self.assertNotIn('RVH0_EXCEPTION60_FAILED', result.stdout)
            self.assertEqual(m.records((out / 'first.el').read_text(), self.c),
                             m.records((out / 'second.el').read_text(), self.c))
            for stage in m.STAGES:
                for index in range(5):
                    m.inventory(out, self.c, stage, index)
                m.check_el(out, self.c, stage)


for name, member in vars(prior.ExactNative).items():
    function = member.__func__ if isinstance(member, classmethod) else member
    if isinstance(function, FunctionType):
        cloned = FunctionType(function.__code__, dict(function.__globals__, m=m), name,
                              function.__defaults__, function.__closure__)
        setattr(ExactNative, name, classmethod(cloned) if isinstance(member, classmethod) else cloned)


class SemanticGrammar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = json.loads((m.FIXTURE / 'config.json').read_bytes())
        cls.first = (m.FIXTURE / 'first.el').read_text()
        cls.second = (m.FIXTURE / 'second.el').read_text()

    def test_real_first_second_exact_semantic_union(self):
        a = m.records(self.first, self.c)
        self.assertEqual(a, m.records(self.second, self.c))
        self.assertEqual(a, m.records(m.candidate(self.c), self.c))
        self.assertEqual(len(a), 79)
        self.assertEqual(len({(s, n) for s, n, _, _ in a}), 60)
        self.assertEqual(sum(d == 'whole' for _, _, _, d in a), 41)
        self.assertEqual(sum(d == '0to1' for _, _, _, d in a), 19)
        self.assertEqual(sum(d == '1to0' for _, _, _, d in a), 19)
        with self.assertRaisesRegex(ValueError, 'Scalar pair must start'):
            m.inherited.records(self.second, self.c)

    def test_200_random_legal_permutations(self):
        blocks = []
        for line in self.first.splitlines():
            if line.startswith('CHECKSUM:'):
                blocks.append(dict(header=[line], units=[]))
            elif line.startswith('INSTANCE:'):
                blocks[-1]['header'].append(line)
            elif line.startswith('ANNOTATION:'):
                blocks[-1]['units'].append([line])
            elif blocks[-1]['units'] and blocks[-1]['units'][-1][0].startswith('ANNOTATION:') and len(blocks[-1]['units'][-1]) == 1:
                blocks[-1]['units'][-1].append(line)
            else:
                blocks[-1]['units'].append([line])
        expected = m.records(self.first, self.c)
        for seed in range(200):
            rng = random.Random(seed)
            shuffled = copy.deepcopy(blocks)
            rng.shuffle(shuffled)
            lines = []
            for block in shuffled:
                rng.shuffle(block['units'])
                lines += block['header']
                lines += [line for unit in block['units'] for line in unit]
            with self.subTest(seed=seed):
                self.assertEqual(m.records('\n'.join(lines) + '\n', self.c), expected)

    def test_negative_semantics_annotation_type_scope_metrics(self):
        annotation = 'ANNOTATION: "' + m.ANNOTATION + '"'
        scalar = next(line for line in self.second.splitlines() if line.startswith('Toggle 1to0 '))
        vector = next(line for line in self.second.splitlines() if line.startswith('Toggle ') and '0to1' not in line and '1to0' not in line)
        scope = self.c['instances'][0]['scope']
        cases = [self.second.replace(scalar + '\n', '', 1),
                 self.second.replace(scalar, scalar + '\n' + scalar, 1),
                 self.second.replace(scalar, annotation + '\n' + scalar, 1),
                 self.second.replace(scalar, scalar.replace('1to0', '0to1'), 1),
                 self.second.replace(annotation + '\n', '', 1),
                 self.second.replace(annotation, annotation + '\n' + annotation, 1),
                 self.second + annotation + '\n',
                 self.second.replace(annotation, 'ANNOTATION: "foreign"', 1),
                 self.second.replace(vector, vector + '\n' + annotation + '\n' + vector, 1),
                 self.second.replace(vector, vector.replace('Toggle ', 'Toggle 0to1 ', 1), 1),
                 self.second.replace(vector, vector.replace(' "logic ', ' [0] "logic ', 1), 1),
                 self.second.replace(vector, vector.replace('[31:0]', '[30:0]'), 1),
                 self.second.replace(vector, vector.replace('logic ', 'logic signed ', 1), 1),
                 self.second.replace(vector, vector.replace('logic ', 'wire ', 1), 1),
                 self.second.replace(vector, 'Toggle store_b_exception_d.cause "logic store_b_exception_d.cause[63:0]"', 1),
                 self.second.replace(vector, 'Toggle store_b_exception_d.tval "logic store_b_exception_d.tval[63:0]"', 1),
                 self.second.replace(scope, scope + '.foreign', 1),
                 self.second.replace(self.c['instances'][0]['toggle_checksum'], '1', 1),
                 self.second + 'FSM 1\n', self.second + 'Line 1\n',
                 self.second + 'Toggle whole_scope\n']
        for index, text in enumerate(cases):
            with self.subTest(index=index), self.assertRaises(ValueError):
                m.records(text, self.c)

    def test_real_three_stages_complete_two_missing(self):
        actual = json.loads((m.FIXTURE / 'actual-binding.json').read_bytes())
        for stage in ('before', 'selected', 'reset'):
            for index in range(5):
                self.assertEqual(m.inventory(m.FIXTURE, self.c, stage, index), actual['scopes'][index])
        self.assertEqual(len(m.grammar_evidence_pins()), 27)
        for stage in ('reloaded', 'final'):
            self.assertFalse(any(m.FIXTURE.glob('native_' + stage + '_*.tsv')))
        self.assertFalse((m.FIXTURE / 'capture-result.json').exists())
        with self.assertRaises(ValueError):
            m.inspect(m.FIXTURE, m.FIXTURE_SEAL)


if __name__ == '__main__':
    unittest.main()
