"""Metadata-only tests; no image launch or architectural acceptance."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import threading
from types import SimpleNamespace
import unittest

sys.dont_write_bytecode = True
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import checker
from adapter import NAME, runtime_case, successor_checked_runner

PLAN = checker.read(HERE.parent/'prepared01/plan.json')
LEDGER = checker.read(Path(PLAN['image'])/'image.json')
ORIGINAL_ROOT = HERE.parent/'prepared01/replay/tests'/NAME


class MetadataTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir=HERE, prefix='host_fixture_')
        self.root = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)
        self.case = copy.deepcopy(PLAN['case'])
        for name in ('input.elf', 'console.log', 'trace_summary.json'):
            shutil.copyfile(ORIGINAL_ROOT/name, self.root/name)
        (self.root/'work').mkdir()
        shutil.copyfile(ORIGINAL_ROOT/'work/run.vcs.log', self.root/'work/run.vcs.log')
        (self.root/'commit_trace.csv').write_text('metadata-only-host-fixture\n')
        self.command = dict(cwd=str(self.root/'work'), command=[LEDGER['simv'], '-l',
            'run.vcs.log', '+ntb_random_seed=1', '+PRELOAD='+str(self.root/'input.elf'),
            '+TESTCASE='+NAME, '+NO_FSDB', '+COMMIT_TRACE='+str(self.root/'commit_trace.csv')])
        self.write('command.json', self.command)
        self.write('inputs.json', dict(binary=dict(source=self.case['elf'],
            path=str(self.root/'input.elf'), sha256=self.case['sha256']),
            simv=dict(path=LEDGER['simv'], image_sha256=LEDGER['files'])))
        self.result = SimpleNamespace(name=NAME, status='PASS', returncode=0,
                                      elapsed_s=7.25, reason='', artifact_dir=self.root)

    def write(self, name, value):
        (self.root/name).write_text(json.dumps(value))

    def check(self):
        checker.common.check_artifacts(self.result, runtime_case(self.case), LEDGER)

    def test_runtime_copy_pass_and_original_unchanged(self):
        original = copy.deepcopy(self.case)
        self.check()
        self.assertEqual(original, self.case)
        with self.assertRaisesRegex(ValueError, 'Command provenance mismatch'):
            checker.common.check_artifacts(self.result, self.case, LEDGER)

    def test_wrong_runtime_seed_cwd_preload_rejected(self):
        for index, value in ((3, '+ntb_random_seed=2'),
                             (5, '+TESTCASE='+self.case['original_name']),
                             (4, '+PRELOAD='+self.case['elf'])):
            with self.subTest(index=index):
                bad = copy.deepcopy(self.command)
                bad['command'][index] = value
                self.write('command.json', bad)
                with self.assertRaisesRegex(ValueError, 'Command provenance mismatch'):
                    self.check()
        bad = copy.deepcopy(self.command)
        bad['cwd'] = str(self.root)
        self.write('command.json', bad)
        with self.assertRaisesRegex(ValueError, 'Command provenance mismatch'):
            self.check()

    def test_wrong_historical_identity_rejected(self):
        self.case['original_name'] = 'unrelated_source'
        with self.assertRaisesRegex(ValueError, 'identity'):
            self.check()

    def test_checker_throw_retains_actual_child_outcome(self):
        supplied = self.result
        class Parent:
            def _run_test(self, test, image):
                return supplied
        def throws(result):
            record = checker.read(self.root/'child_outcome.unvalidated.json')
            self.assertEqual(record['returncode'], 0)
            raise ValueError('intentional postcheck failure')
        abort = threading.Event()
        with self.assertRaisesRegex(ValueError, 'intentional postcheck'):
            successor_checked_runner(Parent, abort, throws)()._run_test(None, None)
        record = checker.read(self.root/'child_outcome.unvalidated.json')
        self.assertEqual((record['name'], record['status'], record['returncode'], record['elapsed_s']),
                         (NAME, 'PASS', 0, 7.25))
        self.assertEqual(record['command'], self.command)
        self.assertEqual(record['command_sha256'], checker.sha(self.root/'command.json'))
        self.assertFalse(record['architectural_acceptance'])
        self.assertTrue(abort.is_set())

    def test_nonzero_child_rc_preserved_without_validation(self):
        supplied = self.result
        supplied.status, supplied.returncode, supplied.reason = 'FAIL', 17, 'child failed'
        class Parent:
            def _run_test(self, test, image):
                return supplied
        abort = threading.Event()
        successor_checked_runner(Parent, abort, lambda _: self.fail('must not check'))()._run_test(None, None)
        record = checker.read(self.root/'child_outcome.unvalidated.json')
        self.assertEqual(record['returncode'], 17)
        self.assertTrue(abort.is_set())


if __name__ == '__main__':
    unittest.main()
