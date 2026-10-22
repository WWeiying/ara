import copy
import csv
import json
import tempfile
import unittest
from pathlib import Path

import rvh0_exception60_alias_successor as m


class AliasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.c = json.loads((m.FAILED / 'config.json').read_bytes())
        with (m.FAILED / 'native_before_0.tsv').open(newline='') as stream:
            cls.rows = list(csv.DictReader(stream, delimiter='\t'))

    def replay(self, rows, stage='before'):
        with tempfile.TemporaryDirectory(dir=m.frozen.life.OUT) as tmp:
            out = Path(tmp)
            with (out / ('native_%s_0.tsv' % stage)).open('w', newline='') as stream:
                writer = csv.DictWriter(stream, fieldnames=['handle', 'path', 'meta', 'name', 'excluded'], delimiter='\t')
                writer.writeheader()
                writer.writerows(rows)
            return m.inventory(out, self.c, stage, 0)

    def test_actual_first_scope_and_original_reject(self):
        with self.assertRaisesRegex(ValueError, 'Foreign/duplicate'):
            m.frozen.inventory(m.FAILED, self.c, 'before', 0)
        result = self.replay(self.rows)
        self.assertEqual(len(result['bindings']), 692)
        self.assertEqual(sum(b['kind'] == 'arrays' for b in result['bindings']), 2)
        self.assertEqual(sum(b['role'] == 'target' for b in result['bindings']), 9)

    def test_no_config_mutation_or_other_alias_expansion(self):
        c = copy.deepcopy(self.c)
        changed = m.adjusted(c)
        self.assertEqual(c, self.c)
        diffs = [(a, b) for i, j in zip(c['instances'], changed['instances'])
                 for a, b in zip(i['bindings'], j['bindings']) if a != b]
        self.assertEqual(len(diffs), 1)
        self.assertEqual(diffs[0][0]['name'], m.NAME)
        self.assertEqual(diffs[0][1]['role'], 'protected')

    def test_wrong_range_type_role_and_source_rejected(self):
        for key, value in [('left', '15'), ('right', '13'), ('file', '547'), ('type', '2')]:
            c = copy.deepcopy(self.c)
            b = next(b for b in c['instances'][0]['bindings'] if b['name'] == m.NAME)
            b['attributes'][key] = value
            with self.assertRaises(ValueError):
                m.adjusted(c)
        c = copy.deepcopy(self.c)
        next(b for b in c['instances'][0]['bindings'] if b['name'] == m.NAME)['role'] = 'target'
        with self.assertRaises(ValueError):
            m.adjusted(c)

    def test_unknown_partial_array_and_duplicate_rejected(self):
        for name in ['instr.rvftype.repl[14]', 'instr.rvftype.repl[15:15]', 'foreign', 'fflags_ex_i[3:0]']:
            rows = copy.deepcopy(self.rows)
            row = next(r for r in rows if r['name'] == m.NAME)
            for key in ('path', 'meta', 'name'):
                row[key] = name
            with self.assertRaises(ValueError):
                self.replay(rows)
        rows = copy.deepcopy(self.rows)
        other = next(r for r in rows if r['name'].startswith('fflags_ex_i['))
        for key in ('path', 'meta', 'name'):
            other[key] = m.NAME + '[14:14]'
        with self.assertRaisesRegex(ValueError, 'Foreign/duplicate'):
            self.replay(rows)

    def test_protected_flags_every_stage(self):
        targets = {label for b in self.c['instances'][0]['bindings'] if b['role'] == 'target'
                   for label in b['allowed_labels']}
        for stage in m.frozen.STAGES:
            rows = copy.deepcopy(self.rows)
            for row in rows:
                row['excluded'] = str(int(stage in ('selected', 'reloaded') and row['name'] in targets))
            next(r for r in rows if r['name'] == m.NAME)['excluded'] = '1'
            with self.assertRaisesRegex(ValueError, 'Target/protected membership differs: ' + m.NAME):
                self.replay(rows, stage)

    def test_missing_capture_and_target_exclusion_rejected(self):
        with self.assertRaisesRegex(ValueError, 'Incomplete'):
            self.replay(self.rows[:-1])
        rows = copy.deepcopy(self.rows)
        target = next(b['allowed_labels'][0] for b in self.c['instances'][0]['bindings'] if b['role'] == 'target')
        next(r for r in rows if r['name'] == target)['excluded'] = '1'
        with self.assertRaises(ValueError):
            self.replay(rows)


if __name__ == '__main__':
    unittest.main()
