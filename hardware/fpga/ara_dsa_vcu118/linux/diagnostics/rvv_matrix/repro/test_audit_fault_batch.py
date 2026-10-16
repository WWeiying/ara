import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from audit_fault_batch import audit
from trace_masks import sha


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        (self.root / 'binaries').mkdir(); (self.root / 'shape').mkdir()
        (self.root / 'binaries/case').write_bytes(b'elf')
        (self.root / 'controls_board_report.json').write_text('{}')
        (self.root / 'board.json').write_text('{}')
        case = dict(name='case', sha256=sha(self.root / 'binaries/case'))
        child = dict(cases=[case], trace_report_sha256=sha(self.root / 'controls_board_report.json'))
        (self.root / 'shape/manifest.json').write_text(json.dumps(child))
        self.manifest = dict(groups=[dict(directory='shape', manifest_sha256=sha(self.root / 'shape/manifest.json'))],
                             measured_report_sha256=child['trace_report_sha256'], cases=[dict(case, source_group='shape')])
        self.save()

    def save(self):
        (self.root / 'manifest.json').write_text(json.dumps(self.manifest))

    def check(self, confirmed=0):
        with patch('audit_fault_batch.audit_single', return_value=dict(confirmed=confirmed, pending=1-confirmed)):
            return audit(self.root, self.root / 'board.json')

    def test_pending_is_not_confirmed(self):
        self.assertEqual(self.check()['pending'], 1)
        self.assertEqual(self.check(1)['confirmed'], 1)

    def test_changed_batch_elf(self):
        (self.root / 'binaries/case').write_bytes(b'changed')
        with self.assertRaises(ValueError): self.check()

    def test_wrong_membership(self):
        self.manifest['cases'][0]['source_group'] = 'wrong'; self.save()
        with self.assertRaises(ValueError): self.check()

    def test_duplicate_group(self):
        self.manifest['groups'] *= 2; self.save()
        with self.assertRaises(ValueError): self.check()

    def test_changed_child(self):
        (self.root / 'shape/manifest.json').write_text('{}')
        with self.assertRaises(ValueError): self.check()


if __name__ == '__main__':
    unittest.main()
