import json
from pathlib import Path
import tempfile
import unittest
from audit_fp_compare import audit
from trace_masks import sha


class AuditTest(unittest.TestCase):
    def test_identity_and_symptom_gates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root/'small').mkdir()
            (root/'binaries').mkdir()
            (root/'small/scenario.S').write_text('assembly')
            (root/'binaries/small').write_bytes(b'ELF')
            detail = ('RVV_FP_COMPARE_DETAIL op=2 seed=1 vl=1 mask=0 sticky=0 '
                      'expected_flags=0 actual_flags=16 errors=1')
            old = dict(inputs=dict(cases=[dict(name='old', sha256='original')]),
                       results=[dict(name='old', status='failed', exit_code=1, output=detail)])
            original = root/'original_board_report.json'
            original.write_text(json.dumps(old))
            digest = sha(root/'binaries/small')
            asm = sha(root/'small/scenario.S')
            case = dict(name='small', original_name='old', original_elf_sha256='original',
                        sha256=digest, scenario_sources={'scenario.S': asm},
                        archived_assembly_sha256=asm, original_failure_detail=detail,
                        oracle_provenance='current_reconstruction')
            (root/'manifest.json').write_text(json.dumps(dict(
                cases=[case], original_report_sha256=sha(original))))
            report = dict(inputs=dict(cases=[dict(name='small', sha256=digest)]),
                          results=[dict(name='small', status='failed', exit_code=1, output=detail)])
            path = root/'report.json'
            def run():
                path.write_text(json.dumps(report))
                return audit(root, path)
            self.assertEqual(run()['confirmed'], 1)
            report['results'][0]['output'] = detail.replace('actual_flags=16', 'actual_flags=0')
            self.assertEqual(run()['confirmed'], 0)
            report['results'][0]['output'] = detail
            report['inputs']['cases'][0]['sha256'] = 'wrong'
            with self.assertRaises(ValueError):
                run()
            report['inputs']['cases'][0]['sha256'] = digest
            report['results'].append(dict(report['results'][0]))
            with self.assertRaises(ValueError):
                run()
            report['results'] = []
            self.assertEqual(run()['pending'], 1)
            (root/'small/scenario.S').write_text('changed')
            with self.assertRaises(ValueError):
                run()


if __name__ == '__main__':
    unittest.main()
