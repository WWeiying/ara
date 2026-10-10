import copy
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import run_final_raw740_dve as r


class Raw740Tests(unittest.TestCase):
    def test_actual_manifest_seal(self):
        manifest = r.life.read_bound(r.BASE / 'admission-manifest.json', r.BASE_SEAL)
        self.assertEqual(manifest['schema'], 'QUEUE_MASK_HISTORICAL740_ADMISSION_V1')
        self.assertEqual(manifest['baseline_seal'], r.PRIOR_SEAL)

    def test_actual_members(self):
        inputs = (r.BASE / 'combined-inputs.txt').read_text().splitlines()
        selected, files = r.member_files(inputs)
        self.assertEqual(len(set(selected)), 740)
        self.assertEqual(len(files), 3706)

    def test_wrong_count_rejected(self):
        with self.assertRaises(ValueError):
            r.member_files((r.BASE / 'combined-inputs.txt').read_text().splitlines()[:-1])

    def test_duplicate_rejected(self):
        inputs = (r.BASE / 'combined-inputs.txt').read_text().splitlines()
        inputs[-1] = inputs[-2]
        with self.assertRaises(ValueError):
            r.member_files(inputs)

    def test_summary_and_identity_gates(self):
        rows = r.common.summary_rows(r.REF / 'summary.csv')
        self.assertEqual(len(rows), 2989)
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)
            (out / 'DVEfiles').mkdir()
            (out / 'inputs.txt').write_text('design\ntest\n')
            (out / 'selected_tests.txt').write_text('native\n')
            (out / 'waiver_status.json').write_text(json.dumps(dict(mode='off', status='DISABLED', waived_report=None)))
            (out / 'diagnostics.txt').write_text('')
            (out / 'DVEfiles/dve_gui.log').write_text('DVE_SELECTED_TESTS: native\nDVE_COVERAGE_EXPORT_DONE\n')
            config = dict(report=str(out), input_ledger=['design', 'test'], selected_tests=['native'])
            with patch.object(r.common, 'summary_rows', return_value=rows):
                result = r.verify_report(config)
                self.assertEqual(result['rows'], 2989)
                self.assertTrue(all(v == '0.00' for v in result['percentage_point_delta_vs737'].values()))
                (out / 'diagnostics.txt').write_text('Warning: mismatch')
                with self.assertRaises(ValueError):
                    r.verify_report(config)
                (out / 'diagnostics.txt').write_text('')
                (out / 'selected_tests.txt').write_text('wrong\n')
                with self.assertRaises(ValueError):
                    r.verify_report(config)

    def test_2988_rows_rejected(self):
        rows = r.common.summary_rows(r.REF / 'summary.csv')
        with tempfile.TemporaryDirectory() as name:
            out = Path(name)
            (out / 'DVEfiles').mkdir()
            for filename, value in [('inputs.txt', 'design\ntest\n'), ('selected_tests.txt', 'native\n'),
                                    ('diagnostics.txt', ''), ('waiver_status.json',
                                     json.dumps(dict(mode='off', status='DISABLED', waived_report=None))),
                                    ('DVEfiles/dve_gui.log', 'DVE_SELECTED_TESTS: native\nDVE_COVERAGE_EXPORT_DONE\n')]:
                (out / filename).write_text(value)
            with patch.object(r.common, 'summary_rows', side_effect=[rows[:-1], rows]):
                with self.assertRaises(ValueError):
                    r.verify_report(dict(report=str(out), input_ledger=['design', 'test'], selected_tests=['native']))


if __name__ == '__main__':
    unittest.main()
