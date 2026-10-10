import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest

import verify_qbs_cause_constants_native_offline as m


class ActualPercentReplay(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = m.original.life.read_bound(m.OUT / 'config.json', m.SEAL)

    def test_actual_complete_original_verification_with_only_percent_adapter(self):
        hold_sha = m.original.life.digest(m.OUT / 'qualification-reject.json')
        with contextlib.redirect_stdout(io.StringIO()): result = m.collect()
        self.assertEqual(result['canonical_EL_direction_members'], 1486)
        self.assertEqual(result['actual_inventory_objects'], 622)
        self.assertEqual(result['protected_target_bits'], 216)
        self.assertFalse(result['population_application'])
        self.assertEqual(hold_sha, m.original.life.digest(m.OUT / 'qualification-reject.json'))
        self.assertFalse((m.OUT / 'capture-result.json').exists())

    def test_actual_terminal_not_done_substitute(self):
        terminal = json.loads((m.OUT / 'terminal.json').read_bytes())
        self.assertEqual(terminal['returncode'], 0)
        self.assertFalse(terminal['timeout'])
        self.assertEqual(len(terminal['actual_dve']), 1)

    def test_actual_percent_identity_all_five_stages(self):
        values = {s: m.metrics(m.OUT, self.c, s) for s in m.original.STAGES}
        self.assertEqual(values['before'], values['reset'])
        self.assertEqual(values['before'], values['final'])
        self.assertEqual(values['selected'], values['reloaded'])

    def test_malformed_nan_bare_suffix_out_of_range_and_missing_metric_rejected(self):
        with (m.OUT / 'rooted_before.csv').open(newline='') as f:
            reader = csv.DictReader(f); fields = reader.fieldnames; source = list(reader)
        with tempfile.TemporaryDirectory(dir=m.original.life.OUT) as tmp:
            out = Path(tmp)
            for value in ('17.94', '17.94%%', 'NaN%', '101.00%', '-1.00%', '17.9%', 'NA'):
                rows = [dict(p) for p in source]; rows[0]['Toggle'] = value
                with (out / 'rooted_before.csv').open('w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
                with self.subTest(value=value), self.assertRaises(ValueError): m.metrics(out, self.c, 'before')

    def test_duplicate_scope_or_wrong_actual_token_rejected(self):
        with (m.OUT / 'rooted_before.csv').open(newline='') as f:
            reader = csv.DictReader(f); fields = reader.fieldnames; source = list(reader)
        with tempfile.TemporaryDirectory(dir=m.original.life.OUT) as tmp:
            out = Path(tmp)
            for rows in ([source[0], source[0], source[2]],
                         [dict(source[0], Token='other'), source[1], source[2]]):
                with (out / 'rooted_before.csv').open('w', newline='') as f:
                    writer = csv.DictWriter(f, fieldnames=fields); writer.writeheader(); writer.writerows(rows)
                with self.assertRaises(ValueError): m.metrics(out, self.c, 'before')


if __name__ == '__main__': unittest.main()
