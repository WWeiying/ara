import copy
import tempfile
import unittest
from pathlib import Path

import audit_csr_reserved1193_percent as audit


class PercentTests(unittest.TestCase):
    def test_actual_rooted_fixture(self):
        c = audit.frozen.life.read_bound(audit.SOURCE/'config.json', audit.CONFIG_SHA)
        values = audit.metrics(audit.SOURCE, c, 'before')
        self.assertEqual(values['Toggle'], '1.71%')
        self.assertEqual(values['Score'], '16.18%')
        self.assertEqual(audit.percent(values['Toggle']), 1.71)
        self.assertEqual(values['FSM'], 'NA')

    def test_strict_encoding(self):
        for bad in ('1.71', '1.71%%', ' 1.71%', '1.71% ', '+1%', '-1%',
                    'nan%', 'inf%', '1e1%', '.1%', '01%', '100.01%', 'NA', ''):
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                audit.percent(bad)
        self.assertEqual(audit.percent('0%'), 0)
        self.assertEqual(audit.percent('100.00%'), 100)

    def test_stage_effect_and_restoration(self):
        raw = dict(Score='16.18%', Line='28.52%', Toggle='1.71%', FSM='NA',
                   Condition='17.86%', Branch='16.61%')
        applied = dict(raw, Score='17.00%', Toggle='2.00%')
        values = {stage: copy.copy(applied if stage in ('selected', 'reloaded') else raw)
                  for stage in audit.frozen.STAGES}
        audit.compare_metrics(values)
        for stage, key, value in [('final', 'Toggle', '1.72%'),
                                  ('reloaded', 'Toggle', '2.01%'),
                                  ('selected', 'Line', '29.00%')]:
            changed = copy.deepcopy(values)
            changed[stage][key] = value
            with self.assertRaises(ValueError):
                audit.compare_metrics(changed)
        values['selected'] = values['reloaded'] = raw
        with self.assertRaises(ValueError):
            audit.compare_metrics(values)

    def test_actual_row_mutations_rejected(self):
        c = audit.frozen.life.read_bound(audit.SOURCE/'config.json', audit.CONFIG_SHA)
        text = (audit.SOURCE/'rooted_before.csv').read_text()
        with tempfile.TemporaryDirectory() as directory:
            out = Path(directory)
            for bad in (text.replace('1.71%', '1.71%%'),
                        text.replace('1.71%', '101%'),
                        text.replace('csr_regfile_i', 'foreign')):
                (out/'rooted_before.csv').write_text(bad)
                with self.assertRaises(ValueError):
                    audit.metrics(out, c, 'before')


if __name__ == '__main__':
    unittest.main()
