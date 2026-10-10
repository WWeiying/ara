import json
from pathlib import Path
import tempfile
import unittest

from inventory_historical_nonpass import collect


class InventoryTest(unittest.TestCase):
    def test_deduplicate_only_exact_name_and_elf_and_preserve_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for batch, rows in [('a', [{'name': 'x', 'elf_sha256': '1', 'status': 'FAIL'}]),
                                ('b', [{'name': 'x', 'elf_sha256': '1', 'status': 'TIMEOUT'},
                                       {'name': 'x', 'elf_sha256': '2', 'status': 'FAIL'},
                                       {'name': 'x', 'elf_sha256': '1', 'status': 'PASS'}])]:
                (root / batch).mkdir()
                (root / batch / 'all-outcomes.json').write_text(json.dumps(rows))
            result = collect(root)
            self.assertEqual(result['record_count'], 3)
            self.assertEqual(result['grouped_name_elf_count'], 2)
            self.assertEqual(len(result['groups'][0]['records']), 2)
            self.assertFalse(result['coverage_inputs_changed'])

    def test_old_image_case_failure_not_top_level_tool_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            batch = root / 'gap1-old-image-test'
            batch.mkdir()
            (batch / 'status.json').write_text(json.dumps(dict(status='FAILED', cases={
                'good': dict(status='PASS'), 'bad': dict(status='FAIL')})))
            result = collect(root)
            self.assertEqual(result['record_count'], 1)
            self.assertEqual(result['groups'][0]['name'], 'bad')
            self.assertIsNone(result['groups'][0]['elf_sha256'])


if __name__ == '__main__':
    unittest.main()
