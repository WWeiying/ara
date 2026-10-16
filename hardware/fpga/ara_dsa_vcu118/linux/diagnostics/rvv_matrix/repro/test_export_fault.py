import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from export_fault import export
from trace_masks import sha


class ExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.base = Path(self.tmp.name)
        self.root, self.controls, self.proof = [self.base / n for n in ('root', 'controls', 'proof')]
        for p in (self.root, self.controls, self.proof):
            p.mkdir(); (p / 'binaries').mkdir()
        self.members = [dict(name='original'), dict(name='baseline'), dict(name='trace')]
        for c in self.members:
            (self.controls / 'binaries' / c['name']).write_bytes(b'control')
        (self.controls / 'manifest.json').write_text(json.dumps(dict(cases=self.members)))
        cases = [dict(name=n, scenario_sources={'scenario.c': 'audited'}) for n in ('yes', 'pending')]
        for c in cases:
            (self.root / c['name']).mkdir()
            (self.root / c['name'] / 'scenario.c').write_text('source')
            (self.root / 'binaries' / c['name']).write_bytes(b'elf')
        (self.root / 'manifest.json').write_text(json.dumps(dict(cases=cases,
            controls_manifest_sha256=sha(self.controls / 'manifest.json'))))
        self.checked = dict(cases=[dict(name='yes', confirmed=True), dict(name='pending', confirmed=False)])
        (self.proof / 'symptoms.json').write_text(json.dumps(self.checked))
        for p in (self.root / 'measured_report.json', self.proof / 'sampled_report.json',
                  self.base / 'original.json'):
            p.write_text('{}')

    def run_export(self, control_match=True, checked=None):
        with patch('export_fault.audit_single', return_value=checked or self.checked), \
             patch('export_fault.audit_controls', return_value=dict(cases=[
                 dict(aggregate_original_symptom_matches=control_match) for _ in range(3)])):
            return export(self.root, self.controls, self.proof, self.base / 'original.json', self.base / 'out')

    def test_select_and_hash_complete_handoff(self):
        result = self.run_export()
        self.assertEqual(result['exported_cases'], 1)
        self.assertFalse(result['original_failure_equivalence_proven'])
        out = self.base / 'out'
        self.assertFalse((out / 'singles/pending').exists())
        self.assertTrue((out / 'controls/original/scenario.elf').is_file())
        for name, digest in json.loads((out / 'hashes.json').read_text()).items():
            self.assertEqual(sha(out / name), digest)

    def test_control_mismatch_rejected_before_output(self):
        with self.assertRaises(ValueError):
            self.run_export(control_match=False)
        self.assertFalse((self.base / 'out').exists())

    def test_changed_control_manifest_rejected(self):
        (self.controls / 'manifest.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.run_export()

    def test_stale_proof_rejected(self):
        with self.assertRaises(ValueError):
            self.run_export(checked=dict(cases=[]))


if __name__ == '__main__':
    unittest.main()
