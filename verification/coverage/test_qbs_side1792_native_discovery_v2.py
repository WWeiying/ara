"""Actual host execution of generated1344 groups; retain frozen discovery tests."""
from pathlib import Path
import tkinter
import unittest

import prepare_qbs_side1792_native_discovery_v2 as successor
import test_qbs_side1792_native_discovery as original


class Successor(original.Discovery):
    def test_actual_failure_log_bound(self):
        diagnostic = successor.failure_evidence()
        self.assertFalse(diagnostic['DVE_API_or_license_failure'])
        self.assertEqual(diagnostic['native_evidence_rows'], 0)
        self.assertEqual(len(diagnostic['pins']), 6)

    def test_original_generated_selection_actual_failure(self):
        text = successor.OLD_SELECTION(self.artifact, Path('/sample.vdb'), 'sampletest')
        with self.assertRaises(tkinter.TclError) as error:
            successor.validate_generated(text, self.artifact, Path('/sample.vdb'), 'sampletest')
        self.assertIn('invalid command name', str(error.exception))

    def test_successor_actual_all_groups(self):
        text = successor.selection(self.artifact, Path('/sample.vdb'), 'sampletest')
        result = successor.validate_generated(text, self.artifact, Path('/sample.vdb'), 'sampletest')
        self.assertEqual(result['groups'], 1344)
        self.assertEqual(result['vectors'], 3584)
        self.assertFalse(result['native_qualified'])

    def test_evaluated_missing_duplicate_scope_vector_and_source(self):
        text = successor.selection(self.artifact, Path('/sample.vdb'), 'sampletest')
        line = next(l for l in text.splitlines(keepends=True) if l.startswith('lappend qsd_groups'))
        cases = (text.replace(line, '', 1), text.replace(line, line+line, 1),
                 text.replace('i_payload_buffer', 'i_foreign_buffer', 1),
                 text.replace('[list {01} {10} {11}]', '[list {01} {10} {unknown}]', 1),
                 text.replace('/sample.vdb', '/foreign.vdb', 1))
        for changed in cases:
            self.assertNotEqual(text, changed)
            with self.assertRaises(ValueError):
                successor.validate_generated(changed, self.artifact, Path('/sample.vdb'), 'sampletest')


if __name__ == '__main__':
    unittest.main()
