import copy
import json
from pathlib import Path
import tempfile
import unittest
from audit_fault_single import audit, signature
from classify_fault import classify
from test_classify_fault import BEGIN, CONTEXT, RETURN, CHECK
from trace_masks import sha


class FaultSingleTests(unittest.TestCase):
    def trial(self):
        return classify('\n'.join((BEGIN, CONTEXT, RETURN, CHECK)))['trials'][0]

    def test_relocation_only_is_normalized(self):
        a = self.trial(); b = copy.deepcopy(a)
        for key in ('address', 'expected_address'):
            b['contexts'][0][key] += 4096 * 53
        for key in ('pc', 'expected_pc'):
            b['contexts'][0][key] += 64
        self.assertEqual(signature(a), signature(b))
        for key in ('sig', 'code', 'address', 'pc', 'vstart', 'vl', 'vtype'):
            c = copy.deepcopy(b); c['contexts'][0][key] += 1
            self.assertNotEqual(signature(a), signature(c), key)

    def test_incomplete_rejected(self):
        with self.assertRaises(ValueError):
            signature(classify(BEGIN)['trials'][0])

    def test_audit_requires_identity_and_exact_tuple(self):
        self.check_audit(1)

    def test_segment_audit_requires_identity_and_exact_tuple(self):
        for fields in (2, 8):
            with self.subTest(fields=fields):self.check_audit(fields)

    def test_strided_audit_requires_identity_and_exact_tuple(self):
        for kind in ('positive', 'negative', 'zero'):
            with self.subTest(kind=kind):self.check_audit(1, kind)

    def check_audit(self, fields, stride=None):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp); name = 'single'
            suffix = (f'segment_nf{fields}_' if fields > 1 else '') + 'e8_mf8'
            begin = BEGIN
            if stride:
                suffix = 'strided' + {'positive': '', 'negative': '_negative_stride',
                                      'zero': '_zero_stride'}[stride] + '_e8_mf8'
                if stride != 'zero':begin += ' gap=3'
                else:begin = begin.replace('boundary=1', 'boundary=0')
            (root / 'binaries').mkdir(); (root / name).mkdir()
            (root / 'binaries' / name).write_bytes(b'elf')
            (root / name / 'scenario.c').write_text('source')
            output = '\n'.join((begin, CONTEXT, RETURN, CHECK,
                'RVV_FAULT_REPLAY_FAIL sew=8 cases=1 signals=1 errors=2'))
            measured = root / 'measured_report.json'
            measured.write_text(json.dumps(dict(results=[dict(
                name='rvv_trace_fault_replay_' + suffix, output=output)])))
            c = dict(name=name, sha256=sha(root / 'binaries' / name),
                     original_name='rvv_fault_replay_' + suffix, sew=8, lmul='mf8',
                     scenario_role='single_current_oracle_trial',
                     scenario_sources={'scenario.c': sha(root / name / 'scenario.c')},
                     selected_trial=classify(output)['trials'][0]['trigger'],
                     measured_trial=classify(output)['trials'][0])
            manifest = dict(trace_report_sha256=sha(measured), cases=[c])
            if fields > 1:
                manifest['diagnostic_layout'] = dict(fields=fields, indexed=False, strided=False)
            if stride:
                manifest['diagnostic_layout'] = dict(fields=fields, indexed=False, strided=True,
                    negative_stride=stride == 'negative', zero_stride=stride == 'zero')
            (root / 'manifest.json').write_text(json.dumps(manifest))
            report = dict(inputs=dict(cases=[dict(name=name, sha256=c['sha256'])]),
                          results=[dict(name=name, status='failed', exit_code=1, output=output)])
            path = root / 'report.json'
            def check():
                path.write_text(json.dumps(report))
                return audit(root, path)
            self.assertEqual(check()['confirmed'], 1)
            self.assertFalse(check()['original_failure_equivalence_proven'])
            report['results'][0]['output'] = output.replace('vstart=1', 'vstart=2')
            self.assertEqual(check()['confirmed'], 0)
            report['results'][0]['output'] = output.replace('split=0', 'split=1')
            self.assertEqual(check()['confirmed'], 0)
            if stride and stride != 'zero':
                report['results'][0]['output'] = output.replace('gap=3', 'gap=1')
                self.assertEqual(check()['confirmed'], 0)
            report['results'] = []
            self.assertEqual(check()['pending'], 1)
            report['inputs']['cases'][0]['sha256'] = 'different'
            with self.assertRaises(ValueError):
                check()


if __name__ == '__main__':
    unittest.main()
