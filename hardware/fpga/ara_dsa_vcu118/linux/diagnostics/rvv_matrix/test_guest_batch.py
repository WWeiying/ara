import hashlib
from pathlib import Path
import subprocess
import tempfile
import unittest

from audit import audit
from guest_batch import Parser, script, configuration_count


RUN_ID = '0123456789abcdef'


class GuestBatchTests(unittest.TestCase):
    def test_fixed_reproducer_legacy_pass_is_exact_and_scoped(self):
        case=dict(name='rvv_repro_large_slideup',pass_marker='RVV_REPRO_PASS',sha256='b'*64)
        self.assertEqual(configuration_count(case,'RVV_REPRO_PASS errors=0'),1)
        for line in ('RVV_REPRO_PASS errors=1','RVV_REPRO_PASS','RVV_REPRO_PASS errors=0 junk'):
            self.assertIsNone(configuration_count(case,line))
        self.assertIsNone(configuration_count(dict(case,name='matrix'),'RVV_REPRO_PASS errors=0'))
        manifest=dict(cases=[case],archive_sha256='a'*64)
        parser=Parser(manifest,RUN_ID)
        parser.feed(f'RVVB:{RUN_ID}:PREP:0:{case["name"]}\nRVVB:{RUN_ID}:START:0:{case["name"]}\n'
                    f'RVV_REPRO_PASS errors=0\nRVVB:{RUN_ID}:END:0:{case["name"]}:0\nRVVB:{RUN_ID}:DONE:1\n')
        self.assertEqual(parser.report['results'][0]['status'],'passed')
        self.assertEqual(audit(manifest,parser.report)['passing_configurations'],1)

    def execute(self, bodies, corrupt=False):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            cases = []
            for index, body in enumerate(bodies):
                name = 'case_' + str(index)
                data = ('#!/bin/sh\n' + body + '\n').encode()
                (root/name).write_bytes(data)
                cases.append(dict(name=name, sha256=hashlib.sha256(data).hexdigest(),
                                  pass_marker='RVV_PASS'))
            manifest = dict(cases=cases, archive_sha256='a'*64)
            if corrupt:
                (root/'case_0').write_text('#!/bin/sh\ntouch EXECUTED\n')
            (root/'batch.sh').write_text(script(manifest, RUN_ID))
            result = subprocess.run(['sh', str(root/'batch.sh')], cwd='/',
                                    capture_output=True, text=True, timeout=5)
            parser = Parser(manifest, RUN_ID)
            # Deliberately split CRLF pairs and protocol lines across reads.
            for char in result.stdout.replace('\n', '\r\n'):
                parser.feed(char)
            return manifest, parser, result, (root/'EXECUTED').exists()

    def test_failure_continues_and_audits_complete(self):
        manifest, parser, result, _ = self.execute([
            "echo 'RVV_PASS cases=21 errors=0'",
            "echo 'RVV_FAIL cases=7 errors=1'; exit 1",
            "echo 'RVV_PASS cases=9 errors=0'",
        ])
        self.assertEqual(result.returncode, 0)
        summary = audit(manifest, parser.report)
        self.assertTrue(summary['complete'])
        self.assertFalse(summary['passed'])
        self.assertEqual(summary['counts']['passed'], 2)
        self.assertEqual(summary['passing_configurations'], 30)

    def test_markers_do_not_override_exit_or_uniqueness(self):
        manifest, parser, _, _ = self.execute([
            "echo 'RVV_PASS cases=1'; exit 132",
            'echo no_marker',
            "echo 'RVV_PASS cases=1'; echo 'RVV_PASS cases=1'",
            'echo RVV_PASS',
            "echo 'RVV_PASS cases=3 errors=0'",
        ])
        summary = audit(manifest, parser.report)
        self.assertEqual(summary['counts']['failed'], 4)
        self.assertEqual(summary['counts']['passed'], 1)

    def test_hash_failure_is_not_hardware_failure(self):
        manifest, parser, result, executed = self.execute(['exit 0'], corrupt=True)
        self.assertEqual(result.returncode, 2)
        self.assertFalse(executed)
        self.assertEqual(parser.report['state'], 'preparation_failed')
        self.assertEqual(parser.report['results'], [])
        self.assertEqual(audit(manifest, parser.report)['counts']['not_run'], 1)

    def test_running_without_end_is_not_pass(self):
        manifest = dict(archive_sha256='a'*64, cases=[dict(
            name='case_0', sha256='b'*64, pass_marker='RVV_PASS')])
        parser = Parser(manifest, RUN_ID)
        parser.feed(f'RVVB:{RUN_ID}:PREP:0:case_0\n')
        parser.feed(f'RVVB:{RUN_ID}:START:0:case_0\nRVV_PASS cases=1\n')
        self.assertEqual(audit(manifest, parser.report)['counts']['running'], 1)
        with self.assertRaises(ValueError):
            parser.feed(f'RVVB:{RUN_ID}:DONE:1\n')

    def test_wrong_order_and_duplicate_done_rejected(self):
        manifest, parser, _, _ = self.execute(["echo 'RVV_PASS cases=1'"])
        with self.assertRaises(ValueError):
            parser.feed(f'RVVB:{RUN_ID}:DONE:1\n')
        parser = Parser(manifest, RUN_ID)
        parser.feed('RVVB:ffffffffffffffff:START:0:case_0\n')
        self.assertEqual(parser.report['results'], [])
        with self.assertRaises(ValueError):
            parser.feed(f'RVVB:{RUN_ID}:START:0:case_0\n')

    def test_unsafe_manifest_rejected(self):
        manifest = dict(archive_sha256='a'*64, cases=[dict(
            name='../escape', sha256='b'*64, pass_marker='RVV_PASS')])
        with self.assertRaises(ValueError):
            script(manifest, RUN_ID)


if __name__ == '__main__':
    unittest.main()
