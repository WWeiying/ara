import unittest
import json
from pathlib import Path
import tempfile
from audit_redspecial import audit, compare, details
from trace_masks import sha


LINE = 'RVV_FP_REDSPECIAL_DETAIL scenario=3 op=0 vl=16 mask=3 frm=0 flags=0 expected_flags=16'


class ReductionMatchTests(unittest.TestCase):
    def test_identity_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'binaries').mkdir()
            (root / 'small').mkdir()
            binary = root / 'binaries/small'; binary.write_bytes(b'candidate')
            rebuilt = root / 'small/original_rebuilt.elf'; rebuilt.write_bytes(b'original')
            source = root / 'small/scenario.c'; source.write_text('fixture')
            original = root / 'original.json'
            original.write_text(json.dumps(dict(inputs=dict(cases=[dict(name='parent', sha256=sha(rebuilt))]),
                results=[dict(name='parent', status='failed', exit_code=1, output=LINE)])))
            manifest = dict(original_report_sha256=sha(original), cases=[dict(name='small',
                original_name='parent', sha256=sha(binary), original_elf_sha256=sha(rebuilt),
                scenario_sources={'scenario.c': sha(source)}, original_failure_detail=LINE)])
            (root / 'manifest.json').write_text(json.dumps(manifest))
            data = dict(inputs=dict(cases=[dict(name='small', sha256=sha(binary))]),
                results=[dict(name='small', status='failed', exit_code=1, output=LINE)])
            report = root / 'report.json'
            report.write_text(json.dumps(data))
            self.assertEqual(audit(root, original, report)['confirmed'], 1)
            data['inputs']['cases'][0]['sha256'] = 'wrong'
            report.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'Deployed ELF'):
                audit(root, original, report)
            data['inputs']['cases'] = []
            report.write_text(json.dumps(data))
            with self.assertRaisesRegex(ValueError, 'no deployed identity'):
                audit(root, original, report)
            data['results'] = []
            report.write_text(json.dumps(data))
            self.assertEqual(audit(root, original, report)['pending'], 1)
            source.write_text('changed')
            with self.assertRaisesRegex(ValueError, 'source changed'):
                audit(root, original, report)

    def test_exact_match(self):
        result = dict(status='failed', exit_code=1, output=LINE)
        self.assertTrue(compare(result, result, LINE)['confirmed'])
        self.assertFalse(compare(result, result, LINE)['raw_result_bits_equivalence_proven'])

    def test_every_field_matters(self):
        original = dict(status='failed', exit_code=1, output=LINE)
        for key, value in details(LINE)[0].items():
            other = dict(original, output=LINE.replace(f'{key}={value}', f'{key}={value + 1}'))
            self.assertFalse(compare(original, other, LINE)['confirmed'], key)

    def test_failure_status_and_exit_required(self):
        original = dict(status='failed', exit_code=1, output=LINE)
        for change in (dict(status='stalled'), dict(status='passed'), dict(exit_code=2)):
            self.assertFalse(compare(original, dict(original, **change), LINE)['confirmed'])

    def test_bad_details_rejected(self):
        for line in (LINE + ' op=0', LINE.replace(' vl=16', ''), LINE + ' junk'):
            with self.assertRaises(ValueError):
                details(line)

    def test_passing_flags_not_a_failure_witness(self):
        with self.assertRaises(ValueError):
            compare({}, {}, LINE.replace('flags=0 ', 'flags=16 '))


if __name__ == '__main__':
    unittest.main()
