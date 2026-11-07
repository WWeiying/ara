#!/usr/bin/env python3
"""Bounded host C integration tests; never launches an RTL/ISA simulator."""
from pathlib import Path
import subprocess
import tempfile
import unittest

import mixed_scale_edge_vectors as edges


class TransformTests(unittest.TestCase):
    def test_exact_reversible_clone(self):
        source = edges.read_source()
        clone, edits = edges.transform(source)
        self.assertEqual(len(edits), 4)
        for edit in reversed(edits):
            self.assertEqual(clone.count(edit['after']), 1)
            clone = clone.replace(edit['after'], edit['before'], 1)
        self.assertEqual(clone, source)

    def test_source_and_anchor_drift_rejected(self):
        source = edges.read_source()
        for changed in (source + '\n', source.replace('static int emit_case_data', 'static int other'),
                        source.replace('QBSCMD1 36', 'QBSCMD1 35')):
            with self.assertRaises(ValueError):
                edges.transform(changed)

    def test_only_finite_inputs_and_mixed_ports(self):
        self.assertTrue(all((bits & 0x7f800000) != 0x7f800000 for row in edges.ACTIVATIONS for bits in row))
        self.assertTrue(all((bits & 0x7c00) != 0x7c00 for row in edges.WEIGHTS for bits in row))
        self.assertTrue(any(a and b == 0 for a, b in edges.WEIGHTS))
        self.assertTrue(any(a == 0 and b for a, b in edges.WEIGHTS))
        self.assertTrue(any(0 < (bits & 0x7fff) < 0x400 for row in edges.WEIGHTS for bits in row))
        self.assertTrue(all(not ((a & 0x7fff) and (b & 0x7fff)) for a, b in edges.OVERFLOW_WEIGHTS))

    def test_recipe_keeps_reference_and_ieee_flags(self):
        recipe = edges.gen_recipe(Path('/tmp/clone.c'), Path('/tmp/oracle'))
        self.assertIn(str(edges.REFERENCE), recipe)
        for flag in ('-ffp-contract=off', '-frounding-math', '-fno-fast-math', '-Werror'):
            self.assertIn(flag, recipe)
        self.assertNotIn('-ffast-math', recipe)


class HostOracleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory(prefix='mixed-scale-edge-host-')
        cls.directory = Path(cls.temporary.name)
        try:
            clone, _ = edges.transform(edges.read_source())
            cls.source = cls.directory / 'clone.c'
            cls.source.write_text(clone)
            cls.executable = cls.directory / 'generator'
            cls.run_host(edges.gen_recipe(cls.source, cls.executable))
            cls.vector = cls.directory / 'extras.txt'
            cls.run_host([cls.executable, cls.vector, '--mixed-scale-edges'])
            cls.text = cls.vector.read_text()
            cls.shapes = edges.parse_extras(cls.text)
        except BaseException:
            cls.temporary.cleanup()
            raise

    @classmethod
    def tearDownClass(cls):
        cls.temporary.cleanup()

    @staticmethod
    def run_host(argv):
        result = subprocess.run(list(map(str, argv)), capture_output=True, timeout=60, check=False)
        if result.returncode:
            raise AssertionError(f'Host command failed ({result.returncode}): {argv}\n'
                                 + result.stderr.decode(errors='replace'))
        return result

    def test_native_c_oracle_geometry_fflags_and_all_bytes(self):
        self.assertEqual(len(self.shapes), 10)
        self.assertEqual(sum(len(shape['outputs']) for shape in self.shapes), 320)
        self.assertTrue(any(shape['flags'] & 2 for shape in self.shapes))
        self.assertTrue(any(shape['flags'] & 4 for shape in self.shapes))
        self.assertTrue(all(not shape['flags'] & 0x18 for shape in self.shapes))
        self.assertEqual(sum(shape['counters'][0] for shape in self.shapes), 40)
        self.assertEqual(sum(shape['counters'][6] for shape in self.shapes), 3648)

    def test_layout_pairs_have_identical_outputs_flags_and_counters(self):
        for index in range(0, 8, 2):
            a, b = self.shapes[index:index + 2]
            self.assertEqual(a['outputs'], b['outputs'])
            self.assertEqual(a['flags'], b['flags'])
            self.assertEqual(a['counters'], b['counters'])

    def test_scale_mul_is_only_inexact_source(self):
        for index, profile in ((8, 2), (9, 1)):
            shape = self.shapes[index]
            self.assertEqual(shape['profile'], profile)
            self.assertEqual(shape['flags'], 1)
            self.assertEqual(set(shape['outputs'].values()), {0})

    def test_nx_only_flag_cannot_be_dropped_or_hidden_by_output(self):
        for ordinal in (8, 9):
            lines = self.text.splitlines()
            index = next(i for i, line in enumerate(lines) if line.startswith(f'CMD {ordinal} '))
            fields = lines[index].split()
            self.assertEqual(fields[-1], '01')
            fields[-1] = '00'
            lines[index] = ' '.join(fields)
            with self.assertRaisesRegex(ValueError, 'NX-only oracle'):
                edges.parse_extras('\n'.join(lines) + '\n')

    def test_original_default_output_and_rng_unchanged(self):
        executable = self.directory / 'original'
        self.run_host(edges.gen_recipe(edges.SOURCE, executable))
        for mode, args in (('default', []), ('context', ['--context-suite'])):
            old, new = self.directory / (mode + '-old.txt'), self.directory / (mode + '-new.txt')
            self.run_host([executable, old, *args])
            self.run_host([self.executable, new, *args])
            self.assertEqual(old.read_bytes(), new.read_bytes())

    def test_matrix_changes_only_declared_dot_counter(self):
        matrix = edges.matrix_vectors(self.text)
        parsed = edges.parse_extras(matrix, matrix=True)
        for a, b in zip(self.shapes, parsed):
            self.assertEqual(a['outputs'], b['outputs'])
            self.assertEqual(a['flags'], b['flags'])
            self.assertEqual(a['counters'][5], 2 * b['counters'][5])
        strip_c = lambda text: [line for line in text.splitlines() if not line.startswith('C ')]
        self.assertEqual(strip_c(matrix), strip_c(self.text))

    def test_append_changes_no_old_body_or_workload(self):
        combined = edges.append_vectors(self.text, self.text)
        self.assertTrue(combined.startswith('QBSCMD1 20\n'))
        self.assertTrue(combined.split('\n', 1)[1].startswith(self.text.split('\n', 1)[1]))
        rows = edges._records(combined)
        self.assertEqual(len(rows), 20)
        for index in range(10):
            self.assertEqual(rows[index][1:], rows[index + 10][1:])
            self.assertEqual(rows[index][0].split()[2:], rows[index + 10][0].split()[2:])

    def test_parser_rejects_truncation_duplicate_and_wrong_byte(self):
        for bad in (self.text[:-10], self.text.replace('CMD 1 ', 'CMD 0 ', 1),
                    self.text.replace('W 0 0 ffff ', 'W 0 0 7fff ', 1),
                    self.text.replace('T 1 0 4', 'T 0 0 4', 1)):
            with self.assertRaises(ValueError):
                edges.parse_extras(bad)
        lines = self.text.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith('W 0 0 '))
        fields = lines[index].split()
        fields[-1] = fields[-1][:-2] + ('ff' if fields[-1][-2:] != 'ff' else '00')
        lines[index] = ' '.join(fields)
        with self.assertRaisesRegex(ValueError, 'Weight native bytes'):
            edges.parse_extras('\n'.join(lines) + '\n')

    def test_parser_rejects_nan_flags_and_changed_work(self):
        for before, after in (('O 0 ', 'O 999 '),
                              ('C 4 2304 2336 16384 16384 512 384 64',
                               'C 4 2304 2336 16384 16384 512 385 64')):
            with self.assertRaises(ValueError):
                edges.parse_extras(self.text.replace(before, after, 1))
        lines = self.text.splitlines()
        command = lines[1].split()
        command[-1] = '10'
        lines[1] = ' '.join(command)
        with self.assertRaises(ValueError):
            edges.parse_extras('\n'.join(lines) + '\n')
        lines = self.text.splitlines()
        index = next(i for i, line in enumerate(lines) if line.startswith('O '))
        lines[index] = lines[index].rsplit(' ', 1)[0] + ' 7fc00000'
        with self.assertRaises(ValueError):
            edges.parse_extras('\n'.join(lines) + '\n')


if __name__ == '__main__':
    unittest.main(verbosity=2)
